# Remember-me differs from keeping an HttpSession alive longer

## 1. The problem: “Remembering login” does not mean “keeping the same session”

In a Spring Security Servlet application, users typically expect two different experiences:

- **Current login session:** After entering the correct username/password, the browser sends a session cookie (usually `JSESSIONID`), the server looks up the `HttpSession`, and restores the `SecurityContext`. The session has a timeout, can be invalidated on logout, or can be cleared when the session store no longer holds its data.
- **Remember-me:** The user **explicitly opts in to remember their login**. The application issues a separate *remember-me* cookie with a longer lifetime. Later, when no authenticated session exists, a filter can inspect that cookie and **authenticate automatically** without prompting for the password again for routine actions.

Both approaches can spare the user from typing their password frequently, but they **differ completely in where state is stored, credential lifecycle, recovery mechanism, and revocation capability**.

| Criterion | Extending the HTTP session | Spring Security remember-me |
| --- | --- | --- |
| What the browser sends | Session ID cookie, usually `JSESSIONID` | Separate cookie, typically named `remember-me` by default |
| How does the server verify it? | Looks up the session ID in the session store; retrieves the saved `SecurityContext` | Verifies the remember-me token/cookie via `RememberMeServices` and `UserDetailsService` |
| When the old session has expired | Cannot restore `Authentication` from an expired session ID alone | **Can** automatically re-authenticate if the remember-me token is still valid |
| Application session data | Can keep shopping cart, CSRF, wizard, etc. longer | Does **not** automatically resurrect data from the old `HttpSession` |
| Authentication state | Usually created by a successful interactive form login | Spring Security can create a `RememberMeAuthenticationToken` |
| Trust level for accessing sensitive features | Can be fully authenticated depending on how the session was created | Can be required to log in again via `fullyAuthenticated()` |
| Impact when a token is stolen | Anyone with a live session ID can hijack the session | Anyone with a still-valid remember-me cookie can also attempt automatic login |
| Revocation | Invalidate session / session store, logout policy | Clear cookie and/or revoke server-side token depending on implementation |
| Timeout/cookie expiration | Session timeout and cookie lifetime need to be aligned | `tokenValiditySeconds` and separate token/cookie mechanism |
| Best suited for | Maintaining login state for an ongoing session | Allowing return visits after the previous session has ended |

**Key takeaway:** Remember-me is a **separate credential-based authentication mechanism to recover login across sessions**. It is **not** setting `server.servlet.session.timeout` to a huge value, and it is **not** simply giving `JSESSIONID` a long `Max-Age`.

This lesson focuses on **Spring Boot 3.x, Spring Security 6.x, Java 17+, Spring MVC/Servlet, and form login using HttpSession**. WebFlux/Reactive APIs are configured differently. For stateless token-based APIs, the browser remember-me mechanism does not apply by default.

## 2. How do HttpSession and JSESSIONID actually work?

When an application uses standard form login:

~~~text
Direct login attempt

Browser                         Servlet + Spring Security
   |                                   |
   | POST /login + user/password       |
   |---------------------------------->|
   |     AuthenticationManager verifies|
   |     SessionAuthenticationStrategy |
   |     saves Authentication into     |
   |     SecurityContext/session       |
   |<----------------------------------|
   | Set-Cookie: JSESSIONID=<S1>       |
   |                                   |
   | GET /account/me                   |
   | Cookie: JSESSIONID=<S1>           |
   |---------------------------------->|
   | Server finds session S1, restores |
   | SecurityContext and username      |
   |<----------------------------------|
   | 200 JSON                          |
~~~

The server receives `JSESSIONID=S1`, checks the session store to see whether session S1 currently exists, and checks whether its `SecurityContext` still holds an authenticated identity. The browser does not need to read the cookie with JavaScript if the cookie has `HttpOnly`.

### 2.1. There are three different lifetimes

Do not confuse them:

1. **Session idle timeout**: the server-side session expires after a period of inactivity (for example, 30 minutes). On Servlet, `HttpSession.getMaxInactiveInterval()` and container/session store configuration determine this.
2. **Cookie lifetime**: the browser decides how long to keep the cookie based on `Max-Age`/`Expires` or as a session cookie according to browser policy.
3. **Authentication validity/level within the session**: can be changed by logout, account disabling, security events, session policies, or session store changes.

A short-lived cookie can cause the browser to discard the ID before the server deletes the session. Conversely, if the cookie outlives the session while the **server-side session has already expired**, the cookie only holds an ID that can no longer restore identity.

For example:

~~~properties
# Illustrates a long session configuration; DO NOT use just to mimic remember-me.
server.servlet.session.timeout=30d
server.servlet.session.cookie.max-age=30d
~~~

This configuration can **extend the lifetime window of the same session ID**, but it does not create a new remember-me token, does not provide per-device revocation design, and does not guarantee a session survives a full 30 days if restarts/evictions/session store policies intervene. Session timeout is an **inactivity period**, not necessarily an absolute maximum lifetime.

### 2.2. Risks of “loosening timeout for convenience”

- A leaked session ID remains usable longer: the window of impact for session hijacking increases.
- The server/session store must retain more session records longer, increasing cost and affecting eviction.
- A public browser or shared device can retain access for a long time if the user forgets to log out.
- When the server evicts the session even though the cookie remains, the user is still forced to log in; the UX problem is not actually solved.
- Long-lived sessions can accumulate sensitive data or stale state that is no longer appropriate.
- Increasing cookie lifetime does **not** automatically increase server session lifetime; increasing server timeout does **not** guarantee the browser keeps sending the cookie.

**Do not use `JSESSIONID` as a “remember-me token”.** A session ID is a credential to access state currently stored on the server; remember-me should have its own credential with its own lifecycle, limits, and validation mechanism.

## 3. Remember-me activates when the current session is gone

A typical remember-me flow:

~~~text
Day 1
Browser checks the "Remember me" checkbox
  └─ POST /login + username/password + remember-me=on
       ├─ Interactive authentication succeeds
       ├─ Creates/saves SecurityContext in session S1
       └─ RememberMeServices.loginSuccess
            └─ issues cookie remember-me=R1

Some time later
Session S1 expires / is evicted from the session store
Browser still holds cookie remember-me=R1
  └─ GET /account/me
       ├─ SecurityContext is initially empty (no valid S1)
       ├─ RememberMeAuthenticationFilter
       │     └─ RememberMeServices.autoLogin(R1)
       │           ├─ R1 valid → creates remember-me Authentication
       │           └─ R1 invalid/expired → rejects auto-login, clears cookie if needed
       ├─ AuthenticationManager verifies RememberMeAuthenticationToken
       ├─ SecurityContext is established for the request
       └─ Authorization decides whether the endpoint is accessible
~~~

Key points:

- When **SecurityContext already contains an Authentication**, the remember-me filter normally does not need to auto-login again. Remember-me is a **recovery path**, not a replacement for every request in an active full session.
- If the old session has expired, remember-me can establish an authenticated identity on a new request, and a new session may be created/saved depending on session/context repository configuration. This is **not resurrecting session S1** with its shopping cart and all old attributes.
- A remember-me cookie can remain valid longer than the session idle timeout. However, if the cookie is also lost/expired or the token is revoked, interactive login is required again.
- If the user **does not check remember-me**, form login normally does not issue that long-lived cookie, even when remember-me is enabled in the application.
- If the browser restores session cookies on reopen, the user may appear still logged in because the **session is still alive**, not because of remember-me. To verify remember-me, test a request that sends only the remember-me cookie without the old session cookie.

### 3.1. Spring Security components

| Component | Role |
| --- | --- |
| `UsernamePasswordAuthenticationFilter` | Handles form login; notifies `RememberMeServices` of success/failure via hooks. |
| `RememberMeServices` | Contract for issuing cookies after login, handling failure, and attempting auto-login. |
| `RememberMeAuthenticationFilter` | When a current `Authentication` is missing, checks for an opportunity to authenticate via remember-me cookie. |
| `TokenBasedRememberMeServices` | Signed/hashed cookie token option, requiring no separate DB table. |
| `PersistentTokenBasedRememberMeServices` | Random token option backed by stored records; supports token rotation. |
| `RememberMeAuthenticationToken` | Represents the result of remember-me authentication. |
| `RememberMeAuthenticationProvider` | Provider that verifies remember-me tokens based on the matching key. |
| `UserDetailsService` | Loads user/authorities to restore identity; both standard remember-me implementations require it. |
| `LogoutFilter` / `LogoutHandler` | Clears session state and invokes handlers to clean up the remember-me cookie/token depending on implementation. |
| `SecurityContextRepository` | Manages saving/restoring `SecurityContext`; not a remember-me token store. |

The `RememberMeServices` contract has three core behaviors:

~~~java
Authentication autoLogin(
    HttpServletRequest request,
    HttpServletResponse response
);

void loginSuccess(
    HttpServletRequest request,
    HttpServletResponse response,
    Authentication successfulAuthentication
);

void loginFail(
    HttpServletRequest request,
    HttpServletResponse response
);
~~~

These are **illustrative API signatures**, not a standalone Java file. `autoLogin` can return an `Authentication` or `null`. `loginSuccess` is invoked upon successful interactive authentication. `loginFail` handles a failed direct login attempt; it does not mean every 401 from every endpoint deletes the remember-me token.

## 4. Difference in trust level: remembered vs. fully authenticated

An account authenticated via a remember-me cookie can access normal pages, but the application should require **re-authentication** before sensitive actions (changing password, payments, changing MFA, deleting the account, etc.).

Spring Security can distinguish:

- **Anonymous**: no real logged-in identity.
- **Remember-me authenticated**: has an `Authentication` from remember-me, recognized by `AuthenticationTrustResolver`.
- **Fully authenticated**: passed a full interactive mechanism according to Spring Security's check policy, neither anonymous nor remember-me.

In the DSL:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/account/sensitive").fullyAuthenticated()
    .requestMatchers("/account/**").authenticated()
    .anyRequest().permitAll()
);
~~~

A request carrying only a valid remember-me cookie is usually allowed into `/account/me`, but **not** into `/account/sensitive` until the user logs in directly. With form login, when a remembered user accesses an endpoint requiring full authentication, Spring Security usually triggers the login entry point again (such as redirecting to `/login`), rather than necessarily returning `403`.

**`Authentication.isAuthenticated()==true` does not mean fully authenticated.** A `RememberMeAuthenticationToken` can have its authenticated flag set and carry the user's authorities, yet still be rejected by `fullyAuthenticated()`. Therefore, you should not write a manual check like `if (authentication.isAuthenticated())` and skip re-auth conditions for sensitive actions.

You can check it using:

~~~java
AuthenticationTrustResolver trustResolver =
    new AuthenticationTrustResolverImpl();

boolean remembered = trustResolver.isRememberMe(authentication);
boolean anonymous = trustResolver.isAnonymous(authentication);
boolean fullyAuthenticated = trustResolver.isFullyAuthenticated(authentication);
~~~

The snippet above is **illustrative logic**, assuming the `authentication` variable was safely obtained from `SecurityContext`. `AuthenticationTrustResolver` inspects the authentication type; an application requiring higher assurance (recently completed MFA, action within the last 5 minutes) must enforce its own step-up policy rather than relying solely on `fullyAuthenticated()`.

## 5. Two standard implementations: hash-based and persistent token

Spring Security provides two standard remember-me approaches. Both use a cookie as a credential to re-authenticate; **neither** preserves the old HTTP session.

### 5.1. TokenBasedRememberMeServices: signed/verified cookie

The idea is to issue a cookie containing fields such as username, expiration timestamp, algorithm, and a signature derived from user information plus a **server-side secret key**. According to Spring Security 6's hash-based implementation design, the conceptual structure is:

~~~text
base64(username : expirationTime : algorithmName : signature)

signature = hash(username : expirationTime : password : key)
~~~

This is a **conceptual representation**, not a guide to rolling your own cookie algorithm. Modern 6.x versions use SHA-256 by default to generate the signature; dedicated APIs exist for algorithm migration.

Advantages:

- Does not require a separate remember-me token table.
- Easy to enable in form-login demos and small systems.
- Changing the password or the signing key can invalidate old tokens.

Limitations and risks:

- A stolen cookie can be **replayed from another browser** until it expires or the password/key changes.
- There is no per-device token record to directly revoke one specific token.
- Normal logout clears the cookie in the current browser, but **does not automatically revoke stolen copies** of a hash-based token.
- The key must be sufficiently random, long, and stable across restarts; losing/changing the key invalidates old cookies.
- Never log or expose the key, raw password, or cookie/token to logs or the frontend.

Thus, this is a convenient way to learn remember-me concepts, **not the best default choice for every system that needs multi-device control**.

### 5.2. PersistentTokenBasedRememberMeServices: series + token stored in DB

Instead of relying solely on a stateless signed cookie, persistent tokens use random values in the cookie backed by a server-side record:

~~~text
Cookie: remember-me = encode(series, token)

Database persistent_logins:
  username | series (primary key) | token | last_used
~~~

When receiving the cookie without an authenticated session:

1. Read `series` and `token` from the cookie.
2. Look up the record by `series` in `PersistentTokenRepository`.
3. Compare the cookie token against the server token and check expiration.
4. If valid: issue `RememberMeAuthenticationToken`, generate a **new** token, update the DB, and send a new cookie (keeping the same series).
5. If the cookie is stale or invalid: auto-login fails; depending on the case, the cookie is cancelled. When **the series exists in the DB but the token does not match**, Spring Security treats it as a sign of possible theft, throws `CookieTheftException`, and deletes the user's tokens.

A commonly used schema (adjust to your DB dialect and migration tooling):

~~~sql
CREATE TABLE persistent_logins (
    username VARCHAR(64) NOT NULL,
    series VARCHAR(64) PRIMARY KEY,
    token VARCHAR(64) NOT NULL,
    last_used TIMESTAMP NOT NULL
);
~~~

Compared with hash-based:

| Criterion | Hash-based | Persistent token |
| --- | --- | --- |
| Separate server-side remember-me token storage | Not required | Yes, via `PersistentTokenRepository` |
| Token after auto-login | No equivalent DB series/token rotation mechanism | Token is rotated upon successful cookie authentication |
| Targeted revocation | Limited; usually relies on expiry, password/key change | Can delete token records according to policy/repository |
| When a cookie is stolen | Cookie can be replayed until expiry | Mismatch after rotation can detect reuse signs; does not guarantee detecting every theft |
| Operations | Fewer components | Requires DB/session/token cleanup and concurrency handling |
| Suitability | Demos/simple setups with assessed low risk | Production systems needing clearer token management/revocation |

**Subtlety regarding logout:** In Spring Security's `PersistentTokenBasedRememberMeServices` implementation, when the logout handler receives an appropriate `Authentication`, it can call `removeUserTokens(username)`, meaning it **revokes the user's persistent remember-me tokens**, not just the cookie on the current device. Do not assume it only revokes a single device. If you want a “sign out this device only” feature, you must design a targeted repository and logout flow explicitly. If the logout request lacks Authentication or runs in a flow without the proper handler configured, server-side revocation behavior may differ from expectations; you must test it.

**Concurrency limitation:** With persistent token rotation, two concurrent requests carrying the same old cookie can race: the first request rotates the token, and the second request holding the previous token sees a mismatch and may trigger suspected-theft handling. You must test applications with multiple tabs, parallel AJAX requests, retries, and response handling so users are not logged out unexpectedly. Token rotation adds protection, but it is not absolute proof that a cookie was never leaked.

**Do not forget cleanup:** Expiration during verification logic does not mean the `persistent_logins` table automatically purges all expired rows. You need a safe cleanup policy based on traffic/lifetime and operational constraints.

## 6. How does standard form login integrate remember-me?

The form-login filter has hooks that notify `RememberMeServices` when interactive login succeeds or fails. When the user checks the checkbox, the application can issue a long-lived cookie in addition to the session cookie.

~~~text
Form login:
  username + password + remember-me=on
         |
         v
UsernamePasswordAuthenticationFilter
         |
         +-- Auth FAIL → rememberMeServices.loginFail(...)
         |
         +-- Auth SUCCESS
               |
               +-- Session authentication and SecurityContext
               |
               +-- rememberMeServices.loginSuccess(...)
                     |
                     +-- Remember-me selected? YES
                           → Set-Cookie: remember-me=<signed-token>
                     +-- NO
                           → Do not issue remember-me cookie
~~~

When the user returns without an `Authentication` in `SecurityContext`, `RememberMeAuthenticationFilter` calls `autoLogin` to attempt identity recovery. Afterward, the request still passes through authorization rules.

One important condition: both standard implementations require `UserDetailsService`. If your application authenticates with a specialized provider not backed by `UserDetailsService` (for example, an LDAP integration), you must provide an appropriate service so remember-me can reload the user and authorities, or use another suitable implementation/flow. Do not assume enabling `rememberMe()` is automatically compatible with every login mechanism.

### 6.1. Default separate cookie and checkbox setup

In Spring Security's generated form login, remember-me typically uses the POST parameter `remember-me` (checkbox) and defaults the cookie name to `remember-me`. Parameter name, key, and validity can be customized. If you use a custom HTML form, the checkbox must have the matching `name`:

~~~html
<form method="post" action="/login">
  <input name="username" autocomplete="username">
  <input name="password" type="password" autocomplete="current-password">
  <label>
    <input type="checkbox" name="remember-me">
    Remember me on this device
  </label>
  <!-- When CSRF is enabled, a real form must include a valid CSRF hidden input. -->
  <button type="submit">Sign in</button>
</form>
~~~

This is an **illustrative HTML form**; it does not yet include a CSRF token, so it is insufficient to POST successfully under default CSRF protection. When using Spring Security's generated login page, the framework handles the form and token. With a custom page, you must safely render and submit the CSRF token.

Do not set `alwaysRemember(true)` if the product requires explicit user consent. A default opt-in checkbox/signal is important for security and UX, especially on shared devices.

## 7. Spring Boot 3.x / Java 17+ demo: short session and long remember-me

We will build an application with:

- A short HTTP session timeout, e.g. **30 minutes** idle.
- A remember-me cookie lifetime of **14 days** (illustrative value only).
- `GET /account/me`: allows users logged in directly **or** restored via remember-me.
- `GET /account/sensitive`: requires fully authenticated; a remember-me token alone is not sufficient.
- Default form login `/login` and logout `/logout`.
- Demo user with BCrypt, requiring no external database.

To keep the example easy to run, we use **hash-based remember-me**. Then section 9 explains how to switch to persistent tokens with JDBC, without mixing both implementations in the same configuration.

### 7.1. Dependencies and file structure

In a Spring Boot Gradle project with the Spring Boot plugin and dependency management, you need:

~~~groovy
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

This is an **addition for a Boot project** (not a complete `build.gradle`). The files:

~~~text
src/main/java/com/example/rememberdemo/
  RememberDemoApplication.java
  SecurityConfig.java
  AccountController.java
src/main/resources/
  application.properties
src/test/java/com/example/rememberdemo/
  RememberMeBehaviorTest.java
~~~

### 7.2. RememberDemoApplication.java

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

### 7.3. SecurityConfig.java

~~~java
package com.example.rememberdemo;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            UserDetailsService users,
            @Value("#{systemEnvironment['REMEMBER_ME_KEY'] ?: 'unsafe-local-demo-key-change-me'}")
            String rememberMeKey) throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .requestMatchers("/account/sensitive").fullyAuthenticated()
                .requestMatchers("/account/**").authenticated()
                .anyRequest().authenticated()
            )
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED)
            )
            .formLogin(Customizer.withDefaults())
            .rememberMe(remember -> remember
                .key(rememberMeKey)
                .userDetailsService(users)
                .rememberMeParameter("remember-me")
                .tokenValiditySeconds(14 * 24 * 60 * 60)
            )
            .logout(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("student")
                .password(encoder.encode("demo-pass"))
                .roles("USER")
                .build()
        );
    }
}
~~~

**Note about the demo key:** `unsafe-local-demo-key-change-me` in the fallback is only for running the program on a developer machine. In production, you **must** supply `REMEMBER_ME_KEY` as a sufficiently strong random secret, stable across restarts and consistent across nodes. Never store real keys in Git or allow guessable fallbacks in production. When the key changes, hash-based remember-me cookies signed with the old key become invalid.

The Spring Expression `@Value("#{systemEnvironment['REMEMBER_ME_KEY'] ?: 'unsafe-local-demo-key-change-me'}")` injects the environment variable before configuring `rememberMe`. If your organization uses a secret manager, swap the injection mechanism while keeping the semantics of a “server-only, stable secret”.

**Why not extend the session to 14 days?** We keep `SessionCreationPolicy.IF_REQUIRED` and a separate session timeout. The remember-me token has a different lifetime from the session. The cookie is issued only when login succeeds and the user selects the corresponding option.

**Why `fullyAuthenticated()`?** `/account/sensitive` does not allow a remember-me token alone to qualify. This rule suits high-risk operations, though it does not replace MFA or password re-confirmation required by product policy.

### 7.4. AccountController.java

~~~java
package com.example.rememberdemo;

import java.util.Map;

import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.annotation.CurrentSecurityContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AccountController {
    private final AuthenticationTrustResolver trust =
        new AuthenticationTrustResolverImpl();

    @GetMapping("/")
    public Map<String, String> home() {
        return Map.of("message", "public");
    }

    @GetMapping("/account/me")
    public Map<String, Object> me(
            @CurrentSecurityContext(expression = "authentication")
            Authentication authentication) {
        return Map.of(
            "username", authentication.getName(),
            "remembered", trust.isRememberMe(authentication),
            "fullyAuthenticated", trust.isFullyAuthenticated(authentication)
        );
    }

    @GetMapping("/account/sensitive")
    public Map<String, String> sensitive(
            @CurrentSecurityContext(expression = "authentication")
            Authentication authentication) {
        return Map.of("sensitiveFor", authentication.getName());
    }
}
~~~

The controller reads the `Authentication` verified by Spring Security. It does **not** manually compare the remember-me cookie against `JSESSIONID`, does not decode tokens in JavaScript, and does not grant sensitive permissions on its own. The `fullyAuthenticated()` rule is placed in the filter chain to protect the endpoint before the controller runs.

With a normal interactive login, the `GET /account/me` response may look like:

~~~json
{
  "username": "student",
  "remembered": false,
  "fullyAuthenticated": true
}
~~~

When **only** the remember-me cookie restores identity:

~~~json
{
  "username": "student",
  "remembered": true,
  "fullyAuthenticated": false
}
~~~

These are **expected outputs according to the demo flow**, not observed output captured from a live run.

### 7.5. application.properties

~~~properties
server.servlet.session.timeout=30m
server.servlet.session.cookie.http-only=true

# Local HTTP is for demo only. Production HTTPS must configure Secure.
# Do not deliberately extend JSESSIONID max-age to 14 days.
~~~

When deploying to production HTTPS:

~~~properties
server.servlet.session.cookie.secure=true
server.servlet.session.cookie.same-site=lax
~~~

The `Secure` attribute ensures the session cookie is only sent over HTTPS (browsers may treat `localhost` differently). `SameSite=Lax` is an example often suitable for same-site web apps, and does not replace CSRF tokens. **These session cookie settings do not automatically ensure every attribute of the remember-me cookie is identical.** Inspect both cookies in DevTools and configure the remember-me cookie/response according to your application policy.

### 7.6. Running with Gradle and using the form

~~~bash
./gradlew bootRun
~~~

On Windows:

~~~powershell
.\gradlew.bat bootRun
~~~

In a browser, visit `http://localhost:8080/account/me` while unauthenticated; the page may redirect to `/login`. Log in with demo credentials `student` / `demo-pass`.

- **Without checking Remember me:** you get a login session, but no long-lived remember-me cookie is issued. When the session is lost, the user must log in again.
- **With Remember me checked:** form login still creates a normal session while also issuing a remember-me cookie. When the session is lost but the remember-me token remains, a new request can be authenticated automatically.
- **Try `/account/sensitive` when only remember-me remains:** the application requires interactive login instead of treating the remember-me token as fully authenticated.

Do not use demo credentials outside localhost. Real remember-me tokens are secrets; do not print their values in logs/screenshots/tickets.

## 8. MockMvc tests verifying two separate lifecycles

Tests should intentionally issue requests **without attaching the old session** while keeping the remember-me cookie. If every test sends `JSESSIONID` back, you are only testing the session and have not proven that remember-me works.

Create `src/test/java/com/example/rememberdemo/RememberMeBehaviorTest.java`:

~~~java
package com.example.rememberdemo;

import jakarta.servlet.http.Cookie;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class RememberMeBehaviorTest {

    @Autowired
    private MockMvc mvc;

    private MvcResult signIn(boolean remember) throws Exception {
        MockHttpSession existing = new MockHttpSession();

        var request = post("/login")
            .session(existing)
            .with(csrf())
            .param("username", "student")
            .param("password", "demo-pass");

        if (remember) {
            request.param("remember-me", "on");
        }

        return mvc.perform(request)
            .andExpect(status().is3xxRedirection())
            .andReturn();
    }

    private Cookie rememberCookie() throws Exception {
        Cookie cookie = signIn(true).getResponse().getCookie("remember-me");
        assertNotNull(cookie, "Checking remember-me must issue a cookie");
        return cookie;
    }

    @Test
    void ordinaryLoginDoesNotIssueLongLivedRememberCookie() throws Exception {
        MvcResult result = signIn(false);
        assertNull(result.getResponse().getCookie("remember-me"));
    }

    @Test
    void rememberMeWorksWithoutSendingOldHttpSession() throws Exception {
        Cookie cookie = rememberCookie();

        // Do not attach JSESSIONID or MockHttpSession from login.
        mvc.perform(get("/account/me").cookie(cookie))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("student"))
            .andExpect(jsonPath("$.remembered").value(true))
            .andExpect(jsonPath("$.fullyAuthenticated").value(false));
    }

    @Test
    void rememberMeAloneDoesNotSatisfySensitiveEndpoint() throws Exception {
        Cookie cookie = rememberCookie();

        mvc.perform(get("/account/sensitive").cookie(cookie))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void fullFormSessionCanEnterSensitiveEndpoint() throws Exception {
        MockHttpSession session = new MockHttpSession();

        mvc.perform(post("/login")
                .session(session)
                .with(csrf())
                .param("username", "student")
                .param("password", "demo-pass"))
            .andExpect(status().is3xxRedirection());

        mvc.perform(get("/account/sensitive").session(session))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.sensitiveFor").value("student"));

        mvc.perform(get("/account/me").session(session))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.remembered").value(false))
            .andExpect(jsonPath("$.fullyAuthenticated").value(true));
    }

    @Test
    void invalidRememberCookieDoesNotAuthenticate() throws Exception {
        Cookie tampered = new Cookie("remember-me", "invalid-token");

        mvc.perform(get("/account/me").cookie(tampered))
            .andExpect(status().is3xxRedirection());
    }
}
~~~

**Why is the second test the most important?** It logs in with the checkbox checked, extracts the remember-me cookie, and calls `/account/me` **without sending the old session**. If the user is still recognized and `remembered=true`, we prove remember-me is a separate authentication mechanism, not merely extending `JSESSIONID`.

The third test checks *step-up*: the user is “remembered” yet must log in interactively for sensitive resources. The fourth test shows that a form-login session indeed satisfies `fullyAuthenticated()`.

In the test suite, `MockHttpSession` is used to simulate sessions. It does not reproduce the full 14-day duration or real browser cookie storage behavior. To verify expiration, restarts, cookie attributes, and clustering, add integration tests with an embedded container/browser and a controllable clock.

Run with Gradle:

~~~bash
./gradlew test --tests com.example.rememberdemo.RememberMeBehaviorTest
~~~

Windows:

~~~powershell
.\gradlew.bat test --tests com.example.rememberdemo.RememberMeBehaviorTest
~~~

If the project, versions, and dependencies are correct and assertions pass, Gradle typically reports `BUILD SUCCESSFUL`. That is the **expected outcome**, not stdout confirmed from running it here. The Java snippets require Spring Boot/Security on the classpath and therefore cannot be compiled standalone with `javac` lacking dependencies.

### 8.1. Additional checks for real environments

You should also test these scenarios:

| Case | How to reproduce | Expected result |
| --- | --- | --- |
| RM-01 | Log in without checking the checkbox | No new remember-me cookie; only a regular session remains. |
| RM-02 | Log in with the checkbox checked | Remember-me cookie is issued with the policy lifetime. |
| RM-03 | Clear/expire session while keeping remember cookie | User is recognized as **remembered**, not fully authenticated. |
| RM-04 | Lose both session and remember cookie | Request to a protected endpoint requires logging in again. |
| RM-05 | Forged or tampered cookie | Auto-login fails, no authorization granted. |
| RM-06 | Expired remember cookie | No automatic re-login. |
| RM-07 | User changes password with hash-based | Old cookie becomes invalid if the hash structure still depends on that password. |
| RM-08 | Remember-only calls a fully authenticated endpoint | Interactive login/step-up is required. |
| RM-09 | Normal logout | Session is invalidated and current cookie is cleared; verify separate revocation policy. |
| RM-10 | Persistent token revoked in DB | Even if the browser retains the cookie, the token is no longer accepted. |
| RM-11 | Concurrent requests sharing an old persistent cookie | Does not cause unexpected logouts/false “theft” beyond operational handling capacity. |
| RM-12 | Browser on another device | Identity is not recognized without the token; if a token is stolen, evaluate detection and revocation. |

## 9. Switching to persistent tokens with JDBC when better revocation is needed

This section is an **alternative option** to the hash-based configuration in section 7, not a configuration to place simultaneously on the same chain.

Requirements:

- `spring-boot-starter-jdbc` and an appropriate JDBC driver.
- A declared, accessible `DataSource`.
- The `persistent_logins` table created by migrations matching the schema.
- A stable secret key.
- Clear `UserDetailsService` and session/CSRF/cookie policies.

Repository bean snippet (add to the corresponding `@Configuration` class):

~~~java
@Bean
PersistentTokenRepository persistentTokenRepository(DataSource dataSource) {
    JdbcTokenRepositoryImpl repository = new JdbcTokenRepositoryImpl();
    repository.setDataSource(dataSource);
    return repository;
}
~~~

Required imports:

~~~java
import javax.sql.DataSource;
import org.springframework.security.web.authentication.rememberme.PersistentTokenRepository;
import org.springframework.security.web.authentication.rememberme.JdbcTokenRepositoryImpl;
~~~

Then, **replace** the `rememberMe(...)` section in the `SecurityFilterChain` bean with:

~~~java
.rememberMe(remember -> remember
    .key(rememberMeKey)
    .userDetailsService(users)
    .tokenRepository(persistentTokenRepository)
    .rememberMeParameter("remember-me")
    .tokenValiditySeconds(14 * 24 * 60 * 60)
)
~~~

The `persistentTokenRepository` variable above is the `PersistentTokenRepository` dependency injected into the chain bean method; **this snippet is a configuration fragment**, not a standalone Java file. When `tokenRepository(...)` is provided, the remember-me configuration uses the appropriate persistent-token service instead of the hash-based default.

Do not use `InMemoryTokenRepositoryImpl` in production: it loses data on restart, is not shared across nodes, and is suitable only for tests/demos. Use `JdbcTokenRepositoryImpl` or an appropriately designed production repository.

### 9.1. Revocation and “log out all devices” must be defined

With persistent tokens:

- Each token has its own record, so the server can delete records to invalidate it.
- The standard Spring Security implementation can delete **all tokens for a username** when the logout handler is called with an appropriate `Authentication`.
- Revoking **a single device** requires device metadata and a repository/flow designed to support it; the default schema only has `username`, `series`, `token`, `last_used`, and is not a device-management system out of the box.
- Revoking remember-me tokens **does not automatically invalidate** all logged-in HTTP sessions across all browsers. If “Logout everywhere” is required, coordinate the session registry/store, access tokens, remember-me tokens, and other credentials according to your application's model.

**Race risk:** If two requests are sent with the same persistent cookie before the browser receives the new cookie, token rotation can cause the second request to hit a series/token mismatch and trigger suspected-theft logic. Test with retries, multiple tabs, and network delays, and prefer managing sessions after auto-login to reduce repeated validation of an old cookie.

### 9.2. Password reset and key rotation

Hash-based remember-me incorporates password/key into signature inputs, so changing the password/key invalidates old cookies. With persistent-token remember-me, separate stored records **are not necessarily deleted simply because the password hash changed**; after a password reset, role change, or user suspension, the application should **explicitly revoke persistent tokens**. Similarly, secret key rotation policies must account for stored tokens and active sessions.

Do not allow a disabled user to keep being identified because remember-me tokens were not revoked. Reload user/status/authorities properly, and test account lockout cases.

## 10. Security attributes for remember-me cookies differ from session cookie config

The system may receive two distinct cookies:

~~~http
Cookie: JSESSIONID=<short-session-id>; remember-me=<long-lived-token>
~~~

Each cookie is an independent **secret**. Attributes to verify:

| Attribute | For session cookie | For remember-me cookie |
| --- | --- | --- |
| `HttpOnly` | Should be enabled so JS cannot read the session ID | Should be enabled when JS does not need to read the token directly |
| `Secure` | Mandatory on production HTTPS | Must also ensure the remember-me cookie travels only over HTTPS |
| `SameSite` | Choose based on site topology and CSRF policy | Choose to fit login context; do not open cross-site unnecessarily |
| `Domain`, `Path` | Send the ID only to required host/path | Restrict the scope of the remember-me cookie |
| `Max-Age`/`Expires` | May be a session cookie or persistent cookie per policy | Usually a persistent cookie using `tokenValiditySeconds` |
| Rotation/revocation | Session ID rotation/session invalidation | Separate token; hash-based vs. DB persistent behave differently |
| Access via JS | No need to read the session ID | No need to read the remember-me token to log in |

Configuration:

~~~properties
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.secure=true
server.servlet.session.cookie.same-site=lax
~~~

sets the policy for the **session cookie** in Spring Boot, but **do not assume it also fully configures the remember-me cookie**. The remember-me cookie is managed by `RememberMeServices`. Inspect the actual `Set-Cookie` response header and use version-appropriate APIs/configuration for `Secure`, `HttpOnly`, `SameSite`, and HTTPS reverse proxies.

Things to evaluate:

1. **End-to-end HTTPS:** never issue remember-me tokens over plain HTTP in real environments. Reverse proxies must forward accurate scheme info without weakening cookie security.
2. **Cross-site frontends:** `SameSite=None; Secure` may be required for cross-site cookies, though browsers may block third-party cookies. If feasible, keep frontend and API on the same site/origin to reduce complexity.
3. **CSRF:** Remember-me cookies are sent automatically by the browser, so state-changing POST/PUT/DELETE operations still carry CSRF risk if the application allows authentication via them. **Do not disable CSRF just because “only remember-me is used”.**
4. **XSS:** `HttpOnly` reduces the risk of JS extracting the token, but XSS can still execute actions under the user's identity inside the browser. Dedicated XSS protections are required.
5. **Shared devices:** the remember-me checkbox must be a deliberate choice and should not be auto-enabled on kiosk/public devices.
6. **Timeouts:** remember-me tokens lasting longer than session timeouts are intentional, but that does not mean tokens should last forever or bypass server-side expiration.
7. **Browser session restore:** closing and reopening a browser is not a reliable test for “session expired”: browsers can restore session cookies. Check specific cookies or use tests that explicitly omit the session ID.
8. **Caching sensitive responses:** protecting sensitive data in browser/proxy caches does not depend solely on cookies.

## 11. Logout: ending the session and ending remember-me are two different things

A logout may involve multiple steps:

~~~text
POST /logout + valid CSRF token
       |
       ├─ SecurityContextLogoutHandler
       │    ├─ clear SecurityContext
       │    └─ invalidate HttpSession (per configuration)
       |
       ├─ RememberMeServices logout handler
       │    ├─ delete browser-side remember-me cookie
       │    └─ persistent implementation may delete DB tokens
       |
       └─ LogoutSuccessHandler
            └─ redirect /login?logout or appropriate response
~~~

Limitations:

- Destroying `JSESSIONID` does **not** automatically invalidate the remember-me token. If the remember-me cookie survives, the browser can automatically log in again on the next request.
- Clearing the cookie via `Set-Cookie: remember-me=; Max-Age=0` in the current browser does not revoke a stolen copy of the token in the hash-based case.
- With the persistent service, server-side logout logic may delete remember-me tokens for **all remembered sessions sharing the same username** if an Authentication is passed to the handler; do not assume per-device revocation by default.
- If a system uses a custom JSON login, filters that skip calling `RememberMeServices.loginSuccess(...)`, and logout handlers that are not properly integrated, cookies may not be issued or cleared as expected.
- After logout, browsers may still hold cached data or cookies on other domains; design an end-to-end logout contract.

**Test logout using a standalone remember-me cookie** after logout/session expiry, and clearly distinguish hash-based from persistent-token behavior. You cannot conclude “logout succeeded everywhere” from an HTTP 302 or 204 alone.

### 11.1. “Not using remember-me” and “clearing remember-me” also differ

When the checkbox is **unchecked** during a new login, the application has not necessarily revoked persistent tokens issued during previous logins. A separate “forget this device” action or an active revocation policy is needed if required by the product. With hash-based tokens, if the browser still holds a valid old cookie, it can still auto-login once the new session expires.

Product requirements should state explicitly: does unchecking the box merely **avoid issuing a new token**, or also **revoke previously issued tokens**? Never assume the two behaviors are equivalent.

## 12. When to choose which approach?

| Product scenario | Better-fitting design | Reason |
| --- | --- | --- |
| Users only need to stay logged in during one short work session | HTTP session with appropriate idle timeout | Fewer long-lived credentials, clearer logout. |
| “Remember me for 14 days” on a personal device | Opt-in remember-me cookie with reasonable limits | Allows re-authentication after the old session ends. |
| Managing/revoking remembered devices | Persistent token + record management, device metadata if needed | Provides a server-side foundation for revocation. |
| Immediately logging out all devices | Token revocation policy, session invalidation, session registry/store | Cannot rely solely on clearing one cookie in the current browser. |
| Accessing sensitive transactions | `fullyAuthenticated()`, plus step-up/MFA based on risk level | Remember-me should not be the sole assurance. |
| Machine-to-machine APIs | Dedicated API tokens/credentials with rotation, scopes, audience, revocation | Browser remember-me is not an appropriate session/token model. |
| High-risk products or public devices | Consider not offering remember-me | Avoids leaving long-lived credentials on devices. |
| Simply preventing timeout mid-task | Tune idle timeout reasonably and add draft-saving UX | Long-lived remember-me is not necessarily needed. |

**There is no “one-size-fits-all” timeout number.** Choices must reflect data classification, risk level, user behavior, revocation capability, device policy, and compliance requirements. The 30-minute/14-day values in the demo exist only to illustrate two distinct lifecycles.

## 13. Common misconceptions and pitfalls

### Pitfall 1 — Setting server.servlet.session.timeout=30d and calling it “Remember me”

This only keeps the session alive longer without adding remember-me token/validation logic. If the session store loses data, the browser loses the cookie, or logout occurs, automatic recovery does not happen.

### Pitfall 2 — Increasing cookie Max-Age while forgetting server timeout

A `JSESSIONID` cookie lasting 30 days does not mean the server-side session lasts 30 days. The cookie may point to an invalidated/evicted ID, causing “the browser still has the cookie yet forces login”.

### Pitfall 3 — User checks the checkbox yet no cookie is issued

Check whether the form has the exact field named `remember-me`; whether login actually succeeded; whether `RememberMeServices` is wired into the authentication flow; and whether the browser blocked `Set-Cookie` due to `Secure`/`SameSite`/domain/path.

### Pitfall 4 — Using custom JSON login without notifying RememberMeServices

Calling `AuthenticationManager.authenticate(...)` then `saveContext(...)` can establish a successful session login, but **does not guarantee issuing a remember-me cookie**. Custom flows need to invoke `loginSuccess` / `loginFail` under the proper conditions and integrate session authentication strategy, CSRF, and logout. Avoid copying the Base64 token algorithm manually into a controller.

### Pitfall 5 — Remember-me cookie is present yet requests still redirect to login

Check: expired/invalid token, nonexistent or locked user, key changed across deployments, persistent token record revoked, request omitting the cookie due to scope/policy, filter chain lacking `rememberMe()`, or endpoint requiring `fullyAuthenticated()`.

### Pitfall 6 — Treating “Remembered” as fully authenticated

Incorrect. Spring Security distinguishes trust levels. Sensitive actions should require interactive re-authentication, and even MFA/step-up; do not treat `Authentication.isAuthenticated()` as proof of recent re-auth.

### Pitfall 7 — Logout clears the session yet immediately logs back in

The remember-me cookie may not have been cleared, or the service/logout handler is misconfigured. Inspect the `Set-Cookie` response clearing the remember-me cookie, persistent token state, and a subsequent request without a session.

### Pitfall 8 — Thinking deleting a cookie revokes a stolen hash-based token

If someone else already copied the cookie, deleting it in the current browser does not affect the copy. With hash-based tokens, changing password/key or waiting for expiration invalidates the copy under that mechanism; for targeted revocation, consider persistent tokens.

### Pitfall 9 — Changing the remember-me key on every server restart

Tokens signed with the old key become invalid, causing users to unexpectedly re-login. All nodes serving the same application must share a consistent key managed via a secret store with a rotation plan; do not hardcode production secrets in source code.

### Pitfall 10 — Persistent tokens lost on restart

Using `InMemoryTokenRepositoryImpl` in production causes tokens not to survive restarts. Use a JDBC/DB repository with durable storage and proper schema/migrations.

### Pitfall 11 — DB tokens exist yet expired data is never cleaned up

Rejecting stale tokens does not guarantee removing rows from the table automatically. Run a conditional cleanup job and avoid deleting still-valid tokens by mistake.

### Pitfall 12 — Multiple tabs using the same persistent token concurrently

Two simultaneous requests can cause a token mismatch after rotation, even triggering suspected cookie theft handling. Test concurrency, browser retries, and choose appropriate UX/telemetry policies; do not simply remove mismatch checks to “silence errors”.

### Pitfall 13 — Confusing remember-me cookies with OAuth refresh tokens

Remember-me is generally meant for websites/session-backed form login. OAuth2 refresh tokens have their own protocol, audience, scopes, rotation, and revocation. Do not put a remember-me token into an SPA/mobile JSON access token as a “JWT replacement”.

### Pitfall 14 — Disabling CSRF because the user does not enter a password

Browsers automatically attach remember-me cookies within scope. It remains a credential susceptible to CSRF when the backend accepts state-changing requests. Keep appropriate CSRF protection, verify SameSite and Origin, and do not treat CORS as a CSRF defense.

### Pitfall 15 — Using remember-me tokens as audit identifier logs

Never log raw remember-me cookies, `JSESSIONID`, or database tokens. Use non-sensitive correlation IDs; if device tracking is needed, design a separate audit identifier. Long-lived tokens are highly sensitive.

## 14. Debugging workflow when users get “forgotten”

Go from easiest-to-verify causes to harder ones:

1. **Is there a valid HTTP session?** Check whether the request sends `JSESSIONID`, the server session store still has the record, and `SecurityContext` was saved.
2. **Did the user opt in to remember-me?** Check the login form parameter `remember-me` and whether the response issued a remember-me cookie.
3. **Did the browser store/send the remember-me cookie?** Inspect `Set-Cookie` and `Cookie` in DevTools; do not copy values into logs.
4. **Is the cookie still within its validity window?** Check `Max-Age`/token expiry and clock alignment across servers/nodes.
5. **Did the key change?** With hash-based tokens, key/password changes invalidate tokens.
6. **Does the DB token still exist?** With persistent tokens, look up the repository by series using an internal secret-redacted tool; check token rotation/revocation/cleanup.
7. **Are the chain and filters correct?** Is `RememberMeAuthenticationFilter` present in the endpoint's chain? Did another filter short-circuit earlier?
8. **Does the endpoint require `fullyAuthenticated` or just `authenticated`?** Redirecting to login on a sensitive endpoint may actually be the intended protection policy.
9. **Was there a logout/reset/account lock event?** An action may have actively revoked tokens or sessions.
10. **Is there a race between concurrent requests?** Persistent-token rotation surfaces easily in clients sending multiple concurrent requests holding an old cookie.
11. **Is a browser policy blocking the cookie?** Cross-origin fetch missing `credentials`, SameSite, Secure, and third-party cookie restrictions are common culprits.
12. **Is the session store/cluster inconsistent?** One node not seeing another node's session/token can make logins appear to fail randomly.

Diagnostic table:

| Observation | Likely cause | Verification step |
| --- | --- | --- |
| Browser holds JSESSIONID yet GET still returns 302 | Server session expired or context missing | Session store/timeout/cookie scope. |
| Remember-me cookie present, normal GET 200 but sensitive GET 302 | `fullyAuthenticated()` is protecting properly | Check trust level, require re-auth. |
| No remember-me cookie seen after login | No opt-in, form param mismatch, blocked cookie | POST params and Set-Cookie. |
| Remember-me invalidates after deploy | Hash key/password changed or DB repository lost | Secret consistency and DB persistence. |
| Logout followed by GET still returns 200 | Remember-me cookie not cleared or token not revoked | Logout handlers, cookies, and token repository. |
| Users logged out en masse after multiple requests | Persistent token rotation conflict or revoke policy | Observe token mismatches and concurrency. |
| Another browser gains access using the same remember-me cookie | Credential was copied and remains valid | Incident response, revoke/rotate/change password. |
| Cookie sent yet Spring does not recognize identity | Wrong chain/filter/expired token/user status | Redacted Security DEBUG, provider, and token store. |

## 15. QA checklist before enabling Remember me in production

| Question | Acceptance criteria |
| --- | --- |
| Are the two lifetimes separated? | `HttpSession` idle timeout and remember-me token validity are declared and tested separately. |
| Does the user have opt-in control? | Clear checkbox or equivalent action; never auto-remember on public devices. |
| Is the cookie protected? | HTTPS, Secure, HttpOnly, SameSite, Domain/Path, CORS/CSRF verified in practice. |
| Is remember-me withheld on failed login? | Test that invalid credentials do not create a usable remember-me cookie. |
| Does remember-me still work when session expires? | Test request **without sending the old session**, sending only the remember-me cookie. |
| Are remember-me privileges restricted? | Sensitive endpoints use `fullyAuthenticated()`/appropriate step-up. |
| Is there a revocation path? | Hash-based: expiry/password/key; persistent: DB revocation and clear logout policy. |
| Are key/DB persistent across restarts? | Key from secret manager, shared across nodes; durable repository if persistent. |
| Does logout prevent automatic re-login? | Test actual cookie clearing and revocation, not just HTTP 302. |
| Is logout-all-devices required? | Policy coordinating session invalidation, remember-me, and other tokens is in place. |
| Are there concurrency risks? | Persistent token rotation is tested with multiple tabs/network retries. |
| Are secrets protected from leaks? | No logging of raw cookies/sessions/tokens, passwords, or Authentication headers. |
| Is authentication backed by valid user status? | `UserDetailsService` checks current user and updated authorities. |
| Is there monitoring and cleanup? | Alerting on anomalies, cleanup of expired tokens, bounded credential lifetime. |

## 16. Summary

**Extending an HTTP session** keeps the same `JSESSIONID → HttpSession → SecurityContext` mechanism alive longer. It provides no automatic re-login once the session is gone and increases the exposure window if a session ID is compromised.

**Remember-me** issues a **separate authentication cookie** during a user-consented login. When the old session disappears, `RememberMeAuthenticationFilter` and `RememberMeServices` can re-authenticate and create a `RememberMeAuthenticationToken`. This does not resurrect all old session data, and **its trust level is lower than interactive login** for endpoints requiring `fullyAuthenticated()`.

- Hash-based remember-me is simple but limited in per-token revocation; password/key changes and expiration are common invalidation mechanisms.
- Persistent tokens store series/tokens server-side, rotate tokens on auto-login, and support revocation, at the cost of DB operations and concurrency handling.
- Logout and “forget device” require explicit policies; clearing the session cookie does not clear the remember-me credential.
- `Secure`/`HttpOnly`/`SameSite` cookies, HTTPS, CSRF, XSS protection, session timeouts, and re-auth checks remain essential.

When designing a **“Remember me”** UX, answer two independent questions: **“How long is the current session kept?”** and **“Once the session ends, which long-lived credential may the browser use to re-prove identity, for how long, and how can it be revoked?”**. That is the fundamental difference between Remember-me and a long-lived HttpSession.

### References

- Spring Security 6.5 Reference — Remember-Me Authentication: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/rememberme.html
- Spring Security 6.5 Reference — Authentication Persistence and Session Management: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html
- Spring Security 6.5 Reference — Logout: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/logout.html
- Spring Security 6.5 Reference — CSRF: https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html
- Spring Security 6.5 Reference — Database Schema (persistent_logins): https://docs.spring.io/spring-security/reference/6.5/servlet/appendix/database-schema.html
- Spring Security 6.5 API — RememberMeServices: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/RememberMeServices.html
- Spring Security 6.5 API — PersistentTokenBasedRememberMeServices: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/rememberme/PersistentTokenBasedRememberMeServices.html
- OWASP — Session Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
- OWASP — Authentication Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
