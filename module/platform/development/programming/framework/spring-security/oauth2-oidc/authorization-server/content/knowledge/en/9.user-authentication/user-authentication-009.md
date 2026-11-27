# Controlling Re-Authentication Experience and Protecting Login Page Data

> **Chapter: User Authentication.** This lesson belongs to the **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER** module, guiding you on designing, configuring, securing, testing, and operating an OAuth 2.0/OpenID Connect Authorization Server using Spring Security and Spring Authorization Server in a Spring Boot application. It focuses on **when to prompt users to log in again**, **how to return to the exact OIDC transaction** after authentication, and **how to protect user data on the login page**.

## 1. Why Does the Re-Authentication Experience Belong to the Authorization Server?

An application signed in through OpenID Connect (OIDC) may have **two separate sessions**: the client application's session (Relying Party, RP) and the login session at the Authorization Server/OpenID Provider (OP). When a user already holds an OP session, visiting another app can authenticate via the existing session (SSO). Yet for sensitive actions like changing a password, viewing sensitive profile data, or confirming a payment, the RP may require a **fresh authentication** rather than simply accepting old session state.

Running example throughout this lesson:

- **OP/Authorization Server:** `https://login.example.vn`, issuer `https://login.example.vn`.
- **Client application:** `https://portal.example.vn`, `client_id=portal-web`, callback `https://portal.example.vn/login/oauth2/code/portal`.
- **OP login page:** `https://login.example.vn/login`.
- **Sensitive action:** a user with an active RP session wants to view highly protected account details; the RP asks the OP for recent authentication via `max_age` or `prompt=login`.

There are three distinct questions:

| Question | Primarily Responsible Component |
|---|---|
| Does the user have a valid **OP session**? | Spring Security on the Authorization Server: `SecurityContext`, session, and authentication mechanisms |
| Has the user **actively authenticated** recently? | OP re-authentication policy: actual login timestamp, `prompt`, `max_age`, MFA/step-up |
| When can the client trust the user was authenticated? | RP verifies an ID Token with a valid signature, `iss`, `aud`, `nonce`, `auth_time`, and session policy |

**Do not equate** an unexpired session, existing cookie, valid access token, or a fresh ID Token `iat` with **the user having just actively logged in**. If the OP mints a new ID Token from an old SSO session, `iat` will be recent while `auth_time` remains the authentication timestamp from hours earlier.

## 2. OIDC Parameters Controlling Re-Authentication

OpenID Connect Core 1.0 defines parameters in the authorization request so an RP can request specific authentication behavior. They arrive at `/oauth2/authorize`, **not** as arbitrary query parameters on `/login`.

| Parameter | Example | OIDC Meaning | Implementation Notes |
|---|---|---|---|
| `prompt=login` | `prompt=login` | The OP **SHOULD** prompt the user to re-authenticate; if unable to do so, it must return an error, typically `login_required` | Requires a real fresh authentication flow, not merely re-rendering and skipping the form |
| `max_age` | `max_age=300` | Maximum elapsed seconds since **active authentication**; if exceeded, the OP **MUST** attempt re-authentication | When `max_age` is used, **the ID Token MUST include `auth_time`** |
| `max_age=0` | `max_age=0` | Per OIDC, equivalent to requesting `prompt=login` | Used when forcing fresh authentication for this transaction |
| `prompt=none` | `prompt=none` | The OP **MUST NOT** display login or consent UI | If interaction is needed, return an OIDC error such as `login_required` or `consent_required` as appropriate |
| `prompt=consent` | `prompt=consent` | Requests re-prompting for authorization consent | **Consent** does not mean the user re-authenticated |
| `prompt=select_account` | `prompt=select_account` | Prompts the user to select an account when the OP supports multiple sessions/accounts | Account selection alone does not prove sufficient authentication |
| `login_hint` | `login_hint=alice%40example.vn` | Identity hint for pre-filling/display | **Untrusted input**; never assume it proves identity |
| `ui_locales` | `ui_locales=vi%20en` | Preferred UI language hints | Validate against supported locales; never inject raw strings into HTML |
| `acr_values` | `acr_values=urn%3Aexample%3Aloa%3A2` | Requested authentication assurance context/level | Must be backed by real enforcement policy; never merely copy into the ID Token |

`prompt` may hold a space-delimited list, such as `prompt=login consent`. **`none` must never appear alongside another prompt value**. RPs must handle valid OIDC errors; OPs must validate the request and registered redirect URI **before** returning errors through the browser.

### 2.1. Differences Between `auth_time`, `iat`, Session Lifetime, and Tokens

Illustrative ID Token:

~~~json
{
  "iss": "https://login.example.vn",
  "sub": "user-123",
  "aud": "portal-web",
  "iat": 1794825600,
  "exp": 1794825900,
  "auth_time": 1794796800,
  "nonce": "NONCE_FROM_AUTHORIZATION_REQUEST"
}
~~~

This is an **illustrative payload only**, not a validly signed JWT. `iat` tells when the ID Token was issued, `exp` tells when it expires, and `auth_time` tells when the user **actively authenticated**. A freshly minted ID Token does not prove active authentication just occurred.

When an RP sends `max_age=300`, the OP must consult the **real authentication timestamp** to decide whether re-interaction is needed. Afterward, the RP also compares the ID Token's `auth_time` against its requested policy, alongside verifying signature, `iss`, `aud`, `exp`, and `nonce` where applicable. Never assign `auth_time = Instant.now()` merely because a token was minted from an existing SSO session.

### 2.2. Re-Authentication Method Must Meet the Required Assurance Level

Re-authentication may use a password, passkey/WebAuthn, MFA, or another policy-approved mechanism. For high-risk transactions, merely re-showing a login page or trusting an old session cookie is insufficient; the OP must execute fresh authentication meeting the required assurance level. If `acr_values`/step-up is implemented, evaluate the methods used (`amr`) and authentication context (`acr`) based on real evidence.

**Library support note:** OIDC Core specifies protocol requirements; default `formLogin()` and `server.oidc(...)` configurations do not guarantee every variant of `prompt`, `max_age`, `auth_time`, MFA, or account selection matches your product policy out of the box. You must **test each parameter on your exact Spring Security/Spring Authorization Server version** and add controlled handling where gaps exist.

## 3. Flow: SSO, Re-Authentication, and Returning to the Original Request

~~~mermaid
sequenceDiagram
    autonumber
    participant Browser as Browser
    participant RP as OIDC Client (portal-web)
    participant OP as Authorization Server (login.example.vn)
    participant Login as Login Page / Authentication

    Browser->>RP: Request sensitive operation
    RP-->>Browser: Redirect /oauth2/authorize<br/>scope=openid, state, nonce, PKCE, max_age
    Browser->>OP: Authorization request
    OP->>OP: Validate client_id, redirect_uri, request
    OP->>OP: Read OP session, active auth time, prompt/max_age
    alt Session and auth_time satisfy policy
        OP->>OP: Proceed to consent evaluation and code issuance
    else Fresh auth required, interaction allowed
        OP-->>Browser: Redirect to GET /login (preserve request server-side)
        Browser->>Login: Render form over HTTPS + CSRF
        Browser->>Login: POST /login, credentials + CSRF token
        Login->>OP: Perform real authentication and update auth_time
        OP->>OP: Restore saved authorization transaction
    else prompt=none and interaction required
        OP-->>Browser: OIDC error to validated redirect_uri
    end
    OP-->>Browser: Redirect callback?code=...&state=...
    Browser->>RP: Receive authorization code, state
    RP->>RP: Verify state and exchange code at token endpoint with PKCE
    OP-->>RP: Token response with ID Token
    RP->>RP: Verify signature, iss, aud, exp, nonce, auth_time
    RP-->>Browser: Allow operation if assurance meets requirement
~~~

For requests with `prompt=none`, the OP **must not** show a form. If no session exists or consent/reauth is needed, return an error via the authorization response to the **validated redirect URI**; never send errors or authorization codes to an unverified URI.

### 3.1. Safely Preserving the OAuth2/OIDC Transaction

Typical Spring Security flow:

1. The RP sends an authorization request to **`/oauth2/authorize`** with `client_id`, `redirect_uri`, `scope=openid`, `state`, `nonce`, PKCE, and any re-authentication parameters.
2. The Authorization Server validates client/redirect URI, then if the user needs authentication redirects to **`/login`**, using the session/request cache to return to the original request after login.
3. `POST /login` is processed by Spring Security; upon success, the original request is restored from **server-controlled state**, never from a user-supplied `returnUrl`.
4. The OP re-evaluates session, `prompt`/`max_age`, and consent rules before issuing the authorization code.
5. The RP verifies `state`, exchanges the code with PKCE, validates the ID Token, and decides whether to allow the sensitive operation.

**Avoid open redirects:** Never use `?next=https://arbitrary-domain.test`, a hidden `redirect` form field, or an unverified `Referer` as the post-login target. If the login page supports returning, rely exclusively on the server-side saved request and validate allowed targets. Protect the request cache from cross-tab/cross-session mix-ups; protocol-level OAuth2 `state`/`nonce` and redirect URI registration checks must still remain enforced.

### 3.2. Handling Account Switching

Suppose the browser was signed into account A, yet at the re-authentication screen the user signs into account B. The OP must issue codes/tokens for the identity **authenticated in the current flow**, rather than keeping A's `sub` or consent. The RP must anticipate that `sub` may change; for sensitive operations bound to account A, the RP must reject continuation or require initiating a transaction for B.

Guard against **login CSRF** and session confusion: an attacker must never be able to force a victim's browser into a session authenticated as an attacker-controlled account. Form login must enforce CSRF protection and proper session ID rotation.

## 4. Spring Boot / Spring Authorization Server Skeleton for the Login Page

The examples below target Spring Boot 3.x, Spring Security 6.x, and Spring Authorization Server 1.5.x. Packages and APIs may differ in other major versions. The setup uses **two filter chains**: one for protocol endpoints, one for the login page and standard application routes.

### 4.1. SecurityFilterChain for Authorization Server and Form Login

~~~java
import java.time.Instant;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.MediaType;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configurers.OAuth2AuthorizationServerConfigurer;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.LoginUrlAuthenticationEntryPoint;
import org.springframework.security.web.authentication.SavedRequestAwareAuthenticationSuccessHandler;
import org.springframework.security.web.header.writers.ReferrerPolicyHeaderWriter;
import org.springframework.security.web.util.matcher.MediaTypeRequestMatcher;

@Configuration(proxyBeanMethods = false)
@EnableWebSecurity
public class LoginSecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain authorizationServerChain(HttpSecurity http) throws Exception {
        OAuth2AuthorizationServerConfigurer authorizationServer =
                OAuth2AuthorizationServerConfigurer.authorizationServer();

        http.securityMatcher(authorizationServer.getEndpointsMatcher())
            .with(authorizationServer, server ->
                server.oidc(Customizer.withDefaults()))
            .authorizeHttpRequests(authorize ->
                authorize.anyRequest().authenticated())
            .exceptionHandling(errors ->
                errors.defaultAuthenticationEntryPointFor(
                    new LoginUrlAuthenticationEntryPoint("/login"),
                    new MediaTypeRequestMatcher(MediaType.TEXT_HTML)));

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain applicationChain(HttpSecurity http) throws Exception {
        SavedRequestAwareAuthenticationSuccessHandler savedRequestHandler =
                new SavedRequestAwareAuthenticationSuccessHandler();

        http.authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/login", "/assets/login/**").permitAll()
                .anyRequest().authenticated())
            .formLogin(form -> form
                .loginPage("/login")
                .successHandler((request, response, authentication) -> {
                    // Record timestamp only upon genuine form authentication success.
                    request.getSession().setAttribute(
                            "LAST_ACTIVE_AUTH_AT", Instant.now().getEpochSecond());
                    savedRequestHandler.onAuthenticationSuccess(
                            request, response, authentication);
                })
                .permitAll())
            .sessionManagement(session ->
                session.sessionFixation(fixation -> fixation.changeSessionId()))
            .headers(headers -> headers
                .cacheControl(Customizer.withDefaults())
                .referrerPolicy(referrer -> referrer.policy(
                    ReferrerPolicyHeaderWriter.ReferrerPolicy.NO_REFERRER))
                .contentSecurityPolicy(csp -> csp.policyDirectives(
                    "default-src 'none'; script-src 'self'; style-src 'self'; " +
                    "img-src 'self'; form-action 'self'; base-uri 'none'; " +
                    "frame-ancestors 'none'"))
                .frameOptions(frame -> frame.deny()));

        return http.build();
    }
}
~~~

Spring Security enables session fixation protection by default in standard setups; the snippet above explicitly specifies rotating the session ID upon successful authentication. `SavedRequestAwareAuthenticationSuccessHandler` preserves returning to the original request after form login succeeds.

**Important note on `LAST_ACTIVE_AUTH_AT`:** This only demonstrates recording the **form login** timestamp in the HTTP session. It does **not automatically** make Spring Authorization Server enforce `max_age`/`prompt=login`, store the timestamp inside `OAuth2Authorization`, or emit the `auth_time` claim in ID Tokens. In a full OIDC implementation, propagate a **trusted authentication record** through the authorization transaction, token issuance, and token customizer—compatible even when token exchange happens over a back-channel without browser cookies.

This example also omits `RegisteredClientRepository`, `UserDetailsService`/authentication providers, `JWKSource`, `JwtDecoder`, `AuthorizationServerSettings`, and authorization/consent persistence. Configure all of those components for a real deployment. If UserInfo is enabled, also add Bearer resource server support matching your version and endpoint needs.

### 4.2. Session Cookie Configuration in Production

~~~yaml
server:
  servlet:
    session:
      timeout: 20m
      cookie:
        http-only: true
        secure: true
        same-site: lax
~~~

- `http-only: true` restricts JavaScript from reading the session cookie; `secure: true` restricts transmission to HTTPS.
- `same-site: lax` generally fits Authorization Code Flow's top-level OIDC GET redirects, yet **must be tested** against your real domains, browsers, callback/response modes, and SSO mechanics. Certain cross-site POST or iframe flows have different needs; never switch to `SameSite=None` without a threat model and `Secure`.
- Session timeout bounds how long the OP session persists; it **does not replace `max_age`** and does not revoke already-issued JWT access tokens.
- Behind a reverse proxy or load balancer, verify TLS termination, trusted forwarded headers, and cookie domain/path; never trust `X-Forwarded-*` headers directly from the Internet.
- In multi-instance deployments, configure an appropriate session store or stickiness policy. Keep sessions, active-authentication records, and OAuth2 authorization objects consistent across instances.

**Never enable `SessionCreationPolicy.STATELESS` on a traditional form login + authorization redirect flow** unless you have designed a complete equivalent state architecture. Turning it stateless arbitrarily wipes saved requests, login sessions, and CSRF tokens.

## 5. Building a Custom Login Page Without Leaking Sensitive Data

Define a `GET /login` controller when using `.loginPage("/login")`:

~~~java
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
class LoginPageController {
    @GetMapping("/login")
    String loginPage() {
        return "login"; // src/main/resources/templates/login.html
    }
}
~~~

Abbreviated Thymeleaf view sample:

~~~html
<!doctype html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Secure Sign In</title>
  <link rel="stylesheet" th:href="@{/assets/login/login.css}">
</head>
<body>
<main>
  <h1>Sign In</h1>
  <p th:if="${param.error}" role="alert">
    Unable to sign in with the provided credentials.
  </p>
  <form th:action="@{/login}" method="post" autocomplete="on">
    <label for="username">Username</label>
    <input id="username" name="username" type="text"
           autocomplete="username" required>

    <label for="password">Password</label>
    <input id="password" name="password" type="password"
           autocomplete="current-password" required>

    <input type="hidden"
           th:name="${_csrf.parameterName}"
           th:value="${_csrf.token}">
    <button type="submit">Continue</button>
  </form>
</main>
</body>
</html>
~~~

**How this form works:**

- `GET /login` only renders the form over HTTPS; `POST /login` is handled by `UsernamePasswordAuthenticationFilter` since default `formLogin` uses the `username`/`password` parameter pair.
- The CSRF hidden input binds the token to the session. In standard Thymeleaf/Spring Security integrations, Spring can auto-inject the CSRF input via `RequestDataValueProcessor`; the snippet includes it **explicitly**, so avoid duplicating the input if your template engine already emits one. Verify the rendered HTML sends only **one** valid token.
- No `value` attribute on the password field; never store passwords in HTML, hidden fields, URLs, JavaScript, arbitrary session attributes, error messages, or logs.
- `autocomplete="username"` and `autocomplete="current-password"` support password managers; **do not** force-disable autocomplete as security theater.
- CSS and assets load from the same origin; never embed third-party resources on pages handling credentials.

In production, deploy MFA or passkeys/WebAuthn commensurate with your assurance level. When using OTPs, recovery codes, or WebAuthn challenges, enforce TTLs, attempt caps, and session binding; never display or record sensitive values in analytics.

### 5.1. Error Messages That Prevent Account Enumeration

Do not publicly distinguish messages like "this email does not exist," "wrong password," or "account locked after X attempts" if they help attackers enumerate identities. Use a consistent message:

> Unable to sign in with the provided credentials. Please check and try again.

Account recovery assistance should occur through a dedicated rate-limited channel with messages that do not disclose account status. Server logs may record **classified error codes** (bad credentials, locked, expired) under restricted access for investigations, minimizing personal data and never logging passwords/OTPs/tokens.

### 5.2. `login_hint` and RP-Supplied Data

An RP may suggest a username/email via `login_hint`, but the OP must treat it strictly as a **UX hint** after validating, bounding length, normalizing encoding, and HTML-escaping. Never use `login_hint` to mark an account authenticated, alter `sub`, or bypass authentication.

When displaying client names, logos, or redirect labels on login/consent screens, read them exclusively from a **trusted `RegisteredClient`** and escape upon rendering. Client metadata may arrive via dynamic registration; enforce validation, content review, and CSP before displaying it. Avoid rendering untrusted HTML via Thymeleaf `th:utext` or interpolating values into inline scripts.

## 6. Protecting HTML Responses and Data Passing Through the Browser

### 6.1. Key HTTP Response Headers

| Header / Policy | Recommended Value | Purpose |
|---|---|---|
| `Cache-Control` | `no-store` (optionally with `no-cache, max-age=0, must-revalidate`) | Prevents caching sensitive pages/responses in browser or proxy caches |
| `Pragma` / `Expires` | `no-cache` / `0` for legacy systems if needed | Legacy cache compatibility; does not replace `Cache-Control` |
| `Content-Security-Policy` | `default-src 'none'; script-src 'self'; style-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'` | Mitigates XSS, form hijacking, clickjacking, and unauthorized resource loads |
| `Referrer-Policy` | `no-referrer` | Prevents leaking URLs carrying query context to other sites via `Referer` |
| `X-Content-Type-Options` | `nosniff` | Prevents MIME sniffing |
| `Strict-Transport-Security` | HSTS policy tailored for production HTTPS domains | Enforces HTTPS in browsers once recorded |
| Cookie `Secure`, `HttpOnly`, `SameSite` | Per threat model; typically `Secure` + `HttpOnly` + `Lax` for top-level GET flows | Reduces cookie exposure and unwanted cross-site requests |

Spring Security provides default security headers, yet you must **inspect actual responses** after customizing, behind reverse proxies/CDNs, and across both the login page and OAuth2 redirects. The CSP in section 4 is a strict policy for a login page without inline scripts. If you add inline JavaScript, never carelessly add `'unsafe-inline'`; prefer first-party script files or CSP nonces/hashes.

**`Cache-Control` cannot erase data already captured** in logs, browser history, or screenshots. Focus on minimizing sensitive data exposure in the first place.

### 6.2. Preventing Credentials, Authorization Codes, and Identifiers from Leaking in URLs

- **Never send username/password/OTP in GET query strings**; submit credentials via HTTPS POST forms.
- Keep access tokens, ID Tokens, refresh tokens, authorization codes, and `code_verifier` out of login URLs, `returnUrl` queries, hidden inputs, and client-side analytics.
- OIDC authorization requests commonly carry `state`, `nonce`, `login_hint`, and occasionally other hint parameters. Limit URL/query logging and never forward them to third-party analytics on the login page.
- Post-login redirects must follow the saved request/valid OAuth2 flow. Never pass a client-supplied `next`/return URL directly into the `Location` header.
- Never set `Access-Control-Allow-Origin: *` on the login page/endpoint just to "fix CORS." The login page is a cookie-authenticated browser UI; configure CORS for specific use cases and never use CORS instead of CSRF protection.
- Do not turn the login page into a REST endpoint accepting and returning credentials in client-side browser JS if you intend to use Spring Security/Spring Authorization Server's standard redirect flow.

### 6.3. Defending the Login Page Against Attacks

| Risk | Defense |
|---|---|
| **CSRF / login CSRF** | Keep CSRF protection on `POST /login`, enforce session binding, verify token against active session |
| **XSS** | Output escaping, input validation, strict CSP, and first-party assets only; avoid raw HTML from `login_hint`/client metadata |
| **Clickjacking** | `frame-ancestors 'none'`, `X-Frame-Options: DENY` unless legitimate framing is required |
| **Session fixation** | Rotate session ID on successful authentication; `Secure`/`HttpOnly`/`SameSite` cookies; appropriate session timeout |
| **Credential stuffing / brute force** | Rate-limit by IP/account/device with lockout-abuse safeguards; anomaly detection, MFA/passkeys |
| **Phishing** | Consistent OP domain, valid TLS, clear issuer/organization branding; prefer phishing-resistant passkeys/WebAuthn |
| **Sensitive data in logs** | Mask/omit `POST /login` bodies, cookies, `Authorization` headers, OTPs, reset tokens, and personal-data responses |
| **Caching and third parties** | `no-store`, `Referrer-Policy: no-referrer`, strip unnecessary analytics, fonts, and scripts |

## 7. Designing Context-Aware Re-Authentication Policies

Do not force users to re-enter their password on every API call: excessive friction actually trains users to click blindly through phishing prompts. Tie re-authentication to **action sensitivity, session trust, and authentication age**.

| Action | Example Policy | Desired UX |
|---|---|---|
| Viewing public info pages | No authentication required | No login shown |
| Opening dashboard with an active OP SSO session | Valid OP session may be used | Skip form if policy allows |
| Viewing sensitive account details | `max_age=300` and suitable assurance | If active authentication is older than 5 minutes, require re-authentication |
| Changing password or recovery email | Require fresh authentication + risk-based MFA | Verify with strong method; never just extend cookie |
| Request includes `prompt=login` | Require re-authentication per OIDC | Do not complete solely on old SSO session |
| Silent SSO check with `prompt=none` | Prohibit interactive UI | Issue code if all checks pass; otherwise return OIDC error |
| Session expires while filling out form | Discard unsubmitted input; prompt to reload form/session | Simple message without echoing entered credentials |

Lifetimes and behaviors in this table are **policy examples**, not fixed OAuth2/OIDC mandates. If your product also requires validation at Resource Servers or RP backends, the RP must still enforce its own policy for sensitive actions. Sending `max_age` without verifying `auth_time` at the RP is an incomplete check.

### 7.1. Re-Authentication Decision Model (Pseudocode)

~~~text
input:
  validatedAuthorizationRequest
  currentUserAuthentication
  lastActiveAuthTimeFromTrustedStore
  prompt, max_age, consentState, requestedAcr
  currentTime

# Validate client_id, redirect_uri, PKCE/state/scope per earlier policy.
needsLogin = currentUserAuthentication is absent
needsFreshAuth = prompt contains "login"
if max_age is present:
    needsFreshAuth =
        needsFreshAuth
        OR lastActiveAuthTimeFromTrustedStore is absent
        OR max_age == 0
        OR (currentTime - lastActiveAuthTimeFromTrustedStore) > max_age

needsStepUp = requestedAcr is not satisfied by real authentication evidence
needsConsent = requested scopes require new consent

if prompt contains "none":
    if needsLogin OR needsFreshAuth OR needsStepUp:
        return OIDC_ERROR(login_required) to validated redirect_uri
    if needsConsent:
        return OIDC_ERROR(consent_required) to validated redirect_uri
    proceed without interactive UI
else:
    if needsLogin OR needsFreshAuth OR needsStepUp:
        start appropriate interactive authentication, preserving safe request state
    if needsConsent:
        show consent UI after identity/assurance verified
    proceed to authorization code issuance

# Bind actual authentication time to authorization transaction.
# When max_age was requested, include verified auth_time in ID Token.
~~~

This pseudocode expresses **intended policy**, **not code you can paste straight into a filter chain**. You must handle authentication/consent ordering, account switching, pending transactions, multi-tab concurrency, and timeouts. If `prompt` is invalid or the redirect URI is untrusted, return a protocol error **without redirecting to an unverified URI**.

### 7.2. Persisting `auth_time` in the Right Place

To emit an accurate `auth_time` on ID Tokens when token exchange occurs over the **back-channel**, the OP must preserve authentication facts from the authorization request through token issuance—for instance:

1. Upon completing **active authentication**, persist a trusted record containing user subject, timestamp, authentication method/assurance, session, and transaction context.
2. When handling `/oauth2/authorize`, compare `prompt`/`max_age` against that record; if insufficient, trigger login/step-up.
3. When minting the authorization code and saving the authorization object, bind the real authentication timestamp to that authorization; never rely on the token request's HTTP session because `/oauth2/token` normally arrives from the RP backend.
4. When building the ID Token via the appropriate hook/token customizer, read the authorization-bound record and include `auth_time` (NumericDate) when `max_age` was requested and per OIDC rules; never use `Instant.now()` at token minting as `auth_time`.
5. Test across multiple authentication providers (password, WebAuthn, federated IdP) and multiple server instances. Timestamps originating from an external IdP must be validated per your trust policy rather than blindly treating every federated session as fresh authentication.

Exact hooks depend on your Spring Authorization Server version and user authentication design. Never build around a request attribute that only survives `GET /login`, since that data vanishes before `POST /oauth2/token`.

## 8. Avoiding Re-Authentication Loops

A common bug redirects users from `/oauth2/authorize` to `/login`, then returns them to `/oauth2/authorize` after successful login only to treat them as **unauthenticated** or re-trigger `prompt=login` repeatedly—causing an infinite loop.

Typical causes:

- Session cookie withheld across domains/HTTPS/proxies or misconfigured `SameSite`.
- Request cache fails to preserve the original request due to session/stateless settings, filter chain ordering, or load balancer routing.
- `prompt=login` handler only inspects the query parameter without marking the transaction as freshly authenticated, forcing login again on every return to `/authorize`.
- `auth_time` is not updated after real authentication or is stored in pod-local memory not shared across pods.
- Multi-tab requests overwrite each other in session/request cache, mixing up `state`/nonce and saved requests.
- RP automatically restarts OIDC login upon receiving `login_required`, while the OP keeps returning errors due to policy or a blocked session.
- Login hint/account selector switches to another account while the transaction stays bound to the old `sub` and cannot complete.

**Remediation:** bind the fresh authentication outcome to the **pending authorization transaction** with explicit state/expiry, checking it once after login. Never "fix" a loop by disabling CSRF, relaxing redirect URI matching, skipping `state`, dropping `nonce`, or automatically treating every session as fresh.

Browsers restricting third-party cookies can make iframe-based silent authentication unreliable. Design the experience around safe **top-level redirects** with explicit RP handling for `login_required`.

## 9. Testing Security and the Re-Authentication Experience

Use real browsers or integration tests that manage cookies and sessions rather than static HTTP GET checks. For tokens/JWTs, use test keys and synthetic accounts, keeping real credentials out of logs and test reports.

| Test Case | Setup and Action | Expected Outcome |
|---|---|---|
| No OP session | RP initiates Authorization Code + PKCE | OP redirects to login; successful login resumes authenticated flow and returns code to exact redirect URI |
| Valid OP session exists | RP does not require fresh auth | Reuses SSO when policy permits; avoids unnecessary password prompts |
| `prompt=login` | RP requests fresh login while OP session exists | Enforces real re-authentication per policy; never issues code solely from cookie |
| `max_age=300`, authed 2 min ago | RP requires auth age within 5 minutes | May reuse session if other assurance checks pass; ID Token includes `auth_time` |
| `max_age=300`, authed 10 min ago | RP requires auth age within 5 minutes | Re-authenticates; ID Token's `auth_time` reflects the new auth timestamp |
| `max_age=0` | RP forces fresh auth | Behaves like `prompt=login`; ID Token includes `auth_time` per `max_age` |
| `prompt=none` without session | Cannot complete silently | Does not render login; returns proper OIDC error to validated redirect URI |
| `prompt=none` needing consent | Client requests unapproved scopes | Does not render consent page; returns OIDC error such as `consent_required` |
| `prompt=login none` | Incompatible prompt values | Request rejected per OIDC rules |
| Wrong password login | `POST /login` with valid CSRF | Friendly error, no user existence leak; no password/username leaked outside policy |
| Missing or invalid CSRF | `POST /login` missing/bad `_csrf` | Rejected; no session change or login |
| Session fixation | Compare session ID before and after successful login | ID rotates per config; attacker-planted pre-auth ID cannot access session |
| Session expiration | Authorization pending, cookie/session lost | Prompts safely for fresh login; never issues code from missing/invalid state |
| Account switch | Signed in as A, chooses B on reauth | Token uses B's `sub`; RP validates transaction/account binding for sensitive action |
| `login_hint` with HTML/script | Untrusted RP-supplied value | Escaped/truncated/validated; no XSS or script injection |
| `GET /login` via proxy | Inspect headers, HTTPS, cookies | CSP, `no-store`, `no-referrer`, and cookie flags match |
| Open redirect | Form/login link carries `next=https://evil.test` | Never redirects to arbitrary URL; returns only to valid saved request |
| Multi-tab browser | Two authorization requests with different `state` | Requests do not cross-contaminate; each RP gets its own transaction response |
| Credential stuffing | Repeated failures across IPs/accounts | Rate limiting, detection, MFA, and policy-compliant alerts without secret leaks |
| Distributed multi-pod | Login on pod A, authorize on pod B | Session/`auth_time`/request state stays valid via shared store or routing |

### 9.1. Verifying Response Headers

In a test environment with a real domain, inspect **headers only**:

~~~bash
curl -sSI https://login.example.vn/login
~~~

Verify `Cache-Control`, `Content-Security-Policy`, `Referrer-Policy`, `X-Content-Type-Options`, and HSTS match your deployment policy. Some login endpoints redirect if an active session or special config exists; inspect every hop in the redirect chain rather than judging only the final response.

Run a browser with Developer Tools to verify form POSTs send CSRF tokens and session cookies carry the right attributes. **Never** paste full request bodies or cookies into public tickets or test logs.

### 9.2. Verifying ID Token `auth_time`

The RP must inspect claims **only after verifying** the JWT signature, issuer, audience, expiration, and nonce. If `max_age` was requested and the ID Token lacks `auth_time`, the RP must treat it as **violating OIDC policy**. Validate `auth_time` against policy thresholds and bounded clock skew—do not check `iat` alone.

A crucial test: the RP sends a `max_age=0` request while the browser already holds an OP session, then verifies the server truly forces a fresh active authentication step and returns an ID Token whose `auth_time` matches that new authentication. A system that merely flashes UI without updating authentication proof is non-compliant.

### 9.3. Testing Across Spring Versions

APIs and behaviors can differ between Spring Authorization Server 1.x and the integrated modules in Spring Security 7.x. In particular, **`prompt=none` must be tested with real unauthenticated requests**, because filter ordering and authentication entry points determine whether `login_required` is returned or the request wrongly redirects to login.

Do not treat enabling `.oidc(Customizer.withDefaults())` as proof that all re-authentication requirements work. Document your Spring version, security filter order, and `prompt`/`max_age` matrix in your test suite for future upgrades.

## 10. Real-World Incidents and Troubleshooting Guide

| Symptom | Causes to Check | Resolution |
|---|---|---|
| Login succeeds yet never returns to client | Request cache lost state; redirect handler hardcodes target URL | Use safe saved request handling; check security filter chains and sessions |
| Infinite login loop | `prompt=login` lacks transaction freshness marker; session cookie dropped; `auth_time` not updated | Bind auth state per transaction; fix cookies/proxy/time; prevent loops |
| RP sends `max_age=0` yet SSO skips straight through | OP does not enforce `max_age` or checks session only | Add reauth enforcement, emit accurate `auth_time`, and add integration tests |
| `prompt=none` renders login form | Entry point/filter handles auth before OIDC error handling | Check filter ordering and version; add protocol-compliant error handling |
| Post-login returns `invalid_state` | OAuth2 `state` overwritten/lost, multi-tab collision, or session reset | Audit RP session, request state/cookies/PKCE; never disable `state` checks |
| User A re-authenticates and becomes B | Login/account selection fails to bind transaction to right subject | Enforce `sub`, consent, and account binding at OP/RP |
| `POST /login` returns 403 | Missing/bad CSRF token, mismatched session, reverse proxy/cookie bug | Check template `_csrf`, form action, cookies, and chain |
| Users can tell whether an account exists | Overly specific error messages or timing differences | Use generic messages; test timing and rate limits |
| Content Security Policy blocks login styles/scripts | Cross-origin assets, inline scripts, overly restrictive directives | Serve first-party assets with clean CSP; avoid unnecessary `unsafe-inline` |
| `login_hint` leaks to analytics | Login page loads third-party scripts/pixels or sends `Referer` | Remove trackers, limit query data, set `Referrer-Policy: no-referrer` |
| Cookies dropped after redirect | Wrong `Secure`/`SameSite`/domain/path/TLS termination | Test real browser against public endpoints; fix trusted proxy config |
| JWT ID Token shows fresh `auth_time` despite no reauth | Claim assigned at token minting instead of active authentication | Propagate trusted auth timestamp across authorization and token exchange |

## 11. Security, Operations, and Privacy Checklist

- [ ] Clearly define fresh-authentication policies for standard SSO, sensitive actions, and MFA/step-up.
- [ ] Support `prompt=login`, `max_age`, and `prompt=none` per OIDC; test both **with an active OP session** and **without an OP session**.
- [ ] Track the **real active authentication** timestamp, bind it to authorizations, and emit `auth_time` when `max_age` is requested.
- [ ] RP verifies ID Token, `auth_time`, `iss`, `aud`, `exp`, `nonce`, and `sub` before permitting sensitive operations.
- [ ] Form `POST /login` uses HTTPS + CSRF; session ID rotates after login; cookies set `Secure`/`HttpOnly`/`SameSite` properly.
- [ ] Login page enforces CSP, `no-store`, `no-referrer`, with no third-party scripts or credentials/authorization data sent to analytics.
- [ ] Passwords/OTPs submitted strictly via POST; never stored in query strings, hidden return URLs, logs, or DOM attributes.
- [ ] Error messages do not disclose account existence; rate limiting, credential-stuffing detection, and MFA/passkeys enabled where needed.
- [ ] Prevent open redirects: restore only validated saved requests/redirect URIs.
- [ ] Test multi-tab usage, account switching, session expiration, proxies, multi-instance deployments, and framework upgrades.
- [ ] Monitor re-authentication rates, `login_required`, `invalid_state`, CSRF errors, login failures, and redirect loops while minimizing personal data.
- [ ] Maintain retention/deletion processes for sensitive audit logs per organizational policy.

**Self-Check Questions**

1. Does an ID Token signed at the current timestamp prove the user just logged in again? Which claim should you check?
2. Under what conditions do `prompt=login` and `max_age=300` differ?
3. If an RP sends `max_age=0`, which claim must the returned ID Token contain?
4. Why must `prompt=none` never redirect the browser to the login page when the user has no session?
5. Why shouldn't you use a browser-supplied `returnUrl` field for post-login redirects?
6. If a user was logged in as A but re-authenticates as B, how must OP and RP protect account binding?
7. When token exchange occurs over a back-channel, can you read `auth_time` from that request's HTTP session?
8. Which headers help mitigate XSS, clickjacking, referrer leakage, and caching on the login page?

## References

- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): `prompt`, `max_age`, `auth_time`, `login_hint`, `acr_values`, and ID Token verification.
- [Spring Authorization Server — Getting Started](https://docs.spring.io/spring-authorization-server/reference/getting-started.html): configuring two filter chains and form login.
- [Spring Authorization Server — SPA with PKCE](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-pkce.html): browser redirect to login and returning to the authorization endpoint.
- [Spring Security — Form Login](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/form.html): form login mechanism and `loginPage` configuration.
- [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): protecting state-changing requests and CSRF tokens in forms.
- [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html): session fixation, session persistence, timeouts, and concurrency.
- [Spring Security — Security HTTP Response Headers](https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html): cache control, CSP, frame options, Referrer Policy, and HSTS.
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): re-authentication, generic errors, MFA, and brute-force defenses.
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): session cookies, renewal, and expiration.
- [Spring Security issue: OIDC `prompt=none` in 7.0](https://github.com/spring-projects/spring-security/issues/18647): example of a version-specific regression test case; check upstream issue status before applying workarounds.
