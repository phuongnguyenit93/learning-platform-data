# Distinguishing Per-Request Context from Sessions Persisting Across Requests

## 1. Core Question

When learning Spring Security, there is a seemingly contradictory phenomenon: **every HTTP request has its own security context during processing, yet a user still logs in once and is recognized on subsequent requests**. This works by distinguishing between two lifecycles:

- **Per-request context**: data that is only meaningful while the server processes a specific HTTP request, such as request attributes, request-scoped beans, and the SecurityContext bound to the current processing thread.
- **Session (HTTP session)**: server-side state that can persist across **multiple HTTP requests** of the same browser/client session, linked by a session identifier (commonly via a cookie named JSESSIONID).

**SecurityContext is not HttpSession.** SecurityContext holds the Authentication information for the current security context; HttpSession is a storage mechanism lasting longer than a single request. In a traditional form-login application, Spring Security can save the SecurityContext in the session and **reload it for each request**. Thus, each request gets an active context while the login state is still maintained.

This lesson helps you:

1. Clearly explain HTTP requests, request scope, SecurityContextHolder, SecurityContext, HttpSession, and session cookies.
2. Trace a single login across three consecutive requests.
3. Distinguish **loading the context**, **saving the context**, and **ending the request**.
4. Understand when to use server-side sessions and when to re-authenticate on every request (stateless).
5. Run a Spring Boot 3.x, Java 17+ example to observe values that change per request versus values that persist per session.
6. Recognize bugs related to sessions, cookies, CSRF, timeouts, ThreadLocal, and SecurityContextRepository.

## 2. HTTP Is a Protocol That Does Not Remember Login Sessions on Its Own

Each HTTP request has a method, URL, headers, and optionally a body. HTTP does not inherently guarantee that two consecutive requests belong to the same user. The server must have a mechanism to link requests, such as a **session cookie**, a **Bearer token**, or another credential.

Suppose a client sends three requests:

~~~http
GET /api/state HTTP/1.1
Host: localhost:8080

GET /api/state HTTP/1.1
Host: localhost:8080

GET /api/state HTTP/1.1
Host: localhost:8080
~~~

Those three requests are **three separate units of processing**, even though the URL is identical. Without a cookie, token, or matching credential, you cannot conclude from the `/api/state` path alone that they come from the same authenticated identity.

In a typical stateful application, the browser adds a cookie:

~~~http
GET /api/state HTTP/1.1
Host: localhost:8080
Cookie: JSESSIONID=example-session-id
~~~

**The cookie value above is illustrative, not a real session ID.** The container/application uses the ID to find the server-side session. The cookie normally holds **the session identifier**, not the entire UserDetails/Authentication object. Do not put real session identifiers into logs, URLs, chat messages, or JSON responses, because anyone who obtains a valid ID can try to hijack the session.

### Three levels of state to distinguish

| Object | Lifecycle | Example | Notes |
| --- | --- | --- | --- |
| **HttpServletRequest** | One request/related dispatch chain | Method, URL, headers, request attributes | Once the request finishes, that instance is not reused for the next request. |
| **Spring @RequestScope bean** | One HTTP request | Request marker value, temporary processing data | Does not automatically persist into the next request. |
| **SecurityContextHolder** | Active context; by default bound to the Servlet processing thread | Accessing Authentication during processing | Loaded and cleared by filter mechanics; **not** a long-lived store across requests. |
| **SecurityContext** | Object containing the security context's Authentication | Principal, authorities via Authentication | Can be saved/loaded by SecurityContextRepository depending on configuration. |
| **HttpSession** | Multiple requests until expired or invalidated | Session attributes, login data when stored here | Lives on the server/container or configured session store. |
| **Spring @SessionScope bean** | One HTTP session | UI preferences or demo data tied to the session | One session reuses the bean; another session has a different bean. |
| **Session cookie (commonly JSESSIONID)** | On the client per cookie/browser attributes | An ID linking to the server-side session | Not synonymous with SecurityContext or the server-side session itself. |

**The word "context" can refer to different concepts.** Spring Framework's request scope and Spring Security's SecurityContext are two separate mechanisms. Both relate to the request being processed, yet only SecurityContext holds authentication/authorization info. Conversely, HttpSession can hold many kinds of data, not just security.

## 3. SecurityContextHolder and the Current Authentication

On the Servlet stack, Spring Security provides a way to access the current identity via SecurityContextHolder:

~~~java
SecurityContext context = SecurityContextHolder.getContext();
Authentication authentication = context.getAuthentication();
~~~

This is a **Java fragment requiring imports**, not a standalone runnable program. The types belong to the **org.springframework.security.core.context** and **org.springframework.security.core** packages.

A SecurityContext contains an Authentication, and Authentication typically holds:

- **principal**: the identity (e.g., UserDetails or Jwt).
- **authorities**: the set of GrantedAuthority used for authorization.
- **authenticated**: authentication status according to the mechanism used.
- **credentials/details**: information meaningful during authentication, often handled so unnecessary secrets are not retained.

### 3.1. Why doesn't SecurityContextHolder keep the login forever?

The default strategy of SecurityContextHolder on Servlet is **MODE_THREADLOCAL**. When a request is processed on a worker thread, code on that thread can read the current security context.

However, web servers reuse threads across multiple clients. If a ThreadLocal holding person A's identity leaked into person B's request, that would be a severe security isolation flaw. The Spring Security filter chain must manage the context lifecycle and **clear the context when request processing ends** per the applicable mechanism.

~~~text
Time T1: Thread-X handles Alice's request
               SecurityContextHolder -> Alice
               Processing finished -> clear/reset context

Time T2: Thread-X is reused for Bob's request
               Spring Security loads/authenticates new context -> Bob
               Processing finished -> clear/reset context
~~~

**A thread does not represent a user**, and a session is not permanently pinned to one thread. Two requests from the same user can be processed by two different threads; multiple concurrent requests in the same session can also run in parallel.

Use **@AuthenticationPrincipal**, an **Authentication** parameter in Spring MVC, or supported context accessors when retrieving the identity in your application. Do not store the current request's Authentication in a **static** variable or singleton field and reuse it for others.

### 3.2. The current request's context can be retrieved from longer-lived data

SecurityContextHolder serves **accessing the active context**, whereas **SecurityContextRepository** decides how to load/save SecurityContext at appropriate points. For session-based login, the repository typically uses HttpSession.

Important notes:

- Start of request: SecurityContext can be loaded from the repository.
- During request: SecurityContextHolder provides the current Authentication.
- On successful login: the authentication mechanism must ensure SecurityContext is saved if login persistence is desired.
- End of request: the context bound to the thread is cleared.
- Subsequent request: the repository can return the saved security state, and Spring Security attaches it to the new processing context.

**This does not mean SecurityContextHolder holds the same Java object across every request**, nor does it mean users must log in again on every request when the system has a store for authentication state.

## 4. How Does a Session-Based Login Cycle Unfold?

Suppose a Spring MVC application uses **formLogin** with session persistence:

~~~text
                 Request 1: GET /private
Browser ----------------------------------------------> Server
(Unauthenticated)                                         |
                                                          | login required
Browser <---------------------------------------------- 302 /login
                 Request 2: GET /login
Browser ----------------------------------------------> login page
                 Request 3: POST /login + CSRF token
Browser ----------------------------------------------> authenticate username/password
                                                          |
                                                          +--> Authentication succeeds
                                                          +--> SecurityContext is saved
                                                          +--> HttpSession links identity
Browser <---------------------------------------------- 302 + session cookie (if needed)
                 Request 4: GET /private + cookie
Browser ----------------------------------------------> Server
                                                          |
                                                          +--> Look up HttpSession by cookie
                                                          +--> SecurityContextRepository
                                                          |    retrieves saved context
                                                          +--> Current SecurityContextHolder
                                                          |    holds corresponding Authentication
                                                          +--> Authorization permits
Browser <---------------------------------------------- 200 private page
                                                          |
                                                          +--> Clear thread context when done
                 Request 5: GET /private + cookie
Browser ----------------------------------------------> Server
                                                          |
                                                          +--> Reload context for new request
Browser <---------------------------------------------- 200 private page
~~~

**A session is not an infinitely long request.** Request 4 and request 5 are two independent executions. Login state is reused because the same client sends information linking to a still-valid session, not because an old ThreadLocal was left uncleared.

### 4.1. Where do HttpSession and cookies differ?

Under the standard Servlet model:

- **HttpSession** is the state managed by the server/container (or stored in another store when integrating Spring Session).
- **The JSESSIONID cookie** is a common way for the client to provide the session ID on subsequent requests.
- The server looks up the session via that ID and can then read session attributes, including SecurityContext when the repository is configured to store it in the session.
- The cookie may still exist while the server-side session has expired or been invalidated; in that case, the old login state is not automatically restored.
- A session may exist on the server, yet if the client does not send the right ID, the server normally will not recognize it as the same session.

A new browser tab in the same profile normally shares cookies matching the domain/path and can share the session. An incognito window or another profile normally has an independent cookie jar. Do not assume **each tab is a separate session**.

### 4.2. What happens upon logout?

In a common Servlet logout configuration, successful logout clears SecurityContext and invalidates HttpSession if configured by default. Subsequent requests no longer have a valid security session, so when accessing protected areas, the browser must re-authenticate.

A session can also end due to **timeout**, an administrator revoking login/session rights, or the server losing session state. An old cookie is not enough to prove that the server-side session still exists.

**The Session ID can change right at login** thanks to **session fixation** protection. Therefore, do not design your application assuming "the ID before and after login is always the same."

## 5. SecurityContextRepository: The Bridge Between Current and Future Requests

In Spring Security 6.x on Servlet, the default repository is typically **DelegatingSecurityContextRepository**, combining:

- **HttpSessionSecurityContextRepository**: binds SecurityContext to HttpSession, suited for maintaining authentication across multiple HTTP requests.
- **RequestAttributeSecurityContextRepository**: stores the context in a request attribute so it can be restored across dispatches of the **same request**, such as an ERROR dispatch, rather than keeping login across independent HTTP requests.

Example:

~~~text
Request A (REQUEST dispatcher)
    |
    +--> SecurityContextHolder / Authentication
    +--> RequestAttributeSecurityContextRepository
    |        |
    |        +--> on transition to ERROR dispatcher in the same request
    |             can still retrieve the context
    |
    +--> HttpSessionSecurityContextRepository
             |
             +--> Requests B and C with the same valid session
                  can load the saved authentication
~~~

**The two repositories address two different storage scopes.** The name "request attribute" does not mean the object is put into a cookie; "HttpSessionSecurityContextRepository" likewise does not mean the entire SecurityContext is sent to the browser.

### 5.1. Spring Security 6 requires attention to context saving

In Spring Security 6.x, the default mechanism uses **SecurityContextHolderFilter** to read SecurityContext from SecurityContextRepository and place it into SecurityContextHolder. This choice favors **explicit saving**: the filter itself **does not automatically save every context mutation back to the repository at the end of the request** like the older mechanism did.

Standard authentication filters such as form login processing already perform the necessary state saving on the success path. However, if you write a **custom authentication controller/filter** and only do:

~~~java
SecurityContextHolder.getContext().setAuthentication(authentication);
~~~

that may only alter the context for the current request and **not be enough to persist login to the next request**.

For self-managed flows with a properly configured repository, the basic pattern is creating the context and asking the repository to save it:

~~~java
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authentication);
SecurityContextHolder.setContext(context);
securityContextRepository.saveContext(context, request, response);
~~~

This is a **conceptual fragment**, not a complete controller: it requires a verified Authentication, the SecurityContextRepository matching the SecurityFilterChain itself, the current HttpServletRequest/HttpServletResponse, a session authentication strategy, and safe login/logout handling. **Do not take this snippet as a guide to rolling custom login while skipping AuthenticationManager or session fixation protections**.

If you simply use standard formLogin/OAuth2 login, you normally do not need to write this context-saving step manually; rely on the authentication mechanisms supported by Spring Security.

## 6. Hands-On Example: Two Kinds of Data, Two Lifecycles

An intuitive way to separate **request lifetime** from **session lifetime** is creating two Spring beans:

- **@RequestScope**: one instance serving each HTTP request.
- **@SessionScope**: one instance lasting for the lifetime of an HTTP session.

These are **Spring Framework scoping mechanisms**, not SecurityContext itself. However, combining them with formLogin and the current Authentication helps demonstrate by observation: a new request gets new request-scope data, while the login session and session-scope data can be reused.

### 6.1. Project setup

Use **Spring Initializr** to create Spring Boot **3.x**, Java **17+**, Gradle, group **com.example**, artifact **demo**, package **com.example.demo**. Select:

- **Spring Web** → spring-boot-starter-web.
- **Spring Security** → spring-boot-starter-security.

The application creates a test user **learner/demo123** and uses Spring Security's default form login; no separate login HTML needs to be written.

Create the file:

~~~text
src/main/java/com/example/demo/RequestSessionDemoApplication.java
~~~

### 6.2. Complete Java code

~~~java
package com.example.demo;

import java.util.Map;
import java.util.UUID;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.context.annotation.RequestScope;
import org.springframework.web.context.annotation.SessionScope;

@SpringBootApplication
public class RequestSessionDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(RequestSessionDemoApplication.class, args);
    }
}

@Configuration
@EnableWebSecurity
class WebSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .sessionManagement(session -> session
                    .sessionCreationPolicy(
                        SessionCreationPolicy.IF_REQUIRED))
                .authorizeHttpRequests(auth -> auth
                    .requestMatchers(HttpMethod.GET, "/public")
                        .permitAll()
                    .requestMatchers(HttpMethod.GET, "/api/state")
                        .authenticated()
                    .anyRequest().denyAll())
                .formLogin(form -> form
                    .defaultSuccessUrl("/api/state", true)
                    .permitAll())
                .logout(logout -> logout
                    .logoutSuccessUrl("/login?logout")
                    .permitAll())
                .build();
    }

    @Bean
    UserDetailsService userDetailsService() {
        return new InMemoryUserDetailsManager(
                User.withUsername("learner")
                    .password("{noop}demo123")
                    .roles("USER")
                    .build());
    }
}

@Component
@RequestScope
class PerRequestMarker {

    private final String marker = UUID.randomUUID().toString();

    public String marker() {
        return marker;
    }
}

@Component
@SessionScope
class PerSessionMarker {

    private final String marker = UUID.randomUUID().toString();

    public String marker() {
        return marker;
    }
}

@RestController
class ContextController {

    private final PerRequestMarker requestMarker;
    private final PerSessionMarker sessionMarker;

    ContextController(PerRequestMarker requestMarker,
            PerSessionMarker sessionMarker) {
        this.requestMarker = requestMarker;
        this.sessionMarker = sessionMarker;
    }

    @GetMapping("/public")
    public Map<String, String> publicEndpoint() {
        return Map.of("message", "public");
    }

    @GetMapping("/api/state")
    public StateView currentState(Authentication authentication,
            HttpServletRequest request) {
        String requestId = requestMarker.marker();
        String sessionMarkerValue = sessionMarker.marker();
        boolean hasHttpSession = request.getSession(false) != null;

        return new StateView(
                authentication.getName(),
                requestId,
                sessionMarkerValue,
                hasHttpSession);
    }

    public record StateView(
            String username,
            String requestMarker,
            String sessionMarker,
            boolean hasHttpSession) {
    }
}
~~~

**Runnability notes for the example:**

- **RequestSessionDemoApplication** is the sole public top-level class; its name matches the Java filename.
- The remaining classes are package-private top-level classes discovered by component scanning in the same package.
- **@RequestScope** and **@SessionScope** use scoped proxies by default, so a singleton controller can inject these beans; each method call on the proxy is routed to the instance in the appropriate scope.
- **Authentication** is supplied by Spring MVC to the authenticated endpoint.
- **sessionMarker** is a randomly generated demo value in session scope, **not the real session ID**, to avoid exposing sensitive session identifiers over the API.
- **UUID** produces random values, so the response content has no fixed UUID to copy verbatim as expected stdout.
- **{noop}** is suitable only for local learning examples; real systems must hash passwords with a proper PasswordEncoder.

### 6.3. Running

In the project root directory containing the Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

On Windows use **gradlew.bat bootRun**. The application typically listens on **http://localhost:8080**, unless you change `server.port`.

The easiest way to observe with a browser:

1. Visit **http://localhost:8080/public**: returns public JSON, no login required.
2. Open **http://localhost:8080/api/state** while unauthenticated: redirects by default to **/login**.
3. Log in with **learner / demo123** on the form page generated by Spring Security.
4. Successful login redirects to **/api/state**, returning JSON containing username, requestMarker, sessionMarker, and hasHttpSession.
5. Reload **/api/state** a few times in the same browser profile with a valid session cookie.
6. Open an **incognito window** and log in as the same user to compare the sessionMarker of a different session.
7. Log out or let the session expire, log in again, and observe the new sessionMarker in the new session.

Example depicting two GET calls after logging in with browser profile A:

~~~text
GET /api/state (attempt 1)
username = learner
requestMarker = R1 (actual UUID value)
sessionMarker = S1 (actual UUID value)
hasHttpSession = true

GET /api/state (attempt 2, same session)
username = learner
requestMarker = R2 (UUID different from R1)
sessionMarker = S1 (still the same value)
hasHttpSession = true
~~~

**R1, R2, S1 are illustrative labels, not fixed UUID outputs from the application.** The browser sends back the session cookie so Spring Security loads Authentication, while Spring SessionScope retrieves the PerSessionMarker instance for that session. Meanwhile, PerRequestMarker is created anew for the second request.

### 6.4. Observation table across multiple clients and requests

| Scenario | requestMarker | sessionMarker | username / authentication |
| --- | --- | --- | --- |
| First GET after login in browser A | R1 | S1 | learner |
| Reload GET in browser A, same session | R2 | S1 | learner |
| Another GET in browser A | R3 | S1 | learner |
| Login in an independent incognito window B | R4 | S2 | learner, but a different session |
| Logout A then log in with a new session | R5 | S3 | learner, session has changed |
| Browser A sends old cookie from expired session | R6 when endpoint is processed after re-authenticating | S4 after new session | Must log in again unless another re-auth mechanism exists |

The R/S labels are **logical, not actual sequence numbers issued by the server**. Two browser windows can access the same username without sharing a session if their cookie jars are isolated. Conversely, two tabs normally share the session cookie and login state.

**Note on session-scoped beans:** the demo does not recreate PerSessionMarker on every request. However, when deploying multiple server instances, session data must have an appropriate storage/replication mechanism if requests routed to another instance need to retain state. This is a distributed systems concern, not a ThreadLocal issue.

## 7. Automated Testing of Both Lifecycles

Performing multiple requests with the same **MockHttpSession** is a more deterministic verification than simply opening a page in a browser.

Add to the project's **build.gradle** if not already present:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

This is a **Gradle Groovy DSL fragment**, not the full build.gradle file; if Spring Initializr already declared starter-test, do not add a duplicate.

Create **src/test/java/com/example/demo/RequestSessionDemoTest.java**:

~~~java
package com.example.demo;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.http.HttpSession;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class RequestSessionDemoTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    ObjectMapper json;

    @Test
    void requestScopeChangesWhileSessionScopePersists()
            throws Exception {
        // Real form login, not just mocking Authentication.
        MvcResult login = mvc.perform(post("/login")
                    .param("username", "learner")
                    .param("password", "demo123")
                    .with(csrf()))
                .andExpect(status().is3xxRedirection())
                .andReturn();

        HttpSession httpSession =
                login.getRequest().getSession(false);
        assertNotNull(httpSession);
        MockHttpSession session = (MockHttpSession) httpSession;

        MvcResult first = mvc.perform(
                    get("/api/state").session(session))
                .andExpect(status().isOk())
                .andReturn();

        MvcResult second = mvc.perform(
                    get("/api/state").session(session))
                .andExpect(status().isOk())
                .andReturn();

        JsonNode a = json.readTree(
                first.getResponse().getContentAsString());
        JsonNode b = json.readTree(
                second.getResponse().getContentAsString());

        assertEquals("learner", a.get("username").asText());
        assertEquals("learner", b.get("username").asText());

        // Each HTTP request uses a distinct request-scoped instance.
        assertNotEquals(
                a.get("requestMarker").asText(),
                b.get("requestMarker").asText());

        // Same HttpSession -> keeps the same session-scoped instance.
        assertEquals(
                a.get("sessionMarker").asText(),
                b.get("sessionMarker").asText());
    }
}
~~~

Run:

~~~bash
./gradlew test
~~~

On Windows use **gradlew.bat test**. The test focuses on lifecycle differences; it does not attempt to pin a specific UUID or session ID. If the program changes SessionCreationPolicy, the authentication mechanism, or how the context is saved, the results may change and the test must be adjusted to match the intended policy.

**Why does this test differ from @WithMockUser?** @WithMockUser mocks Authentication in tests without necessarily testing the login form and state persisted across requests. Here, the test performs POST /login with a valid CSRF token, grabs the login request's session, and reuses **that exact session** across two GETs. Consequently, the check exercises both form authentication persistence and the two Spring bean scopes.

## 8. SessionCreationPolicy: Impact on SecurityContext Across Requests

Spring Security Servlet provides **SessionCreationPolicy** values:

| Policy | How does Spring Security use HttpSession? | Interpretation |
| --- | --- | --- |
| **ALWAYS** | Creates an HttpSession | Suitable when configuration intentionally requires a session for requests. |
| **IF_REQUIRED** | Creates a session only when needed | Common for session-based login; Spring Security may create a session to store required info. |
| **NEVER** | Does not proactively create a session, but can use an existing one | Does not mean no session is used; check where else sessions are created. |
| **STATELESS** | Spring Security neither creates a session nor uses it to obtain SecurityContext | Suited for per-request authentication like Bearer tokens, when fully configured. |

Example switching to stateless at the Security layer:

~~~java
http.sessionManagement(session -> session
        .sessionCreationPolicy(SessionCreationPolicy.STATELESS));
~~~

This is a **configuration fragment**, not a standalone file, and should not be copied into a formLogin application that needs persistent sessions without redesigning the login mechanism. When stateless, each request is authenticated based on credentials included in the request (such as Authorization: Bearer ...) rather than relying on a SecurityContext saved in HttpSession.

**STATELESS does not guarantee that the entire Java application never creates an HttpSession.** It governs Spring Security's behavior; MVC code, other libraries, or application code itself can still call `request.getSession()` and create a session for other purposes. If the goal is a truly sessionless API, audit the entire stack and do not use `@SessionScope`/HttpSession for state you intend to eliminate.

### 8.1. Comparing session-based form login and Bearer tokens

~~~text
STATEFUL:
  POST /login (password, CSRF ...)
       -> server saves SecurityContext bound to HttpSession
       -> browser sends session cookie on subsequent requests
       -> server looks up session, loads Authentication

STATELESS:
  GET /api/data + Authorization: Bearer <token>
       -> server validates token on the current request
       -> builds Authentication for that request
       -> does not rely on HttpSession to obtain SecurityContext
       -> next request needs its own valid credential
~~~

The stateless model does not mean **SecurityContextHolder** ceases to exist. Spring Security still needs Authentication during request processing for authorization to work; the difference lies in **how identity is verified/loaded on each request**, not the presence of the SecurityContext object.

HTTP Basic can send credentials on every request; Bearer tokens do the same. Some systems combine multiple mechanisms, or use JWTs in cookies; therefore **"having a cookie" does not automatically mean "having an HttpSession"**, and **"not having JSESSIONID" does not automatically mean "no authentication"**.

### 8.2. Do not use request attributes in place of a session

Data set via:

~~~java
request.setAttribute("currentStep", "checked");
~~~

belongs to that specific request. RequestAttributeSecurityContextRepository can serve an **ERROR dispatch of the same request**, yet request attributes are not a store for user state on tomorrow's visit.

If you need to keep a simple preference across multiple requests in a session:

~~~java
HttpSession session = request.getSession();
session.setAttribute("preferredLanguage", "vi");
~~~

This is a fragment inside request-handling code; it requires importing HttpSession/HttpServletRequest, and you must evaluate the risks of storing data in the session. Reading on a later request when the client carries the same session:

~~~java
HttpSession session = request.getSession(false);
String language = session == null
        ? null
        : (String) session.getAttribute("preferredLanguage");
~~~

**getSession()** can create a session; **getSession(false)** only looks up the current session and returns null if it does not exist. Do not accidentally create a session just to check whether the client is logged in.

## 9. Important Limitations of the Request Context

### 9.1. Asynchronous calls and thread pools

Because SecurityContextHolder on Servlet uses ThreadLocal by default, spawning a new thread with **new Thread**, using **CompletableFuture**, or **@Async** can cause code on the child thread **not to see the current Authentication**, or to see a different context depending on the setup. Do not use ThreadLocal to implicitly "propagate login."

When asynchronous work must run under a controlled authenticated context, you can use helpers such as **DelegatingSecurityContextRunnable**, **DelegatingSecurityContextExecutor**, or appropriate context propagation methods. Even so, you must still consider session expiration timing, authority validity, and limiting the propagation of credentials into background jobs.

**Do not switch SecurityContextHolder to MODE_GLOBAL just to fix an @Async issue**: in a multi-user server application, that breaks the identity boundary between requests.

### 9.2. Multiple concurrent requests in the same session

The same HttpSession can be read or updated by two different requests **simultaneously**. Session attributes do not automatically make read-modify-write operations concurrency-safe. Do not store shared mutable objects without designing locking, immutability, transactional storage, or appropriate update rules.

~~~text
Request A, thread-1 -> HttpSession S -> attribute "cart"
Request B, thread-2 -> HttpSession S -> attribute "cart"

Both can access the same session data nearly simultaneously.
Each thread still has its own request-processing context.
~~~

Sharing the same session and the same username does not force requests into strict sequential execution.

### 9.3. Distributed multi-server setups and session stores

With a single server, sessions can stay in container memory. When running multiple replicas or restarting servers, consider a shared store such as Spring Session with Redis or an appropriate session affinity mechanism. If sessions are not distributed consistently, one request may load Authentication while a subsequent request routed to a different replica fails to find the session.

When choosing to store sessions outside process memory, consider:
- Serializability of session data.
- TTL/timeout and session invalidation.
- Security of Redis/equivalent store.
- Size of data stored in the session; avoid pushing large reports into the session.
- Handling user authority changes after login; long-lived cached authorities may not reflect the latest permission changes without a refresh/revocation strategy.

## 10. Security Notes for Sessions and Cookies

### 10.1. Do not expose the session identifier

A cookie containing a session ID is a **bearer credential in the sense that anyone who controls a valid session ID can try to use that session**. Do not put session IDs in query strings, logs, public screenshots, or JSON APIs. The demo only returns a **random sessionMarker not used for authentication**, never JSESSIONID.

Cookie configuration should be evaluated per environment:
- **Secure**: cookies are sent only over HTTPS when enabled; production should use HTTPS.
- **HttpOnly**: restricts JavaScript access to cookies when configured.
- **SameSite**: helps reduce certain cross-site cookie-sending scenarios, yet does not replace CSRF protection on its own.
- **Path/Domain**: limits where cookies are sent.
- **Max-Age/Expires** and session timeout policies: determine appropriate lifecycles.

### 10.2. CSRF and sessions are not the same thing

In browser applications using session cookies, the browser can automatically send cookies when cookie policy conditions are met. Therefore, state-changing POST/PUT/DELETE requests generally need **CSRF protection**. Spring Security enables CSRF by default for the appropriate Servlet model. Do not disable CSRF simply because the user is "logged in."

In the demo, the business endpoints only use **GET**; POST /login is still handled by Spring Security alongside the CSRF token in the generated form. If you use curl to send POST /login without the right CSRF token/cookie, the request can be rejected with 403 before the password is even checked.

**Limitation:** actual SameSite and CSRF behavior also depends on the client, how credentials are sent, reverse proxies, and deployment configuration. Do not treat SameSite as the sole solution.

### 10.3. Session fixation, timeout, and logout

An attacker may try to force a victim to use a predetermined session identifier (session fixation). Spring Security supports rotating the session ID upon successful authentication in the appropriate default configuration. Do not disable this protection just to preserve the same ID across login.

On logout, ensure the session and SecurityContext can no longer be misused; if using remember-me or independent tokens, you may also need to revoke the corresponding credentials. When a session times out, the next request must be treated as no longer having a valid login state, unless another re-authentication mechanism applies.

### 10.4. Do not store all secrets in the session

HttpSession is server-side storage, not a "limitless security vault." Do not put plaintext access tokens, private keys, passwords, or unnecessary sensitive data objects in the session just to avoid a database call. Keep sessions small, set sensible TTLs, encrypt/protect the store when needed, and enforce authorization when loading actual data.

## 11. Diagnosing Common Misconceptions

| Symptom | Common cause | How to check / fix |
| --- | --- | --- |
| First request after login succeeds, subsequent request asks to log in again | Cookie not sent, session expired, SecurityContext not saved, or wrong repository | Check Set-Cookie/Cookie, SecurityContextRepository, session policy, and auth flow. |
| Switched to STATELESS and form login stopped remembering users | Spring Security does not use HttpSession to retrieve SecurityContext | Use a per-request auth mechanism, or pick an appropriate session policy again. |
| Reading SecurityContextHolder inside @Async returns null/anonymous | Thread-bound context is not automatically propagated | Use proper delegation/propagation mechanisms; do not switch to MODE_GLOBAL. |
| @RequestScope bean changes on every reload | Expected per request lifetime | Use @SessionScope only if per-session data is genuinely needed. |
| @SessionScope bean changes within the same session | Cookie/session changed, timeout, logout, distributed session config | Check session lifecycle, cookies, and application topology. |
| Two tabs share state | Shared session cookie within the same browser profile | Expected for session-based authentication; isolating them requires a different business model. |
| HttpSession exists yet SecurityContext is empty | Session holds other data, auth is not stored there, not logged in, or stateless | Do not use `session != null` to prove authentication. |
| JSESSIONID cookie exists in browser yet endpoint still returns 401/302 | Session missing/expired or lacks valid authentication | Inspect repo, cookie domain/path, timeout, and logout. |
| Called SecurityContextHolder.setContext yet next request loses login | Forgot to call saveContext under explicit-save mechanics | Use standard auth flow or save via SecurityContextRepository properly. |
| ERROR dispatch cannot see the same request's context | Request dispatcher or repository does not retain corresponding request attribute/context | Check RequestAttributeSecurityContextRepository, filter mappings, and error dispatch. |
| Updates to attributes in the same session get lost | Race condition across multiple parallel requests | Design for concurrency, synchronization, or transactional data storage. |
| Multi-replica app "logs users out randomly" | Session exists on only one replica and load balancer routes requests elsewhere | Use a shared session store/appropriate affinity and monitor session TTL. |

### Logging during investigation

In a development environment, you can enable:

~~~properties
logging.level.org.springframework.security=DEBUG
~~~

Focus on observing: HTTP method/path, whether the request carries a cookie, authentication mechanism type, SecurityContextRepository, username/authorities after authentication, and redirects/statuses. **Never log raw cookie headers, tokens, passwords, or session identifiers**.

## 12. Self-Assessment Questions

1. Why can two requests from the same user be handled on two different threads while the user remains logged in?
2. How does HttpSession differ from the JSESSIONID cookie? What is stored on the client and what is stored on the server?
3. Is SecurityContextHolder a long-lived store of authentication across all requests?
4. Which step in the authentication lifecycle does SecurityContextRepository solve?
5. Why is RequestAttributeSecurityContextRepository useful for ERROR dispatches yet insufficient for maintaining login across multiple HTTP requests?
6. When using Spring Security 6, why might simply setting Authentication in SecurityContextHolder not be enough for the next request?
7. When reloading `/api/state`, how do `requestMarker` and `sessionMarker` change if the session is still alive?
8. Do two incognito windows with independent cookie jars using the same username necessarily share an HttpSession?
9. If an application uses `Authorization: Bearer` on every request, is SecurityContext still used for authorization during the current request?
10. How do `SessionCreationPolicy.NEVER` and `STATELESS` differ?
11. Why doesn't sharing the same session guarantee that requests run sequentially or that operations on session attributes are always thread-safe?
12. When a user logs out or a session times out, why doesn't a leftover cookie prove they are still logged in?
13. If using Spring WebFlux instead of Spring MVC, what context mechanism replaces ThreadLocal SecurityContext?

**Remember:** **request context** answers "what context is active during this HTTP execution?"; **HTTP session** answers "what server-side state is linked across multiple HTTP requests?". In Spring Security Servlet, **SecurityContextHolder** serves the request currently being processed, **SecurityContextRepository** can load/save authentication, and **HttpSession + session cookie** can maintain that link across multiple requests. Stateful and stateless differ primarily in **how identity is re-obtained**, not whether SecurityContext exists during authorization.

## Official Documentation

- Spring Security 6.5 — Authentication Persistence and Session Management: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html
- Spring Security 6.5 — Authentication Architecture / SecurityContextHolder: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html
- Spring Security 6.5 — SecurityContextRepository API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/context/SecurityContextRepository.html
- Spring Security 6.5 — Form Login: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html
- Spring Framework — Request Scope and Session Scope: https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html
- Spring Security — CSRF Protection: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
