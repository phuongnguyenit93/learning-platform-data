# Cookie Theft Risks and Testing Expired, Tampered, or Replayed Tokens — Spring Security Servlet

## Objectives and Context

In a Spring Security application running on **Servlet / Spring MVC**, the **“Remember me”** feature lets users return to the app without re-entering their password every time they open the browser. To achieve this, the server can issue a **remember-me cookie** carrying authentication data verified on subsequent requests when no suitable current authentication is present.

Convenience comes with risk: **anyone possessing a valid cookie may be able to use it to be recognized as the user**, without knowing the password. If a cookie is copied to another device, leaked via logs, sent over an unprotected channel, or exposed by a browser compromise, it becomes a valuable credential.

This lesson focuses on three specific tests and their security implications:

1. **Expired tokens:** the browser stops sending a cookie due to `Max-Age/Expires`; if someone resends the old cookie string anyway, does the server reject it based on the token's lifetime?
2. **Tampered tokens:** the cookie payload is altered by even a single character; does the server verify the signature or match the token in a trusted store instead of trusting client-supplied contents?
3. **Replayed tokens:** an intact cookie value that was already accepted once is sent again; does the mechanism detect an old rotated token or simply keep accepting it until expiration?

Distinguish **remember-me cookies**, **session cookies**, and **access tokens**. Browsers may send them automatically together, yet each is issued and verified under a different contract. The examples below target **Spring Security Servlet 6.x / Spring Boot 3.x / Java 17+** and do not apply directly to Spring Security WebFlux or a JWT Resource Server.

**Remember:** a stolen token can be used successfully *before* any replay signal appears. Signatures, expiration, token rotation, and cookie flags each reduce risk in different ways; **none of them alone guarantees “account takeover can never happen”**.

## 1. Where Does Remember-me Fit in the Authentication Flow?

A form-login website can establish authentication through two paths:

```text
Browser POST /login (username + password + CSRF token)
    |
UsernamePasswordAuthenticationFilter -> AuthenticationManager
    |
Login succeeds and user selected "remember-me"
    |
RememberMeServices.loginSuccess(...)
    |
Server returns Set-Cookie: remember-me=...
    |
----------------- NEW REQUEST -----------------
    |
Browser sends cookies (and possibly session cookie)
    |
SecurityContextRepository loads authentication from session if present
    |
If SecurityContext still has no suitable user:
    |
RememberMeAuthenticationFilter -> RememberMeServices.autoLogin(...)
    |
Read cookie -> verify signature/token and expiration
    |
RememberMeAuthenticationToken / AuthenticationManager
    |
SecurityContextHolder <- Authentication
    |
AuthorizationFilter / Controller
```

This diagram illustrates the common case; exact filter order and context saving depend on configuration. If an HTTP session already holds a valid authentication, Spring Security usually does not need to use the remember-me cookie on that request. When testing remember-me, **deliberately send a new request with only the remember-me cookie and no logged-in HTTP session**, otherwise the result may come from session authentication rather than remember-me.

`RememberMeServices` handles the key actions:

- `loginSuccess(...)`: after successful interactive login, can issue a remember-me cookie if requested by the user and permitted by configuration.
- `autoLogin(...)`: reads the cookie on a later request and restores an authentication per policy.
- `loginFail(...)`: cleans up/clears cookies appropriately when the authentication flow fails.
- `logout(...)`: participates in clearing cookies and cleaning up server-side tokens depending on implementation.

`RememberMeAuthenticationFilter` delegates to this service when needed. It does not define the token algorithm itself. In Spring Security, the two implementations to distinguish are `TokenBasedRememberMeServices` and `PersistentTokenBasedRememberMeServices`.

## 2. Remember-me Cookie vs. HTTP Session Cookie

| Criterion | Session cookie, usually `JSESSIONID` | Remember-me cookie, usually `remember-me` |
|---|---|---|
| Purpose | Points to the active HTTP session on the server | Allows restoring authentication when no valid interactive session remains |
| Typical value carried | Session identifier | Signed token or `series/token` pair, depending on remember-me implementation |
| Scope | Tied to server-side session and cookie lifecycle | Can outlive the session if policy allows |
| Verification | Servlet session store / session management | `RememberMeServices` and signature/repository logic |
| Revocation | Invalidate/delete server-side session, logout config | Clear cookie and/or delete matching token record per implementation |
| If stolen | Someone else may try to hijack the session | Someone else may try to auto-login without the password |
| After password change | Does not automatically delete all sessions | Depends on remember-me type; token-based may depend on password hash, persistent needs explicit record deletion |

A cookie holding a session identifier is **not** the raw password. Yet a session cookie is also valuable as a credential while the session stays active. Protecting remember-me does not replace controls for session fixation, timeouts, logout, or active-session revocation.

**Do not confuse with CSRF:** a cookie attached automatically by the browser exposes the system to CSRF risk; remember-me is an authentication convenience, not a CSRF token. Cookie-backed websites must keep proper CSRF protection, especially on POST/PUT/PATCH/DELETE.

## 3. Two Remember-me Models in Spring Security

### 3.1. TokenBasedRememberMeServices: Self-Verifiable Cookie

`TokenBasedRememberMeServices` creates a remember-me token with an expiration and a **signature derived from a server key**, user info, and required authentication data. Exact formats have evolved across generations and algorithm versions; in modern Spring Security 6.x you may see fields such as username, expiration time, algorithm name, and signature inside a Base64-encoded string.

Idea:

```text
username + expiration timestamp + algorithm metadata + signature
                    |
             Base64 encode
                    |
               cookie value
                    |
New request: decode -> check expiration -> load user -> verify signature
```

**Base64 is not encryption.** Reading the cookie does not automatically reveal the password, yet its payload can contain username/expiration/metadata that must not be treated as secret. Security comes from the inability to forge a valid signature without the secret and associated inputs, not from Base64.

Key points to remember:

- **Modified cookie:** the signature becomes invalid; the server does not trust a client-altered username/expiration.
- **Expiration:** the server checks expiration; an old cookie is rejected even if a client forces sending it.
- **Replay before expiration:** the same valid token **can be used multiple times**, because this mechanism does not maintain a database list of single-use tokens. Signatures do not prevent replay on their own.
- **Revocation:** rotating the signing key or changing user inputs included in signing can invalidate a set of tokens, though impact varies by version. Do not treat this as complete per-device revocation.
- **Overhead:** avoids storing individual remember-me tokens in a separate DB table, though it still typically loads the user to verify details and status.

Token-based mode is usually easier to deploy, yet harder to selectively revoke for **a single device** without added state or switching to a persistent-token scheme.

### 3.2. PersistentTokenBasedRememberMeServices: Server-Side Series/Token

`PersistentTokenBasedRememberMeServices` generates a **series identifier** and a **random token**. The remember-me cookie typically carries an encoded `series:token` pair. The server keeps a record binding series, current token, username, and last-used timestamp in `PersistentTokenRepository`.

```text
At login:
  browser cookie: Base64(series-7 : token-A)
  server DB:      series-7 -> (alice, token-A, lastUsed)

Auto-login request with token-A:
  fetch series-7 record from DB
  compare presented token-A with stored token-A
  if matched: issue new token-B, save token-B in DB
  browser receives cookie: Base64(series-7 : token-B)

Someone resends old cookie Base64(series-7 : token-A):
  series-7 still exists yet stored token is token-B
  -> token mismatch -> indicator of theft/replay
  -> Spring Security persistent service can delete the user's
     persistent remember-me tokens and reject.
```

This is a **token rotation + replay/theft detection** strategy. It improves detection of copied cookies, yet does not guarantee an attacker cannot gain access on first use: if the holder of a stolen cookie sends a request first, that request can succeed and rotate the token. Only when the legitimate user presents the old copy does the system detect the anomaly.

**Do not overgeneralize:** detecting an old token and deleting persistent remember-me tokens **does not automatically terminate all existing HTTP sessions, refresh tokens, or JWTs**. If “log out all devices” is required, the app must apply matching revocation policies there too.

### 3.3. Cookie Verification Comparison

| Scenario | Signed token-based | Persistent series/token |
|---|---|---|
| Cookie payload modified | Invalid signature, rejected | Token/series mismatch or missing, rejected |
| Cookie expired | Server checks token expiration | Server checks token/record age per policy |
| Replay same cookie before expiry | Usually still accepted if token is valid | Once the token has rotated, the old copy can be detected |
| Server stores individual tokens | Usually no | Yes: `PersistentTokenRepository` |
| Revoke a single token/device | Requires additional mechanism | Can delete record by series with proper admin API/design |
| Risk if token DB leaks | Does not store a cookie token list this way | Store exposure creates risk; must protect token records and backups |
| Complexity | Less state, simpler | DB/store, rotation, concurrency, cleanup, incident response |
| Cookie-theft guarantee | Does not stop someone holding a valid cookie from using it | Can detect replay after rotation, cannot block first use |

**Concurrency note:** two closely spaced requests carrying the same persistent token cookie can race to rotate the token, especially before the updated cookie reaches the client. The second request can look like reuse of a rotated token. Production systems must therefore account for parallel browser requests, transactional updates, logging, suspected-theft UX, and false-positive mitigation. Never run only single-threaded two-request tests and assume no race remains.

## 4. How Cookies Get Stolen

Risk does not arise only from XSS; evaluate the entire credential path.

1. **XSS or malicious scripts:** can read cookies missing `HttpOnly`; even with `HttpOnly`, XSS can still issue requests from the logged-in browser or perform same-origin actions.
2. **Unprotected HTTP:** when cookies lack `Secure` or clients connect over HTTP, on-path attackers can intercept credentials. Production should enforce HTTPS, appropriate HSTS, and `Secure` cookies.
3. **Logs, traces, and proxies:** logging `Cookie` request headers, `Set-Cookie` response headers, or full HTTP captures can record raw bearer credentials.
4. **Compromised browsers, extensions, or devices:** an over-privileged extension, malware, or stolen browser profile can leak cookies regardless of cookie flags.
5. **Backups and support tools:** HAR exports, DevTools screenshots, support tickets, or crash dumps can inadvertently contain cookies.
6. **Wrong cookie domain/path:** overly broad scope exposes cookies to unnecessary subdomains or endpoints. A less-trusted subdomain widens the attack surface.
7. **Session fixation and cookie injection:** inconsistent cookie names/paths/domains can cause the system to misread duplicate same-named cookies or trust cookies set by another context.
8. **Excessive lifetime:** the more days a token stays valid, the wider the window for an attacker holding a stolen cookie.
9. **Not deleting persistent tokens:** UI logout while the server record remains accepted leaves stolen cookies valid.
10. **Accepting tokens after account lock or deletion:** if the server skips user status checks and fails to revoke cookies, account lockouts may not take real effect.

Never ask users to send their raw cookie for “debug support”. For investigations, use internal IDs, correlation codes, and controlled traces; avoid storing raw secrets, tokens, or signatures.

## 5. What Cookie Flags Help With—and What They Do Not

| Attribute | Effect | Limitations |
|---|---|---|
| `Secure` | Browser sends cookie only over qualifying HTTPS connections | Does not fix XSS, malicious extensions, or already-copied cookies |
| `HttpOnly` | Restricts normal client-side JavaScript from reading the cookie | XSS can still drive requests; does not stop CSRF or browser compromise |
| `SameSite=Lax/Strict/None` | Controls cookie sending in cross-site contexts | Does not replace CSRF tokens and must fit real OAuth/cross-site flows |
| `Path` | Restricts URL paths receiving the cookie | Not a strong authorization barrier; does not stop same-origin access |
| `Domain` | Restricts host/domain scope | Overly broad domains increase subdomain exposure |
| `Max-Age/Expires` | Limits how long the browser keeps the cookie | Server **must still check token expiry** if a client resends old data |

Design defensively in depth: HTTPS, reverse-proxy forwarded headers, HSTS, CSP/XSS prevention, CSRF protection, logout, and access control on session/token repositories. Do not simply turn on `HttpOnly` and declare “the cookie cannot be stolen”.

**Do not confuse lifetimes:** HTTP session duration, remember-me cookie expiration, and persistent repository token age can differ. If enforcing “remember for 14 days”, the server must apply matching expiry rules and clean up expired records; browser `Max-Age` alone is not enough.

## 6. Testing Expired Tokens: Browser Expiry vs. Server Expiry

A manual test often just waits for the cookie to disappear from the browser, then confirms the user must log in again. That check is useful, yet **does not prove the server rejects old tokens**, because the browser may simply have stopped sending it.

Stronger test:

1. Log in successfully with remember-me enabled and capture the cookie **in the test environment**.
2. Verify a fresh request carrying only the remember-me cookie before expiry: identity restores properly.
3. Retain the token string in test memory and wait past the server-configured lifetime.
4. Issue a new request **deliberately resending the old cookie**, simulating a non-compliant client ignoring `Max-Age`.
5. Assert the server does not restore authentication: private resources return 401 or redirect to login depending on the entry point.
6. Assert failure causes no HTTP 500, grants no access, and logs no secrets.

With some libraries, an injected or fake clock can avoid `Thread.sleep`. The MockMvc demo in Section 10 fixes the lifetime to **2 seconds** solely for fast execution and sleeps slightly past it. Production must never use such a tiny remember-me TTL, and long-duration tests should use controllable clocks where APIs support them.

**Timestamps inside a cookie are not an independent source of trust.** In token-based mode, expiration is covered by the signature. In persistent-token mode, the server relies on the timestamp stored in the repository/controlled TTL. If code merely reads a client-sent `expires=...` without integrity verification, attackers can extend expiration arbitrarily.

## 7. Testing Tampered Tokens: Verifying Integrity

Take a valid cookie, then **alter the token/signature portion while keeping the format valid**. For instance, a persistent cookie contains Base64-encoded `series:token`:

```text
Original, issued by server:
  Base64(series-123:token-ABC)

Tampered cookie (not the server-issued token):
  Base64(series-123:token-XYZ)
```

A proper test must ensure:

- Before tampering, the cookie genuinely succeeds at auto-login when sent without a session.
- After tampering, the private request **is not authenticated**.
- The service does not skip validation just because Base64 parsing succeeded; decoding is not verification.
- The response is a controlled rejection/redirect, not a crash from parsing or array errors.
- In persistent mode, changing the token on a valid series can be treated as a **theft/replay signal** and wipe all of the user's remember-me tokens per implementation. Tests should use isolated data because this has side effects.
- In token-based mode, altering the signature or expiration must fail signature verification; tests must match the running version's format rather than assuming an older version's sample layout works forever.

A test that merely sends a non-Base64 string and gets 401 **is insufficient to prove signature verification**: the server might simply reject a parse error. Include both a **valid-format mismatched-token** case and malformed/missing-field cases to verify robust handling.

## 8. Testing Replay: The Two Models Yield Different Outcomes

“Replay” means **resending a credential that was previously valid**, not modifying its contents. With a bearer credential, anyone holding the real token can use it without knowing the password; a hash alone cannot always distinguish legitimate reuse from a copied token.

### 8.1. Replay With Token-Based

While a signed token remains valid, unexpired, and unaffected by changes invalidating its signature, **resending the same remember-me cookie usually succeeds again**. This is the trade-off of stateless/token-based mechanisms. Signatures prevent **tampering**, not **replay**.

Treat a test showing “replaying twice succeeds both times” as evidence for policy selection, not as a signature bug. If per-device revocation or reuse detection is required, choose server-side state or another mechanism.

### 8.2. Replay With a Rotated Persistent Token

Steps:

```text
POST login -> cookie A = (series S, token T1), DB stores T1

GET private with cookie A:
  -> 200
  -> DB rotates T1 -> T2
  -> response Set-Cookie B = (series S, token T2)

GET private with cookie A again:
  -> presented T1, stored T2
  -> mismatch, suspected cookie theft/replay
  -> rejected, server removes persistent tokens for user

GET private with cookie B:
  -> may be rejected because records were deleted after replay
```

**Very important warning:** the first request using a stolen cookie **can succeed and receive cookie T2**. Rotation detects an incident when the old copy is reused later, yet **cannot tell the server who the rightful owner is**. If an attacker can keep reading the victim's newly issued cookies, token rotation alone does not solve the root problem.

Once replay is detected, a system needs response controls: secret-free audit logs, forcing re-login, revoking other token types per risk policy, notifying the user through an independent channel when appropriate, and monitoring across nodes/devices. Avoid rigid “only the old IP may use this cookie” rules, because roaming/mobile/NAT/proxies frequently change legitimate client IPs.

## 9. Distinguishing Remembered Authentication from Fully Authenticated

Spring Security can issue a `RememberMeAuthenticationToken` for users identified via remember-me cookies. This is normally **weaker** than a recent interactive login, because cookies can be copied and do not prove the user just entered credentials/MFA.

Different authorization rules can be applied:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/public").permitAll()
    .requestMatchers("/sensitive").fullyAuthenticated()
    .anyRequest().authenticated())
```

This is an `HttpSecurity` configuration fragment. For requests identified only via remember-me, `authenticated()` may suffice for ordinary pages while `fullyAuthenticated()` requires authentication that is neither anonymous nor remember-me; the app can then prompt for interactive login instead of allowing sensitive operations.

**Do not confuse `fullyAuthenticated` with full MFA authentication.** This condition distinguishes remember-me/anonymous from interactive authentication in Spring Security; MFA or elevated assurance requires dedicated policies and flows.

An internal news page might allow remember-me, whereas changing email, changing password, viewing secrets, making payments, or granting admin roles should require re-authentication/step-up based on risk.

## 10. Spring Boot Servlet Demo Testing Expiry, Tampering, and Replay

The example below uses **Spring Boot 3.3.5 (Spring Security 6 managed by Boot), Java 17, and Maven** as a stable learning baseline, **without claiming it is the newest or currently supported version**. For real products, choose supported versions and verify corresponding APIs.

The demo deliberately uses `InMemoryTokenRepositoryImpl` to verify the **persistent remember-me** algorithm. It is not durable across restarts and **must not be used in production/clusters**. Production should use a reliable persistent implementation such as JDBC with a proper schema, backups/retention/access control, and multi-node support.

**Other limitations:** the hardcoded demo key is strictly a test fixture. Production must load secrets from a secret manager/secure config with sufficient entropy and a rotation policy. Sample accounts/passwords must never be exposed on the internet.

### 10.1. Structure

```text
remember-me-security-demo/
├── pom.xml
└── src/
    ├── main/java/example/rememberme/
    │   ├── RememberMeApplication.java
    │   ├── SecurityConfiguration.java
    │   └── DemoController.java
    └── test/java/example/rememberme/
        └── RememberMeSecurityTest.java
```

### 10.2. pom.xml

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
    <groupId>example</groupId>
    <artifactId>remember-me-security-demo</artifactId>
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
```

### 10.3. Entry Point

Create `src/main/java/example/rememberme/RememberMeApplication.java`:

```java
package example.rememberme;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RememberMeApplication {
    public static void main(String[] args) {
        SpringApplication.run(RememberMeApplication.class, args);
    }
}
```

### 10.4. SecurityConfiguration

Create `src/main/java/example/rememberme/SecurityConfiguration.java`:

```java
package example.rememberme;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.rememberme.InMemoryTokenRepositoryImpl;
import org.springframework.security.web.authentication.rememberme.PersistentTokenRepository;

@Configuration
public class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("demo-only-password"))
                .roles("USER")
                .build()
        );
    }

    @Bean
    PersistentTokenRepository tokenRepository() {
        return new InMemoryTokenRepositoryImpl();
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            PersistentTokenRepository tokenRepository) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public", "/error").permitAll()
                .requestMatchers("/sensitive").fullyAuthenticated()
                .anyRequest().authenticated())
            .formLogin(form -> form
                .defaultSuccessUrl("/private", true)
                .permitAll())
            .rememberMe(remember -> remember
                .key("demo-only-long-fixed-key-not-for-production")
                .tokenRepository(tokenRepository)
                .tokenValiditySeconds(2))
            .build();
    }
}
```

This configures **persistent remember-me** because a `PersistentTokenRepository` is provided. Without a token repository, default configuration can choose token-based remember-me depending on how Spring Security is configured; verify the active mode through the chain and cookies.

In the demo, token validity is only **2 seconds** to test expiry. In real deployments, choose a lifetime based on risk analysis and user needs; never copy this 2-second value. Form login authentication still uses a normal HTTP session; the remember-me cookie is an opt-in via form parameter `remember-me=on`.

**Security additions needed in production:** HTTPS, proper Secure/HttpOnly/SameSite cookies, secret management, shared token repository, restricting sensitive flows to `fullyAuthenticated`, account lock/disable checks, and logout/revocation.

### 10.5. Controller

Create `src/main/java/example/rememberme/DemoController.java`:

```java
package example.rememberme;

import java.security.Principal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public")
    public String publicPage() {
        return "PUBLIC_OK";
    }

    @GetMapping("/private")
    public String privatePage(Principal principal) {
        return "Hello, " + principal.getName();
    }

    @GetMapping("/sensitive")
    public String sensitive(Principal principal) {
        return "SENSITIVE: " + principal.getName();
    }
}
```

`/private` requires only `authenticated`. `/sensitive` requires `fullyAuthenticated()`, so a user holding only a remember-me cookie is prompted for interactive login.

### 10.6. JUnit + MockMvc Tests

Create `src/test/java/example/rememberme/RememberMeSecurityTest.java`:

```java
package example.rememberme;

import java.nio.charset.StandardCharsets;
import java.util.Base64;
import jakarta.servlet.http.Cookie;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrlPattern;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class RememberMeSecurityTest {

    @Autowired
    MockMvc mvc;

    private Cookie loginAndGetRememberMeCookie() throws Exception {
        MvcResult login = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "alice")
                .param("password", "demo-only-password")
                .param("remember-me", "on"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/private"))
            .andReturn();

        Cookie cookie = login.getResponse().getCookie("remember-me");
        assertThat(cookie).isNotNull();
        assertThat(cookie.getValue()).isNotBlank();
        return cookie;
    }

    private Cookie tamperPersistentToken(Cookie cookie) {
        String decoded = new String(
            Base64.getDecoder().decode(cookie.getValue()),
            StandardCharsets.UTF_8
        );
        String[] fields = decoded.split(":", -1);
        assertThat(fields).hasSize(2);

        String oldToken = fields[1];
        assertThat(oldToken).isNotEmpty();
        String alteredToken = (oldToken.startsWith("A") ? "B" : "A")
            + oldToken.substring(1);

        String forgedPayload = fields[0] + ":" + alteredToken;
        String forgedValue = Base64.getEncoder().encodeToString(
            forgedPayload.getBytes(StandardCharsets.UTF_8)
        );
        return new Cookie("remember-me", forgedValue);
    }

    @Test
    void publicRequestDoesNotNeedLogin() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("PUBLIC_OK"));
    }

    @Test
    void withoutRememberMeCookiePrivateRequiresLogin() throws Exception {
        mvc.perform(get("/private"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrlPattern("**/login"));
    }

    @Test
    void rememberMeIsOptInForTheForm() throws Exception {
        MvcResult login = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "alice")
                .param("password", "demo-only-password"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        assertThat(login.getResponse().getCookie("remember-me")).isNull();
    }

    @Test
    void validCookieRestoresAuthenticationWithoutAnOldHttpSession()
            throws Exception {
        Cookie cookie = loginAndGetRememberMeCookie();

        mvc.perform(get("/private").cookie(cookie))
            .andExpect(status().isOk())
            .andExpect(content().string("Hello, alice"));
    }

    @Test
    void expiredCookieIsRejectedByServerEvenIfClientResendsIt()
            throws Exception {
        Cookie cookie = loginAndGetRememberMeCookie();

        // Demo TTL is 2 seconds; intentionally resend old cookie after expiration.
        Thread.sleep(2800L);

        mvc.perform(get("/private").cookie(cookie))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrlPattern("**/login"));
    }

    @Test
    void modifiedTokenWithValidBase64FormatIsRejected()
            throws Exception {
        Cookie cookie = loginAndGetRememberMeCookie();
        Cookie modified = tamperPersistentToken(cookie);

        mvc.perform(get("/private").cookie(modified))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrlPattern("**/login"));
    }

    @Test
    void replayOfOldTokenAfterRotationIsDetected() throws Exception {
        Cookie original = loginAndGetRememberMeCookie();

        MvcResult firstAutoLogin = mvc.perform(
                get("/private").cookie(original))
            .andExpect(status().isOk())
            .andExpect(content().string("Hello, alice"))
            .andReturn();

        Cookie rotated = firstAutoLogin.getResponse().getCookie("remember-me");
        assertThat(rotated).isNotNull();
        assertThat(rotated.getValue()).isNotEqualTo(original.getValue());

        // Resend token T1 after the repository has replaced it with T2.
        mvc.perform(get("/private").cookie(original))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrlPattern("**/login"));

        // Persistent-token service deleted the user's tokens on suspected theft.
        mvc.perform(get("/private").cookie(rotated))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrlPattern("**/login"));
    }

    @Test
    void rememberMeDoesNotSatisfyFullyAuthenticated()
            throws Exception {
        Cookie cookie = loginAndGetRememberMeCookie();

        mvc.perform(get("/sensitive").cookie(cookie))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrlPattern("**/login"));
    }
}
```

**Explanation of how the tests isolate the real mechanism:**

- Requests like `get("/private").cookie(cookie)` intentionally **omit `.session(...)`**. Results therefore do not rely on the HTTP session created during login POST, testing `RememberMeAuthenticationFilter` and persistent cookies directly.
- The expiry test **deliberately injects an already-expired cookie into the request**; a real browser might drop it, yet the server must still reject it.
- The tamper test alters **the token while keeping valid Base64 and series**, going beyond testing a malformed string. The persistent repository detects the token differs from the stored value.
- The replay test runs a first accepted auto-login that **rotates the token**, then tries resending the old cookie. That is the core scenario persistent-token design can detect.
- After replay, Spring Security's persistent service deletes the user's remember-me records; the final assertion confirms the rotated cookie is no longer sufficient to restore authentication in the demo. This does not guarantee all other HTTP sessions or bearer tokens on the server were canceled.
- The `fullyAuthenticated()` test proves remember-me does not qualify for sensitive endpoints, showing why not every endpoint should let remember-me cookies restore access automatically.

**Expected result:** 8 JUnit tests pass when code, dependencies, and versions match the description. In an environment with concurrent requests, rotation/replay can hit races; sequential MockMvc tests **do not replace** concurrency or real-browser tests. The example was not executed on a live machine while authoring this document.

### 10.7. Running the Application and Testing via Browser

From the `remember-me-security-demo` directory, with JDK 17+ and Maven able to resolve dependencies:

```bash
java -version
mvn -version
mvn test
mvn spring-boot:run
```

Once the server is listening on default port 8080, open `http://localhost:8080/login` on your **development machine** and use demo account `alice / demo-only-password`. Tick remember-me on the form (if the login page displays that option) and observe the issued cookie.

**Never deploy an app with sample keys/passwords or in-memory token storage onto a public network.** In production use HTTPS and properly configured cookie flags; HTTP here is strictly for local learning.

During manual testing, never copy real cookie values into chat, issue trackers, or screenshots. Use DevTools on a controlled machine to inspect cookie names, `Secure`/`HttpOnly`/`SameSite` flags, `Path`, and `Max-Age`—never share secret values.

## 11. Testing Token-Based Remember-me Without a Persistent Repository

Section 10 uses persistent tokens to demonstrate replay detection. If an application uses `TokenBasedRememberMeServices` (without storing each token in a DB), expectations differ:

- **Expiration:** even with a valid signature, a cookie whose expiration has passed must be rejected.
- **Tampering:** altering username, expiration, algorithm, or signature and re-Base64-encoding fails signature verification; the server must reject it.
- **Replay before expiry:** the same valid cookie can be accepted multiple times, because the server keeps no record that “this token was already used”. Tests must reflect this characteristic rather than asserting 401 on every replay when the design has no state.
- **Key rotation:** can invalidate many browser-stored tokens; requires a rollout and user-support plan.
- **Password hash changes:** token-based verification can be affected by the `UserDetails` password value used in signing depending on version; test this explicitly. Never assume changing a password also invalidates every `HttpSession` or persistent cookie.

An anti-replay test for token-based mode can **demonstrate its limitation** rather than proving the server rejects reuse. If the product requires detecting stolen-cookie reuse, adopt a stateful design with rotation per requirements; do not invent custom nonces/counters inside cookies without analyzing concurrency and revocation.

## 12. Logout, Account Lockout, and Revoking Remember-me Cookies

When a user clicks logout, at least two state locations may exist:

1. **HTTP session** holding `SecurityContext`.
2. **Remember-me cookie and persistent token store** capable of restoring authentication once the session is gone.

If logout only invalidates the session while leaving the remember-me token valid, a new request can auto-login again via the cookie. In standard flows, ensure `RememberMeServices` participates in logout to clear cookies and clean up persistent records per implementation. For “log out all devices”, design a mechanism deleting all user series or an equivalent invalidation marker; **clearing a cookie on the current device does not delete its copy on another device**.

For locked/disabled accounts or detected risk:

- Block new logins at the provider/checker.
- Revoke persistent remember-me tokens by user/series and render token-based cookies ineligible when required.
- Review all active HTTP sessions, not just remember-me.
- Revoke refresh tokens, external remember-me/SSO sessions, or other credentials per policy.
- Ensure in-flight requests and cached roles/authorities cannot continue permitting unauthorized sensitive actions.
- Audit and notify incidents per security policy without sending tokens/raw cookies in emails.

With persistent remember-me, deleting records by user stops those cookies from working on the next auto-login attempt. However, a request that already loaded Authentication prior to deletion **does not automatically abort**; sensitive actions require revalidation and authorization at business boundaries.

## 13. Common Real-World Issues

| Symptom | What to distinguish | Investigation path |
|---|---|---|
| User session expired yet still auto-logs in | Remember-me cookie is still valid | May be working as intended; verify policy and `fullyAuthenticated` on sensitive actions |
| Deleted cookie in browser yet another machine stays logged in | Only current cookie cleared; copied token/server record remains | Apply server-side revocation where needed |
| Cookie was tampered yet request still returns 200 | Request may still carry a valid **HTTP session** | Retest sending only the remember-me cookie, without session |
| Cookie expired yet request still permitted | Another session exists, clock skew, browser-only expiry, or missing server check | Test resending old cookie without session and inspect server validation |
| Token-based cookie replayed multiple times before expiry | Stateless signed tokens allow reuse | Do not treat signatures as single-use tokens; change design if replay detection is needed |
| Old persistent token reused and user forced to re-login across all devices | Theft detection wiped user's tokens | Investigate cookie theft vs. concurrent requests, audit, guide re-login |
| Multiple simultaneous tabs trigger false cookie-theft errors | Two requests sent same token before rotated cookie reached client | Check race/transaction/update/token-rotation policies |
| Remember-me still works after password change | Persistent tokens not revoked or different logout flow | Delete records, review password-change policy |
| New page remains authenticated after logout | Remember-me cookie or session not cleared properly | Check logout handler, `Set-Cookie`, store, and subsequent requests |
| Test with `@WithMockUser` passes despite broken cookie | Mock user bypasses remember-me authentication | Use real MockMvc requests with cookie and no session |
| Cookie has `HttpOnly` yet is still abused | XSS can issue requests; compromised device/extension | CSP, XSS prevention, CSRF, endpoint re-auth, session policy |
| Production logs tokens in HTTP access logs | `Cookie`/`Set-Cookie` logging not redacted | Redact secrets at reverse proxy/APM and audit log retention |

Another common bug is **a server having two mismatched remember-me configs** across `SecurityFilterChain`s or instances: inconsistent signing keys, algorithms, cookie names, or repositories. Users then experience intermittent login failures. Align configuration in the right chain, and never wire an entire cluster to an in-memory session registry thinking you achieved global revocation.

## 14. Operational Testing Beyond MockMvc

The unit/integration tests in Section 10 verify contracts yet do not cover every boundary:

1. **Real browsers:** verify `Secure`, `HttpOnly`, `SameSite`, `Domain`, `Path`, browser retention duration, HTTP→HTTPS redirects, and HSTS.
2. **Multiple devices:** two separate browser profiles/cookie jars; logging out one device vs. choosing “log out all” must match policy.
3. **Concurrent tabs:** fire two parallel requests with the same persistent token to assess false-positive theft detection.
4. **Multiple nodes:** log in on A, auto-login on B, revoke on C; token repo must be shared and consistent.
5. **Clocks and TTL:** test exact expiration boundaries, clock skew, and record cleanup; prefer controllable clocks in advanced suites.
6. **Network errors/retries:** when the server rotates a token yet the `Set-Cookie` response fails to reach the browser, the next request may resend the old token. Review handling of missing acknowledgments.
7. **Password change, account lockout, privilege downgrade:** verify active sessions and remember-me tokens both obey policy.
8. **CSRF/XSS:** dangerous actions must not rely solely on cookies; test CSRF tokens, output encoding, and CSP.
9. **Observability/audit:** log expiry, malformed tokens, and suspected replay at appropriate levels without raw credentials/cookies.
10. **Cleanup:** purge expired records so the token table does not grow unboundedly, preserving consistency during background cleanup.

Never try to “catch every replay” by locking out users on any change of IP/User-Agent. Those signals can aid investigation, yet are unreliable identity proofs; legitimate users switch Wi-Fi/cellular and sit behind NATs constantly.

## 15. Secure Remember-me Design and Release Checklist

- [ ] Clearly chose `TokenBasedRememberMeServices` vs. `PersistentTokenBasedRememberMeServices` and understood replay/revocation trade-offs.
- [ ] Remember-me is **opt-in** per product policy; do not auto-remember every login without justification.
- [ ] Lifetime is enforced **server-side**, not solely via browser `Max-Age`.
- [ ] Cookies use HTTPS + `Secure`, `HttpOnly`, `SameSite`, scoped `Path`/`Domain`; never leaked in URLs/logs/HARs.
- [ ] Secret signing key has high entropy, proper protection, and rotation policy; no hardcoded production secrets.
- [ ] Persistent token store has access controls, protected backups/retention, proper indexes/transactions, and cluster support.
- [ ] Tampered or expired tokens fail authentication **when resent without a session**, without causing HTTP 500.
- [ ] Replay of rotated tokens is handled per policy; races and suspected-theft responses are tested.
- [ ] Replay detection is not conflated with preventing the **first use** of a stolen cookie.
- [ ] Sensitive endpoints require `fullyAuthenticated()` or MFA/re-authentication, not just `authenticated()` when remember-me is weaker.
- [ ] CSRF protection remains enforced for browser cookies; `SameSite` is not treated as a total replacement.
- [ ] Logout and “log out all devices” revoke remember-me token records along with HTTP sessions and other credentials as required.
- [ ] User lockout, password change, and privilege downgrade are tested against remembered cookies and pre-existing sessions.
- [ ] Tests cover opt-out, successful auto-login, expired, malformed, tampered, replayed, rotated tokens, and insufficient `fullyAuthenticated`.
- [ ] Behavior verified on real browsers/containers, multi-tab, multi-node, clock skew, and network failures.
- [ ] No sample keys/passwords/tokens from exercises are used on systems with real data.

### Self-Check Questions

**1.** The browser automatically deletes expired remember-me cookies; is that enough to prove the server checks expiry?  
**Answer:** No. You must deliberately resend an old expired token in a sessionless request and verify the server rejects it.

**2.** Does Base64 protect cookie contents against tampering?  
**Answer:** No. Base64 only encodes bytes into text; tamper resistance must rely on a signature or trusted server-side token comparison.

**3.** Will a validly signed token-based remember-me cookie automatically reject a second use?  
**Answer:** Normally no. A signature proves integrity, not single-use semantics.

**4.** A persistent token rotated from T1 to T2, and T1 is sent again. What does that mean?  
**Answer:** It may indicate cookie theft/replay or a race between concurrent requests; the implementation may wipe the user's tokens and require re-login.

**5.** If an attacker uses a stolen cookie **before** the legitimate user, does rotation stop the attacker?  
**Answer:** No. The first use can succeed; rotation detects later reuse of the old copy, without knowing which party is the rightful owner.

**6.** Why does `HttpOnly` not solve all XSS risks?  
**Answer:** It stops normal scripts from reading the cookie, yet scripts executing in a compromised origin can still issue requests in the browser's context.

**7.** Why require `fullyAuthenticated()` on password-change URLs or sensitive actions?  
**Answer:** Remember-me is weaker evidence than interactive login. Sensitive endpoints require re-authentication/step-up per policy rather than a copyable cookie.

**8.** Does deleting persistent remember-me records automatically log out all active HTTP sessions?  
**Answer:** No. Sessions, remember-me tokens, and other credentials need separate revocation policies; in-flight requests also have independent lifecycles.

**Conclusion:** A remember-me cookie is a **time-bounded bearer credential**. Expiry enforcement requires server logic; tamper checks require signatures or a trusted token store; replay detection requires state/rotation and still cannot block first use of a stolen cookie. Only by combining HTTPS, cookie flags, CSRF/XSS defenses, `fullyAuthenticated`/step-up, server-side revocation, and **sessionless** request testing can you accurately assess the security of remember-me.