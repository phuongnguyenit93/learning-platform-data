# SameSite Helps Protect, Yet Does Not Replace All CSRF Checks

## 1. Objectives and Opening Scenario

A banking application uses session cookies to identify users. Developers configure:

~~~http
Set-Cookie: JSESSIONID=abc123; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Because `SameSite=Lax` restricts sending cookies in many requests from external sites, the team considers removing CSRF token checks. That is a dangerous conclusion: **SameSite is a browser-side CSRF risk-reduction layer, not a full replacement for state-changing request validation policies.**

Two easily overlooked cases:

- An attacker tricks a victim into opening a `GET` link from another site to an endpoint **with data-modifying side effects**. With `Lax`, cookies are normally still sent on top-level navigations using a safe method like `GET`. If the server modifies data on `GET`, CSRF can occur.
- Malicious content on `https://evil.example.com` sends a `POST` to `https://app.example.com`. The two origins differ, yet in many setups they are **same site**, so neither `SameSite=Strict` nor `Lax` blocks the cookie; only server-side CSRF token policies or strict origin checks stop it.

After this lesson, you will distinguish site from origin; accurately explain `Strict`, `Lax`, and `None`; know when cookies are sent; examine SameSite's limits; configure session cookies and CSRF checks in Spring Security Servlet with WebFlux/SPA connections; and test both valid paths and cross-site-triggered requests.

**Scope:** Spring Security 6.x with Java 17+, Spring Boot 3.5 for Servlet examples. Certain cookie behaviors depend on browser versions, navigation contexts, and third-party cookie blocking policies; never assume all browsers behave identically.

## 2. How Does CSRF Happen?

**Cross-Site Request Forgery (CSRF)** occurs when a party causes a victim's browser to issue a request to an application where the victim holds an authenticated state, performing an action the victim did not intentionally authorize.

Common conditions:

1. The victim is logged into `https://app.example.com`; the browser holds a valid session cookie.
2. The victim visits `https://attacker.example.net` controlled by an attacker.
3. The malicious page triggers a request to the app, e.g., via an HTML form.
4. If the browser automatically attaches the auth cookie and the server accepts the request without proper origin/challenge validation, the action executes under the victim's privileges.

Simulated malicious form example:

~~~html
<form method="post" action="https://app.example.com/profile/email">
  <input type="hidden" name="email" value="attacker@example.net">
</form>
<script>
  document.forms[0].submit();
</script>
~~~

This merely illustrates how a browser can send a `POST` via an HTML form. It **does not guarantee success**: `SameSite=Lax/Strict` may withhold the cookie in cross-site contexts; and if the server properly enforces CSRF tokens, a tokenless request is rejected even if the cookie is sent.

**Same-Origin Policy (SOP)** normally blocks external JavaScript from **reading responses** from the app unless permitted by CORS. SOP **does not block all requests from being issued**: cross-origin HTML form submissions and navigations can still happen. Thus "attacker JavaScript cannot read the response" does not mean the API is immune to CSRF.

CSRF ties to **credentials auto-sent by browsers**, typically session cookies, though HTTP Basic or other browser auto-authentication mechanisms must also be considered. For APIs accepting only Bearer tokens in `Authorization` actively added per request by the app, the classic CSRF surface differs; XSS/token theft risks remain.

## 3. What Does SameSite Control?

`SameSite` is a `Set-Cookie` attribute instructing **browsers** when to include a cookie on same-site versus cross-site requests. It is not a server-side access-control check and is not honored by every non-browser HTTP client.

Example:

~~~http
Set-Cookie: __Host-session=s3ss10n; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

- `__Host-session`: a cookie name with the `__Host-` prefix; supporting browsers require `Secure`, `Path=/`, and **no `Domain`**. The prefix mitigates certain cross-subdomain cookie injection risks; it does not create a CSRF token.
- `Secure`: sends the cookie only over secure connections, typically HTTPS. Not a CSRF barrier.
- `HttpOnly`: JavaScript cannot read the cookie directly via `document.cookie`. Does not stop XSS from sending authenticated requests.
- `Path=/`: path scope to which the cookie applies. Path is not considered a standalone security boundary.
- `SameSite=Lax`: applies cookie-sending policy based on site relationship and request type.

The server never receives the `SameSite` attribute inside the request's `Cookie` header; the server sees only **the cookie values the browser decided to send**. Hence Spring Security must still verify credentials, authorization, and CSRF per policy rather than treating cookie attributes as proof of user intent.

### 3.1. Site Does Not Mean Origin

An **Origin** is the tuple `scheme://host:port`. Two URLs differing in port or subdomain are **different origins**.

A **Site** in modern SameSite evaluation typically relies on **scheme + registrable domain** (schemeful site), where the registrable domain is determined by the Public Suffix List. Multiple subdomains under one registrable domain count as **same site** despite differing origins; ports do not split sites the way they split origins.

| Requesting URL → Target URL | Same-origin? | Same-site in typical contexts? | Meaning |
| --- | --- | --- | --- |
| `https://app.example.com` → `https://app.example.com` | Yes | Yes | Same origin |
| `https://evil.example.com` → `https://app.example.com` | No | Yes | Sibling subdomain is still same site |
| `https://app.example.com:8443` → `https://app.example.com` | No | Yes | Different port, same site |
| `https://attacker.example.net` → `https://app.example.com` | No | No | Cross-site |
| `http://app.example.com` → `https://app.example.com` | No | Typically no (schemeful) | HTTP/HTTPS differ in scheme |

This table assumes standard domain examples. For special hostnames, domains on the Public Suffix List, localhost, IPs, embedded webviews, or redirect chains, test actual behavior; never split strings on dots manually to infer sites. Redirects can also affect cookie-sending context classification.

**Consequence:** an attacker compromising a subdomain, user-hosted content on a sibling subdomain, or a third-party service CNAME'd to a same-site subdomain can issue requests to the app that the browser considers **same-site**. `SameSite=Strict` does not block them merely because the origin differs. A **host-only** cookie of `app.example.com` is still sent **to `app.example.com`** when a same-site sibling page initiates the request; host-only limits the cookie's **destination**, not ensuring same-origin request initiation.

### 3.2. Strict, Lax, and None Values

| Value | Core rule | Benefit | Things to consider |
| --- | --- | --- | --- |
| `Strict` | Sends cookies only in contexts considered same-site | Stronger restriction on cross-site navigations | Inbound links from external sites may omit the session cookie on first arrival; still permits requests from different origins on the same site |
| `Lax` | Sends in same-site contexts; adds **cross-site top-level navigation using safe methods** like GET | Balances common CSRF defense with external link navigation | State-changing GETs stay dangerous; same-site sibling subdomains are not blocked |
| `None` | Allows cookies in cross-site contexts; modern browsers require `Secure` | Supports legitimate SSO/embed/cross-site flows | Little SameSite CSRF protection; third-party cookies may still be blocked by browsers |

These policies govern **cookie transmission conditions**, not judging whether a request is business-valid. Evaluate `Domain`, `Path`, `Secure`, expiration, browser, and iframe/navigation contexts together.

### 3.3. Browser Behavior Table to Remember

Assuming the cookie is a session cookie whose `Domain/Path/Secure` match the **target** and is not blocked by other browser policies:

| Request-initiating context | Strict | Lax (explicitly declared) | None; Secure |
| --- | --- | --- | --- |
| Same-site POST from sibling subdomain to app | Can send | Can send | Can send |
| Cross-site top-level GET navigation | Not sent | **Sent** | Can send |
| Cross-site top-level POST form submission | Not sent | Normally not sent | Can send |
| Cross-site subresource GET (`img`/`script`) | Not sent | Not sent | Can send |
| Cross-site iframe navigation | Not sent | Not sent under top-level exception | Can send, per third-party cookie policies |

This table describes SameSite policies in typical cases, not guaranteeing every browser version acts identically. Cross-site requests with redirect chains, response-set cookies, and varied browser environments need separate testing.

**Important exception:** When the `SameSite` attribute is **omitted**, some browsers apply **Lax-by-default** with a lenient exception: newly created cookies within a short window (e.g., 2 minutes) can still be sent on certain **cross-site top-level POSTs**. This is **not** the rule for explicitly declared `SameSite=Lax` cookies. Never rely on ambiguous defaults for security design; configure explicitly and keep CSRF protection.

## 4. Why Does SameSite Not Replace CSRF Checks?

### 4.1. Lax Still Sends Cookies on Top-Level GET Navigations

Suppose an app violates HTTP rules with an endpoint:

~~~http
GET /account/delete?confirm=true HTTP/1.1
Host: app.example.com
Cookie: JSESSIONID=...
~~~

If a user clicks a link to that URL from an external site, `SameSite=Lax` can let the browser send the session cookie. Spring Security CSRF by default **does not require a CSRF token for HTTP methods considered safe**, including `GET`. Thus the root bug is **the server mutating state on GET**.

**Proper fix:** move the action to `POST`/`DELETE` accordingly, apply authentication and authorization, require CSRF tokens when credentials auto-send, and add confirmation screens or re-authentication where needed. Never assume "switching to POST" suffices if CSRF remains disabled.

Ensure `GET`, `HEAD`, `OPTIONS`, and `TRACE` never perform business mutations automatically; naming a URL `/logout` or `/delete` does not make the method safe.

### 4.2. Same-Site Yet Cross-Origin: Attackers on Subdomains

~~~text
Victim logged in:      https://app.example.com
Compromised content:   https://blog.example.com
Blog page submits:     POST https://app.example.com/profile/email

Same scheme and registrable domain -> same-site.
Different hosts -> different origins.
App's session cookie can be sent to app.
~~~

`SameSite=Strict`/`Lax` evaluates **site** only, not requiring **same origin**. If `blog` or another subdomain is compromised or lets users post active HTML, attackers can trigger state-changing requests with cookies still attached.

Defense is needed on the backend: valid CSRF tokens **are not auto-sent by browsers**, combined with `Origin`/`Referer` checks against trusted origins, careful `Sec-Fetch-Site` policies for `same-site`, and preventing untrusted subdomains from controlling domain-wide cookies.

### 4.3. CSRF Inside the Application Itself (Client-Side CSRF)

An SPA has JavaScript taking a URL, path, or parameter from untrusted input and using it to build a state-changing request. An attacker can manipulate that input so **first-party JavaScript** sends requests to sensitive endpoints.

Because the request originates from the app's own origin, SameSite, Origin, and Fetch Metadata all look legitimate. If JavaScript auto-attaches the CSRF header to every call without restricting endpoints/methods per trusted config, the token mechanism can be abused indirectly too.

**Prevention:** never let untrusted data freely dictate URLs/methods/bodies for authenticated requests; enforce endpoint allowlists, schema validation, business invariants, server-side authorization; prevent XSS and add confirmation/transaction binding for sensitive actions. CSRF tokens do not fix client-side logic flaws.

### 4.4. XSS Can Bypass Many CSRF Defenses

If an attacker runs script inside the valid origin (XSS), that script can typically send same-origin requests, read form tokens from the DOM, or ride on browser-attached session cookies. `HttpOnly` blocks direct cookie reading yet does not stop scripts from issuing authenticated requests.

Therefore defend against XSS via output encoding, proper CSP, safe HTML/user-content handling, and dependency hygiene. **CSRF protection and XSS prevention are separate layers**; one does not eliminate the need for the other.

### 4.5. SSO Flows, Iframes, and Third-Party Cookies

Apps may use external identity providers redirecting back to callbacks, or require cross-site iframes. `Strict` may omit session cookies on initial navigations from an IdP. `Lax` usually works for cross-site top-level GET callbacks, yet can break form-POST callbacks in setups like `response_mode=form_post`. `None; Secure` supports cross-site cookies yet increases the need for CSRF defense and remains subject to third-party cookie blocking.

With OAuth/OIDC, keep verifying `state`, PKCE, `nonce` where applicable, issuer/redirect URI, tokens, and session binding. `SameSite` **does not replace** `state` or prevent login CSRF/mix-up attacks. Test each specific provider/callback before choosing cookie policies.

### 4.6. Missing Cookies or Non-Browser Clients

Apps issuing multiple cookies (session ID, remember-me, OAuth state, CSRF cookie, app preferences) might assign **different** SameSite values. Setting SameSite only on `JSESSIONID` does not protect other auth cookies. Some apps authenticating via HTTP Basic or reverse-proxy cookies fall outside the app's session cookie settings.

HTTP clients like `curl` can send arbitrary `Cookie` headers and do not enforce browser SameSite rules. Hence **never verify SameSite server-side by trusting clients to obey it**; enforce authentication, authorization, and CSRF mechanisms for browser flows per policy.

## 5. Primary CSRF Defenses and the Role of Each Layer

A cookie-based app can combine:

1. **Synchronizer CSRF token:** server issues an unpredictable token, stores the expected token server-side, safely passes it to HTML forms or JavaScript, and validates it on every state-changing request. Browsers do not auto-copy tokens from app forms into an attacker's arbitrary form.
2. **Signed double-submit cookie:** fits architectures avoiding CSRF state in server sessions. Backend issues a token MAC-bound to a trusted session, browser sends the cookie, and JS/forms send **a copy in a header/field**; backend must verify the signature and session binding rather than merely comparing two attacker-controllable strings.
3. **`Origin`/`Referer` verification:** compare the request's **full origin** (scheme, host, port) against an allowlist/target origin. Never check only domain suffixes with `endsWith("example.com")`.
4. **Fetch Metadata:** use `Sec-Fetch-Site`, `Sec-Fetch-Mode`, and `Sec-Fetch-Dest` to reject obvious unsafe cross-site requests; provide fallbacks for clients/browsers omitting headers and handle `same-site` differently from `same-origin`.
5. **SameSite cookies:** reduce cases where browsers auto-send session cookies from cross-site contexts; configure explicitly per UX needs.
6. **HTTP method discipline and Content-Type policy:** state-changing actions use unsafe methods, never allowing side-effecting GETs; JSON APIs can enforce `Content-Type: application/json` and custom headers to trigger CORS preflight where suitable, though this neither replaces authorization nor acts as the sole barrier.
7. **Authorization/ownership checks and re-authentication:** a valid CSRF token does not prove the user owns another account or has fresh auth to transfer funds. Sensitive actions require authorization and sometimes separate re-authentication/step-up.

**What properties should a CSRF token have?** Unpredictable via cryptographic randomness, bound to the proper session, verified server-side before mutating data, absent from logs/URLs, and refreshed/invalidated across session lifecycle events per framework. Server-rendered forms usually use hidden fields; SPAs usually send dedicated headers on state-changing requests.

**Supporting protections:** `SameSite`, `HttpOnly`, `Secure`, HTTPS, anti-XSS, CORS, and rate limiting each serve different goals. Never use a single cookie flag to replace all endpoint checks.

## 6. Spring Security Servlet: How Is CSRF Handled?

In Spring Security Servlet 6.x:

- `CsrfFilter` performs CSRF checks per policy and rejects requests needing CSRF without a valid token.
- `CsrfTokenRepository` stores and retrieves expected tokens. The default is `HttpSessionCsrfTokenRepository`.
- `CsrfTokenRequestHandler` provides the token to views/controllers and resolves submitted tokens from requests. Spring Security 6 uses `XorCsrfTokenRequestAttributeHandler` by default to support BREACH masking when exposing tokens.
- By default, `GET`, `HEAD`, `TRACE`, and `OPTIONS` are exempt from CSRF token guards; methods like `POST`, `PUT`, `PATCH`, and `DELETE` are checked.
- Tokens are normally accessible via request attribute `_csrf` or `CsrfToken.class.getName()`; HTML forms use the `_csrf` hidden field and the value supplied by the request handler.
- Enabling form login, sessions, or Spring Security does not mean SameSite replaces CSRF. Spring Security **enables CSRF protection by default**; never call `csrf.disable()` arbitrarily just because cookies have `SameSite`.

### 6.1. Why Must CSRF Tokens Live Outside Auto-Sent Cookies?

If an app checks only "did the browser send a session cookie?", requests crafted by an attacker page can still carry that cookie. With synchronizer tokens, the server also requires a value in a **form field/header that browsers do not auto-copy from cookies**. Attackers from untrusted origins normally cannot read the user's page/form across SOP to steal the token, so tokenless requests are rejected.

With `CookieCsrfTokenRepository` for SPAs, the token may sit in an `XSRF-TOKEN` cookie **readable by JavaScript**, which the frontend sends via `X-XSRF-TOKEN`. This differs from an `HttpOnly` session cookie: the session cookie should stay `HttpOnly` where appropriate, whereas the CSRF cookie is designed for JS reading. Calling `withHttpOnlyFalse()` on the **CSRF cookie** is never advice to disable `HttpOnly` on the **session/authentication cookie**.

Spring Security 6 also introduces **deferred** tokens and **BREACH masking**. When an SPA reads the raw CSRF token from a cookie and sends a header, configure an SPA `CsrfTokenRequestHandler` per official docs and refresh tokens when login/logout clears old ones. Changing only the repository while ignoring the request handler or cookie lifecycle can cause valid POSTs to return 403; never "fix" that by turning off CSRF.

## 7. Hands-On Example: Spring Boot 3.5 + Spring Security 6.5, Java 17

The example runs a **standalone Servlet application** with a server-rendered form. It deliberately keeps both `SameSite=Lax` **and** default CSRF tokens. A counter-incrementing POST succeeds only when authenticated with a valid CSRF token; GET reads the counter only.

Requires JDK 17+, Maven, and the following files:

~~~text
samesite-csrf-demo/
├── pom.xml
└── src/main/
    ├── java/example/csrf/CsrfSameSiteDemoApplication.java
    └── resources/application.yml
~~~

**`pom.xml`:**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.0</version>
    <relativePath/>
  </parent>
  <groupId>example</groupId>
  <artifactId>samesite-csrf-demo</artifactId>
  <version>1.0.0</version>
  <properties>
    <java.version>17</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
  </dependencies>
</project>
~~~

**`src/main/resources/application.yml`:**

~~~yaml
server:
  port: 8080
  servlet:
    session:
      cookie:
        same-site: lax
~~~

`server.servlet.session.cookie.same-site` is supported by Spring Boot for session cookies in compatible embedded Servlet containers. For HTTPS production environments, add `secure: true` and evaluate cookie name/`HttpOnly`, path, TTL, and reverse proxies. The sample uses HTTP on localhost for ease of testing, omitting `Secure` in the sample YAML; never deploy production over HTTP.

**`src/main/java/example/csrf/CsrfSameSiteDemoApplication.java`:**

~~~java
package example.csrf;

import java.util.concurrent.atomic.AtomicInteger;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.MediaType;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class CsrfSameSiteDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(CsrfSameSiteDemoApplication.class, args);
    }

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/login").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            // CSRF is ENABLED by default; do not call csrf.disable().
            .build();
    }

    @Bean
    UserDetailsService users() {
        return new InMemoryUserDetailsManager(
            User.withUsername("demo")
                // Demo only: never store plaintext/noop passwords in production.
                .password("{noop}demo123")
                .roles("USER")
                .build());
    }
}

@RestController
class DemoEndpoints {
    private final AtomicInteger changes = new AtomicInteger();

    @GetMapping("/")
    String home() {
        return "Open /form after login; GET /status to read changes";
    }

    @GetMapping("/status")
    String status() {
        return "changes=" + changes.get();
    }

    @GetMapping(value = "/form", produces = MediaType.TEXT_HTML_VALUE)
    String form(HttpServletRequest request) {
        CsrfToken csrf = (CsrfToken) request.getAttribute(
            CsrfToken.class.getName());

        // CsrfToken.getToken() materializes the deferred token when needed.
        return """
            <!doctype html>
            <html lang="en">
              <body>
                <h1>Test state change</h1>
                <form action="/change" method="post">
                  <input type="hidden" name="%s" value="%s">
                  <button type="submit">Perform change</button>
                </form>
              </body>
            </html>
            """.formatted(csrf.getParameterName(), csrf.getToken());
    }

    @PostMapping("/change")
    String change() {
        return "changes=" + changes.incrementAndGet();
    }
}
~~~

**Code explanation:** `@SpringBootApplication` scans controllers in the same package. Every URL except `/` and `/login` requires authentication. `GET /form` reads the CSRF token from the request attribute and embeds it in a hidden field. Because Spring Security generates this value, it is not arbitrary user input. When the browser submits, `CsrfFilter` verifies the token before calling `change()`; the method runs only if all checks pass. `AtomicInteger` is single-process demo state, not a real data store.

Run the application:

~~~bash
mvn spring-boot:run
~~~

Browser testing:

1. Open `http://localhost:8080/status` while logged out: redirected to the login page.
2. Log in with `demo` / `demo123` at `http://localhost:8080/login`.
3. Open `http://localhost:8080/form` and inspect HTML showing hidden input `name="_csrf"` with a generated value.
4. Click the button: `POST /change` succeeds, returning `changes=1` on the first run in a new session.
5. Open `/status`: reads state only; does not increment the count.
6. Using DevTools/HTTP client, replay the POST with **a valid session cookie yet omitting `_csrf`**: Spring Security returns **403 Forbidden**; counter stays unchanged.
7. Replay POST with a wrong or post-session-change stale `_csrf`: **403 Forbidden**. Upon logging out, obtain a fresh token for the new login/session flow.

**Notable point:** Spring Security requires a valid token **even when the browser sends the session cookie**. Setting `SameSite=Lax` only adds a layer preventing certain cross-site requests from carrying cookies; it does not make the CSRF filter skip verification.

### 7.1. Which curl Results Are Trustworthy?

~~~bash
# Without session: redirects to login page.
curl -i http://localhost:8080/status

# With an authenticated session, yet omitting the CSRF token:
# curl -i -b "JSESSIONID=<valid-session-id>" -X POST \
#   http://localhost:8080/change
# Result: HTTP 403 (if session has valid permissions).
~~~

`<valid-session-id>` is a placeholder to replace with **your own test session ID**; never use someone else's cookies. Since `curl` does not simulate full browser SameSite policies, this test **verifies the server-side CSRF guard**, not how browsers actually attach cookies during cross-site navigation.

**Do not put tokens in URLs:** all examples intentionally avoid placing CSRF tokens in query strings. Token values in URLs can leak into history/logs/analytics. Use form bodies or appropriate headers.

## 8. Automated Testing with MockMvc

Spring Security Test lets you mock a valid user and attach CSRF tokens to requests. To run tests, add the two test dependencies to `pom.xml`:

~~~xml
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-test</artifactId>
  <scope>test</scope>
</dependency>
<dependency>
  <groupId>org.springframework.security</groupId>
  <artifactId>spring-security-test</artifactId>
  <scope>test</scope>
</dependency>
~~~

Create **`src/test/java/example/csrf/CsrfSameSiteDemoApplicationTests.java`**:

~~~java
package example.csrf;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CsrfSameSiteDemoApplicationTests {
    @Autowired
    MockMvc mvc;

    @Test
    void authenticatedPostWithoutCsrfIsForbidden() throws Exception {
        mvc.perform(post("/change").with(user("demo")))
            .andExpect(status().isForbidden());
    }

    @Test
    void authenticatedPostWithCsrfSucceeds() throws Exception {
        mvc.perform(post("/change")
                .with(user("demo"))
                .with(csrf()))
            .andExpect(status().isOk());
    }
}
~~~

Run:

~~~bash
mvn test
~~~

The two tests verify `CsrfFilter`'s expected logic: an authenticated request missing a CSRF token is rejected, while an authenticated request with a token is accepted. This suite **does not simulate full browser SameSite cookie algorithms**; testing `Strict/Lax/None` requires real browsers, distinct hostnames/HTTPS, and cross-site test environments.

## 9. Session Cookie SameSite in Spring Boot and Other Cookies

### 9.1. Configuring Servlet Session Cookies

~~~yaml
server:
  servlet:
    session:
      cookie:
        same-site: lax
        http-only: true
        # Production HTTPS environment: add secure: true
~~~

Or in `application.properties`:

~~~properties
server.servlet.session.cookie.same-site=lax
server.servlet.session.cookie.http-only=true
~~~

This configures the Servlet container / Spring Session cookie accordingly. **It does not automatically change all other cookies** issued by the app, proxies, OIDC libraries, or external services. For custom cookies, use `ResponseCookie`, `CookieSameSiteSupplier` (Servlet, Boot), or framework mechanisms to set SameSite. Inspect real `Set-Cookie` headers after login, refresh, logout, and callbacks.

### 9.2. Domain and Path Affect Security

~~~http
Set-Cookie: SESSION_ID=s1; Domain=example.com; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

A `Domain=example.com` cookie can be sent to many subdomains within that scope. Weigh that carefully when hosting user content or third-party services on subdomains. **Do not set `Domain` unless cookie sharing is genuinely required.** Host-only cookies with the `__Host-` prefix prevent subdomains from setting matching-named cookies for parent hosts in supporting browsers.

`Path` limits the target path receiving cookies, not serving as a barrier against JavaScript or untrusted apps on the same origin. Never treat ports or paths as security boundaries replacing authorization.

### 9.3. Strict, Lax, and None: Choose by Real Flow

- **Strict:** suits highly sensitive cookies if users do not need cookies on externally initiated navigations. Can affect deep links, email links, SSO, and returning-user UX.
- **Lax:** generally sensible for standard web sessions with links/redirects from external sites. Must still keep the CSRF filter on unsafe methods and keep GET strictly read-only.
- **None; Secure:** intended for deliberate cross-site interactions (embedded apps, specific callback flows) when browsers allow it; requires proper CSRF token/Origin defenses and watching third-party cookie blocking.

Choose per cookie purpose. An app might use `Lax` for session cookies while another redirect-protocol cookie uses a different policy; never blindly set `None` on every cookie to "fix" SSO errors without assessing attack impact.

## 10. SPAs, CSRF Token Cookies, and Masked Token Issues

SPAs using `fetch`/XHR usually lack server-rendered HTML forms. Two common models exist:

**SPA + backend session/BFF:** the browser holds an `HttpOnly` session cookie; frontend obtains the CSRF token from a bootstrap page/endpoint or readable CSRF cookie, then attaches it in headers on `POST`/`PUT`/`PATCH`/`DELETE`. The server still compares against the expected token for the request/session.

**SPA using only Bearer Authorization headers:** if every authenticated request requires `Authorization: Bearer ...` actively added by JavaScript and **zero** auto-sent cookies/Basic auth are accepted by the server, classic CSRF may no longer be the primary risk. Still audit every endpoint, token storage, XSS, CORS, and token theft; never conclude solely because "the API uses JWT".

In Spring Security 6, `CookieCsrfTokenRepository.withHttpOnlyFalse()` lets SPAs read the `XSRF-TOKEN` cookie and send `X-XSRF-TOKEN`. **Use this only for the CSRF token cookie** and configure the proper request handler per Spring Security 6 docs to handle BREACH masking and deferred-token behavior. Upon login/logout, old CSRF tokens may be cleared and new ones required.

Client-side example **after the system properly issues a CSRF token**:

~~~javascript
const token = readCsrfTokenFromTrustedBootstrap();
await fetch("/profile/email", {
  method: "POST",
  credentials: "same-origin",
  headers: {
    "Content-Type": "application/json",
    "X-CSRF-TOKEN": token
  },
  body: JSON.stringify({ email: "me@example.com" })
});
~~~

`readCsrfTokenFromTrustedBootstrap()` is **a placeholder for your implemented frontend integration layer**, not a default browser or Spring Security API. With `XSRF-TOKEN` cookie setups, the header name is normally `X-XSRF-TOKEN`; match whichever `CsrfTokenRepository` and `CsrfTokenRequestHandler` you actually use. This snippet illustrates **setting the header**, not a standalone JavaScript app.

### 10.1. Why Not Allow Arbitrary CORS?

`Access-Control-Allow-Origin: *` combined with credentialed requests is invalid under CORS browser rules; overly broad origin lists or unvalidated origin reflection can allow external sites to read data or widen exploitability. CORS governs cross-origin response sharing, not verifying who is allowed to mutate resources. Enabling proper CORS **does not replace** CSRF tokens or authorization on cookie-based endpoints.

## 11. Origin, Referer, and Fetch Metadata: Supplemental Checks

### 11.1. Origin/Referer Checks

For state-changing requests, the backend can compare `Origin` (if present) against allowed app origins, e.g., exact `https://app.example.com`. If `Origin` is absent per context, `Referer` may be checked per policy; avoid logging raw URLs with query strings to prevent data leaks.

- `https://app.example.com` is one origin.
- `https://evil.example.com` is **not** that origin, even if same site.
- `https://app.example.com.attacker.net` is also **not** that origin.
- `Origin: null` or missing headers must follow a defined fallback policy; never treat them as "same-origin" by default.
- Behind reverse proxies, know the real target origin seen by clients; never blindly trust `X-Forwarded-Host` which clients can spoof unless stripped/normalized by the proxy.

`Origin` does not replace permissions or CSRF tokens when legitimate cases involve multiple sources or legacy clients. If an API allows multiple origins, use a strict allowlist and know which origins can trigger state changes.

### 11.2. Fetch Metadata Checks

Modern browsers can attach:

~~~http
Sec-Fetch-Site: cross-site
Sec-Fetch-Mode: navigate
Sec-Fetch-Dest: document
~~~

`Sec-Fetch-Site` can be `same-origin`, `same-site`, `cross-site`, or `none`. A defense policy can reject unsafe `cross-site` requests while requiring extra checks for `same-site` when sibling subdomains are untrusted. `none` typically appears in user-initiated direct navigations; handle per method and workflow.

Do not treat every request missing `Sec-Fetch-*` as trusted: older clients and non-browsers may omit these headers. Combine fallbacks via CSRF tokens/Origin/Referer per policy. Non-browser clients can forge headers, so Fetch Metadata **is not an identity authentication mechanism**.

### 11.3. For Financial Actions or Credential Changes

Beyond CSRF guards, apply re-authentication/step-up, transaction confirmation, attempt limits, and per-object authorization checks. A request with a valid CSRF token may still lack eligibility to change an MFA phone number or transfer money.

## 12. WebFlux: SameSite and CSRF Remain Two Separate Configurations

Spring WebFlux apps use `ServerHttpSecurity`, `SecurityWebFilterChain`, and `WebSession` instead of Servlet `HttpSession`. Spring Security WebFlux also enables CSRF protection by default when security is configured appropriately and stores expected tokens in `WebSessionServerCsrfTokenRepository` by default.

**Illustrative configuration fragment** in a cookie-authenticated WebFlux app:

~~~java
@Bean
SecurityWebFilterChain security(ServerHttpSecurity http) {
    return http
        .authorizeExchange(auth -> auth
            .anyExchange().authenticated())
        .formLogin(Customizer.withDefaults())
        // CSRF remains enabled by default.
        .build();
}
~~~

Required imports: `org.springframework.context.annotation.Bean`, `org.springframework.security.config.Customizer`, `org.springframework.security.config.web.server.ServerHttpSecurity`, and `org.springframework.security.web.server.SecurityWebFilterChain`. This snippet **must sit inside a `@Configuration` class of a WebFlux app**, not a standalone Java program.

Spring Boot WebFlux provides `server.reactive.session.cookie.same-site` to configure `WebSession` cookies, e.g.:

~~~properties
server.reactive.session.cookie.same-site=lax
~~~

To let SPA clients read the CSRF token cookie, choose `CookieServerCsrfTokenRepository.withHttpOnlyFalse()` and integrate tokens per WebFlux documentation. Never copy Servlet `HttpSecurity`, `CsrfTokenRepository`, or `server.servlet.session.cookie.same-site` verbatim into WebFlux.

Although both stacks support SameSite cookies, servers must still validate CSRF when using auto-sent credentials. Reactive and non-blocking **does not** mean the app is automatically immune to CSRF.

## 13. Real-World Application Test Matrix

Test over HTTPS with appropriate hostnames such as `app.example.com`, `blog.example.com`, and `attacker.example.net`; use test environments you legally own rather than third-party services.

| Test | Goal | Expected outcome to verify |
| --- | --- | --- |
| Same-origin POST, with session and token | Valid flow | Succeeds if authorized and payload valid |
| Same-origin POST, with session yet missing token | CSRF filter | Rejected, typically 403 |
| Same-origin POST with wrong token | CSRF filter | Rejected |
| Cross-site top-level GET to read-only page | `SameSite=Lax` | Cookie may be sent and GET must not mutate state |
| Cross-site POST form, explicit Lax cookie | `SameSite` | Browser normally withholds cookie; if request arrives, server still enforces CSRF guard |
| Same-site sibling subdomain POST | Site vs. origin scope | Cookie may be sent, yet CSRF token/Origin policy still blocks forged requests |
| Cross-site iframe, `None; Secure` cookie | Embed/third-party policy | Cookie may be sent if browser permits; unsafe requests still validated |
| Cookie omitting SameSite getting browser default Lax | Per-browser behavior | Evaluate new-cookie exception and browser variance |
| OAuth/OIDC callback GET/POST | SSO | Callbacks do not break unintentionally; `state`/nonce/PKCE still verified |
| Login/logout | Session lifecycle | Tokens issued/refreshed/cleared properly; logout uses protected method |
| Same-origin XSS | CSRF bypass risk | Defend against XSS rather than relying solely on SameSite |
| Browser omitting Fetch Metadata | Fallback | Never automatically treat headerless requests as trusted |
| Request missing `Origin` or `Origin: null` | Fallback policy | Handle per explicit rules, never blindly allow |
| API using solely Bearer header | CSRF scope | Verify server rejects auto-sent cookies/Basic on the same route |

**DevTools inspection:** inspect `Set-Cookie` on responses; check exact cookie attributes, whether the browser rejects cookies, whether requests carry `Cookie` headers, what `Origin` and `Sec-Fetch-Site` show, whether `_csrf`/CSRF headers appear, response codes, and whether server data changed. Never deduce solely from a cookie-storage screenshot.

**Distinguishing 302/401/403:** requests lacking a session may redirect to login (302) or return 401; requests with a session yet missing CSRF token are normally blocked with 403. Thus cross-site POST tests need not always return 403: if SameSite drops the session cookie, the app may treat the request as unauthenticated.

## 14. Common Mistakes and Fixes

**Mistake 1 – "With `SameSite=Strict`, CSRF tokens aren't needed."** Sibling subdomains are still same-site; XSS/client-side CSRF remain unaddressed. **Fix:** keep CSRF guards on cookie-based unsafe requests alongside Origin/Fetch Metadata per risk.

**Mistake 2 – "`Lax` blocks every request from other sites."** Lax still sends cookies on cross-site top-level safe navigations like GET. **Fix:** keep GET read-only; test real links/redirects.

**Mistake 3 – "Omitting `SameSite` gives a safe Lax default."** Default behavior and short-lived exceptions vary across browsers. **Fix:** declare SameSite explicitly and keep server CSRF guards.

**Mistake 4 – "Same site means same origin."** `https://evil.example.com` and `https://app.example.com` are different origins. **Fix:** enforce full origin validation when policy requires same origin; never treat all subdomains as trusted.

**Mistake 5 – "Setting `HttpOnly` blocks CSRF."** `HttpOnly` stops JavaScript from directly reading cookies, yet browsers still auto-send them when eligible. **Fix:** CSRF tokens, SameSite, origin checks; defend against XSS separately.

**Mistake 6 – "`Secure` and HTTPS stop CSRF themselves."** HTTPS protects the channel; attacker-triggered requests still travel over HTTPS to the app. **Fix:** verify request intent via CSRF defense.

**Mistake 7 – "Disable CSRF for all APIs because they return JSON."** Endpoints using session cookies/Basic can still receive browser auto-sent credentials. **Fix:** inventory every security chain, credential type, and delivery path; exempt only with solid justification.

**Mistake 8 – "Disable CSRF to fix SPA 403 errors."** Spring Security 6 uses deferred/masked tokens and rotation after login/logout. **Fix:** configure SPA request handlers, token refresh flows, and proper headers.

**Mistake 9 – "Use one static hardcoded CSRF token in HTML."** Static tokens fail to protect sessions properly and can be guessed/leaked. **Fix:** let the framework generate and verify tokens via a proper repository.

**Mistake 10 – "Only check that `Referer` contains `example.com`."** `https://example.com.attacker.net` passes naive substring checks. **Fix:** parse and compare exact origins; handle proxies and missing headers explicitly.

**Mistake 11 – "CORS blocks all CSRF."** Cross-site forms and navigations do not depend entirely on CORS; CORS is not authorization. **Fix:** protect server-side.

**Mistake 12 – "Use GET for logout/account deletion because links are convenient."** GET is treated as safe and unprotected by default CSRF. **Fix:** use POST/DELETE with tokens and proper checks.

**Mistake 13 – "Session cookie SameSite protects every cookie."** Remember-me, OAuth state, and proxy-issued cookies can carry different attributes. **Fix:** audit every `Set-Cookie` and configure at the source.

**Mistake 14 – "`SameSite=None` always makes SSO and iframes work."** Browsers may restrict third-party cookies while CSRF risk persists. **Fix:** test SSO flows and OAuth standards, considering server-side/BFF or supported alternatives per environment.

## 15. Deployment Checklist

1. List **every state-changing endpoint**, HTTP method, accepted credentials, and permitted frontend origins.
2. Allow zero business mutations on `GET`/`HEAD`/`OPTIONS`/`TRACE`.
3. For browser cookie-auth, keep Spring Security CSRF protection enabled and send tokens in properly named form fields/headers.
4. Set `SameSite=Lax` or `Strict` per session needs; use `None; Secure` only for genuinely necessary cross-site flows.
5. Enforce HTTPS in production, `Secure`/`HttpOnly` cookies, minimal Domain scope, `__Host-` prefix consideration, timeouts, and session ID rotation.
6. For SPAs, check `CsrfTokenRequestHandler`, repository, masked/deferred tokens, and fetching fresh tokens after login/logout.
7. Validate `Origin`/`Referer` and Fetch Metadata as supplemental layers; account for same-site cross-origin and headerless browsers.
8. Never treat CORS, JWT, `HttpOnly`, or `SameSite` in isolation as proof CSRF is solved.
9. Automate missing/invalid CSRF token tests, add browser tests for cross-site GET/POST and sibling subdomains, and verify OAuth callbacks.
10. Keep authorization and input validation at the business layer; add re-authentication/step-up for sensitive actions when appropriate.

## 16. Self-Check Questions

**Q1.** Does `SameSite=Lax` stop an external site from leading a user to `GET /delete?id=123`?  
**Answer:** Not reliably; on cross-site top-level GETs, Lax can still send cookies. The server itself must never mutate data via GET.

**Q2.** A script on `https://blog.example.com` submits a form to `https://app.example.com`. Does `SameSite=Strict` guarantee blocking the session cookie?  
**Answer:** No. The two origins differ yet are typically same-site. Server-side CSRF token/Origin policies are required.

**Q3.** Does adding `HttpOnly` to the session cookie automatically act like a CSRF token?  
**Answer:** No. `HttpOnly` only prevents JS from directly reading the cookie; browsers still auto-send it.

**Q4.** Why did two POST requests carrying the same cookie yield 403 and 200 in the demo?  
**Answer:** The CSRF filter checks an additional session-bound token; having a cookie and authentication alone is insufficient.

**Q5.** When does `SameSite=None` make sense?  
**Answer:** When a legitimate flow requires sending cookies in a cross-site context, paired with `Secure` and browser policy checks; CSRF defense matching credentials and endpoints is still needed.

**Q6.** What does Spring Security use by default to store expected CSRF tokens in Servlet apps?  
**Answer:** `HttpSessionCsrfTokenRepository`. For SPAs, a cookie-based repository and matching request handler can be used.

**Q7.** Should CSRF be disabled if an API is called with Bearer tokens?  
**Answer:** Consider only after confirming all API auth paths avoid browser auto-sent credentials, other defenses exist, and cookie/Basic endpoints are not overlooked; using JWT alone is insufficient reason.

**Q8.** Why is Fetch Metadata not a standalone security layer?  
**Answer:** Some browsers omit the headers, non-browser clients can spoof headers; `same-site` does not mean `same-origin`, and client-side CSRF can originate from the app's own origin.

## 17. References

- [Spring Security 6.5 – CSRF Protection (Servlet)](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html) – `CsrfFilter`, `HttpSessionCsrfTokenRepository`, masked/deferred tokens, and SPA integration.
- [Spring Security – CSRF Protection for WebFlux](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html) – `WebSessionServerCsrfTokenRepository` and reactive CSRF.
- [Spring Boot 3.5 – SameSite Cookies](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html#web.servlet.embedded-container.customizing.samesite) – `server.servlet.session.cookie.same-site`.
- [Spring Boot 3.5 – Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/) – Servlet/Reactive session cookie settings.
- [OWASP – Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html) – SameSite limitations, tokens, Origin, and Fetch Metadata.
- [MDN – Set-Cookie header](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie) – Strict/Lax/None, default-Lax exception, and cookie flags.
- [MDN – Cross-site request forgery (CSRF)](https://developer.mozilla.org/en-US/docs/Web/Security/Attacks/CSRF) – same-site vs. same-origin and defense options.
- [OWASP – Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html) – protecting session IDs, cookie scope, and session fixation.
