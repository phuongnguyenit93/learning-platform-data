# Classpath, Module Path, and Application-Managed Plugin Directories

In Java, all three concepts relate to locating and using compiled code, yet they answer **three different questions**:

- **Classpath:** Which paths does the JVM or a class loader search for classes and resources?
- **Module path:** Which modules does the Java Platform Module System (JPMS) locate to resolve dependencies, access rules, and module configuration?
- **Application-managed plugin directory:** Where does the application store extension packages, when does it discover them, and how does it decide to load, instantiate, disable, or replace them?

A directory named `plugins/` does not automatically become a classpath or module path. An application can use the JARs inside that directory to create a new `ClassLoader` or `ModuleLayer`; in that case, the directory is a **deployment convention owned by the application**, while the class loader or JPMS is the actual code-loading mechanism.

## 1. Quick Comparison

| Criterion | Classpath (`-cp` / `--class-path`) | Module path (`-p` / `--module-path`) | Application-managed plugin directory |
|---|---|---|---|
| Nature | A list of directories and JARs containing classes/resources | A list of locations containing Java modules | A storage location for extension bundles by application convention |
| Who interprets it? | Java launcher, compiler, and class loaders | The JPMS module resolver and module layers | The application's startup code, scanner, and plugin manager |
| Primary unit | Classes, packages, resources; code on the classpath belongs to the unnamed module of the defining class loader | Named modules with names, dependencies, and access rules; may include automatic modules | Plugin bundles with IDs, versions, metadata, state, and lifecycle defined by the application |
| Visibility | Depends on the class loader and delegation rules; no `exports` boundaries of named modules between classpath JARs | Resolved module dependencies, `requires`, `exports`, `opens`, and layers | Depends on the loader/layer created by the application, shared APIs, and registration policies |
| Automatic plugin discovery? | No; adding a JAR to the classpath does not automatically instantiate plugin objects | No; placing a module on the module path does not mean the application has activated a plugin | Only when the application explicitly scans, validates, loads, and registers it |
| Changes after JVM startup | Launcher classpath does not auto-update; separate class loaders can be created | Boot layer does not automatically load additional modules; new layers can be created | Can support install/uninstall/reload if the application designs an appropriate lifecycle |
| Typical use cases | Traditional Java applications and libraries | Applications/modules using JPMS to declare and enforce linkage | IDEs, integration platforms, extensible desktop/server applications |

**Note:** a JAR may physically reside in `plugins/`, yet be loaded by a `URLClassLoader` in classpath mode, or located by `ModuleFinder` and resolved as a named module. **The directory name does not determine the loading mechanism.**

## 2. Classpath: Lookup Path for Classes and Resources

Example on Linux/macOS, launching a non-modular application:

~~~bash
java -cp "app.jar:lib/*" com.example.Main
~~~

`-cp` declares the paths for the Java launcher to set up the classpath. `:` separates paths on Linux/macOS; Windows uses `;`. The wildcard `lib/*` includes JARs directly inside `lib`, without recursively scanning subdirectories. Launching with `java -jar app.jar` uses the entry point in the manifest and ignores the launcher's `-cp` option; any additional classpath, if needed, must be handled via manifest rules or a different launch mechanism.

Key points:

1. When `module-info.java` is not declared and JARs are placed on the classpath, classes belong to the **unnamed module** of the class loader that defined them. Packages in such JARs do not create per-JAR module boundaries.
2. The JVM does not have a single global class repository. `ClassLoader` looks up classes by binary name; most standard loaders delegate to their parent first. Two different loaders can define two classes with the **same name**, yet the JVM still treats them as **two distinct types**.
3. A library JAR being on the classpath only makes its code findable. The application must still invoke APIs, scan annotations, use `ServiceLoader`, or employ another mechanism to instantiate and register components.
4. Changing `java.class.path` via `System.setProperty` after the JVM has started **does not automatically update** existing loaders. For plugins loaded at runtime, applications typically create dedicated loaders.
5. `ServiceLoader` on the classpath looks for the descriptor file `META-INF/services/<fully-qualified-interface-name>`. Each valid line in the file contains the fully qualified name of a provider class. Classpath and `ServiceLoader` perform two different jobs: one makes classes findable, while the other locates service providers by contract.

### When does classpath make sense?

Use the classpath when dependencies are known at deployment time, you do not need JPMS module rules, and the application follows a traditional build/runtime model. The classpath is simple to deploy, but prone to duplicate libraries, version conflicts, and components seeing packages that ought to remain hidden.

## 3. Module Path: Where JPMS Locates and Resolves Named Modules

Since Java 9, the Java Platform Module System (JPMS) allows describing a module with `module-info.java`. Example of a public API:

~~~java
module com.example.greeting.api {
    exports com.example.api;
}
~~~

A plugin module depends on the API and provides an implementation:

~~~java
module com.example.greeting.plugin {
    requires com.example.greeting.api;
    provides com.example.api.GreetingPlugin
        with com.example.plugin.HelloPlugin;
}
~~~

A host module consumes this service:

~~~java
module com.example.greeting.host {
    requires com.example.greeting.api;
    uses com.example.api.GreetingPlugin;
}
~~~

These are **illustrative descriptors for the JPMS approach**, separate from the runnable classpath example in section 5. For a project compiled into modular JARs in `mods/`, the launch command may look like:

~~~bash
java --module-path mods \
     --add-modules com.example.greeting.plugin \
     --module com.example.greeting.host/com.example.host.Main
~~~

This command assumes `com.example.host.Main` is a valid entry point and all required modular JARs are present. `--add-modules` adds the plugin module to the set of resolved root modules; merely placing a JAR in `mods/` does not guarantee it is resolved or used by the application.

Understand these four concepts:

- **Resolve/readability:** JPMS selects which modules participate in the graph; `requires` declares a module dependency. A named module can only read modules permitted by the graph.
- **Exports:** `exports package` allows other modules to access `public` types in that package under JPMS rules. A `public` type in a non-exported package does not automatically become public API for other modules.
- **Opens:** `opens package` permits deep reflection according to the declared scope; it differs from `exports`. A framework using reflection may require `opens` without needing that package exported to every consumer.
- **Service binding:** `uses` and `provides ... with ...` declare service consumers and providers in named modules. `ServiceLoader` can use this information once the relevant modules are resolved.

A JAR without `module-info.class` can be treated as an **automatic module** when placed on the module path. This is a migration aid, but the module name derived from the JAR filename can be unstable; explicitly declared module names should be preferred for long-term designs.

**Module path does not equate to a hot-plugin mechanism.** The boot layer is established at startup and does not update automatically when you copy additional JAR files. For modular plugins added at runtime, the application must perform steps such as finding modules with `ModuleFinder`, resolving a `Configuration`, creating a new `ModuleLayer`, and discovering services. This approach requires careful handling of module names, dependencies, packages, and loaders.

## 4. Plugin Directory: Deployment Convention and Application Lifecycle

A deployment layout may look like:

~~~text
my-app/
  app.jar
  lib/
    greeting-api.jar
  plugins/
    hello-plugin.jar
    reporting-plugin.jar
~~~

`plugins/` is just a directory on the filesystem. If you run:

~~~bash
java -cp "app.jar:lib/*" com.example.Main
~~~

then the JARs in `plugins/` are **not on the classpath of that command**. Nor do they automatically join the JPMS module graph. To turn them into plugins, the host must implement a concrete protocol, for example:

1. Define a stable **extension contract**: interfaces/SPI, configuration, API version, and permissions available to plugins.
2. Discover JARs or plugin bundles in the directory; validate file types, metadata, IDs, and compatible versions.
3. Choose the loading mechanism: `URLClassLoader` for classpath-style plugins; `ModuleFinder` and `ModuleLayer` for named-module plugins.
4. Locate implementations via `ServiceLoader`, a manifest-declared entry point, or a custom protocol; validate that the provider is valid.
5. Register, start, monitor state, disconnect, and release resources according to a host-managed lifecycle.

This workflow explains why **file discovery**, **class loading**, **object instantiation**, and **feature activation** are four separate events. Copying a JAR into a directory is not enough to conclude the plugin is running.

### Relationship Between Host, API, and Implementation

~~~text
Host/application
    |
    +-- Shared API / SPI: GreetingPlugin  (host/parent loader)
    |
    +-- Plugin manager: scan plugins/*.jar
            |
            +-- New URLClassLoader or ModuleLayer
                    |
                    +-- Plugin implementation
                    +-- Plugin's dependency libraries (if provided)
~~~

The shared API should be supplied by the host/parent loader or a shared module. If a plugin accidentally packages a **duplicate copy** of this API inside its own class loader, two identically named types may still be incompatible, causing `ClassCastException` or similar type-identity errors.

## 5. Java 17+ Example: Host Loading Plugin JARs from a Directory

The example below is **runnable** on Java 17+ and does not use JPMS. The host is compiled against the API, while the implementation resides in a JAR inside `plugins/`, absent from the host's startup classpath.

Initial source structure:

~~~text
demo/
  src/
    api/com/example/api/GreetingPlugin.java
    plugin/com/example/plugin/HelloPlugin.java
    host/com/example/host/Host.java
~~~

**Step 1 — Shared API** (`src/api/com/example/api/GreetingPlugin.java`):

~~~java
package com.example.api;

public interface GreetingPlugin {
    String id();
    String greet(String name);
}
~~~

**Step 2 — Plugin implementation** (`src/plugin/com/example/plugin/HelloPlugin.java`):

~~~java
package com.example.plugin;

import com.example.api.GreetingPlugin;

public final class HelloPlugin implements GreetingPlugin {
    @Override
    public String id() {
        return "hello";
    }

    @Override
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

**Step 3 — Host lists JARs, creates loader, and finds providers** (`src/host/com/example/host/Host.java`):

~~~java
package com.example.host;

import com.example.api.GreetingPlugin;
import java.io.UncheckedIOException;
import java.net.MalformedURLException;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.ServiceLoader;
import java.util.stream.Stream;

public final class Host {
    public static void main(String[] args) throws Exception {
        Path pluginDir = Path.of("plugins");
        List<URL> jarUrls;

        try (Stream<Path> paths = Files.list(pluginDir)) {
            jarUrls = paths
                    .filter(Files::isRegularFile)
                    .filter(p -> p.getFileName().toString().endsWith(".jar"))
                    .sorted()
                    .map(p -> {
                        try {
                            return p.toUri().toURL();
                        } catch (MalformedURLException e) {
                            throw new UncheckedIOException(e);
                        }
                    })
                    .toList();
        }

        try (URLClassLoader loader = new URLClassLoader(
                jarUrls.toArray(URL[]::new),
                GreetingPlugin.class.getClassLoader())) {
            int count = 0;
            for (GreetingPlugin plugin
                    : ServiceLoader.load(GreetingPlugin.class, loader)) {
                System.out.println(plugin.id() + " -> " + plugin.greet("Java"));
                count++;
            }
            if (count == 0) {
                System.out.println("No plugin found.");
            }
        }
    }
}
~~~

Here:

- `Files.list` only **discovers files**; it does not load classes.
- `URLClassLoader` places the JARs on the plugin loader's class lookup path. The parent loader is the loader of `GreetingPlugin`, ensuring the shared API retains the same type identity.
- `ServiceLoader.load(GreetingPlugin.class, loader)` searches for provider configurations through the specified loader and instantiates implementations while iterating. Calling only the default overload that uses the context class loader may yield different results depending on the running thread.
- `try-with-resources` closes the loader once iteration finishes. In a real plugin system, the host keeps the loader alive for as long as the plugin remains active and closes it only afterward.

**Step 4 — Compile and package in Bash (Linux/macOS or Git Bash on Windows)**. Run in the `demo/` directory:

~~~bash
mkdir -p build/api build/plugin build/host plugins

javac -d build/api src/api/com/example/api/GreetingPlugin.java
javac -cp build/api -d build/plugin src/plugin/com/example/plugin/HelloPlugin.java

mkdir -p build/plugin/META-INF/services
printf '%s\n' 'com.example.plugin.HelloPlugin' \
  > build/plugin/META-INF/services/com.example.api.GreetingPlugin

jar --create --file plugins/hello-plugin.jar -C build/plugin .

javac -cp build/api -d build/host src/host/com/example/host/Host.java
java -cp "build/api:build/host" com.example.host.Host
~~~

Expected output:

~~~text
hello -> Hello, Java!
~~~

On Windows when using `java` or `javac` directly in PowerShell/CMD, the classpath separator character is `;`, for example `java -cp "build/api;build/host" com.example.host.Host`. The `mkdir -p` and `printf` commands above use Bash syntax.

The file `META-INF/services/com.example.api.GreetingPlugin` lives **inside the plugin JAR** and contains a single line:

~~~text
com.example.plugin.HelloPlugin
~~~

If this descriptor file is omitted, the host can still find the class via the loader, but `ServiceLoader` in the example will not know which provider to instantiate, so it prints `No plugin found.`. If `plugins/hello-plugin.jar` is added directly to `-cp`, that becomes static classpath deployment and no longer demonstrates a host managing a plugin directory on its own as above.

### Intentional Limitations of the Example

The example scans only JARs directly inside `plugins/`, uses **a single shared loader for all plugins in the directory**, does not scan recursively, and lacks signature checks, version checks, dependency resolution, or reloading when files change. If two plugins bring conflicting versions of the same library, a shared loader can still fail. This is a minimal prototype to highlight the code-loading steps, not a production plugin manager.

## 6. How Does a Named-Module Plugin Differ?

With JPMS, instead of `META-INF/services/...` in a classpath-style JAR, providers are typically declared via `provides ... with ...` in `module-info.java`; a named-module host must declare `uses`. Once the plugin module is **resolved into a layer**, the host can locate providers with `ServiceLoader.load(layer, GreetingPlugin.class)`.

When loading modules at runtime, API classes must be structured so that both host and plugins reference the exact same API module. One implementation approach is:

~~~java
// Snippet illustrating the core of a modular plugin manager;
// assumes the API is already in the boot layer and the plugin module exists.
ModuleFinder finder = ModuleFinder.of(Path.of("plugins"));
Configuration config = ModuleLayer.boot().configuration()
        .resolve(finder, ModuleFinder.of(),
                 Set.of("com.example.greeting.plugin"));
ModuleLayer layer = ModuleLayer.boot()
        .defineModulesWithOneLoader(
                config, ClassLoader.getSystemClassLoader());

ServiceLoader.load(layer, GreetingPlugin.class)
        .forEach(plugin -> System.out.println(plugin.id()));
~~~

This is an **integration snippet**, not a standalone program: it requires importing `java.lang.module.ModuleFinder`, `java.lang.module.Configuration`, `java.util.Set`, `java.util.ServiceLoader`, `java.nio.file.Path`, having `GreetingPlugin` from the API module, and ensuring the plugin JAR has a valid module descriptor. When deploying new modules, the host must manage roots, dependencies, duplicate module names, split packages, and layer lifecycles. A new layer also **does not automatically modify the contents** of an existing boot layer.

Choose `ModuleLayer` when you need JPMS semantics for plugins and accept the complexity of module resolution. Choose `URLClassLoader` when plugins are built on classpath/SPI and the class loader model satisfies your requirements. Both options still need a **plugin manager** to handle lifecycles; JPMS alone does not provide a complete mechanism for installing, upgrading, or removing plugins.

## 7. Dependencies, Isolation, and Version Updates

**Shared dependencies:** shared APIs/SPIs like `GreetingPlugin` should have compatible versions and be loaded consistently. Plugin implementations may depend on private libraries. With a parent-first `URLClassLoader`, classes already present in the parent are typically chosen first, so a host dependency can shadow the version a plugin expects.

**Isolation:** creating a separate loader/layer per plugin can reduce conflicts between implementations, but requires designing how APIs, messages, resources, and dependencies are shared. Custom child-first delegation is not a default silver bullet: it can break API sharing and cause duplicate class definitions. With JPMS, package visibility and readability help govern linkage, but do not eliminate the need to manage dependencies and service contracts.

**Reloading:** replacing a JAR file on disk does not replace classes already defined in an existing loader. Typically you must stop the old plugin, unregister it and close resources, create a new loader/layer, and then initialize the new plugin. The old class loader can only be garbage collected when no references remain to its classes, instances, threads, listeners, caches, static state, or resources. `URLClassLoader.close()` closes the loader's open resources; it **does not mean classes are unloaded immediately**.

**Safety:** class loaders and JPMS help organize code and control certain access capabilities, **not create a security sandbox for arbitrary plugin code**. A plugin running in the same process can perform dangerous actions with the process's permissions if the host allows it to execute. For untrusted plugins, consider separate processes/containers, restricted communication contracts, OS-level permission controls, and verification of provenance and resources.

## 8. Common Errors and Diagnostics

| Symptom | Causes to Check | How to Fix |
|---|---|---|
| `ClassNotFoundException` | JAR is not on the lookup path of the **right loader**, or wrong package/class name | Print the JAR path, inspect contents with `jar tf`, identify the calling loader |
| `NoClassDefFoundError` | Main class was found, but a dependency is missing during linking/initialization | Check plugin dependencies and the visibility scope of the loader/module |
| `ClassCastException` with two identically named classes | Host and plugin loaded duplicate copies of the API via two different loaders | Keep the shared contract in the common parent/API module; do not bundle overlapping APIs |
| `ServiceConfigurationError` | Wrong `META-INF/services` descriptor, wrong provider name, invalid provider, or instantiation error | Inspect the descriptor inside the JAR, provider constructor/method, and module linkage |
| `IllegalAccessError` / `InaccessibleObjectException` | Access boundary violation, missing `exports`/`opens`, or unauthorized deep reflection | Fix the module descriptor or design explicit APIs; do not open entire modules just to mask errors |
| No provider found despite JAR in `plugins/` | Host has not scanned/loaded or registered it; module unresolved; or missing service metadata | Trace sequentially: **discover → load → resolve → instantiate → register** |
| Errors after replacing a running JAR | Old loader/classes/instances still in use, or leftover file handles and resources | Design stop/close lifecycle, create a new loader, and clear old references |

A useful diagnostic practice is logging the **JAR path, plugin name, version, module name if present, the class loader that defined the provider, and registration status**. This usually clarifies issues much faster than trial-and-error adding of JARs to every path.

## 9. Which Model Should You Choose?

| Scenario | Starting Choice |
|---|---|
| Libraries are fixed dependencies of a traditional Java application | Classpath, using Maven/Gradle to manage dependencies |
| Application wants explicit module declarations and control over public/reflective package access | Module path and JPMS |
| Need independent plugin distribution discovered at startup or runtime | Plugin directory + plugin manager + appropriate class loader/layer |
| Plugins must load/unload new versions without restarting the host | Plugin manager with explicit lifecycle and fresh loaders/layers; track references/resources |
| Plugins come from untrusted third parties | Process isolation and execution permissions before considering classpath or JPMS |

You can also **combine** mechanisms: host and SPI run on the classpath, plugin JARs sit in `plugins/` and are loaded by the host via `URLClassLoader`; or a modular host runs on the module path while its plugin manager creates separate `ModuleLayer` instances for modular plugins. The central design question is not "which directory is the JAR in?", but **who discovers it, which loader/layer defines its classes, which API is shared, and who manages the lifecycle?**

## 10. Knowledge Self-Check

1. **Is copying `weather.jar` into `plugins/` and re-running `java -cp app.jar com.example.Main` enough for the plugin to work?** No. The host must have logic to scan the directory, load the JAR, find the provider, and register it; or a different loading mechanism must be explicitly configured.
2. **Does placing a JAR on `--module-path` guarantee its module is resolved?** No. The module graph depends on roots, `requires` relationships, service binding, and launch options such as `--add-modules`.
3. **Can `ServiceLoader` be used with the classpath?** Yes. Declare the provider via `META-INF/services`, then use the appropriate class loader. With named modules, use `uses` and `provides` under JPMS.
4. **Is using one class loader for multiple plugin JARs equivalent to isolating each plugin?** No. They share that loader's class-definition namespace; dependency and version collisions can occur.
5. **Does calling `close()` on `URLClassLoader` make all plugin classes disappear immediately?** No. The loader and classes can only be collected once no relevant references remain; threads, instances, or caches holding onto them will prevent collection.

**Remember:** **classpath** is the lookup path for classes/resources; **module path** is the input to JPMS's resolution and encapsulation; a **plugin directory** is a deployment location that the application actively turns into running components via loaders/layers, SPI, and lifecycle management.
