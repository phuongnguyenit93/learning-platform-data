# Remember-me and How It Differs from Extending `HttpSession` Lifetime

**Module:** Spring Security – Servlet  
**Group:** Remember Me  
**Example:** Java 17 · Spring Boot 3.3.5 · Spring Security 6.x · Spring MVC/Servlet + Thymeleaf.

## Lesson Objectives

Users check **“Remember me”** so they can return to a website after a normal session expires without re-entering their password. Spring Security provides the **remember-me** mechanism for that scenario. However, remember-me is **not** increasing `HttpSession` timeout from 30 minutes to 14 days.

After this lesson, you will be able to:

1. Distinguish **session authentication** from **remember-me authentication**, and a session cookie (`JSESSIONID`) from a remember-me cookie.
2. Explain when Spring Security invokes `RememberMeServices`, when it builds a `RememberMeAuthenticationToken`, and why a request after the session is lost can still be authenticated from a remember-me cookie.
3. Understand how `SessionCreationPolicy` and `server.servlet.session.timeout` affect the session, while **not** meaning a change to the remember-me token lifecycle.
4. Configure form login, the `remember-me` checkbox, token validity, signing key, `UserDetailsService`, `logout`, and **distinguish `authenticated()` from `fullyAuthenticated()`**.
5. Compare **signed token-in-cookie** remember-me with **persistent token** remember-me that uses a storage table and token rotation.
6. Assess risks of cookie loss, replay, logout, password changes, key rotation, authority revocation, `Secure`/`HttpOnly`/`SameSite`, CSRF, and TLS.
7. Build a complete Java 17 Spring Boot application, run `mvn test`, observe cookies, and test remember-me with MockMvc.

**Key takeaway:** `HttpSession` stores the authentication result of an active session; remember-me uses **a separate long-lived credential** to **re-authenticate** when that session is no longer present. The two mechanisms have different lifetimes, risks, and revocation policies.

## 1. Two Kinds of “Remembering”: Keeping an Active Session vs. Auto Re-Login

### 1.1. Standard Session Login

The user submits a login form with username/password, and `UsernamePasswordAuthenticationFilter` asks `AuthenticationManager` to authenticate. Upon success, Spring Security can store the `SecurityContext` containing the `Authentication` in the `HttpSession`.

The browser holds a session cookie (commonly named `JSESSIONID`) so that on subsequent requests the server locates the right session. There is no need to resend the password on every request; the server uses the login information stored in the session's security context.

```text
POST /perform-login (username + password + CSRF)
  → verify credentials → authentication succeeds
  → SecurityContext bound to HttpSession
  → Set-Cookie: JSESSIONID=... (depending on container/configuration)
  → GET /api/me + Cookie: JSESSIONID=...
  → retrieve Authentication from the session's SecurityContext
```

A session can become invalid due to **idle timeout**, logout, invalidation, infrastructure changes, or policy. When the session expires, the old `JSESSIONID` is no longer sufficient to restore identity; without another mechanism, protected requests redirect to login.

### 1.2. Remember-me: An Additional Credential for Re-Authentication

If the user selected “Remember me” and remember-me configuration is enabled, when form login succeeds the application can also issue a **remember-me cookie**. When the normal session is gone, the browser can still send a valid remember-me cookie so Spring Security **automatically re-authenticates** the user.

```text
POST /perform-login (valid password + remember-me=on + CSRF)
  → Authentication succeeds
  → JSESSIONID for the normal session (if any)
  → remember-me=<token> with a longer expiration

Some time later:
  → session expires / JSESSIONID is not sent
  → browser sends Cookie: remember-me=<token>
  → RememberMeAuthenticationFilter + RememberMeServices validate token
  → create remember-me Authentication, place into SecurityContext
  → controller can grant access to endpoints requiring authenticated()
```

Despite sharing the name “remember login”, **remember-me does not turn the original session into an extended session**. When a remember cookie is accepted, **a new authentication** occurs on that request. Depending on the repository/session policy, the result may again be stored in a new session.

### 1.3. Quick Comparison Table

| Criterion | Extending `HttpSession` | Spring Security remember-me |
| --- | --- | --- |
| Core mechanism | Keep the server-side session alive longer and send the session ID via cookie | Hold a separate remember-me credential to re-authenticate after the session is lost |
| Common cookie | `JSESSIONID` or configured session cookie | `remember-me` or configured name |
| Where identity persists across requests | `SecurityContext` in the session repository | Cookie token verified by `RememberMeServices`; then creates `Authentication` |
| Lifetime | Session **idle timeout**; may be extended by accesses depending on mechanism | Separate token validity/max-age, usually measured from issuance; may rotate depending on strategy |
| Server-side state | `HttpSession` and possibly a session store | Token-based may not need a token DB; persistent-token requires a token repository |
| Standard logout | Invalidate session, clear context/cookie | Must remove remember-me cookie; if persistent-token, revoke the corresponding record |
| Trust level distinction | Recent password login can be treated as fully authenticated | Spring Security classifies remember-me authentication separately, usually not satisfying `fullyAuthenticated()` |
| Cookie loss | Loses session identity (if no other credential) | Loses automatic re-login capability |
| Copied token | Session ID can be hijacked | Remember-me token is a bearer credential, also vulnerable to replay |
| Password/key change | Does not necessarily invalidate the current session immediately | Impact depends on strategy; token-based signature may depend on password hash and signing key |

**Crucial:** **Both cookies can exist in the browser at the same time**. While the session remains valid, Spring Security normally uses the session's authentication; only when the session is gone does remember-me get the opportunity to re-authenticate.

## 2. Exact Lifecycle: login → active session → lost session → remember-me

```mermaid
sequenceDiagram
    participant B as Browser
    participant F as Spring Security Filters
    participant S as HttpSession / SecurityContextRepository
    participant R as RememberMeServices
    participant U as UserDetailsService
    B->>F: POST /perform-login (username, password, remember-me, CSRF)
    F->>U: Authenticate username/password
    U-->>F: Valid UserDetails
    F->>S: Save login Authentication into session
    F->>R: loginSuccess(request,response,authentication)
    R-->>B: Set-Cookie: remember-me=<token>
    F-->>B: Redirect /api/me; JSESSIONID (if any)
    B->>F: GET /api/me with valid JSESSIONID
    S-->>F: Authentication from session
    F-->>B: 200, rememberMe=false
    Note over B,S: Session expires or session cookie is not sent
    B->>F: GET /api/me with remember-me cookie only
    S-->>F: No session Authentication
    F->>R: autoLogin(request,response)
    R->>U: Load user, check token/validity conditions
    R-->>F: RememberMeAuthenticationToken
    F-->>B: 200, rememberMe=true if endpoint permits
```

The diagram is a conceptual model of **form login + remember-me**; exact filter/repository order depends on version and configuration. When remember-me auto-login succeeds, components may save the context, invoke the session strategy, and create a new session depending on setup. Do not infer that “remember-me only runs when the browser is closed and reopened”; the main condition is that **the current request has no valid Authentication yet** and carries an eligible remember-me credential.

### 2.1. Conditions for Accepting a Remember-me Cookie

Typical conditions include:

- Remember-me is configured in the `SecurityFilterChain` handling that request.
- There is no existing authentication sufficient for the filter to skip auto-login.
- The browser sends the remember-me cookie matching domain, path, `Secure`, and cookie policy.
- The token is within its valid lifetime, untampered, and meets the strategy's verification criteria.
- The account still exists and has an appropriate status; token/password revocation effectiveness depends on implementation.
- The token repository still stores and recognizes the token if using a persistent-token strategy.

When there is no cookie or the token is invalid/expired, a protected request still requires real login; **failed remember-me never silently becomes authenticated**.

## 3. `HttpSession` Timeout Works Independently

`HttpSession` has a **max inactive interval**: if the session receives no requests within the configured duration, the container can expire the session. This is **inactivity time**, not the “expiration date written on the remember-me token”.

With Spring Boot Servlet:

```properties
# Example for learning environments: the session can expire after 60 seconds of inactivity.
server.servlet.session.timeout=1m
```

Or in servlet code:

```java
// Fragment inside a handler with HttpServletRequest request:
HttpSession session = request.getSession(false);
if (session != null) {
    session.setMaxInactiveInterval(60); // seconds
}
```

In Spring Boot 3, the imports are `jakarta.servlet.http.HttpSession` and `jakarta.servlet.http.HttpServletRequest`. This is an illustrative snippet, not a standalone class. Do not call `request.getSession()` just to inspect a session, because it can create a new session; use `getSession(false)` when you only want to observe.

**Increasing session timeout from 30 minutes to 14 days is not equivalent to remember-me:**

1. The server still has to manage the session and its data over a long period.
2. A stolen session ID can live longer, widening the session hijacking window.
3. Permissions, user status, and authorities cached in the session can become stale without a refresh/invalidation policy.
4. Session resources in Redis/Tomcat or the session store grow with session count and TTL.
5. There is no semantic distinction between a session just logged in with a password and an identity automatically remembered via remember-me.
6. If `JSESSIONID` is a session cookie, browsers may treat closing/reopening differently compared to a remember-me cookie with `Max-Age`; do not assume closing the browser always destroys or always restores a session cookie.
7. A session can still be explicitly invalidated/logged out and does not automatically “recover login” without another credential.

### 3.1. A 14-Day Remember-me Timeout Does Not Extend the Original Session by 14 Days

When configuring:

```java
http.rememberMe(remember -> remember
        .tokenValiditySeconds(14 * 24 * 60 * 60));
```

This mark is **14 days** for the remember-me token, **not** the value of `server.servlet.session.timeout`. The browser may retain the remember cookie up to that limit, though browser/user policy can delete it earlier; the token strategy must also verify validity on the server side. With persistent-token, successful auto-login may **rotate** the token (and update its last-used time); actual policy must be checked to know whether the validity window is extended or capped.

Use independent parameters according to purpose: session timeout serves the **active session**, while remember-me validity serves **re-authentication capability when the session is gone**.

## 4. Remember-me Authentication Has a Different Trust Level from Direct Login

Spring Security distinguishes remember-me-based authentication from full credential login via `AuthenticationTrustResolver`. Typically after auto-login, the principal still has username and roles, but `Authentication` is a `RememberMeAuthenticationToken`.

| Rule | User logged in via password form in the session | User auto-authenticated solely by remember-me cookie |
| --- | --- | --- |
| `.permitAll()` | Allowed | Allowed |
| `.authenticated()` | Allowed | Allowed if remember-me token is valid |
| `.fullyAuthenticated()` | Allowed | **No**; usually must log in interactively again |
| `.hasRole("USER")` | Evaluates user's role | Can be allowed if the remember-me Authentication has the matching role |
| `.hasRole("ADMIN")` | Depends on role | Depends on role; does not automatically require password re-login |

Therefore, for high-risk actions such as changing a password, viewing particularly sensitive data, deleting an account, or adding a payment method, **do not rely solely on `.authenticated()`** if the business logic requires a recent authentication step. `.fullyAuthenticated()` excludes remember-me, but **does not automatically guarantee** the user supplied a password within the last few minutes, completed MFA, or reached a specific AAL; “recent login” and step-up authentication requirements need additional design.

Authorization example:

```java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/sign-in", "/public/ping").permitAll()
        .requestMatchers("/api/strong").fullyAuthenticated()
        .anyRequest().authenticated());
```

This is a **fragment**. The project example in Section 8 provides complete classes/imports and tests.

### 4.1. `isAuthenticated()` Is Not Enough to Distinguish Remember-me

A valid `RememberMeAuthenticationToken` can have `isAuthenticated() == true`. If business code uses `authentication.isAuthenticated()` to assume the user “just entered a password”, that assessment is wrong.

Use `AuthenticationTrustResolver`, or the `.fullyAuthenticated()` rule at the security layer, to identify a remembered identity:

```java
AuthenticationTrustResolver trust = new AuthenticationTrustResolverImpl();
boolean remembered = trust.isRememberMe(authentication);
boolean fullyAuthenticated = trust.isFullyAuthenticated(authentication);
```

`AuthenticationTrustResolver` and `AuthenticationTrustResolverImpl` are in `org.springframework.security.authentication`. The snippet is a fragment requiring a valid `Authentication authentication` variable in the current method.

## 5. Two Common Spring Security Remember-me Strategies

### 5.1. Token-Based Remember-me: Cookie with Signed Information

A commonly used configuration is **token-based remember-me**, using `TokenBasedRememberMeServices`. The token sent to the client contains components used to verify the user, expiration time, and a **signature** based on a server-side secret key and credential information. It does **not** store the raw password in the cookie.

Characteristics:

- Does not require a separate remember-me token table in the database.
- `UserDetailsService` needs to load the user during auto re-authentication.
- `key` is an important secret; it should be strong, stored in a secret manager or environment, and consistent across instances if cookies must work across multiple nodes.
- Changing the signing key can render all previously issued cookies unverifiable.
- With the standard token-based strategy, validity can depend on the user's encoded password. Changing the password/hash can invalidate old tokens.
- **A signed cookie is still a bearer credential**: anyone who copies an unexpired cookie can use it if the server accepts it, without knowing the plaintext password.
- Clearing the cookie on logout **does not revoke a stolen copy** of a valid stateless token. Revocation may require server-side state/version/key rotation or a persistent-token strategy.
- Do not call this cookie a “JWT”. It has its own Spring Security/version-specific structure, not a standard OAuth2 access token.
- Changing the encoded password hash **because startup regenerates the hash with a new salt** can also invalidate old tokens, even if the raw password did not change. The demo example generates a new BCrypt hash at startup; see the note in Section 8.

A usable configuration:

```java
http.rememberMe(remember -> remember
        .rememberMeParameter("remember-me")
        .userDetailsService(userDetailsService)
        .key(rememberSigningKey)
        .tokenValiditySeconds(14 * 24 * 60 * 60));
```

Do not hardcode a real secret in code; `rememberSigningKey` must be supplied via controlled configuration. The code above is a fragment, not a complete program.

### 5.2. Persistent-Token Remember-me: Server Stores Series/Token

Spring Security also provides `PersistentTokenBasedRememberMeServices` combined with `PersistentTokenRepository` (e.g. `JdbcTokenRepositoryImpl`) and a persistent token table.

Conceptual flow:

```text
Successful login + remember-me checked:
  → generate random series and token
  → save record (username, series, token, last_used) to DB
  → send remember-me cookie to browser

Auto-login with remember-me cookie:
  → look up record by series
  → compare token
  → if valid: generate new token, update record and cookie (rotation)
  → if token mismatches: handle as suspected token theft event

Logout:
  → may delete token records associated with the user from repository
  → clear remember-me cookie on the browser
```

Characteristics:

- Needs **durable storage** so remember-me survives restarts/server instances.
- Can revoke tokens by deleting a user's rows/series; Spring Security has token-mismatch handling logic that can invalidate the user's tokens to limit replay.
- Token rotation changes the cookie after auto-login, yet can also cause a **race** if the browser sends parallel requests using the old token. UX, logging, and anti-replay/race strategies must be evaluated in real applications.
- Database data loss, out-of-sync read replicas, or failed token lookups can cause auto-login to fail.
- `PersistentTokenRepository` must be protected like a **credential** store; tokens should have sufficient entropy, use TLS, and enforce least-privilege access and retention.
- For multi-device logout, distinguish between **revoking all tokens of an account** and **revoking only one device**, depending on implementation/token model. Do not assume the basic repository mechanism supports device-specific logout out of the box as a product may require.
- Expiration schedules/cookie lifetime, DB row cleanup, and locked-account handling strategies must be tested.

#### 5.2.1. Typical Database Schema

Spring Security `JdbcTokenRepositoryImpl` typically uses the `persistent_logins` table:

```sql
CREATE TABLE persistent_logins (
    username VARCHAR(64) NOT NULL,
    series VARCHAR(64) PRIMARY KEY,
    token VARCHAR(64) NOT NULL,
    last_used TIMESTAMP NOT NULL
);
```

This is an illustrative structure compatible with common JDBC token repository examples. In production, consider data types/indexes, schema migrations, cleanup, and DB access policies.

#### 5.2.2. Configuration Fragment for JDBC

When converting the demo project to persistent tokens, add `spring-boot-starter-jdbc`, a JDBC driver, `DataSource`/schema, and the repository bean:

```java
@Bean
PersistentTokenRepository persistentTokenRepository(DataSource dataSource) {
    JdbcTokenRepositoryImpl repository = new JdbcTokenRepositoryImpl();
    repository.setDataSource(dataSource);
    return repository;
}
```

Imports include `javax.sql.DataSource`, `org.springframework.security.web.authentication.rememberme.PersistentTokenRepository`, and `org.springframework.security.web.authentication.rememberme.JdbcTokenRepositoryImpl`. In the remember-me configuration, replace with:

```java
http.rememberMe(remember -> remember
        .userDetailsService(userDetailsService)
        .tokenRepository(persistentTokenRepository)
        .key(rememberSigningKey)
        .tokenValiditySeconds(14 * 24 * 60 * 60));
```

This is a **fragment for the JDBC variant**, not part of the runnable token-based project below. To run the JDBC variant, you must ensure the schema is created, the DataSource works, and tokens are stored durably. Do not add the repository to the Spring context assuming the framework automatically creates tables/migrations for every database. In a cluster, the token store must be shared.

### 5.3. Strategy Comparison

| Requirement | Signed token-based | Persistent-token |
| --- | --- | --- |
| Separate remember-me table | Not required | Yes |
| Across restarts | Depends on stable key, stable password hash/record, and remaining validity | Depends on persistent DB, key/config, and unexpired record |
| Revoke a copied token | Difficult without extra state/rotation or changing key/password | Can revoke via server data, depending on token model |
| Logout clears browser cookie | Yes | Yes |
| Does logout revoke a copied cookie? | Uncertain; an unexpired signed token can be replayed | Can revoke in DB; must know whether implementation deletes tokens by user/series |
| Auto-login request | Verify signature and user | Query DB, check token, usually rotate |
| Operations | Less infrastructure | Requires DB, cleanup, concurrency strategy |
| Best fit | Small apps, simple revocation requirements, and carefully bounded lifetimes | Apps requiring server-side control over remembered credentials |

**Do not confuse:** Both differ from **session timeout**. Persistent-token has its own DB and still uses a cookie, rather than merely extending `JSESSIONID`.

## 6. Cookies, Sessions, Logout, and Security

### 6.1. Remember-me Cookies Are Long-Lived Credentials

A remember-me cookie can restore identity **without re-entering a password**. Therefore treat it as a secret:

- **HTTPS is mandatory** in real environments. Cookies carry `Secure` when appropriate, and the server/proxy must recognize the HTTPS scheme properly.
- `HttpOnly` helps restrict JavaScript access to the cookie, but does not solve all XSS/CSRF and does not replace TLS.
- `SameSite` must be tested for real browsers/clients; behavior differs across browsers and does not replace CSRF protection.
- Restrict domain/path so the browser does not send the cookie to unnecessary hosts/paths; avoid setting cookies on a broad domain unless needed.
- Choose token lifetime based on risk, not just the desire to “stay logged in longer”.
- Rotate/manage signing keys securely; you may need key migration support or accept that all old cookies become invalid.
- Never log `Cookie`, `Set-Cookie`, remember-me tokens, or request headers containing secrets.
- Implement alerting for suspicious logins, new devices, password changes, account lockouts, and proactive credential invalidation.
- Consider requiring MFA/recent authentication for sensitive actions; `fullyAuthenticated()` is a first step but does not provide MFA by itself.

**Local dev note:** The sample below runs on `http://localhost` with dummy passwords for learning. `Secure` cookies should be required when deploying over HTTPS; always enabling `Secure` in a localhost HTTP example often prevents the browser from sending the cookie as expected. Never reuse a non-TLS dev configuration in production.

### 6.2. What Must Logout Clear?

A form-login flow with remember-me typically needs to:

1. Invalidate the current `HttpSession` upon logout.
2. Clear `SecurityContext` and session cookies according to policy.
3. Send the remember-me cookie with an expired lifetime so the browser deletes the credential.
4. If using persistent-token, delete/revoke the corresponding token records per implementation.
5. Protect the logout endpoint from CSRF (e.g., POST with CSRF token when CSRF is enabled).
6. Decide whether other sessions/remember-me tokens of the same user also need revocation.

**Critical risk:** With a signed token-based cookie, logout mainly makes the browser drop the cookie. A stolen copy of the cookie **can still be used** until it expires or the key/password hash changes. Session logout does not automatically revoke copied bearer cookies.

Conversely, **session timeout** does not necessarily trigger cleanup of the remember-me cookie. This is intentional: remember-me exists to re-login after session timeout.

### 6.3. Why Does Enabling `rememberMe()` Not Replace Session Policy?

`rememberMe()` adds the auto-login strategy and cookie; `sessionManagement` governs how Spring Security manages/limits sessions. You can configure a session duration different from token validity. These components coexist.

`SessionCreationPolicy.STATELESS` may suit Basic/Bearer APIs that authenticate every request, but it is not the optimal default for browser **form login + remember-me** if the session is expected to persist after login. When form login uses a session, a policy such as `IF_REQUIRED` is usually appropriate, and remember-me auto-login can create a new session after the old one disappears.

Do not use `rememberMe()` as a long-lived access token for mobile/bearer APIs. Cookies and browser-oriented behavior differ from an OAuth2/OIDC token lifecycle.

### 6.4. Do Not Misunderstand Browser “Close Tab” or “Close Browser”

There is no single rule that closing a tab discards a session cookie or restarting a browser definitely deletes a session. Browsers have session restore and differing cookie policies. A remember-me cookie typically carries `Max-Age` so it can outlive a session cookie, though users or privacy settings can still delete it early. When testing, **explicitly drop `JSESSIONID`** or invalidate the session rather than relying on “closing a tab” as the sole test condition.

### 6.5. Avoid User Enumeration and Stale Authorities

When remember-me re-authenticates, `UserDetailsService` or the user repository can reload the account and authorities. If an account is locked, disabled, or its roles changed, evaluate how permissions are updated or blocked on the next auto-login. An existing session record may hold stale authorities; remember-me does not automatically solve every permission synchronization and authorization problem.

Do not write detailed error messages that reveal to an attacker which usernames exist or which cookies were once valid. For suspicious access, write safe audit logs and consider rate limiting.

## 7. Planning the Demo: What It Will Prove

The project below demonstrates **token-based remember-me** so no DB setup is required. The URLs:

| URL | Access | Behavior |
| --- | --- | --- |
| `GET /public/ping` | Public | Returns `"pong"` |
| `GET /sign-in` | Public | Displays Thymeleaf login form with `remember-me` checkbox |
| `POST /perform-login` | Form login processing | Reads username/password/CSRF and optional checkbox; handled by Spring Security filter, no MVC POST controller |
| `GET /api/me` | `.authenticated()` | Returns JSON with username and `rememberMe` flag |
| `GET /api/strong` | `.fullyAuthenticated()` | Real session/login only; remembered identity must log in interactively again |
| `POST /logout` | Spring Security logout filter | Invalidates session, clears context and remember-me cookie; CSRF still required |
| `GET /sign-in?error` | Public | Form shows generic error without revealing whether user exists |
| `GET /sign-in?logout` | Public | Form shows logout status |

**Demo account:** `student` / `demo-pass`; for local use only. The password is hashed with BCrypt and regenerated when the Spring context starts. **Because a new hash uses a different salt**, a token-based remember-me cookie from an old instance can become invalid after a restart **even if the signing key does not change**. The project therefore proves auto-login **while the application is running and the session is lost**, without promising remember-me persistence across restarts. In production, account hashes are stored durably (DB) and the signing key is managed stably.

Demo configuration:

```properties
server.servlet.session.timeout=1m
app.remember-me.key=${REMEMBER_ME_KEY:demo-key-only-change-it-in-production}
```

`1m` is for **session inactivity**. The remember-me token is configured for **14 days** in Java config. The two parameters are independent.

## 8. Complete Spring Boot Project

### 8.1. Directory Tree

```text
remember-me-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/remember/
    │   │   ├── RememberMeApplication.java
    │   │   ├── SecurityConfig.java
    │   │   ├── SignInController.java
    │   │   └── ApiController.java
    │   └── resources/
    │       ├── application.properties
    │       └── templates/sign-in.html
    └── test/java/demo/remember/
        └── RememberMeApplicationTests.java
```

Requires JDK 17+, Maven 3.6.3+, and network access to download dependencies on first build.

### 8.2. `pom.xml`

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
    <groupId>demo</groupId>
    <artifactId>remember-me-demo</artifactId>
    <version>1.0.0</version>
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
            <artifactId>spring-boot-starter-thymeleaf</artifactId>
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

Starter Web provides Spring MVC/Servlet; Starter Security provides filters/remember-me; Thymeleaf renders the form. Spring Boot BOM manages compatible versions. `spring-boot-starter-jdbc` is not needed for the **token-based** variant.

### 8.3. `src/main/java/demo/remember/RememberMeApplication.java`

```java
package demo.remember;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RememberMeApplication {
    public static void main(String[] args) {
        SpringApplication.run(RememberMeApplication.class, args);
    }
}
```

### 8.4. `src/main/resources/application.properties`

```properties
server.servlet.session.timeout=1m
app.remember-me.key=${REMEMBER_ME_KEY:demo-key-only-change-it-in-production}
```

When running in production, set `REMEMBER_ME_KEY` to a strong secret stored in a secret manager, avoid logging it, and synchronize it across instances. The dev default is chosen solely so the lesson runs on localhost. If key rotation is needed, understand that cookies signed with the old key may become invalid.

### 8.5. `src/main/java/demo/remember/SecurityConfig.java`

```java
package demo.remember;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
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
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails student = User.withUsername("student")
                .password(encoder.encode("demo-pass"))
                .roles("USER")
                .build();
        return new InMemoryUserDetailsManager(student);
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            UserDetailsService userDetailsService,
            @Value("${app.remember-me.key}") String rememberSigningKey)
            throws Exception {

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET,
                        "/public/ping", "/sign-in").permitAll()
                .requestMatchers("/api/strong").fullyAuthenticated()
                .anyRequest().authenticated());

        http.formLogin(form -> form
                .loginPage("/sign-in")
                .loginProcessingUrl("/perform-login")
                .defaultSuccessUrl("/api/me", true)
                .failureUrl("/sign-in?error")
                .permitAll());

        http.rememberMe(remember -> remember
                .rememberMeParameter("remember-me")
                .userDetailsService(userDetailsService)
                .key(rememberSigningKey)
                .tokenValiditySeconds(14 * 24 * 60 * 60));

        http.logout(logout -> logout
                .logoutUrl("/logout")
                .logoutSuccessUrl("/sign-in?logout")
                .invalidateHttpSession(true)
                .deleteCookies("JSESSIONID")
                .permitAll());

        // CSRF remains enabled; POST forms must carry a CSRF token.
        return http.build();
    }
}
```

**Two different timers:**

- `server.servlet.session.timeout=1m`: the `HttpSession` can expire after one minute of inactivity. That is not the remember-me cookie's TTL.
- `tokenValiditySeconds(14 * 24 * 60 * 60)`: remembers identity for 1,209,600 seconds (14 days) per token policy. The cookie can still be deleted early by the browser or user, or rejected by the backend if the account/key/hash no longer matches.

`rememberMeParameter("remember-me")` makes the form checkbox with `name="remember-me"` an **opt-in** signal; if unchecked, a normal new login **is not issued a remember-me cookie**. There is an `alwaysRemember(true)` option if the business truly wants to always issue a cookie, but transparent opt-in by default is easier to explain and better for privacy.

**Do not** call `.sessionCreationPolicy(SessionCreationPolicy.STATELESS)` in this project: the application wants to maintain a normal browser session and only use remember-me when the session is gone. `HttpSession` is not replaced by the remember-me cookie; the two mechanisms work together.

**Do not write** custom `@PostMapping("/perform-login")` or `@PostMapping("/logout")` methods: these URLs are handled by security filters. With CSRF enabled, logout uses a POST with a valid token; visiting GET `/logout` is not the same as POST logout.

### 8.6. `src/main/java/demo/remember/SignInController.java`

```java
package demo.remember;

import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
public class SignInController {

    @GetMapping("/sign-in")
    public String signIn() {
        return "sign-in";
    }
}
```

When declaring `.loginPage("/sign-in")`, you must provide **your own GET login page**; the framework does not auto-generate an HTML template for a custom URL. The handler returns the `sign-in` view so Thymeleaf resolves `templates/sign-in.html`.

### 8.7. `src/main/resources/templates/sign-in.html`

```html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Sign In and Remember Me</title>
</head>
<body>
    <h1>Sign In</h1>

    <p th:if="${param.error}">
        Invalid username or password.
    </p>
    <p th:if="${param.logout}">
        You have been logged out.
    </p>

    <form th:action="@{/perform-login}" method="post">
        <label for="username">Username</label>
        <input id="username"
               type="text"
               name="username"
               autocomplete="username"
               required>

        <label for="password">Password</label>
        <input id="password"
               type="password"
               name="password"
               autocomplete="current-password"
               required>

        <label for="remember-me">
            <input id="remember-me"
                   type="checkbox"
                   name="remember-me"
                   value="on">
            Remember me
        </label>

        <button type="submit">Sign in</button>
    </form>
</body>
</html>
```

Field names must match the filter/form login configuration:

- `name="username"` and `name="password"` use the defaults of `UsernamePasswordAuthenticationFilter`.
- `name="remember-me"` matches `.rememberMeParameter("remember-me")`.
- `th:action="@{/perform-login}"` matches `.loginProcessingUrl("/perform-login")`.

With Spring Security + Spring MVC + Thymeleaf, when rendering forms through the corresponding integration, `th:action` participates in adding the hidden CSRF parameter when CSRF is enabled. If using other HTML/JSP views, you must include the CSRF token in the POST per the active repository. **`permitAll()` on the login URL does not disable CSRF**.

### 8.8. `src/main/java/demo/remember/ApiController.java`

```java
package demo.remember;

import org.springframework.http.MediaType;
import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiController {

    private final AuthenticationTrustResolver trust =
            new AuthenticationTrustResolverImpl();

    @GetMapping(value = "/public/ping",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public String ping() {
        return "pong";
    }

    @GetMapping("/api/me")
    public MeResponse me(Authentication authentication) {
        return new MeResponse(
                authentication.getName(),
                trust.isRememberMe(authentication));
    }

    @GetMapping("/api/strong")
    public String strong() {
        return "FULL_LOGIN_REQUIRED";
    }

    public record MeResponse(String username, boolean rememberMe) {}
}
```

When logging in with a password and using the active session, `/api/me` is expected to return `{"username":"student","rememberMe":false}`. When the session is lost and the request carries only an accepted remember-me cookie, `/api/me` is expected to return `{"username":"student","rememberMe":true}`. This is a **difference in `Authentication` type**, not a difference in username.

The `/api/strong` endpoint requires `.fullyAuthenticated()`. If only remembered via cookie, Spring Security typically redirects the user to the sign-in page to re-authenticate. Do not treat `trust.isRememberMe` as a timestamp of the most recent login; it only classifies the current authentication mechanism.

## 9. Running the Project and Observing the Browser

From the `remember-me-demo` directory:

```bash
mvn clean test
mvn spring-boot:run
```

By default the app listens on `http://localhost:8080`. Because the example uses HTTP and demo credentials, run it only on a local machine for learning. Real applications must use **HTTPS** when transporting passwords, session cookies, or remember-me cookies.

1. Open `http://localhost:8080/sign-in`.
2. Enter `student` / `demo-pass`, **without checking** “Remember me”. Login takes you to `/api/me`, `rememberMe=false`. The browser may have `JSESSIONID`, but no new remember-me cookie is issued.
3. Log out via a POST form with a valid CSRF token (or use a test); return to `/sign-in` and log in again **with the checkbox ticked**.
4. Observe `Set-Cookie` on the login response and cookies stored in the browser. Now both `JSESSIONID` **and** `remember-me` may be present. Do not share the values of those two cookies.
5. Use browser devtools on **demo data** to delete only `JSESSIONID` while keeping `remember-me`, or wait for the session to expire per policy; reload `/api/me`.
6. If the remember-me cookie is valid and the user still exists, the request can be auto re-authenticated; JSON returns `rememberMe=true`.
7. Access `/api/strong` with the remember-me token: interactive re-authentication is required. Logging in again with a password and then accessing `/api/strong` is allowed within the full login session.
8. Log out via a valid POST and observe the server sending a cookie-deletion header for remember-me. After the browser actually deletes this cookie, a new request without session/remember cookies must require login.

**Do not treat closing the browser as a deterministic test**: browsers have session restore and varying cookie settings. Controlled deletion of only the session cookie lets you observe the exact mechanism. If you use H2/token repository in the persistent variant, you will additionally observe token lookup/rotation.

### 9.1. Cookie Expiration Is Not the Same as Session Idle Timeout

When inspecting devtools/Application/Cookies, do not assume `Expires/Max-Age` on the `JSESSIONID` cookie must equal `server.servlet.session.timeout` exactly. A session cookie usually holds only the session ID; the **server** decides whether the session is valid based on inactivity/expiration and policy. A remember-me cookie has a lifetime matching the token (per configuration), yet can still be actively deleted.

## 10. MockMvc Test Suite: Proving the Two Mechanisms Differ

MockMvc can test Spring Security filters without a browser and without opening a network port. These tests do not verify whether a real browser retains cookies across restarts, but they verify **token issuance on opt-in**, **re-authentication with only the remember cookie**, and **authorization distinguishing remember-me**.

### 10.1. `src/test/java/demo/remember/RememberMeApplicationTests.java`

```java
package demo.remember;

import jakarta.servlet.http.Cookie;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

import static org.hamcrest.Matchers.containsString;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class RememberMeApplicationTests {

    @Autowired
    MockMvc mvc;

    private MvcResult login(boolean remember) throws Exception {
        MockHttpServletRequestBuilder request = post("/perform-login")
                .with(csrf())
                .param("username", "student")
                .param("password", "demo-pass");

        if (remember) {
            request.param("remember-me", "on");
        }

        return mvc.perform(request)
                .andExpect(status().is3xxRedirection())
                .andExpect(header().string("Location",
                        containsString("/api/me")))
                .andReturn();
    }

    @Test
    void loginPageHasRememberCheckbox() throws Exception {
        mvc.perform(get("/sign-in"))
                .andExpect(status().isOk())
                .andExpect(content().string(
                        containsString("name=\"remember-me\"")));
    }

    @Test
    void unauthenticatedPrivateRequestRedirectsToLogin()
            throws Exception {
        mvc.perform(get("/api/me")
                        .accept(MediaType.TEXT_HTML))
                .andExpect(status().is3xxRedirection())
                .andExpect(header().string("Location",
                        containsString("/sign-in")));
    }

    @Test
    void loginWithoutRememberDoesNotSetRememberCookie()
            throws Exception {
        MvcResult loggedIn = login(false);
        assertNull(loggedIn.getResponse().getCookie("remember-me"));

        MockHttpSession session = (MockHttpSession)
                loggedIn.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/api/me").session(session))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.username").value("student"))
                .andExpect(jsonPath("$.rememberMe").value(false));
    }

    @Test
    void optingInIssuesRememberCookieWithSeparateLifetime()
            throws Exception {
        MvcResult loggedIn = login(true);
        Cookie cookie = loggedIn.getResponse().getCookie("remember-me");
        assertNotNull(cookie);
        assertEquals(14 * 24 * 60 * 60, cookie.getMaxAge());
    }

    @Test
    void rememberCookieCanAuthenticateWithoutOriginalSession()
            throws Exception {
        MvcResult loggedIn = login(true);
        Cookie cookie = loggedIn.getResponse().getCookie("remember-me");
        assertNotNull(cookie);

        MockHttpSession prior = (MockHttpSession)
                loggedIn.getRequest().getSession(false);
        assertNotNull(prior);
        prior.invalidate(); // Only drop the session, do not clear the remember cookie.

        mvc.perform(get("/api/me").cookie(cookie))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.username").value("student"))
                .andExpect(jsonPath("$.rememberMe").value(true));
    }

    @Test
    void rememberMeIsNotFullyAuthenticated() throws Exception {
        Cookie cookie = login(true).getResponse()
                .getCookie("remember-me");
        assertNotNull(cookie);

        mvc.perform(get("/api/strong").cookie(cookie))
                .andExpect(status().is3xxRedirection())
                .andExpect(header().string("Location",
                        containsString("/sign-in")));
    }

    @Test
    void strongEndpointWorksAfterInteractiveLogin()
            throws Exception {
        MockHttpSession session = (MockHttpSession)
                login(false).getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/api/strong").session(session))
                .andExpect(status().isOk())
                .andExpect(content().string("FULL_LOGIN_REQUIRED"));
    }

    @Test
    void badPasswordDoesNotIssueRememberCookie() throws Exception {
        MvcResult result = mvc.perform(post("/perform-login")
                .with(csrf())
                .param("username", "student")
                .param("password", "wrong")
                .param("remember-me", "on"))
                .andExpect(status().is3xxRedirection())
                .andExpect(header().string("Location",
                        containsString("/sign-in?error")))
                .andReturn();

        assertNull(result.getResponse().getCookie("remember-me"));
    }

    @Test
    void invalidRememberCookieDoesNotAuthenticate() throws Exception {
        Cookie bad = new Cookie("remember-me", "invalid-token");
        mvc.perform(get("/api/me").cookie(bad))
                .andExpect(status().is3xxRedirection())
                .andExpect(header().string("Location",
                        containsString("/sign-in")));
    }

    @Test
    void logoutClearsRememberCookie() throws Exception {
        Cookie cookie = login(true).getResponse()
                .getCookie("remember-me");
        assertNotNull(cookie);

        MvcResult out = mvc.perform(post("/logout")
                .with(csrf())
                .cookie(cookie))
                .andExpect(status().is3xxRedirection())
                .andExpect(header().string("Location",
                        containsString("/sign-in?logout")))
                .andReturn();

        Cookie cleared = out.getResponse().getCookie("remember-me");
        assertNotNull(cleared);
        assertEquals(0, cleared.getMaxAge());
    }
}
```

Result is **expected to be 10 passing tests** if the project and library versions match. Run:

```bash
mvn test
```

**Explanation of each test group:**

- The first two tests verify the public login page and protected redirect.
- Login **without ticking the checkbox** proves session authentication works without issuing an extra remember cookie.
- Login with the checkbox ticked proves a remember token is issued with an independent lifetime.
- The test invalidating `MockHttpSession` and then sending **only the remember-me cookie** proves the old session does not need to exist for auto-login.
- `.fullyAuthenticated()` rejects `RememberMeAuthenticationToken`, while the session after password login allows the strong endpoint.
- Wrong password does not create a remember cookie.
- A forged token is rejected.
- Logout sends a cookie-clear instruction via the corresponding `Set-Cookie`.

The tests use `.with(csrf())` from `spring-security-test` to generate a valid CSRF token for MockMvc; **a real client cannot send a literal `csrf()`**. The browser needs the CSRF token from the page/view/repository in use.

**Limitations:** `MockMvc` does not run a real clock for the 1-minute idle timeout, and does not test Browser Session Restore, TLS handshakes, cross-browser cookie policies, distributed sessions, or persistent DB token rotation. To verify real timeout behavior, use an embedded server/browser or integration tests controlling container clock/session lifetime. Expected test results are not a log run in a production environment.

### 10.2. Why Do HTTP Login Tests Not Put Passwords Directly in the URL?

Form login must use POST with a request body and valid CSRF. Do not put passwords in the query string because URLs can end up in history, referrers, and access logs. In tests, `.param(...)` simulates form parameters with demo values. In real runs, transmit forms over HTTPS and do not log request bodies containing credentials.

## 11. Troubleshooting

### 11.1. Increased Session Timeout, Yet Browser Still Prompts for Login After Reopening

The browser may not keep the session cookie, the session may be invalidated, the session store may have lost data, or the inactivity window may have elapsed. **Session timeout only controls the server-side session**, and does not guarantee the browser retains and sends `JSESSIONID` for the same duration. If you want auto-login after the session expires, consider remember-me according to your threat model.

### 11.2. Checked “Remember me”, Yet No Remember Cookie Is Issued

Check:

1. Does the form have `name="remember-me"` and send a value when the checkbox is checked?
2. Is `.rememberMe(...)` enabled on the right `SecurityFilterChain`?
3. Does `loginProcessingUrl` match the POST action, and does the POST have a valid CSRF token?
4. Did form login authentication actually succeed? Remember cookies must not be issued on a wrong password.
5. Are `alwaysRemember`, custom `RememberMeServices`, cookie name/path, or a proxy rewriting cookies configured?
6. Is the browser blocking the cookie because of `Secure` over HTTP, SameSite, domain/path, or privacy policy?
7. If logging in via a custom REST JSON endpoint, is the remember-me listener invoked properly? Do not assume form-login `RememberMeServices` works automatically with every custom login controller.

### 11.3. Remember Cookie Exists, Yet Auto-Login Does Not Happen

Check whether the cookie is actually **sent back** in the request. Then inspect:

- Expired cookie or invalid signature/token.
- Signing key changed across instances/restarts.
- User's password hash changed; e.g., `InMemoryUserDetailsManager` BCrypt re-hashes on every startup.
- User is disabled/locked/deleted or disallowed from auto-authentication.
- With persistent tokens, the record was deleted, expired, mismatched after rotation, or the repository cannot connect.
- Another security chain matched the URL first and **does not have remember-me enabled**.
- Dev environment uses HTTP with a `Secure` cookie so the cookie is not sent.

Do not blame `HttpSession` timeout for remember-me failure; the two lifetimes are separate.

### 11.4. `/api/me` Works, Yet `/api/strong` Prompts for Login

That can be **correct behavior**. `RememberMeAuthenticationToken` is accepted by `.authenticated()`, whereas `.fullyAuthenticated()` requires a stronger login. Check the `rememberMe` JSON field at `/api/me` to see the authentication type. Do not disable `.fullyAuthenticated()` just to silence the prompt if the business requires re-authentication.

### 11.5. Still Logged In After Logout When Using a Copied Cookie

If using a token-based signed cookie, the server has no token record to revoke individual cookie copies. Logout clears the cookie **on the browser receiving the response**, but a stolen copy can be replayed until the token expires or the password hash/key changes. When active revocation is needed, use persistent tokens or another session/token revocation mechanism and test it thoroughly.

### 11.6. After Restart, Remember Cookie Is Rejected Even Before 14 Days

If a demo app re-hashes BCrypt on startup, the hash changes; a token-based cookie signature normally depends on the password hash and key, so old cookies are rejected. In real applications, encoded passwords must be persisted in a database and the signing key must not change arbitrarily. With persistent tokens, the DB token repository must also persist across restarts.

### 11.7. Session Was “Remembered”, Yet Roles Are Outdated

A session may have stored authorities from login time. With remember-me, user details are normally reloaded on auto-authentication so there is an opportunity to refresh them, though this does not replace real-time revocation/authorization policies. Sensitive actions should re-check account status/permissions if required by business rules.

### 11.8. Mistaking “14-Day Remember-me” for “14-Day Active Session”

Cookie validity is independent of the session inactivity interval. When remember-me auto-authenticates, it may create a **new** session with the standard idle timeout. This does not turn a remember-me token into `JSESSIONID` and does not keep it alive indefinitely if the user does not return in time or the cookie expires.

### 11.9. Not Seeing the Cookie in MockMvc or Browser Devtools

`Set-Cookie` is a response header; `Cookie` is a request header. Inspect the successful login request with the checkbox checked, the redirect status, and the response cookies. Some browser mechanisms hide `HttpOnly` cookies from JavaScript while still showing them in devtools; do not rely on `document.cookie` to conclude a cookie does not exist.

### 11.10. Disabling CSRF to Make POST Login/Logout Work

In a browser app using session cookies, CSRF is an important part of the threat model. `permitAll()` only removes the authorization requirement on a URL; **it does not disable `CsrfFilter`**. Thymeleaf POST forms need a CSRF token; logout should be performed via POST with a valid token. Do not disable CSRF globally just to “test quickly”.

## 12. Production Remember-me Design Checklist

1. **Clarify the goal:** do you want a longer idle session or auto-login **after the session is lost**? The two needs are not equivalent.
2. **Issue tokens only with user consent?** Check the checkbox, privacy policy, and shared-device UX.
3. **Define lifetimes:** session idle timeout and remember-me validity are independent; is there a rolling window or hard max lifetime?
4. **Use HTTPS and secure cookies:** verify `Secure`, `HttpOnly`, `SameSite`, domain/path, HSTS, and proxy TLS termination.
5. **Token strategy:** signed token-based cookie or persistent DB token? Do you need per-user/per-device revocation, rotation, and replay alerts?
6. **Signing key:** strong secret, stored outside source, consistent across a cluster, with a rotation strategy and handling of old cookies.
7. **Stable password hashes:** if token-based depends on the encoded password, do not re-hash on every startup in production.
8. **Sensitive endpoints:** use `.fullyAuthenticated()` or explicit step-up/MFA/recent-login policies instead of `.authenticated()` everywhere.
9. **CSRF:** login/logout forms include CSRF tokens to prevent cross-site state-changing requests; do not use GET for logout when CSRF is enabled.
10. **Logout:** session invalidation + cookie clearing + repository token revocation when a DB is used; define single-device vs. all-device scope.
11. **Account disable/password change:** verify auto-login behavior, existing sessions, old tokens, and forced re-authentication.
12. **Testing:** unchecked box, checked box, expired session with valid remember cookie, tampered token, logout, `fullyAuthenticated`, key/password rotation, and concurrent use if persistent.
13. **Safe observability:** redact tokens/headers and never log values of `remember-me`/`JSESSIONID`.
14. **Cookie theft:** a token cookie is a bearer credential; consider anomalous-device detection, MFA, and shorter validity windows.
15. **Session lifecycle:** session fixation protection, maximum sessions, session registry, and session store if required by the app; remember-me does not configure these for you.

## 13. Practice Exercises

**Exercise 1 — Change session timeout:** Set `server.servlet.session.timeout=30s`, keep `tokenValiditySeconds` at 14 days. In the browser, delete only `JSESSIONID` and test `/api/me` with the remember cookie. Explain why authentication still succeeds.

**Exercise 2 — Leave checkbox unchecked:** Log in with password without selecting remember-me. Delete the session and access `/api/me`; it should redirect to login. Add a test verifying no session is sent and no remember cookie is present.

**Exercise 3 — `fullyAuthenticated` policy:** Change `/api/strong` from `.fullyAuthenticated()` to `.authenticated()` and compare whether the remember cookie grants access. Explain the security trade-off and when step-up authentication is required.

**Exercise 4 — Change signing key:** Change `REMEMBER_ME_KEY` on one instance in a dev cluster. Observe that a token from the previous node cannot be verified on another node. Propose a unified key management approach.

**Exercise 5 — Persistent token:** Add `spring-boot-starter-jdbc`, H2 for local use, the `persistent_logins` table, and `JdbcTokenRepositoryImpl`. Write tests for token rotation and logout revocation; explain the race when multiple requests arrive concurrently.

**Exercise 6 — Change password:** With the token-based strategy, persist the hash and then change the password. Check whether the old token is rejected; compare with an existing authenticated session. Define a policy that actively invalidates sessions.

**Exercise 7 — Logout scope:** Suppose a user has three remembered devices. Distinguish logging out device A, revoking all remember-me tokens, and locking the account; specify the data model needed if a device list is required.

**Exercise 8 — Browser security:** Check `Secure`, `HttpOnly`, and `SameSite` flags in an HTTPS deployment. Explain why an unexpired cookie does not guarantee the server will accept it or the browser will send it.

## Conclusion

**Extending `HttpSession` lifetime keeps a logged-in session alive longer. Remember-me stores a separate credential to automatically re-authenticate when that session is gone.** In Spring Security Servlet, remember-me can create a `RememberMeAuthenticationToken` accepted by `.authenticated()`, while `.fullyAuthenticated()` can require interactive re-login for sensitive actions. Signed tokens in cookies and persistent tokens have different revocation and rotation models; both require HTTPS, bounded lifetimes, cookie protection, logout handling, and deliberate security testing.