# Cookies and Expiration, Secure, HttpOnly, SameSite Configuration in Spring MVC

## 1. Objectives and Context

HTTP is fundamentally a **stateless** protocol: the server does not automatically remember users between two requests through HTTP alone. **Cookies** are a mechanism for the server to instruct the browser to store a name–value pair along with attributes, and the browser then decides when to send that pair in subsequent requests. A Spring MVC application may use cookies for a session identifier, UI preferences, locale, user consent tracking, or other state information.

This lesson focuses on **cookie lifecycle and scope**, specifically `Max-Age`/`Expires`, `Secure`, `HttpOnly`, `SameSite`, and how to configure, read, and delete them in the **Spring MVC Servlet stack**.

After completing this lesson, you will be able to:

1. Distinguish between the **response `Set-Cookie` header** and the **request `Cookie` header**, and between session cookies and persistent cookies.
2. Explain `Max-Age`, `Expires`, `Domain`, `Path`, `Secure`, `HttpOnly`, `SameSite=Strict/Lax/None`, and the limitations of each mechanism.
3. Use `ResponseCookie`, `ResponseEntity`, and `@CookieValue` to set, read, and delete cookies in a Spring MVC controller.
4. Configure attributes of the **session cookie** managed by the Servlet container / Spring Boot without confusing it with custom cookies.
5. Understand the relationship between cookies, HTTPS, CSRF, XSS, CORS, third-party cookie policies, session timeout, and testing with `MockMvc`.
6. Identify insecure configurations: `SameSite=None` without `Secure`, omitting `HttpOnly` on session IDs, overly broad `Domain`, or keeping sensitive cookies for too long.

The application examples target **Java 17+, Spring Framework 6.x, Spring Boot 3.x**. Browsers may enforce different cookie policies depending on version, privacy settings, and first-party/third-party context; the server sending `Set-Cookie` **does not guarantee** that the browser will definitely store or resend that cookie.

## 2. How Do Cookies Travel Over HTTP?

A response instructing the client to create a cookie:

~~~http
HTTP/1.1 204 No Content
Set-Cookie: view_pref=compact; Path=/api/prefs; Max-Age=604800; Secure; HttpOnly; SameSite=Lax
~~~

In subsequent requests, if browser conditions are met, the client sends:

~~~http
GET /api/prefs/current HTTP/1.1
Host: example.com
Cookie: view_pref=compact
~~~

Important details:

- `Set-Cookie` is a **response header** used to create, update, or expire a cookie. To send multiple cookies, the server normally sends **multiple separate `Set-Cookie` headers**, rather than arbitrarily combining them into one comma-separated header.
- `Cookie` is a **request header** carrying only name–value pairs, for example `Cookie: theme=dark; lang=vi`. It **does not send back** `Max-Age`, `Secure`, `HttpOnly`, `Path`, or `SameSite`.
- Cookies are not part of the JSON body. An endpoint can send a JSON body and `Set-Cookie` at the same time; it can also return HTTP 204 with no body while still setting a cookie via the header.
- `@CookieValue` reads cookies from the **current** request, not `Set-Cookie` being generated for the response. To read a newly set cookie, you need the client's next request, or pass the value through the server-side business flow directly.
- Cookies are managed by the client according to scope constraints, expiration, browser policies, and user settings. Seeing `Set-Cookie` in `curl -i` only proves the server sent it; **it does not prove a browser accepted it**.

### Distinguishing Cookies from Server-Side Sessions

The `JSESSIONID` cookie typically holds a **session identifier**, while the actual session data is stored on the server side (memory, Redis, or a session repository). The `JSESSIONID` cookie does not itself contain the entire `HttpSession` object. A session ID can expire on the server even while the browser still holds the cookie; conversely, a session cookie can disappear when the browser closes before the server's session timeout expires.

Do not put passwords, plaintext secrets, or full user objects into cookies just because cookies live in the browser. Users and the client environment have many ways to inspect/modify cookies; an `HttpOnly` cookie is not a server-side secret store.

## 3. Attributes in `Set-Cookie`

| Attribute | Purpose | Notes |
| --- | --- | --- |
| `name=value` | Cookie identifier and value | Do not trust as unmodified server data; validate upon receipt |
| `Max-Age=604800` | Lifetime in **seconds** from receipt; 604800 = 7 days | `Max-Age=0` expires the cookie immediately |
| `Expires=...` | Expiration timestamp in GMT date format | If `Max-Age` is also present, modern clients prioritize `Max-Age` |
| `Path=/api` | Restricts request paths for which the browser sends the cookie | Not a security boundary isolating paths |
| `Domain=example.com` | Allows the cookie to apply to the domain and matching subdomains | Omitting `Domain` is usually safer: host-only cookie |
| `Secure` | Send only over HTTPS connections (localhost exceptions vary by browser) | Does not encrypt the cookie stored on disk |
| `HttpOnly` | Prevents JavaScript `document.cookie` from reading/modifying the cookie | Does not stop the browser from sending the cookie in `fetch` or form requests |
| `SameSite=Strict` | Restricts the cookie to same-site requests | Stronger, but can affect flows opening links from external sites |
| `SameSite=Lax` | Allows same-site and some safe top-level cross-site navigations | Does not replace a CSRF token |
| `SameSite=None` | Allows the cookie in eligible cross-site contexts | **Requires `Secure`**; browsers may still block third-party cookies |
| `Partitioned` | Opts the cookie into partitioned storage in supporting browsers | Requires `Secure`; browser policies vary |

Not every browser retains a cookie for the full requested duration if the user clears cookies, the browser hits storage/count limits, private mode ends, or tracking protection intervenes. Expiration is **not an absolute storage guarantee**.

### What Is a Cookie Without `Domain`?

For example, the server `api.example.com` sends:

~~~http
Set-Cookie: pref=vi; Path=/; Secure; SameSite=Lax
~~~

Because **there is no `Domain`**, this is normally a **host-only cookie**: only the host `api.example.com` receives the cookie, and it does not automatically extend to `www.example.com`.

If `Domain=example.com` is added, the cookie can be sent to both `example.com` and matching subdomains. An overly broad domain increases the risk of a compromised or untrusted subdomain manipulating the cookie. You cannot arbitrarily set `Domain` to an unrelated domain or a public suffix like `com`.

`Path` controls whether the browser sends the cookie by URL path, but **does not isolate read access between applications on the same origin** as a standalone security control. Manage origins, domains, application permissions, and trust boundaries properly.

## 4. Configuring Expiration: Session Cookies, `Max-Age`, and `Expires`

### 4.1. Session Cookie

When neither `Expires` nor `Max-Age` is set, a cookie is typically treated as a **session cookie**, tied to the browser session lifecycle. Do not assume it always disappears immediately upon closing a tab: some browsers have session-restore modes that recover session cookies. A "session cookie" is also distinct from a "server-side session timeout."

### 4.2. Persistent Cookie

~~~http
Set-Cookie: theme=dark; Path=/; Max-Age=2592000; Secure; SameSite=Lax
~~~

`2592000` seconds equals 30 days (30 × 24 × 60 × 60). `Max-Age` is a relative count in seconds, not milliseconds. If the server writes `Max-Age=30` intending 30 days, the cookie will only live for about 30 seconds.

With `Expires`, the server specifies an expiration date/time; clock skew between client and server can occur. When both are present, `Max-Age` takes precedence under standard cookie semantics. Spring's `ResponseCookie` provides `maxAge(Duration.ofDays(...))` to avoid unit mistakes.

### 4.3. Deleting a Cookie

~~~http
Set-Cookie: theme=; Path=/; Max-Age=0; Secure; SameSite=Lax
~~~

`Max-Age=0` asks the browser to expire the cookie immediately. **The name, `Path`, and `Domain` scope must match the existing cookie.** If the original cookie was created with `Path=/api/prefs` and deleted with `Path=/`, the browser may keep the original cookie because it represents a different cookie identity.

To replace/remove a cookie consistently, maintain the same scope configuration between creation and deletion. A deletion cookie does not need to preserve the old value, though keeping security/scope attributes consistent helps clarity. If multiple cookies share the same name across different paths or domains, each must be addressed specifically.

### 4.4. Expiring a Cookie Does Not Equal Secure Logout

Deleting the cookie stops the browser from sending the session ID, but **reliable logout must also invalidate the server-side session/token** when sessions are used. For session IDs managed by Spring Security, use Spring Security's logout/session-management mechanisms rather than only sending `Set-Cookie: JSESSIONID=; Max-Age=0` and assuming access has been revoked.

An opaque session identifier still active on the server can be reused if leaked and not revoked, even if the user deletes the cookie from one browser.

## 5. `Secure`: Protecting Cookies in Transit

`Secure` instructs the browser to send the cookie only over `https:` (a common exception is `localhost` in development environments). This is a required attribute for session/authentication cookies in HTTPS deployments.

~~~http
Set-Cookie: session_ref=abc123; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

It prevents the browser from sending sensitive cookies over plain HTTP, but it **does not**:
- Fully protect against XSS if the application still suffers from script injection.
- Encrypt the cookie value when stored on the client's disk.
- Authorize access or prevent replay of a leaked token.
- Automatically turn an HTTP site into HTTPS, or fix reverse proxy configuration.

Use HTTPS across the entire application, prefer HSTS in production where appropriate, and secure traffic between reverse proxies and backends according to your architecture. If the app sits behind a TLS-terminating load balancer, configure proxying and trusted forwarding properly so the framework knows the original request was HTTPS; do not trust `X-Forwarded-Proto` headers from untrusted clients.

If you use `Secure=true` on `http://localhost:8080`, browser behavior may depend on localhost exceptions and the specific browser. The hands-on example below verifies that **the server emits the right attributes** via `curl -i`/MockMvc; to test automatic browser cookie submission, use HTTPS in an appropriate environment.

## 6. `HttpOnly`: Restricting JavaScript Access to Cookies

A cookie marked `HttpOnly` is normally hidden from `document.cookie` and cannot be modified by ordinary JavaScript in the page:

~~~http
Set-Cookie: session_ref=abc123; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

This reduces certain risks of **reading/stealing session cookies via XSS**, though it does not eliminate XSS. Malicious script running in the origin can still:
- Send `fetch` requests to the backend to which the browser attaches eligible `HttpOnly` cookies.
- Read any information that the UI/API allows scripts to access.
- Perform unauthorized actions within the user's session if the server lacks permission/CSRF controls.

For a **session ID**, `HttpOnly=true` is normally the desired default. For **UI preferences** that client JavaScript genuinely needs to read via `document.cookie`, you may consider a non-`HttpOnly` cookie (since it holds no secrets) or pass the value via permitted HTML/API and store it appropriately. Never disable `HttpOnly` on authentication cookies just so the frontend can "grab the token conveniently."

`HttpOnly` differs from CORS: CORS governs whether JavaScript on another webpage can read a response, not whether the browser sends cookies in general. Browser cookie and credential policies must be evaluated separately.

## 7. `SameSite`: Strict, Lax, None

`SameSite` restricts when the browser attaches a cookie to a request based on the request's **site** relative to the site initiating the request. A "site" is normally **scheme + registrable domain** (schemeful same-site), which is not synonymous with **origin** (scheme + host + port). For instance, `https://app.example.com` and `https://api.example.com` have different origins yet remain same-site; `http://example.com` and `https://example.com` are different sites under schemeful rules.

| Value | Same-site request | Cross-site top-level GET navigation | Typical cross-site fetch/form POST |
| --- | --- | --- | --- |
| `Strict` | Yes, if scope/other rules match | Usually not sent | Not sent |
| `Lax` | Yes | Usually sent for safe top-level navigations | Usually not sent |
| `None` | Allowed per scope | May be sent | May be sent if `Secure` and browser policies allow |

Explanation:

- **`Strict`**: suited to sensitive operations where UX can tolerate cookies not being attached to navigations coming from external websites. For example, a user opening a link sent from another site may need to take one subsequent same-site action before the session cookie is used.
- **`Lax`**: balances UX with partial CSRF mitigation; permits certain safe top-level navigations such as GET. Never assume all GET requests are harmless: APIs must ensure **GET causes no dangerous state changes**.
- **`None`**: imposes no SameSite restriction, used when cookies are needed in cross-site contexts (such as embedded widgets). Modern browsers **require `Secure`** alongside it; third-party cookie blocking/partitioning and privacy settings can still block the cookie.
- **Omitting the attribute**: many browsers apply a Lax-like default, but differences and exceptions exist (such as grace periods for newly created cookies and evolving browser policies). If your application has clear security requirements, **set `SameSite` explicitly**.

**Important:** `SameSite=Lax` does not replace **CSRF protection**. The server needs CSRF tokens or anti-forgery controls suited to the authentication mechanism; Spring Security provides CSRF protection when configured. Cross-site top-level GETs can still carry Lax cookies, so GET/HEAD must follow safe semantics.

### Cross-Origin `fetch` Is Not Always Cross-Site

A frontend at `https://app.example.com` calling `https://api.example.com` is **cross-origin**, because the hosts differ. Yet in many configurations, those two origins are still **same-site**. When a browser processes cookies:
- `SameSite` concerns **site**.
- `Domain`, `Path`, `Secure`, and expiry concern cookie scope.
- `fetch` `credentials` and CORS govern how requests send credentials and whether JavaScript can read the response.
- Third-party cookie blocking also depends on browser policy.

Therefore, do not switch a cookie to `SameSite=None` just because you see a "CORS error." First determine whether the two sites are truly cross-site and whether the blocker is credentials/CORS/cookie scope or CSRF.

## 8. Spring MVC API for Creating Cookies: `ResponseCookie` and `ResponseEntity`

In **Spring Framework 6.x**, `org.springframework.http.ResponseCookie` provides a builder to declare:
- `path(String)`, `domain(String)` when actually needed.
- `maxAge(Duration)` or `maxAge(long seconds)`.
- `secure(boolean)`, `httpOnly(boolean)`, `sameSite(String)`.

Example declaration:

~~~java
ResponseCookie cookie = ResponseCookie.from("view_pref", "compact")
        .path("/api/prefs")
        .maxAge(Duration.ofDays(7))
        .secure(true)
        .httpOnly(true)
        .sameSite("Lax")
        .build();

String headerValue = cookie.toString();
~~~

This is an **in-method illustrative snippet**: imports for `ResponseCookie` and `Duration` are required. `toString()` produces a **value** suitable for the `Set-Cookie` header, not a URL or JSON body.

To send the header, use:

~~~java
return ResponseEntity.noContent()
        .header(HttpHeaders.SET_COOKIE, cookie.toString())
        .build();
~~~

With a return type of `ResponseEntity<Void>`, the result is **HTTP 204 No Content** with `Set-Cookie` and **no body**. `ResponseEntity` is convenient when you need to control status and headers together.

To send multiple cookies, use **two `Set-Cookie` header values**, for example:

~~~java
return ResponseEntity.ok()
        .header(HttpHeaders.SET_COOKIE, first.toString())
        .header(HttpHeaders.SET_COOKIE, second.toString())
        .body("ok");
~~~

This is an illustrative snippet requiring two `ResponseCookie` instances `first` and `second`; the `header` API appends header values. Do not manually concatenate `first + "," + second` into one string because `Set-Cookie` syntax has special rules, especially when `Expires` is present.

### Reading a Cookie in a Controller with `@CookieValue`

~~~java
@GetMapping("/current")
public String current(
        @CookieValue(name = "view_pref", required = false) String pref) {
    return pref == null ? "missing" : pref;
}
~~~

This is an illustrative handler in a `@RestController`, requiring imports. `@CookieValue` looks up a cookie by name on the **request**:
- By default `required=true`; a missing required cookie can cause an HTTP 400 error.
- `required=false` allows the cookie to be absent, passing `null` to the `String` parameter.
- `defaultValue="..."` can provide a fallback and also implies the cookie is not required.
- You can bind `jakarta.servlet.http.Cookie` when you need the Servlet Cookie object, though **the request Cookie does not tell you with certainty** which `SameSite`/`HttpOnly` attributes the browser stored, because browsers do not send those attributes in the `Cookie` request header.

Cookie data is client-controlled. If a cookie holds a choice that only accepts `compact` or `comfortable`, **validate against an allowlist** on the server; never trust a cookie to determine roles, user IDs, or access rights.

## 9. Complete Java 17+ / Spring Boot 3.x Example

Create a project using Spring Initializr: Java 17+, Spring Boot 3.x, Maven, **Spring Web**, and **Spring Boot Starter Test**. The project package is `com.example.demo`. This lesson uses only a UI preference cookie and **does not create an authentication/session system**.

Structure:

~~~text
src/main/java/com/example/demo/DemoApplication.java
src/main/java/com/example/demo/PreferenceCookieController.java
src/test/java/com/example/demo/PreferenceCookieControllerTest.java
~~~

### 9.1. Bootstrap Class

**`src/main/java/com/example/demo/DemoApplication.java`**

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 9.2. Controller to Create, Read, and Delete Cookies

**`src/main/java/com/example/demo/PreferenceCookieController.java`**

~~~java
package com.example.demo;

import java.time.Duration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseCookie;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.CookieValue;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/prefs")
public class PreferenceCookieController {

    private static final String COOKIE_NAME = "view_pref";
    private static final String COOKIE_PATH = "/api/prefs";

    @PostMapping("/compact")
    public ResponseEntity<Void> chooseCompact() {
        ResponseCookie cookie = ResponseCookie.from(COOKIE_NAME, "compact")
                .path(COOKIE_PATH)
                .maxAge(Duration.ofDays(7))
                .secure(true)
                .httpOnly(true)
                .sameSite("Lax")
                .build();

        return ResponseEntity.noContent()
                .header(HttpHeaders.SET_COOKIE, cookie.toString())
                .build();
    }

    @GetMapping(value = "/current",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public String current(
            @CookieValue(name = COOKIE_NAME, required = false)
            String value) {

        if (value == null) {
            return "view_pref=missing";
        }

        // Client-controlled cookie: do not trust arbitrary values.
        if (!value.equals("compact") && !value.equals("comfortable")) {
            return "view_pref=invalid";
        }

        return "view_pref=" + value;
    }

    @DeleteMapping
    public ResponseEntity<Void> clear() {
        ResponseCookie expired = ResponseCookie.from(COOKIE_NAME, "")
                .path(COOKIE_PATH)
                .maxAge(Duration.ZERO)
                .secure(true)
                .httpOnly(true)
                .sameSite("Lax")
                .build();

        return ResponseEntity.noContent()
                .header(HttpHeaders.SET_COOKIE, expired.toString())
                .build();
    }
}
~~~

**How it works:**

1. `POST /api/prefs/compact` sends HTTP 204 and `Set-Cookie: view_pref=compact; ... Max-Age=604800; Secure; HttpOnly; SameSite=Lax`. This cookie persists for up to about 7 days per `Max-Age`.
2. `Path=/api/prefs` means the browser sends the cookie for eligible requests under this path; it is not automatically sent to every endpoint on the website.
3. `Secure(true)` preserves safe semantics for production HTTPS. For the `http://localhost:8080` demo, specific browsers may apply localhost exceptions; testing the header directly does not depend on browser storage decisions.
4. `HttpOnly(true)` shows the attribute protecting cookies from JavaScript cookie-access APIs. This is a **configuration example**; if UI JavaScript truly needs to read a non-secret preference cookie, the design could use another mechanism or consider `HttpOnly=false` **only for cookies containing no credentials**.
5. `SameSite("Lax")` sets an explicit cookie-sending policy. It does not make cross-site requests completely safe.
6. `GET /api/prefs/current` reads `@CookieValue` and validates the value. A missing cookie returns the text `view_pref=missing`; a valid cookie returns `view_pref=compact` or `view_pref=comfortable`.
7. `DELETE /api/prefs` sends `Max-Age=0` with **the same name and Path** to request cookie deletion. Deleting on the browser side does not invalidate a server session, though this example is only a preference cookie and uses no session.
8. Both POST and DELETE return 204 with no body; the `Set-Cookie` header is still valid. The status code does not need to be 200 for the browser to process cookies.

In a real system, if state-changing endpoints use cookies for authentication, appropriate CSRF protection is required. This example omits Spring Security to focus on cookie mechanics.

### 9.3. Invoking with curl

Run:

~~~bash
./mvnw spring-boot:run
~~~

On Windows: `mvnw.cmd spring-boot:run`. Without Maven Wrapper, use `mvn spring-boot:run` after installing Maven.

Send the cookie-creation request and observe the header:

~~~bash
curl -i -X POST "http://localhost:8080/api/prefs/compact"
~~~

You will see status **204 No Content**, and a `Set-Cookie` equivalent to:

~~~http
Set-Cookie: view_pref=compact; Path=/api/prefs; Max-Age=604800; Expires=...; Secure; HttpOnly; SameSite=Lax
~~~

`Expires`, if added automatically by Spring, depends on execution time; `...` here is purely **illustrative**, not a valid date string to copy into a response. Attribute order is not the primary API contract; verify the required attributes.

`curl` in the example does not automatically guarantee sending a `Secure` cookie over HTTP in subsequent commands. To **accurately demonstrate how the controller reads a request `Cookie`**, explicitly send a simulated header:

~~~bash
curl -i "http://localhost:8080/api/prefs/current"   -H "Cookie: view_pref=compact"
~~~

Expected response body:

~~~text
view_pref=compact
~~~

Without sending the cookie:

~~~bash
curl -i "http://localhost:8080/api/prefs/current"
~~~

Body:

~~~text
view_pref=missing
~~~

Sending a value outside the allowlist:

~~~bash
curl -i "http://localhost:8080/api/prefs/current"   -H "Cookie: view_pref=admin"
~~~

Body:

~~~text
view_pref=invalid
~~~

Requesting deletion:

~~~bash
curl -i -X DELETE "http://localhost:8080/api/prefs"
~~~

Expected status **204**, with `Set-Cookie` containing `view_pref=; Path=/api/prefs; Max-Age=0` along with `Secure`, `HttpOnly`, and `SameSite=Lax` flags. In a browser, inspect via DevTools **Application/Storage → Cookies** and **Network → Response Headers / Request Cookies**. With `HttpOnly`, do not expect `document.cookie` to read the cookie.

The multiline commands use `\` from Linux/macOS/Git Bash. On Windows PowerShell, use `curl.exe` with proper quoting/line continuation; a single line is usually less error-prone.

## 10. Testing `Set-Cookie` and `@CookieValue` with MockMvc

Add the `spring-boot-starter-test` dependency and the file **`src/test/java/com/example/demo/PreferenceCookieControllerTest.java`**:

~~~java
package com.example.demo;

import jakarta.servlet.http.Cookie;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(PreferenceCookieController.class)
class PreferenceCookieControllerTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void createCookieWithSevenDayExpiryAndSecurityFlags()
            throws Exception {

        MvcResult result = mockMvc.perform(
                        post("/api/prefs/compact"))
                .andExpect(status().isNoContent())
                .andExpect(content().string(""))
                .andReturn();

        String header = result.getResponse()
                .getHeader(HttpHeaders.SET_COOKIE);

        assertNotNull(header);
        assertTrue(header.contains("view_pref=compact"));
        assertTrue(header.contains("Path=/api/prefs"));
        assertTrue(header.contains("Max-Age=604800"));
        assertTrue(header.contains("Secure"));
        assertTrue(header.contains("HttpOnly"));
        assertTrue(header.contains("SameSite=Lax"));
    }

    @Test
    void readCookieIfPresentAndHandleMissingCookie()
            throws Exception {

        mockMvc.perform(get("/api/prefs/current")
                        .cookie(new Cookie("view_pref", "compact")))
                .andExpect(status().isOk())
                .andExpect(content().string("view_pref=compact"));

        mockMvc.perform(get("/api/prefs/current"))
                .andExpect(status().isOk())
                .andExpect(content().string("view_pref=missing"));
    }

    @Test
    void refuseUnknownCookieValue() throws Exception {
        mockMvc.perform(get("/api/prefs/current")
                        .cookie(new Cookie("view_pref", "admin")))
                .andExpect(status().isOk())
                .andExpect(content().string("view_pref=invalid"));
    }

    @Test
    void clearCookieUsesMatchingPathAndZeroAge()
            throws Exception {

        MvcResult result = mockMvc.perform(delete("/api/prefs"))
                .andExpect(status().isNoContent())
                .andExpect(content().string(""))
                .andReturn();

        String header = result.getResponse()
                .getHeader(HttpHeaders.SET_COOKIE);

        assertNotNull(header);
        assertTrue(header.contains("view_pref="));
        assertTrue(header.contains("Path=/api/prefs"));
        assertTrue(header.contains("Max-Age=0"));
        assertTrue(header.contains("Secure"));
        assertTrue(header.contains("HttpOnly"));
        assertTrue(header.contains("SameSite=Lax"));
    }
}
~~~

Run:

~~~bash
./mvnw test
~~~

The tests verify that **the server emits the right headers** and `@CookieValue` binds the request value properly. `MockMvc` **does not simulate a full browser**: it does not enforce `Secure` cookies over HTTP, test third-party cookie blocking, evaluate browser CSRF policies, or guarantee `SameSite` acceptance by a specific browser. Those characteristics require browser/integration tests under real HTTPS and cross-site contexts.

If a production application uses Spring Security, POST/DELETE tests may require a CSRF token and authentication. Add `spring-security-test` and use `with(csrf())` per project policy rather than disabling CSRF to make tests pass.

## 11. Session Cookies Managed by Spring Boot: Configured Differently from Custom Cookies

Applications using Servlet sessions or Spring Security may see the `JSESSIONID` cookie. **Do not manually manipulate `JSESSIONID` in a controller the way `view_pref` is created** when that cookie belongs to the container or framework's session management.

With **Spring Boot 3.x**, you can configure the session cookie in `src/main/resources/application.properties`:

~~~properties
server.servlet.session.cookie.name=JSESSIONID
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.secure=true
server.servlet.session.cookie.same-site=lax
server.servlet.session.cookie.path=/
server.servlet.session.timeout=30m
~~~

Meaning:
- `http-only=true`, `secure=true`, `same-site=lax` control the attributes the container uses when generating the session cookie.
- `path=/` exposes the cookie across routes on the host, suitable when the session applies across the entire application; it can be narrowed according to app structure.
- `server.servlet.session.timeout=30m` is the **server-side session timeout**, not the browser cookie lifetime.
- If you want the cookie to persist for a specific `Max-Age`, Boot also provides `server.servlet.session.cookie.max-age` and related properties. Evaluate this alongside timeout/invalidation policies to avoid mistakenly assuming a surviving cookie means a surviving session.
- When running over real HTTPS, `Secure=true` is the right setting. On local HTTP, a `Secure` cookie can complicate testing depending on the browser; use a controlled development profile if needed, and never ship insecure settings to production.

If the application does not actually create a session, it does not necessarily emit `JSESSIONID`. Setting these properties **does not itself create a session**.

### Non-Session Cookies: Spring Boot's `CookieSameSiteSupplier`

Spring Boot 3.x supports `CookieSameSiteSupplier` for certain cookies added through the servlet stack's `HttpServletResponse`. Illustrative example:

~~~java
import org.springframework.boot.web.servlet.server.CookieSameSiteSupplier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class CookiePolicyConfig {

    @Bean
    public CookieSameSiteSupplier demoCookies() {
        return CookieSameSiteSupplier.ofLax()
                .whenHasNameMatching("myapp.*");
    }
}
~~~

The class above is an **additional configuration example**; it does not need to be added to the controller project in Section 9. It can apply `SameSite` to matching cookie names going through Boot-supported `response.addCookie(...)` paths. Do not assume the supplier rewrites `Set-Cookie` headers constructed directly via `ResponseEntity.header` or responses from proxies; inspect the specific cookie output path in your system.

### `jakarta.servlet.http.Cookie` and `HttpServletResponse.addCookie`

The traditional Servlet approach:

~~~java
Cookie cookie = new Cookie("view_pref", "compact");
cookie.setPath("/api/prefs");
cookie.setMaxAge(604800);
cookie.setSecure(true);
cookie.setHttpOnly(true);
response.addCookie(cookie);
~~~

This is an illustrative snippet inside a method having `HttpServletResponse response`, with import `jakarta.servlet.http.Cookie`. In compatible Servlet APIs, some implementations also support `setAttribute("SameSite", "Lax")`; serialization of `SameSite` depends on Servlet version, container, and Boot policy. When you need explicit, portable `SameSite` control in Spring MVC 6.x, `ResponseCookie` and the `Set-Cookie` header are usually easier to read and test.

**Do not use `javax.servlet.http.Cookie` in Spring Boot 3.x**, as this branch is based on **Jakarta Servlet** (`jakarta.servlet.*`).

## 12. Sessions and Security: CSRF, XSS, Session Fixation

### CSRF with Cookie Authentication

If a website uses session cookies for authentication, the browser automatically attaches cookies on requests matching cookie scope and policy. An attacker may try to trick a victim's browser into sending a data-modifying request. **`SameSite=Lax/Strict` mitigates some CSRF paths but does not replace CSRF protection**.

Principles:
1. HTTP GET/HEAD must not perform dangerous state changes.
2. For state-changing POST/PUT/PATCH/DELETE backed by cookie authentication, use CSRF tokens/controls suited to Spring Security and your threat model.
3. Checking `Origin`/`Referer` and `Content-Type` where appropriate is a supplementary measure, not a replacement for tokens when the application genuinely needs them.
4. Do not treat CORS as a "CSRF wall": a request can be sent without JavaScript reading the response, especially via HTML forms or navigation mechanisms.

### XSS and `HttpOnly`

`HttpOnly` prevents scripts from reading session cookies via `document.cookie`, yet injected scripts can still interact with the site under the user's authority. Encode output, avoid unsafe DOM sinks, configure an appropriate CSP, and minimize cookie scope.

### Session Fixation and Rotation

After a user logs in, apply **session fixation protection** such as rotating the session ID; Spring Security provides corresponding session management. Never generate predictable session IDs or retain an attacker-controlled ID. On logout, destroy the server-side session/token and remove the associated cookie using framework mechanisms.

### `__Secure-` and `__Host-` Prefixes

Some browsers enforce naming-based checks on cookies:

~~~http
Set-Cookie: __Secure-session=abc; Secure; HttpOnly; Path=/; SameSite=Lax
Set-Cookie: __Host-session=abc; Secure; HttpOnly; Path=/; SameSite=Lax
~~~

- `__Secure-`: requires `Secure` and an HTTPS origin in supporting browsers.
- `__Host-`: in addition to `Secure`, requires `Path=/` and **no `Domain`**, restricting the cookie to the exact host.
- Prefixes are an additional defense layer and **do not replace authorization or session invalidation**.
- The names and cookie values above are placeholders illustrating the header, not real session identifiers to use in production.

## 13. Cross-Origin Frontends, CORS, and Third-Party Cookies

Example of a frontend app at `https://app.example.com` calling an API at `https://api.example.com`:

~~~javascript
const response = await fetch("https://api.example.com/api/prefs/current", {
  method: "GET",
  credentials: "include"
});

if (!response.ok) {
  throw new Error("HTTP " + response.status);
}

console.log(await response.text());
~~~

`credentials: "include"` permits the browser to send credentials on cross-origin requests when eligible; it **does not force** sending cookies blocked by `SameSite`, `Secure`, `Domain`, `Path`, or browser privacy policies. For JavaScript to read a cross-origin response, the backend needs appropriate CORS headers, such as a specific `Access-Control-Allow-Origin` and `Access-Control-Allow-Credentials: true` when credentials are allowed. Never combine `Access-Control-Allow-Origin: *` with credentialed requests.

If the frontend and API belong to **two different sites**, cross-site cookies may require `SameSite=None; Secure`, though **many browsers block third-party cookies** or require alternatives. Do not switch to `None` mechanically: first check whether the two origins share the same registrable domain/scheme (same-site), and consider redesigning with a same-site backend or token-based API when appropriate.

A `Set-Cookie` response may appear in the Network panel yet be flagged "blocked" by the browser due to `SameSite`, `Secure`, domain, browser privacy, prefix, cookie size, or CORS/credentials rules. Inspect the block reason in DevTools rather than checking only for status 200.

Frontend JavaScript **cannot directly read the `Set-Cookie` header via `response.headers.get("set-cookie")`** in a browser like an ordinary header: it is a **forbidden response-header name** for Fetch exposure. The browser processes `Set-Cookie` through its cookie store according to policy.

## 14. Multiple Cookies, Size Limits, and Storage Policies

Cookies are sent on matching requests, so large cookie payloads create network overhead and can be rejected by browsers or proxies. Browsers enforce size limits per cookie and count limits per domain, with specifics varying by browser/version; avoid storing large JSON objects, permission lists, or files in cookies.

Best practices:
- Store only small, necessary values; use server-side state for complex data.
- Name cookies clearly and avoid multiple cookies with the same name across overlapping paths/domains that could confuse server parsing.
- Use a narrow `Path` when appropriate; avoid overly broad `Domain` values.
- Choose a short `Max-Age` for sensitive data, not exceeding the server-side session lifetime.
- Do not write full `Cookie` or `Set-Cookie` headers containing tokens into uncontrolled application logs, analytics, or tracing.
- For authentication tokens, consider rotation/revocation and signing or encrypting values when appropriate; cookie flags **do not prove integrity or prevent tampering**.
- Do not rely on cookie order when multiple cookies share a name in a request; design the server to avoid duplicate names and ambiguous scopes.

Browsers increasingly support features like **Partitioned cookies (CHIPS)** in embedded contexts. Spring Framework 6.2 supports `ResponseCookie.ResponseCookieBuilder#partitioned(boolean)`; however, if your app runs on 6.0/6.1, verify the API before using it. For partitioned cookies, supporting browsers require `Secure` and apply distinct partitioning rules. This lesson focuses on basic `SameSite` and does not treat CHIPS as a replacement for CSRF controls.

## 15. Common Issues and Troubleshooting

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| Browser does not store cookie | `Secure` over HTTP, `SameSite=None` missing `Secure`, invalid `Domain`, third-party policy | Check DevTools blocked reason and HTTPS |
| `@CookieValue` receives null | Browser did not send cookie due to `Path`/`Domain`/`Secure`/expiry/`SameSite` | Inspect request `Cookie` header, not just response `Set-Cookie` |
| Deleted cookie still reappears | Mismatched `Path`/`Domain`, or another cookie with same name in a different scope | Compare identity between creation/deletion; inspect each cookie |
| "7-day" cookie lives only 7 seconds | Passed wrong unit or seconds count to `maxAge` | Use `Duration.ofDays(7)` |
| Cookie disappears after browser restart | Missing `Max-Age`/`Expires`, or browser privacy policy | Set an appropriate lifetime and accept that users can clear cookies |
| Cookie still holds session ID but server says expired | Independent server-side session timeout/invalidation | Distinguish session timeout from cookie expiry |
| JS cannot read `document.cookie` | Cookie has `HttpOnly` | Correct for session cookies; do not disable for credentials |
| Cross-site embed lacks cookie | `SameSite` Lax/Strict, third-party cookie policy, credentials/CORS | Verify site/origin and design appropriate authentication |
| `SameSite=None` does not work | Missing `Secure`, running over HTTP, browser tracking block | Enable HTTPS and check browser policy |
| Cookie-based API still vulnerable to CSRF | Relying solely on `SameSite` or GET endpoints having side effects | Enforce CSRF protection and proper HTTP method semantics |
| Session cookie ignores property | Cookie created by another component, or config not active at runtime | Check if `JSESSIONID` is owned by container or Spring Session, and verify profile/config |
| Two `Set-Cookie` headers merged | Custom proxy/framework improperly combining headers | Emit each `Set-Cookie` header separately |
| Sensitive data leaked in logs | Directly logging `Cookie`/`Set-Cookie` headers | Redact credentials and enforce logging policies |

### Systematic Debugging

1. **Response:** Was `Set-Cookie` actually sent? What are its name, value, Path, Domain, Max-Age, and flags?
2. **Browser storage:** Was the cookie accepted or blocked? What reason does the browser report?
3. **Next request:** Does the `Cookie` header contain the expected name–value pair?
4. **Spring controller:** Does `@CookieValue` have the right name, `required` setting, and type conversion?
5. **Session backend:** If it is a session cookie, is the session ID still valid? Did logout, rotation, or timeout occur?
6. **Cross-origin:** Are fetch credentials, CORS, SameSite, schemeful site, and third-party policies aligned?
7. **Security:** Check CSRF/XSS/session management; never widen cookie scope indiscriminately just to "fix a missing cookie."

## 16. Self-Check Questions

**Q1. How do `Set-Cookie` and `Cookie` differ?**

`Set-Cookie` is a response header instructing the browser to store or update a cookie along with its attributes. `Cookie` is a request header sending back only the name–value pairs of eligible cookies.

**Q2. Does `HttpOnly=true` stop the browser from automatically sending a cookie in `fetch`?**

No. `HttpOnly` restricts JavaScript from directly reading/modifying the cookie; the browser can still attach the cookie to eligible requests depending on `credentials`, `SameSite`, `Secure`, scope, and browser policy.

**Q3. Why does `SameSite=None` require `Secure`?**

Modern browsers require this combination to allow cookies in permitted cross-site contexts. Even with both attributes, browsers may still block third-party cookies.

**Q4. Roughly how long does a cookie set with `Max-Age=3600` live?**

About one hour, because the unit is **seconds**. The client may still delete it earlier. Do not confuse it with `server.servlet.session.timeout` for server-side sessions.

**Q5. Why is merely deleting the `JSESSIONID` cookie not guaranteed to be a secure logout?**

Because the session/token also needs to be invalidated on the server side; a leaked session ID could remain valid. Use Spring Security logout/session management.

**Q6. Does `SameSite=Lax` replace CSRF tokens?**

No. It restricts certain cross-site requests but does not eliminate all forgery scenarios or flawed HTTP method designs.

**Q7. To delete a cookie with `Path=/api/prefs`, is `Max-Age=0; Path=/` sufficient?**

Not necessarily. Deleting a cookie requires matching the name and compatible path/domain scope of the original cookie. You should specify the exact `Path=/api/prefs`.

**Q8. Does `Secure` encrypt the cookie value on disk?**

No. It restricts transmission to HTTPS in supporting browsers; it does not guarantee client-side storage encryption and does not replace server-side authorization.

## 17. Production Deployment Checklist

1. Clearly separate **session/authentication** cookies from **preference** cookies. Do not write custom session management if Spring Security already owns it.
2. Choose `Max-Age`/session timeout according to business requirements; understand that cookie expiry and server-side session expiry are distinct.
3. For sensitive cookies, use HTTPS with `Secure`, `HttpOnly`, and `SameSite=Lax` or `Strict` as suited to the flow; do not choose `None` unless cross-site usage is genuinely required.
4. Omit `Domain` unless subdomain sharing is required; restrict `Path` as needed. Consider `__Host-`/`__Secure-` prefixes in HTTPS environments.
5. Always validate cookies on receipt; never use client-controlled cookie data to grant permissions.
6. When deleting cookies, use the matching name, domain, path, and `Max-Age=0`; for authentication sessions, invalidate the session on the server.
7. Test both HTTP response `Set-Cookie` and request `Cookie`, different URL paths, expiry, CSRF/CORS, and browser acceptance under real HTTPS.
8. Control logging, cookie count, and cookie size; never put credentials into URLs or logs.
9. If deploying a cross-site iframe/SPA, distinguish **same-site** from **same-origin**, verify third-party policies and CORS credentials, and do not fix issues by disabling all security constraints.
10. For session cookies, configure them via `server.servlet.session.cookie.*` and Spring Security according to cookie ownership rather than copying preference-cookie code to replace `JSESSIONID`.

## Official Documentation

- [Spring Framework 6.2 — `ResponseCookie.ResponseCookieBuilder` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.17/javadoc-api/org/springframework/http/ResponseCookie.ResponseCookieBuilder.html)
- [Spring Framework — `@CookieValue` in Spring MVC](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/cookievalue.html)
- [Spring Boot 3.5 — Servlet Web Applications / SameSite Cookies](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html)
- [Spring Boot 3.5 — Application Properties (session cookie)](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html)
- [MDN — Set-Cookie HTTP header](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie)
- [MDN — Using HTTP cookies](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Cookies)
- [MDN — Secure cookie configuration](https://developer.mozilla.org/en-US/docs/Web/Security/Practical_implementation_guides/Cookies)
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
- [OWASP — Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)
