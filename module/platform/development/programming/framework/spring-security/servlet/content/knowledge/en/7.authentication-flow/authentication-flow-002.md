# AuthenticationManager and Input/Output Contracts in Spring Security Servlet

> **Scope:** Spring Security Servlet (e.g., Spring Security 6.x, Spring Framework 6, and Java 17+). This lesson explains exactly what `AuthenticationManager` accepts, returns, or throws; how `ProviderManager` collaborates with `AuthenticationProvider`; and how the result is placed into `SecurityContext` by security filters. The hands-on section uses Spring Boot 3.x for ease of running, while the interfaces explained belong to Spring Security and do not depend on Spring Boot.

## 1. Position of AuthenticationManager in the Authentication Flow

A security system must distinguish two questions:

- **Authentication:** Who are you? Is the provided proof valid?
- **Authorization:** Is this authenticated identity permitted to perform a specific action?

`AuthenticationManager` solves the **authentication** part. It does not directly receive an `HttpServletRequest`, does not create an HTTP response itself, does not decide permissions for a URL on its own, and does not automatically save the user into a session. Those tasks are handled by other parts of Spring Security.

Visualizing an HTTP Basic or form login flow:

```text
Client sends HTTP request
        |
        v
Servlet container + Spring Security filter chain
        |
        v
Authentication filter
  - Extract credentials from request (form, Basic, token...)
  - Create an unauthenticated Authentication
        |
        | authenticate(input)
        v
AuthenticationManager
        |
        v
ProviderManager (a common implementation)
  - Select an AuthenticationProvider supporting the token type
  - Verify account, password, token, or other proof
        |
        +------------------------------+
        |                              |
     SUCCESS                        FAILURE
        |                              |
   Authenticated                  AuthenticationException
   Authentication                      |
        |                              v
        |                      Filter handles failure
        |                      (401 / redirect / handler)
        v
Filter updates SecurityContext
+ saves context if policy requires
        |
        v
AuthorizationFilter / method security
        |
        v
Controller or 403 if insufficient permissions
```

In the Servlet stack, `FilterChainProxy` orchestrates security filters; `AuthenticationManager` is the **authentication invocation point**, while `AuthenticationProvider` performs the verification logic for a specific credential type. These concepts are related, not interchangeable.

## 2. The Formal Contract: `authenticate(Authentication)`

The core interface in simplified form:

```java
package org.springframework.security.authentication;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;

public interface AuthenticationManager {
    Authentication authenticate(Authentication authentication)
            throws AuthenticationException;
}
```

The code above shows the interface signature for study, **not a file to create in your project**: Spring Security already provides this interface.

Interpretation:

1. **Input:** an `Authentication` object representing an **authentication request**. Typically it contains only a username/credential or an unverified token, so `isAuthenticated() == false`. The input may also be another `Authentication` subtype depending on the integration mechanism.
2. **Success:** returns an **authenticated** `Authentication`, populated with the principal and granted authorities based on verification results. The returned object **need not be the same instance or the same class** as the input.
3. **Failure:** throws an exception extending `AuthenticationException`, such as `BadCredentialsException`, `DisabledException`, `LockedException`, or `ProviderNotFoundException`. The caller must handle this failure.
4. **No implicit authorization or persistence:** the method does not place the result into `SecurityContextHolder`, does not save a session, does not keep the user "logged in forever", does not return HTTP 200/401/403, and does not imply every endpoint is permitted.
5. **Do not treat `null` as successful authentication.** An `AuthenticationProvider` may return `null` to defer to another provider; however, a successful `AuthenticationManager` call must return a result object conforming to the contract.

Crucial point: **input and output share the `Authentication` type, yet carry different trust semantics**. A username, role, or `isAuthenticated` flag supplied by the client must never be treated as verified proof.

## 3. What Information Does `Authentication` Contain?

`org.springframework.security.core.Authentication` represents both an **authentication request** and an **authenticated identity**. Common accessors:

| Property / method | On unauthenticated input | On successful output |
| --- | --- | --- |
| `getPrincipal()` | Usually a username (string) or initial token/identifier | `UserDetails`, a principal object, or a trusted identity |
| `getCredentials()` | Password, secret, token, or proof to verify | May have been erased to reduce exposure risk; **not guaranteed to always be `null`** |
| `getDetails()` | May hold request metadata (IP, session ID), if added by a filter | Depends on provider/filter; do not assume it is always present or copied |
| `getAuthorities()` | Usually empty, or untrusted if not yet authenticated | `GrantedAuthority` instances determined by the provider/trusted source |
| `isAuthenticated()` | Usually `false` | Usually `true` for a successfully authenticated user token |
| `getName()` | May derive a name from the initial principal | Identity name for display/logging under appropriate policy |

Example for username/password:

```java
Authentication request =
        UsernamePasswordAuthenticationToken.unauthenticated(
                "linh", "secret123"
        );
// request.isAuthenticated() == false
// request.getPrincipal().equals("linh")
// request.getCredentials() holds the input password
```

This is a **Java fragment** requiring imports for `Authentication` and `UsernamePasswordAuthenticationToken`; it is not a standalone runnable program. Using the `unauthenticated` factory accurately expresses that this data is **unverified**.

After `AuthenticationManager` succeeds, the result from `DaoAuthenticationProvider` is typically an authenticated `UsernamePasswordAuthenticationToken` whose principal is `UserDetails` and which carries authorities (e.g., `ROLE_USER`). `ProviderManager` by default attempts to erase credentials from the result if the object implements `CredentialsContainer`.

### `isAuthenticated()` Does Not Mean "Access Granted"

- `true` indicates the token itself represents an authenticated state; **authorization** still must check roles/authorities, other conditions, and endpoint policies.
- Never call `setAuthenticated(true)` on a user-submitted token to "bypass login". On `UsernamePasswordAuthenticationToken`, the `authenticated(principal, credentials, authorities)` factory or the constructor taking authorities is reserved for logic **already verified by a trusted source**, such as a provider.
- Some special authentication types (e.g., `AnonymousAuthenticationToken`) may also report `isAuthenticated() == true`; Spring Security handles anonymous detection when evaluating the `authenticated()` rule. Therefore, do not replace framework policies with a custom check on the `isAuthenticated()` boolean alone.
- `getAuthorities()` on an **unauthenticated input** is not a trustworthy list of granted permissions. Authorities must come from a verified user store, IdP, or token, not from a client-declared JSON role.

### Principal Is Not Always a Username String

With username/password via `DaoAuthenticationProvider`, the principal may be `UserDetails`. With a JWT Resource Server, the principal is typically a JWT/claim object matching the token; with OAuth2 login or pre-auth, it may have another type. When you only need a name across mechanisms, prefer `authentication.getName()` or inspect the principal type explicitly instead of blindly casting to `UserDetails`.

## 4. `ProviderManager`: Common Implementation of AuthenticationManager

`ProviderManager` implements `AuthenticationManager` by trying a list of `AuthenticationProvider` instances. Each provider has two core methods:

```java
public interface AuthenticationProvider {
    Authentication authenticate(Authentication authentication)
            throws AuthenticationException;

    boolean supports(Class<?> authentication);
}
```

This is a simplified signature to explain the contract; no separate file needs to be created.

- `supports(Class<?>)` indicates whether the provider **can handle that token class**, not that credentials will be valid.
- If supported, `authenticate(...)` may return an authenticated `Authentication`.
- If the provider **cannot decide**, it may return `null` so `ProviderManager` continues trying the next provider.
- If the provider concludes authentication failed, it typically throws an `AuthenticationException`. Depending on the exception type and configuration, `ProviderManager` may try another provider, prioritize account-status errors, or delegate to a parent manager.
- If no provider matches and no parent handles it, `ProviderManager` may throw `ProviderNotFoundException`.

```text
ProviderManager.authenticate(request)
    |
    +-- provider A.supports(request.class)?
    |      +-- no -> try provider B
    |      +-- yes -> authenticate(request)
    |                 +-- valid result -> success
    |                 +-- null -> try provider B
    |                 +-- exception -> handle per error type / policy
    |
    +-- provider B ...
    |
    +-- parent AuthenticationManager (if configured and needed)
    |
    +-- authenticated result OR AuthenticationException
```

Specifically, `ProviderManager` is not an `AuthenticationProvider`; it is a manager that **orchestrates** providers. A common provider for form/Basic is `DaoAuthenticationProvider`, where authentication is split into:

1. Looking up `UserDetails` by username via `UserDetailsService`.
2. Checking account status (locked, disabled, expired, etc., per provider/checker).
3. Matching the password via `PasswordEncoder.matches(rawPassword, encodedPassword)`.
4. Creating a successful `Authentication` with the verified principal and authorities.
5. Reporting failure with an appropriate `AuthenticationException`.

A `ProviderManager` can contain different providers for passwords, pre-auth, or custom token types. **A provider must handle the exact `Authentication` type produced by the filter**; for example, stuffing a JWT string into a `UsernamePasswordAuthenticationToken` and expecting a password provider to verify the JWT signature is a design mismatch.

### Erasing Credentials After Success

By default, `ProviderManager` attempts to call `eraseCredentials()` on the result object if it implements `CredentialsContainer` (`eraseCredentialsAfterAuthentication` defaults to `true`). The goal is to avoid retaining plaintext passwords or secrets in memory or context longer than needed. This can also affect nested objects inside the principal if they share the same instance, so when using a **`UserDetails` cache**, take care not to let credential erasure wipe data the cache expects to reuse for future authentications.

Never log `getCredentials()` or an entire `Authentication` object in a way that leaks secrets, even if you think credentials were erased from the result. Bearer tokens and `details` data can also be sensitive.

## 5. An Authentication Lifecycle in Servlet

Example of a browser submitting a form to `POST /login`:

1. `UsernamePasswordAuthenticationFilter` (when form login is enabled) reads username/password and creates an **unauthenticated** `UsernamePasswordAuthenticationToken`.
2. The filter passes this token to `AuthenticationManager.authenticate(...)`.
3. `ProviderManager` tries a suitable provider; `DaoAuthenticationProvider` loads `UserDetails`, verifies the password, and checks account status.
4. On success, the manager returns an authenticated `Authentication`; the filter runs success steps such as the session authentication strategy and creates a `SecurityContext` holding the result.
5. The filter saves the `SecurityContext` via `SecurityContextRepository` according to strategy, then invokes the success handler (e.g., redirect).
6. Subsequent requests can load the context from the session; `AuthorizationFilter` and/or method security check permissions before allowing business logic.
7. On failure, the filter invokes the failure handler or corresponding entry point; authentication **does not succeed** and does not grant the intended user's permissions.

This path is **conceptual**; exact filter order and concrete classes can vary by configuration and version. HTTP Basic uses `BasicAuthenticationFilter` instead of the form login filter; Bearer tokens use Resource Server filters/tokens/providers. The pattern of input `Authentication` → `AuthenticationManager` → result/exception remains the same.

### `SecurityContextHolder` Is Separate

`SecurityContextHolder` provides access to the current thread's context. **Calling `manager.authenticate(input)` directly from a service or Java program does not automatically place the result into `SecurityContextHolder`**. In a normal HTTP flow, the succeeding filter is what performs that step and configures where the context is persisted.

Illustrative example **once you already have a valid `Authentication result`**:

```java
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(result);
SecurityContextHolder.setContext(context);

try {
    System.out.println(SecurityContextHolder.getContext()
            .getAuthentication().getName());
} finally {
    SecurityContextHolder.clearContext();
}
```

This is a fragment requiring imports for `SecurityContext` and `SecurityContextHolder`; it is not a complete web login flow. Setting a ThreadLocal context **does not automatically ensure the context persists across multiple HTTP requests**: the application must use `SecurityContextRepository` along with the required session and CSRF measures. Avoid writing custom login controllers that bypass framework filters and handlers without fully understanding context persistence, session fixation protection, and failure handling.

## 6. Runnable Example: AuthenticationManager + ProviderManager + HTTP Basic

Let us build a small Spring Boot MVC/Servlet application using **Spring Boot 3.3.5** (illustrative version) and **Java 17+**. There are two in-memory accounts:

| Username | Demo password | Authorities |
| --- | --- | --- |
| `linh` | `secret123` | `ROLE_USER` |
| `quan` | `admin123` | `ROLE_ADMIN` |

To clearly demonstrate inputs and outputs, the application will:

- Explicitly create a `ProviderManager` with a `DaoAuthenticationProvider`.
- Call `authenticate(...)` right after startup to print before/after data.
- Configure HTTP Basic using the **same** `AuthenticationManager` for endpoints `/profile` and `/admin`.
- Verify the difference between successful authentication and URL access authorization.

Directory structure:

```text
authentication-contract/
├── pom.xml
└── src/main/java/example/authcontract/
    ├── AuthenticationContractApplication.java
    ├── SecurityConfig.java
    └── DemoController.java
```

### 6.1. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>authentication-contract</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### 6.2. `AuthenticationContractApplication.java`

```java
package example.authcontract;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AuthenticationContractApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthenticationContractApplication.class, args);
    }
}
```

### 6.3. `SecurityConfig.java`

```java
package example.authcontract;

import java.util.List;

import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails linh = User.withUsername("linh")
                .password(encoder.encode("secret123"))
                .roles("USER")
                .build();
        UserDetails quan = User.withUsername("quan")
                .password(encoder.encode("admin123"))
                .roles("ADMIN")
                .build();
        return new InMemoryUserDetailsManager(linh, quan);
    }

    @Bean
    AuthenticationManager authenticationManager(
            UserDetailsService users, PasswordEncoder encoder) {

        DaoAuthenticationProvider provider = new DaoAuthenticationProvider(users);
        provider.setPasswordEncoder(encoder);

        return new ProviderManager(List.of(provider));
    }

    @Bean
    SecurityFilterChain webSecurity(
            HttpSecurity http, AuthenticationManager manager) throws Exception {

        // Ensure security filters use the declared manager.
        http.authenticationManager(manager);

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/admin").hasRole("ADMIN")
                .requestMatchers("/profile").authenticated()
                .anyRequest().denyAll()
        );
        http.httpBasic(Customizer.withDefaults());
        return http.build();
    }

    @Bean
    ApplicationRunner authenticationProbe(AuthenticationManager manager) {
        return args -> {
            // Create an unauthenticated request.
            Authentication input =
                    UsernamePasswordAuthenticationToken.unauthenticated(
                            "linh", "secret123");

            System.out.println("input.authenticated=" + input.isAuthenticated());

            // Same Authentication interface, now verified.
            Authentication output = manager.authenticate(input);
            System.out.println("output.authenticated=" + output.isAuthenticated());
            System.out.println("output.name=" + output.getName());
            System.out.println("output.authorities=" + output.getAuthorities());
            System.out.println("output.credentialsErased="
                    + (output.getCredentials() == null));
            System.out.println("context.autoFilled="
                    + (SecurityContextHolder.getContext()
                            .getAuthentication() != null));

            try {
                manager.authenticate(
                        UsernamePasswordAuthenticationToken.unauthenticated(
                                "linh", "wrong-password"));
            } catch (BadCredentialsException ex) {
                System.out.println("failure=" + ex.getClass().getSimpleName());
            }
        };
    }
}
```

**Exact explanation of each part:**

- `UserDetailsService` returns the configured users; `PasswordEncoder` uses BCrypt. Store hashed passwords, never compare `rawPassword.equals(encodedPassword)` directly.
- `DaoAuthenticationProvider` looks up the user and checks the password; it is an `AuthenticationProvider`.
- `new ProviderManager(List.of(provider))` creates an `AuthenticationManager` using that specific provider; there is no need to implement the interface manually for standard password login.
- `Authentication input` is created in an **unauthenticated** state with only the username and demo password; the caller does not attach `ROLE_USER` to it.
- `manager.authenticate(input)` verifies it and returns `Authentication output` containing authorities from the user store.
- `ProviderManager` erases credentials from the result by default when possible; this successful example uses a token supporting credential erasure.
- `SecurityContextHolder` remains empty in the probe (which runs outside a request/filter). This proves the manager **does not automatically "log into" an HTTP session**.
- The HTTP Basic filter of `SecurityFilterChain` is pointed to the exact same manager via `http.authenticationManager(manager)`. The HTTP portion handled by the filter differs from the direct call in `ApplicationRunner`.

**Note:** `http.authenticationManager(manager)` sets a manager for the chain being built. In real projects, you can also let Spring Security construct a manager from available providers/beans, or obtain the global manager via `AuthenticationConfiguration`. When multiple `SecurityFilterChain` instances exist, identify which chain uses which manager/provider; avoid accidentally creating a manager missing a provider for the credential type emitted by the chain's filter.

### 6.4. `DemoController.java`

```java
package example.authcontract;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/profile")
    public String profile(Authentication authentication) {
        return "profile:" + authentication.getName();
    }

    @GetMapping("/admin")
    public String admin(Authentication authentication) {
        return "admin:" + authentication.getName();
    }
}
```

The controller receives an `Authentication` **already placed into the request's context by the filter**. That does not mean `AuthenticationManager` inserted it into the context itself. Both endpoints have valid authentication before the method runs; `/admin` must additionally satisfy authority `ROLE_ADMIN`.

### 6.5. Build, Run, and Expected Output

From the directory containing `pom.xml`:

```bash
mvn spring-boot:run
```

Upon successful startup, in addition to standard Spring Boot logs, `ApplicationRunner` prints the following lines in order:

```text
input.authenticated=false
output.authenticated=true
output.name=linh
output.authorities=[ROLE_USER]
output.credentialsErased=true
context.autoFilled=false
failure=BadCredentialsException
```

This output illustrates: the input is a **request/claim**, the output is a **verified identity**, credentials may be erased, failures are signaled via exceptions, and the manager does not set the context itself.

HTTP tests against embedded Tomcat on `localhost:8080` (`curl` syntax for POSIX shells):

```bash
# No authentication proof sent:
curl -s -o /dev/null -w '%{http_code}\n' \
  http://localhost:8080/profile
# 401

# Wrong password:
curl -s -o /dev/null -w '%{http_code}\n' \
  -u linh:wrong-password http://localhost:8080/profile
# 401

# Valid user, endpoint requires authentication only:
curl -s -u linh:secret123 http://localhost:8080/profile
# profile:linh

# Authenticated user, but lacks ROLE_ADMIN:
curl -s -o /dev/null -w '%{http_code}\n' \
  -u linh:secret123 http://localhost:8080/admin
# 403

# Account with ROLE_ADMIN:
curl -s -u quan:admin123 http://localhost:8080/admin
# admin:quan
```

The comment lines show the **expected output** with the unmodified configuration. HTTP Basic sends credentials on every request, so test only locally or over **HTTPS**; never send real passwords over unencrypted HTTP.

### Distinguishing Authentication Errors from Authorization Errors

- `/profile` without credentials or with a wrong password: the filter calls the manager, no authenticated principal is produced → **401** (Basic challenge).
- `/admin` with `linh` and the right password: the manager authenticates successfully, but `AuthorizationFilter` finds `ROLE_ADMIN` missing → **403**.
- `/admin` with `quan`: both authentication and authorization succeed → **200**.

`AuthenticationManager` **does not directly return 401 or 403**. It returns an `Authentication` or throws `AuthenticationException`; filters, the authentication entry point, and access-denied handling translate the outcome into an HTTP response.

## 7. Common `AuthenticationManager` Pitfalls and Issues

| Symptom | Possible Cause | What to Inspect |
| --- | --- | --- |
| `ProviderNotFoundException` | No provider supports the input token's class | Check `supports()`, how the token is constructed, and the list of providers |
| `BadCredentialsException` | Invalid password/token; or user not found and the provider masks details to prevent enumeration | Check encoder, hash format, username, and credential store; do not return detailed errors to clients |
| `DisabledException` / `LockedException` | User is disabled or locked under provider policy | Check `UserDetails` and account status; do not open up permissions as a "quick fix" |
| `CredentialsExpiredException` / `AccountExpiredException` | Credentials or account have expired per source/checker | Design an appropriate credential-rotation or reactivation flow |
| `authenticate` succeeds but subsequent request is still anonymous | No filter saves context/session, or code calls manager outside HTTP filters without handling context | Use standard login mechanisms/filters; inspect `SecurityContextRepository` |
| Received `Authentication` but `getCredentials()==null` | `ProviderManager` erased the secret as designed | Do not use the result to read back the original password/token |
| Casting `getPrincipal()` to `String` fails | Provider returned `UserDetails` or another principal type | Use `getName()` or branch on the authentication type |
| Client sends a role in request and enters API | Application trusted unverified input for permissions | Grant authorities only after verification by a provider/trusted source |
| Login succeeds yet still returns 403 | Valid authentication, but authorities fail the rule | Check `hasRole` / `hasAuthority`, scopes, and role prefixes |
| Unclear which manager is invoked across multiple chains | Multiple `AuthenticationManager`, providers, or `SecurityFilterChain` instances | Review wiring, `http.authenticationManager`, `@Order`, and matchers |
| `SecurityContext` lost in async/other threads | Context is bound to thread/strategy by default and does not automatically propagate across all execution types | Use Spring Security's context propagation mechanisms; do not misuse ThreadLocal |

### Three Serious Design Mistakes to Avoid

**1. Creating an "authenticated" token from client data without verification.**

```java
// WRONG: role taken from untrusted data, bypassing manager/provider.
Authentication forged = UsernamePasswordAuthenticationToken.authenticated(
        userNameFromRequest, null, List.of(new SimpleGrantedAuthority("ROLE_ADMIN"))
);
```

This is a **fragment illustrating an anti-pattern**, not valid business code. It bypasses the authentication contract. Factories creating authenticated tokens may be used in server-side code **only after verification from a trusted source**.

**2. Calling the manager and assuming a login session now exists.**

`manager.authenticate(input)` does not guarantee the result is placed in `SecurityContextRepository` or persisted to future requests. For form login, prefer Spring Security's `formLogin`/filters instead of hand-rolling a controller that handles passwords, sessions, CSRF, and handlers.

**3. Turning every `AuthenticationException` into a "500 system error" or returning overly detailed messages.**

A wrong password is a normal authentication failure, not a system error. Filters and entry points should return an appropriate client response, without disclosing whether the username exists, why it is locked, or which secret failed unless security policy allows it. Log for investigation in a way that does not leak sensitive details.

## 8. Deep Dive into Exceptions and Account Status Handling

Typical failure types all extend `AuthenticationException`:

| Exception | General Meaning |
| --- | --- |
| `BadCredentialsException` | Authentication proof is invalid |
| `UsernameNotFoundException` | User store did not find the username; often masked by `DaoAuthenticationProvider` as `BadCredentialsException` under default settings |
| `DisabledException` | Account is not permitted to log in because it is disabled |
| `LockedException` | Account is locked |
| `AccountExpiredException` | Account has expired |
| `CredentialsExpiredException` | Credential has expired |
| `ProviderNotFoundException` | No provider found supporting the authentication type |
| `AuthenticationServiceException` | Authentication service/infrastructure failure that should be distinguished from a wrong password |

Under `AuthenticationManager`'s contract, disabled/locked account checks and credential verification follow an appropriate order; providers typically stop immediately on severe status errors. However, exact ordering and error details depend on the provider, user source, and configuration.

**Do not assume a 1:1 mapping from an exception class to an HTTP status.** Filters, handlers, session state, and the login mechanism determine the response. Failed form login may redirect to a login page with an error message; Basic/Bearer typically use a 401 response with an appropriate challenge. A 403 typically belongs to **authorization/CSRF** rather than a return value from the manager.

## 9. Managing Managers in Applications with Multiple Authentication Methods

An application may simultaneously serve form login, Basic, JWT/OAuth2 Resource Server, or other authentication mechanisms. Valid setups include:

- A single `ProviderManager` containing multiple `AuthenticationProvider`s, each supporting distinct authentication tokens.
- Multiple `SecurityFilterChain`s, each configuring its own security filters and appropriate `AuthenticationManager`.
- In advanced cases, using `AuthenticationManagerResolver<HttpServletRequest>` when a manager must be chosen dynamically per request (e.g., multiple issuers/tenants with clear trust boundaries).

Do not build a catch-all manager that returns an authenticated token merely because the request includes a username. For JWTs, the provider/decoder must verify signature, issuer, audience, expiration, and relevant claims per design. For passwords, there must be `PasswordEncoder.matches` and account checks.

**Distinguishing `AuthenticationManager` and `UserDetailsService`:** `UserDetailsService` only provides user details by username and **does not itself prove** the password is valid. `DaoAuthenticationProvider` coordinates it with `PasswordEncoder` and checks to authenticate. `AuthenticationManager` is the external orchestration contract.

**Distinguishing `AuthenticationManager` and `AuthorizationManager`:** similar names, different duties. `AuthenticationManager` turns valid proof into a trusted `Authentication`; `AuthorizationManager` (in modern authorization) makes access decisions based on authentication and the resource. Never use them interchangeably.

## 10. Testing: Describing the Minimum Test Cases

In unit or integration tests, verify both the manager's contract and the HTTP flow. Baseline cases:

| Case | Expectation at manager | Expectation at sample HTTP Basic app |
| --- | --- | --- |
| Valid username/password `linh/secret123` | Successful `Authentication`, `getName()=="linh"`, authority `ROLE_USER` | `GET /profile` → 200 |
| Wrong password | Throws `BadCredentialsException` | `GET /profile` → 401 |
| Missing Basic credentials | Filter lacks sufficient credentials to authenticate user | `GET /profile` → 401 |
| `linh` accesses admin | Manager authenticates successfully | `GET /admin` → 403 due to role rule |
| `quan` accesses admin | Manager authenticates successfully, `ROLE_ADMIN` | `GET /admin` → 200 |
| Input token unsupported by any provider | Throws `ProviderNotFoundException` if no parent resolves it | Depends on mechanism's filter/entry point |
| Direct manager call outside request | Returns output without setting context automatically | Does not automatically create a browser login session |

You can write HTTP tests with Spring Security Test (`spring-security-test`), MockMvc, or a real HTTP client. When using `@WithMockUser`, understand that it **simulates authentication** and does not run the provider's password validation. To test the `DaoAuthenticationProvider`/`AuthenticationManager` contract, you must actually invoke the manager with credentials and assert the exception or result.

## 11. Self-Review Questions

1. **What is the input to `AuthenticationManager.authenticate`?** An `Authentication` representing an authentication request and proof to verify, typically unauthenticated.
2. **What does the manager return on success?** An `Authentication` containing the identity, authenticated status, and authorities derived from verification.
3. **Does a failing manager return `false` or HTTP 401?** Neither. It throws `AuthenticationException`; filters and handlers decide the HTTP response.
4. **Can `AuthenticationProvider.authenticate` return `null`?** Yes, when the provider cannot decide and wants to defer to another provider; `null` must never be treated as successful login.
5. **Does `supports()` returning true mean credentials are valid?** No. It only means the provider can handle that token class.
6. **After `manager.authenticate`, does `SecurityContextHolder` automatically contain the user?** Not when calling the manager directly; a security filter or appropriate integration code must manage the context.
7. **After authentication, does `getCredentials()` still contain the password?** Do not rely on it; `ProviderManager` normally erases credentials on tokens supporting erasure.
8. **Why does `linh` with the right password get 403 on `/admin`?** Having the right password is authentication; requiring `ROLE_ADMIN` is separate authorization.
9. **Should roles from a request be passed into `UsernamePasswordAuthenticationToken.authenticated(...)`?** No, if those roles have not been verified by a trusted source.
10. **Is `UserDetailsService` an `AuthenticationManager`?** No; it looks up users, whereas the manager/provider verifies credentials and issues the authentication result.

## 12. Implementation Checklist

- [ ] Create an **authentication request token** of the right type and in an unauthenticated state.
- [ ] Have a provider support the token via `supports()` and verify it against a trusted source.
- [ ] Accept the trusted output `Authentication` or handle `AuthenticationException`; never grant permissions from untrusted input.
- [ ] Never log passwords, credentials, tokens, or sensitive data in `details`.
- [ ] Do not assume principal is always a `String` or `UserDetails`; check the contract for the active mechanism.
- [ ] Use appropriate filters/handlers/context repositories for HTTP login; the manager does not create sessions itself.
- [ ] Enforce authorization separately after authentication; an authenticated user is not guaranteed access to every resource.
- [ ] With multiple providers/chains, verify exactly which manager and provider are selected to avoid mismatches.
- [ ] Write tests for valid output, wrong passwords, invalid accounts, missing providers, and denied permissions.

**Conclusion:** The contract of `AuthenticationManager` is **untrusted input `Authentication` → verification by provider → trusted output `Authentication`, or `AuthenticationException`**. Servlet filters handle extracting data from HTTP, saving `SecurityContext`, and turning failures into HTTP responses; authorization handles what an authenticated user **is allowed to do**.