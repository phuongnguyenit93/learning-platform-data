# Login Testing: CSRF Tokens, Session Cookies, and Redirect Responses

## 1. Goal and scope

In a **Spring Security Servlet** application using form login, checking "valid username/password login returns HTTP 302" is **not enough**. A trustworthy login flow must simultaneously verify:

1. **CSRF token:** POST login, logout, and state-changing requests must carry a valid token per CSRF policy; forged cross-site requests must not leverage the user's cookie to bypass controls.
2. **Session cookie:** the browser retains an identifier like `JSESSIONID`, the server restores `SecurityContext` by session, and session fixation protection rotates the identifier on authentication.
3. **Redirect:** HTTP 302 with a `Location` header can mean redirecting to the login page, reporting a wrong password, reaching the success target, or returning to a resource requested prior to login.

**The three mechanisms do not replace one another.** A CSRF token is not a password or session identifier; a session cookie automatically sent by the browser does not prove a request is legitimate; a 302 does not mean the user logged in successfully.

This lesson focuses on **Login Testing** with **Java 17+ / Spring Boot 3.5.x / Spring Security 6.5.x / Spring MVC / JUnit 5 / MockMvc**, including a complete Maven project, 14 test cases, and steps to inspect cookies/redirects over real HTTP. For stateless OAuth Bearer Resource Servers or WebFlux, use dedicated methods rather than applying Servlet form login's `JSESSIONID` and redirect expectations by default.

## 2. Request/response flow to understand

~~~text
Browser                         Spring Security                      Application
   |                                  |                                 |
   | GET /dashboard                   |                                 |
   |--------------------------------->| unauthenticated                 |
   |                                  | saves GET in RequestCache       |
   |<---------------------------------| 302 Location: /login            |
   | GET /login                       |                                 |
   |--------------------------------->| renders form with CSRF token    |
   |<---------------------------------| 200 HTML + _csrf                |
   |                                  | session depends on repository   |
   | POST /login                      |                                 |
   | Cookie: JSESSIONID=...           |                                 |
   | username/password/_csrf          |                                 |
   |--------------------------------->| CsrfFilter checks token         |
   |                                  | UsernamePasswordAuthentication  |
   |                                  | AuthenticationManager           |
   |                                  | SessionAuthenticationStrategy   |
   |                                  | saves SecurityContext           |
   |<---------------------------------| 302 Location: /dashboard        |
   |                                  | changes session ID vs. fixation |
   | GET /dashboard + session cookie  |                                 |
   |--------------------------------->| loads SecurityContext           |
   |                                  |-------------------------------> |
   |<---------------------------------| 200 dashboard                   |
~~~

If the user opens the login page directly **without a saved request**, success typically redirects to the default target (e.g., `/home`). If they previously hit a protected resource, `SavedRequestAwareAuthenticationSuccessHandler` can redirect back to the original resource.

### 2.1. Related components

| Component | Role | What to test |
| --- | --- | --- |
| `CsrfFilter` | Blocks unsafe requests missing/invalid CSRF | 403 when missing/invalid; passes when token is valid |
| `CsrfTokenRepository` | Stores the expected token | Session or cookie matches configuration |
| `CsrfTokenRequestHandler` | Resolves token in parameter/header | Hidden field, header, XOR/BREACH |
| `UsernamePasswordAuthenticationFilter` | Receives POST /login | Proper parameter names and login URL |
| `AuthenticationManager` | Checks username/password | Valid and invalid credentials |
| `SecurityContextRepository` | Saves/restores authentication | Follow-up requests remain authenticated |
| `SessionAuthenticationStrategy` | Prevents session fixation | Identifier rotates on login |
| `ExceptionTranslationFilter` | Triggers the login entry point | 302 to /login |
| `RequestCache` | Saves intended URL prior to login | Saved request overrides default target |
| `AuthenticationSuccessHandler` | Decides redirect on success | 302 with right Location |
| `AuthenticationFailureHandler` | Decides redirect on wrong password | 302 /login?error |
| `LogoutFilter` | Logs out and clears session/context | POST logout with CSRF, redirect, and invalidation |

Easy point of confusion: **CSRF is checked before credentials** in the standard flow. A login POST missing CSRF returning 403 does not mean the password was wrong. Spring Security form login can also return a redirect on authentication failure; it is not 401 like HTTP Basic or Bearer.

## 3. What is a CSRF token, and how does it differ from a session cookie?

A session cookie is normally attached automatically by the browser per domain/path/SameSite policy. That creates the risk of **Cross-Site Request Forgery (CSRF)**: a malicious site triggers a request to a logged-in site and abuses the auto-sent cookie. Examples: sending a POST to change a contact address, log out, or **login CSRF** making the victim use an attacker-controlled account.

Spring Security issues an unpredictable CSRF token, stores the expected value server-side or via the configured repository, and requires the client to present the token on state-changing requests.

**Do not equate:**

- `JSESSIONID`: the session identifier. It links requests to session state, including `SecurityContext`, though the cookie itself does not hold username/password when using default `HttpSession`.
- `_csrf`: the hidden form parameter holding the CSRF token rendered in the form.
- `X-CSRF-TOKEN` / `X-XSRF-TOKEN`: request headers that can present the token depending on repository/config.
- `XSRF-TOKEN`: cookie name for `CookieCsrfTokenRepository`, distinct from the session cookie.
- Password/OTP: credentials to authenticate the user; a CSRF token **is not authentication**.

### 3.1. Which methods require CSRF?

Spring Security protects unsafe HTTP methods by default. GET, HEAD, OPTIONS, and TRACE do not require CSRF under the default matcher; POST, PUT, PATCH, and DELETE typically do.

| Request | Default CSRF | Notes |
| --- | --- | --- |
| GET /login | No | Renders token in form |
| POST /login | Yes | Login is also vulnerable to login CSRF |
| GET /dashboard | No | Read-only |
| POST /profile | Yes | Mutates state |
| POST /logout | Yes | Prevents logout CSRF |
| DELETE /profile | Yes | Not GET |
| GET /dangerous-delete | No under matcher | **Design flaw** if GET mutates state |

Never move sensitive operations to GET just to avoid sending a CSRF token.

### 3.2. Missing, invalid, and valid CSRF

For POST login:

~~~http
POST /login HTTP/1.1
Content-Type: application/x-www-form-urlencoded
Cookie: JSESSIONID=SESSION_ID

username=learner&password=lab-password
~~~

**Missing CSRF**: typically HTTP 403. Even with the right password, the token is missing so `CsrfFilter` blocks it before authentication.

~~~http
POST /login HTTP/1.1
Content-Type: application/x-www-form-urlencoded
Cookie: JSESSIONID=SESSION_ID

username=learner&password=lab-password&_csrf=INVALID
~~~

**Invalid CSRF**: typically HTTP 403. Only with a real token from the right repository/session and valid credentials can login succeed and return a 302 redirect.

The strings `SESSION_ID`/`INVALID` are illustrative only, not real credentials.

## 4. Deferred CSRF, XOR, and CookieCsrfTokenRepository in Spring Security 6

### 4.1. Default HttpSessionCsrfTokenRepository

Spring Security Servlet normally uses `HttpSessionCsrfTokenRepository`: the expected token lives in the server-side HTTP session. When a view needs to render a hidden input, Spring places the token in a request attribute. The form submits the token and session cookie, and the server compares against the expected token.

Since Spring Security 6, CSRF tokens are **deferred** by default: GETs that do not need the token do not necessarily load/create a session solely because of Spring Security. When rendering a form or processing an unsafe method, the token is used and may create a session.

`XorCsrfTokenRequestAttributeHandler` is the default handler mitigating BREACH risks by randomizing the token representation. Therefore:

- Do not hard-code token values in unit/integration tests.
- Rendered form token values can differ in representation across renders.
- An HTML token will not necessarily equal a string read directly from a session attribute.
- Test that requests are **actually accepted** rather than just comparing token strings.
- Login/logout can clear/rotate old CSRF tokens, which is especially important for SPAs.

### 4.2. CookieCsrfTokenRepository and SPAs

Some SPAs read the CSRF token from the `XSRF-TOKEN` cookie and send the `X-XSRF-TOKEN` header. Configuration may use `CookieCsrfTokenRepository.withHttpOnlyFalse()` so JavaScript can read the **CSRF cookie**.

~~~text
Cookie: XSRF-TOKEN=<csrf-token>
X-XSRF-TOKEN: <csrf-token>
~~~

**Never apply `HttpOnly=false` to `JSESSIONID`** just because JS needs CSRF. The session cookie is a session credential and should stay `HttpOnly`.

Spring Security 6 has distinct handling for **raw tokens in cookies**, **XOR-encoded tokens in HTML**, and deferred loading; SPAs often need a customized `CsrfTokenRequestHandler` as shown in the official docs to resolve headers properly, as well as fetching a new CSRF cookie after login/logout. Simply switching to `CookieCsrfTokenRepository` and skipping this part can cause POST 403 errors.

CORS does not prevent CSRF on its own: cross-origin form submissions can occur without the attacker needing to read the response; SameSite and Origin checks are complementary measures, not substitutes for CSRF policy per threat model.

## 5. Session cookies and attributes to verify

In Spring Boot Servlet/Tomcat you commonly see:

~~~http
Set-Cookie: JSESSIONID=REDACTED; Path=/; HttpOnly
Cookie: JSESSIONID=REDACTED
~~~

The session ID value is an opaque string; the server uses it to look up the session, not a JWT carrying user info.

| Attribute | Meaning | Verification |
| --- | --- | --- |
| `HttpOnly` | JavaScript cannot read the session cookie | Inspect actual Set-Cookie |
| `Secure` | Sent only over HTTPS | Test public HTTPS ingress |
| `SameSite` | Controls cross-site cookie behavior | Check appropriate Lax/Strict/None policy |
| `Path` | Paths where the cookie is sent | Not overly broad |
| `Domain` | Valid cookie domain | Not inadvertently spanning all subdomains |
| `Expires`/`Max-Age` | Session or persistent lifetime | Do not assume session cookies have Max-Age |
| ID rotation | Prevents session fixation | Compare session ID before/after authentication |

Final flags may be shaped by the embedded container, Spring Session, or reverse proxy; **inspect `Set-Cookie` over real HTTP**, not just MockMvc.

### 5.1. Session fixation

An attacker tries to force a user to use a known session ID, waits for the user to log in, and reuses that ID. Spring Security defends against fixation by default by changing the session ID upon successful authentication; on Servlet 3.1+, it uses `changeSessionId()`.

Tests should create a session before login (e.g., via saved request/CSRF), record its ID, perform a valid login, and verify the new ID **differs from the old ID**, while follow-up requests with the new session stay authenticated.

A cookie existing **before login** does not mean the user is authenticated. What must be verified is a GET to a protected route after successful login and session fixation protection, not just the presence of a `Set-Cookie` header.

### 5.2. MockMvc sessions differ from real browsers

`MockMvc` uses `MockHttpSession`, simulating Servlet requests/filters/responses without providing a full cookie jar or network/container behavior. Therefore:

- MockMvc **does not auto-follow** redirects; each request must be sent explicitly by the test.
- MockMvc does not automatically retain cookies like a browser; to simulate the same session, pass `.session(session)`.
- Do not treat the absence of `Set-Cookie: JSESSIONID` in MockMvc as a Spring Security bug.
- Do not conclude production Secure/HttpOnly/SameSite flags from MockMvc alone.
- To test `Set-Cookie`, use embedded Tomcat/an HTTP client or browser E2E through an HTTPS proxy.

## 6. HTTP 302: what to check beyond status?

| Request | Condition | Typical response |
| --- | --- | --- |
| GET /dashboard | Not logged in | 302 Location: /login |
| GET /login | Not logged in | 200 HTML containing _csrf |
| POST /login | Missing or invalid CSRF | 403 |
| POST /login | Valid CSRF, wrong password | 302 Location: /login?error |
| POST /login | Valid CSRF, right password, direct login | 302 Location: /home (this example) |
| POST /login | Right password, has saved request | 302 to saved path |
| GET /dashboard | Authenticated session | 200 |
| POST /logout | Valid CSRF | 302 Location: /login?logout |
| POST /logout | Missing/invalid CSRF | 403 |

**302 does not by itself prove login succeeded:** redirects are also used when unauthenticated or when the password is wrong. Always assert **Location, session, and the follow-up request**.

### 6.1. RequestCache and saved requests

An unauthenticated GET to a protected resource can be saved by `ExceptionTranslationFilter` in `HttpSessionRequestCache`. After successful authentication, `SavedRequestAwareAuthenticationSuccessHandler` typically sends the user back to that URL instead of the default success target.

~~~text
GET /dashboard       -> 302 /login  (saves saved request)
GET /login           -> 200
POST /login          -> 302 /dashboard (saved request)
GET /dashboard       -> 200
~~~

If the user opens the login page directly:

~~~text
GET /login           -> 200
POST /login          -> 302 /home (default target)
~~~

Both are valid logins yet produce **two different Locations**. Redirect URLs may be absolute URLs or carry markers/queries depending on Spring version/config, so saved-request tests should check the destination sensibly without over-coupling to relative vs. absolute formatting.

### 6.2. Open redirects, proxies, and entry points

- Never take a client `returnUrl` or `next` parameter and pass it straight into `sendRedirect`; attackers can exploit open redirects to external domains.
- If supporting custom redirects, use an allowlist of exact trusted URLs/origins or relative internal paths, handling protocol-relative URLs and encoding.
- When the app sits behind a TLS ingress, check that `Location` uses the public HTTPS host rather than returning `http://internal-host:8080`; accept forwarded headers only from trusted proxies.
- If there are multiple `SecurityFilterChain`s, web forms usually return 302 login while Bearer APIs may return 401; check chain order and matchers.

## 7. Spring Boot Maven project (Java 17+) for login testing

We build a learning application:

- Account `learner` / `lab-password`, role USER.
- GET `/health` public.
- GET `/home`, `/dashboard` protected.
- POST `/profile` protected and CSRF enabled.
- Default form login, direct login success redirects to `/home` (when no saved request exists).
- Default POST `/logout` with CSRF and redirect to `/login?logout`.

Uses Spring Boot **3.5.x** with Spring Security **6.5.x** managed by the Boot BOM. `{noop}` passwords are for lab use only; production uses PasswordEncoder hashes and proper credential stores.

### 7.1. File structure

~~~text
login-flow-lab/
├── pom.xml
└── src/
    ├── main/java/demo/login/LoginFlowApplication.java
    └── test/java/demo/login/LoginFlowTests.java
~~~

### 7.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
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
    <groupId>demo</groupId>
    <artifactId>login-flow-lab</artifactId>
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

### 7.3. LoginFlowApplication.java

~~~java
package demo.login;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class LoginFlowApplication {

    public static void main(String[] args) {
        SpringApplication.run(LoginFlowApplication.class, args);
    }

    @Bean
    UserDetailsService users() {
        var user = User.withUsername("learner")
            .password("{noop}lab-password")
            .roles("USER")
            .build();
        return new InMemoryUserDetailsManager(user);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/health").permitAll()
                .requestMatchers("/home", "/dashboard", "/profile")
                    .authenticated()
                .anyRequest().denyAll())
            .formLogin(form -> form.defaultSuccessUrl("/home", false))
            .logout(Customizer.withDefaults());

        // CSRF stays enabled by default. Do not call csrf.disable().
        return http.build();
    }

    @RestController
    static class AppApi {
        @GetMapping("/health")
        String health() {
            return "ready";
        }

        @GetMapping("/home")
        String home(Authentication auth) {
            return "home:" + auth.getName();
        }

        @GetMapping("/dashboard")
        String dashboard(Authentication auth) {
            return "dashboard:" + auth.getName();
        }

        @PostMapping("/profile")
        String changeProfile(Authentication auth) {
            // Illustrative only: does not mutate a real database.
            return "updated:" + auth.getName();
        }
    }
}
~~~

Because there is a custom `SecurityFilterChain`, `.formLogin(...)` must be called explicitly. Spring's generated login page handles `GET /login` and `POST /login`. Default CSRF is preserved. The `/profile` route supports POST only and requires authentication + CSRF token.

## 8. JUnit 5 and MockMvc: 14 test cases

File `src/test/java/demo/login/LoginFlowTests.java`:

~~~java
package demo.login;

import jakarta.servlet.http.HttpSession;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.hamcrest.Matchers.containsString;
import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class LoginFlowTests {

    @Autowired
    MockMvc mvc;

    private static final String USER = "learner";
    private static final String PASS = "lab-password";

    private MvcResult login() throws Exception {
        return mvc.perform(post("/login")
                .param("username", USER)
                .param("password", PASS)
                .with(csrf()))
            .andExpect(status().is3xxRedirection())
            .andReturn();
    }

    @Test
    void publicEndpointIsAccessible() throws Exception {
        mvc.perform(get("/health"))
            .andExpect(status().isOk())
            .andExpect(content().string("ready"));
    }

    @Test
    void anonymousProtectedGetRedirectsToLogin() throws Exception {
        mvc.perform(get("/dashboard"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login"));
    }

    @Test
    void loginFormContainsCsrfField() throws Exception {
        mvc.perform(get("/login"))
            .andExpect(status().isOk())
            .andExpect(content().string(containsString("name=\"_csrf\"")));
    }

    @Test
    void correctPasswordWithoutCsrfIsForbidden() throws Exception {
        mvc.perform(post("/login")
                .param("username", USER)
                .param("password", PASS))
            .andExpect(status().isForbidden());
    }

    @Test
    void incorrectCsrfIsForbidden() throws Exception {
        mvc.perform(post("/login")
                .param("username", USER)
                .param("password", PASS)
                .with(csrf().useInvalidToken()))
            .andExpect(status().isForbidden());
    }

    @Test
    void invalidPasswordWithCsrfRedirectsToError() throws Exception {
        mvc.perform(post("/login")
                .param("username", USER)
                .param("password", "wrong-password")
                .with(csrf()))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?error"));
    }

    @Test
    void directLoginRedirectsHomeAndPersistsSession()
            throws Exception {
        MvcResult result = login();
        assertEquals("/home", result.getResponse().getRedirectedUrl());

        HttpSession session = result.getRequest().getSession(false);
        assertNotNull(session);
        mvc.perform(get("/dashboard")
                .session((MockHttpSession) session))
            .andExpect(status().isOk())
            .andExpect(content().string("dashboard:learner"));
    }

    @Test
    void savedRequestIsRestoredAndSessionIdChanges()
            throws Exception {
        MvcResult first = mvc.perform(get("/dashboard"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login"))
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) first.getRequest().getSession(false);
        assertNotNull(session);
        String oldId = session.getId();

        MvcResult signedIn = mvc.perform(post("/login")
                .session(session)
                .param("username", USER)
                .param("password", PASS)
                .with(csrf()))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        String location = signedIn.getResponse().getRedirectedUrl();
        assertNotNull(location);
        assertTrue(location.contains("/dashboard"));
        HttpSession after = signedIn.getRequest().getSession(false);
        assertNotNull(after);
        assertNotEquals(oldId, after.getId());
    }

    @Test
    void authenticatedPostWithoutCsrfIsForbidden() throws Exception {
        mvc.perform(post("/profile").with(user(USER)))
            .andExpect(status().isForbidden());
    }

    @Test
    void authenticatedPostWithInvalidCsrfIsForbidden()
            throws Exception {
        mvc.perform(post("/profile")
                .with(user(USER))
                .with(csrf().useInvalidToken()))
            .andExpect(status().isForbidden());
    }

    @Test
    void authenticatedPostWithHeaderCsrfSucceeds()
            throws Exception {
        mvc.perform(post("/profile")
                .with(user(USER))
                .with(csrf().asHeader()))
            .andExpect(status().isOk())
            .andExpect(content().string("updated:learner"));
    }

    @Test
    void validCsrfAloneDoesNotAuthenticate() throws Exception {
        mvc.perform(post("/profile").with(csrf()))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login"));
    }

    @Test
    void logoutWithoutCsrfIsForbidden() throws Exception {
        mvc.perform(post("/logout").with(user(USER)))
            .andExpect(status().isForbidden());
    }

    @Test
    void logoutWithCsrfRedirectsAndInvalidatesSession()
            throws Exception {
        MvcResult loggedIn = login();
        MockHttpSession session =
            (MockHttpSession) loggedIn.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(post("/logout")
                .session(session)
                .with(csrf()))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?logout"));

        assertTrue(session.isInvalid());
    }
}
~~~

### 8.1. Specific meaning of the 14 test cases

| Test | What it proves |
| --- | --- |
| Public /health | Public path requires no login |
| GET /dashboard anonymous | Login entry point redirects to /login |
| GET /login | Generated form includes CSRF hidden input |
| POST /login right password missing CSRF | CSRF blocks before credentials are accepted |
| POST /login invalid token | Invalid token is rejected |
| POST /login valid CSRF, wrong password | Failure handler redirects to /login?error |
| Direct login valid | Redirects to /home and session retains authenticated context |
| Saved request login | Returns to dashboard and rotates session ID |
| Authenticated POST missing CSRF | Returns 403 |
| Authenticated POST invalid CSRF | Returns 403 |
| Authenticated POST with CSRF header | Controller executes, status 200 |
| Anonymous POST with CSRF | Still requires login; CSRF does not replace authentication |
| Logout POST missing CSRF | Returns 403 |
| Logout POST valid CSRF | Redirects to logout and session is invalidated |

The tests using `.with(user(USER))` **intentionally mock an authenticated principal only** to isolate endpoint CSRF behavior and do not prove the password provider ran. Only the direct-login and saved-request tests actually send `POST /login` with credentials through the Spring Security filter.

### 8.2. Running and expected output

In the Maven project directory:

~~~bash
mvn test
~~~

With Java 17+ and dependencies downloaded successfully, the suite contains **14 tests**. Expected summary output (Maven will print additional information):

~~~text
Tests run: 14, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
~~~

This is the **expected result** from the example configuration, not a captured execution log. When a real application has custom login URLs, custom handlers, or multiple chains, adjust assertions to the real policy rather than disabling CSRF just to make tests pass.

### 8.3. Spring Security Test helpers

In MockMvc:

~~~java
// CSRF parameter:
mvc.perform(post("/profile").with(csrf()));

// CSRF header:
mvc.perform(post("/profile").with(csrf().asHeader()));

// Invalid CSRF:
mvc.perform(post("/profile").with(csrf().useInvalidToken()));
~~~

Spring Security Test also provides `formLogin()` to build a login POST with a **valid CSRF**:

~~~java
// Test fragment; requires importing formLogin from SecurityMockMvcRequestBuilders:
mvc.perform(formLogin().user("learner").password("lab-password"));
~~~

**Do not use `formLogin()` to test missing CSRF**, because the helper adds the token automatically. When missing-CSRF testing is needed, use `post("/login")` with username/password **without** `.with(csrf())`.

## 9. Checking JSESSIONID and Set-Cookie over real HTTP

To test cookies at the HTTP level, start the application:

~~~bash
mvn spring-boot:run
~~~

Open DevTools → Network in your browser and select **Preserve log**. Then:

1. GET `http://localhost:8080/dashboard` while anonymous: verify 302 `Location: /login`.
2. The browser automatically GETs `/login`: verify 200 and the `_csrf` field.
3. Observe the pre-login session cookie, if any. It may be created for the saved request or to store a token; **having a cookie does not mean authenticated**.
4. Submit username `learner`, password `lab-password`: the POST request needs the cookie and valid CSRF token.
5. Observe the success 302; if there was a saved request `/dashboard`, `Location` returns to `/dashboard`, not necessarily `/home`.
6. Check that the session ID changed after login and the browser sends the new ID on the next request.
7. GET `/dashboard` must return 200. After logout with valid CSRF, the old cookie/session must no longer access protected endpoints.

### 9.1. Curl preserving cookies and inspecting intermediate redirects

Example run **in a lab environment**, without real credentials:

~~~bash
curl -i -c jar.txt http://localhost:8080/dashboard
curl -i -b jar.txt -c jar.txt http://localhost:8080/login
~~~

Read the **actual** `_csrf` value from the HTML of `GET /login` (do not hard-code a string), then POST with the same cookie jar:

~~~bash
curl -i -b jar.txt -c jar.txt \
  --data-urlencode "username=learner" \
  --data-urlencode "password=lab-password" \
  --data-urlencode "_csrf=TOKEN_FROM_FORM" \
  http://localhost:8080/login
~~~

`TOKEN_FROM_FORM` is a placeholder to replace with the real token extracted from the response, not a valid token. Finally:

~~~bash
curl -i -b jar.txt http://localhost:8080/dashboard
~~~

If login/CSRF/session are right, the response is typically 200 with body:

~~~text
dashboard:learner
~~~

`-c` saves cookies and `-b` sends cookies back. **Do not use `-L` when observing `Location`** because it follows redirects and can hide everything except the final status. On Windows PowerShell you can use `curl.exe`. The file `jar.txt` holds session credentials: never commit it to Git, never share it, and delete it safely after the lab.

### 9.2. Checking cookie flags at the public HTTPS ingress

Illustrative HTTP headers:

~~~http
HTTP/1.1 302 Found
Location: /home
Set-Cookie: JSESSIONID=REDACTED; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

**Do not claim** an HTTP localhost demo automatically provides adequate Secure/SameSite in every environment. In production, verify through the public HTTPS URL and reverse proxy:

- `HttpOnly` and `Secure` for the session cookie.
- `SameSite` per login/SSO needs; `SameSite=None` must be paired with `Secure`.
- `Path` and `Domain` cover only the required scope.
- No unexpected duplicate session cookies with the same name but different Path/Domain.
- Redirect `Location` does not leak internal server scheme/hostname.
- Trusted proxy chain handles `Forwarded`/`X-Forwarded-*`, never trusting arbitrary headers sent by Internet clients.

## 10. Testing SavedRequest, Location, and HTTP codes

### 10.1. Direct login vs. saved-request login

~~~text
A. Direct login
GET /login   -> 200 + CSRF
POST /login  -> 302 /home

B. Accessing protected resource first
GET /dashboard -> 302 /login; saved /dashboard
POST /login    -> 302 /dashboard
~~~

Each branch needs its own test. `SavedRequestAwareAuthenticationSuccessHandler` may return an absolute URL, query marker, or relative URL depending on configuration; assertions should check the meaningful destination rather than arbitrarily pinning the entire string when policy does not require it.

### 10.2. A 302 redirect on wrong password does not mean success

~~~text
POST login, right CSRF, wrong password -> 302 /login?error
POST login, right CSRF, right password -> 302 /home
GET dashboard, no authentication       -> 302 /login
~~~

If you only use `andExpect(status().is3xxRedirection())`, all three pass. You must check `redirectedUrl(...)` and **follow-up session access**.

### 10.3. Session timeout and stale CSRF

When a session expires, the expected CSRF token in the session is gone. A browser holding an old open form can submit a stale token and receive 403. UX can provide an expiration notice page and a way to refresh the session/CSRF. Never handle this by disabling CSRF.

### 10.4. Open redirects and external hosts

If an application reads a `returnUrl` query parameter and redirects without validation, attackers can abuse post-login redirects to send users to malicious domains. Use a controlled `RequestCache` or an allowlist of relative paths/trusted origins. Test external values, protocol-relative URLs, and odd encodings, disallowing arbitrary redirects.

### 10.5. Reverse proxies and multiple filter chains

When an internal HTTP backend sits behind a TLS ingress, `Location` URLs must point to the **public HTTPS host**; trusted forwarded-header policies must never accept forged data from the Internet.

If web form login and a REST Bearer JWT API share an app, matchers for each `SecurityFilterChain` must be precise: anonymous web requests typically 302 to `/login`, while API auth failures typically return 401 JSON/Bearer challenges. Test each path separately; do not force the API to 302 or let web routes bypass CSRF via an overly broad matcher.

## 11. Failure cases that must be tested

| Test | Expectation | Notes |
| --- | --- | --- |
| GET /dashboard anonymous | 302 /login | Entry point |
| GET /login | 200, form has CSRF | Do not pin token |
| POST /login missing CSRF | 403 | Even with right password |
| POST /login invalid CSRF | 403 | Not authenticated |
| POST /login valid CSRF/wrong password | 302 /login?error | FailureHandler |
| POST /login both valid | 302 success target | Check Location |
| Login after protected GET | 302 saved URL | RequestCache |
| Post-login request with same session | 200 | Context persisted |
| Session ID before/after login | Changed | Session fixation |
| POST profile authenticated, missing CSRF | 403 | CsrfFilter |
| POST profile with CSRF but anonymous | 302 /login | CSRF is not auth |
| POST profile valid CSRF + authenticated | 200 | Authorization and CSRF |
| POST logout missing CSRF | 403 | Logout CSRF protection |
| POST logout valid | Redirect, invalid session | Check subsequent request |
| Cookie on public HTTPS | Right Secure/HttpOnly/SameSite | Container/gateway test |
| Cookie after logout | No longer grants access | E2E cookie jar |
| CSRF token from another session | Rejected | Reject cross-session |
| SPA using stale token after login | Rejected, fetches new token | Rotation/deferred tokens |
| Redirect to external domain | Rejected | Prevents open redirect |
| Reverse proxy | Location matches public host | Does not leak internal host |

## 12. Common implementation mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| POST login returns 403 despite right password | Missing/invalid CSRF | Include token, keep matching session |
| Using `formLogin()` to test missing token | Helper adds CSRF automatically | Raw POST |
| Using `@WithMockUser` to test login | Mock principal skips credentials | Send real login POST |
| Protected GET returns 302 instead of 401 | Form login entry point | Check Location `/login` |
| Bad password returns 302 instead of 401 | FailureHandler redirect | Check `/login?error` |
| MockMvc lacks Set-Cookie | Mock container does not emit real HTTP cookies | Test over HTTP/embedded Tomcat |
| Session not preserved across test requests | Forgot to pass MockHttpSession | Use `.session(session)` |
| Valid login does not return to intended URL | Saved request vs. default target differ | Test both branches separately |
| Stale SPA token gets 403 after login | CSRF rotation/XOR/deferred | Refresh token and handler |
| POST logout 403 | Missing CSRF | Send valid token |
| JS can read JSESSIONID | HttpOnly disabled | Enable HttpOnly on session cookie |
| Cookie lacks Secure over HTTPS | Wrong proxy/config | Check public ingress headers |
| Misconfigured cookie SameSite | Incompatible with login/cross-site | Set policy per threat model |
| Valid cookie yet keeps redirecting to login | Inconsistent session store, wrong cookie path | Check persistence/HA |
| Redirects to internal hostname | Misconfigured forwarded headers | Trusted proxy headers |
| Tests pass when CSRF is disabled | Assertions lack negative tests | Missing/invalid tests |

### 12.1. Two anti-patterns to avoid

~~~java
// ANTI-PATTERN: do not disable CSRF just to stop POST /login from returning 403.
http.csrf(csrf -> csrf.disable());

// ANTI-PATTERN: do not disable session fixation protection
// just to keep the session ID "stable" in a test.
http.sessionManagement(session ->
    session.sessionFixation(fixation -> fixation.none()));
~~~

These are two intentionally wrong fragments, **not recommended configurations**. Truly stateless APIs may have a different CSRF model depending on credential/cookie mechanisms; never conclude simply that "REST does not need CSRF".

## 13. Pre-handoff checklist

**CSRF**

- [ ] GET login form renders the token properly and never leaks tokens into logs/URLs.
- [ ] POST login missing/invalid token returns 403; valid token still verifies password.
- [ ] POST logout and state mutations are protected by CSRF.
- [ ] Deferred/XOR/BREACH handled properly in Spring Security 6.
- [ ] SPA/cookie tokens are refreshed after login/logout when needed.

**Session**

- [ ] Successful login creates an authenticated session and follow-up requests access protected resources.
- [ ] Session fixation protection rotates the ID; failed login grants no context.
- [ ] Logout invalidates the session; old cookies grant no access.
- [ ] Session timeout, multi-instance store, and cookie flags/paths are tested.
- [ ] HttpOnly/Secure/SameSite cookies are accurate over public HTTPS.

**Redirect**

- [ ] Anonymous protected GET goes to `/login` per policy.
- [ ] Wrong password goes to `/login?error`, never mistaken for success.
- [ ] Direct success goes to the default target.
- [ ] Saved-request success returns to the original URL.
- [ ] No open redirects to unknown origins.
- [ ] Public reverse-proxy redirects do not leak internal hosts.

**Test quality**

- [ ] Unit/MockMvc and HTTP/browser tests are clearly separated.
- [ ] Real credential tests go through filters, not only `@WithMockUser`.
- [ ] No real session cookies/passwords/tokens appear in test reports.
- [ ] Negative tests exist to prove security, not just happy paths.

## 14. Self-check questions

1. Why does `POST /login` also need CSRF in session-based form login?
2. How do `JSESSIONID`, `XSRF-TOKEN`, and `_csrf` differ?
3. Why can a login with the right password still receive 403?
4. Why does a wrong password typically 302 to `/login?error` instead of 401?
5. What must a MockMvc test pass to reuse a session?
6. Why is MockMvc insufficient to prove `Set-Cookie` Secure/HttpOnly?
7. What does session fixation protection do to the session ID?
8. Which URL does `SavedRequestAwareAuthenticationSuccessHandler` pick when a saved request exists?
9. Can the `formLogin()` helper test missing CSRF?
10. Does `@WithMockUser` actually run `DaoAuthenticationProvider`?
11. Why can asserting only HTTP 302 miss login bugs?
12. Why can the CSRF token change after login/logout?
13. What must an SPA using `CookieCsrfTokenRepository` in Security 6 keep in mind?
14. Why is mutating state on HTTP GET a design flaw?
15. Does SameSite replace all CSRF protection?
16. If an old cookie can still view `/dashboard` after logout, which test was missing?
17. If a redirect points to an internal-http hostname behind a proxy, what should be checked?
18. Should a Bearer API and web form login share identical 401/302 expectations?

**Conclusion:** an adequate login test suite does not stop at "POST login returns 302"; it must prove **valid CSRF tokens**, **session persistence and fixation protection**, **redirects to the right target per saved-request/success/failure policy**, and then use **the cookie/session in follow-up requests** to verify authentication. MockMvc tests filter logic; HTTP/browser E2E tests verify `Set-Cookie`, cookie flags, redirects over public ingress, and real browser behavior.

## 15. Official documentation

- [Spring Security 6.5 — Testing with CSRF Protection](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/csrf.html)
- [Spring Security 6.5 — Testing Form-Based Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/form-login.html)
- [Spring Security 6.5 — CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html)
- [Spring Security 6.5 — Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html)
- [Spring Security 6.5 — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html)
- [Spring Security 6.5 — SavedRequestAwareAuthenticationSuccessHandler](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/SavedRequestAwareAuthenticationSuccessHandler.html)
- [Spring Security 6.5 — MockMvc Setup](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/setup.html)
- [OWASP — CSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
