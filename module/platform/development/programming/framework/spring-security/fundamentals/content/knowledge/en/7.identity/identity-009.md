# Designing a Compact Principal Without Storing Passwords or Unnecessary Sensitive Data

## 1. Goal and Real-World Problem

When a login request is authenticated successfully, Spring Security can place an **`Authentication`** into **`SecurityContext`**. `Authentication` carries **`principal`** (identity), **`credentials`** (authentication evidence), **`authorities`** (permissions), **`details`** (auxiliary data), and authenticated status.

If a developer puts an entire **`UserEntity`** into the principal, the object may carry password hashes, emails, phone numbers, addresses, payment details, JPA relationships, and database-only columns. Problems occur when this object is retained long-term in sessions, caches, heap dumps, debug logs, exceptions, JSON responses, or messaging systems.

**Principle:** Put into the principal only the data **truly needed to identify the caller and enforce access policies**. Passwords, password hashes, and identity-verification tokens must be handled during the authentication phase; never store copies inside the business-layer principal.

Example scope: **Java 17+, Spring Boot 3.3.x, Spring Security 6.3.x, and Spring MVC/Servlet**. For JWT/OIDC and WebFlux, principals have different types; specific considerations are covered later.

After this lesson, you will be able to distinguish components in `SecurityContext`, choose fields for a principal, write an immutable principal using an internal ID, build an authentication demo that stores no hashes in the principal, avoid serializing sensitive data, understand credential erasure, audit sessions/caches, and design per-resource authorization.

## 2. What Is a Principal, and How Does It Differ from Authentication?

In Java, **`java.security.Principal`** has `getName()` to express identity. In Spring Security, **`Authentication`** extends `Principal` and adds `getPrincipal()`, `getCredentials()`, `getDetails()`, `getAuthorities()`, and `isAuthenticated()`.

Typically, when people say "the request's principal", they mean **`Authentication.getPrincipal()`**.

| Field | Meaning | Warning |
| --- | --- | --- |
| `Authentication.getPrincipal()` | Identity of the sender or authenticated subject | Type `Object`; not automatically a `User` entity |
| `Authentication.getCredentials()` | Password, token, or authentication evidence | Secret; avoid long retention and never log |
| `Authentication.getAuthorities()` | Permissions granted from a trusted source | Never trust client-claimed authorities |
| `Authentication.getDetails()` | Authentication/request metadata | May contain IP, session ID, or sensitive info |
| `Authentication.isAuthenticated()` | Verified status per framework mechanism | Only trusted providers/managers may mark success |
| `SecurityContext` | Holds the active `Authentication` | May be persisted via session or repository |
| `UserDetails` | Account data serving username/password | May hold a password hash |
| API response DTO | Data returned to the client | Must select fields explicitly per allowed permissions |

**`UserDetails` does not mean a minimal principal.** `DaoAuthenticationProvider` normally uses `UserDetailsService` to load `UserDetails`, verifies the password, and may return `UserDetails` as the principal. `UserDetails` has `getPassword()` because it serves password verification. That does not mean `UserDetails` should be returned to clients or logged as a whole object.

### 2.1. Before and After Authentication

The input can be an unauthenticated token:

~~~java
Authentication attempt =
    UsernamePasswordAuthenticationToken.unauthenticated(
        "alice", "learn123"
    );
~~~

This is a Java snippet inside a method with imports already present; not a standalone program. Principal is the client-claimed name, credentials is the client-sent password, and **`isAuthenticated()` must be false**.

Only after the provider verifies successfully is the `Authentication` considered trusted. A sound configuration can transition from the client-claimed username to a **verified internal ID**, set `credentials=null`, and grant authorities from a trusted data source.

**Creating an authenticated `UsernamePasswordAuthenticationToken` solely from a client-sent ID without checking a password or token is an authentication vulnerability.**

### 2.2. Hashes Are Also Sensitive Credentials

Password hashes using BCrypt, Argon2, or similar algorithms are not plaintext. Yet if a hash leaks, attackers can run offline password cracking, exploit weak passwords, or uncover password reuse. Therefore a password hash is not a "safe to expose" field.

A credential store may need the hash for comparison, whereas the request's principal **needs no hash** to query orders, check permissions, or record who performed an action.

## 3. Choosing Minimal Data for the Principal

A principal should:

1. **Identify sufficiently:** One stable internal `userId`/subject is usually enough.
2. **Come from a verified source:** Never take an arbitrary `userId` or role from the request and trust it.
3. **Be immutable:** Avoid setters that mutate identity after authentication.
4. **Be small and easily serializable when needed:** Never hold JPA entities, `HttpServletRequest`, `EntityManager`, or dependencies/services.
5. **Contain no secrets:** No passwords, hashes, refresh tokens, access tokens, API keys, or session cookies.
6. **Avoid carrying display data:** Email, display name, avatar, and phone number can be loaded from a service when needed.
7. **Keep permissions consistent:** `GrantedAuthority` normally lives on `Authentication`; no need to duplicate the role list inside the principal.

### 3.1. Decision Table

| Field | Suitability | Reason |
| --- | --- | --- |
| Internal `userId` | Usually recommended | Stable identifier, convenient for ownership checks |
| Username | Depends on need | Can change and carries personal identity |
| Tenant ID | Depends on multi-tenant app | Must be verified alongside membership |
| Email, phone | Usually omit | Personal data, unnecessary on every request |
| Display name | Unnecessary for auth | Can change; load when displaying |
| Plaintext password | Strictly never | Direct secret |
| Password hash | No | Sensitive credential value |
| OTP secret, MFA recovery code | No | Could bypass verification steps |
| Access/refresh token | Not in a custom business principal | Bearer credentials need their own lifecycle |
| Full JPA `UserEntity` | Avoid | Risks data leakage and pulls in object graphs |
| Authorities | Usually on `Authentication` | Must come from a trusted source |
| `HttpServletRequest` | No | Not identity data, request-scoped lifecycle |

**UUIDs do not replace permission checks.** Even when a `userId` is hard to guess, someone knowing another user's ID must not read that user's resources. Authorization must check `ownerId`/`tenantId` and business permissions.

### 3.2. Designing a Principal with a Java Record

A compact structure can look like:

~~~java
public record AppPrincipal(java.util.UUID userId)
        implements java.security.Principal, java.io.Serializable {

    @Override
    public String getName() {
        return userId.toString();
    }
}
~~~

A Java 17 record provides immutable components and accessors. This structure **holds only `userId`**, with no hashes/tokens/PII. Implementing `Principal` lets `Authentication.getName()` reflect the ID instead of a custom object's `toString()`.

This is a **data-structure snippet**, not a complete Spring Boot app; the practical section below includes a runnable Java file inside a Boot project.

If `userId` still identifies an individual, it may be treated as personal-linked data. Only return the ID in APIs or logs when needed and permitted by policy.

## 4. Separating Password Lifecycle from Principal Lifecycle

Desired flow:

~~~text
HTTP request: username + raw password
            |
            v
Authentication filter
            |
            v
AuthenticationManager / ProviderManager
            |
            v
AuthenticationProvider
    |-- UserDetailsService loads UserDetails and password hash
    |-- PasswordEncoder.matches(raw, hash)
    |-- checks account status, source ID, authorities
            |
            v
Authenticated Authentication
    |-- principal = AppPrincipal(internal userId)
    |-- credentials = null
    |-- authorities = trusted source
            |
            v
Request's SecurityContext
            |
            v
Controller -> Service checks ownerId/role/tenant
            |
            v
Response DTO containing only allowed fields
~~~

Passwords may still exist briefly in Java `String`s, HTTP requests, or call stacks during authentication. Do not promise every secret vanishes immediately from the heap; the primary goal is **never deliberately putting them into long-lived objects, logs, JSON responses, sessions, or messages**.

## 5. Complete Example with a UUID-Only Principal

This example deliberately separates the password-checking stage from the resulting `Authentication` to highlight how a minimal principal is built. It uses an illustrative `AuthenticationProvider`. In production, **prefer `DaoAuthenticationProvider` and built-in mechanisms provided by Spring Security** for standard authentication needs; custom providers require thorough security testing.

### 5.1. Dependencies

Create a Spring Boot 3.3.x, Java 17+ project via Spring Initializr with Gradle Groovy DSL and the Gradle Wrapper. In **`build.gradle`** you need:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
~~~

This is the dependencies block for a Boot project with plugins already configured, not a standalone Gradle file.

### 5.2. Complete Java File

Create **`src/main/java/com/example/principal/PrincipalDemoApplication.java`**:

~~~java
package com.example.principal;

import java.io.Serializable;
import java.security.Principal;
import java.util.Map;
import java.util.UUID;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.AccountStatusUserDetailsChecker;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class PrincipalDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(PrincipalDemoApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("learn123"))
                .roles("USER")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("admin123"))
                .roles("ADMIN")
                .build()
        );
    }

    @Bean
    AuthenticationProvider compactProvider(
            UserDetailsService users, PasswordEncoder encoder) {
        return new CompactPrincipalProvider(users, encoder);
    }

    @Bean
    AuthenticationManager authenticationManager(
            AuthenticationProvider compactProvider) {
        return new ProviderManager(compactProvider);
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, AuthenticationManager manager) throws Exception {
        return http
            .authenticationManager(manager)
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/me").authenticated()
                .requestMatchers(HttpMethod.GET, "/admin").hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }
}

record CompactPrincipal(UUID userId)
        implements Principal, Serializable {

    @Override
    public String getName() {
        return userId.toString();
    }
}

final class CompactPrincipalProvider implements AuthenticationProvider {

    private static final Map<String, UUID> IDS = Map.of(
        "alice", UUID.fromString("00000000-0000-0000-0000-000000000101"),
        "admin", UUID.fromString("00000000-0000-0000-0000-000000000102")
    );

    private final UserDetailsService users;
    private final PasswordEncoder encoder;
    private final AccountStatusUserDetailsChecker checker =
        new AccountStatusUserDetailsChecker();

    CompactPrincipalProvider(UserDetailsService users,
            PasswordEncoder encoder) {
        this.users = users;
        this.encoder = encoder;
    }

    @Override
    public Authentication authenticate(Authentication request) {
        if (!(request.getCredentials() instanceof String password)) {
            throw new BadCredentialsException("Bad credentials");
        }

        UserDetails user;
        try {
            user = users.loadUserByUsername(request.getName());
        } catch (UsernameNotFoundException ex) {
            throw new BadCredentialsException("Bad credentials");
        }

        if (!encoder.matches(password, user.getPassword())) {
            throw new BadCredentialsException("Bad credentials");
        }

        checker.check(user);

        UUID id = IDS.get(user.getUsername());
        if (id == null) {
            throw new BadCredentialsException("Bad credentials");
        }

        return UsernamePasswordAuthenticationToken.authenticated(
            new CompactPrincipal(id),
            null,
            user.getAuthorities()
        );
    }

    @Override
    public boolean supports(Class<?> tokenType) {
        return UsernamePasswordAuthenticationToken.class
            .isAssignableFrom(tokenType);
    }
}

@RestController
class MeController {

    @GetMapping("/public")
    String publicEndpoint() {
        return "public OK";
    }

    @GetMapping("/me")
    Map<String, Object> me(
            @AuthenticationPrincipal(errorOnInvalidType = true)
            CompactPrincipal principal,
            Authentication authentication) {

        var roles = authentication.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .sorted()
            .toList();

        return Map.of(
            "userId", principal.userId().toString(),
            "authenticationName", authentication.getName(),
            "authorities", roles
        );
    }

    @GetMapping("/admin")
    String adminEndpoint() {
        return "admin OK";
    }
}
~~~

This is **one complete Java file inside a Spring Boot project**: the public class matches the filename, record/provider/Controller share the package, and the Controller is discovered by Spring Boot component scanning. The code uses Java records, pattern matching for `instanceof`, and `Stream.toList` available since Java 17.

**Bean breakdown:**

1. **`UserDetailsService`** creates two demo users with BCrypt-hashed passwords and USER/ADMIN roles.
2. **`CompactPrincipalProvider`** loads the user by the username received from `BasicAuthenticationFilter`, runs `PasswordEncoder.matches`, and checks account status.
3. The provider constructs an authenticated `Authentication` only after valid verification. It pulls the ID from the demo's trusted mapping, uses a UUID-only principal, and sets **`credentials=null`**.
4. **`ProviderManager`** delegates to the provider; **`HttpSecurity.authenticationManager`** binds the manager to the security chain.
5. **`SecurityFilterChain`** makes `GET /public` public, requires login on `GET /me`, requires `ROLE_ADMIN` on `GET /admin`; other URLs hit `denyAll`.
6. **`@AuthenticationPrincipal`** in the Controller extracts the exact `CompactPrincipal` type from `Authentication`; the Controller returns only three allowlisted fields.

**Demo limitations:** The `IDS` map and in-source passwords are for learning only. Production must fetch IDs from a database/IdP and protect credential stores. Custom providers must also address timing/user enumeration, anti-brute-force, MFA, event auditing, and credential lifecycle concerns. If a system only needs standard username/password login, use the battle-tested `DaoAuthenticationProvider`.

### 5.3. Why Does the Result Hold Neither Password Nor Hash?

In the provider:

~~~java
return UsernamePasswordAuthenticationToken.authenticated(
    new CompactPrincipal(id),
    null,
    user.getAuthorities()
);
~~~

**`principal`** holds only `userId`; **`credentials=null`**; **`authorities`** come from the trusted `UserDetails`. The `UserDetails` object carrying the hash for verification is never placed into the successful principal. Even when `Authentication` is saved in a session, the `CompactPrincipal` record carries no hash.

The hash bytes may still sit inside the user store for future logins; that matches the credential store's responsibility. Yet the hash **never needs to be copied into `SecurityContext`**. Do not claim every trace of the hash has been wiped everywhere in the JVM.

### 5.4. Why Must Account Status Be Checked?

The checker verifies `UserDetails` account status such as disabled/locked/expired. If a custom provider compares passwords while skipping account flags, a disabled user could still log in. That is why custom providers require security review and failure-path tests, not just happy paths.

The example throws `BadCredentialsException` for both non-existent usernames and wrong passwords so messages do not clearly reveal whether an account exists. Still, timing can differ; anti-enumeration, rate limiting, and telemetry must be designed specifically for production.

## 6. Running the Example and Reading Results

Run from the project directory containing the Gradle Wrapper:

~~~bash
./gradlew bootRun
~~~

On Windows PowerShell use **.\gradlew.bat bootRun**. Assuming the server runs on `localhost:8080`:

~~~bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/me
curl -i -u alice:wrong http://localhost:8080/me
curl -i -u alice:learn123 http://localhost:8080/me
curl -i -u alice:learn123 http://localhost:8080/admin
curl -i -u admin:admin123 http://localhost:8080/admin
~~~

In PowerShell, use **`curl.exe`** if `curl` is an alias. Hard-coded passwords in commands are for localhost only. HTTP Basic requires HTTPS on real networks; to keep passwords out of shell history, run **`curl -u alice URL`** and enter the password when prompted.

| Request | Expected HTTP status | Reason |
| --- | --- | --- |
| GET /public anonymous | **200** | permitAll |
| GET /me anonymous | **401** | Authentication required |
| GET /me alice + wrong password | **401** | Provider rejected |
| GET /me alice + right password | **200** | Authentication carries CompactPrincipal |
| GET /admin alice + right password | **403** | Lacks ROLE_ADMIN |
| GET /admin admin + right password | **200** | Has ROLE_ADMIN |

Expected response from `GET /me` for alice:

~~~json
{
  "userId": "00000000-0000-0000-0000-000000000101",
  "authenticationName": "00000000-0000-0000-0000-000000000101",
  "authorities": ["ROLE_USER"]
}
~~~

JSON key order may vary; assert field values rather than comparing raw text positions. The response **contains no password, password hash, token, email, or `UserDetails`**.

These statuses/JSON are **expected based on the code**, not output measured from running a build inside this document. Actual responses may vary depending on `SecurityFilterChain`, proxies, or exception handling.

### 6.1. Tests Stronger Than String Searching

Inspect the **response schema**, actual principal type, and storage/logging locations. A response lacking the raw test password does not prove safety if it leaks hashes or sensitive data in another form.

## 7. Do Real Applications Need a Custom AuthenticationProvider?

**Not necessarily.** For standard username/password, Spring Security provides **`DaoAuthenticationProvider`**, `UserDetailsService`, and `PasswordEncoder`; these are usually a better choice than writing custom credential-checking logic.

If a standard provider returns `UserDetails` as the principal:

- Never return `Authentication` or `UserDetails` from Controllers.
- Use `@AuthenticationPrincipal` to read only needed fields and map into an allowlisted response DTO.
- Keep `UserDetails` separate from bulky JPA `UserEntity` classes.
- Audit what `SecurityContext`/sessions actually store and whether it can be trimmed further.
- When an internal ID is needed, map the verified username to the ID from a trusted source.

A custom provider creating a minimal principal like the demo should only be used when clearly justified and thoroughly tested for authentication correctness, account status, auth events, rollback/revocation, and error handling.

**Never trade a well-tested standard provider for a sleek principal by skipping mandatory verification steps.**

## 8. Do CredentialsContainer and ProviderManager Solve Everything?

Spring Security provides the **`CredentialsContainer`** interface allowing secret-holding objects to implement **`eraseCredentials()`**. `ProviderManager` by default tries to erase credentials on the returned `Authentication` after authentication if it supports this interface.

Points to understand:

- Erasure only affects objects designed to participate in that contract; it does not automatically wipe copies in requests, Java `String`s, thread dumps, heap, or logs.
- If `Authentication.getPrincipal()` is a `UserDetails` supporting erasure, the password inside the principal may be cleared upon success.
- Do not rely on post-login erasure to justify keeping hashes in returned payloads or logs.
- A custom `Authentication` holding secrets in custom fields needs explicit credential cleanup; better yet, **never place secrets in the success token**.
- Risk arises if a `UserDetails` cache shares the exact object reference with an erased principal: the cached password can be wiped too, breaking subsequent authentications.

**Best practice:** Separate the credential cache source from principal and response objects. Never disable `eraseCredentialsAfterAuthentication` casually just to dodge a cache bug; fix the reference/lifecycle design first.

## 9. Principals with Sessions, Stateless APIs, JWT, and OIDC

### 9.1. Session-Based Authentication

When using sessions/cookies, `SecurityContext` can be stored and restored via `SecurityContextRepository`. Large principals bloat sessions, increase session-store and serialization overhead, create risks during debugging, and couple to entities/JPA proxies.

An ID-only principal shrinks the stored surface area. Yet it **does not guarantee session safety on its own**; you still need `Secure`/`HttpOnly`/`SameSite` cookies, TLS, session fixation protection, timeouts, logout, and session revocation.

### 9.2. Stateless Authentication

With stateless/Bearer token APIs, `Authentication` may be constructed fresh per request. A compact principal still helps reduce data flowing across filters, business code, and logs. However, the token and claims may still reside inside the Resource Server's `Authentication` implementation.

**Stateless does not mean secrets need no protection.** A leaked Bearer token can be used as a credential until it expires or is revoked.

### 9.3. JWT

In an OAuth2 Resource Server, `Authentication` may be a `JwtAuthenticationToken` with a `Jwt` principal; `Jwt` can hold claims and the token value. Never serialize or log the raw `Jwt`/`JwtAuthenticationToken`.

**Standard signed JWTs do not encrypt their payload.** Claims can be decoded by anyone holding the token. Therefore never put passwords/hashes, refresh tokens, trade secrets, detailed personal profiles, or unnecessary data into claims. Only consume identifiers/authorities from a JWT after verifying signature, issuer, audience, expiry, and applicable conditions.

A service needing a compact internal principal can map the verified **`sub`** to an internal `userId`. Never trust a client-supplied `sub` string in a header.

### 9.4. OIDC/OAuth2 Login

OIDC principals are usually `OidcUser` or `OAuth2User` with attributes/claims that may include email, name, or protocol tokens. These must not be exposed indiscriminately to every Controller or client.

Map from the external identity to an internal `userId` and consume only required claims. When supporting multiple identity providers, link identities by **`issuer + subject`**, since a `sub` string may not be unique across issuers.

### 9.5. Multi-Tenant

If an application needs `tenantId` in the principal, retain it only after membership/tenant access has been verified. An `X-Tenant-Id` header or query parameter sent by a client does not prove the user belongs to that tenant. Access checks must evaluate `userId`, `tenantId`, `ownerId`, and the business action together.

## 10. Never Return the Raw Principal or Authentication Object

This is an anti-pattern:

~~~java
@GetMapping("/me")
Object unsafe(Authentication authentication) {
    return authentication;
}
~~~

Depending on the implementation, Jackson may serialize principal, credentials, details, authorities, or other properties. Library upgrades can alter JSON structure and accidentally leak data.

Return a **field-selected DTO**:

~~~java
record MyIdentityDto(String userId) {}

@GetMapping("/me")
MyIdentityDto safe(
        @AuthenticationPrincipal CompactPrincipal principal) {
    return new MyIdentityDto(principal.userId().toString());
}
~~~

This is a snippet inside a Controller requiring appropriate imports and record declarations; the complete code in section 5 illustrated a similar policy using `Map`.

Likewise, never place an entire `UserEntity` (with `passwordHash`, phone, address, JPA relations) into the principal. When a Controller needs profile data, call a service with the internal `userId` to fetch only permitted fields and verify permissions.

### 10.1. Logs Also Leak Data

- Never log raw passwords, `Authorization` headers, refresh/access tokens, JWTs, cookies, or password hashes.
- Avoid logging whole `Authentication`, `UserDetails`, `OidcUser`, `Jwt`, or JPA `UserEntity` objects without knowing what their `toString()` outputs.
- Default Java records generate a `toString` showing every component; a record containing a secret is not automatically safe.
- Lombok `@Data`/`@ToString` can generate `toString` output containing passwords/hashes.
- MDC/tracing should retain only correlation IDs or a minimal `userId` if policy allows—never scatter emails/phones/tokens.
- Exceptions and debug dumps must also be audited, not just API responses.

`userId` is an identifier linkable to a real person; logging policies still need access restrictions and retention limits.

## 11. Roles and Account Status Can Change

`Authentication` usually holds authorities captured at authentication time. If an admin revokes a role or locks an account, an existing session may keep using old authorities until refreshed, expired, or revoked.

That is a **permission lifecycle** issue, independent of whether the principal is compact. Clarify:

1. Which permissions are stored inside sessions or tokens?
2. When roles change, when is a fresh `Authentication` built?
3. When an account is locked or logged out across all devices, how are old sessions invalidated?
4. If tokens have long lifetimes, how is the impact of stale permissions bounded?
5. Are `ownerId`/`tenantId` policies checked on every sensitive request?

A UUID principal identifies the user, yet does not replace current authorization data. A user with `ROLE_USER` must still be denied if they try to edit an order they do not own.

## 12. Common Mistakes and Fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Principal holds entire `UserEntity` | Hashes/PII/lazy relations leak to context/logs | Minimal ID projection |
| Principal holds plaintext password | Secrets persist too long | Use password only at authentication |
| Principal holds password hash | Sensitive credential spreads | Separate credential store |
| Principal holds refresh token | Can be abused to mint new access | Manage tokens via dedicated mechanism |
| `UserDetails` returned directly from API | Can expose `getPassword` and account flags | Allowlisted response DTO |
| `Authentication` returned as JSON | Serializes details/credentials per implementation | Return only client-needed data |
| Role taken from request body | Self-privilege escalation | Assign authorities from trusted source |
| Creating authenticated token unverified | Authentication bypass | Providers must verify credentials |
| Custom provider skips account status | Locked users can still log in | Use standard provider or status checker |
| Disabling credential erasure to fix cache | Keeps secrets longer | Separate objects/caches |
| Not refreshing roles after revocation | Old permissions linger in session | TTL, revocation, re-checks |
| Logging full JWT | Exposes bearer tokens/claims | Redaction and minimal logging |
| Returning all OIDC claims | Leaks PII and token metadata | Map only required claims |
| Relying on hard-to-guess UUIDs | IDOR/BOLA | Check `ownerId`/permissions |
| Principal holds `HttpServletRequest` | Lifecycle mismatch, hard to serialize | Hold identity data only |

## 13. Minimum Required Tests

### 13.1. Principal Structure

- Verify `CompactPrincipal` holds only **UUID `userId`** and `getName` returns the ID.
- No `password`, `passwordHash`, `token`, `email`, `phone`, or `User` entity fields.
- Business code cannot mutate the ID after authentication.
- Principal holds no services or complex stateful objects.

### 13.2. Authentication Phase

- Valid username/password → returns authenticated `Authentication` with `CompactPrincipal`, `credentials=null`, trusted roles.
- Wrong password → `AuthenticationException`, no success token returned.
- Non-existent username → not authenticated.
- Disabled/locked/expired account → not authenticated.
- No way to inject arbitrary roles/IDs in requests to bypass the provider.

### 13.3. API and Logs

- `GET /me` returns only the allowed schema, never raw `UserDetails` or `Authentication`.
- `SecurityContext`/sessions/caches retain nothing beyond the designed fields.
- Logs, error responses, and tracing record no secrets.
- JWT/OIDC paths never return raw claims/tokens.
- Business authorization rejects access to records owned by others.

Do not just grep JSON for the raw test password and declare it safe: secrets can appear as hashes, tokens, or object metadata.

## 14. Self-Check Questions

**Question 1.** Since a password hash is already hashed, is it fine to store it in the principal?  
**Answer:** No. A hash is still a sensitive credential and is unnecessary for business logic after authentication.

**Question 2.** Is `Authentication.getPrincipal()` always `UserDetails`?  
**Answer:** No. Depending on the authentication mechanism, it can be a `String`, `UserDetails`, `Jwt`, `OidcUser`, or a custom principal.

**Question 3.** Why use `record CompactPrincipal(UUID userId)`?  
**Answer:** It holds only the verified ID, is immutable, and avoids carrying full account data.

**Question 4.** Does `ProviderManager.eraseCredentials` wipe every copy of the raw password from the JVM?  
**Answer:** No. It applies only to objects supporting the erasure contract; requests, caches, logs, and heap require separate care.

**Question 5.** Why must `PasswordEncoder.matches` be called before constructing an authenticated `Authentication`?  
**Answer:** Credentials must be verified; otherwise clients can spoof identities.

**Question 6.** Why not return the raw `Authentication` from `/me`?  
**Answer:** It may contain sensitive details/credentials/principals and its structure can change across library versions.

**Question 7.** Does a signed JWT guarantee its claims are secret?  
**Answer:** No. Signatures protect integrity, while standard JWT payloads remain readable.

**Question 8.** Does a UUID `userId` make `ownerId` checks unnecessary?  
**Answer:** No. An ID does not replace authorization.

**Question 9.** Role `USER` is revoked while a session has not yet expired; what must be done?  
**Answer:** Have a refresh/revocation policy or check current permissions so old authorities do not persist indefinitely.

**Question 10.** Why do both OIDC issuer and subject matter?  
**Answer:** Subjects must be scoped by issuer when mapping identities across multiple providers.

## 15. Official References

- Spring Security — Servlet Authentication Architecture: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security — Authentication API 6.3.4: https://docs.spring.io/spring-security/site/docs/6.3.4/api/org/springframework/security/core/Authentication.html
- Spring Security — CredentialsContainer: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/credentials-container.html
- Spring Security — MVC Integration and @AuthenticationPrincipal: https://docs.spring.io/spring-security/reference/servlet/integrations/mvc.html
- Spring Security — Username/Password: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/index.html
- Spring Security — Password Storage: https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html
- Spring Security — JWT Resource Server: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
- Spring Security — OAuth2 Login: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html
