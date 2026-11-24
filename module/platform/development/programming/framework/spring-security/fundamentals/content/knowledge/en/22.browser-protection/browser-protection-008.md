# Secure cookies and the limits of HttpOnly, Secure, and SameSite

## 1. Core question: is a cookie with "all three flags" completely secure?

In a web application using Spring Security, the browser may receive a session cookie:

~~~http
Set-Cookie: __Host-SESSION=opaque-session-id; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

The three attributes **HttpOnly**, **Secure**, and **SameSite** reduce **different** risk groups, yet they do not turn a cookie into a complete authentication mechanism or eliminate every way of hijacking a session.

- **HttpOnly**: restricts JavaScript from accessing the cookie value via APIs like `document.cookie`.
- **Secure**: instructs the browser to send the cookie over HTTPS connections (with browser-specific exceptions and handling for localhost).
- **SameSite**: restricts when the browser sends the cookie in **cross-site** requests, mitigating several Cross-Site Request Forgery (CSRF) scenarios.

**Key takeaway:** A cookie is a transport/storage vehicle for a value. A session cookie usually holds a **session identifier**, while login state is managed on the server. `HttpOnly` does not remove XSS vulnerabilities, `Secure` does not install TLS or encrypt cookie values stored on the client machine, and `SameSite` does not replace CSRF tokens.

Objectives after this lesson:
1. Read **Set-Cookie** and request **Cookie** headers accurately.
2. Explain the three flags `HttpOnly`/`Secure`/`SameSite` along with the **protection limits** of each flag.
3. Distinguish **origin** from **site**, and understand `Strict`/`Lax`/`None` and when cookies are or are not sent.
4. Understand **Domain, Path, Max-Age/Expires, `__Host-`/`__Secure-` prefixes**, lifetimes, and session fixation / cookie tossing risks.
5. Configure session cookies in **Spring Boot 3.x + Spring Security 6.x**, Java 17+, cleanly separating local HTTP from production HTTPS.
6. Verify via browser DevTools, `curl`, and MockMvc without printing session secrets in API responses.
7. Explain why **CSRF, XSS defenses, logout, session expiry, HTTPS/HSTS, authorization, and server-side session protection** are still required.

> This lesson belongs to **Browser Protection**. Examples focus on **Spring MVC/Servlet and HttpSession**. Cookies used for OAuth/BFF, JWTs in cookies, or Spring WebFlux have distinct requirements; browser principles are the same, while Java code and configuration differ.

## 2. How do HTTP cookies work?

HTTP does not inherently remember identity across multiple requests. Servers commonly use cookies to associate a browser with a session.

~~~text
Request A: browser has no session yet
   Browser -------------------------------> Server
             GET /api/csrf

             Set-Cookie: JSESSIONID=xyz...
   Browser <------------------------------- Server
   Browser stores cookie per Domain/Path/...
   
Request B: browser has a valid session cookie
   Browser -------------------------------> Server
             Cookie: JSESSIONID=xyz...
             GET /api/me

   Server looks up HttpSession from session ID;
   Spring Security reloads Authentication if present.
   Browser <------------------------------- Server
             200 JSON / or login redirect
~~~

**Set-Cookie** is a **response header** sent by the server asking the browser to store a cookie. **Cookie** is a **request header** sent by the browser to the server when the URL/request meets the matching rules. The `Cookie` request header **does not send back `HttpOnly`, `Secure`, or `SameSite` attributes**. The browser stores and enforces those attributes locally.

### 2.1. Common fields in Set-Cookie

~~~http
Set-Cookie: SESSION_ID=example-only; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

| Part | Meaning | Sent in the Cookie request header? |
| --- | --- | --- |
| **SESSION_ID** | Cookie name | Yes, the name is sent in requests |
| **example-only** | Cookie value; example only, not a real session ID | Yes, the value is sent in requests |
| **Path=/** | URL path scope where the browser sends the cookie | **No**, evaluated by the browser itself |
| **Secure** | Only send the cookie over secure connections per browser policy | No |
| **HttpOnly** | Disallow JavaScript from reading/writing the cookie via corresponding APIs | No |
| **SameSite=Lax** | Restrict cookie sending by site relationship and request type | No |

A subsequent request contains only the name/value:

~~~http
GET /api/me HTTP/1.1
Host: app.example.com
Cookie: SESSION_ID=example-only
~~~

Do not check whether a cookie is `HttpOnly` by looking for the text "HttpOnly" in request headers. It appears only in the **Set-Cookie** response header or DevTools' Cookies table.

### 2.2. Session cookies differ from HttpSession, Authentication, and JWTs

A Servlet session cookie typically holds an identifier like **JSESSIONID** (which can be renamed). On the server, `HttpSession` can hold `SecurityContext` or session attributes. The browser does not receive all `UserDetails` or authorities simply by holding `JSESSIONID`.

| Concept | Owner / function | What must NOT be inferred |
| --- | --- | --- |
| **Session cookie** | Browser stores ID, auto-sends when eligible | Having a cookie does not mean the user is authenticated |
| **HttpSession** | Server-side state across requests | Does not necessarily hold Authentication; a session may store only a CSRF token |
| **SecurityContext** | Current Authentication or state persisted via repository | Not a cookie or JWT |
| **JWT access token** | Credential carrying claims per profile, placed in header or cookie | Using a JWT does not mean CSRF can be ignored |
| **CSRF token** | Value validating legitimate state-changing requests | Not a session ID, password, or access token |

For example, when `GET /api/csrf` creates an `HttpSession`, the browser can receive a session cookie **before logging in**. Therefore, cookie presence does not prove authentication. After `POST` login, the session identifier may rotate due to session fixation protection.

## 3. HttpOnly: keeping cookie values away from JavaScript

Example:

~~~http
Set-Cookie: JSESSIONID=abc123; Path=/; HttpOnly
~~~

When a browser stores a cookie marked **HttpOnly**, JavaScript APIs like **`document.cookie`** cannot read or directly overwrite that cookie. Malicious JS injected via an XSS flaw cannot steal the session ID string simply by reading `document.cookie` and exfiltrating it.

### 3.1. What *does* HttpOnly accomplish?

- Reduces the risk of attackers stealing cookies by reading `document.cookie` during an XSS exploit.
- Separates **session credentials** from both legitimate scripts and injected scripts.
- Supports the principle of keeping critical session tokens where JavaScript does not need to read them.
- Acts as defense-in-depth for login cookies, BFF cookies, and credentials accepted automatically by the backend.

**If you can set HttpOnly on session/authentication cookies, do so.** Session cookies do not need JavaScript to read their ID; the browser sends them automatically per policy.

### 3.2. What does HttpOnly *not* do?

**HttpOnly does not stop the browser from sending the cookie in requests.** Even when JavaScript cannot read the value, a same-origin `fetch` can still trigger requests to which the browser automatically attaches the cookie:

~~~javascript
// Runs on a page sharing the application's origin.
fetch("/api/profile", {credentials: "same-origin"})
    .then(response => response.json())
    .then(data => console.log(data));
~~~

If an attacker runs JavaScript in the origin via **XSS**, the attacker can:
- Issue same-origin requests carrying the existing cookie.
- Perform state-changing actions unless the backend enforces extra permissions/rules.
- Read same-origin responses accessible to scripts and steal sensitive data.
- Grab CSRF tokens from the DOM or endpoints if scripts share the app's access level.
- Render fake UI to phish credentials or user input.

**Therefore, HttpOnly does not "fix XSS" and does not prevent attackers from acting inside an open session.** It only closes one **cookie value reading** channel. You must still defend against XSS via output encoding, avoiding unsafe DOM APIs, strong CSP, and JS dependency control.

### 3.3. HttpOnly and DevTools do not contradict each other

In DevTools > Application/Storage > Cookies, developers can inspect cookies and their flags. `HttpOnly` restricts **web-page JavaScript**, not a user/device owner debugging their own browser. Privileged extensions, malware, compromised devices, exposed proxy/logs, and other channels remain risks.

An `HttpOnly` cookie **is still sent** on eligible requests; `HttpOnly` does not replace `Secure`, `SameSite`, CSRF, or server-side authentication.

### 3.4. Do not disable HttpOnly just so an SPA can "read the session"

A common mistake is setting `http-only=false` on a session cookie just so JavaScript can check whether a user is logged in. A better design:
- Keep the session cookie **HttpOnly**.
- Expose a protected **GET /api/me** or session status endpoint returning **non-sensitive metadata**.
- When the frontend needs a username or display roles, return filtered JSON; never return the session ID.
- If the backend must supply a CSRF token to an SPA, use a **dedicated CSRF token mechanism**, never `JSESSIONID` as the CSRF token.

Authorization enforcement always lives on the server, never in an SPA hiding or showing buttons.

## 4. Secure: restricting cookies from traveling over HTTP

Example:

~~~http
Set-Cookie: JSESSIONID=abc123; Path=/; Secure; HttpOnly
~~~

**Secure** instructs the browser to send the cookie only over **HTTPS** according to browser policy and support rules. The goal is preventing session IDs from being transmitted in cleartext over unencrypted HTTP.

### 4.1. Secure does not create HTTPS

If a server only supports HTTP, turning on `Secure` does not generate certificates or switch traffic to TLS. In real environments, you need to:
1. Configure HTTPS and valid TLS certificates.
2. Redirect HTTP to HTTPS by design.
3. Enable **Secure** on session cookies.
4. Use **HSTS** once infrastructure and domain scope are ready.
5. Protect traffic between reverse proxy and backend per your network trust boundary.
6. Never send tokens/passwords in URLs, response logs, or plain HTTP.

If a browser sends a request over plain HTTP to a production host, it will omit the `Secure` cookie. The application may treat the user as logged out, **which is the intended protective behavior**.

### 4.2. What does Secure NOT protect against?

- Does not encrypt the **cookie value stored on disk/in memory** by the browser.
- Does not stop scripts from reading the cookie if **HttpOnly is off**.
- Does not stop CSRF or XSS from hitting **HTTPS** endpoints.
- Does not guarantee the session ID has enough entropy or hasn't leaked into logs.
- Does not guarantee TLS certificates, reverse proxy settings, and HSTS are configured properly.
- Does not invalidate the cookie automatically on logout.
- Does not distinguish ADMIN vs USER privileges.

### 4.3. The localhost exception during learning

MDN notes that some browsers have **special handling for `localhost`** regarding `Secure`. That is no excuse to deploy production over HTTP. Distinguish clearly:
- **Local demo** may use HTTP + non-`Secure` cookies with test passwords strictly on a developer machine.
- **Production** must run over HTTPS + `Secure` cookies with proper hostname/domain policies.
- Never rely on the `localhost` exception to assume `Secure` cookies will work on HTTP staging or real IP/hostnames.

In the Spring Boot example below, the **local** and **default/production** profiles are intentionally configured differently.

### 4.4. Secure behind a reverse proxy

A typical topology looks like:

~~~text
Browser --HTTPS--> Reverse proxy / load balancer
                           |
                           | Internal HTTP (or HTTPS)
                           v
                       Spring Boot
~~~

If the backend does not know the browser connected over HTTPS, redirects, cookies, or HSTS may behave unexpectedly. Conversely, trusting arbitrary `X-Forwarded-Proto` headers sent by Internet clients is dangerous.

Define **trusted proxies** clearly, strip/overwrite untrusted forwarded headers at the edge, configure Spring Boot forwarding properly (e.g., `server.forward-headers-strategy` per environment), and verify **Set-Cookie on the public HTTPS endpoint**, not just internal HTTP.

## 5. SameSite: reducing cookies sent on cross-site requests

**SameSite** controls when a browser sends a cookie in requests that are **same-site** or **cross-site** relative to the initiating page context. It mitigates many CSRF attacks because an attacker's page on another site cannot easily make the browser send the session cookie to the target app on certain requests.

Common values:

~~~http
Set-Cookie: SID=example; Secure; HttpOnly; SameSite=Strict
Set-Cookie: SID=example; Secure; HttpOnly; SameSite=Lax
Set-Cookie: SID=example; Secure; HttpOnly; SameSite=None
~~~

**`SameSite=None` must be paired with `Secure`** to be accepted by modern browsers. The lines above only illustrate valid combinations set over HTTPS; never use dummy IDs as real credentials.

### 5.1. Strict

**SameSite=Strict** permits sending the cookie in **same-site contexts** and restricts sending in **cross-site contexts**, including top-level navigations arriving from another site.

For example, a user is logged into **https://bank.example** and clicks a link to `bank.example` from an external site. With `Strict`, that first navigation request may **omit** the cookie; the user might appear logged out on that initial landing until navigating within the site or following an appropriate flow.

**Pros:** eliminates many cross-site credential-sending scenarios.  
**Cons:** can hurt UX when users arrive from emails, search results, support portals, or external links.

If an application demands high protection and UX tolerates it, `Strict` can be a great fit; test the actual product user journeys.

### 5.2. Lax

**SameSite=Lax** allows cookies on same-site requests and **certain top-level cross-site navigations using safe methods**—typically clicking a link to a GET page. It usually **withholds cookies on cross-site POSTs** or subresource requests in disallowed contexts.

| Request from another site to app | Typically sent under Lax? | Why |
| --- | --- | --- |
| User clicks top-level link to app's HTTPS GET | **Yes** | Top-level navigation + safe method |
| Cross-site JavaScript `fetch` GET with credentials | **No**, if truly cross-site | Not a top-level navigation |
| Cross-site form POST | **No**, with explicit `SameSite=Lax` | Unsafe method |
| Cross-site `img`/`script`/`iframe` subresource | Usually **no** | Not a top-level safe navigation |
| Same-site requests matching path | **Yes** | `SameSite` does not block same-site |

**Important:** A header omitting `SameSite` may be defaulted to Lax by browsers, though in some browsers **Lax-by-default** had a ~2-minute exception for certain newly set cookies on POSTs. **Explicitly declared `SameSite=Lax`** should not be equated with omitting it entirely. Because default behaviors can evolve, set `SameSite` explicitly.

### 5.3. None

**SameSite=None** allows the cookie to be sent in cross-site contexts where other browser rules allow it, including when an app needs iframes or integrations across different sites.

Minimum requirement:

~~~http
Set-Cookie: widget_session=example; Path=/; SameSite=None; Secure; HttpOnly
~~~

However, **`None` does not force browsers to store or send third-party cookies**. Browsers may block third-party cookies, enforce partitioning, or apply privacy protections. **`SameSite=None` does not enable CORS** and does not guarantee login sessions work inside every iframe.

Because of its wider sending scope, when a cookie serves as authentication, protect **CSRF** and audit cross-site integrations, Content Security Policy / framing, clickjacking, cookie lifetimes, and origin trust.

### 5.4. Choosing Strict, Lax, or None?

| Policy | When appropriate? | Trade-offs / limits |
| --- | --- | --- |
| **Strict** | Sensitive pages where UX does not rely on cross-site navigations carrying the session on the first hop | May add friction when opening external links |
| **Lax** | Many traditional web apps needing login preserved when users click links from external sites | Does not replace CSRF; top-level GET still receives cookies |
| **None; Secure** | Cross-site integrations genuinely needing cookies sent | Exposes larger CSRF surface, constrained by third-party cookie policies |
| **Omitted** | Should not be relied upon as a default design choice | Browser defaults and exceptions can vary |

**`SameSite` decisions must reflect real client behavior** and your threat model, not simply "Strict is always best."

## 6. Distinguishing same-origin from same-site

One of the most dangerous misconceptions is equating **origin** with **site**.

- **Origin** uses **scheme + host + port**.
- **Schemeful same-site** compares scheme and **registrable domain** (i.e., eTLD+1 per the Public Suffix List); port usually does not distinguish sites.
- Two subdomains under the same registrable domain can be **cross-origin yet same-site**. Different paths on the same host are both same-origin and same-site.

Example relative to a page open at **https://app.example.com**:

| Target | Same-origin? | Same-site? | Note |
| --- | --- | --- | --- |
| `https://app.example.com/api` | Yes | Yes | Same scheme/host/port |
| `https://app.example.com:8443/api` | No | Yes (site-level) | Different port; site ignores port unlike origin |
| `https://api.example.com/api` | No | Yes | Different subdomain, same registrable domain & scheme |
| `http://app.example.com/api` | No | No (schemeful site) | Different scheme |
| `https://other.example.org/api` | No | No | Different registrable domain |

This example uses illustrative domains under `example.com`/`other.example.org`; actual site rules depend on the Public Suffix List. For internal domains or special suffixes, verify in target browsers rather than splitting strings on dots yourself.

### 6.1. Why are same-site subdomains still risky?

Suppose **app.example.com** holds a `SameSite=Lax` or `Strict` session cookie, while **uploads.example.com** lets outsiders host HTML/JavaScript. The two sites can be **same-site** to the browser, even though they are **cross-origin**. If the untrusted subdomain can trigger requests to `app`, **`SameSite` does not create a security boundary between these two origins**.

Real security still requires:
- CSRF tokens on unsafe methods when using cookie authentication.
- Preventing untrusted sibling subdomains from writing/overwriting cookies via a broad `Domain`.
- CORS allowlisting only genuinely trusted origins.
- Authentication, Authorization, and resource ownership checks.
- Isolating user-uploaded content onto an independent registrable domain when needed.

**Never treat same-site as same-trust.** This is a major limitation of `SameSite`.

### 6.2. CORS does not change SameSite

CORS answers whether JavaScript at origin A may **read responses** from origin B in the browser. `SameSite` answers whether the browser **attaches cookies** in that site context. Cookies are also governed by `Secure`, `Domain`, `Path`, browser privacy policies, and fetch `credentials` mode.

A response permitted by CORS may still omit cookies due to `SameSite` or third-party cookie policies. Conversely, a simple cross-origin POST can be transmitted before the browser checks whether scripts may read the response. Therefore, **never use CORS as CSRF protection**.

## 7. Why does SameSite not replace CSRF tokens?

CSRF protection aims to prevent an attacker's page from making the user's browser send unintended state-changing requests with auto-attached cookies or credentials.

**`SameSite` helps reduce many scenarios, yet has limits**:
1. **Same-site cross-origin**: an untrusted sibling subdomain can still be same-site.
2. **Lax and top-level GET**: GET requests are allowed on qualifying top-level navigations; if developers use GET to delete or update data, `SameSite` does not protect them.
3. **Different browsers/clients**: cookie policies vary and legacy browsers have limited support.
4. **Flows requiring None**: embedding, federated integrations, or cross-site cookies have wider sending scope.
5. **Same-origin XSS**: malicious scripts inside the app can issue requests carrying browser-attached cookies.
6. **Cookie theft via other channels**: `SameSite` does not stop an attacker from replaying a valid ID once obtained, e.g. from a direct HTTP client.
7. **Non-browser clients**: `curl`/backend clients can attach `Cookie` headers manually; `SameSite` is not server authorization.

With session cookies on the Servlet stack, Spring Security **enables CSRF protection by default**. Never disable it merely because you set `SameSite=Strict` or `Lax`.

### 7.1. CSRF tokens and session cookies have distinct roles

~~~text
POST /api/theme/toggle
Cookie: JSESSIONID=<session-id>   -> server locates session/user
X-CSRF-TOKEN: <csrf-token>        -> server verifies request matches
                                     expected token

Then:
  AuthorizationManager checks whether user is permitted
  Controller updates data
~~~

This is a conceptual diagram, not real headers with issued credentials. A CSRF token can be passed via a hidden `_csrf` form field or appropriate header. Never use the session ID as the CSRF token.

### 7.2. POST login and logout

Logging in and logging out are also state changes. With Spring Security Servlet **form login**, `POST /login` typically requires a CSRF token. After login, the CSRF token may be cleared/rotated so clients must fetch the new token. `POST /logout` also requires a token under standard default configuration.

If a `curl` demo returns 403 before login, check the **CSRF token** before concluding the password is wrong. Never fix it by disabling CSRF application-wide.

## 8. Domain and Path: narrowing cookie scope without creating origin-level isolation

Beyond the three main flags, inspect:

~~~http
Set-Cookie: SID=example; Domain=example.com; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

### 8.1. Domain

- **Omitting `Domain`**: the cookie is typically a **host-only cookie**, sent only to the exact host that set it.
- **`Domain=example.com`**: the cookie may be sent to `example.com` and matching subdomains.
- A broad `Domain` exposes the cookie to requests for more hosts, increasing attack surface if any subdomain is untrusted or taken over.
- Servers cannot arbitrarily set cookies for registrable domains they don't own per browser rules; the Public Suffix List blocks things like `Domain=.com`.

**Recommendation for session cookies:** omit **`Domain`** unless cross-subdomain sharing is truly required. In production examples, use **`__Host-`** so browsers enforce host-only binding.

### 8.2. Path

**`Path=/app`** typically instructs the browser to send the cookie only to matching paths under **`/app`**. `Path` narrows which requests receive the cookie, yet **is not a security boundary equivalent to an origin**. JavaScript at other paths on the same origin or cookie-collision conditions can still interact with it.

Never host sensitive and untrusted apps on the same origin and rely solely on different `Path` values for isolation. Use separate origins when a real trust boundary is needed.

### 8.3. Cookie name collisions, cookie tossing, and session fixation

If multiple cookies share a name with different `Domain` or `Path` values, a request can carry multiple values with the same name in one `Cookie` header. Servers/frameworks may pick or parse them differently than expected. A sibling subdomain able to set a broad `Domain` cookie can also perform **cookie tossing** or certain forms of session fixation in vulnerable architectures.

To reduce risk:
- Use clear cookie names and avoid broad `Domain` attributes.
- Use the **`__Host-`** prefix for host-only sessions when HTTPS/`Secure`/`Path=/` conditions are met.
- Regenerate/rotate the session ID upon login to prevent session fixation.
- Never accept an attacker-supplied session ID as a valid authenticated session.
- Isolate uploads/third-party content away from the account origin and cookie scope.

## 9. `__Secure-` and `__Host-` prefixes: enforcing attributes in the browser

Cookie names can carry prefixes that supporting browsers use to **enforce attribute constraints when storing the cookie**.

### 9.1. `__Secure-`

A cookie whose name starts with **`__Secure-`** must be set from an eligible HTTPS context and include the **`Secure`** attribute.

~~~http
Set-Cookie: __Secure-Session=example; Secure; HttpOnly; SameSite=Lax; Path=/
~~~

It **does not** require host-only scope or `Path=/`. When legitimate subdomain cookie sharing is required, `__Secure-` paired with an intentional `Domain` can be considered, while still auditing trust boundaries.

### 9.2. `__Host-`

A cookie with the **`__Host-`** prefix must satisfy:
1. **`Secure`**.
2. Set from an HTTPS/secure origin accepted by the browser.
3. **No `Domain` attribute**.
4. **`Path=/`**.

Example:

~~~http
Set-Cookie: __Host-SESSION=example; Secure; HttpOnly; SameSite=Lax; Path=/
~~~

This is a strong default for session cookies **scoped strictly to the current host**. Supporting browsers reject the cookie if `Secure` is missing, `Path` is not `/`, or `Domain` is specified. Choosing the prefix must therefore be matched with proper server configuration, not merely renaming the cookie string.

**`HttpOnly` is not automatically enforced by `__Host-`.** You must still add `HttpOnly` explicitly to block JavaScript access. Some browsers also support `__Http-` and `__Host-Http-` prefixes enforcing `HttpOnly`; verify compatibility against your target browser matrix.

### 9.3. Prefixes do not replace session lifecycle management

Even a `__Host-SESSION` cookie with `Secure`, `HttpOnly`, and `SameSite=Strict` can still:
- Be leveraged when a same-origin XSS script issues requests.
- Become invalid when the server session expires.
- Be stolen via malware or a compromised device.
- Fail API checks once authentication has been revoked.
- Fail to "auto-logout" all other devices when the user clicks Logout on another session.

Cookie prefixes are browser-side scope/attribute constraints, **not digital signatures or session ID encryption**.

## 10. Expires, Max-Age, session timeout, and credential lifetimes

Cookie lifetime attributes:
- **Expires**: timestamp when the cookie may expire in the browser.
- **Max-Age**: relative duration (in seconds) from receipt; when both are present, browsers prioritize `Max-Age` per specification.
- **Session cookie**: omitting `Expires`/`Max-Age` usually keeps the cookie until the browser session ends per browser policy; browsers may **restore sessions via session restore**, so closing a window is not guaranteed to purge the cookie immediately.
- **HttpSession timeout**: server-side lifetime of the session, never extended indefinitely just because the browser retains the cookie ID.

Example:

~~~http
Set-Cookie: SID=example; Max-Age=900; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

The browser is asked to give the cookie a 900-second lifetime, yet **the server must still enforce `HttpSession`/token expiration**. Do not set an enormous `Max-Age` and treat it as secure session management. After logout or account compromise, invalidate the session/credential on the server rather than merely asking the browser to delete the cookie.

### 10.1. Cookie still present while server session expired

A browser may send an old cookie ID after the server session expired, was invalidated, or disappeared from the shared store. The server must never treat a user as authenticated merely because the `Cookie` header contains `JSESSIONID`. Spring Security looks for a valid `SecurityContext`; if missing, protected requests require re-authentication.

### 10.2. Deleting cookies requires matching scope

For example, returning:

~~~http
Set-Cookie: SID=; Max-Age=0; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

instructs the browser to delete the `SID` cookie with matching name, domain, and path. If the original cookie had a different `Domain`, `Path`, or prefix, a deletion header with mismatched scope can leave the old cookie intact.

**Logout is not merely deleting the cookie in the browser.** You must invalidate the `HttpSession` or revoke credentials server-side; for JWT access/refresh tokens, design an appropriate expiry/revocation strategy.

### 10.3. Session fixation and rotating session IDs after login

An attacker may try to make a user log in using a predictable or attacker-known session identifier. **Session fixation protection** requires rotating/changing the session ID at authentication time via an appropriate strategy.

Spring Security Servlet enables session fixation protection by default for form authentication on modern containers, typically via **`changeSessionId()`**. Consequently:
- The `Set-Cookie`/session ID **before login** and **after login** can differ.
- Clients like `curl` must update their cookie jar after `POST /login`.
- Do not assert an unchanged session ID as a passing test.
- If writing a custom login controller/filter, ensure `SessionAuthenticationStrategy` and `SecurityContext` persistence are invoked properly.

## 11. Spring Boot 3.x, Java 17+ example: explicitly configured session cookie

Let's build an application:
- **GET /**: public endpoint.
- **GET /api/csrf**: issues a CSRF token for requests in the same session.
- **GET /api/me**: accessible only to authenticated users.
- **POST /api/theme/toggle**: mutates session state, requiring **Authentication and a CSRF token**.
- **POST /login / POST /logout**: handled by standard Spring Security form login and logout filters.

Goal: observe two distinct properties:
1. **Cookie response flags** configured via properties.
2. **Business controls** still requiring auth and CSRF even with strong cookie flags.

Two profiles are provided:
- **local**: HTTP `localhost:8080`, using non-`Secure` `JSESSIONID` so `curl` can observe it. Local only, no real secrets.
- **Default for HTTPS deployment**: `__Host-SESSION`; `Secure`; `HttpOnly`; `SameSite=Lax`; `Path=/`; no `Domain` declared. Requires real TLS and a secure proxy.

### 11.1. Create the project

Using Spring Initializr:
- **Spring Boot 3.x**, Java **17+**, **Gradle** build.
- Group **com.example**, artifact **demo**, package **com.example.demo**.
- Dependencies **Spring Web** and **Spring Security**.

File paths:

~~~text
src/main/java/com/example/demo/CookieSecurityDemoApplication.java
src/main/resources/application.yml
src/main/resources/application-local.yml
~~~

Do not write a custom login form or filter, since the goal is **cookie/session flags**, not rebuilding `AuthenticationFilter`.

### 11.2. Complete Java backend

**src/main/java/com/example/demo/CookieSecurityDemoApplication.java**

~~~java
package com.example.demo;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.context.annotation.SessionScope;

@SpringBootApplication
public class CookieSecurityDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(CookieSecurityDemoApplication.class, args);
    }
}

@Configuration
@EnableWebSecurity
class WebSecurityConfiguration {

    @Bean
    SecurityFilterChain webSecurity(HttpSecurity http)
            throws Exception {
        return http
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/", "/api/csrf")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/me")
                    .authenticated()
                .requestMatchers(HttpMethod.POST, "/api/theme/toggle")
                    .authenticated()
                .anyRequest().denyAll())
            .formLogin(form -> form
                .defaultSuccessUrl("/api/me", true)
                .permitAll())
            .logout(logout -> logout
                .logoutSuccessUrl("/login?logout")
                .permitAll())
            // Default CSRF protection remains enabled.
            .build();
    }

    @Bean
    UserDetailsService users() {
        UserDetails learner = User.withUsername("learner")
            .password("{noop}demo123")
            .roles("USER")
            .build();
        return new InMemoryUserDetailsManager(learner);
    }
}

@Component
@SessionScope
class ThemePreference {

    private boolean darkMode;

    public synchronized boolean isDarkMode() {
        return darkMode;
    }

    public synchronized boolean toggle() {
        darkMode = !darkMode;
        return darkMode;
    }
}

@RestController
class BrowserCookieController {

    private final ThemePreference preference;

    BrowserCookieController(ThemePreference preference) {
        this.preference = preference;
    }

    @GetMapping("/")
    Map<String, String> home() {
        return Map.of("message", "open");
    }

    public record CsrfView(
            String headerName,
            String parameterName,
            String token) {
    }

    @GetMapping("/api/csrf")
    CsrfView csrf(CsrfToken csrfToken) {
        return new CsrfView(
            csrfToken.getHeaderName(),
            csrfToken.getParameterName(),
            csrfToken.getToken());
    }

    @GetMapping("/api/me")
    Map<String, Object> me(Authentication authentication) {
        return Map.of(
            "username", authentication.getName(),
            "darkMode", preference.isDarkMode());
    }

    @PostMapping("/api/theme/toggle")
    Map<String, Boolean> toggle() {
        return Map.of("darkMode", preference.toggle());
    }
}
~~~

**Code notes:**
- Only `CookieSecurityDemoApplication` is a public top-level class, matching the Java filename.
- Other classes are package-private and component-scanned in the same package.
- **`@SessionScope`** uses a default scoped proxy to inject `ThemePreference` into the singleton controller. `darkMode` persists per session, not in a static/global variable.
- Default Spring Security **`formLogin`** and **`logout`** handle `POST /login` and `POST /logout` with CSRF protection.
- **`GET /api/csrf`** causes the token to be loaded/generated when `getToken()` is called, which may create a session cookie **even before login**.
- `SessionCreationPolicy.IF_REQUIRED` lets Spring Security create a session when needed; it does not mean "every GET creates a session."
- Password **`{noop}demo123`** is strictly for local learning, never for production.
- The demo never echoes session cookies, `HttpSession.getId()`, refresh tokens, or passwords in JSON.

### 11.3. Cookie configuration for HTTPS (default)

**src/main/resources/application.yml**

~~~yaml
server:
  servlet:
    session:
      timeout: 20m
      tracking-modes: cookie
      cookie:
        name: __Host-SESSION
        http-only: true
        secure: true
        same-site: lax
        path: /
~~~

Explanation:
- **`__Host-SESSION`** uses a prefix requiring `Secure`, host-only scope, and `Path=/`.
- **`secure: true`** forces the `Secure` attribute; public environments must run HTTPS.
- **`http-only: true`** shields the session cookie from direct JavaScript reading.
- **`same-site: lax`** works smoothly with navigation flows while keeping CSRF for POSTs.
- **`path: /`** satisfies the `__Host-` prefix requirement.
- **No `domain` declared** so the server creates a host-only cookie.
- **`tracking-modes: cookie`** tells the container to track sessions via cookies instead of URL rewriting.
- **`timeout: 20m`** sets the server-side session idle timeout; it is not a fixed browser cookie `Max-Age`.

**Actual HTTPS deployment is required.** Enabling these properties on a plain HTTP public host prevents browsers from accepting or returning the `Secure` cookie; with `__Host-`, HTTPS is doubly mandatory. Never switch to insecure settings just to "fix login not sticking."

### 11.4. Local configuration strictly for HTTP practice

**src/main/resources/application-local.yml**

~~~yaml
server:
  servlet:
    session:
      cookie:
        name: JSESSIONID
        secure: false
~~~

In Spring Boot, the `local` profile overrides these two properties from the base config; **`HttpOnly`, `SameSite=Lax`, and `Path=/` remain intact**.

This is an intentional exception for developer workstations. Never activate the `local` profile in production and never accept real credentials over HTTP. If running locally with trusted TLS, you can keep `secure=true` as in production and test browser behavior directly.

### 11.5. Running

In the Gradle project directory:

~~~bash
./gradlew bootRun --args='--spring.profiles.active=local'
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun --args="--spring.profiles.active=local"
~~~

The app runs on **http://localhost:8080** unless `server.port` is changed.

You can open **http://localhost:8080/login** in a browser and log in as `learner`/`demo123`. Afterward, `GET /api/me` returns JSON containing `username` and `darkMode`.

### 11.6. Observing Set-Cookie with curl

In another terminal, use `curl` with a dedicated cookie jar (never share real cookie files):

~~~bash
curl -i -c cookies.txt \
  http://localhost:8080/api/csrf
~~~

Expected output includes the CSRF JSON token and **may include `Set-Cookie`** for the newly created session, e.g.:

~~~http
Set-Cookie: JSESSIONID=<random-value>; Path=/; HttpOnly; SameSite=Lax
~~~

The actual ID is generated by the server and is non-deterministic. Because local mode sets **`secure:false`**, the local response **does not require `Secure`**, which is not a production template. Over HTTPS with the default config, expect cookie name `__Host-SESSION` and **`Secure; HttpOnly; SameSite=Lax; Path=/`** (attribute ordering may vary).

**Never print or paste real session IDs into chats, repositories, screenshots, or public logs.** In the terminal, use `curl -i` only in labs to inspect headers; in real environments, avoid logging or storing secrets in monitoring tools.

### 11.7. POST login and preserving cookies across requests

Using **Bash + Python 3** to extract the CSRF token from JSON:

~~~bash
curl -sS -c cookies.txt \
  http://localhost:8080/api/csrf > csrf-before.json

CSRF=$(python3 -c \
  "import json; print(json.load(open('csrf-before.json'))['token'])")

curl -i -b cookies.txt -c cookies.txt \
  --data-urlencode "username=learner" \
  --data-urlencode "password=demo123" \
  --data-urlencode "_csrf=$CSRF" \
  http://localhost:8080/login

# New request with session cookie after login.
curl -i -b cookies.txt http://localhost:8080/api/me
~~~

Expected: form login returns **302 redirect** to `/api/me`, and the subsequent GET carries the authenticated session and returns **200** with JSON like:

~~~json
{"username":"learner","darkMode":false}
~~~

The cookie jar flags use both **`-b`** and **`-c`** because the session ID may rotate at login for session fixation protection. If `GET /api/me` returns `302 /login`, check whether `curl` sent the updated cookie for the right hostname/path and whether the server stored the session.

### 11.8. SameSite does not replace CSRF: testing state mutation

POST missing CSRF token after login:

~~~bash
curl -i -X POST -b cookies.txt \
  http://localhost:8080/api/theme/toggle
~~~

Expected **403**, and `darkMode` stays **false**. Next, fetch the fresh token for the authenticated session:

~~~bash
curl -sS -b cookies.txt -c cookies.txt \
  http://localhost:8080/api/csrf > csrf-after.json

CSRF=$(python3 -c \
  "import json; print(json.load(open('csrf-after.json'))['token'])")

curl -i -X POST -b cookies.txt -c cookies.txt \
  -H "X-CSRF-TOKEN: $CSRF" \
  http://localhost:8080/api/theme/toggle

curl -i -b cookies.txt \
  http://localhost:8080/api/me
~~~

Expected: valid POST returns **200** with **`{"darkMode":true}`**, and `GET /api/me` reflects `true`. A subsequent POST with an invalid token must be rejected by `CsrfFilter` without changing state.

**Why fetch a new token after login?** Standard authentication flows may clear/rotate the old CSRF token. Never assume `csrf-before.json` remains valid after `POST /login`.

### 11.9. Logout

Fetch the session's current token and POST logout:

~~~bash
curl -sS -b cookies.txt -c cookies.txt \
  http://localhost:8080/api/csrf > csrf-logout.json

CSRF=$(python3 -c \
  "import json; print(json.load(open('csrf-logout.json'))['token'])")

curl -i -X POST -b cookies.txt -c cookies.txt \
  -H "X-CSRF-TOKEN: $CSRF" \
  http://localhost:8080/logout

curl -i -b cookies.txt \
  http://localhost:8080/api/me
~~~

Expected: logout returns **302** to `/login?logout`; the protected GET afterward no longer has a valid authenticated session and typically redirects to login. The old cookie name/value may still linger in the browser/cookie jar even after the server invalidated the session. Never conclude logout failed solely because the cookie name appears; verify server-side validity and protected responses.

### 11.10. These results are expectations only

The examples follow standard Java / Spring Boot 3.x conventions, **not Gradle/curl runs executed in this document**. Exact response headers, cookie attribute order, session creation timing, and redirects can vary by Spring Boot/Tomcat version, proxy infrastructure, browser, and customizations. For cookie attributes, always inspect **Set-Cookie from your running system** and target browser DevTools.

## 12. Integration testing with Spring Security Test and MockMvc

Cookie flags are **properties of responses sent to browsers**, whereas MockMvc tests the filter chain in a simulated servlet environment. We use MockMvc to prove auth + CSRF, then use real HTTP/browsers to verify cookie flags.

In **build.gradle**, if missing:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

This is a Gradle Groovy DSL fragment, not a complete `build.gradle`. Spring Initializr usually already adds `starter-test`; avoid duplicate declarations.

Create **src/test/java/com/example/demo/CookieSecurityDemoApplicationTest.java**:

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CookieSecurityDemoApplicationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void loginPersistsAndCsrfStillProtectsMutation()
            throws Exception {
        MvcResult login = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "learner")
                .param("password", "demo123"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        MockHttpSession session = (MockHttpSession)
            login.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/api/me").session(session))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("learner"))
            .andExpect(jsonPath("$.darkMode").value(false));

        // Valid session without CSRF still cannot mutate state.
        mvc.perform(post("/api/theme/toggle").session(session))
            .andExpect(status().isForbidden());

        // Invalid token must also be rejected.
        mvc.perform(post("/api/theme/toggle")
                .session(session)
                .with(csrf().useInvalidToken()))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/me").session(session))
            .andExpect(jsonPath("$.darkMode").value(false));

        // With valid CSRF: the request is executed.
        mvc.perform(post("/api/theme/toggle")
                .session(session)
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.darkMode").value(true));
    }
}
~~~

Run:

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

**The test above checks Authentication, session persistence, and the CSRF filter.** It does not prove real browsers enforce `Strict`/`Lax`/`None` or **`Secure`/`HttpOnly`** cookies. To verify cookie flags, use:
- HTTP integration tests running against a real embedded servlet container.
- Browser DevTools Application > Cookies and Network > Set-Cookie.
- E2E browser tests in an HTTPS staging/production-like environment.
- Cross-site tests using two distinct registrable domains; merely changing ports on `localhost` **does not** simulate a separate site under `SameSite`.

### 12.1. Checklist for verifying cookie flags over HTTPS

On a public HTTPS host behind a reverse proxy, observe **Set-Cookie** when the real application creates a session:

| What to observe | Why |
| --- | --- |
| Cookie name **`__Host-SESSION`** | Prefix enforces `Secure`, `Path=/`, host-only |
| **`Secure`** | Sent only over eligible HTTPS connections |
| **`HttpOnly`** | Session ID cannot be read via `document.cookie` |
| **`SameSite=Lax`** | Balances navigation UX with CSRF mitigation by design |
| **`Path=/`** | Required by `__Host-` |
| **No `Domain` attribute** | Avoids unintended subdomain exposure |
| No session ID in query/logs | Reduces credential exposure |
| Session ID rotates after login | Default session fixation protection |
| Logout/timeout invalidates authenticated session | Credential revoked server-side |

If the browser **refuses to store** the cookie, inspect Issues/Network tabs to see why: unmet prefix constraints, `Secure` on an ineligible host, `SameSite=None` missing `Secure`, invalid `Domain`, third-party cookie blocking, or TLS/certificate errors.

## 13. Cookie authentication vs Bearer tokens

### 13.1. Session cookie

~~~text
POST /login + form + CSRF
  -> Verify credentials
  -> Store SecurityContext in HttpSession
  -> Browser receives session cookie

GET /api/me
  -> Browser sends cookie (if Secure/SameSite/Domain/Path match)
  -> Server loads session and checks Authentication
~~~

In this model, the browser attaches the cookie automatically; CSRF must be handled for unsafe methods.

### 13.2. Bearer token in Authorization header

~~~http
GET /api/me HTTP/1.1
Authorization: Bearer <access-token>
~~~

The client explicitly attaches the header. Without an auto-sent authentication cookie, the CSRF threat model differs. However, tokens must still be protected from XSS, theft, and replay, and verified cryptographically/via introspection along with issuer, audience, expiry, and scopes/authorities.

### 13.3. What about a JWT stored in a cookie?

~~~http
Set-Cookie: access_token=jwt-value; Secure; HttpOnly; SameSite=Lax; Path=/
~~~

It is still a **cookie** auto-sent by the browser; evaluate CSRF based on how the backend extracts the token from the cookie. Carrying a JWT payload **does not exempt the cookie from `SameSite` or CSRF**. Simultaneously, the backend must still verify the JWT signature and claims. When tokens are not stored server-side, logout/revocation may also need a dedicated strategy.

Never conclude "`HttpOnly` JWT cookie = session" or "JWT cookie = completely stateless": those are orthogonal design dimensions.

## 14. CORS, fetch credentials, third-party cookies, and CHIPS

### 14.1. `credentials: "include"` is not enough for the browser to send cookies

For instance, a frontend at **https://app.example.com** calls an API at **https://api.example.com**:

~~~javascript
const response = await fetch("https://api.example.com/api/me", {
    credentials: "include"
});
~~~

The browser still evaluates:
- `SameSite` between the top-level site and the cookie target.
- `Secure` and HTTPS.
- `Domain`/`Path`.
- Cookie existence, non-expiration, and non-blocking.
- Third-party cookie policies, partitioning, and privacy settings.
- Server CORS allowing the specific origin and credentials when JavaScript needs to read the response.

**CORS responses** for credentialed requests require `Access-Control-Allow-Origin` set to a specific trusted origin and **`Access-Control-Allow-Credentials: true`** where appropriate; never use the `*` wildcard. CORS does not grant API authorization and cannot force the browser to attach cookies blocked by `SameSite` or third-party cookie policies.

### 14.2. Cross-origin is not necessarily cross-site

`https://app.example.com` and `https://api.example.com` are **cross-origin** yet may be **same-site**. If a host-only cookie exists for `api.example.com`, requests to `api.example.com` can carry it when URL/path/protocol and fetch credentials mode permit, even though CORS is still required for JS to read the response.

Never set **`SameSite=None`** merely because frontend and backend sit on different subdomains; first verify whether they are actually **cross-site**. Conversely, two hosts on different registrable domains require evaluating `SameSite=None; Secure` and browser privacy policies if cross-site cookies are strictly necessary.

### 14.3. Partitioned cookies (CHIPS)

Some browsers support **`Partitioned`** cookies, scoping cookies by both top-level site and cookie host for third-party contexts. Example:

~~~http
Set-Cookie: __Host-widget=example; Path=/; Secure; SameSite=None; Partitioned; HttpOnly
~~~

**`Partitioned`** requires **`Secure`** and carries browser-support constraints. It is a tool for embedded widgets with specific needs—**not a replacement for Authentication, CSRF, or CORS**—and does not make every third-party cookie restriction disappear.

Spring Boot provides a cookie `partitioned` property in supporting versions, though this lesson leaves it off since there is no third-party widget flow. Verify actual Spring Boot/container/browser versions before adopting it.

## 15. Common misconceptions

| Claim | Why it is wrong | Accurate understanding |
| --- | --- | --- |
| "HttpOnly blocks all XSS." | XSS can still issue requests carrying cookies | Defend against XSS in code and CSP; `HttpOnly` only limits reading cookies |
| "HttpOnly stops `fetch` from sending cookies." | Browser attaches cookies when eligible | `HttpOnly` does not stop browser networking |
| "Secure means the cookie is encrypted in the browser." | `Secure` primarily restricts transport to HTTPS | Protect device/storage and use real TLS |
| "Secure makes public HTTP apps safe." | It does not generate TLS certificates | Deploy HTTPS and HSTS where appropriate |
| "`SameSite=Strict` makes you immune to CSRF." | Same-site subdomains, XSS, and GET side effects still exist | Keep CSRF tokens for browser cookie auth |
| "`SameSite=Lax` omits cookies on all cross-site requests." | Top-level safe navigations still send cookies | Understand HTTP methods and browsing contexts |
| "Omitting `SameSite` equals explicit `Lax`." | Lax-by-default has exceptions and browser differences | Set `SameSite` explicitly |
| "`SameSite=None` always enables cookies in iframes." | Third-party cookie policies may block them | Test target browsers; consider partitioning/BFF |
| "Different port means cross-site." | Origin includes port; site usually does not | Distinguish origin from schemeful site |
| "Passing CORS means cookies were sent." | Cookie policy is independent | Inspect Network cookies and credentials mode |
| "Having `JSESSIONID` means logged in." | Session may hold only CSRF or attributes | Check `SecurityContext`/`Authentication` |
| "`Secure` cookies mean HSTS isn't needed." | Does not address downgrades or initial visits | Use HTTPS + HSTS and full hardening |
| "`Domain=.example.com` is safer than host-only." | Scope opens to every matching subdomain | Set `Domain` only when needed; prefer host-only |
| "`Path` shields cookies from JS on other paths." | `Path` is not a strong security boundary | Isolate via origin/host and prevent XSS |
| "Deleting the cookie is a complete logout." | Server session/token may remain active | Invalidate sessions / revoke credentials |
| "When `Max-Age` expires, the server knows tokens expired." | Browser expiry differs from server validation | Enforce TTL/idle/absolute session expiration server-side |
| "`__Host-` automatically turns on `HttpOnly`." | Prefix does not mandate `HttpOnly` | Still set `HttpOnly` explicitly |
| "`Set-Cookie` appears in `fetch` `response.headers`." | `Set-Cookie` is a forbidden response header in JS | Inspect Network/DevTools or server tests |
| "A JWT inside a cookie needs no signature check." | Cookie transport creates no trust | Perform full JWT validation plus CSRF if auto-sent |
| "Disable CSRF so login cookies work." | Creates vulnerabilities with auto-sent credentials | Integrate form/header CSRF tokens properly |

## 16. Field troubleshooting guide for session cookie issues

### 16.1. Login returns 302/200 yet the next request loses the session

Check step by step:
1. Did the browser receive **Set-Cookie**? Was it rejected due to prefix/domain/Secure/SameSite?
2. Does the next request carry the expected **Cookie** header?
3. Did path, hostname, port, HTTPS, or redirects change?
4. Does the server session still exist with a persisted `Authentication`?
5. Did session fixation protection rotate the ID without the client saving the new ID?
6. Are there multiple replicas without a shared session store or sticky affinity?
7. Are cookie `Max-Age` and server idle timeout misaligned?
8. Does a cross-origin frontend use proper credentials mode and CORS?

Never randomly turn off `Secure`/`HttpOnly`/`SameSite` to fix 401s or redirects; locate the exact failing layer.

### 16.2. Cookie lacks `Secure` on production HTTPS

Check **`server.servlet.session.cookie.secure`**, active profiles, real headers behind proxies, and forwarding metadata. If the proxy itself issues the session cookie (instead of Spring Boot), fix it at the proxy. Ensure the edge only trusts forwarded headers from trusted proxies, never from Internet clients.

### 16.3. Cookie is `HttpOnly` yet XSS still performs actions

This is expected behavior: XSS does not need to read cookies to call same-origin APIs. Focus on fixing injection, DOM sinks, CSP, response access, and proper authorization/transaction/CSRF controls; never try to solve XSS by renaming `JSESSIONID` to `__Host-SESSION` without fixing the XSS flaw.

### 16.4. `SameSite` breaks payment or SSO flows

Check:
- Is it a top-level redirect or an iframe/cross-site fetch?
- Redirect GET, POST binding, or `form_post` from the Identity Provider?
- `Strict`/`Lax`/`None` and actual schemeful site?
- Which host owns the cookie, and are `Domain`/`Path`/`Secure` right?
- Is third-party cookie blocking or partitioning active?
- Can **`state` parameters, PKCE, server-side sessions, BFF**, or redesigned flows work instead of relaxing cookies globally?

Never switch all session cookies to `SameSite=None` just because one sub-flow fails; evaluate login/callback cookies and protocol design specifically with your security team.

## 17. Production checklist for Spring Security cookie auth

1. **Mandatory HTTPS** with trusted certificates; never transmit credentials over HTTP.
2. Session cookies use **`HttpOnly` + `Secure`**, plus appropriate **`SameSite=Strict` or `Lax`** tested against UX.
3. Prefer **host-only** and **`__Host-`** wherever feasible; omit broad `Domain` attributes unless strictly required.
4. **`Path=/`** when using `__Host-`; verify context paths and reverse proxies.
5. Use **`SameSite=None; Secure`** only for genuine cross-site needs after auditing CSRF and third-party cookie policies.
6. Keep **CSRF protection** enabled for browser session flows, with negative tests for `POST`/`PUT`/`PATCH`/`DELETE`.
7. **Session fixation protection** enabled; ID rotates at login per standard mechanism.
8. Enforce **server-side idle timeout / absolute lifetime** and proper invalidation/revocation strategies.
9. **Never log session IDs, `Cookie`/`Set-Cookie`, passwords, bearer tokens**, or real keys.
10. **Logout** actually invalidates `HttpSession`/credentials; delete cookies with matching Name/Domain/Path to tidy the browser.
11. Audit **XSS and CSP**; `HttpOnly` does not stop malicious scripts from calling same-origin APIs.
12. Protect **authorization, ownership, and tenancy** independently of cookie flags.
13. Audit **third-party subdomains**, DNS takeover risks, cookie tossing, and trust boundaries.
14. Test **CORS, fetch credentials, and `SameSite`/`Secure`** together when frontend and backend are cross-origin.
15. Test **public HTTPS responses behind reverse proxies**, not just local HTTP apps.
16. Audit all **`SecurityFilterChain` beans**, static hosting/gateways, and session stores in multi-replica deployments.
17. Evaluate browser support for `SameSite`/`Partitioned`/prefixes across multiple browsers, not one browser version.
18. Re-verify policies whenever changing domains, CDNs, login providers, or browser embedding setups.

## 18. Self-assessment questions

1. Does `HttpOnly` guarantee an XSS script cannot `fetch` same-origin APIs using the current session? Why or why not?
2. What does `Secure` do for a cookie, and what does it NOT do for TLS certificates?
3. Why might `localhost` HTTP behave differently for `Secure` cookies than production HTTP on a real hostname?
4. How does `SameSite=Lax` differ from `Strict` on top-level navigations from another website?
5. Which attribute is required with `SameSite=None`, and does it guarantee third-party cookies will always be sent?
6. Why are `http://app.example.com` and `https://app.example.com` considered cross-site under schemeful same-site?
7. Are `app.example.com` and `api.example.com` same-origin or same-site? What are the implications for CORS and cookies?
8. When an untrusted subdomain exists, is `SameSite=Strict` enough to stop all CSRF?
9. How does `Domain=example.com` differ from a host-only cookie? Why is a broad `Domain` risky?
10. What conditions does the `__Host-` prefix require? Does it automatically enable `HttpOnly`?
11. Are browser cookie expiration and `HttpSession` expiration the same event?
12. Why must the session ID change after login and why must `curl` retain the updated cookie jar?
13. If `POST` login succeeds yet `GET /api/me` redirects back to login, what steps should be checked?
14. On logout, does deleting the browser cookie alone guarantee credentials were revoked?
15. When a JWT is stored inside an `HttpOnly` cookie, do you still need to evaluate CSRF?
16. Can MockMvc prove a real browser will block `SameSite` cross-site requests? What else must be tested?
17. Why can't JavaScript read **`Set-Cookie`** via `fetch` `response.headers`?
18. Is a CSRF token just a session ID or password under another name?
19. A React app at `localhost:5173` and an API at `localhost:8080` are cross-origin. Are they always cross-site?
20. If you must support an embedded iframe on another site, how would you weigh `SameSite`, third-party cookie restrictions, CSP, and session modeling?

**Remember:** **`HttpOnly`** restricts JavaScript from directly reading cookies; **`Secure`** restricts cookies from traveling over HTTP; **`SameSite`** limits sending cookies on certain cross-site requests. They operate at **different boundaries** and never replace **CSRF protection, XSS protection, HTTPS, authorization, or session lifecycle management**. In Spring Boot, set appropriate cookie flags and **verify actual `Set-Cookie` headers over HTTPS behind proxies**, not merely by reading properties files.

## Official references for further study

- MDN — Set-Cookie, HttpOnly/Secure/SameSite/prefixes: https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie
- MDN — HTTP Cookies: https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Cookies
- MDN — Third-party cookies: https://developer.mozilla.org/en-US/docs/Web/Privacy/Guides/Third-party_cookies
- MDN — Document.cookie and HttpOnly: https://developer.mozilla.org/en-US/docs/Web/API/Document/cookie
- Spring Boot 3.5 — Common Application Properties (server.servlet.session.cookie.*): https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html
- Spring Security 6.5 — Authentication Persistence and Session Management: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html
- Spring Security — CSRF protection: https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html
- OWASP — Session Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
- OWASP — CSRF Prevention Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html
