# How CAS Notifies Services of Session Termination

> **Module:** Spring Security – federation · **Group:** CAS Logout. This lesson covers CAS **Single Logout (SLO)** when a centralized login session is terminated: the CAS Server knows which services received a Service Ticket, broadcasts notifications to each service, and the **CAS client** must delete the right local session. The content applies to the **native CAS protocol** rather than mixing it up with SAML 2.0 SLO or OpenID Connect logout. Pure Java snippets require JDK 17+; Spring Security/CAS Java Client snippets require dependencies and compatibility checks against the actual Spring Boot/Security/Servlet API versions.

## 1. Why does CAS logout need to notify each application?

Suppose the same user uses three internal applications:

| System | Login mechanism | Session state |
| --- | --- | --- |
| CAS Server `https://sso.example.org/cas` | Authenticates user/MFA, issues tickets | TGT in the CAS ticket registry, TGC cookie on the CAS domain |
| Portal A | Validates its own ST issued by CAS | Local HttpSession/SecurityContext A |
| Reports B | Validates a different ST via CAS SSO | Local HttpSession/SecurityContext B |
| Workflow C | Validates a third ST | Local HttpSession/SecurityContext C |

**The CAS Server is the central authenticator, not the HttpSession manager for A/B/C.** The TGT can remain active when A performs a local logout; conversely, CAS deleting the TGT does not automatically invalidate three sessions living in three separate applications.

**CAS Single Logout (SLO)** adds notification capability: when a CAS SSO session ends, CAS finds the **services used in that session** and sends logout messages. Each service **must handle** the notification, locate the exact local session logged in via the CAS-issued Service Ticket, and invalidate it.

Key takeaway: **CAS sends notifications; the client actually terminates the application session**. A successful CAS logout does not guarantee every application session has been destroyed; per documentation, CAS SLO is a **best effort** process.

### Learning objectives

After this lesson, you will be able to:

1. Distinguish application local logout, CAS logout, and Single Logout.
2. Explain how CAS uses the **TGT → Service Tickets → service URLs** relationship to decide where to send notifications.
3. Understand that `SessionIndex` in CAS SLO usually holds the **Service Ticket ID**, not the TGT or session cookie.
4. Read `logoutRequest` XML and understand **back-channel POST** and **front-channel** AJAX/JSONP/iframe.
5. Explain the CAS Java Client **ST ID → HttpSession** session mapping.
6. Integrate `SingleSignOutFilter` and `SingleSignOutHttpSessionListener` with Spring Security CAS.
7. Protect the SLO callback: caller origin, XML parsing, scope, replay, and CSRF boundary.
8. Design for multiple pods with a distributed session repository and session mapping.
9. Understand best-effort limits, timeouts, late logout events, and partial success.
10. Run a Java 17 demo simulating multiple sessions, sending notifications, idempotency, and isolation.

## 2. Distinguishing three logout levels

| Operation | Who initiates? | Terminated session | What does not happen automatically |
| --- | --- | --- | --- |
| **Local logout A** | User clicks log out in Portal A | HttpSession and Spring SecurityContext **A** | CAS TGT/TGC and sessions B/C are not automatically removed |
| **CAS logout** | Browser/user or CAS policy ends SSO | TGT in CAS Server and CAS browser SSO cookie | Local HttpSessions A/B/C are not directly deleted by CAS |
| **CAS SLO** | CAS broadcasts notifications after CAS logout/expiration per policy | **CAS clients** invalidate their respective sessions | No 100% delivery/success guarantee; does not by default delete all sessions of the same user across all devices |

### 2.1. Why can local logout lead to immediate re-login?

The user logs out of Portal A, yet the CAS TGC still exists. When the browser revisits Portal, A redirects to CAS login; CAS sees a valid TGC/TGT and can issue a **new ST** without prompting for a password. From the user's perspective, logging out of A "did not stick". That is the difference between local logout and SSO logout, not an ST being reused.

### 2.2. Why can CAS logout leave Reports authenticated?

CAS only controls the TGT/TGC on the CAS Server. Reports B already validated `ST-B` and established local HttpSession B; subsequent `GET /reports` requests use the Reports session cookie without contacting CAS on every request. If B has no SLO client installed or the notification never arrives, Reports can continue serving authenticated requests until local expiry/logout.

### 2.3. SLO does not mean "log out of all devices"

CAS SLO normally affects **one CAS SSO session** and the services recorded under that TGT. The same user on laptop B may hold a separate TGT and different application sessions. If "logout all devices" is required, a broader session revocation policy is needed rather than inferring it solely from SLO notifications for the current TGT.

## 3. Tickets and cookies involved in SLO

| Identifier | Who holds it? | Role |
| --- | --- | --- |
| **TGT — Ticket-Granting Ticket** | CAS Server | SSO session; knows which services authenticated |
| **TGC — Ticket-Granting Cookie** | Browser, scoped to CAS domain | Allows CAS to recognize the SSO session when /login is visited |
| **ST — Service Ticket** | Issued by CAS Server; browser delivers to service; service validates | Single-use for one service; the ST ID also correlates CAS SLO |
| **HttpSession ID** | Services A/B/C and browser cookie | Identifies the local application session; unknown directly to CAS Server |
| **CAS SLO SessionIndex** | Inside the logoutRequest sent by CAS | The prior **ST ID** for the service being logged out |
| **CAS client session mapping** | Each CAS service | `ST ID → local HttpSession` for invalidation |

**Do not use the TGT as the CAS client session key.** The CAS client does not need to know the CAS TGT secret. It only receives its own ST and knows which session was established after ST validation.

### 3.1. How CAS knows which services via ST records

```text
CAS TGT-USER-001
  |
  +-- issued ST-PORTAL-001 -> Portal A
  +-- issued ST-REPORTS-002 -> Reports B
  +-- issued ST-WORKFLOW-003 -> Workflow C

Portal local mapping:  ST-PORTAL-001 -> HttpSession P-123
Reports local mapping: ST-REPORTS-002 -> HttpSession R-456
Workflow mapping:      ST-WORKFLOW-003 -> HttpSession W-789
```

When CAS terminates the TGT, it can send Portal a message with SessionIndex=`ST-PORTAL-001`; Reports receives SessionIndex=`ST-REPORTS-002`; Workflow receives `ST-WORKFLOW-003`. Each app finds its own session.

### 3.2. Login validity of ST expires, yet its ID remains useful

Once a Service Ticket is validated by CAS, it **cannot be reused to log in**. However, the ST ID can still be stored by the CAS client as a **correlation key** for logout. This does not permit replaying the ST. This mapping must be cleared when the application session expires, on local logout, or once SLO is processed.

**Do not log raw STs**, because an ST can be exposed before consumption and the ST ID could later participate in targeted forced-logout if the SLO endpoint lacks caller authentication.

### 3.3. Two browser sessions for the same user

```text
Browser 1: TGT-1 -> ST-A-1 -> AppSession-A-1
Browser 2: TGT-2 -> ST-A-2 -> AppSession-A-2
```

A CAS logout of TGT-1 should only invalidate AppSession-A-1. **Do not** read `NameID=alice` and delete every session for `alice`, as that can cause out-of-scope or cross-tenant impact.

## 4. Login sequence before SLO

### 4.1. Portal and Reports sharing CAS SSO

```text
Browser               Portal A                CAS Server               Reports B
  |                      |                         |                        |
  | GET /dashboard       |                         |                        |
  |--------------------->|                         |                        |
  |<---------------------| redirect /cas/login?service=Portal             |
  |------------------------------------------------>|                        |
  |                  CAS login/TGT/TGC              |                        |
  |<------------------------------------------------| redirect ST-PORTAL-1   |
  | GET Portal callback?ticket=ST-PORTAL-1         |                        |
  |--------------------->|                         |                        |
  |                      | CAS /serviceValidate    |                        |
  |                      |------------------------>|                        |
  |                      |<------------------------| cas:user=alice         |
  |                      | map ST -> P-session     |                        |
  |                      |                         |                        |
  | GET Reports /finance -----------------------------------------------> |
  |<---------------------------------------------- redirect CAS /login   |
  |------------------------------------------------>|                        |
  |                   CAS TGC still valid            |                        |
  |<------------------------------------------------| ST-REPORTS-1 redirect |
  |--------------------------------------------------------------------> |
  |                                    Reports validates, maps ST -> R-session |
```

The CAS TGT now tracks two services. Portal A and Reports B **do not share the same HttpSession** even though the user entered a password only once.

### 4.2. When does each service begin storing ST→session?

After CAS `/serviceValidate` confirms the ST for the service and Spring Security creates an authenticated context, the CAS client SLO handler needs to know **which HttpSession corresponds to this login's ST ID**. Some CAS client libraries automatically record the mapping via a filter/handler during login; when customizing filters or session fixation policies, verify that the mapping is created for **the actual authenticated session**.

**Do not** store the mapping simply because the browser sent `ticket=ST-...` before validating the ST: an attacker can send bogus tickets and corrupt the mapping or session. Integrate a standard CAS client and verify the behavior with an integration test.

## 5. When the CAS TGT ends: CAS dispatches notifications

### 5.1. Triggering event

Typically the user logs out of CAS via `/cas/logout` or the TGT expires per CAS policy. The CAS server deletes/expires the SSO state; if Single Logout is enabled for the registered services, CAS selects the services/tickets to notify.

The CAS Protocol and Apereo CAS describe SLO when a **TGT is explicitly terminated**; dispatching on idle timeout may depend on configuration/version. Do not assume every cleanup job/TTL eviction fires callbacks identically.

### 5.2. Overall sequence

```text
Browser           CAS Server                    Portal A              Reports B
   |                  |                             |                     |
   | CAS /logout      |                             |                     |
   |----------------->|                             |                     |
   |                  | expire TGT / clear TGC      |                     |
   |                  | lookup ST/service records   |                     |
   |                  |                             |                     |
   |                  | POST SLO for ST-PORTAL-1    |                     |
   |                  |---------------------------->|                     |
   |                  |                             | find mapping        |
   |                  |                             | session.invalidate |
   |                  |<----------------------------| HTTP response       |
   |                  |                                                   |
   |                  | POST SLO for ST-REPORTS-1 ----------------------->|
   |                  |                                                   | invalidate
   |                  |<--------------------------------------------------| HTTP response
   |<-----------------| CAS logout UI/redirect     |                     |
```

The diagram illustrates the logical flow **without guaranteeing order**: Apereo CAS has asynchronous back-channel mechanisms and may not wait for all apps to respond. CAS logout is not rolled back if one service fails.

### 5.3. CAS logout does not directly delete application cookies

The TGC cookie at `sso.example.org` is separate from the `JSESSIONID` cookie at `portal.example.org`. The CAS Server cannot remotely invoke Java `session.invalidate()` in Portal A. It **sends a notification**, and CAS client A looks up the ST→HttpSession mapping to perform local invalidation.

The browser may **still retain the old JSESSIONID** even though the server session is destroyed. QA should resend the old cookie to a protected route and verify it is treated as anonymous/redirected to login, rather than relying on whether the browser cookie still appears.

## 6. Back-channel: CAS Server sends a direct HTTP POST

Apereo CAS defines the `BACK_CHANNEL` type most commonly used by server-side CAS clients.

### 6.1. Notification and path

```text
CAS Server
  POST https://portal.example.org/login/cas
    Content-Type: application/x-www-form-urlencoded
    logoutRequest=(form-encoded CAS SLO XML)
        |
        v
Reverse proxy -> CAS client SLO handler/filter
        |
        v
Parse SessionIndex = ST-PORTAL-1
        |
        v
Lookup ST-PORTAL-1 -> HttpSession P-123
        |
        v
P-123.invalidate()
        |
        v
Remove ST→session mapping / return HTTP result
```

This is a **server-to-server request**, not the browser sending Portal's session cookie. CAS can POST to the **original service URL** used to issue the ST, or a separate `logoutUrl` declared in the registered service configuration.

### 6.2. Example LogoutRequest

Apereo CAS SLO uses XML shaped like:

```xml
<samlp:LogoutRequest
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_sample-event-001"
    Version="2.0"
    IssueInstant="2026-11-07T04:00:00Z">
  <saml:NameID>alice</saml:NameID>
  <samlp:SessionIndex>ST-PORTAL-1</samlp:SessionIndex>
</samlp:LogoutRequest>
```

This is an **illustrative fixture**, not a real signed notification. Key points:

- `SessionIndex`: the **CAS Service Ticket ID** for the client to locate the session, not the HttpSession ID.
- `NameID`: may describe the principal; **never use it alone to delete all sessions sharing a username**.
- `ID`/`IssueInstant`: may support replay/freshness checks depending on implementation.
- An XML namespace containing SAML2 **does not prove the request carries a digital signature** or conforms to a full SAML2 SLO profile.

In traditional CAS SLO, **the message may contain no XML signature**. If a public endpoint accepts a POST with only `SessionIndex` and invalidates any session, an outsider who knows an ST ID can trigger a forced logout. Protecting caller/network identity and correlation is mandatory per the threat model.

### 6.3. An illustrative HTTP request

```http
POST /login/cas HTTP/1.1
Host: portal.example.org
Content-Type: application/x-www-form-urlencoded

logoutRequest=URL_ENCODED_CAS_SLO_XML
```

`URL_ENCODED_CAS_SLO_XML` is a descriptive placeholder. In practice, the CAS Java Client parses the parameter via its API; do not write a custom regex-based XML string parser. Do not log raw form bodies, queries, NameID, or STs.

### 6.4. Which URL does CAS send SLO to by default?

Apereo documentation states that by default CAS sends the logout request to the **service identifier** used during authentication. A registered service can configure a separate `logoutUrl`, for example:

```json
{
  "@class": "org.apereo.cas.services.CasRegisteredService",
  "name": "Portal CAS Client",
  "id": 2101,
  "serviceId": "https://portal[.]example[.]org/login/cas",
  "logoutType": "BACK_CHANNEL",
  "logoutUrl": "https://portal.example.org/cas/slo"
}
```

The JSON above is an **illustrative schema**; exact serialization/validation of configuration and service ID matching strategy depend on the Apereo CAS version. Do not use it directly in production without verifying against your running CAS release/service registry.

If `logoutUrl=/cas/slo` is set, ingress, application routing, and the SLO handler must accept POST at that exact URL. A custom Spring controller that only permits GET could return 405 before the SLO filter handles it.

## 7. Front-channel: CAS instructs the browser to notify logout

Some CAS versions support `FRONT_CHANNEL`: CAS uses the browser to send requests to applications, typically via AJAX/JSONP GET or an iframe.

```text
CAS logout page in browser
     |
     +--> GET Portal SLO URL?
          logoutRequest=BASE64_MESSAGE&callback=...
     |
     +--> GET Reports SLO URL?
          logoutRequest=BASE64_MESSAGE&callback=...
     |
     +--> Client code/filter processes when supported
```

Apereo CAS documentation **warns that not all CAS clients support front-channel**. Risk factors:

- Browser/tab closes before the AJAX/iframe completes.
- Third-party cookie restrictions, `SameSite`/CSP/CORS, popup/tracking blockers.
- The app client does not accept the JSONP GET variant or uses a different method/path.
- JS errors, slow networks, or the service being down.
- GET carrying logout data risks spoofed calls/caching/logging if a custom handler fails to validate context.
- You cannot conclude all services were invalidated simply because the CAS logout page finished loading.

**Selection guidance:** Spring MVC applications using server-side sessions usually fit BACK_CHANNEL with CAS callback origin authentication, provided the CAS Server can reach the service URL. FRONT_CHANNEL requires testing specific browser/client support rather than enabling by assumption.

## 8. Registered services configure the notification type

In Apereo CAS service management, `logoutType` has the following meanings:

| logoutType | Behavior |
| --- | --- |
| `BACK_CHANNEL` | CAS Server sends a direct POST per the CAS SLO protocol |
| `FRONT_CHANNEL` | CAS Server uses the browser to dispatch logout notifications |
| `NONE` | Do not send SLO notifications to this service |

Per Apereo CAS docs, BACK_CHANNEL is noted as the default for registered services in corresponding versions. Check your deployed release and actual registry because system defaults may vary by policy.

### 8.1. Enabling SLO does not install a client handler

Enabling SLO on the CAS Server **only means CAS sends notifications**. If a service lacks a CAS client SLO handler, the POST may be logged as an unexpected request, return 404/405/403, or return 200 from the wrong handler while the session remains alive. Checking only server-side `logoutType=BACK_CHANNEL` is insufficient.

### 8.2. Service-specific logoutUrl different from /login callback

A service may use `https://portal.example.org/login/cas` for CAS login while sending logout notifications to `https://portal.example.org/cas/slo`. Therefore you must:

1. Register `logoutUrl` in the CAS service registry with an approved origin/path.
2. Open HTTPS connectivity from CAS Server → service callback.
3. Configure the CAS client filter/handler to accept POST on the exact path.
4. Protect the notification source; do not allow arbitrary browser POSTs to destroy sessions.
5. Test actual session invalidation, not just that the message reached ingress.

Do not take `logoutUrl` from browser queries, and do not use ambiguous wildcard hosts/ports/paths without clear ownership.

## 9. CAS Java Client and Spring Security: session mapping

### 9.1. Application components

| Component | Role |
| --- | --- |
| `CasAuthenticationEntryPoint` | Redirects browser to CAS login when authentication is needed |
| `CasAuthenticationFilter` | Receives ST from CAS callback to create an authentication request |
| `CasAuthenticationProvider` | Validates ST via CAS Server/TicketValidator and builds the principal in Spring Security |
| `ServiceProperties` | Public service URL used to issue/validate tickets |
| **`SingleSignOutFilter`** | CAS Java Client filter that receives SLO requests and maintains/processes ticket-session mapping per version |
| **`SingleSignOutHttpSessionListener`** | Cleans up the mapping when an HttpSession expires or is invalidated |
| `SessionMappingStorage` | Contract for storing/looking up ST→HttpSession in the CAS client |
| `SecurityContext`/`HttpSession` | Local authenticated state in the service that needs to be destroyed |

**Note:** `SingleSignOutFilter` and its listener belong to **Apereo CAS Java Client**, not Spring Security SAML2's `Saml2LogoutRequestFilter`.

### 9.2. Why is the listener important?

The service stored `ST-A-1 → HttpSession A-1`. When the user performs local logout on A or the session hits idle timeout, the stale mapping must be removed. Otherwise, the map can accumulate stale references, grow memory usage, and risk an old SLO message affecting the wrong session after a new authentication.

`SingleSignOutHttpSessionListener` cleans up the map at the end of the session lifecycle; in multi-pod setups, verify that the actual mapping uses the proper distributed implementation across nodes.

### 9.3. Filter ordering really matters

`SingleSignOutFilter` must receive requests and be positioned properly **before the CAS auth filter** to process POST notifications without being routed through a login redirect, CSRF handler, or wrong @Controller.

The CAS Java Client may also use this filter to record the ticket→session association on incoming login requests. Therefore you must test:

- The mapping exists after successful CAS ticket validation.
- The mapping points to the real session after Spring Security session-fixation rotation.
- A CAS SLO POST finds the mapping and invalidates the right session.
- Duplicate notifications do not destroy a new session.
- Local logout/session expiry removes the mapping.

## 10. Spring Boot Servlet configuration example

This is an example **Spring configuration class**, requiring a CAS Java Client compatible with Jakarta Servlet on Spring Boot 3.x. Older client versions using `javax.servlet` may not run directly on Boot 3 (Jakarta); verify dependencies/Javadoc for your exact version.

```java
import org.apereo.cas.client.session.SingleSignOutFilter;
import org.apereo.cas.client.session.SingleSignOutHttpSessionListener;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.boot.web.servlet.ServletListenerRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;

@Configuration
public class CasSloServletConfiguration {

    @Bean
    FilterRegistrationBean<SingleSignOutFilter> casSingleSignOutFilter() {
        FilterRegistrationBean<SingleSignOutFilter> registration =
                new FilterRegistrationBean<>();
        registration.setFilter(new SingleSignOutFilter());
        registration.addUrlPatterns("/*");
        registration.setOrder(Ordered.HIGHEST_PRECEDENCE + 10);
        return registration;
    }

    @Bean
    ServletListenerRegistrationBean<SingleSignOutHttpSessionListener>
            casSloHttpSessionListener() {
        return new ServletListenerRegistrationBean<>(
                new SingleSignOutHttpSessionListener());
    }
}
```

**This is an integration fragment**, not a complete Spring Boot project. You still need the CAS login entry point/filter/provider, Spring Security filter chain, CAS Server registry, session store, and network security. `Ordered.HIGHEST_PRECEDENCE + 10` is only an illustrative order; verify the order in the real application and avoid duplicate filter/listener registration if `web.xml` or auto-config already registers them.

Why use the `/*` mapping? CAS Java Client documentation typically lets the filter observe both login ticket requests and logoutRequest calls. Use a dedicated path only when your version/architecture guarantees the mapping is still recorded on login; otherwise there will be no ticket→session mapping.

### 10.1. Spring Security keeps CSRF for the user logout button

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class CasLocalLogoutSecurity {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .csrf(Customizer.withDefaults())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .anyRequest().authenticated())
            .logout(logout -> logout
                .logoutUrl("/logout")
                .logoutSuccessUrl("/logged-out"));

        // Register the CAS entry point, filter, and authentication provider
        // separately per Spring Security CAS integration.
        return http.build();
    }
}
```

`POST /logout` with a CSRF token is **user-initiated local logout**. A back-channel SLO POST from the CAS Server lacks a browser form CSRF token, so it needs a route/filter handling the protocol appropriately plus a **trusted caller origin**. If `SingleSignOutFilter` runs before the Spring Security chain and intercepts the notification, you may not need to add a manual CSRF exception. **Do not** call `http.csrf(csrf -> csrf.disable())` just to make the callback work.

### 10.2. CAS SLO XML is not a SAML2 SLO filter

A `<samlp:LogoutRequest>` element with a SAML2 namespace does not mean native CAS SLO is handled by Spring's `saml2Logout()`. Spring Security SAML2 SP has different protocol signing, issuer, SAMLResponse, and request repositories. When using `spring-security-cas`, use the **CAS Java Client SLO handler** matching your protocol/version and do not mix URLs.

### 10.3. Traditional web.xml configuration

The CAS Java Client README also describes Servlet filter/listener setup:

```xml
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
```

Do not configure both `web.xml` and a Spring Boot `FilterRegistrationBean` if that causes the filter to run twice. With Jakarta Servlet, deployment descriptors/schemas/packages must match the container version.

## 11. User-initiated global logout

### 11.1. Start with a CSRF-protected action

The application can offer two choices: "Log out of this application" and "Log out of SSO". Server-rendered form:

```html
<!-- Thymeleaf form; verify that the CSRF token is injected properly. -->
<form th:action="@{/logout}" method="post">
  <button type="submit">Log out of application</button>
</form>

<!-- /logout-sso is a custom app endpoint, not a Spring default. -->
<form th:action="@{/logout-sso}" method="post">
  <button type="submit">Log out of SSO</button>
</form>
```

The `/logout-sso` endpoint should check CSRF, destroy the local session via Spring Security handlers, and then redirect the browser to CAS `https://sso.example.org/cas/logout` using a fixed URL. Do not accept an arbitrary `?casLogoutUrl=...` for redirection, and do not use a GET controller to destroy sessions. Ensure CAS logout flow/cookies match your CAS Server version.

### 11.2. Why perform local logout before CAS logout?

CAS SLO is best effort. If the CAS Server fails to call back the app due to network issues, the initiating app must still end its own local session. Spring Security CAS documentation suggests performing local logout first, after which the user can choose CAS global logout.

### 11.3. Never promise "logout from all applications succeeded"

Once the CAS Server deletes the TGT/TGC, the app can report that the CAS session has ended. However, if Reports B lacks an SLO filter or the callback is failing, Reports still holds a valid local session. The UI and operational reports must distinguish:

- SSO session terminated at CAS.
- Notification attempted/delivered to service.
- Session actually invalidated by service.
- Protected resource is no longer authenticated with the old cookie.

## 12. Protecting the SLO endpoint against forced logout

### 12.1. XML notifications can be forged

Traditional CAS SLO back-channel messages may carry no XML digital signature. If a public endpoint accepts:

```http
POST /login/cas HTTP/1.1
Host: portal.example.org
Content-Type: application/x-www-form-urlencoded

logoutRequest=FAKE_SLO_XML
```

and the handler simply extracts `SessionIndex` and invalidates the session, an outsider who knows an ST ID can force a logout. **Do not treat HTTPS on the service callback as automatic proof that the caller is CAS**: the HTTPS/TLS server certificate authenticates the **service endpoint** to the caller, not the caller, unless mTLS or another caller authentication layer is in place.

### 12.2. Defense layers

- Restrict CAS back-channel via **mTLS**, internal network routing, a maintained IP/CIDR allowlist, or an identity-aware ingress/gateway.
- CAS Server URL and service callback path/method must be fixed and administratively managed; never read from query parameters.
- Enforce body size limits and a hardened XML parser: disallow DTD/XXE, entity expansion, and external resource access.
- If the deployment has genuine signature/message authentication, verify it against a **trust anchor outside the request**, never trusting an unverified certificate inside the request.
- Scope SLO session mappings by trusted CAS server, service, tenant, and ST ID in multi-tenant setups.
- Never invalidate sessions by raw `NameID` or request-supplied `sessionId`.
- Prevent duplicate/late notifications from logging out a new session.
- Rate-limit and log reason codes without logging raw tickets/NameID/logoutRequest XML.
- Test mTLS/ingress, route ordering, and actual session invalidation.

### 12.3. CSRF exceptions, if needed, must be narrow

A CAS Server-to-service POST has no browser `_csrf` form parameter. If the SLO servlet filter is registered before Spring Security's `CsrfFilter` and intercepts the notification, a CSRF exception may not even be necessary.

If there is a dedicated POST `/cas/slo` inside the Spring Security chain, consider an exception **only for that exact method/path** after establishing caller authentication. Spring Security 6.x illustrative fragment:

```java
// ONLY use when /cas/slo is a real CAS back-channel endpoint,
// already protected by mTLS/ingress trust and SLO validation.
http.csrf(csrf -> csrf.ignoringRequestMatchers(
    new org.springframework.security.web.util.matcher
        .AntPathRequestMatcher("/cas/slo", "POST")
));
```

`AntPathRequestMatcher` may be deprecated in newer releases; use the supported matcher accordingly. Never exempt `/logout/**` or disable CSRF app-wide. **A CSRF exception is not a substitute for caller authentication**.

### 12.4. Front-channel GET requires its own threat model

With front-channel CAS SLO, the browser may send a GET carrying `logoutRequest`. Never write a GET endpoint that invalidates a session solely on `?sessionId=...`. If the client lacks validation/compatibility support, use a protected back-channel or another revocation mechanism. A GET cannot be trusted just because it "came from the CAS page"—request headers/Referer can be missing and are not sufficient proof.

## 13. Multi-pod, Spring Session, and ticket-session mapping

### 13.1. A static map in the CAS client is insufficient for a cluster

Spring Security CAS docs show `SingleSignOutFilter` using a static session mapping. If Portal has 2 pods:

```text
CAS ticket ST-PORTAL-1 is processed on pod A
  -> pod A stores ST-PORTAL-1 -> HttpSession A

CAS logout POST goes through the load balancer to pod B
  -> pod B has no in-memory mapping
  -> cannot find HttpSession A

Subsequent browser request reaches pod A or the Spring Session store
  -> the local authenticated session may still be valid
```

Spring Session Redis may already share HttpSession data, yet the CAS client SLO mapping remains local. Two different kinds of state must be synchronized properly.

### 13.2. Distributed mapping model

```text
After validated CAS login:
  mappingKey = HMAC(trusted CAS server + service ID + ST ID)
  mappingValue = local session ID
  expiry = local session expiry upper-bound

On authenticated CAS SLO:
  parse SessionIndex = ST ID
  lookup mapping within correct CAS/service namespace
  check mapping current / not previously consumed
  invalidate server-side session in shared repository
  delete mapping atomically
  publish invalidation to other nodes if needed
```

A custom/distributed `SessionMappingStorage` or matching integration can fulfill this depending on the CAS Java Client version. Do not assign `SessionIndex` directly as the Redis HttpSession key: CAS sends the **ST ID**, not the session ID.

### 13.3. Races and session fixation

- When Spring Security rotates the session ID after login, the mapping must point to the new session holding `SecurityContext`.
- On local logout, remove the old ST mapping. A late SLO notification for an old ST must not invalidate a new session.
- If a request started before SLO, it may hold the Authentication in the request context until completion; sensitive operations may require a revocation check close to commit time.
- Duplicate SLO calls should be idempotent: once the mapping is deleted, do nothing more and touch no other session.
- If Redis/the session repository fails, do not report "logout succeeded" before invalidation has actually occurred per policy.

### 13.4. CAS Server cluster

A multi-node CAS Server needs a shared ticket registry and consistent service records: the node handling logout must know which services were issued tickets under the TGT. Asynchronous back-channel delivery and failover need health/timeout metrics. Do not assume CAS having sent a POST means every application is revoked.

## 14. Java 17: simulating multi-app CAS SLO and session isolation

The following demo runs on pure JDK 17, simulating the CAS Server holding TGT→tickets/services relationships while Portal and Reports hold ST→session mappings. It demonstrates that **local logout does not clear CAS SSO**, CAS global logout dispatches multiple notifications, an old ST already locally logged out does not affect a new session, a forged notification is rejected via a simulated trust flag, and another user's session is left untouched.

**Not production code:** No TLS, browser, CAS XML parsing, digital signatures, Java Servlet sessions, Spring SecurityContext, or HttpSession store. `trustedFromCas` is only a boolean to illustrate separating the trust boundary; production requires real caller authentication. Do not use fake ticket strings as credentials.

Save as `CasSloFlowDemo.java`:

```java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

public class CasSloFlowDemo {

    record Notification(Service service, String ticket) {}

    static final class Service {
        private final Map<String, String> sessionsByTicket = new HashMap<>();
        private final Set<String> liveSessions = new HashSet<>();

        void loginAfterValidation(String ticket, String sessionId) {
            sessionsByTicket.put(ticket, sessionId);
            liveSessions.add(sessionId);
        }

        boolean active(String sessionId) {
            return liveSessions.contains(sessionId);
        }

        void localLogout(String sessionId) {
            liveSessions.remove(sessionId);
            sessionsByTicket.entrySet()
                    .removeIf(e -> e.getValue().equals(sessionId));
        }

        boolean receiveSlo(String ticket, boolean trustedFromCas) {
            if (!trustedFromCas) {
                return false;
            }
            String sessionId = sessionsByTicket.remove(ticket);
            return sessionId != null && liveSessions.remove(sessionId);
        }
    }

    static final class CasServer {
        private final Set<String> activeTgts = new HashSet<>();
        private final Map<String, List<Notification>> ticketsByTgt =
                new HashMap<>();

        void login(String tgt) {
            activeTgts.add(tgt);
            ticketsByTgt.put(tgt, new ArrayList<>());
        }

        void recordIssued(String tgt, Service service, String ticket) {
            if (!activeTgts.contains(tgt)) {
                throw new IllegalStateException("Expired CAS session");
            }
            ticketsByTgt.get(tgt).add(new Notification(service, ticket));
        }

        boolean active(String tgt) {
            return activeTgts.contains(tgt);
        }

        List<Notification> endSso(String tgt) {
            if (!activeTgts.remove(tgt)) {
                return List.of();
            }
            return List.copyOf(ticketsByTgt.remove(tgt));
        }
    }

    public static void main(String[] args) {
        CasServer cas = new CasServer();
        Service portal = new Service();
        Service reports = new Service();
        String tgt = "TGT-DEMO";

        cas.login(tgt);
        portal.loginAfterValidation("ST-PORTAL-OLD", "session-P-old");
        cas.recordIssued(tgt, portal, "ST-PORTAL-OLD");
        reports.loginAfterValidation("ST-REPORTS", "session-R");
        cas.recordIssued(tgt, reports, "ST-REPORTS");

        // Another user has a separate session at Reports.
        reports.loginAfterValidation("ST-OTHER", "session-other");

        System.out.println("Initially portal: "
                + portal.active("session-P-old"));
        System.out.println("Initially reports: "
                + reports.active("session-R"));

        portal.localLogout("session-P-old");
        System.out.println("Local logout keeps reports: "
                + reports.active("session-R"));

        portal.loginAfterValidation("ST-PORTAL-NEW", "session-P-new");
        cas.recordIssued(tgt, portal, "ST-PORTAL-NEW");
        System.out.println("CAS SSO still active: " + cas.active(tgt));

        boolean forged = portal.receiveSlo("ST-PORTAL-NEW", false);
        System.out.println("Untrusted notification rejected: "
                + (!forged && portal.active("session-P-new")));

        List<Notification> notifications = cas.endSso(tgt);
        int invalidated = 0;
        for (Notification notification : notifications) {
            if (notification.service().receiveSlo(
                    notification.ticket(), true)) {
                invalidated++;
            }
        }

        System.out.println("CAS SSO terminated: " + !cas.active(tgt));
        System.out.println("SLO notices sent: " + notifications.size());
        System.out.println("Sessions invalidated: " + invalidated);
        System.out.println("Portal after SLO: "
                + portal.active("session-P-new"));
        System.out.println("Reports after SLO: "
                + reports.active("session-R"));
        System.out.println("Replay changes nothing: "
                + !portal.receiveSlo("ST-PORTAL-NEW", true));
        System.out.println("Unrelated reports session: "
                + reports.active("session-other"));
    }
}
```

Compile/run:

```bash
javac CasSloFlowDemo.java
java CasSloFlowDemo
```

**Exact** stdout:

```text
Initially portal: true
Initially reports: true
Local logout keeps reports: true
CAS SSO still active: true
Untrusted notification rejected: true
CAS SSO terminated: true
SLO notices sent: 3
Sessions invalidated: 2
Portal after SLO: false
Reports after SLO: false
Replay changes nothing: true
Unrelated reports session: true
```

### 14.1. Why send 3 notifications yet invalidate only 2 sessions?

CAS issued `ST-PORTAL-OLD`, `ST-REPORTS`, and `ST-PORTAL-NEW` under the same TGT. Portal already performed local logout on the session bound to `ST-PORTAL-OLD`, so the old notification found no mapping. Only the remaining two notifications invalidated the two active sessions.

This illustrates **idempotency** and why you must not delete by username: an old ST must not destroy a new session just because it belongs to the same user.

### 14.2. Detailed limitations

- `HashMap`/`HashSet` are not thread-safe/distributed; multiple CAS nodes/Portal pods need an appropriate ticket registry and session mapping.
- The ticket strings are predictable and `loginAfterValidation` mocks CAS validation results; production must validate STs against a real CAS Server.
- `trustedFromCas` is a demo parameter and does not prove an HTTP POST came from CAS; production uses mTLS/ingress identity or supported message authentication.
- No XML parser, logoutRequest structure validation, IssueInstant, replay detection, or network error handling.
- The demo dispatches synchronously; real CAS may send best effort/asynchronously.
- No actual Spring HttpSession invalidation or JWT revocation.

## 15. Failed/missing notifications and best effort

### 15.1. Partial logout is a possible outcome

```text
CAS:
  TGT destroyed and TGC cleared

Portal:
  notification delivered -> session invalidated

Reports:
  POST failed (503) -> session still authenticated

Workflow:
  HTTP 200 but ST mapping missing -> session status unknown
```

Per the CAS protocol, the server may ignore errors on SLO requests to preserve availability: **CAS logout does not roll back** if Reports fails. If stronger session revocation guarantees are required, add controls such as a central revocation indicator, shorter session TTL, session introspection on sensitive actions, or out-of-band logout event delivery per your architecture.

### 15.2. Do not confuse HTTP status with revocation outcome

- HTTP 200 only proves a handler/ingress returned a response, not that the session is gone.
- HTTP 302 may be a login redirect caused by filter order; the SLO request was never handled.
- HTTP 403 may come from CSRF, auth/proxy ACL, mTLS, or WAF.
- HTTP 404/405 usually means the wrong callback URL/method.
- HTTP 500/503 may come from session repository/network errors.
- CAS /logout returning a success page is not an acknowledgment from all services.

QA should resend a protected request with the **old cookie** and verify the service's session is no longer authenticated. Because the browser cannot see CAS→service back-channel calls in DevTools, inspect redacted server telemetry.

### 15.3. Late notifications and in-flight requests

When CAS logout occurs, an incoming request to Portal may have already read the authenticated context before the session is invalidated. The server cannot halt all threads solely for CAS SLO. Sensitive operations may need a revocation check right before commit, especially for high-value assets where a race window is unacceptable.

### 15.4. Retries/duplicates

CAS SLO is usually best effort; a custom gateway/queue may add retries. The client must be idempotent: after the first handling deletes the ST mapping, duplicate callbacks simply return an appropriate response without touching other sessions. Do not assume CAS automatically retries until every service succeeds.

## 16. Session lifecycle and common pitfalls

### 16.1. Session fixation protection

Spring Security may rotate the HttpSession ID after a successful login. The ticket→session mapping must point to the authenticated session **after rotation**. If the ST map stores an old session that no longer exists, SLO cannot invalidate the current session. Test the full flow: login, rotation, SLO, and browser cookie reuse.

### 16.2. Username is insufficient as a scope

User `alice` may log in across multiple browsers or tenants. A `NameID=alice` SLO notification does not authorize deleting all `alice` sessions across all tenants. Prefer ST mappings scoped to the trusted CAS authority/service/tenant; session deletion must affect only the matching session.

### 16.3. CAS SLO and API/JWT tokens

If the application issues JWT/access tokens in addition to HttpSession, CAS Java Client SLO may only invalidate the HttpSession. Already-issued tokens are not automatically revoked without a separate revocation mechanism. Evaluate TTL, token introspection, backend caches, and delegated credentials against security requirements.

### 16.4. CAS Proxy credentials

If the application holds a Proxy Granting Ticket (PGT) to call backends via CAS Proxy, local session logout/SLO may require revoking permission to use that PGT in the application vault. CAS TGT/logout also affects server-side PGTs per CAS policy. However, invalidating an HttpSession does not always clear external credential stores automatically; clean them up with the lifecycle and verify CAS `/proxy` rejection.

## 17. Security test matrix

| Scenario | Expected result |
| --- | --- |
| CAS user logout, both A/B use BACK_CHANNEL | A/B receive SLO and invalidate their respective sessions |
| Local logout A without CAS logout | B and CAS SSO remain active |
| CAS registered service `logoutType=NONE` | CAS sends no SLO to the service; local session may remain |
| CAS sends POST to wrong logoutUrl | 404/405 or failure; alert, do not claim complete |
| CAS sends valid SLO for ST A | Only the session mapped to ST A is invalidated |
| B receives an ST index belonging to A | B has no mapping; does not invalidate |
| User has 2 browser sessions with the same username | Only the session belonging to the logged-out TGT is destroyed |
| Invalid/malformed/oversized logoutRequest | Reject without unsafe parsing |
| XXE/DOCTYPE/entity expansion in XML | Reject/harden parser |
| Back-channel POST from untrusted caller | Reject at mTLS/ingress/handler policy |
| XML contains NameID but no ST mapping exists | Do not delete by NameID |
| Duplicate notification | Idempotent; does not destroy additional sessions |
| Old ST notification arrives after new ST login | New session is not erroneously destroyed |
| Session already hit idle timeout before CAS SLO | Mapping is cleaned up, no leak |
| CAS POST arrives at a different pod than login pod | Shared mapping/session invalidation or fail closed |
| Spring Session Redis active while SLO map is local | Test detects the mismatch |
| CAS callback HTTP 200 yet session stays authenticated | QA FAIL; fix handler/mapping |
| Reports backend is down | CAS logout may still finish; Reports partial SLO alert |
| Front-channel SLO on browser blocking iframes/third-party cookies | Do not report complete if app did not process |
| CAS XML has SAML2 namespace but message is unsigned | Do not infer signature verified |
| Browser POST /logout missing CSRF | Reject; do not log out |
| Exempting `/logout/**` or `csrf.disable()` | Security QA FAIL |
| JWT still works after CAS SLO | Acceptable only if token policy permits; evaluate revocation |
| Raw ticket/logoutRequest in nginx/APM logs | Security QA FAIL |
| CAS TGT expires by idle timeout | Verify version/policy SLO event behavior |
| Service mapping cleanup on HttpSession destroy | No stale entries/memory leak |
| In-flight request during SLO | Behavior follows revocation policy and authorization checks |

### 17.1. E2E runbook

1. Start a CAS test Server with registered services A/B supporting SLO.
2. Clean browser logs in to Portal; CAS issues ST A; service creates local HttpSession A.
3. Visit Reports; CAS uses the existing TGC to issue ST B; service creates local HttpSession B.
4. Confirm both protected routes are authenticated.
5. Perform user-triggered CAS logout via a CSRF-protected flow at the service.
6. Verify CAS Server deleted/expired the TGT and sent notifications (redacted logs).
7. Verify A/B received `logoutRequest`, mapped `SessionIndex`, and invalidated.
8. Resend old cookies to protected routes A/B; both must be treated as anonymous.
9. Run negative tests: wrong ST, duplicate, unknown mapping, untrusted caller, and malformed XML.
10. Run failure tests: service B down or SLO POST hitting another pod; CAS logout may still succeed while app B's local session remains; mark as partial.
11. Verify logs/proxy/APM do not store raw tickets/NameID/TGT/HttpSession IDs.
12. Test that other users/tenants are not logged out by this notification.

## 18. Troubleshooting

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| Portal stays logged in after CAS logout | SLO filter did not run, missing mapping, callback never arrived | Check service registry, filter order, ST→session map |
| CAS SLO POST returns 403 | CSRF/proxy ACL/mTLS/security chain | Find the blocking layer; keep caller auth, narrow exception only if needed |
| CAS POST returns 404 or 405 | Wrong `logoutUrl`/HTTP method/router | Check original service URL, dedicated logoutUrl, and ingress |
| CAS SLO has XML yet session not found | Session mapping is only on another pod or already cleared | Shared SessionMappingStorage and session repository |
| One pod handles it, another pod does not | Local static map, non-sticky load balancer | Distributed mapping and invalidation |
| User logs out locally and logs back in without password | CAS TGC/TGT remains | Distinguish local vs CAS logout |
| Reports session remains after CAS TGT deleted | Missed notification or app lacks SLO support | Alert on partial logout; add SLO handler/TTL |
| SLO fails only on newer browsers | FRONT_CHANNEL/third-party cookies/CSP/JS | Test client/browser support; consider BACK_CHANNEL |
| 200 from SLO callback yet session stays alive | Wrong handler ack, session repository not invalidated | Test protected route after callback |
| Old ST logout event deletes new session | Stale mapping after local logout/session rotation | Listener cleanup and proper session binding |
| CAS callback XML rejected by SAML2 filter | Confusing native CAS protocol with SAML 2.0 SLO | Use CAS Java Client SingleSignOutFilter |
| CAS Server sends no SLO on timeout | Version/idle-expiry policy configuration | Test actual CAS TGT expiration conditions |
| Access logs contain `ticket`/`logoutRequest` | Request/query/body tracing not redacted | Sanitize ingress, CAS HTTP client, APM, support tooling |

## 19. Monitoring and auditing without leaking tickets

A log pipeline can emit **event codes**:

```text
CAS:
  cas_tgt_terminated
  cas_slo_service_selected
  cas_slo_notification_attempted
  cas_slo_notification_result

APPLICATION:
  cas_slo_notification_received
  cas_slo_caller_verified
  cas_slo_ticket_mapping_found
  cas_slo_local_session_invalidated
  cas_slo_mapping_removed
  cas_slo_processing_error
```

Suggested metrics: `cas_slo_notifications_sent_total`, `cas_slo_callbacks_received_total`, `cas_slo_mapping_miss_total`, `cas_slo_sessions_invalidated_total`, `cas_slo_failures_total`, and `cas_slo_processing_latency_seconds`, labeled with allowlisted service identifiers. Never put raw ST, TGT, session cookies, NameID/email, or arbitrary URLs into labels/logs.

**Redact across layers:** CAS HTTP client, reverse proxy/Ingress, WAF, servlet access logs, distributed traces, APM, and error handlers. Avoid logging raw XML/`logoutRequest` or browser ticket query parameters. Use internal event IDs and approved service metadata when debugging.

## 20. Production checklist

- [ ] Distinguish local logout, CAS logout, and CAS SLO notifications.
- [ ] CAS Server/registered services enable the right `logoutType` and `logoutUrl`.
- [ ] BACK_CHANNEL POST can reach the right SLO endpoint over TLS.
- [ ] `SingleSignOutFilter`/`SingleSignOutHttpSessionListener` match the CAS client release and Servlet API.
- [ ] Filter order is correct relative to CAS authentication and Spring Security chain; no duplicate registrations.
- [ ] CAS client stores the ST→HttpSession mapping after validated login.
- [ ] Session destroy/local logout cleans up stale mappings.
- [ ] User POST local/global logout is CSRF-protected.
- [ ] CAS SLO back-channel authenticates the caller; XML parser prevents XXE/oversized payloads.
- [ ] Never treat the CAS XML SAML2 namespace as a verified signature.
- [ ] SessionIndex is understood as the Service Ticket ID, not the TGT or HttpSession ID.
- [ ] Never log out by raw NameID or browser query session ID.
- [ ] Duplicate/delayed events do not invalidate a different new session.
- [ ] Multi-pod sessions and SLO mappings are synchronized/invalidated properly.
- [ ] Best-effort CAS SLO is monitored with a partial-failure plan.
- [ ] Browser/front-channel is used only if CAS client supports it and SameSite/CSP are tested.
- [ ] UI never claims logged out everywhere solely because CAS /logout succeeded.
- [ ] SLO does not automatically revoke JWTs/PGTs or non-HttpSession credentials if the app manages them.
- [ ] QA resends the old cookie after SLO and verifies protected routes are unauthenticated.
- [ ] No ST/TGT/TGC/logoutRequest/NameID/cookies logged in ingress/APM.
- [ ] Negative tests exist for untrusted caller, XML, cross-tenant, session mismatch, replay, and service outage.

## 21. Review questions

**1. Why doesn't CAS Server logout directly delete Portal's HttpSession?**  
CAS manages its own TGT/TGC and does not own Portal's session store. CAS must send a notification; the Portal client locates and invalidates its local session.

**2. What value does CAS SLO SessionIndex carry?**  
In native CAS SLO, it is the **Service Ticket ID** previously sent to the CAS service, enabling mapping to the local session.

**3. Should you extract NameID=alice and delete all sessions for alice?**  
No. A single user can have multiple sessions/tenants; only the session matching the ST mapping should be destroyed.

**4. How do BACK_CHANNEL and FRONT_CHANNEL differ?**  
BACK_CHANNEL: CAS Server sends a direct POST. FRONT_CHANNEL: browser AJAX/JSONP/iframe depending on version and client support.

**5. Does CAS SLO XML using the SAML2 namespace mean the message is signed?**  
No. Caller authenticity must be verified via the deployment trust boundary and an actual/verified signature if present; never assume signed by default.

**6. Why is SingleSignOutHttpSessionListener needed?**  
To clean up the ST→HttpSession mapping when a local HttpSession is destroyed or expires.

**7. Does HTTP 200 from the CAS callback guarantee the session is gone?**  
No. You must check the session repository and protected resources after SLO.

**8. Does multi-node Spring Session Redis automatically share the CAS client SLO mapping?**  
Not necessarily. The session store and ST→session mapping may be separate; a distributed mapping must be designed explicitly.

**9. What if a logout notification for an old ST arrives after a new ST login?**  
It must not destroy the new session if it does not belong to the old mapping; ensure cleanup and idempotency.

**10. CAS logout deletes the TGT, yet Reports never receives the POST; what is the state?**  
CAS SSO has ended while the Reports local session may remain—that is best-effort partial SLO.

**11. Should CSRF be disabled app-wide to accept SLO POSTs?**  
No. User logout POST still requires CSRF; the CAS callback must verify caller identity and use dedicated matcher/filter configuration.

**12. What browser factors does FRONT_CHANNEL depend on?**  
JavaScript/iframes/CSP/third-party cookies/SameSite/network and CAS client support; it is not always reliable.

**13. If a service uses API JWTs, does CAS SLO automatically revoke those JWTs?**  
No. An independent token revocation/TTL policy is required.

**14. Can SAML2 LogoutRequestFilter handle native CAS SLO?**  
No. Although the XML uses a SAML namespace, the protocols and CAS client handlers differ.

## 22. Standards and references

- [Apereo CAS 8.0.x — Logout & Single Logout](https://apereo.github.io/cas/8.0.x/installation/Logout-Single-Signout.html): CAS/local/SLO scope, BACK_CHANNEL/FRONT_CHANNEL, SessionIndex=ST, logoutType/logoutUrl, and best-effort nature.
- [Apereo CAS 7.3.x — Logout & Single Logout](https://apereo.github.io/cas/7.3.x/installation/Logout-Single-Signout.html): cross-checking behavior for 7.x releases.
- [Apereo CAS — CAS Protocol Specification](https://apereo.github.io/cas/development/protocol/CAS-Protocol-Specification.html): CAS /logout and SLO POST semantics, client/server error handling.
- [Apereo CAS 8.x — Service Management](https://apereo.github.io/cas/8.0.x/services/Service-Management.html): registered service logoutType policy.
- [Spring Security — CAS Authentication and Single Logout](https://docs.spring.io/spring-security/reference/servlet/authentication/cas.html): SingleSignOutFilter/SingleSignOutHttpSessionListener integration, local vs CAS logout.
- [Apereo Java CAS Client README](https://github.com/apereo/java-cas-client/blob/master/README.md): Servlet filter/listener registration; check jakarta/javax compatibility.
- [Spring Security — CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): CSRF for user logout/state-changing requests.
- [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html): session lifecycle and session fixation.
- [OWASP XML External Entity Prevention](https://cheatsheetseries.owasp.org/cheatsheets/XML_External_Entity_Prevention_Cheat_Sheet.html): XML parser hardening.
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): session invalidation/cookies/logout.

**Remember:** CAS logout destroys the SSO TGT/TGC, yet **the CAS Server only sends notifications**—usually **BACK_CHANNEL POST `logoutRequest`** to services that received tickets. Each client must map `SessionIndex=Service Ticket ID` to **that service's own HttpSession**, invalidate the session, and clean up the mapping. Both BACK_CHANNEL and FRONT_CHANNEL can fail; **CAS SLO is best effort**, so you must verify that local sessions are actually destroyed, authenticate the callback source, never disable CSRF indiscriminately, and never treat the XML SAML2 namespace as proof of a signature.