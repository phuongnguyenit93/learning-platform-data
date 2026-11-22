# getContextClassLoader and setContextClassLoader in Java

## 1. Objectives and Real-World Problem

In Java, a class is typically loaded through the ClassLoader associated with the class requesting the load, or through a loader passed explicitly to an API. However, many frameworks/APIs need to load **application/plugin implementations** from library code that is defined by a higher-level loader. Using only the loader that defines the library may not see the classes/plugins provided by the application.

Java addresses part of this need with the **Thread Context ClassLoader (TCCL)** — a `ClassLoader` reference attached to **each `Thread` object**. Two core APIs:

~~~java
ClassLoader loader = Thread.currentThread().getContextClassLoader();
Thread.currentThread().setContextClassLoader(otherLoader);
~~~

- `getContextClassLoader()`: reads the context ClassLoader currently attached to the thread.
- `setContextClassLoader(ClassLoader)`: sets/replaces the thread's context ClassLoader.
- Both are **instance methods on `Thread`**, not static methods of `ClassLoader`. `Thread.currentThread()` simply selects the currently executing thread.
- TCCL is a **hint/context for APIs that actively use it**. Assigning TCCL **does not load a class on its own**, **does not change the defining loader** of an already defined class, and **does not automatically add a JAR to the JVM classpath**.

**Lesson completion objectives:** distinguish TCCL from the defining loader and parent delegation; read and change TCCL safely; know when an API actually uses TCCL; understand thread inheritance and thread pools; compile/run a Java 17+ example with `URLClassLoader` and restore the loader using `finally`.

## 2. How Does TCCL Differ from a Class's Defining ClassLoader?

### 2.1. Three Pieces of Information to Keep Separate

| Concept | Question It Answers | How to Observe |
|---|---|---|
| **Defining loader** of `SomeType` | Which loader actually defined the runtime class `SomeType`? | `SomeType.class.getClassLoader()` |
| **Parent** of a loader | Which loader does this loader delegate to under the delegation model? | `loader.getParent()` |
| **Thread context loader** | Which context loader is provided to code running in this thread? | `Thread.currentThread().getContextClassLoader()` |

An application may have:

~~~text
Application ClassLoader  (L_app)
  |  defines demo.app.Launcher
  |  defines interface demo.api.Plugin
  |
  +-- Child URLClassLoader (L_plugin)
         defines demo.plugin.Implementation

main thread:
  context ClassLoader = L_plugin  (set temporarily)

demo.app.Launcher.class.getClassLoader() = L_app (unchanged)
Implementation.class.getClassLoader()   = L_plugin
main.getContextClassLoader()            = L_plugin (within temporary scope)
~~~

All three comparisons can hold simultaneously without contradiction. **TCCL belongs to the thread, not to `Class<?>`**. Nor does the name "context loader" mean it is the **parent** loader of other loaders.

### 2.2. Why Is TCCL Needed?

For example, an SPI library running inside a class defined by the platform/application loader wants to find implementations loaded by a plugin loader. If the library uses only its own defining loader, it may not see the plugin. The library can **ask the calling thread** which context loader the application has set, and then use that loader to locate providers.

Control flow diagram:

~~~text
App calls SPI library
  -> library reads Thread.currentThread().getContextClassLoader()
  -> library uses the provided ClassLoader to look up providers
  -> application/plugin specifies the loader containing the corresponding provider

TCCL = context bridge for class discovery, not a command to change class identity.
~~~

An example with a well-defined contract is `ServiceLoader.load(ServiceType.class)`: this convenience overload uses the current thread's TCCL. However, **not every Java class-loading API reads TCCL**; verify the exact overload being called.

## 3. `Thread.getContextClassLoader()`

Signature:

~~~java
public ClassLoader getContextClassLoader()
~~~

The API returns the context ClassLoader of the **Thread object on which it is invoked**. In running code, we commonly use:

~~~java
Thread current = Thread.currentThread();
ClassLoader tccl = current.getContextClassLoader();
~~~

Key points to remember:

1. **It does not default to always equaling the application/system loader.** On the main application thread during a standard Java launch, the initial TCCL is typically the loader used to load the application. However, a framework, server, thread pool, embedded program, or other code may have already changed its value.
2. **It does not default to equaling the caller class's defining loader.** `Library.class.getClassLoader()` and `Thread.currentThread().getContextClassLoader()` can differ.
3. **A `null` value is valid.** According to the `Thread` API, `null` as TCCL indicates using the system class loader (or bootstrap if there is no system loader) for APIs following that contract. Do not call `tccl.loadClass(...)` by default when `tccl == null`.
4. **Reading TCCL does not load a class.** It is a reference retrieval operation, not `loadClass`.
5. **Legacy security policies may have an impact.** In an environment with a SecurityManager, `getContextClassLoader()` can throw `SecurityException` if the caller lacks the appropriate permission. SecurityManager is deprecated in Java 17; do not use it as a centerpiece for new applications.

Safe inspection example:

~~~java
ClassLoader tccl = Thread.currentThread().getContextClassLoader();
if (tccl == null) {
    System.out.println("Thread đang dùng context loader mặc định theo hợp đồng API");
} else {
    System.out.println("TCCL hiện tại là: " + tccl.getClass().getName());
}
~~~

The snippet above **is only illustrative code inside a method**, not a standalone file. Do not use `toString()` strings or class loader names to establish runtime identity; use reference comparison `==` when appropriate.

## 4. `Thread.setContextClassLoader(ClassLoader)`

Signature:

~~~java
public void setContextClassLoader(ClassLoader cl)
~~~

This method **sets** the context ClassLoader for the **Thread receiving the call**. Calling it on the current thread:

~~~java
Thread current = Thread.currentThread();
current.setContextClassLoader(pluginLoader);
~~~

There is no class/JAR check performed inside `setContextClassLoader`. Only when subsequent code calls an API **that uses TCCL**, such as `ServiceLoader.load(MyService.class)` or `Class.forName(name, false, current.getContextClassLoader())`, can the loader be used to find classes.

### 4.1. Can It Be Set on Another Thread?

From an API standpoint, `someThread.setContextClassLoader(cl)` operates on the `someThread` object itself; it does not have to be the current thread. However, changing the TCCL of a thread running elsewhere increases the risk of race conditions, context misinterpretation, and security bugs. The common approach is for **the thread to set its own context** when executing a task, or to configure a proper `ThreadFactory`/executor at the thread creation boundary.

### 4.2. What Does Passing `null` Mean?

`current.setContextClassLoader(null)` is valid under the Java `Thread` API; `null` represents the system loader (or bootstrap fallback) according to the context loader contract. However, if your own code does:

~~~java
Thread.currentThread().getContextClassLoader().loadClass("demo.Widget");
~~~

then a `null` TCCL causes the expression above to throw `NullPointerException`. Do not interpret `null` on your own as a loader object. For APIs that allow a `null` loader, read the exact contract; for example, `Class.forName(name, initialize, null)` instead means the **bootstrap loader**, unlike how `Thread` expresses the default context value.

### 4.3. Access Permissions

In a Java 17 environment with a SecurityManager, `setContextClassLoader` may check `RuntimePermission("setContextClassLoader")` and throw `SecurityException`. This does not mean modern Java always checks permissions via SecurityManager; do not treat this mechanism as a reliable sandbox for untrusted code.

### 4.4. Proper Set-and-Restore Pattern

~~~java
Thread thread = Thread.currentThread();
ClassLoader oldLoader = thread.getContextClassLoader();

try {
    thread.setContextClassLoader(pluginLoader);
    // Call APIs that actually use TCCL within this scope.
} finally {
    thread.setContextClassLoader(oldLoader);
}
~~~

Why **must there be a `finally` block**?

- If a `RuntimeException` occurs within the scope, the context loader must still be restored.
- Thread pools typically reuse a worker thread for multiple different requests/tasks. A leftover old loader can cause a subsequent task to see providers/JARs from the previous task.
- A long-lived thread holding a reference to a custom loader via TCCL can hinder garbage collection of an old plugin, deployment, or application when it needs to be unloaded.

If `setContextClassLoader(pluginLoader)` can throw an error **before entering the execution scope**, placing this call inside the `try` block as in the example is a safe approach for the restoration logic; when handling `SecurityException`, preserve the original cause. Do not "attempt recovery" by forcing every exception into an empty catch block.

## 5. When Is TCCL Actually Used?

### 5.1. An API That Uses TCCL: `ServiceLoader.load(service)`

According to the Java 17 Javadoc, the call:

~~~java
ServiceLoader<MyService> providers =
        ServiceLoader.load(MyService.class);
~~~

is equivalent in terms of loader selection to:

~~~java
ServiceLoader<MyService> providers = ServiceLoader.load(
        MyService.class,
        Thread.currentThread().getContextClassLoader());
~~~

This is the core reason for TCCL in SPI/plugin environments: the provider may be defined by another loader, while the **service interface** needs a type identity that both the library and the plugin agree on.

**The code above is an illustrative snippet requiring the `MyService` interface**; it is not a standalone program. Provider metadata via `META-INF/services/<binary-service-name>` is for the classpath, or via `provides ... with ...` in a named module (depending on how it is deployed/resolved).

The three overloads are not the same:

| API | Source/loader used to find providers |
|---|---|
| `ServiceLoader.load(S.class)` | **Context ClassLoader of the current thread** |
| `ServiceLoader.load(S.class, explicitLoader)` | **Explicitly passed loader** |
| `ServiceLoader.load(layer, S.class)` | **ModuleLayer and ancestor layers** per the JPMS contract |

In named modules, the caller must also comply with the `uses` requirement for the service when required by the API; the provider must be declared and the module resolved appropriately. Changing TCCL **does not automatically create a module layer, nor does it automatically add `requires`, `uses`, or `provides`**.

### 5.2. An API That Does Not Automatically Read TCCL: `Class.forName(String)`

~~~java
Class<?> type = Class.forName("demo.plugin.Widget");
~~~

According to the `Class` Javadoc, the single-argument overload uses **the defining loader of the calling class** (and triggers initialization if needed), **without automatically fetching TCCL**.

If you want to actively use the context loader:

~~~java
ClassLoader tccl = Thread.currentThread().getContextClassLoader();
Class<?> type = Class.forName("demo.plugin.Widget", false, tccl);
~~~

Here **you have passed TCCL into the overload that accepts a loader**. Note: if `tccl == null`, the `Class.forName(String, boolean, ClassLoader)` overload treats it as a request to load using the **bootstrap loader**; you should choose an appropriate null strategy for your application rather than assuming it always uses the system loader.

With the ClassLoader API:

~~~java
ClassLoader tccl = Thread.currentThread().getContextClassLoader();
if (tccl != null) {
    Class<?> type = tccl.loadClass("demo.plugin.Widget");
}
~~~

`loadClass` is invoked on the loader you chose; `ClassLoader.loadClass` does not automatically switch "to TCCL" if invoked on another loader. Do not confuse **an API that uses an explicitly passed loader** with **an API that reads the context loader by default**.

### 5.3. Resource Lookup Also Depends on the API

A framework sometimes uses:

~~~java
ClassLoader tccl = Thread.currentThread().getContextClassLoader();
java.net.URL resource = tccl == null ? null
        : tccl.getResource("config/plugin.properties");
~~~

This looks up the resource using the selected loader. Do not infer from `Thread.setContextClassLoader` that every call to `SomeClass.class.getResource(...)` or `ClassLoader.getSystemResource(...)` will change how it searches: each API has its own loader-selection and lookup rules.

## 6. Standalone Java 17+ Example: Plugin Loader and TCCL

This example verifies simultaneously:

1. The application loader **cannot** find the plugin class with `Class.forName(String)`.
2. The child `URLClassLoader` can find/define the plugin class.
3. `setContextClassLoader` changes TCCL, allowing code to **explicitly pass** TCCL to `Class.forName(name, false, loader)` to find the plugin.
4. A child thread created within the scope where the new TCCL is set **inherits** the context.
5. `finally` restores TCCL; the defining loader of the application class **does not change**.

### 6.1. Directory Structure

~~~text
demo/
  src/
    app/
      TcclDemo.java
    plugin/
      demo/
        plugin/
          Widget.java
  build/
    app/                  # runtime classpath of the launcher
    plugin/               # class files only for the child URLClassLoader
~~~

Run from the exact `demo` directory. Do not add `build/plugin` to the system classpath at runtime; otherwise, the loader-isolation demonstration will no longer be meaningful.

### 6.2. File `src/plugin/demo/plugin/Widget.java`

~~~java
package demo.plugin;

public final class Widget {
    public static String label() {
        return "plugin-ready";
    }
}
~~~

The plugin class is not compiled together with the app. In the example, the app only knows the binary name `demo.plugin.Widget` at runtime.

### 6.3. File `src/app/TcclDemo.java`

~~~java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public class TcclDemo {
    public static void main(String[] args) throws Exception {
        Thread current = Thread.currentThread();
        ClassLoader original = current.getContextClassLoader();
        ClassLoader defining = TcclDemo.class.getClassLoader();

        try (URLClassLoader pluginLoader = new URLClassLoader(
                new URL[] { Path.of("build/plugin").toUri().toURL() },
                defining)) {

            System.out.println("parentIsApp="
                    + (pluginLoader.getParent() == defining));

            try {
                Class.forName("demo.plugin.Widget");
                System.out.println("defaultLookupMissing=false");
            } catch (ClassNotFoundException expected) {
                System.out.println("defaultLookupMissing=true");
            }

            Class<?> pluginClass = Class.forName(
                    "demo.plugin.Widget", false, pluginLoader);
            System.out.println("pluginDefinedByChild="
                    + (pluginClass.getClassLoader() == pluginLoader));

            try {
                current.setContextClassLoader(pluginLoader);
                System.out.println("contextInstalled="
                        + (current.getContextClassLoader() == pluginLoader));

                Class<?> selected = Class.forName(
                        "demo.plugin.Widget",
                        false,
                        current.getContextClassLoader());
                System.out.println("contextLookupMatches="
                        + (selected == pluginClass));

                Thread child = new Thread(() -> System.out.println(
                        "childInherited="
                        + (Thread.currentThread().getContextClassLoader()
                                == pluginLoader)));
                child.start();
                child.join();
            } finally {
                current.setContextClassLoader(original);
            }

            System.out.println("restored="
                    + (current.getContextClassLoader() == original));
            System.out.println("definingLoaderUnchanged="
                    + (TcclDemo.class.getClassLoader() == defining));
        }
    }
}
~~~

Notes:

- `defining` is obtained from `TcclDemo.class` to act as the parent for the new loader. Parent-first delegation preserves the ability to find JDK and shared API classes.
- The plugin exists only in `build/plugin`, so the system loader cannot find `demo.plugin.Widget` when calling the single-argument overload from `TcclDemo`.
- `Class.forName("demo.plugin.Widget", false, pluginLoader)` uses the child loader directly and does not trigger class initialization.
- `Class.forName(..., false, current.getContextClassLoader())` **does not automatically detect TCCL**; the code passed the loader explicitly.
- The child thread is **created after the main thread's context has been set**. It inherits a reference to the same loader. If the child thread continues living after the parent restores TCCL, the reference held by the child thread **is not automatically restored along with it**.

### 6.4. Compiling and Running

On Linux/macOS, from the `demo` directory:

~~~sh
mkdir -p build/app build/plugin
javac --release 17 -d build/plugin src/plugin/demo/plugin/Widget.java
javac --release 17 -d build/app src/app/TcclDemo.java
java -cp build/app TcclDemo
~~~

On Windows PowerShell, create the output directories:

~~~powershell
New-Item -ItemType Directory -Force build/app, build/plugin | Out-Null
javac --release 17 -d build/plugin src/plugin/demo/plugin/Widget.java
javac --release 17 -d build/app src/app/TcclDemo.java
java -cp build/app TcclDemo
~~~

**Exact stdout**, compiled with `javac --release 17` and verified with the JDK:

~~~text
parentIsApp=true
defaultLookupMissing=true
pluginDefinedByChild=true
contextInstalled=true
contextLookupMatches=true
childInherited=true
restored=true
definingLoaderUnchanged=true
~~~

### 6.5. Output Analysis

| Output | What It Proves |
|---|---|
| `parentIsApp=true` | The child loader has `TcclDemo`'s defining loader as its parent |
| `defaultLookupMissing=true` | `Class.forName(String)` from the app **does not automatically use** TCCL/the plugin loader and cannot find the plugin in the app loader |
| `pluginDefinedByChild=true` | The plugin class was defined by the child loader |
| `contextInstalled=true` | The current thread's TCCL changed |
| `contextLookupMatches=true` | Reading TCCL and passing it to the loader-accepting overload finds the exact same `Class<?>` |
| `childInherited=true` | A new thread inherits the context loader of the thread that created it |
| `restored=true` | `finally` restored the original reference |
| `definingLoaderUnchanged=true` | Changing TCCL **did not change** the loader that defined `TcclDemo` |

**Common pitfall:** `contextLookupMatches` succeeding does not mean all class lookups now use the child loader. Only lookups that **select/pass the child loader** use it.

### 6.6. Three Verification Variants

**Variant A — Without setting TCCL:** omit `current.setContextClassLoader(pluginLoader);`. `Class.forName(..., current.getContextClassLoader())` will use the old loader; in the standard demo environment, it cannot find the plugin and throws `ClassNotFoundException`. This is an intentional error in the variant; it is not the output of the original version.

**Variant B — Passing the loader explicitly:** keep the original context unchanged, but call `Class.forName("demo.plugin.Widget", false, pluginLoader)`. The lookup **still succeeds** because the caller passes the right loader, showing that TCCL is only needed when your API/convention chooses to use it.

**Variant C — Creating the child thread before setting TCCL:** create `new Thread(...)` while TCCL is still `original`, then call `setContextClassLoader(pluginLoader)` and `start()` the child. Under `Thread`'s default inheritance rules, the child received the context at **creation time**, not when `start()` begins. The child's TCCL will not automatically jump to the parent's new value.

## 7. How Do New Threads and Executors Change Context?
A normal new thread inherits TCCL at **construction** time. Therefore, if a child thread is created while TCCL is temporarily set to a plugin loader, the child may still retain that reference after the parent has restored its own. A thread pool, on the other hand, reuses workers, so setting TCCL on the submitter does not guarantee that the task runs with that loader. When needed, wrap the task and perform get previous → set plugin loader → execute → restore in `finally` on the **worker**; or pass an explicit loader to an appropriate API. Do not close the plugin loader while tasks/providers are still using it. Two dedicated lessons on inheritance and thread pools provide standalone examples and `ThreadFactory` policies.
## 8. Limitations of Both APIs and Pitfalls to Avoid
`setContextClassLoader` does not create a security sandbox, does not add JARs to the classpath, does not change module readability/exports/opens, and does not make `Class.forName(String)` automatically select TCCL. Code using `getContextClassLoader()` must check for a `null` result before calling an instance method; the meaning of `null` when passed to `Class.forName(String, boolean, ClassLoader)` differs from `Thread`'s convention. If code reading/setting TCCL hits a `SecurityException` in a runtime with an appropriate permission-control mechanism, preserve the original cause and do not assume the context was changed successfully. Avoid caching a tenant/plugin TCCL in a long-lived singleton.
## 9. Comparison of Scenarios

| Expression/Scenario | Uses TCCL Automatically? | Conclusion |
|---|---|---|
| `Thread.currentThread().getContextClassLoader()` | This is a **TCCL read** operation | Returns the context loader or `null` |
| `Thread.currentThread().setContextClassLoader(loader)` | This is a **TCCL assignment** operation | Does not load a class automatically |
| `SomeType.class.getClassLoader()` | **No** | Returns the class's defining loader |
| `Class.forName("p.Type")` | **No** | Relies on the caller's defining loader per Javadoc |
| `Class.forName("p.Type", false, tccl)` | **Yes**, because **the caller passes** it | Uses the explicit loader without requiring initialization |
| `tccl.loadClass("p.Type")` | **Yes**, because it is invoked on that loader | If tccl is null, handle it beforehand |
| `ServiceLoader.load(Service.class)` | **Yes** | Convenience overload gets the current TCCL |
| `ServiceLoader.load(Service.class, loader)` | **Does not fetch automatically** | Uses the loader argument |
| `ServiceLoader.load(layer, Service.class)` | **Does not follow TCCL by default** | Looks up providers in the module layer per the API |
| `new Thread(task)` | **Inherits** by default | Receives context from the creating thread at construction |
| `executor.submit(task)` | **Does not guarantee inheriting** the submitter thread's context | The task may use a pre-created worker thread |

For APIs that use TCCL, if you have set the loader on the main thread but invoke the API on **another thread**, it will read the **other thread's** TCCL, not a process-wide "global context variable".

## 10. Diagnosing Common Errors

| Symptom | Causes Worth Checking | Resolution |
|---|---|---|
| `ServiceLoader` cannot find a provider | Current TCCL cannot see the provider config/class, or service metadata/module configuration is missing | Check the provider path, `META-INF/services`/`provides`, actual loader, and `uses` |
| `Class.forName("plugin.X")` fails despite setting TCCL | The single-argument overload **does not automatically read TCCL** | Use the overload taking an explicit loader if appropriate |
| Plugin A works, but Plugin B called later uses A | The thread pool forgot to restore context or a ServiceLoader cache uses an old loader | Wrap the task with `try/finally`, scope caches appropriately |
| Child thread does not see the new loader | The thread was **created before** the parent set TCCL, or the framework sets its own context | Check creation timing, `ThreadFactory`, and worker logic |
| `NullPointerException` at `getContextClassLoader().loadClass(...)` | TCCL can be null | Check for null and select a fallback loader per the contract |
| `ClassCastException` despite identical class names | Two defining loaders produced two different runtime types | Use shared API types from a unified loader |
| `IllegalAccessError` or module access error | Not just a loader error; may be due to runtime package/JPMS access | Check defining loaders, module readability, and `exports`/`opens` |
| Plugin does not unload after redeploy | Threads/caches still hold references to the old loader | Restore TCCL, stop tasks, clean up caches/resources |
| `SecurityException` when getting/setting TCCL | Legacy SecurityManager permissions or framework policy | Preserve the original cause and follow current permissions and APIs |

### Minimum Checklist Before Changing TCCL

1. Is TCCL truly needed, or does the API already accept an explicit loader?
2. Does the plugin loader contain the class/resource/provider to find, and does it have the right parent?
3. **Which threads** will the setting affect, and will any thread pool or child threads inherit it?
4. Have you captured the old context of **the running thread itself**?
5. Is it restored in `finally` even if the code throws an exception?
6. Are there any caches/static fields or long-lived workers retaining references to the loader/plugin?
7. Are there any access/module conditions that need to be handled independently?

## 11. Exercises and Review Questions

1. Compare `SomeType.class.getClassLoader()` and `Thread.currentThread().getContextClassLoader()`. When can they differ?
2. Does `Thread.setContextClassLoader` change the loader that defined `SomeType`?
3. Why does `Class.forName(String)` still fail to find `Widget` in the example even though the child loader has the bytecode?
4. Which statement in the example explicitly **passes TCCL** to a class-loading API?
5. Why is `ServiceLoader.load(MyService.class)` commonly used in SPI/plugin problems?
6. Does `ServiceLoader.load(MyService.class, explicitLoader)` automatically read TCCL?
7. If the parent thread changes TCCL **after** creating a child thread but **before** calling `child.start()`, which loader does the child thread retain by default?
8. Why does setting TCCL on the thread calling `executor.submit(...)` not guarantee that the task sees the new context?
9. What can go wrong if a plugin loader is left behind in a worker thread's TCCL after the task finishes?
10. Is `getContextClassLoader() == null` valid? Why must you not immediately call `.loadClass(...)` on that value?
11. Describe a scenario where passing a loader explicitly is safer and easier to understand than modifying TCCL.
12. How can a `ClassCastException` when communicating between a host and a plugin be related to defining loaders?
13. Explain why a `finally` block is still necessary when a class-loading API or provider may throw an exception.
14. To unload a plugin, does simply calling `URLClassLoader.close()` guarantee that all old classes will be GC'd immediately?
15. If a class-loading API does not use TCCL, what effect does merely changing TCCL have on that API?

**Completion criteria:** run the example yourself and explain all eight lines of output; distinguish between defining loader, parent, and TCCL; accurately state which APIs do and do not read the context; use `try/finally` to prevent context leakage in thread pools and understand the inheritance rules of `new Thread`.

## 12. Official References

- [Java SE 17 — `Thread.getContextClassLoader` and `Thread.setContextClassLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html): method declarations, inheritance mechanism and `null`, access permissions.
- [Java SE 17 — `ServiceLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html): `load(service)` overload using TCCL, explicit/layer overloads, caching/provider notes.
- [Java SE 17 — `Class.forName`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): loader selection behavior of the one-argument and three-argument overloads.
- [Java SE 17 — `ClassLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): defining loader, delegation, and `loadClass`.
- [Java SE 17 — `URLClassLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html): URL-based loader, closing resources, and usage lifecycle.

This lesson applies to Java 17+; the example was run with compiler `--release 17`. For newer JDK and framework versions, refer to the corresponding API contracts, especially around SecurityManager, module layers, and newer thread types.
