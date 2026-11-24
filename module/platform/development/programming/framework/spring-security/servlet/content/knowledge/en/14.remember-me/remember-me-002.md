# RememberMeAuthenticationFilter, RememberMeServices, and AuthenticationProvider in Spring Security Servlet

> **Scope:** Remember-me in Spring Security Servlet, with Java 17+, Spring Boot 3.x, and Spring Security 6.x. Focus: the filter deciding when to restore identity, services validating cookies, the provider verifying internal remember-me tokens, along with their lifecycle and risks.

## 1. What Is Remember-me Really?

Users generally want to avoid re-entering their password every time an HTTP session expires or after closing and reopening the browser. **Remember-me** lets the application issue a cookie that can be verified on later requests to restore identity when no authentication remains in the session/context. This is a mechanism for **re-authenticating with a remembered credential**, not simply extending the `JSESSIONID` lifetime.

To avoid confusion, separate four things:

- **Primary login**: the user provides a password or stronger credentials, `AuthenticationManager`/provider verifies them, and creates an `Authentication`.
- **HTTP session**: can store the `SecurityContext` of the primary authentication and usually has a shorter lifetime than the remember-me cookie.
- **Remember-me cookie**: a credential sent back so the server can restore authentication when the context is empty; it must be treated as a **bearer secret**.
- **Authorization**: decides what the request is permitted to do. A `RememberMeAuthenticationToken` is marked authenticated but is normally **not fully authenticated**.

The three names in the title correspond to three independent roles:

1. **`RememberMeAuthenticationFilter`**: detects requests that have no authentication in the security context yet, and attempts to use remember-me.
2. **`RememberMeServices`**: manages issuing the cookie on login success, reading/validating the cookie for auto-login, and handling login failure; different implementations use signatures or a server-side token repository.
3. **`RememberMeAuthenticationProvider`**: verifies that the `RememberMeAuthenticationToken` created by services belongs to the matching shared-key configuration before `AuthenticationManager` accepts it.

**Remember:** the filter does not verify cookie signatures itself; the provider does not read browser cookies directly; services do not grant endpoint access on their own. They coordinate with `SecurityContext`, `AuthenticationManager`, and authorization.

## 2. Two Phases of Remember-me: Issuing the Cookie and Auto-Login

A remember-me implementation must perform two distinct jobs.

### Phase A — Issuing the Cookie After Password Login

```text
Browser POST /login
  username + password + CSRF + remember-me checkbox
          |
          v
UsernamePasswordAuthenticationFilter
          |
          v
AuthenticationManager -> DaoAuthenticationProvider
          |
       credential verification succeeds
          |
          +--> SessionAuthenticationStrategy / SecurityContext
          |
          +--> RememberMeServices.loginSuccess(...)
                  |
              cookie created if policy/checkbox allows
                  |
              Set-Cookie: remember-me=...
          |
          v
AuthenticationSuccessHandler -> redirect
```

When the password is wrong, the login filter handles the failure branch and may call `RememberMeServices.loginFail(...)` before `AuthenticationFailureHandler`. **Not every successful login issues a cookie**: by default the checkbox must be selected, unless the application intentionally uses `alwaysRemember(true)`.

### Phase B — Restoring Identity When Session Authentication Is Lost

```text
Browser GET /profile + remember-me cookie
              |
              v
FilterChainProxy selects SecurityFilterChain
              |
              v
RememberMeAuthenticationFilter
   SecurityContext has no Authentication yet
              |
              v
RememberMeServices.autoLogin(request,response)
   |         |
   |         +--> cookie invalid/expired/absent -> null or error
   |
   +--> valid cookie -> creates RememberMeAuthenticationToken
              |
              v
AuthenticationManager.authenticate(...)
              |
              v
RememberMeAuthenticationProvider verifies key hash
              |
              v
SecurityContext holds remember-me Authentication
              |
              v
Authorization: authenticated() / fullyAuthenticated()
              |
              v
MVC controller, if policy permits
```

This is a functional diagram, not an immutable filter order across all versions. If a request already has an `Authentication` in the security context (e.g., from a session login), the remember-me filter typically does not call `autoLogin`. Seeing a browser remain logged in after refresh therefore **does not prove** remember-me was exercised.

### Three Practical Scenarios

| Scenario | Mechanism that can decide authentication |
| --- | --- |
| POST /login with correct password | Form login filter and password provider |
| GET /profile with a session containing a valid Authentication | SecurityContext is restored; remember-me may not need to run |
| GET /profile without session auth but with a valid remember-me cookie | RememberMeAuthenticationFilter → RememberMeServices → RememberMeAuthenticationProvider |

Test design must **separate these scenarios**, especially when proving that the remember-me cookie actually works.

## 3. `RememberMeServices`: API and Meaning of Each Callback

The standard contract in `org.springframework.security.web.authentication.RememberMeServices` consists of three methods:

```java
// Reference signatures, not a full standalone interface.
Authentication autoLogin(
    HttpServletRequest request,
    HttpServletResponse response);

void loginFail(
    HttpServletRequest request,
    HttpServletResponse response);

void loginSuccess(
    HttpServletRequest request,
    HttpServletResponse response,
    Authentication successfulAuthentication);
```

These are abbreviated API signatures; to compile, place them in a class/interface with proper Spring Security and Servlet imports.

**`loginSuccess`** is invoked after a successful primary authentication (typically form login). It decides whether a remember-me cookie is issued, based on the checkbox/alwaysRemember setting and implementation. If the checkbox is unchecked, a cookie is not issued by default.

**`loginFail`** allows cleaning up the cookie or remember-me state when primary login fails. Do not confuse this callback with an HTTP 403 caused by missing permissions on a post-login endpoint: an authorization rejection is not a failed login POST.

**`autoLogin`** reads the cookie from the request and checks whether an `Authentication` candidate can be built. With token-based services, validation typically checks expiration/signature and loads `UserDetails`. With persistent tokens, it queries and updates a server-side token repository. It can return `null` when no suitable info is present or reject an invalid token.

An application can replace `RememberMeServices` for special requirements, but must properly handle `autoLogin`, `loginSuccess`, `loginFail`, cookie cleanup, and logout. Overriding only cookie creation while forgetting how parsing or revocation works creates risk.

### Form Checkbox Name Must Match Configuration

```html
<form method="post" action="/login">
  <input name="username" autocomplete="username">
  <input name="password" type="password"
         autocomplete="current-password">
  <label>
    <input name="remember-me" type="checkbox">
    Remember me
  </label>
  <!-- Must include a server-provided CSRF token in CSRF-enabled apps. -->
  <button type="submit">Sign in</button>
</form>
```

This is a **UI fragment**; it is insufficient in a CSRF-enabled app unless a real CSRF hidden parameter is rendered. If you change `rememberMeParameter("keepSignedIn")`, the frontend must update the checkbox `name` accordingly. Do not assume changing only the visible label is enough.

## 4. `RememberMeAuthenticationFilter`: Execution Conditions and Boundaries

The filter is what triggers Phase B. Conceptual logic:

```text
request enters chain with remember-me enabled
    |
    +--> SecurityContext already has Authentication?
    |       |
    |       +-- Yes -> do not run autoLogin
    |       |
    |       +-- No
    |            |
    |            v
    |     RememberMeServices.autoLogin(...)
    |            |
    |            +-- null/invalid -> do not restore
    |            |
    |            +-- candidate present -> AuthenticationManager.authenticate(...)
    |                                        |
    |                                        +-- provider accepts
    |                                        |     -> write Authentication to context
    |                                        |
    |                                        +-- provider rejects
    |                                              -> clear/failure path
    |
    v
continue to authorization and MVC
```

In standard configuration, the remember-me filter runs before anonymous authentication processing so a request without an identity gets a chance to be restored via cookie. Distinguish between **a context with no Authentication yet** and a request that has already become anonymous after another filter.

How `SecurityContext` is saved after successful remember-me depends on the Spring Security version, filter strategy, and `SecurityContextRepository`. Do not assume every app saves remember-me auth into a new `HttpSession`, nor assume every remembered request is stateless.

The filter is **not** the place to:

- Compare a form password against a password hash.
- Decide whether an admin URL is accessible.
- Verify cookie checksums/signatures directly without going through services.
- Unconditionally reissue a long-lived cookie on every GET.
- Bypass CSRF for POST/PUT/PATCH/DELETE requests.
- Revoke all HTTP sessions or JWTs solely because the remember-me cookie was removed.

When multiple `SecurityFilterChain` instances exist, URLs needing recovery must be handled by a chain containing the remember-me filter. `http.rememberMe(...)` in one chain does not automatically add the filter to other chains.

## 5. `RememberMeAuthenticationToken` and `RememberMeAuthenticationProvider`

After `RememberMeServices` validates the cookie, it can construct a `RememberMeAuthenticationToken`: a server-side `Authentication` object carrying a principal and authorities at the remember-me level. This object is **different from the raw browser cookie**; do not think the provider decodes cookies directly from HTTP headers.

`RememberMeAuthenticationProvider` receives this token through `AuthenticationManager` and checks the **key hash**. The keys in services and provider must match. The purpose is to ensure the remember-me token was produced under a trusted configuration; the provider does not act as a `PasswordEncoder` and does not inspect cookie signatures or database series/tokens itself.

```text
cookie bytes
    |
    v
RememberMeServices
   verify signature/expiry or persistent token store
   load UserDetails/authorities
    |
    v
RememberMeAuthenticationToken(sharedKey, principal, authorities)
    |
    v
AuthenticationManager
    |
    v
RememberMeAuthenticationProvider(sharedKey)
   compare key hash
    |
    v
Remember-me level Authentication
```

If you need to wire the provider manually in advanced configuration, illustrative fragment:

```java
String keyFromSecureConfiguration = "example-only-shared-key";
RememberMeAuthenticationProvider provider =
    new RememberMeAuthenticationProvider(keyFromSecureConfiguration);
```

The fragment requires importing `org.springframework.security.authentication.RememberMeAuthenticationProvider`. The key above is illustrative only; never use it in production. The provider must actually be registered with the appropriate authentication manager. When using `http.rememberMe(...)`, the Spring Security DSL provides the integration; do not create duplicate providers/filters.

### Why Can a Remember-me Token Be Authenticated Yet Not Fully Authenticated?

`RememberMeAuthenticationToken.isAuthenticated()` can return `true`, yet it represents restoring an identity from a pre-existing cookie rather than a primary login during the current interaction. `AuthenticationTrustResolver` and authorization managers distinguish anonymous, remember-me, and fully authenticated states.

| Check | Successful form login | Restored via remember-me cookie |
| --- | --- | --- |
| `authentication != null` | True | True |
| `authentication.isAuthenticated()` | Usually `true` | Can also be `true` |
| `AuthenticationTrustResolver.isRememberMe(auth)` | Usually `false` | `true` |
| `authenticated()` authorization | Usually allowed | Can be allowed |
| `fullyAuthenticated()` authorization | Allowed if no other conditions fail | **Not** satisfied by remember-me alone |
| Business MFA/step-up requirement | Still depends on policy | Should require stronger mechanism for sensitive actions |

Code that checks `isAuthenticated()` and concludes the user “just entered a password” is unsafe for flows requiring re-authentication. Use authorization rules, a trust resolver, or an explicit step-up/MFA mechanism with clear evidence.

## 6. Authenticated and fullyAuthenticated: Designing Authorization by Trust Level

Example in `HttpSecurity`:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/profile").authenticated()
    .requestMatchers("/sensitive").fullyAuthenticated()
    .anyRequest().denyAll()
)
```

- `authenticated()`: accepts any authenticated non-anonymous identity, where remember-me may be accepted depending on configuration.
- `fullyAuthenticated()`: requires authentication that is neither anonymous nor remember-me-only. This rule **does not automatically guarantee MFA** or “password entered within 5 minutes”; if recency/MFA is needed, design it separately.
- `rememberMe()` in authorization config is a specialized condition for authentication classified by the trust resolver as remember-me; it should not be used to replace full auth requirements on sensitive endpoints.

Actions such as changing passwords, modifying recovery info, confirming payments, granting admin privileges, or viewing highly sensitive data should generally require **full authentication** or stronger step-up. Do not rely solely on a user having a remember-me cookie to approve risky transactions.

### Distinguishing 302/401/403

When a remembered user accesses `/sensitive` requiring `fullyAuthenticated()`, Spring Security may send the user to an entry point/login page or produce an error status depending on the filter chain and configuration. Receiving 302 instead of 403 does not mean the cookie is invalid; the rule may intentionally request re-login. Do not hardcode a single inference from the status code without looking at the rule and authentication type.

## 7. Token-Based Remember-me: Simple but Hard to Revoke Per Cookie

`TokenBasedRememberMeServices` creates a remember-me cookie containing data for checking expiration and signature. It uses a server-side secret key and account info to validate the token. Cookie format, algorithms, and signing details **can differ across Spring Security versions/configurations**; do not write a custom parser based on a Base64 string observed in the browser.

Diagram:

```text
Password login succeeds + remember-me checked
         |
TokenBasedRememberMeServices issues token/cookie with expiry and signature
         |
Browser stores remember-me cookie
         |
New request without session Authentication
         |
TokenBasedRememberMeServices.autoLogin(...)
         |
check cookie/expiry/signature, load UserDetails
         |
RememberMeAuthenticationToken
         |
RememberMeAuthenticationProvider
         |
Authorization for the request
```

Pros: no need for a per-cookie token table; easy to use in small apps or demos. However, there are limitations:

1. **Selective revocation is hard**: if a cookie is copied, clearing the cookie in the original browser does not delete the copy. There is no server-side token series to revoke individual devices.
2. **Key must be strong and stable**: changing the key usually invalidates previously issued cookies. Nodes serving the same app must share the secret key if cookies are to work when requests switch nodes.
3. **Password change/user removal** can invalidate token-based cookies depending on how signature verification and user lookup work. However, do not assume changing a password also revokes all sessions, refresh tokens, or other access tokens.
4. **Long TTL increases risk**: a long-lived cookie is a long-lived bearer credential. Bound `tokenValiditySeconds` to actual need and enforce Secure/HttpOnly/HTTPS.
5. **Stale `UserDetails` cache** can delay the effect of user/authority changes. If an account is locked, evaluate checks/revocation separately rather than guessing every provider runs full account-status checks like `DaoAuthenticationProvider`.

A “log out all devices immediately” policy typically requires server-side revocation or another strategy beyond pure token-based cookies.

## 8. Persistent Remember-me: Server Stores Series/Token and Supports Revocation

`PersistentTokenBasedRememberMeServices` uses `PersistentTokenRepository`. The cookie contains series/token data, and the server looks up the record to confirm and rotate the token upon use. Common components:

- `PersistentTokenBasedRememberMeServices`: remember-me implementation that reads, rotates, and writes cookies/tokens via the repository.
- `PersistentTokenRepository`: contract to save/query/update/remove tokens.
- `JdbcTokenRepositoryImpl`: JDBC-backed repository implementation.
- `InMemoryTokenRepositoryImpl`: for testing or demos; not durable across restarts and unsuitable for clusters.
- `CookieTheftException`: mismatch error that can indicate a copied token or a race; requires proper operational handling.

```text
remember-me cookie
  series = S12
  token  = T_old
       |
       v
PersistentTokenBasedRememberMeServices
       |
       v
PersistentTokenRepository looks up series S12
       |
       +--> not found -> reject
       |
       +--> different token -> mismatch/theft handling
       |
       +--> token matches -> load user, rotate/update token,
                             send new cookie if policy requires
       |
       v
RememberMeAuthenticationToken -> provider -> context
```

Because a server-side record exists, the app can delete tokens by user/series and build better device management. However, **persistent does not mean un-replayable**: a valid copied token can still be attempted before rotation/revocation occurs. Concurrent requests using the same cookie can cause mismatches and false-positive theft detection; a production design must test concurrency, retries, multi-node behavior, and real devices.

### Comparison Table

| Criterion | Token-based | Persistent token |
| --- | --- | --- |
| Per-cookie token store | Not required | Yes, via `PersistentTokenRepository` |
| Cookie value verification | Signature/expiry/key and user info per implementation | Series/token matched against server-side record |
| Revoke an individual token | Difficult without extra state/revocation | Repository management available; may need extended API per device |
| Server-side data dependencies | User details/key | User details, token DB, and key/provider config |
| Multi-node | Requires identical key and consistent user store | Requires shared/synchronized token repository and concurrency handling |
| Replay/theft | Valid cookie can be used | Token rotation/mismatch detection helps but is not absolute |
| Operations | Simpler | Schema, cleanup, migration, higher reliability demands |
| Migration | Changing key/format can invalidate old cookies | Changing schema/repository/cookie format requires planning |

Do not set a custom-designed cookie and assume the default `RememberMeServices` will understand it; use only the token format supported by the chosen implementation.

## 9. Complete Spring Boot 3.x + Java 17 Example: Form Login and Remember-me

The example uses **token-based remember-me** to show filter/services/provider coordination without needing a token database yet. Things to observe:

- Browser logs in with password and checks the `remember-me` checkbox.
- `GET /profile` accepts a remembered user.
- `GET /sensitive` requires `fullyAuthenticated()`.
- The controller prints the `Authentication` token class for learning purposes (do not expose class names as a public API contract in production).
- Standard logout keeps CSRF enabled and lets services clear the browser cookie.

### Dependencies

In a Gradle Spring Boot 3.x project with plugin and dependency management configured:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
```

Create `src/main/java/example/rememberdemo/RememberDemoApplication.java`:

```java
package example.rememberdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class RememberDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(RememberDemoApplication.class, args);
    }
}

@Configuration
class SecurityConfiguration {

    // For local demo only. In production use a secret manager,
    // never hardcode keys in code or public repositories.
    private static final String DEMO_REMEMBER_KEY =
        "local-demo-remember-key-never-use-for-production-2026";

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, UserDetailsService users) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/profile").authenticated()
                .requestMatchers("/sensitive").fullyAuthenticated()
                .anyRequest().denyAll()
            )
            .formLogin(Customizer.withDefaults())
            .rememberMe(remember -> remember
                .key(DEMO_REMEMBER_KEY)
                .userDetailsService(users)
                .rememberMeParameter("remember-me")
                .tokenValiditySeconds(14 * 24 * 60 * 60)
            )
            .logout(logout -> logout
                .logoutSuccessUrl("/login?logout")
            )
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails learner = User.withUsername("learner")
            .password(encoder.encode("demo-pass"))
            .roles("USER")
            .build();
        return new InMemoryUserDetailsManager(learner);
    }
}

@RestController
class DemoController {

    @GetMapping("/public")
    String publicPage() {
        return "public";
    }

    @GetMapping("/profile")
    String profile(Authentication authentication) {
        return "profile=" + authentication.getName()
            + "; authType=" + authentication.getClass().getSimpleName();
    }

    @GetMapping("/sensitive")
    String sensitive(Authentication authentication) {
        return "sensitive=" + authentication.getName();
    }
}
```

**Explanation of choices:**

- Java 17 allows one public class matching the filename alongside package-private top-level classes in the same file. `@SpringBootApplication` scans package `example.rememberdemo`.
- The demo `UserDetailsService` keeps the account in memory, hashed via delegating encoder. Never push demo credentials or demo keys to production.
- `.formLogin(Customizer.withDefaults())` enables `UsernamePasswordAuthenticationFilter`; GET `/login` is normally auto-generated by Spring Security when no custom page is set.
- `.rememberMe(...)` registers the remember-me pipeline with a consistent key and `UserDetailsService`. **No need** to manually instantiate `RememberMeAuthenticationFilter`/`RememberMeAuthenticationProvider`.
- `.rememberMeParameter("remember-me")` wires the form checkbox; `.tokenValiditySeconds(...)` sets token validity, not a 14-day session lifetime.
- `.authenticated()` permits remembered identity on `/profile` while `.fullyAuthenticated()` requires stronger login on `/sensitive`.
- `.logout(...)` uses logout with CSRF and remember-me services. Do not assume logging out on one browser revokes all stolen token copies.

### Running the Application

At the root of the Gradle project containing the wrapper:

```bash
./gradlew bootRun
```

On Windows PowerShell you can run `./gradlew.bat bootRun`.

Open the local URLs:

```text
http://localhost:8080/public
http://localhost:8080/profile
```

**Expected:** `/public` returns body `public`; anonymous `/profile` redirects to the login page. Enter `learner` / `demo-pass` and tick the **Remember me** checkbox if your default form/template displays that option.

After logging in with password, the `/profile` controller can return:

```text
profile=learner; authType=UsernamePasswordAuthenticationToken
```

If **session authentication is gone** while the browser still sends a valid remember-me cookie, the filter restores identity and the controller can return:

```text
profile=learner; authType=RememberMeAuthenticationToken
```

This is **expected output based on the code**, not an actual run log. If the session is still active, requests may continue using `UsernamePasswordAuthenticationToken`; refreshing the page **does not automatically delete the session**. To verify remember-me, you must send a request with no session cookie or an expired session while keeping the remember-me cookie.

### About Custom Login Pages

A minimal form with the checkbox:

```html
<form method="post" action="/login">
  <input name="username" autocomplete="username">
  <input type="password" name="password"
         autocomplete="current-password">
  <label>
    <input name="remember-me" type="checkbox">
    Remember me
  </label>
  <!-- Render hidden CSRF input provided by Spring Security. -->
  <button type="submit">Sign in</button>
</form>
```

An HTML fragment is insufficient on a CSRF-enabled app without a real CSRF token from the server; use MVC view/template integration to render the token and proper context path. If you configure a custom `loginPage(...)`, Spring Security will not auto-generate that HTML page; you must declare a GET controller/view and appropriate access rules.

## 10. MockMvc: Proving `autoLogin` Instead of Just Testing Session

In integration tests, the crucial step is **after the initial login, sending a new HTTP request that carries only the remember-me cookie and no session authentication**. Only then can you observe `RememberMeAuthenticationFilter`/services/provider restoration.

Add dependencies:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Create `src/test/java/example/rememberdemo/RememberMeSecurityTest.java`:

```java
package example.rememberdemo;

import jakarta.servlet.http.Cookie;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.hamcrest.Matchers.containsString;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class RememberMeSecurityTest {

    @Autowired
    MockMvc mvc;

    private Cookie loginAndGetRememberCookie() throws Exception {
        MvcResult login = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "learner")
                .param("password", "demo-pass")
                .param("remember-me", "on"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        Cookie cookie = login.getResponse().getCookie("remember-me");
        assertNotNull(cookie, "Opt-in successful login should issue cookie");
        return cookie;
    }

    @Test
    void successfulOptInIssuesRememberMeCookie() throws Exception {
        Cookie cookie = loginAndGetRememberCookie();
        assertNotNull(cookie.getValue());
    }

    @Test
    void cookieAloneCanRestoreRememberMeAuthentication()
            throws Exception {
        Cookie cookie = loginAndGetRememberCookie();

        // Do not pass HttpSession from login to this request.
        mvc.perform(get("/profile").cookie(cookie))
            .andExpect(status().isOk())
            .andExpect(content().string(containsString(
                "authType=RememberMeAuthenticationToken")));
    }

    @Test
    void rememberMeIsNotFullyAuthenticated() throws Exception {
        Cookie cookie = loginAndGetRememberCookie();
        mvc.perform(get("/sensitive").cookie(cookie))
            .andExpect(status().is3xxRedirection())
            .andExpect(header().string(
                "Location", containsString("/login")));
    }

    @Test
    void anonymousNeedsLoginForProfile() throws Exception {
        mvc.perform(get("/profile"))
            .andExpect(status().is3xxRedirection())
            .andExpect(header().string(
                "Location", containsString("/login")));
    }

    @Test
    void notCheckingRememberMeDoesNotIssueCookie()
            throws Exception {
        MvcResult login = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "learner")
                .param("password", "demo-pass"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        assertNull(login.getResponse().getCookie("remember-me"));
    }
}
```

Run:

```bash
./gradlew test
```

The test code and assertions above are built for the described configuration; **no actual execution was performed while authoring this document**. MockMvc does not fully simulate browser behavior for `Secure`/`SameSite` cookies or browser-close durations. In production, test further with real browsers, HTTPS, and reverse proxies.

Important additional tests: tampered cookie; expired cookie; changed key; deleted user; locked account; concurrent requests; logout; password change; stale cache; deleted persistent token series; behavior when `fullyAuthenticated()` requires re-login.

## 11. Using a Persistent Token Store with JDBC When Revocation Management Is Needed

If the system requires server-side revocation or token tracking, you can switch to `JdbcTokenRepositoryImpl`. This is an **extension guide**; the following fragments are not a standalone application and must not be pasted alongside the token-based config without replacing the corresponding DSL.

Add JDBC and appropriate driver dependencies:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2' // For local demo only.
}
```

Repository bean in a `@Configuration`:

```java
@Bean
PersistentTokenRepository persistentTokenRepository(
        javax.sql.DataSource dataSource) {
    JdbcTokenRepositoryImpl repository = new JdbcTokenRepositoryImpl();
    repository.setDataSource(dataSource);
    return repository;
}
```

Imports:

```java
import org.springframework.security.web.authentication.rememberme.PersistentTokenRepository;
import org.springframework.security.web.authentication.rememberme.JdbcTokenRepositoryImpl;
```

In `HttpSecurity`, replace the remember-me configuration with the repository-backed variant:

```java
.rememberMe(remember -> remember
    .key(rememberMeKey)
    .userDetailsService(users)
    .tokenRepository(persistentTokenRepository)
    .tokenValiditySeconds(14 * 24 * 60 * 60)
)
```

The snippet assumes `rememberMeKey`, `users`, and `persistentTokenRepository` are injected/created with matching types. The token table must be created via migration before the service operates. Illustrative DDL for the standard schema:

```sql
CREATE TABLE persistent_logins (
    username VARCHAR(64) NOT NULL,
    series VARCHAR(64) PRIMARY KEY,
    token VARCHAR(64) NOT NULL,
    last_used TIMESTAMP NOT NULL
);
```

The schema must match the target database/dialect and actual implementation; use a migration tool in production, and do not grant overly broad DDL privileges to the web application account.

**Persistent remember-me specific notes:**

- **Multi-node consistency**: share the repository and key configuration, and handle concurrent token rotation.
- **Revocability**: design token deletion policies on logout, password reset, and account lockout; do not treat clearing the browser cookie as deleting all server-side tokens.
- **Device-aware controls**: if “forget this device” or a device list is needed, you may have to extend the repository since `removeUserTokens(username)` operates per user rather than providing a rich per-device API out of the box.
- **Token mismatch**: may signal theft, though concurrent requests can also cause races; do not disable all checks just because a two-tab test failed.
- **Cleanup and observability**: purge expired tokens, rate-limit anomalies, and never write raw tokens into logs or metrics.
- **Persistence**: `InMemoryTokenRepositoryImpl` loses data on restart and is not a production cluster choice.

## 12. Logout, Key Rotation, and Account State Changes

### Browser Logout

Logout typically clears `SecurityContext`, invalidates the session per policy, removes the browser remember-me cookie via `RememberMeServices.logout`, and cleans up the token store if supported by the implementation. Spring Security logout filters/handlers must be configured properly; POST logout may require a CSRF token.

**Do not equate three distinct events**:

1. Deleting `JSESSIONID` does not delete the remember-me cookie.
2. Clearing the remember-me cookie in the browser does not invalidate a stolen cookie copy.
3. Revoking a remember-me token does not automatically revoke all other sessions/JWTs/refresh tokens.

With token-based remember-me, client-side logout does not guarantee a copied cookie becomes useless immediately; if the security requirement is revoke-all, you need a server-side strategy or policy-driven key/signing-data change. With persistent tokens, revocation capability is better, though you must verify the actual logout path has sufficient authentication/user context to delete the right records.

### Key Rotation

The key is a server-side secret. Nodes need a consistent key, and rotating the key can invalidate old cookies. If a key lifecycle is required, plan for downtime, multi-node rollout, migration/old-credential invalidation, monitoring, and re-login UX. Never let clients choose the key, and never disable `keyHash` verification to “save” old cookies.

### Locked Account or Password Change

When an admin locks a user or revokes privileges:

- `UserDetailsService` must supply fresh data and caches must be invalidated.
- `RememberMeServices` usually loads the user, but **`RememberMeAuthenticationProvider` does not automatically re-run full pre/post account checks like `DaoAuthenticationProvider`**. Therefore do not assume `isAccountNonLocked=false` definitely blocks all live remember-me tokens.
- Persistent repositories may need token deletion by user/series; token-based setups may need appropriate key/password-change/invalidation policies.
- Sessions that already held an authentication prior to locking can stay alive; session revocation or request-time checks are required when “lock immediately” is mandated.
- JWTs and other access/refresh tokens have separate revocation paths and do not automatically expire alongside remember-me.

If you must satisfy an SLA like “account lock takes effect within 10 seconds”, design the solution and **measure** from DB commit until all requests/sessions/tokens are blocked; do not merely verify that `removeUserTokens` was called on one node.

## 13. Cookie Flags, HTTPS, XSS/CSRF, and Session Management

Remember-me cookies are credentials. Protecting password hashes in the database while exposing remember cookies over HTTP or in logs still risks account takeover.

**Cookie flags and scope:**

- **Secure**: on public HTTPS, the cookie must only be sent over HTTPS connections. When TLS terminates at a proxy, configure trusted forwarded headers properly.
- **HttpOnly**: restricts JavaScript from reading the cookie; it does not stop same-origin XSS scripts from initiating actions under the user's identity.
- **SameSite**: use `Lax`/`Strict` or a policy fitting login/cross-site flows; do not treat SameSite as the sole defense against CSRF.
- **Domain/Path**: expose only the required scope; do not share remember-me cookies across applications outside the same trust boundary.
- **Max-Age/Expires**: how long the browser retains the cookie and how long the server accepts the token may differ; the browser may delete early, and the server must verify expiry.

**HTTPS and credential hygiene:** TLS in production is mandatory; never log cookie values, Base64 tokens, passwords, `Authorization` headers, query strings with credentials, or raw `Authentication` objects.

**CSRF:** browsers automatically attach remembered cookies to target-domain requests, so **CSRF protection remains critical** for state-changing operations. Spring Security Servlet normally enables CSRF by default; do not call `.csrf(...disable...)` just because “remember-me is used”.

**XSS:** if an attacker executes same-origin JavaScript, they can trigger actions even without reading an `HttpOnly` cookie; apply output encoding, CSP, and independent XSS defenses.

**Session:** session fixation after password login should be protected with an appropriate strategy. Remember-me restoration may interact with session context depending on config; do not assume every remember-me login always creates a session or always bypasses session creation.

## 14. Common Operational Issues

| Symptom | Possible cause | Diagnostic direction |
| --- | --- | --- |
| `remember-me` cookie exists yet GET stays anonymous | Expired cookie/wrong key/path/domain, not sent, user lookup failed, wrong chain | Inspect cookie flags and filter chain, redacted logging |
| Password login succeeds yet no cookie | Checkbox unchecked/wrong name, `alwaysRemember` false, DSL not enabled | Check POST parameter and `.rememberMe(...)` |
| Remember-me still redirects to /login on sensitive endpoint | `fullyAuthenticated()` requires stronger login | Check authorization rule, do not blame the token |
| Page reload still shows normal form auth | Session has not expired; remember-me filter does not need to run | Test cookie-only request without session |
| Works on one node, prompts login on another | Keys differ / token repository not shared | Secret config / cluster DB, deployment strategy |
| Cookie stops working after restart | Key changes on every start; in-memory token store lost | Stable secret, durable repository, migrations |
| Copied old cookie still works after logout | Token-based lacks per-cookie revocation | Choose persistent/revocation strategy |
| Strange remember-me behavior after password change | Password hash/secret changed, stale cache, or cookie mismatch | Check implementation and invalidation |
| Account locked yet remembered access still valid | Account-status check/revocation not applied to remember-me, old session still alive | Security policy for account state + session/token revocation |
| Persistent token reports theft after two concurrent requests | Rotation race/mismatch | Test concurrency, audit, and error handling |
| POST /logout returns 403 | Missing/wrong CSRF token | Use POST with valid CSRF, do not disable protection |
| Cookie sent on wrong origin/scheme | Misconfigured proxy/TLS/Domain/SameSite/Secure | Review public HTTPS origin, trusted forwarded headers |

### Methodical Debugging

1. Confirm the selected `SecurityFilterChain`, request matcher, and presence of `RememberMeAuthenticationFilter`.
2. Confirm the cookie is actually **sent to the server**, not merely visible in browser storage.
3. Check whether the context already holds a session auth; if so, remember-me may not run.
4. Identify whether `RememberMeServices` is token-based or persistent.
5. Check token expiry, key, user lookup, and persistent repository/series (if used) without printing raw values.
6. Check the provider for `RememberMeAuthenticationToken` and the authentication manager.
7. Check whether the authorization rule is `authenticated()` or `fullyAuthenticated()`.
8. Check logout, session invalidation, password/role/locked changes, and other token types.
9. Verify in multi-node and HTTPS environments rather than only local MockMvc.
10. If debug logs are needed, limit duration, audience, and sensitive data, then disable them after diagnosis.

## 15. Conceptual Misconceptions

### "Remember-me is just a long-lived session cookie"

Incorrect. A remember-me credential can be used **after session authentication is lost**, and is restored through a different filter/services/provider path.

### "RememberMeAuthenticationProvider reads the cookie and compares signatures"

No. It verifies `RememberMeAuthenticationToken` using the shared key hash; cookie/token store logic belongs to `RememberMeServices`.

### "Having RememberMeAuthenticationToken and isAuthenticated=true means the user just entered a password"

No. Use `AuthenticationTrustResolver`, `fullyAuthenticated()`, and step-up/recency policies when needed.

### "Enabling rememberMe() is enough to issue a cookie on every login"

Not if policy requires the checkbox. Check the `remember-me` parameter or `alwaysRemember` if that choice is approved.

### "Clearing browser cookies deletes all stolen tokens"

No. With token-based, copies can still be used. With persistent, revocation depends on the server-side repository and proper revoke paths.

### "Persistent tokens automatically solve all replay"

No. Rotation/mismatch detection helps, but races/concurrency, token store reliability, and handling stolen copies must be addressed.

### "Locking an account automatically rejects all remember-me auth"

Do not assume that by default. Check the code paths of services and provider, caches, sessions, persistent token revocation, and business rules.

### "Clearing the UserDetails cache automatically removes old sessions"

No. The session already holds its own `Authentication`, and cookies/tokens have independent lifecycles.

### "Remember-me doesn't need CSRF because it's just a UX helper cookie"

Wrong. A browser can automatically send remember-me credentials, so unsafe operations require CSRF mitigation per the threat model.

## 16. Exercises and Review Questions

**Q1.** The browser still holds `JSESSIONID` containing the primary `Authentication`. Does `RememberMeAuthenticationFilter` always invoke `autoLogin` on every request?

**Answer:** No. When `SecurityContext` already has an authentication, the filter normally does not need to auto-login via the remember-me cookie.

**Q2.** `RememberMeServices` and `RememberMeAuthenticationProvider` both use a key, so which responsibilities overlap?

**Answer:** A consistent key is a coordination condition, but their responsibilities differ: services inspect the cookie/token and build a candidate; the provider verifies the key hash of the internal remember-me token via the authentication manager.

**Q3.** The cookie exists yet the user still cannot view `/sensitive`; that endpoint uses `fullyAuthenticated()`. Is the cookie corrupted?

**Answer:** Not necessarily. Remember-me authentication may be valid without meeting the `fullyAuthenticated` level. This may be the intended security behavior.

**Q4.** Why is a MockMvc test checking `Set-Cookie` on `POST /login` insufficient to prove remember-me works?

**Answer:** It has not tested the `autoLogin` phase. You must perform another request with only the remember cookie and no session authentication, then observe `RememberMeAuthenticationToken`.

**Q5.** An admin revokes roles or locks a user; does clearing browser cookies guarantee all sessions and JWTs are blocked?

**Answer:** No. You need policies for account state, `UserDetails` cache, remember-me token revocation, active sessions, and other token types.

**Q6.** What is the advantage of a persistent token repository over a token-based cookie when “forget device” is needed?

**Answer:** It maintains server-side token state for revocation/rotation; the repository/model may need extension to manage devices accurately.

**Q7.** Why do a hardcoded key in source and differing keys across nodes cause failures?

**Answer:** Hardcoded keys risk leakage, and differing keys prevent provider/services from accepting tokens across nodes. Production needs a secure, uniform secret.

**Q8.** When a user has remember-me auth, `authentication.isAuthenticated()` returns true. Should password changes be allowed without re-authenticating?

**Answer:** Do not rely on that flag alone. Depending on policy, require full authentication, step-up, MFA, or re-verification of valid credentials.

**Q9.** A persistent cookie reports a token mismatch after two concurrent requests. Can mismatch checks be ignored to avoid inconvenience?

**Answer:** You should not. Analyze races versus actual token theft conditions; arbitrarily ignoring mismatches weakens the protection mechanism.

**Q10.** Token-based remember-me needs no token table. Does it still need a user database?

**Answer:** You still need a `UserDetailsService` identity source (or equivalent) to load accounts/authorities per implementation, as well as a system to manage accounts and password hashes.

## 17. Remember-me Acceptance Checklist

- [ ] Identify the exact chain containing `RememberMeAuthenticationFilter` and avoid duplicate filter configuration.
- [ ] Choose token-based/persistent matching cookie revocation and operational requirements.
- [ ] `RememberMeServices` handles `loginSuccess`, `loginFail`, and `autoLogin` per scenario.
- [ ] `AuthenticationManager` has a `RememberMeAuthenticationProvider` with matching key.
- [ ] The `remember-me` checkbox is actually submitted and cookies are not issued unintentionally unless `alwaysRemember` is set.
- [ ] Key is long/random, managed via secret manager, synchronized across nodes, with a rotation plan.
- [ ] Cookie is `Secure` over HTTPS, `HttpOnly`, with appropriate Domain/Path/SameSite and TTL.
- [ ] Test password login, cookie-only restore, expired/corrupt tokens, wrong key, and no-cookie cases.
- [ ] Test that `authenticated()` accepts remembered identity where allowed while `fullyAuthenticated()` requires re-login.
- [ ] Do not let remember-me bypass CSRF, authorization, or MFA/step-up on sensitive actions.
- [ ] Logout/revocation and “logout all devices” are tested on both browser and token store.
- [ ] Account lockout, password changes, and role revocation have explicit policies across remember-me, sessions, and other tokens.
- [ ] If persistent: token table migration/cleanup, retry/rotation races, multi-node DB, and auditing are tested.
- [ ] Run browser/HTTPS/proxy integration tests rather than relying solely on MockMvc.
- [ ] Never print cookie values, passwords, hashes, or token secrets into logs/metrics.

## Conclusion

**`RememberMeAuthenticationFilter`** decides when login restoration is needed; **`RememberMeServices`** manages cookie values and acceptance criteria; **`RememberMeAuthenticationProvider`** verifies the internal remember-me token under the shared key before the authentication manager accepts it. Then `SecurityContext` and authorization decide which requests are allowed.

The core takeaway is that remember-me authentication **is not identical to full authentication**. A long-lived cookie acts as a credential and must be protected with bounded TTL, logout/revocation, key management, and account-status handling; sensitive operations require re-authentication or step-up per policy rather than merely checking `isAuthenticated()`.
