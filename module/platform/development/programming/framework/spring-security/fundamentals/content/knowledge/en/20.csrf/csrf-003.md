# CSRF Tokens and How Servers Validate State-Changing Requests

## 1. What Problem Does a CSRF Token Solve?

**Cross-Site Request Forgery (CSRF)** occurs when an untrusted website causes a user's browser to send a request to another application while the browser may **automatically attach credentials** trusted by the target application: for example, session cookies, certain authentication cookies, or HTTP Basic credentials cached by the browser.

Suppose a user is logged into **https://bank.example**, which provides a money transfer function via POST. While the user's login session is active, a malicious page on a different origin tries to make the browser send a POST to the bank. If the server checks only the session cookie, the request may be interpreted as an action of the account owner, even though the account owner never intended to perform the transaction.

A **CSRF token** is a hard-to-guess value used by the server or a related trusted mechanism to prove that a state-changing request originated from a legitimate application/client, rather than merely carrying an auto-attached cookie. Under the **synchronizer token pattern**, the server stores an **expected token** bound to the appropriate state, while the legitimate page/form obtains the token and must actively submit it back in a **form field** or **HTTP header**. A page on another origin normally cannot read the token from the target application due to Same-Origin Policy restrictions and endpoint design.

~~~text
Logged-in browser
       |
       +--> Legitimate request from application page
       |      Session cookie + CSRF token in header/form
       |      -> Server checks token -> runs business logic
       |
       +--> Forged request from external page
              Session cookie may be sent automatically
              But lacks valid token
              -> Server rejects before controller
~~~

**Checking only the CSRF token is not enough for authentication or authorization.** A POST request with a valid token must still undergo Authentication, GrantedAuthority, ownership/tenant, input validation, and business rule checks. Conversely, being logged in or having sufficient roles does not mean CSRF can be skipped.

### Lesson Objectives

After this lesson, you can:
1. Describe where a CSRF token is generated, stored, exposed to forms/clients, sent back, and verified.
2. Explain Spring Security's **CsrfFilter**, **CsrfTokenRepository**, **CsrfTokenRequestHandler**, as well as **MissingCsrfTokenException / InvalidCsrfTokenException**.
3. Distinguish methods that normally **do not require** CSRF from methods that **must be protected** by default.
4. Integrate CSRF tokens with form login, AJAX/JSON requests, and JavaScript applications.
5. Run a Spring Boot 3.x / Spring Security 6.x / Java 17+ example with a counter-increment endpoint, observing missing/invalid tokens blocked with no data change.
6. Write MockMvc tests to verify both valid and rejected cases.
7. Avoid confusing CSRF with CORS, XSS, SameSite cookies, or Bearer tokens.

> Example scope: **Spring MVC/Servlet**. WebFlux has different filters and reactive APIs. Examples use session-cookie credentials so CSRF risk is clearly visible, rather than recommending disabling CSRF for all APIs.

## 2. Nature of the Attack and Necessary Conditions

A CSRF scenario involves these elements:

- **Victim** already holds a credential that the browser can automatically attach when sending requests to the target application.
- **Attacker** controls or lures the victim to a page, link, form, or content capable of issuing an unwanted request.
- **Target application** has an endpoint that mutates data/state or causes sensitive consequences.
- **Server** accepts the request based solely on auto-sent credentials without additional checks distinguishing client intent.

Example of a cross-origin form that a browser might submit, **solely to illustrate risk**, not a valid request in the demo:

~~~html
<form method="post" action="https://bank.example/transfer">
    <input type="hidden" name="to" value="attacker-account">
    <input type="hidden" name="amount" value="1000">
    <button type="submit">Send</button>
</form>
~~~

Depending on the cookie's **SameSite** policy, request type, browser, and how the application accepts data, credentials may or may not be sent. Do not assume "browsers always send every cookie"; verify cookie policies in real environments. However, **do not rely on SameSite as the sole replacement for CSRF tokens** when the app uses auto-sent browser credentials and sensitive endpoints.

Notably, the attacker **does not necessarily need to read the API response** to cause harm. CORS/Same-Origin Policy limits reading responses or sending certain cross-origin requests, but if the action executes because the server fails to check CSRF properly, being unable to read the response does not undo the action.

### CSRF vs. XSS

| Aspect | CSRF | XSS |
| --- | --- | --- |
| Idea | Causes victim's browser to send an unwanted action to a logged-in app | Injects/runs untrusted JavaScript inside the application's origin |
| What attacker exploits | Credentials auto-attached to requests | Script execution privileges in the same origin, DOM, accessible data |
| Mitigation | CSRF tokens, SameSite, proper Origin/Referer checks, API design | Escaping/output encoding, CSP, context-aware sanitization, avoiding DOM sinks |
| Relationship | CSRF tokens help stop many cross-site forged requests | **XSS can invalidate many CSRF assumptions**, as same-origin scripts can extract or submit tokens |

**CSRF tokens do not cure XSS.** Conversely, solid XSS defense does not guarantee the application handles all CSRF scenarios properly.

## 3. What Characteristics Should a CSRF Token Have?

With the synchronizer token pattern, key properties typically include:

1. **Unpredictable**: generated from a suitable cryptographic random source with sufficient entropy, not formed by concatenating timestamps/usernames as a secret.
2. **Trusted expected source**: the server loads the value from a repository bound to the proper context; never trust a client-proposed value as the expected token.
3. **Not auto-sent just because the browser has an auth cookie**: the client must obtain the token from readable app content/endpoints and actively include it in a header or form field.
4. **Verified before data mutation**: invalid or missing tokens must stop business handlers from running.
5. **Reasonable lifecycle**: tokens may be rotated/cleared upon login, logout, session expiration, or security needs. Clients must have a way to obtain new tokens.
6. **Not exposed in URLs**: query strings can appear in browser history, server logs, `Referer`, or monitoring tools. Use headers or form bodies instead.

A token is not a user password, not a session identifier, and **does not represent ADMIN/USER roles**. It proves a request-validity condition within anti-CSRF defense. A valid token **cannot substitute** for Authentication or Authorization.

### Why Is a Session Cookie Not Enough?

If the browser auto-sends the `JSESSIONID` cookie on a request matching cookie policies, the server can locate the victim's `HttpSession`. That is the role of a session cookie—not proof that the user clicked a button on the bank page. A CSRF token must come from a source an attacker page normally **cannot read and supply** in requests. That is the critical difference between auto-sent cookies and form/header tokens actively supplied by the client.

## 4. At Which Layer Does Spring Security Handle CSRF?

In **Spring Security Servlet**, the primary component is **CsrfFilter**. `CsrfFilter` is a filter inside the Spring Security filter chain; it checks requests requiring CSRF protection **before the controller runs business logic**.

High-level diagram:

~~~text
HTTP request
   |
   v
SecurityFilterChain / CsrfFilter
   |
   +--> CsrfTokenRepository
   |       +--> Find/create expected token (may be deferred)
   |
   +--> CsrfTokenRequestHandler
   |       +--> Expose request token to application
   |       +--> Read client-submitted token from header/parameter
   |
   +--> RequestMatcher: does this method need CSRF?
            |
            +--> NO (GET/HEAD/OPTIONS/TRACE by default)
            |       -> continue down filter chain
            |
            +--> YES (POST/PUT/PATCH/DELETE...)
                    |
                    +--> Load expected token from repository
                    +--> Read actual token from request
                    +--> Compare via request handler
                              |
                              +--> Match -> continue filter chain
                              |            -> authorization -> controller
                              |
                              +--> Missing/mismatch -> AccessDeniedHandler
                                               -> typically HTTP 403
                                               -> controller does not run
~~~

### 4.1. Responsibility of Each Component

| Component | Function | Note |
| --- | --- | --- |
| **CsrfFilter** | Selects requests needing CSRF and checks actual token vs. expected token | Can block POST before reaching controller |
| **CsrfToken** | Object holding header name, parameter name, and token string | E.g., parameter **_csrf**, header **X-CSRF-TOKEN** |
| **CsrfTokenRepository** | Generates, stores, loads, or clears expected tokens | Defaults to **HttpSessionCsrfTokenRepository** |
| **DeferredCsrfToken** | Defers loading/generating the token until needed | Avoids unnecessary session access on many requests |
| **CsrfTokenRequestHandler** | Makes token available to app and reads actual token from request | Spring Security 6 defaults to XOR request handler for BREACH protection |
| **AccessDeniedHandler** | Determines response on rejection | Typically 403 for missing/invalid CSRF tokens |

**Do not rewrite token comparison inside controllers** when `CsrfFilter` is already active, unless architecture demands something special and has undergone full security analysis. With defaults, the filter verifies the token before business handlers.

### 4.2. Important Execution Order

In Spring Security 6, `CsrfFilter` typically:
1. Retrieves a **DeferredCsrfToken** linked to the repository.
2. Passes the token supplier to **CsrfTokenRequestHandler**, enabling controllers/templates to access the token.
3. Checks whether the request method requires CSRF protection.
4. If not required, continues down the filter chain; need not eagerly load session/token yet.
5. If required, loads the expected token from the repository.
6. Reads the client-provided token from header or request parameter via the handler.
7. Validates and proceeds, or invokes `AccessDeniedException` handling if missing/invalid.

Thus, **GET /csrf** triggers loading/generating the token when the controller actually calls `CsrfToken.getToken()`; whereas another public GET does not automatically force session/token creation merely because `CsrfFilter` is present.

### 4.3. MissingCsrfTokenException and InvalidCsrfTokenException

Per Spring Security's API:
- **MissingCsrfTokenException** indicates that the expected token is missing when verification is required.
- **InvalidCsrfTokenException** occurs when an expected token exists, yet the actual token is missing or does not match.

Do not build dashboards assuming every headerless request produces one immutable exception type. Cases vary by repository, session, request handler, and token lifecycle. To the client, both usually surface as **403**, while security logs distinguish the underlying cause.

## 5. Which HTTP Methods Require CSRF?

By default, Spring Security Servlet treats the following as **safe methods** regarding CSRF:

- **GET**
- **HEAD**
- **OPTIONS**
- **TRACE**

Other methods, such as **POST, PUT, PATCH, DELETE**, are considered subject to CSRF checks under the default matcher. This is a **security convention** built on the assumption that the application truly adheres to HTTP semantics.

| Request | CSRF by default? | What to avoid |
| --- | --- | --- |
| GET /products | No | Do not mutate data on GET |
| HEAD /products | No | Do not trigger secondary transactions as side effects |
| OPTIONS /products | No | CORS/preflight is not authorization to POST |
| POST /orders | Yes | Do not rely solely on session cookies |
| PUT /profile | Yes | Do not allow updates without a token |
| PATCH /settings | Yes | Do not allow updates without a token |
| DELETE /documents/42 | Yes | Do not allow deletions without a token |

**Never build an endpoint like GET /delete-account to delete an account** and expect `CsrfFilter` to protect it. GET does not check CSRF by default; a browser-loaded link or image can trigger a GET. Put state-changing actions on proper methods and apply authorization/CSRF.

CSRF protection also **does not guarantee every POST is valid business-wise**; it only eliminates one class of illegitimate requests. The server must still enforce permissions, resource limits, and validation.

### What About HTTP Method Override?

If the application supports converting **POST + _method=DELETE** via a filter or another framework, check filter ordering and ensure CSRF protection covers the request before DELETE logic can execute. Never allow a method-override shortcut to bypass protection layers. Test in practice because filter registration/ordering varies across applications.

## 6. CsrfTokenRepository: Where Is the Expected Token Stored?

### 6.1. HttpSessionCsrfTokenRepository (Default)

Spring Security Servlet commonly uses **HttpSessionCsrfTokenRepository**:

~~~text
Browser                         Server
    | GET /csrf
    |--------------------------->
    |                            Generate/load expected CSRF token
    |                            Store in HttpSession (when needed)
    |<---------------------------
    | JSON containing token and matching session cookie
    |
    | POST /api/counter/increment
    | Cookie: JSESSIONID=...
    | X-CSRF-TOKEN: <token>
    |--------------------------->
    |                            Look up session via cookie
    |                            Fetch expected token
    |                            Read actual token from header
    |                            Compare -> valid?
    |<---------------------------
    | 200 if valid and authorized
~~~

A token from session A must not be treated as valid for session B just because both sessions share a username. **A token retrieved from one session must not validate requests for another independent session**.

When a session expires or is invalidated, the expected token tied to that session also ceases to exist in that scope. Long-open forms may submit stale tokens and receive 403; the app should provide UX to fetch a fresh token without accidentally re-executing sensitive actions.

### 6.2. CookieCsrfTokenRepository

Spring Security also supports **CookieCsrfTokenRepository**. This stores the expected token in a cookie, commonly following the **double-submit cookie** model where the client sends a matching token via header.

Differences:
- Session repositories store expected tokens server-side in `HttpSession`.
- Cookie repositories can avoid relying on sessions for storing expected tokens, but require careful design of cookie/header creation, transmission, and verification.
- **Authentication cookies** and **CSRF cookies** serve different purposes. Never treat the presence of a CSRF cookie as proof that a user is logged in.
- Allowing JavaScript to read the CSRF cookie (e.g., `withHttpOnlyFalse`) is a deliberate tradeoff; session/auth cookies should keep `HttpOnly`.
- Double-submit requires assessing cookie injection, domain/path, SameSite, HTTPS, origin, and integrity; never use a cookie an attacker can easily overwrite as a trusted token.

### 6.3. Do Not Switch to CookieCsrfTokenRepository Without Understanding SPAs

In Spring Security 6.x, **XorCsrfTokenRequestAttributeHandler** provides **BREACH protection** by default by adding randomness to the token presented to the client. Headers read directly from a **cookie containing the raw token** may require an **SPA request handler** to resolve the token properly. Hence, simply changing:

~~~java
http.csrf(csrf ->
    csrf.csrfTokenRepository(
        CookieCsrfTokenRepository.withHttpOnlyFalse()));
~~~

is a **configuration fragment**, not necessarily a complete SPA integration in Spring Security 6. Follow the official SPA guidance (including appropriate decrypting/delegating request handlers and token refreshes after login/logout) and test thoroughly, rather than disabling BREACH protection arbitrarily.

In this lesson's demo, we use the **default session-based repository** and return the properly represented token via **GET /csrf**, so no custom request handler changes are needed.

## 7. BREACH Protection and Deferred Tokens in Spring Security 6

Spring Security 6 has two details that often confuse developers:

### 7.1. Deferred CSRF Token

Tokens are loaded lazily (deferred). For pure read-only GETs, Spring Security may not need to create/read an `HttpSession` just for CSRF handling. When a request uses an unsafe method or a controller/template accesses the token, the token is loaded/generated.

The main benefit is avoiding unnecessary session lookups. Deferred tokens **do not mean POSTs skip verification**: on unsafe requests, `CsrfFilter` still fetches the expected token to verify.

### 7.2. XorCsrfTokenRequestAttributeHandler and BREACH

To mitigate BREACH (an attack involving response compression and secrets), Spring Security 6 by default exposes tokens **masked with randomness** in request attributes. The displayed token string across two renders can differ even though the raw token stored in the repository corresponds to the same session.

~~~text
Raw CSRF token in repository:          T
Request 1, presented token:            mask(T, random1)
Request 2, presented token:            mask(T, random2)

Client sends back the presented token.
Request handler unmasks it back to T.
CsrfFilter compares against expected T.
~~~

This explains why seeing different token strings on two GETs does not necessarily mean the session changed. **Do not strip masking yourself or manually compare masked strings against raw tokens**. Let `CsrfTokenRequestHandler` manage it per Spring Security's contract.

## 8. Complete Spring Boot 3.x Example: Observing POST Blocked Before Data Mutates

We build an **HTTP session**-backed counter:

- **GET /csrf**: returns the CSRF token and header/parameter names to the client; permitted without login.
- **GET /api/counter**: views current count; requires authenticated user.
- **POST /api/counter/increment**: increments count; requires **authenticated** user and **valid CSRF token**.
- **GET /login, POST /login**: uses **Spring Security's default form login**; no custom auth controller needed.

To observe what CSRF actually protects, we check that POST without a token returns 403 and reading the counter afterward still shows 0. With a valid token, POST increments it to 1.

### 8.1. Preparing the Project

Create a Spring Boot **3.x**, Java **17+**, Gradle project with group **com.example**, artifact **demo**, package **com.example.demo** via Spring Initializr. Select:

- **Spring Web** → spring-boot-starter-web.
- **Spring Security** → spring-boot-starter-security.

The application needs no template engine because Spring Security includes a default login page and the API endpoints return JSON. In the generated Gradle project, create:

~~~text
src/main/java/com/example/demo/CsrfTokenDemoApplication.java
~~~

### 8.2. Complete Java Code

~~~java
package com.example.demo;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.context.annotation.SessionScope;

@SpringBootApplication
public class CsrfTokenDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(CsrfTokenDemoApplication.class, args);
    }
}

@Configuration
@EnableWebSecurity
class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .sessionManagement(session -> session
                .sessionCreationPolicy(
                    SessionCreationPolicy.IF_REQUIRED))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/csrf")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/counter")
                    .authenticated()
                .requestMatchers(HttpMethod.POST,
                    "/api/counter/increment")
                    .authenticated()
                .anyRequest().denyAll())
            // Do not disable CSRF: by default Spring Security protects
            // state-changing HTTP methods.
            .formLogin(form -> form
                .defaultSuccessUrl("/api/counter", true)
                .permitAll())
            .logout(logout -> logout
                .logoutSuccessUrl("/login?logout")
                .permitAll())
            .build();
    }

    @Bean
    UserDetailsService userDetailsService() {
        UserDetails learner = User.withUsername("learner")
            .password("{noop}demo123")
            .roles("USER")
            .build();
        return new InMemoryUserDetailsManager(learner);
    }
}

@Component
@SessionScope
class CounterState {
    private int value;

    public synchronized int get() {
        return value;
    }

    public synchronized int increment() {
        return ++value;
    }
}

@RestController
class CounterController {

    private final CounterState state;

    CounterController(CounterState state) {
        this.state = state;
    }

    public record CsrfInfo(
            String headerName,
            String parameterName,
            String token) {
    }

    @GetMapping("/csrf")
    CsrfInfo csrf(CsrfToken csrfToken) {
        return new CsrfInfo(
            csrfToken.getHeaderName(),
            csrfToken.getParameterName(),
            csrfToken.getToken());
    }

    @GetMapping("/api/counter")
    Map<String, Integer> counter() {
        return Map.of("count", state.get());
    }

    @PostMapping("/api/counter/increment")
    Map<String, Integer> increment() {
        return Map.of("count", state.increment());
    }
}
~~~

**Explanation of key points:**

1. **@EnableWebSecurity** and `SecurityFilterChain` configure Servlet endpoint protection. Spring Security 6.x's default policy still includes CSRF protection; do not call **csrf.disable()**.
2. **@SessionScope** stores `CounterState` per `HttpSession` to observe state. The singleton Controller receives a **scoped proxy** of `CounterState`; each session gets its own instance. Two requests in the same session share the counter.
3. **GET /csrf** is `permitAll` yet still passes through the Spring Security filter chain to resolve `CsrfToken`. Calling `getToken()` forces the deferred token to be loaded/generated when needed.
4. **formLogin** generates the default login page and permits URLs for the login flow. `POST /login` is handled by the **form authentication filter**, not `CounterController`.
5. **POST /api/counter/increment** executes the controller only if the request passes the CSRF filter and holds valid `Authentication`. Missing tokens may yield **403 before Spring Security decides to redirect to login**.
6. **CounterState.increment()** uses `synchronized` solely so concurrent requests in the same demo session avoid lost updates. Do not treat `HttpSession` as a production transaction store.
7. **{noop}demo123** is a local test password; never store noop passwords in production. Use a proper `PasswordEncoder` and user store.

**There is no fixed CSRF token in this lesson.** Each run generates random values; do not copy sample tokens from docs to send to your server.

### 8.3. Running the Application

From the project directory with a Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

Windows: **gradlew.bat bootRun**. By default, the app runs at **http://localhost:8080** unless `server.port` is changed.

You can open **/login** in a browser to sign in with `learner/demo123`, then visit **/api/counter** to inspect JSON. However, to verify missing/invalid CSRF tokens, stepping through with `curl` and a cookie jar is clearer.

### 8.4. Testing with Bash, curl, and Python 3

The commands below assume a Bash-like terminal with **curl** and **python3**, not native PowerShell syntax. Create the cookie jar **in a private test directory**; do not commit or share it. Note using **-b** to send cookies and **-c** to save updated cookies, since session IDs may change after login.

**Step 1: fetch token before logging in**

~~~bash
curl -sS -c cookies.txt \
  http://localhost:8080/csrf > csrf-before.json

python3 -m json.tool csrf-before.json
~~~

The returned JSON will resemble:

~~~json
{
  "headerName": "X-CSRF-TOKEN",
  "parameterName": "_csrf",
  "token": "random-value-returned-by-server"
}
~~~

The token string above is just an illustrative label; the real token is generated by the server. Browser/curl stores **JSESSIONID** when the repository must create a session to persist the token.

**Step 2: POST /login requires token and cookie from the same session**

~~~bash
CSRF=$(python3 -c \
  "import json; print(json.load(open('csrf-before.json'))['token'])")

curl -i -b cookies.txt -c cookies.txt \
  --data-urlencode "username=learner" \
  --data-urlencode "password=demo123" \
  --data-urlencode "_csrf=$CSRF" \
  http://localhost:8080/login
~~~

Per configuration, Spring Security authenticates `learner`, applies session management, and typically returns **HTTP 302** to **/api/counter**. Without **-L**, `curl` does not follow redirects automatically.

**Step 3: check initial state**

~~~bash
curl -i -b cookies.txt \
  http://localhost:8080/api/counter
~~~

Expected HTTP 200 with JSON:

~~~json
{"count":0}
~~~

**Step 4: send POST without CSRF token**

~~~bash
curl -i -X POST -b cookies.txt \
  http://localhost:8080/api/counter/increment

curl -i -b cookies.txt \
  http://localhost:8080/api/counter
~~~

Expected POST returns **403**, and subsequent GET remains:

~~~json
{"count":0}
~~~

This is user-visible proof: POST is blocked **before CounterController.increment() increments the counter**.

**Step 5: fetch a fresh token after login and send valid POST**

In Spring Security 6, **CsrfAuthenticationStrategy** may clear the old token upon successful authentication. Therefore, obtain a new token after login; do not assume the token in `csrf-before.json` still works:

~~~bash
curl -sS -b cookies.txt -c cookies.txt \
  http://localhost:8080/csrf > csrf-after.json

CSRF=$(python3 -c \
  "import json; print(json.load(open('csrf-after.json'))['token'])")

curl -i -X POST -b cookies.txt -c cookies.txt \
  -H "X-CSRF-TOKEN: $CSRF" \
  http://localhost:8080/api/counter/increment
~~~

Expected HTTP 200 with JSON:

~~~json
{"count":1}
~~~

Afterward:

~~~bash
curl -i -b cookies.txt \
  http://localhost:8080/api/counter
~~~

Expected:

~~~json
{"count":1}
~~~

**Step 6: test an intentionally invalid token**

~~~bash
curl -i -X POST -b cookies.txt \
  -H 'X-CSRF-TOKEN: definitely-not-the-session-token' \
  http://localhost:8080/api/counter/increment
~~~

Expected **403**, and `GET /api/counter` remains **{"count":1}**.

### 8.5. Behavior Comparison Table

| Request | Token / authentication | Expected HTTP | Counter value |
| --- | --- | --- | --- |
| GET /csrf | Not logged in | 200 | Unchanged |
| POST /login | Cookie + valid CSRF token, valid username/password | 302 | Unchanged |
| GET /api/counter | Cookie after login | 200 | 0 |
| POST /api/counter/increment | Cookie after login, **no CSRF token** | **403** | Still 0 |
| POST /api/counter/increment | Cookie after login, **wrong** CSRF token | **403** | Does not increment |
| POST /api/counter/increment | Cookie after login, **valid** token | **200** | Increments to 1 |
| GET /api/counter | Same cookie after valid POST | 200 | 1 |
| GET /api/counter | Not logged in | 302 to /login | Value not exposed |
| POST /api/counter/increment | Not logged in, no token | Usually **403** due to CSRF before authorization | Unchanged |

These values are **expected results from the source code**, not execution logs from the learner's machine. If a request gets 403 due to a missing token and you try fixing the client by adding username/password while still omitting CSRF, the problem remains unsolved.

**Note:** requests without a token may be blocked by CSRF first, so do not enforce a rigid rule like "unauthenticated always returns 401" or "unauthenticated always 302". Outcomes depend on filters and authentication mechanisms; in this form-login demo, an unauthenticated protected GET normally redirects 302.

### 8.6. Logout and Token Replacement

With default logout, Spring Security handles `POST /logout` with a valid CSRF token. Old tokens and session/security state can be cleared or invalidated after logout.

Fetch a token while logged in and POST logout:

~~~bash
curl -sS -b cookies.txt -c cookies.txt \
  http://localhost:8080/csrf > csrf-logout.json

CSRF=$(python3 -c \
  "import json; print(json.load(open('csrf-logout.json'))['token'])")

curl -i -X POST -b cookies.txt -c cookies.txt \
  -H "X-CSRF-TOKEN: $CSRF" \
  http://localhost:8080/logout
~~~

Per configuration, successful logout normally returns **302** to **/login?logout**, invalidating the authenticated session. If the client needs to continue sending unsafe requests before logging in again, **fetch a new CSRF token** per application policy. Never reuse a token from a logged-out session.

## 9. Automated Testing with Spring Security Test and MockMvc

Testing only that a POST with a CSRF token returns 200 is insufficient. You must prove **POST without a token never reaches business logic** and **POST with a wrong token is also rejected**.

Add dependencies to **build.gradle** if absent:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

This is a **Gradle Groovy DSL fragment**, not a complete file. Spring Initializr usually already includes `spring-boot-starter-test`; do not declare duplicates.

Create the file:

~~~text
src/test/java/com/example/demo/CsrfTokenDemoApplicationTest.java
~~~

Contents:

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CsrfTokenDemoApplicationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void csrfRejectsMissingAndInvalidTokenBeforeMutation()
            throws Exception {
        // Log in via Spring Security form filter, with token for POST.
        MvcResult login = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "learner")
                .param("password", "demo123"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        MockHttpSession session = (MockHttpSession)
                login.getRequest().getSession(false);

        mvc.perform(get("/api/counter").session(session))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.count").value(0));

        // Missing CSRF token -> 403, controller not called.
        mvc.perform(post("/api/counter/increment")
                .session(session))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/counter").session(session))
            .andExpect(jsonPath("$.count").value(0));

        // Intentionally invalid token -> 403.
        mvc.perform(post("/api/counter/increment")
                .session(session)
                .with(csrf().useInvalidToken()))
            .andExpect(status().isForbidden());

        // Valid token -> controller is allowed to increment value.
        mvc.perform(post("/api/counter/increment")
                .session(session)
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.count").value(1));

        mvc.perform(get("/api/counter").session(session))
            .andExpect(jsonPath("$.count").value(1));
    }
}
~~~

Run tests:

~~~bash
./gradlew test
~~~

Windows: **gradlew.bat test**.

**Test explanation:**
- **csrf()** is a test helper from `spring-security-test` supplying a valid CSRF token; production clients do not have this helper.
- **csrf().useInvalidToken()** intentionally sends a wrong token to test the rejection path.
- Keeping the same **MockHttpSession** makes comparing the expected token and the counter meaningful.
- Checking the counter before and after 403 proves business mutation did not occur.
- The test performs form login to obtain an authenticated session rather than only using `@WithMockUser`. However, to test cookie flags, redirects, token rotation, or real CORS, integration/e2e tests in a browser or full HTTP client are still needed.

**Note:** code snippets and commands are documentation for running in a compatible project; stated results are expected behavior, not a claim that Gradle was executed inside this document.

## 10. HTML Form and Thymeleaf Integration

For server-rendered apps, CSRF tokens are typically sent via a hidden form field.

Example HTML fragment corresponding to a form that mutates data:

~~~html
<form action="/settings" method="post">
    <input type="hidden" name="_csrf"
           value="token-from-server">
    <button type="submit">Save</button>
</form>
~~~

The **value** line merely shows where the token is placed; **never use a fixed string** like the snippet in a real app. When using **Thymeleaf + Spring Security** properly, forms with **th:action** integrate with **RequestDataValueProcessor** to insert the corresponding CSRF field:

~~~html
<form th:action="@{/settings}" method="post">
    <button type="submit">Save</button>
</form>
~~~

The template fragment above must be used in a project with Spring MVC and Thymeleaf, not as a standalone HTML file; the controller needs a `POST /settings` endpoint and matching authorization. Inspect the rendered HTML in DevTools to verify the **_csrf** field exists.

When the server receives the form:
1. The browser sends the session cookie per policy.
2. The browser sends the **_csrf** form field rendered by the app.
3. `CsrfFilter` reads the token from the form parameter.
4. The token is checked before the business handler executes.
5. If the token is invalid or missing, the handler does not execute.

**Form login and logout are also state-changing operations.** In standard Servlet configurations, `POST /login` and `POST /logout` require valid tokens. Do not add `csrf.ignoringRequestMatchers("/login")` or drop logout protection merely to avoid updating forms/clients without evaluating login CSRF risks.

## 11. Browser fetch/JSON Integration and SPAs

When a frontend calls APIs via JavaScript, an easy-to-follow approach is:

~~~javascript
// Example running on the same origin as the server.
// Server must expose GET /csrf returning compatible JSON.
async function csrfInfo() {
    const response = await fetch("/csrf", {
        credentials: "same-origin"
    });
    if (!response.ok) {
        throw new Error("Failed to obtain CSRF token");
    }
    return response.json();
}

async function increment() {
    const csrf = await csrfInfo();
    const response = await fetch("/api/counter/increment", {
        method: "POST",
        credentials: "same-origin",
        headers: {
            [csrf.headerName]: csrf.token
        }
    });
    if (!response.ok) {
        throw new Error("Request rejected: " + response.status);
    }
    return response.json();
}
~~~

This is a **frontend JavaScript snippet**; it does not run by sitting in Java sources. It retrieves the token from a same-origin endpoint and returns it in an explicitly set header. For cross-origin apps, configure CORS/credentials/cookies/SameSite per your threat model; never treat **Access-Control-Allow-Origin: \*** with credentials as a general solution.

### SPAs and Token Rotation

With Spring Security 6:
- Tokens may be loaded lazily (deferred).
- BREACH masking changes the per-request token representation.
- **CsrfAuthenticationStrategy** clears old tokens upon successful authentication.
- **CsrfLogoutHandler** clears tokens upon successful logout.
- An SPA wishing to continue making POST/PUT/DELETE requests after login/logout may need to re-call `/csrf` to retrieve a fresh token.

If the frontend caches a CSRF token indefinitely in memory without refreshing after login, a subsequent POST may return **403** despite an active logged-in session. That does not mean the server randomly denied permissions; the token likely became invalid.

### Can Tokens Be Delivered via Cookie and Placed in a Header?

Yes, with **CookieCsrfTokenRepository** and an appropriate SPA request handler configured per Spring Security docs. The client reads the readable CSRF cookie and sends a header like **X-XSRF-TOKEN**. However, distinguish the raw token from the cookie vs. the masked token in request attributes; do not configure raw-vs-masked behavior without verification.

Having the browser auto-send the CSRF cookie **without the client actively placing the corresponding value into a header/form is insufficient** for a proper double-submit implementation. The goal is to require the client to supply a value an attacker page cannot produce, while the server validates it under a trusted policy.

## 12. How Do CSRF, CORS, SameSite, and Bearer Tokens Relate?

| Mechanism | What does it protect/define? | What it does **NOT** replace |
| --- | --- | --- |
| **CSRF token** | Defends against forged state-changing requests when auto-sent browser credentials exist | Authentication, Authorization, input validation, XSS defense |
| **SameSite cookie** | Restricts certain cases where browsers send cookies cross-site | CSRF tokens for all scenarios |
| **CORS** | Browser rules for sharing cross-origin resources and certain JS-initiated requests | User authentication or server-side authorization |
| **HttpOnly** | Restricts JavaScript access to cookies | CSRF; browsers can still auto-send cookies |
| **Secure** | Requires cookies to be sent over HTTPS | Overall application security |
| **Bearer token in Authorization header** | Credential actively sent by client per HTTP request | Protecting tokens from XSS, replay, or leakage |
| **JWT** | Token/claims format | Deciding CSRF safety solely by the name JWT |

### Does Using Bearer Tokens Require CSRF?

**Do not answer solely with the label "JWT" or "stateless".** Ask: **does the browser automatically attach the authenticating credential when another website triggers a request?**

- Browser web app using **session cookies**: requires evaluating/enabling CSRF; this is the demo's model.
- API strictly for **non-browser clients**, where bearer tokens are actively set in the `Authorization` header by clients and no auto-authenticating cookies exist: the CSRF threat model differs; `CsrfFilter` may not be needed on paths designed that way.
- JWT placed in an **auto-sent cookie**: still needs CSRF evaluation just like cookie authentication.
- HTTP Basic cached in browsers: can also carry CSRF risk because browsers auto-send credentials in certain scenarios.

Scoped CSRF disabling must be grounded in actual credential and client design, not merely because an API accepts JSON. If only certain endpoints are truly stateless, Spring Security can use **requireCsrfProtectionMatcher** or **ignoringRequestMatchers** in a controlled way to scope properly; test that session-based paths remain protected.

### Can Origin/Referer Be Used?

Checking **Origin** or **Referer** against trusted origins and request characteristics can supplement defense. However, headers may be absent in legitimate cases and behave differently across proxies/clients; never assume every request has an accurate `Referer`. For session-cookie apps, CSRF tokens typically serve as the primary verification mechanism; origin checks provide good defense-in-depth.

## 13. Distinguishing Types of HTTP 403

A **403** response does not automatically mean CSRF. Depending on configuration and flow:

| Situation | Typical status | Area to inspect |
| --- | --- | --- |
| POST with login cookie but missing CSRF token | **403** | `CsrfFilter`, expected token, actual header/parameter |
| POST with wrong token, same session | **403** | Expected token, session, request handler |
| POST with stale token after login/logout | **403** | Token rotation, `CsrfAuthenticationStrategy`/`CsrfLogoutHandler` |
| POST with valid CSRF but lacking authority | **403** | `AuthorizationManager`, `GrantedAuthority`, resource ownership |
| Unauthenticated protected GET with form login | Usually **302** to `/login` | `AuthenticationEntryPoint` |
| Unauthenticated protected GET with Basic/Bearer | Usually **401** | Authentication entry point/token |
| Unauthenticated POST also missing CSRF | Can be **403** before 302/401 | Filter order and blocking at CSRF layer |
| POST succeeding after all checks | **200/201/204...** per controller | Business logic, response contract |

When encountering 403, check everything: method, path, current cookie/session, which endpoint issued the token, whether the token went in a header or field, whether login/logout happened between requests, roles/authorities, and business rules. Never "fix 403" by disabling CSRF entirely when the cause is a client failing to send the token.

### Enabling Logs When Needed

In **application.properties** for development:

~~~properties
logging.level.org.springframework.security=DEBUG
~~~

Do not log raw CSRF tokens, `Cookie` headers, session IDs, passwords, or `Authorization` headers to shared monitoring systems. To verify logic, inspect **status + counter values** instead of printing secrets/tokens.

## 14. Common Implementation Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using GET to delete/update data | GET does not check CSRF by default | Switch to POST/PUT/PATCH/DELETE, apply CSRF and authorization |
| Checking only whether user is logged in | Forged requests with valid session cookies pass through | Require CSRF tokens for unsafe methods |
| Sending only the session cookie on POST | Does not prove request came from an authorized UI | Also send token via header/form field |
| Taking token from session A, sending with session B's cookie | Expected/actual mismatch | Keep cookie jar consistent and fetch token for current session |
| Reusing pre-login token for all post-login requests | Old token may be cleared during authentication | Refresh token after login |
| Storing tokens in URLs | Easily leaked via logs, history, Referer | Put in header or form body |
| Enabling `CookieCsrfTokenRepository` while keeping an incompatible request handler | Raw token header from cookie isn't resolved properly | Configure SPA per docs and test raw/masked behavior |
| Disabling BREACH protection without reason | Loses protection on rendered tokens | Keep default unless specific needs dictate otherwise |
| Permitting all POSTs with `csrf.ignoringRequestMatchers("/**")` | Bypasses all CSRF | Exclude only endpoints genuinely not at risk per threat model |
| Thinking `application/json` prevents CSRF by itself | Edge cases or misconfigured Content-Type handling can exist | Evaluate realistically, keep CSRF when credentials auto-send |
| Using CORS as an authorization mechanism | Server may still process requests even if browser blocks reading results | Enforce Authentication/Authorization/CSRF |
| Thinking SameSite is a complete solution | Depends on site, method, browser, configuration | Use defense-in-depth and tokens where needed |
| Valid token yet user still shouldn't be allowed | CSRF grants no business permissions | Check roles/authorities, owner, tenant |
| Testing only with `.with(csrf())` | Does not prove rejection path works | Test missing tokens, invalid tokens, and zero data mutation |
| Not handling session expiration | Stale forms send invalid tokens, confusing UX | Provide token refresh and friendly timeout handling |
| Logging real CSRF tokens for debugging | Increases secret exposure risk | Log status/error type/non-sensitive trace IDs |

## 15. E2E Testing for Real Applications

Beyond `MockMvc`, when reviewing sensitive endpoints like **POST /transfer**, **DELETE /account**, or **PUT /profile**, verify:

1. **Valid login** creates `HttpSession`/cookies as designed.
2. **Rendered forms contain the CSRF field** or JS fetches tokens from the official endpoint.
3. **POST with valid token and valid role** executes accurately.
4. **POST without token** is blocked; data in database or store does not change.
5. **POST with tampered token** is blocked; data does not change.
6. **POST with another session's token** is blocked.
7. **POST with stale token after login/logout/session timeout** is handled per rotation/refresh policy.
8. **POST with valid token but missing permission** is still denied at the authorization layer.
9. **GET** never inadvertently modifies sensitive data.
10. **Cookie settings**: Secure, HttpOnly, SameSite, Domain/Path, HTTPS, and proxy configuration.
11. **CORS** and credential sending when frontend is on a different origin.
12. **No tokens/credentials leak in logs, URLs, or analytics**.

Never treat a 200 status alone as "CSRF passed." For financial or account operations, always verify **no side effect occurs** in every rejected case.

### Testing with Other Configurations

When using **multiple SecurityFilterChains**, confirm requests match the chain holding the intended CSRF policy. A separate chain for stateless Bearer APIs may differ in policy from the browser session chain; do not let browser-authenticated POSTs fall into a CSRF-disabled chain meant for API-only clients.

When using **Spring WebFlux**, use **CsrfWebFilter**, **ServerCsrfTokenRepository**, and **ServerCsrfTokenRequestHandler** (not `CsrfFilter` and `HttpServletRequest`). The mindset around safe/unsafe methods and expected/actual checks remains similar, but reactive code must be written and tested with WebFlux/Reactor APIs.

## 16. Self-Assessment Exercises

1. What is CSRF? Why can a browser inadvertently send another app's credentials when visiting an attacker's page?
2. Is a CSRF token a session ID, a password, or an ADMIN role?
3. State the distinct roles of **CsrfFilter**, **CsrfTokenRepository**, and **CsrfTokenRequestHandler**.
4. When a POST is missing a token, is the controller invoked before Spring Security returns 403?
5. Why do **GET** requests not require CSRF by default? What happens if a developer uses GET to delete accounts?
6. How does a CSRF token stored in the session differ from the token sent via a header?
7. Why must **CookieCsrfTokenRepository** be configured carefully when clients read raw cookies and Spring Security 6 enables XOR masking by default?
8. Does seeing different displayed tokens across two GETs necessarily prove they belong to two different sessions?
9. An SPA finishes logging in, then its immediate POST gets 403 despite fetching a token before login. What will you investigate?
10. Why do **SameSite** and **CORS** not replace all CSRF checks by themselves?
11. If an API uses a JWT stored in an **auto-sent cookie**, does CSRF still matter?
12. In `MockMvc`, how do you verify that a POST missing a token is blocked **and the counter remains unchanged**?
13. If a POST has a valid CSRF token yet the user lacks permission, must the server allow it?
14. For file-upload endpoints, why can placing the CSRF token in a header be easier to process than parsing the entire multipart body before the security check?
15. When deploying multiple servers or a shared session store, how must the mechanism fetching the expected CSRF token stay consistent across requests/sessions?

**Key takeaway:** A CSRF token is a value that a trusted server/client must **actively supply on state-changing requests**. In Spring Security Servlet, **CsrfFilter** loads the expected token via **CsrfTokenRepository**, reads the actual token via **CsrfTokenRequestHandler**, compares them, and rejects missing/invalid requests **before the controller mutates data**. Keep CSRF enabled for browser flows using auto-sent credentials, refresh tokens after login/logout, and test both rejection paths and data integrity.

## 17. Official References

- Spring Security 6.5 — CSRF for Servlet Applications: https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html
- Spring Security — Understanding CSRF protection (CSRF vs JSON/stateless/basic): https://docs.spring.io/spring-security/reference/features/exploits/csrf.html
- Spring Security 6.5 — Testing CSRF protection with MockMvc: https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/csrf.html
- Spring Security 6.5 — Exploit Protection Migrations, deferred CSRF and BREACH: https://docs.spring.io/spring-security/reference/6.5/migration/servlet/exploits.html
- Spring Security — CSRF for WebFlux: https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html
- OWASP Cross-Site Request Forgery Prevention Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html
