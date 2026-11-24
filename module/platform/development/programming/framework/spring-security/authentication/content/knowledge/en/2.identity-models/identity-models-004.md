# GrantedAuthority: Authorities Loaded After Identity Verification

> **Topic:** Identity Models in Spring Security — how authorities are fetched from a trusted source, bound to `Authentication` after authentication, and used to make access decisions. This lesson focuses on the meaning, origin, lifecycle, and usage of `GrantedAuthority`; Java 17+ examples run on Spring Boot Servlet.

## 1. Why Is Identifying the Caller Not Enough?

Suppose an application exposes three APIs:

- `GET /me`: returns information about the currently logged-in account.
- `GET /reports`: reserved for users authorized to read reports.
- `GET /admin`: reserved for accounts with an administrative role.

When An enters valid login credentials, the system has **authenticated** An's identity. Yet from the fact "the caller is An", the application cannot automatically infer whether An can read reports or administer the system. The system needs a representation of the authorities **granted to that subject** and a policy matching authorities to actions.

In Spring Security, a standard representation is `GrantedAuthority`. Values such as `ROLE_ADMIN`, `report:read`, or `SCOPE_orders.read` become part of the trusted `Authentication` after proper authentication; they are read during **authorization**.

Consider three separate questions:

1. **Identity:** who is the subject? For example: account `an`, internal identifier `user-17`.
2. **Authentication:** what proof lets the server trust that the current request genuinely belongs to that account?
3. **Authorization:** which authorities have been granted, and which are required to perform an operation?

**There is no rule that "logging in successfully grants every permission."** Conversely, clients cannot pick their own roles by sending `?role=ADMIN` or `X-Role: ADMIN` and expecting the server to obey.

## 2. What Is `GrantedAuthority` Actually?

`GrantedAuthority` is a Spring Security interface declaring one method:

```java
package org.springframework.security.core;

public interface GrantedAuthority extends java.io.Serializable {
    String getAuthority();
}
```

This is an **API shape excerpt for explanation**, not a source file you create in your application. `getAuthority()` returns the string representing the authority; Spring Security commonly uses that string to match authorization rules. For example:

```text
ROLE_USER
ROLE_ADMIN
report:read
report:write
SCOPE_orders.read
```

`SimpleGrantedAuthority` is the simple, commonly used implementation:

```java
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

GrantedAuthority permission = new SimpleGrantedAuthority("report:read");
System.out.println(permission.getAuthority()); // report:read
```

The snippet above is an **illustrative code fragment** (requiring Spring Security dependencies inside a method or JShell), not a standalone Java program with `main`. `SimpleGrantedAuthority` simply wraps a string; the object itself **does not verify** passwords, identity, or resource access.

### What Does an Authority Represent?

| Example | Meaning defined by app/convention | How it is checked |
| --- | --- | --- |
| `ROLE_USER` | User holds role `USER` under the `ROLE_` convention | `hasRole("USER")` or `hasAuthority("ROLE_USER")` in default config |
| `ROLE_ADMIN` | Administrative role | `hasRole("ADMIN")` |
| `report:read` | Application permission to read reports | `hasAuthority("report:read")` |
| `invoice:approve` | Permission to approve invoices | `hasAuthority("invoice:approve")` |
| `SCOPE_orders.read` | OAuth2 scope mapped into an authority | `hasAuthority("SCOPE_orders.read")` |

An authority string **has no built-in magic**: `report:read` does not block any endpoint until the application configures a rule requiring that string. Nor does `ROLE_ADMIN` automatically imply `ROLE_USER` in every application; inheritance exists only if explicitly granted or configured via an appropriate role hierarchy.

For a complex `GrantedAuthority` that cannot be expressed faithfully as a single string, `getAuthority()` may return `null`; in that case, an authorization component that understands that special authority type is required. For most web applications, `SimpleGrantedAuthority` with clear names is easiest to manage.

### Where Does `Authentication` Hold Authorities?

After valid verification, Spring Security provides `Authentication` with these key members:

- `getPrincipal()`: who the represented subject is, such as a `UserDetails` or a `Jwt`.
- `getName()`: the subject's name per the implementation.
- `getAuthorities()`: `Collection<? extends GrantedAuthority>` of authorities bound to the authentication result.
- `getCredentials()`: associated proof, which may be erased after authentication.
- `isAuthenticated()`: status of the authentication token. Must distinguish anonymous tokens; checking this flag alone is insufficient to infer a logged-in user.

Thus, `Authentication` is not merely a username. It is the framework object carrying **identity + authentication status + granted authority set** to the access-decision step.

## 3. What Does "Authorities Loaded After Identity Verification" Mean in Practice?

Saying "authorities are loaded after identity verification" describes **the trust relationship and consumption**: first the system must establish a trusted identity; the authorities used in authorization must be bound to the corresponding verified result. However, **the database read order does not necessarily wait until password checking finishes before loading authorities**.

With username/password and `DaoAuthenticationProvider`, a typical flow is:

1. The client sends username/password; that data is still **untrusted**.
2. `AuthenticationManager` delegates the request to a supporting `AuthenticationProvider`.
3. `DaoAuthenticationProvider` uses `UserDetailsService.loadUserByUsername(...)` to load the account. `UserDetails` can **already contain authorities when loaded**, alongside the password hash and account flags.
4. The provider verifies the credential with `PasswordEncoder` and account status checks. On failure, **it must not issue** a successful login result carrying those loaded authorities.
5. On success, the provider returns an authenticated `Authentication` with the appropriate principal and authorities.
6. The framework makes this result available in the request's `SecurityContext` per its configuration.
7. `AuthorizationManager` or method security compares `Authentication.getAuthorities()` against policy to allow or deny access.

```text
Request: username/password (untrusted)
       |
       v
AuthenticationManager
       |
       v
DaoAuthenticationProvider
       |
       +--> UserDetailsService --> UserDetails
       |                          |-- username
       |                          |-- password hash
       |                          +-- authorities from a trusted source
       |
       +--> PasswordEncoder verifies credential
                |          |
             INVALID     VALID
                |          |
             Reject        v
                         Authenticated Authentication
                         + principal
                         + authorities
                                |
                                v
                         SecurityContext
                                |
                                v
                         AuthorizationManager
                         hasAuthority / hasRole
                                |
                           Allow / Deny
```

**Key point:** Querying authorities may happen before password checking as part of `loadUserByUsername`, yet those authorities **only count as the current caller's authorities once authentication completes validly**. Never fetch authorities for a self-asserted username and immediately use them to pass authorization.

### Where Can Authorities Come From?

- **Internal database:** role tables, permission tables, user–role / role–permission relations.
- **Directory/identity store:** groups or account attributes mapped to application authorities.
- **Verified access token:** trusted scopes/claims converted to authorities by a converter.
- **Trusted provider or service:** authorities returned by another identity/authorization system under an established contract and trust boundary.

`GrantedAuthority` is a **result representation**, not the primary data store. The application must define which authorities exist, who grants them, who revokes them, how they map, and what policies enforce them.

## 4. Are Role, Permission, and Scope the Same Thing?

These three concepts are related yet can carry distinct meanings in a business system.

- **Role:** a bundle of responsibilities, often represented with `ROLE_*` such as `ROLE_MANAGER`. A role may group multiple permissions.
- **Permission:** capability to perform an action such as `report:read`, `report:export`, or `invoice:approve`.
- **Scope:** boundary of rights granted to a client/token in an authorization protocol, commonly represented in Spring Resource Server as `SCOPE_*` under default settings.

Spring Security usually reads them all as **`GrantedAuthority` strings** during authorization checks. Expanding a role into multiple permissions **does not happen automatically** just because `ROLE_MANAGER` is in `Authentication`.

Example application policy:

| Account | Granted role/permission | Report access | Admin access |
| --- | --- | --- | --- |
| An | `ROLE_USER`, `report:read` | Yes | No |
| Binh | `ROLE_ADMIN` | No, if `report:read` is missing | Yes |
| Chi | `ROLE_ADMIN`, `report:read` | Yes | Yes |

The table above is an **illustrative policy**, not a Spring Security default rule. It intentionally shows that someone with role ADMIN cannot read reports if the endpoint specifically requires `report:read` and the system has not configured role inheritance or permission expansion.

### Distinguishing `hasAuthority` and `hasRole`

With the default `ROLE_` role prefix:

```java
.hasAuthority("report:read") // matches the exact string report:read
.hasAuthority("ROLE_ADMIN")  // matches the exact string ROLE_ADMIN
.hasRole("ADMIN")            // typically looks for ROLE_ADMIN
```

These lines are **illustrative DSL fragments** inside `HttpSecurity`, not a standalone Java program.

- `hasAuthority("ADMIN")` looks for the exact string `ADMIN`, **not** `ROLE_ADMIN`.
- `hasRole("ADMIN")` prepends the default role prefix; do not pass `ROLE_ADMIN` into `hasRole` under default configuration.
- If a project customizes `GrantedAuthorityDefaults`, `AuthorizationManagerFactory`, or its authorization setup, verify the actual convention and consistency between web security and method security.
- Authority strings are typically exact-matched; standardize casing, delimiters, domain names, and prefixes.

Do not mix naming styles (`READ_REPORT`, `report.read`, `report:read`) without an explicit mapping step.

## 5. Runnable Spring Boot Example: Same Identity Model, Different Authority Sets

The example below uses Java 17+, **Spring Boot Servlet** with the **Spring Web** and **Spring Security** starters. It defines two in-memory accounts to observe `Authentication.getAuthorities()` and how `hasRole`/`hasAuthority` enforce access. Use the Gradle/Maven wrapper from a Spring Initializr project; this is a learning environment—never use demo passwords in production.

Create `src/main/java/com/example/authoritydemo/AuthorityDemoApplication.java`:

```java
package com.example.authoritydemo;

import java.util.List;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class AuthorityDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthorityDemoApplication.class, args);
    }
}

@Configuration(proxyBeanMethods = false)
class DemoSecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder passwordEncoder) {
        UserDetails an = User.withUsername("an")
                .password(passwordEncoder.encode("demo-password"))
                .authorities("ROLE_USER", "report:read")
                .build();

        UserDetails binh = User.withUsername("binh")
                .password(passwordEncoder.encode("demo-password"))
                .authorities("ROLE_ADMIN")
                .build();

        return new InMemoryUserDetailsManager(an, binh);
    }

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers("/public/ping").permitAll()
                        .requestMatchers("/reports").hasAuthority("report:read")
                        .requestMatchers("/admin").hasRole("ADMIN")
                        .anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}

@RestController
class DemoController {

    @GetMapping("/public/ping")
    String ping() {
        return "pong";
    }

    @GetMapping("/me")
    String me(Authentication authentication) {
        List<String> names = authentication.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .sorted()
                .toList();
        return "principal=" + authentication.getName()
                + "; authorities=" + String.join(",", names);
    }

    @GetMapping("/reports")
    String reports() {
        return "report ok";
    }

    @GetMapping("/admin")
    String admin() {
        return "admin ok";
    }
}
```

Configuration explanation:

1. `UserDetailsService` holds two trusted server-defined profiles. Once loaded, `UserDetails` already carries the username, password hash, and authorities. In production, profiles typically come from a DB rather than memory.
2. `PasswordEncoder` uses BCrypt to generate/check hashes. Granted authorities **never replace** password verification.
3. `/me` requires authentication and returns the principal along with the authority list placed in `Authentication`. `sorted()` keeps output ordering stable.
4. `/reports` requires the exact authority `report:read`, while `/admin` requires role `ADMIN`, corresponding to `ROLE_ADMIN` by default.
5. With HTTP Basic, every request must send the appropriate credentials. With sessions or tokens, how `Authentication` is persisted or derived differs.

### Run and Observe

Run one of the following commands from the project root (depending on build tool):

```bash
./gradlew bootRun
# Or:
./mvnw spring-boot:run
```

On Windows PowerShell, run `.\gradlew.bat bootRun` or `.\mvnw.cmd spring-boot:run`. Do not invoke `javac` directly to compile a Spring Boot file because it needs dependencies supplied by the build tool.

In another terminal, use `curl` (on PowerShell you can use `curl.exe`):

```bash
curl -s http://localhost:8080/public/ping
curl -s -u an:demo-password http://localhost:8080/me
curl -s -u binh:demo-password http://localhost:8080/me
curl -s -u an:demo-password http://localhost:8080/reports
curl -s -u binh:demo-password http://localhost:8080/admin
curl -i http://localhost:8080/reports
curl -i -u an:demo-password http://localhost:8080/admin
curl -i -u binh:demo-password http://localhost:8080/reports
```

With the configuration and demo data above, the **response bodies** of the first five commands are, respectively:

```text
pong
principal=an; authorities=ROLE_USER,report:read
principal=binh; authorities=ROLE_ADMIN
report ok
admin ok
```

The last three commands return status codes under this HTTP Basic configuration: **401**, **403**, **403**. Error headers/bodies may vary by version and configuration, so do not assume a fixed error string. The two `/me` commands prove two principals were identified with different authority sets. The two 403 responses prove **valid login does not imply sufficient permissions**.

HTTP Basic sends username/password Base64-encoded, **not encrypted**. Only deploy in production over HTTPS; the demo uses localhost to observe mechanics.

### How Does Changing an Authority Affect Access?

If when creating `UserDetails` for Binh the server also grants `"report:read"`, a fresh authentication using the updated user record can produce an `Authentication` containing that authority; `GET /reports` will then be permitted under the current rule. Changing a `?role=...` query parameter has no effect because no step trusts the client to supply authorities.

Using `.roles("USER")` in `User.withUsername(...)` can be more convenient than `.authorities("ROLE_USER")`: the builder prepends `ROLE_` to roles. Avoid passing names that already have the prefix into `.roles(...)`. When both roles and custom-named permissions are needed, the example intentionally uses `.authorities(...)` to show the exact stored strings.

## 6. How Do Authorities Flow from the Database to `Authentication`?

In real applications, a common authority schema is:

```text
users
  id, username, password_hash, enabled
       |
       v
user_roles(user_id, role_id) --> roles(id, code)
                                     |
                                     v
                         role_permissions(role_id, permission_id)
                                     |
                                     v
                            permissions(id, code)
```

Suppose user `an` holds role `USER`, and that role grants permission `report:read`. When loading `UserDetails`, the service layer can:

- Find the user by username/email per internal rules.
- Load roles and permissions from a trusted source using an appropriate query/JPA/LDAP lookup.
- Verify account status, tenant scope, and granting policies.
- Normalize role `USER` into `ROLE_USER`, keeping permission `report:read` per convention.
- Deduplicate and return the `GrantedAuthority` collection inside `UserDetails`.

Below is an **illustrative mapping snippet**, assuming `roleCodes` and `permissionCodes` have already been loaded from a trusted source; it is not a standalone repository/service:

```java
import java.util.Collection;
import java.util.Set;
import java.util.TreeSet;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

static Collection<? extends GrantedAuthority> mapAuthorities(
        Set<String> roleCodes,
        Set<String> permissionCodes) {
    Set<String> names = new TreeSet<>();
    for (String role : roleCodes) {
        names.add("ROLE_" + role);
    }
    names.addAll(permissionCodes);
    return names.stream()
            .map(SimpleGrantedAuthority::new)
            .toList();
}
```

This code only illustrates converting **system-controlled authority names** into objects; it does not validate input data or replace business authorization checks. When authorities can originate from multiple roles, merging with deduplication avoids redundant entries.

Watch out for **default authorities**: an application must never grant `ROLE_ADMIN` or sensitive permissions simply because role rows are missing, loading failed, or no authorities were found. The safe policy is **never invent fallback authorities**; if required data is corrupt/missing, fail authentication/access according to the system's contract.

### Choosing Where to Map Authorities

- For username/password, `UserDetailsService` is normally where user-bound authorities are loaded; a custom `AuthenticationProvider` can build the result if the mechanism differs.
- For OAuth2/JWT, use an appropriate converter to map verified claims into authorities rather than pretending the JWT went through `UserDetailsService`.
- For external authority-lookup APIs, account for source trustworthiness, network failures, consistency, and cache lifetime before placing data into `Authentication`.

The mapping layer should have a clear owner. End-user authorities and client/service authorities can be distinct concepts; do not blindly turn a service scope into an end-user permission.

## 7. How Are Authorities Used to Make Access Decisions?

Once `Authentication` exists, Spring Security can protect resources at multiple layers.

### Request-Level Authorization

Example DSL in `SecurityFilterChain`:

```java
.authorizeHttpRequests(authorize -> authorize
        .requestMatchers("/reports/**").hasAuthority("report:read")
        .requestMatchers("/admin/**").hasRole("ADMIN")
        .anyRequest().authenticated())
```

Each rule applies to matching requests; ordering matchers explicitly prevents broad rules from shadowing specific ones. This is an **illustrative DSL fragment**, not a complete runnable configuration.

### Method-Level Authorization

With `@EnableMethodSecurity` and appropriate method security configuration, authorities can be enforced directly on services:

```java
@PreAuthorize("hasAuthority('report:read')")
public Report readReport(long reportId) {
    // Load the report and check other business conditions.
}
```

This is an **illustrative snippet**, requiring `Report`, an actual service, imports, and method-security configuration to compile. Placing checks on services is valuable when business methods are invoked from entry points beyond HTTP controllers.

### Broad Authorities Are Not Enough for Per-Object Permissions

Suppose An has `report:read` yet is only allowed to view reports belonging to An's department. A `hasAuthority("report:read")` check satisfies only the **coarse permission**, without ensuring `report.departmentId` matches an allowed department.

Business logic needs both:

```text
Allow reading report R if:
  (1) Authentication has authority "report:read"
  AND
  (2) Data policy confirms the subject may access R
      (ownerId, departmentId, tenantId, or equivalent policy)
```

Do not load tens of thousands of authorities like `report:501:read`, `report:502:read` just to model per-record ownership, because large lists consume memory, increase verification cost, and are hard to revoke. Use domain-object authorization, policy services, permission-filtered queries, or an architecture-appropriate mechanism.

### `Authentication.getAuthorities()` and Inconsistent Enforcement

Inspecting the authority collection only shows **what data was granted**; it does not prove all authorization paths are wired properly. Endpoints must actually have protective rules; method security must be enabled when used; object-level checks must be written. Having many authorities on a user does not mean they are checked automatically on every operation.

## 8. Login Sessions, Tokens, and Authority Changes

This is a major source of bugs: **changing authorities in the underlying data store does not mean every existing `Authentication` changes immediately**.

### Session-Based Login

After login, `Authentication` may be saved inside `SecurityContext` tied to an HTTP session, depending on `SecurityContextRepository` configuration. If An's authorities change in the DB while the session still holds the earlier set, subsequent requests may keep using the old authorities until the session/context is refreshed, expires, or the user logs in again.

Common options depending on requirements:

- Shorter sessions or forced re-login after sensitive changes.
- Actively invalidating/revoking affected sessions.
- Updating or checking an authority version when handling requests.
- Checking live permissions in a policy/domain service for sensitive actions.

No single authority-refresh strategy fits every system by default.

### HTTP Basic

When every request carries username/password and the app re-authenticates through a provider, authority loading may occur on each authentication. Still, caches, repositories, and specific architectures can prevent instant updates. Do not treat Basic as a guarantee of real-time DB synchronization.

### JWT Bearer Tokens

In Spring Security OAuth2 Resource Server, a typical flow is:

1. Receive a bearer token presented by the client.
2. Verify the JWT with `JwtDecoder`, including signature and configured validation rules (e.g., issuer, expiration; audience validation must be configured appropriately for the API).
3. `JwtAuthenticationConverter` builds `Authentication` and maps trusted scopes/claims to authorities.
4. Authorization consumes the resulting authorities.

Under default conventions, a JWT with claims:

```json
{
  "sub": "user-17",
  "scope": "orders.read orders.write"
}
```

commonly maps those two scopes to:

```text
SCOPE_orders.read
SCOPE_orders.write
```

This is an **illustrative claim payload**, not a complete JWT or signed proof. Never read `scope` from client-submitted JSON to construct a trusted `Authentication`. For a `roles` claim or custom claim names, configure an appropriate converter; **you do not automatically get `ROLE_ADMIN` merely because a token contains `"roles": ["ADMIN"]`** unless a converter is configured to read and map it.

If a token is self-contained and long-lived, revoking a permission in the DB does not strip claims from already-issued tokens. You need TTLs, revocation/rotation strategies, introspection, or supplemental checks matching business risk.

### Opaque Tokens and OIDC

- **Opaque tokens:** a trusted introspection/verification source typically determines whether the token is valid and returns scopes/authorities, which are then mapped into `Authentication`.
- **OIDC login:** identity from the Identity Provider and application permissions are two distinct concepts. The ID token answers the login outcome and identity claims; access tokens, UserInfo, and internal stores serve different purposes. Never use an arbitrary claim from an ID token to grant admin privileges without a clear trust/mapping contract.

## 9. Common Mistakes When Loading and Using `GrantedAuthority`

| Mistake | Why it is wrong | How to fix |
| --- | --- | --- |
| Reading `role` from query, body, or client header and creating `SimpleGrantedAuthority` | Caller escalates their own privileges | Map only from a verified source |
| Treating loading `UserDetails` as being logged in | Finding an account does not prove valid credentials | Let `AuthenticationProvider` verify and produce the result |
| Storing `ADMIN` yet calling `hasRole("ADMIN")` with default prefix | The rule checks for `ROLE_ADMIN` | Align authority naming or prefix/mapping |
| Token has scopes while rule demands roles | `SCOPE_orders.read` is not `ROLE_USER` | Design clear mappings and match rule types to authority types |
| Granting `ADMIN` role and assuming all permissions follow | No implicit permission inheritance | Grant explicit permissions or configure role hierarchy/policy |
| Updating DB authorities and assuming old sessions update | Context stores a snapshot of authorities | Design session refresh/revocation or live permission checks |
| Trusting a JWT because Base64URL decodes | Decoding does not verify signature, issuer, expiry, or audience | Use properly configured resource server/decoder and validators |
| Protecting sensitive data APIs with only `authenticated()` | Authentication does not indicate which actions are permitted | Add authority-based and object-level authorization |
| Checking only `isAuthenticated()` | Anonymous authentication can carry that flag | Use Spring Security trust/authorization mechanisms |
| Logging full `Authentication` or tokens | May leak credentials/PII/sensitive claims | Log minimally, redact secrets, restrict log access |

Another mistake is calling `getAuthorities()` on a potentially `null` `Authentication` on public endpoints while assuming a real user is always present. For public endpoints, handle anonymous/unauthenticated states properly or use appropriate injection/authorization; never pull identity from `SecurityContextHolder` without validating context state.

## 10. Design and Testing Checklist

When building a new feature, identify **the authority source**, **the mapping path**, and **where policies are enforced**:

1. List required atomic authorities (e.g., `report:read`, `report:write`), naming conventions, and administrative/granting roles.
2. Specify the source of truth: internal DB, IdP, access token claims, policy service, or a combined source.
3. Document how source data maps into `GrantedAuthority`, handling duplicates, revoked rights, disabled accounts, and authority-source failures.
4. Verify that only a successful `Authentication` result is treated as the caller's identity/authorities.
5. Apply `hasAuthority`/`hasRole` rules at appropriate endpoints or methods; add object/tenant checks where required.
6. Choose how authority updates/revocations propagate to active sessions, caches, and valid tokens.
7. Test permitted cases, missing authority, wrong credentials, unauthenticated requests, wrong role prefix, revoked authorities, and accessing another user's resources.
8. Ensure logs and data endpoints do not expose credentials, tokens, or unnecessary sensitive permission details.

### Self-Check Questions

**Question 1.** `loadUserByUsername("an")` returns a `UserDetails` with `ROLE_ADMIN`. Does a request carrying username `"an"` already have admin rights?  
**Answer:** No. Credentials must be verified and a trusted `Authentication` produced; loading a profile/authorities does not authenticate the caller.

**Question 2.** Under default configuration, a user has `ROLE_MANAGER` while the endpoint requires `hasAuthority("MANAGER")`. Will access succeed?  
**Answer:** No. The strings do not match; to check the role, use `hasRole("MANAGER")` or `hasAuthority("ROLE_MANAGER")`.

**Question 3.** A valid token has `scope = "orders.read"`. Why might a `hasAuthority("orders.read")` rule reject it?  
**Answer:** Resource Server by default usually maps it to `SCOPE_orders.read`. Use the actual authority string or customize the converter.

**Question 4.** An is authenticated and holds `report:read`, yet tries to read a report from another tenant. Is access guaranteed to be allowed?  
**Answer:** No. Object/tenant scope checks are required in addition to coarse authorities.

**Question 5.** After revoking `ROLE_ADMIN` in the DB, an old session remains open. Can we assume the authority vanishes on the next request?  
**Answer:** No. Check how `Authentication` is stored/restored and design a refresh, revocation, or live authority-checking mechanism.

## Conclusion

`GrantedAuthority` represents **the authorities granted to a principal** in a form Spring Security can evaluate when making access decisions. For username/password, authorities are commonly loaded alongside `UserDetails` during authentication and bound to the successful `Authentication`; for JWT/opaque tokens or other mechanisms, they are mapped from **verified** proof. `SecurityContext` supplies that result to the request, while `AuthorizationManager` or method/domain security decides whether the action is permitted.

**Identifying the subject is only the first condition; loading the right authorities from a trusted source and enforcing policies in the right places is what makes access control complete.**

### Official References

- [Spring Security — Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security — Authorization Architecture / Authorities](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html)
- [Spring Security — Username/Password Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/index.html)
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)