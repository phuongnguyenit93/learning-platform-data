# Separating Multiple Login Mechanisms by SecurityFilterChain in Spring Security

## 1. Capstone Practical Problem

A single Spring Boot application often serves multiple client types with different authentication flows: browser users sign in via an HTML form and keep a session; CLIs/services call APIs using HTTP Basic or Bearer tokens; internal staff use SSO/OIDC; administrators require stronger authentication. Putting all of these into one configuration without clear boundaries leads to APIs redirecting to HTML login pages, browser sessions leaking into API routes, or new endpoints falling outside every filter chain and staying unprotected.

The goal is to deploy **multiple `SecurityFilterChain` beans in the same application**, separated by URL scope, authentication entry point, session policy, and CSRF policy. The core lab comprises:

1. **`/api/**` zone**: HTTP Basic, **stateless**, GET-only, returning **401** when credentials are missing.
2. **`/web/**` zone**: form login, **HttpSession**, CSRF enabled, returning **302** to the login page when unauthenticated.
3. **Fallback chain** without a `securityMatcher`: rejects all remaining paths with `denyAll()`.

Both zones share the same sample `UserDetailsService` for easy observation; we will prove that **a form session does not authenticate HTTP Basic**, and **HTTP Basic does not create a web login session**. Later sections expand the architecture to OAuth2 Resource Server JWT, OIDC/SSO, and segregated identity stores.

### Target Outcomes

- Explain why `FilterChainProxy` selects the **first matching `SecurityFilterChain`** rather than merging chains.
- Distinguish `securityMatcher` (selects the whole chain) from `requestMatchers` inside `authorizeHttpRequests` (selects rules within that chain).
- Order chains with `@Order`, narrow matchers first and fallback last.
- Keep `loginPage`, `loginProcessingUrl`, logout, and OAuth2 callbacks inside the appropriate matcher.
- Distinguish HTTP **401 Basic challenge**, HTTP **302 form redirect**, and HTTP **403 authorization/CSRF**.
- Keep CSRF enabled on browser routes without disabling CSRF globally just because the app exposes APIs.
- Write Java 17 / Spring Security 6.x / JUnit 5 / MockMvc integration tests covering paths, session boundaries, and negative cases.

**Important limitation:** HTTP Basic is an **illustrative** choice for localhost GET APIs, not a default recommendation for mobile or public production APIs. Basic sends passwords in a merely Base64-encoded header, making **HTTPS mandatory** outside localhost. Browsers can also resend Basic credentials automatically in some contexts; if a Basic API supports mutations, evaluate CSRF rather than assuming `STATELESS` makes it safe automatically.

## 2. How Does FilterChainProxy Select a Chain?

~~~text
HTTP request
   |
   v
DelegatingFilterProxy
   |
   v
FilterChainProxy
   |
   +-- try chain @Order(1), matcher=/api/**
   |        match → use API filter list and STOP matching
   |
   +-- try chain @Order(2), matcher=/web/**
   |        match → use WEB filter list and STOP matching
   |
   +-- chain @Order(3), unrestricted matcher
            always matches → denyAll()
~~~

**Only the first matching chain runs for a given request.** Spring Security does not execute the API chain and then stack the WEB chain's filters on top.

| Concept | Role | Consequence |
|---|---|---|
| `http.securityMatcher("/api/**")` | Decides which chain handles the request | Defines filter chain scope |
| `http.authorizeHttpRequests(...)` | Configures permissions inside the matched chain | Does not widen the chain matcher |
| `requestMatchers("/api/admin")` | Applies rules to endpoints inside the chain | Cannot protect URLs outside the chain |
| `anyRequest()` | Remaining paths *within that chain* | Does not replace a catch-all fallback chain |
| `@Order(1)` | High priority | Can shadow later chains if matcher is too broad |
| Fallback without `securityMatcher` | Matches all remaining paths | Prevents unguarded URLs |

A common mistake:

~~~java
// Wrong: /web/login is outside the /api/** scope.
// requestMatchers().permitAll() here will never apply to /web/login.
http.securityMatcher("/api/**")
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/web/login").permitAll()
        .anyRequest().authenticated());
~~~

**If no chain matches**, the request can pass straight to Servlet/MVC **without Spring Security protection**. That is why the example explicitly adds a fallback chain.

## 3. Route Matrix and Expected Behavior

| Method + URL | Chain | Authentication | Intended Outcome |
|---|---|---|---|
| GET /api/whoami | API | Basic | 200 when valid, 401 when missing/wrong |
| GET /api/admin | API | Basic + ROLE_ADMIN | 200 for admin, 403 for USER |
| POST /api/whoami | API | Not permitted | Rejected |
| GET /web/login | WEB | Anonymous | 200, HTML form with CSRF |
| POST /web/login | WEB | Username/password + CSRF | Login success or failure |
| GET /web/home | WEB | Session | 200 when logged in, 302 if anonymous |
| GET /web/admin | WEB | Session + ROLE_ADMIN | 200 admin, 403 USER |
| POST /web/logout | WEB | Session + CSRF | Logout and redirect |
| GET /unmapped | Fallback | No login | 403 in demo config |

We intentionally **omit POST/PUT/PATCH/DELETE on the Basic API**. When exposing state-changing APIs, decide credential and CSRF policies based on real browsers, proxies, and clients.

### Boundary Between API and WEB

~~~text
CLI/API client                              Browser
    |                                         |
    | Authorization: Basic ...                | JSESSIONID cookie
    v                                         v
/api/**                                    /web/**
    |                                         |
API chain                                 WEB chain
    |                                         |
httpBasic                                  formLogin
STATELESS                                  HttpSession
401 challenge                              302 /web/login
    |                                         |
    +----------------+------------------------+
                     |
            UserDetailsService
            PasswordEncoder
            Authorization rules
~~~

Splitting chains **does not automatically split identities**: if both mechanisms share a user store, the same account can still use its password on both, though how `Authentication` is created and retained differs. If policy requires service-account identities never to log into WEB, separate their providers/managers/stores.

## 4. Creating the Java 17 and Spring Boot 3.5.7 Project

Project structure:

~~~text
multiple-login-chains/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/multichain/
    │   │   ├── MultiChainApplication.java
    │   │   ├── SecurityConfiguration.java
    │   │   ├── LoginPageController.java
    │   │   └── DemoController.java
    │   └── resources/
    │       ├── application.yml
    │       └── templates/login.html
    └── test/
        └── java/com/example/multichain/
            └── MultipleSecurityChainsTest.java
~~~

### 4.1. pom.xml

~~~xml
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
    <artifactId>multiple-login-chains</artifactId>
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
            <artifactId>spring-boot-starter-thymeleaf</artifactId>
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

The Spring Boot BOM manages compatible Spring Security dependencies. `spring-security-test` is test-scoped; never use test identity helpers in production.

### 4.2. application.yml

File `src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080

demo:
  password: ${DEMO_PASSWORD}
~~~

Set `DEMO_PASSWORD` via your local environment. JUnit overrides `demo.password` with a dedicated test value in `@SpringBootTest(properties=...)`.

### 4.3. MultiChainApplication.java

~~~java
package com.example.multichain;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MultiChainApplication {
    public static void main(String[] args) {
        SpringApplication.run(MultiChainApplication.class, args);
    }
}
~~~

## 5. Scoped SecurityFilterChain Configuration

File `src/main/java/com/example/multichain/SecurityConfiguration.java`:

~~~java
package com.example.multichain;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(
            PasswordEncoder encoder,
            @Value("${demo.password}") String password) {

        var alice = User.withUsername("alice")
                .password(encoder.encode(password))
                .roles("USER")
                .build();

        var admin = User.withUsername("admin")
                .password(encoder.encode(password))
                .roles("ADMIN")
                .build();

        return new InMemoryUserDetailsManager(alice, admin);
    }

    @Bean
    @Order(1)
    SecurityFilterChain apiSecurity(HttpSecurity http)
            throws Exception {

        return http
                .securityMatcher("/api/**")
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(
                                HttpMethod.GET, "/api/admin")
                            .hasRole("ADMIN")
                        .requestMatchers(
                                HttpMethod.GET, "/api/whoami")
                            .authenticated()
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .sessionManagement(session -> session
                        .sessionCreationPolicy(
                                SessionCreationPolicy.STATELESS))
                .requestCache(cache -> cache.disable())
                // CSRF remains enabled by default; demo API is GET-only.
                .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain webSecurity(HttpSecurity http)
            throws Exception {

        return http
                .securityMatcher("/web/**")
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/web/login")
                            .permitAll()
                        .requestMatchers(
                                HttpMethod.GET, "/web/admin")
                            .hasRole("ADMIN")
                        .requestMatchers(
                                HttpMethod.GET, "/web/home")
                            .authenticated()
                        .anyRequest().denyAll())
                .formLogin(form -> form
                        .loginPage("/web/login")
                        .loginProcessingUrl("/web/login")
                        .defaultSuccessUrl("/web/home", true)
                        .failureUrl("/web/login?error")
                        .permitAll())
                .logout(logout -> logout
                        .logoutUrl("/web/logout")
                        .logoutSuccessUrl("/web/login?logout"))
                .build();
    }

    @Bean
    @Order(3)
    SecurityFilterChain fallbackSecurity(HttpSecurity http)
            throws Exception {

        // No securityMatcher: the last chain matches every remaining URL.
        return http
                .authorizeHttpRequests(auth -> auth
                        .anyRequest().denyAll())
                .build();
    }
}
~~~

### 5.1. Why Does This Configuration Matter?

**API chain:**
- Covers only `/api/**`.
- Conditionally permits only two GET URLs; all other requests hit `denyAll`.
- No `.formLogin()`; `httpBasic()` provides the Basic authentication challenge.
- `STATELESS` prevents Spring Security from reading `SecurityContext` from `HttpSession`.
- `requestCache.disable()` avoids browser-style saved requests/redirects.
- CSRF is not disabled globally.

**WEB chain:**
- Covers only `/web/**`.
- GET/POST `/web/login` serves as the login route.
- `formLogin` authenticates username/password; MVC renders the GET page.
- `/web/logout` is the logout processing URL.
- Uses sessions and default CSRF protection.
- Basic auth is not enabled on the WEB chain.

**Fallback chain:**
- Has no `securityMatcher`, so unmatched URLs are still evaluated by Spring Security.
- Provides no login mechanism that could accidentally grant access to unexpected paths.
- `denyAll()` explicitly rejects rather than relying on the absence of a controller for protection.

### 5.2. Why Cannot @Order Be Ignored?

An `@Order(1)` chain with `securityMatcher("/**")` captures every URL and starves all later chains. Putting the fallback first blocks the entire application. Omitting the fallback leaves any new controller under `/debug` or `/reports` unprotected by Spring Security.

Treat `@Order` as a regression-tested part of security configuration, not cosmetic metadata.

## 6. Custom Login Page and CSRF

Because `.loginPage("/web/login")` is configured, Spring Security does not generate its built-in HTML page. We supply an MVC controller for **GET** and a template; **POST** is handled by `UsernamePasswordAuthenticationFilter`.

### 6.1. LoginPageController.java

~~~java
package com.example.multichain;

import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
public class LoginPageController {

    @GetMapping("/web/login")
    public String login() {
        return "login";
    }
}
~~~

Never create `@PostMapping("/web/login")` to compare passwords manually. Doing so easily bypasses `AuthenticationManager`, `PasswordEncoder`, CSRF/session fixation protections, and authentication events.

### 6.2. templates/login.html

~~~html
<!doctype html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="utf-8">
  <title>WEB login</title>
</head>
<body>
  <h1>WEB Sign In</h1>
  <p th:if="${param.error}">
    Invalid credentials.
  </p>
  <p th:if="${param.logout}">
    You have been logged out.
  </p>
  <form th:action="@{/web/login}" method="post">
    <label for="username">Username</label>
    <input id="username" name="username"
           autocomplete="username" required>

    <label for="password">Password</label>
    <input id="password" name="password" type="password"
           autocomplete="current-password" required>

    <button type="submit">Sign In</button>
  </form>
</body>
</html>
~~~

Thymeleaf integrates Spring MVC's `RequestDataValueProcessor` to **automatically inject a hidden CSRF token** into POST forms using `th:action`. Inspect rendered HTML in the browser to confirm an input with `name="_csrf"` is present.

Do not add a second hidden CSRF field when the view engine already renders one; duplicate parameters can break token validation. With other template engines, render the CSRF token from the request attribute/server-side repository. Never copy one user's token into another session.

### 6.3. Why Does permitAll Still Require CSRF?

`requestMatchers("/web/login").permitAll()` only permits anonymous access at the **authorization** layer. `CsrfFilter` still inspects POSTs and can return 403 **before the password ever reaches `AuthenticationProvider`**.

If POST login returns 403, inspect the CSRF parameter/session rather than disabling CSRF globally or changing the password encoder before confirming the provider ran.

## 7. API and WEB Controllers

File `src/main/java/com/example/multichain/DemoController.java`:

~~~java
package com.example.multichain;

import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/api/whoami")
    public Map<String, String> apiWhoami(
            Authentication authentication) {
        return Map.of(
                "principal", authentication.getName(),
                "channel", "api-basic");
    }

    @GetMapping("/api/admin")
    public Map<String, String> apiAdmin(
            Authentication authentication) {
        return Map.of(
                "principal", authentication.getName(),
                "resource", "api-admin");
    }

    @GetMapping("/web/home")
    public Map<String, String> webHome(
            Authentication authentication) {
        return Map.of(
                "principal", authentication.getName(),
                "channel", "web-form");
    }

    @GetMapping("/web/admin")
    public Map<String, String> webAdmin(
            Authentication authentication) {
        return Map.of(
                "principal", authentication.getName(),
                "resource", "web-admin");
    }
}
~~~

Even though both endpoint groups return JSON, chain selection depends strictly on the **HTTP path request matcher**, not the response content type.

`ROLE_ADMIN` is checked with `hasRole("ADMIN")` (matching the `ROLE_ADMIN` authority). Basic `alice` holds `ROLE_USER` and is denied at `/api/admin`; `alice`'s WEB session is likewise denied at `/web/admin`.

## 8. Running the Demo with Maven, curl, and a Browser

In the project directory with JDK 17+ and Maven:

Linux/macOS:

~~~bash
export DEMO_PASSWORD='local-training-password-only'
mvn spring-boot:run
~~~

PowerShell:

~~~powershell
$env:DEMO_PASSWORD = "local-training-password-only"
mvn spring-boot:run
~~~

This is an example password strictly for **localhost**. Never use it for production accounts or expose the demo environment to the Internet.

### 8.1. Anonymous API

~~~bash
curl -i http://localhost:8080/api/whoami
~~~

Expect **401 Unauthorized** with `WWW-Authenticate: Basic ...` (exact header details vary by config). **Never** redirected to `/web/login`.

### 8.2. Valid Basic API

~~~bash
curl -i -u "alice:local-training-password-only"   http://localhost:8080/api/whoami
~~~

Expect status 200 and JSON equivalent to:

~~~json
{"principal":"alice","channel":"api-basic"}
~~~

In PowerShell, use `curl.exe` if the `curl` alias differs:

~~~powershell
curl.exe -i -u "alice:local-training-password-only" "http://localhost:8080/api/whoami"
~~~

**Warning:** passing `curl -u` on the command line can record credentials in shell history or expose them via process inspection. This example is strictly for local learning; real environments must use secret management and avoid logging credentials.

### 8.3. Invalid Basic API

~~~bash
curl -i -u "alice:wrong"   http://localhost:8080/api/whoami
~~~

Expect 401, with no web session created.

### 8.4. Anonymous WEB

~~~bash
curl -i http://localhost:8080/web/home
~~~

Expect a 302 redirect to `/web/login`. Visit `http://localhost:8080/web/login` in a browser and enter `alice` and the demo password; afterward, `GET /web/home` returns JSON equivalent to:

~~~json
{"principal":"alice","channel":"web-form"}
~~~

Do not send a bare POST form without a CSRF token and conclude the password was wrong. The browser must submit the form token and cookie from **the same session**.

### 8.5. Fallback

~~~bash
curl -i http://localhost:8080/unmapped
~~~

Expect denial (typically 403 under the demo's default handler) rather than public access via Spring MVC.

## 9. JUnit 5 + MockMvc: Proving Two Independent Chains

The tests below run against the **real `SecurityFilterChain` beans in the ApplicationContext** with `spring-security-test`. They verify not only happy paths, but also status codes, roles, CSRF, session isolation, and the fallback chain.

File `src/test/java/com/example/multichain/MultipleSecurityChainsTest.java`:

~~~java
package com.example.multichain;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.hamcrest.Matchers.containsString;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestBuilders.logout;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.security.test.web.servlet.response
        .SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.security.test.web.servlet.response
        .SecurityMockMvcResultMatchers.unauthenticated;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest(properties =
        "demo.password=local-only-test-password")
@AutoConfigureMockMvc
class MultipleSecurityChainsTest {

    @Autowired
    MockMvc mvc;

    private static final String PASSWORD =
            "local-only-test-password";

    private MockHttpSession webLogin(String username)
            throws Exception {
        MvcResult result = mvc.perform(
                formLogin("/web/login")
                    .user(username)
                    .password(PASSWORD))
            .andExpect(status().is3xxRedirection())
            .andExpect(authenticated().withUsername(username))
            .andReturn();

        MockHttpSession session =
                (MockHttpSession)
                    result.getRequest().getSession(false);
        assertNotNull(session);
        return session;
    }

    @Test
    void apiAnonymousGets401() throws Exception {
        mvc.perform(get("/api/whoami"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void apiBasicCorrectPasswordGets200() throws Exception {
        mvc.perform(get("/api/whoami")
                .with(httpBasic("alice", PASSWORD)))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.principal").value("alice"))
            .andExpect(jsonPath("$.channel").value("api-basic"));
    }

    @Test
    void apiBasicWrongPasswordGets401() throws Exception {
        mvc.perform(get("/api/whoami")
                .with(httpBasic("alice", "wrong")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void apiRoleUserCannotAccessAdmin() throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic("alice", PASSWORD)))
            .andExpect(status().isForbidden());
    }

    @Test
    void apiRoleAdminCanAccessAdmin() throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic("admin", PASSWORD)))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.resource").value("api-admin"));
    }

    @Test
    void apiPostIsDeniedEvenWithCredentialsAndCsrf()
            throws Exception {
        mvc.perform(post("/api/whoami")
                .with(httpBasic("alice", PASSWORD))
                .with(csrf()))
            .andExpect(status().isForbidden());
    }

    @Test
    void webAnonymousRedirectsToFormLogin()
            throws Exception {
        mvc.perform(get("/web/home"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/web/login"));
    }

    @Test
    void webLoginPageRendersCsrf() throws Exception {
        mvc.perform(get("/web/login"))
            .andExpect(status().isOk())
            .andExpect(content().string(
                    containsString("name=\"_csrf\"")));
    }

    @Test
    void webSessionAllowsHome() throws Exception {
        MockHttpSession session = webLogin("alice");

        mvc.perform(get("/web/home").session(session))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.principal").value("alice"))
            .andExpect(jsonPath("$.channel").value("web-form"));
    }

    @Test
    void webWrongPasswordRedirectsToError()
            throws Exception {
        mvc.perform(formLogin("/web/login")
                .user("alice")
                .password("wrong"))
            .andExpect(unauthenticated())
            .andExpect(redirectedUrl("/web/login?error"));
    }

    @Test
    void webLoginWithoutCsrfIsForbidden()
            throws Exception {
        mvc.perform(post("/web/login")
                .param("username", "alice")
                .param("password", PASSWORD))
            .andExpect(status().isForbidden());
    }

    @Test
    void webSessionDoesNotAuthenticateStatelessApi()
            throws Exception {
        MockHttpSession session = webLogin("alice");

        mvc.perform(get("/api/whoami").session(session))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void apiBasicHeaderDoesNotAuthenticateWeb()
            throws Exception {
        mvc.perform(get("/web/home")
                .with(httpBasic("alice", PASSWORD)))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/web/login"));
    }

    @Test
    void webAdminRequiresAdminRole() throws Exception {
        MockHttpSession alice = webLogin("alice");
        mvc.perform(get("/web/admin").session(alice))
            .andExpect(status().isForbidden());

        MockHttpSession admin = webLogin("admin");
        mvc.perform(get("/web/admin").session(admin))
            .andExpect(status().isOk());
    }

    @Test
    void webLogoutUsesWebChain() throws Exception {
        MockHttpSession session = webLogin("alice");
        mvc.perform(logout("/web/logout").session(session))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/web/login?logout"));
    }

    @Test
    void unmatchedPathIsDeniedByFallback()
            throws Exception {
        mvc.perform(get("/unmapped"))
            .andExpect(status().isForbidden());
    }
}
~~~

### 9.1. Running Tests

~~~bash
mvn clean test
~~~

**Expectation:** **16 tests** pass with Java 17+, Maven, and compatible dependencies; Maven Surefire reports reside under `target/surefire-reports/`. Timings and Maven output vary by machine; exact byte-for-byte stdout is not guaranteed.

**Boundary of conclusions:** these are MockMvc integration tests exercising real security filters and the password encoder inside an in-process ApplicationContext; they do not prove HTTPS termination, Redis session stores, external IAM/IdP integration, or token signature verification.

### 9.2. The Two Most Important Tests

~~~java
// A WEB session is insufficient to authenticate the stateless Basic API.
mvc.perform(get("/api/whoami").session(webSession))
    .andExpect(status().isUnauthorized());

// A valid Basic header does not create a WEB form session.
mvc.perform(get("/web/home")
        .with(httpBasic("alice", PASSWORD)))
    .andExpect(redirectedUrl("/web/login"));
~~~

This provides request/response proof of mechanism isolation, beyond merely having multiple `SecurityFilterChain` `@Bean` methods in Java.

### 9.3. Purposeful Test Helpers

- `formLogin("/web/login")` posts to the custom processing URL and attaches a valid test CSRF token automatically.
- Parameterless `formLogin()` targets **POST /login** by default, which falls outside the WEB matcher.
- `httpBasic("alice", password)` adds an Authorization header for API tests without creating a form-login session.
- `logout("/web/logout")` builds a logout request to the right URL with a CSRF token.
- `.with(csrf())` is for valid POST tests; to test **missing** CSRF, use a raw POST without the helper.
- `@AutoConfigureMockMvc` must keep security filters active; never set `addFilters=false` just to silence 401/403 errors.

## 10. Standalone Java 17: Simulating First Matching Chain

This sample merely illustrates the **idea** of path-based chain selection without Spring Security and does not replace real `RequestMatcher` semantics. Java file: **FirstMatchDemo.java**.

~~~java
public final class FirstMatchDemo {

    static String choose(String path) {
        if (path.startsWith("/api/")) return "API_BASIC";
        if (path.startsWith("/web/")) return "WEB_FORM";
        return "DENY_FALLBACK";
    }

    static void show(String path) {
        System.out.println(path + " -> " + choose(path));
    }

    public static void main(String[] args) {
        show("/api/whoami");
        show("/web/login");
        show("/web/home");
        show("/oauth2/authorization/demo");
        show("/unmapped");
    }
}
~~~

Command:

~~~bash
javac FirstMatchDemo.java
java FirstMatchDemo
~~~

**Exact stdout:**

~~~text
/api/whoami -> API_BASIC
/web/login -> WEB_FORM
/web/home -> WEB_FORM
/oauth2/authorization/demo -> DENY_FALLBACK
/unmapped -> DENY_FALLBACK
~~~

Real Spring Security evaluates matchers against servlet/MVC request context; the simulation above does not capture edge cases like encoded paths, trailing slashes, or path rewrites. In production, use `securityMatcher` and real HTTP tests.

## 11. CSRF, Sessions, and Logout Must Not Bleed Across Chains

### 11.1. WEB Form Login

~~~text
GET /web/home (anonymous)
   → WEB chain
   → 302 /web/login

GET /web/login
   → MVC renders login.html + CSRF input

POST /web/login with valid CSRF
   → CsrfFilter
   → UsernamePasswordAuthenticationFilter
   → AuthenticationManager / Provider
   → save SecurityContext into HttpSession
   → 302 /web/home

POST /web/logout with valid CSRF
   → WEB chain's LogoutFilter
   → invalidate session + clear security context
   → redirect /web/login?logout
~~~

If `POST /web/login` lacks CSRF, `CsrfFilter` may return 403 before the provider runs. Never "fix" this by disabling CSRF broadly.

### 11.2. API Basic

~~~text
GET /api/whoami
   → API chain
   → BasicAuthenticationFilter
   → Authorization: Basic ... ?
      NO  → 401 challenge
      YES → AuthenticationManager / PasswordEncoder
   → GET endpoint allowed if authenticated
~~~

`SessionCreationPolicy.STATELESS` ensures Spring Security **does not use `HttpSession` as the API chain's SecurityContext repository**. Every Basic request must supply its own credentials; web session cookies do not authenticate it.

### 11.3. CSRF on Basic APIs with Mutations

Never equate "stateless HTTP Basic" with "browsers cannot be CSRF'd". Browsers can cache and automatically resend Basic credentials. That is why the demo restricts the API to GET; if adding POST/PUT/DELETE, you must:
- determine whether clients can be browsers;
- determine which credentials are attached automatically;
- maintain CSRF/token controls where appropriate;
- consider switching to a Bearer-only Resource Server or mTLS;
- add negative tests for cross-origin/CSRF scenarios.

### 11.4. CORS Does Not Replace CSRF

CORS controls which origins may read responses or issue certain cross-origin JS requests; CSRF protects state-changing requests carrying ambient credentials. API clients needing CORS never justify disabling CSRF on browser session routes. Configure both per threat model on the exact filter chain.

## 12. Login URL, Callback URL, and Logout URL Must Belong to the Right Chain

For form login, the chain must cover all related URLs:
- GET login page: `/web/login`;
- POST login-processing URL: `/web/login`;
- success redirect: `/web/home`;
- error redirect: `/web/login?error`;
- POST logout: `/web/logout`;
- logout success: `/web/login?logout`.

If you write:

~~~java
http.securityMatcher("/web/**")
    .formLogin(form -> form
        .loginPage("/login")
        .loginProcessingUrl("/login"));
~~~

then `/login` sits **outside** `/web/**`: the page and processing endpoint may be caught by the fallback or go unhandled by the filter. Place URLs under the same prefix or expand the matcher explicitly.

Similarly, SSO/OIDC commonly uses:
- `/oauth2/authorization/{registrationId}`;
- `/login/oauth2/code/{registrationId}` for the callback.

If the browser chain only matches `/web/**`, default OIDC endpoints sit outside it. Adjust the matcher or endpoint base URIs alongside IdP redirect URI config—never disable the fallback to let callbacks "pass freely".

## 13. Extending the API to a Bearer JWT Resource Server

In production, an HTTP Basic API can be replaced by Bearer access tokens from an OAuth2 Authorization Server. Keep **a single** clearly defined API chain rather than adding multiple `@Order(1)` chains with overlapping matchers and guessing which wins.

### 13.1. New Dependency

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
</dependency>
~~~

### 13.2. Replacement API JWT Chain Sample

~~~java
@Bean
@Order(1)
SecurityFilterChain jwtApi(HttpSecurity http)
        throws Exception {

    return http
            .securityMatcher("/api/**")
            .sessionManagement(s -> s
                .sessionCreationPolicy(
                    SessionCreationPolicy.STATELESS))
            .csrf(csrf -> csrf.disable())
            .authorizeHttpRequests(a -> a
                .requestMatchers(
                    HttpMethod.GET, "/api/admin")
                    .hasAuthority("SCOPE_api.admin")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth -> oauth
                .jwt(Customizer.withDefaults()))
            .build();
}
~~~

This is an **illustrative replacement snippet**, not runnable standalone. You must configure `JwtDecoder`, a trusted issuer, and a key source, for example:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.org/realms/demo
~~~

The URL above is **strictly a configuration example**. Production must validate signatures, issuer, expiration, `nbf`, audience, scopes/roles/tenant mappings, and key rotation/revocation processes. **Default configuration does not automatically validate an API-specific audience** unless a proper validator is added.

Disabling CSRF in the JWT snippet is appropriate only when the API is truly **Bearer-only and rejects cookies, HTTP Basic, and ambient browser credentials**. Never apply that snippet to the WEB form chain.

### 13.3. Mock JWT Tests Are Not Signature Tests

In MockMvc, the `jwt()` post-processor creates a mock authentication to test `SCOPE_api.admin` rules:

~~~java
mvc.perform(get("/api/admin")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_api.admin"))))
    .andExpect(status().isOk());
~~~

Import `jwt`, `SimpleGrantedAuthority`, and MockMvc helpers. However, this helper **does not prove real JWT signature/issuer/audience validation**. To test the cryptographic path, send signed test tokens through the configured decoder using trusted JWK/issuer fixtures.

## 14. Extending Browser Login to OIDC/SSO

When replacing `formLogin` with `oauth2Login`, Spring Security manages:
- the authorization-request initiation endpoint;
- redirecting to the Identity Provider;
- the callback / authorization-code exchange;
- state/nonce/ID token validation, UserInfo, and principal mapping;
- the browser session.

Default URLs `/oauth2/authorization/**` and `/login/oauth2/code/**` may sit **outside** a `/web/**` matcher.

One way to expand the matcher:

~~~java
http.securityMatcher(
        "/web/**",
        "/oauth2/authorization/**",
        "/login/oauth2/code/**")
    .oauth2Login(Customizer.withDefaults());
~~~

The snippet omits `spring-boot-starter-oauth2-client`, `ClientRegistration`, IdP issuer, client credentials, and redirect URIs. It illustrates **matcher scope only**, not a complete runnable OIDC application.

OAuth2 tests must distinguish:
- Mock principals from `oauth2Login()` / `oidcLogin()`: authorization layer post-authentication.
- Real integration flows with an IdP / test Authorization Server: redirects, state, nonce, token signatures, issuer/audience, and user mapping.

**Never remove the `denyAll` fallback to let callbacks through.** Add the callback paths to the right chain and enforce protocol protections on them.

## 15. Segregating Identity Stores, Providers, and AuthenticationManagers

Both chains in the demo share one `UserDetailsService`. That is **mechanism isolation**, not **identity isolation**. When business rules require:
- web users to enter browsers only via OIDC/MFA;
- service accounts to call APIs only via mTLS or Client Credentials;
- admins to reach routes only with step-up auth;

then configure separate `AuthenticationManager`/`AuthenticationProvider` beans and user/token stores per chain.

Skeleton example:

~~~java
// Illustrative snippet in the service API configuration.
// apiManager must be built from providers serving service identities.
@Bean
@Order(1)
SecurityFilterChain apiSecurity(
        HttpSecurity http, AuthenticationManager apiManager)
        throws Exception {

    return http
        .securityMatcher("/api/**")
        .authenticationManager(apiManager)
        .authorizeHttpRequests(a -> a
            .anyRequest().authenticated())
        .httpBasic(Customizer.withDefaults())
        .sessionManagement(s -> s
            .sessionCreationPolicy(
                SessionCreationPolicy.STATELESS))
        .build();
}
~~~

**Not a standalone runnable program:** you must declare `apiManager`, providers, and appropriate CSRF/method policies. `http.authenticationManager(...)` assigns a per-chain manager instead of relying on a single global provider.

HTTP-layer authorization does not replace object-level authorization: an authenticated `ROLE_ADMIN` may still not be allowed to modify another tenant's resources. Verify active privileges at the service/DB layer along with account status and resource ownership.

## 16. Testing Matcher Mistakes and Chain Ordering Bugs

### Case A — API Matcher Broader Than Intended

~~~java
@Order(1)
SecurityFilterChain api(HttpSecurity http) throws Exception {
    return http.securityMatcher("/**")
        .httpBasic(Customizer.withDefaults())
        .authorizeHttpRequests(a ->
            a.anyRequest().authenticated())
        .build();
}
~~~

Because the first chain matches every URL, the WEB chain behind it never runs. Anonymous `/web/home` requests receive a Basic challenge instead of redirecting to form login.

### Case B — requestMatchers Outside securityMatcher

~~~java
http.securityMatcher("/api/**")
    .authorizeHttpRequests(a -> a
        .requestMatchers("/web/login").permitAll()
        .anyRequest().authenticated());
~~~

The `/web/login` rule has no effect because those requests never enter the API chain.

### Case C — Missing Fallback

~~~text
@Order(1): /api/**
@Order(2): /web/**
(no catch-all chain)
~~~

A new URL like `/debug`, `/actuator`, or `/internal` matches no chain. Never assume "because `anyRequest` is in the API chain, every URL is protected". To cover the whole app, add a fallback chain with no matcher restriction.

### Case D — Login/Callback Outside the Chain

Form login `/login` sits outside `/web/**`, or `/login/oauth2/code/**` gets denied by the fallback. Fix the matcher/processing URL rather than disabling security on callbacks.

### Case E — Path Variants

Paths like `/api` (no trailing slash), trailing slashes, encoded characters, context paths, and proxy rewrites affect matchers. Never build custom `startsWith` security checks outside Spring to "patch" paths. Test with `RequestMatcher`, `HttpFirewall`, and the exact URLs exposed at ingress.

### Case F — Basic API POST Missing CSRF

A POST may get 403 from `CsrfFilter` **before** authorization rules run. A POST with valid CSRF is still rejected by `denyAll()`. These are two separate mechanisms; never treat a 403 status alone as proof of which rule blocked the request.

## 17. Monitoring and Regression Checks

Recommended checks on every deploy:
1. Startup logs list the exact expected `SecurityFilterChain` beans and filter lists.
2. `/api/**` without credentials → 401, not 302.
3. `/web/**` anonymous → 302 to the right login page, not 401 Basic.
4. WEB form POST with valid CSRF reaches `AuthenticationManager`.
5. API Basic creates no web session.
6. Web session does not authenticate the stateless API.
7. Role USER is blocked on both admin endpoints.
8. Fallback denies unmapped URLs.
9. Logout URL and session invalidation work properly.
10. OAuth2 callback/refresh/token endpoints sit inside the right chain when SSO is used.
11. CSRF/CORS/session cookies behave properly behind reverse proxies and multi-replica clusters.
12. Tests keep security filters active: never use `@AutoConfigureMockMvc(addFilters=false)`.

Enable DEBUG logging in diagnostic environments:

~~~yaml
logging:
  level:
    org.springframework.security: DEBUG
~~~

Inspect `DefaultSecurityFilterChain` startup logs and request routing. Never log `Authorization`, `Cookie`, passwords, raw tokens, or session IDs; observe via correlation IDs, route templates, chain types, and HTTP status codes.

You can inspect filter lists via `FilterChainProxy.getFilters("/api/whoami")` and `getFilters("/web/home")` in targeted integration tests, yet **request→response tests** remain essential to prove entry points, providers, sessions, and authorization work together.

## 18. Comprehensive QA Matrix

| Case | Expected |
|---|---|
| GET /api/whoami anonymous | 401 |
| GET /api/whoami valid Basic | 200 |
| GET /api/whoami invalid Basic | 401 |
| GET /api/admin Basic alice USER | 403 |
| GET /api/admin Basic admin | 200 |
| POST /api/whoami Basic + CSRF | 403 from `denyAll` |
| GET /web/login | 200, with CSRF form |
| GET /web/home anonymous | 302 /web/login |
| POST /web/login valid + CSRF | Creates authenticated session |
| POST /web/login invalid + CSRF | Redirects /web/login?error |
| POST /web/login missing CSRF | 403 |
| GET /web/home with alice session | 200 |
| GET /web/admin with alice session | 403 |
| GET /web/admin with admin session | 200 |
| Web session without Basic, GET /api/whoami | 401 |
| Basic header without web session, GET /web/home | 302 |
| POST /web/logout with CSRF | Logs out and redirects |
| GET /unmapped | 403 via fallback |
| API path matched into WEB | Regression failure |
| Form endpoint outside WEB matcher | Regression failure |
| OAuth2 callback outside chain | Denied by fallback, fix matcher |
| Mock JWT principal | Authorization check only |
| Real JWT bad issuer/audience/signature | Token verification rejects |
| Reverse proxy path rewrite | Matchers still align with public routes |
| New controller outside prefix | Does not become public |

Tests must exercise **real requests through Spring Security filters**, not controller unit tests alone. A controller returning 200 in a unit test proves nothing about authentication at ingress.

## 19. Mistakes to Avoid

1. Defining only API + WEB chains with no fallback.
2. Placing a catch-all chain at `@Order(1)`.
3. Using `securityMatcher("/**")` on the API chain.
4. Confusing `requestMatchers` with `securityMatcher`.
5. Leaving `/web/login` or `/web/logout` outside the WEB matcher.
6. Enabling multiple login mechanisms together without choosing proper entry points.
7. Letting APIs return 302 HTML instead of 401 status.
8. Assuming Basic headers create web sessions.
9. Assuming web sessions authenticate stateless APIs.
10. Disabling CSRF app-wide just because the app serves APIs.
11. Using HTTP Basic for state-changing browser-accessible APIs without evaluating CSRF.
12. Using Basic over public HTTP without TLS.
13. Writing a custom POST login controller to compare raw passwords manually.
14. Calling default `formLogin()` in MockMvc when the actual path is `/web/login`.
15. Failing to test wrong passwords, wrong roles, and fallback behavior.
16. Disabling MockMvc filters just to get 200s.
17. Adding a JWT chain on `/api/**` without removing the old Basic chain.
18. Granting `ROLE_ADMIN` from client-supplied fields.
19. Assuming `jwt()` mock tests prove signature validation.
20. Failing to verify SSO callback paths and redirect URIs.
21. Confusing mechanism isolation with identity segregation.
22. Leaving actuator, health, metrics, or out-of-prefix endpoints unprotected.
23. Skipping object-level/tenant authorization after authentication.
24. Lacking session/token revocation and account-disablement policies.
25. Skipping tests for path normalization, trailing slashes, and reverse proxies.
26. Failing to log chain/status in monitoring, leading to misdiagnosing 401/302/403 at the wrong layer.

## 20. Production Checklist

- [ ] Inventoried all authentication, authorization, callback, logout, health, and admin URLs.
- [ ] Every `SecurityFilterChain` has a narrow `securityMatcher` or an explicit fallback.
- [ ] `@Order` tested so no chain unintentionally shadows another.
- [ ] Unmatched fallback chain protects all remaining URLs.
- [ ] APIs return proper 401 challenges or Bearer error semantics, never HTML redirects.
- [ ] WEB form login/sessions enforce CSRF, session fixation protection, and secure cookies.
- [ ] API credentials never create web sessions, and WEB sessions never bypass API auth.
- [ ] Basic auth is used only over HTTPS with evaluated CSRF/HTTP method policies.
- [ ] Production Bearer APIs validate JWT signature, issuer, audience, expiry, and scope mappings.
- [ ] OIDC authorization/callback endpoints sit in the right chain with state/nonce verified.
- [ ] Identity providers/authentication managers are separated if policy separates user and service accounts.
- [ ] Both request-level and service/resource-level authorization are tested.
- [ ] Logout, session expiry, revocation, and disabled accounts are tested.
- [ ] MockMvc tests cover anonymous, wrong password, wrong role, CSRF, mixed session, and fallback cases.
- [ ] Reverse proxy, trusted forwarded headers, CORS, and cookie routing are tested.
- [ ] Logs never contain raw Basic credentials, session cookies, JWTs, or passwords.
- [ ] Regression tests run before changing login paths, `@Order`, `securityMatcher`, or policies.

## 21. Summary

Separating multiple authentication mechanisms in Spring Security requires simultaneously separating **URL scope**, **filter mechanism**, **entry point**, **session strategy**, and **security policy**:

~~~text
/api/** → HTTP Basic + STATELESS + 401
/web/** → formLogin + HttpSession + CSRF + 302
other   → fallback denyAll
~~~

**Decisive rule:** `FilterChainProxy` selects the **first matching `SecurityFilterChain`**. `authorizeHttpRequests().requestMatchers` only enforces rules inside the selected chain. Every login-processing URL, logout URL, and OIDC callback must sit inside its proper matcher; remaining URLs must be protected by a fallback.

A successful HTTP Basic call never creates a web session, and a valid web session never replaces the credentials required by a stateless API. Those are the two critical assertions whenever an application combines multiple authentication styles.

## 22. References

1. [Spring Security 6.5 — Java Configuration and Multiple HttpSecurity](https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html): SecurityFilterChain, securityMatcher, @Order, and fallback.
2. [Spring Security 6.5 — Servlet Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html): FilterChainProxy, first matching chain, and filter order.
3. [Spring Security 6.5 — Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html): custom login page, POST processing URL, and CSRF.
4. [Spring Security 6.5 — HTTP Basic](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/basic.html): BasicAuthenticationFilter and Basic entry point.
5. [Spring Security 6.5 — Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html): SessionCreationPolicy.STATELESS and SecurityContextRepository.
6. [Spring Security 6.5 — CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html): CSRF for browser login, tokens, and logout.
7. [Spring Security 6.5 — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html): authorization rules and denyAll.
8. [Spring Security 6.5 — Testing Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/form-login.html): formLogin custom URL with CSRF.
9. [Spring Security 6.5 — MockMvc Security Test](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/index.html): csrf(), httpBasic(), and authentication assertions.
10. [Spring Security 6.5 — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html): Bearer/JWT validation, issuer, and authority mapping.
11. [Spring Security 6.5 — OAuth2 Login](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/login/core.html): OAuth2 endpoints, callback, and ClientRegistration.
12. [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): protecting login and error handling.
13. [OWASP — CSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): token defense, SameSite, and credential boundaries.
