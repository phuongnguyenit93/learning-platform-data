# eraseCredentialsAfterAuthentication and Its Impact on Shared Objects

In Spring Security, `ProviderManager` enables the **`eraseCredentialsAfterAuthentication`** option by default. After **successful** authentication, the manager inspects the `Authentication` result: if the result implements `CredentialsContainer`, it calls `eraseCredentials()` before returning it to the caller. The goal is to reduce how long passwords or sensitive data remain inside Java objects, especially objects that may be placed into `SecurityContext` and the HTTP session.

However, if the `Authentication` result holds a reference to the exact same `UserDetails` object sitting in a cache, erasing sensitive info can **mutate the shared object itself**. In that case, the cache still keeps the key, yet the password hash inside the object has become `null`; the next authentication request may fail or have to reload data from the backing store.

This lesson thoroughly explains **when erasure happens, what gets erased, why aliasing occurs, how to reproduce it with Java 17, remediation strategies, and how to test**. The topic belongs to the **Authentication Engine** group of Spring Security Authentication; do not confuse it with logout, password change, or token revocation.

## 1. Role of the eraseCredentialsAfterAuthentication Flag

A typical username/password flow:

~~~text
Client supplies username and password
                |
                v
Filter receives login request
                |
                v
Authentication request (unauthenticated; credentials=raw password)
                |
                v
ProviderManager.authenticate(request)
                |
                +--> AuthenticationProvider
                |       |
                |       +--> UserDetailsService/cache loads UserDetails
                |       +--> PasswordEncoder.matches(raw, passwordHash)
                |       +--> Return successful Authentication
                |
                +--> If eraseCredentialsAfterAuthentication=true:
                |       If result instanceof CredentialsContainer:
                |           result.eraseCredentials()
                |
                v
Authenticated Authentication result
                |
                v
Filter/handler handles SecurityContext/session per configuration
~~~

`AuthenticationManager.authenticate` defines the authentication contract; `ProviderManager` is a common implementation and is where this flag lives. `ProviderManager`'s default is **`true`**. If implementing a completely separate `AuthenticationManager`, do not assume it also performs erasure unless the implementation shares an equivalent contract.

| Question | Conclusion |
|---|---|
| When does the manager invoke erasure? | After finding a successful result and before returning the result |
| Is it called for every `Authentication`? | Only if the result supports `CredentialsContainer` and the flag is enabled |
| Does it surely wipe every secret in the object graph? | No; depends on each object's `eraseCredentials()` implementation |
| Does it erase credentials from the database record? | No; it is not an SQL statement updating the password hash in the DB |
| Does it erase the original request token and all `String` copies? | No such guarantee exists |
| Does it automatically revoke sessions/JWTs? | No; those are separate authentication lifecycle mechanisms |

Typical configuration API (illustrative snippet, `providers` not declared here):

~~~java
ProviderManager manager = new ProviderManager(providers);
boolean current = manager.isEraseCredentialsAfterAuthentication();
manager.setEraseCredentialsAfterAuthentication(true);
~~~

Standard practice is to **keep it `true`**, and then fix the reference design if caches are affected.

## 2. How Does CredentialsContainer Work?

`org.springframework.security.core.CredentialsContainer` has the contract:

~~~java
public interface CredentialsContainer {
    void eraseCredentials();
}
~~~

It does not define a universal `password` field. Implementing objects must know which references to clear. Common related types:

- `AbstractAuthenticationToken` implements `CredentialsContainer` and during erasure inspects **`getCredentials()`, `getPrincipal()`, and `getDetails()`**. If any of those three objects also implements `CredentialsContainer`, its corresponding erase method is called.
- `UsernamePasswordAuthenticationToken` also sets the token's `credentials` field to `null` when erasure runs.
- `org.springframework.security.core.userdetails.User` is a mutable `UserDetails` implementation whose `eraseCredentials()` sets **that instance's** password hash field to `null`.
- Custom principals/tokens holding secrets must be designed properly: if they do not implement `CredentialsContainer`, the framework does not automatically inspect fields via reflection.

Illustrative reference graph:

~~~text
Authentication result S (CredentialsContainer)
  |- credentials  --> password object / secret
  |- principal    --> UserDetails U (CredentialsContainer)
  '- details      --> Details D (may be a CredentialsContainer)

S.eraseCredentials()
  |- credentials.eraseCredentials() if implementing interface
  |- U.eraseCredentials()           if implementing interface
  '- D.eraseCredentials()           if implementing interface
  '- For UsernamePasswordAuthenticationToken: credentials = null
~~~

Notice the **distinction among sensitive data types**:

1. Raw password in the request is a secret submitted by the client. It should normally not be included in the result after successful verification.
2. Password hash in `UserDetails` is also sensitive, yet usually needs to remain in the trusted source for subsequent authentications. Erasing the hash on a **per-request copy** can be appropriate; erasing the hash on the **original cached object** is risky.
3. The principal typically only needs ID, username, and authorities; it should not hold raw passwords, refresh tokens, private keys, connection secrets, or heavy JPA entities.

Erasure in Java typically **clears references**, rather than guaranteeing every old byte in RAM is overwritten. For example, setting a `String password` field to `null` does not prove every copy of that `String` was immediately wiped from the heap. Good defense therefore includes minimizing secret copies, never logging secrets, and shortening retention windows.

### 2.1. A Note on the Failed Authentication Path

The manager only runs the erasure step on the **successful result** in the contract under discussion. When a provider throws `AuthenticationException`, never assume the failed attempt's request token was automatically wiped. In custom logins/filters, never put raw passwords or tokens into logs/error responses; manage request references and secret lifecycles properly.

## 3. Aliasing: Why Does the Cache Mutate Without Calling cache.put?

Suppose a cache stores an object `U`. After verifying the hash, a provider returns an `Authentication` whose principal references `U`.

~~~text
Cache: "linh" --------> UserDetails U
                             |
                             | passwordHash="$2a$..."
                             ^
                             |
Authentication result -------+  (same Java object, not a copy)
       |
       v
ProviderManager calls result.eraseCredentials()
       |
       v
U.eraseCredentials()
       |
       v
U.password = null
       |
       v
Cache still points to U, yet U.password is now null
~~~

That is **reference aliasing**: multiple variables/paths pointing to the same object. `UserDetails other = cachedUser;` only creates another reference; it does not clone `UserDetails`. Even when `cachedUser.equals(principal)` is `true`, they are not necessarily the same instance since `equals` may compare by username. To verify instance sharing in a test, use `cachedUser == result.getPrincipal()`.

If the cache returns the exact same instance for multiple requests, one completed login can impact other requests. With mutable objects, the timing of erasure vs. `PasswordEncoder.matches(...)` running on different threads can cause hard-to-reproduce bugs.

### 3.1. Common Caching Patterns

| Pattern | Risk |
|---|---|
| Singleton `Map` holding `UserDetails` and service returns the entry directly | Manager erases the hash right on the entry |
| `@Cacheable` on `loadUserByUsername` returning the same reference in-process | Principal is shared with the cache |
| `UserCache` used inside `DaoAuthenticationProvider` | Depending on how provider/cache returns objects and falls back, the cache may be affected |
| Constructing a fresh `UserDetails` per login | Erasure normally affects only that attempt's instance |
| Principal holding only newly created ID/username | No remaining reference to the cached password hash |
| Cache storing an immutable object; provider builds a per-request mutable copy | The copy is erased while the original cache entry stays intact |

Not every `DaoAuthenticationProvider` exhibits “the second login definitely fails”. Some execution paths can reload `UserDetails` from the source after a cache check fails; the program may keep logging users in while increasing queries and defeating the cache. Measure cache hits, database call counts, and latency, in addition to checking login outcomes.

## 4. Runnable Java 17 Example: Reproducing the Bug and Fixing via Detached Principal

The Java program below uses Spring Security Core and Crypto directly, without Spring Boot or a web server. It creates two independent scenarios:

- **UNSAFE:** the custom provider puts `cachedUser` directly (the exact `User` instance used by the cache) into the returned principal.
- **SAFE:** the provider authenticates using `cachedUser` yet returns a `String` principal containing only the verified username, retaining no reference to the cached object. In real projects, use an immutable projection with a stable internal ID.

Both `ProviderManager`s use the default `eraseCredentialsAfterAuthentication=true`. The only change affecting the bug is **the instance identity returned for authentication**, not disabling erasure.

### 4.1. Project Structure and Gradle

~~~text
credentials-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/example/CredentialsDemo.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'credentials-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

group = 'example'
version = '1.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.security:spring-security-core:6.3.8'
    implementation 'org.springframework.security:spring-security-crypto:6.3.8'
}

application {
    mainClass = 'example.CredentialsDemo'
}
~~~

Versions in the demo are pinned so the APIs discussed share a consistent baseline; real Spring Boot apps typically manage Spring Security versions via dependency management/BOM. Requires JDK 17+, compatible Gradle, and downloading dependencies from Maven Central on the first run.

### 4.2. Standalone Source Code

Create `src/main/java/example/CredentialsDemo.java` with content:

~~~java
package example;

import java.util.List;

import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

public final class CredentialsDemo {

    public static void main(String[] args) {
        PasswordEncoder encoder = new BCryptPasswordEncoder();
        runScenario("UNSAFE", false, encoder);
        runScenario("SAFE", true, encoder);
    }

    private static void runScenario(String label,
                                    boolean detachPrincipal,
                                    PasswordEncoder encoder) {
        // One UserDetails entry reused across two login attempts.
        UserDetails cachedUser = User.withUsername("linh")
                .password(encoder.encode("demo-pass"))
                .authorities("notes:read")
                .build();

        AuthenticationProvider provider =
                new DemoProvider(cachedUser, encoder, detachPrincipal);
        ProviderManager manager = new ProviderManager(List.of(provider));
        // Keep the default configuration eraseCredentialsAfterAuthentication=true.

        for (int attempt = 1; attempt <= 2; attempt++) {
            Authentication request =
                    UsernamePasswordAuthenticationToken.unauthenticated(
                            "linh", "demo-pass");

            try {
                Authentication result = manager.authenticate(request);
                System.out.println(label + "#" + attempt
                        + " OK, credentialsNull="
                        + (result.getCredentials() == null)
                        + ", cachedHashPresent="
                        + (cachedUser.getPassword() != null));
            } catch (AuthenticationException ex) {
                System.out.println(label + "#" + attempt
                        + " FAIL=" + ex.getClass().getSimpleName()
                        + ", cachedHashPresent="
                        + (cachedUser.getPassword() != null));
            }
        }
    }

    private static final class DemoProvider
            implements AuthenticationProvider {
        private final UserDetails cachedUser;
        private final PasswordEncoder encoder;
        private final boolean detach;

        private DemoProvider(UserDetails cachedUser,
                             PasswordEncoder encoder, boolean detach) {
            this.cachedUser = cachedUser;
            this.encoder = encoder;
            this.detach = detach;
        }

        @Override
        public Authentication authenticate(Authentication request)
                throws AuthenticationException {
            if (!cachedUser.getUsername().equals(request.getName())
                    || !(request.getCredentials() instanceof String)) {
                throw new BadCredentialsException("Invalid credentials");
            }
            String raw = (String) request.getCredentials();
            if (!encoder.matches(raw, cachedUser.getPassword())) {
                throw new BadCredentialsException("Invalid credentials");
            }

            // UNSAFE: same UserDetails instance as the cache.
            // SAFE: new principal containing only username, holding no hash.
            Object principal = detach
                    ? cachedUser.getUsername() : cachedUser;

            // Only to demonstrate the manager erasing result credentials.
            // Production providers should pass null when no secret is needed.
            return UsernamePasswordAuthenticationToken.authenticated(
                    principal, raw, cachedUser.getAuthorities());
        }

        @Override
        public boolean supports(Class<?> type) {
            return UsernamePasswordAuthenticationToken.class
                    .isAssignableFrom(type);
        }
    }
}
~~~

### 4.3. Running and Expected Output

If the project directory has a Gradle Wrapper:

~~~bash
./gradlew run
~~~

If there is no wrapper yet but a compatible Gradle is installed, run `gradle run`. On PowerShell with a wrapper, use `.\gradlew.bat run`. Program output (omitting Gradle logs):

~~~text
UNSAFE#1 OK, credentialsNull=true, cachedHashPresent=false
UNSAFE#2 FAIL=BadCredentialsException, cachedHashPresent=false
SAFE#1 OK, credentialsNull=true, cachedHashPresent=true
SAFE#2 OK, credentialsNull=true, cachedHashPresent=true
~~~

Logic explanation:

1. `cachedUser` is built via `User.withUsername(...).build()`, so it is an actual object implementing `CredentialsContainer`. The BCrypt hash value varies due to random salts across runs; `matches` checks remain consistent.
2. The provider verifies the right username and raw password against the hash from `cachedUser`.
3. In UNSAFE attempt #1, the resulting principal points to **the same `UserDetails` instance**. `ProviderManager` erases credentials on the result, triggering `User.eraseCredentials()` on the principal; `cachedUser.getPassword()` becomes `null`.
4. UNSAFE attempt #2 calls the provider with the same cache entry whose hash is now missing. `PasswordEncoder.matches(...)` no longer has a valid hash, and the provider throws `BadCredentialsException`. This custom demo provider has no DB reload branch.
5. In SAFE, the principal is the verified username `String`; the result does not hold `cachedUser`, so the manager only erases credentials on the result token. The original cached hash stays intact, and both authentications succeed.
6. `credentialsNull=true` appears because the demo deliberately puts the raw password in the result so the manager erases it. This is solely to observe erasure directly; in production code, avoid putting raw passwords into the result in the first place.

The takeaway is not to always use `String` as the principal. Real applications typically need `accountId`, `tenantId`, or a minimal profile in an **immutable, secret-free** principal/DTO, querying the current account from a repository when needed.

### 4.4. Experimenting with the Flag Without Applying It Arbitrarily

You can add the following statement right after creating `ProviderManager` in the demo **solely to observe the difference**:

~~~java
manager.setEraseCredentialsAfterAuthentication(false);
~~~

When disabled, the manager does not call erasure on the result, so in the UNSAFE example the cached hash is not wiped by this mechanism; however, `result.getCredentials()` still retains the raw password from the demo provider. In web applications, if the result is stored in `SecurityContext`/session, this increases the risk of credential exposure.

**Therefore, the primary solution to shared-object mutation is detaching references or copying objects properly while keeping erasure enabled by default.**

## 5. Production Solutions: Controlling Ownership and Object Lifecycle

### 5.1. Creating a Safe Principal Detached from Cache

Example of an immutable principal:

~~~java
record CurrentActor(java.util.UUID accountId, String username) {}
~~~

After verifying credentials and account status against trusted data, the provider creates a new object:

~~~java
CurrentActor actor = new CurrentActor(account.id(), account.username());
Authentication verified =
        UsernamePasswordAuthenticationToken.authenticated(
                actor, null, grantedAuthorities);
~~~

These two snippets are **illustrative code in an application that already has `account` and `grantedAuthorities`**, not a complete standalone program if copied out of context. Never put password hashes, raw tokens, JPA entities, or cached objects into `CurrentActor`. `accountId` is a stable internal ID; `username` may change.

Ensure the provider uses authorities **granted by the server**, never copying roles self-declared by the client. Erasure is only one layer of protection; the authentication result must still be created only after full verification.

### 5.2. Returning a Per-Request UserDetails Copy

If a provider needs a `UserDetails`-typed principal, the cache can hold the original while returning **a different instance**, such as creating a copy inside `UserDetailsService`/the adapter:

~~~java
UserDetails perRequest = User.withUserDetails(cachedUser).build();
~~~

This snippet assumes `cachedUser` still has its hash intact. `User.withUserDetails` builds a standard `User`; extra fields must be handled manually if the app uses a custom `UserDetails` (internal ID, tenant, other flags). Then the provider can return `perRequest`, letting erasure act on the copy without corrupting the original cached data.

**`UserDetails copy = cachedUser;` is not a copy at all.** It only adds another variable pointing to the same object. When cloning, inspect nested fields too: if the new principal still holds a reference to a mutable object containing secrets, aliasing may persist.

### 5.3. Controlling Caching, Invalidation, and Concurrency

With `UserCache` or `@Cacheable`, ask concrete questions:

- Does the cache store `UserDetails` carrying password hashes, account entities, or a projection?
- Does the cache getter return the same instance or construct a copy?
- When passwords change, accounts lock, or roles change, under what contract are entries invalidated?
- How many `ProviderManager` instances and filter chains participate; which manager is actually used?
- Does the provider have a fallback path to reload `UserDetailsService` if a cache hit holds unusable data?
- Can request A concurrently call `PasswordEncoder.matches(...)` while request B is erasing the principal on the same instance?
- Does auditing print full principals/tokens, credentials, or hashes to logs?

For low login volumes, **not caching `UserDetails` with hashes** sometimes drastically reduces complexity and risk. When using a cache, protect hashes like sensitive data: TTL, access controls, log controls, and invalidation workflows.

### 5.4. When to Consider Disabling eraseCredentialsAfterAuthentication?

The `ProviderManager#setEraseCredentialsAfterAuthentication(false)` API exists, and Spring Security documentation mentions it as an option when caches use shared objects. Yet it is a **trade-off**: the result may retain raw passwords, API keys, or secrets longer in memory, especially if principal/details contain sensitive data.

Consider this option only after analyzing the specific provider/token/result and putting controls in place to limit sensitive data; prefer returning a detached projection or copying data properly first. Never toggle the flag globally just to silence an authentication error without proving the root cause.

## 6. Misconceptions to Eliminate

**“After login, the password hash in the database is erased too.”** False: this mechanism mutates Java objects satisfying `CredentialsContainer`; it does not issue SQL statements updating passwords.

**“The cache holds a copy of the object, so it is safe.”** Not necessarily: caches usually hold references; fetching from a map does not auto-clone. Verify with `==` in tests.

**“If the cached hash became null, the cache entry must have been evicted.”** False: the key can remain in the map pointing to the mutated object.

**“All second logins always fail.”** No. Outcomes also depend on the provider/cache and reload capabilities. Measure both cache hit quality and query counts.

**“Erasing credentials also logs out all sessions and revokes tokens.”** No. Logout/session invalidation/token revocation are separate behaviors.

**“Disabling erasure to fix the bug has no side effects.”** False: sensitive data may remain in the resulting `Authentication`, and in sessions/logs if accidentally persisted.

**“Having a custom `Authentication` implement `CredentialsContainer` is enough.”** Not necessarily: `eraseCredentials()` must actually clear owned secret fields or nested containers appropriately. Better yet, do not store secrets in the result.

**“Erasure wipes every `String` copy from RAM.”** No such contract exists. Nulling fields drops references; the JVM does not guarantee all old bytes vanish immediately.

**“After `authenticate`, I can use `result.getCredentials()` to call another service.”** Should not be done; the result may have erased the secret. Design flows needing only principal/authorities; never use the user's password as a credential on behalf of other services.

## 7. Diagnosing the Bug Systematically

When a login system works the first time yet flakes on subsequent attempts:

1. Check `ProviderManager.isEraseCredentialsAfterAuthentication()` on the manager **actually** handling the failing request type.
2. Write an integration test authenticating the same username twice while holding a separate handle to the cached entry.
3. Before/after attempt #1, measure only the boolean `cachedUser.getPassword() != null`; never print hashes or raw secrets.
4. Check `authentication.getPrincipal() == cachedUser`. Use `==` for identity; `equals()` may be true merely because usernames match.
5. Count `loadUserByUsername`/cache hits/cache misses. Logins succeeding while reloading the DB every time are also a signal.
6. Find where the authenticated token is built: is the same `UserDetails`/mutable entity being put into the principal?
7. Test a version returning a detached principal. If the issue disappears and the cache stays intact, continue testing authorization and account statuses.
8. Add a concurrency test with multiple requests authenticating the same account; eliminate shared mutable references between provider and result.

Never put `Authentication.toString()`, request bodies with passwords, raw JWTs, or hashes into logs during investigation. Observe via harmless IDs, class types, and boolean states, keeping secrets out of logging systems.

## 8. Recommended Test Matrix

| Scenario | Expected outcome |
|---|---|
| Successful auth, default erasure | Authentication succeeds; result credentials are gone when token supports erasure |
| `UserDetails` principal shared with cache | Test reproduces erasure turning the cached hash into null |
| Provider returns safe, detached principal | Original cache entry is unmutated; second authentication still works normally |
| Cache provides per-request copy | Erasure affects only the copy, leaving cache source intact |
| Cache hit after successful login | No abnormal drop in hit rate or unexpected DB queries |
| Two concurrent logins | No race condition from one request clearing another request's hash |
| Custom token holding secrets | `eraseCredentials()` genuinely clears owned secret fields |
| Failed authentication | Do not assume failed request credentials are cleaned by the manager's success branch |
| Password change / account lock | Cache invalidated per policy; sessions/tokens handled separately |
| Disabling erasure in test | Directly observes secrets persisting longer in the demo result |
| SecurityContext/session | Does not unnecessarily serialize raw passwords, hashes, private keys, or sensitive tokens |

### 8.1. Analysis Exercises

**Question 1.** Why can `UserDetails cached = repository.load(...)` and `Authentication principal = cached` cause a bug?  
**Answer:** They can point to the same mutable object. The manager erases credentials on the principal, which mutates the object still held by the cache/repository adapter.

**Question 2.** Does `cached.equals(result.getPrincipal()) == true` always prove they are the same instance?  
**Answer:** No. Two distinct objects can be `equals`; use reference identity `==` when checking aliasing.

**Question 3.** You turned off the erasure flag and the second login succeeded. Is that enough to conclude it is the right production fix?  
**Answer:** No. Inspect whether raw credentials/secrets remain in `Authentication`, context, or sessions. Detaching the principal/copying objects is usually a safer fix.

**Question 4.** Subsequent logins still succeed even though the hash in the cached object became null. Does that mean caching is healthy?  
**Answer:** Not yet. The provider may be falling back to reload fresh data; inspect cache hits, database loads, and latency.

**Question 5.** If a custom authentication result does not implement `CredentialsContainer`, will the manager automatically wipe a private key in an arbitrary field?  
**Answer:** No. Return a result containing no secrets or implement erasure according to the contract.

**Question 6.** Does erasing the raw password from the result replace access-token revocation after locking an account?  
**Answer:** No. Erasure deals with the in-memory state of the authenticated object; revocation/token validity/session management are separate responsibilities.

## 9. Design Checklist Before Deployment

- Keep `eraseCredentialsAfterAuthentication=true` unless there is a specific reason and explicit risk controls.
- Avoid putting raw passwords, password hashes, API tokens, or JPA entities into the result principal unnecessarily.
- Know exactly which **instance** the cache holds; never treat extra variables/references as copies.
- If a provider uses mutable `UserDetails` from a cache, build a detached principal or a true `UserDetails` copy.
- Test both post-cache-hit logins and concurrent requests; measure user-load query counts.
- Define cache invalidation policies when passwords, authorities, or account statuses change.
- Do not treat erasure as logout, JWT revocation, password change, or database cleanup.
- Never log full credentials/results in logs/test outputs, even on errors.
- With multiple filter chains/parent managers, verify which manager actually applies to the flow being changed.

**Remember:** `eraseCredentialsAfterAuthentication` protects credentials after a successful authentication; **impacts on shared objects arise when multiple owners hold the same mutable reference**. Keeping secret erasure enabled while clarifying copy/ownership boundaries keeps the system both secure and cache-safe.

### Official Documentation

- [Spring Security – Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): `ProviderManager` and impact on cached user objects.
- [Spring Security – CredentialsContainer](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/credentials-container.html): contract and meaning of credential erasure.
- [Spring Security – UserDetails](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/user-details.html): recommendations for managing passwords and cached objects.
- [Spring Security – AbstractAuthenticationToken](https://docs.spring.io/spring-security/site/docs/6.3.0/api/org/springframework/security/authentication/AbstractAuthenticationToken.html): erasure across credentials, principal, and details.
- [Spring Security – ProviderManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/ProviderManager.html): configuration API for `eraseCredentialsAfterAuthentication`.
