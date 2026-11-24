# 17.4 CallbackHandler Decouples Credential Collection from Authentication Logic

In Java Authentication and Authorization Service (**JAAS**), developers often want to authenticate a user **without coupling the authentication module directly to an input UI**. A desktop app has a password field, a CLI program has `Console`, a web service receives requests over HTTPS, and a headless service pulls secrets from a vault—each collects credentials very differently. If the authentication module itself calls `System.in`, displays a dialog, or reads an HTTP request, credential verification logic becomes hardwired to the environment and difficult to test or change.

**`javax.security.auth.callback.CallbackHandler` is the boundary separating *providing requested information* from *verifying credentials and deciding login*.** The `LoginModule` declares what data it needs using `Callback`s such as `NameCallback` and `PasswordCallback`; the application's `CallbackHandler` fills in those callbacks; and the authentication module verifies them against a trusted source before reporting success or failure to `LoginContext`. Once JAAS completes `commit()`, the resulting identity is represented as a `Subject` and `Principal`s.

Key takeaway:

> **The handler collects or supplies credentials; the `LoginModule` verifies credentials. The handler does not turn input data into a trusted identity on its own.**

This lesson explains the API contract, login flow, handling `char[]` passwords, unsupported callback scenarios, the relationship with `login`/`commit`/`abort`/`logout`, interactive and headless cases, and a standalone compilable/runnable **Java 17+** program. The example uses mock data **for lab use only**, never as guidance for hardcoding production passwords.

## 1. Learning Objectives

After completing this lesson, you will be able to:

1. Describe the roles of `LoginContext`, `Configuration`, `LoginModule`, `CallbackHandler`, `Callback`, `Subject`, and `Principal` in JAAS.
2. Explain why `NameCallback` holds a username and `PasswordCallback` holds a `char[]` credential yet **neither performs authentication**.
3. Implement `CallbackHandler.handle(Callback[])` supporting the agreed callback types and throwing `UnsupportedCallbackException` for unsupported types.
4. Handle `IOException`, `UnsupportedCallbackException`, `FailedLoginException`, `LoginException`, and user cancellation without returning error messages that leak login details.
5. Explain `PasswordCallback.setPassword()` / `getPassword()` / `clearPassword()`, the existence of **multiple `char[]` copies**, and the requirement to wipe each copy according to ownership.
6. Build the JAAS flow `initialize → login → commit` or `abort` and `logout`, knowing when a `Principal` is added to or removed from `Subject`.
7. Swap credential sources from CLI to UI, web requests, or a secret manager without modifying core authentication logic.
8. Distinguish an in-memory demo password comparison from a production system requiring password hashing/KDF, rate limiting, TLS, MFA/challenges, auditing, and authorization.
9. Write tests for valid/invalid logins, missing handlers, unknown callbacks, cleanup, logout, and reusing the same authentication mechanism with multiple handlers.

## 2. Where `CallbackHandler` Fits in JAAS Architecture

A typical flow diagram:

```text
                   APPLICATION
       (CLI / desktop / web / worker / secret provider)
                          |
                          | creates appropriate CallbackHandler
                          v
                 JAAS LoginContext
                          |
                          | loads LoginModule from Configuration
                          | initialize(Subject, handler, sharedState, options)
                          v
                     LoginModule
                          |
                          | "I need username and password"
                          v
              Callback[] {NameCallback,
                          PasswordCallback}
                          |
                          | handler.handle(callbacks)
                          v
                   CallbackHandler
                          |
               collects / fetches input data
                          |
                          | setName(...), setPassword(...)
                          v
                     LoginModule
                          |
                verifies against trusted source
                          |
          +---------------+----------------+
          |                                |
        success                           failure
          |                                |
         commit()                        abort()
          |                                |
          v                                v
    Subject has Principal            No identity granted
          |
       logout()
          |
    Clean up Principals/credentials per policy
```

The control flow reverses direct UI programming: **the authentication module actively requests data through callback objects, while the application decides how to obtain that data**. Thus the same `LoginModule` can work with many different `CallbackHandler`s.

### Responsibility Boundaries

| Component | Responsibility | Should Not Do |
| --- | --- | --- |
| `LoginContext` | Coordinates `LoginModule`s per JAAS `Configuration`; runs `login()` and `logout()` | Do not render forms or verify password hashes itself |
| `Configuration` | Lists `LoginModule`s, control flags, and options for an application login | Do not use as a plaintext password store |
| `LoginModule` | Requests callbacks, verifies credentials, determines outcome, contributes Principals/credentials to `Subject` | Do not call Swing/console/HTTP directly if reusability is desired |
| `CallbackHandler` | Populates supported callback types; talks to the application's UI/secret source | Do not grant an "authenticated" Principal just because a name was entered |
| `NameCallback` | Carries prompt/default name and receives the name via `setName` | Do not perform trusted account lookup |
| `PasswordCallback` | Carries prompt/echo setting and receives a `char[]` password | Do not check password hashes or protect credentials in external sources |
| `Subject` | Holds Principal and public/private credential sets added by modules per lifecycle | Do not assume any Principal added by arbitrary code is authenticated |
| `Principal` | Represents a typed identity/name | Do not represent passwords; does not imply all permissions |

**Untrusted input sources:** When an HTTP client sends a username and password, `CallbackHandler` may copy them into callbacks; however, that data becomes an authentication result only after `LoginModule` verifies it against an authoritative **server-side** source and `LoginContext` succeeds per control flags.

## 3. The `CallbackHandler` Interface and Invocation Contract

Java 17 defines the core interface:

```java
public interface CallbackHandler {
    void handle(Callback[] callbacks)
            throws IOException, UnsupportedCallbackException;
}
```

This is the API signature, not a standalone Java file. Each element in `Callback[]` describes a data request or interaction. A handler typically iterates through each element like this:

```java
// Illustrative snippet inside a CallbackHandler method with valid username/secret.
for (Callback callback : callbacks) {
    if (callback instanceof NameCallback name) {
        name.setName(username);
    } else if (callback instanceof PasswordCallback password) {
        password.setPassword(secret);
    } else {
        throw new UnsupportedCallbackException(callback);
    }
}
```

**The handler does not return a separate credentials object.** It updates the passed-in `Callback`s. `LoginModule` reads the data from `NameCallback.getName()` and `PasswordCallback.getPassword()` after `handle` returns. This separates **where data comes from** from **how it is verified**.

### Why Is `Callback[]` an Array?

A `LoginModule` may need multiple pieces of information in one interaction:

- Username (`NameCallback`).
- Password or sensitive secret (`PasswordCallback`).
- Selecting a realm or authentication option (`ChoiceCallback`).
- Entering additional less-sensitive text (`TextInputCallback`).
- Displaying warnings or instructions (`TextOutputCallback`).
- Confirming proceed/cancel (`ConfirmationCallback`).
- Provider-specific or custom callbacks.

Invoking the handler with multiple callbacks lets a UI **bundle them into a single form**. However, each `CallbackHandler` must explicitly define which callback types it actually handles. Receiving an unknown callback and silently ignoring it can trick `LoginModule` into thinking all inputs were gathered when they were not.

### What If a Callback Is Unsupported?

The standard contract for an unsupported callback is throwing `UnsupportedCallbackException`, optionally referencing the offending callback. `LoginModule` can catch it and convert it into an appropriate `LoginException`. **Never** treat an unrecognized callback as "login succeeded" or silently return null for a critical field.

If the handler cannot acquire data due to I/O, the user closing the screen, a broken stream, or an unavailable secret manager, it should throw `IOException` or report failure per contract; the authentication module must **fail closed**, never falling back to a default account.

## 4. `NameCallback`: An Identifier Name Is Not Authentication Proof

`NameCallback` typically carries a username prompt and optionally a default name. Its API:

```java
NameCallback callback = new NameCallback("User: ");
callback.setName("alice");
String submittedName = callback.getName();
```

This example only passes data around; no authentication has happened. The name `"alice"` supplied by a client is **never enough** to conclude the caller is Alice.

Notes:

- `getPrompt()` is meant for users or credential providers; never let prompts drive access to untrusted data sources.
- `getDefaultName()` is a UI hint if the constructor supplied a default; it is not a verified identity.
- A username is a `String`—usually not a password secret—yet it may be PII; still apply logging and retention policies.
- Normalize/canonicalize usernames according to identity policy (Unicode, case, realm, tenant) **on the verifier side**, rather than arbitrarily trimming/lowercasing everywhere.
- If a credential store supports multiple tenants, do not let a handler supply just a bare name and accidentally query another tenant without verifying tenant scope.
- Never call `Subject.getPrincipals().add(new UserPrincipal(name))` from a UI handler before credentials are verified.

## 5. `PasswordCallback`: Passing Passwords as `char[]` and Practical Limits

`PasswordCallback` has the constructor `PasswordCallback(String prompt, boolean echoOn)`. The `echoOn` flag is a UI hint on whether typed characters should be displayed; it is **not an encryption mechanism** and does not force every GUI/terminal to obey if a handler ignores it. For passwords, `false` is standard.

```java
PasswordCallback callback = new PasswordCallback("Password: ", false);
char[] secret = {'p', 'a', 's', 's'};
try {
    callback.setPassword(secret);
    char[] provided = callback.getPassword();
    try {
        // Pass only to a valid verifier; never log, never convert to String.
    } finally {
        if (provided != null) Arrays.fill(provided, '\0');
    }
} finally {
    callback.clearPassword();
    Arrays.fill(secret, '\0');
}
```

This is an illustrative snippet requiring imports for `java.util.Arrays` and `javax.security.auth.callback.PasswordCallback`. This is a **mock secret** for the lesson, not a production password example.

### Copying and Clearing Passwords: Know Ownership

With the standard JDK implementation:

1. `PasswordCallback.setPassword(char[])` stores a **copy** of the passed array, without taking ownership of the caller's array.
2. `PasswordCallback.getPassword()` returns a **copy** for the recipient to process; the caller must wipe this array itself.
3. `PasswordCallback.clearPassword()` clears/overwrites the password held inside the callback.
4. Calling `clearPassword()` **does not** wipe the original array in the UI/handler or copies previously returned by `getPassword()`.
5. In the tested JDK 17 implementation, after `clearPassword()`, `getPassword()` may return an array overwritten with spaces rather than `null`. Therefore **do not check "cleared" via `getPassword() == null`**.
6. Java does not promise to erase every copy created by GC/runtime/native/UI/encoding layers; using `char[]` **reduces the lifetime** of plaintext in memory, rather than guaranteeing absolute memory erasure.
7. Avoid converting passwords into `String` for convenient logging or comparison because `String` is immutable and hard to wipe deliberately. Input layers, HTTP libraries, or frameworks may have already created Strings; understand your sources and minimize copies at boundaries you control.

### Proper Cleanup Sequence

```text
UI/source secret char[]   --clone--> Handler-owned char[]
                                  |
                                  | PasswordCallback.setPassword(...)
                                  v
                            Callback internal char[]
                                  |
                                  | getPassword()
                                  v
                            LoginModule local char[]
                                  |
                                  v
                             verifier

After processing:
  - LoginModule Arrays.fill(localCopy, '\0')
  - LoginModule PasswordCallback.clearPassword()
  - Handler.close() Arrays.fill(ownedCredential, '\0')
  - Application Arrays.fill(sourceSecret, '\0')
```

Never log `PasswordCallback` contents or call `Arrays.toString(password)`. Never place passwords in exception messages, `Subject.Principal`, JAAS config files, JVM system properties, or long-lived fields of a `LoginModule`.

## 6. Difference Between Handler and Verifier

Compare two styles.

**Tightly coupled design (not recommended):**

```java
// Illustrates an anti-pattern only, not a standalone program.
boolean login() {
    String name = console.readLine("User: ");
    char[] password = console.readPassword("Password: ");
    return callCredentialDatabase(name, password);
}
```

Here the authentication module depends directly on `console`. When the app runs in a servlet without a console, a headless test, or a worker using a secret manager, you have to rewrite authentication code.

**Decoupled design with JAAS:**

```text
LoginModule:
    NameCallback + PasswordCallback
        -> handler.handle(...)
        -> verifier.verify(name, password)
        -> commit Principal if authentication succeeds

CLI CallbackHandler:
    console.readLine/readPassword

GUI CallbackHandler:
    input from form rendered by UI framework

Web CallbackHandler:
    data from request over HTTPS with proper session/auth flow

Service CallbackHandler:
    fetches secret from vault or identity bootstrap per policy
```

The verifier is backed by a **trusted credential store**; never read expected passwords from the attacker-controlled request itself. `CallbackHandler` can be swapped without changing verification policy. This provides **separation of concerns**, testability, portability, and clear trust boundaries.

## 7. How Do `LoginContext` and `Configuration` Orchestrate?

`LoginContext` coordinates one or more `LoginModule`s based on `Configuration`. An entry typically includes:

- The `LoginModule` class name.
- Control flag: `REQUIRED`, `REQUISITE`, `SUFFICIENT`, or `OPTIONAL`.
- Module options, such as a realm name or credential service identifier, **never plaintext passwords**.

Pseudo-config example:

```text
sample {
    com.example.security.DirectoryLoginModule required
      realm="members";
};
```

This is **conceptual syntax** for a JAAS config; the class name above is illustrative, not a built-in JDK class. The complete program in Section 10 builds `Configuration` in Java so no external file is needed.

Initialization example:

```java
// Illustrative; assumes subject/handler/config come from trusted sources.
LoginContext loginContext =
        new LoginContext("sample", subject, handler, config);

loginContext.login();             // orchestrates LoginModule.login + commit/abort
Subject authenticated = loginContext.getSubject();
loginContext.logout();            // calls logout on participating modules
```

### Control Flags Affect the Overall Outcome

| Flag | Summary meaning | Risk when misunderstood |
| --- | --- | --- |
| `REQUIRED` | Module must succeed; even on failure, subsequent modules in the chain may still run before reporting failure | Assuming login succeeded because a later module passed despite a required module failing |
| `REQUISITE` | Module must succeed; failure typically terminates the overall login immediately | Skipping fail-closed checks on mandatory steps |
| `SUFFICIENT` | Success may allow early completion if no prior required/requisite failure occurred | Misusing to bypass mandatory authentication or policy checks |
| `OPTIONAL` | Contributes to overall policy per JAAS rules; not inherently mandatory | Assuming an optional module enforces MFA or mandatory policy |

The outcome **of one `LoginModule`** is not the outcome of the **entire `LoginContext`** when multiple modules exist. Do not cobble together password + OTP steps with control flags without understanding error handling, ordering, short-circuiting, and `commit/abort`. Real MFA needs protocol binding between factors, not just two input boxes.

### A `CallbackHandler` May Be Passed to Multiple Modules

`LoginContext` may pass the same handler to multiple `LoginModule`s in a configuration, yet each module may request different callback types. If a newly added module requests `TextInputCallback` while the handler only supports Name/Password, `handle` should throw `UnsupportedCallbackException`. That is an integration signal to **deliberately update or reconfigure** the handler, not a reason to silently skip the new step.

## 8. `LoginModule` Lifecycle: `initialize`, `login`, `commit`, `abort`, `logout`

For `javax.security.auth.spi.LoginModule`, the core methods are:

```java
void initialize(Subject subject, CallbackHandler handler,
        Map<String, ?> sharedState, Map<String, ?> options);
boolean login() throws LoginException;
boolean commit() throws LoginException;
boolean abort() throws LoginException;
boolean logout() throws LoginException;
```

Meaning:

1. `initialize` receives `Subject`, handler, `sharedState`, and `options`. It must not immediately publish unauthenticated Principals.
2. `login` requests callbacks, verifies credentials, and records temporary module state. Local success does not mean adding Principals immediately; `LoginContext` still evaluates other modules.
3. `commit` is invoked when JAAS determines overall login succeeded; the module may add appropriate `Principal`s and credentials to `Subject`.
4. `abort` is invoked when overall login fails; the module must discard temporary state and roll back committed changes if applicable.
5. `logout` removes identities/credentials that **this module itself** contributed and ends the session per contract.

**Commit only after authentication.** A common security bug is adding a Principal to `Subject` as soon as the handler supplies a username, while the subsequent password check fails. Separating callback collection from verification and commit prevents half-baked identity states.

### `Subject` and `Principal` Are Not Password Stores

`Subject` holds `Principal`, public credential, and private credential sets. A module should add only what policy requires with clear semantics. Never put plaintext passwords into a Principal name or permanent credential set merely for convenience. For sessions/tokens, enforce lifecycles, read/delete permissions, expiration, refresh, and logout.

In Java, a `Subject` can be marked read-only, causing set modifications to fail. `LoginModule` should treat failing to commit into a read-only `Subject` as a configuration/policy error rather than silently claiming commit succeeded.

## 9. Reference Architecture for a Real Application

Suppose a system has multiple entry sources:

```text
+---------------------+   +---------------------+
| Desktop UI Handler  |   | Web Request Handler |
+---------------------+   +---------------------+
          |                           |
          +-------------+-------------+
                        |
                        v
                NameCallback
                PasswordCallback
                        |
                        v
               DirectoryLoginModule
                        |
                        v
                CredentialVerifier
          (trusted credential database/service)
                        |
         +--------------+-------------+
         |                            |
      authenticated                 rejected
         |                            |
        Subject                     LoginException
        Principal                   no Principal
```

You can swap `DirectoryLoginModule` for another module if the callback/verification contract differs, or swap UI handlers while keeping the module unchanged. However, "reuse" must never blur trust boundaries: web requests are attacker-controlled data, whereas stored password hashes/secret verifiers are protected data. A handler must never let user input pick arbitrary credential database endpoints.

### Testable Interfaces and Layering

```text
CredentialsProvider (application/UI layer)
    -> supplies username + char[] scoped to the request

CallbackHandler (JAAS adapter)
    -> translates callback requests into data

LoginModule (orchestration/JAAS integration)
    -> selects verifier, maps result to JAAS state

CredentialVerifier (server-side policy)
    -> password hashing/KDF, account state, lockout/rate limits, MFA

Subject/Principal (authenticated identity)
    -> authorization layer checks business permissions
```

Small applications do not have to split every layer into separate classes; this mental model lets you change UI and credential backends without dragging cryptography into presenters.

## 10. Java 17+ — Standalone Program Verifying `CallbackHandler`

The example uses pure **JDK 17**, requiring no database, JAAS config file, or external libraries. It includes:

- `UserPrincipal` as a Java record holding a **name**, never a password.
- `LabLoginModule` requesting `NameCallback`/`PasswordCallback` and performing a **mock** check.
- `FixedHandler` populating callbacks, holding a `char[]` copy, and implementing `AutoCloseable` to wipe its copy.
- `Configuration` constructed directly in code with one `REQUIRED` module.
- `LoginContext` for valid and invalid cases; checking Principal counts after commit/logout/failure.
- Test for `UnsupportedCallbackException` on an unsupported callback type.
- Test that `PasswordCallback.clearPassword()` removes the old value **without relying on `getPassword() == null`**.

**Warning on mock credentials:** the program contains a demo password in source **solely to test decoupling callbacks from login**. `Arrays.equals` and hardcoded passwords are **not** a production password-verification design. Real systems must call a trusted credential verifier with password hashing/KDF, salts, rate limiting, and account/MFA policies. Never expose this demo as an Internet-facing authentication service.

Save as **`JaasCallbackDemo.java`**:

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
import javax.security.auth.callback.TextInputCallback;
import javax.security.auth.callback.UnsupportedCallbackException;
import javax.security.auth.login.AppConfigurationEntry;
import javax.security.auth.login.Configuration;
import javax.security.auth.login.FailedLoginException;
import javax.security.auth.login.LoginContext;
import javax.security.auth.login.LoginException;
import javax.security.auth.spi.LoginModule;

public final class JaasCallbackDemo {
    public record UserPrincipal(String name) implements Principal {
        @Override public String getName() { return name; }
    }

    public static final class LabLoginModule implements LoginModule {
        private Subject subject;
        private CallbackHandler handler;
        private UserPrincipal pending;
        private boolean authenticated;
        private boolean committed;

        @Override
        public void initialize(Subject subject, CallbackHandler handler,
                Map<String, ?> sharedState, Map<String, ?> options) {
            this.subject = subject;
            this.handler = handler;
        }

        @Override
        public boolean login() throws LoginException {
            if (handler == null) throw new LoginException("No callback handler");
            NameCallback name = new NameCallback("User: ");
            PasswordCallback password = new PasswordCallback("Password: ", false);
            char[] submitted = null;
            char[] expected = {'d','e','m','o','-','p','a','s','s'};
            try {
                handler.handle(new Callback[] {name, password});
                submitted = password.getPassword();
                if (!"alice".equals(name.getName())
                        || submitted == null
                        || !Arrays.equals(submitted, expected)) {
                    throw new FailedLoginException("Invalid credentials");
                }
                pending = new UserPrincipal(name.getName());
                authenticated = true;
                return true;
            } catch (IOException | UnsupportedCallbackException e) {
                LoginException failure = new LoginException(
                        "Credential collection failed");
                failure.initCause(e);
                throw failure;
            } finally {
                if (submitted != null) Arrays.fill(submitted, '\0');
                Arrays.fill(expected, '\0');
                password.clearPassword();
            }
        }

        @Override
        public boolean commit() throws LoginException {
            if (!authenticated) return false;
            if (subject.isReadOnly()) throw new LoginException("Read-only subject");
            subject.getPrincipals().add(pending);
            committed = true;
            return true;
        }

        private void clearState() {
            authenticated = false;
            committed = false;
            pending = null;
        }

        @Override
        public boolean abort() throws LoginException {
            if (committed) return logout();
            clearState();
            return true;
        }

        @Override
        public boolean logout() throws LoginException {
            if (committed && !subject.isReadOnly()) {
                subject.getPrincipals().remove(pending);
            }
            clearState();
            return true;
        }
    }

    public static final class FixedHandler
            implements CallbackHandler, AutoCloseable {
        private final String username;
        private final char[] credential;
        private boolean closed;

        FixedHandler(String username, char[] credential) {
            this.username = username;
            this.credential = credential.clone();
        }

        @Override
        public void handle(Callback[] callbacks)
                throws IOException, UnsupportedCallbackException {
            if (closed) throw new IOException("Handler is closed");
            for (Callback callback : callbacks) {
                if (callback instanceof NameCallback name) {
                    name.setName(username);
                } else if (callback instanceof PasswordCallback password) {
                    password.setPassword(credential);
                } else {
                    throw new UnsupportedCallbackException(callback);
                }
            }
        }

        @Override
        public void close() {
            Arrays.fill(credential, '\0');
            closed = true;
        }
    }

    private static Configuration labConfiguration() {
        return new Configuration() {
            @Override
            public AppConfigurationEntry[] getAppConfigurationEntry(String name) {
                if (!"sample".equals(name)) return null;
                return new AppConfigurationEntry[] {
                    new AppConfigurationEntry(
                        LabLoginModule.class.getName(),
                        AppConfigurationEntry.LoginModuleControlFlag.REQUIRED,
                        Map.of())
                };
            }
        };
    }

    public static void main(String[] args) throws Exception {
        Configuration config = labConfiguration();
        char[] good = {'d','e','m','o','-','p','a','s','s'};
        try (FixedHandler handler = new FixedHandler("alice", good)) {
            LoginContext context = new LoginContext(
                    "sample", new Subject(), handler, config);
            context.login();
            System.out.println("Valid login: true");
            System.out.println("Authenticated principal: " +
                    context.getSubject().getPrincipals(UserPrincipal.class)
                            .iterator().next().getName());
            System.out.println("Principal count after login: " +
                    context.getSubject().getPrincipals().size());
            context.logout();
            System.out.println("Principal count after logout: " +
                    context.getSubject().getPrincipals().size());
        } finally {
            Arrays.fill(good, '\0');
        }

        char[] wrong = {'n','o','t','-','r','i','g','h','t'};
        try (FixedHandler handler = new FixedHandler("alice", wrong)) {
            LoginContext context = new LoginContext(
                    "sample", new Subject(), handler, config);
            try {
                context.login();
                System.out.println("Wrong password rejected: false");
            } catch (LoginException expected) {
                System.out.println("Wrong password rejected: true");
                System.out.println("Principal count after failure: " +
                        context.getSubject().getPrincipals().size());
            }
        } finally {
            Arrays.fill(wrong, '\0');
        }

        char[] placeholder = {'x'};
        try (FixedHandler handler = new FixedHandler("alice", placeholder)) {
            try {
                handler.handle(new Callback[] {new TextInputCallback("OTP: ")});
                System.out.println("Unsupported callback rejected: false");
            } catch (UnsupportedCallbackException expected) {
                System.out.println("Unsupported callback rejected: true");
            }
        } finally {
            Arrays.fill(placeholder, '\0');
        }

        PasswordCallback callback = new PasswordCallback("Password: ", false);
        char[] temporary = {'x'};
        callback.setPassword(temporary);
        char[] independentCopy = callback.getPassword();
        callback.clearPassword();
        char[] afterClear = callback.getPassword();
        boolean originalRemoved = afterClear == null
                || !Arrays.equals(independentCopy, afterClear);
        Arrays.fill(temporary, '\0');
        Arrays.fill(independentCopy, '\0');
        if (afterClear != null) Arrays.fill(afterClear, '\0');
        System.out.println("Original callback password removed: " +
                originalRemoved);
    }
}
```

Compile and run:

```bash
javac --release 17 JaasCallbackDemo.java
java JaasCallbackDemo
```

**Verified exact stdout on JDK 17 in the test environment:**

```text
Valid login: true
Authenticated principal: alice
Principal count after login: 1
Principal count after logout: 0
Wrong password rejected: true
Principal count after failure: 0
Unsupported callback rejected: true
Original callback password removed: true
```

### Why Does the Program Work This Way?

1. `FixedHandler` only knows the input `username`/`credential` and the two callback types it supports. There is no "is password valid" logic in the handler.
2. `LabLoginModule.login()` creates `NameCallback` and `PasswordCallback`, asks the handler to populate them, and only then compares against the mock verifier. This is the seam to swap in a real credential service in production.
3. `NameCallback.setName` and `PasswordCallback.setPassword` populate the callback objects. After `handle`, the module reads `getName()`/`getPassword()`. Even with the password present, `Subject` receives no Principal until `commit`.
4. `char[] submitted` returned by `getPassword` is overwritten in `finally`. The callback password is cleared via `clearPassword`, the handler's copy is cleared in `close`, and `main`'s source password is wiped with `Arrays.fill`.
5. `expected` is a mock password constructed locally inside the module and wiped before returning. **This is not a password stored in a secure credential store**, and `Arrays.equals` is not an appropriate password-verification design on a production server.
6. `commit` adds `UserPrincipal("alice")` once authentication succeeds. `logout` removes the principal created by the module. With multiple modules or duplicate principals, production code must manage ownership/removal scope more carefully.
7. The wrong-password case throws `FailedLoginException`, causing `LoginContext` to fail; the demo `Subject` remains at **0 Principals**. This verifies no identity is granted after a failed login.
8. `TextInputCallback` is unsupported by the demo handler; `handle` throws `UnsupportedCallbackException` per contract. A real handler supporting OTP/challenges needs dedicated policies, not merely a text branch treated as MFA.
9. `PasswordCallback.clearPassword` is not checked via `getPassword() == null`. The test takes a copy before clearing and confirms the old value is no longer in the callback afterward, while wiping every copy held by the test code.
10. `Configuration` is constructed in Java only for self-contained execution. In deployed systems, configuration providers, module discovery, options, and classpath may be managed by an application server/container.

### Limitations of the Example

The example does not open a console or network connection, does not query a user directory, does not call a password-hashing service, does not enforce rate limits/MFA, has no concurrent sessions, performs no authorization outside `Subject`, and does not demonstrate credential lifecycles inside a web framework. It **verifies the callback mechanism and JAAS login lifecycle**, not production-grade Internet user authentication.

## 11. `CallbackHandler` for CLI: `Console` and Non-Terminal Environments

For an interactive CLI, a handler can use `System.console()` to prompt for username/password. **Illustrative code**, not standalone:

```java
Console console = System.console();
if (console == null) {
    throw new IOException("Interactive console unavailable");
}
String username = console.readLine("User: ");
char[] password = console.readPassword("Password: ");
try {
    nameCallback.setName(username);
    passwordCallback.setPassword(password);
} finally {
    if (password != null) Arrays.fill(password, '\0');
}
```

Import `java.io.Console`, `java.io.IOException`, and `java.util.Arrays`, assuming `nameCallback`/`passwordCallback` of the right types are provided. This belongs **inside a handler**, not verifier logic.

Notes:

- `System.console()` can return `null` inside IDEs, CI, Docker, daemons, redirected stdin, or non-interactive environments. Do not accidentally fall back to `Scanner.nextLine()`, which echoes passwords in plaintext.
- `Console.readPassword` disables echo on supported terminals, yet you must still protect the environment, process permissions, and shell history.
- Users can cancel or send EOF; never pass `null` to a verifier and treat it as a valid empty password.
- A CLI handler might be called on another thread depending on the framework; if a UI is single-threaded, synchronize/dispatch input safely.
- Avoid passing passwords in `String`s, environment variables, or command-line arguments whenever possible; those sources can leak via process inspection, logs, and core dumps.

## 12. `CallbackHandler` for Web and Headless Services

In web apps, credentials may arrive from an HTTPS request, browser challenge, reverse proxy, or identity provider. **`CallbackHandler` does not verify TLS itself**, does not verify request authenticity, and does not replace CSRF/anti-automation/rate-limiting protections.

### Request-Scoped Handler

A handler receiving username/`char[]` for **one login attempt** should have a narrow lifetime:

```text
HTTPS request -> input validation -> request-scoped CallbackHandler
      -> JAAS LoginContext.login()
      -> LoginModule -> credential verifier
      -> JAAS Subject -> session mapping
      -> request cleanup / wipe char[] / close handler
```

Never let a singleton handler hold `username`/`password` across multiple requests; that causes **credential mix-ups** between users. Create a fresh handler/`LoginContext` per request/session context and avoid uncontrolled `ThreadLocal` usage with async execution or thread pools.

### Headless Service with a Vault

A service may need to log in to another system using a secret issued by a vault/KMS/secret manager. The handler can request the password/token from the provider under the workload's identity, populate the callback, and wipe its copy. `LoginModule` remains responsible for passing that data to the target system's verifier and protecting authentication state.

Do not treat the secret manager returning a credential as proof that the current caller is authorized. Enforce IAM, workload identity, environment/tenant scoping, and retrieval auditing. If secret retrieval fails, the handler should report an internal error clearly and login must fail closed—never fall back to an empty password or default backup credential.

### Differences When Using Modern Authentication

JAAS `CallbackHandler` commonly appears in JDK security providers, application servers, Kerberos/SASL, or custom login modules. For OIDC/OAuth2/SAML, authentication is usually handled by dedicated protocol frameworks; do not take an access token and shoehorn it into `PasswordCallback` as a "password" without an explicit adapter/protocol design.

Separating credential collection from verification is an **architectural principle**, not a mandate that every modern app must use JAAS as the gateway for all identity protocols.

## 13. Specialized Callbacks: OTP, Method Selection, and MFA

Beyond Name/Password, JAAS provides other callbacks. They have **different semantics**, and not every input should be treated as a password.

| Callback | Data / Role | Example usage |
| --- | --- | --- |
| `NameCallback` | Username or identifier | Selecting user identity |
| `PasswordCallback` | `char[]` secret, policy-controlled echo off | Password or secret challenge response |
| `TextInputCallback` | Plain text input | Entering realm/attribute name; **be careful if used for OTP/secrets** |
| `TextOutputCallback` | Displaying information/messages | Policy notices, instructions |
| `ChoiceCallback` | Choosing one or more options from a list | Choosing realm/auth method |
| `ConfirmationCallback` | Confirm/cancel | User agrees to proceed |
| `LanguageCallback` | Desired locale | UI localization |
| Provider-specific callback | Data not standardized across all modules | Hardware token, challenge, key handle |

For OTP or WebAuthn/FIDO2, merely "adding another input box" is not MFA. You must validate challenge nonces, expiration, binding to the attempt/user/session, replay resistance, rate limiting, and the authenticator's trust model. If an OTP value is sensitive, use an appropriate data type/handler and clean it up per threat model; `TextInputCallback` uses `String`, which can lengthen secret lifetime.

### When the UI Does Not Support a New Callback

When upgrading a `LoginModule` to require an additional callback, older handlers should throw `UnsupportedCallbackException`. Integration tests must catch this mismatch and roll out updated handlers/clients accordingly; never "default OTP to pass" or skip a prompt that merely looks optional. If a module requires a callback to authenticate and cannot collect it, **login must fail**.

## 14. Exceptions and Safe Error Handling

`CallbackHandler.handle` declares two checked exceptions:

- `IOException`: input I/O or collection failed, such as a console/vault/network adapter error.
- `UnsupportedCallbackException`: the handler does not support a requested callback type.

Inside `LoginModule.login()`, convert these appropriately into `LoginException` (preserving the internal cause) so `LoginContext` orchestrates failure/abort. Invalid credentials per authentication policy should throw `FailedLoginException`.

### Distinguishing Three Failure Types

| Situation | Nature | Proper behavior |
| --- | --- | --- |
| Wrong username/password | Authentication failed | Reject and enforce rate limiting/lockout policy |
| Handler does not support callback | Integration/configuration failure | Reject, log internal error marker, fix handler/module |
| Cannot read secret source | Availability/I/O failure | Reject per policy; no uncontrolled fallback |

For untrusted clients, avoid detailed responses like "username exists but password is wrong" or "vault key for tenant X exists." External messages should be consistent and reveal neither user nor secret inventory; internal logs record error types, correlation IDs, and sanitized metadata.

### Cleanup on Every Branch

In the demo, `finally` always wipes `submitted` and `PasswordCallback`, even when `handle` throws `IOException` or `UnsupportedCallbackException`. When login fails, `abort` must clear module state; the handler must still `close` and wipe buffers it owns.

**Do not wipe passwords only when login succeeds.** Failed credentials are still sensitive—and might even be a user's real password typed under the wrong username.

### Avoid Broadly Catching Exceptions to Claim Success

Never do this:

```java
// Anti-pattern, not a standalone program.
try {
    loginContext.login();
} catch (Exception ignored) {
    session.setAuthenticated(true); // DANGEROUS.
}
```

Any exception during login must fail authentication per policy. If the application needs technical details for troubleshooting, log safely on the server without exposing secret-bearing exception chains.

## 15. Thread Safety, Lifecycle, and Reentrancy

Never assume a `CallbackHandler` is thread-safe by default. The interface only defines `handle(Callback[])`; it **does not** promise:

- The handler will not be called concurrently across login attempts.
- A callback will only be populated once.
- A UI always has an interactive thread.
- The handler may continue reading secrets after the login attempt ends.
- `Callback[]` will forever contain only `NameCallback` and `PasswordCallback`.
- A `LoginModule` can be safely reused across different requests.

A handler holding `username`/`credential` fields should typically be **request-scoped or attempt-scoped**. If a global credential provider is needed, inject a thread-safe service with clear trust boundaries while keeping secret data short-lived per instance.

### Race Condition Risks

Suppose a singleton handler shares `currentUsername` and `currentPassword` fields. Request A sets Alice and is preempted; Request B writes Bob into the same fields; then A's handler resumes and supplies Bob's username with Alice's password or vice versa. That is not just a logic bug—it can cause severe authentication/identity mix-ups. Fix: **never store request credentials in global state**, snapshot per attempt, and scope cleanup properly.

### Do Not Access UI Threads Incorrectly

Desktop UI frameworks like Swing/JavaFX have strict thread rules. A JAAS `LoginModule` may invoke a handler from a worker thread; a handler displaying a dialog must dispatch to the proper UI thread without deadlocking or freezing the UI. Never call `System.console()` in a server process merely because an interface asks for a password.

## 16. Production Password Verifiers: Do Not Trust the UI

A handler may deliver a secret in the "right format," yet **that does not verify the credential**. The `LoginModule`/verifier must rely on a protected source and password policy, typically:

1. Look up the account from a tenant/realm-scoped directory/database with user-enumeration protections.
2. Fetch a salted password verifier/hash; never store plaintext.
3. Use a properly parameterized password hashing/KDF algorithm such as Argon2id, scrypt, bcrypt, or PBKDF2 per standards and organizational/library support. Never use a bare SHA-256 hash of a password as a production verifier.
4. Compare safely to avoid significant timing leaks; plan rehashing/migration when policies change.
5. Enforce rate limiting, controlled backoff/lockout, brute-force/credential-stuffing monitoring, and MFA where needed.
6. Check account status, credential expiry/revocation, and protocol replay/challenge-reuse defenses.
7. Upon success, create a Principal/session with explicit identity and scope; application layers govern sessions and authorization.
8. Do not retain passwords after completion; clear callbacks and app-controlled copies.
9. Never write passwords, raw hashes/challenge responses, or tokens to logs, traces, or exception messages.
10. Ensure credential transport uses HTTPS/secure channels; browser/password-manager/IdP flows need appropriate CSRF and session controls.

`Arrays.equals(submitted, expected)` in the Java demo is merely an easy-to-read **mock** comparison proving `CallbackHandler` does not verify. It is **not** a substitute for a secure KDF password verifier or constant-time password protocol.

## 17. Testing Strategy: Test Module and Handler Independently

To leverage the decoupled architecture, maintain **three layers of tests**.

### 17.1 Unit-Testing the Handler Alone

Pass sample callbacks and verify the handler:

- Populates `NameCallback` accurately.
- Populates `PasswordCallback` with data for the right login attempt.
- Throws `UnsupportedCallbackException` on unsupported callbacks.
- Fails closed when the credential source is unavailable or the handler is closed.
- Never returns another request's password under concurrent attempts.
- Never leaks data in logs or exceptions.
- Wipes owned buffers after `close`, even if `handle` failed.

### 17.2 Unit-Testing the `LoginModule` Alone

Supply a fake handler and fake (or lab) credential verifier. Verify:

- Valid login → `login()` succeeds; only `commit()` adds the Principal.
- Invalid login → `FailedLoginException`/`LoginException`, no authenticated Principal.
- `PasswordCallback.getPassword()` returns null/empty → authentication fails per policy.
- Handler throws `IOException`/`UnsupportedCallbackException` → `LoginException` and cleanup.
- `abort()` cleans temporary state when another module in the same `LoginContext` fails.
- `logout()` removes only Principals created by this module and leaves other modules' identities intact.
- Read-only `Subject` → controlled commit failure.
- Credential verifier outage → fails closed; never falls back to a default password.
- Password cleanup runs on failure branches as well as success.

### 17.3 Integration Testing `LoginContext`

Run with a real JAAS `Configuration`:

| Scenario | Expected Outcome |
| --- | --- |
| Handler supplies valid username/secret, `REQUIRED` module | `LoginContext.login()` succeeds; `Subject` has Principal |
| Handler supplies wrong password | `LoginException`; no Principal granted |
| Handler supplies username from another tenant | Server-side verifier rejects or scopes to right namespace; no session mix-up |
| Handler does not support required callback | Login fails; safe integration log recorded |
| Handler closed before login | I/O/integration failure; no authentication |
| Successful login followed by logout | Module-owned Principals/credentials are cleaned up |
| Multiple `REQUIRED` modules | One required failure → overall failure |
| Mandatory MFA module | Missing valid callback/response → fails |
| Concurrent requests | No credential leakage across attempts |
| `PasswordCallback` clear | Old value gone from callback-owned storage; caller-owned copies wiped too |
| `LoginModule` verifier network error | No bogus successful Principal created |
| UI password masking | Echo policy honored by handler/UI; no logging |
| Reusable UI | Same `LoginModule` works with CLI and web handlers under the same contract |

**Crucial point:** a passing test is not merely "the handler filled name/password"; inspect the authentication result through `LoginContext`/`Subject`. Conversely, a `Subject` holding an app-constructed Principal does not prove `LoginContext` verified it if added in the wrong place.

## 18. Common Mistakes and How to Fix Them

| Mistake | Consequence | Fix |
| --- | --- | --- |
| `LoginModule` reads `System.in`/UI directly | Untestable/headless-incompatible, environment-locked | Request callbacks and pass a handler |
| `CallbackHandler` decides "password is valid" | Mixes data collection with credential verification | Move verification into `LoginModule`/trusted verifier |
| Handler adds a `Principal` itself | Can grant identity before verification | Commit Principals only after authentication |
| Not calling `setSSLParameters`? | Unrelated to JAAS callbacks | Do not mix network TLS configuration with JAAS callbacks |
| Handler ignores unknown callbacks | New auth steps silently bypassed or missing data | Throw `UnsupportedCallbackException` |
| Handling `NameCallback` while skipping `PasswordCallback` | Login gets null/empty secret or unclear failure | Support full contract or fail |
| Converting `char[]` password to `String` | Hard to clear secret from RAM | Keep `char[]` wherever API allows |
| Calling only `clearPassword` | Copies in handler/module remain | Wipe every buffer per ownership |
| Assuming `clearPassword` always yields `getPassword()==null` | Broken cleanup check on JDK 17 | Verify overwrite per contract, not null |
| Using `Arrays.equals` as production password verifier | Missing hash/KDF/mitigations and policy | Use a trusted password verifier |
| Putting passwords in JAAS options | Secret leaks via config/logs | Use a secret manager/credential store |
| Singleton handler holding request credentials | Race/cross-user credential mix-up | Handler per attempt; no global secret state |
| Console is null so reading secret via `Scanner` with echo | Password exposed in console/logs | Fail closed or use secure input |
| Exposing "account X exists" errors | User enumeration | Generic client message; sanitized internal logs |
| `login()` fails yet app marks session authenticated | Auth bypass | Grant session only when `LoginContext.login` succeeds |
| Broken `abort`/`logout` implementation | Principals/credentials retained past lifecycle | Clean state and remove only own identities |
| Letting untrusted handlers choose arbitrary key/vault scopes | SSRF/secret enumeration/tenant isolation bug | Allowlist trusted realms/key lookups server-side |
| Treating JAAS login = authorization | Authenticated user can exceed privileges | Enforce RBAC/ABAC by tenant/resource/action |
| Reusing multi-purpose handler without checking callbacks | Missed MFA/challenges and easy misuse | Explicit supported callback types + integration tests |
| Reusing shared mutable `Subject` across requests | Mixed principals/sessions | Isolate and scope `Subject` lifecycle per security context |

In the "`setSSLParameters`" row, the point is **never mixing distinct security modules**: `SSLParameters` belongs to JSSE/TLS configuration, not JAAS password collection. Configure/verify TLS at the network layer, while `CallbackHandler` handles data handoff to the authentication module.

## 19. Secure Deployment Checklist

Before shipping a JAAS adapter to production, confirm:

1. **Which component requests callbacks?** `LoginModule`/provider has a clear callback-type contract, ordering/semantics, and failure handling.
2. **Who creates the handler?** Application creates a request/attempt-scoped handler and passes it to `LoginContext`; the handler holds no global secrets.
3. **Where do credentials originate?** UI, HTTPS request, vault, or token provider; scope, permissions, and lifetime are explicit.
4. **Where is input validation?** Size/encoding bounds, policy-driven normalization; never let prompts/usernames become arbitrary paths/URL queries.
5. **Is the verifier trustworthy?** Server-side credential store/password hashes, strength policy, rate limits, lockouts, MFA, and monitoring.
6. **How is password ownership tracked?** Inventory all `char[]`/String/encoded copies across source, callback, module, and provider; wipe what you control.
7. **How are unsupported callbacks handled?** Throw the proper exception and never let login pass.
8. **How are `LoginModule`s configured?** Control flags and required checks introduce no bypasses.
9. **When are Principals committed?** Only after successful authentication, never from handlers or unauthenticated requests.
10. **Are `abort`/`logout` idempotent and ownership-safe?** Leave no Principals/credentials behind on failed login or logout.
11. **Is logging safe?** Never log passwords, tokens, hashes, or credential-store responses; include correlation IDs, audit events, and retention limits.
12. **Are concurrent attempts isolated?** Never share mutable handlers or `Subject`s across scopes.
13. **Is transport secure?** HTTPS/TLS peer identity and session security apply independently of JAAS.
14. **Are negative tests present?** Wrong password, unknown user/tenant, unsupported callback, null handler, vault outage, cancellation, and concurrency.
15. **Does the UI support users safely?** Echo off, accessibility/localization, cancel/timeout, and error messages that leak no secrets.
16. **Is identity properly authorized?** After JAAS authentication, the application still checks authorization for tenant/resource/action.
17. **Are secrets rotated/revoked?** Password resets, account disabling, token/key rotation, and login sessions reflect actual policy.
18. **Are provider/JDK quirks verified?** Tested on exact Java 17+ builds, app servers/containers, and JAAS `Configuration` loading mechanisms.
19. **Is observability measuring the right things?** Measure sanitized login outcomes/failure reasons, latency, and callback integration errors without capturing passwords.
20. **No homegrown MFA protocols:** If OIDC/WebAuthn/OTP is required, use a reviewed standard implementation with full binding rather than reading a single String as an OTP.

## 20. Hands-On Exercises

### Exercise 1 — Swap Credential Source While Keeping the Verifier

Keep `LabLoginModule` from the lab and write another `CallbackHandler` reading username/password from a mock request object instead of `FixedHandler`. Do not edit `LabLoginModule`'s verification code. Verify valid/invalid logins and confirm `char[]` copies are wiped per ownership.

### Exercise 2 — Unsupported Callback

Invoke a handler with `NameCallback` + `TextInputCallback`. Require explicit `UnsupportedCallbackException` handling instead of silent ignoring. Outline how a system adding OTP should roll out new handlers and MFA policy without creating bypasses.

### Exercise 3 — Console May Not Exist

Implement an interactive handler using `System.console()` and `readPassword()` in a CLI lab. Run it both in a real terminal and in headless IDE/CI. When `console` returns null, how does the handler react? Why must it never automatically read passwords with echo enabled?

### Exercise 4 — Inspecting Password Copies

Use `PasswordCallback` and multiple independent `char[]` arrays. Mutate the source array after `setPassword` to verify whether the callback copy changes; mutate the array returned by `getPassword` to observe the callback's stored copy; call `clearPassword` and explain why self-managed copies must also be wiped. Never use real passwords in tests.

### Exercise 5 — JAAS Lifecycle

Add a second `LoginModule` with the `REQUIRED` control flag that returns failure. Verify `abort` is called on the first module and `Subject` holds no Principals treated as authenticated. Test `commit` and `logout` with multiple Principals to ensure each module removes only what it contributed.

### Exercise 6 — Designing a Production `CredentialVerifier`

Replace the demo array comparison with a fake interface `CredentialVerifier.verify(username, char[])`, then sketch a real adapter using salted password hashes/KDF, account status, and rate limiting. Explain why expected passwords must never travel through `CallbackHandler` or JAAS options, and how to curb user enumeration.

### Exercise 7 — Multi-Tenant / Concurrency Isolation

Run two concurrent login attempts for Alice/tenant A and Bob/tenant B. Demonstrate how a singleton mutable handler can cause credential mix-ups. Write a test using per-attempt handlers and trusted tenant context to prevent identity cross-talk.

### Exercise 8 — Web Application Integration

Design the flow: HTTPS request → input adapter → JAAS `LoginContext` → `Subject` → session principal → API authorization. Explain how `char[]` is wiped after the request, how `LoginException` is handled safely, CSRF/session fixation/MFA where needed, and why a JAAS `Subject` alone does not grant access to business data.

### Exercise 9 — `CallbackHandler` Does Not Equal Authentication

An attacker sends `username="admin"` and an arbitrary password; the handler populates Name/Password callbacks cleanly. Why must the application still reject the login? Pinpoint where verification occurs, where Principals are committed, and where authorization is checked.

**Completion criteria:** you can build a `LoginModule` **independent of terminal, UI, or HTTP**, implement multiple handlers for different credential sources, handle callback types/exceptions per contract, protect sensitive data via ownership-based cleanup, and add Principals to `Subject` only after JAAS authentication succeeds per policy.

## 21. References

- [Java SE 17 — CallbackHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/callback/CallbackHandler.html): `handle(Callback[])`, `IOException`, and `UnsupportedCallbackException`.
- [Java SE 17 — Callback](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/callback/Callback.html): marker interface for interactive requests.
- [Java SE 17 — NameCallback](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/callback/NameCallback.html): prompt and username.
- [Java SE 17 — PasswordCallback](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/callback/PasswordCallback.html): `setPassword`, `getPassword`, `clearPassword`, `echoOn`.
- [Java SE 17 — UnsupportedCallbackException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/callback/UnsupportedCallbackException.html): unsupported callback types.
- [Java SE 17 — LoginContext](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/login/LoginContext.html): login, logout, and JAAS orchestration.
- [Java SE 17 — LoginModule](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/spi/LoginModule.html): `initialize/login/commit/abort/logout` lifecycle.
- [Java SE 17 — Configuration](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/login/Configuration.html) and [AppConfigurationEntry](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/login/AppConfigurationEntry.html): declaring modules and control flags.
- [Java SE 17 — Subject](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/Subject.html): Principals, credentials, and JAAS identity.
- [Java SE 17 — Principal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/Principal.html): identity object.
- [Java SE 17 — JAAS Authentication Tutorial](https://docs.oracle.com/en/java/javase/17/security/jaas-authentication-tutorial.html): relationship between `LoginContext`, `LoginModule`, and `CallbackHandler`.
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): application authentication, responses, logging, MFA, and brute-force controls.
- [OWASP Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html): salted password hashing/KDF, rehashing, and verifier protection.
