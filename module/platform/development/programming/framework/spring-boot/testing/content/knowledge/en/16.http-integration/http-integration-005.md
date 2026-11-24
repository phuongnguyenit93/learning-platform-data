# Cookies, Sessions, Redirects, and Sequential Multi-Request Flows in Spring Boot HTTP Testing

## 1. Why is testing a single isolated request not enough?

An API can return the right HTTP 200 for a single request and still fail in a **stateful sequence of HTTP requests**. For example:

1. The client sends **POST /demo/login** with a username.
2. The server creates an **HttpSession**, attaches session data, and returns **Set-Cookie: JSESSIONID=...** along with **303 See Other** and **Location: /demo/profile**.
3. The client stores the cookie and sends **GET /demo/profile**. The server receives **Cookie: JSESSIONID=...**, looks up the existing session, and returns the corresponding data.
4. The client sends another GET: the `visits` counter in the **same session** increments from 1 to 2.
5. The client sends **POST /demo/logout**. The server invalidates the session.
6. Even if the client still holds the old cookie, it can no longer access session data: GET profile returns **401**.

A test that only calls `controller.login(...)` directly cannot prove **Set-Cookie**, **Cookie** on subsequent requests, **Location**, the HTTP client's **redirect** policy, or the servlet session lifecycle. A test using real HTTP on a random port with the **same cookie jar across multiple requests** can verify those exact boundaries.

**Lesson objectives:**

- Distinguish HTTP **cookies** (metadata sent back by the client), **server-side sessions** (state on the server), and **redirects** (3xx responses, `Location`).
- Use **@SpringBootTest(webEnvironment = RANDOM_PORT)**, **@LocalServerPort**, and Java 17 **HttpClient** to send multiple real HTTP requests.
- Configure a separate **CookieManager** per scenario; compare a client that stores cookies with one that does not.
- Explicitly test **303** when not auto-following, and **200** after the client follows POST → GET.
- Verify that sessions persist across requests, stay isolated between two clients, are not recognized without cookies, are invalidated on logout, and reject invalid input with 400.
- Avoid bugs caused by hidden redirect following, shared sessions across tests, cookie attributes, concurrency, expiration timing, or misunderstood transaction rollbacks.
- Understand the security limits of the example: this is a **session simulation**, not a production-grade authentication system.

**Practice environment:** Java 17, Spring Boot 3.3.5, Spring MVC/embedded Tomcat, JUnit Jupiter, Gradle. The code uses the **Jakarta Servlet API** of Spring Boot 3.x, not `javax.servlet` from Spring Boot 2.x.

## 2. Cookies, HttpSession, and redirects are not the same thing

| Concept | Where it lives / travels | Purpose | What must be verified |
|---|---|---|---|
| **Set-Cookie** | HTTP response header from server | Instructs client to store cookie | Did the server issue the right cookie name/value/attributes? |
| **Cookie** | HTTP request header from client | Sends back cookies matching domain/path/scheme | Does the next request carry the session ID? |
| **HttpSession** | State managed by servlet container or session repository | Associates requests with server-side data | Does the same cookie read the existing state properly? |
| **JSESSIONID** | Common servlet container session-tracking cookie name | Identifies the session, **not the entire session payload** | Did the client store and send back the cookie? |
| **303 See Other** | HTTP response status + Location | Directs client to another URI, normally with GET | Does the test inspect 303 or follow the redirect to 200? |
| **Location** | Header of redirect response | Specifies where to go next | Is the relative/absolute URI valid and safe? |
| **CookieManager** | State of Java 17 HTTP client | Persists cookies across requests per policy | Do tests avoid leaking cookies across scenarios? |
| **HttpClient.Redirect** | Java 17 client setting | Decides whether to follow redirects automatically | Do `NEVER` and `NORMAL` match expected statuses? |

**Crucial distinction:** `Set-Cookie` contains a **session identifier**, not the username or `visits` counter. On the server, `HttpSession` associates that ID with stored attributes. When a client sends the right cookie, the servlet container locates the session; if the ID is invalid, expired, or invalidated, the cookie no longer proves a live session exists.

**HTTP is stateless** per request; cookies + server-side sessions enable tracking across sequential requests. Cookies can also serve other purposes such as preferences, CSRF tokens, or tracking; not every cookie is `JSESSIONID`, and not every application uses `HttpSession`. Systems using Bearer tokens / stateless JWTs may have no servlet session at all.

### 2.1. Actual request and response flow

~~~text
Client: CookieManager initially empty
       |
       | POST /demo/login {"username":"Lan"}
       v
Embedded Tomcat -> Spring MVC Controller
       |           request.getSession(true)
       |           session["username"] = "Lan"
       |           session["visits"] = 0
       v
HTTP/1.1 303 See Other
Location: /demo/profile
Set-Cookie: JSESSIONID=<opaque-id>; Path=/; HttpOnly; ...
       |
       | Client stores JSESSIONID in cookie jar
       | Redirect.NEVER: receives 303, sends GET manually later
       | Redirect.NORMAL: client can follow automatically
       v
GET /demo/profile
Cookie: JSESSIONID=<opaque-id>
       |
       v
request.getSession(false) -> existing session
session["visits"] = 1
HTTP/1.1 200 OK
{"username":"Lan","visits":1}
       |
       | GET /demo/profile, same cookie
       v
HTTP/1.1 200 OK
{"username":"Lan","visits":2}
       |
       | POST /demo/logout, same cookie
       v
session.invalidate()
HTTP/1.1 204 No Content
       |
       | GET /demo/profile, old cookie might still exist
       v
HTTP/1.1 401 Unauthorized
~~~

The `Set-Cookie` line in the diagram is **illustrative**: session ID values are dynamic, and cookie attributes depend on the servlet container and Spring Boot configuration. Never hardcode a specific session identifier in expected outputs and never log sensitive cookies in CI.

## 3. Redirects: 301, 302, 303, 307, and 308 differ

| Status | Semantics | POST when client follows | Testing guidance |
|---|---|---|---|
| **301 Moved Permanently** | Resource moved permanently | Some clients may switch POST → GET | Test the next request's method per specific client |
| **302 Found** | Temporary redirect | Browser/client history allows switching POST → GET | Avoid relying on ambiguous behavior |
| **303 See Other** | View result at another URI | **GET** (or HEAD when appropriate), ideal for POST/Redirect/GET | Assert 303 + Location or assert final GET |
| **307 Temporary Redirect** | Temporary redirect, **preserves method/body** | Keeps POST | Use when the original request itself should be resent |
| **308 Permanent Redirect** | Permanent redirect, **preserves method/body** | Keeps POST | Watch out for long-term/client caching effects |

This lesson's example intentionally returns **303 See Other** after `POST /demo/login`. When the HTTP client follows it, it sends `GET /demo/profile`. This cleanly expresses the **POST/Redirect/GET** pattern and prevents browsers from resubmitting the POST when users refresh the target page.

**Java 17 HttpClient.Redirect:**
- **NEVER**: never follow redirects automatically; the returned response is **303** and you read `Location` yourself to decide the next request.
- **NORMAL**: follows valid redirects automatically, except **HTTPS → HTTP** downgrades; a POST receiving 303 switches to GET per HTTP semantics.
- **ALWAYS**: allows following even HTTPS → HTTP; do not enable recklessly as it risks connection security downgrades.

A newly built `HttpClient` with default settings **does not follow redirects automatically**. Other clients — such as browsers, `TestRestTemplate`, `RestTemplate` with various request factories, or RestAssured — can have different redirect behaviors. Therefore, **never assert only a final 200 and assume the server never returned 303**.

**`Location` can be a relative URI**, such as `/demo/profile`, or an absolute URI. When following manually:

~~~java
String location = response.headers()
        .firstValue("Location")
        .orElseThrow();

URI destination = response.uri().resolve(location);
~~~

`URI.resolve` produces an absolute URI based on the original request URI. In a real application, **never automatically follow redirects to arbitrary domains from untrusted input**; enforce host/scheme/allowlist checks to prevent open redirects or leaking cookies/credentials to untrusted destinations.

## 4. Why choose real HTTP integration tests instead of only MockMvc?

| Method | Real embedded server + socket? | Multi-request cookies/sessions? | Strengths |
|---|---|---|---|
| **Controller/service unit test** | No | Must be simulated manually | Pure Java logic |
| **MockMvc** with `MockHttpSession` | No | Can simulate sessions/cookies via request builders | Test MVC/filters at Servlet layer without opening a port |
| **@SpringBootTest + @AutoConfigureMockMvc** | Not for `mvc.perform` calls | Can use mock sessions | Full Spring context, mock servlet calls |
| **@SpringBootTest(RANDOM_PORT) + HttpClient** | **Yes** | **Yes, with `CookieManager` or `Cookie` header** | Cookie jar, HTTP redirects, real server/container boundary |
| **WebTestClient bindToApplicationContext** | Not necessarily | Has appropriate test mechanisms | Reactive/mock web testing |
| **Real HTTP client + Testcontainers/staging** | Yes | Yes, depending on test setup | Adds DB/proxy or production-like environment |

MockMvc is not low quality: it is very useful for many controller tests and can test sessions via **MockHttpSession**. However, when the goal is specifically **cookies, sessions, redirects, and sequential requests at the HTTP level**, you need at least one test with an HTTP client that manages cookies and redirects like a real client.

An HTTP integration test on localhost does not by itself prove SSL, reverse proxies, browser `SameSite` enforcement, or distributed session repositories. This is a test against embedded Tomcat inside the test JVM over loopback HTTP.

## 5. Runnable Spring Boot project: session demo app

We will build a learning-only API:

- **POST /demo/login** accepts JSON with a non-blank `username`, stores `username`/`visits` in `HttpSession`; returns **303** and **Location: /demo/profile**.
- **GET /demo/profile** reads the existing session. If no valid session exists → **401**. If present, increments `visits` from 0 to 1, then 2 on the next call, and returns JSON.
- **POST /demo/logout** invalidates the session if present and returns **204**; calling it again without a session still returns 204.
- `POST` login with blank `username` → **400**, without creating a usable session.

In a real system, login can never simply accept a username and treat it as authenticated! This is a **demo of the HTTP session lifecycle**, without authentication, authorization, CSRF, or passwords. When building production apps, use Spring Security and protect state-changing endpoints.

### 5.1. Project structure

~~~text
settings.gradle
build.gradle
src/main/java/demo/httpstate/HttpStateApplication.java
src/main/java/demo/httpstate/LoginRequest.java
src/main/java/demo/httpstate/ProfileResponse.java
src/main/java/demo/httpstate/SessionController.java
src/test/java/demo/httpstate/SessionHttpIntegrationTest.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'http-cookie-session-integration'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
~~~

**Explanation:**
- `spring-boot-starter-web` puts Spring MVC, Jackson, Jakarta Servlet API, and embedded Tomcat on the classpath in Spring Boot 3.3.
- `spring-boot-starter-test` brings JUnit Jupiter, Spring Test, Spring Boot Test, and assertions.
- `java.net.http.HttpClient` and `java.net.CookieManager` are already built into **JDK 17**, so Apache HttpClient is not needed just to store cookies here.
- There is no database, Redis, Spring Security, or external services, so test outcomes depend strictly on sessions + cookies/redirects. If security is added, expected responses must adjust for authentication/CSRF rules.
- `useJUnitPlatform()` is required for JUnit Jupiter tests.

### 5.2. Application

**src/main/java/demo/httpstate/HttpStateApplication.java**

~~~java
package demo.httpstate;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HttpStateApplication {

    public static void main(String[] args) {
        SpringApplication.run(HttpStateApplication.class, args);
    }
}
~~~

**src/main/java/demo/httpstate/LoginRequest.java**

~~~java
package demo.httpstate;

public record LoginRequest(String username) {
}
~~~

**src/main/java/demo/httpstate/ProfileResponse.java**

~~~java
package demo.httpstate;

public record ProfileResponse(String username, int visits) {
}
~~~

Java 17 supports records. Jackson in Spring Boot 3.3 serializes/deserializes simple record DTOs to/from JSON. Keep each public type in its own matching file.

### 5.3. Controller that creates, reuses, and invalidates HttpSession

**src/main/java/demo/httpstate/SessionController.java**

~~~java
package demo.httpstate;

import java.net.URI;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/demo")
public class SessionController {

    private static final String USERNAME = "username";
    private static final String VISITS = "visits";

    @PostMapping("/login")
    public ResponseEntity<Void> login(
            @RequestBody LoginRequest body,
            HttpServletRequest request) {

        if (body.username() == null
                || body.username().isBlank()) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "username must not be blank");
        }

        HttpSession session = request.getSession(true);
        session.setAttribute(USERNAME, body.username());
        session.setAttribute(VISITS, 0);

        return ResponseEntity.status(HttpStatus.SEE_OTHER)
                .location(URI.create("/demo/profile"))
                .build();
    }

    @GetMapping("/profile")
    public ResponseEntity<ProfileResponse> profile(
            HttpServletRequest request) {

        // false: do not auto-create a session just to read profile.
        HttpSession session = request.getSession(false);

        if (session == null) {
            return ResponseEntity.status(
                    HttpStatus.UNAUTHORIZED).build();
        }

        Object value = session.getAttribute(USERNAME);

        if (!(value instanceof String username)) {
            return ResponseEntity.status(
                    HttpStatus.UNAUTHORIZED).build();
        }

        Integer oldVisits =
                (Integer) session.getAttribute(VISITS);
        int nextVisits = (oldVisits == null ? 0 : oldVisits) + 1;
        session.setAttribute(VISITS, nextVisits);

        return ResponseEntity.ok(
                new ProfileResponse(username, nextVisits));
    }

    @PostMapping("/logout")
    public ResponseEntity<Void> logout(
            HttpServletRequest request) {

        HttpSession session = request.getSession(false);
        if (session != null) {
            session.invalidate();
        }

        return ResponseEntity.noContent().build();
    }
}
~~~

**Points to analyze from the source:**

1. **`getSession(true)`** in login gets an existing session or creates one if absent. For simplicity, the demo writes `username`/`visits`; production must prevent session fixation via Spring Security instead of blindly trusting a username as authenticated.
2. Session attributes live **on the server side**; the client never receives `username`/`visits` inside the cookie. With default embedded Tomcat, the session-tracking cookie is normally named **`JSESSIONID`**.
3. **`ResponseEntity.status(HttpStatus.SEE_OTHER)`** sets HTTP **303**, while **`location(...)`** sets `Location` to `/demo/profile`. These two must be asserted together.
4. `GET /profile` uses **`getSession(false)`**: if the request lacks a valid session, the controller does not allocate a new session just for reading and returns **401**.
5. The `visits` counter starts at 0; the first successful GET yields 1, the second yields 2. This is a **read-modify-write** on an `HttpSession` attribute and is **not safe for concurrent requests sharing the same session** without synchronization. All stateful tests in this lesson run **sequentially**; see the concurrency section.
6. **`invalidate()`** invalidates the session on the server. The client **may still hold the old cookie**; the cookie cannot resurrect an invalidated session.
7. `POST /logout` returns **204 No Content** even when no session exists. This makes logout effectively idempotent in outcome, though POST is not an idempotent HTTP method by general definition; idempotent behavior here is defined by the API.
8. The app has no real login security. Deploying this source onto the Internet would allow anyone to claim any username. Never use it as an authentication implementation.

**Why not put `@SessionAttributes` here?** Spring MVC's `@SessionAttributes` stores selected model attributes in session for controller workflows; it is **not identical to the `HttpSession` API** and is unnecessary when accessing the session directly. This exercise focuses on the cookie/servlet-session HTTP boundary, so it uses `HttpServletRequest.getSession`.

## 6. Integration test: Java 17 HttpClient and CookieManager

**Test strategy:**
- Each `@Test` method creates its **own `CookieManager` and `HttpClient`**. Never call `CookieHandler.setDefault(...)`, because that mutates JVM-global state.
- The client's cookie jar uses **`CookiePolicy.ACCEPT_ALL`** for this **loopback-only integration fixture**. This is not a recommendation to accept cookies from all origins in production; real clients need proper origin policies.
- Use **`HttpClient.Redirect.NEVER`** to observe HTTP 303 and `Location` directly.
- Use **`HttpClient.Redirect.NORMAL`** in another test to verify the client automatically follows 303 from POST to GET.
- Always build URIs from **`@LocalServerPort`**. The OS picks the port; never hardcode 8080.
- Every request has a timeout, and tests send synchronously so each request runs only after the prior response returns.

**src/test/java/demo/httpstate/SessionHttpIntegrationTest.java**

~~~java
package demo.httpstate;

import java.net.CookieManager;
import java.net.CookiePolicy;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class SessionHttpIntegrationTest {

    @LocalServerPort
    int port;

    @Autowired
    ObjectMapper mapper;

    private URI uri(String path) {
        return URI.create("http://127.0.0.1:" + port + path);
    }

    private static BrowserState browser(
            HttpClient.Redirect redirectPolicy) {

        CookieManager jar =
                new CookieManager(null, CookiePolicy.ACCEPT_ALL);

        HttpClient client = HttpClient.newBuilder()
                .cookieHandler(jar)
                .followRedirects(redirectPolicy)
                .connectTimeout(Duration.ofSeconds(5))
                .build();

        return new BrowserState(client, jar);
    }

    private record BrowserState(
            HttpClient http, CookieManager jar) {
    }

    private HttpRequest loginRequest(String username)
            throws Exception {

        String json = mapper.writeValueAsString(
                new LoginRequest(username));

        return HttpRequest.newBuilder(uri("/demo/login"))
                .timeout(Duration.ofSeconds(10))
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(json))
                .build();
    }

    private HttpRequest getRequest(String path) {
        return HttpRequest.newBuilder(uri(path))
                .timeout(Duration.ofSeconds(10))
                .GET()
                .build();
    }

    private HttpRequest logoutRequest() {
        return HttpRequest.newBuilder(uri("/demo/logout"))
                .timeout(Duration.ofSeconds(10))
                .POST(HttpRequest.BodyPublishers.noBody())
                .build();
    }

    private static HttpResponse<String> send(
            HttpClient client, HttpRequest request)
            throws Exception {

        return client.send(
                request, HttpResponse.BodyHandlers.ofString());
    }

    private ProfileResponse profileBody(HttpResponse<String> response)
            throws Exception {

        return mapper.readValue(response.body(), ProfileResponse.class);
    }

    @Test
    void loginReturns303LocationAndSessionCookie() throws Exception {
        BrowserState browser = browser(HttpClient.Redirect.NEVER);

        HttpResponse<String> response = send(
                browser.http(), loginRequest("Lan"));

        assertEquals(303, response.statusCode());
        assertEquals(
                "/demo/profile",
                response.headers()
                        .firstValue("Location").orElseThrow());

        assertTrue(response.headers()
                .allValues("Set-Cookie").stream()
                .anyMatch(value -> value.startsWith("JSESSIONID=")));

        assertTrue(browser.jar().getCookieStore().getCookies()
                .stream()
                .anyMatch(cookie ->
                        cookie.getName().equals("JSESSIONID")));
    }

    @Test
    void manualRedirectUsesStoredCookie() throws Exception {
        BrowserState browser = browser(HttpClient.Redirect.NEVER);

        HttpResponse<String> first = send(
                browser.http(), loginRequest("Linh"));

        assertEquals(303, first.statusCode());

        URI destination = first.uri().resolve(
                first.headers().firstValue("Location").orElseThrow());

        assertEquals("127.0.0.1", destination.getHost());
        assertEquals(port, destination.getPort());
        assertEquals("/demo/profile", destination.getPath());

        HttpRequest follow = HttpRequest.newBuilder(destination)
                .timeout(Duration.ofSeconds(10))
                .GET()
                .build();

        HttpResponse<String> profile = send(browser.http(), follow);

        assertEquals(200, profile.statusCode());
        assertEquals(
                new ProfileResponse("Linh", 1), profileBody(profile));
    }

    @Test
    void repeatedRequestsKeepOneSessionAndAdvanceState()
            throws Exception {

        BrowserState browser = browser(HttpClient.Redirect.NEVER);

        assertEquals(303, send(
                browser.http(), loginRequest("Mai")).statusCode());

        HttpResponse<String> first = send(
                browser.http(), getRequest("/demo/profile"));
        HttpResponse<String> second = send(
                browser.http(), getRequest("/demo/profile"));

        assertEquals(200, first.statusCode());
        assertEquals(200, second.statusCode());
        assertEquals(
                new ProfileResponse("Mai", 1), profileBody(first));
        assertEquals(
                new ProfileResponse("Mai", 2), profileBody(second));
    }

    @Test
    void withoutCookieHandlerSessionCannotBeReused()
            throws Exception {

        HttpClient noJar = HttpClient.newBuilder()
                .followRedirects(HttpClient.Redirect.NEVER)
                .connectTimeout(Duration.ofSeconds(5))
                .build();

        assertEquals(303, send(
                noJar, loginRequest("An")).statusCode());

        HttpResponse<String> profile = send(
                noJar, getRequest("/demo/profile"));

        assertEquals(401, profile.statusCode());
    }

    @Test
    void separateCookieJarsHaveSeparateSessions()
            throws Exception {

        BrowserState alice = browser(HttpClient.Redirect.NEVER);
        BrowserState bob = browser(HttpClient.Redirect.NEVER);

        assertEquals(303, send(
                alice.http(), loginRequest("Alice")).statusCode());
        assertEquals(303, send(
                bob.http(), loginRequest("Bob")).statusCode());

        HttpResponse<String> aliceProfile = send(
                alice.http(), getRequest("/demo/profile"));
        HttpResponse<String> bobProfile = send(
                bob.http(), getRequest("/demo/profile"));

        assertEquals(
                new ProfileResponse("Alice", 1),
                profileBody(aliceProfile));
        assertEquals(
                new ProfileResponse("Bob", 1),
                profileBody(bobProfile));
    }

    @Test
    void automatic303RedirectChangesPostIntoGet()
            throws Exception {

        BrowserState browser = browser(HttpClient.Redirect.NORMAL);

        HttpResponse<String> finalResponse = send(
                browser.http(), loginRequest("Vy"));

        // HttpClient follows 303 -> GET /demo/profile with cookie.
        assertEquals(200, finalResponse.statusCode());
        assertEquals(
                "/demo/profile", finalResponse.uri().getPath());
        assertEquals(
                new ProfileResponse("Vy", 1),
                profileBody(finalResponse));

        HttpResponse<String> next = send(
                browser.http(), getRequest("/demo/profile"));

        assertEquals(
                new ProfileResponse("Vy", 2), profileBody(next));
    }

    @Test
    void followingRedirectWithoutCookiesEndsAt401()
            throws Exception {

        HttpClient noJar = HttpClient.newBuilder()
                .followRedirects(HttpClient.Redirect.NORMAL)
                .connectTimeout(Duration.ofSeconds(5))
                .build();

        HttpResponse<String> response = send(
                noJar, loginRequest("Minh"));

        // Follows Location without sending JSESSIONID to the next GET.
        assertEquals(401, response.statusCode());
        assertEquals("/demo/profile", response.uri().getPath());
    }

    @Test
    void logoutInvalidatesSessionOnServer()
            throws Exception {

        BrowserState browser = browser(HttpClient.Redirect.NEVER);

        send(browser.http(), loginRequest("Hà"));

        HttpResponse<String> beforeLogout = send(
                browser.http(), getRequest("/demo/profile"));

        assertEquals(200, beforeLogout.statusCode());

        HttpResponse<String> logout = send(
                browser.http(), logoutRequest());

        assertEquals(204, logout.statusCode());

        HttpResponse<String> afterLogout = send(
                browser.http(), getRequest("/demo/profile"));

        assertEquals(401, afterLogout.statusCode());
    }

    @Test
    void blankLoginIsRejectedAndCannotOpenProfile()
            throws Exception {

        BrowserState browser = browser(HttpClient.Redirect.NEVER);

        HttpResponse<String> rejected = send(
                browser.http(), loginRequest("  "));

        assertEquals(400, rejected.statusCode());

        HttpResponse<String> profile = send(
                browser.http(), getRequest("/demo/profile"));

        assertEquals(401, profile.statusCode());
    }
}
~~~

**Total of 9 `@Test` methods**, with no `@TestMethodOrder` or `@TestInstance(PER_CLASS)`. Each method is designed to be **independent** of the others because it creates its own HTTP client and cookie jar. JUnit Jupiter execution order does not need to be fixed.

### 6.1. Detailed explanation of each test

**Test 1 — `loginReturns303LocationAndSessionCookie`**

The test sets **`Redirect.NEVER`** to observe the server returning status 303. It then checks the exact `Location` and that the response includes a `Set-Cookie` starting with `JSESSIONID=`. It also verifies `CookieManager` stored the cookie in its store. Never assert a specific session ID value — that is dynamic data generated differently every time and should not be exposed in logs. Do not assert the entire `Set-Cookie` string because Tomcat may append `Path`/`HttpOnly`/`SameSite` attributes differently depending on config.

**Test 2 — `manualRedirectUsesStoredCookie`**

Without auto-following, a POST request stops at 303. The test reads **`Location`** and uses `URI.resolve` to build the next URI. Crucially, it **reuses `browser.http()`**: the shared cookie jar ensures `GET /demo/profile` sends `JSESSIONID`. The server returns `ProfileResponse("Linh", 1)`. The test also verifies the redirect does not jump to a different host within the fixture.

**Test 3 — `repeatedRequestsKeepOneSessionAndAdvanceState`**

The same HTTP client performs POST login and two consecutive GET profile requests. Expected `visits` are **1 and 2**; `username` stays `"Mai"`. If each request created a separate `HttpClient` without a shared cookie jar, or if the server failed to keep session state, this test fails. This directly proves **sequential multi-request state**.

**Test 4 — `withoutCookieHandlerSessionCannotBeReused`**

A JDK `HttpClient` without a `CookieManager` will not retain cookies automatically in this example. POST login still succeeds and returns 303, but the subsequent GET **does not send `JSESSIONID`** and receives 401. The difference is not in controller logic — it is in HTTP client state.

**Test 5 — `separateCookieJarsHaveSeparateSessions`**

Two simulated browsers with separate `CookieManager` instances call the same embedded server. Alice sees Alice's session, Bob sees Bob's session. The test uses **distinct usernames** instead of asserting random session IDs; if a cookie jar were accidentally shared, the assertions would catch it.

**Test 6 — `automatic303RedirectChangesPostIntoGet`**

With **`Redirect.NORMAL`**, the HTTP client sees 303 after POST and automatically sends a GET to `Location`. Because it also has a `CookieManager`, the GET carries the session cookie; the final response is **200** and the final URI is `/demo/profile`. A subsequent GET returns `visits=2`, confirming the redirect already counted as the first profile visit.

**Test 7 — `followingRedirectWithoutCookiesEndsAt401`**

The client follows redirects yet stores no cookies. It reaches `/demo/profile`, but without a session ID the final response is **401**. This test separates two independent axes: **following redirects ≠ preserving sessions**. Enabling `followRedirects` alone is not enough for cookie-based workflows.

**Test 8 — `logoutInvalidatesSessionOnServer`**

The client may still keep `JSESSIONID` in its cookie store after logout; session invalidation is performed by the **server**. GET after logout returns 401. The test does not depend on whether the server emits an additional `Set-Cookie` to delete the cookie; it verifies the most important effect: **the old session no longer grants access**.

**Test 9 — `blankLoginIsRejectedAndCannotOpenProfile`**

A blank username must be rejected with 400 and must not create a valid session. A subsequent GET profile returns 401. This is a multi-request negative test proving a failed request does not accidentally establish authenticated state in the demo.

**About 401 in this lesson:** It is returned by the controller for a missing session per the illustrative contract. In production, 401/403 must be governed by a real security policy, typically Spring Security; never treat the mere presence of a `username` string in session as a secure authentication condition.

## 7. Running the example and checking results

In a project with a Gradle Wrapper:

~~~bash
./gradlew test
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

When creating the project from the files in this lesson **without wrapper scripts/JAR**, generate them with a compatible installed Gradle or run **`gradle test`**. The `build.gradle`/`settings.gradle` files alone do not create `./gradlew`.

The source in Sections 5 and 6 contains **9 JUnit Jupiter `@Test` methods**, all inside **`SessionHttpIntegrationTest`**. With the stated versions/dependencies and default server configuration, all are designed to PASS. This is the **expected outcome of the sample source**, not a claim that the tests have already been run in the reader's environment. The actual report is usually at:

~~~text
build/reports/tests/test/index.html
~~~

Run just this class when debugging:

~~~bash
./gradlew test --tests demo.httpstate.SessionHttpIntegrationTest
~~~

**Deterministic outcomes:**

| Test/scenario | Expected response | Key state |
|---|---|---|
| Login `Redirect.NEVER` | **303** + Location + Set-Cookie | Client stores `JSESSIONID` |
| Manual follow of `Location` | **200**, username=Linh, visits=1 | Same cookie jar |
| POST login + two GETs | **303 → 200 → 200** | visits=1 then 2 |
| Client without cookie handler | **303 → 401** | Cookie not sent back |
| Two separate cookie jars | Two **200** responses | Alice/Bob do not cross over |
| `Redirect.NORMAL` with `CookieManager` | Final **200** after 303 | Auto-followed GET, visits=1 |
| `Redirect.NORMAL` without cookie jar | Final **401** after 303 | Redirected but no session |
| Login, profile, logout, profile | **303 → 200 → 204 → 401** | Server session invalidated |
| Blank login, GET profile | **400 → 401** | No usable session created |

**Do not expect a fixed `JSESSIONID` value or a fixed port number.** The random port from `@LocalServerPort` and the container-generated session identifier change across runs. Proper tests verify the **relationships between requests**, not random runtime values.

## 8. Trying manually with curl to observe raw HTTP headers

The demo can also be run standalone via Gradle once the app is configured and builds cleanly:

~~~bash
./gradlew bootRun
~~~

When running the application normally, Spring Boot uses port **8080** if `server.port` is not changed. In **`@SpringBootTest(RANDOM_PORT)`** never assume 8080; the `curl` commands below are for **local `bootRun`** on 8080, not random-port tests.

On Bash/Linux/macOS, you can run:

~~~bash
# Login: -i shows status/headers, -c saves cookies from the response.
curl -i -c cookies.txt \
  -H 'Content-Type: application/json' \
  --data '{"username":"Lan"}' \
  http://127.0.0.1:8080/demo/login

# GET sends saved cookie: --cookie reads the jar.
curl -i --cookie cookies.txt \
  http://127.0.0.1:8080/demo/profile

# Repeat GET: visits increments in the same session.
curl -i --cookie cookies.txt \
  http://127.0.0.1:8080/demo/profile

# Logout: the old cookie may still sit on the client machine.
curl -i --cookie cookies.txt -X POST \
  http://127.0.0.1:8080/demo/logout

# After logout, the session is invalidated -> 401.
curl -i --cookie cookies.txt \
  http://127.0.0.1:8080/demo/profile
~~~

The `cookies.txt` file is purely an **experimental cookie jar** written by curl; never commit it to Git or push it into logs because it can contain session identifiers. Delete the file afterward. On Windows PowerShell, use **`curl.exe`** and adjust quoting for your shell, because the `curl` alias/command differs from Bash.

**To observe the redirect without following it:** omit `-L`; curl prints status 303 and `Location`. If you add `-L`, the client follows the redirect; make sure the cookie jar is attached so the follow-up request carries the session. Never conclude "the server returned 200 instead of 303" if you are reading the final response after a redirect chain.

## 9. CookieManager, CookieStore, and test isolation

### 9.1. Simply reusing the same HttpClient does not store cookies automatically

In Java 17 `HttpClient`, cookie handling is an **opt-in** setting via `builder.cookieHandler(...)`. Without configuring it, the client has no cookie jar for this example. To retain cookies:

~~~java
CookieManager jar = new CookieManager(
        null, CookiePolicy.ACCEPT_ALL);

HttpClient client = HttpClient.newBuilder()
        .cookieHandler(jar)
        .followRedirects(HttpClient.Redirect.NEVER)
        .build();
~~~

Passing `null` as the first argument creates the default in-memory `CookieStore`. **`ACCEPT_ALL` must only be used in controlled loopback tests**; production clients need cookie policies appropriate to origin/domain and security requirements. You can use **`CookiePolicy.ACCEPT_ORIGINAL_SERVER`** or a custom policy, verifying compatibility with the server's actual `Set-Cookie`.

**Do not call `CookieHandler.setDefault(jar)`** in each `@Test`: that is JVM-wide global state and can cause other tests to receive unexpected cookies, especially during parallel runs. Attaching `CookieManager` **per `HttpClient` instance** is much easier to control.

### 9.2. When does CookieManager automatically send a cookie?

`CookieStore` tracks cookies along with **Domain, Path, Secure, and Max-Age/Expires** attributes. When a client sends a new request, `CookieManager` selects cookies matching the target request. For example:
- A cookie with `Path=/demo` can be sent to `/demo/profile`, not necessarily to `/admin`.
- A cookie marked `Secure` is normally only sent over HTTPS per user-agent rules.
- Expired cookies are not sent.
- Switching hostnames between **`127.0.0.1`** and **`localhost`** can alter domain/host matching even though both point to the same machine.
- The JDK cookie manager **is not a web browser**; do not use it as complete proof of browser `SameSite`/CSRF behavior.

Therefore, tests use the **same hostname** `127.0.0.1` and the port from `@LocalServerPort` across all requests. We do not manually construct a `Cookie` header; letting `CookieManager` handle it properly exercises client state behavior.

### 9.3. One jar per test, not just one per test instance

JUnit Jupiter normally creates a new test class instance per method, yet Spring TestContext can reuse the `ApplicationContext`/server. A **static `CookieManager`**, singleton client fixture, or global `CookieHandler` can still cause methods to share cookies unexpectedly.

This example creates a fresh `BrowserState` **inside each `@Test`**, keeping session retention scoped to that specific test flow. The server may still hold un-invalidated sessions until timeout, but other tests lack the session ID to reach them.

In larger systems, consider cleaning up server sessions/DB/caches or using ephemeral environments to prevent stale state accumulation. Never use a production account's cookie in tests.

## 10. Session lifecycle: creation, access, timeout, and invalidation

**`getSession(true)`**: returns the existing session if the request carries a valid session ID; otherwise creates a new session.

**`getSession(false)`**: returns only an existing session, **never creating a new one**. When the client has no cookie or an invalid old cookie, it normally returns `null`. This is the right choice for endpoints checking whether a session exists without allocating empty sessions.

**`invalidate()`**: invalidates the current session. The client's cookie may still exist, yet the server no longer holds the old state. If the server needs to actively instruct the client to delete the cookie (especially custom cookies), it can send an expired `Set-Cookie` with matching name/path/domain; do not assume `session.invalidate` automatically emits a deletion `Set-Cookie` in every servlet container.

**Timeout:** Sessions typically expire after an inactivity period; Spring Boot servlet configuration exposes **`server.servlet.session.timeout`**. Never use **`Thread.sleep(30 minutes)`** to test the default timeout. If you genuinely need to verify expiration, configure a short session timeout in an isolated test profile/context, verify within bounded time avoiding interference with other tests, or unit-test a dedicated expiry abstraction.

**Session ID rotation:** Under real authentication, Spring Security supports session fixation protection, including rotating the session ID per configuration. This demo **does not implement security login**, so it does not test session fixation policies. In real applications, verify that successful login never reuses an attacker-supplied session ID, and check post-logout policies.

**State can vanish on app restart:** Embedded Tomcat in-memory sessions do not survive restarts or carry over to another server instance. When distributed sessions are needed, look at Spring Session with Redis/JDBC and sticky-session/load-balancer policies. Having a cookie present does not guarantee the server-side session exists on every node.

## 11. Cookie security: HttpOnly, Secure, SameSite, Path, and Domain

**`Set-Cookie`** attributes govern how browsers handle cookies:

| Attribute | Effect | What to watch when testing |
|---|---|---|
| **HttpOnly** | Restricts JavaScript from reading the cookie | Does not replace XSS protection; browsers still send the cookie on matching requests |
| **Secure** | Restricts cookie to secure connections | In loopback HTTP tests, do not enable `Secure` and expect the JDK client to always send it like HTTPS |
| **SameSite=Strict/Lax/None** | Controls when browsers send cookies in cross-site contexts | Do not use plain `HttpClient` alone as proof of browser CSRF protection |
| **Path** | Limits request paths receiving the cookie | All demo endpoints share `/demo` |
| **Domain** | Limits/allows hostnames/subdomains | Do not mix `localhost` and `127.0.0.1` within the same scenario |
| **Max-Age / Expires** | Client-side cookie lifetime | Cookie expiration is distinct from server-side session timeout |
| **Name** | Cookie name, e.g., `JSESSIONID` | If customizing `server.servlet.session.cookie.name`, update assertions |

In Spring Boot 3.3, common properties include:

~~~properties
# Example for real HTTPS environments, DO NOT apply verbatim
# to loopback HTTP integration tests:
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.secure=true
server.servlet.session.cookie.same-site=lax
server.servlet.session.timeout=30m
~~~

**Why omit those properties from the runnable example?** The test uses **`http://127.0.0.1`** rather than HTTPS, and `Secure` cookies carry strict client/browser semantics. Forcing `Secure` in an HTTP loopback test can stop clients from sending the cookie and derail the test goal. In production, sensitive session cookies should be protected by HTTPS + appropriate `Secure`/`HttpOnly`/`SameSite` flags and CSRF defenses.

Note that **`SameSite=None`** normally requires **`Secure`** in modern browsers. Spring Boot cookie settings do not replace CSRF protection when an API relies on cookie-based authentication for state-changing operations.

### 11.1. Authentication and session demo are two separate things

Even though the endpoint is named `login`, this lesson's controller accepts an **arbitrary username** without checking passwords or tokens. It must never be treated as a production login mechanism. Real applications need:
- Authentication via Spring Security, storing auth state via a proper security session strategy or token design.
- Protection against **session fixation** when transitioning from anonymous → authenticated.
- CSRF protection for cookie-authenticated state-changing operations where the design requires it.
- Logout invalidating sessions/tokens per threat model, not just returning 204.
- Secure cookie attributes, HTTPS, and proper storage/expiration policies.
- Never exposing `JSESSIONID` in debug logs, query strings, or client-visible JSON.

This example only proves that **a cookie correlates multiple HTTP requests to one `HttpSession`**. Keeping goals distinct avoids turning a testing lesson into bad security advice.

## 12. Redirects and cookies are two independent testing axes

Consider four combinations:

| Client follows redirect? | Client stores cookie? | POST login then view result | Why |
|---|---|---|---|
| **No** | Yes | Receives **303**; manual follow-up GET gets **200** | Cookie jar keeps `JSESSIONID` |
| **No** | No | Receives **303**; manual follow-up GET gets **401** | No session ID |
| **Yes (NORMAL)** | Yes | HTTP client auto-follows, final **200** | 303 switches POST to GET, cookie sent |
| **Yes (NORMAL)** | No | HTTP client auto-follows, final **401** | Following URL does not mean keeping session |

This is why **a single final status assertion is not enough** to diagnose failures. If you expect a final 200 yet receive 401, the first question is not necessarily a broken controller; you may be following the redirect properly while **forgetting `CookieManager`**.

Conversely, if you expect 303 yet receive 200, check whether the client has auto-follow enabled or a test helper swapped out the HTTP request factory. To test a 3xx contract, **disable auto-follow** and assert `Location`/`Set-Cookie` directly.

When a redirect targets a different domain, cookies scoped to the old origin **must not be forwarded** to the new domain unless `Domain`/`Path`/`Secure` rules permit it. Never "fix a test" by blindly copying raw `Cookie` headers across origins: that can leak session IDs to third parties.

## 13. Session state under concurrency and context caching

In the demo, the session holds an `Integer visits` with:

~~~java
Integer visits = (Integer) session.getAttribute("visits");
int next = (visits == null ? 0 : visits) + 1;
session.setAttribute("visits", next);
~~~

This is a **non-atomic read-modify-write**. If two requests arrive **concurrently with the same `JSESSIONID`**, both can read `visits=1`, both write `2`, and lose an increment. The sample tests issue **sequential** requests because they test sequential session continuity, not concurrent increments.

If business logic requires exact counting under concurrency, consider:
- Using a state component with **atomic** increment operations suited to the session/storage scope.
- Using database transactions / optimistic locking or an atomic key-value store increment for distributed state.
- Avoiding storing mutable non-thread-safe objects in session.
- Writing dedicated concurrency tests rather than expecting `HttpSession` to serialize every request for the same session.

**Spring TestContext cache:** Test methods sharing the same `@SpringBootTest` config can reuse the embedded server and session manager. Therefore:
- Never share a static `CookieManager` across tests.
- Never rely on test order to reuse a session created by a previous test.
- Each test should create its own cookie jar/account/fixture, or clean state explicitly.
- **`@DirtiesContext`** can force a server restart, yet is not recommended for resetting cookie jars; manage state at the owner level.
- If sessions live in Redis/JDBC via Spring Session, a context restart **does not automatically wipe** external storage.

## 14. DB transactions when HTTP client and server run on two threads

The demo has no persistence, yet in real integration tests, login, checkout, cart, or session-backed orders may write to a database. When `@SpringBootTest` uses **`RANDOM_PORT`** or **`DEFINED_PORT`**, the HTTP client and server handle requests on different threads/transactions.

**Common trap:** `@Transactional` on a test method rolls back the **test-managed transaction** afterward; it **does not automatically roll back transactions committed by server-side requests**. Hence, an HTTP POST can leave rows in the DB and affect later tests.

How to handle it:
1. Use a dedicated test DB/schema/Redis namespace.
2. Use unique IDs for test data written on the server.
3. Clean up via repository/script/fixture in an appropriate transaction **after server requests complete**.
4. Use Testcontainers or ephemeral databases to reduce cross-run contamination.
5. Do not treat `@DirtiesContext` as a way to wipe DB/Redis; it only affects the `ApplicationContext` cache.
6. Across sequential requests, distinguish **state in `HttpSession`** from persisted state; logout does not necessarily erase carts/orders already saved to the DB.

**Separate concerns:** Session tests should prove the client sends `JSESSIONID` and the server preserves attributes; database transaction tests should prove persistence semantics. Do not mix both goals without cleanup, or failures become harder to pinpoint.

## 15. Common failures and how to diagnose them

| Symptom | Likely cause | Fix |
|---|---|---|
| Login returns 303, yet profile returns 401 | Client did not store or send `JSESSIONID` | Attach `CookieManager`; reuse the same client/jar across requests |
| Test expects 303 yet receives 200 | HTTP client auto-follows redirects | Use `Redirect.NEVER` and assert `Location` |
| Test expects final 200 yet receives 303 | Client does not follow redirects | Use `Redirect.NORMAL` or send GET to `Location` manually |
| Following 303 results in 401 | Redirect works, cookie jar missing | Inspect the redirect and cookie axes separately |
| `CookieStore` has `JSESSIONID` yet server finds no session | Cookie not sent due to path/domain/secure/expiry, or session invalidated/timed out | Inspect request `Cookie` header, session store, and hostname |
| Calling `localhost:8080` fails | `@SpringBootTest` uses `RANDOM_PORT` | Use `@LocalServerPort` |
| Cookie works when running one test, lost in another | `CookieManager` recreated or uncontrolled shared global state | Create a dedicated client per scenario; check cookie policy |
| `visits` increments inaccurately under concurrency | Non-atomic read-modify-write | Isolate sequential tests; design atomic updates for concurrency |
| GET still succeeds after logout | Server failed to invalidate session or unexpectedly created a new one | Check `getSession(false)`, `invalidate()`, and auth policy |
| Unauthorized GET unexpectedly emits `Set-Cookie` | Code calls `getSession(true)` or a filter creates a session | Use `getSession(false)` when only checking; inspect security |
| Server session exists yet browser does not send cookie | `SameSite`/`Secure`/`Domain`/`Path` or CSRF flow | Test with a real browser when needed; inspect cookie attributes |
| Test passes alone, fails in suite | Static cookie jar, shared session, DB/Redis state, or context cache | Isolate fixtures/cleanup at the right boundaries |
| POST redirect uses 307 so GET handler never runs | 307 preserves POST method/body | Use 303 when POST → GET is intended |
| Immediate 401/403 on login after adding Security | Spring Security authentication/CSRF | Send valid credentials/CSRF token per contract; never turn off security recklessly |
| `@Transactional` test fails to roll back server DB write | Server request runs on a different thread/transaction | Use a test DB and explicit cleanup |

**Minimal debugging workflow:**

1. Inspect the **response status of POST login** before following. If 303, read **`Location`** and **`Set-Cookie`**.
2. Verify the HTTP client has a cookie handler and `CookieStore` holds `JSESSIONID`.
3. Check the next request's URL: **same host and path within cookie scope**? Do not mix `localhost` ↔ `127.0.0.1`.
4. If the client auto-follows, check **`response.uri()`** and final status to see where it landed.
5. If GET returns 401, verify the server received the `Cookie` header and **`getSession(false)`** returned a valid session.
6. If two clients mix state, look for a static `CookieManager`/`HttpClient` or shared session fixtures.
7. If logout fails to take effect, inspect `invalidate()`, session ID rotation, and caches/authentication stores.
8. If failures happen only in CI, inspect network sandboxes/ports, startup logs, parallelism, DB state, and browser vs Java client semantics.
9. Trace status, `Location`, `Set-Cookie`/`Cookie`, body, and session state **in request order**, rather than relying on one final assertion.
10. Avoid printing full session identifiers in CI logs; log cookie names or presence flags instead of secret values.

## 16. Practice exercises and self-checks

**Exercise 1 — Prove cookies are required.** Build an `HttpClient` without a `CookieManager`, send POST login and GET profile. Why does POST return 303 while GET returns 401? Does adding `CookieManager` change the redirect policy?

**Exercise 2 — Observe redirects explicitly.** Use `Redirect.NEVER` and assert 303, `Location`, and `Set-Cookie`. Then enable `Redirect.NORMAL` and assert the final URI/path along with 200. Why don't you directly see the 303 response as the final response in the second case?

**Exercise 3 — Two independent clients.** Create two `CookieManager` instances, log in Alice and Bob, and GET both profiles. Write assertions proving usernames do not cross over. What risk arises from calling `CookieHandler.setDefault` in `@BeforeEach` for the entire suite?

**Exercise 4 — Logout.** After logout, a client may still hold `JSESSIONID` in its jar. Why must the server reject the old session? Does a session cookie itself contain `username` and `visits`?

**Exercise 5 — Cookie scope.** Configure cookie `path=/demo`. Do `GET /demo/profile` and `GET /admin` both receive the cookie? Why can switching host from `localhost` to `127.0.0.1` lose the session even on the same machine?

**Exercise 6 — Redirect method.** Compare POST receiving 303 vs POST receiving 307. With 307, may the client arbitrarily switch to GET? Which status fits POST/Redirect/GET in this lesson?

**Exercise 7 — Concurrency.** Two concurrent `GET /profile` requests on the same session can lose a `visits` increment. Why? Propose how to test and store state atomically when business logic requires it.

**Exercise 8 — Production security.** If `X-Username` header were accepted directly into session without authentication, how could a client spoof privileges? Replace the demo with Spring Security login/CSRF/session-fixation policies, and test 401/403 and session rotation per design.

**Exercise 9 — Cookie flags.** When enabling `Secure` on the session cookie while still testing over HTTP `127.0.0.1` with JDK `HttpClient`, why might the cookie not be sent? Should you update the test transport or weaken the production cookie policy?

**Exercise 10 — Transactions.** A POST via `RANDOM_PORT` writes to the DB in a server transaction. Why does `@Transactional` on the JUnit method fail to roll back that DB write? Propose a cleanup mechanism.

**Short answers to remember:** `CookieManager` stores/sends IDs within scope; `HttpSession` holds server state; redirect policy decides whether `Location` is followed; 303 switches POST to GET; `invalidate` renders the old ID useless; context caching can reuse the server/session manager yet each test needs its own cookie jar; real HTTP transactions are distinct from test-method transactions.

## 17. Authoritative references

- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html) — `@SpringBootTest(RANDOM_PORT)`, `@LocalServerPort`, cross-thread transaction caveats.
- [Spring Boot 3.3 — Servlet Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html) — Servlet container settings and session cookie configuration.
- [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/) — `server.servlet.session.timeout`, `cookie.http-only/secure/same-site/path`.
- [Java SE 17 — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html) — HTTP client, cookie handler, and redirect defaults.
- [Java SE 17 — HttpClient.Redirect](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.Redirect.html) — `NEVER`, `NORMAL`, `ALWAYS`.
- [Java SE 17 — CookieManager](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/CookieManager.html) — `CookieStore`, policies, and cookie storage.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110) — `Location`/redirects, 303, 307, and 308.
- [MDN — Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie) — `HttpOnly`, `Secure`, `SameSite`, `Domain`/`Path`, and expiration.

**Conclusion:** Multi-step HTTP testing requires **preserving state properly on both client and server**. `CookieManager` makes the client send back `JSESSIONID`; `HttpSession` retains data on the server; `Location` + redirect policy decide the next request. Verify **every status/header/body across the sequence**, create a separate cookie jar per test, never rely on test order, and keep this session demo clearly distinct from production authentication and security.