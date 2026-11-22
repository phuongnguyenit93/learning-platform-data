# Thread Context Class Loader and ServiceLoader

In Java, a **class loader** determines how the JVM locates and defines classes. For systems with plugins, frameworks, or application servers, not all classes are loaded by the same class loader. A class belonging to a core library may be loaded by a parent class loader, while an implementation of that library resides in a JAR managed by a child class loader.

This is the context for **Thread Context Class Loader (TCCL)** and **ServiceLoader**. TCCL provides running code with a class loader *according to the thread's context*. ServiceLoader can use that class loader to discover providers of a service. Understanding how they work together helps diagnose plugins not being found, type mismatches across class loaders, and differences in behavior between the classpath and the Java Platform Module System (JPMS).

## 1. Class Loaders and Service Provider Interface

The Java Service Provider Interface (SPI) allows a consumer to declare a **service contract**, while one or more other parts supply implementations.

Example contract:

~~~java
package com.example.spi;

public interface GreetingService {
    String greet(String name);
}
~~~

A provider:

~~~java
package com.example.provider;

import com.example.spi.GreetingService;

public final class EnglishGreeting implements GreetingService {
    public EnglishGreeting() {
    }

    @Override
    public String greet(String name) {
        return "Hello, " + name;
    }
}
~~~

Consumer code:

~~~java
import com.example.spi.GreetingService;
import java.util.ServiceLoader;

ServiceLoader<GreetingService> services =
        ServiceLoader.load(GreetingService.class);

for (GreetingService service : services) {
    System.out.println(service.greet("An"));
}
~~~

The application does not need to hard-code the name **EnglishGreeting**. Finding providers relies on service configurations observable by ServiceLoader, and loading providers depends on the class loader / module layer environment.

## 2. What Is the Thread Context Class Loader?

Each Thread has a context class loader. It can be retrieved or changed via:

~~~java
Thread current = Thread.currentThread();

ClassLoader context = current.getContextClassLoader();

current.setContextClassLoader(context);
~~~

**getContextClassLoader()** returns the context class loader of the current thread. **setContextClassLoader(ClassLoader)** sets a new context for the thread.

TCCL is not synonymous with the class loader that defined the currently running class:

~~~java
ClassLoader definingLoader =
        SomeClass.class.getClassLoader();

ClassLoader contextLoader =
        Thread.currentThread().getContextClassLoader();
~~~

The two values can be the same, but they do not have to be.

- **Defining class loader** is tied to a class's identity when the class is defined.
- **TCCL** is a property of a thread and can be changed by code while the thread is running.
- **Class.getClassLoader()** returns the defining loader of the class.
- **Thread.getContextClassLoader()** returns the class loader chosen by the current execution context.

A class loaded by a parent loader may be running on a thread whose TCCL points to a child loader. This is how a framework library defined by a parent loader can collaborate with a plugin located in a child loader.

## 3. Why Is TCCL Needed?

Class loaders commonly use a delegation mechanism: a child loader may ask its parent loader before searching for a class itself. If a library resides in a parent loader, it may not directly see classes loaded exclusively by a child loader.

Illustration:

~~~text
Parent class loader
    |
    +-- GreetingService interface
    +-- Host framework
    |
    v
Plugin class loader (child)
    |
    +-- EnglishGreeting implementation
    +-- META-INF/services/com.example.spi.GreetingService
~~~

The framework knows the **GreetingService** interface, yet the implementation exists in a plugin JAR. If the framework uses only the defining loader of its own framework classes, it may be unable to find resources and implementations sitting under the plugin loader.

TCCL allows the thread to carry a "class context" set by the caller. The framework can use that loader when discovering providers, instead of defaulting solely to the framework's defining loader.

TCCL does not turn the parent class loader into the owner of plugin classes, nor does it create a reverse delegation relationship. It simply provides **a selected ClassLoader object to APIs that know to use TCCL**.

## 4. Which Loader Does `ServiceLoader.load(Service.class)` Use?

The familiar overload:

~~~java
ServiceLoader<GreetingService> loader =
        ServiceLoader.load(GreetingService.class);
~~~

uses the **current thread's context class loader** to perform class-loader-based discovery. You can think of it as equivalent to:

~~~java
ClassLoader context =
        Thread.currentThread().getContextClassLoader();

ServiceLoader<GreetingService> loader =
        ServiceLoader.load(GreetingService.class, context);
~~~

This explains why the same **ServiceLoader.load(...)** call can discover different providers in different environments. The TCCL at the time ServiceLoader is created may have been set by an application server, test runner, plugin manager, or application code.

Important point: ServiceLoader also has a mechanism to discover **named-module providers** declared via JPMS. Therefore, you should not oversimplify it as merely reading `META-INF/services` files. The exact provider scope depends on the ServiceLoader overload, module graph/layer, class loader, and relevant service configuration.

## 5. Important Overloads of ServiceLoader

Three common usages:

~~~java
// 1. Uses the current thread's TCCL.
ServiceLoader<GreetingService> a =
        ServiceLoader.load(GreetingService.class);

// 2. Explicitly specifies a class loader.
ServiceLoader<GreetingService> b =
        ServiceLoader.load(
                GreetingService.class,
                pluginClassLoader
        );

// 3. Discovers service providers in a ModuleLayer.
ServiceLoader<GreetingService> c =
        ServiceLoader.load(
                pluginLayer,
                GreetingService.class
        );
~~~

Comparison:

| Call | Discovery context | Suitable when |
|---|---|---|
| **load(Service.class)** | Thread's context class loader | Frameworks or applications using TCCL |
| **load(Service.class, loader)** | Specified class loader | A plugin manager already knows which loader to use |
| **load(layer, Service.class)** | Specified module layer and parent layers | Plugins are organized as named modules in JPMS |

When an application knows the exact class loader of a plugin, passing the class loader directly is usually clearer than changing TCCL for the whole execution block. If an application manages plugins using ModuleLayer, the layer-based overload is usually more appropriate because it expresses the exact module boundary to search.

## 6. Classpath Provider Example with `META-INF/services`

In traditional SPI organization on the classpath, a provider JAR typically declares a resource named:

~~~text
META-INF/services/com.example.spi.GreetingService
~~~

The file content is the fully qualified name of the provider class:

~~~text
com.example.provider.EnglishGreeting
~~~

Packaged provider JAR:

~~~text
english-greeting.jar
├── META-INF/
│   └── services/
│       └── com.example.spi.GreetingService
└── com/
    └── example/
        └── provider/
            └── EnglishGreeting.class
~~~

The provider class implements **GreetingService**, has a public no-arg constructor in the typical classpath provider model, and is supplied by a class loader that can find both the service resource and that class.

Code to discover providers:

~~~java
ServiceLoader<GreetingService> services =
        ServiceLoader.load(GreetingService.class);

for (GreetingService provider : services) {
    System.out.println(provider.getClass().getName());
}
~~~

For this mechanism to work, TCCL must be able to see the **META-INF/services/** metadata and the implementation class through the corresponding loader's resource/class lookup rules.

The service configuration file must contain the exact class name. If the service provider file is omitted from the JAR during packaging, the provider will not be discovered by that classpath configuration mechanism, even if the **EnglishGreeting** class still exists.

## 7. Example: Loading a Plugin with URLClassLoader

Suppose the application knows the path to an external provider JAR. It can create a separate loader for the plugin:

~~~java
import com.example.spi.GreetingService;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.util.ServiceLoader;

public final class PluginDemo {
    public static void main(String[] args) throws Exception {
        Path pluginJar = Path.of("plugins/english-greeting.jar");
        URL url = pluginJar.toUri().toURL();

        ClassLoader apiLoader =
                GreetingService.class.getClassLoader();

        try (URLClassLoader pluginLoader =
                     new URLClassLoader(
                             new URL[] {url},
                             apiLoader)) {

            ServiceLoader<GreetingService> services =
                    ServiceLoader.load(
                            GreetingService.class,
                            pluginLoader);

            for (GreetingService service : services) {
                System.out.println(service.greet("An"));
            }
        }
    }
}
~~~

In the example:

1. The **GreetingService** class is already visible to the application via the API loader.
2. URLClassLoader has the API loader as its parent.
3. The plugin loader is given the JAR containing the provider.
4. ServiceLoader locates providers with the explicitly passed loader.
5. URLClassLoader is closed with try-with-resources.

Choosing the appropriate parent is crucial. If the plugin loader loads **a different copy** of the GreetingService interface itself, the provider instance may be incompatible with the service type passed by the application to ServiceLoader, even though the class and package names look identical.

Closing URLClassLoader releases the loader's resources; this operation **does not guarantee that all referenced classes/plugin instances will immediately be unloaded**. Unloading also depends on the JVM's ability to reclaim the loader along with all related objects.

## 8. Using TCCL Instead of Passing a Loader Directly

Some frameworks only call the **ServiceLoader.load(Service.class)** overload. If you want that framework to discover providers located in a plugin loader, the caller can set TCCL within a short scope:

~~~java
Thread thread = Thread.currentThread();

ClassLoader previous =
        thread.getContextClassLoader();

try {
    thread.setContextClassLoader(pluginLoader);

    ServiceLoader<GreetingService> services =
            ServiceLoader.load(GreetingService.class);

    for (GreetingService service : services) {
        System.out.println(service.greet("An"));
    }
} finally {
    thread.setContextClassLoader(previous);
}
~~~

Rules to follow:

- **Save the previous TCCL** before replacing it.
- **Restore it in `finally`**, even if the provider throws an error.
- Keep the new TCCL only within the scope where the plugin context is genuinely needed.
- Do not assume the new TCCL automatically propagates to all existing threads.
- Do not leave TCCL changes as permanent state on a thread pool.

This is a common approach for compatibility with framework libraries that depend on TCCL. If you have control over the code calling ServiceLoader and know which class loader to use, the **load(service, loader)** overload avoids side effects on thread context.

## 9. Why Must TCCL Be Restored?

TCCL is mutable state of a Thread. When a thread is reused to handle multiple requests or tasks, a leftover context class loader value can affect subsequent requests.

Example of a thread pool with two plugins:

~~~text
Task A:
  set TCCL -> plugin A
  load services
  (forgot to restore)

Task B on the same worker thread:
  ServiceLoader.load(Service.class)
  still uses TCCL -> plugin A
~~~

Task B might see the wrong provider, miss provider B, or inadvertently retain a reference to class loader A longer than necessary.

Safe pattern:

~~~java
static void withContextLoader(
        ClassLoader desired,
        Runnable action) {

    Thread current = Thread.currentThread();
    ClassLoader previous = current.getContextClassLoader();

    try {
        current.setContextClassLoader(desired);
        action.run();
    } finally {
        current.setContextClassLoader(previous);
    }
}
~~~

Calling it:

~~~java
withContextLoader(pluginLoader, () -> {
    ServiceLoader<GreetingService> loader =
            ServiceLoader.load(GreetingService.class);

    loader.forEach(provider ->
            System.out.println(provider.greet("Mai")));
});
~~~

If the callback throws a RuntimeException, `finally` still restores TCCL. Do not rely on the thread terminating after the callback, because executors commonly reuse threads.

## 10. TCCL in ExecutorService and CompletableFuture

When running asynchronous tasks, you must know **which thread actually invokes ServiceLoader**.

Example:

~~~java
ExecutorService executor =
        java.util.concurrent.Executors.newFixedThreadPool(2);

try {
    Future<?> future = executor.submit(() -> {
        ClassLoader tccl =
                Thread.currentThread().getContextClassLoader();

        System.out.println("Task TCCL = " + tccl);
    });

    future.get();
} finally {
    executor.shutdown();
}
~~~

The thread context loader belongs to the thread executing the task, **not necessarily equal to** the TCCL of the thread that submitted the task. A newly created thread normally inherits the context loader of its creating thread at creation time, but threads in a pool may already exist and be reused.

Therefore, if a task needs its own plugin context, set TCCL **directly inside the task**:

~~~java
Future<?> future = executor.submit(() -> {
    Thread current = Thread.currentThread();
    ClassLoader previous = current.getContextClassLoader();

    try {
        current.setContextClassLoader(pluginLoader);

        ServiceLoader<GreetingService> services =
                ServiceLoader.load(GreetingService.class);

        services.forEach(service ->
                System.out.println(service.greet("Mai")));
    } finally {
        current.setContextClassLoader(previous);
    }
});
~~~

With **CompletableFuture.supplyAsync** or **runAsync**, code may also execute on a thread from another executor. Do not assume the calling thread's TCCL is automatically transferred to the task.

If a framework provides its own context propagation mechanism, understand whether it includes TCCL. TCCL is not a global JVM variable.

## 11. TCCL and Class Identity

A class in the JVM is identified by **(binary name + defining class loader)**. Two different class loaders can define two types with the same name, yet they are not the same class.

Example:

~~~text
Parent loader
    com.example.spi.GreetingService  (Class A)

Another plugin loader
    com.example.spi.GreetingService  (Class B)

A != B
~~~

If a provider implements **Class B**, while the application calls:

~~~java
ServiceLoader.load(ClassA);
~~~

then the provider may not be accepted as an implementation of the service type expected by the application, even though the interface names in source are completely identical.

Rules for classpath plugins:

- The service interface should be supplied from a shared API in a parent loader.
- The plugin loader should delegate to the parent loader for the service contract.
- Do not package a redundant copy of the service API inside each plugin where it could be defined by a separate loader.
- If you catch **ServiceConfigurationError** or **ClassCastException**, check class identity via **getClassLoader()**.

A useful diagnostic:

~~~java
System.out.println(
        GreetingService.class.getClassLoader());

System.out.println(
        provider.getClass().getClassLoader());

System.out.println(
        provider instanceof GreetingService);
~~~

It is normal for a provider class to use a child loader different from the API loader. What matters is that the provider implements the exact **Class object** of the service contract used by the application.

## 12. Named Modules: `uses` and `provides`

In JPMS, a module can declare the service it consumes using **uses**:

~~~java
module com.example.host {
    requires com.example.spi;
    uses com.example.spi.GreetingService;
}
~~~

API module:

~~~java
module com.example.spi {
    exports com.example.spi;
}
~~~

Provider module:

~~~java
module com.example.greeting.en {
    requires com.example.spi;

    provides com.example.spi.GreetingService
        with com.example.greeting.en.EnglishGreeting;
}
~~~

Unlike classpath SPI which relies only on **META-INF/services/**, explicit named modules use the **provides ... with ...** directive to describe providers in the module descriptor.

Rules:

- A module consuming a service must declare **uses ServiceType** when using ServiceLoader in a named module.
- A module providing a service declares **provides ServiceType with ProviderType**.
- The provider class does not have to be in an exported package merely to register a valid provider.
- The provider module and its dependencies must be observable and resolved appropriately for the module graph/layer.
- TCCL does not replace JPMS directives or automatically grant access to unexported packages.

A common mistake is a host module having `requires` on the API module while forgetting `uses`. ServiceLoader may report a configuration error or that the caller is not permitted to use the service when invoked from a named module.

## 13. Does TCCL Replace Module Readability?

No. The two mechanisms belong to two different layers:

- **TCCL** selects the class loader according to the thread's context.
- **JPMS readability** determines which module is allowed to read which module.
- **exports** determines which public API packages are accessible to other modules.
- **opens** determines which packages allow deep reflection.

For example, suppose a host module runs with TCCL pointing to a plugin loader. That does not automatically create:

~~~java
requires com.example.plugin;
~~~

in module-info.java, does not add **--add-reads**, and does not open private packages for framework reflection.

A class can be found by a class loader and still be blocked from access by module, package, or Java access modifier rules. Therefore, when an error occurs, distinguish:

1. Provider/resource not found.
2. Provider found, but class cannot be loaded.
3. Class loaded, but not linked/compatible with the service contract.
4. Class exists, but missing module readability/exports/opens.
5. Instantiating the provider fails.

Each situation requires a different fix.

## 14. ServiceLoader with ModuleLayer

In a modular plugin system, a group of providers can be defined in a separate **ModuleLayer**.

General example:

~~~java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.Set;

ModuleLayer parent = ModuleLayer.boot();

ModuleFinder finder =
        ModuleFinder.of(Path.of("plugins"));

Configuration configuration =
        parent.configuration().resolveAndBind(
                finder,
                ModuleFinder.of(),
                Set.of("com.example.greeting.en")
        );

ModuleLayer pluginLayer =
        parent.defineModulesWithOneLoader(
                configuration,
                ClassLoader.getSystemClassLoader()
        );
~~~

The plugin module must exist in the plugins directory, its required dependencies must be supplied by the finders or parent configuration, and the service API module must be organized so the host and provider use the exact same service type.

After creating the layer:

~~~java
ServiceLoader<GreetingService> services =
        ServiceLoader.load(
                pluginLayer,
                GreetingService.class
        );

for (GreetingService service : services) {
    System.out.println(service.greet("An"));
}
~~~

The **load(ModuleLayer, Service.class)** overload searches for providers in the selected layer and parent layers according to the module service mechanism. This is the explicit approach when an application wants to discover providers in a specific plugin layer.

With a named host module, the host's descriptor still requires **uses com.example.spi.GreetingService**.

Important: **changing TCCL does not automatically create a ModuleLayer** and does not add an arbitrary JAR into that layer. ModuleFinder, Configuration, and layer definition are separate steps.

## 15. Comparing `load(Class)` with `load(ModuleLayer, Class)`

Suppose an application has:

~~~text
Boot layer
  com.example.host
  com.example.spi

Child layer
  com.example.greeting.en
  com.example.greeting.vi
~~~

If the host wants to locate providers in the child layer explicitly:

~~~java
ServiceLoader<GreetingService> loader =
        ServiceLoader.load(childLayer, GreetingService.class);
~~~

This expresses the goal more clearly than merely changing TCCL and hoping the loader in use will discover the right provider modules.

Conversely, if a plugin is just a classpath JAR loaded by URLClassLoader and declares providers via **META-INF/services**, the overload:

~~~java
ServiceLoader.load(GreetingService.class, pluginLoader);
~~~

is usually simple and appropriate.

Do not equate a **classpath plugin class loader** with a **JPMS module layer**. Both can coexist in one architecture, but they are not the same module-management mechanism.

## 16. Lazy Discovery, Caching, and `reload()`

**ServiceLoader** discovers providers lazily as code iterates over its iterator or stream. It caches already-discovered providers according to the behavior of the ServiceLoader instance.

Example:

~~~java
ServiceLoader<GreetingService> loader =
        ServiceLoader.load(GreetingService.class);

for (GreetingService service : loader) {
    System.out.println(service.getClass().getName());
}
~~~

If provider configuration changes and you want ServiceLoader to refresh discovery, the API has a method:

~~~java
loader.reload();
~~~

However, **reload() does not automatically create a new class loader**, does not modify the thread's TCCL, and does not reload bytecode of classes already defined in the same class loader. It clears the ServiceLoader's provider cache so the next iteration re-discovers from the source that instance uses.

If an application needs to replace an already-loaded plugin JAR version, it may have to manage the lifecycle of a separate class loader or module layer, release old references, and create a new configuration. Swapping the JAR file on disk and calling reload does not necessarily cause the JVM to replace already-defined classes.

A ServiceLoader instance is also **not designed for concurrent use from multiple threads without synchronization**. In concurrent systems, manage provider discovery/instantiation at a controlled point, or create independent ServiceLoader instances per context.

## 17. `Provider.type()` and `Provider.get()`

Since Java 9, **ServiceLoader.stream()** returns **ServiceLoader.Provider<S>** handles. Two key operations:

- **type()** returns the Class of the corresponding provider type.
- **get()** obtains a service instance.

Example:

~~~java
ServiceLoader<GreetingService> services =
        ServiceLoader.load(GreetingService.class);

services.stream()
        .filter(provider ->
                provider.type().getName().contains("English"))
        .map(ServiceLoader.Provider::get)
        .forEach(service ->
                System.out.println(service.greet("An")));
~~~

This allows filtering providers based on class metadata before instantiating them. However, **type()** does not guarantee that the provider will instantiate successfully when get() is called.

In a named module with a provider method, the type returned by **type()** may reflect the return type of the provider method, not necessarily the factory class declared in the provides directive.

When a plugin has multiple implementations, do not rely on provider ordering unless the application defines an explicit selection policy itself.

## 18. `ServiceConfigurationError` and How to Diagnose It

ServiceLoader can throw **ServiceConfigurationError** when provider configuration is invalid, a provider class cannot be loaded, is incompatible with the service, or cannot be instantiated.

Example:

~~~java
try {
    ServiceLoader<GreetingService> loader =
            ServiceLoader.load(GreetingService.class);

    for (GreetingService provider : loader) {
        System.out.println(provider.greet("An"));
    }
} catch (java.util.ServiceConfigurationError error) {
    System.err.println(
            "Service discovery failed: " + error.getMessage());
}
~~~

Handle this error at the plugin integration boundary and log sufficient details about the service type, class loader, module, or JAR involved. **ServiceConfigurationError** is an Error, not an ordinary Exception, so a `catch (Exception)` branch will not necessarily catch it.

Do not catch and swallow every Throwable just to ignore a faulty plugin. A framework needs a clear policy: should a provider error fail startup, be isolated, or be logged before moving to another provider?

Common causes:

- Missing **META-INF/services** in a classpath provider JAR.
- Wrong provider class name in the service file.
- Plugin loader cannot see the JAR or resource.
- Plugin loads a different copy of the service API than the one used by the host.
- Consumer named module is missing **uses**.
- Provider named module is missing or misdeclaring **provides**.
- Provider class cannot be instantiated.
- Provider module was not resolved into the searched layer.

## 19. Diagnostic: Printing TCCL, Defining Loader, and Module

A short diagnostic snippet:

~~~java
static void inspectContext(Class<?> serviceType) {
    Thread thread = Thread.currentThread();

    ClassLoader tccl = thread.getContextClassLoader();
    ClassLoader defining = serviceType.getClassLoader();
    Module module = serviceType.getModule();

    System.out.println("Thread: " + thread.getName());
    System.out.println("TCCL: " + tccl);
    System.out.println("Service defining loader: " + defining);
    System.out.println("Service module: " + module.getName());
    System.out.println("Service named: " + module.isNamed());
}
~~~

If a provider has been found:

~~~java
static void inspectProvider(Object provider) {
    Class<?> type = provider.getClass();

    System.out.println("Provider type: " + type.getName());
    System.out.println("Provider loader: " + type.getClassLoader());
    System.out.println("Provider module: "
            + type.getModule().getName());
}
~~~

You may observe:

- TCCL is the plugin's URLClassLoader.
- The service interface uses the application's class loader.
- The provider class uses the child loader.
- The service type or provider type belongs to an unnamed module if it is a classpath class.
- A named module belongs to the boot or a custom module layer.

Do not use **Module.getName()** as the sole condition because an unnamed module returns null. If you need to check the layer, use **Module.getLayer()**, keeping in mind that a module not belonging to a layer may return null.

## 20. When to Choose TCCL, Explicit Loader, or ModuleLayer?

| Context | Preferred approach | Reason |
|---|---|---|
| Simple classpath application | **ServiceLoader.load(Service.class)** | Default TCCL is usually suitable |
| Classpath plugin with its own URLClassLoader | **load(Service.class, pluginLoader)** | Explicit provider source |
| Framework only knows ServiceLoader.load(Service.class) | Set TCCL in try/finally | Compatible with TCCL-dependent APIs |
| Named-module plugin in a child layer | **load(pluginLayer, Service.class)** | Targets the exact layer and its parents |
| Task running in a thread pool | Set/restore TCCL inside the task if needed | Avoids context leaks between tasks |
| Upgrading an already-loaded plugin | Manage loader/layer lifecycle | reload() does not replace loaded classes |

Do not change TCCL as a "cure-all for class loading errors." First, determine whether the plugin is a classpath provider or a named module provider, which loader owns the service API, and which component makes the ServiceLoader call.

## 21. Common Misconceptions

**"ServiceLoader always uses the class loader that defined the service interface."**

Incorrect for the **load(Service.class)** overload: it uses TCCL. To specify a loader explicitly, use the overload taking a ClassLoader. When using named module layers, there is an overload taking a ModuleLayer.

**"Changing TCCL will cause Class.forName(String) to use the new loader."**

You cannot infer that. The **Class.forName(String)** overload uses the caller's loader per API rules, which is not automatically synonymous with TCCL. To specify a loader when loading a class, use the **Class.forName(name, initialize, loader)** overload or the loadClass API on the appropriate loader.

**"A new TCCL makes all modules read each other."**

False. TCCL does not modify requires, exports, opens, or module resolution.

**"A thread pool definitely inherits the task submitter's TCCL."**

False. Pool threads may already be created and reused. Set the context directly inside the task if needed and then restore it.

**"Changing TCCL after creating a ServiceLoader makes the instance switch sources automatically."**

Do not rely on that. When you want a different class loader source, create a new ServiceLoader using the appropriate overload. reload() only refreshes the instance's cache according to its own mechanism.

**"A provider on the classpath only needs to implement the interface."**

Not sufficient for SPI auto-discovery. Classpath providers need properly configured service metadata, a class locatable by the loader, and compatibility with the service contract.

**"Once you have module-info.java, META-INF/services is mandatory."**

With explicit named modules, providers are normally declared using **provides ... with ...** in the module descriptor. This mechanism does not mean you must also create the same META-INF/services file as classpath providers.

**"As soon as a provider is found, you can reflect into any private field."**

False. JPMS continues to enforce opens permissions, module access, and its own reflection rules.

## 22. ServiceLoader Design Checklist in a Plugin System

1. Place the service interface in a shared API with clear class identity.
2. Identify whether the plugin is a classpath JAR, automatic module, or explicit named module.
3. For classpath providers, package **META-INF/services/** accurately.
4. For named modules, declare **uses** in the consumer and **provides ... with ...** in the provider.
5. If using a separate class loader, ensure the plugin loader sees the service API through appropriate parent/delegation.
6. Choose the right ServiceLoader overload for the scope: default TCCL, explicit ClassLoader, or ModuleLayer.
7. If changing TCCL, always save and restore it in `finally`.
8. With executors, set context inside the task instead of assuming inheritance from the submitter.
9. Handle **ServiceConfigurationError** and log the provider's loader/module.
10. Do not rely on provider order without a selection policy.
11. Do not share a ServiceLoader instance unsynchronized across multiple threads.
12. When reloading plugins, understand the limits of **reload()** and manage loader/layer lifecycles.
13. Test all cases: plugin present, plugin absent, and plugin with incompatible dependencies.
14. Inspect the final packaged artifact, because service configuration resources can be stripped from JARs during build/shading.

## 23. Key Takeaways

- **TCCL** is a thread's context class loader, not necessarily the defining loader of the currently executing class.
- **ServiceLoader.load(Service.class)** uses TCCL from the thread context.
- **ServiceLoader.load(Service.class, loader)** lets you select a loader explicitly.
- **ServiceLoader.load(layer, Service.class)** serves discovering providers by ModuleLayer.
- TCCL is useful when a library in a parent loader needs to discover providers located in a child loader.
- Changing TCCL does not alter the module graph or grant exports/opens permissions.
- If using **setContextClassLoader**, restore the old value in **finally**.
- Executor and CompletableFuture do not guarantee each task receives the submitter thread's TCCL.
- The service interface needs the same class identity between host and provider; having the same class name is insufficient if defining loaders differ.
- Classpath SPI relies on **META-INF/services**; named-module SPI relies on **uses** and **provides ... with ...**.
- ServiceLoader has lazy discovery/caching; **reload()** does not by itself swap class loaders or already-loaded classes.
- **ServiceConfigurationError** is an important signal for diagnosing provider metadata, class visibility, and module configuration.

**Conclusion:** use Thread Context Class Loader when you need to pass class/service lookup context across the boundary between a framework and plugins; use ServiceLoader to discover implementations by contract. When combined with JPMS, clearly distinguish **class loader context**, **ModuleLayer**, and **module access rules**. Choosing the right ServiceLoader overload together with a sound thread-management policy makes a plugin system predictable and far less prone to hard-to-reproduce class-loading bugs.
