# Meaning of getName, getPrincipal, getCredentials, and getAuthorities in Spring Security

> **Scope:** the **Spring Security Authentication** identity model on Java 17+, focusing on the `org.springframework.security.core.Authentication` API. This lesson explains the exact role of the four methods, the difference between an authentication request and an authenticated result, how to read them in Spring MVC applications, exceptions by login mechanism, and security risks. It includes a standalone runnable Java example with the Spring Security 6.3.x dependency. The focus is **understanding identity data**, not designing full authorization rules or a new OAuth2 system.

## 1. The Big Picture: Four Distinct Questions

In Spring Security, `Authentication` represents either **an authentication request** sent to `AuthenticationManager` or **the authentication result** of a current identity. That object is typically placed into `SecurityContext` after successful login.

```text
SecurityContextHolder
    └── SecurityContext
         └── Authentication
              ├── getName()        -> name representing the identity
              ├── getPrincipal()   -> object representing the identity
              ├── getCredentials() -> authentication proof (may be erased)
              ├── getAuthorities() -> granted permissions/roles/scopes
              ├── isAuthenticated() -> trust state of the token
              └── getDetails()     -> auxiliary details of the authentication (if any)
```

The four main methods are **not synonymous and not interchangeable**:

| Method | Java return type | Question answered | Common examples |
| --- | --- | --- | --- |
| `getName()` | `String` | What name is this identity referred to by? | `mai`, a subject ID |
| `getPrincipal()` | `Object` | Who or what is represented by this token? | `String` username, `UserDetails`, `Jwt`, `OidcUser` |
| `getCredentials()` | `Object` | What proof was presented to prove the identity? | Password, secret/token, or `null` |
| `getAuthorities()` | `Collection<? extends GrantedAuthority>` | Which permissions/roles/scopes are bound to the authenticated identity? | `ROLE_USER`, `ROLE_ADMIN`, `SCOPE_profile` |

Common pitfall: **`getName()` is an identifier string**, **`getPrincipal()` can be an attribute-rich object**, **`getCredentials()` is sensitive data**, and **`getAuthorities()` is used for access decisions**. You cannot derive a password from a name, you cannot infer permissions solely from a username, and you should not infer an internal user merely from an arbitrary field on an external provider's principal.

### Authentication Has Two Different Semantic States

```text
User enters username/password
    ↓
Authentication request
    principal   = "mai"          (String)
    credentials = submitted password
    authorities = []             (no trusted authorities granted yet)
    authenticated = false
    ↓
AuthenticationManager -> AuthenticationProvider -> verifies credentials
    ↓
Successful Authentication result
    principal   = UserDetails(...) or provider-specific type
    credentials = usually erased (null)
    authorities = [ROLE_LEARNER] (data granted by trusted system)
    authenticated = true
    ↓
SecurityContext (and request context storage/restoration mechanisms)
```

**Same interface, yet the data before and after authentication can differ in both type and value.** Never cast the result based on an example from a single provider.

## 2. getName(): Identity Name for Display or Conditional Lookup

Signature:

```java
String name = authentication.getName();
```

`Authentication` **extends `java.security.Principal`**; `getName()` comes from the `Principal` contract. For common implementations extending `AbstractAuthenticationToken`, the name is derived from the principal: for instance `UserDetails.getUsername()`, `AuthenticatedPrincipal.getName()`, `Principal.getName()`, or an appropriate string representation of the principal. Consequently, the result **depends on the `Authentication` type and principal type**.

Examples:

- Username/password login with a `UserDetails` named `mai`: `getName()` typically returns `mai`.
- OAuth2/OIDC Login: the name may be derived from an attribute/claim configured for the principal, not necessarily matching a username in the internal DB.
- JWT Resource Server: `JwtAuthenticationToken` usually uses subject (`sub`) as its default name, though mapping can be customized.
- An anonymous token can have the name `anonymousUser`; that is **not** a sign that a real user has logged in.

**Proper use:** displaying an identity code/name accepted by the backend, used when the system has precisely defined the meaning and uniqueness of that name. **Never use it by default as a global user key** across all scenarios. With OIDC, durable external identity mapping usually binds to the **issuer + subject (`iss` + `sub`)** pair; emails and display names can change, collide, or be unverified. In multi-tenant systems, include tenant boundaries in identity rules.

**Do not infer:** `getName()` does not provide a password, phone number, access permissions, or proof that a user has logged in. Nor should you assume it always equals `((UserDetails) getPrincipal()).getUsername()`, because the principal might not be a `UserDetails`.

## 3. getPrincipal(): The Object Representing the Authenticated Person or Entity

Signature:

```java
Object principal = authentication.getPrincipal();
```

`principal` is the general concept for the *identified subject*. The API declares `Object` to support multiple information structures and authentication mechanisms.

### Before and After Username/Password Authentication

- **Input:** `UsernamePasswordAuthenticationToken.unauthenticated("mai", "secret")` has the string `"mai"` as its principal.
- **Result:** `DaoAuthenticationProvider` normally returns an `Authentication` whose principal is a `UserDetails` object holding username, authorities, and account status flags (unless configured to return a String principal).
- **Valid exception:** an application may use a custom principal like `CurrentUser` holding internal user ID, tenant ID, or other needed details; it does not have to be a JPA entity.

### When Integrating Other Mechanisms

| Form | Common principal example | Caution needed |
| --- | --- | --- |
| Username/password before auth | `String` | Only a claimed name, not yet trusted |
| Username/password succeeded | `UserDetails` or custom user | May carry password hash/sensitive status |
| JWT Resource Server | `Jwt` | Verified by the configured provider, yet claims must still be interpreted by issuer/audience and business logic |
| OAuth2 Login | `OAuth2User` | User attributes depend on provider/registration |
| OIDC Login | `OidcUser` | `sub`, issuer, claims; avoid mistaking email for a unique ID |
| Anonymous Authentication | Usually the string `anonymousUser` | Not an authenticated end-user in business terms |

When you need specialized type access, check with **`instanceof`**, never cast unconditionally:

```java
Object principal = authentication.getPrincipal();

if (principal instanceof UserDetails userDetails) {
    String username = userDetails.getUsername();
    // Safe when principal is actually a UserDetails.
} else {
    String name = authentication.getName();
    // Handle other principal types per the configured mechanism.
}
```

The snippet above is **illustrative inside a method that already has an `authentication` variable**, not a standalone runnable Java class. In production code, if the application standardizes on a specific custom principal, abstract the conversion from external identity to internal user ID in the login or identity-mapping layer. Avoid making every controller/service guess every provider type.

**Never return `authentication.getPrincipal()` directly from a REST API.** The principal may contain password hashes, emails, token claims, internal attributes, or object graphs not meant for clients. Build a DTO containing only fields explicitly permitted for exposure.

## 4. getCredentials(): Authentication Proof, Not a User Profile

Signature:

```java
Object credentials = authentication.getCredentials();
```

Credentials are the data proving that the principal is entitled to claim an identity. In a username/password flow, the value is usually the password **just submitted by the client**. In other mechanisms it may be a token, secret, or provider-specific data. The `Object` type reflects this variety; **never assume it casts to `String`**.

### Safe Lifecycle

1. The initial request can hold the raw password so `AuthenticationProvider` can verify it against the password hash loaded from the user store.
2. Upon successful authentication, `ProviderManager` by default erases credentials from the result if the result supports `CredentialsContainer`; standard token classes typically implement this. `getCredentials()` after login may therefore **return `null`**.
3. With a custom `AuthenticationManager`, custom token, or different provider, erasure depends on the implementation. Never assume **every** token has been erased.
4. If principal/details also contain an object supporting `CredentialsContainer`, erasure can affect that object too; user cache and shared-object designs must avoid retaining/re-serving a mutable instance whose credentials were wiped.

**Strictly avoid:**

```java
// WRONG: never put credentials into responses, logs, or metrics.
return authentication.getCredentials();

// WRONG: cannot use getCredentials() after login to "recover the password".
String password = (String) authentication.getCredentials();
```

The snippets above are **anti-patterns to avoid**, not implementation advice. Never print the full `Authentication`/principal to logs in real environments because implementations or custom `toString()` methods may expose sensitive data; proper redaction is required. Never save the raw password into `SecurityContext`/HTTP session for later use. If a password change is needed, re-authenticate/design a dedicated flow per policy.

**Distinguish three concepts:**

- `getCredentials()`: proof submitted by the client in an authentication step; may be erased.
- `UserDetails.getPassword()`: normally the **stored password hash**, used for `PasswordEncoder.matches(...)`; not the raw password and also potentially affected by credential erasure.
- `getDetails()`: auxiliary request details (e.g., remote address metadata or session ID depending on configuration). This is a **different** method from `getCredentials()` and must not be treated as proof of identity.

## 5. getAuthorities(): Permissions Granted to the Principal

Signature:

```java
Collection<? extends GrantedAuthority> authorities =
        authentication.getAuthorities();
```

`GrantedAuthority` represents **an application-level authority**. It has `getAuthority()` returning the authority name as a `String` (some complex authorities cannot be represented as strings and return `null`). The `Authentication#getAuthorities()` contract returns a collection, **never `null`**; before a token is authenticated, the collection may be empty.

Examples:

- `ROLE_USER`, `ROLE_ADMIN`, `ROLE_LEARNER`: common role forms.
- `SCOPE_profile`, `SCOPE_orders.read`: common scope mappings in OAuth2 Resource Server; depends on converter/configuration.
- `orders:read`: application-specific authority, requiring consistent conventions and checks.

Role of authorities in the flow:

```text
AuthenticationProvider / trusted identity source
    ↓ assigns authorities after authentication
Authentication.getAuthorities()
    ↓
AuthorizationManager / @PreAuthorize / request authorization rules
    ↓
Allow or deny the operation
```

**Authorities are not synonymous with authentication:** an account can be authenticated while its authorities collection is empty; requests can still be denied if an authority is required. Conversely, an authority list sent by the client in a login request does not become trusted permissions. The system must grant/map authorities from a verified source.

### hasRole and hasAuthority

In Spring Security, `hasRole("ADMIN")` under default configuration checks for authority `ROLE_ADMIN`; `hasAuthority("ROLE_ADMIN")` matches that exact string. Keep the distinction clear:

```java
// Illustrates configuring several request authorization rules:
.requestMatchers("/admin/**").hasRole("ADMIN")
.requestMatchers("/reports/**").hasAuthority("reports:read")
```

These are **lines inside `authorizeHttpRequests` configuration**, not a standalone Java program. The role prefix can be customized; do not blindly add or strip `ROLE_` if the application already has its own convention. Per-record authorization (such as reading only orders belonging to one's own tenant) normally requires checking business context; a global authority alone cannot decide per-object access.

### Reading Authorities Safely

```java
List<String> names = authentication.getAuthorities().stream()
        .map(GrantedAuthority::getAuthority)
        .filter(Objects::nonNull)
        .sorted()
        .toList();
```

This snippet requires importing `java.util.List`, `java.util.Objects`, and `GrantedAuthority`, and assumes an `authentication` variable exists. `filter(Objects::nonNull)` proactively excludes complex authority types that provide no string name. If a system uses such types, the corresponding authorization component must understand their representation directly.

## 6. Runnable Java 17+ Demo: Observing All Four Fields Before and After Real Authentication

The example below runs **without a web server**. It sets up an in-memory account, uses `PasswordEncoder` to create a password hash, lets `DaoAuthenticationProvider` genuinely verify the credential, and uses `ProviderManager` to return the result. The goal is to see **why the getters change before and after authentication**. Demo data is not for production.

Directory structure:

```text
auth-fields-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/AuthFieldsDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'auth-fields-demo'
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
    implementation 'org.springframework.security:spring-security-core:6.3.10'
}

application {
    mainClass = 'demo.AuthFieldsDemo'
}
```

`src/main/java/demo/AuthFieldsDemo.java`:

```java
package demo;

import java.util.Objects;
import java.util.stream.Collectors;

import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;

public class AuthFieldsDemo {
    public static void main(String[] args) {
        PasswordEncoder encoder =
                PasswordEncoderFactories.createDelegatingPasswordEncoder();

        UserDetails account = User.withUsername("mai")
                .password(encoder.encode("demo-password"))
                .roles("LEARNER")
                .build();

        UserDetailsService users = new InMemoryUserDetailsManager(account);

        DaoAuthenticationProvider provider = new DaoAuthenticationProvider();
        provider.setUserDetailsService(users);
        provider.setPasswordEncoder(encoder);

        AuthenticationManager manager = new ProviderManager(provider);

        Authentication request =
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "mai", "demo-password");

        show("request", request);

        Authentication result = manager.authenticate(request);

        show("result", result);
    }

    static void show(String stage, Authentication authentication) {
        Object principal = authentication.getPrincipal();

        String principalType = (principal == null)
                ? "null"
                : principal.getClass().getSimpleName();

        String credentialsState = (authentication.getCredentials() == null)
                ? "absent"
                : "present";

        String authorities = authentication.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .filter(Objects::nonNull)
                .sorted()
                .collect(Collectors.joining(","));

        if (authorities.isEmpty()) {
            authorities = "(none)";
        }

        System.out.printf(
                "%s | name=%s | principal=%s | credentials=%s"
                        + " | authorities=%s | authenticated=%s%n",
                stage,
                authentication.getName(),
                principalType,
                credentialsState,
                authorities,
                authentication.isAuthenticated());
    }
}
```

From the `auth-fields-demo` directory, run with a Gradle 8.x compatible with Java 17:

```bash
gradle run
```

If the project already has a Gradle Wrapper, use `./gradlew run` on macOS/Linux or `gradlew.bat run` on Windows. The program prints two main lines (apart from Gradle's own log lines):

```text
request | name=mai | principal=String | credentials=present | authorities=(none) | authenticated=false
result | name=mai | principal=User | credentials=absent | authorities=ROLE_LEARNER | authenticated=true
```

**Breakdown of each value:**

1. Both `request.getName()` and `result.getName()` are `mai`, even though the principal changed from `String` to `UserDetails`: `name` is the identifier name, not the object's class.
2. `request.getPrincipal()` has type `String`. `result.getPrincipal()` is an `org.springframework.security.core.userdetails.User` (a `UserDetails`) returned by `DaoAuthenticationProvider`.
3. `request.getCredentials()` holds the input data; `show` **only prints the `present` status**, never the secret. `result.getCredentials()` was erased by default `ProviderManager` in the sample flow. **Do not use this result to claim every custom provider erases credentials.**
4. `request.getAuthorities()` is empty; after the account is verified with `PasswordEncoder`, the result carries `ROLE_LEARNER` from `UserDetails`.
5. `request.isAuthenticated()` is `false` and the result is `true`. `true` is trustworthy only when produced through a trusted authentication mechanism, never because a developer manually flipped a flag.

**Try variations to deepen understanding:** change the credential to `"wrong"`; `manager.authenticate(...)` will throw an `AuthenticationException` (typically `BadCredentialsException`) instead of returning a successful result. Add a second role with `.roles("LEARNER", "EDITOR")`; after success, the authorities list grows. Replace the request username with a non-existent name; failed authentication does not automatically create an account. Never intentionally write `setAuthenticated(true)` or construct an authenticated token to "skip password verification": that bypasses the trust boundary.

## 7. Using in Spring MVC / Spring Boot Without Exposing Secrets

In a request protected by Spring Security, a controller can accept `Authentication` directly; or use `SecurityContextHolder.getContext().getAuthentication()` when truly needed. Build a DTO containing only fields safe for the client to see:

```java
package demo.web;

import java.util.List;
import java.util.Objects;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class MeController {
    public record MeResponse(String name, List<String> authorities) {}

    @GetMapping("/me")
    public MeResponse me(Authentication authentication) {
        List<String> authorities = authentication.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .filter(Objects::nonNull)
                .sorted()
                .toList();

        return new MeResponse(authentication.getName(), authorities);
    }
}
```

This is a **complete controller class**, though to run as a web application it must live inside a Spring Boot project with `spring-boot-starter-web`, `spring-boot-starter-security`, a `@SpringBootApplication` entry point, and authentication configuration. The `/me` endpoint **must be protected with an `authenticated()` rule** to guarantee the parameter is non-null and the response never leaks an anonymous identity. Depending on purpose, you can return only `name` and omit authorities if the UI does not need them.

Example configuration protecting `/me`, illustrated inside a `@Configuration` with a `SecurityFilterChain` bean:

```java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/me").authenticated()
            .anyRequest().permitAll())
        .httpBasic(Customizer.withDefaults());
    return http.build();
}
```

Required imports for this config snippet: `org.springframework.context.annotation.Bean`, `org.springframework.security.config.Customizer`, `org.springframework.security.config.annotation.web.builders.HttpSecurity`, and `org.springframework.security.web.SecurityFilterChain`. The sample configuration must be paired with a properly configured user store/`AuthenticationProvider`; do not treat it as a standalone runnable program.

If you only need the principal already mapped by type, Spring MVC also provides `@AuthenticationPrincipal`. For example, `@AuthenticationPrincipal UserDetails user` works when the provider is guaranteed to return `UserDetails`; if the application moves to JWT/OIDC, revisit that parameter type or introduce a unified mapping layer.

**Note on Anonymous:** `SecurityContext` may contain an `AnonymousAuthenticationToken` when not logged in. That token type can return `isAuthenticated() == true` by implementation design; therefore **never** rely solely on checking that flag to decide "a real user has logged in". Prefer letting Spring Security enforce `authenticated()`/`fullyAuthenticated()` per policy, or use `AuthenticationTrustResolver` when programmatic checks are unavoidable.

## 8. Comparing the Getters Across Authentication Mechanisms

The values below are **typical examples**, not a fixed contract across every implementation, custom converter, or version.

| Context | `getName()` | `getPrincipal()` | `getCredentials()` | `getAuthorities()` |
| --- | --- | --- | --- | --- |
| Username/password request | Input username | `String` username | Raw password before processing | Empty, untrusted |
| Username/password succeeded | User's username | `UserDetails` or custom principal | Usually erased/null | Granted roles/permissions |
| JWT Resource Server | Usually `sub` | `Jwt` | Depends on token implementation/lifecycle; do not expose | Authorities mapped from scopes/claims per config |
| OIDC Login | Per selected name attribute | `OidcUser` | Depends on implementation; do not expose | Authorities mapped by client/provider |
| Anonymous | Usually `anonymousUser` | May be an anonymous string | Not a real user's password | May carry `ROLE_ANONYMOUS` |

With JWT/OIDC in particular: `getPrincipal()` can hold claims verified by the authentication flow, yet not every claim should be displayed or trusted as a permission. **API authorities** must come from a trusted issuer and a properly designed converter; never let a client send `"roles":["ADMIN"]` and bind it straight into `Authentication` without verifying the source. `getName()` and `getPrincipal()` must still be interpreted within organization, tenant, issuer, and user-mapping boundaries.

## 9. Testing: What Should Be Verified for Each Method?

A minimal test suite should cover both the **`Authentication` object** and **actual HTTP request behavior**.

| Case | What must be proven |
| --- | --- |
| Creating `UsernamePasswordAuthenticationToken.unauthenticated` | `getPrincipal()` holds input username, `getCredentials()` receives credential, `isAuthenticated() == false`, authorities empty |
| Valid authentication via `AuthenticationManager` | Accurate name; principal matches provider; authorities come from trusted source; authentication succeeds |
| Wrong password | Throws `AuthenticationException`; no trusted result produced |
| Default credential erasure mechanism | In standard flows supporting `CredentialsContainer`, the result no longer holds the raw password |
| Switching source from user/password to JWT/OIDC | Does not cast principal to `UserDetails` when types do not match |
| No user / anonymous | Protected endpoint does not accidentally return `anonymousUser` as a logged-in user |
| Empty authorities or missing `ROLE_ADMIN` | Login may succeed yet admin-only requests are still denied |
| `hasRole("ADMIN")` vs `hasAuthority("ROLE_ADMIN")` rules | Correct handling of default prefix and current customizations |
| REST response / logging | Contains no credentials, raw `Authentication`, password hashes, or secrets |
| Resource belonging to another tenant | Holding a broad authority does not grant access to every record |

When using `spring-security-test`, `@WithMockUser` helps test rules requiring a principal/authority without running form login. However, **it does not prove passwords are hashed or that the real provider authenticates properly**. Include at least one test running through the real `AuthenticationManager`/login filter for username/password paths, and test with appropriate JWT/IdP simulators when using those mechanisms.

## 10. Common Mistakes and How to Fix Them

1. **Using `getName()` as the unique DB ID across all login types.** Display names/usernames can change, and external IdP names have their own namespaces. Normalize to an internal user ID; for OIDC, store issuer + subject per linking policy.
2. **Casting `getPrincipal()` to `UserDetails` without checking.** JWT/OIDC logins or custom principals will throw `ClassCastException`. Check the type or use a mapping layer.
3. **Returning the raw principal to the frontend.** Easily leaks password hashes or sensitive claims. Use a DTO/field allowlist.
4. **Reading passwords via `getCredentials()` after login.** Credentials are usually erased; even if present, they must not be reused to authenticate against another service. Design dedicated token/service-to-service authentication.
5. **Logging `Authentication` unchecked.** Custom implementations can expose sensitive data. Log only minimal events such as authentication type, outcome, and correlation ID; never log credentials/tokens.
6. **Equating `getAuthorities()` with "logged in".** Authorities can be empty; check authentication state and policies in the right places.
7. **Comparing roles with the wrong prefix.** `hasRole("ADMIN")` by default requires `ROLE_ADMIN`, whereas `hasAuthority(...)` matches the exact string.
8. **Letting clients supply authorities and treating them as trusted.** Authorities must be verified/granted from a secure source in the authentication/authorization pipeline.
9. **Checking only `isAuthenticated()` to exclude anonymous.** Anonymous tokens can carry `true`; use an authentication trust resolver or protect endpoints with Spring Security rules.
10. **Assuming erasing credentials wipes all sensitive info from the principal.** Password hashes, claims, personal attributes, and details must be managed/redacted separately.
11. **Reusing an old `Authentication` object after account status/authority changes.** Sessions or tokens may hold previously granted authorities; refresh/revocation/revalidation policies must be designed separately.
12. **Constructing an authenticated token directly in an application controller.** That bypasses the trust boundary. Perform authentication via the appropriate manager/provider/filter.

## 11. Capstone Exercises and Completion Criteria

**Exercise A — Read every field accurately:** run `AuthFieldsDemo` in section 6, record the two output lines, and explain why `getName()` stays the same while `getPrincipal()`, `getCredentials()`, and `getAuthorities()` change. Change the username or enter a wrong password to observe the failure path.

**Exercise B — Change roles:** add the `EDITOR` role to the user, predict the authority strings, and re-run to compare with the output. Explain why `ROLE_EDITOR` appears even though `.roles("EDITOR")` was declared.

**Exercise C — Safe DTO:** write a `GET /me` endpoint restricted to authenticated users, returning name and authorities in a DTO. Verify the response contains no password hash, raw credentials, bearer token, or raw principal.

**Exercise D — Multiple principal types:** list the principal types for form login, JWT Resource Server, and OIDC Login. Propose how to map them into an internal `CurrentUser(id, tenantId, displayName)`; identify which field serves as the stable link and which is for display only.

**Exercise E — Anonymous and 403:** call a protected endpoint while unauthenticated, while authenticated without the required authority, and while authenticated with the right authority. Explain authentication vs. authorization separately, and why `isAuthenticated()` alone is insufficient in all cases.

**Completion criteria:** you pass when you can quickly answer four questions: what name `getName()` returns, which types `getPrincipal()` can be, why `getCredentials()` can be null after authentication, and who grants and consumes `getAuthorities()`. More importantly, you must know **never to expose raw credentials/principals** and **never to turn client-asserted authorities into trusted permissions**.

## 12. Official References

- [Spring Security 6.3.10 — Authentication API](https://docs.spring.io/spring-security/site/docs/6.3.10/api/org/springframework/security/core/Authentication.html): getter signatures, principal/credential/authorities, and authentication state contract.
- [Spring Security — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): `SecurityContext`, role of `Authentication`, `AuthenticationManager`, and providers.
- [Spring Security — Authorization Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/architecture.html): `GrantedAuthority`, role prefix, and authorization checks.
- [Spring Security — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html): flow for loading `UserDetails` and checking passwords.
- [Spring Security — UsernamePasswordAuthenticationToken API](https://docs.spring.io/spring-security/site/docs/6.3.10/api/org/springframework/security/authentication/UsernamePasswordAuthenticationToken.html): unauthenticated vs. authenticated tokens.
- [Spring Security — ProviderManager API](https://docs.spring.io/spring-security/site/docs/6.3.10/api/org/springframework/security/authentication/ProviderManager.html): provider chain and credential erasure policy.

**Version note:** the runnable example targets Spring Security **6.3.x** APIs, matching the Spring Boot 3.3.x line. When a project uses Spring Security 7 or custom infrastructure, re-check constructors/APIs and actual configuration; never mechanically copy a username/password example for JWT, OIDC, or anonymous flows.