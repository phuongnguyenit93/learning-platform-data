# Verifying Account Locking, Password Changes, and Logout Across Multiple Sessions

## 1. Objectives and Context

Users can sign in simultaneously on a laptop, a phone, two browsers, or multiple application nodes. When an account is **locked**, a user **changes their password**, or they request **logout from all devices**, the system must prove that old authentication evidence is no longer accepted per policy. A single `account.locked = true` row or a `200` HTTP response is insufficient.

This exercise uses **Spring Security Servlet**, within a Spring Boot 3.x / Spring Security 6.x context, with three sessions:

- **A**: Alice signed in on browser 1.
- **B**: Alice signed in on browser 2.
- **C**: Bob signed in on browser 3 to verify another account is never revoked accidentally.

Afterward, Alice unlocks and signs in again as **D**; changes her password and signs in again as **E** and **F**. We verify that **logging out single session E** keeps F active; on **logout all**, F is also rejected.

Objectives:

1. Understand why `UserDetails.isAccountNonLocked()` checks at login do not automatically block already-existing sessions.
2. Define test criteria covering new logins, existing sessions, password hashes, logout current, and logout all.
3. Use session epochs/versions and Spring Session to enforce multi-session, multi-node revocation.
4. Distinguish `SessionRegistry.expireNow()` from deleting server-side sessions.
5. Test with `MockMvc`, Spring Session/Redis, and real HTTP cookie jars.
6. Remember refresh tokens, JWT access tokens, remember-me, MFA proofs, and IdP sessions when business rules require broader revocation.
7. Run a **standalone Java 17** program simulating full state transitions with deterministic stdout.

**Illustrative policy scope:** locking an account **blocks both new logins and all existing sessions**. A successful password change **forces all existing sessions—including the session that performed the change—to sign in again**. Systems that only block new logins or preserve the re-authenticated session must state that alternative policy explicitly and test accordingly.

## 2. States That Must Be Distinguished

| Object | State | Conditions to Permit |
| --- | --- | --- |
| Account | `ACTIVE`, `LOCKED`, `DISABLED`, `SUSPENDED` | Checking the password alone is insufficient; must follow active policy. |
| Password | Current hash, credential version | New password must verify against new hash; old password fails login. |
| Browser session | Session ID, principal, issued epoch | Session exists, account active, issued epoch matches current epoch. |
| Remember-me | Token/series/cookie | Not revoked and owner remains permitted. |
| OAuth refresh token | Authorization grant/token family | Active grant, active account, token not revoked/expired. |
| Access JWT | Signature, `iss`, `aud`, `exp`, scopes, version | Cryptographically valid **and** satisfies current revocation strategy. |
| MFA proof | Factor, challenge, `verifiedAt`, purpose | Factor remains valid, proof unrevoked, within freshness window. |
| OIDC/SSO | Local RP session and IdP session | Handle each separately; RP logout does not automatically log out the IdP. |

**Previously issued credentials can outlive a password.** Updating a password in the DB does not automatically invalidate bearer JWTs, refresh grants, API keys, or remember-me cookies.

**Logout current** applies only to one local session unless specified otherwise. **Logout all devices** must explicitly define whether it includes OIDC/IdP, OAuth2 grants, mobile refresh tokens, and trusted devices rather than hiding behind a vague UI label.

## 3. Behavior Matrix Before Writing Code

| Point in Time | A (Alice) | B (Alice) | C (Bob) | Alice Login |
| --- | --- | --- | --- | --- |
| Initial | Allow | Allow | Allow | Allow with right password |
| After locking Alice | Deny | Deny | Allow | Deny even with right password |
| After unlocking Alice | Deny, never resurrect | Deny, never resurrect | Allow | Allow, issue new session D |
| After password change | Deny D and all old sessions | Deny all old sessions | Allow | Old password fails, new password succeeds |
| After logout current E | Deny E | Allow F (same account) | Allow | Can log in if account active |
| After logout all Alice | Deny all Alice sessions | Deny F | Allow | Can log in again with current credentials |

A change should be considered successful only when **the next request presenting an old cookie/session ID is blocked**, not merely when the mutation API returns `200` or the UI shows "Logged out".

Minimum assertions:

- Sessions A and B have **different session IDs**, not the same object reused.
- Bob is never logged out due to a wrong principal lookup or overly broad cleanup.
- Unlocking never revives A/B or tokens from an earlier security epoch.
- When password change fails due to a wrong current password, **never** mutate hash/epoch or revoke sessions unintentionally.
- Delayed cleanup events must not leave stale sessions able to access resources beyond SLA.

## 4. Relevant Spring Security Mechanisms

In the Servlet stack:

~~~text
Browser Cookie JSESSIONID/SESSION
        |
        v
Servlet FilterChain / Spring Security FilterChainProxy
        |
        v
SecurityContextRepository loads Authentication from session
        |
        +-- AuthorizationFilter / method security
        |
        +-- application business method
~~~

During form login:

~~~text
POST /login
    -> UsernamePasswordAuthenticationFilter
    -> AuthenticationManager / ProviderManager
    -> DaoAuthenticationProvider / UserDetailsService
    -> PasswordEncoder matches password
    -> user account status checks
    -> SecurityContext persisted in HttpSession
~~~

`UserDetails.isAccountNonLocked()` and `isEnabled()` run during authentication inside the matching provider. **Requests carrying an already-authenticated session often only restore `Authentication` from `SecurityContextRepository` without re-running the password provider.** Therefore, setting `locked=true` alone does not automatically block active sessions A/B.

Furthermore, `SecurityContextHolder.clearContext()` clears only the current execution's context; it **does not delete** sessions on other devices or refresh/access tokens. You need a dedicated session repository/index/epoch gate.

## 5. Designing Authoritative State and a Monotonic Epoch

Illustrative PostgreSQL schema:

~~~sql
CREATE TABLE app_account (
  user_id           VARCHAR(80) PRIMARY KEY,
  username          VARCHAR(120) UNIQUE NOT NULL,
  password_hash     VARCHAR(255) NOT NULL,
  status            VARCHAR(24) NOT NULL,
  security_epoch    BIGINT NOT NULL DEFAULT 1,
  authz_version     BIGINT NOT NULL DEFAULT 1,
  updated_at        TIMESTAMPTZ NOT NULL
);

CREATE TABLE security_outbox (
  event_id          VARCHAR(80) PRIMARY KEY,
  subject_user_id   VARCHAR(80) NOT NULL,
  event_type        VARCHAR(50) NOT NULL,
  target_epoch      BIGINT NOT NULL,
  actor_user_id     VARCHAR(80),
  created_at        TIMESTAMPTZ NOT NULL
);
~~~

`user_id` is an immutable identifier that never changes with email or username. `password_hash` uses an appropriate `PasswordEncoder` algorithm (e.g., BCrypt/Argon2). `security_epoch` increments whenever all prior sessions/proofs must be revoked; `authz_version` can increment independently when roles/tenant permissions change.

Example:

~~~text
Account Alice: status=ACTIVE, epoch=7
Session A: issuedEpoch=7 -> accepted
Session B: issuedEpoch=7 -> accepted

Admin locks Alice:
  update status=LOCKED
  update epoch=8
  commit

Next request:
  A/B issuedEpoch=7 != current 8 -> denied
  status=LOCKED -> denied

Admin unlocks:
  update status=ACTIVE
  epoch remains >=8 (can increase again)
  A/B epoch=7 -> denied
  new D issuedEpoch=current -> accepted
~~~

**Incrementing the epoch in the DB has zero effect if enforcement points do not check it.** If a node relies only on a session `SecurityContext` snapshot and an unbounded stale cache, old tokens/sessions still pass.

## 6. Account Locking Must Commit Before Reporting Success

Proper admin workflow:

~~~text
Security admin -> POST /admin/users/{id}/lock
   |
   +-- authenticate actor and authorize by tenant
   +-- transactional account update:
   |       ACTIVE -> LOCKED
   |       securityEpoch++
   |       append security_outbox event
   +-- commit
   +-- request gate sees locked status / newer epoch
   +-- cleanup sessions/grants asynchronously with retry
   +-- audit + notification
~~~

Spring service snippet **requiring project-implemented domain types**:

~~~java
@Transactional
public long lockAccount(String stableUserId, String actorId) {
    AccountEntity account =
            repository.findByIdForUpdate(stableUserId)
                    .orElseThrow(AccountNotFoundException::new);

    if (!account.isLocked()) {
        account.setLocked(true);
        account.setSecurityEpoch(account.getSecurityEpoch() + 1);
        outbox.saveLocked(account.getId(),
                account.getSecurityEpoch(), actorId);
    }
    return account.getSecurityEpoch();
}
~~~

This is an **integration snippet**, not an application runnable by `javac` alone. `findByIdForUpdate` requires a transaction/pessimistic lock or explicit optimistic versioning; `outbox` must commit alongside the account update. Prevent races and duplicate messages with event IDs/versions. Never let callers pick arbitrary tenants/subjects outside the admin's authority.

**Proof point:** immediately after commit, attempting a new login with the locked account's valid password must fail. Simultaneously, prior cookies A/B must also be rejected when lock policy dictates "immediate access revocation".

## 7. Password Change: Verifying Old Credentials and Invalidating Old Sessions

Self-service password change requires:

1. A currently authenticated principal mapped to an internal ID from a trusted source.
2. CSRF verification on session-backed POSTs plus recent re-auth/MFA if required by policy.
3. Verifying the current password via `passwordEncoder.matches(...)`.
4. Validating the new password against policy (length, denylist/breached passwords, password history per policy).
5. Transaction: save `passwordEncoder.encode(newPassword)`, increment `securityEpoch`, append outbox event.
6. After commit, invalidate current session / clear `SecurityContext`; clean up other sessions, remember-me, and refresh grants/proofs per scope.
7. Send a safe notification without putting raw passwords into audits/logs.

Example:

~~~java
@Transactional
public long changePassword(
        String stableUserId, String oldPassword, String newPassword) {

    AccountEntity a = repository.findByIdForUpdate(stableUserId)
            .orElseThrow(AccountNotFoundException::new);

    if (!a.isActive() || a.isLocked()) {
        throw new AccountPolicyException();
    }
    if (!passwordEncoder.matches(oldPassword, a.getPasswordHash())) {
        throw new BadCredentialsException("Credential not accepted");
    }
    passwordPolicy.validate(newPassword);

    a.setPasswordHash(passwordEncoder.encode(newPassword));
    a.setSecurityEpoch(a.getSecurityEpoch() + 1);
    outbox.savePasswordChanged(a.getId(), a.getSecurityEpoch());
    return a.getSecurityEpoch();
}
~~~

The fields/types above belong to your application, not built-in Spring Security classes. **Never read `stableUserId` from the request body** letting users change someone else's password; use the authenticated internal principal. Forgot-password reset is a separate workflow with single-use time-limited recovery tokens and its own security checks.

Tests must verify: before/after password hashes differ; `matches(newPassword, storedHash)` is true; the old password fails new logins; **both old sessions A/B are denied**; and a failed password change due to wrong old password leaves epoch/hash untouched.

## 8. Logout Current vs. Logout All

Spring Security Servlet provides `logout()` and logout handlers. Standard handlers clear `SecurityContext` and invalidate the current `HttpSession`. With CSRF enabled, **POST `/logout`** is the proper default.

~~~java
http.authorizeHttpRequests(a -> a
        .requestMatchers("/public").permitAll()
        .anyRequest().authenticated())
    .formLogin(Customizer.withDefaults())
    .logout(logout -> logout
        .logoutUrl("/logout")
        .invalidateHttpSession(true)
        .clearAuthentication(true));
~~~

This is a configuration snippet inside a `SecurityFilterChain` using `HttpSecurity`/`Customizer`, not standalone code. Never disable CSRF app-wide just to support GET logout. When using forms/SPAs for logout, send the CSRF token per your configured repository.

**Logout current:**

~~~text
POST /logout with session A + CSRF-A
  -> delete/invalidate A server-side
  -> old cookie A cannot sign back in
  -> B for same user remains active
  -> C for different user remains active
~~~

**Logout all:**

~~~text
POST /sessions/logout-all with Alice's authenticated context
  -> require recent assurance / step-up if sensitive
  -> bump Alice.securityEpoch
  -> delete/expire Alice sessions
  -> A/B/D/F all denied
  -> Bob session C remains active
~~~

Calling `SecurityContextHolder.clearContext()` alone affects only the current context, not all devices. Deleting cookies client-side is equally insufficient if a cookie was copied.

## 9. Spring Session and `FindByIndexNameSessionRepository`

Spring Session Redis/JDBC can centralize session storage and index by principal. `FindByIndexNameSessionRepository<S extends Session>` exposes `findByPrincipalName(...)`. Once session IDs are found, call `deleteById(...)`:

~~~java
import java.util.Map;
import org.springframework.session.FindByIndexNameSessionRepository;
import org.springframework.session.Session;

public final class AllSessionsRevoker<S extends Session> {
    private final FindByIndexNameSessionRepository<S> sessions;

    public AllSessionsRevoker(
            FindByIndexNameSessionRepository<S> sessions) {
        this.sessions = sessions;
    }

    public int revoke(String indexedPrincipal) {
        Map<String, S> found =
                sessions.findByPrincipalName(indexedPrincipal);
        found.keySet().forEach(sessions::deleteById);
        return found.size();
    }
}
~~~

This is **integration code** with Spring Session. Spring Session docs note that the principal-name index must be populated; some integrations index Spring Security usernames automatically, while custom principals require verification. The queried index name must **match the exact indexed value**, ideally an immutable user ID with explicit tenant namespacing. Do not assume `findByPrincipalName("usr-1001")` finds sessions when the app indexes `"alice@example.test"`.

Potential gaps:

- A session created concurrently right before/after the index scan is missed.
- A node retains a stale session cache and continues permitting access.
- Indexing by a mutable email, or two tenants sharing identical usernames.
- Redis unavailability delays cleanup.
- Deleting sessions does not revoke refresh JWTs or API keys.

Therefore, **request-path security epochs + physical session cleanup** complement each other. If cleanup fails, the epoch still blocks within SLA while outbox/retry/reconciliation sweeps state.

## 10. `SessionRegistry.expireNow()` Is Not Immediate Cluster-Wide Deletion

Spring Security's `SessionRegistry` and `SessionInformation` manage concurrent sessions. You can invoke:

~~~java
List<SessionInformation> active =
        sessionRegistry.getAllSessions(principal, false);
for (SessionInformation s : active) {
    s.expireNow();
}
~~~

Behavior: marks sessions expired so mechanisms like `ConcurrentSessionFilter` (when configured) detect it on the next request and handle expiration. **It does not automatically destroy `HttpSession` synchronously across an entire cluster.** A node-local `SessionRegistryImpl` cannot see browser B's session on another node. Spring Security docs also remind developers to verify `equals/hashCode` on custom `UserDetails` when the registry indexes by principal equality.

Tests must prove **the filter actually executes**, the subsequent request is blocked, and cross-node state stays consistent—not merely assert `isExpired() == true` on the registry object.

`maximumSessions(1)` is a concurrency-control policy, not a replacement for a logout-all endpoint. Previously signed-in users may also hold remember-me/refresh tokens/JWTs outside the session registry.

## 11. Enforcement via Session Security Epoch

To defeat stale `SecurityContext` instances, each session stores a server-issued `LOGIN_EPOCH` upon successful authentication:

~~~text
Session A: principal=usr-1001, LOGIN_EPOCH=11
Account:   userId=usr-1001, active=true, securityEpoch=11
GET /me -> allow

Admin locks:
Account: locked=true, securityEpoch=12
GET /me with A -> deny
~~~

An **illustrative Servlet `OncePerRequestFilter` integration** for session-backed authentication:

~~~java
import java.io.IOException;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.servlet.http.HttpSession;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.filter.OncePerRequestFilter;

public class SessionEpochGuardFilter extends OncePerRequestFilter {
    public static final String LOGIN_EPOCH = "LOGIN_EPOCH";
    private final AccountStateLookup states;

    public SessionEpochGuardFilter(AccountStateLookup states) {
        this.states = states;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request, HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        Authentication a =
                SecurityContextHolder.getContext().getAuthentication();

        if (a == null || !a.isAuthenticated()
                || a instanceof AnonymousAuthenticationToken) {
            chain.doFilter(request, response);
            return;
        }

        String userId = states.resolveVerifiedInternalId(a);
        HttpSession session = request.getSession(false);
        Object issued = session == null ? null :
                session.getAttribute(LOGIN_EPOCH);
        AccountStateLookup.State current =
                states.loadAuthoritative(userId);

        boolean accepted = current != null
                && current.active()
                && issued instanceof Long
                && ((Long) issued) == current.epoch();

        if (!accepted) {
            SecurityContextHolder.clearContext();
            if (session != null) {
                session.invalidate();
            }
            response.sendError(HttpServletResponse.SC_UNAUTHORIZED);
            return;
        }
        chain.doFilter(request, response);
    }
}
~~~

Supporting contract to implement in your project:

~~~java
interface AccountStateLookup {
    record State(boolean active, long epoch) {}
    String resolveVerifiedInternalId(Authentication authentication);
    State loadAuthoritative(String stableUserId);
}
~~~

**This is not a standalone Spring Boot app runnable with `javac` alone.** It needs your project's lookup store/transactions, auth config, imports, bean wiring, and error handling. Register the filter after context loading and before authorization checks:

~~~java
http.addFilterAfter(
        new SessionEpochGuardFilter(states),
        SecurityContextHolderFilter.class);
~~~

`SecurityContextHolderFilter` lives in `org.springframework.security.web.context`, and the `states` bean is supplied by the app. With multiple `SecurityFilterChain` beans, apply the guard across all session-using chains; OIDC, remember-me, and custom logins must all stamp the epoch on their paths.

**Critical limitation:** the filter above is **strictly for session-backed requests**. Stateless Bearer JWT calls have no `HttpSession` and would be rejected by this logic; use a dedicated **token-specific epoch/status gate** on resource servers instead of copying this filter into JWT APIs.

## 12. Stamping the Issued Epoch on Successful Login

Once the provider authenticates and account state remains active, the success handler writes the epoch into the session:

~~~java
http.formLogin(form -> form.successHandler(
        (request, response, authentication) -> {
    String userId =
            states.resolveVerifiedInternalId(authentication);
    AccountStateLookup.State current =
            states.loadAuthoritative(userId);

    if (current == null || !current.active()) {
        throw new IllegalStateException(
                "Account state changed during login");
    }

    request.getSession(true).setAttribute(
            SessionEpochGuardFilter.LOGIN_EPOCH,
            current.epoch());

    response.sendRedirect("/dashboard");
}));
~~~

This is an **integration snippet**, not a production-complete error handler. If the account gets locked between password provider success and session persistence, handle failure cleanup/consistency so an invalid session is never minted. Custom success handlers must also preserve session fixation protection and saved-request semantics where required.

Never take the epoch from a request body or client cookie—it is stamped server-side after verification. When roles/tenants change, `authzVersion` and authorization services may need extra checks; **matching epochs alone do not prove the user may read a specific resource**.

## 13. Testing Real Logins with MockMvc, Not Mock Principals

Spring Security Servlet tests can run with:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class LifecycleSecurityIntegrationTests {
    @Autowired MockMvc mvc;
    // test methods
}
~~~

On `@AutoConfigureMockMvc`, never set `addFilters=false` when testing security filters. If building via `MockMvcBuilders.webAppContextSetup(context)` manually, apply `springSecurity()`.

Create two real sessions:

~~~java
MvcResult first = mvc.perform(
        formLogin().user("alice").password("OldDemo#123"))
    .andExpect(authenticated().withUsername("alice"))
    .andReturn();

MvcResult second = mvc.perform(
        formLogin().user("alice").password("OldDemo#123"))
    .andExpect(authenticated().withUsername("alice"))
    .andReturn();

MockHttpSession a =
        (MockHttpSession) first.getRequest().getSession(false);
MockHttpSession b =
        (MockHttpSession) second.getRequest().getSession(false);

assertNotNull(a);
assertNotNull(b);
assertNotEquals(a.getId(), b.getId());

mvc.perform(get("/me").session(a))
    .andExpect(status().isOk());
mvc.perform(get("/me").session(b))
    .andExpect(status().isOk());
~~~

This is a **test snippet** inside a class importing `MvcResult`, `MockHttpSession`, JUnit assertions, static `formLogin`/`authenticated`/`get`/`status`, plus configured form-login and user fixtures. It cannot run standalone without the corresponding security chain and controller.

**`@WithMockUser`/`user()` cannot replace `formLogin()`** here: they inject a mock principal to test authorization while skipping `PasswordEncoder`, locked/disabled checks, session creation, and real login failures.

For REST APIs using JSON authentication filters instead of Spring `formLogin`, post JSON through the real filter/provider rather than adding `formLogin` just for tests.

## 14. Account Locking Test Scenario

Sequence:

1. Sign Alice in on browsers A/B and Bob on C; verify all three succeed on `GET /me`.
2. Admin invokes lock or the test fixture calls the **real lifecycle service**; verify the transaction commits account locked and bumps epoch.
3. Attempt to log Alice in again with the right password; must be rejected.
4. Replay sessions A and B; protected resources must reject post-commit within SLA.
5. Bob's C must continue working.
6. Unlock Alice; A/B **remain** denied due to their stale issued epoch.
7. Fresh Alice login creates D, and D works normally.

New login assertion:

~~~java
mvc.perform(formLogin()
        .user("alice").password("OldDemo#123"))
    .andExpect(unauthenticated());
~~~

Form-login failure responses are often redirects rather than 401; never assume every login failure returns JSON. Tests should assert both authentication status and expected client response.

**MockMvc note:** once the epoch guard calls `MockHttpSession.invalidate()`, passing that same mock object into another `mvc.perform(...).session(old)` may throw `IllegalStateException`. To test **HTTP cookie replay** faithfully, run an integration test backed by a Spring Session repository and cookie jar sending the raw old cookie ID, rather than inferring status from an invalidated mock object.

## 15. Password Change Test Scenario

After unlocking, log in as D with the old password:

~~~text
Alice: status ACTIVE, epoch=9
Session D: issuedEpoch=9

POST /account/password:
  currentPassword = OldDemo#123
  newPassword     = NewDemo#456
  -> passwordEncoder.matches(current, oldHash) = true
  -> password hash updated
  -> epoch=10 committed
  -> D (and old A/B) revoked

POST /login old password -> fail
POST /login new password -> success, new session E
~~~

Assertions must verify:

- Only the right current password allows changing; a wrong current password leaves hash/epoch unchanged.
- New password meets policy; failures leave zero side effects.
- Before/after hashes differ and the new hash is not plaintext.
- `passwordEncoder.matches("NewDemo#456", storedHash)` returns true.
- All sessions issued before the change are denied.
- New login with old password fails; new password succeeds.
- Other users still log in and access resources normally.
- Only the account owner or an authorized admin can execute the change.
- Requests missing CSRF or recent step-up (if required) are rejected.

Never stop at asserting `/account/password` returns `200`. Afterward, try **the old password** and **the old cookie** just as an attacker would.

## 16. Logout Current and Logout All Tests

**Logout current E:**

~~~text
Alice sessions E & F active
Bob session C active

POST /logout with E + valid CSRF token
  -> E invalidated
  -> F still active
  -> C still active
~~~

Spring Security Test provides `SecurityMockMvcRequestBuilders.logout()` for the default logout filter. Assert server-side invalidation, not just the logout handler's status/redirect.

**Logout all Alice:**

~~~text
Alice F active
Bob C active

POST /sessions/logout-all as Alice with recent assurance
  -> bump Alice securityEpoch
  -> revoke/delete all indexed Alice sessions
  -> replay F -> deny
  -> C -> still allow
~~~

Logout-all can also invalidate the calling session. In self-service APIs, derive the subject from the authenticated principal—never accept a client-supplied `userId`. Test concurrent logout-all requests/races for the same user to ensure idempotency and no session resurrection.

## 17. Standalone Java 17 Program: Full State Verification

This program runs on the **JDK 17 Standard Library** with no Spring dependencies. It simulates an account store and session registry with synchronized operations to illustrate the **epoch + status** policy. Passwords are stored using **PBKDF2WithHmacSHA256** with random salts to avoid plaintext in the example; this remains a **demo**, not a production `PasswordEncoder` replacement.

Save as `AccountLifecycleMultiSessionDemo.java`:

~~~java
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;

public class AccountLifecycleMultiSessionDemo {
    private static final SecureRandom RNG = new SecureRandom();

    private static byte[] derive(char[] password, byte[] salt) {
        PBEKeySpec spec = new PBEKeySpec(
                password, salt, 120_000, 256);
        try {
            return SecretKeyFactory
                    .getInstance("PBKDF2WithHmacSHA256")
                    .generateSecret(spec).getEncoded();
        } catch (GeneralSecurityException e) {
            throw new IllegalStateException("KDF unavailable", e);
        } finally {
            spec.clearPassword();
        }
    }

    private static final class Account {
        final String id;
        byte[] salt;
        byte[] verifier;
        boolean locked;
        long epoch = 1L;

        Account(String id, char[] password) {
            this.id = id;
            updatePassword(password);
        }

        boolean matches(char[] password) {
            return MessageDigest.isEqual(
                    verifier, derive(password, salt));
        }

        void updatePassword(char[] password) {
            byte[] newSalt = new byte[16];
            RNG.nextBytes(newSalt);
            byte[] newVerifier = derive(password, newSalt);
            salt = newSalt;
            verifier = newVerifier;
        }
    }

    private record Ticket(String userId, long epoch) {}

    private static final class Registry {
        private final Map<String, Account> accounts = new HashMap<>();
        private final Map<String, Ticket> sessions = new HashMap<>();
        private long counter;

        synchronized void add(String user, char[] password) {
            accounts.put(user, new Account(user, password));
        }

        synchronized String login(String user, char[] password) {
            Account a = accounts.get(user);
            if (a == null || a.locked || !a.matches(password)) {
                return null;
            }
            String id = "sid-" + (++counter);
            sessions.put(id, new Ticket(user, a.epoch));
            return id;
        }

        synchronized boolean allowed(String sessionId) {
            Ticket ticket = sessions.get(sessionId);
            if (ticket == null) {
                return false;
            }
            Account a = accounts.get(ticket.userId());
            return a != null && !a.locked
                    && ticket.epoch() == a.epoch;
        }

        synchronized void lock(String user) {
            Account a = Objects.requireNonNull(accounts.get(user));
            a.locked = true;
            a.epoch++;
        }

        synchronized void unlock(String user) {
            Account a = Objects.requireNonNull(accounts.get(user));
            a.locked = false;
            a.epoch++;
        }

        synchronized boolean changePassword(
                String user, char[] current, char[] next) {
            Account a = accounts.get(user);
            if (a == null || a.locked || !a.matches(current)) {
                return false;
            }
            a.updatePassword(next);
            a.epoch++;
            return true;
        }

        synchronized void logoutOne(String sid) {
            sessions.remove(sid);
        }

        synchronized void logoutAll(String user) {
            Account a = Objects.requireNonNull(accounts.get(user));
            a.epoch++;
            sessions.entrySet().removeIf(
                    e -> user.equals(e.getValue().userId()));
        }
    }

    public static void main(String[] args) {
        Registry r = new Registry();
        r.add("alice", "OldDemo#123".toCharArray());
        r.add("bob", "BobDemo#789".toCharArray());

        String a = r.login("alice", "OldDemo#123".toCharArray());
        String b = r.login("alice", "OldDemo#123".toCharArray());
        String c = r.login("bob", "BobDemo#789".toCharArray());

        System.out.println("start: A=" + r.allowed(a)
                + ", B=" + r.allowed(b)
                + ", Bob=" + r.allowed(c));

        r.lock("alice");
        System.out.println("locked: A=" + r.allowed(a)
                + ", B=" + r.allowed(b));
        System.out.println("login while locked: " +
                (r.login("alice", "OldDemo#123".toCharArray()) != null));

        r.unlock("alice");
        System.out.println("old session after unlock: "
                + r.allowed(a));
        String d = r.login("alice", "OldDemo#123".toCharArray());
        System.out.println("fresh login after unlock: "
                + r.allowed(d));

        System.out.println("change password: "
                + r.changePassword(
                    "alice",
                    "OldDemo#123".toCharArray(),
                    "NewDemo#456".toCharArray()));
        System.out.println("session D after change: "
                + r.allowed(d));
        System.out.println("old password login: " +
                (r.login("alice", "OldDemo#123".toCharArray()) != null));

        String e = r.login("alice", "NewDemo#456".toCharArray());
        String f = r.login("alice", "NewDemo#456".toCharArray());
        System.out.println("new password login: " + r.allowed(e));

        r.logoutOne(e);
        System.out.println("logout one: E=" + r.allowed(e)
                + ", F=" + r.allowed(f));

        r.logoutAll("alice");
        System.out.println("logout all: F=" + r.allowed(f));
        System.out.println("bob unaffected: " + r.allowed(c));
    }
}
~~~

Run:

~~~bash
javac AccountLifecycleMultiSessionDemo.java
java AccountLifecycleMultiSessionDemo
~~~

**Exact stdout:**

~~~text
start: A=true, B=true, Bob=true
locked: A=false, B=false
login while locked: false
old session after unlock: false
fresh login after unlock: true
change password: true
session D after change: false
old password login: false
new password login: true
logout one: E=false, F=true
logout all: F=false
bob unaffected: true
~~~

Interpretation:

- A/B are active before locking and both denied after locking.
- Login while locked fails even with the right password.
- Unlocking does not revive A/B; a new session D must be minted.
- Password change updates the verifier and bumps the epoch, rejecting old D.
- Old password fails login; new password creates E/F.
- Logging out E leaves F active; logout-all revokes F while Bob's C stays active.

**Limitations:** all state lives in **one JVM**, without HTTP cookies, `SecurityFilterChain`, Redis, JWT, IdPs, or DB transactions. The program illustrates logic; run integration tests against the real stack before claiming multi-device revocation works. Production password cost/algorithm/rotation should use Spring's `PasswordEncoder` per policy, never constant demo passwords.

## 18. Multi-Node and Concurrency Testing

Run Node 1 and Node 2 sharing the account DB and Spring Session Redis/JDBC:

~~~text
Browser A --> Node 1 --+
                        +--> shared account status/epoch
Browser B --> Node 2 --+--> shared session store
Bob C      --> Node 2

Admin lock at Node 1
  -> commit locked=true, epoch=12
  -> replay A at Node 1: DENY
  -> replay B at Node 2: DENY
  -> C remains ALLOW
~~~

A local `MockMvc` test **does not prove cross-node revocation**. Run two server instances with two cookie jars, send requests post-commit, and measure latency from the state change until all paths reject.

Critical race conditions:

- Login B racing with lock: must never mint a session carrying the old epoch that remains accepted post-commit.
- Password change racing with new login: verifier/epoch must update atomically.
- Logout-all scanning sessions while a new session is created: the epoch gate blocks older or mismatched-version sessions.
- Transient queue/Redis cleanup failures: outbox retries while the status gate continues enforcing SLA.
- Unlock after lock: never decrement the epoch and resurrect old cookies.
- High-risk request authorized before lock yet committing after lock: service re-checks epoch near transaction commit per policy.

Use `CountDownLatch`/barriers to reproduce races deterministically in integration tests rather than guessing ordering with `Thread.sleep`.

## 19. Refresh Tokens, Access JWTs, and SSO Sessions

An OAuth2 system may have issued:

~~~text
Alice Browser Session A  -> Spring Session
Refresh Token RT-A       -> Authorization Server
Access JWT AT-A          -> Resource Server (stateless verification)
IdP SSO Session          -> Identity Provider
Remember-Me Cookie       -> Persistent-token repository
~~~

**Locking an account** must stop the Authorization Server from minting new tokens. **Password resets for suspected compromise** typically require revoking refresh grants, token-family rotation state, remember-me tokens, MFA proofs, and sessions. Yet **revoking a refresh token does not automatically invalidate already-issued JWT access tokens**.

For JWTs, pick an explicit strategy:

- Short TTLs accepting the residual window until `exp`.
- Per-user epoch/security version checked by the Resource Server on the request path.
- `jti` denylist for specific tokens.
- Opaque tokens / introspection with bounded cache TTL/invalidation.
- Gateway/central enforcement protected against bypass routes.

An unexpired JWT with a valid signature **does not prove** the account is currently active. Nor should OIDC ID Tokens be used as API access tokens.

**SSO:** logging out a local Relying Party does not automatically log out the IdP. For true "all devices and all apps", implement OIDC RP-initiated/back-channel logout or per-RP deprovisioning enforcement. API keys/service tokens follow their own lifecycles under owner/tenant policies.

## 20. Negative Tests Commonly Missed

| Case | Assertion |
| --- | --- |
| Anonymous caller invokes password change | Denied, hash untouched. |
| Alice submits Bob's `userId` to change password | Denied, Bob unaffected. |
| Password change with wrong current password | Hash/epoch preserved, no unintended revocation. |
| New password fails policy | Rejected before commit. |
| Password change POST missing CSRF | `403` under cookie session/CSRF policy. |
| Locked user attempts login | Authentication rejected even with right password. |
| Replay Cookie A after lock | Denied. |
| Replay Cookie A after unlock | Still denied (no resurrection). |
| Replay Cookie D after password change | Denied. |
| Logout E while F remains active | F succeeds per logout-current semantics. |
| Logout all Alice | All Alice sessions denied, Bob untouched. |
| Session deleted server-side while browser replays old cookie | Authenticated context not restored. |
| `SessionRegistry.expireNow()` | Verify filter blocks next request / cross-node. |
| Old JWT after lock | Matches defined epoch/denylist/TTL SLA, never assumed revoked automatically. |
| Retrying logout-all twice | Grants no privileges and restores no sessions. |
| Node 2 stale cache after lock | High-risk APIs deny within SLA. |
| Cleanup queue down | State gate still denies; events retry/reconcile. |
| Admin tries locking user in another tenant | Forbidden, zero side effects. |
| Account logs in via OIDC with no local password | Local password change workflow rejected cleanly. |
| Logs / audits / metrics | Zero cookies, OTPs, passwords, raw JWTs, or session IDs. |

For POSTs, distinguish `403` from missing CSRF vs. `403` from missing roles: supply valid CSRF when testing authorization, and test missing/invalid CSRF separately.

## 21. Comprehensive CI Test Plan

1. **State machine unit tests:** lock/unlock, monotonic epoch, password-change preconditions, logout current/all idempotency.
2. **Servlet security integration:** `@SpringBootTest` + `@AutoConfigureMockMvc`; real form logins, sessions A/B/C, negative paths.
3. **Persistence integration:** DB transactions, account row locking, outbox commit/retry, and expected hash/state.
4. **Shared session integration:** Spring Session Redis/JDBC principal index, cookie replay after `deleteById`.
5. **Multi-node:** Node 1/2 sharing account/session state, load-balancer routing, cache invalidation.
6. **OAuth/IdP contracts:** refresh revocation, stale JWTs, OIDC local RP sessions, remember-me/MFA proofs if present.
7. **Concurrency/TOCTOU:** requests starting before lock and committing after lock produce no high-risk side effects.
8. **Operational/privacy:** secret-free audits, revocation SLA metrics, chaos tests for queue/store outages.

**Acceptance bar:** HTTP/protected-resource proof that **old sessions** are rejected after lock/change/logout-all; Bob's sessions remain untouched; new logins obey updated status/passwords. Tests asserting only a DB flag or a `200` mutation response are **insufficient**.

## 22. Auditing, Metrics, and Protecting Sensitive Data

A standardized audit event might look like:

~~~json
{
  "eventId": "evt-901",
  "eventType": "ACCOUNT_LOCKED",
  "actorUserId": "security-admin",
  "subjectUserId": "usr-1001",
  "securityEpoch": 7,
  "occurredAt": "2026-11-06T09:00:00Z",
  "correlationId": "req-8fa",
  "cleanupState": "PENDING"
}
~~~

This schema is **application-defined**, not emitted automatically by Spring Security. `cleanupState` must reflect confirmations from cleanup services. Never log raw current/new passwords, password hashes, bearer/refresh tokens, session cookies, raw OTPs/recovery codes, `Authorization` headers, or full `SecurityContext` objects.

Suggested metrics:

~~~text
account_lock_total
account_unlock_total
password_change_success_total
password_change_failure_total
logout_current_total
logout_all_total
stale_session_rejected_total
session_revocation_success_total
session_revocation_lag_seconds
session_reconciliation_discrepancy_total
~~~

Never put user IDs, session IDs, emails, or tokens into high-cardinality metric labels. Store actor/subject refs in an access-controlled, encrypted audit store with proper retention.

**Measure revocation SLA from account-update commit until old requests are rejected at real resources**, not merely until the cleanup event is enqueued.

## 23. Common Mistakes and Fixes

**Mistake 1: only setting `account.locked=true`.** Old sessions may retain `SecurityContext`. Test A/B replay and enforce gates/cleanup.

**Mistake 2: only updating the password hash.** Old cookies, remember-me tokens, and refresh grants do not automatically revoke. Build event/epoch policies matching credential scopes.

**Mistake 3: using `SecurityContextHolder.clearContext()` for logout-all.** Clears only the current thread's context. Use a shared session index and/or epoch guard.

**Mistake 4: assuming `SessionRegistry.expireNow()` deletes every `HttpSession` immediately.** It may only mark entries expired, requiring filter checks and cross-node strategies.

**Mistake 5: forgetting the principal index.** `findByPrincipalName` returns empty if the index is unpopulated or keyed by a different username. Test indexing with two real sessions.

**Mistake 6: letting unlock resurrect old sessions.** Never decrement the epoch and never rely solely on the locked flag.

**Mistake 7: testing with `@WithMockUser`.** Skips login/providers and creates no two real browser sessions. Use real form/Basic/custom filters.

**Mistake 8: reusing an invalidated `MockHttpSession` expecting 401.** Can throw from the mock; run HTTP cookie replay tests against a real server/session store.

**Mistake 9: logout-all accidentally sweeping Bob.** Key by stable internal user ID with clear tenant boundaries and isolation tests.

**Mistake 10: treating a valid JWT signature as proof the account is active.** Enforce TTL/epoch/denylist/introspection per SLA.

**Mistake 11: relying solely on async events to block access.** Event lag creates an exposure window; use an authoritative state gate.

**Mistake 12: allowing a request started before lock to commit sensitive actions after lock.** Re-verify at transaction/business boundaries.

**Mistake 13: disabling CSRF to turn logout/password-change POST tests green.** Protect state-changing endpoints and separate role vs. CSRF tests.

**Mistake 14: logging full `Authentication` or raw session IDs for debugging.** Enables session hijacking; log correlation IDs and redacted metadata.

## 24. Pre-Production Checklist

- [ ] Policy explicitly states whether locking blocks only new logins or all existing sessions.
- [ ] Login manager/provider checks `isAccountNonLocked`/`isEnabled` against authoritative state.
- [ ] Account security epoch is monotonic and commits before reporting revocation success.
- [ ] Sensitive session-backed requests verify current account status/epoch or confirmed server-side session deletion.
- [ ] Unlocking never revives prior-epoch sessions or tokens.
- [ ] Password change validates old credentials, new-password policy, and CSRF/reauth/MFA where needed.
- [ ] Password hashes are managed with an appropriate `PasswordEncoder`.
- [ ] Password change bumps epoch and handles current/other sessions and grants per policy.
- [ ] Logout current destroys the server-side session rather than merely clearing browser cookies.
- [ ] Logout all works cross-node via principal index/epoch gate without affecting other users.
- [ ] Spring Session principal indexing has a stable contract tested across multiple nodes.
- [ ] If using `SessionRegistry.expireNow`, filter/registry behavior is verified across nodes.
- [ ] JWT access, refresh tokens, remember-me, API keys, MFA proofs, and SSO are handled separately where present.
- [ ] Request concurrency, cache staleness, and TOCTOU are tested and bounded.
- [ ] Outbox/retry/reconciliation have explicit auditing and revocation SLAs.
- [ ] Zero sensitive credentials appear in logs, metrics, or notifications.
- [ ] Negative tests run in CI alongside positive tests.
- [ ] Runbooks exist for emergency lock, reset, logout all, unlock, and security notifications.

## 25. Summary

**Account locking, password changes, and multi-session logout share one invariant: prior authentication evidence must lose validity at the right scope and commit point.** In Spring Security, `UserDetails` flags block new logins yet do not destroy `SecurityContext` objects already saved in `HttpSession`. Nor does a new password hash revoke bearer JWTs or refresh grants.

A dependable design is:

**Commit account state/password hash + bump security epoch → enforce on the request path → clean up sessions/tokens via shared repositories → audit/reconcile → test replay across multiple devices and nodes.**

Only when system tests prove A/B are blocked after lock or password change, E is blocked after logout-current while F stays active, F is blocked after logout-all, and Bob's C remains unaffected do you have real proof across the functional boundary.

## References

- [Spring Security — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html): `SecurityContextRepository`, concurrent sessions, and `SessionRegistry`.
- [Spring Security — Logout](https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html): session invalidation, logout handlers, and CSRF.
- [Spring Security — UserDetails](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/user-details.html): account status checks and `DaoAuthenticationProvider`.
- [Spring Security — Password Storage](https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html): `PasswordEncoder`.
- [Spring Security — MockMvc Setup](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/setup.html): Servlet security test filter chain.
- [Spring Security — MockMvc Authentication](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authentication.html): `formLogin`/`user` mock semantics.
- [Spring Session — API](https://docs.spring.io/spring-session/reference/api.html): `FindByIndexNameSessionRepository` and principal index.
- [Spring Session — Redis Guide](https://docs.spring.io/spring-session/reference/guides/boot-redis.html): shared sessions across instances.
- [RFC 7009 — OAuth2 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009.html): revocation of OAuth grants/tokens.
- [RFC 7662 — OAuth2 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662.html): opaque token active state.
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): session lifecycle, revocation, and security events.
- [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): password changes and account management.
- [OWASP — Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html): recovery and invalidating existing sessions.
