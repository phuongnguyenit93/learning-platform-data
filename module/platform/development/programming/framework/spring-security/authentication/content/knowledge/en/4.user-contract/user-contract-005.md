# Defining a Custom UserDetails vs. Using the Built-in User Class

> **Scope:** Spring Security Authentication on Java 17+, focusing on the `UserDetails` contract, the built-in `org.springframework.security.core.userdetails.User` class, and deciding when a custom implementation is needed. Full examples use Spring Security 6.5.x for behavior verification; Spring Boot/DB integration snippets are explicitly noted as illustrative and require application repositories and configuration. The lesson covers security, account status, caching, and using the principal after login.

## 1. Direct Answer: Built-in User or Custom UserDetails?

In most applications that only need **username, password hash, authorities, and account status**, start with Spring Security's `org.springframework.security.core.userdetails.User` class. It already implements `UserDetails`, provides a builder to construct all security attributes, and saves you from writing boilerplate getters.

Only define a **custom `UserDetails`** when the post-login principal genuinely needs stable, application-meaningful data—such as an **internal user ID**, tenant ID, organization code, or select identity attributes permitted in the security context—and you do not want every request to perform an extra lookup for that information. In that case, the custom class must faithfully implement Spring Security's contract while controlling sensitive data, account flags, serialization, and credential lifecycles.

**Important:** using the `User` class **does not mean** you have to store users in memory. `User` is a **data type**, whereas `UserDetailsService` is **how accounts are fetched** from a DB, LDAP, or another source. A database-backed `UserDetailsService` can completely return default `User` objects.

### Decision Table

| Scenario | Preference | Why |
| --- | --- | --- |
| Username/password login demo | `User.withUsername(...)` and `InMemoryUserDetailsManager` | Minimal code, focuses on the authentication mechanism |
| Real DB-backed system needing only username/roles/status | `User.withUsername(...)` inside a custom `UserDetailsService` | No extra principal type needed; still uses a repository |
| Web app needing a stable user ID across many services/controllers | Custom `UserDetails` holding ID (and minimal info) | Avoids depending on mutable usernames; maps clearly to the domain |
| Multi-tenant system where user IDs/usernames collide across tenants | Custom principal combining tenant/subject, with a safe identification mechanism | Login name alone may not be distinguishing enough |
| Only needing one extra display field on a single page | Usually keep `User`, fetch profile via service | Avoids putting frequently changing data into the security context |
| JWT Resource Server or OIDC Login | Check the principal type created by the respective mechanism (`Jwt`, `OidcUser`...) | Do not force every principal to be `UserDetails` by default |
| Needing non-password credential verification | Look into the appropriate provider/protocol | A custom `UserDetails` **does not automatically change** how credentials are checked |

There is no rule saying "large projects must have a custom `UserDetails`". The decision rests on **the identity contract the application needs** and the ability to maintain that data accurately and securely.

## 2. Where Does UserDetails Sit in the Authentication Flow?

```text
POST /login or HTTP Basic username/password
    ↓
Authentication Filter creates unauthenticated UsernamePasswordAuthenticationToken
    ↓
AuthenticationManager (usually ProviderManager)
    ↓
DaoAuthenticationProvider
    ├─ UserDetailsService.loadUserByUsername(username)
    │      ↓
    │   UserDetails from DB / memory / other source
    │      ├─ getUsername()
    │      ├─ getPassword()  → password hash
    │      ├─ getAuthorities()
    │      ├─ isEnabled()
    │      ├─ isAccountNonLocked()
    │      ├─ isAccountNonExpired()
    │      └─ isCredentialsNonExpired()
    └─ PasswordEncoder.matches(rawPassword, storedHash)
    ↓
Authenticated Authentication (principal is typically UserDetails)
    ↓
SecurityContext (managed by integrated security flow)
    ↓
Controller / service reads Authentication or appropriate principal
```

`UserDetailsService` has **one core job**: loading user information by username. It is not the component that decides whether a password is right or wrong in the standard flow. `DaoAuthenticationProvider` uses `UserDetails` and `PasswordEncoder` to verify credentials, check account status, and produce the authentication result.

Therefore, you can change the data source or swap the `UserDetails` implementation **without rewriting authentication filters or providers**.

**Do not confuse three similar names:**

- `UserDetails`: interface holding the data needed for authentication.
- `User` in package `org.springframework.security.core.userdetails`: built-in implementation of `UserDetails`.
- `UserDetailsService`: interface that finds `UserDetails` by username.

`InMemoryUserDetailsManager` is a `UserDetailsManager`/`UserDetailsService` implementation for storing users in memory; it differs from the `User` class. A JPA entity named `User` is also completely different from `org.springframework.security.core.userdetails.User`.

## 3. The UserDetails Contract: Which Data Must Be Accurate?

`UserDetails` extends `Serializable`. In Spring Security 6.5, the main methods mean:

| Method | Contract | Common Mistake |
| --- | --- | --- |
| `getUsername()` | Account name used for authentication; must not return `null` | Returning an unverified display name/email whose uniqueness the system does not enforce |
| `getPassword()` | Stored password hash value for the provider to check | Returning raw password; re-encoding the hash on every DB read |
| `getAuthorities()` | Trusted set of `GrantedAuthority`, non-`null` | Taking client-sent roles directly without verification |
| `isEnabled()` | `true` if the account is allowed to authenticate | Inverting enabled and disabled |
| `isAccountNonLocked()` | `true` when **not locked** | Returning `account.isLocked()` directly |
| `isAccountNonExpired()` | `true` when the account **has not expired** | Using an `expired` flag without negating it |
| `isCredentialsNonExpired()` | `true` if credentials **have not expired** | Ignoring mandatory password rotation rules |

The names of the three methods starting with `is...Non...` are critical: **`true` is the valid state**. In 6.5, the status-check methods have default implementations returning `true`; if a custom class needs to reflect DB state, you must **intentionally override them**. Never omit them and accidentally make locked/expired accounts look valid.

Example of a DB status mapping snippet, inside a method that already has `account`:

```java
boolean enabled = account.isEnabled();
boolean accountNonLocked = !account.isLocked();
boolean accountNonExpired = !account.isExpired();
boolean credentialsNonExpired = !account.isPasswordExpired();
```

The snippet above **illustrates status mapping**, assuming the entity defines those methods. It is not a standalone program.

Rules for upholding the contract:

1. `getUsername()` is stable and non-null within the namespace `UserDetailsService` uses.
2. `getAuthorities()` always returns a valid collection, and every authority must come from a trusted source. It can be empty if authentication policy allows.
3. `getPassword()` in a username/password flow must be **a hash compatible with PasswordEncoder**, not the original password. After authentication, the password may be erased from the principal object.
4. Do not place DB query logic, external API calls, or direct request reads inside getters; construct a sufficient identity snapshot when loading the user.
5. When placing the principal in a session/cache, consider serializability and staleness of roles/status over time.

### `UserDetails` Is Not a Business Entity

An application entity might have `id`, `email`, `phone`, `address`, `lastLoginAt`, `passwordHash`, status, and JPA relationships. A principal for authentication usually **only needs** ID, username, temporary hash, authorities, and status. Putting an entire JPA entity into the security context invites lazy-loading exceptions, serialization errors, storing excessive personal data, and side effects from mutable entities.

A safe mapping diagram:

```text
AccountEntity (DB, domain)
       │ repository query
       ▼
UserDetailsService
       ├── Option A: User.withUsername(...).build()
       └── Option B: new AppUserDetails(id, username, hash, authorities, flags)
       ▼
DaoAuthenticationProvider authenticates
       ▼
Authentication / SecurityContext
       ▼
App service uses internal ID (if custom) or looks up ID from service
```

## 4. Using the Built-in User Class: Common Cases and How to Construct It

The standard `User` class lives in package:

```java
org.springframework.security.core.userdetails.User
```

This **is not** a domain user entity. This class holds username, password, authorities, and status flags, and implements both `UserDetails` and `CredentialsContainer` to support erasing credentials when no longer needed.

Example creating a user with an existing password hash:

```java
UserDetails principal = User.withUsername("mai")
        .password(passwordHash)
        .roles("READER")
        .disabled(false)
        .accountLocked(false)
        .accountExpired(false)
        .credentialsExpired(false)
        .build();
```

This is a **snippet inside a method**, assuming `passwordHash` was generated once using `PasswordEncoder` upon registration/password change. It will not run standalone without imports and that variable.

About the builder:

- `roles("READER")` typically produces authority `ROLE_READER`. Do not pass `"ROLE_READER"` into `roles(...)` since the builder adds the prefix by convention.
- If the source returns exact authority strings like `"accounts:read"` or `"ROLE_AUDITOR"`, use `authorities(...)` and do not treat every authority as a role.
- `disabled(boolean)`, `accountLocked(boolean)`, `accountExpired(boolean)`, and `credentialsExpired(boolean)` take **negated** semantics relative to `isEnabled`, `isAccountNonLocked`, ... Map them accurately.
- Defaults in the builder normally correspond to valid account status; with real data, populate the exact flags from the DB.
- `User.withUserDetails(other)` is useful for copying standard `UserDetails` properties, but **does not preserve custom fields** like an internal ID or tenant ID from a custom principal.

**Pros:** minimal code, standard provider compatibility, methods and credential erasure already implemented by the library. **Limitations:** no custom business attributes. `Authentication.getPrincipal()` is normally `User`; to get an internal ID you must look it up or use a custom principal.

### Using User with a Database Without InMemoryUserDetailsManager

The `UserDetailsService` example below is **an integration sample requiring the application's `AccountRepository` and `AccountEntity`**, not a standalone runnable class:

```java
@Service
public class AccountUserDetailsService implements UserDetailsService {
    private final AccountRepository repository;

    public AccountUserDetailsService(AccountRepository repository) {
        this.repository = repository;
    }

    @Override
    public UserDetails loadUserByUsername(String username)
            throws UsernameNotFoundException {

        AccountEntity account = repository.findByUsername(username)
                .orElseThrow(() -> new UsernameNotFoundException("User not found"));

        return User.withUsername(account.getUsername())
                .password(account.getPasswordHash())
                .authorities(account.getAuthorities())
                .disabled(!account.isEnabled())
                .accountLocked(account.isLocked())
                .accountExpired(account.isExpired())
                .credentialsExpired(account.isPasswordExpired())
                .build();
    }
}
```

The example assumes `account.getAuthorities()` returns a collection/array accepted by `User.UserBuilder.authorities(...)`, and that the status methods exist on the entity. In real code, adapt the mapping to match your actual role types and repository API. The password value passed to the builder is **the hash fetched from the DB**, never `encoder.encode(account.getPasswordHash())`.

If the DB stores `ROLE_READER`, map using `new SimpleGrantedAuthority("ROLE_READER")`; if the DB stores role name `READER` and you use `roles("READER")`, the builder adds the prefix. Stick to one convention to avoid `ROLE_ROLE_READER` or wrong roles.

**When to choose this approach:** business APIs do not need to cast the principal to an entity; controllers/services can use `authentication.getName()` and a dedicated repository/service to fetch the ID when needed. For systems where few pages need the ID, an extra lookup can be easier to maintain than a custom principal.

## 5. When Should You Define a Custom UserDetails?

Choose a custom `UserDetails` when the answers to these questions carry weight:

1. Do you need an **immutable internal user ID** across many requests to access resources accurately while usernames can change?
2. Do you need a verified **tenant/organization ID** or identity realm in the security context to enforce data isolation?
3. Do you need small, **session-stable** identity metadata such as account type for security logic that the `User` class does not provide?
4. Do you need to standardize a custom principal so multiple controllers/services do not constantly translate usernames to domain IDs?
5. Do you have clear serialization/caching requirements and the ability to design credential erasure without breaking the user store?

If you only want to "add an email field for a profile page", a custom principal may not be the best solution since email can change, is sensitive, might be unverified, or does not need to sit in the session. Most display data should be fetched from a profile service and returned via DTOs.

**Custom `UserDetails` does not automatically solve:** issuing JWTs, verifying OIDC/SAML, MFA authentication, per-object permissions, logging out all sessions, or blocking a disabled account inside an existing session. Those belong to other mechanisms that must be designed separately.

### Designing a Custom Class: Keep It Minimal

Examples of information to include in a custom principal:

| Attribute | Put in Principal? | Notes |
| --- | --- | --- |
| Internal numeric/UUID user ID | Usually yes | Durable ID, independent of username |
| Authenticated username | Yes | `getUsername()` per contract |
| Password hash | Needed by password provider during authentication | Do not expose in responses/logs; watch credential erasure |
| Authorities | Yes | Permission snapshot granted from a trusted source |
| Enabled/locked/expired flags | Yes | Needed by `DaoAuthenticationProvider` checks |
| Tenant ID or issuer+subject | Yes when used to enforce boundaries | Value must be verified and mapped properly |
| Email, phone number, avatar | Usually no | Mutable display data that can be sensitive |
| Entire JPA entity with relationships | Avoid | Lazy loading, large payload, serialization, mutable state |
| Raw password, access token, refresh token | No | Secrets should not be held long-term in the principal |

### Implement Directly or Extend User?

- **Implement `UserDetails` directly:** clear control over fields, constructors, getters, equality, serialization, and credential erasure; slightly more code to test.
- **Extend `User`:** lets you reuse built-in behavior and add `userId`; however, you must understand `User`'s `equals/hashCode` based on username and superclass erasure details. If domain identity differs from username or spans multiple tenants, inheritance can introduce unwanted assumptions.
- **Wrap `UserDetails` as a delegate:** avoids repeating status getters, but must forward everything accurately per contract and handle `CredentialsContainer`/serialization. Useful when you want standard behavior while adding an ID.

For a reasonably simple custom principal, **implementing the interface directly and keeping values immutable** (except for erasable credentials) is usually easier to read and test. Do not extend a class just to save a few getters.

## 6. Runnable Java 17+: Same Password, Two Principal Types

This example creates two `UserDetailsService` instances: one returning the built-in `User`, and one returning a custom `AccountDetails` holding an internal ID. Both use the same `DaoAuthenticationProvider` and `ProviderManager`. After authentication, the program **only prints harmless metadata**, never passwords or hashes.

Project structure:

```text
userdetails-choice-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/UserDetailsChoiceDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'userdetails-choice-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.security:spring-security-core:6.5.11'
}

application {
    mainClass = 'demo.UserDetailsChoiceDemo'
}
```

Create `src/main/java/demo/UserDetailsChoiceDemo.java`:

```java
package demo;

import java.util.List;
import java.util.Collection;
import java.util.stream.Collectors;

import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.DisabledException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.CredentialsContainer;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;

public class UserDetailsChoiceDemo {
    private static final PasswordEncoder ENCODER = new BCryptPasswordEncoder();

    public static void main(String[] args) {
        // Test password only; never hardcode credentials in real applications.
        String hash = ENCODER.encode("demo-pass");

        UserDetails builtIn = User.withUsername("mai")
                .password(hash)
                .roles("READER")
                .build();

        UserDetailsService standardSource =
                new InMemoryUserDetailsManager(builtIn);

        UserDetailsService customSource = customSource(hash, true);

        show("built-in", login(standardSource, "demo-pass"));
        show("custom", login(customSource, "demo-pass"));

        try {
            login(customSource, "wrong");
        } catch (BadCredentialsException ex) {
            System.out.println("wrong-password: BadCredentialsException");
        }

        try {
            login(customSource(hash, false), "demo-pass");
        } catch (DisabledException ex) {
            System.out.println("disabled: DisabledException");
        }
    }

    private static UserDetailsService customSource(
            String hash, boolean enabled) {
        return username -> {
            if (!"mai".equals(username)) {
                throw new UsernameNotFoundException("User not found");
            }
            return new AccountDetails(
                    42L,
                    username,
                    hash,
                    List.of(new SimpleGrantedAuthority("ROLE_READER")),
                    enabled,
                    true,  // accountNonExpired
                    true,  // accountNonLocked
                    true   // credentialsNonExpired
            );
        };
    }

    private static Authentication login(
            UserDetailsService users, String rawPassword) {
        DaoAuthenticationProvider provider =
                new DaoAuthenticationProvider(users);
        provider.setPasswordEncoder(ENCODER);

        AuthenticationManager manager = new ProviderManager(provider);

        return manager.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "mai", rawPassword));
    }

    private static void show(String label, Authentication auth) {
        UserDetails principal = (UserDetails) auth.getPrincipal();
        String id = principal instanceof AccountDetails account
                ? Long.toString(account.userId())
                : "-";

        String authorities = auth.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .sorted()
                .collect(Collectors.joining(","));

        String hashState = principal.getPassword() == null
                ? "erased"
                : "present";

        System.out.printf(
                "%s: principal=%s; name=%s; id=%s; authorities=%s; hash=%s%n",
                label,
                principal.getClass().getSimpleName(),
                auth.getName(),
                id,
                authorities,
                hashState);
    }

    // Custom security principal; not a JPA entity.
    private static final class AccountDetails
            implements UserDetails, CredentialsContainer {
        private static final long serialVersionUID = 1L;

        private final long userId;
        private final String username;
        private String passwordHash;
        private final List<GrantedAuthority> authorities;
        private final boolean enabled;
        private final boolean accountNonExpired;
        private final boolean accountNonLocked;
        private final boolean credentialsNonExpired;

        AccountDetails(
                long userId,
                String username,
                String passwordHash,
                Collection<? extends GrantedAuthority> authorities,
                boolean enabled,
                boolean accountNonExpired,
                boolean accountNonLocked,
                boolean credentialsNonExpired) {
            this.userId = userId;
            this.username = username;
            this.passwordHash = passwordHash;
            this.authorities = List.copyOf(authorities);
            this.enabled = enabled;
            this.accountNonExpired = accountNonExpired;
            this.accountNonLocked = accountNonLocked;
            this.credentialsNonExpired = credentialsNonExpired;
        }

        long userId() {
            return userId;
        }

        @Override
        public String getUsername() {
            return username;
        }

        @Override
        public String getPassword() {
            return passwordHash;
        }

        @Override
        public Collection<? extends GrantedAuthority> getAuthorities() {
            return authorities;
        }

        @Override
        public boolean isEnabled() {
            return enabled;
        }

        @Override
        public boolean isAccountNonExpired() {
            return accountNonExpired;
        }

        @Override
        public boolean isAccountNonLocked() {
            return accountNonLocked;
        }

        @Override
        public boolean isCredentialsNonExpired() {
            return credentialsNonExpired;
        }

        @Override
        public void eraseCredentials() {
            passwordHash = null;
        }
    }
}
```

From the `userdetails-choice-demo` directory, run with a Java 17-compatible Gradle:

```bash
gradle run
```

If the project has a Gradle Wrapper, use `./gradlew run` (macOS/Linux) or `gradlew.bat run` (Windows). The program will print the following four main lines (aside from Gradle output):

```text
built-in: principal=User; name=mai; id=-; authorities=ROLE_READER; hash=erased
custom: principal=AccountDetails; name=mai; id=42; authorities=ROLE_READER; hash=erased
wrong-password: BadCredentialsException
disabled: DisabledException
```

### Output Analysis

1. **Same name:** `Authentication.getName()` is `mai` in both; using a custom principal does not alter username on its own.
2. **Different principal class:** when `UserDetailsService` returns `User`, the principal is typically `User`; with the custom source, the principal is `AccountDetails`. Both still implement `UserDetails` and are handled identically by `DaoAuthenticationProvider`.
3. **Internal ID:** only `AccountDetails` has `userId=42`; the standard `User` class lacks this getter. This is the practical reason to pick a custom class.
4. **Authorities:** both return `ROLE_READER` granted by the trusted user source. Roles cannot be inferred from the principal class name.
5. **Hash erased:** `ProviderManager` erases credentials after success by default for objects supporting `CredentialsContainer`. Built-in `User` implements erasure; custom `AccountDetails` also supports it, so `getPassword()` on the resulting principal returns `null`.
6. **Wrong password:** `DaoAuthenticationProvider` calls `PasswordEncoder.matches(...)` and rejects invalid credentials. There is no "custom principal" path that skips password checking.
7. **Disabled:** `isEnabled() == false` causes authentication to be rejected with `DisabledException`, even with the right password. Status flags are checked in the standard provider without needing manual controller checks.

**Technical point of the example:** the `login(...)` method only returns the manager's result without adding it to `SecurityContext`. In a real web app, authentication filters and security infrastructure handle that per the configured flow. The demo code also deliberately constructs a fresh `AccountDetails` on each load from the source, avoiding mutation on a cached and reused object.

### Why Does the Custom Class Support CredentialsContainer?

`UserDetails` is data used by the provider to verify credentials. When a custom principal holds `passwordHash`, supporting `CredentialsContainer` allows `ProviderManager` to clear the hash reference from the result once authentication completes:

```java
@Override
public void eraseCredentials() {
    passwordHash = null;
}
```

Never store raw passwords. Do not confuse password hashes with raw passwords; hashes are still data to protect and must not be output to clients. `ProviderManager` does not automatically know to clear an arbitrary field in a custom class unless the class implements the corresponding mechanism.

**Be careful with caching:** if multiple requests share **the same cached `UserDetails` instance**, erasure can clear the password hash inside the cached instance, leaving subsequent logins with no data to compare against. Design it to return **a separate copy for the authentication result**, manage cache identity lifecycles properly, or control how erasure behaves. Never disable `eraseCredentialsAfterAuthentication` indiscriminately just to hide a cache bug.

## 7. Spring Boot + Database Integration: Where Do the Two Approaches Differ?

The two implementations differ only in **the object `UserDetailsService` returns**; the database, password encoder, authentication provider, and filters can stay the same.

### Option A — DB → Built-in User

```text
AccountRepository.findByUsername
    → AccountEntity
    → User.withUsername(...).password(hash).authorities(...).flags(...).build()
    → DaoAuthenticationProvider
    → Authentication principal = User
```

Good when there is no requirement to put an internal ID into the principal; the code is simple and easy to verify.

### Option B — DB → Custom UserDetails

```text
AccountRepository.findByUsername
    → AccountEntity
    → new AppUserDetails(id, username, hash, authorities, flags)
    → DaoAuthenticationProvider
    → Authentication principal = AppUserDetails
```

Good when services need a verified ID/tenant. Do not attach the entire entity to the principal just because you need the ID.

Sample `UserDetailsService` for Option B, **illustrative only; you must define AccountRepository, AccountEntity, and AppUserDetails yourself**:

```java
@Service
public final class DatabaseUserDetailsService
        implements UserDetailsService {
    private final AccountRepository repository;

    public DatabaseUserDetailsService(AccountRepository repository) {
        this.repository = repository;
    }

    @Override
    public UserDetails loadUserByUsername(String username)
            throws UsernameNotFoundException {
        AccountEntity account = repository.findByUsername(username)
                .orElseThrow(() -> new UsernameNotFoundException("User not found"));

        return new AppUserDetails(
                account.getId(),
                account.getUsername(),
                account.getPasswordHash(),
                toGrantedAuthorities(account.getRoles()),
                account.isEnabled(),
                !account.isExpired(),
                !account.isLocked(),
                !account.isPasswordExpired()
        );
    }
}
```

In a real implementation, `toGrantedAuthorities` must map trusted roles to `GrantedAuthority` and ensure a valid collection. `AppUserDetails` should have a structure similar to `AccountDetails` in the runnable example, with clear ID, flags, and `eraseCredentials` method.

**Do not do inside `loadUserByUsername`:** call `PasswordEncoder.matches` to authenticate yourself (the provider will do it), re-encode the hash from the database, inspect the request session via an unstable thread-local, or take roles from an untrusted request. Never read an email or non-existent username and auto-create an account inside this callback.

### Provider Configuration Remains the Same

The snippet below is for Spring Security 6.5.x, requiring existing `UserDetailsService` and `PasswordEncoder` beans:

```java
@Bean
AuthenticationManager authenticationManager(
        UserDetailsService users, PasswordEncoder encoder) {
    DaoAuthenticationProvider provider = new DaoAuthenticationProvider(users);
    provider.setPasswordEncoder(encoder);
    return new ProviderManager(provider);
}
```

Changing how `UserDetails` is constructed **does not force** you to write a custom `AuthenticationProvider`. In Spring Boot, the framework may already configure a provider for `UserDetailsService`; do not declare duplicate managers just to swap the principal. With multiple `SecurityFilterChain` beans, verify which chain actually uses that manager.

## 8. Using a Custom Principal in Controllers and Services

After successful login, `Authentication.getPrincipal()` is the object returned by the provider (in a username/password flow, usually `UserDetails`). When using a custom class in a Spring MVC application, you can receive the principal via `@AuthenticationPrincipal` in a controller:

```java
// Illustrative method inside a @RestController with custom AppUserDetails.
@GetMapping("/me")
MeResponse me(@AuthenticationPrincipal AppUserDetails principal) {
    return new MeResponse(principal.getUserId(), principal.getUsername());
}

record MeResponse(long id, String username) {}
```

This is a snippet, **not a standalone runnable class**. The endpoint must be protected with an `authenticated()` rule; when using JWT/OIDC or anonymous access, the principal type may differ and the parameter is not necessarily `AppUserDetails`. Use an appropriate mapping service instead of forcing provider-specific casts in every controller.

Avoid returning the raw object:

```java
// DO NOT DO THIS: principal may hold hashes, internal flags, or sensitive claims.
@GetMapping("/raw-principal")
Object raw(@AuthenticationPrincipal Object principal) {
    return principal;
}
```

The snippet above is an **anti-pattern example** meant to show risk, not an API to deploy. Return a DTO with an allowlisted set of fields, such as `id` and `username`, when genuinely permitted.

### When You Want to Keep Built-in User Yet Still Need the ID

You can opt for a dedicated service:

```java
String username = authentication.getName();
Long userId = accountLookupService.findIdByUsername(username);
```

This is a **snippet assuming the service exists**, suitable when only a few places in the application need the ID. Manage username uniqueness, especially in multi-tenancy; typically map within a verified namespace/realm. Never take an ID from a query parameter and treat it as the authenticated user's ID.

### When Multiple Authentication Types Exist

| Flow | Typical Principal | How to Get Application ID |
| --- | --- | --- |
| Username/password + `User` | `UserDetails`, specifically `User` | Look up by canonicalized key or identity mapping layer |
| Username/password + custom | Custom `UserDetails` | Read internal ID stored in the principal |
| JWT Resource Server | `Jwt` or converter-defined principal | Map issuer/subject or trusted claim to internal ID |
| OIDC Login | `OidcUser` | Map issuer + subject pair, with an account linking workflow |
| Anonymous | Anonymous principal or context with no real user | Do not treat as a logged-in internal user |

Do not customize `UserDetails` just to force completely different flows into one class. A JWT/OIDC principal has its own contract; unifying them requires solving **identity mapping** and security boundaries in the proper layer.

## 9. Account States: Wrong Mapping and Testing Easily Cause Security Bugs

With the built-in `User` class, the builder uses flags meaning "problematic"; with custom `UserDetails`, the interface asks for valid state:

| Assumed DB Field | `User` Builder | Custom `UserDetails` Getter |
| --- | --- | --- |
| `enabled=true` | `disabled(false)` | `isEnabled() == true` |
| `locked=true` | `accountLocked(true)` | `isAccountNonLocked() == false` |
| `expired=true` | `accountExpired(true)` | `isAccountNonExpired() == false` |
| `passwordExpired=true` | `credentialsExpired(true)` | `isCredentialsNonExpired() == false` |

Never interpret `accountNonLocked` as "is locked"; inverted semantics are the root cause of many bugs missed in code reviews.

To test, verify at least:

1. Valid user and right password → authentication succeeds.
2. Valid user but wrong password → `BadCredentialsException`.
3. `enabled=false` → `DisabledException`.
4. `locked=true` → `LockedException`.
5. `expired=true` → `AccountExpiredException`.
6. `passwordExpired=true` → `CredentialsExpiredException`.
7. Non-existent user → rejected; default `DaoAuthenticationProvider` may mask user existence with `BadCredentialsException`.
8. User with empty authorities → can authenticate, but lacks permission to access role-protected endpoints.
9. User changes username → internal ID stays unchanged; business relations continue working by ID.
10. After login, hash is not leaked in responses/logs; custom principal does not serialize extra fields.

Also consider **post-login status updates**. If a user is locked after already obtaining a session or token, the security context/token may still hold previously authenticated data. Simply flipping a flag in the DB does not automatically revoke all sessions/tokens. Real systems need revalidation, logout/revocation, TTL, and permission-refresh policies per requirements.

## 10. Credential Erasure, Serialization, Caching, and Principal Lifecycle

### 10.1. Erasing Credentials Does Not Mean Deleting the DB Password

`ProviderManager` normally erases credentials on the resulting `Authentication` after success if the object implements `CredentialsContainer`. This reduces sensitive data retained in memory/sessions.

This **does not delete the password hash in the database**, nor does it alter other account authentication mechanisms. Custom principals should support `CredentialsContainer` when holding credentials, while avoiding directly mutating shared DB/cache objects that get reused.

Do not set `setEraseCredentialsAfterAuthentication(false)` as a default workaround. If you need to cache `UserDetails` with hashes, decouple the cache entry lifecycle from the principal returned to the request, copying or reloading objects appropriately.

### 10.2. Serializable and Mutable Data

`UserDetails` extends `Serializable` because the principal may be stored in a session or passed through persistence/session replication. Custom classes must consider:

- Are all fields serializable? Keep only simple data; never put `EntityManager`, repositories, requests, streams, or JPA proxies into the principal.
- Are any fields sensitive and retained too long? Avoid email/phone/tokens unless needed.
- Are authorities accurate at authentication time? If roles change, old sessions may keep stale snapshots.
- Which ID do `equals` and `hashCode` base identity on? If usernames can change or collide across tenants, do not default to username as the domain key.
- A mutable principal shared across requests can trigger race conditions when erasing credentials or updating fields. Prefer immutable identity fields and distinct objects per authentication.

### 10.3. Performance and Database Lookups

A custom principal holding an ID avoids some username → ID lookups per request, yet also keeps **an ID/role snapshot pinned for the session**. Do not treat stuffing dozens of fields into the principal as an obvious performance optimization. Balance fewer queries against timely updates, accuracy, and permission revocation.

For DB user stores, establish proper indexes/unique constraints on usernames within the authentication namespace; if supporting username/tenant changes, define how mappings transition and prevent account confusion.

### 10.4. Multi-Tenant and External Identity

`UserDetailsService.loadUserByUsername(String)` accepts only a `String`. If multiple tenants share the same login name, you need a **trusted** way to determine the namespace before lookup, such as a manager/provider or token carrying verified context per system architecture. Never trust a client-supplied `tenantId` just because the custom principal has that field.

When logging in via an IdP, internal keys usually derive from issuer + subject and an approved link. Email or display name alone is not enough to merge accounts across issuers.

## 11. Common Mistakes When Choosing or Implementing

1. **Thinking `User` is `InMemoryUserDetailsManager`:** `User` is a data model; the manager is a user source/manager. Using `User` with a DB is completely valid.
2. **Custom class missing flag overrides:** the 6.5 interface defaults status flags to `true`, easily ignoring disabled/locked from the DB by accident.
3. **Inverting `isAccountNonLocked`:** a locked account must return `false`, not `true`.
4. **Returning plaintext from `getPassword()`:** passwords must be stored as hashes using an appropriate `PasswordEncoder`. Never re-encode a hash on load.
5. **Writing roles with the wrong prefix:** `roles("ADMIN")` normally becomes `ROLE_ADMIN`; `authorities("ROLE_ADMIN")` uses the literal string. Do not double-prefix `ROLE_`.
6. **Putting the entire JPA entity into the principal:** introduces lazy loading, serialization bugs, mutable state, and unnecessary session bloat.
7. **Customizing `UserDetails` just to display email:** fast-changing and potentially sensitive data; mostly belongs in profile DTOs/services.
8. **Not implementing credential erasure:** password hashes can linger in sessions longer than needed.
9. **Running erasure on a shared cached instance:** the cache can lose the hash and subsequent logins fail; keep copy/lifecycle clear.
10. **Creating a custom `UserDetails` expecting JWT/OIDC to return that class automatically:** other flows' principals can be `Jwt`/`OidcUser`.
11. **Casting `authentication.getPrincipal()` unconditionally to a custom type:** can throw `ClassCastException` or null if anonymous or from another provider.
12. **Returning the principal directly as JSON:** accidentally leaks hashes or internal attributes. Only return allowlisted DTOs.
13. **Using username as a business primary key when renames are possible:** internal ID and tenant boundaries are usually better.
14. **Authorizing based on client-sent roles:** authorities must come from verified user stores/issuers.
15. **Writing a custom provider or filter just to swap principal classes:** usually you only need to change what `UserDetailsService` returns.
16. **Believing flipping a DB flag instantly revokes all sessions/JWTs:** you need proper refresh/revocation policies.
17. **Changing principal `equals/hashCode` without checking sessions/caches:** can change collection, concurrency, and principal identity behavior unexpectedly.
18. **Putting DB logic inside `getUsername/getAuthorities`:** getters should read a prepared snapshot; avoid hidden queries and detached-transaction errors.

## 12. Minimal Testing for Both Options

| Condition | With Built-in User Class | With Custom UserDetails |
| --- | --- | --- |
| Valid username/password | `DaoAuthenticationProvider` accepts | Accepted if contract is right |
| Principal class | `User` | Custom class |
| Internal ID | Absent, needs extra mapping | Present if passed to constructor |
| Password/hash after authentication | `User` supports erasure | Must design erasure if holding hash |
| Disabled/locked/expired | Builder sets flags properly | Getters return accurate state |
| Authorities | From builder/trusted source | From trusted collection source |
| Identity after username change | Avoid tying domain ID to username | ID can stay stable |
| Cache/session | Avoid reusing erased objects | Verify serialization and mutation |
| HTTP/REST DTO | Output only permitted fields | Same, never return raw object |
| JWT/OIDC | Does not become principal of other flows | Does not replace other flows either |

Use **real authentication tests through manager/provider** to verify password hashes and flags. `@WithMockUser` tests create a mocked security context suited for authorization testing, **without proving `UserDetailsService` or `DaoAuthenticationProvider` was called**. For a custom principal, run a real authentication test and verify `Authentication.getPrincipal() instanceof AppUserDetails` along with the internal ID value.

Test guidance example in Java:

```java
Authentication authentication = manager.authenticate(
        UsernamePasswordAuthenticationToken.unauthenticated(
                "mai", "demo-pass"));

assert authentication.isAuthenticated();
assert authentication.getPrincipal() instanceof AppUserDetails;

AppUserDetails principal =
        (AppUserDetails) authentication.getPrincipal();
assert principal.getUserId().equals(expectedUserId);
```

**This is test pseudocode**, assuming `manager`, `AppUserDetails`, and `expectedUserId` exist; use JUnit `assertThat`/`assertEquals` instead of Java `assert` if you do not want tests to depend on the `-ea` flag. For primitive `long`, compare with `==` or `assertEquals(long,long)` instead of `.equals`. Do not copy the snippet verbatim into production without matching actual types.

## 13. Tiered Practice Exercises

**Exercise 1 — Comparing two principals.** Run the section 6 demo, explain why both log in successfully with the same `DaoAuthenticationProvider` while only the custom principal has an ID. Verify no hash appears in the output.

**Exercise 2 — Mapping status.** Design a mock `AccountEntity` with `enabled`, `locked`, `expired`, and `passwordExpired`. Write mappings to `User.withUsername(...)` and to a custom `UserDetails`. Test every error state to catch inverted getters.

**Exercise 3 — Real DB source.** Create `AccountRepository.findByUsername(...)` and a `UserDetailsService` returning standard `User`. Once all tests pass, swap only the return value to a custom principal with an ID; verify requests still authenticate.

**Exercise 4 — DTO.** Design a `GET /me` endpoint returning only `id`, `username`, and approved fields. Do not serialize `UserDetails`/`Authentication` directly. With built-in `User`, the ID comes from a lookup service; with a custom principal, the ID comes from the authenticated principal.

**Exercise 5 — Cache/erasure.** Predict what happens if a cached `UserDetails` is the same instance subjected to `eraseCredentials`, then try returning a separate instance for the authentication result. Do not disable password protection as a default "fix".

**Exercise 6 — Multi-tenant.** Two tenants have users with the same username `mai`. Propose a complete identity key, how to enforce a trusted tenant during lookup, and how to pass the internal ID safely into services. Explain why adding `tenantId` to the class alone is insufficient.

### Completion Criteria

Learners should be able to answer on their own:

- What fields does `UserDetails` require, and what do the `NonExpired/NonLocked` flags mean?
- Why can using `User` still load users from a database?
- When is an internal ID/tenant ID in the principal more valuable than a lookup?
- Why does a custom `UserDetails` not require a custom `AuthenticationProvider`?
- Why can `CredentialsContainer` and caching conflict?
- How can you retrieve an ID via `@AuthenticationPrincipal` without returning the password hash?
- Why is a JWT/OIDC principal not necessarily `UserDetails`?
- How can both options be verified with real manager/provider tests?

Once you can answer those questions and run the demo, you have a solid foundation to pick the principal type matching business needs while preserving Spring Security's standard authentication mechanics.

## 14. Official Documentation

- [Spring Security 6.5 — UserDetailsService](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/user-details-service.html): how providers retrieve account details.
- [Spring Security 6.5 — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html): using `UserDetailsService`, `PasswordEncoder`, and principals on successful authentication.
- [Spring Security 6.5 — Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): `Authentication`, `SecurityContext`, `ProviderManager`, and credential erasure.
- [Spring Security 6.5.2 — UserDetails Javadoc](https://docs.spring.io/spring-security/site/docs/6.5.2/api/org/springframework/security/core/userdetails/UserDetails.html): interface signature and semantics.
- [Spring Security 6.5 — UserDetails](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/user-details.html): designing `UserDetails` and `CredentialsContainer`.
- [Spring Security 6.5 — Password Storage](https://docs.spring.io/spring-security/reference/6.5/features/authentication/password-storage.html): managing password hashes and encoders.

**Version note:** examples are pinned to Spring Security 6.5.11, in the Spring Security 6.5 branch. When using another version (especially Spring Security 7 or passwordless flows), re-check the API signatures and principal/credential mechanics for that exact version.