# Form Login, HTTP Basic, Sessions, and Logout When Used by an Application

In **Spring Boot - testing**, under **Security**, you need to test the login and identity-persistence mechanisms that **the application actually enables**: form login in browsers, HTTP Basic for suitable clients, HTTP sessions, CSRF, and logout. A test that merely puts **`@WithMockUser`** on a method and gets a 200 on an endpoint **does not prove** that passwords are verified, sessions are created/saved, login failures redirect to the right URL, session fixation is prevented, or logout invalidates the old session.

This lesson focuses on the **Spring Security servlet stack** on **Java 17, Spring Boot 3.4.5, and Spring Security 6.4.x**. The complete example uses **`spring-boot-starter-security`, `spring-security-test`, JUnit Jupiter, `MockMvc`**, and a real HTTP test with **`RANDOM_PORT`**. The suite tests **anonymous vs authenticated**, **form login with right/wrong password**, **HTTP Basic 200/401**, **403 due to missing role or CSRF**, **sessions across multiple requests**, **session ID rotation on login**, **POST logout with CSRF**, and **session invalidation revoking access**.

**Conditions of applicability:** Not every application needs form login, HTTP Basic, or server-side sessions. A completely stateless REST API using bearer tokens/OAuth2 Resource Server has a different contract. Only enable and test mechanisms present in the real threat model; **never add HTTP Basic or form login just to pass a test**. The outcomes stated below are **expectations from code**, not Gradle stdout observed at authoring time.

## 1. Distinguishing authentication, authorization, session, and logout

- **Authentication:** proving who the user is. For example, a form POST with username/password or an HTTP header `Authorization: Basic`.
- **Authorization:** after authentication, which paths the user may enter. **`ROLE_USER`** can enter `/private` but cannot enter `/admin`.
- **SecurityContext:** holds the current `Authentication`; Spring Security uses it in the filter chain while processing a request.
- **HTTP session:** server-side state identified via a session cookie/ID. With stateful form login, the authentication result is typically stored in the session so subsequent requests still recognize the user.
- **Session fixation protection:** rotating the session ID upon successful authentication, preventing reuse of an ID pre-controlled by an attacker.
- **CSRF protection:** blocks state-changing requests sent with browser credentials without a valid token; applies to form login, logout, and POST/PUT/PATCH/DELETE per configuration.
- **Logout:** terminates server-side login state, typically invalidating the session, clearing `SecurityContext`, and sending the client to a logout-success URL.
- **HTTP Basic:** the client sends username/password (Base64, **not secure encryption**) on every request; it is not a form login/session protocol. HTTPS is mandatory; server-side logout **does not revoke** the username/password that a client can keep sending.

Four questions need independent tests: **who can log in**, **what they can do once logged in**, **whether identity persists across new requests**, and **whether logout actually revokes the session**.

### Target behavior matrix

| Scenario | Mechanism | Expected outcome in project |
| --- | --- | --- |
| Anonymous GET /public | permitAll | **200** |
| Anonymous GET /private, Accept text/html | Form entry point | **302** to /login |
| Anonymous GET /private, Accept application/json | Basic entry point | **401**, with WWW-Authenticate Basic |
| Alice logs in with right password + CSRF | Form | **302** to /private and authenticated |
| Alice logs in with wrong password | Form | **302** to /login?error |
| Alice POST /login without CSRF | CSRF | **403**, unauthenticated |
| Alice GET /private with authenticated session | Session | **200**, user=alice |
| Alice GET /admin | Authorization | **403** |
| Admin GET /admin | Authorization | **200** |
| Alice GET /private with valid Basic header | HTTP Basic | **200** |
| Alice GET /private with wrong Basic password | HTTP Basic | **401** |
| Alice POST /private/action without CSRF | CSRF | **403** |
| Alice POST /private/action with CSRF | CSRF | **200** |
| Logged-in POST /logout without CSRF | CSRF | **403**, session still active |
| Logged-in POST /logout with CSRF | Logout | **302** to /login?logout, session invalid |
| New request without session after logout | Anonymous | **401** with Accept application/json |

**302/401 depends on the entry point and `Accept` header** when an app enables both form login and Basic. This project specifies headers explicitly in every test so assertions do not depend on implicit content negotiation.

## 2. What does a Spring Security request pass through?

~~~text
HTTP request
    |
    v
DelegatingFilterProxy
    |
    v
FilterChainProxy / SecurityFilterChain
    |
    +--> SecurityContextHolderFilter reads SecurityContextRepository
    |
    +--> CsrfFilter verifies token on non-safe methods
    |
    +--> UsernamePasswordAuthenticationFilter (POST /login)
    |      or BasicAuthenticationFilter (Authorization: Basic ...)
    |
    +--> AuthorizationFilter applies permitAll/authenticated/hasRole rules
    |
    v
Spring MVC controller
    |
    v
HTTP response
~~~

This is a **conceptual diagram**, not an exact exhaustive ordering of all filters: real filter order can differ depending on configuration. Spring Security 6 uses **`SecurityContextHolderFilter`** and **`SecurityContextRepository`** under an explicit `SecurityContext` saving model; standard authentication filters handle saving on success. A **custom login endpoint** that sets `SecurityContextHolder` directly will not necessarily persist across the next request unless it calls `SecurityContextRepository.saveContext(...)` properly.

### Why is testing the filter chain important?

A pure controller test:

~~~java
MockMvcBuilders.standaloneSetup(controller).build()
~~~

is an **anti-pattern snippet** that can run without the Spring Security filter chain. If it invokes the controller and returns 200, that **does not prove** real anonymous callers are blocked by security. Similarly:

~~~java
@AutoConfigureMockMvc(addFilters = false)
~~~

is a configuration that **disables filters when running MockMvc**, risking false-green security tests. To verify real login/Basic/session/logout behavior, use **`@SpringBootTest + @AutoConfigureMockMvc`** so MockMvc runs the configured filter chain. When building MockMvc manually from `WebApplicationContext`, apply **`SecurityMockMvcConfigurers.springSecurity()`** properly.

## 3. When does Spring Boot automatically enable form login/Basic?

When `spring-boot-starter-security` is on the classpath and no custom `SecurityFilterChain` replaces it, Spring Boot secures the web app by default. The challenge mechanism may pick **form login** or **HTTP Basic** based on the request/`Accept` header. Spring Boot can generate a default user with a random password for development; **never use generated accounts/passwords as a production policy**.

When defining your own **`SecurityFilterChain` bean**, explicitly configure **`authorizeHttpRequests`**, **`formLogin`**, **`httpBasic`**, **`logout`**, **`csrf`**, and **`sessionManagement`** as required. Do not assume importing `starter-security` guarantees features stay enabled once a custom chain overrides the default.

In the sample project:
- GET `/public`: anonymous allowed.
- GET `/private`: any authenticated user.
- GET `/admin`: `ROLE_ADMIN` only.
- POST `/private/action`: authenticated and valid CSRF.
- `/login`: Spring Security provides a **generated login page** and handles form login POSTs.
- `/logout`: Spring Security provides the logout endpoint, requiring **POST + CSRF**.
- Enabling **`formLogin` + `httpBasic`** together is **strictly for learning both flows**. Production should narrow the attack surface and select the mechanism suited to each client.

### Rule matching order matters

Example:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/public").permitAll()
    .requestMatchers("/admin").hasRole("ADMIN")
    .anyRequest().authenticated()
)
~~~

Specific rules must come **before** `anyRequest`. **`hasRole("ADMIN")`** corresponds to authority **`ROLE_ADMIN`** by default; **`hasAuthority("ADMIN")`** is not synonymous. Tests should include both a regular user and an admin to catch overly broad security rules.

## 4. Runnable Java 17 + Spring Boot 3.4.5 project

The project intentionally puts **two in-memory accounts only under the `demo` Spring profile**, so tests do not depend on a database, external IdP, or real user passwords. This is a **learning security fixture**, not a production deployment config.

### 4.1. File structure

~~~text
settings.gradle
build.gradle
src/main/java/com/example/securityqa/SecurityQaApplication.java
src/main/java/com/example/securityqa/DemoSecurityConfig.java
src/main/java/com/example/securityqa/DemoController.java
src/test/java/com/example/securityqa/FormLoginFlowTest.java
src/test/java/com/example/securityqa/HttpBasicFlowTest.java
src/test/java/com/example/securityqa/SessionFixationTest.java
src/test/java/com/example/securityqa/LogoutFlowTest.java
src/test/java/com/example/securityqa/CsrfAndRoleTest.java
src/test/java/com/example/securityqa/RealHttpBasicTest.java
~~~

### 4.2. Gradle and test dependencies

**settings.gradle**

~~~groovy
rootProject.name = 'spring-security-authentication-testing'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.4.5'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

**`spring-boot-starter-security`** provides Spring Security servlet filters, authentication, and password encoding. **`spring-security-test`** provides **`formLogin()`**, **`httpBasic()`**, **`csrf()`**, **`@WithMockUser`**, along with `authenticated()`/`unauthenticated()` matchers. **`spring-boot-starter-test`** brings JUnit Jupiter, MockMvc, and assertions.

Do not add a servlet container manually because `starter-web` already includes an embedded servlet server for real HTTP tests. The Spring Boot 3.4 BOM manages Spring Security 6.4.x; do not mix Spring Security 5.x or Spring Boot 2.x snippets with Java 17/Jakarta Servlet APIs.

### 4.3. Main application

**src/main/java/com/example/securityqa/SecurityQaApplication.java**

~~~java
package com.example.securityqa;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityQaApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityQaApplication.class, args);
    }
}
~~~

### 4.4. SecurityFilterChain and in-memory demo users

**src/main/java/com/example/securityqa/DemoSecurityConfig.java**

~~~java
package com.example.securityqa;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
@Profile("demo")
public class DemoSecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService demoUsers(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("alice-pass"))
                .roles("USER")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .roles("ADMIN", "USER")
                .build()
        );
    }

    @Bean
    SecurityFilterChain demoSecurity(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/admin").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .formLogin(form -> form
                .defaultSuccessUrl("/private", true)
                .permitAll()
            )
            .httpBasic(Customizer.withDefaults())
            .csrf(Customizer.withDefaults())
            .logout(logout -> logout
                .logoutSuccessUrl("/login?logout")
                .permitAll()
            )
            .sessionManagement(session -> session
                .sessionFixation(fixation ->
                    fixation.changeSessionId())
            );

        return http.build();
    }
}
~~~

**`@Profile("demo")`** keeps demonstration credentials and config inactive by default when the application runs with another profile. **Never activate the `demo` profile in internet-facing/public environments**, never store `alice-pass`/`admin-pass` as real secrets, and never use these credentials in production.

- **`BCryptPasswordEncoder`** hashes fixture passwords; login still sends cleartext passwords over form/Basic transport, so HTTPS is mandatory on deployment.
- **`roles("USER")`** generates authority `ROLE_USER`; admin has `ROLE_ADMIN` and `ROLE_USER`.
- **`formLogin.defaultSuccessUrl("/private", true)`** forces a fixed redirect after successful form login, making the contract straightforward to assert. Without **`true`**, Spring Security may send the user back to a pre-login `SavedRequest`.
- **`httpBasic`** is enabled to test HTTP `Authorization` headers; Basic **should not be enabled if the app does not need it**.
- **`csrf`** stays at default; never disable it just to make form login/logout tests pass.
- **`sessionFixation.changeSessionId()`** is the right strategy for Servlet 3.1+, rotating the session ID on auth success.
- **`logout`** uses the default logout filter, redirecting on success to `/login?logout`; by default it invalidates the session and clears `SecurityContext` on logout success.

When writing a custom `loginPage("/sign-in")`, you must serve the GET page yourself, configure `loginProcessingUrl`, username/password parameter names, and `permitAll` properly. Do not copy default `formLogin()` test snippets when the endpoints or fields have changed.

### 4.5. Controller for public, private, admin, and CSRF-protected POST

**src/main/java/com/example/securityqa/DemoController.java**

~~~java
package com.example.securityqa;

import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public")
    public Map<String, String> publicPage() {
        return Map.of("status", "public");
    }

    @GetMapping("/private")
    public Map<String, String> privatePage(
            Authentication authentication) {
        return Map.of(
            "user", authentication.getName(),
            "scope", "private");
    }

    @GetMapping("/admin")
    public Map<String, String> adminPage(
            Authentication authentication) {
        return Map.of(
            "user", authentication.getName(),
            "scope", "admin");
    }

    @PostMapping("/private/action")
    public Map<String, String> submitAction(
            Authentication authentication) {
        return Map.of(
            "status", "accepted",
            "user", authentication.getName());
    }
}
~~~

POST `/private/action` is a **checkpoint for protecting non-safe requests**, mutating no real data. In production, this could be changing a password or creating an order; CSRF tests must verify the request **never reaches business side effects** when the token is missing. In the demo, the HTTP status shows `CsrfFilter` intercepted the request before the controller.

## 5. Testing Form Login: credentials, redirects, and cross-request sessions

**src/test/java/com/example/securityqa/FormLoginFlowTest.java**

~~~java
package com.example.securityqa;

import jakarta.servlet.http.HttpSession;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.unauthenticated;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("demo")
class FormLoginFlowTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void anonymousBrowserIsRedirectedToLogin() throws Exception {
        mvc.perform(get("/private")
                .accept(MediaType.TEXT_HTML))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login"));
    }

    @Test
    void successfulFormLoginPersistsAuthenticationInSession()
            throws Exception {
        MvcResult result = mvc.perform(
                formLogin()
                    .user("alice")
                    .password("alice-pass"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/private"))
            .andExpect(authenticated().withUsername("alice"))
            .andReturn();

        HttpSession session =
                result.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/private")
                .session((MockHttpSession) session)
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.user").value("alice"))
            .andExpect(jsonPath("$.scope").value("private"));
    }

    @Test
    void wrongPasswordIsRejected() throws Exception {
        mvc.perform(formLogin()
                .user("alice")
                .password("wrong-password"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?error"))
            .andExpect(unauthenticated());
    }

    @Test
    void loginWithoutCsrfIsForbidden() throws Exception {
        mvc.perform(post("/login")
                .param("username", "alice")
                .param("password", "alice-pass"))
            .andExpect(status().isForbidden());
    }
}
~~~

**`formLogin()`** is a helper from **`spring-security-test`**: it constructs a **`POST /login`** request, fills credentials, and includes a **valid CSRF token**. Hence a passing `formLogin()` test **does not automatically prove the endpoint rejects POSTs lacking CSRF**; the separate `loginWithoutCsrfIsForbidden` test must send a raw `post` to verify 403.

**`authenticated().withUsername("alice")`** confirms `SecurityContext` after login matches the expected principal. The follow-up step passes **`MockHttpSession`** from the login request into a **new `GET /private`** to prove **authentication persists across requests**, not just during the single request being handled.

**Wrong passwords** must fail and redirect to `/login?error` per the default failure handler. Asserting only `status302` is weak because **both success and failure typically redirect**; always assert both `Location` and `authenticated()`/`unauthenticated()`.

### Saved request cases

If a browser performs `GET /private` first, Spring Security may store a **`SavedRequest`** in the session and redirect back to the original URL after successful form login. The demo intentionally sets **`defaultSuccessUrl("/private", true)`** to always redirect to `/private`; when testing a real app **without `alwaysUse=true`**, expected redirects must reflect the `SavedRequest` contract rather than forcing the demo URL.

### With a custom login form

For example, if an app defines `loginProcessingUrl("/auth/login")`, `usernameParameter("email")`, and `passwordParameter("secret")`, tests use:

~~~java
mvc.perform(
    formLogin("/auth/login")
        .user("email", "alice@example.com")
        .password("secret", "password"))
    .andExpect(authenticated());
~~~

This is an **illustrative snippet**, not part of the runnable tree. It only works if the real `SecurityFilterChain` configures those endpoints/parameter names and a matching user exists. Never mix the default `POST /login` helper with a custom `loginPage` whose URL/fields have changed.

## 6. Testing HTTP Basic: real headers and exact 401/403

HTTP Basic sends:

~~~http
Authorization: Basic YWxpY2U6YWxpY2UtcGFzcw==
~~~

This is Base64 for **`alice:alice-pass`** in the demo. **Base64 is trivially decoded**, not encryption or secret protection; Basic **is only safe over TLS/HTTPS**. Never log `Authorization` headers, never put Basic credentials in URLs, and never use production credentials in tests.

**src/test/java/com/example/securityqa/HttpBasicFlowTest.java**

~~~java
package com.example.securityqa;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.startsWith;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("demo")
class HttpBasicFlowTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void validBasicCredentialsReachProtectedEndpoint()
            throws Exception {
        mvc.perform(get("/private")
                .with(httpBasic("alice", "alice-pass"))
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.user").value("alice"));
    }

    @Test
    void anonymousJsonRequestGetsBasicChallenge()
            throws Exception {
        mvc.perform(get("/private")
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                "WWW-Authenticate", startsWith("Basic")));
    }

    @Test
    void wrongBasicPasswordGetsUnauthorized()
            throws Exception {
        mvc.perform(get("/private")
                .with(httpBasic("alice", "invalid"))
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void userRoleCannotEnterAdminArea() throws Exception {
        mvc.perform(get("/admin")
                .with(httpBasic("alice", "alice-pass"))
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminRoleMayEnterAdminArea() throws Exception {
        mvc.perform(get("/admin")
                .with(httpBasic("admin", "admin-pass"))
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.user").value("admin"))
            .andExpect(jsonPath("$.scope").value("admin"));
    }
}
~~~

**`httpBasic("alice","alice-pass")`** is a **`RequestPostProcessor`** that constructs a real `Authorization` header on `MockHttpServletRequest`. Unlike **`with(user("alice"))`** or **`@WithMockUser`**, it passes through HTTP Basic authentication and verifies the password against `UserDetailsService`/`PasswordEncoder`.

On the same route, an anonymous request can receive:
- **302 redirect `/login`** if the client accepts HTML and the chain selects the form entry point.
- **401 `WWW-Authenticate: Basic`** if the request selects the Basic entry point, such as **`Accept: application/json`** in the demo config.
- **403** if authenticated yet lacking authority, or an unsafe request lacks CSRF.

**Do not write a blanket test claiming every anonymous request must return 401** when a system supports both browser form login and API HTTP Basic. Specify `Accept` headers, `SecurityFilterChain` matchers, entry points, and actual responses.

### Basic auth does not automatically mean STATELESS

Basic is typically sent per request, yet an app can still maintain session behavior depending on `SecurityFilterChain` and `SessionCreationPolicy`. **Do not assume automatically** that every Basic request lacks `JSESSIONID` or server state. If an application is a stateless REST API, explicitly configure `SessionCreationPolicy.STATELESS` on the right filter chain, choose a CSRF policy matching cookie/browser credential risks, and write tests that do not rely on sessions.

## 7. Testing sessions: real login, session fixation, and state persistence

A session fixation attack can occur if an attacker knows or forces a browser to use a session ID before the victim logs in, and that ID remains accepted after login. On Servlet 3.1+, Spring Security uses **`changeSessionId`** by default; the demo configures it explicitly.

Tests must create an **old session**, attach a non-sensitive attribute, log in, compare **old ID vs authenticated session ID**, and verify the user can access a protected endpoint with that session.

**src/test/java/com/example/securityqa/SessionFixationTest.java**

~~~java
package com.example.securityqa;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("demo")
class SessionFixationTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void successfulLoginChangesExistingSessionId()
            throws Exception {

        MockHttpSession preLoginSession = new MockHttpSession();
        preLoginSession.setAttribute("cart", "cart-42");
        String oldSessionId = preLoginSession.getId();

        MvcResult login = mvc.perform(post("/login")
                .session(preLoginSession)
                .param("username", "alice")
                .param("password", "alice-pass")
                .with(csrf()))
            .andExpect(status().is3xxRedirection())
            .andExpect(authenticated().withUsername("alice"))
            .andReturn();

        MockHttpSession afterLogin =
                (MockHttpSession) login.getRequest().getSession(false);

        assertNotNull(afterLogin);
        assertNotEquals(oldSessionId, afterLogin.getId());
        assertEquals("cart-42", afterLogin.getAttribute("cart"));

        mvc.perform(get("/private")
                .session(afterLogin)
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.user").value("alice"));
    }
}
~~~

**Difference between ID and object:** **`changeSessionId()`** can rotate the ID on the **same** `HttpSession` object; do not assert that a new session object instance was allocated. The test asserts only that the **ID changed**, the session still holds the **`cart`** attribute (under the `changeSessionId` strategy), and the subsequent request is authenticated.

Spring Security also provides **`newSession`**, **`migrateSession`**, and **`none`** for session fixation policies:
- **`changeSessionId`**: uses Servlet container API, default on Servlet 3.1+, rotates ID.
- **`newSession`**: creates a new session keeping only certain essential security-related attributes.
- **`migrateSession`**: copies attributes into a new session, typically for other containers/compatibility modes.
- **`none`**: disables session fixation protection; generally **should not be used**.

**If the app configures `SessionCreationPolicy.STATELESS`**, tests expecting `SecurityContext` to persist across sessions violate the contract: clients must resend bearer/basic credentials or another token. Never add sessions to a REST API just to make a test green.

### Do not equate thread SecurityContext with session

**`SecurityContextHolder`** is usually thread-bound during a request. When the request finishes, the context can be cleared from the thread; authentication must be **restored from `SecurityContextRepository`** on the next request. Never conclude “login succeeded” just because `SecurityContextHolder` in the same code block holds an `Authentication` without testing the next request.

If writing a custom JSON login controller or custom authentication filter in Spring Security 6, setting `SecurityContextHolder` alone may **not persist** unless saved to `SecurityContextRepository`. With the standard form login filter, persistence is handled automatically; the session test above catches regressions where custom login persistence is omitted.

## 8. Testing logout: POST + CSRF, session invalidation, and revoked access

When **CSRF is enabled**, Spring Security defaults to **`POST /logout` with CSRF** performing logout; **`GET /logout`** normally renders a confirmation page (with a token) rather than **logging out immediately**. Allowing GET to log out when CSRF is disabled creates a logout-CSRF risk; never fix tests by disabling CSRF app-wide.

A successful logout typically:
1. Invalidates the current `HttpSession`.
2. Clears `SecurityContextHolder`.
3. Clears `SecurityContextRepository`.
4. Clears remember-me state if present.
5. Clears the CSRF token and publishes logout events per handlers.
6. Redirects to the logout-success URL.

**src/test/java/com/example/securityqa/LogoutFlowTest.java**

~~~java
package com.example.securityqa;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("demo")
class LogoutFlowTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void postLogoutRequiresCsrfAndInvalidatesSession()
            throws Exception {

        MvcResult login = mvc.perform(formLogin()
                .user("alice")
                .password("alice-pass"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        MockHttpSession session =
                (MockHttpSession) login.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/private")
                .session(session)
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.user").value("alice"));

        mvc.perform(post("/logout")
                .session(session))
            .andExpect(status().isForbidden());

        assertFalse(session.isInvalid());

        mvc.perform(post("/logout")
                .session(session)
                .with(csrf()))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?logout"));

        assertTrue(session.isInvalid());

        // After logout, send a new request without a session/cookie.
        mvc.perform(get("/private")
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isUnauthorized());
    }
}
~~~

This test **does not** try passing the invalidated `MockHttpSession` into another MockMvc request: an invalidated session should not be reused. Instead, it asserts **`session.isInvalid()`** and that a new request without a session is challenged. Together, both assertions protect the logout lifecycle.

**Important:** If you use the **`SecurityMockMvcRequestBuilders.logout()`** helper, it **attaches valid CSRF automatically** by default. That is convenient for testing the success path, but tests proving **missing CSRF returns 403** must send a raw `post("/logout")` without `csrf()`.

### After logout, HTTP Basic can still re-authenticate

Form session logout **does not disable passwords**. If a client continues sending:

~~~http
Authorization: Basic YWxpY2U6YWxpY2UtcGFzcw==
~~~

the HTTP Basic filter can authenticate a new request and grant access again as long as the credentials remain valid. Thus saying **“logout permanently cuts off Basic access”** is wrong. Revoking credentials/tokens requires password change, token revocation, disabling the account, or an appropriate mechanism. With browser Basic auth, browsers may cache credentials; the app has no standard server-session logout equivalent to form login.

### Deleting browser cookies differs from session invalidation

Invalidating `HttpSession` is a server-side action. Deleting client cookies can be configured additionally via logout handlers/cookie settings, yet **deleting a cookie alone** does not necessarily invalidate a live server session. Conversely, invalidating the server-side session does not ensure browsers delete old cookies unless `Set-Cookie`/`Clear-Site-Data` policies are sent; the old cookie will simply no longer map to a valid session. MockMvc tests verify server behavior, while `Set-Cookie`/`HttpOnly`/`Secure`/`SameSite` require appropriate HTTP/browser tests.

## 9. Test CSRF and authorization separately instead of merging them

**CSRF** can return **403 even when the user is authenticated**. **Role access denial** also returns **403**. Therefore, a test asserting only HTTP 403 does not identify the cause unless credentials, tokens, and routes are controlled explicitly.

**src/test/java/com/example/securityqa/CsrfAndRoleTest.java**

~~~java
package com.example.securityqa;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("demo")
class CsrfAndRoleTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void authenticatedPostWithoutCsrfIsForbidden()
            throws Exception {
        mvc.perform(post("/private/action")
                .with(httpBasic("alice", "alice-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void authenticatedPostWithValidCsrfIsAccepted()
            throws Exception {
        mvc.perform(post("/private/action")
                .with(httpBasic("alice", "alice-pass"))
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("accepted"))
            .andExpect(jsonPath("$.user").value("alice"));
    }

    @Test
    void invalidCsrfTokenIsRejected() throws Exception {
        mvc.perform(post("/private/action")
                .with(httpBasic("alice", "alice-pass"))
                .with(csrf().useInvalidToken()))
            .andExpect(status().isForbidden());
    }

    @Test
    void roleUserCannotAccessAdminEvenWithValidPassword()
            throws Exception {
        mvc.perform(get("/admin")
                .with(httpBasic("alice", "alice-pass"))
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isForbidden());
    }

    @Test
    void roleAdminCanAccessAdmin() throws Exception {
        mvc.perform(get("/admin")
                .with(httpBasic("admin", "admin-pass"))
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.scope").value("admin"));
    }

    @Test
    void publicEndpointDoesNotNeedLogin() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("public"));
    }
}
~~~

**CSRF tests** use real Basic credentials with missing/invalid tokens to verify `CsrfFilter`. **Role tests** use GET (a safe method) so CSRF does not interfere, allowing 403 to be attributed to lacking `ROLE_ADMIN`. Both 403s share the same status code but differ in cause and fix.

**`csrf().useInvalidToken()`** is the specialized helper for testing invalid tokens. **`csrf().asHeader()`** tests clients sending tokens via headers; this still must match the application's CSRF repository/request handler. Do not replace it with `csrf().disable()` in tests just to make POST return 200.

### Must every REST API enable CSRF?

CSRF threats mainly arise when browsers automatically attach credentials (session cookies, browser HTTP Basic cache...). An API using bearer `Authorization` tokens that browsers never attach automatically has a different threat model and may disable CSRF **selectively**. However, an application with form login/cookie-based sessions must protect POST login/logout and state-changing endpoints. Decide based on **how browsers transmit credentials**, not on URLs starting with `/api` or the label “REST”.

## 10. Testing HTTP Basic through a real HTTP server (RANDOM_PORT)

MockMvc runs the Spring Security filter chain yet **does not open a socket or real browser**. When you want additional proof that Basic headers are handled through the servlet server, use the JDK `HttpClient` and a random port. This test **does not test session cookies**; it verifies the actual HTTP challenge and valid Basic credentials.

**src/test/java/com/example/securityqa/RealHttpBasicTest.java**

~~~java
package com.example.securityqa;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Base64;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.SpringBootTest.WebEnvironment;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.context.ActiveProfiles;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment = WebEnvironment.RANDOM_PORT)
@ActiveProfiles("demo")
class RealHttpBasicTest {

    @LocalServerPort
    private int port;

    private final HttpClient client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(5))
            .build();

    @Test
    void basicCredentialsAreCheckedOverRealHttp()
            throws Exception {
        URI url = URI.create(
                "http://127.0.0.1:" + port + "/private");

        HttpRequest withoutCredentials = HttpRequest
                .newBuilder(url)
                .header("Accept", "application/json")
                .timeout(Duration.ofSeconds(5))
                .GET()
                .build();

        HttpResponse<String> denied = client.send(
                withoutCredentials,
                HttpResponse.BodyHandlers.ofString());

        assertEquals(401, denied.statusCode());
        assertTrue(denied.headers()
                .firstValue("WWW-Authenticate")
                .orElse("")
                .startsWith("Basic"));

        String base64 = Base64.getEncoder()
                .encodeToString(
                    "alice:alice-pass".getBytes(
                        StandardCharsets.UTF_8));

        HttpRequest withCredentials = HttpRequest
                .newBuilder(url)
                .header("Accept", "application/json")
                .header("Authorization", "Basic " + base64)
                .timeout(Duration.ofSeconds(5))
                .GET()
                .build();

        HttpResponse<String> allowed = client.send(
                withCredentials,
                HttpResponse.BodyHandlers.ofString());

        assertEquals(200, allowed.statusCode());
        assertTrue(allowed.body().contains(
                "\"user\":\"alice\""));
    }
}
~~~

**Expected outcome:** anonymous JSON request gets **401** and **`WWW-Authenticate: Basic`**; request sending valid Basic credentials gets **200** and a JSON body with user `alice`. This runs over **unencrypted loopback HTTP** using **demo credentials**; production Basic credentials must travel over HTTPS. Never put real accounts into tests or log HTTP `Authorization` headers.

### MockMvc vs RANDOM_PORT vs browser

| Test level | Proves | Does not prove |
| --- | --- | --- |
| Unit `SecurityFilterChain` matcher | Certain class-level rules/configs | Authentication flow, Servlet/cookie runtime |
| MockMvc with Spring Security filters | Form POST, Basic header, CSRF, SecurityContext, role/session logic | TLS, reverse proxy, browser cookies, network |
| `RANDOM_PORT` + `HttpClient` | HTTP server/filter behavior, headers, status/cookie responses | Full browser navigation, real SameSite enforcement |
| Playwright/Selenium browser E2E | HTML forms, cookies, redirects, CSRF hidden fields, navigation | Backend internals/concurrency unless paired with backend assertions |
| Production-like integration | Proxy/TLS/session store/distributed context | Does not replace unit coverage |

**Do not pick one tool to prove everything.** MockMvc is typically the best level for fast, reliable Spring Security filter chain testing. `RANDOM_PORT` helps verify real HTTP configuration; browser tests are needed when UI/login forms/cookies are key contracts.

## 11. @WithMockUser and with(user()) are convenient, not login tests

Example:

~~~java
@Test
@WithMockUser(username = "alice", roles = "USER")
void userRoleMayEnterPrivate() throws Exception {
    mvc.perform(get("/private"))
        .andExpect(status().isOk());
}
~~~

This is an **excerpt** without imports or a class, not part of the runnable tree. **`@WithMockUser`** creates a test `SecurityContext`, does not verify passwords through `UserDetailsService`/`PasswordEncoder`, and **does not perform form POST login or session persistence** like a real browser.

Similarly:

~~~java
mvc.perform(get("/private")
        .with(user("alice").roles("USER")))
    .andExpect(status().isOk());
~~~

This is a request post processor for authorization-focused tests, proving neither actual Basic headers nor form credentials. Use these helpers when you only care about **`hasRole`/`hasAuthority`/method security**; use **`formLogin()`** to test form flows, **`httpBasic()`** to test Basic flows, and sessions obtained from **real login requests** to test persistence.

### Never build a test context that fakes security policy

With **`@WebMvcTest`**, be sure the slice loads the intended filter chain and `UserDetailsService`/security config. If you `@Import` a permissive test `SecurityFilterChain` or disable filters, controller tests can return 200 even when production rules require `ROLE_ADMIN`. When the requirement is the complete security filter chain, use **`@SpringBootTest + @AutoConfigureMockMvc`** or a slice configured with the corresponding `SecurityFilterChain`, and assert negative cases as well.

## 12. Session cookies, expiration, and multiple application instances

An HTTP session is commonly identified by **`JSESSIONID`** or a cookie name configured by the app/container/Spring Session. Distinguish:

- **Server-side session ID**: the token identifying state.
- **Cookie**: how the browser carries the session ID to subsequent requests.
- **`SecurityContextRepository`**: restores authentication from stored `SecurityContext`.
- **`HttpSession` timeout**: expires the session so subsequent requests must re-authenticate per policy.
- **Session fixation**: rotates the ID at login; **logout** invalidates the session.
- **Concurrent session management**: can limit sessions per user, requiring `SessionRegistry`/session event handling and dedicated tests.
- **Distributed deployments**: may use **Spring Session** with Redis/JDBC instead of local `HttpSession`; tests must verify the session store and logout propagation across nodes.

### Cookie flags

Production browser apps should consider:
- **`HttpOnly`**: JavaScript cannot read the cookie, reducing some session cookie XSS exposure without eliminating all XSS risks.
- **`Secure`**: browser only sends the cookie over HTTPS; do not enable `Secure` on local HTTP by default and then wonder why the browser drops the cookie.
- **`SameSite`**: affects cross-site cookie transmission; pick `Lax`/`Strict`/`None` per actual flows and CSRF threat model. **`SameSite` does not replace CSRF tokens in all scenarios**.
- **`Path`/`Domain`**: restricts where browsers send cookies; account for reverse proxies/base paths.
- **`Max-Age`/`Expires`**: controls persistent cookie lifetime, distinct from server-side session timeout.

Illustrative configuration strictly for a **production HTTPS** profile:

~~~properties
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.secure=true
server.servlet.session.cookie.same-site=lax
server.servlet.session.timeout=15m
~~~

This is a **config snippet**, not part of the runnable project; pick values based on real requirements, HTTPS/proxies, and Spring Boot version. In particular, when testing `RANDOM_PORT` over HTTP loopback, do not apply production `Secure` cookie settings and assume browser cookie lifecycles behave like HTTPS.

### MockMvc is not a browser cookie jar

MockMvc provides `MockHttpSession`, passed via `.session(...)` to simulate state. It does not replicate browser cookie transmission, redirect following, `SameSite`/`Secure` enforcement, or TLS. If an app has custom login pages, reverse proxies, OAuth redirects, or complex session-cookie settings, add browser/HTTP integration tests. A green MockMvc test **does not prove Chrome sends the cookie properly in every cross-site flow**.

## 13. Advanced logout: remember-me, Clear-Site-Data, and token revocation

Default logout typically invalidates the session and clears `SecurityContext`, yet other features have their own lifecycles:

**Remember-me cookies:** if remember-me is enabled, verify that remember-me cookies/tokens are deleted or revoked, especially with a persistent token repository. A successful session logout does not automatically prove remember-me state was cleared if a custom logout handler is buggy.

**Custom authentication:** if the app uses custom tokens, passwordless auth, or OAuth login, identify which token/session stores must be revoked. Calling `SecurityContextHolder.clearContext()` is insufficient if credentials/tokens remain reusable.

**`Clear-Site-Data`**: an HTTP response header that instructs browsers to clear caches/cookies/storage within supported scopes; this is client-side browser behavior and must be tested in an appropriate environment. Never call it server-side session invalidation.

**Cookies:** `Delete-Cookie` or `Set-Cookie` `Max-Age=0` affects only the client side. Test both **server session invalidation** and **cookie response headers** when required.

**Logout success URL:** `/login?logout` in the demo is a simple redirect. When using a different custom `logoutSuccessUrl`, tests must assert the new URL and anonymous access to the success endpoint. If the success endpoint is protected by `SecurityFilterChain`, browsers can get trapped in a redirect loop.

**GET `/logout`:** with CSRF enabled, this is usually a confirmation page, not a state-changing GET. Never write a custom GET endpoint to destroy sessions without explicit logout-CSRF protection.

## 14. Session timeout, concurrent login, and security testing

### Session expiration

To test timeout, never call `Thread.sleep(900000)` to wait 15 minutes. Use a mock/test session marked expired/invalidated in unit/integration tests, or configure a short TTL on a test profile using bounded waits. Verify:
1. Request is authenticated.
2. Session expires under the tested mechanism.
3. New request carries no authentication.
4. Server returns 401 or redirects to `/login` per entry point.
5. No `SecurityContext` leaks from previous threads/requests.

With a Spring Session distributed store, run store/TTL and replication integration tests if timeout is a system requirement.

### Concurrency and SessionRegistry

If an app limits users to at most 1 session, configure **`maximumSessions`**, expired session handling, and `SessionRegistry`/`HttpSessionEventPublisher` per runtime. Test two real login sessions and verify the old or new session is rejected per policy; do not run a single `@WithMockUser` test and claim concurrency was tested.

**Session concurrency control is omitted** in the demo because requirement B335 focuses on form login, Basic, sessions, and logout when used by the app. Only add advanced checks when the real system includes that feature.

### Session fixation and custom login

A custom success handler might forget to save `SecurityContext`, drop session fixation protection, or skip CSRF. Tests should create a pre-login session, log in, assert the ID changed, verify the next request, log out, and assert invalidation. The tests in Sections 5–8 catch common regressions invisible to pure controller tests.

## 15. Key differences: stateless APIs, OAuth2, and MFA

**Stateless bearer token API:** requests require `Authorization: Bearer`; typically there is no form login or `HttpSession` authentication. Logging out a server session does not make signed JWTs disappear; token revocation, short-lived access tokens, and refresh-token rotation are needed. Test with JWT/security-specific helpers and real `Authorization` headers rather than copying `formLogin` tests.

**OAuth2/OIDC login:** redirects to an identity provider, uses state/nonce, callbacks, ID tokens, and different authentication principals; `@WithMockOAuth2User` can help controller tests without replacing integration login flow tests.

**MFA/2FA:** valid username/password does not mean fully authenticated under application policy; tests must check challenges and second factors, refusing protected URLs before MFA completion.

**Machine-to-machine Basic:** if still used, credentials require TLS, rotation, a secret store, rate limiting, and auditing. Browser form login is not suitable for machine clients. Security tests must show the app chose the right mechanism.

This example project **does not implement OAuth2/MFA/JWT** because each has its own contract. The critical rule is **never enable mechanisms the application does not use**.

## 16. Testing negative cases: do not measure 200 alone

A security test has value because it verifies cases are **properly denied**.

| Scenario | Expected response | Must also prove |
| --- | --- | --- |
| Anonymous visits auth-required page with browser Accept | 302 -> /login | Right redirect target, no data leak |
| Anonymous API Accept JSON | 401 | Basic challenge if HTTP Basic enabled |
| Wrong form password | 302 -> /login?error | Unauthenticated, no privileged session created |
| Wrong Basic credentials | 401 | Does not reuse previous request auth |
| Regular user enters /admin | 403 | Admin gets 200 to prove rule does not block everyone |
| POST missing CSRF | 403 | No side effect occurred |
| POST wrong CSRF token | 403 | No data leaked |
| Valid POST login | 302 + authenticated | New session request works |
| POST logout missing CSRF | 403 | Session remains valid |
| Valid POST logout | 302 + invalidated session | New request is unauthenticated |
| User request after session timeout | 401/302 | SecurityContext is gone |
| Basic request after form logout still sends valid Basic header | 200 may occur | Logout does not revoke passwords |
| Custom login success handler | Per policy | Saves SecurityContext properly, applies session policy |

**Distinguishing 401 and 403:** 401 usually means authentication/challenge is required; 403 means denied due to permissions or CSRF. When form login picks the entry point, unauthenticated requests can return **302** instead of 401. Read the request context and security chain accurately to evaluate tests.

## 17. Running Gradle and expected results

Requires Java 17+, a compatible Gradle Wrapper, and dependencies from Maven Central. Commands:

~~~bash
./gradlew clean test
./gradlew test --tests com.example.securityqa.FormLoginFlowTest
./gradlew test --tests com.example.securityqa.HttpBasicFlowTest
./gradlew test --tests com.example.securityqa.SessionFixationTest
./gradlew test --tests com.example.securityqa.LogoutFlowTest
./gradlew test --tests com.example.securityqa.CsrfAndRoleTest
./gradlew test --tests com.example.securityqa.RealHttpBasicTest
~~~

On Windows, use **`gradlew.bat`** with the same arguments. Tests are **designed to PASS when files/code/dependencies/config match the lesson**, though no Gradle run was observed during authoring. When using port 0/`RANDOM_PORT`, do not assert a hardcoded port.

### Expected result table

| Test | What is verified |
| --- | --- |
| anonymousBrowserIsRedirectedToLogin | 302 -> /login |
| successfulFormLoginPersistsAuthenticationInSession | 302 -> /private, alice authenticated, session GET 200 |
| wrongPasswordIsRejected | 302 -> /login?error, unauthenticated |
| loginWithoutCsrfIsForbidden | 403 |
| validBasicCredentialsReachProtectedEndpoint | 200, user alice |
| anonymousJsonRequestGetsBasicChallenge | 401, WWW-Authenticate Basic |
| wrongBasicPasswordGetsUnauthorized | 401 |
| userRoleCannotEnterAdminArea | 403 |
| adminRoleMayEnterAdminArea | 200 |
| successfulLoginChangesExistingSessionId | oldId differs from newId, authenticated session usable |
| postLogoutRequiresCsrfAndInvalidatesSession | 403 missing CSRF; POST with CSRF 302, session invalid |
| authenticatedPostWithoutCsrfIsForbidden | 403 |
| authenticatedPostWithValidCsrfIsAccepted | 200 |
| invalidCsrfTokenIsRejected | 403 |
| roleUserCannotAccessAdminEvenWithValidPassword | 403 |
| roleAdminCanAccessAdmin | 200 |
| publicEndpointDoesNotNeedLogin | 200 |
| basicCredentialsAreCheckedOverRealHttp | Real HTTP: 401 no header, 200 with valid Basic |

**Do not claim `BUILD SUCCESSFUL` stdout was observed.** If a real machine test fails due to version mismatches, multiple filter chains, or a custom CSRF repository, read the stacktrace and security debug logs and compare against the exact active configuration.

## 18. Practical troubleshooting

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| MockMvc GET /private returns 200 for anonymous | Security filters disabled, overbroad permitAll | Use `@AutoConfigureMockMvc` with filters; inspect `SecurityFilterChain` |
| Form login always returns 403 | Missing CSRF token | Use `formLogin()` or `post(...).with(csrf())` in tests |
| POST /logout returns 403 | Missing CSRF | Send POST with `csrf()`, do not disable globally |
| Form login with wrong password redirects like success | Wrong credentials/encoder fixture or test asserts only 302 | Assert redirect URL and `authenticated()`/`unauthenticated()` |
| Browser GET /private returns 302 when test expects 401 | Form entry point depends on `Accept` header | Set `Accept` and assert the matching entry point |
| API GET /private returns 401 despite `@WithMockUser` on another test | Authentication applies only to current test/request | Do not rely on state from another test |
| USER role accessing /admin returns 200 | Wrong `hasRole`/`hasAuthority` matcher | Assert both user forbidden and admin allowed |
| POST without CSRF still returns 200 | `csrf` disabled, overbroad ignore matcher, filters skipped | Inspect `CsrfFilter` and matchers |
| Session login follow-up GET redirects again | Forgot to pass session, `SecurityContext` not saved | Pass `MockHttpSession` and check `SecurityContextRepository` |
| Session ID does not change at login | Session fixation disabled / custom filter | Configure proper strategy, test old session and new ID |
| Logout redirects properly yet user stays authenticated | Custom logout forgot invalidate/clear context | Assert session invalid + subsequent request |
| Used `@WithMockUser` and assumed passwords were tested | Helper bypasses password login | Use `formLogin`/`httpBasic` with real credentials |
| Client still logs in after HTTP Basic logout | Credentials are still resent | Basic logout does not revoke passwords |
| Browser cookie not saved on localhost HTTP | `Secure` flag or `SameSite`/cookie config | Test HTTPS profile or adjust test cookie config |
| `@WebMvcTest` ignores role policy | Slice has different security config than production | `@Import` exact config or `@SpringBootTest` |
| Spring Boot has custom `SecurityFilterChain` yet login fails | `formLogin`/Basic not explicitly enabled | Check the DSL |
| Test depends on users/roles from previous class | Shared state or unclear account fixture | Separate fixtures / isolated profile |
| Session timeout test is flaky | Uses `Thread.sleep` and wall-clock timing | Mock session timeout or test TTL with bounded wait |
| `RANDOM_PORT` test fails guessing 8080 | Port is randomly allocated | Use `@LocalServerPort` |
| E2E login through reverse proxy gets wrong redirect/cookie | Forwarded headers/base path/TLS | Test production-like proxy/browser |

### Logging and information safety

You can enable **`org.springframework.security=DEBUG`** locally to diagnose matchers, filter chains, and authentication flows. **Never log plaintext passwords, Basic Authorization headers, session IDs, CSRF tokens, or authentication cookies** in public CI artifacts. Never copy security secrets out of logs or screenshots to create long-lived fixtures.

In apps with multiple `SecurityFilterChain` beans (browser + API), verify **`securityMatcher`** and **`@Order`** on each chain; an API path accidentally matching the browser chain can return 302 instead of 401. Test each URL separately with its matching `Accept`/`Authorization` headers.

## 19. Trimming tests while preserving evidence

You can design a minimal matrix per feature:

**Form login:** right password + wrong password + missing CSRF + redirect target + follow-up session request.

**HTTP Basic:** right, wrong, missing header, insufficient role; verify `WWW-Authenticate` and enforce HTTPS in deployment.

**Session:** login creates/saves authentication, session ID rotates, follow-up request has identity; if the app has timeout/concurrency control, add dedicated tests.

**Logout:** POST with/without CSRF, invalidates session, clears authentication, challenges post-logout access. If the app uses remember-me/custom tokens, add revocation/clear tests.

**Authorization/CSRF:** anonymous, USER, ADMIN, and safe/non-safe methods to separate 401/403. Test one public path to catch overly restrictive configs.

**Integration:** at least one HTTP-level test when redirects/cookies/TLS/reverse proxies are important contracts; do not force every unit test to boot a server.

The sample suite presents more than the minimal matrix so failure causes stay isolated during learning. In real projects, keep the cases that guard real risks and requirements rather than duplicating all tests for every endpoint.

## 20. Self-check exercises

**1.** Does `@WithMockUser(username="alice")` verify `alice`'s password? **No**, it injects a test `SecurityContext` without running form/Basic authentication.

**2.** What does form login `POST /login` without CSRF do by default? **403** when `CsrfFilter` is enabled and the token is missing.

**3.** Does `formLogin()` in `spring-security-test` generate a CSRF token automatically? **Yes**, the helper is designed for successful form requests.

**4.** Why is asserting only 302 on login insufficient? Because both success and failure can return 302; assert **`Location` + authentication state**.

**5.** Is anonymous `GET /private` always 401? **No**, when a form login entry point exists it may redirect 302 based on `Accept`/content negotiation.

**6.** Does Base64 in an HTTP Basic header encrypt data securely? **No**; HTTPS is mandatory.

**7.** What does an authenticated USER lacking `ROLE_ADMIN` receive on `/admin`? **403**.

**8.** Does a 403 from POST definitely mean a missing role? **No**; it can be caused by a missing/invalid CSRF token.

**9.** What is required to test session persistence? Log in for real, capture the post-login session, and send a **new request** carrying that session.

**10.** Why must login rotate the session ID? To prevent **session fixation**.

**11.** Does `changeSessionId` necessarily allocate a new `HttpSession` object? **No**, it may change the ID on the same session object.

**12.** In Spring Security 6, is setting `SecurityContextHolder` inside a custom login enough for the next request? **Not necessarily**; it must be saved to **`SecurityContextRepository`**.

**13.** Should `GET /logout` immediately invalidate the session when CSRF is enabled? **No**, the default is usually a confirmation page; POST logout with CSRF is the state-changing flow.

**14.** Can `POST /logout` without CSRF keep the session alive? **Yes**, the token is rejected and the logout filter never completes; tests should prove this.

**15.** What should successful logout verify besides redirect? **Session invalid**, `SecurityContext` gone, and a new request challenged.

**16.** Can a Basic request with the same credentials after form logout still get 200? **Yes**, logout does not revoke passwords.

**17.** Is `@AutoConfigureMockMvc(addFilters=false)` suitable for verifying security? **No**, it removes the filter chain under test.

**18.** Does a simple `@WebMvcTest` prove the production `SecurityFilterChain` is right? **No** if config/filters differ; use the real chain or full context.

**19.** Does `SessionCreationPolicy.STATELESS` fit testing saved `HttpSession` authentication? **No**, that is a different contract.

**20.** What should you do when an app uses bearer JWTs instead of forms/sessions? Test bearer tokens/resource server and token lifecycles; **do not** force `formLogin()`/session logout.

**21.** What can `Secure=true` cookies cause in a local HTTP browser? Browsers may refuse to store/send the cookie per HTTPS rules, causing login loops in browser tests.

**22.** Does `SameSite` replace all CSRF protection? **No**, a threat model and proper CSRF tokens are needed.

**23.** Why does MockMvc not prove cookie `SameSite` in real browsers? Because MockMvc does not execute a browser cookie jar, network stack, or TLS.

**24.** What is `@LocalServerPort` used for? Retrieving the actual random port when Spring Boot's real server starts.

**25.** When you only need to test `ROLE_ADMIN` permissions, must you re-test form login? **No**; `@WithMockUser` fits authorization-only tests, provided at least one separate integration test covers the real authentication flow.

### End-of-lesson QA checklist

- Did you confirm the app **actually uses** form login/Basic/sessions/logout rather than stateless bearer auth?
- Do tests run the real Spring Security filter chain without `addFilters=false`?
- Does custom `SecurityFilterChain` configure `formLogin`/`httpBasic`/`logout`/`csrf` explicitly per policy?
- Are there public, protected, and role-restricted URLs testing both allow and deny?
- Do form login tests cover right password, wrong password, missing CSRF, redirect URL, and authenticated assertions?
- Is there a protected GET in a new request carrying the **session from a real login**?
- Do HTTP Basic tests cover real `Authorization` headers, wrong credentials, 401 challenge, and role 403?
- Do CSRF tests cover missing/invalid/valid tokens on unsafe HTTP methods?
- Is CSRF kept enabled across the app rather than disabled just to make tests green?
- Does session fixation assert **`oldId` differs from `newId`**, without confusing session object identity?
- Do logout tests cover POST + CSRF, invalidation, and unauthenticated follow-up requests?
- Did you avoid assuming HTTP Basic logout revoked the password?
- Are 302, 401, and 403 distinguished per `Accept` headers and entry point?
- Is `@WithMockUser` restricted to authorization-focused tests rather than treated as proof of password/session handling?
- Are `HttpOnly`/`Secure`/`SameSite` cookies, timeouts, and reverse proxies tested when required by the app?
- Are test data/accounts safe profile fixtures without exposing real credentials?
- Are tests independent of execution order or leftover sessions from earlier methods?
- Were remember-me, custom authentication, and concurrency limits considered if enabled by the app?
- Were `RANDOM_PORT`/browser integration tests added where network/cookie UI behavior truly matters?
- Did you avoid claiming build/run output was observed without running Gradle?

**Conclusion:** Proper Spring Security testing requires **reproducing the exact mechanism real users/clients use**. Use **`formLogin()` + a follow-up session request** to verify login and persistence; use **`httpBasic()`** to verify `Authorization` headers and credentials; use **`csrf()`** to guard POST login/logout/actions; use **role assertions** to distinguish 401 and 403; and use **session ID rotation + logout invalidation** to protect the lifecycle. **`@WithMockUser`** is a great tool for authorization unit tests, yet never replaces proof of a real authentication flow. For browser/cookie/TLS/reverse-proxy behavior, add HTTP/browser integration tests as needed.

## Official references

- Spring Boot 3.4 — Spring Security auto-configuration: https://docs.spring.io/spring-boot/3.4/reference/web/spring-security.html
- Spring Security — Testing form-based authentication with MockMvc: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/form-login.html
- Spring Security — Testing HTTP Basic: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/http-basic.html
- Spring Security — Testing CSRF: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html
- Spring Security — Testing logout: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/logout.html
- Spring Security — Session management and fixation protection: https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html
- Spring Security — Logout architecture and default handlers: https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html
- Spring Security — MockMvc setup with springSecurity(): https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/setup.html
- Spring Security — Form login architecture: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/form.html
