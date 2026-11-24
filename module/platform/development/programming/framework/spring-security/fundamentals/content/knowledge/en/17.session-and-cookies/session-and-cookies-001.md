# What Is a Session and Why Doesn't HTTP Automatically Keep Login State

> **Module:** Spring Security – fundamentals  
> **Topic group:** Sessions and cookies  
> **Lesson:** What is a session and why doesn't HTTP automatically keep login state

## 1. Learning Objectives

After this lesson, you will be able to:

1. Accurately explain what it means that **HTTP is a protocol without application state between requests** (*stateless*).
2. Describe how **session**, **session ID**, **cookie**, **SecurityContext**, and **Authentication** work together so a browser feels like "log in once, use across multiple pages".
3. Read HTTP exchanges involving `Set-Cookie` and `Cookie`, distinguishing which information resides on the browser and which resides on the server.
4. Use `HttpSession` on the Servlet stack and understand when Spring Security stores or restores identity from the session.
5. Build a Java 17+ application with Spring Boot, form login, cookie session, a protected endpoint, logout, and a test verifying two consecutive authenticated requests.
6. Distinguish between session-based login, HTTP Basic, bearer token/JWT, and the `SessionCreationPolicy` options.
7. Avoid common mistakes: confusing cookies with sessions, assuming the presence of a cookie means authenticated, disabling CSRF, putting session IDs in URLs, or ignoring timeouts and session fixation.

## 2. What Does HTTP Being "Stateless" Mean?

HTTP communicates in **request → response** pairs. A request has a method, a target URL, headers, and optionally a body; a response has a status, headers, and a body. **By the nature of the protocol, a second request does not automatically inherit "who is logged in" from a previous request.**

Example of two independent requests:

~~~http
GET /profile HTTP/1.1
Host: example.test
~~~

~~~http
GET /profile HTTP/1.1
Host: example.test
~~~

If they do not carry credentials or any other identifying marker, the server has no basis from these two requests alone to conclude they come from the same account. The server can remember data in RAM or a database, but it needs **a way to link a new request to that data**.

Points to distinguish:

- **Stateless at the HTTP layer** does not mean the server cannot store data.
- **Keep-Alive / HTTP/2 / HTTP/3** can reuse connections or multiplex multiple streams; this does not inherently create a login session for a user. A network connection is not an application identity.
- Two requests coming from the same IP address do not prove the same user: NAT, proxies, public Wi-Fi, mobile networks, and IP changes all make IP unsuitable for identifying a session.
- `User-Agent`, `Referer`, IP address, or any arbitrary header sent by the client is not sufficient for authentication.
- The server can still use cookies, tokens, URL parameters, or other mechanisms to *build application state on top of HTTP*. For traditional web login, cookie + server session is the familiar approach.

**Core takeaway:** HTTP provides the mechanism for sending messages; "remembering that this request belongs to Alice" is the responsibility of **application-layer session/authentication management**.

## 3. How Do Session, Cookie, and Session ID Differ?

A traditional session-based login system typically consists of:

| Concept | Primary location | Function |
| --- | --- | --- |
| **HTTP request** | In transit client → server | Sends the current action; each request is processed independently in HTTP semantics |
| **HTTP response** | Server → client | Returns the result, may set cookies |
| **Cookie** | Stored by the browser and sent per domain/path/SameSite/Secure rules | Carrier for a value such as a session ID across requests |
| **Session ID** | In the browser's cookie and as a server-side lookup key | An opaque identifier for a session; **not a password or an object containing the entire user** |
| **Server-side session** | Server RAM, session store, cache, or database | Stores session-related data, e.g., `SecurityContext`, temporary data |
| **SecurityContext** | During request processing and may be persisted across requests | Holds Spring Security's `Authentication` |
| **Authentication** | Spring Security object | Principal, authorities, and authentication state |
| **Session timeout** | Server policy | Determines how long of inactivity causes a session to become invalid |

In a common Servlet configuration, the cookie is named **`JSESSIONID`**. When using Spring Session or another mechanism, the cookie name may be **`SESSION`** or a configured name; do not write code that hard-depends on a single name if the infrastructure might change.

Simplified example:

~~~text
Browser:
  Cookie: JSESSIONID=s_8b7f...   <-- contains only the identifier

Server:
  sessionStore["s_8b7f..."] = {
    SecurityContext: Authentication(principal="alice",
                                    authorities=["ROLE_USER"]),
    otherSessionData: ...
  }
~~~

The string above is illustrative data, **not a fixed internal format** of Spring Security. A real session ID must be randomly generated and sufficiently unpredictable by the container/session infrastructure. Do not invent IDs like `userId=42`, `alice-2026`, or sequential strings.

### A cookie is not a session

A cookie is a client-side mechanism for carrying data across requests; a session is **server-side context** tied to a session ID. A browser may hold cookies unrelated to login (language, theme, shopping cart), and a server may create a session for an unauthenticated user (for example, to store a saved request or a CSRF token). Therefore:

**Having a `JSESSIONID` cookie does not mean the user is logged in.** You must check whether the corresponding session holds a valid `Authentication`.

Conversely, an application can authenticate using a bearer token without using a session cookie; thus **being logged in does not necessarily mean having a `JSESSIONID`**.

## 4. Step by Step: How a Browser Logs In and Is "Remembered" on Subsequent Requests

Suppose a user opens `https://app.example.test/account`, and the application uses form login and sessions.

### Step 1 — First request without an identity

~~~http
GET /account HTTP/1.1
Host: app.example.test
~~~

The server requires authentication, so it typically returns a redirect to the login page:

~~~http
HTTP/1.1 302 Found
Location: /login
~~~

The application may create a session **even before login succeeds**, for example to store the requested URL or the CSRF token. Receiving `Set-Cookie` at this point does not prove the user is logged in.

### Step 2 — The user enters credentials

The browser receives the login form and submits the username, password, and the CSRF token issued by the application:

~~~http
POST /login HTTP/1.1
Host: app.example.test
Content-Type: application/x-www-form-urlencoded
Cookie: JSESSIONID=prelogin_id

username=alice&password=example-password&_csrf=example-csrf-token
~~~

This is **illustrative HTTP; do not use real tokens/passwords**. Spring Security passes the credentials to the appropriate authentication mechanism (such as `AuthenticationManager` and `UserDetailsService`), verifies them successfully, and creates an `Authentication`.

### Step 3 — Associating authentication with the session

In a session-based configuration, the server persists the `SecurityContext` via a `SecurityContextRepository`; session-related data is stored/looked up by session ID.

After authentication, Spring Security applies **session fixation protection**, which typically changes the session ID. The server sends an updated cookie:

~~~http
HTTP/1.1 302 Found
Location: /account
Set-Cookie: JSESSIONID=postlogin_id; Path=/; HttpOnly; Secure; SameSite=Lax
~~~

The cookie above is an **example of a securely configured HTTPS deployment**, not a guarantee that every default environment emits these exact four attributes. Cookie name, path, `Secure`, and `SameSite` depend on the container, reverse proxy, and configuration.

### Step 4 — Subsequent request carrying the same session ID

~~~http
GET /account HTTP/1.1
Host: app.example.test
Cookie: JSESSIONID=postlogin_id
~~~

The browser sends the cookie according to cookie rules; the server:

1. Extracts the session ID from the request.
2. Looks up the corresponding session in the session store.
3. Restores the `SecurityContext`/`Authentication`.
4. Checks whether the user has sufficient permissions to access `/account`.
5. Returns the data or an appropriate error.
6. Completes the request and clears the security context bound to the processing thread per framework mechanics.

The user feels like they are **still logged in**, but in reality their identity has been **restored for each request**, rather than HTTP remembering it automatically.

### Step 5 — Logout or expiration

Upon a valid logout, the server can invalidate the session, clear the `SecurityContext`, and instruct the browser to discard the cookie. When a session times out, the server record is no longer valid even though the browser may still retain the old cookie. The next request must log in again.

Overall diagram:

~~~text
Browser                     Spring Security                   Session Store
  | GET /private                    |                                |
  |-------------------------------->|                                |
  | 302 /login                      |                                |
  |<--------------------------------|                                |
  | GET /login + form/CSRF          |------ (optional session) ------>|
  |<--------------------------------|                                |
  | POST /login credentials+CSRF    |                                |
  |-------------------------------->| verify password                |
  |                                 | store SecurityContext -------->|
  | 302 + Set-Cookie: JSESSIONID    |                                |
  |<--------------------------------|                                |
  | GET /private + Cookie           |                                |
  |-------------------------------->| lookup session ---------------->|
  |                                 |<-------- SecurityContext -------|
  | 200 protected content           | authorize                      |
  |<--------------------------------|                                |
  | POST /logout + CSRF + Cookie    |                                |
  |-------------------------------->| invalidate session ----------->|
  | 302 login/logout success        |                                |
  |<--------------------------------|                                |
~~~

This is a high-level flow diagram and does not represent the exact filters/redirects/responses in every version of Spring Security.

## 5. Understanding Set-Cookie and Cookie at the HTTP Level

### Set-Cookie: the server asks the browser to store a cookie

~~~http
Set-Cookie: JSESSIONID=opaque-value; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

- **`JSESSIONID=opaque-value`:** name and value. The value is a **bearer credential**; anyone who captures a still-valid ID faces the risk of hijacking the session.
- **`Path=/`:** URL path scope used by the browser to decide whether to send the cookie. Path is not a strong security boundary between applications on the same origin.
- **`Secure`:** the browser only sends the cookie over a secure connection (with some differences/exceptions when running on localhost). Production should use end-to-end HTTPS.
- **`HttpOnly`:** page JavaScript cannot read the cookie via `document.cookie`. It mitigates one type of session theft risk from XSS, though it does not make an application immune to XSS.
- **`SameSite=Lax`:** restricts certain cross-site cookie-sending scenarios, helping defend against CSRF. `SameSite` does not replace CSRF tokens in all contexts.

Other attributes:

- **`Domain`:** if omitted, the cookie is typically host-only; avoid broadening it to subdomains unnecessarily.
- **`Max-Age` and `Expires`:** control browser-side cookie lifetime. They are not the server-side session timeout policy.
- **`SameSite=Strict`:** stricter restriction, though it can cause unexpected navigation experiences when arriving from external sites.
- **`SameSite=None; Secure`:** required for certain genuinely cross-site use cases; requires evaluating CSRF and browser policies.
- **`__Host-` prefix:** enforces name/`Secure`/`Path=/`/no `Domain` rules to support stricter host-only cookies; renaming the session cookie requires compatible infrastructure configuration.

### Cookie: the browser automatically sends it back in requests

~~~http
Cookie: JSESSIONID=opaque-value
~~~

A browser can store multiple cookies for a site. When a request matches cookie policies, it sends the corresponding cookies; JavaScript **does not have to** attach this header manually. Because cookies are typically sent automatically, session-based applications must pay attention to CSRF.

**Security note:** Any HTTP header/cookie sent by a client can be customized by the client during testing. The server must never trust any cookie value as "this user ID is real" without looking up the proper session store and verifying the corresponding state.

## 6. Why Doesn't HTTP Bind Sessions to IP or TCP Connections by Default?

A common wrong intuition is "the server sees the same connection, so it knows it's the same user."

In reality:

- A browser can send multiple requests over multiple connections; HTTP/2 allows multiplexing, but connection reuse is not a login identification standard.
- A reverse proxy can pool/split connections; different users can traverse the same proxy/IP.
- Mobile users can switch networks, IPs, devices, or open private sessions.
- A single browser can use multiple accounts in different profiles despite sharing the same IP.
- Requests routed through a load balancer can land on different server instances.

A cookie session ID solves request identification within policy boundaries, while the session store handles restoring server-side data. Never substitute IP, user agent, or request timing for it.

## 7. What Is Servlet's HttpSession?

In the Servlet API, `jakarta.servlet.http.HttpSession` represents the server-side session. Key methods to know:

| API | Meaning | Notes |
| --- | --- | --- |
| `request.getSession()` | Gets the existing session or **creates a new one** if none exists | Can accidentally create a session |
| `request.getSession(false)` | Gets the existing session, or returns `null` | Suitable when only checking without creating one |
| `session.getId()` | Gets the session identifier | Do not log or expose in production APIs |
| `session.setAttribute(key, value)` | Stores data in the session | Avoid PII, large objects, or unnecessary objects |
| `session.getAttribute(key)` | Reads session data | Perform appropriate type/null checks |
| `session.getMaxInactiveInterval()` | Views the maximum inactive interval (seconds) | Idle timeout, not necessarily absolute lifetime |
| `session.invalidate()` | Destroys the session | Does not replace the entire Spring Security logout flow |
| `request.changeSessionId()` | Changes the current session ID | Key mechanism for preventing session fixation |

Illustrative Servlet example (controller fragment):

~~~java
@GetMapping("/debug/session-present")
public boolean sessionPresent(HttpServletRequest request) {
    return request.getSession(false) != null;
}
~~~

The snippet above requires appropriate annotations/Servlet imports and **you should not expose a debug endpoint revealing internals in production**. The main point is using `getSession(false)` when you do not want observation to create a session.

### Note that session and authentication are two different things

Creating an `HttpSession` with `request.getSession()` does not automatically authenticate a user. An unauthenticated session can store a temporary shopping cart, CSRF token, or saved request. Conversely, Spring Security does not necessarily have to use `HttpSession` if bearer tokens and stateless configuration are used.

Inside a Spring MVC request, `SecurityContextHolder` lets code access the active authentication. **It is not a persistent storage mechanism across requests.** In the standard Servlet strategy, the context is bound to the current execution (typically `ThreadLocal`); the repository/session handles persistence when needed.

## 8. How Does Spring Security Remember a Logged-In User?

Main components:

**`Authentication`** is the result of authentication, holding the principal (e.g., username), authorities (roles/permissions), and flags. Raw passwords should not be stored in the session.

**`SecurityContext`** wraps `Authentication`.

**`SecurityContextHolder`** gives the current code access to the security context. Simply setting the holder in custom code and letting the request finish **does not guarantee** it has been saved for subsequent requests.

**`SecurityContextRepository`** determines how the security context is read/saved across processing stages:

- `HttpSessionSecurityContextRepository`: associates the context with `HttpSession`.
- `RequestAttributeSecurityContextRepository`: preserves the context within the scope of a request/dispatch (e.g., error dispatch), not across-request sessions.
- `DelegatingSecurityContextRepository`: delegates to multiple repositories. This is a common pairing for session + request attributes on the Servlet stack.
- `NullSecurityContextRepository`: does not persist the context; useful when intentionally stateless.

**`SecurityContextHolderFilter`** loads the context from the repository for the request to use; in Spring Security 6+, the standard model is **explicit save**: the login mechanism or custom code must save the context via the repository if subsequent requests need to read it. Do not rely on articles from the Spring Security 5 era and assume mutating `SecurityContextHolder` will always auto-save when the response finishes.

### How does form login differ from HTTP Basic?

- **Form login + session:** the user submits credentials when logging in; upon success, the server associates the authentication with a session; the browser sends the session cookie on subsequent requests.
- **HTTP Basic:** the request sends an `Authorization: Basic ...` header. This mechanism typically re-authenticates on every request without inherently requiring the server to store a session to "remember login." Browsers may cache credentials and resend them automatically, making it feel like a session, though the mechanism differs.
- **Bearer token:** each request sends `Authorization: Bearer ...`; the server validates the token according to the system's strategy. The token may be a self-contained JWT or an opaque token requiring introspection. It is not synonymous with a servlet session.
- **Remember-me:** a separate mechanism that can re-authenticate via a long-lived cookie after a normal session expires; it should not be confused with the session ID itself.

### What if you write a custom login?

In Spring Security 6+, when authenticating manually outside the built-in authentication filters, you typically need to:

1. Authenticate credentials using `AuthenticationManager` or a trusted service.
2. Create a `SecurityContext` containing the `Authentication`.
3. Set the context in the appropriate holder.
4. **Call `SecurityContextRepository.saveContext(context, request, response)`** if persistence across requests is desired.
5. Handle session fixation, CSRF, logout, exceptions, and credential handling.

Do not skip the save step and assume sessions work automatically. The hands-on example below **uses built-in form login**, avoiding error-prone custom login filters and security mechanisms.

## 9. The Four SessionCreationPolicy Options and Understanding "Stateless" Correctly

Spring Security Servlet provides `SessionCreationPolicy`:

| Policy | Meaning in Spring Security | Common use cases |
| --- | --- | --- |
| `ALWAYS` | Always creates an `HttpSession` | Only when the application genuinely needs an eager session |
| `IF_REQUIRED` | Creates a session when needed | Traditional form login; usually the default choice |
| `NEVER` | Spring Security does not proactively create a session, but can use an existing one | When sessions are created by another part of the app |
| `STATELESS` | Spring Security neither creates a session nor uses one to obtain `SecurityContext` | APIs using bearer tokens/Basic designed to be stateless |

Configuration code (fragment inside `SecurityFilterChain`):

~~~java
http.sessionManagement(session -> session
    .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED)
);
~~~

With `STATELESS`, Spring Security will not use `HttpSession` as the source for the security context; **do not interpret this as a promise that the entire application, MVC views, or other libraries will never call `getSession()`**.

Also do not assume switching from `IF_REQUIRED` to `STATELESS` automatically enables JWT login. Those are **different mechanisms**: you need to configure authentication filters, token issuer/validator, refresh/revocation, and dedicated frontend policies.

In an application with multiple `SecurityFilterChain` beans, each chain has its own matcher and policy; verify via tests that requests enter the right chain and the policy genuinely takes effect.

## 10. Full Demo: Java 17 + Spring Boot + Session-Based Form Login

The demo builds a Spring MVC application featuring:

- `/` and `/api/public` requiring no login;
- `/api/me` requiring an authenticated user;
- `/login` page auto-generated by Spring Security;
- form login storing authentication in the session;
- `/logout` handling session invalidation through default mechanics;
- tests for two-request login, unauthenticated requests without cookies, and CSRF.

**Environment:** Java 17+, Maven 3.9+, Spring Boot **3.5.7** (corresponding Spring Security 6.5 line). Use HTTPS in production; HTTP `localhost:8080` here is for learning only.

Structure:

~~~text
session-demo/
  pom.xml
  src/main/java/com/example/sessiondemo/
    SessionDemoApplication.java
    SecurityConfig.java
    DemoController.java
  src/main/resources/
    application.properties
  src/test/java/com/example/sessiondemo/
    SessionFlowTests.java
~~~

### File pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>session-demo</artifactId>
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
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
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

### File SessionDemoApplication.java

~~~java
package com.example.sessiondemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SessionDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(SessionDemoApplication.class, args);
    }
}
~~~

### File SecurityConfig.java

~~~java
package com.example.sessiondemo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/api/public", "/error").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .logout(logout -> logout.logoutSuccessUrl("/?logout"))
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED))
            .csrf(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("demo123"))
            .roles("USER")
            .build();

        UserDetails bob = User.withUsername("bob")
            .password(encoder.encode("example456"))
            .roles("USER")
            .build();

        return new InMemoryUserDetailsManager(alice, bob);
    }
}
~~~

**Explanation:**

- `formLogin(Customizer.withDefaults())` enables the default login page/form managed by Spring Security; no need to write `POST /login` yourself.
- `SessionCreationPolicy.IF_REQUIRED` allows creating a session to maintain login when needed.
- `csrf(Customizer.withDefaults())` keeps the default CSRF mechanism for state-changing methods such as POST. **Do not disable CSRF just to make a curl POST login succeed**.
- `logoutSuccessUrl("/?logout")` takes the user back to a public page upon logout. With CSRF enabled, logout should submit **POST /logout** with a valid token; GET logout usually shows a confirmation page and is not equivalent to completing logout in every configuration.
- Demo passwords are hashed with BCrypt on application startup. `demo123`/`example456` are for localhost only; never hardcode real credentials in production.
- `/error` is permitted so application errors are not masked by an unnecessary login redirect; production should review its error response policy.
- The demo has no data-mutating API, yet still keeps CSRF enabled to practice login/logout properly.

### File DemoController.java

~~~java
package com.example.sessiondemo;

import java.util.Map;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/")
    public String home() {
        return "Welcome - open /api/me after signing in";
    }

    @GetMapping("/api/public")
    public String publicInfo() {
        return "public";
    }

    @GetMapping("/api/me")
    public Map<String, Object> me(
            Authentication authentication,
            HttpServletRequest request
    ) {
        HttpSession session = request.getSession(false);

        return Map.of(
            "username", authentication.getName(),
            "authenticated", authentication.isAuthenticated(),
            "sessionPresent", session != null
        );
    }
}
~~~

`/api/me` is protected by `anyRequest().authenticated()`. On a successful route hit, the method receives the current request's `Authentication`. `request.getSession(false)` **does not create a new session**; it merely illustrates checking whether a session exists. Do not put the session ID in the response body or logs.

### File application.properties

~~~properties
server.port=8080
server.servlet.session.timeout=20m
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.same-site=lax
~~~

`server.servlet.session.timeout=20m` configures the server-side idle timeout, not a guarantee that every cookie always disappears exactly 20 minutes after login. The `http-only` flag prevents browsers from exposing the cookie value to `document.cookie`.

**Production over HTTPS:** enable `Secure` for the session cookie (for instance, configuring appropriately with reverse proxy/TLS termination), and evaluate `Domain`/`Path`, HSTS, and the entire transport path. Since the demo runs on HTTP localhost only, **do not force `server.servlet.session.cookie.secure=true`**, which can prevent the cookie from being sent in some browsers/test environments; production environments must enforce HTTPS.

### Running

In the `session-demo` directory:

~~~bash
mvn clean test
mvn spring-boot:run
~~~

If you have Maven Wrapper from Spring Initializr:

~~~bash
./mvnw test
./mvnw spring-boot:run
~~~

On Windows PowerShell use `.\mvnw.cmd test` and `.\mvnw.cmd spring-boot:run`.

Open **`http://localhost:8080/api/me`** in an unauthenticated browser. The browser will be redirected to the login page. Sign in with:

~~~text
username: alice
password: demo123
~~~

Then reopen `http://localhost:8080/api/me`. Expected JSON body (key order is not guaranteed):

~~~json
{
  "username": "alice",
  "authenticated": true,
  "sessionPresent": true
}
~~~

This is the **expected output from the demo configuration**, not an output already executed in this document. In Spring MVC, a `Map` return type is serialized to JSON by Jackson; key order may vary.

Open a new tab in the **same browser profile** and call `/api/me`: the browser typically resends the same session cookie, so the user remains `alice`. Use a separate private/incognito window or clear cookies to test a request without a session ID: the server does not recognize the user and typically redirects to `/login`.

### Inspecting with Developer Tools

1. Open DevTools → **Network** → inspect the `/login` and `/api/me` requests.
2. In the response, look for `Set-Cookie` and its actual attributes. A cookie may be issued before login succeeds because of CSRF/saved requests; do not label every `Set-Cookie` as "logged in."
3. After login, verify that the browser sends a `Cookie` header containing the session ID to `/api/me`.
4. Observe whether the session ID changes when authentication succeeds (session fixation protection).
5. Try another browser profile: a request without the active cookie must be treated as unauthenticated.
6. Log out via the security form/screen and try calling the endpoint again. The browser might still hold the old cookie, but the invalidated session will no longer authenticate.

**Security when sharing screenshots/network logs:** Never post real session IDs, CSRF tokens, passwords, or authorization tokens to chats, public docs, or bug reports. A session ID is a credential that must be kept secret.

## 11. Programmatic Testing: Reusing the Session in a Second Request

Add `src/test/java/com/example/sessiondemo/SessionFlowTests.java`:

~~~java
package com.example.sessiondemo;

import jakarta.servlet.http.HttpSession;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SessionFlowTests {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointNeedsNoLogin() throws Exception {
        mvc.perform(get("/api/public"))
            .andExpect(status().isOk());
    }

    @Test
    void unauthenticatedRequestRedirectsToLogin() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void loginSessionAuthenticatesNextRequest() throws Exception {
        MvcResult result = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "alice")
                .param("password", "demo123"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        HttpSession rawSession = result.getRequest().getSession(false);
        assertNotNull(rawSession);

        MockHttpSession session = (MockHttpSession) rawSession;

        mvc.perform(get("/api/me").session(session))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("alice"))
            .andExpect(jsonPath("$.authenticated").value(true))
            .andExpect(jsonPath("$.sessionPresent").value(true));
    }

    @Test
    void loginDoesNotAuthenticateAnUnrelatedRequest() throws Exception {
        mvc.perform(post("/login")
                .with(csrf())
                .param("username", "alice")
                .param("password", "demo123"))
            .andExpect(status().is3xxRedirection());

        // Do not pass the session/cookie from the previous login request.
        mvc.perform(get("/api/me"))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void logoutWithoutCsrfIsRejected() throws Exception {
        mvc.perform(post("/logout"))
            .andExpect(status().isForbidden());
    }
}
~~~

Command:

~~~bash
mvn test
~~~

**Meaning of the core tests:**

- `loginSessionAuthenticatesNextRequest`: the POST login request succeeds, grabs the session from that request, and **passes the same session** to a new GET request; GET returns Alice's account.
- `loginDoesNotAuthenticateAnUnrelatedRequest`: after a login request has occurred, another request **not carrying the logged-in session** is still redirected to login.
- `logoutWithoutCsrfIsRejected`: proves that enabling CSRF is distinct from merely requiring login.

`MockMvc` simulates server-side requests, not a real browser. Passing `MockHttpSession` between requests in tests corresponds to a browser sending a session cookie so the server looks up the same session; a `MockMvc` test itself does not prove how a real browser emits `Set-Cookie`. To verify cookie attributes and proxy/HTTPS behavior, run real HTTP tests with a browser or HTTP client.

**Code QA:** This is a complete sample application with all files and dependencies for learners to run with Java 17+ and Maven. This lesson only states expected behavior from the code; it does not claim to have built/run it or observed the `BUILD SUCCESS` line without executing it.

## 12. A Plain Java Simulation to Distinguish Request and Session

If Spring is not installed yet, the following Java 17 program simulates session logic using a `Map`. This is **not an HTTP server and does not generate secure session IDs**, just a small model to observe why requests need a linking identifier.

Create `TinySessionSimulation.java`:

~~~java
import java.util.HashMap;
import java.util.Map;

public class TinySessionSimulation {
    private static final Map<String, String> SESSIONS = new HashMap<>();

    private static String handle(String sessionId) {
        if (sessionId == null) {
            return "anonymous";
        }
        return SESSIONS.getOrDefault(sessionId, "anonymous");
    }

    public static void main(String[] args) {
        System.out.println(handle(null));

        // Simulate the server creating a session for Alice upon login.
        String demoId = "demo-only-not-random";
        SESSIONS.put(demoId, "alice");

        System.out.println(handle(demoId));
        System.out.println(handle(null));

        // Simulate logout: the old session ID no longer maps to Alice.
        SESSIONS.remove(demoId);
        System.out.println(handle(demoId));
    }
}
~~~

Run:

~~~bash
javac TinySessionSimulation.java
java TinySessionSimulation
~~~

Exact stdout:

~~~text
anonymous
alice
anonymous
anonymous
~~~

Explanation:

- First line: request without a session ID ⇒ anonymous.
- Second line: request with an ID mapped to Alice ⇒ restores Alice's name.
- Third line: a new request without an ID ⇒ still anonymous even though Alice's session exists.
- Fourth line: the old ID was removed from the map ⇒ anonymous.

In real production code, do not write a global unsynchronized `HashMap` session store, and do not use predictable IDs like `demo-only-not-random`. Use proven session handling from your Servlet container/Spring Security/Spring Session.

## 13. Cookie Expiration and Session Expiration Are Not the Same Clock

There are at least three distinct timeframes:

1. **Browser cookie lifetime:** a session cookie without `Max-Age`/`Expires` is typically treated as a browser session cookie, though some browsers have a *restore session* feature that keeps cookies alive longer than you might expect.
2. **Server session idle timeout:** for example, 20 minutes without a request counted as activity; upon expiration, the server invalidates/removes the session. Idle time is managed by the container/session store and refreshed according to its own rules.
3. **Absolute login lifetime/security policy:** a system may force re-login after an overall deadline even if the user remains active; this policy must be explicitly designed and does not come automatically from setting an idle timeout.

Illustrative example:

~~~text
10:00 login -> session valid
10:08 /api/me -> session is used
10:15 /api/me -> still valid
10:36 next request -> may have timed out if idle timeout=20m,
                       because from 10:15 to 10:36 is 21 minutes
~~~

This example is only to convey the idea, not a guarantee of the exact sweep/cleanup timing of every container or session infrastructure.

When a browser deletes a cookie, the server session may still exist until timeout if not invalidated. When the server invalidates a session, the browser may still send the old cookie, but it is no longer treated as a logged-in session. **Server-side logout** and **browser-side cookie deletion** should be coordinated properly, rather than doing only one.

## 14. Session Fixation: Why Should the Session ID Change After Login?

Suppose an attacker knows or forces a victim to use a specific session ID **before the victim logs in**. If the ID does not change upon login, the attacker can use that ID to access the subsequently authenticated session. This is **session fixation**.

To mitigate this risk, Spring Security supports session fixation protection; on modern Servlets, the `changeSessionId` strategy is typically the default. This ensures:

- Pre-login and post-login sessions do not share an old identifier that could continue to be reused as a credential.
- The browser is issued a new cookie after authentication succeeds.
- The user does not need to take any action beyond logging in.

Do not disable session fixation protection. Avoid configurations that put the session ID in the query string such as `/page;jsessionid=...` or `?sessionId=...`, because URLs can leak via browser history, Referer headers, logs, or shared links. Cookies sent over HTTPS are the standard approach.

**Session hijacking vs. session fixation:** hijacking occurs when an active session ID is stolen/compromised. Fixation tries to force a user to use an ID already known to the attacker. Fixation protection does not replace HTTPS, XSS mitigation, and cookie protection.

## 15. CSRF: The Flip Side of Automatically Sent Cookies

Because browsers automatically attach cookies on matching requests, another website can cause a user's browser to send a request to an application where the user is logged in. If that request performs a side effect (transferring money, deleting data, changing an address), the server risks executing it **simply because it sees a valid session cookie**.

That is why CSRF protection is important with session/cookie authentication.

Spring Security protects unsafe HTTP methods such as POST/PUT/PATCH/DELETE by default using a CSRF token; the token must be sent in a way another site cannot arbitrarily forge validly. The default login form includes a hidden `_csrf` input. A POST request lacking a valid token may receive **403** even if the user is logged in.

Form example (illustrative, token issued by Spring Security):

~~~html
<form method="post" action="/transfer">
  <input name="destination" value="account-2">
  <input type="hidden" name="_csrf" value="issued-csrf-token">
  <button type="submit">Transfer</button>
</form>
~~~

This is **not a complete money transfer implementation**, only an illustration of where the token goes in a request. For JSON SPAs, the token can be sent via headers like `X-CSRF-TOKEN`/`X-XSRF-TOKEN` depending on the repository/handler configuration. Spring Security 6 features deferred tokens and BREACH protection; do not blindly copy outdated advice like "reading any cookie and sending it back is always enough."

**SameSite helps reduce risk, but does not replace CSRF tokens in all scenarios.** You must consider same-site subdomains, top-level navigations, legacy browsers, and application-specific policies. HTTP `GET` must be semantically read-only; do not perform mutations over GET and hope SameSite will protect it.

## 16. Comparing Session-Based and Stateless Token Authentication

| Criterion | Session-based (cookie session ID) | Bearer token / JWT API |
| --- | --- | --- |
| Per-request data | Browser sends session cookie | Client sends token (usually in `Authorization`) |
| Proof of authentication | Server looks up valid session/context | Server validates bearer token or introspects opaque token |
| Server state for login | Usually has a session store | May have no server session, yet still have revocation/cache/other stores |
| Immediate logout | Can invalidate session on the server | Depends on token lifetime, revocation/refresh-token design |
| Risks | Session hijacking, fixation, CSRF when cookies auto-send | Token theft/replay, refresh-token security; CSRF depends on storage/sending |
| Browser experience | Cookies auto-sent per policy | Client usually must explicitly attach bearer header |
| Scaling | Needs shared session store or appropriate routing | Can reduce session state, but is not free in security/operations |

**JWT is not inherently safer than sessions.** JWTs can be stolen, have lifetimes, require signature/issuer/audience verification, and pose revocation/refresh challenges. If a JWT is stored in an auto-sent cookie, CSRF still needs to be evaluated. If stored in `localStorage`, there is no `HttpOnly` protection and you face the risk of XSS stealing the token. The choice depends on your threat model and architecture.

In systems using OAuth2/OIDC, logging in to the identity provider and the application's session state can also be two distinct concepts. Do not conflate the browser's app session with the access token used to call resource servers or the session at the identity provider.

## 17. Common Mistakes

| Wrong claim or misconfiguration | Actual issue | Proper understanding / fix |
| --- | --- | --- |
| "HTTP keeps login after POST /login" | HTTP does not automatically carry identity across requests | Session/cookie or token is sent back |
| "A cookie is the server session" | Cookies live on the client; session state usually lives on the server | Distinguish identifier from server-side record |
| "Having JSESSIONID means logged in" | A session can exist before authentication | Check `Authentication` and policies |
| "Same IP ⇒ same account" | IP is not identity | Use valid credentials/session/token |
| "HTTP/2 keeps the TCP connection so it keeps login" | Connection reuse is not app auth state | Separate transport from identity |
| "Just call getSession() to read the session" | Can accidentally create a session | Use `getSession(false)` when only reading |
| "SecurityContextHolder lives forever" | Context is scoped to request/thread processing, not a persistence store | Use the appropriate `SecurityContextRepository` |
| "Custom login setContext is enough" | Explicit-save flows may not persist it | Use `saveContext(...)` and proper session strategy |
| "Basic Auth has no JSESSIONID so it's broken" | Basic sends credentials per request | Distinguish authentication mechanisms |
| "STATELESS stops the entire app from creating sessions" | Policy mainly controls Spring Security context/session | Check MVC/container/libraries as well |
| "Cookie lives 30 days so server session lives 30 days" | Cookie TTL differs from server idle timeout | Design each timeout separately |
| "Deleting the cookie logs out the server immediately" | Server session may still exist | Invalidate session, clear context, and expire cookie appropriately |
| "Disable CSRF on form login for easier testing" | Opens up CSRF vulnerabilities | Use CSRF tokens properly |
| "SameSite completely replaces CSRF" | Coverage is insufficient across all models | Defense in depth + CSRF token |
| "HttpOnly eliminates all XSS" | JS can still execute actions inside the victim's page | XSS prevention, CSP, output encoding, authz |
| "Secure cookies are sent over all HTTP" | Secure is designed for HTTPS; localhost has exceptions | HTTPS in production, test real deployments |
| "Session ID in URL is convenient for sharing" | ID can leak via history/logs/referrer | Secure cookies, no URL rewriting |
| "Any load balancer sees sessions automatically" | In-memory sessions may exist on only 1 instance | Spring Session/shared store or intentional strategy |
| "Put role in a cookie and trust its value" | Client can tamper with values | Trust only signed/verified state or server-side store |
| "JWT is a session just like JSESSIONID" | Tokens have different semantics from server sessions | Design persistence/revocation separately |

## 18. Using Sessions in Multi-Server Systems

In an application running a single Servlet server instance, sessions can live in JVM memory. However, when deployed across multiple instances:

~~~text
Browser -- Cookie: JSESSIONID=abc
    |
Load Balancer
    +--> Instance A --> local session store has abc
    |
    +--> Instance B --> local session store does not have abc
~~~

If request 1 hits A and request 2 hits B without shared sessions, the user may hit errors or appear logged out. Approaches to handle this:

- **Shared session store:** use Spring Session (Redis/JDBC or an appropriate backend) so multiple instances read the same session; requires TTL and store security.
- **Sticky sessions:** load balancer pins routing per client; simpler in some environments but less resilient when instances die or scale, requires evaluation.
- **Stateless authentication:** if suited to an API model, use bearer tokens validated on every request; still requires protecting tokens and solving revocation.

Do not store overly large session objects or non-serializable data if the session backend requires serialization. Minimize sensitive data and avoid storing entire entity graphs, passwords, or unnecessary long-lived tokens. Sessions may be read/updated at high frequency, so account for network cost, TTL, caching, and concurrency.

## 19. Troubleshooting Checklist for "Logged In, Then Immediately Kicked Out"

Check in order:

1. **Does the post-login request send the Cookie?** Use DevTools Network to inspect domain/path/SameSite/Secure, cross-subdomain redirects, and browser privacy restrictions.
2. **Does the session ID change on login?** That may be session fixation protection; if rotated properly, the browser must update it.
3. **Does the server session still exist?** Check timeouts, restarts, invalidation, eviction, session store availability, and related clock/time skew.
4. **Are there multiple app instances?** Test sticky routing or shared stores, without logging raw session IDs.
5. **Are you using `STATELESS` or `NullSecurityContextRepository`?** If expecting session-based login while configured stateless, subsequent requests may fail to restore authentication.
6. **Did custom login save `SecurityContext`?** In Spring Security 6+, you must save via the right repository when persistence is desired.
7. **Is a reverse proxy accidentally altering session IDs/cookies?** Check HTTPS termination, forwarded headers, cookie rewriting, and path mapping.
8. **Is POST returning 403 after login?** Distinguish missing permissions from a missing/expired CSRF token; GET still working is a strong clue to check.
9. **Are you still logged in when opening another browser profile?** If not, that is expected behavior since cookies are not shared.
10. **Does logout invalidate the server session?** Inspect handler/CSRF behavior and the session store rather than looking only at the UI.

Do not include passwords or full session IDs in logs or error reports. If correlation is needed, use a request ID and a securely designed token/session hash, never the session credential itself.

## 20. Hands-On Exercises

**Exercise 1 – Two requests.** A browser calls `GET /private` twice without cookies or authentication headers. Does HTTP force the server to know it is the same user? Explain why IP or an HTTP/2 connection is not enough.

**Exercise 2 – Distinguishing values.** In `Set-Cookie: JSESSIONID=abc; HttpOnly; Secure`, which part is the identifier and where is the session data holding username/authorities? Why can't you edit `abc` to `username=admin` and expect admin privileges?

**Exercise 3 – Observing before login.** You see `JSESSIONID` appear as soon as you open `GET /login` before logging in. Is this definitely a bug? Name at least two reasons the framework may create a session prior to authentication.

**Exercise 4 – New browser.** After Alice logs in in a regular window, a private window opens `/api/me` and gets redirected to `/login`. Explain based on the cookie jar.

**Exercise 5 – Timeout.** A cookie still exists after the server session has timed out. How must the next request be handled so the wrong user is not authenticated? Why must cookie TTL and session idle timeout be configured/tested separately?

**Exercise 6 – Session hijacking.** If an attacker steals an active session ID, what mechanisms help reduce the risk? Distinguish session fixation, CSRF, XSS, and cookie `Secure`/`HttpOnly`/`SameSite`.

**Exercise 7 – Stateless API.** You configured `SessionCreationPolicy.STATELESS`, yet notice the application still creates an `HttpSession` because your code calls `getSession()`. Does this completely contradict the policy's meaning? How would you fix the design if server sessions are not needed?

**Exercise 8 – Custom login.** In Spring Security 6, a custom controller authenticates successfully and only calls `SecurityContextHolder.setContext(...)`. After redirecting to a new request, the user is treated as anonymous again. Which component should you check?

**Exercise 9 – CSRF.** Why can a POST request with a valid login cookie still receive 403? Should you disable CSRF when an application uses session cookies?

**Exercise 10 – Experiment.** Run the demo, log in as Alice, read `/api/me`, open a separate profile, and log out. Record which requests have `Set-Cookie`, which have `Cookie`, and explain why "the browser automatically sends cookies" makes the login experience seamless.

### Suggested Answers

1. No. Requests do not automatically inherit authentication; IP/connection is not a reliable identity.
2. `abc` is the client-side session ID; the server looks up the session store and checks `Authentication`.
3. It may be storing a saved request or a CSRF token before login.
4. A different browser profile does not hold the corresponding session cookie.
5. The old session ID must be treated as invalid and re-authentication required; cookies and sessions have separate lifecycles.
6. HTTPS, cookie flags, rotation upon login, CSRF protection, XSS mitigation, timeouts, logout invalidation, scope restriction, and anomaly detection.
7. Not necessarily a contradiction: the policy does not guarantee that all library/application code avoids creating sessions; remove unnecessary session creation and use a bearer mechanism if intentionally stateless.
8. Check `SecurityContextRepository.saveContext(...)` and the session/authentication flow, not just the holder.
9. Because the CSRF token is missing/wrong or has timed out; with cookie-based browser login, keep CSRF enabled and submit valid tokens.
10. Observations will show the session ID being carried with requests; the server restores authentication from server-side state, rather than HTTP remembering it automatically.

## 21. Summary

**A session** is how an application maintains logical context across multiple HTTP requests. Because HTTP does not natively retain login state, the browser and server must coordinate using an additional protocol: the server creates/stores a session, the browser holds the session ID (typically via a cookie), and each subsequent request sends the ID so the server can look up and restore `SecurityContext`.

Key takeaways to remember:

1. **HTTP stateless ≠ the application cannot have state.** State requires an explicit linking mechanism such as cookie/session or token.
2. **Cookie ≠ session ≠ authentication.** A cookie carries an ID; a server-side session can hold context; `Authentication` is the identity/authorities processed by Spring Security.
3. **A session cookie is a credential.** Protect it with HTTPS, appropriate `Secure`, `HttpOnly`, `SameSite`, XSS/CSRF defenses, rotation, and logout.
4. **Spring Security does not "remember" via the holder alone.** Persistence depends on `SecurityContextRepository` and the authentication flow; custom login requires explicit saving when needed.
5. **One login session can span multiple requests, but every request must still be checked.** If the cookie is missing, expired, invalidated, or rejected by policy, the request is not considered authenticated.
6. **Do not confuse session timeout, cookie lifetime, and token expiration.** These are distinct policies that must be designed and tested independently.

### Official Documentation

- [Spring Security – Persisting Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/persistence.html)
- [Spring Security – Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html)
- [Spring Security – Form Login](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/form.html)
- [Spring Security – Logout](https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html)
- [Spring Security – CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Spring Boot 3.5 – Servlet Session/Cookie Properties](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html)
- [MDN – Using HTTP Cookies](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Cookies)
- [MDN – Secure Cookie Configuration](https://developer.mozilla.org/en-US/docs/Web/Security/Practical_implementation_guides/Cookies)
