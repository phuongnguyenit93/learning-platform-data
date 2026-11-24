# ProviderManager and the AuthenticationProvider List in Spring Security

> **Topic:** Spring Security → Authentication → **Authentication Engine**. This lesson explains the role of `ProviderManager`, how it iterates over the list of `AuthenticationProvider`s, the meaning of `supports(...)`, `authenticate(...)`, provider ordering, returning `null` or throwing errors, parent managers, credential erasure, event publishing, and how to configure/test safely. Java 17+ examples use Spring Security 6.5.x. The content focuses on **identity verification** mechanisms and does not replace resource authorization design.

## 1. Why Do We Need ProviderManager?

An application may accept multiple forms of proof for authentication: username and password from a form, a client's API key, an external bearer token, or credentials from an identity provider. Each type usually requires a different verification method. HTTP filters should not have to know every rule for verifying passwords, API keys, or tokens.

Spring Security separates responsibilities:

- **`Authentication`:** an object representing either an authentication request (untrusted) or an authenticated result, containing principal, credentials, authorities, and status.
- **`AuthenticationManager`:** an interface with the `authenticate(Authentication)` method, acting as the entry point for authentication requests.
- **`ProviderManager`:** the common implementation of `AuthenticationManager`, sequentially trying the configured `AuthenticationProvider`s.
- **`AuthenticationProvider`:** an implementation that knows how to authenticate one or more types of `Authentication`; for example, `DaoAuthenticationProvider` handles username/password via `UserDetailsService` and `PasswordEncoder`.
- **Filter/mechanism calling the manager:** such as `UsernamePasswordAuthenticationFilter` or an HTTP Basic filter, converting the request into an `Authentication` and calling the manager. On success, the caller attaches the result to `SecurityContext` according to the configured flow.

An application does not necessarily have only one `ProviderManager` or only one `SecurityFilterChain`. The exact wiring must be determined from the actual configuration.

```text
HTTP request
    │
    ▼
Appropriate Spring Security filter
    │ creates Authentication request (unauthenticated)
    ▼
AuthenticationManager.authenticate(request)
    │
    ▼
ProviderManager
    ├─ Provider #1: supports(request.getClass())?
    │      ├─ no → skip
    │      ├─ yes → authenticate(request)
    │      │          ├─ success → return Authentication, stop
    │      │          ├─ null → undecided, try next
    │      │          └─ AuthenticationException → see error handling rules
    ├─ Provider #2: evaluated in order
    ├─ Provider #3: evaluated in order
    └─ optional parent AuthenticationManager if no result yet
    │
    ├─ SUCCESS → authenticated Authentication
    └─ FAILURE → AuthenticationException
```

Note: **`ProviderManager` only selects and orchestrates the providers handed to it**. Checking passwords, tokens, user status, or credential validity resides in the corresponding provider.

## 2. The AuthenticationProvider Contract: supports and authenticate

`AuthenticationProvider` is an interface with two core methods:

```java
public interface AuthenticationProvider {
    Authentication authenticate(Authentication authentication)
            throws AuthenticationException;

    boolean supports(Class<?> authentication);
}
```

The code above shows the core signature, not a standalone runnable class.

### 2.1. supports(Class<?>) Selects the **Token Type**, Without Proving Valid Credentials

`supports(...)` returns `true` if the provider **is capable of examining** an `Authentication` object of the passed class. For example, a username/password provider usually supports `UsernamePasswordAuthenticationToken`; a provider dedicated to API keys will support a different token type.

```java
@Override
public boolean supports(Class<?> authenticationType) {
    return UsernamePasswordAuthenticationToken.class
            .isAssignableFrom(authenticationType);
}
```

This is a method snippet inside an `AuthenticationProvider` implementation. Using `isAssignableFrom(...)` supports compatible subtypes; `==` comparison is only appropriate when targeting **strictly one exact class**. Avoid having a provider declare support for every token type and then silently authenticate without proper checks.

**`supports(...) == true` does not mean the credentials are valid** and does not promise `authenticate(...)` will return a non-`null` result. It only indicates that the provider can inspect the request further at runtime.

### 2.2. authenticate(Authentication) Has Three Meaningful Outcomes

| Outcome from the invoked provider | Meaning | What does ProviderManager do? |
| --- | --- | --- |
| Returns a non-`null` authenticated `Authentication` | Provider achieved a successful result | Uses that result and does not call the remaining providers in the list |
| Returns `null` | Provider cannot decide for this specific instance | Continues to the next provider with matching `supports(...)` |
| Throws `AuthenticationException` | Provider identified an authentication error/failure | Typically records it and may continue; **certain error types stop immediately** |

Do not arbitrarily treat `return null` as a way to express “wrong password”. For credentials belonging to **an identity source the provider is responsible for**, invalid credentials should throw an appropriate error such as `BadCredentialsException`. `null` is used when the provider **genuinely cannot handle the specific case** and another provider is permitted by policy to handle it.

`authenticate(...)` itself must never return a trusted principal merely because the initial request set `authenticated=true` or self-declared authorities. Trusted attributes must be verified/issued by an appropriate authentication source.

## 3. Iteration Order: Understanding Behavior with Multiple Providers

Suppose `ProviderManager` receives the list:

```text
0. CorporatePasswordProvider
1. LocalPasswordProvider
2. ApiKeyProvider
```

For `UsernamePasswordAuthenticationToken`, both providers 0 and 1 can return `supports(...) == true`, while provider 2 only accepts a custom API-key token and is skipped. For an API-key token, the first two providers are skipped without calling `authenticate(...)`.

During a single `authenticate(request)` call:

1. The manager iterates in the **configured list order**, without automatically sorting by algorithm “priority”.
2. If `supports(request.getClass())` is `false`, that provider is skipped.
3. If `supports(...)` is `true`, the manager calls `authenticate(request)`.
4. If the provider returns `null`, the manager continues. If it returns a successful `Authentication`, the manager keeps the result and stops iterating.
5. An `AuthenticationException` is normally recorded, yet subsequent providers can still succeed; a later successful result supersedes the earlier error. If none succeed, the manager throws the last relevant authentication error.
6. If a provider throws `AccountStatusException` (such as account locked/disabled), the manager **stops immediately** and does not try subsequent providers. `InternalAuthenticationServiceException` is also treated as a fatal error in standard implementations and halts the flow.
7. If no provider returns a result, the manager may try a configured **parent AuthenticationManager**. If both local and parent paths fail to authenticate, the request fails; when no matching provider exists and no other error occurred, the result is typically `ProviderNotFoundException`.

**Essential security point:** configuring two providers that both accept username/password **can create a fallback path**. One provider throwing `BadCredentialsException` does not by itself guarantee the manager stops iterating; another provider might still allow login. If policy requires “corporate accounts must be authenticated by the corporate provider”, separate namespaces/token types or apply an explicit policy blocking fallback. Do not rely on accidental ordering.

### Illustrating Three Cases

```text
CASE A: request = local:mai / correct password
  Corporate.supports = true -> Corporate.authenticate = null (not in realm)
  Local.supports     = true -> Local.authenticate = SUCCESS
  ApiKey             = not tried
  Result             = success

CASE B: request = local:mai / wrong password
  Corporate.supports = true -> Corporate.authenticate = null
  Local.supports     = true -> Local.authenticate = BadCredentialsException
  ApiKey.supports    = false -> skipped
  Parent             = not configured
  Result             = BadCredentialsException

CASE C: request is a token type supported by no provider
  Corporate.supports = false
  Local.supports     = false
  ApiKey.supports    = false
  Parent             = not configured
  Result             = ProviderNotFoundException
```

**Do not confuse `ProviderNotFoundException` with a wrong password.** This error typically indicates that the `Authentication` type sent to the manager has no matching provider in the current list; a wrong password in a provider supporting username/password usually leads to `BadCredentialsException` or another specific error.

## 4. Exceptions That Decide Whether to Stop or Continue

| Case | Behavior to understand | How to handle |
| --- | --- | --- |
| `supports(...) == false` | Does not invoke that provider's `authenticate(...)` | Check the token class from the filter and provider registration |
| `authenticate(...) == null` | Undecided; manager tries next | Return null only when there is a valid delegation policy |
| `BadCredentialsException` | Normally next providers can still be tried; if none succeed, the request is rejected | Do not “fail open” to a weaker provider |
| `UsernameNotFoundException` | A type of authentication failure, does not mean the user is auto-created | Do not leak username existence; apply proper error-display policy |
| `DisabledException`/`LockedException` | Belong to the `AccountStatusException` family; must stop immediately | Do not open an alternate login path for locked accounts |
| `InternalAuthenticationServiceException` | Internal error in the authentication service; standard `ProviderManager` stops processing | Distinguish outages from wrong passwords, handle/alert safely |
| No supporting provider, no parent handles it | `ProviderNotFoundException` | Check provider configuration, token subtype, and which manager is being called |
| Provider returns successful `Authentication` | Stops iterating, returns result after post-processing steps | Only trusted providers may produce authenticated tokens |

**Note on parent:** a parent manager is an additional authentication path, not by default a “safe backup”. In a given configuration, the parent may be consulted when local providers yield no result, including some cases where a local provider failed; verify boundaries and policies to avoid an account from one realm being mistakenly authenticated by another.

## 5. Complete Java 17+ Example: Three Providers, Two Token Types

The example runs **without needing a Spring Boot web server**. Using Spring Security Core, we construct a `ProviderManager` with explicit ordering to observe `supports`, `return null`, successful results, wrong credentials, and an unsupported token. The code embeds dummy accounts/passwords and a fake API key for learning purposes; **never use literal comparison in production**.

### 5.1. Project Structure

```text
provider-manager-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/ProviderManagerDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'provider-manager-demo'
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
    mainClass = 'demo.ProviderManagerDemo'
}
```

`src/main/java/demo/ProviderManagerDemo.java`:

```java
package demo;

import java.util.Collection;
import java.util.List;
import java.util.Objects;
import java.util.stream.Collectors;

import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.ProviderNotFoundException;
import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

public class ProviderManagerDemo {

    public static void main(String[] args) {
        ProviderManager manager = new ProviderManager(List.of(
                new CorporatePasswordProvider(),
                new LocalPasswordProvider(),
                new ApiKeyProvider()
        ));

        System.out.println("-- password --");
        Authentication local = manager.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "local:mai", "local-pass"));
        show(local);

        System.out.println("-- api key --");
        Authentication api = manager.authenticate(
                ApiKeyRequest.unauthenticated("key-123"));
        show(api);

        System.out.println("-- wrong password --");
        try {
            manager.authenticate(
                    UsernamePasswordAuthenticationToken.unauthenticated(
                            "local:mai", "wrong"));
        } catch (BadCredentialsException ex) {
            System.out.println("failure: BadCredentialsException");
        }

        System.out.println("-- unsupported token --");
        try {
            manager.authenticate(
                    new TestingAuthenticationToken("tester", "unused"));
        } catch (ProviderNotFoundException ex) {
            System.out.println("failure: ProviderNotFoundException");
        }
    }

    private static void show(Authentication auth) {
        String authorities = auth.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .sorted()
                .collect(Collectors.joining(","));
        System.out.println("result: name=" + auth.getName()
                + ", authenticated=" + auth.isAuthenticated()
                + ", credentials="
                + (auth.getCredentials() == null ? "absent" : "present")
                + ", authorities=" + authorities);
    }

    // Only manages names belonging to the "corp:" realm.
    static final class CorporatePasswordProvider
            implements AuthenticationProvider {

        @Override
        public boolean supports(Class<?> authenticationType) {
            return UsernamePasswordAuthenticationToken.class
                    .isAssignableFrom(authenticationType);
        }

        @Override
        public Authentication authenticate(Authentication request) {
            String username = request.getName();
            if (!username.startsWith("corp:")) {
                System.out.println("corp: abstain");
                return null;
            }
            if (!Objects.equals(request.getCredentials(), "corp-pass")) {
                throw new BadCredentialsException("Invalid credentials");
            }
            System.out.println("corp: accepted");
            return UsernamePasswordAuthenticationToken.authenticated(
                    username, null,
                    List.of(new SimpleGrantedAuthority("ROLE_CORP")));
        }
    }

    // Only manages names belonging to the "local:" realm.
    static final class LocalPasswordProvider
            implements AuthenticationProvider {

        @Override
        public boolean supports(Class<?> authenticationType) {
            return UsernamePasswordAuthenticationToken.class
                    .isAssignableFrom(authenticationType);
        }

        @Override
        public Authentication authenticate(Authentication request) {
            String username = request.getName();
            if (!username.startsWith("local:")) {
                System.out.println("local: abstain");
                return null;
            }
            if (!Objects.equals(request.getCredentials(), "local-pass")) {
                throw new BadCredentialsException("Invalid credentials");
            }
            System.out.println("local: accepted");
            return UsernamePasswordAuthenticationToken.authenticated(
                    username, null,
                    List.of(new SimpleGrantedAuthority("ROLE_USER")));
        }
    }

    // Only supports ApiKeyRequest, does not handle username/password.
    static final class ApiKeyProvider implements AuthenticationProvider {

        @Override
        public boolean supports(Class<?> authenticationType) {
            return ApiKeyRequest.class.isAssignableFrom(authenticationType);
        }

        @Override
        public Authentication authenticate(Authentication request) {
            if (!Objects.equals(request.getCredentials(), "key-123")) {
                throw new BadCredentialsException("Invalid API key");
            }
            System.out.println("api: accepted");
            return ApiKeyRequest.authenticated("batch-job");
        }
    }

    // Demo token. Private constructor so only factory methods create states.
    private static final class ApiKeyRequest extends AbstractAuthenticationToken {
        private final String principal;
        private String credentials;

        private ApiKeyRequest(
                String principal,
                String credentials,
                Collection<? extends GrantedAuthority> authorities,
                boolean authenticated) {
            super(authorities);
            this.principal = principal;
            this.credentials = credentials;
            super.setAuthenticated(authenticated);
        }

        static ApiKeyRequest unauthenticated(String key) {
            return new ApiKeyRequest("pending-api", key, List.of(), false);
        }

        static ApiKeyRequest authenticated(String principal) {
            return new ApiKeyRequest(
                    principal, null,
                    List.of(new SimpleGrantedAuthority("ROLE_SERVICE")), true);
        }

        @Override
        public Object getPrincipal() {
            return principal;
        }

        @Override
        public Object getCredentials() {
            return credentials;
        }

        @Override
        public void eraseCredentials() {
            super.eraseCredentials();
            credentials = null;
        }
    }
}
```

From the directory containing `build.gradle`, run with a Java 17-compatible Gradle:

```bash
gradle run
```

If the project has a Gradle Wrapper, use `./gradlew run` (macOS/Linux) or `gradlew.bat run` (Windows). Only the stdout printed by the program (excluding Gradle build lines) will be:

```text
-- password --
corp: abstain
local: accepted
result: name=local:mai, authenticated=true, credentials=absent, authorities=ROLE_USER
-- api key --
api: accepted
result: name=batch-job, authenticated=true, credentials=absent, authorities=ROLE_SERVICE
-- wrong password --
corp: abstain
failure: BadCredentialsException
-- unsupported token --
failure: ProviderNotFoundException
```

### 5.2. Why Is the Output Correct?

- With username `local:mai`, `CorporatePasswordProvider.supports(...)` returns true because the token is of the username/password type; however `authenticate(...)` detects the wrong realm and returns `null`. `LocalPasswordProvider` continues, checks the simulated password successfully, and returns a token with `ROLE_USER`.
- When the local provider returns a non-`null` token, the manager stops; `ApiKeyProvider` is not invoked for this request.
- For `ApiKeyRequest`, both password providers return `supports(...) == false`. The manager only calls `ApiKeyProvider`, verifies the API key, and returns principal `batch-job`.
- With a wrong password, the corporate provider properly skips its non-matching namespace; the local provider throws `BadCredentialsException`; the API key provider does not support the token type and there is no parent, so the error is returned to the caller.
- `TestingAuthenticationToken` is a test-oriented token type unsupported by all three configured providers; the manager throws `ProviderNotFoundException`.
- Both successful results have `null` credentials because **the providers proactively omit credentials from the result token**. This is good practice for custom providers. Additionally, `ProviderManager` by default can call `eraseCredentials()` on results supporting `CredentialsContainer`; this example avoids relying on post-cleanup by not putting raw secrets in the result token.

**Important limitation:** the example intentionally uses hardcoded credentials to make the orchestration flow easy to follow. In real applications, **passwords** must be verified with `PasswordEncoder` and stored hashes via `DaoAuthenticationProvider`/`UserDetailsService`; **API keys** must be stored securely, compared appropriately, governed by expiration/revocation, and kept out of logs/source code. All authentication paths must run over HTTPS.

### 5.3. Modify It Yourself to Verify the Policy

1. Swap the order of `CorporatePasswordProvider` and `LocalPasswordProvider`. With separated namespaces and providers returning null in the right places, the success result stays the same while the order in which providers are called changes.
2. Change the request to `corp:an`/`corp-pass`. The corporate provider authenticates it directly and the local provider is not called; `ROLE_CORP` is granted.
3. Change the password of the `corp:an` request to an incorrect one. The corporate provider reports `BadCredentialsException`; analyze how a subsequent provider supporting the same token type might still continue. Do **not** modify the code to a fallback that accepts any password.
4. Temporarily remove `LocalPasswordProvider` from the list. Request `local:mai` has no provider able to authenticate it; because corporate returns null and API key does not support it, the expected result is `ProviderNotFoundException`.
5. Add a test recording the number of `authenticate(...)` calls per provider to assert that providers after a success are not invoked; do not log raw credentials.

These modifications are solely for learning the mechanics; do not alter security rules in production environments.

## 6. DaoAuthenticationProvider in Real-World Username/Password Systems

In real applications, you usually **do not need to rewrite a password-comparing provider**. For username/password, `DaoAuthenticationProvider` already provides a path supported by Spring Security:

```text
UsernamePasswordAuthenticationFilter / BasicAuthenticationFilter
    ↓
UsernamePasswordAuthenticationToken (unauthenticated)
    ↓
ProviderManager
    ↓
DaoAuthenticationProvider
    ├── UserDetailsService.loadUserByUsername(username)
    ├── checks disabled / locked / expired via UserDetails
    └── PasswordEncoder.matches(rawPassword, storedHash)
    ↓
UsernamePasswordAuthenticationToken (authenticated)
    └── principal is usually UserDetails; authorities from user source
```

Configuration example for **only the AuthenticationManager part**, using Spring Security 6.5.x; it can be placed in an appropriate Spring `@Configuration`. This is a snippet that needs bean imports/configuration added, **not a standalone Java file**:

```java
@Bean
AuthenticationManager authenticationManager(
        UserDetailsService users,
        PasswordEncoder passwordEncoder) {

    DaoAuthenticationProvider passwordProvider =
            new DaoAuthenticationProvider(users);
    passwordProvider.setPasswordEncoder(passwordEncoder);

    return new ProviderManager(passwordProvider);
}
```

This is an example of **explicitly constructing the manager**. When using Spring Boot, `SecurityFilterChain`/auto-configuration may already build or assemble an appropriate `AuthenticationManager`; do not declare an extra bean with the same function just to “have multiple providers”. And **do not assume declaring a `@Bean AuthenticationProvider` means every filter/manager automatically uses that bean**: verify how the bean is registered into the right filter chain's manager.

### When There Are Multiple Mechanisms

Suppose a system has both form login for internal accounts and a JWT Resource Server for APIs:

- Form login creates a `UsernamePasswordAuthenticationToken` request, which can go to `DaoAuthenticationProvider`.
- Bearer tokens from APIs are typically processed by `BearerTokenAuthenticationFilter` and a corresponding provider/manager, such as `JwtAuthenticationProvider`.
- Having two mechanisms in one application **does not automatically guarantee** they share the exact same `ProviderManager`. `SecurityFilterChain` and `AuthenticationManagerResolver` configuration (if present) determine the actual processing path.

Questions to answer from the configuration: which filter chain does the request enter, which filter builds what token, which manager is invoked, which providers of that manager return `supports(...) == true`, and how is the result placed into `SecurityContext`/session?

## 7. Parent AuthenticationManager: Controlled Reuse

A `ProviderManager` can point to a **parent `AuthenticationManager`**. This pattern is useful when multiple distinct provider sets share a common group of mechanisms:

```text
Web chain A ─> ProviderManager A [A1, A2] ──┐
                                           ├─ parent AuthenticationManager [P1, P2]
Web chain B ─> ProviderManager B [B1] ─────┘
```

The child manager tries local providers first. If there is no valid result yet and it did not hit an error requiring immediate termination, it can call the parent. The parent can be another `ProviderManager`, also with its own list of providers. This enables provider sharing while increasing the complexity of authentication boundaries.

**Design control:** the parent must not inadvertently treat credentials rejected in realm A as sufficient to log into realm B; a routing policy must be decided. If multiple managers share the same event publisher, watch out for duplicate events when requests traverse the parent. Do not fix authentication errors by adding a parent that “accepts everything” just to make an endpoint work.

## 8. After Successful Authentication: Credentials and Events

### 8.1. Credential Erasure

`ProviderManager` enables `eraseCredentialsAfterAuthentication` by default. If the result token implements `CredentialsContainer`, the manager calls `eraseCredentials()` after successful authentication to reduce how long raw passwords/secrets stay in memory or the session.

```java
// Intentional customization in special environments:
ProviderManager manager = new ProviderManager(providers);
manager.setEraseCredentialsAfterAuthentication(true);
```

This is an illustrative snippet requiring a `providers` variable holding the list of providers. `true` is already the default in standard `ProviderManager`; there is no need to set it again in typical configurations. **Setting false is discouraged** as a workaround for cache issues: if the same `UserDetails` reference is kept in both the cache and the result, `eraseCredentials` can affect the cached object, causing subsequent authentications to fail. Designing proper principal/cache copies and avoiding storing secrets in shared objects is a safer solution.

Custom tokens should return a result without secrets directly from the provider, and if they hold mutable sensitive state, they should support proper cleanup when `CredentialsContainer` is invoked. Never assume Spring Security cleans up every object, every reference, or every log.

### 8.2. Authentication Events

`ProviderManager` can use `AuthenticationEventPublisher` to publish success/failure events; for example, `DefaultAuthenticationEventPublisher` maps common exceptions to events. When creating a `ProviderManager` programmatically, the default publisher is a **no-op** implementation that publishes no events; to receive events, configure an appropriate publisher. With Spring Boot/HTTP security, wiring may differ and the active configuration must be inspected.

Events are useful for auditing and monitoring failed logins, but never log passwords, bearer tokens, API keys, or principal objects containing secrets. When using parent/child managers, avoid configurations that publish duplicate events.

## 9. Clearly Distinguishing Authentication and Authorization

`AuthenticationProvider` verifies **identity proof** and produces a valid `Authentication` with authorities. `AuthorizationManager` or `authorizeHttpRequests`/`@PreAuthorize` rules evaluate authorities along with context to decide access.

```text
Authentication request (credential)
      → ProviderManager / AuthenticationProvider
      → Authentication result (principal, authorities)
      → SecurityContext
      → AuthorizationManager decides permissions for the specific action
```

Do not put rules like “which orders a user can edit” inside a provider just because the provider already knows the username. Permissions based on resource, owner, or tenant should be evaluated at the proper authorization layer. A successful authentication result **does not mean** every endpoint is allowed; empty authorities can still be valid depending on the mechanism.

## 10. Testing and Diagnosing Failures in Order

### Minimum Test Matrix

| Test case | Expected outcome to observe |
| --- | --- |
| Token type supported by only one provider | Only that provider has `authenticate(...)` called |
| Two providers both support; earlier provider returns `null` | Later provider is tried |
| Earlier provider returns success | Later provider is not called |
| Earlier provider throws `BadCredentialsException`, later provider could succeed | Fallback policy must be verified; outcome depends on list and providers |
| Provider throws `LockedException` or `DisabledException` | Does not try later/parent provider as a bypass |
| No supporting provider, no parent | `ProviderNotFoundException` |
| Wrong credentials at matching provider and no provider succeeds | Authentication fails with appropriate `AuthenticationException` |
| Parent configured | Verify exactly when parent is called and identity boundaries |
| Successful token implements `CredentialsContainer` | Credentials are erased per config; not leaked into response/logs |
| Multiple `SecurityFilterChain`s configured | Request reaches the intended chain and manager |
| Custom publisher/parent | Events fired the expected number of times, no secret data exposed |

### How to Diagnose a Failed Login

1. **Verify HTTP route:** did the request enter the right `SecurityFilterChain`? Which matcher selected the chain? Which filter read the credentials?
2. **Verify token type:** did the filter create `UsernamePasswordAuthenticationToken`, `BearerTokenAuthenticationToken`, or a custom token? Do not guess from endpoint names.
3. **Verify actual manager:** which manager does the filter use? Is the bean in the application context actually attached to that chain?
4. **List providers in order:** what does each provider's `supports(token.getClass())` return? Which providers were invoked?
5. **Inspect each provider's result:** `null`, success, or exception? If an exception, which family does it belong to and does it halt immediately?
6. **Check parent:** is one configured, was it consulted, and is there any risk of out-of-policy fallback?
7. **After success:** are principal/authorities accurate, and how is the context saved/restored? Avoid confusing a 403 authorization error with a wrong password.
8. **Safe auditing:** log class/type, processing step, error code, and correlation ID; do not log passwords, API keys, access tokens, or raw `Authentication`.

You may enable DEBUG-level logging for Spring Security packages in a **controlled development environment** to trace the processing path, while reviewing what data gets logged, retention duration, and sensitivity. Turn off verbose logging after analysis, especially in environments containing real credentials.

## 11. Common Design Mistakes

1. **Assuming `supports=true` means authentication succeeded.** `supports` only checks capability by token type; credentials still must be verified.
2. **Returning `null` on wrong password in the sole provider responsible for a realm.** This can open the path to another provider; return semantically accurate errors and design controlled fallbacks.
3. **Believing `BadCredentialsException` always stops iteration.** `ProviderManager` can normally try subsequent providers; check the exception type and final outcome.
4. **Stacking multiple providers with the same token type without checking order.** Results and fallbacks may differ from intent, especially when user sources share overlapping usernames.
5. **Confusing `ProviderNotFoundException` with a non-existent user.** This indicates the manager/provider lacks support for the current token type, not that the user is invalid.
6. **Manually flipping the `authenticated` flag in a controller.** Bypasses credential verification. Only trusted providers may create authenticated results.
7. **Using one token type for all credentials without boundaries.** API keys and passwords have different semantics/lifecycles; create distinct tokens/detection logic when genuinely needed.
8. **Writing a custom provider checking passwords via string comparison.** In production, prefer `DaoAuthenticationProvider` + `UserDetailsService` + `PasswordEncoder`, storing strong password hashes.
9. **Not treating locked/disabled status as a blocking failure.** Avoid allowing a subsequent provider to “rescue” a locked account.
10. **Enabling multiple parent/child managers without checking events/auditing.** Can double-count success/failure, obscure the authentication source, or create hard-to-control fallback loops.
11. **Disabling credential erasure to fix a cache bug.** Risks keeping secrets in memory longer than necessary; fix the cache/reference design instead.
12. **Assuming registering a `@Bean AuthenticationProvider` always wires it into every filter.** Inspect the actual authentication manager of each filter chain.
13. **Putting the entire principal or credentials into responses/logs.** The principal may carry internal data or secrets; output only selected DTOs.
14. **Mixing authorization into providers and letting clients grant their own authorities.** Permissions must originate from verified data and be checked at the proper layer.

## 12. Reinforcement Exercises

**Exercise 1 — Trace diagram:** given `[A, B, C]`, write out the steps when A does not support the token, B supports it but returns `null`, and C returns success. State clearly which providers have `authenticate` called and when the loop stops.

**Exercise 2 — Same token type:** two providers both support `UsernamePasswordAuthenticationToken`. The first throws `BadCredentialsException`, and the second authenticates successfully. Explain why a manager can return success and what security conditions must be controlled to prevent wrong fallbacks.

**Exercise 3 — Account locked:** in a similar setup, the first provider throws `LockedException`. Predict the outcome and why subsequent providers must not be tried.

**Exercise 4 — Parent:** draw two `ProviderManager`s sharing a parent. Propose one valid example (sharing a controlled provider) and one risk (namespace collision or bypassing account lockouts). Write a test ensuring requests do not cross boundaries.

**Exercise 5 — Real system:** pick an application using username/password and a JWT API. Identify the exact filter → token class → manager → provider → SecurityContext for each request type; explain why it is not necessarily a single manager.

**Completion criteria:** be able to explain `supports`, the three outcomes from `authenticate`, ordered provider selection rules, parent managers, `ProviderNotFoundException`, `AccountStatusException`, credential erasure, and how to avoid unsafe fallbacks. Be able to run the Java demo and explain every line of output without reading the library's source code.

## 13. Official Documentation

- [Spring Security 6.5 — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): `AuthenticationManager`, `ProviderManager`, multiple providers, parent, and erasure.
- [Spring Security 6.5 — ProviderManager Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ProviderManager.html): iteration rules, exception handling, event publisher, and `eraseCredentialsAfterAuthentication`.
- [Spring Security 6.5 — AuthenticationProvider Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/AuthenticationProvider.html): `supports` and `authenticate`.
- [Spring Security 6.5 — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html): password hashing and `UserDetailsService`.
- [Spring Security 6.5 — Username/Password Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/index.html): filters, managers, and password login.
- [Spring Security 6.5 — Authorization Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/architecture.html): role of `GrantedAuthority` and `AuthorizationManager` after the authentication step.

Examples are pinned to the Spring Security **6.5.x** API for ease of verification. If your project uses Spring Security 7.x or a custom `AuthenticationManager`, consult the Javadoc/source of that version and implementation before inferring exception-handling rules, security defaults, or provider registration methods.