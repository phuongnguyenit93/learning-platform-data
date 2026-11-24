# Relationship Between HTTP Basic, Sessions, and Per-Request Re-Authentication

> **Scope:** Spring Security 6 on the **Servlet stack**, Spring Boot 3.x, Java 17+. Focuses on the **HTTP Basic authentication** mechanism, how `SecurityContext` can be loaded/saved in a session (`HttpSession`), and the conditions under which the server **re-authenticates credentials** on a new request. Do not equate HTTP Basic with “mandatory stateless” or “calling AuthenticationManager on every request”.

## 1. Core Takeaway: Three Concepts That Must Be Separated

HTTP Basic, sessions, and per-request authentication answer **three different questions**:

1. **HTTP Basic:** How does the client send login credentials? Typically via the `Authorization: Basic ...` header, in which username/password are Base64-encoded per protocol convention. Base64 is **not encryption**.
2. **Session:** Does the server store the authentication result across HTTP requests? This depends on `SecurityContextRepository`, `SessionCreationPolicy`, and whether the authentication filter saves the context—it is **not automatically implied merely by using HTTP Basic**.
3. **Re-authentication:** When the next request arrives, must Spring Security call `AuthenticationManager`/`AuthenticationProvider` again? The answer depends on whether credentials are in the request, whether a valid `Authentication` is already loaded into `SecurityContextHolder`, and the behavior of `BasicAuthenticationFilter`.

**Memorable summary:**

- HTTP Basic is **how a client presents credentials over HTTP**, not a session mechanism.
- An API configured as **stateless** typically requires the client to send Basic credentials on every protected request, so each request authenticates independently of any previous session.
- A **stateful** app can accept Basic credentials initially, save `SecurityContext` into `HttpSession`, and let subsequent requests use the session cookie to restore authentication **even when the subsequent request sends no Basic header**.
- **Having a Basic header on every request does not guarantee the password is re-verified every time:** when Spring Security has already loaded a suitable `Authentication` from a session/context, `BasicAuthenticationFilter` may skip re-authenticating the same username.
- Which policy is active must be proven by **actual configuration and multi-request testing**, not inferred from the name “Basic”.

## 2. How Does HTTP Basic Operate?

HTTP Basic authentication usually starts when a client requests a protected URL without providing an identity:

```text
Client                                        Server
  |                                            |
  | GET /api/me                                |
  |------------------------------------------->|
  |                                            |
  | 401 Unauthorized                           |
  | WWW-Authenticate: Basic realm="api"        |
  |<-------------------------------------------|
  |                                            |
  | GET /api/me                                |
  | Authorization: Basic <Base64(user:pass)>   |
  |------------------------------------------->|
  |                                            |
  | 200 OK (if credentials & permissions valid)|
  |<-------------------------------------------|
```

The `Base64(user:pass)` string does not keep the password secret on the wire. Anyone reading the header can Base64-decode it to obtain the credentials. **HTTPS must be used**; avoid sending Basic headers to untrusted hosts/origins.

### 2.1. Must the Client Send the Basic Header on Every Request?

HTTP Basic is designed so clients can **resend** credentials on requests within an appropriate authentication scope; browsers may cache credentials and attach the header automatically after a challenge. Tools like `curl -u` supply the header for that invocation. However, **not every client attaches the header automatically on every request or every URL**.

Example of two separate `curl` calls:

```bash
curl -i -u learner:study123 http://localhost:8080/stateless/me
curl -i http://localhost:8080/stateless/me
```

On the second call without `-u`, there is no user-supplied Authorization header in this example, so with a stateless chain and an endpoint requiring authentication, the expected result is 401. The first call succeeding **creates no proof that the subsequent request is logged in**.

### 2.2. HTTP Basic Is Not a Session Cookie

| Property | HTTP Basic | Session cookie |
| --- | --- | --- |
| Data sent by client | `Authorization: Basic ...` header with Base64 credentials | `Cookie: JSESSIONID=...` header (or app's cookie name) |
| Meaning | Presents identity/password for authentication | Presents session identifier for server to look up session state |
| Contains raw password or equivalent? | Yes: username/password can be recovered from Base64 | Typically contains no password; cookie is a bearer session ID |
| Can server verify the password? | Yes, when filter/provider decides to authenticate | Typically no need to check password if valid context is restored |
| Depends on session persistence? | Not required | Yes, or an equivalent session store |
| Primary risk | Header leak exposes password; browser retains credentials | Session hijacking/fixation/CSRF depending on cookie usage |

**Both are sensitive.** For Basic headers, protect passwords; for cookies, protect the session ID like a bearer credential. Never log Authorization headers, cookies, or decoded credentials.

## 3. Spring Security's Place in the Servlet Filter Chain

An HTTP request entering a Servlet app can follow this path:

```text
Servlet container
   |
   v
DelegatingFilterProxy (target "springSecurityFilterChain")
   |
   v
FilterChainProxy
   |
   +--> selects first SecurityFilterChain matching the request
           |
           +--> SecurityContextHolderFilter
           |      loads or defers loading SecurityContext from repository
           |
           +--> BasicAuthenticationFilter
           |      reads Authorization: Basic, authenticates if needed
           |
           +--> ExceptionTranslationFilter / AuthorizationFilter
                  checks appropriate authentication/authorization
           |
           +--> DispatcherServlet -> Controller
   |
   v
Response, clears SecurityContextHolder at end of processing
```

The diagram is a conceptual model; exact order and filter count depend on configuration, version, and added filters. What matters is that `SecurityContextHolderFilter` and `BasicAuthenticationFilter` have **distinct responsibilities**:

- `SecurityContextHolderFilter` enables the request to receive a context from `SecurityContextRepository` and clears the holder when done. Under Spring Security 6's **explicit save** model, this filter does not automatically save all context changes at the end of a request.
- `BasicAuthenticationFilter` reads the Basic header if present; when needed, it creates an authentication request and calls `AuthenticationManager`. On success, it puts `Authentication` into the context; subsequent persistence depends on the repository configured for the filter and the policy.
- `AuthorizationFilter` uses the current `Authentication` to decide if the request has permission to access the endpoint. Missing a Basic header **does not automatically fail the request** if a valid context was already loaded from a session accepted by the application.

**Do not confuse them:** `SecurityContextHolder` stores state for the current request processing execution, whereas `SecurityContextRepository` decides how state is loaded/saved across requests.

## 4. Stateless Basic: Each Request Must Carry Its Own Credentials

For an API choosing **`SessionCreationPolicy.STATELESS`** and a non-storing repository (`NullSecurityContextRepository`), Spring Security does not use `HttpSession` to retrieve `Authentication` for subsequent requests. Every request to a protected endpoint must itself carry a valid credential for the chain's authentication mechanism (here, HTTP Basic).

```text
GET /stateless/me + Authorization: Basic valid
     -> SecurityContextRepository does not load session auth
     -> BasicAuthenticationFilter triggers authentication
     -> returns 200 "learner"

GET /stateless/me (no Authorization)
     -> context has no auth from prior request
     -> protected request lacks authentication
     -> 401 + WWW-Authenticate

GET /stateless/me + Authorization: Basic valid (again)
     -> must verify credentials for the new request
     -> returns 200 "learner"
```

In real configurations, **authorization** also depends on other matchers/roles and filters. The example above assumes an endpoint requiring `authenticated()` and no secondary authentication mechanism.

### Does SessionCreationPolicy.STATELESS Mean “Never Any HttpSession Anywhere in the System”?

No. This policy states that Spring Security will not create/use `HttpSession` to obtain `SecurityContext` for that chain configuration. **Application code, MVC libraries, or other filters can still create an `HttpSession`** for their own reasons. Therefore, never inspect only for a `JSESSIONID` cookie to conclude a URL uses sessions for authentication.

If you want genuinely stateless security context behavior for an API, verify **all three**: session policy, `SecurityContextRepository`, and request cache / other authentication mechanisms.

### Does HTTP Basic Inherently Hold Persistent Authentication?

No. A Basic header carries only what is needed for that request. The server may authenticate via a provider whenever needed, yet the header itself never turns into “permanently logged in” or a session token. When a password changes or an account is disabled, a subsequent Basic request that re-checks has a chance to observe the updated state (depending on caching/account lookup).

## 5. Stateful Basic: Can Be Combined with HttpSession

HTTP Basic **does not forbid using sessions**. If an application configures a repository saving `SecurityContext` into `HttpSession` **and** the Basic authentication filter actually uses that repository to save upon success, subsequent requests can be restored from the session cookie.

```text
Request 1: Basic + valid password
     |
     +--> BasicAuthenticationFilter authenticates
     +--> SecurityContext is created/set
     +--> SecurityContextRepository.saveContext(...) writes to HttpSession
     +--> Response sends session cookie (if new session created)

Request 2: Session cookie but NO Basic header
     |
     +--> SecurityContextHolderFilter loads context from HttpSession
     +--> BasicAuthenticationFilter sees no Basic header so proceeds
     +--> AuthorizationFilter sees valid loaded Authentication
     +--> Controller returns 200

Request 3: NO cookie, NO Basic header
     |
     +--> no context is loaded
     +--> 401 Unauthorized
```

**Setting `SessionCreationPolicy.IF_REQUIRED` alone is not enough to guarantee Basic authentication is saved into the session.** With Spring Security 6 and explicit save, check both the **repository used to load the context** and the **repository `BasicAuthenticationFilter` uses to save on success**. In the runnable example below, we configure **the exact same `HttpSessionSecurityContextRepository` on both sides** to demonstrate this behavior.

### 5.1. What Is Actually Stored in HttpSession?

With `HttpSessionSecurityContextRepository`, what gets stored is the `SecurityContext` holding the authenticated `Authentication` (typically principal, authorities, and related details)—not the Basic header string as a session key. Spring Security may erase credentials on the authentication object depending on the provider/configuration.

The client holds a **session ID**; the server uses that ID to retrieve the session context. On server restart or session store expiration, data may be lost depending on session architecture. When the cookie is deleted, new requests cannot rely on that session, even though the browser might still cache Basic credentials and resend them automatically.

### 5.2. Session Present Yet Client Still Sends Basic Header: Is the Provider Called Again?

Not guaranteed. `BasicAuthenticationFilter` includes logic checking whether the existing authentication already satisfies the Basic request, avoiding unnecessary re-authentication for the same identity. When a context has been loaded from the session and a matching `Authentication` is still marked authenticated, the filter **may skip** calling `AuthenticationManager` for Basic credentials carrying the same username.

That leads to two distinctions:

- **Sending credentials on the wire** and **verifying credentials on the server** are two separate events.
- **Having a Basic header on every request** is insufficient to prove the server actually checked the password/account state on every request, especially when a session already holds authentication for the same principal.

When the username in the Basic header changes, when the existing authentication does not match, or when no valid context exists, the filter can trigger fresh authentication. Do not rely on an `Authorization: Basic` log entry to deduce the exact number of `PasswordEncoder.matches(...)` calls.

If policy **mandates re-evaluating the password or account lock status on every single request**, do not merely attach a Basic header and assume the provider runs every time. Design a stateless chain that does not load session authentication, control caching, and actively test credential revocation.

## 6. Two Sequence Diagrams Compared

### 6.1. A Stateless Request and the Next Request

```text
Client               SecurityContextHolderFilter    BasicAuthenticationFilter     Provider
  |                              |                           |                   |
  | GET /stateless/me + Basic    |                           |                   |
  |----------------------------->|-------------------------->| authenticate ----->|
  |                              |                           |<--- Authentication-|
  |                              |                           |  set context      |
  |<-----------------------------|---------------------------| 200               |
  |                              |                           |                   |
  | GET /stateless/me no Basic   |                           |                   |
  |----------------------------->|-- empty context ---------->| no header          |
  |<-----------------------------|---------------------------| 401               |
```

No security session is used to keep the user from the first request. The new request must satisfy the endpoint's authentication rules on its own.

### 6.2. A Session-Backed Request and the Next Request

```text
Client                 SecurityContextRepository       BasicAuthenticationFilter
  |                              |                                |
  | GET /session/me + Basic      |                                |
  |----------------------------->| initial context                |
  |                              |---- authenticate + save <------|
  |<-----------------------------| 200 + session cookie           |
  |                              |                                |
  | GET /session/me + Cookie     |                                |
  |----------------------------->| load context from session      |
  |                              |---- no Basic header ---------->|
  |<-----------------------------| 200 (existing authentication)  |
```

Depending on cookie/session policy, ordering, and specific filters, outcomes can differ if the app does not actually save the context or the cookie is not sent back. Therefore, test at the HTTP request level rather than merely inspecting `SecurityContextHolder` within a single request.

## 7. Runnable Spring Boot Example: Both Modes in One Application

The example uses **Java 17+, Spring Boot 3.3.5, Spring Security 6.x, Gradle 8.5**. Endpoints:

- `GET /stateless/me`: requires Basic on every request; does not use HTTP session for authentication.
- `GET /session/me`: the first request can use Basic; once Basic authentication is **explicitly saved to HttpSession**, subsequent requests with the session cookie can access it without sending a Basic header.
- All other paths are denied by the fallback chain per the demo policy.

We use one test account `learner / study123`, strictly for local use.

### 7.1. Project Structure

```text
http-basic-session-demo/
  settings.gradle
  build.gradle
  src/main/java/demo/
    DemoApplication.java
    SecurityConfig.java
    DemoController.java
  src/test/java/demo/
    BasicSessionTest.java
```

File `settings.gradle`:

```groovy
rootProject.name = 'http-basic-session-demo'
```

File `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

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
```

### 7.2. Startup Class

File `src/main/java/demo/DemoApplication.java`:

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

### 7.3. Configuring Three SecurityFilterChains

File `src/main/java/demo/SecurityConfig.java`:

```java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
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
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.NullSecurityContextRepository;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails learner = User.withUsername("learner")
                .password(encoder.encode("study123"))
                .roles("USER")
                .build();
        return new InMemoryUserDetailsManager(learner);
    }

    @Bean
    @Order(1)
    SecurityFilterChain statelessChain(HttpSecurity http) throws Exception {
        http.securityMatcher("/stateless/**");

        http.sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS));

        http.securityContext(context -> context
                .requireExplicitSave(true)
                .securityContextRepository(new NullSecurityContextRepository()));

        http.requestCache(cache -> cache.disable());

        http.authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated());

        http.httpBasic(Customizer.withDefaults());
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain sessionChain(HttpSecurity http) throws Exception {
        // Same repository for filter to load and Basic filter to save context.
        HttpSessionSecurityContextRepository repository =
                new HttpSessionSecurityContextRepository();

        http.securityMatcher("/session/**");

        http.sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED));

        http.securityContext(context -> context
                .requireExplicitSave(true)
                .securityContextRepository(repository));

        http.authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated());

        http.httpBasic(basic -> basic
                .securityContextRepository(repository));

        return http.build();
    }

    @Bean
    @Order(3)
    SecurityFilterChain fallbackDenyChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
```

**Reading the configuration layer by layer:**

- `@Order(1)` applies only to `/stateless/**`; combines `STATELESS`, `NullSecurityContextRepository`, and disabled request cache so new requests cannot use a security session from previous requests.
- `@Order(2)` applies only to `/session/**`; uses a single `HttpSessionSecurityContextRepository` instance for both `securityContext` (loading at request start) and `httpBasic` (saving upon successful authentication). This is the **key point** of the session-backed example.
- `@Order(3)` matches all remaining paths with `denyAll`; prevents new routes from accidentally falling outside all security chains.
- `SessionCreationPolicy.IF_REQUIRED` allows Spring Security to create a session when needed; it **does not mean every request creates a session automatically**.
- `requireExplicitSave(true)` makes Spring Security 6's contract explicit. Configuring the Basic filter to use a repository to save differs from merely calling `SecurityContextHolder.setContext(...)`.

The demo account hashes passwords with BCrypt instead of storing plaintext in `UserDetailsService`. Never hardcode accounts/passwords in real products; use proper user stores and secrets management.

### 7.4. Controller

File `src/main/java/demo/DemoController.java`:

```java
package demo;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping({"/stateless/me", "/session/me"})
    public String me(Authentication authentication) {
        return authentication.getName();
    }
}
```

The controller does not care whether authentication came from the current request's Basic header or from a context restored from a session. The `Authentication` received by the controller is the result of the Security filter chain.

### 7.5. Testing with MockMvc

File `src/test/java/demo/BasicSessionTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class BasicSessionTest {

    @Autowired
    MockMvc mvc;

    @Test
    void statelessRequiresBasicCredentialsOnEachIndependentRequest()
            throws Exception {
        MvcResult first = mvc.perform(get("/stateless/me")
                        .with(httpBasic("learner", "study123")))
                .andExpect(status().isOk())
                .andExpect(content().string("learner"))
                .andReturn();

        // Stateless chain does not need to create an HttpSession for security context.
        assertNull(first.getRequest().getSession(false));

        mvc.perform(get("/stateless/me"))
                .andExpect(status().isUnauthorized());

        mvc.perform(get("/stateless/me")
                        .with(httpBasic("learner", "study123")))
                .andExpect(status().isOk())
                .andExpect(content().string("learner"));
    }

    @Test
    void sessionModeReusesSavedContextWithoutRepeatingBasicHeader()
            throws Exception {
        MvcResult first = mvc.perform(get("/session/me")
                        .with(httpBasic("learner", "study123")))
                .andExpect(status().isOk())
                .andExpect(content().string("learner"))
                .andReturn();

        MockHttpSession session =
                (MockHttpSession) first.getRequest().getSession(false);
        assertNotNull(session);

        // New request: carries session only, no Basic header.
        mvc.perform(get("/session/me").session(session))
                .andExpect(status().isOk())
                .andExpect(content().string("learner"));

        // Same session ID does not bypass a chain intentionally configured STATELESS.
        mvc.perform(get("/stateless/me").session(session))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void noSessionAndNoBasicHeaderIsUnauthorized() throws Exception {
        mvc.perform(get("/stateless/me"))
                .andExpect(status().isUnauthorized());

        mvc.perform(get("/session/me"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void wrongBasicPasswordIsRejected() throws Exception {
        mvc.perform(get("/stateless/me")
                        .with(httpBasic("learner", "wrong")))
                .andExpect(status().isUnauthorized());

        mvc.perform(get("/session/me")
                        .with(httpBasic("learner", "wrong")))
                .andExpect(status().isUnauthorized());
    }
}
```

Expected outcome with the demo configuration: **4 tests PASS**. This tests Spring Security's HTTP request behavior. It avoids `@WithMockUser` because `@WithMockUser` pre-populates authentication into the context and hides what must be proven: **whether the Basic filter creates/saves authentication**.

The most important contrast lies in `sessionModeReusesSavedContextWithoutRepeatingBasicHeader`: the first request sends Basic credentials; the second request carries only `MockHttpSession` without `httpBasic`, yet still reaches the controller thanks to the repository loading the context.

### 7.6. Running and Testing with curl

Install JDK 17+ and compatible Gradle 8.5. From the project root:

```bash
gradle test
gradle bootRun
```

If you generated the Gradle Wrapper, you can run `./gradlew` on macOS/Linux or `.\gradlew.bat` on Windows.

**Stateless group:**

```bash
curl -i -u learner:study123 http://localhost:8080/stateless/me
curl -i http://localhost:8080/stateless/me
curl -i -u learner:wrong http://localhost:8080/stateless/me
```

Expected respectively: **200**, **401**, **401**.

**Session-backed group:** save the cookie from a successful Basic call; subsequent requests send only the cookie without `-u`:

```bash
curl -i -c cookies.txt -b cookies.txt -u learner:study123 \
  http://localhost:8080/session/me

curl -i -b cookies.txt \
  http://localhost:8080/session/me

curl -i \
  http://localhost:8080/session/me
```

Expected respectively: **200**, **200**, **401** (the last call sends neither Basic nor cookie). Cookie name/value and runtime headers are not fixed output; look for `Set-Cookie` when a new session is created.

**Never use plain HTTP to transmit passwords over public networks.** `http://localhost` is strictly for local practice; real systems require HTTPS, strict cookie policies, and an appropriate authentication mechanism.

### 7.7. Observed Result Matrix

| Request and credentials | Stateless chain | Session-backed chain |
| --- | --- | --- |
| Valid Basic, no prior session | 200 | 200 and may create/save session |
| New request with only valid cookie from successful Basic | 401 | 200 (with repository as in demo) |
| New request with no cookie, no Basic | 401 | 401 |
| Invalid Basic, no valid context | 401 | 401 |
| Valid Basic on an independent new request | 200, requires independent auth | 200, may create/save session |
| Existing session cookie context plus Basic with same username | Does not use session authentication | Filter may reuse existing authentication instead of re-authenticating |

All HTTP statuses above assume endpoints require `authenticated()` and no proxy/SSO/other filter alters authentication. Never assume the exact same outcome for every app merely because `httpBasic()` is enabled.

## 8. Exactly When Does BasicAuthenticationFilter Call AuthenticationManager?

Mental model when handling a request:

```text
New request
  |
  +--> Does SecurityContextRepository load a valid Authentication?
  |        |
  |        +--> yes, if session-backed and session exists
  |        +--> no, if stateless/null repository
  |
  +--> Is Authorization: Basic ... present?
           |
           +--> no: Basic filter does not password-authenticate on its own
           |          -> existing context may be used
           |          -> without context, protected endpoint is blocked
           |
           +--> yes:
                  -> do Basic credentials require new authentication?
                         |
                         +--> needed: call AuthenticationManager
                         |             -> UserDetailsService/PasswordEncoder...
                         |             -> set/save SecurityContext if successful
                         |
                         +--> not needed: use existing Authentication
```

This is an explanatory model, not a copy of source code. Exact details of “is authentication required?” depend on the `BasicAuthenticationFilter` and `SecurityContextHolderStrategy` versions. In a typical implementation, the filter may compare the identity in the Basic header against the current authentication and its `isAuthenticated()` status.

### Why Shouldn't You Measure by Request Count?

The same number of requests can trigger different provider execution counts:

- 10 requests to a stateless chain, each with valid Basic → typically 10 authentication checks, barring provider/infrastructure caching or optimizations.
- 10 requests to a session-backed chain after login → may execute Basic authentication once on the first request and reuse the saved context nine times.
- 10 requests carrying a Basic header when a session context for the same username is already authenticated → the Basic filter may skip calling the provider again as one might assume.
- If the HTTP client clears cookies and does not retain credentials, the next request has no authentication → 401.

**To prove re-authentication, measure at the right boundary:** instrument `AuthenticationProvider.authenticate(...)`/`UserDetailsService.loadUserByUsername(...)` or add tests resetting account/session state. Never draw conclusions from request counts, header counts, or the number of “Securing GET...” log lines alone.

## 9. What Do SecurityContextRepository and SessionCreationPolicy Decide?

| Name | Function | Note |
| --- | --- | --- |
| `SecurityContextHolder` | Context for the current request/thread | Cleared at end of request; not automatically persisted |
| `SecurityContextHolderFilter` | Loads context from repository and clears holder | Explicit-save does not auto-write every change |
| `NullSecurityContextRepository` | Does not persist context to durable store | Fits stateless security |
| `RequestAttributeSecurityContextRepository` | Holds context in request attributes, supporting dispatches within one request | Does not persist across independent HTTP requests |
| `HttpSessionSecurityContextRepository` | Saves/reads context via `HttpSession` | Can reuse authentication across subsequent requests |
| `DelegatingSecurityContextRepository` | Combines multiple repositories | Must inspect which delegate is session-backed |
| `SessionCreationPolicy.STATELESS` | Does not create or use sessions to obtain SecurityContext | Does not forbid other code from creating HttpSession |
| `SessionCreationPolicy.IF_REQUIRED` | Allows creating a session when needed | Does not mean every filter saves context by default |
| `SessionCreationPolicy.NEVER` | Spring Security does not create sessions, yet may use an existing one | **Not** synonymous with stateless |
| `SessionCreationPolicy.ALWAYS` | Spring Security creates sessions per policy | Does not replace configuring context saving under explicit save |

**Spring Security 6 note:** when `SecurityContextHolderFilter` requires explicit save, custom authentication code must call `SecurityContextRepository.saveContext(context, request, response)` to persist context across requests. Standard authentication filters can be configured to save; for example, `httpBasic(basic -> basic.securityContextRepository(repo))` above handles that for the Basic flow.

Do not write a custom login controller that only calls `SecurityContextHolder.setContext(...)` expecting `SessionCreationPolicy.IF_REQUIRED` to save it automatically. Session policy governs session creation/use, while the repository and filter govern saving/loading authentication.

## 10. Security Consequences: Account Revocation, Password Change, and Logout

### 10.1. Password Changed While Session Still Exists

In a stateless chain, when a Basic header is re-authenticated on a new request, checking the new password and account status can reflect the change. Yet if the provider/UserDetails is cached or data lags, results might not update immediately.

In a session-backed chain, if a new request merely loads the old `SecurityContext` from the session, `PasswordEncoder.matches(...)` may **not run**. Hence changing a password, disabling an account, or locking a user in the database does not automatically prove old sessions were revoked.

**If immediate revocation is required:** implement session invalidation, a session registry/revocation mechanism, or appropriate re-authentication/account-status checks. A session with `Authentication.isAuthenticated() == true` does not guarantee the account in the database is still active.

### 10.2. HTTP Basic Has No Standard Logout Like Form Login

Browsers can store Basic credentials and resend them automatically within the matching scope. A server endpoint returning 401 or invalidating a session **does not necessarily** clear browser-cached credentials. An application's logout feature must account for this:

- If a session exists, invalidate the session and clear security context and cookies per policy;
- If the Basic header keeps being sent, the server may re-authenticate the user **immediately again**;
- Never assume `logoutSuccess` caused the browser to “forget” cached passwords;
- For explicit logout requirements, prefer a more suitable login/token mechanism over direct HTTP Basic.

Never mistake clearing `SecurityContextHolder` for a single request with “revoking all sessions”.

### 10.3. Cookie Authentication and CSRF

When an application uses a session cookie to recognize a user on subsequent requests, browsers can send cookies automatically. This makes **CSRF protection** critical for state-changing actions. Never disable CSRF by default just because the app originally used HTTP Basic.

For a purely stateless API accepting only Basic headers explicitly controlled by clients, CSRF analysis differs from a web app with automatic cookies. Yet browsers can cache and auto-attach Basic credentials, so **you cannot claim “using Basic means no CSRF”**. Evaluate how clients send credentials, cookies, CORS, `SameSite`, request origins, and real POST/PUT/DELETE operations.

The demo contains only GET endpoints so no CSRF token is needed. If adding POST endpoints, test CSRF explicitly or apply a CSRF policy analyzed per chain architecture.

### 10.4. Session Fixation and Session Limits

Spring Security's standard login mechanisms can coordinate with session authentication strategies to protect against session fixation, limit concurrent sessions, and so on. When intentionally allowing **HTTP Basic to create persistent sessions**, do not assume every form-login session authentication strategy step runs identically. Verify version/configuration, session ID rotation, timeouts, concurrent session policies, and logout.

The `/session/me` example demonstrates **intentional** persistence; it is not a complete guide to production browser login. For real apps, it is usually better to pick a dedicated login/session mechanism rather than mixing Basic credentials and session cookies without a clear policy.

### 10.5. Session Cookies and Transport

For production environments:

- Use HTTPS to protect both Authorization headers and session cookies.
- Set cookie attributes `Secure`, `HttpOnly`, and `SameSite` suited to your threat model; avoid session IDs in URLs.
- Rotate/invalidate sessions per policy and set appropriate idle/absolute timeouts.
- Avoid writing credentials, Authorization headers, session IDs, or cookies into unsafe logs or metrics.
- Rate-limit logins and defend against credential stuffing / add MFA where appropriate.

## 11. Common Misconceptions

### 11.1. “HTTP Basic Is Always Stateless by Default”

**Do not state that.** HTTP Basic is an authentication scheme; session behavior is an application/framework configuration choice. Inspect `SecurityFilterChain`, `SecurityContextRepository`, `SessionCreationPolicy`, and how the Basic filter saves context. Some default Spring Security setups may use sessions for request caching or other purposes; seeing a session cookie alone does not prove authentication is stored inside it.

### 11.2. “Having JSESSIONID Means the Server No Longer Needs Basic”

Not necessarily. A session might exist due to CSRF/request cache/MVC yet **hold no authentication**; the Basic filter might be saving context in request attributes instead of the session. To test, send a new request **with only the cookie** to an auth-required endpoint without an Authorization header. If you get 401, the cookie alone is insufficient in that setup.

### 11.3. “Having a Basic Header Guarantees Password Verification on Every Request”

No. If a valid `Authentication` from a session is already loaded and the Basic filter sees the same identity, it may skip calling the provider. Re-authentication is not measured by header presence.

### 11.4. “IF_REQUIRED Alone Keeps You Logged In”

No. If the authentication filter does not save to a session-backed repository in an explicit-save flow, context will not persist across requests. Configure **both loading and saving** properly.

### 11.5. “STATELESS Forbids Any Code from Creating a Session”

No. It only sets the policy regarding Spring Security using sessions for the security context; other code can still create sessions. Inspect the cookie/session source rather than inferring from browser state.

### 11.6. “Basic Is Secure Password Encryption Because Base64 Looks Unreadable”

Wrong. Base64 decodes effortlessly; HTTP Basic must travel over TLS. HTTPS protects transit, yet does not replace database password hashing, rate limiting, or credential policies.

### 11.7. “Logout Makes Browsers Delete Basic Credentials”

There is no standard guarantee like that. Browsers may keep resending cached Authorization headers; session invalidation and clearing the holder do not wipe the browser's credential cache.

### 11.8. “Changing the Password Automatically Makes All Session Requests Return 401”

No. An old session-backed context can still be loaded without re-checking the password. Immediate revocation requires proper invalidation/revalidation mechanisms.

### 11.9. “Every URL Shares the Same Policy”

Not when the app has multiple `SecurityFilterChain`s. One chain for `/stateless/**` and one for `/session/**` can differ completely in repository, session, and CSRF settings. `FilterChainProxy` chooses the **first matching chain**. Never test `/stateless/me` and apply the conclusion to `/session/me`.

## 12. Debugging Checklist in a Running Application

When a request unexpectedly returns 200/401:

1. **Identify the exact URL and chain.** Which matcher selects the request, what is the chain's `@Order`, is there a fallback chain?
2. **Inspect headers and cookies.** Is `Authorization: Basic` present? Is a session cookie present? Did the client attach credentials or cookies automatically?
3. **Inspect the context-loading repository.** Does the chain's `SecurityContextHolderFilter` use `NullSecurityContextRepository`, `HttpSessionSecurityContextRepository`, or another repository?
4. **Inspect context saving after authentication.** Is the Basic filter configured to use the same session-backed repository? Does `requireExplicitSave` affect any custom flow?
5. **Check session policy.** Does `STATELESS`/`NEVER`/`IF_REQUIRED`/`ALWAYS` match the URL's goal?
6. **Run two independent requests.** First Basic succeeds; second request cookie-only; third request neither cookie nor Basic.
7. **Test account changes.** Change password/lock user and verify whether requests using old sessions are blocked per policy.
8. **Measure the provider if needed.** Instrument `AuthenticationProvider.authenticate` or `UserDetailsService`; do not merely count Authorization headers.
9. **Compare 401 vs 403.** 401 typically means missing/invalid credentials in the demo; 403 means missing permissions or CSRF; exact output depends on entry point and handler.
10. **Never log secrets.** Never put raw passwords, Basic headers, cookies, or session IDs into debug logs while troubleshooting.

During development debugging, controlled DEBUG logging can be enabled:

```properties
logging.level.org.springframework.security=DEBUG
```

Do not leave overly verbose logging on sensitive data in production. Log lines like “Securing GET ...” show the request entered the filter chain; they **do not prove** the provider re-verified the password.

## 13. Self-Check Questions

1. **Does HTTP Basic create a session under the RFC standard?** No. The protocol defines how credentials/challenges are presented, not Spring Security's session mechanism.
2. **In a STATELESS chain, can a second request without a Basic header reuse the first request's authentication?** Not via `HttpSession`, with NullSecurityContextRepository and no other auth mechanism.
3. **Why can a cookie still be created in an app with a stateless chain?** Other code or components may use sessions; that does not prove the stateless chain used a session to load authentication.
4. **What is required for a Basic login to be reused on a subsequent cookie-only request?** A session-backed repository and an authentication mechanism that actually saves `SecurityContext` into that repository, plus a valid cookie on the next request.
5. **Does sending a Basic header on every request guarantee the password is re-checked?** No; the filter may reuse a matching authenticated context and skip re-authenticating.
6. **Do HTTP Basic and session cookies carry the same kind of data?** No; Basic carries Base64-recoverable credentials, whereas cookies typically carry a session ID.
7. **Does changing a password automatically revoke old sessions?** Never assume so; a session revocation/revalidation policy is required.
8. **Does `SessionCreationPolicy.IF_REQUIRED` automatically save context in every custom auth flow?** No, explicit-save requires the authentication mechanism to save the context.
9. **Why must HTTP Basic be paired with HTTPS?** Base64 does not protect passwords on the wire.
10. **How do you verify whether an app uses session authentication?** Test a first request with Basic, a second request with only the cookie and no Authorization header, compare 200/401, and inspect the repository configuration.

**Remember:** HTTP Basic is **not synonymous** with stateless or stateful. The `Authorization: Basic` header is how credentials are supplied; `SecurityContextRepository` and `SessionCreationPolicy` determine how the server restores authentication across requests; `BasicAuthenticationFilter` decides when `AuthenticationManager` must be called. To require independent authentication on every request, configure stateless explicitly and test; to keep a session, configure both **loading and saving** of context and test a second request **without a Basic header**. Always protect Basic credentials and session cookies with HTTPS and sound security policies.
