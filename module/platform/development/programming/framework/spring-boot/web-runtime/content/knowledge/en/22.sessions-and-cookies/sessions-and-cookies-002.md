# When Sessions Are Created and How Cookies Bind Them

## 1. Goal: understanding precisely “when is a session created?”

In a **Spring Boot application using Spring MVC/Servlet**, HTTP does not maintain state across requests by itself. Two requests sent to the same server are not automatically treated as coming from the same user. **HttpSession** allows the server to hold per-session data, while a **session cookie** lets the client send back an identifier so the server can find that exact session.

The core point of this lesson is to clearly distinguish three moments:

1. **The request arrives at the server:** not sufficient evidence to conclude the server has created an HttpSession. A stateless endpoint can respond without creating a session.
2. **The application or framework requests session creation:** for example, calling **request.getSession()** or **request.getSession(true)** when no valid session exists yet. At that point, the Servlet container creates an HttpSession on the server side.
3. **The session identifier is transferred to the client and sent back:** with cookie-based tracking, the response usually contains **Set-Cookie: JSESSIONID=...**; the browser stores the cookie and sends the **Cookie: JSESSIONID=...** header on subsequent requests if Domain, Path, Secure, and SameSite rules permit.

**A session is not a cookie.** A session is server-side state (or in a shared session store), whereas a cookie usually holds only an **unpredictable identifier** used to look up that state. An existing cookie does not prove the server-side session is still valid; conversely, a newly created session might not yet have had its cookie received/returned by the client.

This lesson focuses on the parent topic **Sessions and cookies**, the **Servlet HttpSession** mechanism, Spring Boot MVC, and how to verify behavior over HTTP. Do not apply this exact explanation to **Spring WebFlux WebSession** or stateless JWTs, as those are different models.

## 2. Diagram from first request to returning request

Assume the application uses Spring MVC + embedded Tomcat, cookie tracking, the default cookie name is usually **JSESSIONID**, and Spring Session is not installed. On a fresh browser:

~~~text
Client                               Spring Boot / Servlet container
  |                                            |
  | GET /api/catalog (no session needed)       |
  |------------------------------------------->|
  |         No call to create an HttpSession   |
  |<-------------------------------------------|
  | 200 OK; usually no session Set-Cookie      |
  |                                            |
  | POST /api/session/visit                    |
  |------------------------------------------->|
  |    Controller calls request.getSession(true)
  |    Container creates session S1, random ID |
  |<-------------------------------------------|
  | 200 OK                                     |
  | Set-Cookie: JSESSIONID=ID_S1; Path=/; ...  |
  |                                            |
  | Client stores ID_S1 if policy allows       |
  |                                            |
  | GET /api/session/status                    |
  | Cookie: JSESSIONID=ID_S1                   |
  |------------------------------------------->|
  |     Container looks up session by ID_S1    |
  |     request.getSession(false) returns S1   |
  |<-------------------------------------------|
  | 200 OK; data retrieved from session S1     |
  |                                            |
  | ... idle timeout, invalidate, or S1 lost   |
  |                                            |
  | GET /api/session/status                    |
  | Cookie: JSESSIONID=ID_S1 (may still exist) |
  |------------------------------------------->|
  |     No valid session found                 |
  |     getSession(false) returns null         |
  |<-------------------------------------------|
  | 200 OK; endpoint reports no active session |
~~~

**Why does the response have Set-Cookie while the request does not?** The **Set-Cookie** header goes **server → client**; the **Cookie** header goes **client → server**. The cookie is attached starting on the **next** request, after the client has received Set-Cookie, unless a prior session already existed.

In practice, the server may set a cookie at another point if a framework created the session earlier, or if another session tracking mechanism is used. The milestones above illustrate a **common explanatory sequence**, not a guarantee that every GET or every POST will behave identically regardless of middleware.

## 3. Servlet API controlling session creation vs. read-only lookup

**jakarta.servlet.http.HttpServletRequest** provides key methods:

| Call | Meaning | If no valid session exists |
| --- | --- | --- |
| request.getSession() | Get the current session, or create a new one if absent | **Creates a new one** |
| request.getSession(true) | Equivalent to getSession() for creation policy | **Creates a new one** |
| request.getSession(false) | Only get an existing valid session | Returns **null**; does not auto-create |
| request.getRequestedSessionId() | The ID the client supplied on the current request, if any | May be null or an expired/invalid ID |
| request.isRequestedSessionIdValid() | Whether the presented ID is valid in the current context | **false** if invalid/absent |
| request.isRequestedSessionIdFromCookie() | Whether the requested ID came from a cookie | **false** if no cookie ID was present |
| request.changeSessionId() | Change the ID of the existing session without replacing all attributes | Do not use if there is no current session |

Avoid confusing **request.getRequestedSessionId()** with **request.getSession(false).getId()**:
- **Requested session ID** is client-supplied information, which may be stale, forged, or invalid.
- **Current session ID** is the ID of a valid HttpSession returned by the container.
- When no session exists, calling getSession(false).getId() directly throws **NullPointerException**. Check for null first.
- When a request sends an old ID cookie, getRequestedSessionId() **may still return the old ID**, while isRequestedSessionIdValid() is false and getSession(false) is null.

### 3.1. Reading without creating: getSession(false)

~~~java
// Fragment in a Spring MVC Controller or Filter; not a standalone file.
HttpSession session = request.getSession(false);
if (session == null) {
    // No valid session yet: show guest state.
} else {
    Object cart = session.getAttribute("cart");
    // Read cart if it has been stored.
}
~~~

This is the right choice for endpoints that only want to **observe** state, such as checking whether a user has a temporary shopping cart. A pure product-viewing GET does not necessarily need to create a session if there is no state to store.

However, **merely having Controller code that avoids calling getSession(true)** does not prove the request creates no session. A Filter, framework component, JSP, CSRF mechanism, or authentication flow may already have created a session before the Controller is invoked.

### 3.2. Creating when needed: getSession(true)

~~~java
// Fragment in Spring MVC; should be used for actions that truly require state.
HttpSession session = request.getSession(true);
session.setAttribute("preferredLanguage", "vi");
~~~

If the request is already associated with a valid session, it **returns the existing session** rather than creating a second one just because `true` was passed. If none exists, it creates a new session, assigns an ID, and stores the attribute. Therefore, **“getSession(true) was called” does not mean “a brand-new session was definitely created”**.

### 3.3. What does HttpSession.isNew() tell you?

**session.isNew()** indicates that the session is new or the client has not yet joined the session with tracking information recognized by the container. It is helpful when analyzing an initial request, but it is **not** an absolute indicator of “the user just logged in”, “the session was created on this exact line of code”, or “the client will receive the cookie”.

If a client fails to send the cookie back due to cookie blocking, mismatched scope, or dropping cookies, every request calling getSession(true) **can** create a new session and `isNew()` will be true again. When logging out and creating a new session, “new session” also does not mean “new user”.

## 4. When is a session cookie issued?

When an application creates a new session and uses **COOKIE tracking**, the Servlet container typically adds **Set-Cookie** to the HTTP response to deliver the session ID. Illustrative example; the ID intentionally uses a placeholder symbol, not a real token:

~~~http
HTTP/1.1 200 OK
Set-Cookie: JSESSIONID=<opaque-id>; Path=/; HttpOnly; SameSite=Lax
Content-Type: text/plain;charset=UTF-8

active=true, visits=1
~~~

In a real response, the cookie name, Path, Secure, SameSite, Max-Age, and other attributes depend on configuration and container. Do **not** assume every response contains Set-Cookie or always has the same set of attributes.

### 4.1. Critical timing: before the response is committed

Response headers must be sent **before** a committed body. If an application tries to call getSession(true) **after the response has already been committed** in a situation that requires writing a new cookie, the container may be unable to create/bind the session as expected and the Servlet API may throw **IllegalStateException**. Create the session during a phase of request processing where headers can still be written, not late inside a stream that has already flushed the response.

Do not adopt a pattern of “wait until rendering finishes and only then create the session”; if the session serves the request's business logic, create or access it within a processing flow with a clear lifecycle.

### 4.2. When is a cookie sent on the next request?

The browser evaluates cookie scope and policy:

- **Host/Domain:** a cookie defaults to only the host that set it; a configured Domain can broaden it to eligible subdomains.
- **Path:** only sent to URL paths allowed by cookie matching rules; an app context path can affect the default Path.
- **Secure:** a Secure cookie is only sent over channels the browser considers secure, primarily HTTPS; do not expect Secure cookies to behave identically on local plain HTTP.
- **SameSite:** governs sending cookies in cross-site contexts.
- **Expires/Max-Age:** the cookie may expire on the client before the server session expires, or still exist after the server has deleted the session.
- **Browser policies:** cookie blocking, privacy settings, third-party restrictions, partitioning, and session restore behavior can alter sending.

**Cookies are not isolated by TCP port**, such as **localhost:8080** and **localhost:9090**. Two services on the same host can share cookie scope and the same cookie name if Path/Domain overlap, causing development conflicts. Port is not a scope attribute of HTTP cookies.

### 4.3. A session cookie does not mean the cookie holds session data

Do not store user objects, passwords, full shopping carts, or permissions inside **JSESSIONID**. The browser normally holds only an ID string. The server uses that ID to look up the **HttpSession** in the container's store or in a shared store when using Spring Session.

Anyone who obtains a valid session ID can impersonate the session if the system relies solely on that cookie for authentication. Therefore, the ID must be unpredictable, transmitted over HTTPS, never leaked via logs/query strings, have logout/timeout mechanisms, and be protected against fixation/hijacking.

## 5. HttpSession has a separate lifecycle from the cookie

In Servlet, **HttpSession** has the following properties and methods:

| Member | Meaning |
| --- | --- |
| session.getId() | ID of the current session; treat as sensitive data |
| session.getCreationTime() | Server-side session creation timestamp |
| session.getLastAccessedTime() | Most recent access timestamp recorded by the container |
| session.getAttribute(name) | Server-side session data |
| session.setAttribute(name, value) | Write an attribute into the session |
| session.removeAttribute(name) | Remove a specific attribute |
| session.getMaxInactiveInterval() | Maximum inactivity interval, in seconds |
| session.setMaxInactiveInterval(seconds) | Change the idle timeout for this session |
| session.invalidate() | Invalidate the current session and unbind attributes |
| session.isNew() | Check new/client-joined status |

**Idle timeout** is usually measured by the interval with no valid request associated with the session. A valid request can refresh the session's last-accessed time, even when business logic only reads; exact container tracking follows the Servlet lifecycle.

Distinguish three kinds of expiration:

1. **Browser-side cookie expires/disappears:** the client stops sending the ID, even though the server may still retain the session for some time.
2. **Server session expires or is invalidated:** the client may still send the old cookie, but the server finds no valid session.
3. **Login/system actively rotates the session ID:** the session may retain attributes, but the old ID is no longer valid; the client must receive/keep the new ID.

A **browser session cookie** usually has no fixed Max-Age/Expires; however, browsers have session-restore features upon reopening, so “closing the tab/browser” must not be treated as certain proof that the server has logged out or expired the session.

### 5.1. What happens when an old cookie is still sent?

~~~text
Cookie: JSESSIONID=ID_OLD
             |
             v
Container lookup session(ID_OLD)
             |
     +-------+--------+
     |                |
 Yes, still valid    No longer valid
     |                |
getSession(false)   getSession(false)
 -> existing session -> null
     |                |
Can continue using   getSession(true)
                     -> create new session ID_NEW
                     -> new Set-Cookie if needed
~~~

**A cookie sent by the browser does not recreate old contents by itself.** The session must exist in the appropriate store and remain valid. If the application uses an in-memory session store and restarts, the old cookie may still exist while the session is gone. Data loss and durability depend on the container/session repository and deployment configuration.

## 6. Running a practical example: one read-only request and one explicit session-creating request

The example below is a runnable **Spring Boot 3.3.13 + Spring MVC + Java 17 + Maven** project. It intentionally omits Spring Security/Spring Session so that **no external middleware creates a session**, allowing a clear view of `getSession(false)` versus `getSession(true)`. Responses return `text/plain` to avoid JSON formatting distractions.

### 6.1. Project structure

~~~text
cookie-session-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/cookiesession/
    │   └── CookieSessionDemoApplication.java
    └── resources/
        └── application.yml
~~~

**pom.xml:**

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
    <artifactId>cookie-session-demo</artifactId>
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

**src/main/resources/application.yml:**

~~~yaml
server:
  port: 8080
  servlet:
    session:
      timeout: 15m
      tracking-modes: cookie
      cookie:
        http-only: true
        same-site: lax
        path: /
~~~

**Explanation:** the demo uses cookie tracking, a target idle timeout of 15 minutes, HttpOnly, SameSite=Lax, and Path=/ on the local host. **Do not set `secure: true` in a localhost HTTP demo** so `curl` can send the cookie back normally. In HTTPS production environments, configure **server.servlet.session.cookie.secure: true**, use TLS, and configure reverse proxy/trusted forwarding appropriately. Timeout values and precision may be subject to Servlet container rounding rules.

### 6.2. Complete Java file

**src/main/java/com/example/cookiesession/CookieSessionDemoApplication.java:**

~~~java
package com.example.cookiesession;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class CookieSessionDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(CookieSessionDemoApplication.class, args);
    }
}

@RestController
class SessionController {

    @GetMapping(
            path = "/api/session/status",
            produces = MediaType.TEXT_PLAIN_VALUE
    )
    String status(HttpServletRequest request) {
        HttpSession session = request.getSession(false);

        if (session == null) {
            return "active=false, visits=0\n";
        }

        Integer visits = (Integer) session.getAttribute("visits");
        int count = visits == null ? 0 : visits;
        return "active=true, visits=" + count + "\n";
    }

    @PostMapping(
            path = "/api/session/visit",
            produces = MediaType.TEXT_PLAIN_VALUE
    )
    String visit(HttpServletRequest request) {
        HttpSession session = request.getSession(true);

        Integer visits = (Integer) session.getAttribute("visits");
        int next = (visits == null ? 0 : visits) + 1;
        session.setAttribute("visits", next);

        return "active=true, visits=" + next + "\n";
    }

    @PostMapping(
            path = "/api/session/logout",
            produces = MediaType.TEXT_PLAIN_VALUE
    )
    String logout(HttpServletRequest request) {
        HttpSession session = request.getSession(false);
        if (session != null) {
            session.invalidate();
        }
        return "active=false, visits=0\n";
    }

    @GetMapping(
            path = "/api/session/trace",
            produces = MediaType.TEXT_PLAIN_VALUE
    )
    String trace(HttpServletRequest request) {
        boolean clientSuppliedId = request.getRequestedSessionId() != null;
        boolean valid = request.isRequestedSessionIdValid();
        boolean fromCookie = request.isRequestedSessionIdFromCookie();

        return "clientSuppliedId=" + clientSuppliedId
                + ", valid=" + valid
                + ", fromCookie=" + fromCookie + "\n";
    }
}
~~~

Important details in the code:

- **GET /api/session/status** only calls **getSession(false)**. When there is no session, it does not auto-create one. It also does not send the ID back to the client in the body.
- **POST /api/session/visit** calls **getSession(true)**. The first call can create a session; subsequent calls with a valid cookie reuse that session. POST is used because it mutates the server-side counter.
- **POST /api/session/logout** calls **invalidate()** if a session exists. It **does not** create a new session in order to log out, and **does not** explicitly emit a browser cookie-deletion header; Section 9 discusses production logout.
- **GET /api/session/trace** inspects the ID presented by the client and its validity, **without printing the raw session ID** to avoid exposing tokens in logs, URLs, or responses.
- Do not use this session to authenticate real users in the demo. The session exists solely to record a simple attribute, the `visits` counter.

**Concurrency limitation:** the code uses `Integer` and increments via `getAttribute`/`setAttribute`, which is not an **atomic** increment if the same session receives multiple parallel requests. The demo uses sequential requests only; real applications need synchronization/atomic updates or a repository with appropriate concurrency control. `HttpSession` does not automatically guarantee that every operation on your mutable attributes is thread-safe.

### 6.3. Build and run

Open a terminal in the `cookie-session-demo` directory:

~~~bash
mvn package
java -jar target/cookie-session-demo-1.0.0.jar
~~~

Requires **JDK 17+**, Maven, and an available port 8080. Once the app is ready, use another terminal to send requests. On Windows PowerShell, invoke **curl.exe** instead of the `curl` alias if you want standard curl flags.

### 6.4. Test 1: read-only, no session yet

~~~bash
curl -i http://localhost:8080/api/session/status
curl -i http://localhost:8080/api/session/trace
~~~

Expected **Body** when the client supplies no cookie:

~~~text
active=false, visits=0
~~~

~~~text
clientSuppliedId=false, valid=false, fromCookie=false
~~~

In the demo app with no middleware auto-creating sessions, responses from **status/trace** do not need a session `Set-Cookie`. Actual server headers, timestamps, and Content-Type may vary by container; the key point is that **no session creation was triggered**.

### 6.5. Test 2: create a session and save the cookie to a cookie jar

~~~bash
curl -i -c session-cookies.txt -X POST \
  http://localhost:8080/api/session/visit
~~~

Body:

~~~text
active=true, visits=1
~~~

The HTTP response typically contains a header similar to (the ID here is an illustrative placeholder):

~~~http
Set-Cookie: JSESSIONID=<opaque-session-id>; Path=/; HttpOnly; SameSite=Lax
~~~

The **`-c` flag** of curl saves cookies issued by the server into the cookie jar file. Use a consistent terminal or working directory so the exact same file is read back. If a prior HTTP request somehow created a session or a browser sent an existing valid cookie, `visits` will not necessarily be 1; the experiment assumes a freshly started process and a client with no prior session.

### 6.6. Test 3: send the existing cookie to link to the exact same session

~~~bash
curl -i -b session-cookies.txt \
  http://localhost:8080/api/session/status

curl -i -b session-cookies.txt \
  http://localhost:8080/api/session/trace
~~~

Corresponding bodies:

~~~text
active=true, visits=1
~~~

~~~text
clientSuppliedId=true, valid=true, fromCookie=true
~~~

The **`-b` flag** instructs curl to load matching cookies from the jar for the domain/path. The container receives the ID, looks up the current session, and returns the stored attributes. Evidence of “the same session” here is not that the server received a second request, but that **the valid cookie allowed retrieving the `visits=1` state**.

Try incrementing the counter with a request reusing the cookie:

~~~bash
curl -i -b session-cookies.txt -c session-cookies.txt -X POST \
  http://localhost:8080/api/session/visit
~~~

Expected body:

~~~text
active=true, visits=2
~~~

If you omit **`-b session-cookies.txt`** on the second POST, curl does not send the old cookie and the server may create a **new session** with `visits=1`. Passing `-c` only saves **response** cookies; it does not automatically send existing cookies unless `-b` or an equivalent option is used.

### 6.7. Test 4: invalidate the session and resend the old cookie

~~~bash
curl -i -b session-cookies.txt -X POST \
  http://localhost:8080/api/session/logout

curl -i -b session-cookies.txt \
  http://localhost:8080/api/session/status
~~~

Bodies of the two responses in the demo:

~~~text
active=false, visits=0
~~~

~~~text
active=false, visits=0
~~~

The old session was **invalidate()**d on the server; if the client still sends the old cookie, `getSession(false)` does not retrieve the invalidated session. When calling **GET /api/session/trace** with the old cookie, the result is typically **clientSuppliedId=true, valid=false, fromCookie=true**. Still, do not assume a fixed client/browser behavior for cookies after logout; frameworks or containers may apply additional cookie logic under extended configurations.

Next, try **POST /api/session/visit** with the old cookie: **getSession(true)** may create a new session and issue a **new JSESSIONID**. The old cookie does not resurrect attributes of the destroyed session.

### 6.8. Test 5: without a cookie, requests have no built-in “memory”

Open a new cookie jar or run:

~~~bash
curl -i -X POST http://localhost:8080/api/session/visit
curl -i -X POST http://localhost:8080/api/session/visit
~~~

Each curl command without `-b` fails to return the ID from the previous command, so in the typical demo flow each request creates a **new session with `visits=1`**. Real browsers normally retain cookies automatically, so their behavior differs from curl when no cookie jar is used.

To view all headers, use **curl -i**; to view only the body, use **curl -s**. When practicing, distinguish illustrative bodies from actual curl stdout (which includes the progress meter or headers if enabled).

## 7. Cases where a session appears “earlier than expected”

When a real application returns `JSESSIONID` immediately after the very first GET, do not rush to conclude that Servlet creates a session for every request. Find the code/framework that requested a session:

### 7.1. A Filter, Interceptor, Controller, or view calls getSession()

A Filter calling `request.getSession()` just to read an attribute **accidentally creates a session**. A Controller or argument resolver can also trigger session retrieval when needed. When you only want to check existence, use **getSession(false)** wherever possible.

~~~java
// WRONG if the goal is only to check an existing state:
HttpSession s = request.getSession();
Object flag = s.getAttribute("flag");

// RIGHT for non-creating reads:
HttpSession existing = request.getSession(false);
Object flag = existing == null ? null : existing.getAttribute("flag");
~~~

Both snippets are **fragments** requiring `HttpServletRequest` and an `HttpSession` import; they are not standalone Java files.

### 7.2. JSPs and session-backed model mechanisms

A JSP page with **session support** enabled by default in many setups, or a framework storing model attributes in `HttpSession`, can cause a session to appear during rendering. Check JSP tags/directives and any usage of **@SessionAttributes**. Do not confuse **@SessionAttribute** (reading an attribute) with **@SessionAttributes** (managing model attributes associated with an interaction flow).

### 7.3. Spring Security may create a session when needed

Spring Security supports multiple policies via **SessionCreationPolicy**:

| Policy | Role in Spring Security |
| --- | --- |
| ALWAYS | Proactively creates an HttpSession |
| IF_REQUIRED | Creates only when Security needs one for configured mechanisms |
| NEVER | Security does not create one itself, though it may use an existing session |
| STATELESS | Security does not create or use HttpSession to obtain SecurityContext |

**This is a Spring Security policy**, not an application-wide ban on the Servlet API. Even with `SessionCreationPolicy.STATELESS`, business code directly calling **request.getSession(true)** can still create an `HttpSession`. Conversely, a flow using cookie-based login, a CSRF token repository, or saved requests may require a session depending on the specific policy and configuration.

The following configuration fragment expresses stateless intent for the Security layer, **not a standalone project**:

~~~java
http.sessionManagement(session ->
        session.sessionCreationPolicy(SessionCreationPolicy.STATELESS)
);
~~~

Requires `HttpSecurity` and the `SessionCreationPolicy` import inside an appropriate `SecurityFilterChain`. Do not copy this fragment into a session-based demo application where you want to observe cookies working: stateless Security and session-based applications serve two different goals.

### 7.4. Login redirects and session fixation

Upon successful login, a security framework may **change the session ID** to prevent session fixation. As a result, the user remains logged in during a valid flow while a new ID cookie is issued; do not assume a single session ID must stay constant from initial guest visit through logout.

Servlet supports **request.changeSessionId()** when a valid session already exists, while Spring Security provides built-in session fixation protection. To stay safe, **let Spring Security manage authentication, ID rotation, and logout** under standard configuration rather than manually using a session ID as a login ticket.

## 8. Spring Boot configuration: timeout and cookie policies

Boot 3.3 properties for Servlet sessions:

| Property | Example | Purpose |
| --- | --- | --- |
| server.servlet.session.timeout | 15m | Idle timeout of HttpSession |
| server.servlet.session.tracking-modes | cookie | Choose session tracking mode; cookie or other Servlet modes |
| server.servlet.session.cookie.name | JSESSIONID | Cookie name (when using container sessions) |
| server.servlet.session.cookie.path | / | Cookie path used to determine which requests carry the cookie |
| server.servlet.session.cookie.domain | app.example.com | Cookie domain if configured; do not broaden needlessly |
| server.servlet.session.cookie.http-only | true | Prevent normal JavaScript from reading the cookie via document.cookie |
| server.servlet.session.cookie.secure | true | Send only over secure channels; use with HTTPS in production |
| server.servlet.session.cookie.same-site | lax | Reduce cookie sending in certain cross-site contexts |
| server.servlet.session.cookie.max-age | 30m | Browser cookie lifetime, **distinct** from server idle timeout |

The default **server.servlet.session.timeout** documented by Boot 3.3 is **30m**, though this exercise uses 15m to clearly distinguish configuration changes. Do not assume all containers and session stores apply millisecond precision; Servlet containers may have their own granularity.

**Do not equate cookie max-age with session timeout**: you can have a cookie stored for 30 minutes while the server session expires after 15 minutes of inactivity, or a cookie that expires after 5 minutes while the server session remains alive. In the latter case, new requests cannot resume the session once the client has lost the ID.

### 8.1. SameSite in practice

- **Strict:** restricts cookies more tightly in cross-site scenarios, which can affect links coming from external sites.
- **Lax:** generally fits websites with standard navigation, though it does not guarantee blocking all CSRF.
- **None:** permits cross-site scenarios if the browser allows; modern browsers typically require **Secure**.
- **Same-site differs from same-origin:** two origins that differ by scheme/host/port are not necessarily two different sites under browser rules.

Changing SameSite alone does not replace **CSRF protection** in applications using cookies for authentication. Do not set `SameSite=None` by default just because frontend and backend run on different ports; examine CORS, SameSite, domain/host, and real browser requirements first.

### 8.2. What do HttpOnly and Secure protect?

- **HttpOnly** restricts page JavaScript from directly reading the cookie value; it **does not** stop the browser from sending the cookie on requests and does not inherently stop XSS payloads from issuing requests on the user's behalf.
- **Secure** requires transmitting the cookie over a secure channel per browser rules; it **does not** encrypt session data stored on the server and does not enable HTTPS by itself.
- **HTTPS/TLS** protects data in transit over the network; you still need to control session IDs, timeouts, and cookie scope.
- **Path/Domain** helps limit where cookies are sent, but is **not** an authorization boundary; applications sharing a domain can affect cookies depending on scope.

In environments with TLS termination at a reverse proxy, configure the proxy and trusted forwarding properly so the application recognizes the original request as secure; or explicitly set the Secure attribute. Do not turn off Secure in production just as a workaround for unsent cookies without analyzing host/scheme/scope.

## 9. Proper logout: server invalidation differs from browser cookie deletion

Calling:

~~~java
HttpSession s = request.getSession(false);
if (s != null) {
    s.invalidate();
}
~~~

renders the **server-side session invalid**. This is the core security step: the old cookie can no longer link to the destroyed session. However, **invalidate() does not mean every client automatically deletes the cookie immediately**; the browser may retain the old `JSESSIONID` until it expires or the server sends an appropriate deletion directive.

To clear the cookie on the client side, the server emits **Set-Cookie with the same name/appropriate scope and Max-Age=0** (along with matching Path/Domain); prefer using the standard logout handler/cookie serializer of your security/session framework to avoid deleting the wrong scope.

Illustrative deletion header when the prior cookie used `Path=/`:

~~~http
Set-Cookie: JSESSIONID=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax
~~~

In production HTTPS, the cookie should carry `Secure` per configuration. When the prior cookie used a different Path or Domain, deleting with a mismatched scope can merely create another empty cookie without removing the old one.

A secure logout typically includes these steps:
1. Verify that this is a legitimate logout request and protect against CSRF under the cookie-based authentication model.
2. Invalidate the server-side session and `SecurityContext` via framework mechanisms.
3. Emit cookie deletion if needed; clean up other temporary data (remember-me, refresh tokens) according to policy.
4. Avoid accidentally recreating a session on the page/redirect rendered after logout.
5. Verify that subsequent requests with the old cookie cannot access authenticated resources.

In the Section 6 demo, the logout endpoint only performs the `invalidate` step to illustrate the difference between **a cookie still existing** and **a dead session**; it is not a complete production authentication logout.

## 10. Scaling pitfall: same cookie, different replicas

Suppose there are two instances:

~~~text
Browser
   | Cookie: JSESSIONID=abc
   v
Load Balancer
   |
   +--> Instance A: memory store has session abc
   |
   +--> Instance B: memory store does not have abc
~~~

If the session-creating request hits **A** but the next request goes to **B**, and both instances use **separate in-memory sessions**, B may treat the ID as invalid. The browser sent the cookie completely correctly; the issue lies in **where the server stores the session**.

Design options:

- **Sticky session / session affinity:** the load balancer prefers routing a client to the same instance. This can allow local sessions to work, but offers no guarantee when an instance dies or undergoes a rolling deploy, and makes load balancing harder.
- **Shared session store using Spring Session Redis/JDBC:** multiple replicas look up sessions by ID from a shared store. Requires designing TTL, serialization, availability, capacity, security, transactions, and data schema evolution.
- **Appropriate stateless authentication:** avoid relying on HttpSession if the business logic truly does not need server-side state; in exchange, you must address token revocation/expiry and its own threat model.

**Cookie name warning:** with **default Servlet sessions**, you commonly see `JSESSIONID`; with **Spring Session using DefaultCookieSerializer**, the default name is **SESSION**. Do not hardcode accepting only `JSESSIONID` across all Spring applications. When using Spring Session, check `CookieSerializer` configuration, **spring.session.timeout**, and related properties; once the session repository is replaced, storage lifecycle no longer depends solely on the container's memory store.

A syntactically valid cookie does not prove the session store is healthy. Losing Redis connectivity, failing to serialize an attribute, or mismatching cookie name/scope can all prevent requests from resuming state.

## 11. Common errors and how to diagnose them

| Symptom | Likely cause | How to verify |
| --- | --- | --- |
| Every GET to any page immediately gets JSESSIONID | A Filter, JSP, Security, or model/session logic called getSession(true) or equivalent | Trace when the session is created; audit Filters/Interceptors/Security |
| Every request gets a new session | Client does not send Cookie, wrong Path/Domain/Secure/SameSite, or cookies blocked | DevTools Network/Storage, curl -c/-b, inspect headers |
| Cookie is sent, yet session is lost | Idle timeout, invalidate, restart, different replica, or session store data loss | isRequestedSessionIdValid(), logs, store, LB routing |
| JSESSIONID still visible in browser after logout | Invalidated without clearing cookie, or cleared with wrong Path/Domain | Are old requests rejected? Check Set-Cookie Max-Age=0 |
| Cookie rejected by browser | Wrong Domain, SameSite=None missing Secure, invalid HTTPS/scope | Browser DevTools Issues/Network; response headers |
| Cookie has HttpOnly so document.cookie cannot see it | HttpOnly is working properly | Check DevTools cookie storage or request Cookie header |
| Cookie works in this tab, and another tab shares the state | Cookies are normally shared per profile and scope, not per tab | Open a separate profile/incognito window to test a fresh client |
| User loses login when load balancer switches Pods | Local in-memory sessions are not shared | Check sticky routing/session repository, rolling restarts |
| Session created after body has already flushed | Response committed before writing session cookie | Check where getSession() is called relative to response commit |
| Assumed Security STATELESS forbids any HttpSession | Controller directly calls getSession(true) or another library creates one | Separate Security policy from the Servlet API |
| CORS allows request, but browser does not send cookie | Missing credentials, cookie scope/SameSite, third-party cookie policy | Check fetch credentials, CORS origin/credentials, DevTools |
| Cookie is SESSION instead of JSESSIONID | Using Spring Session / custom CookieSerializer | Inspect dependencies and actual cookie name |

### 11.1. Debugging without leaking tokens

In DevTools:
1. Open **Network** and select the request that created the session.
2. Check response headers for **Set-Cookie**; note any browser reason for accepting/blocking the cookie.
3. Select the next request and check request headers for the corresponding **Cookie**.
4. Verify Path/Domain/Secure/SameSite/Expires against the actual URL.
5. On the server, log **whether a session exists**, `isNew()`, session creation events/counters, and the `valid` boolean—**never log the raw session ID**.

Do not put real `JSESSIONID` values into tickets, public screenshots, URL queries, shared stdout, or unsecured analytics tools. If you must correlate request logs, use an independent request correlation ID rather than the session cookie as a trace ID.

### 11.2. Using HttpSessionListener when lifecycle observation is needed

In a Servlet application, you can register **jakarta.servlet.http.HttpSessionListener** to receive **sessionCreated** and **sessionDestroyed** events at the container level. Example fragment (not a complete program):

~~~java
@WebListener
public class SessionLifecycleLogger implements HttpSessionListener {
    @Override
    public void sessionCreated(HttpSessionEvent event) {
        log.info("Session created");
    }

    @Override
    public void sessionDestroyed(HttpSessionEvent event) {
        log.info("Session destroyed");
    }
}
~~~

To run this fragment in Boot, you need Servlet annotation/interface imports, appropriate Servlet component discovery/registration (e.g., `@ServletComponentScan` or a `ServletListenerRegistrationBean`), and a logger. **Do not** print the raw session ID. Timeout-driven destruction may be processed asynchronously by container background sweeps; do not expect the event at the exact millisecond of expiration.

With distributed Spring Session, expired-session events and repository management differ from a local container; choose observation tools suited to the actual store.

## 12. Scenario exercises: predicting whether the server creates a cookie

**Exercise 1.** A client calls `GET /api/session/status` on the fresh demo app without sending a cookie. The method calls `getSession(false)`. Is a new session created?

**Answer:** Not by this method. `getSession(false)` returns `null`; the response needs no session `Set-Cookie`. In other applications, a Filter or Security might have created a session earlier.

**Exercise 2.** A client calls `POST /api/session/visit` once, receives `Set-Cookie`, and on the second request does not send `Cookie`. Is the counter 1 or 2?

**Answer:** Typically 1 on both requests if each creates a new session. The server has no way to link two requests to the same session without an ID or equivalent tracking mechanism.

**Exercise 3.** A client sends `Cookie: JSESSIONID=OLD`, but `OLD` has timed out. What does `getRequestedSessionId()` return, and what does `getSession(false)` return?

**Answer:** `getRequestedSessionId()` may return `OLD` (the client-presented ID); `isRequestedSessionIdValid()` is false; `getSession(false)` returns `null`. Calling `getSession(true)` may create a new session.

**Exercise 4.** After logging in, `JSESSIONID` changes while shopping cart data remains. Is this necessarily a bug?

**Answer:** No. The framework can rotate the ID to defend against session fixation while preserving session attributes under an appropriate strategy. Verify the configured authentication flow.

**Exercise 5.** The browser still has the `JSESSIONID` cookie after logout. Is the user necessarily still logged in?

**Answer:** No. Once the server has invalidated the session and auth state, the old cookie cannot restore the session. Even so, clear the client-side cookie with the proper scope and verify security on subsequent requests.

**Exercise 6.** There are 3 replicas storing sessions only in each replica's RAM. A client sends the right cookie, yet is occasionally treated as a guest. Why?

**Answer:** The request may land on a replica that does not hold the corresponding session. Managed session affinity or a shared session store (Spring Session) is needed if the system must preserve sessions across replicas/restarts.

**Exercise 7.** Using `SessionCreationPolicy.STATELESS`, yet a Controller calls `request.getSession(true)`. Why does `Set-Cookie` still appear?

**Answer:** `STATELESS` is a policy for Spring Security components; it does not lock down the Servlet API for application code. A Controller can still explicitly create an `HttpSession`; code/framework changes are needed to achieve end-to-end statelessness.

**Exercise 8.** The cookie has `Max-Age=24h`, and the session has an idle timeout of `15m`. The user returns after 2 hours and the browser still sends the cookie. Can the old session be resumed?

**Answer:** Normally no if the server session has already expired from inactivity, even though the client cookie remains. Cookie lifetime does not extend `HttpSession` lifetime.

**Exercise 9.** The server sends `Set-Cookie: JSESSIONID=...; Secure` over HTTPS, but the client makes the next call over plain HTTP. What can happen?

**Answer:** A `Secure` cookie is not sent over plain HTTP. The server may see no ID and create a new session if the handler calls `getSession(true)`. Use HTTPS consistently; do not weaken `Secure` to “fix” the issue.

## 13. Practical checklist for code review

- **Session purpose:** Use `HttpSession` only when server state across requests is genuinely needed; stateless APIs should not create sessions inadvertently.
- **Creation point:** Identify which line of code or middleware calls `getSession(true)`/`getSession()`; do not equate every HTTP request with a new session.
- **Non-creating reads:** For read-only/check endpoints, prefer `getSession(false)` and handle `null`.
- **Binding:** Inspect the initial response `Set-Cookie` and subsequent request `Cookie` headers, along with Domain/Path/Secure/SameSite rules.
- **Validity:** Check whether the presented ID is valid; cookie existence does not mean the server session exists.
- **Security:** Appropriate HTTPS, Secure, HttpOnly, SameSite, CSRF protection, and framework-managed session fixation protection.
- **Logout:** Invalidate on the server and clear the client cookie with the proper scope when needed; avoid accidental session creation after logout.
- **Timeout:** Distinguish server idle timeout from cookie Max-Age/Expires and browser session restore.
- **Scale:** With multiple replicas, determine whether the session store is local or shared; do not expect cookies to transport attributes by themselves.
- **Testing:** Use `curl -c/-b` or DevTools to observe headers and state; never log or display real IDs.
- **Framework version:** Distinguish Servlet `HttpSession`, Spring Session, and WebFlux `WebSession` before choosing properties or APIs.

## 14. Conclusion

**An HttpSession is created when the application/framework requests a new session**, typically via **request.getSession() / request.getSession(true)**; **request.getSession(false)** only reads an existing valid session without creating one. With cookie tracking, **Set-Cookie** transfers the ID from server to browser, and **Cookie** sends that ID on subsequent requests so the Servlet container can retrieve the server-side session.

A cookie is merely a **linking mechanism**: it does not inherently contain full state, cannot revive a timed-out session, does not guarantee the client is authenticated, and does not automatically share sessions across instances. To determine “has a session been created?”, observe **the session-creation API call, Set-Cookie/Cookie headers, and server session state** in order, rather than guessing from a lone `JSESSIONID`.

## Official references

- Jakarta Servlet 6.0 — HttpServletRequest: https://jakarta.ee/specifications/servlet/6.0/apidocs/jakarta.servlet/jakarta/servlet/http/HttpServletRequest.html
- Jakarta Servlet 6.0 — HttpSession: https://jakarta.ee/specifications/servlet/6.0/apidocs/jakarta.servlet/jakarta/servlet/http/HttpSession.html
- Spring Boot 3.3 — Common Application Properties (Servlet Session): https://docs.spring.io/spring-boot/3.3/appendix/application-properties/
- Spring Boot 3.3 — Servlet Web Applications / SameSite Cookies: https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html
- Spring Security — Authentication Persistence and Session Management: https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html
- Spring Session — CookieSerializer, default cookie name and shared-session settings: https://docs.spring.io/spring-session/reference/api.html
