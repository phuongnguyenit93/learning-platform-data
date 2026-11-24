# Cookie Secure, HttpOnly, SameSite, Domain, and Path in Spring Boot

## 1. Learning objectives and big picture

When a Spring Boot application uses an HTTP session or a custom cookie, **the server sends cookie-storage instructions via the `Set-Cookie` header**, and the browser decides when to send the cookie back via the `Cookie` header. The attributes `Secure`, `HttpOnly`, `SameSite`, `Domain`, and `Path` largely govern **how cookies are stored, transmitted, and used**. Misconfiguration can expose session IDs, log users out unexpectedly, break third-party sign-ins, or open the door to cookie-related attacks.

Example HTTP response:

```http
HTTP/1.1 200 OK
Set-Cookie: JSESSIONID=abc123; Path=/; Secure; HttpOnly; SameSite=Lax
Content-Type: text/plain;charset=UTF-8

visits=1
```

A subsequent request may send:

```http
GET /account HTTP/1.1
Host: app.example.com
Cookie: JSESSIONID=abc123
```

**Core point:** attributes such as `Secure`, `HttpOnly`, and `SameSite` appear in the **response `Set-Cookie` header**, **not in the request `Cookie` header**. The browser evaluates its policy and decides whether to send the `name=value` pair. The server should not assume a cookie is secure simply because a request arrives with `Cookie: JSESSIONID=...`.

This lesson focuses on the **Spring Boot web runtime**, especially HTTP sessions/`JSESSIONID` on Spring MVC (Servlet), and explains how the equivalent settings apply to WebFlux. The content uses Java 17+, Spring Boot 3.5.x, and HTTP examples verifiable with `curl`/browsers. All session ID values in this document are **illustrative**, not real tokens.

## 2. What is a cookie and at which layer do attributes apply?

A cookie is small `name=value` data stored by the browser according to policy. The browser enforces cookie attributes when **storing**, when **allowing JavaScript access**, and when **sending requests**. Spring Boot can issue session cookies via the servlet container or reactive session manager; applications can also construct cookies themselves with `ResponseCookie`.

| Component | Where primarily handled | Effect |
| --- | --- | --- |
| `Set-Cookie` | Sent by server, received by browser | Creates/updates/deletes a cookie and its attributes |
| `Cookie` | Sent by browser, received by server | Contains only selected name/value pairs |
| `Secure` | Browser | Restricts sending the cookie over insecure connections, typically requiring HTTPS |
| `HttpOnly` | Browser | Blocks JavaScript from reading/writing the cookie via `document.cookie` |
| `SameSite` | Browser | Controls cookie sending in same-site vs. cross-site contexts |
| `Domain` | Browser | Specifies which hostnames may receive the cookie |
| `Path` | Browser | Specifies which URL paths may receive the cookie |
| `Expires`, `Max-Age` | Browser | Controls client-side lifetime |
| `HttpSession` | Server/Servlet container | Holds session state on the server; the cookie usually holds only an ID |

**A cookie is not synonymous with a session.** In the traditional Spring MVC model, `JSESSIONID` usually contains only a **session reference ID**; data inside `HttpSession` lives on the server. For custom cookies holding themes, carts, or tokens, cookie contents may differ. Protective attributes must be chosen according to **data sensitivity** and business flow.

**A cookie is also not synonymous with `localStorage`.** Browsers can automatically attach cookies based on request policies, whereas data in `localStorage` does not automatically accompany every HTTP request. This makes cookie-based authentication convenient while introducing CSRF risk that must be mitigated.

## 3. `Secure`: send only over secure connections

`Secure` instructs the browser to send the cookie only on secure requests, typically **HTTPS**.

```http
Set-Cookie: JSESSIONID=abc123; Path=/; Secure; HttpOnly
```

For `https://app.example.com`, the cookie above can be sent on HTTPS requests matching `Domain`, `Path`, and `SameSite`. Browsers generally **do not send** that cookie over `http://app.example.com`. Some browsers grant special testing exceptions for `localhost`; do not treat that exception as a production security standard.

### What does `Secure` solve?

- Reduces the risk of session cookies being transmitted in plaintext over HTTP.
- Mitigates certain cookie theft/injection attacks over insecure connections.
- Required by browsers before they accept cookies with `SameSite=None`.
- Required for cookie prefixes such as `__Secure-` and `__Host-` (see Section 8).

### What does `Secure` NOT solve?

- **Does not encrypt the cookie value in the browser's own storage**; transport encryption is provided by TLS/HTTPS.
- Does not block JavaScript from reading the cookie: that is `HttpOnly`'s job.
- Does not prevent CSRF by itself: that involves `SameSite`, CSRF tokens, and request verification.
- Does not protect the server from XSS, broken authorization, or data theft via API calls made from the victim's own session.
- Does not replace proper HTTPS deployment, HSTS, and reverse proxy configuration.

**Practice:** production session/auth cookies should carry `Secure`, and the application should only serve authenticated requests over HTTPS. If TLS terminates at a load balancer that proxies to Spring Boot over internal HTTP, configure TLS/proxy forwarding properly and never let the application trust forwarded headers from unauthenticated clients.

### HTTPS in front of a reverse proxy

Example deployment flow:

```text
Browser --HTTPS--> Reverse proxy/load balancer --internal HTTP--> Spring Boot
```

If cookies are configured dynamically based on whether the backend perceives a request as HTTPS, the backend may see `request.isSecure() == false` and omit `Secure`. For critical sessions, **explicitly setting `server.servlet.session.cookie.secure=true`** in the production profile avoids relying on fragile inference. If forwarded headers are needed for redirects, URLs, or secure detection, configure `server.forward-headers-strategy` to match your network topology and trust forwarded headers only when created or overwritten by a trusted proxy.

## 4. `HttpOnly`: blocking JavaScript access to cookies

`HttpOnly` prevents page JavaScript from reading or setting the cookie through `document.cookie`.

```http
Set-Cookie: JSESSIONID=abc123; Path=/; Secure; HttpOnly; SameSite=Lax
```

Example:

```javascript
console.log(document.cookie);
```

This is browser-executed code, **not Java**. If `JSESSIONID` has `HttpOnly`, it will not appear in the string returned by `document.cookie`. However, the browser **still sends** that cookie on policy-eligible requests, including requests initiated via `fetch` or `XMLHttpRequest` when credentials mode and web platform rules permit.

### Why set it on session cookies?

If an XSS vulnerability executes malicious JavaScript, that script might attempt to read `document.cookie` and exfiltrate the session ID. `HttpOnly` reduces the risk of stealing the **cookie value** through that vector.

However, **`HttpOnly` does not cure XSS**: a malicious script can still perform actions within the current session, read page contents accessible to the script, or dispatch requests to which the browser attaches cookies. You still need output escaping, an appropriate Content Security Policy, input validation, server-side authorization checks, and CSRF protection.

### Which cookies should NOT have `HttpOnly`?

Only cookies that JavaScript genuinely needs to read or modify directly—such as certain non-sensitive UI preferences—should be considered for `HttpOnly=false`. If JavaScript does not need to inspect the value, even UI preference cookies can be marked `HttpOnly=true`.

For **session IDs, refresh tokens, or sensitive login tokens stored in cookies**, prefer `HttpOnly=true`. Some double-submit CSRF designs use a token cookie readable by JavaScript; that is an intentional pattern requiring a clear understanding of how Spring Security handles CSRF, and the CSRF token cookie must not be confused with the session authentication cookie.

## 5. `SameSite`: same-site, cross-site, and the three modes

`SameSite` instructs the browser whether to send a cookie on requests originating from **another site**. It is a defense-in-depth barrier against CSRF, **not an authorization mechanism**.

Modern browsers define **site** using **scheme and registrable domain** (schemeful same-site). Distinguish this from **origin**, which consists of scheme, host, and port.

Examples:

| Two URLs | Same-site? | Same-origin? | Explanation |
| --- | --- | --- | --- |
| `https://app.example.com` and `https://api.example.com` | Usually **yes** | **No** | Same scheme and registrable domain, different hosts |
| `https://app.example.com:443` and `https://app.example.com:8443` | **Yes** | **No** | Port changes the origin, usually not the site |
| `http://app.example.com` and `https://app.example.com` | **No** under schemeful site | **No** | Different schemes |
| `https://app.example.com` and `https://other.example.net` | **No** | **No** | Different registrable domains |

The domains in the table are hypothetical examples; real rules also involve the Public Suffix List. Thus **cross-origin is not necessarily cross-site**: an SPA on `app.example.com` calling an API on `api.example.com` is cross-origin yet can still be same-site. CORS and SameSite are two different mechanisms.

### `SameSite=Strict`

```http
Set-Cookie: SID=demo; Path=/; Secure; HttpOnly; SameSite=Strict
```

The browser sends the cookie only in **same-site** contexts. When a user clicks a link from an external site to the application, a `Strict` cookie may be omitted on the initial request, making a logged-in session temporarily appear logged out. `Strict` fits certain highly sensitive action cookies, but requires testing page-navigation and login UX.

### `SameSite=Lax`

```http
Set-Cookie: SID=demo; Path=/; Secure; HttpOnly; SameSite=Lax
```

`Lax` sends cookies on same-site requests and **certain top-level navigations from other sites using safe HTTP methods**, typically when a user clicks a link to a `GET` page. It generally **does not send** cookies for cross-site `POST`s, iframes, subresources, or restricted `fetch` calls.

This is typically the balanced default for **traditional web session cookies**. Nevertheless, state-changing actions via `GET` remain a design flaw, and same-site subdomains might not be fully trustworthy. **`Lax` does not replace CSRF tokens.**

Some browsers apply Lax-like behavior when `SameSite` is omitted, sometimes with transitional exceptions for newly created cookies. Therefore, **explicitly declaring `SameSite=Lax`** yields more predictable behavior than relying on browser defaults.

### `SameSite=None`

```http
Set-Cookie: SID=demo; Path=/; Secure; HttpOnly; SameSite=None
```

`None` permits sending cookies even in cross-site contexts, **provided other browser policies allow it**. Modern browsers require `Secure` when `SameSite=None` is used; cookies missing `Secure` may be rejected.

Choose `None` only when business flows genuinely require cookies inside third-party iframes, cross-site integrations, or multi-site login flows. Even with `None; Secure`, third-party cookies may be blocked or partitioned by tracking privacy policies; **`None` does not guarantee cookies will always be accepted**.

### Reference scenarios

| Scenario | Strict | Lax | None + Secure |
| --- | --- | --- | --- |
| Normal navigation within the same site | Sent if Domain/Path valid | Sent if valid | Sent if valid |
| Clicking a link from an external site via top-level GET | Usually not | Usually yes | Possible |
| Cross-site POST form submission | No | Usually not | Possible |
| External site embedding an iframe or subresource pointing to the app | No | Usually not | Possible, subject to third-party policies |
| Cross-**origin** fetch that is still same-site | Possible if credentials/CORS and Domain/Path valid | Similar | Similar |

This table summarizes `SameSite` conditions and **does not account** for server authorization, CSP, CORS, third-party cookie blocking, or browser-specific policies. For OAuth/OIDC/SAML, carefully evaluate redirects via top-level GET, `form_post`, iframes, or callbacks alongside state/correlation cookies; flipping all session cookies to `None` without analysis is a common mistake.

## 6. `Domain`: host-only vs. sharing cookies across subdomains

When `Set-Cookie` **has no Domain attribute**, the cookie is **host-only**: it is sent only to the exact hostname that set it (provided other conditions hold).

Example response from `https://app.example.com`:

```http
Set-Cookie: SID=abc123; Path=/; Secure; HttpOnly; SameSite=Lax
```

That cookie is sent to `app.example.com`; it is **not automatically sent to** `api.example.com` because the hostnames differ.

If the server is authorized to set a cookie for a valid parent domain:

```http
Set-Cookie: SID=abc123; Domain=example.com; Path=/; Secure; HttpOnly; SameSite=Lax
```

The cookie can be sent to `example.com` and subdomains such as `app.example.com` and `api.example.com`, assuming Secure/SameSite/Path also match. `Domain` allows broadening scope to a valid parent domain; it **does not allow** `app.example.com` to set a cookie for `other-company.com` or a public suffix like `com`.

### Key rules

- **Default to omitting Domain** so cookies remain host-only, minimizing session sharing across subdomains.
- Only use `Domain=example.com` when the architecture genuinely needs subdomains to **share that exact cookie**; even when shared, services still need a shared authentication/session repository for the session ID to be meaningful everywhere.
- Legacy `.example.com` syntax: a leading dot is **ignored** by modern browsers; `.example.com` does not mean “subdomains only, excluding root”.
- `Domain=example.com` expands the attack surface: less-trusted or compromised subdomains can be involved in cookie tossing, cookie fixation, or cookie collisions.
- `Domain` **must not contain** a scheme or port. Never write `Domain=https://example.com` or `Domain=example.com:8443`.
- A server on `localhost` or an IP address handles `Domain` differently from normal Internet domains; during local development, prefer omitting `Domain`.

### Domain is not “same-site”

Two subdomains can be **same-site**, yet a host-only cookie for `app.example.com` is still **not sent** to `api.example.com`. `SameSite=Lax` does not expand `Domain` scope. For a request to carry a cookie, **Domain/host, Path, Secure, SameSite, and all other browser policies** must be satisfied simultaneously.

## 7. `Path`: filtering which URLs receive the cookie

`Path` specifies the path prefix for which the browser sends the cookie under cookie path-matching rules.

```http
Set-Cookie: SID=abc123; Path=/admin; Secure; HttpOnly; SameSite=Lax
```

The cookie above is typically sent to:

- `/admin`, `/admin/`, `/admin/orders`;
- but **not sent** to `/`, `/api`, or `/administrator`.

The `/` character acts as a path segment delimiter: `Path=/admin` does not match `/administrator` by raw string prefix. If `Path` is omitted, browsers compute a **default-path from the cookie-setting URL**, which is not always `/`. For session cookies, Spring Boot/servlet containers typically apply a path matching the application context path; you can configure `server.servlet.session.cookie.path` explicitly.

### Path is a delivery scope, not a security boundary

**Never use Path for authorization**: scripts or apps on the same origin can find ways to interact with other paths; the server must still enforce authentication/authorization. `Path=/admin` does not stop unauthorized users from accessing `/admin` resources.

Cookies with the same name and different `Path` values can coexist, for example:

```http
Set-Cookie: SID=aaa; Path=/; Secure
Set-Cookie: SID=bbb; Path=/admin; Secure
```

A request to `/admin` may carry two `SID` pairs. Servers and frameworks should not rely on the ordering of duplicate cookie names to pick a sensitive value. Use **distinct cookie names** per application or maintain consistent paths. Avoid letting apps at different context paths emit multiple indistinguishable `JSESSIONID` cookies.

### Path and applications under a context path

When running a Spring Boot Servlet app at `/shop` (e.g., `server.servlet.context-path=/shop`), the session cookie may be scoped to `/shop` rather than the entire host. Overriding to `Path=/` sends the cookie more broadly to other apps on the same host. Broadening may help some architectures, but increases exposure.

An app's `Path=/shop` cookie does not automatically become `Path=/` when a reverse proxy rewrites prefixes in front of Spring Boot; inspect the URI **the browser actually sees**, proxy rewrites, context path, and cookie path. Proxies can rewrite `Set-Cookie`, but that must be tested and managed consistently.

## 8. Combining attributes and cookie prefixes

A sound configuration for an HTTPS web application session on a **single host** typically looks like:

```http
Set-Cookie: __Host-SESSION=opaque-id; Path=/; Secure; HttpOnly; SameSite=Lax
```

Benefit of the `__Host-` prefix: browsers supporting prefixes only accept the cookie if it has **`Secure`**, **`Path=/`**, and **no `Domain`**, and is set from a secure HTTPS context. This helps mitigate certain overwrites from subdomains or unexpected paths.

| Prefix | Core browser requirements (where supported) | Best suited for |
| --- | --- | --- |
| `__Secure-` | `Secure`; set from HTTPS | Secure cookies that may still need a custom Domain or Path |
| `__Host-` | `Secure`, `Path=/`, **no Domain**, set from HTTPS | Host-only session cookies on a single hostname |
| `__Http-` | `Secure` and `HttpOnly`, set via Set-Cookie | Targeting server-only cookie creation; check browser support |
| `__Host-Http-` | Combines `__Host-` and `HttpOnly` requirements | Stricter model in supporting browsers |

Prefixes are **browser-enforced naming conventions**, not server-side authentication/authorization. Some newer prefixes lack uniform support across all browsers; check your deployment targets.

**Very common pitfall:** `__Host-SESSION` and `Domain=example.com` are **incompatible**. If you must share cookies across subdomains using `Domain`, do not use the `__Host-` prefix. When using `__Host-`, you must use `Path=/` (never `Path=/shop`).

### Choosing settings by scenario

| Purpose | Secure | HttpOnly | SameSite | Domain | Path |
| --- | --- | --- | --- | --- | --- |
| Standard HTTPS web login session | `true` | `true` | `Lax` (evaluate flows) | Omitted (host-only) | `/` or matching context path |
| Ultra-sensitive session, no cross-site navigation needed | `true` | `true` | `Strict` after testing UX | Omitted | Scoped to app |
| Cookie needed inside third-party iframe | `true` | `true` if JS doesn't read it | `None`; still subject to third-party policy | Minimal required | Minimal required |
| Non-sensitive theme/locale preference read by JS | `true` on HTTPS | Can be `false` | Usually `Lax` | Omitted | Per UI needs |
| CSRF token for JS-readable cookie pattern | `true` on HTTPS | Can be `false` if framework requires JS access | Per flow and CSRF guidance | Minimal | Per config |

No single attribute bundle fits every application. **Auth sessions** require stricter protections than non-sensitive preferences; iframe/cross-site apps have different constraints than traditional web apps.

## 9. Configuring HTTP session cookies in Spring Boot MVC

In Spring Boot MVC running on a Servlet container such as Tomcat, session cookie attributes are configured via `server.servlet.session.cookie.*`. Boot applies these settings to the container-generated session cookie, and **does not automatically apply all these properties to custom cookies created by controllers or third-party libraries**.

Example for an HTTPS production environment:

```properties
server.servlet.session.cookie.name=__Host-SESSION
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.secure=true
server.servlet.session.cookie.same-site=Lax
server.servlet.session.cookie.path=/
# Do not set server.servlet.session.cookie.domain
server.servlet.session.timeout=20m
```

This is a **production configuration snippet** for an application on its own host with a `/` compatible context path. Setting `secure=true` requires browsers to use HTTPS for session exchange; do not test this entire policy over plain HTTP. If the app uses `server.servlet.context-path=/shop`, evaluate the cookie path and prefix before keeping `__Host-SESSION`.

### Property meanings

| Property | Meaning | Notes |
| --- | --- | --- |
| `server.servlet.session.cookie.name` | Session cookie name | Default is usually `JSESSIONID` |
| `server.servlet.session.cookie.secure` | Always attach `Secure` | Set `true` in HTTPS production |
| `server.servlet.session.cookie.http-only` | Attach `HttpOnly` | Set `true` for session IDs |
| `server.servlet.session.cookie.same-site` | `Lax`/`Strict`/`None` | Test login and cross-site flows |
| `server.servlet.session.cookie.domain` | Domain attribute | Leave unset for host-only |
| `server.servlet.session.cookie.path` | Path attribute | Matches context path or set explicitly |
| `server.servlet.session.cookie.max-age` | Client-side cookie age | Not the server-side session idle timeout |
| `server.servlet.session.timeout` | Server-side session idle timeout | Must be evaluated alongside cookie lifetime |

**Cookie lifetime and session lifetime differ:** setting `cookie.max-age=7d` does not mean the session survives seven days; if the server expires the session after 20 minutes of inactivity, the browser may still send an old cookie whose ID no longer points to a valid session. Conversely, the browser deleting a cookie does not immediately erase server-side state; proper logout/invalidation logic is required.

### When using Spring Session

If the application uses Spring Session (e.g., sessions in Redis), the framework has its own cookie manager such as `DefaultCookieSerializer`. Do not assume Servlet container defaults/`server.servlet.session.cookie.*` are always the final source of truth when a session repository or custom cookie serializer is active. Verify the actual bean/session integration and the **`Set-Cookie` response** in the running environment. Equivalent attributes may need to be configured on the appropriate serializer, following the same Secure, HttpOnly, SameSite, Domain, and Path principles.

### When using WebFlux

Spring Boot WebFlux has the corresponding **`server.reactive.session.cookie.*`** property group, for example:

```properties
server.reactive.session.cookie.secure=true
server.reactive.session.cookie.http-only=true
server.reactive.session.cookie.same-site=Lax
server.reactive.session.cookie.path=/
# Omit Domain to keep host-only if sharing is not needed
```

This is **specifically for WebFlux applications**; do not set `server.servlet.*` expecting it to alter reactive session cookies. Spring Security and Spring Session can still have their own session cookie serializers; inspect response headers when combining them.

## 10. Runnable example: Spring Boot MVC and session cookies

This example uses **JDK 17+**, **Maven**, and **Spring Boot 3.5.0** in a standalone project. This is a specific release of the 3.5 line, not necessarily the latest Spring Boot release. In real projects, pick a supported patch release according to your operational policy.

The example includes an endpoint counting visits in `HttpSession`, an endpoint creating a separate preference cookie, and an endpoint deleting that preference cookie. There is no real login; the data is solely for observing how browsers store and send cookies.

### 10.1. Structure

```text
cookie-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/cookiedemo/
    │   └── CookieDemoApplication.java
    └── resources/
        ├── application.properties
        └── application-prod.properties
```

### 10.2. Complete `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>cookie-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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
```

The POM omits Spring Security because the demo only illustrates **cookies and sessions**; do not use this demo app as a production authentication system. If Security is added, CSRF and login/logout rules must be configured in the security filter chain.

### 10.3. Complete Java, single file

File `src/main/java/com/example/cookiedemo/CookieDemoApplication.java`:

```java
package com.example.cookiedemo;

import java.time.Duration;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseCookie;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class CookieDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(CookieDemoApplication.class, args);
    }
}

@RestController
class CookieDemoController {

    @GetMapping(value = "/demo/visit",
            produces = MediaType.TEXT_PLAIN_VALUE)
    String visit(HttpSession session) {
        Integer oldCount = (Integer) session.getAttribute("visits");
        int count = oldCount == null ? 1 : oldCount + 1;
        session.setAttribute("visits", count);
        return "visits=" + count;
    }

    @GetMapping(value = "/demo/choice",
            produces = MediaType.TEXT_PLAIN_VALUE)
    ResponseEntity<String> setChoice(HttpServletRequest request) {
        ResponseCookie cookie = ResponseCookie
                .from("demo_choice", "compact")
                .path("/demo")
                .sameSite("Lax")
                .httpOnly(true)
                .secure(request.isSecure())
                .maxAge(Duration.ofMinutes(10))
                .build();

        return ResponseEntity.ok()
                .header(HttpHeaders.SET_COOKIE, cookie.toString())
                .body("choice=compact");
    }

    @PostMapping(value = "/demo/choice/clear",
            produces = MediaType.TEXT_PLAIN_VALUE)
    ResponseEntity<String> clearChoice(HttpServletRequest request) {
        ResponseCookie deleted = ResponseCookie
                .from("demo_choice", "")
                .path("/demo")
                .sameSite("Lax")
                .httpOnly(true)
                .secure(request.isSecure())
                .maxAge(Duration.ZERO)
                .build();

        return ResponseEntity.ok()
                .header(HttpHeaders.SET_COOKIE, deleted.toString())
                .body("choice cleared");
    }
}
```

All code resides **in a single file**. `CookieDemoApplication` is `public`; `CookieDemoController` is package-private and component-scanned by Spring in the same package. There is no need to manually write `Set-Cookie: JSESSIONID=...`: when `/demo/visit` creates/writes state in `HttpSession`, the servlet container manages the session cookie.

**Intent of `.secure(request.isSecure())` in the demo preference cookie:** allows observing both local HTTP (without Secure) and HTTPS (with Secure) without needing local TLS certificates. This is not a recommended security configuration for auth cookies; **in production, auth cookies must mandate `Secure=true`**, never dropping the flag depending on whether the app observes HTTP or HTTPS.

### 10.4. Local and production configurations

`src/main/resources/application.properties` for local HTTP runs:

```properties
server.port=8080
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.same-site=Lax
server.servlet.session.cookie.path=/
server.servlet.session.timeout=20m
```

This file **does not force `Secure=false`**; local cookie policy depends on the request/server. Real applications must have a separate production profile for HTTPS, such as `src/main/resources/application-prod.properties`:

```properties
server.servlet.session.cookie.name=__Host-SESSION
server.servlet.session.cookie.secure=true
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.same-site=Lax
server.servlet.session.cookie.path=/
# Intentionally do NOT set Domain: __Host- requires host-only
```

`application-prod.properties` only takes effect when running with the `prod` profile. In production, valid HTTPS at the browser and proper proxy configuration are required. **Do not activate the `prod` profile while testing plain HTTP on a hostname other than `localhost`** and conclude cookies are broken, because browsers may intentionally refuse to send or store `Secure` cookies.

When running `java -jar` behind an HTTPS proxy:

```bash
java -jar target/cookie-demo-1.0.0.jar --spring.profiles.active=prod
```

This command only enables the production cookie policy; it **does not create a TLS certificate**. TLS/proxy configuration belongs to the deployment layer.

### 10.5. Run and test locally

From the `cookie-demo` directory:

```bash
mvn spring-boot:run
```

In another terminal using `curl`:

```bash
curl -i -c cookies.txt http://localhost:8080/demo/visit
```

The HTTP body after headers is:

```text
visits=1
```

The first response creating a session typically includes `Set-Cookie: JSESSIONID=...` with the configured attributes. The session ID value is **random** and unpredictable. `cookies.txt` stores cookies in curl's Netscape cookie jar format.

Send a second request **using the same cookie jar**:

```bash
curl -s -b cookies.txt http://localhost:8080/demo/visit
```

Exact body:

```text
visits=2
```

If you omit `-b cookies.txt` and send no session cookie, the new request creates a different session and typically returns `visits=1`. This demonstrates that session state lives on the server, while the cookie is the lookup key.

Create the preference cookie:

```bash
curl -i -c cookies.txt http://localhost:8080/demo/choice
```

The body is `choice=compact`. The header will resemble:

```http
Set-Cookie: demo_choice=compact; Path=/demo; Max-Age=600; HttpOnly; SameSite=Lax
```

This is an **illustrative representation** of the main attributes; ordering, `Expires`, and header details can vary by version. Over local HTTP, the cookie created by code omits `Secure` because `request.isSecure()` is `false`. If the request is genuinely HTTPS, `Secure` is included.

Delete the preference cookie:

```bash
curl -i -b cookies.txt -c cookies.txt -X POST \
  http://localhost:8080/demo/choice/clear
```

Exact body:

```text
choice cleared
```

The server sends `Set-Cookie` with **the same name and `Path=/demo`**, plus `Max-Age=0`. The browser/curl handles deleting that scoped cookie. This is an example of deleting a preference, **not authentication logout**, and does not invalidate `HttpSession`.

On Windows PowerShell, use `curl.exe` if `curl` is aliased to a PowerShell cmdlet; place commands on one line or use PowerShell line continuation. `-X POST` is used here simply because the endpoint is annotated with `@PostMapping`.

### 10.6. Why not set cookie flags with `document.cookie`?

`document.cookie` can only write certain client-side cookie attributes and **cannot set `HttpOnly`**. Therefore, session/auth cookies must be created by the server via `Set-Cookie`. `ResponseCookie` in Java lets you declare attributes cleanly rather than hand-concatenating HTTP header strings.

To write multiple cookies in one response, send **multiple separate `Set-Cookie` headers**, rather than merging them into one comma-separated header. Each `Set-Cookie` creates or updates a single cookie.

## 11. Configuring application cookies with `ResponseCookie`

`server.servlet.session.cookie.*` mainly governs the **session cookie**; custom cookies such as `theme`, `locale`, `remember_me`, or CSRF cookies may be created by the application, Spring Security, or libraries and **must have their own policies**.

The following illustrative snippet uses Spring Framework's API:

```java
ResponseCookie cookie = ResponseCookie.from("ui_mode", "dark")
        .secure(true)
        .httpOnly(true)
        .sameSite("Lax")
        .path("/")
        .maxAge(Duration.ofDays(30))
        .build();

response.addHeader(HttpHeaders.SET_COOKIE, cookie.toString());
```

This is a **snippet**, not a standalone program: it requires `HttpServletResponse response`, imports for `ResponseCookie`, `HttpHeaders`, and `Duration`, and must run over HTTPS. If JavaScript needs to read `ui_mode`, consider `httpOnly(false)` **only for a concrete functional reason** and ensure the value is non-sensitive.

### `SameSite=None` cookie when cross-site usage is unavoidable

```java
ResponseCookie thirdPartyCookie = ResponseCookie.from(
                "embedded_widget_session", "opaque-value")
        .secure(true)
        .httpOnly(true)
        .sameSite("None")
        .path("/")
        .build();
```

This **illustrates setting the attributes**; it does not guarantee browsers will allow third-party cookies, does not create a secure login mechanism, and is not a recommendation to store secrets directly in cookies. Beyond CORS/credentials (if cross-origin), analyze CSRF, clickjacking defenses, cookie blocking, and iframe restrictions.

### Can `Partitioned` be added?

Some browsers support **partitioned cookies (CHIPS)**: cookies stored per top-level site partition to limit cross-site tracking. Partitioned cookies require `Secure`, and support varies across browsers. Spring Boot 3.5.x provides `server.servlet.session.cookie.partitioned` and `server.reactive.session.cookie.partitioned` for their respective runtimes; if unneeded, leave it disabled.

`Partitioned` is not a substitute for `SameSite`, not a universal fix for embedded apps, and does not remove authentication/CSRF requirements. Inspect Browser DevTools and test on target browsers before rolling out.

## 12. `Expires`, `Max-Age`, cookie deletion, and scope conflicts

Time-related cookie attributes:

- `Max-Age=600`: cookie expires 600 seconds after being set, per browser rules.
- `Expires=Wed, 01 Jan 2031 00:00:00 GMT`: absolute expiration timestamp on the client.
- When both are present, **`Max-Age` takes precedence** by specification.
- `Max-Age=0` or negative values generally expire the cookie immediately; `Max-Age=0` is the standard deletion mechanism.
- Omitting both `Expires` and `Max-Age` usually creates a client-side **session cookie**; browser session restore after restarts can keep it alive longer than “closing the window deletes it”.

Deletion example:

```http
Set-Cookie: demo_choice=; Path=/demo; Max-Age=0; SameSite=Lax
```

Subtlety: browsers key cookies primarily by **name + domain/host scope + path** (plus partition key for partitioned cookies). To delete the right cookie, you generally must match the **same name, Domain if originally set, and Path**, along with expiry 0. If originally created with `Path=/admin` and deleted with `Path=/`, you may delete a different cookie or fail to remove the original.

`Secure`, `HttpOnly`, and `SameSite` should continue to be set consistently on deletion cookies, though those flags do not substitute for matching name/domain/path. With `__Host-`, preserve the prefix constraints during deletion as well.

**Deleting the session cookie is not the whole logout:** the server must also invalidate/rotate the session, Spring Security must run its logout flow, and systems using remember-me/refresh tokens must revoke the relevant tokens. Clearing the browser cookie addresses only part of client state.

## 13. Cookies and CSRF, XSS, CORS: distinct boundaries

### 13.1. CSRF

Authentication cookies are attached automatically by browsers to requests. A malicious site can try to make the browser send a state-changing request to an app where the user is logged in. `SameSite=Lax`/`Strict` mitigates some CSRF cases, yet **does not replace** proper HTTP method design, CSRF token checks where needed, and request-origin verification.

In session-based Spring Security apps, generally keep **properly configured CSRF protection**, especially for state-changing POST/PUT/PATCH/DELETE endpoints. Do not disable CSRF globally just because `SameSite=Lax` is set. Same-site subdomains are not inherently trustworthy: if a subdomain is compromised, attacks can bypass SameSite-only defenses.

### 13.2. XSS

`HttpOnly` prevents scripts from reading the **cookie value** via standard JavaScript APIs. It does not prevent malicious scripts from acting with the active session. XSS defense requires output escaping, safe templates, controlling dynamic HTML, an appropriate CSP, and auditing frontend dependencies.

### 13.3. CORS

A page at `https://app.example.com` calling an API at `https://api.example.com` is **cross-origin**; the browser enforces CORS even when both hosts are same-site. To send cookies with a cross-origin `fetch`, the client normally needs:

```javascript
fetch("https://api.example.com/me", {
  credentials: "include"
});
```

This is browser code, not Java. The API side needs proper CORS for the exact origin when allowing credentials: for example, `Access-Control-Allow-Credentials: true` and `Access-Control-Allow-Origin` set to the allowed origin (never wildcard `*` with credentials). Even with valid CORS, the cookie must still satisfy Domain/Path/Secure/SameSite and browser privacy policies.

**CORS is not CSRF protection.** The browser blocking JavaScript from reading a response due to CORS does not necessarily prevent a state-changing request from being sent. Permissive CORS combined with `SameSite=None` requires even closer scrutiny.

### 13.4. Do not put secrets into cookies “because HttpOnly is set”

`HttpOnly` does not encrypt cookie data in the browser. Avoid storing passwords, API keys, or plaintext sensitive personal data in cookies. If an architecture places tokens in cookies, evaluate signing/encryption, expiry, rotation, revocation/logout, size limits, and browser flags. With server-side sessions, keeping an **unpredictable ID** in the cookie and session state on the server is usually easier to govern.

## 14. Practical debugging: why isn’t the cookie being sent?

When a user “logs in, then the next page load loses the session”, follow a clear diagnostic sequence:

1. **Did the session-creating request actually return `Set-Cookie`?** Open Browser DevTools → Network → response headers, look for `Set-Cookie`.
2. **Did the browser accept the cookie?** Check DevTools Application/Storage → Cookies and any blocked/rejected reason (if shown by the browser).
3. **Does the accessed URL match scheme/host/path?** Check HTTPS, port/proxy, Domain, host-only, and Path.
4. **Did the request originate same-site or cross-site?** Check the initiating page, GET/POST method, top-level navigation/iframe, and `SameSite`.
5. **If cross-origin JS fetch, are credentials/CORS right?** `credentials: "include"`, origin, and CORS headers, while still obeying cookie policies.
6. **Did the cookie expire or get deleted?** Inspect Max-Age/Expires, server session timeout, logout, rotation, and subsequent `Set-Cookie` headers.
7. **Are there duplicate cookies with the same name?** Check `JSESSIONID`/`SESSION` across Paths/Domains and stale cookies from other contexts.
8. **Did Spring Session/Spring Security or a reverse proxy alter the cookie?** Inspect actual response headers at the browser and at each proxy hop.
9. **Does the server have the session ID yet fail to find state?** Check session store, sticky sessions, Redis availability, session timeout, and auth logic.

Use `curl -i` to inspect headers:

```bash
curl -i https://app.example.com/login
```

This is only a **header inspection command pattern**; do not assume `/login` is a public GET on every application. To observe cookies across multiple requests:

```bash
curl -c cookies.txt -i https://app.example.com/
curl -b cookies.txt -i https://app.example.com/profile
```

`curl` uses its own cookie jar and **does not simulate all browser policies** such as SameSite and third-party restrictions. Use browser DevTools to verify production client behavior. JavaScript `fetch` cannot read the `Set-Cookie` response header directly because it is a forbidden response-header name, even when the server sends it.

### Quick symptom table

| Symptom | Most likely cause | How to fix |
| --- | --- | --- |
| Cookie not sent over `http://example.com` | `Secure` flag; site requires HTTPS | Test/deploy HTTPS; do not remove Secure in production |
| `SameSite=None` cookie not stored | Missing `Secure` or third-party restrictions | Add Secure/HTTPS; check browser blocked reason |
| `document.cookie` does not show session ID | `HttpOnly` is active | Expected behavior; inspect Network/Cookies instead |
| Only `app.example.com` has cookie, `api.example.com` does not | Host-only; Domain omitted | Design hostnames/Domain intentionally if sharing is genuinely needed |
| `/shop` has session, `/admin` does not | Cookie `Path=/shop` | Check context path and cookie scope design |
| Redirecting to HTTPS then back to HTTP loses session | Secure + HTTP callback | Keep HTTPS end-to-end; fix reverse proxy |
| Cross-site OAuth callback POST arrives without state cookie | SameSite=Lax/Strict blocks cross-site POST | Analyze callback flow; use state/correlation and suitable attributes |
| Cookie sent, yet server treats user as unauthenticated | Session expired / server-side state lost | Check session store, auth handler, and timeout |
| Old cookie still present after logout | Cookie deleted with wrong Path/Domain or missing invalidate | Delete with exact matching scope; invalidate server session and tokens |
| JS fetch to API omits cookie | Credentials mode, CORS, Domain, SameSite | Verify all 4 layers and browser policy |
| Cookie has `Domain=.example.com` with unexpected matching | Leading dot no longer carries legacy meaning | Use explicit `Domain=example.com` or omit Domain |
| Two `JSESSIONID` cookies exist and server picks the wrong one | Duplicate names under different Paths/Domains | Use distinct names and clear scopes |

## 15. Designing for each Spring Boot architecture

### 15.1. Single-host server-rendered MVC app

- Use server-side sessions with host-only cookies.
- Mandate HTTPS in production, `Secure=true`, `HttpOnly=true`.
- `SameSite=Lax` is usually appropriate absent special flows; protect CSRF with Spring Security.
- Keep `Domain` unset; set `Path` to match the application.
- Consider the `__Host-` prefix when `Path=/` and `Domain` is omitted.

### 15.2. SPA on one subdomain calling an API on another subdomain

- Both hostnames may be same-site yet cross-origin.
- CORS + `fetch credentials` must be configured properly; the cookie must match the hostname the request actually targets.
- The API can set a **host-only cookie for `api.example.com`** and the browser will attach it on API calls; you do not necessarily have to set `Domain=example.com` just for the SPA to call the API. The SPA's JavaScript does not need to read the `HttpOnly` session cookie.
- If multiple subdomains must share the cookie, broadening `Domain` carries security trade-offs and requires consistent auth design.
- Even when same-site, review CSRF and untrusted subdomains.

### 15.3. App embedded in an external site's iframe

- Likely requires `SameSite=None; Secure` for embedded session cookies.
- Browsers may block third-party cookies; evaluate modern policies, cookie partitioning, top-level login flows, or alternative architectures as required.
- Configure CSP `frame-ancestors` and `X-Frame-Options` to permit embedding only where authorized.
- Do not loosen `Domain` or CORS arbitrarily to fix iframe issues.

### 15.4. Multiple Spring Boot apps behind the same reverse proxy

- Determine host, context path, and `Set-Cookie` **after passing through the proxy**.
- Use distinct cookie names if multiple apps share the same hostname, or appropriate `Path` isolation.
- If multiple instances of the same app share sessions, use a proper session store (e.g., Spring Session Redis) or explicit session affinity, not just the same cookie name.
- `X-Forwarded-Proto`/`Forwarded` headers must be controlled by a trusted proxy; the backend must never trust spoofed headers from the Internet.
- Defend against session fixation by rotating the session ID upon login; Spring Security supports the appropriate strategy.

## 16. Exercises and self-check questions

1. **Are `Secure` and `HttpOnly` the same?** No. `Secure` restricts transmission over insecure connections; `HttpOnly` restricts JavaScript access to the cookie value.
2. **Can `SameSite=None` be used without `Secure`?** Modern browsers generally reject it; `Secure` and HTTPS are required (aside from localhost exceptions in some environments).
3. **Which host receives a cookie with no `Domain` attribute?** The exact host that set the cookie, not automatically other subdomains.
4. **Does `Domain=example.com` apply only to subdomains, not the root domain?** False. It can apply to both the root domain and eligible subdomains.
5. **Does `Path=/admin` protect `/admin` endpoints from unauthorized users?** No. It only scopes where browsers send the cookie; authorization must be enforced on the server.
6. **Does `SameSite=Lax` replace CSRF tokens?** No. It mitigates some cross-site request scenarios, not all of them.
7. **Does `HttpOnly` stop XSS from making transactions using the victim's session?** No; the browser still attaches the cookie to eligible requests.
8. **If `Set-Cookie` includes `Secure`, does the request `Cookie` header contain the word `Secure`?** No. `Cookie` carries only names and values.
9. **Does a 20-minute session timeout plus a 7-day cookie `Max-Age` keep the user logged in for 7 days?** No. Once the server-side session expires, the old cookie cannot restore expired state.
10. **Why is a `__Host-SESSION` cookie with `Domain=example.com` rejected?** The `__Host-` prefix forbids `Domain`, requires `Path=/`, and requires `Secure` over HTTPS.
11. **If `app.example.com` calls `api.example.com`, is it definitely cross-site?** No; it is typically same-site but cross-origin. Domain, CORS/credentials, and cookie policies still must be evaluated separately.
12. **Is deleting a `Path=/admin` cookie using `Path=/` correct?** Not guaranteed; deletion must match the original cookie's name/Domain/Path.

## 17. Pre-production deployment checklist

- [ ] Identified what each cookie holds: session ID, auth token, CSRF token, or preference.
- [ ] Session/auth cookies have `Secure=true`, `HttpOnly=true`, and use HTTPS exclusively.
- [ ] Selected `SameSite=Lax` or `Strict` appropriately; `None; Secure` only when flows demand it, with CSRF/third-party restrictions evaluated.
- [ ] Omitted `Domain` unless cookie sharing is genuinely required; never broaden cookies to all subdomains out of habit.
- [ ] Set `Path` explicitly to match the application context; considered `__Host-` where constraints fit.
- [ ] Set appropriate cookie lifetimes, distinguishing client `Max-Age` from server session timeout.
- [ ] Verified logout, session invalidation, session ID rotation, and scope-matched cookie deletion.
- [ ] Confirmed Spring MVC uses `server.servlet.session.cookie.*`, WebFlux uses `server.reactive.session.cookie.*`, and Spring Session/Security integrations do not override unexpectedly.
- [ ] Verified HTTPS termination, reverse proxy forwarded headers, and trust boundaries.
- [ ] Did not replace CSRF/XSS defenses with `SameSite`/`HttpOnly`.
- [ ] Tested in DevTools across target browsers/devices, including cross-site redirects/iframes where applicable.
- [ ] Never log real session IDs/tokens, and never store plaintext sensitive data in cookies.
- [ ] Monitor invalid-session rates, login loops, failed redirects, and browser cookie rejections after release.

## 18. Reliable references

- Spring Boot 3.5 — [Common Application Properties: Servlet Session Cookie and Reactive Session Cookie](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html)
- Spring Boot — [Embedded Servlet Container and session cookie configuration](https://docs.spring.io/spring-boot/how-to/webserver.html)
- Spring Framework — [ResponseCookie API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/ResponseCookie.html)
- Spring Security — [Protection Against Exploits: CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- Spring Session — [Spring Session with Servlet](https://docs.spring.io/spring-session/reference/http-session.html)
- MDN — [Set-Cookie header: Secure, HttpOnly, SameSite, Domain, Path and cookie prefixes](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie)
- MDN — [Using HTTP Cookies](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Cookies)
- MDN — [Secure Cookie Configuration](https://developer.mozilla.org/en-US/docs/Web/Security/Practical_implementation_guides/Cookies)
- MDN — [Fetch: credentials](https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API/Using_Fetch)

**Remember:** `Secure` controls **sending over secure connections**, `HttpOnly` controls **whether JavaScript can read the cookie**, `SameSite` controls **which site contexts send it**, `Domain` limits **hosts**, and `Path` limits **URL paths**. The browser evaluates these conditions **simultaneously**, while authorization, CSRF protection, session management, and TLS remain additional responsibilities of the application and infrastructure.