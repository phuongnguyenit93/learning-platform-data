# Switching the Context Class Loader in a Narrow Scope and Restoring with finally

## 1. Why Switch the Thread Context ClassLoader?

In Java, each thread can hold a reference to a **Thread Context ClassLoader (TCCL)**. You retrieve it with:

~~~java
ClassLoader current =
        Thread.currentThread().getContextClassLoader();
~~~

This is a **loader bound to the thread's context**, not necessarily the loader that defined the currently executing class. A library might be loaded by the host's loader yet still need to locate providers, classes, or resources belonging to a plugin. Instead of forcing the library to know about a specific plugin loader, a framework can set **the thread's TCCL** to the plugin loader for the duration of the library call.

Practical example: the single-argument overload of `ServiceLoader.load(MyService.class)` uses **the current thread's TCCL** to discover providers in the caller's context. Several other plugin/resource discovery frameworks and APIs also read the TCCL to select the appropriate loader.

However, the TCCL is **mutable thread state**, so switching it requires a clear scope and restoration mechanism:

> **Core rule:** Save the old loader, set the temporary loader, perform the work inside `try`, and **always restore the old loader in `finally`**.

If you forget to restore it, a subsequent operation on the **same thread** may mistakenly use the plugin loader, find the wrong resource/provider, or keep the old loader alive after the plugin has been unloaded.

## 2. Distinguishing the Three Types of “Current ClassLoader”

The following three ways of obtaining a loader answer different questions:

~~~java
ClassLoader defining =
        MyClass.class.getClassLoader();

ClassLoader system =
        ClassLoader.getSystemClassLoader();

ClassLoader context =
        Thread.currentThread().getContextClassLoader();
~~~

| Reference | Question it answers | Does it change on `setContextClassLoader`? |
|---|---|---|
| `MyClass.class.getClassLoader()` | Who **defined the runtime class** `MyClass`? | **No** |
| `ClassLoader.getSystemClassLoader()` | What is the system/application loader selected by the JVM? | **No** |
| `Thread.currentThread().getContextClassLoader()` | Which loader is the thread currently using as its lookup context? | **Yes**, for that thread |

Calling `thread.setContextClassLoader(pluginLoader)` **does not move classes** from parent to child, does not change the defining loader of already-loaded classes, and does not alter parent–child delegation relationships. It only changes the value of **a context field on the `Thread` object**.

If an API directly calls `SomeClass.class.getClassLoader()` instead of reading the TCCL, changing the TCCL may have **no effect** on that API. The TCCL is a **lookup convention used by certain APIs/frameworks**, not a switch that replaces all JVM class loading.

## 3. Minimum Safe Pattern: `try/finally`

A pattern worth knowing by heart:

~~~java
Thread thread = Thread.currentThread();
ClassLoader previous = thread.getContextClassLoader();

try {
    thread.setContextClassLoader(pluginLoader);
    // Call the library or framework that needs to look up resources from pluginLoader.
} finally {
    thread.setContextClassLoader(previous);
}
~~~

This is an **illustrative snippet**: `pluginLoader` must be created or passed in externally. Key points not to overlook:

1. **Obtain the right current thread.** A `setContextClassLoader` call changes the TCCL of the thread on which it is invoked; in this example, `Thread.currentThread()`.
2. **Preserve the exact old loader reference**, even when it is `null`. Do not assume “the old loader must be the system loader”.
3. **Limit the `try` block** to just the call that needs the plugin loader. Do not keep the plugin's TCCL set for an entire request if only a discovery step requires it.
4. **Use `finally` rather than placing the restore after `try`**. `finally` still executes in normal control flow whether the code inside `try` succeeds, returns, or throws an exception.
5. **Do not swallow the primary exception.** `finally` is for restoring state; exceptions from the main operation generally need to propagate to the caller or be handled according to an explicit policy.

The following code is **unsafe**:

~~~java
// Incorrect illustrative snippet.
Thread.currentThread().setContextClassLoader(pluginLoader);
service.perform();
Thread.currentThread().setContextClassLoader(previous);
~~~

If `service.perform()` throws an exception, the final restore line **does not run**. On a thread pool, a subsequent task can accidentally see the previous task's plugin loader.

Technical note: `setContextClassLoader` may be denied by permission controls in runtimes configured with such enforcement, such as `SecurityManager` on JDKs that support it. `finally` guarantees an **attempt to restore**, not that a blocked restore call will always succeed. Do not silently ignore restore failures.

## 4. Why Is This Pattern Important for Nested Calls and Exceptions?

Suppose operation A requires loader A, and while executing A it invokes operation B, which requires loader B.

~~~text
Initially:              TCCL = system
│
├─ Enter scope A:       TCCL = loader A
│  │
│  ├─ Enter scope B:    TCCL = loader B
│  └─ B's finally:      TCCL = loader A
│
└─ A's finally:         TCCL = system
~~~

Each scope saves **the loader it saw upon entry** and restores **that exact value**. Thus, nested scopes work naturally in a *stack* structure.

If B throws an exception, B's `finally` still restores A; then if the exception continues propagating out of scope A, A's `finally` restores system. There is no need to assume the previous loader is always the system loader.

If you change the TCCL multiple times within the same `try` block without clearly structuring the nesting levels, it is easy to restore the wrong loader. It is best for each temporary switch to be wrapped in **an independent `try/finally` block**.

## 5. Complete Java 17+ Example: Two Plugin Resources and TCCL Restoration

The following example demonstrates this using **resource lookup via TCCL**. This makes the context change clearly visible without requiring any framework dependencies.

We create two JARs containing only the same resource name:

~~~text
tccl-demo/
├── src/
│   └── ContextScopeDemo.java
└── resources/
    ├── alpha/
    │   └── demo/context/marker.txt
    └── beta/
        └── demo/context/marker.txt
~~~

Exact contents of the two UTF-8 files:

- `resources/alpha/demo/context/marker.txt`: `ALPHA`
- `resources/beta/demo/context/marker.txt`: `BETA`

These resources are **not** added to the application classpath. The host contains only the `ContextScopeDemo` class. They are loaded through two separate `URLClassLoader` instances.

### 5.1. Standalone Java Source File

Create **`src/ContextScopeDemo.java`**:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.Callable;

public final class ContextScopeDemo {
    private static final String RESOURCE = "demo/context/marker.txt";

    private ContextScopeDemo() {
    }

    private static String readMarker() throws IOException {
        ClassLoader loader =
                Thread.currentThread().getContextClassLoader();

        if (loader == null) {
            return "(no context loader)";
        }

        try (InputStream in = loader.getResourceAsStream(RESOURCE)) {
            if (in == null) {
                return "(missing)";
            }
            return new String(
                    in.readAllBytes(),
                    StandardCharsets.UTF_8).strip();
        }
    }

    private static <T> T withContext(
            ClassLoader temporary, Callable<T> action) throws Exception {
        Thread thread = Thread.currentThread();
        ClassLoader previous = thread.getContextClassLoader();

        try {
            thread.setContextClassLoader(temporary);
            return action.call();
        } finally {
            thread.setContextClassLoader(previous);
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Usage: ContextScopeDemo <alpha.jar> <beta.jar>");
        }

        Path alphaJar = Path.of(args[0]).toAbsolutePath().normalize();
        Path betaJar = Path.of(args[1]).toAbsolutePath().normalize();

        if (!Files.isRegularFile(alphaJar)
                || !Files.isRegularFile(betaJar)) {
            throw new IllegalArgumentException("Both JARs must exist");
        }

        URL alphaUrl = alphaJar.toUri().toURL();
        URL betaUrl = betaJar.toUri().toURL();

        Thread thread = Thread.currentThread();
        ClassLoader original = thread.getContextClassLoader();

        try (URLClassLoader alpha =
                     new URLClassLoader(new URL[] {alphaUrl}, original);
             URLClassLoader beta =
                     new URLClassLoader(new URL[] {betaUrl}, original)) {

            System.out.println("Before: " + readMarker());

            withContext(alpha, () -> {
                System.out.println("Inside alpha: " + readMarker());

                String nestedValue =
                        withContext(beta, ContextScopeDemo::readMarker);
                System.out.println("Inside beta: " + nestedValue);

                System.out.println("Back in alpha: " + readMarker());
                return null;
            });

            System.out.println("After alpha: " + readMarker());

            try {
                withContext(beta, () -> {
                    throw new IllegalStateException("boom");
                });
            } catch (IllegalStateException expected) {
                System.out.println("Caught: " + expected.getMessage());
            }

            System.out.println("After exception: " + readMarker());
            System.out.println("Original restored: "
                    + (thread.getContextClassLoader() == original));
        }
    }
}
~~~

**The core pattern** is the `withContext` method. It accepts a unit of work as a `Callable<T>`, saves the previous loader, sets the new loader, runs `action.call()`, and then restores the previous loader in `finally`.

This approach simplifies nested calls because each `withContext` call manages its own scope. It is not the only way to build a context scope; for a single operation, the direct `try/finally` block in section 3 is often easier to read.

### 5.2. Compiling, Packaging JARs, and Running

Requires **JDK 17 or later**. Run from the `tccl-demo/` directory with the structure described above.

**Bash (Linux/macOS or Git Bash):**

~~~bash
mkdir -p build/classes dist

javac -encoding UTF-8 \
  -d build/classes src/ContextScopeDemo.java

jar --create --file dist/alpha.jar -C resources/alpha .
jar --create --file dist/beta.jar -C resources/beta .

java -cp build/classes \
  ContextScopeDemo dist/alpha.jar dist/beta.jar
~~~

**Windows PowerShell:**

~~~powershell
New-Item -ItemType Directory -Force build/classes,dist | Out-Null

javac -encoding UTF-8 -d build/classes src/ContextScopeDemo.java

jar --create --file dist/alpha.jar -C resources/alpha .
jar --create --file dist/beta.jar -C resources/beta .

java -cp build/classes ContextScopeDemo dist/alpha.jar dist/beta.jar
~~~

The `jar` commands package the resource into each JAR at the path `demo/context/marker.txt`. You can verify with:

~~~bash
jar --list --file dist/alpha.jar
jar --list --file dist/beta.jar
~~~

Both JARs must contain `demo/context/marker.txt`. The program runs on the `build/classes` classpath and **does not** add either JAR to `-cp`: thus the host's default loader cannot find the plugin resource, whereas the `alpha` or `beta` TCCL can.

### 5.3. Stdout in a Standard Java 17 Environment

With the standard Java launcher (where the `main` thread's initial TCCL is the application/system loader) and no identically named resource on the application/JDK classpath:

~~~text
Before: (missing)
Inside alpha: ALPHA
Inside beta: BETA
Back in alpha: ALPHA
After alpha: (missing)
Caught: boom
After exception: (missing)
Original restored: true
~~~

**Explanation:**

1. **Before:** The initial system/context loader cannot see `marker.txt`, which exists only inside the plugin JARs → `(missing)`.
2. **Inside alpha:** `withContext(alpha, ...)` temporarily sets the TCCL to the alpha loader; reads the resource from `alpha.jar` → `ALPHA`.
3. **Inside beta:** The nested `withContext(beta, ...)` sets the beta loader → `BETA`. When the nested call finishes, beta's `finally` restores the TCCL to **alpha**, not system.
4. **Back in alpha:** The resource once again returns `ALPHA`, proving that the nested scope restored properly.
5. **After alpha:** Alpha's `finally` restores the TCCL to the original loader → the plugin resource is no longer visible from the host context.
6. **Caught:** An action using beta intentionally throws `IllegalStateException("boom")`. `finally` still restores the TCCL, and the caller subsequently catches the exception.
7. **After exception** and **Original restored:** The TCCL did not leak out of the temporary scope and is **the exact same initial loader object**; the comparison uses `==`, not names or `toString()`.

Results will differ if the runtime environment explicitly configures a custom initial TCCL or adds similar resources to the parent classpath. The program still demonstrates the restoration principle, though the lookups may be affected by parent-first resource delegation.

## 6. Why Save the Old Loader Instead of Forcing It Back to System?

A common mistake:

~~~java
// Snippet illustrating incorrect scope semantics.
try {
    Thread.currentThread().setContextClassLoader(pluginLoader);
    usePlugin();
} finally {
    Thread.currentThread().setContextClassLoader(
            ClassLoader.getSystemClassLoader());
}
~~~

If the original caller was running inside an application server, a request loader, plugin A's loader, or a custom context loader, this snippet **replaces the original context with the system loader** instead of restoring it. It can break the outer call in a nested scope.

The right way:

~~~java
// Illustrative snippet; pluginLoader/usePlugin are provided by the application.
Thread current = Thread.currentThread();
ClassLoader old = current.getContextClassLoader();

try {
    current.setContextClassLoader(pluginLoader);
    usePlugin();
} finally {
    current.setContextClassLoader(old);
}
~~~

The old TCCL may be `null`; if it was indeed `null`, `finally` must restore it to `null` as well, rather than substituting the system loader.

You should not determine the old loader via `getClass().getClassLoader()` inside a library, because the defining loader of the library class is often **different** from the context loader chosen by the caller.

## 7. When to Use TCCL with ServiceLoader?

Suppose the host has an interface `com.example.api.Plugin` defined by a parent loader, and a plugin JAR has the service descriptor `META-INF/services/com.example.api.Plugin`.

In a library using the overload:

~~~java
// Illustrative snippet; Plugin is already defined by the shared API.
ServiceLoader<Plugin> providers = ServiceLoader.load(Plugin.class);
~~~

`ServiceLoader.load(Plugin.class)` selects the loader via **the thread's TCCL**. Therefore, the host can invoke it within a temporary scope:

~~~java
// Illustrative snippet; Plugin and pluginLoader are provided externally.
Thread thread = Thread.currentThread();
ClassLoader old = thread.getContextClassLoader();

try {
    thread.setContextClassLoader(pluginLoader);
    for (Plugin provider : ServiceLoader.load(Plugin.class)) {
        // Use provider within the appropriate plugin loader scope.
    }
} finally {
    thread.setContextClassLoader(old);
}
~~~

A more direct approach, when the API allows passing the loader explicitly:

~~~java
// Illustrative snippet; no need to switch the TCCL.
ServiceLoader<Plugin> providers =
        ServiceLoader.load(Plugin.class, pluginLoader);
~~~

**Prefer passing the loader explicitly** if the API supports it, as this avoids mutating thread state. Switch the TCCL only when the underlying library/framework actively relies on it and provides no suitable way to pass a loader.

Either way, the provider class must link to **the same runtime interface** that the host passes to `ServiceLoader`. TCCL cannot fix a `ClassCastException` caused by the host and plugin independently defining two versions of an interface with the same name.

With **named modules**, `ServiceLoader` and module layers also involve `uses`, `provides ... with ...`, readability, and other provider-loading mechanisms; the example above only describes the common classpath/plugin case.

## 8. TCCL Scope Does Not Automatically Propagate to Asynchronous Work
`try/finally` manages only **the thread executing the scope**. If a method inside the scope calls `executor.submit(...)` and returns, the submitting thread's `finally` runs before the task completes, and the worker does not automatically receive the temporary TCCL. With `CompletableFuture`, callbacks may run on a different thread or on the thread that completes the stage, depending on the API.

If you want a task to use the plugin TCCL, pass the desired loader as a dependency and set/restore it on the worker itself inside a wrapper. When a new thread is **created** inside a temporary scope, it may inherit the plugin loader and retain a reference even after the parent scope has restored its own TCCL; bound the child thread's lifetime or set its context explicitly via a factory. Do not close the `URLClassLoader` while an async task still needs to load resources or classes from it. The article on thread creation/pools presents detailed examples.
## 9. Narrow Scope and Relationship to the URLClassLoader Lifecycle

Switching the TCCL **does not automatically close** the resource loader and **does not automatically unload** classes. If the plugin loader is a `URLClassLoader`:

~~~java
// Illustrative snippet (not a standalone program):
try (URLClassLoader pluginLoader =
             new URLClassLoader(urls, parentLoader)) {
    Thread thread = Thread.currentThread();
    ClassLoader previous = thread.getContextClassLoader();
    try {
        thread.setContextClassLoader(pluginLoader);
        usePlugin();
    } finally {
        thread.setContextClassLoader(previous);
    }
}
~~~

Intentional ordering:

1. Create/open the loader.
2. Temporarily switch the TCCL.
3. Invoke the code that requires the loader.
4. **Restore the TCCL in `finally`**.
5. Close the `URLClassLoader` once the work using the loader has finished.

`URLClassLoader.close()` closes the JAR/file sources managed by the loader, but it does not guarantee that already-loaded classes are immediately reclaimed. A thread pool, long-lived thread, plugin object, callback, or cache that still holds a reference to the loader can prevent class unloading.

If work submitted to another thread has not yet finished, **do not close the plugin loader prematurely**. The TCCL scope and the plugin lifecycle must be synchronized: close the loader only when no remaining tasks need its class/resource sources.

## 10. Helper Pattern and the Cost of Abstraction

Repetitive boilerplate can be encapsulated as in the example:

~~~java
// Illustrative method — requires importing java.util.concurrent.Callable.
static <T> T withContext(
        ClassLoader temporary, Callable<T> action) throws Exception {
    Thread thread = Thread.currentThread();
    ClassLoader original = thread.getContextClassLoader();
    try {
        thread.setContextClassLoader(temporary);
        return action.call();
    } finally {
        thread.setContextClassLoader(original);
    }
}
~~~

Advantages: call sites are less likely to forget to restore, nested scopes are managed properly, and the helper works with tasks that return a value.

However, the helper does not eliminate every responsibility:

- `Callable.call()` is allowed to throw `Exception`; callers need an appropriate handling policy.
- With restore errors (for example, denied by security configuration), an exception in `finally` can mask the original exception. If the system needs to ensure both errors are fully reported, dedicated cleanup/error-reporting logic must be designed.
- If the action returns a `CompletableFuture` and immediately returns, `finally` restores the TCCL **before** the asynchronous work finishes. Do not treat this synchronous helper as a scope covering an asynchronous future.
- The helper switches the TCCL only on **the thread that calls it**, and does not propagate to other executor threads.
- When no return value is needed, `Runnable` can be used while still handling exceptions according to the contract, though you should avoid creating multiple helpers that obscure which loader is selected.

An `AutoCloseable` context scope can also be designed, provided it captures the original thread accurately, restores in proper nested order, and prevents closing the scope from a different thread. For foundational lessons and Java 17, direct `try/finally` is usually the most transparent.

## 11. Common Pitfalls

| Symptom | Cause | Solution |
|---|---|---|
| After calling a plugin, a subsequent call sees the plugin's provider | Forgot to restore the TCCL | Wrap the call in `try/finally` |
| Nested scoped call reverts to system instead of loader A | Scope B restored to system instead of restoring `previous` | Save the TCCL at the start of **each** scope |
| After an exception, a thread pool continues using the plugin loader | Placed the restore after a line that can throw an exception | Move the restore into `finally` |
| The parent thread restored its TCCL, but the worker still sees the plugin | A new thread inherited the TCCL or the worker maintains its own state | Manage the TCCL inside the worker/thread factory |
| `executor.submit` cannot find the plugin resource even though the caller switched TCCL | The task runs on a different thread | Set the scope inside the executed task |
| `Class.forName(...)` still fails to find the plugin class | The API uses the caller's loader rather than reading TCCL | Use the overload taking an explicit `ClassLoader` or a TCCL-aware API |
| `ServiceLoader` does not find the provider | Wrong TCCL or missing `META-INF/services` metadata | Pass the loader explicitly and check the provider descriptor |
| After a plugin reload, the old loader is not unloaded | A thread/callback/cache holds a reference to the loader | Restore TCCL, clean up tasks/threads/caches, and manage lifecycle |
| `ClassCastException` between host and plugin | Shared interface/DTO independently defined by multiple loaders | Use a single API version defined by a shared loader |
| Changing TCCL does not change the current class's loader | TCCL is not the defining loader | Check `SomeClass.class.getClassLoader()` |
| Resource lookup gives different results across environments | Differences in parent delegation/classpath/module visibility | Verify the exact loader, URLs, modules, and access permissions |
| `finally` also throws an exception | Restore failed or cleanup is unsafe | Do not swallow errors; analyze both the primary error and the cleanup error |

## 12. TCCL and Modules/Security: The True Scope of the Mechanism

**TCCL does not create a sandbox.** Setting a plugin loader as the thread's context does not restrict the plugin code's operating-system privileges and does not provide process isolation. For untrusted plugins, true isolation models such as processes/containers and appropriate access policies are required.

**JPMS does not disappear.** A ClassLoader may locate bytecode, yet named modules remain subject to readability, `exports`, `opens`, and `ModuleLayer` rules. Changing the TCCL does not automatically grant access to encapsulated packages.

**The bootstrap loader and `null` values.** `Thread.getContextClassLoader()` can return `null`. This case is not necessarily an error; how a library interprets a null TCCL depends on that API. Do not automatically replace null with the system loader in restore logic.

**Independent class initialization.** Switching the TCCL does not run the `static initializer` of every class in the plugin; it only changes the loader chosen by a library if that library actively reads the TCCL. `loadClass`, `Class.forName`, and initialization each follow their own rules.

## 13. Checklist When Switching the Context Class Loader

1. **Does the API actually read the TCCL?** If it supports a ClassLoader parameter, prefer passing the parameter explicitly.
2. **What is the initial loader?** Call `Thread.currentThread().getContextClassLoader()` and preserve the exact object reference, including `null`.
3. **Is the scope narrow enough?** Wrap just the library/plugin call that needs the temporary loader.
4. **Is the restore inside `finally`?** Covering returns, exceptions, and nested scopes alike.
5. **Are other threads involved?** If using an executor or async execution, apply the scope on the executing thread.
6. **Are long-lived threads being created?** Consider inherited TCCL, ThreadFactory, and classloader leaks.
7. **Does the loader remain alive throughout the work?** Do not close `URLClassLoader` before tasks using it have finished.
8. **Does the shared API have the right identity?** TCCL does not resolve two separate versions of an interface.
9. **Have error paths been tested?** Intentionally throw an exception and verify the context loader is restored using `==`.
10. **Have nested calls been tested?** B restores A, and then A restores the caller.

## 14. Self-Check Questions

**Question 1.** Why do you need to save the old TCCL before calling `setContextClassLoader`?

**Answer:** To restore the caller's **exact original context**, which may be a custom loader or `null`; do not assume it is the system loader.

**Question 2.** If a method inside the scope throws an exception, is placing the restore after the call sufficient?

**Answer:** No. The restore line after the call can be skipped. It must be placed inside `finally`.

**Question 3.** With nested scopes A → B, which loader must be restored at the end of scope B?

**Answer:** **Loader A**, which is the TCCL saved when scope B began. When A ends, restore to the original caller's TCCL.

**Question 4.** Does a task in a thread pool automatically use the TCCL that the submitting thread just set?

**Answer:** There is no such general guarantee. Workers have their own TCCL; switch the TCCL inside the task if the underlying API needs that context.

**Question 5.** Why is `ServiceLoader.load(Service.class, pluginLoader)` usually preferable to switching the TCCL solely to load providers?

**Answer:** It selects the loader explicitly without mutating thread state and reduces the risk of leaking the TCCL. Use a scope only when the underlying API does not support passing a loader.

**Question 6.** Does properly restoring the TCCL in a scope guarantee that the plugin loader is unloaded immediately afterward?

**Answer:** No. Other threads, objects, caches, listeners, or resources still holding references to the loader can still prevent unloading.

## 15. Reference Documentation

- [Java SE 17: Thread.getContextClassLoader and setContextClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html): thread context loader behavior and modification permissions.
- [Java SE 17: ServiceLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html): overloads for loading services via TCCL or an explicit loader.
- [Java SE 17: ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): class/resource lookup, delegation, and class identity.
- [Java SE 17: URLClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html): loading resources from JARs and closing the loader.
- [Java SE 17: Callable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Callable.html): how to pass a task that returns a value and may throw a checked exception.

**Key takeaway:** The TCCL is **temporary thread context**, not a class's defining loader. When switching to a plugin loader is needed, **save old → set temporary → run inside try → restore old in finally**; nested scopes restore layer by layer, and executors/async tasks must be handled directly on the executing thread.
