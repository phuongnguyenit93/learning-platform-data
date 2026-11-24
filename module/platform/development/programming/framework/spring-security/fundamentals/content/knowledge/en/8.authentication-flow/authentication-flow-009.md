# Erasing Credentials After Authentication and Limiting Sensitive Data Lifetimes

Mai logs into a Spring Security application using a username and password. To verify Mai, the program must briefly receive the password, pass it to the authentication component, and compare it against the stored password hash. Yet **once authentication finishes, does the program still need to keep that password inside `Authentication`, `SecurityContext`, or the session?**

In most password-based login flows, the answer is **no**. Keeping a raw password longer than necessary increases damage during accidental logging, heap dumps, session serialization, authorization bugs, or when an object is inadvertently passed to another layer. Spring Security provides cleanup mechanisms involving `ProviderManager`, `CredentialsContainer`, and `eraseCredentials()` to shorten how long references to spent secrets live.

However, understand the exact limitation: **erasing credentials from a Java object does not mean every copy of that data has vanished from RAM**. An immutable `String`, copies in the request, logs, caches, tokens, or other memory regions may still exist. That is why this lesson combines **framework mechanisms** with **sensitive-data lifecycle design from receipt to disposal**.

Objectives: after this lesson, you can distinguish raw credentials from password hashes and identities, know when Spring Security invokes `eraseCredentials()`, avoid `UserDetails` caching bugs, handle custom authentication safely, and run a standalone Java 17+ example observing credentials before/after authentication.

## 1. What Are Credentials? Not Every Field in Authentication Should Be Erased

In Spring Security, `Authentication` represents **an authentication request** or **an authenticated identity**. Common fields:

| Component | Role | Examples | Should it be kept after authentication? |
| --- | --- | --- | --- |
| `principal` | Who is being identified | `UserDetails`, username, JWT, custom principal | Keep **only the minimal necessary identifier**; omit unnecessary secrets |
| `credentials` | Evidence used to prove identity | Password, bearer token, assertion | Usually **do not keep raw secrets** after verification; check mechanism needs |
| `authorities` | Permissions granted to the principal by the provider | `ROLE_USER`, `DOC_READ` | May be needed for authorization, yet still handle revoked permissions |
| `details` | Mechanism/request-specific metadata | IP, session ID, or device info if configured | Retain only data with a clear purpose, minimizing privacy exposure |
| `isAuthenticated()` | State of the authentication result | `true` after provider trusts the evidence | Not credentials; does not by itself prove permission on individual resources |

**Credentials** are what is presented to prove the right to use an identity. With form login, that is typically the *raw password* just entered. With a JWT Resource Server, the bearer token serves as the request's evidence; with OAuth2/OIDC, there may also be authorization codes, refresh tokens, client secrets, or assertions depending on the flow. With MFA, there may be OTPs or recovery codes.

**Never conflate these three things:**

- **Raw password:** secret just supplied by the user; should live very briefly during request/authentication processing.
- **Stored password hash:** data used to verify passwords later; must persist durably in a protected credential store. Hashes remain sensitive and must not leak to clients/logs.
- **Authenticated identity:** ID and permissions needed to identify the caller in the current request or session; in principle, it does not need the raw password.

When `UserDetails` exposes `getPassword()`, it is normally the **stored hash**, not the raw password. Spring Security clearing the password field from **the `UserDetails` instance on the principal** does not mean deleting the hash from the database. Distinguishing these is crucial when reading code and debugging.

## 2. Desired Password Lifecycle During a Single Login

Picture a servlet flow using username/password:

~~~text
1. Browser sends POST /login over HTTPS
        username + raw password
                  |
                  v
2. UsernamePasswordAuthenticationFilter
        creates unauthenticated Authentication request
        principal=username, credentials=raw password
                  |
                  v
3. AuthenticationManager (usually ProviderManager)
        invokes matching AuthenticationProvider
                  |
                  v
4. DaoAuthenticationProvider
        UserDetailsService loads user + password hash
        PasswordEncoder.matches(raw password, hash)
                  |
            match | mismatch
                  |------------------------------------+
                  v                                    |
5. Authentication succeeds                           |
        principal + authorities                        |
        credentials may still exist briefly            |
                  |                                    v
                  v                         AuthenticationException
6. ProviderManager erases credentials           error handling/cleanup
        if returned Authentication supports
        CredentialsContainer
                  |
                  v
7. Filter handles SecurityContext / session
        retains identity + appropriate permissions
        no raw password needed
                  |
                  v
8. Controller/service performs authorization
        uses only ID/permissions, never password
~~~

**Important point about timing:** `ProviderManager` credential cleanup occurs after a provider authenticates **successfully** and returns an `Authentication`. Never assume that data in the **initial request**, copies in the servlet request body, logs, or objects referenced elsewhere are also automatically wiped.

A custom controller calling `AuthenticationManager` directly is responsible for managing its own input. A custom provider must also decide what the result object contains. Never think merely enabling Spring Security automatically scrubs every memory region containing passwords.

## 3. Default Mechanism of ProviderManager

In Spring Security Servlet, `AuthenticationManager` has the contract:

~~~java
Authentication authenticate(Authentication authentication)
        throws AuthenticationException;
~~~

The standard implementation is `ProviderManager`, coordinating one or more `AuthenticationProvider` instances.

When a provider returns a successful result, `ProviderManager` **by default attempts to erase credentials** from the resulting `Authentication` if it implements `CredentialsContainer`. Corresponding configuration:

~~~java
// Fragment when you construct ProviderManager yourself.
ProviderManager manager = new ProviderManager(provider);

boolean enabled = manager.isEraseCredentialsAfterAuthentication();
// Defaults to true.
~~~

The library provides the property:

~~~java
manager.setEraseCredentialsAfterAuthentication(false);
~~~

**This shows the switch exists, NOT a recommendation to turn it off.** Disabling credential cleanup can leave raw passwords or other secrets inside `Authentication`/sessions longer than necessary. Consider it only after understanding the technical cause, risks, data lifecycle, and having an equivalent safeguard; for normal applications, keep the default.

Conceptually, the post-authentication step resembles:

~~~java
// Pseudocode illustrating behavior; DO NOT copy to replace ProviderManager.
Authentication result = provider.authenticate(input);

if (result != null && eraseAfterAuthentication
        && result instanceof CredentialsContainer container) {
    container.eraseCredentials();
}

return result;
~~~

Note that this pseudocode does not depict trying multiple providers, parent managers, exceptions, and events; it only illustrates **which object is cleaned** and **when**.

After the provider returns a successful result, the filter handles putting `Authentication` into `SecurityContext` and saving/restoring context per the configured mechanism. When the result holds fewer secrets, the risk of exposure via sessions/serialization drops.

### Why is this mechanism valuable?

If a `UsernamePasswordAuthenticationToken` still carried the raw password and the app stored it in session, the secret could survive until session expiration or accidentally appear in caches, debug output, or crash dumps. Erasing credentials before retaining `Authentication` long-term shrinks that exposure surface.

Still, cleanup depends on **the returned `Authentication` type** and whether `eraseCredentials()` is properly implemented. Not every custom object knows how to clear secrets inside it automatically.

## 4. CredentialsContainer and the eraseCredentials() Method

The interface lives at:

~~~java
org.springframework.security.core.CredentialsContainer
~~~

The contract is tiny:

~~~java
public interface CredentialsContainer {
    void eraseCredentials();
}
~~~

This is a simplified signature for study. The interface signals that an object carries sensitive data needing release, and `eraseCredentials()` is where that happens.

Familiar Spring Security classes implementing this interface include:

- `UsernamePasswordAuthenticationToken`.
- `AbstractAuthenticationToken` and many subclasses.
- `org.springframework.security.core.userdetails.User`.
- Various mechanism-specific tokens/authentication objects, depending on version.

Invocation **cascades**: `AbstractAuthenticationToken.eraseCredentials()` inspects `credentials`, `principal`, and `details`; if a child object implements `CredentialsContainer`, it invokes `eraseCredentials()` on that child. `UsernamePasswordAuthenticationToken` also clears its reference to the token's own credentials field.

An `Authentication` might look like:

~~~text
UsernamePasswordAuthenticationToken
  principal = UserDetails(User)
    username = "mai"
    password = "{bcrypt}..."
    authorities = [ROLE_USER]
  credentials = "raw-password-just-entered"
  details = WebAuthenticationDetails(...)
~~~

After the result token is cleaned appropriately:

~~~text
UsernamePasswordAuthenticationToken
  principal = UserDetails(User)
    username = "mai"
    password = null
    authorities = [ROLE_USER]
  credentials = null
  details = non-sensitive info or managed metadata
~~~

This is an **example for Spring Security's `User` type**, not a promise that every `UserDetails` will have `password=null`. A custom `UserDetails` implementing only `UserDetails` without `CredentialsContainer` can continue holding the hash inside the principal even after the token clears `credentials`.

### Important: eraseCredentials does not erase every field

`eraseCredentials()` is **not a command to wipe the entire principal or authorities**. Identity and permissions are still needed for downstream calls. Nor does it automatically wipe `details` unless that object implements the matching erasure contract.

Therefore, if a custom principal holds `String accessToken`, `String otp`, or `String passwordHash` without implementing cleanup, the secret can remain. Proactively minimize data stored in principals rather than relying on a method name.

## 5. Runnable Java 17+ Example: Observing Credential Erasure After Authentication

This standalone example uses real Spring Security classes. The goal is not building a website, but **observing the `ProviderManager.authenticate` result** with username/password.

The program verifies:

1. `ProviderManager` enables credential cleanup by default.
2. Authenticating with a valid password returns `authenticated=true`.
3. `Authentication.getCredentials()` on the **result** becomes `null`.
4. `UserDetails.getPassword()` on a `User` principal also becomes `null`.
5. The original request token is cleaned separately in `finally`.
6. The next login still succeeds because `UserDetailsService` builds **a fresh object each time**, never reusing a cleared principal.

### 5.1. Create Gradle project

Structure:

~~~text
credential-lifetime-demo/
  build.gradle
  src/main/java/CredentialLifetimeDemo.java
~~~

Create `build.gradle`:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.security:spring-security-core:7.1.2'
    implementation 'org.springframework.security:spring-security-crypto:7.1.2'
}

application {
    mainClass = 'CredentialLifetimeDemo'
}
~~~

The example pins the same released stable Spring Security version for easy standalone practice; Java 17+ is required. In real Spring Boot projects, use `spring-boot-starter-security` and let the Spring Boot BOM manage Security versions instead of copying individual version lines.

### 5.2. Complete Java file

Create `src/main/java/CredentialLifetimeDemo.java`:

~~~java
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

public class CredentialLifetimeDemo {

    public static void main(String[] args) {
        PasswordEncoder encoder = new BCryptPasswordEncoder();

        // Demo-only dummy password; never use in real production.
        String storedHash = encoder.encode("demo-password");

        // Create a NEW UserDetails for each call; never reuse a
        // User object whose eraseCredentials() ran in an earlier login.
        UserDetailsService users = username -> {
            if (!"mai".equals(username)) {
                throw new UsernameNotFoundException("Unknown username");
            }
            return User.withUsername("mai")
                    .password(storedHash)
                    .roles("USER")
                    .build();
        };

        DaoAuthenticationProvider provider =
                new DaoAuthenticationProvider(users);
        provider.setPasswordEncoder(encoder);

        ProviderManager manager = new ProviderManager(provider);
        System.out.println("erase-enabled="
                + manager.isEraseCredentialsAfterAuthentication());

        UsernamePasswordAuthenticationToken firstInput =
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "mai", "demo-password");

        Authentication firstResult;
        try {
            firstResult = manager.authenticate(firstInput);
        } finally {
            // Manager cleans the RESULT; caller handles the INPUT it holds.
            firstInput.eraseCredentials();
        }

        UserDetails firstPrincipal =
                (UserDetails) firstResult.getPrincipal();

        System.out.println("first-authenticated="
                + firstResult.isAuthenticated());
        System.out.println("result-credentials-empty="
                + (firstResult.getCredentials() == null));
        System.out.println("principal-password-empty="
                + (firstPrincipal.getPassword() == null));
        System.out.println("input-credentials-empty="
                + (firstInput.getCredentials() == null));

        UsernamePasswordAuthenticationToken secondInput =
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "mai", "demo-password");
        try {
            Authentication second = manager.authenticate(secondInput);
            System.out.println("second-authenticated="
                    + second.isAuthenticated());
        } finally {
            secondInput.eraseCredentials();
        }
    }
}
~~~

With JDK 17+ and a compatible Gradle version, from the directory containing `build.gradle`, run:

~~~bash
java -version
gradle run --quiet
~~~

Output produced by the `println` statements themselves:

~~~text
erase-enabled=true
first-authenticated=true
result-credentials-empty=true
principal-password-empty=true
input-credentials-empty=true
second-authenticated=true
~~~

**This output is deducible directly from the APIs used**, independent of random bcrypt strings, so no specific hash value is printed. The program cleanly separates input, result, and principal objects.

Explanation:

- `DaoAuthenticationProvider` uses `PasswordEncoder.matches` to check the password against `storedHash`.
- `ProviderManager` receives the successful `Authentication` and calls credential cleanup on the **result** by default.
- `UsernamePasswordAuthenticationToken` drops the reference to raw credentials in the result; the principal is `User`, so `User.eraseCredentials()` drops the reference to the password hash on the principal.
- `firstInput` is a different object, and the application explicitly calls `eraseCredentials()` in `finally`.
- `storedHash` remains in the source variable serving as the verification store (simulating a repository). The next login loads a fresh `User` from it and continues to succeed.

**Important limitation:** the demo password is a `String` literal inside a Java class. Calling `eraseCredentials()` clears **the chosen object's references**, without guaranteeing the bytes/characters forming the `String` are wiped from every memory area. In production, never hardcode passwords; use HTTPS, proper data stores, and secure secret handling.

### 5.3. Why not reuse the exact same User object?

If you write a `UserDetailsService` like this, you can hit a bug:

~~~java
// PROBLEMATIC EXAMPLE WHEN REUSING THE SAME OBJECT:
UserDetails oneSharedUser = User.withUsername("mai")
        .password(storedHash)
        .roles("USER")
        .build();

UserDetailsService users = username -> oneSharedUser;
~~~

After the first successful login, `ProviderManager` can cause the password inside `oneSharedUser` to be cleared via the shared reference. On the next login, the provider needs the hash to check yet receives an already-mutated object. This can make authentication fail or raise errors depending on implementation.

In the runnable example above, `users` returns **a fresh `User`** every time. Distinguish carefully:

~~~text
CORRECT OBJECT BOUNDARIES:
  Store holds durable password hash
          |
  Each login creates a fresh UserDetails copy
          |
  ProviderManager erases on the fresh copy principal
          |
  Store remains unmodified

AT RISK:
  Cache holds a shared UserDetails instance
          |
  Login retrieves that exact instance
          |
  Result principal holds the same reference
          |
  ProviderManager erases -> cache gets mutated too
          |
  Next login has no password hash left to check
~~~

That is an **ownership/reference conflation bug** between an object meant to be disposable and an object meant to persist for future verifications. It is not evidence that you should turn off secret erasure; the fix is separating short-lived objects from cached/persisted data serving a different purpose.

## 6. Caching UserDetails: Where Credential Erasure Bugs Usually Surface

Large applications may cache users to reduce database queries. This scenario deserves attention because Spring Security's `User` is **mutable** and implements `CredentialsContainer`.

Example:

~~~text
cache["mai"] -> User(username="mai", password="{bcrypt}...", ...)
                       |
                       +--- UserDetailsService returns same object
                                   |
                                   v
                             Authentication principal
                                   |
                                   v
                        ProviderManager.eraseCredentials()
                                   |
                                   v
cache["mai"].password == null  (due to shared object reference)
~~~

The consequence can be: the first login succeeds, while the second login fails even when the user enters the right password. Whether it breaks immediately or after a TTL depends on the cache implementation and authentication flow.

Sound solutions:

1. **Fetch from repository and build a fresh UserDetails copy** per authentication when performance allows. The section 5 demo uses this approach.
2. **If using a cache, return an isolated copy** separate from the cached object, copying verification data safely; the object placed into `Authentication` can be erased without mutating the cache.
3. With a custom `AuthenticationProvider`, **build an authenticated result holding only ID/authorities**, without referencing the cached `UserDetails` carrying the password hash. Input credential cleanup still needs attention.
4. If design demands a different lifetime, carefully evaluate using `setEraseCredentialsAfterAuthentication(false)`. This trades off keeping secrets in memory longer and **should not be the default fix** for shared caches.

When using `User.withUserDetails(existing)`, verify whether the new object and nested components are actually copied safely; do not mistake a shallow wrapper copy for a deep copy of all sensitive objects.

### Is caching password hashes completely safe?

No. A password hash is verification material and remains sensitive if the cache is read without authorization, debugged, or dumped. Enforce access controls, transport/storage encryption where appropriate, TTLs, and cache lifecycle rules. Having a cache never permits putting raw password hashes into sessions or API responses.

You can maintain a separate cache for profiles and authorities **without hashes**, while password authentication queries a dedicated credential store. Specific architecture depends on load, SLA, and security, yet keep clear where **hashes are needed for verification** and where **only identity is needed**.

## 7. Custom UserDetails: How to Implement CredentialsContainer?

If a project defines a custom `UserDetails` class holding a password hash, consider implementing `CredentialsContainer` to clear the field on the instance used for authentication.

Snippet illustrating the relevant part (other `UserDetails` methods must be implemented in the real class):

~~~java
import org.springframework.security.core.CredentialsContainer;
import org.springframework.security.core.userdetails.UserDetails;

public final class AccountUserDetails
        implements UserDetails, CredentialsContainer {

    private String passwordHash;
    // Other fields: username, authorities, status...

    @Override
    public String getPassword() {
        return passwordHash;
    }

    @Override
    public void eraseCredentials() {
        passwordHash = null;
    }

    // Implement the remaining UserDetails methods in a real class.
}
~~~

**This is a fragment for understanding the interface, not a standalone compilable class.** In production apps, fulfill the full `UserDetails` contract, avoid printing hashes in `toString()`, and avoid using cached or JPA-managed entities directly as principals.

Because `CredentialsContainer` targets mutable/cleanable objects, an immutable Java `record` holding `String passwordHash` is usually unsuitable if you expect `eraseCredentials()` to mutate that field. Better yet, **omit secrets from the authenticated principal altogether**, or use structures with clean ownership/cleanup at authentication time.

If a custom principal has nested objects that also carry secrets, check whether they need their own cleanup. `AbstractAuthenticationToken` invokes `eraseCredentials()` on nested objects **only if they also implement the interface**; it does not reflectively scan arbitrary fields in classes you write.

### Avoid creating authenticated objects before verification

A custom provider can create a minimal result once verified:

~~~java
// Fragment inside AuthenticationProvider, ONLY after verifying
// password/certificate/token against a trusted source.
return UsernamePasswordAuthenticationToken.authenticated(
        new AccountPrincipal(accountId), // custom identity, holds no password
        null,                            // no raw credentials needed
        authorities                     // verified permissions
);
~~~

`AccountPrincipal`, `accountId`, and `authorities` in the fragment are application-supplied types/data. When writing a custom provider, **prefer returning an `Authentication` containing no secrets from the outset** rather than relying on `CredentialsContainer` to compensate for holding excessive data.

Never construct an `authenticated(...)` token from a client-supplied username/role before verification, as that marks a trusted identity before performing security checks.

## 8. Clearing References Differs from True Zeroization

The name `eraseCredentials()` can be misleading. In Java/JVM there are at least three levels:

| Handling approach | What actually happens | Limitation |
| --- | --- | --- |
| Setting `credentials=null` | Object no longer holds that reference | Other objects may still hold the same secret |
| Clearing `char[]`/`byte[]` elements owned by the app | Overwrites an array you control | Does not wipe other copies; runtime/compiler optimizations may exist |
| Garbage collection | JVM may reclaim unreferenced object memory | No guarantee data is physically overwritten immediately |

Java `String` is **immutable**. If a raw password is created as a `String` in a controller, setting `password = null` cannot guarantee its character data is overwritten. The JVM may retain other copies in request buffers, logs, profilers, thread dumps, or other components.

A pure JDK 17 pattern for clearing an app-owned array:

~~~java
char[] password = obtainPasswordFromTrustedInput();
try {
    verifyWithoutCreatingUnnecessaryCopies(password);
} finally {
    java.util.Arrays.fill(password, '\0');
}
~~~

This is a **fragment about array ownership**, with two application-defined methods; it is not a Spring `PasswordEncoder` example (`encode`/`matches` APIs typically take `CharSequence`). Never equate zero-filling one array with having wiped all copies from the heap.

In practice, Servlet form params and many APIs handle passwords as `String`, so raw password residence time cannot be eliminated entirely. The useful strategy is **minimizing copies, avoiding long retention, keeping secrets out of logs/caches/sessions, clearing references you own, and restricting unauthorized memory capture**.

### A practical rule: secrets are short-lived, yet hashes must persist

Do not try to delete the password hash from the **database** after each login; it is needed for future verifications. Distinguish the canonical record in the credential store from the copy loaded into `UserDetails`/principal that can be cleared after authentication.

When you need to change a password, run a **change/reset workflow** and update the new hash; `eraseCredentials()` does not replace `PasswordEncoder.encode(...)`, password rotation, or token revocation.

## 9. Difference Between Erasing Credentials and Clearing SecurityContext

In Servlet, Spring Security typically manages `SecurityContextHolder` via `ThreadLocal` for the request and clears the context when the request ends. Two different operations exist:

- `Authentication.eraseCredentials()` (via `CredentialsContainer`): clears secret fields on participating objects.
- `SecurityContextHolder.clearContext()`: removes the `SecurityContext` bound to the current thread, preventing identity leakage into another task/request reusing that thread.

Both matter, yet **they are not interchangeable**.

Example when writing custom code running on a thread and manually setting context:

~~~java
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authenticatedResult);
try {
    SecurityContextHolder.setContext(context);
    runTaskAsAuthenticatedPrincipal();
} finally {
    SecurityContextHolder.clearContext();
}
~~~

This is a fragment requiring imports and an implementation of `runTaskAsAuthenticatedPrincipal`. In standard Spring Security web flows, framework filters handle setting/clearing the context; do not insert your own cleanup that wipes Authentication mid-request without understanding the lifecycle.

**`clearContext()` does not delete server sessions, revoke JWTs, clear browser cookies, or wipe password hashes.** It primarily affects the thread-bound context. Logout and session/token revocation are separate concerns handled independently.

### Sessions and SecurityContextRepository

In stateful apps, `SecurityContext` can be saved to and restored from the HTTP session via `SecurityContextRepository`. Thus ensure the post-login result has a **minimal principal, erased credentials, and secret-free `details`** before longer-term persistence.

In stateless apps, each request may carry a bearer token itself. There is **no password-login session to clear** there, yet tokens and their copies in requests/logs/contexts still need protection. Never infer that `eraseCredentialsAfterAuthentication=true` automatically invalidates bearer tokens or deletes client access tokens.

### Other threads and asynchronous work

`SecurityContextHolder` defaults to `ThreadLocal`. When spawning threads, running `@Async`, using executors, or running message consumers, the security context may not automatically be present or cleared where expected. Use propagation mechanisms provided by Spring Security (such as delegating security context wrappers) when identity genuinely must be propagated.

Never copy entire requests, passwords, or secret-bearing `Authentication` objects into async queues/jobs. Pass **business-appropriate IDs and permissions**, or explicitly designed authorization claims. Background jobs need their own authorization policies and must never hold raw request passwords.

## 10. Sensitive Information Is More Than Just Passwords

`eraseCredentials()` is an object cleanup mechanism, yet system protection strategies must cover many kinds of secrets:

| Data | When needed | Reasonable lifetime | Risk if kept too long |
| --- | --- | --- | --- |
| Login raw password | Verification against hash during login request | Never persist durably; drop references as soon as possible | Exposure in logs, heap dumps, sessions |
| Password hash | Verifying newly entered passwords | Keep in controlled credential store; copies on principals can be cleared | Offline password guessing if hash leaks |
| OTP/TOTP code | Verifying second factor | Use only within short policy window; never log | Replay/code guessing while valid |
| Recovery code | Recovery when losing an auth factor | Single-use per code and securely stored | Account takeover by unauthorized party |
| Password reset token | Verifying right to reset password | Short-lived, single-use, invalidated after use | Unauthorized password reset takeover |
| OAuth authorization code + PKCE verifier | Completing code exchange | Use in flow then discard extra copies | Unintended code interception/exchange |
| Access token / JWT | Proving API permissions until expiry | Matching TTL and management/revocation mechanisms | Replay if stolen |
| Refresh token | Requesting new access tokens | Store in protected location, rotate/revoke as appropriate | Prolonged access if leaked |
| Session ID/cookie | Binding requests to authenticated session | Protected cookies, timeouts, logout/invalidation | Session hijacking if stolen |
| Client secret/API key/private key | App/machine authentication or signing | Dedicated secret store, access controls/rotation | Broad resource compromise |

Not every piece of data should be deleted after **one** request: refresh tokens or session identifiers have longer legitimate lifetimes. What matters is **retaining them only for the right purpose, in the right store, for the right duration**, avoiding dumping them arbitrarily into principals or logs.

A JWT cannot be revoked merely by setting `authentication.getCredentials()=null` on the server, because the client still holds the original token. For tokens needing fast revocation, design TTLs, denylists, token versions, session binding, or introspection per architecture.

## 11. Places Where Secrets Are Easily Copied by Accident

A login flow can cross many layers:

~~~text
HTTPS request
  -> reverse proxy / WAF
  -> access log / request tracing
  -> Servlet request
  -> Filter / controller
  -> Authentication token
  -> Authentication provider
  -> UserDetails / database
  -> success/failure handler
  -> session / cache / audit / telemetry
~~~

At each boundary, ask: **do we truly need username, password, authorization header, cookie, or token inside this object?** If not, strip it from the payload immediately.

Common mistakes:

1. Letting a reverse proxy or APM record the **request body of `POST /login`**.
2. Writing `log.debug("auth={}", authentication)` without knowing what `toString()`/custom principals may emit.
3. Writing `Authorization: Bearer ...` or `Cookie: JSESSIONID=...` into logs while debugging.
4. Returning `exception.getMessage()` straight from an API when the exception contains raw credentials or storage details.
5. Putting raw login DTOs into message queues, caches, audit events, or retry payloads.
6. Building an `AccountPrincipal` holding password hashes, refresh tokens, or full JPA entities and serializing it into session.
7. Storing OTP/reset tokens in browser local storage, analytics URLs, or unintended referrers.
8. Creating an audit table with a `request_json` column storing unfiltered login payloads.
9. Adding an interceptor that "captures every HTTP request" without redaction rules.
10. Putting secrets into URL query parameters; URLs can enter history, access logs, or analytics systems.

Even with `ProviderManager` clearing credentials by default, logging a secret **before** the provider returns has already leaked it. Credential erasure is therefore **one mitigation layer**, not a substitute for controls at other layers.

### When logs are needed for investigation, what should be kept?

Log less-sensitive fields: request ID, timestamp, auth mechanism type, success/failure outcome, error category, service name, latency, and sanitized actor/account IDs per policy. Avoid raw usernames/emails as metric labels if they constitute personal data or high cardinality.

For exceptions, exception classes and stack traces can go to **restricted-access operational channels** after redacting sensitive data. Public responses must contain no stack traces, SQL, or provider configuration.

## 12. What Happens When Login Fails?

`ProviderManager`'s default mechanism clears credentials on the **successful result Authentication**, so you **must never assume** raw credentials in the input vanished when authentication failed.

A custom controller calling the manager directly can write:

~~~java
// Fragment in web/service layer with an available authenticationManager.
// username/password obtained from the request via the chosen mechanism.
UsernamePasswordAuthenticationToken input =
        UsernamePasswordAuthenticationToken.unauthenticated(
                username, password);

try {
    Authentication result = authenticationManager.authenticate(input);
    // Continue standard success flow, DO NOT put raw input into session.
    return result;
} finally {
    input.eraseCredentials(); // Runs even if authenticate() throws an exception.
}
~~~

This cleans the input object owned by the code. It **does not guarantee** external `password` variables or request bodies holding raw `String`s are scrubbed from RAM. If `password` is a local String, limit its scope and avoid extra copies.

Nor should you catch `AuthenticationException` and return an empty successful `Authentication` to "avoid interrupting service". When evidence is unverified, **fail closed**. When the user store is unavailable, distinguish `AuthenticationServiceException` from `BadCredentialsException` internally; clean secrets in both scenarios.

### Multi-step login (MFA) needs its own lifecycle

If the password step succeeds yet OTP/MFA remains, the system can hold a **challenge state** and temporary identifier. That state must not hold the raw password "waiting for step 2", and must not be marked fully privileged before completing verification per policy.

OTP codes, recovery codes, WebAuthn challenges, and bearer tokens require dedicated lifetimes, one-time use, and protection. An `Authentication` result with `credentials=null` does not by itself guarantee MFA has completed.

## 13. When Should Credentials Not Be Kept in Authentication?

Some practical design decisions:

| Requirement | Approach to consider |
| --- | --- |
| Controller needs to know "who is calling?" | Use `Authentication.getName()` or principal ID; no raw password needed |
| Service wants role-based authorization | Use `getAuthorities()` combined with resource-level authorization; never read passwords |
| Profile screen needs current display name/email | Query business source/DTO with proper permissions; do not copy full entities with passwordHash into principal |
| Need to re-verify sensitive actions | Use a dedicated **reauthentication** or step-up flow; never keep the old password in session |
| Need to contact IdP after login | Use protected token management; do not stuff refresh tokens into every `Authentication`'s details |
| Need to change password | Verify old password/step-up per policy and `encode` the new password; never retrieve raw passwords from session |
| Need to handle login errors | Use failure handlers/entry points; never put exceptions/requests containing secrets into logs |
| Caching users to reduce DB load | Design copies and lifetimes separately; never let mutable principals corrupt cache |

**Storing passwords "to reuse later when needed" is almost always an architectural smell.** If an action needs fresh proof, request fresh proof, or use a dedicated credential/token designed to authorize that action.

## 14. Testing Credential Erasure Properly

You can test at three distinct layers:

**A. AuthenticationManager unit/integration:** after a valid login, the result is authenticated while `getCredentials()==null`; if the principal is `User`, its password is also null. This is exactly what the Gradle example above tests.

**B. Repeated logins and caching:** call `authenticate` twice. If the first login clears the password hash inside a cached `UserDetails`, the second login easily fails. Verify repositories/caches remain unmutated when the result principal is erased.

**C. HTTP/request/session/logging:** test real form/Basic logins; confirm sessions contain no raw passwords, request-body logging is redacted, API errors leak no secrets, and failed requests do not keep sensitive objects alive unexpectedly.

Test matrix:

| Scenario | Expectation |
| --- | --- |
| Valid auth via default ProviderManager | Result `isAuthenticated=true`, `getCredentials()==null` if token supports it |
| Principal is Spring Security `User` | Password field of result principal is cleared |
| Provider returns custom Authentication **not** implementing CredentialsContainer | Never assume framework can wipe all secret fields automatically |
| UserDetailsService creates fresh copy each time | Second login still succeeds |
| Cache holds shared mutable User object | Test catches risk of password being erased from cached entry |
| Failed authentication | No trusted Authentication granted; input cleanup runs |
| `AuthenticationException` thrown mid-flight | `finally` still cleans caller-created input object |
| Session created after login | No raw passwords/OTPs/sensitive tokens stored in principal/details |
| Pooled thread completes request | SecurityContext is cleared by proper web mechanism |
| Logout | Session/tokens handled per policy, not merely `clearContext()` on one thread |
| Trace logs on login success/failure | No passwords, OTPs, bearer tokens, Cookies, or raw request bodies |
| Custom provider | Result Authentication contains needed ID/authorities, no unnecessary secrets |
| Password reset | Short-lived, account-bound, single-use reset code; never relies on password retained from login |
| Cache and database data | Canonical password hash stays protected and is not accidentally wiped via shared reference with principal |

With Spring Boot/MockMvc, `@WithMockUser` builds a pre-authenticated `Authentication` for authorization tests. It **does not run `DaoAuthenticationProvider` and `ProviderManager` through password authentication**. To test real credential erasure, invoke the real manager or send real login requests through the configured filter.

### Specific tests when `eraseCredentialsAfterAuthentication=false`

If a system is forced to disable the default due to caching, tests must explicitly evaluate:

- Does the result retain passwords/tokens in credentials or principal?
- Can it be serialized via sessions or emitted through debugging/monitoring?
- When is manual cleanup performed and what access controls protect it?
- Can the design be changed to return a secret-free/copied principal instead of keeping raw credentials?

A "working" flag is not enough to conclude the design is safe. Document the rationale and risk mitigations before going to production.

## 15. Common Mental Pitfalls

1. **"Spring Security wipes all passwords from RAM after login."** False. It usually clears references on the result object; other copies may remain.
2. **"`ProviderManager` automatically cleans the input request token too."** Not by default; it targets the returned **result**.
3. **"Seeing `Authentication.getCredentials()==null` guarantees no password remains in the principal."** Not guaranteed for custom principals lacking erasure support.
4. **"Clearing the password in the principal deletes the hash from the database."** No. In-memory objects and credential stores have separate lifecycles.
5. **"UserDetails can share the same cached object without mutation worries."** Default `User` is mutable and erasure can wipe the cached hash.
6. **"Disabling `eraseCredentialsAfterAuthentication` is the best cache fix."** Should not be the default; prefer copying objects or returning hash-free principals.
7. **"`CredentialsContainer` only erases raw passwords."** It can also clear password hashes or other secrets if the class implements it properly.
8. **"Spring automatically discovers any `secret` field in a custom Authentication."** No; the framework does not reflectively scan arbitrary fields.
9. **"An expired JWT just needs `eraseCredentials()`."** Token lifetime/validation/revocation are separate concerns.
10. **"`SecurityContextHolder.clearContext()` logs out all devices too."** No; it only affects the current thread's context.
11. **"With `permitAll()`, no secrets exist in the request."** No; clients can still send tokens/passwords to public URLs.
12. **"Not logging passwords in controllers is enough."** Reverse proxies, APMs, filters, and failure handlers can also record data.
13. **"`char[]` guarantees the secret disappears completely."** No; copies and runtime limits may exist, it merely helps manage one owned array.
14. **"Putting refresh tokens in `Authentication.details` lets Spring clean them."** Not guaranteed; design `details` separately and avoid storing secrets there.
15. **"Only successful logins need cleanup."** False. Failure and exception paths must also clean application-owned inputs.
16. **"Login succeeded, so keep the password for background tasks to reuse."** No; background work needs its own identity/delegation.
17. **"Bcrypt hashes are harmless and fine to return in JSON."** No; hashes remain sensitive and vulnerable to offline cracking if exposed.
18. **"Using HTTPS means we don't need to worry about secrets in logs/sessions."** TLS protects transport, not internal copies.
19. **"Once MFA completes, all OTPs/tokens vanish automatically."** Each secret and component needs its own lifecycle.
20. **"Using `@WithMockUser` proves DaoAuthenticationProvider cleanup works."** No; that test skips real password authentication.

## 16. Self-Check Questions

**Question 1.** When `DaoAuthenticationProvider` verifies a valid password, which component is responsible for erasing credentials on the successful `Authentication` in the standard configuration?

*Answer:* `ProviderManager` calls `eraseCredentials()` on the result if it implements `CredentialsContainer` and the feature is enabled (default).

**Question 2.** Does `getCredentials()==null` prove every copy of the raw password has vanished from the JVM?

*Answer:* No. That is only the state of one object; Strings, request buffers, and other copies may remain in memory.

**Question 3.** A `UserDetailsService` returns the exact same `User` instance from a cache. Why might the next login fail?

*Answer:* When that object is attached as the result principal, `eraseCredentials()` can clear the password hash inside the cached instance itself. Return an isolated copy or design the provider to return a minimal principal.

**Question 4.** Should you disable `setEraseCredentialsAfterAuthentication` just to solve a cache bug?

*Answer:* While the option exists, it retains secrets longer; prefer isolating the cache from the principal or using copies. If forced to disable it, evaluate and test the risks.

**Question 5.** Why can `UserDetails#getPassword()` on the result principal be `null` even after a valid login?

*Answer:* Because `User` implements `CredentialsContainer` and the framework cleared the password hash from the principal copy after authentication, while the hash in storage remains intact.

**Question 6.** A failed login throws `BadCredentialsException`. Can you assume ProviderManager cleaned the application's input request?

*Answer:* No. When owning the request token, clean it in `finally` and avoid copying raw credentials; default result cleanup applies to successful results.

**Question 7.** What is the difference between `eraseCredentials()` and `SecurityContextHolder.clearContext()`?

*Answer:* One clears secrets inside supporting objects; the other removes the authentication context from the current thread. Neither substitutes for system-wide logout/revocation.

**Question 8.** Should an entire Account entity containing the password hash be placed in `Authentication.principal`?

*Answer:* No. Principals should carry only needed IDs and metadata; entities hold sensitive data and different lifecycles, risking long retention or serialization.

**Question 9.** To preserve access permissions for a background job after login, should you push the entire Authentication with the password into the queue?

*Answer:* No. Pass IDs/claims/permissions designed for the job and enforce separate authorization; never retain raw request passwords.

**Question 10.** A bearer token remains valid on the client even after the server calls `eraseCredentials()`. Why?

*Answer:* Clearing references on a server object does not revoke the token copy held by the client. Use appropriate TTL/validation/revocation to limit stolen tokens.

## 17. Checklist Before Completing an Authentication Flow

- [ ] Raw passwords/tokens exist only in components that genuinely need them and are excluded from logs, caches, analytics, or sessions.
- [ ] Authentication mechanism returns `Authentication` with minimal principal/authorities; result credentials are erased where possible.
- [ ] `ProviderManager` keeps `eraseCredentialsAfterAuthentication=true` unless there is an explicit, documented technical decision.
- [ ] Custom `Authentication`/principals implement secret cleanup if forced to carry secrets, or better yet omit secrets from the start.
- [ ] Application-created input tokens are cleaned in `finally` on both success and failure paths.
- [ ] `UserDetailsService` and caches never return a shared mutable `User` whose erasure loses the password hash needed for later logins.
- [ ] Password hashes in DB/credential stores remain protected, unexposed to APIs, and safe from accidental erasure.
- [ ] Sessions/`SecurityContext` hold no raw passwords; logout/session invalidation follows policy.
- [ ] JWT/access/refresh tokens have dedicated lifetimes, storage, and revocation strategies.
- [ ] Thread/security context is properly managed across Servlet, async tasks, and background workers.
- [ ] HTTP traces, reverse proxies, APMs, exception logs, and audits redact credentials and sensitive tokens.
- [ ] Code and tests never embed production passwords in literals, stdout, command history, or shared test fixtures.
- [ ] Integration tests cover two consecutive logins, failed logins, credential cleanup, and cache ownership.
- [ ] Password reset, MFA, and step-up authentication flows are reviewed rather than relying on passwords retained from login.
- [ ] Application maintains heap-dump, monitoring, log access, and incident-response policies fitting sensitive data.

A useful way to remember this divides three responsibilities: **`PasswordEncoder` verifies evidence**, **`ProviderManager` can erase result credentials**, and **application design decides where copies of secrets are kept and for how long**. No single step replaces the other two; sound security ensures secrets appear in as few places as possible and survive only as long as the task requires.

### Reference Documentation

- [Spring Security — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security — CredentialsContainer](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/credentials-container.html)
- [Spring Security — UserDetails and Credentials Management](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/user-details.html)
- [Spring Security — ProviderManager API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/ProviderManager.html)
- [Spring Security — CredentialsContainer API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/CredentialsContainer.html)
- [Spring Security — UsernamePasswordAuthenticationToken API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/UsernamePasswordAuthenticationToken.html)
- [Spring Security — User API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/userdetails/User.html)
- [Spring Security — DaoAuthenticationProvider API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/dao/DaoAuthenticationProvider.html)
- [Spring Security — SecurityContextHolder](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html#servlet-authentication-securitycontextholder)
- [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
