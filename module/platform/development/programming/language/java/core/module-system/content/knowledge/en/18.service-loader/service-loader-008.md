# Context class loader with service discovery

## 1. What is the context class loader?

Every Java class is defined by a class loader. You can check the loader that defined a class using **Class.getClassLoader()**. However, a thread also has its own contextual loader, called the **context class loader (TCCL)**, obtained via **Thread.currentThread().getContextClassLoader()**.

    ClassLoader definingLoader = Codec.class.getClassLoader();
    ClassLoader contextLoader =
            Thread.currentThread().getContextClassLoader();

These two loaders may be the same or different:

- **Defining class loader** is the loader that loaded and defined a specific class. A class's identity in the JVM depends on its binary name and its defining loader.
- **Context class loader** is the loader attached to a thread so code running on that thread can use it when looking up classes or resources. It is a context passed down to libraries and frameworks.

TCCL solves a common scenario: a library loaded by a framework's loader needs to find implementations supplied by an application or plugin. If the library only uses the loader that defined itself, that loader may not be able to see classes inside the application's loading scope. TCCL allows the thread to carry the loader appropriate for the application performing the work.

TCCL is read and modified via:

    Thread thread = Thread.currentThread();
    ClassLoader loader = thread.getContextClassLoader();

    thread.setContextClassLoader(loader);

When a new thread is created, its initial context class loader is typically inherited from the parent thread at thread creation time. Therefore, this value can differ across threads. With thread pools, worker threads may have been created long ago and continue holding an old context loader unless the application manages it explicitly.

## 2. Why does ServiceLoader use the context class loader?

**ServiceLoader** is Java's standard mechanism for finding and creating implementations of a service without forcing the application to depend directly on implementation classes.

A service is typically an interface or an abstract class. For example:

    package com.example.codec;

    public interface Codec {
        String name();
        byte[] encode(String input);
    }

A library only needs to know the **Codec** type. Other modules or JARs can provide implementations such as **JsonCodec** or **XmlCodec**. The application requests providers through ServiceLoader:

    ServiceLoader<Codec> codecs =
            ServiceLoader.load(Codec.class);

    for (Codec codec : codecs) {
        System.out.println(codec.name());
    }

The **ServiceLoader.load(Class)** overload uses the current thread's context class loader. At the API level, the call:

    ServiceLoader.load(Codec.class);

is equivalent to:

    ServiceLoader.load(
            Codec.class,
            Thread.currentThread().getContextClassLoader());

This is why TCCL frequently appears in service discovery. A library can call ServiceLoader without knowing each application's specific loader. The thread already carries the context loader set by the runtime environment or application; ServiceLoader uses that loader as the starting point to locate providers.

TCCL only affects APIs that actually use it. Changing TCCL does not alter the defining loader of existing classes and does not automatically change all class-loading operations in the JVM.

## 3. Service discovery on the classpath

When providers are packaged as JARs on the classpath, ServiceLoader identifies providers via configuration files in the **META-INF/services** directory.

The file name is the fully qualified binary name of the service. For the service **com.example.codec.Codec**, the provider JAR contains the file:

    META-INF/services/com.example.codec.Codec

The file contents list the fully qualified binary names of the providers, one provider per line:

    com.example.codec.json.JsonCodec
    com.example.codec.xml.XmlCodec

The file is UTF-8 encoded. Blank lines and whitespace around provider names are ignored; the **#** character begins a comment on a line. Duplicate providers are ignored.

When **ServiceLoader.load(Codec.class)** is called, TCCL is used to locate service configuration resources and load the listed provider classes. Providers must be visible from the loader used for discovery. Therefore, having a META-INF/services file inside a JAR is not enough to guarantee provider discovery: that JAR and the provider class must be within the scope accessible to the loader.

You can pass a loader explicitly when the application already knows which loader to use:

    ClassLoader pluginLoader = getPluginClassLoader();

    ServiceLoader<Codec> codecs =
            ServiceLoader.load(Codec.class, pluginLoader);

This makes the discovery scope explicit and independent of the thread's implicit TCCL value.

## 4. Service discovery on the module path with JPMS

When providers are packaged in named modules, service metadata resides in **module-info.java** rather than relying on META-INF/services files.

The module containing the service exports the service type:

    module com.example.codec.api {
        exports com.example.codec;
    }

The application module declares that it uses the service:

    module com.example.application {
        requires com.example.codec.api;
        uses com.example.codec.Codec;
    }

The module supplying the implementation declares the provider:

    module com.example.codec.json {
        requires com.example.codec.api;

        provides com.example.codec.Codec
            with com.example.codec.json.JsonCodec;
    }

The **uses** directive indicates that the application module needs to discover providers for the service. If the caller is in an explicit named module whose module descriptor does not declare uses for the service, the corresponding load methods may throw **ServiceConfigurationError**.

The **provides ... with ...** directive registers the provider with JPMS. The package containing the implementation generally does not need to be exported to the consuming application; the application works through the public service type. This allows the provider module to keep implementation details private.

ServiceLoader supports both providers on the classpath and providers in named modules. With the overload accepting a class loader, discovery examines providers in named modules associated with the loader and its parent loaders, and then examines providers in unnamed modules through service configuration files found by the loader. If a loader belongs to a module layer, discovering named module providers can include modules in that layer, even modules defined by another loader in the same layer.

When the application wants to specify the exact module layer to search, use:

    ModuleLayer pluginLayer = ...;

    ServiceLoader<Codec> codecs =
            ServiceLoader.load(pluginLayer, Codec.class);

This overload searches for providers in the specified module layer and its parent layers. It does not search for providers in unnamed modules. This is a clean choice for plugin systems that create dynamic module layers and need to restrict discovery by layer.

## 5. Choosing the right ServiceLoader overload

| API | Discovery scope | When to use |
|---|---|---|
| **ServiceLoader.load(service)** | Uses the current TCCL as the starting loader to find providers | Libraries or frameworks that want to respect the application's context loader |
| **ServiceLoader.load(service, loader)** | Uses the passed loader to find providers in named and unnamed modules accessible to that loader | Applications that know the exact plugin loader to use |
| **ServiceLoader.load(layer, service)** | Finds providers in named modules belonging to the layer and its parent layers; does not search unnamed modules | Applications managing their own module layers |
| **ServiceLoader.loadInstalled(service)** | Uses the platform class loader | Only wanting providers installed at the platform level |

Do not pick an overload merely out of habit. Identify whether providers are deployed on the classpath, module path, or a dynamic module layer, then choose the loader or layer that expresses the exact intended scope.

**loadInstalled** is not a general replacement for **load**. It uses the platform class loader, so providers present only on the application classpath or application module path will not be discovered through this overload.

## 6. Setting TCCL in a controlled manner

A framework sometimes needs to set TCCL to an application or plugin loader while running a block of code. Save the old value and restore it in a **finally** block:

    Thread thread = Thread.currentThread();
    ClassLoader previous = thread.getContextClassLoader();

    try {
        thread.setContextClassLoader(pluginLoader);

        ServiceLoader<Codec> codecs =
                ServiceLoader.load(Codec.class);

        for (Codec codec : codecs) {
            System.out.println(codec.name());
        }
    } finally {
        thread.setContextClassLoader(previous);
    }

Restoring is especially important when using thread pools. Worker threads are reused across many tasks; if a task leaves a plugin's TCCL behind, the next task may discover the wrong providers or hold a reference to the old loader. That reference can also retain the plugin's class loader and classes, making plugin unloading or memory reclamation difficult.

If only a single service discovery call is needed, passing an explicit loader is usually simpler than mutating TCCL:

    ServiceLoader<Codec> codecs =
            ServiceLoader.load(Codec.class, pluginLoader);

Only change TCCL when called code or a framework needs to read the context loader from the thread. Do not set TCCL to a plugin loader and forget to restore it.

A child thread's initial TCCL is usually inherited at the time the thread is created. This means threads created before the application changes TCCL may not carry the new loader. With executors or thread pools, establish who is responsible for setting and restoring the loader for each task.

## 7. Discovery is lazy and providers are cached

Creating a **ServiceLoader** does not mean all providers have been loaded and instantiated. Providers are discovered, loaded, and instantiated on demand as the application iterates **iterator()** or processes **stream()**.

    ServiceLoader<Codec> codecs =
            ServiceLoader.load(Codec.class);

    for (Codec codec : codecs) {
        // The provider is instantiated when the iterator reaches that provider.
        System.out.println(codec.name());
    }

If you only want to inspect provider type information before creating instances, you can use **stream()** and **ServiceLoader.Provider**:

    ServiceLoader.load(Codec.class)
            .stream()
            .map(provider -> provider.type().getName())
            .forEach(System.out::println);

Calling **Provider.type()** lets you view the provider class without needing to obtain an instance. Calling **Provider.get()** obtains the instance from the provider.

A ServiceLoader caches loaded providers. Subsequent iterations use cached providers first before continuing to search for remaining providers. Call **reload()** to clear the cache and allow providers to be loaded again:

    codecs.reload();

A ServiceLoader is created with the loader active at the time **load** is called. Changing TCCL afterward does not automatically switch an existing ServiceLoader to the new loader. If discovery against a new loader is needed, create a new ServiceLoader using the appropriate overload.

## 8. Common errors during service discovery

### Provider not found

Check the following points:

- Is the thread's TCCL the loader the application expects?
- Is the provider JAR within the search scope of the loader?
- Does the **META-INF/services** file have the exact service name and location?
- Is the provider name in the file the fully qualified binary name, and is the class visible to the loader?
- For named modules, does the provider module declare **provides** for the right service?
- Is the module layer containing the provider within the discovery scope?
- Has the caller in an explicit named module declared **uses**?

You can print loader details for diagnosis:

    Thread thread = Thread.currentThread();

    System.out.println("Thread: " + thread.getName());
    System.out.println("Context loader: "
            + thread.getContextClassLoader());
    System.out.println("Service loader: "
            + Codec.class.getClassLoader());
    System.out.println("Service module: "
            + Codec.class.getModule());

### Provider incompatible with service type

The service type and provider must be compatible in runtime type identity. If the application and a plugin load two copies of the **Codec** interface via two independent loaders, the JVM may treat them as two different types even though their package and class names are identical.

In that case, the provider may not be recognized as an implementation of the service the application uses, or type-related errors may arise when loading and using the provider. Place the shared service API in a loader/module shared between the host and plugins; avoid packaging an independent copy of that API inside each plugin.

### ServiceConfigurationError

**ServiceConfigurationError** can occur when ServiceLoader cannot read configuration, cannot load a provider, a provider is incompatible with the service, a valid constructor/provider method is missing, or provider creation fails. For explicit named modules, a missing **uses** directive is also a cause to check.

Errors can occur while iterating the iterator, including at **hasNext()** or **next()**, or when performing stream operations that cause providers to be located or loaded. Because the process is lazy, do not merely check that creating the ServiceLoader succeeded and conclude discovery worked.

### Sharing a ServiceLoader across multiple threads

**ServiceLoader** instances are not safe for concurrent use by multiple threads. Do not share a single mutable instance across multiple threads without synchronization. Typically, create a dedicated loader scoped to the task or synchronize explicitly if sharing is required.

### Caching ServiceLoader across the whole JVM

Do not cache a ServiceLoader created with **ServiceLoader.load(service)** globally across the JVM when the environment hosts multiple applications or plugins. Each thread may have a different TCCL; providers found in one application's context may be inappropriate for another application. Such caching can also retain references to plugin class loaders and cause memory leaks.

## 9. Quick diagnostic workflow

When service discovery fails to find a provider or finds the wrong provider, check step by step:

1. Identify the service type being used: call **Codec.class.getModule()** and **Codec.class.getClassLoader()**.
2. Identify the TCCL on the exact thread making the call: **Thread.currentThread().getContextClassLoader()**.
3. Identify the ServiceLoader overload: default using TCCL, explicit loader passed, or module layer specified.
4. Check how the provider is deployed: a META-INF/services file on the classpath or a provides directive in a module descriptor.
5. For named modules, check **uses**, **provides**, the module path, and module layers.
6. Check whether the service interface has been loaded as multiple copies by different loaders.
7. Iterate the iterator or stream and record any actual **ServiceConfigurationError**; discovery is lazy, so errors may appear only during iteration.

## 10. Key takeaways

- TCCL is a thread's contextual loader; defining loader is the loader that defined a class. The two values may differ.
- **ServiceLoader.load(service)** uses the current thread's TCCL.
- **ServiceLoader.load(service, loader)** uses the specified loader, suitable when you want explicit control over the provider search scope.
- **ServiceLoader.load(layer, service)** searches providers in the module layer and its parent layers, not in unnamed modules.
- Providers on the classpath are declared with **META-INF/services/**; providers in named modules are declared with **provides** and the consumer module declares **uses**.
- TCCL does not grant JPMS permissions and does not alter the identity of already loaded classes.
- Restore TCCL in **finally**, especially when using thread pools or plugins.
- ServiceLoader loads providers lazily, caches loaded providers, and is not safe for concurrent shared use across threads.
- When a provider is not found, check the loader, module layer, service configuration, and service class identity before changing runtime configuration.

**The context class loader is the bridge that lets a library discover implementations supplied by an application or plugin.** When combined with ServiceLoader, choose the right loader or module layer and manage its lifecycle per thread or task.

## References

- Java SE 21 API — ServiceLoader: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ServiceLoader.html
- Java SE 21 API — Thread: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html