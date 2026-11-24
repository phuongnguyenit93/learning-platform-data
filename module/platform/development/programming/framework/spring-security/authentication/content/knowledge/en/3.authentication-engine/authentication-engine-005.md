# Parent Manager and Conditions for Forwarding When a Child Manager Cannot Handle a Request

## Objectives and Context

In Spring Security, an `AuthenticationManager` receives an authentication request (an `Authentication` object) and either returns an authenticated identity or throws an `AuthenticationException`. The most common implementation is `ProviderManager`: it queries its `AuthenticationProvider`s in turn. A `ProviderManager` can also declare a **parent manager** (`parent AuthenticationManager`) to handle requests for which the child manager has not yet produced a successful result.

This lesson answers precisely **when a child manager calls the parent manager, when it stops immediately, and which result or exception is returned**. This is an orchestration mechanism of the authentication engine, not a role-inheritance rule or an automatic switch to another security filter chain.

After this lesson, you will be able to:

1. Distinguish `AuthenticationManager`, `ProviderManager`, `AuthenticationProvider`, and the parent–child relationship between managers.
2. Track how `supports(Class<?>)`, `null` values, successful authentication, and `AuthenticationException` groups affect the processing flow.
3. Understand why **`BadCredentialsException` from a child provider can still be processed onward by the parent manager**, whereas `AccountStatusException` and `InternalAuthenticationServiceException` stop immediately.
4. Predict outcomes when the parent succeeds, when the parent reports `ProviderNotFoundException`, or when the entire system has no handling provider.
5. Configure a `ProviderManager` with a parent, exercise the control branches with a Java 17+ example, and avoid fallback configurations that unintentionally allow authentication in the wrong identity domain.

The scope is Spring Security 6.x / Spring Boot 3.x, specifically how `ProviderManager.authenticate(...)` works. Core behavior is described based on the API contract and `ProviderManager` implementation; custom `AuthenticationManager`s may have different logic.

## 1. Parent–Child Model in the Authentication Engine

Three components to distinguish:

| Component | Responsibility | Examples |
| --- | --- | --- |
| `AuthenticationManager` | Interface receiving `authenticate(Authentication)`, returning an authenticated `Authentication` or throwing an exception | `ProviderManager`, custom manager |
| `AuthenticationProvider` | Verifies a specific token type or authentication method; declares `supports(Class<?>)` | `DaoAuthenticationProvider`, custom API-key provider |
| `ProviderManager` | Selects and tries providers in order; optionally forwards the request to a parent `AuthenticationManager` | Manager for a specific login area |

Diagram of a simple manager tree:

~~~text
Authentication request
         |
         v
  ProviderManager CHILD
    |-- Provider #1: supports? -> authenticate(...)
    |-- Provider #2: supports? -> authenticate(...)
    |-- ...
    |
    +-- If no valid result yet
          |
          v
    AuthenticationManager PARENT
          |
          +-- Another ProviderManager (if parent is also a ProviderManager)
          |      |-- Parent provider A
          |      +-- Parent provider B
          |
          +-- Successful result OR AuthenticationException
~~~

`parent` is an **optional** property of `ProviderManager`. It can be another `ProviderManager` or any `AuthenticationManager` implementation. Having multiple HTTP security chains in an application does not automatically guarantee that every chain shares a common parent; you must rely on the actual manager configuration.

Explicit initialization:

~~~java
AuthenticationManager parent =
    new ProviderManager(List.of(sharedProvider));

ProviderManager child =
    new ProviderManager(List.of(localProvider), parent);
~~~

This is an illustrative snippet placed in a method with two valid `AuthenticationProvider`s, `sharedProvider` and `localProvider`. The constructor accepts the child's provider list and the parent manager. A complete runnable example is in Section 5.

**Do not confuse:** parent–child managers **differ from** class inheritance, parent/child `ApplicationContext` relationships, and `FilterChainProxy` selecting a `SecurityFilterChain`. An HTTP request is typically handled only by the first matching chain; falling back to the parent inside the selected chain does not automatically route the request to a second chain.

## 2. Contract of Each AuthenticationProvider

Upon receiving an input `Authentication`, `ProviderManager` walks the `providers` list in order. For each provider:

1. Calls `provider.supports(authentication.getClass())`. If `false`, skips the provider; **does not call** its `authenticate(...)`.
2. If `true`, calls `provider.authenticate(authentication)`. This only means the provider can evaluate further, **not yet a guarantee it can authenticate the specific instance**.
3. The provider may return a **non-`null`** `Authentication`: the manager treats this as the authentication result, stops trying subsequent providers, and **does not call the parent**.
4. The provider may return `null`: “cannot decide/handle this request”; the manager moves to the next provider. If the list ends and there is still no result, the parent (if any) is tried.
5. The provider may throw `AuthenticationException`: whether to continue depends on the exception type; see Section 3.

Common misconception: `supports(...) == true` does not rule out `authenticate(...)` returning `null`. This is the mechanism documented in the `AuthenticationProvider` Javadoc.

### What Does a Non-Null Result Mean?

A provider must return an `Authentication` marked authenticated only after **verifying valid proof**. When the manager receives a non-null result, it does not invoke later providers or the parent manager to “authenticate a second time”. There is no concept of “the parent must always approve the child's success”. If a provider returns a wrongly authenticated token, the issue lies in that provider's implementation/trust policy.

`ProviderManager` can also copy details from the input token into an `AbstractAuthenticationToken` result if the result has no details yet, and by default erases sensitive credentials on a successful result if it implements `CredentialsContainer`. That is `ProviderManager` behavior, not evidence that the parent is guaranteed to be called.

## 3. Actual Conditions for Calling the Parent Manager

The central condition in the implementation can be paraphrased as:

~~~text
If result is still null after trying the child's providers
    AND child has a parent:
        try parent.authenticate(originalAuthentication)
~~~

This is an **algorithm description**, not Java code copied from the library. The key point is `result == null` after the loop, **not** “only when all providers have `supports == false`”.

Cases that lead to `result == null` include:

- None of the child's providers support the token class.
- One or more providers support the token, yet all return `null`.
- One or more providers throw a continuable `AuthenticationException`; afterward no provider returns success.
- A combination of the above: one provider returns null, another fails with a standard exception, and no result is produced.

Therefore, saying “the parent is only called if none of the child's providers support the token” is **too narrow**. It is also wrong to say “if the child fails, the parent is definitely always called”: there are exceptions that stop immediately, and the child might have no parent configured.

### 3.1. Standard Exceptions: Recorded, Then Continue

`BadCredentialsException`, a standard `AuthenticationException`, can occur if a child provider considers the username/password incorrect. In `ProviderManager`, standard exceptions are stored in a “last error” variable, yet the loop **continues trying subsequent providers**; if no child provider succeeds, the parent can be tried.

This has an important consequence:

~~~text
child provider: BadCredentialsException
remaining child providers: unsuccessful
parent manager: succeeds
=> final result: AUTHENTICATION SUCCEEDED
~~~

If a later provider or the parent succeeds, the earlier error does not determine the final outcome. This mechanism is useful when providers genuinely represent interchangeable valid authentication sources; it can also create a vulnerability if the parent acts as a “backdoor” accepting credentials the child intentionally rejected.

**Do not use `BadCredentialsException` expecting it to block all fallbacks by default.** Design clear credential domains, token types, and manager scopes if trying another source must not be permitted.

### 3.2. Immediate-Stop Exceptions: AccountStatusException

Exceptions extending `AccountStatusException` (e.g., `DisabledException`, `LockedException`, `AccountExpiredException`, and `CredentialsExpiredException`) cause `ProviderManager` to **throw immediately**. Remaining providers in the child are not called, and **the parent manager is not tried either**.

Meaning: once an account is known to be locked or disabled, execution must not continue trying other providers as if it were merely “undecided”. Never fake `LockedException` as a trick to control routing; it carries specific business semantics about account status.

### 3.3. Immediate-Stop Exception: InternalAuthenticationServiceException

`InternalAuthenticationServiceException` also causes `ProviderManager` to stop and throw immediately. For example, the identity source suffers an internal failure that cannot be classified as an invalid/missing account. Treating authentication service errors as a signal to “freely forward onward” could turn an outage into a bypass mechanism.

Non-`AuthenticationException` `RuntimeException`s in general are not a valid `ProviderManager` fallback mechanism either; do not expect the manager to swallow programming bugs and call the parent.

### 3.4. Decision Table at the Child

| Child behavior | Try next child provider? | Try parent if out of child providers? |
| --- | --- | --- |
| `supports(...) == false` | Yes, skip that provider | Yes, if no result yet and parent is configured |
| `supports(...) == true`, `authenticate(...) == null` | Yes | Yes, if still no result |
| Provider returns non-null `Authentication` | No | **No** |
| Provider throws `BadCredentialsException` or standard `AuthenticationException` | Yes | Yes, if no provider succeeds |
| Provider throws `AccountStatusException` | **No** | **No** |
| Provider throws `InternalAuthenticationServiceException` | **No** | **No** |
| Non-`AuthenticationException` programming error | No fallback rule | Must not assume parent will run |

When there are multiple providers, “next provider” means **the remaining providers in order that support the token class**, not that every provider has `authenticate` called.

## 4. After Calling the Parent, What Does the System Return?

The parent is called with the child's original input `Authentication`. It can have its own providers and even another parent, forming a multi-level tree; configurations should be designed without cycles.

Outcomes to distinguish:

| Parent outcome | Outcome from child ProviderManager |
| --- | --- |
| Parent returns non-null `Authentication` | **Success**, returns that authentication; earlier standard child errors are ignored |
| Parent throws `BadCredentialsException` or another `AuthenticationException` | When there is no successful result, the parent's exception is used as the last error and thrown |
| Parent throws `ProviderNotFoundException` | In `ProviderManager`'s implementation, this exception from the parent is ignored to preserve any exception already recorded in the child |
| Parent also has no matching provider and child recorded no error | Ends with `ProviderNotFoundException` |
| Child has no parent, no provider succeeds | Throws the last authentication exception, or `ProviderNotFoundException` if none occurred |

### 4.1. Easily Missed Detail: Parent's ProviderNotFoundException

Suppose a child provider supports the token yet throws `BadCredentialsException`. Meanwhile, the parent has no provider able to handle the token and throws `ProviderNotFoundException`. With standard `ProviderManager`, the “provider not found” error from the parent **does not overwrite** the `BadCredentialsException` already recorded from the child; the child's error can become the final failure result.

Conversely, if the child only encountered `supports == false` or `null`, recorded no error, and the parent cannot handle it either, the final outcome is `ProviderNotFoundException`.

`ProviderNotFoundException` describes a lack of support for **the authentication request type**; it does not necessarily mean the user's password is wrong. In HTTP APIs, the exact status depends on filters/entry points and exception mapping, rather than always deducing a single status solely from the exception class.

### 4.2. If a Later Provider Succeeds, Does the Earlier Error Still Matter?

The earlier error may still matter for internal logging or per-provider security observability, yet `ProviderManager` returns **final success** and does not throw that error. Do not build business logic assuming every `BadCredentialsException` from one provider will definitely appear in the HTTP response.

### 4.3. Authentication Events When a Parent Exists

`ProviderManager` supports `AuthenticationEventPublisher`. By default, its publisher emits no events unless configured. If both child and parent are configured to publish authentication events, watch out for duplicate events, especially on failure branches; the Javadoc recommends not configuring the parent to publish its own events in scenarios where duplication can happen. For auditing, identify **who owns event publishing** and test it in practice, rather than counting one `authenticate(...)` call as guaranteed to equal one event.

## 5. Runnable Java 17+ Example: Five Branches of Parent Fallback

The example below is **a command-line Spring Boot program creating no HTTP endpoints**. Its goal is to directly observe `ProviderManager` semantics. It uses simulated providers to precisely drive each branch; **it does not check real passwords and must not be used as a production login system**.

Generate a project from Spring Initializr with Java 17+, Spring Boot 3.x, Maven build, and the **Spring Security** dependency (no Spring Web needed). Place file `src/main/java/com/example/demo/ParentManagerDemoApplication.java`:

~~~java
package com.example.demo;

import java.util.List;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.LockedException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

@SpringBootApplication
public class ParentManagerDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ParentManagerDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner demonstrateFallback() {
        return args -> {
            AuthenticationProvider localProvider =
                new AuthenticationProvider() {
                    @Override
                    public Authentication authenticate(Authentication request) {
                        return switch (request.getName()) {
                            case "local" -> success("local", "ROLE_LOCAL");
                            case "fallback" -> null;
                            case "retry" ->
                                throw new BadCredentialsException("local rejected");
                            case "locked" ->
                                throw new LockedException("account locked");
                            default -> null;
                        };
                    }

                    @Override
                    public boolean supports(Class<?> type) {
                        return UsernamePasswordAuthenticationToken.class
                            .isAssignableFrom(type);
                    }
                };

            AuthenticationProvider sharedProvider =
                new AuthenticationProvider() {
                    @Override
                    public Authentication authenticate(Authentication request) {
                        System.out.println("PARENT tried: " + request.getName());
                        return switch (request.getName()) {
                            case "fallback", "retry", "locked" ->
                                success(request.getName(), "ROLE_SHARED");
                            default -> null;
                        };
                    }

                    @Override
                    public boolean supports(Class<?> type) {
                        return UsernamePasswordAuthenticationToken.class
                            .isAssignableFrom(type);
                    }
                };

            ProviderManager parent =
                new ProviderManager(List.of(sharedProvider));

            ProviderManager child =
                new ProviderManager(List.of(localProvider), parent);

            for (String username :
                List.of("local", "fallback", "retry", "locked", "unknown")) {
                demonstrateCase(child, username);
            }
        };
    }

    private static Authentication success(String name, String role) {
        return UsernamePasswordAuthenticationToken.authenticated(
            name,
            null,
            List.of(new SimpleGrantedAuthority(role))
        );
    }

    private static void demonstrateCase(
        ProviderManager child,
        String username
    ) {
        try {
            Authentication result = child.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                    username, "demo"
                )
            );
            String authority =
                result.getAuthorities().iterator().next().getAuthority();
            System.out.println(username + " -> OK / " + authority);
        }
        catch (AuthenticationException failure) {
            System.out.println(
                username + " -> " + failure.getClass().getSimpleName()
            );
        }
    }
}
~~~

### 5.1. How to Run

In the directory containing `pom.xml` generated by Initializr:

~~~bash
./mvnw spring-boot:run
~~~

On Windows PowerShell, use `.\mvnw.cmd spring-boot:run`. If choosing Gradle instead of Maven, the corresponding command is `./gradlew bootRun` (Windows: `.\gradlew.bat bootRun`).

Lines printed by the demo, **excluding Spring Boot startup logs**:

~~~text
local -> OK / ROLE_LOCAL
PARENT tried: fallback
fallback -> OK / ROLE_SHARED
PARENT tried: retry
retry -> OK / ROLE_SHARED
locked -> LockedException
PARENT tried: unknown
unknown -> ProviderNotFoundException
~~~

### 5.2. Explaining Each Invocation

**`local`:** child provider returns a successful authentication with `ROLE_LOCAL`. `ProviderManager` stops immediately; parent does not print `PARENT tried: local`.

**`fallback`:** child has `supports(...) == true` yet `authenticate(...) == null`. After local providers finish, the parent is called and returns `ROLE_SHARED`.

**`retry`:** child throws `BadCredentialsException`. `ProviderManager` records the standard exception yet continues. No child provider succeeds, so the parent is still called and succeeds. This example **intentionally highlights the risk of falling back after credentials were rejected**.

**`locked`:** child throws `LockedException`, which is an `AccountStatusException`. `ProviderManager` stops and throws immediately; even though the parent was written to accept username `locked`, it **is not called**. Consequently, there is no `PARENT tried: locked` line either.

**`unknown`:** local provider returns null, and parent also returns null. When no provider returns an authentication and no specific exception was retained, the final outcome is `ProviderNotFoundException`.

The example uses one provider in the child and one provider in the parent to show the flow clearly; you can add more providers to observe processing order. When doing so, remember that order in the `List` determines which provider is tried first and which can decide success.

### 5.3. Why Doesn't the Example Check Passwords?

Each `switch` in the demo intentionally selects outcomes by username to illustrate the contract. This is **not how to build a real provider**: `success(...)` creates an `authenticated(...)` token without verifying proof. In production applications, create a successful authentication only after verifying credentials, account status, and matching policies. For username/password, prefer proven mechanisms such as `DaoAuthenticationProvider` and an appropriate `PasswordEncoder`.

## 6. Further Simulation: Difference Between null and Wrong Password

Suppose child serves users in an internal system, while parent serves users in a shared identity source.

**Branch A — child does not know how to handle the token:**

~~~text
ChildProvider.supports(TokenX) == false
-> skip ChildProvider
-> parent is tried if no other result
~~~

This is where parent's valid scope should extend if parent supports `TokenX`.

**Branch B — child knows the token type yet the user does not belong to its domain:**

~~~text
ChildProvider.supports(TokenX) == true
ChildProvider.authenticate(request) == null
-> manager tries next provider / parent
~~~

Return null only when the provider genuinely **cannot decide** for that request. This is the “yield turn” contract, requiring clear distinction on verified data such as domain/issuer/tenant, avoiding routing logic based on self-declared headers.

**Branch C — child owns the identity yet the password is wrong:**

~~~text
ChildProvider.authenticate(request)
    throws BadCredentialsException
-> Manager may try next provider / parent
~~~

If product policy forbids authenticating this user via another source, **do not merely hope an exception stops fallback**. Design managers/chains and token types so the parent does not cross-accept the same rejected login credentials, or omit the parent for that authentication flow. Partitioning via dedicated `Authentication` token types when appropriate is usually clearer than trying to distinguish inside `supports` solely by username.

**Branch D — account is locked:**

~~~text
ChildProvider.authenticate(request)
    throws LockedException
-> ProviderManager stops and throws immediately
-> parent is not called
~~~

This is a property of `AccountStatusException`. Do not abuse status exceptions as an artificial `break` statement; if the account is not actually locked, messages and semantics become wrong.

## 7. Parent Manager in Applications with Multiple SecurityFilterChains

A structure you may encounter is:

~~~text
HTTP request
  -> FilterChainProxy
       |-- /api/** -> SecurityFilterChain API
       |                -> AuthenticationManager child-API
       |                   -> API-specific providers
       |
       |-- /admin/** -> SecurityFilterChain ADMIN
                        -> AuthenticationManager child-ADMIN
                           -> Admin-specific providers

child-API   ----+
                +----> Shared AuthenticationManager parent
child-ADMIN ----+      -> Shared providers
~~~

`FilterChainProxy` selects the **first matching chain** for the request. Once a filter in that chain calls `authenticate(...)` on the child manager, parent fallback logic takes place **within that chain's authentication process**. It does not ask `FilterChainProxy` to re-evaluate URL matchers or switch filters to another chain.

You can use a parent to share common authentication and children to add specialized mechanisms, but only when mechanisms are permitted to share the same trust boundary. Do not blindly connect all chains to one parent and assume admin/API endpoints are completely isolated: a parent accepting out-of-scope tokens can blur that separation.

With HTTP configuration DSLs, the methods and builders used to assemble managers depend on the specific Spring Security configuration. The `new ProviderManager(providers, parent)` example above is a **clear, direct, and testable** way to explore parent–child relationships; do not claim Spring Boot always builds this structure for you.

### 7.1. Separating Authentication Domains by Boundary

Suppose two user groups share identical usernames, yet belong to different identity stores. If both child and parent support `UsernamePasswordAuthenticationToken`, `supports(Class<?>)` only identifies **the token type**, not which group the username belongs to. Therefore, design so an internal account rejected by the child cannot unintentionally “log in” using the parent's data.

Ways to reduce confusion:

- Classify mechanisms by token class/issuer/trusted source; ensure the authentication request type and data source match the intended scope.
- Configure a parent only on child managers where fallback is genuinely allowed.
- Do not pass invalid credentials across multiple backends indefinitely; watch rate limiting, lockouts, auditing, and user enumeration protection.
- Test the flow **child provider fails + parent has valid credentials**, because this is the case most easily missed.
- Do not misuse `supports(...)` to verify credentials: it receives a **`Class`**, not a request instance or verified secret.

## 8. Common Mistakes and Diagnosis Guide

| Symptom | Possible underlying mechanism | How to check |
| --- | --- | --- |
| Assumed child returning `null` fails immediately | Parent is tried after all child providers yield no success | Check the actually configured parent and which tokens it supports |
| Child throws `BadCredentialsException` yet user still logs in | Later provider or parent succeeded | Trace provider ordering, identity store partitioning, test colliding accounts |
| Child returns authentication and parent is not called | Non-null result stops the manager | Normal behavior if child provider authenticated validly |
| Account is locked and parent does not run | `LockedException` belongs to `AccountStatusException` | Check early-stop flow and account policy |
| Auth infrastructure error occurs with no fallback | `InternalAuthenticationServiceException` stops immediately | Fix error source; do not turn internal errors into auth bypass |
| Final outcome is `ProviderNotFoundException` | No provider handles the token, or parent does not support it either | Check `supports(Class<?>)`, token class, and provider list |
| Client hit child error yet server reports a different error | Parent returned a new `AuthenticationException` | Identify the last error and filter/entry point mapping the response |
| Audit logs unexpected multiple events | Event publishers at multiple manager layers | Check ownership of `AuthenticationEventPublisher` |
| Successful token no longer holds password | `ProviderManager` erases credentials on `CredentialsContainer` after auth | Security default; do not rely on passwords remaining after login |

When debugging is needed, you can enable Spring Security logging at an appropriate level in test environments and set breakpoints at `ProviderManager.authenticate(...)`, `AuthenticationProvider.supports(...)`, and `AuthenticationProvider.authenticate(...)`. Never log passwords, bearer tokens, session cookies, or whole `Authentication` objects if they may contain secrets.

## 9. Self-Check Questions

**Question 1.** Child has two providers: P1 returns `null`; P2 throws `BadCredentialsException`; parent authenticates successfully. Result?

Answer: success from parent because no child provider returned a non-null result and this exception belongs to the continuable group.

**Question 2.** Child P1 throws `LockedException`, P2 can authenticate, and parent can also authenticate. Are P2 or parent called?

Answer: no; `LockedException` extends `AccountStatusException`, causing `ProviderManager` to stop immediately.

**Question 3.** Child throws `BadCredentialsException`; parent throws `ProviderNotFoundException`. Which exception is normally emitted by the child `ProviderManager`?

Answer: child retains the recorded `BadCredentialsException`; the parent's `ProviderNotFoundException` does not necessarily overwrite it. This is specific behavior of standard `ProviderManager`.

**Question 4.** Child provider's `supports(TokenA.class)` returns false, while parent has a provider supporting `TokenA`. Must it fail?

Answer: no. Child skips the unsupported provider and can delegate to parent; parent can authenticate successfully if the mechanism matches.

**Question 5.** Child returns an authenticated token, yet policy wants parent to verify further. Does parent run automatically?

Answer: no. A non-null result stops `ProviderManager`. If multi-step/multi-factor authentication is needed, design a flow with explicit verification steps; parent fallback is not a mandatory parent-approval workflow.

**Question 6.** If two security chains share a parent manager, does a request run through both chains?

Answer: no. Chain selection and calling a parent manager are two separate mechanisms. The first matching chain is chosen for the request; within that chain, authentication may use child then parent.

## 10. Checklist Before Using Parent Fallback in Practice

1. Is the parent actually configured on the child `ProviderManager`? Who instantiates and owns it?
2. Which `AuthenticationProvider`s can handle the incoming token type? What is their order?
3. Are `supports == false`, `authenticate == null`, and `BadCredentialsException` distinguished in tests?
4. Can a child provider reject credentials while the parent authenticates the same username from another source? Does that meet security requirements?
5. Do account status and internal service errors stop immediately as designed?
6. Are there tests for the parent throwing `ProviderNotFoundException` and both managers failing to handle the token?
7. Are API/admin/web security chains using the intended authentication managers and identity domains?
8. Are logging, event publishing, rate limiting, and credential erasure consistent when the result comes from the parent?
9. Are tests verifying actual provider ordering to catch behavioral shifts when new configuration is added?

**Core conclusion:** a parent manager is **a fallback when the child `ProviderManager` still has no authentication result** and a parent is configured. That condition can still hold after a standard `BadCredentialsException`. A non-null authentication result blocks fallback; `AccountStatusException` and `InternalAuthenticationServiceException` also block fallback by stopping immediately. Understanding these three branches accurately enables sharing authentication mechanisms without accidentally opening unauthorized login paths.

## References

- [Spring Security — Servlet Authentication Architecture / ProviderManager](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security 6.5 — ProviderManager API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ProviderManager.html)
- [Spring Security 6.5 — AuthenticationProvider API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/AuthenticationProvider.html)
- [Spring Security — Servlet Security Architecture / Multiple Filter Chains](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Security — ProviderManager source code](https://github.com/spring-projects/spring-security/blob/6.5.x/core/src/main/java/org/springframework/security/authentication/ProviderManager.java)
