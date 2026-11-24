# From an Unprotected Application to Public and Authenticated Endpoints

## 1. What Will This Practical Exercise Build?

Start from a **Spring Boot MVC application without Spring Security**: both `GET /api/public` and `GET /api/profile` return data to unauthenticated guests. Next, add Spring Security step by step, observe the default protection behavior, write a `SecurityFilterChain` to **keep `/api/public` public** and **require authentication for `/api/profile`**, and finally write automated tests proving that policy.

This exercise focuses on **authentication and HTTP request authorization**. It does not yet build database-backed accounts, a login UI, JWT, or OAuth2. Those topics should be studied after clearly understanding the boundary between public and authenticated endpoints in a simple application.

Final result:

| HTTP request | Expected | Reason |
| --- | --- | --- |
| `GET /api/public`, no credentials sent | **200** | Configured with `permitAll()` |
| `GET /api/public`, valid credentials | **200** | Public resource remains accessible |
| `GET /api/profile`, no credentials sent | **401** | `authenticated()` + HTTP Basic |
| `GET /api/profile`, wrong password | **401** | Authentication failed |
| `GET /api/profile`, valid credentials | **200** | Authenticated |
| `GET /api/missing`, unauthenticated | **401** | `anyRequest().authenticated()` applies before reaching MVC |
| `GET /api/missing`, authenticated | **404** | Passed the security layer, but no controller exists |

**Distinction:** 401 means authentication is required or failed, 403 usually means authenticated without sufficient permissions (or rejected by a defense such as CSRF), and 404 means no resource/handler was found. The returned status code depends on the actual `SecurityFilterChain`, entry point, and controller; this table is the contract of the **HTTP Basic** configuration written in this exercise.

## 2. Setup and Project Structure

The example uses **Java 17**, **Spring Boot 3.3.5**, **Spring Security 6.x** managed by the Spring Boot BOM, **Gradle Groovy DSL**, **Spring MVC/Servlet**, JUnit 5, and MockMvc. This is a fixed sample version set for practice; a real project must choose its own compatible Boot/Security pair. It can be run with JDK 17 or newer compatible with Gradle and Boot. No database, Docker, or frontend is needed.

Create a Spring Boot Gradle project from Spring Initializr or an empty project that already has the Gradle Wrapper; declare the package `example.securitydemo`, Java 17, and initially only the **Spring Web** dependency. If Initializr provides a different version, choose a supported version and adjust Gradle accordingly; do not mix starters across generations. Keep `gradlew` / `gradlew.bat` provided by the project generator.

Structure of the files we write:

~~~text
security-demo/
├── settings.gradle
├── build.gradle
├── gradlew                        # provided by Gradle Wrapper
├── gradlew.bat                    # provided by Gradle Wrapper
├── gradle/wrapper/...
└── src/
    ├── main/java/example/securitydemo/
    │   ├── SecurityDemoApplication.java
    │   ├── DemoController.java
    │   └── SecurityConfig.java    # added only in step 5
    └── test/java/example/securitydemo/
        └── SecurityBoundaryTests.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'security-demo'
~~~

**Initial `build.gradle`, before adding Spring Security:**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
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
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Explanation: `spring-boot-starter-web` provides Spring MVC, embedded Tomcat, and Jackson for returning JSON. The Boot plugin and dependency management keep libraries aligned on the same version family; **there is no need to declare individual versions for each starter**. `spring-boot-starter-test` provides JUnit/Spring Test libraries for the testing section later.

## 3. Step 1 — Application Without a Security Layer

File `src/main/java/example/securitydemo/SecurityDemoApplication.java`:

~~~java
package example.securitydemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityDemoApplication.class, args);
    }
}
~~~

File `src/main/java/example/securitydemo/DemoController.java`:

~~~java
package example.securitydemo;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/api/public")
    public Map<String, String> publicInfo() {
        return Map.of("message", "public");
    }

    @GetMapping("/api/profile")
    public Map<String, String> profile() {
        return Map.of("message", "private");
    }
}
~~~

Run in the directory containing `gradlew`:

~~~bash
./gradlew bootRun
~~~

With PowerShell on Windows:

~~~powershell
.\gradlew.bat bootRun
~~~

In another terminal, call both endpoints:

~~~bash
curl -i http://localhost:8080/api/public
curl -i http://localhost:8080/api/profile
~~~

Key result **before installing Security**: both return `200 OK`, with bodies respectively:

~~~json
{"message":"public"}
~~~

and:

~~~json
{"message":"private"}
~~~

At this stage, the name `/api/profile` or the variable value `private` **does not create security by itself**. Spring MVC only maps the request to the controller method; without authentication/authorization filters or explicit checks, any client that knows the URL can call it.

Self-check question: If this controller is exposed on a public network, is hiding the URL enough to protect private data? **No.** URLs can be guessed, leaked through logs, browser history, or sharing. A server-side enforced security rule is required.

## 4. Step 2 — Add Spring Security and Observe the Default Behavior

Stop the application and add exactly one dependency under `dependencies`:

~~~groovy
implementation 'org.springframework.boot:spring-boot-starter-security'
~~~

Restart with `./gradlew bootRun` or `.\gradlew.bat bootRun`. When there is no custom `SecurityFilterChain` or `UserDetailsService`, Spring Boot enables its default protection configuration: requiring login for requests and providing HTTP Basic/form login mechanisms based on content negotiation. In development environments, Boot can generate a temporary password for the default user and print it in the startup log. **That password is not a user management mechanism for production.**

Observe using a client that does not request HTML:

~~~bash
curl -i -H "Accept: application/json" http://localhost:8080/api/public
curl -i -H "Accept: application/json" http://localhost:8080/api/profile
~~~

You will see both require authentication (typically **401** with this API client). This is a key point: **adding the Security starter does not mean the framework automatically knows which of your URLs should be public**. With a browser accepting HTML, the default form login mechanism may produce a **302** redirect to the login page; when testing status codes, you must understand the entry point/client and actual configuration.

This step helps identify the cause: the controller did not change, yet the request now passes through the security filters registered by Spring Security. Do not conclude that Spring MVC "lost the route"; the route still exists, and security simply intercepts it beforehand.

Simplified processing flow diagram:

~~~text
Client
  |
  v
Spring Security FilterChainProxy / SecurityFilterChain
  |  (authenticates request: e.g., BasicAuthenticationFilter)
  |  (checks rules: AuthorizationFilter)
  v
Spring MVC DispatcherServlet
  |
  v
DemoController
  |
  v
HTTP response

If authentication/authorization fails, the request may terminate in the
Security filter/exception handling without reaching the controller.
~~~

Spring Security handles **authentication** (who is this request?) and **authorization** (is this request allowed to access the resource?) in related but distinct steps.

## 5. Step 3 — Write the Public and Authenticated Policy

Final goal: `GET /api/public` is accessible without logging in; all other requests require authentication. Here we choose only HTTP Basic so **401** is easy to observe in the API exercise. We do not enable form login because we are not building a browser UI flow.

New file `src/main/java/example/securitydemo/SecurityConfig.java`:

~~~java
package example.securitydemo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
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
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(HttpMethod.GET, "/api/public").permitAll()
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(AbstractHttpConfigurer::disable);

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails learner = User.withUsername("learner")
            .password(encoder.encode("learning-only-password"))
            .roles("USER")
            .build();

        return new InMemoryUserDetailsManager(learner);
    }
}
~~~

**Reading each part carefully:**

1. `@Configuration` declares a Spring configuration class; `@Bean SecurityFilterChain` provides the list and configuration of filters that actually process HTTP requests. In Spring Boot, a user-declared bean replaces the fallback default HTTP security configuration.
2. `authorizeHttpRequests` evaluates rules in order. `requestMatchers(HttpMethod.GET, "/api/public").permitAll()` only opens **GET** on that exact URL; it does not implicitly open `/api/public/admin`, other HTTP methods, or the entire application.
3. `anyRequest().authenticated()` is the final safety net: any request not matching a public rule must still carry an authenticated `Authentication`. Do not put `anyRequest().permitAll()` at the end because that opens all remaining routes.
4. `httpBasic(Customizer.withDefaults())` accepts a username/password pair via the `Authorization: Basic ...` header and plugs authentication into the filter chain. `formLogin(AbstractHttpConfigurer::disable)` removes redirects to a login form in this API exercise; when unauthenticated, the expected result is HTTP **401** with the Basic challenge mechanism.
5. `PasswordEncoder` uses BCrypt to verify encoded passwords. `UserDetailsService` returns an in-memory demo account, so no database is required. `roles("USER")` creates the authority `ROLE_USER`; however, **the rule here only requires `authenticated()`** and does not yet restrict by role.
6. `learning-only-password` is a **hardcoded password strictly for local practice**. Never hardcode demo accounts like this in production or commit real passwords. Real systems require a trusted identity source (database/LDAP/identity provider), secret management, TLS, and account lifecycle management.

**Common pitfall:** `permitAll()` only bypasses the **URL access authorization check**; the request still passes through other filters. For example, if a client sends an **invalid Basic header** even to `/api/public`, the authentication filter may return 401 before `permitAll()` is ever evaluated. Nor does `permitAll()` automatically disable CSRF, CORS, or security response headers.

## 6. Step 4 — Call the API and Verify Every Status Code

Restart the application after adding `SecurityConfig`. If using Windows PowerShell, use **`curl.exe`**, because in older Windows PowerShell versions `curl` can be an alias for `Invoke-WebRequest`.

### 6.1. Unauthenticated guest calling the public endpoint

~~~bash
curl -i http://localhost:8080/api/public
~~~

Expected `HTTP 200`, JSON:

~~~json
{"message":"public"}
~~~

### 6.2. Unauthenticated guest calling the authenticated endpoint

~~~bash
curl -i http://localhost:8080/api/profile
~~~

Expected `HTTP 401 Unauthorized`. With HTTP Basic, the server typically also returns `WWW-Authenticate: Basic ...` describing the authentication scheme. There is no `{"message":"private"}` body because the controller was never invoked.

### 6.3. Sending the correct username/password pair

~~~bash
curl -i --basic -u 'learner:learning-only-password' \
  http://localhost:8080/api/profile
~~~

Expected `HTTP 200` and body:

~~~json
{"message":"private"}
~~~

In PowerShell, use a single line:

~~~powershell
curl.exe -i --basic -u "learner:learning-only-password" http://localhost:8080/api/profile
~~~

`curl -u` constructs the Basic header from username/password. This header is only **Base64-encoded**, not encrypted for transport security. In real deployments, **HTTPS** is mandatory to prevent credentials from being exposed on the network.

### 6.4. Sending a wrong password

~~~bash
curl -i --basic -u 'learner:wrong-password' \
  http://localhost:8080/api/profile
~~~

Expected **401**, even though the username exists. The difference between the valid and invalid outcomes shows that Spring Security actually verifies credentials rather than merely checking whether the header is present.

### 6.5. Calling a nonexistent URL

~~~bash
curl -i http://localhost:8080/api/missing
curl -i --basic -u 'learner:learning-only-password' \
  http://localhost:8080/api/missing
~~~

Expected **401** (blocked by policy) and **404** (passed policy, but MVC has no handler), respectively. This illustrates why looking at a single status code in isolation is not enough to diagnose the root cause.

Note: `curl -i` prints all response headers; specific headers such as `Date`, `Cache-Control`, `Content-Length`, or the error body may vary by environment. Only compare the status codes and payloads actually required by the exercise contract.

## 7. Step 5 — Write Regression Tests with MockMvc

Add the Spring Security test library to `build.gradle` alongside the Security starter under `implementation`. The **final** `dependencies` block is:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Keep the plugins, `group`, `java`, `repositories`, and `tasks.named('test')` sections from step 2's `build.gradle` unchanged. Spring Boot manages compatible test library versions.

Create `src/test/java/example/securitydemo/SecurityBoundaryTests.java`:

~~~java
package example.securitydemo;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityBoundaryTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void publicEndpointAllowsAnonymous() throws Exception {
        mockMvc.perform(get("/api/public"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("public"));
    }

    @Test
    void publicEndpointAlsoAllowsAuthenticatedUser() throws Exception {
        mockMvc.perform(
                get("/api/public")
                    .with(httpBasic("learner", "learning-only-password")))
            .andExpect(status().isOk());
    }

    @Test
    void profileRejectsAnonymous() throws Exception {
        mockMvc.perform(get("/api/profile"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void profileRejectsWrongPassword() throws Exception {
        mockMvc.perform(
                get("/api/profile")
                    .with(httpBasic("learner", "wrong-password")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void profileAllowsCorrectCredentials() throws Exception {
        mockMvc.perform(
                get("/api/profile")
                    .with(httpBasic("learner", "learning-only-password")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("private"));
    }

    @Test
    void unknownPathIsStillProtectedForAnonymous() throws Exception {
        mockMvc.perform(get("/api/missing"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void unknownPathReturnsNotFoundAfterAuthentication() throws Exception {
        mockMvc.perform(
                get("/api/missing")
                    .with(httpBasic("learner", "learning-only-password")))
            .andExpect(status().isNotFound());
    }

    @Test
    void invalidBasicCredentialsFailEvenOnPublicEndpoint() throws Exception {
        mockMvc.perform(
                get("/api/public")
                    .with(httpBasic("learner", "wrong-password")))
            .andExpect(status().isUnauthorized());
    }
}
~~~

Run:

~~~bash
./gradlew test --tests "example.securitydemo.SecurityBoundaryTests"
~~~

On Windows:

~~~powershell
.\gradlew.bat test --tests "example.securitydemo.SecurityBoundaryTests"
~~~

**Expected outcome:** all **8 tests pass** and Gradle reports `BUILD SUCCESSFUL`. Exact log line counts may vary across versions. This is the expected behavior from the configured example, not a record of execution in the reader's own environment.

**Why is this test approach more reliable than calling the controller directly?** `@SpringBootTest` boots the real Spring application context of the exercise; `@AutoConfigureMockMvc` configures `MockMvc` within the Boot context with registered filters enabled (security filters are included by default). `httpBasic(...)` simulates a request carrying credentials for Spring Security to verify through the filter chain. If you merely call `new DemoController().profile()` or use `MockMvcBuilders.standaloneSetup` without filters, a `200` test does not prove the endpoint is protected.

**Distinguishing two kinds of tests:** `@WithMockUser` is useful for testing permissions when a mocked `Authentication` is already present; it does not prove that a password goes through `PasswordEncoder` or HTTP Basic. In this capstone exercise, use `httpBasic` to verify the full basic authentication path. When role-level permissions need testing, you can add `@WithMockUser(roles = "USER")` to focus on authorization, while understanding their different purposes.

## 8. Explaining the Mechanism from Request to Controller

### When an unauthenticated request hits `/api/public`

1. The request enters the servlet filter chain.
2. There are no HTTP Basic credentials to authenticate; the context can be treated as anonymous.
3. `AuthorizationFilter` matches the `GET /api/public` rule and sees `permitAll()`.
4. The request enters `DispatcherServlet`, locates `DemoController.publicInfo()`, and returns JSON with status 200.

### When an unauthenticated request hits `/api/profile`

1. The security filter chain cannot authenticate the user because the request has no credentials.
2. No public rule matches, so `anyRequest().authenticated()` applies.
3. The request is rejected; security exception handling invokes the HTTP Basic entry point.
4. The client receives **401** and can retry with an Authorization header; `profile()` is never called.

### When a request with valid credentials hits `/api/profile`

1. `BasicAuthenticationFilter` decodes the Basic format and triggers authentication.
2. The authentication provider queries `UserDetailsService` to load user `learner` and the BCrypt hash.
3. `PasswordEncoder.matches(...)` verifies the password; on success, an authenticated `Authentication` is created.
4. The `authenticated()` rule is satisfied; the controller runs and returns 200 and JSON.

Logic flow diagram:

~~~text
GET /api/profile
       |
       v
Basic header present? -- no -----> Not authenticated
       |                                  |
      yes                                 v
       |                          authenticated() denies
       v                                  |
Verify user + password                    v
       |                                 401
       +---- wrong ---------------------> 401
       |
     valid
       |
       v
authenticated() allows
       |
       v
DemoController.profile()
       |
       v
200 {"message":"private"}
~~~

**Boundary note:** `authenticated()` only requires a valid identity. It **does not prove** that the user is allowed to read another user's records; real data requires role/ownership authorization in the controller/service/data layers. The exercise's `profile()` only returns mock JSON to keep the focus on the security pipeline.

## 9. Small Changes That Can Leak Endpoints

| Mistake | Consequence | How to fix/check |
| --- | --- | --- |
| Using `.anyRequest().permitAll()` | Opens every route without an explicit rule | Use `anyRequest().authenticated()` or `denyAll()` depending on policy |
| Using `/api/**` with `permitAll()` | Accidentally exposes `/api/profile` as well | Use exact matchers for the URL and HTTP method that should be public |
| Testing by calling controller directly | Security filters do not participate | Test via `MockMvc` configured with Spring Security or real HTTP |
| Confusing 401 and 403 | Misdiagnosing missing login vs missing permission | Inspect entry point, `Authentication`, authorization rule, and CSRF |
| Sending wrong password and expecting `permitAll` to return 200 | Basic auth filter rejects bad credentials before policy runs | Retry **without sending an Authorization header**, test invalid creds separately |
| Only testing 200 with a valid user | Fails to catch resources accidentally open to anonymous | Always test both anonymous and wrong-password cases |
| Leaving hardcoded user/password in production code | Easy credential exposure | Use an identity store, password hashing, secrets, and rotation |
| Disabling all of Spring Security to fix an error | Loses protection across the entire app | Inspect filter chain, matchers, entry point, and tests before changing policy |
| Seeing 404 and assuming the request is safe | Could just be a wrong URL/missing handler | Test an **existing** endpoint and verify 401/200 on it |
| Securing only the client-facing path | May miss context/servlet path or route aliases | Audit actual mappings and test boundary URLs |

### Why not disable CSRF arbitrarily?

The main example uses **GET**, which does not mutate server state. The configuration in step 5 **keeps Spring Security's default CSRF protection**. If you extend it with `POST /api/orders` using session/cookies or browser login, you must test missing/invalid/valid CSRF tokens according to the authentication model. URL-level `permitAll()` does not mean CSRF protection is automatically bypassed. Bearer-token-only APIs without cookies may have a different CSRF design, but you need to evaluate how credentials are stored and attached before deciding.

Illustrative test example for a POST endpoint **if you have added the corresponding controller** (the snippet below does not run standalone in the GET-only project):

~~~java
// Requires importing SecurityMockMvcRequestPostProcessors.csrf and post(...)
mockMvc.perform(post("/api/orders")
        .with(httpBasic("learner", "learning-only-password")))
    .andExpect(status().isForbidden());

mockMvc.perform(post("/api/orders")
        .with(httpBasic("learner", "learning-only-password"))
        .with(csrf()))
    .andExpect(status().isCreated());
~~~

For the second assertion to pass, the controller must actually return **201 Created** and the request must pass business validation. Do not treat `csrf()` as a way to bypass security; it supplies a valid test token per Spring Security Test's mechanism.

## 10. Extending Yourself from Login to Role-Based Authorization

Once all eight baseline tests are green, try adding a `GET /api/admin` endpoint and requiring only `ADMIN`. Keep `/api/public` public and `/api/profile` requiring authentication.

In `SecurityConfig`, add the rule **before** `anyRequest()`:

~~~java
.authorizeHttpRequests(authorize -> authorize
    .requestMatchers(HttpMethod.GET, "/api/public").permitAll()
    .requestMatchers(HttpMethod.GET, "/api/admin").hasRole("ADMIN")
    .anyRequest().authenticated()
)
~~~

The snippet above **replaces the corresponding `authorizeHttpRequests` section** rather than pasting a duplicate call into the method. Add `@GetMapping("/api/admin")` to the controller before testing.

Try three scenarios against the existing endpoint:

- Unauthenticated guest: **401** under this exercise's HTTP Basic configuration.
- `learner` (has `ROLE_USER`): **403**, because they are authenticated but lack `ROLE_ADMIN`.
- A new user with `roles("ADMIN")` and a valid password: **200**.

`hasRole("ADMIN")` looks for the `ROLE_ADMIN` authority using the default prefix; if you use `hasAuthority("...")`, write the exact authority string to check. This is an **authorization** upgrade independent of the minimal `authenticated()` requirement.

## 11. Self-Diagnosis When Results Differ from Expectations

**`/api/public` still returns 401 for anonymous:** check whether the new code was actually restarted, whether `SecurityConfig` is in a package scanned by Spring Boot component scan, whether the matcher has the exact method/URL, whether another `SecurityFilterChain` exists, and whether the request carries invalid credentials.

**`/api/profile` returns 200 for anonymous:** check that `anyRequest().authenticated()` is still present, that the configuration wasn't overridden by another filter chain, that the test attaches security filters, and that the request doesn't include a cookie/Authorization header from an earlier call.

**`/api/profile` returns 401 with valid credentials:** check the username/password in `curl`, whether the `UserDetailsService` bean was created, whether there is an encoder mismatch, and check authentication logs. Never switch passwords to `{noop}` in production to fix an error.

**401 turns into 302:** form login may have been enabled by another configuration, or the client sent a different `Accept` header. This exercise explicitly configures `httpBasic` and disables `formLogin` for stable API status codes.

**403 on POST:** distinguish CSRF token issues from missing permissions; check the HTTP method, `SecurityFilterChain`, entry point, and session/cookie. The GET-only exercise does not require disabling CSRF.

**404 for an authenticated request:** does a controller match the route? Is the `@GetMapping` path exact? Is there a different `server.servlet.context-path` or servlet prefix? A 404 is not necessarily a Security error.

When debugging, you can enable security logging in a **local environment** with controlled configuration, such as `logging.level.org.springframework.security=DEBUG`; never share passwords, tokens, cookies, or HTTP Authorization headers in public logs. Dial back logging once the cause is identified.

## 12. Acceptance Tasks and Pass Criteria

1. Run the version **without Spring Security**, proving `/api/public` and `/api/profile` both return 200 when anonymous.
2. Add the starter without declaring a custom `SecurityFilterChain`; prove both require authentication under the default configuration.
3. Add `SecurityConfig` from the exercise, re-run the same URLs with anonymous, wrong credentials, and valid credentials; record the 200/401/200 status table matching the intent.
4. Run all eight tests. Intentionally change `/api/public`'s `permitAll()` to `authenticated()`, watch `publicEndpointAllowsAnonymous` turn red; restore the right config and verify tests turn green again.
5. Write an explanation of why an anonymous call to a URL with no controller can return 401 before returning 404, and why `permitAll` does not rescue invalid Basic credentials.
6. Complete the optional `/api/admin` extension: add the ADMIN role, test anonymous/USER/ADMIN, and explain why USER receives 403.
7. List the constraints that must be upgraded before production: identity store, TLS, secret management, owner-based data access control, CSRF/CORS/session, logging, and regression tests.

**You pass when:** you have a working runnable application, exactly one GET endpoint is public by design while the rest require authentication, and your test suite catches both **over-blocking public** and **accidentally opening private** regressions. You can explain the `SecurityFilterChain → authentication → authorization → controller` mechanism via observed HTTP statuses.

## 13. Official Reference Documentation

- [Spring Security — Servlet Security Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html): filter ordering and roles.
- [Spring Security — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): `requestMatchers`, `permitAll`, `authenticated`, rule ordering, and `hasRole`.
- [Spring Security — Java Configuration](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html): `HttpSecurity` and `SecurityFilterChain`.
- [Spring Security — Username/Password Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/index.html): `UserDetailsService`, authentication provider, encoder.
- [Spring Security — Servlet Testing](https://docs.spring.io/spring-security/reference/servlet/test/index.html): integrating security testing with Spring Test/MockMvc.
- [Spring Security — Testing CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html): `csrf()` support.
- [Spring Boot — Build Systems](https://docs.spring.io/spring-boot/reference/using/build-systems.html): Gradle and dependency management.

The online `/reference/` documentation usually displays the current version. When studying with the fixed Spring Boot 3.3.5 example, use the **version selector** matching your project BOM's Spring Security version if API/default details differ. Any major version change must be cross-checked against the target version's migration guide.
