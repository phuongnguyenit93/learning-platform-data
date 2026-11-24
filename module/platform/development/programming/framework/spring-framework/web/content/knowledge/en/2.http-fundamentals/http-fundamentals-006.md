# Cookies, Sessions, and the Limits of State Over HTTP

HTTP is a **request–response** exchange protocol. A request is normally processed based on its method, URL, headers, body, and data the server can look up. HTTP itself **does not remember** who sent a previous request or what happened in that request. To support a shopping cart, login, language preferences, or multi-step workflows, an application must design a mechanism to link requests together.

Three concepts to distinguish from the start:

- A **cookie** is a name–value pair with attributes that the server asks the user agent to store via `Set-Cookie`, and that the user agent may send back via `Cookie` when conditions match. Cookies live on the client side.
- A **session** is how an application links multiple requests over a period of time. In the common server-side session model, the cookie only carries a **session ID**, while the actual state resides on the server or in a session store.
- **Authentication state** is the application's knowledge of who is currently authenticated, usually tied to a session or token. Having a cookie/session **does not mean** the user is logged in.

This lesson focuses on the HTTP mechanics, how browsers handle cookies, server-side session state, limits and security implications, and then connects them to Spring MVC.

## 1. Why Is HTTP Called Stateless?

Consider two independent requests:

```http
GET /catalog HTTP/1.1
Host: shop.example
```

```http
GET /checkout HTTP/1.1
Host: shop.example
```

Looking at these two messages alone, the server cannot tell for sure that the same user sent them. A TCP/TLS connection may be reused, yet **a connection is not a user identity**. Clients can open multiple connections; proxies, load balancers, and HTTP/2/HTTP/3 change how requests are transported without causing HTTP itself to create business sessions.

Statelessness does not mean **the server cannot store data**. The server can store accounts, orders, carts, or sessions in a database. The key point is that the protocol does not define built-in conversational memory across requests. The application must provide a way to identify which state the current request relates to.

```text
Request 1: client ── HTTP ──> server  → create state
Request 2: client ── HTTP ──> server  → needs key to look up old state
                                    ↑
                        Cookie / token / request data
```

Some applications are designed **statelessly at the application layer**: every request carries a token or verifiable data, so the server does not need to store a corresponding login session. Others use **stateful server sessions**: requests carry a session ID so the server looks up session data. Both still run over HTTP.

## 2. How Do Cookies Travel Over HTTP?

### 2.1. Set-Cookie and Cookie go in opposite directions

An example response:

```http
HTTP/1.1 200 OK
Content-Type: text/plain
Set-Cookie: sid=opaqueRandomIdentifier; Path=/; Secure; HttpOnly; SameSite=Lax

Session created.
```

After receiving the response, the browser **may store** the cookie if permitted by cookie policy and the current context. On a subsequent request to a matching host/path:

```http
GET /profile HTTP/1.1
Host: shop.example
Cookie: sid=opaqueRandomIdentifier
```

Notes:

1. `Set-Cookie` is a **response header**; `Cookie` is a **request header**. In `Cookie`, the client mainly sends `name=value` pairs and **does not send back** `HttpOnly`, `Secure`, `SameSite`, or `Path` as attributes.
2. One response can include multiple `Set-Cookie` headers; one request can send multiple cookie pairs.
3. The `sid` value here is merely a dummy illustrative string. Real session IDs need sufficient randomness/unpredictability; **never use a username or sequential number as a session ID**.
4. The browser decides whether to send a cookie based on host/domain, path, HTTPS, expiration, site context, and its own policies. The server cannot assume every client always retains or sends cookies.
5. JavaScript `fetch` is governed by its own credentials/CORS rules; knowing a valid URL does not guarantee cross-origin requests automatically include cookies.

Cookies are client-side data: any value sent by a client must be treated as **untrusted input**. Cookies are generally neither encrypted nor signed by default; users can modify their own cookies, even though `HttpOnly` restricts access via in-page JavaScript.

### 2.2. Core attributes

| Attribute | Practical Meaning | What to Remember |
| --- | --- | --- |
| `Domain` | Restricts the host/domain scope receiving the cookie | If `Domain` is omitted, the cookie is typically **host-only**; setting `Domain=example.com` can allow matching subdomains to receive it. Cannot be used to set cookies for unauthorized domains. |
| `Path` | Restricts the URL path to which the cookie is attached | For example `Path=/account`; **not an authorization/security isolation mechanism** separating application areas. |
| `Secure` | Sends the cookie only over connections considered secure under user-agent rules | In standard deployments, uses HTTPS; certain behaviors for localhost depend on the browser. |
| `HttpOnly` | Prevents page-side JavaScript from directly reading/writing the cookie via APIs like `document.cookie` | The browser **still automatically sends** the cookie on matching requests, including requests initiated by JavaScript. Does not by itself prevent CSRF or XSS completely. |
| `SameSite=Strict` | Strictly restricts sending the cookie in cross-site contexts | Strengthens protection against some CSRF attacks, though it can affect user flows arriving from other sites. |
| `SameSite=Lax` | Withholds cookies on most cross-site requests, while still allowing certain eligible top-level navigations | Suitable for many typical sessions; **does not replace full CSRF defense**. |
| `SameSite=None` | Allows sending in cross-site contexts if browser policies permit | Modern browsers typically require `Secure` alongside it; still subject to third-party cookie/partitioning restrictions. |
| `Max-Age` | Cookie lifetime in seconds | If both `Max-Age` and `Expires` are present, `Max-Age` takes precedence per the standard. |
| `Expires` | Expiration timestamp as an HTTP date/time | Clocks and browser policies can affect retention/deletion behavior. |

Example of a language preference cookie lasting one hour:

```http
Set-Cookie: lang=vi; Max-Age=3600; Path=/; Secure; SameSite=Lax
```

Example of a session cookie that page JavaScript cannot read directly:

```http
Set-Cookie: sid=unpredictableValue; Path=/; Secure; HttpOnly; SameSite=Lax
```

In local development over HTTP, cookies marked `Secure` may behave differently than in real HTTPS environments. Test in an appropriate environment and inspect the browser's actual headers and cookie store.

### 2.3. Session cookies vs. persistent cookies

- **Session cookies** usually have neither `Max-Age` nor `Expires`. The user agent may delete them when the browser session ends; browser session-restore features can keep them alive upon reopening.
- **Persistent cookies** have an explicit lifetime via `Max-Age`/`Expires`, yet can still be cleared by users, blocked by browsers, or constrained by privacy policies.
- **Cookie lifetime** and **server session lifetime** are two separate clocks. A cookie still existing on the client does not mean that session ID still exists or is still accepted by the server.

Deleting a cookie is usually done with `Set-Cookie` using the **matching name and Path/Domain scope**, plus `Max-Age=0` (or a past expiration date):

```http
Set-Cookie: sid=; Max-Age=0; Path=/; Secure; HttpOnly; SameSite=Lax
```

Setting `Max-Age=0` with a different `Path` or `Domain` than the original cookie may fail to delete the intended cookie. For login cookies, **deleting the cookie only on the client side is insufficient**: the server must also invalidate the session or revoke the token by design.

### 2.4. “Origin” differs from “site”: a common source of confusion

An **origin** is typically defined by *scheme + host + port*: `https://app.example.com:443` and `https://app.example.com:8443` are different origins. The **site** concept used by SameSite is built from scheme and registrable domain per browser rules: `https://app.example.com` and `https://api.example.com` can be the same site, even though they are different origins.

Implications:

- Cookies **are not isolated by port** like origins are. Two applications on different ports of the same host must be very careful with cookie names and scopes.
- CORS primarily governs whether JavaScript on one origin may read cross-origin responses, and whether certain requests may be sent by the browser; CORS **is not a resource authorization system**.
- `SameSite` considers site relationships, not just origin relationships. Two subdomains on the same site can still pose CSRF risks if trusted too broadly.
- Configuring `Domain` and `Path` only affects when cookies are sent, not server-side data read permissions or endpoint access rights.

Prefer host-only cookies for sessions when subdomain sharing is unnecessary. In browsers supporting cookie prefixes, names starting with `__Host-` require `Secure`, `Path=/`, and **no `Domain`**; `__Secure-` requires `Secure`. Prefixes add configuration enforcement, not authentication/authorization.

## 3. How Do Server-Side Sessions Work?

Example of a common session model:

```text
First time:
Browser -- POST /preferences (no sid yet) --> Spring MVC
                                     │
                          session store generates random ID
                                     │
Browser <-- Set-Cookie: JSESSIONID=abc... -----┘

Next time:
Browser -- Cookie: JSESSIONID=abc... --> Spring MVC
                                      │
                         look up ID abc... in session store
                                      │
                         read / write session attributes
```

**A session ID is a lookup key**, not where all user information must live. With standard Servlet `HttpSession`, state is kept server-side as attributes like `language=vi` or `cartId=...`. Internal storage depends on the container, configuration, and session store. Spring MVC builds on the Servlet API; Spring Session is an optional addition to manage/store sessions across external backends.

A session typically has three key lifecycle points:

1. **Creation**: when the application genuinely needs to store state; in Servlet, `request.getSession(true)` can create a new one if none exists.
2. **Use/renewal**: requests carrying a valid ID are associated with the session; inactivity timeout rules are determined by the container/session infrastructure.
3. **Expiration or invalidation**: inactivity timeout, logout, invalidation, or removal from the session store causes the old ID to stop pointing to a valid session.

Do not treat `JSESSIONID` as meaning "user is logged in". An unauthenticated guest session can still exist; upon login, the application must bind the session to the proper principal and authentication lifecycle.

### 3.1. Why must session IDs be unpredictable?

If a session ID is guessed, stolen, or forced upon a user, an attacker can use it to access the same session when the server relies solely on the ID. Therefore:

- Generate IDs using the framework/container's secure mechanism; never invent them from timestamps, user IDs, or counters.
- Always prefer HTTPS/TLS; authentication cookies should have `Secure`, `HttpOnly`, and an appropriate `SameSite`.
- Upon login or privilege elevation, **rotate/change the session ID** to prevent session fixation. Servlet provides `HttpServletRequest.changeSessionId()`; Spring Security also provides session fixation protection when properly configured.
- Expire and invalidate the server-side session on logout. Set an appropriate inactivity timeout, and consider an absolute lifetime limit when required by business policy.
- Never put session IDs in URLs, public access logs, analytics, or error messages. URLs can leak via history, referrers, bookmarks, and logs.
- Protect against XSS: `HttpOnly` restricts script access to cookies, yet XSS can still perform actions in the user's context or read page data.

If users need to stay logged in long-term ("remember me"), that is typically a separate token/lifecycle management mechanism rather than extending session lifetime indefinitely.

### 3.2. Server-signed cookies vs. server-side sessions

Not every cookie with "session" in its name holds a lookup ID. There are three common designs:

| Design | What the client holds | Does the server store matching state? | What must be verified? |
| --- | --- | --- | --- |
| Server-side session | Random ID | Yes, in memory or a session store | ID validity, expiration/non-revocation, current permissions |
| Cookie containing signed/MACed data | Data and signature | Not necessarily per session | Signature, expiration, audience/meaning, revocation handling if needed |
| Token like JWT in a cookie | Token containing claims | Not necessarily per request | Signature/algorithm, issuer, audience, expiry, permissions, and revocation policy |

**Signatures/MACs protect integrity, not confidentiality**: anyone holding the cookie can still read unencrypted data. Encryption and signing serve different needs. Tokens carrying claims do not make HTTP stateful; they are a way to transmit state/authentication info on each request.

Deciding whether to place a token in a cookie or in `Authorization: Bearer ...` affects how browsers attach credentials and the threat model. Cookies are sent automatically under matching rules and thus require CSRF evaluation; JavaScript-attached tokens change the CSRF mechanics while requiring protection of token storage against XSS.

## 4. Practical Limits of State Over HTTP

### 4.1. Cookies have size and lifecycle limits

Cookies are unsuitable as a large data store. Browsers enforce limits on individual cookie size, cookies per domain/site, and total storage, though exact numbers **vary by browser and version**. A rule of thumb is to keep each cookie small (typically around a few kilobytes or less) and avoid stuffing a full shopping cart or user profile into cookies.

Matching cookies are sent on **many requests**, even requests that do not need that data, increasing header size and transmission overhead. A short session ID is usually better than cramming large payloads into cookies.

Cookies can be deleted or rejected, users may browse in private mode, use multiple devices, switch browsers, or block third-party cookies. **Cookies are neither permanent storage** nor unique identifiers of a human being.

### 4.2. Server-side sessions introduce scaling challenges

With a server storing sessions in RAM:

```text
Browser -- sid=abc --> Load Balancer
                          ├── Node A: has session abc
                          └── Node B: does not have session abc
```

If the next request routes to Node B, state in Node A's RAM may not be found. Common options:

- **Sticky sessions**: the load balancer attempts to route a client's requests to the same instance; easy to start with, but risky when instances fail/replace and harder to balance load.
- **Shared/distributed session store**: multiple instances access a shared session store (such as Redis via mechanisms like Spring Session), requiring attention to TTL, latency, serialization, consistency, and security.
- **Stateless authentication**: each request carries a verifiable token; reduces the need to store login sessions, though immediate logout/early revocation, permission changes, or leaked tokens introduce other trade-offs.
- **Persist business data in a database**: carts, orders, and important events should generally have their own durable identifiers and storage, rather than living solely in an expiring session.

A shared session store does not automatically make every operation **atomic**. Two concurrent requests can read and overwrite an attribute, causing a lost update. When consistency matters, use transactions, atomic updates, versioning, or appropriate synchronization.

### 4.3. Sessions do not replace databases or authorization

Sessions are for short-lived state, and should not become a dumping ground for all business data:

- Orders must survive session expiration; the session might hold only a `cartId` key.
- Prices, roles, permissions, or payment status must be verified server-side at action time; never trust a client-supplied string.
- Sessions do not guarantee "one tab per user": multiple tabs in the same browser/profile usually share cookies/sessions; changes in one tab can affect another.
- Sessions do not guarantee "one device per user": different browsers or devices get separate session IDs.
- Session timeouts are usually inactivity-based; you may also need absolute expiration, concurrent session limits, or logout-all-devices mechanisms as required.

## 5. Cookies, CSRF, XSS, and Trust Boundaries

### 5.1. CSRF arises when credentials are sent automatically

If a browser automatically attaches a session cookie to a request, a malicious page can try to make the user's browser send a request to the logged-in application. That is a source of **cross-site request forgery (CSRF)** risk when an endpoint accepts sensitive actions without proper protection.

Bad example: `/transfer?amount=1000` transferring money via GET just because the browser holds a session cookie. GET is expected to be **safe** under HTTP semantics; meaningful business state changes must not be placed on GET.

Measures commonly combined:

1. Use HTTP methods properly: GET/HEAD for reads only; POST/PUT/PATCH/DELETE for mutations.
2. Use a **CSRF token** or framework-supported equivalent for vulnerable actions; do not treat `SameSite` as the sole defense layer.
3. Configure `SameSite` appropriately and check `Origin`/`Referer` where suitable.
4. Avoid enabling `Access-Control-Allow-Credentials: true` with arbitrary origins; allow only genuinely needed origins and validate server-side. CORS does not replace authentication/authorization.
5. Do not assume every `Content-Type: application/json` request is automatically immune to CSRF; browser behavior, preflights, supported endpoint content types, and other vectors must be evaluated.

**CSRF differs from XSS**: CSRF exploits automatic credential sending by the browser; XSS executes malicious script in the page's context. Applications may need defenses against both.

### 5.2. `HttpOnly`, `Secure`, and `SameSite` address different threats

- `HttpOnly` restricts JavaScript from reading cookies; it **does not** stop the browser from sending cookies on requests.
- `Secure` restricts cookie transmission over insecure connections; it **does not** encrypt cookie values or make them trustworthy if modified on the client.
- `SameSite` limits certain cross-site cookie transmissions; it **does not** replace CSRF tokens/authorization checks, especially for same-site scenarios or other vulnerabilities.
- TLS encryption protects data **in transit**; it does not prevent cookie leaks via logs, XSS session hijacking, malware, misconfigurations, or server compromise.
- **Authentication** establishes who is accessing; **authorization** establishes whether that account may perform a specific action. A valid session never permits skipping per-resource authorization checks.

In production, configure cookie policies, timeouts, CSRF, CORS, and logout alongside a Spring Security configuration suited to your login flow. Never rely on a single controller annotation to declare an endpoint secure.

## 6. Spring MVC Example: Storing Preferences with HttpSession

This example demonstrates the boundary clearly: the first request creates a session and stores `language`; subsequent requests use the cookie carrying the session ID to read the stored value. This is an exercise on session mechanics, **not a login or authorization implementation**.

Requirements: **JDK 17+**, **Spring Boot 3.x** with the `spring-boot-starter-web` dependency (Spring MVC on the `jakarta.servlet` Servlet API). Place the following file at `src/main/java/demo/session/SessionDemoApplication.java` inside a configured Spring Boot project. This is a **complete application file when Spring Boot dependencies are present**, not a program compilable with plain `javac` without libraries.

```java
package demo.session;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
public class SessionDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(SessionDemoApplication.class, args);
    }
}

@RestController
@RequestMapping("/api")
class PreferenceController {
    record PreferenceInput(String language) {}
    record PreferenceOutput(String language) {}

    @PostMapping("/preference")
    ResponseEntity<Void> save(
            @RequestBody PreferenceInput input,
            HttpServletRequest request) {
        if (input == null ||
                (!"vi".equals(input.language()) &&
                 !"en".equals(input.language()))) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "language must be vi or en");
        }

        HttpSession session = request.getSession(true);
        session.setAttribute("language", input.language());
        return ResponseEntity.noContent().build();
    }

    @GetMapping("/preference")
    PreferenceOutput read(HttpServletRequest request) {
        HttpSession session = request.getSession(false);
        String language = session == null
                ? null
                : (String) session.getAttribute("language");
        return new PreferenceOutput(language == null ? "vi" : language);
    }

    @DeleteMapping("/session")
    ResponseEntity<Void> signOutOfDemoSession(HttpServletRequest request) {
        HttpSession session = request.getSession(false);
        if (session != null) {
            session.invalidate();
        }
        return ResponseEntity.noContent().build();
    }
}
```

**Key points explained:**

- `getSession(true)` retrieves an existing session or creates a new one. The container typically responds with `Set-Cookie: JSESSIONID=...` when sending the ID for the client to reuse.
- `getSession(false)` only returns an existing session, or `null` if none exists. GET does not accidentally create a session.
- `setAttribute("language", ...)` stores data in the server-side session; the cookie typically contains only the session ID, **not `language=en`**.
- `invalidate()` destroys the server-side session. The browser may still retain the cookie holding the old ID, yet that ID can no longer access the old session.
- POST returns `204 No Content`, GET returns JSON with status 200, and DELETE returns 204. These statuses are specified by the controller or chosen by Spring MVC per mapping rules.
- Two concurrent requests writing the same attribute on the same session can **overwrite each other**; the example does not handle update conflicts. Complex business scenarios require concurrency and data consistency design.
- This DELETE endpoint illustrates session invalidation; in a real application with login cookies, it must integrate Spring Security, CSRF defense, and a proper logout flow.

### 6.1. Verifying with curl and a cookie jar

Suppose the application runs at `http://localhost:8080`. The following command examples use Bash shell syntax; on Windows PowerShell, invoke `curl.exe` and adjust JSON quoting if needed.

**A. GET without sending cookies** — no session exists yet, so the default is returned:

```bash
curl -i http://localhost:8080/api/preference
```

Equivalent response body:

```json
{"language":"vi"}
```

**B. POST creates a session**, saving the cookie returned by the server to `cookies.txt`:

```bash
curl -i -c cookies.txt -X POST \
  http://localhost:8080/api/preference \
  -H 'Content-Type: application/json' \
  -d '{"language":"en"}'
```

Expected status: `204 No Content`. In a typical Servlet setup, the response upon creating a session includes a header similar to:

```http
Set-Cookie: JSESSIONID=<server-generated-ID>; Path=/; HttpOnly
```

The cookie name, security flags, and other attributes **depend on configuration/HTTPS/container**. The line above is illustrative only, not an invariant output across every environment.

**C. GET with cookie jar** — curl sends the saved cookie:

```bash
curl -i -b cookies.txt http://localhost:8080/api/preference
```

Equivalent body:

```json
{"language":"en"}
```

**D. GET without sending cookies** still yields:

```bash
curl -i http://localhost:8080/api/preference
```

```json
{"language":"vi"}
```

**E. Invalidate the session and retry the old cookie:**

```bash
curl -i -b cookies.txt -X DELETE http://localhost:8080/api/session
curl -i -b cookies.txt http://localhost:8080/api/preference
```

The DELETE command returns 204; the subsequent GET returns the default `{"language":"vi"}` even though curl may still send the old ID. That demonstrates **server-side invalidation**.

If using a different HTTP client, remember to distinguish "auto-persist cookies" mode from "stateless/no cookies" mode; do not mix results across modes and draw wrong conclusions.

### 6.2. Configuring cookies and timeouts in Spring Boot

Example **applicable only when deploying over HTTPS** with an appropriate Spring Boot Servlet session configuration, in `application.yml`:

```yaml
server:
  servlet:
    session:
      timeout: 30m
      cookie:
        http-only: true
        secure: true
        same-site: lax
```

Meaning:

- `timeout: 30m` sets the target session inactivity timeout per the underlying mechanism/container; it **does not guarantee** a hard 30-minute absolute lifetime for every session.
- `http-only` helps prevent scripts from directly reading the session cookie.
- `secure: true` requires the cookie to be sent over secure connections; on local HTTP consider a separate development config rather than silently disabling protection in production.
- `same-site: lax` restricts certain cross-site scenarios; depending on legitimate cross-site/login flows, the policy may need adjustment.

When using a reverse proxy with TLS termination, configure trusted scheme/forwarded-header recognition for the application. When using Spring Session or a custom cookie serializer, verify the actual configuration of that cookie/session manager; do not infer everything solely from a YAML snippet.

## 7. Failure Scenarios to Diagnose

| Symptom | Possible Causes | What to Check |
| --- | --- | --- |
| Every request starts a new session | Client not storing/sending cookie, `Secure` over HTTP, wrong Domain/Path, cookie blocked | Inspect `Set-Cookie` response, `Cookie` request, URL, and DevTools cookie jar |
| Cookie exists but session seems lost | Session expired, server restarted, load balancer switched instances, session store error, invalid ID | Check session store/TTL, routing, and logs with IDs masked |
| CORS error on fetch with cookies | Origin not allowed, mismatched credentials/cookie policy | Configure specific origin, credentials, SameSite/Secure; inspect preflight |
| Still sees data after logout | Server did not invalidate, another token remains valid, browser cached data | Check credential invalidation/revocation, cache policy, and client data |
| Two tabs see the same preference | Both tabs share the same cookie/session | Revisit per-tab data design if separation is genuinely needed |
| Session ID leaked | Logs, URLs, XSS, or insecure channel | Remove IDs from logs/URLs, enforce TLS, cookie flags, rotation, revocation |
| GET accidentally creates many sessions | Calling `getSession()` instead of `getSession(false)` in read-only flows | Audit session creation points and `Set-Cookie` responses |
| Session store grows too large | Storing oversized objects, overly long timeouts, ineffective cleanup | Store only necessary attributes; monitor TTL/capacity |
| Cross-site request sometimes sends cookie, sometimes not | Different origin/site, `SameSite`, browser policy, HTTPS, or navigation conditions | Analyze request context and individual browser policies |

Do not use "seeing the cookie in DevTools" as proof that the server received it properly: inspect the **actual request header** and cross-check expiration, scope, and the session store.

## 8. Common Misconceptions

1. **“HTTP is stateless, so Spring cannot have sessions.”** False: stateful sessions are an application-layer mechanism linking requests by ID.
2. **“A cookie is a session.”** False: a cookie is a client-side mechanism for storing/sending data; a session is a state and lifecycle management mechanism that may or may not use cookies.
3. **“An `HttpOnly` cookie cannot be abused.”** False: browsers still send cookies automatically; XSS can still trigger actions, and CSRF must still be addressed.
4. **“Setting `Secure` encrypts the cookie.”** False: `Secure` restricts the transport channel; it does not encrypt the value stored on the client.
5. **“CORS blocks all external requests to the API.”** False: CORS is a browser policy, not server-side authorization; non-browser clients can call APIs on their own terms.
6. **“Every cookie lives for the exact configured number of seconds.”** False: browsers can delete or block them; server-side sessions also have their own expiration.
7. **“Each tab has an independent session.”** False under the standard cookie model within the same browser profile/site; multiple tabs usually share a session.
8. **“Sticky sessions guarantee state is never lost.”** False: instance crashes or redeployments can still lose in-RAM session data.
9. **“JWT is always better than server sessions.”** No universal conclusion: tokens reduce session lookups in some designs, yet make immediate revocation and permission updates harder.
10. **“Deleting the cookie is enough to log out.”** False for server-side sessions; the old ID must be invalidated on the server, authentication state ended, and related tokens handled.
11. **“There is only one session per user.”** Not necessarily; each device/browser can have its own session, and one browser can hold multiple sessions depending on domains or application design.
12. **“SameSite and CORS are the same thing.”** False: SameSite governs certain cookie-sending conditions; CORS governs certain cross-origin browser interactions.

## 9. Self-Check Questions and Application

1. **Without cookies:** Why are two requests from the same laptop insufficient for the server to identify the same session? Describe a design using `Authorization` instead of cookies.
2. **Cookie without session:** The browser sends `Cookie: JSESSIONID=abc`, yet the session store no longer has `abc`. Can the server infer the user is still logged in? Why?
3. **Cookie scope:** Does `Path=/admin` prevent JavaScript at `/` from accessing all admin endpoints, or replace authentication? Distinguish cookie scope from authorization.
4. **Expiration:** Why does `Max-Age=3600` not mean the server keeps the session valid for exactly one hour? To enable immediate logout across all devices, what state must be managed?
5. **Security:** For a login cookie, explain the distinct roles of `Secure`, `HttpOnly`, `SameSite`, and a CSRF token. Which does not replace authorization checks?
6. **Scaling:** If a session lives in Node A's RAM while a request lands on Node B, what happens? Compare sticky sessions with a shared session store.
7. **Practice:** Run the example in section 6, inspect `Set-Cookie` and `Cookie`; then DELETE the session and try GET with the old cookie. Point out which data lives on the client and which lives on the server.
8. **Design:** For UI language, a shopping cart, and paid orders, would you choose a small cookie, a session attribute, or a durable database? Explain what happens when the browser clears cookies or the session expires.

**Key takeaway:** HTTP does not maintain sessions on its own; cookies are a client-side transport/storage mechanism with scope and lifetime; sessions are an application mechanism binding requests to state. A well-built web application must simultaneously address **identity, access control, session lifecycle, CSRF/XSS risks, browser limits, and multi-server scaling consistency**. Understand these boundaries before implementing login, session management, or Spring Security.
