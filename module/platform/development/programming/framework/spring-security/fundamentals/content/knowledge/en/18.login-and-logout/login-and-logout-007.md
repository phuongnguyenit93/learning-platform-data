# Remember-Me Differs from Extending a Login Session

> **Spring Security – fundamentals** · Group: **Login and Logout**. This lesson distinguishes the mechanism of re-authenticating with a remember-me credential from keeping an HTTP session alive longer. The focus is Servlet/Spring MVC and Spring Security 6.x APIs; when using another version, consult its corresponding documentation.

## 1. What will you learn?

After this lesson, you can explain the lifecycle of `HttpSession`, session IDs, and remember-me cookies; understand how Spring Security automatically logs a user back in when the session is gone; distinguish `RememberMeAuthenticationToken` from a full authentication session; compare hash-based and persistent tokens; configure Java 17/Spring Boot; write real tests; and design safely around logout, CSRF, cookie flags, timeouts, and revocation.

**Core idea from the start:** extending a session means **keeping existing authentication state** longer; remember-me means **holding a separate piece of evidence to re-authenticate** if the old session state is gone. They can coexist, but they are not the same mechanism.

## 2. HTTP does not remember users across requests by itself

HTTP sends semantically independent requests. A subsequent request does not automatically carry information from the previous request. Traditional web applications maintain login by having the browser send a session identifier to the server on each request:

~~~text
Browser: Cookie: JSESSIONID=sid1
    |
    v
Server looks up SessionStore[sid1] -> SecurityContext(Authentication: alice)
    |
    v
Evaluate permissions for current request
~~~

Sessions usually reside in RAM or a server-side store; the browser holds the lookup identifier. `JSESSIONID` is a common cookie name on the Servlet stack, though it can change when using Spring Session or container settings. The cookie is not the entire session object. Having a `JSESSIONID` cookie also **does not prove the user is logged in**: an anonymous session can be created to hold a CSRF token or a saved request.

In Spring Security Servlet, `SecurityContext` holds `Authentication`. `SecurityContextRepository` is responsible for loading/saving the context; a common implementation is `HttpSessionSecurityContextRepository` or a `DelegatingSecurityContextRepository`. `SecurityContextHolder` supplies the context during request processing, rather than being the durable storage across requests itself.

## 3. What does "extending the login session" actually change?

Suppose the server configures the session idle timeout from 20 minutes to 8 hours:

~~~properties
server.servlet.session.timeout=8h
~~~

This affects how long the server retains an inactive `HttpSession`, depending on how the container/session store manages TTL. If the session still exists and the browser sends the matching session ID, Spring Security can restore the saved authentication. **No remember-me re-authentication is needed.**

If the session expires/is invalidated or the browser stops sending the right session ID, increasing the timeout does not create new credentials. The server cannot resurrect a vanished session merely by remembering a username in the UI.

Making the timeout too long has consequences:

- A stolen session credential can be used longer if not revoked.
- The session store must hold more objects, increasing RAM/cache/replication costs.
- Distinguishing "the user just entered a password" from "the device is being remembered" becomes harder.
- Browser cookie TTL and server idle timeout are not necessarily synchronized: a cookie's `Max-Age` does not keep the server session alive forever.
- Browsers may restore session cookies after a restart depending on restore settings; never treat closing a tab as a security boundary.

Therefore, **"so users don't have to log in too often"** does not always mean **"keep the session alive for a month."**

## 4. What is remember-me?

Remember-me, also called **persistent-login authentication**, is a mechanism allowing the application to re-identify a user after the normal HTTP login session is gone. The system typically issues a **separate cookie** when the user logs in successfully and selects "Remember me" or "Remember this device."

In Servlet/Spring Security, when a request has no `Authentication` in its context, `RememberMeAuthenticationFilter` can use `RememberMeServices.autoLogin(...)` to verify the remember-me cookie. If valid, it creates a `RememberMeAuthenticationToken` for the request. Depending on session policy, the system may create/save a new session, but doing so **does not revive the old session**.

### Two cookies with different purposes

| Component | Example name | Nature | When used? |
| --- | --- | --- | --- |
| Session cookie | `JSESSIONID` | Carries session ID to look up an existing session | Requests with a valid session |
| Remember-me cookie | `remember-me` | Carries remember credential to auto-authenticate again | When no valid authentication exists in context |
| CSRF token | `_csrf` in form or token in header | Proves a state-changing request comes from a valid flow per CSRF mechanism | Unsafe operations like POST/PUT/DELETE |
| User password | Should not be stored in cookies | Secret for interactive authentication | Login/reauthentication |

The last cookie name is customizable. **Both session cookies and remember-me cookies are sensitive credentials**; anyone obtaining a valid copy risks impersonating the user within policy bounds. Never share or log raw values.

## 5. Two timelines: diverging when the session is lost

### Scenario A: without remember-me

~~~text
09:00 Alice logs in -> creates session S1 -> JSESSIONID=s1
09:10 request with s1 -> uses Authentication from S1
11:00 S1 timed out -> no Authentication remains
11:01 request with old s1 cookie -> no valid session found
Result: Alice must log in again
~~~

Session timeout can happen due to idle timeout, invalidation, store infrastructure, or logout. The cookie may still sit in the browser, yet the server no longer recognizes the old session ID.

### Scenario B: with remember-me

~~~text
09:00 Alice logs in + checks Remember me
      Server creates S1 and remember token R1
      Browser holds JSESSIONID=s1 and remember-me=r1

09:10 request sends s1, r1
      S1 still valid => uses full Authentication from S1
      RememberMeAuthenticationFilter does not need auto-login

11:00 S1 has expired
11:01 new request still has remember-me=r1, no valid S1
      RememberMeServices verifies r1
          - valid: creates RememberMeAuthenticationToken for Alice
          - invalid: no auto-login; requires reauthentication

11:02 a sensitive endpoint requires fullyAuthenticated()
      valid remember token is still insufficient -> requires full login
~~~

**Conclusion:** S1 was not "extended." R1 enabled the application to create authentication at the remember-me level **after S1 was lost**. Whether an action is allowed still depends on authorization rules.

## 6. Internal Spring Security flow

Components to understand:

1. `UsernamePasswordAuthenticationFilter` or interactive authentication filter: processes username/password.
2. `RememberMeServices`: interface with `loginSuccess(...)`, `loginFail(...)`, and `autoLogin(...)`.
3. `RememberMeAuthenticationFilter`: when no authentication is present yet, checks remember-me credentials.
4. `TokenBasedRememberMeServices` or `PersistentTokenBasedRememberMeServices`: verifies according to each strategy.
5. `RememberMeAuthenticationToken` and `RememberMeAuthenticationProvider`: represent and validate remember-me authentication.
6. `SecurityContextRepository`/session handling: loads/saves context as needed; do not confuse with the remember-me token store.
7. `AuthorizationFilter`/method authorization: ultimately decides whether an endpoint/action permits remember-me authentication.

Overview diagram:

~~~text
Request -> SecurityFilterChain
             |
             v
      Authentication already present from session/context?
             | YES                     | NO
             v                         v
       Authorization           RememberMeAuthenticationFilter
                                       |
                               Has remember cookie?
                                /             \
                              NO               YES
                              |                 |
                         anonymous        verify token
                                               |
                                      fail -----+----- valid
                                       |                 |
                                  anonymous   RememberMeAuthenticationToken
                                       \                 /
                                         Authorization
~~~

This is a general model, not a detailed specification of every filter's exact position across versions.

### When is a remember-me cookie issued?

With form login, the remember-me service is invoked after authentication succeeds. By default, it typically requires a checkbox parameter such as `remember-me=on`. Some configurations may use `alwaysRemember(true)`, though doing so should consider user consent on shared machines.

If the user does not select remember-me, **a normal session can still work**. Having no remember cookie does not mean not logged in. And if the browser has a remember cookie while the request uses full session auth, the current authentication remains full, not remember-me.

## 7. Remember-me does not have the same trust level as full login

Spring Security lets you distinguish:

| State | `authenticated()` | `fullyAuthenticated()` |
| --- | --- | --- |
| Anonymous | Fails | Fails |
| Valid `RememberMeAuthenticationToken` | Passes | Fails |
| Full interactive login | Passes | Passes (per Spring Security's trust resolver) |

DSL example inside a `SecurityFilterChain` bean:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/profile").authenticated()
    .requestMatchers("/api/strong").fullyAuthenticated()
    .anyRequest().denyAll()
);
~~~

With only a remember cookie left, a user can view their profile but cannot perform a sensitive action requiring full login. With a form-login entry point, being rejected for remember-me login usually results in a redirect to the login page, not necessarily HTTP 403; behavior depends on configuration.

`fullyAuthenticated()` **does not by itself prove the user just completed MFA**, re-entered a password within 5 minutes, or holds a specific `acr` level. For operations like money transfers, password changes, adding MFA devices, creating API keys, or deleting data, consider step-up authentication/MFA and a dedicated "recent login" policy.

In method security (with `@EnableMethodSecurity` enabled), you can use:

~~~java
@PreAuthorize("isFullyAuthenticated()")
public void changePassword(String newPassword) {
    // Illustrative business code; handle passwords securely in practice.
}
~~~

This fragment is not a standalone Java file. Never put real passwords into logs or store raw passwords.

## 8. Two remember-me mechanisms supported by Spring Security

### 8.1. Hash-based token: TokenBasedRememberMeServices

This mechanism needs no separate token table. After successful login, the server computes a signed/hashed value based on username, expiration time, algorithm, password info stored in `UserDetailsService`, and a secret key. General format in documentation:

~~~text
base64(
  username + ":" + expirationTime + ":" + algorithmName + ":" +
  hash(username + ":" + expirationTime + ":" +
       storedPassword + ":" + serverKey)
)
~~~

The formula is only for understanding verification; **do not implement crypto from the string above yourself**. On incoming requests, Spring Security checks expiration, loads the user, and recomputes the verification value.

**Advantages:** minimal infrastructure, easy to demo.

**Important drawbacks:**

- Stolen credentials can be **replayed** on another device until expiration or until verification inputs change.
- There is no per-token server-side record, making individual device revocation difficult.
- Changing the password hash or secret key can invalidate old cookies; key rotation can affect many users.
- The secret key must be strong, kept confidential, and consistent across application instances.
- The cookie does not contain the raw password, yet this implementation may expose the username in the encoded payload.

### 8.2. Persistent token: PersistentTokenBasedRememberMeServices

This mechanism requires a `PersistentTokenRepository` with server-side token state, such as JDBC. Traditional table:

~~~sql
CREATE TABLE persistent_logins (
    username VARCHAR(64) NOT NULL,
    series VARCHAR(64) PRIMARY KEY,
    token VARCHAR(64) NOT NULL,
    last_used TIMESTAMP NOT NULL
);
~~~

A `series/token` pair is used for verification. The server can **rotate the token** upon successful auto-login and update the repository, shortening the window during which an old credential can be reused; an old token reappearing can be treated as a sign of replay/theft per the implementation.

Classes to know:

- `PersistentTokenRepository`: interface for storing/looking up/updating/removing tokens.
- `JdbcTokenRepositoryImpl`: stores tokens in a database.
- `InMemoryTokenRepositoryImpl`: suitable only for tests/demos, not production storage.
- `PersistentTokenBasedRememberMeServices`: remember-me implementation using the repository.

In real products, the default schema does not provide full "device management": you need device metadata, revoke-all-devices, expiry cleanup, handling races/concurrent requests, token-theft response, and auditing. A persistent token is still a bearer credential and cannot be treated as completely risk-free.

### Quick comparison

| Criterion | Hash-based | Persistent |
| --- | --- | --- |
| Separate token repository | No | Yes |
| Cookie contents | Username/expiry/signature | Series + token |
| Revoking an individual token | Limited | Can be designed |
| Rotation on reuse | Not repository-backed | Has token update mechanism |
| Password change | Usually invalidates old cookies | Must coordinate token revocation per policy |
| Multi-instance | Consistent shared secret & user store | Shared DB/token store and config |
| Operations | Simpler | Adds storage, cleanup, concurrency |
| Risk if stolen | Replay until expiry/key or password change | Replay risk exists, mitigated by state/rotation/revocation |

Spring Security docs describe both main types and require a compatible `UserDetailsService`. If an application authenticates via OIDC/LDAP/JWT without a corresponding `UserDetailsService`, do not assume enabling remember-me will automatically work.

## 9. Hands-on example: Java 17 + Spring Boot

The demo application uses **Spring Boot 3.5.7** (Spring Security 6.5 line), **Spring MVC/Servlet**, Java 17+, and Maven. It has form login, hash-based remember-me, a session shorter than the remember token, a profile endpoint accepting remember-me, and a strong endpoint requiring full login.

Structure:

~~~text
remember-demo/
  pom.xml
  src/main/java/com/example/rememberdemo/
    RememberDemoApplication.java
    SecurityConfig.java
    DemoController.java
  src/main/resources/application.properties
  src/test/java/com/example/rememberdemo/
    RememberFlowTests.java
~~~

### 9.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.7</version>
    <relativePath/>
  </parent>
  <groupId>com.example</groupId>
  <artifactId>remember-demo</artifactId>
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

### 9.2. RememberDemoApplication.java

~~~java
package com.example.rememberdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RememberDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(RememberDemoApplication.class, args);
    }
}
~~~

### 9.3. SecurityConfig.java

~~~java
package com.example.rememberdemo;

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
    SecurityFilterChain chain(HttpSecurity http, UserDetailsService users)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/api/public", "/error").permitAll()
                .requestMatchers("/api/strong").fullyAuthenticated()
                .requestMatchers("/api/profile").authenticated()
                .anyRequest().denyAll())
            .formLogin(Customizer.withDefaults())
            .rememberMe(remember -> remember
                .key("local-demo-only-replace-with-long-secure-secret")
                .userDetailsService(users)
                .rememberMeParameter("remember-me")
                .tokenValiditySeconds(7 * 24 * 60 * 60))
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED))
            .logout(logout -> logout
                .invalidateHttpSession(true)
                .logoutSuccessUrl("/?logout"))
            .csrf(Customizer.withDefaults());
        return http.build();
    }

    @Bean
    PasswordEncoder encoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("demo123"))
            .roles("USER")
            .build();
        return new InMemoryUserDetailsManager(alice);
    }
}
~~~

**Security notes:**

- The hardcoded secret string is **for demo only**; production must place the secret in a vault/env with a rotation policy and ensure consistency across instances.
- The BCrypt hash for the in-memory user is newly generated on each app restart; with hash-based remember-me, old tokens **can become invalid after restart** because the signature depends on the stored password hash. Production needs a persistent user store.
- `tokenValiditySeconds(7 * 24 * 60 * 60)` gives the remember token a **7-day** lifetime; **it does not make the server session live 7 days**.
- `SessionCreationPolicy.IF_REQUIRED` allows creating a session when needed, distinct from the remember token.
- Do not disable CSRF because browser form login/logout uses cookies. POST login requires a CSRF token.
- Username/password login uses demo credential `alice/demo123` on localhost only; never use it in production.
- The `.rememberMe(...)` DSL automatically configures the corresponding Spring Security components; do not manually add duplicate filters.

### 9.4. DemoController.java

~~~java
package com.example.rememberdemo;

import java.util.Map;
import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    private final AuthenticationTrustResolver resolver =
        new AuthenticationTrustResolverImpl();

    @GetMapping("/")
    public String home() {
        return "Demo remember-me: open /api/profile after login";
    }

    @GetMapping("/api/public")
    public String publicEndpoint() {
        return "public";
    }

    @GetMapping("/api/profile")
    public Map<String, Object> profile(Authentication auth) {
        return Map.of(
            "username", auth.getName(),
            "rememberMe", resolver.isRememberMe(auth)
        );
    }

    @GetMapping("/api/strong")
    public String strong() {
        return "full-login-required";
    }
}
~~~

`AuthenticationTrustResolverImpl.isRememberMe(auth)` reflects the **current authentication type**. When the browser has both a remember cookie and a valid session after interactive login, requests normally use full authentication from the session, so `rememberMe=false` even if the checkbox was ticked. When the session is lost, the remember cookie creates a different authentication, so it can return `rememberMe=true`.

### 9.5. application.properties

~~~properties
server.port=8080
server.servlet.session.timeout=20m
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.same-site=lax
~~~

Notice **20 minutes** is the session idle timeout and **7 days** is the remember token validity. Cookie Max-Age and server TTL remain two separate mechanisms.

In production, use HTTPS, set `Secure` for both session and remember cookies, verify `HttpOnly`/`SameSite`/`Domain`/`Path` on each cookie, and evaluate HTTPS termination at reverse proxies. Servlet session cookie properties **do not necessarily apply automatically to the remember-me cookie**. Never expose tokens in logs, URLs, screenshots, or bug reports.

### 9.6. Running

Inside the directory containing `pom.xml`:

~~~bash
mvn clean test
mvn spring-boot:run
~~~

Or Maven Wrapper if generated via Spring Initializr:

~~~bash
./mvnw test
./mvnw spring-boot:run
~~~

On Windows PowerShell: `.\mvnw.cmd test` and `.\mvnw.cmd spring-boot:run`.

Open `http://localhost:8080/api/profile` while not logged in: expected redirect to `/login`. Log in with `alice/demo123` and check remember-me if the form displays the checkbox. If using a custom form, send parameter `remember-me=on` on successful login. Expected JSON while the session exists (key order may vary):

~~~json
{
  "username": "alice",
  "rememberMe": false
}
~~~

Then **delete only the session cookie** in the test environment, keep the remember cookie, and call `/api/profile` again. While the cookie is valid, expected result:

~~~json
{
  "username": "alice",
  "rememberMe": true
}
~~~

`/api/strong` with only the remember cookie must require full authentication, usually redirecting to `/login`. This does not prove the token is invalid; it proves the policy does not accept remember-me for sensitive actions.

The JSON/statuses in this lesson are **expected results from the configuration**; run the app/tests on your machine to verify actual behavior. If the auto-generated login page does not show a checkbox due to customization/version, the tests in the next section still send the parameter explicitly.

## 10. Testing with MockMvc: no old session needed, but remember cookie required

Create `src/test/java/com/example/rememberdemo/RememberFlowTests.java`:

~~~java
package com.example.rememberdemo;

import jakarta.servlet.http.Cookie;
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
class RememberFlowTests {

    @Autowired
    MockMvc mvc;

    private MvcResult loginAndRemember() throws Exception {
        return mvc.perform(post("/login")
                .with(csrf())
                .param("username", "alice")
                .param("password", "demo123")
                .param("remember-me", "on"))
            .andExpect(status().is3xxRedirection())
            .andReturn();
    }

    @Test
    void anonymousCannotSeeProfile() throws Exception {
        mvc.perform(get("/api/profile"))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void existingSessionIsFullyAuthenticated() throws Exception {
        MvcResult login = loginAndRemember();
        HttpSession raw = login.getRequest().getSession(false);
        assertNotNull(raw);
        MockHttpSession session = (MockHttpSession) raw;

        mvc.perform(get("/api/profile").session(session))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("alice"))
            .andExpect(jsonPath("$.rememberMe").value(false));

        mvc.perform(get("/api/strong").session(session))
            .andExpect(status().isOk());
    }

    @Test
    void rememberCookieWorksWithoutOldSession() throws Exception {
        MvcResult login = loginAndRemember();
        Cookie remembered = login.getResponse().getCookie("remember-me");
        assertNotNull(remembered);

        // Do not pass MockHttpSession on this request.
        mvc.perform(get("/api/profile").cookie(remembered))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("alice"))
            .andExpect(jsonPath("$.rememberMe").value(true));
    }

    @Test
    void rememberOnlyIsNotFullyAuthenticated() throws Exception {
        MvcResult login = loginAndRemember();
        Cookie remembered = login.getResponse().getCookie("remember-me");
        assertNotNull(remembered);

        mvc.perform(get("/api/strong").cookie(remembered))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void loginPostWithoutCsrfIsRejected() throws Exception {
        mvc.perform(post("/login")
                .param("username", "alice")
                .param("password", "demo123"))
            .andExpect(status().isForbidden());
    }
}
~~~

Explanation:

- `loginAndRemember()` simulates a real form login with a CSRF token and checkbox.
- `existingSessionIsFullyAuthenticated` passes `MockHttpSession` to the second request: Spring Security restores full authentication.
- `rememberCookieWorksWithoutOldSession` **does not pass a session**, only the remember-me cookie. If the request is allowed, that is auto-login behavior rather than extending S1.
- `rememberOnlyIsNotFullyAuthenticated` demonstrates the trust-level policy.
- The CSRF test disallows POST without a valid token.
- `@WithMockUser` is not used here because it skips testing the remember-me cookie/filter flow.

Run `mvn test`. This is complete sample code for a learning project; **the lesson does not claim Maven was actually executed**. If using Spring Security 7.x or a customized security configuration, check the API, filter chain, and expected statuses against your deployed version.

## 11. Plain Java: simulating the difference in four output lines

If Spring is not installed yet, the Java 17 program below verifies the concept with no framework dependencies. It is not a real session system and is **not safe for production**.

Create file `RememberVsSession.java`:

~~~java
import java.util.HashMap;
import java.util.Map;

public class RememberVsSession {
    private static final Map<String, String> sessions = new HashMap<>();
    private static final Map<String, String> rememberTokens = new HashMap<>();

    static String handle(String sid, String remember) {
        if (sid != null && sessions.containsKey(sid)) {
            return "SESSION:" + sessions.get(sid);
        }
        if (remember != null && rememberTokens.containsKey(remember)) {
            return "REMEMBER:" + rememberTokens.get(remember);
        }
        return "ANONYMOUS";
    }

    public static void main(String[] args) {
        sessions.put("sid1", "alice");
        rememberTokens.put("r1", "alice");

        System.out.println(handle("sid1", "r1"));
        sessions.remove("sid1");
        System.out.println(handle("sid1", "r1"));
        System.out.println(handle(null, "r1"));
        rememberTokens.remove("r1");
        System.out.println(handle(null, "r1"));
    }
}
~~~

Commands:

~~~bash
javac RememberVsSession.java
java RememberVsSession
~~~

Exact stdout:

~~~text
SESSION:alice
REMEMBER:alice
REMEMBER:alice
ANONYMOUS
~~~

Line 1: session exists; line 2: session lost yet remember remains; line 3: no session sent yet remember present; line 4: remember credential also gone so anonymous. **Never use** guessable IDs like `sid1`/`r1` or a hand-rolled `HashMap` for real authentication.

## 12. Persistent tokens in practice: needing a database and revocation lifecycle

To store tokens server-side, use `PersistentTokenRepository`. Illustrative configuration example (**does not run standalone against a demo lacking a datasource**):

~~~java
@Bean
PersistentTokenRepository tokenRepository(DataSource dataSource) {
    JdbcTokenRepositoryImpl repo = new JdbcTokenRepositoryImpl();
    repo.setDataSource(dataSource);
    return repo;
}

@Bean
SecurityFilterChain chain(
        HttpSecurity http,
        UserDetailsService users,
        PersistentTokenRepository repo
) throws Exception {
    http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/profile").authenticated()
            .anyRequest().fullyAuthenticated())
        .formLogin(Customizer.withDefaults())
        .rememberMe(remember -> remember
            .key("use-a-secret-from-secret-manager")
            .userDetailsService(users)
            .tokenRepository(repo)
            .tokenValiditySeconds(7 * 24 * 60 * 60));
    return http.build();
}
~~~

Requires imports `javax.sql.DataSource`, `PersistentTokenRepository`, `JdbcTokenRepositoryImpl`, `HttpSecurity`, `UserDetailsService`, `SecurityFilterChain`, `Bean`, and `Customizer`. To run, add a JDBC driver, `DataSource`, schema migration creating the table, and complete logout/CSRF configuration. **Do not add a second `SecurityFilterChain` bean to the demo** unless you have designed multiple security chains with explicit `securityMatcher`s.

Production needs:

1. Create the schema via Flyway/Liquibase with appropriate indexes/constraints; never auto-create tables per request.
2. Use a shared repository when running multiple instances.
3. Clean up expired tokens; rejected expired tokens are not necessarily deleted from rows automatically.
4. Revoke on password change, account lock, lost-device report, or user request.
5. Write minimal audit logs without logging tokens.
6. Test concurrent requests because rotation can cause an old token to reappear. Never disable replay detection just to "make errors go away."

## 13. Logout does not automatically delete every copy of a remember token

On valid logout, Spring Security can invalidate the session, clear `SecurityContext`, and send cookie deletion headers. The remember-me service also provides a logout handler to clear the cookie in the browser.

**However**:

- With **hash-based** cookies, deleting the cookie on the real device **does not guarantee a stolen copy stops working immediately**. The old signature can remain valid until expiry or until the password/key changes.
- With **persistent tokens**, the application has server-side token state to delete/revoke matching tokens. Coordinate logout with a "logout all devices" policy, not just deleting the browser cookie.
- If the product also has OAuth2 refresh tokens, Identity Provider sessions, or API tokens, treat them as credentials with their own lifecycles.

Never implement a **"Log out all devices"** button merely by calling `deleteCookies("remember-me")` on the current browser. It must revoke credentials where they are verified.

## 14. Cookie security and CSRF

Remember-me cookies live longer than normal sessions and therefore require strict controls:

| Measure | Why |
| --- | --- |
| HTTPS + `Secure` | Restricts transmitting cookies over unencrypted connections |
| `HttpOnly` | Prevents JavaScript from reading the cookie directly; does not eliminate all XSS harm |
| Appropriate `SameSite` | Limits some cross-site auto-sending of cookies; does not replace CSRF tokens |
| Minimal Domain/Path | Do not send cookies where unneeded |
| Reasonable token validity | Reduces the replay window if stolen |
| Secret manager | Avoids hardcoded remember keys, keeps instances consistent |
| Logout + revoke strategy | Stolen credentials are not kept alive indefinitely |
| Full reauth/MFA when needed | Never treat a remember token as sufficient proof for sensitive transactions |

CSRF matters because browsers usually attach cookies automatically. A POST request carrying valid session/remember cookies can still be rejected for lacking a CSRF token, and **that is the right protective behavior**. Disabling CSRF globally just to make POST form login simpler can open vulnerabilities. `SameSite` helps, yet does not fully replace CSRF protection in every design.

`SessionCreationPolicy.STATELESS` does not configure JWTs or eliminate cookies created by other parts of the application. For APIs using bearer tokens, design session/token authentication independently; do not treat Servlet remember-me as an OAuth2 refresh token.

## 15. When to use, when to avoid?

Remember-me is better suited when:

- The product is a form-login website whose UX expects users to return after several days.
- Users explicitly opt in to "remember this device" with clear notice.
- Sensitive endpoints enforce full or step-up authentication policies.
- Cookie controls, expiry, revocation, devices, and account lifecycle are properly managed.

Avoid or restrict when:

- The application handles financial transactions or highly sensitive secrets.
- Kiosk or shared-computer environments.
- No mechanism exists to revoke tokens when a device is stolen.
- Secret keys, HTTPS, CSRF, or anomaly detection are not yet trustworthy.
- The integration is primarily a stateless API/OAuth2, where a dedicated refresh-token mechanism fits better.

Do not set `alwaysRemember(true)` just to cut login steps without understanding the difference in user consent.

## 16. Debugging: "I checked Remember me, yet had to log in again the next day"

Check in order:

1. Did the form actually send the `remember-me` parameter on successful login?
2. Did the response actually issue the remember-me cookie, and did the browser store it?
3. Did the browser send the cookie back with matching domain/path/SameSite/Secure attributes?
4. Did the token expire, get modified, or did the user get disabled or change their password?
5. Is the secret key stable across deployments/instances?
6. Did `UserDetailsService` find the user and return the right password hash/authorities?
7. Is a demo generating a new BCrypt hash on every restart, invalidating old hash-based tokens?
8. If using persistent tokens, is the token store shared across instances? Are there rotation conflicts?
9. Is there a separate `SecurityFilterChain` for that URL without remember-me enabled?
10. Does the endpoint require `fullyAuthenticated()`, intentionally rejecting remember-me?
11. Did logout, password reset, or account lock intentionally delete/revoke the token?
12. Did HTTP 403 come from authorization or CSRF? Do not rush to "fix" it by disabling protection.

When debugging, log only appropriate metadata and request IDs. **Never log full session IDs or remember-me tokens.**

## 17. Comprehension exercises

**Exercise 1.** Session timeout is 20 minutes, remember token is valid 7 days. After 2 hours of inactivity, the user returns with only the remember-me cookie. Can the user be recognized? Is this extending the old session or auto-login?

**Exercise 2.** Why did a user who ticked Remember me and still has a valid session see `rememberMe=false` on the demo endpoint?

**Exercise 3.** Why can `/api/profile` return 200 for a remember token while `/api/strong` requires interactive login?

**Exercise 4.** Alice logs out of her browser, yet an attacker holds a copy of her hash-based remember-me cookie. Why might that copy still work? State how to reduce the risk.

**Exercise 5.** A system needs to revoke tokens per individual device. Which mechanism would you prefer and what management components must be added?

**Exercise 6.** After deploying a new release, remember cookies stop working even though username/password did not change. List things that might have changed in token verification.

**Exercise 7.** Can you simply raise the server session timeout to 30 days and drop CSRF and HTTPS? Explain.

**Exercise 8.** An SPA uses OAuth2 refresh tokens. Can you use `RememberMeAuthenticationFilter` to process OAuth2 refresh tokens directly? Why or why not?

**Exercise 9.** How would you test to prove remember-me works **without reusing the old session**?

### Suggested answers

1. Auto-login can succeed if the token is valid; it is not keeping the original session alive.
2. Because the request is using full authentication from the session; the flag reflects how the current authentication was created, not the checkbox state.
3. `authenticated()` accepts remember-me, whereas `fullyAuthenticated()` does not.
4. A hash-based token copy can be replayed until expiry; mitigate by revoking via password/key change or designing a persistent store with proper revocation.
5. Persistent tokens + device records, revoke API, token rotation, auditing, and a shared store.
6. Stored password hash, secret key, user status, token expiry, algorithm/config, or persistent store.
7. No. Long sessions widen the exposure window; CSRF and HTTPS are independent protective layers.
8. No. Refresh tokens belong to OAuth2 grants/authorization servers and do not share a contract with Servlet remember-me services.
9. In MockMvc, log in with the remember parameter, capture the remember cookie from the response, and send a new request with only `.cookie(remembered)`, omitting `.session(...)`.

## 18. Summary and references

**Extending a session** keeps an existing `HttpSession` alive. **Remember-me** allows re-authenticating with a separate credential after the session disappears. Spring Security expresses this authentication level via `RememberMeAuthenticationToken`, enabling applications to permit routine tasks while requiring `fullyAuthenticated()` or step-up/MFA for sensitive actions.

Remember: **two cookies, two lifecycles, two trust levels, and two revocation strategies**. If you design remember-me as if it were just a long session timeout, you will overlook critical risks around replay, logout, and compromised devices.

Official documentation:

- [Spring Security — Remember-Me Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/rememberme.html)
- [Spring Security 6.5 — Remember-Me](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/rememberme.html)
- [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html)
- [Spring Security — Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Spring Security — Logout](https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html)
- [Spring Session — Spring Security Integration](https://docs.spring.io/spring-session/reference/spring-security.html)
