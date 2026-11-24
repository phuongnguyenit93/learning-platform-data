# Customizing Credential Verification with AuthenticationProvider in Spring Security

> **Scope:** Spring Security for Servlet/Spring MVC applications, Java 17+, Spring Boot 3.x, and Spring Security 6.x. The topic is how to build, register, and test a custom `AuthenticationProvider` to verify credentials according to an application's specific requirements. The example uses HTTP Basic and in-memory account data to focus on the extension point.

## 1. When Is a Custom AuthenticationProvider Needed?

In Spring Security, **authentication** answers "who is sending the request and is the proof of identity valid?". **Authorization** answers "does the verified identity have permission to perform this operation?". These two do not replace each other.

`AuthenticationProvider` is the interface responsible for **authenticating a specific type of `Authentication` object**. It can look up an account, verify a password/token, evaluate account status, and return an authenticated `Authentication` containing the principal and authorities. If verification fails, it throws an appropriate authentication exception.

Cases that may require a custom provider: verifying credentials against a legacy account system; authenticating users who must satisfy custom activation rules; using a special access mechanism with a custom token; integrating with an internal authentication service. However, **not every application needs to rewrite a provider**: if you only need to change how users are read from a database and verify passwords normally, prefer `UserDetailsService` + `PasswordEncoder` + `DaoAuthenticationProvider`.

Learning objectives:

1. Understand the roles of `AuthenticationManager`, `ProviderManager`, `AuthenticationProvider`, filters, and `SecurityContext`.
2. Understand the contract of `supports(Class<?>)`, `authenticate(Authentication)`, and the three possible outcomes.
3. Write a provider that verifies passwords with BCrypt, checks account status, and grants authorities safely.
4. Register the provider with `SecurityFilterChain` and verify HTTP 200/401/403 results.
5. Know how to test independently, distinguish authentication from authorization, and avoid security mistakes when customizing.

## 2. Where AuthenticationProvider Fits in the Authentication Flow

Typical flow in a Servlet application using HTTP Basic:

```text
HTTP request (Authorization: Basic ...)
     |
     v
BasicAuthenticationFilter
     | creates unauthenticated UsernamePasswordAuthenticationToken
     v
AuthenticationManager (typically ProviderManager)
     | invokes a provider matching the token type
     v
Custom AuthenticationProvider
     | looks up account / checks credential / checks status
     +---------------------------+
     |                           |
     v                           v
Authenticated                AuthenticationException
Authentication result        (BadCredentialsException,
     |                        DisabledException, ...)
     v                           |
Authentication filter            v
writes SecurityContext    Basic mechanism responds
     |                     with auth error (usually 401)
     v
AuthorizationFilter / AuthorizationManager
     |                           |
     v                           v
Authorized                   Missing permission
     |                           |
     v                           v
Controller / HTTP 200       Denied (usually 403)
```

| Component | Responsibility |
| --- | --- |
| `Authentication` | Holds principal, credentials, authorities, and authentication status; serves as either unauthenticated input or authenticated result. |
| `AuthenticationProvider` | Checks one type of `Authentication` and returns success, rejects, or defers to another provider. |
| `AuthenticationManager` | The `authenticate(Authentication)` interface invoked by login mechanisms. |
| `ProviderManager` | Common manager implementation; iterates through providers and uses `supports` to select candidates. |
| `Authentication filter` | Reads data from the HTTP request, creates the input token, calls the manager, and handles the result and security context. |
| `SecurityContextHolder` | Provides the current `SecurityContext`; the filter is normally responsible for updating it after the manager succeeds. |
| `AuthorizationManager` / `AuthorizationFilter` | Decides whether to grant access to a resource based on `Authentication` and access policies. |
| `AuthenticationEntryPoint` / failure handler | Decides how to respond to authentication requirements, e.g., HTTP Basic 401 or form login redirect. |

**Important:** A new provider **does not automatically know how to read a new header/cookie/body**. If you want to authenticate a custom header like `X-Api-Key`, you also need to add a mechanism to extract the credential from the request and create the corresponding `Authentication` type before calling the manager/provider. By contrast, Basic/form login already provide filters for username/password.

## 3. The AuthenticationProvider Contract

The Spring Security interface has two main methods (this is an illustrative declaration; the interface is already provided by the library):

```java
public interface AuthenticationProvider {
    Authentication authenticate(Authentication authentication)
            throws AuthenticationException;

    boolean supports(Class<?> authentication);
}
```

### 3.1. supports(Class<?>) checks the token type

`supports` receives the Java class of the token; it **does not inspect roles, usernames, URL paths, or password contents**.

Example provider for username/password:

```java
@Override
public boolean supports(Class<?> authenticationType) {
    return UsernamePasswordAuthenticationToken.class
            .isAssignableFrom(authenticationType);
}
```

`isAssignableFrom` also allows subclasses of `UsernamePasswordAuthenticationToken`. Returning `true` only means the provider **can evaluate** this token type; it does not guarantee authentication will succeed. If you must accept a different credential type, design a dedicated token and `supports` for that exact type rather than returning `true` for every `Authentication`.

### 3.2. authenticate(Authentication) has three possible outcomes

| Outcome | Meaning |
| --- | --- |
| Return an authenticated `Authentication` | Credentials are valid; principal and granted authorities come from a trusted source. |
| Return `null` | Provider cannot make a determination for this input; `ProviderManager` can try the next provider. |
| Throw `AuthenticationException` | Authentication failed or an authentication error occurred; e.g., `BadCredentialsException`, `DisabledException`, `LockedException`, `AuthenticationServiceException`. |

If the token type matches and the password is wrong, a password-checking provider should normally **throw `BadCredentialsException`**, rather than returning `null` as if it did not care. When there are multiple providers, returning `null` and trial order affect behavior. `ProviderManager` may continue trying after certain authentication exceptions; for account-status errors under `AccountStatusException`, the process may stop immediately. Do not rely on the assumption that "the first provider is always the final provider".

Username/password input is typically represented by an unauthenticated token:

```java
Authentication request =
        UsernamePasswordAuthenticationToken.unauthenticated(
                "reader", "reader-pass");
```

Once verification succeeds, the provider can return:

```java
return UsernamePasswordAuthenticationToken.authenticated(
        username,
        null,
        List.of(new SimpleGrantedAuthority("ROLE_USER")));
```

The two snippets above are **illustrative fragments** within a method scope and require appropriate imports/variables. The result has `isAuthenticated() == true`; `credentials` is set to `null` so the raw password is not retained. Never construct a successful token solely from a client-supplied `username` or `role`.

## 4. Complete Runnable Example on Spring Boot

We will provide three demo accounts:

| Username | Demo password | Status | Authority |
| --- | --- | --- | --- |
| `reader` | `reader-pass` | Active | `ROLE_USER` |
| `admin` | `admin-pass` | Active | `ROLE_ADMIN` |
| `disabled` | `disabled-pass` | Disabled | `ROLE_USER` |

The provider will (1) look up the username from a `Map`, (2) match the password using BCrypt, (3) check `enabled`, and (4) return a token containing the authority. Demo accounts are created in memory at startup for learning purposes only; production must store hashes and statuses in a real data store and manage secrets safely.

### 4.1. Dependencies

In a Spring Boot 3.x project that already has the Gradle plugin and Java 17+, add the following starters to `dependencies` in `build.gradle`:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

This is a dependency declaration snippet, **not an entire `build.gradle` file**. With Maven, use the corresponding starters.

### 4.2. Complete Source Code

Create `src/main/java/demo/DemoApplication.java` with the exact name and package:

```java
package demo;

import java.util.List;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.DisabledException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}

@Configuration
class SecurityConfig {
    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    AuthenticationProvider demoAuthenticationProvider(PasswordEncoder encoder) {
        return new DemoAuthenticationProvider(encoder);
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            AuthenticationProvider demoAuthenticationProvider) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public").permitAll()
                        .requestMatchers("/admin").hasRole("ADMIN")
                        .anyRequest().authenticated())
                .authenticationProvider(demoAuthenticationProvider)
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}

record DemoAccount(String passwordHash, boolean enabled, String role) {
}

final class DemoAuthenticationProvider implements AuthenticationProvider {
    private final PasswordEncoder encoder;
    private final Map<String, DemoAccount> users;
    private final String dummyPasswordHash;

    DemoAuthenticationProvider(PasswordEncoder encoder) {
        this.encoder = encoder;
        this.users = Map.of(
                "reader", new DemoAccount(
                        encoder.encode("reader-pass"), true, "ROLE_USER"),
                "admin", new DemoAccount(
                        encoder.encode("admin-pass"), true, "ROLE_ADMIN"),
                "disabled", new DemoAccount(
                        encoder.encode("disabled-pass"), false, "ROLE_USER")
        );
        this.dummyPasswordHash = encoder.encode("unused-dummy-password");
    }

    @Override
    public Authentication authenticate(Authentication input)
            throws AuthenticationException {
        String username = input.getName();
        Object credentials = input.getCredentials();
        String rawPassword = credentials instanceof String value ? value : "";

        DemoAccount account = users.get(username);
        String hash = account == null
                ? dummyPasswordHash
                : account.passwordHash();

        boolean matches = encoder.matches(rawPassword, hash);
        if (account == null || !matches) {
            throw new BadCredentialsException("Bad credentials");
        }
        if (!account.enabled()) {
            throw new DisabledException("Account disabled");
        }

        return UsernamePasswordAuthenticationToken.authenticated(
                username,
                null,
                List.of(new SimpleGrantedAuthority(account.role()))
        );
    }

    @Override
    public boolean supports(Class<?> authenticationType) {
        return UsernamePasswordAuthenticationToken.class
                .isAssignableFrom(authenticationType);
    }
}

@RestController
class DemoController {
    @GetMapping("/public")
    String publicPage() {
        return "public";
    }

    @GetMapping("/profile")
    String profile() {
        return "profile";
    }

    @GetMapping("/admin")
    String admin() {
        return "admin";
    }
}
```

**This is a complete Java program in a single file**, using a single `public` class `DemoApplication`. The remaining classes are top-level package-private classes in the same `demo` package, scanned by Spring Boot at startup. The `record` syntax and `instanceof String value` pattern matching require Java 17 or higher.

In this code, `.authenticationProvider(demoAuthenticationProvider)` attaches the custom provider to the HTTP Security configuration. HTTP Basic provides the mechanism to read username/password and invoke the manager. `.requestMatchers("/admin").hasRole("ADMIN")` is an **authorization** check applied after credentials are validated. By convention, `hasRole("ADMIN")` requires the `ROLE_ADMIN` authority.

### 4.3. Running the Program and Checking HTTP Responses

With Gradle Wrapper:

```bash
./gradlew bootRun
```

On Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

By default, if no other port is configured, the application runs at `http://localhost:8080`. Using another terminal:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/profile
curl -i -u reader:wrong-pass http://localhost:8080/profile
curl -i -u reader:reader-pass http://localhost:8080/profile
curl -i -u reader:reader-pass http://localhost:8080/admin
curl -i -u admin:admin-pass http://localhost:8080/admin
curl -i -u disabled:disabled-pass http://localhost:8080/profile
```

If PowerShell aliases `curl` to `Invoke-WebRequest`, use `curl.exe` instead of `curl`.

| Scenario | Expected HTTP | Why? |
| --- | --- | --- |
| `GET /public` unauthenticated | 200, body `public` | `permitAll`. |
| `GET /profile` unauthenticated | 401 | HTTP Basic requires authentication. |
| `reader` enters wrong password | 401 | Provider throws `BadCredentialsException`. |
| `reader` enters right password, calls `/profile` | 200, body `profile` | Valid `Authentication` result. |
| `reader` enters right password, calls `/admin` | 403 | Authenticated but missing `ROLE_ADMIN`. |
| `admin` enters right password, calls `/admin` | 200, body `admin` | Passes both authentication and authorization. |
| `disabled` enters right password | 401 | Provider throws `DisabledException`; Basic responds with an authentication error. |

`curl -i` shows status, headers, and body; an HTTP Basic 401 response typically includes `WWW-Authenticate`. These are results **for the example configuration**. Form login may redirect instead of returning 401; Bearer tokens use their own challenge mechanism. If you deliberately send an invalid Basic header to `/public`, the Basic filter may reject it before reaching `permitAll`; public endpoints should be tested without sending invalid credentials.

## 5. Explaining the Logic Inside the Provider

### 5.1. Reading credentials of the right type

`input.getName()` gets the identifier, and `input.getCredentials()` returns `Object`. With a `UsernamePasswordAuthenticationToken` created by HTTP Basic, credentials are usually a `String`. `credentials instanceof String value ? value : ""` avoids unsafe casting and treats missing credentials as invalid authentication.

If the app uses a custom token type, do not apply the casting/password assumptions from this example; define the token's contract clearly, and write `supports` and `authenticate` accordingly.

### 5.2. Protecting passwords and account data

`PasswordEncoder.matches(rawPassword, storedHash)` verifies a password hashed with BCrypt. Never compare raw passwords against stored passwords, never store plaintext passwords, and never use `{noop}` in production. The example generates hashes at runtime for easy learning; real products must store persistent hashes, have a hash upgrade strategy, and never hard-code passwords.

When a username does not exist, the example still runs `encoder.matches(...)` against `dummyPasswordHash`. The goal is to reduce an easily observable timing difference between "non-existent account" and "wrong password"; this **is not a constant-time guarantee**. You still need rate limiting, brute-force detection, input controls, and generic error messages for clients.

### 5.3. Checking account status

`BadCredentialsException` reflects unacceptable credentials; `DisabledException` reflects a known account that is disabled after the password matched. Other systems may distinguish `LockedException`, `AccountExpiredException`, and `CredentialsExpiredException` according to business rules.

Do not expose internal messages such as "this username exists but is locked" through public APIs. Throwing semantically accurate exceptions internally helps monitor exact causes; presenting errors to clients is the responsibility of the entry point/failure handler.

### 5.4. Returning a safe result token

`UsernamePasswordAuthenticationToken.authenticated(username, null, authorities)` is called only after verification completes. In the example:

- `principal` is the verified username.
- `credentials` is `null` so the raw password is not kept.
- `authorities` are taken from the server-side account, never reading client-supplied roles.

`ProviderManager` also erases sensitive credentials from successful results whenever possible. If the application returns a shared `UserDetails` instance from a cache, understand the effect of credential erasure on that cached object.

### 5.5. Do not mutate SecurityContextHolder from inside the provider

`AuthenticationProvider` focuses on verifying and **returning a result**. In the HTTP Basic flow, the filter calls `AuthenticationManager` and updates `SecurityContext` after success; the provider does not call `SecurityContextHolder.getContext().setAuthentication(...)` itself. If an application calls the manager manually in a controller or service, it must explicitly integrate the result with an appropriate security context/session persistence strategy, and not treat `authenticate` as a complete login session.

## 6. Registering a Provider, Multiple Providers, and Multiple Filter Chains

There are two key parts in the example:

```java
@Bean
AuthenticationProvider demoAuthenticationProvider(PasswordEncoder encoder) {
    return new DemoAuthenticationProvider(encoder);
}
```

and the `HttpSecurity` configuration:

```java
.authenticationProvider(demoAuthenticationProvider)
.httpBasic(Customizer.withDefaults())
```

These two snippets are **configuration fragments inside the complete `SecurityConfig` from section 4** and do not run standalone if separated.

`HttpSecurity.authenticationProvider(...)` adds a provider used when building the security chain's authentication manager. If you genuinely need dedicated control over the manager, you can create a `ProviderManager` with a specifically designed list of providers and configure `http.authenticationManager(...)`. There is no need to use every registration mechanism at once just because they exist.

If a project has multiple providers, check:

1. Does `supports` of each provider overlap on token types?
2. When multiple providers support the same token type, do the traversal order and throwing exceptions/returning `null` satisfy your policy?
3. Does a provider mistakenly turn "wrong credential" into "let another provider try"?
4. Is there a filter creating the exact `Authentication` type accepted by the provider?
5. Are there multiple `SecurityFilterChain` beans with different `securityMatcher` rules? The provider must be scoped to the chain that actually handles the request.

When using Resource Server JWT, OAuth2/OIDC, LDAP, or SAML, specialized providers/mechanisms usually already exist. A custom username/password provider does not authenticate JWTs merely because it is registered as a Spring bean.

## 7. When Is DaoAuthenticationProvider a Better Choice?

`DaoAuthenticationProvider` already implements username/password authentication using `UserDetailsService` and `PasswordEncoder`. You usually do not need to write a new provider just to change how accounts are looked up in a database. Comparison:

| Requirement | Solution to consider |
| --- | --- |
| Read users from a custom table/database | Implement `UserDetailsService`; use `DaoAuthenticationProvider`. |
| Change algorithm or upgrade password hashes | Configure `PasswordEncoder` and password upgrade mechanisms. |
| Authenticate with genuinely custom logic/credentials | Custom `AuthenticationProvider` or specialized component. |
| Accept an API key in a custom header | Filter/converter reading the request, custom token, and matching provider. |
| Access permissions by URL, role, or scope | `authorizeHttpRequests`/`AuthorizationManager`; method security if needed. |
| Format 401/403 errors | `AuthenticationEntryPoint`, `AccessDeniedHandler`, login failure handler. |

Example **alternative configuration snippet** in a `@Configuration` class using Spring Security 6.x:

```java
@Bean
AuthenticationProvider standardProvider(
        UserDetailsService userDetailsService,
        PasswordEncoder passwordEncoder) {
    DaoAuthenticationProvider provider =
            new DaoAuthenticationProvider(userDetailsService);
    provider.setPasswordEncoder(passwordEncoder);
    return provider;
}
```

Additional imports when using this snippet:

```java
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.password.PasswordEncoder;
```

The snippet above is not part of the `DemoAuthenticationProvider` example running in section 4. Do not automatically register both providers for the same token without designing ordering and failure handling. With standard configuration, Spring Boot/Spring Security can typically auto-create the authentication mechanism when the project supplies a valid `UserDetailsService`.

## 8. Testing the Provider Independently

A well-written provider can be tested with JUnit without starting a server. With `spring-boot-starter-test`, create `src/test/java/demo/DemoAuthenticationProviderTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.DisabledException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;

import static org.junit.jupiter.api.Assertions.*;

class DemoAuthenticationProviderTest {
    private final DemoAuthenticationProvider provider =
            new DemoAuthenticationProvider(new BCryptPasswordEncoder());

    @Test
    void validPasswordProducesAuthenticatedResult() {
        Authentication request =
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "reader", "reader-pass");

        Authentication result = provider.authenticate(request);

        assertTrue(result.isAuthenticated());
        assertEquals("reader", result.getName());
        assertNull(result.getCredentials());
        assertTrue(result.getAuthorities().stream()
                .anyMatch(a -> "ROLE_USER".equals(a.getAuthority())));
    }

    @Test
    void wrongPasswordIsRejected() {
        Authentication request =
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "reader", "wrong");

        assertThrows(BadCredentialsException.class,
                () -> provider.authenticate(request));
    }

    @Test
    void unknownUsernameIsRejected() {
        Authentication request =
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "missing", "anything");

        assertThrows(BadCredentialsException.class,
                () -> provider.authenticate(request));
    }

    @Test
    void disabledAccountIsRejected() {
        Authentication request =
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "disabled", "disabled-pass");

        assertThrows(DisabledException.class,
                () -> provider.authenticate(request));
    }

    @Test
    void supportsUsernamePasswordType() {
        assertTrue(provider.supports(
                UsernamePasswordAuthenticationToken.class));
    }
}
```

Run:

```bash
./gradlew test
```

Add integration tests with `MockMvc` or real HTTP to prove that `SecurityFilterChain` actually calls the provider, returning 401 when credentials are wrong/disabled and 403 when credentials are valid but a role is missing. Unit tests prove the logic inside the provider; web tests prove how the provider connects with filters and handlers.

## 9. Common Mistakes and Deployment Checklist

**Common mistakes:**

- Returning an authenticated token before checking credentials, or reading authorities directly from the client payload.
- Putting all credential checks in controllers and bypassing `AuthenticationManager` and filters.
- Registering a provider bean without a filter/converter that creates the corresponding token type.
- Writing `supports` to return `true` for every `Authentication`, causing overlap and conflicts across providers.
- Returning `null` for every wrong password, giving another provider a chance to process it unintentionally.
- Throwing `BadCredentialsException` for database/gateway timeout errors, making operational failures hard to distinguish.
- Logging passwords, Authorization headers, or sensitive exception messages; revealing whether a username exists.
- Confusing `AuthenticationException` with `AccessDeniedException`: an authenticated user lacking `ROLE_ADMIN` needs authorization handling, normally returning 403.
- Hastily disabling CSRF upon seeing 403; the error may be caused by a missing CSRF token unrelated to the provider.
- Using HTTP Basic over unencrypted HTTP outside localhost; HTTPS and brute-force protection are required.

**Before going to production:** use TLS, an approved hash store/password encoder, login attempt rate limiting, username enumeration protection, external service timeouts, no sensitive data leaks, semantically accurate account-status handling, safe metrics/logging, and tests for both success and failure cases. `AuthenticationProvider` should have clear responsibilities, be concurrency-safe, and never store per-request credentials in shared fields of a singleton bean.

## 10. Self-Practice Questions

1. Based on what information does `AuthenticationProvider.supports(...)` return `true`? Does it verify whether the password is valid?
2. When a password is wrong in a provider that already accepted `UsernamePasswordAuthenticationToken`, should it throw `BadCredentialsException` or return `null`? Why?
3. Why does `reader` with the right password get 403 when calling `/admin`, while `reader` with the wrong password gets 401?
4. If you want to read an API key from the `X-Api-Key` header, is implementing `AuthenticationProvider` alone sufficient?
5. When you only need to load users from a custom table and use BCrypt, is it necessary to write a custom provider?
6. Why does the provider result set `credentials = null` and use server-supplied authorities?
7. What happens if you share one provider across multiple `SecurityFilterChain` beans without attaching it to the chain handling the right requests?
8. Should a timeout from an external authentication service be tracked as an infrastructure error or silently recorded as "wrong password"?

**Answer hints:** (1) the `Authentication` type; (2) throw an appropriate exception once credentials have been evaluated and failed; (3) authentication differs from authorization; (4) a component is needed to extract the request and create the token; (5) usually `UserDetailsService` + `DaoAuthenticationProvider`; (6) prevents leaking secrets and forged roles; (7) the provider may never be invoked; (8) distinguish and log infrastructure errors safely.

## Official Documentation

- [Spring Security — Servlet Authentication Architecture, AuthenticationManager, ProviderManager](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security 6.5 — AuthenticationProvider API](https://docs.spring.io/spring-security/site/docs/6.5.6/api/org/springframework/security/authentication/AuthenticationProvider.html)
- [Spring Security 6.5 — HttpSecurity.authenticationProvider API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/annotation/web/builders/HttpSecurity.html)
- [Spring Security 6.5 — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html)
- [Spring Security — UserDetailsService](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/user-details-service.html)
- [Spring Security — PasswordEncoder](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/password-encoder.html)