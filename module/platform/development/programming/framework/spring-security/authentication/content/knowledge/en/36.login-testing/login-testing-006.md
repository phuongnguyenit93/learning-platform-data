# Follow-Up Requests After Login to Verify Identity Persistence

## 1. Why a single successful login is not enough to conclude

When testing a Spring Security application with form/session login, we often call `POST /login`, see a redirect or HTTP 200, and conclude "login works". That is only **the first step**. A system can verify the password on the current request yet **fail to save `SecurityContext` into the session**, bind the wrong user to the session, fail to restore authorities on the next request, or accidentally reuse identity from another request.

A more meaningful test executes **two independent HTTP requests**:

1. **Login request:** send credentials through the real login mechanism; verify authentication succeeds and capture the session returned by the server.
2. **Post-login request:** do not resend username/password; pass only that session to a protected endpoint. The endpoint must observe **the exact principal and authorities** of the user who just logged in.
3. **Negative testing:** a new request **without a session** or with another user's session must not inherit that identity; a failed login must not store a user; a valid user lacking a role must still be denied.
4. **Lifecycle checks:** logout/invalidation/expired sessions stop the identity from being usable; if the application relies on stateless Bearer JWTs instead of sessions, verify the token on the follow-up request rather than assuming server-side state.

This lesson belongs to the **Login Testing** group in the **Spring Security - authentication** module. The focus is verifying **persistence and restoration of `Authentication` across requests**, not just password verification on a single isolated request.

**Core takeaway:** `authenticated()` on the `POST /login` response is necessary but **insufficient**; test `GET /me` with the same `HttpSession` and verify identity + authorities at a real endpoint.

## 2. Two-request independent model

Example of a server-side website using Spring Security form login:

```text
Browser / MockMvc Client                 Spring Security + Server
           |                                        |
           | POST /login                           |
           | username=alice, password=...          |
           | valid CSRF token                      |
           |--------------------------------------->|
           |                             UsernamePasswordAuthenticationFilter
           |                             AuthenticationManager / DaoAuthenticationProvider
           |                             PasswordEncoder checks password
           |                             UsernamePasswordAuthenticationToken
           |                             SecurityContextRepository.saveContext(...)
           |<---------------------------------------|
           | 302 Location: /                       |
           | Set-Cookie: JSESSIONID=...             |
           |                                        |
           | GET /me                               |
           | Cookie: JSESSIONID=...                 |
           |--------------------------------------->|
           |                             SecurityContextHolderFilter
           |                             loads from SecurityContextRepository
           |                             authorization: authenticated
           |                             controller reads Authentication.getName()
           |<---------------------------------------|
           | 200 JSON { username: "alice", ... }    |
```

In MockMvc, we typically pass the same `MockHttpSession` from `perform(post("/login"))` to `perform(get("/me").session(session))`. This **simulates a browser sending the session cookie on the second request**.

You do not need (and should not) resend the password on `GET /me`. If a test has to attach username/password or inject a mock principal on the follow-up request, the test no longer proves identity was **saved and restored** from the initial login.

### 2.1. Distinguishing types of state

| Component | Where does it live? | Responsibility |
| --- | --- | --- |
| `SecurityContextHolder` | Usually thread-local during request processing | Exposes the current request's Authentication to running code |
| `SecurityContext` | Object holding `Authentication` | Identity and authentication status of the request |
| `SecurityContextRepository` | Context load/save layer | Associates Authentication with subsequent requests |
| `HttpSessionSecurityContextRepository` | HTTP session | Stores SecurityContext across requests in a web session |
| `RequestAttributeSecurityContextRepository` | Request attributes | Holds context within one request across dispatches, **not** multi-request session storage |
| `DelegatingSecurityContextRepository` | Delegates to multiple repositories | Common Spring Security 6 default is request attribute + HttpSession |
| `JSESSIONID` | Cookie holding session ID | Points the server to the session, **does not hold user/password itself** |
| `Authentication` | Object created by authentication mechanism | Principal, authorities, authenticated flag, details, and credentials |

`SecurityContextHolder` is not permanent login storage. Once the servlet filter chain finishes, the request's context is cleared from the thread; next time, Spring Security must **reload** it via the repository or re-verify credentials under a stateless model.

## 3. Exactly what to check on the follow-up request

A strong post-login test proves multiple levels:

| What to check | Why? | How to prove |
| --- | --- | --- |
| Valid HTTP status | Endpoint is permitted to process | `status().isOk()` |
| Right principal | Did not pick up anonymous, another user, or stale identity | `authenticated().withUsername("alice")`; `Authentication.getName()` |
| Matching authorities | Login did not drop roles or over-grant permissions | `ROLE_READER`, `SCOPE_x` per policy |
| Genuinely authenticated | Not just returning dummy body or a session ID existing | Inspect Authentication in request |
| No credentials resent | Identity restored from valid state | Second request uses session only |
| No session → denied | No cross-client state leak | Anonymous request redirected to login / 401 |
| Wrong login → no identity stored | Failure does not create authenticated session | Second request with failure session stays blocked |
| User B's session differs from A | No session confusion / cross-user leak | Two independent logins, two GETs return right names |
| Missing role still returns 403 | Authentication differs from authorization | Authenticated `ROLE_READER` hitting `/admin` is denied |
| Logout/expired session no longer valid | Do not let sessions outlive lifecycle | Old cookie after logout no longer authenticates |
| CSRF/session fixation protection | Session cannot be pre-set unexpectedly | POST missing CSRF fails to log in; proper session policy |

**Note:** calling only `status().isOk()` is not enough. The controller might be public, or the test might accidentally mock Authentication on the second request. Force the endpoint to require `authenticated()` and check the real principal in `SecurityContext`.

## 4. Save and restore flow in Spring Security 6.x

In Spring Security 6, `SecurityContextHolderFilter` loads context from `SecurityContextRepository`, but **does not automatically save every mutation** of `SecurityContextHolder` when the request ends. With standard authentication mechanisms like form login, the relevant filter saves the context for you on successful login. If you write a custom login filter/controller, you must perform an **explicit save**.

Typical sequence:

```text
Request 1: POST /login
  UsernamePasswordAuthenticationFilter
    └─ AuthenticationManager.authenticate(...)
         └─ UserDetailsService + PasswordEncoder
    └─ SessionAuthenticationStrategy (session fixation policy)
    └─ Create new SecurityContext, attach authenticated Authentication
    └─ SecurityContextRepository.saveContext(...)
    └─ SuccessHandler: redirect

Request 2: GET /me + session ID
  SecurityContextHolderFilter
    └─ SecurityContextRepository.loadDeferredContext(request)
    └─ Populate SecurityContextHolder when accessed
  AuthorizationFilter
    └─ authenticated()
  Controller
    └─ Authentication.getName() → "alice"
```

### 4.1. Why is the second request necessary?

If a custom handler runs:

```java
// ANTI-PATTERN: only sets ThreadLocal, does NOT save through repository
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authentication);
SecurityContextHolder.setContext(context);
```

An endpoint in **the current request** can see the user, yet the next request is anonymous. In Spring Security 6 where explicit saving is required, the snippet above is **not enough** to persist Authentication. You must call `SecurityContextRepository.saveContext(context, request, response)` per chain configuration, and do so **before the response is committed**.

### 4.2. What does the default repository include?

In the Spring Security 6.x Servlet stack, standard default configuration uses `DelegatingSecurityContextRepository` with `RequestAttributeSecurityContextRepository` and `HttpSessionSecurityContextRepository`. The request-attribute branch supports error/forward dispatches **within the same HTTP request**; the HttpSession branch preserves identity for **other requests** sharing the session.

When testing the goal "log in once, next request is still Alice", what you are truly testing is that the session/context is persisted + restored, not just a temporary attribute during the first request.

Replacing it with `NullSecurityContextRepository` or configuring `SessionCreationPolicy.STATELESS` on a web chain can break session-persistence expectations. In a stateless Resource Server, however, that can be **the intended design**: every request must supply its own token.

## 5. Choosing the test layer

Not every testing approach proves the same thing:

| Test type | What it verifies | Limitations |
| --- | --- | --- |
| `AuthenticationProvider` unit test | Valid/invalid credentials, authorities on authenticate | Does not prove HTTP session/repository |
| `@WithMockUser` | Authorization/controller with mocked user | Does not run real login, does not test persistence |
| `user("alice")` request post-processor | Mocked user on the request under test | Does not prove a session from prior login |
| `jwt()` post-processor | Tests mocked JWT authorization | Does not check signature/issuer/audience and does not prove session |
| MockMvc `POST /login` then `GET /me` with same session | Form filter, authentication manager, repository, and per-request authorization | Simulates Servlet; does not prove real cookies/TLS/proxy |
| HTTP integration test with running server + cookie jar | Set-Cookie, session ID, cookie flags, real HTTP and routing | Slower; requires a managed environment |
| Browser E2E (Playwright/Selenium) | Login UX, redirects, browser cookies, CSRF, logout | Harder to isolate root cause; does not replace integration tests |

**Recommendation for this topic:** choose two-request MockMvc as the primary test, supplemented by a real HTTP/browser test for session cookies, proxies, and lifecycle concerns. Never rely solely on `@WithMockUser`.

## 6. Spring Boot 3.x and Java 17 project: standard setup

The example is designed for **Spring Boot 3.x + Spring Security 6.x + Java 17+**, using Spring MVC/Servlet and default form login. Redis sessions, OIDC, and real databases are omitted so the focus stays sharp.

### 6.1. Gradle dependencies

In a project already configured with the Spring Boot plugin, dependency management, and appropriate Java toolchain, add the `dependencies` block:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

`spring-security-test` provides matchers/processors such as `authenticated()`, `unauthenticated()`, `csrf()`, `formLogin()`, and `user()`. `@SpringBootTest` + `@AutoConfigureMockMvc` ensure the filters auto-configured by Spring Boot are applied to MockMvc.

**No need to call `MockMvcBuilders.standaloneSetup(...)` manually for this example.** If building MockMvc manually instead of using Boot auto-configuration, you must attach Spring Security with `.apply(springSecurity())` (and the appropriate framework/context); otherwise tests may skip filters and produce false results.

### 6.2. Main class

Place the Java files in `src/main/java/com/example/loginproof/`, package `com.example.loginproof`.

**`LoginProofApplication.java`**

```java
package com.example.loginproof;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LoginProofApplication {

    public static void main(String[] args) {
        SpringApplication.run(LoginProofApplication.class, args);
    }
}
```

### 6.3. SecurityConfig.java

**`SecurityConfig.java`**

```java
package com.example.loginproof;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/login", "/error").permitAll()
                        .requestMatchers("/me").authenticated()
                        .requestMatchers("/admin").hasRole("ADMIN")
                        .anyRequest().denyAll())
                .formLogin(Customizer.withDefaults())
                .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService demoUsers(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password(encoder.encode("alice-demo-secret"))
                        .roles("READER")
                        .build(),
                User.withUsername("bob")
                        .password(encoder.encode("bob-demo-secret"))
                        .roles("VIEWER")
                        .build());
    }
}
```

**Notable points:**

- `formLogin(Customizer.withDefaults())` uses the default Spring Security login page and handles `POST /login` via `UsernamePasswordAuthenticationFilter`.
- `/me` requires an authenticated user; `/admin` additionally requires `ROLE_ADMIN`. Alice and Bob do **not** have the ADMIN role in the demo, so both can log in yet receive 403 when hitting `/admin`.
- `PasswordEncoder` is BCrypt, never comparing plaintext directly. The two passwords are for **lab/test only**, not valid secrets to deploy to production.
- `anyRequest().denyAll()` blocks undefined URLs; the login/error pages are permitted to avoid redirect loops.
- Do not disable CSRF. When POSTing form login, tests must supply a valid CSRF token; bypassing CSRF to fix a 403 test is the wrong approach for web sessions.
- Do not use `SessionCreationPolicy.STATELESS` because this is a website that must persist Authentication in `HttpSession`.
- In a real project, `UserDetailsService` and the password encoder may use a database/LDAP, distributed session store, MFA, and account state; the two-request test semantics remain the same.

### 6.4. Endpoint to inspect identity without leaking secrets

**`IdentityController.java`**

```java
package com.example.loginproof;

import java.util.List;
import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class IdentityController {

    @GetMapping("/")
    public String home() {
        return "Home: public";
    }

    @GetMapping("/me")
    public Map<String, Object> me(Authentication authentication) {
        List<String> authorities = authentication.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .sorted()
                .toList();

        return Map.of(
                "username", authentication.getName(),
                "authenticated", authentication.isAuthenticated(),
                "authorities", authorities);
    }

    @GetMapping("/admin")
    public String admin() {
        return "Admin: permitted";
    }
}
```

When Alice's session is restored properly, `GET /me` returns JSON like:

```json
{
  "username": "alice",
  "authenticated": true,
  "authorities": ["ROLE_READER"]
}
```

This is an **expected demo response** example, not output captured from a real server. Never return credentials, password hashes, OAuth2 access/refresh tokens, session IDs, or the full `Authentication.toString()`. In production, a `/me` endpoint should return only the user info genuinely needed for display; detailed permissions may be internal data and must be evaluated against the contract.

## 7. Core MockMvc test: real login then send follow-up request

This is the most important part of the lesson. The test file lives at `src/test/java/com/example/loginproof/LoginPersistenceTest.java`.

**`LoginPersistenceTest.java`**

```java
package com.example.loginproof;

import jakarta.servlet.http.HttpSession;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.hamcrest.Matchers.hasItem;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class LoginPersistenceTest {

    @Autowired
    MockMvc mvc;

    private MockHttpSession login(String username, String password)
            throws Exception {

        MvcResult loginResult = mvc.perform(post("/login")
                        .with(csrf())
                        .param("username", username)
                        .param("password", password))
                .andExpect(status().is3xxRedirection())
                .andExpect(authenticated().withUsername(username))
                .andReturn();

        HttpSession session = loginResult.getRequest().getSession(false);
        assertNotNull(session, "Login must establish a session");
        return (MockHttpSession) session;
    }

    @Test
    void nextRequestMustRestoreAliceFromSameSession() throws Exception {
        MockHttpSession session = login("alice", "alice-demo-secret");

        mvc.perform(get("/me").session(session))
                .andExpect(status().isOk())
                .andExpect(authenticated().withUsername("alice"))
                .andExpect(jsonPath("$.username").value("alice"))
                .andExpect(jsonPath("$.authenticated").value(true))
                .andExpect(jsonPath("$.authorities", hasItem("ROLE_READER")));
    }

    @Test
    void freshRequestWithoutSessionMustNotBorrowAlice() throws Exception {
        login("alice", "alice-demo-secret");

        // Do not pass .session(...) on the second request.
        mvc.perform(get("/me"))
                .andExpect(status().is3xxRedirection());
    }

    @Test
    void differentSessionsMustKeepTheirOwnIdentities() throws Exception {
        MockHttpSession alice = login("alice", "alice-demo-secret");
        MockHttpSession bob = login("bob", "bob-demo-secret");

        mvc.perform(get("/me").session(alice))
                .andExpect(status().isOk())
                .andExpect(authenticated().withUsername("alice"))
                .andExpect(jsonPath("$.username").value("alice"))
                .andExpect(jsonPath("$.authorities", hasItem("ROLE_READER")));

        mvc.perform(get("/me").session(bob))
                .andExpect(status().isOk())
                .andExpect(authenticated().withUsername("bob"))
                .andExpect(jsonPath("$.username").value("bob"))
                .andExpect(jsonPath("$.authorities", hasItem("ROLE_VIEWER")));
    }

    @Test
    void readerIsAuthenticatedButNotAuthorizedAsAdmin() throws Exception {
        MockHttpSession session = login("alice", "alice-demo-secret");

        mvc.perform(get("/admin").session(session))
                .andExpect(status().isForbidden())
                .andExpect(authenticated().withUsername("alice"));
    }
}
```

### 7.1. Step-by-step walkthrough of the passing test

1. `mvc.perform(post("/login").with(csrf())...)` sends the HTTP login request through the **real filter chain** in the Spring test context; no mock Authentication is pre-injected.
2. `andExpect(authenticated().withUsername("alice"))` confirms authentication on **the login result** matches Alice.
3. `getRequest().getSession(false)` retrieves the server-side session **after login**, without creating a new session just to let the test pass. Casting to `MockHttpSession` fits the MockMvc environment.
4. `mvc.perform(get("/me").session(session))` is a **new request**. There is no `.with(user("alice"))`, no password, and no manual `SecurityContextHolder` setup.
5. `authenticated().withUsername("alice")` on the **second request** verifies that Authentication was restored, rather than relying only on HTTP 200.
6. `jsonPath("$.username")` and `jsonPath("$.authorities")` prove the controller sees the right identity and role inside the restored context.
7. The Bob user test uses a separate session to verify **isolation between two users**; sending Alice, then Bob, then Alice still succeeds and helps detect state leaks across requests or threads.

**Significance:** this test will fail if a custom authentication handler only sets ThreadLocal without saving SecurityContext. The login request may still appear authenticated, yet the next `GET /me` redirects back to login.

### 7.2. Do not treat login redirect as proof of persistence

Form login usually returns 302 after a successful login. A redirect only indicates the success handler was called; if the repository saved incorrectly or another request uses a different session, the new request may still have no user. Verify `GET /me`. Similarly, an HTTP 200 response does not prove Authentication if the endpoint is unprotected.

### 7.3. Running the tests

In a project with the Gradle wrapper:

```bash
./gradlew test
```

On Windows PowerShell:

```powershell
.\gradlew.bat test
```

**Expected result:** all four tests in the file above pass when configured properly. This lesson provides code and testing guidance, **without claiming the command was executed in a repository or CI**. For a real project with different security filters/CSRF/session config, adapt the tests to the project contract while keeping the **two-request and same-identity verification** requirement.

## 8. Failed login case: must not store an authenticated principal

A failed login is normally handled by `AuthenticationFailureHandler`; the authentication context must be cleared or not created. Use the same session before and after a failed login to confirm the failure does not grant access.

Test snippet to **add to class `LoginPersistenceTest`** (requires the import shown below):

```java
@Test
void failedLoginMustNotAuthenticateExistingAnonymousSession()
        throws Exception {

    MockHttpSession session = new MockHttpSession();

    mvc.perform(post("/login")
                    .session(session)
                    .with(csrf())
                    .param("username", "alice")
                    .param("password", "wrong-secret"))
            .andExpect(status().is3xxRedirection())
            .andExpect(unauthenticated());

    mvc.perform(get("/me").session(session))
            .andExpect(status().is3xxRedirection())
            .andExpect(unauthenticated());
}
```

Add import:

```java
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.unauthenticated;
```

**Do not** merely assert "wrong login → redirect to `/login?error`" and stop: if a custom filter accidentally saved authentication before finishing verification, a subsequent request could still slip through.

Distinguish **a failed login on an anonymous session** from **an already logged-in user entering wrong credentials in another form**. In the second scenario, policy might be keeping the current session, requiring reauthentication, invalidating the session, or reporting an error; define the contract explicitly. Never treat one failed login attempt as guaranteed proof that all other sessions of that user were destroyed.

## 9. Checking CSRF and verifying the right endpoint

With browser form login, Spring Security enables CSRF by default. A test sending `POST /login` without a token can be blocked with 403 **before** the password is checked. Asserting only 403 and concluding "wrong password was blocked" misses the target.

Test snippet that can be added to the class:

```java
@Test
void postLoginWithoutCsrfMustBeRejected() throws Exception {
    mvc.perform(post("/login")
                    .param("username", "alice")
                    .param("password", "alice-demo-secret"))
            .andExpect(status().isForbidden());
}
```

When testing real login, use `.with(csrf())` or Spring Security Test `formLogin()` to generate a valid CSRF. Do not disable CSRF across the web chain just to make tests "easy to pass".

**Important negative test:** after a POST missing CSRF, a request to `/me` must not see an authenticated Alice. You can attach an explicit fresh session to both requests to prove this, similar to section 8. State-mutating endpoints using cookie sessions must also be CSRF-protected; `GET /me` is read-only and does not need a token.

## 10. Alternative: using Spring Security Test's formLogin() RequestBuilder

Spring Security Test provides `SecurityMockMvcRequestBuilders.formLogin()`. It is a helper that creates a form login POST with username/password and valid CSRF, not a way to inject a mocked user.

Example **snippet placed in the test class** using the helper:

```java
MvcResult loginResult = mvc.perform(formLogin()
                .user("alice")
                .password("alice-demo-secret"))
        .andExpect(authenticated().withUsername("alice"))
        .andReturn();

MockHttpSession session =
        (MockHttpSession) loginResult.getRequest().getSession(false);
assertNotNull(session);

mvc.perform(get("/me").session(session))
        .andExpect(authenticated().withUsername("alice"))
        .andExpect(jsonPath("$.username").value("alice"));
```

Required import:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestBuilders.formLogin;
```

With a custom `loginProcessingUrl("/auth/login")` and custom parameter names, the helper supports customizing the URL and field names per your Spring Security Test version's API. In the current example, the defaults `POST /login`, `username`, and `password` are used.

**Why does `formLogin()` differ from `with(user(...))`?** `formLogin()` actually sends a POST through the authentication filters; `with(user("alice"))` sets a mocked SecurityContext on the request under test. Only the former, when paired with attaching the session to a follow-up GET, proves the login path ran.

## 11. Inspecting SecurityContext directly in HttpSession: when is it needed?

You can read the session attribute that `HttpSessionSecurityContextRepository` normally uses:

```java
Object stored = session.getAttribute(
        HttpSessionSecurityContextRepository.SPRING_SECURITY_CONTEXT_KEY);

assertNotNull(stored);

SecurityContext context = (SecurityContext) stored;
assertEquals("alice", context.getAuthentication().getName());
```

This is an **additional Java snippet for tests**; required imports:

```java
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import static org.junit.jupiter.api.Assertions.assertEquals;
```

With Spring Security 6 defaulting to the session repository, this check helps diagnose state storage. However:

- It depends on **the specific storage mechanism**. If the project uses a custom `SecurityContextRepository`, another Redis/session adapter, or a stateless API, the key/data type may differ.
- Having the object in the session **is not enough**: authorization might still use a different filter chain and fail to load that object.
- What matters most remains that **the second request injects no mock principal** and the protected endpoint reads the right Authentication.
- Never dump session IDs or serialized SecurityContexts into logs/CI artifacts.

**Prefer behavioral testing.** Use repository/session-attribute inspection only when debugging session persistence to narrow down the root cause.

## 12. Custom authentication: explicit save is mandatory when persisting sessions

If an application writes a custom login controller or filter creating an Authentication, the following **illustrates logic placed in a component that has request/response/AuthenticationManager and a configured repository**:

```java
Authentication requested =
        UsernamePasswordAuthenticationToken.unauthenticated(
                submittedUsername, submittedPassword);

Authentication verified = authenticationManager.authenticate(requested);

SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(verified);
SecurityContextHolder.setContext(context);

// Spring Security 6: must save explicitly if the next request needs to load the context.
securityContextRepository.saveContext(context, request, response);
```

Types to import:

```java
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.context.SecurityContextRepository;
```

**Do not copy this snippet directly into a main project and treat it as a standalone login controller.** You must implement AuthenticationManager, error handling, session authentication strategy, CSRF policy, success/failure handlers, account controls, and the chain's exact `SecurityContextRepository`. A custom flow skipping the session authentication strategy can create a fixation vulnerability even when the context is saved.

### 12.1. Two common pitfalls in Spring Security 6

**Pitfall A: only setting context, forgetting to save.** In the current request the user is authenticated, yet the next request is anonymous. The two-request test pattern catches this.

**Pitfall B: using a repository that mismatches the chain.** A custom controller saves into a self-instantiated `HttpSessionSecurityContextRepository`, while the filter chain reads from `NullSecurityContextRepository` or another custom repository. State exists yet is never restored. Configure and use one consistently across the login path and protected requests.

### 12.2. Save before redirecting or committing the response

When calling `sendRedirect`, the response may become committed. Save `SecurityContext` before sending the redirect/returning the response. If a session is created after the response is committed, the session cookie may fail to reach the client as expected. A test that only checks the username on the login request may miss this, while a post-login test catches it.

### 12.3. SecurityContextHolderFilter and differences from Spring Security 5

In Spring Security 5, `SecurityContextPersistenceFilter` could auto-save context at the end of a request by default. Spring Security 6 favors `SecurityContextHolderFilter`, requiring explicit saves whenever custom code alters Authentication. Do not try enabling both filters to "fix" persistence; consult your version's docs and design the repository cleanly.

## 13. Session fixation and why you should obtain the session after login

One risk of HTTP session login is **session fixation**: an attacker tries to force a victim to log in under a known session ID. Spring Security normally uses a session authentication strategy to change the session ID or session depending on configuration/container.

Therefore, in tests:

1. Log in through the standard filter; never set Authentication manually to bypass the session strategy.
2. Obtain the session **from the post-login result** via `loginResult.getRequest().getSession(false)`.
3. Use that session for `GET /me`. Never hardcode session IDs or assume pre- and post-login IDs always match.
4. When testing session fixation specifically, create a session before login and check `SessionAuthenticationStrategy` per environment; do not treat one container-specific assertion as a guarantee across all containers.

A session ID is a browser session credential. Never return it in JSON `/me`, never log full cookies, and use HTTPS plus `Secure`, `HttpOnly`, and `SameSite` cookies per policy. The cookie ID **does not carry the username**; the server uses the ID to look up the context.

With multiple instances/pods, session affinity or an appropriate distributed session store is required. An integration test through a load balancer sending login to node A and the follow-up request to node B will catch unshared session state.

## 14. Two users, two sessions: preventing identity leaks

The Alice and Bob test in section 7 checks two isolated sessions. You can extend it by alternating requests:

```text
Login Alice → session A
Login Bob   → session B

GET /me + session A   → username = alice, ROLE_READER
GET /me + session B   → username = bob,   ROLE_VIEWER
GET /me + session A   → username = alice, ROLE_READER
GET /me no session    → anonymous/redirect to login
```

Goal: catch **cross-user contamination**, such as a controller storing the current user in a singleton field or a custom filter failing to clear a thread's `SecurityContextHolder` before reuse.

**Dangerous mistake:**

```java
// ANTI-PATTERN: singleton controller holding identity in a shared field
@RestController
class UnsafeController {
    private String lastUser;

    @GetMapping("/whoami")
    String who(Authentication auth) {
        lastUser = auth.getName();
        return lastUser;
    }
}
```

The code above is not an identity solution: a mutable field on a singleton bean races across requests; if `lastUser` is used elsewhere, user A could see user B's data. In controllers/services, read identity from the **current request's** Authentication, never storing principals in shared fields.

MDC/tracing must be cleared properly at the end of each request; never treat a custom `ThreadLocal` as a session store. `SecurityContextHolderFilter` manages the framework's context lifecycle, whereas application-created ThreadLocals still require separate cleanup.

## 15. Logout, session expiration, and reauthentication

After login, tests should ask not only "was the user saved?" but also "when does it stop working?". Check:

- `POST /logout` with valid CSRF clears Authentication and invalidates the session per configuration.
- Requests using the **old** session/cookie after logout cannot access `/me` as an authenticated user.
- Session expiration per server policy forces protected requests to log in again.
- Roles/permissions revoked while a session is active must take effect per refresh or invalidation policy.
- Password resets, disabled users, locked accounts, or MFA step-up may require destroying/rotating sessions per threat model.
- Concurrent sessions: if `maximumSessions` is configured, test sessions A/B per expected behavior rather than assuming the framework limits them by default.
- Remember-me, persistent login, and OAuth2 authorized client state need separate tests, because they can **re-authenticate** the user even after the original session expires.

With MockMvc, after logout a `MockHttpSession` may be **invalidated**, so trying to reuse that object may throw an exception rather than issuing a browser-like request. To test stale cookies over real HTTP, use a test server with a cookie jar/client able to send the old cookie without touching an invalidated Java object; the expected outcome is no longer authenticated.

**Do not treat a redirect to `/login` after logout as sufficient** if a JSON/API endpoint still accepts the old session or a remember-me token remains valid.

## 16. OAuth2/OIDC login: which identity is saved?

If the website uses `oauth2Login()` instead of form login, the testing pattern **remains two requests**, though the Authentication/principal type differs:

1. Browser performs Authorization Code/OIDC login via the IdP.
2. Spring Security verifies the IdP response/token and builds `OAuth2AuthenticationToken` with principal `OAuth2User` or `OidcUser`.
3. Per web session config, `SecurityContext` is persisted; a follow-up request with the same session must see the principal of **the exact provider and user**.
4. The endpoint verifies `authentication.getName()`, provider registration, and validated claims per contract; never treat an unverified email as the primary identifier for local account linking.
5. OIDC logout, token expiration, and local session expiration have **different lifecycles** and must be tested separately.

With OIDC, stable identity should rely on the `(iss, sub)` pair under a trusted issuer. Never rely on mutable or non-unique display names/emails for account linking. When comparing identity in post-login requests, verify exact **issuer, subject, tenant, and local account mapping** if the app links external providers.

### 16.1. Unit/mock OIDC differs from testing real callbacks

Spring Security Test has post-processors like `oidcLogin()` to create an authenticated principal for a single authorization/controller test request. It does not simulate redirects/callbacks, `state`, nonce, signature/issuer validation, or session saving of real OIDC login.

Therefore:

- `oidcLogin()` is suitable for testing controllers and policies against a mocked `OidcUser`.
- To prove **OIDC login persists across requests**, write an integration test for the login/callback flow against a test IdP or a web E2E flow, then send the second request with the session cookie.
- Never put the `oidcLogin()` request post-processor on `GET /me` and claim OIDC login persistence works.

## 17. Bearer/JWT Resource Server: the second request means something different

For a stateless API using `oauth2ResourceServer().jwt()`, there is no goal of "saving the JWT in HttpSession" unless the app **intentionally** designs for that. Normally each HTTP request supplies:

```http
GET /api/me HTTP/1.1
Authorization: Bearer <access_token>
```

The Resource Server validates the signature/issuer/audience/expiry of the **access token** and builds `JwtAuthenticationToken` for **that request**. Once the request ends, there is no requirement to keep the JWT in a session.

Stateless API tests should verify:

| Request | Expected result |
| --- | --- |
| `GET /api/me` with valid JWT and right scope | 200, verified principal/claims |
| Follow-up `GET /api/me` with same valid token | Still resolves the right identity |
| Follow-up `GET /api/me` **without** a token | 401; must not "borrow" Authentication from previous request |
| Token with bad signature, wrong issuer/audience, or expired | 401 |
| Valid token missing scope/role | Usually 403 |
| Cookie from web form is not a Bearer token | Does not grant API access if API chain is stateless |

**Very important:** tests using Spring Security Test's `jwt()` only mock Authentication and **do not pass through `JwtDecoder` to verify signatures**. Integration tests with tokens signed by a test key and test JWKS/AS are needed when verifying real token validation.

Thus, **the same "follow-up request" concept applies with different criteria**: web sessions must restore state from the session; stateless APIs must re-authenticate from a valid credential on every request.

## 18. End-to-end HTTP with a cookie jar

MockMvc is a simulated environment. To verify browser cookies over real HTTP, start the app on a test port and use a cookie jar.

For a web form with CSRF, the real flow is typically:

```text
GET /login
  → receive session cookie (if created by server)
  → extract CSRF token from HTML form or a protected token endpoint

POST /login + username/password + CSRF token + session cookie
  → authentication succeeds
  → receive post-login cookie/session ID (may rotate due to session fixation)

GET /me + new session cookie
  → 200 and right identity
```

Do not send a POST without CSRF and then disable CSRF upon seeing 403. Never hardcode a CSRF token copied from another session: the token must match the request's repository/session policy. With server-rendered forms, template engines normally inject the proper hidden CSRF input. With SPAs, an appropriate CSRF contract is required.

You can use `curl -c cookies.txt -b cookies.txt` to save and resend cookies, though logging in past CSRF requires extracting the actual token from `GET /login`; automation varies by template/HTML. When inspecting the initial 302, avoid `curl -L` before viewing headers because following redirects can hide the login response.

### 18.1. Why is HTTP E2E still needed?

MockMvc cannot fully verify:

- `Set-Cookie` headers/domain/path/secure/samesite through a reverse proxy.
- Session cookies rejected by browsers due to `SameSite`/HTTPS or cross-site origins.
- Session affinity/Redis sessions across two nodes.
- Real server `HttpSession` lifecycle/container behavior.
- OIDC login redirects and callbacks between browser and IdP.
- XSS/CSRF and cookie replay/invalid session behavior in a real environment.

MockMvc tests **Spring web security logic** very well, whereas E2E verifies the entire path from client to backend.

## 19. Common pitfalls and fixes

| Mistake | Why the test misleads | Fix |
| --- | --- | --- |
| Only `POST /login` and assert 302 | Does not prove session/context was saved | `GET /me` with session from login |
| Using `with(user("alice"))` on post-login GET | Injects a new principal, hiding persistence bugs | Use `.session(session)` only |
| Using `@WithMockUser` for the entire login test | Bypasses filter/password validation | Send real POST login in test context |
| After login, `GET /me` omits session | New request is anonymous by design, creating false failure | Pass post-login `MockHttpSession` |
| Reading `SecurityContextHolder` after `mvc.perform` | ThreadLocal was already cleared, misleading result | Assert inside request via endpoint/ResultMatcher |
| Creating a new session with `getSession()` while debugging | Session exists without proving login created it | Use `getSession(false)` and `assertNotNull` |
| `GET /me` public, asserting only 200 | Anonymous also gets 200 | Protect with `authenticated()` and assert principal |
| Custom login only sets context | Does not persist in Security 6 | Call `SecurityContextRepository.saveContext` |
| Saving to a different repository than the chain | GET cannot load the context | Use one consistently configured repository |
| Custom login skips session strategy | Can introduce a session fixation vulnerability | Run standard strategy/flow before saving |
| Form POST without CSRF token | 403 from CsrfFilter before checking password | `.with(csrf())` or `formLogin()` helper |
| Checking right user while skipping authorities | Roles can be dropped or mis-assigned | Assert roles/scopes on the second request |
| Two users sharing one session in test | Data may overwrite; fails to test isolation | Create two independent sessions and interleave |
| Asserting exact Location across all setups | SavedRequest/success handler changes redirects | Assert 3xx + right target per contract |
| Testing `jwt()` for persistence | JWT post-processor applies to current request only | Session test for web; decoder test for JWT |
| Treating ID token/OIDC email as session ID | Confuses identity with protocol | Verify `(iss, sub)` and web session separately |
| Testing logout with an invalidated MockHttpSession | Can throw an exception on the mock object | Use E2E cookie replay or valid simulated session |
| Not testing no-session/wrong-session | Easy to miss cross-user identity leaks | Negative tests and cross-session checks |
| Checking only response body, ignoring Authentication | Controller could return hardcoded data | Assert both security context and output |
| Leaving cookies/sessions unprotected | Session hijacking can bypass login | TLS, Secure/HttpOnly/SameSite, rotation, expiration |
| Assuming sessions exist on every backend pod | Stateful load balancing can drop context | Proper Spring Session/affinity and E2E |

## 20. Testing checklist before completing a login feature

A pull request modifying login should only be considered thoroughly tested when there is evidence of:

- [ ] `POST /login` with valid credentials goes through the **real authentication filter**, without injecting mock users.
- [ ] Successful login response matches the HTTP contract (redirect or JSON) and leaks no secrets.
- [ ] Test obtains **the post-login session**, without assuming the initial session ID stayed unchanged.
- [ ] `GET` on a protected resource in the second request **does not resend passwords**, using only the captured session.
- [ ] The second result carries an authenticated `Authentication`, exact username, and right permissions.
- [ ] No session (or wrong session) never inherits the previous user's identity.
- [ ] Failed login never writes an authenticated principal into an anonymous session.
- [ ] Two-user test maintains separate Alice/Bob sessions with no state leak when interleaved.
- [ ] Endpoints enforce role/authorization rules; users lacking a role receive 403.
- [ ] `POST /login` missing CSRF is never misinterpreted as a password error.
- [ ] Logout, session expiry, session fixation, and remember-me flows have dedicated tests.
- [ ] Custom login (if any) saves `SecurityContext` to the right repository before response commit.
- [ ] OIDC/SAML/social login (if any) tests identity mapping and callback persistence rather than mocking principals alone.
- [ ] Stateless bearer API (if any) ensures follow-up requests **must carry their own valid token**, not web sessions.
- [ ] Integration tests cover cookie jars, HTTPS proxies, and session stores for browser behavior when needed.
- [ ] Tests never print passwords/tokens/cookies/session IDs, full principals, or credentials into CI logs.

## 21. Practice exercises

1. Run `LoginPersistenceTest` in the Boot 3.x project. Remove `.session(session)` from `GET /me`; explain why an anonymous redirect is **correct** behavior for a sessionless request.
2. Write a custom login handler that only calls `SecurityContextHolder.setContext(...)` and forgets to save. Test the login result matcher and second GET; then fix it with `SecurityContextRepository.saveContext(...)`.
3. Replace `.requestMatchers("/me").authenticated()` with `permitAll()`. Why does checking only status 200 produce a false positive? Add Authentication/JSON assertions.
4. Create three users with different roles. Log each one in, use their separate sessions, and verify `authorities` on follow-up requests. Then interleave Alice→Bob→Alice.
5. Add a wrong-login test with a pre-existing session, verifying the second request does not become authenticated.
6. Try `POST /login` without CSRF and verify 403. Why does this not prove the password is wrong? How does the `formLogin()` helper generate a valid CSRF?
7. Create an endpoint restricted to `ADMIN`. Verify that an authenticated `READER` user with a properly saved session still receives 403 at this endpoint.
8. Write an integration test using a cookie jar through an HTTPS proxy and two backend pods. Without a distributed session, what happens when the second request hits the other pod?
9. If the application uses OIDC, design a real callback test and `GET /me` to verify `(iss, sub)`/account mapping instead of substituting `oidcLogin()` for flow verification.
10. Design a stateless Resource Server test: two requests with a valid JWT succeed; a third request without a token must return 401, proving no identity leaked from the prior two requests.

## 22. Summary and references

- **A single successful login is not enough** to prove identity persistence. You need an **independent second request** to a protected resource using the issued session/cookie.
- In Spring Security Servlet, `SecurityContextHolder` represents the current request's context; `SecurityContextRepository` persists and restores `Authentication` across requests.
- In Spring Security 6, custom logins must **explicitly save context** when persistence is required; standard form login does this via framework mechanisms.
- A strong test checks **Authentication/username/authorities** on the post-login GET, not just HTTP 200 or a non-null session variable.
- Mock `@WithMockUser`, `with(user(...))`, or `jwt()` suit single-request policy tests and **do not prove a real login flow saved a session**.
- Negative tests for missing sessions, failed logins, another user's session, missing roles, CSRF, and logout are essential to prevent false positives.
- For OAuth2/OIDC web login, the criterion remains the exact user/issuer/subject on subsequent requests; for stateless JWT APIs, the criterion is **per-request** token verification rather than web session storage.

**Official documentation for verification:**

- [Spring Security 6.5 — Testing Form-Based Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/form-login.html)
- [Spring Security 6.5 — Testing MockMvc Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/authentication.html)
- [Spring Security 6.5 — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html)
- [Spring Security 6.5 — SecurityContextRepository and Explicit Saving](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/persistence.html)
- [Spring Security 6.5 — Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html)
- [Spring Security 6.5 — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html)
- [Spring Security 6.5 — Spring Security Test](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/index.html)
- [Spring Security 6.5 — Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html)
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)