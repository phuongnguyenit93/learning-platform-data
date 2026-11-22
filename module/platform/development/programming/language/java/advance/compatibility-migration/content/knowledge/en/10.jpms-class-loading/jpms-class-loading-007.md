# ServiceLoader and `uses` or `provides` declarations

When a Java application needs to support multiple implementations for the same functionality, directly calling `new` on a concrete class quickly creates tight coupling. For example, a report-exporting application may need to add PDF, CSV, or JSON exporters; a payment system may integrate multiple payment gateways; a library may allow users to install additional plugins without recompiling business code.

`java.util.ServiceLoader` provides a mechanism for discovering implementations (*service providers*) under a common contract (*service*). With the Java Platform Module System (JPMS), this contract is further described in `module-info.java` using two directives:

- `uses`: the **consuming** module wants to find providers of a service.
- `provides ... with ...`: the **providing** module registers the class or factory implementing that service.

Using `ServiceLoader`, `uses`, and `provides` properly helps a system gradually migrate from the classpath to the module path, maintain clear module boundaries, and avoid requiring the consumer to depend directly on every implementation.

## 1. Roles in the Service Provider Interface mechanism

A system using ServiceLoader typically has three components:

| Component | Role | Example |
|---|---|---|
| Service API/SPI | Declares the interface or abstract class that providers must satisfy. | `GreetingService` |
| Service provider | Implements the service using a specific technology or processing approach. | `EnglishGreetingService`, `VietnameseGreetingService` |
| Service consumer | Finds, selects, and uses one or more providers. | The `com.example.greeting.app` application |

The typically desired dependency path:

```text
                 +---------------------------+
                 |      Service API/SPI      |
                 |      GreetingService      |
                 +---------------------------+
                      ^                ^
                      |                |
             implements/uses          uses
                      |                |
           +----------------+  +----------------+
           | Provider module|  | Consumer module|
           | English / Vi   |  | Main / business|
           +----------------+  +----------------+
                      ^                |
                      |                |
                      +--ServiceLoader-+
                         discovery
```

The consumer knows the service type but does not need `new EnglishGreetingService()` or to directly declare a dependency on the provider's module. The provider also does not have to know which specific consumer will use it.

**Distinction:** `ServiceLoader` is a mechanism for finding and instantiating providers. It does not define interfaces itself, does not automatically choose the best provider according to business rules, does not guarantee that every module on disk is loaded, and does not automatically update all running plugins.

## 2. How do `uses` and `provides` differ from `requires`?

In `module-info.java`, these directives have independent meanings:

```java
module com.example.greeting.app {
    requires com.example.greeting.api;
    uses com.example.greeting.api.GreetingService;
}
```

- `requires com.example.greeting.api` creates a module readability relationship so that the consumer can reference the `GreetingService` type.
- `uses com.example.greeting.api.GreetingService` declares that the consumer uses service discovery for that type.

On the provider side:

```java
module com.example.greeting.provider.en {
    requires com.example.greeting.api;
    provides com.example.greeting.api.GreetingService
        with com.example.greeting.provider.en.EnglishGreetingService;
}
```

- `requires` allows the provider to reference the service API.
- `provides ... with ...` registers the provider with JPMS.
- It is not necessary to `exports` the implementation package just for ServiceLoader to instantiate the provider.

| Directive | Which module declares it? | Purpose |
|---|---|---|
| `requires api.module` | Consumer and provider, if they need to use an API in another module. | Allows reading the module containing the service type. |
| `exports api.package` | Module containing the service API. | Allows other modules to use the public service type. |
| `uses api.Service` | Module calling ServiceLoader to find the service. | Announces the need to consume a service. |
| `provides api.Service with impl.Provider` | Module containing the provider. | Registers a provider that can be discovered by ServiceLoader. |
| `opens implementation.package` | Only when there are other deep reflection requirements. | Not a mandatory requirement for ServiceLoader to use `provides`. |

A `uses` directive does not specify a concrete provider; a `provides` directive does not create an explicit dependency relationship from the application to the provider. These are the two core ideas behind a pluggable architecture.

## 3. Complete example with three roles and multiple providers

The example consists of four named modules: one module publishing the service, two modules providing implementations, and one consuming module.

### 3.1. Directory structure

```text
src/
├── com.example.greeting.api/
│   ├── module-info.java
│   └── com/example/greeting/api/GreetingService.java
├── com.example.greeting.provider.en/
│   ├── module-info.java
│   └── com/example/greeting/provider/en/EnglishGreetingService.java
├── com.example.greeting.provider.vi/
│   ├── module-info.java
│   └── com/example/greeting/provider/vi/VietnameseGreetingService.java
└── com.example.greeting.app/
    ├── module-info.java
    └── com/example/greeting/app/Main.java
```

Each directory directly under `src` has a name matching the module name. This structure is compatible with how `javac --module-source-path` is used in the example.

### 3.2. Declaring the Service API

File `src/com.example.greeting.api/module-info.java`:

```java
module com.example.greeting.api {
    exports com.example.greeting.api;
}
```

File `src/com.example.greeting.api/com/example/greeting/api/GreetingService.java`:

```java
package com.example.greeting.api;

public interface GreetingService {
    String languageTag();
    String greet(String person);
}
```

`GreetingService` is the service type that providers will implement. The package containing the interface is exported via `exports` so that consumers and providers can use it.

### 3.3. English provider

File `src/com.example.greeting.provider.en/module-info.java`:

```java
module com.example.greeting.provider.en {
    requires com.example.greeting.api;

    provides com.example.greeting.api.GreetingService
        with com.example.greeting.provider.en.EnglishGreetingService;
}
```

File `src/com.example.greeting.provider.en/com/example/greeting/provider/en/EnglishGreetingService.java`:

```java
package com.example.greeting.provider.en;

import com.example.greeting.api.GreetingService;

public final class EnglishGreetingService implements GreetingService {
    public EnglishGreetingService() {
    }

    @Override
    public String languageTag() {
        return "en";
    }

    @Override
    public String greet(String person) {
        return "Hello, " + person + "!";
    }
}
```

The class has a `public` no-argument constructor so ServiceLoader can create an instance via the constructor-based provider mechanism. The fully qualified name after `with` must be a provider type residing in the providing module itself, according to JPMS's `provides` rules.

Notice that the provider's `module-info.java` **does not have** `exports com.example.greeting.provider.en`. That is still valid: ServiceLoader uses the module's service registration mechanism, without requiring the entire implementation to become a public API.

### 3.4. Vietnamese provider

File `src/com.example.greeting.provider.vi/module-info.java`:

```java
module com.example.greeting.provider.vi {
    requires com.example.greeting.api;

    provides com.example.greeting.api.GreetingService
        with com.example.greeting.provider.vi.VietnameseGreetingService;
}
```

File `src/com.example.greeting.provider.vi/com/example/greeting/provider/vi/VietnameseGreetingService.java`:

```java
package com.example.greeting.provider.vi;

import com.example.greeting.api.GreetingService;

public final class VietnameseGreetingService implements GreetingService {
    public VietnameseGreetingService() {
    }

    @Override
    public String languageTag() {
        return "vi";
    }

    @Override
    public String greet(String person) {
        return "Xin chào, " + person + "!";
    }
}
```

The two providers implement the same service interface. The consumer can select a provider by `languageTag()` without knowing the implementing class name.

### 3.5. Consumer declaring `uses`

File `src/com.example.greeting.app/module-info.java`:

```java
module com.example.greeting.app {
    requires com.example.greeting.api;
    uses com.example.greeting.api.GreetingService;
}
```

File `src/com.example.greeting.app/com/example/greeting/app/Main.java`:

```java
package com.example.greeting.app;

import com.example.greeting.api.GreetingService;
import java.util.ServiceLoader;

public final class Main {
    public static void main(String[] args) {
        String desiredLanguage = args.length == 0 ? "vi" : args[0];

        GreetingService selected = null;
        for (GreetingService candidate :
                ServiceLoader.load(GreetingService.class)) {
            if (desiredLanguage.equals(candidate.languageTag())) {
                selected = candidate;
                break;
            }
        }

        if (selected == null) {
            throw new IllegalStateException(
                    "No greeting provider for: " + desiredLanguage);
        }

        System.out.println(selected.greet("Java"));
    }
}
```

The consumer depends directly on `com.example.greeting.api`. It neither imports `EnglishGreetingService` or `VietnameseGreetingService`, nor adds `requires` for the two provider modules.

### 3.6. Compiling

In the directory containing `src`, using JDK 9 or newer:

```bash
javac --module-source-path src -d mods \
  -m com.example.greeting.api,com.example.greeting.provider.en,com.example.greeting.provider.vi,com.example.greeting.app
```

On Windows PowerShell, the same command can be written on a single line:

```powershell
javac --module-source-path src -d mods -m com.example.greeting.api,com.example.greeting.provider.en,com.example.greeting.provider.vi,com.example.greeting.app
```

The command creates class files in the module directories under `mods`. If the system uses Maven or Gradle, equivalent configuration is needed to compile each module with the proper module path.

### 3.7. Running the application

```bash
java --module-path mods \
  --add-modules com.example.greeting.provider.en,com.example.greeting.provider.vi \
  --module com.example.greeting.app/com.example.greeting.app.Main vi
```

Expected output:

```text
Xin chào, Java!
```

When replacing `vi` with `en`, the application will print:

```text
Hello, Java!
```

Here, `--add-modules` explicitly adds the two provider modules into the resolved module configuration. In an environment with service binding in the module resolver, providers can also be brought into the graph through the `uses`/`provides` relationship. With a custom runtime or layer creation approach, you must ensure the provider modules are actually in the **resolved module graph**; merely placing JAR files on the module path is not proof that every provider will be loaded.

## 4. Rules for `uses`

The `uses` directive has the form:

```java
uses com.example.greeting.api.GreetingService;
```

It must be located in the `module-info.java` of the **explicit named module** containing the code that consumes the service via ServiceLoader. Another module declaring `uses` does not automatically substitute for the module that actually invokes ServiceLoader.

For example, if the `com.example.plugin.manager` module contains the method:

```java
public ServiceLoader<GreetingService> discover() {
    return ServiceLoader.load(GreetingService.class);
}
```

then `com.example.plugin.manager` must have `uses com.example.greeting.api.GreetingService;` in its own descriptor if it is an explicit named module. Having the application call `discover()` from outside does not remove the declaration requirement of the module performing the `ServiceLoader.load` call.

Related rules:

- The service type must be accessible from the module declaring `uses`.
- If the service interface is in another module, it is usually necessary to `requires` the module containing the service, and that module must `exports` the appropriate package.
- Do not repeat the same service across multiple `uses` directives within one module.
- `uses` declares a service dependency, but does not require any specific provider to exist.
- If no provider is found, iterating `ServiceLoader` simply yields an empty result; handling fallback is the consumer's responsibility.

For unnamed modules and automatic modules, the service-use dependency mechanism has its own rules; they do not have the explicit `uses` declaration requirement like explicit named modules.

## 5. Rules for `provides ... with ...`

A providing module can register one or more providers for the same service:

```java
module com.example.greeting.provider {
    requires com.example.greeting.api;

    provides com.example.greeting.api.GreetingService
        with com.example.greeting.provider.FastGreetingService,
             com.example.greeting.provider.FormalGreetingService;
}
```

The syntax consists of the service type, the `with` keyword, and a list of fully qualified provider names. If you need to publish two different services, use two separate `provides` directives.

Key points:

1. The declared provider type must belong to the providing module; you cannot register an implementation located in another module using an arbitrary `provides`.
2. The provider class must have appropriate accessibility for JPMS to verify the configuration; typically `public`.
3. The provider is instantiated via a public no-arg constructor, or via a valid provider method in an explicit named module.
4. If using a constructor, the provider class must be compatible with the service type (implementing the interface or extending the appropriate class).
5. The implementation package does not necessarily need `exports` or `opens` for the consumer.
6. The providing module must be able to read the module with the service API when the service type resides in another module.

**Do not add `exports` just to fix a ServiceLoader error**. If a provider is not found, check `provides`, module resolution, and the constructor/provider method first. Broadening exports can unintentionally expose implementation APIs.

## 6. Two ways to instantiate a provider in a named module

### 6.1. Provider constructor

The most common approach is a class implementing the service with a `public` no-argument constructor:

```java
public final class BasicGreeting implements GreetingService {
    public BasicGreeting() {
    }

    @Override
    public String languageTag() {
        return "en";
    }

    @Override
    public String greet(String person) {
        return "Hello, " + person;
    }
}
```

This is the pattern used in the runnable example in the previous section. A provider can use its own dependencies in the constructor, but keep in mind that the constructor is called during provider iteration, so initialization errors can occur at the moment the consumer actually accesses the service.

### 6.2. Provider method

In an explicit named module, ServiceLoader also supports a factory method named exactly `provider`, with the following characteristics:

- `public static`;
- no parameters;
- returns an object of a type compatible with the service type.

For example:

```java
package com.example.greeting.provider.factory;

import com.example.greeting.api.GreetingService;

public final class GreetingFactory {
    private GreetingFactory() {
    }

    public static GreetingService provider() {
        return new CachedGreetingService();
    }
}
```

Registering in the module:

```java
module com.example.greeting.provider.factory {
    requires com.example.greeting.api;

    provides com.example.greeting.api.GreetingService
        with com.example.greeting.provider.factory.GreetingFactory;
}
```

`GreetingFactory` does not need to implement `GreetingService`, because `provider()` creates and returns the implementation object. `CachedGreetingService` here is an illustrative implementation, defined separately inside the provider module.

A provider method is especially useful when you need control over how the instance is created, such as performing factory setup or choosing an implementation based on configuration. However, the factory should not have hard-to-control side effects, and the method must not return `null`.

**Migration limitation:** Provider methods are only supported for providers in explicit named modules. Providers in automatic modules or on the classpath configured via `META-INF/services` must use a public no-arg constructor and be an appropriate subtype of the service.

## 7. Using ServiceLoader from the consumer

### 7.1. `load(Class<S>)`

This is the most commonly used form:

```java
ServiceLoader<GreetingService> loader =
        ServiceLoader.load(GreetingService.class);

for (GreetingService service : loader) {
    System.out.println(service.languageTag());
}
```

`ServiceLoader.load(Class)` uses the *thread context class loader* to start searching for providers. In modular applications, it can also find providers belonging to named modules visible through the module/class loader mechanism. If you want explicit control over the provider source, consider the overloads taking a ClassLoader or ModuleLayer.

### 7.2. `load(Class<S>, ClassLoader)`

You can pass a class loader explicitly:

```java
ClassLoader pluginLoader = Thread.currentThread()
        .getContextClassLoader();

ServiceLoader<GreetingService> loader =
        ServiceLoader.load(GreetingService.class, pluginLoader);
```

This overload is useful in application server environments, plugin managers, or when multiple class loaders exist. It does not allow finding providers from arbitrary locations; the provider must still be present and accessible within the corresponding class/module loading scope.

### 7.3. `load(ModuleLayer, Class<S>)`

When an application creates separate `ModuleLayer` instances to isolate plugins, providers can be looked up within a specific layer:

```java
ModuleLayer pluginLayer = obtainPluginLayer();
ServiceLoader<GreetingService> loader =
        ServiceLoader.load(pluginLayer, GreetingService.class);
```

`obtainPluginLayer()` is an illustrative function: the application must create or obtain a valid layer before calling it. This overload searches within the specified layer and its parent layers, and does **not** search for providers in unnamed modules on the classpath.

ModuleLayer helps manage module configurations and class loaders by plugin group, but it does not automatically solve versioning issues, access permissions, or class conflicts when a plugin and the host use different versions of the service API.

### 7.4. `findFirst()`, `iterator()`, and `stream()`

Since Java 9, ServiceLoader has `findFirst()` and `stream()`:

```java
ServiceLoader<GreetingService> loader =
        ServiceLoader.load(GreetingService.class);

GreetingService first = loader.findFirst()
        .orElseThrow(() -> new IllegalStateException(
                "No greeting provider installed"));
```

`findFirst()` is useful when the application only needs one provider, but you **should not** rely on it to determine business priority order among independent modules. The order of module providers is not guaranteed to be stable.

With `stream()`, you can inspect provider information and instantiate on demand:

```java
ServiceLoader<GreetingService> loader =
        ServiceLoader.load(GreetingService.class);

loader.stream()
        .map(ServiceLoader.Provider::get)
        .filter(service -> "vi".equals(service.languageTag()))
        .findFirst()
        .ifPresent(service ->
                System.out.println(service.greet("Java")));
```

`Provider.get()` can trigger actual instantiation. `Provider.type()` returns the provider type information according to the API contract; for a provider method, this type does not necessarily match the factory class listed after `with`. Do not use implementation class details as the primary criterion if the application already has its own metadata/capabilities.

## 8. Lazy loading, caching, and `reload()`

`ServiceLoader` discovers and instantiates providers on demand. Calling `load` creates a service loader; iterating the iterator or consuming the stream is what causes the discovery/instantiation process to happen incrementally.

Each ServiceLoader instance maintains a cache of loaded provider instances. Upon subsequent iteration, cached providers may be returned before new ones. This helps avoid unnecessary repeated instantiation within the lifecycle of a loader.

```java
ServiceLoader<GreetingService> loader =
        ServiceLoader.load(GreetingService.class);

for (GreetingService service : loader) {
    System.out.println(service.languageTag());
}

loader.reload();

for (GreetingService service : loader) {
    System.out.println(service.languageTag());
}
```

`reload()` clears the loader's internal cache so that the next traversal rediscovers/reinstantiates providers. It does **not** reload bytecode already loaded by a class loader, does not add unresolved modules to a layer, and is not a full hot-deployment mechanism. To add a new modular plugin while the application is running, an appropriate layer and class loader creation workflow is usually needed.

ServiceLoader is not guaranteed to be safe when the same instance is accessed concurrently by multiple threads. If used in a multi-request processing flow, you should manage synchronization or load the provider list into an immutable structure after initialization.

## 9. Provider ordering and implementation selection

You should not depend on the return order of providers across different modules. The order among modules within the same class loader/layer is not defined as a stable contract.

When a product has multiple providers, you should put the selection rules explicitly into the API or configuration:

- By capability such as language, file type, payment code, or driver.
- By name/configuration selected by an administrator.
- By version/capability published by the provider.
- By self-defined priority, with tie-breaking handling.
- By fallback policy when a provider is absent or fails to instantiate.

For example, a service can expose `languageTag()` and the consumer selects `vi` specifically instead of using the first provider. If the system requires selecting a single provider for a code, detect duplicate configurations rather than silently picking one provider by accidental order.

Additionally, a provider constructor or factory can be resource-intensive. Avoid repeating `ServiceLoader.load` on every request if the application only needs to create plugins once at startup.

## 10. From the legacy classpath to JPMS: `META-INF/services`

Before Java 9, ServiceLoader worked with a provider configuration file inside the JAR:

```text
provider.jar
├── com/example/greeting/provider/en/EnglishGreetingService.class
└── META-INF/
    └── services/
        └── com.example.greeting.api.GreetingService
```

The file name must exactly match the fully qualified binary name of the service type. The file contents are a list of fully qualified names of provider classes, one per line:

```text
com.example.greeting.provider.en.EnglishGreetingService
```

This file is UTF-8 encoded and may contain blank lines and comments starting with `#`. For example:

```text
# English implementation
com.example.greeting.provider.en.EnglishGreetingService
```

When a provider JAR is on the classpath, ServiceLoader searches for `META-INF/services/<service-name>` files and reads the class names to instantiate them. The provider class must have a public no-arg constructor, be an appropriate subtype of the service, and be findable by the class loader.

### 10.1. Differences when placing the JAR on the module path

| Packaging | Provider registration | Notes |
|---|---|---|
| JAR on classpath (unnamed module) | `META-INF/services` | Traditional ServiceLoader mechanism. |
| Automatic module on module path | Usually inferred from `META-INF/services` | Does not support provider factory methods; requires a provider constructor. |
| Explicit named module with `module-info.class` | `provides Service with Provider` | Does not need `META-INF/services` to register that module's providers. |

When converting a provider JAR from the classpath to an explicit named module, keeping only `META-INF/services` without declaring `provides` can prevent ServiceLoader from seeing providers in that module. For an explicit named module, move the registration to `module-info.java`.

If an explicit named module JAR has both `provides` and a `META-INF/services` file, ServiceLoader does not use the legacy file to redundantly register providers already present in the named module. Keeping the legacy file can serve configurations running on the classpath, though you should verify the actual release artifact and how the JAR is used.

### 10.2. Step-by-step migration

A common roadmap:

1. Place the service interface into a stable artifact/API shared by both the consumer and providers.
2. Inspect the contents of `META-INF/services` and all existing implementation classes.
3. If converting a provider to a named module, add `requires api.module` and `provides ... with ...`.
4. If converting a consumer to a named module, add `requires api.module` and `uses api.Service`.
5. Compile, run on the module path, and verify the resolved module graph.
6. If still supporting the classpath, test classpath mode separately and keep the appropriate service configuration files.
7. Explicitly document the supported combinations in the release documentation: classpath, module path, automatic module, and custom runtime image.

This is the stage where differences between old and new environments easily arise, because the classpath, automatic modules, and explicit named modules do not register and resolve providers in completely identical ways.

## 11. Providers must be resolved before they can be found

A common misconception is treating `--module-path` as equivalent to “load all modules in the directory”. In reality, the module path provides the set of *observable* modules; the module system must still *resolve* which modules will participate in a configuration/module layer.

The `requires` relationships and service binding can cause additional modules to be pulled into the graph. With a different configuration, a provider might not be resolved even though the JAR file is sitting in the directory.

To add a provider explicitly when running the sample application:

```bash
java --module-path mods \
  --add-modules com.example.greeting.provider.vi \
  --module com.example.greeting.app/com.example.greeting.app.Main
```

To view module resolution:

```bash
java --show-module-resolution \
  --module-path mods \
  --module com.example.greeting.app/com.example.greeting.app.Main
```

Inspect the output to determine whether the provider module participates in the graph. In applications creating custom `ModuleLayer` instances, you can use configuration APIs with service binding such as `Configuration.resolveAndBind` if you want to automatically include modules providing services; standard `Configuration.resolve` only resolves module relationships requested by the configuration.

If a service cannot find a provider, you need to distinguish between **an unresolved provider** and **a resolved but misregistered provider**. These two errors have different troubleshooting paths.

## 12. Interaction with `jlink` and minimal runtime images

`jlink` allows packaging a runtime image containing selected modules. To keep the image small, `jlink` does not perform service binding by default. Therefore, a provider automatically discovered when running with a full JDK may be missing in a custom runtime image if not selected during linking.

Example of creating an image from application and JDK modules:

```bash
jlink --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.example.greeting.app,com.example.greeting.provider.vi \
  --output greeting-runtime
```

The example above is for Linux/macOS, where `:` separates module path elements; Windows uses `;`. When using `jlink` in practice, you need to provide valid modular JARs/JMODs or an input structure supported by the tool version.

If you want to include observable service provider modules into the image based on service relationships, you can use:

```bash
jlink --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.example.greeting.app \
  --bind-services \
  --output greeting-runtime
```

`--bind-services` links provider modules and related dependencies. The set of modules can grow substantially, so you should inspect the image size and perform testing after linking. In environments with optional plugins, it is usually better to select providers explicitly to control the image better.

You can use `jlink --suggest-providers <service-type>` when looking for modules that provide an observable service. The generated runtime image must be tested against real execution paths, because ServiceLoader is only one part of a plugin system that may also depend on reflection, resources, native libraries, or external configuration.

## 13. Common errors and diagnostics

### 13.1. Consumer missing `uses`

When an explicit named module invokes ServiceLoader without declaring a service-use dependence, at runtime it can receive a `ServiceConfigurationError` stating that the module does not declare `uses` for that service.

**Resolution:** Add `uses com.example.greeting.api.GreetingService;` to the `module-info.java` of the exact module containing the code calling ServiceLoader, then recompile the module.

### 13.2. Provider missing `provides`

The consumer iterates ServiceLoader but sees no provider, even though the provider module is present on the module path.

**Resolution:** Verify that the provider module has `provides ... with ...`, that the provider module is resolved, and that the class after `with` has the exact fully qualified name.

### 13.3. Provider is only on the module path but not yet resolved

The module path only describes where to find modules; it does not guarantee that the provider is in the module graph.

**Resolution:** Check `--show-module-resolution`, use `--add-modules` when needed, or verify the service binding policy of the module configuration/module layer.

### 13.4. Invalid provider class

For example, the provider constructor is not `public`, lacks a no-argument constructor, does not implement the service type, or the provider factory returns the wrong type. When ServiceLoader actually finds/instantiates the provider, it can throw `ServiceConfigurationError`.

**Resolution:** Cross-check the constructor/provider method rules and inspect the underlying error thrown by the factory/constructor.

### 13.5. Incorrect `META-INF/services` file on the classpath

The service file name or provider class name is wrong, the resource was not included in the JAR, or the packaging tool dropped the services file.

**Resolution:** Inspect the JAR contents:

```bash
jar --list --file provider.jar
```

Ensure that the `META-INF/services/com.example.greeting.api.GreetingService` file is actually inside the JAR and contains the exact provider name.

### 13.6. `exports` in the wrong place

The service interface is in a package that the API module does not `exports`. Consumers and providers may be unable to access the service type during compilation.

**Resolution:** Export the package containing the API from the module defining the service. Do not export the implementation package unless there is an intent to expose the API.

### 13.7. Provider class and service interface loaded by two different class loaders

A plugin may bundle its own copy of the service API. Even with the same class name, the JVM treats types loaded by different class loaders as different types. The provider is no longer assignable to the service type used by the host.

**Resolution:** Design an API-sharing mechanism between the host and plugins, check class loader delegation, and avoid duplicate packaging of the service API across incompatible class loaders.

### 13.8. `findFirst()` selects the wrong implementation

The application works properly on machine A but picks a different provider on machine B because it relies on discovery order.

**Resolution:** Define explicit selection criteria in the service contract or configuration; do not treat module order as priority order.

## 14. Tools for inspecting JPMS

To inspect the descriptor in a modular JAR:

```bash
jar --describe-module --file greeting-provider.jar
```

To view the descriptor of a module on the module path:

```bash
java --module-path mods --describe-module com.example.greeting.provider.vi
```

Information to observe includes the module name, `requires`, `uses`, and `provides`. If the descriptor does not reflect recent changes, the pipeline may be packaging old class files or using a different JAR from the one just compiled.

To inspect module dependencies in an archive:

```bash
jdeps --print-module-deps --module-path mods greeting-app.jar
```

`jdeps` is a static analysis tool and does not guarantee finding every dynamically loaded provider. Combine it with `--show-module-resolution` and tests that run the application to know which providers are actually found at runtime.

## 15. Maintaining compatibility across versions

A plugin system must also preserve compatibility between the service API and independently released providers. The following changes should be considered:

| Change | Risk to old providers | How to handle |
|---|---|---|
| Adding an abstract method to the service interface | Old providers may fail to recompile; new calls may hit runtime errors. | Use appropriate default methods, a new API, or a provider upgrade roadmap. |
| Renaming or deleting the service type | Old `uses`, `provides`, and service configuration files become invalid. | Maintain adapters or release a clearly versioned API. |
| Renaming the implementation package | The `provides ... with ...` descriptor may point to a nonexistent class name. | Update the descriptor and inspect the packaged artifact. |
| Splitting the API module | `requires` and `exports` may change; the module graph must be updated. | Verify compilation, package accessibility, and resolution. |
| Changing provider packaging (classpath → named module) | The `META-INF/services` file does not replace `provides` for an explicit module. | Add the descriptor and test both modes if both remain supported. |
| Creating a smaller custom runtime image | Provider modules may be omitted during linking. | Select providers explicitly or use `--bind-services` in a controlled manner. |

For long-lived plugin APIs, publish compatibility rules and the JDK baseline. If a service interface needs major changes, one strategy is to keep the old interface version along with an adapter during a transition period, rather than breaking all providers in a single update.

## 16. Testing service discovery in a project

Tests that only instantiate implementations with `new` do not verify that the ServiceLoader mechanism works. You need tests that use the exact module path and descriptors to be released.

Example with JUnit 5:

```java
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.example.greeting.api.GreetingService;
import java.util.ServiceLoader;
import org.junit.jupiter.api.Test;

class GreetingDiscoveryTest {
    @Test
    void discoversVietnameseProvider() {
        boolean found = ServiceLoader.load(GreetingService.class)
                .stream()
                .map(ServiceLoader.Provider::get)
                .anyMatch(service -> "vi".equals(service.languageTag()));

        assertTrue(found);
    }
}
```

Tests need to run in an environment where `uses`, `provides`, and provider modules are properly resolved. If placing tests in a separate module, examine which module actually invokes ServiceLoader and declare `uses` accordingly; the test runner may use a different classloader/module layer from the production application.

Cases that should be tested:

1. No provider: how does the consumer handle an empty result?
2. One provider: does the consumer find and invoke the service?
3. Multiple providers: does the consumer select based on capability and without relying on order?
4. Provider constructor or factory throws an error: does the system log the error with sufficient information?
5. Provider class in an unresolved module: do logs/monitoring show the cause?
6. Running from the classpath and module path (if both are supported): are both the service file and descriptor correct?
7. Running in a custom runtime image: is the provider module actually present?
8. Running after upgrading the service API: are old providers still source-, binary-, and behaviorally compatible?

When an application deploys multiple third-party plugins, a contract test for providers is essential: checking the methods and invariants that every implementation must adhere to. ServiceLoader only guarantees the discovery/instantiation mechanism according to configuration rules, not that plugins fulfill business requirements properly.

## 17. An applicable migration workflow

Suppose an old library contains `PaymentPlugin` and multiple providers registered via `META-INF/services`. To migrate to JPMS:

### Step 1: Inventory service types and providers

List every service interface, provider class, JAR distribution, and how it is loaded. Identify plugins outside the repository or installed only in production.

### Step 2: Separate a stable service API

Place the service contract into a dedicated module and `exports` the package containing the API. Providers depend on the API module; the consumer also depends on the API module.

### Step 3: Add module declarations

In the consumer, declare `uses`. In each explicit named provider module, declare `provides ... with ...`. Choose an appropriate constructor or provider method.

### Step 4: Verify module resolution

Build proper modular artifacts, inspect descriptors, run `--show-module-resolution`, and confirm the provider modules participate in the graph. If using a runtime image, verify the `jlink` step.

### Step 5: Test required two-way compatibility

Run on the classpath if legacy systems still need support, run on the module path for new systems, and also test new consumers with previously released providers.

### Step 6: Separate the provider selection policy

Do not rely on discovery order; add selection mechanisms based on identifier, capability, or configuration. Clearly define behavior when no provider exists or multiple providers match.

### Step 7: Observe production

Log once at startup the service in use, the selected provider, the module name, and the plugin version when metadata is available. Avoid logging sensitive data; provider errors must be routed into the application's monitoring mechanism.

## 18. Frequently asked questions

**The consumer module already `requires` the API, does it still need `uses`?**

Yes, if it is an explicit named module calling ServiceLoader to find providers for the service. `requires` establishes type readability, whereas `uses` declares a service discovery dependency.

**Does the provider module need to `exports` the package containing the implementation?**

No. The provider class can be instantiated by ServiceLoader through `provides` even when the implementation package is not exported. This is a benefit of encapsulation in JPMS.

**Does the consumer need to `requires` all provider modules?**

No. The consumer should depend on the service API. Module resolution or configuration steps at run/link time ensure the necessary providers are present.

**Does ServiceLoader guarantee discovering providers in every JAR on disk?**

No. It searches within the scope of the relevant class loader or module layer/configuration. A JAR not placed into the appropriate classpath/module graph will not automatically become a usable provider.

**Can a provider be registered with both `provides` and `META-INF/services`?**

You can maintain both forms of metadata in a JAR to serve different runtime modes, but an explicit named module uses the `provides` declaration for its service providers. You should verify packaging and avoid relying on duplicate registration.

**Can ServiceLoader be used as a complete plugin manager?**

ServiceLoader focuses on discovery and instantiation. Version management, dependencies, lifecycle, fault isolation, permissions, runtime upgrades, and plugin selection policies still require additional design.

## 19. Checklist when designing and releasing service modules

- [ ] The service interface or abstract service class is published in an appropriate package.
- [ ] The module containing the service API `exports` the right package for consumers and providers.
- [ ] The explicit named module calling ServiceLoader declares `uses` for the right service.
- [ ] The provider module has `requires` for the service API and `provides ... with ...` with the exact class name.
- [ ] The provider uses a public no-arg constructor or a valid provider method.
- [ ] The implementation package uses `exports`/`opens` only when genuinely needed.
- [ ] The provider module has been included in the resolved module graph.
- [ ] `META-INF/services` is packaged properly if the system still supports the classpath/automatic modules.
- [ ] The provider selection policy does not rely on discovery order.
- [ ] Behavior is defined when there are no providers, multiple providers, or provider instantiation failures.
- [ ] A single ServiceLoader instance is not shared across multiple threads without controlled access.
- [ ] Tested on the module path, classpath, and runtime image across supported configurations.
- [ ] Compatibility has been tested against the service API and providers from previous releases.

## References

- [Java API — ServiceLoader (Java SE 26)](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ServiceLoader.html): definition of service/provider, lazy loading, registration, and `load` overloads.
- [JLS 7.7 — Module Declarations](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-7.html#jls-7.7): syntax and rules for `requires`, `exports`, `uses`, `provides`.
- [Module API — `canUse` and `addUses`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Module.html): querying and adjusting service dependencies in appropriate framework scenarios.
- [Configuration — `resolveAndBind`](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/module/Configuration.html): resolving the module graph combined with service binding.
- [Oracle jlink Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jlink.html): the `--bind-services` and `--add-modules` options.

## Conclusion

`ServiceLoader` is a mechanism connecting a service API, consumers, and providers without requiring direct dependencies on implementations. In JPMS, an explicit named consumer module declares `uses` to find a service, a provider module declares `provides ... with ...` to register an implementation, while `requires` and `exports` govern module readability and accessibility of the service type. When migrating from the classpath to the module path, check `META-INF/services` metadata, module resolution, provider instantiation conditions, and implementation selection policies. Discovery tests against actual artifacts and custom runtime images help uncover errors that direct `new` calls cannot see.
