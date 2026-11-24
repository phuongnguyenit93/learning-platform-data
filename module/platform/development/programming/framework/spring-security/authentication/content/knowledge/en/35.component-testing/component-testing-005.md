# Testing Account Status, Loaded Authorities, and Credential Erasure

## 1. Lesson Objectives

In Spring Security, a login involves more than just checking "correct password". The outcome also depends on **account status**, **authorities loaded from a trusted source**, and **how credentials are handled after authentication**. A test that only asserts `authentication.isAuthenticated() == true` can miss three major bugs:

- Locked, disabled, expired, or credential-expired accounts can still log in.
- `UserDetailsService` returns missing authorities, extra authorities, or the mapper mistakenly grants `ROLE_ADMIN`.
- Raw passwords/secrets remain inside `Authentication`, or erasing secrets corrupts a shared `UserDetails` instance in the cache.

This lesson focuses on **component testing** of the username/password authentication path in **Spring Security 6.x / Spring Boot 3.x with Java 17+**. Notes are included for **Spring Security 7.x** and other mechanisms such as JWT, LDAP, WebAuthn, and OTT where relevant. The unit tests here do not require running an HTTP server; later sections explain tests at the filter/HTTP layer to clarify boundaries.

By the end of this lesson, you will be able to:

1. Read the four status flags on `UserDetails` and their corresponding exceptions accurately.
2. Write real tests for `DaoAuthenticationProvider` and `ProviderManager`, rather than relying only on mocked `@WithMockUser`.
3. Verify **where authorities come from**, whether they map accurately to `GrantedAuthority`, and that no authorities are fabricated from requests.
4. Verify credentials are erased from successful login results without corrupting original/cached user data.
5. Design negative tests for nonexistent usernames, wrong passwords, locked accounts, expired credentials, and permission changes.
6. Distinguish a new authentication event from an existing session, and distinguish provider unit tests from HTTP integration tests.
7. Apply security principles: never expose overly specific failure reasons externally, never retain plaintext passwords, and never disable erasure to "fix" caching without a threat model.

## 2. Components Under Test

Typical Servlet path:

```text
UsernamePasswordAuthenticationFilter
       |
       v
UsernamePasswordAuthenticationToken (unauthenticated)
       | principal=username, credentials=raw password
       v
AuthenticationManager: ProviderManager
       |
       v
DaoAuthenticationProvider
       |
       +--> UserDetailsService.loadUserByUsername(username)
       |       -> UserDetails
       |       -> flags + password hash + authorities
       |
       +--> check account status before password
       +--> PasswordEncoder.matches(raw, storedHash)
       +--> check credentials non-expired
       +--> optionally apply GrantedAuthoritiesMapper
       |
       v
UsernamePasswordAuthenticationToken (authenticated)
       | principal is usually UserDetails
       | authorities determined
       | credentials may still remain on object returned by provider
       v
ProviderManager.eraseCredentialsAfterAuthentication (default true)
       |
       v
Authentication after erasing credentials
       |
       v
SecurityContext / session when filter handles HTTP request
```

**Note the three independent layers:**

- `UserDetailsService` **loads data**: username, encoded password, status flags, and the set of authorities. It does not compare passwords itself and does not populate `SecurityContext`.
- `DaoAuthenticationProvider` **verifies** username/password against the provider's status policies, then produces a successful `Authentication`.
- `ProviderManager` **coordinates providers** and by default calls `eraseCredentials()` on a successful authentication if the object implements `CredentialsContainer`.

In unit tests calling `manager.authenticate(...)` directly, Spring Security **does not automatically place the result into `SecurityContextHolder`** as an HTTP filter does. Tests must inspect the returned object rather than assuming a session or login cookie exists.

## 3. Status Flags on `UserDetails`

`UserDetails` provides the following methods:

| Method | `true` means | `false` typically leads to |
| --- | --- | --- |
| `isEnabled()` | Account is permitted for use | `DisabledException` |
| `isAccountNonLocked()` | Account is not locked | `LockedException` |
| `isAccountNonExpired()` | Account has not expired | `AccountExpiredException` |
| `isCredentialsNonExpired()` | Credentials (typically password) have not expired | `CredentialsExpiredException` |

**Especially easy to confuse:** three method names contain **`Non`**. `isAccountNonLocked() == true` means **not locked**; `isCredentialsNonExpired() == false` means **credentials have expired**.

With the `org.springframework.security.core.userdetails.User` builder, the syntax takes the inverse polarity of the flags:

```java
User.withUsername("linh")
    .password(encodedPassword)
    .roles("READER")
    .disabled(true)
    .accountLocked(true)
    .accountExpired(true)
    .credentialsExpired(true)
    .build();
```

The builder parameters `disabled`, `accountLocked`, `accountExpired`, and `credentialsExpired` take `true` when the **bad state is active**. A single `.accountLocked(true)` call causes `isAccountNonLocked() == false`.

Never set all four values to `true` in one test and expect all four exceptions to be thrown: the provider throws only the **first exception** in its actual check order. Each status must have its own fixture and assertion.

### 3.1. Account status is distinct from business permissions

An account with `ROLE_ADMIN` and `disabled=true` must not pass authentication merely because of its high role. Conversely, an enabled account with `ROLE_READER` can still authenticate successfully yet remain barred from calling endpoints requiring `ROLE_ADMIN`.

Therefore, tests need **two layers**:

1. **Authentication test**: do username/password and account status allow creating an `Authentication`?
2. **Authorization test**: given a valid `Authentication`, which authorities does it carry and does it satisfy `hasAuthority`/`hasRole` rules?

`isAuthenticated()` cannot replace testing the full account policy and loaded authorities.

## 4. When Does `DaoAuthenticationProvider` Check Status?

In Spring Security 6.x's default username/password path, the superclass `AbstractUserDetailsAuthenticationProvider` performs checks conceptually as:

```text
Loaded UserDetails
       |
       +--> Pre-authentication checks:
       |      1. accountNonLocked?
       |      2. enabled?
       |      3. accountNonExpired?
       |
       +--> additionalAuthenticationChecks:
       |      PasswordEncoder.matches(raw, encoded)?
       |
       +--> Post-authentication checks:
              credentialsNonExpired?
```

Typical exceptions:

```text
isAccountNonLocked() = false      -> LockedException
isEnabled() = false               -> DisabledException
isAccountNonExpired() = false     -> AccountExpiredException
Wrong password                    -> BadCredentialsException
isCredentialsNonExpired() = false -> CredentialsExpiredException
```

This ordering enables targeted testing. For instance, **credentials expired** may be checked only after the password has been verified; use the **correct password** to assert `CredentialsExpiredException` instead of confusing a password error with an expiry error.

**API note:** `DaoAuthenticationProvider` can be configured with `setPreAuthenticationChecks(...)`, `setPostAuthenticationChecks(...)`, `setAuthoritiesMapper(...)`, a password encoder, caching, and other customizations. If the app replaces checkers or providers, ordering/policies may differ; tests must reflect the **actual configuration**, not just the default class behavior.

### 4.1. `AccountStatusUserDetailsChecker`

Spring Security also provides `org.springframework.security.authentication.AccountStatusUserDetailsChecker` to check user status via the `UserDetailsChecker` interface. This is a reusable helper when writing custom providers or login flows:

```java
AccountStatusUserDetailsChecker checker =
    new AccountStatusUserDetailsChecker();
checker.check(userDetails);
```

Import:

```java
import org.springframework.security.authentication.AccountStatusUserDetailsChecker;
```

**Distinction:** this checker verifies **`UserDetails` status**; it does not compare passwords, validate JWT signatures, or manage sessions or HTTP permissions. Providers other than `DaoAuthenticationProvider` may have their own account-status semantics; do not assume a flow using `UserDetailsService` automatically runs all checkers by default.

## 5. Loaded Permissions: `roles`, `authorities`, and `GrantedAuthority`

A `UserDetails` holds `Collection<? extends GrantedAuthority>` from the account source (DB, LDAP mapper, authorization service, etc.). After authentication, `Authentication.getAuthorities()` is what authorization rules such as `hasRole`/`hasAuthority` inspect.

| Builder call | Actual authority |
| --- | --- |
| `.roles("READER")` | `ROLE_READER` |
| `.roles("ADMIN")` | `ROLE_ADMIN` |
| `.authorities("ROLE_ADMIN")` | `ROLE_ADMIN` |
| `.authorities("SCOPE_reports:read")` | `SCOPE_reports:read` |
| `.roles("ROLE_ADMIN")` | **Wrong**: the `roles` builder automatically prepends `ROLE_` |
| `.authorities("ADMIN")` | `ADMIN`, **does not automatically** become `ROLE_ADMIN` |

How to inspect:

```java
Set<String> actual = authentication.getAuthorities().stream()
    .map(GrantedAuthority::getAuthority)
    .collect(Collectors.toSet());
```

Corresponding imports:

```java
import java.util.Set;
import java.util.stream.Collectors;
import org.springframework.security.core.GrantedAuthority;
```

For authority sets, it is usually better to **compare as a `Set`** rather than asserting `Collection` order unless policy requires ordering. Crucially, assert **no extra authorities exist**: asserting only `contains("ROLE_READER")` can let an accidentally granted `ROLE_ADMIN` slip through.

### Loaded permissions vs client-asserted claims

- `request.getParameter("role")`, `X-Role` headers, email, or username are not trusted sources of authorities.
- Testing a mock `UserDetailsService` uses test-defined roles; in production, roles must come from a repository/IdP with an explicit contract and access controls.
- `ROLE_ADMIN` is an authorization grant; **never** infer it from `isEnabled()==true` or `isAuthenticated()==true`.
- For OAuth2 JWT/opaque bearer tokens, authorities can come from scopes/claims and converters, **bypassing** `DaoAuthenticationProvider`. JWT authority-mapping tests must test the dedicated converter rather than forcing every login path through `UserDetailsService`.
- For LDAP/SAML/OIDC or passkeys, confirm the real flow invokes the proper loader/checker; never assume username/password behavior applies to every authentication provider.

## 6. Setting Up a Spring Boot 3.x / Spring Security 6.5 Test Project

You need JDK **17+** and a Gradle project with Spring Boot 3.x managing Spring Security 6.x. Unit tests only need Spring Security core, config/crypto, and JUnit; in a simple Spring Boot project you can use:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-web'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

You **do not need** a database connection or an HTTP server to test `ProviderManager` directly in Section 7. `BCryptPasswordEncoder(4)` is used in unit tests to keep execution fast; **cost 4 is not a production recommendation**. For production, choose a cost benchmarked for your security requirements, `DelegatingPasswordEncoder` where appropriate, secret management, and safe hash migration.

If your project uses Spring Security **7.x/Boot 4.x**, cross-check APIs against that version, keep all modules on the same major version, and adjust your project's Java baseline. The code focuses on 6.5 APIs and does not assume a full Boot configuration is required to test a provider.

## 7. JUnit 5: A Real Test Suite for Status, Authorities, and Erasure

Create `src/test/java/example/auth/AccountComponentTest.java`. The code below is **a complete Java class** runnable with the dependencies from Section 6.

```java
package example.auth;

import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;

import org.springframework.security.authentication.AccountExpiredException;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.CredentialsExpiredException;
import org.springframework.security.authentication.DisabledException;
import org.springframework.security.authentication.LockedException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class AccountComponentTest {

    private static final String PASSWORD = "correct-for-component-test";

    // Low cost for fast unit tests; DO NOT use as a production policy.
    private final PasswordEncoder encoder = new BCryptPasswordEncoder(4);
    private final String encodedPassword = encoder.encode(PASSWORD);

    private UserDetails fixture(
            boolean disabled,
            boolean locked,
            boolean accountExpired,
            boolean credentialsExpired) {
        return User.withUsername("linh")
            .password(encodedPassword)
            .disabled(disabled)
            .accountLocked(locked)
            .accountExpired(accountExpired)
            .credentialsExpired(credentialsExpired)
            .authorities("ROLE_ANALYST", "SCOPE_reports:read")
            .build();
    }

    private UserDetails active() {
        return fixture(false, false, false, false);
    }

    private AuthenticationManager manager(UserDetails source) {
        // Only loads the "linh" account; returns a separate COPY each time.
        UserDetailsService loader = username -> {
            if (!"linh".equals(username)) {
                throw new UsernameNotFoundException("Not found");
            }
            return User.withUserDetails(source).build();
        };

        DaoAuthenticationProvider provider =
            new DaoAuthenticationProvider(loader);
        provider.setPasswordEncoder(encoder);

        // ProviderManager erases credentials by default after successful login.
        return new ProviderManager(List.of(provider));
    }

    private Authentication authenticate(
            UserDetails source, String username, String password) {
        return manager(source).authenticate(
            UsernamePasswordAuthenticationToken.unauthenticated(
                username, password
            )
        );
    }

    private Set<String> names(Authentication auth) {
        return auth.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .collect(Collectors.toSet());
    }

    @Test
    void activeAccountGetsExactlyLoadedAuthorities() {
        UserDetails source = active();
        Authentication auth = authenticate(source, "linh", PASSWORD);

        assertTrue(auth.isAuthenticated());
        assertEquals("linh", auth.getName());
        assertEquals(
            Set.of("ROLE_ANALYST", "SCOPE_reports:read"),
            names(auth)
        );
        assertFalse(names(auth).contains("ROLE_ADMIN"));
        assertTrue(auth.getPrincipal() instanceof UserDetails);
    }

    @Test
    void lockedAccountIsRejected() {
        assertThrows(LockedException.class, () ->
            authenticate(fixture(false, true, false, false),
                "linh", PASSWORD));
    }

    @Test
    void disabledAccountIsRejected() {
        assertThrows(DisabledException.class, () ->
            authenticate(fixture(true, false, false, false),
                "linh", PASSWORD));
    }

    @Test
    void expiredAccountIsRejected() {
        assertThrows(AccountExpiredException.class, () ->
            authenticate(fixture(false, false, true, false),
                "linh", PASSWORD));
    }

    @Test
    void expiredCredentialsAreRejected() {
        assertThrows(CredentialsExpiredException.class, () ->
            authenticate(fixture(false, false, false, true),
                "linh", PASSWORD));
    }

    @Test
    void wrongPasswordFails() {
        assertThrows(BadCredentialsException.class, () ->
            authenticate(active(), "linh", "wrong-password"));
    }

    @Test
    void unknownUserDoesNotExposeUsernameNotFound() {
        assertThrows(BadCredentialsException.class, () ->
            authenticate(active(), "unknown", "wrong-password"));
    }

    @Test
    void managerErasesRawAndPrincipalCredentials() {
        UserDetails stored = active();
        assertNotNull(stored.getPassword());

        Authentication auth = authenticate(stored, "linh", PASSWORD);

        // UsernamePasswordAuthenticationToken was erased by ProviderManager.
        assertNull(auth.getCredentials());

        // org.springframework.security.core.userdetails.User
        // implements CredentialsContainer; password inside principal is erased.
        UserDetails principal = (UserDetails) auth.getPrincipal();
        assertNull(principal.getPassword());

        // Yet the underlying data for looking up passwords on subsequent logins
        // still keeps the hash, because UserDetailsService returned a copy.
        assertNotNull(stored.getPassword());
        assertTrue(encoder.matches(PASSWORD, stored.getPassword()));
    }
}
```

Run in a Gradle project:

```bash
./gradlew test --tests example.auth.AccountComponentTest
```

**Expectation:** all eight `@Test` methods pass with compatible Spring Security 6.5/JUnit 5. File name matches class `AccountComponentTest` and directory matches package `example.auth`.

### Why do the tests call `ProviderManager`, not just the provider?

The specific requirement "**erase credentials after authentication**" lives in **`ProviderManager`**. A test calling only `provider.authenticate(...)` can receive a `UsernamePasswordAuthenticationToken` that still has the password in `credentials`, because the manager has not performed the erasure step yet. That is **not a bug** in the provider itself.

The test in Section 7 instantiates:

```java
return new ProviderManager(List.of(provider));
```

and calls `manager.authenticate(...)`, thus exercising the **provider + manager chain**—the exact scope under observation.

## 8. Deep Dive into Credential Erasure

### 8.1. `CredentialsContainer` and `ProviderManager`

`org.springframework.security.core.CredentialsContainer` defines:

```java
public interface CredentialsContainer {
    void eraseCredentials();
}
```

After successful authentication, `ProviderManager` checks by default whether the `Authentication` object implements `CredentialsContainer`. If so, it calls `eraseCredentials()` so sensitive credentials are not held longer than necessary.

For `UsernamePasswordAuthenticationToken`:

1. `getCredentials()` prior to erasure can hold the **raw password** submitted by the client.
2. `eraseCredentials()` clears the credentials field on the token.
3. Some `Authentication` types also forward the erasure call to the **principal and details** if those objects implement `CredentialsContainer`.
4. `org.springframework.security.core.userdetails.User` implements `CredentialsContainer`, so `User#getPassword()` can become `null` once the token's principal is erased.

Therefore, distinguish:

```text
Authentication.getCredentials()  -> may be the raw password
((UserDetails) authentication.getPrincipal()).getPassword()
                                 -> may be the encoded hash
Database/repository passwordHash -> source of truth used for next login
```

**Tests should verify which kind of data is being erased**, rather than asserting an ambiguous property like `password == ""`. With Spring Security's `User` implementation, the post-erasure value is typically `null`, not an empty string.

### 8.2. What must not be assumed?

- Not every authentication principal has a `getPassword()` method. JWT, SAML, OAuth2, passkey, and X.509 tokens have different structures.
- Not every credential can be scrubbed from every location in the JVM: copies of `String`s, request buffers, or other logs may still exist.
- Having erased credentials does **not** mean the session was terminated; `Authentication` remains authenticated and carries identity/authorities.
- Erasing credentials does **not** automatically revoke reset tokens, refresh tokens, or remember-me cookies.
- Erasing in RAM does **not** delete the password hash stored in the DB.
- Never log `Authentication.toString()` in production if the app uses custom principals/details holding sensitive fields.

### 8.3. `eraseCredentialsAfterAuthentication`

`ProviderManager` supports:

```java
providerManager.setEraseCredentialsAfterAuthentication(false);
```

Setting `false` avoids side effects on a cached `UserDetails` shared by reference, **yet allows credentials to linger longer in authentication/session objects**. This is a significant security trade-off, not a default fix to reach for.

**Prefer** changing `UserDetailsService`/caching to return **isolated copies**, or designing an `Authentication` principal that does not carry a password hash. Only disable erasure after a risk analysis and explicit tests covering what remains in sessions, logs, caches, and object graphs.

## 9. Subtle Bug: Cache Sharing a Reference with the Principal

Suppose `UserDetailsService` holds a `User` in memory and returns the **exact same instance** on every login.

```text
Cache/repository
   |
   +--> User object U, U.password = encoded hash
              |
              v
        DaoAuthenticationProvider returns principal = U
              |
              v
        ProviderManager.eraseCredentials()
              |
              v
        U.password = null   (same object as in cache!)
              |
              v
        Next login: service returns U.password == null
                         -> password verification fails
```

This is a shared-state bug, not Spring Security intentionally deleting hashes from the database. It commonly appears in tests using `InMemoryUserDetailsManager`, a fixture `Map`, or a homegrown cache without accounting for object references.

### 9.1. Test demonstrating the hazard

Standalone illustrative file `src/test/java/example/auth/SharedReferenceDangerTest.java`:

```java
package example.auth;

import java.util.List;

import org.junit.jupiter.api.Test;

import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

class SharedReferenceDangerTest {

    @Test
    void sharedPrincipalCanLoseItsStoredHash() {
        var encoder = new BCryptPasswordEncoder(4);
        UserDetails shared = User.withUsername("linh")
            .password(encoder.encode("fixture-only"))
            .roles("USER")
            .build();

        // INTENTIONALLY WRONG: same object for every lookup.
        UserDetailsService loader = username -> shared;
        var provider = new DaoAuthenticationProvider(loader);
        provider.setPasswordEncoder(encoder);
        var manager = new ProviderManager(List.of(provider));

        assertNotNull(shared.getPassword());

        manager.authenticate(
            UsernamePasswordAuthenticationToken.unauthenticated(
                "linh", "fixture-only"
            )
        );

        // Because principal and cache both point to shared:
        assertNull(shared.getPassword());

        // Next attempt has no encoded password left for matches().
        assertThrows(BadCredentialsException.class, () ->
            manager.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                    "linh", "fixture-only"
                )
            )
        );
    }
}
```

**This test models an anti-pattern**, not a configuration to use in production. Purpose: demonstrate why the second login fails even though the input password did not change. Test both with caching enabled and across multiple application instances.

**Note:** the example lambda intentionally ignores `username` to expose the reference bug. In a real `UserDetailsService`, always reject unknown usernames with `UsernameNotFoundException` instead of returning another account; otherwise you create an even worse flaw than losing a hash. Never put this lambda into a real application.

### 9.2. Recommended fix

If the source data is an encoded password + immutable flags/authorities, create a **fresh principal instance per lookup**:

```java
UserDetailsService safeLoader = username -> {
    if (!"linh".equals(username)) {
        throw new UsernameNotFoundException("Not found");
    }
    return User.withUserDetails(storedTemplate).build();
};
```

`storedTemplate` must be a source object that is **never** placed directly into `Authentication` to be erased. With custom caches:
- The cache stores account data/encoded hash as an independent snapshot.
- The provider receives an appropriate copy to match passwords and use as the principal.
- Never share the same mutable `User` holding a password between the cache and the authenticated result.
- Track invalidation when an account is locked/disabled or authorities change.
- Never disable `eraseCredentialsAfterAuthentication` system-wide just to work around a misdesigned cache.

## 10. Testing Authority Changes Between Two Logins

An `Authentication` is typically a **snapshot of permissions at creation time**. If roles change in the repository, existing sessions do not all update their authorities automatically.

Business requirement example:

```text
T0: linh has ROLE_READER
    -> login -> Authentication A1 [ROLE_READER]

T1: administrator revokes ROLE_READER, grants ROLE_AUDITOR

T2: linh logs in again
    -> Authentication A2 [ROLE_AUDITOR]

Session A1 not yet revoked/reloaded:
    -> may still carry the old ROLE_READER
```

**A good test suite must check two things:**
1. A **new** authentication loads authorities from the updated source, not stale data without policy justification.
2. For **existing sessions**, the app needs an invalidation/reload policy or dynamic permission checks if revocations must take effect immediately.

### Component test for authority reload

File `src/test/java/example/auth/AuthorityReloadTest.java`:

```java
package example.auth;

import java.util.List;
import java.util.Set;
import java.util.concurrent.atomic.AtomicReference;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;

import static org.junit.jupiter.api.Assertions.assertEquals;

class AuthorityReloadTest {

    @Test
    void newAuthenticationLoadsCurrentAuthorities() {
        var encoder = new BCryptPasswordEncoder(4);
        String hash = encoder.encode("fixture-only");

        AtomicReference<List<String>> source =
            new AtomicReference<>(List.of("ROLE_READER"));

        UserDetailsService loader = username -> {
            if (!"linh".equals(username)) {
                throw new UsernameNotFoundException("Not found");
            }
            // Creates a new User each time from the current snapshot.
            return User.withUsername("linh")
                .password(hash)
                .authorities(source.get().toArray(String[]::new))
                .build();
        };

        var provider = new DaoAuthenticationProvider(loader);
        provider.setPasswordEncoder(encoder);
        var manager = new ProviderManager(List.of(provider));

        Authentication first = manager.authenticate(
            UsernamePasswordAuthenticationToken.unauthenticated(
                "linh", "fixture-only"
            )
        );

        source.set(List.of("ROLE_AUDITOR"));

        Authentication second = manager.authenticate(
            UsernamePasswordAuthenticationToken.unauthenticated(
                "linh", "fixture-only"
            )
        );

        assertEquals(Set.of("ROLE_READER"), authorities(first));
        assertEquals(Set.of("ROLE_AUDITOR"), authorities(second));
        assertEquals(Set.of("ROLE_READER"), authorities(first));
    }

    private static Set<String> authorities(Authentication a) {
        return a.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .collect(Collectors.toSet());
    }
}
```

**Why not assert that roles changed on `first`?** `first` is the old `Authentication` created at T0. When the source reference changes, it does not flow backward into old objects. The application needs policies for **session revocation, reauthentication, real-time authorization queries, or cache invalidation** when permissions change.

### Watch out for `GrantedAuthoritiesMapper`

If the app uses:

```java
provider.setAuthoritiesMapper(authorities -> {
    // Map groups from external source to application authorities.
    return authorities;
});
```

then tests must assert `Authentication.getAuthorities()` **after the mapper**, not only the data returned by the loader. A mapper can add, rename, or drop roles. A mapper that grants `ROLE_ADMIN` solely from an email domain or an untrusted header is an authorization bug, not a password bug.

## 11. Writing a Custom `UserDetailsService`: What to Test Separately?

A repository-backed `UserDetailsService` typically needs to:
- Transform `username` into a lookup key per contract, avoiding tenant/case-sensitivity mix-ups.
- Return the **exact user** with that identity without leaking another user's data.
- Populate `getPassword()` with the encoded password for password login.
- Load `enabled`, locked/expired flags, and credential expiry accurately.
- Load authorities from a trusted source, independent of request headers/parameters.
- Throw `UsernameNotFoundException` if no user exists.
- Never return `null`, and never construct an anonymous user with authorities.
- Provide cache isolation and invalidation per policy.
- Never log raw passwords or full credential secrets.

### Dedicated test example for mapping from a record

Suppose the DB has a record:

```java
record AccountRecord(
    String username,
    String passwordHash,
    boolean enabled,
    boolean locked,
    boolean expired,
    boolean passwordExpired,
    Set<String> privileges
) {}
```

A loader might build:

```java
UserDetails loaded = User.withUsername(record.username())
    .password(record.passwordHash())
    .disabled(!record.enabled())
    .accountLocked(record.locked())
    .accountExpired(record.expired())
    .credentialsExpired(record.passwordExpired())
    .authorities(record.privileges().toArray(String[]::new))
    .build();
```

This is a **snippet to place inside the mapper class** given a `record` returned by the repository. Mapper tests should check each flag:

```java
assertEquals(!record.enabled(), !loaded.isEnabled());
assertEquals(record.locked(), !loaded.isAccountNonLocked());
assertEquals(record.expired(), !loaded.isAccountNonExpired());
assertEquals(record.passwordExpired(), !loaded.isCredentialsNonExpired());
```

Assertions use JUnit `Assertions.assertEquals` inside a test method; **avoid** double `!` expressions when comparing flags in production code because they hurt readability, though here they highlight the inverted polarity during mapping.

Pay special attention to password-expiry mapping: DBs often store `passwordExpiresAt` instead of a boolean; code should compare against an injected `Clock` so unit tests are deterministic rather than calling `Instant.now()` in multiple places and making tests flaky. Never conflate account expiry with credentials expiry.

## 12. `AccountStatusUserDetailsChecker` in Custom Authentication

An application may support OTT, SAML, passkey, pre-authenticated gateway, or JWT logins that use `UserDetailsService` to fetch local authorities. **Never assume** those providers run all the same pre/post checks as `DaoAuthenticationProvider` by default.

When a custom flow loads `UserDetails`, it can explicitly invoke:

```java
AccountStatusUserDetailsChecker checker =
    new AccountStatusUserDetailsChecker();
checker.check(loadedUserDetails);
```

This is a **snippet inside a method** after obtaining a valid verified identity source; it does not replace token signatures, challenges, passwords, or replay protection. `check` throws an exception if the status is disallowed per the checker.

### Direct unit test for the checker

```java
var checker = new AccountStatusUserDetailsChecker();

UserDetails locked = User.withUsername("linh")
    .password("{noop}test-only")
    .accountLocked(true)
    .roles("USER")
    .build();

assertThrows(LockedException.class, () -> checker.check(locked));
```

**Required imports:** `AccountStatusUserDetailsChecker`, `User`, `UserDetails`, `LockedException`, and static `Assertions.assertThrows`. This is a **snippet to insert inside a `@Test`**, using `{noop}` password only because the checker does not verify passwords; **never** use `{noop}` in production code.

In custom authentication flows, if you load `UserDetails` and skip `checker.check(...)` before creating an authenticated token directly, that new flow could log in locked users. Write regression tests for **every provider** deployed, especially recovery paths.

## 13. Testing Failures and Not Leaking Account Status

Exceptions such as:
- `LockedException`
- `DisabledException`
- `AccountExpiredException`
- `CredentialsExpiredException`
- `BadCredentialsException`

are very useful to assert **at the provider layer**. However, returning `"ACCOUNT_LOCKED"` directly to a public endpoint can create an **account-existence oracle**.

Distinguish:

| Location | Should causes be distinguished? |
| --- | --- |
| Provider unit/component tests | **Yes**; assert exact exception per contract |
| Restricted-access internal logs/audits | Yes, within necessary scope and privacy compliance |
| Public HTTP login responses | Consider returning a generic error message to prevent account enumeration |
| Identity-verified user channel | Can explain clearly after proof of ownership |
| Security incident investigation | Can use controlled reason codes without logging secrets |

For example, a public endpoint can return the same JSON/status for a nonexistent username or a wrong password, while provider tests still confirm `UsernameNotFoundException` is masked as `BadCredentialsException` by default.

**Do not "fix" this by turning every exception into `BadCredentialsException` inside a custom provider if that breaks auditing/policy.** Classify internally at the right layer, then normalize public responses in the authentication failure handler.

## 14. Testing Credentials Before and After Authentication: Inspecting the Right Object

A test anti-pattern:

```java
var user = User.withUsername("linh")
    .password(encoded)
    .roles("USER")
    .build();

assertNotNull(user.getPassword());
// Only tests the object before authentication => does not verify erasure.
```

A proper test runs through `ProviderManager` and checks the result:

```java
Authentication success = manager.authenticate(
    UsernamePasswordAuthenticationToken.unauthenticated(
        "linh", "correct-password"
    )
);

assertNull(success.getCredentials());
```

Then if the principal is a `User`, check:

```java
UserDetails principal = (UserDetails) success.getPrincipal();
assertNull(principal.getPassword());
```

**Do not assert** `storedAccountPasswordHash == null` in the DB: storage must retain the hash for future logins. If `storedUserDetails` loses its hash, that is likely a shared-reference bug as shown in Section 9.

### Checking whether other attributes of `Authentication` changed

After erasure, the following must **remain valid**:

```java
assertTrue(success.isAuthenticated());
assertEquals("linh", success.getName());
assertTrue(success.getAuthorities().stream()
    .anyMatch(a -> "ROLE_ANALYST".equals(a.getAuthority())));
```

Erasing credentials must never clear principal identity, authorities, or valid permissions. Erase only the secret.

## 15. Custom Principals and `CredentialsContainer`

If the application writes a `CustomUserDetails` or custom `Authentication`, do not assume the framework knows about every sensitive field on that class.

`CredentialsContainer` is the contract:

```java
public interface CredentialsContainer {
    void eraseCredentials();
}
```

A custom principal might hold:
- a password hash (if needed for password verification in the provider);
- an exchange token for downstream services;
- a temporary recovery code;
- an MFA secret or ephemeral key.

**Recommendation:** avoid putting unnecessary secrets into the principal/session in the first place. Use a separate data type for authentication results containing only identity and authorities. If you write a custom `CredentialsContainer`, test that `eraseCredentials()` actually clears sensitive fields and nested objects per contract.

Warnings:
- Clearing a `String` field on an object does not guarantee removing every immutable `String` copy already on the heap.
- Never include secrets in `toString`, `equals`, logs, JSON serialization, or exception messages.
- Never place raw credentials inside a `GrantedAuthority`.
- When a cached principal implements `CredentialsContainer`, you must still manage **copying/ownership** explicitly.

### Only assert erasure on supported types

For `JwtAuthenticationToken` or SAML tokens, principals and credentials have different semantics than username/password; secret-checking policies differ accordingly. `assertNull(((UserDetails) principal).getPassword())` only makes sense when the principal **actually** is a `UserDetails`.

## 16. Cases Where Caches and Mappers Cause "False-Pass" Tests

### Problem A — Mock only verifies it was called once

```java
verify(userDetailsService).loadUserByUsername("linh");
```

This is a useful Mockito assertion, yet it does not prove the loaded data was **accurate**. You must check status flags and authorities **after authentication**.

### Problem B — `@WithMockUser` supplies roles itself

```java
@WithMockUser(username = "linh", roles = "ADMIN")
```

`@WithMockUser` puts a **fake** `Authentication` into the test context, skipping the login filter, `UserDetailsService`, `DaoAuthenticationProvider`, and real password encoder. A controller test can pass with `ROLE_ADMIN` even if the production loader never loads that role.

Using `@WithMockUser` for simple authorization tests is valid, yet to test this lesson's goals you must:
1. Test the loader/mapper with account fixtures.
2. Test the provider/manager with real credentials in the test environment.
3. Test the filter chain/HTTP when end-to-end policy verification is needed.

### Problem C — Asserting expected permissions while missing extra permissions

```java
assertTrue(names(auth).contains("ROLE_READER"));
```

If `names(auth)` also includes an erroneously granted `ROLE_ADMIN`, the assertion still passes. For security-sensitive mappings, compare the **exact set** or at minimum assert that no out-of-contract sensitive authorities exist.

### Problem D — Test only constructs `UsernamePasswordAuthenticationToken.authenticated(...)`

```java
UsernamePasswordAuthenticationToken.authenticated(
    "linh",
    null,
    List.of(new SimpleGrantedAuthority("ROLE_ADMIN"))
);
```

The code above creates an already-authenticated `Authentication` **without verifying passwords or account status**. That can serve as a fixture in authorization tests, but it is **not** a `DaoAuthenticationProvider` component test and must never be how production creates sessions from HTTP input.

## 17. Component Tests, MockMvc, and Integration Tests: Boundaries

| Test level | What is actually tested | What is NOT proven |
| --- | --- | --- |
| Unit mapping record → `UserDetails` | Translating DB/account data into flags/authorities | Real password verification, sessions/filters |
| `DaoAuthenticationProvider` + `ProviderManager` | Username/password, status, authorities, erasure | CSRF, HTTP, redirects, sessions, full config |
| `AccountStatusUserDetailsChecker` directly | Status booleans | Passwords/roles/HTTP |
| `MockMvc` with `.with(user(...))` | Authorization for a mocked principal | Loader/provider/password login |
| `MockMvc` with `formLogin()` and real filter chain | HTTP request through auth filter, CSRF, success/failure | Distributed DB, email/SMS, real browser if mocked |
| Integration with DB/LDAP/IdP | Repository/backend, mapping, real tokens/identities | Every production operational scenario |
| End-to-end security/regression | Login path, sessions, account revocation, API permissions | Does not replace code audits and threat modeling |

### When real MockMvc is needed

For example, in Spring MVC, `spring-security-test` offers the `formLogin()` request post-processor to submit username/password through the filter:

```java
// Inside a @Test that already has MockMvc mvc, SecurityFilterChain, and DB/test-user.
mvc.perform(formLogin().user("linh").password("correct-password"))
   .andExpect(authenticated().withUsername("linh"));
```

Required imports in the Java test:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.authenticated;
```

This is a **snippet inside a test method**, not a standalone runnable file. If the app customizes username/password parameters, CSRF, or login URL, adjust the request post-processor to match the actual configuration. A passing `formLogin()` test does not by itself verify that DB roles refresh after an account is disabled during an older session.

## 18. Account Status Changes After Login: Old Sessions Do Not Vanish Automatically

Scenario:

```text
T0: account enabled, ROLE_READER
    -> login -> session A succeeds

T1: admin sets enabled=false

T2: session A still holds the old Authentication
    -> next request?
```

Do not automatically conclude the T2 request is denied merely because `UserDetailsService` now returns `isEnabled=false`: authorization typically reads the `Authentication` stored in the session and **does not reload the account on every request**.

If the product requires account locks to take effect immediately, one or more mechanisms are needed:
- Invalidate sessions when status changes.
- Revocation/token version/security stamp checks at the request boundary.
- Short TTLs on sessions/tokens, requiring reauthentication.
- Dynamic account-status checks on sensitive endpoints or via a policy engine.
- In multi-instance deployments, ensure revocation events propagate to caches/session stores.
- Prevent `remember-me` logins from bypassing disabled accounts; test remember-me flows explicitly.

### Tests to keep separate

1. **New login after lock:** rejected with `LockedException` per provider.
2. **Existing session after lock:** behavior depends on session revocation design; test separately.
3. **Password reset/recovery after lock:** must not automatically unlock the account unless policy allows it.
4. **Authority change:** new logins get new permissions; old sessions are revoked/reloaded or continue per configured TTL.
5. **JWT resource server:** must enforce issuer/audience/revocation policies separately; do not expect `UserDetailsService` to block still-valid tokens on its own.

## 19. Failure Analysis and Debugging

| Symptom | Common cause | How to verify |
| --- | --- | --- |
| User with `enabled=false` still logs in | Custom provider skips status checks; inverted flag mapping | Test loader + `AccountStatusUserDetailsChecker` or provider |
| Locked account throws `BadCredentialsException` | Wrong password hits different branch, custom checker, or exception masking | Use correct password in provider unit test; check pre/post config |
| `CredentialsExpiredException` does not appear | Test uses wrong password, or custom provider skips expiry check | Test with valid password and `credentialsExpired=true` |
| Test expects `ROLE_ADMIN` yet production lacks it | Test uses `@WithMockUser` instead of real loader | Assert `Authentication.getAuthorities()` after provider |
| Token has `ROLE_USER` yet `hasRole("USER")` fails | Prefix configured differently or authorities not loaded | Print authority names **in local test**, never log secrets |
| After login, `getCredentials()` still has password | Called `DaoAuthenticationProvider` directly or disabled erasure | Test through `ProviderManager`, check `eraseCredentialsAfterAuthentication` |
| First login works, second fails with same password | Cached `UserDetails` got erased due to shared object | Assert reference identity, copy template on load, check cache |
| Cache keeps old roles after admin revocation | Wrong TTL/invalidation | Test old/new login and session revocation |
| `NullPointerException` calling `getPassword()` | `User` principal was erased, or different principal type | Do not rely on password inside authenticated principal |
| Extra role granted during mapping | `GrantedAuthoritiesMapper` adds overly broad roles | Compare **exact** authority set, test allowlist/tenant |
| HTTP login returns 302/401 differing from unit exception | Filter success/failure handler and entrypoint produce response | Test `MockMvc` through real chain |
| Valid JWT accepted despite `enabled=false` | Resource server only verifies token and claims/policy, never calls DAO | Design token revocation or separate account lookup |

Never "fix" tests by disabling all account-status checks or retaining credentials in the session; fix data ownership and enforce checks at the right layer.

## 20. QA Checklist for the Development Team

### `UserDetails` contract

- [ ] Username is loaded for the exact tenant and account; nonexistent users are rejected.
- [ ] Encoded password matches the active encoder; plaintext is never stored.
- [ ] `enabled`, `locked`, `accountExpired`, and `credentialsExpired` map accurately and have individual tests.
- [ ] `getAuthorities()` contains only authorities from trusted sources with proper prefixes.
- [ ] No `ROLE_ADMIN` or sensitive out-of-contract permissions exist.
- [ ] `UserDetailsService` never returns a mutable principal shared with erased authentications.

### Provider and Manager

- [ ] Test right username, right password → authenticated.
- [ ] Test wrong password and unknown username → fail.
- [ ] Test all four bad status flags → expected exceptions.
- [ ] Test `ProviderManager` erases raw credentials after success by default.
- [ ] Test erasure does not destroy the hash source for subsequent logins.
- [ ] Test `Authentication` retains identity/authorities after erasure.
- [ ] If using `setAuthoritiesMapper`, assert the authority set after mapping.
- [ ] If changing `eraseCredentialsAfterAuthentication`, perform a concrete risk review.
- [ ] Do not mix Spring Security 6.x/7.x dependencies and APIs in one project.

### Integration and lifecycle

- [ ] HTTP tests traverse the real filter chain with CSRF when required.
- [ ] Existing sessions after user lock/role revocation have an explicit policy.
- [ ] User/authority cache invalidation is tested in clustered setups.
- [ ] Logins via LDAP, SAML, OIDC, OTT, WebAuthn, and Bearer have dedicated account-status policies if required.
- [ ] Public errors never disclose user existence, passwords, hashes, or internal details.
- [ ] Logging/security events never store raw credentials.
- [ ] Negative tests verify no weaker login path bypasses disabled accounts.
- [ ] Regression tests run whenever changing password encoders, database schemas, role mappers, or authentication providers.

## 21. Self-Check Questions

**Question 1:** Does `isAccountNonLocked()` returning `true` mean the account is locked?

**Answer:** No, `true` means **not locked**. Builder `.accountLocked(true)` creates the locked state, making `isAccountNonLocked()==false`.

**Question 2:** `DaoAuthenticationProvider` directly returns an `Authentication` still carrying credentials; is that a framework password-leak bug?

**Answer:** Not enough to conclude that. `ProviderManager` erases credentials on successful authentications by default. Erasure tests must go through the manager, not just the provider.

**Question 3:** Why does logging in with the same password succeed the first time and fail the second time after enabling caching?

**Answer:** The cache and authentication principal may point to the same mutable `User`; `eraseCredentials()` on the principal sets the cached password hash to null. Separate copies / fix cache ownership.

**Question 4:** A user has `ROLE_ADMIN` but `.disabled(true)`. Can they authenticate successfully?

**Answer:** No, in the default `DaoAuthenticationProvider` path it is blocked by account-status checks. High roles do not override the account-enabled policy.

**Question 5:** Does testing solely with `@WithMockUser(roles="ADMIN")` prove `UserDetailsService` loads `ROLE_ADMIN` properly?

**Answer:** No. That is a mocked principal bypassing the loader/provider. You need direct component tests and integration tests through the login filter.

**Question 6:** Does changing a role in the database immediately update every existing `Authentication` in active sessions?

**Answer:** Not by default. You must test session revocation/reloading and the policy on permission-change propagation delay.

**Question 7:** When `credentialsExpired=true`, if a test uses a wrong password, should it expect `CredentialsExpiredException`?

**Answer:** No. The password check can fail before the post-authentication check. Use the **correct** password to test credential expiry.

**Question 8:** Should `setEraseCredentialsAfterAuthentication(false)` be set on all applications to prevent cached login failures?

**Answer:** No. That retains sensitive credentials longer. Prefer returning copies of the principal and designing caches that do not share objects subject to erasure.

## 22. Summary

A solid Spring Security Authentication component test suite must verify **three independent properties**:

1. **Status:** account is enabled, not locked/expired, and credentials are non-expired. Each failure state must be tested individually with the right exception.
2. **Authorities:** `UserDetailsService` and mappers return the exact set of `GrantedAuthority` on the created `Authentication`; never under-grant, over-grant, or take authorities from untrusted data.
3. **Credential erasure:** with default `ProviderManager`, secrets on `Authentication` and applicable principals are erased after authentication **without** corrupting the hash source in the repository/cache.

Direct tests on `DaoAuthenticationProvider`/`ProviderManager` form the foundation, while real production apps also need tests for HTTP filters/sessions, post-login permission changes, multiple authentication mechanisms, and revocation. **Testing one successful login does not prove the system protects locked accounts or properly erases credentials.**

## 23. Official Documentation

- Spring Security 6.5 — `DaoAuthenticationProvider`: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html
- Spring Security 6.5 — Authentication Architecture, `ProviderManager`, and credentials erasure: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html
- Spring Security 6.5 — `CredentialsContainer`: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/credentials-container.html
- Spring Security 6.5 Javadoc — `DaoAuthenticationProvider`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/dao/DaoAuthenticationProvider.html
- Spring Security 6.5 Javadoc — `AbstractUserDetailsAuthenticationProvider`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/dao/AbstractUserDetailsAuthenticationProvider.html
- Spring Security 6.5 Javadoc — `ProviderManager`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ProviderManager.html
- Spring Security 6.5 Javadoc — `User.UserBuilder`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/userdetails/User.UserBuilder.html
- Spring Security 6.5 Javadoc — `UsernamePasswordAuthenticationToken`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/UsernamePasswordAuthenticationToken.html
- Spring Security 6.5 — Testing Authentication in Spring MVC: https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/authentication.html
