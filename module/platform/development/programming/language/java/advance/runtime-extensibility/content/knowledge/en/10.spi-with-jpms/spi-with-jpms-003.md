# Declaring `requires`, `exports`, and `uses` on the Service Consumer Side in JPMS

## 1. Problem: What Does an SPI-Consuming Module Need to Declare?

The Java Platform Module System (JPMS) allows an application to discover implementations of a Service Provider Interface (SPI) without directly importing the implementation classes. A service is typically an interface or an abstract class; another module publishes a provider via `provides ... with ...`, while the consuming module discovers providers using `java.util.ServiceLoader`.

When writing an **explicit named module** as a consumer, there are three directives that are easily confused:

- **`requires module.name;`**: the consumer module *can read* the module containing the service type or another dependency.
- **`exports package.name;`**: the module *that owns the package* allows other modules to access the `public` types in that package. If the SPI is in a separate module, **the SPI module itself** exports the interface package; the consumer only exports its own packages when exposing an API to other modules.
- **`uses package.name.Service;`**: the consumer module declares that it will *look up providers for the service* via `ServiceLoader`.

These three directives do three different things. `requires` does not register a service consumer, `uses` does not automatically make an API module readable, and `exports` does not discover or instantiate any provider on its own.

On the provider side, the corresponding declaration is:

~~~java
module demo.provider {
    requires demo.spi;
    provides demo.spi.GreetingService
        with demo.provider.HelloGreeting;
}
~~~

The consumer **usually does not need** `requires demo.provider;`. This is key to swapping or adding implementations without forcing consumer code to depend on a concrete implementation module.

## 2. Who Owns Which Directive?

Suppose there are four modules:

| Module | Responsibility | Primary Directives |
|---|---|---|
| `demo.spi` | Defines the `GreetingService` contract | `exports demo.spi;` |
| `demo.host` | Direct consumer calling `ServiceLoader`; also provides an API to the app | `requires demo.spi;`, `uses demo.spi.GreetingService;`, and `exports demo.host.api;` |
| `demo.provider` | Defines the implementation and registers the provider | `requires demo.spi;`, `provides ... with ...;` |
| `demo.app` | Application module calling the host's public API | `requires demo.host;` |

Conceptual relationships:

~~~text
demo.app
    |
    | requires
    v
demo.host ---requires----> demo.spi
    |                         |
    | uses                    | exports demo.spi
    +-- demo.spi.GreetingService
                              ^
                              |
demo.provider --requires------+
    |
    +-- provides demo.spi.GreetingService
                  with demo.provider.HelloGreeting
~~~

The `requires` arrows represent **module readability** relationships. The `uses`/`provides` pair represents the **service discovery contract**, without creating an implementation import relationship from host to provider.

It is necessary to identify accurately **which module contains the `ServiceLoader` call**, not merely which module contains the `main` method. If `demo.app` calls `GreetingEngine.run()`, but the code inside `GreetingEngine` in `demo.host` is what calls `ServiceLoader.load(...)`, then `uses` belongs to `demo.host`.

## 3. `requires`: The Consumer Reads the Module Containing the API

Example descriptor:

~~~java
module demo.host {
    requires demo.spi;
    uses demo.spi.GreetingService;
}
~~~

`requires demo.spi;` establishes a dependency from `demo.host` to `demo.spi`. When the module graph is resolved, the consumer can read the SPI module. To import `demo.spi.GreetingService`, the `demo.spi` package must also be **exported** by its owning module to the consumer, and the interface must have appropriate accessibility (`public` here).

**`requires` is not the same as `uses`.** A module that can read a service interface has not yet declared permission to use `ServiceLoader` for that interface. Conversely, the `uses` directive does not replace `requires` when the service resides in another module and the consumer needs to access that type.

The following snippet only illustrates API usage and is not a standalone program:

~~~java
import demo.spi.GreetingService;

public final class ConsumerHelper {
    public static String describe(GreetingService provider) {
        return provider.id();
    }
}
~~~

If the consumer module cannot read `demo.spi`, the compiler cannot use `GreetingService` as shown above. Adding the JAR containing the interface to the module path **does not automatically bypass** readability rules.

### Do Not `requires` a Provider Just to Find a Service

In an extensible design, the host should depend on the **API contract**. Write:

~~~java
module demo.host {
    requires demo.spi;
    uses demo.spi.GreetingService;
}
~~~

instead of reflexively adding:

~~~java
module demo.host {
    requires demo.spi;
    requires demo.provider;
    uses demo.spi.GreetingService;
}
~~~

`requires demo.provider` only makes sense if the host genuinely needs to read that module as a direct dependency. Putting it in the descriptor merely because a provider exists can force the host to know implementation names, creating unnecessary coupling and making plugin replacement harder.

### `requires transitive`

When a host module exports an API whose public signatures reference a type from the SPI module, the host may want its clients to read the SPI module through the host:

~~~java
module demo.host {
    requires transitive demo.spi;
    uses demo.spi.GreetingService;
    exports demo.host.api;
}
~~~

Another module with `requires demo.host;` then also reads `demo.spi` transitively. `requires transitive` is **not needed** for every dependency: if the host's public API only returns `String` or `void` and does not expose SPI types, plain `requires demo.spi` is usually the cleaner choice.

`requires static` is for dependencies that are mandatory at compile time but optional at runtime; it should not be used to "make optional" a module containing a service type that the application definitely needs at execution time.

## 4. `exports`: The Package-Owning Module Exposes Its Public API

Suppose the service interface is at `demo.spi/demo/spi/GreetingService.java`. Only **module `demo.spi`** owns the `demo.spi` package, so only it can declare:

~~~java
module demo.spi {
    exports demo.spi;
}
~~~

This directive allows other modules to access `public` types in the `demo.spi` package when proper readability is established. It does not make package-private classes public, does not open private fields for deep reflection, and does not guarantee that a provider will be loaded.

### Why Might `exports` Appear in a Consumer Module?

If the consumer also publishes an API for an application module:

~~~java
module demo.host {
    requires demo.spi;
    uses demo.spi.GreetingService;
    exports demo.host.api;
}
~~~

then `exports demo.host.api;` is how the host allows `demo.app` to import the `demo.host.api.GreetingEngine` class. This is **different** from exporting the SPI interface. A consumer cannot export `demo.spi` on its own if that package belongs to a different module.

If `demo.host` is just a standalone runnable module and does not expose an API to external modules, `exports demo.host.api;` can be omitted when no other module uses that package. Service discovery inside the host itself will still work if `requires`/`uses` and the provider configuration are valid.

### Qualified Exports

To grant access only to specific named modules, the API module can declare:

~~~java
module demo.spi {
    exports demo.spi to demo.host, demo.provider;
}
~~~

`exports ... to ...` opens public package access only to the listed modules. If a project has third-party providers whose module names are not known in advance, this kind of restricted export can make extensibility harder.

Distinguish between:

- `exports package;`: standard public API for modules allowed to read it.
- `exports package to module1, module2;`: public API for specific modules.
- `opens package;` or `opens ... to ...;`: for deep reflection under JPMS rules; not synonymous with exporting.
- `provides Service with Implementation;`: announces the provider to `ServiceLoader`; **does not require exporting the implementation package** just so the consumer can discover it.

With SPI, a provider's implementation package should normally be kept internal. The consumer interacts through the interface exported by the API module rather than importing the implementation directly.

## 5. `uses`: Marking the Module That Performs Service Lookup

In the descriptor of the module containing the code that calls `ServiceLoader`:

~~~java
module demo.host {
    requires demo.spi;
    uses demo.spi.GreetingService;
}
~~~

The name after `uses` is the **service type name**, such as `demo.spi.GreetingService`—**not** the module name `demo.spi` and **not** the class `demo.provider.HelloGreeting`.

API example:

~~~java
ServiceLoader<GreetingService> loader =
        ServiceLoader.load(GreetingService.class);

for (GreetingService provider : loader) {
    System.out.println(provider.id());
}
~~~

This is an illustrative snippet inside the consumer module: `demo.spi.GreetingService` and `java.util.ServiceLoader` must be imported. Creating a `ServiceLoader` does not necessarily locate or instantiate providers yet; iterating over it performs the bulk of the work lazily.

Under the Java 17 contract, when code inside an **explicit named module** calls `ServiceLoader`, the module containing the call must declare `uses` for the service. If `uses` is removed from `demo.host` while the code still calls `ServiceLoader.load(GreetingService.class)`, the call can throw `ServiceConfigurationError` because the caller module has not declared consumption of the service. In that case, adding `requires` or `exports` cannot substitute for `uses`.

### Does `uses` Create a Provider?

No. The `uses` directive does not specify an implementation, install a plugin, or create instances. The provider module must have a `provides ... with ...` descriptor or equivalent metadata in another provider model; the provider module must be within the resolved module graph/layer scope and the appropriate lookup path. `ServiceLoader` performs discovery when the code runs.

### Does the Module with `main` Always Need `uses`?

No. `uses` belongs to the module that **directly uses ServiceLoader for that service**. If `demo.app` only calls `GreetingEngine.run()`, it does not necessarily need to declare `uses`. In the complete example below, `demo.host` is where `ServiceLoader.load(...)` is called, so `uses` lives in `demo.host/module-info.java`.

## 6. Complete Java 17+ Example: Four Named Modules

This example clarifies all three consumer-side directives and verifies that the provider is still discovered while the host **does not require the implementation module**. The source code consists of eight files.

### 6.1. Project Structure

~~~text
jpms-spi-demo/
  src/
    demo.spi/
      module-info.java
      demo/spi/GreetingService.java
    demo.host/
      module-info.java
      demo/host/api/GreetingEngine.java
    demo.provider/
      module-info.java
      demo/provider/HelloGreeting.java
    demo.app/
      module-info.java
      demo/app/Main.java
  mods/                   (generated by javac)
~~~

### 6.2. The SPI Module

**`src/demo.spi/module-info.java`**:

~~~java
module demo.spi {
    exports demo.spi;
}
~~~

**`src/demo.spi/demo/spi/GreetingService.java`**:

~~~java
package demo.spi;

public interface GreetingService {
    String id();
    String greet(String name);
}
~~~

The API module does not need to know which consumers or providers will use it. Because this API exposes a public interface to other modules, the interface's package must be exported.

### 6.3. The Consumer/Host Module

**`src/demo.host/module-info.java`**:

~~~java
module demo.host {
    requires demo.spi;
    uses demo.spi.GreetingService;
    exports demo.host.api;
}
~~~

This is an example featuring **all three directives in the consumer module**: `requires` to read the SPI, `uses` to discover providers, and `exports` to let `demo.app` use the host API.

**`src/demo.host/demo/host/api/GreetingEngine.java`**:

~~~java
package demo.host.api;

import demo.spi.GreetingService;
import java.util.ServiceLoader;

public final class GreetingEngine {
    private GreetingEngine() {}

    public static void run() {
        for (GreetingService service :
                ServiceLoader.load(GreetingService.class)) {
            System.out.println(
                    service.id() + " -> " + service.greet("Java"));
        }
    }
}
~~~

`GreetingEngine.run()` finds providers of `GreetingService` using `ServiceLoader`. In this sample run, there is one implementation. The host depends on the SPI, but does not import `demo.provider.HelloGreeting` and does not `requires demo.provider`.

### 6.4. The Provider Module

**`src/demo.provider/module-info.java`**:

~~~java
module demo.provider {
    requires demo.spi;
    provides demo.spi.GreetingService
        with demo.provider.HelloGreeting;
}
~~~

**`src/demo.provider/demo/provider/HelloGreeting.java`**:

~~~java
package demo.provider;

import demo.spi.GreetingService;

public final class HelloGreeting implements GreetingService {
    @Override
    public String id() {
        return "hello";
    }

    @Override
    public String greet(String name) {
        return "Xin chao, " + name + "!";
    }
}
~~~

The provider module **also** needs to read the SPI module to implement the interface. However, it does not export the `demo.provider` package: the `provides ... with ...` declaration is sufficient for JPMS/`ServiceLoader` to recognize the provider once the module is resolved. The example uses a public class with a public default constructor, satisfying standard provider instantiation rules.

### 6.5. The Application Module

**`src/demo.app/module-info.java`**:

~~~java
module demo.app {
    requires demo.host;
}
~~~

**`src/demo.app/demo/app/Main.java`**:

~~~java
package demo.app;

import demo.host.api.GreetingEngine;

public final class Main {
    public static void main(String[] args) {
        GreetingEngine.run();
    }
}
~~~

The application uses the public API from the host, so it needs `requires demo.host;` and the host needs `exports demo.host.api;`. The application does not call `ServiceLoader` directly, so it does not need `uses demo.spi.GreetingService;` in `demo.app`'s descriptor. The `GreetingEngine.run()` API also does not force `demo.app` to import `GreetingService`, so `demo.app` does not need `requires demo.spi;` in this example.

### 6.6. Compiling and Running

Run inside `jpms-spi-demo/` using Bash (Linux/macOS or Git Bash on Windows):

~~~bash
mkdir -p mods

javac --release 17 \
  --module-source-path src \
  -d mods \
  $(find src -type f -name '*.java')

java --module-path mods \
  --add-modules demo.provider \
  --module demo.app/demo.app.Main
~~~

Explanation:

- `--release 17` checks source code and API compatibility against Java 17.
- `--module-source-path src` tells `javac` that the source directory contains submodules.
- `-d mods` generates per-module output, such as `mods/demo.host/module-info.class`.
- `--module-path mods` provides the path to locate named modules at runtime.
- `--add-modules demo.provider` adds the provider as a root to ensure the implementation module **is resolved** for the example; merely placing a module on the module path is not enough to conclude it was resolved.
- `--module demo.app/demo.app.Main` selects the entry point inside the named module `demo.app`.

Program output:

~~~text
hello -> Xin chao, Java!
~~~

This result was verified by compiling with `javac --release 17` and running on OpenJDK 21. Because there is one provider, print order is unambiguous. The sample string uses ASCII in its output for consistency across shell/terminal environments.

On Windows PowerShell, you can create `mods` with `New-Item -ItemType Directory -Force mods`, build the file list `$sources = @(Get-ChildItem src -Recurse -Filter *.java | ForEach-Object FullName)`, and invoke `javac --release 17 --module-source-path src -d mods $sources`. The command `java --module-path mods --add-modules demo.provider --module demo.app/demo.app.Main` works directly in PowerShell.

### 6.7. Why Does the Example Need These Exact Directives?

- `demo.spi` exports the interface; otherwise, the host and provider cannot access public types in the package under JPMS.
- `demo.host` requires the SPI; otherwise, it cannot read the module containing the interface.
- `demo.host` uses the service; otherwise, calling `ServiceLoader` inside an explicit named module lacks the service consumption declaration.
- `demo.host` exports its API; otherwise, `demo.app` cannot import the `GreetingEngine` class from that package.
- `demo.provider` provides the implementation; otherwise, `ServiceLoader` has no provider registration metadata for this module.
- `demo.app` requires the host, because the application needs access to the module supplying `GreetingEngine`.

Separating roles this way clarifies the difference between **API module**, **consumer module**, **provider module**, and **entry point module**.

## 7. Experimenting by Changing Individual Directives to Identify Errors

Restore the working version before testing the next change.

| Change to Try | Outcome to Understand |
|---|---|
| Remove `requires demo.spi;` from `demo.host` | The consumer cannot read the module containing `GreetingService`; references/imports to the service type will fail to compile unless another readability path exists |
| Remove `exports demo.spi;` from `demo.spi` | The consumer/provider cannot access types in the SPI package even with `requires demo.spi;`; typically fails at compile time |
| Remove `uses demo.spi.GreetingService;` from `demo.host` | The consumer may still compile because `requires` remains, but calling `ServiceLoader` inside a named module can throw `ServiceConfigurationError` |
| Remove `exports demo.host.api;` from `demo.host` | `demo.app` cannot import the public `GreetingEngine` class from an unexported package; compile-time error |
| Remove `provides ... with ...;` from `demo.provider` | The provider module no longer registers `HelloGreeting` for the service; if no other provider exists, no implementation is discovered |
| Omit `--add-modules demo.provider` at launch | You cannot assume the provider module was resolved. Depending on launch/service binding, it might still be resolved by another mechanism; inspect the actual graph |
| Add `requires demo.provider;` to the host | Creates a direct dependency on the implementation module, which is not the general way to register or swap providers |

It is crucial to distinguish **compile-time errors caused by readability/exports** from **service lookup errors caused by `uses`/`provides` or provider scope**. Changing the wrong kind of directive may surface a different error without fixing the root cause.

## 8. Reading the Graph, Finding Providers, and Choosing the Right Overload

A program with multiple named modules goes through these steps:

1. **Module discovery:** the runtime sees modules accessible from the module path, system modules, or other sources.
2. **Resolution:** selects root modules, follows `requires` and other rules to form the graph. Service binding may bring additional provider modules into the graph depending on the resolution mode. In the example, `--add-modules demo.provider` explicitly specifies a root.
3. **Layer/class loader:** resolved modules are placed into a module layer, and the runtime assigns appropriate class loaders.
4. **Service discovery:** when consumer code calls `ServiceLoader`, it looks up providers within the loader/layer scope and service metadata, then instantiates them when requested.

The following snippet is **illustrative**, assuming we are in `demo.host` and have already imported `demo.spi.GreetingService` and `java.util.ServiceLoader`:

~~~java
ServiceLoader<GreetingService> fromTccl =
        ServiceLoader.load(GreetingService.class);

ServiceLoader<GreetingService> fromBootLayer =
        ServiceLoader.load(ModuleLayer.boot(), GreetingService.class);
~~~

- `ServiceLoader.load(service)` uses the **thread context class loader** at the time of the call. Usually when running `main`, the TCCL is the application/system loader, though frameworks or plugin hosts may change it.
- `ServiceLoader.load(layer, service)` looks for providers from **named modules** in the specified layer and its parent layers; it does not look for providers in unnamed modules/classpath.
- Both overloads still require an explicit named caller module to declare `uses` for the service.
- Neither overload creates JARs, copies files into a plugin directory, or automatically adds modules to an existing graph.

When designing plugins added at runtime, an application can create a separate `ModuleLayer` and use `ServiceLoader.load(pluginLayer, ServiceType.class)` after resolving providers; this belongs to module layer and plugin lifecycle management and is not automatically accomplished by a `uses` directive.

### Lazy Discovery and Late-Surfacing Errors

`ServiceLoader` is lazy: some metadata lookup/reading and provider instantiation only happen when iterating or streaming. Misconfigured provider declarations, missing classes, invalid providers, or instantiation failures usually surface as `ServiceConfigurationError` while using the service loader. `reload()` clears the provider cache inside that `ServiceLoader` instance, but it does not add modules to the graph, write `module-info.java`, or make new providers appear if the class loader/module layer scope is still wrong.

If multiple providers exist, do not base business rules on the order providers are found across named modules, because module order in a layer is not guaranteed by the API.

## 9. Common Misconceptions

### Misconception 1: The consumer must export the SPI interface from its own module

False when the SPI belongs to another module. A consumer only exports packages **that it owns**. In the example, `demo.spi` exports `demo.spi`; `demo.host` exports `demo.host.api` because another application calls the host API. Do not move `exports demo.spi;` into `demo.host`.

### Misconception 2: `uses` replaces all `requires`

False. `uses` declares service dependence; when a consumer uses a service type from a separate API module, it still needs to read that module and be permitted to access its package. The two concepts—**module readability** and **service consumption**—are independent.

### Misconception 3: `exports` is required for `ServiceLoader` to find a provider class

There is no need to export the implementation package just to use `provides ... with ...`. `ServiceLoader` uses the appropriate provider/module metadata to locate the implementation. Exporting the implementation publicly increases coupling and exposes unnecessary internal APIs.

### Misconception 4: The module with `main` is always the module that needs `uses`

No. The module that actually calls `ServiceLoader` is the one that needs to declare service consumption. An application module may call an API of another module; the library module inside is where `ServiceLoader.load` is executed.

### Misconception 5: Java finds providers in every JAR on the module path

No. Being present on the module path and being resolved into a configuration/module layer are two different things. You must verify roots, dependency relationships, and service binding. For learning programs, using `--add-modules provider.module` makes the selected provider module explicit.

### Misconception 6: `requires transitive` is always better than `requires`

No. `requires transitive` causes modules reading the current module to also read its dependency, which is a public API design decision; overusing it leaks unnecessary dependencies to clients.

### Misconception 7: Classpath providers and named-module providers are declared identically

Not quite. For JARs on the classpath, service provider registration typically uses `META-INF/services/<fully-qualified-service-name>`. For **explicit named modules**, the provider-side descriptor uses `provides ... with ...` and the consumer side uses `uses`. Do not mix up deployment approaches or assume adding a service file will fix a module descriptor missing `uses`.

## 10. Design and Troubleshooting Checklist

Before debugging runtime errors, verify:

1. **Service API:** does the service type exist in the expected package/module with the right visibility?
2. **Readability:** does the consumer module `requires` the SPI module (or have another valid readability relationship)?
3. **Exports:** does the module owning the service package `exports` it to the consumer and provider?
4. **Uses:** has the module containing the `ServiceLoader` call declared `uses` with the exact service name?
5. **Provides:** does the implementation module have `provides Service with Provider;` and is the provider valid?
6. **Resolution:** has the provider module been included in the graph/layer, or is it merely a JAR sitting on disk?
7. **Lookup:** which TCCL, loader, or module layer is the `ServiceLoader.load` overload using?
8. **Instantiation:** is a `ServiceConfigurationError` thrown while iterating or instantiating the provider?
9. **API design:** what exported packages and transitive dependencies do the consumer's clients genuinely need?

After compiling the example, you can inspect descriptors with:

~~~bash
java --module-path mods --describe-module demo.host
java --module-path mods --describe-module demo.provider
~~~

These descriptions let you inspect `requires`, `exports`, `uses`, or `provides` for the relevant modules; exact formatting may vary across JDKs. When `ServiceLoader` returns empty results, verify that the module was resolved and the provider was declared before assuming `uses` automatically locates and installs providers.

## 11. Self-Check Questions

1. **A consumer module `requires demo.spi`, but lacks `uses demo.spi.GreetingService`. Are the requirements met to use `ServiceLoader` from an explicit named module?** No. `uses` is required in the module calling `ServiceLoader`.
2. **An API module has `exports demo.spi`, but the consumer does not `requires demo.spi`. Can the consumer read the service type normally?** No. Exporting does not automatically grant readability.
3. **A provider has `provides` but does not export its implementation package. Can `ServiceLoader` find it?** Yes, if the provider module is resolved and its metadata is valid; the consumer does not need to import the implementation.
4. **Module `demo.app` calls `GreetingEngine.run()`, while `demo.host` calls `ServiceLoader`. Where does `uses` go?** In `demo.host`.
5. **Is a consumer module required to `exports` a package?** No. Only when another module needs to access the consumer's API.
6. **Is placing a provider module on the module path sufficient for all launch configurations to find the provider?** No; it must be resolved within the searched scope.
7. **When should `requires transitive` be considered?** When you want clients of the current module to automatically read its dependency, typically because the public API uses types from that dependent module.
8. **What is the difference between `requires` and `provides`?** `requires` establishes a module dependency/readability; `provides` registers an implementation for a service.
9. **Can `ServiceLoader.reload()` fix a consumer missing `uses` or an unresolved provider?** No.

**Key takeaway:** the consumer reads the **API module** via `requires`, gains access to the **service type** via the owning module's `exports`, and declares its intent to discover providers via `uses`. The consumer `exports` its own packages only when exposing a public API externally. The provider registers its implementation via `provides ... with ...`; module resolution and `ServiceLoader` connect the pieces at runtime.

## References

- [Java SE 17 — ServiceLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html): consumer `uses`, provider `provides`, loader/layer, lazy discovery, and errors.
- [Java Language Specification 17, `7.7 — Module Declarations](https://docs.oracle.com/en/java/javase/specs/jls/se17/html/jls-7.html#jls-7.7): syntax, readability, `requires`, `exports`, `uses`, and `provides`.
- [Java SE 17 — java.lang.module](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/package-summary.html): resolution, module graph, and service binding.
