# 23.10. Secure, HttpOnly, and SameSite Cookies and Their Relationship to OAuth Callbacks

## 1. Context: OAuth2 Login Fails Even When Authorization Code and Redirect URI Look Right

Suppose **Employee Portal** uses **Spring Boot 3, Spring Security 6, and Spring MVC/Servlet** as an **OAuth2/OIDC Client**. Users visit:

~~~text
https://portal.example.test
~~~

and sign in via an OpenID Provider (OP):

~~~text
https://login.identity.example
~~~

The Portal uses the Authorization Code Flow. The browser redirects to the OP, the user authenticates, and then the browser navigates back:

~~~http
GET /login/oauth2/code/company?code=abc&state=xyz HTTP/1.1
Host: portal.example.test
~~~

Yet the application returns errors such as:

~~~text
authorization_request_not_found
invalid_state_parameter
OAuth2AuthenticationException
Login failed: authorization request not found
~~~

A frequent root cause is that **the browser did not send the Portal's session cookie on the callback request**. Spring Security then cannot look up the authorization request saved before redirecting to the OP.

The problem may not lie in `client-secret`, `redirect-uri`, or the token endpoint. The cookie may have been blocked by its attributes:

- `Secure`: cookie is sent only over an eligible secure connection.
- `HttpOnly`: JavaScript cannot read the cookie directly.
- `SameSite`: controls whether the browser sends the cookie in same-site/cross-site contexts.
- `Domain` and `Path`: restrict which hosts and paths receive the cookie.

**Lesson focus:** an OAuth2/OIDC callback is not just an HTTP endpoint. It is a **browser navigation** that must resume the prior authorization state. Cookie policies determine whether Spring Security still sees the session holding `state`, authorization request details, `nonce`, and PKCE metadata.

> Examples use Java 17+, Spring Boot 3, Spring Security 6, and Servlet. WebFlux/Spring Session differences are noted separately. Browsers and cookie policies evolve across releases and privacy modes; test in real browsers rather than calling callbacks only with `curl`.

## 2. Distinguishing Session Cookies, Tokens, and OAuth2 State

These three concepts are **not synonymous**:

| Concept | Typical Location | Role |
|---|---|---|
| **Session cookie** such as `JSESSIONID` or `SESSION` | Browser holds a **session identifier** | Browser sends the ID so Portal locates the server-side session |
| **HttpSession / server-side session** | Servlet container, Spring Session, or distributed session store | Stores login state and may store authorization requests |
| **`OAuth2AuthorizedClient`** | Authorized-client repository/service | Holds the OAuth client's access token and optional refresh token |

In a **backend-for-frontend (BFF)** architecture, the browser normally needs only the session cookie:

~~~text
Browser:
  Cookie: JSESSIONID=<opaque-session-id>

Portal backend:
  HttpSession:
    SecurityContext
    OAuth2 authorization request (while login is incomplete)

  OAuth2AuthorizedClientRepository/Service:
    access token
    refresh token (if issued)
~~~

The browser **does not need** to hold OAuth2 access tokens or refresh tokens in cookies for Spring Security to call Resource Servers. When the Portal is a server-side OAuth2 Client, keep tokens protected on the backend and let the browser carry only a session cookie.

### 2.1. What Does the Callback Need from the Session?

Before redirecting the browser to the Authorization Server, Spring Security typically creates an **`OAuth2AuthorizationRequest`** containing:

- `registrationId`, client ID, authorization URI, scopes.
- `redirect_uri` and random `state`.
- PKCE `code_verifier` / `code_challenge` if applicable.
- OIDC `nonce` when validating an ID Token.
- Additional attributes added by the authorization request resolver.

By default in Servlet, Spring Security typically saves the authorization request using:

~~~java
org.springframework.security.oauth2.client.web
    .HttpSessionOAuth2AuthorizationRequestRepository
~~~

If the browser returns **without carrying the right session cookie**, the callback cannot find the saved authorization request, even when `code` and `state` appear in the URL.

**Never "fix" this by skipping `state`, `nonce`, or PKCE checks.** Those are security defenses, not decorative fields.

## 3. Authorization Code Flow and When Cookies Are Used

~~~mermaid
sequenceDiagram
    actor Browser as Browser
    participant RP as Portal / Spring Security
    participant OP as OpenID Provider
    participant Session as Server-side Session Store

    Browser->>RP: GET /oauth2/authorization/company
    RP->>Session: Create/save authorization request with state, nonce, PKCE
    RP-->>Browser: 302 Location: OP /authorize + Set-Cookie: SESSION=...; Secure; HttpOnly; SameSite=Lax
    Browser->>OP: GET /authorize?...&state=...
    OP-->>Browser: Authenticate and 302 callback URL
    Browser->>RP: GET /login/oauth2/code/company?code=...&state=... + Cookie: SESSION=...
    RP->>Session: Load authorization request via session cookie
    Session-->>RP: state, nonce, PKCE metadata
    RP->>RP: Compare state, exchange code for tokens, validate OIDC
    RP-->>Browser: Login succeeded, may rotate session ID
~~~

Key steps:

1. **The Portal creates a session or uses an existing one** before redirecting.
2. The browser stores the cookie issued by the **Portal**, not the one issued by the OP.
3. The browser performs one or more navigations at the OP.
4. When the OP sends the browser back to the callback, the browser decides **whether to send the Portal's cookie**.
5. Spring Security uses that session to verify correlation.

A cookie from `login.identity.example` **does not replace** `portal.example.test`'s cookie. Each party maintains its own session and security policy.

### 3.1. OIDC Redirects Do More Than Return a Code

On callback, Spring Security must match the **authorization response** to the **original authorization request**. `state` prevents CSRF/login-swapping at the authorization layer; `nonce` binds the ID Token to the authentication request; PKCE binds the code exchange to the initiating client.

If the session is lost, merely having an authorization code does not prove the flow belongs to the current browser.

## 4. What Is a Cookie in HTTP?

An HTTP response can set a cookie:

~~~http
HTTP/1.1 302 Found
Location: https://login.identity.example/authorize?...
Set-Cookie: JSESSIONID=opaque-id; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

On a matching subsequent request, the browser may send:

~~~http
GET /login/oauth2/code/company?code=...&state=... HTTP/1.1
Host: portal.example.test
Cookie: JSESSIONID=opaque-id
~~~

**The `Cookie` request header never repeats attributes** like `Secure`, `HttpOnly`, or `SameSite`. Those attributes appear in `Set-Cookie` when the browser receives the cookie and are enforced by the browser when deciding whether to send it.

A session cookie typically has:

- **Name**: `JSESSIONID` or `SESSION`.
- **Value**: unpredictable session ID; never public user data.
- **Path**: request paths allowed to receive the cookie.
- **Domain**: host or host group allowed to receive it if configured.
- **Secure, HttpOnly, SameSite**: browser constraints.
- **Expires/Max-Age**: for persistent cookies; session cookies do not necessarily have a fixed browser expiration.

**A cookie can outlive or expire sooner than the server-side `HttpSession`.** Having a cookie in the browser does not mean the server session is still valid; conversely, an active server session cannot help if the browser lost the cookie.

## 5. Secure: Why Must Callbacks Use HTTPS?

A cookie with `Secure` is sent by browsers only over connections considered secure—typically **HTTPS**.

~~~http
Set-Cookie: JSESSIONID=abc; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

If the app sets a `Secure` cookie when the browser visits:

~~~text
https://portal.example.test
~~~

then under normal conditions the browser sends the cookie on a matching HTTPS callback:

~~~text
https://portal.example.test/login/oauth2/code/company
~~~

If the redirect URI was generated wrongly as:

~~~text
http://portal.example.test/login/oauth2/code/company
~~~

the `Secure` cookie **may not be sent**, and the flow also violates production OAuth/OIDC transport-security requirements.

### 5.1. `Secure` Does Not Mean Cookies Can Never Be Stolen

`Secure` reduces the risk of cookies traversing plaintext HTTP. It **does not**:

- Stop XSS scripts from issuing requests using the user's cookie.
- Prevent CSRF on its own.
- Stop cookies from leaking via logs, proxies, or a compromised browser.
- Guarantee server-side sessions are encrypted or properly authorized.

You still need HTTPS, HSTS, application security, correct proxy configs, and sound session management.

### 5.2. Localhost and Development Environments

Some browsers apply special handling or exceptions for **localhost** with `Secure` cookies. Never extrapolate localhost exceptions to public domains.

Production must run HTTPS end-to-end from the browser's perspective. For local testing, use local HTTPS or a dedicated dev profile with appropriate cookie config; **never disable `Secure` in production just because local HTTP testing failed**.

## 6. HttpOnly: JavaScript Cannot Read the Cookie, Yet the Browser Still Sends It

~~~http
Set-Cookie: JSESSIONID=abc; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

`HttpOnly` blocks JavaScript from reading the cookie via APIs like:

~~~javascript
document.cookie
~~~

So if frontend code runs:

~~~javascript
console.log(document.cookie);
~~~

and does not see `JSESSIONID`, that **is expected and secure behavior**.

**`HttpOnly` does not stop the browser from attaching the cookie** to matching URLs. When the user hits the callback, an `HttpOnly` cookie is sent normally provided `Secure`, `Domain`, `Path`, `SameSite`, and browser policies allow it.

### 6.1. `HttpOnly` Does Not Eliminate XSS Impact

Malicious JavaScript cannot read an `HttpOnly` cookie value directly, yet it can still issue requests under the active session and read frontend-accessible data if XSS executes in a same-origin context.

Therefore you still need:

- Output escaping/encoding and XSS defenses.
- A strong Content Security Policy.
- Keeping access/refresh tokens out of the DOM and unnecessary JavaScript.
- Server-side authorization on every action.
- Combining `HttpOnly` with `Secure` and `SameSite`, not using it as a standalone replacement.

### 6.2. CSRF Cookies Are Not Session Cookies

Some SPAs use an `XSRF-TOKEN` cookie that JavaScript reads and echoes back in an anti-CSRF header. That cookie may be configured **without `HttpOnly`** per the framework pattern.

This **does not mean dropping `HttpOnly` on the session cookie**. Distinguish clearly:

~~~text
SESSION / JSESSIONID: keep HttpOnly = true.
XSRF-TOKEN: JS-readable per CSRF strategy.
~~~

OAuth2 `state` is also not the `XSRF-TOKEN` cookie; they protect different flows.

## 7. SameSite: The Attribute Determining Whether Cookies Travel on OAuth Callbacks

`SameSite` has three key values:

| Value | General Meaning | Effect on Cross-Site IdP OAuth Callbacks |
|---|---|---|
| `Strict` | Cookie is sent only in same-site contexts | Cross-site callbacks usually **omit the session cookie** |
| `Lax` | Allows cookies in same-site and certain safe **top-level navigations** | Fits common **top-level GET callbacks** |
| `None` | Allows cookies in cross-site contexts if browser permits | May be needed for **`form_post` POST callbacks**, but **requires `Secure`** |

**`SameSite` is not CORS**, and **site is not synonymous with origin**.

### 7.1. What Is a "Site"?

In modern browsers, **schemeful same-site** evaluates both scheme and registrable domain (via the Public Suffix List). For example:

~~~text
https://portal.example.com
https://admin.example.com
~~~

usually share the same **site** (`https://example.com`) yet have **different origins** because their hostnames differ.

~~~text
https://portal.example.com
https://login.other-idp.test
~~~

are **cross-site**.

~~~text
http://portal.example.com
https://portal.example.com
~~~

are treated as **cross-site under schemeful same-site** despite identical hostnames.

When analyzing callback cookies, check **scheme, host, and how browsers define a site**—never just glance at two URLs sharing the word `example`.

### 7.2. Same Site Can Still Mean Different Origins

Two hosts:

~~~text
https://portal.example.com
https://api.example.com
~~~

are usually same-site, yet cross-origin JavaScript requests remain governed by **Same-Origin Policy / CORS**.

Conversely, a top-level GET OAuth callback from a cross-site IdP can carry `SameSite=Lax` cookies **without needing CORS**, because it is a browser navigation rather than `fetch()`.

## 8. `SameSite=Lax` with Top-Level GET Callbacks — The Common Case

Default Authorization Code Flow normally returns the browser to the RP via **GET** with `code` and `state` in the query string:

~~~text
IdP:
  https://login.identity.example
       |
       | 302 Location
       v
Portal:
  https://portal.example.test/login/oauth2/code/company
    ?code=...
    &state=...
~~~

The browser performs a **top-level GET navigation** from the IdP's site to the Portal's site. A `SameSite=Lax` cookie on the Portal **is normally sent** if all other constraints (`Secure`, `Domain`, `Path`, expiry, browser policy) are satisfied.

~~~http
Set-Cookie: JSESSIONID=abc; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

**`Lax` is usually the right choice for session cookies in a server-rendered/BFF web app using OAuth2 Authorization Code Flow with GET callbacks.** It shrinks CSRF exposure relative to `None` while supporting standard callback navigations.

### 8.1. `Lax` Allows Only Certain Safe Top-Level Navigations

Remember:

- **Top-level navigation**: the browser navigates the main page/tab to the Portal.
- **Safe HTTP method**: commonly GET.
- **Cross-site POST**: does not receive `SameSite=Lax` cookies by default.
- **Cross-site iframe/fetch**: does not receive the top-level GET exception.

Never infer from "the IdP redirects to the Portal" that **every callback mode works with `Lax`**. Check whether the callback uses GET or POST and whether it is top-level.

## 9. `SameSite=Strict`: Tighter Restrictions That Can Break OAuth Callbacks

~~~http
Set-Cookie: JSESSIONID=abc; Path=/; Secure; HttpOnly; SameSite=Strict
~~~

When the browser returns from a cross-site IdP:

~~~text
login.identity.example
      |
      | redirect GET
      v
portal.example.test/login/oauth2/code/company
~~~

a `Strict` cookie on the Portal **may not be sent**. The Portal creates a new session or finds no existing session, and Spring Security loses the saved authorization request holding `state`.

Result:

~~~text
User logs into IdP successfully.
IdP returns a valid authorization code.
Portal cannot find the old session's authorization request.
OAuth login fails.
~~~

**You cannot fix this by disabling `state` checks.** If sessions must survive cross-site redirects, `Strict` cookies may not fit the flow.

### 9.1. `Strict` May Work in Some Same-Site Deployments

If the IdP and Portal share a schemeful site, or navigation follows a same-site pattern, `Strict` cookies might be sent. However, **never assume the IdP will always be same-site**: organizations switch to external IdPs, brokers, or multi-provider federation.

Test each IdP and callback mode in real browsers. For browser login with cross-site IdPs, `Lax` is usually far more practical than `Strict`.

## 10. `SameSite=None`: When Is It Needed and What Are the Risks?

~~~http
Set-Cookie: JSESSIONID=abc; Path=/; Secure; HttpOnly; SameSite=None
~~~

`SameSite=None` requires **`Secure`** in modern browsers. A cookie with:

~~~http
Set-Cookie: JSESSIONID=abc; SameSite=None
~~~

that **lacks `Secure`** may be rejected immediately upon receipt.

`None` lets browsers send cookies in cross-site contexts where `Strict`/`Lax` block them—**if** the browser permits that cookie. This helps when:

- The IdP delivers callbacks via **cross-site POST** (OIDC `response_mode=form_post`).
- The app genuinely operates inside an iframe/cross-site embedded context under an approved architecture.
- A valid integration requires third-party cookie delivery.

Trade-offs:

- Cookies travel in broader cross-site contexts, increasing CSRF risk if app protections are missing.
- Browsers may still block third-party cookies via privacy settings, tracking prevention, or enterprise policies.
- `SameSite=None` **does not guarantee** every browser or iframe permits the cookie.

**`None` is not a "fix all OAuth callback errors" switch.** Choose it only for a specific callback mode and architecture, paired with CSRF/`state`/`nonce`/PKCE, TLS, and browser testing.

### 10.1. `None` and Third-Party Cookie Blocking Are Different Rules

A `SameSite=None; Secure` cookie satisfies `SameSite` rules, yet can still be blocked inside an iframe by browser third-party cookie policies.

Conversely, a **top-level redirect** back to the Portal differs from loading the Portal inside a third-party iframe. Distinguish top-level browser navigation from embedded login.

## 11. SameSite Decision Table by Callback Mode

| Scenario | Browser Request to Portal | Lax | Strict | None + Secure |
|---|---|---|---|---|
| Cross-site IdP redirect to Portal | **Top-level GET** | **Normally sends cookie** | **Normally withheld** | May send |
| OIDC `response_mode=form_post` | **Top-level POST** | **Normally withheld** | Withheld if cross-site | May send |
| Portal inside cross-site iframe | Iframe request/navigation | Normally withheld | Normally withheld | May send, subject to third-party policy |
| Portal calling itself on same site | Same-site request | Sends if other attrs match | Sends if other attrs match | Sends if other attrs match |
| `fetch()` to cross-site API | XHR/fetch | Withheld cross-site by SameSite | Withheld | May send if fetch credentials/CORS/browser allow |
| IdP and Portal share schemeful site | Same-site callback | Normally sends | May send | May send |

**Decision rule:** inspect the **actual URL**, **HTTP method**, **top-level vs. iframe**, **schemeful site**, and **browser policy**.

### 11.1. Can You Rely on the "Two-Minute Lax+POST" Exception?

Some browsers apply/applied a compatibility exception for newly created cookies **without an explicit `SameSite` attribute**, temporarily permitting certain cross-site POSTs (often called **Lax-allowing-unsafe** or the "Lax+POST grace period").

**Never rely on that exception to design OAuth `form_post` callbacks.** It applies only to cookies omitting `SameSite`, differs from explicit `SameSite=Lax`, and varies across browsers, versions, and timing.

If cross-site POST callbacks are required, configure cookies and response modes explicitly for POST and test on target browsers.

## 12. OIDC `response_mode=form_post`: A Classic Cause of Lost Sessions

Some OPs support:

~~~text
response_mode=form_post
~~~

Instead of a GET redirect carrying `code`/`state`, the OP returns an HTML page with an auto-submitting form:

~~~html
<form method="post"
      action="https://portal.example.test/login/oauth2/code/company">
  <input type="hidden" name="code" value="EXAMPLE_CODE">
  <input type="hidden" name="state" value="EXAMPLE_STATE">
  <button type="submit">Continue</button>
</form>
~~~

This is a **cross-site POST navigation** from the OP to the Portal. Browsers will typically **not send** a `SameSite=Lax` Portal cookie:

~~~text
1. Portal saves state in HttpSession S1.
2. Portal sets JSESSIONID=S1; SameSite=Lax.
3. Browser visits OP.
4. OP returns form_post POST callback.
5. Browser withholds cookie S1 due to cross-site POST.
6. Spring Security callback cannot find HttpSession S1.
7. authorization_request_not_found / state mismatch.
~~~

With `form_post`, you may need a `SameSite=None; Secure` cookie for the correlation state. Yet that is only **half the story**.

### 12.1. Spring Security's CSRF Filter Also Applies

Servlet Spring Security enforces **CSRF protection** on state-changing HTTP methods, including POST. An OIDC `form_post` callback is a POST initiated by the OP, which naturally **lacks the application's CSRF token in the form**.

Therefore check **two independent barriers**:

1. Does the browser send the session cookie on a cross-site POST?
2. Does the CSRF filter allow the callback POST to reach `OAuth2LoginAuthenticationFilter`?

If the CSRF filter blocks the POST, changing `SameSite` to `None` **is not enough**. Conversely, exempting the callback from CSRF while leaving cookies `Lax` **is also not enough**.

### 12.2. Narrow CSRF Exemption for the Callback POST Only

In an app intentionally choosing `response_mode=form_post`, a Spring Security 6 Servlet example:

~~~java
package com.example.portal.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.util.matcher.AntPathRequestMatcher;

@Configuration
public class OidcFormPostSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .csrf(csrf -> csrf
                .ignoringRequestMatchers(
                    new AntPathRequestMatcher(
                        "/login/oauth2/code/*",
                        "POST"
                    )
                ))
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults())
            .build();
    }
}
~~~

This is a **conditional pattern for `form_post`**, not a recommendation if you only use GET callbacks. Paths must match your real callbacks and matchers appropriate for your Spring Security version.

**Never disable CSRF app-wide** via `csrf.disable()` just to make a callback work. Exempting the callback from CSRF tokens is safe only when **`state`, `nonce`, authorization request correlation, PKCE, and OIDC validation** remain fully enforced.

### 12.3. Aligning `response_mode` Config with the IdP

An authorization request resolver can attach the parameter:

~~~java
import org.springframework.security.oauth2.client.registration
    .ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web
    .DefaultOAuth2AuthorizationRequestResolver;

DefaultOAuth2AuthorizationRequestResolver resolver =
    new DefaultOAuth2AuthorizationRequestResolver(
        registrations,
        "/oauth2/authorization"
    );

resolver.setAuthorizationRequestCustomizer(builder ->
    builder.additionalParameters(params ->
        params.put("response_mode", "form_post")
    )
);
~~~

`registrations` is the existing `ClientRegistrationRepository` bean. Wire this resolver into `oauth2Login().authorizationEndpoint()`:

~~~java
http.oauth2Login(login -> login
    .authorizationEndpoint(endpoint -> endpoint
        .authorizationRequestResolver(resolver)
    )
);
~~~

Do not add `response_mode=form_post` without verifying POST callback handling, the CSRF matcher, `None; Secure` cookies, and actual OP support. Unless `form_post` is specifically required, **GET callbacks with `Lax`** are usually simpler for Servlet/BFF apps.

## 13. Cookie Domain: Host-Only vs. Domain Cookies

A cookie set by:

~~~text
https://portal.example.com
~~~

without a `Domain` attribute:

~~~http
Set-Cookie: SESSION=abc; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

is a **host-only cookie**: the browser restricts it to `portal.example.com`. This is normally the best choice for login sessions.

Setting:

~~~http
Set-Cookie: SESSION=abc; Domain=example.com; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

allows the cookie to be sent to multiple subdomains under `example.com` per domain-matching rules.

### 13.1. Why Should You Not Widen `Domain` to "Fix OAuth Callbacks"?

If the Portal and IdP have **different registrable domains**, setting `Domain=example.com` **does not** send the Portal's cookie to a cross-site IdP—nor should it. The callback returns to the Portal; the browser only needs to send the cookie when reaching the Portal's own host.

Unnecessarily widening `Domain` increases exposure from other subdomains, including subdomain takeover or less-trusted apps. Keep session cookies **host-only** unless cross-subdomain session sharing is intentionally designed and strictly secured.

### 13.2. `app.example.com` Cookies Do Not Travel to `portal.example.com`

If the browser initiates login at:

~~~text
https://app.example.com/oauth2/authorization/company
~~~

while the IdP calls back to:

~~~text
https://portal.example.com/login/oauth2/code/company
~~~

a host-only cookie set for `app.example.com` is not sent to `portal.example.com`, even though both share the same site.

**This is a hostname/redirect URI mismatch**, not a `SameSite` issue. Keep one canonical public host for login start and callback, or intentionally design cross-host state correlation.

## 14. Cookie Path and Callback Endpoints

A cookie:

~~~http
Set-Cookie: SESSION=abc; Path=/portal; Secure; HttpOnly; SameSite=Lax
~~~

is sent only to request paths matching `/portal` per cookie path-matching rules.

If the callback actually lives at:

~~~text
/login/oauth2/code/company
~~~

a cookie with `Path=/portal` **will not be sent**.

Similarly, if the app deploys under a context path:

~~~text
/employee
~~~

login initiation, callbacks, and cookie paths must align consistently.

### 14.1. `Path` Is Not an Access Control Boundary

Cookie `Path` only controls which URLs the browser attaches the cookie to. It **does not** stop same-origin apps or same-origin XSS from accessing other endpoints via the browser.

Never rely on `Path` in place of server-side authentication and authorization.

### 14.2. The `__Host-` Cookie Prefix

A cookie named with the `__Host-` prefix must satisfy modern constraints:

- Has `Secure`.
- `Path=/`.
- **No `Domain` attribute**.
- Set from a secure context.

Example:

~~~http
Set-Cookie: __Host-SESSION=opaque; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

This prefix lets browsers enforce stricter cookie scoping. If your app requires `Path=/portal` or a `Domain` cookie, it **cannot** validly use `__Host-SESSION`.

The `__Secure-` prefix only requires `Secure` with different scoping rules; it does not substitute for `__Host-` guarantees.

## 15. Reasons Cookies Are Not Sent on Callbacks

| Symptom | Why Browser Withholds Cookie? | How to Confirm |
|---|---|---|
| `SameSite=Strict` | Callback comes from cross-site IdP | Check Initiator/Site, Cookie blocked reason |
| `SameSite=Lax` + `form_post` | Cross-site POST lacks `Lax` GET exception | Check Request Method: POST and `Set-Cookie` |
| `SameSite=None` missing `Secure` | Browser may reject storing cookie | Check `Set-Cookie` issues/blocked reasons |
| `Secure` + HTTP callback | Not sent over insecure HTTP | Check Request URL scheme |
| Different host | Host-only cookie misses callback host | Compare login-start and callback hosts |
| Different path | Cookie `Path` misses callback path | Compare `Path` with Request URL |
| Cookie expired/cleared | Browser no longer holds session ID | Check cookie storage/`Expires`/`Max-Age` |
| Wrong/broad `Domain` | Cookie rejected or mismatched | Check `Domain` and response host |
| Third-party/iframe restrictions | Blocked by browser privacy policy | Check iframe context and browser issues |
| Cookie too large/too many | Browser/proxy/container rejects or evicts | Check cookie size/count/header limits |
| Different Session ID | Server rotated session, host changed, or out-of-sync store | Compare server-side session lifecycle safely |

**Never change every attribute at once** when debugging. First pinpoint why the browser failed to store or send the cookie.

## 16. Configuring Spring Boot Servlet Session Cookies

In Spring Boot 3 with an embedded Servlet container:

~~~yaml
# application-prod.yml
server:
  servlet:
    session:
      timeout: 30m
      cookie:
        name: __Host-SESSION
        path: /
        secure: true
        http-only: true
        same-site: lax
~~~

**Meaning:**

- `name`: session cookie name; here `__Host-SESSION` follows prefix rules.
- `path: /`: callbacks and endpoints on the same host receive the cookie.
- `secure: true`: cookie travels only over secure connections.
- `http-only: true`: JS cannot read the session ID directly.
- `same-site: lax`: fits standard top-level GET callbacks.
- `timeout: 30m`: server-side inactivity timeout; **not the OAuth access token TTL**.

**Do not set `domain` when using the `__Host-` prefix.** Ensure the app actually runs on a public HTTPS URL.

### 16.1. Without a Cookie Prefix

Simple configuration:

~~~yaml
server:
  servlet:
    session:
      cookie:
        name: JSESSIONID
        secure: true
        http-only: true
        same-site: lax
        path: /
~~~

Choosing `JSESSIONID`, `SESSION`, or a custom name does not alter `SameSite` semantics. What matters is **which cookie actually carries the session used by Spring Security**.

### 16.2. Deploying Under a Context Path

If the app runs under `/employee`, the default session cookie `Path` may follow the context path or container settings. Inspect the real `Set-Cookie` header rather than relying solely on YAML.

If using `__Host-SESSION`, you must use `Path=/`. If policy demands a narrower path, **drop the `__Host-` prefix** and ensure cookie path matches callbacks.

### 16.3. Do Not Confuse App Properties with the Final Emitted Cookie

Depending on Servlet container, Spring Session, reverse proxies, or gateways, the final cookie may be emitted or modified by **another layer**.

Always inspect:

~~~http
Set-Cookie: ...
~~~

on the HTTP response **reaching the browser**. Even with valid YAML, if a filter or proxy rewrites `SameSite`/`Domain`/`Path`, the browser obeys the header it actually receives.

## 17. Spring Session Redis/JDBC May Use Different Cookies Than the Servlet Container

When using **Spring Session**, session IDs are typically emitted via Spring Session's cookie serializer rather than embedded Tomcat's cookie settings alone.

`DefaultCookieSerializer` example:

~~~java
package com.example.portal.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.session.web.http.CookieSerializer;
import org.springframework.session.web.http.DefaultCookieSerializer;

@Configuration
public class SpringSessionCookieConfig {

    @Bean
    CookieSerializer cookieSerializer() {
        DefaultCookieSerializer serializer =
            new DefaultCookieSerializer();

        serializer.setCookieName("__Host-SESSION");
        serializer.setCookiePath("/");
        serializer.setUseSecureCookie(true);
        serializer.setUseHttpOnlyCookie(true);
        serializer.setSameSite("Lax");

        // Never call setDomainName(...) with the __Host- prefix.
        return serializer;
    }
}
~~~

Spring Session dependencies and the backing store must also be configured properly; this snippet focuses purely on **cookie serialization**.

### 17.1. Avoid Accidentally Emitting Two Session Cookies

A deployment might emit both:

~~~text
JSESSIONID=...  (Servlet container)
SESSION=...     (Spring Session)
~~~

If the login filter uses Spring Session while debugging looks at the container's cookie, conclusions will be wrong.

Identify which cookie actually carries the session ID holding `SPRING_SECURITY_CONTEXT` and the authorization request. Never configure two different cookies to drive the same session without a clear architectural reason.

### 17.2. Data in Redis Does Not Guarantee Callbacks Succeed

The Redis session may still exist while the browser fails to send the cookie → the app **cannot know which session to load**.

Conversely, the browser may send the cookie properly while Redis lost the session or its TTL expired → the app still cannot find the authorization request. Check **both the browser cookie and the server-side store**.

## 18. External HTTPS, Internal HTTP: Reverse Proxies and Load Balancers

A common topology:

~~~text
Browser
  |
  | HTTPS https://portal.example.test
  v
Load Balancer / Ingress
  |
  | HTTP http://portal-service:8080
  v
Spring Boot Servlet
~~~

Without proxy header handling, the app sees only internal HTTP connections. This causes:

- Redirect URIs generated as `http://...` even though the public URL uses HTTPS.
- Internal hostnames/ports appearing in callbacks.
- `request.isSecure()` returning `false` contrary to what the browser sees.
- `Secure` cookies omitted if the server infers security from the internal scheme.

### 18.1. Controlled Forwarded-Headers Configuration

Spring Boot example:

~~~yaml
server:
  forward-headers-strategy: framework
  servlet:
    session:
      cookie:
        secure: true
        http-only: true
        same-site: lax
~~~

With `framework`, Spring processes `Forwarded` or `X-Forwarded-*` headers so the app recognizes the external scheme and host. Some setups use `native` with container/ingress support.

**Mandatory security constraint:** trust forwarded headers only from **trusted reverse proxies**, and ensure the proxy **strips or overwrites client-supplied headers from the Internet**. Trusting spoofed headers lets attackers manipulate redirect URLs, host validation, and URL policies.

### 18.2. Redirect URIs Constructed by Spring Security

Example:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
        provider:
          company:
            issuer-uri: ${OIDC_ISSUER_URI}
~~~

`{baseUrl}` depends on the recognized request/proxy info. If `baseUrl` resolves to `http://portal-service:8080` while the OP only registered:

~~~text
https://portal.example.test/login/oauth2/code/company
~~~

you hit `redirect_uri_mismatch` or the browser calls back to a host lacking the session cookie.

**Note:** a redirect URI error is not necessarily a `SameSite` cookie bug; both often appear together from misconfigured proxies.

### 18.3. Do Not Fix It Merely by Hard-Coding the Redirect URI

Hard-coding a public redirect URI may unblock one environment quickly, yet does not fix:

- Missing `Secure` on cookies.
- Mismatched cookie `Path`/`Domain`.
- Trusting untrusted `X-Forwarded-Host` headers.
- Load balancers routing callbacks to nodes missing the session.

Fix root causes in proxy, public URL, and session architecture. Hard-coding can still be useful when deployments have a clear canonical URI, provided IdP registration and environment configs stay aligned.

## 19. `HttpSessionOAuth2AuthorizationRequestRepository` and State Correlation

In the Servlet stack, Spring Security provides:

~~~java
HttpSessionOAuth2AuthorizationRequestRepository
~~~

Conceptually:

~~~text
Browser starts authorization:
  GET /oauth2/authorization/company

Server:
  generate OAuth2AuthorizationRequest:
    authorizationUri, clientId, redirectUri, scopes
    state = RANDOM_STATE
    nonce/PKCE attributes when applicable
  store request in HttpSession

Browser callback:
  GET /login/oauth2/code/company?code=...&state=RANDOM_STATE

Server:
  find HttpSession via session cookie
  load matching request
  compare state
  continue code exchange
~~~

Losing the session causes the repository to miss the authorization request.

### 19.1. `state` Is Not the Session ID

`state` is a correlation/CSRF token for the OAuth authorization response. `JSESSIONID` identifies the session at the Portal.

~~~text
state      = random-OAuth-correlation-value
JSESSIONID = random-web-session-identifier
~~~

Both appear in one flow with distinct purposes. Never set `state = JSESSIONID` and never pass session IDs in query parameters to "work around blocked cookies".

### 19.2. Does Having `state` in the URL Mean the Callback Is Valid?

No. An attacker can send any arbitrary `state`. Spring Security must verify that `state` **matches the original authorization request stored for that session/flow**.

If the authorization request is missing, never synthesize a fake request to accept the `code` from the URL.

### 19.3. OIDC `nonce` and PKCE Still Need Protection

Upon login completion:

- PKCE `code_verifier` must match the initial request's `code_challenge`.
- OIDC `nonce` in the ID Token must match the flow's issued nonce.
- The ID Token must pass issuer, audience, signature, expiry, and OIDC checks.

Cookie policies ensure **the context is recovered**, without replacing any of those validations.

## 20. Session Fixation Protection and Post-Login Session ID Rotation

An easily misunderstood behavior:

~~~text
Before login:
  JSESSIONID = S1

Callback succeeds:
  Session fixation protection may rotate the session ID.

After login:
  JSESSIONID = S2
~~~

Spring Security enables **session fixation protection** by default in standard setups, preventing attackers from pre-fixing a user's session ID and hijacking it after login.

**Session ID rotation after authentication is not a bug.** What matters:

1. Before callback processing, the browser must send **S1** to locate the authorization request.
2. After successful login, the app may issue **S2**.
3. The browser must store the new cookie and send S2 on subsequent requests.

### 20.1. Never Freeze the Session ID to Fix Callbacks

If the callback lacked S1 due to `SameSite=Strict` or POST with `Lax`, disabling session fixation protection **fixes nothing**. It only weakens another security layer.

### 20.2. Multiple Tabs and Concurrent Authorization Requests

If a user opens two login flows concurrently:

~~~text
Tab A -> authorization request state=A
Tab B -> authorization request state=B
Tab A -> callback state=A
~~~

depending on repository/session design, the second request may overwrite or collide with the first. On state mismatches:

- Verify whether the cookie was sent.
- Check for multiple tabs, popups, or parallel login attempts.
- Check cross-node session persistence.
- Check whether custom authorization request repositories support concurrent flows.

**Never assume every state mismatch is caused by `SameSite`.**

## 21. `SessionCreationPolicy.STATELESS` and OAuth2 Login

A common misconfiguration:

~~~java
http.sessionManagement(session ->
    session.sessionCreationPolicy(SessionCreationPolicy.STATELESS));
~~~

combined with default `oauth2Login()` using `HttpSessionOAuth2AuthorizationRequestRepository`.

`STATELESS` conflicts with a login flow relying on `HttpSession` for authorization requests and `SecurityContext`. Without designing a stateless correlation repository, callbacks lose state.

### 21.1. Separate Security Chains When One App Serves Both BFF and APIs

An app may expose:

- **Browser/login endpoints**: session-based, OAuth2/OIDC login.
- **Machine API endpoints**: stateless bearer-token resource server.

Never apply a single `STATELESS` policy globally if browser logins still rely on sessions. Split `SecurityFilterChain` beans by request matchers with tailored policies.

This is a session-storage architecture issue—**not solvable by changing `SameSite`**.

## 22. Cookie-Based `AuthorizationRequestRepository`: Should It Replace `HttpSession`?

Spring Security allows replacing:

~~~java
org.springframework.security.oauth2.client.web
    .AuthorizationRequestRepository<OAuth2AuthorizationRequest>
~~~

For instance, storing authorization request correlation in a dedicated cookie instead of `HttpSession`. Doing so demands careful design:

- Cookies have tight size limits (typically a few KiB), unsuitable for arbitrarily large serialized requests.
- Data from browsers can be tampered with; enforce integrity, binding, and replay protection.
- Never put code verifiers, nonces, credentials, or sensitive details in JS-readable cookies.
- If a cookie holds state, sign/encrypt it properly and validate TTL, audience, client registration, and redirect URI.
- Support multiple concurrent login flows without overwriting each other.
- Callback cookies are still subject to **`Secure`/`HttpOnly`/`SameSite`/`Domain`/`Path`**.
- Plan key rotation and cookie cleanup after login or failure.

### 22.1. Switching Repositories Does Not Bypass `SameSite`

If you move from `HttpSession` to a cookie-based repository while still setting:

~~~http
Set-Cookie: OAUTH2_REQUEST=...; Secure; HttpOnly; SameSite=Strict
~~~

on cross-site IdP callbacks, that custom cookie **still will not be sent**.

Changing repositories only changes where correlation lives; **browser cookie policies still apply identically**.

### 22.2. Never Treat Client-Side Cookies as a New Trust Anchor

If a browser sends a cookie claiming "I am logged in as sub=admin", the server must never trust that claim to bypass ID Token validation or authorization.

OAuth2/OIDC callbacks must always enforce state, nonce/PKCE, and token validation; cookies are merely a protected transport for correlation state.

## 23. `Lax` GET Callbacks vs. Logout and Front-Channel Iframes

Not all OIDC flows use the same request shape:

| Flow | Typical Shape | Cookie Behavior |
|---|---|---|
| OIDC authorization-code callback | Top-level GET | `Lax` normally works |
| OIDC `form_post` callback | Top-level POST | `Lax` normally withheld |
| RP-Initiated Logout | Top-level browser redirect | Cookies may reach RP depending on endpoint/flow |
| Front-channel logout via iframe | Cross-site iframe | `Lax`/`Strict` block cookies; `None` still hits third-party limits |
| Back-channel logout | Server-to-server HTTP | Does not depend on browser cookies like callbacks |
| Silent login/refresh in iframe | Embedded cross-site context | Browser third-party cookie restrictions often break it |

**A cookie configuration tuned for top-level GET callbacks does not guarantee iframe-based front-channel logout works.**

### 23.1. Do Not Equate `SameSite=None` with "Silent Login Works"

Browsers restrict third-party cookies and cross-site tracking, blocking iframe cookies even with valid `Set-Cookie` headers. Check OP guidance and browser policies for embedded auth. Usually prefer top-level redirects with authorization code + PKCE over silent iframes under modern privacy rules.

### 23.2. Portal Logout vs. Token Revocation at the OP

Clearing local cookies/sessions:

~~~text
Browser no longer holds a Portal session.
~~~

does not mean:

~~~text
Access tokens, refresh tokens, and the OP SSO session were all revoked.
~~~

Implement local logout, OIDC OP logout, authorized-client cleanup, and token revocation per requirements; **`SameSite` cookies do not perform these actions**.

## 24. CSRF: `SameSite` Helps, Yet Does Not Replace CSRF Defenses

CSRF occurs when an attacker tricks a user's browser into sending authenticated cookie-bearing requests to a trusted app. `SameSite=Lax` reduces some cross-site cookie requests, especially non-top-level or unsafe ones.

However, it is **not complete protection** because:

- Browsers vary in compatibility and policy.
- Attacker-controlled same-site subdomains can trigger requests considered same-site.
- Non-standard **side-effecting GET endpoints** may exist.
- `SameSite=None` cookies allow broader cross-site delivery.
- Login callbacks require dedicated correlation via `state`.

Therefore:

1. Keep CSRF protection on session-backed forms/actions.
2. Use `state` for OAuth2 authorization responses.
3. Use `nonce` for OIDC correlation and PKCE where applicable.
4. Exempt CSRF tokens only on the **exact POST callback endpoint** if `form_post` genuinely requires it.
5. Never disable CSRF app-wide just to make callbacks pass.

### 24.1. `HttpOnly` Is Not a CSRF Defense

Even when attackers cannot read `JSESSIONID` via JavaScript, browsers still attach cookies automatically to eligible requests. `HttpOnly` stops direct JS exfiltration, not CSRF requests.

### 24.2. `SameSite` Does Not Replace Authentication

Internal endpoints must still enforce Authentication and Authorization. Receiving a cookie does not prove a user may modify every resource. Multi-tenant apps must verify tenant/resource ownership server-side.

## 25. Callbacks via `fetch`/AJAX: Why Is This Usually the Wrong Model?

OAuth2 Authorization Code Flow in Spring Security Servlet is designed around **browser navigation**:

~~~text
Browser -> Portal starts authorization
Browser -> IdP login
Browser -> Portal callback
~~~

If frontend code tries:

~~~javascript
fetch("https://portal.example.test/login/oauth2/code/company?code=...")
~~~

the request hits CORS/cookie credential constraints, lacks top-level navigation semantics, and may not belong to the session holding `state`.

**The callback URL is not an arbitrary API for frontends to submit codes manually.** Let the browser follow the authorization redirects issued by Spring Security and the IdP.

### 25.1. Cross-Origin Fetch and Credentials

If the frontend runs on:

~~~text
https://frontend.example.com
~~~

and the BFF runs on:

~~~text
https://portal.example.com
~~~

they are **cross-origin yet same-site**.

To send cookies via `fetch`, the frontend may need:

~~~javascript
fetch("https://portal.example.com/api/me", {
  credentials: "include"
});
~~~

and the server needs matching CORS policies allowing the specific origin and credentials. Still, **`credentials: "include"` never overrides `SameSite`, `Secure`, or third-party cookie blocking**.

**CORS governs cross-origin JavaScript fetches**, not top-level OAuth browser redirects. Never add wildcard CORS trying to "fix" GET callbacks.

## 26. SameSite and Subdomains: Three Practical Examples

### 26.1. External-Domain IdP, GET Callback

~~~text
Portal: https://portal.example.com
IdP:    https://login.company-idp.net
Callback method: GET
Cookie: Secure; HttpOnly; SameSite=Lax; Path=/
~~~

Works cleanly with top-level redirects. You do not need `Domain=example.com` or `SameSite=None` just because the IdP is on another site.

### 26.2. External IdP, POST Callback

~~~text
Portal: https://portal.example.com
IdP:    https://login.company-idp.net
Callback method: POST (form_post)
Cookie: Secure; HttpOnly; SameSite=Lax
~~~

Cross-site POST typically causes `Lax` cookies to be **withheld**. Evaluate `SameSite=None; Secure`, a narrow CSRF callback matcher, and OP/RP support for `response_mode=form_post`.

### 26.3. IdP Sharing Registrable Domain, Different Host

~~~text
Portal: https://portal.example.com
IdP:    https://login.example.com
Callback method: GET or POST
~~~

These are usually **same-site** because scheme and registrable domain match. `SameSite=Strict` cookies may be sent in same-site navigations, yet **the Portal's host-only cookie still will not be sent to `login.example.com`**—nor does the IdP need it.

Never "share cookies between Portal and OP" merely because they share a parent site; each must isolate sessions along its security boundary.

## 27. Cookie Security Behind Reverse Proxies / CDNs

Beyond application config, check the proxy layer:

- Does it terminate TLS with valid certificates?
- Is HSTS enabled on the public HTTPS host per policy?
- Does it rewrite `Set-Cookie`?
- Does it sanitize/normalize `X-Forwarded-Proto`, `Host`, and `X-Forwarded-Host`?
- Does it downgrade `Location` redirects from HTTPS to HTTP?
- Does it accidentally cache login responses containing `Set-Cookie`?
- Does it log session cookies or `code`/`state` query strings?
- Does it forward cookies to out-of-scope CDN/static hostnames?

**Never publicly cache personalized responses carrying `Set-Cookie` or authorization artifacts.** If proxies log full callback URLs, authorization codes appear in access logs; enforce masking and retention controls.

### 27.1. The `Set-Cookie` Reaching the Browser Is Truth

Application logs may report:

~~~text
session created successfully
~~~

yet if a proxy strips `SameSite=None`, drops `Secure`, or alters `Path`, the browser follows the altered header.

Inspect the **actual** HTTP response in the browser Network tab and on intermediate proxies with proper access controls.

## 28. Multi-Instance: Right Cookie, Wrong Session Store

Suppose the Portal runs two replicas:

~~~mermaid
flowchart TD
    B["Browser holds SESSION=S1"] --> LB["Load Balancer"]
    LB --> A["Portal Node A: creates authorization request in S1"]
    LB --> C["Portal Node B: handles OAuth callback"]
    A --> LocalA["Local HttpSession Store A"]
    C --> LocalB["Local HttpSession Store B"]
~~~

Even when the browser sends the right cookie, if Node B cannot find S1 in its local store, the callback still fails with `authorization_request_not_found`.

Solutions:

- **Shared session storage**, such as Spring Session with Redis/JDBC per architecture.
- Sticky sessions if deliberate, while accounting for failover/scaling limits.
- Verify session timeouts and cookie-to-session mapping.

**`SameSite=Lax` cannot fix sessions that are not shared across nodes.**

### 28.1. Session Stickiness Is Not Authorization Security

Even when sticky routing works, the server must still validate `state`, `nonce`, PKCE, client registration, and the ID Token. Sticky sessions only route the callback to the right state store.

### 28.2. Races with Session Fixation and Parallel Callbacks

When one login request succeeds and rotates the session ID, a parallel request holding the old cookie may see a different state. Test multi-tab/concurrent flows and storage consistency rather than blaming only blocked cookies.

## 29. Investigating with Browser DevTools

A practical isolation workflow:

**Step 1 — Open a clean incognito window or dedicated test profile.** Avoid stale session cookies, extensions, and extra tabs skewing results.

**Step 2 — Access the Portal via its public HTTPS URL.** Never start login on an internal host or plain HTTP and expect callbacks to another host.

**Step 3 — Open DevTools Network and enable Preserve log.** Trace requests:

~~~text
GET /oauth2/authorization/company
302 Location: https://login.identity.example/authorize...
GET /login/oauth2/code/company?code=...&state=...
~~~

**Step 4 — Inspect the Portal's initial response:**

~~~http
Set-Cookie: JSESSIONID=...; Secure; HttpOnly; SameSite=Lax; Path=/
~~~

Verify the cookie was actually stored; check `Application/Storage → Cookies` and browser **Issues / blocked reasons**.

**Step 5 — Inspect the callback request to the Portal:** under Network → Request Headers → `Cookie`. Did the browser send the exact session cookie (from before Spring Security rotates the session ID)?

**Step 6 — Check the HTTP method:** is the callback **GET** or **POST**? If POST, is it `form_post` and are `SameSite`/CSRF configured properly?

**Step 7 — Check scheme/host/path:** did `https://portal.example.test` stay consistent from initiation through callback?

**Step 8 — If the cookie was sent:** inspect the server session store, state correlation, concurrent login attempts, and filter chain matchers.

### 29.1. Never Paste Real Cookies or Codes into Tickets or Logs

When sharing HAR files, network traces, or screenshots, **redact**:

- `Cookie: JSESSIONID=...` or `SESSION=...`.
- Authorization codes in query strings/bodies.
- OAuth2 `state` and OIDC `nonce` when unnecessary.
- `Authorization: Basic/Bearer`.
- ID Tokens, access tokens, refresh tokens.
- Client secrets and PII.

Those values may still be live or allow session hijacking. Sharing **cookie presence, attributes, timestamps, and status codes** is usually plenty to diagnose issues.

## 30. Distinguishing Blocked Cookies from Missing Cookies

Two cases:

~~~text
A. Cookie not stored:
   Set-Cookie was returned, yet the browser rejected it.

B. Cookie stored, yet not sent:
   Browser holds the cookie, yet the callback request omits Cookie.
~~~

Different root causes:

| Case | Example Causes |
|---|---|
| Not stored | `SameSite=None` lacking `Secure`, invalid `Domain`, browser policy, cookie limits |
| Not sent | `SameSite=Strict`, `Lax` + POST, `Secure` + HTTP, `Path`/`Domain` mismatch, expired, iframe limits |
| Sent properly, yet server lacks session | Session timeout, Redis outage, hit another node with local store |
| Cookie sent, yet callback still fails | State mismatch, parallel logins, wrong request repository, client registration/callback filter mismatch |

**Never look only at the Storage tab and assume the browser sent the cookie on the callback.** Inspect the Request Headers of the callback itself.

## 31. Using `curl` to Inspect HTTP Headers — Not a Browser Replacement

You can check whether the server returns the expected `Set-Cookie` and `Location`:

~~~bash
curl --silent --show-error --include \
  https://portal.example.test/oauth2/authorization/company
~~~

Illustrative response:

~~~http
HTTP/1.1 302 Found
Set-Cookie: JSESSIONID=...; Path=/; Secure; HttpOnly; SameSite=Lax
Location: https://login.identity.example/authorize?client_id=...&...
~~~

**Never use `curl -k` to bypass TLS verification in production checks.** Never publish raw responses containing authorization codes, cookies, or session IDs.

### 31.1. `curl` Does Not Enforce SameSite Like a Browser

`curl` cookie jars and HTTP client libraries do not fully emulate browser rules for:

- Site/top-level navigation.
- `Strict`/`Lax` cross-site restrictions.
- Third-party iframe blocking.
- Browser privacy policies.

Therefore, "curl sent the cookie" **does not prove a browser callback will**. Test `SameSite` using real browsers or browser automation navigating across sites.

## 32. Testing with `MockMvc`: What It Can and Cannot Prove

With Spring Security Test, you can verify authorization/login endpoints and server policies. However, **`MockMvc` is not a browser**, so it does not enforce `SameSite` like Chrome, Firefox, or Safari.

Conceptual example:

~~~java
@Test
void authorizationEndpointRedirectsToProvider() throws Exception {
    mvc.perform(get("/oauth2/authorization/company"))
        .andExpect(status().is3xxRedirection())
        .andExpect(header().string(
            "Location",
            org.hamcrest.Matchers.containsString("state=")
        ));
}
~~~

Here `mvc` is `MockMvc` configured with Spring Security and appropriate test registrations.

### 32.1. `MockMvc` Is Not a Full `Set-Cookie` Test

How a Servlet container emits session cookies—or how a reverse proxy alters headers—is not fully replicated by `MockMvc`. To verify **`Secure`/`HttpOnly`/`SameSite` on actually emitted cookies**, run embedded-container integration tests or test staging over real HTTP.

### 32.2. Testing State Mismatch

Test callbacks lacking a matching authorization request/session to ensure Spring Security **rejects** them:

~~~text
Given:
  Callback has code and state.
  No session holds a saved OAuth2AuthorizationRequest.

Then:
  Login fails.
  Never create an authenticated principal merely because code is present.
~~~

You never need to bypass `state` to test happy paths. Full integration tests require a browser/session repository and a mock Authorization Server honoring the protocol contract.

## 33. Browser End-to-End Tests: Minimum Case Matrix

| Test Case | Cookie | Callback | Expected Outcome |
|---|---|---|---|
| Common happy path | `Secure; HttpOnly; Lax` | Top-level GET | Browser sends cookie; state found |
| `Strict` + cross-site IdP | `Secure; HttpOnly; Strict` | Top-level GET | Cookie withheld; login fails for the expected reason |
| `Lax` + `form_post` | `Secure; HttpOnly; Lax` | Top-level POST | Cookie normally withheld |
| `None` + `form_post` | `Secure; HttpOnly; None` | Top-level POST | Browser sends cookie; CSRF callback config still required |
| `None` missing `Secure` | `HttpOnly; None` | GET or POST | Browser rejects `Set-Cookie` |
| `Secure` + HTTP callback | `Secure` | GET | Cookie withheld per HTTPS policy |
| Different hostname | Host-only cookie for Host A | Callback to Host B | Host-only cookie withheld |
| Path mismatch | `Path=/portal` | Callback `/login/oauth2/code` | Cookie does not match path |
| Shared session store failure | Valid cookie | GET | Server cannot locate session |
| Multi-tab login | Valid cookie | GET | Potential state collision depending on repository |
| Callback POST blocked by CSRF | `None; Secure` | POST | HTTP 403 if CSRF matcher lacks exemption |
| Third-party iframe | `None; Secure` | Embedded | May be blocked by browser privacy rules |

**Do not treat those expected failure cases as errors to keep in production.** They validate mechanics so you pick the right config.

### 33.1. Test Against a Public Staging Host, Not Just Localhost

Cookie matching depends on scheme, hostname, top-level navigation, and browser privacy modes. Run at least one test across:

~~~text
https://staging-portal.example.test
    -> staging IdP
    -> https://staging-portal.example.test/login/oauth2/code/company
~~~

traversing the exact same reverse proxy/load balancer setup as production. Testing only `localhost:8080` misses `Secure`, public hosts, forwarded headers, and third-party policies.

## 34. Common Misconfigurations

### 34.1. Setting `SameSite=Strict` on All Session Cookies

~~~http
Set-Cookie: SESSION=...; Secure; HttpOnly; SameSite=Strict
~~~

With a cross-site IdP, GET callbacks lose the cookie. Choose `Lax` for standard top-level GET flows or design for your callback mode; **never drop `state` checks**.

### 34.2. Setting `SameSite=None` Without `Secure`

~~~http
Set-Cookie: SESSION=...; HttpOnly; SameSite=None
~~~

Browsers reject the cookie. Use:

~~~http
Set-Cookie: SESSION=...; Secure; HttpOnly; SameSite=None
~~~

alongside HTTPS and third-party policy considerations.

### 34.3. Using `form_post` Without Configuring POST Callback CSRF

Even when cookies arrive, Spring Security's CSRF filter blocks the POST. Exempt only the specific callback endpoint when `form_post` is used, while keeping `state`/`nonce`/PKCE validation active.

### 34.4. OAuth Login Start and Callback on Different Hosts

~~~text
Start:    https://app.example.com/oauth2/authorization/company
Callback: https://portal.example.com/login/oauth2/code/company
~~~

Host-only cookies do not travel to Host B. Align canonical hosts/redirect URLs or design cross-host state storage; never widen `Domain` indiscriminately.

### 34.5. Setting `HttpOnly=false` So JavaScript Can Read Sessions

JS not seeing an `HttpOnly` cookie is the desired state. **Never disable `HttpOnly`** to debug OAuth callbacks.

### 34.6. Disabling CSRF App-Wide

~~~java
http.csrf(csrf -> csrf.disable());
~~~

Never use this as a default fix. Session-based browser apps still need CSRF protection for state-changing actions.

### 34.7. `SessionCreationPolicy.STATELESS` on the Login Chain

If Spring Security still relies on `HttpSession` for authorization requests, callbacks lose context. Align session strategies or configure a proper custom authorization request repository.

### 34.8. Trusting `X-Forwarded-Proto` from the Internet

Attackers can spoof headers if proxies fail to strip/normalize them. Enforce trust boundaries at ingress, not just forwarded-header support in Boot.

### 34.9. Blaming Token Expiry When Callbacks Lose Cookies

Callbacks fail **before** token exchange even happens. Distinguish state/session errors from access token expiry, invalid refresh tokens, and Resource Server 401s.

### 34.10. Storing Access Tokens in Session Cookies

Cookies being easy to resend does not make them the right place for access/refresh tokens. In server-side BFFs, keep tokens on the backend and put only a protected opaque session ID in the cookie.

## 35. Symptom-Based Troubleshooting

| Symptom | Hypothesis to Test | Confirmation Signal |
|---|---|---|
| Redirects to IdP fine, callback gets `authorization_request_not_found` | Browser withheld session cookie | Callback Request Headers lack `Cookie` |
| Fails only with `form_post` | `Lax` blocks cross-site POST or CSRF filter blocks POST | Request Method is POST; `SameSite` or 403 on callback |
| Fails only in specific Chrome/Safari profiles | Browser privacy policy or default `SameSite` | DevTools blocked reasons, browser settings |
| Fails over HTTPS behind ingress | Wrong `X-Forwarded-Proto`/`Host` | Broken redirect URI or missing `Secure` attribute |
| IdP reports `redirect_uri_mismatch` | Registered callback differs from generated URI | Compare exact URIs, not cookies |
| Cookie appears in Storage, yet missing on callback | `Secure`/`Domain`/`Path`/`SameSite` restriction | Network request lacks `Cookie` header |
| Cookie sent, yet Spring misses authorization request | Redis/node mismatch, session timeout, multi-tab overwrite | Session store lacks matching request |
| Fails only in second tab | State collision / parallel logins | Two authorization requests in one session |
| Login callback succeeds, then cookie value changes | Session fixation ID rotation | New `Set-Cookie` post-login; flow succeeds |
| Backend API calls work, yet browser gets logged out | Session cookie lost/expired while access token remains | `SecurityContext`/session differs from OAuth tokens |
| Switched to `SameSite=None`, still fails | Third-party blocking, missing `Secure`, CSRF, proxy | Inspect layer by layer |
| JS cannot read `JSESSIONID` | `HttpOnly` configured properly | Browser still attaches cookie on valid requests |
| Cookie does not reach another subdomain | Host-only scope | Callback host differs from cookie-setting host |
| Callback returns 404 | Security matcher/path/context mismatch | Request reaches right URL, filter misses it |
| Fails only when scaling multiple pods | Unshared local sessions | Cookie valid, other node lacks state |
| Immediate re-login after logout fails | Stale cookie/session store/cache mismatch | Old vs. new session ID and cookie serialization |

### 35.1. Rapid Isolation Path

~~~text
OAuth2 callback failure
    |
    v
Are callback URL/scheme/host/path right?
    |-- No -> fix redirect URI/proxy/routing.
    |
    v
Is callback method GET or POST?
    |-- POST -> check SameSite=None;Secure and narrow CSRF callback exemption.
    |
    v
Does browser hold the Portal's cookie?
    |-- No -> inspect Set-Cookie response and browser blocked reasons.
    |
    v
Is cookie sent on the callback request?
    |-- No -> check SameSite, Secure, Domain, Path, expiry, iframe policy.
    |
    v
Does server hold the matching session?
    |-- No -> check TTL, Redis, sticky/shared session, and session ID.
    |
    v
Does OAuth2AuthorizationRequest have matching state?
    |-- No -> check repository, multi-tab, state/nonce/PKCE.
    |
    v
Do token exchange and OIDC validation succeed?
    |-- No -> check token endpoint, client auth, issuer/audience.
    |
    v
Login succeeded; inspect post-login session ID.
~~~

## 36. Hands-On Exercises

### Exercise 1 — `Lax` and GET Callbacks

~~~text
Portal = https://portal.example.com
IdP    = https://login.idp.net
Cookie = Secure; HttpOnly; SameSite=Lax; Path=/
Callback = top-level GET
~~~

**Question:** Can the browser send the session cookie on the callback?

**Solution:** Yes, `Lax` normally allows cookies on top-level cross-site navigations using safe methods like GET, assuming `Domain`/`Path`/`Secure`/expiry and other policies match.

### Exercise 2 — `Strict` and Lost State

Same scenario, except cookie uses `SameSite=Strict`.

**Question:** Should you disable OAuth `state` verification so the callback succeeds?

**Solution:** No. `Strict` cookies may be withheld on cross-site callbacks. Pick a compatible cookie policy or redesign the flow while keeping `state`/`nonce`/PKCE validation intact.

### Exercise 3 — `form_post` and CSRF

The IdP sends POST to `/login/oauth2/code/company`. The browser holds a `SameSite=Lax` session cookie and Spring Security enables its CSRF filter.

**Question:** What two reasons cause this flow to fail?

**Solution:** `Lax` withholds cookies on cross-site POSTs; the CSRF filter blocks the POST callback because it lacks an app CSRF token. Configure `form_post` deliberately: compatible cookies, callback matcher, and full `state`/`nonce`/PKCE checks.

### Exercise 4 — `Secure` and Reverse Proxies

Browsers connect via HTTPS, yet Spring Boot behind a load balancer sees HTTP and builds:

~~~text
redirect_uri=http://portal-service:8080/login/oauth2/code/company
~~~

**Question:** What should you check?

**Solution:** Trusted proxy/forwarded headers, public `baseUrl`, redirect URI registration, and `Secure` cookie config. Never just drop `Secure`.

### Exercise 5 — `HttpOnly`

Frontend runs `document.cookie` and does not see `JSESSIONID`. Yet the browser sends `Cookie` to `/api/me`.

**Question:** Is anything broken?

**Solution:** No. `HttpOnly` prevents JS from reading the cookie value while allowing the browser to attach it to valid requests.

### Exercise 6 — `Domain` and `Path`

Session cookie set:

~~~http
Set-Cookie: SESSION=abc; Path=/employee; Secure; HttpOnly; SameSite=Lax
~~~

Actual callback:

~~~text
https://portal.example.com/login/oauth2/code/company
~~~

**Question:** Why might the cookie not be sent?

**Solution:** Cookie `Path=/employee` does not match callback `/login/...`. Align context path and callback or use a compatible cookie path.

### Exercise 7 — Multi-Replica

Node A stores the authorization request in a local `HttpSession`, and the load balancer routes the callback to Node B. The browser sends the cookie fine.

**Question:** Will `SameSite=None` fix this?

**Solution:** No. The cookie already arrived; the problem is Node B lacks the session state. Use a shared session store or an appropriate routing/session strategy.

### Exercise 8 — Third-Party Iframe

Portal login runs in a cross-site iframe, the cookie has `SameSite=None; Secure`, yet a browser still omits it.

**Question:** Does that contradict `SameSite=None`?

**Solution:** No. Browsers can block third-party cookies for privacy. `SameSite=None` satisfies `SameSite` rules, not a bypass over browser privacy restrictions.

### Exercise 9 — Post-Login Session ID Changes

Before callback the user had `SESSION=S1`; after callback the Portal returns `Set-Cookie: SESSION=S2`.

**Question:** Is that a bug?

**Solution:** Not necessarily. Session fixation protection normally rotates the session ID after authentication. Verify session continuity before the callback and the new cookie post-login; never disable protection just to keep S1.

### Exercise 10 — CORS Does Not Fix Callbacks

GET login callbacks fail with missing `state`. A team proposes:

~~~http
Access-Control-Allow-Origin: *
~~~

**Question:** Will this make top-level browser redirects send session cookies?

**Solution:** No. CORS applies primarily to cross-origin JavaScript requests; `SameSite`/`Domain`/`Path`/`Secure` and the session repository govern OAuth callback navigation cookies.

## 37. Deployment Checklist for OAuth2/OIDC Callback Cookies

| Question | What to Confirm |
|---|---|
| Which host starts browser login? | Canonical public HTTPS host |
| Which host receives callbacks? | Same host/path matching cookie, or deliberate cross-host design |
| Is the callback method GET or POST? | Determines `SameSite` policy |
| Are IdP and Portal same-site? | Based on schemeful site / registrable domain |
| Is the session cookie `JSESSIONID` or `SESSION`? | Identify the real cookie carrying the session |
| Is the cookie `Secure`? | Yes on production HTTPS |
| Is the cookie `HttpOnly`? | Yes for session identifiers |
| What is the cookie `SameSite`? | `Lax` for common top-level GETs; `None` only if cross-site POST is required |
| Does `None` include `Secure`? | Mandatory in modern browsers |
| Does the cookie set `Domain`? | Prefer host-only unless sharing is required |
| Does cookie `Path` match callbacks? | Yes |
| Using `__Host-` prefix? | `Secure`, `Path=/`, no `Domain` |
| Does the browser actually store the cookie? | Check DevTools Storage and blocked reasons |
| Does the browser send the cookie on callbacks? | Check callback Network Request Headers |
| Does login save `OAuth2AuthorizationRequest`? | Repository/session working |
| Does the callback hit the same session? | Valid Session ID, TTL, and store |
| Are `state`/`nonce`/PKCE verified? | Yes—never skip to work around cookies |
| Using `form_post`? | Narrow POST callback CSRF exemption and matching cookies |
| Behind a reverse proxy? | Trusted forwarded headers, accurate public scheme/host |
| Multi-node session store? | Shared store or stable routing strategy |
| Using Spring Session? | Check `DefaultCookieSerializer`; do not confuse with container cookies |
| Multiple login tabs? | Test state correlation and concurrency |
| Does the app have a `STATELESS` chain? | Ensure it does not break session-based login flows |
| Any iframe/third-party contexts? | Evaluate browser privacy restrictions |
| Separated CSRF and session cookies? | Keep `HttpOnly` on sessions, proper CSRF defense |
| Tested in real browsers? | Yes—not only `curl`/`MockMvc` |
| Do logs leak sessions/codes/tokens? | Masked secrets, queries, and headers |

## 38. Summary

**`Secure`**, **`HttpOnly`**, and **`SameSite`** cookies protect distinct aspects of a login session. `Secure` keeps cookies off insecure HTTP channels; `HttpOnly` stops JavaScript from reading session IDs directly; `SameSite` governs whether browsers send cookies across same-site and cross-site contexts. Alongside them, **`Domain`** and **`Path`** define which hosts and paths receive cookies.

In **Servlet Spring Security OAuth2/OIDC Client**, Authorization Code Flow typically saves `OAuth2AuthorizationRequest` in **`HttpSession`**. When the browser returns to the callback, it must carry **the matching session cookie** so Spring Security can look up and verify `state`, plus `nonce`/PKCE data. Accordingly, **`SameSite=Lax`** usually fits **top-level GET callbacks** from cross-site IdPs; **`Strict`** easily drops cookies; and **`None; Secure`** may be required for **`form_post` POSTs**, paired with narrow CSRF callback handling while still subject to browser privacy restrictions.

When OAuth callbacks fail, inspect **browser cookie storage and request headers**, **callback method/scheme/host/path**, **forwarded proxy headers**, and **the server-side session store** before assuming state/token errors. **Never disable `HttpOnly`, CSRF, `state`, `nonce`, or PKCE to mask a cookie configuration bug.** Proper cookie and login-flow configuration not only stabilizes logins, but also preserves clean boundaries among **browser sessions**, **OAuth2 authorized clients**, and **Authorization Server / Resource Server security**.
