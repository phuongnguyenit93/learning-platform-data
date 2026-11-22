# ServiceLoader.load from the caller module

> Scope: Java Platform Module System (JPMS, since Java 9). This lesson explains which module must declare **uses** when calling **ServiceLoader.load**, and how that relates to discovering providers at runtime.

## Objectives

After this lesson, you will be able to:

- Correctly identify the **caller module** of a **ServiceLoader.load** call.
- Place **uses**, **requires**, and **provides** in the right module descriptors.
- Distinguish between the caller module, the module containing the service API, the module containing the provider, and the thread context class loader.
- Explain why an application does not need to depend directly on the provider module.
- Choose the appropriate **ServiceLoader.load** overload and diagnose **ServiceConfigurationError** issues.

## 1. Which module is the caller module?

The **caller module** is the module containing the code that directly invokes **ServiceLoader.load**. The JVM determines this module implicitly when the method is called; you do not pass the caller module as a parameter.

Example:

~~~java
ServiceLoader<GreetingService> loader =
        ServiceLoader.load(GreetingService.class);
~~~

If the code above resides in the **com.acme.app** module, then **com.acme.app** is the caller module. The caller module is not automatically:

- the module declaring the **GreetingService** interface;
- the module implementing **GreetingService**;
- the module of the thread context class loader.

These concepts serve different roles:

| Component | Role |
|---|---|
| Caller module | The module that must be permitted to use the service; this is where **uses** is declared. |
| Service module | The module containing the service type; the caller needs to read this type, typically via **requires** and **exports**. |
| Provider module | The module registering an implementation with **provides ... with ...**. |
| Thread context class loader (TCCL) | The starting point for **ServiceLoader.load(service)** to search for providers. |

Key point: **the caller module determines the uses check; the TCCL determines the class loader scope where provider lookup begins.** Do not conflate these two concepts into one.

## 2. How does ServiceLoader.load(Class<S>) work?

The call:

~~~java
ServiceLoader.load(GreetingService.class);
~~~

is equivalent to:

~~~java
ServiceLoader.load(
        GreetingService.class,
        Thread.currentThread().getContextClassLoader()
);
~~~

Therefore, the single-argument overload uses the current thread's TCCL. The overload accepting a **ClassLoader** lets you specify a loader explicitly:

~~~java
ClassLoader loader = Thread.currentThread().getContextClassLoader();

ServiceLoader<GreetingService> services =
        ServiceLoader.load(GreetingService.class, loader);
~~~

Both overloads perform a service-usage permission check based on the caller module. If the caller is in an **explicit named module**, the caller's module descriptor must declare **uses** for the service. If the service type is not accessible from the caller, or if the caller is an explicit module lacking **uses**, the call can throw **ServiceConfigurationError**.

**ServiceLoader.load** creates the loader object; providers are located and instantiated lazily when you iterate with **iterator()**, use **stream()**, or call an equivalent operation. Consequently, provider errors may appear during iteration, after the **load** call has already returned.

## 3. Placing requires, uses, and provides in the right places

Suppose there are three modules:

- **com.acme.spi**: publishes the service API.
- **com.acme.provider**: supplies the implementation.
- **com.acme.app**: calls **ServiceLoader.load** to use the service.

### Module containing the service API

**module-info.java** of **com.acme.spi**:

~~~java
module com.acme.spi {
    exports com.acme.spi;
}
~~~

Service interface:

~~~java
package com.acme.spi;

public interface GreetingService {
    String greet(String name);
}
~~~

The package containing the interface must be exported so that the application module can reference the **GreetingService** type.

### Module calling ServiceLoader.load

**module-info.java** of **com.acme.app**:

~~~java
module com.acme.app {
    requires com.acme.spi;
    uses com.acme.spi.GreetingService;
}
~~~

The two directives have distinct purposes:

- **requires com.acme.spi** allows code in the app to read and use the service type exported from the SPI module.
- **uses com.acme.spi.GreetingService** declares that the app looks up providers for this service via **ServiceLoader**.

**uses must reside in the module that directly calls ServiceLoader.load.** If the code calling the API lives in a utility module, such as **com.acme.bootstrap**, then **uses** must be declared in **com.acme.bootstrap**. Having the application module call a wrapper function does not transfer the **uses** declaration privilege to the application.

### Module supplying the implementation

**module-info.java** of **com.acme.provider**:

~~~java
module com.acme.provider {
    requires com.acme.spi;

    provides com.acme.spi.GreetingService
        with com.acme.provider.EnglishGreetingService;
}
~~~

Implementation:

~~~java
package com.acme.provider;

import com.acme.spi.GreetingService;

public final class EnglishGreetingService implements GreetingService {

    public EnglishGreetingService() {
    }

    @Override
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

The provider module needs to read the service API, so it declares **requires com.acme.spi**. The **provides ... with ...** directive registers the implementation for the service. In this example, the provider has a public no-argument constructor.

The **com.acme.provider** package does not need to be exported solely for **ServiceLoader** to use a provider declared with **provides**. Only the package containing the service API needs to be exported to the caller.

A provider in a named module can also declare a public static no-argument method named **provider**, returning a type compatible with the service. When using that provider method, the provider class itself is not required to implement the service interface; without a provider method, the provider class must satisfy ServiceLoader's constructor rules.

### Why doesn't the app require com.acme.provider?

The app only depends on the **GreetingService** abstraction. Providers are discovered through the module system's service binding mechanism and ServiceLoader. When a resolved module uses a service, resolution can bring corresponding provider modules on the module path into the module graph.

Thus, the app typically only needs to **requires** the module containing the service API and declare **uses** for the service. If the app declares **requires com.acme.provider**, the app becomes directly dependent on a concrete implementation and loses part of the benefit of independently replaceable providers.

## 4. Complete usage example

In module **com.acme.app**, class **Main** can iterate through all providers:

~~~java
package com.acme.app;

import com.acme.spi.GreetingService;
import java.util.ServiceLoader;

public final class Main {

    public static void main(String[] args) {
        ServiceLoader<GreetingService> services =
                ServiceLoader.load(GreetingService.class);

        for (GreetingService service : services) {
            System.out.println(service.greet("Lan"));
        }
    }
}
~~~

A simple source layout:

~~~text
src/
├── com.acme.spi/
│   ├── module-info.java
│   └── com/acme/spi/GreetingService.java
├── com.acme.provider/
│   ├── module-info.java
│   └── com/acme/provider/EnglishGreetingService.java
└── com.acme.app/
    ├── module-info.java
    └── com/acme/app/Main.java
~~~

Compile the modules:

~~~bash
javac --module-source-path src -d out \
  -m com.acme.spi,com.acme.provider,com.acme.app
~~~

Run the application:

~~~bash
java --module-path out \
  -m com.acme.app/com.acme.app.Main
~~~

When service binding is performed during module resolution, a provider module declaring **provides** for a service that the app declares with **uses** can be added to the module graph without the app directly declaring **requires** on that provider.

Output with the provider above:

~~~text
Hello, Lan!
~~~

## 5. Provider search scope: class loaders and module layers

The caller module and where providers are searched are two separate axes.

### load(service)

~~~java
ServiceLoader.load(GreetingService.class);
~~~

Uses the current thread's TCCL as the starting class loader for discovery. The provider lookup mechanism can consider providers in named modules and unnamed modules visible to that loader, including parent delegation relationships.

If the application runs in a container, application server, or plugin environment, the TCCL may differ from the class loader of the calling class. When a provider is not found, check the TCCL on the exact thread making the call.

### load(service, classLoader)

~~~java
ServiceLoader.load(GreetingService.class, pluginClassLoader);
~~~

Uses the passed-in class loader as the starting point for locating providers. The **uses** check is still based on the caller module.

### load(moduleLayer, service)

~~~java
ServiceLoader<GreetingService> services =
        ServiceLoader.load(pluginLayer, GreetingService.class);
~~~

Used when providers reside in a specific module layer, such as a layer created specifically for plugins. This method searches for providers in the specified layer and its parent layers; it does not search for providers in unnamed modules.

The **ModuleLayer** overload also applies service accessibility and **uses** checks against the caller module. If using a plugin layer, ensure that the provider module actually belongs to that layer or an appropriate parent layer.

### loadInstalled(service)

~~~java
ServiceLoader.loadInstalled(GreetingService.class);
~~~

Uses the platform class loader. This method targets providers installed in the runtime; providers located only on the application module path or classpath will not be discovered the usual way as with **load(service)**.

## 6. If the provider is on the classpath

ServiceLoader still supports providers using the traditional classpath mechanism. The provider JAR contains the file:

~~~text
META-INF/services/com.acme.spi.GreetingService
~~~

The file lists the fully qualified names of the provider classes, one name per line:

~~~text
com.acme.provider.EnglishGreetingService
~~~

When an application runs on the classpath, the code typically belongs to an unnamed module and therefore has no **module-info.java** to declare **uses**. For applications running in an explicit named module, use **uses** as shown in the previous sections.

Do not confuse the two registration mechanisms:

- Named module: declare **provides ... with ...** in **module-info.java**.
- Classpath: declare provider classes in **META-INF/services/<fully-qualified-service-name>**.

## 7. Common errors and root cause analysis

| Symptom | Common cause | How to resolve |
|---|---|---|
| **ServiceConfigurationError** right at **load** | Caller is an explicit module missing **uses**, or the service type is inaccessible | Identify the module directly calling **load**; add **uses**; check **requires** and **exports** for the service API |
| No provider found | Provider module not resolved, provider outside the loader/layer scope, or missing **provides** | Check the module path, module graph, **provides**, and TCCL/layer |
| Error while iterating **ServiceLoader** | Provider class cannot be loaded, invalid provider declaration, invalid constructor/provider method, or provider instantiation fails | Read the full cause of **ServiceConfigurationError**; inspect the class and provider declaration |
| App has **uses** but still fails | **uses** is in the app module, while another module is the one directly calling **ServiceLoader.load** | Move **uses** to the module containing the direct call |
| App ends up depending on a concrete implementation | App declares **requires** on the provider module | Have the app depend on the service API; register the implementation with **provides** in the provider module |
| Works on one thread but cannot find provider on another | TCCL differs across threads | Check **Thread.currentThread().getContextClassLoader()** at the call site; consider passing an explicit loader |

A practical debugging sequence:

1. Find the exact line calling **ServiceLoader.load**.
2. Identify the module containing the class making that call.
3. If it is an explicit named module, verify the module descriptor has **uses** for the right service type.
4. Confirm the caller can read the service type: the module containing the service exports the package and the caller has an appropriate **requires**.
5. Check that the provider module has **provides ... with ...**, is present on the module path, and is resolved into the target module layer.
6. Check the TCCL if using the **load(service)** or **load(service, loader)** overloads.
7. Iterate the loader to observe errors occurring during provider discovery, loading, and instantiation.

## 8. Key points to remember

- **uses** belongs to the caller module — the module directly calling **ServiceLoader.load**.
- **requires** allows the caller to use the service API; **exports** publishes the package containing the service API.
- **provides ... with ...** belongs to the provider module and registers the implementation.
- The caller module is not synonymous with the service module, provider module, or the TCCL's module.
- **ServiceLoader.load(service)** uses the TCCL; **ServiceLoader.load(layer, service)** searches in the module layer and its parent layers.
- **load** returns a loader; providers are processed lazily during iteration.
- You do not need the consumer to **requires** each provider module if you want to preserve a replaceable service provider architecture.

A note on lifecycle: ServiceLoader is not designed for concurrent shared use across multiple threads. Nor should this loader be cached arbitrarily across the entire JVM, because different applications may have different TCCLs and a global cache could retain class loaders longer than expected.

## References

- [ServiceLoader — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ServiceLoader.html)
- [Java Language Specification — Module Declarations, Service Consumption, and Service Provision](https://docs.oracle.com/javase/specs/jls/se21/html/jls-7.html#jls-7.7)
- [Decoupling Modules with Services — Dev.java](https://dev.java/learn/organizing/modules/services/)
