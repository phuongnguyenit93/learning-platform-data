# `uses` and `provides` in `module-info.java`: declaring and loading Java services

## 1. The problem to solve

A Java application often needs to extend its functionality with multiple implementations of **the same contract**: data formatters, storage systems, drivers, converters, or plugins. If the application hardcodes the names of all implementation classes and calls `new` directly, it becomes tightly coupled to those concrete implementations. **Service Provider Interface (SPI)** together with `java.util.ServiceLoader` allows an application to declare **which services it uses**, while implementation libraries **advertise their capability to provide services**.

When using the **Java Platform Module System (JPMS)** since Java 9, two core declarations reside in `module-info.java`:

```java
uses com.example.spi.GreetingService;
```

and:

```java
provides com.example.spi.GreetingService
        with com.example.provider.EnglishGreeting;
```

These are **two declaration fragments** in two different module descriptors, not yet a complete runnable program.

- **`uses ServiceType;`** is placed in the **module that uses** the service. It declares that the module's code can look up providers for that service type using `ServiceLoader`.
- **`provides ServiceType with ProviderType1, ProviderType2;`** is placed in the **providing module**. It registers providers for the service type. `with` lists provider class names; this is a module declaration, not an instruction that automatically runs constructors.
- **`ServiceLoader.load(ServiceType.class)`** is the runtime call that **discovers and retrieves providers** according to the corresponding module/class loader rules.
- **`requires` and `exports`** support readability and visibility of **the service API type**, but **do not replace `uses` or `provides`**.

The goal of this lesson is to explain the semantics, resolution and class loading mechanisms, runnable Java 17+ code, file layout, common errors, and differences from the traditional classpath `META-INF/services` mechanism.

## 2. Four roles in the service architecture

Suppose there is a `GreetingService` contract and two implementations, English and Vietnamese:

```text
learning.services.api
    └── learning.services.api.GreetingService  (service interface)
                    ^
                    |
          publishes/implements
               /        \
              /          \
learning.services.en   learning.services.vi
provides ... with ...  provides ... with ...
              \          /
               \        /
                v      v
        learning.services.app
        requires API; uses API
        ServiceLoader.load(...)
```

There are four concepts to keep separate:

| Concept | Role | Example |
| --- | --- | --- |
| **Service** | Interface or abstract class contract that the consumer wants to use | `GreetingService` |
| **Service consumer** | Module calling `ServiceLoader` to obtain implementations | `learning.services.app` |
| **Service provider** | Module registering one or more providers using `provides ... with ...` | `learning.services.en` |
| **Provider implementation** | Class implementing the contract or class providing a valid `provider()` factory | `EnglishGreeting` |

A **provider module** is not synonymous with a **provider object**. A single module can register multiple provider types, and a service can receive multiple providers from different modules. Provider discovery order should not be used as an application priority policy.

### Distinguishing `requires`, `exports`, `uses`, `provides`

| Directive in module-info.java | Who declares it? | Meaning |
| --- | --- | --- |
| `requires learning.services.api;` | Both consumer and provider may need it | Allows the module to read the module containing the API type |
| `exports learning.services.api;` | API module | Allows other modules to access public types in the API package |
| `uses learning.services.api.GreetingService;` | Module calling `ServiceLoader` | Declares the permission/contract to use a service type |
| `provides learning.services.api.GreetingService with ...;` | Provider module | Publishes a provider of the service for the discovery mechanism |
| `opens package.name;` | Module needing reflective access under JPMS rules | Does not automatically register a service provider |
| `requires static ...;` | Module with an optional dependency at runtime | Does not substitute for provider registration |

**Key point:** `requires provider.module` is not an appropriate mechanism to “discover” providers when the consumer only wants to know the service API. The consumer needs to declare `uses` and maintain the SPI contract; providers are published via `provides`, while module resolution/service binding decides which providers participate in the graph at runtime.

## 3. Basic syntax and rules

### 3.1. `uses`

In the module descriptor:

```java
module learning.services.app {
    requires learning.services.api;
    uses learning.services.api.GreetingService;
}
```

The consumer module reads the API module and declares that it uses that service type. The `uses` syntax takes a **type name**, not a file name, JAR name, or object instance.

If a named module calls the `ServiceLoader.load(...)` mechanism for a service type for which that module **does not declare `uses`**, the loading process can fail with a `ServiceConfigurationError` stating that the caller module does not declare using that service (per the `ServiceLoader` API). `uses` should not be omitted just because the module already `requires` the API module.

### 3.2. `provides ... with ...`

In the providing module:

```java
module learning.services.en {
    requires learning.services.api;
    provides learning.services.api.GreetingService
        with learning.services.en.internal.EnglishGreeting;
}
```

The provider type must satisfy valid registration requirements. The common case is a **public provider class** implementing the service interface and having a **public no-argument constructor**.

For an **explicit named module**, `ServiceLoader` also supports a **provider factory method** named `provider` per the API rules, instead of requiring the declared provider class to directly implement the service. We will distinguish the two approaches in the advanced section.

### 3.3. Is it mandatory to `exports` the implementation package?

**No.** Module `learning.services.en` can place `EnglishGreeting` in package `learning.services.en.internal` and **not export this package**. ServiceLoader has a mechanism supporting loading providers validly declared by the module descriptor without requiring the consumer to directly access the implementation class. The consumer only programs against the public interface exported from the API module.

If the consumer tries to directly import/call `learning.services.en.internal.EnglishGreeting`, the compiler or module access checks will reject it when the package is not exported; this is not a `ServiceLoader` error.

## 4. Complete Java 17 demo: 1 service, 2 providers, 1 consumer

The example uses four **explicit named modules**:

1. `learning.services.api` defines the `GreetingService` contract.
2. `learning.services.en` supplies the English provider.
3. `learning.services.vi` supplies the Vietnamese provider.
4. `learning.services.app` declares `uses` and calls `ServiceLoader`.

No dependencies outside the JDK, nor Maven or Gradle, are needed. Use JDK 17+ with `javac` and `java`.

### 4.1. Directory structure

```text
src/
├── learning.services.api/
│   ├── module-info.java
│   └── learning/services/api/GreetingService.java
├── learning.services.en/
│   ├── module-info.java
│   └── learning/services/en/internal/EnglishGreeting.java
├── learning.services.vi/
│   ├── module-info.java
│   └── learning/services/vi/internal/VietnameseGreeting.java
└── learning.services.app/
    ├── module-info.java
    └── learning/services/app/Main.java
```

Directory names under `src` correspond to module names; `javac --module-source-path src` uses this layout convention.

### 4.2. Service API module

File `src/learning.services.api/module-info.java`:

```java
module learning.services.api {
    exports learning.services.api;
}
```

File `src/learning.services.api/learning/services/api/GreetingService.java`:

```java
package learning.services.api;

public interface GreetingService {
    String code();
    String greet(String name);
}
```

`exports` allows the consumer and providers to **use the public type** `GreetingService` in the API package. Without export (and without another access mechanism), other modules cannot write `implements GreetingService` in this way.

### 4.3. English provider

File `src/learning.services.en/module-info.java`:

```java
module learning.services.en {
    requires learning.services.api;
    provides learning.services.api.GreetingService
        with learning.services.en.internal.EnglishGreeting;
}
```

File `src/learning.services.en/learning/services/en/internal/EnglishGreeting.java`:

```java
package learning.services.en.internal;

import learning.services.api.GreetingService;

public final class EnglishGreeting implements GreetingService {
    public EnglishGreeting() {}

    @Override
    public String code() {
        return "en";
    }

    @Override
    public String greet(String name) {
        return "Hello, " + name;
    }
}
```

The provider class is public, implements the interface, and has a public no-argument constructor. The `internal` package is **not exported** from the provider module, yet `provides ... with ...` is still valid.

### 4.4. Vietnamese provider

File `src/learning.services.vi/module-info.java`:

```java
module learning.services.vi {
    requires learning.services.api;
    provides learning.services.api.GreetingService
        with learning.services.vi.internal.VietnameseGreeting;
}
```

File `src/learning.services.vi/learning/services/vi/internal/VietnameseGreeting.java`:

```java
package learning.services.vi.internal;

import learning.services.api.GreetingService;

public final class VietnameseGreeting implements GreetingService {
    public VietnameseGreeting() {}

    @Override
    public String code() {
        return "vi";
    }

    @Override
    public String greet(String name) {
        return "Xin chào, " + name;
    }
}
```

A service interface can have multiple providers; each provider is registered in the module descriptor of the module containing that provider.

### 4.5. Consumer module

File `src/learning.services.app/module-info.java`:

```java
module learning.services.app {
    requires learning.services.api;
    uses learning.services.api.GreetingService;
}
```

File `src/learning.services.app/learning/services/app/Main.java`:

```java
package learning.services.app;

import java.util.ServiceLoader;
import java.util.SortedMap;
import java.util.TreeMap;
import learning.services.api.GreetingService;

public final class Main {
    public static void main(String[] args) {
        SortedMap<String, String> results = new TreeMap<>();

        for (GreetingService provider :
                ServiceLoader.load(GreetingService.class)) {
            results.put(provider.code(), provider.greet("Java"));
        }

        System.out.println("providers=" + results.size());
        results.forEach((code, message) ->
                System.out.println(code + "=" + message));
    }
}
```

**Why choose `TreeMap`?** `ServiceLoader` can find multiple providers, and the order in which they are supplied should not be treated as a business priority order. `TreeMap` sorts by `code()`, giving **stdout a stable order** with `en` before `vi`, provided each provider returns a distinct code.

**Why not import EnglishGreeting in Main?** The consumer depends only on the exported service interface; the implementation class resides in an unexported package and can change independently.

### 4.6. Compiling with module-source-path

In a terminal positioned at the directory containing `src`:

```bash
javac -encoding UTF-8 --release 17 --module-source-path src -d mods -m learning.services.api,learning.services.en,learning.services.vi,learning.services.app
```

This command compiles the modules along with their source files according to the `--module-source-path` layout into `mods/<module-name>/...`. `-encoding UTF-8` ensures Vietnamese source code is decoded consistently when the compiler runs on an operating system with a different default charset.

### 4.7. Running with resolved provider modules

```bash
java --module-path mods --add-modules learning.services.en,learning.services.vi --module learning.services.app/learning.services.app.Main
```

Explanation:

- `--module-path mods` points to the location of the compiled modules.
- `--module learning.services.app/learning.services.app.Main` specifies the module and main class.
- `--add-modules learning.services.en,learning.services.vi` requests that the two provider modules be added to the root set and resolved in the module graph, so the demo does not rely on assumptions about the launcher environment's default service binding.
- The consumer still **does not import** any provider implementation; `ServiceLoader` discovers them through the descriptors.

**Expected stdout when running in a normal JDK 17+ environment:**

```text
providers=2
en=Hello, Java
vi=Xin chào, Java
```

The order here comes from `TreeMap`; it is not a promise about the native order of `ServiceLoader`.

### 4.8. What happened at runtime

1. The module graph contains `learning.services.api`, `learning.services.app`, and the two provider modules.
2. The consumer reads the `GreetingService` type from the API module thanks to `requires` + `exports`.
3. The consumer's `uses` declares the service that the consumer has permission to discover.
4. `provides` in the provider modules registers the implementation classes.
5. `ServiceLoader.load(GreetingService.class)` creates a discovery loader; when iterating over providers, Java finds and instantiates the appropriate providers.
6. `GreetingService.code()/greet()` are called via the interface; no API is needed to directly access the `internal` packages.
7. The results are sorted and printed; there is no guarantee regarding provider priority inside `ServiceLoader`.

**Note:** having a provider module on the module path is **not sufficient** for every discovery API to see it; the module must be included in the appropriate module layer/graph configuration. `--add-modules` in the demo is a way to make this condition explicit. In real-world launchers, services may also be bound by module resolution or an application framework.

## 5. Does `ServiceLoader` do anything immediately at load()?

`ServiceLoader.load(ServiceType.class)` creates a `ServiceLoader<ServiceType>` object; providers are located/instantiated **lazily** when the iterator or stream is used. This is not an alternative syntax for `new EnglishGreeting()` and does not guarantee that all provider objects have already been created right when `load(...)` is called.

Example snippet in a consumer with `uses GreetingService`:

```java
ServiceLoader<GreetingService> loader =
        ServiceLoader.load(GreetingService.class);

for (GreetingService service : loader) {
    System.out.println(service.getClass().getName());
}
```

This is a **non-standalone** snippet (it requires imports, the service module, and appropriate providers).

Some important APIs:

| API | Purpose |
| --- | --- |
| `ServiceLoader.load(Service.class)` | Uses the appropriate context class loader per the API and caller module permissions |
| `ServiceLoader.load(Service.class, loader)` | Looks up with the specified class loader per API semantics; caller module checks still apply |
| `ServiceLoader.load(layer, Service.class)` | Discovers providers in the specified module layer and parent layers per the contract |
| `iterator()` or `for` loop | Retrieves/instantiates provider instances one by one |
| `stream()` | Accesses `ServiceLoader.Provider<S>` to inspect the type and retrieve the instance via `get()` |
| `reload()` | Clears the ServiceLoader's provider cache; subsequent iteration searches again per the API mechanism |
| `ServiceConfigurationError` | Service/provider configuration error, invalid class, or error when locating/instantiating a provider |

`reload()` does **not** unload classes already defined by the JVM or automatically replace all runtime classes from an old JAR. If a plugin is updated, it may also be necessary to create a new module layer/class loader and manage lifecycle references.

**TCCL:** `Thread.currentThread().getContextClassLoader()` can affect `ServiceLoader` overloads that use the context loader, especially providers on the classpath or custom frameworks. However, changing the TCCL does not “grant” `uses` to a named module caller, nor does it change the defining loader of an already-loaded class.

## 6. Does a service provider need to export its implementation package?

No. One goal of the JPMS service mechanism is to **hide implementation details while allowing service discovery**.

Example:

```java
module learning.services.en {
    requires learning.services.api;
    provides learning.services.api.GreetingService
        with learning.services.en.internal.EnglishGreeting;
}
```

The directive above **does not export** `learning.services.en.internal`. The consumer calls the `GreetingService` interface and does not need to see the implementation package.

Avoid this incorrect fix:

```java
module learning.services.en {
    requires learning.services.api;
    exports learning.services.en.internal;
    provides learning.services.api.GreetingService
        with learning.services.en.internal.EnglishGreeting;
}
```

This is a **compilable but unnecessary configuration snippet** if the package is only exported to help ServiceLoader detect the provider. `exports` expands the public surface for compile/runtime module access; it should not be done when there is no direct API need.

### Public constructor and access scope

For a provider type **instantiated via constructor**, the provider class must typically be `public`, non-abstract, and have a **public no-args constructor**. The service mechanism is capable of creating instances according to the module registration model; it does not require the consumer to directly access the implementation package via `exports`.

If the constructor requires arguments, throws an exception, or cannot be instantiated, discovery/iteration may fail with a `ServiceConfigurationError`; inspect `Caused by` to find the root cause.

## 7. Provider factory method (advanced)

For a provider in an **explicit named module**, `ServiceLoader` supports declaring a **provider class with a public static no-arg method named `provider`** that returns a type assignable to the service. This allows using a factory and hiding the constructor/implementation:

```java
package example.provider.internal;

import example.api.Compressor;

public final class CompressorFactory {
    private CompressorFactory() {}

    public static Compressor provider() {
        return new FastCompressor();
    }
}
```

This is **illustrative code**, not a standalone runnable example: `Compressor` and `FastCompressor` must be defined in the appropriate module.

Module descriptor:

```java
module example.provider {
    requires example.api;
    provides example.api.Compressor
        with example.provider.internal.CompressorFactory;
}
```

- In the factory approach, the class listed after `with` can be a class **supplying the service object**, without that class itself necessarily implementing the service; the `provider()` method returns the appropriate object.
- The provider method must meet the Java ServiceLoader API requirements; having multiple overloads or an invalid factory declaration can cause a `ServiceConfigurationError`.
- This factory provider method approach applies to **explicit modules**, not legacy classpath `META-INF/services` configuration; for provider classes in an unnamed module/automatic module, the corresponding constructor-based rules still matter.
- Do not confuse the SPI `provider()` factory method with an injection framework annotation or general Java method reflection; it has a dedicated contract in `ServiceLoader`.

### Why is a factory method useful?

A factory can decide on the appropriate implementation based on configuration or construct the service object with dependencies without requiring a public no-arg constructor on the real implementation. However, the provider module responsible for the factory must not arbitrarily instantiate untrusted classes/plugins inside the main JVM without appropriate safety mechanisms.

## 8. JPMS service binding and module resolution

The `uses`/`provides` keywords reside in the descriptor; however, it is the **module graph** at runtime that determines which provider modules are available for service discovery.

In the Java launcher:

- The named module specified as the main module is a key root.
- `requires` pulls read modules into the graph through module resolution.
- `--add-modules` allows adding modules as roots.
- There is a **service binding** mechanism during resolution to bind consumers that use a service to observable provider modules; behavior also depends on how the launcher/layer is constructed and the observable module sets.
- You should not infer that “merely having the provider JAR on the module path guarantees it will be loaded” in every application.

The demo uses `--add-modules learning.services.en,learning.services.vi` so the provider modules are guaranteed to be present in the resolved graph when the descriptors and dependencies are correct. In deployment, this can be replaced by module resolution with deliberately configured service binding.

### Useful diagnostic command

```bash
java --show-module-resolution --module-path mods --add-modules learning.services.en,learning.services.vi --module learning.services.app/learning.services.app.Main
```

The `--show-module-resolution` option shows which modules are resolved along with their sources and participating relationships, helping detect missing provider modules or wrong artifacts being selected. Diagnostic output varies by JDK and graph, so this lesson does not hardcode all log lines.

If you run:

```bash
java --module-path mods --add-modules learning.services.en --module learning.services.app/learning.services.app.Main
```

then **you should not definitively claim there is only one provider** under every service binding mechanism. What is certain is that module `learning.services.en` is added directly; other modules may still be resolved by service binding or launcher/layer configuration. When you need to test excluding `learning.services.vi`, use a module path/graph that supplies only the desired modules or configure the layer explicitly.

## 9. ClassLoader and module layers in ServiceLoader

On the traditional classpath, plugins are sometimes loaded with separate `URLClassLoader` instances. In JPMS, the system can have a **ModuleLayer** containing modules, with each module defined with an appropriate class loader.

Things to distinguish:

1. **Module path** is the input for the resolver to locate module artifacts; it is not itself a “parent of a class loader”.
2. **Module graph** indicates which modules have been resolved and their corresponding readability/export relationships.
3. **Class loader** actually defines the provider class and service interface; the same binary name with different defining loaders constitutes two distinct runtime types.
4. **ModuleLayer** is a runtime structure containing resolved modules (additional layers can be created for plugins).
5. **ServiceLoader** has overloads that look up providers by class loader or by module layer.

Snippet when the corresponding layer and service type already exist:

```java
ServiceLoader<GreetingService> providers =
        ServiceLoader.load(pluginLayer, GreetingService.class);
```

This is a **snippet**, not a standalone program: `pluginLayer` must be created properly and the caller named module must have permission to use the service per the contract. The `ModuleLayer` overload can search for providers in the specified layer and parent layers per the API; it does not create a layer automatically from a module name.

### An easily overlooked constraint: SPI identity

If the host uses `learning.services.api.GreetingService` defined in loader H, while another plugin loader **redefines** a class/interface with the same name, a provider implementing the plugin's “copy of the SPI” will not be recognized as an implementation of the exact service type the host is passing to `ServiceLoader`.

Therefore, in a plugin architecture:

- Place the shared API/SPI into a shared module/loader.
- Have provider modules read that service API instead of bundling a duplicate copy.
- Check the module layer and defining loader of the service interface/provider.
- Avoid child-first configurations that duplicate the shared SPI.
- When seeing `ServiceConfigurationError: not a subtype` or strange class-cast errors, inspect runtime type identity rather than just the package name.

## 10. Comparing `module-info.java` with `META-INF/services` on the classpath

Before JPMS, and today when deploying on the classpath, a provider can be published via a text resource:

```text
META-INF/services/learning.services.api.GreetingService
```

Example file contents:

```text
learning.services.en.internal.EnglishGreeting
learning.services.vi.internal.VietnameseGreeting
```

On the **classpath**, this is a list of provider class names. The library author must place the resource file in the right location inside the JAR/classes, public provider classes must have an appropriate constructor under the legacy provider mechanism, and the appropriate loader must be able to find the resource via `getResources`.

In **explicit named modules**, the standard model is **`provides ... with ...` in the module descriptor**. Obtaining providers from a named module is governed by module descriptor metadata and module resolution; there is no need to place `META-INF/services` to register that same provider as in the example pattern.

| Topic | Explicit named module | Unnamed module / traditional classpath |
| --- | --- | --- |
| Consumer declaration | `uses ServiceType;` in `module-info.java` | No `module-info.java`; calls the appropriate ServiceLoader API |
| Provider registration | `provides ServiceType with Provider;` | `META-INF/services/<fully.qualified.Service>` |
| API visibility | `requires` + `exports` where appropriate | Classpath/type visibility and defining loader |
| Provider package export | No need to export just so ServiceLoader can instantiate the provider | No JPMS-style exports from an unnamed module |
| Provider factory `provider()` | Supported per explicit named module rules | Not applicable under the legacy file-based registration |
| Discovery boundary | Resolved modules, module layers, class loaders | Resource lookup/class loaders |
| When providers duplicate | Depends on provider identity in descriptor/resolution | Depends on multiple JAR/resource configuration; ServiceLoader handles valid duplicate rules |

When migrating a library from the classpath to the module path, do not assume the legacy descriptor file is sufficient for an **explicit modular JAR**. Verify the descriptor, how services are declared, and the actual launcher/module graph.

### Automatic modules

A JAR without `module-info.class` can be treated as an **automatic module** when placed on the module path. Automatic modules have different metadata inference and service-provider rules than explicit named modules; they can derive service-provider declarations from `META-INF/services` per JPMS. Do not call every JAR on the module path an explicit module or assume provider factory method support applies to automatic modules.

## 11. What happens if `uses` or `provides` is missing?

### Case 1: Consumer forgets `uses`

The consumer module can still `requires` the API and compile code using `GreetingService`. However, when calling `ServiceLoader.load(GreetingService.class)` from a named module that does not declare `uses GreetingService`, Java ServiceLoader may throw a `ServiceConfigurationError` because the caller module has not declared that it uses this service.

**Fix:** add `uses learning.services.api.GreetingService;` to the consumer descriptor. Do not try to fix this by exporting the provider implementation package.

### Case 2: Provider forgets `provides`

The provider module contains a class that implements `GreetingService`, but its descriptor does not publish the provider. Under the explicit named module mechanism, `ServiceLoader` **does not automatically scan all classes** to guess which class implements the interface.

**Fix:** register `provides ... with ...` in the provider module, ensure the class/provider method adheres to the contract, and make sure the module is present in the resolved graph.

### Case 3: Provider module is not resolved

The module JAR resides in the `mods` directory, but does not participate in the queried module layer. The consumer does not see that provider via a ServiceLoader using that layer/class loader.

**Fix:** inspect the module graph using `--show-module-resolution`; include the provider in resolution with `--add-modules`, appropriate service binding, or by creating a plugin layer containing the provider modules according to your architecture.

### Case 4: API interface is defined twice

The host and plugin package two definitions of `GreetingService` with the same binary name but different defining loaders. A provider implementing the plugin's SPI might not be a subtype of the host's SPI.

**Fix:** unify the service API in a shared module/loader and avoid shadowing the API inside plugins.

### Case 5: Invalid constructor/provider factory

A provider class fails validity requirements, lacks a public no-arg constructor (in the constructor-based case), has a provider() method with an incorrect signature, or its constructor throws an error.

**Fix:** read the `ServiceConfigurationError` along with its cause, verify the signature and module descriptor; do not catch all exceptions and silently ignore unreliable providers.

## 12. Common errors and diagnostics

| Symptom | Possible cause to check | Resolution |
| --- | --- | --- |
| `ServiceConfigurationError: module ... does not declare uses` | Consumer named module is missing uses | Add uses to the caller module's module-info |
| No providers found, empty loop | Provider module is not resolved, missing provides, or searching the wrong layer/loader | Check module graph, provides, `--add-modules` |
| `ServiceConfigurationError: Provider ... not found` | Wrong provider name, provider class/dependency failed to load | Binary name, JAR/module path, class loader |
| `ServiceConfigurationError: ... not a subtype` | Provider does not implement the right service type, possibly due to duplicate SPI | Compare defining loaders of the SPI/provider |
| Constructor/provider method error | Invalid provider class/factory configuration or exception thrown | Public constructor, factory method, cause |
| `IllegalAccessError` / `InaccessibleObjectException` | Invalid module access, exports/opens, or reflection | Inspect module descriptors/caller module |
| `NoClassDefFoundError` | Provider class references a missing dependency or previous initializer failed | Read cause and runtime dependencies |
| `NoSuchMethodError` | Compile/runtime library API version mismatch | Check defining loader, JAR, method descriptor |
| `ClassCastException` | Provider passed across a duplicated SPI type boundary | Unify the API interface definition |
| Provider seen when running in IDE but missing in JAR | Different module graph/packaging, missing descriptor or services resource | Inspect the actual artifact and launch command |
| Reload does not pick up the new class version | ServiceLoader cache or old loader/module layer holds classes | Check lifecycle, `reload()`, and new layer/class loader |

### Inspecting the actual artifact

If the module JAR has been packaged (the JAR file actually exists):

```bash
jar --describe-module --file provider.jar
jar tf provider.jar
```

`jar --describe-module` shows the descriptor with provides/exports/requires, while `jar tf` lists actual entries. The name `provider.jar` here is an example, not a file generated by the demo commands that did not include a packaging step.

Use:

```bash
java --show-module-resolution --module-path mods --add-modules learning.services.en,learning.services.vi --module learning.services.app/learning.services.app.Main
```

to inspect which modules participate in resolution. Do not rely solely on `ServiceLoader` logs: a provider error can lie in class loading/linking or in the constructor during iteration.

### Observing type identity

If you have a `GreetingService provider` object:

```java
System.out.println(GreetingService.class.getClassLoader());
System.out.println(provider.getClass().getClassLoader());
System.out.println(provider.getClass().getModule());
```

This is a snippet, not a standalone program. The service interface and provider **do not have to share the same defining loader**, but the provider must actually implement **the SPI definition that the consumer is using**. When relying on multiple plugin loaders, verify interface identity by the actual `Class<?>`.

## 13. Performance, thread-safety, and lifecycle

`ServiceLoader` caches providers per instance to avoid repeated discovery/instantiation work. However, **the `ServiceLoader` instance itself is not safe for concurrent use by multiple threads without appropriate synchronization**. This is distinct from whether provider implementations are thread-safe or not depending on their own contracts.

Operational notes:

- **Do not assume provider order:** if a provider needs to be selected by region/priority, use metadata or an explicit policy; in the example, `code()` is sorted to print the results.
- **Handle provider errors deliberately:** a failing provider can cause iteration to fail and should not be silently hidden.
- **Close provider resources:** ServiceLoader does not take over the implementation's responsibility for closing connections, threads, or streams. If a provider is AutoCloseable, the application/framework must manage its lifecycle appropriately.
- **Be careful with TCCL in thread pools:** if temporarily setting the context loader to look up plugins, restore it in a `finally` block afterward.
- **`reload()` does not automatically change class identity:** the same old class loader/module layer may continue using the same already-defined runtime class.
- **Do not treat a modular service provider as a sandbox:** provider code still runs with the process's privileges under the actual security model; verify plugin sources and consider process isolation for untrusted code.

### A controlled provider selection scenario

For example, when an application needs to prioritize service code `vi`:

```java
GreetingService chosen = null;
for (GreetingService item : ServiceLoader.load(GreetingService.class)) {
    if ("vi".equals(item.code())) {
        chosen = item;
        break;
    }
}
if (chosen == null) {
    throw new IllegalStateException("Vietnamese provider unavailable");
}
System.out.println(chosen.greet("Java"));
```

This is a **snippet** inside a consumer module that has declared `uses`. Output when the Vietnamese provider is present as in the demo:

```text
Xin chào, Java
```

Do not use `iterator().next()` without checking when provider order can change across deployment environments.

## 14. Common misconceptions

**“`requires` on the provider module is enough for ServiceLoader to recognize the service.”** False. The consumer must declare an appropriate `uses`, and the provider must publish `provides` or use another registration mechanism depending on the module kind.

**“A module with `provides` means the provider constructor already runs at startup.”** False. Provider discovery/instantiation is normally lazy when the API is used; the descriptor only publishes the registration.

**“The provider package must be `exports`ed for ServiceLoader to call the constructor.”** No. A provider properly declared in an explicit module can reside in an unexported package; the consumer only needs the appropriate public service API.

**“ServiceLoader automatically scans every class implementing the interface on the module path.”** No. It uses service configuration/module metadata/classpath descriptors per the contract, not arbitrary classpath scanning.

**“Two providers must be in the same module.”** No. A single service can be provided by multiple separate modules.

**“ServiceLoader will always prioritize the provider that comes first alphabetically.”** No. Discovery order is not a priority policy; the application should select providers deliberately.

**“Having the provider JAR on disk guarantees the module has been resolved.”** No. You need to verify the module layer/graph and how the loader is invoked.

**“`reload()` automatically updates to the new class in the old loader.”** No. It handles the ServiceLoader's provider cache; it does not redefine a class with the same binary name in the same loader.

**“Both `META-INF/services` and `provides` must always be written to run on the module path.”** No. Explicit named modules use standard `provides` registration; classpath/automatic modules have a different mechanism.

**“Using `ServiceLoader` makes providers always safe because the JVM verifies bytecode.”** False. Valid bytecode can still perform actions under the runtime privileges of the process.

## 15. Knowledge self-check

**Question 1.** Where is `uses` placed? Is it mandatory to put it in a provider module?

**Answer:** `uses ServiceType` belongs to the module **that calls ServiceLoader to consume the service**. The provider module uses `provides ServiceType with Provider;`. A module can both use and provide different services, but not every provider inherently needs `uses`.

**Question 2.** Does `exports learning.services.api;` replace `uses GreetingService;`?

**Answer:** No. `exports` controls type accessibility in a package; `uses` declares the need to look up providers under the named module's ServiceLoader contract.

**Question 3.** Why does the demo consumer not import `EnglishGreeting` yet still receives an instance?

**Answer:** The provider is registered with `provides ... with ...`, the module is present in the graph, and ServiceLoader discovers/instantiates it via the service API. The consumer depends only on the SPI.

**Question 4.** If `provides` is removed from `learning.services.vi` while keeping the `VietnameseGreeting` class in the JAR, is ServiceLoader guaranteed to pick up this provider?

**Answer:** Not under the explicit named module mechanism presented here; merely having a class that implements the SPI is not enough for automatic registration.

**Question 5.** What does `--add-modules learning.services.en,learning.services.vi` solve in the demo command?

**Answer:** It adds both provider modules to the resolution root set; this is a way to ensure they appear in the runtime module graph so ServiceLoader can find them.

**Question 6.** Why does the demo output use `TreeMap`?

**Answer:** Because ServiceLoader is not an API that guarantees sorting by provider code; TreeMap provides stable display ordered by keys `en`, `vi` and avoids drawing false conclusions about discovery order.

**Question 7.** Can a provider class be registered in an unexported `internal` package?

**Answer:** Yes, with an explicit named module and a valid declaration/provider. ServiceLoader is designed to discover providers without forcing the consumer to depend on the implementation package.

**Question 8.** Does `ServiceLoader.reload()` replace old class bytecode with a new version in the same ClassLoader?

**Answer:** No. `reload()` clears the ServiceLoader cache; it does not replace the runtime class definition already loaded by the JVM.

**Question 9.** A provider module is on the module path, yet ServiceLoader returns empty. What needs to be checked?

**Answer:** Whether the provider descriptor has `provides`, whether the module has been resolved into the active layer/graph, whether the consumer has `uses`, whether the service API has the same runtime identity, and which loader/layer the invoked ServiceLoader method uses.

**Question 10.** When should the `provider()` provider factory be considered?

**Answer:** When an explicit named module needs a factory to create a service instance per the contract without wanting the provider class to directly implement the SPI with a public no-arg constructor; it must follow the method signature and be verified with the compiler/runtime.

## 16. Implementation checklist

- [ ] Design a stable service interface or abstract class in a dedicated API module.
- [ ] Have the API module `exports` the package containing the service type to modules that need it.
- [ ] Have the consumer `requires` the API as needed and declare `uses ServiceType;`.
- [ ] Have the provider `requires` the API and properly register `provides ServiceType with Provider;`.
- [ ] Ensure the provider class has a valid constructor or factory method, and its runtime dependencies are present.
- [ ] Do not export the implementation package merely so ServiceLoader can access it.
- [ ] Ensure the provider module is resolved into the right runtime graph/layer.
- [ ] Do not package duplicate copies of the service API type across multiple loaders.
- [ ] Use `ServiceLoader` appropriately; handle provider errors and ordering deliberately.
- [ ] If plugin reloading is needed, manage the module layer/ClassLoader and provider lifecycle explicitly.
- [ ] For the classpath, verify `META-INF/services/<service binary name>` has the correct path and provider names.
- [ ] Test with artifacts, module path, and launch commands matching the deployment environment.

## 17. Conclusion and references

In JPMS, `uses` and `provides` are **two sides of a service-loading contract**. The consumer declares the service type it will use; the provider module publishes the providing class; `ServiceLoader` locates providers from the appropriate modules/resources according to the actual graph and loaders. `requires` and `exports` remain necessary for type accessibility, yet **are not the provider registration mechanism**.

A sustainable design places the common SPI in a shared module/loader, keeps implementations in provider modules without exporting them, verifies that providers are resolved, uses ServiceLoader with an explicit provider-selection policy, and does not rely on unguaranteed discovery order.

### Official references

- Java SE 17 `ServiceLoader` API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html
- JLS 17 §7.7.1, *Module Directives* (`requires`, `exports`, `uses`, `provides`): https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7.1
- Java SE 17 `java` launcher, module path/add-modules/show-module-resolution: https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- Java SE 17 `javac`, module-source-path: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html
- Java SE 17 `ModuleLayer` API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html
- Java SE 17 `ClassLoader` API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
