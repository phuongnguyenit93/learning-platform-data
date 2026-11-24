# Testing UserDetailsService with Existing, Missing, and Invalid Accounts in Spring Security

## 1. Lesson Objectives and Scope of Component Testing

In Spring Security, `UserDetailsService` is the component that **loads account data** for username/password authentication flows. This interface has only one core method:

```java
UserDetails loadUserByUsername(String username)
        throws UsernameNotFoundException;
```

Its responsibility is to look up the identifier, return a complete `UserDetails`, and prevent data belonging to another account from leaking into the result. A `UserDetails` typically contains the username, password hash or required credential metadata, authorities (permissions), and enabled/locked/expired flags.

**Scopes that must be distinguished immediately:**

- **Unit/component tests of UserDetailsService:** existing accounts are returned accurately; missing accounts throw `UsernameNotFoundException`; blank or improperly normalized names; disabled/locked/expired accounts have the **correct status flags**; passwords are stored as hashes; authorities are accurate and not mixed up with another user.
- **Authentication tests with DaoAuthenticationProvider:** credentials/passwords are verified via `PasswordEncoder.matches(...)`; the provider decides whether a locked/disabled/expired user can log in; the result is a successful `Authentication` or an appropriate `AuthenticationException`.
- **HTTP tests with SecurityFilterChain:** `POST /login`/HTTP Basic passes through filters, CSRF, redirect/challenge, and saves SecurityContext/session; endpoints requiring permissions are blocked when unauthorized.

**Do not assign password verification to UserDetailsService.** It only loads the record and should not check the raw password against the password in the request. `DaoAuthenticationProvider` (together with `PasswordEncoder`) handles password matching. Having `service.loadUserByUsername("alice")` return a user does not prove Alice can log in with a wrong password.

This lesson uses **Java 17+, Spring Boot 3.x, and Spring Security 6.x on Servlet/Spring MVC**. For Spring Security 7/Boot 4, the testing concepts remain the same, though test auto-configuration packages/APIs and constructors may differ; check your project's dependency version before copying.

### Expected outcomes after the lesson

1. Design repeatable CI tests for **existing, missing, and invalid** accounts.
2. Follow the contract properly: when a user is missing, do not return `null` or a fake user; when present, return a `UserDetails` belonging to the exact identity.
3. Separately verify the `enabled`, `accountNonLocked`, `accountNonExpired`, `credentialsNonExpired` flags and authorities.
4. Use Mockito/JUnit 5 for component tests, avoiding unnecessary DB and HTTP setup; use `DaoAuthenticationProvider` at the integration layer to test real credentials.
5. Include tests against user enumeration and risks of account/tenant mix-ups, duplicate usernames, or broken password hash/role mappings.
6. Know how to write tests that distinguish "failing due to CSRF or missing role" from "failing due to UserDetailsService".

## 2. Path of a Login Request and Responsibilities of Each Layer

```text
Browser POST /login
  username=alice, password=secret, valid CSRF
          |
          v
UsernamePasswordAuthenticationFilter
          | creates UsernamePasswordAuthenticationToken
          v
AuthenticationManager / ProviderManager
          |
          v
DaoAuthenticationProvider
          |
          | -- 1. loadUserByUsername("alice") ------------------+
          v                                                    |
UserDetailsService                                            |
          |                                                    |
          | -- 2. AccountRepository / LDAP / JDBC store        |
          v                                                    |
UserDetails(username, encodedPassword, authorities, flags) <---+
          |
          v
DaoAuthenticationProvider
          | 3. Check account locked / disabled / expired
          | 4. PasswordEncoder.matches(raw, encoded)
          | 5. Check credentialsNonExpired
          v
Authentication succeeded or AuthenticationException
          |
          v
SecurityContext + authorization/session (if successful)
```

**`UserDetailsService` neither creates `Authentication`, populates `SecurityContext`, nor authorizes routes.** Therefore, unit tests using only the service are insufficient to prove the HTTP login flow. Conversely, tests using `@WithMockUser` may pass authorization **without ever calling `UserDetailsService`**; it is suited for testing authorization, not repository lookup.

Per the Javadoc, `loadUserByUsername` **returns a populated record and never returns `null`**. If the user cannot be found or a user with valid authorities cannot be loaded per contract, it throws `UsernameNotFoundException`. Whether lookups are case-sensitive or case-insensitive is decided by the service/repository; you must define a normalization policy and test it, rather than assuming the framework normalizes identically across every datasource.

## 3. States to Test: Existing, Missing, and Invalid

| ID | Input/fixture | Expected at UserDetailsService | Expected at Provider/HTTP |
| --- | --- | --- | --- |
| U01 | Alice exists, enabled, has ROLE_USER | UserDetails matches Alice; encoded password; valid flags | Correct password → authenticated |
| U02 | Alice exists, wrong request password | UserDetails **is still loaded** | `BadCredentialsException` / login fail |
| U03 | Nonexistent username | `UsernameNotFoundException` | Not authenticated; usually masked as `BadCredentialsException` |
| U04 | Empty or whitespace username | Rejected per policy, no pointless DB query | Generic login failure |
| U05 | `null` username in direct service test | Rejected (choose consistent exception) | HTTP filter may normalize differently |
| U06 | `" Alice "`, DB canonical `alice` | Looked up by normalized key if policy allows | Login/authorities match canonical account |
| U07 | `ALICE` vs `alice` | Per defined case-insensitive/case-sensitive policy | Never falls into the wrong account |
| U08 | Account `enabled=false` | `isEnabled=false` | Provider rejects with `DisabledException` |
| U09 | Account `locked=true` | `isAccountNonLocked=false` | Provider rejects with `LockedException` |
| U10 | Account expired | `isAccountNonExpired=false` | Provider rejects with `AccountExpiredException` |
| U11 | Password credential expired | `isCredentialsNonExpired=false` | Provider rejects with `CredentialsExpiredException` |
| U12 | Account enabled but no valid roles | Rejected or handled per designed contract, no dangerous default role | Never accidentally gets `ROLE_ADMIN` |
| U13 | Account has roles USER,EDITOR | `ROLE_USER` and `ROLE_EDITOR`, not mixed with another account | Routes checking `hasRole`/`hasAuthority` work correctly |
| U14 | Same username in two tenants | Lookup must be scoped by stable tenant + normalized key | Never returns wrong tenant |
| U15 | Repository error/timeout | Infrastructure error distinguished internally, not faked as missing user or allowed to log in | Fail closed; log audit without leaking secrets |
| U16 | Password/account status changed in DB | Service reads current record or cache has invalidation policy | New auth does not use stale roles/status indefinitely |
| U17 | UserDetails has different username than requested | Accepted only if canonicalization/mapping allows | Principal bound to exact stable identity |
| U18 | Stored password raw/unsupported format | Mapping must preserve schema hash; data migration errors detected | Provider must not skip password check |
| U19 | Role taken from untrusted request/header | Service does not use it as an authority source | No privilege escalation |
| U20 | Concurrent requests loading two users | No mutable global "currentUser" | Never returns another user's details |

**Note on "invalid":** this is not a single state. *Missing account* ≠ *disabled account* ≠ *locked account* ≠ *credential expired* ≠ *wrong password* ≠ *database failure*. Handling across **service/provider/internal metrics** may differ, while external login responses should avoid revealing details that enable account enumeration.

## 4. Test Environment Setup (Spring Boot 3.x, Java 17+)

In a Spring Boot 3.x Gradle Groovy project that already has the Spring Boot plugin and Java toolchain configured, you need:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-web'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

`spring-boot-starter-test` typically brings JUnit Jupiter/Mockito/AssertJ onto the test classpath, while `spring-security-test` provides `MockMvc`, `csrf()`, `formLogin()`, `httpBasic()`, and `@WithMockUser`. You do not need to start a web server to **unit test** a `UserDetailsService` with a fake/mock repository.

Illustrative file layout:

```text
src/main/java/com/example/security/
  AccountRecord.java
  AccountRepository.java
  DatabaseUserDetailsService.java

src/test/java/com/example/security/
  DatabaseUserDetailsServiceTest.java
  DaoAuthenticationProviderTest.java

src/main/java/com/example/security/
  SecurityConfig.java              # only for the integration/HTTP section
```

The sample below intentionally uses a small repository interface, **without setting up Spring Data JPA**. By mocking a simple real interface, we isolate mapping/status testing from SQL details, transactions, and database infrastructure. For production, replace `AccountRepository` with an adapter calling JPA/JDBC/LDAP and write dedicated datastore integration tests.

### Fixture principles

- Test accounts `alice` and `bob` have **different** passwords and different roles to catch user mix-ups.
- Include enabled, disabled, locked, accountExpired, and credentialsExpired accounts.
- Passwords are **encoded with the same PasswordEncoder** that the provider will use in tests; never compare raw passwords against hash values with `equals`.
- Do not use production users/passwords/emails; all strings in this lesson are test fixtures only.
- For component unit tests, mock the repository so you know exactly which query key was used, what was returned, and whether the repository was called on invalid input.

## 5. Model and Repository Contract for the Example

### 5.1. AccountRecord.java

In `src/main/java/com/example/security/AccountRecord.java`:

```java
package com.example.security;

import java.util.Set;

public record AccountRecord(
        String usernameKey,
        String passwordHash,
        boolean enabled,
        boolean locked,
        boolean accountExpired,
        boolean credentialsExpired,
        Set<String> roles) {
}
```

`usernameKey` is a normalized key unique within the demo's namespace/tenant; a real system should have an immutable account ID, tenant ID, and dedicated security status fields. These booleans are a snapshot read from the datastore, **not the result of password comparison**.

### 5.2. AccountRepository.java

In `src/main/java/com/example/security/AccountRepository.java`:

```java
package com.example.security;

import java.util.Optional;

public interface AccountRepository {
    Optional<AccountRecord> findByUsernameKey(String usernameKey);
}
```

This is not a Spring Data interface; **a real adapter implementation is needed** when connecting to a DB. Use `Optional.empty()` to represent not found; never return `null` for repository results under this contract. Test mocks supply responses without connecting to a DB.

### 5.3. UserDetailsService mapping from record

In `src/main/java/com/example/security/DatabaseUserDetailsService.java`:

```java
package com.example.security;

import java.util.Locale;
import java.util.Objects;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;

public final class DatabaseUserDetailsService
        implements UserDetailsService {

    private final AccountRepository repository;

    public DatabaseUserDetailsService(AccountRepository repository) {
        this.repository = Objects.requireNonNull(repository);
    }

    @Override
    public UserDetails loadUserByUsername(String rawUsername)
            throws UsernameNotFoundException {

        if (rawUsername == null || rawUsername.isBlank()) {
            throw new UsernameNotFoundException("Account cannot be loaded");
        }

        String key = rawUsername.strip().toLowerCase(Locale.ROOT);
        AccountRecord account = repository.findByUsernameKey(key)
                .orElseThrow(() -> new UsernameNotFoundException(
                        "Account cannot be loaded"));

        // Roles in the DB are managed values like USER/EDITOR;
        // do not take roles directly from requests or grant default authorities.
        if (account.roles() == null || account.roles().isEmpty()) {
            throw new UsernameNotFoundException("Account cannot be loaded");
        }

        String[] authorities = account.roles().stream()
                .map(role -> "ROLE_" + role)
                .sorted()
                .toArray(String[]::new);

        return User.withUsername(account.usernameKey())
                .password(account.passwordHash())
                .authorities(authorities)
                .disabled(!account.enabled())
                .accountLocked(account.locked())
                .accountExpired(account.accountExpired())
                .credentialsExpired(account.credentialsExpired())
                .build();
    }
}
```

**Read the 4-flag mapping carefully:**

| DB field | UserDetails field | Meaning |
| --- | --- | --- |
| `enabled=true` | `isEnabled() == true` | Account is allowed to authenticate |
| `locked=true` | `isAccountNonLocked() == false` | Inverted! Account is currently locked |
| `accountExpired=true` | `isAccountNonExpired() == false` | Account has expired |
| `credentialsExpired=true` | `isCredentialsNonExpired() == false` | Password/credential has expired |

`.disabled(boolean)` accepts **whether it is disabled**, while `isEnabled()` returns **whether it is still enabled**; similarly `.accountLocked(true)` sets `isAccountNonLocked()=false`. This is a very easy place to invert flags by mistake when mapping from a DB.

**Normalization policy in the example:** `strip()` and `toLowerCase(Locale.ROOT)`; this fits when database usernames are stored canonically case-insensitively. If your system has case-sensitive usernames, internationalized emails, Unicode normalization, tenant-scoped logins, or multi-attribute usernames, you **must change the policy** and write corresponding tests. Never merge two distinct accounts merely by lowercasing.

**Roles contract:** the demo rejects an empty role set to avoid creating an under-specified `UserDetails`. In designs allowing authenticated users with no roles, you must explicitly decide how `authenticated()` authorization works while obeying the appropriate service/provider contract; **do not automatically add `ROLE_USER` just to make tests pass**. Roles are managed from a trusted server datastore, not from the caller's `username`/HTTP headers.

**Password security:** `UserDetails.getPassword()` is a hash (or encoder-supported credential representation); the service does not run `password.equals(raw)`. `User.withUsername(...).password(...)` in the example does not automatically encode the string. If `AccountRecord.passwordHash` contains a raw password, that is a data bug—never "fix" it by comparing plaintext passwords inside `UserDetailsService`.

## 6. JUnit 5 + Mockito: Testing the Service with Existing and Missing Accounts

File `src/test/java/com/example/security/DatabaseUserDetailsServiceTest.java`:

```java
package com.example.security;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import java.util.Optional;
import java.util.Set;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

class DatabaseUserDetailsServiceTest {

    private AccountRepository repository;
    private DatabaseUserDetailsService service;
    private PasswordEncoder encoder;

    @BeforeEach
    void setUp() {
        repository = mock(AccountRepository.class);
        service = new DatabaseUserDetailsService(repository);
        // Cost 4 so tests run fast; use an appropriate cost in production.
        encoder = new BCryptPasswordEncoder(4);
    }

    private AccountRecord account(String username) {
        return new AccountRecord(
                username,
                encoder.encode("correct-pass"),
                true, false, false, false,
                Set.of("USER", "EDITOR"));
    }

    @Test
    void existingAccountReturnsCanonicalIdentityAndHash() {
        when(repository.findByUsernameKey("alice"))
                .thenReturn(Optional.of(account("alice")));

        UserDetails result = service.loadUserByUsername(" Alice ");

        assertEquals("alice", result.getUsername());
        assertTrue(result.isEnabled());
        assertTrue(result.isAccountNonLocked());
        assertTrue(result.isAccountNonExpired());
        assertTrue(result.isCredentialsNonExpired());
        assertTrue(encoder.matches("correct-pass", result.getPassword()));
        assertNotEquals("correct-pass", result.getPassword());

        assertTrue(result.getAuthorities().stream()
                .anyMatch(a -> a.getAuthority().equals("ROLE_USER")));
        assertTrue(result.getAuthorities().stream()
                .anyMatch(a -> a.getAuthority().equals("ROLE_EDITOR")));
        assertEquals(2, result.getAuthorities().size());

        verify(repository).findByUsernameKey("alice");
        verifyNoMoreInteractions(repository);
    }

    @Test
    void missingAccountThrowsInsteadOfReturningNull() {
        when(repository.findByUsernameKey("ghost"))
                .thenReturn(Optional.empty());

        assertThrows(UsernameNotFoundException.class,
                () -> service.loadUserByUsername("ghost"));

        verify(repository).findByUsernameKey("ghost");
        verifyNoMoreInteractions(repository);
    }

    @Test
    void nullOrBlankUsernameIsRejectedWithoutDatabaseCall() {
        assertThrows(UsernameNotFoundException.class,
                () -> service.loadUserByUsername(null));
        assertThrows(UsernameNotFoundException.class,
                () -> service.loadUserByUsername(""));
        assertThrows(UsernameNotFoundException.class,
                () -> service.loadUserByUsername("   "));

        verifyNoInteractions(repository);
    }

    @Test
    void uppercaseLookupUsesConfiguredCanonicalization() {
        when(repository.findByUsernameKey("alice"))
                .thenReturn(Optional.of(account("alice")));

        UserDetails result = service.loadUserByUsername("ALICE");

        assertEquals("alice", result.getUsername());
        verify(repository).findByUsernameKey("alice");
    }

    @Test
    void unknownUserDoesNotReturnAnotherUsersData() {
        when(repository.findByUsernameKey("bob"))
                .thenReturn(Optional.empty());
        when(repository.findByUsernameKey("alice"))
                .thenReturn(Optional.of(account("alice")));

        assertThrows(UsernameNotFoundException.class,
                () -> service.loadUserByUsername("bob"));
        assertEquals("alice",
                service.loadUserByUsername("alice").getUsername());

        verify(repository).findByUsernameKey("bob");
        verify(repository).findByUsernameKey("alice");
    }

    @Test
    void noRolesDoesNotGainAnyDefaultAuthority() {
        AccountRecord noRoles = new AccountRecord(
                "alice", encoder.encode("correct-pass"),
                true, false, false, false, Set.of());
        when(repository.findByUsernameKey("alice"))
                .thenReturn(Optional.of(noRoles));

        assertThrows(UsernameNotFoundException.class,
                () -> service.loadUserByUsername("alice"));
    }
}
```

### Why are these unit tests at the "right layer"?

- No `@SpringBootTest`/HTTP/DB: tests are fast and isolate the `AccountRecord → UserDetails` mapping logic.
- `verify(repository).findByUsernameKey("alice")` proves normalization works correctly without querying with an unnormalized string.
- `assertThrows(UsernameNotFoundException.class, ...)` is far different from returning `null` or a fake account; callers know the user was not found per contract.
- Checking `encoder.matches(...)` only confirms the fixture hash was preserved intact and is encoder-compatible; it does **not** prove the service checks credentials itself. Real password checking is in the provider tests in Section 8.
- `verifyNoInteractions(repository)` catches accidental DB queries on null/blank input, which could otherwise lead to injection or reading wrong data.
- Checks exact `ROLE_USER`/`ROLE_EDITOR` names without fabricating permissions absent from the record.

Run:

```bash
./gradlew test --tests com.example.security.DatabaseUserDetailsServiceTest
```

The test code in Section 6 runs once the three production files and Section 4 dependencies exist. No repository implementation is needed because Mockito creates the mock. On Windows, use `gradlew.bat test --tests com.example.security.DatabaseUserDetailsServiceTest`.

**Do not use `@WithMockUser` in `UserDetailsService` unit tests.** That annotation constructs an authenticated principal to test the security context, never calls `loadUserByUsername`, and can produce false positives.

## 7. Testing Locked, Disabled, or Expired Accounts

Inside the same `DatabaseUserDetailsServiceTest.java`, you can add these standalone methods:

```java
@Test
void disabledUserIsNotSilentlyMarkedEnabled() {
    AccountRecord disabled = new AccountRecord(
            "alice", encoder.encode("correct-pass"),
            false, false, false, false, Set.of("USER"));
    when(repository.findByUsernameKey("alice"))
            .thenReturn(Optional.of(disabled));

    UserDetails details = service.loadUserByUsername("alice");

    assertFalse(details.isEnabled());
    assertTrue(details.isAccountNonLocked());
}

@Test
void lockedUserIsNotMarkedUnlocked() {
    AccountRecord locked = new AccountRecord(
            "alice", encoder.encode("correct-pass"),
            true, true, false, false, Set.of("USER"));
    when(repository.findByUsernameKey("alice"))
            .thenReturn(Optional.of(locked));

    UserDetails details = service.loadUserByUsername("alice");

    assertFalse(details.isAccountNonLocked());
    assertTrue(details.isEnabled());
}

@Test
void expiredAccountAndCredentialsRemainDistinct() {
    AccountRecord expiredAccount = new AccountRecord(
            "alice", encoder.encode("correct-pass"),
            true, false, true, false, Set.of("USER"));
    when(repository.findByUsernameKey("alice"))
            .thenReturn(Optional.of(expiredAccount));

    assertFalse(service.loadUserByUsername("alice")
            .isAccountNonExpired());

    AccountRecord expiredPassword = new AccountRecord(
            "alice", encoder.encode("correct-pass"),
            true, false, false, true, Set.of("USER"));
    when(repository.findByUsernameKey("alice"))
            .thenReturn(Optional.of(expiredPassword));

    assertFalse(service.loadUserByUsername("alice")
            .isCredentialsNonExpired());
    assertTrue(service.loadUserByUsername("alice")
            .isAccountNonExpired());
}
```

These are **additional methods for the previous test class**, not a standalone Java file. They test flag mapping (at the service layer); they do not yet prove the provider will reject login. Some applications have additional account statuses such as disabled-by-admin, locked-until, must-change-password, or tenant-suspended; these must be mapped to `UserDetails` flags or checked explicitly in the provider per policy.

**Do not "fix" tests by throwing `UsernameNotFoundException` for every disabled/locked account in the service** if the system is meant to preserve distinct internal statuses. Pick one consistent contract: the service returns `UserDetails` with flags; the provider decides whether authentication can succeed. You can mask UI messages to prevent enumeration while keeping accurate internal logs/metrics.

## 8. Real DaoAuthenticationProvider Tests: Wrong Passwords and Account Status

This is the next layer after the service. Upon receiving `UserDetails`, `DaoAuthenticationProvider` uses `PasswordEncoder` and status checks to authenticate. Spring Security 6.5 provides the constructor `new DaoAuthenticationProvider(UserDetailsService)` and setter `setPasswordEncoder(...)`.

Create `src/test/java/com/example/security/DaoAuthenticationProviderTest.java`:

```java
package com.example.security;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import java.util.Optional;
import java.util.Set;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.core.Authentication;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.DisabledException;
import org.springframework.security.authentication.LockedException;
import org.springframework.security.authentication.AccountExpiredException;
import org.springframework.security.authentication.CredentialsExpiredException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

class DaoAuthenticationProviderTest {

    private AccountRepository repository;
    private DaoAuthenticationProvider provider;
    private PasswordEncoder encoder;

    @BeforeEach
    void setUp() {
        repository = mock(AccountRepository.class);
        encoder = new BCryptPasswordEncoder(4);
        DatabaseUserDetailsService service =
                new DatabaseUserDetailsService(repository);
        provider = new DaoAuthenticationProvider(service);
        provider.setPasswordEncoder(encoder);
    }

    private AccountRecord fixture(boolean enabled,
                                  boolean locked,
                                  boolean accountExpired,
                                  boolean credentialsExpired) {
        return new AccountRecord("alice",
                encoder.encode("correct-pass"),
                enabled, locked, accountExpired,
                credentialsExpired, Set.of("USER"));
    }

    private void exists(AccountRecord record) {
        when(repository.findByUsernameKey("alice"))
                .thenReturn(Optional.of(record));
    }

    private Authentication login(String username, String rawPassword) {
        return provider.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                        username, rawPassword));
    }

    @Test
    void existingUserAndCorrectPasswordAuthenticate() {
        exists(fixture(true, false, false, false));

        Authentication result = login("alice", "correct-pass");

        assertNotNull(result);
        assertTrue(result.isAuthenticated());
        assertEquals("alice", result.getName());
        assertTrue(result.getAuthorities().stream()
                .anyMatch(a -> a.getAuthority().equals("ROLE_USER")));
    }

    @Test
    void wrongPasswordFailsEvenThoughUserExists() {
        exists(fixture(true, false, false, false));

        assertThrows(BadCredentialsException.class,
                () -> login("alice", "wrong-pass"));
    }

    @Test
    void missingAccountIsNotAuthenticated() {
        when(repository.findByUsernameKey("ghost"))
                .thenReturn(Optional.empty());

        // Spring Security hides UsernameNotFoundException by default,
        // converting it to BadCredentialsException at the provider boundary.
        assertThrows(BadCredentialsException.class,
                () -> login("ghost", "any-pass"));
    }

    @Test
    void disabledUserCannotAuthenticateWithCorrectPassword() {
        exists(fixture(false, false, false, false));

        assertThrows(DisabledException.class,
                () -> login("alice", "correct-pass"));
    }

    @Test
    void lockedUserCannotAuthenticateWithCorrectPassword() {
        exists(fixture(true, true, false, false));

        assertThrows(LockedException.class,
                () -> login("alice", "correct-pass"));
    }

    @Test
    void expiredAccountCannotAuthenticateWithCorrectPassword() {
        exists(fixture(true, false, true, false));

        assertThrows(AccountExpiredException.class,
                () -> login("alice", "correct-pass"));
    }

    @Test
    void expiredCredentialsCannotAuthenticateWithCorrectPassword() {
        exists(fixture(true, false, false, true));

        assertThrows(CredentialsExpiredException.class,
                () -> login("alice", "correct-pass"));
    }
}
```

Note: `Authentication` is in package `org.springframework.security.core.Authentication`, **not** in `org.springframework.security.authentication.Authentication`. The example above already uses the exact import below for `Authentication`:

```java
import org.springframework.security.core.Authentication;
```

This is the import line already used in the example, not a second import to add to the same file. Do not use `org.springframework.security.authentication.Authentication`; the exception imports still belong to `org.springframework.security.authentication`. The correction preserves the exact test logic.

**Why not use `@WithMockUser` at this layer?** The provider must genuinely call `UserDetailsService` and then run `PasswordEncoder` and account-status checks. A mocked principal could make tests pass even with a wrong password or a disabled account.

**Important distinction between the two exception types:**

- At the **service**, looking up nonexistent `ghost` → `UsernameNotFoundException`.
- At the **provider**, `AbstractUserDetailsAuthenticationProvider` by default **hides the difference between a missing user and a wrong password** using `BadCredentialsException` (`hideUserNotFoundExceptions=true`). That helps reduce user enumeration, though timing side-channels still need separate evaluation.
- Locked/disabled/expired accounts throw specialized internal exceptions; **do not send raw exception names** to the public login page where they would leak account state.

In production, use a BCrypt cost suited to your capacity/hardware, Argon2, or `DelegatingPasswordEncoder` with a clear policy—do not use test cost 4 as a default security level. Never write `rawPassword`, hashes, or exception messages containing sensitive usernames into unprotected logs.

## 9. Repository/JPA Integration Tests: Catching Bugs Mockito Misses

Mockito tests are fast but **do not verify SQL/JPA queries**, unique indexes, collation, lazy loading, or real transactions. When the adapter uses Spring Data JPA/JDBC, dedicated tests are needed:

1. Data for Alice exists → repository queries the exact normalized username and returns one record.
2. Missing record → `Optional.empty()`; never fall back to returning the first account.
3. Duplicate `usernameKey` → schema must enforce a **UNIQUE constraint** per namespace/tenant. Never arbitrarily pick one row if a query returns multiple.
4. Case-insensitive policy → use a normalized column and unique constraint per policy, avoiding cases where one DB allows `Alice` and `alice` while another treats them as duplicates.
5. Tenant binding → the key must include tenant/realm if usernames are only unique **within a tenant**, never querying table-wide by username alone.
6. Stored passwords match the hash format expected by the encoder; test compatibility for migrations to `{bcrypt}`/Argon2.
7. Roles/authorities are fully loaded **within the transaction**; after the session closes, no unexpected `LazyInitializationException` occurs.
8. Disabled/locked/expired records map accurately, and account state updates take effect under the designed cache policy.
9. DB outages/timeouts must **fail closed**, never creating a default user or mapping every exception to a missing user to hide operational errors.
10. Concurrent data for two users never bleeds across due to wrong cache keys or shared mutable state.

With Spring Boot 3.x and Spring Data JPA, you can use `@DataJpaTest` with H2/Testcontainers to test the real repository. Prefer Testcontainers or a production-compatible database when case sensitivity, collation, or unique constraints play a security role. H2 can behave differently from PostgreSQL/MySQL regarding Unicode/collation. Never conclude that JPA mappings are safe solely because unit mocks pass.

### Tenant issue when UserDetailsService only receives a username

`loadUserByUsername(String username)` **has no tenant parameter**. If two tenants both have `username="alice"`, the service cannot know which tenant the request belongs to on its own. Proper designs depending on architecture:

- Design a globally unique account key, using an immutable internal user ID for authorization/tenant scoping.
- Map a composite identifier validated per policy (e.g., safely formatted tenant+username) and resolve it inside a custom authentication flow.
- Write a dedicated `AuthenticationProvider` that receives the verified tenant and looks up with a composite key.

**Do not trust an arbitrary tenant value declared by the request to grant cross-tenant authorities.** When IP, HTTP request, or tenant context is needed, per the Spring Security FAQ, `UserDetailsService` only takes a username; do not rely on loose thread-local session state without an explicit policy.

## 10. HTTP Application Testing: Where Users See 401/302/403

Service and provider unit examples do not prove HTTP form login. For a Spring MVC application using form login, typical HTTP behavior is:

```text
POST /login username=alice password=correct-pass + CSRF:
    -> form authentication success -> 302 redirect per success handler
POST /login username=alice password=wrong-pass + CSRF:
    -> authentication fail -> 302 /login?error (by default)
POST /login username=ghost password=any + CSRF:
    -> authentication fail -> 302 /login?error
GET /private (not logged in):
    -> redirect /login if FormLogin entry point
GET /admin (logged in ROLE_USER, requires ROLE_ADMIN):
    -> HTTP 403
POST /login missing CSRF:
    -> may return 403 from CsrfFilter before calling UserDetailsService
```

If the app uses HTTP Basic only, missing/wrong passwords normally return 401 with `WWW-Authenticate: Basic ...`; in Form Login, anonymous requests usually receive a **302 redirect** to the login page. Status **403** does not prove a user is logged in: CSRF can block anonymous requests too.

### SecurityFilterChain fragment

In a Spring Boot 3 Servlet app with a `UserDetailsService` bean or properly configured authentication provider:

```java
@Bean
SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
    return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/public/**").permitAll()
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .build();
}
```

This is a **fragment inside a `@Configuration` class**, requiring a `UserDetailsService`/repository bean and imports for `HttpSecurity`, `SecurityFilterChain`, and `Customizer`; it does not run standalone. **Do not disable CSRF** just to make POST login pass in tests. Without a real custom `UserDetailsService` bean/adapter, Spring Boot cannot construct a proper production authentication flow from demo source snippets alone.

### MockMvc integration fragments

In `@SpringBootTest @AutoConfigureMockMvc` with a `MockMvc mvc` bean, account repository/test datasource fixtures, and Spring Security Test:

```java
// Illustrative code inside a test class, with static imports get, post,
// csrf, status, redirectedUrlPattern, and test fixtures already present.

mvc.perform(post("/login")
        .with(csrf())
        .param("username", "alice")
        .param("password", "correct-pass"))
    .andExpect(status().is3xxRedirection());

// On wrong password, default formLogin redirects to login?error:
mvc.perform(post("/login")
        .with(csrf())
        .param("username", "alice")
        .param("password", "wrong-pass"))
    .andExpect(status().is3xxRedirection());

// Requests missing CSRF are blocked before authentication:
mvc.perform(post("/login")
        .param("username", "alice")
        .param("password", "correct-pass"))
    .andExpect(status().isForbidden());
```

**Asserting 302 alone is not enough**: both success and failure can redirect. Use `SecurityMockMvcResultMatchers.authenticated()`/`unauthenticated()`, `redirectedUrl(...)`, check the session/Principal on subsequent requests, or verify `UserDetailsService` was invoked in the expected flow while checking DB side effects. If a request hits `CsrfFilter` and gets 403 before auth, that is **not testing a wrong password or missing user**.

Conversely, service unit tests should not boot the entire app and send `POST /login` for every case: that is slow, couples to CSRF/routing/DB, and makes root-cause diagnosis harder.

## 11. Standalone Java 17: Modeling the Three Account Groups to Run Locally

The code below uses plain JDK 17 with no Spring installed. It models the **account lookup contract**, not a production `UserDetailsService`. The `passwordHash` values in the demo are merely labels distinguishing raw vs stored credentials; it does not store bcrypt, perform password authentication, and must not be copied as a real login mechanism.

Save as `UserDirectoryCasesLab.java`:

```java
import java.util.HashMap;
import java.util.Locale;
import java.util.Map;
import java.util.Set;

public final class UserDirectoryCasesLab {

    record Account(String username, String passwordHash,
                   boolean enabled, boolean locked, Set<String> roles) {}

    static final class MissingAccount extends RuntimeException {
        MissingAccount() {
            super("Account cannot be loaded");
        }
    }

    static final class Directory {
        private final Map<String, Account> data = new HashMap<>();

        Directory() {
            data.put("alice", new Account(
                    "alice", "{bcrypt}fixture-hash-not-real",
                    true, false, Set.of("USER")));
            data.put("bob", new Account(
                    "bob", "{bcrypt}fixture-hash-not-real",
                    false, false, Set.of("USER")));
            data.put("carol", new Account(
                    "carol", "{bcrypt}fixture-hash-not-real",
                    true, true, Set.of("EDITOR")));
        }

        Account load(String username) {
            if (username == null || username.isBlank()) {
                throw new MissingAccount();
            }
            String key = username.strip().toLowerCase(Locale.ROOT);
            Account account = data.get(key);
            if (account == null || account.roles().isEmpty()) {
                throw new MissingAccount();
            }
            return account;
        }
    }

    static boolean rejected(Directory directory, String name) {
        try {
            directory.load(name);
            return false;
        } catch (MissingAccount expected) {
            return true;
        }
    }

    public static void main(String[] args) {
        Directory directory = new Directory();

        Account alice = directory.load(" ALICE ");
        System.out.println("existingCanonical=" +
                alice.username().equals("alice"));
        System.out.println("existingEnabled=" + alice.enabled());
        System.out.println("missingRejected=" +
                rejected(directory, "ghost"));
        System.out.println("blankRejected=" +
                rejected(directory, "  "));
        System.out.println("disabledFlag=" +
                !directory.load("bob").enabled());
        System.out.println("lockedFlag=" +
                directory.load("carol").locked());
        System.out.println("authoritiesFromAliceOnly=" +
                alice.roles().equals(Set.of("USER")));
    }
}
```

Run with Java 17+:

```bash
javac UserDirectoryCasesLab.java
java UserDirectoryCasesLab
```

**Exact** stdout:

```text
existingCanonical=true
existingEnabled=true
missingRejected=true
blankRejected=true
disabledFlag=true
lockedFlag=true
authoritiesFromAliceOnly=true
```

**Explanation:** found/canonical user, missing/blank, disabled/locked, and role mapping are verified independently; **nowhere is a password compared** because the `Directory` model only loads records. This lab does not prove real Provider/Spring Security behavior: the JUnit tests in Sections 6 and 8 are what exercise real Spring APIs.

## 12. Caching, Concurrency, and Potentially Stale Data

### 12.1. When UserCache is used

Spring Security can cache `UserDetails` (e.g., via caching provider/services or application-level caches). Tests should ask:

- Does a newly disabled/locked account keep getting retrieved from the cache with `isEnabled=true`?
- Does a user whose `ROLE_ADMIN` was just revoked keep the old permission in a session/token/Authentication?
- After a password change, for how long does a cached old hash still work in new authentications?
- If the cache key is only the username, do two tenants sharing a username return the wrong user?
- Are cache TTL/invalidation consistent across instances?

**Note:** updating `UserDetailsService` does not mean already-authenticated HTTP sessions immediately become invalid; `SecurityContext`/sessions or JWTs have their own lifecycles. Tests must distinguish **new authentication** after a data change from **previously issued sessions**. If the product needs instant session revocation, a dedicated session registry/revocation mechanism is required.

### 12.2. Password/credentials erasure

Spring Security can erase credentials from `Authentication` after login to reduce exposure risk. If a cached `UserDetails` is reused as the **same mutable object** and `eraseCredentials()` clears the password field, subsequent logins may fail because the cache returns an object missing its hash. Test that the cache implementation returns an appropriate copy or disables caching as needed; never turn off credential erasure just to mask the symptom.

### 12.3. Concurrency

Two requests concurrently loading `alice` and `bob` must return their respective records. The service must not store instance fields like `currentUser`, `currentPassword`, or mutable `selectedTenant` shared across requests. If caching is used, key strictly by tenant/account; in reactive repositories, do not pull session context from servlet thread-locals inside the service without an explicit design.

Concurrency tests can use `ExecutorService` + latches, though they are only meaningful when the real code has caches/mutable state; avoid adding multi-threaded tests to a stateless service just to complicate the suite. For DBs, rely on transactions/unique constraints to ensure duplicate accounts are not returned arbitrarily.

## 13. Common Mistakes When Writing Tests

| Mistake | Why it is wrong | How to fix |
| --- | --- | --- |
| Returning `null` when user is missing | Violates `UserDetailsService` contract | Throw `UsernameNotFoundException` |
| Unit testing wrong password with `service.loadUserByUsername(...)` | Service does not accept raw passwords | Test `DaoAuthenticationProvider` with encoder |
| Expecting `UsernameNotFoundException` directly from default provider | Provider normally masks it as `BadCredentialsException` | Separate service and provider assertions |
| Asserting only username without roles/flags | Could open permissions or ignore locked accounts | Assert identity, authorities, and all 4 status flags |
| Mapping `locked=true` to `isAccountNonLocked=true` | Inverted flag polarity | Add separate tests for locked and unlocked |
| Auto-creating `ROLE_USER` when DB roles are empty | Privilege escalation or broken business rules | Fail closed per documented contract |
| Calling `PasswordEncoder.encode(raw)` and comparing two hashes with `equals` | BCrypt is salted; hashes differ each time | Use `matches(raw, hash)` |
| Using `{noop}` and plaintext test passwords as production standard | Stored passwords are unprotected | Always use hashes + proper PasswordEncoder |
| Mocking `UserDetailsService` while testing it | Test does not execute the implementation | Mock **repository**, test real service |
| Using `@WithMockUser` to prove password login | Skips provider + service | Real POST form login with CSRF / provider test |
| Seeing HTTP POST 403 and claiming "disabled user rejected" | Might be missing CSRF without running auth | Include valid CSRF, assert failure reason |
| Relying on 302 for login success | Failed form logins also redirect | Assert Principal, `authenticated()`, and redirect target |
| Using `findFirst` on duplicate usernames | Picked account depends on query order | Unique key + DB integration test |
| Ignoring tenant separation | Same username across tenants can leak/mix data | Namespace/tenant binding from trusted source |
| Testing query with raw username while code normalizes | Mock returns `Optional.empty()` causing false negatives | `verify(repository).findByUsernameKey("alice")` |
| Catching every `RuntimeException` and returning a guest user | Severe fail-open flaw | Repository failures must fail closed |
| Catching DB timeout and arbitrarily throwing `UsernameNotFoundException` | Masks outages, hampers alerting, skews timing | Separate internal error/telemetry, safe public response |
| Logging raw passwords or full hashes | Credential leakage | Mask logs, use correlation IDs |
| Reusing mutable `UserDetails` in cache after credential erasure | Hash gets wiped, subsequent auth fails | Copy immutable/disable cache per design |
| Trusting roles from request headers | Caller grants themselves permissions | Fetch roles from trusted server repository |

## 14. Final Test Coverage by Layer

| Layer | Key tests | What to assert |
| --- | --- | --- |
| **Service + Mockito** | existing `alice` | exact canonical username, password hash, authorities, 4 flags, exact repository key |
| Service + Mockito | missing `ghost` | `UsernameNotFoundException`, never returns null/another user |
| Service + Mockito | `null`/blank/case | normalization/validation policy, no DB query on blank |
| Service + Mockito | disabled/locked/expired/credentialExpired | accurate flags, no inverted polarity |
| Service + Mockito | no roles/role mismatch | never fabricates new roles or mixes accounts |
| **DaoAuthenticationProvider** | correct password | valid `Authentication` and exact principal |
| DaoAuthenticationProvider | wrong password | `BadCredentialsException` |
| DaoAuthenticationProvider | missing account | `BadCredentialsException` by default, does not reveal user existence |
| DaoAuthenticationProvider | disabled/locked | internal `DisabledException` / `LockedException` |
| DaoAuthenticationProvider | expired account/password | `AccountExpiredException` / `CredentialsExpiredException` |
| **Repository/JPA** | normalized username, duplicate, case collation | UNIQUE per namespace, never returns wrong user |
| Repository/JPA | tenant/authorities/lazy loading | right tenant, roles loaded before transaction closes |
| **MockMvc/HTTP** | form right/wrong/missing password | `authenticated`/`unauthenticated` and exact redirect |
| MockMvc/HTTP | POST login missing CSRF | blocked before auth |
| MockMvc/HTTP | ROLE_USER accessing admin | 403, no side effects |
| **Security/system** | DB update lock/revoke role | new auth and existing sessions per explicit policy |
| Security/system | DB outage/stale cache | fail closed, metrics/correlation ID, no credential leaks |

**CI execution tip:** keep component tests under 1 second where possible (aside from password hashing cost), followed by provider tests, repository integration tests against a test database, and a few MockMvc smoke tests. Avoid forcing every test into a heavy `@SpringBootTest`; results become harder to read and a failure in one layer masks bugs in another.

## 15. Checklist Before Concluding the Feature Is Complete

- [ ] `loadUserByUsername` is actually called with the right key and returns a **non-null UserDetails** for existing accounts.
- [ ] Missing usernames produce `UsernameNotFoundException` at the service; default provider does not leak user existence in login responses.
- [ ] Null/blank names, case-insensitivity policy, Unicode/email/tenant are tested per product requirements.
- [ ] Password hashes are preserved from the trusted store; `PasswordEncoder.matches` runs only at the provider layer.
- [ ] Enabled, locked, accountExpired, and credentialsExpired have positive/negative tests with no inverted flags.
- [ ] Roles/authorities have proper prefixes and tenant scoping; none come from HTTP requests or fabricated defaults.
- [ ] Mock the repository to test the real service; mock the service only in **controller/authorization** tests, never to prove the service itself.
- [ ] Real provider is tested with right/wrong passwords and disabled/locked/expired accounts.
- [ ] Database has unique keys and tests for duplicates/collation/tenant to prevent wrong-account lookups.
- [ ] HTTP login has CSRF/redirect tests and 401/403 matching the auth scheme, without misinterpreting 302/403 across layers.
- [ ] Cache invalidation and credential erasure do not keep old users/roles active indefinitely.
- [ ] No passwords/tokens/hashes leak in logs, exception bodies, or test snapshots.
- [ ] Denied cases never create an authenticated session, issue access tokens, or trigger business side effects.
- [ ] Test code uses only test accounts, never real personal data or production connections.

**Conclusion:** testing `UserDetailsService` is about testing the **correctness and safety of identity lookup**. Existing accounts must return the right user and flags/authorities; missing accounts must throw `UsernameNotFoundException`; invalid accounts must preserve exact state flags so the provider rejects login. Only after that should you test passwords and HTTP security flows at their respective layers. No single test using `@WithMockUser` or merely observing 302/403 can replace all three testing layers.

### Official documentation

- [Spring Security 6.5 — UserDetailsService](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/user-details-service.html)
- [Spring Security — UserDetailsService API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/userdetails/UserDetailsService.html)
- [Spring Security 6.5 — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html)
- [Spring Security 6.5 — DaoAuthenticationProvider API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/dao/DaoAuthenticationProvider.html)
- [Spring Security — UserDetails API and Credentials Erasure](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/user-details.html)
- [Spring Security 6.5 — Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html)
- [Spring Security 6.5 — MockMvc Security Setup](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/setup.html)
- [Spring Security 6.5 — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html)
- [Spring Security FAQ — additional identity data / tenant context](https://docs.spring.io/spring-security/reference/6.5/servlet/appendix/faq.html)
