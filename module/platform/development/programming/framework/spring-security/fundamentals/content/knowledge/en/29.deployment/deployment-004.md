# Configuring Cookies by Domain, Path, and Browser Policies

> **Scope:** deploying **Java 17+, Spring Boot 3.x, Spring Security 6.x, Servlet/Spring MVC** applications that use browser login sessions. This lesson explains how browsers accept, store, and send cookies according to `Domain`, `Path`, `Secure`, `HttpOnly`, `SameSite`, expiration, and third-party policies; then configures secure session cookies in Spring Boot, tests them with MockMvc, and verifies real behavior via browsers/HTTPS. **Cookies are not an authorization mechanism**: beyond cookies you still need authentication, authorization, CSRF, session control, and proper proxy configuration.

## 1. Starting from a deployment scenario

Suppose a company operates three services:

- `https://app.example.com`: web UI with user login.
- `https://api.example.com`: API serving the web app.
- `https://admin.example.com`: admin UI requiring strict protection.

The Java application creates a session after a user logs in. The browser holds a cookie containing a **random session identifier**, e.g., named `__Host-SESSION`. The questions to decide are not merely "do we have a cookie yet?", but include:

1. Should the cookie be sent only to the **host that created it** or to all of `*.example.com`?
2. Should the cookie be sent when the URL is at `/app`, `/admin`, or `/api`?
3. Is it sent only over HTTPS or could it be sent over HTTP?
4. Can JavaScript read the cookie?
5. When a user arrives from another site or a frontend calls a different-origin API, is the cookie attached?
6. When the session expires, the user logs out, a browser blocks third-party cookies, or a reverse proxy changes scheme, what happens?

An imprecise cookie configuration can bounce users back to the login page, stop the browser from sending the session, broaden cookies to untrusted subdomains, or send forged requests with sessions attached in dangerous situations.

**Goal:** learn to read `Set-Cookie`, distinguish host-only vs. domain cookies, pick `Path`/`SameSite` for the right purpose, configure Spring Boot's `server.servlet.session.cookie.*`, predict browser behavior, and verify with tests rather than checking HTTP status alone.

## 2. How do cookies actually work?

The application returns an HTTP response with a header:

```http
HTTP/1.1 200 OK
Set-Cookie: __Host-SESSION=opaque-random-id; Path=/; Secure; HttpOnly; SameSite=Lax
```

The browser decides **whether to accept** this cookie and, if accepted, stores it with its scope metadata. On a matching subsequent request, the browser sends:

```http
GET /profile HTTP/1.1
Host: app.example.com
Cookie: __Host-SESSION=opaque-random-id
```

**Mandatory distinction:** the request `Cookie` header carries only **name and value**, never the `Secure`, `HttpOnly`, `SameSite`, `Path`, or `Domain` attributes. Those attributes are enforced by the browser when storing and deciding whether to send the cookie. Therefore, **the server cannot inspect an incoming `Cookie` header to prove the browser received the cookie over HTTPS or which attributes were applied**; you must configure responses properly and verify via browsers/HTTPS.

The session ID in the cookie is typically just a **lookup key** into a server-side session or session store; it is not itself the full profile/permissions. When the server deletes/invalidates a session or it expires, the browser may still hold a cookie, but that identifier can no longer authenticate.

### Two commonly confused headers

| Header | Data direction | Contents |
| --- | --- | --- |
| `Set-Cookie` | Server → browser | Creates/updates/expires a cookie; includes `Domain`, `Path`, `Secure`, `SameSite`, etc. |
| `Cookie` | Browser → server | Matching `name=value` pairs sent by the browser to the server |
| `Authorization` | Client → server | Credentials such as Bearer/Basic (not a session cookie, though they can coexist) |

Never place an entire user object or password in a session cookie. Never log full `Cookie`, `Set-Cookie`, or session IDs; they can hold session-hijacking values.

## 3. Domain: host-only vs. subdomain-shared cookies

### 3.1. Omitting Domain → host-only (recommended default)

If a response from `https://app.example.com` sets:

```http
Set-Cookie: SESSION=abc; Path=/; Secure; HttpOnly; SameSite=Lax
```

with **no `Domain`**, it is a **host-only cookie**. The browser sends it back to `app.example.com` but **does not send** it to `api.example.com` or `admin.example.com` merely because those hosts share `example.com`.

When users only log into a single web app, host-only reduces the attack surface and prevents accidentally sending cookies to other subdomains. In Spring Boot, **omit** `server.servlet.session.cookie.domain` if you want the cookie bound strictly to the host serving the response.

### 3.2. Setting Domain=example.com → scope can broaden to subdomains

If `app.example.com` sets:

```http
Set-Cookie: SESSION=abc; Domain=example.com; Path=/; Secure; HttpOnly; SameSite=Lax
```

the browser may send the cookie to `example.com` and its subdomains, such as `app.example.com`, `api.example.com`, and `admin.example.com`, when other conditions also match.

That **does not mean applications automatically share login state**. API B must have a way to **understand the same session ID and share the session store/session policy** or an explicitly designed federated auth mechanism. Simply making a cookie arrive at B does not make B recognize A's user; instead, it increases the number of services receiving a sensitive session identifier.

**Risk:** a compromised subdomain or weak sibling app can enable domain-cookie attacks such as cookie tossing, session fixation, or cookie overwriting under certain conditions. Never widen cookie scope just "for convenience"; for cross-app login, consider OIDC/SSO with separate per-host sessions.

### 3.3. Domain constraints

- A server may only set `Domain` matching the current host or an allowed parent domain; `app.example.com` cannot arbitrarily set a cookie for `other-company.test`.
- A public suffix like `com` cannot be used as a cookie domain. Browsers enforce the Public Suffix List and cookie policies.
- A leading dot in `Domain=.example.com` is ignored by modern processing; it grants no broader scope than `Domain=example.com`.
- **Cookies are not isolated by port.** For example, two apps on different ports of the **same host** can receive the same cookie if domain/path/scheme match, even though they are **two distinct origins** under CORS rules.
- Multiple cookies with the same name can exist across different `Domain`/`Path` scopes. When multiple same-named cookies are sent, order is not a reliable basis for the server to pick the "right" cookie. Avoid name/scope collisions and design clear migrations.

**Remember:** `Domain` scope is a **cookie delivery** decision, not an authorization rule or a guarantee of full isolation between apps on the same site.

## 4. Path: restricts where cookies are sent, not a security boundary

A cookie with `Path=/app` matches request paths `/app`, `/app/`, and `/app/profile`, but does not match `/admin` or `/application` under browser path-matching rules.

| Cookie Path | Request URL path | Can the browser send the cookie? |
| --- | --- | --- |
| `/` | `/profile` | Yes, if domain, scheme, and SameSite also match |
| `/app` | `/app` | Yes |
| `/app` | `/app/account` | Yes |
| `/app` | `/application` | No |
| `/app` | `/admin` | No |
| `/admin` | `/app/profile` | No |

A Spring MVC app deployed at `/portal` may need a session cookie with `Path=/portal` so the browser sends it only on requests in that context. However, if an SPA runs at `/` and the backend session is needed at `/api`, setting `Path=/portal` leaves `/api` requests **without the session cookie**, causing unexpected 401s or redirects.

**Important:** `Path` **is not a confidentiality boundary between apps sharing a host**. JavaScript, URL forwarding, page structure, or another privileged app on the host still have interaction paths; `Path` does not replace authorization, origin isolation, or separate-host segmentation.

### Path and logout must match

To delete a cookie, you typically return a new `Set-Cookie` with the **same name, Domain, and Path** as the original cookie plus `Max-Age=0` (or an `Expires` in the past). If the real cookie was set with `Path=/portal` and your code deletes it at `Path=/`, the browser may keep the old cookie. Likewise, changing `Domain` config can leave a same-named cookie alive in the old scope.

However, **deleting the browser cookie does not replace server-side session invalidation**. Spring Security logout must invalidate the session and clear the security context per configuration; long-lived/refresh tokens have their own lifecycles and may require revocation.

## 5. Secure, HttpOnly, and protective cookie name prefixes

### 5.1. Secure

`Secure` requires the browser to send the cookie over a secure channel, normally **HTTPS**. For cookies carrying a session ID, enable `Secure` in production alongside properly configured TLS/HSTS.

**Do not misunderstand:** `Secure` does not encrypt the cookie value in application logs, does not prevent XSS, and does not turn an HTTP server into HTTPS. Some browsers make exceptions for `localhost`, but **never rely on that exception as a production deployment standard**.

When an app runs behind a TLS-terminating reverse proxy, the proxy-to-Java hop may be HTTP on an internal network. You should still issue session cookies with `Secure` if the user-facing URL is HTTPS. Set the attribute explicitly and verify redirects/forwarded headers in deployment.

### 5.2. HttpOnly

`HttpOnly` prevents scripts on the page from reading the cookie via `document.cookie` or equivalent cookie-reading APIs. This mitigates stealing the session ID through JavaScript.

However, `HttpOnly` **does not** stop the browser from automatically attaching the cookie to valid requests, including requests initiated by JavaScript `fetch()`/XHR when browser rules allow. Therefore, XSS can still trigger actions under the user's session; you still need output encoding, CSP, CSRF/authorization, and other controls.

Do not disable `HttpOnly` on the **session cookie** just so the frontend can read the username. The frontend should call an API like `/api/me` to fetch needed fields. If an SPA uses a **separate CSRF cookie** that JavaScript must read, setting `HttpOnly=false` may be justified **for that CSRF cookie**, never for the session cookie.

### 5.3. __Secure- and __Host-

Modern browsers support **cookie name prefixes** carrying extra constraints:

| Prefix | Browser validation requirements | When to consider |
| --- | --- | --- |
| `__Secure-` | Set from a secure origin and includes `Secure` | Cookie needs `Secure` but may have `Domain`/`Path` per contract |
| `__Host-` | Secure origin, `Secure`, `Path=/`, **no Domain** | Session cookie belonging strictly to the current host, host-wide |
| No prefix | No extra prefix checks | Local/test environments or cookies ineligible for prefixes |

Example for **HTTPS production**:

```http
Set-Cookie: __Host-SESSION=opaque-id; Path=/; Secure; HttpOnly; SameSite=Lax
```

If you add `Domain=example.com` or change `Path=/portal`, a `__Host-`-prefixed cookie **becomes invalid** under prefix rules and may be rejected by the browser. The prefix name does not replace the attributes: the app must still emit `Secure`, `Path=/`, and omit `Domain`.

**Design lesson:** if you are required to share a cookie across subdomains or restrict its path, **you cannot use `__Host-` at the same time**. Consider another name such as `__Secure-SESSION` with `Secure`, `HttpOnly`, and the narrowest possible scope after a risk assessment.

## 6. SameSite: cookie sending policy by "site", not origin

`SameSite` reduces cookie attachment on certain requests originating from other websites, particularly regarding CSRF. Under modern browsers' **schemeful same-site** definition, a site considers **scheme** (`https`/`http`) and registrable domain; an origin additionally considers host and port.

Examples:

| Two URLs | Site relationship | Origin relationship |
| --- | --- | --- |
| `https://app.example.com` and `https://api.example.com` | Usually **same-site** | **Cross-origin** because hosts differ |
| `https://app.example.com` and `https://app.example.com:8443` | **Same-site** | **Cross-origin** because ports differ |
| `http://app.example.com` and `https://app.example.com` | **Cross-site** under schemeful site | **Cross-origin** because schemes differ |
| `https://app.example.com` and `https://other.example.net` | **Cross-site** | **Cross-origin** |

This is an extremely common point of confusion: a frontend at `app.example.com` calling an API at `api.example.com` can be **cross-origin yet same-site**. `SameSite=Lax` is not necessarily why a cookie is blocked; the cookie might be **host-only** on `app`, the frontend might have omitted `credentials: "include"`, CORS might be misconfigured, or the browser might have rejected the cookie due to `Secure`/`Domain`/`Path`.

### 6.1. Values

| SameSite | General behavior | Use case |
| --- | --- | --- |
| `Strict` | Cookie sent only in same-site context; navigations from external sites may omit the cookie | Pages needing maximum cross-site restriction, though it can disrupt links from emails/external sites |
| `Lax` | Sent in same-site; in cross-site may be sent on top-level navigations using safe methods like GET | Suitable for most web apps with standard login and navigation |
| `None` | Allows sending cookie in cross-site contexts **if the browser permits**; requires `Secure` | Certain iframes, embedded/identity integrations, or purpose-built cross-site flows |

If `SameSite` is omitted, many browsers default to behavior close to `Lax`, **but you should not rely on per-browser/version defaults**; certain flows behave differently when the attribute is absent. Explicitly set `Strict`, `Lax`, or `None` according to your flow.

**`SameSite=None; Secure` does not guarantee third-party cookies work:** browsers may block third-party cookies, users may disable tracking, iframes face sandbox/storage-access restrictions, or partitioning (CHIPS) may apply. Do not treat `None` as a "bypass switch" for browser privacy policies.

### 6.2. SameSite does not replace CSRF protection

Even with `SameSite=Strict/Lax`, you must still account for:

- Cross-site top-level navigations with safe methods under `Lax`.
- Same-site but **different origin/subdomain** environments: a compromised subdomain can issue same-site requests.
- Older or specialized browsers, or cookies sent when users arrive via permitted flows.
- Endpoints not using session cookies but carrying other credentials (Bearer, HTTP Basic, mTLS) and their respective request-forgery risks.

With Spring Security form login/sessions, **never disable CSRF just because `SameSite=Lax` is set**. `CsrfFilter` and CSRF tokens in forms/headers remain a dedicated defense for state-changing requests alongside XSS mitigation and request/resource authorization.

## 7. CORS, fetch credentials, and browser policies

### 7.1. Same-site does not mean same-origin

Frontend at `https://app.example.com`:

```javascript
const response = await fetch("https://api.example.com/api/me", {
  method: "GET",
  credentials: "include"
});
```

`credentials: "include"` tells the browser to send/receive credentials per cookie rules. However, for JavaScript to **read the response** from a credentialed cross-origin API call, the server must allow a specific origin and credentials:

```http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
```

For credentialed CORS requests, the server **cannot** return `Access-Control-Allow-Origin: *` and expect the browser to let JavaScript read the response. Preflight requests must be handled when triggered. Configure CORS on a trusted server/gateway and allow explicit origins rather than reflecting every `Origin` blindly.

**Two separate decisions:** (1) does the browser send the cookie per `Domain`/`Path`/`Secure`/`SameSite` and `credentials`? (2) is JavaScript allowed to **read the response** per CORS? An API returning 200 in the network tab while JS hits a CORS error is a very different symptom from 401 caused by the browser not sending the session cookie.

CORS **is not** a comprehensive anti-CSRF mechanism. A form POST from another website follows different CORS rules than `fetch` and can still cause side effects if CSRF/authorization are missing.

### 7.2. Third-party cookies and Partitioned

For a widget embedded in an iframe on another site, a `SameSite=None; Secure` cookie may still be restricted by the browser. **CHIPS** uses the `Partitioned` attribute to store cookies in a partition keyed by top-level site in supporting browsers:

```http
Set-Cookie: __Host-EMBED=opaque; Path=/; Secure; HttpOnly; SameSite=None; Partitioned
```

A partitioned cookie **is not an Internet-wide shared session**, nor a way to bypass privacy policies. Verify browser support and actual requirements. Spring Boot 3.5 provides `server.servlet.session.cookie.partitioned` for session cookies, though final behavior depends on the servlet container, browser, and version. Never enable it indiscriminately for all sessions: a user can end up with separate cookie partitions per top-level site.

## 8. Configuring session cookies in Spring Boot 3

### 8.1. Recommended configuration for a dedicated host under HTTPS

Suppose the application is published solely at `https://app.example.com`. Create **`src/main/resources/application.properties`**:

```properties
spring.application.name=cookie-policy-demo

# Host-only session cookie, sent only over HTTPS.
server.servlet.session.cookie.name=__Host-SESSION
server.servlet.session.cookie.path=/
server.servlet.session.cookie.secure=true
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.same-site=lax

# Do not set server.servlet.session.cookie.domain:
#   let the browser restrict the cookie to the host returning the response.

# Server-side HttpSession inactivity timeout.
server.servlet.session.timeout=20m

# Use cookies for session tracking, never URL rewriting.
server.servlet.session.tracking-modes=cookie
```

**Explanation of each property:**

| Property | Example value | Meaning |
| --- | --- | --- |
| `server.servlet.session.cookie.name` | `__Host-SESSION` | Cookie name carrying the session ID; prefix requires `Secure` + `Path=/` + no `Domain` |
| `...path` | `/` | Cookie sent for all URL paths on the current host; fits `__Host-` prefix |
| `...secure` | `true` | Requires browser to send only over a secure channel |
| `...http-only` | `true` | Prevents JavaScript from reading the session cookie via `document.cookie` |
| `...same-site` | `lax` | Reduces cookie attachment on many cross-site requests while supporting top-level GET links |
| `...domain` | **omitted** | Creates a host-only cookie, not shared with sibling subdomains |
| `server.servlet.session.timeout` | `20m` | Inactivity timeout of the **server-side session**, not browser cookie lifetime |
| `...tracking-modes` | `cookie` | Avoids URL-based session tracking where supported by configuration |

**Note on `max-age`:** `server.servlet.session.cookie.max-age` controls browser-side cookie lifetime (if configured), which is **different** from `server.servlet.session.timeout`. You do not need persistent session cookies just to keep users logged in longer. A surviving cookie does not mean the `HttpSession` is still valid; conversely, a "session cookie" without `Max-Age` can still be restored by browser session-restore features depending on browser policy.

**Do not copy this configuration verbatim to a plain local HTTP environment:** browsers cannot use `__Host-SESSION; Secure` over normal HTTP. For real browser testing, prefer local HTTPS or a **development-only** local profile as shown below.

### 8.2. Localhost lab profile — never deploy

Create **`src/main/resources/application-local.properties`**:

```properties
# ONLY for HTTP localhost/dev. NEVER deploy to production.
server.servlet.session.cookie.name=DEMOSESSION_LOCAL
server.servlet.session.cookie.secure=false
server.servlet.session.cookie.path=/
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.same-site=lax
```

Run with Gradle Wrapper:

```bash
./gradlew bootRun --args='--spring.profiles.active=local'
```

On Windows PowerShell:

```powershell
.\gradlew.bat bootRun --args="--spring.profiles.active=local"
```

The `local` profile renames the cookie so it **does not use `__Host-` when `Secure` is disabled**. Running on HTTP `localhost:8080` lets you try form login in a browser to understand sessions, but HTTP results cannot serve as proof that production cookies are secure. Production HTTPS cookies must be verified separately with TLS, ingress, and the real host.

### 8.3. Sharing cookies across subdomains when genuinely required

If an **approved design** requires issuing a domain cookie:

```properties
# Illustrative only; DO NOT combine with the __Host-SESSION name.
server.servlet.session.cookie.name=__Secure-SESSION
server.servlet.session.cookie.domain=example.com
server.servlet.session.cookie.path=/
server.servlet.session.cookie.secure=true
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.same-site=lax
```

You must use a name that does not require host-only scope, such as `__Secure-SESSION` instead of `__Host-SESSION`. Evaluate all subdomains, session stores, cookie conflicts, logout, and migrations. **Setting `Domain=example.com` does not automatically log users into every service**. Sharing a session across subdomains expands session ID exposure if any subdomain is weaker; OIDC/SSO with separate per-app sessions generally provides cleaner boundaries.

### 8.4. Cross-site configuration for special flows

In a flow that genuinely needs cookies sent cross-site:

```properties
server.servlet.session.cookie.same-site=none
server.servlet.session.cookie.secure=true
```

`SameSite=None` requires `Secure` in modern browsers. You must still determine third-party policies, iframe constraints, CSRF, CORS, Storage Access API/CHIPS (if applicable), and test in real browsers. **Do not choose `None` merely because frontend and backend sit on two sibling subdomains**: those two hosts may be cross-origin while remaining same-site.

## 9. Runnable Java 17+ example: form login and cookie scope

### 9.1. Dependencies

Create a Spring Boot 3.x, Java 17+ project with Spring Initializr or your build tool. Inside `build.gradle` with the Spring Boot plugin and repositories already declared, the `dependencies` block is:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

This is only the **dependencies block**, not a full Gradle script. The example requires Spring MVC, Security, JUnit Jupiter, and MockMvc; no database is needed.

### 9.2. Full application code

Create **`src/main/java/demo/DemoApplication.java`**:

```java
package demo;

import java.time.Duration;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseCookie;
import org.springframework.http.ResponseEntity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}

@Configuration
class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password(encoder.encode("alice-pass"))
                        .roles("USER")
                        .build()
        );
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public", "/cookie-demo")
                                .permitAll()
                        .anyRequest().authenticated())
                .formLogin(form -> form
                        .defaultSuccessUrl("/profile", true)
                        .permitAll())
                .logout(logout -> logout
                        .logoutSuccessUrl("/public")
                        .permitAll())
                .build();
    }
}

@RestController
class DemoController {

    @GetMapping("/public")
    String publicPage() {
        return "public";
    }

    @GetMapping("/profile")
    String profile(Authentication authentication) {
        return "hello " + authentication.getName();
    }

    @GetMapping("/cookie-demo")
    ResponseEntity<String> demoCookie() {
        // Illustrative cookie, contains NO session ID/token/PII.
        ResponseCookie cookie =
                ResponseCookie.from("__Host-DEMO_PREF", "ok")
                        .path("/")
                        .secure(true)
                        .httpOnly(true)
                        .sameSite("Lax")
                        .maxAge(Duration.ofMinutes(10))
                        .build();

        return ResponseEntity.ok()
                .header(HttpHeaders.SET_COOKIE, cookie.toString())
                .body("cookie-preview");
    }
}
```

**Separation points to understand clearly:**

- `@SpringBootApplication` boots the Servlet app and scans `SecurityConfig` and `DemoController`.
- `formLogin(...)` and `UserDetailsService` create a real login flow: default login page, POST login processing username/password, and storing the authenticated `SecurityContext` in the session via framework mechanics.
- `server.servlet.session.cookie.*` in properties controls the **Servlet `HttpSession` cookie**, not a line in the controller.
- `ResponseCookie` in `demoCookie()` creates a **separate illustrative cookie** named `__Host-DEMO_PREF` with non-sensitive value `ok` to test `Set-Cookie` directly via MockMvc. **This cookie does not log users in and is unrelated to the `__Host-SESSION` session cookie**.
- `.logout(...)` configures the success URL; Spring Security handles logout, session invalidation, and clearing the security context per standard setup. With CSRF enabled, logout requires a POST with a CSRF token; do not build state-changing GET endpoints in demos.
- `Secure=true` on the demo cookie means browsers require a secure context to accept/send it per policy; MockMvc sees only server headers and **does not simulate a browser cookie jar**.
- There is no `csrf.disable()`. Even `permitAll` endpoints still need proper CSRF handling if they accept unsafe methods, because `permitAll` does not bypass all filters.

**Runnable details:** only `DemoApplication` is `public`, matching the file name; `SecurityConfig` and `DemoController` are top-level package-private classes in package `demo`. All imports and types are compatible with Java 17+/Spring Boot 3.x/Spring Security 6.x.

### 9.3. Testing with MockMvc

Create **`src/test/java/demo/CookiePolicyTest.java`**:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;
import org.springframework.http.HttpHeaders;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.hamcrest.Matchers.allOf;
import static org.hamcrest.Matchers.containsString;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.response
        .SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.security.test.web.servlet.response
        .SecurityMockMvcResultMatchers.unauthenticated;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CookiePolicyTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    Environment env;

    @Test
    void productionSessionCookiePolicyIsExplicit() {
        assertThat(env.getProperty(
                "server.servlet.session.cookie.name"))
                .isEqualTo("__Host-SESSION");
        assertThat(env.getProperty(
                "server.servlet.session.cookie.path"))
                .isEqualTo("/");
        assertThat(env.getProperty(
                "server.servlet.session.cookie.secure"))
                .isEqualTo("true");
        assertThat(env.getProperty(
                "server.servlet.session.cookie.http-only"))
                .isEqualTo("true");
        assertThat(env.getProperty(
                "server.servlet.session.cookie.same-site"))
                .isEqualToIgnoringCase("lax");
        assertThat(env.getProperty(
                "server.servlet.session.cookie.domain")).isNull();
    }

    @Test
    void explicitCookieResponseHasSecurityAttributes()
            throws Exception {
        mvc.perform(get("/cookie-demo"))
                .andExpect(status().isOk())
                .andExpect(content().string("cookie-preview"))
                .andExpect(header().string(
                        HttpHeaders.SET_COOKIE,
                        allOf(
                                containsString("__Host-DEMO_PREF=ok"),
                                containsString("Path=/"),
                                containsString("Secure"),
                                containsString("HttpOnly"),
                                containsString("SameSite=Lax"))));
    }

    @Test
    void anonymousUserIsSentToLoginPage() throws Exception {
        mvc.perform(get("/profile"))
                .andExpect(status().is3xxRedirection())
                .andExpect(header().string(
                        "Location", containsString("/login")));
    }

    @Test
    void successfulLoginProducesReusableSessionInMockMvc()
            throws Exception {

        MvcResult login = mvc.perform(formLogin()
                        .user("alice")
                        .password("alice-pass"))
                .andExpect(status().isFound())
                .andExpect(redirectedUrl("/profile"))
                .andExpect(authenticated().withUsername("alice"))
                .andReturn();

        MockHttpSession session = (MockHttpSession)
                login.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/profile").session(session))
                .andExpect(status().isOk())
                .andExpect(content().string("hello alice"));
    }

    @Test
    void wrongPasswordDoesNotCreateAuthenticatedLogin()
            throws Exception {
        mvc.perform(formLogin()
                        .user("alice")
                        .password("wrong-password"))
                .andExpect(status().isFound())
                .andExpect(redirectedUrl("/login?error"))
                .andExpect(unauthenticated());
    }

    @Test
    void postLogoutWithoutCsrfIsRejected()
            throws Exception {

        MvcResult login = mvc.perform(formLogin()
                        .user("alice")
                        .password("alice-pass"))
                .andReturn();

        MockHttpSession session = (MockHttpSession)
                login.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(post("/logout").session(session))
                .andExpect(status().isForbidden());
    }
}
```

**Classifying evidence from the tests:**

- `productionSessionCookiePolicyIsExplicit` verifies the **loaded configuration file** under the default profile; it does not prove the browser received the cookie. Do not run this test under the `local` profile because the cookie values intentionally differ; write separate test classes/profiles if the app has multiple environments.
- `explicitCookieResponseHasSecurityAttributes` verifies the `Set-Cookie` header of the **demo cookie created in the controller with `ResponseCookie`**. It does not test the session `Set-Cookie` emitted by Tomcat/Jetty/Undertow.
- `successfulLoginProducesReusableSessionInMockMvc` proves session authentication exists in the test flow and is reused on a second request; **MockMvc does not fully simulate how browsers store/reject session cookies by `Secure`/`Domain`/`Path`/`SameSite`**.
- `postLogoutWithoutCsrfIsRejected` proves state-changing requests require CSRF in this setup; it cannot be properly "fixed" by disabling CSRF because `SameSite=Lax` is enabled.

Run the tests:

```bash
./gradlew test
./gradlew test --tests demo.CookiePolicyTest
```

On Windows:

```powershell
.\gradlew.bat test --tests demo.CookiePolicyTest
```

**Do not claim a fixed stdout string:** when tests pass, Gradle/JUnit reports according to version and configuration. In real projects, add tests using an embedded server or browser automation to observe actual session `Set-Cookie` headers and browser policy behavior, not just MockMvc tests.

## 10. Verifying with DevTools and real HTTPS

### Step 1 — Identify the real URL and transport layer

Verify whether the browser opens `https://app.example.com` or `http://localhost:8080`, and whether the backend sits behind a TLS-terminating proxy. Remember that **cookie `Secure` checks the browser's URL/connection**, while the app may see HTTP between the proxy and Java.

Do not assume the app is running over HTTPS just because a load balancer has TLS; check the browser address bar, redirects, reverse proxy, and response headers.

### Step 2 — Inspect the Set-Cookie response

In DevTools → Network, select the login response or session-creating response and inspect `Set-Cookie`. Check the attributes:

```http
Set-Cookie: __Host-SESSION=<session-id>; Path=/; Secure; HttpOnly; SameSite=Lax
```

The line above is the **expected format**, not a real session value. Never copy raw session IDs into tickets, screenshots, Slack, logs, or bug reports. Browsers may flag a blocked cookie with reasons such as wrong `Domain`, missing `Secure` with `SameSite=None`, prefix violation, third-party policy, or scheme mismatch.

### Step 3 — Inspect the cookie jar and request Cookie header

In DevTools → Application/Storage → Cookies, inspect host, path, `Secure`, `HttpOnly`, `SameSite`, expiration, and partition key if any. On the next request to `/profile`, check whether the browser **sends `Cookie`**. If `Set-Cookie` appears yet the next request omits the cookie, the issue is usually scope or browser policy; if the browser sends the cookie yet the server redirects back to login, investigate the session store, invalidation, timeout, and Spring Security analysis.

### Step 4 — Compare same host vs. sibling subdomain

With a host-only cookie issued by `app.example.com`, issue a request to `api.example.com` and confirm the app's cookie **is not sent**. If the system intentionally uses a domain cookie `example.com`, verify the browser sends it to both hosts when `SameSite`/`Secure`/`Path` match, and still verify whether both backends **accept the same session ID**.

**Never share a session secret just to work around CORS**. When a cross-origin client calls an API, check each requirement: cookie scope, `credentials: "include"`, valid CORS headers, and Spring Security authorization. Every investigation needs evidence from Network traces and redacted server logs.

### Step 5 — Verify logout and rotation behavior

Log in, note the cookie name/scope **without recording the session ID value**; log out via a valid POST with CSRF and inspect both browser and server session state. Try hitting the private endpoint again; if the session is invalidated, re-authentication must be required. Spring Security's session fixation protection/rotation on login should also be tested in real systems if session management is customized.

If you recently changed `Domain` or `Path`, "legacy" cookies with the same name may still linger in the old scope. Have a plan to delete them using their exact name/domain/path and ensure the session store no longer accepts revoked sessions.

### Step 6 — Test across different browser policies

Test Chrome, Edge, Firefox, and Safari—including private/strict privacy modes where relevant. Third-party cookies and iframe storage vary widely. Passing in one server test or one browser does not guarantee every browser works. For iframes, you may need to redesign the auth flow rather than endlessly loosening `SameSite`.

### Step 7 — CLI tools

With real HTTPS and a live endpoint:

```bash
# Never use -k in production; inspect Set-Cookie only.
curl -i https://app.example.com/login

# Only illustrates cookie jar storage; the jar file may CONTAIN SECRETS.
# Restrict file permissions and delete after testing.
curl -c cookie-jar.txt -b cookie-jar.txt \
  https://app.example.com/profile
```

`curl` helps inspect HTTP headers and save a cookie jar for testing, **but it does not simulate browser `SameSite`/CORS/third-party policies** like Chrome or Safari. Never store production session cookie jars in shared directories or Git; for sensitive apps, prefer browser DevTools and dedicated test accounts.

## 11. Behind reverse proxies, ingress, and multiple instances

### 11.1. TLS termination

Common model:

```text
Browser --HTTPS--> Reverse Proxy / Load Balancer
                   |
                   +--HTTP (private network)--> Spring Boot
```

The app must emit cookies with `Secure` because the browser sends and receives them over HTTPS. In this guide's `application.properties`, setting `server.servlet.session.cookie.secure=true` avoids accidentally depending on the scheme seen by the Servlet request.

Also check login redirects, absolute URLs, issuer/callbacks, and cookie paths. If the app emits an incorrect `Location: http://...` while the browser uses HTTPS, proxy forwarded headers or app scheme detection is misconfigured. You may need `server.forward-headers-strategy=framework` or `native` depending on infrastructure, **only when the trusted gateway strips/replaces external client-supplied `Forwarded`/`X-Forwarded-*` headers**. Blindly trusting forwarded headers from the Internet enables Host/scheme spoofing and open redirects.

### 11.2. Multiple instances and session stores

When scaling out to multiple Spring Boot instances, the cookie arrives at the right host, but another instance may **not know the session ID** if session state lives only in the old instance's memory. You need thoughtfully configured sticky sessions or a shared session store (such as Spring Session + Redis/JDBC depending on design) with consistent lifecycles and key rotation.

**Keep distinct:** setting `Domain=example.com` does not solve separate session stores; sharing a session store also does not replace transport security or per-app authorization.

### 11.3. Changing context paths

When moving from `/` to `/portal`, cookie `Path` may need adjustment if you want to scope cookie transmission; however, using `__Host-` mandates `Path=/`. Never try to set `__Host-SESSION` and `Path=/portal` together. If a narrow path matters more than the prefix, choose another valid cookie name and assess risks across co-hosted apps.

## 12. Diagnosing common cookie errors

| Symptom | Causes to inspect | How to verify |
| --- | --- | --- |
| Redirected back to login right after logging in | Cookie rejected or not sent by browser, lost session store, invalid session | Network response `Set-Cookie`, request `Cookie`, server session |
| Cookie rejected immediately upon receipt | `SameSite=None` missing `Secure`; bad `__Host-` prefix; invalid `Domain` | DevTools Issues/Cookies rejection reason |
| Production HTTPS yet cookie lacks `Secure` | Wrong default config or proxy scheme | Check `Set-Cookie` in browser; set `Secure` explicitly |
| `/app` sends cookie, `/api` does not | `Path=/app` restricts scope | Compare URL path with cookie `Path` |
| `app.example.com` has session, `api.example.com` sees no cookie | Host-only cookie; browser does not send to sibling subdomain | Check `Domain` in DevTools, request headers |
| API receives cookie yet frontend gets CORS error | ACAO mismatch, missing ACAC, wrong fetch credentials | Network CORS headers + console; do not blame `SameSite` |
| Valid CORS yet API returns 401 | Cookie not sent, session expired, or cookie belongs to another host | Inspect request `Cookie` and server authentication |
| Iframe widget loses login | Third-party cookie policy, `SameSite`/partition/storage restriction | Browser-specific DevTools, real iframe test |
| Changed Domain/Path yet logout leaves user logged in | Old cookie in previous scope not deleted, session not invalidated | Check duplicate names in cookie jar and session store |
| Cookie with `__Host-` + `Domain=example.com` is not saved | Prefix requires **no Domain** | Remove `Domain` or change cookie type/prefix |
| Cookie sent to multiple ports on the same host | Cookies are not isolated by port | Compare origins vs. cookie scope; split hosts if isolation needed |
| `Set-Cookie` invisible in `fetch().headers` | `Set-Cookie` is a Fetch forbidden response-header name | Inspect DevTools Network instead of reading via JavaScript |
| MockMvc tests pass yet browser fails | MockMvc does not fully simulate browser cookie jars/policies | Browser E2E or embedded server + TLS |
| CSRF 403 on POST despite valid session | Having a cookie does not mean a valid CSRF token is present | Inspect CSRF token flow; never disable CSRF casually |
| Server returns 401 even though request sends cookie | Invalid/expired session ID or missing security context | Check session store, logout, cookie name, app profile |

Never log real session cookie values while investigating; logging request correlation IDs, endpoint categories, HTTP statuses, and approved event codes is safer.

## 13. Design mistakes to avoid

1. **Setting `Domain=example.com` on every cookie by default.** This unnecessarily widens scope; a weak sibling subdomain increases session-hijacking risk. Prefer host-only.
2. **Treating `Path=/admin` as an authorization barrier.** `Path` only affects which cookies the browser sends; admin URLs still require `hasRole` and server-side checks.
3. **Choosing `SameSite=None` just because the API sits on another subdomain.** Two HTTPS subdomains are typically still same-site; check `Domain`, fetch credentials, and CORS before changing `SameSite`.
4. **Using `__Host-SESSION` with `Domain` or non-root `Path`.** Browsers can reject it; obey `Secure` + `Path=/` + no `Domain`.
5. **Dropping `HttpOnly` so an SPA can read the session ID.** Build a proper profile/CSRF API flow; never expose session cookies to JS.
6. **Disabling CSRF because `SameSite=Lax` is enabled.** Browsers have multiple same-site and cross-site flows; `SameSite` is defense in depth, not a replacement for CSRF tokens.
7. **Treating CORS as protection against all cross-site requests.** CORS primarily governs whether JavaScript can read responses; other requests can still trigger side effects if the server does not enforce checks.
8. **Enabling `Secure=true` on plain HTTP dev while keeping the `__Host-` prefix and concluding the app is broken.** Use local HTTPS or a separate cookie name in the `local` profile, and never deploy weakened settings.
9. **Trusting client-supplied `X-Forwarded-Proto/Host`.** Configure trusted proxies and header sanitization.
10. **Keeping persistent cookies without managing session timeout/revocation.** Cookie lifetime and server session lifetime are distinct concepts.
11. **Trying to share logins via `Domain` without a common session store/protocol.** The browser may send the cookie, but the second server will not recognize the session.
12. **Skipping cleanup of legacy cookies after changing `Domain`/`Path`/name.** Duplicate cookies cause hard-to-debug session issues.
13. **Relying on a single MockMvc test for all browsers.** Verify HTTP responses from a real container and test cookie policies in real browsers.
14. **Logging verbatim `Set-Cookie`/`Cookie` headers.** Session IDs are credentials; tokens in logs or tickets can be hijacked.
15. **Letting GET endpoints perform important state changes.** `SameSite` and CSRF policies assume safe methods are safe; actions must use appropriate methods and CSRF protection.

## 14. Environment-by-environment cookie deployment checklist

### Quick decision table

| Architecture | Suggested scope | Suggested SameSite | Mandatory conditions |
| --- | --- | --- | --- |
| Single-host web over HTTPS | No `Domain`, appropriate `Path` (`/` preferred with `__Host-`) | `Lax` or `Strict` per UX | `Secure`, `HttpOnly`, CSRF, session expiry |
| Frontend and API on sibling subdomains (same site) | Prefer separate sessions and clear auth flow; domain cookies require review | Usually does not need `None` just for sibling subdomains | CORS/credentials if cross-origin, data authorization, HTTPS |
| Iframe/third-party integration | Minimal scope with dedicated assessment | May need `None; Secure` or auth flow redesign | Third-party policies, browser support, CSRF, tracing |
| Shared domain session | Approved and narrowest `Domain` | Per flow | Trusted subdomains, shared session store, logout/migration |
| Localhost HTTP lab | Dev cookie name without `Secure`/`Host` prefix when `Secure=false` | `Lax` | Never deploy the `local` profile |
| Reverse-proxy TLS termination | Browser-visible cookie over HTTPS, `Secure=true` | Per web flow | Trusted proxy, fixed redirects and scope |

### Final checklist

1. Identify the **exact host, scheme, port, and context path** observed by the browser.
2. Default to host-only; set `Domain` only when subdomain sharing is truly needed and risk-assessed.
3. Choose `Path` matching the app's real URLs; understand `Path` is not a security boundary.
4. Production session cookies have `Secure` + `HttpOnly`, with reasonable lifetime and server session timeout.
5. Set `SameSite` explicitly per flow; `None` requires `Secure` and remains subject to third-party blocking.
6. When using `__Host-`, verify **no Domain, Path=/, Secure, and HTTPS**.
7. Avoid arbitrary cookie name collisions across apps/hosts/paths; plan migrations.
8. CSRF, XSS, authorization, session fixation, and logout remain protected independently.
9. For cross-origin fetch, verify `credentials` and CORS responses for explicit origins.
10. Behind proxies, accept forwarded headers only from trusted networks, and verify redirect URLs and `Secure`.
11. Inspect real `Set-Cookie`/`Cookie` in Network and DevTools Application Storage without exposing session IDs.
12. Test login/logout/timeout/rotation in real browsers and across multiple scaled instances.
13. Account for browser differences, iframes, CHIPS/`Partitioned`, and third-party policies per use case.
14. Never log credentials; emit event codes and correlation IDs for support.

## 15. Self-study questions

1. `app.example.com` omits `Domain`—will `api.example.com` receive that cookie merely because both share `example.com`?
2. If you add `Domain=example.com`, do two backends automatically share `HttpSession`? What architectural condition is still missing?
3. Will a `Path=/app` cookie be sent to `/application`? Should you rely on `Path` to protect `/admin`?
4. How do `Secure` and `HttpOnly` address different risks? Do these two attributes eliminate XSS or CSRF?
5. Why does `SameSite=Lax` not mean "same-origin only"? What is the site/origin relationship between `app.example.com` and `api.example.com`?
6. What happens to a `SameSite=None` cookie missing `Secure` in modern browsers? After adding `Secure`, is a third-party iframe guaranteed to work?
7. In an HTTPS production app, why must `__Host-SESSION; Path=/; Secure` **omit `Domain`**?
8. If a cross-origin frontend uses `fetch` and forgets `credentials: "include"`, how might the bug manifest even when `SameSite` is valid?
9. If a server returns `Access-Control-Allow-Origin: *` with `Access-Control-Allow-Credentials: true`, will the browser let JavaScript read the credentialed response?
10. Why shouldn't a CSRF 403 after login be fixed with `csrf.disable()` just because the cookie has `SameSite=Lax`?
11. Why doesn't a MockMvc test prove a `Secure` cookie is stored and sent properly by browsers?
12. If you change `Path=/portal` to `Path=/`, does the old cookie vanish automatically? What must be done for the old cookie and server session?
13. Why does `server.servlet.session.timeout=20m` not mean `Max-Age=1200`?
14. With HTTPS at the load balancer and HTTP to Spring Boot, why must you still emit `Secure` and sanitize forwarded headers?
15. If a user logs into instance A and the next request hits instance B and loses login state, is the bug necessarily caused by `SameSite`?
16. If you want to share login across multiple apps without broadening cookie `Domain`, what pattern fits better?

**Hints:** (1) no, host-only; (2) shared auth/session store or SSO protocol needed; (3) no, `Path` is not authorization; (4) HTTPS delivery vs. JS read; (5) site checks scheme/registrable domain, origin checks host/port; (6) `None` requires `Secure`, and browsers still enforce privacy rules; (7) `__Host-` requirement; (8) browser omits credentials; (9) no; (10) `SameSite` is only defense in depth; (11) MockMvc lacks browser cookie policy; (12) delete with matching name/domain/path and invalidate session; (13) server timeout differs from cookie age; (14) browser uses HTTPS and proxy headers require trust; (15) check session store/sticky sessions; (16) OIDC/SSO with separate sessions.

## References

- [Spring Boot 3.5 — Common Application Properties: server.servlet.session.cookie.*](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html)
- [Spring Boot 3.5 — Servlet Web Applications, SameSite Cookies](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html)
- [MDN — Set-Cookie: Domain, Path, Secure, HttpOnly, SameSite, prefixes](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie)
- [MDN — Using HTTP cookies](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Cookies)
- [MDN — Secure cookie configuration](https://developer.mozilla.org/en-US/docs/Web/Security/Practical_implementation_guides/Cookies)
- [MDN — Partitioned Cookies / CHIPS](https://developer.mozilla.org/en-US/docs/Web/Privacy/Guides/Third-party_cookies/Partitioned_cookies)
- [Spring Security 6.5 — CSRF Protection](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html)
- [Spring Security 6.5 — Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html)
- [Spring Security 6.5 — MockMvc Testing](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/index.html)