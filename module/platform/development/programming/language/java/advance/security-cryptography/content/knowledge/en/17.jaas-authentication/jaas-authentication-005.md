# 17.5. The LoginModule Lifecycle: initialize, login, commit, abort, and logout

**JAAS** (Java Authentication and Authorization Service) allows a Java application to change its authentication mechanism without rewriting the orchestration logic. The application calls `javax.security.auth.login.LoginContext`; one or more authentication providers implement `javax.security.auth.spi.LoginModule`.

The key takeaway of this lesson: **JAAS authenticates in two phases**. The `login()` phase verifies credentials and stores the success state **temporarily inside the module**. After the modules are evaluated according to their control flags, `LoginContext` calls **`commit()` if overall authentication succeeds** or **`abort()` if overall authentication fails**. `logout()` is a separate operation when the application wants to end an already authenticated session. `initialize()` passes the context so the module can begin working.

This lesson belongs to **17. JAAS Authentication**, focusing on the full five-method lifecycle, the execution paths on success and failure, the responsibility for updating and cleaning up `Subject`, coordinating multiple modules, and a compilable and runnable Java 21 example.

## Learning Objectives

- Know the roles of `LoginContext`, `LoginModule`, `Configuration`, `AppConfigurationEntry`, `CallbackHandler`, `Subject`, and `Principal`.
- Correctly explain `initialize → login → commit/abort` and `logout`, including the case where one module succeeds while another causes the overall login to fail.
- Distinguish `true`, `false`, and `LoginException` from `login/commit/abort/logout`; never use `false` to mask a wrong password.
- Understand the `REQUIRED`, `REQUISITE`, `SUFFICIENT`, and `OPTIONAL` control flags.
- Write a module that adds principals only in `commit`, removes only what the module truly owns in `abort`/`logout`, and clears passwords.
- Run three scenarios in Java 21: valid login, wrong password, and a subsequent `REQUIRED` module rejecting; interpret the trace and principal count.
- Design tests for partial failure, unsupported callbacks, read-only `Subject`, duplicate principals, retry/logout, and secrets.
- Distinguish JAAS authentication from web sessions, MFA, password hashing, business authorization, and database rollback.

## 1. JAAS Architecture Before Discussing the Lifecycle

`LoginContext` is the application's entry point. It reads `Configuration` by application name, instantiates the `LoginModule`s, and decides which modules must succeed. Each `LoginModule` authenticates using its plugged-in mechanism without unilaterally declaring the overall system result.

```text
Application
  |
  +--> new LoginContext("demo", Subject?, CallbackHandler, Configuration)
  |
  +--> LoginContext.login()
          |
          +--> LoginModule A: checks username/password
          +--> LoginModule B: checks other conditions if required by configuration
          |
          +--> JAAS aggregates results according to control flags
                   |
                   +--> SUCCESS: commit()
                   +--> FAILURE: abort()
  |
  +--> LoginContext.getSubject() on success
  |
  +--> LoginContext.logout() when ending the session
```

| Component | Responsibility |
| --- | --- |
| `LoginContext` | Manages the login flow, selects modules, coordinates commit/abort/logout, and provides the Subject |
| `LoginModule` | Executes an authentication method and maintains its own private state |
| `Configuration` | Defines the application name, module list, control flags, and options |
| `AppConfigurationEntry` | Configures a LoginModule with its class, flag, and options map |
| `CallbackHandler` | Supplies callbacks to gather input such as `NameCallback` and `PasswordCallback` |
| `Subject` | Object holding the principals and public/private credentials of an authenticated subject |
| `Principal` | Identifier, group, or role in the application's model; not an absolute permission |
| `sharedState` | Shared map across modules during the same process; requires conventions and cleanup |
| `options` | Per-module configuration map; not a password store |

An application can call `LoginContext.login()` without knowing whether Kerberos, passwords, smart cards, or a custom module is used underneath. Every model must still obey the **JAAS state rules**.

## 2. The Interface Contract: Five Methods That Cannot Swap Roles

The standard interface `javax.security.auth.spi.LoginModule` (already built into the JDK—**do not rewrite it**) has the signature:

```java
void initialize(Subject subject,
                CallbackHandler callbackHandler,
                Map<String, ?> sharedState,
                Map<String, ?> options);

boolean login() throws LoginException;
boolean commit() throws LoginException;
boolean abort() throws LoginException;
boolean logout() throws LoginException;
```

| Method | Phase | What it receives/reads | What it performs |
| --- | --- | --- | --- |
| `initialize` | Preparation | Subject, handler, shared state, options | Stores context/configuration; does not authenticate yet |
| `login` | Phase 1 | Credentials/identity from callbacks or provider | Authenticates and holds **temporary** state |
| `commit` | Phase 2, on overall acceptance | The module's `login` result | Adds Principal/Credentials to Subject, marks committed |
| `abort` | Phase 2, on overall rejection | Login/commit state needing rollback | Cleans pending state and anything the module added if applicable |
| `logout` | After an accepted login | Committed state | Cleans Principal/Credentials owned by the module and closes related session state |

**There is no public `LoginContext.initialize()` for applications to call to initialize individual modules.** `LoginContext` itself instantiates and calls `LoginModule.initialize(...)` as each module is processed. JAAS documentation describes two phases, but initialization of different modules can be interleaved with `login` rather than strictly "initializing all modules before calling `login` on any module."

A `LoginModule` needs a public no-argument constructor so `LoginContext` can instantiate it via reflection. If placed as a nested class, it must be `public static` and its binary class name must be configured properly.

## 3. Phase 1: `initialize` and `login`

### 3.1 `initialize(...)` Receives Context, Grants No Authority

```java
@Override
public void initialize(Subject subject, CallbackHandler handler,
                       Map<String, ?> sharedState,
                       Map<String, ?> options) {
    this.subject = subject;
    this.handler = handler;
}
```

This is only an **illustrative snippet inside a class**, not a standalone runnable program. `initialize` returns `void` and must not add Principals or public/private credentials to the Subject as though the user were already authenticated.

- `subject` is the object to be updated later, typically in `commit`.
- `handler` may be `null`. If the module needs interactive input, it must handle this case with a controlled failure in `login`.
- `sharedState` may contain data shared by other modules; if secrets are shared, you must define who owns them, who clears them, and avoid leaks across login attempts.
- `options` come from the module configuration such as realm, debug flag, or endpoint. Validate them and never log passwords/secrets.

Never use `static` fields to store a user's `Subject` or credentials: different sessions may run concurrently, causing identity leakage.

### 3.2 `login()` Verifies Credentials and Stores Private State

```java
boolean login() throws LoginException;
```

A proper implementation typically calls `CallbackHandler.handle(...)`, retrieves a username/password or token, validates it with the designed authentication mechanism, then sets `authenticated=true` and retains `pendingPrincipal` upon success.

**Do not add principals to the Subject in `login()`.** If module A succeeds while `REQUIRED` module B fails, the overall login must `abort`; adding principals too early leaves the Subject containing an unaccepted identity.

Three outcomes must be distinguished:

| Outcome | Meaning |
| --- | --- |
| `return true` | The module authenticated successfully. This does **not** guarantee the entire LoginContext will succeed. |
| `return false` | The module chooses to **be ignored** or does not apply to the current case. Do not treat this as a wrong password. |
| `throw FailedLoginException` or `LoginException` | Authentication genuinely failed or could not complete; LoginContext handles it according to the module's flag. |

If a module receives a password and determines the password is **incorrect**, do not `return false` to silently ignore it. In a stack with `OPTIONAL`/`SUFFICIENT`, returning the wrong value can allow another authentication method to succeed when policy actually required the factor that was skipped.

`LoginModule.login()` should not perform its own retry/backoff loops or sleep-waits. Per JAAS guidance, retries belong to the caller/application and login protection policies; the module should report success or failure clearly.

### 3.3 Clearing Data from `PasswordCallback`

`PasswordCallback.getPassword()` returns `char[]`. After use, code should clear its own copy (`Arrays.fill`), call `PasswordCallback.clearPassword()` in a `finally` block, and never log the password. Clearing one array does not erase every possible copy inside the JVM/provider. When the original input is an immutable `String`—especially in web frameworks—you cannot guarantee erasing all secret copies from the heap.

A production module must never compare passwords against literals in source code. It needs a secure verifier store (Argon2id or PBKDF2 with salt and policy-configured work factor), brute-force/rate-limit protection, and multi-factor authentication where needed.

## 4. Phase 2 Success: `commit()`

```java
boolean commit() throws LoginException;
```

When `LoginContext` determines that the **overall login** succeeded according to the control flags, the commit phase runs on the relevant modules. A module where `login() == true` converts the authenticated identity into `Principal`s and/or credentials inside the `Subject`.

Mental model:

```text
login() -> authenticated=true, pendingPrincipal=UserPrincipal("alice")
overall LoginContext login succeeds
commit() -> subject.getPrincipals().add(pendingPrincipal)
           -> record what was actually added
           -> clear pending state/secrets no longer needed
           -> return true
```

If a module did not authenticate successfully or was ignored, `commit()` typically clears state and `return false`. If commit is **required but fails**—for example, a read-only Subject or a provider failing to create a credential—`throw LoginException`; never return `true` when the Subject is left in an inconsistent state.

### 4.1 Principal Ownership Matters

For example:

```java
boolean added = subject.getPrincipals().add(new UserPrincipal("alice"));
```

If the Subject already contains an equal Principal by value, the set may return `false`. The module **must not remove** that principal during logout, because it was not added by this module. Track the module's own object such as `ownedPrincipal`, and remove it only if truly owned. This is especially critical when multiple LoginModules add identities or roles.

`commit` is not a database transaction. Side effects against APIs, databases, or token stores must have their own transaction boundaries or compensating actions; JAAS **does not automatically roll back** an issued token or a written database row.

## 5. Phase 2 Failure: `abort()`

```java
boolean abort() throws LoginException;
```

When the **overall** login fails, `LoginContext` switches to the abort branch. This happens even if **module A itself authenticated successfully** but another `REQUIRED`/`REQUISITE` module failed.

`abort()` must:

1. Clear pending identities, sensitive data, and authentication state created in `login`.
2. If state was partially committed before a failure was detected, remove only the `Principal`/credentials **added by that module**.
3. Close temporary resources/revoke temporary grants per policy; never remove contributions from other modules.
4. Reset internal state so old login results cannot be reused on a subsequent attempt.
5. Return `true` when cleanup of participated state succeeds, `false` when the module was ignored/never authenticated, or throw `LoginException` if required cleanup fails.

Even a module that failed during `login` can receive `abort()`. Therefore cleanup methods must be safe when state is nearly empty.

**Do not confuse abort with logout:** abort ends an **unaccepted login attempt**; logout ends an **already successful session**.

## 6. `logout()`: Cleaning Up Only This Module's Committed Contributions

```java
boolean logout() throws LoginException;
```

When the application calls `LoginContext.logout()`, JAAS invokes `logout` on the modules according to the configuration. A module should remove the Principals and credentials it added in `commit`, destroy secrets it manages, and reset state.

Common pitfalls:

- **Do not** call `subject.getPrincipals().clear()` because that can wipe out identities from other modules.
- **Do not** remove principals solely by class or name if you do not know whether this module actually added them.
- When `Subject.isReadOnly() == true`, mutating the principals set is forbidden; handle according to contract (destroying credentials may have separate rules), and throw `LoginException` if required cleanup cannot be performed.
- `logout()` does not automatically terminate an HTTP session, delete browser cookies, or revoke OAuth tokens unless the module/application explicitly implements that.
- Test cleanup across repeated invocations and realistic state transitions to avoid double-release bugs and secret leaks.

| Scenario | Method to focus on | Subject state |
| --- | --- | --- |
| Valid password, all modules pass | `commit` | Contains authenticated principals/credentials |
| Wrong password | `abort` | Must not contain any new principal |
| Module A passes, REQUIRED module B fails | `abort` on A and B | Must retain no state from the failed login |
| Successful session later logged out by user | `logout` | Contributions owned by the module are removed |
| Read-only Subject | `commit/abort/logout` may report cleanup failure | Do not bypass immutability checks |

## 7. Control Flags Determine the Overall Path

`AppConfigurationEntry.LoginModuleControlFlag` has four types:

| Flag | On success | On failure |
| --- | --- | --- |
| `REQUIRED` | Required to succeed, then continues evaluating remaining modules | Overall login will fail; typically continues evaluating remaining modules before reporting failure |
| `REQUISITE` | Required to succeed, then continues | Stops early on failure; overall login fails |
| `SUFFICIENT` | May finish early with success if no prior `REQUIRED`/`REQUISITE` failure occurred | Individual failure does not necessarily cause overall failure |
| `OPTIONAL` | May contribute to success | Individual failure does not necessarily cause overall failure; when no required module exists, at least one `SUFFICIENT`/`OPTIONAL` must still succeed |

For example:

```text
PasswordModule REQUIRED  → login true
DenyModule     REQUIRED  → login throws FailedLoginException
----------------------------------------------
overall failure → PasswordModule.abort(), DenyModule.abort()
```

Even though `PasswordModule` returned `true`, **no Principal may be committed** because another `REQUIRED` module failed. That is the purpose of the two-phase mechanism.

`SUFFICIENT` can short-circuit; therefore **do not assume every module will always receive every callback**. Module order and flags change control flow. Returning `false` from `login` means the module wishes to be ignored, which differs from throwing an exception when credentials are genuinely invalid. Flag configuration is part of security policy and needs integration tests, not only per-module unit tests.

## 8. Standalone Java 21 Program: Three Lifecycle Branches

The example includes two nested modules:

- `PasswordModule` authenticates username `alice` with **lab-only** password `lab-secret`. It does not add a Principal in `login`; it adds it only in `commit`. `cleanup` removes only the Principal owned by the module itself.
- `DenyModule` throws `FailedLoginException` to simulate a second `REQUIRED` module rejecting, thereby triggering `abort` across the stack.

`Configuration` is constructed **programmatically**, with no `jaas.conf` file required. The password literal and `Arrays.equals` comparison are **JAAS flow-testing code**, not a secure production password-checking algorithm. There is no real UI callback or real database.

Create the file **`JaasLifecycleDemo.java`**:

```java
import java.io.IOException;
import java.security.Principal;
import java.util.Arrays;
import java.util.Map;
import javax.security.auth.Subject;
import javax.security.auth.callback.Callback;
import javax.security.auth.callback.CallbackHandler;
import javax.security.auth.callback.NameCallback;
import javax.security.auth.callback.PasswordCallback;
import javax.security.auth.callback.UnsupportedCallbackException;
import javax.security.auth.login.AppConfigurationEntry;
import javax.security.auth.login.Configuration;
import javax.security.auth.login.FailedLoginException;
import javax.security.auth.login.LoginContext;
import javax.security.auth.login.LoginException;
import javax.security.auth.spi.LoginModule;

public final class JaasLifecycleDemo {
    public record UserPrincipal(String name) implements Principal {
        @Override public String getName() { return name; }
    }

    public static final class PasswordModule implements LoginModule {
        private Subject subject;
        private CallbackHandler handler;
        private UserPrincipal pending;
        private UserPrincipal owned;
        private boolean authenticated;
        private boolean committed;

        @Override public void initialize(Subject subject, CallbackHandler handler,
                                         Map<String, ?> sharedState,
                                         Map<String, ?> options) {
            System.out.println("password initialize");
            this.subject = subject;
            this.handler = handler;
        }

        @Override public boolean login() throws LoginException {
            System.out.println("password login");
            authenticated = false;
            pending = null;
            if (handler == null) throw new LoginException("Handler required");
            NameCallback name = new NameCallback("User: ");
            PasswordCallback password = new PasswordCallback("Password: ", false);
            try {
                handler.handle(new Callback[]{name, password});
                char[] supplied = password.getPassword();
                char[] expected = "lab-secret".toCharArray();
                try {
                    if (!"alice".equals(name.getName()) ||
                        !Arrays.equals(supplied, expected)) {
                        throw new FailedLoginException("Invalid credentials");
                    }
                    pending = new UserPrincipal(name.getName());
                    authenticated = true;
                    return true;
                } finally {
                    if (supplied != null) Arrays.fill(supplied, '\0');
                    Arrays.fill(expected, '\0');
                }
            } catch (IOException | UnsupportedCallbackException e) {
                LoginException failure = new LoginException("Callback error");
                failure.initCause(e);
                throw failure;
            } finally {
                password.clearPassword();
            }
        }

        @Override public boolean commit() throws LoginException {
            System.out.println("password commit");
            if (!authenticated) return false;
            if (subject.isReadOnly()) throw new LoginException("Read-only Subject");
            boolean added = subject.getPrincipals().add(pending);
            owned = added ? pending : null; // Never remove another module's Principal.
            committed = true;
            pending = null;
            return true;
        }

        private void cleanup() throws LoginException {
            if (owned != null) {
                if (subject.isReadOnly())
                    throw new LoginException("Cannot remove from read-only Subject");
                subject.getPrincipals().remove(owned);
            }
            pending = null;
            owned = null;
            authenticated = false;
            committed = false;
        }

        @Override public boolean abort() throws LoginException {
            System.out.println("password abort");
            boolean participated = authenticated || committed;
            cleanup();
            return participated;
        }

        @Override public boolean logout() throws LoginException {
            System.out.println("password logout");
            cleanup();
            return true;
        }
    }

    public static final class DenyModule implements LoginModule {
        @Override public void initialize(Subject s, CallbackHandler h,
                                         Map<String, ?> sharedState,
                                         Map<String, ?> options) {
            System.out.println("deny initialize");
        }
        @Override public boolean login() throws LoginException {
            System.out.println("deny login");
            throw new FailedLoginException("Second REQUIRED module rejects");
        }
        @Override public boolean commit() {
            System.out.println("deny commit");
            return false;
        }
        @Override public boolean abort() {
            System.out.println("deny abort");
            return false;
        }
        @Override public boolean logout() {
            System.out.println("deny logout");
            return true;
        }
    }

    static Configuration configuration(boolean addDeny) {
        return new Configuration() {
            @Override public AppConfigurationEntry[] getAppConfigurationEntry(
                    String name) {
                if (!"demo".equals(name)) return null;
                AppConfigurationEntry password = new AppConfigurationEntry(
                        PasswordModule.class.getName(),
                        AppConfigurationEntry.LoginModuleControlFlag.REQUIRED,
                        Map.of());
                if (!addDeny) return new AppConfigurationEntry[]{password};
                AppConfigurationEntry deny = new AppConfigurationEntry(
                        DenyModule.class.getName(),
                        AppConfigurationEntry.LoginModuleControlFlag.REQUIRED,
                        Map.of());
                return new AppConfigurationEntry[]{password, deny};
            }
        };
    }

    static CallbackHandler handler(String value) {
        return callbacks -> {
            for (Callback callback : callbacks) {
                if (callback instanceof NameCallback name) {
                    name.setName("alice");
                } else if (callback instanceof PasswordCallback password) {
                    password.setPassword(value.toCharArray());
                } else {
                    throw new UnsupportedCallbackException(callback);
                }
            }
        };
    }

    public static void main(String[] args) throws Exception {
        System.out.println("-- success --");
        LoginContext good = new LoginContext("demo", null,
                handler("lab-secret"), configuration(false));
        good.login();
        System.out.println("principal count after commit: " +
                good.getSubject().getPrincipals(UserPrincipal.class).size());
        good.logout();
        System.out.println("principal count after logout: " +
                good.getSubject().getPrincipals(UserPrincipal.class).size());

        System.out.println("-- wrong password --");
        LoginContext wrong = new LoginContext("demo", null,
                handler("wrong"), configuration(false));
        try {
            wrong.login();
            throw new AssertionError("Unexpected success");
        } catch (LoginException expected) {
            System.out.println("wrong password rejected: true");
        }

        System.out.println("-- later REQUIRED failure --");
        LoginContext denied = new LoginContext("demo", null,
                handler("lab-secret"), configuration(true));
        try {
            denied.login();
            throw new AssertionError("Unexpected success");
        } catch (LoginException expected) {
            System.out.println("required module failure rejected: true");
        }
    }
}
```

### 8.1 Compiling and Running

Use JDK 21 or a compiler supporting `--release 21`:

```text
java -version
javac -version
javac --release 21 -encoding UTF-8 JaasLifecycleDemo.java
java JaasLifecycleDemo
```

**Verified exact stdout:**

```text
-- success --
password initialize
password login
password commit
principal count after commit: 1
password logout
principal count after logout: 0
-- wrong password --
password initialize
password login
password abort
wrong password rejected: true
-- later REQUIRED failure --
password initialize
password login
deny initialize
deny login
password abort
deny abort
required module failure rejected: true
```

Three results to understand:

**Success:** `login` authenticates temporarily, and only `commit` adds a `UserPrincipal` to the Subject. `logout` removes the exact Principal added by the module, dropping the count from **1 to 0**.

**Wrong password:** `FailedLoginException` is thrown immediately inside `login`; `abort` cleans up state, **there is no `password commit` line**, and the caller receives a `LoginException`.

**Later module fails:** `PasswordModule.login` succeeded, `DenyModule.login` rejected while flagged `REQUIRED`, and then `abort` was invoked on both; neither module was committed. The trace also demonstrates that `deny initialize` can occur **after** `password login`, because JAAS may initialize each module on demand.

The program uses public nested modules with a no-arg constructor; `AppConfigurationEntry` gets the binary class name from `PasswordModule.class.getName()`, avoiding naming mistakes when loading nested classes. These results were compiled and run with `javac --release 21` on a standard JDK with JAAS.

### 8.2 Explaining State Choices in the Code

- `pending` is populated only after valid credentials and does not put a principal on the Subject by itself.
- `authenticated` stores the Phase 1 result per instance, avoiding passing "success" through a shared static variable.
- `owned` is assigned only if `subject.getPrincipals().add(pending)` returns `true`. If an equal Principal already exists, the module does not claim ownership and will not delete someone else's principal on logout.
- `commit` checks `subject.isReadOnly()` before mutating; if unable to commit, it throws `LoginException`.
- `cleanup` removes `owned` and resets `pending` and booleans to a clean state. `abort` invokes cleanup even when `login` did not succeed.
- `DenyModule.abort` returns `false` because the module had no successful state to commit; this is not a successful login being rolled back.
- `PasswordCallback.clearPassword()` and `Arrays.fill` wipe the arrays that can be wiped; the String literal in the demo remains subject to JVM semantics and is not a production secret-handling technique.

## 9. External Configuration via a JAAS File and How It Differs from the Example

Another common approach is using a JAAS configuration file:

```text
demo {
    JaasLifecycleDemo$PasswordModule required;
    JaasLifecycleDemo$DenyModule required;
};
```

The `$` is part of the nested class's **binary class name** in the example. In a real project, a LoginModule is usually a top-level class in a managed package. Each stanza specifies the class name, flag, and options; the file must reside in a readable deployment location and must not contain hardcoded passwords.

When using an installed `Configuration` loaded from a file, the application typically calls `new LoginContext("demo", callbackHandler)` or an equivalent. The location can be configured via `java.security.auth.login.config` according to the JDK/deployment mechanism. **The Java example in Section 8 does not use this file** because it passes an in-memory `Configuration` directly to the constructor; do not create the file expecting the program to read it automatically.

The file's `required` corresponds to `AppConfigurationEntry.LoginModuleControlFlag.REQUIRED`, but you must verify module order and options. Never rely on default permissions or an `other` entry without understanding who is being authenticated.

## 10. Edge Cases to Test When Writing a LoginModule

### 10.1 One Module Succeeds While Another Fails

This is a critical scenario for proving **Subject consistency**. Tests must verify that `commit` is **not** called on a module before overall acceptance, and that after `abort` no pending identities or external tokens remain.

### 10.2 Commit Fails After Creating Partial State

For example, a module adds a group Principal and then fails during credential creation. `commit` must throw `LoginException`; cleanup/abort must remove the group Principal **owned by that module**, while also revoking external resources. JAAS does not roll back databases automatically. Write tests for partial commit, not just success/login failure.

### 10.3 Subject Is Already Read-Only

`Subject.setReadOnly()` prevents normal modifications to the principals/credentials sets. If a module must write to the Subject in `commit`, it should fail with `LoginException`. `logout` may be unable to remove a Principal belonging to the module; adhere to read-only semantics and credential destruction support, and do not force access by bypassing checks.

### 10.4 Duplicate Principal from Another Module

If the Subject already contains `UserPrincipal("alice")`, `add` under set semantics may return `false`. If module A did not add a new element yet still runs `logout` and removes by name/class, it could erase module B's state. Track **object ownership** and handle duplicates properly.

### 10.5 Shared State and Multiple Logins

`sharedState` is a map shared among configured modules. When using it to exchange usernames or credentials, restrict keys, types, read access, and clear secrets after use. Do not reuse a module instance or `LoginContext` across multiple Subjects; `LoginContext` documentation warns against using a single context to authenticate **multiple Subjects**.

If an application retries, state from the previous attempt must be reset. Do not retain passwords or pending principals after an initial failure when a second attempt begins, and never use static fields shared across accounts.

### 10.6 Do Not Turn JAAS into a Session Store

JAAS manages the authentication process and updates the Subject. Tokens, cookies, SSO, expiration, revocation, timeouts, authorization, auditing, and network/TLS belong to other layers. `LoginContext.logout` does not automatically revoke an issued JWT unless the system implements a corresponding revocation mechanism.

## 11. Common Pitfalls Table

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Module `login` succeeds yet app login still fails | Another `REQUIRED`/`REQUISITE` module failed | Check configuration and per-module trace; verify abort |
| `Subject` contains a Principal after overall login fails | Module added too early in `login`, missing abort cleanup | Add only in `commit`; track ownership |
| No `commit` even though `PasswordModule` returned `true` | Overall failure or flag-based short-circuit | Inspect `LoginContext` and control flags |
| `CallbackHandler` is null / NPE | Constructor/config did not provide a handler | Check for null and throw a controlled `LoginException` |
| `UnsupportedCallbackException` | Handler does not support Name/Password callbacks | Verify callback contract; do not log secrets |
| Wrong password still logs in | Returned `false` instead of `FailedLoginException`, weak `OPTIONAL`/`SUFFICIENT` config | Distinguish ignored vs. failed and review policy |
| `commit` throws read-only Subject error | Principal/credential set is locked | Check `setReadOnly` lifecycle and handle cleanup |
| `logout` removes another module's Principal | Removed by class/name instead of ownership | Remove only contributions actually added |
| `logout` fails to clean credentials | Missing cleanup implementation or missing destroy | Test Subject before/after; handle secret resources |
| Retry reuses old results | Failed to reset booleans/pending identity | Reset state cleanly per attempt; use a separate `LoginContext` |
| `LoginModule` fails to load | Wrong binary name, JAR/classpath, missing no-arg constructor | Check deployment and `Class.getName()` |
| Trace leaks password/token | Printing callbacks/exception details or debug state | Log only phase/result; mask secrets and PII |

**Never** add delays or retry loops inside `LoginModule` to "prevent brute force." Place rate limiting, MFA, lockout controls, and monitoring in the layers designed for them; avoid hanging the module or misreporting outcomes.

## 12. Exercises and Completion Checklist

1. Run the Java 21 program and trace the three flows from `initialize` to `commit/abort/logout`. Why is there no `commit` when the password is wrong?
2. Use `DenyModule REQUIRED` to explain the case where a module's `login` returned `true` yet **no new Principal** appears in the Subject.
3. Change `DenyModule` to `OPTIONAL` and predict the overall result. Explain how the flag changes the success/failure condition.
4. Design a `LoginModule` that returns `false` when it does not recognize the credential type. Why is this different from throwing `FailedLoginException` on a wrong password?
5. Add a `UserPrincipal("alice")` before `commit`; observe whether `Set.add` returns `true` or `false`. During `logout`, is the module allowed to remove the pre-existing Principal?
6. Write a unit test for `abort` on empty state: a module rejected directly in `login` must still clean up safely.
7. Simulate an error midway through `commit` after adding a role Principal. Determine how to remove that role and compensate for external side effects that JAAS does not handle automatically.
8. Call `Subject.setReadOnly` before `commit`. How must it be handled so it does not falsely report a successful login?
9. Build a safe `CallbackHandler` without password literals; describe when `clearPassword` and `Arrays.fill` are called.
10. If a user has logged out yet a web JWT still works, which part of the system is responsible for fixing that? Does `LoginContext.logout` automatically revoke JWTs?
11. When `SUFFICIENT` succeeds early, may you assume all subsequent modules were initialized and had `login` called? Explain the impact of short-circuiting.
12. Design a concurrency test for two different Subjects. Why is a mutable static `Principal` or password buffer a critical bug?

**Completion criteria:** you can state clearly that **initialize = receive context; login = authenticate and hold temporary state; commit = write to Subject when the whole stack is accepted; abort = clean up on failure; logout = clean up contributions of an already successful session**, and you do not confuse JAAS with password hashing, session management, or authorization.

## 13. References

- [Java SE 21 — `javax.security.auth.spi.LoginModule`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/security/auth/spi/LoginModule.html): five-method contract, two-phase login, and boolean/exception results.
- [Java SE 21 — `javax.security.auth.login.LoginContext`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/security/auth/login/LoginContext.html): module orchestration, constructors, Subject, and logout.
- [Java SE 21 — `Configuration`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/security/auth/login/Configuration.html) and [`AppConfigurationEntry`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/security/auth/login/AppConfigurationEntry.html): module flags and configuration.
- [Java SE 21 — `Subject`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/security/auth/Subject.html): principal/credential sets and read-only mode.
- [Java SE 21 — `CallbackHandler`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/security/auth/callback/CallbackHandler.html) and [`PasswordCallback`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/security/auth/callback/PasswordCallback.html): retrieving and clearing input.
- [Oracle Java 21 — JAAS LoginModule Developer's Guide](https://docs.oracle.com/en/java/javase/21/security/java-authentication-and-authorization-service-jaas-loginmodule-developers-guide1.html): two phases, initialize/login/commit/abort/logout.
- [Oracle Java 21 — JAAS Reference Guide](https://docs.oracle.com/en/java/javase/21/security/java-authentication-and-authorization-service-jaas-reference-guide.html): control flags, JAAS config, and Subject.
