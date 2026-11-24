# ProviderNotFoundException When No Matching Provider Exists

**Module:** Spring Security – authentication. **Knowledge group:** Authentication Engine.

## 1. Understanding the Exception Properly

`ProviderNotFoundException` is an `AuthenticationException` used by `ProviderManager` when **no authentication component can produce a result for the request's `Authentication` type** and there is no other authentication exception to throw instead. A typical message looks like:

~~~text
No AuthenticationProvider found for org.springframework.security.authentication.UsernamePasswordAuthenticationToken
~~~

The class name at the end of the message identifies **the `Authentication` object type** being processed. This exception usually indicates a **mismatch between the request token and `AuthenticationProvider`/`AuthenticationManager`**, rather than inherently meaning a wrong username, wrong password, or missing database user.

Easy example to picture: an application has `DaoAuthenticationProvider` to authenticate `UsernamePasswordAuthenticationToken`, yet a custom filter sends a different `Authentication` type into the same `ProviderManager`. With no provider for the new type, the manager has no way to verify credentials and throws `ProviderNotFoundException`.

**Distinguishing the terms:**

- **`Authentication`**: object describing an authentication request or result; e.g., `UsernamePasswordAuthenticationToken`, bearer/JWT request tokens, custom token types.
- **`AuthenticationProvider`**: component knowing how to evaluate **one or a few types** of `Authentication`.
- **`AuthenticationManager`**: API orchestrating the authentication process; `ProviderManager` is the standard implementation.
- **`ProviderNotFoundException`**: no appropriate authentication handler exists for the request passed into the manager. This is **not HTTP 404**, nor does it necessarily mean the Spring container is missing a bean.
- **`BadCredentialsException`**: a credential-handling path exists, yet the supplied credentials are invalid. The two exceptions point to two different diagnostic paths.

## 2. How Does ProviderManager Decide Which Provider to Pick?

`ProviderManager` takes an ordered list of `AuthenticationProvider`s. Each provider exposes two key methods:

~~~java
boolean supports(Class<?> authentication);

Authentication authenticate(Authentication authentication)
        throws AuthenticationException;
~~~

How to read the contract:

1. `provider.supports(request.getClass())` returns **false** → the manager **skips** that provider; does not call its `authenticate(...)`.
2. `supports(...)` returns **true** → the provider **is capable of evaluating** the token type; only then does the manager call `authenticate(...)`.
3. `authenticate(...)` returns a non-`null` `Authentication` → a result is produced; the manager stops iterating and returns that object (after success post-processing steps).
4. `authenticate(...)` returns **null** → the provider could not decide; the manager can try the next provider.
5. Provider throws `AuthenticationException` → the manager records the exception and depending on error type may keep trying other providers; `AccountStatusException` and `InternalAuthenticationServiceException` stop immediately in `ProviderManager`'s implementation.
6. If there is no local result and the manager has a **parent AuthenticationManager**, the parent is tried. If the parent returns a result, authentication can still succeed.
7. When no result is produced, if an appropriate `AuthenticationException` was recorded, the manager throws that exception; if no such error exists, the manager creates `ProviderNotFoundException`.

~~~text
Authentication request (e.g., UsernamePasswordAuthenticationToken)
                       |
                       v
             ProviderManager
                       |
      +----------------+----------------+
      |                                 |
 Provider A.supports(type)?       Provider B.supports(type)?
      |                                 |
     false                              true
      |                                 |
      v                                 v
     skip                  Provider B.authenticate(request)
                                           |
                              +------------+------------+
                              |                         |
                           result != null            null
                              |                         |
                              v                         v
                            SUCCESS             try next provider
                                                        |
                                                        v
                                         parent AuthenticationManager?
                                           |              |
                                         SUCCESS       not handled
                                           |              |
                                           v              v
                                        SUCCESS     prior error exists?
                                                      |       |
                                                     yes      no
                                                      |       |
                                                      v       v
                                             throw recorded error  ProviderNotFoundException
~~~

**Subtle point:** `supports(...) == true` **does not guarantee** login will succeed, nor even guarantee the provider can make a decision. The provider still has the right to return `null`. Thus “no provider could handle it” is broader than “no provider had `supports(...) == true`”.

Additionally, one provider might throw `BadCredentialsException`, while a subsequent provider authenticates successfully; in that case, the successful result supersedes the earlier exception. Conversely, when no provider succeeds and a matching authentication error already occurred, usually **the last exception** is returned rather than generating an extra `ProviderNotFoundException`. Never assume “wrong password always leads to ProviderNotFoundException”.

## 3. Conditions Causing ProviderNotFoundException

| Scenario | `supports(...)` | `authenticate(...)` | Final outcome if no parent/other provider |
| --- | --- | --- | --- |
| Every provider rejects the request type | All `false` | Not called | `ProviderNotFoundException` |
| Providers accept the request type yet all return `null` | At least one `true` | No provider decides | `ProviderNotFoundException` |
| A provider throws `BadCredentialsException` and no later provider succeeds | At least one `true` | Authentication error occurred | Typically `BadCredentialsException` |
| One provider returns a valid authenticated result | A provider `true` | Returns non-null `Authentication` | Success, no ProviderNotFoundException |
| Local providers yield no result, parent handles it | Local undecided | Parent returns result | Success |
| Local providers yield no result and parent also throws `ProviderNotFoundException` | No result | Nowhere resolves it | Ultimately `ProviderNotFoundException` if no higher-priority error |

**An empty provider list** must also be understood properly: `ProviderManager` normally requires at least one provider **or** a parent manager right at construction time. Calling `new ProviderManager(List.of())` without a parent can fail with a configuration check before ever reaching `authenticate(...)`; do not use that to simulate runtime errors.

## 4. Common Causes in Real Applications

### 4.1. Filter Creates the Wrong Authentication Type

For example, `DaoAuthenticationProvider` supports `UsernamePasswordAuthenticationToken`, yet a custom filter creates `TestingAuthenticationToken` or a `CustomOtpAuthenticationToken`. The manager only holds the Dao provider and therefore has nowhere to verify the new type.

~~~text
Custom filter -> CustomOtpAuthenticationToken
                      |
                      v
         ProviderManager [DaoAuthenticationProvider]
                      |
                      +-- supports(CustomOtpAuthenticationToken.class) = false
                      |
                      v
             ProviderNotFoundException
~~~

How to fix: If it truly is username/password, send the proper `UsernamePasswordAuthenticationToken.unauthenticated(username, password)`. If it is an OTP/magic link/custom device mechanism, create a **provider verifying that credential type** and register it on the right manager; never work around it by stuffing a new token into username/password when the semantics differ.

### 4.2. Provider Exists Yet Is Not Attached to the Running Manager

An application may declare an `AuthenticationProvider` bean, yet a manually constructed custom `ProviderManager` only receives other providers. Or there are **multiple `SecurityFilterChain`s**, and the current request's filter belongs to a chain whose `AuthenticationManager` differs from the one you are inspecting in configuration.

Therefore, trace the **manager actually invoked by the filter** and that manager's provider list, rather than merely checking “is there an AuthenticationProvider bean in the Spring Context”. Depending on configuration, a bean does not automatically become a provider in every manager/chain.

### 4.3. Incorrect `supports(...)` Implementation

When writing a custom provider, this is a common pattern:

~~~java
@Override
public boolean supports(Class<?> authentication) {
    return CustomOtpAuthenticationToken.class.isAssignableFrom(authentication);
}
~~~

This line means “the request type is `CustomOtpAuthenticationToken` or a subclass”. Reversing the `isAssignableFrom` argument order can skip valid subclasses or match an overly broad supertype.

Never write `return true` for every token type just to make the exception disappear. If a provider cannot decide on a token type, restrict `supports(...)` to the right type or return `null` per contract; a provider accepting every type and handling them loosely can break authentication boundaries.

### 4.4. Confusing Token Types Across Protocols

Form login may create `UsernamePasswordAuthenticationToken`; OAuth2 Resource Server handles Bearer tokens using the matching filter/provider chain (e.g., JWT provider). If custom code extracts a bearer token and wraps it into a username/password token, or sends a bearer request into a manager containing only a DAO provider, the configuration no longer aligns.

Not every `Authentication` implementation is handled by `DaoAuthenticationProvider`. Check the **exact object type** on the request and provider per the enabled mechanism.

### 4.5. Provider Matches the Type Yet Returns `null` on All Branches

By contract, `null` means “the provider cannot decide yet”; subsequent providers are allowed to try. If a custom provider returns `null` even when credentials are **clearly invalid** and no other provider exists, the result can be `ProviderNotFoundException`, masking the credential error.

For request types the provider is responsible for verifying and **knows for certain failed**, throw an appropriate `AuthenticationException` (such as `BadCredentialsException`), rather than returning `null`. Return `null` only when genuinely yielding the decision to another provider.

### 4.6. Missing or Unsuitable Parent AuthenticationManager

`ProviderManager` can delegate up to a parent if local providers yield no result. If the configuration relies on a parent yet no parent is wired, or the parent cannot handle the token type either, the error can still occur. However, **never add a shared parent as an arbitrary patch**: understand chain boundaries, identities, and authentication strategy before sharing managers.

## 5. Runnable Demo: Five Processing States

This Java 17 demo uses **Spring Security Core 6.5.11** in a standalone Gradle application. It illustrates:

1. DAO provider encounters an **unsupported token type** → `ProviderNotFoundException`.
2. Same manager receives **right token type + right password** → success.
3. Right token type + **wrong password** → `BadCredentialsException`.
4. Provider accepts the token type yet **returns null** → `ProviderNotFoundException`.
5. Child manager is undecided yet **parent manager** verifies it → success.

`TestingAuthenticationToken` is used **solely to model a mismatched Authentication type**; it is a testing class, not a token recommended for real logins.

Create directory:

~~~text
provider-lookup/
├── build.gradle
└── src/main/java/example/ProviderLookupDemo.java
~~~

**build.gradle:**

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.security:spring-security-core:6.5.11'
    implementation 'org.springframework.security:spring-security-crypto:6.5.11'
}

application {
    mainClass = 'example.ProviderLookupDemo'
}
~~~

**src/main/java/example/ProviderLookupDemo.java:**

~~~java
package example;

import java.util.List;

import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.ProviderNotFoundException;
import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.InMemoryUserDetailsManager;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

public final class ProviderLookupDemo {

    public static void main(String[] args) {
        PasswordEncoder encoder = new BCryptPasswordEncoder();
        var account = User.withUsername("mai")
                .password(encoder.encode("training-password"))
                .roles("READER")
                .build();
        var users = new InMemoryUserDetailsManager(account);

        DaoAuthenticationProvider dao = new DaoAuthenticationProvider(users);
        dao.setPasswordEncoder(encoder);
        AuthenticationManager manager = new ProviderManager(dao);

        // Case 1: DaoAuthenticationProvider does not support the testing token.
        System.out.println("supports.testing="
                + dao.supports(TestingAuthenticationToken.class));
        try {
            manager.authenticate(
                    new TestingAuthenticationToken("mai", "training-password"));
            System.out.println("case1=unexpected-success");
        } catch (ProviderNotFoundException expected) {
            System.out.println("case1=ProviderNotFoundException");
        }

        // Case 2: right token type; verify real password.
        System.out.println("supports.password="
                + dao.supports(UsernamePasswordAuthenticationToken.class));
        Authentication correct = manager.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "mai", "training-password"));
        boolean hasReaderRole = correct.getAuthorities().stream()
                .anyMatch(a -> "ROLE_READER".equals(a.getAuthority()));
        System.out.println("case2.user=" + correct.getName());
        System.out.println("case2.authenticated=" + correct.isAuthenticated());
        System.out.println("case2.reader=" + hasReaderRole);
        System.out.println("case2.credentialsErased="
                + (correct.getCredentials() == null));

        // Case 3: supports right type, yet wrong credential.
        try {
            manager.authenticate(
                    UsernamePasswordAuthenticationToken.unauthenticated(
                            "mai", "wrong-password"));
            System.out.println("case3=unexpected-success");
        } catch (BadCredentialsException expected) {
            System.out.println("case3=BadCredentialsException");
        }

        // This provider accepts UsernamePasswordAuthenticationToken
        // yet always yields the decision to another provider.
        AuthenticationProvider undecided = new AuthenticationProvider() {
            @Override
            public Authentication authenticate(Authentication request) {
                return null;
            }

            @Override
            public boolean supports(Class<?> type) {
                return UsernamePasswordAuthenticationToken.class
                        .isAssignableFrom(type);
            }
        };

        // Case 4: supports=true yet no result, no parent.
        AuthenticationManager onlyUndecided = new ProviderManager(undecided);
        try {
            onlyUndecided.authenticate(
                    UsernamePasswordAuthenticationToken.unauthenticated(
                            "mai", "training-password"));
            System.out.println("case4=unexpected-success");
        } catch (ProviderNotFoundException expected) {
            System.out.println("case4=ProviderNotFoundException");
        }

        // Case 5: child undecided yet parent handles it.
        AuthenticationManager child = new ProviderManager(
                List.of(undecided), manager);
        Authentication fromParent = child.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "mai", "training-password"));
        System.out.println("case5.parentFallback="
                + fromParent.isAuthenticated());
    }
}
~~~

**Run:** from the `provider-lookup` directory, using JDK 17+ and a compatible Gradle:

~~~bash
gradle -q run
~~~

If the project has a Gradle Wrapper, use `./gradlew -q run` (Windows: `gradlew.bat -q run`). Libraries will be downloaded on the first run when internet access and Maven Central are reachable.

**stdout printed by the program** (ignoring build tool logs if the environment enables extra logging):

~~~text
supports.testing=false
case1=ProviderNotFoundException
supports.password=true
case2.user=mai
case2.authenticated=true
case2.reader=true
case2.credentialsErased=true
case3=BadCredentialsException
case4=ProviderNotFoundException
case5.parentFallback=true
~~~

**Result explanation:**

- `supports.testing=false` confirms the DAO provider ignores `TestingAuthenticationToken`. With no other provider or parent, Case 1 raises `ProviderNotFoundException`. The password inside this token **was never verified by DAO**.
- `supports.password=true` shows the provider can process `UsernamePasswordAuthenticationToken`. The right password yields an authenticated result, user `mai`, and `ROLE_READER` from server-side `UserDetails`.
- `case2.credentialsErased=true` is `ProviderManager`'s default behavior after success when the result supports credential erasure, not the cause of a provider lookup error.
- `case3=BadCredentialsException` distinguishes a request of **the right type with wrong credentials** from an unsupported token type.
- `case4=ProviderNotFoundException` demonstrates **`supports=true` is not enough**: the provider returns `null` and nowhere else makes a decision.
- `case5.parentFallback=true` illustrates the parent manager handling the request when the child yields no result. The parent in the demo simply reuses the same DAO setup; real applications must enforce clear trust boundaries.

**Demo safety:** hardcoded passwords and in-memory users are solely for learning. Never use demo passwords, `TestingAuthenticationToken`, or a provider always returning null as a real login method. Never log raw credentials.

## 6. Debugging in Order to Pinpoint the Broken Link

### Step 1 – Identify the Authentication Class Passed into the Manager

Where the filter calls `authenticate(...)`, identify the exact class:

~~~java
// Illustrative snippet in filter/controller that already has variable "requestAuth".
// Log only the type name; DO NOT log credentials or token toString().
logger.debug("Authentication request type: {}",
        requestAuth.getClass().getName());
~~~

The message `No AuthenticationProvider found for ...` usually helps identify this class. Check whether the custom filter builds the right token for the configured login mechanism.

### Step 2 – Identify the Manager Actually Invoked

Find where the filter/controller obtains its `AuthenticationManager`. With multiple `SecurityFilterChain`s, inspect **request matchers, chain ordering**, and the local manager of the chain handling the request. A provider bean existing in the container **does not prove** it is inside the running manager's list.

If instantiating `new ProviderManager(...)` manually, inspect the exact list passed in. If relying on Spring Security configuration mechanisms, trace the providers registered for the corresponding chain/manager. When a parent exists, check the parent too.

### Step 3 – Check supports for the Exact Class

A limited check for debug/test environments:

~~~java
// Illustrative snippet; apply only when variable "manager" is genuinely
// the ProviderManager of the flow being diagnosed.
if (manager instanceof ProviderManager pm) {
    Class<?> type = requestAuth.getClass();
    for (AuthenticationProvider provider : pm.getProviders()) {
        logger.debug("Provider {} supports {}: {}",
                provider.getClass().getSimpleName(),
                type.getSimpleName(),
                provider.supports(type));
    }
}
~~~

If no provider returns `supports(type)`, add a provider handling **the right authentication mechanism**, or fix the filter to construct the right token type. If a provider has `supports=true`, check `authenticate(...)` behavior: non-`null` result, `null`, or throwing `AuthenticationException`.

### Step 4 – Compare Against the Actual Exception Occurring

| Symptom | Helpful inference | Next step |
| --- | --- | --- |
| `ProviderNotFoundException` with unexpected token name | Mismatch between token type ↔ provider, or manager has no provider registered | Check token class, supports, active manager |
| `ProviderNotFoundException` despite `supports=true` | Providers may have returned `null`, parent did not handle | Inspect custom provider's authenticate contract |
| `BadCredentialsException` | A provider verified yet credentials were invalid; sometimes hides missing-user info | Check password encoder, user data, password hash, and login flow |
| `LockedException`, `DisabledException`, other `AccountStatusException`s | Account status blocks login | Check account policy; do not add another provider to bypass it |
| `InternalAuthenticationServiceException` | Internal error during authentication, e.g., service dependency | Check root cause in backend, monitor dependencies |
| Missing `SecurityContext` after successful login | Distinct from provider lookup; may be a context/session persistence issue | Check SecurityContextRepository, session, success handler |

**Do not rely solely on HTTP status.** Whether the result is 401, 403, a form login redirect, or a custom response depends on `AuthenticationEntryPoint`, failure handlers, and security filters; `ProviderNotFoundException` does not map fixedly to “HTTP 404” or any single status.

### Step 5 – Verify with Meaningful Tests

At minimum, test the exact same manager used in production:

- Right token type, valid credentials → authenticated `Authentication`.
- Right token type, wrong credentials → appropriate authentication exception, no success token created.
- Unsupported token → `ProviderNotFoundException`.
- Multiple providers or parent → the right provider is actually selected per policy; wrong token types are not accidentally authenticated.

At the web tier, send requests through **the right filter chain** and verify login/401/redirect effects properly. Simply unit-testing a provider bean will not catch wrong manager wiring per chain.

## 7. Fixing by Root Cause, Avoiding “Quick Hacks” That Bypass Authentication

| Root cause | Proper fix |
| --- | --- |
| Filter sends wrong token type | Use a token matching the protocol and expected provider |
| Custom auth flow has no provider | Write a provider that genuinely verifies credentials, scopes `supports`, and registers into the manager used by the filter |
| Provider bean is not inside the manager/chain | Attach the provider to the right configuration or actual `ProviderManager`; check `SecurityFilterChain` order |
| `supports` implemented wrongly | Fix `isAssignableFrom`/token type, add tests for exact type and subclasses |
| Provider returns `null` despite owning responsibility | Return result on success, throw `AuthenticationException` when known to fail; yield only when genuinely undecided |
| Missing parent needed by design | Configure parent in a controlled manner; review domain and chain separation |
| System uses JWT/mTLS yet goes through DAO provider | Pick the right authentication mechanism and resource-server/X.509 provider for the enabled stack/config |

### Example Registering a Provider Properly in Spring Security Servlet

The following configuration snippet is **an integration illustration**, placed in a Spring Boot Servlet application with `spring-boot-starter-security`, `spring-boot-starter-web`, `UserDetailsService`, and `PasswordEncoder` dependencies. It is not a standalone Java program:

~~~java
@Bean
AuthenticationProvider passwordProvider(
        UserDetailsService users, PasswordEncoder passwordEncoder) {
    DaoAuthenticationProvider provider = new DaoAuthenticationProvider(users);
    provider.setPasswordEncoder(passwordEncoder);
    return provider;
}

@Bean
SecurityFilterChain web(HttpSecurity http,
                        AuthenticationProvider passwordProvider) throws Exception {
    http.authenticationProvider(passwordProvider);
    http.authorizeHttpRequests(a -> a.anyRequest().authenticated());
    http.formLogin(Customizer.withDefaults());
    return http.build();
}
~~~

Here `http.authenticationProvider(passwordProvider)` registers the provider with that chain's security builder; `formLogin` sends a compatible authentication type. Multi-chain applications must verify which `SecurityFilterChain` actually receives the request, and configure additional required components before production use (CSRF/session/entry point/password policy).

**Do not fix by** calling `UsernamePasswordAuthenticationToken.authenticated(...)` with a username/role from the client or assigning `SecurityContextHolder` directly without verifying credentials. That bypasses the authentication flow and creates an impersonation vulnerability.

## 8. Common Reasoning Mistakes and Safety Notes

1. **“Adding any `AuthenticationProvider` fixes the error.”** Only a provider supporting the right request type and wired into the right manager helps.
2. **“`supports=true` means the provider authenticated successfully.”** Wrong: the provider can return `null` or throw `AuthenticationException`.
3. **“`No AuthenticationProvider found` means DI couldn't find the bean.”** Not necessarily; the active manager may not use that bean or the token type does not match.
4. **“No providers in the constructor means the manager throws `ProviderNotFoundException` at runtime.”** Incorrect regarding constructor validation of `ProviderManager` without a parent.
5. **“Wrong password throws `ProviderNotFoundException`.”** With a properly matched DAO provider, it is usually `BadCredentialsException`.
6. **“To avoid errors, the provider should support every subclass of `Authentication`.”** No. That widens the trust scope beyond the intended mechanism.
7. **“Just catch `ProviderNotFoundException` and issue an anonymous/authenticated token so the API runs.”** No. Granting a trusted identity without verification is a security flaw.
8. **“Provider returns `null` to report wrong credentials.”** Should not be done; once credentials are known to be invalid, use an appropriate `AuthenticationException`.
9. **“Just fix the global `AuthenticationManager` bean.”** An application can have multiple chains, each with its own manager.
10. **“HTTP 404 is proof of `ProviderNotFoundException`.”** No. 404 represents an unfound HTTP resource, independent of the exception class semantics.
11. **“Log the entire `Authentication` for debugging.”** Dangerous because tokens can carry credentials/metadata. Log only class names, provider types, and controlled information.

## 9. Self-Check Questions

**Question 1.** `DaoAuthenticationProvider.supports(TestingAuthenticationToken.class)` returns `false`. If the manager holds only the DAO provider, is a valid password checked?  
**Answer:** No. The manager skips the provider due to **wrong token type**; with no other handling provider/parent, `ProviderNotFoundException` occurs.

**Question 2.** Two providers both have `supports(...) == true` yet both return `null`. The manager has no parent and no other exception occurred. Result?  
**Answer:** `ProviderNotFoundException`, because no provider reached a conclusion.

**Question 3.** Provider A throws `BadCredentialsException`, and a later provider B successfully authenticates the request and returns a non-null `Authentication`. Which exception is thrown?  
**Answer:** No exception is thrown in the final outcome; the manager returns B's result, except for exception types that force an immediate stop per contract.

**Question 4.** An application has two `SecurityFilterChain`s. One handles form login, the other handles bearer APIs. Should both default to the same manager?  
**Answer:** No. Inspect requirements, request matchers, and trust policies for each chain; each chain must have providers handling its intended token types and access rules.

**Question 5.** A custom provider bean already exists in the container yet `ProviderNotFoundException` still happens. What is the first thing to check?  
**Answer:** Whether the request goes through **the manager containing that provider** and whether `supports(request.getClass())` matches.

## 10. Official References

- [Spring Security – Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): `AuthenticationManager`, `ProviderManager`, and the provider chain.
- [ProviderNotFoundException – API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ProviderNotFoundException.html): exception conditions and relationship to `AuthenticationException`.
- [ProviderManager – API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ProviderManager.html): iterating providers, handling `null`, errors, parent, and credentials.
- [AuthenticationProvider – API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/AuthenticationProvider.html): `supports`/`authenticate` contract.
- [DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html): provider for username/password, `UserDetailsService`, `PasswordEncoder`.

**Remember:** When encountering `ProviderNotFoundException`, trace **`Authentication` type → manager actually handling the request → manager's providers → `supports(...)` → `authenticate(...)` → parent**. Fix the configuration and credential-mechanism mismatch; never skip identity verification just to make the exception vanish.
