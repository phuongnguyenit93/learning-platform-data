# PersistentTokenBasedRememberMeServices and PersistentTokenRepository

> **Context:** Spring Security 6 on the **Servlet stack**, Java 17+, Spring Boot 3.x. Topic under **Remember-me**: how `PersistentTokenBasedRememberMeServices` maintains login after an HTTP session is gone, the `PersistentTokenRepository` contract, `series/token` pair structure, token rotation, misuse detection, implementation with `JdbcTokenRepositoryImpl`, and operational risks. This is a **browser** remember-me mechanism; it is not an OAuth2 refresh token, API key, or session replacement.

## 1. What Problem Does Remember-me Solve?

Web applications typically create an **HTTP session** after a user logs in with username/password. The browser carries a session cookie (usually `JSESSIONID`), and the server loads the `SecurityContext` from that session so it does not re-verify the password on every request. When the session expires, the browser is closed, the session is invalidated, or the server loses state, the user normally must log in again.

**Remember-me** allows an app to use **a separate long-lived cookie** to auto-authenticate the user when a new request lacks a valid `Authentication` in `SecurityContext`. The user can check the “Remember me” box on the login form. When the normal session expires, a valid remember-me cookie can create a new authentication, after which the app may store it back into a session depending on configuration.

```text
First login
   POST /login + username/password + remember-me=on
       |
       +--> Form login authenticates credentials
       +--> PersistentTokenBasedRememberMeServices generates random series/token
       +--> PersistentTokenRepository saves server-side record
       +--> Browser receives long-lived remember-me cookie
       +--> App may also create a normal HTTP session

Request after the session is gone
   GET /me + remember-me cookie (no valid JSESSIONID)
       |
       +--> RememberMeAuthenticationFilter sees no Authentication yet
       +--> RememberMeServices reads cookie
       +--> Repository looks up series, compares token and expiration
       +--> Generate new token, update repository + cookie
       +--> Load UserDetails, create RememberMeAuthenticationToken
       +--> AuthorizationFilter enforces permissions per policy
```

**Important:** Remember-me is an **authentication path with lower trust than re-entering credentials**, because whoever holds the cookie may not be the account owner. Sensitive operations should require full authentication (`fullyAuthenticated()`), current password verification, or re-authentication/MFA per policy.

## 2. Distinguishing Session Cookie, Remember-me Cookie, and Password

| Concept | Data held by browser | What does the server check? | Typical lifecycle |
| --- | --- | --- | --- |
| **Session cookie** | Short session ID, e.g., `JSESSIONID` | Look up session and saved `SecurityContext` | Based on idle timeout, logout, session store, and policy |
| **Persistent remember-me cookie** | Data containing **series/token** in Spring Security's format | Query repository, compare random token and expiration; may rotate token | Longer lifetime than session; depends on `tokenValiditySeconds` and DB state |
| **Username/password** | Entered by user at login; should not be stored plaintext on server | `AuthenticationManager`/provider compares raw password with password hash | Basis for initial verification or re-authentication |
| **OAuth2 refresh token** | Credential issued by authorization server | Token endpoint/authorization server per OAuth2 spec | Different mechanism; not used as default remember-me token |

A browser can carry **both cookies** simultaneously: the session cookie for fast access during the current session, and the remember-me cookie as fallback recovery when the session is absent. Do not infer that “having a remember-me cookie” means every request runs auto-login: when `SecurityContextHolder` already holds an `Authentication` from the session, `RememberMeAuthenticationFilter` normally skips the remember-me cookie.

This is crucial when testing **rotation**: to prove remember-me works, you must send an **independent request carrying no valid session**, only the remember-me cookie.

## 3. Spring Security's Two Remember-me Options

Spring Security offers two basic implementation styles:

### 3.1. Token-Based Remember-me Without a Persistent Token Table

`TokenBasedRememberMeServices` relies on cookie data and corresponding verification logic, without needing a separate `PersistentTokenRepository`. It carries trade-offs around revocation and password/key lifecycles; do not assume all Spring Security token-based schemes can easily revoke individual devices.

### 3.2. Persistent Token-Based Remember-me Using a Server-Side Repository

`PersistentTokenBasedRememberMeServices` (this lesson's topic) generates a random **`series`** and **`token`** pair:

- `series`: identifier of the remembered login series stored in the repository, used to locate the record.
- `token`: random secret value for the current use; compared against the value stored by the server.
- `username`: account bound to the series.
- `lastUsed`: timestamp when the token was most recently created/updated, used for expiration logic.

Each time a remember-me cookie is successfully used for auto-login, the service typically **keeps the series unchanged while generating a new token**, updating the repository and issuing a new cookie. An old cookie carrying the previous token becomes invalid once the token has rotated.

**Pros:** server-side data supports verification, token rotation, and revocation; integrates cleanly with security workflows. **Trade-offs:** requires an operational, properly secured database/replicated store; auto-login requests incur DB reads/writes; concurrent requests can create race conditions.

## 4. What Does PersistentTokenBasedRememberMeServices Do?

`org.springframework.security.web.authentication.rememberme.PersistentTokenBasedRememberMeServices` extends `AbstractRememberMeServices`. Its main constructor takes three dependencies:

```java
PersistentTokenBasedRememberMeServices services =
        new PersistentTokenBasedRememberMeServices(
                rememberMeKey,
                userDetailsService,
                persistentTokenRepository);

services.setTokenValiditySeconds(14 * 24 * 60 * 60);
services.setParameter("remember-me");
```

This is an **illustrative configuration fragment**, not a standalone Java class. `rememberMeKey` is the app's stable secret string, `userDetailsService` is the user source, and `persistentTokenRepository` is the token store. When configuring via the `http.rememberMe(...)` DSL, Spring Security can automatically instantiate and wire this service once `tokenRepository` is supplied; manual bean registration is not always required.

### 4.1. On Successful Form Login

After form login authenticates username/password, the remember-me service runs on the success path:

1. Checks whether the user **selected remember-me** via the configured parameter name, unless `alwaysRemember(true)` is set.
2. Generates a random `series` and random `token`.
3. Builds `PersistentRememberMeToken(username, series, token, date)`.
4. Calls `PersistentTokenRepository.createNewToken(...)` to persist the record.
5. Sends the remember-me cookie to the browser with an appropriate expiration.
6. Completes login; a normal HTTP session may be created/saved separately.

The persistent cookie is not an “encrypted password”; it carries a random credential dedicated to remember-me. The service never fetches a plaintext password from the database to put into the cookie.

### 4.2. When a New Request Arrives With Only the Remember-me Cookie

`RememberMeAuthenticationFilter` checks whether no authentication is present in the context and invokes `RememberMeServices.autoLogin(...)` when appropriate. For a valid persistent cookie, the service:

1. Reads and decodes the cookie according to its internal format.
2. Requires both expected parts: `series` and `token`.
3. Calls `getTokenForSeries(series)` to fetch the record from the repository.
4. If no series is found, rejects remember-me.
5. If the cookie token **does not match** the stored record for that series, handles suspected token theft/reuse.
6. If the token exceeds the allowed lifetime, rejects it.
7. For a valid token, **generates a new token**, updates the record via `updateToken(...)`, and issues a new cookie.
8. Calls `UserDetailsService.loadUserByUsername(...)` to fetch the current user, and the remember-me mechanism builds a `RememberMeAuthenticationToken` for the filter.

`RememberMeAuthenticationToken` is a distinct authentication result. It counts as authenticated under Spring Security's contract, yet **is not equivalent to full login** when the system enforces `fullyAuthenticated()`.

### 4.3. On Logout

`RememberMeServices` also participates in logout to clear the remember-me cookie and potentially delete server-side tokens for the user. `PersistentTokenRepository.removeUserTokens(username)` deletes tokens by **username**, not by a specific series; with `JdbcTokenRepositoryImpl`, this operation can revoke **all remember-me records belonging to that user**.

This has a UX consequence: logging out on one device can stop remember-me from working on another device, depending on the actual flow and repository setup. If the requirement is “log out only this device”, you must design a custom token store/revocation model or controlled extension rather than relying blindly on `removeUserTokens(username)`.

## 5. PersistentTokenRepository: The Storage Contract

The `org.springframework.security.web.authentication.rememberme.PersistentTokenRepository` interface decouples the remember-me service from the database type.

Key methods:

```java
public interface PersistentTokenRepository {
    void createNewToken(PersistentRememberMeToken token);

    void updateToken(String series, String tokenValue, Date lastUsed);

    PersistentRememberMeToken getTokenForSeries(String seriesId);

    void removeUserTokens(String username);
}
```

These are **abbreviated interface signatures for learning**; if declaring them yourself you need `java.util.Date` and Spring Security's `PersistentRememberMeToken`, though real applications should use the framework's built-in interface.

| Method | When called | Properties to guarantee |
| --- | --- | --- |
| `createNewToken` | After successful login with remember-me enabled | Persist username, series, token, lastUsed; series must be unique |
| `getTokenForSeries` | When a cookie arrives and auto-login is needed | Look up exact series or return null; never “guess” user from cookie |
| `updateToken` | On successful auto-login with token rotation | Update token value and timestamp atomically; support race control |
| `removeUserTokens` | On logout, suspected cookie theft, or revocation policy | Remove/revoke series belonging to the user per contract |

### 5.1. What Does PersistentRememberMeToken Contain?

`PersistentRememberMeToken` is a data object holding:

```text
username:  "learner"
series:    <random-series>
token:     <random-token-value>
date:      <last-used-timestamp>
```

The random strings are format placeholders, **not valid tokens**. Java code exposes getters such as `getUsername()`, `getSeries()`, `getTokenValue()`, and `getDate()`.

Neither the password hash nor the raw password needs to be stored in the remember-me table. Password hashes stay in the user store for `DaoAuthenticationProvider`; remember-me credentials are managed separately.

### 5.2. Custom Repository Implementations

If using Redis/JPA or a remote store, implement the interface faithfully. Design requirements:

- `series` must be unique, fast to look up, and unguessable.
- Token writes must be **atomic** so two requests on the same series do not overwrite each other.
- All application nodes share the same store or a store with appropriate consistency.
- Clocks/timezones and `lastUsed` are consistent; usually store UTC timestamps.
- Delete tokens on logout/revocation, and do not cache stale tokens too long.
- Protect DB data, backups, and logs: series/token values are **sensitive credentials**.
- If applying optimistic locking/CAS or hash-at-rest for tokens, verify compatibility with the standard service and test failure/concurrency cases.

**Never** implement a repository storing tokens in a local `HashMap` for a multi-node environment and call it “persistent”, because tokens vanish on process restart or when requests hit another node.

## 6. JDBC Implementation and the persistent_logins Table

`JdbcTokenRepositoryImpl` is the built-in implementation of `PersistentTokenRepository`. It uses a `DataSource` to create, read, update, and remove persistent tokens.

Equivalent default schema:

```sql
CREATE TABLE persistent_logins (
    username VARCHAR(64) NOT NULL,
    series VARCHAR(64) PRIMARY KEY,
    token VARCHAR(64) NOT NULL,
    last_used TIMESTAMP NOT NULL
);
```

| Column | Role |
| --- | --- |
| `username` | Identity of the remembered user |
| `series` | Primary key identifying the remember-me series |
| `token` | Current secret value matched against the cookie |
| `last_used` | Timestamp of last token update, basis for expiration |

This is a **remember-me** table, not a Spring Session table and not a `users` table. Each user can have multiple `series` rows (multiple browsers/devices); the primary key is on `series`, not on `username`.

### 6.1. Table Creation

`JdbcTokenRepositoryImpl` provides `setCreateTableOnStartup(true)` to create the table on startup in certain demo scenarios. **Do not blindly enable this in production:** restarts can fail with table-already-exists errors, and schema migrations should be managed by Flyway/Liquibase or DB deployment pipelines.

The demo project below uses H2's `CREATE TABLE IF NOT EXISTS` in `schema.sql`. For production databases, use migrations matching the target dialect; `IF NOT EXISTS` does not share identical syntax across all engines.

### 6.2. When Must Old Data Be Cleaned Up?

A token expiring according to the service does not by default delete the database row immediately. Depending on repository/flow, expired rows can accumulate until cleanup or revocation runs. For large databases, build a safe cleanup schedule based on lifetime policy and `last_used`; verify clocks/timezones, indexes, and impact on active sessions.

Do not delete based on “account creation date” when expiration relies on `lastUsed` and `tokenValiditySeconds`. If you need an extra guard such as an absolute maximum age, design and store dedicated fields accordingly.

## 7. Series/Token Cookie: Security Analysis

The logical format of a persistent remember-me cookie combines two values:

```text
series:token
    |
    v
Base64(...) -> remember-me cookie
```

This is only a **conceptual representation**; the implementation may escape/encode per internal API rules. Base64 does not encrypt secrets. A remember-me cookie acts as a **bearer credential**: if stolen, someone else can attempt to use it for auto-login.

### 7.1. Why Are Both Series and Token Needed?

- `series` provides a stable lookup key for a remembered session line.
- `token` is **rotated after successful auto-login**, invalidating an old cookie once the token updates.
- When the server finds the series but the token differs from the stored value, it may indicate the credential was stolen or used beforehand.
- Depending on service logic, the suspicious event can revoke that username's persistent tokens.

Compared to a static long-lived cookie, rotation helps detect reuse of an old token. However, **it is not conclusive proof of theft**: two parallel requests from the same browser can also submit the same old cookie while the token is rotating.

### 7.2. Concurrent Request Issue When a Session Expires

Suppose a browser fires two requests simultaneously carrying `series=S, token=T0`:

```text
Request A: sends S,T0     Request B: sends S,T0
       |                         |
       v                         v
  queries DB, sees T0       queries DB, sees T0 or T1
       |
  updates DB to T1
       |
  returns cookie S,T1
                                 |
                          if B reads after A updates:
                          DB is now T1, B sent T0
                          -> token mismatch, suspected theft
                          -> may revoke tokens
```

The outcome depends on interleaving, the database, and the order in which the client receives cookies. With standard persistent remember-me, a request reusing an old token after the series updated can trigger `CookieTheftException` and `removeUserTokens(username)`.

**Do not fix this by removing token rotation or disabling token mismatch checks** just because users get logged out when multiple tabs send parallel requests. Better mitigations are reducing situations where multiple concurrent requests need remember-me (e.g., managing the session after the first auto-login), measuring race errors, testing realistically, and designing a more suitable repository/flow under security review if necessary.

### 7.3. Expiration: Cookie and lastUsed

`setTokenValiditySeconds(...)` defines how long remember-me is accepted per service mechanics. On successful auto-login, the token and `lastUsed` are usually updated and a new cookie is issued; understand this **sliding expiration behavior** rather than assuming it is a fixed absolute lifetime from the first login.

The token store must still hold a valid record; an unexpired cookie in the browser **does not mean** the server will accept it if the record was deleted, the token mismatches, or the user is invalid. Conversely, a DB record existing when the browser cookie expired or wasn't sent will not produce auto-login either.

If a product requires an **absolute maximum lifetime** or mandatory re-auth after a fixed duration, design dedicated controls rather than relying solely on `lastUsed` updates.

### 7.4. The Service Key Does Not Replace Token Secrecy

The constructor accepts `key` for use within the remember-me authentication ecosystem and internal token trust checks. **Do not** think of it as an AES key to “decrypt” persistent cookies, nor treat the key as a substitute for DB token secrecy. The key must remain consistent across nodes/restarts in the same app and be protected via secret management. Changing the key can invalidate earlier remember-me authentications depending on configuration.

### 7.5. Cookie Attributes

Use HTTPS, `Secure`, `HttpOnly`, and `SameSite` appropriate to your protocol and clients; scope domain/path tightly. Never pass remember-me tokens in URLs, log `Cookie` headers, or casually copy credentials into `LocalStorage`. `SameSite` reduces some CSRF risks but does not replace CSRF tokens for cookie-based applications protecting state-changing requests.

## 8. Runnable Spring Boot Project: Remember-me with JDBC

The demo uses **Java 17+**, **Spring Boot 3.3.5 / Spring Security 6.x**, and **Gradle 8.5**. We use a file-backed H2 database locally so persistent token records survive process restarts; learning accounts are created in memory. This is **not a production configuration**: never use H2 files or demo secrets to manage real users.

### 8.1. Demo Features

- `GET /` is public.
- `GET /me` requires `authenticated()`; returns username and Authentication class.
- `GET /settings` requires `fullyAuthenticated()`, denying/redirecting to re-login when only remember-me is present.
- `POST /login` handled by `formLogin()`, with CSRF, username/password, and optional `remember-me=on`.
- `JdbcTokenRepositoryImpl` stores series/token pairs in the `persistent_logins` table.

### 8.2. File Structure

```text
jdbc-remember-me-demo/
  settings.gradle
  build.gradle
  src/main/java/demo/
    DemoApplication.java
    SecurityConfig.java
    DemoController.java
  src/main/resources/
    application.properties
    schema.sql
  src/test/java/demo/
    PersistentRememberMeTest.java
```

`settings.gradle`:

```groovy
rootProject.name = 'jdbc-remember-me-demo'
```

`build.gradle`:

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
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'

    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Spring Boot manages compatible Spring Security, JDBC, and H2 versions in the `3.3.5` BOM. There is no need to add `spring-data-jpa` when only using `JdbcTokenRepositoryImpl`.

### 8.3. Local Datasource and Secret Configuration

`src/main/resources/application.properties`:

```properties
spring.datasource.url=jdbc:h2:file:./rememberme-db;DB_CLOSE_ON_EXIT=FALSE
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always

app.security.remember-me-key=demo-local-key-change-before-production
```

`H2 file` stores data on the demo machine's disk, unlike `jdbc:h2:mem:...` which disappears across process restarts. When running in a container with an ephemeral filesystem, data can still be lost when the container is replaced.

**Warning:** the key in properties is for **local demo only**, unsuitable for production. In real environments, inject a strong, stable secret via environment variables/secret manager (such as `APP_SECURITY_REMEMBER_ME_KEY` per Spring Boot's property binding); never commit production secrets or rotate the key arbitrarily on every deploy.

`src/main/resources/schema.sql`:

```sql
CREATE TABLE IF NOT EXISTS persistent_logins (
    username VARCHAR(64) NOT NULL,
    series VARCHAR(64) PRIMARY KEY,
    token VARCHAR(64) NOT NULL,
    last_used TIMESTAMP NOT NULL
);
```

This schema uses H2's `IF NOT EXISTS` syntax so the demo app can restart when the DB file already exists. For MySQL/PostgreSQL or production systems, use matching DDL/migrations, least-privilege DB accounts, and backup protection policies.

### 8.4. Startup Class

`src/main/java/demo/DemoApplication.java`:

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

### 8.5. SecurityConfig: Using PersistentTokenRepository with JDBC

`src/main/java/demo/SecurityConfig.java`:

```java
package demo;

import javax.sql.DataSource;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.rememberme.JdbcTokenRepositoryImpl;
import org.springframework.security.web.authentication.rememberme.PersistentTokenRepository;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails user = User.withUsername("learner")
                .password(encoder.encode("study123"))
                .roles("USER")
                .build();

        return new InMemoryUserDetailsManager(user);
    }

    @Bean
    PersistentTokenRepository persistentTokenRepository(
            DataSource dataSource) {
        JdbcTokenRepositoryImpl repository = new JdbcTokenRepositoryImpl();
        repository.setDataSource(dataSource);
        return repository;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            UserDetailsService users,
            PersistentTokenRepository tokens,
            Environment environment) throws Exception {

        String rememberMeKey = environment.getRequiredProperty(
                "app.security.remember-me-key");

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/").permitAll()
                .requestMatchers("/settings").fullyAuthenticated()
                .anyRequest().authenticated());

        http.formLogin(form -> form
                .defaultSuccessUrl("/me", true)
                .permitAll());

        http.rememberMe(remember -> remember
                .key(rememberMeKey)
                .userDetailsService(users)
                .tokenRepository(tokens)
                .rememberMeParameter("remember-me")
                .rememberMeCookieName("remember-me")
                .tokenValiditySeconds(14 * 24 * 60 * 60));

        http.logout(logout -> logout.logoutSuccessUrl("/"));

        return http.build();
    }
}
```

**Reading piece by piece:**

1. `UserDetailsService` is where the remember-me service looks up the user from the username stored in the token record. If the user was deleted, disabled, or policy changed, authentication can fail/reject per the associated checks; test explicit user-state policies.
2. `PersistentTokenRepository` is the contract; `JdbcTokenRepositoryImpl` uses the same `DataSource` for the `persistent_logins` table. The bean does not call `setCreateTableOnStartup(true)`, because `schema.sql` handles table creation for the demo.
3. `http.rememberMe(...tokenRepository(tokens))` activates the **persistent token-based** branch. Spring Security integrates remember-me with form login, the auto-login filter, and the appropriate provider.
4. `rememberMeParameter("remember-me")` requires the client to submit the opt-in parameter; when absent/unchecked, normal form login does not issue a persistent remember-me cookie.
5. `rememberMeCookieName("remember-me")` sets the cookie name for easy observation in tests.
6. `tokenValiditySeconds(14 * 24 * 60 * 60)` sets a 14-day validity for the demo; this is not a recommendation for optimal lifetime across all products.
7. `fullyAuthenticated()` distinguishes remember-me from full credential login on `/settings`.
8. Do not call `csrf.disable()`. Cookie-backed form login and logout require CSRF protection; tests submit valid CSRF tokens.

**Do not implement a custom `AuthenticationProvider` just to validate persistent cookies** in this example. The remember-me DSL creates/wires the required components; if customizing `RememberMeServices`, you must understand how filters and providers attach to the chain.

### 8.6. Controller Displaying Authentication Type

`src/main/java/demo/DemoController.java`:

```java
package demo;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/")
    public String home() {
        return "home";
    }

    @GetMapping("/me")
    public String me(Authentication authentication) {
        return authentication.getName() + ":"
                + authentication.getClass().getSimpleName();
    }

    @GetMapping("/settings")
    public String settings(Authentication authentication) {
        return "settings-for-" + authentication.getName();
    }
}
```

A session after full form login normally holds `UsernamePasswordAuthenticationToken`, while a request auto-authenticated via remember-me holds `RememberMeAuthenticationToken`. Thus `/me` illustrates the difference between the two authentication paths. `/settings` requires `fullyAuthenticated()` so a remember-me cookie alone cannot bypass password re-entry.

Do not use the authentication class name as a production authorization rule; use authorization DSLs, `AuthenticationTrustResolver`, or Spring Security's supported re-authentication policies instead.

### 8.7. MockMvc Tests: Opt-In, Cookie-Only, Rotation, Full Authentication

`src/test/java/demo/PersistentRememberMeTest.java`:

```java
package demo;

import jakarta.servlet.http.Cookie;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = {
    "spring.datasource.url=jdbc:h2:mem:rememberme-test;DB_CLOSE_DELAY=-1"
})
@AutoConfigureMockMvc
class PersistentRememberMeTest {

    @Autowired
    MockMvc mvc;

    private Cookie loginAndGetRememberMeCookie() throws Exception {
        MvcResult login = mvc.perform(post("/login")
                        .with(csrf())
                        .param("username", "learner")
                        .param("password", "study123")
                        .param("remember-me", "on"))
                .andExpect(status().is3xxRedirection())
                .andReturn();

        Cookie cookie = login.getResponse().getCookie("remember-me");
        assertNotNull(cookie);
        return cookie;
    }

    @Test
    void anonymousRequestNeedsLogin() throws Exception {
        mvc.perform(get("/me"))
                .andExpect(status().is3xxRedirection());
    }

    @Test
    void loginWithoutRememberMeDoesNotCreatePersistentCookie()
            throws Exception {
        MvcResult login = mvc.perform(post("/login")
                        .with(csrf())
                        .param("username", "learner")
                        .param("password", "study123"))
                .andExpect(status().is3xxRedirection())
                .andReturn();

        assertNull(login.getResponse().getCookie("remember-me"));
    }

    @Test
    void rememberMeCookieReauthenticatesWithoutSession()
            throws Exception {
        Cookie cookie = loginAndGetRememberMeCookie();

        // New request WITHOUT using the form login session.
        mvc.perform(get("/me").cookie(cookie))
                .andExpect(status().isOk())
                .andExpect(content().string(
                        "learner:RememberMeAuthenticationToken"));
    }

    @Test
    void successfulAutoLoginRotatesPersistentToken()
            throws Exception {
        Cookie original = loginAndGetRememberMeCookie();

        MvcResult restored = mvc.perform(get("/me")
                        .cookie(original))
                .andExpect(status().isOk())
                .andReturn();

        Cookie rotated = restored.getResponse().getCookie("remember-me");
        assertNotNull(rotated);
        assertNotEquals(original.getValue(), rotated.getValue());
    }

    @Test
    void rememberMeDoesNotSatisfyFullyAuthenticated()
            throws Exception {
        Cookie cookie = loginAndGetRememberMeCookie();

        mvc.perform(get("/settings").cookie(cookie))
                .andExpect(status().is3xxRedirection());
    }

    @Test
    void loginRequiresCsrfToken() throws Exception {
        mvc.perform(post("/login")
                        .param("username", "learner")
                        .param("password", "study123")
                        .param("remember-me", "on"))
                .andExpect(status().isForbidden());
    }
}
```

**Expected results:** 6 tests PASS with the stated project and dependencies. They prove:

- Unauthenticated `/me` requires authentication.
- Without checking the box, successful form login does not issue a persistent remember-me cookie.
- Taking the remember-me cookie from the login response and **omitting the login request's session**, a new request still receives `RememberMeAuthenticationToken`.
- Successful auto-login issues a new cookie because the token rotated.
- A remember-me authentication does not satisfy `fullyAuthenticated()` on `/settings`.
- Form login without a CSRF token is rejected.

**Pitfalls to avoid:** do not use `@WithMockUser` to test persistent remember-me, because that annotation injects an authentication directly into the test context and bypasses `RememberMeAuthenticationFilter`. Do not copy `MockHttpSession` from the login request into the auto-login test; doing so accidentally tests the session instead of the remember-me cookie.

In certain containers/browsers or integrations, cookie attributes, redirects, and session handling may differ from MockMvc. Run E2E tests with HTTPS, reverse proxies, and real browsers before deploying to production.

### 8.8. Running the Application

From the `jdbc-remember-me-demo` directory:

```bash
gradle test
gradle bootRun
```

If the project uses the Gradle Wrapper, run `./gradlew test` and `./gradlew bootRun` (macOS/Linux) or `.\gradlew.bat test` and `.\gradlew.bat bootRun` (Windows PowerShell).

Test in the browser at `http://localhost:8080`:

1. Open `/me` while logged out: expected redirect to the login page.
2. On the login page, enter `learner` / `study123` and enable **Remember me** (or submit `remember-me=on`).
3. Observe the login response setting the `remember-me` cookie. Actual cookies are runtime data; never copy them into logs.
4. Delete **only the session cookie** in the browser or use a sessionless test; retain the `remember-me` cookie.
5. Request `/me`: identity should be restored as `learner:RememberMeAuthenticationToken`.
6. Request `/settings` with only the remember-me cookie: must require full login per the `fullyAuthenticated()` policy.
7. Inspect the `persistent_logins` table in the local DB: after remember-me login there is a row with username/series/token/last_used; after successful auto-login, `token` and `last_used` update. **Never expose `series/token` values.**

If using `curl`, handle the cookie jar **and the login page's CSRF token** rather than sending a raw POST login without CSRF. Since the default form-login page generates a per-request/session token, testing via browser is usually easier to observe. Localhost HTTP is for demo use only; use HTTPS in real environments.

## 9. What Happens on Logout, Password Change, or Account Lockout?

### 9.1. Logout

With standard Spring Security logout, the remember-me logout handler clears the cookie and calls the repository to delete tokens belonging to the username. With the default JDBC repository, `removeUserTokens(username)` targets all remembered series for that user.

Apps with requirements for **single-device logout**, “log out all devices”, “forget remembered device”, or “revoke active sessions” must separate concerns: remember-me and HTTP sessions are **two distinct sources of state**. Deleting persistent tokens does not automatically invalidate all active sessions; invalidating one session does not necessarily delete all remember-me tokens unless logout/revocation follows the proper flow.

### 9.2. Changing Password

A persistent token is not a password hash. Therefore updating a password in `UserDetailsService`/database **does not automatically guarantee** stored persistent tokens are deleted. If policy requires forcing all devices to re-login after a password change, explicitly invoke `removeUserTokens(username)` and consider session invalidation/revocation.

Never claim “the token cookie stayed valid because the password matched”—remember-me restores the user from repository/cookie and does not repeat password comparison on every auto-login.

### 9.3. Locking or Disabling an Account

During auto-login, the service loads current `UserDetails`. However, the system must carefully check account status and authorization policies: if a user is disabled, locked, or stripped of privileges, it must **fail closed** and revoke relevant tokens/sessions. Never rely solely on the presence of a `persistent_logins` row to grant permanent access.

### 9.4. Lost Secret or Database

If the demo H2 file is deleted, the repository loses stored series/tokens; cookies left in browsers fail to find their series and auto-login fails. If multi-node apps use separate unsynchronized databases, a cookie may work on node A and fail on node B. Production should use an appropriate shared store/cluster.

If the remember-me key is rotated while nodes carry different keys, the authentication token provider may not accept results consistently. Manage keys per environment, keep them stable across deploys, and plan rotations knowing their impact on issued cookies.

## 10. Scalability and Production Deployment Risks

### 10.1. Database Availability

Whenever persistent auto-login is needed, the server must query and usually update the token server-side. When the database is down, the cookie cannot be trusted independently. Configure timeouts, connection pools, bounded retries, and safe failure responses; **never** let auto-login succeed merely because the DB is unreachable.

### 10.2. Atomicity and Race Conditions

The standard JDBC repository provides CRUD operations per contract. Under network latency, multiple tabs, and concurrent requests, the read–check–update cycle can hit races. Test these paths thoroughly. When building a custom repository, consider optimistic concurrency/compare-and-set and avoiding accidental acceptance of replays; never alter behavior to accept old tokens without a security analysis.

### 10.3. Tokens Stored in the DB Are Still Credentials

With classic persistent remember-me, token values may be stored in a form allowing direct comparison. If the DB is read without authorization, treat this data as sensitive: combined `series/token` pairs can help forge valid cookies. Protect the DB, backups, access permissions, and logs; if hash-at-rest is required, design a custom repository/service with proper matching semantics and rotation, rather than blindly replacing the `token` column with a one-way hash and expecting default `JdbcTokenRepositoryImpl` to work.

Do not hash a random token one-way with `PasswordEncoder` and expect default `JdbcTokenRepositoryImpl` to understand the transformed hash; the default service compares tokens in the format it expects. Changing storage semantics requires implementing the matching repository and verification flow.

### 10.4. Cookie Security and CSRF

A persistent remember-me cookie is a long-lived bearer credential. Use HTTPS, configure `Secure`, `HttpOnly`, `SameSite`, strict domain/path, HSTS where appropriate, and keep cookies out of URLs. Because browsers automatically attach cookies, CSRF protection remains essential for POST/PUT/DELETE. Never disable CSRF globally just because remember-me is enabled.

### 10.5. Cookie Theft and Legitimate Users Getting Logged Out

`CookieTheftException` can occur when the cookie token mismatches the DB token even though the series exists. It is a **signal requiring investigation**, not legal proof of an attacker. Concurrent requests after session expiration can also cause the token to rotate before another request is processed.

Logs/metrics should record **event codes**, correlation IDs, usernames per data policy, and failure counts; **never** log raw cookies, series/tokens, or secrets. When real attack indicators appear, apply revocation and alerting per policy.

### 10.6. Device Management and Token Series

A single user can hold multiple series across browsers/devices. `PersistentTokenRepository.removeUserTokens(username)` deletes by user, not by a single series. If the product lets users view and revoke **individual devices**, design additional data model/metadata and controlled per-series revocation APIs; never display secret tokens in the device management UI.

### 10.7. Choosing a Sensible Lifetime

14 days in the demo is purely an educational value. Banking, healthcare, or admin consoles should often avoid remember-me or enforce strict session limits, MFA, and re-auth. Less sensitive apps may favor UX while ensuring transparency, opt-in, and logout. Timeouts for HTTP sessions, remember-me tokens, and external access tokens should be managed independently.

## 11. Troubleshooting: Remember-me Not Working

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| Login succeeds yet no remember-me cookie | Checkbox not selected, wrong parameter name, flow did not call rememberMe success | Check `rememberMeParameter` and response after valid login |
| Cookie exists yet new request redirects to login | Cookie not sent, wrong path/domain/Secure, flawed session test, DB missing series | Inspect cookie in Network tab, token store, and URL scope |
| Cookie stops working after server restart | In-memory DB, key changed, non-durable tokens, cookie/session config | Use durable DB, stable key, inspect schema |
| Error because `persistent_logins` table does not exist | Migration/schema not executed | Check DDL, datasource, database permissions |
| Table-already-exists error on startup | Using `setCreateTableOnStartup(true)` when table already exists | Use proper idempotent migrations instead of leaving auto-create on |
| Auto-login works once then remember-me breaks | Token rotation, new cookie not saved, parallel requests with old token | Inspect `Set-Cookie` after auto-login, replay/concurrency |
| `CookieTheftException` thrown | Series exists but token wrong/stale, possibly replay or race | Never log tokens; investigate concurrency, DB writes, security events |
| `fullyAuthenticated()` blocks access to sensitive page | Remember-me auth is not considered full authentication | Expected behavior; require credential re-entry |
| Logged out yet other session/device stays active | Session and token are separate states; revocation scopes differ | Check logout handler, `removeUserTokens`, and session invalidation |
| Changed password yet another browser stays remembered | Persistent tokens and sessions not revoked | Revoke tokens by user and policy |
| Multi-node: works intermittently | Token DB/key inconsistent across nodes | Use shared store, consistent key, and synchronized clocks/timezone |

### How to Debug Without Exposing Secrets

You can enable DEBUG logging for Spring Security in test environments:

```properties
logging.level.org.springframework.security=DEBUG
```

Never enable full logging of `Cookie`/`Authorization` headers in production. `SecurityFilterChain` log lines only confirm filters executed; they do not prove `getTokenForSeries` found a record, the token rotated, or the client received the new cookie. Measure the repository/remember-me service boundary under control and test HTTP requests without a session.

## 12. Pre-Deployment Testing Checklist

1. **Opt-in:** login with `remember-me=on` issues a cookie; login without it does not.
2. **Cookie-only:** separate the session, send a new request with only the remember-me cookie, and verify `RememberMeAuthenticationToken`.
3. **Rotation:** after auto-login, the new cookie differs from the old cookie; DB `token`/`last_used` updates.
4. **Replay detection:** a cookie with an existing series and wrong token triggers rejection and revocation per contract; test in isolation.
5. **Expiry:** expired cookies, expired records, or deleted records prevent auto-login; do not trust browser `Max-Age` alone.
6. **Password/account changes:** verify whether locking/disabling an account or changing password triggers required re-auth/revocation per policy.
7. **Authorization:** `authenticated()` and `fullyAuthenticated()` endpoints behave differently under remember-me.
8. **Logout:** clears the remember-me cookie and repository tokens per intended scope, distinct from session invalidation.
9. **Multi-device:** independent series and user-level revocation behavior align with UX expectations.
10. **Concurrency:** concurrent requests after session expiry do not destabilize the app; false theft alerts are observed and evaluated.
11. **Persistence:** process restarts and multiple nodes read the shared repository consistently; keys and datasource match.
12. **Cookie/CSRF:** HTTPS, cookie flags, domain/path, CSRF, logout, and sensitive POSTs are tested.
13. **Secrets/DB:** no hardcoded real keys, no token logging, backups secured, schema migrations safe.
14. **Monitoring:** metrics for create/rotate/revoke/fail without placing credentials in telemetry.

## 13. Self-Check Questions

1. **How does persistent remember-me differ from an HTTP session?** A session cookie points to a normal `HttpSession`, whereas a persistent remember-me cookie carries series/token backed by a dedicated repository to restore authentication when no context is present.
2. **Is `PersistentTokenRepository` a user database?** No. It stores username/series/token/lastUsed for remember-me; accounts and password hashes belong to the user store.
3. **Why are both series and token needed?** Series identifies the record, while the random token verifies possession and rotates after auto-login.
4. **On successful auto-login, does the series change?** Normally the series stays the same, while `token` and `lastUsed` update and a new cookie is issued.
5. **Can a cookie still work after its DB record is deleted?** Not under the standard mechanism; if no valid series is found, auto-login is rejected.
6. **Does `CookieTheftException` always prove an attacker?** No. It can arise from reusing an old token or a race between concurrent requests.
7. **Why can `fullyAuthenticated()` reject remember-me?** Remember-me is a weaker form of authentication than a fresh full login, so sensitive endpoints can require re-login.
8. **Does `removeUserTokens(username)` usually revoke one device or all?** The contract deletes by username; with the default JDBC repository, it affects every series of that user.
9. **Does changing a password automatically delete persistent tokens?** Do not assume so. Applications need explicit token/session revocation policies.
10. **Why must remember-me tokens never be logged?** They are bearer credentials that could be used to impersonate users.
11. **Is using in-memory H2 accurate for demonstrating “persistent across restarts”?** No; in-memory H2 usually resets on process restart. The demo uses file-backed H2 to illustrate local persistence.
12. **Is `tokenValiditySeconds` an absolute lifetime from initial login?** Do not treat it that way: the persistent service can update token/lastUsed on auto-login, creating sliding expiration.
13. **Can remember-me simply be replaced with a long-lived JWT?** Do not equate them; JWT/token lifecycles, rotation, revocation, and threat models differ and require separate design.

**Takeaway:** `PersistentTokenBasedRememberMeServices` pairs a **long-lived cookie carrying series/token** with a server-side `PersistentTokenRepository`. After opt-in login, the service stores a record; when the session is gone, `RememberMeAuthenticationFilter` can use the cookie to restore a `RememberMeAuthenticationToken` while **rotating the token** and updating the repository. `JdbcTokenRepositoryImpl` is the built-in JDBC option using the `persistent_logins` table. Because this is a long-lived bearer credential, enforce HTTPS, cookie security, protected DB storage, revocation, and replay/concurrency testing. For sensitive actions, enforce `fullyAuthenticated()` or re-authentication rather than treating remember-me as equivalent to password login.
