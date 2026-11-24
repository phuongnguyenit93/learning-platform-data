# Cookies, sessions, and how browsers automatically send data

When logging into a website, you usually only enter your username and password **once**. Afterward, you open the profile page, switch to a list page, and submit forms without having to re-enter your password on every request. This easily leads beginners to think that HTTP "remembers" who is logged in. In reality, **every HTTP request is independent at the protocol level**; the application must have a mechanism to recognize the relationship between requests.

The first two mechanisms to understand are **cookies** and **sessions**:

- A **cookie** is a piece of data stored by the browser according to HTTP rules, usually sent by the server via the `Set-Cookie` header. When a subsequent request matches the cookie's scope, the browser can **automatically include** it in the `Cookie` header.
- A **session** is application state tied to an interaction, usually kept on the server side. In servlet applications, a session can be identified by a random identifier stored in a cookie, commonly `JSESSIONID`.
- **Spring Security** can use a session to store and restore authentication information (`SecurityContext` containing `Authentication`) across subsequent requests. However, having a cookie or having a session **does not automatically** prove that the user is validly authenticated.

From this arises a security consequence: because the browser automatically sends cookies, a request the user did not intend can still carry the login cookie. This is the foundational reason to understand **CSRF (Cross-Site Request Forgery)** and cookie protection attributes.

## 1. Why does HTTP need a mechanism to maintain context?

For example, Mai logs in and then requests two resources:

~~~http
POST /login HTTP/1.1
Host: learning.example
Content-Type: application/x-www-form-urlencoded

username=mai&password=********
~~~

~~~http
GET /account HTTP/1.1
Host: learning.example
~~~

The `GET /account` request by itself carries no memory that the previous `POST /login` succeeded. The server should not require re-sending the password on every request. Instead, a stateful mechanism typically operates as follows:

1. The server authenticates the login credentials.
2. The server creates or uses an appropriate session and associates the authentication result with that session.
3. The server sends the browser a **session identifier** (session ID) via a cookie.
4. The browser stores the cookie and automatically attaches it to subsequent requests matching its scope.
5. The server reads the session ID, looks up the corresponding session, and restores the needed information.
6. When accessing a resource, Spring Security continues applying authorization rules.

Diagram illustrating a cookie-based servlet session:

~~~text
BROWSER                                          SERVER
    |                                                 |
    | POST /login (username, password)                |
    |------------------------------------------------>|
    |                                    Authentication succeeds
    |                                    Create/rotate session ID
    |                                    Save SecurityContext
    |<------------------------------------------------|
    | HTTP 302 + Set-Cookie: JSESSIONID=<random-id>   |
    |                                                 |
    | (cookie is stored in the browser's jar)         |
    |                                                 |
    | GET /account                                    |
    | Cookie: JSESSIONID=<random-id>                  |
    |------------------------------------------------>|
    |                                    Look up session
    |                                    Restore Authentication
    |                                    Check authorization
    |<------------------------------------------------|
    | 200 OK or appropriate denial response           |
~~~

This is a typical flow, not something all implementations must use sessions for. An API authenticating with a bearer token in the `Authorization` header may not use cookies to maintain state. You must observe the exact mechanism the application chooses.

## 2. How do cookies actually travel over HTTP?

The server may return a response like this:

~~~http
HTTP/1.1 200 OK
Content-Type: text/plain
Set-Cookie: DEMO_SESSION=opaque-random-id; Path=/; Secure; HttpOnly; SameSite=Lax

Login successful
~~~

The `Set-Cookie` line tells the browser to store a cookie named `DEMO_SESSION`, with value `opaque-random-id`, along with scope and security rules. This value is illustrative only; a real session ID must be unpredictable, generated with a secure random source. **The server should not send passwords in cookies.**

On a matching subsequent request, the browser may automatically send:

~~~http
GET /account HTTP/1.1
Host: learning.example
Cookie: DEMO_SESSION=opaque-random-id
~~~

Points to look closely at:

- **`Set-Cookie`** is a **response** header sent by the server to set/update a cookie.
- **`Cookie`** is a **request** header carrying the `name=value` pairs the browser decides to send.
- The `Cookie` header normally only carries name/value pairs; attributes like `HttpOnly`, `Secure`, `SameSite`, and `Path` are used to govern how the cookie is stored/sent and **are not repeated** as attributes in the request.
- The browser can hold multiple cookies and send matching name/value pairs in the same header. A cookie name is not a user identity; a cookie's value is also not automatically authenticated.
- When the browser receives multiple `Set-Cookie` responses, saving, updating, or removing cookies depends on the name, scope, attributes, and browser security policy.

Do not confuse a cookie with a field in a JSON response or `localStorage`: cookies have their own HTTP mechanism and can be sent automatically by the browser; data in `localStorage` is not automatically attached to every request.

### Are cookies sent to every website?

**No.** The browser applies per-cookie rules and request context: host/domain, path, HTTPS protocol when `Secure` is set, `SameSite`, browser cookie policy, and whether the request mode includes credentials.

For example, if a cookie is set on `https://app.example.com` with `Path=/account`, it can accompany requests to `/account` and `/account/settings`; it does not automatically accompany requests to `/public`. However, `Path` **does not create a strong security boundary** between parts of the same website: do not rely on `Path` to isolate secrets from malicious code or privileged users on the same host.

## 3. Sessions and cookies are two separate layers

You can think of a cookie as **a ticket containing a lookup code**, while a session is **the state record** managed by the server.

| Characteristic | Cookie | Server-side session |
| --- | --- | --- |
| Storage location | In the browser's cookie jar (memory or persistent) | Server memory, shared session store, database, or application-chosen store |
| Typical data | Random ID, UI preferences, small state values | Info tied to a login session or application data |
| How it is sent | Browser can auto-add `Cookie` to requests | Entire session is not auto-sent to browser; server looks up by matching ID |
| Role in login | Can transport the session identifier | Can hold `SecurityContext` and login state |
| Expiration | Cookie rules and browser policy | Timeout/invalidation decided by server, potentially independent of the cookie |

Example data held by the server:

~~~text
Session store (server-only):
  key:   <random-id-123>
  value: { userId: "mai", SecurityContext: ..., expiresAt: ... }

Browser cookie store:
  DEMO_SESSION=<random-id-123>
~~~

The browser **does not need to hold the entire** `Authentication` object or access permissions in a session cookie. The server takes the session ID, looks up the data, and makes security decisions. A session cookie usually only carries an identifier; if someone steals a still-valid session ID, they can try to use that session. Therefore **a session ID is a secret that must be protected**, even though it does not contain a password itself.

Some systems use cookies containing signed/encrypted data instead of server state lookup; not every cookie is a session ID. You must accurately distinguish the design of the system under review.

### "Session cookie" and "server session" are not synonymous

A cookie **without `Max-Age`/`Expires`** is often called a *session cookie* in terms of browser storage lifecycle. Meanwhile, `HttpSession` is a server-side state object with independent expiration rules.

Consequences:

- The cookie may still remain in the browser while the server-side session has expired: a request sending the old ID no longer has a valid session.
- The server may destroy the session on logout while the browser has not deleted the old cookie; the old ID must no longer grant permissions.
- The browser may delete the cookie while the server session has not expired: the client no longer has the ID to reference that session.
- Some browsers have session-restore features and may keep session cookies across close/reopen cycles. Do not treat closing a tab/browser as the sole safe logout mechanism.

## 4. Cookie attributes govern scope and protection level

| Attribute | Primary effect | Notes |
| --- | --- | --- |
| `Domain` | Defines the host/domain scope to receive the cookie | Omitting `Domain` is usually **host-only**: only the setting host, not automatically expanded to subdomains |
| `Path` | Only send when request path matches the configured scope | `Path=/` covers the entire website; **not** an authorization mechanism |
| `Secure` | Restricts sending the cookie over secure connections, normally HTTPS | Required for session cookies in HTTPS production; does not block internal app access by itself |
| `HttpOnly` | JavaScript via `document.cookie` cannot read/write this cookie | Browser **still sends the cookie in HTTP requests**, including script-triggered requests if sending conditions are met |
| `SameSite=Strict` | Restricts cookie to same-site context | May affect navigation to the website from another site |
| `SameSite=Lax` | Restricts many cross-site requests while allowing certain top-level safe navigations like GET | Does not replace CSRF tokens and is not an authorization boundary |
| `SameSite=None` | Allows cookie in cross-site contexts per browser policy | Requires `Secure`; browsers/third-party cookie blocking policies may still restrict it |
| `Max-Age` | Cookie lifetime in seconds | `Max-Age=0` can be used to delete a cookie with matching scope |
| `Expires` | Absolute expiration timestamp | When both are present, `Max-Age` typically takes precedence |
| `__Host-` prefix | Requires `Secure`, `Path=/`, and no `Domain` in supporting browsers | Helps prevent cookies from being set by subdomains; only use when valid over HTTPS |

**Host-only vs Domain:** if `app.example.com` sets a cookie without `Domain`, the cookie is normally only sent back to `app.example.com`. If a server is permitted to set `Domain=example.com`, the cookie may also be sent to matching subdomains, increasing exposure scope. Only broaden domain scope when truly needed.

**Secure does not mean the cookie value is encrypted at rest.** It primarily restricts the cookie from being transmitted over unencrypted HTTP. HTTPS transport and device/browser protection remain separate factors.

**HttpOnly does not make the cookie "stop working."** It restricts access via JavaScript APIs like `document.cookie`; the browser can still auto-send the cookie in requests. HttpOnly helps reduce cookie theft via certain XSS types, but XSS can still send requests in the user's context and perform actions if the app has vulnerabilities.

**SameSite is a relationship between "sites," not identical to origin.** Origin considers the **scheme + host + port** tuple, whereas same-site is based on scheme and the corresponding registrable domain. Two subdomains can be different origins yet still same-site. Therefore, using `SameSite` alone is insufficient against all scenarios from untrusted subdomains.

Example session cookie for an HTTPS website:

~~~http
Set-Cookie: __Host-SESSION=some-unpredictable-id; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Real session values must be unpredictable, protected, and rotated/invalidated at the right times. The `__Host-` prefix name is an advanced option; default servlet systems may use `JSESSIONID`, and there is no need to force a rename without a corresponding design.

## 5. What does "the browser sends automatically" mean across request methods?

A developer does not have to write manual commands to "add the session cookie" to every link on the same website. When the user clicks a link, loads a page, submits a form, or a script calls an API, **the browser decides which cookies are attached** based on scope and context.

| Request creation method | Typical behavior |
| --- | --- |
| Clicking an `<a>` link to the same site | Browser navigates and attaches matching cookies |
| Submitting an HTML form | Browser auto-sends matching cookies; this directly relates to CSRF |
| Loading images, stylesheets, or scripts | May send cookies to the target if cookie rules and third-party protections permit |
| JavaScript `fetch("/api/account")` same-origin | Defaults to `credentials: "same-origin"`; matching cookies are typically sent |
| JavaScript fetch to **another origin** | Must account for `credentials: "include"`, server CORS, and `SameSite`/third-party cookie rules; `include` cannot bypass all cookie policies |
| Non-browser API clients, such as curl | Do not inherently have a browser cookie jar; must manage cookie jars/headers via client-supported mechanisms |

Distinguishing **same-site** and **same-origin** is crucial when a frontend at `https://app.example.com` calls an API at `https://api.example.com`: the two hosts are different origins even if they may be same-site; `fetch` does not send cross-origin credentials by default. If cookies are needed, the frontend must configure `credentials` properly; the API must return appropriate CORS headers (never `Access-Control-Allow-Origin: *` with credentials), and cookies must still satisfy `Domain`, `Path`, `Secure`, and `SameSite`.

CORS primarily governs whether JavaScript from another origin may **read** the response and which request types may proceed via preflight; **CORS is not a substitute for CSRF protection**. The browser can still submit forms or navigate without JavaScript on another page needing to read the response.

### Cookie and Authorization header are two different ways to carry info

- With applications using **session cookies**, the browser usually auto-attaches cookies to matching requests.
- With APIs expecting a **bearer token in `Authorization: Bearer ...`**, the client application usually must explicitly attach the header or use HTTP client tooling that supports it. A token stored in memory or `localStorage` does not automatically turn into a `Cookie`.
- Some systems may place a bearer token **in a cookie**; in that case the browser auto-sends it per cookie rules and CSRF must be evaluated accordingly. Do not deduce the entire risk profile from the word "JWT" or "stateless."

## 6. How do auto-sent cookies lead to CSRF risk?

Suppose someone is logged into a banking site. A malicious website can cause that person's browser to issue a request to the bank, for example using a form. If the session cookie is attached and the bank only checks "is logged in," a data-modifying operation could be executed unintentionally.

Threat diagram:

~~~text
[1] User logs into bank
    Browser stores valid session cookie
                  |
[2] User opens untrusted website
    That website triggers a request to the bank
                  |
[3] Browser may auto-send bank cookie
    (depending on SameSite, context, browser policy)
                  |
[4] If server only checks the login cookie
    and lacks appropriate CSRF protection
                  |
              CSRF RISK
~~~

Key takeaway: **the server receiving a valid cookie does not ensure the request was intentionally created by the user**. The server needs to separate authentication from verifying the origin/intent of operations with side effects.

Appropriate defense layers include:

1. A **CSRF token** bound to the required context and verified by the server on state-changing requests. A malicious page should not be able to generate a valid token itself.
2. **`SameSite=Lax` or `Strict`** on session cookies when business logic permits. This is an additional barrier with limitations and variations across contexts/browsers.
3. **GET/HEAD/OPTIONS/TRACE must be designed as safe operations per HTTP semantics**: do not use GET to delete/transfer money; design state-changing endpoints using appropriate methods.
4. **Checking Origin/Referer or Fetch Metadata** where appropriate, as part of a defense-in-depth strategy.
5. **Do not broadly enable CORS credentials** for untrusted origins; CORS still does not replace CSRF tokens for websites using cookies for authentication.

Spring Security provides CSRF support for servlet applications. For session/cookie-based login web apps, **do not disable CSRF just to let a POST form pass**. Find the right way to pass a valid token in forms/headers and configure the appropriate mechanism. For stateless APIs using an `Authorization` header explicitly sent by the client, the risk assessment may differ; however, if the browser auto-attaches cookies, CSRF risk still needs consideration.

### HttpOnly does not replace CSRF tokens

An `HttpOnly` cookie may be blocked from JavaScript reads, but the browser can still attach that cookie to requests. Thus even when a script on a malicious page **does not know the session ID string**, it can still try to trigger requests to which the browser attaches the cookie per its rules.

Some SPA applications use **a separate cookie to pass the CSRF token** to JavaScript. The CSRF token cookie and the login session cookie have different roles; do not make a sensitive session cookie readable by JavaScript just because JavaScript needs to read the CSRF token.

## 7. What other risks do sessions have?

**Session hijacking:** someone who obtains a still-valid session ID can impersonate the user's session. Requires HTTPS, `Secure`, `HttpOnly`, narrow cookie scope, XSS protection, not logging IDs, invalidating sessions when needed, and limiting lifetime.

**Session fixation:** an attacker tries to create/impose a session ID before the victim logs in, then waits for that session to be elevated. After successful login, the application should change the session ID. Spring Security servlet includes session fixation protection when using standard authentication flows; on Servlet 3.1+ it commonly uses `changeSessionId`. Do not write a custom login flow and skip this step.

**Session timeout:** a session can expire even while the browser still has the cookie. APIs need to treat requests that no longer have a valid Authentication as requiring re-authentication, rather than blindly trusting an old cookie ID.

**Logout:** must invalidate the session or clear authentication state as required by the login mechanism in use; can ask the browser to delete the cookie with matching name/scope. Simply clearing the login UI or a JavaScript variable is not enough to destroy the server-side session.

**Multi-device/multi-tab:** multiple tabs of the same origin usually share a cookie jar; logging in/out in one tab can affect requests in another tab. Two devices usually have separate sessions; whether concurrent login sessions are permitted is an application policy decision.

**Permission changes while a session is alive:** an old session may retain `Authentication`/authorities from login time. If permissions are revoked, the system must design a mechanism to update permissions or invalidate/re-check the session when needed. Auto-sent cookies do not guarantee current permissions are still accurate.

## 8. Java 17+ example: a cookie jar automatically deciding which cookies to send

Java provides `java.net.CookieManager`, which simulates an HTTP client's **cookie jar**. The following example does not create accounts, does not store real sessions, and does not simulate all modern browser rules (especially SameSite and third-party cookie blocking). It only shows that a cookie received from `Set-Cookie` can automatically appear in the `Cookie` header on requests to a matching URL.

Create file `CookieJarDemo.java`:

~~~java
import java.io.IOException;
import java.net.CookieManager;
import java.net.CookiePolicy;
import java.net.URI;
import java.util.List;
import java.util.Map;

public class CookieJarDemo {

    private static boolean includesSession(
            CookieManager jar, URI target) throws IOException {
        Map<String, List<String>> headers = jar.get(target, Map.of());
        return headers.getOrDefault("Cookie", List.of())
                .stream()
                .anyMatch(value -> value.contains("DEMO_SESSION="));
    }

    public static void main(String[] args) throws IOException {
        CookieManager browserLikeJar = new CookieManager(
                null, CookiePolicy.ACCEPT_ORIGINAL_SERVER);

        URI login = URI.create("https://app.example.test/login");
        URI account = URI.create("https://app.example.test/account");
        URI otherSite = URI.create("https://different.test/account");

        System.out.println("Before login: "
                + includesSession(browserLikeJar, account));

        browserLikeJar.put(login, Map.of(
                "Set-Cookie",
                List.of("DEMO_SESSION=opaque-demo-value; "
                        + "Path=/; Secure; HttpOnly; SameSite=Lax")));

        System.out.println("After login, same host: "
                + includesSession(browserLikeJar, account));
        System.out.println("Unrelated host: "
                + includesSession(browserLikeJar, otherSite));
        System.out.println("Cookie count: "
                + browserLikeJar.getCookieStore().getCookies().size());
    }
}
~~~

Run with JDK 17 or higher, requiring no external libraries or Internet connection:

~~~bash
javac CookieJarDemo.java
java CookieJarDemo
~~~

Expected output:

~~~text
Before login: false
After login, same host: true
Unrelated host: false
Cookie count: 1
~~~

Line-by-line explanation:

1. Initially the cookie jar is empty, so requests to `/account` have no `DEMO_SESSION`.
2. `put` simulates receiving a response containing `Set-Cookie`; afterward the cookie jar selects the cookie to send to the same host over HTTPS.
3. Requests to an unrelated host do not receive `app.example.test`'s cookie.
4. The `CookieManager` store holds one cookie; the example **does not need to print the secret value**.

Do not confuse this example with a real authentication mechanism. A production server must generate IDs using a secure random source, look up valid sessions, and enforce authorization checks. JDK's `CookieManager` is not a browser: it cannot be used to draw accurate conclusions about CORS, SameSite, or third-party cookie restrictions.

## 9. Cookies and sessions in Spring Security servlet

For a Spring Boot servlet application with form login/session, the conceptual flow is typically:

~~~text
Browser
  -> Cookie: JSESSIONID=...
Servlet container
  -> looks up HttpSession by valid ID
Spring Security
  -> SecurityContextRepository loads SecurityContext when needed
  -> Authentication is used to process the current request
  -> authorization decides allow/deny access
~~~

Common classes/contracts:

- **`HttpSession`**: servlet container-side session concept; can store attributes across multiple requests.
- **`SecurityContext`**: holds the `Authentication` currently used to make security decisions.
- **`SecurityContextHolder`**: accesses the current security context on the appropriate servlet thread.
- **`SecurityContextRepository`**, e.g. `HttpSessionSecurityContextRepository`: mechanism for saving/reading authentication context across requests.
- **`JSESSIONID`**: common cookie name used to carry the session ID; the name and session tracking method can be configured.

Spring Security 6 has an **explicit SecurityContext saving** rule when custom code authenticates manually, such as in a custom filter/controller. If you construct an authentication result yourself and only put it in `SecurityContextHolder`, it is not automatically guaranteed to persist to the next request; it must be saved properly via `SecurityContextRepository`. With built-in Spring Security login mechanisms, the framework handles authentication and context persistence per configuration.

A minimal servlet `SecurityFilterChain` configuration might look like this (this is a Spring Security application snippet, not a standalone Java program):

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class WebSecurityConfig {

    @Bean
    SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/public/**").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults());

        // Do not disable CSRF for session-based form login applications.
        return http.build();
    }
}
~~~

This snippet illustrates the boundary: every URL outside `/public/**` requires authentication, persisting the authentication result across requests depends on the configured login/session mechanism, and CSRF remains enabled by default in Spring Security. To run a real application, you also need Spring Security dependencies, user or provider configuration, Spring Boot structure, and appropriate endpoint handlers.

In Spring Boot servlet, an example configuration for **session cookies in an HTTPS production environment** (do not apply verbatim to local HTTP if `Secure=true` prevents the browser from sending the cookie) is:

~~~properties
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.secure=true
server.servlet.session.cookie.same-site=lax
server.servlet.session.timeout=30m
~~~

Cookie attributes are configured by the servlet container/Spring Boot; Spring Security does not directly set every attribute on the session cookie header. When deploying behind a reverse proxy or TLS termination, trusted proxy/forwarded headers must be configured so the application recognizes the HTTPS environment properly.

**`SessionCreationPolicy.STATELESS`** can be configured for authentication flows that do not save SecurityContext in a session. However, it does not automatically disable all cookies or forbid every application component from creating an `HttpSession`; always check authentication mechanisms, CSRF, and behavior of other filters/libraries. Do not confuse `stateless` with "the browser cannot send cookies."

## 10. A request sequence to analyze yourself

Suppose a website uses `HttpSession` and the `JSESSIONID` cookie:

| Moment | What does the browser do? | What must the server do? |
| --- | --- | --- |
| Before login | Has no valid session cookie | Without a valid Authentication, require authentication |
| After login | Receives `Set-Cookie` and stores session ID | Create/rotate session ID and save valid authentication state |
| Opening a new page on the same site | Auto-sends cookie if URL and context match | Look up session, read SecurityContext, and check permissions |
| Session expired | May still send the old cookie | Do not treat the expired ID as a valid session |
| Logout | May be instructed to delete cookie | Invalidate session/clear context per login mechanism |
| Opening a link from another site | May or may not send cookie depending on SameSite | Do not rely solely on cookie presence to confirm intent to perform changes |
| Calling an API on another origin | `fetch` needs to consider credentials, CORS, and cookie policy | Only return credentialed responses to allowed origins and still enforce authentication, authorization, and proper CSRF |

Thought experiment: the user logs in successfully, the browser sends `JSESSIONID` on the next request, but the server session has been deleted. **The cookie may still appear in the request, but the server cannot find a valid authenticated session**, so the user cannot be considered logged in. Conversely, if the server has a valid session but the browser does not send the right cookie, the server cannot guess which session belongs to that request.

## 11. Common mistakes and how to avoid them

1. **"HTTP has built-in sessions because the browser remembers the user."** HTTP does not remember requests on its own; cookies/sessions are an added mechanism.
2. **"Cookies and sessions are the same thing."** Cookies live on the client; server-side sessions are state that can be identified by a cookie.
3. **"`JSESSIONID` contains the entire account and permissions."** Usually it only holds an ID for session lookup; authentication state resides in server-side context.
4. **"Having a `Cookie` header means already logged in."** A cookie can be invalid, expired, belong to an unrelated feature, or not map to a trusted Authentication.
5. **"`HttpOnly` stops the browser from sending the cookie."** False: it restricts JavaScript reads/writes, while the browser still auto-sends it per rules.
6. **"`Secure` prevents all cookie attacks."** False: properly configured HTTPS, reduced scope, XSS/CSRF protection, and session ID protection are still required.
7. **"`SameSite=Lax` eliminates all CSRF."** False: it is one defense layer; websites still need an appropriate anti-CSRF strategy.
8. **"CORS allows/denies login instead of CSRF."** False: CORS and CSRF address different boundaries.
9. **"GET changing data is fine because the user is logged in."** Unsafe: GET navigations can be triggered from other sources; safe operations should not mutate business state.
10. **"Using JWT instead of sessions eliminates CSRF."** Incorrect if the JWT still sits in an auto-sent cookie; evaluate the transport mechanism and request conditions.
11. **"Closing the browser always destroys the server session."** Not guaranteed; cookie lifetime and `HttpSession` are two separate layers.
12. **"Just deleting the cookie on the client invalidates the session."** With server sessions, you still need to invalidate the session or appropriate authentication state.

## 12. Self-check questions

**1. Why do users typically not need to re-send their password on every request after logging in?**  
Because the browser can resend a cookie containing the session ID, and the server uses this ID to look up saved authentication state. Each request still must be verified per the application's mechanism, not by inheriting memory from HTTP.

**2. Who sets the cookie, and who sends the cookie on subsequent requests?**  
The server usually sets it via the `Set-Cookie` response header. The browser stores it and automatically selects matching cookies to send in the `Cookie` request header.

**3. `HttpOnly` is enabled. JavaScript cannot read the session ID. Why is CSRF protection still needed?**  
Because the browser can still automatically attach the cookie to requests; the request carrying the cookie does not prove the user intentionally requested a state change.

**4. The browser has the `JSESSIONID` cookie, yet the server reports unauthenticated. Is it necessarily a cookie bug?**  
No. The session may have expired, been invalidated, not be found in the session store, or no longer hold a valid Authentication.

**5. Frontend `app.example.com` calls `api.example.com`. Why might the cookie not be sent even though both seem like the same website in everyday terms?**  
Because the two addresses are different origins; `fetch` only sends credentials same-origin by default. One must also consider credentials config, CORS, domain/path, Secure, SameSite, and browser policies.

**6. Does an API using a bearer token in `Authorization` carry the same CSRF risk as an app using session cookies?**  
You cannot conclude solely from the word "bearer." If the browser does not auto-send credentials and the client must explicitly attach the header, CSRF risk may differ. If the token sits in an auto-sent cookie, CSRF must be evaluated like other cookie mechanisms.

**7. Can a logged-in user modify every record just because their session cookie is valid?**  
No. Cookies/sessions establish the authentication context; Spring Security and business logic still must check permissions to operate on the specific requested data.

When encountering login or request security issues in Spring Security, inspect along the chain: **does the response have `Set-Cookie` → does the browser save the cookie → does the next request send the matching `Cookie` → does the server find the session → does `SecurityContext` have a valid Authentication → do authorization and CSRF allow the operation**. Breaking down these steps helps pinpoint whether the bug is at the HTTP layer, session layer, or security layer.

### References

- [MDN — Using HTTP cookies](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Cookies)
- [MDN — Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie)
- [MDN — Secure cookie configuration](https://developer.mozilla.org/en-US/docs/Web/Security/Practical_implementation_guides/Cookies)
- [Spring Security — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html)
- [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Spring Boot — Common Application Properties](https://docs.spring.io/spring-boot/reference/application-properties.html)
