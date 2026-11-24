# Cookies, Sessions, and HTTP Statelessness

HTTP is designed around a request/response model: each request must carry enough information for the server to process that request. The protocol does not require the server to remember the state of a previous request. This characteristic is commonly called **stateless** (not storing state at the protocol level).

In web applications, users still need stateful experiences such as login, shopping carts, UI preferences, and multi-step workflows. Cookies and sessions are two common mechanisms to link independent requests into a continuous experience. Understanding each mechanism's role helps design APIs, configure Spring Boot, and secure applications properly.

## 1. What Does HTTP Stateless Mean?

An HTTP request can be processed independently based on the method, URL, headers, body, and accompanying authentication info. The server does not need to remember that the same client called an endpoint earlier.

Example:

~~~http
GET /products/42 HTTP/1.1
Host: shop.example.com
Accept: application/json
~~~

The server can handle this request using the path and existing data. The next request to the same server is still a brand-new request:

~~~http
GET /products/43 HTTP/1.1
Host: shop.example.com
Accept: application/json
~~~

HTTP does not automatically carry variables like currentUser or cart from the first request to the next. If the application needs to know two requests belong to the same user, it must identify the user from information sent again, such as a cookie holding a session ID or a token in the Authorization header.

Distinguish three concepts:

- **HTTP statelessness**: the protocol does not require the server to remember processing state from an earlier request to understand a later one.
- **Application statefulness**: the application persists data across requests, such as a login session or shopping cart.
- **Persistent connection**: keeping a TCP/TLS or HTTP connection open for reuse. Keep-alive and multiplexing do not turn HTTP itself into a business-stateful protocol.

An application can use stateless HTTP while still storing business state in a database, cache, or session store. Stateless also does not mean the server has no memory or stores no data.

## 2. What Is a Cookie and How Does It Work?

A **cookie** is a small name/value pair sent by the server to the browser via the Set-Cookie header. The browser can store the cookie and automatically send it back on subsequent requests when the request matches the cookie's scope and policy.

Basic flow:

1. The browser sends a request to the server.
2. The server returns a response with a Set-Cookie header.
3. The browser checks attributes and stores the cookie if policy permits.
4. On subsequent matching requests, the browser attaches the cookie in the Cookie header.
5. The server reads the cookie value to identify the client or apply preferences.

Example response:

~~~http
HTTP/1.1 200 OK
Set-Cookie: theme=dark; Path=/; Max-Age=2592000; Secure; HttpOnly; SameSite=Lax
Content-Type: application/json
~~~

A subsequent request within matching scope may contain:

~~~http
GET /account HTTP/1.1
Host: shop.example.com
Cookie: theme=dark
~~~

The Set-Cookie header is sent by the server in the response; the Cookie header is sent by the browser in the request. The browser does not send back attributes like Path, Secure, or SameSite in the Cookie header. Those attributes are used by the browser to decide whether to send the cookie.

A response can set multiple cookies using multiple separate Set-Cookie headers. Do not merge multiple cookies into a single Set-Cookie header separated by commas because the Expires attribute itself can contain a comma. In Java/Spring, use addHeader for each Set-Cookie when sending multiple cookies.

## 3. Important Cookie Attributes

| Attribute | Effect | Common usage |
|---|---|---|
| **Name=Value** | Cookie name and value | Keep values small; avoid storing secrets |
| **Expires** | Timestamp when the cookie expires | Use when the cookie should persist until a specific date/time |
| **Max-Age** | Lifetime in seconds | Usually easier to control duration than Expires |
| **Domain** | Host scope permitted to receive the cookie | Omit to restrict to current host; declaring it expands to matching subdomains |
| **Path** | Path scope for sending the cookie | Use Path=/ if the cookie applies across the whole app |
| **Secure** | Send cookie only over secure HTTPS connections | Enable in production environments using HTTPS |
| **HttpOnly** | Prevents JavaScript from reading the cookie via document.cookie | Enable for cookies containing session IDs or auth info |
| **SameSite** | Controls sending cookies in certain cross-site contexts | Choose Lax, Strict, or None depending on navigation and integration flows |

### 3.1. Expires and Max-Age

Without Expires or Max-Age, a cookie is usually treated as a session cookie managed by the browser's browsing session. Browser session does not always mean closing the window guarantees the cookie disappears; some browsers restore sessions after restarting.

Max-Age specifies how many seconds the cookie is kept. For example, Max-Age=3600 keeps the cookie for one hour. Expires specifies an expiration date/time. If both are present, Max-Age takes precedence under current cookie rules.

Cookie expiration in the browser and session expiration on the server are two separate things. Deleting a browser cookie does not automatically delete the server session; conversely, an expired server session does not mean the cookie ID vanished from the browser.

### 3.2. Domain and Path

If Domain is omitted, the cookie is a host-only cookie: only the host that created it receives it back. If Domain is declared, the cookie may be sent to that domain and matching subdomains. Only widen Domain when sharing cookies across multiple hosts is truly necessary.

Path restricts which request paths receive the cookie. For instance, Path=/admin limits the cookie to paths under /admin. Path is not a security authorization mechanism; the server must still enforce access control on every endpoint.

### 3.3. Secure and HttpOnly

Secure instructs the browser to send the cookie only over secure connections. This attribute does not encrypt the cookie value itself; TLS protects data in transit.

HttpOnly prevents JavaScript from reading the cookie via document.cookie. This reduces the risk of malicious scripts directly stealing a session ID during an XSS attack. However, injected scripts can still make requests from a compromised page and the browser will still attach the cookie. HttpOnly does not replace preventing XSS with context-aware output encoding, input validation, and an appropriate Content Security Policy.

### 3.4. SameSite

SameSite governs whether the browser sends cookies in certain cross-site requests:

- **Strict**: strictly limits sending cookies in cross-site contexts. Can hurt UX when users arrive at the app from an external link.
- **Lax**: allows cookies on certain safe top-level navigations while restricting many other cross-site requests. Often a balanced default for regular session cookies.
- **None**: allows cookies to be sent in cross-site contexts subject to other browser rules; SameSite=None cookies must set Secure.

SameSite helps mitigate CSRF risks yet should not be treated as the sole defense. Identity-provider logins, iframes, or third-party payment flows may require different policies; always test in real browsers.

### 3.5. Cookie Prefixes

Some browsers support prefixes that enforce stricter rules:

- Cookies prefixed with __Secure- must be created with the Secure attribute.
- Cookies prefixed with __Host- must set Secure, Path=/, and must not declare Domain.

For example, the name __Host-session prevents a cookie from being scoped to subdomains or other paths. Exact support and rules depend on browsers; still configure all attributes explicitly.

## 4. What Is a Session?

A **session** is a server-side mechanism for storing state for a user or interaction flow over a period of time. The server creates a session and issues the client a random identifier, typically called a session ID. The browser stores this ID in a cookie and sends it back on matching requests.

Common pattern:

- The server creates a session and stores data such as user ID, shopping cart, or workflow state.
- The server sends the session ID to the browser via a cookie.
- The browser sends the session ID on subsequent requests.
- The server uses the ID to look up the corresponding session in a session store.
- When the session expires or is invalidated, the old ID can no longer access that state.

In Servlet containers, the default session cookie is commonly named JSESSIONID. The cookie name and session storage mechanism are configurable. Do not treat JSESSIONID as a mandatory HTTP standard; it is a common Servlet container convention.

Cookies and sessions are not interchangeable concepts:

- A cookie is a mechanism to store and transmit data on the client side.
- A session is state managed on the server side.
- A cookie can hold a session ID so the server locates the right session.
- A UI preference cookie may have nothing to do with a server session.
- An application can use sessions without storing bulky data in cookies; the cookie only holds the identifier.

## 5. Lifecycle of an HTTP Session

A session lifecycle typically includes these stages:

1. **Session creation**: the application or framework requests creating a session when state needs to be stored.
2. **Issuing ID**: the server generates an unpredictable ID and sends it to the client, usually via Set-Cookie.
3. **Using the session**: the browser sends back the ID; the server looks up session data and handles the request.
4. **Renewal or expiration**: activity may reset the inactivity timeout; once past the limit, the session is evicted.
5. **Logout or invalidation**: the server invalidates the session and removes corresponding data; the browser cookie ID should also be expired if needed.

Session timeout is usually an inactivity timeout (idle timeout). If security requirements demand capping total login duration, the application must also enforce an absolute timeout; relying solely on idle timeout can allow a session to remain active indefinitely if the user stays active.

When a user logs in successfully, rotate the session ID to prevent session fixation. An attacker might trick a victim into using a session ID known to the attacker; if the ID stays unchanged after login, the attacker can exploit the elevated session. Spring Security includes session fixation protection in standard authentication flows, yet you should re-verify if customizing authentication or session management.

Do not store passwords, long-lived access tokens, sensitive payment details, or large domain objects in sessions. Store only the minimal data required, control lifetimes, and enforce access limits.

## 6. Cookies, Sessions, and Tokens: Comparing State Storage Approaches

| Mechanism | Where does data live? | What does the request carry? | Must server look up state? |
|---|---|---|---|
| Preference cookie | Browser | Cookie name/value | Not necessarily |
| Cookie carrying session ID | Server-side session store; cookie holds ID | Session ID in Cookie | Yes |
| Server-side session | Database, cache, or server memory | Session reference ID | Yes |
| Opaque bearer token | Client holds token; server or auth service manages token | Token in Authorization header | Usually requires lookup or introspection |
| JWT access token | Client holds token; claims reside in signed token | JWT in Authorization header or cookie | Signature can be verified without per-request lookup |

JWTs are typically Base64URL-encoded and signed for integrity; the payload is not automatically encrypted for confidentiality. Anyone holding the token can usually read its claims. Do not place passwords, secret keys, or sensitive data in an unencrypted JWT payload.

Using tokens does not automatically make a system more secure than sessions. Consider token lifetime, revocation, key rotation, client-side storage, and XSS/CSRF risks. A token stored in a cookie is still automatically sent by browsers and therefore still requires CSRF evaluation. A token in an Authorization header is not automatically sent on normal browser navigations, yet if exposed via XSS it can still be stolen.

## 7. Stateful vs. Stateless in Application Design

### 7.1. Stateful Sessions

The application stores session state on the server and the client sends only the session ID. The advantage is immediate revocation by invalidating or deleting session data; the client does not resend all state on every request.

On the flip side, the server must manage the session store, timeouts, cross-node synchronization, and store outages. In multi-instance deployments, sessions stored only in one node's memory break if the next request routes to another node.

Common deployment choices:

- **Sticky sessions**: the load balancer pins a client's requests to the same node. This avoids sharing sessions yet still requires handling node failures or topology changes.
- **Session replication**: nodes synchronize session data; evaluate synchronization cost and latency.
- **Shared session store**: store sessions in Redis or JDBC so multiple instances read/write together. Spring Session supports integrating stores like Redis and JDBC.

If using a shared store, define TTL, serialization, size limits, compatibility across rolling deployments, and fallback behavior if the store becomes temporarily unreachable.

### 7.2. Stateless Authentication

With a stateless design, the server holds no per-client login session. Each request carries credentials sufficient for verification, such as a signed bearer token. The server may still query a database for permissions or business data; stateless here refers to not relying on a login session kept across requests.

The benefit is that instances handle requests independently without sharing login sessions. The tradeoff is that revoking a token before expiration is harder; design short-lived access tokens, refresh tokens, denylists, or introspection if security requirements demand it.

### 7.3. Choosing by Need

- Traditional web apps with login and server-side rendering typically fit session cookies.
- Mobile APIs or service-to-service APIs typically use bearer tokens in the Authorization header.
- Multi-node apps needing immediate session revocation can use Spring Session with Redis/JDBC.
- A system can combine sessions for the web UI and tokens for external APIs, provided authentication boundaries stay clear.

Do not pick stateless solely to scale horizontally. Sessions with a shared store scale too; stateless tokens still require key management, revocation strategies, and access control.

## 8. Configuring Session Cookies in Spring Boot

For Servlet applications using Spring Boot, common properties live in application.properties or application.yml.

Example application.properties:

~~~properties
server.servlet.session.timeout=30m
server.servlet.session.cookie.name=JSESSIONID
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.secure=true
server.servlet.session.cookie.same-site=lax
~~~

Meaning:

- server.servlet.session.timeout sets session inactivity duration.
- server.servlet.session.cookie.name sets the session cookie name.
- http-only restricts JavaScript access to the session cookie.
- secure requires sending the cookie only over HTTPS.
- same-site=lax limits sending the cookie in many cross-site contexts.

When running locally over plain HTTP, cookies marked Secure may not be sent on ordinary HTTP requests. Account for this during local testing. Production environments should use HTTPS end-to-end, even when TLS terminates at a reverse proxy; proxy and forwarded-header settings must be accurate so the app sees the real external scheme.

Property names and configuration options can vary across Spring Boot versions. Check the metadata/documentation for your project's exact version, especially when working on older releases.

## 9. Creating Custom Cookies in Spring MVC

When storing non-sensitive preferences such as a theme, you can issue a dedicated cookie. The example below uses Spring Boot 3.x, Java 17+, and Spring MVC.

~~~java
package com.example.web;

import java.time.Duration;
import java.util.Map;

import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseCookie;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.CookieValue;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/preferences")
public class PreferenceController {

    @GetMapping("/theme")
    public Map<String, String> getTheme(
            @CookieValue(name = "theme", required = false) String theme) {
        return Map.of("theme", theme == null ? "light" : theme);
    }

    @PostMapping("/theme")
    public ResponseEntity<Void> saveTheme(@RequestParam String theme) {
        if (!theme.equals("light") && !theme.equals("dark")) {
            return ResponseEntity.badRequest().build();
        }

        ResponseCookie cookie = ResponseCookie.from("theme", theme)
                .path("/")
                .maxAge(Duration.ofDays(30))
                .secure(true)
                .httpOnly(true)
                .sameSite("Lax")
                .build();

        return ResponseEntity.noContent()
                .header(HttpHeaders.SET_COOKIE, cookie.toString())
                .build();
    }

    @DeleteMapping("/theme")
    public ResponseEntity<Void> clearTheme() {
        ResponseCookie cookie = ResponseCookie.from("theme", "")
                .path("/")
                .maxAge(Duration.ZERO)
                .secure(true)
                .httpOnly(true)
                .sameSite("Lax")
                .build();

        return ResponseEntity.noContent()
                .header(HttpHeaders.SET_COOKIE, cookie.toString())
                .build();
    }
}
~~~

Key points to understand:

- @CookieValue reads a cookie value from the request.
- ResponseCookie builds a Set-Cookie header with the chosen attributes.
- Max-Age=0 instructs the browser to delete the cookie.
- To delete a cookie, its name, Domain, and Path must match the original cookie. If the original cookie used a different Domain or Path, reuse that exact scope when clearing it.
- Because the example enables Secure, real browser testing requires HTTPS.
- The theme cookie stores only a display preference and must never be used as proof of authentication or authorization.

If a response needs multiple cookies, call addHeader(HttpHeaders.SET_COOKIE, ...) for each cookie. Avoid concatenating multiple Set-Cookie values with commas in a single header.

## 10. Storing and Reading Data in HttpSession

Spring MVC can inject HttpSession as a controller parameter. Example illustrating a cart item counter:

~~~java
package com.example.web;

import java.util.Map;

import jakarta.servlet.http.HttpSession;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/cart")
public class CartController {

    @GetMapping
    public Map<String, Integer> getCart(HttpSession session) {
        Integer count = (Integer) session.getAttribute("itemCount");
        return Map.of("itemCount", count == null ? 0 : count);
    }

    @PostMapping("/items")
    public Map<String, Integer> addItem(HttpSession session) {
        Integer count = (Integer) session.getAttribute("itemCount");
        int updatedCount = (count == null ? 0 : count) + 1;
        session.setAttribute("itemCount", updatedCount);
        return Map.of("itemCount", updatedCount);
    }
}
~~~

On the first request to an endpoint requiring a session, the Servlet container creates one if absent and sends the session ID to the client. Subsequent requests carry the session ID cookie so the server restores the data.

Example test using curl:

~~~bash
curl -i -c cookies.txt http://localhost:8080/api/cart
curl -i -b cookies.txt -c cookies.txt -X POST http://localhost:8080/api/cart/items
curl -i -b cookies.txt http://localhost:8080/api/cart
~~~

The -c option saves received cookies to a file; -b sends cookies from the file in the request. The POST increments the item count, and the subsequent GET reads back the stored session value. When using Secure cookies, test over HTTPS rather than HTTP.

This example only demonstrates retaining data across requests. Real shopping carts normally store business data in a database or cart service so data is not lost when sessions expire, nodes are replaced, or users switch devices.

## 11. Securing Cookies, Sessions, and Requests

### 11.1. CSRF

Browsers automatically attach matching cookies when visiting a website. Therefore, if a cookie represents a login session, a malicious site can cause the browser to send requests to the real website along with the victim's cookies. This is the basis of Cross-Site Request Forgery (CSRF).

Combine these defenses:

- Enable CSRF protection suited to your application, especially for cookie-based authentication.
- Use an appropriate SameSite attribute as an additional defense layer.
- For state-changing operations, use appropriate HTTP methods and validate request origins per policy.
- Do not treat CORS as CSRF protection; CORS primarily governs whether JavaScript can read cross-origin responses, not whether requests are sent.
- Test form, AJAX, login, and third-party integration flows.

Spring Security enables CSRF protection by default for common Servlet configurations. If disabling or customizing CSRF, document the client types, credential transport, and compensating controls. Never disable CSRF merely to silence a 403 error without understanding the cause.

### 11.2. Session Fixation and Session Hijacking

Session fixation happens when an attacker forces a user to use a predetermined session ID. Session hijacking happens when a valid session ID is stolen and reused by someone else.

Mitigate risks by:

- Transmitting session cookies only over HTTPS with Secure enabled.
- Enabling HttpOnly to restrict JavaScript cookie reads.
- Setting appropriate SameSite and CSRF protection.
- Generating unpredictable session IDs—never deriving IDs from usernames, timestamps, or guessable values.
- Rotating session IDs upon authentication or privilege elevation.
- Invalidating sessions on logout and enforcing sensible timeouts.
- Never logging full session IDs or tokens in logs, URLs, or error messages.

### 11.3. XSS and Data Inside Cookies

HttpOnly reduces JavaScript's ability to read cookies, yet does not stop XSS from executing actions on behalf of the user. Apply context-aware output encoding, avoid unsafe HTML injection, validate input, and configure an appropriate CSP.

Do not store secrets inside a cookie merely because Secure or HttpOnly is set. Secure protects transit; HttpOnly restricts JavaScript access. Neither turns a cookie into encrypted secret storage.

### 11.4. Cookies and CSRF in APIs

If an API accepts bearer tokens explicitly attached by client code in the Authorization header, browsers do not automatically attach that header on cross-site navigations. CSRF risk is typically lower than with auto-sent cookie credentials, though XSS and token leakage remain threats.

If a bearer token is placed inside a cookie, browsers once again attach it automatically according to cookie rules; apply CSRF protection just as with any cookie-based authentication. Never decide whether to enable/disable CSRF based solely on whether a token is a JWT.

## 12. Logout and Session Removal

Logout must invalidate server-side authentication state. With a Servlet session, call invalidate on the current session:

~~~java
session.invalidate();
~~~

In Spring Security applications, use Spring Security's logout flow to clear the SecurityContext, handle the session, and clear configured cookies. If writing a custom logout endpoint, ensure no security cleanup step is missed.

Clearing the browser cookie is a separate operation. The server sends Set-Cookie with the same name and Domain/Path scope, setting Max-Age=0 or an Expires date in the past. If Path or Domain does not match, the old cookie can linger.

Do not put session IDs in query strings for URL rewriting unless required for exceptional legacy compatibility. URLs can be saved in browser history, access logs, analytics, proxy logs, or Referer headers, exposing the session identifier.

## 13. Testing Cookies and Sessions

A test suite should cover:

- **Cookie issued**: response contains Set-Cookie with expected attributes.
- **Cookie read back**: subsequent request sends the cookie and the app handles its value properly.
- **Cookie cleared**: response clears the cookie with the exact name and scope.
- **Session retained**: multiple requests sharing a session ID observe the same session state.
- **Session expired**: session data is inaccessible after the configured timeout.
- **Logout**: session is invalidated and subsequent requests lose privileges tied to the old session.
- **CSRF**: state-changing requests missing a valid token or origin are rejected per policy.
- **Multi-node deployment**: sessions work properly when requests bounce across instances if required by architecture.

MockMvc can test cookies and sessions in integration tests. Example:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class CartControllerTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void keepsCartCountInSession() throws Exception {
        MockHttpSession session = new MockHttpSession();

        mockMvc.perform(post("/api/cart/items").session(session))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.itemCount").value(1));

        mockMvc.perform(get("/api/cart").session(session))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.itemCount").value(1));
    }
}
~~~

The test requires the corresponding static imports from Spring Test, MockMvc, JUnit, and JSONPath. MockHttpSession simulates a session in tests; it does not replace testing against a real Servlet container or verifying browser cookie behavior.

## 14. Common Issues and Troubleshooting

| Symptom | Possible cause | Where to check |
|---|---|---|
| State lost on the request right after login | Session cookie was not saved or not sent back | Inspect Set-Cookie, Cookie, Domain, Path, Secure, and SameSite |
| Secure cookie fails during local development | Request uses plain HTTP | Test over HTTPS or configure a separate local profile |
| Browser still sends old cookie after deletion | Deletion Path or Domain mismatches original cookie | Send clearing Set-Cookie with matching name and scope |
| Session disappears when routed to another node | Session lived only in the previous node's memory | Use sticky sessions or a shared store like Spring Session |
| User remains logged in after closing the browser | Browser restored session or server session has not expired | Enforce explicit timeouts and logout/absolute timeout policies |
| POST request returns 403 | Missing or invalid CSRF token | Check Spring Security config and how the client sends the CSRF token |
| Cookie has HttpOnly yet weird actions happen under XSS | Malicious script still sends requests from the compromised page | Fix the XSS vulnerability; HttpOnly only blocks direct cookie reads |
| Duplicate cookies with the same name exist | Cookies were created with different Path or Domain values | Inspect all Set-Cookie headers and clear each scope |
| Session ID appears in logs or URLs | App logs credentials or uses URL rewriting | Remove IDs from URLs/logs and rotate session IDs if exposed |
| JWT treated as confidential data | Payload is only Base64URL-encoded and signed | Do not put secrets in claims; encrypt separately if confidentiality is truly needed |

## 15. Process for Choosing a State Mechanism

When designing a feature, follow this sequence:

1. Identify what data must persist across requests and for how long.
2. If it is only a small, non-sensitive preference, consider a cookie.
3. If you need session revocation and server-side state, use a session with an ID cookie.
4. If an API requires client-attached credentials, consider bearer tokens with expiration/revocation policies.
5. If deploying multiple instances, choose appropriate session sharing or routing.
6. Evaluate CSRF, XSS, HTTPS, timeouts, logout, and access control.
7. Write tests for initial requests, subsequent requests, and expiration scenarios.

Do not store critical business records solely in cookies or temporary sessions. Orders, payments, ownership, and auditable data must live in durable data stores; cookies/sessions should hold only references or short-lived state.

## 16. Summary

HTTP does not natively preserve business state across requests. Cookies let browsers store small amounts of data and send them back automatically when scoped appropriately. Sessions keep state on the server and usually rely on a session ID cookie to correlate requests. Stateless authentication requires the client to send credentials on every request while still requiring token lifecycle management.

In Spring Boot, configure session cookies with appropriate Secure, HttpOnly, and SameSite settings; set intentional timeouts; rotate session IDs upon authentication; invalidate on logout; and use a shared session store when running multiple instances. Choosing between cookies, sessions, and tokens must rest on where data lives, how credentials travel, revocation requirements, and deployment topology.
