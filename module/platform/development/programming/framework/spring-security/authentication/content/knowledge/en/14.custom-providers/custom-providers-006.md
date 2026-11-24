# Distinguishing Between Returning null, Throwing AuthenticationException, and System Errors

## 1. The Problem: What Decisions Must a Custom Provider Make?

In Spring Security Servlet, an `AuthenticationManager` (typically `ProviderManager`) receives an unauthenticated `Authentication` object and passes it through matching `AuthenticationProvider` instances. Each provider may authenticate against a different source: internal accounts, a dedicated tenant, a directory, or a specialized credential type. A custom provider must clearly distinguish between **cannot handle the request**, **handled but authentication failed**, **authentication succeeded**, and **cannot reach a conclusion because the system errored**.

The `AuthenticationProvider` contract has two primary methods:

~~~java
public interface AuthenticationProvider {
    Authentication authenticate(Authentication authentication)
            throws AuthenticationException;

    boolean supports(Class<?> authentication);
}
~~~

| Situation inside provider | What should it do? | Signal sent to `ProviderManager` |
| --- | --- | --- |
| Credentials verified, account valid | Return an authenticated `Authentication` with principal/authorities | **Success:** stop searching other providers. |
| Provider is not responsible for this specific credential | Return `null` | **Inconclusive:** try the next provider supporting the token type. |
| Credential belongs to this provider but is wrong | Throw `BadCredentialsException` or an appropriate `AuthenticationException` subclass | **Authentication failure:** manager records the error; may try later providers depending on exception type. |
| Account is determined to be locked/disabled | Throw `LockedException` / `DisabledException` (subclasses of `AccountStatusException`) | **Stop immediately** per `ProviderManager`'s special handling. |
| Internal authentication system errored, cannot conclude true/false | Throw an appropriate `AuthenticationServiceException`, usually `InternalAuthenticationServiceException` for internal failures | **Infrastructure error:** do not turn into “wrong password” or `null`; `InternalAuthenticationServiceException` stops the chain immediately. |
| `Authentication` type is not supported by the provider at all | `supports(...)` returns `false` | Provider is skipped; `authenticate(...)` is not called. |

**Most important rule:** `null` does not mean “wrong password”, and a database connection failure is not “unsupported token type”. Each decision has different consequences for fallback, logging, client responses, and security.

## 2. How Does ProviderManager Evaluate the Provider List?

Suppose a manager holds providers A, B, and C in order, and receives a `UsernamePasswordAuthenticationToken`:

~~~text
AuthenticationManager.authenticate(request)
              |
              v
         ProviderManager
              |
              v
        Provider A supports?
          |             |
         NO            YES
          |             |
          |        A.authenticate(...)
          |           |      |        |
          |         null  success   exception
          |           |      |        |
          |           |    RETURN    | 
          |           |              +-- AccountStatusException /
          |           |              |   InternalAuthenticationServiceException
          |           |              |       → THROW immediately
          |           |              |
          |           |              +-- Other AuthenticationException
          |           |                    → record, try B
          |           v
        Provider B ...
              |
         Is there a result?
          |          |
         YES        NO
          |          |
       RETURN     Check parent if present;
                  if still failed, throw
                  appropriate exception
~~~

Points to read carefully:

1. `supports(Class<?>)` is only an **`Authentication` object type filter**. Returning `true` means the provider can inspect further; it does not guarantee every instance of that class falls within its scope. After `supports` returns `true`, `authenticate(...)` **can still return `null`**.
2. A **non-`null`** `Authentication` result makes `ProviderManager` stop asking subsequent providers. Therefore, a provider must never return the unauthenticated token to pretend “not handled”.
3. A normal authentication exception, such as `BadCredentialsException`, **does not necessarily terminate the entire manager immediately**. `ProviderManager` may try subsequent providers. If a later provider succeeds, that successful result replaces the earlier error.
4. If no provider succeeds, the last appropriate authentication exception is thrown; if no provider handled the token and no exception occurred, the manager throws `ProviderNotFoundException`.
5. `AccountStatusException` and `InternalAuthenticationServiceException` receive special handling in `ProviderManager`: it stops immediately without continuing to later providers.
6. If a `parent AuthenticationManager` is configured, the parent may be queried when current providers have not returned a result. Do not rely on the parent as a workaround for misconfigured missing providers.

These behaviors belong to Spring Security's **`ProviderManager`** and should not be generalized to every custom implementation of the `AuthenticationManager` interface. Provider ordering and exception types directly affect the final outcome.

## 3. When Should You Return null?

`return null` means: **“I am a provider that can inspect this token class, but this specific request does not fall within my scope of responsibility; let another provider try.”**

For example, a system allows two different account domains to share `UsernamePasswordAuthenticationToken`:

- Accounts whose username starts with `tenant:` are owned by `TenantAuthenticationProvider`.
- Accounts whose username starts with `local:` are owned by `LocalAuthenticationProvider`.

Both providers can return `supports(UsernamePasswordAuthenticationToken.class) == true`. Yet when receiving `local:bob`, the Tenant provider must return `null` because that request belongs to the Local provider. That is completely different from `tenant:alice` submitting the wrong password: the Tenant provider **took ownership**, so it must throw `BadCredentialsException`.

~~~java
@Override
public Authentication authenticate(Authentication authentication)
        throws AuthenticationException {

    String username = authentication.getName();

    if (!username.startsWith("tenant:")) {
        return null; // Not this provider's account domain.
    }

    // From here on, this provider is responsible for verifying the tenant account.
    if (!isValidTenantCredential(authentication)) {
        throw new BadCredentialsException("Invalid credentials");
    }

    return createAuthenticatedResult(authentication);
}
~~~

**The snippet above is conceptual Java pseudocode**, since `isValidTenantCredential` and `createAuthenticatedResult` are not defined. A complete runnable example is in section 7 below.

Do not return `null` in these cases:

- The username **belongs to this provider** but is not found in its database. Not finding a user within an owned domain should normally be an authentication failure (avoid returning `null` to send the request to a weaker provider).
- Wrong password, expired token, invalid signature, revoked credential: already checked and determined to be a failure.
- Database down, LDAP timeout, key store unreachable: these are verification failures and must be represented as system errors.
- Account locked or disabled: these are account status failures, not signals to fall back.

If providers have **overlapping username/credential spaces**, design explicit credential ownership rules. Arbitrarily returning `null` can let a credential rejected by a strong provider be accepted by a weak provider.

## 4. When Should You Throw AuthenticationException?

`AuthenticationException` is the base class for errors **during authentication**. It is an *unchecked exception* (`RuntimeException`), though declaring `throws AuthenticationException` on the method clarifies the contract.

Common subclasses:

| Exception type | When appropriate? | Meaning |
| --- | --- | --- |
| `BadCredentialsException` | Username/password or other credential is invalid | Request was evaluated and failed authentication. |
| `UsernameNotFoundException` | System knows the account does not exist | Internal lookup detail; avoid exposing to clients. |
| `DisabledException` | Account is disabled | Account status error; manager stops immediately. |
| `LockedException` | Account is locked | Account status error; manager stops immediately. |
| `AccountExpiredException` | Account has expired | Account status error; manager stops immediately. |
| `CredentialsExpiredException` | Credentials have expired | An `AccountStatusException`; manager stops immediately. |
| `ProviderNotFoundException` | No suitable provider produced a result | Usually a wiring/token type issue; decided by manager. |
| `AuthenticationServiceException` | Authentication system could not process request | Not evidence of wrong credentials. |
| `InternalAuthenticationServiceException` | Internal authentication system failed | Subclass of `AuthenticationServiceException`; manager stops chain immediately. |

**Common misconception:** `BadCredentialsException` is an `AuthenticationException`, yet in `ProviderManager` it is normally recorded while still giving later providers a chance. Never claim “throwing any `AuthenticationException` stops the manager immediately”. The specific exception type determines whether early termination applies.

### 4.1. Invalid Credentials

When the provider owns the account, invalid credentials can be reported as:

~~~java
if (!passwordEncoder.matches(rawPassword, user.getPasswordHash())) {
    throw new BadCredentialsException("Invalid credentials");
}
~~~

This snippet depends on `user` and `passwordEncoder` defined in a real system; it illustrates where the password hash check happens. Avoid distinguishing “username does not exist” from “wrong password” in public responses so attackers cannot enumerate accounts. `DaoAuthenticationProvider` / `AbstractUserDetailsAuthenticationProvider` defaults to `hideUserNotFoundExceptions` to mask that difference.

### 4.2. Account Status

If the account is locked or disabled:

~~~java
if (user.isLocked()) {
    throw new LockedException("Account is locked");
}
if (!user.isEnabled()) {
    throw new DisabledException("Account is disabled");
}
~~~

This is also illustrative logic based on an application's `user` object. With standard `ProviderManager`, errors extending `AccountStatusException` make the manager **stop trying other providers**, because falling back to a weaker source could bypass account lockout policies.

### 4.3. Other Authentication Failures Do Not Necessarily Prevent Fallback

Suppose providers A and B both support the token:

~~~text
A.authenticate(...) → BadCredentialsException
B.authenticate(...) → Authentication succeeded
ProviderManager    → returns B's result
~~~

This is intentional behavior of `ProviderManager`, **but it does not mean you should allow fallback after a wrong password within the same account domain**. When multiple providers verify the same identity, you can accidentally create a bypass around account protection policies. Clearly route token types, tenants, or credential sources before authentication and thoroughly test provider ordering.

## 5. System Errors: When Authentication Cannot Be Determined Valid or Invalid

A system error occurs when the provider **cannot complete verification**, for example:

- The internal user store loses connection, the repository throws an exception, or required data cannot be read.
- The signature-verification component cannot load valid keys due to an infrastructure error.
- A credential-processing dependency is misconfigured, times out, or is unavailable.
- Backend data violates the contract and cannot be safely verified.

In these scenarios, **do not return `null`** (which could accidentally pass to another provider) and **do not convert everything to `BadCredentialsException`** (which hides outages and causes false wrong-password alerts).

### 5.1. AuthenticationServiceException and InternalAuthenticationServiceException

`AuthenticationServiceException` extends `AuthenticationException` and describes that the authentication system could not process the request due to an incident. `InternalAuthenticationServiceException` extends `AuthenticationServiceException`, emphasizing a failure in an internal application-controlled component. Per Spring Security's contract, these two types are **not identical in how `ProviderManager` continues the chain**:

- `InternalAuthenticationServiceException`: `ProviderManager` catches it specifically and rethrows immediately without trying the next provider.
- Plain `AuthenticationServiceException`: caught in the general `AuthenticationException` branch, so the manager **may continue to other providers**. Do not assume every “service exception” stops early.

Example illustrating how to preserve the original cause:

~~~java
try {
    return loadAccountFromInternalStore(username);
} catch (RepositoryUnavailableException ex) {
    throw new InternalAuthenticationServiceException(
        "Internal credential store is unavailable", ex);
}
~~~

This is an **illustrative snippet**, as `loadAccountFromInternalStore` and `RepositoryUnavailableException` are hypothetical names in a specific system.

**Classification warning:** do not automatically map every external provider outage to `InternalAuthenticationServiceException`. Spring Security's documentation distinguishes internal errors from external system errors. Choose the exception type fitting your integration contract; at the same time design **fail closed** behavior, operational alerts, and explicit fallback rules. If an infrastructure exception is permitted to continue to another provider, ensure that is an intentional policy and does not bypass security controls.

### 5.2. What About Runtime Exceptions Outside AuthenticationException?

Suppose provider code has a programming bug:

~~~java
throw new IllegalStateException("Broken provider configuration");
~~~

`IllegalStateException` does not extend `AuthenticationException`. `ProviderManager` does not treat every `RuntimeException` as “wrong password” to move to the next provider. The error can bubble up as an application error through other exception handling, with no guaranteed HTTP status without inspecting the filter/controller.

Never write `catch (Exception ex) { return null; }` or `catch (RuntimeException ex) { throw new BadCredentialsException(...); }` to swallow all errors: that loses the root cause, breaks fallback handling, and complicates operations. Catch exceptions **at a defined integration boundary**, preserve the cause, and log sanitized data.

### 5.3. HTTP Status Is Not Decided by AuthenticationProvider Directly

A provider returns an `Authentication` object or throws an exception; it **does not own the HTTP response code**. Calling components such as the authentication filter, `AuthenticationEntryPoint`, `AuthenticationFailureHandler`, or JSON controller decide the status/redirect/body.

An illustrative API policy:

| Outcome | Typical suitable API response | Notes |
| --- | --- | --- |
| Wrong credentials / unauthenticated | `401 Unauthorized` | Generic message; do not reveal specific user/password details. |
| Authenticated but insufficient endpoint permissions | `403 Forbidden` | This is **authorization**, usually via `AccessDeniedHandler`, distinct from `AuthenticationException`. |
| Authentication system disrupted | `503 Service Unavailable` or appropriate operational error status | **Does not automatically** become 503 without configuring error mapping. |
| Login succeeded | HTTP `200` or protocol success response | If using sessions, save `SecurityContext` properly. |

**Do not claim** Spring Security maps `InternalAuthenticationServiceException` to 503 by default. With uncustomized filters/controllers, the handling and response may be 401 or a login error page. If an API needs to distinguish infrastructure outages, configure a failure handler / entry point or controller layer explicitly.

## 6. Quick Decision Table by Scenario

| Scenario | `supports` | `authenticate` | Is the next provider tried? |
| --- | --- | --- | --- |
| Provider only supports OTP tokens; request is username/password | `false` | Not called | Yes. |
| Provider supports username/password class, but request belongs to another login source | `true` | `return null` | Yes. |
| Wrong password in a source owned by this provider | `true` | `BadCredentialsException` | Possibly, per `ProviderManager` logic. |
| Username belongs to this source but does not exist | `true` | Usually `BadCredentialsException` or masked `UsernameNotFoundException` | Possibly; must avoid poorly designed fallback. |
| Account is locked | `true` | `LockedException` | **No**, stops immediately. |
| Account is disabled | `true` | `DisabledException` | **No**, stops immediately. |
| Internal store hit an unprocessable failure | `true` | `InternalAuthenticationServiceException` | **No**, stops immediately. |
| Plain service exception | `true` | `AuthenticationServiceException` | **Possibly**, does not stop immediately by default. |
| Valid credentials, provider builds authenticated result | `true` | Returns non-`null` `Authentication` | **No**, completes. |
| All providers skip token class / return null | `false` or `null` | No result | Manager throws `ProviderNotFoundException` if no exception/parent succeeded. |

This table describes `ProviderManager` in Spring Security 6.x; custom managers may implement different logic. `supports(true)` says nothing about whether credentials are valid or invalid.

## 7. Runnable Java 17+ Example with JUnit 5: Verifying Each Branch

The following example focuses on the **provider contract**, without running a servlet container. We use two providers:

- `TenantProvider` owns usernames starting with `tenant:`; it returns `null` for other namespaces.
- `LocalProvider` owns usernames starting with `local:`; it returns `null` for other namespaces.

Both support `UsernamePasswordAuthenticationToken`, have demo BCrypt passwords, and are wired into a `ProviderManager` in order. Tests verify exactly which provider gets called and which exception emerges. This avoids guessing from HTTP statuses before understanding the manager.

### 7.1. Dependencies and File Location

In a Gradle project configured with Spring Boot 3.x / JDK 17+ and JUnit Platform:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

This is only a **`build.gradle` snippet**, not a complete build file. You can place the test in a Boot project that already has plugin/dependency management; Spring Security/JUnit versions are managed by the Boot BOM.

Place the file at:

~~~text
src/test/java/com/example/security/ProviderSemanticsTest.java
~~~

### 7.2. Complete Test Code

~~~java
package com.example.security;

import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.DisabledException;
import org.springframework.security.authentication.InternalAuthenticationServiceException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.ProviderNotFoundException;
import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ProviderSemanticsTest {

    // Creates dummy account solely for illustration. BCrypt hashes differ per run.
    private final PasswordEncoder encoder = new BCryptPasswordEncoder(4);
    private final String demoHash = encoder.encode("demo-pass");

    private ProviderManager manager(List<String> calls) {
        return new ProviderManager(List.of(
            new TenantProvider(calls, encoder, demoHash),
            new LocalProvider(calls, encoder, demoHash)
        ));
    }

    private static Authentication request(String username, String password) {
        return UsernamePasswordAuthenticationToken.unauthenticated(
            username, password);
    }

    private static Authentication success(String username) {
        return UsernamePasswordAuthenticationToken.authenticated(
            username,
            null,
            List.of(new SimpleGrantedAuthority("ROLE_USER"))
        );
    }

    private static final class TenantProvider implements AuthenticationProvider {
        private final List<String> calls;
        private final PasswordEncoder encoder;
        private final String hash;

        TenantProvider(List<String> calls, PasswordEncoder encoder, String hash) {
            this.calls = calls;
            this.encoder = encoder;
            this.hash = hash;
        }

        @Override
        public boolean supports(Class<?> type) {
            return UsernamePasswordAuthenticationToken.class
                .isAssignableFrom(type);
        }

        @Override
        public Authentication authenticate(Authentication auth)
                throws AuthenticationException {
            calls.add("TENANT");

            String username = auth.getName();
            if (!username.startsWith("tenant:")) {
                return null; // Does not belong to this namespace.
            }

            if ("tenant:disabled".equals(username)) {
                throw new DisabledException("Account disabled");
            }
            if ("tenant:outage".equals(username)) {
                throw new InternalAuthenticationServiceException(
                    "Internal account store is unavailable",
                    new IllegalStateException("Simulated storage outage")
                );
            }

            boolean known = "tenant:alice".equals(username);
            boolean valid = known && encoder.matches(
                String.valueOf(auth.getCredentials()), hash);
            if (!valid) {
                throw new BadCredentialsException("Invalid credentials");
            }

            return success(username);
        }
    }

    private static final class LocalProvider implements AuthenticationProvider {
        private final List<String> calls;
        private final PasswordEncoder encoder;
        private final String hash;

        LocalProvider(List<String> calls, PasswordEncoder encoder, String hash) {
            this.calls = calls;
            this.encoder = encoder;
            this.hash = hash;
        }

        @Override
        public boolean supports(Class<?> type) {
            return UsernamePasswordAuthenticationToken.class
                .isAssignableFrom(type);
        }

        @Override
        public Authentication authenticate(Authentication auth)
                throws AuthenticationException {
            calls.add("LOCAL");

            String username = auth.getName();
            if (!username.startsWith("local:")) {
                return null;
            }

            boolean known = "local:bob".equals(username);
            boolean valid = known && encoder.matches(
                String.valueOf(auth.getCredentials()), hash);
            if (!valid) {
                throw new BadCredentialsException("Invalid credentials");
            }

            return success(username);
        }
    }

    @Test
    void nullAllowsNextProviderToAuthenticate() {
        List<String> calls = new ArrayList<>();
        Authentication result = manager(calls).authenticate(
            request("local:bob", "demo-pass"));

        assertTrue(result.isAuthenticated());
        assertEquals("local:bob", result.getName());
        assertEquals(List.of("TENANT", "LOCAL"), calls);
    }

    @Test
    void successfulProviderStopsTheChain() {
        List<String> calls = new ArrayList<>();
        Authentication result = manager(calls).authenticate(
            request("tenant:alice", "demo-pass"));

        assertTrue(result.isAuthenticated());
        assertEquals(List.of("TENANT"), calls);
    }

    @Test
    void badCredentialsIsRetainedWhenNoLaterProviderSucceeds() {
        List<String> calls = new ArrayList<>();
        assertThrows(BadCredentialsException.class, () ->
            manager(calls).authenticate(
                request("tenant:alice", "wrong-pass")));

        // Manager also asks LOCAL; LOCAL returns null.
        assertEquals(List.of("TENANT", "LOCAL"), calls);
    }

    @Test
    void accountStatusFailureStopsImmediately() {
        List<String> calls = new ArrayList<>();
        assertThrows(DisabledException.class, () ->
            manager(calls).authenticate(
                request("tenant:disabled", "demo-pass")));

        assertEquals(List.of("TENANT"), calls);
    }

    @Test
    void internalServiceFailureStopsImmediately() {
        List<String> calls = new ArrayList<>();
        InternalAuthenticationServiceException error = assertThrows(
            InternalAuthenticationServiceException.class,
            () -> manager(calls).authenticate(
                request("tenant:outage", "demo-pass")));

        assertInstanceOf(IllegalStateException.class, error.getCause());
        assertEquals(List.of("TENANT"), calls);
    }

    @Test
    void unsupportedTokenTypeHasNoProvider() {
        List<String> calls = new ArrayList<>();
        assertThrows(ProviderNotFoundException.class, () ->
            manager(calls).authenticate(
                new TestingAuthenticationToken("alice", "token")));

        assertTrue(calls.isEmpty());
    }

    @Test
    void laterSuccessCanOverrideEarlierBadCredentials() {
        List<String> calls = new ArrayList<>();

        AuthenticationProvider rejects = new AuthenticationProvider() {
            @Override
            public boolean supports(Class<?> type) {
                return UsernamePasswordAuthenticationToken.class
                    .isAssignableFrom(type);
            }

            @Override
            public Authentication authenticate(Authentication auth) {
                calls.add("REJECT");
                throw new BadCredentialsException("First provider rejects");
            }
        };

        AuthenticationProvider succeeds = new AuthenticationProvider() {
            @Override
            public boolean supports(Class<?> type) {
                return UsernamePasswordAuthenticationToken.class
                    .isAssignableFrom(type);
            }

            @Override
            public Authentication authenticate(Authentication auth) {
                calls.add("ACCEPT");
                return success(auth.getName());
            }
        };

        Authentication result = new ProviderManager(
            List.of(rejects, succeeds)).authenticate(
                request("demo", "demo-pass"));

        assertTrue(result.isAuthenticated());
        assertEquals(List.of("REJECT", "ACCEPT"), calls);
    }
}
~~~

The final test **intentionally makes the second provider accept the request** solely to expose the `ProviderManager` contract: a later provider's success can override a `BadCredentialsException` thrown by an earlier provider. **Never put an “accept-all-requests” provider like this into a real application.** In production, every provider must genuinely verify credentials, account locks, and namespace scopes before creating an authenticated result.

The demo password is hashed with BCrypt; `matches` verifies via hash rather than storing Base64 or comparing plaintext passwords in real applications. In the test, the hash is regenerated on each run so the string differs, while `matches` produces stable results.

### 7.3. Running and Explaining the Results

In the project directory:

~~~bash
./gradlew test --tests com.example.security.ProviderSemanticsTest
~~~

On Windows:

~~~powershell
.\gradlew.bat test --tests com.example.security.ProviderSemanticsTest
~~~

When dependencies/plugins are present and tests pass, Gradle reports `BUILD SUCCESSFUL` (potentially with other logs depending on configuration). The tests rely on assertions rather than fixed console stdout.

Each test corresponds to a branch:

| Test | What happens in ProviderManager | Result |
| --- | --- | --- |
| `nullAllowsNextProviderToAuthenticate` | TENANT returns null → LOCAL succeeds | Authentication succeeds for `local:bob`. |
| `successfulProviderStopsTheChain` | TENANT succeeds | LOCAL is not called. |
| `badCredentialsIsRetainedWhenNoLaterProviderSucceeds` | TENANT throws BadCredentials → LOCAL returns null | Throws BadCredentials. |
| `accountStatusFailureStopsImmediately` | TENANT throws DisabledException | LOCAL is not called. |
| `internalServiceFailureStopsImmediately` | TENANT throws InternalAuthenticationServiceException | LOCAL is not called; preserves root cause. |
| `unsupportedTokenTypeHasNoProvider` | Both `supports` return false | ProviderNotFoundException. |
| `laterSuccessCanOverrideEarlierBadCredentials` | REJECT throws BadCredentials → ACCEPT succeeds | Manager returns ACCEPT's result. |

Inspecting **the order in which providers are called** is how you distinguish `return null`, normal exceptions, and early-stopping exceptions. If your application has multiple `AuthenticationManager` / filter chains, make sure tests construct the exact manager holding the actual provider list and ordering used for real requests.

## 8. Connecting to HTTP Login or JSON Login

In Spring Security Servlet, a filter (such as `UsernamePasswordAuthenticationFilter` or `BasicAuthenticationFilter`) calls `AuthenticationManager`. AuthenticationManager calls the providers. When providers fail, the filter/login handler handles the exception per configured mechanism.

~~~text
POST /login or /api/login
      |
      v
AuthenticationFilter / Controller
      |
      v
AuthenticationManager
      |
      +--> Provider A
      |      +-- null → Provider B
      |      +-- Authentication → success flow
      |      +-- AuthenticationException → failure flow
      |
      v
Success result / exception
      |
      +--> Login succeeded: update SecurityContext,
      |    session/token per design
      |
      +--> Login failed: FailureHandler/EntryPoint
           or controller decides HTTP status/body
~~~

### 8.1. JSON API Returning Clear Errors Without Leaking Info

This is an **illustrative controller handling snippet**, not a standalone Java file. The goal is to show exception classification order:

~~~java
try {
    Authentication authenticated = authenticationManager.authenticate(
        UsernamePasswordAuthenticationToken.unauthenticated(
            request.username(), request.password()));
    // Save SecurityContext/session or issue token per architecture.
    return ResponseEntity.ok(toLoginResponse(authenticated));
}
catch (AuthenticationServiceException ex) {
    // Server log includes request ID; mask credentials and sensitive info.
    log.error("Authentication backend unavailable", ex);
    return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
        .body(Map.of("error", "authentication_temporarily_unavailable"));
}
catch (AuthenticationException ex) {
    return ResponseEntity.status(HttpStatus.UNAUTHORIZED)
        .body(Map.of("error", "invalid_credentials"));
}
~~~

Variables `authenticationManager`, `request`, `log`, and method `toLoginResponse` must be declared in the application. `AuthenticationServiceException` must come **before** `AuthenticationException` because it is a subclass. Never return `ex.getMessage()` to the browser: exception messages can expose backend details, system names, or account states.

An API can choose 503 when the authentication service is unavailable, but that is an **application decision**; Spring Security does not automatically commit to turning every service failure into 503. When handling via filters, use the corresponding `AuthenticationFailureHandler` / `AuthenticationEntryPoint` rather than assuming a controller will catch the exception.

### 8.2. 401 and 403 Are Two Different Stages

- `401 Unauthorized` (in HTTP authentication context) usually means authentication has not succeeded. Invalid credentials, missing credentials, or no matching provider can land here depending on filter and handler.
- `403 Forbidden` usually means authenticated but blocked by permission policies, or the request was blocked by another filter such as CSRF. `AccessDeniedException` belongs to the authorization flow; **an `AuthenticationProvider` throwing an exception does not automatically produce 403**.
- Backend system errors may need to be reported via 503 or a dedicated operational mechanism; never falsely label them “wrong password”.

Therefore when debugging, check the **actual exception at the provider** and which provider ran before analyzing the HTTP response.

## 9. Pitfalls When Implementing a Custom Provider

### Pitfall 1 — Returning null When a User Is Not Found in an Owned Source

A provider authenticating all `tenant:*` usernames returns `null` if `tenant:alice` does not exist. A downstream provider might accept the same username with a weaker mechanism. Distinguish **not my namespace** from **my user but invalid**. The second case usually throws `BadCredentialsException`; in external APIs, avoid revealing whether the account exists.

### Pitfall 2 — Turning Database Errors into BadCredentialsException

If the connection pool is exhausted, a database query times out, or the repository is unavailable, you cannot conclude the user entered the wrong password. Converting everything to `BadCredentialsException` causes clients to retry improperly, pollutes failed-login metrics, hinders outage investigation, and can trigger account lockouts for the wrong reason. Preserve the cause and log operational errors safely.

### Pitfall 3 — Catching All Exceptions and Returning null

~~~java
try {
    return doAuthenticate(authentication);
} catch (Exception ignored) {
    return null; // WRONG: masks wrong passwords, locked accounts, and outages.
}
~~~

This illustrative code is strictly to demonstrate an **anti-pattern**: depending on exception types, the manager may fall back unexpectedly. Catch specific error groups intentionally instead of suppressing all errors.

### Pitfall 4 — Assuming BadCredentialsException Always Stops Every Provider

`ProviderManager` can keep trying and let a later provider succeed. If you need to prevent bypasses across account domains, design separate token types, routing, or managers. Stopping everything with a fake “account locked” exception is also wrong because it distorts semantics; solve ownership/fallback issues in architecture.

### Pitfall 5 — Returning an Unauthenticated Token Instead of null

~~~java
return UsernamePasswordAuthenticationToken.unauthenticated(
    authentication.getPrincipal(),
    authentication.getCredentials()
);
~~~

This code does not create an authenticated result, yet it is **different from `return null`**: the manager receives a non-null object and stops checking other providers. Do not treat this as a standard way to signal “I do not support this request”. On success, return an authenticated token with an appropriate principal and authorities; when not handling it, return null.

### Pitfall 6 — Broken supports() Logic

For instance, never make `supports` always return true for every `Authentication` type and blindly cast to `UsernamePasswordAuthenticationToken`. That can trigger `ClassCastException` instead of a meaningful authentication message.

~~~java
@Override
public boolean supports(Class<?> tokenType) {
    return UsernamePasswordAuthenticationToken.class
        .isAssignableFrom(tokenType);
}
~~~

If you need to support a custom token type, create a dedicated class extending `AbstractAuthenticationToken` and provide a matching provider. Never use `supports` to inspect username/password; it receives only a `Class<?>`, with no credential instance.

### Pitfall 7 — Skipping Account Status Checks Before Granting Authorities

A valid password for a locked user must still be rejected. Place enabled/locked/expired checks alongside password hash checks at the proper boundary. If using `DaoAuthenticationProvider` with `UserDetailsService`, many status checks are already built in; do not rewrite everything unnecessarily.

### Pitfall 8 — Returning Untrusted Principal/Authorities

When a provider returns an authenticated `Authentication`, authorities must come from verified server data. Never take role lists from login JSON or a client-asserted token and attach them to the authenticated result. Never call `authenticated(...)` before completing all password, account status, signature, or factor checks.

### Pitfall 9 — Retaining Credentials or Logging Secrets

`ProviderManager` erases credentials from the result by default when the object implements `CredentialsContainer` (configurable behavior). Still, providers should never put raw passwords into logs, exception messages, telemetry, or long-lived principals. Prefer `PasswordEncoder.matches(...)` and return `null` credentials when possible. Credential erasure does not replace proper secret management.

### Pitfall 10 — Seeing 401 Without Checking for ProviderNotFoundException

`ProviderNotFoundException` can stem from a missing provider or passing a token type mismatched with `supports`; this is typically a wiring/flow bug to fix, not necessarily a user mistyping their password. Record the exception type in controlled internal logs and check both the token class and provider list.

## 10. QA Checklist When Adding an AuthenticationProvider

A custom provider should have tests proving:

| Question | Required evidence |
| --- | --- |
| Does the provider support the right token type? | `supports` true/false with specific classes. |
| Does a request belong to another source? | `authenticate` returns null; next provider is called. |
| Invalid credentials in an owned source? | `BadCredentialsException` or corresponding authentication error. |
| Account locked/expired? | Appropriate `AccountStatusException`; no fallback. |
| Internal auth store broken? | `InternalAuthenticationServiceException` preserving cause; no fallback. |
| No provider handles the token? | `ProviderNotFoundException` from the manager. |
| Can a later provider override an earlier error? | Test proving the mechanism, plus evaluation of policy bypass risk. |
| Successful authentication? | `isAuthenticated()==true`, principal and authorities from server; later providers not called. |
| Do endpoints/handlers respond properly? | Separate tests for 401/403/503 and no leaked credentials, user enumeration, or stack traces. |
| Is production protected against dependency failures? | Timeouts, rate limits, secret-redacted logging, outage alerts, and no infinite retries. |

When reading logs, prioritize details like `Authentication` type, provider name, internal error code, timestamp, and request correlation ID. **Never log `getCredentials()` values, `Authorization` headers, password hashes, or real tokens.**

## 11. Key Takeaways

- **`return null`** = the provider **does not take responsibility for handling this instance**; the manager may proceed to another provider.
- **`throw BadCredentialsException`** = the provider checked and rejected the credentials; `ProviderManager` **may still try a later provider** and accept a subsequent success.
- **`throw AccountStatusException`** (e.g., `LockedException`, `DisabledException`) = invalid account state, **stops the chain immediately**.
- **`throw InternalAuthenticationServiceException`** = internal authentication failure, **stops the chain immediately**. General `AuthenticationServiceException` may continue along the normal exception branch.
- **`return authenticated Authentication`** = authentication succeeded, stops the chain; principal/roles must be server-verified.
- **System errors differ from wrong credentials**. Pick exception types and HTTP mappings with the right semantics, preserve causes, protect logs, and avoid falling back to weaker mechanisms during infrastructure outages.

### References

- Spring Security Reference — Authentication Architecture: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security 6.5 API — AuthenticationProvider: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/AuthenticationProvider.html
- Spring Security 6.5 API — ProviderManager: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ProviderManager.html
- Spring Security 6.5 API — AuthenticationServiceException: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/AuthenticationServiceException.html
- Spring Security 6.5 API — InternalAuthenticationServiceException: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/InternalAuthenticationServiceException.html
- Spring Security 6.5 API — AbstractUserDetailsAuthenticationProvider: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/dao/AbstractUserDetailsAuthenticationProvider.html
