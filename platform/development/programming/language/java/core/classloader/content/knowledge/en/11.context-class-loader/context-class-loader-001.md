# What is Thread Context ClassLoader (TCCL)?

## 1. Concept and Purpose

**Thread Context ClassLoader (TCCL)** is a `ClassLoader` reference **attached to each `Thread` object**, allowing code running in that thread to ask: “In the current work context, which class loader should be used to dynamically look up classes and resources?”

Core API:

```java
ClassLoader loader =
        Thread.currentThread().getContextClassLoader();

Thread.currentThread().setContextClassLoader(loader);
```

TCCL is **not** a new kind of `ClassLoader`, nor is it a static field shared across all threads. It is **a readable/mutable reference per Thread**. The ClassLoader attached to TCCL still retains its own loading policy, such as parent-first or child-first depending on the implementation.

TCCL was created to solve a common scenario in large applications:

- **The core framework or library** is defined by a parent loader (or platform loader).
- **Plugins, JDBC drivers, service providers, and child application libraries** reside in a child loader.
- Under **parent-first delegation**, the parent loader cannot automatically see downward into all classes defined by the child loader.
- The framework needs to locate implementations belonging to **the calling application/thread context**, rather than searching only within the framework's own classpath.

TCCL creates a **context propagation channel from application-side code to the framework**, enabling the framework to select an appropriate loader when searching for plugins.

Conceptual example:

```text
Application / plugin code
   └── running on Thread T
       └── TCCL = PluginLoader
                  │
                  ▼
Framework code / ServiceLoader
   └── reads Thread.currentThread().getContextClassLoader()
       └── uses PluginLoader to find providers, resources
           └── PluginLoader can see the plugin's own classes
```

**Key point to remember:** TCCL **only takes effect when an API/framework actively uses it**. Java does not automatically replace the defining loader of every class, nor does it redirect every `Class.forName(...)` call to TCCL simply because the thread has a new TCCL.

## 2. Distinguishing Three Commonly Confused Loaders

At the same line of code, three `ClassLoader` sources can differ:

```java
ClassLoader defining =
        SomeClass.class.getClassLoader();

ClassLoader context =
        Thread.currentThread().getContextClassLoader();

ClassLoader system =
        ClassLoader.getSystemClassLoader();
```

This is an **API snippet**; `SomeClass` must be a concrete class in the program, not a built-in identifier in the JDK.

| Concept | Where does it come from? | Role |
|---|---|---|
| Defining loader of `SomeClass` | `SomeClass.class.getClassLoader()` | **Defined the runtime class** SomeClass |
| TCCL of the current thread | `Thread.currentThread().getContextClassLoader()` | The loader that **the current execution context wants the API to choose**, when supported by the API |
| System class loader | `ClassLoader.getSystemClassLoader()` | The application's system loader according to the runtime configuration |

Subtle points:

1. TCCL **does not have to equal** the defining loader of the executing class.
2. Changing TCCL **does not change** the defining loader of already-loaded classes; class identity still depends on the binary name and the defining loader.
3. TCCL can point to a custom loader, `URLClassLoader`, an application loader, or `null`. Under the `Thread` contract, a `null` value represents **the system class loader (or bootstrap if there is no system loader)** for the thread context. **Do not equate** a `null` value in TCCL with the meaning of `loader=null` in **`Class.forName(name, initialize, loader)`**, because that overload specifies **bootstrap** when `loader=null`.
4. The system class loader does not necessarily have the same class visibility scope as a plugin loader, especially in a container hosting multiple child applications.

For example, a library `engine.Framework` defined by a parent loader might call:

```java
// In framework code:
ClassLoader appLoader =
        Thread.currentThread().getContextClassLoader();

Class<?> implementation =
        Class.forName("my.plugin.Provider", false, appLoader);
```

This is a snippet; it requires declaring `throws ClassNotFoundException` or catching the exception. The framework **actively passes TCCL** into the three-argument overload. If it only calls `Class.forName("my.plugin.Provider")`, the single-argument overload will use the loader of the class **containing the call** (`engine.Framework`), and will not automatically use TCCL.

## 3. Why Is the Normal Delegation Model Not Enough?

With parent-first delegation, a child loader typically tries:

```text
findLoadedClass
     ↓ if not yet loaded
parent.loadClass
     ↓ if parent does not find it
findClass of the child loader itself
```

The parent-child relationship primarily operates in the direction of **child delegating upward to parent**. That is a useful design so that shared API classes maintain consistent identity. However, the parent **does not automatically delegate downward to every child**.

Example of a container running two applications:

```text
                  Bootstrap / Platform
                         │
                 SharedFrameworkLoader
                   /             \
          ApplicationLoader-A   ApplicationLoader-B
             plugin.A             plugin.B
```

If `SharedFrameworkLoader` has a class `FrameworkRegistry` and that class looks up `plugin.A` using its own loader, it may receive a `ClassNotFoundException`: the parent loader **cannot see classes that exist only in child loader A**.

If a request for application A is processed on a thread with TCCL = `ApplicationLoader-A`, `FrameworkRegistry` can read TCCL and ask loader A to locate the appropriate provider. For a request for B, TCCL can be `ApplicationLoader-B`.

This is the **context-dependent discovery** model. It is useful in Java SPI, service providers, JDBC, logging/provider ecosystems, application servers, test runners, and various plugin systems.

**However, TCCL does not guarantee isolation or security:** the selected loader still sees classes/resources according to its existing policies and permissions. Loading code from untrusted plugins requires additional controls over bytecode sources, modules, permissions, API boundaries, and loader lifecycle.

## 4. Reading and Setting TCCL on Thread

`Thread` provides two instance methods:

```java
public ClassLoader getContextClassLoader();
public void setContextClassLoader(ClassLoader cl);
```

Usage:

```java
Thread thread = Thread.currentThread();
ClassLoader before = thread.getContextClassLoader();

try {
    thread.setContextClassLoader(chosenLoader);
    // Invoke the framework/service discovery that needs this context's loader.
} finally {
    thread.setContextClassLoader(before);
}
```

This is a **code snippet pattern**: `chosenLoader` is supplied by the program. Using `try/finally` is critical because threads may be reused in a thread pool. If plugin A's TCCL is left on a worker and that worker later handles request B, request B could accidentally locate A's classes/resources.

### Scope Characteristics

- **Per-Thread:** changing the current thread's TCCL does not automatically change the TCCL of all other threads.
- **Readable/Writable:** components sharing a thread can both read and modify TCCL; it is not an immutable field.
- **Not automatically “scoped” on method exit:** Java does not automatically restore TCCL when a method returns. The code/framework that changed TCCL is responsible for restoring the proper context.
- **Inheritable:** a new thread typically receives its initial TCCL from its creating thread, according to `Thread` rules.
- **Not automatically propagated across all asynchronous mechanisms:** thread pools have pre-existing workers, so the TCCL at task submission time does not automatically become the TCCL of the worker executing that task.

### Notes on `null`

The `Thread.getContextClassLoader()` documentation allows returning `null`, meaning the context uses the system class loader (or bootstrap when there is no system loader). The `setContextClassLoader(null)` documentation follows the corresponding convention.

However, if **your code** retrieves TCCL and passes it directly to another API, you must check the contract of **the API receiving the loader parameter**. For example, `Class.forName(name, false, null)` uses the bootstrap loader. Therefore, a framework that wants a fallback to the system loader when TCCL is `null` may need to implement it explicitly:

```java
// Snippet: explicitly define a fallback matching the application requirements.
ClassLoader cl = Thread.currentThread().getContextClassLoader();
if (cl == null) {
    cl = ClassLoader.getSystemClassLoader();
}
Class<?> type = Class.forName("demo.Provider", false, cl);
```

Do not assume “`null` means the same thing everywhere” when combining multiple APIs.

## 5. Runnable Example 1: TCCL Is Inherited When Creating a Thread

Create the file `ThreadContextDemo.java` and run with Java 17+:

```java
public class ThreadContextDemo {
    public static void main(String[] args) throws InterruptedException {
        Thread parent = Thread.currentThread();
        ClassLoader original = parent.getContextClassLoader();

        ClassLoader marker = new ClassLoader(original) {
        };

        parent.setContextClassLoader(marker);
        System.out.println("main uses marker: "
                + (parent.getContextClassLoader() == marker));

        // Create the child thread while main's TCCL is marker.
        Thread child = new Thread(() -> {
            ClassLoader inherited =
                    Thread.currentThread().getContextClassLoader();
            System.out.println("child inherited marker: "
                    + (inherited == marker));
        }, "child");

        // Restore main's TCCL BEFORE starting the child thread.
        parent.setContextClassLoader(original);
        System.out.println("main restored: "
                + (parent.getContextClassLoader() == original));

        child.start();
        child.join();
    }
}
```

Compile and run:

```bash
javac ThreadContextDemo.java
java ThreadContextDemo
```

Stdout:

```text
main uses marker: true
main restored: true
child inherited marker: true
```

**Analysis:**

1. `marker` is a new `ClassLoader` object with `original` as its parent. No plugin classes are defined; the loader object serves only as a marker.
2. `main` changes its TCCL to `marker`.
3. When `new Thread(...)` is executed, the child thread **receives its initial TCCL value** from the creating thread under default inheritance rules. **The moment of Thread creation** matters; it does not wait until `start()` to capture TCCL.
4. `main` switches back to `original` before `child.start()`. The child thread still retains the `marker` reference it received earlier.
5. `child.join()` ensures a consistent stdout printing order in this example.

In production applications, if creating threads or running code can throw an exception, ensure TCCL is restored in a `finally` block rather than placing restoration after a normal sequence of statements.

### Does This Apply to Virtual Threads?

JDK 21+ introduced virtual threads as a standard feature. Thread-building APIs have options related to inheriting inheritable thread-local/context state; you should not conclude that all thread types, thread builders, executors, or frameworks copy TCCL in the exact same way regardless of configuration. This article chooses `new Thread(...)` to illustrate clear behavior and remain runnable on **Java 17**.

## 6. ServiceLoader Uses TCCL to Find Providers
When the service API is defined in the host but the provider exists only in the plugin loader, `ServiceLoader.load(Greeting.class)` can use **the current TCCL** to discover providers. This is the bridge between the parent–child model and the SPI mechanism. The following example is an illustrative snippet inside a method, assuming the host already has the `Greeting` interface, the plugin classpath already contains the corresponding `META-INF/services`, and the variable `pluginLoader`:

```java
Thread current = Thread.currentThread();
ClassLoader before = current.getContextClassLoader();
try {
    current.setContextClassLoader(pluginLoader);
    for (Greeting greeting : ServiceLoader.load(Greeting.class)) {
        System.out.println(greeting.message());
    }
} finally {
    current.setContextClassLoader(before);
}
```

The provider must implement **the exact runtime interface** used by the host; two copies of an interface with the same binary name defined by different loaders may be incompatible. Both the descriptor file and provider code must reside within the scope visible to `pluginLoader`. `ServiceLoader.load(Greeting.class, pluginLoader)` is the explicit alternative when changing TCCL is unnecessary. Provider discovery/instantiation can happen lazily during iteration, and a misconfigured provider can throw `ServiceConfigurationError`; do not treat every error as “no provider found”. The in-depth article at the end of the chapter explains the full project structure, compilation commands, output, caching, and JPMS.
## 7. ServiceLoader and TCCL: Not All Overloads Are the Same

`ServiceLoader` provides multiple factory methods with different search scopes:

| API | Search loader/context |
|---|---|
| `ServiceLoader.load(Service.class)` | **TCCL of the current thread** |
| `ServiceLoader.load(Service.class, loader)` | **Explicitly passed ClassLoader** |
| `ServiceLoader.load(ModuleLayer layer, Service.class)` | Searches providers in the module layer and parent layers per contract |
| `ServiceLoader.loadInstalled(Service.class)` | Providers installed via the platform loader and appropriate ancestors, not an arbitrary plugin loader |

TCCL cannot be generalized to all Java SPIs. Each library/provider discovery API must be checked individually: which API actually reads `Thread.currentThread().getContextClassLoader()`, which uses the caller's loader, and which uses a service module/layer configuration?

**Note on lazy loading:** `ServiceLoader.load(...)` creates a service loader, but providers may only be located/loaded/instantiated when an iterator, `findFirst()`, or stream consumes them. For an already-created `ServiceLoader`, changing TCCL later **does not mean** the old ServiceLoader object automatically switches to the new loader. Create a new service loader for the context, or use the overload taking an explicit loader if you want to avoid depending on TCCL.

If a service configuration is found but the provider class cannot be loaded or does not implement the exact API runtime class, `ServiceLoader` can throw **`ServiceConfigurationError`** instead of simply returning an empty collection. You must distinguish between “no provider” and “a declared but invalid provider”.

## 8. Relationship with ClassLoader.loadClass and Class.forName

Comparison table:

| Expression | How is the loader selected? | Does it automatically request initialization of the target class? |
|---|---|---|
| `Thread.currentThread().getContextClassLoader()` | Reads the thread's context | Does not load the target class |
| `loader.loadClass("p.X")` | Uses the `loader` on which the method is called | Does not automatically request running `X.<clinit>` |
| `Class.forName("p.X")` | Defining loader of the class **containing the call** | Yes, if X is not yet initialized |
| `Class.forName("p.X", false, loader)` | Explicitly passed loader | Does not request initialization |
| `Class.forName("p.X", true, loader)` | Explicitly passed loader | Yes, if X is not yet initialized |
| `ServiceLoader.load(S.class)` | Current TCCL | Provider loading/instantiation happens during service loader traversal |

This is a major distinction between **class-loading context** and **class initialization**. TCCL does not actively execute `<clinit>`; it can **select the loader** to be used when an API needs to locate a class. The subsequent operation determines loading/linking/initialization according to its own contract.

In particular, `Class.forName(name, boolean, loader)` with `loader=null` selects the **bootstrap loader**, whereas `Thread.getContextClassLoader()==null` carries the **system-or-bootstrap context** convention of the Thread API. Always check each API's contract rather than passing `null` straight through without inspection.

## 9. TCCL When Creating Threads and Submitting Tasks to an Executor
With a standard `new Thread(task)`, the child thread's initial TCCL is inherited **when the Thread object is created**, without waiting for `start()`. Changing the parent thread's TCCL after the child has been created does not automatically change the child's value (see the standalone example in Section 5).

Conversely, `executor.submit(task)` typically runs work on **pre-existing** workers; the API does not promise to copy the submitter's TCCL to the worker on each submission. If an API inside the task requires the plugin loader, pass the loader as a dependency or wrap the `Runnable`/`Callable` so the worker saves previous → sets desired → executes → restores in `finally`. The thread executing the task is where TCCL needs to be read and updated.

This also applies when a callback or `CompletableFuture` shifts execution to another thread. With virtual threads (Java 21+), consider the inheritance configuration of the thread builder/factory and do not confuse the virtual thread's TCCL with the carrier thread's. The articles “Propagation and Inheritance...” and “Thread Pools...” analyze context capture timing, pool examples, and runnable wrappers.
## 10. Loader Lifecycle and the Risk of Retaining Plugins Longer Than Expected
`Thread.contextClassLoader` is a **strong reference**. If a long-lived worker retains the TCCL of a plugin loader that has stopped operating, that loader remains reachable; the classes it defined are not yet eligible for unloading. This is a **reference retention path**, which can occur alongside caches, `ThreadLocal`, callbacks, or task queues.

```text
living host worker
  └── TCCL -> old plugin loader -> plugin classes / resources
```

You need to restore the previous TCCL in `finally`, stop/cancel the plugin's work, and clean up application-owned references. `URLClassLoader.close()` only closes associated resources; it does not force GC to unload classes. Do not blindly reset it to `null` or the system loader: always restore the exact previous value. The article “Memory Leaks...” explains the unloading process, inspecting GC roots, and the limitations of `System.gc()`.
## 11. Safety and Correctness When Using TCCL

### 11.1. TCCL Is a Lookup Selection, Not a Sandbox

`setContextClassLoader(pluginLoader)` does not make plugin classes inherently safer, does not block reflection, and does not grant module/package permissions. It only tells certain APIs **which loader to ask**.

Do not use TCCL as reliable proof that a class was loaded from a legitimate source. The returned provider class still needs to be verified:

- Does it implement the exact shared interface/API and have the expected runtime type?
- Was it loaded from the expected JAR/source?
- Did parent-first delegation pick another class with the same name first?
- Is it compatible with module access rules and the Java runtime version?
- Are constructor/provider initialization side effects controlled?

### 11.2. Duplicate API Names Across Loaders

Suppose `HostApi` is defined in the parent, but a child-first plugin loader defines another copy of `HostApi` with the same binary name. A provider implementing the child's copy of the API may be **not assignable** to the host's `HostApi.class`, even though both classes look identical by name on screen. `ServiceLoader` may report that the provider is not a subtype of the service, or a cast in code will fail.

The standard design keeps **shared communication APIs in the parent** and plugin implementations in the child; only use child-first overrides for plugin/private namespaces that genuinely require isolation.

### 11.3. Errors and How They Are Reported

| Symptom | Possible Cause | How to Check |
|---|---|---|
| `ServiceLoader` does not find the provider | TCCL does not point to the right plugin loader, missing `META-INF/services` or module `provides` | Print TCCL, inspect resources and module layers |
| `ClassNotFoundException` from `Class.forName(name)` | Single-argument API uses the caller's loader, not TCCL | Switch to the overload taking an explicit loader if appropriate |
| `ServiceConfigurationError` | Incorrect provider class/constructor/service config, or provider is not assignable | Check the cause, provider binary name, and class identity |
| `ClassCastException` | Host/plugin defined duplicate APIs with the same name via different loaders | Compare `Class<?>` and `getClassLoader()` on both sides |
| Wrong provider after a previous request | TCCL leaked on a thread pool or stale service loader/cache | Restore TCCL, clarify cache lifecycle |
| Plugin cannot be released on redeploy | Long-lived thread retains the plugin loader's TCCL or other references | Thread dumps, reference paths, close/unregister |
| `SecurityException` when getting/setting TCCL | Legacy environment with a SecurityManager checking permissions | Inspect policy/runtime; do not assume every JVM has an active manager |

Do not catch `ServiceConfigurationError` and silently return “no provider” while ignoring the error. When a provider is declared but cannot be instantiated/loaded, that is a **broken configuration**, distinct from no provider being supplied.

## 12. When to Use TCCL vs. When to Pass an Explicit ClassLoader?

| Design Scenario | Appropriate Choice |
|---|---|
| Generic framework calling an SPI in the current request/application context | TCCL if that is the contract designed by the framework/API |
| Library managing plugins itself and knowing the exact loader | Passing an explicit `ClassLoader` is usually clearer |
| Code with compile-time known types, no dynamic discovery needed | Use `SomeType.class` directly or new/type-safe API |
| Task via an executor with its own context | Wrapper that sets/restores TCCL on the worker or passing context explicitly |
| Need plugin isolation and unload/redeploy | Control loader lifecycle, scope TCCL, avoid strong references |
| JPMS application with named modules | Also look at `ModuleLayer` and `ServiceLoader.load(layer, service)` |
| Do not want to mutate per-Thread global state | Prefer overloads taking a loader directly if the API provides them |

TCCL is especially useful when a low-level API does not accept a loader parameter yet needs to discover implementations based on the application currently being processed. However, because it is **ambient** state on the thread, it makes behavior harder to predict if the context is modified elsewhere. Once the right loader is known and the API offers an explicit overload, passing the loader directly is typically easier to test and maintain.

## 13. Distinguishing TCCL from Related Concepts

### 13.1. TCCL Is Different from ThreadLocal

TCCL is a dedicated property of `Thread` with the `getContextClassLoader`/`setContextClassLoader` API. `ThreadLocal<T>` is a separate mechanism for arbitrary thread-local data. TCCL shares some inheritance behavior similar to inheritable thread state, but **setting TCCL should not be treated as identical to setting an arbitrary ThreadLocal**.

Consult the documentation for `Thread` and `InheritableThreadLocal` when designing context propagation across platform threads, virtual threads, or executors.

### 13.2. TCCL Is Different from the Caller's Defining Loader

TCCL serves to select class/resource lookup based on thread context. The caller's defining loader is fixed when the runtime class is defined. Changing TCCL does not change the result of `Host.class.getClassLoader()` or allow casting between two identically named runtime classes defined by different loaders.

### 13.3. TCCL Is Different from Module Layer

In JPMS, the module graph, readability, exports/opens, and service declarations partially govern the ability to discover/access providers. A single loader can define multiple modules. Merely setting TCCL does not guarantee that a service belonging to an independent module layer will be found in all cases. If your architecture creates custom module layers, consider the `ServiceLoader.load(layer, service)` overload and the module `uses`/`provides` contract.

### 13.4. TCCL Does Not Automatically Initialize Classes

Reading, assigning, or inheriting TCCL **does not run the provider's static initializer**. Only when an API actually loads, resolves, instantiates, or calls a static method does Java apply the loading/linking/initialization conditions according to the specification. Therefore, if you observe `<clinit>` running after `ServiceLoader.findFirst()`, the cause is **provider discovery and instantiation**, not the `setContextClassLoader` call itself.

## 14. Short Debugging Workflow When a Plugin Is Not Found
1. Identify **the thread actually executing** the provider lookup call (especially when using an executor).
2. Record the TCCL right at the lookup site, along with the defining loader of the service interface.
3. Verify whether the API uses **TCCL**, the caller-determined loader, an explicit loader parameter, or `ModuleLayer`. `Class.forName(String)` does not automatically read TCCL.
4. Check the provider descriptor `META-INF/services/...` or `provides`, JAR paths, shared type identity, and parent delegation policy.
5. Distinguish a non-existent provider from `ServiceConfigurationError`, `ClassNotFoundException`, module access errors, or failed casts.
6. Check `finally` blocks, stale caches/service loaders, and lingering references during redeploy.

Try `ServiceLoader.load(service, pluginLoader)` to distinguish a TCCL selection error from an actual visibility error of the plugin loader.
## 15. Self-Check Questions

1. **Is TCCL a new `ClassLoader` subclass created by the JVM for each thread?** No; it is a `ClassLoader` reference on `Thread`.
2. **Does `Thread.currentThread().setContextClassLoader(pluginLoader)` change the defining loader of `Host.class`?** No.
3. **A framework class defined by a parent loader needs to find a provider in a child loader; how does TCCL help?** The framework can actively retrieve the loader from the thread context to look up the provider in the child.
4. **How does `ServiceLoader.load(MyService.class)` choose its loader?** It uses the current thread's TCCL.
5. **Does `Class.forName("p.Provider")` automatically use a newly set TCCL?** No; it uses the caller's defining loader per the single-argument overload contract.
6. **Does `Class.forName("p.Provider", false, tccl)` automatically execute `Provider.<clinit>`?** It does not request it; `initialize=false`.
7. **Does a child thread inherit TCCL at the time of `new Thread` or `start`?** With default constructors, it is inherited when the thread is created, without waiting for `start`.
8. **Can you change TCCL on the main thread, submit a task to a thread pool, and be sure the worker uses the new TCCL?** No; the worker may already exist and have its own context.
9. **Why must TCCL be restored in `finally`?** To avoid context contamination across tasks and holding references that leak the plugin loader.
10. **If `getContextClassLoader() == null`, can you pass `null` directly into `Class.forName(name,false,loader)` and still be sure the system loader is used?** No; `forName` uses the bootstrap loader when the loader is null.
11. **If two plugin loaders define two API classes with the same binary name, what can happen with ServiceLoader/casting?** Different type identity, the provider may not be assignable, resulting in `ServiceConfigurationError` or `ClassCastException`.
12. **When the plugin loader is already known and you want to avoid ambient state, which API should be used?** The overload accepting an explicit loader if the API provides one, such as `ServiceLoader.load(service, pluginLoader)`.

## Official References

- [Java SE 21 — Thread.getContextClassLoader / setContextClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html): meaning of the context ClassLoader, inheritance from the creating thread, how to get/set it, and `null`.
- [Java SE 21 — ServiceLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ServiceLoader.html): the `load(service)` overload using TCCL, service-provider configuration, lazy discovery, and `ServiceConfigurationError`.
- [Java SE 21 — Class.forName](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html): distinguishing the caller's defining loader from the overload taking an explicit loader.
- [Java SE 21 — ClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): parent-first delegation, `loadClass`, `findClass`, and identity.
- [JLS — `12.2 Loading, `12.3 Linking, `12.4 Initialization](https://docs.oracle.com/javase/specs/jls/se21/html/jls-12.html): relationship between class loading, linking, and initialization.

**Summary:** TCCL is **the loader designated by the Thread context** so that an API/framework can locate the class or provider matching the application currently being processed, especially when the implementation resides in a child loader. It **does not change the defining loader**, **does not automatically alter the loading policy**, and **does not automatically initialize classes**. When using it, you must distinguish each API's contract, pass a loader explicitly when appropriate, and always restore TCCL after a scope to prevent wrong providers and ClassLoader leaks.
