# Distinguishing an Application Session from an Identity Provider Login Session

> **Topic:** Spring Security – federation. **Knowledge group:** Sessions and browsers. This article explains the difference between an **application local login session (SP/RP application session)** and an **identity provider Single Sign-On session (IdP/OP SSO session)** in OIDC, SAML2, and CAS; applicable to browser-based Spring Security servlet applications.

## 1. Learning Objectives

After this article, learners can:

1. Identify who creates, maintains, and expires an **application session** versus an **IdP session**.
2. Explain why a user who **logs out of application A**, returns to A, and can log back in immediately **without entering a password**.
3. Understand why **IdP session expiration does not automatically delete** active application sessions immediately, unless logout notifications/session checks exist and the SP enforces them.
4. Distinguish between **session cookie**, **ID Token**, **OAuth Access Token**, **Refresh Token**, **SAML Assertion**, **CAS Service Ticket**, and **CAS Ticket-Granting Ticket**.
5. Identify the impact of **session timeout**, `Secure`/`HttpOnly`/`SameSite` cookies, HTTPS, session fixation, CSRF, and binding sessions to the browser.
6. Choose properly among **local logout**, **RP-initiated/IdP-initiated logout**, **SAML Single Logout (SLO)**, and **OIDC back-channel logout**, understanding the limitations when the IdP/application does not support them.
7. Configure Spring Security for web sessions and local logout; know when to use `OidcClientInitiatedLogoutSuccessHandler` or `saml2Logout`.
8. Independently test the states of both sessions using multiple tabs, multiple applications, incognito windows, timeouts, and logout.
9. Maintain a **reauthentication / step-up** policy for high-risk actions, rather than equating "has SSO" with "just entered password/MFA".
10. Design user support workflows and investigate login-loop / incomplete-logout issues suited to federation systems.

**Core principle:** The IdP verifies identity so the application can **create its own application session**. A single authentication at the IdP does **not** turn all applications' sessions into **one shared session**. Coordination between sessions only happens through login/logout protocols and configured policies.

## 2. Two Sessions Living in Two Different Systems

Consider a user opening three websites:

```text
Browser
  |
  +-- https://app-a.example.org     (RP/SP A: reporting)
  |      Cookie: JSESSIONID=A-opaque
  |      Server: HttpSession A + SecurityContext A
  |
  +-- https://app-b.example.org     (RP/SP B: HR)
  |      Cookie: JSESSIONID=B-opaque
  |      Server: HttpSession B + SecurityContext B
  |
  +-- https://login.example.org     (IdP / OIDC OP)
         Cookie: IDP_SSO=I-opaque
         Server: IdP login/SSO session I
```

The browser can hold **three cookies across three different origins/paths**. The cookie names are examples; the actual IdP cookie is determined by the product. When the browser calls App A, according to cookie scope it normally sends **App A's** cookie, **not the IdP cookie to App A**. When redirected to `login.example.org`, the browser sends the IdP cookie matching the IdP's own scope, and the IdP can tell that the user has previously authenticated.

### 2.1. Application session (local SP/RP session)

- **Who owns it?** Each individual Spring Security application, such as App A or App B.
- **When is it created?** After the application verifies the OIDC ID Token, SAML Response, or CAS Service Ticket and successfully logs the user in, then stores `Authentication` in `SecurityContext`/session.
- **Main data?** An opaque Session ID in a browser cookie and server-side state (or distributed session store), `SecurityContext`, user ID, authorities, and application data.
- **When is it used?** On each browser request to **that application**, without redirecting to the IdP every time.
- **Who expires it?** App A's session timeout/invalidation policy; local logout, admin revocation, session store loss, session ID rotation, or security policy.
- **Boundary?** A session of App A is not by default a session of App B, even if both authenticate through the same IdP.
- **Characteristic:** While App A's session remains valid, the IdP may **not be called** for each page view; therefore, an expired IdP session does not necessarily log out App A immediately.

In Spring Security Servlet with session persistence, `SecurityContextHolder` represents the current authentication within a request, while `HttpSession` (or Spring Session storage) can store state for subsequent requests. Do not call `SecurityContextHolder.clearContext()` **alone** and assume every session on the server/browser has been destroyed; proper logout/session invalidation mechanisms are needed.

### 2.2. IdP session (OP/IdP SSO session)

- **Who owns it?** The identity provider: OpenID Provider, SAML IdP, or CAS server.
- **When is it created?** When the user logs in/completes MFA or authentication policies at the IdP.
- **Main data?** IdP authentication state, the IdP's browser cookie, possibly an OP-provided `sid`/session identifier, authentication method/`auth_time`/assurance context.
- **When is it used?** When the browser arrives at the IdP in a new login flow of App A/B; the IdP can reuse the previous authentication to issue an ID Token/SAMLResponse/Service Ticket.
- **Who expires it?** The IdP's idle/absolute timeout policy, logout, account lock, risk engine/MFA, or revocation.
- **Boundary?** The IdP session is **not** App A's `JSESSIONID` cookie. Nor can the IdP arbitrarily modify every RP's session store unless linked/notification mechanisms are deployed.
- **Characteristic:** While the IdP session remains valid, an application that just performed local logout can redirect to the IdP and receive fresh login proof **without needing a password**.

**An IdP session does not mean "an organization-wide session across all devices".** Different browsers, different profiles, and different machines usually have different cookies/SSO sessions; an IdP may additionally manage device-wide sessions or remembered devices depending on the product. Specific behavior must be tested, not inferred from an account being logged in on another browser.

### 2.3. Quick Comparison Table

| Criterion | Application A Session | IdP Session |
| --- | --- | --- |
| Owner | SP/RP A | OP/IdP |
| Common cookie | `JSESSIONID` or A's session cookie | IdP's SSO cookie |
| Processing server | App A / Spring Session | IdP server/session store |
| Scope | Authorized web requests of A | SSO visits to the IdP for multiple RPs |
| Created when | A verifies the federation response and establishes local authentication | User authenticates/establishes SSO at the IdP |
| Is it an OIDC/SAML token? | No | No; the IdP can issue tokens based on the session |
| Expired by | A's timeout/logout/revocation | IdP's timeout/logout/revocation |
| Impact on B | Not directly | Can help B create a **new session B** when the browser visits the IdP |
| Local logout at A | Invalidates A session | Usually does **not** destroy the IdP session |
| IdP logout | Does not automatically guarantee A session is deleted | Destroys IdP session; requires propagated logout mechanism to delete A |
| Re-login after local logout | Can SSO immediately if IdP session remains | Can re-authenticate automatically if policy allows |
| Clock/timeout | Configured by application and store A | Configured independently by IdP |

## 3. Which Sessions Exist in an Actual OIDC Login Flow?

Suppose App A uses Spring Security `oauth2Login` with the OIDC Authorization Code flow.

```text
(1) Browser -> GET https://app-a.example.org/reports
                 no local session A yet

(2) App A -> 302 to IdP's authorization endpoint
                 sends state, nonce, client_id, redirect_uri, scope...
                 may use PKCE depending on client/policy

(3) Browser -> IdP
                 already has valid IdP cookie?
                 |-- No  -> login/MFA -> IdP session I is created
                 +-- Yes -> IdP may reuse I if policy allows

(4) IdP -> 302 to App A callback with authorization code
                 App A verifies state/correlation

(5) App A backend exchanges code for tokens; verifies ID Token
                 signature, issuer, audience, exp, nonce per flow

(6) App A -> creates Authentication + HttpSession A
                 browser receives session cookie A

(7) Browser -> GET /reports with cookie A
                 App A uses local session; NO need to call IdP on every request
```

**Time distinction:** In step (5), the ID Token has `iat`, `exp`, and possibly `auth_time`; App A uses them per validation rules **at login/relevant checks**. The ID Token's `exp` is **not automatically the timeout of HttpSession A**. Similarly, an expired access token does not automatically delete browser session A. An application may still have a valid session but need to refresh the access token when calling APIs; if refreshing fails, the application must apply its own policy.

**Do not extrapolate from ID Token rules to run SAML/CAS.** OIDC, SAML, and CAS use distinct artifacts and login rules, even though all share the two-tier session model.

### 3.1. Why Doesn't App B Need a Password After App A?

After App A logs in, IdP session I exists. The browser visits App B:

```text
Browser -> App B /staff
  |
  +-- no session B yet, redirects browser to IdP
        |
        +-- IdP receives cookie I again, authentication still valid
               |
               +-- IdP issues new proof for App B (OIDC/SAML/CAS)
                      |
                      +-- App B verifies separately
                             |
                             +-- creates session B
```

App B does not take App A's `JSESSIONID=A`; it creates session B based on the federation result **intended for B** (matching OIDC audience/client or SAML AudienceRestriction/Recipient). Session cookies should not be shared between two applications just because both use one IdP.

### 3.2. When App A Performs Local Logout and Returns

```text
T0: App A session = ACTIVE      IdP session = ACTIVE
T1: Browser POST /logout at A;  A session = INVALIDATED
                                IdP session = ACTIVE
T2: Browser GET /reports at A -> A redirects to IdP
T3: IdP sees session I valid, issues proof for A
T4: A verifies proof, creates NEW A session
=> User sees "just logged out and right back in", without entering a password.
```

This is usually the **correct behavior of local logout**, not proof that `HttpSession.invalidate()` failed. Distinguish it from cases where logging out of A truly did **not** delete the session (e.g., a GET logout request blocked by CSRF, session store not invalidated, browser still sending a valid cookie A). Both cases look identical in the UI, but their network traces differ completely.

## 4. When the IdP Session Expires While the Application Session Is Still Alive

Reverse scenario:

```text
T0: App A session = ACTIVE       IdP session = ACTIVE
T1: IdP idle timeout/logout      IdP session = EXPIRED
                                App A session = ACTIVE
T2: Browser GET /reports at A
    App A has valid session A -> can still return 200
T3: App A needs re-login (A session expired, session revoked,
    policy requires step-up, or IdP-initiated logout updated A)
T4: Browser is sent to IdP; since IdP session has expired
    -> user must re-authenticate (unless another mechanism allows otherwise).
```

**Do not assume that changing a password/locking the account at the IdP or logging out of the IdP immediately revokes every session across every application.** Back-channel/front-channel logout or appropriate server-side revocation mechanisms must be integrated and enforced on existing sessions. For stateless APIs, valid access tokens may remain until they expire or are rejected by revocation/introspection/policy.

**Important:** Security policy may dictate that "disabling an account at the IdP must lock access immediately". That requires designing independent **deprovisioning/session revocation**, not just reducing the IdP cookie TTL.

## 5. Do Not Confuse Sessions with Tokens and Protocol Artifacts

| What learners see | Who issues/holds it | What is it used for? | Does it replace the local session? |
| --- | --- | --- | --- |
| **Application session cookie** `JSESSIONID` | App A/Servlet container or Spring Session | References HttpSession/SecurityContext A | It is browser A's session credential, if the app uses server-side sessions |
| **IdP SSO cookie** | IdP | References the SSO session at the IdP when the browser visits the IdP | **Not** used directly as an app session |
| **OIDC ID Token** | OP signed for RP/client | Proof of identity authentication and session info per OIDC | Not a session cookie itself; do not arbitrarily use as a Bearer token for APIs |
| **OAuth Access Token** | Authorization Server issued for resource audience/scope | Calling Resource Server APIs | Not synonymous with an RP browser session; has its own expiry and scope |
| **OAuth Refresh Token** | Authorization Server granted per client/policy | Requesting a new access token without necessarily showing login UI | Does not prove the IdP SSO cookie is still valid |
| **SAMLResponse/Assertion** | IdP issued and signed per profile | SP verifies and creates a session | Login message, **not** an SP session cookie |
| **SAML `SessionIndex`** | IdP includes in `AuthnStatement` when present | May relate to SAML logout/session correlation | Not identical to `HttpSession.getId()` |
| **CAS Service Ticket (ST)** | CAS server issued per service | Service verifies ST, establishes application session | Single-use/short-lived, not an application session cookie |
| **CAS Ticket-Granting Ticket (TGT)** | CAS server | Represents CAS SSO session; browser usually has a linked TGC | TGT is the CAS session, not the SP local session |
| **Remember-me cookie / remembered device** | Application or IdP per policy | Restores a form of login/device trust | A separate mechanism that can cause a promptless "re-login" experience |

**A Session ID in a cookie is usually an opaque value**, not a JWT. The server may use Redis/JDBC to store sessions. If an application adopts a signed self-contained cookie design instead of server-side HttpSession, the storage model differs but **there is still an independent application session** requiring revocation/expiry mechanisms; this article focuses on Spring Security Servlet using HttpSession/Spring Session.

### 5.1. Does an Expired Access Token Log Out the Web Session?

One cannot conclude from `exp` alone:

- An OIDC Client application can store `OAuth2AuthorizedClient`/refresh tokens in a separate repository/service and refresh access tokens when needed, while the local session remains active.
- A Resource Server receiving a Bearer token per request typically validates the token on every request; if the API does not use a browser session, token expiration can cause `401` **unrelated to the IdP session or UI session**.
- If an application intentionally ties session A's lifetime to the IdP authentication time or token, that is an **application policy that must be configured/tested**, not a default equivalence across every framework.

The claim "Token expired, user must re-enter password" is also not always true: a refresh token, IdP SSO cookie, or another session mechanism can re-authenticate automatically, unless policy requires fresh interaction.

## 6. Session Timeout: Who Measures Idle Time and Who Sets Absolute Lifetime?

Three clocks are typically independent:

1. **Application A idle timeout:** After N minutes without a session-maintaining request, server A may expire the session; depending on the session store and heartbeats, "inactivity" in the UI might still emit background requests.
2. **Application A absolute lifetime / max session age:** Policy forcing a new session after a period since login even during active use; must be implemented separately if the container/session API only supports inactivity timeout.
3. **IdP idle/absolute SSO lifetime:** The IdP decides how long its SSO cookie/session remains valid, potentially with "remember me" and authentication context policies.

Additionally, there are `exp` of ID Tokens, access tokens, SAML `NotOnOrAfter`, CAS ticket TTL, MFA duration, and remember-me lifetime. These timestamps **do not synchronize automatically**.

Spring Boot Servlet configuration example:

```yaml
server:
  servlet:
    session:
      timeout: 20m
      cookie:
        secure: true
        http-only: true
        same-site: lax
```

This is an example of an **HTTPS web application** using Servlet container sessions. `server.servlet.session.timeout: 20m` is the application-side inactivity timeout; it **does not configure the IdP SSO timeout** and does not automatically create an absolute lifetime. When using Spring Session Redis/JDBC, verify the actual timeout and store configuration; ensure there is no mismatch among cookie max-age, session TTL, and load balancer.

**SameSite warning:** `SameSite=Lax` typically works for many OIDC GET redirect flows, but **SAML HTTP-POST binding from the IdP to the ACS is a cross-site POST** in many deployments. The SP's session cookie may not be sent if browser policy blocks it; this breaks `AuthnRequest`/`InResponseTo` correlation. Evaluate SameSite compatibility for SAML POST (which may require `SameSite=None; Secure` depending on topology/browser), while maintaining CSRF and other protections. Do not pick `None` system-wide without testing/risk review.

### 6.1. Session Cookie and Server Session Are Not the Same Thing

- **Cookie still in browser but server session expired:** The browser still sends the cookie, the server rejects the old Session ID/creates a new session per policy; cookie presence must not be treated as authenticated.
- **Server session still alive but browser deleted cookie A:** The browser no longer has the session handle to reach session A; the user may be redirected to the IdP and create another session A. The old server session may need cleanup by timeout/cleanup; deleting the cookie only in the browser does not guarantee server-side revocation.
- **Tab 1 performs local logout, Tab 2 still displays the old rendered page:** HTML in the tab may still display from cache, but new API requests must be rejected once the session is invalidated. Test via network/reload, not just by looking at already-loaded content.
- **Browser restart:** Session cookies can be restored by browser restore features; do not rely on "closing the browser" as a reliable logout/session revocation measure.
- **IdP cookie remains after RP logout:** The browser may silently SSO again; this is the nature of local vs IdP sessions.

## 7. Spring Security: Proper Local Logout

Assume the application uses Spring Boot servlet and `spring-boot-starter-security` + `spring-boot-starter-oauth2-client`, with an appropriate OIDC client registration.

File `src/main/java/com/example/sessionlab/OidcLocalLogoutConfig.java`:

```java
package com.example.sessionlab;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OidcLocalLogoutConfig {

    @Bean
    SecurityFilterChain web(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/signed-out", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .logout(logout -> logout
                .logoutUrl("/logout")
                .logoutSuccessUrl("/signed-out")
                .invalidateHttpSession(true)
                .clearAuthentication(true)
                .deleteCookies("JSESSIONID"))
            .build();
    }
}
```

**Reading the configuration:**

- `oauth2Login` handles OIDC login and creates a local authenticated session after verification; no custom controller is needed to handle authorization codes.
- `logoutUrl("/logout")` configures **App A's** logout endpoint. With CSRF enabled in a web app, logout typically requires a **POST with a CSRF token**; do not default to a GET link for logout.
- `invalidateHttpSession(true)` and `clearAuthentication(true)` clear the application authentication session during the logout flow. `deleteCookies("JSESSIONID")` instructs the browser to discard the corresponding session cookie; if the cookie has a specific Domain/Path, check the actual `Set-Cookie` header.
- `logoutSuccessUrl("/signed-out")` redirects the browser to the **application's** public page after local logout. The application needs a corresponding route/controller or page; `permitAll` alone does not create content.
- **There is no step going to the IdP logout endpoint.** After session A is destroyed, the IdP SSO cookie may remain valid. A GET to a protected URL on A can create a new session A via OIDC without prompting for a password.
- Do not put `logout` into `web.ignoring` or disable CSRF app-wide. Do not use `SecurityContextHolder.clearContext()` in a custom controller as a full replacement for the logout filter.

This is a Spring class within a Maven/Gradle project that already has dependencies; it does not compile standalone with `javac OidcLocalLogoutConfig.java` without the Spring classpath. If the project already has another `SecurityFilterChain`, **do not register two chain beans matching all URLs**; integrate the logic into the appropriate chain.

### 7.1. CSRF-Protected Logout Form in Spring MVC/Thymeleaf

An application using server-side templates and Spring Security CSRF integration can render:

```html
<form method="post" action="/logout">
  <input type="hidden" name="_csrf" value="CSRF_TOKEN_FROM_SERVER">
  <button type="submit">Sign out of this application</button>
</form>
```

This is an **illustrative shape**, do not copy `CSRF_TOKEN_FROM_SERVER` literally. In Thymeleaf/Spring MVC, obtain the token dynamically from the request/template integration. Do not hardcode static CSRF tokens in source code and do not put tokens in query strings to share in tickets.

**Browser verification:** Log in with OIDC, GET a protected URL returning 200, POST a valid logout, then GET the protected URL again to start OIDC login; if IdP SSO remains active, the process may complete immediately. To distinguish, inspect network redirects to the IdP and the new session ID rather than relying on whether the user sees a password form.

### 7.2. Do Not "Log Out" by Randomly Deleting Cookies in JavaScript

Browser JavaScript cannot read/delete `HttpOnly` cookies through normal means; only the server has authority to invalidate HttpSession. Operations like `document.cookie="JSESSIONID=..."` may miss the right Domain/Path/Secure attributes and fail to delete the server session. Proper local logout goes through Spring Security's `LogoutFilter`/`LogoutHandler`; other application components such as the OAuth authorized client repository, refresh tokens, or custom state also need cleanup verification per policy.

## 8. OIDC: Logout from RP and IdP Must Coordinate

OIDC supports **RP-Initiated Logout**, a mechanism for an RP to request that the OP log the user out. Both sides must agree on the endpoint and post-logout redirect.

### 8.1. Diagram

```text
Browser        App A (OIDC RP)                   IdP (OP)
   |                |                               |
   | POST /logout   |                               |
   |--------------->|                               |
   |  local logout  |                               |
   |<-- 302 to OP end_session_endpoint ------------|
   |----------------------------------------------->|
   |                |    OP confirms/logs out session|
   |<--------------- post-logout redirect ----------|
   | GET /signed-out|                               |
   |--------------->|                               |
   |<--- public page|                               |
```

**Cases may occur where the OP asks for user confirmation** or lacks endpoint support. A redirect to `end_session_endpoint` **does not by itself prove** the OP actually destroyed the session, nor does it guarantee all other RPs were notified/had sessions deleted. OIDC RP-Initiated Logout defines parameters such as `id_token_hint` and `post_logout_redirect_uri` subject to OP validation; applications should not construct logout URLs from raw user input.

### 8.2. Spring Security Example with `OidcClientInitiatedLogoutSuccessHandler`

This is an **alternative configuration** to section 7 when requesting OP logout. Do not place both catch-all URL configs in the same application.

File `src/main/java/com/example/sessionlab/OidcFederatedLogoutConfig.java`:

```java
package com.example.sessionlab;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.oidc.web.logout.OidcClientInitiatedLogoutSuccessHandler;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OidcFederatedLogoutConfig {

    @Bean
    SecurityFilterChain web(
            HttpSecurity http,
            ClientRegistrationRepository registrations) throws Exception {

        OidcClientInitiatedLogoutSuccessHandler oidcLogout =
            new OidcClientInitiatedLogoutSuccessHandler(registrations);
        oidcLogout.setPostLogoutRedirectUri("{baseUrl}/signed-out");

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/signed-out", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .logout(logout -> logout
                .logoutUrl("/logout")
                .invalidateHttpSession(true)
                .clearAuthentication(true)
                .logoutSuccessHandler(oidcLogout))
            .build();
    }
}
```

**Prerequisites:** The OP supports RP-Initiated Logout and publishes `end_session_endpoint` in discovery (or a framework-supported configuration mechanism), the client registration has the correct `issuer-uri`/client, and `post_logout_redirect_uri` is registered/allowed at the OP. Use HTTPS and verify canonical URLs behind reverse proxies; `{baseUrl}` depends on the scheme/host seen by Spring.

**Behavior:** Spring processes local logout and then the logout success handler attempts to redirect the browser to the OP. Depending on OP/policy, the browser may be asked for confirmation or redirected back. To perform a POST to the OP instead of a GET redirect, Spring provides `FormPostRedirectStrategy` depending on version/capability; do not write custom JavaScript to send sensitive tokens unnecessarily.

**Note:** RP-Initiated Logout is a **request** to log out at the OP, not automatically a "guaranteed successful global logout". If the browser loses network connectivity, the user closes the tab, the OP rejects the request, or the product does not support the endpoint, the outcome may only be deleting session A. The application must still report the level actually achieved, rather than displaying "logged out everywhere" without proof.

### 8.3. OP-initiated / Back-channel logout

OIDC defines mechanisms for the OP to send notifications to RPs:

- **Front-channel logout:** The OP asks the browser to navigate/load RPs' logout endpoints; depends on browser/cookies and can be blocked by third-party cookie or frame/redirect policies.
- **Back-channel logout:** The OP sends a **Logout Token** over a server-to-server connection to the RP endpoint. The RP must verify the JWT logout token (issuer, audience, logout event, `iat`, `jti`/replay, `sid` or `sub` per profile), then locate and destroy matching local sessions.
- **Session Management:** Can track OP session changes through an agreed mechanism; reliability is impacted by browser behavior.

Spring Security supports OIDC back-channel logout depending on version, typically requiring dedicated configuration like `oidcLogout(...).backChannel(...)` and ensuring a registry maps OP sessions/users to local sessions. The default endpoint may look like `/logout/connect/back-channel/{registrationId}`, **not the user's local POST /logout**. Consult the exact Servlet documentation for your Spring Security version; do not use WebFlux code in a Servlet application.

**Do not equate OP `sid` with `HttpSession.getId()`:** `sid` is an IdP-side session identifier that the IdP may include in tokens; the backend needs a registry linking verified values. An OP logout event by `sub` may relate to multiple RP sessions for the same user/client, while an event by `sid` targets a specific OP session scope; all invalidation operations must be scoped by verified issuer/client.

**If an RP does not handle logout notifications:** The IdP having logged out does not mean session A disappears automatically. Failure behavior, retries, idempotency, ordering, HA registry, and session-store consistency must be tested.

## 9. SAML2: IdP Session, SP Session, and Single Logout

In SAML 2.0 Web Browser SSO:

```text
SP A: stores local HttpSession A
IdP: stores IdP-managed SSO session
AuthnRequest -> IdP
SAMLResponse/Assertion -> SP A ACS
SP A verifies -> creates Authentication + HttpSession A
```

A SAML assertion may contain an `AuthnStatement` and `SessionIndex`, but **`SessionIndex` is not the SP's session ID**. The IdP can use `SessionIndex` in SAML Single Logout to identify the session/subject to log out. Each SP must still locate and invalidate its **corresponding local session**.

### 9.1. Local Logout Differs from SAML SLO

- **Local logout:** SP A invalidates its own `HttpSession`; the IdP session usually remains. Revisiting A can trigger a new `AuthnRequest` and IdP SSO without requiring a password.
- **SP/RP-initiated SLO:** SP A sends a signed `saml2:LogoutRequest` per policy to the IdP. The IdP processes it, may notify other SPs, and returns a `LogoutResponse` to SP A. Error/partial completion scenarios must be fully handled.
- **IdP/AP-initiated SLO:** The IdP sends a `LogoutRequest` to SP A; the SP verifies signature/issuer/destination/correlation/profile, destroys the related session, and returns a `LogoutResponse`.
- **SLO unsupported:** If the IdP or SP lacks registered `SingleLogoutService`/signing credentials/matching binding, local logout **does not become SLO** merely by calling a regular logout endpoint.

**Spring Security SAML configuration example (as an independent alternative to OIDC):**

```java
package com.example.sessionlab;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlLogoutChoiceConfig {

    @Bean
    SecurityFilterChain samlWeb(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/signed-out", "/error").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())

            // Destroys only the SP session, does not call IdP SLO.
            .logout(logout -> logout
                .logoutUrl("/logout-local")
                .logoutSuccessUrl("/signed-out"))

            // Works properly only when both IdP and RP have SLO configured.
            .saml2Logout(saml -> saml
                .logoutUrl("/logout-federated"))

            .build();
    }
}
```

**Prerequisites before deploying SLO:** The `RelyingPartyRegistrationRepository` bean must have IdP metadata supporting `SingleLogoutService`, accurate SLO/ACS URLs, SP signing private key/certificate (when needed), and a trusted IdP signing verification certificate. `saml2Logout` does not generate signing keys or partner registrations for you. The sample class is part of a Spring Boot/Spring Security project with SAML2 dependencies; it is not a standalone compilable plain Java program.

The Spring Security reference has examples separating local `POST /logout` and federated `POST /saml2/logout`. The path `/logout-federated` above is **chosen by this article**; the URL where the IdP sends LogoutRequest to the SP is a different SLO protocol endpoint, typically `/logout/saml2/slo` per framework configuration/defaults. Do not use `permitAll("/logout/**")` or manually accept logout XML to delete arbitrary sessions.

### 9.2. Why Can SAML SLO Partially Fail?

- Another SP is offline or its SLO URL is unreachable.
- Other SPs still hold sessions but do not support SLO, or do not store the `NameID + SessionIndex` association properly.
- Mismatched Redirect/POST binding, signing, `Destination`, certificate rollover, or correlation.
- Browser closes the tab before front-channel SLO finishes; SameSite cookies/browser protections block request forwarding.
- An SP cluster cannot locate the matching session due to unsynchronized session store/registry.
- One application logs out while other applications' sessions remain active.

Therefore, do not promise "logging out of the system" guarantees deleting **all sessions on all applications/devices**. For high-risk requirements, verify using actual session metrics/revocation orchestration and define SLAs.

## 10. CAS: TGT/TGC Differ from Service Ticket and Application Session

Apereo CAS uses the terminology:

- **Ticket-Granting Ticket (TGT):** represents the SSO session on the CAS server; typically linked to a browser **Ticket-Granting Cookie (TGC)** on the CAS domain.
- **Service Ticket (ST):** a single-use credential for a specific `service`; CAS issues it when the user authenticates or has a valid TGT.
- **Application session:** after App A verifies the ST with CAS, App A creates its own local session. CAS does not directly manage each app's HttpSession.

Example:

```text
Browser -- GET /app-a/private --> App A
App A -- redirect /login?service=app-a --> CAS
Does CAS have valid TGT/TGC?
    Yes -> issue ST for App A, no password re-entry
    No  -> user login -> CAS creates TGT/TGC -> issues ST
Browser -- single-use ST --> App A callback
App A -- /serviceValidate --> CAS
App A -- creates HttpSession A
```

**App A local logout** can delete session A while TGT/TGC remains; the next visit causes CAS to issue a new ST without requiring a password. **CAS /logout** destroys the CAS SSO session/TGT, while local sessions of services **need a Single Logout mechanism** to be destroyed. CAS can send logout notifications; each CAS client/service must receive them, verify/correlate the ticket-session mapping, and perform proper invalidation. Do not treat CAS SLO as merely redirecting the user to `/logout` while skipping service-side cleanup.

Do not attempt to use ST as a long-lived session cookie, because STs are service-scoped and single-use. Nor are TGT/TGC the Spring app's `JSESSIONID`.

## 11. Requiring Password/MFA Re-entry: "SSO Active" Does Not Equal "Fresh Authentication"

A common source of confusion: a user SSO'd in the morning, and in the afternoon opens a money-transfer/admin-privilege-change feature. The application has a valid local session and IdP session, yet policy may require **fresh authentication** or step-up.

### 11.1. OIDC `prompt`, `max_age`, and `auth_time`

OIDC supports authorization request parameters:

- `prompt=login`: instructs the OP to **re-authenticate** the user, even if an OP session exists.
- `max_age=300`: requires that the authentication at the OP be no older than 300 seconds; if exceeded, the OP must perform active reauthentication. When `max_age` is sent, the returned ID Token must include `auth_time`.
- `prompt=none`: instructs the OP not to interact with the user; if unable to satisfy, return an appropriate error such as `login_required` or `interaction_required`.
- `acr_values` or `acr`/`amr` claims can describe authentication level/method per OP contract, **without automatically proving** the user satisfied the organization's MFA requirement unless mapped by policy.

**Note:** OIDC `max_age` refers to **authentication time at the OP**, not App A's HTTP idle timeout. `auth_time` is a timestamp signed/verified from the OP; do not trust `auth_time` from browser query strings. If the app needs proof that "the user just reauthenticated", it must force a new flow, check `auth_time`/`acr` per policy, and bind the result to the local session/authorization decision. Do not merely display a login screen without checking the returned ID Token.

### 11.2. SAML `ForceAuthn` and `IsPassive`

In a SAML `AuthnRequest`, the SP can request:

- `ForceAuthn="true"`: the IdP must directly re-authenticate the presenter rather than relying solely on a previous authentication session, per IdP profile/rules.
- `IsPassive="true"`: the IdP must not interact directly with the user; if passive authentication is impossible, it may return an appropriate error status.

SAML `AuthnStatement/AuthnInstant` and `AuthnContextClassRef` can provide signals about authentication time/context. Use them only after the assertion is verified and matched against signed policies. Like OIDC, **`ForceAuthn` does not automatically shorten an existing HttpSession**; a new round-trip must be initiated when policy requires it.

### 11.3. CAS `renew=true`

The CAS protocol supports the `renew=true` parameter to require authentication with primary credentials for a service request, instead of relying solely on an existing TGT/TGC SSO session. Application and enforcement must be verified in the actual CAS client/server; do not append the parameter arbitrarily to URLs without verifying the corresponding service-ticket validation.

**Do not assume SSO = continuous MFA.** The required assurance level must be decided based on the timing and context of the action, not merely whether the IdP session still exists.

## 12. Session/Browser Security Controls to Apply on Each Side

### 12.1. Cookies and Transport

- **`Secure`:** send session cookies only over HTTPS (excluding controlled development mechanisms/exceptions); production must use HTTPS for both SP and IdP.
- **`HttpOnly`:** restricts JavaScript from reading session cookies, reducing theft risk via certain XSS attacks; **does not replace XSS prevention**.
- **`SameSite`:** mitigates certain CSRF/cross-site cookie flows; requires testing OIDC redirects, SAML POST ACS, iframe/front-channel logout, and modern browsers.
- **Domain/Path:** restrict cookie scope; do not arbitrarily share `JSESSIONID` across multiple subdomains; prefer host-only cookies when possible.
- **HSTS/CSP:** apply policies appropriate to HTTPS/frontend; CSP can affect auto-submit POST forms and front-channel SLO.
- **Do not log or put session IDs in URLs/queries:** Session fixation and leaks via referrer/proxy are risks. Avoid `jsessionid` in URLs by disabling URL rewriting when possible.

### 12.2. Session Fixation and CSRF

Spring Security Servlet provides session fixation protection: after successful login, the framework can **change the session ID** (default `changeSessionId` on modern servlets). This is unrelated to changing the IdP SSO cookie. Do not disable `sessionFixation` to "keep the same JSESSIONID" across logins.

Logout is a state-changing operation, so use **POST with a CSRF token** for cookie-session applications. If GET `/logout` is allowed without CSRF, an external website could force users to log out unintentionally (logout CSRF). Protocol callback endpoints for OIDC/SAML have their own correlation/signature/state mechanisms; do not use them as an excuse to disable CSRF globally.

### 12.3. Session ID, Permissions, and Linked Accounts

After login, the local session holds the **Authentication for the specific account and mapped authorities**. If a user switches accounts at the IdP while App A still has local session A, App A's UI may continue displaying the old user A until logout/re-authentication per policy. Do not assume "the account just chosen at the IdP" automatically replaced the Authentication in the current session.

When an app has multiple IdPs/tenants, store issuer+subject (OIDC), or SAML issuer+stable identifier and registration, rather than auto-linking users by email. Tenant A's sessions must be bound to tenant A; logout/revocation must locate the exact sessions to avoid deleting sessions of other users/tenants.

**Permission revocation:** If `ROLE_ADMIN` is removed from a user at the IdP, an already-created session A may retain the old authorities. Sensitive policies may require re-evaluating permissions via a server-side store, session invalidation, deprovisioning events, or short lifetimes, rather than trusting the session until idle timeout.

## 13. Standalone Java 17 Example: Simulating Two Session States

The following example **only illustrates the state machine**; it does not perform HTTP, OIDC/SAML, token signing, cookies, or session storage. It demonstrates a browser having one IdP SSO session and two independent application sessions.

File `TwoSessionModelDemo.java`:

```java
public class TwoSessionModelDemo {

    static final class Browser {
        boolean idpSession;
        boolean appASession;
        boolean appBSession;

        String visitA() {
            if (appASession) {
                return "A: existing local session";
            }
            if (idpSession) {
                appASession = true;
                return "A: new local session via SSO";
            }
            return "A: login at IdP required";
        }

        String loginAAtIdp() {
            idpSession = true;
            appASession = true;
            return "A: login at IdP and new local session";
        }

        String visitB() {
            if (appBSession) {
                return "B: existing local session";
            }
            if (idpSession) {
                appBSession = true;
                return "B: new local session via SSO";
            }
            return "B: login at IdP required";
        }

        void localLogoutA() {
            appASession = false;
        }

        void endIdpSessionWithoutNotifications() {
            idpSession = false;
        }

        void localLogoutB() {
            appBSession = false;
        }
    }

    public static void main(String[] args) {
        Browser browser = new Browser();

        System.out.println("firstA=" + browser.visitA());
        System.out.println("login=" + browser.loginAAtIdp());
        System.out.println("firstB=" + browser.visitB());

        browser.localLogoutA();
        System.out.println("afterLocalLogoutA=" + browser.visitA());

        browser.endIdpSessionWithoutNotifications();
        System.out.println("afterIdpEndB=" + browser.visitB());

        browser.localLogoutA();
        browser.localLogoutB();
        System.out.println("afterBothLocalEndA=" + browser.visitA());
    }
}
```

Run on JDK 17+:

```bash
javac --release 17 TwoSessionModelDemo.java
java TwoSessionModelDemo
```

Deterministic stdout:

```text
firstA=A: login at IdP required
login=A: login at IdP and new local session
firstB=B: new local session via SSO
afterLocalLogoutA=A: new local session via SSO
afterIdpEndB=B: existing local session
afterBothLocalEndA=A: login at IdP required
```

**Explanation of each state:**

1. `firstA`: no session exists yet, so authentication at the IdP is required.
2. `login`: after authentication, the IdP session and App A session are created.
3. `firstB`: App B has no session yet but can SSO via the IdP, then creates a separate session B.
4. `afterLocalLogoutA`: A destroyed its local session; because the IdP still has a session, the next visit creates a new session A without needing a password.
5. `afterIdpEndB`: simulates **ending only the IdP session without sending/receiving logout notifications**; session B is still accepted.
6. `afterBothLocalEndA`: once both local sessions are cleared and the IdP session is gone, visiting A requires re-authentication.

**This is not a global SLO simulation.** In a real deployment with OIDC back-channel logout/SAML SLO and successful notifications, the IdP ending the session **can** cause A/B to be destroyed as well. The program intentionally tests only the case without propagation to highlight the two independent lifecycles.

## 14. Real Browser Testing: Observe Both Cookies and Server Sessions

Prepare two test applications A/B (or one test app with an IdP), HTTPS, a test IdP, and a non-sensitive user. Do not use production sessions/cookies/tokens for public debugging.

### 14.1. Procedure to Prove Local Logout Is Not IdP Logout

1. Clear prior test sessions in a **dedicated test profile**, without affecting your real work profile.
2. Visit a protected URL of A, redirect to the IdP, enter the test user's password, complete SSO.
3. Visit B in the same browser profile: verify the browser goes to the IdP and automatically completes SSO, creating a separate **B session cookie**.
4. At A, perform a **POST local logout** using a valid form/CSRF; verify App A's session is invalidated.
5. Do not log out of the IdP. Visit A's protected URL again: if OP SSO remains, the browser can log back in without showing a password prompt; **a new session ID A**.
6. Visit B: session B remains valid. Conclude that local logout of A has no authority to automatically delete session B/IdP session.

**Technical evidence:** The network waterfall shows redirect A→IdP→A, cookie A is rotated/invalidated; B's cookie/session is untouched by A's logout. Do not just look at UI text like "Hello user" or a name dropdown because the old page may be cached.

### 14.2. Procedure to Prove IdP Session Expiration Does Not Mean SP Expiration

1. Log in to A and B, record test session times, do not copy raw cookies into tickets.
2. In the test IdP, terminate the **SSO session** via the admin UI or a supported endpoint; do **not** send logout notifications to A/B in the isolated test (or use a test environment with SLO disabled).
3. GET a protected endpoint on A with the **still-valid** cookie A: it may still return 200.
4. Invalidate local session A: a subsequent GET to A will require IdP reauthentication; this is when the effect of the expired IdP session becomes visible.
5. Repeat with B; verify session B has its own policy.
6. Re-enable logout notifications in the test environment and test separately: if integrated properly, targeted SP sessions must be invalidated per policy.

### 14.3. Testing Cookies/SameSite/Different Browsers

- Within the same browser profile, open two tabs of A: they normally share session cookie A. Logging out in one tab forces new protected requests in the other tab to re-authenticate.
- Open A in an **incognito** window: separate cookie jar, does not automatically share A/IdP sessions from the normal profile, except for special OS/SSO mechanisms that must be tested separately.
- Open A on a phone or another browser: different IdP session and different session A; a local logout on machine 1 does not automatically log out machine 2.
- SAML HTTP-POST ACS can lose correlation if `SameSite=Lax` omits the session cookie on cross-site POST; inspect DevTools Cookies and response headers.
- When browsers block third-party cookies/iframes, front-channel logout and silent auth may fail; evaluate back-channel logout where appropriate.
- Test across browser restarts and session restore; do not rely on "closing the browser" as a way to revoke server sessions.
- Test behind actual HTTPS ingress/proxies because wrong scheme/host/Secure cookies easily cause redirect loops.

### 14.4. Outcome Matrix

| Local A State | IdP State | Request A | Typical Observed Behavior |
| --- | --- | --- | --- |
| ACTIVE | ACTIVE | GET resource A | Uses session A; no IdP round-trip needed |
| INACTIVE | ACTIVE | GET resource A | Redirects to IdP then may SSO again, creating a new session A |
| ACTIVE | INACTIVE | GET resource A | May still use session A; depends on revocation/reauth policy |
| INACTIVE | INACTIVE | GET resource A | Requires authentication at IdP or another allowed mechanism |
| ACTIVE | ACTIVE but step-up policy | GET sensitive action | Requires reauthentication/assurance per policy, even though session A exists |
| INACTIVE | ACTIVE, `prompt=login` | New OIDC login | OP must require reauthentication per OIDC |
| INACTIVE | ACTIVE, `max_age` not exceeded | New OIDC login | OP may reuse authentication evidence if policy allows |
| ACTIVE | OP sent valid logout notification and RP processed it | Request A after invalidation | Old session A must not be accepted |
| ACTIVE | OP logout notification failed | Request A | May still be allowed if no other revocation mechanism exists |
| B ACTIVE, A just locally logged out | IdP ACTIVE | GET B | B continues working under its own session |

**The word "may" is intentional:** Each application has its own session policy and each IdP has its own policy; outcomes depend on whether SLO/back-channel/absolute timeout/step-up is deployed. Testing must record the **effective configuration**, rather than guessing from product documentation.

## 15. Operational Issues and Symptom-Based Diagnostics

| Symptom | Possible Cause | Check/Fix |
| --- | --- | --- |
| "I clicked logout and logged right back in" | App A local logout succeeded but IdP session is still ACTIVE; redirected to IdP SSO | Check A→IdP→A network flow and new session ID. To also log out of the IdP, configure OIDC RP-initiated logout/SAML SLO appropriately |
| "After logout, clicking Back still shows the page" | Browser cache holds HTML, no new request checked yet | Reload and test APIs; protect sensitive data responses with appropriate Cache-Control |
| "Logout failed, cookie A unchanged" | GET /logout blocked by CSRF, wrong endpoint, session not invalidated | Use POST with CSRF, inspect LogoutFilter, session store, and Set-Cookie |
| "Logged out of IdP but App A can still view reports" | App A session still alive; missing or failing SLO/back-channel/revocation | Check session A, logout notifications, registry, and policy |
| "Logging out of A logs out B too" | Federated/global logout enabled, or improperly shared session store/cookie | Confirm business intent, distinguish local vs global, check notification scope |
| "Application keeps looping back to login page" | Session cookie not sent/stored, `SameSite`, Secure/HTTPS proxy, request correlation | Check cookies/headers/ACS/redirect URI and session ID; do not disable state/nonce/InResponseTo |
| "OIDC token expired but user can still use the app" | Token expiration differs from HttpSession timeout; authorized client may refresh | Check app session, refresh token policy, API tokens, and session lifetime |
| "IdP didn't prompt even though fresh MFA was required" | Missing `prompt=login`/`max_age` or not checking `auth_time`/`acr` | Design reauthentication flow, verify validated claims and assurance policy |
| "SAML `ForceAuthn` didn't change the local session" | ForceAuthn applies only when creating a new AuthnRequest; existing local session is still used | Force a proper round-trip and update security context after re-authentication |
| "CAS /logout was called but app stayed logged in" | TGT destroyed but CAS SLO notification/client did not destroy local session | Check CAS client Single Logout support and ticket→session store |
| "SAML SLO sometimes destroys A, sometimes doesn't" | SessionIndex/NameID, SLO binding/signature, cache, HA, or browser closed tab | Check verified LogoutRequest/Response, session mapping, and timeouts |
| "Got 401 on API, yet website stays logged in" | API Access Token expired/wrong audience; web session is separate | Check resource server JWT/opaque token, refresh, and session policy |
| "User removed from group, app still allows access" | Spring session stored authorities at login, not refreshed/revoked | Sync deprovisioning and perform dynamic permission checks on sensitive actions |
| "Safari/Chrome privacy breaks silent login/logout" | Third-party cookie/iframe policies, SameSite, IdP tracking protections | Try top-level redirects and back-channel where appropriate; do not disable browser protections |
| "Logged out account A but came back as account B" | Another user's OP session, account chooser/remembered IdP login, stale local session | Check issuer/sub/NameID, browser profiles, IdP user selection, and local account mapping |

### 15.1. Decision Tree for Technical Support

```text
User says "cannot log out"
  |
  +-- Was a valid POST local logout sent? (CSRF, status, route)
       |
       +-- No  -> fix UI/logout endpoint
       |
       +-- Yes -> was session A on the server invalidated?
                    |
                    +-- No  -> fix session store/filter/handler
                    |
                    +-- Yes -> did the browser redirect to the IdP?
                                 |
                                 +-- Yes -> IdP SSO remains, A created new session
                                 |          -> expected local vs federated logout?
                                 |
                                 +-- No  -> check cache/page/other sessions
  |
  +-- User wants "log out everywhere"?
       |
       +-- Choose and verify RP-initiated/SLO/back-channel,
           check participating RPs, sessions on other devices,
           processing timing, and partial failures.
```

Logs should record `requestId`, issuer/registration, safe-reference local account ID, login/logout event type, session lifecycle action, IdP/logout-correlation status, and outcome; **do not log raw session cookies, ID Tokens, Access Tokens, SAMLResponses, CAS TGTs/STs, or refresh tokens**.

## 16. UX Design: Label the Logout Scope Accurately

The logout button must accurately describe its effect:

- **"Sign out of this application"** when invalidating only the local app session.
- **"Sign out of SSO account"** when requesting OP/IdP logout, while still evaluating notifications and actual state.
- **"Sign out of all devices"** only when the system actually has a session/device inventory and corresponding revocation mechanism, not by relying on a browser redirect to the IdP.
- The success page must not promise "all applications signed out" when only local logout of A is proven.
- When IdP SSO remains active, display a clear message: revisiting a protected page may automatically log back in if the IdP session is still active.
- On shared devices, recommend logging out of both the application and IdP per policy, closing the browser profile, and not saving credentials/remember-me; **do not** treat clearing browser history as revoking a session.

Separating "app logout" and "SSO logout" buttons can be useful in multi-application environments: users may want to leave one application while continuing work in another. However, when access risk is high, policy may prioritize centralized logout/revocation. UX must reflect that policy.

## 17. Production Checklist for Spring Security Federation

- [ ] System diagrams distinguish **A HttpSession**, **B HttpSession**, and **IdP SSO session**; do not merge them via arbitrary cookies/domains.
- [ ] Idle timeout/absolute timeout/revocation policies are documented **for each party**, without equating ID Token exp = app session timeout.
- [ ] Spring Security login properly verifies OIDC `iss/aud/nonce/state` or SAML issuer/signature/audience/recipient/InResponseTo before creating local Authentication.
- [ ] SP cookies have `Secure`, `HttpOnly`, appropriate Domain/Path, and SameSite tested against OIDC/SAML/SSO callbacks.
- [ ] Login has session fixation protection; local logout invalidates the server session rather than merely deleting cookies with JavaScript.
- [ ] Logout POST has a CSRF token; do not turn GET or open redirects into dangerous logout endpoints.
- [ ] UX distinguishes local logout from federated logout; actual outcomes and partial failure cases are tested.
- [ ] For OIDC RP-initiated logout, the OP supports `end_session_endpoint` and the post-logout URI is registered; browser redirects and OP confirmation are tested.
- [ ] For OIDC back-channel logout, the RP verifies Logout Tokens for issuer/audience/event/replay and locates the right local sessions; appropriate registry/HA exists.
- [ ] For SAML SLO, the IdP has `SingleLogoutService`, SP signing credentials, request/response validation, and proper session correlation.
- [ ] For CAS, client/server handle SLO notifications and ticket/session mapping properly; TGT/TGC are not confused with ST/local cookies.
- [ ] Fresh authentication/MFA/step-up policies exist based on `auth_time`/`ForceAuthn`/`renew` timing and business permissions.
- [ ] Session revocation mechanisms exist when a user is locked, loses critical groups, or an account/IdP is compromised; do not wait for IdP cookies to expire.
- [ ] Tested all scenarios: local logout→silent SSO, IdP timeout→A still active, multi-tab, incognito, browser restart, SAML POST SameSite, HTTPS proxy, and cluster.
- [ ] Logs/metrics exist for login/logout/session invalidation without logging secrets or unnecessary PII.
- [ ] Operations runbooks include a diagnostic path for "local session was not deleted" versus "new local session was just created via IdP SSO".

**Conclusion:** A user can simultaneously hold **each RP/SP's application session** and an **IdP-managed SSO session**. The local session governs logged-in requests at the application; the IdP session governs the ability to obtain **new login proof** at an RP when the browser is sent to the IdP. Destroying one session **does not automatically destroy** the other. Achieving "coordinated logout" requires logout protocols/notifications, per-RP session handling, risk bounds, and browser/IdP compatibility testing. Achieving "fresh authentication" requires a reauthentication/step-up flow with evidence verification, not merely waiting for sessions to expire.

## 18. References

1. [Spring Security — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html) — HttpSession, SecurityContext, session fixation, concurrency, and session policy.
2. [Spring Security — Logout (Servlet)](https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html) — LogoutFilter, local logout, CSRF, and cleanup.
3. [Spring Security — OIDC Logout (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/logout.html) — local logout, `OidcClientInitiatedLogoutSuccessHandler`, RP-initiated/back-channel logout.
4. [Spring Security — SAML 2.0 Single Logout](https://docs.spring.io/spring-security/reference/servlet/saml2/logout.html) — RP-initiated/AP-initiated SLO, signing credentials, SessionIndex, and logout filters.
5. [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html) — `prompt`, `max_age`, `auth_time`, ID Token, authentication context.
6. [OpenID Connect RP-Initiated Logout 1.0](https://openid.net/specs/openid-connect-rpinitiated-1_0.html) — `end_session_endpoint`, `id_token_hint`, `post_logout_redirect_uri`, RP/OP responsibilities.
7. [OpenID Connect Back-Channel Logout 1.0](https://openid.net/specs/openid-connect-backchannel-1_0.html) — Logout Token, `sid`/`sub`, signatures, and replay protection.
8. [OASIS SAML 2.0 Profiles](https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf) — Web Browser SSO, `ForceAuthn`, and Single Logout.
9. [Apereo CAS — Logout & Single Logout](https://apereo.github.io/cas/7.3.x/installation/Logout-Single-Signout.html) — distinguishing CAS SSO sessions from application sessions and SLO notifications.
10. [Apereo CAS — CAS Protocol Specification](https://apereo.github.io/cas/development/protocol/CAS-Protocol-Specification.html) — ST/TGT/TGC, `renew`, and `/logout`.
