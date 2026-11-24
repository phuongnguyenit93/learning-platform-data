# Configuring Session Timeout and Handling Expired Sessions in Spring Boot Web Runtime

Once a user has an **HttpSession**, the server must decide **how long the session remains valid without requests**, what happens when the browser keeps sending a cookie carrying an old session ID, and whether the application should return **HTTP 401, a login redirect, or another response**. Three concerns are frequently conflated: **server-side session timeout**, **browser-side cookie lifetime**, and **login lifetime under security policy**. Misconfiguration can force users to log in too often, cause APIs to return a login HTML page instead of 401 JSON, or leave old sessions usable longer than policy allows.

This lesson focuses on **Spring Boot 3.x, Java 17+, Spring MVC/Servlet, and HttpSession**. The examples use Spring Boot 3.3, embedded Tomcat, and demonstration endpoints. When a project uses **Spring Security** or **Spring Session Redis/JDBC**, there are additional mechanisms that must be understood separately. The demo simulates session state and is **not a production authentication system**.

## 1. Learning objectives

After this lesson, you should be able to:

1. Explain the relationship between **HttpSession**, **session ID**, the **JSESSIONID** cookie, last-accessed time, and **maxInactiveInterval**.
2. Configure inactivity duration via **server.servlet.session.timeout** and know when to adjust it with **HttpSession.setMaxInactiveInterval(...)**.
3. Distinguish **idle timeout**, **absolute timeout**, **cookie Max-Age/Expires**, logout/invalidate, and sessions invalidated by concurrent-login policies.
4. Handle requests when a session is missing/expired **without accidentally creating a new session**, especially when an API must return JSON + HTTP 401.
5. Design a sensible browser experience: preserving unsaved form data, notifying of expired sessions, redirecting to login, and handling 401 in JavaScript.
6. Understand the differences between container-local sessions, **Spring Security**, and distributed **Spring Session** over Redis/JDBC.
7. Verify behavior with **MockMvc** and real HTTP, and diagnose cookie, proxy, load balancer, restart, cleanup, and timeout failures.

Prerequisites: familiarity with Servlet request/response, HTTP status codes, cookies, Spring MVC controllers, and running Spring Boot applications with Maven/Gradle.

## 2. How are HttpSession and cookies actually related?

### 2.1. HttpSession is server-side state

**HttpSession** represents state tied to a client across multiple HTTP requests. A session has an **ID** and can hold attributes such as language, shopping cart, or state flags. With a default Servlet container, session data is usually managed in the server's runtime; storage format and survival across restarts depend on the container and configuration.

Simple flow:

~~~text
Browser                                      Spring Boot / Servlet container
   |                                                   |
   | POST /demo/session/start                          |
   |-------------------------------------------------->|
   |                              request.getSession(true)
   |                              create session S1 if absent
   |<--------------------------------------------------|
   | Set-Cookie: JSESSIONID=<id>; Path=/; HttpOnly     |
   |                                                   |
   | GET /demo/session/me                              |
   | Cookie: JSESSIONID=<id>                           |
   |-------------------------------------------------->|
   |                              look up session S1
   |                              check if idle timeout exceeded
   |<--------------------------------------------------|
   | 200 JSON if session and attributes remain valid   |
   |                                                   |
   | ... no requests touch the session past timeout ...|
   |                                                   |
   | GET /demo/session/me                              |
   | Cookie: JSESSIONID=<id> (cookie may still exist)  |
   |-------------------------------------------------->|
   |                              no valid session left
   |<--------------------------------------------------|
   | 401 JSON / or UI redirect per policy              |
~~~

A cookie normally carries a **session ID**, not the entire Java `HttpSession` object. Do not put passwords, sensitive access tokens, or all attributes into a cookie just because the browser must hold the session ID. HTTP requests use the cookie so the server can look up the session; cookie security, TLS, and session governance are shared responsibilities of the application, container, and Spring Security.

**JSESSIONID** is the common name when using a default Servlet container. If **Spring Session** is integrated, the cookie may be named **SESSION** under Spring Session's default configuration; the actual name is customizable. Do not write logic assuming a single hardcoded cookie name without checking the running stack's configuration.

### 2.2. Creating, looking up, and closing a session

| API / Property | Behavior | Key takeaway |
| --- | --- | --- |
| **request.getSession()** | Get the current session or create a new one if needed | Can mask expiration bugs because the API silently creates a new session. |
| **request.getSession(true)** | Same, explicitly stating creation is allowed | Use only when intentionally starting a session makes sense. |
| **request.getSession(false)** | Return valid session if present, otherwise **null** | Suitable for checking a session before using stateful resources. |
| **session.getAttribute("key")** | Read an attribute stored in the session | Null does not necessarily mean expired; the key may never have been set. |
| **session.setAttribute("key", value)** | Store data in the session | Does not replace durable persistence or database transactions. |
| **session.getMaxInactiveInterval()** | Maximum seconds of inactivity | 0 or negative in the Servlet API means no inactivity timeout; do not use for real auth sessions. |
| **session.setMaxInactiveInterval(seconds)** | Set idle timeout for a specific session | Enforce proper policy bounds; affects only that session, not the app-wide property. |
| **session.getLastAccessedTime()** | Start time of the most recent request associated with the session by the client | In milliseconds since epoch; not an absolute expiry time. |
| **session.invalidate()** | Explicitly invalidate the session | Used on logout/state revocation; prior references become invalid. |
| **request.isRequestedSessionIdValid()** | Check whether the client-supplied ID is still valid | Cannot distinguish the exact reason an ID is invalid (timeout vs. logout). |

**Critical warning:** When a request arrives with an old session cookie whose session has expired, **getSession(false)** returns `null`. If code calls **getSession()** before checking, the server may create a brand-new session, causing 401/redirect handling to behave unexpectedly.

### 2.3. Sessions typically use sliding idle timeout, not absolute timeout

**Idle timeout** is the maximum allowed gap between client accesses to the session. For example, configured to 30 minutes:

~~~text
10:00 - valid request arrives            -> last access at 10:00
10:25 - valid request arrives            -> last access slides to 10:25
10:50 - valid request arrives            -> last access slides to 10:50
11:20 - if no relevant request arrives   -> eligible to expire due to 30m idle
~~~

With regular requests, a session can stay alive far longer than 30 minutes from initial login. This is a **sliding idle timeout**, not “the user is logged in for at most 30 minutes from the start”. Heartbeats, AJAX polling, or auto-refresh requests can keep extending the last-accessed timestamp; WebSockets/push traffic and background jobs do not necessarily affect it the same way session-bound HTTP requests do.

**Absolute timeout** is a hard cutoff measured from creation/login—for instance, forcing re-authentication after 8 hours even if the user remains active. `HttpSession` idle timeout **does not provide this cutoff automatically**. If an absolute lifetime policy exists, you must store a timestamp and enforce the check at the security boundary, or use a mechanism supported by your framework/security platform. Do not merely raise or lower `server.servlet.session.timeout` and assume you have configured an absolute lifetime.

### 2.4. Expiration and cleanup do not always happen at the exact final second

Containers typically detect session expiration when a request accesses the session, or during a background session-sweeper task. Therefore, **when the resource is cleaned up** and **when an old request is rejected** may differ by a few seconds or by the sweep interval. Do not rely on a background task running at the exact second of expiration to commit critical business data.

A session with a 60-second timeout does not mean the browser receives a push notification at second 60. If the UI does not call the server, the browser continues showing the old page; when the user acts again, the new request reveals that the session is no longer valid.

## 3. Configuring session timeout in Spring Boot

### 3.1. Primary property: server.servlet.session.timeout

For **Spring Boot 3.3** on the Servlet stack, the property:

~~~yaml
server:
  servlet:
    session:
      timeout: 30m
~~~

sets the **inactivity** duration of `HttpSession`. **30m** is a common default in Spring Boot 3.3. You can specify units such as **s**, **m**, **h**, but note that a specific embedded Servlet container may **round or apply minute-level resolution**. With Tomcat, do not rely on a 2–3 second timeout for stable tests; use minute-scale timeouts for practical experiments.

Equivalent **application.properties**:

~~~properties
server.servlet.session.timeout=30m
~~~

Example **shorter testing configuration**:

~~~yaml
server:
  servlet:
    session:
      timeout: 1m
~~~

Do not use an overly short setting like 1 minute in production just because it makes demos easy to observe. Production duration must balance security requirements, data sensitivity, UX, internal compliance rules, and tab/browser/background request behavior.

**Key distinction:** This configures **Servlet HttpSession**. For WebFlux applications, the property for reactive sessions is **server.reactive.session.timeout**, not `server.servlet.session.timeout`. For distributed Spring Session, there is also **spring.session.timeout**, explained later.

### 3.2. Environment-specific configuration

You can use Spring profiles:

**src/main/resources/application.yml**

~~~yaml
spring:
  application:
    name: session-expiry-demo

server:
  port: 8080
  servlet:
    session:
      timeout: 30m
      cookie:
        http-only: true
        same-site: lax
~~~

**src/main/resources/application-local.yml**:

~~~yaml
server:
  servlet:
    session:
      timeout: 1m
~~~

Run with the `local` profile:

~~~bash
java -jar target/session-expiry-demo-0.0.1-SNAPSHOT.jar --spring.profiles.active=local
~~~

When the `local` profile is active, **timeout: 1m** overrides the **30m** value in the base configuration. Check overrides via environment variables, command-line args, or external config systems when running in containers. Do not infer the effective runtime configuration solely from reading a YAML file.

**Duration syntax:** Write explicit units such as **30m**, **1h** instead of bare numbers in training examples. Per Boot documentation, without a suffix many duration properties default to seconds, which is easily misread in code and still subject to container granularity.

### 3.3. Setting per-session timeout in Java

In some cases, an administrative session must expire faster than a regular user session. The Servlet API allows:

~~~java
HttpSession session = request.getSession(false);
if (session != null) {
    session.setMaxInactiveInterval(5 * 60); // 300 seconds
}
~~~

This is an **illustrative method snippet**, not a standalone runnable Java file. **setMaxInactiveInterval** takes an **`int` number of seconds**, not `java.time.Duration`. Place it in managed session handling after verifying permissions/context; never allow the client to supply an arbitrary timeout value to extend session lifetime. Setting intervals per request can make policies harder to audit, so prefer centralized configuration unless there is a clear requirement.

Per the Servlet API, **0 or negative values can prevent the session from timing out due to inactivity**. Never use this to “fix” user complaints about having to log back in: it keeps sessions alive indefinitely and increases the risk of session ID hijacking. Supporting “remember me” is a separate authentication problem with dedicated tokens/mechanisms, not disabling server session expiry.

## 4. Cookie Max-Age does not equal HttpSession timeout

### 4.1. Two counters stored in different places

- **server.servlet.session.timeout:** the server decides when `HttpSession` becomes invalid due to inactivity.
- **server.servlet.session.cookie.max-age:** the browser decides how long to keep the cookie if `Max-Age` is set. It does not directly set the **HttpSession** lifetime on the server.
- **Cookie HttpOnly:** browser JavaScript cannot read the cookie via `document.cookie`; it does not stop the cookie from being sent in HTTP requests.
- **Cookie Secure:** browser sends the cookie only over connections deemed secure, normally HTTPS.
- **Cookie SameSite:** restricts some situations in which cookies are sent on cross-site requests; does not replace CSRF protection or authentication.
- **Cookie Path/Domain:** limits the URL paths and hosts to which the browser sends the cookie; may differ when deployed under a context path/proxy.

Example cookie configuration:

~~~yaml
server:
  servlet:
    session:
      timeout: 20m
      cookie:
        http-only: true
        secure: true
        same-site: lax
        max-age: 2h
~~~

This is an **HTTPS deployment example**, not a config to copy into a plain HTTP localhost demo. Setting **Secure=true** while accessing over plain HTTP can prevent the browser from sending the cookie, making the endpoint look as if the session is constantly lost.

**The configuration above does not keep the server session alive for 2 hours.** The server can still expire the session after 20 minutes of inactivity, even while the browser keeps the cookie for 2 hours. When the old cookie is sent, the server finds no valid session; the application must handle that case.

Conversely, **a cookie Max-Age shorter than the idle timeout** can cause the browser to delete the ID while the server still holds the session until it expires. The server-side session temporarily becomes “orphaned”. Therefore, cookie and server session policies must be designed consistently rather than assuming they share one timer.

### 4.2. Session cookies without Max-Age

If a cookie has no `Max-Age`/`Expires`, the browser generally treats it as a **session cookie** tied to the browser session's lifecycle. However, some browsers restore tabs and session cookies upon reopening via session restore. Thus, **closing the browser cannot be treated as an absolute guarantee** of logout or server session deletion.

Conversely, the browser deleting a cookie does not immediately clean up the `HttpSession` object on the server. The server handles timeout/cleanup under its own policy; when explicit logout is required, **invalidate** the server session.

### 4.3. How cookies affect APIs

For browser clients using cookies, requests may need to respect credentials mode across origins, CORS, and SameSite. If a frontend on another domain calls `fetch` without sending credentials, the API sees **no session**, even if the server session is alive. That is a **cookie delivery** issue, not a timeout.

Avoid treating every HTTP 401 as “expired due to idle”: it can also happen because the user never logged in, the cookie wasn't sent, the session was revoked, security policy changed, or the session store was temporarily unreachable. UI messages should respect this uncertainty—for example, **“Session is no longer valid, please sign in again”**.

## 5. When a session expires, what should the server do?

### 5.1. Distinguishing the states

~~~text
Request arrives at an endpoint requiring a session
               |
               v
request.getSession(false)
       |                    |
       | session exists     | null
       v                    v
check business state        do not call getSession() to auto-create
/ permissions               |
       |                    v
       |                API -> 401 + JSON
       |                UI  -> 302/303 to appropriate login
       |
       +-- valid -> process request and return response
       |
       +-- missing attribute / policy invalid
                   -> 401/403 or redirect depending on cause
~~~

**Do not create a new session just to render an error.** A common mistake:

~~~java
HttpSession session = request.getSession();
if (session.getAttribute("USER") == null) {
    // Here the old session may have expired, yet getSession() just created a new session.
}
~~~

**The snippet above is an anti-pattern**, not a recommended approach. Replace it with **getSession(false)** when you only want to check an existing session. Moreover, in a real application with Spring Security, let the security filter chain handle authentication instead of manually checking a `USER` attribute in every endpoint.

### 5.2. APIs should return structured 401, not 200 HTML

For REST APIs using session authentication, when a request requires authentication but has no valid session/authentication, the response should typically be:

~~~http
HTTP/1.1 401 Unauthorized
Content-Type: application/json
Cache-Control: no-store

{"state":"missing_or_expired"}
~~~

**401 Unauthorized** indicates authentication is required. **403 Forbidden** is typically for an authenticated user lacking permission to perform the action. **200 OK + login page** is the wrong response for a JSON API: the frontend may try to parse HTML as JSON and surface an unclear error.

There is no standard HTTP status **440** in the IANA HTTP status registry to represent timeout; some platforms use 440 by proprietary convention, but public APIs should prefer 401 or an agreed error contract. If using **RFC 9457 Problem Details**, you can return `application/problem+json` with status 401, an appropriate `title`, and `type`. Do not include session IDs or tokens in error responses.

### 5.3. UI/browser flows can redirect to login

A server-rendered MVC application can handle a page navigation request with a redirect:

~~~java
@GetMapping("/account")
public String account(HttpServletRequest request, Model model) {
    HttpSession session = request.getSession(false);
    if (session == null || session.getAttribute("CURRENT_USER") == null) {
        return "redirect:/login?reason=session";
    }
    model.addAttribute("user", session.getAttribute("CURRENT_USER"));
    return "account";
}
~~~

This is an **illustrative snippet inside a @Controller** with separately configured view/login handling, **not a standalone Java file**. In a real authentication system, rely on Spring Security `Authentication` and entry points. When redirecting, verify context paths, relative URLs, and prevent open redirects from user parameters. Do not put sensitive info or user form data into query strings.

For SPA/JavaScript apps calling APIs, let the API return **401 JSON**, and have the frontend explicitly:

1. Clear the “logged-in” state on the UI side only, without assuming logout across all devices.
2. Preserve or restore unsaved draft data if policy permits; do not automatically replay a POST with side effects.
3. Display an invalid-session message and guide the user to sign in again.
4. After re-authentication, only retry safe requests or requests equipped with an idempotency key by design.

If using `fetch`, note that a 302 redirect from the server may be **followed automatically** by the browser to the login page; JavaScript then sees HTML instead of directly seeing 401. Separate page navigation flows from API flows right at the security configuration layer.

## 6. Runnable demo: timeout + 401 + invalidate without auto-creating a session

The following example demonstrates **HttpSession and idle timeout** without Spring Security. The **/demo/session/start** endpoint only sets a demo flag and **does not verify a password**; never turn a demo flag into a production login.

### 6.1. Create the project

Create a Java 17+ Spring Boot project via **https://start.spring.io** with Maven, Spring Boot **3.3.x**, group **com.example**, artifact **session-expiry-demo**, package **com.example.sessionexpiry**, dependencies:

- **Spring Web**
- **Spring Boot Starter Test**

Example file layout:

~~~text
session-expiry-demo/
  pom.xml
  mvnw
  mvnw.cmd
  src/main/java/com/example/sessionexpiry/
    SessionExpiryApplication.java
    DemoSessionController.java
  src/main/resources/
    application.yml
  src/test/java/com/example/sessionexpiry/
    DemoSessionControllerTest.java
~~~

Do not add Spring Security to this project if you want to run the simple demo as written, because security auto-configuration alters authentication/CSRF requirements and POST behavior. The Spring Security section (Section 8) covers the proper approach for real applications.

### 6.2. Minimal pom.xml, compiling with Java 17

~~~xml
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
    <artifactId>session-expiry-demo</artifactId>
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

Version **3.3.13** here is a pinned reference point for reading the syntax; in new projects, choose a version supported by your organization, apply security updates, and check the corresponding docs. Do not manually pin Spring Framework/Tomcat dependencies to versions different from Spring Boot's managed versions without a clear reason.

### 6.3. Main class

**src/main/java/com/example/sessionexpiry/SessionExpiryApplication.java**

~~~java
package com.example.sessionexpiry;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SessionExpiryApplication {
    public static void main(String[] args) {
        SpringApplication.run(SessionExpiryApplication.class, args);
    }
}
~~~

### 6.4. 1-minute demo configuration

**src/main/resources/application.yml**

~~~yaml
spring:
  application:
    name: session-expiry-demo

server:
  port: 8080
  servlet:
    session:
      timeout: 1m
      cookie:
        http-only: true
        same-site: lax
~~~

The `Secure` cookie flag is not enabled in this HTTP localhost demo because there is no HTTPS. In production, run HTTPS, consider **secure: true**, verify forwarded headers from a trusted reverse proxy, and configure cookie Path/Domain/SameSite appropriately. Never lower cookie protections in production just to make a demo work.

### 6.5. Demo controller: explicitly create, inspect, and invalidate sessions

**src/main/java/com/example/sessionexpiry/DemoSessionController.java**

~~~java
package com.example.sessionexpiry;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/demo/session")
public class DemoSessionController {
    private static final String DEMO_ACTIVE = "DEMO_ACTIVE";

    public record Message(String state) { }

    @PostMapping("/start")
    public ResponseEntity<Message> start(HttpServletRequest request) {
        // Only to illustrate HttpSession lifecycle, not user authentication.
        HttpSession session = request.getSession(true);
        session.setAttribute(DEMO_ACTIVE, Boolean.TRUE);

        return ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .body(new Message("started"));
    }

    @GetMapping("/me")
    public ResponseEntity<Message> me(HttpServletRequest request) {
        // Do not auto-create a new session just to check.
        HttpSession session = request.getSession(false);

        if (session == null
                || !Boolean.TRUE.equals(session.getAttribute(DEMO_ACTIVE))) {
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED)
                    .cacheControl(CacheControl.noStore())
                    .body(new Message("missing_or_expired"));
        }

        return ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .body(new Message("active"));
    }

    @PostMapping("/stop")
    public ResponseEntity<Void> stop(HttpServletRequest request) {
        HttpSession session = request.getSession(false);
        if (session != null) {
            session.invalidate();
        }

        return ResponseEntity.noContent()
                .cacheControl(CacheControl.noStore())
                .build();
    }
}
~~~

**What to verify in the code:**

- **start** calls `getSession(true)` because it is the only endpoint that intentionally opens the demo state.
- **me** calls **getSession(false)**, avoiding creating a new session when there is no valid ID.
- When the session is missing **or** `DEMO_ACTIVE` is missing, the API returns **401 JSON**. Both cases are combined into one state because neither proves “expired due to inactivity” by itself.
- **stop** only invalidates the session if present, and **does not** create a new session. A 204 result means no response body, so JSON must not be written to this response.
- **CacheControl.noStore()** instructs caches not to store session-related content; browser/proxy caches must not be used to decide whether a session is still valid.
- Do not include the session ID in JSON responses or public logs. The cookie ID is information that must be protected.
- Do not store passwords or secrets in session attributes; if sensitive data exists, minimize what is stored and apply real authentication/authorization mechanisms.

### 6.6. Run the demo and test the session with curl

Linux/macOS:

~~~bash
./mvnw spring-boot:run
~~~

Windows:

~~~text
mvnw.cmd spring-boot:run
~~~

Or package as an executable JAR:

~~~bash
./mvnw clean package
java -jar target/session-expiry-demo-0.0.1-SNAPSHOT.jar
~~~

Open a second terminal. **`-c`** writes cookies to a file, **`-b`** sends cookies back:

~~~bash
curl -i -c cookies.txt -b cookies.txt -X POST http://localhost:8080/demo/session/start
curl -i -b cookies.txt http://localhost:8080/demo/session/me
~~~

Expected response from the demo API:

~~~http
HTTP/1.1 200
Content-Type: application/json

{"state":"started"}
~~~

The **/me** request right after returns response body:

~~~json
{"state":"active"}
~~~

The **cookies.txt** file may contain the `JSESSIONID` cookie, so use it only for local testing and **do not commit to git or share it**. Actual headers such as charset, server name, `Cache-Control`, and `Set-Cookie`/`Path` may vary; the JSON body above is what the controller defines.

To observe real idle timeout:

1. Call **/demo/session/start** and save the cookie.
2. **Do not call /demo/session/me**, and make no session-related requests for longer than **1m** (allow extra margin because containers may round and run cleanup periodically).
3. After the inactivity period, run **curl -i -b cookies.txt http://localhost:8080/demo/session/me**.
4. Expect **HTTP 401** with body **{"state":"missing_or_expired"}**.

If you repeatedly call `/me` to “check if it has expired yet”, those very requests may refresh the session's last-accessed time and cause it to **never expire while you are checking**. When precise measurement is needed, use a non-polling client and inspect timestamps and session/container settings.

To test explicit invalidation:

~~~bash
curl -i -b cookies.txt -X POST http://localhost:8080/demo/session/stop
curl -i -b cookies.txt http://localhost:8080/demo/session/me
~~~

The response for **stop** is **204 No Content**; the next **me** request returns 401. The old cookie may still remain in the file/browser even after the server session is invalidated; deleting the cookie is a separate concern.

### 6.7. MockMvc test: ensuring no new session is created to handle errors

**src/test/java/com/example/sessionexpiry/DemoSessionControllerTest.java**

~~~java
package com.example.sessionexpiry;

import jakarta.servlet.http.HttpSession;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class DemoSessionControllerTest {
    @Autowired
    MockMvc mvc;

    @Test
    void missingSessionReturns401WithoutCreatingNewSession()
            throws Exception {
        MvcResult result = mvc.perform(get("/demo/session/me"))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.state")
                        .value("missing_or_expired"))
                .andReturn();

        assertNull(result.getRequest().getSession(false));
    }

    @Test
    void startUseAndStopSession() throws Exception {
        MvcResult started = mvc.perform(post("/demo/session/start"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.state").value("started"))
                .andReturn();

        HttpSession rawSession = started.getRequest().getSession(false);
        assertNotNull(rawSession);
        MockHttpSession session = (MockHttpSession) rawSession;

        mvc.perform(get("/demo/session/me").session(session))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.state").value("active"));

        mvc.perform(post("/demo/session/stop").session(session))
                .andExpect(status().isNoContent());

        mvc.perform(get("/demo/session/me"))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.state")
                        .value("missing_or_expired"));
    }
}
~~~

Run:

~~~bash
./mvnw test
~~~

The tests verify the **application contract**: no session created on read-only check, session created with attribute, returns 200, invalidates, and returns 401 when no session is present. **MockMvc does not prove a real server will idle-expire after exactly 60 seconds**, because it runs simulated Servlet requests and the test does not wait on a real clock. To verify container-level timeout, use HTTP integration tests or curl tests against the running server.

If you want to simulate inactivity in unit tests, do not use `Thread.sleep(60000)` as your primary test strategy; test isolated session policy logic with a fake **`Clock`**, while confirming container cleanup timing with targeted integration tests. Do not make tests depend on exact timing of background cleaners.

## 7. Handling expiration in the UI, APIs, and multi-tab scenarios

### 7.1. The browser may not know the session is gone until the next request

Sessions are server-side state. A form a user is filling out may sit idle for minutes; server expiration does not erase the text they are typing. When they click Submit, the API receives the old cookie and returns 401/redirect. Recommended UX:

- Clearly notify: “Session has expired, please sign in again”.
- Keep form data on the client **if it contains no sensitive data and policy allows**, without uploading it to an unauthenticated server.
- After login, restore navigation/data intentionally; avoid automatically resubmitting payment, order placement, or side-effecting POSTs.
- If the UI spans multiple tabs, handle consistency when one tab logs out or the session expires. Do not treat a `localStorage` flag as proof the server session is still active.
- Do not keep sessions alive via automatic background polling just to avoid logout. Heartbeats that extend sessions can violate inactivity security requirements.

### 7.2. Return 401 or redirect?

| Scenario | Typically appropriate behavior | Notes |
| --- | --- | --- |
| Fetch / XHR to a REST API requiring login | **401 JSON/Problem Details** | Frontend redirects or shows login according to its own logic. |
| Server-rendered MVC page navigation | **302/303 to login** | Only for valid navigation; do not put sensitive data in URLs. |
| Authenticated user lacking permission | **403** | Do not label every 403 as “session expired”. |
| Successful logout command | Invalidate, clear cookie per policy, redirect/204 | Do not merely clear UI state and leave the server session alive. |
| Session revoked by admin/policy | **401/redirect** depending on surface | Cause differs from idle timeout; a generic message can be shown. |
| Redis/session store error | Separate infrastructure errors from security errors | Do not assume backend connection loss is caused by user inactivity. |

**Important:** HTTP 401 does not always mean session timeout. Include correlation/request IDs in logs rather than logging session IDs, and monitor 401 counts, 403 counts, re-login rates, and session store errors. On the client side, avoid `/login → API → /login` redirect loops or infinite retries when the session is lost.

### 7.3. Distinguishing a newly expired session from a user who never logged in

If you only use **getSession(false)**, both cases can return `null`. **request.getRequestedSessionId()** and **request.isRequestedSessionIdValid()** can indicate that the client sent an ID that is invalid; they **do not tell you whether the cause** of invalidity was idle timeout, logout, server restart, a forged ID, or session registry revocation.

Therefore, a unified message is accurate: **"Session does not exist or is no longer valid"**. If the system requires the exact reason for auditing, record events at the infrastructure/session-store policy layer and avoid exposing details that could help an attacker infer session ID values.

### 7.4. Client-side timers are UX only, not authentication

A banner saying “2 minutes remaining in session” can be based on the idle timeout value or a server-returned timestamp. However, the client clock can drift, requests from another tab can extend the session, and the server can revoke the session at any time. **The server is always the authority on access control.** Never use a JavaScript timer to allow access to an API that requires 401 enforcement.

## 8. Spring Security: handling expired sessions at the right security layer

The `HttpSession` demo in Section 6 intentionally performs **no real authentication**. In applications with usernames/passwords, roles, CSRF, session fixation protection, or concurrent logins, **Spring Security** should manage identity and authorization. Never define production login by putting `Boolean.TRUE` into a session and trusting the client as authenticated.

### 8.1. Session timeout and Security are two different layers

**The Servlet container** controls `HttpSession` expiration due to inactivity. **Spring Security** uses authentication information from the security context, commonly stored across requests via the session in form-login flows. When the session expires, the old security context can no longer be restored from it; requests to protected resources require re-authentication.

**server.servlet.session.timeout** remains the underlying servlet session timeout. Spring Security has separate strategies for session fixation, invalid session IDs, invalid session URLs, concurrent session management, and logout. There is no single catch-all “spring.security.session.timeout” property equivalent to `server.servlet.session.timeout`.

### 8.2. invalidSessionUrl and InvalidSessionStrategy

Spring Security supports:

~~~java
http.sessionManagement(session ->
        session.invalidSessionUrl("/login?reason=session"));
~~~

This is a **configuration snippet inside an existing SecurityFilterChain**, not a standalone Java file. It can redirect when a request carries an **invalid session ID**. Some default stacks like form login have specific behaviors; test with your exact Spring Security version, filter chain, and entry point.

**Core caveat:** an invalid session ID does not prove timeout. When logout invalidates a session and the browser keeps sending the old cookie, the user may also be routed to the “session invalid” URL. Spring Security documentation warns about this false positive and recommends deleting the cookie on logout.

If API endpoints must return **401 JSON**, a redirect-style **invalidSessionUrl** may be unsuitable. Use an **InvalidSessionStrategy** or security entry point that handles **/api/** separately while HTML navigation goes to login. A conceptual illustration:

~~~text
If request matches /api/** and requires authentication, but session is invalid:
    HTTP 401 application/problem+json
If request is HTML navigation and session is invalid:
    controlled redirect to login
If request is /login or a static public resource:
    avoid redirect loops caused by stale cookies
~~~

Do not copy a blanket redirect lambda for the entire filter chain without testing the login page, static resources, APIs, and CSRF. API requests carrying **Authorization: Bearer ...** may use a different stateless mechanism; do not force them to follow browser-login session timeouts when the API does not actually rely on `HttpSession`.

### 8.3. maximumSessions expiredUrl is not the general idle timeout

Spring Security can limit concurrent sessions:

~~~java
http.sessionManagement(session -> session
        .maximumSessions(1)
        .expiredUrl("/login?reason=another-login"));
~~~

This too is an **illustrative snippet inside a SecurityFilterChain**. **expiredUrl** under **concurrent session control** applies to sessions marked expired because the maximum session count was exceeded (for example, logging in elsewhere). **Do not use expiredUrl to explain general idle timeouts.** Concurrent session control requires components such as **SessionRegistry** and usually **HttpSessionEventPublisher** to track session lifecycle, depending on Spring Security configuration.

Distinguish:

| Cause | Primary owner | Required behavior |
| --- | --- | --- |
| Inactivity exceeds maxInactiveInterval | Servlet container / Spring Session | Session is no longer valid; handle on next request. |
| User logout | Security/logout handler + session owner | Invalidate session, handle cookie, clear security context. |
| Second login exceeds maximumSessions | Spring Security concurrent session control | Old session is marked expired or new login is blocked per policy. |
| Cookie not sent due to SameSite/CORS | Browser/cookie policy | Server finds no session, though this is not a timeout. |
| Server restart with local-only sessions | Container/runtime | Old sessions may be lost; require re-login or shared session store. |
| JWT access token expired | Token validation | Not synonymous with HttpSession idle timeout. |

### 8.4. Logout, cookies, and session fixation protection

On logout, the server must revoke/invalidate the session under the actual authentication mechanism. Spring Security can be configured with:

~~~java
http.logout(logout -> logout
        .invalidateHttpSession(true)
        .deleteCookies("JSESSIONID"));
~~~

**Illustrative snippet, not a standalone application.** Cookie deletion may depend on cookie **Path/Domain** and container; test in a real browser. With Spring Session, the cookie name may be **SESSION** rather than `JSESSIONID`. Another option in supported HTTPS environments is **Clear-Site-Data** per policy, though do not wipe all site data indiscriminately.

Spring Security's **session fixation protection** usually rotates the session ID after successful authentication (such as `changeSessionId` on modern Servlets). This differs from idle timeout; its goal is preventing an attacker from forcing a victim to use a known session ID. Do not disable this protection just to keep a constant ID across login.

## 9. Spring Session: when sessions must survive across multiple instances

### 9.1. Limits of local HttpSession

In a **single-JVM** application, container-local sessions may suffice. However, when deploying multiple replicas:

~~~text
Browser -- Cookie ID --> Load Balancer
                               |
                               +--> Instance A: session S1
                               |
                               +--> Instance B: does not have S1
~~~

If the initial request hits A and the next hits B without a shared session store or appropriate sticky routing, B may return 401 even though the user was just active. If instance A restarts, local sessions may also be lost. Do not hastily increase timeouts to fix **not sharing a session store**.

### 9.2. Redis/JDBC with Spring Session

**Spring Session** can replace the default `HttpSession` implementation with a repository backed by Redis or JDBC. With Spring Boot and the corresponding starter, auto-configuration can provide **SessionRepositoryFilter** so Servlet requests see a session backed by the shared store.

Example with Redis in a Spring Boot application that has the `session-data-redis` dependency and valid Redis configuration:

~~~yaml
spring:
  session:
    timeout: 30m
    redis:
      namespace: myapp:sessions
~~~

In Spring Boot with Spring Session auto-configuration, **spring.session.timeout** sets the store's session timeout. If this property is not configured in a Servlet app, auto-configuration may fall back to **server.servlet.session.timeout**. When using **@EnableRedisHttpSession/@EnableJdbcHttpSession** for manual repository configuration, auto-configuration may back off; follow the properties of your explicit configuration rather than assuming every property applies.

**Do not add a Spring Session dependency to a demo and expect it to work immediately** without providing a Redis/JDBC store and proper configuration. Adding a store is an architectural change involving availability, serialization, scaling, connection security, and deployment.

### 9.3. TTL, cleanup, and expiration events

Redis has TTL/eviction mechanisms, while JDBC repositories usually need a cleanup job. **Session logic rejecting expired IDs** is the critical requirement, though background cleanup/deletion jobs do not necessarily run on the exact second. Spring Session also has repository-specific expiration events; do not build critical business workflows that depend solely on expiration callbacks.

Session attributes in a shared store must fit serialization mechanisms, data cost, and retention policies. Avoid storing large object graphs, credentials, open resources, or non-serializable objects. Do not use sessions as the primary database for carts/orders when that data requires transactions and high durability.

### 9.4. Notes when enabling HTTPS/proxies

When serving frontend/backend across different domains, verify the actual `Set-Cookie`: **Name, Domain, Path, HttpOnly, Secure, SameSite**. When HTTPS terminates at a reverse proxy, the application needs to know the real scheme if it determines secure-cookies/redirects dynamically, and can use an appropriate forward-header strategy with trusted infrastructure.

**CORS cannot fix a cookie with the wrong SameSite policy.** CORS only governs response readability and preflight; cookie delivery also depends on browser rules, credentials mode, third-party cookie restrictions, and `Secure`/`SameSite`. Do not disable CSRF protection just because APIs return 401 when sessions expire.

## 10. Absolute timeout, re-authentication, and risk-based idle timeout

### 10.1. When is idle timeout insufficient?

A financial administration system or sensitive document portal may require:

- **Idle timeout:** for example, 15 minutes with no valid activity.
- **Absolute lifetime:** for example, no more than 8 hours from authentication.
- **Re-authentication:** requiring password/MFA re-entry for sensitive operations.
- **Server-side revocation:** administrators can revoke a session even if it was just used.
- **Concurrent-session policy:** limiting the number of active devices/sessions.

The thresholds above are **examples only**, not mandatory standards for every organization. Do not use cookie `Max-Age` as a substitute for absolute lifetime; cookies can be deleted or retained longer, whereas access enforcement must happen server-side.

### 10.2. Implementing a hard cutoff

An architectural-level approach:

~~~text
After successful authentication:
    record server-generated authTime in the security principal/session record
On every request requiring authentication:
    if no session/security context -> 401 / login
    if now > authTime + absoluteLifetime:
        revoke or invalidate session
        require re-authentication
    if still valid:
        check roles/permissions and process request
~~~

**Do not store a client-sent timestamp as a trusted source.** Enforce the policy in a security filter/service invoked on every protected request, not just in one controller. Use an injectable/testable `Clock`, account for distributed/clock skew across instances, and avoid races between concurrent requests. If “remember me” exists, design a dedicated token with proper rotation/revocation instead of setting `maxInactiveInterval` to unlimited.

### 10.3. How should in-flight requests be handled?

Idle timeout is defined by the gap between client accesses; a long-running request already in progress may remain valid while being served, depending on the Servlet container and API. Do not assume the timer automatically aborts a long HTTP request at the exact second of expiration. For streaming/SSE/WebSockets, connection timeouts, access tokens, periodic re-authorization, and idle app logic must be designed separately.

If a long transaction exceeds the session policy, do not try to keep the session alive by sending fake requests. Use transaction/job management and idempotency so writes are neither duplicated nor lost if the user must log back in.

## 11. Session invalidation events and resource cleanup

### 11.1. Listeners are not instant timers

Servlet provides **HttpSessionListener** with callbacks on session creation/destruction; frameworks may use listeners for metrics or cleanup. However, when a session expires from idle timeout, the destruction callback runs as managed/cleaned up by the container and is **not guaranteed to fire at an exact moment visible to the frontend**.

If session-scoped resources need cleanup, design the data model and lifecycle appropriately. Do not store threads, sockets, transactions, or long-lived JDBC `Connection`s directly in a session hoping a listener will close them. If an event never arrives due to a crash/`SIGKILL`, resources will need recovery/cleanup through a durable mechanism.

### 11.2. Invalidate does not automatically delete every browser cookie

**session.invalidate()** invalidates the server session and triggers attribute-binding lifecycle callbacks, whereas the browser cookie is client-side state. If it needs to be removed, the server must emit an expired **Set-Cookie** with matching Path/Domain or use the framework's logout handler. A stale cookie can return with the same ID after logout, triggering **invalid session** detection rather than a true “timeout”.

Do not use a cookie-deletion response header as a replacement for server-side session invalidation. Perform both according to policy, especially when multiple tabs or cURL cookie files are involved.

### 11.3. Singleton @PreDestroy differs from session expiration

**@PreDestroy** on a singleton bean runs when the bean/container context is destroyed—typically application shutdown—not each time a user session expires. Do not use it to clean up a single user's session. Servlet listeners, Spring Session events, or dedicated business timeouts serve different roles and must also handle recovery when events do not fire.

## 12. Testing and observability in production

### 12.1. Minimum test suite

| Test case | What it must prove | Suitable tool |
| --- | --- | --- |
| Call protected API with no cookie | **401**, does not auto-create a session | MockMvc or HTTP integration. |
| Create session, call again immediately | API returns valid state | MockMvc + cookie jar / browser. |
| Stay silent longer than idle timeout | Old session is no longer accepted | Real HTTP against real container/session store. |
| Call API repeatedly before timeout | Extends if request touches session; no false timeout | Time-controlled HTTP integration. |
| Logout invalidate | Old cookie/ID cannot be reused | HTTP test, Security logout test. |
| Browser omits cookie due to SameSite/Secure | Server reports no session, even if store still holds it | Browser Network + server logs. |
| Multiple replicas/restart | Session survives or clears per store policy | Staging/load balancer test. |
| Session expired during side-effecting POST | No double write when user logs back in | Transaction/idempotency integration test. |
| UI redirect vs. API JSON | Does not return 200 HTML for JSON endpoints | Contract test + browser navigation test. |
| Spring Security concurrent maxSessions | Old session is revoked per policy | Security integration with two logins. |

**Do not rely solely on unit tests of getSession(false)** to claim Tomcat/Redis timeouts work properly. Those layers have different responsibilities.

### 12.2. Safe observability

Track metrics such as **HTTP 401 counts**, re-login counts, session creation/destruction, session store latency/errors, and 401 rates after deployment. Spring Boot Actuator/Micrometer can be used where instrumented. However, **never write raw JSESSIONID, SESSION cookies, bearer tokens, or passwords into logs**.

When tracing a request, use a **correlation ID** independent of credentials/session IDs. If security auditing genuinely requires correlating sessions, use an access-controlled audit system with anonymization and retention policies; never put session IDs into URLs or error messages.

### 12.3. Verifying effective runtime config

When timeout behavior does not match YAML:

1. Check active profiles, property precedence, environment variables, and startup arguments.
2. Confirm whether the app is **Servlet MVC** or **WebFlux**, and whether **Spring Session** is active.
3. If using Spring Session, check **spring.session.timeout**, manual repository configuration options, and store TTLs.
4. If using an external Servlet container/WAR, check whether context/container config overrides the timeout.
5. Check code for per-session **setMaxInactiveInterval** calls or interceptors touching state.
6. Check which heartbeat/AJAX requests are touching the session, not just user clicks.
7. Measure against the real instance/proxy/container, not just MockMvc.

## 13. Common errors and how to fix them

### 13.1. “Set timeout to 15 minutes, yet users never get logged out”

**Likely causes:** frontend polling, keep-alives hitting session-using endpoints, multiple tabs sending requests, or an overridden timeout. **Diagnosis:** inspect real HTTP requests and last-accessed behavior; search for `setMaxInactiveInterval` and runtime properties. **Solution:** separate health/stateless requests from sessions, remove unnecessary polling, and clarify idle vs. absolute lifetime. If policy requires a hard limit, enforce absolute expiry server-side.

### 13.2. “Got 401 only a few minutes after logging in”

**Causes:** cookie not sent (SameSite, Secure, Path, Domain, credentials), request routed to another replica with local sessions, server restart, session store disconnect, or misconfigured Spring Security redirect/login flow. **Diagnosis:** compare `Set-Cookie` and `Cookie` in the Network tab; verify instance, session store, and logs. Never blindly increase timeout when the real issue is cookie delivery.

### 13.3. “Session expired, yet the API returned the login HTML page”

**Causes:** form login/`invalidSessionUrl` redirecting globally for all requests, with browser `fetch` following the redirect automatically. **Solution:** protected APIs return 401 JSON or Problem Details; UI navigation redirects. Write tests asserting the Content-Type and status code of API endpoints.

### 13.4. “Why does logging out show ‘session expired’?”

**Causes:** the browser keeps sending the old session ID cookie after invalidation; `InvalidSessionStrategy` treats it as an invalid session. **Solution:** the logout handler clears the cookie with the exact name/Path/Domain, avoids redirect loops, and uses messaging that does not claim a specific cause when unknown.

### 13.5. “Expiring at exactly 60 seconds is flaky”

**Causes:** container rounds timeouts to minutes, background cleanup differs from request-time checks, or other requests touch the session. **Solution:** test with an adequate time margin, avoid ultra-short `Thread.sleep`, and do not test policy with microsecond assertions. If business rules require exact cutoffs, build explicit security/expiry checks.

### 13.6. “Cookie Max-Age is 2 hours, yet the session only works for 20 minutes”

**Causes:** the browser still holds the ID, but the server expired the session due to inactivity. **Solution:** understand the two TTLs; choose consistent cookie ages, return 401/redirect when the old session is gone, and never treat cookie presence as sufficient authorization.

### 13.7. “In a cluster, requests work intermittently”

**Causes:** local sessions are not shared across replicas and the load balancer routes requests to different instances. **Solution:** use a shared store like Spring Session Redis/JDBC or sticky sessions where appropriate, paired with a failover policy; test rolling restarts and store outages. Do not assume sticky routing fully replaces session durability.

### 13.8. “Spring Security expiredUrl doesn’t trigger on idle”

**Causes:** `expiredUrl` belongs to concurrent session control (`maximumSessions`), not the general handler for idle timeouts. **Solution:** configure handling for **invalid session IDs**, an authentication entry point, or app-level 401s on the filter chain. Distinguish a session kicked out by another login from one expired by inactivity.

### 13.9. “Cleared the cookie, yet the request still has a session?”

**Causes:** cookie deleted with wrong Path/Domain, browser has another cookie under a different name/namespace, Spring Session uses `SESSION` instead of `JSESSIONID`, or another authentication mechanism remains active. **Solution:** inspect all `Set-Cookie`/`Cookie` headers in the browser, check `SecurityContext` and shared stores, and log out from the proper owner.

### 13.10. “Session listener hasn’t run right after timeout”

**Causes:** background cleanup does not run at the exact second of expiration; Redis/JDBC have their own TTL/cleanup schedules and event semantics. **Solution:** never use listeners as the sole executor of critical business logic; enforce expiration inside authorization checks and design durable cleanup.

## 14. Pre-deployment checklist

- [ ] Identified whether the app uses **Servlet HttpSession**, WebFlux session, or stateless tokens.
- [ ] Selected **server.servlet.session.timeout** (or `spring.session.timeout` if using Spring Session) aligned with security and UX requirements.
- [ ] Clearly distinguished **idle timeout** from **absolute lifetime**, without assuming they are the same.
- [ ] Session-checking code uses **request.getSession(false)** where a new session must not be created.
- [ ] API requests with missing/expired sessions return **401 JSON**, not 200 HTML or out-of-contract redirects.
- [ ] UI navigation requests redirect/route to login properly without loops.
- [ ] Logout invalidates the server-side session and handles browser cookies with matching name/Path/Domain.
- [ ] Sensitive cookies use **HttpOnly, Secure, SameSite, Path/Domain** suited to HTTPS/proxy setup.
- [ ] **Cookie Max-Age** is not mistaken for server-side `HttpSession` data lifetime.
- [ ] CORS/credentials/third-party cookie restrictions verified if the frontend is on a different origin.
- [ ] Spring Security is used for real authentication, session fixation protection, and authorization.
- [ ] If using **maximumSessions**, `expiredUrl` is understood properly and concurrent-login policy is tested.
- [ ] If using Spring Session Redis/JDBC, verified store TTL, serialization, cleanup, and store-failure behavior.
- [ ] No credentials/secrets, open resources, or large object graphs stored in sessions.
- [ ] Tests cover **no cookie, active session, idle-expired, invalidate/logout, multi-tab, and multi-instance**.
- [ ] Session expiration events are not relied upon as the sole mechanism guaranteeing business commits.
- [ ] Logs and metrics do not expose session IDs or tokens.

## 15. Self-check questions

**1. Does `server.servlet.session.timeout=30m` mean the user is automatically logged out exactly 30 minutes after login?** No. It is an **inactivity timeout**; session-related requests can refresh the last-accessed timestamp.

**2. If the `JSESSIONID` cookie still exists after 2 hours, does that mean the `HttpSession` is still valid?** No. Cookie age and server session timeout are independent; a stale cookie can point to an expired session.

**3. Why is `getSession(false)` suitable for session-checking APIs?** Because it does not create a new session when no valid one is found; the application can return 401 properly.

**4. If a request carries an invalid session ID, can you tell for sure whether it timed out or was logged out?** No. There are multiple reasons a session ID can be invalid; the API should return an appropriate message/response without guessing the cause.

**5. Should Spring Security's `invalidSessionUrl` be used for JSON APIs?** It can be configured, but it typically redirects, easily breaking API contracts. APIs need an entry point/invalid-session strategy returning structured 401s.

**6. Does `maximumSessions` `expiredUrl` handle all idle timeouts automatically?** No. It serves concurrent session policy; idle timeouts and invalid sessions are separate flows.

**7. When is `spring.session.timeout` used?** When Spring Session auto-configuration manages the session repository. If unset in a Servlet app, configuration may fall back to `server.servlet.session.timeout`.

**8. Why doesn't a MockMvc test returning 401 prove a 1-minute idle timeout works?** MockMvc tests handler logic, not the full clock/cleanup behavior of a real container. HTTP integration tests or real server tests with waiting periods are required.

**9. If a dashboard auto-polls every 20 seconds, is a 15-minute idle timeout effective?** If those polling requests touch the session, they can keep extending it indefinitely. You must define what counts as meaningful user activity if policy mandates user-inactivity logout.

**10. Why doesn't session timeout replace policies protecting critical transactions?** Because session lifetime does not guarantee retries, idempotency, or commits. When a session is lost mid-transaction, the system still needs proper transactions and recovery mechanisms.

## 16. Official references

1. [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/): **server.servlet.session.timeout**, cookie flags, **spring.session.timeout**, reactive session.
2. [Jakarta Servlet — HttpSession API](https://jakarta.ee/specifications/servlet/6.0/apidocs/jakarta.servlet/jakarta/servlet/http/httpsession): **getSession**, **getLastAccessedTime**, **setMaxInactiveInterval**, **invalidate**, and lifecycle semantics.
3. [Spring Security — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html): **invalidSessionUrl**, **InvalidSessionStrategy**, session fixation, logout, concurrent session control.
4. [Spring Session — Spring Boot with Redis](https://docs.spring.io/spring-session/reference/guides/boot-redis.html): shared **HttpSession** and Redis-backed sessions.
5. [Spring Boot — Spring Session](https://docs.spring.io/spring-boot/reference/web/spring-session.html): auto-configuration and the **spring.session.timeout** / **server.servlet.session.timeout** relationship.
6. [MDN — Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Set-Cookie): Max-Age, Expires, HttpOnly, Secure, SameSite, and cookie scope.

**Summary:** **server.servlet.session.timeout** controls `HttpSession` inactivity duration, but **does not set an absolute lifetime and does not control cookie Max-Age**. When a session is no longer valid, the handling path must be clear: **APIs return structured 401, UIs redirect appropriately, and the server never auto-creates a new session to mask the error**. For real authentication applications, coordinate with Spring Security; for multiple instances, manage a shared session store via Spring Session and always verify against the deployed runtime.