# Changing Passwords, Re-authentication, and Invalidating Related Sessions in Spring Security Servlet

**Scope:** Java 17+, Spring Security 6.x / Spring Boot 3.x on Jakarta Servlet. This lesson belongs to the **Passwords** group. The goal is to design a safe password-change flow; re-verify the user before sensitive actions; update the password hash properly; revoke authenticated sessions and related credentials; and test the results.

Scenario: an account is logged in on browsers A, B, and phone C. On A, the user changes their password. The old password can no longer be used for **new logins**, yet B and C can keep operating if the server only updates the hash in the database. Reason: each session may already hold a valid <code>Authentication</code> in <code>SecurityContext</code> and does not re-check the password on every request.

## 1. Three tasks that must be completed independently

1. **Re-authentication / step-up:** re-verify that the requester is the account owner or authorized to change credentials. For local passwords, this usually checks the current password; for SSO/IdP, use appropriate re-authentication/MFA.
2. **Updating the credential:** validate the new password, hash it with <code>PasswordEncoder</code>, persist durably and consistently without storing plaintext; also increment a credential version or record the change timestamp when revocation relies on it.
3. **Invalidating existing access:** invalidate the current session, mark/remove other sessions, revoke remember-me tokens, refresh tokens, or enforce policies on issued tokens if the application uses them.

Do not treat the following operations as equivalent:

| Operation | Effect | Does not automatically do |
| --- | --- | --- |
| <code>PasswordEncoder.encode(newPassword)</code> | Produces a new password hash | Does not destroy sessions or JWTs |
| Updating <code>password_hash</code> in the database | Changes credential for future authentications | Does not clear stored SecurityContexts |
| <code>SecurityContextHolder.clearContext()</code> | Clears authentication in the current context | Does not find and destroy sessions on other devices |
| <code>request.getSession(false).invalidate()</code> | Invalidates the single HttpSession of the current request | Does not iterate all sessions of the account |
| <code>SessionInformation.expireNow()</code> | Marks a SessionRegistry-tracked session as expired | Does not delete cookies on remote devices or sync across nodes |
| Deleting the <code>JSESSIONID</code> cookie in browser A | Browser A stops sending that cookie | Does not destroy the session on the server or in browser B |

**Security goal:** the user must log in again with the new credential after changing it; all old sessions within the revocation policy scope can no longer perform protected actions. "Session destruction" may take effect immediately in the session store or be caught on the **next request**; describe your architecture's semantics accurately.

## 2. Password change, forgot password, and admin reset are not the same flow

| Operation type | Proof of identity | Key rules |
| --- | --- | --- |
| Logged-in user self-service password change | Authenticated session **and** current password/step-up | Change only the password of the server-authenticated account |
| Forgot password (password reset) | Single-use recovery token, short TTL, bound to account and purpose | Does not require current password; token invalidated after use |
| Admin-assisted reset | Admin's own authentication and authorization, audit log | Never let clients supply arbitrary <code>userId</code> to bypass checks; consider forcing a new password |
| Changing password at Identity Provider | IdP re-authentication/MFA | If the app does not own hashes, do not manage local passwords itself |

Reset tokens must be stored hashed or equivalently protected, cryptographically random, single-use, and revoked upon expiration or use. Never email new passwords or permanent tokens. If SSO is supported, review revocation policies across the Identity Provider, the application, and any separate refresh tokens.

## 3. HTTP flow of a self-service password change

~~~text
Browser A                         Spring Security / application
  | POST /password/change                    |
  | Cookie: JSESSIONID=... + CSRF token      |
  | currentPassword, newPassword             |
  |----------------------------------------->|
  |                             CSRF validated
  |                             Authenticated?
  |                             Load account from server principal
  |                             matches(currentPassword, hash)?
  |                             Validate new password policy
  |                             Encode and update hash/version
  |                             Revoke old sessions/tokens
  |                             Logout + invalidate current session
  |<-----------------------------------------|
  | 200 + prompt to sign in again            |
  |                                          |
Browser B sends request with prior session
  |----------------------------------------->|
  |                             Session expired/revoked?
  |<-----------------------------------------|
  | Login redirect or rejection response     |
~~~

A logged-in session is not strong enough proof for **every** sensitive action: it could be hijacked or a request could be CSRF. Verify the current password (or recent IdP step-up), enable CSRF for cookie/session apps, and require HTTPS.

Password data must travel only in the request body over a secure channel. Never put it in query strings, HTTP logs, analytics, unprotected message queues, or email. Do not leak overly detailed failure reasons to unauthorized callers; keep server-side audit logs following data-protection rules.

**Re-authentication differs from regular authentication:** having an active session authorizes starting the flow, while checking the current password or MFA re-proves the user before modifying credentials. Never accept self-asserted flags like <code>confirmed=true</code> from the browser.

## 4. Password hashing and change policy

Spring Security uses <code>PasswordEncoder</code>:

~~~java
// Logic snippet inside a service, not a standalone program.
if (!passwordEncoder.matches(currentPassword, currentHash)) {
    throw new IllegalArgumentException("Current password not accepted");
}
if (passwordEncoder.matches(newPassword, currentHash)) {
    throw new IllegalArgumentException("Choose a different password");
}
String newHash = passwordEncoder.encode(newPassword);
repository.updatePasswordHash(accountId, newHash);
~~~

Key points:
- <code>matches(raw, encoded)</code> verifies a raw password against a hash without decrypting it. Proper password hashing is one-way.
- Password hashes should use password-dedicated algorithms such as BCrypt/Argon2/PBKDF2 with tuned cost settings; never use plain SHA-256 to store passwords.
- <code>PasswordEncoderFactories.createDelegatingPasswordEncoder()</code> stores algorithm tags like <code>{bcrypt}</code>; never strip prefixes when saving to the database.
- Because hashes are salted, two <code>encode</code> calls on the same password can differ; never compare old and new hashes to test if passwords match.
- Policies can include length, passphrases, breached/guessable password checks, password history, and password-manager support; the demo uses only minimum length to stay focused on sessions.
- Never rely solely on client-side validation; the server must validate. Rate limiting failed current-password attempts, anomaly detection, and safe notifications are standard production needs.

**Concurrency and transactions:** two nearly simultaneous password-change requests can both match the old hash and overwrite each other sequentially. Production should use database transactions, row locks, or optimistic versioning, emitting revocation events/state only after the credential commit succeeds. If session revocation fails after the hash already changed, have a reliable retry strategy or reject sessions via credential versioning.

## 5. Session lifecycle and Servlet limitations

The <code>JSESSIONID</code> session cookie usually carries only a session ID; <code>HttpSession</code> and <code>SecurityContext</code> are server-managed. Distinguish:

- <code>logout</code> on the current request normally invokes <code>SecurityContextLogoutHandler</code>, clearing the SecurityContext and invalidating the current HttpSession by default.
- <code>SessionRegistry</code> can list sessions per principal if sessions are properly registered. <code>SessionInformation.expireNow()</code> marks them expired; <code>ConcurrentSessionFilter</code> checks on the next request.
- <code>HttpSessionEventPublisher</code> forwards container session-lifecycle events so the registry stays up to date.
- A <code>SessionRegistryImpl</code> holds data **within one JVM only** and does not automatically revoke sessions on other replicas, unregistered sessions, or stateless JWTs.

Excerpt example:

~~~java
for (SessionInformation info
        : sessionRegistry.getAllSessions(authentication.getPrincipal(), false)) {
    info.expireNow();
}
// Then logout/invalidate the current session.
~~~

The snippet only works when proper session concurrency/tracking is configured. Spring Security does not provide a "by default" global logout-everywhere system across every authentication type.

If you want to keep the current session active, design a dedicated flow proving that session received strong step-up verification and rotate the session ID as needed; **never** assume session A is safer than all others merely because the action ran from machine A. The example below chooses to **log out everything, including the machine changing the password**.

## 6. Complete single-JVM runnable example: form login + SessionRegistry

The demo uses **Java 17+, Maven, Spring Boot 3.3.5, Spring Security 6.x**. Passwords live in <code>InMemoryUserDetailsManager</code> to run standalone. Form login creates sessions; concurrency support registers them; on password change, the server marks all user sessions expired and invalidates the current session. When another session sends its next request, it is redirected to login.

**Intentional limitations:** this is a single-process learning example, not a production solution with databases/Redis, SSO, or JWTs. Sample passwords are for localhost runs only.

Project structure:

~~~text
password-sessions-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/passwordsessions/
    │   ├── PasswordSessionsApplication.java
    │   ├── SecurityConfiguration.java
    │   └── PasswordController.java
    └── test/java/com/example/passwordsessions/
        └── PasswordChangeTest.java
~~~

### 6.1. Maven

File <code>pom.xml</code>:

~~~xml
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
    <artifactId>password-sessions-demo</artifactId>
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

### 6.2. Entry point and session-check endpoint

Create <code>src/main/java/com/example/passwordsessions/PasswordSessionsApplication.java</code>:

~~~java
package com.example.passwordsessions;

import java.security.Principal;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class PasswordSessionsApplication {

    public static void main(String[] args) {
        SpringApplication.run(PasswordSessionsApplication.class, args);
    }

    @GetMapping("/me")
    public String me(Principal principal) {
        return principal.getName();
    }
}
~~~

<code>/me</code> returns only the current username without exposing session IDs, password hashes, or sensitive data. Anonymous requests to this endpoint must be redirected to login.

### 6.3. Authentication and session-tracking configuration

Create <code>src/main/java/com/example/passwordsessions/SecurityConfiguration.java</code>:

~~~java
package com.example.passwordsessions;

import org.springframework.boot.web.servlet.ServletListenerRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.core.session.SessionRegistry;
import org.springframework.security.core.session.SessionRegistryImpl;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.session.HttpSessionEventPublisher;

@Configuration
public class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    InMemoryUserDetailsManager demoUsers(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("Old-password-1234"))
            .roles("USER")
            .build();
        return new InMemoryUserDetailsManager(alice);
    }

    @Bean
    SessionRegistry sessionRegistry() {
        return new SessionRegistryImpl();
    }

    @Bean
    ServletListenerRegistrationBean<HttpSessionEventPublisher> sessionEvents() {
        return new ServletListenerRegistrationBean<>(
            new HttpSessionEventPublisher());
    }

    @Bean
    SecurityFilterChain appSecurity(HttpSecurity http,
                                    SessionRegistry registry) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/error").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .sessionManagement(sessions -> sessions
                .maximumSessions(5)
                    .expiredUrl("/login?expired")
                    .sessionRegistry(registry))
            .build();
    }
}
~~~

How the configuration works:
- <code>InMemoryUserDetailsManager</code> provides both <code>UserDetailsService</code> at login and <code>updateUser(...)</code> for the password-change demo.
- <code>maximumSessions(5)</code> enables concurrent session tracking and registers sessions with <code>SessionRegistry</code>. The cap of 5 simply helps simulate multiple sessions; it does not mean password change generally finds at most 5 sessions.
- <code>expiredUrl("/login?expired")</code> specifies that sessions marked expired are redirected to login on their next request. Expired status does not mean cookies on other devices vanish instantly.
- <code>HttpSessionEventPublisher</code> lets the registry receive session destruction events.
- CSRF stays enabled by default for POSTs. Default form login handles <code>POST /login</code>, requiring authentication for <code>/me</code> and <code>/password/change</code>.
- Session fixation protection is handled by Spring Security on login; if replacing authentication strategies or custom filters, verify this protection remains active.

### 6.4. Controller re-checking password and revoking sessions

Create <code>src/main/java/com/example/passwordsessions/PasswordController.java</code>:

~~~java
package com.example.passwordsessions;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.session.SessionInformation;
import org.springframework.security.core.session.SessionRegistry;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.authentication.logout.SecurityContextLogoutHandler;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PasswordController {

    private final InMemoryUserDetailsManager users;
    private final PasswordEncoder encoder;
    private final SessionRegistry sessions;
    private final SecurityContextLogoutHandler logout =
        new SecurityContextLogoutHandler();

    public PasswordController(InMemoryUserDetailsManager users,
                              PasswordEncoder encoder,
                              SessionRegistry sessions) {
        this.users = users;
        this.encoder = encoder;
        this.sessions = sessions;
    }

    @PostMapping("/password/change")
    public ResponseEntity<String> change(
            @RequestParam String currentPassword,
            @RequestParam String newPassword,
            Authentication authentication,
            HttpServletRequest request,
            HttpServletResponse response) {

        // Obtain identity from the server's authentication.
        UserDetails stored = users.loadUserByUsername(authentication.getName());

        // Current session does not substitute for re-authentication.
        if (!encoder.matches(currentPassword, stored.getPassword())) {
            return ResponseEntity.status(HttpStatus.FORBIDDEN)
                .body("Current password was not accepted");
        }

        // Minimum policy for demo, insufficient for production.
        if (newPassword.length() < 12
                || encoder.matches(newPassword, stored.getPassword())) {
            return ResponseEntity.badRequest()
                .body("Choose a different password with 12+ characters");
        }

        UserDetails updated = User.withUserDetails(stored)
            .password(encoder.encode(newPassword))
            .build();
        users.updateUser(updated);

        // Sessions tracked by the registry for the same principal.
        for (SessionInformation info
                : sessions.getAllSessions(authentication.getPrincipal(), false)) {
            info.expireNow();
        }

        // Current session is invalidated and SecurityContext is cleared.
        logout.logout(request, response, authentication);
        return ResponseEntity.ok("Password changed; sign in again");
    }
}
~~~

Design decisions here:
- The endpoint does not accept a target username from the client. It strictly uses <code>authentication.getName()</code> determined by Spring Security to prevent cross-account changes.
- <code>encoder.matches</code> verifies the current password; new-password rules are validated **before writing**.
- <code>User.withUserDetails(stored)</code> copies the demo user's status/authorities, swapping only the new hash; <code>users.updateUser</code> updates the in-memory store.
- <code>getAllSessions(principal, false)</code> fetches non-expired sessions in the registry; <code>expireNow()</code> marks all of them, including the current session if tracked.
- <code>SecurityContextLogoutHandler.logout</code> immediately invalidates the current request's HttpSession and clears the context. Other sessions are rejected on their next request by <code>ConcurrentSessionFilter</code>.
- Because this uses an in-memory store/registry, there are no cross-node transactions and no JWT/remember-me token revocation. This is a **single-JVM learning model**, not a promise of production global logout.

## 7. Testing two login sessions and credential change with MockMvc

Add <code>src/test/java/com/example/passwordsessions/PasswordChangeTest.java</code>:

~~~java
package com.example.passwordsessions;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.security.core.session.SessionInformation;
import org.springframework.security.core.session.SessionRegistry;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.result.SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.security.test.web.servlet.result.SecurityMockMvcResultMatchers.unauthenticated;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class PasswordChangeTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    SessionRegistry sessions;

    private MockHttpSession login(String password) throws Exception {
        MvcResult result = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "alice")
                .param("password", password))
            .andExpect(authenticated().withUsername("alice"))
            .andReturn();
        MockHttpSession session =
            (MockHttpSession) result.getRequest().getSession(false);
        assertThat(session).isNotNull();
        return session;
    }

    @Test
    void changeRequiresReauthenticationAndRevokesBothSessions()
            throws Exception {
        MockHttpSession browserA = login("Old-password-1234");
        MockHttpSession browserB = login("Old-password-1234");

        mvc.perform(get("/me").session(browserA))
            .andExpect(status().isOk())
            .andExpect(content().string("alice"));
        mvc.perform(get("/me").session(browserB))
            .andExpect(status().isOk())
            .andExpect(content().string("alice"));

        // Missing CSRF: password change request is blocked.
        mvc.perform(post("/password/change")
                .session(browserA)
                .param("currentPassword", "Old-password-1234")
                .param("newPassword", "New-password-5678"))
            .andExpect(status().isForbidden());

        // Wrong current password: credential must not be changed.
        mvc.perform(post("/password/change")
                .session(browserA).with(csrf())
                .param("currentPassword", "incorrect")
                .param("newPassword", "New-password-5678"))
            .andExpect(status().isForbidden());

        // Successful change: requires valid current password and CSRF.
        mvc.perform(post("/password/change")
                .session(browserA).with(csrf())
                .param("currentPassword", "Old-password-1234")
                .param("newPassword", "New-password-5678"))
            .andExpect(status().isOk())
            .andExpect(content().string("Password changed; sign in again"));

        assertThat(browserA.isInvalid()).isTrue();

        SessionInformation other =
            sessions.getSessionInformation(browserB.getId());
        assertThat(other).isNotNull();
        assertThat(other.isExpired()).isTrue();

        // Next request using session B is redirected to login.
        mvc.perform(get("/me").session(browserB))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?expired"));

        // Old password no longer authenticates a new login.
        mvc.perform(post("/login").with(csrf())
                .param("username", "alice")
                .param("password", "Old-password-1234"))
            .andExpect(unauthenticated());

        // New credential creates a valid new session.
        MockHttpSession newSession = login("New-password-5678");
        mvc.perform(get("/me").session(newSession))
            .andExpect(status().isOk())
            .andExpect(content().string("alice"));
    }
}
~~~

This is **an integration test exercising configuration, authentication filters, session registry, and controller**. It enforces key invariants:
- Without CSRF or with a wrong current password, the credential is not changed.
- Two independent logins create two HttpSessions for the same principal.
- After password change, the current session is invalidated; the other session is marked expired and redirected on its next call.
- The old password can no longer log in; the new password works.

Run with JDK 17+ and Maven in the <code>password-sessions-demo</code> directory:

~~~bash
mvn test
mvn spring-boot:run
~~~

<code>mvn test</code> runs automated tests; it does **not** prove immediate revocation across Redis/clusters since the demo uses a single JVM. There is no fixed stdout here: Maven/Tomcat logs vary by environment. The important result is whether the test suite passes or clearly identifies any failed assertion.

If testing manually in a browser, open <code>/login</code> and sign in as <code>alice / Old-password-1234</code>, then submit the password-change endpoint using a form carrying the Spring Security-provided CSRF token. Sending a bare <code>POST /password/change</code> via curl without a CSRF token **is expected to return 403**. This is intentional protection; never disable CSRF app-wide just for testing convenience.

## 8. Session and token types to audit beyond HttpSession

| State type | What to handle on password change |
| --- | --- |
| Current HttpSession | Logout, clear SecurityContext, invalidate session |
| HttpSessions on other browsers/devices | List/delete or mark expired in the shared session store |
| Persistent-token remember-me cookies | Revoke series/token in persistent token repository; clear cookie properly |
| Hash-based remember-me | Changing the password may invalidate old cookies if the implementation uses the password hash; still verify the actual mechanism |
| Refresh tokens | Revoke user refresh tokens/grants, preventing new access tokens |
| Self-contained JWT access tokens | Changing password cannot delete JWTs from clients; require short expiry, token versioning, blacklists, or introspection/verification sources |
| OAuth2/OIDC sessions at IdP | Review IdP logout/revocation/back-channel logout capabilities and app contract |
| WebSockets/long-lived connections | May need to close connections or re-verify permissions on sensitive messages |
| Sessions on other nodes | Need a shared session store or cross-node revocation mechanism |

**Do not conflate concepts:** <code>JSESSIONID</code> is a Servlet session identifier, whereas JWT access tokens, refresh tokens, and remember-me cookies have separate lifecycles. Spring Security does not automatically revoke all of them simply because a controller calls <code>invalidate()</code> on one HttpSession.

### Common stateless JWT case

Suppose a JWT was issued when the account had <code>credentialVersion=4</code>. On password change, the server increments the version to 5. If each request verifies the token signature/issuer/audience/expiry and **checks the token's version against the current account version** (from a trusted source), version 4 tokens can be rejected.

This requires dedicated system design: JWTs do not inherently carry a version field and Spring Security does not check a database version automatically. Reading versions from a cache also needs consistency/TTL policies aligned with revocation requirements; never trust a version claim while skipping signature or issuer verification. For tokens validated strictly offline without server lookups, old tokens can remain valid until expiration.

## 9. Multiple servers: SessionRegistryImpl is insufficient for logout everywhere

Suppose the same application runs behind a load balancer:

~~~text
Browser A -> App node A -> node A's SessionRegistryImpl
Browser B -> App node B -> node B's SessionRegistryImpl
Browser C -> App node C -> node C's SessionRegistryImpl
                    |
             Shared account database
~~~

When changing the password on node A:
- The database receives the new hash.
- A's registry marks the sessions it knows about.
- B/C's registries **do not automatically know** that A marked sessions expired.
- Old sessions can stay alive on B/C until a shared store or re-check mechanism intervenes.

Common production design patterns (often combined):
1. **Shared session store**, e.g., Spring Session + Redis/JDBC with a properly configured principal index. After a successful change, look up the account's sessions and delete/mark them in the central store, respecting repository/index semantics and deletion permissions.
2. **Account credential/security version:** store <code>version</code> when creating `Authentication`; re-check before protected requests and reject/invalidate sessions if versions diverge. Account for lookup cost and freshness.
3. **Reliable revocation events:** after committing the password, publish events to nodes to clear caches/sessions with retries, idempotency, and error monitoring. Events serve as an accelerator if high certainty is required; still verify against a shared source.
4. **Short token lifetimes + refresh token revocation:** for stateless access tokens, bound the window old tokens stay alive and design revocation suited to the risk level.

**Illustrative, non-standalone snippet** using a Spring Session repository with a principal index:

~~~java
// Spring Session / repository / principal index must be configured first.
var sessions = indexedSessionRepository.findByPrincipalName(username);
for (String sessionId : sessions.keySet()) {
    indexedSessionRepository.deleteById(sessionId);
}
~~~

Here <code>indexedSessionRepository</code> must be a properly configured <code>FindByIndexNameSessionRepository</code> and <code>username</code> must come from the server, not arbitrary client input. Delete only when the principal index is complete; test all session types, race conditions, failure handling, and separating the current session. **This is not a drop-in API replacement for the `SessionRegistryImpl` demo.**

### When strong revocation policies are needed

A durable pattern stores <code>credentialsChangedAt</code> or <code>credentialVersion</code> in the database and saves the matching version in Authentication/session at login. Every request or sensitive request group compares against the current version; sessions carrying an older version are rejected. This handles even sessions missing from a registry, provided requests pass through the designed filter/check. Test this mechanism across multiple nodes, caches, and resource authorization.

## 10. Transactions, race conditions, and error recovery

The "update hash -> revoke sessions" sequence has failure windows:

| Failure point | Consequence | Real-system handling |
| --- | --- | --- |
| Current password incorrect | Caller must not change hash | Reject, rate limit, and audit safely |
| Two concurrent change requests | Later writer may overwrite newer password | Transactions, optimistic versioning / row locks |
| Hash update succeeds, session revoke fails | Old sessions may stay valid | Enforced credential version, retry/outbox, monitoring |
| Sessions revoked first yet hash update fails | User gets logged out even though credential did not change | Order actions around transaction boundaries |
| Another session created mid-revoke | New session may slip between steps | Sync version/cutoff in a trusted source |
| A node loses message bus connectivity | That node's cache/session misses password change | Cross-check state against shared store on incoming requests |
| Remember-me/refresh tokens missed | Secondary credentials keep minting new sessions | Revoke tokens in the same workflow; test explicitly |

A database transaction cannot atomically roll back Redis session deletions or IdP token revocations without specialized architecture. Use transactional outboxes, durable revocation state, and idempotent retries. Design explicit guarantees and responses when a step fails: never report "logged out all devices" unless actually verified.

## 11. CSRF, XSS, cookies, and browser configuration

With form login and session cookies, browsers attach cookies automatically to matching requests; attackers may try forging state-changing requests via the victim's browser. Therefore:
- Enable and test CSRF on <code>POST /password/change</code>.
- Accept passwords only in the request body over HTTPS; never in GET URLs.
- Production session cookies should use <code>Secure</code>, <code>HttpOnly</code>, and an appropriate `SameSite` policy for real flows, plus reasonable timeouts.
- `HttpOnly` reduces JavaScript cookie access yet **does not** stop XSS from issuing requests; prevent XSS.
- After credential changes, you can clear browser session cookies using a response with matching Path/Domain, yet **server-side** invalidation remains central. Clearing one browser's cookie cannot guarantee sessions on other browsers are destroyed.
- If a frontend calls cross-origin APIs, configure CORS and <code>credentials</code> explicitly; never use CORS as a substitute for authentication/authorization.

Never echo current or new passwords back into HTML/logs; never email new passwords. You may send a "password changed" notification with timestamp and a suspicious-activity reporting link, without including secrets.

## 12. Checking UX and security behavior after password change

A sound user flow:
1. The settings page asks for current password and new password; for MFA-enabled accounts, re-authentication may be required per policy.
2. The request uses HTTPS and a CSRF token. The server identifies the account from authentication, verifies against a trusted source, then updates the hash.
3. The server revokes sessions/tokens per the "sign out all devices" policy. The response leaks no sensitive details.
4. The UI clears stale state and navigates the user to login; never rely on frontend actions to conclude server sessions expired.
5. The user signs in again with the new credential. Any device still holding an old session is prompted to authenticate on its next API call.
6. The system audits the event by account ID, timestamp, action type, and outcome; never log current/new passwords or tokens.

**Note on status codes:** with form login, expired sessions may 302 redirect to login; APIs may return 401 or 403 depending on entry point/configuration. Do not assert every app returns the same status. In the demo, <code>expiredUrl</code> is set explicitly to test the redirect.

## 13. Common mistakes

| Mistake | Outcome | How to fix |
| --- | --- | --- |
| Only changing the hash in the DB | Logged-in sessions still keep old authentication | Revoke sessions/tokens or check credential version |
| Logging out only the current tab | Other devices remain unaffected | Principal-indexed session store and multi-node policy |
| Calling <code>expireNow()</code> without tracking/filter | Sessions unregistered or never checked for expiration | Enable concurrency management, listener, and test next request |
| Using `SessionRegistryImpl` across multiple nodes | Each node only knows its own sessions | Spring Session/shared store or version guard |
| Not requiring current password/step-up | Hijacked sessions can change credentials | Appropriate re-authentication |
| Disabling CSRF so POST works | Cookie-based browser apps face CSRF risk | Keep CSRF and send valid tokens |
| Calling BCrypt encode and comparing hashes to check password equality | Fails comparison due to salt | Use <code>matches</code> |
| Accepting <code>username</code> from form to select account | Risk of changing someone else's password | Get account ID from server principal |
| Forgetting refresh/remember-me tokens | Logged-out users still regain access via secondary tokens | Inventory all credential types and revoke |
| Believing JWTs auto-expire on password change | Old JWTs still carry valid signatures and unexpired claims | Token versioning, revoke/introspection, or tight TTL |
| Sending success before revocation is ensured | Misrepresents actual security state | Transactions + retries/monitoring + accurate messages |
| Testing only one session | Misses that other sessions still work | Test two browsers and multi-node setups |
| Storing plaintext or logging passwords | Credential leakage | PasswordEncoder, TLS, never log sensitive data |

## 14. Production deployment checklist

1. Identify all authentication mechanisms: form login, HTTP Basic, OAuth2/OIDC, remember-me, JWT, refresh tokens; list every state requiring revocation.
2. Design re-authentication/step-up proportional to risk. SSO accounts must go through the IdP's flow when changing passwords at the IdP.
3. Identify the account from the trusted principal, never arbitrary client-supplied `userId`; process POSTs only after CSRF validation.
4. Verify current password with <code>PasswordEncoder.matches</code>, enforce new-password policy, block reuse as needed, and handle errors safely.
5. Update hash and credential version under transactions/locks or optimistic concurrency.
6. Invalidate the current session and all other sessions via principal index or version guard. Across multiple nodes, ensure shared state.
7. Revoke remember-me/refresh tokens; clearly define handling for issued JWT/access tokens, caches, and WebSocket connections.
8. Test happy and failure paths: wrong current password, missing CSRF, two sessions, login with old/new password, cross-node sessions, concurrent changes, and revocation service failures.
9. Notify password-change events via secure channels, keep audits free of secrets, and provide an anomaly-reporting workflow.
10. Verify that once "logged out everywhere" is reported, every access path using old credentials is blocked at the designed assurance level.

## 15. Knowledge self-check

**Q1:** After updating the password hash, is logged-in browser B automatically logged out?  
**Answer:** No. Authentication in HttpSession or tokens may still be valid; handle session/token revocation separately.

**Q2:** Does <code>SessionInformation.expireNow()</code> immediately delete browser B's cookie and HttpSession?  
**Answer:** No. It marks the session in the registry; when browser B sends its next request, the filter detects and handles the expired session. Browser cookies are not deleted immediately.

**Q3:** Why check the current password if the user already has a session?  
**Answer:** Changing credentials is a sensitive operation; the current session could be hijacked. Re-authentication/step-up adds another defensive layer alongside CSRF and other controls.

**Q4:** Does `SessionRegistryImpl` on node A guarantee revoking sessions on node B in a cluster?  
**Answer:** No. An in-memory `RegistryImpl` only knows its own process's sessions; you need a shared store, version guard, or controlled eventing.

**Q5:** Does changing a password automatically expire JWTs?  
**Answer:** No. JWTs typically have independent lifecycles; design TTLs, revocation/introspection, or credential-version checks.

**Q6:** For forgot-password flows, should the current password be required?  
**Answer:** No. Recovery flows must use an alternative proof such as a single-use, short-TTL token with strong verification, then revoke that token.

**Remember:** a password change operation is only complete when you have **re-authenticated**, **updated the credential properly**, and **invalidated related sessions/tokens**. Spring Security supplies many building blocks, yet guaranteeing logout everywhere depends on session registration, multi-node architecture, and actual token policies.
