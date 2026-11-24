# Password Change, Password Reset, and Which Sessions Must Be Revoked

In Spring Security, **changing a password** (*change password*) and **resetting a password** (*reset password*) are not the same workflow. Both may end by creating a new password hash, yet they differ in **identity verification proof**, **authorization**, and **the lifecycle of previously issued login sessions**.

**Often-overlooked security gap:** saving a new hash in the database **does not automatically revoke** previously issued HTTP sessions, remember-me cookies, refresh tokens, or JWT access tokens. An attacker holding a stolen session cookie can keep acting as authenticated even after the victim changes their password unless the application implements proper revocation.

This lesson targets **Spring Boot 3, Spring Security 6.x, Java 17+ (Servlet/MVC)** and cleanly separates three tasks:

1. Changing a password while logged in: re-authenticate based on risk level, verify the current password or an equivalent factor, create a new hash, and apply a session revocation policy.
2. Forgot password: request a reset via a trusted recovery channel, receive a high-entropy, single-use, expiring secret token, then set a new password **without auto-logging in**.
3. Revoking old access credentials: distinguish server-side sessions, remember-me, refresh tokens, self-contained access tokens, client cookies, OAuth2/SSO, and recovery tokens.

Examples include standalone Java 17 and a sample Spring Security app. Demo data/infrastructure in the Spring Boot set is **in-memory** for easy observation, **not** a production password-reset system. Production requires database transactions, rate limiting, MFA/step-up, CSRF, email/outbox, auditing, multi-node design, and clear revocation policies.

## 1. Change Password, Reset Password, and Logout-All Differ

| Operation | Proof | When Does the Hash Change? | Existing Sessions |
| --- | --- | --- | --- |
| Change password | Authenticated user with recent re-auth/current password or equivalent factor | After verifying actor, policy, and credentials | Needs clear policy: revoke all, or keep current session after re-auth/rotating session ID |
| Reset request | Only email/username to send a challenge | **Unchanged** | Never auto-revoke merely because someone submitted a request |
| Reset confirm | Valid, unexpired, unused reset token matching account and purpose | After consuming token **atomically** | Usually revoke old sessions, refresh tokens, and remaining recovery links |
| Single-session logout | Current session/token | No password change needed | One session only, unless a logout-all policy applies |
| Logout all devices | Verified action with appropriate authority | No password change required | Must cause old sessions/tokens to be rejected by the server |
| Compromised account recovery | Strong independent proof; review MFA/recovery bindings | Usually requires changing password and related secrets | Needs broader revocation scope and inspection of attacker-modified authenticators/recovery channels |

Anyone can know an email address. Therefore `POST /reset/request` does not prove the caller owns the account; never lock the account automatically, revoke all of the victim's sessions, or return a reset token in the HTTP response simply because that email exists.

## 2. Why Changing the Password Hash Is Not Enough to Log Out

Suppose Alice currently has:

```text
Account alice
  passwordHash = hash(oldPassword)

Browser A: JSESSIONID=A, Alice's Authentication saved
Browser B: JSESSIONID=B, Alice's Authentication saved
Mobile C: refreshToken=R3
API D: JWT accessToken=T4, 12 minutes left on exp
Reset link P5: unused

Alice changes password:
  passwordHash = hash(newPassword)

Credentials A, B, R3, T4, P5 do not disappear automatically.
```

On initial login, a `UsernamePasswordAuthenticationToken` carrying the raw password passes through `AuthenticationManager` and `DaoAuthenticationProvider`. Spring Security then saves an authenticated `Authentication` into `SecurityContext` under the session mechanism. Subsequent HTTP requests rely on the session/cookie rather than running `PasswordEncoder.matches` against a raw password on every call.

Consequences:

- Updating the hash causes **new login attempts** with the old password to fail.
- Previously established sessions still hold an `Authentication` and remain valid until invalidated, expired, or revoked.
- Living refresh tokens can keep minting new access tokens unless revoked at the authorization server.
- Signed JWT access tokens do not self-invalidate when a DB password changes.
- Previously issued recovery links can still reset the password unless invalidated.
- Deleting the cookie in the current browser does not erase a cookie copy stolen by an attacker if the server session remains alive.

**True definition of “session revocation”:** the server/authorization service must **reject old credentials when presented**. Client UI/cookie cleanup is supplementary, never a substitute for server-side invalidation or state checks.

## 3. Changing Password While Logged In

### 3.1. Recommended Flow

```text
POST /account/change-password
  |
  +-- Spring Security authentication & authorization
  +-- CSRF check (for browser cookies/sessions)
  |
  v
Server reads principal ID from trusted Authentication
  |
  +-- Re-verify current password or appropriate step-up factor
  +-- Rate limit current-password attempts
  +-- Check account status, MFA/risk policy
  +-- Validate new password (length, breached-password rules...)
  |
  v
Transaction:
  - PasswordEncoder.encode(newPassword)
  - Update password_hash
  - Increment credentialVersion/authVersion
  - Invalidate pending reset challenges
  - Persist audit/outbox event
  |
  v
Revoke sessions/token families per policy
  |
  +-- Display outcome without leaking secrets
  +-- Notify user via verified channel
  +-- Redirect to login if current session was revoked
```

Never trust a `userId` sent in the request body for whose password to change. If the controller receives `Authentication authentication`, take the internal ID from the trusted principal—never let clients pick Alice or Bob via an arbitrary `userId`. Admin password-change support for other users must be a separate flow with strict authorization, auditing, and avoiding setting an “admin-known password” unnecessarily.

### 3.2. Why Re-Verify When Already Logged In?

A browser holding a valid session does not guarantee the person at the keyboard is the account owner. Cookies can be stolen, a machine may be left unlocked, or a session may be long-lived. Password, MFA, and recovery email changes are sensitive operations that normally warrant **recent authentication** or **step-up**.

For accounts with local passwords, the service can verify:

```java
boolean valid =
    passwordEncoder.matches(
        submittedCurrentPassword, storedPasswordHash
    );
```

This snippet uses Spring Security's `PasswordEncoder`. Never compare raw passwords against hashes with `equals`, and never run `encoder.encode(raw).equals(stored)` because salts change on each encode.

If a user authenticates via passkey, OIDC, or MFA without a local password, a current password is not valid proof across all accounts. Use a re-authentication method matched to the login method and assurance level rather than demanding a nonexistent password from every account.

### 3.3. Password Policy, Hashing, and Updates

After verifying the actor and current credentials:

- Validate the new password against length/policy rules and breached-password lists; handle Unicode and encoder length limits per version.
- Call `PasswordEncoder.encode(newPassword)` (e.g., BCrypt/Argon2id/PBKDF2 per policy) and **store only the hash**.
- Never log old/new passwords, hashes, reset tokens, or `Authorization` headers.
- Update the password hash and **revocation epoch** (`authVersion`, `credentialVersion`, `validAfter`) consistently.
- If two change-password requests arrive concurrently, use optimistic locking/CAS/row locks rather than letting a slower request overwrite the newer password.
- Invalidate outstanding old reset tokens/recovery links.
- Record minimal audit metadata and notify post-commit per policy.

Never let “change password” escalate into granting `ROLE_ADMIN` or skipping owner/tenant authorization. Authentication and authorization remain separate layers.

### 3.4. Keep or Revoke the Current Session When Changing Password?

Two valid policies exist depending on the threat model:

**A. Revoke all sessions, including the current one.** Simple to reason about: upon password change, the user logs in again, and all prior sessions/tokens lose access. When account compromise is suspected, this is usually the safer choice.

**B. Keep the current session after re-auth while revoking all other sessions.** Requires updating the session version on the current session, rotating the session ID when policy dictates against session fixation, and ensuring strong assurance on that session. If you increment `authVersion` without updating the active session's stamped version, that current session itself will be rejected on the very next request.

In the sample app below, we choose **A**: the current session is logged out immediately, and other sessions are rejected via `authVersion` on their next request.

## 4. Requesting a Password Reset When the Old Password Is Forgotten

### 4.1. Reset Request Is Not Login

Users who forgot their password have no current password to supply. They must prove control of the account through an appropriate recovery channel. Request pattern:

```text
POST /reset/request
username or email
  |
  +-- Rate limit requests (IP/account/device/risk)
  +-- Do not disclose account existence via response/timing
  +-- If account exists: generate random reset challenge
  +-- Store token verifier + purpose + expiry
  +-- Send link via verified email/side channel
  |
  v
202 Accepted: "If a matching account exists,
               instructions will be sent"
```

Never return “this email does not exist” in one branch and “code sent” in the other. **Generic response text alone is insufficient if timing differences leak account existence**; production needs sensible timing-enumeration mitigations paired with rate limiting and abuse monitoring rather than naive fixed sleeps that invite DoS.

Never use a client-supplied `Host` header to build the reset link domain; use a preconfigured canonical origin/domain, HTTPS, and proper redirect/referrer policies.

### 4.2. What Properties Must a Reset Token Have?

A strong reset token requires:

- Generated by a **CSPRNG**, such as `SecureRandom`, with high entropy, e.g., 32 bytes (~256 bits).
- URL-safe encoding such as Base64url; encoding **adds no entropy**, it only formats the token for links.
- Scoped strictly to **password reset**, never accepted as a general access token.
- Bound to account ID, purpose, issued timestamp, and expiration; short-lived per threat model, e.g., 15 minutes.
- **Single-use**, with consumption executed **atomically** alongside the password update.
- Revocable when the password changes or the user requests a newer reset link.
- Never stored raw in application logs or analytics; prefer storing a digest/verifier server-side.
- Never returned in public HTTP responses; delivered only through an appropriate side channel.
- Rate limited to prevent email flooding, guessing, and abuse.

Java 17 token-generation snippet:

```java
byte[] randomBytes = new byte[32];
new SecureRandom().nextBytes(randomBytes);

String rawToken = Base64.getUrlEncoder()
    .withoutPadding()
    .encodeToString(randomBytes);
```

This token is a secret; never log `rawToken`. For a 256-bit random token, storing a SHA-256 digest of the token to look up the verifier in the database is viable because attackers cannot brute-force a 256-bit high-entropy space. This **does not apply** to human-chosen passwords: storing single-pass `SHA256(password)` is inadequate because human passwords are guessable and require a slow password KDF.

### 4.3. When the Reset Link Is Opened

The client submits the token and new password; the server checks:

1. Does the verifier/token hash exist for the right purpose and account?
2. Is the token unexpired and neither consumed nor revoked?
3. Is the account valid and does recovery policy permit the action?
4. Does the new password meet policy and any required step-up checks?
5. Can the server **consume once** and update hash/version within one transaction?
6. Are any remaining reset links invalidated, and are sessions/tokens scheduled for revocation?
7. Is the user notified via a trusted channel on success?

Do not auto-log the user in after reset. OWASP recommends sending the user back through the normal login flow after resetting, because minting a session directly from a reset link increases risk and complexity.

### 4.4. Atomic Consume: Preventing Double Use of a Token

If code simply does:

```text
if token.used == false:
   update password
   token.used = true
```

two concurrent requests can both observe `used=false` and both succeed. You need a transaction, row lock/CAS, or conditional update so **only one request** consumes the token.

Illustrative SQL pattern:

```sql
UPDATE password_reset_tokens
SET consumed_at = CURRENT_TIMESTAMP
WHERE token_digest = ?
  AND purpose = 'PASSWORD_RESET'
  AND consumed_at IS NULL
  AND expires_at > CURRENT_TIMESTAMP;
```

Only when **affected rows = 1** do you proceed to update the hash/version **in the same transaction**. If the password update fails, roll back token consumption as well. When multiple reset links could be active simultaneously, invalidate all other links for that account upon one successful reset.

### 4.5. Should a Reset Request Auto-Log Out the Victim?

No. An attacker can flood reset requests for any email without owning the account; auto-revoking on `/reset/request` creates a denial-of-service vector. **Revoke sessions after verified reset confirmation**, never on an unauthenticated reset request.

## 5. Which Sessions Must Be Revoked: Not Just JSESSIONID

| Credential Type | How It Works | Revocation Mechanism |
| --- | --- | --- |
| Servlet `HttpSession` | Server holds SecurityContext, browser carries `JSESSIONID` | Invalidate server session, delete from session repository, or check `authVersion` |
| Remember-me cookie/token | Can mint a new Authentication after session expiry | Clear current cookie and revoke persistent tokens in store |
| Refresh token | Requests new access tokens, often long-lived | Revoke token/family at authorization server; consider rotation/reuse detection |
| Self-contained JWT access token | Verifies signature, issuer, audience, and `exp` | `jti` denylist, user/token version, `validAfter`, or accept remaining TTL |
| Opaque access token | Server-side introspection/state store | Revoke at auth server; mind introspection caching |
| OAuth2/OIDC SSO session | IdP/authorization server and RP hold separate state | Provider-specific logout/revocation; may require end-session/backchannel coordination |
| Reset token/recovery challenge | Single-purpose task token | Consume and revoke all active challenges per user/purpose |
| Long-lived API key | Separate device/integration secret | Rotate/revoke key ID per policy; do not blindly tie to password |
| Device/MFA/recovery factor | Authenticator bindings | Revoke compromised factors; re-verify recovery methods |

**Changing a hash does not revoke a JWT.** A signed JWT access token keeps passing signature and expiration checks even after the user's password changes. If you only revoke refresh tokens while the resource server lacks runtime access-token revocation, existing access tokens stay usable until `exp`.

### 5.1. When Account Compromise Is Suspected

A compromise requires broader remediation:

- Invalidate **all** active HTTP sessions and refresh token families.
- Revoke remember-me tokens and active reset links/recovery codes.
- Assess active access tokens, denylist/version checks, and remaining TTL.
- Review connected OAuth apps, API keys, trusted devices, passkeys, and MFA factors.
- Inspect recently changed recovery emails/phones; never trust a channel newly added by an attacker.
- Audit suspicious activity and safeguard accessed data.
- Notify the user via a trusted channel and guide clean re-authentication.
- Never promise “instant global logout everywhere” if the architecture leaves tokens valid for minutes without revocation checks.

## 6. Logout in Spring Security: One Session vs. All Sessions

Spring Security Servlet includes built-in logout. With CSRF enabled, `POST /logout` is handled by `LogoutFilter`: `SecurityContextLogoutHandler` invalidates the `HttpSession` and clears the authentication/context, while additional logout handlers can clean up remember-me, CSRF, and events as configured.

Configuration snippet:

```java
@Bean
SecurityFilterChain chain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth.anyRequest().authenticated())
        .formLogin(Customizer.withDefaults())
        .logout(Customizer.withDefaults())
        .build();
}
```

This snippet requires a project, imports, and user authentication config; it does not compile standalone via `javac`. Logging out from browser A does not automatically find or cancel sessions B/C on other devices.

In a custom change-password controller, a handler can invalidate the **current** session:

```java
SecurityContextLogoutHandler handler =
    new SecurityContextLogoutHandler();

handler.logout(request, response, authentication);
```

This snippet runs inside a servlet HTTP request. It handles only that request's context/session; for remember-me, CSRF logout cleanup, and auditing, review the full Spring Security logout chain or attach the appropriate handlers. **Deleting only the client cookie** while leaving the server session alive does not stop an attacker holding a copy of that cookie.

### 6.1. SessionRegistry / ConcurrentSessionFilter

Spring Security provides `SessionRegistry` when configured to track concurrent sessions. A pattern for marking registered sessions expired:

```java
for (SessionInformation session :
        registry.getAllSessions(principal, false)) {
    session.expireNow();
}
```

This snippet requires the registry to be wired into the security flow and is not standalone runnable code. **`expireNow()` marks sessions as expired**; `ConcurrentSessionFilter` handles/invalidates them when a subsequent request arrives, and does not guarantee immediate deletion from storage at the moment of the call. `SessionRegistryImpl` typically lives in a single JVM's memory and does not coordinate across nodes automatically. With custom principals, implement consistent `equals`/`hashCode` so the registry matches the user reliably.

### 6.2. Spring Session with a Shared Session Repository

In apps using Spring Session with Redis/JDBC, if principal indexing is properly configured, you can look up session IDs by principal and delete them from the shared store:

```java
Map<String, ? extends Session> owned =
    repository.findByPrincipalName(principalName);

for (String sessionId : owned.keySet()) {
    repository.deleteById(sessionId);
}
```

This is a Spring Session snippet requiring `FindByIndexNameSessionRepository` and matching imports/dependencies. Never assume principal indexing is enabled without verifying; key lookups by immutable user ID/tenant scope to avoid username collisions. Caching and replication can introduce revocation latency that must be measured.

### 6.3. authVersion / sessionVersion

Another architecture stamps a **version** when a session is created and compares it against the authoritative version on the account:

```text
Account alice: authVersion = 5
Session A: authVersionAtLogin = 5
Session B: authVersionAtLogin = 5

Change/reset password (committed):
  passwordHash = newHash
  authVersion = 6

Request with Session A: 5 != 6 => reject/invalidate session
Request with Session B: 5 != 6 => reject/invalidate session
New login: authVersionAtLogin = 6 => allowed
```

This works across multiple nodes as long as **every node reads the same authoritative source** and enforces the check at the right filter/request boundary. In stateless JWT apps, the resource server can check a `tokenVersion` claim or denylist, weighing DB/cache cost and failure behavior.

**Spring Security does not automatically check `authVersion` just because you added a field to an entity.** You must implement storing, stamping, checking, and testing the version yourself.

### 6.4. Race Between Revocation and In-Flight Requests

A request that passed the version filter **just before** a password reset committed may still be executing sensitive work. For operations like money transfers, MFA changes, or data deletion, recheck version or recent authentication at the service/transaction boundary rather than assuming a request-entry filter stops all concurrency races.

## 7. CSRF and Session Fixation

Password changes, reset confirmations, and logouts are typically `POST` requests. With cookie-based sessions, browsers attach cookies automatically on matching-scope requests, which attackers can exploit via forged cross-site requests. Spring Security enables CSRF protection by default for state-changing HTTP methods.

**`permitAll()` does not mean disabling CSRF.** A public reset form still needs a CSRF token when submitted from a browser. With MockMvc, include `.with(csrf())` so requests pass the CSRF filter; otherwise a `403` may come from missing CSRF rather than missing roles.

If keeping the current session after changing password, consider rotating the session ID / renewing credentials to guard against session fixation. If invalidating the current session and requiring re-login, the framework typically applies session fixation protection on the next login; still verify actual config and cookie flags (`Secure`, `HttpOnly`, `SameSite` as suited to your app).

## 8. Practical Database and Transaction Design

Example schema (illustrative, not a runnable migration):

```sql
accounts (
    id BIGINT PRIMARY KEY,
    tenant_id BIGINT,
    normalized_login VARCHAR(255),
    password_hash VARCHAR(255) NOT NULL,
    auth_version BIGINT NOT NULL,
    password_changed_at TIMESTAMP NOT NULL,
    enabled BOOLEAN NOT NULL
);

password_reset_tokens (
    id BIGINT PRIMARY KEY,
    account_id BIGINT NOT NULL,
    token_digest VARCHAR(64) UNIQUE NOT NULL,
    purpose VARCHAR(50) NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    consumed_at TIMESTAMP NULL
);

refresh_token_families (
    id BIGINT PRIMARY KEY,
    account_id BIGINT NOT NULL,
    revoked_at TIMESTAMP NULL
);
```

Production needs foreign keys/indexes, tenant-scoped uniqueness, atomic updates with concurrency control, UTC timestamps, retention/cleanup, and proper key/secret management.

### 8.1. Change-Password Transaction

- Load the account and verify the expected credential version.
- Verify the current password or completed step-up per flow.
- Compute the new hash via `PasswordEncoder.encode`.
- Update `password_hash`, increment `auth_version`, and update the timestamp.
- Delete/revoke old reset tokens in the same transaction if in the same DB.
- Persist an outbox event for external session/token revocation, notifications, and auditing.
- Commit before calling downstream email/HTTP services, or use a transactional outbox for retries.

If the event bus or downstream call fails, the updated authoritative `authVersion` still ensures old sessions are rejected on arrival. If a server relies solely on an async job deleting sessions and that job fails, old sessions linger—monitor, retry, and fail closed.

### 8.2. Reset-Password Transaction

- Reject expired or already-used reset tokens before modifying hashes.
- Consume the token exactly once using a lock or CAS.
- Atomically update the hash and `authVersion`.
- Invalidate remaining reset tokens for the same user.
- Emit an audit/outbox event.
- Post-commit, notify the user and revoke token families/session stores per policy.

Changing a password **does not automatically change MFA or recovery methods**. In account-takeover incidents, audit those factors separately.

## 9. Spring Boot 3 Example: Change/Reset with authVersion Guard

This demo uses Spring MVC form login, server-side sessions, a single user `alice`, and an in-memory account/reset store. It demonstrates verifying the **current password**, a **32-byte** reset token, single-use token consumption, and version-based session revocation. Use it strictly for study—**never** copy the in-memory store or reset delivery stub into production.

Files:

```text
src/main/java/example/recovery/
  RecoveryApplication.java
  DemoDelivery.java
  DemoAccounts.java
  SessionVersionFilter.java
  SecurityConfig.java
  RecoveryController.java

src/test/java/example/recovery/
  RecoveryFlowTest.java
```

In a Spring Boot 3 Gradle project with Java 17, dependencies:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

This is the dependencies block, requiring compatible plugins/repositories/toolchain to run. With Maven, use the corresponding starters and `spring-security-test` in test scope.

### 9.1. Main Application

```java
package example.recovery;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RecoveryApplication {
    public static void main(String[] args) {
        SpringApplication.run(RecoveryApplication.class, args);
    }
}
```

File: `src/main/java/example/recovery/RecoveryApplication.java`.

### 9.2. DemoDelivery.java: Test-Only Delivery Double

```java
package example.recovery;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.stereotype.Component;

/** TEST DOUBLE ONLY: stores raw token in memory for tests to retrieve.
 *  Production requires a secure email/outbox adapter and MUST NOT expose tokens.
 */
@Component
public class DemoDelivery {
    private final Map<String, String> latest = new ConcurrentHashMap<>();

    public void deliver(String user, String token) {
        latest.put(user, token);
    }

    public String lastForTest(String user) {
        return latest.get(user);
    }
}
```

Never build a public `GET /reset/token?user=alice` endpoint returning tokens from this adapter. In real products, send links exclusively over verified recovery channels, using a fixed HTTPS origin for the reset URL. Minimize leakage via referrers, logs, analytics, and browser history.

### 9.3. DemoAccounts.java: User Store, Tokens, and authVersion

```java
package example.recovery;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.time.Clock;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.Base64;
import java.util.HashMap;
import java.util.HexFormat;
import java.util.Map;

import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;

@Service
public class DemoAccounts implements UserDetailsService {

    private static final class Account {
        String hash;
        long version;

        Account(String hash, long version) {
            this.hash = hash;
            this.version = version;
        }
    }

    private record Reset(String user, Instant expiresAt) {}

    private final Map<String, Account> accounts = new HashMap<>();
    private final Map<String, Reset> resets = new HashMap<>();
    private final SecureRandom random = new SecureRandom();
    private final Clock clock = Clock.systemUTC();
    private final PasswordEncoder encoder;
    private final DemoDelivery delivery;

    public DemoAccounts(PasswordEncoder encoder, DemoDelivery delivery) {
        this.encoder = encoder;
        this.delivery = delivery;
        accounts.put(
            "alice",
            new Account(encoder.encode("old-demo-password-123"), 1L)
        );
    }

    @Override
    public synchronized UserDetails loadUserByUsername(String user) {
        Account account = accounts.get(user);
        if (account == null) {
            throw new UsernameNotFoundException("User not found");
        }
        // Return a fresh object per lookup; avoid losing the hash in the store.
        return User.withUsername(user)
            .password(account.hash)
            .roles("USER")
            .build();
    }

    public synchronized long version(String user) {
        Account account = accounts.get(user);
        return account == null ? -1 : account.version;
    }

    public synchronized boolean change(
            String user, String current, String next) {
        Account account = accounts.get(user);
        if (account == null || current == null || !validNext(next)) {
            return false;
        }
        if (!encoder.matches(current, account.hash)
                || encoder.matches(next, account.hash)) {
            return false;
        }

        account.hash = encoder.encode(next);
        account.version++;
        resets.entrySet().removeIf(e -> e.getValue().user().equals(user));
        return true;
    }

    public synchronized void requestReset(String user) {
        if (!accounts.containsKey(user)) {
            return; // Controller still returns a generic response.
        }
        resets.entrySet().removeIf(e -> e.getValue().user().equals(user));

        byte[] bytes = new byte[32];
        random.nextBytes(bytes);
        String raw = Base64.getUrlEncoder()
            .withoutPadding()
            .encodeToString(bytes);

        resets.put(
            digest(raw),
            new Reset(user, clock.instant().plus(15, ChronoUnit.MINUTES))
        );
        delivery.deliver(user, raw); // TEST ONLY, never expose via API.
    }

    public synchronized boolean confirm(
            String token, String next) {
        if (token == null || !validNext(next)) {
            return false;
        }

        String id = digest(token);
        Reset grant = resets.get(id);
        if (grant == null || !clock.instant().isBefore(
                grant.expiresAt())) {
            return false;
        }

        Account account = accounts.get(grant.user());
        if (account == null) {
            return false;
        }

        // Demo: single-JVM lock. Production uses DB transaction/CAS.
        resets.remove(id);
        account.hash = encoder.encode(next);
        account.version++;
        resets.entrySet().removeIf(
            e -> e.getValue().user().equals(grant.user())
        );
        return true;
    }

    private static boolean validNext(String value) {
        // Demo length-only; production adds breached-password checks.
        return value != null && value.length() >= 12
            && value.length() <= 128;
    }

    private static String digest(String raw) {
        try {
            byte[] hash = MessageDigest.getInstance("SHA-256")
                .digest(raw.getBytes(StandardCharsets.US_ASCII));
            return HexFormat.of().formatHex(hash);
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException("SHA-256 unavailable", ex);
        }
    }
}
```

**This is not a production reset store:** `synchronized` applies only within one JVM; `HashMap` does not survive restarts or guarantee multi-node atomicity; a real store must purge expired tokens. The demo `requestReset` has different timing for existing vs. missing accounts, so production must handle timing enumeration and rate limiting. `DemoDelivery` keeps raw tokens in RAM for testing and is not a secure side channel. The password policy checks only length for demo purposes, lacking MFA, passkeys, and breached-password checks.

Reset tokens use SHA-256 because the **raw token has 256 bits of CSPRNG entropy**. Never infer that human passwords can be stored with single-pass SHA-256: use `PasswordEncoder` with a slow password KDF.

### 9.4. SessionVersionFilter.java

```java
package example.recovery;

import java.io.IOException;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.servlet.http.HttpSession;

import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.authentication.logout.SecurityContextLogoutHandler;
import org.springframework.web.filter.OncePerRequestFilter;

public class SessionVersionFilter extends OncePerRequestFilter {

    private final DemoAccounts accounts;
    private final SecurityContextLogoutHandler logout =
        new SecurityContextLogoutHandler();

    public SessionVersionFilter(DemoAccounts accounts) {
        this.accounts = accounts;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        Authentication auth =
            SecurityContextHolder.getContext().getAuthentication();

        if (auth != null && auth.isAuthenticated()
                && !(auth instanceof AnonymousAuthenticationToken)) {

            HttpSession session = request.getSession(false);
            Object stamped = session == null
                ? null : session.getAttribute("authVersion");

            long current = accounts.version(auth.getName());

            if (!(stamped instanceof Long v)
                    || v.longValue() != current) {
                logout.logout(request, response, auth);
                response.sendError(HttpServletResponse.SC_UNAUTHORIZED);
                return;
            }
        }

        chain.doFilter(request, response);
    }
}
```

Because the filter compares versions, any other session carrying an old `Authentication` is rejected on its next request after the hash/version changes. The demo uses a single form-login chain; do not attach this exact filter directly to stateless JWT flows. When the DB version is temporarily unreadable, production must fail closed and guard availability rather than letting old sessions pass.

### 9.5. SecurityConfig.java

```java
package example.recovery;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.context.SecurityContextHolderFilter;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        // Cost 10 for demo; production benchmarks/configures stronger.
        return new BCryptPasswordEncoder(10);
    }

    @Bean
    SecurityFilterChain chain(
            HttpSecurity http,
            DemoAccounts accounts) throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/reset/request", "/reset/confirm")
                    .permitAll()
                .requestMatchers("/api/me", "/account/change-password")
                    .authenticated()
                .anyRequest().denyAll()
            )
            .formLogin(form -> form
                .successHandler((request, response, authentication) -> {
                    long v = accounts.version(authentication.getName());
                    request.getSession(true).setAttribute(
                        "authVersion", v
                    );
                    response.sendRedirect("/api/me");
                })
            )
            .logout(logout -> logout.logoutUrl("/logout"))
            .addFilterAfter(
                new SessionVersionFilter(accounts),
                SecurityContextHolderFilter.class
            )
            .build();
    }
}
```

Explanation:

- Spring Security automatically uses `DemoAccounts implements UserDetailsService` with `PasswordEncoder` for standard username/password login. No custom `AuthenticationManager` bean is needed for the demo.
- Upon success, the success handler stamps `authVersion` into the session and redirects. Sessions created before a change or reset keep the older version.
- `SessionVersionFilter` runs right after the security context is loaded and rejects mismatched versions.
- The filter is instantiated inside the chain and **not annotated with `@Component`**, preventing Spring Boot from auto-registering it a second time outside the security filter chain.
- `/reset/request` and `/reset/confirm` are `permitAll` for authorization, **yet default CSRF protection remains active** on `POST`.
- This is a form-login demo; stateless JWT requires its own flow rather than a `JSESSIONID` version attribute.
- The Controller does not mint a new cookie/session after reset; the user must log in again.
- All production responses and notifications must be standardized, minimize sensitive details, and handle errors safely.

### 9.6. RecoveryController.java

```java
package example.recovery;

import java.util.Map;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.authentication.logout.SecurityContextLogoutHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class RecoveryController {

    private final DemoAccounts accounts;
    private final SecurityContextLogoutHandler logout =
        new SecurityContextLogoutHandler();

    public RecoveryController(DemoAccounts accounts) {
        this.accounts = accounts;
    }

    @GetMapping("/api/me")
    public Map<String, String> me(Authentication authentication) {
        return Map.of("username", authentication.getName());
    }

    @PostMapping("/account/change-password")
    public ResponseEntity<Void> change(
            Authentication authentication,
            HttpServletRequest request,
            HttpServletResponse response,
            @RequestParam String currentPassword,
            @RequestParam String newPassword) {

        if (!accounts.change(
                authentication.getName(), currentPassword, newPassword)) {
            return ResponseEntity.badRequest().build();
        }

        logout.logout(request, response, authentication);
        return ResponseEntity.noContent().build();
    }

    @PostMapping("/reset/request")
    public ResponseEntity<Void> requestReset(
            @RequestParam String username) {
        accounts.requestReset(username);
        // Do not disclose account existence or raw token.
        return ResponseEntity.accepted().build();
    }

    @PostMapping("/reset/confirm")
    public ResponseEntity<Void> confirm(
            @RequestParam String token,
            @RequestParam String newPassword) {

        return accounts.confirm(token, newPassword)
            ? ResponseEntity.noContent().build()
            : ResponseEntity.badRequest().build();
    }
}
```

`change` accepts requests only from an authenticated session; the server reads the username from the principal rather than taking `userId` from the body. On a successful change, the handler invalidates the current session; other sessions are rejected by the version filter on their next request. On a successful reset, the API **does not auto-log in**.

**Note:** the demo code takes form parameters for test simplicity. Production needs validation, proper password input handling, HTTPS, CSRF UX, rate limits, and clean response/error design. Calling `SecurityContextLogoutHandler` alone does not replace all Spring Security logout handlers (remember-me, CSRF token cleanup, events).

### 9.7. Testing with JUnit and MockMvc

Create `src/test/java/example/recovery/RecoveryFlowTest.java`:

```java
package example.recovery;

import jakarta.servlet.http.HttpSession;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class RecoveryFlowTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    DemoDelivery delivery;

    private MockHttpSession login(String password) throws Exception {
        MvcResult result = mvc.perform(
            post("/login")
                .with(csrf())
                .param("username", "alice")
                .param("password", password)
        ).andExpect(status().is3xxRedirection())
         .andExpect(redirectedUrl("/api/me"))
         .andReturn();

        HttpSession session = result.getRequest().getSession(false);
        assertThat(session).isInstanceOf(MockHttpSession.class);
        return (MockHttpSession) session;
    }

    @Test
    void loginSessionCanReadIdentity() throws Exception {
        MockHttpSession session = login("old-demo-password-123");

        mvc.perform(get("/api/me").session(session))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("alice"));
    }

    @Test
    void wrongCurrentPasswordDoesNotChangeAccount()
            throws Exception {
        MockHttpSession session = login("old-demo-password-123");

        mvc.perform(post("/account/change-password")
                .session(session)
                .with(csrf())
                .param("currentPassword", "incorrect")
                .param("newPassword", "new-strong-password-987"))
            .andExpect(status().isBadRequest());

        mvc.perform(get("/api/me").session(session))
            .andExpect(status().isOk());
    }

    @Test
    void changeRevokesSessionsAndOldPassword()
            throws Exception {
        MockHttpSession a = login("old-demo-password-123");
        MockHttpSession b = login("old-demo-password-123");

        mvc.perform(post("/account/change-password")
                .session(a)
                .with(csrf())
                .param("currentPassword", "old-demo-password-123")
                .param("newPassword", "new-strong-password-987"))
            .andExpect(status().isNoContent());

        mvc.perform(get("/api/me").session(b))
            .andExpect(status().isUnauthorized());

        mvc.perform(post("/login")
                .with(csrf())
                .param("username", "alice")
                .param("password", "old-demo-password-123"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?error"));

        MockHttpSession fresh = login("new-strong-password-987");
        mvc.perform(get("/api/me").session(fresh))
            .andExpect(status().isOk());
    }

    @Test
    void changeRequiresCsrf() throws Exception {
        MockHttpSession session = login("old-demo-password-123");

        mvc.perform(post("/account/change-password")
                .session(session)
                .param("currentPassword", "old-demo-password-123")
                .param("newPassword", "new-strong-password-987"))
            .andExpect(status().isForbidden());
    }

    @Test
    void resetRequestResponseIsGeneric() throws Exception {
        mvc.perform(post("/reset/request")
                .with(csrf())
                .param("username", "nobody"))
            .andExpect(status().isAccepted());

        mvc.perform(post("/reset/request")
                .with(csrf())
                .param("username", "alice"))
            .andExpect(status().isAccepted());

        assertThat(delivery.lastForTest("nobody")).isNull();
        assertThat(delivery.lastForTest("alice")).isNotBlank();
    }

    @Test
    void resetTokenOneTimeAndOldSessionRejected()
            throws Exception {
        MockHttpSession old = login("old-demo-password-123");

        mvc.perform(post("/reset/request")
                .with(csrf())
                .param("username", "alice"))
            .andExpect(status().isAccepted());

        String token = delivery.lastForTest("alice");
        assertThat(token).isNotBlank();

        mvc.perform(post("/reset/confirm")
                .with(csrf())
                .param("token", token)
                .param("newPassword", "reset-password-new-123"))
            .andExpect(status().isNoContent());

        mvc.perform(post("/reset/confirm")
                .with(csrf())
                .param("token", token)
                .param("newPassword", "another-long-password"))
            .andExpect(status().isBadRequest());

        mvc.perform(get("/api/me").session(old))
            .andExpect(status().isUnauthorized());

        MockHttpSession fresh = login("reset-password-new-123");
        mvc.perform(get("/api/me").session(fresh))
            .andExpect(status().isOk());
    }

    @Test
    void invalidResetTokenCannotChangePassword()
            throws Exception {
        mvc.perform(post("/reset/confirm")
                .with(csrf())
                .param("token", "invalid-token")
                .param("newPassword", "reset-password-new-123"))
            .andExpect(status().isBadRequest());
    }
}
```

Run:

```bash
./gradlew test --tests example.recovery.RecoveryFlowTest
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests example.recovery.RecoveryFlowTest
```

**Expected outcome:** seven test methods pass when the Spring Boot 3 / Spring Security 6.x project, dependencies, and files are configured properly. This is **an expectation from the code**, not a Gradle run executed inside this lesson.

`@DirtiesContext(AFTER_EACH_TEST_METHOD)` resets the account/store state for every test because the demo mutates passwords and `authVersion`. That is a test-isolation choice, not a real account management strategy.

The suite verifies that a post-login session works, a wrong current password is rejected, changing passwords invalidates sessions on other devices, CSRF is enforced, reset responses do not disclose usernames directly, reset tokens are single-use, and prior sessions are rejected. It **does not prove** multi-node transactions, timing-enumeration resistance, email security, expired-token clock edge cases, JWT/refresh revocation, or production infrastructure readiness—all of which require additional integration and security tests.

## 10. Standalone Java 17: Old Sessions Revoked via Session Version

Without Spring Boot, this JDK 17 program clearly demonstrates epoch logic. It **intentionally uses plaintext passwords and an incrementing counter token** to focus purely on the state machine: **never copy this password storage or token generation into production**. The Spring code above uses BCrypt and a CSPRNG; production requires a DB/transaction and proper identity design.

Create `SessionRevocationDemo.java`:

```java
import java.util.HashMap;
import java.util.Map;

public class SessionRevocationDemo {

    record Session(long versionAtLogin) {}

    static final class SystemModel {
        private String password = "old-demo-password";
        private long authVersion = 1;
        private int sequence = 0;

        private final Map<String, Session> sessions =
            new HashMap<>();
        private final Map<String, Boolean> resets =
            new HashMap<>();

        String login(String candidate) {
            if (!password.equals(candidate)) {
                return null;
            }
            String id = "session-" + (++sequence);
            sessions.put(id, new Session(authVersion));
            return id;
        }

        boolean active(String sessionId) {
            Session session = sessions.get(sessionId);
            return session != null
                && session.versionAtLogin() == authVersion;
        }

        boolean change(String current, String next) {
            if (!password.equals(current) || next.length() < 12) {
                return false;
            }
            password = next;
            authVersion++;
            resets.clear();
            return true;
        }

        String requestReset() {
            String token = "demo-token-" + (++sequence);
            resets.put(token, true);
            return token;
        }

        boolean confirmReset(String token, String next) {
            if (next.length() < 12 || resets.remove(token) == null) {
                return false;
            }
            password = next;
            authVersion++;
            resets.clear();
            return true;
        }
    }

    public static void main(String[] args) {
        SystemModel system = new SystemModel();

        String a = system.login("old-demo-password");
        String b = system.login("old-demo-password");

        System.out.println("before.a=" + system.active(a));
        System.out.println("before.b=" + system.active(b));
        System.out.println("change.wrong="
            + system.change("wrong", "changed-password"));
        System.out.println("change.correct="
            + system.change("old-demo-password", "changed-password"));
        System.out.println("afterChange.a=" + system.active(a));
        System.out.println("afterChange.b=" + system.active(b));
        System.out.println("oldLogin="
            + (system.login("old-demo-password") != null));

        String c = system.login("changed-password");
        System.out.println("newSession=" + system.active(c));

        String token = system.requestReset();
        System.out.println("reset.correct="
            + system.confirmReset(token, "reset-password-123"));
        System.out.println("reset.reuse="
            + system.confirmReset(token, "another-password"));
        System.out.println("afterReset.c=" + system.active(c));
        System.out.println("newLogin="
            + (system.login("reset-password-123") != null));
    }
}
```

Compile and run with JDK 17:

```bash
javac SessionRevocationDemo.java
java SessionRevocationDemo
```

**Exact stdout following program logic:**

```text
before.a=true
before.b=true
change.wrong=false
change.correct=true
afterChange.a=false
afterChange.b=false
oldLogin=false
newSession=true
reset.correct=true
reset.reuse=false
afterReset.c=false
newLogin=true
```

Reading the logic:

1. When Alice logs in, each session stores `versionAtLogin=1`.
2. A valid password change increments `authVersion` to 2. Old session IDs stay in the map, yet `active` returns false.
3. The old password can no longer create a new session.
4. A new session carries version 2.
5. A successful reset bumps the version to 3, rendering version-2 sessions inactive.
6. The reset token is removed from the map, so reusing it fails.
7. The user logs in with the newly reset password to get a version-3 session.

This is solely a **state-machine model**, with no HTTPS, CSRF, secure cookies, DB, or password hashing. In particular `demo-token-1` is predictable, not a real reset token; the Spring Boot example uses `SecureRandom` and 32 bytes. Never use this toy model to protect real data.

## 11. Operational Decisions to Clarify

### 11.1. Session-Based, Stateless JWT, and SSO

If your app uses only Servlet sessions, revoking via a shared session store or `authVersion` guard works cleanly. For a JWT resource server, check `JwtDecoder`, token claims, expiration, and runtime policy. If refresh tokens live at an IdP, revoke them at the authorization server. With SSO, logging out of one app does not automatically log out the entire ecosystem; use provider-supported flows.

### 11.2. What Does “Log Out All Devices Immediately” Mean?

On the backend, this requirement can encounter propagation delays:

- Expired registry entries may be evicted only on the next request;
- JWTs without revocation checks remain valid until `exp`;
- Caches introduce TTL or replication lag;
- Requests already authorized before revocation committed may still finish;
- Email/outbox token-revocation events may undergo retries.

Claim “immediate” only when backed by matching guards and measurements, and define the maximum acceptable propagation delay.

### 11.3. Audit Every Token Type

Before coding, list every authentication mechanism your application actually uses: form login, Basic, OAuth2, JWT, refresh tokens, remember-me, SSO, and API keys. Pick a revocation strategy for **each** type and write integration tests using tokens/sessions issued **before** the password change or reset.

### 11.4. Keeping Versions Only in JVM Memory Is Insufficient

Across multiple replicas/pods, every instance must read the same authoritative source or receive synchronous invalidations. The demo `HashMap` does not provide this. If the DB is unreachable, sensitive actions must never silently let old sessions through.

## 12. Common Anti-Patterns

**1. Updating only the hash and assuming logout-all occurred.** Old independent sessions and tokens survive. Add server-side revocation or version guards.

**2. Taking `userId` from a JSON body to change passwords.** Easily causes BOLA/IDOR. Derive the actor from the principal and enforce permissions.

**3. Logging out the user upon a reset request.** Any stranger knowing the email can trigger a DoS. Change state only after verified recovery confirmation.

**4. Returning raw reset tokens in public API responses.** Attackers can change the password themselves. Deliver via verified side channels.

**5. Predictable reset tokens.** Timestamps, counters, or `hash(email)` are inadequate. Use `SecureRandom` with high entropy.

**6. Missing expiration or single-use.** Old links can be replayed; consume tokens atomically.

**7. Two requests with the same token both succeed.** Checking and consuming are non-atomic. Use DB transactions/CAS.

**8. Failing to invalidate other active reset links.** An older link could overwrite the newly reset password.

**9. Deleting the browser cookie while leaving the server session alive.** A stolen cookie copy still works; destroy server-side state.

**10. Using `SessionRegistry` when sessions aren’t registered or across multiple JVMs.** Lookups return empty while you think revocation succeeded. Verify wiring and storage.

**11. Revoking refresh tokens while ignoring still-valid access JWTs.** Document access token TTLs or implement runtime revocation checks.

**12. Rotating the global signing key just to log out one user.** Disrupts all accounts; use per-user token families, versions, or `jti`.

**13. Skipping CSRF on change/reset because of `permitAll`.** Authorization `permitAll` does not replace CSRF. Evaluate browser/cookie threat models.

**14. Letting password reset mint an authenticated session automatically.** Increases session fixation and assurance-bypass risks. Require normal login.

**15. Neglecting timing enumeration.** Generic response text fails if existing accounts take noticeably different processing paths. Control timing and rate limits.

**16. Failing to recheck session state at transaction boundaries.** In-flight requests can still perform side effects after revocation.

**17. Skipping MFA/recovery factor review after compromise.** Attackers may retain control of recovery channels; a new password alone won't evict them.

**18. Forgetting to test old logins after reset.** Tests must verify the old password fails, token reuse fails, old sessions are rejected, and new sessions work.

**19. Conflating reset tokens with access tokens.** Reset tokens are single-purpose and must never authorize general API reads.

**20. Logging reset links or building links from the `Host` header.** Leaks tokens or routes users to attacker domains. Pin trusted origins and guard referrers/logs.

## 13. Implementation Checklist

**Change password**

- [ ] Endpoint resolves the actor solely from verified `Authentication`/immutable user ID.
- [ ] Requires current password or appropriate step-up; attempts are rate-limited.
- [ ] New password passes policy, uses `PasswordEncoder.encode`, and never logs secrets.
- [ ] Updates hash + `authVersion` under transaction/version control.
- [ ] Invalidates old reset links and applies an explicit keep/revoke policy for the current session.
- [ ] Revokes other sessions, refresh tokens, and remember-me tokens per stated scope.
- [ ] CSRF, TLS, cookie flags, and session fixation protections verified.
- [ ] Safe notifications/auditing and retry mechanisms if revocation stores fail.

**Reset password**

- [ ] Request returns generic responses without disclosing accounts via content or timing.
- [ ] Tokens generated with CSPRNG, high entropy, bound to purpose/account/expiry/single-use.
- [ ] Raw tokens never returned publicly or logged; delivered via trusted side channels.
- [ ] Never changes passwords or revokes sessions at the unauthenticated request step.
- [ ] Confirms token atomically alongside password update and version bump.
- [ ] Invalidates old reset tokens and revokes sessions per policy.
- [ ] Does not auto-login after reset; routes user to standard authentication.
- [ ] Rate limiting, email-flood protection, auditing, and concurrency tests in place.

**Session/token revocation**

- [ ] Cataloged HTTP sessions, remember-me, refresh, JWT, opaque, SSO, and API keys.
- [ ] Session registry/index works with custom principals, multiple nodes, and tenants.
- [ ] If using versions, every request checks the authoritative version.
- [ ] Access JWTs have clear TTLs, denylists, or version checks.
- [ ] Refresh tokens/families revoked server-side, not merely deleted from browser storage.
- [ ] Uses immutable user IDs to avoid cross-tenant revocation bugs.
- [ ] Tests cover pre-existing sessions, pre-existing tokens, in-flight requests, and infra failures.
- [ ] UI never promises stronger revocation latency than the backend delivers.

## 14. Self-Check Questions

**1.** Why doesn’t changing `password_hash` automatically invalidate already logged-in HTTP sessions?

**2.** What proof distinguishes change password from reset password?

**3.** Why must a reset request taking only an email never auto-log out the victim?

**4.** Why do reset tokens need CSPRNG generation, expiration, and single-use?

**5.** Why can you store a SHA-256 digest of a random 256-bit reset token, yet must not store `SHA256(password)` for user passwords?

**6.** Why can `permitAll()` still fail with a CSRF 403?

**7.** Which session does `SecurityContextLogoutHandler` handle?

**8.** Does `SessionInformation.expireNow()` immediately delete sessions across multiple nodes?

**9.** How does the `authVersion` pattern work?

**10.** Does an unexpired JWT access token automatically become invalid when a password changes?

**11.** Why is revoking refresh tokens critical?

**12.** Why does a successful reset normally avoid auto-creating a login session?

**13.** During account compromise, why must recovery emails and MFA factors be reviewed?

**14.** How must two concurrent requests presenting the same reset token be handled?

**15.** If a resource server checks neither `tokenVersion` nor a denylist, can the UI promise instant JWT logout?

**16.** Why must tests use a session created *before* the password change or reset?

**Suggested answers**

1. Session `SecurityContext` has a separate lifecycle from the password hash and does not re-verify raw passwords on every request.
2. Change has an authenticated principal and re-auth; reset relies on a recovery token/side channel.
3. Email is not a credential, so strangers could trigger DoS/forced logouts against victims.
4. So tokens cannot be guessed, do not linger indefinitely, and cannot be replayed.
5. High-entropy tokens have a vast search space; human passwords have low entropy and need slow KDFs.
6. Because the CSRF filter protects state-changing requests independently of `permitAll` authorization.
7. Only the current request/context/session, not other devices automatically.
8. Not by default; it may only mark expired in memory and requires proper registry/filter/shared storage.
9. Sessions stamp the version at login; when the account increments the version, older sessions are rejected.
10. No, unless the resource server checks revocation or until the token expires.
11. Because living refresh tokens can continue minting new access tokens.
12. OWASP recommends returning to normal login, reducing complexity and assurance risks.
13. Attackers may have added or compromised recovery channels and authenticators.
14. Only one request may succeed atomically inside a transaction/CAS.
15. No. Either state the `exp` bound clearly or implement runtime revocation checks.
16. Testing only a brand-new session fails to prove old sessions were actually revoked.

## 15. Official References

- [OWASP – Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html)
- [OWASP – Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
- [OWASP – Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
- [Spring Security 6.5 – Handling Logouts](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/logout.html)
- [Spring Security 6.5 – Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html)
- [Spring Security 6.5 – CSRF Protection](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html)
- [Spring Security 6.5 – Password Storage](https://docs.spring.io/spring-security/reference/6.5/features/authentication/password-storage.html)
- [Spring Security – SecurityContextLogoutHandler API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/logout/SecurityContextLogoutHandler.html)
- [Spring Security – SessionInformation API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/session/SessionInformation.html)
- [Spring Session – FindByIndexNameSessionRepository API](https://docs.spring.io/spring-session/docs/current/api/org/springframework/session/FindByIndexNameSessionRepository.html)
- [NIST SP 800-63B – Authentication and Account Recovery](https://pages.nist.gov/800-63-4/sp800-63b.html)
