# Practice Lab: Concurrent Sessions, Remember-Me, and Access Revocation

**Module:** Spring Security – Servlet  
**Parent topic:** Integrated Practice

## 1. Scenario, Goals, and Acceptance Criteria

A web application using Spring MVC, session cookies, and form login needs to satisfy these requirements:

1. Each account maintains at most **one valid interactive login session** at inspection time. If Alice signs in on browser B after browser A, session A must be **marked expired** and must no longer be accepted on the next request to the server.
2. Users can select **Remember me** to receive a long-lived cookie allowing re-authentication when the short-lived session disappears, yet **that cookie must not be treated as an active interactive session** and must have a revocation mechanism.
3. Logout must end the current session and delete the browser's remember-me cookie; with persistent remember-me, the server-side token series must be handled per the corresponding mechanism.
4. Administrators can **revoke an account's access**: mark managed sessions expired and request deletion of that user's persistent remember-me tokens.
5. POST logout and POST revocation still require a **valid CSRF token**; only users with the ADMIN role may invoke the revocation feature.
6. Automated **tests** verify login/logout, authorization, CSRF, remember-me cookies, the single-session policy, and token deletion logic.
7. Do not overpromise security guarantees: a session marked expired is normally blocked/invalidated only on its next request. **In-flight requests** are not necessarily aborted instantaneously; **multi-node environments** require shared state management.

**Learning outcomes:** understand the differences between session authentication, remember-me authentication, and revocation; properly configure `maximumSessions`, `SessionRegistry`, and `PersistentTokenRepository`; know how to test and operate without relying on a mock user or in-memory data in production.

### Overall Flow Diagram

~~~text
Alice / Browser A                            Servlet Application
       | POST /login + username/password + _csrf |
       |----------------------------------------->|
       |  Session A, SecurityContext = alice      |
       |<-----------------------------------------|
       | GET /me -> 200                           |
       |----------------------------------------->|

Alice / Browser B
       | POST /login + password + _csrf           |
       |----------------------------------------->|
       |  SessionRegistry: max 1 session          |
       |  Mark Session A = expired                |
       |  Register Session B = active             |
       |<-----------------------------------------|

Browser A: GET /me
       |----------------------------------------->|
       | ConcurrentSessionFilter detects A        |
       | invalidates session, handles expiration  |
       |<-----------------------------------------|

Admin
       | POST /admin/revoke + target=alice + _csrf|
       |----------------------------------------->|
       | SessionRegistry: expire Alice sessions   |
       | PersistentTokenRepository: remove tokens |
       |<-----------------------------------------|

Subsequent requests using revoked session/token:
       |--> expired session blocked when processed
       |--> deleted remember-me token series invalid
~~~

**Scope:** this is Spring Security **Servlet**, not WebFlux. The project uses **Spring Boot 3.3.5, Java 17, and a single JVM**, focusing on mechanics and boundaries to know before designing for production.

## 2. Three Kinds of State Not to Confuse

| Object | Where Stored/Transmitted | Purpose | Affected By Which Actions? |
| --- | --- | --- | --- |
| **HTTP session** | Server and session cookie (usually JSESSIONID) | Binds browser to authenticated `SecurityContext` | Logout, session timeout, session invalidation, concurrency expiry |
| **SessionRegistry** | Registry tracking session IDs and principals | Counts, looks up, and marks sessions for concurrent session control | Login registration, session destroy/expire, admin calling `expireNow()` |
| **Persistent remember-me token** | Browser cookie + token series in repository | Can restore authentication after the session expires | Logout, token rotation, explicit repository revocation, token expiry, cookie loss |

**SessionRegistry is not the HTTP session store**, and **PersistentTokenRepository does not store SecurityContext**. Any "access revocation" operation must specify exactly which layer is invalidated, on which devices, for how long, and within what acceptable latency.

For example: deleting session A while leaving a valid remember-me cookie can cause browser A to re-authenticate automatically. Conversely, deleting only the remember-me token **without** expiring an already-authenticated session will not immediately strip access from subsequent requests on that active session.

### 2.1. What Kind of Authentication Follows Remember-Me?

In Spring Security, when remember-me authenticates successfully, the principal is normally wrapped in `RememberMeAuthenticationToken` and counts as authenticated for endpoints using `authenticated()`.

For sensitive actions like changing passwords or transferring funds, consider **`fullyAuthenticated()`** or step-up authentication per your threat model, since remember-me authentication does not prove the user recently re-entered their password. `fullyAuthenticated()` excludes both anonymous and remember-me authentication under Spring Security semantics.

**Never** inspect `authentication.isAuthenticated()` alone and assume the user just signed in interactively; check the Authentication type and specific policy.

## 3. Concurrent Sessions in Spring Security Servlet

### 3.1. maximumSessions(1)

Modern configuration example:

~~~java
// Snippet inside Spring Security 6 HttpSecurity DSL.
http.sessionManagement(session -> session
    .maximumSessions(1)
    .maxSessionsPreventsLogin(false)
    .sessionRegistry(sessionRegistry)
);
~~~

Meaning:

- `maximumSessions(1)`: caps concurrent sessions per principal recognized by the registry.
- `maxSessionsPreventsLogin(false)`: allows the new login and **marks the old session expired** to make room. This fits "new device replaces old device" requirements.
- `maxSessionsPreventsLogin(true)`: instead of evicting the old session, **rejects the new login** once the limit is reached. When toggling this option, test failed logins and user experience.
- `sessionRegistry(sessionRegistry)`: supplies a shared registry for concurrency control and administrative components.

In the default `false` mode, the new login **does not immediately remotely terminate** in-flight requests on the prior session; a `SessionInformation` is marked expired and `ConcurrentSessionFilter` handles it on that session's next request.

### 3.2. SessionRegistryImpl and HttpSessionEventPublisher

In a single-JVM demo:

~~~java
@Bean
SessionRegistry sessionRegistry() {
    return new SessionRegistryImpl();
}

@Bean
HttpSessionEventPublisher httpSessionEventPublisher() {
    return new HttpSessionEventPublisher();
}
~~~

`SessionRegistryImpl` tracks principals and session IDs **in process memory**. `HttpSessionEventPublisher` lets Spring Security receive session creation/destruction events from the servlet container to clean up the registry in standard setups.

Omitting session destroy events can leave expired/destroyed session IDs in the registry and skew session counts. **Do not treat an `HttpSessionEventPublisher` bean as a multi-node session solution.**

### 3.3. Testing with Two Browsers

1. Open Chrome profile A, go to `/login`, and sign in as Alice.
2. In profile B (independent cookies/session), also sign in as Alice.
3. In profile B, `GET /me` keeps working.
4. In profile A, the next request to `/me` must be handled as **session expired**; per defaults it may redirect to `/login?expired`.
5. Repeat with `maxSessionsPreventsLogin(true)`: profile B must be denied login while A holds an active session.

**You must use two independent cookie stores.** Two tabs in the same browser profile normally **share the same session cookie**, so opening a second tab does not prove two independent sessions.

**Key insight:** session concurrency applies to sessions that Spring Security **tracks**, typically from successful authentication; remember-me auto-login, session fixation, custom filters, and asynchronous operations need dedicated testing. Never interpret `maximumSessions(1)` as an absolute guarantee that two in-flight HTTP requests from one user can never overlap.

## 4. Remember-Me: Cookies Are Not Sessions

Spring Security Servlet offers remember-me in two common modes:

- **Token-based remember-me**: the cookie holds data signed/verified with a secret; simpler, but revoking individual tokens can be difficult without extra server-side tracking.
- **Persistent token-based remember-me**: the cookie carries a series/token while the server stores a **persistent token record** keyed by series and username. The token rotates when used to re-authenticate; the server can delete a user's series to revoke access.

This lab uses **persistent remember-me** via `PersistentTokenRepository`. The demo uses `InMemoryTokenRepositoryImpl`; real systems should use a durable repository backed by a database or shared data store with proper security, backups, HA, and expired-token cleanup.

### 4.1. Remember-Me Flow

~~~text
POST /login (username, password, _csrf, remember-me=on)
    |
    +--> Password verification succeeds
    |
    +--> PersistentTokenRepository.createNewToken(series, token, user)
    |
    +--> Set-Cookie: remember-me=... (HTTP-only per config)
    |
    +--> Browser stores cookie
              |
              +--> Session cookie lost/expired, remember-me still present
                      |
                      +--> RememberMeAuthenticationFilter
                      +--> Look up token series in repository
                      +--> Verify token and rotate new token
                      +--> Authentication of type RememberMeAuthenticationToken
~~~

Never log raw remember-me cookies/tokens into logs, dashboards, docs, or URLs. Cookie tokens are **stealable credentials**; use HTTPS, `Secure`, `HttpOnly`, appropriate `SameSite`, and bounded lifetimes. `SameSite` is supplemental defense, not a replacement for all CSRF controls.

Persistent token series can be deleted via `removeUserTokens(username)`. This is server-side revocation, far stronger than merely telling one browser to clear its cookie (another browser may still hold a copy).

### 4.2. Remember-Me Logout and Revocation

When remember-me is configured, `LogoutFilter` typically invokes `RememberMeServices.logout` to clear the remember-me cookie and update the token repository per implementation. For persistent implementations, logout can delete the user's series per its contract. **Check and test your specific version** rather than assuming logout clears only the session.

When an administrator revokes access, perform two independent steps:

1. `SessionInformation.expireNow()` for every registry-tracked session of that account.
2. `PersistentTokenRepository.removeUserTokens(username)` so old remember-me cookies have no server-side token record left.

Once tokens are removed, a browser may still display the physical cookie until the server sends a clearing cookie or the browser evicts it. **A cookie still existing on disk does not mean the credential is still valid.** Conversely, do not claim every device is blocked instantaneously: in-flight requests, independent JWT access tokens, and other nodes lacking a shared registry can still behave per their own policies.

## 5. Matrix of Effects and Revocation Boundaries

| Action | Current HTTP Session | Other Sessions | Persistent Remember-Me |
| --- | --- | --- | --- |
| Standard user logout | Logout request's session invalidated per config | Does not invalidate all other sessions by default | Browser cookie cleared; implementation handles token repository |
| New login with maximumSessions(1), preventsLogin=false | New session active | Previously tracked session marked expired | Does not delete all remember-me series by default |
| Admin expireNow by username | User's registry sessions marked expired | Other sessions **in the same registry** marked expired | **Unchanged** if only expireNow is called |
| Admin removeUserTokens(username) | **Does not invalidate authenticated sessions** | Does not invalidate | Deletes the user's persistent records in repository |
| Admin performs both | Managed sessions blocked on next request | Same within the registry's scope | Old cookie series cannot re-authenticate |
| Password change | Policy-dependent; **not guaranteed to revoke all sessions/tokens by default** | Implementation-dependent | Should trigger explicit revocation after password change |

**Example assumption:** all requests hit **a single instance**. A cluster requires a shared session store + registry + token repository along with a coordinated revocation policy.

## 6. Runnable Practice Project — Spring Boot 3.3.5 / Java 17

The project includes default form login, a Thymeleaf-rendered admin form, an identity inspection endpoint, and a revocation service. Hardcoded passwords are for localhost learning only.

### 6.1. Directory Structure

~~~text
session-revocation-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── SessionLabApplication.java
    │   │   ├── SecurityConfiguration.java
    │   │   ├── AccessRevocationService.java
    │   │   └── LabController.java
    │   └── resources/
    │       ├── application.yml
    │       └── templates/revoke-form.html
    └── test/java/demo/
        ├── LabHttpSecurityTests.java
        └── AccessRevocationServiceTests.java
~~~

### 6.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>session-revocation-lab</artifactId>
    <version>1.0.0</version>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
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
~~~

`starter-security` provides Servlet security/remember-me/concurrent session infrastructure, `starter-thymeleaf` renders the admin form, and `spring-security-test` supports `csrf()`, `user()`, and login tests in MockMvc. Neither Spring Session nor JDBC is added in this **single-JVM** demo; for production, see Section 11.

### 6.3. src/main/resources/application.yml

~~~yaml
app:
  remember-me:
    key: ${APP_REMEMBER_ME_KEY}

server:
  servlet:
    session:
      timeout: 20m
~~~

`APP_REMEMBER_ME_KEY` is a **required environment variable**. Never hardcode secrets in the source repository or use sample keys in production. Across multiple instances, the key and repository must stay consistent under a key rotation plan.

`server.servlet.session.timeout` sets the short-lived session timeout; remember-me validity below is 7 days. Session timeout and remember-me cookie expiry are **two separate parameters**.

### 6.4. src/main/java/demo/SessionLabApplication.java

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SessionLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(SessionLabApplication.class, args);
    }
}
~~~

### 6.5. src/main/java/demo/SecurityConfiguration.java

~~~java
package demo;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.session.SessionRegistry;
import org.springframework.security.core.session.SessionRegistryImpl;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.rememberme.InMemoryTokenRepositoryImpl;
import org.springframework.security.web.authentication.rememberme.PersistentTokenRepository;
import org.springframework.security.web.session.HttpSessionEventPublisher;

@Configuration
@EnableMethodSecurity
public class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        // DEMO ONLY: never use hardcoded passwords in production.
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("demo-only"))
                .roles("USER")
                .build(),
            User.withUsername("bob")
                .password(encoder.encode("demo-only"))
                .roles("USER")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("demo-only"))
                .roles("ADMIN")
                .build()
        );
    }

    @Bean
    SessionRegistry sessionRegistry() {
        return new SessionRegistryImpl();
    }

    @Bean
    HttpSessionEventPublisher httpSessionEventPublisher() {
        return new HttpSessionEventPublisher();
    }

    @Bean
    PersistentTokenRepository persistentTokenRepository() {
        // In-memory for single-JVM practice only.
        return new InMemoryTokenRepositoryImpl();
    }

    @Bean
    SecurityFilterChain filterChain(
            HttpSecurity http,
            UserDetailsService users,
            SessionRegistry sessionRegistry,
            PersistentTokenRepository tokenRepository,
            @Value("${app.remember-me.key}") String rememberKey)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/", "/health")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/me")
                    .authenticated()
                .requestMatchers(HttpMethod.GET, "/admin/revoke-form",
                    "/admin/sessions").hasRole("ADMIN")
                .requestMatchers(HttpMethod.POST, "/admin/revoke")
                    .hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .formLogin(form -> form
                .defaultSuccessUrl("/me", true)
                .permitAll()
            )
            .rememberMe(remember -> remember
                .key(rememberKey)
                .userDetailsService(users)
                .tokenRepository(tokenRepository)
                .rememberMeParameter("remember-me")
                .tokenValiditySeconds(7 * 24 * 60 * 60)
            )
            .sessionManagement(session -> session
                .sessionFixation(fixation -> fixation.migrateSession())
                .maximumSessions(1)
                .maxSessionsPreventsLogin(false)
                .sessionRegistry(sessionRegistry)
            )
            .logout(logout -> logout
                .logoutSuccessUrl("/login?logout")
                .permitAll()
            );

        // CSRF remains ENABLED by default for login, logout, and admin POST.
        return http.build();
    }
}
~~~

**Configuration breakdown:**

1. `@EnableMethodSecurity` enables `@PreAuthorize` on the revocation service; HTTP rules guard the endpoint as layer one, method security as layer two.
2. `SessionRegistryImpl` looks up sessions by principal; it is not a durable session store. `HttpSessionEventPublisher` cleans up session metadata when the container fires session destroy events.
3. `maximumSessions(1)` + `maxSessionsPreventsLogin(false)` prioritizes the newest login and marks the old session expired.
4. `PersistentTokenRepository` provides server-side storage for persistent remember-me. `InMemoryTokenRepositoryImpl` **loses data on restart** and is not shared across nodes.
5. The remember-me secret is injected from the environment; production must protect keys, cookies, HTTPS, and follow a rotation schedule.
6. `formLogin(...permitAll())` enables the default login page/processing endpoints without opening all URLs.
7. `anyRequest().denyAll()` ensures undeclared endpoints do not become public automatically.
8. Spring Security handles logout and CSRF; never call `csrf.disable()` just to invoke the admin POST from curl.
9. `migrateSession()` protects against session fixation via session ID rotation/session migration per Servlet runtime semantics.
10. `ROLE_ADMIN` (from `.roles("ADMIN")`) is required to revoke, never ordinary users.

**Limitation note:** remember-me auto-authentication can establish sessions under a distinct lifecycle; to ensure concurrency limits hold across multiple authentication types/providers, run end-to-end tests covering both remember-me and interactive logins on your stack. `maximumSessions(1)` is not a standalone "global device inventory" independent of the session registry.

### 6.6. src/main/java/demo/AccessRevocationService.java

~~~java
package demo;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.session.SessionInformation;
import org.springframework.security.core.session.SessionRegistry;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.web.authentication.rememberme.PersistentTokenRepository;
import org.springframework.stereotype.Service;

@Service
public class AccessRevocationService {

    private final SessionRegistry registry;
    private final PersistentTokenRepository tokens;

    public AccessRevocationService(
            SessionRegistry registry,
            PersistentTokenRepository tokens) {
        this.registry = registry;
        this.tokens = tokens;
    }

    @PreAuthorize("hasRole('ADMIN')")
    public int revoke(String username) {
        if (username == null || username.isBlank()) {
            throw new IllegalArgumentException("Invalid username");
        }

        int expired = 0;
        for (Object candidate : registry.getAllPrincipals()) {
            if (candidate instanceof UserDetails details
                    && username.equals(details.getUsername())) {
                for (SessionInformation info
                        : registry.getAllSessions(candidate, false)) {
                    info.expireNow();
                    expired++;
                }
            }
        }

        // Revoke persistent remember-me series for username.
        tokens.removeUserTokens(username);
        return expired;
    }

    @PreAuthorize("hasRole('ADMIN')")
    public int activeSessions(String username) {
        int count = 0;
        for (Object candidate : registry.getAllPrincipals()) {
            if (candidate instanceof UserDetails details
                    && username.equals(details.getUsername())) {
                count += registry.getAllSessions(candidate, false).size();
            }
        }
        return count;
    }
}
~~~

**Exact limitations explained:**

- `SessionRegistry#getAllPrincipals()` returns principal objects, not necessarily username strings. The demo uses `UserDetails` created by in-memory form login; with OAuth2/OIDC login, custom principals, or other providers, matching logic **must adapt to the principal type and a stable identifier key**. Match by username only when it is guaranteed unique within the application's scope.
- `getAllSessions(candidate, false)` returns non-expired sessions known to the registry. `expireNow()` **only marks** them; it is not an HTTP call aborting an in-flight request.
- `removeUserTokens(username)` returns `void`, so the service **cannot report how many tokens were actually deleted**. The response confirms only that removal was **requested**, never fabricating a fake token count.
- If the target user changed passwords, holds sessions on another node, or holds separate JWT access tokens, these two calls **do not resolve all of them automatically**. See Section 11.
- Production needs auditing of who initiated revocation, reason, target validation, fine-grained authorization, CSRF, rate limiting, and never leaking session IDs in responses.
- `@PreAuthorize` takes effect when invoked through a **Spring-managed bean/proxy**. Instantiating the service via `new` in the unit test below tests only the **revocation logic**, not the method-security proxy; HTTP tests verify authorization.

### 6.7. src/main/java/demo/LabController.java

~~~java
package demo;

import java.util.List;
import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseBody;

@Controller
public class LabController {

    private final AccessRevocationService revocation;

    public LabController(AccessRevocationService revocation) {
        this.revocation = revocation;
    }

    @GetMapping("/")
    @ResponseBody
    public Map<String, String> home() {
        return Map.of("message", "session-lab");
    }

    @GetMapping("/health")
    @ResponseBody
    public Map<String, String> health() {
        return Map.of("status", "up");
    }

    @GetMapping("/me")
    @ResponseBody
    public Map<String, Object> me(Authentication authentication) {
        List<String> roles = authentication.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .toList();

        return Map.of(
            "user", authentication.getName(),
            "authenticationType",
                authentication.getClass().getSimpleName(),
            "authorities", roles
        );
    }

    @GetMapping("/admin/revoke-form")
    public String revokeForm() {
        return "revoke-form";
    }

    @GetMapping("/admin/sessions")
    @ResponseBody
    public Map<String, Object> activeSessions(
            @RequestParam String username) {
        return Map.of(
            "user", username,
            "activeSessions", revocation.activeSessions(username)
        );
    }

    @PostMapping("/admin/revoke")
    @ResponseBody
    public Map<String, Object> revoke(
            @RequestParam String username) {
        int expired = revocation.revoke(username);
        return Map.of(
            "user", username,
            "sessionsMarkedExpired", expired,
            "rememberMeTokenRemovalRequested", true
        );
    }
}
~~~

`/admin/revoke` **never** returns session IDs or raw tokens. `sessionsMarkedExpired` is only the count marked in the registry, not proof that every browser or access token across the system has been revoked.

The controller accepts only the target `username`; the **administrator's** identity must be verified via `Authentication` and enforced by filters + method security, never taken from a hidden field like `isAdmin=true`.

### 6.8. src/main/resources/templates/revoke-form.html

~~~html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Revoke Access</title>
</head>
<body>
    <h1>Revoke Sessions and Remember-Me Tokens</h1>
    <p>Only ROLE_ADMIN accounts can access this page.</p>

    <form method="post" action="/admin/revoke">
        <label for="username">Account to revoke</label>
        <input id="username" name="username" type="text"
               maxlength="100" required>
        <input type="hidden"
               th:name="${_csrf.parameterName}"
               th:value="${_csrf.token}">
        <button type="submit">Revoke</button>
    </form>
</body>
</html>
~~~

The POST form includes an **explicit** CSRF field populated from the Spring Security request. `action="/admin/revoke"` assumes the demo runs at the root context path; under a custom context path, use Thymeleaf `@{/admin/revoke}` and inspect the rendered HTML. If using `th:action`, Spring/Thymeleaf can auto-inject the CSRF input; avoid emitting two duplicate fields.

The GET page is restricted to admins, yet **hiding buttons or forms is not access control**. `SecurityFilterChain` and `@PreAuthorize` are what block unauthorized POSTs.

## 7. Running the Practice with Two Browser Profiles

### 7.1. Setting the Secret and Running Maven

On PowerShell (using a local key—**never** use in production):

~~~powershell
$env:APP_REMEMBER_ME_KEY = "LOCAL-DEMO-ONLY-change-to-a-long-random-key"
mvn spring-boot:run
~~~

On bash/zsh:

~~~bash
export APP_REMEMBER_ME_KEY="LOCAL-DEMO-ONLY-change-to-a-long-random-key"
mvn spring-boot:run
~~~

Open:

~~~text
http://localhost:8080/login
~~~

Demo accounts:

| Username | Password | Authorities |
| --- | --- | --- |
| `alice` | `demo-only` | `ROLE_USER` |
| `bob` | `demo-only` | `ROLE_USER` |
| `admin` | `demo-only` | `ROLE_ADMIN` |

These are dummy accounts for localhost only. Production must use an appropriate identity store, protected password hashing, MFA where warranted, HTTPS, and securely configured session cookies.

### 7.2. Scenario A: Maximum One Login Session

1. Open browser profile A and sign in as Alice at `/login`.
2. Visit `/me`; the JSON must show `"user":"alice"`.
3. Open browser profile B with an independent cookie store and sign in as Alice.
4. Visit `/me` in B; expect B to be authenticated.
5. Reload `/me` in A: with `maxSessionsPreventsLogin(false)`, session A is considered expired; redirect/message behavior depends on defaults/handlers, typically redirecting to login with an expired parameter.
6. Sign in as Bob in another profile: Bob must not be treated as Alice's principal unless the app customizes identity mapping.

Never use two tabs in the same profile to test this because they normally share cookies. Do not assume an in-flight request on A aborts the instant B logs in; test a **new request** on A.

### 7.3. Scenario B: Remember-Me Login

1. Sign in as Alice and check remember-me (if the default login page does not display it depending on config, a custom form can submit `remember-me=on` with CSRF).
2. Observe the `remember-me` cookie on the login response. **Never copy cookie values into logs or share screenshots containing secrets.**
3. Delete the session cookie or let the session time out while keeping the valid remember-me cookie.
4. Call `/me`: if remember-me is accepted, Authentication can become `RememberMeAuthenticationToken`; the demo JSON returns `authenticationType` to show the difference.
5. Sign out via POST `/logout` with a CSRF token. The remember-me cookie must be cleared and the repository updated for the associated token.
6. Replay the old revoked cookie: remember-me authentication with a token series no longer in the repository must fail.

**Never** manually delete session cookies in a production environment to test bypasses; use a controlled browser profile/test environment.

### 7.4. Scenario C: Admin Revokes Alice

1. Sign in as Alice in profile A, optionally checking remember-me.
2. Sign in as admin in profile C.
3. Admin opens `/admin/revoke-form`, enters `alice`, and clicks Revoke.
4. The JSON response shows `sessionsMarkedExpired` (per registry), without session IDs or tokens.
5. Alice sends a **new** request to `/me`: the session marked expired is handled as invalid; the old remember-me series was deleted so that cookie cannot restore access.
6. Alice **can still sign in again with her valid password**. "Revoking sessions/tokens" **is not locking the account** or changing the password; to block future logins, add an account disable/lock policy and update/test the provider.

Check `GET /admin/sessions?username=alice` as admin: active sessions in the registry should drop to 0 after marking. If other nodes exist without a shared registry, this is **not the system-wide session count**.

### 7.5. Scenario D: Permissions and CSRF

- Alice calls `GET /admin/revoke-form` → **403** because she is logged in without `ROLE_ADMIN`.
- Alice calls `POST /admin/revoke` with a CSRF token → **403** due to authorization.
- Admin calls `POST /admin/revoke` **without a CSRF token** → **403** due to CSRF.
- Admin calls `POST /admin/revoke` **with a valid CSRF token** → reaches controller and service, returns revocation JSON.
- Unauthenticated user visits `/me` → normally redirected to `/login` by the form-login entry point.

Separate CSRF tests from role tests, because the same **403** status can stem from two different causes.

## 8. MockMvc and Unit Tests: Reproducing Behavior Without Leaking Tokens

### 8.1. src/test/java/demo/LabHttpSecurityTests.java

~~~java
package demo;

import jakarta.servlet.http.Cookie;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.security.core.session.SessionInformation;
import org.springframework.security.core.session.SessionRegistry;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;
import static org.hamcrest.Matchers.containsString;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@TestPropertySource(properties =
    "app.remember-me.key=unit-test-only-long-random-placeholder")
class LabHttpSecurityTests {

    @Autowired
    MockMvc mvc;

    @Autowired
    SessionRegistry registry;

    @Test
    void homeIsPublic() throws Exception {
        mvc.perform(get("/"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("session-lab"));
    }

    @Test
    void anonymousProfileRedirectsToLogin() throws Exception {
        mvc.perform(get("/me"))
            .andExpect(status().isFound())
            .andExpect(header().string(
                HttpHeaders.LOCATION, containsString("/login")));
    }

    @Test
    void loggedInUserCanReadOwnIdentity() throws Exception {
        mvc.perform(get("/me").with(user("alice").roles("USER")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.user").value("alice"));
    }

    @Test
    void nonAdminCannotSeeRevocationForm() throws Exception {
        mvc.perform(get("/admin/revoke-form")
                .with(user("alice").roles("USER")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminCanSeeCsrfProtectedForm() throws Exception {
        mvc.perform(get("/admin/revoke-form")
                .with(user("admin").roles("ADMIN")))
            .andExpect(status().isOk())
            .andExpect(content().string(
                containsString("name=\"_csrf\"")));
    }

    @Test
    void adminPostWithoutCsrfIsForbidden() throws Exception {
        mvc.perform(post("/admin/revoke")
                .with(user("admin").roles("ADMIN"))
                .param("username", "alice"))
            .andExpect(status().isForbidden());
    }

    @Test
    void userPostWithCsrfStillForbidden() throws Exception {
        mvc.perform(post("/admin/revoke")
                .with(user("alice").roles("USER"))
                .with(csrf())
                .param("username", "bob"))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminPostWithCsrfIsAllowed() throws Exception {
        mvc.perform(post("/admin/revoke")
                .with(user("admin").roles("ADMIN"))
                .with(csrf())
                .param("username", "not-currently-signed-in"))
            .andExpect(status().isOk())
            .andExpect(jsonPath(
                "$.rememberMeTokenRemovalRequested").value(true));
    }

    @Test
    void validPasswordCreatesInteractiveLogin() throws Exception {
        mvc.perform(post("/login")
                .with(csrf())
                .param("username", "bob")
                .param("password", "demo-only"))
            .andExpect(status().isFound())
            .andExpect(redirectedUrl("/me"));
    }

    @Test
    void wrongPasswordDoesNotAuthenticate() throws Exception {
        mvc.perform(post("/login")
                .with(csrf())
                .param("username", "bob")
                .param("password", "incorrect"))
            .andExpect(status().isFound())
            .andExpect(redirectedUrl("/login?error"));
    }

    @Test
    void rememberMeLoginIssuesCookie() throws Exception {
        MvcResult result = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "alice")
                .param("password", "demo-only")
                .param("remember-me", "on"))
            .andExpect(status().isFound())
            .andReturn();

        Cookie cookie = result.getResponse().getCookie("remember-me");
        assertThat(cookie).isNotNull();
        assertThat(cookie.getMaxAge()).isPositive();
    }

    @Test
    void laterLoginMarksEarlierSessionExpired() throws Exception {
        MvcResult first = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "alice")
                .param("password", "demo-only"))
            .andExpect(status().isFound())
            .andReturn();

        MockHttpSession sessionA =
            (MockHttpSession) first.getRequest().getSession(false);
        assertThat(sessionA).isNotNull();

        MvcResult second = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "alice")
                .param("password", "demo-only"))
            .andExpect(status().isFound())
            .andReturn();

        MockHttpSession sessionB =
            (MockHttpSession) second.getRequest().getSession(false);
        assertThat(sessionB).isNotNull();
        assertThat(sessionB.getId()).isNotEqualTo(sessionA.getId());

        boolean firstExpired = registry.getAllPrincipals().stream()
            .filter(p -> p instanceof UserDetails details
                && details.getUsername().equals("alice"))
            .flatMap(p -> registry.getAllSessions(p, true).stream())
            .anyMatch(info -> info.getSessionId().equals(
                sessionA.getId()) && info.isExpired());

        assertThat(firstExpired).isTrue();
    }

    @Test
    void logoutRequiresCsrf() throws Exception {
        mvc.perform(post("/logout")
                .with(user("alice").roles("USER")))
            .andExpect(status().isForbidden());
    }

    @Test
    void validLogoutRedirects() throws Exception {
        mvc.perform(post("/logout")
                .with(user("alice").roles("USER"))
                .with(csrf()))
            .andExpect(status().isFound())
            .andExpect(redirectedUrl("/login?logout"));
    }

    @Test
    void unlistedPathIsNotPublic() throws Exception {
        mvc.perform(get("/not-listed")
                .with(user("alice").roles("USER")))
            .andExpect(status().isForbidden());
    }
}
~~~

**Note on test isolation:** HTTP login tests can leave session/remember-me state in the shared `SessionRegistry` or repository of one `ApplicationContext`. In real suites, intentionally clean up sessions/tokens or isolate fixtures so tests do not depend on execution order, especially under parallel execution. The concurrency test here creates **two fresh sessions** and asserts session A is marked expired after login B, though a production suite should also test session A's next request, cookie rotation, and repository state via Testcontainers/real session stores.

Tests using `.with(user())` **only mock Authentication on the request**, without verifying real password login. That is why separate POST login tests exist for valid and wrong passwords. `@TestPropertySource` supplies a test-only placeholder secret, not a production secret.

### 8.2. src/test/java/demo/AccessRevocationServiceTests.java

~~~java
package demo;

import java.util.Date;

import org.junit.jupiter.api.Test;
import org.springframework.security.core.session.SessionRegistryImpl;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.web.authentication.rememberme.InMemoryTokenRepositoryImpl;
import org.springframework.security.web.authentication.rememberme.PersistentRememberMeToken;

import static org.assertj.core.api.Assertions.assertThat;

class AccessRevocationServiceTests {

    @Test
    void marksSessionExpiredAndDeletesPersistentToken() {
        var registry = new SessionRegistryImpl();
        var tokens = new InMemoryTokenRepositoryImpl();
        var service = new AccessRevocationService(registry, tokens);

        var alice = User.withUsername("alice")
            .password("{noop}not-used")
            .roles("USER")
            .build();

        registry.registerNewSession("demo-session-1", alice);
        tokens.createNewToken(new PersistentRememberMeToken(
            "alice", "demo-series-1", "demo-token-1", new Date()
        ));

        assertThat(service.activeSessions("alice")).isEqualTo(1);
        assertThat(tokens.getTokenForSeries("demo-series-1"))
            .isNotNull();

        int expired = service.revoke("alice");

        assertThat(expired).isEqualTo(1);
        assertThat(registry.getSessionInformation(
            "demo-session-1").isExpired()).isTrue();
        assertThat(service.activeSessions("alice")).isZero();
        assertThat(tokens.getTokenForSeries("demo-series-1"))
            .isNull();
    }
}
~~~

**This is a pure unit test** of `AccessRevocationService` logic: calling `new AccessRevocationService(...)` bypasses proxies, so it does not test `@PreAuthorize`. The HTTP tests above prove only ROLE_ADMIN can invoke the endpoint; to test method security directly through the proxy, add a `@SpringBootTest` with `@Autowired AccessRevocationService` and `@WithMockUser` for both admin and a regular user receiving `AccessDeniedException`.

### 8.3. Running Tests and Expectations

~~~bash
mvn test
~~~

With the files above, there are **16 tests**: 15 MockMvc tests and 1 unit test for the revocation service. All tests are expected to pass when the project is configured properly.

**These are expected outcomes, not actual Maven output run while authoring.** In environments with different listeners or session simulation, verify `MockHttpSession` and session event behavior on your specific version. An integration test with an embedded server and two cookie jars reflects real browser/session behavior more accurately.

Run a single class:

~~~bash
mvn -Dtest=LabHttpSecurityTests test
mvn -Dtest=AccessRevocationServiceTests test
~~~

Never call `csrf.disable()` just to make POST tests pass: that stops tests from exercising the very defense layer being verified.

## 9. Common Error Analysis

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Two browsers still work simultaneously | Actually sharing cookies; SessionRegistry not registering properly; login bypassed session strategy; test did not send a post-expiry request | Use two browser profiles; check session IDs, registry, login pipeline, and next request |
| New login is blocked | `maxSessionsPreventsLogin(true)`, old sessions not cleaned up, registry holds stale records | Choose the right policy; enable session destroy events; inspect registry |
| Session A expired yet still shows cached page | Browser cache or request never hit server | Issue a fresh protected request; verify network status and session |
| Remember-me does not issue a cookie | Form omitted `remember-me`, login failed, rememberMe config missing users/repository, cookie policy | Check POST fields and cookie attributes; never log cookie values |
| Remember-me stops working after restart | InMemoryTokenRepositoryImpl lost records | Use a persistent shared token repository in production |
| User still logged in on another device after logout | Standard logout handles the current browser/session, not all other sessions by default | Use admin/global revocation if business requirements demand it |
| Persistent tokens deleted yet session still works | Token repository is independent of active sessions | Expire registry sessions or invalidate the session accordingly |
| Session marked expired yet remember-me re-authenticates | Remember-me cookie was not revoked | Delete user's token series and test remember-me behavior |
| Admin POST returns 403 | Missing CSRF or missing ROLE_ADMIN | Include valid `csrf()` in role tests; verify real authorities |
| Role `ADMIN` fails `hasRole("ADMIN")` | Missing `ROLE_` prefix | Use `.roles("ADMIN")` or `authorities("ROLE_ADMIN")` |
| SessionRegistry reports 0 while user still makes requests | Different node; remember-me auto-auth not tracked like interactive login; mismatched principal identity | Use a shared registry, audit auth types, and unify identity keys |
| Stolen token still works after password change | No workflow revoking tokens/sessions on password change | Invoke revocation after password reset; lock account when needed |
| `@PreAuthorize` ignored in unit test | Service instantiated via `new`, bypassing Spring proxy | Inject Spring-managed bean for method-security integration tests |
| Many sessions linger after closing tabs | Closing a tab does not automatically invalidate server sessions; expiry relies on timeout/events | Configure timeouts, cleanup, and monitor registry counts |
| Frequent unexpected logouts across multiple nodes | In-memory session registry, inconsistent shared keys/token repository | Use Spring Session/backed registry and shared persistent token store |
| Session fixation after login | Session fixation protection not applied properly in web app | Verify session ID migration and cookies after login |
| Logout returns 302 yet data remains accessible | Logout redirect does not prove session/token revocation by itself | Check session invalidation, repository state, and post-logout requests |

## 10. Production Security and Operations

### 10.1. Database Storage for Persistent Remember-Me

`InMemoryTokenRepositoryImpl` is suitable only for learning. A production setup can use `JdbcTokenRepositoryImpl` with a persistent token table matching the release schema. When using `JdbcTokenRepositoryImpl`:

- Provision the `persistent_logins` schema via managed migrations (Flyway/Liquibase), not reckless auto-create settings.
- Index/constrain series uniquely; protect DB backups and SELECT/UPDATE/DELETE privileges.
- Enforce expired-token cleanup and retention limits.
- Monitor unusual remember-me authentication failures, token reuse, and revocation activity.
- Never place raw tokens, cookies, or DB secrets into logs, tickets, or reports.
- When rotating keys, assess impact on existing cookies and roll out consistently across nodes.

This is production guidance; the runnable example does not pretend to include a DB/H2/JDBC when `pom.xml` declares no such dependencies.

### 10.2. Spring Session for Multiple Nodes

With multiple instances behind a load balancer, `SessionRegistryImpl` sees only the **current JVM's** sessions. Design a distributed session store—such as Spring Session with a matching registry (e.g., `SpringSessionBackedSessionRegistry` when backed by a compatible repository)—or a domain-specific active-session management mechanism.

**Never assume** that merely adding Redis makes `SessionRegistryImpl`'s `expireNow()` revoke sessions on every node. Use the store-integrated registry and test propagation/revocation in a multi-node environment.

### 10.3. Access Revocation Does Not Equal Account Lockout

Suppose an admin calls revoke for Alice at time T:

- Tracked sessions are marked expired.
- Alice's persistent remember-me records are deleted.
- Requests already in-flight at T that passed authorization may continue to finish.
- If Alice still knows her password, she can **sign in again** immediately.
- If the app issues self-contained JWT access tokens with long `exp` claims, stateless APIs may continue accepting those JWTs **unless** token revocation, session/credential versioning, introspection, or short TTLs paired with refresh-token revocation are implemented.
- If API keys or mTLS certificates exist, each credential type needs its own revocation workflow.

Therefore, for account compromise incidents, you typically need to **disable/lock the account or reset credentials**, revoke refresh tokens/API keys, rotate secrets if needed, expire sessions, remove remember-me tokens, and log an audit trail. Calling `expireNow()` alone does not constitute "instant global sign-out everywhere".

### 10.4. Cookie and Browser Safety

- Use **HTTPS** and `Secure` cookies in production; local HTTP demos do not represent production config.
- Use `HttpOnly` so regular scripts cannot read cookies; add `SameSite` compatible with form login/SSO flows.
- Verify Domain/Path and behavior behind reverse proxies; never log `Cookie`/`Set-Cookie` headers containing tokens.
- CSRF tokens for POST logout/revoke must come from the server; `permitAll()` does not bypass CSRF checks.
- Set bounded session timeouts and separate remember-me lifetimes; never issue infinite cookies.
- For sensitive endpoints, consider step-up authentication, `fullyAuthenticated()`, MFA, auditing, and owner notifications.

### 10.5. Revocation Auditing and Race Conditions

A mature revocation workflow should log **who**, **which target**, **timestamp**, **reason**, **count of sessions marked expired**, and **repository operation outcome**, without writing raw tokens or session IDs to general application logs.

If a request authenticated **before** time T and executes past T, marking expired at T may not abort the already-started operation. When business rules demand a hard cutoff for financial or high-privilege transactions, enforce account status / credential version checks directly inside the transaction/service authorization and design cancellation/rollback handling rather than relying solely on servlet session concurrency.

## 11. Practice Acceptance Checklist

- [ ] Form login uses encoded passwords; demo passwords are never used in production.
- [ ] Browsers A and B **do not share a cookie jar** and establish distinct sessions.
- [ ] `maximumSessions(1)` combined with `maxSessionsPreventsLogin(false)` matches requirements.
- [ ] `SessionRegistry` is shared consistently between the concurrency policy and revocation service.
- [ ] `HttpSessionEventPublisher` is registered in the appropriate servlet runtime.
- [ ] Old session is marked expired after a new login and handled on its **next request**.
- [ ] Remember-me issues a cookie only when requested at login and authentication succeeds.
- [ ] Session timeout is not confused with remember-me token expiry.
- [ ] Remember-me token repository uses durable server-side persistence when reliable revocation is required.
- [ ] POST logout includes CSRF, invalidates the session, and handles remember-me cleanup.
- [ ] Admin POST revoke includes CSRF and requires ROLE_ADMIN at both URL **and** service layers.
- [ ] Revocation expires active sessions **and** deletes persistent tokens, without fabricating deleted token counts if the API returns none.
- [ ] Response payloads never include raw cookies, tokens, passwords, or session IDs.
- [ ] Tests cover both positive and negative cases for authorization and CSRF to avoid false positives.
- [ ] Concurrency tests cover two distinct sessions; production includes integration tests with browsers or embedded servers.
- [ ] Multi-node deployments use a shared session registry/store, persistent token store, consistent keys, and end-to-end revocation tests.
- [ ] When "account lockout" is needed, explicit disable/credential revocation exists; session expiry is not mistaken for disabling passwords/JWTs.
- [ ] Monitoring, auditing, and expired token/session cleanup operate without leaking secrets.

## 12. Questions and Extension Exercises

**1.** Why doesn't clearing the remember-me cookie in one browser guarantee revocation across all devices?

**Answer:** Other browsers may still hold their own cookies. The server must delete the corresponding token records from the persistent repository or use an equivalent revocation mechanism.

**2.** Does `SessionInformation.expireNow()` immediately abort an in-flight HTTP request?

**Answer:** No. It marks the session expired; the filter checks it on the next request. An already-running request may finish if it already cleared authentication/authorization.

**3.** If Alice is revoked yet still knows her password, what happens?

**Answer:** Alice can sign in again unless her account was disabled/locked or her credentials were changed. Session/token revocation does not automatically lock the account.

**4.** Why must the session-limit policy and admin revocation share the same `SessionRegistry`?

**Answer:** If the two components inspect different registries, admin revocation will miss sessions tracked by the concurrency config. In a cluster, state must also be shared through an appropriate backing store.

**5.** How does `maxSessionsPreventsLogin(true)` differ from `false`?

**Answer:** `true` rejects new logins once the limit is reached; `false` allows the new login and marks the older session expired. Choose based on UX and threat model.

**6.** Why can an admin POST with `ROLE_ADMIN` still return 403?

**Answer:** The CSRF token may be missing or invalid. Include a valid token in role tests; keep the right role while omitting the token in CSRF tests.

**7.** Is `RememberMeAuthenticationToken` equivalent to freshly entered password authentication?

**Answer:** No. For sensitive operations, enforce `fullyAuthenticated()` or step-up authentication as needed.

**8.** When one node uses `SessionRegistryImpl`, do other nodes automatically know about Alice's session?

**Answer:** No. An in-memory registry is local to one JVM. Multi-node deployments need a distributed registry/store and synchronized testing.

**9.** If persistent remember-me series are deleted while an authenticated session remains active, has the user lost access?

**Answer:** Not yet. Deleting tokens does not clear SecurityContext from the active session. You must also expire/invalidate sessions and verify the right authorization policies.

**10.** What makes a revocation test stronger than just asserting HTTP 200?

**Answer:** Verify the session record is marked expired, the persistent series was deleted, the next request is blocked, the old browser cookie fails to re-authenticate, and unauthorized users cannot invoke the endpoint—and in multi-node setups, verify across different instances.

### Exercise A: "Keep the Old Device" Policy

Change `maxSessionsPreventsLogin(false)` to `true`. Verify profile A keeps working and profile B cannot create a new session while A is active. Describe how to handle the UX when login is denied without leaking another user's session ID or device details.

### Exercise B: Enforcing Fresh Strong Authentication

Add a `POST /account/change-password` endpoint protected by `fullyAuthenticated()` and CSRF. Compare responses when a user authenticated via form login versus returning automatically via remember-me; disallow changing passwords based solely on a long-lived cookie.

### Exercise C: Production Design

Outline migrating `InMemoryTokenRepositoryImpl` to `JdbcTokenRepositoryImpl`, moving sessions to a shared store, swapping the registry for a store-backed implementation, and adding auditing, account locking, and refresh-token revocation. Explain expected behavior for in-flight requests and eventual consistency across nodes.

---

**Conclusion:** Session concurrency, remember-me, and access revocation are **three related yet distinct problems**. `maximumSessions(1)` caps registry-tracked sessions; persistent remember-me manages separate long-lived credentials; reliable revocation requires marking sessions expired **and** deleting persistent token series. Logging out of one browser does not automatically block all devices; `expireNow()` does not abort in-flight requests; and an in-memory model serves only one JVM. Combine the right filters, registry, repository, method/URL authorization, CSRF, cookie security, tests, and operations to achieve the protection your product truly requires.