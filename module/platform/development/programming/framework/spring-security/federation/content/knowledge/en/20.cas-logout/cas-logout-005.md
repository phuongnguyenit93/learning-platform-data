# Filter Ordering, Notification Endpoints, and Minimal CSRF Exemption Scope

> **Topic:** Spring Security – federation. **Knowledge group:** CAS Logout. This lesson focuses on **CAS Single Logout (SLO)** when the CAS Server sends a notification so a Spring Security application destroys an authenticated `HttpSession`, how to order `SingleSignOutFilter` before filters that might reject the notification, how to determine the receiving endpoint, and **exempting CSRF checks in the narrowest possible scope**. Examples target Java 17+, Spring Boot 3.x, Spring Security 6.x/Servlet, and a Jakarta Servlet–compatible Apereo Java CAS Client; verify APIs against your deployed BOM/version.

## 1. Learning objectives

After this lesson, you will be able to:

1. Distinguish **local logout** on an application, **CAS SSO logout** at the CAS Server, and **Single Logout notifications** to multiple services.
2. Explain why `SingleSignOutFilter` must observe **both login requests carrying a Service Ticket and logout requests sent by CAS**.
3. Know the distinct roles of `SingleSignOutFilter`, `SingleSignOutHttpSessionListener`, `CasAuthenticationFilter`, `CsrfFilter`, `LogoutFilter`, and `AuthorizationFilter`.
4. Determine where CAS sends SLO: the **original service URL** or a dedicated `logoutUrl` defined in the CAS registered-service entry.
5. Configure a dedicated endpoint such as `POST /cas/slo` when the CAS Server supports `logoutUrl` and know when to use the default `/login/cas` callback.
6. Apply one of two consistent strategies: **SLO filter at the Servlet layer before Spring Security** or **SLO filter inside `SecurityFilterChain` before `CsrfFilter`**; never register it twice.
7. Understand why `permitAll()` **does not** replace `csrf.ignoringRequestMatchers(...)` if a POST request still traverses `CsrfFilter`.
8. Avoid disabling CSRF app-wide; **browser `POST /logout` must still require a CSRF token**.
9. Verify `Service Ticket → HttpSession` mapping, cleanup, session fixation, cluster behavior, and notifications landing on a different node.
10. Test success/failure cases: back-channel SLO with/without a CSRF token, forged requests, missing sessions, spent tokens, wrong path/method requests, front-channel, ingress/HTTPS, and concurrency.

**Core principle:** A CAS SLO notification is a **protocol message from the SSO system**, not a POST form submitted by a browser user. Because the CAS Server typically **lacks the application session's CSRF token**, do not require it to submit one like a user. Instead, restrict any exemption strictly by **path, HTTP method, and allowed origin**, while keeping regular `POST /logout` CSRF-protected.

## 2. Three logout operations — not the same endpoint

| Action | Who initiates? | Endpoint | Direct outcome | CSRF? |
| --- | --- | --- | --- | --- |
| **Local application logout** | User's browser | `POST https://app.example.org/logout` | Clears `HttpSession`/`SecurityContext` in application A | **Yes**, per Spring Security when using session cookies |
| **CAS SSO logout** | Browser visits CAS Server | `https://sso.example.org/cas/logout` | Deletes/revokes CAS SSO session (TGT/TGC) per policy | Protected by CAS Server according to its own design |
| **CAS Single Logout notification** | CAS Server sends to service | Typically `POST https://app.example.org/login/cas` or dedicated `/cas/slo` | CAS client finds and invalidates session A bound to the Service Ticket | Cannot require browser A's CSRF token; needs separate origin/protocol protection |
| **SLO front-channel (if supported)** | CAS Server via browser | May be GET/JSONP to service URL per CAS config | Instructs service to handle logout via browser; depends on cookies/browser | GET does not require CSRF by default; must evaluate support/integrity |
| **CAS login callback** | Browser after CAS login | `GET /login/cas?ticket=ST-...` | `CasAuthenticationFilter` validates ST, creates local Authentication | GET, yet has CAS service binding and ticket validation |
| **CAS service ticket validation** | Application backend | `GET /cas/serviceValidate` on CAS Server | Verifies ST matches `service`, is valid/single-use | Not an App A CSRF endpoint |

**Common pitfall:** CAS Server `/cas/logout` is not Spring Security `/logout`, and an SLO notification **is not a user logout request from a web page**. CAS can end the SSO session and then send a cookie-less POST to the application; the application must handle it using the **ticket–session mapping** recorded during the earlier login.

## 3. Login flow and why requests carrying Service Tickets must be captured

To log out a session later, the CAS client must remember **which `HttpSession` was created for which Service Ticket**.

```text
Browser                  Spring Application                CAS Server
  |                             |                              |
  | GET /private                |                              |
  |---------------------------->|                              |
  |<-- 302 CAS /login?service=...                              |
  |------------------------------------------------------------>|
  |<------- 302 /login/cas?ticket=ST-abc ----------------------|
  |                             |                              |
  | GET /login/cas?ticket=ST-abc|                              |
  |---------------------------->|                              |
  |                    [SingleSignOutFilter]
  |                    record ST-abc -> HttpSession A
  |                             |
  |                    [CasAuthenticationFilter]
  |                    validate ST with CAS Server             |
  |                             |----------------------------->|
  |                             |<-----------------------------|
  |                    [SecurityContext + HttpSession A]
  |<---- 302 /private ----------|
  | GET /private, cookie A      |
  |---------------------------->|
  |<--- data if authorized -----|
```

When the CAS SSO session is destroyed:

```text
CAS Server                   Spring Application
    |                                |
    | POST /cas/slo                  |
    | Content-Type: application/x-www-form-urlencoded
    | logoutRequest=<SAML LogoutRequest>
    |------------------------------->|
    |                    [SingleSignOutFilter]
    |                      parse/logoutRequest
    |                      extract SessionIndex/ST-abc
    |                      look up mapping -> HttpSession A
    |                      session.invalidate()
    |<-------------------------------|
    |                    HttpSession A is no longer valid
```

**Core requirement:** If you run the SLO filter only on `/cas/slo` and **do not let it observe `GET /login/cas?ticket=...`**, the default filter may **have no mapping** to know which ST is linked to the `HttpSession`. That is why Apereo Java CAS Client documents `SingleSignOutFilter` mapped to `/*` at the Servlet level; a dedicated logout endpoint only **restricts where logout messages are handled**, not necessarily everywhere the filter runs.

### 3.1. What is the SessionIndex used in SLO?

The CAS Server typically sends the **CAS Service Ticket ID** from the user's login as a session identifier inside the SAML-style `LogoutRequest`. The Apereo CAS Client uses that value to locate the recorded session:

```text
login ticket ST-abc --> client mapping --> HttpSession A
LogoutRequest/SessionIndex = ST-abc
                                      |
                                      v
                              invalidate HttpSession A
```

Do not treat this `SessionIndex` as a browser `JSESSIONID` or an arbitrary ID usable for deleting sessions. Do not extract `NameID` from `LogoutRequest` to search and delete **all sessions** sharing the same username unless the system/tenant has an explicit global revocation policy. Mapping strictly by ticket prevents destroying the wrong session.

### 3.2. What does `SingleSignOutHttpSessionListener` do?

Apereo Java CAS Client provides `SingleSignOutHttpSessionListener` to clean up `SessionMappingStorage` when an `HttpSession` is destroyed by logout, timeout, or application invalidation. Without the listener, mappings can retain dead session references, increasing memory leaks/inconsistency or complicating SLO diagnostics.

The listener **does not replace the SLO filter**: it only reacts to `HttpSession` lifecycle events and does not receive `POST logoutRequest` from CAS. Both components are required in a servlet-style CAS client configuration.

## 4. Back-channel and front-channel SLO must be distinguished

### 4.1. Back-channel: CAS Server calls the service directly

Per Apereo CAS, `LogoutType.BACK_CHANNEL` is commonly the default for a CAS registered-service. CAS performs a **direct HTTP POST** to the service; the request carries `logoutRequest`, containing a **SAML `LogoutRequest`** with `SessionIndex` for correlation. The connection does not depend on the browser sending application cookies.

Pros: less constrained by third-party cookies/iframes and can work even after the user closes the application tab. Cons: the CAS Server must reach the service callback over the network, TLS, and ingress; the application must persist accurate ticket–session mappings across nodes and be able to invalidate sessions.

### 4.2. Front-channel: CAS orchestrates via the browser

Some CAS configurations use the browser to send `GET`/JSONP logout requests to services. This is affected by JavaScript, frame/browser privacy rules, and individual CAS client support. **Do not assume every Spring Security CAS client recognizes SLO GET requests**; test the exact Apereo Java CAS Client, CAS Server, and browsers in use.

If back-channel POST is selected, **do not open CSRF exemptions for all GETs**—GET already does not require CSRF in Spring by default, and especially never configure `GET /logout` to perform unconfirmed local logout.

### 4.3. One CAS server can speak SAML protocol separately from CAS protocol

Apereo CAS can act as an OIDC/SAML2 IdP, yet `SingleSignOutFilter` discussed here belongs to the **Apereo Java CAS Client for the CAS protocol** and does not replace `saml2Logout` or OIDC Back-Channel Logout. SAML2 logout uses its own request signatures, issuer, destination, and profile validation; OIDC logout has its own Logout Token JWT standard. Never merge filters, callbacks, and CSRF exemptions across these three protocols merely because all endpoints contain the word "logout".

## 5. Which URL does CAS send notifications to?

Apereo CAS has two mechanisms to distinguish.

### 5.1. Default: the service URL used when issuing the ticket

If App A's service is configured as:

```text
ServiceProperties.service =
  https://app.example.org/login/cas
```

and the CAS registered-service **sets no dedicated `logoutUrl`**, SLO notifications are normally sent to **the service URL recorded by CAS during authentication**, for example:

```http
POST /login/cas HTTP/1.1
Host: app.example.org
Content-Type: application/x-www-form-urlencoded

logoutRequest=<URL-encoded XML>
```

The same `/login/cas` path can handle **two request types**: a browser `GET` with `ticket` is validated by the CAS authentication filter; a CAS Server `POST` with `logoutRequest` is handled by the SLO filter. **Filter ordering is critical**: the SLO POST must be intercepted before `CsrfFilter` blocks it or `CasAuthenticationFilter` misinterprets it.

### 5.2. Recommended for new deployments: a dedicated registered `logoutUrl`

Apereo CAS allows a service to specify a `logoutUrl` distinct from the original service URL. Illustrative policy example in the CAS service registry:

```json
{
  "@class": "org.apereo.cas.services.CasRegisteredService",
  "serviceId": "^https://app\\.example\\.org/login/cas$",
  "name": "reports-app",
  "id": 1200,
  "logoutType": "BACK_CHANNEL",
  "logoutUrl": "https://app.example.org/cas/slo"
}
```

This is an **illustrative Apereo CAS registered-service configuration**, not a file you can paste into every CAS release without checking schema/serializer compatibility. Verify the `logoutType`, `logoutUrl`, and class name against your **running CAS Server**, and make sure the service ID regex/route is approved.

This configuration cleanly separates:

```text
CAS login/ST callback:
  GET  https://app.example.org/login/cas?ticket=ST-abc

CAS SLO notification:
  POST https://app.example.org/cas/slo
  body: logoutRequest=<encoded SAML LogoutRequest>

Browser local logout:
  POST https://app.example.org/logout
  body: _csrf=<browser-session-csrf-token>
```

A dedicated endpoint makes it easy to apply ingress/mTLS/rate-limit policies and narrow any CSRF exception **solely to `POST /cas/slo`** without affecting browser logout. However, because the SLO filter must record the ticket–session mapping at login, **the filter itself must still run broadly enough to cover login requests**.

**If the CAS Server does not support or has not configured `logoutUrl`:** Do not invent `/cas/slo` and wait for CAS to send there automatically. Use the actual default endpoint (typically `/login/cas`) and narrow any **POST exception on that path** if needed. Always confirm the URL by inspecting the CAS registered-service, access logs, and SLO tests rather than guessing.

### 5.3. Choosing a secure and stable path

- Pin the **public canonical HTTPS URL**; do not use an internal `http://app:8080` URL if the CAS Server cannot reach it.
- Do not use browser `/logout` as the CAS callback when a dedicated endpoint can be configured.
- Do not use wildcard `/logout/**` across all protocols and tenants.
- If the app has `context-path=/portal`, the public callback may be `https://app.example.org/portal/cas/slo`, while the servlet path matcher inside the context is typically `/cas/slo`. Verify in practice.
- The CAS Server calls the endpoint from the **CAS network** without browser session cookies; bypass any login-forcing authentication gateway on that exact callback.
- Reverse proxies must preserve `POST`, the `application/x-www-form-urlencoded` body, `logoutRequest`, and encoding without rewriting paths or methods.
- If each tenant uses a separate CAS Server or registered-service, callback routing, trust stores, and session mappings must partition by tenant so tenant A's SLO never destroys tenant B's session.

## 6. Filter ordering: two layers to view separately

A Servlet application has **two filter chain layers**:

```text
Servlet Container Filter Chain
    |
    +--> CharacterEncodingFilter (depends on topology, yet should be early)
    |
    +--> Apereo SingleSignOutFilter        <--- option 1: before Spring
    |
    +--> DelegatingFilterProxy("springSecurityFilterChain")
             |
             +--> FilterChainProxy
                    |
                    +--> SecurityContextHolderFilter
                    +--> HeaderWriterFilter
                    +--> CsrfFilter
                    +--> LogoutFilter
                    +--> CasAuthenticationFilter
                    +--> ...
                    +--> AuthorizationFilter
    |
    +--> DispatcherServlet / MVC Controller
```

Each `FilterChainProxy` has an order established by Spring Security. When adding custom filters, **do not look at `@Bean` declaration order in code** and assume that is the HTTP request execution order. Verify the **actual order** in logs or integration tests.

### 6.1. Option A: place the Apereo SLO filter before the entire Spring Security chain

This is the clearest option for **Servlet Filter–style Apereo Java CAS Client SLO**:

1. `CharacterEncodingFilter` with UTF-8 runs early to avoid mis-decoding XML/form bodies when needed.
2. `SingleSignOutFilter` is registered **once** in the Servlet chain with URL pattern `/*` so it observes requests carrying `ticket` as well as `logoutRequest`.
3. `DelegatingFilterProxy`/Spring Security chain runs afterwards for normal requests; valid SLO callbacks are handled by the Apereo filter before reaching `CsrfFilter`.
4. `CasAuthenticationFilter` sits inside the Spring Security chain to validate STs and create authenticated sessions.
5. `SingleSignOutHttpSessionListener` cleans up mappings when an `HttpSession` is destroyed.

**CSRF consequence:** If `SingleSignOutFilter` completely handles the CAS POST **before** Spring Security's `CsrfFilter`, **you do not need to disable CSRF or add `csrf.ignoringRequestMatchers`** for the notification to be accepted. Other POST requests continue through Spring Security and require a CSRF token as usual.

**Precondition:** You must **measure and verify the actual Servlet Filter order**; if Boot registers the SLO filter **after** Spring Security, a CSRF-less `POST logoutRequest` may be rejected with `403` by `CsrfFilter` before the SLO filter ever sees it. If an ingress/WAF layer blocks it upstream, Spring ordering cannot save it either.

### 6.2. Option B: add the SLO filter inside `SecurityFilterChain`

You can add `SingleSignOutFilter` via `http.addFilterBefore(singleSignOutFilter, CsrfFilter.class)` so CAS logout POSTs are handled before `CsrfFilter` and `CasAuthenticationFilter`. If added with `before="CAS_FILTER"` per older XML examples, still **verify whether it precedes `CsrfFilter`**, since `CsrfFilter` normally appears before authentication filters.

Structural example—**do not run alongside the Servlet registration in Option A**:

```java
// Alternative option: only when SingleSignOutFilter is supported
// by your Spring CAS/Jakarta version and is NOT already registered
// as a Servlet Filter.
SingleSignOutFilter slo = new SingleSignOutFilter();

http.addFilterBefore(slo, CsrfFilter.class);
// Still requires SessionMapping listener, encoding,
// proper logout callback path, and CAS auth filter.
```

**Never simultaneously** register one `SingleSignOutFilter` in the Servlet container and another instance inside the Spring chain. Running twice can read the body/ticket twice, record duplicate mappings, or cause erratic invalidation that is hard to diagnose.

### 6.3. `LogoutFilter` is not `SingleSignOutFilter`

- **Spring `LogoutFilter`:** handles **local logout** at `POST /logout` with `LogoutHandler`s, including invalidating `HttpSession`, clearing `SecurityContext`, and CSRF cleanup.
- **Apereo `SingleSignOutFilter`:** receives **CAS protocol SLO notifications**, looks up ticket→HttpSession, and invalidates that session.
- **Spring `CasAuthenticationFilter`:** receives the CAS Service Ticket after login, calls the CAS Server to validate it, and creates Authentication.
- **`CsrfFilter`:** prevents cross-site request forgery on unsafe HTTP methods passing through it, unless exempted by a rule.
- **`AuthorizationFilter`:** enforces authorization after authentication; `permitAll` does not let a request bypass `CsrfFilter` if it was already rejected earlier.

Never turn a CAS `POST logoutRequest` into a browser `POST /logout` to "reuse" `LogoutFilter`; that loses ticket–session correlation and risks logging out the wrong session.

## 7. CSRF: when must it be exempted and what exactly should be exempted?

### 7.1. Why doesn't CAS have the application's CSRF token?

`CsrfFilter` uses a CSRF token bound to a browser session/cookie when handling browser-submitted POSTs. Back-channel CAS SLO comes from a **CAS HTTP client** on another server, which normally knows neither `JSESSIONID` nor the user's App A CSRF token. Forcing CAS to submit session A's `_csrf` is impossible.

Thus only two clean approaches exist:

- **SLO filter handles the call before `CsrfFilter`**: no separate CSRF ignore rule is needed in Spring Security.
- **SLO POST must traverse `CsrfFilter`** due to architecture: exempt only the exact **method + endpoint** receiving CAS, and enforce dedicated origin/protocol checks.

**Never do this:** `http.csrf(csrf -> csrf.disable())` across the whole web app just for CAS SLO. That exposes browser `/logout`, profile edits, money transfers, role changes, and all other POSTs to CSRF.

### 7.2. Exemption scope by method and exact path

If the CAS registered-service uses `logoutUrl=https://app.example.org/cas/slo`, the narrow matcher should look like:

```text
POST /cas/slo        --> no browser CSRF token required,
                         yet ONLY the SLO protocol handler processes it
POST /logout         --> MUST have CSRF token
POST /api/orders     --> MUST have CSRF token if API uses cookie session
POST /cas/slo-extra  --> MUST have CSRF token
PUT  /cas/slo        --> MUST have CSRF token
GET  /cas/slo        --> no CSRF required by default,
                         yet MUST NOT be processed as an SLO POST
```

If using the default `POST /login/cas` callback, exempt `POST /login/cas` only after confirming the CAS Server actually sends SLO there. **`GET /login/cas?ticket=ST` is the CAS login callback**, requiring no CSRF exception because GET is not an unsafe method by default.

### 7.3. Spring Security 6.x: ignore snippet **only when needed**

In an app with `HttpSecurity http`, if a valid SLO handler must pass **through `CsrfFilter` before being handled**, use a `RequestMatcher` constrained by method and path:

```java
import org.springframework.security.web.util.matcher.RequestMatcher;

// Local path inside servlet context, without query string.
// Use ONLY when CAS actually sends back-channel SLO to /cas/slo.
RequestMatcher casSloPost = request ->
    "POST".equals(request.getMethod())
        && "/cas/slo".equals(request.getServletPath());

http.csrf(csrf -> csrf.ignoringRequestMatchers(casSloPost));
```

If using an Ant matcher in Spring Security 6.x, the equivalent pattern is:

```java
import org.springframework.security.web.util.matcher.AntPathRequestMatcher;

http.csrf(csrf -> csrf.ignoringRequestMatchers(
    new AntPathRequestMatcher("/cas/slo", "POST")));
```

These two snippets are **alternatives—pick one**, not both. Spring Security 7.x migrates toward `PathPatternRequestMatcher`; check your version/Javadoc instead of copying deprecated classes that fail to compile. If the Servlet mapping is not `/` or a context path exists, verify `request.getServletPath()` and the effective matcher via integration tests.

**Note:** The main example in section 8 registers the SLO filter **before Spring Security**, so `csrf.ignoringRequestMatchers(...)` is **not needed** in that `SecurityFilterChain`. Do not add both just "in case": an unused exemption leaves an unprotected surface if the filter fails to run.

### 7.4. `permitAll` is not a CSRF exemption

These two lines:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/cas/slo").permitAll())
.csrf(csrf -> csrf.ignoringRequestMatchers(casSloPost))
```

solve two **different** problems:

1. `permitAll`: once a request reaches `AuthorizationFilter`, no browser Authentication is required on that endpoint.
2. `ignoringRequestMatchers`: when a request passes through `CsrfFilter`, **no browser CSRF token is required** for that matcher.

If a CAS request is blocked by `CsrfFilter` earlier in the chain, `permitAll` **does not help**. Conversely, if it bypasses `CsrfFilter` yet hits an `authenticated()` authorization rule, fix the policy/handler per architecture.

**This does not mean "anonymous callers are allowed to destroy sessions".** An SLO endpoint must enforce proper protocol semantics and verify origin/correlation rather than returning 200 to arbitrary POSTs.

### 7.5. A CSRF exemption is not proof of authenticity

Exempting `POST /cas/slo` from a CSRF token **does not make the message trustworthy**. The callback requires defense-in-depth:

- Only the approved CAS Server/ingress may send per policy, using mTLS/network policies/allowed source CIDRs where appropriate.
- Accept only the expected `Content-Type`, method, request size, encoding, and `logoutRequest` parameter; never parse XML with a hand-rolled XXE-unsafe parser.
- Use an up-to-date Apereo Java CAS Client adhering to the contract. **Do not assume every `logoutRequest` variant carries a verified signature**; check what protocol-level message authentication your server/client actually enforces.
- Never take an unverified `SessionIndex` from XML to arbitrarily invalidate all user sessions.
- Bind the ticket recorded at CAS login to the local `HttpSession`, tenant/registration, and appropriate CAS source.
- Rate-limit and audit anomalous requests to mitigate logout denial-of-service (expanded logout CSRF).
- Block browser-originated forged requests to the SLO endpoint at the network boundary when possible; if the SLO endpoint must be public, enforce appropriate origin authentication and omit sensitive info from responses.
- Always keep CSRF enabled for user `POST /logout` and all cookie-session business actions.

**Never treat missing `Origin`/`Referer` as proof the call came from the CAS Server**: server-side HTTP clients may omit them, and non-browser attackers can forge headers.

## 8. Spring Boot 3.x example: SLO Servlet filter before Spring Security

This example chooses **Option A**: Apereo `SingleSignOutFilter` is a **Servlet filter** placed before `springSecurityFilterChain`; `CasAuthenticationFilter` is a **Spring Security filter**. This architecture is easy to inspect and keeps CSRF intact for normal requests.

### 8.1. Dependencies and build prerequisites

In a Spring Boot 3.x project managing dependencies via BOM on Java 17+, add:

```xml
<dependencies>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-cas</artifactId>
  </dependency>
</dependencies>
```

This is a `pom.xml` fragment, not a standalone POM. `spring-security-cas` relies on Apereo Java CAS Client; since Spring Boot 3.x uses **`jakarta.servlet`**, choose an artifact/client version with a compatible Jakarta Servlet API. Verify:

```bash
./mvnw dependency:tree
./mvnw test
```

Do not mix an old `SingleSignOutFilter` compiled for `javax.servlet.Filter` with Spring Boot 3 Jakarta and force casts; if versions mismatch, align CAS Client/Spring BOM per compatibility guidance. Never place multiple versions of `java-cas-client` on the classpath.

### 8.2. URL configuration in `application.yml`

```yaml
server:
  port: 8080
  forward-headers-strategy: framework
  servlet:
    session:
      timeout: 30m
      cookie:
        secure: true
        http-only: true
        same-site: lax

app:
  cas:
    server-base-url: https://sso.example.org/cas
    login-url: https://sso.example.org/cas/login
    service-url: https://app.example.org/login/cas
    slo-path: /cas/slo
```

**Assumption:** The app is exposed publicly behind an HTTPS 443 reverse proxy, backend HTTP port 8080, and the CAS Server has registered `service-url` for login and `logoutUrl=https://app.example.org/cas/slo` for back-channel SLO. The `example.org` domains are illustrative, not a live running CAS environment.

`forward-headers-strategy` is safe only if the proxy **strips/overwrites** client-supplied forwarded headers before forwarding to Spring. Even so, it is safest to place `service-url` and `logoutUrl` in fixed trusted configuration rather than deriving them from raw `Host`/`X-Forwarded-Host`.

### 8.3. Registering the SLO filter and session listener at the Servlet layer

File `src/main/java/com/example/caslogout/CasSloServletConfig.java`:

```java
package com.example.caslogout;

import org.apereo.cas.client.session.SingleSignOutFilter;
import org.apereo.cas.client.session.SingleSignOutHttpSessionListener;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.boot.web.servlet.ServletListenerRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;

@Configuration
public class CasSloServletConfig {

    @Bean
    FilterRegistrationBean<SingleSignOutFilter>
            casSingleSignOutFilterRegistration() {

        SingleSignOutFilter filter = new SingleSignOutFilter();

        FilterRegistrationBean<SingleSignOutFilter> reg =
            new FilterRegistrationBean<>(filter);

        reg.setName("casSingleSignOutFilter");
        // Cover ticket-bearing login requests + CAS SLO callbacks.
        reg.addUrlPatterns("/*");

        // Pin the endpoint receiving logoutRequest.
        // Ensure CAS Server registered-service sends to /cas/slo.
        reg.addInitParameter("logoutCallbackPath", "/cas/slo");

        // Servlet filter must actually run before
        // springSecurityFilterChain / DelegatingFilterProxy.
        reg.setOrder(Ordered.HIGHEST_PRECEDENCE + 20);
        return reg;
    }

    @Bean
    ServletListenerRegistrationBean<SingleSignOutHttpSessionListener>
            casSingleSignOutSessionListener() {
        return new ServletListenerRegistrationBean<>(
            new SingleSignOutHttpSessionListener());
    }
}
```

**Explanation:**

- `FilterRegistrationBean` creates a single filter instance. **Do not** also declare `@Bean SingleSignOutFilter` and call `http.addFilterBefore`; avoid duplicate registration.
- `addUrlPatterns("/*")` lets the filter observe **GETs carrying `ticket`** when the browser returns from CAS as well as **POSTs carrying `logoutRequest`** from CAS. Restricting URL patterns to `/cas/slo` alone drops the ticket–session mapping if the default client relies on filter tracking during the login callback.
- `logoutCallbackPath=/cas/slo` tells the CAS client to recognize logout requests on the defined endpoint. Verify matcher behavior on your actual Apereo Client version, especially with a servlet context path.
- `Ordered.HIGHEST_PRECEDENCE + 20` is a **very early** priority, usually ahead of Boot's `springSecurityFilterChain`; do not assume this guarantees order in every custom bootstrap. **Inspect the actual filter registration/order and test SLO POSTs.**
- `SingleSignOutHttpSessionListener` cleans up mappings when an `HttpSession` expires; it neither validates tickets itself nor receives SLO requests if the filter is missing.
- `CharacterEncodingFilter` should run early/be configured by Boot for UTF-8; verify encoding on SLO XML form POSTs without registering a duplicate encoding filter if Boot already provides one.
- The SLO endpoint needs no MVC controller. `SingleSignOutFilter` handles the request; a controller merely returning `200` **does not** prove the session was invalidated.
- A CAS callback is typically a server-side POST without browser cookies; the early filter must have access to the in-process/cluster session mapping.

**Version note:** Class names and init parameters above belong to Apereo Java CAS Client; different releases may alter Servlet API types, callback handling, or parsers. These examples are source code for a Spring Boot project with dependencies and a test CAS server; they do not compile with plain `javac`.

### 8.4. CAS login filter and Spring Security logout coexisting

File `src/main/java/com/example/caslogout/CasWebSecurityConfig.java`:

```java
package com.example.caslogout;

import org.apereo.cas.client.validation.Cas20ServiceTicketValidator;
import org.apereo.cas.client.validation.TicketValidator;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.cas.ServiceProperties;
import org.springframework.security.cas.authentication.CasAuthenticationProvider;
import org.springframework.security.cas.web.CasAuthenticationEntryPoint;
import org.springframework.security.cas.web.CasAuthenticationFilter;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;

@Configuration
public class CasWebSecurityConfig {

    @Bean
    ServiceProperties serviceProperties(
        @Value("${app.cas.service-url}") String service) {
        ServiceProperties props = new ServiceProperties();
        props.setService(service);
        props.setSendRenew(false);
        return props;
    }

    @Bean
    TicketValidator ticketValidator(
        @Value("${app.cas.server-base-url}") String casBase) {
        return new Cas20ServiceTicketValidator(casBase);
    }

    @Bean
    UserDetailsService userDetailsService() {
        // CAS lab fixture user only.
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password("{noop}unused-by-cas")
                .roles("USER")
                .build());
    }

    @Bean
    CasAuthenticationProvider casAuthenticationProvider(
        ServiceProperties props,
        TicketValidator validator,
        UserDetailsService users) {

        CasAuthenticationProvider provider =
            new CasAuthenticationProvider();
        provider.setServiceProperties(props);
        provider.setTicketValidator(validator);
        provider.setUserDetailsService(users);
        provider.setKey("cas-slo-example-v1");
        return provider;
    }

    @Bean
    SecurityContextRepository securityContextRepository() {
        return new HttpSessionSecurityContextRepository();
    }

    @Bean
    SecurityFilterChain casWeb(
        HttpSecurity http,
        ServiceProperties props,
        CasAuthenticationProvider provider,
        SecurityContextRepository contextRepository,
        @Value("${app.cas.login-url}") String casLoginUrl)
            throws Exception {

        CasAuthenticationEntryPoint entryPoint =
            new CasAuthenticationEntryPoint();
        entryPoint.setLoginUrl(casLoginUrl);
        entryPoint.setServiceProperties(props);

        CasAuthenticationFilter casFilter =
            new CasAuthenticationFilter();
        casFilter.setServiceProperties(props);
        casFilter.setFilterProcessesUrl("/login/cas");
        casFilter.setAuthenticationManager(
            new ProviderManager(provider));
        casFilter.setSecurityContextRepository(contextRepository);

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error",
                    "/signed-out").permitAll()
                .requestMatchers("/reports/**").hasRole("USER")
                .anyRequest().authenticated())

            // Keep default CSRF for POST /logout and web forms.
            // SLO POST is already handled by Servlet SingleSignOutFilter
            // before reaching the Spring Security chain.
            .csrf(Customizer.withDefaults())

            .exceptionHandling(ex -> ex
                .authenticationEntryPoint(entryPoint))
            .securityContext(context -> context
                .securityContextRepository(contextRepository))
            .logout(logout -> logout
                .logoutUrl("/logout")
                .logoutSuccessUrl("/signed-out")
                .invalidateHttpSession(true)
                .clearAuthentication(true));

        // Register CAS auth filter only inside SecurityFilterChain.
        http.addFilterAt(casFilter, CasAuthenticationFilter.class);
        return http.build();
    }
}
```

**What this configuration guarantees and does not guarantee:**

- `CasAuthenticationFilter` processes the browser's Service Ticket at `GET /login/cas?ticket=...`, using the provider to validate the ticket via CAS Server.
- Apereo's `SingleSignOutFilter` at the Servlet layer sees the ticket-bearing request first so it can record the mapping to the session; when CAS sends SLO, it looks up and invalidates the session.
- Spring `LogoutFilter` preserves CSRF-protected local logout by default; `POST /logout` must carry a valid CSRF token when the user logs out from a browser.
- `HttpSessionSecurityContextRepository` stores local Authentication per session; invalidating the session ensures subsequent requests are no longer authenticated.
- There is no `csrf.disable()` and **no CSRF ignore rule**, because the SLO filter already runs before `CsrfFilter`.
- There is no `@GetMapping("/cas/slo")` or `@PostMapping("/cas/slo")`; if the SLO filter fails to handle it, seeing 401/404/403 is a bug to fix, not a reason to add a dummy "200 OK" controller.
- `alice` with `{noop}unused-by-cas` is solely a fixture for local role demo; actual password authentication happens on the CAS Server. Production uses real user repositories and tenant authorization.
- This configuration **does not automatically redirect the browser to CAS `/logout`** after local logout. Global logout requires a separate UX/policy decision (section 11).
- If the app already has another `SecurityFilterChain`, integrate rather than creating two chains both matching all requests; ensure ticket callbacks and business URLs belong to the right chain.

### 8.5. Spring Boot application and illustrative endpoints

File `src/main/java/com/example/caslogout/CasSloDemoApplication.java`:

```java
package com.example.caslogout;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CasSloDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(CasSloDemoApplication.class, args);
    }
}
```

File `src/main/java/com/example/caslogout/DemoController.java`:

```java
package com.example.caslogout;

import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/")
    public Map<String, String> home() {
        return Map.of("message", "Public CAS SLO demo");
    }

    @GetMapping("/reports")
    public Map<String, String> reports(Authentication user) {
        return Map.of("message", "Protected data",
                      "user", user.getName());
    }

    @GetMapping("/signed-out")
    public Map<String, String> signedOut() {
        return Map.of("status", "Local application logout done");
    }
}
```

The `/cas/slo` SLO endpoint **has no controller**. The `/signed-out` page confirms only **local logout**, without claiming the CAS Server or every app destroyed sessions.

### 8.6. Empirical prerequisites for the example to run

Beyond a compiled project, you need:

1. A running HTTPS CAS Server whose certificate is trusted by the client JVM.
2. A CAS test user `alice` and registered service `https://app.example.org/login/cas`.
3. Registered service configured for back-channel SLO with `logoutUrl=https://app.example.org/cas/slo`; if custom URLs are unsupported, adjust design/matcher to the default `/login/cas`.
4. Network reachability from the CAS Server to App A's callback from the actual pod/VM; ingress forwards POSTs/bodies properly.
5. Spring Boot exposed over HTTPS at the public host, browser retaining session cookies.
6. `SingleSignOutFilter`/listener dependency matching Jakarta Servlet API; filter order logs showing it runs before Spring Security.
7. `UserDetails` fixture containing the exact username issued by CAS.
8. Browser testing plus CAS Server logs confirming ticket→session mapping and invalidation, not just seeing the CAS logout page.

## 9. When using the default `/login/cas` endpoint for both login and SLO

Not every CAS Server has a dedicated registered `logoutUrl`; the default case typically POSTs to `/login/cas`.

If keeping the **early Servlet filter approach** from section 8, change:

```java
reg.addInitParameter("logoutCallbackPath", "/login/cas");
```

And ensure the registered-service sends SLO to `https://app.example.org/login/cas`. **No CSRF bypass is needed** because the SLO filter still runs before Spring Security. Browser `GET /login/cas?ticket` continues to the CAS auth filter; CAS `POST /login/cas` is handled by the SLO filter.

If deploying the **SLO handler after `CsrfFilter`** approach, the exemption matcher must be:

```java
RequestMatcher casSloPost = request ->
    "POST".equals(request.getMethod())
      && "/login/cas".equals(request.getServletPath());

http.csrf(csrf -> csrf.ignoringRequestMatchers(casSloPost));
```

**Never exempt all of `/login/**`**, never exempt `GET /login/cas` since GET needs no token by default, and never exempt any request carrying a `logoutRequest` query parameter on arbitrary paths. Scope the exemption strictly to the method + exact callback path matching observed CAS config.

## 10. Where does login record the mapping? Filter order and session fixation

In modern Servlet setups, Spring Security commonly enables **session fixation protection** (e.g., `changeSessionId` after login). Because CAS SLO relies on an `HttpSession` reference, test the mapping across the full lifecycle:

```text
GET /login/cas?ticket=ST-1
    |
SingleSignOutFilter stores ST-1 -> HttpSession object
    |
CasAuthenticationFilter validates ticket
    |
Spring Security session fixation strategy (changes session id)
    |
App session authenticated and remains in use
    |
CAS POST /cas/slo, SessionIndex=ST-1
    |
SingleSignOutFilter looks up mapping
    |
invalidates the authenticated HttpSession
```

If configuration switches from `changeSessionId` to `newSession`/`migrateSession`, or the application recreates sessions in custom code, the mapping may no longer reference the final session unless the integration updates it. **Never disable session fixation protection just to make SLO work**; instead verify the fixation strategy, test session identity, and use a compatible library/session mapper.

### 10.1. Debugging "SLO returned 200 yet user is still logged in"

Possible causes:

- The SLO callback filter returned 200 yet **did not find the ST in `SessionMappingStorage`**.
- The filter was mapped only to `/cas/slo`, missing `GET /login/cas?ticket=...` to create the mapping.
- The CAS Server sent a `SessionIndex` not matching the ST stored by the client.
- The post-authentication local `HttpSession` changed in a way the mapping did not follow.
- The user has **another session** on a different browser/tab/node or immediately re-SSO'd after invalidation.
- The same account has multiple local sessions; the SLO message targeted only the session linked to that ticket.
- The browser is showing cached HTML, while the next request is already unauthenticated.
- The CAS request hit node B while the mapping lived on node A; storage was not shared.
- A reverse proxy returned 200 from a fake endpoint (MVC/WAF) instead of the SLO filter.

**Evidence to collect:** pseudonymized local `HttpSession` ID, hashed/trace ticket correlation ID without exposing raw STs, invalidation event, fresh HTTP request to a protected resource, and auth server result—never rely solely on seeing a "logged out" page or HTTP 200.

## 11. Local logout and "log out of all applications": UX action order

Spring Security `POST /logout` normally:

- Invalidates the local `HttpSession`.
- Clears `SecurityContextHolder` and the context repository.
- Cleans up CSRF/remember-me state via `LogoutHandler`s.
- Redirects to a local logout success page or configured URL.

**It does not automatically destroy the CAS TGT/TGC.** Thus if the user immediately revisits a protected URL, the remaining CAS SSO session can issue a **new ST** and log the user right back in. That is not automatically a local logout bug.

To terminate CAS SSO:

```text
(1) Browser POST /logout at App A
    with App A's CSRF token
    => A session invalidated

(2) App redirects browser to CAS /cas/logout
    via a fixed/approved server-side URL
    => CAS TGT/TGC ends

(3) CAS sends SLO notifications to authenticated services
    => CAS clients use SLO filters to invalidate local sessions

(4) Browser reaches an appropriate signed-out page;
    do not claim all services logged out if SLO had errors.
```

Depending on policy, you can offer users **"Log out of this application"** and **"Log out of SSO"**. If automatically redirecting to CAS logout after local POST, enforce a fixed URL or registered post-logout redirect service; **never accept `?returnTo=https://evil...`** as an open redirect.

### 11.1. Why does the Spring reference add another `LogoutFilter` before `LOGOUT_FILTER`?

The Spring Security CAS documentation shows an old XML example placing a `requestSingleLogoutFilter` to redirect the browser to the CAS logout endpoint alongside `singleLogoutFilter` receiving notifications from CAS. These are **two distinct functions**:

1. Browser requests local/global logout to tell the CAS Server to end SSO.
2. CAS Server sends `logoutRequest` back to the app signaling it to invalidate its session.

**Do not mechanically copy old XML filter ordering into Spring Boot 3.x** without verifying `CsrfFilter` ordering and POST CSRF requirements. Depending on the app, browser redirection can be implemented cleanly via a safe `LogoutSuccessHandler` or a link on the success page rather than adding an extra `LogoutFilter` with unclear matchers.

### 11.2. Do not accept SLO messages on `POST /logout`

`POST /logout` is a browser action carrying a CSRF token. Back-channel CAS SLO carries `logoutRequest` with `SessionIndex`, without local browser cookies/CSRF. Mixing both on one endpoint undermines narrowing exemptions and can open logout CSRF/DoS. If the CAS Server supports a dedicated `logoutUrl`, pick `/cas/slo` as shown; if forced to use the default `/login/cas`, still keep it separate from browser `/logout`.

## 12. Protecting the SLO receiver endpoint without browser CSRF

CSRF protects **browser cookie workflows**; CAS back-channel SLO requires a **server-to-server** trust mechanism.

### 12.1. Network and TLS

- CAS Server calls `https://app.example.org/cas/slo` over HTTPS; certificate/hostname/trust chain must be valid for the CAS HTTP client.
- At ingress, route `POST /cas/slo` strictly to the right service handler, preserving the form body; block requests from arbitrary unknown network sources when restrictable.
- Behind a CDN/WAF, ensure CAPTCHA/bot challenges or login gates do not intercept the callback.
- mTLS or private networking with CAS strengthens trust where client/server support it; do not claim Apereo Java CAS Client enforces mTLS on SLO by default.
- IP allowlists must account for CAS NAT/egress gateways/HA/DR and never trust client-supplied headers alone. CAS origins may comprise multiple nodes.
- Ensure proxies do not log raw `logoutRequest` payloads in access logs or analytics; XML can contain sensitive `NameID`/`SessionIndex` values.
- Enforce appropriate request body size limits and timeouts to mitigate XML DoS and rate-limit abnormal callback volume.

### 12.2. Message integrity and authenticity

A SAML-style `LogoutRequest` in the CAS protocol **is not automatically equivalent** to a signed SAML 2.0 Single Logout request verified by a SAML framework. Never assume a body containing `LogoutRequest` XML is inherently trustworthy.

Explicitly verify for your CAS Server + Java CAS Client version:

1. Which integrity/authenticity checks the filter supports for SLO payloads.
2. Whether `Issuer`, destination, timestamps, or XML signatures (if required by profile/product) are validated.
3. Whether replay/deduplication, ST→session mapping, and tenant/issuer scoping are enforced.
4. Whether ingress source restrictions or mTLS can authenticate the CAS Server.
5. Whether forged requests with a leaked `SessionIndex` could cause logout DoS, and how that is prevented.
6. Whether the callback uses the approved registered-service `logoutType=BACK_CHANNEL` and URL.

**Never write a custom XML parser with XXE enabled**, and never take a browser-submitted `SessionIndex` string to call `session.invalidate()` on arbitrary sessions. If an Apereo Java CAS Client release lacks the authentication/integrity controls demanded by a strict threat model, add network/mTLS authentication or adopt an agreed protocol profile supporting verified signed logout notifications rather than waiving security requirements.

### 12.3. Prevent a tenant A CAS Server from destroying tenant B sessions

In multi-tenant/multi-CAS applications:

- Each CAS Server has its own trust domain, registered-services, and callback policies.
- A `SessionIndex` alone may be ambiguous if mappings are not namespaced by CAS source, application, tenant, and ticket.
- If a user belongs to multiple tenants, SLO from one CAS issuer must not automatically destroy sessions from other issuers.
- An admin disabling an account in tenant A requires tenant-scoped revocation policies; do not equate it with global logout across every account.
- Never use a global static map without HA and isolation planning.
- When callbacks carry no explicit `registrationId`, derive context from source routing and verified CAS trust in ingress/server configuration—never from email, raw `Host`, or untrusted XML.

## 13. Standalone Java 17: testing CSRF scope and processing order

The following example is a **logical model** running on JDK 17 with no Spring/CAS dependencies. It does not accept real STs, parse SAML, check TLS, or invalidate production `HttpSession`s; it illustrates why **only POST to the exact SLO endpoint** gets a CSRF exemption and why **an SLO filter before CSRF** preserves local logout protection.

File `SloCsrfBoundaryDemo.java`:

```java
public final class SloCsrfBoundaryDemo {

    record Request(String method, String servletPath,
                   boolean csrfTokenValid) { }

    static boolean safeMethod(String method) {
        return "GET".equals(method) || "HEAD".equals(method)
            || "OPTIONS".equals(method) || "TRACE".equals(method);
    }

    static boolean isBackChannelSloPath(Request request) {
        return "POST".equals(request.method())
            && "/cas/slo".equals(request.servletPath());
    }

    // Simulates strategy B: if the request traverses CsrfFilter,
    // waive the CSRF token requirement only for POST /cas/slo.
    static boolean csrfRequired(Request request) {
        return !safeMethod(request.method())
            && !isBackChannelSloPath(request);
    }

    // trustedCasMessage is a model assumption.
    // Real systems require origin/protocol authentication.
    static String dispatch(Request request,
                           boolean trustedCasMessage) {

        // Represents SingleSignOutFilter placed before CsrfFilter.
        if (isBackChannelSloPath(request) && trustedCasMessage) {
            return "SLO_HANDLED";
        }

        if (csrfRequired(request) && !request.csrfTokenValid()) {
            return "CSRF_403";
        }

        if ("POST".equals(request.method())
                && "/logout".equals(request.servletPath())) {
            return "LOCAL_LOGOUT";
        }

        // Requests are not treated as logout unless endpoint/method match;
        // real routes also enforce authorization.
        return "NOT_LOGOUT";
    }

    public static void main(String[] args) {
        Request slo = new Request(
            "POST", "/cas/slo", false);
        Request local = new Request(
            "POST", "/logout", false);
        Request localValid = new Request(
            "POST", "/logout", true);
        Request near = new Request(
            "POST", "/cas/slo-extra", false);
        Request wrongMethod = new Request(
            "PUT", "/cas/slo", false);
        Request getSlo = new Request(
            "GET", "/cas/slo", false);

        System.out.println("sloExempt=" + !csrfRequired(slo));
        System.out.println("localExempt=" + !csrfRequired(local));
        System.out.println("nearExempt=" + !csrfRequired(near));
        System.out.println("putExempt=" + !csrfRequired(wrongMethod));

        System.out.println("slo=" + dispatch(slo, true));
        System.out.println("localMissingCsrf=" +
            dispatch(local, false));
        System.out.println("localWithCsrf=" +
            dispatch(localValid, false));
        System.out.println("nearPath=" +
            dispatch(near, false));
        System.out.println("putOnSloPath=" +
            dispatch(wrongMethod, false));
        System.out.println("getSlo=" +
            dispatch(getSlo, false));
        System.out.println("untrustedSlo=" +
            dispatch(slo, false));
    }
}
```

Compile/run on JDK 17+:

```bash
javac --release 17 SloCsrfBoundaryDemo.java
java SloCsrfBoundaryDemo
```

**Deterministic** stdout:

```text
sloExempt=true
localExempt=false
nearExempt=false
putExempt=false
slo=SLO_HANDLED
localMissingCsrf=CSRF_403
localWithCsrf=LOCAL_LOGOUT
nearPath=CSRF_403
putOnSloPath=CSRF_403
getSlo=NOT_LOGOUT
untrustedSlo=NOT_LOGOUT
```

**Result explanation:**

- Only `POST /cas/slo` is designed with a CSRF exception; `POST /cas/slo-extra`, `PUT /cas/slo`, and `POST /logout` are not.
- `slo=SLO_HANDLED` assumes the callback **passed origin/protocol verification**; this models the protocol filter and does not prove a real HTTP callback came from CAS.
- Browser `POST /logout` missing CSRF is rejected; with a CSRF token it executes local logout.
- `GET /cas/slo` is a safe method so it needs no CSRF, yet **it is never processed as an SLO POST**.
- `untrustedSlo` in the demo returns `NOT_LOGOUT` despite being CSRF-exempt; **do not assume the real Apereo filter automatically performs every equivalent authenticity check**. Production must use network/integrity controls and the library's contract.
- In the **early Servlet filter option**, the SLO callback is processed before `CsrfFilter`, so no CSRF exception is needed. `csrfRequired()` models **Option B**, clarifying the boundary when an exception must be configured.

**Runnability note:** This is a standalone Java 17 program using `record` with zero external dependencies. The Spring code in section 8 requires Spring Boot/Security/Apereo dependencies and will not compile with plain `javac` without the classpath.

## 14. Test matrix: must prove real sessions are revoked

### 14.1. Success cases

| Test | Verification step | Expected outcome |
| --- | --- | --- |
| CAS login records mapping | User logs in, browser GET `/login/cas?ticket=ST-...` | SLO filter observed request and mapped to real `HttpSession` |
| Back-channel CAS SLO | Terminate TGT at CAS Server, CAS POST `/cas/slo` | Filter receives and invalidates exact app session |
| Session unusable afterwards | After SLO, resend old browser session cookie to protected API | No old data returned; triggers fresh auth or 401/302 per policy |
| Local logout with CSRF | Browser POST `/logout` with token | Local session invalidated; no 403 error |
| Local logout without CSRF | Browser POST `/logout` without token | 403, local logout not executed |
| CAS without browser cookie | CAS HTTP client sends SLO POST without `JSESSIONID` | SLO still succeeds via ticket→session mapping |
| Dedicated callback | CAS registered-service `logoutUrl=/cas/slo` | Actually delivered to that URL, not default `/login/cas` |
| Cleanup listener | Local session timeout/invalidation | Mapping entry cleaned up by listener |
| Multi-node | Login on pod A, SLO callback arrives at pod B | Shared mapping or mechanism routing invalidation to session owner |
| Front-channel if used | CAS configured `FRONT_CHANNEL` and Java client supports it | Browser flow handled properly; never assume it works untested |
| Duplicate logout | CAS sends duplicate notification | Does not destroy another session; idempotent/benign handling |
| Same user, 2 sessions | User logs in from two separate browsers | Only sessions scoped to the CAS event/policy are destroyed |

### 14.2. Failure cases to isolate

| Scenario | Security expectation | Diagnosis |
| --- | --- | --- |
| SLO filter registered after Spring Security | CSRF-less CAS POST gets 403 | Check Servlet Filter order; place SLO before chain |
| SLO filter mapped only to `/cas/slo` | No mapping from `GET /login/cas?ticket` | Map filter `/*` and narrow `logoutCallbackPath` |
| Registered-service missing `logoutUrl` | CAS POSTs to `/login/cas` instead of `/cas/slo` | Cross-check service registry/CAS logs |
| `permitAll("/cas/slo")` while `CsrfFilter` runs first | CAS POST still gets 403 | Use early filter or exact CSRF matcher, not just `permitAll` |
| Global `csrf.disable()` | Browser POST actions lose protection | Restore CSRF; exempt only CAS endpoint when required |
| `csrf.ignoringRequestMatchers("/**")` | Every POST is exempted | Narrow to path+method; cover with integration tests |
| Exempt `/logout` to accept CAS SLO | Logout CSRF becomes possible | Separate CAS callback from browser logout |
| CAS SLO GET/POST blocked by WAF | No event reaches application | Review ingress/payload/method/TLS |
| CAS SLO POST sent to internal HTTP URL | CAS cannot route properly; confidentiality risk | Use public canonical HTTPS URL |
| `SessionIndex` mismatch | HTTP 200 yet session survives | Check ticket→session mapping/actual CAS ST |
| Duplicated `SingleSignOutFilter` | Unstable/body read twice | Register only one filter in one layer |
| Listener unregistered | Stale mappings remain after timeout/invalidation | Register `SingleSignOutHttpSessionListener` |
| Session fixation creates a new session | SLO kills old session; authenticated session stays alive | Test session lifecycle; never disable fixation |
| Form body encoding altered | Cannot read `logoutRequest` | Enable UTF-8/verify raw form parser & WAF |
| Two pods, in-memory map | CAS callback hits node without mapping | Design distributed mapping/target node routing |
| Callback returns 200 from MVC fallback | App never invalidates `HttpSession` | Remove dummy controller; verify Apereo filter runs |
| Forged `LogoutRequest` from Internet | Logout DoS possible if ticket leaks/weak policy | Enforce origin/mTLS/network/signature policy/replay checks |
| User immediately re-SSO'd | Browser gets a brand-new session after SLO | Compare session IDs and network redirects; do not assume SLO broke |
| Browser still displays cached page | Old HTML visible yet APIs already deny | Refresh/new request; apply `Cache-Control` for sensitive data |
| CAS 5/6/7/8 logout differences | Path/format/front-channel mismatches | Pin version and check docs + real tests |
| CAS as SAML/OIDC broker | CAS Filter does not process other protocol logouts | Use the matching logout protocol |
| Cross-tenant session mapping | Tenant A SLO kills tenant B session | Namespace issuer/service/tenant and enforce authorization checks |

**Do not rely solely on HTTP 200.** PASS criteria must include **the session was invalidated**, old tokens/cookies can no longer access protected data, mappings were cleaned up, other sessions were untouched, and browser local logout still enforces CSRF.

### 14.3. Writing integration tests properly

Against staging CAS:

1. Log in through real CAS to obtain a fresh Service Ticket; never fabricate `ST-TEST` expecting CAS to validate it.
2. Trace mappings with an ID **containing no raw ST**.
3. End the CAS SSO session via supported UI/endpoints and observe the CAS-emitted notification rather than POSTing fake XML and calling it end-to-end.
4. Confirm the app session holding `SecurityContext` is gone: GET a protected endpoint with the old cookie and confirm re-auth/denial.
5. Check a second browser tab, user B's session, and other tenant sessions; none may be erroneously invalidated.
6. Test local `POST /logout` with/without a CSRF token and business POST actions.
7. Test disabled SLO, network outages, timeouts, CAS retries, pod failovers, and session fixation strategies.
8. Test dedicated CAS `logoutUrl` and default `service URL` across two **separate** configs without mixing assumptions.
9. Vary forwarded headers/context path/ingress routes and rerun regressions.
10. Measure callback success/failure/silent mismatches and invalidated session counts, not merely logout request counts.

**Spring Security MockMvc** can test application CSRF rules, yet **does not replace** end-to-end CAS Server testing: `csrf()` test support validates browser POSTs; a fake `logoutRequest` POST in MockMvc only tests matcher/filter routing and does not prove real CAS session mapping or logout authenticity.

## 15. Symptom-based operational diagnostic table

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| User clicks "logout all" yet App A stays logged in | CAS SLO not sent or A did not handle it | Check CAS `logoutType`, `logoutUrl`, filter order, mapping |
| CAS logs SLO POST 200 yet session A remains | Filter/controller did not invalidate or mapping missed | Check ST→HttpSession, session fixation, and node |
| CAS SLO 403 | `CsrfFilter` blocked, authorization/gateway, WAF | Early SLO filter or exact CSRF exemption/permitAll if needed; inspect ingress |
| CAS SLO 404 | CAS called wrong path or filter unmapped | Compare registered `logoutUrl`/service URL and servlet path |
| CAS SLO 302 to CAS login | Endpoint intercepted by `AuthenticationEntryPoint`/gateway requiring login | Let protocol filter handle first without browser cookies |
| CAS SLO 400/415 | Incompatible form encoding/content-type/body parser | Use `application/x-www-form-urlencoded` per CAS client, UTF-8 |
| SLO works on only one pod | Per-JVM static mapping or flawed sticky routing | Distributed session mapping/HA design |
| SLO destroys the wrong session | Mapping keyed by username instead of ST/tenant, collision | Check `SessionIndex`/ST and tenant-aware origin scoping |
| Local logout 403 | Browser POST missing CSRF token | Send proper CSRF token; never disable CSRF |
| Login loop after local logout | CAS TGT/TGC remains; app re-SSOs | Distinguish local vs. CAS global logout |
| Login loop after SLO | Browser re-SSO'd or session was not properly invalidated | Trace requests and old vs. new session IDs |
| Previously loaded page still visible | Browser cache | Network refresh and fresh API call to confirm |
| CAS callback lacks cookie | Completely normal for back-channel | Use ticket–session map; never require `JSESSIONID` |
| Anomalous `logoutRequest` traffic | Possible scan, spoofing, replay/DoS | Check origin, method/path/size/policy, and audit |
| Servlet Filter missing from debug chain | Filter lives at Servlet layer outside `FilterChainProxy` | Inspect Servlet filter registration/order, not just Spring Security debug logs |
| Filter added via `addFilterAt` has odd order | Placed at `CasAuthenticationFilter` or equivalent slot | Place before `CsrfFilter`/CAS filter per architecture and test |
| `logoutRequest` token logged | Access log captures sensitive query/form body | Redact/enforce retention; never log raw payloads |
| Filter runs twice | Double registration in Servlet and Spring | Remove one registration; check Boot auto-registration |
| Changing callback from `/login/cas` to `/cas/slo` has no effect | CAS registered-service `logoutUrl` not updated | Update registry and test from real CAS Server |

### 15.1. Request-level decision tree

```text
Did CAS emit an SLO notification?
    |
    +-- NO  -> check TGT logout, CAS registered-service,
    |          logoutType, service registry, CAS logs.
    |
    +-- YES -> What is the URL/method?
               |
               +-- POST /login/cas  -> CAS default service URL?
               |
               +-- POST /cas/slo    -> Dedicated CAS logoutUrl?
               |
               +-- GET JSONP        -> FRONT_CHANNEL; client supported?
               |
               +-- Mismatch         -> fix CAS service config.
                         |
                         v
             Did the request reach App ingress and Spring?
                         |
             +-- 404/502/network -> route, TLS, WAF, CAS egress.
             |
             +-- 403 -> CsrfFilter or auth gateway?
                        |
                        +-- CsrfFilter -> SLO filter order/narrow exception.
                        +-- Gateway -> bypass exact callback, verify origin.
             |
             +-- 200 -> Did SingleSignOutFilter actually process it?
                        |
                        +-- No  -> dummy controller/duplicate/wrong path.
                        |
                        +-- Yes -> Did ticket→HttpSession mapping hit?
                                   |
                                   +-- Miss -> login callback, listener,
                                   |           fixation, cluster/storage.
                                   |
                                   +-- Hit -> Did session.invalidate really run?
                                              |
                                              +-- Yes -> test GET API with old
                                              |          cookie, check re-SSO.
                                              +-- No  -> fix client/provider.
```

## 16. Pre-production security/QA checklist

- [ ] Architecture docs distinguish local `POST /logout`, CAS `/cas/logout`, and CAS back-channel SLO callbacks.
- [ ] `ServiceProperties.service` matches the public CAS login callback; dedicated `logoutUrl` registered if using `/cas/slo`.
- [ ] `logoutType=BACK_CHANNEL`/`FRONT_CHANNEL` selected per CAS Server and Java CAS Client capability, with end-to-end tests.
- [ ] `SingleSignOutFilter` sees both ticket-bearing login requests and SLO notifications; registration pattern/order verified.
- [ ] `SingleSignOutHttpSessionListener` registered exactly once to clean up mappings.
- [ ] `SingleSignOutFilter` is not registered simultaneously in both Servlet and Spring Security chains.
- [ ] If the SLO Servlet filter precedes the Spring chain, no redundant CSRF exemption is added.
- [ ] If SLO must pass through `CsrfFilter`, exempt only exact `POST` + actual local callback path; never disable CSRF globally.
- [ ] Browser `POST /logout` and all stateful actions still mandate a CSRF token when using cookie sessions.
- [ ] `permitAll`/`csrf.ignoringRequestMatchers` are understood as separate controls and applied per actual filter path.
- [ ] SLO callback requires no browser cookie; any CSRF exemption is compensated by network/TLS/integrity/session-correlation controls.
- [ ] CAS HTTP client can actually reach the HTTPS callback; ingress/WAF preserves method, form body, and encoding.
- [ ] No dummy MVC controller returns 200 for SLO requests unhandled by the filter.
- [ ] Unverified `logoutRequest` query/body values are never used to arbitrarily delete sessions.
- [ ] ST→HttpSession mapping aligns with the session fixation strategy and local `SecurityContext`.
- [ ] Multi-node environments have appropriate mapping/invalidation, cleanup, and SLAs; tested callbacks hitting non-owner nodes.
- [ ] Multi-tenant/multi-CAS setups isolate issuers, services, and tenant memberships.
- [ ] Duplicate/replayed/malformed SLO messages are handled safely without logging out wrong users.
- [ ] Logging/auditing uses event/trace IDs and never records raw STs, `SessionIndex`, SAML `LogoutRequest`, `JSESSIONID`, or secrets.
- [ ] Tested browser local logout with/without CSRF token, CSRF-less SLO POST, wrong path, wrong method, and auth gateway.
- [ ] Tested SLO from real CAS, confirming the session is invalidated and protected APIs reject the old session.
- [ ] Tested IdP SSO/session reuse after local logout so immediate re-login is not mistaken for an SLO failure.
- [ ] CSRF exceptions and filter chain ordering are reviewed when upgrading Spring Security/CAS Client, especially Jakarta Servlet and Spring Security 7.
- [ ] HA failover, certificate rotation, ingress changes, and CAS outages all have regression tests/runbooks.

**Conclusion:** For **CAS Logout**, filter ordering decides whether notifications are handled or rejected by Spring Security's `CsrfFilter`. A reliable setup lets `SingleSignOutFilter` observe both the **Service Ticket at login** and the **SLO notification** to invalidate the right `HttpSession`. The CAS Server can send back-channel POSTs to the **original service URL** or a dedicated `logoutUrl` like `/cas/slo`. If the SLO filter sits **before `CsrfFilter`**, no extra CSRF exemption is needed; if the callback must traverse `CsrfFilter`, exempt **only POST on that exact SLO callback**, keeping CSRF intact for `POST /logout` and business actions. Never trade away app-wide CSRF protection or origin/correlation verification just to receive logout calls.

## 17. References

1. [Spring Security — CAS Authentication, Single Logout](https://docs.spring.io/spring-security/reference/servlet/authentication/cas.html) — `SingleSignOutFilter` before CAS filter, local logout, and requesting global logout.
2. [Spring Security 6.5 — CSRF Protection](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html) — `CsrfFilter`, `ignoringRequestMatchers`, and CSRF requirements for POST logout.
3. [Spring Security — Handling Logouts (Servlet)](https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html) — `LogoutFilter`, `LogoutHandler`, `SecurityContextLogoutHandler`, and local logout.
4. [Spring Security 6.5 — Servlet Security Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html) — `FilterChainProxy`, `addFilterBefore`, and verifying filter order.
5. [Apereo Java CAS Client — Configuring Single Sign Out](https://github.com/apereo/java-cas-client#configuring-single-sign-out) — `SingleSignOutFilter`, `SingleSignOutHttpSessionListener`, `logoutCallbackPath`, `/*` URL pattern, and mapping storage.
6. [Apereo CAS 7.3 — Logout & Single Logout](https://apereo.github.io/cas/7.3.x/installation/Logout-Single-Signout.html) — `logoutType`, back-channel POST/front-channel GET, `logoutUrl`/service URL, and CAS SLO session correlation.
7. [Apereo CAS Protocol Specification](https://apereo.github.io/cas/development/protocol/CAS-Protocol-Specification.html) — CAS `/login`, `/logout`, service tickets, TGT/TGC, and service registration.
8. [Spring Security — Authentication Persistence](https://docs.spring.io/spring-security/reference/servlet/authentication/persistence.html) — `SecurityContextRepository` and `HttpSession`.
9. [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html) — session fixation strategies and local sessions.
10. [OWASP Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html) — narrowing CSRF exceptions, logout CSRF, and cookie-based session workflows.
11. [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html) — session invalidation, logout, and session IDs.
12. [OWASP XML External Entity Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/XML_External_Entity_Prevention_Cheat_Sheet.html) — avoiding custom XXE-vulnerable parsers when integrating XML SLO.
