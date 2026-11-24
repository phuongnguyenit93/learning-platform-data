# DaoAuthenticationProvider in Username and Password Authentication

## 1. What Problem Does DaoAuthenticationProvider Solve?

In Spring Security, **`DaoAuthenticationProvider` is an `AuthenticationProvider` implementation used to authenticate a username and password pair**. It receives an unauthenticated `UsernamePasswordAuthenticationToken`, retrieves account information from `UserDetailsService`, verifies the password using `PasswordEncoder`, checks account status, and returns an authenticated `Authentication` object when valid.

The name **DAO** (Data Access Object) reflects loading user information from a data source, yet this class **does not connect to JDBC/JPA on its own, does not query a `users` table by default, and does not create accounts automatically**. The concrete data source is supplied by the application via `UserDetailsService`: in-memory, JDBC, JPA repository, or a suitable adapter.

Remember the four roles:

| Component | Responsible for | Do not confuse with |
| --- | --- | --- |
| `UsernamePasswordAuthenticationToken` | Carries username/credentials into the authentication process; holds the result once verified. | Account store or password checker. |
| `AuthenticationManager` (usually `ProviderManager`) | Receives the request and delegates to a capable `AuthenticationProvider`. | Password-matching algorithm. |
| **`DaoAuthenticationProvider`** | Coordinates loading `UserDetails`, checking account status and `PasswordEncoder`, and building the authentication result. | Login controller, HTTP filter, or account persistence layer. |
| `UserDetailsService` + `PasswordEncoder` | Fetches login profile/authorities and compares the raw password against the stored hash. | Interchangeable operations. |

Business example: a user submits `lan` and password `DemoPass123!`. `UserDetailsService` looks up `lan`, returning `UserDetails` containing the password **hash** and permissions. `DaoAuthenticationProvider` runs `encoder.matches(rawPassword, storedHash)`, checks enabled/locked/expired flags, and returns an authenticated token. The controller does not need to fetch hashes from the database to compare them manually.

**Scope:** this is the **username/password** mechanism. JWT bearer, OIDC/OAuth2 login, and other authentication mechanisms have their own providers/flows; do not force every login method through `DaoAuthenticationProvider`.

## 2. Position in the Servlet Authentication Engine

With Spring MVC or HTTP Basic, the typical flow is as follows:

```text
Client sends username + password
           |
           v
Servlet security filter (e.g., BasicAuthenticationFilter
                          or UsernamePasswordAuthenticationFilter)
           |
           | creates UsernamePasswordAuthenticationToken
           |   principal   = client-supplied username
           |   credentials = raw password
           |   authenticated = false
           v
AuthenticationManager.authenticate(request)
           |
           v
ProviderManager
           |
           +--> selects AuthenticationProvider via supports(...)
                      |
                      v
              DaoAuthenticationProvider
                      |
                      +--> UserDetailsService.loadUserByUsername(username)
                      |          |
                      |          +--> in-memory, JDBC, JPA, DB adapter...
                      |          |
                      |          v
                      |        UserDetails: username, hash, enabled,
                      |                     locked/expired, authorities
                      |
                      +--> checks account status
                      +--> PasswordEncoder.matches(raw, storedHash)
                      +--> checks expired credentials, if applicable
                      |
           +----------+-----------+
           |                      |
        Failure                Success
           |                      |
           v                      v
AuthenticationException     Authenticated Authentication
(BadCredentialsException,    principal = UserDetails (default)
 DisabledException, ...)     authorities from trusted source
                              authenticated = true
                                     |
                                     v
                          Filter updates SecurityContext
                                     |
                                     v
                         Authorization checks permissions
                                     |
                                     v
                          Controller/service permitted
```

The diagram shows **a common configuration**; not every web request calls the provider. If a user already has an established valid session, a subsequent request can use the restored `SecurityContext` without re-running BCrypt. With HTTP Basic, clients may resend credentials on new requests and verification can run accordingly.

### At the Start vs. at the End, How Does `Authentication` Differ?

Input request:

```java
Authentication request =
    UsernamePasswordAuthenticationToken.unauthenticated(
        "lan", "DemoPass123!");
// request.isAuthenticated() == false
```

After successful authentication:

```java
Authentication verified = authenticationManager.authenticate(request);
// verified.isAuthenticated() == true
// verified.getPrincipal() is usually UserDetails
// verified.getAuthorities() contains trusted GrantedAuthorities
```

The input and result objects share the `Authentication` interface yet **do not have to be the same instance**. Use `verified`, rather than assuming the provider flips a flag directly on `request`. When the password is wrong or the account is invalid, the method normally throws a subclass of `AuthenticationException`; there is no “logged-in result” to continue using.

## 3. How Does One authenticate Cycle Work Inside the Provider?

`DaoAuthenticationProvider` extends `AbstractUserDetailsAuthenticationProvider`. The parent class provides the shared processing template; the provider implements fetching the user and verifying the password.

### Step 1. Check Request Type

`DaoAuthenticationProvider.supports(...)` matches `UsernamePasswordAuthenticationToken`. `ProviderManager` can hold multiple providers; a provider should accept only request types it understands. Therefore, `DaoAuthenticationProvider` is **not the place to verify JWTs or SAML assertions**.

If no provider supports the token type, `ProviderManager` may throw `ProviderNotFoundException`. This error usually points to wrong manager/provider wiring or input token type, not “the user's password is wrong”.

### Step 2. Load `UserDetails`

The provider uses `UserDetailsService.loadUserByUsername(String username)` to fetch the authentication profile:

- `getUsername()`: account name / login identifier.
- `getPassword()`: **the hashed/encoded password string**, not plaintext.
- `isEnabled()`: whether the account is enabled.
- `isAccountNonLocked()`: not locked.
- `isAccountNonExpired()`: account has not expired.
- `isCredentialsNonExpired()`: credentials have not expired.
- `getAuthorities()`: roles/scopes/permissions granted to the account by the application.

`UserDetailsService` **only loads account data**. It does not run `matches(...)` itself, does not create a session itself, and must not treat finding a username as the user being logged in.

If not found, the implementation should throw `UsernameNotFoundException`. By default, `AbstractUserDetailsAuthenticationProvider` typically translates a non-existent user into `BadCredentialsException`, identical to a wrong password, to limit revealing whether an account exists.

### Step 3. Check Account Status

The provider framework performs account-status checks (pre/post authentication checks) per configuration:

| `UserDetails` status | Meaning | Typical exception |
| --- | --- | --- |
| `enabled == false` | Account has been disabled. | `DisabledException` |
| `accountNonLocked == false` | Account is currently locked. | `LockedException` |
| `accountNonExpired == false` | Account has expired. | `AccountExpiredException` |
| `credentialsNonExpired == false` | Password/credentials have expired. | `CredentialsExpiredException` |

The account-status checks and password comparison steps may be adjusted depending on version/configuration. Do not write business logic that depends on the **order** of exceptions leaking to the client. Login APIs should usually return a controlled external message; internal logs can categorize causes for operations, without logging secrets.

### Step 4. Compare Passwords Properly

`DaoAuthenticationProvider` calls `PasswordEncoder.matches(rawPassword, storedEncodedPassword)`. With BCrypt:

```java
PasswordEncoder encoder = new BCryptPasswordEncoder();
String hash = encoder.encode("DemoPass123!");

System.out.println(encoder.matches("DemoPass123!", hash)); // true
System.out.println(encoder.matches("wrong", hash));        // false
```

`encode` uses a random salt, so calling it twice can produce **two different hashes for the same password**. Therefore, **do not** compare `encoder.encode(input).equals(storedHash)`. `matches` reads the hash format and applies the required parameters to compare properly.

The application must use **an encoder compatible with the stored data**. For instance, if storing raw BCrypt directly, `BCryptPasswordEncoder` understands `$2a$...`/`$2b$...` hashes; if using `DelegatingPasswordEncoder`, stored strings typically have a prefix like `{bcrypt}...`. Mixing storage formats without consistent rules can cause valid passwords to fail matching or report an unknown id.

### Step 5. Create a Trusted Result

When checks pass, the provider builds an **authenticated** `UsernamePasswordAuthenticationToken`, typically containing:

- `principal`: the `UserDetails` object returned from the source (default), or a `String` if the application explicitly configured `setForcePrincipalAsString(true)`.
- `authorities`: the `GrantedAuthority` instances from the account, optionally passed through `GrantedAuthoritiesMapper` if configured.
- `isAuthenticated() == true`.
- `credentials`: may temporarily exist on the provider's result; `ProviderManager` by default tries to erase credentials on a successful result via `CredentialsContainer`.

**Do not call** `UsernamePasswordAuthenticationToken.authenticated(usernameFromClient, null, suppliedRoles)` yourself to “quick log in”: doing so bypasses verification. Always use the configured provider/manager and use the object returned after success.

### Step 6. Place the Result into `SecurityContext`

`DaoAuthenticationProvider` **does not create HTTP sessions or cookies itself**. It returns `Authentication` to the caller. With standard login filters, the filter/framework manages updating `SecurityContext`, handling failure/success, and saving state per the configured authentication mechanism.

If calling `AuthenticationManager.authenticate(...)` directly in console or service code, the result is **not automatically** placed in `SecurityContextHolder`. Set the context manually only when you understand the session/context contract and are not bypassing security filters.

## 4. Complete Java 17+ Example: Provider, User Store, Errors, and Result

This console example uses **Spring Security 6.5.11**, Java 17+, and Gradle. It demonstrates the exact provider behavior **without needing a web server or Spring Boot**. `InMemoryUserDetailsManager` serves as the test identity store; `BCryptPasswordEncoder` handles hashing and password comparison.

Structure:

```text
dao-provider-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/DaoProviderDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'dao-provider-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
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
    implementation 'org.springframework.security:spring-security-crypto:6.5.11'
}

application {
    mainClass = 'demo.DaoProviderDemo'
}
```

`src/main/java/demo/DaoProviderDemo.java`:

```java
package demo;

import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.DisabledException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;

public final class DaoProviderDemo {

    public static void main(String[] args) {
        // Demo identity store: stores hashes only, never plaintext passwords.
        PasswordEncoder encoder = new BCryptPasswordEncoder();

        UserDetails lan = User.withUsername("lan")
                .password(encoder.encode("DemoPass123!"))
                .roles("READER")
                .build();

        UserDetails khoa = User.withUsername("khoa")
                .password(encoder.encode("AnotherPass123!"))
                .roles("READER")
                .disabled(true)
                .build();

        InMemoryUserDetailsManager users =
                new InMemoryUserDetailsManager(lan, khoa);

        // DaoAuthenticationProvider loads UserDetails and compares credentials.
        DaoAuthenticationProvider dao = new DaoAuthenticationProvider(users);
        dao.setPasswordEncoder(encoder);

        // In web apps, AuthenticationManager is usually invoked by a filter.
        AuthenticationManager manager = new ProviderManager(dao);

        System.out.println("dao.supportsUsernamePassword="
                + dao.supports(UsernamePasswordAuthenticationToken.class));

        Authentication request =
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "lan", "DemoPass123!");

        System.out.println("request.authenticated=" + request.isAuthenticated());
        System.out.println("request.authorities=" + request.getAuthorities().size());

        // 1. Wrong password: no authenticated token is returned.
        try {
            manager.authenticate(
                    UsernamePasswordAuthenticationToken.unauthenticated(
                            "lan", "wrong-password"));
        } catch (BadCredentialsException ex) {
            System.out.println("wrongPassword=BadCredentialsException");
        }

        // 2. Non-existent username: also hidden as BadCredentials by default.
        try {
            manager.authenticate(
                    UsernamePasswordAuthenticationToken.unauthenticated(
                            "unknown", "any-password"));
        } catch (BadCredentialsException ex) {
            System.out.println("unknownUser=BadCredentialsException");
        }

        // 3. Disabled account: rejected even with the matching password.
        try {
            manager.authenticate(
                    UsernamePasswordAuthenticationToken.unauthenticated(
                            "khoa", "AnotherPass123!"));
        } catch (DisabledException ex) {
            System.out.println("disabledUser=DisabledException");
        }

        // 4. Valid authentication: receives a newly verified Authentication.
        Authentication result = manager.authenticate(request);

        System.out.println("result.authenticated=" + result.isAuthenticated());
        System.out.println("result.name=" + result.getName());
        System.out.println("result.principalIsUserDetails="
                + (result.getPrincipal() instanceof UserDetails));
        System.out.println("result.hasReaderRole=" + result.getAuthorities()
                .stream()
                .anyMatch(a -> "ROLE_READER".equals(a.getAuthority())));
        System.out.println("result.credentialsErased="
                + (result.getCredentials() == null));

        // 5. Setting SecurityContext in console; web filters handle this separately.
        SecurityContext context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(result);
        SecurityContextHolder.setContext(context);
        try {
            System.out.println("context.name="
                    + SecurityContextHolder.getContext()
                    .getAuthentication().getName());
        } finally {
            SecurityContextHolder.clearContext();
        }
        System.out.println("context.cleared="
                + (SecurityContextHolder.getContext().getAuthentication() == null));
    }
}
```

Run from the project root using JDK 17+ and Gradle supporting Java 17 (or a compatible Gradle Wrapper):

```bash
gradle run --quiet
```

**Stdout lines from `System.out.println` in exact order** (excluding Gradle or library logs if emitted by the environment):

```text
dao.supportsUsernamePassword=true
request.authenticated=false
request.authorities=0
wrongPassword=BadCredentialsException
unknownUser=BadCredentialsException
disabledUser=DisabledException
result.authenticated=true
result.name=lan
result.principalIsUserDetails=true
result.hasReaderRole=true
result.credentialsErased=true
context.name=lan
context.cleared=true
```

Explaining each observation:

1. `supportsUsernamePassword=true` because the provider handles `UsernamePasswordAuthenticationToken`.
2. The initial request has `isAuthenticated()==false` and no trusted permissions; having a username does not mean logged in.
3. Both `wrongPassword` and `unknownUser` receive `BadCredentialsException` per default username-hiding behavior. Do not change the configuration just to tell clients whether an account exists.
4. `disabledUser` is rejected by the account-state check; `isEnabled() == false` cannot pass authentication even with the right password.
5. `result.authenticated=true` because the manager/provider actually verified it, not because code manually set a flag.
6. The resulting principal is `UserDetails`, and role `READER` appears as authority `ROLE_READER`. A role's display name and the authority string are not the same thing.
7. `result.credentialsErased=true` is the outcome of `ProviderManager.eraseCredentialsAfterAuthentication`'s default setting on a successful token; **do not pull the password out of the result for further use**.
8. `context.name=lan` is printed after the demo manually puts the result into the context; `finally` clears the context. In web applications, filters/session mechanisms manage those steps.

Passwords and hashes in the example are dummy data for learning; never hardcode production credentials. BCrypt hashes have random salts, so the example intentionally **does not print literal hashes**. Never print `getCredentials()` or the entire `Authentication` object in logs because the request may carry secrets.

## 5. Inside `UserDetailsService`: Where Is the “DAO”?

`DaoAuthenticationProvider` only needs the `UserDetailsService` contract:

```java
UserDetails loadUserByUsername(String username)
        throws UsernameNotFoundException;
```

Implementations can read from many sources. Two examples:

### A. In-Memory for Demos and Tests

```java
UserDetails user = User.withUsername("lan")
    .password(encodedPassword)
    .authorities("document:read", "ROLE_READER")
    .build();

UserDetailsService users = new InMemoryUserDetailsManager(user);
```

`encodedPassword` in the snippet must be a hash string compatible with the encoder (e.g., `encoder.encode(...)` when creating the user). This snippet only illustrates building a user store, not a standalone program.

### B. Real Repository (Adapter Sketch)

Suppose a module has `AccountRepository` and an `Account` entity containing `username`, `passwordHash`, `enabled`, and `roles`. An adapter can be written as:

```java
// Illustrative code in an application with AccountRepository and Account defined.
// Needs imports for Spring @Service, UserDetailsService, User,
// UsernameNotFoundException, and entity/repository types.
@Service
class AccountDetailsService implements UserDetailsService {

    private final AccountRepository accounts;

    AccountDetailsService(AccountRepository accounts) {
        this.accounts = accounts;
    }

    @Override
    public UserDetails loadUserByUsername(String username) {
        Account account = accounts.findByUsername(username)
                .orElseThrow(() -> new UsernameNotFoundException(
                        "Account not found"));

        String[] authorities = account.roles().stream()
                .map(role -> "ROLE_" + role)
                .toArray(String[]::new);

        return User.withUsername(account.username())
                .password(account.passwordHash())
                .disabled(!account.enabled())
                .authorities(authorities)
                .build();
    }
}
```

This snippet intentionally omits repository/entity definitions, transactions, and schema; it is an **illustrative adapter**, not a standalone buildable example. In real applications, preserve lock/expiration flags per system policy, normalize usernames properly, map vetted permissions, and handle null/duplicates.

**Crucial point:** `UserDetailsService` does not return “a logged-in user”; it returns data for the provider to verify. When the password does not match, `DaoAuthenticationProvider` fails even though the repository returned an account with the matching name.

### Why Not `SELECT password_hash` and Compare Manually in a Controller?

Embedding password checks inside controllers makes endpoints prone to mistakes or policy drift: missing locked accounts, verifying hashes wrongly, forgetting to update the security context, logging secrets, or trusting client-supplied roles. Use Spring Security's manager/provider to centralize verification, while controllers receive the framework-established `Authentication` result and execute business logic.

## 6. PasswordEncoder, Hashes, DelegatingPasswordEncoder, and Password Upgrades

### Proper Comparison

User input is the **raw password**; the stored value is the **encoded password**. Interface:

```java
String stored = encoder.encode(rawPassword); // When creating/changing password
boolean valid = encoder.matches(rawPassword, stored); // On login
```

BCrypt, PBKDF2, scrypt, and Argon2 are one-way functions with tunable computational cost. Choose the algorithm, work factor, and upgrade policy according to system capacity; never use plaintext, `NoOpPasswordEncoder` in production, or raw SHA-256 hashes unsuited for password storage.

**Note on `DelegatingPasswordEncoder`:** it identifies the algorithm from the `{id}` prefix in the stored string, for example:

```text
{bcrypt}$2a$...
{pbkdf2@SpringSecurity_v5_8}...
```

Common call site:

```java
PasswordEncoder encoder =
    PasswordEncoderFactories.createDelegatingPasswordEncoder();
```

`DelegatingPasswordEncoder` encodes by default using a current algorithm chosen by the factory and can read multiple formats with registered ids. If the DB stores raw BCrypt `$2a$...` yet configuration switches to default delegating **without `{bcrypt}`**, `matches` can fail because no id is identified. A controlled migration strategy is required; never arbitrarily alter DB hashes by prepending prefixes without verifying the format.

### Upgrading Hashes

`PasswordEncoder.upgradeEncoding(encodedPassword)` indicates whether a hash string should be upgraded per encoder configuration. `DaoAuthenticationProvider` can combine with `UserDetailsPasswordService` to update to a new hash **after a successful password check**. The update implementation is responsible for data integrity, concurrency handling, and preserving account status.

Do not assume simply declaring a `PasswordEncoder` automatically migrates all legacy hash records. To update stored hashes, configure an appropriate update service and keep legacy format support during the transition window.

### Compromised Password Checking

Since Spring Security 6.3, `DaoAuthenticationProvider` supports configuring a `CompromisedPasswordChecker` (for example, integrating a leaked-password checking service). This is an optional extra capability, **not a replacement** for `PasswordEncoder.matches`, MFA, rate limiting, or account lifecycle management.

Do not send plaintext passwords to arbitrary external services. Evaluate protocol contracts, privacy, availability, and fallback policy when the checker is unavailable.

## 7. Handling Authentication Errors: Exceptions Carry Different Meanings

`AuthenticationManager.authenticate(...)` usually throws `AuthenticationException` if it cannot authenticate the request. Common types:

| Exception | Scenario | How to handle |
| --- | --- | --- |
| `BadCredentialsException` | Wrong password; non-existent username when default config hides details. | Return a generic login error; do not reveal which usernames exist. |
| `DisabledException` | User is disabled. | Maintain account-state policy; guide support via proper flow. |
| `LockedException` | User is locked. | Protect unlock workflow; avoid leaking sensitive info. |
| `AccountExpiredException` | Account has expired. | Clarify account lifecycle policy. |
| `CredentialsExpiredException` | Password has expired. | Redirect to a secure password-change flow. |
| `ProviderNotFoundException` | Manager has no provider supporting the token. | Check provider/token wiring; usually a configuration bug. |
| `AuthenticationServiceException` | System/data-source error during authentication. | Record and handle incident; do not treat as wrong password in all cases. |

**HTTP status codes are not determined mechanically from exception names alone.** Form login usually redirects to a login page and invokes failure handling; HTTP Basic usually returns `401` with `WWW-Authenticate`; permission checks on a logged-in identity lacking authority can produce `403`. This depends on `AuthenticationEntryPoint`, failure handlers, `AccessDeniedHandler`, and the configured web mechanism.

By default, `hideUserNotFoundExceptions=true` helps mitigate enumeration by exception type; it is **not a complete shield against timing attacks**, brute force, or leaks via differing responses. Use patched Spring Security versions, rate-limit login attempts, monitor anomalies, and avoid revealing user existence details to clients.

## 8. Using with Spring Boot Servlet

**Spring Boot builds the context and integrates Spring Security into the web app; `DaoAuthenticationProvider` remains Spring Security's username/password authentication mechanism.** You can supply `UserDetailsService` and `PasswordEncoder` beans for the framework to use, or declare a `DaoAuthenticationProvider` bean explicitly when direct control over the provider is needed.

An illustrative configuration in an app that already includes `spring-boot-starter-web` and `spring-boot-starter-security`:

```java
// Illustrative configuration; place in a @Configuration class of the Boot project.
// Needs imports: @Bean, @Configuration, HttpSecurity, SecurityFilterChain,
// Customizer, User, UserDetailsService, InMemoryUserDetailsManager,
// DaoAuthenticationProvider, PasswordEncoder, BCryptPasswordEncoder.
@Configuration
class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("lan")
                .password(encoder.encode("DemoPass123!"))
                .roles("READER")
                .build()
        );
    }

    @Bean
    DaoAuthenticationProvider daoAuthenticationProvider(
            UserDetailsService users, PasswordEncoder encoder) {

        DaoAuthenticationProvider provider =
                new DaoAuthenticationProvider(users);
        provider.setPasswordEncoder(encoder);
        return provider;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, DaoAuthenticationProvider provider)
            throws Exception {

        http
            .authenticationProvider(provider)
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/documents").hasRole("READER")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
```

This is an **illustrative configuration, not a complete Boot project**: a `@SpringBootApplication` startup class, controller endpoints, dependencies, and proper imports are required. Constructing `DaoAuthenticationProvider(UserDetailsService)` here is compatible with Spring Security **6.5.11**; for Boot 3.3 projects on Security 6.3, check the actual version's API before copying the constructor as overloads have evolved across releases.

When running in practice with HTTP Basic:

- `/public` has `permitAll()`, so no login is needed.
- `/documents` requires `ROLE_READER`; using HTTP Basic with valid `lan:DemoPass123!` lets the provider produce an authenticated token.
- If credentials are missing, the app may prompt for login with `401` and `WWW-Authenticate`; if authenticated yet lacking the role, usually `403`.
- Use **HTTPS** in real deployments. HTTP Basic encodes with Base64 yet **does not encrypt secrets**, and should only be used over properly protected connections.
- Never widen `permitAll()` to bypass 401/403 configuration errors; determine whether the request reached the filter/provider, whether the user is locked, and whether authorities are mapped properly.

In Spring Boot, declaring a `SecurityFilterChain` bean can cause Boot's default web security config to back off; creating/selecting `UserDetailsService` is a separate decision. **Do not assume users in a database are automatically authenticated merely because Boot has JPA and a User entity.**

### Separating “Login” and “Authorization”

`DaoAuthenticationProvider` returns verified identity and authorities. A `hasRole("READER")` rule matches the `ROLE_READER` authority string by default convention, whereas `hasAuthority("document:read")` matches verbatim. Both require mapping permission data properly at the source.

For permissions on specific data, such as “only view documents owned by oneself”, add owner/resource checks at the business layer or via method security. A user with `ROLE_READER` cannot implicitly read every account's documents.

## 9. Caching, SecurityContext, and Real-World Deployment Consequences

### `UserCache` Is Not a Session

`AbstractUserDetailsAuthenticationProvider` supports `UserCache`, though the default is typically `NullUserCache`. In a session-based web app, after successful login, subsequent requests can read the context from the session without calling `UserDetailsService` and BCrypt on every request.

If `UserCache` is enabled for the provider, you must handle cache invalidation when a user changes passwords, gets locked, or has roles changed. A cache holding a `UserDetails` object whose hash was erased by `CredentialsContainer.eraseCredentials()` can cause subsequent authentication failures. Consider copying objects into the cache or designing credential-erasure/caching compatible with your threat model; do not disable credential erasure just to make caching “work” without understanding the consequences.

### Roles and Status Changing After Login

Once the manager returns a token, `Authentication` can hold authorities from the time of authentication. When an account is disabled or a role is revoked in the database, existing sessions/JWTs or stale contexts **do not automatically** reflect the change without an update/revocation/re-authentication mechanism.

Design session lifetimes, refresh flows, dynamic permissions, and revocation mechanisms appropriate to your risk level. Never assume every request re-queries `UserDetailsService`.

### Threads and Context

In Servlet applications, `SecurityContextHolder` defaults to a thread-bound context. The Spring Security filter chain manages setting up and clearing the context per request. With async/task executors, propagate principal/context properly via built-in integration mechanisms; never put `Authentication` into a global static variable or a shared multi-user cache.

## 10. Common Mistakes

1. **“DAO provider queries the `users` table automatically.”** No. It depends on `UserDetailsService`; the application must provide the source and adapter.
2. **“Finding the username means login succeeded.”** Wrong. The provider also checks the password hash and account status.
3. **“You can compare two `encoder.encode(...)` outputs.”** Wrong with salted BCrypt; use `matches(raw, encoded)`.
4. **“The default `PasswordEncoder` always understands every hash.”** Wrong. It must match the data format; delegating normally requires `{id}`.
5. **“Setting `isAuthenticated=true` is enough.”** Wrong. Trust only results returned by a verified manager/provider; never fabricate trusted tokens from a request body.
6. **“Every resource access calls `DaoAuthenticationProvider` again.”** Wrong with session/caching mechanisms; many requests use the restored context.
7. **“`DaoAuthenticationProvider` writes sessions/cookies itself.”** Wrong. The provider returns a result; filters, context repositories, and success/failure handlers manage the web request parts.
8. **“`UserDetailsService` checks the password itself.”** Not per standard contract. It is the data source, while the provider/encoder verifies credentials.
9. **“Non-existent usernames always return `UsernameNotFoundException` to the client.”** By default, the provider typically hides it as `BadCredentialsException`; do not expose account existence.
10. **“Roles from the client are used directly.”** No. Authorities must come from/map from a verified source; `ROLE_READER` differs from the string `READER` depending on policy.
11. **“Erasing raw passwords on success means all logs are clean.”** No. Leaks can still occur in request access logs, error logs, tracing, URL queries, and debug dumps. Never write secrets to logs.
12. **“Turning on account lockouts is enough against brute force.”** You also need rate limiting, monitoring, recovery, and policies preventing attackers from locking out mass users.
13. **“Use `NoOpPasswordEncoder` to ship to production faster.”** Wrong. Only use encoders that store proper hashes; demos must clearly separate learning environments from real deployments.
14. **“DAO provider replaces every other provider.”** No. It handles username/password; JWT/OIDC/pre-authentication each have their own contracts.
15. **“Successful login means every API is allowed.”** No. Authorization must check roles, permissions, and access to business objects.
16. **“Just catch every `AuthenticationException` and return true.”** Dangerous: destroys trust boundaries. Only translate failures into safe responses without faking success results.

## 11. Self-Check Your Understanding

**Question 1.** `UserDetailsService.loadUserByUsername("lan")` returned an account with a hash and roles. Is `lan` logged in yet?

**Answer:** Not yet. `DaoAuthenticationProvider` still has to verify credentials and status; only a successful result from the manager/provider represents a valid authentication.

**Question 2.** Calling `encoder.encode("x")` twice yields different hashes. Is the encoder broken?

**Answer:** No. BCrypt uses a random salt; you must use `matches("x", storedHash)`.

**Question 3.** A request submits a non-existent username. By default, does returning `UsernameNotFoundException` to the client differ from a wrong password?

**Answer:** The provider typically hides non-existent usernames under `BadCredentialsException`. The web layer also decides how HTTP errors are represented; avoid leaking a list of valid accounts.

**Question 4.** Can `DaoAuthenticationProvider` authenticate a bearer JWT simply by adding a `UserDetailsService`?

**Answer:** No. `DaoAuthenticationProvider` processes username/password tokens. A JWT resource server needs bearer token decoding/verification mechanisms and the corresponding provider/converter.

**Question 5.** You called `manager.authenticate(request)` and got `result`. Is `SecurityContextHolder` automatically updated?

**Answer:** Not guaranteed on manual calls; standard web filters manage context/sessions, while custom code must respect that contract.

**Question 6.** `UserDetails` has `isEnabled()==false` yet the password is right. Do you get an authenticated token?

**Answer:** No. The account-state check rejects disabled accounts, typically via `DisabledException`.

**Question 7.** Why can `result.getCredentials()` be `null` even when authentication succeeded?

**Answer:** `ProviderManager` by default tries to erase credential data from the result to reduce secret retention risk. Do not rely on passwords after login.

**Question 8.** Does `ROLE_READER` mean the user can view everyone's documents?

**Answer:** No. A role is only a coarse-grained authority. Checking data ownership / fine-grained permissions is a separate authorization step.

## 12. Official Documentation and Next Reading

- [Spring Security 6.5.11 — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html): diagram of filter → manager → provider → `UserDetailsService`/`PasswordEncoder`.
- [DaoAuthenticationProvider API 6.5.11](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/dao/DaoAuthenticationProvider.html): constructors, `setPasswordEncoder`, `setUserDetailsPasswordService`, `setCompromisedPasswordChecker`.
- [AbstractUserDetailsAuthenticationProvider API 6.5.11](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/dao/AbstractUserDetailsAuthenticationProvider.html): state checks, `UserCache`, exception hiding, result token.
- [Spring Security 6.5 — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): `Authentication`, `ProviderManager`, `SecurityContext`, and credentials erasure.
- [Spring Security 6.5 — Password Storage](https://docs.spring.io/spring-security/reference/6.5/features/authentication/password-storage.html): BCrypt, DelegatingPasswordEncoder, work factor, `{id}` format.
- [Spring Security — CVE-2026-22746](https://spring.io/security/cve-2026-22746/): advisory regarding account status checks and timing; the example above uses 6.5.11 from the patched line.

**Key takeaway:** `DaoAuthenticationProvider` is the **username/password verification** component built on `UserDetailsService` and `PasswordEncoder`, checking account status and returning a trusted `Authentication` on success. Account storage, HTTP filters/sessions, and authorization policies are separate responsibilities. Keeping those boundaries clear lets you swap in-memory storage for a database without rewriting password-verification logic inside controllers.