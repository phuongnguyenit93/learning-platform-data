# Distinguishing Application Logout, OIDC Logout, and Broker-Backed IdP Logout

## 1. Goal and Context

In a **Spring Security – federation** system, a Java application can authenticate users via OpenID Connect (OIDC) without **connecting directly to the originating identity system**. Instead, an **identity broker** sits between the application and the upstream Identity Provider (IdP). For example, a Spring Boot application uses OIDC to sign in via Keycloak, while Keycloak uses OIDC, SAML 2.0, or another federation protocol to authenticate the user at the enterprise IdP.

When the user clicks **Sign out**, at least three distinct entities must be distinguished:

1. **Application session** — the session/cookie and SecurityContext at the Spring Boot Relying Party (RP).
2. **OIDC Provider/broker session** — the SSO session of the OpenID Provider (OP) that the application directly trusts, e.g., a Keycloak realm.
3. **Upstream IdP session** — the login session at the identity system behind the broker, e.g., a partner's OIDC/SAML IdP.

Beyond these three sessions, another dimension cannot be ignored: **OAuth access/refresh tokens** and sessions of **other RP applications** signed in through the broker. Ending one browser session **does not automatically guarantee** every access token has been revoked or every other RP has cleared its session.

This lesson belongs to the **OIDC and Brokering** group. After studying it, you should be able to:

- Distinguish **local application logout**, **OIDC RP-Initiated Logout**, **OIDC OP-initiated front-channel/back-channel logout**, and **upstream IdP logout**.
- Explain why a user clicks logout in an app yet **the next login still SSOs without asking for a password**.
- Configure Spring Security with **OidcClientInitiatedLogoutSuccessHandler** and **end_session_endpoint** in the right place.
- Understand that the broker is an **OP toward the application**, yet an **RP/SP toward the upstream IdP**; therefore logout must traverse **two distinct trust relationships**.
- Distinguish protocol logout from **token revocation**, expiration, SAML Single Logout, and "sign out everywhere" policies.
- Design validation for **state, id_token_hint, post_logout_redirect_uri, logout_token, iss, aud, sid, sub**, plus replay and cross-session logout protection.
- Build a test matrix, honest UI messages, and operational runbooks regarding logout scope.

**Core principle:** the word "logout" has no single universal meaning across every system. One logout step affects only **the sessions, tokens, and partners that component has authority over and has a configured, supported, and executed notification protocol for**.

## 2. Three-Tier Diagram and Role Relationships

~~~text
                   Browser / End User
                           |
                           v
                  +-------------------+
                  | Spring Boot Web   |
                  | App (RP)          |
                  | APP session A     |
                  +-------------------+
                           |
                           | OIDC Authorization Code
                           | issuer = broker OP
                           v
                  +-------------------+
                  | Identity Broker   |
                  | Keycloak / OP     |
                  | Broker session B  |
                  +-------------------+
                           |
                           | OIDC, SAML, or other
                           | federation protocol
                           v
                  +-------------------+
                  | Upstream IdP      |
                  | Org/Partner IdP   |
                  | Upstream session C|
                  +-------------------+

              Broker OP also serves:
                 RP 2 / RP 3 / mobile / API
                 (each with its own session or tokens)
~~~

Two relationships have **reversed roles**:

| Relationship | Party Requesting Auth | Party Issuing Identity | Who Does the App Trust? |
| --- | --- | --- | --- |
| **Spring app ↔ broker** | Spring app is **OIDC RP/client** | Broker is **OIDC OP** | App trusts **broker's issuer/JWKS**, never trusting upstream tokens directly |
| **Broker ↔ OIDC upstream IdP** | Broker is **OIDC RP/client** | Upstream is **OIDC OP** | Broker verifies upstream issuer/JWKS |
| **Broker ↔ SAML upstream IdP** | Broker is **SAML SP** | Upstream is **SAML IdP** | Broker verifies upstream SAML signature/metadata |

User identifiers, session IDs, and tokens are **not automatically identical** across the three tiers. An ID Token issued to the app by the broker carries **iss=broker**, **aud=app's client ID**. If upstream issued an ID Token to the broker, that token carries **iss=upstream** and **aud=broker's client ID at upstream**. The app **must never pass the upstream ID Token as `id_token_hint` when logging out at the broker**; that token belongs to a different relationship.

### 2.1. Visual State Matrix

Assume all three sessions are initially active:

| Action | App Session A | Broker Session B | Upstream Session C | Other RPs on Broker |
| --- | --- | --- | --- | --- |
| **Local logout only** | Closed | **May remain** | **May remain** | May remain |
| **OIDC RP-Initiated Logout at broker, accepted by OP** | Closed | Closed per OP | **Not guaranteed closed** | Depends on whether OP notifies and RP receives/handles |
| **Broker with working upstream logout** | Closed | Closed | May close when upstream completes successfully | Depends on notification mechanism |
| **User logs out directly at upstream** | **May remain** | **May remain** unless notified by upstream | Closed | May remain |
| **Upstream sends valid back-channel; broker processes and notifies downstream** | May close via downstream notification | Closed | Closed | May close |

"May" in the table indicates **implementation dependency**, not a flaw in OIDC. Tiers interlock only when a **chain of logout events is supported, trusted, delivered, and processed successfully**.

## 3. Tier 1 — Application Logout (Local Logout)

**Local logout** means the Spring Boot application terminates the **local login session**: clearing or invalidating the SecurityContext and associated HttpSession/session cookie, purging sensitive data in application state, and navigating to a confirmation page.

~~~text
Browser -> Spring POST /logout
  -> Spring Security LogoutFilter
  -> SecurityContextLogoutHandler
  -> clear Authentication/SecurityContext
  -> invalidate HttpSession
  -> local logout success URL

Does not automatically send OIDC end-session request to broker.
Does not automatically send SAML LogoutRequest to upstream IdP.
~~~

Spring Security defaults to Servlet logout via **POST /logout** when CSRF is enabled. Local logout operates independently of whether you use form login, OAuth2 Login, or OIDC Login. Configuring only a success URL triggers **no standard OIDC mechanism to end the OP-side SSO session**.

### 3.1. Resulting User Experience

After local logout, the user visits a protected page again. The application redirects them to the broker. If **broker session B is still valid**, the broker can issue a new authorization code/ID Token **without prompting for login**. If the broker has to visit the upstream IdP and **upstream session C is still alive**, upstream can also SSO silently.

This does not necessarily mean "Spring Security logout failed". The local session may genuinely have been destroyed properly, while **sessions at other systems remain active**.

### 3.2. Spring Security Local-Only Example

This is a **configuration class for a Spring Boot 3.x / Spring Security Servlet project** with the OAuth2 Client dependency; it will not compile/run with pure JDK without Spring:

~~~java
package com.example.portal;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class LocalLogoutConfig {
    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/signed-out", "/assets/**")
                .permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .logout(logout -> logout
                .logoutUrl("/logout")
                .invalidateHttpSession(true)
                .clearAuthentication(true)
                .logoutSuccessUrl("/signed-out"));
        return http.build();
    }
}
~~~

**Result:** the app performs local logout and redirects to **/signed-out**. Without **OidcClientInitiatedLogoutSuccessHandler**, do not expect the broker OP session to terminate. **/signed-out** must have a corresponding controller/static page or route; the example illustrates security config only and creates no page.

Key notes:

- Never turn **GET /logout** into an unprotected state-changing endpoint just for button convenience.
- Distributed session backends / Spring Session must propagate session deletion.
- If an SPA keeps state in memory/localStorage, the app must clear client-side data per policy; invalidating **HttpSession** does not automatically wipe JavaScript caches.
- If the app is an API using **Bearer JWTs** with no server session, browser "local logout" does not automatically invalidate JWTs held elsewhere.
- Logout is a security event; never log session cookies, ID Tokens, access/refresh tokens, or PII on debug pages or in logs.

## 4. Tier 2 — OIDC Logout at the Broker (RP-Initiated Logout)

In the **Spring app ↔ broker OP** relationship, OpenID Connect RP-Initiated Logout 1.0 lets the **RP ask the OP to log the user out** by redirecting the browser to the **OP's Logout Endpoint**, typically published in **Discovery metadata** under **end_session_endpoint**.

~~~text
User clicks Sign out in Spring app
     |
     v
Spring Security runs local logout
     |
     v
302 -> broker end_session_endpoint
       id_token_hint / client_id (per policy)
       post_logout_redirect_uri (if callback desired)
       state (if used)
     |
     v
Broker identifies user/OP session, applies policy and confirmation if needed
     |
     +-> Ends broker SSO session
     +-> May send front/back-channel logout to downstream RPs
     +-> May initiate upstream logout per broker/IdP config
     |
     v
Browser returns to valid post_logout_redirect_uri, if OP allows
~~~

**Important:** **redirecting to end_session_endpoint** means **sending a logout request**, not proof that the OP closed the session, sibling RPs received notifications, or the upstream IdP logged out. Observe responses, session/token state, and callbacks to confirm actual scope.

### 4.1. RP-Initiated Logout Parameters

| Parameter | Meaning | Notes |
| --- | --- | --- |
| **end_session_endpoint** | Logout URL published by OP via Discovery | URL must come from trusted issuer/config, never user-supplied |
| **id_token_hint** | ID Token **previously issued by OP to this RP** | **RECOMMENDED**; helps OP identify the session/client |
| **client_id** | RP's Client ID at the OP | May be needed without `id_token_hint`; OP sets policy |
| **post_logout_redirect_uri** | URL where RP wants OP to return browser after logout | Must **match an exact URL registered** at the OP |
| **state** | Opaque value binding logout request and callback | If sent, verify on return; prevents mix-up/cross-request attacks |
| **logout_hint** | OP-specific user hint | Does not replace trust; should contain no secrets |
| **ui_locales** | OP UI locale, if supported | Affects UX only, not authentication |

Per spec, **post_logout_redirect_uri** cannot be an arbitrary URL. The OP must never redirect to a URL that fails to match a registered value. When `post_logout_redirect_uri` is provided without **id_token_hint**, the OP needs another way to validate the redirect target and must not skip verification.

**Do not confuse:** OIDC **redirect_uri** for **login** and **post_logout_redirect_uri** for **logout** have separate roles and allowlists. Never pass a browser-supplied **returnTo** or **next** parameter straight as `post_logout_redirect_uri`.

### 4.2. Example Broker Discovery Metadata

**Illustrative** JSON example retaining only key fields:

~~~json
{
  "issuer": "https://broker.example.test/realms/enterprise",
  "authorization_endpoint":
    "https://broker.example.test/realms/enterprise/protocol/openid-connect/auth",
  "token_endpoint":
    "https://broker.example.test/realms/enterprise/protocol/openid-connect/token",
  "jwks_uri":
    "https://broker.example.test/realms/enterprise/protocol/openid-connect/certs",
  "end_session_endpoint":
    "https://broker.example.test/realms/enterprise/protocol/openid-connect/logout"
}
~~~

This is **not a complete Discovery document**; URLs and realm are examples. Real apps fetch **/.well-known/openid-configuration** from a managed issuer URI, validate the configured issuer, and use live endpoints. Never discover `end_session_endpoint` from a browser-supplied domain, and **never hardcode one vendor's path** assuming all OIDC OPs share it.

### 4.3. Wire-Level Request Example

~~~text
GET https://broker.example.test/realms/enterprise/protocol/openid-connect/logout
    ?id_token_hint=<OIDC-ID-Token-issued-by-broker>
    &post_logout_redirect_uri=https%3A%2F%2Fportal.example.test%2Fsigned-out
    &state=<opaque-random-logout-state>
~~~

This is a **structural example URL**; bracketed values are placeholders, not real tokens. Token and state values must be properly URL-encoded. An ID Token is a sensitive credential: passing it in a URL increases exposure in browser history, access logs, and proxy telemetry; minimize leakage and follow the OP's GET/POST capabilities. **Never log the full query string containing `id_token_hint`**.

If supported by the OP and configured in the framework, RP-Initiated Logout can also use POST per spec/config; never assume an arbitrary POST to a login URL logs out.

## 5. Configuring a Spring Boot OIDC Client with a Broker

Example **application.yml** in Spring Boot 3.x where the app uses **OIDC Authorization Code flow** with the broker:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          broker:
            provider: broker
            client-id: "portal-web"
            client-secret: "${BROKER_OIDC_CLIENT_SECRET}"
            authorization-grant-type: authorization_code
            scope:
              - openid
              - profile
              - email
        provider:
          broker:
            issuer-uri: "https://broker.example.test/realms/enterprise"
~~~

**Explanation:**

- **registration.broker** is the local Spring Security **ClientRegistration** to sign in via the broker OIDC OP.
- **client-id=portal-web** is the client ID the broker assigned to **the app**, not the client ID the broker uses toward the upstream IdP.
- **issuer-uri** must be the **broker issuer**, because the broker is the OP issuing ID Tokens directly to the app. Never put the upstream issuer here if the app does **not** authenticate directly with upstream.
- **scope: openid** distinguishes OIDC login from plain OAuth2; Spring Security creates an **OidcUser** and retains the broker's ID Token.
- The client secret comes from an environment variable here for illustration; in production use a secret manager, keystore, or protected volume, and never commit literal secrets to Git. Note that process environments also carry exposure risk via debug tooling.
- Spring Security reads provider metadata for discovery endpoints, including **end_session_endpoint** when the OP advertises RP-Initiated Logout.

The app must also register both its **login redirect URI** and **Valid Post Logout Redirect URI** at the broker. Passing OAuth2 login **does not prove** the broker permits post-logout redirection.

## 6. Spring Security Servlet: OidcClientInitiatedLogoutSuccessHandler

Spring Security provides **OidcClientInitiatedLogoutSuccessHandler** for RP-Initiated Logout. It is intended for an **OIDC RP application connected directly to the broker**. Never invoke upstream APIs from an application handler when a broker sits in between, because the app owns neither the broker's upstream session nor client context.

Example **SecurityConfig.java** in a Spring Boot app with **spring-security-oauth2-client**:

~~~java
package com.example.portal;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.oidc.web.logout.OidcClientInitiatedLogoutSuccessHandler;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            ClientRegistrationRepository clientRegistrations)
            throws Exception {

        OidcClientInitiatedLogoutSuccessHandler oidcLogout =
            new OidcClientInitiatedLogoutSuccessHandler(
                clientRegistrations);

        oidcLogout.setPostLogoutRedirectUri(
            "{baseUrl}/signed-out");

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/signed-out", "/assets/**")
                .permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .logout(logout -> logout
                .logoutUrl("/logout")
                .invalidateHttpSession(true)
                .clearAuthentication(true)
                .logoutSuccessHandler(oidcLogout));

        return http.build();
    }
}
~~~

**This is a Spring Boot configuration class**; it cannot run standalone with `javac` without dependencies, broker metadata, client registration, secrets, and a **/signed-out** page. Check API details against your **running Spring Security version**.

Per Spring Security docs:

- **OidcClientInitiatedLogoutSuccessHandler** takes **ClientRegistrationRepository** to resolve the OIDC client's OP/metadata.
- **setPostLogoutRedirectUri("{baseUrl}/signed-out")** specifies the callback target; the **{baseUrl}** template resolves from the scheme/host/port/path observed by the app.
- By default the handler performs a **GET** HTTP redirect to the OP logout URL; newer releases offer **FormPostRedirectStrategy** if POST is needed and supported by the OP/framework.
- For OIDC logout to fire properly, Authentication must be an **OIDC login**, and the OP must publish **end_session_endpoint** for a valid client registration. If plain OAuth2 login lacks an OIDC ID Token or the OP omits the endpoint, design an explicit **local logout fallback**; never assume the handler is guaranteed to call the OP.

**URL management note:** behind an ingress or reverse proxy, ensure **{baseUrl}** resolves from the trusted public URL. If it generates **http://internal-node:8080/signed-out**, the OP will reject `post_logout_redirect_uri` or redirect to the wrong host. Never blindly trust browser-supplied `Host`/`X-Forwarded-*` headers.

### 6.1. The OIDC Client-Initiated Handler Is Not a Back-Channel Receiver

The class above **initiates** logout from the app to the broker. It **does not set up a Logout Token receiver endpoint** for OIDC Back-Channel Logout. If your product needs the broker to notify the app **when the user signs out from another RP, the IdP, or an admin console**, configure **front-channel/back-channel** support per your Spring Security/adapter capabilities with a spec-compliant endpoint.

Never conclude that **using OidcClientInitiatedLogoutSuccessHandler** means the app automatically hears when the upstream IdP logs out in another tab.

## 7. Tier 3 — Logging Out the Upstream IdP Behind the Broker

The broker plays two roles: **OP toward the app**, yet **RP or SP toward upstream**. When the app sends RP-Initiated Logout to the broker, the broker must decide **whether it should and can propagate a logout request to the upstream IdP**.

~~~text
App --(OIDC logout)--> Broker OP
                       |
                       +-- clears broker session
                       |
                       +-- depending on config:
                           |
                           +-- OIDC upstream:
                           |      RP-Initiated Logout / Logout URL
                           |      or back-channel when IdP supports
                           |
                           +-- SAML upstream:
                           |      SAML Single Logout (SLO)
                           |
                           +-- Social/custom IdP:
                                  may lack logout API /
                                  no session mapping
~~~

**There is no universal OIDC rule forcing every broker to log out of every upstream IdP.** Behavior depends on product, version, broker config, IdP type, transport, browser cookie lifetimes, logout protocol support, and user consent.

### 7.1. OIDC Upstream

The broker can configure a **Logout URL** or use the upstream OP's discovery to run RP-Initiated Logout. In this leg:

- **Broker** is the upstream OIDC RP.
- **Upstream IdP** is the OP performing logout.
- **The ID Token hint upstream expects** is the ID Token **issued by upstream to the broker**, not the ID Token **issued by the broker to the app**.
- **post_logout_redirect_uri** (if used) must be the **broker's registered URI at upstream**, not the app's final URL.
- **Back-channel logout** may be used if supported by both broker and upstream IdP with proper session mapping.
- Do not assume the broker retains the upstream ID Token after clearing its session; check which tokens and logout contexts your provider/broker stores.

### 7.2. SAML Upstream

If the broker uses SAML 2.0 to authenticate at the upstream IdP, logout can use **SAML Single Logout**:

~~~text
Broker (SAML SP) -> upstream (SAML IdP):
  LogoutRequest ID / NameID / SessionIndex
upstream -> Broker:
  LogoutResponse InResponseTo = request ID
~~~

SAML SLO depends on **`SingleLogoutService` endpoints, signing credentials, retained `NameID`/`SessionIndex`, bindings, signatures, and correlation state**. It differs completely from OIDC `end_session_endpoint`; never send an OIDC ID Token hint to a SAML SLO endpoint.

If the upstream IdP supports SAML login **without SLO**, the broker cannot "invent" a universal logout call. Proceed with clearing broker/local sessions and state clearly that the upstream session may remain, optionally offering an approved provider logout link/procedure.

### 7.3. Keycloak Identity Brokering Example

Keycloak can act as a broker between an OIDC client app and upstream OIDC/SAML IdPs. Keycloak administration documentation covers **Identity brokering** and **OIDC Logout**. For upstream OIDC, configuration includes an optional **Logout URL** and **Backchannel Logout** capabilities on supported providers. Keycloak also exposes broker/upstream logout options depending on IdP type and version.

**Never claim "Keycloak always logs out upstream" or "Keycloak never logs out upstream".** Check your exact version and provider configuration: Logout URL, broker-initiated logout behavior, back-channel mode, session mapping, and whether upstream actually receives and processes it.

Also distinguish two groups of Keycloak settings:

- **Application client in the broker realm**: Valid Post Logout Redirect URIs, Front-Channel Logout, Backchannel Logout URL, session required, client session behavior.
- **Upstream Identity Provider in the broker realm**: Identity Provider alias/type, Logout URL/SLO URL, Backchannel Logout, upstream token storage/retrieval, logout propagation options.

Client settings **do not automatically substitute** for upstream identity provider settings, or vice versa.

### 7.4. Upstream IdP May Retain an SSO Session Even After Browser Visits Broker Logout

This explains a common symptom:

~~~text
App local logout -> broker logout succeeds
Upstream IdP session remains alive

User visits app again -> app redirects to broker
Broker has no session -> broker redirects to upstream IdP
Upstream IdP still has SSO cookie -> authenticates silently
Broker creates new session -> app creates new session
~~~

A quick re-login right after logout **does not necessarily prove broker logout never ran**; upstream may simply have minted a **brand-new broker session** from its still-valid upstream SSO session.

To diagnose accurately, inspect sessions, cookies, and telemetry at **each tier** instead of judging merely by "the user wasn't prompted for a password".

## 8. OP-Initiated Logout: From the Broker Down to Other Applications

When broker session B closes, the broker can notify **other Relying Parties** sharing that broker. OIDC defines multiple mechanisms:

| Mechanism | Notification Direction | Core Payload | Key Limitation |
| --- | --- | --- | --- |
| **RP-Initiated Logout 1.0** | App RP -> Broker OP | Browser hits `end_session_endpoint` | Only requests OP logout |
| **Front-Channel Logout 1.0** | Broker OP -> RP via browser | RP receives GET at `frontchannel_logout_uri`, possibly with `iss`/`sid` | Depends on iframes, cookies, and cross-site browser rules |
| **Back-Channel Logout 1.0** | Broker OP -> RP server-to-server | HTTP POST `logout_token` JWT to `backchannel_logout_uri` | Requires endpoint, JWT validation, and session mapping |
| **OIDC Session Management 1.0** | Browser RP polls OP session state | RP detects SSO state changes | Depends on browser, cookies, and integration |
| **Local logout** | User -> single application | Clears that app's session/cookie | Does not touch broker/IdP without protocol |

Never assume any mechanism is active merely because an OP supports OIDC login. **Login, logout, and notification endpoints are distinct capabilities** that must be registered and tested separately.

### 8.1. Front-Channel: Browser-Dependent

OIDC Front-Channel Logout lets the OP use the user agent to load each RP's **`frontchannel_logout_uri`**, typically inside hidden iframes. The OP may pass **`iss`** and **`sid`** so the RP knows which session to terminate; the RP should validate session mapping appropriately.

Limitations:

- Third-party cookie restrictions or **`SameSite`** can stop the RP from reading its session cookie inside the iframe.
- **Content Security Policy (CSP)** or `X-Frame-Options` can block framing.
- Closing the browser/tab before iframes finish executing drops notifications.
- BFF RPs with `HttpOnly` cookies may be unable to identify the session inside a blocked third-party iframe.
- Never treat "broker logout page rendered" as proof every logout iframe succeeded.

The OIDC Front-Channel Logout spec notes browser blocking of third-party content and observes that back-channel logout avoids those browser limitations.

### 8.2. Back-Channel: Server-to-Server Notification

OIDC Back-Channel Logout 1.0 lets the OP send an HTTP POST to an RP's registered **`backchannel_logout_uri`**. The **`application/x-www-form-urlencoded`** request body contains **`logout_token`**, a **signed JWT**.

~~~text
POST /oidc/backchannel-logout HTTP/1.1
Content-Type: application/x-www-form-urlencoded

logout_token=<signed-jwt-from-trusted-broker>
~~~

This is a **protocol illustration**, not an HTTP request with a valid token.

Back-channel works even if the browser closed or blocks third-party cookies, yet it is still not an "absolute guarantee":

- The OP must be configured to send notifications.
- The RP must expose a reachable endpoint and **verify the JWT**.
- The RP must map **`iss+sid/sub`** to the **exact local session** to invalidate.
- The server must handle retries, duplicate deliveries, expirations, replays, and distributed session sync.
- Delivery can fail due to network or config issues; implement metrics and retry policies.

**A `SecurityFilterChain` with `oauth2Login()` does not automatically provide a complete back-channel logout endpoint and session registry**. Support depends on adapters, Spring Security versions, or custom wiring; verify actual APIs and capabilities.

## 9. Logout Token: Neither ID Token Nor Access Token

An OIDC Back-Channel Logout Token is a purpose-built JWT. **Illustrative claims** example:

~~~json
{
  "iss": "https://broker.example.test/realms/enterprise",
  "aud": "portal-web",
  "iat": 1760000000,
  "exp": 1760000300,
  "jti": "logout-event-123",
  "sid": "broker-session-7",
  "events": {
    "http://schemas.openid.net/event/backchannel-logout": {}
  }
}
~~~

This JSON is an **illustrative JWT claims payload** with no JOSE header/signature and is **not a valid Logout Token to send**. `iat`/`exp` values merely illustrate Unix timestamps rather than real operational times.

Essential checks per **OpenID Connect Back-Channel Logout 1.0**:

1. Token is a **validly signed** JWT using trusted OP/JWKS keys for the exact issuer; **reject `alg=none`**.
2. Verify **`iss`** matches the registered trusted broker OP—not the upstream issuer if the RP directly trusts the broker.
3. Verify **`aud`** contains the receiving RP's client ID.
4. Check **`iat`** and **`exp`** when present, enforcing clock skew and expiry per spec/policy.
5. Must contain **`events`** with exact key **`http://schemas.openid.net/event/backchannel-logout`** mapped to an object.
6. Must contain at least one of **`sub` or `sid`**, and may contain both.
7. **Must NOT contain `nonce`**. Distinguish ID Tokens from Logout Tokens to prevent token-type confusion.
8. Include **`jti`** as required and enforce duplicate/replay protection within a reasonable window.
9. Map **`sid`** within issuer/client/session scope; `sid` is meaningful only in the OP's context.
10. Locate the exact local session and invalidate the session/tokens per policy; handle repeated deliveries idempotently.

**Never Base64-decode a JWT payload and log out merely because `sid` matches.** An attacker could forge raw JSON and force-logout another user's session if signature, `iss`, `aud`, or event type checks are skipped.

In a brokered system, there is another validation boundary: **the broker receiving an upstream back-channel logout token** must verify **upstream issuer/JWKS and the broker's client ID**, and then the broker **issues its own notifications to downstream RPs** if policy and capabilities permit. Apps **should not directly process upstream logout tokens** when they are clients of a broker unless explicitly designed and reviewed.

### 9.1. OIDC sid Differs from App Session ID

- OIDC **`sid`** represents an OP-assigned session identifier; it may differ between broker and upstream.
- **`JSESSIONID`** is a Java web app's HTTP session cookie, not an OIDC `sid`.
- **`sub`** is the issuer's subject; unique only within that exact **issuer** and client/session scope per profile.
- **`jti`** identifies the **event JWT** for replay prevention, not a session ID.
- A user may hold multiple browser/device sessions; logout by `sid` may target one session, whereas logout by `sub` without `sid` may target multiple sessions per policy.
- Never use email to find and terminate sessions across all tenants when a single OP sends a logout token.

## 10. Logging Out from Upstream Down to the Broker and App

Scenario where **the user logs out directly at the upstream IdP**:

~~~text
Upstream user session C ends
     |
     +-- Does upstream support OIDC Back-Channel / SAML SLO / notifications?
     |       |
     |       +-- NO:
     |       |     Broker B may stay alive
     |       |     App A may stay alive
     |       |
     |       +-- YES, broker actually receives/verifies:
     |             |
     |             v
     |           Broker invalidates exact broker session B
     |             |
     |             +-- Does broker send logout to downstream RPs?
     |                    |
     |                    +-- Yes, RP receives/verifies/matches:
     |                    |      App A is invalidated
     |                    |
     |                    +-- No / delivery fails:
     |                           App A may remain alive
~~~

**Two independent propagation hops are required**:

- **Upstream → broker**: upstream must support and enable logout notifications, and the broker must verify them and map which broker session links to that upstream session.
- **Broker → app**: the broker must support and enable RP notifications, and the app must maintain session mapping and a working endpoint.

A failure at an intermediate step cannot be inferred solely from another system's final state. Verify using secure logs and session state at each tier.

### 10.1. One Broker with Multiple Upstream IdPs

A broker may serve multiple IdPs (Corporate A, Corporate B, social logins). Upon receiving a logout event from upstream A, the broker must never wipe **every session for every user sharing an email** or use issuer B to verify token A.

State to map:

~~~text
Broker session:
  brokerIssuer
  brokerSid
  localSubject
  upstreamProviderAlias
  upstreamIssuer
  upstreamSubject
  upstreamSid / SAML SessionIndex
  downstreamClientSessions
~~~

This is a **logical data model**; not every product stores every field in this exact shape. An upstream logout must match the exact **provider + subject/session** and apply scoped fan-out—never letting a client/browser supply a provider alias to kill another partner's sessions.

### 10.2. IdP Ends the Session While Access Tokens Survive

If an app holds a broker-issued JWT access token and a resource server validates **signature + `exp`** offline, that token remains accepted **until expiration** even after the broker browser session closes. That does not mean logout broke; it is the boundary between **session invalidation** and **token validation policy**.

Use short token lifetimes, refresh-token policies, token revocation/introspection, or live status checks for high-risk actions depending on architecture. Never claim every JWT is revoked immediately upon RP-Initiated Logout when no mechanism enforces it.

## 11. OIDC Logout and OAuth2 Token Revocation Are Distinct Operations

**OIDC logout** terminates **OP/RP sessions** via standard browser/notification mechanisms. **OAuth 2.0 Token Revocation (RFC 7009)** invalidates **tokens or authorization grants** via the **`revocation_endpoint`**, if supported by the authorization server.

| Operation | Receiving Component | What It Ends | What It Does Not Guarantee |
| --- | --- | --- | --- |
| Spring local logout | RP application | Local `HttpSession`/`SecurityContext` | Broker/upstream sessions, standalone tokens |
| OIDC RP-initiated logout | Broker OP | Broker SSO session per policy | Upstream session, all JWTs/refresh tokens, other RPs |
| OAuth2 token revocation | Authorization server | Token/authorization grant per AS policy | Browser SSO session at OP or upstream |
| OIDC back-channel logout | RP receiving OP event | Local sessions matched by `logout_token` | Access JWTs at other resource servers without checks |
| Upstream SAML Single Logout | SAML IdP/partner SPs | SAML sessions per SLO profile | OIDC tokens, non-SLO apps |

Operational points:

- RFC 7009 requires **refresh token revocation** and recommends **access token revocation**; cascading effects depend on AS policy.
- Revoking a refresh token stops the app from obtaining new tokens, yet **already-issued access JWTs may remain usable** at offline-validating resource servers until `exp` unless blocked separately.
- Access tokens, refresh tokens, and ID Tokens serve **different purposes**. An ID Token proves login to the RP and serves as `id_token_hint` in RP-Initiated Logout; it is not an API Bearer Access Token.
- If the app persists `OAuth2AuthorizedClient` in a database/cache, clean up/revoke it on logout rather than clearing only `HttpSession`.
- With **`offline_access`**, refresh/offline tokens can outlive browser sessions; manage them separately per policy and OP implementation.
- Never call an **upstream** revocation endpoint using upstream client secrets or refresh tokens from an app that trusts only the **broker**: the broker is the RP owning that upstream relationship.

## 12. Two Common Topologies: Server-Rendered/BFF vs. SPA

### 12.1. Server-Rendered Spring Boot or BFF

Here the browser holds **Spring's session cookie**, while ID/access/refresh tokens remain server-side:

~~~text
Browser cookie -> Spring HttpSession
Spring server -> OAuth2AuthorizedClient tokens -> broker
~~~

Minimum logout steps:

1. Invalidate local session, clear SecurityContext and `AuthorizedClient` entries per policy.
2. When broker logout is required, redirect the browser to the broker's **`end_session_endpoint`** via the OIDC handler.
3. Receive callback on the registered `post_logout_redirect_uri`; if `state` was sent, verify `state`.
4. Display accurate messaging about which tiers are confirmed complete.
5. Never expose raw ID Tokens or session cookies in redirect logs.

If the OP lacks RP-Initiated Logout, fall back to local-only and **state the limitation explicitly**. Never call upstream SAML endpoints directly from the BFF.

### 12.2. SPA Holding Tokens in the Browser

In an SPA, JavaScript may keep tokens in memory while the browser also holds an OP SSO cookie. Logout must:

- Clear app state/tokens wherever stored per policy.
- Invoke the OIDC client library or redirect to the right `end_session_endpoint`.
- Never embed client secrets in the frontend bundle.
- Account for multiple tabs/broadcast state, `SameSite` cookies, and callbacks.
- Avoid storing sensitive tokens in `localStorage` when safer options exist, especially under XSS risk.
- Never assume "cleared `localStorage`" revoked the refresh token at the OP.

With a BFF, the backend secures tokens and cookies better; ending the **upstream IdP session** still remains the responsibility of the broker and upstream protocol.

## 13. Redirects, state, Cookies, and Reverse Proxies

### 13.1. post_logout_redirect_uri Requires Exact Matching

Registered URI example:

~~~text
https://portal.example.test/signed-out
~~~

If Spring generates:

~~~text
http://portal.internal:8080/signed-out
~~~

the broker will reject it as outside the allowlist. Behind an ingress:

- Use a fixed public HTTPS base URL or configure forwarded headers from **trusted proxies** only.
- Never blindly trust browser-supplied `Host`/`X-Forwarded-Host`.
- Match the OP-registered callback **on exact path, scheme, host, and port**.
- Never turn `post_logout_redirect_uri` into an **open redirect** via an unvalidated `returnUrl` parameter.

### 13.2. state and Logout CSRF

If the RP sends **`state`**, bind it to a **specific logout flow** with a short TTL and sufficient entropy, and verify it on return. State is **not a session ID**, not an authentication JWT, and must hold no secrets.

An attacker may try forcing a browser to hit an unprotected logout endpoint to cause **forced logout**. Therefore:

- Web local logout should use POST with proper CSRF protection.
- The OP must enforce RP-Initiated Logout rules: `id_token_hint` or client/target validation and user confirmation when needed.
- Front-channel logout must verify `iss+sid` per profile rather than destroying arbitrary sessions on any GET.
- Back-channel logout must verify signed JWTs and block replays.
- Never disable CSRF app-wide just to trigger OIDC logout via a GET link.

### 13.3. What Do Browser Cookies Control?

- App cookie identifies the **application**.
- Broker cookie identifies the **OP SSO session**.
- Upstream cookie identifies the **upstream IdP session**.

Each cookie has its own domain, path, `SameSite`, `Secure`, and lifetime. Clearing an app cookie **cannot arbitrarily delete cookies owned by the upstream IdP domain**. Front-channel depends on the browser sending the target cookie inside an iframe/redirect; back-channel avoids browser cookies yet requires server-side session mapping.

## 14. Security Boundaries When Brokering Multiple Partners/Tenants

In multi-IdP/multi-tenant setups, a broker authenticates users from IdP A or IdP B. Logout propagation must preserve **issuer/subject/session scope**:

| Entity | Good Correlation Key | Never Rely Solely On |
| --- | --- | --- |
| App local session | Application session ID + OIDC provider registration / verified broker `sid` | Browser-supplied email |
| Broker session | Broker issuer + broker `sid`, local subject + RP client links | App `JSESSIONID` |
| Upstream OIDC session | Upstream issuer + upstream `sid`/`sub` + provider alias | `sub` without issuer |
| Upstream SAML session | Upstream IdP `entityId` + `NameID` + `SessionIndex` per profile | Email or unscoped `NameID` alone |
| Logout Token event | Verified issuer + audience/client + `jti` + `sid`/`sub` | Unverified JWT payload |

A single user may hold two accounts/tenants across two browsers. A logout event for one upstream `sid` **must never invalidate every user sharing an email**. On mapping failures, **fail closed** and report incomplete status rather than "broadcasting logout to everyone" for convenience.

When a broker and app support multiple OPs/realms, validate **`iss` and `aud` against the exact client registration**. A Logout Token from Broker A must never terminate a session authenticated by Broker B.

## 15. Experience Walkthrough: Why Does Login Succeed Without a Password Right After Logout?

### Scenario A — Local Logout Only

~~~text
A (app session):      CLOSED
B (broker session):   ALIVE
C (upstream session): ALIVE

User visits /protected -> redirects to broker
Broker sees B is alive -> issues new code/ID Token
User signs back in almost instantaneously
~~~

**Diagnosis:** app logout may have worked properly. If UX requires ending broker SSO, use RP-Initiated Logout and verify OP metadata.

### Scenario B — Broker Logged Out, Upstream Remains Alive

~~~text
A: CLOSED
B: CLOSED
C: ALIVE

User visits /protected -> broker lacks B
Broker redirects upstream -> upstream still has C
Upstream supplies identity -> broker creates new B
Broker returns to app -> app creates new A
~~~

**Diagnosis:** inspect **broker → upstream Logout URL / SAML SLO / back-channel** settings rather than tweaking local `HttpSession`.

### Scenario C — Upstream Logged Out, Broker Never Notified

~~~text
A: ALIVE
B: ALIVE
C: CLOSED

Browser keeps accessing app with valid session A
Broker B is unaware upstream C closed
~~~

**Diagnosis:** missing or broken **upstream → broker notification**, and/or missing **broker → downstream RP logout**. Configure those channels or tighten session freshness/re-authentication policies.

### Scenario D — Full-Chain Logout Supported

~~~text
App local logout -> broker RP-initiated logout accepted
Broker clears session B -> sends downstream logout
Broker executes upstream logout -> upstream confirms
Broker/app receive and process callbacks/notifications

A: CLOSED
B: CLOSED
C: CLOSED
Other RPs: depends on which notifications actually processed
~~~

**Never display "Signed out everywhere successfully" merely because the app saw an HTTP 302**. Every hop can time out, retry, or partially fail; define success at the system level.

## 16. Standalone Java 17: Modeling Session Layers and Propagation

The program below runs on **JDK 17+**, requiring no Spring or OIDC server. It is a **state-machine simulation** clarifying logout outcomes:

- **Local logout** closes only the app session.
- **Broker-accepted RP-Initiated Logout** closes the broker session, with two independent policies: **notify sibling RPs** and **propagate upstream**.
- **Direct upstream logout** does not close app/broker unless a notification reaches the broker.
- **Upstream back-channel events** must be verified by a trusted library and match issuer/audience/session before the broker may propagate.
- After broker logout, **`refreshTokenUsable=false` in the demo** is a **broker policy assumption of token invalidation**, **not a mandatory requirement of RP-Initiated Logout**.
- **`accessTokenNotExpired=true`** shows issued JWTs can still be within `exp`; whether resource servers accept them depends on revocation/introspection/policy.

**Warning:** the boolean **`validatedByJwtLibrary`** in the demo is a **mocked verifier output**. Never read this boolean from an HTTP body or query! This code performs no JWT signature checks, HTTP redirects, OIDC Discovery, broker session lookups, or token revocation. Real systems must use Spring Security/OIDC libraries, database session registries, and trust configs.

File **OidcBrokerLogoutLayersDemo.java**:

~~~java
import java.util.Objects;

public class OidcBrokerLogoutLayersDemo {
    static final class Sessions {
        boolean application = true;
        boolean brokerOp = true;
        boolean upstreamIdp = true;
        boolean siblingRp = true;
        boolean refreshTokenUsable = true;
        boolean accessTokenNotExpired = true;

        void localLogout() {
            application = false;
        }

        // Models an OP that accepted the RP-initiated logout request.
        // Notification/propagation are explicit capabilities, not guarantees.
        void acceptedOidcLogout(boolean notifySibling,
                                boolean upstreamPropagationEnabled) {
            localLogout();
            brokerOp = false;
            refreshTokenUsable = false;
            if (notifySibling) siblingRp = false;
            if (upstreamPropagationEnabled) upstreamIdp = false;
        }

        boolean onUpstreamBackchannel(
                String issuer, String audience, String sessionId,
                boolean validatedByJwtLibrary) {
            // "validatedByJwtLibrary" is MOCK TRUST from tests only.
            if (!validatedByJwtLibrary
                    || !Objects.equals(
                        issuer, "https://upstream.example.test")
                    || !Objects.equals(audience, "broker-client")
                    || !Objects.equals(sessionId, "upstream-session-7")) {
                return false;
            }
            upstreamIdp = false;
            brokerOp = false;
            application = false;
            siblingRp = false;
            refreshTokenUsable = false;
            return true;
        }

        String summary() {
            return "app=" + application + ",broker=" + brokerOp
                + ",upstream=" + upstreamIdp + ",sibling=" + siblingRp;
        }
    }

    public static void main(String[] args) {
        Sessions local = new Sessions();
        local.localLogout();
        System.out.println("localOnly=" + local.summary());

        Sessions oidc = new Sessions();
        oidc.acceptedOidcLogout(true, false);
        System.out.println("oidcNoUpstream=" + oidc.summary());

        Sessions isolated = new Sessions();
        isolated.acceptedOidcLogout(false, false);
        System.out.println("oidcNoSiblingNotification=" + isolated.summary());

        Sessions propagated = new Sessions();
        propagated.acceptedOidcLogout(true, true);
        System.out.println("oidcAndUpstream=" + propagated.summary());

        Sessions upstream = new Sessions();
        upstream.upstreamIdp = false; // user signed out upstream directly
        System.out.println("upstreamWithoutNotice=" + upstream.summary());
        boolean rejected = !upstream.onUpstreamBackchannel(
            "https://fake.example.test", "broker-client",
            "upstream-session-7", false);
        System.out.println("untrustedNoticeRejected=" + rejected);
        System.out.println("upstreamAfterUntrustedNotice=" + upstream.summary());
        boolean accepted = upstream.onUpstreamBackchannel(
            "https://upstream.example.test", "broker-client",
            "upstream-session-7", true);
        System.out.println("trustedNoticeAccepted=" + accepted);
        System.out.println("upstreamWithNotice=" + upstream.summary());

        System.out.println("refreshTokenUsableAfterOidc=" + oidc.refreshTokenUsable);
        System.out.println("accessTokenMayRemainTimeValid=" + oidc.accessTokenNotExpired);
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 OidcBrokerLogoutLayersDemo.java
java OidcBrokerLogoutLayersDemo
~~~

**Exact stdout**:

~~~text
localOnly=app=false,broker=true,upstream=true,sibling=true
oidcNoUpstream=app=false,broker=false,upstream=true,sibling=false
oidcNoSiblingNotification=app=false,broker=false,upstream=true,sibling=true
oidcAndUpstream=app=false,broker=false,upstream=false,sibling=false
upstreamWithoutNotice=app=true,broker=true,upstream=false,sibling=true
untrustedNoticeRejected=true
upstreamAfterUntrustedNotice=app=true,broker=true,upstream=false,sibling=true
trustedNoticeAccepted=true
upstreamWithNotice=app=false,broker=false,upstream=false,sibling=false
refreshTokenUsableAfterOidc=false
accessTokenMayRemainTimeValid=true
~~~

**Interpretation:** true/false values in the output do not verify a live broker's SSO state. They are **hypothetical outcomes** corresponding to specific notify/propagate capabilities. This clearly shows **local logout**, **broker OP logout**, and **upstream IdP logout** are three separate events, and multiple independent events must succeed together to claim "full-chain logout".

## 17. Integration Test Matrix

| Test Case | Action | Expected Verification |
| --- | --- | --- |
| Local logout only | App `POST /logout` with local handler | A closes; does **not** automatically ask B/C to close |
| Valid RP-Initiated Logout | App logout with OIDC handler, OP supports endpoint | A closes, browser hits broker `end_session_endpoint`; verify B's state |
| OP lacks `end_session_endpoint` | Discovery omits endpoint | Clear local fallback; never claim guaranteed broker logout |
| OIDC login vs. OAuth2-only | Authentication lacks `OidcUser`/ID Token | Never send fake `id_token_hint`; local fallback policy |
| Wrong `post_logout_redirect_uri` | URI outside broker allowlist | OP rejects redirect; no open redirect |
| Reverse proxy wrong host | `{baseUrl}` points to internal HTTP | Test catches callback mismatch |
| Tampered `state` | Callback `state` differs from stored request | Reject / distrust callback |
| Missing ID Token hint | OP requires extra confirmation | OP enforces policy/confirmation; never bypasses |
| Broker OP logout succeeds, upstream lacks SLO | A/B close, C stays alive | UI never claims C closed |
| Broker logout with upstream propagation | Configured upstream Logout URL / SAML SLO | Verify notification and actual state of C |
| Upstream OIDC logout token hits broker | JWT signed by upstream OP key, valid `iss`/`aud`/`sid` | Broker maps session and handles properly |
| Upstream logout token `alg=none` | Token lacks valid signature | Reject |
| Upstream logout token wrong issuer | Another IdP's issuer | Never terminate broker sessions for this IdP |
| Back-channel missing event | JWT lacks backchannel-logout `events` claim | Reject |
| Back-channel includes `nonce` | Logout Token contains `nonce` claim | Reject per spec |
| Back-channel missing `sub`/`sid` | Cannot locate session | Reject |
| Back-channel wrong `aud` | Token intended for another client | Reject |
| Back-channel replay | Re-submitted `jti` | Idempotent + replay protection |
| Broker sends front-channel iframe | App receives request inside iframe | Test `SameSite`/CSP/third-party cookies |
| Browser closes mid-logout | OP notifying front-channel | Do not assume sibling RPs logged out |
| Broker sends downstream back-channel | RP endpoint receives signed Logout Token | Matches exact session and invalidates |
| Sibling RP lacks back-channel URL | Broker has nowhere to send notification | Sibling session may stay alive |
| Upstream SAML IdP | Broker sends SAML `LogoutRequest` if SLO supported | Verify issuer, signature, `SessionIndex`, `InResponseTo` |
| Same user, multiple sessions | Two devices with distinct `sid` | Logout scoped properly by session/`sub` per policy |
| Multi-tenant with shared email | IdP A/B emit identical emails | Never terminate sessions for the wrong issuer/provider |
| Refresh token revocation | AS supports RFC 7009 and revokes token | Cannot obtain new tokens post-revocation per policy |
| Access JWT unexpired | Resource server verifies offline | May remain usable; requires dedicated policy |
| OP logout error/timeout | Browser gets error; upstream unconfirmed | Never display "all signed out" |
| Logout CSRF | Attacker injects GET/POST without valid CSRF | App/OP resists forced logout violating policy |
| Token leak in logs | Proxy logs full logout query | Detect and scrub `id_token_hint`/tokens |
| UI "Sign out everywhere" | Promises signing out all devices/apps | Show only when full chain is substantiated; otherwise narrow wording |

Integration tests must run against a **real or sandbox broker/IdP**, not just Java unit tests. Safely observe sessions/cookies, OP events, token refreshes, sibling RPs, and the upstream IdP. **Never paste production ID/access tokens into logs or public debugging tools**.

## 18. Layer-by-Layer Troubleshooting

| Symptom | Common Cause | Where to Inspect |
| --- | --- | --- |
| Immediate re-login right after local logout | Broker session B or upstream session C still alive | Compare sessions A/B/C, not just app cookie |
| Spring never redirects to OP logout | Missing OIDC handler, non-OIDC Auth, or OP omits endpoint | `ClientRegistration`, `OidcUser`, Discovery |
| Broker reports invalid redirect URI | `post_logout_redirect_uri` unregistered or wrong `{baseUrl}` | OP client config, proxy/public URL |
| Browser returns to app yet B stays alive | OP logout unexecuted, user confirmation, wrong session hint | OP logs and session store |
| Broker B closes yet C stays alive | Upstream logout disabled or unsupported | Upstream IdP config, Logout URL / SAML SLO |
| Upstream C closes while B stays alive | Missing upstream→broker logout notification | Upstream back-channel / SAML SLO + broker session mapping |
| Broker B closes while sibling app A stays alive | Missing broker→RP notification or RP not receiving | Backchannel Logout URL / front-channel config |
| Front-channel logout fails to close RP session | Iframe blocked by CSP/`SameSite`/third-party cookies | Browser Network, cookies, iframe console errors |
| Back-channel token arrives yet RP stays logged in | Invalid JWT, missing `sid` mapping, or endpoint unwired | JWT verifier, `iss`/`aud`/`events`/`jti`, session registry |
| Wrong tenant's session logged out | Lookup by email/`sub` without issuer/session scope | Mapping (`issuer`, `sid`/`sub`, `client`, `tenant`) |
| App still calls APIs after broker logout | JWT access token still valid/accepted | Token expiry, Resource Server policy, revocation |
| Refresh token still works | OP did not revoke per policy or `offline_access` | AS revocation/session policies |
| Logout loop | Callback URL still protected/redirecting to auth | `/signed-out` `permitAll`, authorization rules |
| Upstream SAML reports invalid SLO | Broker sent wrong `NameID`/`SessionIndex`/signature/binding | SAML metadata, signing cert, `InResponseTo` |
| Logout differs between DEV and PROD | Differing broker realms, issuers, callbacks, cookies | Per-environment registration/trust |
| OP logout kills only one client session | Broker notification scope depends on config | OP client session / RP notification policy |
| No login prompt after logout | Upstream holds SSO cookie, remember-me, or reauth policy | Upstream IdP session/step-up settings |

### 18.1. Useful Diagnostic Order

1. **A:** after `POST /logout`, do local `HttpSession`/`SecurityContext` still exist?
2. **B:** did the browser redirect to the **broker `end_session_endpoint`**, and did the OP confirm closing B?
3. **Downstream:** did sibling RPs receive valid front/back-channel notifications and invalidate their sessions?
4. **C:** did the broker issue upstream logout per provider config, and did upstream report an outcome?
5. **Tokens:** were refresh tokens, access tokens, and the `AuthorizedClient` store cleaned up/revoked per policy?
6. **Browser:** do app/broker/upstream cookies have the right domain/`SameSite`/expiry, and is another session still alive?
7. **UX:** does the confirmation message reflect verified outcomes or merely assume success from an HTTP 302?

Log using **correlation ID, registrationId, issuer, client ID, hashed session-id, event type, response status, and timestamp**—never log raw tokens, session cookies, PII, or full JWT claims. Correlate telemetry across all three tiers instead of guessing upstream events from app logs alone.

## 19. Designing Logout UX Messaging and Policy

Safe UX avoids a single button making sweeping promises the architecture cannot back up:

| UI Option | Minimum Implementation Meaning | Appropriate Message |
| --- | --- | --- |
| **Sign out of app** | Local logout A | "You have signed out of this application." |
| **Sign out of SSO** | Local A + RP-Initiated Logout to broker B, observe outcome | "SSO sign-out request sent." or clear confirmation when broker reports success |
| **Sign out of enterprise IdP** | Supported and processed broker upstream logout | Confirm only when upstream/protocol evidence exists |
| **Sign out of all apps/devices** | All OP/RP/device/token paths have matching revocation/notification | Promise only when designed and verified to this standard |

**Never show "Signed out of all systems" after a single redirect** if the broker lacks upstream logout or downstream notifications are best-effort. Guidance can read: "You have signed out of the application. Your identity provider session may still be active; sign out at your provider if needed."

### 19.1. Re-Authentication Policy

Some products intentionally avoid logging out the entire upstream session when a user closes one app: employees may be using several corporate apps and upstream logout would disrupt them. Here **local-only logout is a deliberate choice**, paired with clear messaging.

When targeting **shared devices/kiosks** or high-risk accounts, require:

- OP logout with proper user confirmation.
- Upstream logout where supported and permitted by the IdP.
- Re-authentication/step-up with **`max_age`**, **`prompt=login`**, or matching IdP policy on the next sign-in.
- Token revocation, short session lifetimes, and server-side session invalidation.
- Verification of cross-browser/multi-device behavior within the promised scope.

**`prompt=login`** on the next sign-in requests re-authentication; it **does not replace genuine RP logout or revoking old tokens**.

## 20. Implementation Checklist

- [ ] Clear diagram of **app A → OIDC broker B → upstream IdP C**, identifying RP/OP on each leg.
- [ ] Separate **local session**, **broker OP session**, **upstream IdP session**, **sibling RPs**, and **access/refresh tokens**.
- [ ] UI copy states exact logout scope without promising full federation logout if unsupported.
- [ ] Spring Security local logout clears `SecurityContext`/`HttpSession` and client session state per policy.
- [ ] When broker logout is required, OIDC RP uses **`OidcClientInitiatedLogoutSuccessHandler`** or verified equivalent.
- [ ] Broker Discovery publishes **`end_session_endpoint`** and app uses the right issuer/client registration.
- [ ] **`id_token_hint`**, if sent, is the broker token issued to the app—never an upstream token with wrong audience.
- [ ] **`post_logout_redirect_uri`** is exact-match registered, public HTTPS, and free of open redirects.
- [ ] If **`state`** is used, RP generates an opaque high-entropy/TTL value and validates the callback.
- [ ] Tested browser cookies, `SameSite`, `Secure`, and trusted reverse proxy/forwarded headers.
- [ ] Distinguished OP-accepted logout from mere browser 302 redirects.
- [ ] Sibling RPs have real front-channel or back-channel configs rather than assuming automatic notifications.
- [ ] If using front-channel, tested iframe CSP and third-party cookie blocking.
- [ ] If using back-channel, endpoint receives **`logout_token`** and verifies signature, `iss`, `aud`, `events`, `iat`, `sub`/`sid`, `nonce` prohibition, and replay.
- [ ] Broker maps upstream provider/issuer/session to broker session with proper scope, never email alone.
- [ ] Broker upstream logout URL / SAML SLO / back-channel enabled, agreed, and tested per IdP.
- [ ] Upstream SAML logout uses proper **SAML `LogoutRequest`/`LogoutResponse`**, never confusing with OIDC `end_session_endpoint`.
- [ ] Safe fallback when upstream lacks logout support or user closes the browser.
- [ ] Distinguished OIDC logout from **RFC 7009 token revocation** and offline JWT lifetimes.
- [ ] Never assumed OIDC logout revokes all access/refresh/offline tokens unless the OP guarantees it.
- [ ] Multi-session/multi-device policy matching `sid` + issuer/client; never logs out the wrong tenant.
- [ ] Negative tests pass: forged logout token, wrong `iss`/`aud`, missing `events`/`sub`/`sid`, `nonce` present, `alg=none`, `jti` replay, wrong redirect, expired session.
- [ ] Never log raw ID Tokens, refresh tokens, `logout_token`, cookies, or PII in logs/traces.
- [ ] Tier A/B/C monitoring, ticketing, and runbooks when a logout tier fails.

## 21. Self-Check Questions

**1. The Spring app cleared `JSESSIONID` yet the user immediately SSOs back in; is local logout broken?**

Not necessarily. Broker B or upstream C may still hold an SSO session and mint a new app session. Inspect each tier.

**2. Should the Spring app send logout to the broker or the upstream IdP?**

When the app authenticates via OIDC **directly with the broker**, the app sends **RP-Initiated Logout to the broker OP**. The broker handles logout integration with upstream per config/protocol.

**3. How does `end_session_endpoint` differ from `authorization_endpoint`?**

`authorization_endpoint` starts login/authorization; `end_session_endpoint` lets the RP ask the OP to end a session. They are functionally separate endpoints.

**4. Where does `id_token_hint` come from?**

From the **ID Token issued by the broker to this RP app** during the prior OIDC login. Never use an access token or an upstream ID Token with a different issuer/audience.

**5. Can `post_logout_redirect_uri` be chosen arbitrarily by the browser?**

No. It must match an exact allowlist registered at the OP; without valid verification, the OP must never redirect to an untrusted parameter.

**6. Does `OidcClientInitiatedLogoutSuccessHandler` automatically receive back-channel logout tokens?**

Never assume that. It handles **RP-initiated logout**; receiving and processing OP-initiated Back-Channel Logout is a separate flow/endpoint requiring dedicated support.

**7. Does successful broker logout guarantee upstream logout?**

No. It depends on upstream Logout URL / SAML SLO / back-channel, broker config, and IdP support, and may fail or be unsupported.

**8. Does direct upstream logout automatically clear the app session?**

Not automatically. It requires upstream→broker notification and broker→app notification or appropriate session detection.

**9. What is the key difference between front-channel and back-channel?**

Front-channel relies on browser/iframes and cookies/CSP; back-channel posts a signed `Logout Token` JWT server-to-server to an RP endpoint and works even when the browser is gone.

**10. Can a Logout Token be an `alg=none` JWT or an ID Token carrying a `nonce`?**

No. Per Back-Channel Logout, the token must be signed, carry the right event marker, include `sub`/`sid`, **have no `nonce`**, and pass `iss`/`aud`/time/replay checks.

**11. Does OIDC RP-Initiated Logout guarantee revoking every unexpired JWT access token?**

No. Session logout and token revocation are separate mechanisms. A JWT may remain accepted by a resource server until `exp` without status/revocation checks.

**12. Why might closing the browser during logout leave other RPs signed in?**

Front-channel notifications depend on the browser loading logout iframes/pages; closing mid-flow prevents delivery/receipt. Back-channel or additional session controls are needed.

**13. Can an upstream SAML IdP accept an OIDC `id_token_hint` for logout?**

No. For SAML SLO, the broker must use SAML `LogoutRequest`/`LogoutResponse`, `NameID`/`SessionIndex`, signing, and `InResponseTo` per profile.

**14. When is local-only logout a sound design?**

When UX intends to exit only one application without disrupting other corporate apps; state the scope clearly, accept fast re-SSO, and manage local tokens/sessions securely.

**15. Why shouldn't multi-tenant back-channel logout rely solely on email?**

Email does not distinguish issuers/providers, can be recycled, and is not a session key. Use verified identifiers: issuer, `aud`/client, `sub`/`sid`, and session/tenant mappings.

## 22. Standards and Official References

- Spring Security, **OIDC Logout** — `OidcClientInitiatedLogoutSuccessHandler`, `end_session_endpoint`, post-logout redirect template: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/logout.html
- Spring Security Javadoc, **`OidcClientInitiatedLogoutSuccessHandler`**: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/oidc/web/logout/OidcClientInitiatedLogoutSuccessHandler.html
- Spring Security, **Logout** — local Session/Cookie/SecurityContext logout: https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html
- Spring Security, **OAuth2 Login** — `ClientRegistration` and `OidcUser`: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html
- OpenID Connect, **RP-Initiated Logout 1.0** — `id_token_hint`, `client_id`, `state`, `post_logout_redirect_uri`, `end_session_endpoint`: https://openid.net/specs/openid-connect-rpinitiated-1_0.html
- OpenID Connect, **Front-Channel Logout 1.0** — browser/iframe, `iss` and `sid`, third-party content issues: https://openid.net/specs/openid-connect-frontchannel-1_0.html
- OpenID Connect, **Back-Channel Logout 1.0** — `logout_token` JWT, `events`, signature, `sub`/`sid`, `nonce` prohibition, and validation: https://openid.net/specs/openid-connect-backchannel-1_0.html
- OpenID Connect, **Session Management 1.0** — OP/RP session state: https://openid.net/specs/openid-connect-session-1_0.html
- IETF, **RFC 7009 OAuth 2.0 Token Revocation** — token revocation distinct from browser logout: https://www.rfc-editor.org/rfc/rfc7009.html
- Keycloak, **Server Administration Guide**, Identity Brokering, OIDC Logout, Client Logout, IdP Logout URL/Backchannel: https://www.keycloak.org/docs/latest/server_admin/
- Keycloak, **OIDC endpoints** — RP-initiated logout and legacy token logout: https://www.keycloak.org/securing-apps/oidc-layers
- OASIS, **SAML 2.0 Profiles**, Single Logout Profile when upstream uses SAML: https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf

**Conclusion:** in a brokered OIDC architecture, **local logout A**, **broker OIDC logout B**, and **upstream IdP logout C** are **three distinct states**, not three names for one action. Spring Security can clear the local session and use **`OidcClientInitiatedLogoutSuccessHandler`** to request broker logout. From the broker to the upstream IdP depends on **provider configuration, logout protocols, and event propagation**. To claim "complete sign-out", verify every committed scope—including **sessions, OIDC front/back-channel, token lifetimes/revocation, and connected applications**.