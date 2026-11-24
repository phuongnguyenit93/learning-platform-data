# formLogin, httpBasic, and logout in Servlet Testing

In a **Spring Security Servlet** application, testing login is not just putting a mock `Authentication` into a test and expecting the endpoint to return HTTP 200. To genuinely prove the login mechanism, a test must actually run the **Spring Security Filter Chain**, send the right **HTTP request** through the corresponding filter, verify the **authentication result and access permissions**, and check **CSRF, session, and logout**.

The `spring-security-test` toolkit provides three very useful helpers for `MockMvc`:

- **`formLogin()`**: creates a form-login **POST** with a valid CSRF token, allowing you to set username/password or change the URL and parameter names.
- **`httpBasic(username, password)`**: a `RequestPostProcessor` that adds an `Authorization: Basic ...` header to a single request; it does **not** create a form-login session.
- **`logout()`**: creates a logout **POST** with a CSRF token; used to test `LogoutFilter` and the configured URL/logout handlers.

This lesson belongs to the **Login Testing** group and uses **Java 17+, Spring Boot 3.5.x, Spring Security 6.5.x**, JUnit Jupiter, and `MockMvc`. The content covers flow explanations, a complete Spring Boot example, valid and failure test cases, reusing sessions across multiple requests, distinguishing HTTP 401/403/302, CSRF testing, real logout, and common mistakes when only mocking users.

## 1. Testing goal: are you testing filters or only authorization?

The first question before writing a test is: **what do I want to verify?**

| Purpose | Appropriate tool | Which layer is tested? |
| --- | --- | --- |
| Does the controller return the right data for a user with role `USER`? | `@WithMockUser` or `with(user("..."))` | Mainly authorization and controller; **skips real password verification** |
| Does form login verify correct/incorrect username/password? | `mvc.perform(formLogin().user(...).password(...))` | `UsernamePasswordAuthenticationFilter` → `AuthenticationManager` → provider, CSRF, and handlers |
| Does the API accept real Basic Auth? | `mvc.perform(get(...).with(httpBasic(...)))` | `BasicAuthenticationFilter`/provider, HTTP status, and permissions |
| Does POST logout with CSRF work properly? | `mvc.perform(logout())` | `LogoutFilter`, logout handlers, and configured redirect |
| Does logout **invalidate the logged-in session**? | Create a session via `formLogin()`, then `post("/logout").session(session).with(csrf())` | Session/context invalidation mechanism and subsequent request |
| Does CSRF protection work? | `post("/login")`/`post("/logout")` **without** `with(csrf())` | `CsrfFilter` rejects unsafe requests |
| Does a browser receive cookies, follow redirects, and keep sessions across replicas? | E2E/browser or real HTTP integration tests | Beyond `MockMvc` scope; requires production-like infrastructure |

**Do not equate** `with(user("student"))` with `formLogin().user("student")`. In the first approach, Spring Security Test **pre-populates an already-authenticated principal**; in the second, the system must **verify the real password** against the configured `UserDetailsService`/`PasswordEncoder`.

Similarly, `httpBasic(...)` only adds a header for a single request; HTTP Basic is normally a **per-request** authentication mechanism and does not mean it has created a login session like form login. To test password hashing or the Basic Authentication Entry Point, you must send a real request through the filter chain.

## 2. Components and requests in Servlet

~~~text
Browser/HTTP test
       │
       ▼
MockMvc + Spring Security FilterChainProxy
       │
       ├── POST /login + CSRF, username/password
       │       │
       │       ▼
       │   UsernamePasswordAuthenticationFilter
       │       │
       │       ▼
       │   AuthenticationManager → AuthenticationProvider
       │       ├─ success → SecurityContext/session → success handler
       │       │                                      └─ redirect (usually 302)
       │       └─ failure → failure handler (usually /login?error)
       │
       ├── GET /api/me + Authorization: Basic <Base64>
       │       │
       │       ▼
       │   BasicAuthenticationFilter
       │       ├─ valid   → Authentication for request → controller/authorization
       │       └─ invalid → AuthenticationEntryPoint (usually HTTP 401)
       │
       └── POST /logout + CSRF
               │
               ▼
           LogoutFilter
               ├─ clear SecurityContext, invalidate session
               ├─ cleanup remember-me/CSRF (per config)
               └─ logout success handler (usually /login?logout)
~~~

The **actual order** of filters and error-handling points depends on the `SecurityFilterChain`, enabled authentication mechanisms, and Spring Security version. In the example, both form login and HTTP Basic use the **same `UserDetailsService` and `PasswordEncoder`**, yet they are two distinct HTTP entry points.

### 2.1. POST login differs from GET login page

- `GET /login`: usually renders the input page with a form containing a CSRF token. It **does not perform authentication by itself**.
- `POST /login`: by default, the URL handled by `UsernamePasswordAuthenticationFilter`, reading the `username` and `password` parameters.
- When the password is correct: Spring Security form login typically issues a redirect, not necessarily returning HTTP 200 directly on the POST.
- When wrong: typically redirects to `/login?error`, **not HTTP 401**, unless the application customizes the failure handler.
- If CSRF is missing: `CsrfFilter` typically returns HTTP 403 **before** username/password are verified.

### 2.2. HTTP Basic differs from session login

With HTTP Basic, the request sends:

~~~http
GET /api/me HTTP/1.1
Host: localhost:8080
Accept: application/json
Authorization: Basic <base64-of-username-colon-password>
~~~

Base64 is only **encoding**, not security encryption. **HTTPS is mandatory in production**. Basic headers in tests must be built from test data; do not write raw credentials/headers to logs. A valid Basic request can return 200 if the user is authorized; a subsequent request **without the Basic header** does not automatically have that authentication. Do not assume HTTP Basic creates a session.

### 2.3. Logout differs from "deleting a cookie on the client"

Spring Security Servlet logout typically involves `LogoutFilter`, `SecurityContextLogoutHandler`, and other logout handlers. When CSRF is enabled, **POST /logout with a CSRF token** is the actual logout action; `GET /logout` by default usually displays a confirmation page instead of logging out immediately.

The server redirecting to `/login?logout` is only one piece of evidence. You must verify that **the session is invalidated**, `SecurityContext` is cleared, and **subsequent requests** are no longer considered logged in. If Basic credentials are sent again in the next request, the system can authenticate anew normally; logout does not erase credentials on the client.

## 3. Dependencies and static imports to know

### 3.1. Gradle dependencies

Snippet to place in `build.gradle` (Groovy DSL) of a Spring Boot project **with plugins and Java 17+ already declared**:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

If using Maven, you correspondingly need `spring-boot-starter-web`, `spring-boot-starter-security`, `spring-boot-starter-test` (test scope), and `spring-security-test` (test scope), letting the Spring Boot BOM manage versions. Do not mix Spring Security test 6.5 with runtime security 6.3 and expect the API to behave identically.

In Spring Boot 3.5, `@AutoConfigureMockMvc` configures `MockMvc` for integration tests and normally registers the application's filter chain when the security dependency is present; check whether the project **disables filters** via `addFilters=false` or uses a standalone setup without Security.

### 3.2. Standard static imports

~~~java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestBuilders.logout;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.response
        .SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.security.test.web.servlet.response
        .SecurityMockMvcResultMatchers.unauthenticated;
~~~

**Java note:** line-breaking with the dot **at the beginning of the line** in imports as shown is valid Java syntax (whitespace between tokens); however, for easier copying and reading, write each import on **a single line** in the complete test file below.

These static imports are not in the same package:
- `formLogin` and `logout` belong to **`SecurityMockMvcRequestBuilders`**.
- `httpBasic` and `csrf` belong to **`SecurityMockMvcRequestPostProcessors`**.
- `authenticated` and `unauthenticated` belong to **`SecurityMockMvcResultMatchers`**.

This is a common import mistake. Do not look for `SecurityMockMvcRequestBuilders.httpBasic`; the `httpBasic` helper is used with `with(...)` on a regular request builder.

## 4. Building a runnable Spring Boot sample application

The example uses a small Spring MVC application with two **lab-only** accounts:

| User | Test password | Authorities |
| --- | --- | --- |
| `student` | `student-lab-pass` | `ROLE_USER` |
| `admin` | `admin-lab-pass` | `ROLE_ADMIN` |

Never use these passwords for any real account. They are fixed **solely for deterministic testing**; production must use properly managed secrets, accounts in a database/IdP, HTTPS, and password policies per organizational standards. Passwords stored in `InMemoryUserDetailsManager` are BCrypt-encoded, not plaintext in the user store.

### 4.1. Application file

Create `src/main/java/example/servlettest/ServletAuthDemoApplication.java`:

~~~java
package example.servlettest;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ServletAuthDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ServletAuthDemoApplication.class, args);
    }
}
~~~

### 4.2. SecurityFilterChain, user store, and endpoints

Create `src/main/java/example/servlettest/DemoSecurityConfig.java`:

~~~java
package example.servlettest;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
public class DemoSecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService labUsers(PasswordEncoder encoder) {
        UserDetails student = User.withUsername("student")
                .password(encoder.encode("student-lab-pass"))
                .roles("USER")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("admin-lab-pass"))
                .roles("ADMIN")
                .build();

        return new InMemoryUserDetailsManager(student, admin);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/admin").hasRole("ADMIN")
                .anyRequest().authenticated());

        http.formLogin(form -> form
                .defaultSuccessUrl("/private", true)
                .permitAll());

        http.httpBasic(Customizer.withDefaults());
        http.logout(Customizer.withDefaults());

        // CSRF kept at default: POST /login and POST /logout require a token.
        return http.build();
    }
}
~~~

Create `src/main/java/example/servlettest/DemoEndpoints.java`:

~~~java
package example.servlettest;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoEndpoints {

    @GetMapping("/public")
    String publicPage() {
        return "public";
    }

    @GetMapping("/private")
    String privatePage(Authentication authentication) {
        return "private:" + authentication.getName();
    }

    @GetMapping("/api/me")
    String currentUser(Authentication authentication) {
        return "me:" + authentication.getName();
    }

    @GetMapping("/admin")
    String admin() {
        return "admin-only";
    }
}
~~~

**Configuration explanation:**

1. `/public` is accessible to anonymous users; `/private` and `/api/me` require authentication; `/admin` requires `ROLE_ADMIN`.
2. `formLogin` provides the default login page and handles POST `/login`; `defaultSuccessUrl("/private", true)` forces a redirect to `/private` after successful login, giving clear expectations for tests.
3. `httpBasic` lets the same accounts authenticate with a Basic header on matching requests. If an HTTP Basic request has the wrong password, `BasicAuthenticationFilter` typically returns 401.
4. `logout` uses default configuration, including POST `/logout` with CSRF, invalidating the session, clearing `SecurityContext`, and redirecting to `/login?logout`.
5. Neither CSRF is disabled nor `SessionCreationPolicy.STATELESS` is used, because this lesson needs to test real form sessions.
6. The code declares no controller for `POST /login` or `POST /logout`: those URLs are handled by **Spring Security filters** before reaching any controller.
7. In production, configuring both HTTP Basic and form login across all URLs requires careful evaluation of accepted schemes/Accept headers; the demo enables both for comparison.
8. Both form login and HTTP Basic use `DaoAuthenticationProvider`/`PasswordEncoder` in standard configuration. Because this is a sample, it has no password reset, MFA, account lock, rate limiting, or JDBC identity storage.

When running with JDK 17 and the Gradle wrapper, use:

~~~bash
./gradlew bootRun
~~~

On Windows use `gradlew.bat bootRun`. A browser can open `http://localhost:8080/login` to view the demo form, but **never send real passwords over HTTP outside localhost**; production systems must use HTTPS.

## 5. Integration test file: formLogin + httpBasic + logout

Create `src/test/java/example/servlettest/ServletAuthenticationFlowTest.java`. The entire file below is a **JUnit Jupiter + Spring Boot + MockMvc** test class running the `ServletAuthDemoApplication` declared above with lab data.

~~~java
package example.servlettest;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestBuilders.logout;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.unauthenticated;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class ServletAuthenticationFlowTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicPageDoesNotRequireAuthentication() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void anonymousUserIsRedirectedToLoginPage() throws Exception {
        mvc.perform(get("/private").accept(MediaType.TEXT_HTML))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrlPattern("**/login"));
    }

    @Test
    void formLoginAcceptsCorrectPasswordAndPersistsSession()
            throws Exception {

        MvcResult loginResult = mvc.perform(formLogin()
                .user("student")
                .password("student-lab-pass"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/private"))
            .andExpect(authenticated().withUsername("student"))
            .andReturn();

        MockHttpSession session = (MockHttpSession)
                loginResult.getRequest().getSession(false);
        assertNotNull(session);

        // This is a separate request, without username/password.
        mvc.perform(get("/private").session(session))
            .andExpect(status().isOk())
            .andExpect(authenticated().withUsername("student"))
            .andExpect(content().string("private:student"));
    }

    @Test
    void formLoginRejectsWrongPassword() throws Exception {
        mvc.perform(formLogin()
                .user("student")
                .password("incorrect"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?error"))
            .andExpect(unauthenticated());
    }

    @Test
    void rawFormPostWithoutCsrfIsForbidden() throws Exception {
        mvc.perform(post("/login")
                .param("username", "student")
                .param("password", "student-lab-pass"))
            .andExpect(status().isForbidden());
    }

    @Test
    void httpBasicAcceptsCorrectCredentialsPerRequest()
            throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("student", "student-lab-pass"))
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(authenticated().withUsername("student"))
            .andExpect(content().string("me:student"));
    }

    @Test
    void httpBasicRejectsIncorrectPassword() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("student", "incorrect"))
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isUnauthorized())
            .andExpect(unauthenticated());
    }

    @Test
    void authenticatedStudentCannotAccessAdminPage()
            throws Exception {
        mvc.perform(get("/admin")
                .with(httpBasic("student", "student-lab-pass"))
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminRoleCanAccessAdminPage() throws Exception {
        mvc.perform(get("/admin")
                .with(httpBasic("admin", "admin-lab-pass"))
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(content().string("admin-only"));
    }

    @Test
    void logoutHelperBuildsPostWithValidCsrf()
            throws Exception {
        // logout() adds CSRF automatically, even without a logged-in user.
        mvc.perform(logout())
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?logout"));
    }

    @Test
    void logoutInvalidatesActualLoggedInSession()
            throws Exception {
        MvcResult login = mvc.perform(formLogin()
                .user("student")
                .password("student-lab-pass"))
            .andExpect(authenticated())
            .andReturn();

        MockHttpSession session = (MockHttpSession)
                login.getRequest().getSession(false);
        assertNotNull(session);
        assertFalse(session.isInvalid());

        mvc.perform(get("/private").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("private:student"));

        // Here we use post(...).session(...).with(csrf())
        // to attach THAT exact logged-in session to logout.
        mvc.perform(post("/logout")
                .session(session)
                .with(csrf()))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?logout"))
            .andExpect(unauthenticated());

        // Verify the server invalidated that exact session.
        assertTrue(session.isInvalid());

        // Do not reuse an invalidated MockHttpSession in a
        // RequestBuilder; like a browser, send a new request without a
        // valid cookie/session and verify login is required.
        mvc.perform(get("/private").accept(MediaType.TEXT_HTML))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void logoutWithoutCsrfDoesNotInvalidateSession()
            throws Exception {
        MvcResult login = mvc.perform(formLogin()
                .user("student")
                .password("student-lab-pass"))
            .andExpect(authenticated())
            .andReturn();

        MockHttpSession session = (MockHttpSession)
                login.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(post("/logout").session(session))
            .andExpect(status().isForbidden());

        assertFalse(session.isInvalid());
        mvc.perform(get("/private").session(session))
            .andExpect(status().isOk());
    }
}
~~~

This is a **Security Filter Chain integration** example (not just a controller unit test), with **12 `@Test` methods** covering key scenarios: anonymous, successful/failed form login, CSRF, successful/failed Basic, 403 authorization, logout, and session invalidation.

Run with Gradle (when the project has the Gradle wrapper):

~~~bash
./gradlew test --tests example.servlettest.ServletAuthenticationFlowTest
~~~

With the dependencies and configuration above, **12 tests are expected to pass**. Logger names, timestamps, or Gradle output may vary by project; never claim a build passes without actually running it in a matching project. This test suite requires no Internet, database, email, JWT issuer, or real browser.

## 6. formLogin(): understanding precisely what this helper does

`formLogin()` from `SecurityMockMvcRequestBuilders`:

- Generates `POST /login` by default.
- Sets the `username` and `password` parameters (helper defaults are `user/password` unless changed).
- Adds a valid CSRF token so the request is not rejected upfront by `CsrfFilter`.
- Allows customizing the login processing URL and parameter names.

Default example:

~~~java
mvc.perform(formLogin()
        .user("student")
        .password("student-lab-pass"))
    .andExpect(authenticated().withUsername("student"));
~~~

The call above **differs from**:

~~~java
mvc.perform(get("/private")
        .with(user("student").roles("USER")))
    .andExpect(status().isOk());
~~~

The second snippet requires importing `SecurityMockMvcRequestPostProcessors.user`. It pre-populates an authenticated test principal and **does not** verify a password, does not create `POST /login`, and does not necessarily run handlers/session strategies like real login. Use it only to test authorization when verifying the authentication algorithm is unnecessary.

### 6.1. Changing the login URL and parameter names

If the application configures:

~~~java
http.formLogin(form -> form
        .loginProcessingUrl("/session/login")
        .usernameParameter("loginName")
        .passwordParameter("secretValue")
        .defaultSuccessUrl("/private", true)
        .permitAll());
~~~

Then the test must also change accordingly:

~~~java
mvc.perform(formLogin("/session/login")
        .user("loginName", "student")
        .password("secretValue", "student-lab-pass"))
    .andExpect(authenticated().withUsername("student"));
~~~

These are **two snippets in different locations**: the config snippet belongs in the `SecurityFilterChain` bean, while the test snippet belongs in a test method with `MockMvc mvc`. **Do not drop this into the section 4 demo file without updating the default tests**, because differing URLs/parameters will prevent the filter from matching properly.

### 6.2. CSRF and misleading results

| Test request | CSRF | Typical result |
| --- | --- | --- |
| `mvc.perform(formLogin())` | **Added by the helper** | Proceeds to authentication; pass/fail depends on credentials |
| `mvc.perform(post("/login"))` | **Missing** | 403 from CSRF before checking password |
| `mvc.perform(post("/login").with(csrf()))` | Valid | Proceeds to the username/password filter |
| `mvc.perform(post("/login").with(csrf().useInvalidToken()))` | Invalid | 403 |
| `GET /login` | No token needed to *read the page*, but the form must submit CSRF on POST | Returns login page/redirect per config |

Seeing HTTP 403 when sending a login POST without CSRF **does not mean** the password was verified as wrong. Seeing a redirect to `/login?error` with valid CSRF is typically the login failure handler; distinguish these two categories in tests.

### 6.3. Mind the builder's syntax

`SecurityMockMvcRequestBuilders.FormLoginRequestBuilder` implements `RequestBuilder` and has `.user(...)`, `.password(...)`, and `.acceptMediaType(...)`; it is **not** a `MockHttpServletRequestBuilder` with all `.session(...)` and `.with(...)` methods like `get(...)`/`post(...)`.

If you want to control the session or add a custom `RequestPostProcessor`, you can use `post("/login").session(session).with(csrf()).param(...)`, keeping in mind that this request enters the same filter chain and is subject to real session/CSRF policies. **Do not blindly call `formLogin().session(...)` if your version's builder API lacks that method.**

## 7. httpBasic(): Basic Auth is a per-request header

The right helper is:

~~~java
mvc.perform(get("/api/me")
        .with(httpBasic("student", "student-lab-pass")))
    .andExpect(status().isOk())
    .andExpect(content().string("me:student"));
~~~

It creates the `Authorization: Basic ...` header corresponding to the supplied username/password pair and Base64-encodes it in Basic Auth format. Its purpose is to **avoid writing the header by hand and reduce formatting errors**, not to mock authentication.

### 7.1. Expecting 401, 403, 200

| Scenario | Typical result | Why |
| --- | --- | --- |
| Basic username/password correct, endpoint requires authenticated | **200** | Provider authenticates, controller runs |
| Basic password wrong | **401**; usually includes `WWW-Authenticate: Basic ...` | Authentication failure, Basic entry point |
| Basic valid but missing role for endpoint | **403** | Authentication succeeds but authorization denies |
| Basic header omitted | Can be **401 or redirect to /login** | Depends on the chain's entry point, Accept header, and whether form login is also enabled |
| Basic header sent but `httpBasic` not configured on the matched chain | Basic handling not guaranteed | A header does not enable the filter by itself |
| Basic valid, next request omits header | Does not automatically create a new session | Default Basic typically authenticates per request |

### 7.2. Why Basic cannot replace formLogin

- `formLogin()` tests the POST flow, CSRF, form success/failure handlers, session fixation, and saving the SecurityContext.
- `httpBasic(...)` tests the HTTP header, 401/challenge status, and authorization for that request.
- An endpoint can enable **both**, with client negotiation/entry point chosen per request.
- Logging out of a form session does not prevent a valid Basic header from **continuing to authenticate on subsequent requests**; revoking Basic requires changing credentials, locking the account, or changing the authentication policy.
- Do not log or snapshot raw Basic headers in tests: Base64 username/password can be decoded immediately.

### 7.3. Testing with curl on localhost only

With the demo app running locally:

~~~bash
curl -i -u student:student-lab-pass \
  -H "Accept: application/json" \
  http://localhost:8080/api/me
~~~

Expected body:

~~~text
me:student
~~~

The `-u` flag makes curl send Basic credentials. When working with real credentials, avoid placing them directly in shell history/process arguments; use proper secrets management. Never send Basic Auth over public HTTP; use HTTPS only in real environments.

### 7.4. User mocking does not prove Basic works

The following two tests check different things:

~~~java
// Tests controller Authorization; does not verify Basic password.
mvc.perform(get("/api/me").with(user("student").roles("USER")))
    .andExpect(status().isOk());

// Actually feeds a Basic header into the Security filter.
mvc.perform(get("/api/me")
        .with(httpBasic("student", "student-lab-pass")))
    .andExpect(status().isOk());
~~~

A mock user test can pass even if `httpBasic` is not enabled. Therefore, when required to prove Basic Authentication works, test with `httpBasic(...)` and include a **negative case** for a wrong password.

## 8. logout(): helper, session, CSRF, and what results mean

Spring Security enables `LogoutFilter` by default in the servlet security chain. With CSRF enabled:

- `GET /logout` usually shows a confirmation page and **does not** perform the logout action itself.
- `POST /logout` with a valid CSRF token is the logout command.
- The `logout()` helper creates the right baseline request.
- Default logout invalidates `HttpSession`, clears `SecurityContext`, handles related remember-me/CSRF cleanup, and redirects to `/login?logout`.

### 8.1. Testing the logout helper

~~~java
mvc.perform(logout())
    .andExpect(status().is3xxRedirection())
    .andExpect(redirectedUrl("/login?logout"));
~~~

**Limitation:** calling it as above without attaching a logged-in session mainly proves **the endpoint accepts the request and produces a redirect**. It does not confirm a prior user's session was destroyed. An integration case like `logoutInvalidatesActualLoggedInSession()` in the section 5 test file is needed.

### 8.2. Testing logout of the actual session

Procedure:

1. `formLogin()` with the right password.
2. Extract `MockHttpSession` from `MvcResult`.
3. Call a protected endpoint with `.session(session)` to confirm it actually works.
4. `post("/logout").session(session).with(csrf())`.
5. Assert the redirect and `session.isInvalid() == true`.
6. Call a protected endpoint with a **new request without a valid session**; it must require authentication.

Core code inside the test method:

~~~java
MockHttpSession session = (MockHttpSession)
        loginResult.getRequest().getSession(false);

mvc.perform(post("/logout").session(session).with(csrf()))
    .andExpect(redirectedUrl("/login?logout"));

assertTrue(session.isInvalid());
~~~

Note that `loginResult` comes from an earlier successful form-login request; the snippet above is **not a standalone test method**. With a real browser, cookie invalidation/expiration has container-specific behavior. With `MockMvc`, an invalidated `MockHttpSession` object should not be reused as a valid session.

### 8.3. CSRF with logout

~~~java
mvc.perform(post("/logout"))
    .andExpect(status().isForbidden());

mvc.perform(post("/logout").with(csrf()))
    .andExpect(redirectedUrl("/login?logout"));
~~~

Both requests above have no authenticated session attached and are used to test how the router/filter handles CSRF and the logout endpoint. When testing a session, **attach the actual session** and verify invalidation rather than inferring from a standalone redirect.

**Do not disable CSRF app-wide** just to let POST logout run. CSRF protection prevents an external site from forcing a victim's browser to log out or perform other state-changing requests.

### 8.4. Custom URL

When the application uses:

~~~java
http.logout(logout -> logout
        .logoutUrl("/session/logout")
        .logoutSuccessUrl("/goodbye"));
~~~

The test helper can use:

~~~java
mvc.perform(logout("/session/logout"))
    .andExpect(redirectedUrl("/goodbye"));
~~~

Condition: `/goodbye` must be permitted for anonymous access if the browser is redirected there after logout; you can use `logout.permitAll()` or an appropriate rule. These two snippets are **alternative configurations** to the default demo and must not be pasted in without updating test expectations.

### 8.5. Session logout differs from revoking other token types

| Credential/state | After default `LogoutFilter` |
| --- | --- |
| Current HTTP session | Usually invalidated, Spring Security context cleared |
| CSRF token tied to session | May be cleared/rotated depending on logout handlers |
| Remember-me cookie | Cleaned up if enabled and a handler is configured |
| **HTTP Basic password** | Not changed or revoked by logout |
| **JWT Bearer access token** | Not invalidated merely by servlet session logout |
| Refresh token/OAuth2 grant at IdP | May require separate revocation/logout |
| Session in another system (SSO) | May require separate federated/OIDC logout |

When testing "complete logout", define whether **local logout or system-wide logout is being tested**. A 302 `/login?logout` does not prove an external JWT has been revoked.

## 9. Why can MockMvc tests produce misleading results?

### 9.1. Security filters not running

With `MockMvcBuilders.standaloneSetup(controller)` by default, you may not have `FilterChainProxy`. Result: the controller is invoked even when unauthenticated, or `formLogin()` sends a POST with no filter handling it as in the real project.

When building `MockMvc` manually for a WebApplicationContext:

~~~java
MockMvc mvc = MockMvcBuilders
        .webAppContextSetup(context)
        .apply(springSecurity())
        .build();
~~~

This snippet requires importing `MockMvcBuilders` and static-importing `springSecurity` from `SecurityMockMvcConfigurers`, placed in a setup method with `WebApplicationContext context`. In the `@SpringBootTest + @AutoConfigureMockMvc` example, Boot configures `MockMvc`, so manual setup is unnecessary.

### 9.2. Using @WithMockUser to test passwords

~~~java
@Test
@WithMockUser(username = "student", roles = "USER")
void mockUserCanSeeProtectedPage() throws Exception {
    mvc.perform(get("/private"))
        .andExpect(status().isOk());
}
~~~

This test is valuable for testing authorization; **it does not prove real passwords are validated**. It can pass even if `PasswordEncoder` is wrong or `UserDetailsService` throws an error. To test login, build a real POST with `formLogin()`; to test Basic, use `httpBasic(...)`.

### 9.3. Confusing HTTP status with authentication result

A test with only `.andExpect(status().isOk())` is insufficient. The `/public` endpoint is always 200 and does not prove authentication.

Suggested combined checks:

~~~java
mvc.perform(formLogin().user("student").password("student-lab-pass"))
    .andExpect(authenticated().withUsername("student"))
    .andExpect(redirectedUrl("/private"));
~~~

With Basic, also check body/principal or roles. With logout, check **invalidation/session**. Note that a 403 controller response after Basic can be an **authorization failure** rather than a credential failure.

### 9.4. Using session cookies incorrectly

A common mistake is taking `MockHttpSession` from a **different** request or creating a fresh `new MockHttpSession()` before the follow-up, then concluding the session was not saved. Take the session from the exact `MvcResult` of the POST login, then pass it to the second request with `.session(session)`.

Conversely, **do not share the same session across all tests** when tests should be independent. The examples above create a new session per method without storing a global static session, preventing cross-test interference.

### 9.5. Confusing CSRF 403 errors with authorization 403 errors

There are at least two causes of 403:

- `CsrfFilter` rejects `POST /login` or `POST /logout` missing CSRF.
- `AuthorizationFilter` rejects an authenticated user lacking `ROLE_ADMIN`.

If a test simply asserts "got 403 so security is good", it does not prove **the intended rule** works. Send valid CSRF in authorization tests for unsafe methods and distinguish response paths/events.

### 9.6. HTTP Basic and the Accept header

When both `formLogin` and `httpBasic` are enabled, Spring Security chooses the authentication entry point matching the request type and configuration. For requests missing credentials, an HTML browser typically redirects to login, while an API accepting JSON/Basic may receive a 401 challenge. That is why tests must specify the **Accept header** and expected result according to the chain. Never claim every anonymous GET is always 401 or every API GET always redirects.

### 9.7. Password hashing and the mock user store

In the `InMemoryUserDetailsManager` example, passwords are BCrypt-encoded before storage. If a test uses a different raw password, `DaoAuthenticationProvider` must reject it. If you try using `{noop}` to "make tests easier", tests may diverge from production, miss `PasswordEncoder` interaction bugs, and encourage dangerous habits when copying configuration.

Using fixed lab data in test sources is acceptable **if** those are not real credentials and are never reused in other environments. Never log failed passwords or Basic headers in CI.

## 10. Advanced authorization, session fixation, and concurrency testing

### 10.1. Logging in does not grant all permissions

Form login and Basic only verify identity. User `student` with `ROLE_USER` is still denied at `/admin`. The test suite should include:

- Valid credentials + right permission → 200.
- Valid credentials + missing permission → 403.
- Wrong credentials → authentication failure.
- No credentials → login redirect/401 depending on entry point.

This cleanly separates **authentication** from **authorization**.

### 10.2. Session fixation

Spring Security protects against session fixation by default by changing the session ID or creating a new session depending on servlet container/version. You can test:

1. Create a `MockHttpSession` before login and store a benign attribute.
2. `post("/login").session(preSession).with(csrf())` with username/password params.
3. Inspect `MockHttpSession#getId()` before/after (it may be the same Java object with a changed ID).
4. Verify the security context is properly saved and the pre-login ID is not reused per policy.

**Do not blindly use `formLogin().session(...)`**; the `formLogin` builder lacks a `session(MockHttpSession)` API like `MockHttpServletRequestBuilder`. To test session fixation, use raw `post` + `with(csrf())`. This case should be cross-checked against the mock container's `changeSessionId` and specific strategy.

### 10.3. Concurrent session control

If `maximumSessions(1)` is configured, verify:

- First login succeeds; session A can access protected endpoints.
- Second login of the same user from another session; if policy allows new logins, session A becomes invalid while B remains valid.
- If `maxSessionsPreventsLogin(true)` is set, the second login is blocked and session A stays active.
- Events/responses and cookies match the policy.

With a session registry or distributed Spring Session, integration tests require the real environment/beans. Do not conclude concurrent session correctness from a single MockMvc test without a registry.

### 10.4. LogoutSuccessEvent and auditing

Spring Security can publish `LogoutSuccessEvent` during logout. If the application listens to the event for auditing, do not treat the event as proof that **all external systems** have ended their sessions. Log only event codes, approved internal actor/refs, and timestamps; never record passwords, Basic headers, session IDs, CSRF tokens, or raw requests.

Do not perform non-idempotent side effects relying solely on a non-durable event listener. For SSO-wide logout, implement a separate federated logout flow per the IdP standard.

## 11. Acceptance checklist and failure matrix

| ID | Scenario | Expectation |
| --- | --- | --- |
| M01 | `GET /public` anonymous | 200 |
| M02 | `GET /private` anonymous, Accept HTML | Redirect to login |
| M03 | `formLogin` valid username/password + CSRF | Authentication success, redirect `/private` |
| M04 | After form login, GET protected with same session | 200 with right principal |
| M05 | `formLogin` wrong password | Redirect `/login?error`, unauthenticated |
| M06 | Raw POST `/login` missing CSRF | 403 from CSRF, not treated as password failure |
| M07 | Raw POST `/login` with invalid CSRF | 403 |
| M08 | Basic valid password, authenticated endpoint | 200 with right principal |
| M09 | Basic wrong password | 401, unauthenticated |
| M10 | Basic valid but missing role | 403 authorization |
| M11 | Basic admin with required role | 200 `/admin` |
| M12 | Subsequent Basic request without Authorization header | Not automatically treated as having a form session |
| M13 | Default `logout()` helper | POST with CSRF, redirect `/login?logout` |
| M14 | Logout the actual logged-in session | Session invalidated, context cleared |
| M15 | POST logout without CSRF | 403, old session remains valid |
| M16 | GET logout with CSRF enabled | Does not auto-logout; typically shows confirmation |
| M17 | Custom login/logout URLs | Builders use matching URLs and params |
| M18 | `@WithMockUser` passes while real form login fails | Detects mock test not checking passwords |
| M19 | MockMvc without Security filters | Detected, results not treated as valid auth tests |
| M20 | Local logout then send valid Basic credentials | New request can still authenticate |
| M21 | Session expired or logged out | Cannot access protected routes with old session |
| M22 | User disabled/locked | Login must be rejected per account policy |
| M23 | 401/403/302 under multiple Accept headers | Matches entry point/security chain |
| M24 | Real browser receiving/using cookies in production | Requires E2E, not just MockMvc |
| M25 | Multiple `SecurityFilterChain`s | Tests the exact matched endpoint/chain |

### Troubleshooting

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| `formLogin()` gets 404 | Filter chain not running, wrong `loginProcessingUrl` | Ensure Boot MockMvc has filters and URL matches |
| `formLogin()` gets 403 | CSRF config, builder not used, or different filter chain | Check CSRF and filter chain |
| `formLogin()` fails despite right password | PasswordEncoder mismatch or different user store | Test `UserDetailsService`/`PasswordEncoder.matches` |
| Form login succeeds but target redirects back to login | Session not retained, wrong cookie, context not saved | Check `SecurityContextRepository` and session |
| Basic test returns 200 despite wrong password | Used `with(user(...))` and bypassed Basic | Remove mock principal when testing Basic |
| Basic test returns 302 instead of 401 | Request lacks Basic header or entry point matches HTML | Check header, Accept, and `httpBasic` config |
| Basic test returns 401 despite valid user | Password/hash mismatch or wrong filter chain | Check provider, key, password encoder |
| Logout test returns 302 but session remains | Tested logout on different session or custom handler skipped cleanup | Attach the right session, check `SecurityContextLogoutHandler` |
| POST logout gets 403 | Missing CSRF | Use `logout()` or `post(...).with(csrf())` |
| GET logout returns 200 yet remains authenticated | GET shows confirm page without executing POST | Submit POST logout with CSRF |
| Still able to enter with Basic after logout | Client re-sent Basic credentials | Distinguish session logout from password revocation |
| 403 on `/admin` called "login fail" by test | User is authenticated but lacks role | Separate negative authorization from login |
| Isolated test passes but fails in full suite | Static/global session used, dirty test context config | Isolate sessions and fixtures across tests |
| `MockMvc` returns right code but real browser fails | Cookies/HTTPS/proxy/SameSite/distributed session | Use E2E tests |

## 12. Self-check questions

1. Does `formLogin()` differ from `with(user("student"))`? Which one executes password verification?
2. Why does `formLogin()` add CSRF automatically, whereas raw `post("/login")` can return 403?
3. When form login succeeds, why expect a 302 redirect rather than always 200?
4. Which helper generates the HTTP Basic header? Which class does this helper belong to?
5. Why does `httpBasic("student","pass")` not mean the user has a session?
6. If a user has the right password but lacks `ROLE_ADMIN`, which status should `/admin` return?
7. Why is a `logout()` 302 redirect insufficient by itself to prove the session was truly destroyed?
8. When logging out an existing session, why use `post("/logout").session(session).with(csrf())`?
9. With CSRF enabled, does `GET /logout` automatically log out?
10. After logging out of a form session, why can Basic Auth with the same username/password still call the API?
11. If using `@WebMvcTest` or `standaloneSetup`, what must be ensured before concluding the test runs Security?
12. How do `SecurityMockMvcResultMatchers.authenticated()` and `MockMvcResultMatchers.status()` verify different aspects?
13. Which test scenario proves `SecurityContext` is actually persisted and used across requests?
14. If the app changes `usernameParameter` to `loginName`, what must change in the test?
15. Have these tests proven real browser cookies and reverse proxies are secure?

**Short answers:** (1) yes, `formLogin` goes through the auth provider; (2) CSRF is required for unsafe POSTs; (3) form success handlers usually redirect; (4) `SecurityMockMvcRequestPostProcessors.httpBasic`; (5) Basic attaches a header per request; (6) 403; (7) no session attached or only redirect tested; (8) raw POST builder supports `.session` and `.with(csrf())`; (9) typically only shows a confirmation page; (10) Basic authenticates the new request; (11) `FilterChainProxy`/`springSecurity()` is present; (12) authentication state vs. HTTP status; (13) sending a protected GET with the same `MockHttpSession`; (14) change the param name in `formLogin(...).user("loginName", "...")`; (15) not yet, E2E is required.

## 13. Official references

- [Spring Security 6.5 — Testing Form Based Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/form-login.html)
- [Spring Security 6.5 — Testing HTTP Basic Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/http-basic.html)
- [Spring Security 6.5 — Testing Logout](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/logout.html)
- [Spring Security 6.5 — SecurityMockMvcRequestBuilders API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/test/web/servlet/request/SecurityMockMvcRequestBuilders.html)
- [Spring Security 6.5 — SecurityMockMvcRequestPostProcessors API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/test/web/servlet/request/SecurityMockMvcRequestPostProcessors.html)
- [Spring Security 6.5 — SecurityMockMvcResultMatchers API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/test/web/servlet/response/SecurityMockMvcResultMatchers.html)
- [Spring Security 6.5 — Logout](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/logout.html)
- [Spring Security 6.5 — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html)
- [Spring Security 6.5 — CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html)
- [Spring Framework — MockMvc](https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-framework.html)
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
