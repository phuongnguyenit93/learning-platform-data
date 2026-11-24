# UserDetails and the Data Required by the Authentication Engine

In Spring Security, user information stored in a database typically has many fields: account ID, email, display name, phone number, permission groups, lock status, activity history, and business attributes. **The username/password authentication engine does not need that entire profile**. It needs a minimal contract to know *whether the right account was found, which credential to verify against, whether the account is still permitted to log in, and if successful, what authorities the principal has*. That contract is `org.springframework.security.core.userdetails.UserDetails`.

A `UserDetails` object **is not proof of having logged in**, is not the raw password just submitted by the client, and does not place the user into `SecurityContext` on its own. It is **an account description provided by a trusted source** for `DaoAuthenticationProvider` to evaluate during the username/password flow. Understanding the exact data the contract provides helps you build `UserDetailsService`, map accounts from the database, and lock or disable accounts predictably.

This lesson focuses on the **User Contract** in the *Spring Security - authentication* module, with Java 17+ and Spring Security 6.x (Spring Boot 3.x application) code examples. Bearer JWT/OIDC architectures may use other principal types; they are mentioned to define the responsibility boundary of `UserDetails`.

## 1. Objectives

After this lesson, you can:

1. Explain the responsibilities of `UserDetails`, `UserDetailsService`, `PasswordEncoder`, `DaoAuthenticationProvider`, `Authentication`, and `SecurityContext`, avoiding mixing them up.
2. Correctly read every method in `UserDetails`: username, password, authorities, and the four negated status flags.
3. Know how to convert an account record into `UserDetails` without passing business data or unnecessary secrets into the principal.
4. Predict outcomes when the username does not exist, the password is wrong, the account is locked/disabled/expired, or the password has expired.
5. Distinguish `roles(...)` from `authorities(...)`, authority data sources, and the limits of authorization checks.
6. Run a Spring Boot example with an active account and rejected states; inspect observable HTTP results.
7. Recognize common mistakes when caching `UserDetails`, erasing credentials, normalizing usernames, using multi-tenant accounts, and handling status changes after login.

## 2. Clearly Distinguishing Objects in the Authentication Flow

| Component | Role | Typical Data | What Not to Do |
| --- | --- | --- | --- |
| **Account / domain entity** | Business record, the organization's authoritative data source | ID, email, password hash, status, personal info, business relationships | Pass the entire entity, including private attributes, to every request/controller. |
| **`UserDetails`** | Security view of an account needed by the provider to verify username/password | Username, password verifier, authorities, account flags | Treat this object as proof of a successful login or store incoming raw passwords in it. |
| **`UserDetailsService`** | Service that retrieves the account security view by username | `loadUserByUsername(String)` returning `UserDetails` | Authenticate raw passwords itself or grant permissions based on a client-sent header. |
| **`PasswordEncoder`** | Verifies a raw credential against a stored verifier; generates hashes when issuing/changing passwords | `matches(raw, encoded)`, `encode(raw)` | Compare plain strings against hashes or store passwords in plaintext. |
| **`DaoAuthenticationProvider`** | Provider that authenticates username/password using UserDetails and PasswordEncoder | Status check, password match, resulting principal | Change account status just because a request claims it is allowed. |
| **`Authentication`** | Initial authentication request or authenticated result | Principal, credentials, authorities, authentication state | Infer `isAuthenticated=true` from having a username without verifying credentials. |
| **`SecurityContext`** | Security context of the execution/request | `Authentication` established by a trusted mechanism | Store raw passwords or assume every database change syncs immediately. |

Viewed in sequence: **domain account → `UserDetailsService` loads security view → `DaoAuthenticationProvider` verifies credentials and status → `Authentication` result → `SecurityContext` → authorization**. Each link is responsible for a different question.

### UserDetails vs. Principal

After a standard username/password login flow with `DaoAuthenticationProvider`, `Authentication.getPrincipal()` is usually the loaded `UserDetails`. However, `Authentication.getPrincipal()` has type `Object`; depending on the mechanism, it may be a `String`, `Jwt`, `OAuth2User`, a custom object, or another type. Therefore:

- `UserDetails` describes account data for a specific mechanism.
- `Principal` in `Authentication` describes **the subject authenticated by the mechanism**.
- `Authentication.getName()` is a convenient way to get the identifier declared by the authentication object.
- Do not cast `(UserDetails) authentication.getPrincipal()` across all controllers if the application uses multiple authentication mechanisms.
- Logging in successfully is also not permission to read another user's record; the authorization step still has to check the actual resource.

## 3. The UserDetails Contract: Seven Core Values

In Spring Security 6.x, `UserDetails` defines three data methods and four status methods. The following interface is **a simplified version for reading its meaning**, not code to copy to recreate a Spring Security package:

```java
public interface UserDetails extends java.io.Serializable {
    Collection<? extends GrantedAuthority> getAuthorities();
    String getPassword();
    String getUsername();

    default boolean isAccountNonExpired() { return true; }
    default boolean isAccountNonLocked() { return true; }
    default boolean isCredentialsNonExpired() { return true; }
    default boolean isEnabled() { return true; }
}
```

The default methods returning `true` allow implementations that only need the three basic fields to work, **but this is a risk if the application has lock/expiration policies and forgets to override them**. A system that has a lock status in the DB while `UserDetails` always returns `true` will not have the provider block based on that status.

| Method | What information does the provider need? | Contract and examples |
| --- | --- | --- |
| `getUsername()` | Login name/identifier of the loaded account | Returns a non-`null` string; may be a canonicalized username. |
| `getPassword()` | Verifier value for `PasswordEncoder.matches(...)` to check the raw password against | In the username/password flow, usually an **encoded password hash** (e.g., `{bcrypt}...`), not the original password. |
| `getAuthorities()` | List of `GrantedAuthority` granted to the principal after authentication | Must not return `null`; sourced from a trusted authority store, e.g., `ROLE_READER`, `orders:read`. |
| `isEnabled()` | Whether the account is allowed to be used for authentication | `true` = enabled, `false` = disabled. |
| `isAccountNonExpired()` | Whether the account is still valid or has expired | `true` = not expired; `false` = expired. |
| `isAccountNonLocked()` | Whether the account is currently locked | `true` = not locked; `false` = locked. |
| `isCredentialsNonExpired()` | Whether the credential/password verifier is still within its validity/policy | `true` = still valid; `false` = credentials expired. |

**Warning about negation:** `isAccountNonLocked() == false` means **the account is locked**, not unlocked. `isCredentialsNonExpired() == false` means **the password has expired**. Name boolean variables clearly when mapping from the DB to avoid inverting the condition.

### 3.1 Which Fields Are Required?

For standard username/password authentication:

- `username` must point to the right record according to the application's lookup policy.
- `password` must contain a verifier understood by the current `PasswordEncoder`. Do not store raw passwords and rely on `{noop}` in production.
- `authorities` must represent the permissions granted by a trusted source, which may be minimal authorities to identify the user; the collection must not be `null`.
- The four status flags must match the account state and login policy. The default `true` cannot automatically know that an account is locked in the database.

Do not confuse `UserDetails.getPassword()` with `Authentication.getCredentials()`: the first is usually the **stored hash** from the server; the second is usually the **raw credential** presented by the request before being erased. Exposing the hash is still sensitive because it can be cracked offline.

### 3.2 Data That Does Not Belong in the Contract

`UserDetails` does not need to contain phone number, address, date of birth, payment methods, language settings, order lists, avatar, tenant config, or the full domain object. If business logic needs a stable value like `accountId` or `tenantId`, use a **minimal custom principal** or query an access-checked service. Do not let `UserDetails` become a copy of the entire entity on every authentication.

Information about MFA, identity proofing, external IdPs, authentication strength, and reauthentication time may require separate models/contracts. The four status flags do not replace all those decisions.

## 4. Data Path Through DaoAuthenticationProvider

This is a common flow with HTTP Basic or form login in Spring Security Servlet, and does not apply verbatim to every mechanism:

```text
Client (username + raw password)
            |
            v
UsernamePasswordAuthenticationFilter / BasicAuthenticationFilter
            |
            | creates an UNAUTHENTICATED UsernamePasswordAuthenticationToken
            v
AuthenticationManager / ProviderManager
            |
            v
DaoAuthenticationProvider
            |
            +--> UserDetailsService.loadUserByUsername(username)
            |         |
            |         +--> Account store / DB / LDAP / cache
            |                   |
            |                   +--> UserDetails: username, encoded password,
            |                         authorities, enabled/non-expired/non-locked...
            |
            +--> Check account status
            +--> PasswordEncoder.matches(raw, storedHash)
            +--> Check credential expiration status
            |
            v
Successful Authentication (principal is typically UserDetails)
            |
            v
SecurityContext managed by filter/security mechanism
            |
            v
Authorization: evaluate permissions for specific action and resource
```

Key steps:

1. The client sends credentials over HTTPS to the configured endpoint/mechanism.
2. The filter creates an `Authentication` request to be processed, such as `UsernamePasswordAuthenticationToken.unauthenticated(username, rawPassword)`.
3. `ProviderManager` selects a provider matching the token type. `DaoAuthenticationProvider` uses `UserDetailsService` to load the security view by username. Loading does not mean the password has been proven.
4. The provider performs status checks and matches using `PasswordEncoder` according to the specific mechanism. A locked/disabled/expired account can be blocked even if the password matches.
5. If successful, the provider returns an authenticated `Authentication` containing the appropriate principal and authorities; the filter places the result into the context.
6. The controller/service reads the authenticated principal/authorities and authorization decides the action. It **does not need to know the raw password**, and usually does not need to call `UserDetailsService` to log in again.

In an application with caching, some authentications may retrieve `UserDetails` from the cache instead of hitting the database directly; loading every time is not guaranteed. The cache must have an appropriate refresh/eviction policy when an account changes.

### What Happens When Lookup Fails?

`UserDetailsService.loadUserByUsername` returns a fully populated `UserDetails` or throws `UsernameNotFoundException` when the user cannot be found; **it must not return `null`**. With standard `DaoAuthenticationProvider`, a "username not found" error can be masked as a generic credential error at the authentication boundary to reduce the risk of account enumeration. Do not expose a public API revealing "this username exists" just to make debugging easier.

### Do Not Call UserDetailsService Directly as Proof of Authentication

Wrong:

```java
UserDetails details = userDetailsService.loadUserByUsername(username);

// Wrong: merely loading the user does not prove the sender knows the password.
SecurityContextHolder.getContext().setAuthentication(
        UsernamePasswordAuthenticationToken.authenticated(
                details, null, details.getAuthorities()));
```

This is a **broken example**, not a complete program. The right approach is to let a trusted mechanism call `AuthenticationManager.authenticate(...)`, check the password/credentials and status before establishing an authenticated authentication. If using Spring Security with configured HTTP Basic/form login, the framework performs most of this chain.

## 5. Four Status Flags: Account Data Driving Login Decisions

For example, a database has three boolean states with **positive-for-bad-state** semantics:

```text
enabled = true
accountLocked = true
passwordExpired = false
```

When mapped to `UserDetails`:

```text
isEnabled()                 =  true
isAccountNonLocked()        = !accountLocked        = false
isCredentialsNonExpired()   = !passwordExpired      = true
```

With `DaoAuthenticationProvider`, `isAccountNonLocked=false` causes login to be rejected, even if the user enters the correct password. If the implementation forgets to map the flag or inverts the meaning, a locked account can log in.

| Source Status | Value on UserDetails | Typical Username/Password Login Behavior |
| --- | --- | --- |
| `enabled=false` | `isEnabled()=false` | Rejected with `DisabledException` at the provider (HTTP response may display a generic error). |
| `expired=true` | `isAccountNonExpired()=false` | Rejected with `AccountExpiredException`. |
| `locked=true` | `isAccountNonLocked()=false` | Rejected with `LockedException`. |
| `passwordExpired=true` | `isCredentialsNonExpired()=false` | Rejected with `CredentialsExpiredException`. |
| All conditions permit, but raw password is wrong | Flags may still be `true` | Rejected with `BadCredentialsException` after unsuccessful matching. |
| All conditions permit and password is right | Flags are `true` | Provider can return a successful authentication; authorization is still a separate step. |

**The check order in a specific provider** determines which internal exception is thrown first when multiple issues occur at once; do not assume every provider checks all status flags identically. When using HTTP Basic, these failures typically all manifest as **HTTP 401** under generic error handling. Do not rely on the 401 status code to guess whether an account is locked or the password is wrong.

### Business Differences Between Enabled and Locked

- `enabled=false` usually means the account is not yet activated or has been disabled by policy.
- `locked=true` usually means login must be blocked due to failed attempts, security signals, or administrative action.
- `accountExpired=true` can be used for subscription/time-limited accounts if the product is designed that way; distinguish this from a business contract expiring where the account can still log in to view data.
- `credentialsExpired=true` represents credentials that are no longer valid under policy; a password change/account recovery flow must be designed separately, not simply allowing any authenticated request to flip the flag.

Common pitfall: **account** status and **existing login** state are not identical. Setting `enabled` to false in the DB does not automatically delete every server session or immediately invalidate every issued JWT; you must define status re-checking, revocation, and session/token lifetime mechanisms.

### Are Status Flags Authorization?

No. They usually serve as **conditions for accepting authentication**. `getAuthorities()` describes the permissions granted to the principal; endpoints still need authorization checks. For example, a `ROLE_READER` user can log in successfully yet receive HTTP 403 when calling an endpoint requiring `ROLE_ADMIN`.

## 6. UserDetailsService: Which Record to Select and How to Populate Data?

The retrieval contract is:

```java
public interface UserDetailsService {
    UserDetails loadUserByUsername(String username)
            throws UsernameNotFoundException;
}
```

It is usually a **read-only lookup**, not an API for registering users, resetting passwords, or directly authenticating raw passwords. `UserDetailsManager` is a complementary contract for certain user management operations; `InMemoryUserDetailsManager` is only suitable for demos/tests and small cases.

**Minimum requirements for a loader:**

1. Receive the username identified by the authentication mechanism, applying defined canonicalization rules (e.g., lowercase email if business rules allow; do not uncontrolledly lowercase every identifier).
2. Look up using an appropriate index within **the right tenant/issuer/namespace scope**. If the login key is not globally unique, do not use an SQL query lacking a tenant constraint.
3. If not found, throw `UsernameNotFoundException`. Do not return a default user, and do not auto-grant permissions to an unknown account.
4. If a record exists, map the verifier/password hash, trusted authorities, enabled/locked/expired status, and other necessary fields.
5. Return a `UserDetails` object compatible with the current `PasswordEncoder` and provider, without placing unnecessary sensitive information into the principal.
6. Define cache lifecycle and state freshness. When an account is locked or permissions change, decide on cache invalidation/freshness and how to handle already-logged-in sessions.

A common place for the mapper is a security adapter layer: the **domain repository** knows the schema and data relationships; the **security adapter** transforms them into `UserDetails`. Keep DB access, transactions, and policies in the appropriate layers; do not stuff HTTP requests, email OTPs, or payment services into `UserDetails`.

### Username Is Not Necessarily Account ID

A person can change their email while their internal ID stays the same. A username like `alex` can exist across multiple organizations. If users log in by email, distinguish:

- **Login identifier**: lookup data, which can change over time.
- **Canonical subject/account ID**: stable identity key that the domain uses to link orders and tenants.
- **Display name**: display name that can collide, not used as a security key.

`getUsername()` can be the canonicalized login identifier. If business logic needs the account ID, a custom principal can hold the stable ID or the controller/service can look up the ID from a trusted source. Do not use a `username` string received from a JSON body to bypass the authenticated principal.

## 7. Mapping AccountRecord to UserDetails Without Ambiguity

This is a **complete mapping utility** when the application has an account record and already has `passwordHash` and `authorities` from a trusted source. It is helper code requiring Spring Security libraries on the classpath; it has no `main` so it does not run standalone via `java AccountUserMapper`.

File `src/main/java/demo/AccountUserMapper.java`:

```java
package demo;

import java.util.Set;

import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;

public final class AccountUserMapper {

    private AccountUserMapper() {
    }

    public record AccountRecord(
            String accountId,
            String loginName,
            String passwordHash,
            Set<String> grantedAuthorities,
            boolean enabled,
            boolean locked,
            boolean accountExpired,
            boolean passwordExpired) {
    }

    public static UserDetails toUserDetails(AccountRecord account) {
        return User.withUsername(account.loginName())
                .password(account.passwordHash())
                .authorities(account.grantedAuthorities().toArray(String[]::new))
                .disabled(!account.enabled())
                .accountLocked(account.locked())
                .accountExpired(account.accountExpired())
                .credentialsExpired(account.passwordExpired())
                .build();
    }
}
```

Notes:

- `passwordHash` is **already** an encoded password according to the system's `PasswordEncoder`. Do not re-`encode(...)` the stored hash on every load, because then the client's raw password can never match.
- `grantedAuthorities` are authority strings computed from the server's role/permission store; e.g., `ROLE_READER`, `orders:read`. Do not take permission lists directly from a request or hidden field.
- The flags in the domain are named `locked`, `accountExpired`, and `passwordExpired` with **true = bad state**; the builder uses this same meaning. When writing a custom `UserDetails` implementation, the `is...Non...` methods must invert the meaning.
- `accountId` is kept in the domain record, but the built-in `User` has no account ID accessor. If an ID is needed in the principal, build a minimal custom `UserDetails` with a stable ID or look it up by a verified key, accompanied by a tenant check.
- Provide an immutable copy/snapshot of the required data. Do not return a lazy-loaded Hibernate entity directly as the principal and use it across another request; it can cause unpredictable serialization, transaction, PII, and performance issues.

**Protecting authority mapping:** Do not generate authorities based on `request.getParameter("role")`. When a user has multiple roles, decide union/intersection according to policy, tenant, and grant source. Authentication only confirms the user; authorization continues evaluating the exact object being operated on.

### Role of PasswordEncoder When Storing Hashes

For example, with `PasswordEncoderFactories.createDelegatingPasswordEncoder()`, the `encode` output usually has an algorithm prefix like `{bcrypt}...`. `DaoAuthenticationProvider` calls `matches(rawPassword, userDetails.getPassword())`; it does not require you to provide a separate salt when the verifier format already embeds the corresponding parameters and salt.

If the application has legacy hashes, there must be a defined migration path: validate allowed old algorithms, safely update the hash when an opportunity arises, and manage password upgrades appropriately. `UserDetailsPasswordService` can participate in encoding upgrade mechanisms when compatible providers are configured, but do not assume by default that merely changing `PasswordEncoder` will automatically upgrade all accounts.

## 8. Runnable Spring Boot 3.x / Security 6.x Example

This example creates **five in-memory accounts** with the same demo password but different statuses:

| Username | Status | Result with Correct Credentials |
| --- | --- | --- |
| `alice` | Enabled, non-expired, unlocked, password non-expired | Login succeeds; has `ROLE_READER`. |
| `locked` | `accountLocked(true)` | Login rejected. |
| `disabled` | `disabled(true)` | Login rejected. |
| `expired` | `accountExpired(true)` | Login rejected. |
| `old-password` | `credentialsExpired(true)` | Login rejected. |

The goal is **to observe the fields UserDetails provides** to the provider. This is a locally run learning application, not a password storage approach for production. Requires **Java 17+**, Spring Boot 3.x, and the two starters `spring-boot-starter-web` and `spring-boot-starter-security`.

### 8.1 Source Code

File `src/main/java/demo/UserDetailsLessonApplication.java`:

```java
package demo;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class UserDetailsLessonApplication {

    public static void main(String[] args) {
        SpringApplication.run(UserDetailsLessonApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        String demoPassword = "local-only-password";

        UserDetails alice = User.withUsername("alice")
                .password(encoder.encode(demoPassword))
                .roles("READER")
                .build();

        UserDetails locked = User.withUsername("locked")
                .password(encoder.encode(demoPassword))
                .roles("READER")
                .accountLocked(true)
                .build();

        UserDetails disabled = User.withUsername("disabled")
                .password(encoder.encode(demoPassword))
                .roles("READER")
                .disabled(true)
                .build();

        UserDetails expired = User.withUsername("expired")
                .password(encoder.encode(demoPassword))
                .roles("READER")
                .accountExpired(true)
                .build();

        UserDetails passwordExpired = User.withUsername("old-password")
                .password(encoder.encode(demoPassword))
                .roles("READER")
                .credentialsExpired(true)
                .build();

        return new InMemoryUserDetailsManager(
                alice, locked, disabled, expired, passwordExpired);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers("/public").permitAll()
                        .requestMatchers("/api/me").authenticated()
                        .requestMatchers("/api/admin").hasRole("ADMIN")
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}

@RestController
class IdentityController {

    @GetMapping("/public")
    String publicPage() {
        return "public";
    }

    @GetMapping("/api/me")
    Map<String, Object> me(Authentication authentication) {
        return Map.of(
                "username", authentication.getName(),
                "authorities", authentication.getAuthorities().stream()
                        .map(GrantedAuthority::getAuthority)
                        .sorted()
                        .toList());
    }

    @GetMapping("/api/admin")
    String adminArea() {
        return "admin";
    }
}
```

Because the app uses `UserDetailsService` and `PasswordEncoder` configured as beans, Spring Security in a standard username/password setup can create/configure a suitable provider to verify credentials. You do not have to rewrite `DaoAuthenticationProvider` just to read the four flags. For systems with multiple custom authentication managers/filter chains, verify which beans and providers are wired into the actual chain.

**Component explanation:**

- `User.withUsername(...).password(...).roles("READER").build()` creates a standard `UserDetails`. `roles("READER")` is converted into the `ROLE_READER` authority.
- `disabled(true)` on the builder sets `isEnabled()` to `false`. Similarly, `accountLocked(true)` sets `isAccountNonLocked()` to `false`; `accountExpired(true)` and `credentialsExpired(true)` also have meanings opposite to the `NonExpired` method names.
- HTTP Basic receives username/password via headers and uses the authentication mechanism. HTTP Basic only Base64-encodes credentials in transit, **not secure encryption**; production requires HTTPS.
- The `/api/me` endpoint only returns username and authorities after authentication; it does not access `getPassword()` or `getCredentials()`, and does not serialize `UserDetails` directly to JSON.
- `/api/admin` requires `ROLE_ADMIN`, whereas the demo user only has `ROLE_READER`. A successfully logged-in user can still get 403 due to insufficient permissions.

### 8.2 How to Run with a Spring Boot Project

Create a Spring Boot 3.x project with the two starters mentioned above, place the file in package `demo`, and run it with the project's build tool.

On Linux/macOS using Gradle wrapper:

```bash
./gradlew bootRun
```

On Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Or with the Maven wrapper of an equivalent Spring Boot project:

```bash
./mvnw spring-boot:run
```

**Do not run `javac UserDetailsLessonApplication.java` alone** because the example imports Spring Framework, Spring Boot, and Spring Security; running `javac/java` directly requires the dependency classpath generated by the build tool. Run locally or in a closed test environment; do not deploy demo accounts/passwords to the Internet.

### 8.3 Calling the API and Checking Results

Test from another terminal (on Windows use `curl.exe` if PowerShell aliases `curl`):

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/api/me
curl -i -u alice:wrong http://localhost:8080/api/me
curl -i -u alice:local-only-password http://localhost:8080/api/me
curl -i -u locked:local-only-password http://localhost:8080/api/me
curl -i -u disabled:local-only-password http://localhost:8080/api/me
curl -i -u expired:local-only-password http://localhost:8080/api/me
curl -i -u old-password:local-only-password http://localhost:8080/api/me
curl -i -u alice:local-only-password http://localhost:8080/api/admin
```

| Request | Expected Result | Interpretation |
| --- | --- | --- |
| `GET /public` | HTTP 200, body `public` | No credentials required per `permitAll()`. |
| `GET /api/me` without credentials | HTTP 401 and HTTP Basic challenge | Endpoint requires an authenticated principal. |
| `alice:wrong` | HTTP 401 | Username exists, but raw password does not match hash. |
| `alice:local-only-password` | HTTP 200, JSON has `username` = `alice` and `authorities` contains `ROLE_READER` | Valid UserDetails and correct password. |
| `locked` with right password | HTTP 401 | `isAccountNonLocked=false` causes login to be rejected. |
| `disabled` with right password | HTTP 401 | `isEnabled=false`. |
| `expired` with right password | HTTP 401 | `isAccountNonExpired=false`. |
| `old-password` with right password | HTTP 401 | `isCredentialsNonExpired=false`. |
| `GET /api/admin` as alice | HTTP 403 | Authentication succeeded, but role is insufficient; this is authorization. |

Successful JSON has equivalent content:

```json
{
  "username": "alice",
  "authorities": ["ROLE_READER"]
}
```

JSON key order is not guaranteed; do not use exact byte-for-byte JSON as a criterion. The endpoint returns **no** password hash, raw password, or full principal. If you see HTTP 200 for `locked` or `disabled`, check the manager/provider configuration and the actual `UserDetails` object loaded.

**Reading the results properly:** `401` for `locked`/`disabled` shows that authentication was blocked; an endpoint returning the same error does not mean the internal reason is the same. Do not disclose details about whether a user exists or is locked in error messages if that is sensitive information. `403` when Alice accesses `/api/admin` proves access permissions are evaluated **after** authentication.

## 9. Custom UserDetails Implementation When the Domain Needs accountId

Spring Security provides `User` implementing `UserDetails`, suitable when you only need username/password/authorities/status. A custom class is useful when you need to attach a **stable account ID** for business logic or handle a specific security view. However, the custom class must uphold the contract.

A common design:

```java
package demo;

import java.util.Collection;
import java.util.List;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.userdetails.UserDetails;

public final class AccountPrincipal implements UserDetails {

    private final String accountId;
    private final String username;
    private final String passwordHash;
    private final List<GrantedAuthority> authorities;
    private final boolean enabled;
    private final boolean accountNonExpired;
    private final boolean accountNonLocked;
    private final boolean credentialsNonExpired;

    public AccountPrincipal(
            String accountId,
            String username,
            String passwordHash,
            Collection<? extends GrantedAuthority> authorities,
            boolean enabled,
            boolean accountNonExpired,
            boolean accountNonLocked,
            boolean credentialsNonExpired) {
        this.accountId = accountId;
        this.username = username;
        this.passwordHash = passwordHash;
        this.authorities = List.copyOf(authorities);
        this.enabled = enabled;
        this.accountNonExpired = accountNonExpired;
        this.accountNonLocked = accountNonLocked;
        this.credentialsNonExpired = credentialsNonExpired;
    }

    public String getAccountId() {
        return accountId;
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
}
```

This is a **security adapter data class**, without a `main`, requiring Spring Security dependencies to compile; it is not a standalone runnable application. It intentionally omits private email, phone, address, session secrets, or domain entities. In production, consider avoiding keeping `passwordHash` in the principal inside sessions/caches for too long; erasure, snapshots, and caching should be designed around the application's lifecycle, as in section 10.

### Status Mapping When Constructor Uses Non-Expired/Non-Locked Names

If the domain stores `locked=true`, the `accountNonLocked` constructor parameter must receive `!locked`. If the domain stores `expired=true`, pass `!expired` into `accountNonExpired`. Test each boolean inversion, especially when data comes from SQL columns like `status`/`deleted_at`/`locked_until`.

Do not capture an expiration timestamp from a clock once at startup and hold it forever in a singleton; `UserDetails` values must represent sufficiently fresh status at verification time according to policy. If status is computed from a timestamp, use a consistent clock/timezone and properly check boundary conditions such as `now >= expiresAt`.

### Serializer and equals/hashCode Considerations

A `UserDetails` instance may appear in the security context/session, cache, or distribution mechanisms across nodes. Avoid large object graphs and lazy entities; keep data compact and stable. If implementing `equals/hashCode`, choose a clear identity key appropriate for multi-tenancy; do not include password hashes or frequently changing attributes in the identity. Consider compatibility when changing serialized classes in a session store. Keep audit information separate from the principal rather than embedding the HTTP request object in it.

## 10. Authority: Data Needed by Authentication, While Authorization Decides Separately

`getAuthorities()` returns the `GrantedAuthority` instances assigned to the principal, such as `ROLE_READER` or `invoices:approve`. `GrantedAuthority.getAuthority()` typically returns a string; policies may use special authority types, and not all providers map them the same way.

With the built-in `User.UserBuilder`:

```java
UserDetails a = User.withUsername("alice")
        .password("{bcrypt}...") // Illustrative value, not a hash that can log in.
        .roles("READER", "EDITOR")
        .build();

// Authorities: ROLE_READER, ROLE_EDITOR
```

`roles("READER")` automatically adds the `ROLE_` prefix; do not pass `roles("ROLE_READER")` expecting it to stay as-is. If the data source already contains the full string `ROLE_READER`, use `authorities("ROLE_READER")` or a compatible mapping. Distinguish `hasRole("ADMIN")` (which checks `ROLE_ADMIN` by default) from `hasAuthority("orders:read")` (which checks the exact string).

A subject can be authenticated successfully with valid authorities yet lack permission for a specific object. For example, `ROLE_READER` does not grant automatic access to read records belonging to another tenant. `@PreAuthorize` and request-level authorization provide part of the control; object ownership and business policies must still be evaluated in the appropriate service/resource layer.

**Authority source principle:** Authorities originate from a controlled role/permission store or validated and properly mapped claims from a verified issuer. Do not grant authorities based on a `role` field in a form, query param, or custom client-sent header. If roles change after a user logs in, there must be a policy to refresh the session/context and cache.

## 11. Caching, Credential Erasure, and State Freshness

`UserDetails` contains the password verifier and authorities; caching can save queries, but it prolongs how long sensitive data remains present and causes stale state to continue being used.

### 11.1 How Does Caching Cause Stale State?

Scenario:

1. User Alice logs in, and `UserDetails` is loaded with `enabled=true` and `ROLE_ADMIN`.
2. The system caches that record for 30 minutes.
3. An administrator disables Alice or revokes her ADMIN role 5 minutes later.
4. New requests or a subsequent authentication still see the old copy if the cache is not invalidated/refreshed; already authenticated sessions may still retain old authorities.

System-dependent solutions: short cache TTL, event-based invalidation on account changes, keys scoped by tenant/namespace, reauthentication for sensitive actions, and checking authorization against fresh data when needed. **Changing a flag in the DB has no immediate effect on every issued session/JWT** without a revocation or freshness mechanism.

### 11.2 Which Objects Does eraseCredentials Affect?

By default, `ProviderManager` attempts to erase credentials on a successful `Authentication` if the object implements `CredentialsContainer`. In some cases, this behavior also affects principal/credentials/details that are erasable objects.

If a custom provider returns **the exact `UserDetails` instance from the cache** as the principal, erasing on the result can wipe the password hash inside that same cached instance; the next login attempt may fail because no hash remains to verify against. You must account for copying/caching mechanics and the specific `UserDetails` type:

- Do not share a mutable instance containing the hash between the cached verifier and the authenticated principal if erasure would corrupt the reused record.
- Use a separate security view, an appropriate copy, or a cache/credential-erasure plan verified by tests.
- Do not disable `eraseCredentialsAfterAuthentication` just to work around a cache bug without analyzing the risk of keeping secrets in memory.
- Do not log raw `UserDetails` or serialize all attributes as an API response; enforce an allowlisted DTO for required fields.

Note that Spring Security 6 has multiple login mechanisms. With a JWT resource server, the principal may be a `Jwt` rather than `UserDetails`, so caching and raw credential erasure policies differ from username/password. Do not claim that every authentication queries `UserDetailsService`.

### 11.3 Hash vs. Raw Password

`UserDetails.getPassword()` in a username/password flow should be an **encoded password verifier**; `Authentication.getCredentials()` before authentication is typically the raw password sent by the user. Both must be protected from logs/dumps, though they serve different functions and lifecycles.

- Hashes must be stored in a protected database with appropriate algorithm parameters/salts.
- Raw passwords should exist only long enough for verification; avoid secondary copies in logs.
- Never send password hashes to the client for "offline login".
- Clearing a Java variable does not guarantee all copies of a raw password/hash are gone from the JVM or monitoring systems.
- For passwordless tokens and passkeys, the verification contract may differ; do not force tokens into the domain's `passwordHash` field just to reuse `UserDetailsService`.

## 12. Very Common Implementation Mistakes

### 12.1 Loading a User and Treating It as Logged In

**Wrong:** A controller calls `userDetailsService.loadUserByUsername(request.getParameter("username"))` and creates a successful `Authentication`. **Right:** The filter/provider flow must verify credentials; business logic only receives a trusted principal after authentication.

### 12.2 Storing Plaintext Passwords or Double-Hashing

**Wrong:** The DB stores the raw password; or the loader calls `encoder.encode(hashFromDb)`. **Right:** Only encode when creating/changing a password; the loader returns the stored verifier; the provider calls `matches(raw, storedHash)`.

### 12.3 Returning `null` from loadUserByUsername

**Wrong:** `return null` when not found. **Right:** Throw `UsernameNotFoundException`. Falling back to a "default admin" branch in the loader is a critical vulnerability.

### 12.4 Inverting Status Meanings

**Wrong:** `isAccountNonLocked() { return record.isLocked(); }`. **Right:** `return !record.isLocked();`. Similarly `nonExpired` is the negation of expired; check carefully when mapping timestamps.

### 12.5 Forgetting to Override Status Flags

`UserDetails` has default boolean methods returning `true`. To enforce real state, you must override/map them properly. Tests for disabled/locked/expired accounts need to verify that login fails, not just test getters.

### 12.6 Reading Roles from the Request Payload

`getAuthorities()` must never read `role=ADMIN` from the client. Permissions must come from the server/trusted source. Also `roles("ADMIN")` prepends `ROLE_`; confusing prefixes often causes HTTP 403 even with a valid login.

### 12.7 Returning the Whole Domain Entity as UserDetails

This easily causes lazy loading exceptions, JSON circular references, leakage of password hashes/PII, or unstable identities. Create a lean security adapter with only the ID, verifier, authorities, and required status. Return filtered DTOs from APIs.

### 12.8 Same Username Across Multiple Tenants

If the service queries `findByUsername("alex")` without scoping to a tenant, it can load an account from the wrong organization. Canonicalize the identity namespace; verify tenant from a trusted context; do not let clients switch tenants via headers to access another account. Design a clear multi-tenant resolver/manager or subject key.

### 12.9 Confusing Authentication State with the Latest Authorization State

An old session may retain authorities in `SecurityContext` after the DB changes. A system requiring immediate permission revocation must have an appropriate re-check/invalidation mechanism rather than expecting DB `UserDetails` changes to push automatically to all sessions/tokens.

### 12.10 Casting Every Principal to UserDetails

HTTP Basic/form login may use `UserDetails`; bearer JWT/OIDC typically uses other principal types. In controllers, use `Authentication`/`getName()` or an adapter with a clear contract. With `@AuthenticationPrincipal`, ensure the type matches the active security chain.

## 13. Checklist for Designing a Production UserDetailsService

- **Identifier:** Is the login key unique within its namespace? Are case canonicalization, Unicode, email changes, and tenant handling defined?
- **Data source:** Does the query enforce tenant/issuer? Are deleted accounts, tenant transfers, and soft deletes handled?
- **Verifier:** Are passwords stored only as proper hashes; can `PasswordEncoder` read the current format and is there a hash upgrade plan?
- **Status:** Are `enabled`/`locked`/`expired`/`passwordExpired` mapped with the right polarity and reflective of login policy?
- **Authorities:** Is the permission source authoritative, properly scoped/tenanted, free of client-declared roles, and non-null?
- **Principal:** Does it only retain account ID, username, and needed authentication data, minimizing PII and lazy data?
- **Cache:** Is there TTL/invalidation on user lock, password change, permission change, and account deletion? Has credential erasure been tested with cached objects?
- **Failed logins:** Does it avoid leaking account existence/non-existence; does it log sufficient metadata without exposing passwords?
- **Session/token records:** Is it defined how long existing sessions and JWTs remain valid after a user is disabled or permissions change?
- **Multi-factor and federation:** If this flow involves an IdP/OTP/passkey, is it clear which responsibilities belong to other providers rather than cramming everything into `UserDetails`?
- **Testing:** Are bad password, unknown user, account flags, authorities, tenant, and cache branches meaningfully tested?

## 14. Test Matrix for Each Piece of Data the Provider Needs

| Case | Input Data | Expected Result |
| --- | --- | --- |
| User exists, right raw password, all status flags valid | Complete `UserDetails` and matching hash | Authentication succeeds; principal/authorities are correct. |
| User does not exist | Loader cannot find account | Throws `UsernameNotFoundException` in service; authentication fails and client receives appropriate response. |
| User exists, wrong password | Valid hash, but `matches=false` | Authentication fails; no authorities granted. |
| Legacy hash/unknown prefix | `PasswordEncoder` cannot handle format | Do not accept by default; handle safely via migration/encoder. |
| User is locked | `isAccountNonLocked=false` | Login rejected even with correct raw password. |
| User is disabled | `isEnabled=false` | Login rejected. |
| Account expired | `isAccountNonExpired=false` | Login rejected. |
| Password expired | `isCredentialsNonExpired=false` | Normal login rejected; recovery/rotation needs a separate flow. |
| Required role loaded | `getAuthorities()` contains `ROLE_READER` | Endpoint requiring READER allows access if other policies permit. |
| Missing role | Only `ROLE_READER`, endpoint needs ADMIN | Authentication succeeds, authorization rejects (typically HTTP 403). |
| Request sends `role=ADMIN` | Client payload is not an authority source | No privilege escalation. |
| Login on tenant B with username matching tenant A | Loader enforces tenant boundary | Does not load tenant A's record. |
| Cached UserDetails erased or stale | Cache reuses old instance/hash/status | Does not break second authentication; state changes apply per freshness policy. |
| Controller returns principal data | API response `/api/me` | Does not expose encoded password, raw credentials, PII, or session secrets. |
| JWT authentication on another security chain | Principal may be Jwt | Business logic/controller does not cast everything to UserDetails. |

**Important testing scope:** Mapper unit tests only prove value assignment; integration tests going through security filters/managers and HTTP status codes prove accounts are actually rejected. Cache/session cases require a context-persistence environment matching production behavior.

## 15. Scenario Exercises

**Exercise 1.** The database has a record:

```text
login_name      = "nina"
password_hash   = "{bcrypt}..."
enabled         = true
locked          = true
account_expired = false
password_expired= false
role            = "READER"
```

Determine what `UserDetails` should return.

**Answer:** `getUsername()="nina"`, `getPassword()` holds the stored hash, `getAuthorities()` contains `ROLE_READER` if policy uses that role. `isEnabled=true`, `isAccountNonLocked=false`, `isAccountNonExpired=true`, `isCredentialsNonExpired=true`. Normal username/password login must be blocked because the account is locked.

**Exercise 2.** An engineer writes:

```java
@Override
public boolean isAccountNonExpired() {
    return account.getExpiredAt() != null;
}
```

Is this correct?

**Answer:** No. `expiredAt != null` is not enough to confirm expiration (it could still be a future date); furthermore, `NonExpired` must return **true when the account has not expired**. Define explicit time conditions and clock handling, such as `expiresAt == null || now.isBefore(expiresAt)` per policy, paying attention to timezone and boundary behavior.

**Exercise 3.** `loadUserByUsername("alice")` returns a valid object. Can this object be used to grant an authenticated session without checking the password?

**Answer:** No. The loader only returns server-side data for verification; it does not prove the client possesses credentials. A provider must perform the authentication.

**Exercise 4.** `UserDetailsService` returns a password hash with the `{bcrypt}` prefix. May a controller output this hash when returning Alice's profile?

**Answer:** No. The hash is a sensitive verifier, and the user only needs permitted profile fields. Use a response DTO containing only allowed data; do not serialize the principal or entity directly.

**Exercise 5.** Alice logged in at 09:00 with `ROLE_ADMIN`. At 09:05 an admin revokes the role in the DB. At 09:06 Alice calls an API using her old session. Does the new `getAuthorities()` in the database guarantee the API will reject her?

**Answer:** Not automatically. The session may still hold the old authentication snapshot; you need a revocation/authority-refresh/live-policy-check mechanism or session invalidation to ensure changes take effect in a timely manner.

**Exercise 6.** With an OIDC token, will `(UserDetails) authentication.getPrincipal()` always work?

**Answer:** No. The principal type depends on the mechanism: OIDC/OAuth2/JWT may use `OAuth2User`, `OidcUser`, or `Jwt`. Read the contract of the active chain or use a type-safe unified adapter.

**Exercise 7.** An account has `enabled=false`, yet a mapper unit test passes because `getUsername()` and `getAuthorities()` are right. What is missing from the tests?

**Answer:** You must verify `isEnabled()=false`, and an authentication integration test through the real provider/filter must reject login; you can assert the exception at the provider layer and HTTP 401 at the API layer depending on configuration.

## 16. Reference Documentation

- [Spring Security — UserDetails](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/user-details.html): security view contract, credential management, and caching considerations.
- [Spring Security — UserDetailsService](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/user-details-service.html): source returning username/password/attributes for username-password authentication.
- [Spring Security — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/dao-authentication-provider.html): process for loading `UserDetails` and checking with `PasswordEncoder`.
- [UserDetails Javadoc (Spring Security 6.3)](https://docs.spring.io/spring-security/site/docs/6.3.x/api/org/springframework/security/core/userdetails/UserDetails.html): all three getters and four status flags with default methods.
- [User.UserBuilder Javadoc](https://docs.spring.io/spring-security/site/docs/6.4.x/api/org/springframework/security/core/userdetails/User.UserBuilder.html): `disabled`, `accountLocked`, `accountExpired`, `credentialsExpired`, `roles`, and `authorities`.
- [Spring Security — Password Storage](https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html): `PasswordEncoder` and verifiers with algorithm formatting.
- [Spring Security — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html): relationship among `Authentication`, `AuthenticationManager`, `AuthenticationProvider`, and `SecurityContextHolder`.

**Key takeaway:** `UserDetails` is **the minimal, trusted account data for a provider to check credentials and status**, not a client claim and not the entire domain user. `UserDetailsService` finds the right record, `PasswordEncoder` checks the verifier, `DaoAuthenticationProvider` decides authentication, `Authentication` carries the result, and authorization still checks permissions on resources.