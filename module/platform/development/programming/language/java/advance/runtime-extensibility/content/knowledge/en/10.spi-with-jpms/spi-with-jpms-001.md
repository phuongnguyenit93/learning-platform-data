# Named Modules, Automatic Modules, and Unnamed Modules in a Plugin System

## 1. Why Distinguish Between the Three Types of Modules?

In Java 9+ (JPMS), a plugin JAR can run as an **explicit named module**, an **automatic module**, or belong to an **unnamed module**, depending on the JAR's contents and where it is placed at launch time. This distinction determines how dependencies are read, packages are exported, services are discovered via `ServiceLoader`, and `ModuleLayer` instances are created to load plugins at runtime.

| Type | Placement | How the module is identified | Characteristics |
|---|---|---|---|
| Explicit named module | Module path or module layer | `module-info.class` | Has explicit `requires`, `exports`, `opens`, `uses`, `provides` |
| Automatic module | Module path | JAR without a descriptor, may have `Automatic-Module-Name` | Has a name, exports/opens all packages, reads resolved modules broadly |
| Unnamed module | Class path | Unnamed; each class loader has its own unnamed module | Does not declare a module descriptor; class path code runs under the traditional model |

**Note:** A JAR without `module-info.class` is not automatically an automatic module by default. If it only sits on the class path, its classes usually belong to the unnamed module of the loader that loads them. Only moving the JAR to the module path gives it the ability to be treated as an automatic module.

## 2. Named Modules and Dependency Relationships

With an explicit named module, the `module-info.java` source declares the module's contract. For example, a shared API module:

```java
module demo.api {
    exports demo.api;
}
```

Host module using the service:

```java
module demo.host {
    requires demo.api;
    uses demo.api.GreetingService;
}
```

Plugin module providing the provider:

```java
module demo.plugin {
    requires demo.api;
    provides demo.api.GreetingService
        with demo.plugin.VietnameseGreeting;
}
```

`requires` establishes a readability relationship to a module; `exports` allows other modules to access the **public** types of the exported package; `opens` serves deep reflection according to JPMS rules. `uses` and `provides` are directives for Java SPI. The host does not need to import the `VietnameseGreeting` class, and the package containing the implementation usually does not need to be exported.

Being able to read a module does not mean every package inside that module is accessible. `exports` also does not turn package-private types into public ones. `opens` is not a replacement for `exports` for normal bytecode access.

### 2.1. Module Resolution and Service Binding

The JVM resolves the graph from root modules, `requires`, and additional mechanisms. Not every JAR present on the module path is guaranteed to be resolved. In applications using `ServiceLoader`, service binding can bring appropriate provider modules into the graph; `--add-modules` can also be used to explicitly specify root modules at launch.

For a named module using `ServiceLoader.load(GreetingService.class)`, `uses demo.api.GreetingService;` must be declared. An explicit named provider module declares `provides`; merely placing a `META-INF/services` file inside a named module is not sufficient to replace the module descriptor.

## 3. Hands-On Java 17+: Three Independent Named Modules

Project structure:

```text
project/
└── src/
    ├── demo.api/
    │   ├── module-info.java
    │   └── demo/api/GreetingService.java
    ├── demo.host/
    │   ├── module-info.java
    │   └── demo/host/Main.java
    └── demo.plugin/
        ├── module-info.java
        └── demo/plugin/VietnameseGreeting.java
```

The three `module-info.java` files are the descriptors from the previous section. Add the following source code.

`src/demo.api/demo/api/GreetingService.java`:

```java
package demo.api;

public interface GreetingService {
    String greet(String name);
}
```

`src/demo.host/demo/host/Main.java`:

```java
package host;

import demo.api.GreetingService;
import java.util.ServiceLoader;

public final class Main {
    public static void main(String[] args) {
        boolean found = false;
        for (GreetingService service : ServiceLoader.load(GreetingService.class)) {
            found = true;
            System.out.println(service.greet("Java"));
        }
        if (!found) System.out.println("Không có provider");
    }
}
```

`src/demo.plugin/demo/plugin/VietnameseGreeting.java`:

```java
package demo.plugin;

import demo.api.GreetingService;

public final class VietnameseGreeting implements GreetingService {
    public VietnameseGreeting() {}

    @Override
    public String greet(String name) {
        return "Xin chào " + name;
    }
}
```

Compile with JDK 17+ using a POSIX shell, from the `project/` directory:

```bash
mkdir -p mods dist
javac -encoding UTF-8 --module-source-path src -d mods \
  $(find src -name '*.java')
jar --create --file dist/demo.api.jar -C mods/demo.api .
jar --create --file dist/demo.host.jar -C mods/demo.host .
jar --create --file dist/demo.plugin.jar -C mods/demo.plugin .
java --module-path dist --add-modules demo.plugin \
  --module demo.host/demo.host.Main
```

Output:

```text
Xin chào Java
```

On Windows, use `javac --module-source-path src -d mods` along with the full list of `.java` files instead of POSIX shell `find` and `$()`. `--add-modules demo.plugin` forces the provider module to participate in the graph in this example, making the practical result clear.

Inspect the module descriptor and the resolution process:

```bash
jar --describe-module --file dist/demo.plugin.jar
java --show-module-resolution --module-path dist \
  --add-modules demo.plugin --module demo.host/demo.host.Main
```

The output of `--show-module-resolution` varies by JDK; use it only to inspect which modules were resolved and the relationships between them.

Try running without the plugin installed by keeping only the two JARs `demo.api.jar` and `demo.host.jar` in a new module path directory, then running the host **without** adding `--add-modules demo.plugin`. In that case, the output will be `Không có provider`.

## 4. Automatic Modules: Converting a Legacy JAR

A traditional JAR that does not contain `module-info.class`, when placed on the module path, can be treated by Java as an automatic module. It has a module name, exports/opens its packages, and has broad readability to support migration. However, it **does not have strict encapsulation** like an explicit named module.

To keep the module name stable, add the attribute to `META-INF/MANIFEST.MF`:

```text
Manifest-Version: 1.0
Automatic-Module-Name: com.example.legacy
```

If `Automatic-Module-Name` is not declared, Java can derive a name from the JAR file; this name easily changes when the artifact is renamed. Use the command:

```bash
jar --describe-module --file legacy-plugin.jar
```

to inspect the actual automatic module name. If a named host module uses that library, it can declare `requires com.example.legacy;` when the module is actually on the module path.

### 4.1. Automatic Module Providers

An automatic module does not write `provides` in a source descriptor. When the JAR has a class-path-style service provider configuration:

```text
META-INF/services/demo.api.GreetingService
```

and contents:

```text
legacy.plugin.LegacyGreeting
```

the module system can derive the service provider from this descriptor. The provider still needs to be a valid, loadable implementation, and the module must participate in the appropriate graph. Automatically reading SPI information does not mean every JAR on the module path automatically becomes a plugin.

### 4.2. Migration Limitations

Automatic modules allow a transitional phase when legacy dependencies do not yet have `module-info.class`, but module names, split packages, service descriptors, nested dependencies, and relationships with the unnamed module must still be checked. When designing a long-term plugin API, you should gradually migrate to explicit named modules so constraints are checked explicitly.

## 5. Unnamed Modules: The Traditional Class Path

Classes loaded from the class path usually reside in the unnamed module corresponding to the class loader. This module has no name for an explicit named module to declare `requires`. It can read named modules that have been resolved in an appropriate environment; conversely, a named module does not read the unnamed module by default.

Run a class path application:

```bash
java -cp "host.jar:api.jar:plugin.jar" demo.host.Main
```

On Windows, replace `:` with `;`. In this model, the service descriptor `META-INF/services/<binary-name-of-service>` allows `ServiceLoader` to discover providers from the class path.

Special note: A JAR placed on the class path does not automatically participate in the module graph as a named module, even if the JAR has the `Automatic-Module-Name` manifest attribute. The same JAR can be treated differently between `-cp` and `--module-path`.

### 5.1. Named Host Using a Legacy Library

If `demo.host` is a named module but the `legacy.Helper` class only appears on the class path, you cannot simply add `legacy.jar` to the class path and treat it as a module that the host can `requires`. The common migration approach is to move that JAR onto the module path, determine its automatic module name, and declare the corresponding dependency.

Depending on the environment, `--add-reads` can serve as an exception to patch readability relationships at runtime, but it should not be used as the default structure for a plugin system.

### 5.2. Unnamed Modules and Class Loaders

Each class loader has its own unnamed module. If the host and plugin use different class loaders, a class with the same binary name defined twice is still two distinct types. You must share the interface contract from the same loader or a compatible module/layer to avoid `ClassCastException` and SPI errors.

## 6. Module Path Does Not Mean Plugins Are Dynamically Loaded

The module path at JVM startup is usually used to build the boot layer. Copying additional plugin JARs into a directory after that point does not cause the boot layer to automatically resolve the new modules. For systems that install plugins at runtime, a separate workflow is needed:

1. Use `ModuleFinder.of(path)` to find modules in the directory/plugin JARs.
2. Resolve the configuration from the parent layer with explicit root modules and dependencies.
3. Use `ModuleLayer.defineModulesWithOneLoader(...)` or another variant to create the layer.
4. Discover providers through `ServiceLoader.load(layer, ServiceType.class)`.
5. Manage lifecycle, resources, errors, dependencies, and the ability to stop plugins.

Illustrative example **not standalone**, requiring `parentLayer`, `finder`, and `GreetingService` to already be defined:

```java
var configuration = parentLayer.configuration().resolveAndBind(
        finder, java.lang.module.ModuleFinder.of(),
        java.util.Set.of("demo.plugin"));

ModuleLayer layer = parentLayer.defineModulesWithOneLoader(
        configuration, ClassLoader.getSystemClassLoader());

var providers = ServiceLoader.load(layer, GreetingService.class);
```

ModuleLayer provides resolution/loading scope; it does not automatically create a security sandbox, unload classes immediately when a JAR is deleted, or stop threads/resources that a plugin has created.

## 7. ServiceLoader Across the Three Module Types

| Aspect | Explicit named module | Automatic module | Unnamed module |
|---|---|---|---|
| Consumer declares `uses` | Yes, in `module-info.java` | No source descriptor to write `uses` | No descriptor |
| Provider declares `provides` | Yes, in `module-info.java` | Usually via `META-INF/services` | Via `META-INF/services` |
| Discovery via `ServiceLoader` | According to module graph, layer, and provider registration | When the automatic module is resolved and has an SPI descriptor | According to class loader/class path and SPI descriptor |
| Separating implementation from public API | Export API package, keep implementation package internal | Packages are broadly exported | No module-based export restrictions |

In real-world environments, providers on the class path and module path can be combined, but discovery depends on the `ServiceLoader.load(...)` overload, context class loader, layer, module graph, and shared class identity of the service API. You should not assume every combination works automatically.

## 8. Common Implementation Issues

### `ClassNotFoundException` or Missing Provider Errors

Check the class path/module path, root modules, `uses`, `provides`, `META-INF/services` files, provider name, class loader, and dependency resolution capability. `ServiceLoader` can throw `ServiceConfigurationError` when a provider is invalid or cannot be loaded.

### Split Package Errors

Two named modules sharing the same package may not coexist in the same layer/loader configuration, or may cause resolution/access errors. Separate API, host, and plugin into distinct namespaces; do not move a legacy JAR onto the module path without checking for package collisions.

### `IllegalAccessError` and Reflection

A named module may be able to read another module, yet the required package has not been exported via `exports`; deep reflection usually needs an appropriate `opens`. Automatic modules open up packages to support migration, but this should not be treated as a long-term encapsulation policy.

### Duplicate API Between Class Path and Module Path

If the `GreetingService` contract is loaded as two distinct classes by different loaders, a provider implementing the interface from one copy is not necessarily assignable to the interface held by the host. Keep a single shared copy of the contract and inspect `getClassLoader()` and `getModule()` when diagnosing.

### Provider Ordering

Do not rely on service discovery order as business priority order. If you need to select a single plugin, use explicit metadata/priority and a clear tie-breaker, while also handling cases with no provider or multiple providers with overlapping capabilities.

## 9. Pre-Release Verification Checklist

- [ ] The contract is a stable API JAR/module, not packaged in duplicate across loaders.
- [ ] The named host declares `requires` and `uses` for the right service.
- [ ] The explicit provider declares `provides` for the right implementation.
- [ ] Automatic/unnamed providers have `META-INF/services` with the exact name and contents.
- [ ] The automatic module name is verified in practice; do not rely on guessed names.
- [ ] The module graph resolves cleanly and has no invalid split packages.
- [ ] Public API packages are exported when using JPMS; reflection has appropriate `opens`.
- [ ] Tested with a provider, without a provider, with multiple providers, missing dependencies, and faulty providers.
- [ ] If runtime plugin installation is supported, tested separate ModuleLayer, class loader, and lifecycle.

**Conclusion:** Named modules provide explicit dependency contracts and SPI; automatic modules serve as a bridge for legacy JARs; unnamed modules preserve the traditional class path mechanism. When building a plugin system, you must choose a consistent structure for the contract, host, and implementation, while verifying module resolution, loader identity, and ServiceLoader on the target runtime.
