# RememberMeServices, RememberMeAuthenticationFilter, and the corresponding provider

> **Context:** Spring Security — authentication, **Remember Me** group. This article uses Spring Security **Servlet 6.x**, with a full example on **Spring Boot 3.3.5 / Java 17+ / Maven**. The focus is the relationship between `RememberMeServices`, `RememberMeAuthenticationFilter`, and `RememberMeAuthenticationProvider`; the remember-me cookie issuance/verification mechanism; the trust level of restored identities; and how to implement and test safely.

## 1. What does Remember-me solve?

When a user closes their browser, the HTTP session may expire or the `JSESSIONID` session cookie may be cleared. If they explicitly opted into **"Remember me"**, the application can issue a remember-me cookie with a longer lifetime than the session cookie. On a subsequent visit, Spring Security uses that cookie to **recreate `Authentication`** without requiring the user to re-enter their password at that moment.

This is an **automatic re-login mechanism backed by a long-lived credential in a cookie**, not a "keep the session alive forever" feature. The remember-me cookie must be treated as a **sensitive credential**: anyone who steals it can impersonate the user while the cookie remains valid, depending on the token type and revocation policy.

Example user behavior:

1. The user opens `GET /login` and enters username/password.
2. The user **checks** `remember-me` and submits `POST /login`. After credentials are verified, the application issues the `remember-me` cookie to the browser.
3. The user continues using the HTTP session normally. While the session holds a valid `SecurityContext`, Spring Security does not need to use the remember-me cookie on every request.
4. Once the session disappears while the `remember-me` cookie remains, a request to a protected URL triggers the auto-login flow.
5. Valid cookie → the server identifies the user, loads trusted authorities from `UserDetailsService`, and places the remember-me authentication into `SecurityContext`. Invalid/expired cookie → no re-login; the protected endpoint will require signing in.
6. A sensitive endpoint such as changing a password or transferring money can require **`fullyAuthenticated()`** to force fresh credential entry rather than trusting remember-me alone.

### Distinguishing session and remember-me

| Criterion | HTTP session | Remember-me |
| --- | --- | --- |
| Browser-side artifact | Session cookie, usually `JSESSIONID` | Longer-lived cookie, typically named `remember-me` by default |
| Identity source for subsequent requests | `SecurityContextRepository` reads context from session | `RememberMeServices` verifies cookie when `Authentication` is missing |
| Triggering event | Successful login and saving context/session | Successful login **and** user requested remember-me (unless `alwaysRemember` is configured) |
| Server-side data | Session contents held by container/session store | Token-based: no token table needed; persistent-based: `PersistentTokenRepository` |
| Trust level | Fresh/interactive login is usually considered fully authenticated | Remembered login has **lower** trust for `fullyAuthenticated()` |
| Logout | Can invalidate session and clear context | Must also clear cookie; revoking copies depends on token type |
| Risk | Session hijacking/fixation | Remember-me cookie replay, stolen token, long lifetime |

**Do not confuse:** `RememberMeAuthenticationToken.isAuthenticated() == true` **does not mean** `fullyAuthenticated() == true`. Spring Security uses `AuthenticationTrustResolver` to distinguish remembered from full interactive authentication.

## 2. The three main components and their contracts

### 2.1. `RememberMeServices` — issuing, cancelling, and reading cookies

The `org.springframework.security.web.authentication.RememberMeServices` interface provides three core methods:

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

These are **condensed API signatures for learning**; add the corresponding Servlet and Spring Security imports when placing them in a Java file. Meaning:

- `loginSuccess`: the interactive authentication filter notifies that the user just logged in successfully. The service checks the "remember me" request (usually the `remember-me` form parameter). If selected, it signs/issues a cookie or persists a token and issues a cookie.
- `loginFail`: interactive login failed; the service may clear any presented remember-me cookie, avoiding retaining a no-longer-appropriate cookie.
- `autoLogin`: on a new request lacking authentication, the service reads the cookie and checks format, expiration, signature, or server record; if successful it returns an appropriate `Authentication` object, and if the cookie cannot be used it typically returns `null` or throws `AuthenticationException`.

Two standard Spring Security implementations:

- `TokenBasedRememberMeServices` — signed token based on user/password hash, expiration, and secret key; **no separate token database needed**.
- `PersistentTokenBasedRememberMeServices` — random series/token with a record in `PersistentTokenRepository`, commonly stored via JDBC; tokens are rotated on use by design.

Both typically require `UserDetailsService` to look up the user and current authorities after verifying the cookie. If the application only has an LDAP/custom provider without supplying a `UserDetailsService` for remember-me, the configuration must be supplemented appropriately.

### 2.2. `RememberMeAuthenticationFilter` — where auto-login is triggered

`RememberMeAuthenticationFilter` belongs to the Servlet `SecurityFilterChain`. The filter only attempts auto-login when **`SecurityContext` does not currently contain an `Authentication`**. It invokes:

```text
RememberMeServices.autoLogin(request, response)
    -> Authentication candidate or null
    -> if candidate is non-null:
         AuthenticationManager.authenticate(candidate)
         -> Authentication accepted by manager
         -> placed into SecurityContext
         -> continue filter chain
    -> if failed:
         clean up context/cookie per implementation
         -> continue as anonymous / proceed to entry point when needed
```

Points to emphasize:

1. The filter does **not** read raw passwords from a form on every request. It uses the remember-me cookie.
2. The filter does **not** blindly accept every cookie as valid. Remember-me services verify cookie contents; the manager/provider verifies the internal token.
3. If the session already carries an `Authentication`, the remember-me filter typically **skips** auto-login. Thus a user who simultaneously has a remember-me cookie and a logged-in session may still be using full interactive authentication.
4. When remember-me succeeds, filter/repository configuration can save the context so subsequent requests use the session; the cookie remains the recovery basis when the session is gone.
5. The filter does not mean every stateless/JWT API automatically gains remember-me; it belongs to the Servlet cookie flow configured for web apps.

### 2.3. `RememberMeAuthenticationProvider` — verifying the internal token

`RememberMeAuthenticationProvider` processes `RememberMeAuthenticationToken`. This provider verifies whether the token's **key hash** matches the configured key. It **does not re-verify raw username/password** like `DaoAuthenticationProvider`, nor is it **the component** that directly checks the browser cookie signature.

Exact boundaries:

| Step | Component | What is being verified? |
| --- | --- | --- |
| POST /login | `UsernamePasswordAuthenticationFilter` + `DaoAuthenticationProvider` | Username/password, password hash, user status |
| Successful login with remember-me checked | `RememberMeServices.loginSuccess` | Opt-in presence and how cookie/token is generated |
| Subsequent request without session auth | `RememberMeAuthenticationFilter` | Should auto-login be attempted? |
| Verifying long-lived cookie | `TokenBasedRememberMeServices` or `PersistentTokenBasedRememberMeServices` | Token integrity, expiry, repository record if any, user lookup |
| Accepting `RememberMeAuthenticationToken` | `RememberMeAuthenticationProvider` | Token was created using the **trusted application key** |
| Endpoint authorization | `AuthorizationFilter` + `AuthenticationTrustResolver` | `authenticated()`, `fullyAuthenticated()`, and authorities |

**Keys must match:** `RememberMeServices` and `RememberMeAuthenticationProvider` must agree on the `key`. If the provider is configured with a different key than the service, auto-login will not be accepted. Conversely, never allow clients to construct a `RememberMeAuthenticationToken` with arbitrary authorities and place it into the context — this token must only be created inside trusted server logic after cookie verification.

With Spring Security's `http.rememberMe(...)` Java DSL, the framework wires the corresponding filter, services, and provider together. Usually **there is no need** to manually `new RememberMeAuthenticationFilter` or manually add the provider when using standard remember-me.

## 3. Detailed flow: first login, lost session, and returning

```text
PHASE A — INTERACTIVE LOGIN

Browser POST /login
  | username=alice, password=demo-pass123, remember-me=on, valid CSRF
  v
UsernamePasswordAuthenticationFilter
  |-> AuthenticationManager -> DaoAuthenticationProvider
  |      -> UserDetailsService + PasswordEncoder
  |      -> Authenticated interactive Authentication
  |
  +-> SessionAuthenticationStrategy / SecurityContextRepository
  |      -> create / rotate session ID and save SecurityContext
  |
  +-> RememberMeServices.loginSuccess(request, response, authenticated)
         -> remember-me cookie issued (if opt-in)
  v
HTTP 302 + Set-Cookie: remember-me=... + session cookie as needed

PHASE B — HTTP SESSION EXPIRED / NOT SENT

Browser GET /api/me
  | Cookie: remember-me=...     (JSESSIONID not sent)
  v
SecurityContextHolderFilter: no Authentication from session
  v
RememberMeAuthenticationFilter
  -> RememberMeServices.autoLogin(...)
       -> read cookie, verify hash/token and UserDetails
       -> return RememberMeAuthenticationToken
  -> AuthenticationManager.authenticate(...)
       -> RememberMeAuthenticationProvider checks key hash
  -> set authenticated Authentication into SecurityContext
  v
AuthorizationFilter: /api/me .authenticated() -> allow
  v
Controller observes rememberMe=true, fullyAuthenticated=false

PHASE C — SENSITIVE ACTION

Browser GET /api/high-risk carrying only remember-me cookie
  -> /api/high-risk .fullyAuthenticated()
  -> NOT satisfied; entry point prompts re-login
  -> accessible only after successful interactive form login
```

**Important observation:** phases A and B use **two different `Authentication` types**. Normal login is `UsernamePasswordAuthenticationToken`. Auto-login is `RememberMeAuthenticationToken`; this token is authenticated from Spring Security's perspective, but `AuthenticationTrustResolver` classifies it at the **remember-me** level, not fully authenticated.

## 4. Two ways to store remember-me tokens: hash-based and persistent

### 4.1. Token-based: signed cookie, no token table

The simple model uses `TokenBasedRememberMeServices`. According to Spring Security documentation, the Base64-decoded cookie content is conceptually close to:

```text
username : expirationTime : algorithmName :
H(username : expirationTime : passwordHash : serverKey)
```

Where:

- `username` is used to reload the user via `UserDetailsService`.
- `expirationTime` is the expiration timestamp, not the `HttpSession` limit.
- `algorithmName` identifies the hash algorithm encoded in the token in supporting versions.
- `passwordHash` is the server-stored encoded password, **not the user's raw password inside the cookie**.
- `serverKey` is the application secret key; it must never be sent to the client.
- The hash value detects token tampering, but **does not encrypt** the whole cookie into secret data. Base64 is not encryption.

Advantages: simple setup, no token table required, verification based on key and UserDetails. Major drawback: **a copied cookie can be replayed while still within its validity window**, and it is usually impossible to revoke a single device with pure token-based remember-me. Changing the password hash or changing the key invalidates old tokens; you need a key rotation policy mindful of its impact on all browsers.

**Note in the demo:** `UserDetailsService` hashes the password with BCrypt on every startup. BCrypt uses a random salt, so even if the plaintext password stays the same, the new hash can differ. Because the token-based signature depends on the stored hash, a remember-me cookie created before an app restart **may become invalid** in the demo. Production uses a stable hash stored in a database and a stable key in a secret manager.

### 4.2. Persistent token: series/token in a server store

`PersistentTokenBasedRememberMeServices` uses `PersistentTokenRepository`. The cookie usually contains a **series identifier** and a random token. The server looks up the series in the store, compares the presented token against the stored token, and then **replaces it with a new token** after successful auto-login. When the same series appears with a mismatched old token, it can be treated as a sign of a copied/stolen token, per the implementation's policy.

Typical flow:

```text
Cookie with series=s1, token=t1
  -> look up persistent_logins by series s1
  -> if valid: create new token t2, update repository, send new cookie
  -> if wrong token for existing series: handle possible token theft
  -> if series missing / expired: reject auto-login
```

Common schema with `JdbcTokenRepositoryImpl`:

```sql
CREATE TABLE persistent_logins (
    username VARCHAR(64) NOT NULL,
    series VARCHAR(64) PRIMARY KEY,
    token VARCHAR(64) NOT NULL,
    last_used TIMESTAMP NOT NULL
);
```

This table must be created through system migrations and wired to a properly configured `DataSource`. `JdbcTokenRepositoryImpl` does not replace device lifecycle management: revoking by user, by series, or cancelling on account lock requires explicit policies.

| Criterion | Token-based | Persistent-token |
| --- | --- | --- |
| Where proof is stored | Signed cookie, no token table needed | Series/token cookie **and** server-side repository |
| Implementation | Simple, few storage dependencies | Requires DB/repository, migrations, backups, concurrency handling |
| Verification | Signature from user, expiry, password hash, key | Look up series/token, match, rotate token |
| Per-device revocation | Difficult in the pure model | Can delete/suspend series if design supports it |
| If cookie is copied | Replayable until expiry/key/password change | Rotation helps detect some copy/replay cases, though does not eliminate every risk |
| Multi-node usage | Needs consistent signing key and user data | Needs a shared, consistent repository across all nodes |
| Recommendation | Low-risk applications, carefully evaluated | Usually better suited when token tracking/revocation is needed |

**Do not misunderstand persistent = completely secure.** If an attacker uses a token before the legitimate user or compromises the token store itself, risks remain. You still need TLS, secure cookies, rotation, auditing, expiration limits, and device-compromise defenses.

### 4.3. When should you not use remember-me?

Do not issue remember-me by default for:

- Applications requiring strict re-authentication on every visit (highly sensitive financial apps, secret-key administration, etc.).
- Privileged accounts lacking mechanisms to restrict the scope of remembered authentication.
- Public computers or shared devices.
- Flows where regulations/policies mandate fresh auth/MFA that cannot be satisfied by a long-lived cookie.
- Stateless bearer-token-only APIs with no browser cookie needs: do not enable remember-me merely to replace refresh tokens.

Remember-me does not replace MFA, step-up authentication, password reset workflows, or session management.

## 5. Runnable Spring Boot application: token-based remember-me

The example retains `formLogin` and default CSRF protection. User `alice` with study password `demo-pass123` has `ROLE_USER`. There are two endpoints:

- `GET /api/me`: accepts session login or remembered login; returns the actual trust level.
- `GET /api/high-risk`: requires `fullyAuthenticated()`; a remembered cookie alone is **not enough**.

### 5.1. Structure and Maven

```text
remember-me-demo/
├── pom.xml
├── src/main/java/com/example/rememberme/RememberMeDemoApplication.java
└── src/test/java/com/example/rememberme/RememberMeDemoApplicationTests.java
```

Contents of `pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>remember-me-demo</artifactId>
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
```

### 5.2. Java application

Create `src/main/java/com/example/rememberme/RememberMeDemoApplication.java`:

```java
package com.example.rememberme;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@SpringBootApplication
public class RememberMeDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(RememberMeDemoApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password(encoder.encode("demo-pass123"))
                        .roles("USER")
                        .build()
        );
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            UserDetailsService users) throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/public").permitAll()
                .requestMatchers("/api/high-risk").fullyAuthenticated()
                .requestMatchers("/api/me").authenticated()
                .anyRequest().denyAll()
            )
            .formLogin(Customizer.withDefaults())
            .rememberMe(remember -> remember
                // Demo only: production must use a strong secret stored outside source.
                .key("local-demo-key-do-not-use-in-production")
                .userDetailsService(users)
                .rememberMeParameter("remember-me")
                .rememberMeCookieName("remember-me")
                .tokenValiditySeconds(7 * 24 * 60 * 60)
                .alwaysRemember(false)
            )
            .logout(Customizer.withDefaults());

        // Default CSRF and session-fixation protection remain enabled.
        return http.build();
    }

    public record UserState(
            String username,
            boolean remembered,
            boolean fullyAuthenticated,
            List<String> authorities
    ) {}

    @RestController
    static class DemoController {
        private final AuthenticationTrustResolver trustResolver =
                new AuthenticationTrustResolverImpl();

        @GetMapping("/public")
        String publicPage() {
            return "public";
        }

        @GetMapping("/api/me")
        UserState me(Authentication authentication) {
            List<String> authorities = authentication.getAuthorities().stream()
                    .map(GrantedAuthority::getAuthority)
                    .sorted()
                    .toList();

            return new UserState(
                    authentication.getName(),
                    trustResolver.isRememberMe(authentication),
                    trustResolver.isFullyAuthenticated(authentication),
                    authorities
            );
        }

        @GetMapping("/api/high-risk")
        String highRisk() {
            return "fresh-login-required";
        }
    }
}
```

### 5.3. Read the configuration carefully instead of blindly copying

1. `UserDetailsService` serves both username/password authentication at login and reloading the user when verifying the remember-me cookie. `PasswordEncoder` uses BCrypt rather than comparing raw passwords with `equals`.
2. `formLogin` enables form-based login handled by Spring Security. Upon successful authentication, the authentication filter can invoke `RememberMeServices.loginSuccess`.
3. `rememberMe(...).key(...)` sets the key for the remember-me token/provider; the key in the demo code is **not secure enough for production**. In real deployments, inject the secret from a secret manager/secure configuration and keep it consistent across instances.
4. `rememberMeParameter("remember-me")` sets the opt-in parameter name. If the user **does not select it**, `alwaysRemember(false)` prevents issuing a remember-me cookie automatically.
5. `tokenValiditySeconds(7 * 24 * 60 * 60)` sets a 7-day token lifetime for the demo; it does **not** change the session timeout. Do not confuse it with `server.servlet.session.timeout`.
6. `rememberMeCookieName("remember-me")` makes the cookie easy to identify in tests. This cookie **does not contain the raw password**; however, anyone obtaining a valid cookie can exploit it.
7. `/api/me` requires `authenticated()`, allowing both interactive login and remember-me login. The controller uses `AuthenticationTrustResolver` to reflect trust level rather than inferring from `Authentication.isAuthenticated()`.
8. `/api/high-risk` uses `fullyAuthenticated()`. With remember-me only, the framework requires a sufficiently strong login flow; with form login this is usually a redirect to the login page, so do not expect HTTP 403 in all cases.
9. `logout` is handled by `LogoutFilter`. Do not write custom logout logic that only clears `JSESSIONID`, because the remember-me cookie must also be cleaned up.
10. `rememberMe` via Java DSL automatically connects `RememberMeAuthenticationFilter` and `RememberMeAuthenticationProvider`. Do **not** add a second parallel filter/provider for the same cookie, as this can cause duplicate processing or mismatched keys.

**Important regarding HTTPS:** the cookie holds a long-lived bearer-like credential, so production must use TLS, `Secure`, `HttpOnly`, an appropriate `SameSite` policy, CSRF protection, and a reasonable expiration limit. On localhost HTTP, do not force `Secure` if you want to test with curl without TLS; real environments should enforce HTTPS and secure cookies.

## 6. Hands-on in the browser: remembering login when the session is lost

Run the application:

```bash
mvn spring-boot:run
```

Try using a fresh browser profile at `http://localhost:8080/login`:

1. Log in with `alice` / `demo-pass123` and **check remember-me**. Spring Security's default login page provides a remember-me option when the feature is enabled; if building a custom login page, the form must submit `remember-me=on` and a valid CSRF token. After logging in, inspect the `remember-me` cookie in developer tools.
2. Call `http://localhost:8080/api/me` while the session is active. The response typically shows `remembered=false`, `fullyAuthenticated=true`.
3. To verify auto-login, **delete only the `JSESSIONID` session cookie**, keeping the `remember-me` cookie. Do not click logout at this step; logout means the user intentionally wants to end remember-me.
4. Reload `/api/me`. If the remember-me cookie is still valid, Spring Security restores identity and the response returns `remembered=true`, `fullyAuthenticated=false`.
5. Try `/api/high-risk` with remember-me authentication: the URL requires a fresh login and usually redirects to `/login`. Only after entering the password and authenticating interactively does the endpoint become accessible.
6. Perform a formal logout. The browser is directed to `/login?logout`. The remember-me cookie on the browser is cleared by the remember-me logout handler. **Security note:** with token-based remember-me, a **stolen copy of an old cookie** can remain valid until expiry or key/password change; clearing the browser cookie does not mean the server has blacklisted that token.

Example `/api/me` response during interactive login:

```json
{
  "username": "alice",
  "remembered": false,
  "fullyAuthenticated": true,
  "authorities": ["ROLE_USER"]
}
```

Response when only the remember-me cookie remains:

```json
{
  "username": "alice",
  "remembered": true,
  "fullyAuthenticated": false,
  "authorities": ["ROLE_USER"]
}
```

The JSON illustrates **values only**; key order is not a security contract. Both cases carry the `ROLE_USER` authority loaded from `UserDetailsService` on the server, but the level of identity proof differs. An endpoint requiring `hasRole("USER")` without additional trust-level conditions may accept a remember-me user; sensitive actions need stronger policies.

### If you want to test with an HTTP client instead of UI

Use a client that maintains a cookie jar and sends a form POST with the corresponding CSRF token. At login, the default form parameters are `username`, `password`, and `remember-me=on`. A POST lacking valid CSRF can be blocked with 403 by `CsrfFilter` **before** `RememberMeServices.loginSuccess` runs; never disable CSRF just to make testing easier. The MockMvc section below submits CSRF properly.

## 7. Testing real Spring Security with MockMvc

Create `src/test/java/com/example/rememberme/RememberMeDemoApplicationTests.java`:

```java
package com.example.rememberme;

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
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class RememberMeDemoApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void optInIssuesCookieAndCookieRestoresRememberedIdentity() throws Exception {
        MvcResult login = mvc.perform(post("/login")
                    .with(csrf())
                    .param("username", "alice")
                    .param("password", "demo-pass123")
                    .param("remember-me", "on"))
                .andExpect(status().is3xxRedirection())
                .andReturn();

        Cookie rememberCookie = login.getResponse().getCookie("remember-me");
        assertNotNull(rememberCookie);
        assertTrue(rememberCookie.getMaxAge() > 0);

        // Session from interactive login: not remember-me authentication.
        MockHttpSession session =
                (MockHttpSession) login.getRequest().getSession(false);
        assertNotNull(session);
        mvc.perform(get("/api/me").session(session))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.username").value("alice"))
                .andExpect(jsonPath("$.remembered").value(false))
                .andExpect(jsonPath("$.fullyAuthenticated").value(true));

        // Independent request without sending session: ONLY remember-me cookie.
        mvc.perform(get("/api/me").cookie(rememberCookie))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.username").value("alice"))
                .andExpect(jsonPath("$.remembered").value(true))
                .andExpect(jsonPath("$.fullyAuthenticated").value(false))
                .andExpect(jsonPath("$.authorities[0]").value("ROLE_USER"));

        // Remember-me cookie is insufficient for endpoint requiring fresh login.
        mvc.perform(get("/api/high-risk").cookie(rememberCookie))
                .andExpect(status().is3xxRedirection());
    }

    @Test
    void withoutExplicitOptInNoRememberCookieIsIssued() throws Exception {
        MvcResult login = mvc.perform(post("/login")
                    .with(csrf())
                    .param("username", "alice")
                    .param("password", "demo-pass123"))
                .andExpect(status().is3xxRedirection())
                .andReturn();

        assertNull(login.getResponse().getCookie("remember-me"));
    }

    @Test
    void forgedRememberCookieCannotAuthenticate() throws Exception {
        Cookie forged = new Cookie("remember-me", "forged.invalid.token");

        // Cookie lacks valid signature: login page is requested.
        mvc.perform(get("/api/me").cookie(forged))
                .andExpect(status().is3xxRedirection());
    }
}
```

Run inside the `remember-me-demo` directory:

```bash
mvn test
```

The first test runs through the real filter chain configured by Spring Security: form login issues a cookie only on opt-in; a new request **without sending `JSESSIONID`** carrying only the `remember-me` cookie is handled by `RememberMeAuthenticationFilter`; the endpoint reports `remembered=true`; and the endpoint requiring `fullyAuthenticated()` rejects this trust level. The second test verifies opt-in; the third test verifies that a forged cookie cannot log in.

Note: `MockMvc` is not a real browser and does not automatically verify all production `Secure`/`SameSite` attributes. Test HTTPS, cookie flags, restarts, cookie expiry, and persistent repositories with integration/E2E tests if those are operational requirements.

## 8. When you want PersistentTokenRepository instead of token-based

This is an **additional integration snippet**, not a standalone Java file. When using a database, you need `spring-boot-starter-jdbc` and an appropriate JDBC driver, a configured `DataSource`, the `persistent_logins` table created via migrations, and then add the bean:

```java
@Bean
PersistentTokenRepository persistentTokenRepository(DataSource dataSource) {
    JdbcTokenRepositoryImpl repository = new JdbcTokenRepositoryImpl();
    repository.setDataSource(dataSource);
    return repository;
}
```

Required imports for the snippet above:

```java
import javax.sql.DataSource;
import org.springframework.security.web.authentication.rememberme.JdbcTokenRepositoryImpl;
import org.springframework.security.web.authentication.rememberme.PersistentTokenRepository;
```

In the `SecurityFilterChain` configuration, replace the token-based remember-me part with:

```java
.rememberMe(remember -> remember
    .key(rememberMeKeyFromSecretManager)
    .userDetailsService(users)
    .tokenRepository(persistentTokenRepository)
    .rememberMeParameter("remember-me")
    .tokenValiditySeconds(7 * 24 * 60 * 60)
)
```

The variables `users`, `persistentTokenRepository`, and `rememberMeKeyFromSecretManager` in the snippet are dependencies injected/configured in the real application. This snippet **does not compile standalone** if copied verbatim into a file without context. When `tokenRepository(...)` is declared, the DSL selects the appropriate `PersistentTokenBasedRememberMeServices`; do not create another `TokenBasedRememberMeServices` alongside it.

`InMemoryTokenRepositoryImpl` is suitable only for experimentation; it does not survive restarts and is not shared across nodes. With JDBC, do not call `setCreateTableOnStartup(true)` in production because schema/migrations belong to a dedicated process and can fail when the table already exists.

A real system also needs to define:
- Deleting persistent tokens on password change, user lock, account revocation, or detected abuse.
- A revocation strategy per user/device; `removeUserTokens(username)` affects the user's series.
- Handling races when multiple requests use the same token series nearly concurrently and when tokens are copied.
- Lifetime limits, key rotation policies, and mechanisms to protect the token database.
- Storing audit/device metadata separately from raw tokens, without exposing sensitive tokens/series in public APIs.

## 9. Configuration pitfalls and how to isolate root causes

### 9.1. Login succeeds yet no remember-me cookie is issued

Check in order:

1. Did the user actually send the `remember-me` parameter in the **POST login**? With a custom frontend, an untransmitted checkbox provides no opt-in.
2. `alwaysRemember(false)` is a sensible default. Enabling `alwaysRemember(true)` creates cookies even when the user did not opt in — usually undesirable without explicit consent.
3. Does `formLogin` use the same configured `RememberMeServices`? If writing a custom JSON login, you must call `RememberMeServices.loginSuccess(...)` at the right moment (after the manager succeeds) or configure a corresponding filter.
4. Was the login request rejected by the CSRF filter before reaching the authentication filter?
5. Was the `Set-Cookie` header stripped by a reverse proxy, cookie policy, or browser? A `Secure` cookie will not be sent over plain HTTP connections.
6. Are multiple filter chains configured such that remember-me is only on a different chain?

### 9.2. Cookie exists yet login is still required

Check whether the cookie is sent with matching Domain/Path/SameSite/Secure on the request; then inspect:
- Has the cookie expired or been structurally altered?
- Can `UserDetailsService` still load that user? Is the user disabled/removed?
- Did the password hash or `key` change? With the in-memory BCrypt demo, restarts change the hash.
- Do `RememberMeServices` and `RememberMeAuthenticationProvider` share the same key? If wired manually, was the provider registered with the manager?
- Does a chain/endpoint configuration exclude `RememberMeAuthenticationFilter`?
- Was another session/`SecurityContext` already loaded, causing the remember-me filter to skip auto-login?
- Does the endpoint require `fullyAuthenticated()`? In that case remember-me **is recognized**, yet its trust level is insufficient.

### 9.3. Remember-me is active yet password is still required to change password

That is usually the **correct behavior**. `authenticated()` accepts remembered authentication; `fullyAuthenticated()` requires an identity that is neither anonymous nor remembered. For highly sensitive actions, you may also require step-up MFA or check elapsed time since interactive authentication, not just `fullyAuthenticated()`.

### 9.4. After logout, does the old cookie still log in?

Distinguish carefully:
- **Cookie remaining in the browser**: the logout handler must clear both the cookie and session properly.
- **A stolen copy of a token-based cookie captured before logout**: lacking a token store for targeted revocation, it can still verify successfully until expiration or password hash/key change. This is a design limitation, not a bug in `LogoutFilter`.
- **Persistent token**: the repository allows server-side token/series deletion; however, logout policy, all-devices logout, and token rotation still require explicit design and testing.

Never tell users that “clearing the cookie revokes all sessions/devices” if the server does not actually do so.

### 9.5. Does `RememberMeAuthenticationProvider` verify passwords?

**No.** It verifies the key hash of `RememberMeAuthenticationToken`. `TokenBasedRememberMeServices` verifies the cookie against user data and the key; `DaoAuthenticationProvider` is what verifies username/password during interactive login. Making this distinction prevents writing a faulty custom provider or assuming remember-me is as strong as password login.

## 10. Security principles to apply

- **Never log remember-me cookies, raw tokens, series/tokens, or secret keys** in access logs, tracing, exceptions, metric labels, or responses.
- **Issue cookies only on opt-in** when policy and UX require consent. Do not default to `alwaysRemember(true)` for everyone.
- **Use HTTPS/TLS**, `Secure`/`HttpOnly` cookies, and appropriate `SameSite`; verify reverse proxies and domain/path. Copied long-lived cookies can be replayed.
- **Do not disable CSRF unconditionally**: browsers still send cookies/sessions automatically on state-changing requests.
- **Separate trust levels:** `authenticated()` for routine endpoints, `fullyAuthenticated()` or step-up MFA/reauth for high-risk actions.
- **Limit token lifetimes**, plan signing key rotation, revocation, and detection of suspected copied tokens.
- **Never grant authorities from custom cookies or client data**; load roles from a trusted server source and enforce them in `AuthorizationFilter`.
- **Keep keys consistent across nodes** if token-based; if persistent, use a shared repository and sound concurrency policies.
- **Control user lifecycle**: password changes, account locks, offboarding, and role changes must have clear effects on remember-me.
- **Test session and cookie separately:** a request with an active session does not prove `RememberMeAuthenticationFilter` actually ran; create a fresh request carrying only the remember-me cookie.

## 11. Checklist and self-check exercises

### Pre-release checklist

- [ ] `UserDetailsService` and authentication provider use the proper password hash/user source.
- [ ] `RememberMeServices` and `RememberMeAuthenticationProvider` share the same key; no duplicate filter/provider.
- [ ] Remember-me tokens are issued only after valid interactive login and opt-in.
- [ ] Cookies are sent back by browsers on needed requests; HTTPS and cookie attributes are verified.
- [ ] A fresh request **without `JSESSIONID`** carrying a valid remember-me cookie restores the right user.
- [ ] Expired/tampered cookies, deleted users, or changed passwords do not produce valid authentication.
- [ ] Sensitive endpoints use `fullyAuthenticated()` or require re-authentication.
- [ ] Logout clears the browser cookie, and documentation accurately states replay/revocation limits.
- [ ] Persistent repository has migrations, indexes, backups, rotation, and a revocation policy.
- [ ] Remember-me cookies, keys, hashes, or tokens are not leaked in logs.

### Questions

1. At **which two points** are `RememberMeServices.loginSuccess` and `autoLogin` called?
2. When `SecurityContext` already holds an authentication from the session, does `RememberMeAuthenticationFilter` need to auto-login?
3. Which component verifies the token-based cookie signature, and which component verifies the key hash inside `RememberMeAuthenticationToken`?
4. Does `RememberMeAuthenticationProvider` compare raw passwords against password hashes like `DaoAuthenticationProvider`?
5. Why can `RememberMeAuthenticationToken.isAuthenticated()` be true while `fullyAuthenticated()` remains false?
6. With `maximumSessions` or logout, does remember-me automatically vanish across all devices?
7. What is the biggest difference regarding per-device revocation between token-based and persistent-token?
8. Why must tests omit `JSESSIONID` while keeping `remember-me` to prove auto-login?
9. If a new BCrypt hash is generated on each startup, how can token-based remember-me be affected?
10. If a user does not check remember-me, why does a successful login normally still create a session yet issue no remember-me cookie?

**Short answers:** (1) after interactive login and on a later request lacking authentication; (2) usually no; (3) the service and corresponding provider respectively; (4) no; (5) remembered is a lower trust level than fresh login; (6) not necessarily, explicit session/token policies are needed; (7) server storage enables revocation/rotation; (8) to avoid the test accidentally using the session; (9) changing the hash invalidates old cookie signatures; (10) session login and remember-me opt-in are two distinct mechanisms.

## 12. Official references

- Spring Security — Remember-Me Authentication (Servlet 6.5): https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/rememberme.html
- Spring Security — `RememberMeServices` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/RememberMeServices.html
- Spring Security — `RememberMeAuthenticationFilter` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/rememberme/RememberMeAuthenticationFilter.html
- Spring Security — `RememberMeAuthenticationProvider` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/RememberMeAuthenticationProvider.html
- Spring Security — `RememberMeAuthenticationToken` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/RememberMeAuthenticationToken.html
- Spring Security — `AuthenticationTrustResolver` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/AuthenticationTrustResolver.html
- Spring Security — Authorize HTTP Requests (authenticated vs fullyAuthenticated): https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html
- Spring Security — CSRF (Servlet): https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html
