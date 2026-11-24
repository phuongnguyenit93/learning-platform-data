# Diagnosing Lost Sessions, Unsent Cookies, and Wrong-Protocol Redirects

**Module:** Spring Boot - web-runtime  
**Parent topic:** Debugging and Upgrades

## 1. The Problem: Login Succeeds, Then the User Is Immediately Logged Out

A Spring Boot service is moved from direct HTTP behind a Kubernetes Ingress at public URL **`https://app.example.test/portal/`**. After the upgrade, users hit these symptoms:

- `POST` login returns 200 or 302, yet accessing the next page prompts for login again.
- The login response carries **`Set-Cookie: JSESSIONID=...`**, yet the next request lacks **`Cookie: JSESSIONID=...`**.
- The cookie reaches the backend, yet the application finds no **`HttpSession`**.
- The `HttpSession` exists, yet Spring Security does not restore **`Authentication`**.
- An HTTPS browser receives **`Location: http://internal:8080/login`**, or gets caught in an HTTPS → HTTP → HTTPS loop.
- The bug happens only when load-balanced to a different pod, or after a restart / rolling upgrade.
- The frontend sends `fetch` to a different-origin API; the server has a session, yet the browser does not preserve credentials.

This is not a single bug. To fix it properly, find the **first broken step** in the HTTP flow: server creates session → response sets cookie → browser stores → browser sends → backend finds session → framework restores authentication → redirect targets the right public URL.

**Goal:** isolate the root cause yourself instead of disabling CSRF, dropping `Secure` cookies, or blindly enabling `SameSite=None`.

This lesson uses **Spring Boot 3.3**, Servlet/Spring MVC, Spring Security 6, Java 17+, cookies, and reverse proxies. The main Java example is an `HttpSession` lab without real login integration so transport bugs are isolated from authentication. Security/Redis explanations are supplementary guidance, not claims that those dependencies are already included in the lab.

## 2. Splitting the Symptom into Six Layers to Investigate

~~~text
Browser GET/POST public HTTPS
       |
       v
[1] Does login response include Set-Cookie?
       |
       v
[2] Does browser store the cookie?
       |
       v
[3] Does next request send Cookie per URL/policy?
       |
       v
Ingress / proxy TLS termination, path rewrite
       |
       v
[4] Does backend find server-side HttpSession?
       |
       v
[5] Are SecurityContext/Authentication restored?
       |
       v
[6] Does redirect Location have the right scheme/host/prefix?
~~~

| Layer | What to check | If wrong, inspect |
| --- | --- | --- |
| Response cookie | Is **`Set-Cookie`** present and valid? | Session never created, stateless policy, headers altered by proxy. |
| Cookie storage | Did the browser accept the cookie? | Wrong `Domain`, `SameSite=None` without `Secure`, third-party blocking. |
| Cookie sending | Does the request carry **`Cookie`**? | `Path`, host/domain, `Secure`, `SameSite`, `fetch` credentials. |
| Session lookup | Is `getSession(false)` null? | Expired, logged out, different pod, Redis/replication, ID rotation. |
| Authentication | Session exists yet still 401/302 login? | `SecurityContextRepository`, `SecurityFilterChain`, roles, fixation. |
| Redirect URL | `Location` uses HTTP/internal host/missing prefix? | Forwarded headers, context path, TLS termination, ingress rewrite. |

**Separate two situations clearly:**

1. **Browser does not send the cookie:** do not jump straight to checking Redis or Spring Session, because the request never carried the lookup key.
2. **Browser sends the cookie:** do not tweak `SameSite`/`Path` before inspecting session validity, storage, and Spring Security auth.

An HTTP status **`302`**, **`401`**, or **`403`** by itself does not pinpoint the cause. `302` can be an auth entry point or canonical redirect; `401` can be missing auth; `403` can be CSRF or authorization failure.

## 3. `HttpSession`, `JSESSIONID`, and `SecurityContext` Are Not the Same Thing

**`HttpSession`** is server-side Servlet state. **`JSESSIONID`** is the default cookie name Servlet containers typically use to carry an opaque session identifier. The cookie holds only a lookup key, **not a password**, and the cookie's existence in the browser does not guarantee the server-side session still exists.

**Spring Security `Authentication`/`SecurityContext`** represents authenticated state. In a stateful app, it can be stored inside `HttpSession` via **`SecurityContextRepository`**. However, not every `HttpSession` holds an authenticated user; an anonymous client with a shopping-cart session still has a session.

**JWT/Bearer** or a **`SessionCreationPolicy.STATELESS`** API may not use `HttpSession` for authentication at all. Confirm your auth architecture before debugging `JSESSIONID`.

Servlet APIs:

~~~java
// Illustrative snippet with request of type HttpServletRequest.
HttpSession current = request.getSession(false);
~~~

**`getSession(false)`** never creates a new session; it returns `null` if no valid session exists. Conversely:

~~~java
HttpSession existingOrCreated = request.getSession(true);
~~~

can create a new session and emit a new cookie. **Use `getSession(false)` in diagnostic endpoints**, because accidentally creating a session while inspecting destroys evidence of the original failure.

**Never log `HttpSession.getId()`, raw `JSESSIONID`, or `request.getHeader("Cookie")`**, even at DEBUG level. A session ID is a bearer-like credential: anyone obtaining it may hijack the session if replay defenses are absent.

### Session Fixation and `SessionFixation`

**Session fixation** is an attack class where an attacker fixes a known session ID and tricks a victim into logging in with it. Spring Security normally defends by rotating the session ID upon successful authentication, such as **`changeSessionId()`** on modern Servlets. Hence **`JSESSIONID` changing after login can be right**, not a bug. Verify that the browser stored the new ID and sent it on the subsequent request.

Logout may invalidate the server-side session while the browser retains the old cookie briefly. A stale `JSESSIONID` keeps getting sent and is rejected as invalid by the server. To clear it cleanly, expire the cookie with the **exact `Path` and `Domain`**, or use an appropriate logout handler; do not assume `invalidate()` deletes browser cookies automatically.

## 4. `Set-Cookie` Is a Response Header; `Cookie` Is a Request Header

Response:

~~~http
HTTP/1.1 200 OK
Set-Cookie: JSESSIONID=REDACTED; Path=/portal; Secure; HttpOnly; SameSite=Lax
~~~

Next request:

~~~http
GET /portal/profile HTTP/1.1
Host: app.example.test
Cookie: JSESSIONID=REDACTED
~~~

**`REDACTED`** is an illustrative placeholder. When the browser sends the `Cookie` request header, it does not resend `Path`/`SameSite`/`Secure`/`HttpOnly` attributes; the browser already evaluated those rules before choosing which cookies to attach.

Do not conflate:
- Server sent `Set-Cookie`.
- Browser **accepted/stored** the cookie.
- Browser **sent** the cookie on the next request.
- Backend **looked up** the matching server-side session.
- Spring Security restored `Authentication`.

These are five independent events requiring separate evidence.

**HTTP redirects can also carry `Set-Cookie`.** For form logins or OAuth2 callbacks, inspect every **`302`/`303`** response, not just the final response of a redirect chain.

**`HttpOnly`:** `document.cookie` will not display `JSESSIONID` when `HttpOnly` is set. That is proper protection; it does not block the browser from sending the cookie over HTTP. **`Set-Cookie`** is also a forbidden response header in browser Fetch APIs; **`response.headers.get("set-cookie")`** is not a reliable way to inspect it. Use DevTools Network/Storage and subsequent requests.

## 5. Cookie Attributes Table and Common Pitfalls

| Attribute | Controls | Symptom when wrong |
| --- | --- | --- |
| **Name** | `JSESSIONID` or custom name | Client keeps old name; multiple cookies under old/new names. |
| **Domain** | Which hostnames receive the cookie | Cookie set on internal host or domain mismatching public host. |
| **Path** | Which public request paths receive the cookie | Public `/portal` yet cookie has `Path=/internal`. |
| **Secure** | Sent over HTTPS only, with browser exceptions for localhost | Redirect to HTTP drops the `Secure` cookie. |
| **HttpOnly** | Blocks JavaScript from reading the cookie | JS cannot see the cookie even though the browser sends it properly. |
| **SameSite=Strict** | Strictly restricts cross-site contexts | Callbacks/navigations from external sites omit the cookie. |
| **SameSite=Lax** | Allows same-site and certain top-level safe navigations | Cross-site `fetch`, iframes, or POST callbacks may omit it. |
| **SameSite=None** | Allows cross-site per browser policy | Requires `Secure`; third-party cookie policies may still block it. |
| **Max-Age/Expires** | Client-side cookie persistence | Cookie expires before server session, or outlives server session. |
| **Partitioned** | Cookie partitioning per browser support | Third-party context behavior differs from unpartitioned cookies. |

**Cookie `Path` is not a strong security boundary**, and **`Domain` never includes a port**. `SameSite` is a **site** concept, not strictly identical to **origin**; origin comprises scheme, host, and port. Two subdomains of the same registrable domain can be same-site yet cross-origin.

### `Domain`: Host-Only Is Usually Simpler and Safer

If the public app is at **`app.example.test`** and no `Domain` attribute is set, the cookie is host-only for `app.example.test`. Never set **`Domain=internal-service`** just because the app runs behind a proxy; the browser never sees that internal hostname.

~~~http
Set-Cookie: JSESSIONID=REDACTED; Domain=example.test; Path=/; Secure
~~~

can span matching subdomains, widening scope; use only when business requirements genuinely demand it. If the app changes hostnames after an upgrade, host-only cookies from the old hostname will not carry over to the new host.

**Never use `Domain=app.example.test:8080`** because cookie domains do not accept ports. For localhost and IPs in labs, leaving host-only default causes far fewer surprises than setting `Domain` manually.

### `Path`: Must Match the URL the Browser Sees

Example:

~~~text
Browser: https://app.example.test/portal/dashboard
Proxy:   strip /portal
Backend: http://service:8080/dashboard
~~~

If the backend emits **`Path=/internal`**, the browser will not send the cookie to **`/portal/dashboard`**. You can configure:

~~~properties
server.servlet.session.cookie.path=/portal
~~~

if the cookie should be scoped to public `/portal`, or **`Path=/`** if host-wide policy requires it. **Never set `Path` to the upstream `/dashboard` route** when the browser visits `/portal/dashboard`.

When changing `Path`, browsers may still hold an old `JSESSIONID` at `Path=/` or `/internal`; if they share the same name, handle migration/cookie cleanup explicitly for the exact `Domain` and `Path` rather than wiping unrelated cookies.

### `Secure`: Never Disable It to Work Around HTTPS Mistakes

Public production:

~~~text
Browser --HTTPS--> Ingress --HTTP--> Spring Boot
~~~

can still use **`Secure`** cookies: the browser only ever sees public HTTPS. If the backend mistakenly thinks external traffic is HTTP and redirects the browser to `http://`, the `Secure` cookie will not be sent. **Fix the forwarded scheme and public redirects**, instead of flipping `Secure` to `false` in production.

**Localhost exception:** browsers may treat `Secure` differently on `localhost`; `curl` and Java `HttpClient` do not emulate every browser exception. Do not treat `localhost` results as proof for real HTTPS environments.

## 6. `SameSite`, `fetch` Credentials, and CORS Are Three Distinct Mechanisms

In the browser:

~~~javascript
const result = await fetch(
  "https://api.example.test/portal/api/me",
  { credentials: "include" }
);
console.log(result.status);
~~~

**Fetch `credentials`:**

- **`omit`**: does not send credentials, nor accept/store `Set-Cookie` per Fetch credential rules.
- **`same-origin`**: default; sends credentials only on same-origin requests.
- **`include`**: allows cross-origin credentials, yet **cannot bypass** `Domain`/`Path`/`Secure`/`SameSite` or browser privacy rules.

If the frontend is **`https://app.example.test`** and the API is **`https://api.example.test`**, they are two distinct origins even though they may be same-site. Default `same-origin` fetch will not send cookies to the API; `credentials: "include"` is required **when permitted by the API contract**.

For credentialed cross-origin fetch, the server must return:

~~~http
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Credentials: true
Vary: Origin
~~~

**`Access-Control-Allow-Origin: *`** cannot be paired with credentialed CORS. The server must allowlist `Origin`, never echo arbitrary `Origin`s blindly. Preflight `OPTIONS` requests usually omit credentials; check both the preflight and the actual request/response.

**`SameSite=None; Secure`** is often required if the app intentionally sends cookies in cross-site requests, though it still does not guarantee third-party cookies are allowed. Browsers may block them via privacy policies, storage partitioning, or user settings. Always read **Blocked Reason** in DevTools.

**Never rely on `SameSite=None` in place of CSRF defenses.** Cross-site cookie delivery opens extra CSRF paths; cookie-authenticated endpoints need proper CSRF protection or explicit API design. If a cross-origin POST throws a CORS error, the request may already have reached the server; never retry a payment POST just because JavaScript was blocked from reading the response.

### OAuth2/OIDC Callbacks

The authorization-code flow often uses a top-level GET redirect from the identity provider back to the app; `SameSite=Lax` generally allows those top-level navigations. However, iframes or **`form_post`** callbacks obey stricter rules. Alongside `JSESSIONID`, inspect state/correlation cookies, redirect URIs, sessions, and browser blocked reasons. Never switch all cookies to `SameSite=None` just to force one login flow green.

## 7. Cookie Reached the Server, Yet `HttpSession` Is Still Missing

If a request carries **`Cookie: JSESSIONID=...`** yet **`request.getSession(false) == null`**, check:

- Server-side **idle timeout**; the cookie may persist in the browser longer.
- Logout or application calling **`session.invalidate()`**.
- Browser sent an old cookie ID before ID rotation/login finished.
- Cookie name or session namespace changed.
- Pod scaled down / restarted, wiping in-memory sessions.
- Load balancer routed the next request to **pod B** while the session only lives in **pod A**'s RAM.
- Shared session store (Redis/JDBC) suffered an outage, TTL expiration, or deserialization failure.
- Rolling upgrade left new servers unable to deserialize attributes written by the previous version.
- Another container/app on the same domain/path overwrote `JSESSIONID` with the same name.
- Sticky-session config was dropped when switching Ingress Controllers.

**`server.servlet.session.timeout=30m`** is the server-side idle timeout, not cookie `Max-Age`. A session cookie without `Max-Age` remains in the browser until closed, even after the server expires its state.

In Servlet APIs, **`request.isRequestedSessionIdValid()`** tells you whether the request's session ID is valid; never return the raw ID value to clients. `false` can mean either no ID was sent or the ID wasn't found, so combine it with browser Network evidence without logging raw credentials.

**Never call `getSession(true)` in a diagnostic endpoint**, as it immediately creates a fresh session and hides evidence of the invalid previous session.

## 8. Lost Sessions Across Multiple Replicas and Spring Session Redis

Failure pattern:

~~~text
POST /login -> Ingress -> Pod A
  Pod A stores HttpSession in RAM.

GET /profile (same JSESSIONID) -> Ingress -> Pod B
  Pod B does not have that HttpSession.
  -> 302 /login or 401.
~~~

**Sticky sessions** can route a client's requests to the same pod, yet they are not durable across pod restarts, HPA scale-downs, or failovers.

**Spring Session** backs `HttpSession` with a shared repository. With Redis, multiple pods share the same sessions. Corresponding Boot dependency:

~~~xml
<!-- Only add when the deployment genuinely has Redis and security controls. -->
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-session-data-redis</artifactId>
</dependency>
~~~

Illustrative config, **not runnable without a Redis server**:

~~~properties
spring.data.redis.host=redis.internal
spring.data.redis.port=6379
server.servlet.session.timeout=30m
~~~

You must also configure TLS/auth, Redis network policies, compatible Spring Session versions, TTL, key namespaces, serialization strategy, and capacity. Never store plaintext passwords/tokens in `HttpSession` or Redis, and keep session attributes compact.

**During rolling upgrades**, changing class names, `serialVersionUID`, JSON schemas, or attribute structures can render existing sessions unreadable. Neither `SameSite` nor cookie `Path` fixes that. Plan migration policies, backward-compatible serialization, or intentional re-login.

### Separating Session Storage Failures from Authentication Failures

An **`HttpSession`** can exist with app attributes while Spring Security still fails to restore `SecurityContext`. In Spring Security 6, custom auth handlers may need to save context explicitly via **`SecurityContextRepository`**. Inspect the `SecurityFilterChain` and repository instead of inferring auth solely from `sessionPresent`.

## 9. Spring Security 6 and Upgrade Behavior Changes

Spring Boot 3.x moved Servlet APIs from **`javax.servlet.*`** to **`jakarta.servlet.*`** (from Boot 2.x), and Spring Security 6 altered several session-management flows.

Common misconceptions:

1. Spring Security may rotate the session ID after login for SessionFixation protection. **ID rotation is expected security behavior**, not a lost session.
2. **`SecurityContextHolderFilter`** and **`SecurityContextRepository`** manage context persistence across requests. In custom auth code, setting only the `ThreadLocal` context without saving to the repository leaves the next request unauthenticated.
3. **`SessionManagementFilter`** is no longer wired by default across every auth flow in Spring Security 6; authentication mechanisms invoke their own strategies.
4. **`SessionCreationPolicy.STATELESS`** prevents creating sessions for auth even in a Servlet app.
5. `InvalidSessionStrategy` or `invalidSessionUrl` can redirect users carrying stale post-logout cookies.
6. A `403` after POST may be a CSRF failure rather than a missing cookie; inspect the CSRF token alongside session/context.
7. A new `SecurityFilterChain` config can alter login URLs, request matchers, and logout behavior, producing different 302/401s than before the upgrade.

Non-standalone **pseudocode illustration** for a custom auth handler:

~~~java
// Authentication auth = authenticationManager.authenticate(token);
// SecurityContext context = SecurityContextHolder.createEmptyContext();
// context.setAuthentication(auth);
// SecurityContextHolder.setContext(context);
// securityContextRepository.saveContext(context, request, response);
~~~

This snippet is not standalone compilable; it requires beans, imports, and an auth flow. It shows that you **must save the context** explicitly when framework policy requires it, rather than only populating `ThreadLocal`.

**Never disable CSRF or session fixation protection to silence an unverified bug.** Those weaken security and can mask unrelated problems. On logout, expire the session cookie with matching `Name`/`Path`/`Domain` or use Spring Security's built-in logout clearing and test on the real Servlet container.

## 10. Reverse Proxy Producing Wrong-Scheme Redirects

Suppose:

~~~text
Browser: https://app.example.test/portal/login
Ingress: HTTPS -> HTTP backend
Backend: http://session-service:8080/login
~~~

If the backend sees only HTTP and builds a redirect link, it may respond:

~~~http
HTTP/1.1 302 Found
Location: http://session-service:8080/login
~~~

When the browser follows that redirect, it leaves HTTPS, drops `Secure` cookies, mismatches host/path, and can enter a login loop.

Spring Boot 3.3 supports:

~~~properties
server.forward-headers-strategy=framework
~~~

A trusted reverse proxy forwards consistent metadata:

~~~http
Forwarded: proto=https;host=app.example.test
X-Forwarded-Host: app.example.test
X-Forwarded-Proto: https
X-Forwarded-Port: 443
X-Forwarded-Prefix: /portal
~~~

**`Forwarded`** is the RFC 7239 standard header; `X-Forwarded-*` are de facto headers. Never let `Forwarded` and `X-Forwarded-Host`/`Proto` contradict each other; the proxy must enforce a clear write/overwrite policy.

| Strategy | Meaning | When to use |
| --- | --- | --- |
| **`none`** | No Boot forwarded-header processing | No trusted proxy, or using a separate canonical public URL. |
| **`native`** | Uses Tomcat/Jetty/Netty native forwarding support | Often enough for `X-Forwarded-For`/`Proto` with a compatible proxy. |
| **`framework`** | Spring MVC `ForwardedHeaderFilter`; WebFlux `ForwardedHeaderTransformer` | Helpful when `X-Forwarded-Prefix` and URI/redirect generation are needed. |

With **embedded Tomcat** behind TLS termination, Spring Boot docs also highlight:

~~~properties
server.tomcat.redirect-context-root=false
~~~

so `X-Forwarded-Proto` is evaluated before context-root redirects. It **does not create HTTPS certificates** or fix URL rewrites at ingress.

### HTTP → HTTPS → HTTP Loop

~~~text
1. Browser GET https://app.example.test/portal
2. Proxy sends HTTP to backend
3. Backend thinks client used HTTP, redirects to http://app.example.test/portal
4. Proxy enforces HTTPS again
5. Browser returns over HTTPS, loop repeats
~~~

Capture every hop of the redirect chain using DevTools Preserve log or **`curl -i`** without following redirects. Never disable HTTPS enforcement to stop a loop; fix **`Forwarded` Proto and redirect URLs**.

### Never Skip the Trust Boundary

An attacker can forge **`X-Forwarded-Host: attacker.example`**. If the backend trusts it to build `Location` or OAuth callbacks, host-header poisoning or open redirects follow. **`ForwardedHeaderFilter` does not authenticate where headers came from**.

Internet-facing proxies must **strip or overwrite `Forwarded` and `X-Forwarded-*`** from untrusted clients and populate values from allowlisted virtual hosts/TLS/routes. Isolate the backend from direct public traffic using network policies, security groups, mTLS, or equivalent.

## 11. Context Path, Public Path, and Nginx Rewrites

Two common topologies:

| Topology | Public request | Backend request | `server.servlet.context-path` | Appropriate cookie `Path` |
| --- | --- | --- | --- | --- |
| **Preserve `/portal`** | `/portal/demo/session/status` | `/portal/demo/session/status` | `/portal` | `/portal` or `/` per policy |
| **Strip `/portal`** | `/portal/demo/session/status` | `/demo/session/status` | root | `/portal` or `/` per policy |

In strip mode, **`X-Forwarded-Prefix: /portal`** guides generated public URLs—it **does not add a Servlet context path**. If you strip `/portal` yet also set `server.servlet.context-path=/portal`, the backend receives `/demo/...` while expecting `/portal/demo/...` and returns 404.

Nginx lab illustrating prefix stripping:

~~~nginx
server {
    listen 8088;
    server_name localhost;
    location /portal/ {
        proxy_pass http://127.0.0.1:8080/;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Port $server_port;
        proxy_set_header X-Forwarded-Prefix /portal;
        proxy_set_header X-Forwarded-For $remote_addr;
    }
}
~~~

With **`location /portal/`** and **`proxy_pass http://127.0.0.1:8080/`** ending in a slash, Nginx swaps the matched prefix for `/`, so upstream receives `/demo/session/status`. Without a trailing URI slash in `proxy_pass`, the path is normally preserved. When using regex locations, variables, or rewrites, check Nginx semantics specifically.

**This snippet is for local HTTP labs only**, lacking TLS, host allowlists, and production reverse-proxy security. On real public HTTPS, forwarded proto must reflect the original HTTPS client connection, not internal HTTP.

If you cannot modify the backend's `Set-Cookie` `Path`, Nginx offers **`proxy_cookie_path`** to rewrite `Path`, though configuring the app directly and verifying the actual `Set-Cookie` is preferred. Avoid stacking overlapping rewrites; during migrations, browsers may hold same-named cookies at both old and new paths.

Kubernetes Ingress **`pathType: Prefix`** controls routing, not prefix stripping. `ingress-nginx` **`rewrite-target`** is controller-specific and not portable across all `IngressClass` or Gateway API implementations.

## 12. Spring Boot 3.3 Configuration by Environment

### Local Lab — HTTP Localhost, No Proxy

~~~properties
# application.properties
spring.application.name=session-diagnostics
server.port=8080

server.servlet.session.timeout=30m
server.servlet.session.tracking-modes=cookie
server.servlet.session.cookie.name=JSESSIONID
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.same-site=lax
server.servlet.session.cookie.secure=false

server.forward-headers-strategy=none
server.error.include-message=never
server.error.include-stacktrace=never
~~~

**`secure=false` is strictly for local HTTP labs**. In production HTTPS, keep `Secure=true`. Use **`server.servlet.session.tracking-modes=cookie`** to avoid falling back to URL rewriting (`;jsessionid`) in links or logs.

### Production Example — Edge HTTPS, Proxy Strips `/portal`

~~~properties
# application-prod.properties
server.servlet.session.timeout=30m
server.servlet.session.tracking-modes=cookie
server.servlet.session.cookie.name=JSESSIONID
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.secure=true
server.servlet.session.cookie.same-site=lax
server.servlet.session.cookie.path=/portal

# Backend uses root context because proxy strips /portal.
server.forward-headers-strategy=framework
server.tomcat.redirect-context-root=false

server.error.include-message=never
server.error.include-stacktrace=never
~~~

**Never copy the `prod` profile into a service lacking TLS, ingress, and authentication**. This is strictly a cookie/forwarded configuration example, not a complete security posture. `SameSite` must match your frontend/OAuth flows, `Path` must match the public URL, and `framework` strategy should only be enabled when the proxy sanitizes headers.

**Never rely on cookie `Max-Age` alone to keep users logged in.** Even if the cookie survives in the browser, an expired server `HttpSession` still drops auth.

## 13. Runnable Java 17+ Demo: `HttpSession` and Redirects

Goal: demonstrate that a client with a cookie jar keeps state while one without does not; invalidating the session clears state; and redirects emit public URLs when trusted forwarded metadata is present.

Structure:

~~~text
session-diagnostics/
  pom.xml
  src/main/java/com/example/sessiondiag/
    SessionDiagnosticsApplication.java
    SessionState.java
    SessionController.java
    LocalRequestViewController.java
  src/main/resources/
    application.properties
    application-prod.properties
  src/test/java/com/example/sessiondiag/
    SessionHttpTests.java
    SessionMvcTests.java
~~~

The demo has **no Spring Security**, passwords, database, or Redis. Never use it in place of production authentication. Illustrated Spring Boot version is **3.3.13**, Java 17+. For new projects, pick a currently supported Boot branch and re-run contract tests when upgrading.

### 13.1. `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.13</version>
    <relativePath/>
  </parent>
  <groupId>com.example</groupId>
  <artifactId>session-diagnostics</artifactId>
  <version>0.0.1-SNAPSHOT</version>
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
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
~~~

### 13.2. Main Class

File **`src/main/java/com/example/sessiondiag/SessionDiagnosticsApplication.java`**:

~~~java
package com.example.sessiondiag;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SessionDiagnosticsApplication {
    public static void main(String[] args) {
        SpringApplication.run(SessionDiagnosticsApplication.class, args);
    }
}
~~~

### 13.3. DTO

File **`src/main/java/com/example/sessiondiag/SessionState.java`**:

~~~java
package com.example.sessiondiag;

public record SessionState(boolean present, int visits) {
}
~~~

Do not include the session ID in the response body. `present` only indicates an **`HttpSession` exists**, not that a user is authenticated.

### 13.4. `SessionController.java`

~~~java
package com.example.sessiondiag;

import java.net.URI;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.support.ServletUriComponentsBuilder;

@RestController
@RequestMapping("/demo")
public class SessionController {

    private static final String VISITS = "visits";

    @PostMapping(value = "/session/start",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public SessionState start(HttpServletRequest request) {
        HttpSession session = request.getSession(true);
        session.setAttribute(VISITS, 1);
        return new SessionState(true, 1);
    }

    @GetMapping(value = "/session/status",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public SessionState status(HttpServletRequest request) {
        return view(request.getSession(false));
    }

    @PostMapping(value = "/session/visit",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public SessionState visit(HttpServletRequest request) {
        HttpSession session = request.getSession(false);
        if (session == null) {
            return new SessionState(false, 0);
        }
        Object previous = session.getAttribute(VISITS);
        int next = previous instanceof Integer n ? n + 1 : 1;
        session.setAttribute(VISITS, next);
        return new SessionState(true, next);
    }

    @PostMapping("/session/clear")
    public ResponseEntity<Void> clear(
            HttpServletRequest request) {
        HttpSession session = request.getSession(false);
        if (session != null) {
            session.invalidate();
        }
        return ResponseEntity.noContent().build();
    }

    @GetMapping("/redirect")
    public ResponseEntity<Void> redirect() {
        URI target = ServletUriComponentsBuilder
                .fromCurrentContextPath()
                .path("/demo/session/status")
                .build()
                .toUri();

        return ResponseEntity.status(HttpStatus.FOUND)
                .location(target)
                .build();
    }

    private SessionState view(HttpSession session) {
        if (session == null) {
            return new SessionState(false, 0);
        }
        Object stored = session.getAttribute(VISITS);
        int count = stored instanceof Integer n ? n : 0;
        return new SessionState(true, count);
    }
}
~~~

Explanation:

- **`POST /demo/session/start`** explicitly creates a session, causing the container to emit `Set-Cookie: JSESSIONID=...`.
- **`GET /demo/session/status`** reads with `getSession(false)`, creating nothing.
- **`POST /demo/session/visit`** increments state if a session is found. Real apps using cookie auth require CSRF protection on state-changing requests.
- **`POST /demo/session/clear`** invalidates and returns **`204 No Content`**. The old cookie may still sit in the browser.
- **`GET /demo/redirect`** returns **`302 Found`** with `Location` from the URI builder; when forwarded headers are processed, the URL reflects public scheme/host/prefix.
- State lives in JVM RAM, so restarts or routing to another pod without a shared store will lose the session.

### 13.5. Diagnostic Controller Enabled Only in the `local` Profile

File **`src/main/java/com/example/sessiondiag/LocalRequestViewController.java`**:

~~~java
package com.example.sessiondiag;

import java.util.Map;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.context.annotation.Profile;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@Profile("local")
@RestController
public class LocalRequestViewController {

    @GetMapping("/debug/request-view")
    public Map<String, Object> view(HttpServletRequest request) {
        return Map.of(
                "scheme", request.getScheme(),
                "secure", request.isSecure(),
                "host", request.getServerName(),
                "port", request.getServerPort(),
                "contextPath", request.getContextPath(),
                "requestedSessionIdValid",
                    request.isRequestedSessionIdValid(),
                "sessionPresent",
                    request.getSession(false) != null);
    }
}
~~~

The endpoint registers only under the **`local`** profile and never logs or returns session IDs. Even so, it reveals request host and proxy details, so never expose it on the Internet. In production, rely on reviewed instrumentation, metrics, and authenticated management endpoints instead of a public debug endpoint.

Create both **`application.properties`** and **`application-prod.properties`** as shown in section 12. You can run the `local` profile without an `application-local.properties`: `@Profile("local")` activates the diagnostic controller while base properties remain active.

## 14. Running the Lab with a `curl` Cookie Jar

With Java 17+ and Maven, inside the project directory:

~~~bash
mvn clean test
mvn spring-boot:run -Dspring-boot.run.profiles=local
~~~

In another terminal, without cookies:

~~~bash
curl -si http://127.0.0.1:8080/demo/session/status
~~~

Expected body:

~~~json
{"present":false,"visits":0}
~~~

### Create a Session and Save the Cookie

~~~bash
curl -si -X POST \
  -c session-cookies.txt \
  http://127.0.0.1:8080/demo/session/start
~~~

Expected body:

~~~json
{"present":true,"visits":1}
~~~

The response also includes `Set-Cookie` for `JSESSIONID`. **`session-cookies.txt`** holds demo credentials; never commit it to Git or paste it into support tickets. Never use real user sessions in lab experiments.

### Omit the Cookie Jar: Session Is Not Found

~~~bash
curl -si http://127.0.0.1:8080/demo/session/status
~~~

Expect **`present=false`**, because `curl` does not share cookies across invocations without a jar.

### Send the Cookie Jar: Session Is Recognized

~~~bash
curl -si -b session-cookies.txt \
  http://127.0.0.1:8080/demo/session/status
~~~

Expected:

~~~json
{"present":true,"visits":1}
~~~

Increment visits:

~~~bash
curl -si -X POST -b session-cookies.txt \
  http://127.0.0.1:8080/demo/session/visit
~~~

Expected:

~~~json
{"present":true,"visits":2}
~~~

### Invalidate

~~~bash
curl -si -X POST -b session-cookies.txt \
  http://127.0.0.1:8080/demo/session/clear
~~~

Expect **`204 No Content`** and empty body. Check status using the old cookie:

~~~bash
curl -si -b session-cookies.txt \
  http://127.0.0.1:8080/demo/session/status
~~~

Expect **`present=false`** because the server-side session was invalidated; the cookie jar may still hold the old credential, yet the server no longer recognizes that ID.

**Do not assume `curl -v` is safe on production:** verbose output prints real `Cookie`/`Set-Cookie` values. Always redact tokens and sensitive paths/queries before sharing logs with a team.

## 15. Testing Redirects With and Without Forwarded Headers

Local default strategy **`none`**:

~~~bash
curl -si http://127.0.0.1:8080/demo/redirect
~~~

Expect **`302 Found`**, `Location` pointing to the direct backend origin:

~~~http
Location: http://127.0.0.1:8080/demo/session/status
~~~

Stop the previous instance. Start locally with framework forwarded-header processing enabled:

~~~bash
mvn spring-boot:run \
  -Dspring-boot.run.arguments="--server.forward-headers-strategy=framework"
~~~

Send the test request:

~~~bash
curl -si \
  -H 'X-Forwarded-Host: app.example.test' \
  -H 'X-Forwarded-Proto: https' \
  -H 'X-Forwarded-Port: 443' \
  -H 'X-Forwarded-Prefix: /portal' \
  http://127.0.0.1:8080/demo/redirect
~~~

Expect **`302 Location`** with `scheme=https`, `host=app.example.test`, `path=/portal/demo/session/status`, and port `-1` or `443`. Illustrative response:

~~~http
HTTP/1.1 302
Location: https://app.example.test/portal/demo/session/status
~~~

**This is a synthetic local lab test**, not proof that real ingress sanitizes forwarded headers. Avoid **`curl -L`** when inspecting the first redirect response, because `-L` follows redirects automatically and can mask a bad `Location`.

When a public proxy strips **`/portal`** before forwarding to a root backend, `X-Forwarded-Prefix` lets Spring build external links accurately; **do not set `server.servlet.context-path=/portal`** because upstream no longer receives that prefix.

## 16. Integration Tests Over a Real Embedded HTTP Server

This test uses **`@SpringBootTest(RANDOM_PORT)`**, Java 17 **`HttpClient`**, and **`CookieManager`**. It tests session lifecycle at the HTTP connector, without pretending to emulate Chrome/Firefox `SameSite`, third-party cookie, or CORS policies.

File **`src/test/java/com/example/sessiondiag/SessionHttpTests.java`**:

~~~java
package com.example.sessiondiag;

import java.net.CookieManager;
import java.net.CookiePolicy;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = {
        "server.forward-headers-strategy=framework",
        "server.servlet.session.cookie.secure=false",
        "server.servlet.session.cookie.path=/"
    })
class SessionHttpTests {

    @LocalServerPort
    int port;

    private final ObjectMapper mapper = new ObjectMapper();

    private URI uri(String path) {
        return URI.create("http://127.0.0.1:" + port + path);
    }

    private HttpRequest get(String path) {
        return HttpRequest.newBuilder(uri(path))
                .timeout(Duration.ofSeconds(5))
                .GET().build();
    }

    private HttpRequest post(String path) {
        return HttpRequest.newBuilder(uri(path))
                .timeout(Duration.ofSeconds(5))
                .POST(HttpRequest.BodyPublishers.noBody())
                .build();
    }

    @Test
    void cookieStoreKeepsHttpSessionAcrossRequests()
            throws Exception {

        CookieManager cookies = new CookieManager();
        cookies.setCookiePolicy(CookiePolicy.ACCEPT_ALL);

        HttpClient withCookies = HttpClient.newBuilder()
                .cookieHandler(cookies).build();
        HttpClient withoutCookies = HttpClient.newHttpClient();

        HttpResponse<String> created = withCookies.send(
                post("/demo/session/start"),
                HttpResponse.BodyHandlers.ofString());

        assertEquals(200, created.statusCode());
        assertTrue(created.headers()
                .firstValue("set-cookie").isPresent());
        assertTrue(mapper.readTree(created.body())
                .path("present").asBoolean());

        HttpResponse<String> absent = withoutCookies.send(
                get("/demo/session/status"),
                HttpResponse.BodyHandlers.ofString());
        assertFalse(mapper.readTree(absent.body())
                .path("present").asBoolean());

        HttpResponse<String> existing = withCookies.send(
                get("/demo/session/status"),
                HttpResponse.BodyHandlers.ofString());
        assertTrue(mapper.readTree(existing.body())
                .path("present").asBoolean());

        HttpResponse<String> visit = withCookies.send(
                post("/demo/session/visit"),
                HttpResponse.BodyHandlers.ofString());
        JsonNode visited = mapper.readTree(visit.body());
        assertEquals(2, visited.path("visits").asInt());

        HttpResponse<String> cleared = withCookies.send(
                post("/demo/session/clear"),
                HttpResponse.BodyHandlers.ofString());
        assertEquals(204, cleared.statusCode());

        HttpResponse<String> after = withCookies.send(
                get("/demo/session/status"),
                HttpResponse.BodyHandlers.ofString());
        assertFalse(mapper.readTree(after.body())
                .path("present").asBoolean());
    }

    @Test
    void forwardedHttpsAndPrefixAffectRedirectLocation()
            throws Exception {

        HttpClient noRedirect = HttpClient.newBuilder()
                .followRedirects(HttpClient.Redirect.NEVER)
                .build();

        HttpRequest request = HttpRequest.newBuilder(
                uri("/demo/redirect"))
                .timeout(Duration.ofSeconds(5))
                .header("X-Forwarded-Host", "app.example.test")
                .header("X-Forwarded-Proto", "https")
                .header("X-Forwarded-Port", "443")
                .header("X-Forwarded-Prefix", "/portal")
                .GET().build();

        HttpResponse<String> response = noRedirect.send(
                request, HttpResponse.BodyHandlers.ofString());

        assertEquals(302, response.statusCode());
        URI location = URI.create(response.headers()
                .firstValue("Location").orElseThrow());

        assertEquals("https", location.getScheme());
        assertEquals("app.example.test", location.getHost());
        assertEquals("/portal/demo/session/status",
                location.getPath());
        assertTrue(location.getPort() == -1 ||
                location.getPort() == 443);
    }
}
~~~

**What is tested:** the same cookie jar retains the session while a cookieless client does not; invalidation destroys the session; 302 `Location` honors forwarded origin/prefix in the framework test context.

**What is NOT tested:** `SameSite`, browser cookie policies, CORS preflight, third-party blocking, real ingress path rewrites, or TLS certificates. Java `HttpClient` does not enforce all browser restrictions. Verify those via DevTools and end-to-end public URLs.

## 17. `MockMvc` Controller Tests Using `MockHttpSession`

File **`src/test/java/com/example/sessiondiag/SessionMvcTests.java`**:

~~~java
package com.example.sessiondiag;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(SessionController.class)
class SessionMvcTests {

    @Autowired
    MockMvc mvc;

    @Test
    void missingSessionDoesNotCreateOneOnStatus()
            throws Exception {
        mvc.perform(get("/demo/session/status")
                    .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.present").value(false))
                .andExpect(jsonPath("$.visits").value(0));
    }

    @Test
    void readsExistingMockSession() throws Exception {
        MockHttpSession session = new MockHttpSession();
        session.setAttribute("visits", 7);

        mvc.perform(get("/demo/session/status")
                    .session(session))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.present").value(true))
                .andExpect(jsonPath("$.visits").value(7));
    }

    @Test
    void clearReturns204() throws Exception {
        MockHttpSession session = new MockHttpSession();
        session.setAttribute("visits", 1);

        mvc.perform(post("/demo/session/clear")
                    .session(session))
                .andExpect(status().isNoContent());
    }
}
~~~

`MockMvc` opens no socket, so it does not test browser cookie handling. A real app with Spring Security requires **`spring-security-test`**, principals, and CSRF tokens in POST tests. The demo omits Security to isolate `HttpSession` mechanics.

Run from the project directory:

~~~bash
mvn clean test
~~~

Only conclude tests pass when real Maven exits with code 0 and executes the test classes. Code in this article is instructional material, not a claim that it was already built on the reader's machine.

## 18. DevTools: Gather Evidence Instead of Guessing

Step-by-step in Chrome/Edge/Firefox (menu names may vary by version):

1. Open **Network** before login, enable **Preserve log** to keep the 302 chain.
2. Select the login response and inspect **`Set-Cookie`**. Never copy or screenshare unredacted cookie values.
3. Inspect **Application/Storage → Cookies**: `Name`, `Domain`, `Path`, `Secure`, `HttpOnly`, `SameSite`, `Expires`/`Max-Age`.
4. Check **Issues / Blocked Reason** if a cookie was rejected; record the exact reason rather than just writing "cookie missing."
5. Select the request immediately after login and inspect **Request Headers → `Cookie`**. Is the expected cookie name sent?
6. If `Cookie` is sent yet the server lacks a session, inspect **`isRequestedSessionIdValid()`** as a boolean, session store TTL, and pod routing.
7. If the session is valid yet you get 401/302 login, investigate **`SecurityContextRepository`** and authentication state.
8. Inspect every **`Location`** in the redirect chain: did HTTPS flip to HTTP, host become internal, or prefix `/portal` disappear?
9. If cross-origin `fetch` reports CORS, check **`credentials`** on the request, `ACAO`/`ACAC` on the response, and preflight; never assume the cookie wasn't sent solely from a JS error.
10. Use test accounts and synthetic traffic. Never paste real `JSESSIONID`s, OAuth tokens, passwords, or session dumps into issue trackers.

**Never use `document.cookie` to conclude an `HttpOnly` cookie is missing.** JS is blocked from reading it by design.

**Never use `response.headers.get("set-cookie")`** to conclude the server didn't set a cookie; Fetch hides this header from browser JS.

## 19. Diagnosing Lost Sessions Caused by Rolling Upgrades

A migration checklist should verify:

| Change | Risk |
| --- | --- |
| Boot 2.x → Boot 3.x | Namespace **`javax.servlet` → `jakarta.servlet`**, custom filters/listeners and dependencies must be updated. |
| Security 5 → 6 | Context persistence/explicit-save, default filter behavior, and session management differ. |
| Changed login hostname | Old host-only cookies are not sent to the new hostname. |
| Changed public prefix | Old cookie `Path` no longer matches the new path. |
| Added HTTPS termination | Misconfigured Forwarded Proto/Host breaks redirects and `Secure` cookies. |
| Nginx Ingress → another gateway | Header sanitization, rewrites, and proxy-cookie policies differ. |
| Single pod → multiple pods | In-memory sessions are not shared; needs routing or shared store strategy. |
| Added Spring Session Redis | Session TTL/serializer/namespace do not automatically match container stores. |
| Upgraded Jackson/serialization | Old session attributes may fail to deserialize. |
| Changed `SameSite`/browser behavior | Cross-site callbacks/logins and `fetch` behavior change. |
| Changed cookie name | Clients hold old `JSESSIONID`, app expects a new name. |
| Switched Servlet container | `Set-Cookie` defaults, session tracking, and redirects differ. |

Before rollout, run compatibility tests through the public route and decide whether user re-authentication is part of the plan. Never assume existing in-memory sessions migrate to Redis automatically.

A rolling upgrade where two app versions share Redis simultaneously can fail due to incompatible session attribute serialization. Plan versioned schemas or deployment strategies to avoid unintended session drops.

## 20. Quick Error Classification Table

| Symptom | Do not confuse with | Action to take |
| --- | --- | --- |
| Missing `Set-Cookie` | Browser not sending cookie | Check if app created session, auth/context save, or proxy stripped header. |
| `Set-Cookie` present yet blocked by browser | Session store failure | Read blocked reason, `Domain`/`Secure`/`SameSite`/third-party rules. |
| Cookie not sent under `/portal` | Redis timeout | Check public cookie `Path` and `Domain`. |
| `Secure` cookie dropped after HTTP redirect | Session fixation | Fix `X-Forwarded-Proto` and HTTPS `Location`. |
| JS cannot see `document.cookie` | Cookie wasn't stored | Likely `HttpOnly`; verify in Network/Storage. |
| JS cannot read `Set-Cookie` | Server didn't set cookie | Header hidden by browser Fetch; inspect DevTools. |
| `credentials: "include"` still sends no `Cookie` | Fetch omitted credentials | Check `SameSite`/`Domain`/`Path`/`Secure`/browser privacy. |
| CORS wildcard with credentials | Wrong cookie `Path` | `ACAO` must be an exact allowlist, `ACAC` `true`. |
| Cookie reaches server yet session invalid | Browser blocked cookie | Timeout/invalidation/wrong pod/Redis/namespace. |
| `JSESSIONID` changes right after login | Lost session | Likely normal SessionFixation protection. |
| `HttpSession` exists yet auth returns 401 | Cookie not sent | Check `SecurityContextRepository`, token/login policy. |
| POST returns 403 | Always means lost cookie | May be CSRF or authorization failure. |
| 302 to `http://internal` | `SameSite` | Check reverse proxy `Forwarded`/Host/Proto and URI builder. |
| Repeated 302 login after logout | User not authenticated | Unexpired old cookie or `invalid-session` strategy. |
| Fails on only one pod | Browser cookie policies | Inspect session store, cluster rollout, or version drift. |
| Session lost after restart | Cookie `Domain` | In-memory state is non-persistent. |
| HTTPS ↔ HTTP redirect loop | Cookie wasn't stored | Fix external scheme detection; never turn off HTTPS. |

## 21. Safe Monitoring and Logging

When debugging production, log **minimal metadata**:

~~~json
{
  "event": "session.lookup",
  "route": "/account",
  "request_id": "safe-correlation-id",
  "cookie_header_present": true,
  "requested_session_id_valid": false,
  "session_present": false,
  "authenticated": false,
  "pod": "api-2"
}
~~~

This is an illustrative schema, not emitted by Spring Boot by default. These booleans isolate cookie transport, session lookup, and auth without leaking tokens. Generate a separate request/trace ID—**never use the raw session ID**.

Never log:
- `JSESSIONID`/`SESSION`/remember-me cookie values.
- Full `Set-Cookie`/`Cookie`/`Authorization` headers.
- OAuth authorization codes/state or refresh tokens.
- Login request bodies containing usernames/passwords/OTPs.
- Raw paths/queries with tokens or personal data.
- Redis keys containing literal session IDs.
- Stringified `SecurityContext`/principal objects.

Keep **`spring.mvc.log-request-details=false`** in production; avoid enabling root TRACE, wire logging, or Tomcat access logs capturing `Cookie` headers. If narrow DEBUG logging is temporarily needed, review contents, set an owner/TTL, prepare rollback, and guard log volume and access controls.

Useful metrics: sessions created/expired counts (never labeled by session ID), auth failure codes, 302 login redirects, 401/403 counts, session store errors, per-pod load, wrong-scheme redirects, 5xx, and Redis latency. Never put raw `userId`, cookie values, or request IDs into metric tags.

## 22. Incident Runbook

1. Record frontend origin, public API URL, ingress/controller, backend URL, Spring Boot/Security versions, and authentication mode.
2. Pick a test account and trace login → next request → logout in DevTools with Preserve log.
3. Confirm whether `Set-Cookie` was emitted, stored or blocked by the browser, and whether the next request sent `Cookie`.
4. Compare `Domain`/`Path`/`Secure`/`HttpOnly`/`SameSite`/`Expires` against the **public URL**, not the upstream URI.
5. If `Cookie` is missing, check `fetch` `credentials`, CORS, and cross-site browser policies.
6. If `Cookie` is present, check session validity (without logging the real ID), timeout/invalidation, session store, and load-balancer pod routing.
7. If session exists yet unauthenticated, check custom Spring Security persistence, SessionFixation, `SecurityFilterChain`, and logout/invalid-session policies.
8. Inspect redirect chains: `Location` scheme/host/port/prefix, TLS termination, and forwarded headers.
9. If URLs are wrong, fix the forwarded strategy, proxy header sanitization, or context mapping instead of disabling `Secure`.
10. Verify the exact flow with **`curl -c/-b`** against the public origin and **Java `RANDOM_PORT`** against the backend, plus browser tests for `SameSite`/CORS.
11. With multiple replicas, verify sticky sessions or shared session repository, TTLs, and serialization compatibility.
12. Keep a rollback ready for ingress, cookie attributes, or login-flow config if canary checks fail.
13. Post-incident, add regression tests and sanitized telemetry so future triage never needs session IDs in logs.

**Never do:** disable `Secure` on production HTTPS, set `SameSite=None` regardless of CSRF, turn off CSRF, or expose `/actuator/loggers` just to "make errors go away"; these open vulnerabilities without fixing the broken layer.

## 23. Pre-Release and Post-Upgrade Checklist

- [ ] Identified auth mode: stateful `HttpSession`, Spring Session, JWT, or hybrid.
- [ ] Cookie `Name`, `Domain`, `Path`, `Secure`, `HttpOnly`, and `SameSite` match the public browser URL.
- [ ] Server/repository session timeout aligns with cookie persistence policy.
- [ ] Public HTTPS never redirects to HTTP or internal hosts.
- [ ] `Forwarded`/`X-Forwarded-*` headers come from a trusted proxy, and backend rejects untrusted direct traffic.
- [ ] Context path, Ingress strip/preserve, and cookie `Path` align.
- [ ] Session IDs never appear in URLs/queries/logs; session tracking uses cookies.
- [ ] Cross-origin `fetch` uses `credentials` and exact-origin CORS only when genuinely required.
- [ ] CSRF protection, `SameSite`, and OAuth state/correlation are tested.
- [ ] DevTools verified across login, refresh, cross-site callback, and logout.
- [ ] Spring Security context persistence, SessionFixation, and invalid-session handling are tested.
- [ ] Pre/post-login session ID rotation is handled normally rather than treated as a bug.
- [ ] Logout invalidates the session and expires cookies with the right `Name`/`Path`/`Domain` when required.
- [ ] Multi-pod setups use a shared session repository or documented sticky strategy.
- [ ] Redis TTL/serializer/namespace and rolling-upgrade compatibility evaluated.
- [ ] 302/303 redirects, `Set-Cookie`, and `Cookie` requests verified through **public ingress**.
- [ ] Both `RANDOM_PORT` real-HTTP tests and browser policy tests exist, not just `MockMvc`.
- [ ] No credentials, cookies, OAuth secrets, or raw `SecurityContext` in logs.
- [ ] Canary rollout/rollback and sanitized per-pod/version session metrics ready.
- [ ] Version-specific docs/configs reviewed when upgrading Spring Boot/Servlet/Ingress controllers.

## 24. Self-Check Questions

**1. If a response includes `Set-Cookie`, will the next request always send `Cookie`?**  
No. The browser may reject storing it or omit sending it due to `Domain`/`Path`/`Secure`/`SameSite`/`credentials`.

**2. Why doesn't `document.cookie` show `JSESSIONID`?**  
Often because of `HttpOnly`; the browser still sends it over HTTP when policies allow.

**3. What advantage does `getSession(false)` have when debugging?**  
It does not create a new session, preserving evidence if the previous session was invalid.

**4. Why can a valid `Cookie` still lose its session in Kubernetes?**  
The session lives in another pod's RAM, timed out/invalidated, or the shared store failed.

**5. Is `JSESSIONID` changing right after login necessarily abnormal?**  
No. Session fixation protection often rotates the ID.

**6. Does an existing `HttpSession` guarantee the request is authenticated?**  
No. The Spring Security context may not have been saved or restored.

**7. Does a `Secure` cookie require HTTPS on the backend when TLS terminates at the proxy?**  
The browser sees public HTTPS; the backend can run HTTP inside a trusted network.

**8. Why do redirects to HTTP cause logins to fail?**  
`Secure` cookies are not sent over HTTP, and host/path may also mismatch.

**9. Does `SameSite=None` bypass browser third-party cookie blocking?**  
No. It also requires `Secure` and remains subject to browser privacy policies.

**10. Can `app.example.test` and `api.example.test` be same-site yet cross-origin?**  
Yes. Cross-origin `fetch` still requires `credentials` and CORS when using cookies.

**11. Is `Access-Control-Allow-Origin: *` valid with credentials?**  
No. Credentialed CORS requires an explicit allowed origin and `ACAC: true`.

**12. Will a cookie with `Path=/internal` be sent to public `/portal`?**  
No, because `Path` matching evaluates against the public URL seen by the browser.

**13. Does `server.servlet.session.timeout=30m` automatically set cookie `Max-Age` to 30 minutes?**  
Not identically. Server idle timeout and client cookie lifetime are separate.

**14. Does `invalidate()` automatically delete the browser cookie across all containers?**  
Not guaranteed; configure explicit cookie expiration for the matching cookie scope.

**15. Why isn't a 403 on POST always a lost session?**  
It can be a CSRF rejection or authorization denial.

**16. Why is `MockMvc` alone insufficient for debugging cookies?**  
`MockMvc` does not test browser storage, `SameSite`, TLS/proxies, or network cookie jars.

**17. Which Boot property helps Spring MVC honor `X-Forwarded-Prefix`?**  
`server.forward-headers-strategy=framework`.

**18. Can `ForwardedHeaderFilter` tell whether a header was forged by an attacker?**  
No. The proxy must sanitize headers and the backend must be network-isolated.

**19. When migrating from Boot 2 to Boot 3, how do Servlet imports change?**  
From `javax.servlet` to `jakarta.servlet`.

**20. If a POST response is blocked in the browser by CORS, should you retry unconditionally?**  
No. The server may have processed the request; retries require an idempotency contract.

## 25. References

- **Spring Boot 3.3 Servlet Web Applications / SameSite Cookies:** https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html — session cookies, `SameSite` support on Tomcat/Jetty/Undertow.
- **Spring Boot 3.3 Common Application Properties:** https://docs.spring.io/spring-boot/3.3/appendix/application-properties/ — `server.servlet.session.cookie.*`, session timeout, tracking modes, and forwarded config.
- **Spring Boot 3.3 Behind a Front-end Proxy Server:** https://docs.spring.io/spring-boot/3.3/how-to/webserver.html — forwarded headers strategy, Tomcat `redirect-context-root`.
- **Spring Security Authentication Persistence & Session Management:** https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html — `SecurityContextRepository`, invalid session, fixation, and logout.
- **Spring Session HttpSession Integration:** https://docs.spring.io/spring-session/reference/http-session.html — clustered sessions and Spring Session integration.
- **Spring Session Spring Boot + Redis:** https://docs.spring.io/spring-session/reference/guides/boot-redis.html — Spring Session Redis starter and architecture.
- **Spring Framework Servlet Filters:** https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html — forwarded metadata/`ForwardedHeaderFilter`.
- **MDN Set-Cookie:** https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie — `Domain`, `Path`, `Secure`, `HttpOnly`, `SameSite`, expiry.
- **MDN Request.credentials:** https://developer.mozilla.org/en-US/docs/Web/API/Request/credentials — `omit`/`same-origin`/`include`.
- **MDN Fetch Credentials:** https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API/Using_Fetch — `credentials`, `SameSite`, cross-origin CORS.
- **MDN Access-Control-Allow-Credentials:** https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Access-Control-Allow-Credentials — credentialed response rules.
- **NGINX `proxy_pass`:** https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_pass — URI rewriting and path handling.
