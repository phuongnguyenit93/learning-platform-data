# Provider Ordering and How Success, Unsupported, or Failure Are Handled

> **Context:** Spring Security → Authentication → Authentication Engine. This lesson dives into how `ProviderManager` iterates through `AuthenticationProvider`s, distinguishing “unsupported”, “undecided”, “authentication succeeded”, “authentication failed”, and why provider ordering is an essential part of security design. API examples apply to Spring Security 6.x, Java 17+.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain the responsibilities of `AuthenticationManager`, `ProviderManager`, and `AuthenticationProvider`; know the order in which providers are called.
2. Clearly distinguish the three signals `supports(...) == false`, `authenticate(...) == null`, and `authenticate(...)` throwing `AuthenticationException`.
3. Accurately predict behavior when the first provider returns a successful result, rejects credentials, does not support the token, and when a subsequent provider can succeed.
4. Recognize exceptions that cause `ProviderManager` to **stop immediately**, especially `AccountStatusException` and `InternalAuthenticationServiceException`.
5. Understand how a parent `AuthenticationManager` works, when `ProviderNotFoundException` occurs, how the final exception is chosen, authentication events, and credential erasure after success.
6. Run a Java example with observable provider ordering; design tests to avoid accidentally letting a later provider bypass an earlier provider's policy.

## 2. Three Roles in a Single Authentication

`AuthenticationManager` defines the central operation:

~~~java
Authentication authenticate(Authentication authentication)
        throws AuthenticationException;
~~~

It receives an **authentication request** as an `Authentication`, returns an authenticated result on success, or throws `AuthenticationException` on failure.

`ProviderManager` is the standard implementation of `AuthenticationManager`. It holds an **ordered list** of `AuthenticationProvider`s and routes each request to matching providers. An `AuthenticationProvider` typically handles one mechanism or a specific credential set: username/password, JWT, external access token, certificate, or a custom mechanism.

The provider interface has two primary methods:

~~~java
public interface AuthenticationProvider {
    Authentication authenticate(Authentication authentication)
            throws AuthenticationException;

    boolean supports(Class<?> authentication);
}
~~~

| Component | Question it answers | Responsibility |
| --- | --- | --- |
| Request `Authentication` | “What proof am I presenting?” | Holds principal, credentials, and request info; initially usually unauthenticated |
| `AuthenticationProvider.supports(type)` | “Can I **examine** this Java token type?” | Determines capability by **class type**, without checking credentials |
| `AuthenticationProvider.authenticate(request)` | “For a matching request type, is this proof valid?” | Performs actual verification, returns a result, or reports undecided/failure |
| `ProviderManager.authenticate(request)` | “Which provider in the list produces an authentication result?” | Selects providers in order and applies continue/stop policies |
| Security filter or trusted caller | “Where do we get and store the result?” | Calls manager, handles success/failure, establishes `SecurityContext` via appropriate mechanism |
| Authorization | “Does the subject have permission to perform this action?” | Evaluates authorities, roles, scopes, resource/tenant policies |

**Note:** `supports(...) == true` **only confirms the provider is capable of evaluating that `Authentication` class**. It does not mean the password is correct, the token is valid, or the user has permissions. It must pass through `authenticate(...)` and yield a trusted result.

For example, two providers both return `true` for `UsernamePasswordAuthenticationToken.class`: one checks LDAP, the other checks an internal user store. In that case, ordering and fallback rules shape the final decision.

## 3. Ordered Provider Iteration Algorithm

Given a list `[P1, P2, P3]`, `ProviderManager` iterates from start to end. Conceptual control model:

~~~mermaid
flowchart TD
    A["Authentication request"] --> B["Check next provider in order"]
    B --> C{"supports(request.getClass())?"}
    C -->|false| D["Skip; do not call authenticate"]
    D --> B
    C -->|true| E["Call provider.authenticate(request)"]
    E --> F{"Result?"}
    F -->|"Non-null Authentication"| G["Success; stop iterating"]
    F -->|null| H["Undecided; try next"]
    H --> B
    F -->|"Standard AuthenticationException"| I["Record error; try next"]
    I --> B
    F -->|"AccountStatusException or InternalAuthenticationServiceException"| J["Throw immediately; stop"]
    B --> K{"Out of providers?"}
    K -->|yes| L["If parent exists, try parent"]
    L --> M{"Have a result?"}
    M -->|yes| G
    M -->|no| N["Throw last error or ProviderNotFoundException"]
~~~

The diagram condenses termination conditions; detailed rules on parents and exceptions are explained in Sections 5–6.

### 3.1. `supports(...) == false`: Authentication Type Not Supported

The provider is **completely skipped**, and `authenticate(...)` is not called. Control moves to the next provider. For instance, a provider supporting only `UsernamePasswordAuthenticationToken` will typically skip a JWT token if `supports(...)` is implemented properly by type.

This is a decision **by Java token class**, not “username does not exist in this store”. Never use `supports(...)` to attempt password verification or make requests to external systems.

### 3.2. `supports(...) == true` and `authenticate(...)` Returns `null`

The provider can evaluate the token type yet **makes no decision** for the specific request. `ProviderManager` continues to the next provider. This is the “abstain” mechanism: neither confirming success nor declaring failure.

For example, there may be two different variants within the same token type; the first provider recognizes the request does not belong to the mechanism it owns and returns `null`, allowing another provider to inspect it.

**Do not use `null` to hide a wrong password** if the provider is actually responsible for verifying credentials. If all providers yield no result and no parent can authenticate, `ProviderNotFoundException` is typically thrown. If a standard authentication error occurred earlier, the last error is retained per Section 4 rules.

### 3.3. Returning Non-`null` `Authentication`: Success, Stop Iterating

When a provider returns a **non-`null`** result, `ProviderManager` accepts it and **calls no subsequent providers**. The provider must return this result **only after genuinely verifying the proof** and building a trusted `Authentication`; `ProviderManager` does not re-check passwords or token signatures on behalf of the provider.

Why is this decision critical? If P1 returns a bad result due to code building an “authenticated” token from client data, P2 never gets a chance to correct it. Provider design and tests are responsible for ensuring the resulting `Authentication` is valid.

### 3.4. Throwing Standard `AuthenticationException`: Next Providers May Be Tried

A `BadCredentialsException` from P1 **does not inherently stop all of `ProviderManager`**. The manager records the error and can try P2, P3 if they support the same token type. If P2 authenticates successfully, **P2's success is used and P1's error is discarded**. If no provider succeeds, the last authentication error is thrown.

This often surprises developers: “P1 reported wrong password” does not equate to “the request is definitely rejected” when a second provider supports the same request type.

**Security implication:** only enable fallback across multiple providers when it is an intentional login policy. If “user absent from LDAP” is allowed to continue checking a local store, you must define clear namespaces, avoid identity collisions, and consider account locks, login conditions, and the risk of a weaker store accepting credentials rejected by an earlier store.

### 3.5. Special Exceptions: Immediate Stop

Two branches in `ProviderManager` require separate understanding:

- `AccountStatusException`, such as `LockedException`, `DisabledException`, `AccountExpiredException`, `CredentialsExpiredException`: **stops immediately**, without querying remaining providers or using the parent to bypass the locked/expired status.
- `InternalAuthenticationServiceException`: also **stops immediately**, because the provider reported a serious internal authentication service error; do not arbitrarily continue falling back.

Do not equate every `AuthenticationException` with “stop immediately”; nor assume **every** service error behaves identically to `InternalAuthenticationServiceException`. Branching depends on the **actual exception class thrown**.

## 4. Decision Table by Scenario

Assume list `[P1, P2]` with no parent configured. “Result” here refers to the outcome of `ProviderManager.authenticate(...)`, **not yet the endpoint's authorization decision**.

| P1 | P2 | Is P2 tried? | Result |
| --- | --- | --- | --- |
| `supports=false` | Succeeds | Yes | Returns P2's `Authentication` |
| `supports=true`, returns `null` | Succeeds | Yes | Returns P2's `Authentication` |
| Succeeds | Any | **No** | Returns P1's result, stops immediately |
| Throws `BadCredentialsException` | Succeeds | Yes | Returns P2's result; P1's error is no longer decisive |
| Throws `BadCredentialsException` | Throws `BadCredentialsException` | Yes | Throws P2's error (last error) |
| Throws `BadCredentialsException` | Returns `null` or unsupported | Yes / skipped per `supports` | Throws P1's `BadCredentialsException` |
| `supports=false` | `supports=false` | P2 checked `supports` but did not run `authenticate` | Throws `ProviderNotFoundException` |
| Returns `null` | Returns `null` | Yes | Throws `ProviderNotFoundException` if no other error |
| Throws `LockedException` | Would succeed if called | **No** | Throws `LockedException` immediately |
| Throws `InternalAuthenticationServiceException` | Would succeed if called | **No** | Throws internal error immediately |

**Distinguishing “P2 is tried” from “P2 has `authenticate` called”:** `supports` is normally still checked when the loop reaches P2; `authenticate` is only called if `supports` returns `true`. If P1 already succeeded or threw an immediate-stop exception, even evaluating P2 does not occur.

### What Does “Last Exception” Mean?

Suppose P1 throws `BadCredentialsException("password wrong")` and P2 throws `BadCredentialsException("token rejected")`. If no provider succeeds and no parent handles it, `ProviderManager` typically throws **P2's exception**, rather than merging both into a new error. If P1 throws an error and P2 returns `null`, P1's error remains the last error. This aids diagnostics, though internal error messages should not be returned verbatim in public APIs.

Certain exceptional branches are handled specially before reaching the “last error” rule: `AccountStatusException` and `InternalAuthenticationServiceException` are thrown immediately. Meanwhile, a parent may participate after all providers in the list fail to produce a result; see the next section.

## 5. When Is the Parent AuthenticationManager Called?

A `ProviderManager` can have a **parent `AuthenticationManager`**. When child providers **produce no successful result**, and no immediate-stop exception occurred, the manager can try the parent. The parent is not “the last provider” in the list, yet is consulted after the local provider loop.

Example structure:

~~~text
HTTP authentication request
    |
    v
Child ProviderManager
    |-- P1
    |-- P2
    |
    +-- if no result yet and allowed to continue
            |
            v
       Parent AuthenticationManager
            |-- P3
            |-- P4
~~~

Key facts to know:

- The parent **can be called even if** a child provider threw a standard `BadCredentialsException`, as long as there is no result yet and no immediate-stop branch was hit.
- Parent succeeds → parent's result is used.
- Parent throws a standard `AuthenticationException` → that error can become the last error.
- Parent throws `ProviderNotFoundException` → the child `ProviderManager` has logic to avoid overwriting an earlier authentication error from a child provider with the parent's “provider not found” error; if there is no other error, the final outcome is still `ProviderNotFoundException`.
- Child provider throws `AccountStatusException` or `InternalAuthenticationServiceException` → stops before reaching the parent.
- A system with multiple `SecurityFilterChain`s sometimes uses multiple child managers sharing the same parent. That is an intentional design, not a default where every request passes through every chain.

**Example setting up a parent (integrated Java snippet, not standalone):**

~~~java
AuthenticationManager parent = new ProviderManager(
        List.of(sharedProvider));
AuthenticationManager child = new ProviderManager(
        List.of(applicationProviderA, applicationProviderB),
        parent);
~~~

Here `sharedProvider`, `applicationProviderA`, and `applicationProviderB` are configured `AuthenticationProvider`s that genuinely verify credentials. Only use a parent structure when the fallback policy makes security sense and is tested. Never use a parent to evade account locks or lump identities together across incompatible systems.

## 6. Runnable Java 17 Example: Ordering and Decision Branches

The example below uses **Spring Security's actual `ProviderManager` class**, creating simulated providers that can return success, `null`, reject, or raise errors. The “ACCEPT” provider **does not check passwords** because the sole goal is observing orchestration logic; **never reuse this simulated provider for real logins**. Real applications must verify credentials, enforce account policies, and restrict permissions.

The example is a **Java console app with a Spring Security Core dependency**, requiring no Spring Boot or web server; results are printed by `main`. The `build.gradle` requires Gradle able to download dependencies from Maven Central.

### 6.1. Structure and Gradle

~~~text
provider-order-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/example/providerorder/
    └── ProviderOrderDemo.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'provider-order-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.security:spring-security-core:6.5.11'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'example.providerorder.ProviderOrderDemo'
}
~~~

### 6.2. Complete Java File

Save at `src/main/java/example/providerorder/ProviderOrderDemo.java`:

~~~java
package example.providerorder;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.InternalAuthenticationServiceException;
import org.springframework.security.authentication.LockedException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

public class ProviderOrderDemo {

    enum Decision {
        UNSUPPORTED, ABSTAIN, REJECT, LOCKED, INTERNAL_ERROR, ACCEPT
    }

    // Provider simulating orchestration flow; DOES NOT perform real authentication.
    static final class TracedProvider implements AuthenticationProvider {
        private final String name;
        private final Decision decision;
        private final List<String> trace;

        TracedProvider(String name, Decision decision, List<String> trace) {
            this.name = name;
            this.decision = decision;
            this.trace = trace;
        }

        @Override
        public boolean supports(Class<?> authenticationType) {
            boolean supported = decision != Decision.UNSUPPORTED
                    && UsernamePasswordAuthenticationToken.class
                            .isAssignableFrom(authenticationType);
            trace.add(name + ".supports=" + supported);
            return supported;
        }

        @Override
        public Authentication authenticate(Authentication request)
                throws AuthenticationException {
            trace.add(name + ".authenticate");

            return switch (decision) {
                case ABSTAIN -> null;

                case REJECT ->
                        throw new BadCredentialsException("rejected by " + name);

                case LOCKED ->
                        throw new LockedException("locked by " + name);

                case INTERNAL_ERROR ->
                        throw new InternalAuthenticationServiceException(
                                "backend error at " + name);

                case ACCEPT ->
                        UsernamePasswordAuthenticationToken.authenticated(
                                request.getPrincipal(),
                                null,
                                List.of(new SimpleGrantedAuthority("ROLE_DEMO")));

                case UNSUPPORTED ->
                        throw new IllegalStateException(
                                "Unsupported provider should never be called");
            };
        }
    }

    static void runCase(String label, Decision... decisions) {
        List<String> trace = new ArrayList<>();
        List<AuthenticationProvider> providers = new ArrayList<>();

        for (int i = 0; i < decisions.length; i++) {
            providers.add(new TracedProvider(
                    "P" + (i + 1), decisions[i], trace));
        }

        ProviderManager manager = new ProviderManager(providers);

        Authentication request =
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "alice", "demo-credential");

        try {
            Authentication result = manager.authenticate(request);
            System.out.println(label + " => SUCCESS(" + result.getName() + ")");
        }
        catch (AuthenticationException failure) {
            System.out.println(label + " => "
                    + failure.getClass().getSimpleName());
        }

        System.out.println("  trace=" + trace);
    }

    public static void main(String[] args) {
        runCase("first-success",
                Decision.ACCEPT, Decision.REJECT);

        runCase("unsupported-then-success",
                Decision.UNSUPPORTED, Decision.ACCEPT);

        runCase("null-then-success",
                Decision.ABSTAIN, Decision.ACCEPT);

        runCase("bad-then-success",
                Decision.REJECT, Decision.ACCEPT);

        runCase("bad-then-bad",
                Decision.REJECT, Decision.REJECT);

        runCase("locked-stops",
                Decision.LOCKED, Decision.ACCEPT);

        runCase("internal-stops",
                Decision.INTERNAL_ERROR, Decision.ACCEPT);

        runCase("all-unsupported",
                Decision.UNSUPPORTED, Decision.UNSUPPORTED);

        runCase("all-null",
                Decision.ABSTAIN, Decision.ABSTAIN);
    }
}
~~~

Explanation:

- `Decision.UNSUPPORTED` makes `supports` return `false`, so that provider's `authenticate` method cannot be called under normal orchestration.
- `Decision.ABSTAIN` returns `null`, depicting a provider examining the token type yet unable to decide.
- `Decision.REJECT` throws `BadCredentialsException`: a standard error that `ProviderManager` can record while trying further.
- `Decision.LOCKED` and `Decision.INTERNAL_ERROR` throw exceptions belonging to the immediate-stop group.
- `Decision.ACCEPT` returns a non-`null` result: the manager stops iterating. This is a **simulation point**, not a production authentication pattern.

### 6.3. Running the Program

From the `provider-order-demo` directory with JDK 17+ and Gradle (or a configured Gradle Wrapper):

~~~bash
gradle run --quiet
~~~

Output generated by `ProviderOrderDemo.main`:

~~~text
first-success => SUCCESS(alice)
  trace=[P1.supports=true, P1.authenticate]
unsupported-then-success => SUCCESS(alice)
  trace=[P1.supports=false, P2.supports=true, P2.authenticate]
null-then-success => SUCCESS(alice)
  trace=[P1.supports=true, P1.authenticate, P2.supports=true, P2.authenticate]
bad-then-success => SUCCESS(alice)
  trace=[P1.supports=true, P1.authenticate, P2.supports=true, P2.authenticate]
bad-then-bad => BadCredentialsException
  trace=[P1.supports=true, P1.authenticate, P2.supports=true, P2.authenticate]
locked-stops => LockedException
  trace=[P1.supports=true, P1.authenticate]
internal-stops => InternalAuthenticationServiceException
  trace=[P1.supports=true, P1.authenticate]
all-unsupported => ProviderNotFoundException
  trace=[P1.supports=false, P2.supports=false]
all-null => ProviderNotFoundException
  trace=[P1.supports=true, P1.authenticate, P2.supports=true, P2.authenticate]
~~~

**How to read the trace:** in `first-success`, P2 is not even asked `supports`. In `unsupported-then-success`, P1 is asked `supports` yet does not run `authenticate`. In `bad-then-success`, P1's error does not stop P2. In `locked-stops` and `internal-stops`, P2 is not consulted at all. The last two cases prove `ProviderNotFoundException` can occur either because **no provider can handle the type** or because **every eligible provider declined to decide**.

Line ordering in the program is set by `main`, and `List` preserves insertion order. Exception messages and logs depend on the environment; the example prints only the exception class name for easy output verification. These simulated providers **must not be used to make real authentication decisions**, as they intentionally omit credential checks.

### 6.4. Trying an Additional Parent Scenario

Add to the code (or run in another example) the following conceptual snippet once `TracedProvider` is defined:

~~~java
List<String> trace = new ArrayList<>();

ProviderManager parent = new ProviderManager(List.of(
        new TracedProvider("parent", Decision.ACCEPT, trace)));
ProviderManager child = new ProviderManager(
        List.of(new TracedProvider("child", Decision.REJECT, trace)),
        parent);

Authentication result = child.authenticate(
        UsernamePasswordAuthenticationToken.unauthenticated(
                "alice", "demo-credential"));

System.out.println(result.getName());
System.out.println(trace);
~~~

This is an **integrated code snippet** (placed inside a method of `ProviderOrderDemo`, not a standalone file). With the simulated behavior above, the parent is still tried after the child's `BadCredentialsException` and succeeds:

~~~text
alice
[child.supports=true, child.authenticate, parent.supports=true, parent.authenticate]
~~~

Try changing the child's `Decision.REJECT` to `Decision.LOCKED`: the exception is thrown immediately, so the parent is never called. This explains why account status errors must not be used as a signal to “try another login store”.

## 7. Configuring Providers in a Spring Security Application

Ordering can be established via the provider list passed to `ProviderManager` or via the corresponding security configuration mechanism. Example integrating providers that **have been genuinely implemented and tested**:

~~~java
@Bean
AuthenticationManager authenticationManager(
        CorporateAuthenticationProvider corporateProvider,
        PartnerAuthenticationProvider partnerProvider) {

    return new ProviderManager(List.of(corporateProvider, partnerProvider));
}
~~~

This is a **configuration outline**: two real provider classes and imports for `@Bean`, `AuthenticationManager`, `ProviderManager`, `List` are required. It explicitly places `corporateProvider` before `partnerProvider`. With Spring Boot, defining a custom `AuthenticationManager` can affect auto-configuration; you must verify which filter chain actually uses this manager.

Questions to answer before deployment:

- Do the two providers support **the same** Java `Authentication` type or different types?
- If both support it, when one provider reports wrong user/password, **is the next provider allowed** to authenticate against a different identity store?
- Can an account locked in the first store be unlocked/open in the second? If so, what policy is the system enforcing?
- Does the same username in two stores belong to the same person? How are issuer/realm/tenant attached to prevent ambiguity?
- Who creates the result token and assigns authorities? Are permissions fetched from a trusted source?
- Is there a parent manager? Under what circumstances is it called and which permissions can be granted by the parent?
- Have you verified the actual runtime order?

**Do not assume Spring bean discovery order via component scan, class name, or `@Order` is always the exact order inside the running manager.** The decisive order is the provider list actually held by the `ProviderManager` instance. If exact ordering matters, configure the list explicitly and verify it with an integration test.

### 7.1. Different Mechanisms Usually Have Different Request Tokens

In an application with multiple login methods, the corresponding filter creates a request `Authentication` type and sends it to the manager. For example:

- Username/password: typically uses `UsernamePasswordAuthenticationToken` and a password-verifying provider such as `DaoAuthenticationProvider`.
- Bearer token: typically passes through `BearerTokenAuthenticationFilter`, with an appropriate provider/manager to verify JWT or opaque access tokens.
- OAuth2/OIDC login: dedicated path for authorization code/OIDC, with its own provider and token type.

When providers support different types, `supports` skips irrelevant providers. When multiple providers accept the same type, ordering/fallback must be treated as a real login policy, not merely a performance detail.

### 7.2. Provider Order Differs from Filter and SecurityFilterChain Order

In a Servlet application:

1. `FilterChainProxy` selects the `SecurityFilterChain` matching the request.
2. The corresponding authentication filter receives credentials/request and may call `AuthenticationManager`.
3. `ProviderManager` selects providers **within its own list**.
4. After success, the filter/security mechanism manages the result in `SecurityContext` and handles sessions if needed.
5. An authorization filter or method security checks access policies.

`ProviderManager` **does not handle URLs itself, does not write HTTP 401/403 itself, and does not automatically persist `Authentication` into `SecurityContext`**. Web HTTP responses also depend on the authentication entry point, failure handler, and access denied handler. Hence observing 401/403 helps diagnose issues, yet is insufficient to prove which provider ran without corresponding traces/tests.

## 8. After a Successful Result: Credentials, Details, and Events

### 8.1. Erasing Credentials to Reduce Risk

By default, `ProviderManager` attempts to erase sensitive credential data from **the `Authentication` result** after successful authentication if the result implements `CredentialsContainer`. The `eraseCredentialsAfterAuthentication` property controls this behavior (default is `true`).

Erasure can affect objects shared in a cache if that object itself also implements `CredentialsContainer`. When caching `UserDetails`/principals, design proper copying and caching; **never disable credential erasure just to fix a cache bug without evaluating the security impact**.

Credentials being erased after success **does not mean** the password/JWT was never verified; nor does it mean every piece of sensitive data in every application object is automatically wiped.

### 8.2. Copying Details

When a provider returns a successful result that is an `AbstractAuthenticationToken` with unset `details`, `ProviderManager` can copy `details` from the request to the result. That is auxiliary info, such as certain HTTP request metadata; never turn self-declared client details into trusted authorities.

### 8.3. Authentication Events

`ProviderManager` can invoke `AuthenticationEventPublisher` to publish authentication success/failure events. **`ProviderManager`'s own default is a no-op publisher that publishes no events**; the application/framework must provide an appropriate publisher if you want to observe those events. Never claim events always fire just because a provider ran.

A manager with a parent must avoid duplicate event logging when the parent already published an event. When configuring separate event publishers across multiple managers, test the case where child delegates to parent to ensure accurate audit counts.

**Never log raw passwords, API keys, access tokens, or secrets in trace logs.** To inspect provider ordering, log only request type, provider name, outcome classification, and a safe correlation ID.

## 9. Designing Tests That Protect Fallback Policies

The console example in Section 6 verifies the algorithmic path. Real applications need tests covering at least the following behavioral classes:

| Test | Scenario setup | What to assert |
| --- | --- | --- |
| Skip unsupported provider | P1 `supports=false`, P2 supports and authenticates | P1 does not run `authenticate`; P2 is called |
| Abstain | P1 returns `null`, P2 authenticates | P2 is called; do not mistake null for success |
| Early success | P1 succeeds, any P2 | P2 is not called, not even `supports` |
| Credential rejected then fallback | P1 throws `BadCredentialsException`, P2 authenticates | P2 **can** succeed; verify whether business policy allows this |
| All reject | P1/P2 throw standard errors | Fails; last exception is used |
| No provider handles it | All `supports=false` or all `authenticate=null` | `ProviderNotFoundException` if no parent and no prior error |
| Account locked | P1 throws `LockedException`, P2 could authenticate | P2 and parent are not called |
| Internal error | P1 throws `InternalAuthenticationServiceException` | No other providers tried; error propagates |
| Parent fallback | Child yields no result, parent authenticates | Parent is called after child providers |
| Post-authentication authorization | Provider returns valid principal yet lacks required authority | Protected endpoint still denies; authentication differs from authorization |

**Real tests should check provider invocations** (using counters/safe mocks/spies) and exception types at the `AuthenticationManager` layer. A test checking only HTTP 401/403 can miss dangerous fallback policies. Real login tests must verify filters/providers/encoders/decoders with checked credentials; using `@WithMockUser` only tests the authorization layer, not that passwords/JWTs were actually verified.

### 9.1. Dangerous Case: Accidental Fallback Changes What “Wrong Password” Means

Suppose a system uses two user stores:

~~~text
P1: CorporatePasswordProvider (username/password)
P2: LegacyPasswordProvider    (also username/password)
~~~

When P1 finds username “alice” with a wrong password and throws `BadCredentialsException`, P2 can still run and accept the same username/password against the legacy store. At that point, the actual behavior is “accept if **either** store accepts”, not “corporate is the mandatory authentication source”.

If that is the system's intent, you must explicitly manage identity linking, authorization, and lockout states. If not, design pre-authentication identity routing, use distinct realms or token types, or separate managers/chains so the second provider is only tried when valid per business rules. **Do not expect P1's `BadCredentialsException` to automatically block P2**.

### 9.2. Distinguishing “Unknown User” from “User with Wrong Credentials”

A provider that does not find a user in its store may make different decisions depending on its contract and security design. In some standard `UserDetailsService`/provider setups, a missing user is handled as a credential error to reduce user enumeration leakage. Never assume “user not found” must always return `null`, or must always throw one fixed exception across every provider.

The goal is **maintaining a consistent authentication policy**, avoiding letting error details or response timing reveal which store contains an account. Never use `supports(...)` to check username existence via a remote query; that method receives **`Class<?>`**, not request data.

## 10. Common Mistakes When Reading or Implementing ProviderManager

1. **“First provider threw an exception, so the manager stops.”** False for many standard `AuthenticationException`s; the next provider can still be tried, and if it succeeds, it wins.
2. **“`supports=true` means the password is right.”** False; it only checks capability to handle a type of `Authentication`.
3. **“Provider wants to yield, so it throws `BadCredentialsException`.”** That is a failed-authentication conclusion, different from `null` (undecided); it can affect the final error and auditing.
4. **“`authenticate=null` means anonymous login is allowed.”** False; null only means the provider did not decide; the overall manager still needs a successful result.
5. **“All providers returned null, so the manager returns null.”** False when there is no parent result: the manager throws `ProviderNotFoundException`.
6. **“All service errors try another provider.”** False for `InternalAuthenticationServiceException`; the manager stops immediately.
7. **“Account is locked in P1, so P2 can still try.”** Not when the provider properly throws `AccountStatusException`.
8. **“Sorting classes alphabetically or adding `@Order` is enough.”** You must verify the actual list and manager instance used by the filter.
9. **“A provider returning a non-null token is safe enough.”** The provider must verify credentials/signature/status itself and assign authorities from a trusted source; the manager does not re-verify those contents.
10. **“ProviderManager returned success, so the endpoint is authorized.”** Authorization still needs to check authorities, scopes, ownership, and tenant.
11. **“No event seen means the provider didn't run.”** Events depend on `AuthenticationEventPublisher` and configuration.
12. **“ProviderManager returns HTTP 401 itself.”** The manager handles Java results; HTTP statuses are decided by the web security/failure-handling layer.

## 11. Self-Check Questions

**Question 1:** P1 has `supports=true` yet returns `null`, and P2 succeeds. What happens?  
**Answer:** P2 is called; the manager returns P2's result. `null` from P1 means “undecided”.

**Question 2:** P1 throws `BadCredentialsException`, and P2 succeeds on the same request. What is the result?  
**Answer:** Per `ProviderManager`'s iteration logic, P2's result is used. You must review whether that fallback matches the authentication policy.

**Question 3:** P1 throws `DisabledException`, and P2 could authenticate. Is P2 tried?  
**Answer:** No. `DisabledException` is an `AccountStatusException`; the manager stops and throws the error immediately.

**Question 4:** Both P1 and P2 return `null`; there is no parent. What is the output of `authenticate`?  
**Answer:** `ProviderNotFoundException`, not `null`.

**Question 5:** P1 throws `BadCredentialsException`, P2 does not support the token, and the parent authenticates successfully. What is the final result?  
**Answer:** The parent still has a chance to authenticate after child providers yield no result, except on immediate-stop exception branches.

**Question 6:** A provider returns an authenticated token with `ROLE_ADMIN` without checking any password. Is this fine since `ProviderManager` accepts the result?  
**Answer:** No. This is a severe authentication vulnerability in the provider. The manager trusts non-`null` results; the provider is obligated to verify proof and authorities.

**Question 7:** How do you know P2 was invoked during a real login?  
**Answer:** Test spies/counters or safe logging in `supports`/`authenticate`; never infer solely from HTTP status or default bean ordering.

**Question 8:** Why does an API return 403 even though `ProviderManager` authenticated successfully?  
**Answer:** The principal may lack the required authority/permission on the resource; authentication and authorization are two independent stages.

## 12. Design Checklist and Takeaways

Before approving a provider chain, answer completely:

- Which **`Authentication` types** do the providers accept? How many providers support the same type?
- For each provider, in which business scenarios are **`null`, standard exceptions, immediate-stop exceptions, and success** used?
- If an earlier provider rejects credentials, under what policy is a later provider allowed to try? Could that neutralize lockouts or MFA?
- Does a parent `AuthenticationManager` participate? When? Can it alter authentication decisions or events?
- Are credentials erased from the result after success? Are there shared cached objects to watch out for?
- Do tests measure provider invocation order, exception branches, and post-authentication authorization?

**Quick rule of thumb:** `ProviderManager` iterates providers in **order**, skips unsupported providers, continues when a provider returns `null`, and **stops upon receiving a non-null result**; standard authentication errors can allow trying further, whereas `AccountStatusException` and `InternalAuthenticationServiceException` stop immediately. If nobody succeeds, the manager can consult the parent and then throw an appropriate error. Provider ordering is therefore part of the **authentication policy**, requiring explicit design and testing.

### Official References

- Spring Security — Servlet Authentication Architecture, `ProviderManager`: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html
- `ProviderManager` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ProviderManager.html
- `AuthenticationProvider` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/AuthenticationProvider.html
- `AuthenticationManager` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/AuthenticationManager.html
- `ProviderManager` source code for inspecting exception/parent/event branches: https://github.com/spring-projects/spring-security/blob/6.5.x/core/src/main/java/org/springframework/security/authentication/ProviderManager.java
