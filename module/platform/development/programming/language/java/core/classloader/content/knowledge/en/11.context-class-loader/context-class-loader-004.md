# Choosing an explicit loader instead of implicitly relying on the thread

## 1. Why choose a ClassLoader?

In the JVM, a class is identified by its **binary name and defining class loader**. Two classes with the same name `com.example.Plugin` can be two different runtime types if they are defined by two different defining loaders. Therefore, the question “which class to load?” always has the additional part “load **via which loader**?”.

Java provides the **thread context class loader (TCCL)** via `Thread.currentThread().getContextClassLoader()`. The TCCL helps library/framework code locate implementations and resources according to the context of the running thread, especially when the implementation resides in a child loader that a library in a parent loader cannot see on its own. However, that value is **mutable**, is attached to the thread, and may differ when code runs inside an executor, callback, application server, or plugin runtime.

When it is clear which artifact/module/plugin a class, resource, or provider belongs to, you should consider **choosing an explicit loader** and passing it to the API:

```java
ClassLoader pluginLoader = /* loader provided by the plugin manager */;
Class<?> implementation =
        Class.forName("com.example.PluginImpl", false, pluginLoader);
```

This is **illustrative code**; `pluginLoader` needs to be replaced with an actually declared variable. `false` does not require initialization; the loader must be able to see the requested class. The idea is to pass the loader dependency into the component's input rather than inferring it from the current TCCL.

> The TCCL is not wrong. It is appropriate when a framework **intentionally defines lookup according to the thread's context**. The problem is using it as an unconscious default when there is already a loader that owns the exact definition needed.

## 2. How does the TCCL differ from the defining loader?

| Concept | Where does it come from? | Meaning |
|---|---|---|
| **Defining loader** | `SomeType.class.getClassLoader()` | The loader that defines the runtime class `SomeType`; once defined, its identity does not change |
| **TCCL** | `Thread.currentThread().getContextClassLoader()` | The loader attached to the thread context, which can be changed |
| **System loader** | `ClassLoader.getSystemClassLoader()` | The system loader according to the JVM configuration; it does not automatically contain every plugin |
| **Explicitly passed loader** | A `loader` variable provided by the caller/factory | Determines a dedicated lookup path for the request |
| **Bootstrap loader** | Typically represented by `null` in APIs intended for it | The JVM's foundational class-loading mechanism |

Changing the TCCL does not cause `SomeType.class.getClassLoader()` to change, does not redefine an existing class, and does not turn an object belonging to loader A into an object belonging to loader B.

Example:

```java
Thread thread = Thread.currentThread();
ClassLoader old = thread.getContextClassLoader();
ClassLoader custom = new ClassLoader(old) { };

try {
    thread.setContextClassLoader(custom);
    // The thread's TCCL is custom;
    // the class containing this code snippet still has the same defining loader as before.
} finally {
    thread.setContextClassLoader(old);
}
```

This is an illustrative snippet using Java 17; each thread holds its own TCCL. By default, a new thread's TCCL is inherited from the thread that created it unless explicitly set otherwise; it does not automatically change along with the parent once the parent has already created the child thread.

### Why does the TCCL exist?

In common **parent delegation**, a child loader can ask its parent to load a class; code defined by the parent does not automatically look down into all classes specific to the child loader. A foundational library may need to load a provider supplied by the application without having a direct reference to the application loader. The TCCL allows that code to obtain a loader according to the context.

This is the meaning of `ServiceLoader.load(Service.class)`: this convenience overload uses the TCCL. It does not mean that every reflection/class loading API automatically uses the TCCL.

## 3. Which API uses which loader?

| API | Source determining the lookup |
|---|---|
| `Class.forName("com.example.Foo")` | **Defining loader of the calling class**, while also requesting initialization |
| `Class.forName("com.example.Foo", false, chosen)` | The explicitly passed `chosen` loader |
| `chosen.loadClass("com.example.Foo")` | The `chosen` loader and its delegation strategy |
| `Foo.class` | Class literal linked by the compiler/JVM according to the current class context |
| `Foo.class.getClassLoader()` | Only **reads the defining loader** of the runtime type `Foo` |
| `ServiceLoader.load(FooService.class)` | **TCCL** of the current thread |
| `ServiceLoader.load(FooService.class, chosen)` | The `chosen` loader used to locate providers |
| `ServiceLoader.load(layer, FooService.class)` | The specified `ModuleLayer` (and parent layers per the API) |
| `chosen.getResourceAsStream("config/a.yml")` | Resource lookup through the `chosen` loader |

**Two common points of confusion:**

1. `Class.forName(String)` does not implicitly read `Thread.currentThread().getContextClassLoader()`. According to Java SE 17, the single-parameter overload is equivalent to `Class.forName(name, true, currentLoader)`, where `currentLoader` is the defining loader of the **calling class**.
2. `ServiceLoader.load(Class<S>)` **does use the TCCL**; it is equivalent to `ServiceLoader.load(service, Thread.currentThread().getContextClassLoader())`.

Therefore, simply seeing a method named `load` or `forName` is not enough; you must check the actual overload and the API contract.

### Do not assume the meaning of null

`null` has **different** semantics across APIs:

- `Class.forName(name, false, null)`: searches via the **bootstrap loader**.
- `ClassLoader.getParent() == null`: in common class loader delegation, the parent API represents the bootstrap loader.
- `SomeClass.class.getClassLoader() == null`: for an ordinary class such as `java.lang.String`, the defining loader is the bootstrap loader on a typical JDK; primitive/void/array types have their own rules.
- `Thread.getContextClassLoader() == null`: the `Thread` documentation specifies that `null` indicates the **system loader**, or the bootstrap loader if there is no system loader.
- `ServiceLoader.load(service, null)`: the `ServiceLoader` documentation specifies using the **system loader**, or the bootstrap loader if the system loader is unavailable.

Do not pass a nullable loader across multiple APIs assuming all of them use the bootstrap loader. If an anchor class is defined by bootstrap and `getClassLoader()` returns `null`, you must review the specific contract of the API receiving that value.

## 4. What errors occur when using the TCCL implicitly?

Suppose a library has a function:

```java
static Class<?> locate(String name)
        throws ClassNotFoundException {
    ClassLoader loader =
            Thread.currentThread().getContextClassLoader();
    return Class.forName(name, false, loader);
}
```

This is an illustrative snippet that must be placed inside a class. With the same `name` input, the result can still differ:

- The main thread usually has the application loader and finds the app's class.
- A container-managed thread may carry a different loader; the class is not found.
- A pre-created executor worker thread may hold a TCCL unrelated to the current request.
- A plugin changes the TCCL before calling the library, causing the same binary name to resolve according to the plugin.
- A unit test runner or agent may create threads with a TCCL different from the production environment.
- If the TCCL is `null` and the code passes it directly to `Class.forName(name,false,null)`, the lookup is restricted by that API's bootstrap rules.

Relying on the TCCL is a **hidden dependency tied to thread state**. The logic becomes difficult to reproduce and test when execution moves to another thread.

### The TCCL does not fix type identity on its own

If loaders A and B both define `api.Message`, the results of `A.loadClass("api.Message")` and `B.loadClass("api.Message")` can be two different `Class<?>` objects. Those two runtime types are not automatically compatible just because they share the same binary name.

Setting the TCCL to A or B can affect lookup, but it does not turn the two classes into one. For a host/plugin sharing interfaces or DTOs, you should define the **shared API** in a common loader and let plugins resolve to the same runtime class identity.

## 5. Rules for choosing an explicit loader by owner

### 5.1. Class belongs to the same library as the API anchor

If the library contains the class `com.example.lib.Helper`, you can choose the loader of a known class belonging to the library:

```java
ClassLoader libraryLoader = LibraryAnchor.class.getClassLoader();
Class<?> helper = Class.forName(
        "com.example.lib.Helper", false, libraryLoader);
```

This is illustrative code: `LibraryAnchor` and `Helper` need to exist. This approach reduces dependence on the TCCL of a worker or HTTP request.

### 5.2. Implementation loaded by a plugin manager

If the implementation belongs to a plugin, the **loader managed by the plugin manager** is the clear choice:

```java
public final class PluginFactory {
    private final ClassLoader implementationLoader;

    public PluginFactory(ClassLoader implementationLoader) {
        this.implementationLoader =
                java.util.Objects.requireNonNull(implementationLoader);
    }

    public Class<?> loadType(String binaryName)
            throws ClassNotFoundException {
        return Class.forName(binaryName, false, implementationLoader);
    }
}
```

This class can be saved in `PluginFactory.java`. The constructor explicitly expresses the dependency. Tests can pass a test loader; when the plugin closes, the registry/factory can be released according to its lifecycle.

If the plugin implementation uses a shared interface, configure parent/delegation so that the implementation and the host see the same runtime class of the interface. An explicit loader only ensures that the lookup path **is well-defined**; it does not bypass Java access checks, JPMS, or loading constraints.

### 5.3. Resource bundled with a library

If the resource is owned by the same artifact as `LibraryAnchor`, you can use:

```java
try (java.io.InputStream in =
             LibraryAnchor.class.getResourceAsStream(
                     "/config/defaults.properties")) {
    if (in == null) {
        throw new java.io.FileNotFoundException("Resource missing");
    }
    // Read configuration data.
}
```

This snippet must be placed inside a method declaring `throws IOException` or handling the exception. If the resource is owned by a plugin, use the exact `pluginLoader.getResourceAsStream(...)` instead of the host's anchor. With named modules, resource encapsulation and package opening rules still apply.

### 5.4. Service provider in the module system

If the provider lives in a `ModuleLayer` created and managed by the application, you can use:

```java
java.util.ServiceLoader<MyService> providers =
        java.util.ServiceLoader.load(layer, MyService.class);
```

This illustrative snippet requires the `layer` variable and the `MyService` interface. In named modules, you need to configure `uses` and `provides` along with the appropriate module relationships; an explicit loader does not bypass JPMS rules.

## 6. Standalone Java 17: TCCL is changed, yet explicit lookup remains correct

Create the file `ExplicitLoaderDemo.java`:

```java
public class ExplicitLoaderDemo {
    public static void main(String[] args)
            throws ClassNotFoundException {

        Thread thread = Thread.currentThread();
        ClassLoader previous = thread.getContextClassLoader();
        ClassLoader app = ExplicitLoaderDemo.class.getClassLoader();
        ClassLoader isolated = new ClassLoader(null) { };

        try {
            thread.setContextClassLoader(isolated);
            System.out.println("TCCL is isolated: "
                    + (thread.getContextClassLoader() == isolated));

            boolean notFound = false;
            try {
                Class.forName("ExplicitLoaderDemo", false,
                        thread.getContextClassLoader());
            } catch (ClassNotFoundException expected) {
                notFound = true;
            }
            System.out.println("TCCL cannot find main: " + notFound);

            Class<?> viaExplicit =
                    Class.forName("ExplicitLoaderDemo", false, app);
            System.out.println("Explicit finds main: "
                    + (viaExplicit == ExplicitLoaderDemo.class));

            Class<?> viaCaller = Class.forName("ExplicitLoaderDemo");
            System.out.println("Caller forName finds main: "
                    + (viaCaller == ExplicitLoaderDemo.class));

            Class<?> viaBootstrap =
                    Class.forName("java.lang.String", false, null);
            System.out.println("Bootstrap finds String: "
                    + (viaBootstrap == String.class));

            System.out.println("Defining loader unchanged: "
                    + (viaExplicit.getClassLoader() == app));
        } finally {
            thread.setContextClassLoader(previous);
        }

        System.out.println("TCCL restored: "
                + (thread.getContextClassLoader() == previous));
    }
}
```

Run with JDK 17+ using a standard class path configuration:

```bash
javac ExplicitLoaderDemo.java
java ExplicitLoaderDemo
```

Stdout:

```text
TCCL is isolated: true
TCCL cannot find main: true
Explicit finds main: true
Caller forName finds main: true
Bootstrap finds String: true
Defining loader unchanged: true
TCCL restored: true
```

Explanation:

1. `isolated` is a custom loader with a `null` parent. According to the default algorithm, it can delegate to bootstrap, but it does not automatically read application classes on the application class path.
2. Passing the `isolated` TCCL to `Class.forName` causes `ExplicitLoaderDemo` not to be found, and `notFound` becomes `true`.
3. When `app` is passed explicitly, the lookup finds the same runtime class as `ExplicitLoaderDemo.class`.
4. The `Class.forName(String)` overload uses the loader of the **calling class**, so it is not broken by changing the TCCL.
5. `Class.forName(..., false, null)` demonstrates bootstrap lookup of `String`.
6. `finally` restores the TCCL; changing the context does not change the defining loader of `ExplicitLoaderDemo`.

**Key takeaway:** on the same thread and with the same class name, choosing a different loader can produce different results. APIs that accept an explicit loader allow the caller to control that.

## 7. ServiceLoader: comparing lookup via TCCL and explicit loader
`ServiceLoader` is an important exception: the overload that does not accept a loader **intentionally** reads the TCCL. When the plugin owner is known, we can eliminate dependence on the thread's ambient state:

```java
// Snippet inside a method; MyService and pluginLoader have already been declared.
ServiceLoader<MyService> ambient = ServiceLoader.load(MyService.class);
ServiceLoader<MyService> explicit =
        ServiceLoader.load(MyService.class, pluginLoader);
```

`ambient` depends on the TCCL of the **calling thread**, whereas `explicit` depends on the passed loader itself. If an executor worker's TCCL is changed, the two calls can see different sets of providers. The `META-INF/services/<binary-service-name>` descriptor must be discoverable by the specified loader; the provider must implement the **same runtime service API** that the host uses. In named modules, there are also `uses`/`provides` and the overload taking `ModuleLayer`. This is how the loader selection principle from Section 5 is applied to SPI; the ServiceLoader lesson at the end of the chapter includes a full runnable sample project.
## 8. Choosing a loader at thread and executor boundaries
`new Thread` typically inherits the TCCL at creation time. An executor worker may live long before a request is submitted, so the submitter's TCCL is **not** automatically propagated to each task. For example, if a plugin factory already knows `pluginLoader`, it can pass that loader into the task's constructor/parameter and call `Class.forName(name, false, pluginLoader)` instead of relying on the worker's TCCL.

If a library requires using the TCCL, change it **inside the executing worker** and restore `previous` in `finally`. Do not change the submitter's TCCL and assume the worker will follow. The lesson on thread inheritance, pools, and finally covers wrapper/exception paths in detail.
## 9. How to switch the TCCL responsibly

There are legacy frameworks that only read `Thread.currentThread().getContextClassLoader()` without providing an overload that accepts a loader. In that case, you should use a narrow scope:

```java
Thread current = Thread.currentThread();
ClassLoader previous = current.getContextClassLoader();

try {
    current.setContextClassLoader(pluginLoader);
    // Call the framework that intentionally uses the TCCL right inside this scope.
} finally {
    current.setContextClassLoader(previous);
}
```

The snippet above illustrates this with a chosen `pluginLoader`. The principles:

- Save and restore the TCCL on the **same thread**.
- Do not retain the plugin's TCCL after the work is completed.
- For nested calls, each level that makes a change should save the value **immediately before** changing it, rather than assuming the previous context is the system loader.
- If the task switches threads or triggers an asynchronous callback, this scope **does not automatically propagate** to other threads.
- In long-running servers, a thread pool, listener, cache, or TCCL still holding a reference to a plugin loader can prevent garbage collection/class unloading after a redeploy.

You should not “reset” the TCCL with `setContextClassLoader(null)` after every callback: that is not necessarily the prior value, and `null` has semantics according to the `Thread` API. Restore the exact `previous` value.

## 10. Plugin factory and loader dependency injection

Instead of having every method read the TCCL, you can pass the loader into the constructor:

```java
public final class ProviderRegistry {
    private final ClassLoader providerLoader;

    public ProviderRegistry(ClassLoader providerLoader) {
        this.providerLoader =
                java.util.Objects.requireNonNull(providerLoader);
    }

    public <S> java.util.ServiceLoader<S> providers(Class<S> service) {
        return java.util.ServiceLoader.load(service, providerLoader);
    }
}
```

This code can be saved as `ProviderRegistry.java`. The registry knows which loader manages the providers; the calling thread does not alter that choice.

Benefits:

- **Easy to test:** tests can pass a test loader or a dedicated loader for a fixture.
- **Reproducible bugs:** you know the exact loader used in logs and stack traces.
- **Fits plugin architecture:** each plugin has its own owner/lifecycle.
- **Avoids cross-thread contamination:** no need to modify the TCCL for APIs that have an explicit overload.
- **Reduces leaks:** the registry can be released along with the plugin instead of being retained indefinitely in a host static cache.

However, an explicit loader **does not automatically guarantee** that the loader sees every required class. You need to design delegation properly for the shared API and the providers.

### Do not choose the system loader mechanically

`ClassLoader.getSystemClassLoader()` is usually suitable for simple apps run with `java -cp`. In an application server, plugin manager, test runner, or runtime modules, the implementation may lie outside the visibility of the system loader.

Rely on the **artifact owner**: an API anchor, the loader handed out by the plugin manager, the module/layer loader, or the registry's provider loader. Do not replace every TCCL with the system loader merely because the code runs inside an app.

## 11. Common mistakes and how to fix them

| Mistake | Why it is wrong | How to handle it |
|---|---|---|
| Believing `Class.forName(name)` uses the TCCL | The single-parameter overload uses the calling class's loader | Use the three-parameter overload to select the loader |
| Calling `ServiceLoader.load(service)` in a worker without considering context | Provider lookup depends on the worker's TCCL | Pass an explicit loader when an owner exists |
| Changing the TCCL on the submitting thread and assuming the worker sees it immediately | Workers have their own TCCL, which is often reused | Set/restore inside the worker or remove the TCCL dependency |
| Failing to restore the TCCL | Subsequent tasks may use the wrong context and retain the old class loader | Use `try/finally` |
| Restoring with `null` instead of the previous value | Null has its own contract and can change behavior | Save `previous` and restore that exact value |
| Using `getSystemClassLoader()` for every provider | The provider may be defined by another loader | Obtain the loader from the plugin/module owner |
| Using the library API's loader to look up an implementation in a child plugin | A parent does not see child classes by default | Use an explicitly passed plugin loader |
| Having two copies of a shared interface with the same binary name | Their runtime identities differ | Define the shared API once in a common loader |
| Thinking an explicit loader bypasses module access | JPMS and Java access checks still apply | Declare `uses`, `provides`, and check exports/opens |
| Holding a plugin's `Class<?>` or `ServiceLoader` in a singleton forever | References can prevent class unloading | Manage caches and registries according to the plugin lifecycle |
| Treating `null` as bootstrap across all APIs | `Class.forName`, `ServiceLoader`, and `Thread` handle it differently | Read the documentation for each overload |

### When should you still use the TCCL?

The TCCL is a valid choice when:

- The framework explicitly publishes the contract “locate implementations via thread context”.
- The caller knows clearly which thread runs the lookup and sets the proper context.
- There is a mechanism to **restore in finally** and manage the lifecycle.
- You do not obtain a ServiceLoader via one tenant's TCCL and then cache it indefinitely to share with other tenants.
- The shared API has a class identity consistent with the provider loader.

In cases where the specific loader is already known when constructing the component, an explicit loader is usually easier to maintain.

## 12. Self-check exercises

**Question 1.** Does `Class.forName("example.Task")` automatically use the TCCL?

**Answer:** No. The single-parameter overload uses the calling class's loader. To pass a specific loader, use `Class.forName(name, initialize, loader)`.

**Question 2.** Which loader does `ServiceLoader.load(MyService.class)` use?

**Answer:** The current thread's TCCL per the Java 17 contract. The overload `ServiceLoader.load(MyService.class, chosenLoader)` uses the specified loader.

**Question 3.** Why can the same method find a class on the main thread but fail to find it on an executor worker?

**Answer:** If the method chooses the TCCL, each thread has a different context; the worker may have been pre-created or managed by a container.

**Question 4.** When using a library that only supports the TCCL, on which thread must the context be changed?

**Answer:** The thread that actually calls the library and performs the lookup, saving the old value and restoring it in `finally`.

**Question 5.** If `SomeClass.class.getClassLoader()` and the TCCL differ, what happens to the defining loader of `SomeClass`?

**Answer:** Nothing changes. The defining loader is part of the runtime class identity; the TCCL is only per-thread lookup state.

**Question 6.** Do `Class.forName(name,false,null)` and `ServiceLoader.load(service,null)` always have the same meaning?

**Answer:** No. The `Class.forName` overload uses the bootstrap loader when the loader is null; `ServiceLoader.load(service,null)` uses the system loader, or the bootstrap loader when there is no system loader.

**Question 7.** A plugin provider implements an interface `api.Plugin` with the same binary name, but defined by its own loader. Can the host reliably cast it to the host's `api.Plugin`?

**Answer:** No. The same runtime interface identity is required, usually achieved by having plugins delegate the shared API type to a common loader.

**Question 8.** What can happen if a TCCL from a plugin remains on a worker thread pool after the plugin has stopped?

**Answer:** It can keep the plugin's loader and class metadata reachable, preventing hot reload/unloading from freeing resources as expected.

## 13. Key takeaways and official documentation

- **The TCCL** provides a loader per thread context; it is useful for SPI, but easily becomes a hidden dependency in executors/servers/plugins.
- **An explicit loader** is a parameter/configuration that accurately represents the owner of a class or provider, aiding debugging and testing.
- **Single-parameter Class.forName** uses the calling class's loader; **single-parameter ServiceLoader.load** uses the TCCL.
- **Switching the TCCL must be scoped and restored**, especially with thread pools that reuse workers.
- **Loader visibility differs from runtime type identity**: providers must use the same shared API runtime types as the host.
- **Null does not mean the same thing across all APIs**; read the contract of the overload being used.

Official sources:

1. [Java SE 17 — Thread.getContextClassLoader and setContextClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html).
2. [Java SE 17 — Class.forName](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html).
3. [Java SE 17 — ServiceLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html).
4. [Java SE 17 — ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html).
5. [JVMS 17 — Loading, Linking, and Initializing](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html).
