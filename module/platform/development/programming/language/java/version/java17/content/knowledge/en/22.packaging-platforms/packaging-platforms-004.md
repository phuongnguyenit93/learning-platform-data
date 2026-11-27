# Service Providers and Dynamic Dependency Limits When Building a Runtime in Java 17

Java has a **service provider** mechanism so one module can publish an implementation of a service while another module depends only on that service's contract. Applications discover implementations with `ServiceLoader` instead of directly invoking each provider's constructor.

This mechanism is especially important when packaging an application into a runtime image with `jlink`. A provider discovered dynamically at runtime still must be present in the module graph observable by the JVM. `jlink` cannot predict every plugin or library an application might load in the future. When building an image, you need to specify root modules explicitly, allow provider linking via `--bind-services`, and understand the constraints of `--limit-modules`.

Key concepts:

- **Service:** a contract, usually an interface or abstract class, that an application needs.
- **Provider:** an implementation supplying that service.
- **`uses` / `provides`:** directives in `module-info.java` declaring that a module consumes a service or provides an implementation.
- **`ServiceLoader`:** the API that locates and instantiates providers at runtime.
- **Service binding in `jlink`:** including provider modules along with their dependencies when creating a runtime image.
- **Dynamic dependency limits:** a provider can only be discovered if its module or class lies within what the runtime can load and is configured to find.

## 1. Why Are Service Providers Needed?

Suppose an application supports multiple data formats: JSON, XML, and CSV. If the application directly instantiates each implementation, the application module depends on all implementations:

```java
JsonCodec json = new JsonCodec();
XmlCodec xml = new XmlCodec();
CsvCodec csv = new CsvCodec();
```

This forces the application module to know the names and construction details of every provider. Adding a new format requires changing orchestration code and potentially modifying the application's dependencies.

Instead, the application defines a service contract:

```java
package com.example.codec.api;

public interface Codec {
    String format();
    Object decode(byte[] input);
}
```

Providers implement the contract:

```java
package com.example.codec.json;

import com.example.codec.api.Codec;

public final class JsonCodec implements Codec {
    public JsonCodec() {
    }

    @Override
    public String format() {
        return "json";
    }

    @Override
    public Object decode(byte[] input) {
        return new String(input, java.nio.charset.StandardCharsets.UTF_8);
    }
}
```

The application simply discovers available `Codec`s:

```java
ServiceLoader<Codec> codecs = ServiceLoader.load(Codec.class);

for (Codec codec : codecs) {
    System.out.println(codec.format());
}
```

The application depends on the `Codec` contract. Which providers are installed and discoverable is determined by the deployment environment.

### 1.1. Service Providers Are Not a Dependency Injection Framework

`ServiceLoader` is Java's standard mechanism for discovering providers by service contract. It does not automatically provide all features of a dependency injection container:

- It does not manage application-wide lifecycles for every provider.
- It does not automatically inject arbitrary dependencies into constructors.
- It does not select a provider by business priority on its own.
- It does not sandbox provider code.
- It does not download libraries from the Internet.

If you need configuration-based implementation selection, scope management, or complex dependency graphs, build an orchestration layer on top of `ServiceLoader` or use an appropriate framework.

## 2. Declaring the Service in an API Module

With JPMS, the service contract typically lives in its own module with the contract package exported.

Example structure:

```text
modules/
├── com.example.codec.api/
│   ├── module-info.java
│   └── com/example/codec/api/Codec.java
├── com.example.codec.json/
│   ├── module-info.java
│   └── com/example/codec/json/JsonCodec.java
└── com.example.app/
    ├── module-info.java
    └── com/example/app/Main.java
```

API module:

```java
module com.example.codec.api {
    exports com.example.codec.api;
}
```

`exports` allows other modules to access public types in the service contract package.

The service API does not need to know which providers will be used. Consequently, the API module can be shared by multiple independent providers.

### 2.1. Why Separate the Service API into Its Own Module?

A small API module establishes clear dependency boundaries:

```text
                com.example.app
                       |
                       | requires
                       v
               com.example.codec.api
                       ^
                       | requires
                       |
              com.example.codec.json
```

- The application reads the contract from the API module.
- The provider also reads the contract from the API module.
- The application does not need to `requires` the provider directly if providers are discovered through service binding.
- Providers can be swapped or added without modifying the service contract, provided they remain compatible.

If the service interface lived inside the application module, external providers would struggle to depend on the contract without introducing cyclic dependencies. Separating the API avoids that problem.

## 3. The `uses` Directive in a Service-Consuming Module

A module calling `ServiceLoader` must declare the service it consumes using the `uses` directive.

```java
module com.example.app {
    requires com.example.codec.api;

    uses com.example.codec.api.Codec;
}
```

Meaning:

- `requires com.example.codec.api` establishes readability to the module containing the `Codec` type.
- `uses com.example.codec.api.Codec` declares that the app module needs to discover providers for that service.

`uses` does not name specific provider modules. Nor does it imply that every provider is automatically packaged into a runtime image.

If code in a named module calls `ServiceLoader.load(Codec.class)` without declaring `uses Codec` in its module descriptor, service loading can fail with `ServiceConfigurationError`. Place the `uses` directive in the module that performs service lookup.

### 3.1. A Module Can Use Multiple Services

```java
module com.example.app {
    requires com.example.codec.api;
    requires com.example.storage.api;

    uses com.example.codec.api.Codec;
    uses com.example.storage.api.Storage;
}
```

Each service is declared with its own directive. The name in `uses` is the fully qualified service type name, not a module name.

### 3.2. uses Does Not Replace requires

If `Codec` resides in module `com.example.codec.api`, the app still needs to read the API module:

```java
module com.example.app {
    requires com.example.codec.api;
    uses com.example.codec.api.Codec;
}
```

Having `uses` alone does not grant readability to the module defining the service type. The two directives serve distinct roles: `requires` grants access to the type; `uses` declares service consumption.

## 4. The `provides ... with ...` Directive in a Provider Module

A provider module declares its implementation with `provides`:

```java
module com.example.codec.json {
    requires com.example.codec.api;

    provides com.example.codec.api.Codec
        with com.example.codec.json.JsonCodec;
}
```

Where:

- `com.example.codec.api.Codec` is the service type.
- `com.example.codec.json.JsonCodec` is the provider implementation.
- The provider module must read the module containing the service type, typically via `requires`.
- The implementation package does not have to be exported to consuming modules.

A traditional provider class must be `public` and have a `public` no-argument constructor so `ServiceLoader` can instantiate it.

Example:

```java
package com.example.codec.json;

import com.example.codec.api.Codec;

public final class JsonCodec implements Codec {
    public JsonCodec() {
    }

    @Override
    public String format() {
        return "json";
    }

    @Override
    public Object decode(byte[] input) {
        return new String(input, java.nio.charset.StandardCharsets.UTF_8);
    }
}
```

You do not need to declare `exports com.example.codec.json` just for `ServiceLoader` to locate the provider. The module system uses the provider declaration to locate the implementation. Exporting the implementation package is only needed if it is a public API that other modules import directly.

### 4.1. Provider Method

JPMS also allows declaring a provider via a class with a `public static` parameterless method named `provider` returning the service type or a subtype:

```java
package com.example.codec.json;

import com.example.codec.api.Codec;

public final class JsonCodecProvider {
    private JsonCodecProvider() {
    }

    public static Codec provider() {
        return new JsonCodec();
    }
}
```

Module descriptor:

```java
module com.example.codec.json {
    requires com.example.codec.api;

    provides com.example.codec.api.Codec
        with com.example.codec.json.JsonCodecProvider;
}
```

In this form, the class listed in `provides` is the provider class containing the `provider()` method. It does not have to be the service implementation class itself; the method returns an instance fulfilling the contract.

A provider method is useful when the implementation requires custom creation logic or when you want to keep the concrete implementation class hidden from the API.

### 4.2. Provider Implementations Need Not Be Exported

Example:

```java
module com.example.codec.json {
    requires com.example.codec.api;

    provides com.example.codec.api.Codec
        with com.example.codec.json.internal.JsonCodec;
}
```

Package `com.example.codec.json.internal` can remain unexported. `ServiceLoader` can still instantiate the provider according to the declared module metadata.

This is one advantage of service providers: the application depends on the service contract, not on implementation packages.

## 5. Discovering Providers with ServiceLoader

`ServiceLoader` resides in `java.util`. Common usage:

```java
import com.example.codec.api.Codec;

import java.util.ServiceLoader;

public class Main {
    public static void main(String[] args) {
        ServiceLoader<Codec> loader =
                ServiceLoader.load(Codec.class);

        for (Codec codec : loader) {
            System.out.println(codec.format());
        }
    }
}
```

`ServiceLoader.load` creates a service loader to locate providers matching the service type. Discovery and instantiation are lazy: providers are normally instantiated as the iterator or stream is consumed, not necessarily when `load` is called.

### 5.1. Getting the First Provider

```java
Codec codec = ServiceLoader.load(Codec.class)
        .findFirst()
        .orElseThrow(() ->
                new IllegalStateException("No Codec provider found"));
```

This is appropriate when the application only needs one provider and the environment ensures a single suitable implementation is present.

If multiple providers exist, do not assume the first provider is always the intended one. Discovery order should not be treated as business priority. Select based on configuration or an explicit contract property such as `format()`.

### 5.2. Inspecting Provider Metadata via Stream

```java
ServiceLoader<Codec> loader = ServiceLoader.load(Codec.class);

loader.stream()
        .map(ServiceLoader.Provider::type)
        .forEach(System.out::println);
```

`Provider.type()` reveals the provider class without invoking `get()` to instantiate it. When you need an instance:

```java
Codec codec = loader.stream()
        .filter(provider ->
                provider.type().getName().contains("Json"))
        .map(ServiceLoader.Provider::get)
        .findFirst()
        .orElseThrow();
```

This example illustrates filtering on metadata; in real applications, select based on the contract or stable configuration rather than depending on implementation class names.

### 5.3. Caching and Reloading

A `ServiceLoader` caches discovered providers. `reload()` clears the cache so subsequent iterations rediscover providers according to the current loader:

```java
ServiceLoader<Codec> loader = ServiceLoader.load(Codec.class);

// Use loader...
loader.reload();
```

`reload()` does not install new modules into a runtime image, add JARs to the module path, or create module layers. If the observable set of modules has not changed, reloading will not reveal providers outside that scope.

### 5.4. Selecting an Explicit Module Layer

When an application uses a dedicated module layer for plugins, you can call:

```java
ServiceLoader<Codec> loader =
        ServiceLoader.load(pluginLayer, Codec.class);
```

This overload searches for providers in the specified module layer and its parent layers according to API rules. It is useful when providers are not in the default boot layer.

In a named module, the module performing the service loading call must still declare `uses` for the service type.

## 6. Service Providers on the Classpath and Module Path

Java supports service loading in both the classpath model and JPMS.

| Environment | How Providers Are Declared |
|---|---|
| Classpath | File `META-INF/services/<service-name>` inside the JAR |
| Named module | Directive `provides Service with Provider` in `module-info.java` |
| Automatic module | Providers can be derived from the service configuration file inside the JAR under automatic module rules |

Classpath configuration example:

```text
META-INF/services/com.example.codec.api.Codec
```

File contents contain the provider class name:

```text
com.example.codec.json.JsonCodec
```

This mechanism remains useful for libraries that need to run on the classpath. In named modules designed for JPMS, declaring `uses` and `provides` in descriptors makes service dependencies clearer.

### 6.1. Do Not Confuse Module Names with Provider Class Names

In `module-info.java`:

```java
uses com.example.codec.api.Codec;

provides com.example.codec.api.Codec
    with com.example.codec.json.JsonCodec;
```

`uses` and `provides` take fully qualified Java type names. `requires` takes a module name.

Example:

```java
requires com.example.codec.api;
```

This is a module name; it does not necessarily equal the package name of the service type.

## 7. Service Providers and the Module Graph

Service providers establish a different kind of link from normal `requires` edges.

Diagram:

```text
             com.example.app
                    |
                    | requires
                    v
            com.example.codec.api
                    ^
                    | requires
                    |
           com.example.codec.json

com.example.app:
    uses com.example.codec.api.Codec

com.example.codec.json:
    provides com.example.codec.api.Codec
        with com.example.codec.json.JsonCodec
```

The app does not need `requires com.example.codec.json` if it only discovers providers via the service contract. The provider module is discovered through service binding.

This keeps the app module free of compile-time dependencies on concrete implementations. However, the provider module still must be discoverable and included in the module graph at runtime or inside the runtime image.

### 7.1. Service Binding Is Not Remote Module Downloading

`ServiceLoader` does not scan arbitrary JARs on disk, nor does it download modules from the Internet. It only discovers providers within the scope of the class loader or module layer used by the service loader.

A provider must:

- Be present on the appropriate classpath or module path.
- Have the corresponding service declaration.
- Be discoverable by the module resolver/class loader.
- Have its required dependencies available.
- Be compatible with the service API used by the consumer.

If the provider JAR is not deployed, `ServiceLoader` cannot synthesize the missing implementation.

## 8. jlink and Custom Runtime Images

`jlink` creates a custom runtime image from a resolved set of modules. The image typically includes launchers, runtime libraries, and selected modules so the application can run without installing a full JDK on the target machine.

Example:

```bash
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.example.app \
  --output runtime
```

Where:

- `--module-path` indicates where to find JDK modules and application modules.
- `--add-modules` selects the root modules to include in the graph.
- `--output` specifies the runtime image directory to create.

Modules referenced by `requires` and their dependencies are resolved along the module graph. However, providers discovered dynamically as services may not belong to the ordinary `requires` dependency graph.

That is why understanding `--bind-services` is important.

### 8.1. A Runtime Image Is Not a Copy of the Entire JDK

`jlink` only links the modules needed according to configuration. A runtime image can be smaller than a full JDK and does not necessarily include JDK modules outside the graph, unlinked provider modules, classpath-only application libraries, plugins loaded from external directories later, or undeployed native libraries/resources.

Therefore, an application that works on a full JDK is not guaranteed to work on a minimal runtime image. You must check both static module dependencies and dynamic dependencies via services/reflection.

## 9. `jlink --bind-services` Links Provider Modules

The option:

```bash
--bind-services
```

instructs `jlink` to link service provider modules and their dependencies when building the runtime image.

Example:

```bash
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.example.app \
  --bind-services \
  --output runtime
```

Assuming:

- `com.example.app` declares `uses com.example.codec.api.Codec`.
- `com.example.codec.json` declares `provides com.example.codec.api.Codec with ...`.
- The provider module and its dependencies exist on the module path.

`--bind-services` allows `jlink` to find the matching provider and add the provider module along with its dependencies into the image.

### 9.1. Without --bind-services

If a provider module is not pulled in via `requires` and is not added directly via `--add-modules`, it may be omitted from the runtime image.

When the application runs inside that image, `ServiceLoader` may find no providers. This does not mean `ServiceLoader` is broken; the provider simply does not exist in the running runtime image/module layer.

### 9.2. When Providers Are Added Directly

If you know the exact provider module, you can add it as a root:

```bash
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.example.app,com.example.codec.json \
  --output runtime
```

When a provider is added directly, `jlink` resolves that module and its dependencies. This is useful when you want to bundle an exact, known set of providers.

`--bind-services` is more convenient when you want to link providers by service contract without listing every implementation manually.

### 9.3. bind-services Is Not include-all

`--bind-services` does not include every module or every JAR in a directory inside the runtime. It links providers for services used in the module graph that are observable on the module path.

If a provider does not declare the service, is missing from the module path, or is excluded from the observable module universe, `jlink` cannot automatically discover it.

## 10. jlink Options Affecting Dynamic Dependencies

Three options must be understood together:

| Option | Role |
|---|---|
| `--add-modules` | Selects root modules to resolve and include in the image |
| `--bind-services` | Links service provider modules and their dependencies |
| `--limit-modules` | Limits the set of modules observable to the module resolver |

### 10.1. --add-modules

Example:

```bash
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.example.app,java.logging \
  --bind-services \
  --output runtime
```

`com.example.app` and `java.logging` are chosen as roots. Their dependencies are resolved; `--bind-services` adds matching providers.

Use `--add-modules` when the application needs a module that static dependencies do not pull into the graph, or when you want to include a known provider module explicitly.

### 10.2. --limit-modules

`--limit-modules` restricts the universe of observable modules during resolution:

```bash
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.example.app \
  --limit-modules java.base,java.logging,com.example.app,com.example.codec.api,com.example.codec.json \
  --bind-services \
  --output runtime
```

The example above is illustrative: the limited set must include all required dependencies and any providers you intend to link. If a provider is excluded from the observable set, service binding cannot add it.

Do not use `--limit-modules` prematurely just to shrink image size. Identify required modules, active providers, and provider dependencies first.

### 10.3. --suggest-providers

`jlink` can suggest providers for service types used by modules:

```bash
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --suggest-providers com.example.app
```

This option is useful for inspecting potential providers before building an image. It is a discovery aid, not a substitute for checking module descriptors and verifying the provider is actually included in the image.

### 10.4. Thinking Order When Configuring jlink

1. Choose the application module as a root via `--add-modules`.
2. Identify service API modules that the application `uses`.
3. Verify provider modules have `provides` for the exact service type.
4. Ensure providers and their dependencies are present on the module path.
5. Use `--bind-services` if you want `jlink` to link providers automatically.
6. Only use `--limit-modules` once you know the allowed observable module set.
7. Verify the resulting image with `--list-modules` and test service loading.

## 11. Complete Example: Building a Runtime Image with a JSON Provider

### 11.1. API Module

```java
// modules/com.example.codec.api/module-info.java
module com.example.codec.api {
    exports com.example.codec.api;
}
```

```java
// modules/com.example.codec.api/com/example/codec/api/Codec.java
package com.example.codec.api;

public interface Codec {
    String format();
    String decode(byte[] input);
}
```

### 11.2. Provider Module

```java
// modules/com.example.codec.json/module-info.java
module com.example.codec.json {
    requires com.example.codec.api;

    provides com.example.codec.api.Codec
        with com.example.codec.json.JsonCodec;
}
```

```java
// modules/com.example.codec.json/com/example/codec/json/JsonCodec.java
package com.example.codec.json;

import com.example.codec.api.Codec;
import java.nio.charset.StandardCharsets;

public final class JsonCodec implements Codec {
    public JsonCodec() {
    }

    @Override
    public String format() {
        return "json";
    }

    @Override
    public String decode(byte[] input) {
        return new String(input, StandardCharsets.UTF_8);
    }
}
```

### 11.3. Application Module

```java
// modules/com.example.app/module-info.java
module com.example.app {
    requires com.example.codec.api;

    uses com.example.codec.api.Codec;
}
```

```java
// modules/com.example.app/com/example/app/Main.java
package com.example.app;

import com.example.codec.api.Codec;
import java.util.ServiceLoader;

public class Main {
    public static void main(String[] args) {
        ServiceLoader<Codec> loader = ServiceLoader.load(Codec.class);

        for (Codec codec : loader) {
            System.out.println("Provider: " + codec.getClass().getName());
            System.out.println("Format: " + codec.format());
        }
    }
}
```

### 11.4. Compiling the Modules

From the project directory:

```bash
javac --module-source-path modules \
  -d out \
  -m com.example.codec.api,com.example.codec.json,com.example.app
```

This produces compiled modules under the `out` directory.

### 11.5. Running on the Full JDK

```bash
java --module-path out \
  --module com.example.app/com.example.app.Main
```

In this environment, all three modules are placed on the module path. The JSON provider can be found by `ServiceLoader` because the provider module is present and has its service declaration.

### 11.6. Building the Runtime Image with bind-services

On Linux/macOS:

```bash
jlink \
  --module-path "$JAVA_HOME/jmods:out" \
  --add-modules com.example.app \
  --bind-services \
  --output runtime
```

On Windows PowerShell, the module path uses a semicolon:

```powershell
jlink --module-path "$env:JAVA_HOME\jmods;out" --add-modules com.example.app --bind-services --output runtime
```

### 11.7. Inspecting the Runtime Image

```bash
runtime/bin/java --list-modules
runtime/bin/java --describe-module com.example.codec.json
runtime/bin/java --module com.example.app/com.example.app.Main
```

On Windows, the launcher is at `runtime\bin\java.exe`.

Expected application output:

```text
Provider: com.example.codec.json.JsonCodec
Format: json
```

If the provider does not appear, check whether the app declared `uses`, whether the provider descriptor has `provides ... with ...`, whether the provider module was on the module path when running `jlink`, whether `--bind-services` was used or the provider was added via `--add-modules`, whether `--limit-modules` excluded the provider from the universe, and whether the service API shares the same module/type identity between app and provider.

## 12. Dynamic Dependency Limits When Building a Runtime

This is the most important area to understand well when packaging modular applications.

### 12.1. jlink Only Links Modules Observable at Build Time

`jlink` runs at build/deployment time. It resolves the module graph from the supplied module path and options. It has no knowledge of a plugin that will be downloaded from the Internet, another disk, or a plugin management system months later.

If a provider only appears after the runtime image has been built, that provider cannot spontaneously exist inside the already-built image.

To use providers installed later, deploy the module/JAR along with its dependencies and load it via an appropriate module path or module layer.

### 12.2. Service Binding Only Handles Declared and Discoverable Providers

`--bind-services` does not scan all classes to guess implementations. A provider must be declared according to service mechanisms:

- Named modules use `provides`.
- Classpath service providers use `META-INF/services`.
- The provider module must be on the observable module path at link time.
- The service type must be used by a module in the graph via `uses`.

If a provider does not declare the service or is absent from the module path, service binding cannot add it to the image.

### 12.3. jlink Does Not Package Automatic Modules or Arbitrary Classpath Libraries

`jlink` builds runtime images from modules that are linkable under the module system. Automatic modules and classpath-only JARs cannot be used as regular modules to link directly into a custom runtime image.

If a library remains classpath-only:

- You can deploy the JAR alongside the runtime image and run using the classpath if the application is designed that way.
- Or convert the library into a proper named module before linking.
- If the library is an automatic module, evaluate modularizing it or using a different deployment model; do not assume `jlink` will turn it into an explicit module.

Do not confuse a JAR being runnable on the module path as an automatic module with it being packageable by `jlink` as an explicit module.

### 12.4. Reflection and Dynamic Class Names May Not Appear in requires

An application can load classes via:

```java
Class.forName("com.example.plugin.CustomPlugin");
```

Class names loaded from configuration or external data may not be fully detected by static dependency analysis tools. Likewise, JNI, resource lookups, service loading, and plugin discovery can create dependencies not inferable from `import` statements alone.

When building a runtime image, list known dynamic dependencies and verify they are included in the image or deployed externally by design.

### 12.5. --limit-modules Can Exclude Providers

If a provider module falls outside the allowed observable module universe, the resolver cannot select that provider. An overly minimal image may execute the main code path while lacking providers expected by the application.

When using `--limit-modules`, re-verify service binding after linking. Do not check only the app module and API module; verify the provider module is present too.

### 12.6. Module Layers Can Only Load Deployed and Resolvable Modules

`ModuleLayer` lets you create a new module layer at runtime, but the module finder still needs to locate the module and its dependencies. It is not a mechanism for automatically downloading remote dependencies or bypassing module resolution.

A plugin must have a valid module descriptor or a supported deployment form, a unique module name within the configuration scope, its required dependencies on the module path, an accurate service provider declaration if discovered via `ServiceLoader`, and a service API compatible with the parent module read by the plugin.

## 13. Loading Providers Outside the Runtime Image with ModuleLayer

An application can keep its runtime image lean and deploy modular plugins in a separate directory. At runtime, the application creates a module layer for the plugins.

Suppose:

```text
runtime/
plugins/
└── com.example.codec.xml.jar
```

The plugin module declares:

```java
module com.example.codec.xml {
    requires com.example.codec.api;

    provides com.example.codec.api.Codec
        with com.example.codec.xml.XmlCodec;
}
```

The application already has the service API in the boot layer. It can discover plugin modules from the external directory:

```java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.Set;

ModuleFinder finder = ModuleFinder.of(Path.of("plugins"));

Configuration configuration =
        ModuleLayer.boot()
                .configuration()
                .resolve(
                        finder,
                        ModuleFinder.of(),
                        Set.of("com.example.codec.xml")
                );

ModuleLayer pluginLayer =
        ModuleLayer.boot()
                .defineModulesWithOneLoader(
                        configuration,
                        ClassLoader.getSystemClassLoader()
                );
```

Then discover service providers in that layer:

```java
ServiceLoader<Codec> plugins =
        ServiceLoader.load(pluginLayer, Codec.class);

for (Codec codec : plugins) {
    System.out.println(codec.format());
}
```

This example assumes the app module declares `uses com.example.codec.api.Codec`, the plugin JAR is a valid named module, the plugin reads the service API from the parent layer, all of the plugin's dependencies can be resolved, and the plugin is deployed in the `plugins` directory.

`defineModulesWithOneLoader` creates a single class loader for the modules in the new layer. If you need separate loaders per module, consider `defineModulesWithManyLoaders`.

### 13.1. ModuleLayer Does Not Automatically Resolve All Plugin Conflicts

If two plugins share the same module name or require incompatible API versions, module resolution may fail or deployments may not coexist in the same graph.

JPMS does not provide version selection like a dependency manager. You must manage versions, module names, dependencies, and compatibility in your build/deployment pipeline.

### 13.2. External Providers Are Not Inside the Image

`--bind-services` during runtime image creation only links providers observable at link time. Plugins deployed later must be loaded through the module path or a new layer.

| Model | Advantages | Limitations |
|---|---|---|
| Link providers into the image with `--bind-services` | Image is self-contained with providers; simple runtime | Adding new providers usually requires building a new image |
| Deploy plugins outside the image and create a `ModuleLayer` | Plugins can be installed/replaced independently | Must manage dependencies, compatibility, and runtime module resolution |

## 14. Using jdeps and JDK Tools to Find Dependencies

`jdeps` analyzes dependencies at the package/module level from classes or JARs. It is helpful for finding static dependencies, though it cannot substitute for reviewing service declarations, reflection, or plugin configurations.

Example:

```bash
jdeps --module-path out \
      --print-module-deps \
      --module com.example.app
```

The output can serve as input for understanding required module dependencies. However, review module descriptors and service providers separately.

To inspect the descriptor inside a JAR:

```bash
jar --describe-module --file out/com.example.codec.json.jar
```

To inspect modules inside a runtime image:

```bash
runtime/bin/java --list-modules
runtime/bin/java --describe-module com.example.codec.json
```

To suggest providers:

```bash
jlink --module-path "$JAVA_HOME/jmods:out" \
      --suggest-providers com.example.app
```

These commands answer different questions:

- `jdeps`: which static dependencies does bytecode/module have?
- `jar --describe-module`: how does the JAR declare its module/services?
- `jlink --suggest-providers`: which providers exist for the used services?
- `java --list-modules`: which modules are in the runtime image?
- `java --describe-module`: what is the module descriptor inside the runtime?

Do not rely on a single command alone to conclude that all dynamic dependencies have been packaged.

## 15. Common Errors When Building Runtimes with Service Providers

| Symptom | Common Cause | Resolution |
|---|---|---|
| `ServiceLoader` finds no providers on full JDK | Missing `uses` or provider lacks `provides`/valid service metadata | Check consumer and provider descriptors |
| Runs on full JDK but image finds no providers | Provider was not linked into the image | Use `--bind-services` or add provider via `--add-modules` |
| `jlink` reports module not found | API/provider module or dependency missing from module path | Check module path and module name |
| Provider not found after using `--limit-modules` | Provider module was excluded from the observable universe | Adjust the limited module set |
| Provider class fails to instantiate | Missing public no-arg constructor/provider method or runtime dependency | Inspect provider declaration and `ServiceConfigurationError` cause |
| External plugin outside image fails to load | Plugin/dependency omitted from module finder/layer | Deploy full module path and resolve the layer |
| JAR runs on classpath but `jlink` cannot link it | JAR is not an eligible explicit module | Modularize or deploy using the classpath model outside the image |
| Multiple providers exist and wrong one is chosen | Relying on provider order | Select explicitly via configuration or contract metadata |
| Image runs but optional features fail | Dynamic dependencies via reflection/services were not packaged | List and verify dynamic dependencies |
| Two plugins are incompatible | Duplicate module names or incompatible dependency/API versions | Manage module names and compatibility at build/deploy time |

### 15.1. Empty ServiceLoader Is Not Necessarily a JVM Error

`ServiceLoader.load` can return a valid loader even when no providers exist. If none exist, its iterator yields no elements and `findFirst()` returns `Optional.empty()`.

The application should decide whether a service is required or optional:

```java
Codec codec = ServiceLoader.load(Codec.class)
        .findFirst()
        .orElseThrow(() ->
                new IllegalStateException(
                        "No codec provider is installed"
                ));
```

If the service is an optional feature, display an appropriate status or skip that feature. If the service is required, failing fast at startup catches packaging mistakes early.

### 15.2. ServiceConfigurationError

`ServiceLoader` can throw `ServiceConfigurationError` when provider metadata is invalid, the provider cannot be instantiated, or the provider does not satisfy the contract.

Do not catch the error and silently continue as if the provider loaded. Log the service name, provider type, and underlying cause to catch configuration mistakes.

## 16. Designing a Runtime Image for Plugin-Based Applications

Before linking the image, decide which providers belong to the core application and which providers are optional plugins.

### 16.1. Core Providers

If the application always needs the JSON provider, ensure it is linked into the image:

```bash
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.example.app \
  --bind-services \
  --output runtime
```

After linking, run tests inside the created image itself. Do not run only on a full JDK and conclude the image works.

### 16.2. Optional Providers

If the XML provider is only present on certain deployments, deploy it outside the image and load it via a module layer. The application must handle missing plugins or unresolvable dependencies gracefully.

### 16.3. Separating API from Implementation

Place the service contract in a stable API module. Providers depend on the API; the app also depends on the API. Avoid letting the API depend on implementations or creating cyclic dependencies among providers.

### 16.4. Defining a Selection Policy When Multiple Providers Exist

Do not rely on provider ordering. You can add metadata to the contract:

```java
public interface Codec {
    String format();
    int priority();
    String decode(byte[] input);
}
```

Then select explicitly:

```java
Codec selected = ServiceLoader.load(Codec.class)
        .stream()
        .map(ServiceLoader.Provider::get)
        .filter(codec -> codec.format().equals("json"))
        .max(java.util.Comparator.comparingInt(Codec::priority))
        .orElseThrow();
```

The selection policy should be defined by the application. If two providers share the same priority, define a deterministic tie-breaker or report an ambiguous configuration.

## 17. Service Providers Do Not Create a Security Sandbox

The module system provides encapsulation and readability, not a sandbox for running untrusted provider code.

When `ServiceLoader` instantiates a provider, its constructor or provider method can execute arbitrary code with the permissions of the process. Therefore:

- Only deploy providers from trusted sources.
- Verify plugin signatures, checksums, or provenance according to release procedures.
- Restrict OS/container privileges of the process.
- Do not treat unexported packages as isolation against malicious code.
- Do not grant plugins access to secrets or system privileges beyond what they need.
- Maintain update and rollback policies for providers.

A provider linked into a runtime image is executable code within the application. A service declaration describes capability to fulfill a contract, not that the provider is safe.

## 18. Practical Workflow for Building a Custom Runtime

1. **Identify root modules:** the application launch module and core modules.
2. **Verify service APIs:** contract packages are exported and the app module declares `uses`.
3. **Verify providers:** provider modules `requires` the API and `provides` the exact service type.
4. **Check static dependencies:** use `jdeps`, module descriptors, and the module path.
5. **Discover providers:** run `jlink --suggest-providers` and inspect descriptors.
6. **Choose a strategy:** core providers are linked with `--bind-services`; optional plugins are deployed outside the image.
7. **Limit modules deliberately:** if using `--limit-modules`, ensure providers and dependencies remain observable.
8. **Build the image:** run `jlink` with module path, roots, service binding, and output path.
9. **Verify the image:** run `--list-modules`, `--describe-module`, and exercise service discovery.
10. **Test missing-provider scenarios:** verify the application fails fast or handles optional services per contract.
11. **Verify target environments:** runtime images are tied to the OS/architecture they were built for; build separate images for each supported target.
12. **Record module inventory:** document root modules, providers, module versions/builds, and how to reproduce the image.

## 19. Practice Exercises

### Exercise 1 — uses or requires?

An app module needs to call `ServiceLoader.load(Codec.class)`. The service interface resides in module `com.example.codec.api`.

**Answer:** The app needs `requires com.example.codec.api` to read the service type and `uses com.example.codec.api.Codec` to declare its service requirement.

### Exercise 2 — Does a Provider Need to Export Its Implementation Package?

A provider module declares `provides Codec with JsonCodec`. The package containing `JsonCodec` is not exported.

**Answer:** Exporting it is not required solely for `ServiceLoader` to instantiate the provider. The provider declaration in the module descriptor enables the module system to access the service implementation.

### Exercise 3 — Why Does It Work on a Full JDK but Fail in a Runtime Image?

The app finds the provider on a full JDK, but the image only contains the app module and the service API.

**Answer:** The provider module was not included in the image. Use `--bind-services` if the provider is declared and observable, or add the provider module with `--add-modules`.

### Exercise 4 — Does --bind-services Add Every Plugin?

**Answer:** No. It links discoverable provider modules and their dependencies for services used in the module graph. Plugins absent from the module path at link time or lacking service declarations will not be added automatically.

### Exercise 5 — How Does --limit-modules Affect Binding?

**Answer:** It limits the observable module universe. If a provider is excluded from that scope, service binding cannot select that provider.

### Exercise 6 — Can a JAR with META-INF/services Be Packaged Directly by jlink?

**Answer:** Do not assume so. A classpath-only JAR or an automatic module is not an explicit module that `jlink` can link directly. Modularize it or deploy the JAR using an appropriate runtime/classpath model.

### Exercise 7 — Can Plugins Be Installed After the Runtime Image Is Built?

**Answer:** Yes, if the application is designed to load plugins external to the image. Deploy the module and its dependencies on a module path, resolve them into a `ModuleLayer`, and call `ServiceLoader.load(layer, service)`. Those plugins are not part of the original image.

### Exercise 8 — Does ServiceLoader Guarantee the First Provider Is the Best?

**Answer:** No. Do not rely on discovery order as business priority. Select based on configuration or explicit contract metadata.

## 20. Key Takeaways

- Service providers decouple the service contract from its implementations.
- Consumer modules declare `uses ServiceType`; provider modules declare `provides ServiceType with ProviderType`.
- Consumers must `requires` the module defining the service type; providers must also read the service API.
- Provider implementation packages do not have to be exported.
- `ServiceLoader` discovers providers within the observable class loader/module layer scope.
- Providers can use a public no-arg constructor or a suitable provider method.
- `jlink --bind-services` links provider modules and their dependencies when building a runtime image.
- `--add-modules` chooses root modules; `--limit-modules` limits the module universe.
- `--bind-services` is not include-all and does not download remote plugins.
- `jlink` does not turn classpath JARs or automatic modules into explicit modules that can be linked directly.
- Reflection, service loading, and plugin discovery can introduce dynamic dependencies missed by static analysis.
- Plugins deployed outside the image can be resolved into a `ModuleLayer` if modules and dependencies are complete.
- Service providers are executable code inside the process; the module system does not provide a security sandbox.
- Always test service discovery inside the final runtime image itself.

## Official References for Java 17

- [Java SE 17 API — `java.util.ServiceLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html).
- [Java SE 17 API — `java.lang.module.ModuleFinder`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/ModuleFinder.html).
- [Java SE 17 API — `java.lang.ModuleLayer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html).
- [Java SE 17 API — `java.lang.module.Configuration`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/Configuration.html).
- [Java Language Specification 17 — `7.7.4`: Service Providers](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7.4).
- [Java SE 17 — `jlink` tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jlink.html).
- [Java SE 17 — `jdeps` tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jdeps.html).
- [Java SE 17 — `jar` tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jar.html).
- [JEP 261 — Module System](https://openjdk.org/jeps/261).
