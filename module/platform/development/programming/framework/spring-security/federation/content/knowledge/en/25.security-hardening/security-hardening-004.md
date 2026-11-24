# Login CSRF, Unsolicited Login, and Session Confusion in Spring Security Federation

## 1. Objective and Context

In **Spring Security – federation**, users may log in via a traditional form or be redirected to an Identity Provider via **OIDC/OAuth 2.0, SAML 2.0, CAS, SPNEGO**, or an identity-aware proxy. In redirect flows, a **cryptographically valid** authentication response is not sufficient to prove that **this browser actively initiated that exact login attempt**.

This is the root cause of **Login CSRF** (Cross-Site Request Forgery at login), **unsolicited login** (a login without a corresponding application request), and **session/account confusion** (a session carrying an unwanted identity or belonging to someone else).

A scenario:

~~~text
1. Mallory has an account on a business website.
2. Mallory exploits a login CSRF flaw to make Alice's browser
   complete a login into Mallory's account.
3. Alice does not notice the active identity has changed.
4. Alice enters orders, activity history, or sensitive data.
5. Data is saved under Mallory's account; Mallory can view it.
~~~

The attacker **does not need Alice's password**. They want **Alice to use an account they control**. Therefore, testing only “can the attacker take over Alice's account?” misses login CSRF.

This lesson belongs to the **Security Hardening** group and helps you:

- Distinguish login CSRF, business CSRF, session fixation, unsolicited IdP SSO, identity switch, account linking CSRF, and AS mix-up.
- Require an **initiated, time-bounded, single-use, browser/pre-session-bound login transaction** before accepting a callback.
- Understand the roles and limits of **form CSRF tokens**, OAuth/OIDC **state**, **PKCE S256**, OIDC **nonce**, RFC 9207 **iss**, SAML **InResponseTo**, and **RelayState**.
- Never silently switch an authenticated user **from Alice to Mallory** merely because a new callback carries a valid token.
- Lock down **issuer + tenant + stable subject**, manage local sessions, fixation protection, session rotation, and saved state.
- Diagnose SAML IdP-initiated login, OIDC authorization response injection, CAS callbacks, SPNEGO automatic authentication, and proxy header/session mismatches.
- Configure Spring Security in the right areas and write security tests covering real-world flows.
- Run a **standalone Java 17** example simulating state binding, wrong browser, unsolicited/replayed responses, wrong IdP, nonce, audience, and silent account switching.

**Core principle:** before creating a Spring `Authentication`, verify **(a) the IdP evidence is genuinely valid**, **(b) the evidence belongs to the exact RP request issued to this browser**, and **(c) the new identity is permitted to attach to the current local session**. These three conditions **do not replace one another**.

## 2. Distinguishing the Attack Classes

| Name | What does the attacker want? | Technical mistake | Countermeasure |
| --- | --- | --- | --- |
| **Business CSRF** | Force a logged-in user to transfer funds/change address | Missing CSRF token on POST/PUT/... | `CsrfFilter`, token, Origin/Fetch Metadata defense in depth |
| **Form login CSRF** | Force a browser to log in with the attacker's credentials | Form POST login does not check CSRF token | Pre-session + CSRF token + fresh authenticated session |
| **OAuth/OIDC response CSRF** | Inject a code/token response not belonging to the browser/login transaction | Missing state/PKCE/nonce/binding checks | Correlate state/nonce/PKCE with browser, one-time consume |
| **IdP-initiated SAML unsolicited** | Send a SAMLResponse when the SP never issued an AuthnRequest | No InResponseTo to prove request | SP-initiated by default; allow unsolicited only under explicit policy |
| **Session fixation** | Reuse a session ID known to the attacker across login | Pre-session becomes authenticated session without rotation/replacement | Session fixation protection; audit session attribute migration |
| **Account/session confusion** | Alice stays on Bob's session/role or gets switched to Mallory | Not comparing principal/tenant/session on new callback | Explicit account-switch policy, session invalidation/rotation |
| **OAuth AS mix-up** | Send code/credentials to the wrong AS/token endpoint | Not binding issuer to transaction and callback | RFC 9207 iss / RFC 9700 mix-up defense |
| **Account-linking CSRF** | Link attacker's identity to victim's local account | Linking OAuth/SAML without consent/transaction | Reauth + CSRF/user intent + full binding |

**An unsolicited login is not always an attack**: many IdPs let users start SSO from a portal/app tile. However, if the SP does not initiate the request, **the ability to correlate the transaction with the browser at the SP is reduced**; you must acknowledge and govern that risk.

## 3. Why Does Login CSRF Appear in the Anonymous State?

OWASP makes clear that **form login also needs CSRF protection**, even when the user is not yet authenticated. While unauthenticated, the browser can still receive a **pre-session cookie** to hold the CSRF token. If the login endpoint skips token checking, a third-party page can automatically POST the attacker's credentials to the target app.

Safe example:

~~~text
GET /login:
    create pre-session A
    issue CSRF token matching A

POST /login:
    require valid token from pre-session A
    verify username/password with real provider
    invalidate/replace pre-session A
    issue authenticated session B with a new ID
~~~

**Do not unconditionally promote a pre-session to an authenticated session.** OWASP recommends creating a new session after login to prevent session fixation. Spring Security provides session fixation strategies, yet you still must audit **which attributes are preserved** and never carry old user data into the new session.

Illustrative form:

~~~html
<form method="post" action="/login">
  <input type="hidden" name="_csrf" value="render-from-CsrfToken">
  <input type="text" name="username" autocomplete="username">
  <input type="password" name="password" autocomplete="current-password">
  <button type="submit">Sign in</button>
</form>
~~~

The value `render-from-CsrfToken` **describes how to render it**, not a usable token. With Thymeleaf/Spring MVC, obtain the real `CsrfToken` provided by the framework; never hard-code or share one token across all browsers.

### 3.1. Spring Security protecting form login

~~~java
package com.example.portal.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class FormSecurity {
    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/public/**").permitAll()
                .anyRequest().authenticated())
            .formLogin(form -> form
                .loginPage("/login").permitAll())
            .sessionManagement(session -> session
                .sessionFixation(fixation -> fixation.newSession()));
        return http.build();
    }
}
~~~

This is a **Spring Boot Servlet configuration fragment** requiring a login page, provider, CSRF token, project/dependencies, and integration tests; it is **not a standalone Java file**. Spring Security Servlet **enables CSRF by default** and documentation explicitly states CSRF is needed for login requests. Do not write `csrf.disable()` or `csrf.ignoringRequestMatchers("/login")` just to stop 403 errors on login POSTs.

**A valid CSRF token does not prove valid credentials**: after `CsrfFilter`, requests must still pass the AuthenticationManager, user status checks, and authorization rules. Require HTTPS, rate limiting, and never log passwords or request bodies.

## 4. Login Transaction: Mandatory Contract Before Callback

A secure federation redirect flow typically needs server-side state such as:

~~~text
LoginTransaction:
  transactionId       = one-time random secret/state
  browserBinding      = pre-session identifier
  providerRegistration= corp
  expectedIssuer      = https://login.example.test/realms/corp
  clientId            = portal-client
  redirectUri         = https://portal.example.test/login/oauth2/code/corp
  nonce               = fresh random value (OIDC when applicable)
  pkceVerifier        = secret (OAuth Authorization Code + PKCE)
  createdAt/expiresAt = short-lived
  intent              = normal login / reauth / switch / link
  existingAccountKey  = if browser is already authenticated
  consumed            = false
~~~

This is a **learning model**, not the exact structure Spring persists verbatim. Depending on the protocol, SAML uses **AuthnRequest ID/InResponseTo**; OAuth uses **state/nonce/PKCE**; other flows have their own mechanisms. **Do not use email, spoofable Origin, IP, or User-Agent as a substitute for browser binding.**

The callback must:

1. Confirm the request hit the **right callback endpoint** routed to the right SecurityFilterChain/protocol filter.
2. Reject missing, blank, duplicate `state`/request ID, or absent pending transaction.
3. Verify the pending transaction is bound to **this browser/pre-session**, unused, and unexpired.
4. Verify **issuer/provider/registration/client/redirectUri** match the initiated transaction.
5. Perform **real protocol validation** (signature, audience, nonce, assertion conditions, service binding, etc.).
6. **Consume once** the transaction; reject replayed/concurrent callbacks.
7. Check account-switch/login-intent policy if the browser is already authenticated.
8. Load local user and authorities for the right **issuer+tenant+subject**, creating/rotating the authenticated session.
9. Never let an old callback create a new `SecurityContext` after logout or switching to another account.

**If a request lacks a matching transaction, fail closed**: never “reconstruct” a pending transaction from the caller's `state` or query parameters alone.

## 5. OAuth/OIDC Authorization Code: state, PKCE, nonce, iss

### 5.1. Valid flow

~~~text
Browser                   Spring RP                       OIDC Provider
   |                         |                                  |
   | select /login           |                                  |
   |------------------------>|                                  |
   |                         | generate state, nonce, PKCE,     |
   |                         | save provider + browser session  |
   |<------------------------| 302 /authorize?state=...         |
   |----------------------------------------------------------->|
   |                         |                                  | Auth user
   |<-----------------------------------------------------------|
   | callback?code=...&state=... (may include iss=...)          |
   |------------------------>|                                  |
   |                         | lookup transaction               |
   |                         | compare browser, state, issuer   |
   |                         | check expiry / one-time          |
   |                         | validate iss before code routing |
   |                         | exchange code + code_verifier    |
   |                         | verify ID Token + nonce          |
   |                         | local user / consent policy      |
   |                         | fresh local session              |
~~~

- `state` is an **unpredictable value** used to bind the authorization response to the authorization request/browser. If it encodes application state, it must be protected against **tampering/swapping**.
- OIDC `nonce` binds the authorization request to the **ID Token** to detect replay/injection; it must be verified per the request/response profile.
- **PKCE S256** binds the issued code to a secret `code_verifier` known only to the client during token exchange, helping prevent code interception/injection.
- `iss` per **RFC 9207** identifies the authorization server that issued the response, preventing **mix-up** when the RP has multiple providers.
- `redirect_uri` and `client_id` must match the client registration; never read a token endpoint or JWKS URL from an unvalidated query parameter.
- For OIDC, the ID Token requires a valid signature, issuer, audience, expiry, nonce, and configured required claims; never trust `sub` before validation.
- If an access token is present, it does not replace the ID Token in OIDC login. Never use a raw `code` as a session credential.

### 5.2. A standard-accurate note on CSRF defense

**RFC 9700 (OAuth 2.0 Security Best Current Practice)** allows a client to **rely on PKCE** or OIDC **nonce** to prevent authorization response CSRF **when the specified conditions are met**, such as ensuring the authorization server supports and enforces PKCE. It is inaccurate to say every OAuth client must use all of `state`, PKCE, and nonce simultaneously in every profile.

Nevertheless, for Spring OIDC applications using Authorization Code, clear practice is to **keep state/browser transaction binding**, use PKCE S256 where applicable, and validate nonce in OIDC. Avoid:

- Fixed or predictable `state`;
- `state` consisting merely of base64(username);
- Storing `state` globally without browser binding;
- Allowing `state` reuse;
- Using a fixed `nonce` across multiple logins;
- Accepting PKCE downgrade when the AS does not actually enforce it;
- Exchanging the code against a client-specified callback endpoint.

### 5.3. With multiple providers: AS mix-up

~~~text
Browser intends to log in to IdP A.
RP saved expectedIssuer = A.
Callback instead has code/issuer from IdP B.
If RP selects the token endpoint from a browser parameter:
  it may send the code/credential to the wrong endpoint.
~~~

Per **RFC 9700**, an RP interacting with **multiple authorization servers** must defend against mix-up. Common mechanisms:

- Check `iss` in the authorization response per **RFC 9207** against the **stored issuer**, before routing the code to a token endpoint;
- Or an equivalent properly verified issuer indication;
- Absent those, use **distinct redirect URIs per issuer** per the BCP.

**Warning:** checking ID Token `iss` **after** the code has already been sent to the wrong endpoint can be **too late** to prevent code leakage in a mix-up scenario. Bind the issuer/provider right from the OAuth client's transaction and routing.

### 5.4. Authorization request differs from user intent

Spring Security commonly permits initiation via GET:

~~~text
GET /oauth2/authorization/{registrationId}
~~~

An attacker can direct a victim's browser to this URL via a link/redirect, causing the RP to generate a completely valid `state`. Thus **state proves a transaction exists**, not **that the user intentionally chose to switch accounts**.

For **account linking, switching, step-up, privilege elevation, or tenant changes**, add an **explicit user intent** layer: a confirmation page, reauthentication, a POST/CSRF-protected action, or an approved flow coordinator, plus verification of the resulting identity. Never let an external GET automatically attach an IdP identity to a logged-in account.

## 6. Spring Security oauth2Login and AuthorizationRequestRepository

Spring Security provides:

| Component | Responsibility |
| --- | --- |
| `OAuth2AuthorizationRequestRedirectFilter` | Initiates the OAuth authorization request |
| `AuthorizationRequestRepository<OAuth2AuthorizationRequest>` | Stores pending authorization requests for correlation |
| `HttpSessionOAuth2AuthorizationRequestRepository` | Implementation storing requests in HttpSession |
| `OAuth2LoginAuthenticationFilter` | Receives authorization code responses and processes login |
| `ClientRegistrationRepository` | Stores registrationId, issuer/provider, redirect URI, client metadata |
| `OAuth2AccessTokenResponseClient` | Executes token exchange per client registration |
| `OidcUserService` and token validators | Loads and validates OIDC identity/claims appropriately |

Default routes are typically:

~~~text
Start:    /oauth2/authorization/{registrationId}
Callback: /login/oauth2/code/{registrationId}
~~~

Configuration example emphasizing keeping the request repository:

~~~java
package com.example.portal.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.web.AuthorizationRequestRepository;
import org.springframework.security.oauth2.client.web.HttpSessionOAuth2AuthorizationRequestRepository;
import org.springframework.security.oauth2.core.endpoint.OAuth2AuthorizationRequest;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OidcLoginConfig {
    @Bean
    AuthorizationRequestRepository<OAuth2AuthorizationRequest>
    authorizationRequestRepository() {
        return new HttpSessionOAuth2AuthorizationRequestRepository();
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            AuthorizationRequestRepository<OAuth2AuthorizationRequest> repo)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/login", "/public/**").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(oidc -> oidc
                .loginPage("/login")
                .authorizationEndpoint(authz -> authz
                    .authorizationRequestRepository(repo)))
            .sessionManagement(session -> session
                .sessionFixation(fixation -> fixation.newSession()));
        return http.build();
    }
}
~~~

**This is a Spring configuration sample**, not Java runnable with `javac` alone. It requires OAuth2 Client dependencies, a valid ClientRegistration, HTTPS, a real IdP, and `GET /login` if using a custom loginPage. `oauth2Login` handles the protocol; **policy forbidding silent account switching must be added in the application's success handler/flow coordinator**.

If replacing the repository with cookies or Redis:

- Protect **integrity/confidentiality** if storing sensitive data in cookies.
- Bind state to browser/pre-session, expected issuer/client/redirectUri/nonce/verifier.
- Enforce atomic consume, TTL, and logout invalidation.
- Avoid a global shared map keyed by state **without checking browser session**.
- Test real multi-tab and multi-node behavior.
- Never fix state errors by “accepting the callback anyway”.

## 7. SAML SP-Initiated: InResponseTo Is Transaction Correlation

~~~text
Browser -> /saml2/authenticate/corp
SP -> create <AuthnRequest ID="_req123"> and bind to browser session
SP -> IdP SAMLRequest
IdP -> Browser -> SP ACS SAMLResponse
Response/SubjectConfirmationData InResponseTo="_req123"
SP -> verify signature, issuer, audience, destination, recipient,
      Conditions, SubjectConfirmation, and correlation with original request.
SP -> replay check, local account binding, new authenticated session.
~~~

**`InResponseTo` carries meaning**: which SP-created AuthnRequest the response or subject confirmation belongs to. A response with a valid IdP signature whose `InResponseTo` does not match a stored request **must be rejected** in an SP-initiated flow.

**`RelayState`** carries return state, but is **not standalone proof** that the SP requested authentication in the browser receiving the callback. If the RP looks up a request solely by `InResponseTo`/RelayState in a **global cache** without binding to the browser, an attacker can attempt **login fixation**.

Spring Security Servlet SAML 2.0 includes:

- `Saml2WebSsoAuthenticationRequestFilter` issues the AuthnRequest.
- `Saml2AuthenticationRequestRepository` stores the request.
- `HttpSessionSaml2AuthenticationRequestRepository` is the default cited in Spring documentation.
- `CacheSaml2AuthenticationRequestRepository` can be used when not holding sessions; it **must genuinely manage browser binding**.
- `Saml2WebSsoAuthenticationFilter` and converters/validators read the request + assertion.

Spring docs warn: when AuthnRequest is looked up in **HttpSession**, there is a natural anti-login-fixation benefit; if lookup relies solely on an `InResponseTo`/`RelayState` usable across any browser, there is no longer proof that “this browser initiated that request”.

## 8. SAML IdP-Initiated / Unsolicited Response

An IdP can send a user into an application when they click a tile on the IdP portal, without the **SP ever issuing an AuthnRequest**. The IdP posts a SAMLResponse to the ACS, usually **without InResponseTo**.

~~~text
User -> IdP portal tile
IdP -> POST signed SAMLResponse -> SP ACS
SAML Response: no SP AuthnRequest, no corresponding InResponseTo
~~~

This is a **legitimate use case**, not malicious by default. However, it **loses the RP transaction correlation layer**; if an attacker can submit a valid assertion for their own account into someone else's browser, the SP risks **unsolicited login / login CSRF** if it automatically accepts/replaces sessions.

Recommendations:

1. For sensitive applications, **prefer SP-initiated** and reject unsolicited responses if not needed.
2. If IdP-initiated is required, restrict it to **approved IdPs/registrations/services/tenants**; do not accept all.
3. Still validate the full SAML signature with trusted keys, issuer, audience, recipient, destination, Conditions, SubjectConfirmationData, clock skew, and replay of assertion/response IDs.
4. **Do not fabricate InResponseTo or treat unprotected RelayState as proof of SP-initiated flow.**
5. Do not let an unsolicited response automatically **replace an existing authenticated user**; require explicit account switch/consent if policy requires.
6. For apps needing SP-side proof of user intent, let the IdP tile open a landing page that then **initiates SP-initiated SSO**.
7. Test anonymous browsers, same-user active sessions, different-user active sessions, two tabs, SAML response replay, and cross-browser POSTs.
8. Do not copy `supportUnsolicitedResponse` configuration from the **legacy Spring SAML Extension** into modern Spring Security SAML 2.0 without verifying API/version.

### 8.1. SAML POST and Spring Servlet CSRF

SAML HTTP-POST binding sends a form POST **from the external IdP to the ACS**. It normally **cannot** include the business app's form `_csrf` token. Therefore, if configuring a CSRF exception for the ACS:

- Scope it strictly to the **ACS endpoint** handled by the SAML filter; never call `csrf.disable()` for the whole application.
- Rely on **SAML signature + request correlation + audience/recipient/timing/replay** to protect the ACS itself.
- Never start trusting arbitrary `SAMLResponse` payloads just because the request passed a CSRF exception.
- Browser `SameSite=Lax` cookies normally **are not sent on cross-site POSTs**, which can lose the HttpSession holding the AuthnRequest. Design cookie/correlation handling to preserve callbacks without abandoning browser binding.

## 9. CAS, SPNEGO, and Proxy-Auth Do Not Share the Same State Parameter

### 9.1. CAS Service Ticket

A CAS ST can be verified once by CAS and bound to a service:

~~~text
Browser -> /login/cas?ticket=ST-...
App -> CAS /serviceValidate(ticket, service)
CAS -> valid service ticket + CAS username
~~~

A valid ST **does not automatically prove the browser intentionally requested this login**. The app still needs policies for **login initiation**, local session switching, and tenant/identity binding. If adding state to the service URL, preserve the exact **service identity** matching the CAS registered service and validator; never append arbitrary query params assuming all CAS deployments support them.

### 9.2. Kerberos/SPNEGO

Domain browsers may automatically send `Authorization: Negotiate` using the OS Kerberos cache. That automatic behavior **differs** from OAuth callback state. If the browser already holds a local session for Alice while OS/browser auth switches to Bob, enforce **principal continuity** and user-switch policy rather than keeping Alice's roles/cache for Bob.

### 9.3. Identity-aware proxy

A gateway sends trusted headers such as `X-Authenticated-Subject`. The app might still have an old HttpSession for Alice. If the gateway drops the header or sends Bob, the app **must not** keep using Alice's SecurityContext. Require a trusted gateway/network, header stripping, per-request identity binding, and session invalidation—not merely checking a header string.

**Common takeaway:** there is no single uniform `state` across OIDC, SAML, CAS, SPNEGO, and pre-auth proxies. Each protocol proves provenance differently, yet every path must **prevent identity/session confusion**.

## 10. Session Fixation, Session Swapping, Silent User Change

Three distinct scenarios:

### 10.1. Fixation — a session ID problem

~~~text
Pre-session S0: anonymous, attacker knows/fixes session ID S0.
User logs in successfully.
Faulty app: authenticated session still uses S0.
=> attacker can use S0 in the fixation threat model.
~~~

Spring Security offers `changeSessionId()`, `newSession()`, and `migrateSession()` depending on servlet/session version. `changeSessionId` rotates the ID while keeping session attributes; `migrateSession` copies attributes; `newSession` creates a cleaner session while the framework handles required Spring Security attributes. You must still audit whether project/app data travels with the session—never assume changing the ID alone makes all state safe.

### 10.2. Session swapping — an identity problem, not an ID problem

~~~text
Browser is currently using Alice or anonymous.
A valid login response for Mallory arrives.
App creates/switches authenticated principal = Mallory.
User does not realize the account changed; enters data into Mallory's account.
~~~

The session ID may have been **perfectly rotated**, yet **login CSRF** still occurred because the user never intended to log in as Mallory.

### 10.3. Session confusion — data/roles of two users mixed

~~~text
Session S_A: Alice, tenant A, Alice's cart, ROLE_APPROVER.
New callback: Bob, tenant B.
App only changes Authentication principal to Bob.
Old SavedRequest/cart/cache/roles were not cleared.
=> Bob can see Alice's state or use wrong permissions.
~~~

Two strategies:

- **Deny-on-switch (simple recommended default):** never silently change identity; reject the callback, preserve the current session or require logout/reauth depending on policy and risk.
- **Explicit switch:** user intentionally selects **Switch account** via a CSRF/intent-bound transaction; app validates the response, invalidates the old session, creates a clean new session, loads the new user's local UserDetails/roles, and ensures no old data carries over.

**Do not rely solely on `Authentication.getName()`**: emails can collide or change, and tenants/issuers can differ despite matching usernames. Use a stable key such as `(trusted issuer, tenant, subject)` or a governed SAML issuer-qualified NameID; linking two distinct identities requires separate approval.

### 10.4. Local logout is not IdP logout

If the local `HttpSession` is cleared while the IdP SSO session remains active, the browser can quickly re-authenticate through a **new transaction**. That is not automatically a session invalidation bug. Conversely, if the IdP session logged out while the app still accepts the local session contrary to contract, check back-channel/front-channel logout or session freshness policy.

## 11. Pre-Session, SecurityContext, and New Sessions

Spring Security `SecurityContextHolder` holds the Authentication for the current request; `SecurityContextRepository` is responsible for restoring/persisting it in HttpSession or an appropriate store. **Merely calling `SecurityContextHolder.clearContext()` does not automatically delete the Authentication stored in HttpSession.**

For custom login/switch flows:

1. Verify the transaction and identity before creating an Authentication.
2. Check account switch / linking policy.
3. Apply the proper session fixation/session authentication strategy.
4. Invalidate old session/user-specific attributes, session store state, and stale pending transactions.
5. Create a new SecurityContext with an Authentication carrying roles **from the new user/tenant**.
6. Call `SecurityContextRepository.saveContext(...)` when persisting in Spring Security Servlet with explicit-save semantics.
7. Redirect to an allowlisted internal return path; avoid open redirects.
8. Ensure the old session/cookie is no longer accessible.
9. If backed by Redis/JDBC/Spring Session, verify invalidation across replicas and concurrent callbacks.
10. Test browser refresh/back, two tabs, re-login after logout, same-account reauth, and different-account switch.

**Never promote a pre-session unconditionally into an authenticated session**, and never treat a login success handler returning `302` as proof that session/account mapping is correct.

## 12. Multi-Provider, Multiple Tabs, and Concurrent Callbacks

A browser can open:

~~~text
Tab A: /oauth2/authorization/idp-a -> state=A
Tab B: /oauth2/authorization/idp-b -> state=B
Tab C: /logout or switch-account
~~~

If the app stores **only a single pending auth request**, Tab B overwrites transaction A. That can cause login failures or, worse, custom code falling back to accept a mismatched response.

Safe design:

- Each flow gets its own random state/request ID, issuer/client/nonce/PKCE.
- Bind to the browser session, **not merely a global cache lookup by state**.
- Atomic **compare-and-consume** so the same response cannot be processed twice.
- On a wrong-browser callback, reject without using the response to log in; handle DoS if an attacker knows state.
- If logout/account switch occurs during a pending flow, cancel or version old transactions.
- When two callbacks for the same session arrive nearly simultaneously, an **account/session policy** decides winner/loser; never create user A and let user B keep A's business state.
- Use a distributed TTL store + atomic operations across multiple nodes; never rely on a single-machine `HashMap`.
- Test session ID rotation, stale cookies, SameSite cookies, user changes, issuer changes, multiple tabs, and redirect loops.

### 12.1. What is login intent?

Even when OIDC state is valid, an attacker can **actively navigate a browser to the start endpoint**. For systems needing proof that the user chose an account or linked an IdP:

- Provide an explicit login/IdP selection page with confirmation.
- For sensitive account switching/linking, require a CSRF-protected POST or a transaction with equivalent **user-intent proof**.
- Treat a new callback as **a request to change identity**, never silently replacing an existing session.
- Never trust `intent=link` from a query parameter without a bound server-side transaction.

**Key distinction:** a request sent by the browser ≠ a request the browser's owner intended to perform.

## 13. Cookie SameSite, HTTPS, and Open Redirects

| Profile | Callback shape | Cookie considerations |
| --- | --- | --- |
| Traditional OIDC Authorization Code | Top-level cross-site GET | `SameSite=Lax` usually sends the RP cookie on top-level GET |
| SAML HTTP-POST | Cross-site POST to ACS | `SameSite=Lax` usually omits cookies; SP may lose AuthnRequest |
| Same-site form login | POST to /login | CSRF token still required |
| Special Iframe/SPA/BFF | Embedded/cross-site contexts | Third-party cookie policy, SameSite, and security context need dedicated design |

Cookies should use `Secure`, `HttpOnly` where possible, tight `Path/Domain`, session timeouts, and server-side invalidation. `SameSite=None` requires `Secure` on modern browsers and **raises the importance of CSRF/correlation**. `SameSite=Strict` can make OIDC/SAML callbacks lose cookies even on valid auth responses; fix the cookie/binding strategy instead of **disabling state/InResponseTo validation**.

**Return URL/open redirect:**

~~~text
Login success?return=https://attacker.example.test/collect
~~~

Never redirect arbitrarily to a URL supplied by browser/RelayState/state without validation. Allow only **relative internal paths or an exact allowlist**, and protect state integrity. Bad redirects can leak `code`, tokens, or identity info; never place code/ID Token/SAMLResponse/ServiceTicket in downstream URLs.

**Logging:** redact `code`, `state`, `ticket`, SAMLResponse, cookies, Authorization headers, code_verifier, user credentials, and PII.

## 14. Standalone Java 17: Login Transaction and Session Protection

The following example **compiles with JDK 17+** and runs without an IdP or Spring. It simulates:

- The server only initiates a flow if **userIntent** has been checked beforehand.
- `SecureRandom` generates 32-byte Base64URL state/nonce.
- Each flow stores browser session, expected issuer, audience/client, and creation time.
- Callbacks from the wrong browser, missing state, expired, tampered/replayed, or mismatched issuer/nonce/audience are rejected.
- `VerifiedIdToken` is only a **mock verifier output**, not a JWT and does not verify signatures.
- Valid login creates a **new session** and removes the pre-session; old callbacks cannot reopen it.
- A browser logged in as Alice cannot be silently replaced by Mallory; same-account reauth rotates the session.

**Warning:** `userIntent`/`signatureValid` are **simulated test-driven inputs** and must never be read directly from JSON/HTTP requests in real code. Production must use framework OIDC to verify JWT/issuer/audience/nonce/token endpoint and PKCE, browser cookies, TLS, CSRF tokens, and atomic session stores. `HashMap` and `SecureRandom` in the demo **do not make a production OIDC client**.

File **LoginCsrfSessionDemo.java**:

~~~java
import java.security.SecureRandom;
import java.time.Duration;
import java.time.Instant;
import java.util.Base64;
import java.util.HashMap;
import java.util.Map;

public class LoginCsrfSessionDemo {
    static final String IDP_A = "https://idp-a.example.test";
    static final String IDP_B = "https://idp-b.example.test";
    static final String CLIENT = "portal-client";
    static final Instant NOW = Instant.parse("2026-01-01T12:00:00Z");
    static final Duration FLOW_TTL = Duration.ofMinutes(5);

    record Identity(String issuer, String subject) {}
    record Session(String id, Identity user) {}
    record Flow(String sessionId, String state, String nonce,
                String expectedIssuer, String audience, Instant started) {}
    // This record models a token ALREADY verified by a trusted OIDC library.
    // Never take signatureValid from request parameters or JSON in real code.
    record VerifiedIdToken(String issuer, String subject, String audience,
                           String nonce, boolean signatureValid) {}
    record Outcome(boolean accepted, String reason, String sessionId) {}

    private final SecureRandom random = new SecureRandom();
    private final Map<String, Session> sessions = new HashMap<>();
    private final Map<String, Flow> pending = new HashMap<>();

    private String fresh() {
        byte[] bytes = new byte[32];
        random.nextBytes(bytes);
        return Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
    }

    Session newBrowser() {
        Session s = new Session(fresh(), null);
        sessions.put(s.id(), s);
        return s;
    }

    Flow initiate(String sid, String issuer, boolean userIntent, Instant now) {
        if (!userIntent || !sessions.containsKey(sid) ||
            (!IDP_A.equals(issuer) && !IDP_B.equals(issuer))) return null;
        Flow f = new Flow(sid, fresh(), fresh(), issuer, CLIENT, now);
        pending.put(f.state(), f);
        return f;
    }

    VerifiedIdToken token(Flow f, String issuer, String user) {
        return new VerifiedIdToken(issuer, user, CLIENT, f.nonce(), true);
    }

    Outcome finish(String sid, String state, VerifiedIdToken token, Instant now) {
        Session browser = sessions.get(sid);
        if (browser == null) return new Outcome(false, "unknown-session", null);
        if (state == null || state.isBlank()) {
            return new Outcome(false, "missing-state", sid);
        }
        Flow f = pending.get(state);
        if (f == null) return new Outcome(false, "unsolicited-or-replay", sid);
        if (!sid.equals(f.sessionId())) {
            // A foreign browser must not consume the real browser's flow.
            return new Outcome(false, "cross-browser", sid);
        }
        if (now.isBefore(f.started()) ||
            !now.isBefore(f.started().plus(FLOW_TTL))) {
            pending.remove(state, f);
            return new Outcome(false, "expired-flow", sid);
        }
        if (!pending.remove(state, f)) {
            return new Outcome(false, "concurrent-replay", sid);
        }
        if (token == null || !token.signatureValid() ||
            token.subject() == null || token.subject().isBlank() ||
            !f.expectedIssuer().equals(token.issuer()) ||
            !f.audience().equals(token.audience()) ||
            !f.nonce().equals(token.nonce())) {
            return new Outcome(false, "invalid-id-token", sid);
        }

        Identity incoming = new Identity(token.issuer(), token.subject());
        if (browser.user() != null && !browser.user().equals(incoming)) {
            // Explicit logout/account switch required; keep existing identity.
            return new Outcome(false, "account-switch-requires-consent", sid);
        }
        // Successful authentication gets a NEW session, not a reused pre-session.
        sessions.remove(sid);
        Session authenticated = new Session(fresh(), incoming);
        sessions.put(authenticated.id(), authenticated);
        return new Outcome(true, "authenticated", authenticated.id());
    }

    static void expect(String name, boolean condition) {
        System.out.println(name + "=" + condition);
    }

    public static void main(String[] args) {
        LoginCsrfSessionDemo app = new LoginCsrfSessionDemo();
        Session a = app.newBrowser();
        expect("startRequiresUserIntent",
            app.initiate(a.id(), IDP_A, false, NOW) == null);

        Flow good = app.initiate(a.id(), IDP_A, true, NOW);
        Outcome ok = app.finish(a.id(), good.state(),
            app.token(good, IDP_A, "alice"), NOW.plusSeconds(3));
        expect("legitimateLoginAccepted", ok.accepted());
        expect("sessionRotated", !a.id().equals(ok.sessionId()));
        expect("oldSessionRejected", !app.finish(
            a.id(), good.state(), app.token(good, IDP_A, "alice"),
            NOW.plusSeconds(4)).accepted());
        expect("replayedStateRejected", !app.finish(
            ok.sessionId(), good.state(), app.token(good, IDP_A, "alice"),
            NOW.plusSeconds(4)).accepted());

        Session b = app.newBrowser();
        expect("unsolicitedCallbackRejected", !app.finish(
            b.id(), "not-issued-by-app",
            new VerifiedIdToken(IDP_A, "mallory", CLIENT, "x", true),
            NOW).accepted());
        expect("missingStateRejected", !app.finish(
            b.id(), null, null, NOW).accepted());

        Flow foreign = app.initiate(b.id(), IDP_A, true, NOW);
        Session c = app.newBrowser();
        expect("crossBrowserStateRejected", !app.finish(
            c.id(), foreign.state(), app.token(foreign, IDP_A, "alice"),
            NOW.plusSeconds(2)).accepted());
        expect("crossBrowserAttemptDoesNotConsumeOwnerFlow",
            app.finish(b.id(), foreign.state(),
                app.token(foreign, IDP_A, "alice"), NOW.plusSeconds(3))
                .accepted());

        Session d = app.newBrowser();
        Flow wrongIssuer = app.initiate(d.id(), IDP_A, true, NOW);
        expect("issuerMixupRejected", !app.finish(
            d.id(), wrongIssuer.state(),
            app.token(wrongIssuer, IDP_B, "alice"),
            NOW.plusSeconds(2)).accepted());

        Flow noProof = app.initiate(d.id(), IDP_A, true, NOW);
        expect("invalidTokenProofRejected", !app.finish(
            d.id(), noProof.state(),
            new VerifiedIdToken(IDP_A, "alice", CLIENT,
                noProof.nonce(), false), NOW.plusSeconds(2)).accepted());

        Flow nonce = app.initiate(d.id(), IDP_A, true, NOW);
        expect("nonceMismatchRejected", !app.finish(
            d.id(), nonce.state(),
            new VerifiedIdToken(IDP_A, "alice", CLIENT, "wrong", true),
            NOW.plusSeconds(2)).accepted());

        Flow audience = app.initiate(d.id(), IDP_A, true, NOW);
        expect("audienceMismatchRejected", !app.finish(
            d.id(), audience.state(),
            new VerifiedIdToken(IDP_A, "alice", "other-client",
                audience.nonce(), true), NOW.plusSeconds(2)).accepted());

        Flow expired = app.initiate(d.id(), IDP_A, true, NOW);
        expect("expiredStateRejected", !app.finish(
            d.id(), expired.state(), app.token(expired, IDP_A, "alice"),
            NOW.plusSeconds(301)).accepted());

        Flow alice = app.initiate(d.id(), IDP_A, true, NOW);
        Outcome loginAlice = app.finish(d.id(), alice.state(),
            app.token(alice, IDP_A, "alice"), NOW.plusSeconds(1));
        Flow mallory = app.initiate(loginAlice.sessionId(), IDP_A, true, NOW);
        expect("silentAccountSwitchRejected", !app.finish(
            loginAlice.sessionId(), mallory.state(),
            app.token(mallory, IDP_A, "mallory"),
            NOW.plusSeconds(2)).accepted());
        expect("existingAccountUnchanged",
            "alice".equals(app.sessions.get(loginAlice.sessionId()).user().subject()));

        Flow same = app.initiate(loginAlice.sessionId(), IDP_A, true, NOW);
        Outcome sameUser = app.finish(loginAlice.sessionId(), same.state(),
            app.token(same, IDP_A, "alice"), NOW.plusSeconds(2));
        expect("sameAccountReauthenticationAccepted", sameUser.accepted());
        expect("reauthenticationRotatesSession",
            !loginAlice.sessionId().equals(sameUser.sessionId()));

        Flow old = app.initiate(sameUser.sessionId(), IDP_A, true, NOW);
        expect("stateTamperingRejected", !app.finish(
            sameUser.sessionId(), old.state() + "x",
            app.token(old, IDP_A, "alice"), NOW.plusSeconds(2)).accepted());
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 LoginCsrfSessionDemo.java
java LoginCsrfSessionDemo
~~~

**Exact stdout after compiling/running:**

~~~text
startRequiresUserIntent=true
legitimateLoginAccepted=true
sessionRotated=true
oldSessionRejected=true
replayedStateRejected=true
unsolicitedCallbackRejected=true
missingStateRejected=true
crossBrowserStateRejected=true
crossBrowserAttemptDoesNotConsumeOwnerFlow=true
issuerMixupRejected=true
invalidTokenProofRejected=true
nonceMismatchRejected=true
audienceMismatchRejected=true
expiredStateRejected=true
silentAccountSwitchRejected=true
existingAccountUnchanged=true
sameAccountReauthenticationAccepted=true
reauthenticationRotatesSession=true
stateTamperingRejected=true
~~~

Important explanations:

- **startRequiresUserIntent=true:** the model only allows initiating a flow after the user-intent condition is checked. Production must enforce that check with real CSRF/confirmation.
- **sessionRotated=true** and **oldSessionRejected=true:** never re-promote a pre-session ID into an authenticated session.
- **replayedStateRejected=true**, **unsolicitedCallbackRejected=true**, and **missingStateRejected=true:** reject callbacks without a transaction or with an already-used transaction.
- **crossBrowserStateRejected=true:** browser B's state cannot be used to log in browser C. The next test shows B can still complete its valid flow.
- **issuerMixupRejected=true**, **nonceMismatchRejected=true**, and **audienceMismatchRejected=true:** each binding type is verified independently.
- **silentAccountSwitchRejected=true:** Mallory's callback does not automatically replace Alice's session.
- **sameAccountReauthenticationAccepted=true** and **reauthenticationRotatesSession=true:** reauth for the same subject is permitted with a fresh session.
- **stateTamperingRejected=true:** modified state values fail verification.

**Do not use the demo as security middleware.** It does not implement OAuth code exchange, PKCE, TLS, JWT signature verification, SAML XML validation, browser cookies, clustered session cleanup, atomic state stores, or real authorization.

## 15. Spring MockMvc / Integration Testing Strategy

Testing **form login**:

~~~java
// Spring Security Test fragment; requires MockMvc + static imports.
mockMvc.perform(post("/login")
    .param("username", "mallory")
    .param("password", "example-password"))
  .andExpect(status().isForbidden());

mockMvc.perform(post("/login").with(csrf())
    .param("username", "alice")
    .param("password", "example-password"));
// A valid CSRF token does not mean login succeeded:
// AuthenticationProvider still must authenticate real credentials.
~~~

Testing an **OAuth callback** without a pending flow:

~~~http
GET /login/oauth2/code/corp?code=attacker-code&state=made-up HTTP/1.1
Cookie: JSESSIONID=pre-session-without-authorization-request
~~~

Expected: **do not create an Authentication**, do not link accounts, and do not call the wrong issuer's token endpoint. The status may be 302 to a login error page or 401 depending on the failure handler, so **do not assert only the status**.

Testing **cross-browser**:

~~~text
Browser A creates pending state A1.
Browser B has a different HttpSession.
B calls callback code=...&state=A1.

Expected:
  Reject B, do not create a session under user A in B.
  A has a clear policy to handle transaction A1.
~~~

Testing **account switch**:

~~~text
Browser has Alice's session.
An IdP-valid callback for Mallory arrives.
No approved account-switch transaction exists.

Expected:
  Alice is not replaced with Mallory.
  Alice's SavedRequest/cart/roles/tenant cache are not used for Mallory.
  If switching is allowed, it must go through confirmation/reauth and a fresh session.
~~~

Testing **SAML ACS** requires signed mock responses/assertions in a test environment or test IdP—never use an unsigned XML string and mark it authenticated.

## 16. Negative Test Matrix

| Test | Input | Expected |
| --- | --- | --- |
| Form login without CSRF | POST /login + attacker credentials | 403/deny, no auth |
| Wrong form token | Browser B's token used in A | Deny |
| Pre-session reuse | Pre-login session ID still works after | Deny if policy requires fresh ID |
| Valid form token + wrong password | Valid `_csrf` but wrong credentials | Not authenticated |
| OIDC callback missing state | Code present, no state | Deny |
| OIDC callback empty state | `state=` | Deny |
| State without pending flow | Attacker-invented state | Deny |
| State from another browser | B takes A's state | Deny |
| State replay | Callback already succeeded earlier | Deny |
| Expired state | Authorization request past TTL | Deny |
| Duplicate state | `state=A&state=B` | Deny ambiguity |
| Duplicate code | `code=A&code=B` | Deny ambiguity |
| Issuer mix-up | Request IdP A, response B | Deny before wrong code exchange |
| Wrong OIDC nonce | ID Token nonce differs from transaction | Deny |
| Invalid ID Token signature | Forged token | Deny |
| Expired ID Token | `exp` past due | Deny |
| Wrong audience | ID Token aud differs from client | Deny |
| PKCE verifier mismatch | Code/challenge mismatch | Token exchange fails |
| PKCE downgrade | AS does not enforce per client assumption | Deny/mitigate per RFC9700 |
| Wrong redirect URI | Unregistered client URI | Deny |
| Open redirect | External login returnUrl | Deny |
| Unsolicited OAuth callback | No transaction | Deny |
| Cross-site forced login initiation | Attacker leads browser to start GET | Not treated by default as approved account switch/link |
| Current user Alice, callback Mallory | No switch intent | Do not replace Alice |
| Same email, different issuer | Matching email but different `iss/sub` | Do not merge accounts |
| Account linking injection | Link IdP B from attacker callback | Do not link without approval transaction |
| SAML SP-init InResponseTo mismatch | Wrong AuthnRequest ID | Deny |
| SAML SP-init missing request | No pending request | Deny if SP-init only |
| Wrong SAML issuer/cert | Signature from untrusted IdP | Deny |
| Wrong SAML audience/destination | Assertion for another SP | Deny |
| SAML replay | Already-used Response/Assertion ID | Deny |
| SAML expired conditions | NotOnOrAfter past due | Deny |
| Unintentionally open IdP-init SAML | Unknown IdP sends unsolicited response | Deny |
| IdP-init user switch | Bob's signed response during Alice's session | No silent switch |
| SAML RelayState external URL | Attacker return URL | Deny/open-redirect protection |
| CAS ticket wrong service | ST issued for another app | CAS validation fails |
| CAS ST reuse | Already-consumed ticket | CAS validation fails |
| SPNEGO account switch | OS user differs from app session | Do not keep old principal's roles |
| Proxy missing identity header | Old local JSESSIONID remains | Fail closed if contract requires header |
| Proxy new header Bob | Local session Alice | Invalidate/switch policy |
| Local user disabled | IdP token still valid | Deny local user |
| Roles revoked | Old session still holds ROLE_ADMIN | Refresh/invalidate per policy |
| SAML SameSite Lax POST | Pre-session cookie not sent | Fail closed; fix cookie/correlation |
| OAuth Strict cookie | GET callback loses pre-session | Fail closed, do not drop state |
| Multi-tab overwrite | Pending state A overwritten by B | Reject without mixing flows |
| Multi-node replay | State exists across two nodes | Atomic one-time consume |
| Pending flow after logout | Old callback after logout | Reject per policy |
| Cookie session fixation | Predictable/fixed ID | New session ID and old invalidation |
| Logs leaking code/state | Proxy logs full callback URL | Redact, incident response |

**Tests must verify principal/account/session/roles and actual data received**, not just HTTP status. A failing callback may return a 302 to the login page and still be safe if it **never alters Authentication**.

## 17. Troubleshooting

| Symptom | Likely Cause | How to Check |
| --- | --- | --- |
| POST /login 403 | Missing CSRF token/wrong pre-session | Login view, CsrfTokenRepository, cookie |
| OIDC reaches callback but fails | State/pending authorization request not found | HttpSessionOAuth2AuthorizationRequestRepository |
| OAuth fails only with SameSite Strict | RP cookie omitted on redirect | Cookie Path/SameSite, browser network trace |
| SAML ACS POST loses request | SameSite=Lax blocks cross-site POST | Cookie profile and SAML AuthnRequest repository |
| OIDC wrong nonce | Transaction overwritten/mixed up | Per-flow nonce, multiple tabs |
| User swapped after callback | Missing account-switch policy | Current authenticated principal vs verified new one |
| OIDC callback hits wrong token endpoint | Provider/issuer mix-up | RFC9207 iss, expected issuer, registrations |
| Unintended IdP-init SAML enters app | Unsolicited allowed too broadly | IdP registration, SP-init policy |
| Signed SAML Response rejected | InResponseTo/audience/recipient mismatch | AuthnRequest, assertion, clock |
| OIDC/SAML flow fails with multiple tabs | Single pending flow or bad browser binding | Per-state store, concurrent flows |
| Previous user's cart remains after login | Session data migrated | newSession/invalidation/business state cleanup |
| Same session ID remains after login | Custom auth bypassed fixation strategy | SessionAuthenticationStrategy |
| Session auto-logs in after local logout | IdP SSO session still active | Upstream logout vs local |
| Request after custom login is anonymous | Context not saved | SecurityContextRepository |
| Multi-node callbacks yield different results | Local state store, cache/sticky sessions | Redis/JDBC atomicity/binding |
| Open redirect on error | Return URL not allowlisted | SavedRequest/redirect config |
| Logs leak state/code/nonce | APM/proxy logging raw query | Redact sensitive auth parameters |

### 17.1. Runbook

1. Classify the flow: form, OAuth/OIDC, SAML SP-init/IdP-init, CAS, SPNEGO, or proxy.
2. Determine whether the browser before callback held a local session for Alice/Bob or was anonymous.
3. Locate the pending transaction via an **internal correlation reference**, without pulling raw state/tokens from production logs.
4. Verify client/issuer/binding/TTL/one-time consume, nonce/PKCE, or SAML InResponseTo.
5. Verify protocol signature, audience, recipient, time, and replay.
6. Check account-switch user intent, local user/tenant mapping, and authority revocation.
7. Check session ID before/after login, saved request, pre-session attrs, and old session invalidation.
8. Check cookie Secure/HttpOnly/SameSite/Path, TLS termination, multiple tabs, and multi-node.
9. Audit logs so credentials never leak; log reason codes, correlation, and provider/policy version.
10. Patch with integration tests; never disable CSRF/state/InResponseTo to silence errors.

## 18. Production Design Process

1. Inventory all login entrypoints: `/login`, `/oauth2/authorization/*`, `/login/oauth2/code/*`, `/saml2/authenticate/*`, ACS, CAS callback, proxy identity, account-link/switch.
2. Decide which flows require explicit user intent vs which may use IdP-init/automatic SSO, with risk acceptance.
3. Design pending login transactions per protocol: state/nonce/PKCE or AuthnRequest ID, issuer, client, browser binding, TTL.
4. Configure framework repositories safely; if using a distributed cache, enforce atomic consume and session binding.
5. Enable protocol validation of issuer/signature/audience/recipient/timestamps/replay.
6. With multiple IdPs, defend against mix-up and never send codes to attacker-controlled token endpoints.
7. Separate unauthenticated pre-sessions from authenticated sessions, with fixation protection + clearing stale business state.
8. Define explicit account-switch confirmation/reauth/account linking, never letting a random login response overwrite a user.
9. Use stable identity keys issuer+tenant+subject and local user policy; never merge by email.
10. Configure HTTPS, cookies, SameSite for OIDC GET/SAML POST, CSRF on forms/business actions, and redirect allowlists.
11. Test multi-tab/multi-node, replay, cross-browser callbacks, wrong issuer, wrong account, and stale sessions.
12. Set up monitoring, log redaction, and a runbook for session revocation/data repair if login CSRF is detected.

## 19. Security Checklist

- [ ] CSRF protection for login POST and logout POST works properly.
- [ ] Pre-session CSRF token is browser-bound; authenticated sessions receive a new ID and clean user data.
- [ ] OIDC callbacks without a pending authorization request are rejected.
- [ ] `state` is random, time-bounded, single-use, and session/browser-bound; check duplicate parameters.
- [ ] OIDC nonce and PKCE are used/checked per profile and RFC 9700.
- [ ] Multiple providers have issuer mix-up defense before code exchange.
- [ ] ID Token signature, issuer, audience, exp, nonce, and required claims are validated.
- [ ] Never select token endpoint/client registration/redirectUri from an unverified query parameter.
- [ ] Login start GET is not treated on its own as user intent to link/switch accounts.
- [ ] SAML SP-init has AuthnRequest repository, InResponseTo correlation, and browser binding.
- [ ] SAML assertion signature, issuer, audience, recipient, destination, conditions, and replay are checked.
- [ ] IdP-initiated SAML is enabled only by policy and never silently replaces the current user.
- [ ] RelayState/returnUrl cannot cause open redirects or prove SP-init by itself.
- [ ] CAS Service Ticket matches the exact service and is not reused; app still checks login/session policy.
- [ ] SPNEGO/proxy identity changes never retain old principal/roles.
- [ ] Current user Alice cannot be silently replaced by Mallory's callback without consent/reauth.
- [ ] Account linking has a transaction, CSRF, reauthentication, and trusted identity binding.
- [ ] Local identity key binds issuer/tenant/stable subject, not email alone.
- [ ] Spring SecurityContextRepository/session persistence and invalidation match the exact version.
- [ ] Session fixation protection is not disabled; old user attrs are not migrated.
- [ ] Cookies Secure/HttpOnly/SameSite and SAML cross-site POST/OIDC GET callbacks are tested.
- [ ] Multiple tabs/providers/nodes execute concurrently without mixing states.
- [ ] Login/logout/response errors never create an authenticated session against policy.
- [ ] Logs contain no state, nonce, code, code_verifier, tokens, assertions, tickets, cookies/passwords.
- [ ] Regression tests cover login CSRF, response injection, unsolicited SAML, AS mix-up, silent switch, state replay, cross-browser, and open redirect.
- [ ] Alerts exist for login anomalies, session revocation, and incident handling.

## 20. Self-Check Questions

**1. How does login CSRF differ from taking over a victim's account?**

Login CSRF can force the **victim to use the attacker's account**, putting their own data into that account. The attacker does not need the victim's password.

**2. Why does a login form need a CSRF token even when the user is unauthenticated?**

Because another website can still force the browser to POST the attacker's credentials. A pre-session/CSRF token blocks POSTs not originating from the legitimate browser.

**3. Is a random `state` in a global cache enough protection?**

No, not without **browser/session binding**. The attacker's browser response/state can be carried to another browser and looked up by state.

**4. Does OAuth `state` prove the user intended to log in?**

Not necessarily. Another site can navigate the browser to the start GET, causing the RP to generate a valid state. Account switching/linking requires explicit intent/confirmation.

**5. Can PKCE protect against CSRF?**

Yes, under **RFC 9700** conditions—specifically ensuring the AS supports and enforces PKCE; it does not hold automatically when the AS can be downgraded.

**6. How does OIDC nonce differ from state?**

Nonce binds the request to the ID Token and is checked in the `nonce` claim; state binds the authorization response to the browser's authorization request.

**7. Why check issuer before token exchange when using multiple ASes?**

To prevent **mix-up**, stopping the RP from sending codes/credentials to the wrong token endpoint based on a mixed-up response.

**8. What is `InResponseTo` used for in SAML?**

Correlating the SAML Response/SubjectConfirmation with the SP-created AuthnRequest, identifying which flow the response belongs to.

**9. Is IdP-initiated SAML always forbidden?**

No. However, it lacks an SP AuthnRequest and carries unsolicited-login risk, so permit it only by policy with strict checks.

**10. Is a SAML assertion with a valid signature enough to log in?**

Not yet. You also need issuer, audience, recipient, conditions, replay, SP-init correlation or unsolicited policy, and local account/session consent.

**11. What issue does `SameSite=Lax` cause for SAML ACS?**

Browsers normally omit session cookies on cross-site POSTs from the IdP, causing the SP to lose the stored AuthnRequest; do not “fix” this by dropping correlation.

**12. How does session fixation differ from session swapping?**

Fixation concerns a session **ID known to the attacker**; swapping concerns an unexpected **identity/account**. Rotating the ID does not automatically guarantee the right user.

**13. What if the current user is Alice and a valid callback for Mallory arrives?**

Under the safe default policy, **do not silently replace Alice**. Require an approved switch and a clean new session, or reject.

**14. Why can a user still SSO again after local logout?**

Because the IdP session remains alive, allowing a fresh login. Local sessions and upstream SSO sessions have separate lifecycles.

**15. Can accounts be linked based on matching email?**

Not automatically. Use stable issuer+subject/tenant and explicit account-linking consent/reauth.

**16. Is checking only the HTTP status in callback tests enough?**

No. You must assert principal/session/roles/account linkage and downstream token exchange/issuer; failures may legitimately return a 302 redirect.

## 21. References

- OWASP **CSRF Prevention Cheat Sheet**, login forms and pre-session: https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html
- OWASP **Session Management Cheat Sheet**, session fixation/rotation/logout: https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
- OWASP **Authentication Cheat Sheet**: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
- Spring Security **CSRF for Servlet**, protecting login/logout: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Spring Security **OAuth2 Login Advanced Configuration**, authorization request repository and callback URLs: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html
- Spring Security **SAML 2.0 AuthnRequests**, HttpSession/Cache request repository and login fixation warning: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html
- Spring Security **Session Management**, fixation/newSession/explicit save: https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html
- IETF **RFC 9700 — OAuth 2.0 Security BCP**, state, PKCE, nonce, issuer mix-up, redirect URI: https://www.rfc-editor.org/rfc/rfc9700
- IETF **RFC 9207 — OAuth Authorization Server Issuer Identification**: https://www.rfc-editor.org/rfc/rfc9207
- IETF **RFC 7636 — PKCE**: https://www.rfc-editor.org/rfc/rfc7636
- OpenID Connect **Core 1.0**, nonce, issuer/audience, and ID Token validation: https://openid.net/specs/openid-connect-core-1_0.html
- OASIS **SAML 2.0 Core**: https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf
- OASIS **SAML 2.0 Profiles**: https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf
- Spring Security **Servlet Logout**, SecurityContext/session cleanup: https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html

**Remember:** **Login CSRF** can make a user **log into an attacker's account** without ever leaking a password. With Spring Security federation, you must separate **form CSRF tokens**, **browser-correlated SSO redirect transactions** (`state`/PKCE/nonce or SAML `InResponseTo`), **right IdP/issuer**, **signature and claims verification**, **account-switch policy**, and **session fixation/rotation**. If a callback is unsolicited, lacks state, comes from the wrong browser, is replayed, has the wrong issuer, lacks required assertion correlation, or tries to switch identities unexpectedly: **fail closed**, do not create an authenticated session, and never carry old account authorities/data into a new account.