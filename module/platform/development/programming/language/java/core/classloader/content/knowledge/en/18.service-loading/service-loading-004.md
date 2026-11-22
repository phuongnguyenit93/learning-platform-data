# `ServiceLoader.load` with an explicit loader or context loader

> **Java Core → ClassLoader → Service Loading.** This lesson explains the difference between `ServiceLoader.load(Service.class)` (using the **thread context class loader – TCCL**) and `ServiceLoader.load(Service.class, chosenLoader)` (using an **explicit loader**), how providers are packaged in a JAR, the impact of class-loader delegation, the provider lookup mechanism in unnamed/named modules, and safe cache/lifecycle management. The main hands-on practice uses **Java 17+**; module/stream APIs were introduced in Java 9.

## 1. Core Answer

`java.util.ServiceLoader<S>` is the standard API for discovering **implementations (service providers)** of an interface/abstract service type `S`, without the consumer having to hard-code each implementation class name.

There are two common ways to invoke it:

~~~java
// (1) Relies on the current thread's TCCL.
ServiceLoader<MyService> viaContext =
        ServiceLoader.load(MyService.class);

// (2) Explicitly specifies the class loader to use as the starting point for provider lookup.
ClassLoader chosenLoader = obtainPluginLoader();
ServiceLoader<MyService> viaExplicit =
        ServiceLoader.load(MyService.class, chosenLoader);
~~~

This is an **illustrative snippet**, not a standalone Java file; `MyService` and `obtainPluginLoader` are provided by the application.

**Official Java SE rule:**

~~~java
ServiceLoader.load(service)
~~~

**is equivalent to:**

~~~java
ServiceLoader.load(
        service,
        Thread.currentThread().getContextClassLoader())
~~~

This means the single-parameter overload depends on the **TCCL at the time the `ServiceLoader` is created**, whereas the two-parameter overload uses the **loader you pass in**. It is not an arbitrary choice based on the service interface's package.

### Quick Comparison Table

| Invocation | Loader used as starting point for provider discovery | Commonly used when |
| --- | --- | --- |
| `ServiceLoader.load(S.class)` | TCCL of the thread **calling `load`** | A framework needs to select providers based on the caller/application context |
| `ServiceLoader.load(S.class, pluginLoader)` | The chosen `pluginLoader` | A plugin host/container wants controlled lookup without depending on the current thread |
| `ServiceLoader.load(S.class, null)` | **System class loader**, or bootstrap if there is no system loader | You need the documented fallback according to the Java SE API; `null` does not mean “find nothing” |
| `ServiceLoader.loadInstalled(S.class)` | **Platform class loader** on Java 9+ | Only installed/platform providers are needed; usually does **not** see application classpath/module-path providers |
| `ServiceLoader.load(layer, S.class)` | Specified **ModuleLayer** along with its parent layers | Plugins operate through JPMS module layers; searches only named-module providers |

**The TCCL is distinct from the defining loader.** The loader that defines `S.class`, the loader that defines the provider implementation, and the TCCL can all be different objects. A result is valid only when the provider is **assignable** to the exact runtime `S.class` passed in by the consumer.

## 2. Why Does ServiceLoader Need a Context Class Loader?

Suppose a platform library is loaded by a parent classloader, while an application/plugin has a child classloader:

~~~text
               Platform / parent / host loader
                   |
                   +-- api.PaymentService
                   +-- framework.Discovery
                   |
                   v
                Plugin loader
                   |
                   +-- impl.CardPayment
                   +-- META-INF/services/api.PaymentService

Framework in parent wants to find implementation in child:
  Using only Framework's defining loader => may not see plugin
  Choosing TCCL = plugin loader => can find provider
  Passing plugin loader explicitly => no need to change TCCL
~~~

Standard parent-first delegation only lets a **child ask its parent**; it does not cause the parent to automatically search all classes/resources of the child. ServiceLoader uses the TCCL in its convenience overload so that a framework loaded by a parent still has a **vantage point** into providers implemented in a child/application loader.

That does **not** make the TCCL the parent of every class or replace JVM bytecode class resolution:

- `Framework.class.getClassLoader()` is still the loader that **defines** Framework.
- `PaymentService.class` must be the shared contract with the exact same runtime identity.
- The TCCL is a **reference on a Thread object**, which can be changed via `getContextClassLoader`/`setContextClassLoader`.
- Only APIs that **actively use the TCCL** (such as the `ServiceLoader.load(S.class)` overload) are directly affected.
- With an explicit loader, the caller can select the plugin loader **without changing** the worker thread's TCCL.

### 2.1. When does `ServiceLoader.load(S.class)` obtain the TCCL?

**At the moment you call `ServiceLoader.load(S.class)` to create the loader object**, rather than repeatedly querying the TCCL before each `iterator().next()`. Provider discovery/instantiation, by contrast, happens **lazily**, so the time of **selecting the loader** and the time of **creating the provider object** do not necessarily coincide.

Conceptual example:

~~~java
Thread thread = Thread.currentThread();
ClassLoader saved = thread.getContextClassLoader();

ServiceLoader<MyService> serviceLoader;
try {
    thread.setContextClassLoader(pluginLoader);
    serviceLoader = ServiceLoader.load(MyService.class);
} finally {
    thread.setContextClassLoader(saved);
}

// After restoring the TCCL, serviceLoader still uses the loader chosen
// at the time ServiceLoader.load(...) was called.
for (MyService provider : serviceLoader) {
    use(provider);
}
~~~

This is a snippet inside an application that has a valid `MyService`, `pluginLoader`, and `use`. Changing the thread's TCCL **after** creating the `ServiceLoader` object does not switch that object to a different loader.

**Do not infer that the chosen loader is guaranteed to see the provider.** The classpath, parent delegation, `META-INF/services`, module graph, and class identity must still align.

## 3. How Are Providers Loaded? Classpath and Module Path

A service can have **0, 1, or multiple providers**. Providers are not necessarily created immediately when you call the `load` factory method; the caller iterates via `iterator()`, `stream()`, or `findFirst()` to actually discover/instantiate them according to the API.

### 3.1. Providers on the classpath / unnamed module

Given the interface:

~~~java
package demo.spi;

public interface GreetingService {
    String greet();
}
~~~

The JAR supplying the provider needs to:

1. Contain an implementation class, for example `demo.plugin.EnglishGreeter implements demo.spi.GreetingService`.
2. Have a configuration file with the exact resource name:

~~~text
META-INF/services/demo.spi.GreetingService
~~~

3. Have UTF-8 encoded file content containing the **binary name** of the implementation:

~~~text
demo.plugin.EnglishGreeter
~~~

4. Ensure both the resource and the implementation are **visible** through the loader that `ServiceLoader` uses for lookup. A provider class in an unnamed module generally needs to be a **public class** with a **public no-argument constructor** for ServiceLoader to instantiate it.

The configuration file may contain multiple provider names, one per line. Blank lines and `#` comments are handled according to the specification; the names must be valid binary names. An incorrect name, a provider that does not implement the interface with the right runtime identity, or an invalid constructor can throw a `ServiceConfigurationError`.

**Do not confuse** `META-INF/services` with an OS folder-scanning API. ServiceLoader looks up **resources through the classloader** (typically `getResources("META-INF/services/"+serviceName)` for providers in unnamed modules), so packaging the resource at the right path inside the JAR matters more than the working directory location.

### 3.2. Providers in named modules (JPMS)

Since Java 9, a provider can be declared using `module-info.java`:

~~~java
module demo.provider {
    requires demo.api;
    provides demo.spi.GreetingService
        with demo.provider.EnglishGreeter;
}
~~~

The consumer module (for example, `demo.consumer`) must declare:

~~~java
module demo.consumer {
    requires demo.api;
    uses demo.spi.GreetingService;
}
~~~

The `demo.api` API exports the `demo.spi` package:

~~~java
module demo.api {
    exports demo.spi;
}
~~~

These are **three illustrative module descriptors**, not a single Java file. For a caller inside an **explicit named module**, `uses` is mandatory under the ServiceLoader contract; omitting `uses` can cause a `ServiceConfigurationError` when calling `load`. `requires` ensures readability of the module that owns the service type if the service resides in another module.

**Do not confuse:**

- `requires`: module dependency/readability.
- `uses`: declares that the caller consumes the service.
- `provides ... with ...`: the provider module advertises its implementation.
- `exports`: makes a public API package accessible; the provider implementation class does not necessarily have to be exported like a regular public API.
- The module must be part of the appropriate **resolved graph/layer**; merely placing a JAR on the module path does not mean that module is present in the graph.

When using the `load(S.class, loader)` overload on JDK 9+, ServiceLoader can search for providers in **named modules** associated with the loader/module layer before reading provider-configuration files in **unnamed modules**. Therefore, an explicit loader **does not mean “only scan this loader's JAR URLs”**.

## 4. Complete Hands-On Lab: Explicit Loader and TCCL for a Plugin JAR

This lab intentionally separates the **host API/application** from the **provider JAR**. We will demonstrate that:

- The host loader does not see the provider because the provider is not on the host classpath.
- Passing `pluginLoader` explicitly sees the provider.
- Calling `load(S.class)` when the TCCL is the host does not see it.
- Creating the `ServiceLoader` when the TCCL is the plugin, **then restoring the TCCL before iterating**, still sees the provider.

### 4.1. Directory Tree

~~~text
service-loader-lab/
├── src/
│   ├── api/demo/spi/GreetingService.java
│   ├── plugin/demo/plugin/EnglishGreeter.java
│   └── host/demo/host/ServiceLookupDemo.java
├── config/
│   └── META-INF/services/demo.spi.GreetingService
└── build/                     (created by the commands below)
    ├── api/
    ├── plugin/
    ├── host/
    └── provider.jar
~~~

File **`src/api/demo/spi/GreetingService.java`**:

~~~java
package demo.spi;

public interface GreetingService {
    String greet();
}
~~~

File **`src/plugin/demo/plugin/EnglishGreeter.java`**:

~~~java
package demo.plugin;

import demo.spi.GreetingService;

public final class EnglishGreeter implements GreetingService {
    public EnglishGreeter() { }

    @Override
    public String greet() {
        return "hello from plugin";
    }
}
~~~

Configuration file **`config/META-INF/services/demo.spi.GreetingService`** has **exactly one line**:

~~~text
demo.plugin.EnglishGreeter
~~~

File **`src/host/demo/host/ServiceLookupDemo.java`**:

~~~java
package demo.host;

import demo.spi.GreetingService;

import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.ServiceLoader;

public final class ServiceLookupDemo {
    private static String values(
            ServiceLoader<GreetingService> services) {
        List<String> result = new ArrayList<>();
        for (GreetingService service : services) {
            result.add(service.greet());
        }
        return result.toString();
    }

    public static void main(String[] args) throws Exception {
        ClassLoader hostLoader = GreetingService.class.getClassLoader();
        Thread caller = Thread.currentThread();
        ClassLoader originalTccl = caller.getContextClassLoader();
        URL jar = Path.of("build", "provider.jar")
                .toAbsolutePath().toUri().toURL();

        try (URLClassLoader pluginLoader = new URLClassLoader(
                new URL[] {jar}, hostLoader)) {

            // Control the program's TCCL: make no assumptions about the environment.
            caller.setContextClassLoader(hostLoader);
            System.out.println("context-host="
                    + values(ServiceLoader.load(GreetingService.class)));
            System.out.println("explicit-host="
                    + values(ServiceLoader.load(
                            GreetingService.class, hostLoader)));

            System.out.println("explicit-plugin="
                    + values(ServiceLoader.load(
                            GreetingService.class, pluginLoader)));

            caller.setContextClassLoader(pluginLoader);
            ServiceLoader<GreetingService> captured =
                    ServiceLoader.load(GreetingService.class);

            // Restore BEFORE iterating over the ServiceLoader.
            caller.setContextClassLoader(hostLoader);
            System.out.println("captured-after-change="
                    + values(captured));
        } finally {
            caller.setContextClassLoader(originalTccl);
        }
    }
}
~~~

**Design safety point:** The `URLClassLoader` has as its parent the loader that defines the shared service interface, so `EnglishGreeter` implements the **exact same `demo.spi.GreetingService`** that the host passes into `ServiceLoader.load`. The plugin JAR **must not** contain a copy of `demo/spi/GreetingService.class` redefined by the child loader.

### 4.2. Compile and Package the JAR (Linux/macOS, POSIX shell)

From the `service-loader-lab` directory:

~~~bash
mkdir -p build/api build/plugin build/host \
    build/plugin/META-INF/services

# 1. Compile the service interface into the host/shared API.
javac --release 17 -d build/api \
    src/api/demo/spi/GreetingService.java

# 2. Compile the plugin against the host API.
javac --release 17 -cp build/api -d build/plugin \
    src/plugin/demo/plugin/EnglishGreeter.java

# 3. Copy the provider configuration to the right location inside the JAR.
cp config/META-INF/services/demo.spi.GreetingService \
    build/plugin/META-INF/services/demo.spi.GreetingService

# 4. Package ONLY the plugin implementation and metadata, without the API.
jar --create --file build/provider.jar -C build/plugin .

# 5. Host main class uses the API, without the plugin JAR on the classpath.
javac --release 17 -cp build/api -d build/host \
    src/host/demo/host/ServiceLookupDemo.java

java -cp "build/api:build/host" demo.host.ServiceLookupDemo
~~~

On Windows, use the appropriate PowerShell directory-creation/copy commands and change the classpath separator to **`;`**:

~~~powershell
java -cp "build/api;build/host" demo.host.ServiceLookupDemo
~~~

When setting up directories/files manually in an IDE, ensure the `META-INF/services/demo.spi.GreetingService` path inside the JAR has exact case matching; `jar --list --file build/provider.jar` can verify this.

### 4.3. Expected Stdout (Java 17+ in the lab configuration)

~~~text
context-host=[]
explicit-host=[]
explicit-plugin=[hello from plugin]
captured-after-change=[hello from plugin]
~~~

**Exact explanation:**

1. `context-host=[]`: The TCCL is set to the host loader, so `ServiceLoader.load(S.class)` only sees provider sources reachable by the host. The lab does not deploy any provider on the host classpath.
2. `explicit-host=[]`: regardless of what the TCCL is, the two-parameter overload explicitly selects **hostLoader**.
3. `explicit-plugin=[hello from plugin]`: the child loader has a URL pointing to `provider.jar`, locates `META-INF/services`, and defines `EnglishGreeter`; the interface is defined by the parent.
4. `captured-after-change=[hello from plugin]`: the `ServiceLoader` is **created while the TCCL is the plugin loader**, and then the caller restores the TCCL to the host **before the iterator begins**. The ServiceLoader still retains the initially chosen loader.
5. `try-with-resources` closes `pluginLoader` after iterating over the providers completes; `finally` restores the TCCL regardless of whether provider discovery succeeds or throws an error.

This is the output of the **configured experiment**, not a guarantee for every application that happens to have additional providers in its host runtime. If the host has other providers for the same service, the result will vary depending on the actual deployment.

### 4.4. Try These Changes to Understand the Mechanism

- **Remove the `META-INF/services/...` file from the JAR:** Classpath-based ServiceLoader does not automatically scan all classes to find implementations; the two lines using the plugin will typically return `[]`.
- **Misspell the FQCN in the configuration file:** iterating over providers can throw a `ServiceConfigurationError` with a “provider ... not found” cause.
- **Put the provider JAR onto the host classpath:** the host loader can find the provider, breaking the “empty host, plugin has provider” test boundary.
- **Change the plugin loader's parent to the platform loader without providing the shared API:** the provider may fail to find `demo.spi.GreetingService`, or type identity will mismatch if the plugin bundles its own copy of the API.
- **Change the TCCL after calling `ServiceLoader.load(S.class)`:** does not switch the already held `ServiceLoader` object to the new loader.

## 5. Explicit Loader: Proactively Choosing Context Instead of Depending on the Thread

In a plugin manager, explicit selection is usually safer and clearer:

~~~java
ServiceLoader<PluginService> providers =
        ServiceLoader.load(PluginService.class, pluginLoader);

for (PluginService provider : providers) {
    register(provider);
}
~~~

This snippet requires `PluginService`, `pluginLoader`, and `register` in the project. The advantage is that the API expresses the **loader selection intent** right at the call site; an executor worker having the host TCCL or another plugin's TCCL does not alter the passed-in loader.

However, an explicit loader is still **not “bypassing delegation”**:

- With a default `URLClassLoader`, finding resources/classes typically depends on **parent-first behavior**.
- `ServiceLoader.load(S.class, pluginLoader)` on JDK 9+ can discover **named-module providers** associated with the module layer, rather than only reading configurations inside `pluginLoader.getURLs()`.
- The service contract must be accessible and have the exact class identity; the `S.class` passed in by the host must not be replaced by a copy of `S` defined by the plugin.
- A new ServiceLoader also has its **own provider cache**. Changing an external `ClassLoader` variable does not mutate previously created ServiceLoaders.

When a host has plugins belonging to multiple tenants, tie service discovery to the **specific plugin context/loader**, rather than relying on the incidental TCCL of the calling thread.

### 5.1. When the `loader` Argument Is null

According to the Javadoc of `load(Class<S>, ClassLoader)`:

~~~java
ServiceLoader<MyService> viaSystem =
        ServiceLoader.load(MyService.class, null);
~~~

If the loader is null, the API uses the **system class loader** (or the bootstrap loader if there is no system loader). It does **not** mean “use bootstrap immediately”, “find no providers”, or “use the current TCCL”.

Distinguish between two cases:

~~~java
ServiceLoader.load(MyService.class, null);
ServiceLoader.load(MyService.class);
~~~

The first call selects the system/bootstrap fallback. The second call reads the TCCL; if the TCCL is also null, the two-parameter overload's fallback leads to the system/bootstrap loader as above. If the TCCL is a plugin loader, the two calls **can produce different results**.

### 5.2. `loadInstalled` Does Not Replace Plugin Discovery

~~~java
ServiceLoader<MyService> installed =
        ServiceLoader.loadInstalled(MyService.class);
~~~

On Java 9+, this API uses the **platform class loader**, which usually does not see provider deployments on the application classpath/module path. It is not a general choice for finding plugin JARs shipped by an application. Do not infer from the name “installed” that Java still has the `lib/ext` extension mechanism like Java 8.

## 6. When Should You Proactively Change the TCCL?

Some frameworks or libraries only call the single-parameter overload and **do not let you pass a loader**. In that case, you can set the TCCL around an operation:

~~~java
Thread thread = Thread.currentThread();
ClassLoader previous = thread.getContextClassLoader();

try {
    thread.setContextClassLoader(pluginLoader);
    framework.discoverAndRun();
} finally {
    thread.setContextClassLoader(previous);
}
~~~

This is a **snippet** and requires `framework` and `pluginLoader` in scope. The `try/finally` block is important because:

- The framework method may throw an exception.
- A worker in an `ExecutorService` is typically **reused**. Without restoring it, the next task might mistakenly look up providers from the previous plugin.
- The TCCL is a **strong reference** to the loader. A long-lived thread (pool worker, scheduler) holding onto a stopped plugin loader can prevent class unloading and cause hot reloads to retain JARs/Metaspace longer.
- Setting the TCCL does not automatically propagate to an already existing worker; when `framework.discoverAndRun()` runs on another thread, that thread must have the right TCCL **at the actual time `ServiceLoader.load` is called**.

If the two-parameter overload is available and can be called directly, **prefer the explicit loader** to reduce unintended changes to thread context.

### 6.1. TCCL, `new Thread`, and Thread Pools

In a standard Thread creation setup, a child thread **inherits the TCCL at the time the thread object is created**, not when `start()` is called. A thread pool typically has pre-created, reused workers; `executor.submit(runnable)` **does not guarantee** that the worker will pick up the submitter's TCCL.

Example:

~~~java
ExecutorService executor = Executors.newSingleThreadExecutor();

// This is only a conceptual example:
Thread.currentThread().setContextClassLoader(pluginLoader);
executor.submit(() -> ServiceLoader.load(PluginService.class));
// There is no guarantee the worker sees pluginLoader if the worker already existed.
~~~

This is an illustrative snippet, **not** a proper propagation approach. Aside from missing imports and variables, it omits restoring the caller's TCCL and does not iterate over providers yet. A proper design must capture the loader from the plugin context and **set it on the worker inside the task itself**, or pass it explicitly to `ServiceLoader.load`.

### 6.2. Wrapper Propagation for Executor Tasks (Java 17+)

File **`ServiceContextTasks.java`**:

~~~java
import java.util.concurrent.Callable;

public final class ServiceContextTasks {
    private ServiceContextTasks() { }

    public static <T> Callable<T> withTccl(
            ClassLoader desired,
            Callable<T> operation) {
        return () -> {
            Thread current = Thread.currentThread();
            ClassLoader previous = current.getContextClassLoader();
            try {
                current.setContextClassLoader(desired);
                return operation.call();
            } finally {
                current.setContextClassLoader(previous);
            }
        };
    }
}
~~~

~~~bash
javac --release 17 ServiceContextTasks.java
~~~

This is a valid helper class without `main`. Usage from code that has `ExecutorService executor` and `pluginLoader`:

~~~java
var future = executor.submit(
    ServiceContextTasks.withTccl(pluginLoader, () -> {
        var services = ServiceLoader.load(PluginService.class);
        return services.findFirst().orElse(null);
    })
);
PluginService service = future.get();
~~~

This snippet requires surrounding imports/variables/context, and also requires managing the lifecycle of the returned provider. When the `ServiceLoader.load` method is invoked inside the worker, the TCCL is already `pluginLoader`. `finally` restores it whether the operation succeeds or fails. In a multi-tenant app, pass `pluginLoader` from the host-managed context rather than copying a TCCL value that might have been polluted by another task.

**Note:** `withTccl` applies only to **synchronous operations inside the callback**. If the callback spawns other async tasks without forwarding the loader, they are not guaranteed to share the same context.

## 7. Lazy Discovery, Caching, and `reload()`

Many misconceptions arise because `ServiceLoader.load` only **creates the loader object**. Providers are discovered/instantiated when you actually iterate:

~~~java
ServiceLoader<MyService> services =
        ServiceLoader.load(MyService.class, chosenLoader);

// At this point, you cannot assume all providers have been instantiated.
for (MyService provider : services) {
    System.out.println(provider);
}
~~~

- `iterator()` discovers and **instantiates** providers lazily; `hasNext`/`next` can throw `ServiceConfigurationError`.
- Already loaded providers are stored in **that `ServiceLoader`'s own cache**; subsequent iterations typically yield cached providers first and then continue searching for remaining ones.
- `findFirst()` (Java 9+) returns an `Optional<S>` containing the first provider, if present; there is no guarantee that the first provider across the entire system has a stable priority unless specific deployment/module rules specify it.
- `stream()` (Java 9+) returns a `Stream<ServiceLoader.Provider<S>>`; `provider.type()` gives the provider type and `provider.get()` creates/retrieves the instance according to the contract. It allows inspecting/filtering types without necessarily instantiating all providers.
- `reload()` **clears the provider cache** so that subsequent iterations search from scratch; it **does not** switch the `ServiceLoader` to another classloader and **does not** unload already loaded runtime classes.

### 7.1. Do Not Mistake `reload` for Reloading a JAR/Class

~~~java
ServiceLoader<MyService> services =
        ServiceLoader.load(MyService.class, pluginLoader);
services.reload();
~~~

The outcome does not guarantee that plugin bytecode on disk will be redefined by the VM. The same defining classloader cannot define the same binary name multiple times; hot reloading a new implementation typically requires creating a **new-generation plugin loader**, switching service routing, stopping and closing the old generation, and dropping references.

After `reload()`, previously created iterators/streams **should no longer be used**; the API has a fail-fast mechanism (`ConcurrentModificationException`) if the cache is cleared while iterating.

### 7.2. `ServiceLoader` Is Not Thread-Safe

The Javadoc explicitly states **instances of `ServiceLoader` are not safe for use by multiple concurrent threads**. Do not share a single ServiceLoader instance across multiple workers calling both `iterator()` and `reload()` without proper orchestration.

Better ways to manage this:

- Create a ServiceLoader **per plugin/request/context** when discovery is needed.
- Iterate and select providers **in a single managed thread/phase**, then publish the service instances with appropriate synchronization.
- Separate provider instance thread-safety from `ServiceLoader` thread-safety; a provider may not be thread-safe even after discovery has finished.
- Do not cache `ServiceLoader.load(S.class)` in a **JVM-wide static singleton** across different applications/TCCLs; the Javadoc warns against wrong context and memory leaks. If caching is needed, key it accurately by **service type + loader/layer + lifecycle** and perform cleanup when the plugin stops.

## 8. Handling `ServiceConfigurationError` Properly

`ServiceConfigurationError` **extends `Error`**, not `Exception`. The error can occur when calling `load` (for example, a named caller missing `uses`) or later when `iterator`/`stream` actually discovers the provider. Common causes:

| Symptom | Possible reason | How to check |
| --- | --- | --- |
| No provider found, list is `[]` | Config file/provider module is not visible through the loader | Check `META-INF/services` in the JAR, loader, and graph |
| “Provider ... not found” | Wrong provider name in config, missing JAR, or class unavailable | Check exact binary name + classpath/loader |
| “Provider ... not a subtype” | Provider implements a copy of `S` from a different defining loader | Compare `S.class` identity between host and plugin |
| Cannot instantiate provider | No valid public no-arg constructor for classpath deployment, or constructor throws an error | Inspect cause, visibility, and constructor |
| Error when named caller calls `load` | Module is missing `uses` or service is not accessible | Add appropriate `uses S`/`requires`/`exports` |
| Provider discovery hits wrong tenant/plugin | TCCL is a loader from an old worker | Use an explicit loader or a `try/finally` wrapper |
| Provider retained long after shutdown | Caches, host registries, TCCL, or threads hold strong references | Close instances if needed, clear references, shut down workers |
| Unexpected duplicate providers | Duplicated descriptors/classpath/module paths | Inspect JAR entries, module provides, and parent resources |
| `ConcurrentModificationException` while iterating | `reload()` occurred after an iterator/stream was created | Use a new iterator; do not access ServiceLoader concurrently |

Handling pattern at a trusted boundary:

~~~java
try {
    for (MyService provider : ServiceLoader.load(
            MyService.class, pluginLoader)) {
        register(provider);
    }
} catch (java.util.ServiceConfigurationError problem) {
    // Log full provider metadata/cause and transition the plugin to FAILED.
    throw problem;
}
~~~

This is a snippet. Do not catch all `Error`/`Throwable` and silently skip a “broken provider” unconditionally; `ServiceConfigurationError` usually indicates a serious deployment misconfiguration. The API might try continuing after certain errors, but Java SE does not guarantee full recovery. The operational layer must explicitly decide on a fail-fast, quarantine, or degrade policy.

### 8.1. Debugging with the Chosen Loader Directly

When only classpath SPI is used:

~~~java
String resourceName =
        "META-INF/services/" + MyService.class.getName();

java.util.Enumeration<java.net.URL> urls =
        pluginLoader.getResources(resourceName);

while (urls.hasMoreElements()) {
    System.out.println(urls.nextElement());
}
~~~

This snippet requires `MyService`/`pluginLoader` and a method handling `IOException`. It helps verify which provider configurations are visible through the loader, but **does not prove that the provider class will load, the constructor will succeed, or module access is valid**. With named modules, module descriptors declare providers, so searching only `META-INF/services` is **incomplete**.

If the resource location is right yet the provider still does not work, check which loader defined each class:

~~~java
System.out.println(MyService.class.getClassLoader());
System.out.println(provider.getClass().getClassLoader());
System.out.println(MyService.class.isInstance(provider));
~~~

This is also a snippet (assuming `provider` is already available); its goal is to distinguish between **visibility**, **type identity**, and **instantiation failure**.

## 9. JPMS and `ModuleLayer`: How It Differs from TCCL

For plugin modules resolved in a separate layer, the API:

~~~java
ServiceLoader<MyService> fromLayer =
        ServiceLoader.load(pluginLayer, MyService.class);
~~~

searches for named-module providers in **`pluginLayer` and its parent layers**, and **does not search unnamed-module providers** via `META-INF/services`. This is usually the right choice when the plugin architecture uses JPMS ModuleLayer instead of `URLClassLoader` with JARs on the classpath.

Conversely:

~~~java
ServiceLoader<MyService> fromLoader =
        ServiceLoader.load(MyService.class, someLoader);
~~~

can search for **both named- and unnamed-module providers** according to the ServiceLoader algorithm. Even when a classloader belongs to a layer, named-module lookup can involve **other modules in the same layer**, not just modules defined by that loader itself. Understand this as **service discovery**, not merely `someLoader.loadClass("...")`.

### 9.1. Implementing a Service Provider as a Named Module

Example module declarations:

~~~java
module demo.api {
    exports demo.spi;
}
~~~

~~~java
module demo.provider {
    requires demo.api;
    provides demo.spi.GreetingService
        with demo.provider.EnglishGreeter;
}
~~~

~~~java
module demo.consumer {
    requires demo.api;
    uses demo.spi.GreetingService;
}
~~~

If the compiler/launcher requires:

~~~bash
java --module-path mods --add-modules demo.provider \
     --module demo.consumer/demo.consumer.Main
~~~

`mods` must contain the compiled modules and `Main` must have appropriate runnable code; this command is a **launch pattern**, not a standalone script that builds the three modules. `--add-modules` in the example helps bring the provider module into the graph, while accurate ServiceLoader discovery also depends on the layer/module graph and service declarations. For the classpath demo in section 4, **do not add a `module-info.java` to the provider JAR** and still expect the output/packaging to stay unchanged.

### 9.2. `uses` Does Not Replace `exports`

The consumer module must read the service type's module and declare that it uses the service; the service provider module must declare its providers. Do not try to solve `ServiceConfigurationError` with `--add-opens` when the real issue is a missing `uses` or an unresolved module. `opens` is primarily about deep reflection, not “enabling” SPI provider discovery.

## 10. Provider Lifecycle, Caching, and Hot Reload

When a provider is a plugin holding state/resources, ServiceLoader **does not manage shutdown** for the provider. The discovery/instantiation API does not automatically call `close()` when the host stops using the provider.

For explicitly managed plugins:

~~~text
1. Create plugin ClassLoader / ModuleLayer
2. Discover providers using an explicit loader or layer
3. Validate shared interface identity and constructor/module access
4. Start the service and publish it to the registry
5. Quiesce: stop accepting new requests
6. Drain/cancel async tasks; unregister callbacks/listeners
7. Close plugin-owned providers/resources (if any)
8. Drop ServiceLoader/provider caches and strong references
9. Close URLClassLoader once no concurrent loads remain
10. JVM can unload classes when eligible; not guaranteed immediately
~~~

If you use `ServiceLoader.load(S.class)` inside a long-lived worker thread, letting the worker retain the plugin loader as its TCCL **can keep the old plugin reachable**, even after `URLClassLoader.close()`. Therefore, you must restore the TCCL and clear caches/registries.

**Do not confuse:** `ServiceLoader.reload()` only resets the cache of **a single ServiceLoader instance**; it does not close old providers, does not change the captured TCCL, does not close JARs, does not create a new loader, and does not force GC to unload classes.

With `ServiceLoader.Provider<S>` (Java 9+), `Provider.get()` can create an instance during use; its lifecycle is also the responsibility of the application framework once the provider is obtained.

## 11. Rules for Choosing an Overload in Real Applications

| Scenario | API to consider | Reason |
| --- | --- | --- |
| Framework/library does not know the plugin loader and selects context per request | `ServiceLoader.load(S.class)` | Uses TCCL so parent-side code can find child-side providers |
| Host knows which loader owns the plugin | `ServiceLoader.load(S.class, pluginLoader)` | Explicit; does not depend on executor/TCCL |
| Code needs the default system loader without relying on TCCL | `ServiceLoader.load(S.class, ClassLoader.getSystemClassLoader())` or `load(S.class, null)` | Clear fallback according to the API |
| Only platform providers are wanted | `ServiceLoader.loadInstalled(S.class)` | Uses the platform loader; usually excludes application plugin providers |
| Plugin modules live in a separate ModuleLayer | `ServiceLoader.load(layer, S.class)` | Searches named modules in the layer and its ancestors |
| Need the first provider if available | `ServiceLoader.load(...).findFirst()` | Returns `Optional`; can still throw `ServiceConfigurationError` |
| Need to inspect provider types before instantiating | `ServiceLoader.load(...).stream()` | `Provider.type()` and `Provider.get()` are separate |
| Need to refresh the provider list for the loader already in use | `serviceLoader.reload()` | Resets cache; **does not hot-reload bytecode** |

**Plugin application recommendation:** When the control plane already knows the loader/layer that owns the provider, use an **explicit loader/layer**. Only use TCCL to integrate libraries/frameworks that require an ambient context, and whenever changing the TCCL, always restore it inside `finally`.

## 12. Common Misconceptions

1. “`ServiceLoader.load(S.class)` always uses the loader of `S.class`.” — **False**; it uses the TCCL.
2. “`load(S.class, pluginLoader)` only searches classes from the exact URLs of pluginLoader, never via its parent.” — **False**; you must account for delegation, `getResources`, and named modules/layers.
3. “After creating a ServiceLoader, changing the TCCL switches the loader it uses.” — **False**; the loader is chosen at the factory call.
4. “Placing a JAR into a `plugins` directory causes ServiceLoader to scan it automatically.” — **False** unless loader/module resolution is configured to locate that artifact.
5. “A provider class on the classpath does not need `META-INF/services`.” — **False** for traditional classpath-based provider deployment; standard configuration is required.
6. “A named module still needs `META-INF/services` just like the classpath.” — **Not required**; use `provides ... with`.
7. “`ServiceLoader.loadInstalled` is the way to load plugin JARs.” — **Usually false** on Java 9+ because it uses the platform loader.
8. “`load(S.class, null)` always uses the bootstrap loader.” — **False**; it prefers the system loader.
9. “`ServiceLoader.load` has already instantiated all providers before returning.” — **False**; discovery/instantiation is lazy.
10. “`reload()` creates a new `Class<?>` for the plugin.” — **False**; it only clears the provider cache.
11. “ServiceLoader is automatically thread-safe because it lives in java.util.” — **False**; the Javadoc warns it is not safe for concurrent multi-threaded access.
12. “Having the same interface name on the provider means it is compatible across two loaders.” — **False**; they must share the same runtime type identity.
13. “Setting the TCCL on the submitter is enough for an existing thread pool worker.” — **No guarantee**.
14. “Providers obtained from ServiceLoader are automatically closed when the loader closes.” — **False**; the application manages provider lifecycle.
15. “If the classloader can see the provider, the caller module surely has the right `uses`/readability.” — **False**; JPMS also checks module declarations.

## 13. Self-Check Exercises

Suppose the application API `demo.spi.GreetingService` is defined by the host loader, `pluginLoader` sees `EnglishGreeter` and the SPI file, and the host loader does not see the provider:

1. What does `ServiceLoader.load(GreetingService.class, hostLoader)` yield when iterated? **No providers in the lab**, typically an empty list.
2. What does `ServiceLoader.load(GreetingService.class, pluginLoader)` yield? **The `EnglishGreeter` provider**.
3. If the current TCCL is `pluginLoader`, which option does `ServiceLoader.load(GreetingService.class)` behave like? **The explicit plugin loader**.
4. If the TCCL is changed back to the host after creating the ServiceLoader but before `iterator` runs, does the loader change? **No**.
5. What if `load(S.class, null)` is used while the TCCL is the plugin loader? **System/bootstrap fallback; it does not take the plugin TCCL**.
6. If the provider JAR has no `META-INF/services/demo.spi.GreetingService` file and no named-module declaration, does ServiceLoader scan all `*.class` files? **No**.
7. What is the result if the provider has a class with the same name `demo.spi.GreetingService` that redefines the interface itself? **Not a subtype of the host service type**, potentially a `ServiceConfigurationError`.
8. When does the provider constructor run? **When the provider is lazily instantiated during iteration/Provider.get**, not necessarily when `load` is called.
9. Does `reload()` discard provider objects already stored elsewhere by the host? **No**.
10. If a named caller forgets `uses`, where should that be fixed? **Fix the module descriptor/caller module, not by merely changing the TCCL**.
11. What is the risk of a pool worker keeping an old plugin's TCCL? **Wrong provider lookup and potentially keeping the classloader from unloading**.
12. Does `ServiceLoader.load(layer,S.class)` look up providers in an unnamed module solely through `META-INF/services`? **No**.

## 14. Primary References Worth Consulting

1. [`ServiceLoader` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/ServiceLoader.html): `load` overloads, TCCL, explicit loader, null behavior, named/unnamed modules, caching, `reload`, concurrency, and errors.
2. [`ServiceLoader.Provider` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/ServiceLoader.Provider.html): `type()`, `get()`, and lazy provider creation.
3. [`ClassLoader` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ClassLoader.html): parent delegation, `loadClass`, `getResources`, and runtime loader behavior.
4. [`Thread` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Thread.html): `getContextClassLoader`/`setContextClassLoader` and inheritance.
5. [JPMS `java.lang.Module` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Module.html): module identity/readability.
6. [`ModuleLayer` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ModuleLayer.html): building and using module layers.
7. [JEP 261 — Module System](https://openjdk.org/jeps/261): ServiceLoader with named modules.
8. [Java SPI Tutorial — Oracle (historical Java 8)](https://docs.oracle.com/javase/tutorial/ext/basics/spi.html): concepts of service interface/provider/ServiceLoader; for Java 9+, prefer consulting the current Javadoc regarding JPMS.

**Conclusion:** `ServiceLoader.load(S.class)` picks the **TCCL at the time the ServiceLoader is created**; `ServiceLoader.load(S.class, chosenLoader)` picks the **loader you explicitly specify**. Provider discovery occurs lazily and also depends on `META-INF/services` or JPMS `provides/uses`, class identity, and the module graph. In host/plugin systems, an explicit loader is usually easier to control; if you must use the TCCL, you must pass the right context at the execution boundary and **always restore it in `finally`**.
