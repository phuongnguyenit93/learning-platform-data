# ClassLoader after JDK 8 and the URLClassLoader cast assumption

When upgrading an application or library from Java 8 to Java 9, 11, 17, 21, or newer JDK versions, a common error appears very early during startup:

```text
java.lang.ClassCastException:
  class jdk.internal.loader.ClassLoaders$AppClassLoader
  cannot be cast to class java.net.URLClassLoader
```

This error usually originates from code that worked on JDK 8:

```java
URLClassLoader loader =
    (URLClassLoader) ClassLoader.getSystemClassLoader();
```

On common OpenJDK/Oracle JDK 8 distributions, the application class loader is implemented on top of `URLClassLoader`. Starting in JDK 9, the JDK's class loading system was reorganized to support the Java Platform Module System (JPMS). The default application class loader is no longer an instance of `URLClassLoader`. The cast above therefore has no compatibility contract and can throw `ClassCastException`.

The key point is: **`ClassLoader` is the guaranteed abstraction; a specific implementation class of the system class loader is not a contract for application code to rely on.** `URLClassLoader` remains a public API and is still useful when an application creates its own loader to load JARs/plugins. What is no longer safe is assuming that a JVM-created loader must be of this type.

This lesson covers the changes after JDK 8, differences between the classpath and module path, how to access resources, how to load JARs dynamically, the role of the context class loader, and a migration process to eliminate implementation-dependent casts.

## 1. First: what does ClassLoader actually do?

`ClassLoader` is the Java component used to locate and define the classes needed by the JVM. When one class references another class, the JVM must find the corresponding definition from the classpath, modules, a custom loader, or a mechanism established by the runtime.

Several concepts should be kept distinct:

- **Binary name of a class:** a name such as `com.example.service.OrderService`.
- **Defining class loader:** the loader that actually defines the class in the JVM.
- **Initiating class loader:** the loader requested to load the class, which may delegate definition to another loader.
- **Class identity:** in principle determined by the binary name and the defining loader. Two classes with the same name defined by two different loaders are two different types.
- **Resource:** a data file accompanying classes/JARs, which can be located via the loader's or module's resource API, rather than being a `Class` itself.

Parent delegation is the common behavior: a loader asks its parent first before trying to find the class from its own sources. This helps prevent an application from accidentally replacing platform classes and keeps shared types consistent. However, not every custom class loader uses a parent-first policy; plugin containers and application servers may have their own rules.

A simple mental model for common runtimes:

```text
Bootstrap loader
    |
Platform loader
    |
Application (system) loader
    |
Custom loader(s) created by the framework/application
```

The diagram is a way to visualize common relationships, not a complete description of every module readability path or every class loader topology. In JPMS, module readability and which loader defines a class cannot be inferred solely from a parent chain.

### 1.1. When should ClassLoader be used?

Common needs:

1. Loading a class by name at runtime, such as a plugin or provider.
2. Locating resources such as `application.properties`, templates, or format files.
3. Detecting which loader actually loaded a class to diagnose dependency conflicts.
4. Using `ServiceLoader` to discover providers via the Java SPI mechanism.
5. Creating a dedicated loader for a plugin or for a group of JARs with an independent lifecycle.

There is no need to manipulate `ClassLoader` directly to instantiate classes that the program already knows at compile time. Such classes should be referenced in the usual way, allowing the compiler and build tool to check dependencies.

## 2. What changes when moving from JDK 8 to JDK 9+?

### 2.1. JDK 8: bootstrap, extension, and application loaders

In JDK 8, a common model consists of:

| Loader | Typical role |
|---|---|
| Bootstrap | Loads JDK platform classes |
| Extension | Loads extensions configured via the extension mechanism |
| Application/System | Loads application classes from the classpath |

In common OpenJDK/Oracle JDK 8 builds, the application class loader and extension class loader are implementations extending `URLClassLoader`. This caused many pieces of code to succeed by coincidence when casting `ClassLoader.getSystemClassLoader()` to `URLClassLoader`.

However, the `ClassLoader.getSystemClassLoader()` method has a declared return type of `ClassLoader`, **not** `URLClassLoader`. The actual implementation type is a detail of the running JDK and can differ when the vendor, version, or loader configuration changes.

Even on JDK 8, such casting code still relied on a fragile assumption: an application could configure a custom system loader or run in an environment where class loading differs from a standard Java launcher.

### 2.2. JDK 9: JPMS and the new loader structure

Starting in Java 9, JPMS was introduced into the JDK. Runtime modules changed how platform classes are packaged and formalized module readability, exports, and opens. At the same time, the implementation of the built-in class loaders was adjusted.

The model exposed through the API consists of:

- **Bootstrap class loader:** the foundational mechanism for loading core classes. There is no public `ClassLoader` object representing it in many diagnostic APIs.
- **Platform class loader:** obtainable via `ClassLoader.getPlatformClassLoader()`, replacing the role of the former extension loader.
- **System/application class loader:** obtainable via `ClassLoader.getSystemClassLoader()`. It typically loads classes on the application classpath and some application modules on the module path.

On modern OpenJDK runtimes, the default system loader may have a class name such as `jdk.internal.loader.ClassLoaders$AppClassLoader`. This is an internal implementation, **not** an API type that applications should import, cast to, or use reflection on to call internal methods.

`URLClassLoader` **was not removed from Java**. It still exists in the `java.net` package and can be instantiated directly for application-controlled URL/JAR loading scenarios.

### 2.3. The JDK 8 extension mechanism is no longer a deployment path

The extension directory and endorsed standards override mechanisms of older JDKs are no longer supported deployment models as they were prior to JDK 9. Scripts that relied on `java.ext.dirs`, `java.endorsed.dirs`, or copying JARs into the extension directory need to be redesigned.

Modern deployment approaches:

- For ordinary libraries, declare dependencies and place them on the classpath or module path.
- For modular applications, define modules and their `requires`/`exports`/`opens` relationships.
- For runtime plugins, use custom loaders or module layers following a clear contract.
- For upgrading platform modules, use only mechanisms supported and documented by the JDK; avoid replacing platform classes with classloader hacks.

### 2.4. Contract-level comparison

| Topic | Common on JDK 8 | Recommended on JDK 9+ |
|---|---|---|
| Obtaining the system loader | `ClassLoader.getSystemClassLoader()` | Keep using this API if the system loader is genuinely needed |
| Assuming system loader is URLClassLoader | Often true by coincidence | Incorrect; check the type and remove the cast |
| Obtaining the extension loader | Extension mechanism existed | Use `getPlatformClassLoader()` when the platform loader is needed |
| Listing system URLs | Cast to `URLClassLoader` then `getURLs()` | Use dependency metadata and diagnostics appropriate for classpath/modules |
| Adding JARs at runtime | Call internal methods or reflect on the app loader | Create an application-owned loader, or use a plugin/module layer |
| Loading classes from module path | No JPMS | Inspect module ownership, readability, and exports/opens |
| Locating resources | Typically searched via classpath | Resource APIs still exist, but account for module encapsulation |

## 3. Why does casting to URLClassLoader fail?

### 3.1. Failing code

```java
import java.net.URLClassLoader;

public class LegacyLoaderCode {
    public static void main(String[] args) {
        URLClassLoader loader =
            (URLClassLoader) ClassLoader.getSystemClassLoader();

        for (var url : loader.getURLs()) {
            System.out.println(url);
        }
    }
}
```

Declaring `URLClassLoader` on a local variable does **not** turn the system loader into a `URLClassLoader`. Java checks the instance type at runtime. If the object is not of the target type, the JVM throws `ClassCastException`.

The example above may run on a specific vendor's JDK 8 yet fail on JDK 17 or 21. The issue is not that `getURLs()` was renamed. The issue is that the program obtains an object it did not create and assumes that object's implementation.

### 3.2. The `getURLs()` method belongs to URLClassLoader, not ClassLoader

`URLClassLoader.getURLs()` returns the URLs configured for **that specific URLClassLoader**. The base `ClassLoader` makes no promise to provide a list of URLs, because not every loader locates classes from URLs.

A loader can obtain classes from:

- A runtime module image.
- An archive or file system other than standard URLs.
- Byte arrays generated or transformed at runtime.
- A network source or custom plugin repository.
- A container/application server.
- A classloader graph with multiple different sources.

Therefore, a universal API to "get all JARs visible to every class loader" cannot be derived from `ClassLoader.getSystemClassLoader()`.

### 3.3. Do not fix by reflecting on internal implementations

Some incorrect migration snippets often appear:

```java
// AVOID: depending on an internal implementation.
Class<?> impl = Class.forName(
    "jdk.internal.loader.ClassLoaders$AppClassLoader"
);

// AVOID: looking up the internal addURL method via reflection.
// AVOID: opening internal packages en masse just to fix old assumptions.
```

Starting in Java 9, module encapsulation can reject reflective access to internal components. Options like `--add-opens` or `--add-exports` can modify access permissions where necessary, but they do not turn an internal implementation into a stable API.

Identify the **original intent** of the cast: listing the classpath, loading resources, or dynamically adding JARs? Each intent has a different solution.

## 4. Choosing the right solution by intent

| Original intent of legacy code | Appropriate solution | What to avoid |
|---|---|---|
| Finding config files or templates | `getResourceAsStream`, `getResource`, or `Module.getResourceAsStream` | Casting system loader to `URLClassLoader` to inspect URLs |
| Getting classpath paths for logging | `java.class.path`, data from build/launch config | Treating classpath as the entire module path or every class source |
| Knowing where a class was loaded from | `Class.getProtectionDomain()`/`CodeSource` when available, `getClassLoader()`/`getModule()` | Assuming URL or `CodeSource` always exists |
| Loading classes from a plugin JAR | Create the application's own `URLClassLoader` | Trying to append URLs to the system loader |
| Finding service implementations | `ServiceLoader` with the appropriate loader or layer | Scanning every JAR and casting manually or scanning internal packages |
| Loading modular applications | Module path, `ModuleLayer` | Assuming all named modules reside on the classpath |
| Diagnosing linkage errors | Logging, `-Xlog:class+load`, `jdeps`, module metadata | Only printing `getURLs()` of a single loader |

Do not simply turn every cast into an `instanceof` check and stop there:

```java
ClassLoader loader = ClassLoader.getSystemClassLoader();

if (loader instanceof URLClassLoader urls) {
    // Only works when loader is actually a URLClassLoader.
}
```

`instanceof` can be a local compatibility measure if the block is optional diagnostics, but it does not provide a solution for functional requirements. If loading a plugin or resource is mandatory, there must be a proper handling path when the loader is not a `URLClassLoader`.

## 5. Classpath and module path are not a single shared URL list

### 5.1. Traditional classpath

For applications that do not use modules, the JVM can accept JARs and directories via the classpath:

```shell
java -cp "app.jar:lib/*" com.example.Main
```

The illustrative example above uses the colon commonly seen on Unix-like OSes. On Windows, the classpath separator is normally a semicolon. In Maven/Gradle, IDEs, or deployment scripts, the classpath may be generated automatically.

Non-modular applications usually reside in the **unnamed module** associated with their class loader. JPMS still exists in the JDK, but the application can continue using the classpath.

### 5.2. Module path and named modules

A modular application can have a descriptor:

```java
module com.example.app {
    requires com.example.api;
}
```

And be launched with:

```shell
java --module-path mods --module com.example.app/com.example.app.Main
```

Named modules are resolved via the module path and module graph mechanisms. This adds an access control layer and dependencies that cannot be accurately represented by `URLClassLoader.getURLs()`.

Some differences:

- `requires` defines module readability relationships.
- `exports` allows other modules to access public packages according to JPMS rules.
- `opens` relates to deep reflective access and access permissions for certain resources.
- Modules can be placed in different layers.
- A class loader can define multiple modules, though that does not mean every module in a layer is defined by the same loader.

To inspect the module of a specific class, use the official API:

```java
Class<?> type = com.example.app.Main.class;

Module ownerModule = type.getModule();
ClassLoader definingLoader = type.getClassLoader();

System.out.println("Module: " + ownerModule.getName());
System.out.println("Named module: " + ownerModule.isNamed());
System.out.println("Class loader: " + definingLoader);
```

`getClassLoader()` can return `null` for classes defined by the bootstrap loader. Do not treat null as necessarily an error.

### 5.3. Why is `java.class.path` not enough for every application?

`System.getProperty("java.class.path")` usually reports the application's classpath according to the launcher configuration. However, it is not a complete map for:

- Named modules located on the module path.
- Modules created in dynamic layers.
- JARs loaded by custom loaders.
- Classes generated from byte arrays.
- Certain runtime images or custom embedded environments.

If you only need to log the classpath, this property can be useful. If you need to inventory all system dependencies, combine it with the build tool, dependency graph, module descriptors, and corresponding runtime information.

### 5.4. Checking the module graph at startup

Some useful launcher options:

```shell
java --show-module-resolution \
     --module-path mods \
     --module com.example.app/com.example.app.Main
```

The trailing backslashes above illustrate Unix shell style. On Windows PowerShell, use a single-line command or the appropriate line-continuation syntax.

The command helps observe module resolution in a specific configuration. It does not replace testing the custom runtime loaders of a plugin container.

## 6. Loading resources without URLClassLoader

### 6.1. Using `getResourceAsStream` for resources on the classpath

A resource such as `config/app.properties` can be placed in `src/main/resources` and packaged into the JAR. It can then be read directly:

```java
import java.io.IOException;
import java.io.InputStream;
import java.util.Properties;

public final class ConfigReader {
    public static Properties load() throws IOException {
        ClassLoader loader = ConfigReader.class.getClassLoader();

        try (InputStream input = loader.getResourceAsStream(
                "config/app.properties")) {

            if (input == null) {
                throw new IOException("Resource not found");
            }

            Properties props = new Properties();
            props.load(input);
            return props;
        }
    }
}
```

There is no need to know whether the loader is `URLClassLoader` or an internal implementation. If the class is in the bootstrap loader, another appropriate resource path or a designed fallback can be used; the application example above typically has a non-null application loader.

### 6.2. Differences between `Class.getResource` and `ClassLoader.getResource`

`ClassLoader.getResource("x/y.txt")` takes a resource name relative to the root that the loader searches, **without** a leading `/`.

`Class.getResource("file.txt")` typically searches for a resource relative to the class's package. `Class.getResource("/x/y.txt")` searches by absolute path from the root of the appropriate resource scope.

Example:

```java
// Resource in the same package as MyService.class:
var local = MyService.class.getResource("template.txt");

// Resource using an absolute path:
var absolute = MyService.class.getResource("/templates/page.html");

// Resource via class loader:
var viaLoader = MyService.class
    .getClassLoader()
    .getResource("templates/page.html");
```

Confusion over the `/` character often causes "resource not found" errors when migrating code between APIs. Clearly identify the path packaged inside the JAR and the source class/module containing the resource.

### 6.3. Resources in named modules have additional access conditions

In JPMS, a resource residing inside a module JAR does not guarantee every loader can read it from every module. For resources inside a named module's package, package encapsulation/opening rules can affect access via a class loader or module API.

A module can read its own resources:

```java
import java.io.IOException;
import java.io.InputStream;

static InputStream openOwnResource() throws IOException {
    Module module = MyService.class.getModule();

    InputStream input =
        module.getResourceAsStream("com/example/app/config.properties");

    if (input == null) {
        throw new IOException("Module resource unavailable");
    }

    return input;
}
```

The caller is responsible for closing the returned stream. For strongly encapsulated modules, consider placing the resource in an appropriate location, using the module API, or providing a public API for retrieval instead of opening packages unnecessarily.

Do not add `--add-opens` to every command just to work around misplacing a resource or calling the wrong API.

### 6.4. Duplicate resource names

Two JARs can contain the same path, such as `META-INF/services/...` or `config/defaults.properties`. The `getResource` method returns a single result according to the search order; the actual order can depend on loader configuration.

If business logic needs to discover multiple resources with the same name:

```java
import java.io.IOException;
import java.net.URL;
import java.util.Enumeration;

static void printAllResources(
        ClassLoader loader,
        String name) throws IOException {

    Enumeration<URL> urls = loader.getResources(name);

    while (urls.hasMoreElements()) {
        URL url = urls.nextElement();
        System.out.println(url);
    }
}
```

`getResources` only searches within the loader's search scope and related boundaries; it is not an API to inventory all modules/URLs of every loader in the process.

## 7. Choosing the right loader for dynamic class loading

### 7.1. Obtaining the system loader

`ClassLoader.getSystemClassLoader()` is the valid API when you want to reference the loader configured as the system loader. There is no reason to cast it to a concrete type:

```java
ClassLoader systemLoader = ClassLoader.getSystemClassLoader();

Class<?> type = Class.forName(
    "com.example.extension.ExampleService",
    true,
    systemLoader
);
```

The example only works if that class is actually visible from the system loader. Classes in a child plugin loader are not necessarily visible upward from the parent/system loader.

### 7.2. Obtaining the loader that defined a class

If code needs to load resources or classes related to an existing API, the loader of that class is usually used:

```java
ClassLoader apiLoader = PublicPluginApi.class.getClassLoader();
```

This is a good choice when you want the class identity of a shared API to remain consistent. However, if the API resides in the bootstrap loader, the result can be `null`. Plugin requirements may need a specific parent; declare it explicitly rather than arbitrarily falling back to the system loader in every case.

### 7.3. Thread Context ClassLoader (TCCL)

Frameworks and SPIs often need to locate application-provided implementations even though framework code is loaded by a parent-tier loader. `Thread.currentThread().getContextClassLoader()` is a useful mechanism for this situation.

```java
ClassLoader contextLoader =
    Thread.currentThread().getContextClassLoader();

System.out.println("Context loader: " + contextLoader);
```

Do not assume TCCL is the system loader or the loader defining the current class. Application servers, executors, plugin containers, or frameworks can set it differently. The context loader can be `null` in certain configurations.

If temporarily changing TCCL within the scope of a task, restore the previous value:

```java
Thread thread = Thread.currentThread();
ClassLoader previous = thread.getContextClassLoader();

try {
    thread.setContextClassLoader(pluginLoader);
    runPluginTask();
} finally {
    thread.setContextClassLoader(previous);
}
```

Do not let pooled threads retain a plugin's TCCL after completing a request; doing so both creates a risk of loading the wrong implementation and holds a reference to the plugin loader, preventing the class loader from being reclaimed.

## 8. Loading plugin JARs dynamically with an application-created URLClassLoader

### 8.1. This is where URLClassLoader remains appropriate

If the application needs to load an additional JAR at runtime, a new `URLClassLoader` can be created:

```java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

Path pluginJar = Path.of("plugins", "demo-plugin.jar");
URL[] pluginUrls = { pluginJar.toUri().toURL() };

URLClassLoader pluginLoader = new URLClassLoader(
    pluginUrls,
    Plugin.class.getClassLoader()
);
```

Here `Plugin` represents the shared API interface between the host and plugin. The parent loader is chosen so that the plugin sees the shared API. If the parent lacks that API, or the plugin bundles another copy of the API with the same name, type conflicts can result.

Do not grab the system loader and mutate its internal URL list via reflection. A new loader cleanly isolates the scope of plugin dependencies and enables implementing a dedicated lifecycle.

### 8.2. A complete design-level plugin example

The host defines the API:

```java
package com.example.api;

public interface Plugin {
    String execute(String input);
}
```

The plugin JAR provides the implementation:

```java
package com.example.plugin;

import com.example.api.Plugin;

public final class UppercasePlugin implements Plugin {
    @Override
    public String execute(String input) {
        return input.toUpperCase(java.util.Locale.ROOT);
    }
}
```

The host loads the plugin from the JAR by class name:

```java
import com.example.api.Plugin;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class PluginRunner {
    public static void main(String[] args) throws Exception {
        Path jar = Path.of("plugins", "uppercase-plugin.jar");
        URL[] urls = { jar.toUri().toURL() };

        try (URLClassLoader loader = new URLClassLoader(
                urls,
                Plugin.class.getClassLoader())) {

            Class<?> impl = Class.forName(
                "com.example.plugin.UppercasePlugin",
                true,
                loader
            );

            if (!Plugin.class.isAssignableFrom(impl)) {
                throw new IllegalArgumentException(
                    "Class does not implement host Plugin API"
                );
            }

            Plugin plugin = (Plugin) impl
                .getDeclaredConstructor()
                .newInstance();

            System.out.println(plugin.execute("hello"));
        }
    }
}
```

Notes:

1. The host and plugin must agree on a single `Plugin` API definition defined by a compatible loader.
2. The code above illustrates a classpath plugin; it does not automatically satisfy named module requirements of modular plugins.
3. The plugin is selected by class name. If discovery is needed, `ServiceLoader` can be used.
4. Close the `URLClassLoader` once finished using it and after resources created by the plugin have been closed.
5. Closing the loader releases certain resources owned by the loader, but does not force all loaded classes to be unloaded immediately. If the host still retains classes, instances, threads, listeners, static references, or the context loader, the class loader may remain reachable.

### 8.3. Plugin lifecycle and versioning

For a real-world plugin system, define:

- `start()`, `stop()`, or an equivalent lifecycle API.
- Who creates and closes the plugin loader.
- Which threads or scheduled tasks the plugin is permitted to create.
- How to register/unregister listeners, callbacks, and registry entries.
- Version of the plugin API and required dependencies.
- Behavior when a plugin fails during initialization or shutdown.
- Reload capability and mechanisms to clear old references.

Do not simply call `URLClassLoader.close()` and declare the plugin unloaded. The JVM can retain classes and loaders longer if references remain; external resources must be cleaned up according to the designed lifecycle.

### 8.4. Caution with parent-first and duplicate dependencies

By default, `URLClassLoader` typically delegates class lookup to the parent first. When the host and plugin use different versions of the same library, the plugin may receive classes from the parent instead of its own JAR.

The solution is not simply writing a custom child-first loader for every package. Partition namespaces:

- Shared APIs must have a consistent identity.
- Internal plugin libraries may need isolation.
- Plugins must not be allowed to replace Java platform classes.
- Shared dependencies need an appropriate versioning or shading policy.
- If using a custom child-first policy, check class identity and security thoroughly.

## 9. When plugins are named modules: consider ModuleLayer

A JPMS application may need to load modules not available in the boot layer. `ModuleLayer` provides a mechanism to create a new module layer with a designed configuration and class loader.

Concept:

```text
Boot module layer
  ├─ com.example.api
  └─ com.example.host
       |
       +-- Child module layer
             └─ com.example.plugin
```

The host can locate plugin modules using `ModuleFinder` and create a new configuration/layer using the module API.

Guiding example:

```java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.Set;

Path plugins = Path.of("plugins");
ModuleFinder finder = ModuleFinder.of(plugins);

ModuleLayer parentLayer = ModuleLayer.boot();

Configuration configuration =
    parentLayer.configuration().resolve(
        finder,
        ModuleFinder.of(),
        Set.of("com.example.plugin")
    );

ModuleLayer pluginLayer =
    parentLayer.defineModulesWithOneLoader(
        configuration,
        ClassLoader.getSystemClassLoader()
    );
```

The code assumes a `com.example.plugin` module exists on the plugin path and the module graph resolves. `defineModulesWithOneLoader` is one strategy; the JPMS API offers other ways to map modules to loaders. Do not assume every modular plugin can reuse a URLClassLoader like a classpath plugin.

After creating the layer, you can retrieve the loader that loads a specific module:

```java
ClassLoader moduleLoader =
    pluginLayer.findLoader("com.example.plugin");
```

If the plugin provides services, consider `ServiceLoader.load(layer, serviceType)` and proper `uses`/`provides ... with` declarations in the module descriptor. Modules need appropriate readability and visibility relationships.

**A module layer is not a security sandbox.** It organizes the module graph and loaders, and does not reliably restrict malicious plugin code from accessing the filesystem or network. When running untrusted code, process/container-level isolation or an equivalent mechanism is required.

## 10. ServiceLoader: discovery instead of manually scanning URLs

### 10.1. Why is the SPI API useful?

Many legacy applications list JARs via `URLClassLoader.getURLs()` and then search for classes ending with a certain suffix. This approach depends on JAR structure, classpath, and loader implementation.

`ServiceLoader` lets an API define a service interface and lets plugins/providers declare implementations. Consuming code does not need to know the exact JAR file or URL of each provider.

API example:

```java
package com.example.api;

public interface ReportFormatter {
    String format(String report);
}
```

For a provider on the classpath, the JAR contains the file:

```text
META-INF/services/com.example.api.ReportFormatter
```

The file contents list the implementation class names, one per line:

```text
com.example.plugins.JsonFormatter
```

The application can discover providers:

```java
import com.example.api.ReportFormatter;
import java.util.ServiceLoader;

ServiceLoader<ReportFormatter> providers =
    ServiceLoader.load(ReportFormatter.class);

for (ReportFormatter formatter : providers) {
    System.out.println(formatter.format("sample"));
}
```

`ServiceLoader.load(serviceType)` normally uses TCCL. If a specific loader matters, use the overload taking a `ClassLoader`:

```java
ServiceLoader<ReportFormatter> providers =
    ServiceLoader.load(ReportFormatter.class, pluginLoader);
```

With named modules, the provider can use directives in `module-info.java`:

```java
module com.example.plugin {
    requires com.example.api;

    provides com.example.api.ReportFormatter
        with com.example.plugin.JsonFormatter;
}
```

A modular consumer also needs to declare `uses` appropriately according to the JPMS contract. With dynamic layers, use the `ServiceLoader.load(layer, serviceType)` overload.

### 10.2. Limitations of ServiceLoader

`ServiceLoader` is not a full lifecycle management framework or versioning mechanism. Providers can throw exceptions during instantiation; multiple providers can be discovered simultaneously; results can depend on the loader and layer.

Verify:

- Which providers are allowed and in what order.
- How to select a provider when multiple implementations exist.
- How to close providers that hold resources.
- How to reload when plugins change.
- Which loader defines the service API.
- Provider compatibility when the interface changes.

## 11. Diagnosing loaders, classpath, and modules at runtime

### 11.1. Printing information about the class in use

When investigating issues, print the class, loader, and module instead of casting the loader to URLClassLoader:

```java
public final class LoaderReport {
    public static void report(Class<?> type) {
        Module module = type.getModule();
        ClassLoader loader = type.getClassLoader();

        System.out.println("Class: " + type.getName());
        System.out.println("Module: " + module.getName());
        System.out.println("Named: " + module.isNamed());
        System.out.println("Defining loader: " + loader);
        System.out.println("System loader: "
            + ClassLoader.getSystemClassLoader());
        System.out.println("Platform loader: "
            + ClassLoader.getPlatformClassLoader());
        System.out.println("Context loader: "
            + Thread.currentThread().getContextClassLoader());
    }

    public static void main(String[] args) {
        report(LoaderReport.class);
        report(String.class);
    }
}
```

`String.class.getClassLoader()` typically returns `null` because the class is defined by the bootstrap loader. If an internal loader implementation name is printed, use it only for diagnostics; do not add a compile dependency on that package.

### 11.2. Checking CodeSource when available

`ProtectionDomain` and `CodeSource` can sometimes indicate which JAR or location a class was loaded from:

```java
import java.net.URL;
import java.security.CodeSource;
import java.security.ProtectionDomain;

static URL codeSourceOf(Class<?> type) {
    ProtectionDomain domain = type.getProtectionDomain();

    if (domain == null) {
        return null;
    }

    CodeSource source = domain.getCodeSource();
    return source == null ? null : source.getLocation();
}
```

The result can be `null`, especially for certain platform classes, dynamically generated classes, or custom loader configurations. `CodeSource` is useful for diagnostics but is not guaranteed as a classpath-listing API.

### 11.3. Using JVM logs to see loaded classes

On modern JDKs, unified logging supports class loading diagnostics:

```shell
java -Xlog:class+load=info -jar app.jar
```

Logs can reveal class names and loading sources. Enable it in an appropriate environment and control log volume. Tag syntax/details may vary across JVM versions; confirm on the target JDK.

`jdeps` can be used to inventory static dependencies and internal API issues:

```shell
jdeps --jdk-internals app.jar
jdeps --print-module-deps app.jar
```

`jdeps` does not see every dependency loaded via reflection or runtime plugins. Combine it with unit/integration tests and actual logs.

### 11.4. Printing modules present in the boot layer

```java
ModuleLayer.boot().modules().stream()
    .map(Module::getName)
    .sorted()
    .forEach(System.out::println);
```

This list does not include modules in other dynamic layers. If the application creates layers itself, retain metadata about those layers for diagnostics.

## 12. Errors from the same class name with different loaders

### 12.1. Class identity is not just the name

Suppose both the host and plugin package `com.example.api.Plugin`, but each copy of the class is defined by a different loader. Then:

```text
com.example.api.Plugin defined by HostLoader
com.example.api.Plugin defined by PluginLoader
```

These two types are distinct despite having the same binary name. A cast can fail with `ClassCastException`, or the JVM can report a loading constraint violation depending on the context.

Do not solve this by changing the display name in logs. Ensure shared APIs are loaded from a single shareable loader; avoid bundling duplicate copies of the API inside the plugin JAR without a valid design reason.

### 12.2. Related errors with similar symptoms

| Error | Common cause | Investigation direction |
|---|---|---|
| `ClassCastException` | Casting to wrong loader implementation or two same-named classes with different defining loaders | Print `getClassLoader()` of both types |
| `ClassNotFoundException` | Requested loader cannot find class by name | Check loader, classpath/module path, and package |
| `NoClassDefFoundError` | Class was referenced but could not be properly defined/linked/initialized | Read the cause, check dependencies and initializers |
| `IllegalAccessError` | Illegal access at runtime | Check module exports, binary changes, and class access |
| `InaccessibleObjectException` | Deep reflection denied | Check opens, dependencies, and internal APIs |
| `ServiceConfigurationError` | Missing, wrong-type, uninstantiable, or misdeclared SPI provider | Check `META-INF/services`, `provides`, and loader/layer |
| `LinkageError` | Class definition or linkage conflict | Check class identity, versions, and loader graph |

Do not look only at the first exception in the log. For class initialization failures, the cause chain often contains the root cause.

## 13. Security and encapsulation issues after JDK 8

### 13.1. JPMS does not turn ClassLoader into URLClassLoader

JPMS introduces the module graph and package encapsulation model. Opening packages with `--add-opens` can permit certain reflective accesses, but it does not make the system loader an instance of `URLClassLoader`.

Therefore, fixing `ClassCastException` by adding `--add-opens java.base/jdk.internal.loader=ALL-UNNAMED` does not address the root cause. An object's inheritance hierarchy does not change based on JVM flags.

### 13.2. Avoiding dependencies on `sun.*` and `jdk.internal.*`

Internal packages can change or be restricted without the source/binary compatibility guarantees of public APIs. For migration:

- Use `ClassLoader`, `URLClassLoader`, `Module`, `ModuleLayer`, and `ServiceLoader`.
- Replace `sun.misc.Launcher` or similar implementations with official APIs according to the intended purpose.
- Do not put internal class names in configuration or code just to call unpublished methods.
- Read third-party library release notes if they perform deep classloading manipulation.

### 13.3. Untrusted plugins require separate isolation

Simply having a dedicated loader does not mean plugin code is sandboxed. `ClassLoader` handles loading and namespace/class identity isolation; it does not prevent a plugin from calling OS APIs that the process has permission to use.

For untrusted plugins, consider running in a separate process or container, restricting filesystem, network, and privileges according to the system's threat model. Do not rely on the Security Manager as a general solution for newer JDKs, because this mechanism has been disabled in the modern roadmap.

## 14. Step-by-step migration from JDK 8

### Step 1: Inventory assumptions in the source code

Search for patterns:

- Casting `ClassLoader.getSystemClassLoader()` to `URLClassLoader`.
- Casting `getParent()` or TCCL to `URLClassLoader`.
- Using reflection on `addURL` of the system loader.
- Using `sun.misc.Launcher`, `sun.misc.URLClassPath`, or `jdk.internal.loader`.
- Scanning `getURLs()` to find plugins, resources, or classpath entries.
- Relying on extension/endorsed directories.
- Manually replacing module access logic with classpath URLs.
- Assuming any classes with the same name can be cast across loaders.

Example initial queries using ripgrep:

```shell
rg -n "URLClassLoader|getSystemClassLoader|getContextClassLoader" src
rg -n "getURLs\\(|addURL\\(|java\\.ext\\.dirs|endorsed" .
rg -n "sun\\.misc\\.Launcher|jdk\\.internal\\.loader" .
rg -n "Class\\.forName|ServiceLoader|ModuleLayer" src
```

These are preliminary text queries. Bytecode/dependencies must also be examined if the failing code resides in external libraries.

### Step 2: Document the intent of each location

Create an inventory table:

| Location | Intent | Legacy code | Replacement approach |
|---|---|---|---|
| ResourceUtil | Find config in JAR | Cast system loader then iterate URLs | `getResourceAsStream` |
| StartupReporter | Print classpath | `((URLClassLoader) loader).getURLs()` | `java.class.path` and module diagnostics |
| PluginManager | Add JAR at runtime | Reflective `addURL` | Custom `URLClassLoader` or module layer |
| ProviderDiscovery | Find implementations | Manual JAR scanning | `ServiceLoader` |
| ContainerAdapter | Obtain class from framework | Trying to obtain system loader | TCCL or framework-provided loader |

Do not turn a valid fix for ResourceUtil into a global replacement rule. Each intent requires its own API.

### Step 3: Separate abstraction from implementation

Change the receiving variable type from `URLClassLoader` to `ClassLoader` when only general methods are needed:

```java
// Before migration:
URLClassLoader loader =
    (URLClassLoader) ClassLoader.getSystemClassLoader();

// After migration:
ClassLoader loader = ClassLoader.getSystemClassLoader();
```

This is only the first step. If the code still calls `loader.getURLs()`, it must be switched to a solution matching the intent of that call. Do not simply delete the `getURLs()` statement and drop important behavior.

### Step 4: Update libraries and frameworks

A dependency may contain a cast that application source code searches do not reveal. Check:

- Legacy container/plugin frameworks.
- Template or script engines that load classes dynamically.
- Serialization, ORM, proxy, and bytecode frameworks.
- Test runners, mocking tools, classpath scanners, and compiler plugins.
- Java agents or code instrumentation tools.
- SDK loaders, JDBC drivers, and provider discovery.

Prioritize upgrading to an official version that supports the target JDK. Fork or patch a dependency only when there is a clear maintenance plan. Do not use blanket `--add-opens` as a substitute for updating libraries.

### Step 5: Inspect the classpath and module path of the target environment

Distinguish:

- Which JARs are on the classpath?
- Which JARs are named modules?
- Are there any automatic modules on the module path?
- Are there any dynamic module layers?
- Which loader defines the shared API between host and plugin?
- How is TCCL configured in the web container or thread pool?
- Are any resources hidden due to module encapsulation?

When an application is gradually transitioning to JPMS, it is not necessary to modularize every dependency in a single step. You can temporarily run the application on the modern JDK's classpath, resolve classloader assumptions, and then migrate module by module if the architecture requires it.

### Step 6: Verify in CI and the real runtime

Run the same test suite on JDK 8 (if still a supported target) and the new JDK. In particular, include:

- Unit tests for resource lookup.
- Integration tests loading plugins from external JARs.
- Tests instantiating providers via `ServiceLoader`.
- Tests for duplicate class names between plugin and host.
- Tests for duplicate resource names across two JARs.
- Tests for module exports/opens and reflective access.
- Async/thread pool tests with TCCL.
- Tests for plugin shutdown, reload, and loader closing.
- Startup smoke tests with the exact launcher arguments.

Run tests on the actual vendor/OS runtime used in production, rather than relying only on an IDE. IDEs can alter the classpath, working directory, or class loader context.

## 15. Small test suite to reproduce and fix the issue

### 15.1. Printing the system loader type without casting

```java
public final class SystemLoaderProbe {
    public static void main(String[] args) {
        ClassLoader loader = ClassLoader.getSystemClassLoader();

        System.out.println(loader.getClass().getName());
        System.out.println(
            "URLClassLoader: "
                + (loader instanceof java.net.URLClassLoader)
        );
        System.out.println("Java: " + System.getProperty("java.version"));
    }
}
```

This snippet runs across multiple Java versions (without requiring preview features). Output may differ by vendor and runtime configuration, but it is enough to demonstrate why implementation-dependent casts are unsafe.

### 15.2. Testing resources using the ClassLoader API

```java
import java.io.InputStream;

public final class ResourceProbe {
    public static void main(String[] args) throws Exception {
        ClassLoader loader = ResourceProbe.class.getClassLoader();

        try (InputStream input =
                 loader.getResourceAsStream("sample.txt")) {

            if (input == null) {
                throw new IllegalStateException(
                    "sample.txt is not visible"
                );
            }

            System.out.println("Resource loaded");
        }
    }
}
```

Place `sample.txt` on the classpath or in a valid resource location of the module. The test will fail clearly if the resource is not visible without needing to know whether the loader is a `URLClassLoader`.

### 15.3. Testing an isolated plugin

Build a small plugin JAR, create a dedicated `URLClassLoader`, load the implementation, and invoke the shared interface. Also test cases where:

1. The plugin JAR is present with the right class name and API.
2. The plugin JAR does not exist.
3. The plugin class lacks a public constructor.
4. The plugin class does not implement the shared API.
5. Host and plugin package duplicate APIs causing a class identity conflict.
6. The plugin creates threads or listeners that are not shut down.
7. The plugin has its own resources inside its JAR.

The results of these tests show that plugin loading is under control rather than relying on system loader implementation details.

### 15.4. Version matrix

| Environment | Verification goal |
|---|---|
| JDK 8 | Baseline of legacy behavior if the product still supports it |
| JDK 11 | Detect changes caused by JPMS and built-in loaders |
| JDK 17 | Detect strong encapsulation errors and outdated dependencies |
| JDK 21 | Confirm the new LTS environment and related runtime APIs |
| JDK 25 or other target JDK | Confirm actual support of dependencies, agents, and plugins |

Not every project is required to support all of the JDKs above. Define the matrix according to the product's commitments, though if an error appears during a major upgrade step, running an intermediate release can help pinpoint when it emerged.

## 16. Troubleshooting common errors

### Error 1: `AppClassLoader cannot be cast to URLClassLoader`

**Symptom:** startup fails immediately when code or a library casts the system loader to `URLClassLoader`.

**Cause:** the current system loader does not extend `URLClassLoader`.

**Resolution:** identify the intent of the cast, switch to official resource/diagnostic APIs, or create a dedicated loader for plugins. Do not use reflection on internal implementations.

### Error 2: Resource not found after moving a JAR to the module path

**Symptom:** `getResourceAsStream` returns null even though the file is in the JAR.

**Possible causes:** wrong path, JAR outside the scope of the loader in use, or module encapsulation affecting access permissions.

**Resolution:** verify relative/absolute paths, the owning module, where the resource is packaged, and the appropriate resource API. Use `Class.getResourceAsStream` or `Module.getResourceAsStream` where appropriate.

### Error 3: `ClassNotFoundException` even though the plugin JAR exists

**Symptom:** the system loader cannot find a class loaded via the plugin loader.

**Possible causes:** the class is only visible from the child loader; the parent does not automatically search inside the child.

**Resolution:** use the right plugin loader when calling `Class.forName` or design provider discovery. Do not try to patch the JVM-wide classpath.

### Error 4: `ClassCastException` between two classes with the same name

**Symptom:** the message shows both sides have the same class name yet the cast still fails.

**Cause:** class identity differs because the defining loaders differ.

**Resolution:** print the loader of each class, avoid duplicate API packaging, and place shared interfaces in an appropriate parent.

### Error 5: `InaccessibleObjectException` in an old library

**Symptom:** a framework attempts to read a private field/method in a platform module.

**Cause:** JPMS strong encapsulation in newer JDKs.

**Resolution:** upgrade the library, switch to public APIs, or configure minimal opens permissions if truly required and accept technical debt. Do not mistakenly link this error to the runtime type of the system loader.

### Error 6: SPI provider not discovered

**Symptom:** `ServiceLoader` does not return the expected provider or throws `ServiceConfigurationError`.

**Cause:** wrong loader/layer, wrong `META-INF/services` file, provider not visible, module descriptor missing `provides`/`uses`, or invalid provider.

**Resolution:** check the SPI contract, provider metadata, service type identity, and TCCL/module layer.

### Error 7: Plugin reload increases memory usage

**Symptom:** after multiple reloads, class count and memory increase even though `URLClassLoader` was closed.

**Possible causes:** lingering references to the loader, `Class`, instances, threads, TCCL, listeners, or caches.

**Resolution:** structure the plugin lifecycle, stop tasks and clean up registries, restore TCCL; use profiling/class histograms to identify retained references.

## 17. Migration checklist

### Source code and dependencies

- [ ] No longer casting the default system loader or platform loader to `URLClassLoader`.
- [ ] Searched for code using reflection on `addURL` or internal loader packages.
- [ ] Identified the actual requirement: resource lookup, classpath logging, provider discovery, or dynamic JAR loading.
- [ ] Updated frameworks/agents/plugins containing JDK 8 loader assumptions.
- [ ] No reliance on legacy extension/endorsed directories.

### Resources and modules

- [ ] Resource lookup uses official APIs suited to classpath/modules.
- [ ] Verified path differences between `Class.getResource` and `ClassLoader.getResource`.
- [ ] Identified relevant named modules, unnamed modules, and module layers.
- [ ] Module `exports`/`opens` accurately reflect API and reflection requirements.
- [ ] Not treating `java.class.path` as a complete list of the module path and custom loaders.

### Plugins and SPI

- [ ] Plugin loaders are application-created and closed according to an explicit lifecycle.
- [ ] Shared APIs between host and plugin are not defined twice in different loaders.
- [ ] `ServiceLoader` uses the right loader or layer.
- [ ] TCCL is properly set/restored when frameworks require it.
- [ ] No references to plugin loaders retained via threads, listeners, or caches after unloading.

### Verification

- [ ] Startup tests on the target JDK have been run.
- [ ] Resource lookup and classpath/module path tests have been run.
- [ ] Dynamic plugin loading and SPI tests have been run.
- [ ] Class identity error, duplicate dependency, and missing provider tests have been run.
- [ ] Dependencies and agents have been confirmed to support the target JDK.
- [ ] Rollback plan and loader/module diagnostic information have been prepared.

## Conclusion

Assuming `ClassLoader.getSystemClassLoader()` is always a `URLClassLoader` is a classic example of depending on a JDK 8 implementation rather than the public API. JPMS and the reorganization of built-in class loaders starting in JDK 9 invalidated that assumption; the cast can fail even when the classpath and JARs are completely valid.

A proper migration is not about trying to turn the system loader into a `URLClassLoader`, but about **separating intent from implementation**: using resource APIs to read files, using appropriate diagnostics to inspect the classpath/modules, using `ServiceLoader` to discover providers, and creating a dedicated `URLClassLoader` or `ModuleLayer` when the application actually needs dynamic plugin loading. When combined with checks on class identity, TCCL, module visibility, and plugin lifecycles, a Java application can run stably on modern JDKs without depending on legacy class-loading details.
