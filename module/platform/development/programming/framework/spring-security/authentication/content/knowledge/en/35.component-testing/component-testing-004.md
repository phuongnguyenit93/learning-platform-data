# Testing ProviderManager with Multiple AuthenticationProviders and Parent Managers in Spring Security

## 1. Why Test Multi-Provider Configurations?

In Spring Security, `AuthenticationManager` receives an untrusted `Authentication` and authenticates it. The widely used implementation in the Servlet stack is `ProviderManager`: it iterates through a list of `AuthenticationProvider` instances in order and can delegate to a **parent `AuthenticationManager`** if the providers at the current level do not produce an authenticated result.

When there is only one provider, testing "valid credentials allow login" may seem sufficient. With **multiple providers** and a **parent manager**, subtler security bugs emerge:

- An internal password provider fails, yet another provider accepts the same request under weaker rules.
- `supports(...)` is declared too broadly so a provider accepts the wrong token type; or too narrowly so the manager reports no suitable provider.
- A provider returns `null` as intended ("I do not handle this"), yet tests mistake it for an "invalid credentials" exception.
- `LockedException` or an authentication service failure improperly falls back to the parent, allowing lockout policies to be bypassed.
- The parent is invoked even though a child already authenticated successfully; authentication events are published twice or credentials are not erased.
- Unit tests rely solely on `MockMvc.with(user(...))`, skipping the entire real `ProviderManager` while still claiming the authentication chain was tested.

This lesson focuses on **component testing**: precisely verifying `ProviderManager.authenticate(...)`, `AuthenticationProvider.supports(...)`, `AuthenticationProvider.authenticate(...)`, outcomes or exceptions, ordering, and parent delegation. JUnit examples use Java 17+, Spring Security 6.5.x, JUnit Jupiter 5, and Mockito. A plain Java example at the end lets you observe first-success-wins without booting Spring Boot.

### After this lesson, you will be able to

1. Explain the flow **supports → authenticate → result/null/exception → parent → events/credential erasure**.
2. Write unit tests asserting **exact providers were called/not called**, rather than merely checking HTTP 200/401.
3. Test multiple providers supporting the same `Authentication`, providers supporting different token types, and timely parent delegation.
4. Distinguish `ProviderNotFoundException`, `BadCredentialsException`, `LockedException`, and `InternalAuthenticationServiceException`, and how each affects fallback.
5. Verify exception precedence when both child and parent fail.
6. Verify post-authentication credential erasure and the rule against duplicate event publishing.
7. Recognize when to expand into integration tests for `SecurityFilterChain`/login filters, password encoders, DAOs, or external IdPs.

**Baseline:** Spring Security **6.5.11** for Javadoc reference, Java 17+, Gradle/JUnit 5. If using Spring Security 7.x or another custom setup, cross-check the source/Javadoc and re-run the same regression suite. This section describes the **Servlet/blocking `ProviderManager`**, not reactive `ReactiveAuthenticationManager`.

## 2. Position of ProviderManager in the Authentication Architecture

```text
Incoming request
       |
       v
Authentication filter (form, Basic, Bearer, custom ...)
       |
       v
Unauthenticated Authentication token
       |
       v
AuthenticationManager.authenticate(authentication)
       |
       v
ProviderManager (child)
       |
       +--> Provider #1.supports(token.class)?
       |        false: skip
       |        true: authenticate(token)
       |              +--> Authentication: SUCCESS, stop
       |              +--> null: next provider
       |              +--> ordinary AuthenticationException: remember, continue
       |              +--> AccountStatusException / internal service error: STOP
       |
       +--> Provider #2 ...
       |
       +--> no local success -> parent AuthenticationManager, if present
       |
       +--> authenticated result or AuthenticationException
       |
       +--> erase credentials / publish events as configured
       v
Filter success/failure handling, SecurityContext/session, response
```

Do not invert responsibilities:

| Component | Responsibility |
| --- | --- |
| `Authentication` request | Carries principal/credentials/details to verify; typically `isAuthenticated() = false` initially |
| `AuthenticationProvider` | Determines whether it supports the **token type**; when called, verifies and returns an authenticated token, `null`, or an exception |
| `ProviderManager` | Coordinates **provider order**, handles results/exceptions, tries parent, erases credentials, and publishes events |
| Parent `AuthenticationManager` | Fallback mechanism at the manager level; can be another `ProviderManager` or custom implementation |
| `AuthenticationFilter` | Extracts credentials from HTTP, calls the manager, and handles success/failure |
| `SecurityContext` | Where the auth result is held/restored per request/session architecture |
| Authorization | Checks roles, authorities, scopes, and ownership **after** authentication is established |

**True unit testing:** you can instantiate `ProviderManager` directly via `new ProviderManager(...)` in JUnit without an HTTP request, application context, or database. This excels at isolating ordering and parent delegation; however, it also has limits: it does not verify filters, request matchers, sessions, or endpoints.

## 3. Four Methods and Data Types You Must Know

### 3.1. AuthenticationManager

```java
public interface AuthenticationManager {
    Authentication authenticate(Authentication authentication)
            throws AuthenticationException;
}
```

`AuthenticationManager` itself says nothing about how many providers exist; `ProviderManager` is the implementation that coordinates providers.

### 3.2. AuthenticationProvider

```java
public interface AuthenticationProvider {
    Authentication authenticate(Authentication authentication)
            throws AuthenticationException;
    boolean supports(Class<?> authentication);
}
```

In the interface contract:

- `supports(Class<?>) = false`: the manager **never calls `authenticate`** on that provider for the current request type.
- `supports(...) = true`: the provider **can inspect** the token type; it **does not promise** authentication will succeed. It can still return `null` so the next provider handles it.
- `authenticate(...)` returns **non-null `Authentication`**: the provider authenticated successfully; the manager picks the result and stops checking child providers.
- `authenticate(...)` returns `null`: the provider makes no decision; the manager continues.
- `authenticate(...)` throws `AuthenticationException`: authentication failed; how the manager proceeds depends on the **exception type**.

Never write a custom provider that returns an `Authentication` with `isAuthenticated=true` without verifying real credentials/issuer/challenge. `UsernamePasswordAuthenticationToken.authenticated(...)` objects in unit tests are controlled fixtures, not a production authentication mechanism.

### 3.3. ProviderManager constructors

Spring Security 6.5 supports:

```java
new ProviderManager(List.of(providerA, providerB));

new ProviderManager(List.of(localProvider), parentManager);

new ProviderManager(providerA, providerB);
```

The second constructor accepts `List<AuthenticationProvider>` and a parent `AuthenticationManager`. The parent is a **fallback authentication manager**, not `ApplicationContext.getParent()` or Java class inheritance.

Never configure both an empty provider list **and** a null parent: the manager requires at least one authentication source. Never put `null` inside the providers list. Order in the `List` is security-critical policy data.

### 3.4. Authentication tokens used in this lesson

We use `UsernamePasswordAuthenticationToken` for clarity:

```java
UsernamePasswordAuthenticationToken request =
        UsernamePasswordAuthenticationToken.unauthenticated(
                "alice", "demo-password");

Authentication accepted =
        UsernamePasswordAuthenticationToken.authenticated(
                "alice", "secret-that-will-be-erased",
                List.of(new SimpleGrantedAuthority("ROLE_USER")));
```

`unauthenticated(...)` is a **request fixture**; `authenticated(...)` represents a result verified by a provider. Spring Security 6.5 provides both factories. In tests, credentials are dummy strings, **not** real passwords or production secrets.

## 4. Multi-Provider Traversal Rules: First-Success-Wins, Not First-Error-Wins

### 4.1. Core behavior

Assume list `[P1, P2, P3]` and request type `UsernamePasswordAuthenticationToken`:

| P1 | P2 | P3 | Outcome |
| --- | --- | --- | --- |
| `supports=false` | success | not needed | P1 skipped, uses P2 |
| `supports=true, authenticate=null` | success | not needed | Uses P2 |
| `BadCredentialsException` | success | not needed | **Uses P2**; P1 error does not win |
| success | not consulted | not consulted | **Uses P1**, stops immediately |
| `BadCredentialsException("first")` | `BadCredentialsException("second")` | `null` | No success; **last exception** `"second"` is thrown (unless a parent changes the outcome) |
| `LockedException` | not consulted | not consulted | **Throws immediately** `LockedException` |
| `InternalAuthenticationServiceException` | not consulted | not consulted | **Throws immediately**, no fallback to next provider |
| all `supports=false` | — | — | No parent → `ProviderNotFoundException` |
| all `null` | — | — | No parent → `ProviderNotFoundException` when no exception occurred |

Two exception types require special attention:

- `AccountStatusException` and subclasses such as `LockedException`, `DisabledException`, `AccountExpiredException`, and `CredentialsExpiredException`: **do not continue trying other providers** once encountered.
- `InternalAuthenticationServiceException`: internal failure of the authentication service; **no fallback to another provider** because that could turn an outage into a bypass.

Ordinary `BadCredentialsException`, however, can still be handled by a later provider. This is by design in `ProviderManager`, so if two providers enforce different password rules, **provider ordering and token-type support policy are security concerns**, not just performance concerns.

### 4.2. Why can a BadCredentials exception be "overridden"?

Two providers can both support `UsernamePasswordAuthenticationToken`:

```text
P1: supports=true
    authenticate -> BadCredentialsException
           |
           v
P2: supports=true
    authenticate -> authenticated alice
           |
           v
ProviderManager -> authenticated alice
```

This **can be intentional** if each provider serves a safe identity domain with proper fallback rules. However, if P1 enforces a new password policy while P2 still accepts old/weak passwords, the result is a **security downgrade**. To block fallback in special states, use auditable policies/provider composition rather than "hoping an exception will stop the chain on its own".

### 4.3. `supports=true` does not mean "authenticated"

A provider returning `supports=true` and then `null` is completely valid; it says "I can evaluate this token class, but this specific request is not my responsibility." Tests should verify both phases: class-level support and content-level decision.

## 5. When Is the Parent AuthenticationManager Called?

A `ProviderManager` can have a parent, for example:

```text
ChildProviderManager
   +-- local username/password provider
   +-- local API-key provider
   |
   +-- parent AuthenticationManager
         +-- shared enterprise provider
         +-- shared emergency/account-policy provider
```

Execution rule in Spring Security 6.5: **if child-level providers have not returned an authenticated result**, the manager **can call the parent**. This covers:

1. No child provider `supports` the request type.
2. One or more child providers return `supports=true` but all return `null`.
3. A child provider throws an **ordinary `AuthenticationException`** and no child provider returns a successful result, giving the parent a chance to authenticate.

Case 3 is crucial: do not misinterpret "only when no provider supports it" as a strict rule that a `BadCredentialsException` always blocks the parent. The Javadoc and implementation of `ProviderManager` 6.5 allow trying the parent whenever no success has been produced yet, except on early-termination exceptions.

**The parent is not tried** if:

- A child provider returned a non-null `Authentication`.
- A child provider threw `AccountStatusException`.
- A child provider threw `InternalAuthenticationServiceException`.

### 5.1. Outcomes from the parent

| Local result | Parent result | Behavior to test |
| --- | --- | --- |
| No local result | Authenticated `Authentication` | Uses parent result |
| Local `BadCredentials` | Parent authenticated | Parent **can win**, request succeeds |
| No local result | Parent `BadCredentialsException` | Throws parent exception |
| Local `BadCredentials` "local" | Parent `BadCredentials` "parent" | Parent exception is the final error |
| Local `BadCredentials` | Parent `ProviderNotFoundException` | Parent "not handled" is ignored; preserves local exception |
| No local result or exception | Parent `ProviderNotFoundException` | With no prior local error, throws `ProviderNotFoundException` |

For **hierarchical managers**, a parent handles requests at a broader tier. It is **not inherently stricter than child providers**; a parent accepting weak passwords can still create a bypass when the child has strict policies. Define clearly who can fall back, for which token types, and across which realms.

### 5.2. A parent can be another ProviderManager

The Spring Security reference describes multiple child `ProviderManager`s sharing one parent—for instance, multiple `SecurityFilterChain`s with their own auth mechanisms sharing an enterprise provider. When testing, verify:

- Child A calls local provider A then parent; Child B calls local provider B then the same parent.
- Local A is never invoked in Chain B.
- Which authentication types the parent accepts and whether it shares account-lockout policies.
- Never wire parent/child into a **cycle**; that causes infinite recursion.
- Providers share thread-safe stores/dependencies if invoked concurrently.

## 6. Exception Precedence and Chain Termination: Common Test Pitfalls

### 6.1. ProviderNotFoundException vs BadCredentialsException

`ProviderNotFoundException` indicates the manager found no provider capable of authenticating the request type; it is a **configuration/capability error**, not proof that the user's credentials are wrong.

`BadCredentialsException` indicates credentials were rejected by a provider that inspected the request. If another provider or parent later returns an authenticated result, the manager can still succeed. Otherwise, the last exception may be thrown.

Therefore:

```java
// Do not treat every AuthenticationException as "wrong password".
if (exception instanceof ProviderNotFoundException) {
    // Check provider / token type / parent configuration.
}
```

This is an error-management snippet for illustration; **never** return detailed internal exceptions in HTTP responses to users.

### 6.2. AccountStatusException must terminate

`LockedException` extends `AccountStatusException`. If a provider has proof that an account is locked, letting another provider authenticate the same identity could break the lockout policy. `ProviderManager` stops the chain immediately when this exception is thrown.

Proper testing must assert:

- Exception class is `LockedException`.
- Provider 2 did **not** have `supports` or `authenticate` called.
- Parent `authenticate` was **not** called.

Asserting only "login failed" is too weak: a misconfiguration might throw an error at the end while still having invoked providers that should never have run.

### 6.3. InternalAuthenticationServiceException terminates

For example, the identity database fails or the AS/LDAP backend returns an inability to verify identity. If a provider turns an outage into `BadCredentialsException`, `ProviderManager` may keep trying other providers. Classify internal failures as `InternalAuthenticationServiceException` where appropriate. Unit tests must verify there is no fallback.

**Fail closed does not always mean returning 401 to the caller**: HTTP status/observability for outages is a separate concern; manager unit tests verify that **no authenticated `Authentication` is produced** and no unauthorized fallback queries run.

### 6.4. Ordinary AuthenticationException still continues

Do not use `LockedException` merely to force the chain to stop for every wrong password; that exception class carries specific account-status semantics. If policy dictates rejecting fallback because credentials "belong to realm A and were wrong", separate auth token types, manager routing, provider composition, or decide within a centralized provider rather than abusing exception semantics.

## 7. Preparing a JUnit 5 + Mockito Project

In a **Spring Boot 3.5.x project with the Gradle plugin**, Java 17+, add dependencies:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-test` provides JUnit Jupiter, Mockito, and assertions; `spring-security-test` helps when you need HTTP or security-context tests. The tests in Section 8 are pure **unit tests** of `ProviderManager`, requiring no Spring context, database, server port, or `MockMvc`.

If using Maven, use Spring Boot's dependency management and `spring-boot-starter-test` with `test` scope; configure Surefire for JUnit 5. Regardless of Gradle/Maven, **never** hard-code mismatched versions of `spring-security-core` and `spring-security-test` when a BOM manages them.

### 7.1. Directory tree

```text
src/
  main/
    java/...
  test/
    java/
      demo/
        security/
          ProviderManagerBehaviorTest.java
build.gradle
```

Tests construct real instances:

```java
ProviderManager manager =
        new ProviderManager(List.of(primaryProvider, secondaryProvider), parent);
```

Do not use `@SpringBootTest` when the goal is purely provider ordering: booting the entire context slows tests down, introduces unnecessary configuration dependencies, and obscures failures.

## 8. Complete JUnit 5 Suite: Multiple Providers and Parent

Place file **`src/test/java/demo/security/ProviderManagerBehaviorTest.java`**. The code uses **Java 17**, Mockito APIs from the Spring Boot test starter, and Spring Security 6.5. You can copy the file verbatim into a project with the dependencies from Section 7.

```java
package demo.security;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.mockito.InOrder;

import org.springframework.security.authentication.AuthenticationEventPublisher;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.InternalAuthenticationServiceException;
import org.springframework.security.authentication.LockedException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.ProviderNotFoundException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

class ProviderManagerBehaviorTest {

    private static final Class<UsernamePasswordAuthenticationToken> PASSWORD =
            UsernamePasswordAuthenticationToken.class;

    private static UsernamePasswordAuthenticationToken request() {
        return UsernamePasswordAuthenticationToken
                .unauthenticated("alice", "demo-password");
    }

    private static Authentication accepted(String principal) {
        return UsernamePasswordAuthenticationToken.authenticated(
                principal,
                "temporary-secret",
                List.of(new SimpleGrantedAuthority("ROLE_USER")));
    }

    private static AuthenticationProvider provider(
            boolean supportsPassword) {
        AuthenticationProvider p = mock(AuthenticationProvider.class);
        when(p.supports(PASSWORD)).thenReturn(supportsPassword);
        return p;
    }

    @Test
    void unsupportedProviderIsSkippedThenSecondSucceeds() {
        AuthenticationProvider first = provider(false);
        AuthenticationProvider second = provider(true);
        AuthenticationManager parent = mock(AuthenticationManager.class);

        when(second.authenticate(any(Authentication.class)))
                .thenReturn(accepted("alice"));

        ProviderManager manager =
                new ProviderManager(List.of(first, second), parent);
        Authentication result = manager.authenticate(request());

        assertTrue(result.isAuthenticated());
        assertEquals("alice", result.getName());
        verify(first, never()).authenticate(any(Authentication.class));
        verify(second).authenticate(any(Authentication.class));
        verifyNoInteractions(parent);
    }

    @Test
    void nullMeansDeclineAndLaterProviderCanSucceed() {
        AuthenticationProvider first = provider(true);
        AuthenticationProvider second = provider(true);

        when(first.authenticate(any(Authentication.class)))
                .thenReturn(null);
        when(second.authenticate(any(Authentication.class)))
                .thenReturn(accepted("bob"));

        ProviderManager manager = new ProviderManager(List.of(first, second));
        Authentication result = manager.authenticate(request());

        assertEquals("bob", result.getName());
        InOrder order = inOrder(first, second);
        order.verify(first).supports(PASSWORD);
        order.verify(first).authenticate(any(Authentication.class));
        order.verify(second).supports(PASSWORD);
        order.verify(second).authenticate(any(Authentication.class));
    }

    @Test
    void firstSuccessStopsWithoutConsultingSecondOrParent() {
        AuthenticationProvider first = provider(true);
        AuthenticationProvider second = provider(true);
        AuthenticationManager parent = mock(AuthenticationManager.class);

        when(first.authenticate(any(Authentication.class)))
                .thenReturn(accepted("first"));

        ProviderManager manager =
                new ProviderManager(List.of(first, second), parent);

        assertEquals("first", manager.authenticate(request()).getName());
        verify(second, never()).authenticate(any(Authentication.class));
        verify(second, never()).supports(any());
        verifyNoInteractions(parent);
    }

    @Test
    void badCredentialsFromFirstCanBeOverriddenBySecondSuccess() {
        AuthenticationProvider first = provider(true);
        AuthenticationProvider second = provider(true);
        when(first.authenticate(any(Authentication.class)))
                .thenThrow(new BadCredentialsException("first failed"));
        when(second.authenticate(any(Authentication.class)))
                .thenReturn(accepted("second"));

        ProviderManager manager = new ProviderManager(List.of(first, second));

        Authentication result = manager.authenticate(request());
        assertEquals("second", result.getName());
        verify(first).authenticate(any(Authentication.class));
        verify(second).authenticate(any(Authentication.class));
    }

    @Test
    void lastOrdinaryAuthenticationExceptionWinsWithoutParent() {
        AuthenticationProvider first = provider(true);
        AuthenticationProvider second = provider(true);
        when(first.authenticate(any(Authentication.class)))
                .thenThrow(new BadCredentialsException("first"));
        when(second.authenticate(any(Authentication.class)))
                .thenThrow(new BadCredentialsException("second"));

        ProviderManager manager = new ProviderManager(List.of(first, second));

        BadCredentialsException ex = assertThrows(
                BadCredentialsException.class,
                () -> manager.authenticate(request()));
        assertEquals("second", ex.getMessage());
    }

    @Test
    void lockedAccountStopsBeforeSecondProviderAndParent() {
        AuthenticationProvider first = provider(true);
        AuthenticationProvider second = provider(true);
        AuthenticationManager parent = mock(AuthenticationManager.class);
        when(first.authenticate(any(Authentication.class)))
                .thenThrow(new LockedException("locked"));

        ProviderManager manager =
                new ProviderManager(List.of(first, second), parent);

        assertThrows(LockedException.class,
                () -> manager.authenticate(request()));
        verify(second, never()).supports(any());
        verify(second, never()).authenticate(any(Authentication.class));
        verifyNoInteractions(parent);
    }

    @Test
    void internalAuthenticationServiceErrorStopsWithoutFallback() {
        AuthenticationProvider first = provider(true);
        AuthenticationProvider second = provider(true);
        AuthenticationManager parent = mock(AuthenticationManager.class);
        when(first.authenticate(any(Authentication.class)))
                .thenThrow(new InternalAuthenticationServiceException(
                        "identity service unavailable"));

        ProviderManager manager =
                new ProviderManager(List.of(first, second), parent);

        assertThrows(InternalAuthenticationServiceException.class,
                () -> manager.authenticate(request()));
        verify(second, never()).authenticate(any(Authentication.class));
        verifyNoInteractions(parent);
    }

    @Test
    void parentHandlesRequestWhenAllLocalProvidersDecline() {
        AuthenticationProvider first = provider(false);
        AuthenticationProvider second = provider(true);
        AuthenticationManager parent = mock(AuthenticationManager.class);

        when(second.authenticate(any(Authentication.class)))
                .thenReturn(null);
        when(parent.authenticate(any(Authentication.class)))
                .thenReturn(accepted("parent"));

        ProviderManager manager =
                new ProviderManager(List.of(first, second), parent);

        assertEquals("parent", manager.authenticate(request()).getName());
        verify(first, never()).authenticate(any(Authentication.class));
        verify(second).authenticate(any(Authentication.class));
        verify(parent).authenticate(any(Authentication.class));
    }

    @Test
    void parentMaySucceedAfterOrdinaryLocalFailure() {
        AuthenticationProvider local = provider(true);
        AuthenticationManager parent = mock(AuthenticationManager.class);

        when(local.authenticate(any(Authentication.class)))
                .thenThrow(new BadCredentialsException("local-reject"));
        when(parent.authenticate(any(Authentication.class)))
                .thenReturn(accepted("parent"));

        ProviderManager manager =
                new ProviderManager(List.of(local), parent);

        assertEquals("parent", manager.authenticate(request()).getName());
        verify(parent).authenticate(any(Authentication.class));
    }

    @Test
    void parentOrdinaryExceptionOverridesLocalException() {
        AuthenticationProvider local = provider(true);
        AuthenticationManager parent = mock(AuthenticationManager.class);

        when(local.authenticate(any(Authentication.class)))
                .thenThrow(new BadCredentialsException("local"));
        when(parent.authenticate(any(Authentication.class)))
                .thenThrow(new BadCredentialsException("parent"));

        ProviderManager manager =
                new ProviderManager(List.of(local), parent);

        BadCredentialsException ex = assertThrows(
                BadCredentialsException.class,
                () -> manager.authenticate(request()));
        assertEquals("parent", ex.getMessage());
    }

    @Test
    void parentProviderNotFoundPreservesEarlierLocalException() {
        AuthenticationProvider local = provider(true);
        AuthenticationManager parent = mock(AuthenticationManager.class);

        when(local.authenticate(any(Authentication.class)))
                .thenThrow(new BadCredentialsException("local"));
        when(parent.authenticate(any(Authentication.class)))
                .thenThrow(new ProviderNotFoundException("not found"));

        ProviderManager manager =
                new ProviderManager(List.of(local), parent);

        BadCredentialsException ex = assertThrows(
                BadCredentialsException.class,
                () -> manager.authenticate(request()));
        assertEquals("local", ex.getMessage());
    }

    @Test
    void noSupportingProviderAndNoParentThrowsProviderNotFound() {
        AuthenticationProvider local = provider(false);
        ProviderManager manager = new ProviderManager(List.of(local));

        assertThrows(ProviderNotFoundException.class,
                () -> manager.authenticate(request()));
        verify(local, never()).authenticate(any(Authentication.class));
    }

    @Test
    void resultCredentialsAreErasedAndRequestDetailsCopied() {
        AuthenticationProvider local = provider(true);
        when(local.authenticate(any(Authentication.class)))
                .thenReturn(accepted("alice"));

        UsernamePasswordAuthenticationToken incoming = request();
        incoming.setDetails("correlation-from-filter");
        ProviderManager manager = new ProviderManager(List.of(local));

        Authentication result = manager.authenticate(incoming);

        assertTrue(result.isAuthenticated());
        assertNull(result.getCredentials());
        assertEquals("correlation-from-filter", result.getDetails());
    }

    @Test
    void parentProviderManagerPublishesSuccessEventOnlyOnce() {
        AuthenticationProvider local = provider(false);
        AuthenticationProvider parentProvider = provider(true);
        when(parentProvider.authenticate(any(Authentication.class)))
                .thenReturn(accepted("parent"));
        AuthenticationEventPublisher events =
                mock(AuthenticationEventPublisher.class);

        ProviderManager parent =
                new ProviderManager(List.of(parentProvider));
        parent.setAuthenticationEventPublisher(events);

        ProviderManager child =
                new ProviderManager(List.of(local), parent);
        child.setAuthenticationEventPublisher(events);

        Authentication result = child.authenticate(request());

        assertTrue(result.isAuthenticated());
        verify(events, times(1))
                .publishAuthenticationSuccess(any(Authentication.class));
    }
}
```

### 8.1. How to run and what it means

```bash
./gradlew test --tests demo.security.ProviderManagerBehaviorTest
```

On Windows use `gradlew.bat test --tests demo.security.ProviderManagerBehaviorTest`. With a Spring Boot project and proper dependencies, expect **14 tests PASS**. There is no fixed business stdout from JUnit/Gradle because version/task logging varies; check that the test report records all 14 passing and **0 failed**.

**These tests use Mockito stubs** to isolate manager logic. They do not prove passwords were checked with BCrypt, that a real LDAP/IdP works, or that HTTP sessions/authorization are secure. Furthermore, the 9th test's purpose is to describe Spring Security 6.5 fallback behavior, **not to recommend for every system that `BadCredentials` should always fall back**.

### 8.2. Explaining the key assertions

- `verify(first, never()).authenticate(...)` proves `supports=false` causes the provider to be skipped.
- `InOrder` verifies provider 1 is evaluated before provider 2, rather than relying only on the resulting principal's name.
- `verify(second, never()).supports(any())` and `verifyNoInteractions(parent)` prove short-circuiting on success or `LockedException`; `supports` is not even queried further.
- `assertThrows(ProviderNotFoundException.class, ...)` distinguishes an unsupported request-type configuration from a "wrong password".
- `result.getCredentials() == null` verifies default credential erasure on the returned `Authentication`.
- `getDetails()` demonstrates the framework can copy details from the original request onto the result when the result has no details yet.
- The event publisher test uses **two real `ProviderManager` instances**. If the parent were merely a Mockito mock returning a result without publishing events, a test asserting "one event published by child" could draw the wrong conclusion.

### 8.3. Mistakes when copying the tests

1. Importing `AuthenticationProvider` from a different SDK's package.
2. Missing `mockito-core`/Boot test starter on the test classpath.
3. Mixing JUnit 4 `@Test` with Jupiter `@Test` when the build enables JUnit Platform.
4. Returning `UsernamePasswordAuthenticationToken.unauthenticated(...)` from a provider and expecting `isAuthenticated()==true`; must return an authenticated object **after** provider verification.
5. Stubbing `authenticate` in Mockito while forgetting `supports=true`: the manager will never call the stub.
6. Using a `HashSet` for providers and expecting deterministic order: `ProviderManager` takes a **`List`**, it does not sort.
7. Mocking `ProviderManager.authenticate` directly instead of instantiating a real one: the test only exercises Mockito, not manager logic.
8. Asserting exception messages in production is brittle when i18n/framework messages change; the lesson intentionally uses custom-thrown exceptions with fixed test messages.

## 9. Testing When Providers Support **Two Different Authentication Types**

Section 8 tests reused `UsernamePasswordAuthenticationToken` to focus on ordering, support/non-support, and parent delegation. In real systems, each provider may serve **a distinct authentication type** such as username-password, Bearer access token, X.509 pre-auth, or OTP.

What to test: `supports(Class<?>)` receives a **class**, not a request instance. Only after `supports` returns true does `authenticate(Authentication)` receive the instance to inspect credentials, username, issuer, and tenant.

### 9.1. Dedicated token to clarify type routing

Example defining a **custom request token** in a test file in the same package:

```java
package demo.security;

import java.util.Collections;

import org.springframework.security.authentication.AbstractAuthenticationToken;

public final class EmailCodeAuthenticationToken
        extends AbstractAuthenticationToken {

    private final String username;
    private final String code;

    public EmailCodeAuthenticationToken(String username, String code) {
        super(Collections.emptyList());
        this.username = username;
        this.code = code;
        super.setAuthenticated(false);
    }

    @Override
    public Object getCredentials() {
        return code;
    }

    @Override
    public Object getPrincipal() {
        return username;
    }
}
```

Save as `src/test/java/demo/security/EmailCodeAuthenticationToken.java`. This is only a **request token**; it neither verifies a real email code nor marks itself authenticated. Specifically, **never** call `setAuthenticated(true)` from client/controller code to "bypass" the manager; only a trusted provider may return an authenticated result.

A dedicated provider can declare:

```java
@Override
public boolean supports(Class<?> authentication) {
    return EmailCodeAuthenticationToken.class
            .isAssignableFrom(authentication);
}
```

The snippet above is an excerpt **inside a custom `AuthenticationProvider`**, not a standalone runnable file. It only classifies the type. `authenticate` must verify the code server-side, TTL, one-time/replay protection, account state, and rate limits, then return an authenticated `Authentication` or throw per policy.

### 9.2. Why test class-specific support?

If an OTP provider writes `supports(Authentication.class)` meaning "I handle any token type", or its `supports(Class<?>)` implementation always returns true, it could receive password tokens and act as an unintended fallback. Conversely, a provider using string conversion to check token type might reject subclasses. Use:

```java
EmailCodeAuthenticationToken.class.isAssignableFrom(authentication)
```

when you intend to accept the exact class/subclasses of the token you understand. However, accepting subclasses also carries risk if a subclass changes semantics; test accordingly. Do not force every provider to support `UsernamePasswordAuthenticationToken` just to reuse an existing form login.

### 9.3. Adding a classification test

In the test suite, create two mock providers: `passwordProvider` supporting `UsernamePasswordAuthenticationToken.class`; `emailCodeProvider` supporting `EmailCodeAuthenticationToken.class`. When sending an email code, verify `passwordProvider` never calls `authenticate` and vice versa. No HTTP server is needed to catch `supports` regressions.

## 10. Parent Manager: Designing Dedicated Tests for Shared Multi-Child Scenarios

Suppose an application has two areas: `/employee/**` and `/partner/**`, each with a specialized login provider, and both sharing a central identity provider:

```text
Employee AuthenticationManager
      |
      +-- employee-specific provider
      |
      +-------+
              |
              v
          Shared Parent
          +-- common identity provider
              ^
              |
      +-------+
      |
Partner AuthenticationManager
      |
      +-- partner-specific provider
```

A production test suite should verify:

1. Employee credentials accepted by the local employee provider → parent is not called.
2. Partner credentials accepted by the local partner provider → parent is not called.
3. Shared-identity credentials → local declines → parent accepts.
4. Wrong credentials belonging to the employee realm → decide whether fallback is allowed; it is **not** automatically safe for the parent to accept.
5. Account disabled/locked in the local or shared directory → cannot be bypassed via another provider.
6. Child A and Child B invoked concurrently → providers with shared dependencies are thread-safe; counters/metrics are accurate.
7. Multiple logins do not produce duplicate authentication success/failure events.
8. Each chain receives only its intended token types and security context; the parent must not infer permissions from an untrusted request path.

**A parent manager is not role inheritance.** When a child receives an `Authentication` from the parent, granted authorities remain the authentication/authorization mapping produced by that provider. Never automatically add `ROLE_ADMIN` just because fallback to the parent succeeded.

## 11. Testing Exception Precedence Across Child and Parent Levels

An implementation checking multiple realms can encounter multiple exceptions. Separate two questions:

- **Did any provider produce an authenticated result?**
- If not, **which exception was thrown and from where?**

Additional test table example:

| Child P1 | Child P2 | Parent | Outcome |
| --- | --- | --- | --- |
| Unsupported | Unsupported | Unsupported | `ProviderNotFoundException` |
| `null` | `null` | no parent | `ProviderNotFoundException` |
| `BadCredentials("A")` | `null` | no parent | `BadCredentials("A")` |
| `BadCredentials("A")` | `BadCredentials("B")` | no parent | `BadCredentials("B")` |
| `BadCredentials("A")` | `null` | Success | Success from parent |
| `BadCredentials("A")` | `null` | `BadCredentials("P")` | `BadCredentials("P")` |
| `BadCredentials("A")` | `null` | `ProviderNotFoundException` | `BadCredentials("A")` |
| `LockedException` | not called | not called | `LockedException` |
| `InternalAuthenticationServiceException` | not called | not called | Internal service error |
| Success | not called | not called | Success from first child |

Do not use HTTP status 401 to deduce which exact provider threw an exception: an `AuthenticationEntryPoint` or failure handler can map multiple exceptions to the same generic error body under anti-account-enumeration policies.

### 11.1. Special case with parent ProviderNotFound

If the parent throws `ProviderNotFoundException` while the child previously threw `BadCredentialsException`, the child manager may preserve the child's error. This is a detail to test against your Spring Security version, rather than assuming "parent error" always replaces the local exception.

### 11.2. Avoid tests that depend on log messages

The goal of component tests is **outcomes, ordering, and side effects**, not an internal log string like `"Authenticating request with..."` that can change. If tracing is needed, enable DEBUG/TRACE in the test environment with dummy credentials and never use real raw passwords/tokens.

## 12. Erasing Credentials After Authentication: Logic and Cache Traps

### 12.1. What does ProviderManager do by default?

After obtaining an authenticated result, `ProviderManager` calls `eraseCredentials()` by default if the returned `Authentication` implements `CredentialsContainer`. `UsernamePasswordAuthenticationToken` is one such class. This reduces how long raw passwords/credentials remain in memory/session.

```text
Provider result: principal=alice, credentials="temporary-secret"
        |
        v
ProviderManager authenticates
        |
        v
CredentialsContainer.eraseCredentials()
        |
        v
Returned Authentication: credentials=null
```

The `result.getCredentials() == null` test in Section 8 verifies this default.

### 12.2. Can be disabled, but should not be turned off lightly

Spring Security provides:

```java
ProviderManager manager = new ProviderManager(List.of(provider));
manager.setEraseCredentialsAfterAuthentication(false);
```

This is a real API, but **not a recommended default configuration**. Disabling credential erasure can leave passwords/raw tokens inside `SecurityContext` or the session. If an application intentionally retains a credential to call downstream services, review the delegation architecture and secret storage rather than keeping raw passwords indefinitely by default.

### 12.3. CredentialsContainer and cached UserDetails

If the principal/details/result contains an object implementing `CredentialsContainer` and that same object is cached/reused across requests, erasure can break reuse of the cached object (e.g., credentials become null on the cached principal). Spring Security documentation warns to design proper copy/immutable snapshots or cache policies rather than blindly disabling credential erasure to treat the symptom.

To test this scenario: use a real provider or a fixture principal implementing `CredentialsContainer`, verify erasure is called once on the returned result, and verify it does not accidentally wipe reusable source data. Never put real password hashes in test logs.

## 13. Authentication Events: Why Testing Parents Requires Care

`ProviderManager` supports `AuthenticationEventPublisher`. By default when you construct a manager directly in a unit test, the event publisher is a no-op implementation that emits no events; to test events you must **attach a publisher**:

```java
AuthenticationEventPublisher publisher =
        mock(AuthenticationEventPublisher.class);

ProviderManager manager = new ProviderManager(List.of(provider));
manager.setAuthenticationEventPublisher(publisher);
```

A `DefaultAuthenticationEventPublisher` in a Spring application maps common exceptions to failure events and publishes success events. However, event delivery is customizable; do not rely on a Mockito parent emitting events automatically when stubbing `authenticate`.

### 13.1. Details when a parent exists

Spring Security 6.5 avoids duplicate authentication events when a child manager receives a result or error from its parent. Therefore:

- **Unit testing with a mocked parent**: the mock only returns an `Authentication` and does not publish events itself; you cannot use emitted event counts to evaluate the full production pipeline.
- **Two real `ProviderManager` instances**: wire the publisher per your architecture and assert the final event count. Section 8's suite shares a mock publisher between parent and child to verify success events are not duplicated.
- **Custom parent**: know which manager is responsible for publishing; do not assume the child will emit events if a custom parent does not.
- **Failure events**: mapping exception classes to events can depend on the publisher; test the publisher implementation if audit/monitoring policies rely on event types.

Never write production code that manually publishes the same event in the provider, success handler, child manager, and parent manager without idempotency/correlation. A single login could be counted as multiple events or trigger multiple fraud alerts.

### 13.2. Safe testing with events

`verify(publisher, times(1)).publishAuthenticationSuccess(...)` checks counts at the unit level. In Spring `ApplicationContext` integration tests, you can use `@EventListener` or a test event collector to verify event counts and **log-safe** principal/metadata; never copy raw credentials into events.

## 14. ProviderManager Unit Tests vs AuthenticationProvider Unit Tests

To avoid mixing test layers:

| Test level | Primary subject | What to mock? | What is proven |
| --- | --- | --- | --- |
| `ProviderManager` unit test | Real manager | Stubbed providers/parent | Ordering, supports, null, exceptions, parent, erasure, events |
| `DaoAuthenticationProvider` unit test | Real DAO provider | `UserDetailsService`, optional `PasswordEncoder` | Password comparison, account locked/disabled/expired |
| Custom OTP provider unit test | Real provider | Token service/repository | TTL, one-time consumption, account check |
| JWT/opaque provider unit test | Real provider/manager | `JwtDecoder` / introspector | Token validation/claims per contract |
| Servlet filter integration | Real `SecurityFilterChain` | Stubbed external backend | HTTP request, filter calls, `SecurityContext`, success/failure handlers |
| End-to-end login | Full deployed app + IdP/DB | Few or no mocks for security-critical dependencies | Real login flow and business policies |

**Anti-pattern:** mocking `AuthenticationManager.authenticate(...)`, asserting the API returns 200, and calling it "testing `ProviderManager`". That test never runs `ProviderManager`. Conversely, manager unit tests without HTTP filters **do not prove** headers/cookies/CSRF/session fixation are handled properly.

### 14.1. Why doesn't MockMvc.with(user(...)) test authentication?

`SecurityMockMvcRequestPostProcessors.user("alice")` injects a mock principal onto the HTTP request, skipping password verification and provider traversal. It is very useful for testing **authorization**, but unsuitable if the goal is proving a parent `AuthenticationManager` was called.

To test HTTP auth flows, send real login requests or test the authentication filter with a real/stubbed provider chain and observe events/statuses/sessions; manager unit tests remain the best way to verify ordering.

## 15. Wiring Multiple Providers into a Spring Security App: Configuration and Testing

In a Servlet app, a `SecurityFilterChain` can use multiple authentication mechanisms, and Spring Security builds an internal `AuthenticationManager` from the DSL/configurers. When replacing the manager with a custom `ProviderManager`, scope it explicitly and test for side effects.

Example **fragment inside a configuration method** (not a standalone runnable project):

```java
@Bean
SecurityFilterChain filterChain(
        HttpSecurity http,
        AuthenticationProvider ldapProvider,
        AuthenticationProvider localPasswordProvider)
        throws Exception {

    AuthenticationManager sharedParent =
            new ProviderManager(List.of(localPasswordProvider));

    AuthenticationManager child =
            new ProviderManager(List.of(ldapProvider), sharedParent);

    http
            .authenticationManager(child)
            .authorizeHttpRequests(auth -> auth
                    .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults());

    return http.build();
}
```

**Warning:** this is an **illustrative structure**. LDAP/DAO providers must be configured and tested for real, and account-status policies must be consistent; calling `http.authenticationManager(child)` can affect other mechanism filters. If you register this manager under one `SecurityFilterChain`, do not assume it automatically becomes the global manager for every other chain.

Never add a "fallback `localPasswordProvider`" with weaker passwords than LDAP just to keep things running during a directory outage. When LDAP cannot verify credentials, the provider should report the appropriate service error and follow a defined outage runbook; otherwise, you accidentally introduce an **authentication bypass**.

### 15.1. Combining multiple filter chains

Suppose:

```java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                    .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
}

@Bean
@Order(2)
SecurityFilterChain webChain(HttpSecurity http) throws Exception {
    return http
            .authorizeHttpRequests(auth -> auth
                    .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .build();
}
```

This snippet is **not enough to wire full provider chains**; it only illustrates selecting a `SecurityFilterChain` per request. Shared parent/local manager configuration must be explicitly attached to chains if that is the desired architecture. Avoid assuming two `SecurityFilterChain`s automatically share all providers via one parent.

### 15.2. Selecting providers by token type instead of untrusted URLs

If an API uses Bearer tokens and browsers use form login, you can use **distinct `Authentication` types** with matching `supports(Class<?>)`. `ProviderManager` does not inspect request paths or HTTP headers on its own unless a filter places info into request details. Never rely on client-controlled `request.getParameter("provider")` to bypass a strict provider.

## 16. HTTP Integration with MockMvc: Testing Both Layers Properly

To prove integration works:

1. Configure a real `SecurityFilterChain` with form login/filters, authentication manager, and chosen providers.
2. With `MockMvc`, send `POST /login` using the exact method/form fields, including a CSRF token when enabled by default.
3. Assert login success/failure responses and the resulting `SecurityContext`.
4. Use Mockito `verify(...)` on providers/parent **injected into the real chain**, rather than mocking `AuthenticationManager.authenticate`.
5. Test anonymous users, locked users, unsupported providers, wrong passwords, and authenticated-but-forbidden requests.
6. Separate HTTP redirect/401 tests from provider exception-precedence tests; HTTP errors pass through failure handlers whose status codes depend on configuration.

Example **MockMvc fragment** (not a complete test file):

```java
mvc.perform(formLogin()
                .user("alice")
                .password("test-password"))
        .andExpect(authenticated().withUsername("alice"));
```

This uses `SecurityMockMvcRequestBuilders.formLogin()` and `SecurityMockMvcResultMatchers.authenticated()`, requiring static imports and a test context; the configuration must enable real form login. The `formLogin()` helper submits a form login request, **unlike** `with(user("alice"))` which pre-populates a principal.

For Basic auth APIs, `httpBasic("alice","password")` is a different helper. For Bearer tokens, send real request headers/tokens or use appropriate Resource Server tests; never use the `formLogin` helper for a Bearer API.

## 17. Spring WebFlux Does Not Use Servlet ProviderManager

WebFlux uses these types:

- `ReactiveAuthenticationManager` returning `Mono<Authentication>`.
- `DelegatingReactiveAuthenticationManager` allowing multiple reactive managers to be tried under Reactor semantics.
- A manager that cannot handle a request can return `Mono.empty()`, an auth failure returns `Mono.error(AuthenticationException)`, and success returns `Mono.just(Authentication)`.
- HTTP security uses `ServerHttpSecurity`, `SecurityWebFilterChain`, and `ReactiveSecurityContextHolder`.

**Never** take a Servlet `ProviderManager` and invoke blocking LDAP/JDBC directly on the Netty event loop. Reactive testing requires `StepVerifier`/Reactor Test and verifying composition/error semantics of `DelegatingReactiveAuthenticationManager` in your target version.

Example **directional snippet**, not a standalone program:

```java
ReactiveAuthenticationManager first = authentication -> Mono.empty();

ReactiveAuthenticationManager second = authentication ->
        Mono.just(UsernamePasswordAuthenticationToken.authenticated(
                "alice", null,
                List.of(new SimpleGrantedAuthority("ROLE_USER"))));

ReactiveAuthenticationManager delegating =
        new DelegatingReactiveAuthenticationManager(first, second);

StepVerifier.create(delegating.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "alice", "demo")))
        .assertNext(result -> assertTrue(result.isAuthenticated()))
        .verifyComplete();
```

This snippet requires Reactor `Mono`, `StepVerifier`, Spring Security Reactive interfaces, and JUnit assertions; it does **not** test Servlet `ProviderManager`. For complex reactive chains, verify terminal events and never call `block()`/`subscribe()` manually in production.

## 18. AuthenticationException, Authorization, and HTTP Status: Three Non-Uniform Layers

When `ProviderManager` throws `BadCredentialsException`, test code sees the exception type. When a request goes through HTTP:

- `UsernamePasswordAuthenticationFilter` typically invokes `AuthenticationFailureHandler`, which may redirect to `/login?error`.
- HTTP Basic may return `401` with `WWW-Authenticate: Basic`.
- Bearer Resource Server uses `BearerTokenAuthenticationEntryPoint` and RFC 6750 challenge semantics.
- Users who are **authenticated** yet lack permissions typically receive `403 Forbidden` from authorization/`AccessDeniedHandler`.

Therefore, manager tests **should not assert HTTP 401 or 302** — the manager knows nothing about HTTP responses. Conversely, observing HTTP 401 alone **cannot prove** child or parent providers were invoked in the right order.

To limit user enumeration, never return internal messages like `"alice locked after 5 attempts"` in public HTTP error bodies. Audit logs can record standardized reason codes without logging raw credentials.

## 19. Standalone Java 17 Exercise: Observing Fallback and First Success

The following plain Java program simulates provider/parent **decision logic**. It does **not** implement Spring Security interfaces, verify real passwords, or replace `ProviderManager`; use it to visualize ordering.

Save as `ProviderChainModel.java`:

```java
import java.util.List;
import java.util.Optional;

public class ProviderChainModel {

    record Request(String method, String identity) {}

    interface Provider {
        boolean supports(Request request);
        Optional<String> authenticate(Request request);
    }

    static String authenticate(
            Request request,
            List<Provider> providers,
            Provider parent) {

        for (Provider provider : providers) {
            if (!provider.supports(request)) {
                continue;
            }
            Optional<String> result = provider.authenticate(request);
            if (result.isPresent()) {
                return result.get();
            }
        }

        if (parent != null && parent.supports(request)) {
            return parent.authenticate(request).orElse("DENIED");
        }
        return "DENIED";
    }

    public static void main(String[] args) {
        Provider passkey = new Provider() {
            public boolean supports(Request r) {
                return "passkey".equals(r.method());
            }
            public Optional<String> authenticate(Request r) {
                return Optional.of("PASSKEY:" + r.identity());
            }
        };

        Provider localPassword = new Provider() {
            public boolean supports(Request r) {
                return "password".equals(r.method());
            }
            public Optional<String> authenticate(Request r) {
                return Optional.empty();
            }
        };

        Provider parentPassword = new Provider() {
            public boolean supports(Request r) {
                return "password".equals(r.method());
            }
            public Optional<String> authenticate(Request r) {
                return Optional.of("PARENT:" + r.identity());
            }
        };

        List<Provider> child =
                List.of(passkey, localPassword);

        System.out.println(authenticate(
                new Request("passkey", "alice"), child, parentPassword));
        System.out.println(authenticate(
                new Request("password", "bob"), child, parentPassword));
        System.out.println(authenticate(
                new Request("unknown", "carol"), child, parentPassword));
    }
}
```

Compile and run with JDK 17+:

```bash
javac ProviderChainModel.java
java ProviderChainModel
```

**Exact** stdout:

```text
PASSKEY:alice
PARENT:bob
DENIED
```

The example intentionally **does not model exception precedence, event publishers, credential erasure, or contexts**. Those aspects must be tested with real JUnit/`ProviderManager` as in Section 8, not inferred from a simplified model program.

### Extension exercise

Modify `parentPassword` so it only returns `Optional.of(...)` for identities in a specific realm, and update the test to ensure users outside that realm receive `DENIED`. Next, add a "service-error provider" to the model and simulate fail-closed behavior; compare how real `ProviderManager`'s `InternalAuthenticationServiceException` stops the chain, unlike `Optional.empty()`.

## 20. Multi-Layer ProviderManager Test Matrix

| # | Input/configuration | What must be asserted |
| --- | --- | --- |
| 1 | P1 supports=false, P2 success | P1 does not authenticate; P2 succeeds |
| 2 | P1 supports=true, returns null, P2 success | Ordering P1 → P2 |
| 3 | P1 success, P2 could also succeed | P2 is not consulted; P1 wins |
| 4 | P1 BadCredentials, P2 success | P2 wins per 6.5 semantics |
| 5 | P1 BadCredentials, P2 BadCredentials | Last exception P2 |
| 6 | P1 LockedException | Neither P2 nor parent called |
| 7 | P1 DisabledException | Neither P2 nor parent called |
| 8 | P1 InternalAuthenticationServiceException | Neither P2 nor parent called |
| 9 | All supports=false, no parent | `ProviderNotFoundException` |
| 10 | All return null, no parent | `ProviderNotFoundException` |
| 11 | Child unsupported, parent success | Parent is called |
| 12 | Child null, parent success | Parent is called |
| 13 | Child BadCredentials, parent success | Parent can win |
| 14 | Child BadCredentials, parent BadCredentials | Parent exception is thrown |
| 15 | Child BadCredentials, parent ProviderNotFound | Local exception preserved |
| 16 | Child LockedException, parent supports=true | Parent is not called |
| 17 | Child InternalAuthenticationServiceException, parent supports=true | Parent is not called |
| 18 | Child success, parent has side effects | Parent is not called |
| 19 | Password request type | Only providers supporting password receive `authenticate` |
| 20 | Custom OTP request type | Only providers supporting OTP receive `authenticate` |
| 21 | Authenticated token with credentials | `CredentialsContainer` erased by default |
| 22 | Authenticated token with request details | Details copied when result lacks details |
| 23 | Parent and child share publisher | Success event is not duplicated |
| 24 | Custom `AuthenticationEventPublisher` | Failure event types mapped per config |
| 25 | Cached `UserDetails` implements `CredentialsContainer` | Does not corrupt cache via credential erasure |
| 26 | Concurrent authentication requests | Providers are thread-safe; no principal mix-up |
| 27 | Two children share parent | Proper local/provider chain; no crossover |
| 28 | Auth type unsupported by all managers | Fail closed; never defaults to anonymous success |
| 29 | HTTP DTO invalid credentials | Protocol-compliant failure handler; no internal exception leak |
| 30 | Form login integration | Request traverses real manager, not just mocked principal |
| 31 | Bean wiring across versions | Provider/parent ordering in context matches design |
| 32 | Parent points back to child | No configuration cycle |
| 33 | External LDAP/DB timeout | Stops internally on service error instead of weak fallback |
| 34 | Account disabled at shared parent | No local provider re-enables against policy |

**QA principle:** both unit tests for coordination logic and integration tests for wiring/HTTP configuration are required. Never substitute a single happy-path test for negative cases covering exceptions, parent fallback, and credential handling.

## 21. Common Mistakes When Testing or Implementing

### `supports=false` yet test expects `authenticate` to be called

This is an invalid expectation. The manager checks types first; unsupported providers are skipped. If the provider should handle the request, fix `supports(Class<?>)` or the token type rather than forcing the manager to call `authenticate` directly.

### Parent is not called even though configured

Check whether a child provider already returned an authenticated result, whether `LockedException` or `InternalAuthenticationServiceException` terminated early, and whether the parent was actually passed into `ProviderManager(List, AuthenticationManager)` rather than merely existing as an unattached bean in the context. Verify with `verify(parent).authenticate(...)` when conditions are met.

### Parent is called after BadCredentials and accepts the password

That is part of standard manager behavior. Evaluate whether your fallback design is weaker than local policy. Do not fix it by faking `LockedException` for wrong passwords; separate realms/token types and design an authoritative policy that prevents downgrades.

### Expected ProviderNotFound but got BadCredentials

A provider may support the request type and return `BadCredentialsException`, or the parent may supply that error. `ProviderNotFoundException` only appears when no provider/manager authenticates and no other appropriate `AuthenticationException` applies. Assert matching configuration conditions.

### P1's `BadCredentialsException` is not thrown

P2 or the parent may have returned an authenticated result, causing the earlier exception to be discarded. This is why you must test the complete provider/parent ordering rather than mocking P1 alone.

### Locked account can still log in

If the provider checking account state is never reached, an earlier provider might succeed before the lock-checking provider runs. Alternatively, the provider may not throw a proper `AccountStatusException`. Enforce consistent account-status policies across all auth paths; never treat one provider's exception as a "global lock" if that provider is never invoked.

### Test always PASSES even when provider order changes

You may have mocked the manager instead of using a real one, or only asserted `isAuthenticated()` without checking `result.getName()`, `verifyNoInteractions`, and `InOrder`. Write fixtures with distinct principals/provider outcomes so ordering regressions fail immediately.

### Event is published twice or not at all

Inspect parent/child publishers and wiring. A manually instantiated `ProviderManager` defaults to a null publisher; if the parent is a mock, it will not actually publish events. Use two real `ProviderManager`s or an integration test listening to application events.

### UserDetails cache gets corrupted after authentication

`eraseCredentials()` can wipe fields on a shared `CredentialsContainer` object. Do not rush to set `setEraseCredentialsAfterAuthentication(false)`; inspect the cache model and copy-on-authentication behavior.

### Credentials remain in the session

Check whether the returned `Authentication` implements `CredentialsContainer` and whether custom providers return appropriate objects. Never log credentials before or after erasure in environments with real data.

### `@MockBean` or test fixture is never invoked

Verify Spring Boot/Test version, bean wiring, which real manager is attached to which `SecurityFilterChain`, whether the request hits the expected chain, and whether `with(user(...))` bypassed authentication. For unit tests not needing a Spring context, instantiate real objects directly to avoid confusion.

## 22. Production Readiness Checklist

1. **Token types:** list every `Authentication` subclass produced by filters, design type-safe `supports`, and test negative support cases.
2. **Provider order:** agree on `List` ordering and audit who is allowed to win when multiple providers support the same type.
3. **Fallback policy:** define explicitly when the parent is invoked after local non-success; never let a weaker realm accept credentials rejected by a stricter realm.
4. **Fail closed:** `AccountStatusException`/`InternalAuthenticationServiceException` stop the chain; providers must not turn outages into `BadCredentialsException` arbitrarily.
5. **Parent wiring:** parent must be wired explicitly, non-circularly, without relying on accidental bean names.
6. **Exception precedence:** test child/parent errors, `ProviderNotFoundException`, `null`, and last-exception behavior.
7. **Credentials:** returned tokens are marked authenticated only after real verification; `CredentialsContainer` erases secrets promptly; caches never hold mutated objects.
8. **Authentication events:** attach `AuthenticationEventPublisher` when needed for audit/monitoring and avoid duplicate publishing between parent and child.
9. **Separation of layers:** test `ProviderManager` separately; test DAO/LDAP/IdP separately; test filters/HTTP/login/CSRF/sessions separately.
10. **Thread safety:** providers/parent managers are shared across requests; never store current principals or credentials in mutable instance fields.
11. **Account security:** disabled/locked/tenant/issuer checks apply across **all** authentication paths, not just the last provider.
12. **Observability:** record provider ID/latency/result codes in trusted environments without logging raw passwords, tokens, session IDs, or exposing internal diagnostics in responses.
13. **Regression:** re-run the suite whenever changing provider order, adding mechanisms, upgrading Spring Security, or altering parent/child chain structures.
14. **Documentation:** document which provider is authoritative for which credential types and when fallback to a parent is permitted.

**Conclusion:** `ProviderManager` does not merely "pick one provider". It enforces an **ordered traversal policy**, allowing providers to abstain via `supports=false` or `null`, continuing past certain `AuthenticationException`s, terminating immediately on account-status/internal-service failures, optionally consulting a parent, and handling credentials/events on the result. To keep multi-provider setups safe, your test suite must **verify uncalled branches**, exception precedence, and parent fallback rather than asserting only successful logins.

## 23. Official Documentation

- [Spring Security 6.5 — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): Authentication, AuthenticationManager, ProviderManager, providers, and parent.
- [Spring Security 6.5.11 — ProviderManager API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ProviderManager.html): iteration, last exception, parent, `setEraseCredentialsAfterAuthentication`, and events.
- [Spring Security 6.5.11 — AuthenticationProvider API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/AuthenticationProvider.html): `supports`, `authenticate`, returning `null`.
- [Spring Security 6.5.11 — AuthenticationManager API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/AuthenticationManager.html): authentication invocation interface.
- [Spring Security 6.5.11 — UsernamePasswordAuthenticationToken API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/UsernamePasswordAuthenticationToken.html): `unauthenticated` and `authenticated` factories, credential erasure.
- [Spring Security 6.5 — Authentication Events](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/events.html): `AuthenticationEventPublisher` and failure/success event mapping.
- [Spring Security 6.5 — Servlet Authentication and Passwords](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html): DAO provider, `UserDetailsService`, PasswordEncoder, and account-status checks.
- [Spring Security 6.5 — Multiple SecurityFilterChains](https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html#_multiple_httpsecurity_instances): chain selection and `@Order`.
- [Spring Security — Test](https://docs.spring.io/spring-security/reference/servlet/test/index.html): `spring-security-test`, MockMvc helpers, and method/security testing.
- [Spring Security 6.5 — ReactiveAuthenticationManager API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ReactiveAuthenticationManager.html): `Mono.empty`, `Mono.error`, and reactive differences.
- [Spring Security 6.5 — DelegatingReactiveAuthenticationManager API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/DelegatingReactiveAuthenticationManager.html): composing reactive managers.
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): generic authentication error messages, lockout, anti-brute-force, and avoiding authentication bypass.
