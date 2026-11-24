# Distinguishing User Not Found from Account Store Connection Failures

> **Context:** Spring Security — Authentication → **Account Store**. In a username/password login flow, "successfully queried and found no user record" and "unable to query because the database/LDAP/identity service is failing" are **two fundamentally different outcomes**. Conflating them can produce misleading errors, mask operational outages, allow unintended authentication fallback, or falsely conclude that an account does not exist. Examples use Java 17 and Spring Security 6.3.x for runnable code.

## 1. Objectives

After this lesson, you can:

1. Distinguish **trusted not found**, **invalid credentials**, **account store failure**, and **data/contract errors** using concrete signals.
2. Properly use `UserDetailsService.loadUserByUsername`, `UsernameNotFoundException`, `BadCredentialsException`, and `InternalAuthenticationServiceException`.
3. Understand the default `hideUserNotFoundExceptions = true` in `AbstractUserDetailsAuthenticationProvider`: hiding the difference between "username does not exist" and "wrong password" at the standard error layer.
4. Explain why **you must never turn every database exception into `UsernameNotFoundException`**, or return `null` when the backend fails.
5. Distinguish the Java result of `AuthenticationManager` from HTTP status codes 401/500/503; understand why **a store failure does not automatically produce HTTP 503**.
6. Write an account store adapter and a runnable program demonstrating all four branches: success, missing user, wrong password, and lost connection.
7. Design logging, metrics, testing, and safe multi-provider policies when an identity source fails.

## 2. The Problem Inside a Single Query

Suppose the system receives a login for `username=linh`. A lookup operation can yield several outcomes:

| Outcome from the backing store | Meaning | Proper action |
| --- | --- | --- |
| Query **succeeded**, exact account found | Enough data to check status, password hash, and authorities | Map into a valid `UserDetails` for the provider to verify next |
| Query **succeeded**, confirmed no account | No user with the queried key exists in that tenant/realm | `UserDetailsService` throws `UsernameNotFoundException` |
| Unable to reach DB/LDAP/identity API, timeout, pool exhausted | **Unknown** whether the account exists | Throw a service/data-source error so authentication rejects for lack of evidence |
| Store returns malformed data, missing required fields, mapping error, or contract-violating `null` | Cannot construct a trustworthy `UserDetails` | Report a data/service error; never treat it as "account does not exist" when uncertain |
| User found, yet password entered is wrong | Account may exist; credential is invalid | `DaoAuthenticationProvider` throws `BadCredentialsException` |
| User found, yet `enabled=false` or locked | Account exists but is blocked by policy | Provider throws status errors like `DisabledException` or `LockedException` |

**Key classification sentence:** "I **successfully checked** and concluded there is no user" is different from "I **could not check**, so I do not know whether the user exists".

Returning `Optional.empty()` is right when a query genuinely completed and returned 0 rows in the defined scope. Returning `Optional.empty()` as a stand-in for a timeout is a **security logic bug**.

## 3. The UserDetailsService Contract

Spring Security defines:

~~~java
public interface UserDetailsService {
    UserDetails loadUserByUsername(String username)
            throws UsernameNotFoundException;
}
~~~

This is the condensed signature of the interface. `UserDetailsService` **only loads account data**. It is not the entire login engine and must never assume that a username appearing in the database means credentials are valid.

Conditions to uphold:

- On successful load, return a **non-`null` `UserDetails`** containing username, password hash, status, and authorities from a trusted source.
- If the user **cannot be identified** by username: throw `UsernameNotFoundException`. The Javadoc also allows this exception when the user has no `GrantedAuthority` in certain cases; the application needs an explicit mapping contract.
- If querying fails due to infrastructure: **never fake a not-found result**; let the error propagate or translate it into a service exception preserving the cause.
- Never return `new User(...)` with default passwords/rules when data is corrupt, and never grant temporary permissions to an unverified user.
- Never mark `Authentication.isAuthenticated=true` inside the service; the provider mechanism must verify credentials.

In Spring Security Servlet with username/password, a typical sequence is:

~~~mermaid
sequenceDiagram
    participant C as HTTP client
    participant F as Authentication filter
    participant M as ProviderManager
    participant P as DaoAuthenticationProvider
    participant S as UserDetailsService
    participant D as DB / LDAP / user API
    C->>F: Username + password
    F->>M: UsernamePasswordAuthenticationToken (unauthenticated)
    M->>P: authenticate(request)
    P->>S: loadUserByUsername(username)
    S->>D: Query account
    alt Account found
        D-->>S: Account
        S-->>P: UserDetails
        P->>P: Check status and PasswordEncoder.matches
        P-->>M: Authentication result or exception
    else Query succeeded, no account
        D-->>S: No record
        S-->>P: UsernameNotFoundException
        P-->>M: Default BadCredentialsException
    else Store unreachable
        D--xS: Timeout / connection failure
        S-->>P: Infrastructure/translated exception
        P-->>M: InternalAuthenticationServiceException
    end
~~~

In the **found** branch, if the password is wrong it still fails: `UserDetailsService` returning the right object does not automatically grant a successful login.

## 4. Three Distinct Exception Groups

### 4.1. `UsernameNotFoundException`: Lookup Completed, User Not Identified

This is the signal defined by the `UserDetailsService` contract. Use it only when the backend has reliably answered that the user key does not exist in the lookup scope. A completed SQL query returning 0 rows is an example.

Java example **illustrating an integration method**:

~~~java
@Override
public UserDetails loadUserByUsername(String username)
        throws UsernameNotFoundException {
    Account account = repository.findByUsername(username)
            .orElseThrow(() -> new UsernameNotFoundException(
                    "Account not found"));
    return toUserDetails(account);
}
~~~

The `repository` variable and `toUserDetails` method must be defined by the application. This method is only valid if `findByUsername` **throws an exception when the store fails** and returns `Optional.empty()` solely when the query succeeds with no matching account.

**Never include "which username does not exist" in client responses**, even while the backend holds `UsernameNotFoundException`. Distinguishing existing users via error messages or response timing enables user enumeration.

### 4.2. `BadCredentialsException`: Login Credentials Rejected

`DaoAuthenticationProvider` verifies passwords via `PasswordEncoder`. A password that does not match a valid hash produces `BadCredentialsException`.

In addition, `AbstractUserDetailsAuthenticationProvider` **sets `hideUserNotFoundExceptions=true` by default**: when `UserDetailsService` throws `UsernameNotFoundException`, the provider normally translates it into **`BadCredentialsException`**. That prevents external callers from easily telling "username does not exist" apart from "wrong password" via surface exception classes or messages.

Consequence:

~~~text
Username does not exist
  -> UserDetailsService: UsernameNotFoundException
  -> DaoAuthenticationProvider default: BadCredentialsException

Username exists, wrong password
  -> UserDetailsService: UserDetails
  -> DaoAuthenticationProvider: BadCredentialsException
~~~

**The same final exception class does not mean the same root cause.** In internal debugging, you can distinguish them via query traces or controlled exception causes, without exposing detailed messages to clients.

### 4.3. `InternalAuthenticationServiceException`: Authentication Source Suffered a Serious Failure

When `UserDetailsService` throws an exception other than `UsernameNotFoundException` due to a broken DB/LDAP/HTTP client, `DaoAuthenticationProvider.retrieveUser(...)` converts that error into `InternalAuthenticationServiceException`. If the service explicitly throws `InternalAuthenticationServiceException`, the provider propagates it. Returning `null` from `UserDetailsService` violates the contract and is also treated by the provider as a service failure.

This signals: **identity could not be verified because the backing service is broken**, not that the user entered wrong evidence or is confirmed absent from the store.

`InternalAuthenticationServiceException` is an `AuthenticationException`; inside `ProviderManager`, this exception category triggers an **immediate stop branch**, so it does not keep trying subsequent or parent providers in a way that masks outages. Conversely, a normal `BadCredentialsException` may let the next provider try when a manager is configured with multiple providers.

**Not every error is constructed directly as `InternalAuthenticationServiceException`**: systems may use `AuthenticationServiceException`, data-library exceptions, or custom errors at different boundaries. For metrics and alerting, classify by **the actual exception and root cause**, not just a message string.

### Quick Reference Table

| Event | What should service/adapter do? | What may provider return? | Internal meaning |
| --- | --- | --- | --- |
| User absent, lookup succeeded | `UsernameNotFoundException` | Typically `BadCredentialsException` under default config | Account not found |
| User exists, wrong password | Return proper `UserDetails` | `BadCredentialsException` | Invalid credentials |
| DB timeout/connection refused | Throw infrastructure error or `InternalAuthenticationServiceException` | `InternalAuthenticationServiceException` | Cannot verify due to infrastructure |
| `loadUserByUsername` returns `null` | Contract bug | Service failure, never success | Source returned invalid data |
| User disabled/locked | Return `UserDetails` with accurate status | `DisabledException` / `LockedException` | Blocked by account policy |
| Valid user, right password | Return accurate `UserDetails` | Authenticated `Authentication` | Ready to proceed to authorization |

## 5. Why Must You Avoid `catch (Exception) { throw new UsernameNotFoundException(...) }`?

A common anti-pattern:

~~~java
// WRONG: convert every error into "no user".
@Override
public UserDetails loadUserByUsername(String username) {
    try {
        return mapAccount(repository.findByUsername(username));
    }
    catch (Exception exception) {
        throw new UsernameNotFoundException("No user");
    }
}
~~~

If the DB runs out of connections, the network drops, LDAP returns 503, or the mapper hits a bug, this code still says "no user". That erases the distinction between "found a negative answer" and "unable to search".

Primary harms:

1. **False statement about identity:** the account may exist, yet the system records it as absent.
2. **Masks outages:** "user not found" metrics spike, dashboards miss the database outage, and operators troubleshoot the wrong thing.
3. **Unintended fallback:** if `ProviderManager` has multiple providers supporting the same token type, a `BadCredentialsException` produced by hiding "user not found" can let a subsequent provider try; the system's authentication policy silently changes during a DB outage.
4. **Hard to recover:** the app may cache negative lookups or trigger "create new account" flows based on a false absence conclusion caused merely by a timeout.
5. **Hard to debug:** the original exception and stack trace are lost if the cause is discarded.
6. **Missed alerts:** alerting pipelines, retries, circuit breakers, and health checks fail to receive the right error category.

The fix is **narrow exception catching**, preserving the cause and keeping operational separation:

~~~java
// Illustrative integration snippet: DB query returns Optional<Account>.
try {
    Account account = repository.findByUsername(username)
            .orElseThrow(() -> new UsernameNotFoundException(
                    "Account not found"));
    return mapAccount(account);
}
catch (DataAccessException ex) {
    throw new InternalAuthenticationServiceException(
            "Account repository unavailable", ex);
}
~~~

`DataAccessException` belongs to Spring DAO; this snippet needs `spring-tx`/appropriate JDBC or JPA dependencies and imports. It does not cover every infrastructure failure type: an HTTP or LDAP client throws different exception classes. Identify the exact exceptions thrown by **the data source you use**, rather than catching `Exception` and assuming every failure is a lost connection.

**Pick the right catch order:** `UsernameNotFoundException` belongs to the business lookup branch; never accidentally swallow it in an overly broad catch block. In the complete program below, we use a custom store exception to avoid adding a database framework.

## 6. Common Mistakes When Using Optional, SQL, LDAP, and APIs

### 6.1. SQL/JPA

A `SELECT ... WHERE username = ?` query that completes with **0 rows** can be mapped to `Optional.empty()`. However, a `SQLException` from connection refused, timeout, unstable network, or exhausted connection pool is not equivalent.

Classification example:

~~~text
SELECT returns 0 rows      -> no record (if query has right scope)
SELECT returns 1 row       -> account exists, read data
CannotGetJdbcConnection    -> DB access error
QueryTimeout               -> cannot conclude whether account exists
Data mapping failure       -> data/contract error, must investigate
~~~

Never convert `DataAccessException` into `Optional.empty()` just to avoid throwing errors up to a controller.

### 6.2. LDAP/Active Directory

A completed search with the right filter/base DN returning 0 entries can be treated as not found. A dropped LDAP connection, failed service-credential bind, TLS negotiation failure, server unavailable response, or unreachable referral **does not prove the user does not exist**.

Pay attention to namespace, base DN, and read permissions: insufficient read permissions can cause incomplete lookups or rejections. Never silently turn "not permitted to query" into "no account".

### 6.3. Remote Identity APIs

Identity API examples:
- `200` with matching payload → user exists.
- `404` under a **specific lookup endpoint contract** → may represent "no user", when the API guarantees 404 specifically carries that meaning.
- `401/403` from upstream → authentication/permissions of **the calling application** are broken, not evidence that the end user's account is absent.
- `429`, `500/502/503/504`, or timeout → cannot conclude the username does not exist.
- `200` with broken schema/required fields → untrustworthy data; report a system or contract error.

**Never assume every HTTP 404 means the same thing**: endpoints and gateways may return 404 for unknown routes, hidden tenants, or suppressed resources. Only map to `UsernameNotFoundException` when the API contract specifies it and the request succeeded within the right namespace.

### 6.4. Reactor/WebFlux or CompletableFuture

In reactive code, `onErrorResume(error -> Mono.empty())` can turn a timeout into "lookup found no user". Likewise, `exceptionally(error -> Optional.empty())` on a Java `CompletableFuture` can swallow network failures. Reserve **empty** for successful lookups with zero results, and **error** for failures. This classification principle holds regardless of whether an app is Servlet or Reactive.

## 7. How Spring Security Hides "Whether a User Exists"

### 7.1. Default hideUserNotFoundExceptions

`AbstractUserDetailsAuthenticationProvider` has the `hideUserNotFoundExceptions` property, defaulting to `true`. With that setting, both `UsernameNotFoundException` and a password mismatch leave the provider as a standard `BadCredentialsException`.

It can be changed to `false`:

~~~java
DaoAuthenticationProvider provider = new DaoAuthenticationProvider();
provider.setHideUserNotFoundExceptions(false);
~~~

This is an **integration snippet**; it only makes sense when the provider is fully configured with a `UserDetailsService` and `PasswordEncoder`. Never set `false` in public applications just for debugging, because differing errors can aid user enumeration.

**Do not misunderstand:** hiding exceptions reduces information leakage; it does not make database queries more reliable. You must still preserve the service-error category when connections break. Hiding details from clients while classifying accurately for operators **can be achieved simultaneously**.

### 7.2. Response Timing Can Also Reveal Users

Even when both cases return "Bad credentials", different code paths can take different times: an existing user triggers real hash verification, whereas a missing user might exit early. `DaoAuthenticationProvider` mitigates timing differences in some paths by checking the password against a dummy hash; that reduces risk, yet **does not guarantee identical timings** across caches, DBs, networks, and environments.

Add rate limiting, brute-force alerts, and uniform error messages. Never invent a predictable static dummy hash or "sleep 500ms" and treat that as a complete solution.

### 7.3. Client-Facing Messages vs. Internal Events Differ

A public error response might only say:

> Unable to sign in with the provided credentials.

While operational telemetry distinguishes:
- `BAD_CREDENTIALS`;
- `ACCOUNT_LOOKUP_MISS` (internal, restricted access);
- `IDENTITY_STORE_UNAVAILABLE`;
- `ACCOUNT_DISABLED`;
- `IDENTITY_DATA_INVALID`.

Internal codes should be standardized and protected from leaking identities, passwords, SQL/JDBC URLs, or specific design details. Metric tags should use bounded label sets to avoid high cardinality.

## 8. ProviderManager and Fallback Risks When a Store Fails

`ProviderManager` iterates through its list of `AuthenticationProvider` instances in order. When a provider throws a normal `BadCredentialsException`, the manager may continue trying the next provider; if a later provider succeeds, that success is used. `InternalAuthenticationServiceException` hits an immediate-stop branch to avoid falling through to other providers.

Example:

~~~text
P1: corporate-user-provider    -> primary LDAP/DB
P2: legacy-user-provider       -> legacy store with some overlapping usernames

If P1 query succeeds: no user
    -> UsernameNotFoundException
    -> default BadCredentialsException
    -> P2 may be tried (depending on supports and config)

If P1 loses connection but code wrongly turns error into UsernameNotFoundException
    -> default BadCredentialsException
    -> P2 may also be tried: fallback policy triggered unintentionally

If P1 loses connection and throws InternalAuthenticationServiceException
    -> ProviderManager stops immediately
    -> does not authenticate via P2 as if lookup succeeded
~~~

**Consequence:** accurate error classification not only keeps logs clear, it also preserves **authentication policy**. If a system genuinely wants a backup path when one store fails, design routing rules, subject-matching conditions, permission policies, and equivalent assurance levels explicitly—never let an accidental catch block decide.

Never deliberately throw `BadCredentialsException` for database errors to force the system to "try another provider" unless that behavior was explicitly designed and tested.

## 9. HTTP Status: 401 Does Not Necessarily Mean "Wrong Password"

`AuthenticationManager.authenticate(...)` is a Java API: it returns an authenticated `Authentication` or throws `AuthenticationException`. It **does not return HTTP status codes itself**.

In Servlet apps, `BasicAuthenticationFilter` and failure handlers/`AuthenticationEntryPoint` catch `AuthenticationException` and produce a **401** response for HTTP Basic. Even when the root cause is an account store outage, default configuration **does not automatically turn it into 503**.

Layer-by-layer comparison:

| Layer | What does it see? | What must it classify? |
| --- | --- | --- |
| Database/LDAP/client | Account present, absent, or access error | Source-level outcome |
| `UserDetailsService` | `UserDetails`, `UsernameNotFoundException`, or infrastructure failure | Preserve distinction between lookup and outage |
| `DaoAuthenticationProvider` | Auth success, `BadCredentialsException`, `InternalAuthenticationServiceException`... | Verify credentials and translate exceptions |
| `ProviderManager` | Final result or exception; certain errors stop immediately | Provider/fallback policy |
| Servlet auth filter/entry point | 401/redirect/custom error response | HTTP protocol policy |
| Monitoring | Safe metrics, logs, and traces | Outage detection and separate investigation |

**Principle for returning statuses:** 401 fits missing/invalid credentials in many APIs; 503 can fit **authentication service temporarily unavailable** if your HTTP/security handler explicitly implements that branch. Never infer status codes solely from exception names, and never expect a standard `@RestControllerAdvice` to return 503 if the failure occurred inside an authentication filter **before** any controller was invoked.

If you need to distinguish 503 at the HTTP layer, design it at the exact authentication entry point/failure handler/filter boundary, test the real execution path, and configure client retries to avoid a thundering herd. In some systems, returning a uniform public response paired with dedicated internal metrics is an intentional security policy decision.

## 10. Runnable Java 17 Demo with Real DaoAuthenticationProvider

The program below intentionally avoids a DB or web server. An in-memory account store simulates **three lookup states**: found, not found, and unreachable. Then real `DaoAuthenticationProvider` verifies `BCryptPasswordEncoder` and `ProviderManager` classifies exceptions.

Key point: **the provider and password matching are real Spring Security machinery**, while "database network disconnected" is simulated via an `available=false` flag. Never put a mock store into production.

### 10.1. Structure and Gradle

~~~text
account-store-errors-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/example/store/
    └── AccountStoreErrorsDemo.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'account-store-errors-demo'
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
    implementation 'org.springframework.security:spring-security-core:6.3.5'
    implementation 'org.springframework.security:spring-security-crypto:6.3.5'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'example.store.AccountStoreErrorsDemo'
}
~~~

Run with JDK 17+ and a compatible Gradle or Gradle Wrapper. Dependencies are pinned to reproduce the example; real applications should use the Spring Boot BOM with current security patches.

### 10.2. Complete Java File

`src/main/java/example/store/AccountStoreErrorsDemo.java`:

~~~java
package example.store;

import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.InternalAuthenticationServiceException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

public class AccountStoreErrorsDemo {

    record StoredAccount(String username, String passwordHash) {}

    // Simulates a real store connection/timeout outage, not a missing user.
    static final class StoreUnavailableException extends RuntimeException {
        StoreUnavailableException(String message) {
            super(message);
        }
    }

    static final class AccountStore {
        private final Map<String, StoredAccount> accounts =
                new ConcurrentHashMap<>();

        private volatile boolean available = true;

        AccountStore(PasswordEncoder encoder) {
            accounts.put("linh",
                    new StoredAccount(
                            "linh", encoder.encode("demo-password")));
        }

        void setAvailable(boolean available) {
            this.available = available;
        }

        Optional<StoredAccount> findByUsername(String username) {
            if (!available) {
                throw new StoreUnavailableException("Simulated outage");
            }
            // Optional.empty only means lookup succeeded with zero rows.
            return Optional.ofNullable(accounts.get(username));
        }
    }

    static final class AccountUserDetailsService
            implements UserDetailsService {
        private final AccountStore store;

        AccountUserDetailsService(AccountStore store) {
            this.store = store;
        }

        @Override
        public UserDetails loadUserByUsername(String username)
                throws UsernameNotFoundException {
            try {
                StoredAccount account = store.findByUsername(username)
                        .orElseThrow(() -> new UsernameNotFoundException(
                                "User missing in account store"));

                return User.withUsername(account.username())
                        .password(account.passwordHash())
                        .authorities("reports.read")
                        .build();
            }
            catch (StoreUnavailableException ex) {
                // Preserve the cause for internal operator investigation.
                throw new InternalAuthenticationServiceException(
                        "Account store unavailable", ex);
            }
        }
    }

    static void expectSuccess(AuthenticationManager manager) {
        Authentication input =
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "linh", "demo-password");

        Authentication output = manager.authenticate(input);
        if (!output.isAuthenticated()
                || !"linh".equals(output.getName())) {
            throw new AssertionError("Unexpected result");
        }
        System.out.println("known-user => SUCCESS authenticated=true");
    }

    static void expectFailure(
            AuthenticationManager manager,
            String label,
            String username,
            String password,
            Class<? extends AuthenticationException> expected) {

        Authentication input =
                UsernamePasswordAuthenticationToken.unauthenticated(
                        username, password);

        try {
            manager.authenticate(input);
            throw new AssertionError(label + " unexpectedly succeeded");
        }
        catch (AuthenticationException failure) {
            if (!expected.isInstance(failure)) {
                throw new AssertionError(
                        label + " wrong exception: "
                        + failure.getClass().getSimpleName(), failure);
            }
            // Only print exception type; never print passwords or raw requests.
            System.out.println(label + " => "
                    + failure.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        PasswordEncoder encoder = new BCryptPasswordEncoder();
        AccountStore store = new AccountStore(encoder);

        UserDetailsService users = new AccountUserDetailsService(store);
        DaoAuthenticationProvider provider =
                new DaoAuthenticationProvider();
        provider.setUserDetailsService(users);
        provider.setPasswordEncoder(encoder);

        // Default hideUserNotFoundExceptions = true.
        AuthenticationManager manager =
                new ProviderManager(List.of(provider));

        expectSuccess(manager);

        expectFailure(manager, "unknown-user",
                "khong-ton-tai", "anything",
                BadCredentialsException.class);

        expectFailure(manager, "wrong-password",
                "linh", "not-the-password",
                BadCredentialsException.class);

        store.setAvailable(false);
        expectFailure(manager, "store-down",
                "linh", "demo-password",
                InternalAuthenticationServiceException.class);
    }
}
~~~

**Explanation of each key point in the code:**

1. `AccountStore.findByUsername(...)` returns `Optional.empty()` **only when the store is available** and the key is absent from the map. When `available=false`, it throws `StoreUnavailableException`.
2. `AccountUserDetailsService` separates two branches: missing account → `UsernameNotFoundException`, store outage → `InternalAuthenticationServiceException` preserving the cause.
3. Standard `DaoAuthenticationProvider` uses the real `PasswordEncoder` to check credentials. No code manually constructs an authenticated token from the username.
4. `ProviderManager` has one provider; failures cannot be overridden by another provider. Multi-provider setups require explicit policies.
5. `expectFailure` only asserts the exception class. The program **never prints usernames/password hashes/credentials** and logs nothing from the simulated store.
6. `UserDetailsService` can throw runtime `InternalAuthenticationServiceException` even though the interface method only declares `UsernameNotFoundException`: both are unchecked exceptions in Java.

### 10.3. Running the Program and Interpreting Output

~~~bash
gradle run --quiet
~~~

If using a Gradle Wrapper, run `./gradlew run --quiet` (on Windows PowerShell: `.\gradlew.bat run --quiet`).

Lines printed by `System.out.println`, excluding build-tool or library logs:

~~~text
known-user => SUCCESS authenticated=true
unknown-user => BadCredentialsException
wrong-password => BadCredentialsException
store-down => InternalAuthenticationServiceException
~~~

The output shows the same credential request type yielding different **data causes** and **final exceptions**. For an unknown user, default `hideUserNotFoundExceptions=true` makes the surface match a wrong password. For a store failure, the provider has no evidence to conclude the user does not exist, so it emits a service failure signal.

**What the demo leaves out:** there is no real network, SQL pool, retry, TLS, servlet filters, HTTP status, session, or multiple providers. Run this console program first to study the `UserDetailsService`/provider boundary; afterward, write integration tests in your real application covering the DB, filters, entry point, and monitoring.

## 11. Critical Tests at the Provider, DB Adapter, and HTTP Layers

A solid test suite needs both **data tests** and **authentication-flow tests**. Asserting only HTTP 401 in both scenarios does not tell you whether the system classified the failure correctly.

| Case | Simulation/fixture | Expected at adapter | Expected at manager |
| --- | --- | --- | --- |
| Account exists, right password | DB has row and is up | Returns `UserDetails` | Success `Authentication` |
| Account does not exist | Query succeeds with 0 rows | `UsernameNotFoundException` | Default `BadCredentialsException` |
| Wrong password | Query has row and valid hash | Returns `UserDetails` | `BadCredentialsException` |
| Connection refused | Store throws connection exception | Service error, cause preserved | `InternalAuthenticationServiceException` |
| Query timeout | Store throws timeout | Service error, not converted to empty | Service error |
| Repository returns null violating contract | Bug in adapter | Caught | Must never return success |
| Account locked/disabled | Row carries lock status | Returns `UserDetails` reflecting status | `LockedException`/`DisabledException` |
| Pool exhausted or LDAP unavailable | Identity source fails | No user-existence conclusion | Service error and metric |
| P2 fallback configured | P1 hits store outage | P1 does not mask as bad credentials | P2 must not bypass the immediate-stop error |
| HTTP Basic missing credentials | Lookup not called | No mandatory lookup | Protected endpoint typically 401 |
| HTTP Basic store down | Failure occurs inside filter | Adapter throws service error | HTTP depends on entry point; metrics must record outage |

### 11.1. Testing the Adapter Directly

Pseudo-assertions for the declared repository:

~~~java
// store, users, and manager belong to the test fixture.
store.setAvailable(true);

assertThrows(UsernameNotFoundException.class,
        () -> users.loadUserByUsername("missing"));

store.setAvailable(false);

assertThrows(InternalAuthenticationServiceException.class,
        () -> users.loadUserByUsername("linh"));
~~~

This is a **JUnit 5 integration snippet**: it needs `org.junit.jupiter.api.Assertions.assertThrows` and proper fixtures; not a standalone program. At the adapter layer, also assert the exception cause to verify diagnostic context is preserved; in public HTTP, never leak the cause externally.

### 11.2. Testing the Real Manager

Beyond testing adapter exceptions, test the provider:

~~~java
// Store is available, yet username does not exist:
assertThrows(BadCredentialsException.class,
        () -> manager.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "missing", "password")));

// Store is down:
store.setAvailable(false);
assertThrows(InternalAuthenticationServiceException.class,
        () -> manager.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "linh", "password")));
~~~

These assertions are also **JUnit integration snippets**. The complete `main` demo in section 10 already runs equivalent verification without JUnit.

### 11.3. Testing HTTP Separately Without Guessing from Exceptions

If the application uses Spring Security Servlet HTTP Basic, write integration tests (such as `MockMvc` with security filters enabled) to verify the HTTP status the entry point actually returns. The same `InternalAuthenticationServiceException` in a provider may produce 401 under the default Basic entry point, or another code if the app adds custom classification. Record actual behavior and test against your public policy.

Never run a `@WithMockUser` test and conclude database exceptions are handled: that annotation injects a mock user into the security context, bypassing `UserDetailsService` and `DaoAuthenticationProvider` completely.

### 11.4. Testing Across Multiple Instances and Multiple User Sources

Simulate the database going down in one replica, LDAP timing out in another, and connections dropping mid-authentication. Assert:
- No instance produces an authenticated result from untrusted data.
- Infrastructure failures are never misclassified as missing accounts.
- Fallbacks execute only when explicitly allowed by policy.
- Metrics let operators distinguish outages from users mistyping passwords.
- Caches never serve expired user entries when policy demands fresh data; define concrete invalidation/staleness policies.

## 12. Observability: Distinguishing Outages Without Exposing Users

For operations, track at least:

| Event group | Recommended internal metric/log | Never record |
| --- | --- | --- |
| Lookup miss | `account_lookup_outcome=NOT_FOUND` | Raw username/PII unless necessary |
| Store unavailable | `account_lookup_outcome=STORE_UNAVAILABLE`, timeout/connection type, dependency name | Connection strings containing credentials |
| Bad password | `auth_outcome=BAD_CREDENTIALS` | Password, password hash, Basic/Bearer header |
| Account disabled | `auth_outcome=ACCOUNT_DISABLED` | Sensitive profile fields |
| Success | `auth_outcome=SUCCESS`, mechanism, elapsed time | Full `Authentication.toString()` |
| Data contract violation | `account_lookup_outcome=INVALID_DATA`, normalized schema error | Sensitive upstream response bodies |

**Never label metrics by username** to avoid high cardinality and identity leaks. If auditing by principal is required, use a verified identifier or policy-compliant pseudonym with strict access control and retention.

### 12.1. Alerting on the Right Error Categories

A spike in `STORE_UNAVAILABLE` over a few minutes points to a broken database/LDAP/identity API. A spike in `BAD_CREDENTIALS` points to users mistyping passwords or brute-force activity. The two require different responses.

If code turns everything into `UsernameNotFoundException`, metrics and incident response lose meaning. Build dashboards around distinct adapter-level outcomes while keeping client responses uniform to curb user enumeration.

### 12.2. Correlation IDs and Exception Causes

Propagate a safe request/correlation ID from the gateway to service and provider logs. When logging store failures, preserve the **exception cause** in controlled logs without printing secrets or PII-laden queries. Return a generic message to clients, never leaking stack traces or internal hostnames.

When calling a remote identity API, add bounded timeouts, selective retries/circuit breakers, exponential backoff, and dependency monitoring. Retries must never turn a final failure into `Optional.empty()`; once exhausted, it remains a service failure.

## 13. Reading Logs by Real-World Case

### Case A — User Not Found

~~~text
request=R-101
store.lookup outcome=NOT_FOUND
provider.failure=BadCredentialsException
http.response=401  (e.g., Basic configuration)
~~~

**Explanation:** the store returned a reliable negative result; the service threw `UsernameNotFoundException`, yet the provider masked it at the surface. Internal logs capture the miss; the client learns nothing about whether the username exists.

### Case B — Wrong Password

~~~text
request=R-102
store.lookup outcome=FOUND
provider.failure=BadCredentialsException
http.response=401
~~~

**Explanation:** differs from A in **internal lookup outcome**, though the authentication result sent to the client can look identical.

### Case C — Account Store Outage

~~~text
request=R-103
store.lookup outcome=STORE_UNAVAILABLE
provider.failure=InternalAuthenticationServiceException
http.response=<depends on failure/entry point config>
dependency_alert=IDENTITY_STORE_UNAVAILABLE
~~~

This is an **illustrative trace**, not a default log format. Even if the app returns 401 for system errors, logs/metrics must still classify outages separately; if designed to return 503, verify filter paths and retry policies.

**Never assume:** a 401 means the user does not exist, or an HTTP 500/503 means the password was wrong. HTTP status is the presentation layer; the root cause sits at the account lookup/provider layer.

## 14. Design Mistakes to Avoid

1. **Catching every exception and throwing `UsernameNotFoundException`.** Disguises outages as not-found results, breaking fallbacks and monitoring.
2. **Returning `null` on query errors.** Violates the `UserDetailsService` contract and still fails to authenticate safely.
3. **Returning a default/guest user with a hardcoded password when the DB is down.** Enables bypasses and grants unverified permissions.
4. **Returning `Optional.empty()` on timeout.** Equates "absent" with "unable to determine".
5. **Treating HTTP 404 from an identity API as permanent proof without checking the contract.** Could be a broken route, hidden tenant, or unauthorized upstream access.
6. **Setting `setHideUserNotFoundExceptions(false)` in public production to ease debugging.** Can expose user enumeration.
7. **Returning raw exception messages/causes over HTTP.** Leaks internal details, usernames, SQL, and network topology.
8. **Assuming database down always returns HTTP 503.** Filters/entry points may return 401 or another response; configure and test explicitly.
9. **Measuring failed logins solely by HTTP 401 counts.** Lumps missing credentials, wrong passwords, and outages into one metric.
10. **Using `BadCredentialsException` to represent connection errors.** Can cause `ProviderManager` to fall back unexpectedly.
11. **Treating stale user cache hits as proof the identity source is healthy.** Cache hits can mask outages, and account data may have changed.
12. **Testing only account-not-found without testing timeouts or exhausted pools.** Misses the most critical failure branch.
13. **Having multiple providers sharing usernames without defining realms and ordering.** One store may authenticate in place of another under an unintended policy.
14. **Retrying infinitely when the identity source is down.** Overloads and amplifies outages; apply timeouts, bounded retries, and circuit breakers.
15. **Replacing root causes with generic messages without safe logging.** Leaves operators blind during incidents.
16. **Skipping authorization after authentication.** Even when a user enters the right password, endpoints must still enforce authorities/permissions.

## 15. Self-Check Questions

**Question 1:** `UserDetailsService` receives `Optional.empty()` when a database query completes with 0 rows. What should it do?  
**Answer:** Map it to `UsernameNotFoundException` if username/tenant were queried in the right scope and the result unambiguously means no account exists.

**Question 2:** That same query hits `CannotGetJdbcConnectionException`. Can we throw `UsernameNotFoundException` for convenience?  
**Answer:** No. Being unable to reach the database says nothing about whether the account exists. Preserve the infrastructure error or translate it into `InternalAuthenticationServiceException` with its cause.

**Question 3:** Why do non-existent usernames and wrong passwords usually both surface as `BadCredentialsException`?  
**Answer:** `hideUserNotFoundExceptions=true` is the default on the username/password provider, helping limit account disclosure in public errors. This masks details at the authentication boundary without losing root-cause separation in operational telemetry.

**Question 4:** The store times out, yet code catches `Exception` and throws `UsernameNotFoundException`. If a legacy login provider follows next, what is dangerous?  
**Answer:** The failure may be masked as `BadCredentialsException` and `ProviderManager` will try the next provider, unintentionally altering fallback policy. A proper service exception preserves "cannot verify" and stops the chain.

**Question 5:** A store outage makes the provider throw `InternalAuthenticationServiceException`. Will the client definitely receive HTTP 503?  
**Answer:** No. Filters, entry points, and failure handlers determine the response; default HTTP Basic may return 401 for `AuthenticationException`. Test explicitly if your product requires a different status.

**Question 6:** Why avoid logging raw usernames/passwords when distinguishing missing users from store outages?  
**Answer:** Outcomes, request IDs, and error types are sufficient for triage. Credentials and PII in logs create risk; use internal codes or policy-compliant masked/hashed identifiers if needed.

**Question 7:** The store returns a row with `enabled=false`. Is that "user not found"?  
**Answer:** No. The account exists but is blocked by status, normally resulting in `DisabledException`. Never strip status info to pretend the account is absent at the service layer.

**Question 8:** Does a passing `@WithMockUser` test prove the DB adapter classifies errors properly?  
**Answer:** No. It bypasses `UserDetailsService` and `DaoAuthenticationProvider`; test the adapter/provider with real query failures or fault injection.

**Question 9:** A remote identity API returns 403 to the querying service. Does that mean the user does not exist?  
**Answer:** No. That usually indicates broken permissions/authentication on the upstream-calling client. Only a properly authorized lookup returning a trustworthy answer justifies concluding absence.

**Question 10:** Is returning the exact same public response for missing user, wrong password, and store outage necessarily wrong?  
**Answer:** Not necessarily; some policies intentionally mask differences. However, **metrics, safe logging, retries, and internal exception classification** must still remain accurate—otherwise outages get hidden or fallbacks misfire.

## 16. Checklist When Integrating a Real Account Store

Before putting `UserDetailsService` into an authentication flow:

- **Lookup key:** are username/tenant/realm uniquely and reliably defined?
- **Successful lookup:** are 0 rows clearly separated from malformed-data errors?
- **Source contract:** how do DB/LDAP/identity APIs report timeouts, 401/403/429/503, and schema errors?
- **Exception adapter:** does it throw `UsernameNotFoundException` only on confirmed absence, preserving causes for infrastructure failures?
- **Provider defaults:** is `hideUserNotFoundExceptions` configured safely? Have timing and user enumeration been reviewed?
- **Fallback:** can other providers or parent managers authenticate when the primary source fails?
- **Public HTTP:** do responses leak user existence, infrastructure details, or stack traces? Are real handlers/filters tested?
- **Observability:** are there separate outcomes for lookup miss, bad credentials, store unavailable, and disabled?
- **Resilience:** are timeouts/retries/circuit breakers bounded and prevented from turning outages into empty results?
- **Caching:** if using `UserCache`, are stale-data, eviction, and invalidation policies defined for account changes?
- **Authorization:** does authentication success still enforce business authorities/tenant/resource checks?
- **Testing:** are cases covered for missing user, wrong password, locked/disabled, DB down, timeout, bad mapping, multi-provider, and caching?

**Key takeaway:** **"No user exists" is the conclusion of a successful lookup; "connection failure" means no conclusion could be reached.** Spring Security may intentionally mask "user missing" into `BadCredentialsException` to protect account privacy, yet application code must preserve the separation from service failures. Only with accurate classification can a system authenticate safely, monitor operational health accurately, and avoid silently shifting policy when an identity store fails.

### References

- Spring Security — `DaoAuthenticationProvider`: https://docs.spring.io/spring-security/reference/6.3/servlet/authentication/passwords/dao-authentication-provider.html
- Spring Security — `UserDetailsService`: https://docs.spring.io/spring-security/reference/6.3/servlet/authentication/passwords/user-details-service.html
- Spring Security — `AbstractUserDetailsAuthenticationProvider` Javadoc: https://docs.spring.io/spring-security/site/docs/6.3.10/api/org/springframework/security/authentication/dao/AbstractUserDetailsAuthenticationProvider.html
- Spring Security — `InternalAuthenticationServiceException` Javadoc: https://docs.spring.io/spring-security/site/docs/6.3.10/api/org/springframework/security/authentication/InternalAuthenticationServiceException.html
- Spring Security — `AuthenticationManager` / `ProviderManager`: https://docs.spring.io/spring-security/reference/6.3/servlet/authentication/architecture.html
- Spring Security — source `DaoAuthenticationProvider`: https://github.com/spring-projects/spring-security/blob/6.3.5/core/src/main/java/org/springframework/security/authentication/dao/DaoAuthenticationProvider.java
