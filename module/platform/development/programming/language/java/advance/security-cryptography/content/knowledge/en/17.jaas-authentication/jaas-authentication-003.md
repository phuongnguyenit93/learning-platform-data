# 17.3 LoginContext, Configuration, and the Pluggable LoginModule Model

In Java Authentication and Authorization Service (**JAAS**), an application wishing to authenticate a user or service does not need to hardcode a login function tied directly to a database, Kerberos, LDAP, or an SSO system. JAAS provides a **pluggable authentication** model: the application calls **`LoginContext`**, a **`Configuration`** determines which **`LoginModule`**s are activated along with their order and combination policy, and each `LoginModule` implements a concrete authentication mechanism.

Three core roles:

- **`LoginContext`** is the **orchestrator of the login/logout workflow** by application name. It reads the configuration, drives modules through the standard lifecycle, and provides a **`Subject`** upon successful login.
- **`Configuration`** is the authentication **blueprint**: each application name maps to an **ordered list** of `AppConfigurationEntry` objects specifying the `LoginModule` class name, control flag (`REQUIRED`/`REQUISITE`/`SUFFICIENT`/`OPTIONAL`), and module `options`.
- **`LoginModule`** is the **SPI (Service Provider Interface)** comprising five methods: `initialize`, `login`, `commit`, `abort`, and `logout`. A module performs credential verification and only **attaches Principals/credentials to the `Subject` during `commit`** when overall authentication succeeds.

This lesson belongs to **17. JAAS Authentication** in Java Advanced Security & Cryptography. The examples use **Java 17+** and require no Internet connection or Kerberos server. We will run three standalone programs: authenticating via callbacks and `Subject`, simulating **control flags**, and loading a JAAS `Configuration` from a file. The examples intentionally use mock test passwords or simulated allow/deny behavior to illustrate the **JAAS contract**, **not** a secure production password authentication library.

## 1. Overall Model and Path of a Login Attempt

```text
APPLICATION
    |
    | 1. new LoginContext("LearningApp", subject, callback, config)
    v
LoginContext
    |
    | look up configuration by application name
    v
Configuration
    |
    +-- AppConfigurationEntry #1
    |      className = ...PasswordModule
    |      flag = REQUIRED
    |      options = {...}
    |
    +-- AppConfigurationEntry #2
    |      className = ...MfaModule
    |      flag = REQUIRED
    |      options = {...}
    |
    +-- AppConfigurationEntry #3
           className = ...AuditModule
           flag = OPTIONAL
           options = {...}
    |
    v
LoginContext.login()
    |
    +-- instantiate/initialize module(s)
    |       Subject + CallbackHandler + sharedState + options
    |
    +-- PHASE 1: call login() in order + control flags
    |
    +-- If overall authentication succeeds:
    |       PHASE 2: call commit()
    |       -> Subject holds appropriate Principals/credentials
    |
    +-- If it fails:
            PHASE 2: call abort()
            -> clean up temporary state/credentials
    |
    v
Application receives success / LoginException
    |
    +-- login.getSubject(): authenticated identity on success
    |
    +-- logout() -> each LoginModule.logout()
```

**Crucial point:** `LoginContext` does not know what the right password is, does not connect to LDAP itself, does not mint tokens, and does not automatically grant users permissions. Authentication modules report results; `LoginContext` applies flags and lifecycle phases; the application/separate authorization layer **evaluates access rights** from the identity and policy.

### 1.1 Four Easily Confused Objects

| Component | Role | Holds passwords/credentials? | API |
| --- | --- | --- | --- |
| **`LoginContext`** | Coordinates login, commit/abort, and logout; provides `Subject` | Not a password store itself; passes `CallbackHandler`/`Subject` to modules | `javax.security.auth.login.LoginContext` |
| **`Configuration`** | Determines *which modules*, order, flags, and options | **Should never** hold hardcoded passwords/secrets | `javax.security.auth.login.Configuration` |
| **`LoginModule`** | Authenticates via a concrete technology; manages its own state/`Subject` updates | May **temporarily** process credentials; must protect and wipe appropriately | `javax.security.auth.spi.LoginModule` |
| **`CallbackHandler`** | Supplies interactive data such as username, password, OTP, or credential source | May place credentials into `Callback`s; not where trust is decided | `javax.security.auth.callback.CallbackHandler` |

**`Subject` is not `LoginContext`.** `Subject` represents the authenticated entity, containing `Principal`, public credential, and private credential sets. After `login()` succeeds, the application typically retrieves it via `getSubject()`. Each `Principal` represents an identity name/attribute; a `Principal` named `admin` does not grant administrative privileges unless the application has a corresponding authorization policy.

## 2. `LoginContext`: Contract with the Application

Common usage:

```java
// Illustrative snippet inside a method with a valid callbackHandler.
LoginContext login = new LoginContext(
        "LearningApp", callbackHandler);
login.login();
Subject subject = login.getSubject();
try {
    // Use only verified identity attributes.
} finally {
    login.logout();
}
```

This is an **illustrative snippet**, not a standalone program because imports, `callbackHandler`, and exception handling are omitted. A full runnable example appears in Section 7.

### 2.1 Constructors Worth Remembering

| Constructor | Meaning |
| --- | --- |
| `new LoginContext(String name)` | Reads the installed `Configuration`, looks up `name`, uses default config's callback if any |
| `new LoginContext(String name, CallbackHandler handler)` | Installed `Configuration`, caller-supplied handler |
| `new LoginContext(String name, Subject subject)` | Authenticates the **provided `Subject`**, using default callback if needed |
| `new LoginContext(String name, Subject subject, CallbackHandler handler)` | Installed `Configuration`, explicit `Subject` and handler |
| `new LoginContext(String name, Subject subject, CallbackHandler handler, Configuration config)` | **Dedicated `Configuration`** for this context; ideal for apps controlling module stacks without altering global config |

**There is no** standard `LoginContext(String, CallbackHandler, Configuration)` constructor in Java 17; to pass a custom config, use the **four-argument** overload where `Subject` can be `null`. Working pattern:

```java
LoginContext ctx = new LoginContext(
        "LearningApp", null, callbackHandler, configuration);
```

When the caller passes no `Subject`, `LoginContext` creates a new `Subject` per contract; when one is provided, that `Subject` is used. **Never reuse one `LoginContext` across multiple different users/`Subject`s**; the API documentation recommends a separate context per `Subject`.

### 2.2 Application Name Is a Lookup Key, Not an Authentication Type

`"LearningApp"`, `"MyService"`, or `"FileDemo"` is an **entry name** in `Configuration`:

```text
LoginContext("LearningApp") --> Configuration.getAppConfigurationEntry("LearningApp")
                                     |
                                     +--> list of LoginModules + flags + options
```

If no entry exists for `name`, `LoginContext` by contract also tries the **`"other"`** entry. If both are missing, the constructor can throw `LoginException`. This fallback policy helps in some setups, yet can **silently substitute the wrong authentication mechanism** if `other` is overly permissive. In multi-trust-domain apps, verify entry names and configure fallbacks deliberately.

### 2.3 `login()`, `getSubject()`, `logout()`

- **`login()`:** executes the configured modules, completing overall authentication or throwing `LoginException`.
- **`getSubject()`:** retrieves the corresponding `Subject`. Never treat `Subject` as proof of login before `login()` returns normally; before login, it may return `null` depending on constructor/state.
- **`logout()`:** invokes logout on the modules in the context; **each module removes** the `Principal`s and credentials it added. Logout does not automatically revoke external session tokens/JWTs unless the module implements that.
- **No automatic retries** on wrong password: rate limiting, lockouts, backoff, CAPTCHA, or retry policies belong to the application/auth service. JAAS guidelines instruct modules not to insert arbitrary delays/retries inside `login()`.

## 3. `Configuration`: How `LoginModule`s Are Selected and Swapped

`Configuration` is an abstract class returning **`AppConfigurationEntry[]`** for an application name. Each entry has three parts:

```text
AppConfigurationEntry {
    loginModuleName: "com.example.auth.PasswordModule"
    controlFlag: REQUIRED
    options: {"debug": "false", "realm": "example"}
}
```

In Java code:

```java
// Illustrative API snippet, not a standalone file.
AppConfigurationEntry item = new AppConfigurationEntry(
        PasswordModule.class.getName(),
        AppConfigurationEntry.LoginModuleControlFlag.REQUIRED,
        Map.of("realm", "demo"));
```

**Properties:**

1. **Class name**: fully qualified name of a loadable `LoginModule` implementing the interface properly with a **public no-argument constructor**. When using nested classes in demos, the Java binary class name uses **`$`**.
2. **Control flag**: rule for combining success/failure with other modules; not a "security level" or "priority."
3. **Options**: a **module-specific** map whose keys and meanings are defined by that module. `debug`, `tryFirstPass`, and `useFirstPass` are not guaranteed to share universal semantics across every module.

### 3.1 Declarative JAAS Configuration File

A file configuration typically uses the syntax:

```text
ApplicationName {
    fully.qualified.ModuleClass required optionName="value";
    another.ModuleClass optional debug="false";
};
```

Modules inside the same stanza run in **the exact listed order**, subject to early termination by flags. Semicolons **after each module** and after the closing `}` are syntactically significant; option strings are enclosed in double quotes under default configuration syntax.

Illustrative snippet for a multi-step authentication system:

```text
ServiceLogin {
    com.example.auth.PasswordLoginModule required realm="employees";
    com.example.auth.OtpLoginModule required issuer="company";
    com.example.auth.AuditLoginModule optional debug="false";
};
```

**The `com.example.auth.*` classes are illustrative names only, not built-in JDK classes.** The runnable example in Section 9 uses real classes defined in the accompanying Java file. The config specifies **modules**—it neither generates implementations nor sets up LDAP/OTP automatically.

With the JDK's default `ConfigFile` implementation, you can supply a file via a system property:

```bash
java -Djava.security.auth.login.config=jaas.conf MainClass
```

If an application uses the installed config, it queries `Configuration.getConfiguration()`. The effective config can come from system properties, `login.config.url.n` security properties, and providers, with precedence defined by the reference implementation and startup flags. Do not assume a `jaas.conf` file is used when code passes a **custom `Configuration`** into the four-argument constructor.

**Never place passwords, secret tokens, private keys, or sensitive connection secrets into JAAS config files**: options are not automatically encrypted and can appear in files, memory, diagnostics, and process configs. Use proper secret management; config files should hold **realm names, issuers, modes, controlled endpoints**, and non-secret options.

### 3.2 Programmatic `Configuration`

Instead of relying on a JVM-wide file, an application can subclass:

```java
// Illustrative snippet; MyLoginModule must exist and implement LoginModule.
Configuration config = new Configuration() {
    @Override
    public AppConfigurationEntry[] getAppConfigurationEntry(String name) {
        if (!"LearningApp".equals(name)) {
            return null;
        }
        return new AppConfigurationEntry[]{
            new AppConfigurationEntry(
                    MyLoginModule.class.getName(),
                    AppConfigurationEntry.LoginModuleControlFlag.REQUIRED,
                    Map.of())
        };
    }
};

LoginContext context = new LoginContext(
        "LearningApp", null, callbackHandler, config);
```

**This is a non-standalone snippet** because `MyLoginModule` and `callbackHandler` are undeclared. The complete program in Section 7 defines its own module and similar `Configuration`.

Advantage: isolates authentication policy per tenant, environment, or test **without mutating the global installed `Configuration`**. Pin/version the config for a given login attempt; never mutate a module stack mid-login nondeterministically.

### 3.3 Installed Configuration and `refresh()`

`Configuration.getConfiguration()` retrieves the installed JAAS configuration; `Configuration.setConfiguration(...)` replaces the global setting at runtime. When multiple apps/libraries share one JVM, calling `setConfiguration` to solve a local problem can affect other callers.

`Configuration.refresh()` asks the provider to **reload/update** configuration per its implementation. Never assume that:
- Every provider supports instant hot reloading;
- An already-created `LoginContext` swaps its module list mid-login;
- `setConfiguration` or `refresh` atomically migrates all active sessions.

**If dynamic configuration is needed**, build versioning, synchronized rollout, new contexts, and consistency tests; passing an explicit `Configuration` to `LoginContext` isolates changes much more cleanly.

## 4. The Pluggable `LoginModule` Model

A `LoginModule` is an **authentication plugin**, decoupled from web or console UIs. Two modules can implement the same SPI while authenticating with completely different technologies:

```text
Application:
    LoginContext("ServiceLogin").login()

Configuration A:
    PasswordDatabaseLoginModule required

Configuration B:
    KerberosLoginModule required

Configuration C:
    CertificateLoginModule required
    AuditLoginModule optional

Configuration D:
    PasswordLoginModule required
    OneTimePasswordModule required
```

The application's `LoginContext` call stays the same while **the underlying mechanism changes via configuration and module implementation**. That is **pluggable authentication**. However, any replacement module must remain compatible with the application's `Subject`/`Principal` types, credential sources, assurance level, exception semantics, and authorization contract. Swapping modules does not automatically guarantee **equivalent security**.

### 4.1 The `LoginModule` Interface: Five Methods

```java
package javax.security.auth.spi;

// Explanatory signature, not a new source file to create a javax package.
public interface LoginModule {
    void initialize(
            Subject subject,
            CallbackHandler callbackHandler,
            Map<String, ?> sharedState,
            Map<String, ?> options);
    boolean login() throws LoginException;
    boolean commit() throws LoginException;
    boolean abort() throws LoginException;
    boolean logout() throws LoginException;
}
```

Responsibility table:

| Method | Timing | Primary work | What to avoid |
| --- | --- | --- | --- |
| **`initialize`** | After JAAS instantiates module, before phases | Save `Subject`, `CallbackHandler`, `sharedState`, and needed `options` | Expensive network calls without timeouts; adding Principals before verification |
| **`login`** | Phase 1 | Gather credentials, verify, record temporary identity/auth status **inside the module** | Adding Principals to `Subject` too early; logging passwords; infinite internal retries |
| **`commit`** | Phase 2, when overall authentication succeeds | If this module succeeded, add valid Principals/credentials to `Subject`; wipe temp state | Committing identities from failed modules; retaining plaintext passwords |
| **`abort`** | Phase 2, when overall authentication fails or rollback is needed | Discard temporary credentials/state; roll back module-owned changes | Leaving behind half-baked Principals or tokens |
| **`logout`** | When `LoginContext.logout()` is called | Remove Principals/credentials added by **this module** and close owned sessions/resources | Blindly calling `subject.getPrincipals().clear()` and deleting other modules' data |

A module must have a **public no-argument constructor** so `LoginContext` can instantiate it via provider/class loading. A `public static` **nested class** with an implicit default no-arg constructor also works in demos.

### 4.2 Why Must `login` and `commit` Be Separate?

Suppose a stack has two modules:

```text
PasswordModule  REQUIRED  -> valid password
OtpModule       REQUIRED  -> wrong OTP
```

If `PasswordModule.login()` **had already added its Principal to `Subject`**, then after OTP fails, `Subject` could retain partial identity even though **overall login was rejected**. Hence the standard contract:

```text
PHASE 1:
    PasswordModule.login() -> true (holds private pending state)
    OtpModule.login()      -> throws FailedLoginException

OVERALL FAILURE:
    PasswordModule.abort()
    OtpModule.abort()
    Subject has no new identity committed
```

If both succeed:

```text
PHASE 1:
    PasswordModule.login() -> true
    OtpModule.login()      -> true

PHASE 2:
    PasswordModule.commit() -> add Principal to Subject
    OtpModule.commit()      -> attach credential/assurance if applicable
    LoginContext.login()    -> returns successfully
```

**Decisive point:** `login() == true` for **one module** does not equal **overall `LoginContext` success**. `Configuration`'s **control flags** determine the success threshold, and `commit` executes per phase logic only after the overall condition is met.

## 5. `REQUIRED`, `REQUISITE`, `SUFFICIENT`, `OPTIONAL`

The four flags control **authentication ordering and success criteria**. They are the core reason JAAS supports a module stack rather than a single boolean function.

| Flag | When module succeeds | When module fails | Impact on overall outcome |
| --- | --- | --- | --- |
| **`REQUIRED`** | Continue evaluating subsequent modules | **Still continues** evaluating subsequent modules | This module **must succeed**; its failure cannot be erased by a later `SUFFICIENT` |
| **`REQUISITE`** | Continue evaluating subsequent modules | **Stops immediately** in the login stack phase | This module **must succeed**; failure returns early |
| **`SUFFICIENT`** | May **stop early with success** if **no prior `REQUIRED`/`REQUISITE` failed** | Continue to subsequent modules | Not mandatory; a succeeding `SUFFICIENT` can conclude the stack |
| **`OPTIONAL`** | Continue to subsequent modules | Continue to subsequent modules | Not mandatory, unless the stack has no `required`/`requisite`, in which case at least one `sufficient`/`optional` must succeed |

**General rule per Java `Configuration`:** all **relevant executed `REQUIRED`/`REQUISITE`** modules must succeed. When a `SUFFICIENT` succeeds, all `REQUIRED`/`REQUISITE` modules **preceding it** must have succeeded to terminate early. If no `REQUIRED` or `REQUISITE` exists, **at least one `SUFFICIENT` or `OPTIONAL`** must succeed.

### 5.1 Order Makes the Difference

The following stacks yield different results:

```text
A. OPTIONAL fail -> REQUIRED pass
   => SUCCESS

B. REQUIRED fail -> SUFFICIENT pass
   => FAILURE (required failure is not ignored)

C. REQUISITE fail -> OPTIONAL pass
   => FAILURE; optional is not called

D. SUFFICIENT pass -> REQUIRED fail
   => Early SUCCESS; downstream required is not called

E. OPTIONAL fail (only one module)
   => FAILURE because no module succeeded
```

Notice the difference between **throwing `LoginException`** and **`login()` returning `false`**: the `LoginModule` contract allows returning `false` when a module should be ignored; never use `return false` to mean "wrong password" for a mandatory auth module in your code. Intentionally throw **`FailedLoginException`** when a module rejects credentials so test semantics stay crystal clear.

### 5.2 Why Not Make Everything `OPTIONAL`?

A stack with `AuditModule OPTIONAL` and `PasswordModule OPTIONAL` could **succeed** if the audit module returns success while the password module fails. Misconfigured flags create **authentication bypasses**. In particular, an "audit/logging" module must never be written to return `true` in a way that lets an all-`OPTIONAL` stack succeed without real authentication.

**Rule:** design flags from your **threat model**, not from a desire for "fewer login errors"; unit-test every success/failure combination to ensure mandatory factors stay mandatory. MFA requiring **both password and OTP** usually needs corresponding policy modules—such as both `REQUIRED` or vetted centralized verification—never marking an MFA step `OPTIONAL` merely because users sometimes lack an OTP.

## 6. `Subject`, `Principal`, and Credentials

`javax.security.auth.Subject` represents the authenticated entity and has three main collections:

```text
Subject
  |
  +-- Set<Principal>
  |      e.g.: UserPrincipal("student"),
  |              RolePrincipal("reader") (if granted by trusted policy)
  |
  +-- publicCredentials
  |      credential data shareable per contract
  |
  +-- privateCredentials
         secret/sensitive credentials requiring read protection and lifecycle management
```

`Principal` is an interface with `getName()`; in Java 17 we can use **`record AppPrincipal(String getName) implements Principal`** for small examples. In real systems, designing stable `Principal` types, mapping identity → roles, tenants, scopes, and authorization policies **must be analyzed separately**. Never infer that `subject.getPrincipals().contains("admin")` grants privileges without proper `Principal` type/issuer/trust contracts.

### 6.1 When Should `Subject` Be Updated?

- **Before login:** a new/existing `Subject` may hold Principals from other modules; preserve anything you do not own.
- **During `login`:** store temporary identity (`pendingPrincipal`) inside the module instance—**do not** add it to `Subject`.
- **During `commit`:** add identity only if this module succeeded and overall flow succeeded.
- **During `abort`:** clear temporary state/tokens and roll back any changes that occurred.
- **During `logout`:** remove **only the Principals/credentials owned by this module**. Never clear all of `Subject.getPrincipals()` since other modules may have added valid data.
- **Read-only `Subject`:** if the caller called `Subject.setReadOnly()`, adding/removing Principals will be rejected; handle fail-closed and throw an appropriate `LoginException`.

### 6.2 Never Put Raw Passwords in `Principal`

Principals represent identities (users, services, or verified roles), **not passwords**. Passwords are only for verification and should then be wiped from temporary memory; never place `PasswordCallback` or plaintext into `Subject.getPublicCredentials()`, logs, or errors. For tokens/session keys in `privateCredentials`, enforce proper lifecycles and `Destroyable` when supported.

## 7. Runnable Java 17+: `LoginContext` + Custom `LoginModule` + `Subject`

This example needs no config file: we create `Configuration` in code and pass it directly to `LoginContext`. `PasswordModule` illustrates the full lifecycle; `CallbackHandler` supplies test user/password input; `commit` adds `AppPrincipal`, `logout` removes it, and wrong logins throw `FailedLoginException`.

**Security note:** `"lab-only"` is a hardcoded test password for demonstration. The program has **no** password hash database, Argon2id/PBKDF2, throttling, or secure credential storage. The `char[]` comparison only tests the JAAS callback lifecycle and is **not a production password authenticator**.

Save as **`JaasLoginDemo.java`**:

```java
import java.security.Principal;
import java.util.*;
import javax.security.auth.Subject;
import javax.security.auth.callback.*;
import javax.security.auth.login.*;
import javax.security.auth.spi.LoginModule;

public final class JaasLoginDemo {
    public record AppPrincipal(String getName) implements Principal {}

    public static final class PasswordModule implements LoginModule {
        private Subject subject;
        private CallbackHandler handler;
        private AppPrincipal pending;
        private boolean loggedIn;
        private boolean committed;

        @Override
        public void initialize(Subject subject, CallbackHandler handler,
                               Map<String, ?> sharedState,
                               Map<String, ?> options) {
            this.subject = Objects.requireNonNull(subject);
            this.handler = Objects.requireNonNull(handler);
        }

        @Override
        public boolean login() throws LoginException {
            NameCallback name = new NameCallback("Username: ");
            PasswordCallback password =
                    new PasswordCallback("Password: ", false);
            try {
                handler.handle(new Callback[]{name, password});
                char[] received = password.getPassword();
                char[] expected = "lab-only".toCharArray();
                boolean correctUser =
                        "student".equals(name.getName());
                boolean correctPassword =
                        constantTimeEqual(received, expected);
                Arrays.fill(expected, '\0');

                if (!correctUser || !correctPassword) {
                    throw new FailedLoginException("Invalid credentials");
                }
                pending = new AppPrincipal(name.getName());
                loggedIn = true;
                return true;
            } catch (UnsupportedCallbackException
                     | java.io.IOException e) {
                LoginException ex = new LoginException("Callback failed");
                ex.initCause(e);
                throw ex;
            } finally {
                password.clearPassword();
            }
        }

        private static boolean constantTimeEqual(
                char[] left, char[] right) {
            if (left == null || right == null) return false;
            int diff = left.length ^ right.length;
            int max = Math.max(left.length, right.length);
            for (int i = 0; i < max; i++) {
                char a = i < left.length ? left[i] : 0;
                char b = i < right.length ? right[i] : 0;
                diff |= a ^ b;
            }
            return diff == 0;
        }

        @Override
        public boolean commit() throws LoginException {
            if (!loggedIn) return false;
            if (subject.isReadOnly()) {
                throw new LoginException("Subject read-only");
            }
            subject.getPrincipals().add(pending);
            committed = true;
            return true;
        }

        @Override
        public boolean abort() throws LoginException {
            if (committed) return logout();
            reset();
            return true;
        }

        @Override
        public boolean logout() throws LoginException {
            if (committed) {
                if (subject.isReadOnly()) {
                    throw new LoginException("Subject read-only");
                }
                subject.getPrincipals().remove(pending);
            }
            reset();
            return true;
        }

        private void reset() {
            pending = null;
            loggedIn = false;
            committed = false;
        }
    }

    public static final class UserCallbacks implements CallbackHandler {
        private final String user;
        private final char[] pass;

        UserCallbacks(String user, char[] pass) {
            this.user = user;
            this.pass = pass.clone();
        }

        @Override
        public void handle(Callback[] callbacks)
                throws UnsupportedCallbackException {
            for (Callback callback : callbacks) {
                if (callback instanceof NameCallback name) {
                    name.setName(user);
                } else if (callback instanceof PasswordCallback pwd) {
                    pwd.setPassword(pass);
                } else {
                    throw new UnsupportedCallbackException(callback);
                }
            }
        }

        void clear() {
            Arrays.fill(pass, '\0');
        }
    }

    public static final class InMemoryConfiguration
            extends Configuration {
        @Override
        public AppConfigurationEntry[] getAppConfigurationEntry(
                String name) {
            if (!"LearningApp".equals(name)) return null;
            return new AppConfigurationEntry[]{
                    new AppConfigurationEntry(
                            PasswordModule.class.getName(),
                            AppConfigurationEntry
                                    .LoginModuleControlFlag.REQUIRED,
                            Map.of())
            };
        }
    }

    public static void main(String[] args) throws Exception {
        Configuration config = new InMemoryConfiguration();

        UserCallbacks good = new UserCallbacks(
                "student", "lab-only".toCharArray());
        try {
            LoginContext login = new LoginContext(
                    "LearningApp", null, good, config);
            login.login();
            Subject subject = login.getSubject();
            System.out.println("Login successful: "
                    + (subject != null));
            System.out.println("Principals after login: "
                    + subject.getPrincipals().stream()
                            .map(Principal::getName)
                            .sorted().toList());

            login.logout();
            System.out.println("Principals after logout: "
                    + subject.getPrincipals().size());
        } finally {
            good.clear();
        }

        UserCallbacks bad = new UserCallbacks(
                "student", "wrong".toCharArray());
        try {
            LoginContext login = new LoginContext(
                    "LearningApp", null, bad, config);
            boolean rejected = false;
            try {
                login.login();
            } catch (LoginException expected) {
                rejected = true;
            }
            System.out.println("Wrong password rejected: "
                    + rejected);
        } finally {
            bad.clear();
        }
    }
}
```

Compile and run in the directory containing the file:

```bash
javac -encoding UTF-8 JaasLoginDemo.java
java JaasLoginDemo
```

Stdout on Java 17+ (tested):

```text
Login successful: true
Principals after login: [student]
Principals after logout: 0
Wrong password rejected: true
```

### 7.1 Class-by-Class Explanation

- **`AppPrincipal`** is a `record` implementing `Principal`. The username is exposed via `getName()`. Java record `equals`/`hashCode` use state, making it suitable for illustrating `Set<Principal>`.
- **`PasswordModule`** is a `public static` nested class with an implicit no-arg constructor so `LoginContext` can load it via `PasswordModule.class.getName()` (`JaasLoginDemo$PasswordModule` at runtime).
- **`initialize`** receives `Subject`/`CallbackHandler` and both maps. The demo ignores `sharedState` and `options`, which is valid since modules may ignore unused maps.
- **`NameCallback` and `PasswordCallback`** are the callback protocol objects. The module does not need to know whether credentials came from console, GUI, validated HTTP request, or a test handler.
- **`login`** compares the test inputs and sets `pending` and `loggedIn` privately inside the module; **does not add a Principal yet**.
- **`commit`** adds `pending` to `Subject` only when the module itself succeeded and JAAS enters the commit phase overall.
- **`abort`/`logout`** clear module state and remove only the Principal managed by this module; never call `subject.getPrincipals().clear()`.
- **`InMemoryConfiguration`** returns a single `AppConfigurationEntry` with `REQUIRED`; a bad login yields `LoginException`.
- **`main`** uses **two separate `LoginContext` instances** for two logins: a successful login followed by logout, then a wrong-password login that is rejected.

### 7.2 Intentional Security Limitations

**Unsafe demo password:** `constantTimeEqual` here only avoids an early return based on character values; runtime/input length and other factors may still be observable. It does not replace **slow password hashing**, random salts, and proper login controls. Production should use an identity provider or password verification with **Argon2id/scrypt/bcrypt/PBKDF2** per policy, TLS in transit, rate limiting, auditing, MFA, and in-memory credential protection.

**Never store passwords in `Subject`:** the demo clears the password from `PasswordCallback` via `clearPassword()`. The custom handler also wipes its buffer in `finally`; arrays returned by `PasswordCallback.getPassword()` and JVM copies can have different lifetimes. **`Arrays.fill` alone cannot guarantee erasing every heap copy**.

**Never use a module to self-grant roles:** authenticating `student` does not imply `role=admin`. If roles/entitlements are needed, fetch them from a trusted source and verify them at authorization time.

**Note on commit errors:** if a read-only `Subject` causes `commit` to fail, exception handling and rollback must fail closed. While lab code is simple, production modules must keep cleanup consistent so no Principals/credentials remain after partial failures.

## 8. Java 17+: Testing Flag Ordering with a Reusable `LoginModule`

One `LoginModule` can **be configured multiple times** in the same stack with different options. The example below defines **`StepModule`**, which decides its result from an `allow` option while recording the names of modules whose `login()` was actually invoked. This makes **`REQUIRED`, `REQUISITE`, `SUFFICIENT`, `OPTIONAL`** and module placement directly observable.

**Solely for testing flag logic**: `allow="true"` in configuration is simulated behavior that **never** authenticates a real person; never deploy such a module in production.

Save **`JaasStackDemo.java`**:

```java
import java.util.*;
import javax.security.auth.Subject;
import javax.security.auth.callback.CallbackHandler;
import javax.security.auth.login.*;
import javax.security.auth.spi.LoginModule;

public final class JaasStackDemo {
    private static final List<String> TRACE = new ArrayList<>();

    public static final class StepModule implements LoginModule {
        private String label;
        private boolean allow;
        private boolean authenticated;

        @Override
        public void initialize(
                Subject subject, CallbackHandler handler,
                Map<String, ?> sharedState, Map<String, ?> options) {
            label = (String) options.get("label");
            allow = Boolean.parseBoolean((String) options.get("allow"));
        }

        @Override
        public boolean login() throws LoginException {
            TRACE.add(label);
            if (!allow) {
                throw new FailedLoginException("Denied by " + label);
            }
            authenticated = true;
            return true;
        }

        @Override
        public boolean commit() {
            return authenticated;
        }

        @Override
        public boolean abort() {
            authenticated = false;
            return true;
        }

        @Override
        public boolean logout() {
            authenticated = false;
            return true;
        }
    }

    static AppConfigurationEntry entry(
            String label, boolean allow,
            AppConfigurationEntry.LoginModuleControlFlag flag) {
        return new AppConfigurationEntry(
                StepModule.class.getName(),
                flag,
                Map.of(
                        "label", label,
                        "allow", Boolean.toString(allow)));
    }

    public static void main(String[] args) throws Exception {
        var required =
                AppConfigurationEntry.LoginModuleControlFlag.REQUIRED;
        var requisite =
                AppConfigurationEntry.LoginModuleControlFlag.REQUISITE;
        var sufficient =
                AppConfigurationEntry.LoginModuleControlFlag.SUFFICIENT;
        var optional =
                AppConfigurationEntry.LoginModuleControlFlag.OPTIONAL;

        run("optional_then_required",
                new AppConfigurationEntry[]{
                        entry("optional-fail", false, optional),
                        entry("required-pass", true, required)
                });

        run("required_fail_before_sufficient",
                new AppConfigurationEntry[]{
                        entry("required-fail", false, required),
                        entry("sufficient-pass", true, sufficient)
                });

        run("requisite_short_circuit",
                new AppConfigurationEntry[]{
                        entry("requisite-fail", false, requisite),
                        entry("later-pass", true, optional)
                });

        run("sufficient_short_circuit",
                new AppConfigurationEntry[]{
                        entry("sufficient-pass", true, sufficient),
                        entry("later-fail", false, required)
                });

        run("only_optional_failed",
                new AppConfigurationEntry[]{
                        entry("only-optional-fail", false, optional)
                });
    }

    static void run(String scenario, AppConfigurationEntry[] entries)
            throws Exception {
        TRACE.clear();

        Configuration config = new Configuration() {
            @Override
            public AppConfigurationEntry[] getAppConfigurationEntry(
                    String name) {
                return scenario.equals(name)
                        ? entries.clone() : null;
            }
        };

        LoginContext ctx = new LoginContext(
                scenario, null, callbacks -> {}, config);
        boolean passed;
        try {
            ctx.login();
            passed = true;
        } catch (LoginException expected) {
            passed = false;
        }
        if (passed) ctx.logout();

        System.out.println(
                scenario + ": " + passed
                        + "; ran=" + String.join(",", TRACE));
    }
}
```

```bash
javac -encoding UTF-8 JaasStackDemo.java
java JaasStackDemo
```

Verified stdout on JDK:

```text
optional_then_required: true; ran=optional-fail,required-pass
required_fail_before_sufficient: false; ran=required-fail,sufficient-pass
requisite_short_circuit: false; ran=requisite-fail
sufficient_short_circuit: true; ran=sufficient-pass
only_optional_failed: false; ran=only-optional-fail
```

### 8.1 Reading the Five Cases in Order

**Case 1 — `OPTIONAL` fail, `REQUIRED` pass:** `OPTIONAL` fails but is not mandatory. `REQUIRED` succeeds, so overall login succeeds.

**Case 2 — `REQUIRED` fail, `SUFFICIENT` pass:** `SUFFICIENT` still runs, yet **cannot mask the earlier `REQUIRED` failure**. Result is `false` even though the later module succeeded.

**Case 3 — `REQUISITE` fail:** stops the login phase immediately; `later-pass` never appears in `TRACE`. This avoids executing downstream modules once a mandatory condition fails.

**Case 4 — `SUFFICIENT` pass:** with no prior `required`/`requisite` failure, JAAS can terminate the login phase early; `later-fail` is never called. Order and flags dictate the path.

**Case 5 — Only `OPTIONAL` fails:** no module authenticated successfully, so overall login still fails. **`OPTIONAL` does not mean "allow login without authentication."**

**Test limitations:** `StepModule` adds no Principal to `Subject`; it only models control flow. `TRACE` is a static list for single-threaded unit tests and is **unsuitable** for tracking users/concurrent logins in production. With real modules, also test commit/abort/logout and cleanup for each plugin.

### 8.2 Suspicious Stacks

```text
# DANGEROUS if AuditModule returns success when PasswordModule fails:
Service {
    com.example.AuditModule optional;
    com.example.PasswordModule optional;
};

# DANGEROUS if SufficientPassModule can always succeed:
Service {
    com.example.SufficientPassModule sufficient;
    com.example.RequiredPasswordModule required;
};
```

Both blocks are **illustrative config snippets without real implementations**. They demonstrate why changing modules/flags **is a security policy change**, not a harmless config tweak. Having an optional logging module does not mean it should return `true` as proof of authentication.

## 9. Java 17+: Loading `Configuration` from `jaas.conf`

The previous two examples passed an explicit `Configuration` object. Next we test the **default JAAS configuration parser**: the application calls `LoginContext("FileDemo", handler)` while the module class and options come from `jaas.conf`.

To keep the demo self-contained, we define `AllowModule` as a static nested class. It **always accepts** the user—**solely to prove the config file was actually read**, not as an authentication mechanism.

Create **two files in the same directory**.

**File 1 — `jaas.conf`**:

```text
FileDemo {
    JaasFileConfigDemo$AllowModule required principalName="from-file";
};
```

The **`$`** is part of the JVM binary name of nested class `JaasFileConfigDemo.AllowModule`; packaged production classes use their **fully qualified class name** on the proper classpath/modulepath. `principalName` is a **custom option** read by this example's module, not an automatic JAAS-supported key.

**File 2 — `JaasFileConfigDemo.java`**:

```java
import java.security.Principal;
import java.util.*;
import javax.security.auth.Subject;
import javax.security.auth.callback.CallbackHandler;
import javax.security.auth.login.*;
import javax.security.auth.spi.LoginModule;

public final class JaasFileConfigDemo {
    public record AppPrincipal(String getName) implements Principal {}

    // "Pass-through" module solely to illustrate file configuration;
    // never use as a real authentication mechanism.
    public static final class AllowModule implements LoginModule {
        private Subject subject;
        private AppPrincipal assigned;
        private boolean loggedIn;
        private boolean committed;

        @Override
        public void initialize(
                Subject subject, CallbackHandler cb,
                Map<String, ?> shared, Map<String, ?> options) {
            this.subject = subject;
            this.assigned = new AppPrincipal(
                    (String) options.get("principalName"));
        }

        @Override
        public boolean login() {
            loggedIn = true;
            return true;
        }

        @Override
        public boolean commit() {
            if (!loggedIn) return false;
            subject.getPrincipals().add(assigned);
            committed = true;
            return true;
        }

        @Override
        public boolean abort() {
            if (committed) {
                subject.getPrincipals().remove(assigned);
            }
            loggedIn = false;
            committed = false;
            return true;
        }

        @Override
        public boolean logout() {
            if (committed) {
                subject.getPrincipals().remove(assigned);
            }
            loggedIn = false;
            committed = false;
            return true;
        }
    }

    public static void main(String[] args) throws Exception {
        LoginContext login = new LoginContext(
                "FileDemo",
                (CallbackHandler) callbacks -> {});
        login.login();
        System.out.println("Principal from file config: "
                + login.getSubject().getPrincipals()
                        .iterator().next().getName());
        login.logout();
        System.out.println("Principal count after logout: "
                + login.getSubject().getPrincipals().size());
    }
}
```

Compile and pass the system property **before the main class name**:

```bash
javac -encoding UTF-8 JaasFileConfigDemo.java
java -Djava.security.auth.login.config=jaas.conf JaasFileConfigDemo
```

Stdout:

```text
Principal from file config: from-file
Principal count after logout: 0
```

**What this proves:**

1. `LoginContext("FileDemo", handler)` passes no explicit config, so it uses Java's installed `Configuration`.
2. `jaas.conf` maps `FileDemo` to `JaasFileConfigDemo$AllowModule` and option `principalName="from-file"`.
3. `LoginContext` loads the class, calls `initialize` with options, and invokes `login`/`commit`.
4. The module creates `AppPrincipal("from-file")` in `commit` and removes it from `Subject` in `logout`.
5. There is no password/OTP/CA in this test; **success here is not real authentication proof**.

If the path to `jaas.conf` is wrong, `FileDemo` does not match, the class cannot be found, or file syntax is invalid, the constructor or `login()` will fail (depending on cause and timing). Preserve the **cause** for diagnosis without logging credentials.

## 10. `CallbackHandler`: Separating Credential Input UI from `LoginModule`

`CallbackHandler` acts as a **bridge** between an authentication module and the application's data source. The module submits `Callback[]` requests and the handler provides values.

```text
PasswordModule.login()
     |
     +-- NameCallback("Username")
     +-- PasswordCallback("Password")
                  |
                  v
          CallbackHandler.handle(callbacks)
                  |
            +-----+--------------+
            |                    |
      Console handler       GUI / server handler
            |                    |
       user input           received/validated credential
            |                    |
            +----------+---------+
                       v
                populated callbacks
                       |
                       v
             module.verify(credentials)
```

A module may request callbacks for **username, password, text, confirmation**, or other provider-specific callbacks. The handler must handle the supported `Callback`s or throw `UnsupportedCallbackException`; never silently return empty strings and treat login as successful.

**Responsibility separation:**

- `CallbackHandler` supplies data to the module; it does **not** create an authenticated `Subject` itself.
- `LoginModule` verifies credentials and carries state into the `commit` phase.
- `LoginContext` manages modules per policy and returns overall success/failure.
- `Subject` holds identities/credentials after the process is verified.

### 10.1 `PasswordCallback` Hygiene

- Use `char[]` instead of holding passwords in immutable `String`s whenever APIs permit.
- Call `PasswordCallback.clearPassword()` and wipe buffers the application actually owns; recognize that copies may exist in the heap.
- Never store callback objects in static fields or cache passwords in `sharedState` across requests.
- When authenticating against stored passwords, use **proper password hashing** such as Argon2id/PBKDF2 per system requirements; **never compare hardcoded plaintext** as in the demo.
- Never let messages/exceptions reveal user existence, password correctness, or secrets. Implement retry throttling and auditing at the auth service layer.

## 11. `sharedState` and `options`: Both Are Maps, Different Purposes

When `LoginContext` initializes a module:

```java
void initialize(
        Subject subject,
        CallbackHandler callbackHandler,
        Map<String, ?> sharedState,
        Map<String, ?> options)
```

**`sharedState`** is a **shared Map** across modules in the same login context/stack; it can pass necessary data under a module contract. **`options`** is **static per-entry configuration** on each `AppConfigurationEntry`.

| Property | `sharedState` | `options` |
| --- | --- | --- |
| Origin | Provided by `LoginContext` for modules to share | Attached by `Configuration` to each module entry |
| Purpose | Sharing temporary state/credentials across modules when truly required | Realm, endpoint, mode, debug flags, timeouts, or module-defined policy |
| Mutability during login | Read/written by modules; needs contracts and cleanup | Normally read-only configuration, not a shared state area |
| Risks | Credentials leaking to other modules; stale state left after `abort`/`logout` | Hardcoded passwords/tokens or options misunderstood by the module |
| API | `Map<String, ?> sharedState` | `Map<String, ?> options` |

**Option names are not universal JAAS features.** For instance, `useFirstPass`, `tryFirstPass`, `storePass`, and `clearPass` appear in various modules/providers to pass state/passwords under module-specific conventions. Check **each `LoginModule`'s own documentation** before using them; never assume `useFirstPass="true"` works across arbitrary modules.

When sharing state, namespace keys, avoid collisions, wipe secrets once finished, and never widen trust carelessly: any module able to read `sharedState` can inspect data written by another module. **Never treat JAAS `sharedState` as a secure key vault.**

## 12. Swapping Modules Without Changing Application Code: Capabilities and Limits

JAAS's strength lies in its contract:

```java
// Caller only knows the application name.
LoginContext lc = new LoginContext("ServiceLogin", callbackHandler);
lc.login();
// ...
lc.logout();
```

Configuration can change from:

```text
ServiceLogin {
    com.example.auth.DatabasePasswordModule required;
};
```

to:

```text
ServiceLogin {
    com.example.auth.KerberosAuthModule required;
};
```

or:

```text
ServiceLogin {
    com.example.auth.PasswordModule required;
    com.example.auth.TotpModule required;
};
```

The **`com.example.auth.*` classes are illustrative plugin names**, not part of the JDK. Once valid implementations are deployed on the classpath/modulepath, application callers can remain unchanged. However, this is **config-driven substitutability**, not a guarantee that every plugin shares identical semantics or can be **hot-swapped mid-request**.

### 12.1 What Must Stay Compatible When Swapping Plugins

- **`Subject`/`Principal` structure:** what Principal types does downstream code expect? If switching from `UserPrincipal` to `KerberosPrincipal`, does authorization code need an adapter?
- **Identity assurance level:** passwords, Kerberos tickets, certificates, or MFA carry different trust assumptions and assurance; swapping plugins can change the threat model.
- **Credential/callback sources:** a new plugin may request different callbacks (password, token, smart card PIN), which the application handler must support.
- **Errors and timeouts:** LDAP/network failures differ semantically from wrong passwords; fail closed and avoid leaking accounts.
- **`LoginModule` options:** `debug`, `realm`, `issuer`, `useFirstPass` are provider-specific.
- **Lifecycle state:** the new module must obey `login/commit/abort/logout`, rollback, and leak-free sessions.
- **Performance/concurrency:** external auth services need proper timeouts, circuit breakers, pools, or per-request sessions.
- **Authorization mapping:** authenticated Principals do not grant permissions automatically; map identities/roles from trusted sources.
- **Testing/release:** never roll out a new module in production by editing JAAS config alone without regression tests for flags and negative cases.

### 12.2 Java Modules and Class Loading

A `LoginModule` is referenced by its **fully qualified class name** in `Configuration`. The runtime must be able to **load the class**; it must be public or accessible to the provider mechanism, implement `LoginModule`, and have a public no-arg constructor. When using the Java Module System (JPMS), appropriate packaging/exports/opens/service declarations are also required per the provider mechanism. Do not confuse **JAAS `LoginModule`** with JPMS **`module-info.java`**: "module" here means **authentication plugin**, not necessarily a Java Platform Module.

**A "module class not found" error** means checking JARs on the classpath/modulepath, class names, visibility, and providers—not a password error.

## 13. Error Flows and Fail-Closed Behavior

| Error / Symptom | Where it occurs | Meaning and handling |
| --- | --- | --- |
| `LoginException` creating `LoginContext` | App name has no entry and `other` is missing/invalid; config/class issue per implementation | Check `name`, config file, installed `Configuration`, and class names |
| `FailedLoginException` | `LoginModule.login()` | Credentials rejected; return generic message without leaking user/password |
| `UnsupportedCallbackException` | `CallbackHandler.handle` | Handler does not support callback type requested by module; fix bridge/UI, do not ignore |
| `IOException` while handler reads input | Callback/credential input | I/O failure; wrap into `LoginException` with safe cause handling |
| Exception during `commit` | Read-only `Subject`, permission/provider error, error adding Principal/credential | Fail closed, roll back/abort, leave no half-committed identity |
| Later modules not called in stack | `REQUISITE` failure or valid `SUFFICIENT` pass | May be **intended control flow**, not a "missing" module |
| Module returns `true` yet `LoginContext.login()` fails | Another `REQUIRED`/`REQUISITE` failed or commit phase errored | Inspect the entire stack rather than blaming one module in isolation |
| `logout()` fails | Module could not clean up token/session/`Subject` | Log safely and handle lifecycle without treating session as still valid |
| App login succeeds yet Principals are empty | Module failed to attach Principal or commit logic is buggy | Verify module contract; never treat bare success as permissions |
| Config file changed yet behavior unchanged | Context/provider uses snapshot, cache, or explicit programmatic config | Verify config source, `refresh`, new contexts, and rollout strategy |

**Fail closed:** when a module is missing, config cannot be found, callbacks fail, the identity provider is unreachable, or the password-hashing backend is down, never insert an `AllowAllLoginModule` just to keep the service running. If a degraded mode is required, document a threat model and explicit policy that **never unintentionally weakens authentication**.

### 13.1 Safe Logging Practices

Safe to log (under access-controlled log policy): scenario code, service/realm, module class, login outcome, duration, generic error reason, trace ID. **Never log** passwords/OTPs/private credentials, full `sharedState`, callback payloads, raw tokens, or details that act as an account-existence oracle. Review provider documentation before enabling any module `debug` flag.

### 13.2 Retries, Lockouts, and Brute-Force Protection

JAAS specifies the SPI and lifecycle, yet **does not build in** application-wide rate limiting, lockouts, account recovery, or password policies. Implement these in your identity service/gateway/backend per threat model:

- Rate-limit attempts per user and appropriate signals while preventing enumeration;
- Use salted, cost-configured password hashing rather than plaintext or bare fast SHA-256;
- Transmit credentials over TLS or protected channels;
- Manage MFA, trusted devices, recovery, and session revocation;
- Audit relevant events while keeping secrets out of logs.

## 14. Authentication Is Not Authorization

`LoginContext.login()` confirms **this user or service passed the configured authentication mechanism**. It does not automatically permit reading a database or transferring funds.

```text
Authentication:
    credentials + LoginModules -> Subject/Principals

Authorization:
    authenticated identity + resource/action + policy
        -> ALLOW or DENY
```

A `Subject` holding `AppPrincipal("student")` does not prove the student may call an admin API. The system needs separate authorization, such as RBAC/ABAC or a policy engine. Classical JAAS authorization concepts involved `Subject.doAs`, `AccessControlContext`, and `SecurityManager`; **the Security Manager was deprecated for removal in JDK 17** and legacy `java.security.Policy`/`SecurityManager` models should not be chosen for new protections. Related API behavior evolves across JDK releases, so consult your runtime's docs when maintaining legacy code.

**Modern application mindset:** JAAS can authenticate and produce Principals; then an independent security/framework layer evaluates access rights using the verified token/identity, without assuming a principal name grants privileges on its own.

## 15. Required Test Scenarios for a `LoginModule` Stack

| Scenario | Expected Outcome |
| --- | --- |
| Valid password; `REQUIRED` module succeeds | `LoginContext.login()` succeeds; `Subject` holds expected Principal |
| Wrong password | `LoginException`; no new Principal committed |
| Earlier `REQUIRED` fails, later `SUFFICIENT` succeeds | **Overall failure**; required failure is not masked |
| `REQUISITE` fails | **Stops** downstream modules, fails, and cleans up |
| `SUFFICIENT` succeeds ahead of later modules with no prior required failure | May **finish early**; test confirms no mandatory check was unintentionally skipped |
| `OPTIONAL` fails while `REQUIRED` passes | Overall pass if all other mandatory checks pass |
| All `OPTIONAL` fail | Overall failure |
| `commit` fails partway through | Proper rollback; no leftover credentials/Principals |
| `abort` after one module succeeded in `login` | Clears pending state and secrets; `Subject` is not wrongly updated |
| `logout` | Removes only this module's Principal; preserves other modules' Principals |
| `CallbackHandler` lacks a callback type | Explicit error; no bypass |
| Wrong app name or `other` fallback in `Configuration` | Follows intended policy; never silently falls back to weak auth |
| Invalid config options | Fails closed or logs config error; never silently accepts |
| Concurrent user logins | No `sharedState`/credential leaks across contexts; no static state |
| Swapping module/password provider | Tests verify `Subject` contract, flags, timeouts, errors, and authorization |
| Read-only `Subject` | Module cannot add Principal; fails safely and cleans state |

The programs in Sections 7–9 are **unit/behavior demos**. Production projects also need integration tests against real identity providers, network-failure tests, load/concurrency tests, secret rotation tests, negative security cases, authorization tests, and audit checks.

## 16. Self-Check Questions with Answers

**Q1.** An application calls `new LoginContext("Portal", handler)`. Which `LoginModule` classes are selected?  
**Answer:** Whatever the **installed `Configuration`** returns for entry `"Portal"`. If absent, JAAS by contract may also check `"other"`; never guess from class names in app code.

**Q2.** Does `LoginContext` verify usernames and passwords itself?  
**Answer:** No. It coordinates **`LoginModule`s**; each module performs credential verification according to its technology and policy.

**Q3.** `PasswordModule.login()` returns `true`, yet a `REQUIRED` OTP module fails. Should `UserPrincipal` be added to `Subject`?  
**Answer:** No. **Overall login failed**, so `abort` cleans up state; only `commit` after overall success attaches Principals.

**Q4.** `REQUIRED` fails and then `SUFFICIENT` succeeds—what is the outcome?  
**Answer:** **Failure**. `SUFFICIENT` does not override an earlier `REQUIRED` failure.

**Q5.** A `REQUISITE` module fails—is the next module called?  
**Answer:** No, not in the login stack evaluation phase; it fails early. Module lifecycle cleanup/`abort` must still run properly.

**Q6.** A `SUFFICIENT` succeeds at the top of the stack, followed by a `REQUIRED`. Can the later module be skipped?  
**Answer:** Yes. If no prior `required`/`requisite` failed, `SUFFICIENT` can short-circuit early. That is why **ordering and flags are security-critical**.

**Q7.** An `AuditModule OPTIONAL` returns `true` while `PasswordModule OPTIONAL` fails. Can login pass?  
**Answer:** Yes, under stack rules with no `REQUIRED`/`REQUISITE`, if one `OPTIONAL` succeeds. That can be a **severe policy vulnerability**; design flags and module semantics carefully.

**Q8.** How do `sharedState` and `options` differ?  
**Answer:** `sharedState` is a Map **shared** across modules in the same context; `options` is **per-`AppConfigurationEntry`** configuration. Neither is a secret vault.

**Q9.** After login, `Subject` has `AppPrincipal("student")`. Does that grant admin permissions?  
**Answer:** No. **Authentication** is not **Authorization**; permissions must be verified separately against trusted policy.

**Q10.** To swap password authentication for Kerberos, can you just change the config?  
**Answer:** Architecturally **yes**, provided the Kerberos plugin is deployed and caller/callback/Subject/authorization contracts align. Changing a class name alone does not provision Kerberos or guarantee equivalent security.

**Q11.** What happens if you call `Configuration.setConfiguration(...)` for a test inside a JVM running multiple apps?  
**Answer:** It can overwrite the **installed global configuration** and affect other callers. Prefer passing a dedicated `Configuration` to the four-argument constructor.

**Q12.** The password from `PasswordCallback` was verified and login succeeded. Should it be kept in `publicCredentials`?  
**Answer:** No. Wipe temporary credentials; if a session credential is needed, use a protected object with explicit lifecycle and access controls.

**Q13.** If `LoginContext.login()` succeeded, does `logout()` automatically revoke a JWT issued by an external service?  
**Answer:** Not automatically. The `LoginModule`/provider must implement revocation/cleanup or the application needs its own lifecycle mechanism.

**Q14.** Are JAAS `LoginModule` and Java `module-info.java` the same concept?  
**Answer:** No. A JAAS `LoginModule` is an SPI **authentication plugin**; a JPMS module is a **Java Platform Module System packaging and encapsulation unit**.

## 17. Checklist for Designing Pluggable `LoginModule`s

1. **Define the authentication contract**: application name, identity types, `Principal` classes, callback types, assurance level, and metadata for authorization.
2. **Write `LoginModule`s with a public no-arg constructor** and faithfully implement `initialize/login/commit/abort/logout`.
3. **Commit only after overall success**; keep pending state private in `login`; clean up only module-managed state/Principals in `abort`/`logout`.
4. **Design `Configuration` with safe ordering and flags**: `REQUIRED`/`REQUISITE`/`SUFFICIENT`/`OPTIONAL`, never letting auxiliary modules replace authentication proof.
5. **Keep secrets out of options, source code, and logs**; use backend secret management, proper password hashing, TLS, and rate limiting.
6. **Be careful with the `other` fallback**, global `Configuration`, and versioning/hot reloads; prefer per-application configs when isolation is needed.
7. **Control `sharedState`**: enforce permissions/namespacing/cleanup and never pass secrets to untrusted modules.
8. **Separate `Subject` identity from permissions**: maintain independent authorization policies checking role/tenant/resource/action at every required boundary.
9. **Test on the exact JDK/provider/packaging**: class loading, classpath/modulepath, callbacks, flags, phase rollbacks, and concurrent requests.
10. **Fail safely**: never turn network/LDAP/Kerberos errors into success; sanitize exceptions and enforce auditing and lockouts.
11. **Do not build new protections on legacy `SecurityManager`**: consult current JDK runtime docs when maintaining legacy JAAS authorization.
12. **Plan module swaps carefully**: test new plugins, `Principal` mappings, dry-runs/canaries, rollbacks, credential rotation, and error monitoring.

## 18. Official Documentation

- [Java SE 17 — `LoginContext`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/login/LoginContext.html): constructors, configuration fallback, `login`/`logout`, and `getSubject`.
- [Java SE 17 — `Configuration`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/login/Configuration.html): module stack syntax, control flags, `getAppConfigurationEntry`, installed configuration, and `refresh`.
- [Java SE 17 — `AppConfigurationEntry`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/login/AppConfigurationEntry.html): module class name, flags, and options.
- [Java SE 17 — `LoginModule`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/spi/LoginModule.html): the five-method SPI contract.
- [Java SE 17 — `Subject`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/Subject.html) and [`Principal`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/Principal.html): identity, principals, and credentials.
- [Java SE 17 — `CallbackHandler`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/callback/CallbackHandler.html), [`NameCallback`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/callback/NameCallback.html), [`PasswordCallback`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/callback/PasswordCallback.html): receiving input from credential sources.
- [Oracle JDK 17 — JAAS LoginModule Developer’s Guide](https://docs.oracle.com/en/java/javase/17/security/java-authentication-and-authorization-service-jaas-loginmodule-developers-guide1.html): module structure, two phases, callbacks, cleanup, and testing.
- [Java SE 17 — `ConfigFile`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.security.auth/com/sun/security/auth/login/ConfigFile.html): file-based JAAS configuration implementation.
- [JEP 411 — Deprecate the Security Manager for Removal](https://openjdk.org/jeps/411): notes on legacy `SecurityManager`-based JAAS authorization patterns in older JDKs.

**Summary:** `LoginContext` is the **orchestrator**; `Configuration` is the **plugin list + order + flag policy**; `LoginModule` is the **pluggable authentication mechanism**; `Subject` carries the identity committed on overall login success. Thanks to this separation, Java supports multiple authentication technologies without tying callers directly to them—yet **flag configuration, callbacks, credential handling, rollback, and authorization** remain core security requirements.
