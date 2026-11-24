# Cookie Size Limits and Sensitive Data in Sessions

## 1. Two storage places easily confused: cookies and HttpSession

In **Spring Boot Web MVC on Servlet**, applications can preserve state across HTTP requests via **session cookies**. However, cookies and `HttpSession` play distinct roles:

- **Cookie:** a name–value pair held by the browser/client, received from a **Set-Cookie** response header and sent back in a **Cookie** request header when Domain, Path, Secure, SameSite, and other policies permit.
- **HttpSession:** an attribute container managed **on the server side** by the Servlet container or a session repository such as Spring Session. Data may reside in RAM, Redis, or JDBC depending on deployment.
- **Session ID cookie** (typically **JSESSIONID** on default Servlet containers) should hold only an **opaque, random, unpredictable session identifier**. It lets the server look up the right session. Attributes in `HttpSession` **are not automatically copied into the cookie**.
- **Database/object storage** is the right place for user profiles, documents, large files, and durable data; the session should hold only small IDs/references when genuinely needed.

Consequently, a value larger than 4 KiB can still live inside `HttpSession` without enlarging `JSESSIONID`. That **does not mean `HttpSession` has unlimited resources or is inherently safe**. This lesson explains both cookie technical limits and the security, memory, and lifecycle limits of session data.

Scope: **Spring Boot 3.3.x + Java 17+ + Spring MVC/Servlet**, using cookie tracking. **Spring WebFlux WebSession** is a different API model; cookie and privacy principles still apply, yet do not copy `HttpSession` code directly into WebFlux.

## 2. Cookie size limits: understand bytes and browser capabilities

### 2.1. The 4,096-byte benchmark in RFC 6265

RFC 6265, Section 6.1, states the minimum capabilities user agents **SHOULD** support:

| Recommended limit | Value |
| --- | ---: |
| Size per cookie, including name, value, and attributes as counted by the RFC | **At least 4,096 bytes** |
| Cookies per domain | **At least 50** |
| Total cookies in user agent | **At least 3,000** |

These are **recommended minimum support levels**, not identical hard caps across Chrome, Firefox, Safari, or every version. Browsers may compute lengths slightly differently, block cookies, evict cookies when full, or omit cookies due to privacy settings. Servers must cope gracefully when clients **do not store or send** cookies.

In practice, “cookies have roughly a 4 KiB limit” means **do not rely on cookies to carry long data**. A typical session ID should be far smaller than that threshold. Never treat 4 KiB as a budget to fill up.

Source: https://www.rfc-editor.org/rfc/rfc6265.html#section-6.1

### 2.2. Java `String.length()` is not cookie byte size

**String.length()** counts UTF-16 code units; cookies transport encoded bytes. For example:
- **theme=dark**: 10 ASCII characters, 10 UTF-8 bytes.
- **note=Tiếng Việt**: 15 UTF-16 code units, **19 UTF-8 bytes** due to the Vietnamese diacritics.

When serializing a cookie, data may also undergo percent encoding, Base64URL encoding, or other formatting. A Unicode string on screen can consume more bytes than its character count. Signing or chunk metadata adds even more overhead.

To verify real limits, measure **`name=value` after encoding plus `Set-Cookie` attributes**, and test on target browsers. Never check `String.length()` alone and claim “under 4 KiB so it is guaranteed valid”.

### 2.3. Many small cookies still add up to huge headers

Multiple cookies matching a URL are sent together in the same request:

~~~http
Cookie: JSESSIONID=<opaque-id>; theme=dark; lang=vi; consent=accepted
~~~

The **Request `Cookie` header** carries `name=value` pairs, typically omitting `Set-Cookie` attributes like `HttpOnly`/`Secure`/`Expires`. Still, the **combined cookies** can total many KiB. Every scope-matching request transmits them, including endpoints that never use those values.

Consequences of oversized cookies/headers:
1. Higher request byte size, transmission time, and proxy/server parsing overhead.
2. Hitting **request header size** limits in ingress, proxies, or web containers, returning **400** or **431 Request Header Fields Too Large** depending on configuration.
3. Browsers may reject overly long `Set-Cookie` headers or evict older cookies.
4. Logging layers that accidentally log the full `Cookie` header can leak session tokens.

**HTTP 431** indicates oversized request headers, **not** proof that a single cookie exceeded 4 KiB. Likewise, an oversized single cookie might never trigger 431 because the browser may reject it as soon as `Set-Cookie` arrives.

### 2.4. Why not split one JSON payload across multiple cookies?

Splitting a profile JSON into `cookie_1`, `cookie_2`, and `cookie_3` sidesteps a **single cookie's** cap while leaving total HTTP header size just as bloated. One chunk can be evicted by the browser, clients can tamper with chunks, and you must manage integrity, versioning, TTLs, and reassembly order. Thus the cleaner design is usually:
- Cookies: small identifiers or tiny byte-sized preferences only.
- Server: minimal TTL-bounded state.
- Database/storage: large queryable or long-lived objects.

## 3. HttpSession is not bound by the 4 KiB cookie cap, yet faces server limits

In Spring MVC, code may run:

~~~java
// Fragment in a Controller/Servlet; not a standalone program.
HttpSession session = request.getSession(true);
session.setAttribute("cartId", "cart-456");
session.setAttribute("itemCount", 3);
~~~

Model:

~~~text
Browser                                   Server-side state
Cookie: JSESSIONID=ID_A  -------->       HttpSession[ID_A]
                                            cartId="cart-456"
                                            itemCount=3
~~~

When the client sends `JSESSIONID` on another request, the container/session repository looks up the ID to retrieve attributes. The browser **does not receive** `cartId` and `itemCount` inside the cookie.

**getSession(true)**: returns an existing valid session or creates one if absent. **getSession(false)**: only reads an existing valid session, returning `null` if none exists. **invalidate()** invalidates the session.

Still, stuffing long strings, files, or full entities into the session pushes costs onto the store:
- **In-memory container:** heap usage, garbage collection, metadata, and concurrent session counts.
- **Spring Session Redis/JDBC:** serialization/deserialization CPU, network I/O, Redis RAM or DB storage, replication, timeouts, backups, and object compatibility.
- **Multiple replicas:** local sessions on instance A do not automatically exist on B simply because the browser sends the same cookie.

For instance, **10,000 sessions × 20 KiB payload ≈ 195.3 MiB** of raw payload alone; actual usage is higher due to object overhead, metadata, and copies. Measure via heap/metrics or serialized byte sizes rather than treating that back-of-the-envelope figure as exact.

**Never** treat `HttpSession` as a database, global cache, or upload storage. A 5 MiB file is still heavy data even though it never enters `JSESSIONID`.

## 4. What data should and should not live in a session

| Data type | Typically suitable choice | Reason |
| --- | --- | --- |
| Random session ID | `HttpOnly`/`Secure` session cookie | Client carries only the state lookup key |
| Theme, locale, non-sensitive options | Very small cookie or preference store | Expendable; validate values |
| Cart ID, item count, short workflow flags | `HttpSession`/session cache | Temporary, small, TTL-bounded state |
| Complete personal profile | Database / identity service | Authorization, updates, retention |
| Lists of thousands of products | Database / dedicated cache | Do not duplicate per session |
| Images, PDFs, uploads, binary payloads | Private file/object storage | Avoid blowing heap/session store |
| Passwords, unprotected OTPs, API keys, private keys | Policy-compliant credential/secret store | Never store casually in sessions or cookies |
| Authorization state | Spring Security or identity policy | Never trust a `role=admin` cookie |
| JWT/JWS carrying heavy PII | Avoid; keep tokens minimal when genuinely needed | Signing does not hide payload; tokens can bloat headers |
| Data that must survive restarts | DB/object store or proper session repository | Local sessions can be lost |

**Sensitive data inside `HttpSession` also needs protection.** Spring Security may store `SecurityContext` under framework mechanisms for session-based auth, yet business code should avoid stuffing extra passwords, access tokens, raw secrets, or unnecessary full user profiles into the session.

**Store IDs, not whole objects:** a session can hold a `reportId`; when the report is needed, the backend fetches it from the datastore, verifies ownership and permissions, and then returns the result.

## 5. Cookies do not inherently provide confidentiality or integrity

### 5.1. HttpOnly, Secure, and SameSite solve different problems

- **HttpOnly**: restricts standard JavaScript from reading the cookie via `document.cookie`, yet **does not encrypt the value**; the browser owner and backend can still view it.
- **Secure**: requires the browser to send the cookie over secure connections, typically HTTPS; does not enable TLS by itself and does not encrypt cookies stored on the user's device.
- **SameSite**: restricts sending cookies in certain cross-site contexts. It is **defense-in-depth for CSRF**, not a replacement for CSRF tokens or origin validation.
- **Domain/Path**: determines cookie-sending scope; **not** business access control.
- **Max-Age/Expires**: client-side cookie lifetime; **distinct** from server idle timeout.

Dangerous example:

~~~http
Set-Cookie: userProfile={"email":"private@example.org"}; Path=/; HttpOnly; Secure
~~~

Even with `HttpOnly` and `Secure`, `userProfile` sits on the client and is not encrypted. Never put personal data, ID numbers, passwords, payment details, or credentials into plain cookies.

### 5.2. Signed cookies differ from encrypted cookies; JWTs are not secret by default

- **Signed cookies**: prevent payload tampering if the signature is verified properly, yet the payload **remains readable**.
- **Encrypted/authenticated cookies**: require key management, nonces, rotation, replay protection, expiry, and size limits. Encryption does not turn cookies into unlimited storage.
- **JWT JWS**: payload is Base64URL-encoded and signed; it is **not** encrypted automatically. Anyone holding a signed-only JWT can decode and read its claims.
- **Opaque session ID**: reveals no user information from the ID itself; the server holds associated state behind it.

Do not invent custom crypto/cookie schemes when Spring Security and the session framework already solve the problem. If a JWT carries permissions, address token expiration, revocation, and stale privileges; a once-valid `"admin"` claim is not a permanent permission contract.

### 5.3. Session cookies must be protected like bearer secrets

Anyone holding a valid session ID can hijack the session in systems relying on that ID. Therefore:
1. Use random IDs generated by the framework/container, never `email` or `userId`.
2. Enforce HTTPS throughout the session; `Secure` + `HttpOnly` in production.
3. Use appropriate `SameSite` plus CSRF protection for state-changing actions.
4. Defend against XSS, session fixation, and token leakage.
5. Invalidate on logout; rotate session IDs upon privilege elevation via the framework.
6. Never put session IDs into URLs, logs, analytics, or shared stack traces.
7. Narrow cookie `Domain`/`Path` to real needs; cookies are **not** isolated by TCP port.

## 6. Why can sensitive data inside HttpSession still leak?

“Server-side” does not mean “nobody can ever read it”. For example:
- Code logs all session attributes or `SecurityContext` objects containing user details.
- Heap dumps, debug endpoints, or crash reports expose data sitting in RAM.
- A Redis/DB session store has weak ACLs, lacks TLS where needed, or has unprotected backups.
- A user profile attribute is mistakenly returned by an API to the wrong request due to an authorization bug.
- Session ID theft or session fixation lets an attacker access data under the right ID for the wrong user.
- Serialization stores giant unneeded object graphs; backups retain data far too long.
- Stale permissions in a session let a user whose role was revoked keep accessing resources.

Corresponding mitigations:
- Minimize attributes; store small keys rather than large objects.
- Enforce TTLs/idle timeouts and clean up attributes after workflows finish.
- Protect session stores with ACLs, encryption, TLS, and proper backup retention policies.
- Never log cookies or sensitive session contents; lock down heap dumps and debug endpoints.
- Use Spring Security for authentication/authorization and refresh/invalidate when privileges change.
- Enforce authorization on every sensitive operation rather than trusting an old flag in the session.
- Never serialize JPA/Hibernate entities with lazy relations into sessions without an explicit versioning/serialization plan.

Small, “unguessable” cookie IDs defend against guessing; they **do not** stop an attacker who stole a real ID. Security requires defense in depth.

## 7. Session timeout is not cookie expiry

A cookie with **Max-Age=24h** can remain in the browser while the server `HttpSession` expires after **15 minutes** of inactivity. The browser then sends the old cookie, yet the server has no valid state left. Conversely, if the browser deletes the cookie first, the server may still hold state until TTL while the client can no longer reconnect to it.

Distinguish:
- Cookie `Max-Age`/`Expires`: client side.
- `HttpSession` idle timeout/invalidation: server side.
- Session store TTL/eviction: repository side.
- Logout: must invalidate server-side state, not just delete the client-side cookie.

Closing the browser is not always proof a session was cleared: browsers have session-cookie restore features. Never treat “closing the tab” as a secure logout mechanism.

### 7.1. Multi-replica deployments: valid cookie, missing session

If Instance A holds a local `HttpSession` and Instance B does not, a load balancer routing a request from A to B causes state loss even though the cookie is completely valid. Options include sticky sessions/affinity, a shared session repository such as Spring Session Redis/JDBC, or stateless design if business rules allow. Each carries its own costs and risks.

When using Spring Session, the cookie may be named **SESSION** instead of `JSESSIONID` under `DefaultCookieSerializer`. Do not hardcode a single name when checking whether the app has a session.

## 8. Where does Spring Boot configure cookies and sessions?

For Spring Boot 3.3 on the Servlet stack, a reference configuration for **HTTPS production**:

~~~yaml
server:
  servlet:
    session:
      tracking-modes: cookie
      timeout: 20m
      cookie:
        http-only: true
        secure: true
        same-site: lax
        path: /
~~~

Explanation:
- **tracking-modes: cookie**: uses cookies for session binding rather than URL session tracking.
- **timeout**: server-side inactivity timeout; does not set cookie size limits.
- **http-only**: reduces risk of JS reading the ID.
- **secure**: browser sends only over secure connections; production requires HTTPS and proper reverse proxy/trusted header settings.
- **same-site**: helps block certain cross-site requests; CSRF protection is still required.
- **path**: choose a suitable URL scope; avoid unnecessarily broad paths if the app lives under a context path.

The **server.servlet.session.cookie** properties primarily configure the **session cookie**, and do not automatically apply to **custom cookies**. For custom cookies, use Spring's **ResponseCookie** or an appropriate `SameSite` configuration mechanism. With Spring Session, verify the actual `CookieSerializer`/repository.

**The local HTTP demo** in the next section **does not enable `Secure`** so `curl` over localhost can send cookies back. Never copy that local config to production.

## 9. Runnable Java 17 Spring Boot MVC example

The sample app proves:
1. `GET /api/state` does not create a session when none exists.
2. `POST /api/session/demo` stores an **8,192-character ASCII String in server-side `HttpSession`** purely to contrast against the 4 KiB cookie threshold.
3. `POST /api/preference` sets a small **theme=dark** cookie.
4. Repeating `GET` with a cookie jar retrieves both the session and `theme`.
5. `DELETE /api/session/demo` invalidates the session without deleting the `theme` cookie.

This is a **technical demonstration**, not a recommendation to store 8 KiB or sensitive data in production sessions. In real apps, keep small IDs in sessions and large data in a DB/object store.

### 9.1. Structure and `pom.xml`

~~~text
cookie-session-budget/
├── pom.xml
└── src/main/
    ├── java/com/example/cookiebudget/
    │   └── CookieSessionBudgetApplication.java
    └── resources/application.yml
~~~

**pom.xml**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>cookie-session-budget</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
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
~~~

**src/main/resources/application.yml**, for local HTTP only:

~~~yaml
server:
  port: 8080
  servlet:
    session:
      tracking-modes: cookie
      timeout: 15m
      cookie:
        http-only: true
        same-site: lax
        path: /
~~~

Do not enable `Secure` on local HTTP. Production requires HTTPS and **server.servlet.session.cookie.secure: true**, plus `Secure` on custom cookies needing protection.

### 9.2. Complete single-file Java code

**src/main/java/com/example/cookiebudget/CookieSessionBudgetApplication.java**:

~~~java
package com.example.cookiebudget;

import java.time.Duration;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseCookie;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.CookieValue;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class CookieSessionBudgetApplication {
    public static void main(String[] args) {
        SpringApplication.run(CookieSessionBudgetApplication.class, args);
    }
}

@RestController
class BudgetController {

    private static final String KEY = "demoText";
    private static final int DEMO_LENGTH = 8192;

    @GetMapping(path = "/api/state", produces = MediaType.TEXT_PLAIN_VALUE)
    String state(HttpServletRequest request,
                 @CookieValue(name = "theme", required = false) String theme) {
        HttpSession session = request.getSession(false);
        Object data = session == null ? null : session.getAttribute(KEY);
        int length = data instanceof String value ? value.length() : 0;

        String safeTheme = "dark".equals(theme) || "light".equals(theme)
                ? theme : "absent";

        return "sessionActive=" + (session != null)
                + ", storedChars=" + length
                + ", theme=" + safeTheme + "\n";
    }

    @PostMapping(path = "/api/session/demo",
                 produces = MediaType.TEXT_PLAIN_VALUE)
    String demo(HttpServletRequest request) {
        HttpSession session = request.getSession(true);
        session.setAttribute(KEY, "x".repeat(DEMO_LENGTH));
        return "storedChars=" + DEMO_LENGTH + "\n";
    }

    @PostMapping(path = "/api/preference",
                 produces = MediaType.TEXT_PLAIN_VALUE)
    ResponseEntity<String> preference() {
        ResponseCookie cookie = ResponseCookie.from("theme", "dark")
                .path("/")
                .httpOnly(true)
                .sameSite("Lax")
                .maxAge(Duration.ofDays(1))
                .build();

        return ResponseEntity.ok()
                .header(HttpHeaders.SET_COOKIE, cookie.toString())
                .body("themeCookieSet=dark\n");
    }

    @DeleteMapping(path = "/api/session/demo",
                   produces = MediaType.TEXT_PLAIN_VALUE)
    String logoutDemo(HttpServletRequest request) {
        HttpSession session = request.getSession(false);
        if (session != null) {
            session.invalidate();
        }
        return "sessionInvalidated=true\n";
    }
}
~~~

**Detailed explanation:**
- **getSession(false)** inside GET does not auto-create state.
- **getSession(true)** inside POST creates a session if absent; if the client already holds a valid session, it reuses it.
- **session.setAttribute** stores the 8,192-character String on the server, **without** putting 8,192 characters into the cookie.
- The `theme` cookie is independent of `JSESSIONID` and holds only a non-sensitive preference; `HttpOnly` is set because this demo has no JS needing to read it.
- **@CookieValue** receives client-supplied values; it accepts only `dark`/`light` and never uses any cookie as a role or permission.
- Never log `session.getId()`, or put it in URLs or responses.
- **invalidate()** ends the old server session; the `theme` cookie continues on its own lifecycle.
- The demo omits Spring Security; real authenticated apps should use the framework to manage login/logout, CSRF, fixation, and authorization.

### 9.3. Build and run

In the **cookie-session-budget** directory, with Java 17+, Maven, and port 8080 free:

~~~bash
mvn package
java -jar target/cookie-session-budget-1.0.0.jar
~~~

Run the curl commands below in another terminal. On Windows PowerShell, use **curl.exe** instead of the `curl` alias so standard flags work.

**Step 1 — no cookie/session yet:**

~~~bash
curl -s http://localhost:8080/api/state
~~~

Body:

~~~text
sessionActive=false, storedChars=0, theme=absent
~~~

**Step 2 — create a session and save Set-Cookie into the jar:**

~~~bash
curl -i -c demo-cookies.txt -X POST \
  http://localhost:8080/api/session/demo
~~~

Body:

~~~text
storedChars=8192
~~~

The response typically includes **Set-Cookie: JSESSIONID=...** holding a small random ID, **not** the entire 8,192 characters. `demo-cookies.txt` holds tokens, so never commit it to Git or post it in logs or public chats.

**Step 3 — send the session ID and receive the additional theme cookie:**

~~~bash
curl -i -b demo-cookies.txt -c demo-cookies.txt -X POST \
  http://localhost:8080/api/preference
~~~

Body:

~~~text
themeCookieSet=dark
~~~

**Step 4 — GET with both cookies:**

~~~bash
curl -s -b demo-cookies.txt http://localhost:8080/api/state
~~~

Body:

~~~text
sessionActive=true, storedChars=8192, theme=dark
~~~

**Step 5 — invalidate the session:**

~~~bash
curl -s -b demo-cookies.txt -X DELETE \
  http://localhost:8080/api/session/demo
curl -s -b demo-cookies.txt http://localhost:8080/api/state
~~~

Bodies in order:

~~~text
sessionInvalidated=true
~~~

~~~text
sessionActive=false, storedChars=0, theme=dark
~~~

Explanation: the old server session was invalidated, while the independent `theme` custom cookie is still sent by the client. These are the **bodies of each HTTP response**, not the full stdout when running curl with `-i`.

Do not place all session attributes into JSON responses in the demo, because the goal is verifying **where data is stored**. If code returns profile details in a response body, that is an API design choice, not Servlet exporting the session through cookies.

## 10. Standalone Java 17: proving `String.length()` differs from UTF-8 byte length

Create file **CookieBytesDemo.java**:

~~~java
import java.nio.charset.StandardCharsets;

public class CookieBytesDemo {
    public static void main(String[] args) {
        String ascii = "theme=dark";
        String unicode = "note=Tiếng Việt";

        System.out.println("asciiChars=" + ascii.length());
        System.out.println("asciiBytes=" +
                ascii.getBytes(StandardCharsets.UTF_8).length);
        System.out.println("unicodeChars=" + unicode.length());
        System.out.println("unicodeBytes=" +
                unicode.getBytes(StandardCharsets.UTF_8).length);
    }
}
~~~

Compile and run with JDK 17:

~~~bash
javac -encoding UTF-8 CookieBytesDemo.java
java CookieBytesDemo
~~~

**Exact** stdout:

~~~text
asciiChars=10
asciiBytes=10
unicodeChars=15
unicodeBytes=19
~~~

This measures raw UTF-8 bytes of the chosen string, **excluding** percent encoding or `Set-Cookie` attribute names/values. Never use real user data to test size thresholds.

## 11. Detecting cookie/session bloat and leaks

### 11.1. Useful metrics

| Observation | Meaning |
| --- | --- |
| Total `Cookie` header bytes and cookies per request | Spot header bloat |
| HTTP 400/431 at proxy or container | Separate header limits from app logic |
| Cookies marked blocked in DevTools | Inspect size, Domain, Path, Secure, SameSite |
| Active session count and idle times | Estimate footprint and timeouts |
| Heap/GC, session attribute counts | Spot heavy in-memory sessions |
| Serialized session bytes in Redis/JDBC | Spot large objects, network/store cost |
| Store evictions, deserialization failures, backup sizes | Spot scaling/upgrade risks |
| Session invalidation/logout failures | Detect unrevoked sessions |

**Never record raw session IDs or cookie values as metric labels**; doing so leaks bearer secrets and creates unbounded metric cardinality. Never log raw `Cookie` headers for “easier debugging”. Use independent correlation IDs, masked logs, and controlled retention.

### 11.2. Common issues

| Situation | Analysis | Fix |
| --- | --- | --- |
| Browser omits newly received cookie | Cookie rejected/evicted or scope mismatch | Check DevTools, size, Secure/SameSite/Domain/Path |
| Many cookies, API returns 431 | Total request headers exceed limit | Shrink cookie data, measure total headers, check proxy limits |
| Redis RAM grows despite tiny cookies | `HttpSession` serialized payload is large | Store references only; limit counts and TTL |
| Pod A has session, Pod B does not | Local sessions not shared | Shared store or affinity with clear trade-offs |
| Signed JWT leaks email in payload | Signed without encryption | Minimize claims or use opaque/encrypted tokens when needed |
| `role=admin` cookie can be forged | Backend trusts client-supplied data | Perform authorization from trusted framework/store |
| `HttpOnly` enabled yet CSRF still works | Browser attaches cookies automatically | Enforce CSRF protection and SameSite matching threat model |
| Logout deletes cookie yet old token still works | Server did not invalidate/revoke | Invalidate session server-side |
| Session alive yet cookie expired | Two separate lifecycles | Design fallback/re-login behavior |
| ORM entity in session breaks after deploy | Serialization/schema changed across versions | Store small IDs/values and plan migrations |

## 12. Security and operations checklist

- Keep cookies **short and few**; never put profiles, files, or secrets in cookies.
- Measure encoded byte lengths and **total request headers**, not just a single cookie.
- Session IDs must be unpredictable framework-issued identifiers; never put IDs in URLs or logs.
- Enable HTTPS, `Secure`, `HttpOnly`, `SameSite`, and narrow scopes for production session cookies.
- XSS/CSRF defenses and authorization are separate requirements; cookie flags do not replace them.
- Sensitive data stored server-side still requires data minimization, ACLs, TLS, encryption/backup policies, and retention limits.
- Keep session attributes small, clean them up early, and enforce timeouts; move large data to DB/object storage.
- Never trust client-sent cookies; validate preferences/identifiers and never grant permissions from a role cookie.
- With distributed Spring Session, verify TTLs, serialized byte sizes, version compatibility, store health, and rollout plans.
- Logout must invalidate/revoke server-side and clear cookies with matching scope when needed.
- Test deleted cookies, tampered cookies, blocked cookies, expired sessions, multiple cookies, request header limits, and multi-replica routing.
- Collect aggregate metrics without capturing tokens or sensitive attributes.

## 13. Reinforcement exercises

**1. `HttpSession` holds a 12 KiB String. Must the browser store a 12 KiB cookie?**  
No under standard server-side `HttpSession`. The cookie holds only the session ID; the String stays on the server.

**2. Why can 15 cookies of 1 KiB each still cause a request error?**  
Combined headers can exceed proxy or server header limits, even though each individual cookie is below roughly 4 KiB.

**3. Do `HttpOnly` and `Secure` hide an email stored directly in a cookie?**  
No. `HttpOnly` restricts JS access and `Secure` mandates secure transport; neither encrypts the value.

**4. Is an email claim inside a signed JWT (JWS) encrypted?**  
No by default; signed payloads can be decoded. Integrity is not confidentiality.

**5. Cookie `Max-Age` is 1 day, `HttpSession` timeout is 15 minutes. After 2 hours idle, does the old session survive?**  
Usually no if the server expired the session, even though the browser still holds the cookie.

**6. Why shouldn't you store a `byte[]` PDF in `HttpSession`?**  
It bloats heap or serialized stores, multiplies by session count, and drives heavy GC, network, and replication overhead.

**7. A `role=admin` cookie edited in DevTools is trusted by the backend. What is the bug?**  
Trusting unauthenticated client data; authorization must happen through proper server-side/framework controls.

**8. Why isn't deleting the cookie on logout enough?**  
A previously copied session ID could still be replayed unless the server session is invalidated.

**9. Does Spring Session Redis remove memory limits?**  
No; it shifts the footprint to Redis, network I/O, serialization, and store capacity limits.

**10. If the browser sends `JSESSIONID` yet the request hits an instance without the session, is the cookie wrong?**  
Not necessarily; local sessions may simply not be shared across replicas.

## 14. Conclusion

**Cookies are constrained by browsers and HTTP headers**, so they should carry only an opaque session ID or small non-sensitive preferences. **Server-side `HttpSession` avoids the 4 KiB cookie cap**, yet remains bounded by RAM, storage, serialization, timeouts, and security risks.

The sound pattern is usually: **Small cookie → Secure session ID → Minimal session state → Large/sensitive data in a protected database or dedicated store**. Picking the right storage tier, bounding lifetimes, and enforcing authorization matter far more than cramming extra data into cookies or sessions.

## Official references

- RFC 6265 §6.1 — Cookie limits: https://www.rfc-editor.org/rfc/rfc6265.html#section-6.1
- MDN — Set-Cookie: https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Set-Cookie
- MDN — HTTP Cookies: https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Cookies
- OWASP — Session Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
- OWASP — CSRF Prevention: https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html
- Spring Boot 3.3 — Servlet Web Applications/SameSite: https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html
- Spring Boot 3.3 — Application Properties: https://docs.spring.io/spring-boot/3.3/appendix/application-properties/
- Jakarta Servlet 6.0 — HttpSession: https://jakarta.ee/specifications/servlet/6.0/apidocs/jakarta.servlet/jakarta/servlet/http/HttpSession.html
- Spring Security — Session Management: https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html
