# Testing AuthenticationProvider.supports and authenticate Outcomes in Spring Security

## 1. Objective: Test the Full Contract, Not Just a Single Login

In Spring Security Servlet, an `AuthenticationProvider` handles one or more specific `Authentication` types. Multiple providers can be assembled into a `ProviderManager`; therefore, component testing must verify **both methods together**:

~~~java
boolean supports(Class<?> authentication);

Authentication authenticate(Authentication authentication)
        throws AuthenticationException;
~~~

- `supports(...)` answers **can this provider inspect the given token type?** It does not verify username/password and does not guarantee that a subsequent `authenticate(...)` call will succeed.
- `authenticate(...)` has three outcome groups: **return an authenticated `Authentication`**, **return `null` to abstain and defer the decision**, or **throw `AuthenticationException` when authentication fails**.
- `ProviderManager` chains providers in order, checks `supports(...)` first, and handles `null`, success, or exceptions per the framework contract.

If you only test "right password returns user", you easily miss high-impact bugs: a provider accepting the wrong token type, `supports=true` yet throwing for another provider's request, treating `null` as a login failure, bypassing locked accounts, or accidentally retaining credentials inside the authenticated result.

This lesson belongs to **Component Testing**. Examples use **Java 17+, Spring Boot 3.5.x, and Spring Security 6.5.x**, focusing on testing the provider/manager layer with **JUnit 5 without starting a web server or ApplicationContext**. These contract rules also form the foundation for Spring Security 7, though always check the Javadoc matching your project version.

## 2. Relationship Between Authentication, Provider, and Manager

~~~text
Servlet authentication filter
    |
    | Authentication request
    |  (e.g. untrusted UsernamePasswordAuthenticationToken)
    v
AuthenticationManager (usually ProviderManager)
    |
    +-- Provider A: supports(Class)?
    |      |
    |      +-- false -> skip
    |      +-- true  -> authenticate(...)
    |                   +-- null -> ask next provider
    |                   +-- Authenticated Authentication -> use result
    |                   +-- AuthenticationException -> handle by error type
    |
    +-- Provider B: supports(Class)? ...
    |
    +-- parent AuthenticationManager (if present and fallback needed)
    |
    +-- final result: success OR AuthenticationException
    v
Filter/caller saves SecurityContext or returns HTTP response
~~~

**Responsibility boundaries:**

- `AuthenticationProvider` does **not** directly issue HTTP redirects, 401/403 responses, or persist `SecurityContext`. It checks a single authentication mechanism.
- `AuthenticationManager` coordinates providers and determines whether any provider actually authenticates successfully.
- The filter/caller is responsible for consuming the manager's result, populating `SecurityContext`, and managing HTTP/session state per the login flow.
- Authorization such as `hasRole("ADMIN")` runs after authentication; a successfully authenticated user can still be denied a resource due to insufficient permissions.

### 2.1. Request tokens and result tokens

Two factories on `UsernamePasswordAuthenticationToken` are helpful for testing:

~~~java
// Input from caller: NOT YET authenticated.
Authentication request =
    UsernamePasswordAuthenticationToken.unauthenticated(
        "alice", "password-from-user");

// Output created only after provider has verified proof:
Authentication result =
    UsernamePasswordAuthenticationToken.authenticated(
        "alice", null,
        List.of(new SimpleGrantedAuthority("ROLE_USER")));
~~~

Both snippets above are **illustrative fragments**, assuming appropriate Spring Security imports. `request.isAuthenticated()` is `false`, while `result.isAuthenticated()` is `true`.

In production, **never construct a trusted token directly from form input just to make a unit test pass**; an authenticated token must be produced by a trusted provider after verifying credentials and account status.

## 3. What Must the supports(Class<?>) Contract Verify?

The `AuthenticationProvider.supports(Class<?>)` Javadoc defines support for an **`Authentication` type**:

~~~java
@Override
public boolean supports(Class<?> authenticationType) {
    return UsernamePasswordAuthenticationToken.class
        .isAssignableFrom(authenticationType);
}
~~~

Meaning:

- `supports(UsernamePasswordAuthenticationToken.class) == true`.
- If `MyPasswordToken extends UsernamePasswordAuthenticationToken`, `supports(MyPasswordToken.class) == true` thanks to `isAssignableFrom(...)`.
- `supports(TestingAuthenticationToken.class) == false` if the provider does not accept that type.
- Do not use `authenticationType == UsernamePasswordAuthenticationToken.class` when you actually intend to support valid subclasses.
- Conversely, if the design is only safe for an **exact token class**, checking exact class equality can be intentional; make this explicit in tests and documentation.

**Do not reverse the direction of `isAssignableFrom`:**

~~~java
UsernamePasswordAuthenticationToken.class
    .isAssignableFrom(MyPasswordToken.class);   // true

MyPasswordToken.class
    .isAssignableFrom(UsernamePasswordAuthenticationToken.class); // false
~~~

Crucially: `supports(Class<?>)` only receives a **class**, not a username, password, session, or token instance; it is not the place to verify credentials. Proper behavior must be consistent for the same class under normal conditions and have no unnecessary side effects.

### 3.1. supports(true) can still return null

The Javadoc states clearly: a provider returning `true` **does not guarantee** it can handle a specific instance. For example, two providers may both handle `UsernamePasswordAuthenticationToken`, with each responsible for a different **realm**. Provider A can return `supports(type)=true` and then return `null` for an account belonging to realm B; `ProviderManager` will then try B.

This is completely different from **wrong credentials in a realm the provider actually owns**. If the password was checked and did not match, the provider should throw `BadCredentialsException`; it should not unconditionally `return null` merely to "let another provider try the password too".

## 4. Three Outcome Forms of authenticate(Authentication)

| Result | Contract | When appropriate | Testing |
| --- | --- | --- | --- |
| Non-null `Authentication` | Provider verified and produced a complete, trusted result | Correct credentials, valid account | `assertTrue(isAuthenticated())`, principal, authorities, credentials |
| `null` | Provider **cannot decide** on this request | Request belongs to another realm/mechanism despite same token class | `assertNull(...)` and test `ProviderManager` fallback |
| `AuthenticationException` | Provider attempted authentication and failed | Wrong password, locked/expired account, provider error | `assertThrows(...)` exact subclass and manager outcome |

### 4.1. What must a successful result contain?

Typically the provider returns:

- `isAuthenticated() == true` **only after trustworthy verification**.
- Principal matching the verified user, not blindly trusting the client-entered username.
- `GrantedAuthority` loaded from a verified authority source, never trusting roles from client JSON.
- Unnecessary credentials set to `null` to avoid pushing passwords back into session/cache.
- Appropriate details/audit metadata, without logging raw passwords or Bearer tokens.

If a provider returns a non-null object **that is not yet authenticated**, that is a suspicious result: `ProviderManager` treats non-null as a decision having been made and may stop trying other providers. Tests must assert `isAuthenticated()`, not just `assertNotNull(...)`.

### 4.2. Returning null does not mean authenticated=false

`null` means **"I take no responsibility for authenticating this request"**—it is not an anonymous token, not a user with a wrong password, and not an immediate 401 from the provider.

For a request not yet handled successfully by any provider, if **all providers are skipped or return `null`**, `ProviderManager` typically throws `ProviderNotFoundException` (when there is no succeeding parent). Distinguish token-support configuration errors from invalid credentials.

### 4.3. Throwing AuthenticationException

Typical classes:

- `BadCredentialsException`: invalid credentials.
- `LockedException`, `DisabledException`, `AccountExpiredException`: account status errors; all belong to `AccountStatusException`.
- `CredentialsExpiredException`: expired credentials, also an account status exception.
- `AuthenticationServiceException` / `InternalAuthenticationServiceException`: authentication/service processing error; should not be treated as "wrong password".
- `ProviderNotFoundException`: no matching provider in the chain (typically thrown by the manager).

A good unit test asserts the **exception class** and security invariants, rather than asserting exact message text that the application may change for i18n, and avoids exposing internal details to clients.

## 5. How Does ProviderManager Process Outcomes in Order?

Per the Spring Security 6.5 Javadoc:

1. A provider with `supports(type)=false` **is skipped**; its `authenticate` method is never called.
2. A provider with `supports=true` returning `null`: the manager **tries the next provider**.
3. A provider with `supports=true` returning a **non-null** result: the manager **stops**, uses the result, and does not try subsequent providers.
4. A provider throwing `BadCredentialsException` or an ordinary `AuthenticationException`: the manager can **try the next provider**; if a later provider succeeds, that success is used and the earlier error does not win.
5. A provider throwing `AccountStatusException` (e.g., `LockedException`): the manager **stops immediately** without consulting further providers. This is a critical security invariant: a locked account must not "fall through to another provider" to bypass controls.
6. If no provider succeeds but an ordinary exception occurred, **the last exception is thrown** in actual execution order.
7. If no provider authenticates and no appropriate exception was thrown, typically `ProviderNotFoundException`.
8. If a **parent `AuthenticationManager`** is configured, it can be tried when child providers fail to decide successfully; test the fallback path explicitly.

Certain severe system errors such as `InternalAuthenticationServiceException` also follow fail-fast handling in the relevant implementation; do not design fallback behavior during an IdP/DB outage assuming the manager ignores all exceptions.

### 5.1. Scenario matrix to test

| Provider 1 | Provider 2 | Outcome to verify |
| --- | --- | --- |
| `supports=false` | success | Provider 1 never calls `authenticate` |
| `supports=true, return null` | success | Provider 2 is called |
| success | success | Provider 2 **is not called** |
| `BadCredentialsException` | success | Provider 2's success can win |
| `BadCredentialsException("one")` | `BadCredentialsException("two")` | Throws last exception when none succeed |
| `LockedException` | success | Stops immediately at `LockedException` |
| null | null | No result; `ProviderNotFoundException` without parent |
| No supporting provider | None | `ProviderNotFoundException` |
| null | parent success | Falls back to parent if present |
| success containing `CredentialsContainer` | — | Manager erases credentials by default before returning |

**Security note:** letting one provider's success "override" another provider's password error **is not always desirable**. If providers share authority over an account but enforce different policies, design provider ordering/realms or account-state checks carefully to avoid bypasses. Never make tests pass by disabling account-status checks.

## 6. Component Testing Strategy

Split into three layers:

**Layer A — direct provider unit tests:** no web server or Spring Context. Verify `supports` against valid/invalid/subclass token classes; verify `authenticate` with valid/invalid credentials, out-of-scope accounts or realms, and no credential leakage.

**Layer B — `ProviderManager` unit tests:** wire multiple stub/spy providers with counters to prove ordering, skipping, `null`, exceptions, fallback, and credential erasure. This tests coordination semantics that isolated provider unit tests cannot prove.

**Layer C — filter chain integration tests:** with `MockMvc` or real HTTP, verify which filter creates which token type, manager wiring, 401/redirect responses, `SecurityContext`, and event publishing. Using `@WithMockUser` or `with(user(...))` only places an authentication into the context and **does not prove `authenticate(...)` ran**; requests must actually traverse the filter/manager.

In the **Component Testing** module, prioritize A and B; there is no need to boot an entire Spring Boot `ApplicationContext` to test a 2-method contract.

## 7. Runnable Maven JUnit 5 Project with Java 17+

This example includes:

- A demo provider with two realms: user `alice` is within scope; usernames prefixed with `external:` are **deferred** (returning `null`) for another provider.
- Credentials verified using `BCryptPasswordEncoder` instead of plaintext comparison.
- Provider returning an authenticated token with `ROLE_USER` on success.
- A JUnit class testing both `supports(...)` and all `authenticate(...)` outcomes, along with `ProviderManager` chaining.

This is a lab independent of a database/IdP to keep focus on the contract. Demo hashes/passwords are not for production use. Real applications should use `UserDetailsService`, account-status policies, a managed `PasswordEncoder`, rate limiting, PII/log hygiene, and a consistent realm model.

### 7.1. Project structure

~~~text
provider-contract-lab/
├── pom.xml
└── src/
    ├── main/java/demo/auth/PasswordProvider.java
    └── test/java/demo/auth/PasswordProviderContractTest.java
~~~

### 7.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>provider-contract-lab</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

The Spring Boot parent provides Java 17 compiler settings and compatible JUnit Platform/Surefire configuration. `@SpringBootTest` is not needed in the unit tests below.

### 7.3. PasswordProvider.java — the provider under test

~~~java
package demo.auth;

import java.util.List;

import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

public final class PasswordProvider implements AuthenticationProvider {

    private final PasswordEncoder encoder = new BCryptPasswordEncoder();
    private final String alicePasswordHash =
            encoder.encode("lab-secret-123");

    @Override
    public boolean supports(Class<?> authenticationType) {
        // Accept token class and subclasses of this type.
        return UsernamePasswordAuthenticationToken.class
                .isAssignableFrom(authenticationType);
    }

    @Override
    public Authentication authenticate(Authentication authentication) {
        // Defensive: do not attempt to read credentials of another token type.
        if (!(authentication instanceof UsernamePasswordAuthenticationToken)) {
            return null;
        }

        // Demo: realm outside the scope of the current provider.
        // supports(type) is still true due to same class, but provider defers.
        String username = authentication.getName();
        if (username.startsWith("external:")) {
            return null;
        }

        Object credential = authentication.getCredentials();
        if (!"alice".equals(username)
                || !(credential instanceof String password)
                || !encoder.matches(password, alicePasswordHash)) {
            throw new BadCredentialsException("Invalid credentials");
        }

        // Only a trusted provider creates an authenticated token.
        return UsernamePasswordAuthenticationToken.authenticated(
                "alice",
                null,
                List.of(new SimpleGrantedAuthority("ROLE_USER")));
    }
}
~~~

**Read the null branch carefully:** `external:...` is an **illustrative realm** to let another provider decide; it is not a safe default fallback for every multi-tenant system. Realms must be determined from trusted data (issuer, tenant, client registration) and authenticated under policies preventing credential confusion. Any username other than `alice` within the provider's scope is treated as bad credentials.

**Read the success branch carefully:** `UsernamePasswordAuthenticationToken.authenticated(...)` is called only after `PasswordEncoder.matches(...)`. Setting `credentials=null` avoids keeping plaintext inside the authenticated token.

### 7.4. PasswordProviderContractTest.java — complete JUnit 5 suite

~~~java
package demo.auth;

import java.util.List;
import java.util.function.Function;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.LockedException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.ProviderNotFoundException;
import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

import static org.junit.jupiter.api.Assertions.*;

class PasswordProviderContractTest {

    private static UsernamePasswordAuthenticationToken request() {
        return UsernamePasswordAuthenticationToken.unauthenticated(
                "alice", "lab-secret-123");
    }

    static final class ChildPasswordToken
            extends UsernamePasswordAuthenticationToken {
        ChildPasswordToken(String username, String password) {
            super(username, password);
        }
    }

    // Stub actively counts how many times authenticate is called.
    // Supports testing null / success / failure depending on Function.
    static final class ProbeProvider implements AuthenticationProvider {
        final Class<?> type;
        final Function<Authentication, Authentication> behavior;
        int calls;

        ProbeProvider(Class<?> type,
                Function<Authentication, Authentication> behavior) {
            this.type = type;
            this.behavior = behavior;
        }

        @Override
        public boolean supports(Class<?> authenticationType) {
            return type.isAssignableFrom(authenticationType);
        }

        @Override
        public Authentication authenticate(Authentication authentication) {
            calls++;
            return behavior.apply(authentication);
        }
    }

    private static Authentication trusted(String name) {
        return UsernamePasswordAuthenticationToken.authenticated(
                name,
                null,
                List.of(new SimpleGrantedAuthority("ROLE_USER")));
    }

    @Test
    void supportsChecksTypeAndSubclassButNotPassword() {
        PasswordProvider provider = new PasswordProvider();
        assertTrue(provider.supports(
                UsernamePasswordAuthenticationToken.class));
        assertTrue(provider.supports(ChildPasswordToken.class));
        assertFalse(provider.supports(TestingAuthenticationToken.class));
        assertFalse(provider.supports(Authentication.class));
    }

    @Test
    void authenticatesValidCredentialsAndSetsAuthorities() {
        Authentication actual = new PasswordProvider().authenticate(request());

        assertNotNull(actual);
        assertTrue(actual.isAuthenticated());
        assertEquals("alice", actual.getName());
        assertNull(actual.getCredentials());
        assertTrue(actual.getAuthorities().stream()
                .anyMatch(a -> "ROLE_USER".equals(a.getAuthority())));
    }

    @Test
    void rejectsBadCredentialsWithTypedException() {
        Authentication wrong =
            UsernamePasswordAuthenticationToken.unauthenticated(
                "alice", "wrong-password");

        assertThrows(BadCredentialsException.class,
                () -> new PasswordProvider().authenticate(wrong));
    }

    @Test
    void returnsNullWhenUnableToProcessInstance() {
        PasswordProvider provider = new PasswordProvider();

        assertNull(provider.authenticate(
                new TestingAuthenticationToken("alice", "anything")));

        Authentication outsideRealm =
            UsernamePasswordAuthenticationToken.unauthenticated(
                    "external:bob", "anything");

        assertTrue(provider.supports(outsideRealm.getClass()));
        assertNull(provider.authenticate(outsideRealm));
    }

    @Test
    void managerSkipsProvidersThatDoNotSupportTokenClass() {
        ProbeProvider unrelated = new ProbeProvider(
                TestingAuthenticationToken.class, ignored -> trusted("wrong"));
        ProviderManager manager = new ProviderManager(
                unrelated, new PasswordProvider());

        assertEquals("alice", manager.authenticate(request()).getName());
        assertEquals(0, unrelated.calls);
    }

    @Test
    void managerContinuesAfterNullThenStopsOnSuccess() {
        ProbeProvider abstains = new ProbeProvider(
                UsernamePasswordAuthenticationToken.class, ignored -> null);
        ProbeProvider shouldNotRun = new ProbeProvider(
                UsernamePasswordAuthenticationToken.class,
                ignored -> trusted("unexpected"));
        ProviderManager manager = new ProviderManager(
                abstains, new PasswordProvider(), shouldNotRun);

        Authentication actual = manager.authenticate(request());

        assertEquals("alice", actual.getName());
        assertEquals(1, abstains.calls);
        assertEquals(0, shouldNotRun.calls);
    }

    @Test
    void ordinaryFailureCanBeOverriddenByLaterSuccess() {
        ProbeProvider initialFailure = new ProbeProvider(
                UsernamePasswordAuthenticationToken.class,
                ignored -> {
                    throw new BadCredentialsException("first");
                });

        ProviderManager manager = new ProviderManager(
                initialFailure, new PasswordProvider());

        assertEquals("alice", manager.authenticate(request()).getName());
        assertEquals(1, initialFailure.calls);
    }

    @Test
    void accountStatusExceptionStopsFallbackImmediately() {
        ProbeProvider locked = new ProbeProvider(
                UsernamePasswordAuthenticationToken.class,
                ignored -> {
                    throw new LockedException("Account locked");
                });
        ProbeProvider fallback = new ProbeProvider(
                UsernamePasswordAuthenticationToken.class,
                ignored -> trusted("wrong"));

        ProviderManager manager = new ProviderManager(locked, fallback);
        assertThrows(LockedException.class,
                () -> manager.authenticate(request()));
        assertEquals(1, locked.calls);
        assertEquals(0, fallback.calls);
    }

    @Test
    void allNullMeansNoProviderAuthenticated() {
        ProbeProvider abstains = new ProbeProvider(
                UsernamePasswordAuthenticationToken.class, ignored -> null);

        ProviderManager manager = new ProviderManager(abstains);
        assertThrows(ProviderNotFoundException.class,
                () -> manager.authenticate(request()));
        assertEquals(1, abstains.calls);
    }

    @Test
    void noSupportingProviderThrowsProviderNotFound() {
        ProbeProvider unrelated = new ProbeProvider(
                TestingAuthenticationToken.class,
                ignored -> trusted("never"));

        ProviderManager manager = new ProviderManager(unrelated);
        assertThrows(ProviderNotFoundException.class,
                () -> manager.authenticate(request()));
        assertEquals(0, unrelated.calls);
    }

    @Test
    void lastOrdinaryAuthenticationExceptionIsPropagated() {
        ProbeProvider first = new ProbeProvider(
                UsernamePasswordAuthenticationToken.class, ignored -> {
                    throw new BadCredentialsException("first");
                });
        ProbeProvider second = new ProbeProvider(
                UsernamePasswordAuthenticationToken.class, ignored -> {
                    throw new BadCredentialsException("second");
                });

        ProviderManager manager = new ProviderManager(first, second);
        BadCredentialsException failure =
                assertThrows(BadCredentialsException.class,
                        () -> manager.authenticate(request()));

        assertEquals("second", failure.getMessage());
        assertEquals(1, first.calls);
        assertEquals(1, second.calls);
    }

    @Test
    void parentManagerIsFallbackWhenChildAbstains() {
        ProbeProvider child = new ProbeProvider(
                UsernamePasswordAuthenticationToken.class, ignored -> null);
        AuthenticationManager parent = ignored -> trusted("parent-user");

        ProviderManager manager = new ProviderManager(
                List.of(child), parent);

        assertEquals("parent-user",
                manager.authenticate(request()).getName());
        assertEquals(1, child.calls);
    }

    @Test
    void managerErasesCredentialsOfReturnedTokenByDefault() {
        ProbeProvider provider = new ProbeProvider(
                UsernamePasswordAuthenticationToken.class,
                ignored -> UsernamePasswordAuthenticationToken.authenticated(
                        "alice", "temporary-secret",
                        List.of(new SimpleGrantedAuthority("ROLE_USER"))));
        ProviderManager manager = new ProviderManager(provider);

        Authentication actual = manager.authenticate(request());

        assertTrue(actual.isAuthenticated());
        assertNull(actual.getCredentials());
    }
}
~~~

### 7.5. Running tests and evaluating results

In the project directory, with JDK 17+ and Maven:

~~~bash
mvn test
~~~

Maven downloads dependencies and runs the tests. With compatible source and dependencies, expect:

~~~text
Tests run: 13, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
~~~

This is an **excerpt of the expected output**, not the full stdout (Maven adds timestamps, class names, build progress, and execution time). If compilation errors occur, check the JDK version, Boot BOM, Java package/path, and dependency resolution before interpreting them as Spring behavior.

On Windows PowerShell/CMD also use `mvn test`; with Maven Wrapper use `mvnw.cmd test`. There is no need to run `spring-boot:run` because this project is a **unit test module** with no `@SpringBootApplication`. That is intentional.

### 7.6. Why not mock every AuthenticationProvider?

Mockito is helpful when you only want to verify that `ProviderManager` calls providers in the right order:

~~~java
// Mockito fragment; not a standalone test class.
when(provider.supports(UsernamePasswordAuthenticationToken.class))
    .thenReturn(true);
when(provider.authenticate(any(Authentication.class)))
    .thenReturn(null);
~~~

However, using only mocks does not prove that a **real provider** checks passwords, account state, or constructs authorities properly. Combining **real provider tests** and **stub/spy manager tests** as in the example verifies the contract cleanly without booting a full web app.

## 8. What to Assert and What Not to Assert

### 8.1. Checklist by method

| Target | Required assertions | Why |
| --- | --- | --- |
| `supports(...)` | true for intended token, false for other types | Avoid mechanism confusion |
| `supports(...)` | true for subclasses if intended | Avoid missing token subtypes |
| `authenticate(valid)` | `authenticated` true | Never return untrusted tokens |
| `authenticate(valid)` | exact principal | Prevent user confusion |
| `authenticate(valid)` | exact minimal authorities | Ensure proper roles/scopes |
| `authenticate(valid)` | credentials null/erased | Do not retain passwords |
| `authenticate(wrong)` | exact `AuthenticationException` | Do not swallow errors |
| `authenticate(unhandled)` | `null` when semantically right | Allow manager fallback |
| `ProviderManager` | skips unsupported providers | Do not invoke wrong provider |
| `ProviderManager` | `null` -> next | Do not treat `null` as terminal failure |
| `ProviderManager` | success -> stop | Prevent overlapping authentication |
| `ProviderManager` | `LockedException` -> stop | Do not bypass account status |
| `ProviderManager` | fail then success | Understand provider precedence |
| `ProviderManager` | all `null` -> `ProviderNotFound` | Detect missing wiring |
| `ProviderManager` | parent fallback | Verify multi-chain configuration |
| `ProviderManager` | erase credentials | Protect session and cached secrets |

### 8.2. Easy-to-get-wrong assertions

- **Only `assertNotNull(authenticate(...))`:** does not guarantee `isAuthenticated()`, principal, or authorities are valid.
- **`assertThrows(BadCredentialsException.class)` for every error:** locked/disabled accounts, provider outages, and unsupported tokens mean different things.
- **Expecting `supports(...)` to verify passwords:** the method only receives `Class<?>`.
- **Expecting every thrown exception to stop the chain:** ordinary exceptions can be overridden by a later provider; `AccountStatusException` is the classic hard stop.
- **Expecting `null` to equal bad credentials:** `null` means abstaining.
- **Expecting the manager to always throw the first error:** if multiple `AuthenticationException`s occur with no success, the last error is typically used.
- **Expecting every mock context to invoke the provider:** `@WithMockUser` populates `SecurityContext` upfront and bypasses the provider.
- **Expecting the output `Authentication` to still carry the raw password:** callers should receive erased/absent credentials.

## 9. Testing Built-in AuthenticationProviders

When you do not write a custom provider, you should still test the contract and configuration with appropriate integration tests.

| Provider/flow | Common input class | Priority test points |
| --- | --- | --- |
| `DaoAuthenticationProvider` | `UsernamePasswordAuthenticationToken` | `PasswordEncoder`, account lock/disabled, `UserDetailsService`, authorities |
| `JwtAuthenticationProvider` | `BearerTokenAuthenticationToken` | Signature/JWK, `iss`, `aud`, `exp`, scopes, invalid token |
| `PreAuthenticatedAuthenticationProvider` | `PreAuthenticatedAuthenticationToken` | Trust boundary with reverse proxy, `UserDetailsService`, never trust spoofed headers |
| `CasAuthenticationProvider` | Version-appropriate CAS-specific service-ticket token | Ticket validator, service URL binding, replay, errors |
| `LdapAuthenticationProvider` | Username/password token | Bind, LDAPS/TLS, disabled account policy, role mapping |
| Custom `AuthenticationProvider` | Custom `Authentication` | `supports` policy, validation, exceptions, null/fallback |

**Do not force every provider to use `UsernamePasswordAuthenticationToken`**. For JWT/opaque tokens or X.509, request token types differ; if `supports(...)` is overly broad, the manager can pass the wrong token to a provider, causing `ClassCastException` or trust-mechanism errors.

To test HTTP integration:

1. Use `spring-security-test` with `MockMvc` or a real HTTP client.
2. Send credentials/tokens through the filter under test, not just injecting an authenticated principal.
3. Confirm requests with invalid tokens are rejected and create no authenticated `SecurityContext`.
4. Verify 401/redirect on authentication failure and 403 on authorization denial per configuration.
5. Verify exception mappings and event publishers/metrics if needed.
6. Verify multiple `SecurityFilterChain` instances and which manager is used on each path.

## 10. Safety of Custom Providers and Fallback Ordering

When multiple providers support the same token type, **ordering can be a security decision**, not just a technical one.

For example, a system with two identity sources:

~~~text
Provider A: internal user store
Provider B: external directory
~~~

If `Provider A` throws `BadCredentialsException` for an internal user with a wrong password, and `Provider B` happens to authenticate the same username, the manager may accept B. That is known contract behavior, yet it may **violate policy** if usernames/realms are not separated.

Solutions:

- Clearly define the **authority/realm** for each provider and choose appropriate `Authentication` types or routing.
- Map principals to a trusted namespace/issuer/tenant; never use a plain username string as a global identity key when sources can collide.
- Locked/disabled account checks must apply wherever authority resides; never return `null` to skip status checks.
- On service errors/IdP outages, choose fail-closed/routing per policy rather than automatically trying a weaker source.
- Test provider ordering and parent fallback; a configuration change can introduce a bypass that isolated provider unit tests miss.
- Never leak account existence through HTTP error messages, logs, or easily distinguishable timing.
- Never log raw `Authentication.getCredentials()` or bearer tokens in failure tests.

### 10.1. CredentialsContainer and caching

Upon success, `ProviderManager` erases credentials on the output token by default if the token implements `CredentialsContainer`. Tests should prove this.

If the output token holds a reference to a cached `UserDetails` and `eraseCredentials` mutates that shared object, later authentications may break. Consider copying the principal/cache object rather than globally disabling credential erasure. Never keep passwords long-lived in `HttpSession`.

### 10.2. ProviderManager does not publish events by itself when instantiated manually

A manually instantiated `ProviderManager` has a default publisher that emits no events. If you need `AuthenticationSuccessEvent` or failure events, wire the bean:

~~~java
// Fragment: publisher already created/injected from Spring.
ProviderManager manager = new ProviderManager(providers);
manager.setAuthenticationEventPublisher(authenticationEventPublisher);
~~~

Do not conclude a provider was not called merely because "no event was seen". With parent and child managers, avoid duplicate events when both publish.

## 11. Diagnosing Test Failures

| Symptom | Common cause | How to fix |
| --- | --- | --- |
| `supports(...)` returns false for subclass | Used `==` instead of `isAssignableFrom` | Clarify intent, fix/test class policy |
| `ClassCastException` in `authenticate` | Cast token before checking type | Use `instanceof`, accurate `supports` |
| `ProviderNotFoundException` | No provider supported or returned non-null | Check token class, manager wiring, parent |
| `BadCredentialsException` "overridden" by later provider | Manager tried next provider | Check ordering and realm policy |
| `LockedException` yet later provider still runs (in custom manager) | Custom manager violated contract | Use `ProviderManager`/test hard-stop |
| Provider unit tests pass but HTTP returns 401 | Filter creates different token type, wrong manager, chain config | Integration test the real path |
| `@WithMockUser` test passes even though provider never ran | Test injects context directly | Test with credential requests through the filter |
| Returned `Authentication` has `isAuthenticated=false` | Provider returned request token instead of trusted token | Use `authenticated` factory after verification |
| Output token still holds plaintext password | Provider returned raw credentials/object without erasing | Return null credentials, verify manager erase |
| Manager calls provider 2 even though provider 1 succeeded | Provider 1 actually returned null or wrong type | Spy ordering, check return value |
| Mock returns null for unsupported provider without checking supports | Test does not prove skipping | Assert `authenticate` was never called |
| Test expects first exception but gets last | Manager contract retains last exception | Verify provider ordering |
| Parent manager runs unexpectedly | Local providers made no decision | Verify parent fallback & policy |
| JUnit import error | Missing `starter-test` or mismatched Maven version | Check parent BOM and JDK |
| Tests fail intermittently | Shared mutable mocks/threads, real clock | Use fresh test instances/deterministic clock |

## 12. Practical Checklist Before Finishing

**supports contract**

- [ ] True for designed token types, false for out-of-scope tokens.
- [ ] Subclass behavior and direction of `isAssignableFrom` clearly defined.
- [ ] No password checks or external IdP calls inside `supports(Class<?>)`.
- [ ] Does not assume `supports=true` guarantees a non-null result.

**authenticate contract**

- [ ] Valid requests produce a trusted `Authentication`, exact principal, and exact authorities.
- [ ] Bad credentials throw the right `AuthenticationException` type.
- [ ] Unknown/unowned realms can return `null` **only per intentional policy**.
- [ ] Locked/disabled accounts cannot fall back improperly.
- [ ] Never return an authenticated result using client-supplied roles.
- [ ] Never expose credentials or sensitive details in output/logs.

**ProviderManager behavior**

- [ ] Skips providers where `supports=false`.
- [ ] Continues after `null`; stops after success.
- [ ] Understands last exception vs later success.
- [ ] Hard-stops on `AccountStatusException`.
- [ ] Throws `ProviderNotFound` when no result/match exists.
- [ ] Parent fallback is explicit and cannot accidentally bypass policy.
- [ ] Runs `eraseCredentials` on outputs implementing `CredentialsContainer`.
- [ ] Event publishing wired when needed, without duplicates.

**Integration/operations**

- [ ] Real filters create the expected token class.
- [ ] HTTP responses and `SecurityContext` are accurate after login success/failure.
- [ ] Do not confuse Servlet `AuthenticationProvider` with WebFlux `ReactiveAuthenticationManager`.
- [ ] Never use `@WithMockUser` as proof that a provider ran.
- [ ] Include negative tests for account status and provider outages.
- [ ] Test code never prints real tokens/passwords or causes out-of-scope side effects.

## 13. Self-Check Questions

1. What parameter does `supports(Class<?>)` receive? Can it be used to check whether a password is correct?
2. Does `supports(...) == true` require `authenticate(...)` to return a non-null token?
3. Why is `null` different from `BadCredentialsException`?
4. When does `ProviderManager` skip a provider without calling `authenticate`?
5. If provider A returns `null` and B authenticates successfully, what is the result?
6. If provider A throws `BadCredentialsException` and B succeeds, how does the manager handle it?
7. If provider A throws `LockedException`, is B called?
8. If all providers return `null` or do not support the token, what does the manager usually throw?
9. If there are two ordinary exceptions and no success, which exception is thrown?
10. Why is asserting only `assertNotNull(authenticate(...))` insufficient?
11. Why should you not call `UsernamePasswordAuthenticationToken.authenticated(...)` directly on form input?
12. Why should you not test a provider flow using only MockMvc's `with(user(...))`?
13. When is a parent `AuthenticationManager` tried?
14. Why is erasing credentials by default important?

**Conclusion:** a proper provider must **accurately `supports` token types** and **safely `authenticate`** across success, `null`, and exception cases; a proper manager must **preserve ordering, fallback, and hard-stops**. A JUnit suite covering both levels is the most effective way to catch wiring bugs and prevent authentication bypasses when adding new providers.

## 14. Official Documentation

- [Spring Security 6.5 — AuthenticationProvider API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/AuthenticationProvider.html)
- [Spring Security 6.5 — ProviderManager API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ProviderManager.html)
- [Spring Security 6.5 — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html)
- [Spring Security 6.5 — Authentication interface](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/Authentication.html)
- [Spring Security 6.5 — UsernamePasswordAuthenticationToken](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/UsernamePasswordAuthenticationToken.html)
- [Spring Security 6.5 — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html)
- [Spring Security 6.5 — Testing](https://docs.spring.io/spring-security/reference/6.5/servlet/test/index.html)
- [JUnit 5 — Writing Tests](https://junit.org/junit5/docs/current/user-guide/#writing-tests)
