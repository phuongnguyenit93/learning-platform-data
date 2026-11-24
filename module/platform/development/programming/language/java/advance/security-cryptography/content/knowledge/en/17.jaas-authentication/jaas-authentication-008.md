# 17.8 Credential Management, Read-Only `Subject`, and Handling `LoginException`

## 1. Learning Objectives

In **JAAS (Java Authentication and Authorization Service)**, a successful login is more than returning `true`. The system must also manage **identities (`Principal`)**, **credentials**, the **`Subject`** object, the login–logout lifecycle, and authentication failure cases. Seemingly simple mistakes—such as putting a password into a `String`, marking a `Subject` read-only too early, or swallowing a `LoginException`—can cause secrets to linger longer than necessary or cause the application to accept an invalid authentication state.

After this lesson, you will be able to:

1. Distinguish `Principal`, **public credentials**, **private credentials**, and temporary secrets used only during login.
2. Understand the roles of `LoginContext`, `LoginModule`, `CallbackHandler`, `PasswordCallback`, and `Configuration`.
3. Manage credentials from acquisition, authentication, insertion into `Subject`, usage, and logout through **destroying secrets** via `Destroyable`.
4. Explain accurately what `Subject.setReadOnly()` does and **does not** do, especially the difference between **locking set structure** and **erasing/destroying data inside a credential object**.
5. Handle `LoginException`/`FailedLoginException` following the **fail-closed** principle, with proper per-phase rollback/cleanup, minimal logging, and zero password leakage.
6. Run a **Java 17+** example demonstrating login, a read-only snapshot, normal cleanup, logout with a locked `Subject`, and a failed login.

**Scope:** application-level JAAS / Java SE, not a guide to writing a production authentication provider. The sample program uses a hardcoded mock password purely to test the lifecycle and does **not** replace Kerberos, LDAP, IAM, KMS, password hashing, or a real credential store.

## 2. What Components Does JAAS Have?

```text
      UI / Application                    Authentication mechanism (pluggable)
      ------------------                 ---------------------------------
      Create LoginContext
           |
           | name + CallbackHandler + Configuration (+ optional Subject)
           v
      LoginContext.login()
           |
           +-------> LoginModule A.login()   <--- CallbackHandler
           |                 |                        NameCallback
           +-------> LoginModule B.login()            PasswordCallback
           |                 |
           |          Results and control flags
           v
      If overall success:
           LoginModule.commit()   --> Subject:
                                     - Principals
                                     - Public credentials
                                     - Private credentials

      If overall failure:
           LoginModule.abort()    --> clean up temporary/added state

      When ending the session:
           LoginContext.logout()  --> LoginModule.logout()
                                       remove credentials/principals added by module
                                       and destroy secrets as supported
```

| Type/API | Role | Remember |
| --- | --- | --- |
| `javax.security.auth.Subject` | Container for identities and credentials associated with an entity | Does not authenticate anyone on its own; **must be populated by a trusted process** |
| `java.security.Principal` | An identity/name/role represented as an object | Not a password or token |
| `Subject.getPublicCredentials()` | Set of credentials shareable per policy, depending on type | "Public" does not mean anyone has write permission |
| `Subject.getPrivateCredentials()` | Set of private credentials, which may hold tickets/keys/tokens | **Does not guarantee automatic encryption, wiping, or log prevention** |
| `javax.security.auth.login.LoginContext` | Client entry point into the login/logout lifecycle | Relies on configured `LoginModule`s |
| `javax.security.auth.spi.LoginModule` | Plugin implementing `initialize/login/commit/abort/logout` | Holds actual auth responsibility; adds/removes only state it owns |
| `CallbackHandler` | Connects the module to the source of username/password/OTP, etc. | Keeps the module decoupled from how input is collected |
| `NameCallback` | Requests/receives a username | A username alone does not prove identity |
| `PasswordCallback` | Receives a password as a **`char[]`** | `clearPassword()` clears the copy stored inside the callback |
| `Configuration` / `AppConfigurationEntry` | Selects modules and JAAS control flags | Flags determine overall success/failure |
| `LoginException` | Checked exception for JAAS login/logout | Must never be turned into a successful login |
| `Destroyable` | `destroy()` / `isDestroyed()` contract | Clears secret material at the credential implementation level |

**Distinguishing authentication from authorization:** `LoginContext.login()` only establishes identity and credentials according to the modules. Having a `Subject` contain `Principal("alice")` does not by itself authorize Alice to access specific accounts, resources, or business operations. Authorization must additionally check permissions/roles, resources, tenants, scopes, policies, and session state. Likewise, users must never be allowed to call `subject.getPrincipals().add(new Principal(...))` on a `Subject` treated as a trusted identity source.

## 3. How Do `Principal`, Public Credentials, and Private Credentials Differ?

For example, when a user logs in via Kerberos, a `Subject` may carry an identity principal and the appropriate tickets/keys. With a custom module, the contents might look like:

```text
Subject (object tied to the login)
|
+-- Set<Principal>
|     +-- UserPrincipal("alice")              // identity
|
+-- Set<Object> publicCredentials
|     +-- public certificate / shareable public data, if needed
|
+-- Set<Object> privateCredentials
      +-- session/ticket/token/secret object, if needed by module
```

**The `Subject` sets are `Set`s, not dedicated secret vaults.** Private credentials are still ordinary Java objects, governed by `Subject`/SecurityManager rules depending on the runtime, but they are **not an encrypted vault**, are not deterministically wiped by the garbage collector at a fixed time, and provide no server-side revocation guarantee. If a credential is a production access token, it needs **scope, expiry, rotation, revocation**, and dedicated policies.

### 3.1 Classification by Sensitivity

| Data | Where is it typically placed? | Rule |
| --- | --- | --- |
| Username or service identity | `Principal` after authentication | Do not treat a self-declared name as an authenticated identity |
| Verified public certificate | `publicCredentials` if required by the use case | Verify issuer/trust/usage before trusting |
| Kerberos ticket, private key handle, access token | `privateCredentials` **when needed** and governed by policy | Keep lifetime short, restrict access, avoid printing/logging |
| Password entered during login | Temporary `PasswordCallback` / auth processing memory | **Do not** retain as a "session credential" after login |
| Raw password as a `String` | **Avoid** | `String` is immutable and cannot be actively wiped from the heap |
| Passwords/verifiers stored by an auth server | Dedicated identity service | Do not use a JAAS `Subject` as a password store |

A module does not need all three sets: a `Subject` containing only a `Principal` is normal if no post-login credential is needed. Conversely, keeping all raw passwords under `privateCredentials` simply because they are "private" is a dangerous design.

### 3.2 Two Methods for Retrieving Private Credentials Are Not the Same

```java
// Illustrative snippet once a trusted Subject is available:
java.util.Set<Object> liveSet = subject.getPrivateCredentials();
java.util.Set<MyCredential> filtered =
        subject.getPrivateCredentials(MyCredential.class);
```

- `getPrivateCredentials()` returns a **set backed by the `Subject`**. If the `Subject` is still mutable and permitted, add/remove calls on this set modify the subject.
- `getPrivateCredentials(Class<T>)` returns a **new type-filtered set**, not backed by the subject; modifying the filtered set does **not** add or remove credentials in the subject.
- When a SecurityManager is active, iterating over private credentials may be subject to `PrivateCredentialPermission`/security checks; do not assume sample code running without a SecurityManager implies every runtime grants access.
- **Do not** log `getPrivateCredentials().toString()`, iterate and print secrets, or freely serialize a `Subject`. Even if one credential has a redacted `toString()`, another implementation might not.

**Management permission does not imply extraction permission:** a private credential object may enforce its own restrictions or act as a handle to an HSM/KMS. Some keys cannot be exported as bytes; forcing `getEncoded()` and logging or falling back usually breaks the key-protection model.

## 4. Credential Lifecycle: Acquire, Use Temporarily, Commit, Destroy

A proper lifecycle separates the **password entered by the user** from the **credential issued after authentication**.

```text
[Acquire]            [Authenticate]             [Logged in]           [Logout]
char[] password ---> LoginModule.login() ---> LoginModule.commit() ---> logout()
                         |                           |                     |
                       verify                  add Principal,       remove owned items
                       password                session credential   destroy secret
                         |                           |
                  clear callback & copies      DO NOT store raw password
                         |
                  fail -> LoginException -> abort/cleanup
```

### 4.1 Why Use `char[]` Instead of `String`?

`PasswordCallback` uses `char[]` so the application can actively wipe sensitive data after use:

```java
// Illustrative snippet inside LoginModule.login(), with a callback supplying the password.
javax.security.auth.callback.PasswordCallback pwd =
        new javax.security.auth.callback.PasswordCallback("Password", false);
callbackHandler.handle(new javax.security.auth.callback.Callback[]{pwd});
char[] supplied = pwd.getPassword(); // obtain a copy to process
pwd.clearPassword();                 // clear the copy inside PasswordCallback
try {
    // Verify against a trusted identity service; never log supplied.
} finally {
    if (supplied != null) java.util.Arrays.fill(supplied, '\0');
}
```

With `PasswordCallback`, `setPassword()` copies the passed-in array; `getPassword()` returns a copied array; `clearPassword()` zeroes out the callback's internal credential. Therefore you must wipe **every copy** created by the application, not merely call `clearPassword()` and assume all data in the process is gone.

We cannot reliably control every temporary copy created by the JVM/JIT/OS in memory, yet using `char[]` with a short lifetime and clearing in `finally` still reduces exposure. **You cannot guarantee wiping every byte on the system solely via `Arrays.fill`.** For production credentials, use a provider/keystore/HSM/password verification service appropriate to your threat model.

### 4.2 `CallbackHandler` Has Its Own Responsibility

A `LoginModule` should not read `System.console()` directly or pull passwords from global variables. It requests the required `Callback`s and lets the application provide a `CallbackHandler`:

- `NameCallback`: username.
- `PasswordCallback`: `char[]` password.
- `UnsupportedCallbackException`: when the handler does not support a required callback, convert it into a controlled failure.
- `IOException`: error reading input/credential source, also handled as an authentication infrastructure failure.

**Do not** print passwords to the console inside a callback handler, and do not keep `char[]` in a long-lived field. When passwords arrive in a request body, ensure the request framework and logging already protect secrets before they reach JAAS.

### 4.3 `Destroyable`: Destroying Credential **Contents**

The `javax.security.auth.Destroyable` API defines:

```java
// Contract definition, not an implementation class:
void destroy() throws javax.security.auth.DestroyFailedException;
boolean isDestroyed();
```

A credential managing its own material can implement `destroy()` by zeroing out `byte[]`/`char[]` buffers or closing native handles. `destroy()` must be designed not to leak secrets through error messages. A destroyed object must not be reused; check `isDestroyed()` if application logic must decide its state.

**Boundary of responsibility:** `Subject.getPrivateCredentials().remove(token)` only **removes the reference from the set** and does not guarantee memory holding the secret is wiped. Conversely, `token.destroy()` may clear the internal material, yet does **not** automatically remove the object from `Subject`. Clean session termination requires handling **both removal and destruction** according to capability and actual lifecycle.

### 4.4 Real Credentials Have a Lifecycle Outside the Java Heap

Zeroing a `byte[]` does not revoke an OAuth token on the server, clear a provider's ticket cache, revoke an HSM key, or complete a network logout. Those steps depend on the credential provider. When investigating incidents, consider:

- Secrets may have been copied or captured in heap dumps/traces before destruction.
- A token may remain valid on the server after local destruction.
- A login session on one thread may currently be in use by another thread.
- Cached roles/authorizations may persist after `logout`.
- Expiry/revocation/rotation determine actual validity, not merely the `isDestroyed()` flag of a Java object.

## 5. `Subject.setReadOnly()`: What Exactly Does It Lock?

A `Subject` has three `Set`s: principals, public credentials, and private credentials. Calling:

```java
Subject subject = new Subject();
// Once structural modifications allowed by the application are complete:
subject.setReadOnly();
boolean locked = subject.isReadOnly();
```

When `subject.isReadOnly() == true`:

1. Elements **cannot be added to or removed from** `getPrincipals()`, `getPublicCredentials()`, or `getPrivateCredentials()`; mutating operations throw `IllegalStateException` (additional permission checks may apply on runtimes with a SecurityManager).
2. `setReadOnly()` is a **one-way** change; Java has no `setWritable()` to reverse that state.
3. Read-only status **does not automatically make the contained objects immutable**: a `Principal` with mutable fields or a custom credential can still have its internal state modified if its API allows it.
4. Under the Java SE contract, **`destroy()` on credentials is still permitted**. This is a critical distinction from adding/removing elements in the sets.
5. `setReadOnly()` **does not authenticate** an identity; it only prevents modifying the subject's set structure after locking.

```text
Before setReadOnly:
    Subject Principals: [Alice]
    Subject PrivateCredentials: [SessionCredential]
           |
        add/remove allowed (per permissions and runtime)
           |
       setReadOnly()
           v
After setReadOnly:
    Subject Principals: [Alice]           -- cannot be removed from Subject
    Subject PrivateCredentials: [token]   -- cannot be removed from Subject
                                                  |
                                                  +-- token.destroy() can still
                                                      wipe the secret inside token
```

**Common misconception:** "Once `setReadOnly` is called, private credentials are completely safe." False: read-only does not encrypt secrets, does not automatically guarantee trusted identity, does not block method calls that mutate **internal object state**, and does not replace destruction/rotation/revocation.

### 5.1 Why Locking `Subject` Too Early Complicates `LoginModule.logout()`

Normally `LoginModule.commit()` adds the principals/credentials it owns; `logout()` **removes** those items and **destroys** secrets. If the application calls `subject.setReadOnly()` immediately after login, the sets can no longer be modified. Oracle's JAAS `LoginModule` guide describes the pattern: for a read-only subject, the module should **destroy the credentials it added if they are destroyable**, since it cannot remove them from the subject; if credentials cannot be destroyed, logout may have to throw `LoginException`.

This means:

- Logout on a **mutable Subject**: remove principals/credentials added by the module, then destroy the corresponding secret resources.
- Logout on a **read-only Subject**: entries attached to the subject cannot be removed; the module can destroy **credential contents**; principal/credential objects remain in the sets even though the credential has been destroyed.
- A successful `logout()` on a read-only subject **does not guarantee** `subject.getPrincipals().isEmpty()` or `getPrivateCredentials().isEmpty()`.
- If a custom module blindly calls `.remove()` on a read-only subject without checking state, it can hit `IllegalStateException`, which must be handled as a failure rather than silently treating logout as successful.

### 5.2 A Safer Design: Separate Live Subject and Identity Snapshot

If you need an identity representation that **callers cannot modify**, while still letting JAAS logout remove credentials, you can:

1. **Keep the `LoginContext`'s `Subject` mutable** for the login/logout lifecycle according to module ownership.
2. After successful login, create **a separate `Subject` copying only the verified immutable principals**, without copying private credentials.
3. Call `setReadOnly()` on the **identity-only snapshot**, and pass that snapshot to identity-reading layers as needed; do not give those layers direct control over the live Subject.
4. When the session ends, call `LoginContext.logout()` on the **live Subject** so modules can clean up and destroy secrets.

This is purely an **application-specific pattern**: a copied `Subject` does not carry all JAAS state/authorization, does not update when the original changes, and is not cryptographically sealed proof of identity. **Never** allow a snapshot to keep sessions alive after real authorization has expired. Use **immutable** principal objects; a read-only Subject does not deep-freeze contained objects.

Another strategy is freezing the original subject once you have verified that the module/provider lifecycle supports read-only logout and all credentials are destroyable; test the specific module carefully. Do not treat `setReadOnly()` in sample code as a blanket best practice for every JAAS provider.

## 6. The `LoginModule` Cycle: `login`, `commit`, `abort`, `logout`

JAAS has **two phases** inside `LoginContext.login()`:

```text
Phase 1: LoginModule.login()
    - Read callbacks; verify credentials
    - Return true, false (ignore), or throw LoginException
    - Do not add Principals before overall success

Overall success per JAAS control flags?
    YES -> Phase 2: LoginModule.commit()
             - Put authenticated state into Subject
    NO  -> Phase 2: LoginModule.abort()
             - Discard temporary state, roll back if needed

After the application finishes the session:
    LoginContext.logout() -> LoginModule.logout()
             - Clean up only Principals/credentials owned by the module
```

`LoginModule`s in the same login context can share the **same `Subject` object** and `sharedState`; therefore module A **must not** call `subject.getPrincipals().clear()` or `getPrivateCredentials().clear()` to clean up its own part, because that could wipe out module B's data or pre-existing entries.

| Method | When used | What to do | What to avoid |
| --- | --- | --- | --- |
| `initialize(...)` | JAAS instantiates module | Receive `Subject`, handler, shared state, options | Storing secrets longer than necessary |
| `login()` | Authentication phase | Retrieve password via callback, verify, record **module-private** state; `return true` on success | Putting raw passwords into Subject/logs; internal retry loops |
| `commit()` | Overall login succeeds | Add **only module-owned principals/credentials** to Subject | Adding before module succeeded; swallowing commit errors |
| `abort()` | Overall login fails | Discard temporary state, roll back owned changes as possible | Leaving session tokens or principals from a failed login |
| `logout()` | Application ends session | Remove owned state (if mutable), destroy secrets, and call provider revoke if needed | Deleting another module's data; assuming a read-only subject supports removal |

### 6.1 How JAAS Control Flags Affect Overall Success

Common `AppConfigurationEntry.LoginModuleControlFlag` values:

| Flag | General meaning |
| --- | --- |
| `REQUIRED` | Module **must succeed** for overall success, though subsequent modules are usually still called |
| `REQUISITE` | Module **must succeed**; failure can terminate authentication early |
| `SUFFICIENT` | Success may allow early completion if no prior `REQUIRED`/`REQUISITE` failure occurred |
| `OPTIONAL` | Result depends on the combination of modules and overall rules |

Do not write your own `LoginContext`-like loop calling `login()` then `commit()` regardless of other modules failing. Use the JAAS-managed contract, because a module may generate temporary tokens before being allowed to write them to the subject.

## 7. `LoginException` and Failure Classification

`javax.security.auth.login.LoginException` is a **checked exception** for JAAS login/logout errors. Subclasses such as `FailedLoginException`, `AccountExpiredException`, and `CredentialExpiredException` help categorize failures when supported by a real provider. The exception caught by the application is not always the exact original subclass: many modules and providers wrap errors or throw a general `LoginException`.

### 7.1 Login Failure Never Means Proceeding as an Authenticated Guest

```java
// Snippet in an application holding LoginContext loginContext:
try {
    loginContext.login();
    javax.security.auth.Subject authenticated =
            loginContext.getSubject();
    // Grant permissions per policy only after success.
} catch (javax.security.auth.login.LoginException ex) {
    // Record audit event without passwords/tokens/secrets.
    // Deny access, discard temporary context/clean up per provider API.
    throw new SecurityException("Authentication unsuccessful");
}
```

When `login()` throws `LoginException`, the application **must not** infer successful authentication from a `Subject` that already had a name or from a callback having supplied a password. `LoginContext.getSubject()` may return `null` if overall login failed; even when passing an external `Subject`, check success before treating principals in it as authenticated.

### 7.2 Preserve Technical Causes Without Leaking Secrets

Inside a module, when `CallbackHandler.handle(...)` throws `IOException` or `UnsupportedCallbackException`, wrap it in `LoginException` and preserve the cause:

```java
// Snippet inside catch (IOException | UnsupportedCallbackException cause):
javax.security.auth.login.LoginException ex =
        new javax.security.auth.login.LoginException("Callback failed");
ex.initCause(cause);
throw ex;
```

**Outer application code** may log error codes and correlation IDs, but should not print causes containing raw passwords, tokens, callback contents, full authentication headers, or input secrets. Return a generic message such as "Authentication unsuccessful" to clients rather than overly specific distinctions like "user exists but wrong password" if that aids account enumeration.

Proper classification:

- `FailedLoginException`: credentials did not match.
- `CredentialExpiredException` / `AccountExpiredException`: credential/account expired per provider policy.
- Callback errors, misconfiguration, unreachable identity backend: **infrastructure/authentication failure**.
- `LoginException` in `commit`/`abort`/`logout`: lifecycle error; clean up or raise a security event, and never claim secrets were destroyed without verifying.

### 7.3 Who Is Responsible for Retries?

Oracle's JAAS `LoginModule` documentation states that **modules should not retry internally or sleep/delay inside `login()` on authentication failure**; the application/gateway owns retry policies, rate limits, backoff, lockouts, and telemetry. Looping callback invocations inside a module can corrupt single-login state, keep passwords in memory longer, and create brute-force vulnerabilities.

### 7.4 When `commit()` Partially Fails

If a module has added a principal and then throws an exception before adding a credential, it must roll back **what that module just added**, destroy created secrets, and throw `LoginException`. Never return `true` and leave the subject carrying an identity without its required credentials.

Conversely, if `abort()`/`logout()` needs to clean up while the credential provider has lost connectivity, the module must follow its documented contract and report errors appropriately. For a token still valid on the server, local `Destroyable.destroy()` does not replace remote revocation; mark the session invalid at the application layer and track reconciliation.

## 8. Complete Java 17+ Program: `Subject`, Credentials, and `LoginException`

The following program is self-contained and needs no external JAAS configuration. It provides an **in-memory** `Configuration` selecting `ExampleModule` with the `REQUIRED` control flag, uses `OneUseHandler` to supply the password to `PasswordCallback`, and generates a random `SessionCredential` after sample authentication.

The program verifies these scenarios:

1. Login with demo user `alice`/temporary password `demo`, writing one principal and one **demo session secret** into `Subject`.
2. Create a **principal-only snapshot**, call `setReadOnly()`, attempt to mutate the snapshot, and observe `IllegalStateException`; the snapshot contains **no** private credentials.
3. `logout()` on the **mutable live Subject** removes the principal/credential and zeroes out the token.
4. Another case: mark the **live Subject read-only** before `logout`; the module can only destroy the credential and cannot remove the principal/credential from the sets.
5. Wrong login `bad` is rejected with `LoginException`; neither principal nor credential is committed.
6. Never print passwords, token bytes, or private credential contents.

> **Security note:** The module uses a hardcoded `demo` password and `Arrays.equals` **solely to illustrate the API/lifecycle**. **Never use** this in production: never hardcode passwords, never compare plaintext passwords as a real auth mechanism, and never use demo random bytes as a privileged session token. Real applications need a vetted authentication provider, salted password hashing/identity service, MFA where required, secret rotation, KMS/HSM/keystore, rate limiting, and session policies.

Create the file **`JaasCredentialLifecycleDemo.java`**:

```java
import java.io.IOException;
import java.security.Principal;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;
import javax.security.auth.Destroyable;
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

public final class JaasCredentialLifecycleDemo {
    public record UserId(String value) implements Principal {
        @Override public String getName() { return value; }
    }

    public static final class SessionCredential implements Destroyable {
        private final byte[] material = new byte[16];
        private boolean destroyed;

        public SessionCredential() {
            new SecureRandom().nextBytes(material);
        }

        @Override public synchronized void destroy() {
            Arrays.fill(material, (byte) 0);
            destroyed = true;
        }

        @Override public synchronized boolean isDestroyed() {
            return destroyed;
        }

        @Override public String toString() {
            return "SessionCredential[redacted]";
        }
    }

    public static final class OneUseHandler implements CallbackHandler {
        private final String user;
        private final char[] password;

        public OneUseHandler(String user, char[] password) {
            this.user = user;
            this.password = password; // takes ownership of caller array
        }

        @Override public void handle(Callback[] callbacks)
                throws IOException, UnsupportedCallbackException {
            try {
                for (Callback callback : callbacks) {
                    if (callback instanceof NameCallback name) {
                        name.setName(user);
                    } else if (callback instanceof PasswordCallback pwd) {
                        pwd.setPassword(password); // PasswordCallback copies it
                    } else {
                        throw new UnsupportedCallbackException(callback);
                    }
                }
            } finally {
                Arrays.fill(password, '\0');
            }
        }
    }

    public static final class ExampleModule implements LoginModule {
        private Subject subject;
        private CallbackHandler handler;
        private boolean authenticated;
        private boolean committed;
        private UserId principal;
        private SessionCredential credential;

        @Override public void initialize(Subject subject,
                CallbackHandler handler, Map<String, ?> sharedState,
                Map<String, ?> options) {
            this.subject = subject;
            this.handler = handler;
        }

        @Override public boolean login() throws LoginException {
            NameCallback name = new NameCallback("User");
            PasswordCallback pwd = new PasswordCallback("Password", false);
            try {
                handler.handle(new Callback[] {name, pwd});
            } catch (IOException | UnsupportedCallbackException e) {
                LoginException failure = new LoginException("Callback failed");
                failure.initCause(e);
                throw failure;
            }
            char[] actual = pwd.getPassword();
            pwd.clearPassword();
            char[] expected = {'d','e','m','o'}; // demonstration ONLY
            try {
                if (!"alice".equals(name.getName())
                        || actual == null
                        || !Arrays.equals(actual, expected)) {
                    throw new FailedLoginException("Invalid credentials");
                }
                principal = new UserId(name.getName());
                credential = new SessionCredential();
                authenticated = true;
                return true;
            } finally {
                if (actual != null) Arrays.fill(actual, '\0');
                Arrays.fill(expected, '\0');
            }
        }

        @Override public boolean commit() throws LoginException {
            if (!authenticated) return false;
            try {
                subject.getPrincipals().add(principal);
                subject.getPrivateCredentials().add(credential);
                committed = true;
                return true;
            } catch (RuntimeException e) {
                try {
                    if (!subject.isReadOnly()) {
                        subject.getPrincipals().remove(principal);
                        subject.getPrivateCredentials().remove(credential);
                    }
                } finally {
                    credential.destroy();
                }
                LoginException failure = new LoginException("Commit failed");
                failure.initCause(e);
                throw failure;
            }
        }

        private void cleanup() {
            if (committed && !subject.isReadOnly()) {
                subject.getPrincipals().remove(principal);
                subject.getPrivateCredentials().remove(credential);
            }
            if (credential != null) credential.destroy();
            credential = null;
            principal = null;
            authenticated = false;
            committed = false;
        }

        @Override public boolean abort() {
            if (!authenticated && !committed) return false;
            cleanup();
            return true;
        }

        @Override public boolean logout() {
            cleanup();
            return true;
        }
    }

    private static Configuration configuration() {
        return new Configuration() {
            @Override public AppConfigurationEntry[] getAppConfigurationEntry(
                    String name) {
                if (!"Example".equals(name)) return null;
                return new AppConfigurationEntry[] {
                    new AppConfigurationEntry(
                            ExampleModule.class.getName(),
                            AppConfigurationEntry.LoginModuleControlFlag.REQUIRED,
                            Map.of())
                };
            }
        };
    }

    private static LoginContext context(Subject subject, char[] password)
            throws LoginException {
        return new LoginContext("Example", subject,
                new OneUseHandler("alice", password), configuration());
    }

    public static void main(String[] args) throws Exception {
        Subject live = new Subject();
        LoginContext ok = context(live, new char[] {'d','e','m','o'});
        ok.login();
        SessionCredential token = live.getPrivateCredentials(
                SessionCredential.class).iterator().next();
        System.out.println("Login principal count: " +
                live.getPrincipals().size());
        System.out.println("Private credential count: " +
                live.getPrivateCredentials().size());

        Subject snapshot = new Subject(false,
                new HashSet<>(live.getPrincipals()), Set.of(), Set.of());
        snapshot.setReadOnly();
        boolean modificationBlocked = false;
        try {
            snapshot.getPrincipals().add(new UserId("mallory"));
        } catch (IllegalStateException expected) {
            modificationBlocked = true;
        }
        System.out.println("Identity snapshot read-only: " +
                snapshot.isReadOnly());
        System.out.println("Snapshot mutation rejected: " +
                modificationBlocked);
        System.out.println("Snapshot has private credentials: " +
                !snapshot.getPrivateCredentials().isEmpty());

        ok.logout();
        System.out.println("Mutable Subject cleared at logout: " +
                (live.getPrincipals().isEmpty()
                        && live.getPrivateCredentials().isEmpty()));
        System.out.println("Session credential destroyed: " +
                token.isDestroyed());

        Subject frozen = new Subject();
        LoginContext frozenContext = context(
                frozen, new char[] {'d','e','m','o'});
        frozenContext.login();
        SessionCredential frozenToken = frozen.getPrivateCredentials(
                SessionCredential.class).iterator().next();
        frozen.setReadOnly();
        frozenContext.logout();
        System.out.println("Frozen Subject still holds identity: " +
                !frozen.getPrincipals().isEmpty());
        System.out.println("Frozen credential destroyed: " +
                frozenToken.isDestroyed());

        Subject rejected = new Subject();
        LoginContext wrong = context(rejected, new char[] {'b','a','d'});
        boolean failed = false;
        try {
            wrong.login();
        } catch (LoginException expected) {
            failed = true;
        }
        System.out.println("Wrong password rejected: " + failed);
        System.out.println("Failed login Subject empty: " +
                (rejected.getPrincipals().isEmpty()
                        && rejected.getPrivateCredentials().isEmpty()));
    }
}
```

Compile with **Java 17+** (no preview features; `record` and pattern matching `instanceof` are standard features):

```bash
javac --release 17 JaasCredentialLifecycleDemo.java
java JaasCredentialLifecycleDemo
```

**Verified stdout on a JDK supporting Java 17 syntax/API:**

```text
Login principal count: 1
Private credential count: 1
Identity snapshot read-only: true
Snapshot mutation rejected: true
Snapshot has private credentials: false
Mutable Subject cleared at logout: true
Session credential destroyed: true
Frozen Subject still holds identity: true
Frozen credential destroyed: true
Wrong password rejected: true
Failed login Subject empty: true
```

### 8.1 Explaining Each Part and the Results

**`UserId implements Principal`:** the `record` holds the identity string immutably. `getName()` returns the name so JAAS APIs can work with it. Only the module adds `UserId` **after authentication succeeds**; a `UserId` constructed directly from a request must never be treated as proof of authentication.

**`SessionCredential implements Destroyable`:** holds 16 mock bytes generated via `SecureRandom`. In the demo it is **not a production access token** and is not used by anyone to grant permissions. `destroy()` zeroes the buffer and sets the destroyed flag, `isDestroyed()` enables verification, and `toString()` intentionally returns only `[redacted]`. Memory protection is not absolute, and zeroing does not erase external copies if they already exist.

**`OneUseHandler`:** takes ownership of the caller-supplied password array, passes it into `PasswordCallback`, and wipes the original array in `finally`. `PasswordCallback` makes its own copy, which the module clears via `clearPassword()`. The module also wipes the `actual` array returned by `getPassword()`. The handler is designed for **single use**; do not reuse it across retries once its password has been cleared.

**`ExampleModule.login()`:** checks the mock `name` and `password`, throwing `FailedLoginException` on mismatch; does not add a Principal at this stage. The expected password from a char array in the lesson is an **unsafe-for-production** example solely illustrating wiping temporary arrays. With a real provider, verification may be performed by an identity service, Kerberos/KDC, PAM, LDAP over TLS, a salted password verifier, or a hardware security device.

**`commit()`:** only when `authenticated == true` does it add `UserId` and `SessionCredential` to the Subject. If an add step throws a runtime exception, it rolls back what the module tried to add, destroys the token, and wraps the failure in `LoginException`. The demo is single-threaded, so checking `subject.isReadOnly()` and mutating the sets is shown in one thread; real systems must manage ownership/concurrency and provider-specific cleanup.

**`snapshot.setReadOnly()`:** the snapshot contains only the authenticated principal (copied via constructor `Subject(false, ...)`). Adding a new principal to the snapshot throws `IllegalStateException`. The snapshot holds no private credentials, so it cannot leak the demo token. It is not a new login account and does not outlive the original session.

**`ok.logout()` on the mutable live Subject:** the module removes the exact principal/token it added and then calls `token.destroy()`. The outputs `Mutable Subject cleared at logout: true` and `Session credential destroyed: true` confirm both **removing references from the subject** and **destroying the material**.

**`frozen.setReadOnly()` before logout:** the Subject's structure is locked, so the module **cannot remove** elements. The demo module checks `isReadOnly()` so it only destroys the token contents; thus `Frozen Subject still holds identity: true` and `Frozen credential destroyed: true` are **not contradictory**. This scenario illustrates why freezing the live Subject too early can leave old identities present after logout and why trust/lifetime must be managed at another layer.

**Wrong password:** the module throws `FailedLoginException`; `LoginContext.login()` reports failure with no successful `commit`. `Subject rejected` stays empty. The application knows only that **login was rejected** and must neither grant access nor expose details that help enumerate usernames.

### 8.2 Do Not Generalize the Demo into a Production JAAS Module

The code above is intentionally minimal: one module, one mock user, one thread, an in-memory `Configuration`, and an unused secret. It does **not** include distributed revocation, cache/ticket protection, multi-module shared state, logout races across threads, account locking, rate limiting, secure password storage, remote backends, audit logging, authorization, or provider-managed credentials. A production `LoginModule` must also handle exception cleanup even when revocation fails or the subject was modified by other modules.

In particular, never copy `Arrays.equals(actual, expected)` to replace production password verification; **never hardcode passwords** or pick weak hash schemes.

## 9. Comparing Two "Read-Only Subject" Strategies at Logout

| Concern | Freeze live `Subject` after login | Keep live mutable, create read-only snapshot |
| --- | --- | --- |
| Can external code mutate principals on the live object? | Cannot mutate sets after `setReadOnly()` | Only the snapshot is locked; avoid exposing the live Subject reference |
| Can logout remove principals/credentials? | **No**: Subject is locked | Yes, if the module is well-behaved and no other constraints apply |
| Can `Destroyable` credentials be destroyed? | Possible, depending on contract and module implementation | Possible; module removes and destroys |
| Do principals remain in Subject after logout? | May remain | Can be empty if cleaned properly |
| Does snapshot hold its own credentials? | Not applicable | Design-dependent: should **copy only needed identities**, avoiding secrets |
| Easy to misuse old identity after logout? | High risk if live read-only Subject reference is retained | Still requires invalidating snapshot/tokens in the application |
| When is it suitable? | Only when modules/providers are designed for read-only cleanup | When separating auth lifecycle from identity view |

**Security rule:** Never rely on `Subject.isReadOnly()` as proof that a user **is currently logged in**. A `Subject` can be read-only without ever being authenticated, and can be read-only while holding stale principals after logout. Rely on **authentication outcome, session expiration, and policy**.

## 10. Real-World Errors and How to Fix Them

| Error/Symptom | Cause | Remediation |
| --- | --- | --- |
| Login succeeds yet Subject has no Principal | Module did not `commit`, commit returned false, or flags failed | Use the proper `LoginContext` flow and check `commit` |
| `FailedLoginException` | Username/password/credential mismatch | Reject, enforce retry policy, do not leak details |
| `CredentialExpiredException` | Credential expired per provider | Require controlled re-authentication/renewal |
| `AccountExpiredException` | Account expired per policy | Reject; never silently bypass expiration |
| `LoginException` when `CallbackHandler` runs | Unsupported callback, I/O failure | Wrap cause safely; do not log secrets |
| `LoginException` in `commit` | Read-only Subject, permission denial, state-add error | Roll back owned changes, destroy secrets, fail closed |
| `IllegalStateException` on `getPrincipals().add()` | `Subject.setReadOnly()` already called | Do not mutate a read-only Subject; adjust snapshot or lifecycle design |
| After `logout()`, Principal still remains | Live Subject was read-only, could not remove entries | Do not treat that Subject as an active session; invalidate authorization/session |
| After `logout()`, secret still remains | `remove` does not mean zeroing; provider did not destroy/revoke | Destroy `Destroyable`, revoke remotely, and audit |
| Destroyed credential still in `getPrivateCredentials()` | Destroy does not auto-remove, or subject is read-only | Use compatible module cleanup; never treat presence as active |
| `SecurityException` reading private credentials | Runtime has SecurityManager/credential permissions | Review security policy; do not disable access controls |
| Password accidentally appears in logs | Logger prints callback or `Subject`/credential `toString` | Redact; log only status/correlation ID |
| `getPrivateCredentials(MyType.class).clear()` does nothing to subject | Typed accessor returns a copy, not a backed set | Module must remove from the raw backed set when mutable and permitted |
| Account still has privileges after logout | External cache/token not revoked | Inspect session registry, TTL, invalidation, audit |
| User borrows `Subject` and adds a role | Writable live Subject leaked | Encapsulation, immutable principal snapshot, auth boundaries |
| `LoginModule.abort()` fails to clean temporary token | Missing cleanup on overall login failure | Clean module state in `abort` and `finally` |

**Special note:** `Subject.setReadOnly()` locks *the sets* rather than deep-freezing `Principal`/credential objects, so an application-defined credential with setters can still change its contents after the subject is read-only. Use immutable principals, credentials with clear lifecycles, and avoid arbitrary setters on secrets.

## 11. Code Review Checklist for JAAS Credentials and Logout

- [ ] `LoginContext` is constructed with the right configuration name, handler, and system-managed `Configuration`/flags.
- [ ] `LoginModule.login()` only authenticates and keeps minimal state, never committing Principals before overall success.
- [ ] Raw passwords are never written to `String`, logs, Subject, or exception messages.
- [ ] `PasswordCallback.clearPassword()` is called; copies from `getPassword()` and from the handler are wiped in `finally`.
- [ ] Module does not loop retries internally on failure; the application enforces rate limiting/backoff/lockout.
- [ ] `commit()` adds **exactly the owned Principals/credentials**; partial commit failures are handled safely.
- [ ] `abort()` cleans temporary state if overall authentication fails; `logout()` cleans module-owned state.
- [ ] Private credentials have scope/expiry and `Destroyable`/provider cleanup; remove and destroy are not treated as the same operation.
- [ ] Raw `Subject`/credentials are never printed to loggers; credential `toString` never reveals material.
- [ ] If the Subject is read-only, you know `getPrincipals`/credential sets cannot be removed from, though credential destruction may still succeed.
- [ ] `setReadOnly()` is not called on the live Subject before verifying that the module supports read-only logout.
- [ ] Identity snapshots, if used, contain **no** private credentials; principal objects are immutable.
- [ ] `LoginException` leads to fail-closed behavior; a non-empty Subject is never treated as authenticated on error.
- [ ] Audit logs separate user-safe errors from internal diagnostics, exposing neither account existence nor secret-bearing causes.
- [ ] Integration tests cover success, wrong password, callback failure, read-only mutation, logout cleanup, abort, credential destroy, expired/revoked tokens, and race conditions.

## 12. Hands-On Exercises

**Exercise 1 — Distinguish remove from destroy.**  
Temporarily modify `ExampleModule.cleanup()` to only remove the token without calling `destroy()`, then inspect the `SessionCredential` reference held outside the subject. Why is `isDestroyed()` still `false`? Restore it so cleanup actually wipes the secret.

**Exercise 2 — Read-only before commit.**  
Try calling `live.setReadOnly()` before `LoginContext.login()`, and observe that commit cannot add the principal/token. Explain why **supplying the right password via callback does not equal a successful login** when commit fails. Do not let the module `return true` after the exception.

**Exercise 3 — Snapshot without secrets.**  
After login, create a principal-only snapshot. Attempt to modify the snapshot's set and verify `IllegalStateException`; verify `snapshot.getPrivateCredentials().isEmpty()` remains true. After logging out the live Subject, explain why the old snapshot must not be treated as an active session.

**Exercise 4 — Logout on a frozen Subject.**  
Call `frozen.setReadOnly()` before logout. Why can the module no longer call `.remove()` yet can still call `destroy()`? Try a credential that does not implement `Destroyable` and analyze the failure policy; never claim it was definitely wiped.

**Exercise 5 — Callback failure.**  
Have `CallbackHandler` throw `UnsupportedCallbackException` upon seeing `PasswordCallback`. Should the module return `false`, `true`, or throw `LoginException`? Why must state be cleaned in `abort` when overall login fails?

**Exercise 6 — Timeout and revocation policy.**  
For a real access token credential, explain why zeroing an array in the JVM does not revoke the token's access on the server. Add TTL, revocation events, and session registry invalidation.

**Exercise 7 — Multi-module ownership.**  
Imagine two modules both adding principals to one Subject. Why is `subject.getPrincipals().clear()` in module A's logout wrong? Fix it so A removes only the principals/credentials A itself added.

**Exercise 8 — Authorization boundary.**  
A request sends `"user": "admin"`; the application directly constructs `new UserId("admin")` and puts it into a Subject. Why is `getPrincipals` containing admin **not** enough to grant admin privileges? Explain how identity must come from a successful login and server-side policy.

## 13. Self-Check Questions

**1. Is `Subject.getPrivateCredentials()` an automatically encrypted token vault?**  
No. It is a set of objects governed by JAAS/runtime access controls, **not guaranteeing encryption, zeroization, or remote revocation**.

**2. Does `PasswordCallback.clearPassword()` erase every copy of a password?**  
No. It clears the callback's internal copy; the source array in the handler and the copy returned by `getPassword()` must be wiped separately, preferably in `finally`.

**3. What operations does `Subject.setReadOnly()` block?**  
It blocks adding/removing elements in the principal and public/private credential sets. It does **not** deep-freeze objects, does not prevent destroying credentials, and does not prove a user authenticated.

**4. Why can `logout()` succeed while a read-only Subject still retains principals?**  
Because the sets cannot be modified after `setReadOnly`; the module may only destroy secrets inside the credentials. **The presence of a principal after logout does not confirm the session is still valid.**

**5. When `LoginModule.login()` succeeds, may it add the principal immediately?**  
Normally it must wait for **overall login success** and `commit()`. If another module fails, `abort()` is invoked and temporary state must be cleaned up.

**6. Does `LoginException` only indicate a wrong password?**  
No. It also represents callback, configuration, provider, or lifecycle errors; `FailedLoginException` is a common subclass for invalid credentials.

**7. Why is the typed `getPrivateCredentials(MyType.class)` not the place to remove credentials from a subject?**  
Because the filtered accessor returns a **new set**; mutating that new set does not modify the Subject-backed set.

**8. When should you use a principal-only `Subject` snapshot?**  
When you want to provide verified identity in a **structurally unmodifiable** form to external code while still letting the `LoginContext`'s live Subject perform logout/cleanup per its lifecycle. The snapshot does not maintain session expiration by itself.

**9. Can `Destroyable.destroy()` replace remote revocation?**  
No. It only manages the local credential object's lifecycle; server/IdP privileges require dedicated revocation/expiry mechanisms.

**10. May an application continue processing a request after `login()` throws `LoginException`?**  
It may continue only along an appropriate **unauthenticated** branch and must never grant privileges based on an unconfirmed login state.

## 14. Official Documentation

- [Java SE 17 — `Subject`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/Subject.html): principal/public/private credentials, `setReadOnly`, `isReadOnly`, typed credential accessors, and destroy behavior when read-only.
- [Java SE 17 — `LoginContext`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/login/LoginContext.html): `login`, `getSubject`, `logout`, constructors, and configuration.
- [Java SE 17 — `LoginModule`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/spi/LoginModule.html): `initialize`, `login`, `commit`, `abort`, `logout`.
- [Java SE 17 — `LoginException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/login/LoginException.html): checked authentication/login exception.
- [Java SE 17 — `FailedLoginException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/login/FailedLoginException.html): authentication failure.
- [Java SE 17 — `PasswordCallback`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/callback/PasswordCallback.html): `setPassword`, `getPassword`, `clearPassword`.
- [Java SE 17 — `Destroyable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/Destroyable.html): destroyable secrets/credential lifecycle.
- [Java SE 17 — `Configuration`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/login/Configuration.html): configuring JAAS modules.
- [Oracle Java SE 17 — JAAS Authentication](https://docs.oracle.com/en/java/javase/17/security/jaas-authentication.html): architecture of Subject, LoginContext, CallbackHandler, and JAAS config.
- [Oracle Java SE 17 — JAAS LoginModule Developer's Guide](https://docs.oracle.com/en/java/javase/17/security/java-authentication-and-authorization-service-jaas-loginmodule-developers-guide1.html): two-phase login, `commit/abort/logout`, ownership, and credential destruction when Subject is read-only.

**Summary:** `Subject` holds **identities and credentials** but does not authenticate or protect secrets for the application on its own. `LoginModule` must manage `login → commit/abort → logout`, wipe temporary passwords, and destroy destroyable credentials. **`setReadOnly()` only locks set structure, does not lock or revoke secret permissions, and cannot replace `logout`.** Whenever `LoginException` occurs, **deny access**, clean up module-owned state, and keep logs free of secrets.
