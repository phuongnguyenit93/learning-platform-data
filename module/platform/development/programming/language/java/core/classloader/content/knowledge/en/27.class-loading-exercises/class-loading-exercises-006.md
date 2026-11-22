# Creating a ModuleLayer for Modularized Plugins with Java 17+

## 1. Problem: loading a plugin as a named module while the host is running

In the Java Platform Module System (**JPMS**, Java 9+), a plugin does not necessarily have to be just a JAR placed on the classpath whose implementation is found using `Class.forName`. A plugin can be a **named module**, having a `module-info.java` file, declaring `requires` dependencies and `provides ... with ...` service providers.

A host application (**host**) can start **without resolving the plugin module**, and then:

1. Discover module artifacts using `ModuleFinder`.
2. Resolve a new module graph based on the parent layer's `Configuration`.
3. Define runtime modules and map loaders using `ModuleLayer.defineModulesWithManyLoaders` (or `WithOneLoader`).
4. Find service providers in the **new layer** using `ServiceLoader.load(layer, ServiceType.class)`.
5. Invoke the plugin through the host's **shared API module**, without importing the implementation class.
6. Manage the lifecycle of the layer, instances, class loaders, caches, and related resources.

This exercise will have three parts:

~~~text
Boot ModuleLayer (ModuleLayer.boot())
  |
  +-- plugin.api named module
  |     exports plugin.api.Extension
  |
  +-- java.base and resolved system modules
  |
  v
Child ModuleLayer (dynamically created)
  |
  +-- plugin.echo named module
        requires plugin.api
        provides plugin.api.Extension
          with plugin.echo.EchoExtension
~~~

**Key point:** The `plugin.api.Extension` API must have the **same runtime class identity** in both the host and the provider. The plugin implementation is defined in the **child layer**, while the shared API module already exists in the **boot parent layer**. This is how the communication contract is preserved while allowing new plugins to be discovered at runtime.

### Expected outcomes

You will build a Java 17+ program without Maven/Gradle, with an API module, a provider module, and a host launcher; compile each part yourself; create a `Configuration` and then a `ModuleLayer`; use `ServiceLoader.load(layer, ...)`; and verify the defining loader, runtime module identity, parent visibility, and the creation of two independent child layers.

The exercise also explains the differences between module path and classpath, `ModuleFinder` and `Configuration`, parent `ModuleLayer` and parent `ClassLoader`, choosing one/many/custom loaders, visibility/exports/opens restrictions, the difference between `resolve` and `resolveAndBind`, and common errors in real-world plugin systems.

## 2. Four distinct objects of JPMS

### 2.1. Module artifact and module descriptor

A modular JAR or a compiled directory module contains `module-info.class`. The source descriptor file:

~~~java
module plugin.echo {
    requires plugin.api;
    provides plugin.api.Extension
        with plugin.echo.EchoExtension;
}
~~~

At runtime, the descriptor information indicates:

- **Module name**: `plugin.echo`.
- **Requires**: needs `plugin.api`.
- **Provides**: registers provider `plugin.echo.EchoExtension` for service `plugin.api.Extension`.
- Other directives can be `exports`, `opens`, `uses`.

An artifact appearing on disk **does not yet mean** its module has been resolved or has a runtime `Module` object.

### 2.2. ModuleFinder: finding artifacts/module references

~~~java
ModuleFinder finder =
        ModuleFinder.of(Path.of("build/plugins"));
~~~

`ModuleFinder` knows how to recognize module artifacts at the specified roots; it does not itself define runtime classes or start providers.

In the demo, `build/plugins` contains the exploded module directory `plugin.echo`. It can be replaced with a modular JAR if properly packaged and given the appropriate path.

### 2.3. Configuration: the resolved module graph

~~~java
Configuration configuration =
        ModuleLayer.boot().configuration().resolve(
                finder,
                ModuleFinder.of(),
                Set.of("plugin.echo"));
~~~

This is the graph of **newly resolved modules** based on the parent configuration. `resolve` processes `requires` and resolution constraints; it does not itself instantiate providers or create a ClassLoader.

Parameters to distinguish:

- First `finder`: module artifacts that can be used in the current resolution.
- `ModuleFinder.of()`: the after-finder catalog in this API, left empty in the demo.
- `Set.of("plugin.echo")`: **root module names** requested to be resolved.

The `plugin.api` API is already in the parent boot configuration; the resolver can satisfy `requires plugin.api` from the parent, so **there is no need to create a second copy of the API in the child**.

### 2.4. ModuleLayer: defining runtime modules and loaders

~~~java
ModuleLayer layer = ModuleLayer.boot()
        .defineModulesWithManyLoaders(
                configuration,
                ClassLoader.getSystemClassLoader());
~~~

This is when runtime `Module` objects are created and the new named modules are mapped to loader(s). The instance method `defineModulesWithManyLoaders` returns a `ModuleLayer`.

In this experiment:

- Parent module layer: `ModuleLayer.boot()`.
- Parent `Configuration`: `boot.configuration()`.
- Child configuration contains `plugin.echo`.
- Loader strategy: **each new module** gets its own new loader.
- The parameter `ClassLoader.getSystemClassLoader()` is the **parent ClassLoader for the new loader**, which does **not** mean the plugin is defined directly in the application/system loader.

**Separate three relationships:** JPMS module readability (which modules can be read), parent layer relation (which layer is the parent), and ClassLoader delegation (which loader loads/delegates which classes). They are related but **not identical**.

## 3. Designing the host, shared API, and plugin module

### 3.1. Shared API contract

The API module is named `plugin.api`:

~~~java
module plugin.api {
    exports plugin.api;
}
~~~

And the interface:

~~~java
package plugin.api;

public interface Extension {
    String name();
    String execute(String input);
}
~~~

This choice keeps the public contract small. The host and implementation only know about `Extension`, without needing to share the implementation type or the plugin's private libraries.

**Responsibility of the API module:** managing the service interfaces, DTOs, and exceptions that cross the boundary. In a multi-plugin system, do not let a provider define its own copy of `plugin.api.Extension`; otherwise, runtime type identity can split in two and casting/service discovery will fail.

### 3.2. Plugin implementation module

Descriptor:

~~~java
module plugin.echo {
    requires plugin.api;
    provides plugin.api.Extension with plugin.echo.EchoExtension;
}
~~~

Provider class:

~~~java
package plugin.echo;

import plugin.api.Extension;

public final class EchoExtension implements Extension {
    @Override
    public String name() {
        return "echo";
    }

    @Override
    public String execute(String input) {
        return "PLUGIN:" + input;
    }
}
~~~

**`exports plugin.echo;` is not needed** just for `ServiceLoader` to instantiate the provider declared via `provides ... with ...`. The provider factory mechanism is handled by JPMS/`ServiceLoader` according to the contract. The host does not need direct access to the implementation type via a Java source import.

In the demo, the provider has the default public no-arg constructor. In real-world systems, provider requirements, constructors, and static `provider()` factory behavior also depend on the named module/service-provider contract, so the corresponding Javadoc should be checked.

### 3.3. The host knows the API and child ModuleLayer, not EchoExtension

The host will write:

~~~java
for (Extension extension :
        ServiceLoader.load(layer, Extension.class)) {
    System.out.println(extension.execute("hello"));
}
~~~

There is no:

~~~java
import plugin.echo.EchoExtension;
~~~

This allows the plugin module to **be absent when compiling the host** or absent from the boot layer. The plugin lifecycle can be handled through the API interface and a metadata/service registry.

### 3.4. Why should the API reside in the parent layer?

If the host uses `plugin.api.Extension` from the boot layer while the child plugin resolves another `plugin.api` with the same name under a different layer, there is a risk that the host and the plugin will not use the same `Class<?>`.

Recommended design in the demo:

~~~text
Boot layer:
  plugin.api.Extension => shared Class<?>

Child layer:
  plugin.echo.EchoExtension
       implements Extension from parent
~~~

The important condition is that the **module resolution graph and module-classloader mapping** actually direct the provider to the host's exact `Extension.class`; simply checking that two JAR bytecodes "look the same" is not enough.

## 4. Demo project structure

~~~text
demo/
├── src/
│   ├── plugin.api/
│   │   ├── module-info.java
│   │   └── plugin/api/Extension.java
│   ├── plugin.echo/
│   │   ├── module-info.java
│   │   └── plugin/echo/EchoExtension.java
│   └── host/
│       └── HostMain.java
└── build/
    ├── mods/
    │   └── plugin.api/          # compiled API module
    ├── plugins/
    │   └── plugin.echo/         # compiled provider module
    └── host/                    # launcher on classpath
~~~

**Intentional separation of the two directories:**

- `build/mods` is the **module path when running the host** so that `plugin.api` is resolved into the boot layer.
- `build/plugins` is **not on the launcher's `--module-path`**; the host only passes this path to `ModuleFinder.of` **at runtime**.
- `build/host` is the classpath containing `HostMain.class` in the **unnamed module**.

Because of this, the `echoNotInBoot=true` test is genuinely meaningful: the provider is not resolved by the launcher before the host code creates the child layer.

If `plugin.echo` were placed on the boot module path **and added as a root module** with `--add-modules`, the demo would no longer accurately measure the dynamic layer creation process.

## 5. Source files of the shared API module

### 5.1. `src/plugin.api/module-info.java`

~~~java
module plugin.api {
    exports plugin.api;
}
~~~

`exports plugin.api;` allows code from other modules (including the unnamed host module) to use public types of the API package when there is appropriate readability.

### 5.2. `src/plugin.api/plugin/api/Extension.java`

~~~java
package plugin.api;

public interface Extension {
    String name();
    String execute(String input);
}
~~~

In the program, `Extension.class` is passed by the host to `ServiceLoader.load(layer, Extension.class)`. It is a concrete type defined by the JVM, not a service name string.

## 6. Source files of the plugin provider module

### 6.1. `src/plugin.echo/module-info.java`

~~~java
module plugin.echo {
    requires plugin.api;
    provides plugin.api.Extension with plugin.echo.EchoExtension;
}
~~~

`uses plugin.api.Extension;` is not needed inside the plugin provider module itself to declare a provider; `uses` is a directive for the **service-consuming module**.

The demo host is an unnamed module. If the host is modularized into a named module `plugin.host`, the descriptor should have:

~~~java
module plugin.host {
    requires plugin.api;
    uses plugin.api.Extension;
}
~~~

This is an **illustrative descriptor for a named host architecture**, **not used in the runnable demo source** in section 8. When the host is a named module consuming a service, `uses` is what must be declared for `ServiceLoader` to be valid. The demo's purpose in using an unnamed host is to simplify compilation and emphasize the dynamic layer; it still has permission to invoke the service API resolved in boot.

### 6.2. `src/plugin.echo/plugin/echo/EchoExtension.java`

~~~java
package plugin.echo;

import plugin.api.Extension;

public final class EchoExtension implements Extension {
    @Override
    public String name() {
        return "echo";
    }

    @Override
    public String execute(String input) {
        return "PLUGIN:" + input;
    }
}
~~~

This plugin only accepts and returns a Java platform `String` so that the output does not depend on DTO serialization or versioning. In production, this can be replaced with `Request`/`Response` from the API module, but API version/identity must be kept consistent.

## 7. Creating a child ModuleLayer in the right order

### 7.1. Confirming the API is resolved in boot

~~~java
ModuleLayer boot = ModuleLayer.boot();
boolean apiInBoot = boot.findModule("plugin.api").isPresent();
~~~

If `plugin.api` is not in boot, `requires plugin.api` in the provider may not be satisfied by the resolver from the parent as intended. The demo deliberately runs with `--add-modules plugin.api` to make the API a root of the boot layer.

### 7.2. Confirming the plugin is not yet in boot

~~~java
boolean pluginNotYetLoaded =
        boot.findModule("plugin.echo").isEmpty();
~~~

This checks whether the **module is already defined in the layer**; it does not assert that the artifact does not exist on disk. The plugin is available in `build/plugins` but has not been resolved in the boot configuration.

### 7.3. ModuleFinder reads the plugin artifact

~~~java
ModuleFinder finder =
        ModuleFinder.of(Path.of("build/plugins"));
~~~

With the proper directory structure, the finder recognizes `plugin.echo`. If `module-info.class` is missing or the module directory/JAR is invalid, the discovery/resolution step can fail. You must use the **module root**, and not mistakenly pass a source tree or an output directory containing many disorganized files.

### 7.4. Resolving roots while keeping the API in the parent

~~~java
Configuration configuration = boot.configuration()
        .resolve(finder, ModuleFinder.of(), Set.of("plugin.echo"));
~~~

Meaning:

~~~text
Parent Configuration:
  plugin.api (already resolved)
     ^
     | requires
New Configuration:
  plugin.echo
~~~

`resolve` does not create runtime classes; it only builds a graph with valid module references and readability dependencies. Because the root set contains `plugin.echo`, the provider module is resolved **even though the host has no compile-time dependency on the provider**.

`resolveAndBind` is a different method: in addition to roots/requires, it also performs service binding resolution that pulls in matching provider modules across the module graph. In the demo, we **explicitly specified `plugin.echo` as a root**, so service binding is not needed to select the plugin. If you want to discover providers automatically via `uses/provides`, you must clearly design the `resolveAndBind` algorithm and the module finder scope/parent config.

### 7.5. Defining the runtime layer and choosing the ClassLoader policy

~~~java
ModuleLayer layer = boot.defineModulesWithManyLoaders(
        configuration,
        ClassLoader.getSystemClassLoader());
~~~

This instance form returns a `ModuleLayer`. `WithManyLoaders` creates a new loader for **each named module defined in the new configuration**, without requiring every module of the **parent boot layer** to also be recreated.

Then:

~~~java
Module providerModule =
        layer.findModule("plugin.echo").orElseThrow();

ClassLoader providerLoader =
        layer.findLoader("plugin.echo");
~~~

`layer.findModule` can look up in the current layer or its parents, whereas `layer.modules()` contains only the modules defined directly in the current layer. `layer.findLoader` looks up the loader of the corresponding module in the current/parent layers; it can return `null` for the bootstrap loader, not only for a missing module.

### 7.6. Distinguishing the module loader from the parent loader

In the demo:

~~~java
ClassLoader appLoader = ClassLoader.getSystemClassLoader();
ClassLoader pluginLoader = layer.findLoader("plugin.echo");
~~~

- `appLoader` is the **parent loader parameter** passed when creating the child layer.
- `pluginLoader` is the **defining loader** set up by layer creation for the plugin module.
- `Extension.class.getClassLoader()` belongs to the loader that defines the shared API module in the boot layer.
- The plugin implementation class will have `pluginLoader` as its loader, while the API interface gets its class identity from the shared parent.

Do not conclude merely from the existence of a parent loader that the plugin class was **defined by the parent**. That is the difference between **delegation** and **definition**.

## 8. Complete, runnable Java 17+ program

Save the file `src/host/HostMain.java`:

~~~java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.ServiceLoader;
import java.util.Set;
import plugin.api.Extension;

public final class HostMain {
    public static void main(String[] args) {
        ModuleLayer boot = ModuleLayer.boot();

        System.out.println("apiInBoot="
                + boot.findModule("plugin.api").isPresent());
        System.out.println("echoNotInBoot="
                + boot.findModule("plugin.echo").isEmpty());

        ModuleFinder finder = ModuleFinder.of(
                Path.of("build/plugins"));
        Configuration configuration = boot.configuration()
                .resolve(finder, ModuleFinder.of(),
                         Set.of("plugin.echo"));

        ModuleLayer layer = boot.defineModulesWithManyLoaders(
                configuration, ClassLoader.getSystemClassLoader());
        Module pluginModule =
                layer.findModule("plugin.echo").orElseThrow();
        ClassLoader pluginLoader = layer.findLoader("plugin.echo");

        System.out.println("pluginResolved="
                + configuration.findModule("plugin.echo").isPresent());
        System.out.println("newLayerModule="
                + layer.modules().contains(pluginModule));
        System.out.println("parentApiVisible="
                + layer.findModule("plugin.api").isPresent());
        System.out.println("loaderFindsParentApi="
                + (layer.findLoader("plugin.api")
                    == boot.findLoader("plugin.api")));

        int count = 0;
        for (Extension ext :
                ServiceLoader.load(layer, Extension.class)) {
            count++;
            System.out.println("providerName=" + ext.name());
            System.out.println("providerResult=" + ext.execute("hello"));
            System.out.println("providerInChildModule="
                    + (ext.getClass().getModule() == pluginModule));
            System.out.println("providerLoaderMatches="
                    + (ext.getClass().getClassLoader() == pluginLoader));
            System.out.println("sharedApiIdentity="
                    + Extension.class.isAssignableFrom(ext.getClass()));
        }
        System.out.println("providerCount=" + count);

        ModuleLayer second = boot.defineModulesWithManyLoaders(
                configuration, ClassLoader.getSystemClassLoader());
        System.out.println("separateLayerSeparateModule="
                + (second.findModule("plugin.echo").orElseThrow()
                    != pluginModule));
        System.out.println("separateLayerSeparateLoader="
                + (second.findLoader("plugin.echo") != pluginLoader));
    }
}
~~~

Operations:

- `ModuleFinder.of(...)` creates a finder for the plugin directory.
- `Configuration.resolve(...)` creates a new graph with the provider root.
- `defineModulesWithManyLoaders(...)` creates the child ModuleLayer and the provider's loader.
- `ServiceLoader.load(layer, Extension.class)` requests discovery within that layer.
- `provider.getClass().getModule()` compares **Module object identity**, not just the String name.
- `provider.getClass().getClassLoader()` checks against the exact defining loader assigned by the layer.
- `Extension.class.isAssignableFrom(provider.getClass())` proves the provider is compatible with the host's runtime interface.
- Creating an additional child layer `second` from the same configuration allows comparing **two separate runtime Module objects** and loaders without altering the first layer.

**Note:** the example has only one provider, so the loop prints a single group of lines. A real plugin system can have multiple providers; discovery order should not be treated as priority unless the application defines its own provider selection policy.

## 9. Compilation and execution commands

### 9.1. Linux/macOS

From the `demo` directory, create the output directories and then use JDK 17+:

~~~sh
mkdir -p build/mods/plugin.api build/plugins/plugin.echo build/host

javac --release 17 \
  -d build/mods/plugin.api \
  src/plugin.api/module-info.java \
  src/plugin.api/plugin/api/Extension.java

javac --release 17 \
  --module-path build/mods \
  -d build/plugins/plugin.echo \
  src/plugin.echo/module-info.java \
  src/plugin.echo/plugin/echo/EchoExtension.java

javac --release 17 \
  --module-path build/mods \
  --add-modules plugin.api \
  -d build/host \
  src/host/HostMain.java

java \
  --module-path build/mods \
  --add-modules plugin.api \
  -cp build/host \
  HostMain
~~~

Do **not** put `build/plugins` on `--module-path` at launch time. If you use a different directory root, update `ModuleFinder.of(...)` in the host code accordingly before running.

### 9.2. Windows PowerShell

~~~powershell
New-Item -ItemType Directory -Force build/mods/plugin.api | Out-Null
New-Item -ItemType Directory -Force build/plugins/plugin.echo | Out-Null
New-Item -ItemType Directory -Force build/host | Out-Null

javac --release 17 -d build/mods/plugin.api src/plugin.api/module-info.java src/plugin.api/plugin/api/Extension.java

javac --release 17 --module-path build/mods -d build/plugins/plugin.echo src/plugin.echo/module-info.java src/plugin.echo/plugin/echo/EchoExtension.java

javac --release 17 --module-path build/mods --add-modules plugin.api -d build/host src/host/HostMain.java

java --module-path build/mods --add-modules plugin.api -cp build/host HostMain
~~~

These are single-line commands compatible with Windows PowerShell. The source directories must be created beforehand at the exact paths stated in section 4. No Maven, Gradle, external libraries, or platform-specific Java code are required.

### 9.3. Why is `--add-modules plugin.api` required?

The host runs on the **classpath/unnamed module** yet needs to call `Extension.class` from the named API module. Placing `plugin.api` on the module path is **not enough if the module has not been resolved as a root**. `--add-modules plugin.api` forces the JVM to resolve it into the boot layer at launch.

When compiling the host, `--module-path build/mods --add-modules plugin.api` is also needed so `javac` can see the exported type in the named API module. Do not include the implementation JAR/directory in the host's compile dependencies.

### 9.4. Verified exact stdout

~~~text
apiInBoot=true
echoNotInBoot=true
pluginResolved=true
newLayerModule=true
parentApiVisible=true
loaderFindsParentApi=true
providerName=echo
providerResult=PLUGIN:hello
providerInChildModule=true
providerLoaderMatches=true
sharedApiIdentity=true
providerCount=1
separateLayerSeparateModule=true
separateLayerSeparateLoader=true
~~~

The example was verified by compiling the three source groups with `javac --release 17` and running `java` on a JDK supporting Java 17. It does not depend on ClassLoader hashes, absolute paths, or filesystem ordering.

### 9.5. Explanation of the 14 lines

| Line | Meaning |
|---|---|
| `apiInBoot=true` | The shared API is resolved into the boot layer |
| `echoNotInBoot=true` | The implementation module has not been defined in the boot layer |
| `pluginResolved=true` | The child configuration resolved the provider module root |
| `newLayerModule=true` | The plugin Module object is defined directly in the child layer |
| `parentApiVisible=true` | The child layer sees the shared API from the parent layer |
| `loaderFindsParentApi=true` | The child's `findLoader` can look up modules in parent layers |
| `providerName=echo` | `ServiceLoader` created the plugin instance |
| `providerResult=PLUGIN:hello` | The plugin processes input through the shared API contract |
| `providerInChildModule=true` | The implementation class belongs to the exact runtime Module object of the child layer |
| `providerLoaderMatches=true` | The implementation class is defined by the loader returned by `layer.findLoader` |
| `sharedApiIdentity=true` | The provider implements the host's exact runtime service API type |
| `providerCount=1` | Exactly one provider was found in the demo configuration |
| `separateLayerSeparateModule=true` | Two sibling child layers have distinct runtime Module objects |
| `separateLayerSeparateLoader=true` | With `WithManyLoaders`, the two child layers have separate plugin loaders |

**Read accurately:** `ModuleLayer.findLoader(name)` **can search in parent layers**. Do not claim that it only looks up modules in the child layer. For a bootstrap-defined module such as `java.base`, the loader result can be `null` while the module is still valid.

## 10. One loader, many loaders, and custom mapping

### 10.1. `defineModulesWithOneLoader`

~~~java
ModuleLayer child = boot.defineModulesWithOneLoader(
        configuration,
        ClassLoader.getSystemClassLoader());
~~~

All **modules defined in the new configuration** use **one new ClassLoader**. If a plugin consists of multiple named modules that can share a single loader, this is a simple choice. However, package overlap or loader constraints can cause layer creation to fail.

**Do not assume** that every module in the **boot parent layer** is also moved into the new loader; only the modules in the new configuration are defined in the child layer.

### 10.2. `defineModulesWithManyLoaders`

~~~java
ModuleLayer child = boot.defineModulesWithManyLoaders(
        configuration,
        ClassLoader.getSystemClassLoader());
~~~

Each new module is defined with its own new loader. When there are multiple implementation modules, this can reduce certain package name conflicts. However, module readability/exports/opens and API type consistency are still required.

A provider module can reference types defined by the parent API module; there is no need to create another copy of the API in the child.

### 10.3. `defineModules` with a mapping function

If a framework needs to select a custom loader for each module:

~~~java
ModuleLayer child = boot.defineModules(
        configuration,
        moduleName -> loaderRegistry.get(moduleName));
~~~

This is an **architectural snippet**, not runnable on its own; you must prepare `loaderRegistry` and satisfy all module/package/delegation constraints of the API. It does not automatically turn an arbitrary ClassLoader into a complete JPMS-aware loader. Custom loaders must properly implement class/resource loading and avoid deadlocks/delegation cycles.

### 10.4. Instance and static overloads

Using `boot.defineModulesWithManyLoaders(cf, parentLoader)` returns a `ModuleLayer` directly. In contrast, the **static** methods:

~~~java
ModuleLayer.Controller controller =
        ModuleLayer.defineModulesWithManyLoaders(
                configuration,
                List.of(boot),
                ClassLoader.getSystemClassLoader());
ModuleLayer child = controller.layer();
~~~

This is a snippet requiring `java.util.List`, `configuration`, and `boot`. The static variant accepts a list of parent layers and returns a `Controller`, which can be used to perform certain readability/exports/opens adjustments through the controller according to its contract. Do not confuse its return type with that of the instance method.

### 10.5. Choosing a strategy for the problem

| Strategy | New module mapping | When to use | Notes |
|---|---|---|---|
| `WithOneLoader` | Multiple modules share one new loader | Modules work closely together with no package conflicts | Do not assume it is always valid with split packages |
| `WithManyLoaders` | One new loader per new module | You want namespaces separated per module | Shared API still needs to be consistent |
| `defineModules(cf, fn)` | Custom mapping | Container/plugin engine has its own loader policy | Complex to implement and debug |
| Static `ModuleLayer.defineModules...` | Includes `Controller` | Multiple parents or controller APIs are needed | Different return type from the instance method |

## 11. `resolve` and `resolveAndBind` in plugin architecture

### 11.1. `resolve` by root + requires

In the demo:

~~~java
Configuration configuration = boot.configuration().resolve(
        finder, ModuleFinder.of(), Set.of("plugin.echo"));
~~~

We **know the exact plugin module name** and resolve it as a root. The plugin's `requires plugin.api` is satisfied from the boot parent config.

### 11.2. `resolveAndBind` when using service binding

Another model is where the host module declares `uses plugin.api.Extension;` and wants the resolver to discover provider modules from the finder. In that case, `resolveAndBind` can add provider modules to the graph based on `provides` according to service binding rules.

However:

- Not every JAR containing a provider is selected in every resolution.
- The root graph/module finder scope and module descriptors affect binding.
- Service binding may pull in additional module dependencies or providers beyond the initial roots.
- `ServiceLoader.load(layer, service)` still requires a **layer that has already defined the provider modules**. It does not resolve the graph itself or load arbitrary JARs from disk outside the layer solely by service name.

It is important to distinguish **provider module discovery during resolution** from **provider object discovery/instantiation during ServiceLoader iteration**.

### 11.3. ModuleFinder first, ServiceLoader later

~~~text
Plugin artifacts
   |
   | ModuleFinder
   v
Resolved Configuration
   |
   | ModuleLayer.defineModules...
   v
Runtime ModuleLayer + loaders
   |
   | ServiceLoader.load(layer, Service.class)
   v
Provider instances
~~~

If the layer has not been created yet, `ServiceLoader.load(layer, ...)` has nowhere to look for new provider runtime modules. If the plugin has not been resolved, changing the TCCL will not make a `ModuleLayer` appear on its own.

## 12. Diagnostics: module is in the folder, but ServiceLoader finds no provider

### 12.1. Checking packaging/module descriptors

A plugin modular JAR must have the appropriate contract:

~~~text
plugin.echo.jar
  module-info.class
  plugin/echo/EchoExtension.class
~~~

The descriptor declares `provides plugin.api.Extension with plugin.echo.EchoExtension;`. If `provides` is omitted, `ServiceLoader.load(layer, Extension.class)` has no named-module provider declaration to find, even though the implementation class exists.

For an **explicit named module**, do not rely solely on `META-INF/services/plugin.api.Extension` as in the classpath model. Java SPI for the classpath has its own provider configuration file; for a JPMS explicit module, the descriptor's `provides` clause is the standard way to publish providers.

### 12.2. Checking runtime paths

Paths with different roles:

~~~text
--module-path build/mods
    => plugin.api in boot configuration

ModuleFinder.of("build/plugins")
    => plugin.echo is discovered while the host is running

-cp build/host
    => HostMain in the unnamed module
~~~

If you accidentally add `plugin.echo` to the boot roots, `echoNotInBoot` will no longer be true; if `plugin.api` is left unresolved in boot, provider dependency resolution may fail.

Do not conflate compile-time module path, launcher module path, dynamic ModuleFinder roots, and classpath.

### 12.3. Common causes

| Symptom | Cause to check | Remediation |
|---|---|---|
| `FindException` during finder/resolve | Invalid module artifact, missing module, or duplicate names | Check path/module-info.class, roots |
| `ResolutionException` | Module graph, package, or readability constraint conflicts | Read the exception; fix descriptors/dependencies |
| `LayerInstantiationException` | Cannot create loader/module mapping according to policy | Check package overlap and loader constraints |
| `NoClassDefFoundError` when the provider is used | Runtime dependency is not in the appropriate graph/loader | Check `requires`/modules/launcher path |
| `ServiceConfigurationError` | Incompatible provider declaration/constructor/module/class identity | Check `provides ... with` and the shared API type |
| No provider found even though the layer was created successfully | Missing `provides` or the plugin module was not resolved | Check `configuration.modules()`, `layer.modules()` |
| Provider class cannot be found by the host loader | Implementation belongs to a child module/loader | Use `ServiceLoader.load(layer,service)`; do not use host `Class.forName` |
| `ClassCastException` when casting the provider | Host and plugin use different runtime API types | Keep API in parent, check `Extension.class` identity |
| Module exists in file, but `findModule` is empty | ModuleFinder has not resolved the module as a root/dependency | Fix the root set/module finder |
| Plugin added later, but the host does not see it | Existing layer is immutable with respect to its modules | Create a new child layer or plugin manager generations |
| Changing TCCL does not change `ServiceLoader.load(layer,...)` | The layer-based overload uses the explicit layer | Pick the right overload/check which layer is actually used |
| Runtime JAR version differs from source | Wrong artifact packaged/deployed | Compare module descriptor, bytecode, and source version |
| Modules with the same name in sibling layers | Runtime module identities differ despite the same name | Keep the right layer reference and API bridge |

### 12.4. Distinguishing ClassLoader errors from JPMS access errors

A resolved module whose class loaded successfully can still encounter:

- `IllegalAccessError` if Java access or module exports are incompatible.
- `InaccessibleObjectException` on deep reflection into a package that is not `opens`.
- `NoSuchMethodException` or provider constructor/factory errors.
- `ClassCastException` if service API/runtime types are split.
- `ServiceConfigurationError` when the provider is invalid.

Do not just change `ClassLoader.getParent()` or blindly add `--add-opens`. Classify the error by stage: **resolution**, **definition**, **loading**, **access**, or **instantiation**.

## 13. A module layer is not automatic plugin hot reload

### 13.1. ModuleLayer does not allow "appending modules" to the same instance

Once a `ModuleLayer` is created, there is no `layer.addModule(newJar)` operation to arbitrarily define additional modules in the existing layer. To deploy a new plugin or a new version, you usually need a **new Configuration/layer**, choosing parent(s) and the module graph according to your design.

Two sibling layers can have a named module with the same name and identical implementation binary class names yet be **different runtime Module/Class objects**, as shown in the last two lines of the demo.

### 13.2. Lifecycle references preventing the loader from being GC'd

A plugin manager might retain:

- `ServiceLoader` and provider instances.
- `ModuleLayer`, `Module`, `ClassLoader`, `Class<?>`.
- `MethodHandle`/reflection caches.
- Threads, thread context class loaders, executors, and thread locals.
- Listeners, callbacks, scheduled tasks, or static maps.

Creating a new layer does not mean the old layer automatically unloads. When replacing a plugin, you need to stop the old code and clean up references and resources before the garbage collector can reclaim the classes/loaders when eligible.

### 13.3. API compatibility across multiple generations

The shared API module in the boot layer ensures the host and providers use the same `Extension.class`, but it does not guarantee that every plugin version is compatible:

- Changing a method descriptor can break binary compatibility.
- A new plugin requiring a different API revision that the host does not yet have will cause resolution/linkage errors.
- Shared DTOs/types appearing in method signatures must also have consistent identity.
- A child module can contain its own private dependencies, but if a private type leaks across the shared API boundary, ClassCastException/linkage problems can occur.

Production systems should have version metadata, a semantic compatibility policy, and health/startup validation before putting a plugin into service for requests.

### 13.4. Parent layer differs from parent ClassLoader

To reiterate according to the demo logic:

~~~text
ModuleLayer parent:
    Boot Layer
         |
         v
    Dynamic Plugin Layer

ClassLoader relationships (do not draw as 1:1):
    Application/system loader (parentLoader parameter)
         |
         v
    New loader for plugin.echo
~~~

The boot layer can contain modules defined by bootstrap, platform, and application loaders. **There is no rule that "one layer = one loader"**; the `WithOneLoader` and `WithManyLoaders` APIs explicitly choose different mappings.

### 13.5. Security boundary

`ModuleLayer` helps control module resolution/readability/exports/opens, but it is **not an OS sandbox** for running untrusted plugins. A provider in the same JVM can still use public Java APIs, consume CPU/RAM, and access any resources permitted to the process by the OS.

Untrusted plugins require process/container/VM isolation, least-privilege credentials, resource limits, network policies, and IPC authorization. On JDK 24+, `SecurityManager` has been disabled per JEP 486; do not design new sandboxes based on legacy SecurityManager policies.

## 14. Common mistakes to avoid

1. **"Having a module JAR in a folder means the runtime already has the module."** False: finder/artifact is different from resolve/define.
2. **"`ModuleFinder` creates a ClassLoader."** False: a module finder only provides references.
3. **"`Configuration.resolve` already instantiates providers."** False: it only resolves the graph.
4. **"The host must import the provider implementation."** False: shared API + service loader are designed so that this is unnecessary.
5. **"Merely placing a modular JAR on `--module-path` guarantees it will be resolved."** False: roots/dependencies/binding are needed.
6. **"The plugin and the shared API should each have their own separate copy of the API module."** False for the demo: this breaks shared type identity.
7. **"Without `exports plugin.echo`, `ServiceLoader` cannot use the provider."** False in a valid explicit module `provides` model.
8. **"`ServiceLoader.load(layer, Service.class)` uses the TCCL like the single-parameter overload."** False: this overload uses the passed-in layer.
9. **"`ServiceLoader` automatically finds JARs that have not been resolved and defined in a layer."** False: runtime modules must exist in the layer.
10. **"Parent ModuleLayer is parent ClassLoader."** False: they are two separate relationships.
11. **"`WithManyLoaders` creates a new loader for every module in the boot layer."** False: only for modules in the new configuration.
12. **"`WithOneLoader` is guaranteed to be valid for every module graph."** False: it can hit split-package/loader constraints.
13. **"`layer.modules()` lists ancestor modules as well."** False: only modules directly in the layer.
14. **"A child's `findLoader` cannot find a parent module."** False: it can look in parent layers.
15. **"`findLoader` returning null always means the module is missing."** False: the bootstrap loader is null; a missing module throws IllegalArgumentException.
16. **"Two layers with the same module name contain the same Module object."** False: sibling layers can have different identities.
17. **"Creating a new layer unloads the old layer."** False: references/threads can keep the old layer alive.
18. **"A separate loader guarantees the plugin cannot read host files."** False: a ClassLoader is not a sandbox.
19. **"`ServiceLoader` does not find a provider solely because `META-INF/services` is missing."** For an explicit named module, check `provides` in `module-info.java`.
20. **"You can change the module/loader mapping of an existing layer."** False: a new configuration and appropriate layer must be created.

## 15. Exercises and self-check questions

1. What are `ModuleFinder`, `Configuration`, `ModuleLayer`, and `ServiceLoader` each responsible for?
2. Why is `plugin.echo` not placed on the demo launcher's `--module-path`?
3. What does `--add-modules plugin.api` do to the boot layer?
4. Why do `Extension.class` in the host and in the plugin need the same runtime identity?
5. How must the plugin's `module-info.java` declare `requires` and `provides`?
6. Why is `plugin.echo` not required to declare `exports plugin.echo;` to act as a service provider?
7. How does an unnamed module host differ from a named module host regarding `uses`?
8. Why does `Configuration.resolve` not automatically run the provider's static initializer?
9. What additional step does `resolveAndBind` perform compared to `resolve`?
10. What happens if the module folder does not contain a valid `module-info.class`?
11. How do `defineModulesWithOneLoader` and `defineModulesWithManyLoaders` choose loaders?
12. Does the `parentLoader` parameter have the same meaning as the parent `ModuleLayer`?
13. Why does `layer.findLoader("plugin.api")` in the demo still return the loader from the boot layer?
14. Do `layer.modules()` and `layer.findModule("plugin.api")` have the same lookup scope?
15. Why is `plugin.echo` a named module in the child layer in the demo even though the host runs on the classpath?
16. Which `ServiceLoader` overload uses an explicit layer? How does it differ from the TCCL-based overload?
17. What does `provider.getClass().getModule() == pluginModule` verify?
18. What does `Extension.class.isAssignableFrom(provider.getClass())` help check?
19. Why can the same `Configuration` create two independent runtime child `ModuleLayer` instances?
20. If a plugin JAR is added to the filesystem after the layer has been created, how do you bring the new plugin into the runtime?
21. When should you use static `ModuleLayer.defineModules...` and `Controller`?
22. If a provider encounters `NoClassDefFoundError` at runtime, which parts of the graph/loader should you check?
23. If a provider uses different private dependency versions from the host, how do you prevent API type leaks?
24. Why is it necessary to stop plugin threads and clear TCCL/caches and provider references before unloading?
25. If a plugin comes from an untrusted source, is ModuleLayer sufficient as a sandbox?

**Completion criteria:** create the exact source tree, compile the API/provider/host, and run to get all **14 stdout lines** as documented; explain why the plugin is created in the child layer while the API is in the parent; use `ServiceLoader.load(layer, Extension.class)` successfully; and distinguish finder/resolve/define/service discovery and common errors.

## 16. Official documentation

- [Java SE 21 — ModuleLayer](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ModuleLayer.html): creating layers, `findModule`, `findLoader`, parents, controller.
- [Java SE 21 — Configuration](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/module/Configuration.html): `resolve`, `resolveAndBind`, resolution graph.
- [Java SE 21 — ModuleFinder](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/module/ModuleFinder.html): how to find modular JARs/exploded modules.
- [Java SE 21 — ServiceLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ServiceLoader.html): service provider modules, `load(ModuleLayer, Class)`, declaration.
- [Java SE 21 — Module](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Module.html): runtime module identity, loader, and layer.
- [Java SE 21 — Java launcher](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html): `--module-path`, `--add-modules`, `-cp`.
- [Java Language Specification §7.7 — Module Declarations](https://docs.oracle.com/javase/specs/jls/se21/html/jls-7.html#jls-7.7): module descriptors, `requires`/`exports`/`uses`/`provides`.
- [JEP 261 — Module System](https://openjdk.org/jeps/261): JPMS architecture.
- [JEP 486 — Permanently Disable the Security Manager](https://openjdk.org/jeps/486): limitations of the new security architecture for untrusted code.

**Conclusion:** creating a dynamic ModuleLayer is an explicit process: **ModuleFinder locates the plugin artifact → Configuration resolves the module graph → ModuleLayer defines runtime named modules and loaders → ServiceLoader uses the layer to create provider instances**. By keeping the shared API in the parent layer, the host can invoke modularized plugins without compile-time dependencies on the implementation, while preserving proper module/classloader identity and actively managing the plugin lifecycle.
