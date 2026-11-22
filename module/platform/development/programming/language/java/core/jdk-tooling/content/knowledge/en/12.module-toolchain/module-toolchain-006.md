# The `provides` Directive in the Java Module System

## Objectives

After this lesson, you will be able to explain the `provides` directive in the Java Platform Module System (JPMS); declare a module that provides an implementation for a service; combine `provides` with `uses` and `ServiceLoader`; distinguish between service API, provider, and consumer; choose between a provider constructor and a provider factory method; package, run, and inspect modules on the module path; and diagnose common discovery errors.

## 1. What is `provides`?

Since Java 9, JPMS allows a module to describe the services it provides. In the `module-info.java` file, the directive:

~~~java
provides com.example.codec.spi.Codec
    with com.example.codec.provider.impl.Utf8Codec;
~~~

means the current module registers the class `Utf8Codec` as a service provider for the service type `Codec`.

A service is typically an interface or abstract class describing a capability that an application needs, for example:

- Data encoders/decoders.
- Database connection drivers.
- File format parsers.
- Logging or security providers.
- Plugins that extend an application feature.

The consumer knows the service API and invokes it through `ServiceLoader`. The consumer does not need to know the name or package of the concrete implementation. The provider module registers its implementation using `provides`.

This model separates three roles:

| Component | Responsibility |
|---|---|
| Service API | Defines the interface/abstract class and usage contract |
| Provider module | Supplies one or more implementations of the service |
| Consumer module | Declares the service it needs and locates providers at runtime |

`provides` is not a method call and does not instantiate objects immediately when the JVM starts. It is metadata in the module descriptor so that the module system and `ServiceLoader` can locate providers when the application requests them.

## 2. Syntax and Placement in module-info.java

General syntax:

~~~java
provides ServiceType
    with ProviderType1, ProviderType2;
~~~

- `ServiceType` is the service type known to the consumer.
- After `with` are one or more provider classes belonging to the module declaring the directive.
- Each provider is separated by a comma.
- The directive ends with a semicolon.
- Type names are usually fully qualified with their package so the descriptor is unambiguous.

Example:

~~~java
module com.example.image.provider {
    requires com.example.image.api;

    provides com.example.image.spi.ImageCodec
        with com.example.image.provider.PngCodec,
             com.example.image.provider.JpegCodec;
}
~~~

A module can provide multiple different services using multiple `provides` directives. For the same service type, a module may have only one `provides` directive; if multiple implementations are needed, list them in the same `with` clause.

The provider class must be declared in the same module that contains the `provides` directive. You cannot use a directive in module A to register a provider class belonging to module B.

## 3. Distinguishing `provides`, `uses`, `requires`, and `exports`

These four directives often appear together, but they serve different purposes:

| Directive | Question It Answers |
|---|---|
| `requires` | Which modules does this module depend on? |
| `exports` | Which packages are accessible to other modules? |
| `uses` | Which service does this module need to find providers for? |
| `provides ... with ...` | Which provider does this module supply for which service? |

Example of a provider module:

~~~java
module com.example.codec.provider {
    requires com.example.codec.api;

    provides com.example.codec.spi.Codec
        with com.example.codec.provider.impl.Utf8Codec;
}
~~~

The provider module needs `requires` for the module containing the service API in order to reference the `Codec` interface. It uses `provides` to register the implementation.

Example of a consumer module:

~~~java
module com.example.codec.app {
    requires com.example.codec.api;

    uses com.example.codec.spi.Codec;
}
~~~

The consumer needs `requires` for the API module because its source code calls methods of the `Codec` interface. The consumer declares `uses` to be allowed to look up providers of that service using `ServiceLoader`.

Typically, the consumer **does not need** `requires com.example.codec.provider`. This is a key benefit of service abstraction: the consumer depends on the API, while the provider is discovered via module resolution and service loading.

### The Service API Must Be Exported

If the service interface resides in a separate module, the package containing the interface must be exported for consumers and providers to use:

~~~java
module com.example.codec.api {
    exports com.example.codec.spi;
}
~~~

The provider implementation package usually does not need to be exported. The `provides` module descriptor directive allows registering an implementation without exposing internal packages to all modules. This provides better encapsulation.

`exports` and `opens` also have different meanings: `exports` grants access to public types according to module rules; `opens` allows deep reflection. Registering a service with `provides` does not by itself mean the provider package needs to be opened for reflection.

## 4. Two Ways to Create a Service Provider

JPMS supports two ways for `ServiceLoader` to instantiate a provider declared with `provides`.

### Way 1: Provider Class Implements the Service and Has a Public No-Arg Constructor

This is the most direct and commonly used approach:

~~~java
package com.example.codec.provider.impl;

import com.example.codec.spi.Codec;

public class Utf8Codec implements Codec {

    public Utf8Codec() {
    }

    @Override
    public String encode(String input) {
        return "UTF-8:" + input;
    }
}
~~~

Module descriptor:

~~~java
module com.example.codec.provider {
    requires com.example.codec.api;

    provides com.example.codec.spi.Codec
        with com.example.codec.provider.impl.Utf8Codec;
}
~~~

In this case:

- The provider class must be `public`.
- The provider class must be a top-level class or a static nested class.
- The provider must implement the service type (or be a subtype of the service class).
- The provider must have a `public` no-arg constructor.
- `ServiceLoader` creates the instance via that constructor.

If a class declares no constructors, the compiler may generate a default constructor; however, the provider must satisfy the public no-arg constructor requirement. Once you declare a custom constructor with parameters, do not assume the compiler still generates a default constructor.

### Way 2: A Provider Method Named `provider()`

Since Java 9, a provider class can declare a `public static` method named exactly `provider`, taking no parameters and returning a subtype of the service:

~~~java
package com.example.codec.provider.impl;

import com.example.codec.spi.Codec;

public final class Utf8CodecFactory {

    public static Codec provider() {
        return new Utf8Codec();
    }
}
~~~

The module descriptor registers the factory class:

~~~java
provides com.example.codec.spi.Codec
    with com.example.codec.provider.impl.Utf8CodecFactory;
~~~

In this form, the `Utf8CodecFactory` class does not need to implement `Codec` itself; `ServiceLoader` calls the `provider()` method to obtain the object that implements the service.

The provider method must satisfy:

- Has the `public static` modifiers.
- Method name is `provider`.
- Takes no parameters.
- Return type is the service type or a subtype of the service type.
- There is only one valid provider method for the provider class.

The factory approach is useful when creating the implementation requires configuration, selecting a specific object, or hiding the actual implementation class. If the provider method returns `null` or throws an exception, loading the provider may fail with a `ServiceConfigurationError`.

### Comparing the Two Approaches

| Criterion | Provider Constructor | Provider Method |
|---|---|---|
| Must the provider class implement the service? | Yes | Not necessarily |
| How the instance is created | Public no-arg constructor | Public static `provider()` |
| Return value | The provider instance itself | Object returned by the factory |
| Best suited when | Simple implementation | Factory logic or hiding implementation is needed |
| Is a public no-arg constructor required? | Yes | No, if a valid provider method is used |

If a provider class has a valid provider method, `ServiceLoader` uses that method to create the provider. If there is no provider method, it uses the provider constructor and the provider class must be a subtype of the service.

## 5. Complete Example: API, Provider, and Consumer

The example below creates three independent modules. The provider supplies an implementation of the `Codec` service; the consumer locates and invokes the implementation via `ServiceLoader`.

### Directory Structure

~~~text
project/
└── src/
    ├── com.example.codec.api/
    │   ├── module-info.java
    │   └── com/example/codec/spi/Codec.java
    ├── com.example.codec.provider/
    │   ├── module-info.java
    │   └── com/example/codec/provider/impl/Utf8Codec.java
    └── com.example.codec.app/
        ├── module-info.java
        └── com/example/codec/app/Main.java
~~~

### Module 1: Service API

File `src/com.example.codec.api/module-info.java`:

~~~java
module com.example.codec.api {
    exports com.example.codec.spi;
}
~~~

File `src/com.example.codec.api/com/example/codec/spi/Codec.java`:

~~~java
package com.example.codec.spi;

public interface Codec {
    String encode(String input);
}
~~~

The API module only exposes the package containing the service interface.

### Module 2: Provider

File `src/com.example.codec.provider/module-info.java`:

~~~java
module com.example.codec.provider {
    requires com.example.codec.api;

    provides com.example.codec.spi.Codec
        with com.example.codec.provider.impl.Utf8Codec;
}
~~~

File `src/com.example.codec.provider/com/example/codec/provider/impl/Utf8Codec.java`:

~~~java
package com.example.codec.provider.impl;

import com.example.codec.spi.Codec;

public class Utf8Codec implements Codec {

    public Utf8Codec() {
    }

    @Override
    public String encode(String input) {
        return "UTF-8:" + input;
    }
}
~~~

The package `com.example.codec.provider.impl` is not exported. The consumer does not need to import or call `Utf8Codec` directly.

### Module 3: Consumer Application

File `src/com.example.codec.app/module-info.java`:

~~~java
module com.example.codec.app {
    requires com.example.codec.api;

    uses com.example.codec.spi.Codec;
}
~~~

File `src/com.example.codec.app/com/example/codec/app/Main.java`:

~~~java
package com.example.codec.app;

import com.example.codec.spi.Codec;
import java.util.ServiceLoader;

public class Main {

    public static void main(String[] args) {
        ServiceLoader<Codec> loader =
                ServiceLoader.load(Codec.class);

        for (Codec codec : loader) {
            System.out.println(codec.encode("hello"));
        }
    }
}
~~~

The consumer only imports `Codec` and `ServiceLoader`. It does not import `Utf8Codec` and does not declare `requires com.example.codec.provider`.

### Compiling All Three Modules

Open a terminal in the `project` directory:

~~~bash
javac --module-source-path src -d out -m com.example.codec.api,com.example.codec.provider,com.example.codec.app
~~~

Options:

- `--module-source-path src` specifies the root directory containing the sources of the modules.
- `-d out` places the compiled class files into the `out` directory organized by module.
- `-m` selects the modules to compile; the compiler handles dependencies between them.

After compiling, the output structure looks like:

~~~text
out/
├── com.example.codec.api/
│   ├── module-info.class
│   └── com/example/codec/spi/Codec.class
├── com.example.codec.provider/
│   ├── module-info.class
│   └── com/example/codec/provider/impl/Utf8Codec.class
└── com.example.codec.app/
    ├── module-info.class
    └── com/example/codec/app/Main.class
~~~

### Running the Consumer on the Module Path

~~~bash
java --module-path out -m com.example.codec.app/com.example.codec.app.Main
~~~

Exact output:

~~~text
UTF-8:hello
~~~

When launching the consumer module, module resolution can bind observable provider modules on the module path because the consumer declares `uses` and the provider module declares `provides`. `ServiceLoader` then locates and instantiates the provider when the loop requests elements.

To observe the module resolution process:

~~~bash
java --show-module-resolution --module-path out -m com.example.codec.app/com.example.codec.app.Main
~~~

Resolution details are printed to stderr; the application output remains `UTF-8:hello`.

## 6. Packaging into Modular JARs

The compiled modules can be packaged into three separate JARs:

~~~bash
mkdir dist
jar --create --file dist/com.example.codec.api.jar -C out/com.example.codec.api .
jar --create --file dist/com.example.codec.provider.jar -C out/com.example.codec.provider .
jar --create --file dist/com.example.codec.app.jar -C out/com.example.codec.app .
~~~

Each JAR has `module-info.class` at its root, making it a modular JAR with a module name taken from the descriptor rather than inferred from the filename.

Inspect the provider descriptor:

~~~bash
jar --describe-module --file dist/com.example.codec.provider.jar
~~~

In the output, look for the module name and the service-providing directive, similar to:

~~~text
com.example.codec.provider
requires com.example.codec.api
provides com.example.codec.spi.Codec with com.example.codec.provider.impl.Utf8Codec
~~~

Run the application from the directory containing the three modular JARs:

~~~bash
java --module-path dist -m com.example.codec.app/com.example.codec.app.Main
~~~

Output:

~~~text
UTF-8:hello
~~~

There is no need to add the provider module to `requires` in the app module. Module resolution discovers the provider through service binding when the consumer module uses the service and the provider module is present in the set of observable modules.

## 7. Why Are Provider Packages Usually Not Exported?

One of the biggest benefits of JPMS services is that a provider can be discovered without exposing its implementation package.

Example:

~~~java
module com.example.codec.provider {
    requires com.example.codec.api;

    provides com.example.codec.spi.Codec
        with com.example.codec.provider.impl.Utf8Codec;
}
~~~

The module does not have:

~~~java
exports com.example.codec.provider.impl;
~~~

This means consumer code cannot directly access the public class `Utf8Codec` simply by importing it as a public API. However, the service loader can still locate and instantiate the provider based on the `provides` metadata.

This design allows the provider to swap implementations without forcing the consumer to depend on a specific class. For example, the provider module can replace `Utf8Codec` with a new implementation while the `Codec` service contract and consumer code remain unchanged.

Only export a provider package if it is genuinely an API that other modules need to call directly. Do not export it just to make `ServiceLoader` work.

## 8. Multiple Providers for the Same Service

A single directive can register multiple providers:

~~~java
provides com.example.codec.spi.Codec
    with com.example.codec.provider.impl.Utf8Codec,
         com.example.codec.provider.impl.Base64Codec,
         com.example.codec.provider.impl.HexCodec;
~~~

The consumer can iterate over all providers:

~~~java
for (Codec codec : ServiceLoader.load(Codec.class)) {
    System.out.println(codec.encode("hello"));
}
~~~

`ServiceLoader` can locate providers from multiple modules. You should not rely on ordering across different modules if the application requires a specific provider. If selection is needed, add metadata or methods to the service contract to evaluate capability/priority, or let the user configure the desired provider.

Having no providers is also a valid situation from the API perspective: the iterator may be empty. The consumer should clearly define its behavior when a service has no implementations.

## 9. How Does `ServiceLoader` Work?

`ServiceLoader` is the standard API for discovering and loading service providers.

~~~java
ServiceLoader<Codec> loader =
        ServiceLoader.load(Codec.class);
~~~

When code calls `iterator()`, `for-each`, `findFirst()`, or operates on a stream, providers are discovered and instantiated on demand. Discovery and instantiation are lazy; simply calling `load` does not immediately create objects for every provider.

Important APIs:

| API | Purpose |
|---|---|
| `ServiceLoader.load(Codec.class)` | Creates a loader using the thread context class loader |
| `iterator()` | Iterates and instantiates providers on demand |
| `stream()` | Iterates over provider descriptors before obtaining instances |
| `reload()` | Clears the cache of providers already discovered by the loader |
| `ServiceLoader.load(layer, Codec.class)` | Finds providers in a `ModuleLayer` and its parent layers |

`ServiceLoader` caches loaded providers within a loader instance. When the provider environment changes in a way the application manages, `reload()` can be called to clear the cache. Do not share the same `ServiceLoader` instance across multiple threads without proper synchronization.

### Inspecting Providers Before Creating Instances

`stream()` returns `ServiceLoader.Provider` objects. They allow inspecting the provider type and filtering before calling `get()` to create an instance:

~~~java
ServiceLoader<Codec> loader =
        ServiceLoader.load(Codec.class);

loader.stream()
      .map(ServiceLoader.Provider::type)
      .forEach(System.out::println);
~~~

This is useful when the application wants to inspect metadata or select a provider prior to instantiation. With a provider factory, `type()` may represent the return type of the provider method; call `get()` to obtain the service instance.

## 10. Rules and Restrictions of the `provides` Directive

According to the Java Language Specification, key conditions include:

- The service type must be accessible from the current module; an enum cannot be used as a service in a `provides` directive.
- Each provider must be a `public` class or interface, either top-level or static nested.
- Each provider must be declared in the same module that contains the directive.
- If a provider has a provider method, that method must be `public static`, named `provider`, take no parameters, and return a subtype of the service.
- If there is no provider method, the provider must have a `public` no-arg constructor and be a subtype of the service.
- A module must not declare multiple `provides` directives for the same service.
- A provider must not be listed more than once in the same directive.

These conditions are checked by the compiler at compile time when sufficient module/type information is available. Some errors only surface at runtime if the provider cannot be loaded or instantiated in the actual environment.

### Some Invalid Examples

Non-public provider:

~~~java
class HiddenCodec implements Codec {
    public String encode(String input) {
        return input;
    }
}
~~~

Provider with no public no-arg constructor and no provider method:

~~~java
public class ConfiguredCodec implements Codec {
    public ConfiguredCodec(String charset) {
    }

    public String encode(String input) {
        return input;
    }
}
~~~

Provider method returning a type incompatible with the service:

~~~java
public class CodecFactory {
    public static String provider() {
        return "not a Codec";
    }
}
~~~

These examples do not satisfy the corresponding provider requirements. Fix the class or provider method according to one of the two valid mechanisms described above.

## 11. Differences Between Named Modules and Classpath Providers

Java can locate service providers in both named modules and on the classpath, though the registration mechanism differs.

| Environment | Provider Registration Mechanism |
|---|---|
| Explicit named module | `provides Service with Provider;` directive in `module-info.java` |
| Classpath / unnamed module | File `META-INF/services/<fully-qualified-service-name>` |
| Automatic module on module path | Provider configuration file following `ServiceLoader` rules; provider requires a public no-arg constructor |

For the classpath, the provider JAR contains the file:

~~~text
META-INF/services/com.example.codec.spi.Codec
~~~

File contents:

~~~text
com.example.codec.provider.impl.Utf8Codec
~~~

Each line is a provider class name. This registration approach predates Java 9 and remains supported for compatibility.

With an explicit named module, you should declare `provides` in the module descriptor. You do not need to also create a provider configuration file for the same provider in a named module; `ServiceLoader` ignores provider names in the configuration file if that provider is already declared by the named module.

An automatic module has no explicit `module-info.java`; therefore, it cannot declare its own `provides` directive. The provider constructor rule applies to providers discovered via the provider configuration file in this case; provider methods are not supported as they are for explicit named modules.

## 12. Common Errors and How to Fix Them

### Consumer Forgets the `uses` Directive

**Symptom:** Calling `ServiceLoader.load(Service.class)` from an explicit named module throws `ServiceConfigurationError`.

**Cause:** The consumer module has not declared the service in `uses`.

**Fix:** Add:

~~~java
uses com.example.codec.spi.Codec;
~~~

to the consumer's `module-info.java`, recompile, and rerun.

### Provider Not Found

**Symptom:** `ServiceLoader` returns no providers.

**Possible causes:**

- The provider module is not on the module path.
- The provider module is not observable or is not resolved into the module layer.
- Missing `provides` directive or incorrect service/provider class name.
- The consumer does not declare `uses`.
- The module path points to the wrong directory or JAR.

**Fix:** Check `jar --describe-module`, the module path, module resolution, and module descriptors. Use `--show-module-resolution` to observe the module graph at startup.

### Provider Lacks a Public No-Arg Constructor

**Symptom:** `ServiceConfigurationError` when `ServiceLoader` instantiates the provider.

**Cause:** The provider declares neither a valid provider method nor a public no-arg constructor.

**Fix:** Add a `public` no-arg constructor or use a `public static` no-arg `provider()` method with a compatible return type.

### Invalid Provider Method

**Symptom:** The provider is not instantiated or `ServiceConfigurationError` occurs.

**Cause:** Wrong method name, not `public static`, has parameters, incompatible return type, returns `null`, or throws an exception.

**Fix:** Verify the method is `public static`, named exactly `provider`, takes no parameters, and returns the service type or a subtype; ensure the factory does not return `null`.

### Provider Package Exported Too Broadly

**Symptom:** The module descriptor has many public implementation packages even though consumers only need the service interface.

**Cause:** Confusing `provides` with `exports`.

**Fix:** Keep the service API package exported; keep provider implementation packages encapsulated unless there is a genuine need to expose them publicly.

### Errors While Iterating Over `ServiceLoader`

**Symptom:** `ServiceConfigurationError` occurs when calling `hasNext()`, `next()`, or processing the stream.

**Cause:** The provider class cannot be loaded, the constructor/factory fails, the provider method returns `null`, or there is a configuration error.

**Fix:** Read the cause of the error and check the module descriptor, classpath/module path, and provider initialization. Because loading is lazy, errors can surface during iteration rather than immediately at `ServiceLoader.load()`.

### Misusing Module Path and Classpath

**Symptom:** The API or provider module is not found, or the app runs without discovering providers.

**Cause:** Modular JARs are placed on the classpath instead of the module path, or the module path is missing required directories/JARs.

**Fix:** Use `--module-path` for named modules and run the app with `-m module/class`. For traditional classpath applications, use `-cp` and provider configuration files.

## 13. When Should You Use `provides`?

Use JPMS services when:

- An API has multiple interchangeable implementations.
- The consumer should not depend directly on implementation modules.
- You want to package plugins/providers as independent modules.
- You want to keep implementation packages unexported.
- You want a framework or application to discover providers at runtime.
- You want to swap a provider for another module without changing consumer code.

You do not need to use `ServiceLoader` for every method call. If an application only has a single fixed implementation and does not need extensibility, direct dependency injection or constructor injection may be simpler.

Service abstraction should reflect a genuine extension point. Do not create a service interface just to wrap a single class if there is no need to swap or discover implementations.

## 14. Implementation Checklist

- [ ] The service API is in a package exported by the API module.
- [ ] The provider module has a `requires` directive for the module containing the service type.
- [ ] The provider module declares `provides Service with Provider;`.
- [ ] The provider class is `public` and is top-level or static nested.
- [ ] The provider uses a public no-arg constructor or a valid provider method.
- [ ] The consumer module has `requires` for the service API.
- [ ] The consumer module declares `uses Service;`.
- [ ] The consumer does not depend directly on the provider module unless necessary.
- [ ] The provider implementation package is not exported unless it is a public API.
- [ ] The provider module is present on the module path/resolved module layer.
- [ ] The descriptor has been verified with `jar --describe-module`.
- [ ] `ServiceLoader` has been tested, including the case where no providers are present.
- [ ] `ServiceConfigurationError` is handled appropriately.
- [ ] No reliance on provider ordering across modules unless a clear contract exists.

## 15. Official References

- [Java Language Specification, Java SE 26 — §7.7.3 Service Consumption](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-7.html#jls-7.7.3) — the `uses` directive and service consumption rules.
- [Java Language Specification, Java SE 26 — §7.7.4 Service Provision](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-7.html#jls-7.7.4) — syntax and provider rules for the `provides` directive.
- [ServiceLoader — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ServiceLoader.html) — discovery, provider constructors, provider methods, lazy loading, caching, and configuration errors.
- [ServiceLoader.Provider — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ServiceLoader.Provider.html) — inspecting provider types and obtaining provider instances.
- [ModuleDescriptor.Builder — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/module/ModuleDescriptor.Builder.html) — API for creating module descriptors and declaring service providers.

The `provides` directive is the service provider registration mechanism of JPMS. When combined properly with a service API, `uses`, `ServiceLoader`, and the module path, an application can discover implementations while maintaining clear module boundaries and encapsulation.
