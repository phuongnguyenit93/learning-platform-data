# Remember-me, anonymous, and fullyAuthenticated in access policies

> Scope: **Spring Security - authentication → Remember Me**, **Spring Boot 3.x / Spring Security 6.x / Servlet / Java 17+**. This lesson focuses on **login session trust levels** when making access decisions: unauthenticated guests (anonymous), users re-identified via a remember-me cookie, and users who authenticated interactively in full (fully authenticated). These are distinct levels; sharing the same username and the same `ROLE_USER` authority does not mean every action should be permitted.

## 1. Three states that are not the same

A website with a “Remember me” feature usually puts a checkbox on the login form. After password authentication succeeds, the server can issue a remember-me cookie that outlives a normal login session. When the session expires or the browser does not send the old session, that cookie **restores identity at the remember-me trust level**, rather than proving the user just re-entered their password.

| State | How it is formed | Typical Authentication | Can read profile? | Should change password / transfer funds? |
| --- | --- | --- | --- | --- |
| **Anonymous** | No valid authentication; Spring Security creates an anonymous token for the request | `AnonymousAuthenticationToken` | No, unless route is public | No |
| **Remember-me** | Remember-me cookie verified when no session authentication exists | `RememberMeAuthenticationToken` | Possibly, if policy uses `authenticated()` | Should not; require `fullyAuthenticated()`, possibly MFA |
| **Fully authenticated** | Interactive login via form/password (or mechanism treated as full by the framework) | Successfully authenticated `UsernamePasswordAuthenticationToken` | Yes | Potentially yes, after checking both business permissions and auth level |

**Core point:** Spring Security does not automatically treat remember-me as “not logged in”; it is a valid authentication yet recognized as a **lower trust level** for sensitive actions. Thus, `authenticated()` **permits** both remember-me and full login, whereas `fullyAuthenticated()` accepts only full login, excluding anonymous and remember-me.

### 1.1. authenticated(), fullyAuthenticated(), rememberMe(), anonymous()

Spring Security 6.x provides rules inside `authorizeHttpRequests`:

- `.authenticated()`: requires an authenticated identity, **including** users identified via remember-me, **excluding anonymous**.
- `.fullyAuthenticated()`: requires an authenticated identity **not via remember-me** and not anonymous; commonly used for changing email, password, payouts, or security settings.
- `.rememberMe()`: requires the request to be authenticated in the **remember-me state**; full-login users do not match this rule. Rarely needed for business logic, useful for a dedicated “welcome back” page.
- `.anonymous()`: allows only principals treated as anonymous by the framework; rejects remember-me or full login.
- `.permitAll()`: every state may pass; does not mean the request must carry `AnonymousAuthenticationToken`.
- `.hasRole("USER")` or `.hasAuthority("...")`: checks **authorities**, without automatically requiring `fullyAuthenticated()`. A remembered user holding `ROLE_USER` can still pass a rule that only checks roles.

### 1.2. Access policy matrix

| Policy | Anonymous | Remember-me | Fully authenticated |
| --- | :---: | :---: | :---: |
| `permitAll()` | ✅ | ✅ | ✅ |
| `anonymous()` | ✅ | ❌ | ❌ |
| `rememberMe()` | ❌ | ✅ | ❌ |
| `authenticated()` | ❌ | ✅ | ✅ |
| `fullyAuthenticated()` | ❌ | ❌ | ✅ |
| `hasRole("USER")` (if user has role) | ❌ | ✅ | ✅ |
| `fullyAuthenticated()` **and** `hasRole("ADMIN")` | ❌ | ❌ | Admin only |

The table describes framework **authorization** decisions, not fixed HTTP status codes. With form login, when anonymous or remember-me requests a page requiring full login, `ExceptionTranslationFilter` typically **redirects to the login page** (`302`). A fully logged-in user lacking the role usually gets `403 Forbidden`. If an API uses a different authentication entry point, the status code can be `401`/`403` depending on configuration.

**Do not confuse:** “remember-me restored the principal and authorities” does not mean the user re-authenticated in the current session. `fullyAuthenticated()` checks authentication type via `AuthenticationTrustResolver`; it **does not** prove MFA was recently completed, is not a freshness window, and does not replace dedicated step-up checks.

## 2. Why can AnonymousAuthenticationToken cause confusion?

When there is neither a session nor a valid remember-me cookie, `AnonymousAuthenticationFilter` can place an `AnonymousAuthenticationToken` into `SecurityContextHolder`. That token can return `authentication.isAuthenticated() == true` because the framework created it, yet it **still represents an anonymous guest**, not a real logged-in user.

Therefore, the naive check below is **insufficient** to protect an endpoint:

```java
Authentication a = SecurityContextHolder.getContext().getAuthentication();
if (a != null && a.isAuthenticated()) {
    // Wrong if treated as proof of a real login:
    // AnonymousAuthenticationToken can also return true.
}
```

Spring Security uses `AuthenticationTrustResolver` to classify authentication origin:

```java
AuthenticationTrustResolver trust = new AuthenticationTrustResolverImpl();
Authentication a = SecurityContextHolder.getContext().getAuthentication();

boolean guest = trust.isAnonymous(a);
boolean remembered = trust.isRememberMe(a);
boolean knownUser = trust.isAuthenticated(a);
boolean fullLogin = trust.isFullyAuthenticated(a);
```

The **trust resolver's** `isAuthenticated(a)` (unlike raw `a.isAuthenticated()`) returns false for anonymous. `isFullyAuthenticated(a)` returns false for anonymous/remember-me and true for full authentication recognized by the resolver.

**Recommendation:** in URL configuration, use `authorizeHttpRequests(...).authenticated()/fullyAuthenticated()`; do not write custom filters relying on `Authentication.isAuthenticated()`. On business methods, combine `@PreAuthorize`/an appropriate authorization manager or verify state with the trust resolver when there is a clear reason.

## 3. Remember-me lifecycle: from checkbox to later request

```text
First visit:
  Browser (no session)
     | GET /profile
     v
  Authorization: not authenticated
     '-- redirect to /login (form)

Interactive login:
  Browser
     | POST /login
     | username=alice, password=study-pass
     | remember-me=on + CSRF
     v
  UsernamePasswordAuthenticationFilter
     | AuthenticationManager verifies username/password
     | SecurityContext saved in HttpSession
     | RememberMeServices.loginSuccess()
     '-- response contains JSESSIONID and remember-me cookies

While the session still exists:
  GET /auth-state + JSESSIONID
     '-- Authentication from HttpSession -> fully-authenticated:alice

After the session is not sent / has expired:
  GET /auth-state + remember-me cookie, WITHOUT old JSESSIONID
     |
     v
  RememberMeAuthenticationFilter
     | RememberMeServices.autoLogin() verifies cookie
     | loads UserDetails from server source
     | creates RememberMeAuthenticationToken
     '-- AuthenticationTrustResolver.isRememberMe() == true

  /profile uses authenticated()            -> allowed
  /security-settings uses fullyAuthenticated() -> requires re-login
```

Remember-me **only runs if the token is still valid** and the request lacks an already accepted Authentication in context. If both a full-login session and a remember-me cookie exist, full authentication from the session is normally used; remember-me does not downgrade trust level.

### 3.1. Two ways to issue remember-me tokens

**Hash-based token** (`TokenBasedRememberMeServices`): signature depends on username, expiry, password (current value provided by `UserDetailsService`), and an application secret key. Spring Security 6.x uses SHA-256 by default for signatures. The server verifies the cookie with account info + key. The upside is simplicity with no token table; the downside is that if stolen, it can be **replayed** until expiration or key/password change. Browser logout usually clears the cookie **on the client**; clearing a local cookie alone cannot revoke a copy stolen elsewhere.

**Persistent token** (`PersistentTokenBasedRememberMeServices`): uses a series/random token stored server-side (`PersistentTokenRepository`; e.g., JDBC). Usually supports rotation and stateful token management. Real systems must design revocation strategies, reused-token handling, stale-token cleanup, and multi-device policies. It remains a **security-sensitive bearer cookie**, and does not turn remember-me into full login.

Both mechanisms normally need `UserDetailsService` to reload identity and authorities. If primary authentication uses an external provider (such as LDAP/custom) without a matching `UserDetailsService`, configure an explicit lookup source; do not assume enabling `rememberMe()` automatically restores every principal type.

### 3.2. Remember-me cookies differ from session cookies

| Property | Session cookie | Remember-me cookie |
| --- | --- | --- |
| Purpose | References `HttpSession` state | Proof to reconstruct authentication when session is absent |
| Common name | `JSESSIONID` | `remember-me` (configurable) |
| Lifetime scope | Session/browser/container policy | Token validity and cookie policy |
| Deleting session | Loses full-login session | Remember-me cookie may still remain valid |
| Authorization trust | Full login if context holds interactive login result | Remember-me level, not full login |
| Theft impact | Can hijack session | Can re-authenticate at remember-me level |

Never place remember-me keys in production source code or send cookies to logs/analytics. Configure `Secure`/`HttpOnly`/`SameSite`, HTTPS, and appropriate domain/path; CSRF policy remains crucial because browsers send cookies automatically.

## 4. Spring Boot 3.x / Spring Security 6.x / Java 17+ example

The example uses standard form login, BCrypt encoding for demo users, opt-in remember-me, and a policy distinguishing all four states. The `GET /login` page is generated by Spring Security by default; no custom login page is written so focus stays sharp.

### 4.1. Dependencies

In a Spring Boot 3.x project with the Gradle plugin and Java 17:

```groovy
// build.gradle (dependencies section)
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

No Spring Session or database is needed to run this single-node demo. In real deployments, replace in-memory accounts with a user store and token store having matching management policies.

### 4.2. Application class

**`src/main/java/example/rememberpolicy/RememberPolicyApplication.java`**

```java
package example.rememberpolicy;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RememberPolicyApplication {
    public static void main(String[] args) {
        SpringApplication.run(RememberPolicyApplication.class, args);
    }
}
```

### 4.3. SecurityFilterChain configuration

**`src/main/java/example/rememberpolicy/SecurityConfig.java`**

```java
package example.rememberpolicy;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.security.authorization.AuthenticatedAuthorizationManager;
import org.springframework.security.authorization.AuthorizationManagers;
import org.springframework.security.authorization.AuthorityAuthorizationManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;

@Configuration
@EnableWebSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("study-pass"))
                .roles("USER")
                .build(),
            User.withUsername("operator")
                .password(encoder.encode("admin-pass"))
                .roles("USER", "ADMIN")
                .build()
        );
    }

    @Bean
    SecurityFilterChain filterChain(
            HttpSecurity http,
            UserDetailsService users,
            Environment environment) throws Exception {

        String signingKey = environment.getRequiredProperty(
            "app.remember-me.key");

        http
            .authorizeHttpRequests(auth -> auth
                // Everyone can access public resources.
                .requestMatchers("/public", "/auth-state").permitAll()

                // Route reserved for anonymous guests.
                .requestMatchers("/guest-only").anonymous()

                // Route exclusively for requests restored via remember-me.
                .requestMatchers("/remembered-only").rememberMe()

                // Profile can be viewed via full login or remember-me.
                .requestMatchers("/profile").authenticated()

                // Sensitive action: remembering login is not enough.
                .requestMatchers("/security-settings").fullyAuthenticated()

                // Sensitive example requiring both full login AND ROLE_ADMIN.
                .requestMatchers("/admin/critical").access(
                    AuthorizationManagers.allOf(
                        AuthenticatedAuthorizationManager
                            .<RequestAuthorizationContext>fullyAuthenticated(),
                        AuthorityAuthorizationManager
                            .<RequestAuthorizationContext>hasRole("ADMIN")
                    )
                )

                .anyRequest().denyAll()
            )
            .formLogin(form -> form
                .defaultSuccessUrl("/profile", true)
                .permitAll()
            )
            .rememberMe(remember -> remember
                .key(signingKey)
                .userDetailsService(users)
                .rememberMeParameter("remember-me")
                .tokenValiditySeconds(7 * 24 * 60 * 60)
            );

        // Default CSRF remains enabled for POST /login and POST /logout.
        return http.build();
    }
}
```

**Important details in the configuration:**

1. Matcher order matters; Spring Security selects the first rule matching the URL. `/security-settings` uses `fullyAuthenticated()`, not just `hasRole("USER")`.
2. `/admin/critical` uses `AuthorizationManagers.allOf(...)` to require **both** full login and `ROLE_ADMIN`. Requiring `hasRole("ADMIN")` alone would not exclude a remembered admin because `ROLE_ADMIN` is reloaded from the server.
3. `/remembered-only` is an illustrative route for the **strict** remember-me state. It does not replace `/profile`. In real apps, endpoints allowing only remember-me while denying full login are rare; a “welcome back” banner page is one possible use case.
4. `/guest-only` uses `anonymous()` to demonstrate a guest-only route. Spring Security's `/login` is permitted via `formLogin(...permitAll())`; do not put the login page under `anonymous()` because full or remembered users may need to log in again to step up trust level.
5. `.rememberMe(...)` sets up remember-me with a secret key, `UserDetailsService`, and a 7-day lifetime. The checkbox must send `remember-me=on` at login; if unchecked, no cookie is issued automatically. The 7-day duration is for demo only, not a universal product default.
6. `.formLogin(...)` uses `UsernamePasswordAuthenticationFilter` and the standard success handler. Remember-me services are invoked on login success, while `RememberMeAuthenticationFilter` can restore authentication on later requests **when no logged-in context exists**.
7. `.anyRequest().denyAll()` blocks undeclared routes. When adding new endpoints, choose explicit policies instead of leaving a permissive default.
8. Do not disable CSRF for cookie-based form login; browser POST requests still need tokens. `MockMvc` uses `csrf()` on POSTs.
9. `.key(signingKey)` uses a server-private secret. Do **not** use the dev example key in real deployments; load it from a secret manager/environment and manage rotation.

### 4.4. Demo configuration

**`src/main/resources/application.yml`**

```yaml
app:
  remember-me:
    # For local machine study only; real deployments use a separate secret.
    key: local-demo-key-only-do-not-use-in-production-2026

server:
  servlet:
    session:
      cookie:
        http-only: true
        same-site: lax
```

In production you need a strong random secret never committed to git; configure HTTPS/cookie `Secure` and `SameSite` per threat model. Across multiple instances, the key must be consistent across nodes serving the same domain. Changing the key invalidates previously issued hash-based cookies; changing passwords can do the same.

### 4.5. Controller displaying trust resolver status

**`src/main/java/example/rememberpolicy/AccessController.java`**

```java
package example.rememberpolicy;

import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AccessController {
    private final AuthenticationTrustResolver trust =
        new AuthenticationTrustResolverImpl();

    @GetMapping("/public")
    String publicPage() {
        return "public";
    }

    @GetMapping("/guest-only")
    String guestOnly() {
        return "guest";
    }

    @GetMapping("/remembered-only")
    String rememberedOnly() {
        return "welcome-back";
    }

    @GetMapping("/profile")
    String profile(Authentication user) {
        return "profile:" + user.getName();
    }

    @GetMapping("/security-settings")
    String securitySettings(Authentication user) {
        return "security:" + user.getName();
    }

    @GetMapping("/admin/critical")
    String adminCritical(Authentication user) {
        return "admin:" + user.getName();
    }

    @GetMapping("/auth-state")
    String authState() {
        Authentication a =
            SecurityContextHolder.getContext().getAuthentication();

        if (a == null || trust.isAnonymous(a)) {
            return "anonymous";
        }
        if (trust.isRememberMe(a)) {
            return "remember-me:" + a.getName();
        }
        if (trust.isFullyAuthenticated(a)) {
            return "fully-authenticated:" + a.getName();
        }
        return "unrecognized";
    }
}
```

`/auth-state` is left public **solely for observation in the demo**, reading context from `SecurityContextHolder` and classifying via `AuthenticationTrustResolver`. Never return raw tokens, authorities, session IDs, cookie values, or secrets to clients. In real apps, return only state information the UI actually needs and guard it with appropriate policies.

**Expected** response bodies from the endpoint (not live run stdout):

```text
GET /auth-state when not logged in              -> anonymous
GET /auth-state with logged-in JSESSIONID       -> fully-authenticated:alice
GET /auth-state with remember-me cookie only    -> remember-me:alice
GET /profile with remember-me cookie            -> profile:alice
```

Be sure to send the remember-me cookie **without a full-login session** in the third test. If a JSESSIONID carrying full authentication is still sent, the request continues to classify as full login.

## 5. MockMvc tests across the three authentication levels

The tests exercise the real `SecurityFilterChain`, submit `POST /login` with password + CSRF, capture the response cookie, and issue fresh requests. This differs from tests using `@WithMockUser`, because `@WithMockUser` injects a mock authentication without **proving** the remember-me cookie issuance and recovery flow.

**`src/test/java/example/rememberpolicy/RememberPolicyTest.java`**

```java
package example.rememberpolicy;

import jakarta.servlet.http.Cookie;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class RememberPolicyTest {
    @Autowired
    MockMvc mvc;

    private MvcResult login(
            String username, String password, boolean remember) throws Exception {
        var request = post("/login")
            .with(csrf())
            .param("username", username)
            .param("password", password);

        if (remember) {
            request.param("remember-me", "on");
        }

        return mvc.perform(request)
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/profile"))
            .andReturn();
    }

    private Cookie rememberCookie(String username, String password)
            throws Exception {
        MvcResult response = login(username, password, true);
        Cookie cookie = response.getResponse().getCookie("remember-me");
        assertNotNull(cookie, "A remember-me cookie must be issued on opt-in");
        assertNotNull(cookie.getValue());
        assertFalse(cookie.getValue().isBlank());
        return cookie;
    }

    @Test
    void anonymousCanReadPublicAndGuestButNotProfile() throws Exception {
        mvc.perform(get("/auth-state"))
            .andExpect(status().isOk())
            .andExpect(content().string("anonymous"));

        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));

        mvc.perform(get("/guest-only"))
            .andExpect(status().isOk())
            .andExpect(content().string("guest"));

        mvc.perform(get("/profile"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login"));
    }

    @Test
    void interactiveLoginIsFullyAuthenticated() throws Exception {
        MvcResult response = login("alice", "study-pass", false);
        MockHttpSession session =
            (MockHttpSession) response.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/auth-state").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("fully-authenticated:alice"));

        mvc.perform(get("/profile").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("profile:alice"));

        mvc.perform(get("/security-settings").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("security:alice"));
    }

    @Test
    void fullLoginDoesNotMatchRememberMeOnlyOrAnonymousOnly()
            throws Exception {
        MvcResult response = login("alice", "study-pass", false);
        MockHttpSession session =
            (MockHttpSession) response.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/remembered-only").session(session))
            .andExpect(status().isForbidden());

        mvc.perform(get("/guest-only").session(session))
            .andExpect(status().isForbidden());
    }

    @Test
    void rememberCookieRestoresIdentityWithoutOriginalSession()
            throws Exception {
        Cookie cookie = rememberCookie("alice", "study-pass");

        // NO .session(...) -> does not reuse Authentication from old session.
        mvc.perform(get("/auth-state").cookie(cookie))
            .andExpect(status().isOk())
            .andExpect(content().string("remember-me:alice"));

        mvc.perform(get("/profile").cookie(cookie))
            .andExpect(status().isOk())
            .andExpect(content().string("profile:alice"));

        mvc.perform(get("/remembered-only").cookie(cookie))
            .andExpect(status().isOk())
            .andExpect(content().string("welcome-back"));
    }

    @Test
    void rememberMeCannotReachFullyAuthenticatedResource()
            throws Exception {
        Cookie cookie = rememberCookie("alice", "study-pass");

        mvc.perform(get("/security-settings").cookie(cookie))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login"));
    }

    @Test
    void sensitiveAdminEndpointRequiresFullLoginAndRole()
            throws Exception {
        // Alice is fully logged in yet lacks ROLE_ADMIN.
        MvcResult aliceLogin = login("alice", "study-pass", false);
        MockHttpSession aliceSession =
            (MockHttpSession) aliceLogin.getRequest().getSession(false);
        assertNotNull(aliceSession);

        mvc.perform(get("/admin/critical").session(aliceSession))
            .andExpect(status().isForbidden());

        // Operator has ROLE_ADMIN, yet remember-me cookie is insufficient.
        MvcResult adminLogin = login("operator", "admin-pass", true);
        Cookie adminRemember =
            adminLogin.getResponse().getCookie("remember-me");
        assertNotNull(adminRemember);

        mvc.perform(get("/admin/critical").cookie(adminRemember))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login"));

        // Same operator with full-login session is allowed.
        MockHttpSession adminSession =
            (MockHttpSession) adminLogin.getRequest().getSession(false);
        assertNotNull(adminSession);

        mvc.perform(get("/admin/critical").session(adminSession))
            .andExpect(status().isOk())
            .andExpect(content().string("admin:operator"));
    }

    @Test
    void rememberMeCookieIsOnlyIssuedWithOptIn() throws Exception {
        MvcResult response = login("alice", "study-pass", false);
        assertNull(response.getResponse().getCookie("remember-me"));
    }

    @Test
    void tamperedRememberCookieDoesNotAuthenticate() throws Exception {
        mvc.perform(get("/auth-state")
                .cookie(new Cookie("remember-me", "invalid-cookie")))
            .andExpect(status().isOk())
            .andExpect(content().string("anonymous"));

        mvc.perform(get("/profile")
                .cookie(new Cookie("remember-me", "invalid-cookie")))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login"));
    }

    @Test
    void csrfStillProtectsLogin() throws Exception {
        mvc.perform(post("/login")
                .param("username", "alice")
                .param("password", "study-pass")
                .param("remember-me", "on"))
            .andExpect(status().isForbidden());
    }
}
```

The test suite contains **9 `@Test` methods**. Each login helper runs an independent HTTP request; when testing remember-me, the test **sends only the remember-me cookie** without forwarding the logged-in session. Conversely, testing full authentication uses the `MockHttpSession` returned by form login.

Run in the Spring Boot project root with the Gradle wrapper:

```bash
./gradlew test --tests example.rememberpolicy.RememberPolicyTest
./gradlew bootRun
```

On Windows use `gradlew.bat`. The response strings and statuses in the tests are **verifiable expectations**, not claims that Gradle was executed in the current environment.

### 5.1. Interpreting the tests accurately

1. **Anonymous** can reach `/public` and `/guest-only`, but not `/profile`. When not logged in, the form authentication entry point redirects to `/login`.
2. **Full login** accesses `/profile` and `/security-settings`; it does not match `.rememberMe()`-only or `.anonymous()`-only routes.
3. **Remember-me auto login** needs only a valid cookie when no full session exists; `/auth-state` returns `remember-me:alice`, while `/profile` still works because `authenticated()` accepts this level.
4. **Fully authenticated resources** still block remember-me: typically redirecting to `/login` so the user re-authenticates.
5. **Admin authorization** illustrates two independent conditions: a fully logged-in user lacking `ROLE_ADMIN` gets `403`; a remembered admin without full login is prompted to re-authenticate; only a fully logged-in admin enters.
6. **Checkbox and cookie**: omitting `remember-me` still lets login succeed, yet the response issues no remember-me cookie.
7. **Corrupted cookie**: fails to restore authentication; the request is classified anonymous and protected endpoints redirect to login.
8. **CSRF** continues protecting the login form POST; remember-me is no reason to disable CSRF.

**MockMvc limits:** the tests simulate HTTP and server filters, not full browser behavior regarding cookie expiry, SameSite, domain, Secure flags, private browsing, or proxies. For production, run end-to-end tests over HTTPS in real browsers covering TLS/cookie settings and timeout/revocation policies.

## 6. Manual testing with a browser

Run the app at `http://localhost:8080` in a local learning environment. In a dedicated browser profile, visit `/login`. Spring Security's default form shows a remember-me option when the feature is enabled.

**Pass A — without checking Remember me:**

1. Log in as `alice` / `study-pass` without checking the checkbox. `/auth-state` returns `fully-authenticated:alice` while `JSESSIONID` remains valid.
2. Open DevTools → Application/Storage → Cookies and verify no `remember-me` cookie was issued in this response.
3. Once the session is truly gone, `GET /profile` redirects to `/login`. Do not merely open a second tab in the same browser and assume the session was cleared.

**Pass B — with Remember me checked:**

1. Log out via POST with a CSRF token and log in again, this time checking the checkbox. On success, the browser may hold both `JSESSIONID` and the `remember-me` cookie.
2. While `JSESSIONID` remains valid, `/auth-state` **remains full login**, not remember-me.
3. In a separate demo step, delete **only** the `JSESSIONID`/session cookie in the browser, keeping the remember-me cookie; call `/auth-state` again. Expected result: `remember-me:alice`.
4. `GET /profile` keeps working; `GET /security-settings` redirects to `/login` requiring credential re-entry.
5. After re-entering credentials via the login form, the new request has full authentication. `fullyAuthenticated()` grants access if business policy also allows it.

**Never copy real cookies into bug reports or logs.** Anyone holding a stolen session cookie or remember-me cookie can use it as a bearer credential under certain conditions. Password changes, persistent token revocation, and cookie lifecycles must be designed around product risk.

## 7. Designing access policies by sensitivity level

| Feature type | Suggested rule | Reason |
| --- | --- | --- |
| About pages, terms, login page | `permitAll()` | No identity required; login page may need to remain open for remembered users |
| Welcome page for guests without an account | `anonymous()` (if truly needed) | Shown only to guests, not a mandatory login route |
| Remember-me recognition page | `rememberMe()` (rarely used) | Reflects only state restored via cookie |
| Viewing profile, low-sensitivity order lists | `authenticated()` if threat model permits | Remember-me may suffice for read UX; still enforce resource ownership |
| Changing password/email or security settings | `fullyAuthenticated()` | A leaked long-lived cookie must not alter sensitive security state |
| Approving payments, exporting secrets, granting admin roles | `fullyAuthenticated()` **and** appropriate role/permission/MFA/step-up | Full login is necessary yet insufficient for high-risk operations |

**Roles do not substitute for freshness.** A restored `RememberMeAuthenticationToken` can reload `ROLE_ADMIN` from the user store. `hasRole("ADMIN")` alone does not stop it. Use composite `AuthorizationManagers.allOf(fullyAuthenticated(), hasRole(...))` or an equivalent policy. For ultra-sensitive actions, full auth in Spring Security still does not prove “password verified within 5 minutes” or “MFA completed”: you need explicit timestamp/assurance proof, separate challenges, or step-up.

**API note:** Browsers using cookies face CSRF risks; `rememberMe()` suits form login/session browsers. Stateless bearer JWT/OAuth2 resource servers have a different trust model; do not use `fullyAuthenticated()` as a proxy for MFA verification or token age in a JWT API without defining an explicit policy.

## 8. Classic mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| `if (authentication.isAuthenticated())` treated as a real user | `AnonymousAuthenticationToken` can also have flag true | Use `AuthenticationTrustResolver` or Spring Security authorization DSL |
| Protecting password changes with `authenticated()` | Remember-me can pass through | Use `fullyAuthenticated()` and add step-up if needed |
| Using `hasRole("ADMIN")` as the sole condition for critical actions | A remembered admin still gets authorities reloaded | Combine full login and role; add MFA/freshness policy |
| Assuming having a remember-me cookie means full login | Cookie only proves re-identification under remember-me | Distinguish `RememberMeAuthenticationToken` from full tokens |
| Treating `.rememberMe()` as “at least remember-me” | This rule matches only the remember-me state, rejecting full login | Use `.authenticated()` when you want to accept both |
| Treating `.anonymous()` like `permitAll()` | Full/remembered users get denied on anonymous-only routes | Use `permitAll()` for public pages open to everyone |
| Disabling CSRF because remember-me cookies exist | Browsers send cookies automatically, enabling forged requests | Keep CSRF for cookie/session actions |
| Clearing cookie on logout and concluding a stolen token is revoked | Copied hash-based remember-me tokens can remain valid | Use short TTLs, change password/key when needed; persistent token store for revocation |
| Putting remember-me secret key in a public repository | Attackers can forge/inspect tokens | Secret manager/env, rotation, and least-privilege access |
| Using `@WithMockUser` to “test remember-me” | Skips filter cookie issuance and autoLogin | Perform real login in MockMvc then test cookie without session |
| Reusing `JSESSIONID` in tests and claiming remember-me activated | Authentication is still read from the full session | Send a new request without session, carrying only the remember-me cookie |
| Losing session while retaining remember-me cookie unexplained in UX | User thinks they logged out completely while still auto-recognized | Align logout/revocation and explain remembered state clearly |

## 9. Cookie security and login lifecycle

1. **HTTPS and cookie flags:** Use `Secure` in production, `HttpOnly` to limit JavaScript access, and `SameSite` matching valid cross-site flows; keep domain/path as narrow as possible. Flags reduce risk but do not replace XSS/CSRF defenses.
2. **Reasonable lifetime:** remember-me normally outlives sessions; enforce TTLs, monitoring, cookie expiration, and invalidation on password change, account lock, or privilege removal. Never let remember-me last forever.
3. **Revocability:** simple hash-based tokens fit demos or low-risk cases, yet lack server-side per-token revocation like a persistent store. If the product needs device lists or single-device revocation, store token state properly.
4. **Login/re-authentication:** rely on remember-me only where permitted. For `fullyAuthenticated()`, form login must perform interactive re-authentication; never fake a redirect or switch token types by manually flipping an authenticated flag.
5. **MFA/step-up:** for high-risk transactions, perform additional verification (fresh password entry, passkey, OTP/phishing-resistant MFA per policy) and record proof/freshness accurately. `fullyAuthenticated()` only separates anonymous/remember-me/full inside Spring Security; it does not hold full assurance evidence.
6. **Session fixation:** if remember-me creates a new session during autoLogin, session fixation/lifecycle concerns must still be managed properly by Spring Security. Never let a remember-me cookie open sensitive admin endpoints directly.
7. **Account authority changes:** reloading `UserDetails` can refresh authorities when remember-me is used, yet request authorization policies must always re-check verified data and proper rules. Never trust roles sent by the client.
8. **Error handling:** expired cookies, bad signatures, nonexistent users, or disabled users must result in no authentication restoration; the UI should not display error messages leaking excessive account or token details.

## 10. QA checklist

- [ ] Correctly distinguish anonymous, remember-me, and full login; do not rely on `Authentication.isAuthenticated()` alone.
- [ ] Understand `authenticated()` accepts remember-me + full, while `fullyAuthenticated()` accepts only full.
- [ ] Understand `anonymous()` and `rememberMe()` are **specific-state** policies, not aliases for `permitAll()` or `authenticated()`.
- [ ] Remember-me cookies are issued only on user opt-in (unless policy intentionally enables `alwaysRemember`).
- [ ] While a full-login session remains, requests are classified full; when only a valid cookie is present, requests are classified remember-me.
- [ ] Informational endpoints may use `authenticated()`; endpoints modifying security settings require `fullyAuthenticated()`.
- [ ] Sensitive admin endpoints verify **both** full login and role/permission; high-risk ones also require MFA/step-up.
- [ ] Test that missing/corrupted cookies do not yield a logged-in account.
- [ ] CSRF continues protecting form POSTs, logout, and sensitive cookie-based actions.
- [ ] Remember-me secrets are managed safely, cookies have proper flags and TTL, and revocation and auditing processes exist.
- [ ] MockMvc tests verify cookie issuance, authentication recovery **without the old session**, and 302/403 per policy.
- [ ] Additional verification in a real browser covering HTTPS, session expiry, logout, and cookie attributes.
- [ ] Do not confuse Spring Security Remember-me with stateless JWTs or proof of completed MFA.

### References

- [Spring Security 6.5 — Remember-Me Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/rememberme.html)
- [Spring Security 6.5 — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html)
- [Spring Security 6.5 — Authorization Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/architecture.html)
- [Spring Security 6.5 — AuthenticationTrustResolver](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/AuthenticationTrustResolver.html)
- [Spring Security 6.5 — AuthenticatedAuthorizationManager](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/AuthenticatedAuthorizationManager.html)
- [Spring Security 6.5 — RememberMeConfigurer](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/annotation/web/configurers/RememberMeConfigurer.html)
- [Spring Security 6.5 — MockMvc Security Setup](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/setup.html)
- [Spring Security 6.5 — Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html)
