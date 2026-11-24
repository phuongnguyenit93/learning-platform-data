# Revoking remember-me tokens on logout or account changes

## Lesson objectives

**Remember-me** allows a browser to be authenticated automatically on a later visit after the normal HTTP session has ended. Spring Security Servlet supports **signed/hashed cookies** and **server-stored persistent tokens**. When a user logs out, changes their password, recovers an account, locks an account, or updates security settings, we must decide **which tokens are still permitted to auto-login**.

This lesson covers **revoking remember-me tokens**, not merely clearing browser cookies. This is an important security distinction: a cookie cleared on the current device can still exist in a copy held by an attacker or another device.

After this lesson, you will be able to:

1. Explain accurately the difference between `TokenBasedRememberMeServices` and `PersistentTokenBasedRememberMeServices`.
2. Understand the flow **remember-me cookie → RememberMeAuthenticationFilter → RememberMeServices → PersistentTokenRepository → Authentication**.
3. Distinguish **clearing a cookie**, **deleting tokens in the repository**, **invalidating HttpSession**, and **revoking active sessions**.
4. Explain why Spring Security persistent remember-me typically deletes **all tokens for a username** on logout with Authentication, while password changes or account updates still need explicit revocation logic.
5. Build a Java 17+ / Spring Boot Servlet / JDBC remember-me app with a password-change endpoint that simultaneously deletes tokens and requires re-login.
6. Write test scenarios covering stale cookies, two devices, password changes, CSRF, and stolen-token risks.

**Scope:** Spring Security Servlet 6.5.x / Spring Boot 3.5.x and application-managed remember-me. This is **not** OAuth2 Refresh Tokens, OIDC logout, JWT blacklists, or Spring Session, though each has its own revocation concerns. Examples use in-memory H2 for learning; production must use a secure persistent store and a currently supported Spring version.

## 1. Three distinct states: HttpSession, remember-me cookie, server-side token

A browser may simultaneously carry:

- **HTTP session cookie**, usually `JSESSIONID`: lets the server restore the `SecurityContext` stored in `HttpSession` until the session expires or is invalidated.
- **Remember-me cookie**, defaulting to `remember-me`: proof allowing Spring Security to build an `Authentication` when the request **does not yet have an appropriate Authentication** in `SecurityContext`.
- **Persistent token record** in the database, if the application chooses `PersistentTokenBasedRememberMeServices`. This record lets the server verify and rotate cookie credentials.

Typical path:

~~~text
1. POST /login: username + password + remember-me=on
      |
      +--> AuthenticationManager verifies successfully
      +--> RememberMeServices.loginSuccess(...)
      +--> issues remember-me cookie
      +--> (if persistent) inserts persistent_logins row
      |
      v
2. GET /me: JSESSIONID still valid
      |
      +--> SecurityContext is read from HttpSession
      +--> usually NO need to auto-login via remember-me
      |
      v
3. GET /me: JSESSIONID gone, remember-me cookie present
      |
      +--> RememberMeAuthenticationFilter
      +--> RememberMeServices.autoLogin(...)
      +--> checks cookie / repository / UserDetailsService
      +--> may create RememberMeAuthenticationToken
      +--> if valid: proceeds as an authenticated user
~~~

From this it follows:

- **Logout destroying the session** does not mean a stolen remember-me cookie has lost validity.
- **Deleting remember-me tokens** does not automatically invalidate existing `HttpSession`s that already hold an Authentication. Requests with a valid session may no longer need the remember-me cookie.
- **Password changes** affect the two remember-me strategies differently.
- **Role changes/account locks** must consider both remember-me tokens and **previously authenticated sessions**, not just one token table.

## 2. Two remember-me styles and their revocation capabilities

### 2.1. TokenBasedRememberMeServices: signed/hashed cookie

The hash-based mechanism stores encoded authentication info in the cookie, bound to username, expiry, the user's stored password, and an application secret key. Spring Security's conceptual formula:

~~~text
cookie = Base64(
    username : expiryTime : algorithmName : signature
)

signature = hash(
    username : expiryTime : passwordHashFromUserDetails : applicationKey
)
~~~

This formula illustrates the inputs participating in verification; exact formatting and algorithms depend on Spring Security version/properties. Do not hand-roll remember-me signatures manually.

**Ways to invalidate:**

- **Change the user's password hash**: old cookies fail verification because the server password hash changed.
- **Rotate the secret key**: invalidates old cookies for **all users** relying on that key.
- **Wait for expiration**: cookies become invalid once past their validity check.

**Limitation:** the server **has no list of individual tokens** per user to delete. On logout, Spring Security can clear the cookie in the current device's response, yet a stolen copy of a hash-based cookie remains valid until password/key changes or the token expires.

If you genuinely need “Log out of all devices” or “Revoke a specific device”, hash-based remember-me has serious limitations. You can either embed a server-side security/token version in a custom mechanism or switch to **persistent remember-me**; never claim client cookie deletion is server-side revocation.

### 2.2. PersistentTokenBasedRememberMeServices: server verifies by series

The persistent mechanism uses `PersistentTokenRepository`, typically `JdbcTokenRepositoryImpl`, storing these fields:

| Field | Meaning |
| --- | --- |
| `username` | Token owner, used to manage and delete tokens by user |
| `series` | Token series ID, unique/primary key; identifies a remember-me series |
| `token` | Current token value of the series, must match the cookie |
| `last_used` | Most recent usage timestamp, used to check token age |

Common SQL schema:

~~~sql
create table persistent_logins (
    username varchar(64) not null,
    series varchar(64) primary key,
    token varchar(64) not null,
    last_used timestamp not null
);
~~~

Persistent cookies typically carry **series + token** without needing a plaintext username. The server looks up the series in the database and verifies the current token and expiration.

**Token rotation:** after successful auto-login, Spring Security can generate a **new token value within the same series**, update the repository, and send a new cookie. An old cookie copy immediately becomes invalid after that use. If the series still exists while the token differs, the framework can treat it as suspected cookie theft (`CookieTheftException`) and call `removeUserTokens(username)`.

**Active deletion mechanism:** the `PersistentTokenRepository` interface provides:

~~~java
void removeUserTokens(String username);
~~~

This method deletes **remember-me tokens for the specified user**. With the default JDBC repository, it deletes matching rows in `persistent_logins`. After deletion, previously issued cookies are no longer accepted by the repository when the browser presents only a remember-me cookie.

Note: the default API **does not provide a delete-by-series-ID operation**. If you want “sign out current device only”, extend the repository and remember-me service/handler with series ownership verification and race/rotation handling; do not try to misuse `removeUserTokens(username)` as a per-device function.

## 3. What happens when a user logs out?

### 3.1. Logout path managed by Spring Security

In a Servlet app with standard `formLogin()`, `rememberMe()`, and `logout()`, `LogoutFilter` coordinates `LogoutHandler`s:

~~~text
POST /logout (valid CSRF)
       |
       v
LogoutFilter
       |
       +--> SecurityContextLogoutHandler
       |      - invalidate HttpSession (per configuration)
       |      - clear SecurityContext
       |
       +--> RememberMeServices logout handling
       |      - clear remember-me cookie in response
       |      - persistent remember-me: may delete server-side tokens
       |
       +--> CsrfLogoutHandler / event-related handlers
       |
       v
LogoutSuccessHandler (defaults typically to redirect /login?logout)
~~~

**You do not need a custom `POST /logout` controller** just to clear the remember-me cookie. Use `http.logout(...)` and wire remember-me properly so the framework runs every required handler.

### 3.2. Specific detail of persistent remember-me

In Spring Security 6.5, `PersistentTokenBasedRememberMeServices.logout(request, response, authentication)` invokes its parent cookie-clearing logic and, **when Authentication is non-null**, deletes the username's tokens via `PersistentTokenRepository.removeUserTokens(authentication.getName())`.

Common consequences:

1. **Logging out on device A** with a valid Authentication → remember-me cookie on A is cleared.
2. **All remember-me rows for that username** may be deleted from the repository.
3. Device B may still hold an old remember-me cookie, yet if it **lacks an authenticated HttpSession**, it cannot use the revoked cookie to auto-login again.
4. If B **still has a valid HttpSession**, B can continue accessing via that session. Deleting remember-me rows **does not automatically destroy B's session**.

That is why saying “logout immediately signs out every device” is **overstated**. More accurately: with standard persistent remember-me integration, an authenticated logout can **revoke remember-me auto-login across all devices**, without automatically destroying every active session.

**When Authentication is null:** the persistent implementation deletes server-side tokens only when an Authentication supplies the username. If a logout request lacks Authentication, you cannot assume all of the user's rows were deleted. Define fallback behavior according to your threat model.

### 3.3. Clearing cookies is not the only step

Additional configuration example:

~~~java
http.logout(logout -> logout
    .deleteCookies("remember-me")
);
~~~

The snippet above **only illustrates cookie clearing**. With persistent remember-me, standard remember-me services already have a logout hook; clearing the cookie alone **does not replace row revocation** if you write a custom logout endpoint or use a custom `RememberMeServices`.

If the app customizes cookie name, domain/path, or runs behind a reverse proxy, make sure cookie deletion uses the matching name, path/domain, and attributes. A returned `Set-Cookie` may fail to clear the right cookie if path/domain mismatch. Never ask the browser to echo secret credentials in responses or logs for “debugging”.

## 4. Why do password changes need an explicit revocation strategy?

Suppose a user changes their password because they suspect unauthorized account access.

### With hash-based cookies

Because remember-me signatures depend on the password hash from `UserDetails`, **if the password hash actually changes**, old cookies fail hash verification on the next auto-login.

Limitations:

- This mechanism does not automatically destroy existing `HttpSession`s.
- Changing **email, phone, MFA, account status, or authorities** does not necessarily change the password hash, so remember-me tokens may stay valid.
- If a custom `UserDetailsService` returns inconsistent hashes or the app changes algorithms/keys, compatibility must be tested.

### With persistent tokens

`persistent_logins` records **do not depend directly on the password hash**. Hence **changing the password does not guarantee** old persistent tokens become invalid.

Intentional approach:

~~~java
// Inside a service handling security updates for an authenticated account.
// username comes from trusted server identity, not client-supplied JSON.
userService.updatePassword(username, newEncodedPassword);
persistentTokenRepository.removeUserTokens(username);
~~~

This is **illustrative code**, not a standalone Java class. You must verify the current password / step-up authentication, guarantee atomicity, and handle failures. Never delete by an arbitrary `username` sent in the request body, to prevent revoking someone else's tokens.

Events that commonly warrant revoking remember-me tokens:

| Event | Policy to consider |
| --- | --- |
| **Password change** requested by user | Delete all of the user's remember-me tokens; invalidate other sessions per threat model |
| **Forgot password / password reset** via email | Delete remember-me tokens after successful reset; review active sessions |
| **Changing email used as username** | Delete tokens under the **old** username before/alongside changing the identifier |
| **Changing phone or MFA/2FA** | Require re-authentication; delete tokens if security policy treats it as a sensitive change |
| **Locking/disabling account** | Revoke remember-me tokens, handle active sessions, and reject new authentications |
| **Deleting account** | Delete related tokens and sessions; purge data per policy |
| **Suspected cookie theft** | Revoke all remember-me tokens, alert/investigate, and consider invalidating other sessions |
| **Role/authority change** | Do not only delete tokens; inspect cached Authentication in sessions and re-authorize |
| **Log out all devices** | Revoke remember-me tokens and invalidate active sessions per policy |

**Changing a display email that is not the login identifier** can carry different risks; apply policy according to your threat model and actual identifiers.

## 5. Runnable example: Persistent remember-me with JDBC and password change

Demo goals:

- Use **Spring Boot 3.5.16, Java 17+**, Spring Security Servlet, and in-memory H2.
- User `demo` with initial password `change-me` logs in via form and selects **remember-me**.
- `JdbcTokenRepositoryImpl` stores tokens in the `persistent_logins` table.
- Endpoint `POST /account/change-password` verifies the current password, updates the password hash, and **calls removeUserTokens(username)** within the same JDBC transaction.
- On success, invalidates the **current session** and clears the remember-me cookie, forcing the client to log in again.
- Exposes a CSRF token via `GET /csrf` for testing with curl. **CSRF is not disabled**.

**Demo limitation:** the in-memory H2 database loses data when the app stops. Demo accounts and the remember-me key in properties are for local use only. Spring Boot 3.5.16 is the final OSS release on the 3.5 branch; **new production systems should choose a currently supported Spring Boot branch** and compatible Spring Security version.

### 5.1. Project structure

~~~text
remember-revocation-demo/
  settings.gradle
  build.gradle
  src/main/resources/application.properties
  src/main/resources/schema.sql
  src/main/java/example/remember/RememberRevocationApplication.java
~~~

**settings.gradle:**

~~~groovy
rootProject.name = 'remember-revocation-demo'
~~~

**build.gradle:**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
}
~~~

**src/main/resources/application.properties:**

~~~properties
spring.datasource.url=jdbc:h2:mem:rememberdemo;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always

server.port=8080
app.remember-me.key=local-demo-only-not-a-production-secret
~~~

**Note:** in production, load `app.remember-me.key` from a secret manager/secure environment variable and never commit real keys to Git. Instances of the same app must share compatible keys; rotating keys invalidates hash-based cookies and can affect remember-me service compatibility. Never use in-memory H2 to share remember-me across multiple instances.

**src/main/resources/schema.sql:**

~~~sql
create table users (
    username varchar(50) not null primary key,
    password varchar(500) not null,
    enabled boolean not null
);

create table authorities (
    username varchar(50) not null,
    authority varchar(50) not null,
    constraint fk_authorities_users
        foreign key (username) references users(username)
);

create unique index ix_auth_username
    on authorities (username, authority);

create table persistent_logins (
    username varchar(64) not null,
    series varchar(64) primary key,
    token varchar(64) not null,
    last_used timestamp not null
);
~~~

The first two tables match `JdbcUserDetailsManager`'s default queries for simple scenarios. The `persistent_logins` table is the persistent remember-me schema documented by Spring Security. In production, use versioned migrations, database-appropriate indexes/constraints, connection limits, backups, and cleanup; do not run `create table` on every startup.

### 5.2. Complete Java code

Create **src/main/java/example/remember/RememberRevocationApplication.java**:

~~~java
package example.remember;

import java.util.Map;

import javax.sql.DataSource;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.JdbcUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.logout.CookieClearingLogoutHandler;
import org.springframework.security.web.authentication.logout.SecurityContextLogoutHandler;
import org.springframework.security.web.authentication.rememberme.JdbcTokenRepositoryImpl;
import org.springframework.security.web.authentication.rememberme.PersistentTokenRepository;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class RememberRevocationApplication {

    public static void main(String[] args) {
        SpringApplication.run(RememberRevocationApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    JdbcUserDetailsManager users(DataSource dataSource) {
        return new JdbcUserDetailsManager(dataSource);
    }

    @Bean
    PersistentTokenRepository persistentTokenRepository(
            DataSource dataSource) {
        JdbcTokenRepositoryImpl repository = new JdbcTokenRepositoryImpl();
        repository.setDataSource(dataSource);
        return repository;
    }

    @Bean
    ApplicationRunner seedDemoUser(
            JdbcUserDetailsManager users, PasswordEncoder encoder) {
        return args -> {
            if (!users.userExists("demo")) {
                users.createUser(User.withUsername("demo")
                    .password(encoder.encode("change-me"))
                    .roles("USER")
                    .build());
            }
        };
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            JdbcUserDetailsManager users,
            PersistentTokenRepository persistentTokens,
            Environment environment) throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/csrf").permitAll()
                // Sensitive action: remember-me-only is not enough.
                .requestMatchers("/account/change-password")
                    .fullyAuthenticated()
                .anyRequest().authenticated()
            )
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED)
            )
            .formLogin(Customizer.withDefaults())
            .rememberMe(remember -> remember
                .key(environment.getRequiredProperty("app.remember-me.key"))
                .userDetailsService(users)
                .tokenRepository(persistentTokens)
                .rememberMeParameter("remember-me")
                .tokenValiditySeconds(7 * 24 * 60 * 60)
            )
            .logout(Customizer.withDefaults());

        return http.build();
    }

    @Service
    public static class PasswordChangeService {
        private final JdbcUserDetailsManager users;
        private final PasswordEncoder encoder;
        private final PersistentTokenRepository persistentTokens;

        public PasswordChangeService(
                JdbcUserDetailsManager users,
                PasswordEncoder encoder,
                PersistentTokenRepository persistentTokens) {
            this.users = users;
            this.encoder = encoder;
            this.persistentTokens = persistentTokens;
        }

        // Both updateUser and removeUserTokens share the same DataSource.
        @Transactional
        public boolean changePassword(
                String verifiedUsername,
                String currentPassword,
                String newPassword) {

            if (currentPassword == null
                    || newPassword == null
                    || newPassword.length() < 12) {
                return false;
            }

            // Identity comes from verified Authentication.
            UserDetails current = users.loadUserByUsername(
                verifiedUsername
            );

            if (!encoder.matches(
                    currentPassword, current.getPassword())) {
                return false;
            }

            UserDetails updated = User.withUserDetails(current)
                .password(encoder.encode(newPassword))
                .build();

            users.updateUser(updated);

            // Revoke ALL remember-me tokens for the user.
            persistentTokens.removeUserTokens(verifiedUsername);

            return true;
        }
    }

    @RestController
    public static class Api {
        private final PasswordChangeService passwords;

        public Api(PasswordChangeService passwords) {
            this.passwords = passwords;
        }

        public record ChangePassword(
                String currentPassword, String newPassword) {
        }

        public record CsrfInfo(String headerName, String token) {
        }

        @GetMapping("/csrf")
        public CsrfInfo csrf(CsrfToken token) {
            return new CsrfInfo(
                token.getHeaderName(),
                token.getToken()
            );
        }

        @GetMapping("/")
        public String home(Authentication authentication) {
            return "hello, " + authentication.getName();
        }

        @GetMapping("/me")
        public Map<String, String> me(Authentication authentication) {
            return Map.of(
                "username", authentication.getName(),
                "authenticationType",
                    authentication.getClass().getSimpleName()
            );
        }

        @PostMapping("/account/change-password")
        public ResponseEntity<Void> changePassword(
                @RequestBody ChangePassword body,
                Authentication authentication,
                HttpServletRequest request,
                HttpServletResponse response) {

            boolean changed = passwords.changePassword(
                authentication.getName(),
                body.currentPassword(),
                body.newPassword()
            );

            if (!changed) {
                return ResponseEntity.status(HttpStatus.BAD_REQUEST)
                    .build();
            }

            // Clear cookie in current browser (demo root path).
            new CookieClearingLogoutHandler("remember-me")
                .logout(request, response, authentication);

            // Invalidate current session and SecurityContext.
            new SecurityContextLogoutHandler()
                .logout(request, response, authentication);

            return ResponseEntity.noContent().build();
        }
    }
}
~~~

### 5.3. Explaining the revocation flow in code

**1. Server-side token store exists.** `PersistentTokenRepository` is wired to H2 via `JdbcTokenRepositoryImpl`. When `http.rememberMe().tokenRepository(...)` is configured, Spring Security uses persistent remember-me instead of the default hash-based cookie.

**2. Passwords are stored encoded.** `PasswordEncoderFactories.createDelegatingPasswordEncoder()` produces password hashes prefixed with the algorithm ID rather than storing plaintext passwords. The demo user is seeded only if absent.

**3. Password-change endpoint requires full authentication.** `.fullyAuthenticated()` blocks a request holding only `RememberMeAuthenticationToken` from performing the sensitive action; the user must authenticate interactively with credentials. Additionally, the service verifies **currentPassword**.

**4. Do not trust client-supplied usernames.** Username comes from `Authentication.getName()`, with no `username` field in the request body. This prevents deleting another account's tokens.

**5. Updating password + removing tokens in one transaction.** `@Transactional` on the service coordinates `JdbcUserDetailsManager.updateUser(...)` and `PersistentTokenRepository.removeUserTokens(...)` over the same DataSource/transaction manager. If a DB operation fails and throws an exception, the transaction normally rolls back. **Never catch the exception and return success** when token revocation failed.

**6. Response cleanup happens only after success.** The controller clears the browser's remember-me cookie and invokes `SecurityContextLogoutHandler` to invalidate the current session. Because the transactional service is called through a Spring proxy, the transaction commits before the controller returns 204.

**7. Other sessions are not invalidated automatically.** This code has no distributed session registry or “log out all active sessions” feature. It **revokes the user's remember-me tokens** and **invalidates the current request's session**. If two browsers hold active `HttpSession`s, ending both requires session management by ID/user.

**8. CSRF is not disabled.** POST login, POST logout, and POST change-password require valid tokens; automatic browser cookie submission is a major reason CSRF protection is needed. `GET /csrf` lets same-origin clients obtain the token whenever Spring Security issues or rotates it.

**9. Cookie path/domain must match.** `CookieClearingLogoutHandler("remember-me")` fits the demo's default root path. If an app customizes cookie name/path/domain/SameSite, configure matching cleanup. Do not copy this example verbatim across subdomains expecting all cookies to clear properly.

**10. Demo validation is minimal.** Production requires password policies, rate limiting, auditing, step-up authentication for email/MFA changes, brute-force defenses, and PII protection. In-memory H2 loses data on shutdown and must never be claimed as production persistence.

## 6. Running the application and verifying with curl

From a project directory with a Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

If the project lacks a wrapper while a compatible Gradle is installed, run `gradle bootRun`. The sample Spring Boot app listens on `http://localhost:8080`.

The commands below use **Bash/WSL/Git Bash**, `curl`, and `python3`. You can adapt them to PowerShell/`curl.exe` with corresponding JSON parsing. **Never commit cookie jar files to a repository or paste them into logs/chats.**

### 6.1. Fetching the initial CSRF token

~~~bash
csrf=$(curl -fsS -c login-cookies.txt \
  http://localhost:8080/csrf \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["token"])')

test -n "$csrf"
~~~

`GET /csrf` may create a session to store the CSRF token. Use `-c` and `-b` to preserve cookies consistently across subsequent requests.

### 6.2. Form login with remember-me checked

~~~bash
curl -i -b login-cookies.txt -c login-cookies.txt \
  -H "X-CSRF-TOKEN: $csrf" \
  --data-urlencode "username=demo" \
  --data-urlencode "password=change-me" \
  --data-urlencode "remember-me=on" \
  http://localhost:8080/login
~~~

The result is typically **302 Redirect** upon successful login. The response may update the session cookie and send the **remember-me** cookie. Header ordering varies by browser/curl; inspect actual status and cookies.

The H2 store will contain a `persistent_logins` row for user `demo`. That row is server-side proof of remember-me, not merely a cookie in the browser.

### 6.3. Isolating a remember-me cookie before revocation

To simulate a copied old cookie, **strip JSESSIONID** from the cookie jar. Otherwise, requests might succeed via `HttpSession`, leading to false conclusions about remember-me revocation.

Netscape-format cookie files written by curl put the cookie name in the sixth column. Filter out `JSESSIONID`:

~~~bash
awk -F '\t' '$6 != "JSESSIONID"' \
  login-cookies.txt > remembered-before.txt
~~~

`remembered-before.txt` retains the **remember-me** cookie (and any unrelated cookies) without `JSESSIONID`. **Do not use this remember-me cookie to auto-login before running the revocation test**, because persistent remember-me uses **token rotation**: using it earlier rotates the token and makes the saved copy invalid beforehand, defeating the revocation test.

To test auto-login **before revocation**, run a separate login scenario and let curl update the cookie jar; never reuse an old token after it has already been rotated.

### 6.4. Logout and attempting to replay the old remember-me cookie

Fetch a new CSRF token after login, since the pre-login token may have been cleared/rotated:

~~~bash
csrf=$(curl -fsS -b login-cookies.txt -c login-cookies.txt \
  http://localhost:8080/csrf \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["token"])')

curl -i -b login-cookies.txt -c login-cookies.txt \
  -H "X-CSRF-TOKEN: $csrf" \
  -X POST http://localhost:8080/logout
~~~

The result is usually **302** to `/login?logout`. With persistent remember-me, an authenticated logout also invokes token deletion for the username.

Attempt to replay the old remember-me cookie without sending a session:

~~~bash
curl -i -b remembered-before.txt \
  http://localhost:8080/me
~~~

**Expected:** the request is not auto-authenticated by the revoked cookie; with form login, the result is usually **302** to `/login` (not always 401). Calling `/me` with a jar still holding a valid `JSESSIONID` fails to isolate remember-me.

### 6.5. Changing password and forcing re-login

Start a **fresh** login with the old password and `remember-me=on`, writing to a new `password-cookies.txt` file. Fetch CSRF and log in as in sections 6.1–6.2, then snapshot the remember-me cookie before changing the password:

~~~bash
awk -F '\t' '$6 != "JSESSIONID"' \
  password-cookies.txt > password-remembered-before.txt
~~~

Fetch the current CSRF token after login and call the endpoint:

~~~bash
csrf=$(curl -fsS -b password-cookies.txt -c password-cookies.txt \
  http://localhost:8080/csrf \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["token"])')

curl -i -b password-cookies.txt -c password-cookies.txt \
  -H "Content-Type: application/json" \
  -H "X-CSRF-TOKEN: $csrf" \
  --data '{"currentPassword":"change-me","newPassword":"new-strong-pass-2026"}' \
  http://localhost:8080/account/change-password
~~~

**Expected:** **204 No Content**. The service updates the password hash and deletes the user's persistent tokens; the browser cookie and current session are cleared. When replaying `password-remembered-before.txt` without `JSESSIONID`:

~~~bash
curl -i -b password-remembered-before.txt \
  http://localhost:8080/me
~~~

**Expected:** cannot auto-login; a form-login app usually redirects to `/login`. The new password works for interactive login; the old password is no longer valid.

**Demo data state note:** H2 `jdbc:h2:mem:` loses data when the process stops. During testing, do not restart the app between changing the password and replaying the cookie; restarting H2 wipes the token row because the DB resets, rendering the invalidation test meaningless.

## 7. Revocation limits to state accurately

### 7.1. Revoking remember-me is not equivalent to logging out all sessions

Example:

~~~text
Device A:
  - JSESSIONID = session-A
  - remember-me = series-A/token-A

Device B:
  - JSESSIONID = session-B (still valid)
  - remember-me = series-B/token-B

User changes password on A:
  - delete persistent_logins where username = user
  - invalidate session-A
  - clear remember-me cookie on A

Afterward:
  - A must log in again
  - B can still access via valid session-B
  - Once session-B expires, remember-me cookie B cannot auto-login again
~~~

To **terminate all authenticated sessions**, manage sessions by principal and delete/invalidate them in the corresponding session store. In multi-node apps with Spring Session, you can use APIs that look up sessions by principal when an indexed repository is configured. With local `HttpSession`, each node knows only its own sessions. Never rely on clearing a single cookie to claim cluster-wide revocation.

Some systems adopt a **security version/account epoch**: storing a security version number on the account, embedding it in session/token state, and re-checking it on incoming requests. When the account changes, bumping the version invalidates stale state. This is an additional design pattern, not built-in behavior of `PersistentTokenBasedRememberMeServices`.

### 7.2. Single-device logout vs. all-device logout

With default persistent remember-me, `removeUserTokens(username)` deletes all series for the user. If you want “sign out only the current device” while keeping remember-me on other devices, you need a custom token repository supporting **delete-by-series**.

Requirements:

- Identify the series from the cookie and verify ownership before deleting.
- Prevent races between auto-login rotation and revocation, especially under concurrent requests.
- Never allow a user to specify another user's series for deletion.
- Still offer a **revoke all** path for lost devices, password resets, or security changes.
- Consider event/audit logging and visibility after transaction commit.

You cannot call `PersistentTokenRepository.removeUserTokens(username)` directly and claim it only signs out one device.

### 7.3. Two concurrent requests and rotation

Some browsers fire multiple near-simultaneous requests carrying the same remember-me cookie **before a new session is established**. If the first request rotates the token, the second request may still carry the old token for the same series. The framework can treat this as a mismatched token/cookie theft and delete the user's tokens.

Therefore, when testing multiple tabs or heavy loads, do not replay an old cookie repeatedly and mistake anti-theft detection for a random bug. Real products must test concurrency, cookie races, and login-session coordination; **never disable token rotation or ignore `CookieTheftException` just to make tests pass**.

### 7.4. Expired tokens whose rows have not been purged

`PersistentTokenBasedRememberMeServices` rejects tokens older than `tokenValiditySeconds`, yet does not automatically delete all expired rows from the database.

Implement **periodic cleanup** on `persistent_logins.last_used` based on your actual retention/validity policy, e.g., illustrative SQL:

~~~sql
-- Run on a schedule in production once TTL has been evaluated.
delete from persistent_logins
where last_used < CURRENT_TIMESTAMP - INTERVAL '30' DAY;
~~~

Date/interval syntax differs across H2/PostgreSQL/MySQL; adjust for your dialect and policy. Never purge rows at an age shorter than `tokenValiditySeconds` unless you intend to log users out early. Do not confuse scheduled cleanup of expired rows with immediate revocation on security events.

## 8. Account changes inside one transaction: consistency perspective

### 8.1. Single-database case

In the demo, `JdbcUserDetailsManager` and `JdbcTokenRepositoryImpl` share the same **DataSource**. Under `@Transactional`:

~~~text
BEGIN TRANSACTION
  -> verify current credential / policy
  -> UPDATE users SET password = ...
  -> DELETE FROM persistent_logins WHERE username = ...
COMMIT

After COMMIT:
  -> clear cookie on response
  -> invalidate current session
  -> client must log in again
~~~

If the password update succeeds in the DB yet token deletion fails and the transaction rolls back, the change is not reported as successful. This better satisfies the requirement “changing password must also revoke remember-me capability”.

**Do not write:**

~~~java
// Illustrates an UNSAFE PATTERN.
try {
    persistentTokenRepository.removeUserTokens(username);
} catch (Exception ignored) {
    // Then returns 200 "password changed" even though old tokens remain valid.
}
~~~

If security policy requires tokens to be revoked, **never swallow errors and return success**. Fail closed, log the event without exposing secrets, and provide a recovery procedure.

### 8.2. When the user store and token store are separate

For example, accounts reside in PostgreSQL while remember-me tokens reside in Redis or another service. A standard `@Transactional` cannot span both.

Consistency design is needed:

- Execute revocation/token-version updates in a defined security order.
- Use outbox/event delivery with retries and idempotency where appropriate.
- While propagation is pending, ensure old tokens **cannot continue granting access against policy**; an account security epoch checked at authentication time may be needed.
- Avoid “illusory” rollbacks: updating DB A when store B is unreachable must not claim revocation succeeded in B.
- Monitor failed revocation events, alert, and reconcile.

For sensitive changes (password reset after suspected account takeover), prefer **rejecting old tokens immediately** until completion rather than leaving an unannounced window where old tokens still work.

### 8.3. Changing username/email used as ID

`PersistentTokenRepository.removeUserTokens` takes `username`. If a system changes a login identifier from `old@example.com` to `new@example.com`, verify:

1. Which **ID** is stored in `persistent_logins.username`?
2. Must deletion run against the **old username** before or alongside updating the username?
3. Does `UserDetailsService.loadUserByUsername` still accept the old ID?
4. How should active user sessions be invalidated or have their principals updated?

Calling `removeUserTokens(newUsername)` after renaming can leave orphaned rows keyed by the old username. In production, prefer a **stable account ID** for custom token systems mapped cleanly to users; with standard JDBC remember-me, understand the repository's username key before changing identifiers.

## 9. When should re-authentication be required?

Remember-me is generally considered lower trust than direct credential entry, since cookies can sit on devices for days. For actions like changing passwords, changing MFA, changing login emails, creating API keys, or viewing sensitive data, require:

- **Interactive/fresh authentication**, not `RememberMeAuthenticationToken` alone.
- Current credential verification or step-up MFA per policy.
- CSRF protection when browsers use cookies.
- Rate limiting on sensitive actions and redacted audit logs.

Spring Security offers the **`fullyAuthenticated()`** authorization expression to distinguish fully authenticated requests from remember-me-only. In the example:

~~~java
.requestMatchers("/account/change-password").fullyAuthenticated()
~~~

That stops someone holding only a remember-me cookie from directly invoking the password-change endpoint in the demo. However, `fullyAuthenticated()` does not prove MFA was just completed or that the session is recent; high-assurance apps must also verify **re-auth timestamp** and additional authentication factors.

## 10. Matrix for testing proper revocation

| Scenario | Expected result |
| --- | --- |
| Form login without remember-me checked | No new persistent remember-me cookie issued |
| Login with remember-me | Persistent token row saved; cookie issued |
| JSESSIONID still valid | User can authenticate via session without needing remember-me yet |
| Valid remember-me cookie only | Auto-login succeeds; token may rotate |
| Authenticated logout | Current session ends; current cookie cleared; username's persistent tokens deleted |
| Replay old remember-me cookie **without session** after logout | Auto-login fails |
| Successful password change | Password hash updated, all persistent tokens for user deleted, current session invalidated |
| Wrong current password | Password is not updated and success revocation flow does not run |
| POST password change missing CSRF | 403 before controller; no data changed |
| Remember-me-only Authentication calls fullyAuthenticated endpoint | Rejected; full login required |
| New password, interactive login | Succeeds |
| Old password after change | Fails |
| Another active session remains open | May continue unless an invalidate-all-sessions policy is implemented |
| Concurrent auto-login using the same cookie | Must handle rotation/races; do not assume all requests succeed |
| Database error during removeUserTokens | Do not report security update revocation as succeeded when incomplete |

### Spring Security Test integration tips

When a project includes `spring-security-test` and `MockMvc`, test at the Servlet layer:

~~~groovy
testImplementation 'org.springframework.security:spring-security-test'
testImplementation 'org.springframework.boot:spring-boot-starter-test'
~~~

In integration tests, use `MockMvc`/cookie jars to:

- Log in via form with `remember-me=on` and valid CSRF.
- Verify the repository stored the token for the username.
- Log out, then re-read the repository/DB to confirm the row was deleted.
- Send only the old remember-me cookie **without HttpSession**, verifying rejection.
- Change password in a fully authenticated session, verifying the new hash, zero remaining token rows, and invalidated current session.
- Test account update rollback when repository token deletion throws an exception.
- Check other sessions per system policy (if invalidate-all exists).

**Do not assert only HTTP 302/204.** A 302 can occur because the user wasn't logged in or because of CSRF; inspect repository state and cookie replay behavior.

## 11. Production operations and additional risks

### 11.1. Cookie security

- Transmit remember-me cookies only over **HTTPS/TLS**; enable `Secure`, `HttpOnly`, and appropriate `SameSite`; keep cookie domain/path as narrow as possible.
- Never embed cookies in URLs, emails, redirect queries, or logs.
- Never treat `remember-me` as a replacement for sessions, MFA, or server-side revocation management.
- Balance `tokenValiditySeconds` between UX and risk: long-lived cookies expand the attack window when lost.
- With multiple instances, keep key/cookie/store configuration compatible; never use `InMemoryTokenRepositoryImpl` in a production cluster.

### 11.2. PersistentTokenRepository and data safety

- With JDBC, protect the database via least privilege, backups, and migrations; only necessary applications/services may access `persistent_logins`.
- Protect `series` and `token` as sensitive data; never log raw values or expose the token table to users.
- If displaying an online device list, never expose series/tokens in responses; return only bounded metadata like device label/time, and verify ownership before revoking.
- Review concurrency across login/rotation/revocation. Transactions and a unique series constraint prevent collisions, yet do not solve every multi-request race.
- Purge expired rows on a schedule; do not rely on the framework to clean up every old row.

### 11.3. Security notifications and auditing

On password change, password reset, account lock, or detected token theft, emit structured events: account ID, action, timestamp, normalized IP/trusted-proxy metadata, and correlation ID—never storing tokens, cookies, or passwords. Notify users over a verified channel when product policy calls for it.

If a user reports a lost device, trigger a revoke-all flow and review active sessions; merely “clearing the cookie on the active device” is insufficient. If the user holds API tokens, OAuth refresh tokens, or other SSO sessions, revoking remember-me does not replace revoking those credentials.

### 11.4. Security claims to avoid

- “Changing password automatically deletes all persistent remember-me tokens”: **false without `removeUserTokens` logic**.
- “Logout only clears cookies, so persistent remember-me never revokes server-side”: **false for standard persistent implementations with Authentication**, since they delete tokens by username.
- “Deleting `persistent_logins` immediately logs out all browsers”: **false** if a browser still holds an authenticated `HttpSession`.
- “The remember-me cookie is JSESSIONID”: **false**; they are two distinct cookies with different roles.
- “Using persistent tokens means CSRF protection isn't needed”: **false**; browsers still send cookies automatically.
- “One persistent token row equals one HttpSession”: **incorrect**; lifecycles and counts are not necessarily one-to-one.
- “Revocation can be verified by testing an already-rotated old cookie”: **invalid**, because that cookie was already invalidated prior to revocation.

## 12. Self-check exercises

**Q1.** A user logs out with persistent remember-me and a valid Authentication. What does the repository typically do?

**Answer:** `PersistentTokenBasedRememberMeServices.logout(...)` can call `removeUserTokens(username)`, revoking the username's remember-me rows while also clearing the response cookie.

**Q2.** After logging out on device A, device B still holds an authenticated `HttpSession`. Is B logged out immediately?

**Answer:** Not necessarily. Revoking remember-me tokens prevents **future auto-login**, while active `HttpSession`s must be invalidated separately if all-session logout is required.

**Q3.** Does changing the password invalidate hash-based cookies?

**Answer:** Usually yes, because the signature depends on the password hash returned by `UserDetailsService`; however, it does not automatically invalidate active `HttpSession`s.

**Q4.** With persistent remember-me, is updating the password in the `users` table enough?

**Answer:** No. Persistent tokens do not directly depend on the password hash; you must explicitly call `PersistentTokenRepository.removeUserTokens(username)` and review active sessions.

**Q5.** Why must you never call `removeUserTokens(requestBody.username)` using a client-supplied username?

**Answer:** A client could supply another username to revoke someone else's tokens. The principal must come from verified Authentication or an authorized admin workflow.

**Q6.** When changing a login username/email, which username should be passed to delete rows?

**Answer:** Verify the key stored in `persistent_logins`. Normally you must delete by the **old username** before or alongside changing the identifier, not blindly by the new username.

**Q7.** Two concurrent requests carrying the same persistent cookie are processed simultaneously, and one rotates the token. What error might the other encounter?

**Answer:** The token for the same series no longer matches, which can be detected as cookie theft and lead to deleting the user's tokens. Test races and avoid replaying old cookies carelessly.

**Q8.** Why is a transaction needed for password change and persistent token deletion?

**Answer:** To avoid reporting the account as secured after changing the password while old tokens survive due to a deletion error. Within the same DB, `@Transactional` helps roll back related changes on exception.

**Q9.** When holding only remember-me authentication, which authorization rule should the password-change endpoint use in the example?

**Answer:** `fullyAuthenticated()`, combined with current password verification or policy step-up, and CSRF protection.

**Q10.** If a single device must be revoked without affecting other devices, is the default `removeUserTokens(username)` API suitable?

**Answer:** No. It deletes every series for that user. You need a custom repository and service supporting revocation by series verified to belong to the user.

## Official documentation

- [Spring Security 6.5 — Remember-Me Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/rememberme.html)
- [Spring Security 6.5 — Handling Logouts](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/logout.html)
- [Spring Security 6.5 — PersistentTokenBasedRememberMeServices API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/rememberme/PersistentTokenBasedRememberMeServices.html)
- [Spring Security 6.5 — PersistentTokenRepository API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/rememberme/PersistentTokenRepository.html)
- [Spring Security 6.5 — RememberMeConfigurer API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/annotation/web/configurers/RememberMeConfigurer.html)
- [Spring Security 6.5 — JDBC Authentication and UserDetailsManager](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/jdbc.html)
- [Spring Security 6.5 — Database Schema](https://docs.spring.io/spring-security/reference/6.5/servlet/appendix/database-schema.html)
- [Spring Security 6.5 — Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html)
