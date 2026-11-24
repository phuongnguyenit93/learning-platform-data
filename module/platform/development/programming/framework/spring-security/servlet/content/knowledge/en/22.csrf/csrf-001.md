# CSRF Attack Model and Conditions for Browsers Automatically Sending Credentials

> **Scope:** CSRF (Cross-Site Request Forgery) in Spring Security applications on the Servlet stack. This lesson focuses on how an external page initiates a request carrying a user's identity, **the practical conditions for a browser to automatically send credentials**, and how the server verifies request intent.

## 1. What is CSRF and what does it exploit?

**CSRF** is an attack that causes **an authenticated user's browser** to send an unintended request to a target application. When the server accepts the request solely because it carries a session cookie or credentials automatically attached by the browser, the operation can be executed under the victim's identity.

For example: the victim is logged into `https://bank.example`, then opens a page controlled by an attacker. That page triggers a `POST https://bank.example/transfer` request. Depending on policies and context, the browser may attach the `bank.example` session cookie to the request. If the server verifies the session **without checking a CSRF token or trustworthy proof of intent**, the server may execute the operation.

Three concerns must be separated:

- **Authentication:** "Whose identity does the request have?" A session cookie can answer this question.
- **Authorization:** "What is that identity allowed to do?" Permission checks are still required.
- **CSRF protection:** "Did the state-changing request originate from a legitimate flow prepared by the server for this user?"

Attackers typically **do not know the password**, **cannot read HttpOnly cookies**, and **do not need to read the response**. They exploit the browser's built-in credential-sending mechanism (`ambient authority`). The attack only succeeds when the necessary conditions occur; a standalone cross-site form does not succeed by default.

## 2. Three Actors and Attack Sequence

Assumptions:

- **Target application:** `bank.example` has a `POST /transfer` endpoint requiring a logged-in session.
- **Victim:** a user who already has a valid session in the browser.
- **Attacking page:** `evil.example` can display arbitrary HTML/JavaScript but has no permission to read `bank.example`'s cookies or DOM.

```mermaid
sequenceDiagram
    participant V as Victim / Browser
    participant B as bank.example
    participant E as evil.example
    V->>B: Valid login
    B-->>V: Set-Cookie: JSESSIONID=...; cookie attributes
    V->>E: Open page created by attacker
    E-->>V: HTML with auto-submitting form to bank.example
    Note over V: Browser evaluates host/path, Secure, SameSite, request type
    V->>B: POST /transfer (cookie if allowed to be sent)
    alt Without effective CSRF protection
        B-->>V: May execute business logic under victim's session
    else With CSRF token verification
        B-->>V: Typically 403 if token is missing/incorrect
    end
```

**Decision points:** the malicious page creates the request; **the browser** decides whether to send credentials according to cookies/policies; **the server** decides whether the request is executed. No party in the diagram is allowed to assume the verification step of another party.

### Forged Form Example

This is illustrative HTML on the attacker's domain, with a hypothetical account and endpoint:

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>CSRF Mechanism Illustration</title>
</head>
<body>
  <form id="request" method="POST" action="https://bank.example/transfer">
    <input type="hidden" name="to" value="attacker-account">
    <input type="hidden" name="amount" value="100">
  </form>
  <script>
    document.getElementById("request").submit();
  </script>
</body>
</html>
```

An HTML form is allowed to send a request to a different origin. The attacker does not need to call `document.cookie` on the target application; if cookie conditions are satisfied, **the browser automatically attaches the target host's cookie**. The malicious page's JavaScript does not need to read the HTTP response for the request to cause changes. However, if a `SameSite` cookie is blocked, the session is expired, the CSRF token is missing, or the server rejects the business action, the form fails to achieve its goal.

## 3. Distinguishing “origin” and “site”

**Origin** is defined by the triple `scheme + host + port`. Two URLs differing in any of these components have different origins. **Same-Origin Policy (SOP)** restricts a page from one origin from reading content and manipulating resources of another origin. SOP **does not mean blocking all cross-origin HTTP requests**.

**Site** for modern `SameSite` (`schemeful same-site`) essentially checks the scheme and registrable domain (often called eTLD+1). Two subdomains can be **cross-origin yet same-site** if the scheme matches. Certain special hostnames have different rules.

| URL 1 and URL 2 | Same-origin? | Same-site? |
| --- | --- | --- |
| `https://app.example.com` and `https://app.example.com:8443` | No: different port | Yes |
| `https://app.example.com` and `https://admin.example.com` | No: different host | Yes |
| `http://app.example.com` and `https://app.example.com` | No: different scheme | No (schemeful) |
| `https://evil.example` and `https://bank.example` | No | No |

**Security implication:** a less-trusted subdomain can generate a `cross-origin` yet `same-site` request. SameSite will not necessarily block cookies then. Even when same-site, cookies must still match **host/Domain, Path, Secure, and target context**.

## 4. Under what conditions does a browser automatically send credentials?

### 4.1. Cookies are the most important case

Example of a session cookie an application might set upon login:

```http
HTTP/1.1 200 OK
Set-Cookie: JSESSIONID=opaque-session-id; Path=/; Secure; HttpOnly; SameSite=None
```

Relevant conditions:

1. The cookie **exists and is still valid**; the server-side session is also still valid. An expired/deleted cookie or logged-out session cannot automatically authenticate a request.
2. **Host/Domain:** if the cookie has no `Domain`, it is usually sent only to the host that set it (`host-only`). If it has a valid `Domain`, the host scope can be broader. `bank.example`'s cookie is not sent to `evil.example`; it is considered by the browser when making a request **to `bank.example`**.
3. **Path:** the target request must match the path scope. `Path` controls cookie transmission, but does not create a trustworthy security boundary between applications on the same host.
4. **Secure:** a `Secure` cookie is only sent over an appropriate connection (typically HTTPS); this attribute does not prove the user intentionally initiated the action.
5. **HttpOnly:** prevents JavaScript from reading the cookie via `document.cookie`, but **does not prevent the browser from attaching the cookie to a request**. This is the key distinction for CSRF.
6. **SameSite:** determines in which cross-site contexts the cookie is sent, influenced by request type and navigation.
7. **Browser policies:** third-party cookie restrictions, partitioned cookies, privacy settings, and cookie access permission mechanisms can change the outcome.

A cookie matching the above attributes is merely a **candidate to be sent**; the server must also accept it as a valid session. One cannot conclude from a user "having a logged-in tab open" that every cross-site POST carries a session.

### 4.2. SameSite=Strict, Lax, None

| Cookie attribute | Cross-site form POST | Cross-site top-level GET navigation | Key takeaways |
| --- | --- | --- | --- |
| `SameSite=Strict` | Usually not sent | Usually not sent | Strong cross-site restriction; may affect legitimate navigation flows |
| `SameSite=Lax` (explicitly declared) | Usually not sent | May be sent on top-level navigation using a safe method | State-changing GET remains dangerous |
| `SameSite=None; Secure` | May be sent when browser permits | May be sent when browser permits | Requires independent CSRF protection; no guarantee third-party cookies are always allowed |

**Exception note:** when a cookie *does not declare* `SameSite`, some browsers apply a flexible Lax variant by default, which may allow top-level POSTs for a short window after setting the cookie. This differs from an explicitly declared `SameSite=Lax`. **Do not rely on timing exceptions in security design**, and verify on real browsers.

`SameSite=None` in modern browsers generally requires `Secure`. Additionally, third-party cookie blocking policies or partitioning may restrict cookie sending even with `SameSite=None`. SameSite applies per **site**, so same-site subdomain pages can trigger requests where cookies are still sent if other conditions are met.

### 4.3. Request Types and Browser Behavior

| Originator | Can the request be sent? | Are credentials automatically included? |
| --- | --- | --- |
| HTML form `method="POST"` to another origin | Yes, with a valid form | **Target's** cookie per cookie rules, not the source page's cookie |
| Link click / top-level `GET` navigation | Yes | `Lax` cookies may be sent; GET must not alter state |
| `<img>`, `<script>`, iframe, embedded resources | Can initiate resource loading requests | Depends on context, SameSite, cookie/third-party policy; never use GET for side effects |
| Default cross-origin `fetch(url)` | Can initiate per SOP/CORS | Defaults to `credentials: "same-origin"`, so **does not send** cross-origin cookies under this default mechanism |
| `fetch(url, { credentials: "include" })` | Can send if policy allows | Browser may add matching cookies; JavaScript is still subject to CORS controls when reading the response |
| Cross-origin `fetch` with JSON, non-“simple” headers | Usually requires CORS preflight | Preflight rejection can prevent the actual request; do not assume every request preflights |

**Form POST** uses standard encoding types such as `application/x-www-form-urlencoded`, `multipart/form-data`, and `text/plain`. These simple requests do not necessarily go through CORS preflight. Even when the browser blocks JavaScript from reading the response, the request may **already have been processed by the server**.

### 4.4. Non-Cookie Authentication Mechanisms

- **Browser-managed HTTP Basic/Digest:** the browser can remember and automatically use credentials within the appropriate challenge/realm scope. Whether it automatically sends them on a specific request also depends on cache, challenge, origin, and context; it is not automatically true for every cross-site request.
- **TLS client certificates (mTLS):** browser-managed credentials can be selected/sent at the connection layer. If the server treats this as automatic authentication for an operation, the risk of unintended request triggering still needs evaluation.
- **Bearer token in JavaScript memory, actively added only by a trusted client to the `Authorization` header:** a form on another origin does not possess the token and cannot ask the browser to automatically add arbitrary headers like a cookie. The CSRF attack vector relying on ambient credentials is reduced, though XSS protection and verifying there is no parallel cookie authentication path remain necessary.
- **JWT/Bearer token in a cookie:** even if an application is called a REST API or `stateless`, if the browser automatically sends the cookie containing the token, CSRF remains an issue to evaluate.
- **Systems with multiple authentication methods:** examine every credential the server accepts (session, remember-me, Basic, mTLS, bearer cookie), even if documentation only mentions one primary method.

## 5. Practical Necessary and Sufficient Conditions for CSRF to Cause Harm

A typical attack must simultaneously satisfy these conditions:

1. **Valid victim session:** credentials accepted by the server exist; the victim has permission to perform the action.
2. **Attacker triggers the request:** via form, link, navigation, embedded resource, or an appropriate browser mechanism; the victim must load/interact with the attack content to the required extent.
3. **Request can describe the operation:** endpoint, method, and sufficient parameters are known; the attack does not require reading secrets if the data is already known or predictable.
4. **Browser actually sends the target's credentials:** cookies match host/path/transport and SameSite, or another automatic mechanism allows it.
5. **Server accepts the request as valid and allows state change:** no mandatory valid CSRF token, or misconfigured bypass; no sufficiently strong additional intent verification.
6. **Business logic does not block it:** authorization, transaction constraints, input validation, re-authentication, or anti-replay checks do not reject the operation.

If a single link in this chain is missing, the attack target is not achieved. **CSRF does not bypass authorization:** it exploits permissions the victim actually has. Being able to send a request from an external page also **does not mean** the attacker can read the response or automatically send credentials.

Three diagnostic questions:

- Who **initiates the intent**: a genuine application flow or content controlled by an external page?
- Who **attaches the credentials**: the browser automatically or trusted client code actively adding a secret token?
- What does the server **verify beyond the session**: CSRF token, Origin/Referer, Fetch Metadata, transaction confirmation, and business permissions?

## 6. Why are SOP, CORS, HttpOnly, and POST-only not enough?

**SOP** is primarily a barrier to reading/accessing data across origins. It does not forbid all cross-origin requests. A malicious page can submit a form, even without being able to read the response. Not being able to read the result **does not undo changes that already occurred**.

**CORS** controls whether cross-origin JavaScript may read responses and requires preflight for certain requests. Simple form POSTs can still reach the server. **Not declaring CORS for external origins does not automatically protect endpoints against CSRF**. Even a CORS error in the console does not necessarily mean the server did not process the request.

**HttpOnly** blocks reading cookies from JavaScript; it does not stop the browser from automatically sending cookies. **Secure** protects cookie transport over an appropriate connection; it does not prove intent. These two attributes have their own security value, but they do not replace a CSRF token.

**Merely switching an endpoint from GET to POST** is necessary because GET must be "safe", yet HTML forms can still send POST. Using GET for deletion, money transfers, email changes, or toggling settings also opens extra attack paths via links, navigation, and embedded resources.

**Hiding UI buttons, renaming endpoints, trusting AJAX, or checking hostnames via substrings** also do not replace CSRF verification. Any request describable over HTTP must be verified by the server independently of the UI.

## 7. Defense in Spring Security Servlet

In Spring Security 6 on the Servlet stack, standard `HttpSecurity` configuration **enables CSRF protection by default**. `CsrfFilter` requires a valid token for state-changing methods (e.g., POST, PUT, PATCH, DELETE); by default GET, HEAD, TRACE, and OPTIONS are considered safe methods and do not require a CSRF token.

Processing flow:

1. An HTTP request enters `SecurityFilterChain` on Servlet.
2. `CsrfFilter` determines whether the method/request requires CSRF verification.
3. If required, the filter obtains the expected token via `CsrfTokenRepository` and compares it with the token provided by the client in a form parameter or header.
4. A request with a missing/incorrect token is rejected, **typically with HTTP 403**, even if the browser attached a valid session cookie.
5. A request passing the CSRF check still requires authentication, authorization, and other business rules.

By default, `HttpSessionCsrfTokenRepository` stores the CSRF token in the HTTP session. Spring Security 6 uses a BREACH-aware request token handler and deferred token loading. Therefore, you should not assume that a token stored in a cookie matches the token rendered on the page, or replace the default handler without understanding the integration flow.

### 7.1. Illustrative Java 17+ Configuration

This is a **configuration file inside a Spring Boot 3.x application that already has `spring-boot-starter-security`**, not a standalone Java program that can be compiled with `javac` without Spring libraries.

```java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults())
            .build();
    }
}
```

`SecurityConfig` preserves default CSRF protection because it **does not call `csrf.disable()`**. Suppose there is a `@PostMapping("/transfer")` controller in the same application: a POST request without a token will be blocked before invoking the handler. A POST request with the right token must still pass login, authorization, and data validation checks. This configuration is for applications with form login; public endpoints may also need a CSRF token if they mutate state and accept browser auto-sent credentials.

### 7.2. Legitimate Forms Must Carry the Server Token

The server renders the token based on information from `CsrfToken` into the form. This is an example of **expected HTML output**, where the illustrative string `SERVER_GENERATED_TOKEN` must be the actual value for the request/session, never hardcoded or reused across users:

```html
<form method="post" action="/transfer">
  <input type="hidden" name="to" value="trusted-recipient">
  <input type="hidden" name="amount" value="100">
  <input type="hidden" name="_csrf" value="SERVER_GENERATED_TOKEN">
  <button type="submit">Confirm</button>
</form>
```

The parameter name is usually `_csrf` but should be read from `CsrfToken`; Spring MVC / template engine integrations can automatically add the hidden field. **Inspect the actual HTML** to be sure the token is included with the form.

With AJAX/SPA, a trusted application can send the CSRF token in a header such as `X-CSRF-TOKEN` or `X-XSRF-TOKEN` depending on configuration. If using `CookieCsrfTokenRepository` to support an SPA, you must properly handle how the client retrieves the token and how Spring Security 6 resolves it (especially BREACH-protected token representation and deferred loading). **A token cookie is only useful if the server actually verifies an independent token sent by the client in a header/form**; merely setting a token cookie does not block CSRF.

Do not disable CSRF just because an API uses JSON, the application does not render HTML, uses JWT, or sets `SessionCreationPolicy.STATELESS`. Before excluding an endpoint, you must prove that **no authentication path on the endpoint uses credentials automatically sent by the browser**, and consider login/logout, remember-me, Basic, or parallel cookies.

### 7.3. Defense in Depth

- **Appropriate SameSite:** prefer `Lax` or `Strict` when legitimate flows permit; `None; Secure` only when cross-site communication is required. Still keep CSRF tokens for applications using session cookies.
- **Origin/Referer:** perform exact matching against trusted origins for state-changing requests; have a clear strategy for missing headers, `null`, proxies, and same-site yet untrusted sources. Avoid checking via substring matching on URLs.
- **Fetch Metadata:** `Sec-Fetch-Site` can distinguish `same-origin`, `same-site`, `cross-site`, and `none`; it can block cross-site unsafe requests. Need a fallback policy for browsers/HTTP clients that do not send the header, and consider same-site subdomains.
- **Do not change state with GET:** apply this also to logout with side effects, permission changes, profile updates, and enabling/disabling resources.
- **Re-confirm sensitive actions:** password, MFA, or transaction confirmation mechanisms if required by business logic. This serves as an additional layer for high-risk operations.
- **XSS protection:** scripts running within the application's origin can extract rendered tokens or issue requests just like the application itself; CSRF tokens do not solve XSS.
- **Server-side authorization and validation:** verify each request; do not trust that the UI hid a button or the client validated enough.

## 8. Analyzing Six Scenarios to Avoid Over-Concluding

**A. Session cookie declares `SameSite=None; Secure`, external page submits a POST form.** The browser *may* send the target's cookie if Domain/Path, HTTPS, and cookie policies permit. If the server does not check a token, there is a CSRF risk. If `CsrfFilter` requires a valid token, the forged form is rejected.

**B. Cookie declares `SameSite=Lax`, POST form from a different site.** The cookie is normally not sent with the request. However, do not conclude the application is immune to CSRF in all cases: there are still same-site subdomain contexts, differing cookie configurations, and the Lax-by-default exception for cookies without a declared SameSite.

**C. Cookie `SameSite=Lax`, `GET /delete?id=42` endpoint mutates data.** Cross-site top-level GET navigation can carry the cookie. The main flaw is an unsafe GET design. Move the business logic to an appropriate state-changing method and require intent verification.

**D. SPA uses only an in-memory bearer token and trusted JavaScript adds the `Authorization` header.** An external form does not automatically possess that token or header, so the CSRF path based on auto-sent credentials drops sharply. You still need to address XSS, CORS, and any other cookie/Basic paths the server accepts.

**E. `https://promo.example.com` sends a POST to `https://app.example.com`.** Different origins yet potentially same-site. SameSite allows cookies bound to the target host/path if conditions hold; thus a compromised subdomain can be an untrusted request source.

**F. Browser-managed Basic credentials or TLS client certificates.** You must verify in practice which requests the browser attaches credentials to. If credentials carry identity without user intent, the server must still defend against forged requests.

## 9. How to Verify Using a Test Environment

Use **two self-managed test origins**, one Spring Security Servlet app with a simulated state-updating POST endpoint and one page sending an external form. Avoid using real systems or accounts.

1. Log in with a test account and confirm a valid session.
2. Open DevTools → Application/Storage, inspect the cookie's host/Domain, Path, Secure, HttpOnly, and SameSite.
3. Open the external page containing the form. In DevTools → Network check **whether the browser sends the request**, whether `Cookie`/`Authorization` is present, `Origin`, `Sec-Fetch-Site`, and why a cookie was excluded (if provided by the browser).
4. With CSRF protection enabled, a POST missing a token expects **403**, even when the session cookie is attached. Verify the controller did not run.
5. From a legitimate form rendered by the application with the right token, confirm the POST is processed when logged in and authorized.
6. Test `Strict`/`Lax`/`None`, cross-site POST and top-level GET, requests from a same-site subdomain, default `fetch`, and `credentials: "include"`. Record browser version, cookie policy, and results, avoiding asserting an absolute rule for all browsers.

| Request | Are credentials actually included? | CSRF token | Expected result |
| --- | --- | --- | --- |
| External form POST to app, cookie allowed to be sent | Yes | Missing/wrong | 403 with CSRF filter active |
| Valid app form, valid session and permissions | Yes | Valid | Passes CSRF check and business logic is processed |
| External form POST, cookie blocked by SameSite | No | Missing | Cannot execute under victim's session |
| Cross-site top-level GET with Lax cookie | Possible | Not required for GET by default | Safe only when GET causes no state change |

**Do not use `curl` to prove whether SameSite will or will not send cookies in a browser.** Command-line tools can craft requests carrying arbitrary cookies, but do not fully simulate a browser's site context, top-level navigation, SameSite, third-party cookie policy, and CORS. `curl` can only help verify server-side HTTP/CSRF outcomes using manually supplied cookies/tokens.

## 10. Common Thinking Errors

| Misconception | Correct understanding |
| --- | --- |
| “The cookie has HttpOnly so CSRF is impossible.” | The browser still automatically sends the cookie even though scripts cannot read it. |
| “SOP/CORS blocks unknown origins from sending POST.” | Forms and certain requests still reach the server; being forbidden from reading the response does not mean the server did not execute the change. |
| “Every cross-site request carries the session.” | It must satisfy Domain/Path, Secure, SameSite, request type, browser policy, and an active session. |
| “Same-origin is the same as Same-site.” | They differ; cross-origin subdomains can still be same-site. |
| “Just use POST instead of GET.” | External forms can still send POST; CSRF tokens and business checks are essential. |
| “JWT, API, or stateless means no CSRF needed.” | If cookies or auto-sent credentials are still accepted by the server, the risk remains. |
| “CSRF tokens replace authorization.” | No. Tokens only help verify request provenance; permissions and business constraints must still be checked. |
| “Getting 403 means the browser did not send the cookie.” | The cookie may have been sent, and a missing/wrong CSRF token is what caused Spring Security to return 403. |

### Remember the Model

**External page creates request → browser evaluates whether to attach credentials → server verifies authentication, CSRF token, and authorization → business logic decides whether to mutate state.** To accurately assess risk, you must verify *both sides*: the **browser's** credential-sending behavior and the **server's** request-acceptance mechanism. In Spring Security Servlet applications using session cookies, keep CSRF protection enabled, use GET only for safe operations, configure cookies appropriately, and add Origin/Fetch Metadata checks when needed.
