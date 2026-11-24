# Testing Remember-Me: Valid, Expired, Tampered Cookies, and Logout

## 1. Lesson goal and scope

**Remember-me** in Spring Security lets the browser re-identify a user after a prior interactive login session has been lost or expired, via a **cookie stored longer than the HTTP session**. It is an **automatic re-authentication** mechanism, not a property that makes the `JSESSIONID` session last forever, nor is it an OAuth refresh token or a WebAuthn passkey.

In the **Spring Security - authentication** module, **Login Testing** group, the goal of this lesson is to **write and understand Remember-me tests** for these cases:

1. User performs interactive login **without opting in** to remember-me → no persistent-login cookie is issued.
2. User **opts in** to remember-me → a cookie is issued; a new request without the old session can still authenticate.
3. Valid cookie but **expired** → rejected, no privileged session is created.
4. Cookie with **tampered contents or signature** → rejected; never treat a readable Base64 string as trustworthy.
5. **Persistent series/token** cookie tampered or replayed after rotation → mismatch detected and token store handled per Spring Security behavior.
6. **Logout** → clears browser cookie, ends HTTP session, and revokes persistent tokens under defined conditions; explicitly tests stale cookie copies.
7. How password changes, disabled accounts, signing key rotation, deleting database tokens, and cookie flags affect behavior.
8. Combining **service unit tests**, **SecurityFilterChain/MockMvc integration tests**, and multi-node/real HTTP testing.
9. Distinguishing a `RememberMeAuthenticationToken` accepted by `authenticated()` from **fully authenticated** to protect sensitive operations.

**Example baseline:** Java 17+, Spring Boot 3.5.x, Spring Security 6.5.x, JUnit Jupiter 5, Spring Test/MockMvc. Content focuses on **Servlet security**: `HttpSecurity`, `RememberMeAuthenticationFilter`, `RememberMeServices`, `TokenBasedRememberMeServices`, and `PersistentTokenBasedRememberMeServices`. If the app uses WebFlux, see the comparison notes; do not copy Servlet code verbatim into a reactive chain.

> Password/key/token values in the code are all **test fixtures**, not passwords or secrets used in production. Never copy `{noop}` or test signing keys into real applications.

## 2. Where does Remember-me sit in the login process?

```text
                                 INTERACTIVE REQUEST
User -> POST /login (username, password, remember-me=on, CSRF)
                   |
                   v
           UsernamePasswordAuthenticationFilter
                   |
                   v
           AuthenticationManager/Provider verifies password
                   |
                   +-- FAIL -> RememberMeServices.loginFail(...)
                   |
                   +-- SUCCESS
                          |
                          v
                   RememberMeServices.loginSuccess(...)
                          |
                   if "remember-me" selected:
                     Set-Cookie: remember-me=...
                          |
                          v
                   normal browser login session

                         SUBSEQUENT REQUEST
Browser -> GET /private, carrying no authenticated session
           Cookie: remember-me=...
                   |
                   v
           RememberMeAuthenticationFilter
                   |
                   v
           RememberMeServices.autoLogin(request, response)
                   |
                   +-- null: no auto-auth; per URL -> login/401
                   |
                   +-- RememberMeAuthenticationToken
                              |
                              v
                    AuthenticationManager verifies token
                              |
                              v
                    SecurityContext for request
                              |
                              v
                    Authorization: authenticated() or fullyAuthenticated()?
```

Easily confused boundaries:

- `UsernamePasswordAuthenticationFilter` or an interactive authentication filter notifies the service of **loginSuccess/loginFail**.
- `RememberMeAuthenticationFilter` tries **autoLogin** when there is not yet an `Authentication` in `SecurityContext`.
- `RememberMeAuthenticationProvider` in `AuthenticationManager` verifies the application key of `RememberMeAuthenticationToken`. This **is not** a repeated password check like a form POST.
- `HttpSession` can coexist alongside the remember-me cookie; when testing cookie effect, you must **omit the old session** to avoid false positives.
- Authentication created via remember-me is normally considered **remember-me**, not fully authenticated per Spring Security's trust resolver.
- A valid cookie alone is insufficient if the account is disabled/locked or access requires step-up.

Per Spring Security 6.5, `RememberMeServices` has these methods:

```java
Authentication autoLogin(
        HttpServletRequest request,
        HttpServletResponse response);

void loginSuccess(
        HttpServletRequest request,
        HttpServletResponse response,
        Authentication successfulAuthentication);

void loginFail(
        HttpServletRequest request,
        HttpServletResponse response);
```

These functions are **abbreviated interface signatures for learning**, requiring imports for `org.springframework.security.web.authentication.RememberMeServices` and Spring/Servlet types. `autoLogin` returns an `Authentication` or `null`; an invalid cookie is typically rejected and instructed to be deleted on the response.

## 3. Two main implementations and testing differences

| Property | `TokenBasedRememberMeServices` | `PersistentTokenBasedRememberMeServices` |
| --- | --- | --- |
| Cookie verification basis | Hash signature over username, expiry timestamp, password hash, and application key | `series` + `token`; server looks up record via `PersistentTokenRepository` |
| Separate server-side store | Not required | Requires a persistent token repository |
| Can revoke individual devices/token series? | No per-series store lookup; typically requires changing password/key or custom design | Can delete row/series in custom store; default API `removeUserTokens(username)` deletes all series of user |
| Cookie still valid after password change? | **No**, because signature uses current password | Not auto-revoked solely by password change; must actively manage persistent records |
| Auto-rotates token after successful auto-login | No series/token rotation model | **Yes**: same series, new token value |
| Old cookie after token rotation | Not applicable | Series/token mismatch: suspected-theft response |
| Expiration | Verifies signed expiry timestamp | Checks `last_used` date + configured validity |
| Logout | Clears cookie; copied old cookie may remain valid | Clears cookie and calls **removeUserTokens** when `Authentication != null` |
| Fast testing | No database needed | `InMemoryTokenRepositoryImpl` for unit tests; JDBC for integration |
| Multi-node usage | Needs consistent signing key and UserDetails/password state | Needs shared repository + race/rotation handling |

**Terminology note:** the name "persistent token" does not mean Spring Session or an OAuth refresh token. It is a data store dedicated to **persistent browser logins**. Do not use it to call REST APIs like an OAuth Bearer token.

### 3.1. Why a signed cookie is not an "encrypted cookie"

`TokenBasedRememberMeServices` uses a Base64 cookie containing fields readable upon decoding, along with a verification signature/hash:

```text
Base64(
  username : expiryTimeMillis : algorithmName : signatureHex
)
```

`signatureHex` depends on username, expiration time, password from `UserDetails`, and the application's secret key. **Base64 does not encrypt secrets**; it is merely data encoding. A client can alter any value, yet it will not be accepted without generating a valid signature.

In Spring Security 6.5, the default signing algorithm is **SHA-256**, with an algorithm identifier to support upgrades/matching; do not write tests relying on old assumptions of MD5 without an algorithm field. Never compare Base64 strings yourself to decide cookie validity.

### 3.2. Why a persistent cookie checks more than just a timestamp

A persistent cookie is encoded from:

```text
Base64(series : token)
```

The `persistent_logins` record contains username, series, token, and last-used timestamp. When a cookie arrives:

1. Look up the record by `series`.
2. Not found → no auto-login.
3. Series exists but token value differs → suspected replay/cookie theft: deletes **all persistent series of the user** under the default implementation and rejects.
4. Token matches but record has expired → rejects; the record **is not auto-deleted** merely during expiry checks.
5. Token is valid → rotates token value, updates last-used date, writes new cookie, then loads `UserDetails`.

Rotation improves replay detection, yet **two concurrent requests from the same browser with the same cookie** can race and trigger theft detection unless storage/transactions/response timing are designed carefully. Do not treat `InMemoryTokenRepositoryImpl` as proof of distributed concurrency safety; load/multi-node test with a real database before production.

## 4. Designing the right test matrix before writing tests

A minimal matrix:

| ID | Input data | Observed expectation |
| --- | --- | --- |
| R01 | Interactive login right password, **no opt-in** | No new remember-me cookie issued |
| R02 | Interactive login right password, `remember-me=on` | Cookie issued with right Max-Age/security settings |
| R03 | Valid cookie, **no `JSESSIONID` sent** | Auto-login succeeds via remember-me |
| R04 | Missing or empty cookie | No auto-login |
| R05 | Signed cookie with one signature character altered | No auto-login; response instructs cookie deletion |
| R06 | Signed cookie with past expiry yet valid signature | No auto-login |
| R07 | Valid signed cookie after password hash change | No auto-login |
| R08 | Signed cookie after logout, browser deleted cookie | Browser can no longer send cookie |
| R09 | **Copy** of signed cookie from before logout | May still be valid if password/key unchanged; needs additional policy |
| R10 | Valid persistent cookie, first reuse | Auto-login, updates new token value |
| R11 | Persistent cookie with unknown/missing series | No auto-login |
| R12 | Persistent cookie right series/wrong token | No auto-login; `removeUserTokens(user)` |
| R13 | Old persistent cookie after a successful rotation | Treated as mismatch/replay; may delete series |
| R14 | Persistent row with overly old last-used | No auto-login; record remains until cleanup |
| R15 | Persistent cookie after logout with `Authentication != null` | Client cookie cleared; user's server token records deleted |
| R16 | Calling `service.logout` with `Authentication == null` | Cookie cleared; **must not assume** server records were deleted |
| R17 | Disabled/locked/removed account | Auto-login grants no access |
| R18 | `authenticated()` vs `fullyAuthenticated()` | Remember-me passes the first rule yet is blocked by the second |
| R19 | Custom cookie Secure/HttpOnly/SameSite | Flags match HTTPS/browser contract |
| R20 | Missing/invalid logout CSRF | No unauthorized logout side effects |
| R21 | Cookie-less API client / stateless endpoint | Does not rely on remember-me to open API access outside policy |
| R22 | Multiple replicas and shared storage | No conflicts over keys/store/rotation |

**Key criterion:** do not assert only HTTP 200/302. Prove **why** it succeeded or failed: the request has no session, the cookie is genuinely issued/read/cleared, the principal is remember-me, the persistent token store is updated/revoked, and authorization branches allow/deny properly.

## 5. Configuring Spring Security Servlet for testing

In a **Spring Boot 3.x Java 17+ project** using Gradle Groovy and an appropriate Spring Boot plugin/BOM:

```groovy
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

`spring-boot-starter-test` provides JUnit Jupiter and Spring Test; `spring-security-test` provides MockMvc helpers and Spring Security test support. For JDBC persistent tokens, add `spring-boot-starter-jdbc` and the appropriate driver.

### 5.1. Form login + opt-in remember-me

```java
// Snippet inside a SecurityFilterChain bean; not a standalone file.
@Bean
SecurityFilterChain security(HttpSecurity http,
        UserDetailsService userDetailsService) throws Exception {
    return http
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/", "/error").permitAll()
                    .requestMatchers("/sensitive").fullyAuthenticated()
                    .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .rememberMe(remember -> remember
                    .key(rememberKey)
                    .userDetailsService(userDetailsService)
                    .rememberMeParameter("remember-me")
                    .tokenValiditySeconds(7 * 24 * 60 * 60))
            .build();
}
```

Assume `rememberKey` is a secret string injected from configuration. Never hardcode it in production sources. `rememberMeParameter("remember-me")` matches the checkbox/field name in the login POST request. If the user does not opt in and you do **not** set `alwaysRemember(true)`, the framework issues no new remember-me cookie.

Note that the security chain above uses form login/HTTP sessions. When testing remember-me, **do not** reuse the old HTTP session and attribute a 200 result to the cookie.

### 5.2. Cookie configuration

Commonly needed options:

- Default name `remember-me`; configurable via `rememberMeCookieName(...)` on the DSL or `setCookieName(...)` on the service.
- `HttpOnly` so JavaScript cannot read the token; default `AbstractRememberMeServices` sets `HttpOnly`.
- `Secure` when using HTTPS; `Secure` should be mandatory in production behind a TLS proxy.
- `SameSite=Lax` or `Strict` per UX/CSRF policy and cross-site navigation needs. Spring Security 6.5 provides `AbstractRememberMeServices.setCookieCustomizer(...)` if you create the service bean explicitly.
- `Path`/`Domain` matching endpoints that use the cookie and the logout endpoint; mismatched path/domain can leave the browser holding the old cookie.
- `Max-Age` compatible with server-side TTL. A browser may delete a cookie early, yet if it still sends an expired cookie, **the server must reject it**.
- The cookie never contains a plaintext password; tokens must never be written to logs, metrics, URL queries, or screenshots.

Customization example in a configuration class for a service you instantiate:

```java
rememberMeServices.setUseSecureCookie(true);
rememberMeServices.setCookieCustomizer(cookie -> {
    cookie.setHttpOnly(true);
    cookie.setAttribute("SameSite", "Lax");
});
```

This is a **snippet** where `rememberMeServices` is an `AbstractRememberMeServices`; requires a Servlet version supporting cookie attributes. When using a custom service bean, register it in the DSL with `.rememberMeServices(rememberMeServices)` and keep the signing key and `UserDetailsService` consistent across nodes.

## 6. Complete Spring Boot demo to run MockMvc

File `src/main/java/demo/remember/RememberMeDemoApplication.java`:

```java
package demo.remember;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class RememberMeDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(RememberMeDemoApplication.class, args);
    }

    @Bean
    UserDetailsService users() {
        UserDetails alice = User.withUsername("alice")
                .password("{noop}demo-password")
                .roles("USER")
                .build();
        return new InMemoryUserDetailsManager(alice);
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http,
            UserDetailsService users,
            @Value("${app.remember.key}") String key) throws Exception {

        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/error").permitAll()
                        .requestMatchers("/sensitive").fullyAuthenticated()
                        .anyRequest().authenticated())
                .formLogin(Customizer.withDefaults())
                .rememberMe(remember -> remember
                        .key(key)
                        .userDetailsService(users)
                        .rememberMeParameter("remember-me")
                        .tokenValiditySeconds(86400))
                .build();
    }

    @RestController
    static class Pages {
        @GetMapping("/")
        String home() {
            return "Public";
        }

        @GetMapping("/private")
        String privatePage(Authentication authentication) {
            return "Hello, " + authentication.getName();
        }

        @GetMapping("/sensitive")
        String sensitive() {
            return "Recent login required";
        }
    }
}
```

File `src/main/resources/application.yml`:

```yaml
server:
  port: 8080
app:
  remember:
    key: "${REMEMBER_ME_KEY}"
```

Locally, supply `REMEMBER_ME_KEY` via an environment variable; in unit/integration tests you can supply a dedicated test key via `@SpringBootTest(properties=...)`. The key must be secret, stable across restarts, and **identical across nodes**; if each node uses a different random key, cookies issued on node A will be rejected on node B. Rotating the key intentionally can invalidate all old signed cookies.

The `{noop}demo-password` password is **only** for demo tests. In production use a proper `PasswordEncoder`, TLS, rate limiting, account status/lockout, and auditing. Remember-me is not a substitute for MFA/passkeys when resources require high assurance.

### 6.1. Running the demo

```bash
./gradlew bootRun
```

Windows PowerShell/cmd depending on project may use `gradlew.bat bootRun`. Visit `http://localhost:8080/login`, enter username `alice` and password `demo-password`. The default login page can show a remember-me checkbox once the feature is enabled. With a custom-designed form, the field must be named `remember-me`, following Spring Security CSRF rules.

Never print remember-me cookies or signing key values to stdout. When using DevTools and testing over local HTTP, the cookie is not `Secure`; **never** carry local HTTP configuration into production.

## 7. MockMvc: verifying login with/without opt-in and cookies on new requests

Save file `src/test/java/demo/remember/RememberMeWebFlowTest.java`:

```java
package demo.remember;

import java.util.Arrays;

import jakarta.servlet.http.Cookie;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.*;

@SpringBootTest(properties =
        "app.remember.key=local-test-signing-key-not-for-production")
@AutoConfigureMockMvc
class RememberMeWebFlowTest {

    @Autowired
    MockMvc mvc;

    private MvcResult login(boolean optIn) throws Exception {
        var request = post("/login")
                .with(csrf())
                .param("username", "alice")
                .param("password", "demo-password");

        if (optIn) {
            request.param("remember-me", "on");
        }

        return mvc.perform(request)
                .andExpect(status().is3xxRedirection())
                .andReturn();
    }

    private static Cookie rememberCookie(MvcResult result) {
        return Arrays.stream(result.getResponse().getCookies())
                .filter(c -> c.getName().equals("remember-me"))
                .findFirst()
                .orElseThrow();
    }

    @Test
    void optOutDoesNotIssueRememberMeCookie() throws Exception {
        MvcResult loggedIn = login(false);

        boolean issued = Arrays.stream(
                loggedIn.getResponse().getCookies())
                .anyMatch(c -> c.getName().equals("remember-me")
                        && c.getMaxAge() > 0);

        assertFalse(issued);
    }

    @Test
    void optedInCookieReauthenticatesWithoutOriginalSession()
            throws Exception {
        Cookie cookie = rememberCookie(login(true));

        // Intentionally do NOT pass MockHttpSession/JSESSIONID from login.
        mvc.perform(get("/private").cookie(cookie))
                .andExpect(status().isOk())
                .andExpect(content().string("Hello, alice"));
    }

    @Test
    void rememberMeIsNotFullyAuthenticated() throws Exception {
        Cookie cookie = rememberCookie(login(true));

        // authenticated() allows remember-me; fullyAuthenticated()
        // requires stronger authentication than remember-me.
        mvc.perform(get("/sensitive").cookie(cookie))
                .andExpect(status().is3xxRedirection());
    }

    @Test
    void logoutWithSessionClearsCookie() throws Exception {
        MvcResult loggedIn = login(true);
        Cookie cookie = rememberCookie(loggedIn);
        MockHttpSession session = (MockHttpSession)
                loggedIn.getRequest().getSession(false);

        assertNotNull(session);

        MvcResult logout = mvc.perform(post("/logout")
                        .with(csrf())
                        .session(session)
                        .cookie(cookie))
                .andExpect(status().is3xxRedirection())
                .andReturn();

        Cookie cleared = Arrays.stream(
                logout.getResponse().getCookies())
                .filter(c -> c.getName().equals("remember-me"))
                .findFirst()
                .orElseThrow();

        assertEquals(0, cleared.getMaxAge());
    }
}
```

Run:

```bash
./gradlew test --tests demo.remember.RememberMeWebFlowTest
```

Expected: **4 tests PASS** when the project uses the exact Servlet stack/configuration from the demo. There is no fixed JUnit stdout: Gradle may print different summaries; the test report simply needs **4 tests, 0 failed**.

### 7.1. What this test genuinely proves

- Form login with the right password and opt-in can issue a remember-me cookie.
- Not opting in does not issue a **new** remember-me cookie.
- A request **carrying no HttpSession from login** yet carrying a valid remember-me cookie can still access `/private`.
- `fullyAuthenticated()` differs from `authenticated()`: requests using only remember-me are required to authenticate more strongly.
- Logout with an authenticated session clears the cookie on the response.

### 7.2. What this test does not prove

- Does not test tampered or expired cookies: to avoid waiting for real time, use the unit tests in subsequent sections.
- Does not prove the real browser deleted the cookie because `MockMvc` simulates HTTP; verifying browser persistence/cookie attributes requires E2E tests.
- Does not prove **a stolen cookie copy** becomes invalid after logout. With signed cookies, by default it may remain accepted until expiry if password/key do not change.
- Does not test `Secure` cookies over local HTTP; production HTTPS needs dedicated tests.
- Does not prove `MockMvc.with(user("alice"))` passed through `RememberMeAuthenticationFilter`: the demo intentionally uses a real cookie generated by login, not a fake principal.

## 8. Unit testing TokenBasedRememberMeServices: no opt-in, valid, tampered signature, expired

`TokenBasedRememberMeServices` can be tested **without booting Spring Boot/an HTTP server** using `MockHttpServletRequest`, `MockHttpServletResponse`, and an `InMemoryUserDetailsManager`. Invoking `loginSuccess` and `autoLogin` directly tests the real cookie algorithm, not just Mockito stubs.

File `src/test/java/demo/remember/SignedRememberMeServiceTest.java`:

```java
package demo.remember;

import java.time.Instant;
import java.util.Arrays;

import jakarta.servlet.http.Cookie;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.authentication.RememberMeAuthenticationToken;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.authentication.rememberme
        .TokenBasedRememberMeServices;
import org.springframework.security.web.authentication.rememberme
        .TokenBasedRememberMeServices.RememberMeTokenAlgorithm;

import static org.junit.jupiter.api.Assertions.*;

class SignedRememberMeServiceTest {

    private InMemoryUserDetailsManager users;
    private TestableSignedService service;

    static final class TestableSignedService
            extends TokenBasedRememberMeServices {

        TestableSignedService(InMemoryUserDetailsManager users) {
            super("unit-test-key", users, RememberMeTokenAlgorithm.SHA256);
        }

        String[] parts(Cookie cookie) {
            return decodeCookie(cookie.getValue());
        }

        Cookie pack(String[] parts) {
            return new Cookie("remember-me", encodeCookie(parts));
        }

        Cookie expiredButCorrectlySigned(String username,
                String storedPassword) {
            long expiry = Instant.parse(
                    "2000-01-01T00:00:00Z").toEpochMilli();
            String signature = makeTokenSignature(
                    expiry, username, storedPassword,
                    RememberMeTokenAlgorithm.SHA256);

            return pack(new String[] {
                    username,
                    Long.toString(expiry),
                    "SHA256",
                    signature
            });
        }
    }

    @BeforeEach
    void setup() {
        users = new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password("{noop}demo-password")
                        .roles("USER")
                        .build());

        service = new TestableSignedService(users);
        service.setTokenValiditySeconds(3600);
        service.afterPropertiesSet();
    }

    private Authentication authenticatedAlice() {
        UserDetails user = users.loadUserByUsername("alice");
        return UsernamePasswordAuthenticationToken.authenticated(
                user, null, user.getAuthorities());
    }

    private Cookie issue() {
        MockHttpServletRequest login =
                new MockHttpServletRequest("POST", "/login");
        login.addParameter("remember-me", "on");
        MockHttpServletResponse response =
                new MockHttpServletResponse();
        service.loginSuccess(login, response, authenticatedAlice());

        return Arrays.stream(response.getCookies())
                .filter(c -> c.getName().equals("remember-me"))
                .findFirst()
                .orElseThrow();
    }

    private MockHttpServletRequest withCookie(Cookie cookie) {
        MockHttpServletRequest request =
                new MockHttpServletRequest("GET", "/private");
        request.setCookies(cookie);
        return request;
    }

    private static Cookie cancellation(MockHttpServletResponse response) {
        return Arrays.stream(response.getCookies())
                .filter(c -> c.getName().equals("remember-me"))
                .findFirst()
                .orElseThrow();
    }

    @Test
    void noOptInMeansNoPersistentLoginCookie() {
        MockHttpServletResponse response =
                new MockHttpServletResponse();

        service.loginSuccess(
                new MockHttpServletRequest("POST", "/login"),
                response, authenticatedAlice());

        assertEquals(0, response.getCookies().length);
    }

    @Test
    void validCookieAutoLogsInAlice() {
        Cookie cookie = issue();

        Authentication result = service.autoLogin(
                withCookie(cookie), new MockHttpServletResponse());

        assertNotNull(result);
        assertInstanceOf(RememberMeAuthenticationToken.class, result);
        assertEquals("alice", result.getName());
        assertTrue(result.isAuthenticated());
    }

    @Test
    void modifiedSignatureIsRejectedAndCookieCleared() {
        Cookie original = issue();
        String[] parts = service.parts(original);
        String signature = parts[3];

        // Deterministically change one signature character while keeping valid Base64 format.
        parts[3] = (signature.charAt(0) == '0' ? "1" : "0")
                + signature.substring(1);
        Cookie tampered = service.pack(parts);
        MockHttpServletResponse response =
                new MockHttpServletResponse();

        Authentication result = service.autoLogin(
                withCookie(tampered), response);

        assertNull(result);
        assertEquals(0, cancellation(response).getMaxAge());
    }

    @Test
    void correctlySignedExpiredCookieIsRejected() {
        String storedPassword =
                users.loadUserByUsername("alice").getPassword();
        Cookie expired = service.expiredButCorrectlySigned(
                "alice", storedPassword);

        MockHttpServletResponse response =
                new MockHttpServletResponse();
        Authentication result = service.autoLogin(
                withCookie(expired), response);

        assertNull(result);
        assertEquals(0, cancellation(response).getMaxAge());
    }

    @Test
    void changingPasswordInvalidatesSignedCookie() {
        Cookie oldCookie = issue();
        users.updateUser(User.withUsername("alice")
                .password("{noop}new-password")
                .roles("USER")
                .build());

        Authentication result = service.autoLogin(
                withCookie(oldCookie), new MockHttpServletResponse());

        assertNull(result);
    }

    @Test
    void disabledUserCannotAutoLoginEvenWithValidSignature() {
        Cookie oldCookie = issue();
        users.updateUser(User.withUsername("alice")
                .password("{noop}demo-password")
                .roles("USER")
                .disabled(true)
                .build());

        Authentication result = service.autoLogin(
                withCookie(oldCookie), new MockHttpServletResponse());

        assertNull(result);
    }

    @Test
    void logoutClearsCookieButCannotRevokeCapturedSignedCopy() {
        Cookie capturedCopy = issue();
        MockHttpServletResponse logoutResponse =
                new MockHttpServletResponse();

        service.logout(withCookie(capturedCopy),
                logoutResponse, authenticatedAlice());

        assertEquals(0, cancellation(logoutResponse).getMaxAge());

        // Simulates an attacker still holding an earlier cookie copy.
        Authentication replay = service.autoLogin(
                withCookie(capturedCopy), new MockHttpServletResponse());

        assertNotNull(replay);
        assertEquals("alice", replay.getName());
    }
}
```

Run:

```bash
./gradlew test --tests demo.remember.SignedRememberMeServiceTest
```

Expected: **7 tests PASS**. The expiration test uses a test subclass to access **protected** `makeTokenSignature(...)`/`encodeCookie(...)` from the real implementation; avoid `Thread.sleep(...)`, and never fake expiry using a token with an invalid signature and call it an "expiry test".

### 8.1. Explaining the "logged out yet captured copy still valid" test

It intentionally illustrates a **security limitation** of signed/stateless remember-me. Logout typically only sends an expired cookie to the browser. The server has no per-token series to track and revoke every previously captured cookie copy. If the old password hash and signing key remain unchanged, **the old cookie copy** can still be used until expiry. For a suspected compromised account:

- Changing the password makes the old cookie's signature fail in `TokenBasedRememberMeServices`.
- Rotating the application remember-me signing key invalidates cookies signed under the old key, typically affecting **all** users of that key.
- You can switch to a persistent token store to support server-side revocation, or disable remember-me on sensitive accounts.
- Destroying the HTTP session alone is insufficient if the old cookie can recreate authentication on the next request.

Never claim "logout invalidates every session/token ever issued" merely because a test checks `Max-Age=0`.

## 9. Unit testing PersistentTokenBasedRememberMeServices: rotation, expiry, token tampering, and logout

The persistent implementation supports lifecycle testing with **`InMemoryTokenRepositoryImpl`**. That is a **test-only** repository, not a multi-instance production choice.

A persistent cookie has two parts (`series` and `token`); tests should use the class's own encode/decode via a small test subclass rather than guessing Base64 formatting. Be especially sure to test **rotation** when a valid token is used: series stays the same, token value changes.

File `src/test/java/demo/remember/PersistentRememberMeServiceTest.java`:

```java
package demo.remember;

import java.util.Arrays;
import java.util.Date;

import jakarta.servlet.http.Cookie;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.authentication.RememberMeAuthenticationToken;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.authentication.rememberme
        .InMemoryTokenRepositoryImpl;
import org.springframework.security.web.authentication.rememberme
        .PersistentTokenBasedRememberMeServices;
import org.springframework.security.web.authentication.rememberme
        .PersistentTokenRepository;

import static org.junit.jupiter.api.Assertions.*;

class PersistentRememberMeServiceTest {

    private InMemoryUserDetailsManager users;
    private InMemoryTokenRepositoryImpl store;
    private TestablePersistentService service;

    static final class TestablePersistentService
            extends PersistentTokenBasedRememberMeServices {

        TestablePersistentService(InMemoryUserDetailsManager users,
                PersistentTokenRepository store) {
            super("persistent-test-key", users, store);
        }

        String[] parts(Cookie cookie) {
            return decodeCookie(cookie.getValue());
        }

        Cookie pack(String[] parts) {
            return new Cookie("remember-me", encodeCookie(parts));
        }
    }

    @BeforeEach
    void setup() {
        users = new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password("{noop}demo-password")
                        .roles("USER")
                        .build());

        store = new InMemoryTokenRepositoryImpl();
        service = new TestablePersistentService(users, store);
        service.setTokenValiditySeconds(3600);
        service.afterPropertiesSet();
    }

    private Authentication authenticatedAlice() {
        UserDetails user = users.loadUserByUsername("alice");
        return UsernamePasswordAuthenticationToken.authenticated(
                user, null, user.getAuthorities());
    }

    private MockHttpServletRequest withCookie(Cookie cookie) {
        MockHttpServletRequest request =
                new MockHttpServletRequest("GET", "/private");
        request.setCookies(cookie);
        return request;
    }

    private static Cookie findCookie(MockHttpServletResponse response) {
        return Arrays.stream(response.getCookies())
                .filter(c -> c.getName().equals("remember-me"))
                .findFirst()
                .orElseThrow();
    }

    private Cookie issue() {
        MockHttpServletRequest login =
                new MockHttpServletRequest("POST", "/login");
        login.addParameter("remember-me", "on");

        MockHttpServletResponse response =
                new MockHttpServletResponse();
        service.loginSuccess(login, response, authenticatedAlice());

        return findCookie(response);
    }

    @Test
    void validPersistentCookieAuthenticatesAndRotates() {
        Cookie before = issue();
        String[] old = service.parts(before);

        MockHttpServletResponse response =
                new MockHttpServletResponse();
        Authentication result = service.autoLogin(
                withCookie(before), response);

        assertNotNull(result);
        assertInstanceOf(RememberMeAuthenticationToken.class, result);
        assertEquals("alice", result.getName());

        Cookie rotated = findCookie(response);
        String[] newer = service.parts(rotated);

        assertEquals(old[0], newer[0]);  // series unchanged
        assertNotEquals(old[1], newer[1]); // token rotated
        assertEquals(newer[1],
                store.getTokenForSeries(old[0]).getTokenValue());
    }

    @Test
    void modifiedTokenWithKnownSeriesRevokesUserTokens() {
        Cookie issued = issue();
        String[] parts = service.parts(issued);
        String series = parts[0];
        parts[1] = parts[1] + "-changed";

        Cookie tampered = service.pack(parts);
        MockHttpServletResponse response =
                new MockHttpServletResponse();

        assertNull(service.autoLogin(withCookie(tampered), response));
        assertEquals(0, findCookie(response).getMaxAge());

        // Spring Security handles mismatches via removeUserTokens(username).
        assertNull(store.getTokenForSeries(series));
    }

    @Test
    void replayingOldCookieAfterRotationTriggersRevocation() {
        Cookie original = issue();
        String series = service.parts(original)[0];

        // First use valid; token is rotated.
        assertNotNull(service.autoLogin(
                withCookie(original), new MockHttpServletResponse()));

        // Old copy no longer matches the current token of the same series.
        assertNull(service.autoLogin(
                withCookie(original), new MockHttpServletResponse()));
        assertNull(store.getTokenForSeries(series));
    }

    @Test
    void expiredPersistentRecordIsRejectedButNotAutoDeleted() {
        Cookie original = issue();
        String[] parts = service.parts(original);

        // No sleep; write last-used far in the past.
        store.updateToken(parts[0], parts[1], new Date(0L));

        MockHttpServletResponse response =
                new MockHttpServletResponse();
        assertNull(service.autoLogin(withCookie(original), response));
        assertEquals(0, findCookie(response).getMaxAge());

        // Expiry check does NOT auto-clean up the record.
        assertNotNull(store.getTokenForSeries(parts[0]));
    }

    @Test
    void unknownSeriesDoesNotAuthenticate() {
        Cookie issued = issue();
        String[] parts = service.parts(issued);
        parts[0] = "does-not-exist";

        assertNull(service.autoLogin(
                withCookie(service.pack(parts)),
                new MockHttpServletResponse()));
    }

    @Test
    void logoutWithPrincipalClearsCookieAndServerRecords() {
        Cookie original = issue();
        String series = service.parts(original)[0];
        MockHttpServletResponse response =
                new MockHttpServletResponse();

        service.logout(
                withCookie(original), response, authenticatedAlice());

        assertEquals(0, findCookie(response).getMaxAge());
        assertNull(store.getTokenForSeries(series));
        assertNull(service.autoLogin(
                withCookie(original), new MockHttpServletResponse()));
    }

    @Test
    void logoutWithoutPrincipalOnlyClearsBrowserCookie() {
        Cookie capturedCopy = issue();
        String series = service.parts(capturedCopy)[0];

        MockHttpServletResponse response =
                new MockHttpServletResponse();
        service.logout(withCookie(capturedCopy), response, null);

        assertEquals(0, findCookie(response).getMaxAge());

        // Default implementation calls removeUserTokens only if auth != null.
        assertNotNull(store.getTokenForSeries(series));

        // Copy can still be accepted if an attacker retains it.
        assertNotNull(service.autoLogin(
                withCookie(capturedCopy), new MockHttpServletResponse()));
    }
}
```

Run:

```bash
./gradlew test --tests demo.remember.PersistentRememberMeServiceTest
```

Expected: **7 tests PASS** when using the right Spring Security 6.5.x and test dependencies. No clock waiting is required because the expiry case changes `last_used` in the test repository. In a real application, "expired record still exists" is a storage cleanup problem, **not** proof that the token is still accepted.

### 9.1. Distinguishing series tampering from token tampering

- **Non-existent series**: lookup finds no record; this cannot identify which user's cookie was stolen, so there is no user for calling `removeUserTokens`.
- **Valid series yet wrong token value**: may be **an old replayed or tampered cookie**, and by default Spring Security calls `removeUserTokens(username)`, revoking all persistent remembered logins for the user.
- **Valid record yet expired**: rejected by TTL; the record may remain until scheduled cleanup.
- **Valid, unexpired record**: authentication is created, the store receives the new token, and the response issues the matching cookie.

For multi-device accounts, a mismatch can force multiple devices to log in again. You need UX/monitoring for suspected replay, without exposing series/token details in HTTP errors or logs.

## 10. Logout has three layers: cookie, session, server token

A user clicks Sign out. Minimum operations to consider:

```text
POST /logout (+ CSRF for browser session)
       |
       v
Spring Security LogoutFilter / LogoutHandlers
       |
       +--> SecurityContextLogoutHandler
       |       invalidates session and clears context
       |
       +--> RememberMeServices.logout(...)
       |       sends Set-Cookie remember-me=; Max-Age=0
       |       if persistent & authentication != null:
       |           removeUserTokens(authentication.getName())
       |
       +--> CsrfLogoutHandler / related handlers
       |
       v
LogoutSuccessHandler -> redirect/response
```

**Three independent states:**

1. **Browser cookie:** `Set-Cookie` with `Max-Age=0` tells the browser to drop the remember-me credential. To clear the cookie reliably, name, Path, Domain, Secure, and SameSite policies should match those used when issuing the cookie. MockMvc sees only the response; browser E2E verifies the actual cookie jar.
2. **HTTP session:** `JSESSIONID`/SecurityContext of the interactive login must be invalidated/cleared. Deleting the remember-me cookie does **not** prove the session was destroyed; and destroying the session does **not** automatically invalidate a stolen remember-me cookie copy.
3. **Persistent token record:** with `PersistentTokenBasedRememberMeServices`, `logout(..., authentication)` calls `removeUserTokens(username)` **only if authentication is non-null**. When null, default behavior only clears the client cookie.

### 10.1. Why does logout after session loss need a dedicated test?

Spring Security's `LogoutFilter` may execute before `RememberMeAuthenticationFilter` in the filter chain. If the user no longer has a session yet the browser still sends the remember-me cookie, by the time `LogoutFilter` runs there may be **no Authentication** restored yet. In that case, the persistent logout service may not know which user's token records to delete.

Never conclude a `POST /logout` call **always** revokes all persistent tokens merely from seeing HTTP 302 or `Max-Age=0`. To guarantee "logout and revoke server-side even without a session", you need a secure flow that verifies the cookie before revoking or an account-verified management endpoint; it must enforce CSRF and never let the client pick an arbitrary username to delete someone else's tokens.

**Never** solve this by decoding the cookie for a username and deleting all tokens: persistent cookies do not carry a username, and even if a signed cookie contains a username, reading an unverified string is not authorization to revoke anyone.

### 10.2. "Log out all devices" behavior

`PersistentTokenRepository.removeUserTokens(username)` can revoke all remember-me series **for `username`**. Yet it does not by default:

- Destroy all HTTP sessions in Redis/Spring Session.
- Revoke OAuth refresh tokens/access tokens at the Authorization Server.
- Destroy OP/IdP SSO sessions or passkeys on devices.
- Delete cookies stored in every browser; browsers clear them upon receiving their own responses, or the server rejects those cookies on future requests.

For a security incident, coordinate across multiple stores/devices and confirm enforcement on each component. If the requirement is merely "log out current device", deleting **all series of the user** may be broader than desired. Define UX and policy before relying on this default method.

## 11. Testing HTTP logout: CSRF, session, and redirect

In the `/login` demo with Spring Security CSRF enabled by default, logout is executed via **POST `/logout`** and a valid CSRF token:

```java
// MockMvc snippet in @SpringBootTest with MockMvc mvc:
mvc.perform(post("/logout")
        .with(csrf())
        .session(existingLoggedInSession))
    .andExpect(status().is3xxRedirection());
```

Test the request missing CSRF:

```java
// Snippet - logout must not occur when CSRF is required.
mvc.perform(post("/logout")
        .session(existingLoggedInSession))
    .andExpect(status().isForbidden());
```

In standard versions and configurations, `GET /logout` may render a confirmation page; it **is not equivalent** to state-mutating `POST /logout`. If you disable CSRF globally, default mappings can change; never disable CSRF just to make logout tests "pass easily".

When logout runs properly, additional assertions:

- The session was invalidated or `SecurityContext` was cleared per the handler.
- The response includes the remember-me cookie deletion with matching name/path and max age.
- For persistent flows with an authenticated account, repository records were deleted.
- Retry a **new request without the old session** carrying the pre-logout cookie copy to confirm whether the server accepts or rejects it.
- The client is not redirected to an external-domain URL via an untrusted query parameter.

## 12. Expiration: never use Thread.sleep and never confuse cookie Max-Age

### 12.1. Two kinds of time

- **Browser cookie Max-Age/Expires:** the browser decides how long to store/send the cookie.
- **Server-side token validity:** Spring Security checks the token/cookie expiration or last-used date in the persistent store.

A browser may stop sending a cookie past `Max-Age`, yet an attacker can **manually send the old cookie with an HTTP client**. Thus the server must enforce expiration rather than trusting the browser. Conversely, an early-deleted cookie does not mean the server token record has expired.

### 12.2. Deterministic tests

**Signed strategy:** The `TokenBasedRememberMeServices` test subclass in section 8 uses real `makeTokenSignature(...)` and a year-2000 expiry value. Independent of a machine clock running seconds fast or slow.

**Persistent strategy:** The repository test uses `Date(0)` for `last_used` on a valid record. With `tokenValiditySeconds=3600`, the record is unambiguously expired. No `Thread.sleep(3600000)` needed.

**Practice:** use an injectable `Clock` with custom time-aware components if you write services yourself; never mutate the global system clock for the whole JVM test suite. If business policy requires a 7-day TTL, separately test generated cookie `Max-Age=604800` and server-side expiry verification via test fixtures.

### 12.3. Boundary tests

Add tests at the thresholds:

1. Just before expiry → valid.
2. **Exactly at** expiry → behavior depends on the actual implementation's comparison operator; test your version's source rather than guessing `<` or `<=`.
3. Immediately after expiry → invalid.
4. Clock skew across nodes; millisecond vs. second expiry timestamps.
5. Token rotated near expiry: persistent tokens can extend based on **last-used**, whereas signed expiry is typically fixed from interactive login.
6. Browser keeps sending a cookie due to a skewed client clock: the server must remain the authoritative source for expiration.

**Do not** treat persistent `last_used` as a fixed issuance timestamp. Token rotation can extend remembered logins per policy, unless the system adds a separate **absolute maximum lifetime**.

## 13. Tampered tokens: four tampering groups to distinguish

| Tamper | Signed cookie | Persistent cookie |
| --- | --- | --- |
| Truncate/drop a field | Invalid cookie, autoLogin rejects/clears | Invalid cookie, autoLogin rejects/clears |
| Change username | Signature becomes invalid | No username inside cookie |
| Change expiry | Signature invalid without re-signing | Expiry rests on server record, not in cookie |
| Change signature | Signature comparison fails | Not applicable; changing token on same series → mismatch/theft handling |
| Change series | No series | No row found or hits another series with wrong token |
| Replay old cookie after rotation | No per-request rotation by default | Old token differs from new → replay protection deletes user's series per default code |
| Change application key | Old signed token fails verification | Persistent token still relies on store; key still affects auth-provider key matching |

**A true "tampered" test should not just pass a non-Base64 string**, get 401, and conclude tampering protection works. There are two distinct tests: malformed encoding and **valid format with mismatched content/signature**. This lesson used `decodeCookie/encodeCookie` helpers to construct the second case.

### 13.1. Never write raw cookies into logs/CI artifacts

A remember-me cookie is a **credential**. JUnit failure messages like `assertEquals(expectedCookieValue, actualCookieValue)` can print credentials into test reports. With integration tests using test users the risk is lower, yet maintain the habit of never pushing cookies into logs, snapshots, or metrics. Use safe hashes/correlation IDs when needed.

## 14. Stolen cookies: password change, disabled accounts, and signing keys

### 14.1. Password change

The signed strategy includes the current password string/hash in the signature. Thus changing `passwordHash` on `UserDetails` makes old cookies mismatch, as tested in section 8. Never expose password hashes in responses — the mechanism uses them purely server-side to compute/check signatures.

The persistent strategy does not automatically use the password hash to check series/tokens. **After a password change, explicitly delete persistent tokens** (e.g., `removeUserTokens(username)`) if business policy requires re-login across all devices. Also revoke old sessions/refresh tokens if present.

### 14.2. Disabled/locked accounts

`AbstractRememberMeServices` provides `setUserDetailsChecker(...)` and uses appropriate account-status checks by default. When a user is disabled/locked/expired, `autoLogin` should create no authenticated principal. A custom `UserDetailsService` failing to populate status accurately onto `UserDetails` can bypass this policy.

Tests must:

- Issue the cookie **before** disabling the user.
- Disable the user in the trusted repository.
- Send a request **without a session** carrying the old cookie.
- Expect no remember-me Authentication and blocked access.
- Restore accounts only through proper reactivation policy, without automatically reviving revoked persistent records.

### 14.3. Signing key

If the signing key is leaked, an attacker can forge valid signed cookies if they possess the required fields; rotate keys, review sessions, and raise protections. Nodes using different keys cause intermittent failures. Store keys in a secret manager with scheduled rotation and clear runbooks. Under the signed strategy, rotating the key normally invalidates old cookies app-wide.

## 15. Persistent token storage: JDBC and cleanup

Spring Security provides `JdbcTokenRepositoryImpl` implementing `PersistentTokenRepository`. Per the 6.5 reference, the baseline schema:

```sql
CREATE TABLE persistent_logins (
    username VARCHAR(64) NOT NULL,
    series VARCHAR(64) PRIMARY KEY,
    token VARCHAR(64) NOT NULL,
    last_used TIMESTAMP NOT NULL
);
```

This is a reference schema; PostgreSQL/MySQL/SQL Server require migrations matching dialect/requirements. Never rely on `setCreateTableOnStartup(true)` in production: that feature is only for quick debugging.

Servlet JDBC bean example:

```java
// Snippet inside @Configuration of a Spring Boot JDBC app.
@Bean
PersistentTokenRepository rememberTokenRepository(DataSource dataSource) {
    JdbcTokenRepositoryImpl repository = new JdbcTokenRepositoryImpl();
    repository.setDataSource(dataSource);
    return repository;
}

@Bean
SecurityFilterChain security(HttpSecurity http,
        PersistentTokenRepository repository,
        UserDetailsService users,
        @Value("${app.remember.key}") String key) throws Exception {
    return http
            .authorizeHttpRequests(auth -> auth
                    .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .rememberMe(remember -> remember
                    .key(key)
                    .userDetailsService(users)
                    .tokenRepository(repository)
                    .tokenValiditySeconds(86400))
            .build();
}
```

Both snippets require imports for `javax.sql.DataSource`, Spring Security config, rememberme types, etc. They illustrate **separate persistent configuration** and should not be mixed into the section 6 signed-cookie demo app without choosing one clear strategy.

### 15.1. Real JDBC tests differ from in-memory

`InMemoryTokenRepositoryImpl` can pass unit tests without proving:

- DB transactions/isolation and unique constraints on `series`.
- Rotation updates and concurrent requests across two application replicas.
- Token data surviving restarts/deploys.
- Cleanup of expired rows, retention, and DB capacity.
- Credential rows deleted upon logout, password change, and account disable/delete across **all nodes**.
- Row-level security/tenant boundaries and token protection in backups/DB query logs.

Write integration tests with H2/Testcontainers or the real app DB, apply schemas with Flyway/Liquibase, and use two HTTP clients with separate cookie jars. Never enable automatic table creation when multiple replicas compete.

### 15.2. Concurrency and rotation

If two concurrent requests use the same persistent cookie:

```text
Request A                         Request B
 read series S, token T           read series S, token T
 compare T == stored T            compare T == stored T
 update stored token = T_A        update stored token = T_B ?
 Set-Cookie(T_A)                  Set-Cookie(T_B)
```

Outcomes depend on storage isolation and read/write timing. When one request arrives with the old cookie after rotation, the implementation may treat the mismatch as theft and delete all tokens for that user. Production requires real load tests ensuring appropriate replay policies, concurrency/transactions, and UX. Never promise that the default JDBC implementation provides atomic compare-and-swap eliminating all races unless verified against source/dialect.

## 16. Remember-me and authorization: authenticated vs. fullyAuthenticated

Spring Security provides `AuthenticationTrustResolver` and authorization expressions to distinguish remember-me authentication from stronger logins:

```java
// Inside authorizeHttpRequests:
.requestMatchers("/profile").authenticated()
.requestMatchers("/change-password").fullyAuthenticated()
```

- `authenticated()`: request holds an `Authentication` considered authenticated, including remember-me where applicable.
- `fullyAuthenticated()`: requires **neither** anonymous **nor** remember-me; may redirect to login or return a challenge per config when only a remembered identity is present.
- Role/scope rules still apply separately; `fullyAuthenticated()` does not by itself prove MFA/passkey/UV or recent login time.
- For money transfers, changing email/keys, deleting accounts, or registering passkeys, even `fullyAuthenticated` **may still be insufficient**; require recent reauthentication/step-up and corresponding business authorization.

The WebFlow test suite in section 7 generates a real cookie and calls `/sensitive` **without a session** to confirm no bypass. Using only `with(user("alice"))` makes Spring Security Test build a fake authentication treated as full, failing to verify the real remember-me trust level.

## 17. Distinguishing remember-me from OAuth tokens, passkeys, and SSO

| Credential/state | Purpose | How does logout affect it? |
| --- | --- | --- |
| `remember-me` cookie | Recreates authentication for the browser | Logout handler clears cookie; server-side persistent tokens need proper revocation |
| `JSESSIONID` / HTTP session | Maintains SecurityContext across requests | Session invalidation/context clear |
| OAuth2 refresh token | Requests new access tokens from Authorization Server | Must revoke grant/token at AS; local logout does not auto-revoke |
| JWT access token | Calls Resource Server | Offline RS may keep accepting until expiry without a revocation mechanism |
| OIDC OP SSO session | Centralized login at IdP | RP logout does not guarantee OP logout; requires OIDC logout flow |
| WebAuthn passkey | Cryptographic key credential for login/step-up | Logout does not delete public-key bindings or private keys on the authenticator |

Losing a device holding session cookies, remember-me cookies, and passkeys requires a **coordinated incident response**. Changing the password may invalidate signed remember-me cookies yet **does not guarantee** revoking all OAuth tokens or passkeys. Deleting a passkey at the RP does not automatically erase issued remember-me cookies. That is why tests must verify each state store rather than collapsing them into one "logout all" assertion.

## 18. CORS, CSRF, same-site, and real browsers: testing beyond MockMvc

Remember-me cookies are attached by the browser per domain/path/SameSite policy, so:

1. The browser does not need JavaScript to read the cookie; `HttpOnly` should be enabled.
2. Form login/logout use cookie authentication and sessions: keep **CSRF protection** on POSTs per policy.
3. Production HTTPS: `Secure` cookies are mandatory; never accept credential cookies over HTTP. Behind a TLS reverse proxy, configure forwarded headers/secure requests properly.
4. `SameSite` can affect cross-site navigation flows; do not use `SameSite=None` carelessly, and when required, enable `Secure`.
5. Run E2E tests on real browsers to verify cookies are stored, sent on the right subdomain/path, and truly deleted after logout.
6. A cookie has `Max-Age`, yet browser policies/private mode can delete it early; the server cannot infer whether the client cookie jar still holds it.
7. Never scope a remember-me cookie across an unnecessarily broad domain, avoiding untrusted subdomains receiving the cookie.
8. CORS preflight/fetch credentials do not equate to remember-me. CORS only controls browser API access, not cookie authentication.
9. The UI should offer a clear **Remember me on this device** option; never auto-opt-in on shared machines if policy disallows it.
10. After logout, testing page reload in a **clean browser context** and testing an attacker manually replaying the old cookie are two distinct scenarios.

### 18.1. Browser test described as pseudocode

```text
Given: user Alice authenticates using interactive login
When: Alice selects "Remember me"
Then: browser stores the remember-me cookie with expected flags

When: the application session disappears but remember-me cookie remains
Then: browser can load a non-sensitive authenticated page

When: Alice logs out
Then: browser drops the remember-me cookie
And: the application session is invalidated

When: an attacker replays the original cookie value with a separate client
Then: expected result depends on signed vs persistent revocation policy
And: high-risk actions still require step-up
```

Do not use this pseudocode in place of JUnit/HTTP integration tests; it serves as acceptance criteria for Playwright/Selenium or browser test infrastructure.

## 19. Debugging common issues

### 19.1. Logged in yet no remember-me cookie appeared

Check whether the login POST includes `remember-me=on`, whether default `alwaysRemember(false)` is active, whether login truly succeeded, whether `RememberMeServices.loginSuccess` is wired into the authentication filter, and whether cookie path/secure policies caused the browser to ignore it. If using a custom success handler/provider, check that it invokes the right hooks.

### 19.2. Cookie exists yet the user is not auto-logged-in

Check whether the cookie is sent on the new request (Domain, Path, SameSite, Secure), whether an old `HttpSession` is skewing the test, whether keys match across nodes, whether `UserDetailsService` returns matching password hash/account status, whether the token expired, and whether the manager includes the corresponding `RememberMeAuthenticationProvider`.

### 19.3. Valid test passes yet HTTP returns 302 login

The route may require `fullyAuthenticated()`, the cookie may not have been sent by the browser, the cookie may have been rejected, or the service created `RememberMeAuthenticationToken` yet the provider/manager distrusts the key. Read traces in the test environment without printing raw tokens/passwords. For `fullyAuthenticated()`, a redirect/challenge is expected behavior.

### 19.4. Tampered with the cookie yet the test still gets 200

The request very likely still carries an authenticated session, so the remember-me filter **never ran**. Clear `JSESSIONID`/`MockHttpSession` when sending a tampered cookie; send only the `remember-me` cookie. Ensure the target route requires authentication. Use assertions proving `SecurityContext` is remember-me when valid.

### 19.5. Expiry test fails intermittently

Never use `Thread.sleep(1000)` and compare near boundaries; it depends on CI speed/system clocks. For the signed strategy, use a properly signed token with an expiry far in the past; for persistent, use an old record via `Date(0)`. Test exact boundaries only when you know which comparison operator your implementation uses.

### 19.6. Logout returns 302 and cookie cleared yet DB record remains

Check whether `PersistentTokenBasedRememberMeServices.logout` received `Authentication != null`. Check logout handler registration and whether the request had session/user context. Do not conclude "the database must delete it" from HTTP status alone. When design mandates always revoking, add a flow that identifies the user reliably and test sessionless paths too.

### 19.7. Persistent tokens wiped en masse after one request

A request may have used an old cookie after rotation: the series matched yet the token value no longer matched, so the implementation treated it as a stolen cookie and called `removeUserTokens(username)`. Check concurrent requests/response races, storage replication, and browser tabs. Never change this to "accept on mismatch", which breaks replay protection.

### 19.8. Password changed yet persistent remember-me still works

That is the difference between signed cookies and a persistent token store. Call `removeUserTokens(username)` upon password change/reset or account security events per policy. Do not expect a password change to delete DB token rows automatically.

### 19.9. Rotating key invalidates signed cookies across all browsers

Expected semantics: signatures depend on the key. If rotation was unintentional, check secret configuration across replicas/deployments. If rotated due to an incident, plan to force users to log in again with proper communication.

### 19.10. Tests relying on MockMvc.with(user(...)) always pass

That request post-processor **injects an existing Authentication**, bypassing login/password/remember-me cookie validation. Use it for authorization tests, never to prove a remember-me token is valid/expired/tampered. Invoke the real login flow or real service.

## 20. Comprehensive production test matrix

| Test | Layer | Data/trigger | Required outcome |
| --- | --- | --- | --- |
| T01 | MockMvc | Valid POST /login, no remember-me | No new cookie issued |
| T02 | MockMvc | Valid POST /login, opt-in | Remember-me cookie issued |
| T03 | MockMvc | Wrong-password POST /login, opt-in | No valid remember-me credential issued |
| T04 | MockMvc | POST /login missing CSRF | No login/cookie created |
| T05 | MockMvc | No session, valid cookie | Authenticates via remember-me |
| T06 | MockMvc | Remember-me only, calling `fullyAuthenticated` | Denied/reauth challenge |
| T07 | Unit signed | Cookie with valid format, tampered signature | No autoLogin |
| T08 | Unit signed | Expired cookie yet valid signature | No autoLogin |
| T09 | Unit signed | Password hash changed | Old cookie rejected |
| T10 | Unit signed | Disabled/locked account | No autoLogin |
| T11 | Unit signed | Malformed base64/truncated fields cookie | No autoLogin and cancels cookie |
| T12 | Unit signed | Application key changed | Old signature rejected |
| T13 | Unit signed | Logout | Clears browser cookie; assess replay risk |
| T14 | Unit persistent | Valid unexpired series/token | AutoLogin + rotates |
| T15 | Unit persistent | Non-existent series | Rejected |
| T16 | Unit persistent | Right series/wrong token | Rejected, revokes user tokens |
| T17 | Unit persistent | Replay pre-rotation cookie | Rejected and signals suspected theft per policy |
| T18 | Unit persistent | Expired record | Rejected while record stays until cleanup |
| T19 | Unit persistent | Logout with principal | Cookie expired + `removeUserTokens` |
| T20 | Unit persistent | Logout with null principal | Do not assume server tokens were deleted |
| T21 | JDBC integration | DB restart after cookie issuance | Token persistence behaves as designed |
| T22 | JDBC integration | Two app replicas sharing DB | Consistent login/revocation |
| T23 | Concurrency | Two requests same series/token | No false access leak; evaluate rotation race |
| T24 | Browser | Cookie Secure/HttpOnly/SameSite/Path | Browser stores/sends/deletes properly |
| T25 | Browser | POST logout missing CSRF | No unintended logout |
| T26 | Account security | Disable/remove user | All remember-me paths fail closed |
| T27 | Account security | Password reset/logout all | Revocation per policy on both cookies and DB |
| T28 | OIDC/OAuth | Local logout + active OAuth/SSO token | Do not claim revocation beyond what executed |
| T29 | Session | HTTP session still active, bad cookie | Isolate tests to avoid false positives |
| T30 | Ops | Metrics/logs | Never log raw cookies, secrets, or passwords |
| T31 | Recovery | Lost device holding remember-me cookie | Playbook exists to revoke sessions/tokens |
| T32 | Multi-node | Different signing keys across nodes | Test catches mismatch; policy requires consistent key |
| T33 | Version regression | Spring Security/Boot upgrade | Cookie algorithm/format and integration tests stay green |
| T34 | Retention | Long-expired persistent rows | Background cleanup prevents unbounded storage growth |

Prioritization: **7 signed unit tests + 7 persistent unit tests + 4 MockMvc tests** form the core learning set; JDBC/multi-node/browser cases are mandatory verification layers if the product actually ships remember-me to users.

## 21. Operations and security: where passing tests are still not enough

### 21.1. Remember-me is a long-lived credential

A valid remember-me cookie lets its holder restore authentication after a session disappears. Protect it like a credential: HTTPS, `Secure`/`HttpOnly`/`SameSite`, minimal domain/path, bounded TTL, never logged or sent to third parties. For sensitive accounts, consider **disabling** the feature or requiring step-up for risky actions.

### 21.2. Post-incident revocation

When a user reports a lost device:

1. Lock/invalidate suspected compromised sessions.
2. Revoke persistent remember-me token rows or rotate signing key/password per appropriate strategy.
3. Revoke needed refresh grants/API keys in other systems.
4. Protect email/phone/passkey recovery so attackers cannot reclaim the account.
5. Notify/audit and verify new requests with revoked cookies are blocked.
6. Acknowledge that local logout and server-side remember-me revocation may have propagation latency in clusters; measure and monitor.

Never send only `Set-Cookie: remember-me=; Max-Age=0` to the current browser and conclude an attacker cannot use an old copy.

### 21.3. Keys and repositories share the trust boundary

Keys in `TokenBasedRememberMeServices` must remain secret and rotate per policy. Persistent repositories must prevent unauthorized access, series/token row leaks, query log exposure, and backup leaks. With 2+ replicas, use a shared store with required consistency; never treat the test in-memory repository as production-ready.

### 21.4. Expired record cleanup

`PersistentTokenBasedRememberMeServices` checks record dates but does not automatically purge all expired tokens from the store. Design a scheduled cleanup job with proper indexes; test that cleanup does not delete active records by mistake and handles retries safely. If storing retention/audit metadata, do not retain raw tokens longer than necessary.

## 22. Pre-handoff checklist for the test suite

1. Identified whether the app uses the **signed** or **persistent** strategy, plus cookie name, validity, and user details source.
2. Tested login **opt-in vs. opt-out**, matching form fields and CSRF.
3. Tested valid cookies **without sending an old session**, avoiding false positives.
4. Tested signed cookie **signature changed** separately from malformed Base64.
5. Tested signed cookie **expired yet validly signed**, plus password/key invalidation.
6. Tested persistent **valid + rotation** checking both series and new token; tested replay.
7. Tested persistent **unknown series**, **same series/wrong token**, and expired records.
8. Tested logout with `Authentication != null` **and** `null`, checking both cookies and repository.
9. Distinguished logout merely clearing cookies from revoking stolen copies.
10. Tested `authenticated()` vs. `fullyAuthenticated()` for sensitive endpoints.
11. Tested disabled/locked account status, `UserDetailsChecker`, and password changes.
12. If using JDBC, tested schema/cleanup/transactions/concurrency and 2+ replicas.
13. Added browser E2E tests for `Secure`, `HttpOnly`, `SameSite`, `Domain`, `Path`, `Max-Age`, logout, and CSRF.
14. Kept remember-me cookies/tokens/keys out of logs, request URLs, metrics, and test reports.
15. Prepared a playbook for account compromise/lost device, re-signing cookies or revoking persistent tokens.
16. Maintained regression tests across Spring Security upgrades, login filter changes, or authentication mechanism changes.

**Conclusion:** Remember-me testing must prove **cookies are issued on opt-in, accepted while unexpired, rejected when expired/tampered, and handled properly on logout**. In particular, never equate **clearing a cookie in the browser** with **revoking server-side credentials** or **blocking a stolen cookie copy**. For the persistent strategy, rotation and series/token mismatches are mandatory dedicated tests; for the signed strategy, expiry/signature/password-key dependencies are central.

## 23. Official documentation

- [Spring Security 6.5.11 — Remember-Me Authentication (Servlet)](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/rememberme.html): signed approach, persistent approach, loginSuccess/loginFail/autoLogin, `UserDetailsService`, cookie rotation.
- [Spring Security 6.5.11 — RememberMeServices API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/RememberMeServices.html): 3-method contract and invalid cookie handling.
- [Spring Security 6.5.11 — AbstractRememberMeServices API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/rememberme/AbstractRememberMeServices.html): cookie flags, TTL, opt-in, and logout.
- [Spring Security 6.5.11 — TokenBasedRememberMeServices API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/rememberme/TokenBasedRememberMeServices.html): signature, SHA-256, expiry, password/key invalidation.
- [Spring Security 6.5.11 — PersistentTokenBasedRememberMeServices API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/rememberme/PersistentTokenBasedRememberMeServices.html): series/token, refresh/rotation, expiry record, logout.
- [Spring Security 6.5.11 — PersistentRememberMeToken API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/rememberme/PersistentRememberMeToken.html): username, series, token, and date.
- [Spring Security 6.5.11 — InMemoryTokenRepositoryImpl API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/rememberme/InMemoryTokenRepositoryImpl.html): test repository.
- [Spring Security 6.5.11 — JdbcTokenRepositoryImpl API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/rememberme/JdbcTokenRepositoryImpl.html): JDBC persistent records and schema/migration.
- [Spring Security 6.5.11 — RememberMeAuthenticationFilter API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/rememberme/RememberMeAuthenticationFilter.html): auto login filter and SecurityContext.
- [Spring Security — Handling Logouts](https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html): LogoutFilter, handlers, CSRF, SecurityContext/session/cookie cleanup.
- [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html): session persistence, SecurityContext, authentication lifetime.
- [Spring Security — MockMvc Testing](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html): testing form login/CSRF/authentication and request post-processors.
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): session/token lifecycle, cookie flags, and invalidation.
- [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): persistent login, reauthentication for sensitive actions, preventing credential leakage.
