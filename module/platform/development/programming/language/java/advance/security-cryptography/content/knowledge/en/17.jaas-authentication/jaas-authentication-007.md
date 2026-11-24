# 17.7 Subject.current, Subject.callAs, and How to Read Legacy Code Using doAs

In **JAAS (Java Authentication and Authorization Service)**, `javax.security.auth.Subject` represents the authenticated identity of a user or service: it groups **`Principal`**s and related credentials. Business logic may need to know **which `Subject` is bound to the current execution scope** without passing the object through every method. The modern APIs for that are:

- **`Subject.current()`:** reads the `Subject` bound to the current execution scope; may return `null`.
- **`Subject.callAs(subject, callable)`:** runs a `Callable<T>` with `subject` as the current `Subject` for the duration of the action, then restores the previous context.

Legacy Java code frequently uses **`Subject.doAs(...)`** and **`Subject.getSubject(AccessController.getContext())`**. They came from the **Security Manager / AccessControlContext (ACC)** architecture; as of **JDK 24**, the Security Manager is **permanently disabled** (JEP 486). Therefore, when reading or upgrading a JAAS system, distinguish **binding an identity to an execution scope**, **authenticating credentials**, and **authorizing business operations**: these three concerns are **not synonymous**.

**Version requirement:** `Subject.current` and `Subject.callAs` were introduced in **Java 18**, so programs using them **will not compile with `--release 17`**. Both full examples in this lesson are compiled with `javac --release 18` and tested on JDK 24. Java 17 still has the legacy APIs, but lacks the two new methods. In JDK 24–26, `doAs` remains in the API as *deprecated for removal*, while `getSubject(AccessControlContext)` throws `UnsupportedOperationException`.

## 1. Learning Outcomes

After this lesson, you will be able to:

1. Recognize a `Subject`, `Principal`s, and credential sets in JAAS; understand trusted `Subject` sources.
2. Accurately explain the **dynamic scope** of `callAs`, how `current` returns a `Subject` or `null`, and how nested scopes and exceptions restore context.
3. Write and run a Java 18+ program using `Subject.callAs`, including a `Callable` with checked exceptions.
4. Read `Subject.doAs(Subject, PrivilegedAction)` and `doAs(Subject, PrivilegedExceptionAction)`, distinguishing legacy exception wrappers.
5. Understand why `Subject.getSubject(AccessController.getContext())` breaks in JDK 24+ and why you should not try to re-enable the Security Manager.
6. Migrate legacy code to `current`/`callAs` and verify **asynchronous threads/thread pools** to avoid losing or leaking identities.
7. Maintain the boundary between **JAAS authentication** and **application authorization**: `callAs` neither verifies passwords nor grants file/database access.

## 2. The `Subject` Model: Identity, Not a "Login" Command

`javax.security.auth.Subject` is a container holding:

- **`Set<Principal>`:** one or more identities/identifiers, such as a username, Kerberos principal, certificate DN, or service principal.
- **Public credentials:** information shareable within an appropriate security model, such as a certificate.
- **Private credentials:** sensitive information such as tickets, tokens, or secret keys depending on the authentication technology; restrict reading and never log arbitrarily.

`Principal` is merely an interface with a `getName()` method. A `Subject` can hold **multiple Principals**; applications must not assume `subject.getPrincipals().iterator().next()` always represents the right user or access rights.

```text
                   JAAS LoginContext
                 login() succeeds
                         |
                         v
                Authenticated Subject
               /         |         \
           Principals  Public     Private
                       Credentials Credentials
                         |
               Subject.callAs(subject, action)
                         |
                Subject.current()
                         |
                   business code
                         |
              separate authorization
```

### 2.1. Where Does `Subject` Come From?

In a typical JAAS system, `LoginContext` uses `LoginModule`s and a `CallbackHandler` to perform **authentication**; after `login()` succeeds, `LoginContext.getSubject()` returns the `Subject` populated by the relevant modules.

An application can call `new Subject()` directly in tests, but **doing so does not prove a user logged in**, does not prove a certificate/Kerberos ticket is valid, and does not prove the `Principal`s inside are trustworthy. Creating a `Subject` containing `CN=Admin` does not make the caller an administrator in security terms.

### 2.2. A Principal Is Not Automatically a Role or Permission

A `Principal` may be an account name, DN, service identity, or another identifier. **There is no universal rule** that a principal named `"admin"` has administrative privileges. Actual permissions are evaluated via the application's or protocol's **authorization policy/IAM/ACL/resource ownership**.

As of JDK 24, JAAS authorization based on **Security Manager / policy-file permissions** no longer operates as before. Having a current subject **does not replace** the permission checks of the old model.

### 2.3. `setReadOnly` and Credential Protection

`Subject.setReadOnly()` prevents adding or removing `Principal`s and credentials directly from the `Subject`'s sets. It **does not freeze the internal contents of mutable credential objects**, does not destroy secrets, and does not solve missing authentication.

When a Subject does not need modification after login, an application may consider read-only mode according to the JAAS lifecycle; however, avoid calling it before a `LoginModule` needs to add or remove principals/credentials during `commit`/`logout`. Secret lifecycle management and `logout()` depend on the technology and login module.

## 3. What Does `Subject.current()` Read?

Signature:

```java
public static Subject current()
```

It returns the **`Subject` currently bound to the active execution scope**. On JDK 24+, outside any applicable `callAs`/`doAs`, the normal return value is **`null`**.

```text
Subject.current()  -> null                  [outside scope]

Subject.callAs(alice, action) {
    Subject.current() -> alice
}

Subject.current()  -> null                  [after action]
```

This is an illustrative diagram, **not directly runnable Java syntax**.

**Do not call `Subject.current()` and immediately invoke `getPrincipals()` without handling `null`.** If an API requires an identity, fail explicitly by design or accept an authenticated `Subject` as an explicit parameter.

### 3.1. Is Current Subject a Global Variable?

**No.** It does not mean every thread in the JVM shares a single `Subject`. `current()` reflects identity binding within the **current thread's execution scope**, and propagation to child tasks depends on the concurrency model.

- Do not store a `static Subject activeUser` field for all requests: one request could observe another's identity.
- Do not assume an `ExecutorService` task inherits the current subject from the submitting thread.
- Do not treat `Subject.current()` as proof of a verified identity, since code could call `callAs` with a `Subject` it constructed itself.

### 3.2. When There Is No Current Subject

`Subject.current() == null` can mean:

- The code is running outside any `callAs`/`doAs` scope.
- `callAs(null, action)` explicitly bound `null` temporarily.
- Work was handed off across a thread/executor without propagating context.
- A framework authenticated the user yet **does not use `Subject` as its context**; the user identity may live in a request object or another framework context.

Therefore do not equate "current subject is null" with "the system has not authenticated anyone." It reflects the state of **JAAS Subject binding**, not overall authentication status.

## 4. `Subject.callAs(Subject, Callable<T>)`: Dynamic Scope

API signature (since Java 18):

```java
public static <T> T callAs(Subject subject, Callable<T> action)
        throws CompletionException
```

`callAs` takes two arguments:

- `subject` is the `Subject` to bind during execution; **may be `null`**.
- `action` is a `java.util.concurrent.Callable<T>`; **cannot be `null`**.

It **invokes the action immediately within the scope**, returns its result, and **restores the previous Subject** after the action finishes. This is not an API that enqueues tasks or spawns new threads. Inside the action, `Subject.current()` returns `subject` under the modern model.

### 4.1. Nested Scopes: Alice → Bob → Alice

```text
outside: current=null
  callAs(Alice)
    current=Alice
    callAs(Bob)
      current=Bob
    done Bob
    current=Alice
  done Alice
outside: current=null
```

When nesting `callAs`, the inner scope **temporarily shadows** the outer scope; when it finishes, the outer scope is restored. There is no "`Subject.setCurrent`" because no such API **exists**.

### 4.2. Can You Bind `null`?

Yes. For example, inside Alice's scope, calling `Subject.callAs(null, () -> ...)` causes `Subject.current()` to return `null` **inside the inner action**, then restores Alice once the action completes.

This must not be used as a Java Security Manager "privilege drop." It is only **changing the current context**. Any code path requiring a specific principal must enforce its own authorization checks.

### 4.3. Exceptions from `Callable`

Unlike legacy `doAs`, `callAs` accepts `Callable<T>`, allowing `call()` to declare checked exceptions. By the API contract, if the action throws an exception, `callAs` throws **`CompletionException`**, with `getCause()` holding the original exception. This holds even if the exception is thrown deep inside the action: **the subject binding is still restored** per the scope.

Do not write `catch (Exception e) { return allowed; }` or ignore `CompletionException` as if the action succeeded. When surfacing errors to an API, inspect the cause and translate it into an appropriate business error without leaking credentials.

### 4.4. `callAs` Does Not Elevate Privileges

The method name might mislead readers into thinking it performs OS-level impersonation or "elevates privileges." It does not: **`callAs` only binds a `Subject` for code to read**. It does not change the Windows/Linux process user, does not grant OS permissions, does not mint tokens, does not open Kerberos connections, and **does not verify Principals**.

Libraries supporting JAAS Subject or GSS/Kerberos may consult this context to pick credentials, while authentication/authorization and runtime compatibility remain the application's/library's responsibility.

## 5. Why Does `Subject.doAs(...)` Appear in Legacy Code?

Before the new API model, a common JAAS pattern was:

```java
Subject.doAs(authenticatedSubject,
        (PrivilegedAction<String>) () -> service.call());
```

In older Java with a Security Manager, `doAs` integrated with **`AccessControlContext`/`SubjectDomainCombiner`** and policy permissions to associate the `Subject` with permissions for the action. In modern releases, the Security Manager has been removed from normal operation, so this usage no longer means **"temporarily run with Security Manager-based privileges."**

There are two main overloads:

| Legacy API | Action type | Typical exception behavior |
| --- | --- | --- |
| `Subject.doAs(Subject, PrivilegedAction<T>)` | `PrivilegedAction<T>.run()` declares no checked exceptions | Runtime exceptions propagate per the action's semantics |
| `Subject.doAs(Subject, PrivilegedExceptionAction<T>)` | `PrivilegedExceptionAction<T>.run()` may throw checked exceptions | `PrivilegedActionException` wraps checked exceptions |
| `Subject.doAsPrivileged(..., AccessControlContext)` | Variant accepting an ACC | **No replacement method preserves Security Manager permission behavior** |
| `Subject.getSubject(AccessControlContext)` | Reads the `Subject` tied to an ACC | On **JDK 24+ throws `UnsupportedOperationException`** |

When a lambda matches both `PrivilegedAction` and `PrivilegedExceptionAction`, Java can report an **ambiguous method call**. In legacy code, pay close attention to casts or target types:

```java
String name = Subject.doAs(s,
        (PrivilegedAction<String>) () -> "Alice");
```

This is an illustrative fragment where `s` is an already-created/approved `Subject`. When migrating to `callAs`, overload ambiguity disappears because `Callable<T>` is a single parameter form.

### 5.1. Was `doAs` Removed in JDK 24?

**Not yet.** Java SE 24–26 documentation still lists `doAs`, marked **deprecated for removal**. On JDK 24+, it still binds the `Subject` for the duration of the action; **there is no longer any Security Manager privilege elevation**. Still, new code should not depend on a deprecated API; move to `Subject.callAs`.

### 5.2. What Actually Breaks in JDK 24?

Legacy pattern:

```java
AccessControlContext context = AccessController.getContext();
Subject found = Subject.getSubject(context);
```

On JDK 24+, `Subject.getSubject(context)` **always throws `UnsupportedOperationException`**, even when called inside `Subject.doAs(...)`. This is an intentional API change as part of permanently disabling the Security Manager.

Replace it with:

```java
Subject found = Subject.current();
```

Do not change `Subject.getSubject(AccessController.getContext())` to `Subject.getSubject(null)` to try to bypass the error: this API is **no longer supported**, not merely rejecting a bad argument.

## 6. Java Version Milestones to Remember

| JDK | Actual status | Recommendation when reading/upgrading |
| --- | --- | --- |
| **Java 8–17** | Legacy `Subject.doAs`/`getSubject(ACC)` exist; **`current`/`callAs` do not exist yet** | For code required to run on Java 17, you cannot use the new API directly yet; isolate runtime compatibility or plan a JDK upgrade |
| **Java 18–22** | `Subject.current`/`Subject.callAs` added **in Java 18**; legacy APIs deprecated | Write new code with the new APIs; test according to your actual Security Manager setup |
| **Java 23** | `Subject` behavior depends on whether Security Manager is "allowed"; when disallowed, `getSubject(ACC)` throws UOE and current binding is scoped | Test with Security Manager disallowed; eliminate assumptions about ACC and thread inheritance |
| **Java 24–26** | Security Manager **permanently disabled** since JDK 24; `getSubject(ACC)` throws UOE; deprecated `doAs` still binds by scope | Use `current`/`callAs`; enforce authorization directly and handle async context and exception migration |

In JDK 23 there was a temporary compatibility option `-Djava.security.manager=allow` in certain cases to retain old behavior. **That is not a long-term upgrade solution and does not restore the Security Manager on JDK 24+.** Never instruct production to re-enable a disabled mechanism to fix JAAS errors.

### 6.1. How Do JEP 411 and JEP 486 Relate?

- **JEP 411 (Java 17):** marked the Security Manager **deprecated for removal**.
- **Java 18:** added `Subject.current` and `Subject.callAs` as replacements for ACC-dependent JAAS Subject methods.
- **Java 23:** adjusted behavior when the Security Manager is disallowed, helping detect code relying on `getSubject(ACC)` or child-thread context inheritance early.
- **JEP 486 (Java 24):** permanently disabled the Security Manager; authorization based on Security Manager/policy files is no longer supported.

**Key distinction:** "renaming `doAs` to `callAs`" is only **part** of migration. If legacy code relied on the Security Manager to block file/network/API access, you must **redesign the permission checks**, not just adjust syntax.

## 7. Runnable Java 18+ Example: `current`, Nested `callAs`, and `ExecutorService`

This example **creates mock `Subject`s in memory to learn the API**, without a real JAAS LoginModule or real passwords. It tests: empty scope → Alice → Bob → Alice, `callAs(null)`, restoration after exceptions, and the difference between a thread pool task **without propagated context** versus one **explicitly rebound**.

It uses `javax.security.auth.x500.X500Principal` as a built-in `Principal` type in the JDK instead of writing another principal class. The constructor `new Subject(true, ...)` creates a **read-only** object for demonstration purposes.

Save as **`SubjectScopeDemo.java`**:

```java
import java.io.IOException;
import java.util.Set;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import javax.security.auth.Subject;
import javax.security.auth.x500.X500Principal;

public class SubjectScopeDemo {
    static Subject user(String name) {
        return new Subject(true,
                Set.of(new X500Principal("CN=" + name)),
                Set.of(), Set.of());
    }

    public static void main(String[] args) throws Exception {
        Subject alice = user("Alice");
        Subject bob = user("Bob");

        System.out.println("outside null: "
                + (Subject.current() == null));

        String result = Subject.callAs(alice, () -> {
            boolean aliceVisible = Subject.current() == alice;
            boolean nestedBob = Subject.callAs(
                    bob, () -> Subject.current() == bob);
            boolean restoredAlice = Subject.current() == alice;
            boolean temporarilyNull = Subject.callAs(
                    null, () -> Subject.current() == null);
            boolean restoredAgain = Subject.current() == alice;
            return aliceVisible + "," + nestedBob + ","
                    + restoredAlice + "," + temporarilyNull
                    + "," + restoredAgain;
        });
        System.out.println("nested scope checks: " + result);
        System.out.println("after scope null: "
                + (Subject.current() == null));

        boolean checkedExceptionWrapped = false;
        try {
            Subject.callAs(alice, () -> {
                throw new IOException("test failure");
            });
        } catch (CompletionException expected) {
            checkedExceptionWrapped =
                    expected.getCause() instanceof IOException;
        }
        System.out.println("checked exception wrapped: "
                + checkedExceptionWrapped);
        System.out.println("after exception null: "
                + (Subject.current() == null));

        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            // Create the worker before submitting inside Alice's scope.
            pool.submit(() -> Subject.current()).get();

            Future<Boolean> implicit = Subject.callAs(
                    alice,
                    () -> pool.submit(() -> Subject.current() == null));

            Future<Boolean> explicit = Subject.callAs(alice, () -> {
                Subject captured = Subject.current();
                return pool.submit(() ->
                        Subject.callAs(captured,
                                () -> Subject.current() == alice));
            });

            System.out.println("pool not inherited: "
                    + implicit.get());
            System.out.println("explicit propagation works: "
                    + explicit.get());
        } finally {
            pool.shutdownNow();
        }
    }
}
```

**Minimum version: Java 18.** Can be compiled on JDK 24 with `--release 18` compatibility:

```bash
javac --release 18 -encoding UTF-8 SubjectScopeDemo.java
java SubjectScopeDemo
```

Verified stdout when run on JDK 24:

```text
outside null: true
nested scope checks: true,true,true,true,true
after scope null: true
checked exception wrapped: true
after exception null: true
pool not inherited: true
explicit propagation works: true
```

### 7.1. Detailed Explanation of the Output

**Before `callAs`:** the demo has not bound any `Subject`, so `Subject.current()==null` is `true`.

**Inside Alice:** `current()==alice` is `true`; using `==` here proves the **exact same object reference** is bound, not a business identity comparison.

**Inside Bob's scope:** `callAs(bob, ...)` temporarily replaces the current Subject. When Bob finishes, Alice is restored. This is a **nested scope structure**, not a permanent change to a global singleton.

**`callAs(null)`:** temporarily yields `current()==null`, then Alice is restored right after the callback.

**Outside the scope:** `current()==null` is `true` again; there is no need to call a nonexistent `setCurrent(null)` method.

**Checked exception:** `IOException` from `Callable.call` becomes the cause of `CompletionException`. After catching it, current is still restored to `null`.

**ExecutorService:** `pool.submit` does not automatically inherit the subject bound on the calling thread. The demo **creates the worker beforehand** to avoid confusion with any thread-creation mechanics; the task running in the worker checks `current()==null`.

**Explicit propagation:** capture the `Subject` from Alice's scope, pass the object reference to the worker, and **call `Subject.callAs(captured, ...)` inside the worker**; that task sees Alice within its own scope. Once the task finishes, the worker's previous context is restored.

### 7.2. What the Demo Does NOT Prove

- It does not prove Alice/Bob authenticated: both `Subject`s were manually created just to exercise the scoped API.
- It does not prove admin privileges or file/network permissions: **`callAs` does not enforce Security Manager permissions**.
- It does not prove every concurrency framework propagates context identically: executors, `CompletableFuture`, parallel streams, reactive streams, and structured concurrency have different lifecycles.
- It does not guarantee a worker could never see a `Subject` from another context if a custom wrapper/framework intervenes; test your application's **runtime and context propagation policy**.
- It does not prove sharing a mutable `Subject` with private credentials across threads is safe; protect credentials and lifetimes separately.

## 8. Runnable Example: Reading Legacy `doAs` and the `getSubject` Error on JDK 24+

Legacy code often uses both `doAs` overloads and retrieves `Subject` via `AccessController.getContext()`. This program shows that **`doAs` still binds the subject on JDK 24**, whereas **ACC-based reading no longer works**.

Save as **`LegacySubjectDemo.java`**:

```java
import java.io.IOException;
import java.security.AccessController;
import java.security.PrivilegedAction;
import java.security.PrivilegedActionException;
import java.security.PrivilegedExceptionAction;
import java.util.Set;
import javax.security.auth.Subject;
import javax.security.auth.x500.X500Principal;

@SuppressWarnings("removal")
public class LegacySubjectDemo {
    public static void main(String[] args) throws Exception {
        Subject alice = new Subject(
                true, Set.of(new X500Principal("CN=Alice")),
                Set.of(), Set.of());

        String result = Subject.doAs(alice,
                (PrivilegedAction<String>) () ->
                        Subject.current() == alice
                                ? "Alice" : "not Alice");
        System.out.println("legacy doAs still binds: " + result);

        boolean checkedWrapped = false;
        try {
            Subject.doAs(alice,
                    (PrivilegedExceptionAction<Void>) () -> {
                        throw new IOException("legacy failure");
                    });
        } catch (PrivilegedActionException expected) {
            checkedWrapped =
                    expected.getException() instanceof IOException;
        }
        System.out.println("legacy checked wrapped: " + checkedWrapped);

        boolean oldReaderUnavailable = false;
        try {
            Subject.getSubject(AccessController.getContext());
        } catch (UnsupportedOperationException expected) {
            oldReaderUnavailable = true;
        }
        System.out.println("getSubject unsupported on JDK 24+: "
                + oldReaderUnavailable);
    }
}
```

Compile with **Java 18+** because the example uses `Subject.current()`; run on **JDK 24+** to see `getSubject` no longer works:

```bash
javac --release 18 -encoding UTF-8 LegacySubjectDemo.java
java LegacySubjectDemo
```

Verified stdout on JDK 24:

```text
legacy doAs still binds: Alice
legacy checked wrapped: true
getSubject unsupported on JDK 24+: true
```

**`@SuppressWarnings("removal")` in the demo is only to keep the example focused, not a recommendation to hide warnings in production.** In real projects, migrate to the new APIs, audit legacy dependencies, and keep deprecation warnings visible in CI whenever possible.

### 8.1. Why Are the Two Exception Wrappers Different?

- **`doAs(PrivilegedExceptionAction)`:** checked exceptions from `run()` are wrapped in **`PrivilegedActionException`**; retrieve the real exception via `getException()` or `getCause()`.
- **`callAs(Callable)`:** exceptions from `call()` are wrapped in **`CompletionException`**; retrieve the cause via `getCause()`.
- **`doAs(PrivilegedAction)`:** `run()` itself declares no checked exceptions; distinguish unchecked business exceptions.
- **`Subject.getSubject(ACC)`:** throws **`UnsupportedOperationException`** on JDK 24+, rather than returning `null` for "no user."

Do not change a catch from `PrivilegedActionException` directly to `IOException` while ignoring the wrapper. That is a common bug when migrating code with checked exceptions.

## 9. Migrating Legacy Code to the New APIs

### 9.1. Replacement Map

| In legacy code | Modern replacement | What to verify |
| --- | --- | --- |
| `Subject.getSubject(AccessController.getContext())` | `Subject.current()` | May be `null`; no need and no reason to fetch ACC |
| `Subject.doAs(subject, PrivilegedAction<T>)` | `Subject.callAs(subject, Callable<T>)` | Remove `PrivilegedAction` cast; wrapper changes if action throws |
| `Subject.doAs(subject, PrivilegedExceptionAction<T>)` | `Subject.callAs(subject, Callable<T>)` | `PrivilegedActionException` → `CompletionException` |
| `Subject.doAsPrivileged(subject, action, acc)` | Bind context with `callAs` if only identity is needed | No replacement for Security Manager **privilege restriction/elevation** |
| `AccessController.doPrivileged(...)` | Redesign authorization if dependent on SM | Do not simply rename to restore permission enforcement |
| ACC carrying Subject passed to child threads | Pass authenticated `Subject` and re-bind inside the task | Do not expect `ExecutorService` to inherit automatically |

### 9.2. Migration Pattern for Reading the Current Identity

Before (legacy, tied to Security Manager/ACC):

```java
// LEGACY - illustrative; modern code should not use this.
Subject s = Subject.getSubject(AccessController.getContext());
if (s == null) {
    throw new SecurityException("Missing JAAS subject");
}
```

After (Java 18+):

```java
Subject s = Subject.current();
if (s == null) {
    throw new SecurityException("Missing JAAS subject");
}
```

In both fragments, a present `Subject` **does not guarantee authentication**: you must still ensure callers only create/bind `Subject` from an authenticated source and enforce authorization.

### 9.3. Migrating an Action Returning a Value

Before:

```java
String value = Subject.doAs(authenticatedSubject,
        (PrivilegedAction<String>) () -> service.readValue());
```

After:

```java
String value = Subject.callAs(authenticatedSubject,
        () -> service.readValue());
```

The `authenticatedSubject`/`service` variables are application dependencies, so this is a **fragment**, not a standalone program. When the action only needs to observe `Subject.current`, replacing the binding behavior is appropriate. If the legacy code relied on the Security Manager to allow file/URL/permission operations, address that boundary separately.

### 9.4. Safely Migrating Checked Exceptions

Legacy pattern:

```java
try {
    return Subject.doAs(authenticatedSubject,
            (PrivilegedExceptionAction<String>)
                    () -> service.loadFromDisk());
} catch (PrivilegedActionException e) {
    Throwable original = e.getException();
    // Classify original according to the application API contract.
    throw new IllegalStateException("Operation failed", original);
}
```

New pattern:

```java
try {
    return Subject.callAs(authenticatedSubject,
            () -> service.loadFromDisk());
} catch (CompletionException e) {
    Throwable original = e.getCause();
    // Do not swallow the exception; choose a safe business error/type.
    throw new IllegalStateException("Operation failed", original);
}
```

Both snippets are **fragments** that must sit inside a method with the matching return type and imports for `CompletionException`, `PrivilegedExceptionAction`, and `PrivilegedActionException`. For an `IOException` that needs to propagate unchanged to a higher-level API, consider:

```java
try {
    return Subject.callAs(authenticatedSubject,
            () -> service.loadFromDisk());
} catch (CompletionException e) {
    if (e.getCause() instanceof IOException io) {
        throw io;
    }
    throw e;
}
```

This fragment compiles only in a method declaring `throws IOException` (or handling the checked exception appropriately); it uses Java 18+ and existing service variables.

### 9.5. Do Not Migrate Simply with Search-and-Replace

A proper migration requires auditing:

1. Where is `Subject` obtained from `LoginContext.getSubject()` or another authenticated source?
2. Where is a fake `Subject` created via `new Subject()` and mistakenly treated as authenticated?
3. Do `doAs` call sites truly only need **identity binding**, or do they also depend on Security Manager policy?
4. Is any library/JAR calling `Subject.getSubject(AccessController.getContext())`?
5. Does any code assume `Subject` **automatically propagates to new threads, executors, or reactive callbacks**?
6. Are checked exceptions caught with the new wrapper, and are audit logs free of credentials?
7. Do operations requiring authentication fail closed when `Subject` is missing?
8. Have tests verified before/outside/after `callAs`, nested scopes, and concurrency?

## 10. How Do JAAS `LoginContext` and `Subject.callAs` Connect?

**Authentication** must finish before binding a `Subject` to handle an identity-sensitive request.

Conceptual integration example (`LoginContext` must be configured with real `LoginModule`s and `CallbackHandler`; this fragment does not run standalone):

```java
LoginContext login = new LoginContext("ApplicationLogin", callbackHandler);
try {
    login.login();
    Subject authenticated = login.getSubject();
    if (authenticated == null) {
        throw new SecurityException("JAAS login returned no Subject");
    }
    Subject.callAs(authenticated, () -> {
        service.processAuthenticatedRequest();
        return null;
    });
} finally {
    // Follow actual lifecycle: logout and clean up credentials.
    login.logout();
}
```

In a real system, handle `LoginException`, timeouts, retries, and callback secrets; also avoid calling `logout` when login did not succeed if the module does not support it. The fragment above illustrates the conceptual order, **not complete production code**.

### 10.1. `callAs` Does Not Call `login` Automatically

There is no implicit chaining:

```text
Subject.callAs(subject, action)
        !=
LoginContext.login() + authorization
```

You can call `callAs` with an empty or self-constructed `Subject`. Therefore, a service must never use `Subject.current()!=null` as the **sole proof** to permit withdrawing funds, downloading personal data, or invoking privileged APIs.

### 10.2. Reading Principals Purposefully

Illustrative code for an authenticated application reading an X.500 principal:

```java
Subject s = Subject.current();
if (s == null) {
    throw new SecurityException("No authenticated JAAS context");
}
Set<X500Principal> names =
        s.getPrincipals(X500Principal.class);
for (X500Principal name : names) {
    System.out.println(name.getName(X500Principal.RFC2253));
}
```

The snippet above only makes sense if the application's authentication technology actually populates X.500 principals; do not assume every `Subject` has an `X500Principal`. In production, do not log sensitive identities unless policy permits, and never print private credentials.

### 10.3. Logout and Scope Are Different

`callAs` always **restores the current subject binding** when the action completes; that **does not log out** of a KDC, revoke Kerberos tickets/tokens, or wipe secrets from the `Subject`.

`LoginContext.logout()` asks the `LoginModule`s to clean up according to their contract. You must manage **both lifecycles**: execution scope and credential/session lifetime.

## 11. Async, Executors, Virtual Threads, and Context Propagation

### 11.1. Why Does the Subject "Disappear" When Moving to a Worker?

Request-thread code:

```java
Subject.callAs(requestSubject, () -> {
    executor.submit(() -> service.handleRequest());
    return null;
});
```

This is a fragment. If `handleRequest` calls `Subject.current()` on an **executor worker thread**, it does **not by default** receive `requestSubject` from the submitting thread. The worker may have been created earlier and serve many different requests; expecting Java to automatically copy per-thread context leads to bugs.

This is especially important when modernizing older Java systems that relied on `AccessControlContext` or library-specific propagation.

### 11.2. Capture Explicitly and Bind Scoped Inside the Worker

A clearer pattern:

```java
Subject captured = Subject.current();
Future<Result> future = executor.submit(() ->
        Subject.callAs(captured, () -> service.compute()));
```

This is a fragment. To use it safely:

- Capture only a `Subject` that was **properly authenticated/authorized** for the current request.
- Bound task lifetimes; do not leave objects containing private credentials sitting in queues too long.
- `callAs` sets context inside the **worker** and restores it after the task ends; this prevents cross-request leaks in thread pools.
- `Future.get()`/`CompletableFuture` add their own exception wrappers (`ExecutionException`/`CompletionException`); handle **multiple layers of causes** rather than simply swapping one catch.
- If a task spawns further tasks, design a propagation policy across the **entire task tree**, or use a vetted context-propagation framework.

### 11.3. Why Not Roll a Global `ThreadLocal<Subject>`?

Legacy reasons aside, a custom `ThreadLocal` is prone to:

- Forgetting `remove()` in a pool → the next request sees the previous request's identity.
- Copying references to private credentials into unauthorized threads.
- Sharing one thread across multiple reactive/coroutine requests with broken semantics.
- Diverging from the JDK's `Subject.current()`, causing libraries to read one context while the app writes another.

Prefer **`Subject.callAs`** scoping if libraries already consume `Subject.current`; it ensures structured context restoration. If the app has a framework security context of its own, integrate via supported APIs instead of turning every identity into a Subject.

### 11.4. Structured Concurrency

Recent JDK documentation notes that the current Subject **can be inherited by child threads started and completed within a parent scope when using appropriate structured concurrency**. However:

- This is **not** automatic propagation for every `new Thread` or every `ExecutorService`.
- Structured concurrency has gone through **preview API** iterations across JDK versions; no preview code is used in the Java 18+ examples in this lesson.
- If a framework uses structured concurrency, verify the JDK version, scope boundaries, cancellation behavior, and specific inheritance rules.
- For thread pools and tasks without structured parent–child lifetimes, use **explicit passing** or a trusted context-propagation adapter.

## 12. Authorization in a World Without the Security Manager

### 12.1. Binding a Subject Alone Is Not Enough

On JDK 24+, `Subject.callAs` binds identity information for code to read, yet **there is no policy file / `SecurityManager.checkPermission` enforcing checks as in older releases**.

Conceptual flow:

```text
User authenticator  -> Subject trusted by application
Subject.callAs(...) -> Scope so service can read identity
Authorization        -> Check identity/roles/tenant/resource policy
Sensitive operation  -> Execute only if policy explicitly allows
Audit                -> Record safe metadata, not credentials
```

If code needs to read files or access a database, **OS ACLs, IAM credentials, DB privileges, and authorization logic** remain the real enforcement layers. Do not rely on calling `callAs` to automatically prevent an unauthorized user from reading data.

### 12.2. `Subject.current` Can Be Policy Input, Not Policy Itself

An application might have code like:

```java
Subject current = Subject.current();
if (current == null) {
    throw new SecurityException("Authentication required");
}
authorizationService.requireAccess(
        current, "orders:read", requestedOrderId);
```

This is a fragment: `authorizationService` and `requestedOrderId` must be supplied by the application. Crucially, `authorizationService` must:

1. Accept only a `Subject` from a **trusted authentication source** at a controlled boundary.
2. Treat principals as identity, without blindly trusting fake role names added by a caller.
3. Verify **permissions on the specific resource** (tenant, owner, scope, action).
4. Fail closed when context is insufficient, credentials have expired, or policy is unclear.
5. Never allow untrusted callers to choose an arbitrary `Subject` and abuse `callAs` to bypass permissions.

### 12.3. Replacing `doAsPrivileged`

If legacy code did:

```java
// LEGACY: previously used AccessControlContext/policy permissions.
Subject.doAsPrivileged(subject, action, context);
```

You **can** replace the "bind identity within a scope" aspect with `Subject.callAs(subject, callable)` if services only need the current subject. However, **there is no equivalent API replacement for Security Manager permission elevation/restriction**. File/network/API access rights must move to other boundaries (IAM/OS permissions/ACLs, service boundaries, explicit policies), backed by regression tests and threat modeling.

## 13. Common Errors and Symptoms When Upgrading the JDK

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| `cannot find symbol: Subject.current` with `javac --release 17` | API exists only since Java 18 | Raise target JDK or isolate runtime compatibility; do not assume it is Java 17 API |
| `UnsupportedOperationException` in `Subject.getSubject(...)` on JDK 24 | ACC-based reader has been disabled | Switch to `Subject.current()` and `callAs` scope |
| `doAs` warning: deprecated for removal | Legacy API tied to Security Manager concepts | Migrate to `callAs`; test exception handling |
| `reference to doAs is ambiguous` | Two overloads with similar functional interfaces | Cast `PrivilegedAction`/`PrivilegedExceptionAction` in legacy code; new code uses `Callable` |
| Catch `PrivilegedActionException` misses errors after migration | `callAs` throws `CompletionException` | Update catch handling and preserve root cause |
| `Subject.current()==null` inside executor | Subject is not inherited across thread pools | Capture trusted subject and bind inside task via `callAs` |
| Wrong user's Subject appears in a worker | Custom ThreadLocal/context leaked without cleanup | Use scoped binding; test isolation across requests |
| `Subject.current()!=null` yet API is accessed without permission | Treating Subject presence as authorization | Check policy/tenant/action/resource explicitly |
| Kerberos/GSS fails after JDK upgrade | Library uses ACC/`getSubject` or old thread inheritance | Upgrade dependencies; test JAAS login, delegation, and thread propagation |
| Using `-Djava.security.manager=allow` on JDK 24 to rescue code | Security Manager is permanently disabled | Fix code/APIs; do not use legacy flags as a workaround |
| Private credentials missing after `logout` | LoginModule cleaned up session or code held Subject too long | Manage lifecycle and async tasks properly |
| Multiple `Principal`s yet app picks first element | Sets have no universal order/semantics | Filter by exact Principal class and domain policy |
| Debug prints `Subject.toString()` | Risks exposing metadata/credentials depending on implementation | Log minimally; never print private credentials |
| Context held too long in queue | Captured Subject carries expired/revoked credentials | Enforce TTL, cancel tasks, re-verify at boundaries |

### 13.1. Diagnostic Checklist

When seeing "Subject not found" errors after a JDK upgrade:

1. Print the JDK version in the test environment (without logging login credentials): `java -version`.
2. Search source/classpath for `getSubject(AccessController.getContext())`.
3. Check for `Subject.doAs`/`doAsPrivileged`, or `AccessController.doPrivileged` relying on Security Manager permissions.
4. Confirm `LoginContext.login()` actually succeeded and populated the `Subject`.
5. Determine whether the callback runs in the **same scope/thread** as `callAs` or moved to an executor/async boundary.
6. Inspect the root cause of `CompletionException` and other wrappers.
7. Run tests before/outside/after scope, nested calls, exceptions, executors, and many concurrent users.
8. Verify authorization decisions with valid, invalid, null, expired, and forged `Subject`s.

## 14. Using `jdeprscan` to Detect Deprecated APIs

The JDK includes **`jdeprscan`** to scan classes/JARs for calls to deprecated APIs. For example:

```bash
jdeprscan --release 24 path/to/legacy-app.jar
```

This is an illustrative command; replace the JAR path with **your application's own artifact**. It can flag uses of `AccessController`/`Subject.getSubject` or other deprecated Java APIs. **Do not treat empty output as proof that migration is complete**, because not every dynamic/reflective call or Security Manager behavior is caught by bytecode scanning.

In local testing of `LegacySubjectDemo`, `jdeprscan --release 24` warned about using `AccessController` and `Subject.getSubject`. Combine scanning with source search and integration tests.

### 14.1. Migration Steps for Multi-Module Projects

1. **Inventory:** list every call to `doAs`, `doAsPrivileged`, `getSubject`, and `AccessController`; check whether dependencies/frameworks use JAAS/GSS.
2. **Version policy:** determine minimum JDK. If Java 17 is still required, do not put `Subject.callAs` directly in code compiled with `--release 17`; isolate a runtime adapter or plan a minimum-JDK bump.
3. **Authentication boundary:** verify `Subject` originates from JAAS login; reject self-created Subjects from user input.
4. **Context scope:** replace `doAs` with `callAs` when only binding is needed, and replace `getSubject(ACC)` with `current`.
5. **Authorization boundary:** move all logic previously relying on Security Manager to explicit policy/IAM/ACL checks.
6. **Concurrency:** audit thread pools, `CompletableFuture`, async RPC, reactive flows, and structured concurrency; propagate Subject explicitly without leaks.
7. **Exceptions:** update `PrivilegedActionException` to `CompletionException`, preserving causes accurately; test checked and unchecked failures.
8. **CI:** run `javac --release <minimum>`, `jdeprscan`, unit/integration tests on the target JDK, and negative security tests.
9. **Production rollout:** monitor safe logs for authentication/authorization failures, prepare rollback plans without weakening security policy, and upgrade dependencies before broad JDK rollout.

## 15. Security Notes on Credentials, Subject, and Access Control

### 15.1. `Subject.current()` Is Not Cryptographic Verification

Do not treat a service call as trusted solely because `Subject.current() != null`. That object could have been constructed manually with arbitrary `Principal`s. Authentication must be performed by a JAAS LoginModule or trusted boundary, and authorization must evaluate verified identity/roles/scopes.

### 15.2. Do Not Propagate Private Credentials Arbitrarily

A `Subject` can contain **Kerberos tickets**, tokens, keys, certificates, or other credentials. When capturing and passing a `Subject` to an executor:

- Propagate only when the task genuinely needs the current subject and is authorized.
- Never store the object in global static caches or unbounded queues without TTL.
- Never serialize `Subject` as a network payload merely to "preserve context."
- Never print `Subject` or credentials in debug logs.
- Clean up/invalidate credentials according to `LoginModule.logout` or technology policy.

### 15.3. Privileges Do Not Increase via Nesting

If a task lacks permission to perform an operation, `Subject.callAs(adminSubject, ...)` invoked by **untrusted code** must never be a way to escalate privileges. A proper authorization layer protects **the Subject source, binding capability, workload privileges, and resource policies**, not merely a principal name string.

### 15.4. Error Messages Must Not Leak Credentials

`CompletionException.getCause()` can occasionally contain service or authentication details. When returning errors to an API client, never echo raw exception contents from JAAS/LDAP/Kerberos. Log safely using correlation IDs, status, module, and error codes; restrict usernames, tokens, paths, and private credentials per policy.

## 16. Self-Check Exercises

**Q1.** Was `Subject.current()` added in Java 17 or Java 18?  
**Answer:** **Java 18**; `--release 17` will not compile code calling this method.

**Q2.** After `Subject.callAs(alice, action)` finishes, does Alice permanently remain the current subject?  
**Answer:** **No.** It is restored to the previous value before the call, typically `null` outside any scope.

**Q3.** When nesting `Subject.callAs(bob, action)` inside Alice's scope, what is `current()` inside Bob and after Bob?  
**Answer:** Inside Bob's action, `current()==bob`; after Bob's action and before Alice's scope ends, `current()==alice`.

**Q4.** Does `callAs` accept a `null` `Subject`?  
**Answer:** **Yes.** Inside the action `current()` will be `null`; the outer scope is restored afterward. However, `action` cannot be `null`.

**Q5.** A `Callable` throws `IOException`. Which exception type does the caller of `callAs` catch?  
**Answer:** **`CompletionException`**, retrieving the original `IOException` via `getCause()`.

**Q6.** Does `doAs(PrivilegedExceptionAction)` also throw `CompletionException` on older JDKs?  
**Answer:** **No.** Checked exceptions are wrapped in `PrivilegedActionException`, which is an important difference during migration.

**Q7.** On JDK 24, does `Subject.doAs(subject, action)` still exist in the API?  
**Answer:** **Yes**, though deprecated for removal; it binds the current subject by scope, **without Security Manager privilege elevation**.

**Q8.** On JDK 24, if no Subject is present, does `Subject.getSubject(AccessController.getContext())` return `null`?  
**Answer:** **No.** This API always throws `UnsupportedOperationException`, regardless of whether a Subject exists.

**Q9.** Does a thread pool task submitted inside `Subject.callAs(alice, ...)` automatically inherit Alice?  
**Answer:** **Never assume so.** Standard executor workers do not automatically carry the submitter's current subject; capture a trusted Subject and re-bind it during execution.

**Q10.** Is `Subject.callAs` enough to allow a user to access a bank account?  
**Answer:** **No.** Proper authentication and authorization by user/tenant/resource/action are required; context binding is only an input.

**Q11.** Does a `Subject` containing a principal named `"admin"` prove the admin role was granted?  
**Answer:** **No.** Principal names must come from an authenticated source and permissions from policy; calling `new Subject()` is not logging in.

**Q12.** When migrating `doAsPrivileged`, can you simply replace it with `callAs` and assume the Java Security Manager still protects files?  
**Answer:** **No.** The Security Manager is no longer supported as of JDK 24; redesign authorization/OS permissions/IAM.

**Q13.** Why should you test throwing an exception inside nested `callAs`?  
**Answer:** To verify that the context is **properly restored even when an action throws**, preventing identity leaks to other requests or tasks.

**Q14.** If `jdeprscan` reports no warnings, is the codebase guaranteed free of JAAS/Security Manager issues?  
**Answer:** **No.** You must still inspect dynamic/reflection calls, dependencies, permission semantics, concurrency, and integration tests.

## 17. Official References

- [Java SE 26 — Subject API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/security/auth/Subject.html): `current`, `callAs`, `doAs`, `getSubject`, version and exception semantics.
- [Oracle — Migrating from Subject.getSubject/Subject.doAs to Subject.current/Subject.callAs](https://docs.oracle.com/en/java/javase/25/security/migrating-from-deprecated-removal-subject-getsubject-subject-doas-methods-subject-current-subject-callas-methods.html): migration and post-JDK 24 changes.
- [Oracle — Java Authentication and Authorization Service Reference Guide](https://docs.oracle.com/en/java/javase/24/security/java-authentication-and-authorization-service-jaas-reference-guide.html): JAAS authentication, Subject/Principals, and modern authorization boundaries.
- [OpenJDK — JEP 486: Permanently Disable the Security Manager](https://openjdk.org/jeps/486): rationale for Java 24 behavior changes.
- [OpenJDK — JEP 411: Deprecate the Security Manager for Removal](https://openjdk.org/jeps/411): background starting in Java 17.
- [Oracle — JDK 23 Release Notes, Subject API changes](https://www.oracle.com/java/technologies/javase/23-relnote-issues.html): Security Manager states and how Subject propagates to child threads.
- [Java SE 26 — LoginContext](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/security/auth/login/LoginContext.html): obtaining a `Subject` from JAAS login.
- [Oracle — jdeprscan](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jdeprscan.html): bytecode scanning to detect deprecated APIs.

### Key Takeaways

**`Subject.current()` reads the identity bound to the scope; `Subject.callAs(subject, action)` binds it only for the duration of the action and restores it afterward.** Both APIs were added in **Java 18**. Legacy code using **`doAs`** needs migration because it is deprecated; in particular, **`getSubject(AccessController.getContext())` always throws `UnsupportedOperationException` starting in JDK 24**. Do not carry Security Manager permission assumptions into `callAs`: **authentication, context propagation, and authorization are three distinct responsibilities**, requiring explicit control over `Subject` origin, thread/task binding, and resource permissions.
