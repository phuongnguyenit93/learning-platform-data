# Migrating Away from lib/ext, java.ext.dirs, and Assuming the Application Loader Is a URLClassLoader

When upgrading a Java 8 system with dynamic library or plugin loading to Java 17+, three legacy assumptions can break the application **immediately at startup** or only on the plugin execution path:

1. "Copying a JAR into `$JAVA_HOME/lib/ext` makes the JVM see it automatically." **No longer true since JDK 9**: the extension mechanism was removed.
2. "We can point `-Djava.ext.dirs=...` to a custom extension directory." **No longer a valid configuration**: modern JDK launchers and compilers reject the legacy flag.
3. "`ClassLoader.getSystemClassLoader()` returns a `URLClassLoader`; cast it and call `getURLs()` or try calling `addURL`." **Not a Java SE contract**; the default application class loader in JDK 9+ is no longer a `URLClassLoader`.

These three errors directly affect **testing and deploying runtime extensibility architectures**: a JAR may be packaged properly yet sit on no valid search path, or loader-casting code throws `ClassCastException` before even opening a plugin.

The safe migration path is to **choose the deployment mechanism explicitly**: classpath for legacy libraries; module path and `ModuleLayer` for named modules; or a `URLClassLoader` **created, owned, and closed by the application** for classpath plugins. Business logic should program against the `ClassLoader`/SPI contract rather than internal system loader implementations.

This Knowledge article explains the JDK changes, builds a configuration replacement table, provides a standalone Java 17 demo, and establishes a testing checklist for migration and plugin deployment.

## 1. Before JDK 9: What Did the Extension Mechanism Actually Do?

In Java 8 and earlier, the JVM had an **installed extensions mechanism**: JARs placed in extension directories were discovered by the extension class loader without listing every JAR on the application classpath. Legacy deployment habits looked like:

```text
<JAVA_HOME>/
    jre/lib/ext/
        vendor-codec.jar
        shared-plugin.jar

or:
    java -Djava.ext.dirs=/opt/company/extensions -cp app.jar com.example.Main
```

This is a **historical diagram**, not commands for Java 17. Directory locations depended on legacy JDK/JRE distribution layouts. `java.ext.dirs` specified a list of extension directories instead of per-application dependency configurations.

This mechanism felt convenient yet carried real costs:

- Dependencies lived in the **shared Java environment**, hard to reproduce across tests, containers, or other servers.
- An unexpected artifact in an extension directory could affect **multiple applications** sharing that runtime.
- Version conflicts were hard to trace without tracking individual JARs and origins.
- Plugins were "installed" by mutating the JDK directory, complicating updates, testing, and rollbacks.
- Loader resolution depended on host machine setup rather than explicit application manifests/deployment descriptors.

When moving to a modular JDK runtime, this is no longer a valid extension point. **Do not mechanically move JARs from `lib/ext` to another `lib` folder assuming the JVM will scan it automatically.** Java does not scan arbitrary directories by default.

## 2. Changes Since JDK 9: Mechanism Removed, Hierarchy Renamed

The Oracle JDK Migration Guide distinguishes two related—yet **not identical**—changes:

### 2.1. Extension Directory Scanning Was Removed

Since JDK 9, the extension mechanism is no longer supported. To use a JAR that previously lived in `lib/ext`, you must **place it on the classpath/module path or load it via an application-defined loader**.

Oracle's migration guide notes that the `java` launcher and `javac` compiler exit on startup if legacy extension configurations such as `java.ext.dirs` or `lib/ext` appear in checked layouts; exact messages vary by JDK version and distribution. On tested Java 17, a command like:

```bash
java -Djava.ext.dirs=legacy -version
```

**Is not a new configuration option**: the JVM rejects that setting. Running it in a test runtime serves only to **detect leftover legacy flags**, not as a step for running the demo program later.

Never work around startup errors by creating a new `lib/ext` folder inside the JDK. The right fix is removing the legacy extension configuration and **declaring needed JARs in the application's deployment**.

### 2.2. The Extension Class Loader Became the Platform Class Loader

The conceptual hierarchy in JDK 9+ is commonly drawn as:

```text
Bootstrap class loader  (typically represented as null parent)
        ^
        |
Platform class loader   ClassLoader.getPlatformClassLoader()
        ^
        |
Application/system class loader   ClassLoader.getSystemClassLoader()
        ^
        |
Application-created plugin loader (if any)
```

This illustrates the default runtime model, **not a guarantee that every custom class loader follows this exact tree**. JDK 9+ provides `ClassLoader.getPlatformClassLoader()`; it takes the conceptual place of the old extension loader in the hierarchy without **continuing to auto-scan `lib/ext`**.

The platform loader provides access to required platform classes per the JDK contract. **Do not equate "visible through the platform loader" with "defined by the platform loader"**: some Java SE classes are actually defined by the bootstrap loader. Code should never rely on which exact loader defined a particular platform class.

When choosing a parent for a custom plugin loader where the plugin uses an **application-owned API**, normally pass the **host API's loader**, not automatically the platform loader or `null`:

```java
ClassLoader parent = PluginApi.class.getClassLoader();
URLClassLoader pluginLoader =
        new URLClassLoader(pluginUrls, parent);
```

This is a **snippet**: `PluginApi`/`pluginUrls` must be defined along with `URLClassLoader` and `URL` imports. When plugin and host must share `PluginApi`, this parent prevents the plugin from loading a duplicate copy of the API. Passing `null` is not a safe plugin isolation trick; it can hide the host API and certain platform modules.

## 3. Application/System Loader Is No Longer a URLClassLoader by Default

A common Java 8 anti-pattern:

```java
// Legacy non-portable pattern: can throw ClassCastException on Java 17.
URLClassLoader app =
        (URLClassLoader) ClassLoader.getSystemClassLoader();

for (URL url : app.getURLs()) {
    System.out.println(url);
}
```

The snippet above is an **anti-pattern illustration**, not code to run in production. `ClassLoader.getSystemClassLoader()` has declared return type **`ClassLoader`**, not `URLClassLoader`. In JDK 9+, the default application loader is implemented by an internal JDK class that does not extend `URLClassLoader`.

Never infer from a cast succeeding on an older JVM that newer JVMs must use the same implementation. Even in runtimes allowing a custom system loader, its concrete class can differ; portable code **avoids casting when `ClassLoader` methods suffice**.

### APIs to Call Directly on ClassLoader

```java
ClassLoader loader = ClassLoader.getSystemClassLoader();

Class<?> c = loader.loadClass("com.example.api.Service");
URL resource = loader.getResource("config/defaults.properties");
java.util.Enumeration<URL> all =
        loader.getResources("META-INF/services/com.example.api.Service");
```

This is a **snippet** requiring `URL`, `IOException`, and real classes/resources. `loadClass` can throw `ClassNotFoundException`; `getResource` can return `null`; `getResources` returns an enumeration and can throw `IOException`.

**These methods are the standard `ClassLoader` contract**, requiring no knowledge of whether the loader holds a URL list. To inspect **which artifact supplied a class/resource**, use resource APIs, `Class.getProtectionDomain().getCodeSource()` when available, module/layer metadata, and JVM logs as appropriate. Never assume every class has a `jar:file:...` code source URL.

### Do Not Use Reflection to Mutate Internal Loaders

Some legacy code reflects into internal loader fields or looks up `addURL` to append JARs to the system classpath at runtime. This is not a standard API for mutating the system loader and can be blocked by JPMS **strong encapsulation**. Never treat `--add-opens` as a permanent fix for loader design flaws: it only opens reflection to a named package and does not turn JDK internals into stable public APIs.

**Need to add JARs dynamically?** Create/swap an **application-owned loader**, or use `ModuleLayer` if plugins are deployed as named modules. **Need a classpath fixed only at startup?** Declare it via the launcher/build tool instead of mutating the system loader at runtime.

## 4. Migration Mapping: Legacy Deployment → Modern Model

| Legacy Assumption / Deployment | Replacement | When Appropriate |
| --- | --- | --- |
| Copy `foo.jar` into `$JAVA_HOME/lib/ext` | Put `foo.jar` on application classpath or module path | Library needed from startup |
| `-Djava.ext.dirs=/opt/ext` | `-cp "/opt/ext/*:app.jar"` on Unix or build/launcher-generated classpath | Multiple independent JARs in one directory |
| Drop files into `lib/ext` while app runs | Registry + custom loader per plugin generation | Plugins installed/removed/replaced dynamically |
| `(URLClassLoader) getSystemClassLoader()` | Use `ClassLoader` API; if URLs are needed, instantiate your own `URLClassLoader` and keep its reference | Portable lookup, or application-owned loader |
| Reflective `addURL` on system loader | Declare startup classpath, or create a new loader | Avoid depending on JDK internals |
| `sun.misc.Launcher$ExtClassLoader` / `AppClassLoader` | `getPlatformClassLoader()` and `getSystemClassLoader()` via public API | Accessing platform/application loaders |
| `rt.jar` or `tools.jar` on classpath | Java SE module APIs, `--module-path`/`--add-modules` as needed | JDK 9+ modular runtime |
| Scanning JARs by classpath order to pick first | Pin artifacts/versions via manifest and registry | Prevent class/resource collisions, repeatable deploys |

**Path syntax note:** on macOS/Linux the classpath delimiter is `:`; on Windows it is `;`. Never pass literal quotes mismatched with shell syntax. For example:

```bash
# macOS/Linux: classpath at startup time.
java -cp "app.jar:lib/*" com.example.Main
```

```powershell
# Windows PowerShell: classpath at startup time.
java -cp "app.jar;lib/*" com.example.Main
```

These are **illustrative commands**; `app.jar`, `lib/*`, and `com.example.Main` must exist. The `lib/*` wildcard in a classpath is expanded by the Java launcher to matching JARs **in that exact directory**, without recursing into subdirectories. The expansion order of JARs is not a version management contract, so never rely on wildcards to "pick the right plugin" when competing versions exist.

Putting a plugin onto the application classpath also exposes it to the **shared application environment**. If you need to install, remove, or roll back a plugin version independently within the same process, use a dedicated loader and explicit lifecycle rather than changing the JVM-wide classpath.

## 5. Choosing Classpath, Dedicated URLClassLoader, or ModuleLayer?

This is a decision about **scope and lifecycle**, not just a single command-line option.

### A. Explicit Classpath

Suitable when the application stays in the **unnamed module** and dependencies are fixed per deployment:

```text
build produces:
  app.jar
  lib/codec.jar
  lib/common.jar

startup:
  java -cp "app.jar:lib/*" com.example.Main   (Unix)
  java -cp "app.jar;lib/*" com.example.Main   (Windows)
```

Pros: simple setup, compatible with many Java 8 JARs, minimal code changes. Cons: JARs enter the **same application loader** with no per-plugin isolation; copying a new JAR does not trigger hot replacement.

### B. Application-Owned URLClassLoader

Suitable for **classpath-based plugins** managed by a registry. You retain the reference to the `URLClassLoader` you constructed:

```java
try (URLClassLoader pluginLoader = new URLClassLoader(
        new URL[] { pluginJar.toUri().toURL() },
        PluginApi.class.getClassLoader())) {
    Class<?> type = pluginLoader.loadClass("com.acme.extension.Handler");
    // Discover, instantiate, and use plugin within this scope.
}
```

This is a **snippet** requiring `pluginJar`, `PluginApi`, and imports. Key points:

- You **know** this loader is a `URLClassLoader` because **you created it**, not by casting the system loader.
- The parent should provide the exact host/API classes needing shared identity; never pass `null` carelessly.
- Standard `URLClassLoader` is **parent-first**: matching classes in the parent win; verify namespaces and compatibility.
- Close the loader when its generation retires and no requests or resource streams remain open. `close()` does not force immediate class/object unloading.
- In production, avoid wrapping the loader in a try-with-resources around discovery alone if the plugin instance outlives that scope; the **plugin generation** owner must decide when to close.

To upgrade a running plugin, build a **new** loader for the new generation, validate it, atomically publish the snapshot, and drain/close the old generation—never mutate an active loader in place.

### C. Module Path + ModuleLayer

Suitable when you want named modules, `module-info.java` contracts, `requires`/`exports`/`uses`/`provides`, and layer-scoped service discovery.

At startup, the launcher can use:

```bash
java --module-path mods --module com.example.app/com.example.app.Main
```

This is an **illustrative template**; there is no `com.example.app` module in section 6's demo. `--module-path` makes modules *observable*, which **does not mean all modules are automatically resolved**. Add root modules/`--add-modules` or service binding as needed.

For dynamic runtime plugins, the conceptual pipeline is:

```text
Plugin artifact / modules directory
       |
       v
ModuleFinder.of(path)                     (observable modules)
       |
       v
Configuration.resolve(...) / resolveAndBind(...)
       |
       v
ModuleLayer.defineModulesWithOneLoader(...) or WithManyLoaders
       |
       v
ModuleLayer.findLoader(moduleName)
       |
       v
ServiceLoader.load(layer, Service.class)
       |
       v
Registry generation + lifecycle
```

`ModuleLayer` does not turn the system loader into a `URLClassLoader`; it provides **module resolution and class-loader mapping**. With `ServiceLoader` in a layer, the service class needs matching identity along with valid service-use/provider declarations. `resolveAndBind` can add providers via `uses`/`provides` that `resolve` omits if the provider is not a root or dependency.

**Never mix the two models haphazardly:** placing a legacy JAR on the classpath while expecting a dynamic `ModuleLayer` to see it, or putting a module on the module path while calling `Class.forName` with the wrong class loader and blaming a missing JAR. Be explicit at every step whether a plugin belongs to **unnamed/classpath scope** or **named/module scope**.

## 6. Complete Java 17 Example: Loading Plugins Without Casting the Application Loader

To mirror reality, this demo builds **host and plugin into two separate output directories**:

- Host `LoaderMigrationDemo` runs from `host-out` and **does not** put the plugin on the host's `-cp`.
- Plugin class `demo.plugin.Greeter` is compiled separately into `plugins`.
- Resource file `META-INF/plugin/version.txt` also lives in `plugins`.
- The host creates an **explicit `URLClassLoader`** pointing at `plugins`, with the application loader as parent, and loads classes/resources through it.

The demo uses JDK 17 and standard APIs only—no Maven, Gradle, or external libraries.

### 6.1. Project Structure

```text
loader-migration-demo/
├── LoaderMigrationDemo.java
├── plugin-src/
│   └── demo/plugin/Greeter.java
├── host-out/                   (javac output for host)
└── plugins/
    ├── demo/plugin/Greeter.class   (javac output for plugin)
    └── META-INF/plugin/version.txt (resource)
```

`host-out` and `plugins` are created during compilation; the resource file is created in the run commands. No `$JAVA_HOME/lib/ext` or `java.ext.dirs` is used.

### 6.2. Plugin Class

**`plugin-src/demo/plugin/Greeter.java`**

```java
package demo.plugin;

public final class Greeter {
    public static String message() {
        return "from-plugin";
    }
}
```

This plugin class has no dependency on a host API so the example focuses on a loader finding classes absent from the host classpath. In real SPI systems, plugins typically implement a host-owned interface; the parent loader must then expose that exact interface.

### 6.3. Host Loader

**`LoaderMigrationDemo.java`**

```java
import java.io.InputStream;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;

public final class LoaderMigrationDemo {
    public static void main(String[] args) throws Exception {
        ClassLoader app = ClassLoader.getSystemClassLoader();
        System.out.println("appIsURLClassLoader=" + (app instanceof URLClassLoader));
        System.out.println("appParentIsPlatform="
                + (app.getParent() == ClassLoader.getPlatformClassLoader()));

        Path plugins = Path.of(args[0]);
        URL[] urls = {plugins.toUri().toURL()};
        try (URLClassLoader plugin = new URLClassLoader(urls, app)) {
            Class<?> type = Class.forName("demo.plugin.Greeter", true, plugin);
            Object value = type.getMethod("message").invoke(null);

            System.out.println("explicitUrls=" + plugin.getURLs().length);
            System.out.println("pluginDefinedClass=" + (type.getClassLoader() == plugin));
            System.out.println("message=" + value);

            try (InputStream in =
                         plugin.getResourceAsStream("META-INF/plugin/version.txt")) {
                if (in == null) throw new IllegalStateException("missing resource");
                System.out.println("resource=" +
                        new String(in.readAllBytes(), StandardCharsets.UTF_8).trim());
            }
        }
    }
}
```

**Key takeaways:**

1. `app` is typed as generic `ClassLoader`; `instanceof URLClassLoader` **only observes**, never casts.
2. `ClassLoader.getPlatformClassLoader()` is the Java 9+ public API replacing internal access to `sun.misc.Launcher$ExtClassLoader`.
3. `new URLClassLoader(urls, app)` is **host-owned**; calling `getURLs()` is valid on **this object**.
4. `Class.forName("demo.plugin.Greeter", true, plugin)` loads and initializes the class through the explicit loader. Because the plugin is absent from `host-out`, this loader genuinely defines it.
5. `type.getClassLoader() == plugin` proves `Greeter` was defined by the plugin loader in this demo rather than an identically named class in the parent.
6. `getResourceAsStream("META-INF/plugin/version.txt")` reads the resource using a logical path from the plugin root without `File.separator` or reaching into build source folders.
7. Both the stream and `URLClassLoader` are closed in `try-with-resources`. In production, while a plugin still serves requests, **do not close the loader at the end of a loading method**; hold it in the generation owner until retirement/draining.

### 6.4. Compile and Run on Windows PowerShell

Inside `loader-migration-demo` with both `.java` files placed as in section 6.1:

```powershell
New-Item -ItemType Directory -Force host-out, plugins, plugins/META-INF/plugin | Out-Null
"v2" | Set-Content -Encoding Ascii plugins/META-INF/plugin/version.txt

javac --release 17 -d host-out LoaderMigrationDemo.java
javac --release 17 -d plugins plugin-src/demo/plugin/Greeter.java

java -cp host-out LoaderMigrationDemo plugins
```

**Why use `-Encoding Ascii` for the demo resource file?** Because `v2` is pure ASCII, this keeps it simple and avoids a byte-order mark added by certain PowerShell versions under older UTF-8 flags. For real Unicode resources, write UTF-8 without BOM per your file API/contract.

### 6.5. Compile and Run on macOS/Linux

```bash
mkdir -p host-out plugins/META-INF/plugin
printf 'v2\n' > plugins/META-INF/plugin/version.txt

javac --release 17 -d host-out LoaderMigrationDemo.java
javac --release 17 -d plugins plugin-src/demo/plugin/Greeter.java

java -cp host-out LoaderMigrationDemo plugins
```

### 6.6. Verified Output on JDK 17

```text
appIsURLClassLoader=false
appParentIsPlatform=true
explicitUrls=1
pluginDefinedClass=true
message=from-plugin
resource=v2
```

This is stdout **compiled with `javac --release 17` and executed on JDK 17**. The first two lines describe the **tested default runtime**, not a guarantee for JVMs configured with custom `java.system.class.loader`. The remaining four lines prove the new loader holds one root URL, defines the plugin class, invokes its method, and reads the resource from the plugin directory.

**Migration takeaway:** you neither need nor should cast the application loader to `URLClassLoader` to inspect or load plugins. The app keeps using the standard class loader, while plugins get an explicit loader with clear ownership and source directory.

### 6.7. Testing `java.ext.dirs` Separately

To prove the legacy flag is rejected, run standalone in a test environment:

```bash
java -Djava.ext.dirs=legacy -version
```

On tested JDK 17, the JVM **exits with an error code** instead of running `java -version` normally. Never put this flag in production startup scripts. Exact stderr wording varies by build/JDK version; Oracle docs describe the "extension mechanism no longer supported" error.

## 7. When Plugins Actually Use ServiceLoader

Section 6's demo used reflection to avoid requiring a host SPI. In a real system with an API/plugin provider:

```java
// Snippet; PluginApi is the interface defined by the host/shared parent loader.
try (URLClassLoader loader =
         new URLClassLoader(pluginUrls, PluginApi.class.getClassLoader())) {
    ServiceLoader<PluginApi> services =
            ServiceLoader.load(PluginApi.class, loader);

    for (PluginApi plugin : services) {
        plugin.validate();
        // Do not publish to traffic until readiness passes.
    }
}
```

This is an **architectural snippet, not standalone runnable code**; `pluginUrls`, `PluginApi`, and imports for `URLClassLoader` and `ServiceLoader` must be supplied by your project. In production code, the loader's lifetime must **span the provider's serving lifetime** (e.g., owned by a generation), rather than ending inside a local discovery block if providers are called later.

For classpath SPI, place the metadata file properly:

```text
META-INF/services/com.example.api.PluginApi

UTF-8 content (one implementation name per line):
com.example.plugins.CodecPlugin
```

**Distinction:** `com.example.api.PluginApi` and `com.example.plugins.CodecPlugin` are **structural placeholders**; replace them with real fully qualified names. The plugin class must implement the service API with **the exact same class identity** used by the host; a duplicate `PluginApi.class` in a child loader causes `ServiceConfigurationError` or `ClassCastException`.

When a plugin loader is parent-first, if the parent already contains a same-named class or resource, it will pick **the parent's copy**. Never "fix" this by casting the system loader. Design distinct plugin namespaces, avoid dependency collisions, define the loader hierarchy, and test which exact version gets picked.

### TCCL and ServiceLoader

`ServiceLoader.load(PluginApi.class)` (the one-argument overload) uses the **thread context class loader (TCCL)**, which may not be the intended plugin loader. Inside a host or plugin registry, once you know the generation's loader, prefer:

```java
ServiceLoader<PluginApi> providers =
        ServiceLoader.load(PluginApi.class, pluginLoader);
```

This snippet requires an explicit `pluginLoader` and valid service type. Do not blindly overwrite TCCL across thread pools as a catch-all fix. When a framework mandates TCCL, set and restore it in `finally`, and test under concurrency.

**For named modules**, use `provides ... with ...`/`uses` and `ServiceLoader.load(layer, serviceClass)` per JPMS. The same plugin can be distributed as a classpath JAR or a modular JAR; discovery, layers, and visibility must follow the chosen deployment model.

## 8. A Practical Migration Plan from Java 8 to Java 17

### Step 1 — Inventory Build and Runtime Configurations

Search **solely within projects and deployment configs you own** for:

```text
java.ext.dirs
lib/ext
jre/lib/ext
getSystemClassLoader()
(URLClassLoader)
getURLs()
addURL
sun.misc.Launcher
rt.jar
tools.jar
java.endorsed.dirs
```

Look beyond Java source code. Inspect:

- startup scripts, `JAVA_TOOL_OPTIONS`/`_JAVA_OPTIONS`, wrapper/service units;
- Dockerfiles/container images, JDK image customizations, app server system properties;
- Maven/Gradle dependencies, test runtime classpaths, shaded/fat JAR configs;
- module path flags, `--add-modules`, and obsolete `--add-opens`;
- plugin catalogs/manifests and how the app loads versioned JARs.

**Keep read/edit scope properly bounded:** this is a checklist for your deployment team, not an instruction to modify machine-wide installations or delete Java files outside managed deployments.

### Step 2 — Classify Every JAR That Used to Live in Extension Directories

Each JAR needs an explicit owner:

| Category | Migration Target | Verification |
| --- | --- | --- |
| Library needed from startup | Move to app runtime dependency/classpath | Classpath/JAR exists, exact version |
| Host-defined SPI API | Host/shared loader owns API | No duplicate API loaded from plugins |
| Dynamically installed/upgraded plugin | Plugin registry creates loader or layer per generation | Isolation, validation, drain, cleanup |
| Named module with `module-info.class` | Module path with resolved roots/service binding | `requires`/`exports`/`uses`/`provides` |
| Automatic module | Module path only if genuinely needed; check automatic name/deps | All JPMS rules and actual conflicts |
| Code touching JDK internals | Migrate to public APIs or new loader design | Zero reliance on `sun.misc.*`/internal casts |

There is no rule that "every legacy JAR must become a named module". **Classpath remains a valid migration target** for many applications. JPMS helps when explicit boundaries/graphs are desired, yet moving JARs onto the module path adds constraints around packages, reflection, service discovery, and module naming.

### Step 3 — Remove Legacy Properties and Directories from Deployments

- Remove the `-Djava.ext.dirs` **configuration flag** from scripts/service wrappers instead of "moving its value" into another hidden property.
- Never copy `lib/ext` into a Java 17 image. Package dependencies alongside the app or into a **host-managed** plugin directory.
- Avoid mutating system-wide JDK installations serving other apps. Build a new versioned image/container and verify with a clean-room run.
- If `java.endorsed.dirs` or `lib/endorsed` appears, that is **another removed legacy mechanism**, not a replacement for `lib/ext`.

### Step 4 — Refactor Code Depending on Loader Implementations

**Before:**

```java
URLClassLoader system =
        (URLClassLoader) ClassLoader.getSystemClassLoader();
URL[] urls = system.getURLs();
```

**After, when only loading resources/classes:**

```java
ClassLoader system = ClassLoader.getSystemClassLoader();
URL config = system.getResource("config/defaults.properties");
Class<?> api = system.loadClass("com.example.api.Service");
```

**After, when you genuinely want a plugin's URL list:**

```java
URLClassLoader plugin =
        new URLClassLoader(pluginUrls, ClassLoader.getSystemClassLoader());
URL[] urls = plugin.getURLs();
```

These are **snippets** requiring imports and real classes/resources/`pluginUrls`. You do not have to "preserve the `URLClassLoader` type" if your goal is only inspecting the application runtime's classpath. For classpath diagnostics, inspect launcher arguments and runtime module metadata instead of reconstructing classpaths from loader internals.

### Step 5 — Verify Contracts When Plugins Run

A smoke test suite should confirm:

1. Host boots **without `java.ext.dirs`** and without legacy extension folders.
2. Required providers/libraries load from the right **classpath/module path/explicit loader** scope.
3. Application loader is never cast to `URLClassLoader`.
4. Plugin classes have the expected defining loader and version origin.
5. SPI `ServiceLoader` finds the expected provider count (zero, one, or many per policy).
6. Named modules have valid graphs; reflective access/`exports`/`opens` are tested if used.
7. Resources like `META-INF/services`, JSON/templates/configs are packaged and resolved by the right loader.
8. Upgrading V1→V2 does not break old in-flight requests; V1's loader is cleaned up at the right time.
9. Tests pass across changed working directories, container base images, and startup classpaths.
10. Application has zero dependency on `rt.jar` paths or JDK internal URL assumptions.

## 9. Diagnosing Failures After Migration

### JVM Rejects Startup Immediately

**Symptom:** message "extensions mechanism no longer supported", or mentioning `java.ext.dirs` / `lib/ext`.

**Diagnosis:** caught **before application `main` runs**, so editing `ClassLoader` code inside `main` cannot fix it.

**Action:** inspect startup flags/environment, strip legacy properties/extension directories, place dependencies explicitly on classpath/module path, and retest in a clean image. If the launcher picks up flags from `JAVA_TOOL_OPTIONS` or `_JAVA_OPTIONS`, fix that environment source rather than only the `java` invocation script.

### ClassCastException Initializing Plugin Manager

**Sample symptom:**

```text
java.lang.ClassCastException:
  ...AppClassLoader cannot be cast to java.net.URLClassLoader
```

This is an **illustrative error pattern**; exact class names depend on the JDK. Locate `(URLClassLoader) ClassLoader.getSystemClassLoader()`, switch to the `ClassLoader` API or instantiate your own `URLClassLoader`. Do not resort to reflection or JDK internals.

### ClassNotFoundException or NoClassDefFoundError

**`ClassNotFoundException`** typically stems from explicit name-based lookups on a loader that cannot see the class. **`NoClassDefFoundError`** happens when runtime lacks a bytecode-referenced dependency or a prior static initialization failed. These surface **after the app starts**, unlike launcher extension-mechanism rejections.

Procedure:

1. Read the **target class name**, full root `cause`, and loader identity.
2. Verify the `.class` file exists in the right deployed JAR/directory.
3. Confirm that JAR belongs to the **classpath/module path/custom loader** used by the caller.
4. When multiple versions exist, identify **which artifact actually supplied the loaded class**.
5. If the error says `Could not initialize class`, inspect the initial initializer failure instead of assuming a missing file.

### ServiceLoader Finds No Providers

- On classpath: verify `META-INF/services/<service-interface>` exists, has valid contents, the provider class loads under the right loader, and implements the exact shared API.
- On named modules: check `uses`, `provides`, module resolution/definition in the layer, service class identity, and `ServiceLoader.load(layer, serviceClass)`.
- Do not rush to blame `URLClassLoader`. SPI metadata may be intact while a parent-first loader picks another version of a resource or class.

### JDK Resources No Longer Live in rt.jar

`ClassLoader.getSystemResource("java/lang/Class.class")` since JDK 9 can return a URL like:

```text
jrt:/java.base/java/lang/Class.class
```

This is an **example from Oracle's migration guide**, not demo stdout. It represents a resource inside a modular runtime image; never assume every resource URL converts to `jar:file:...` or a filesystem `Path` to a JAR file. When you only need resource bytes, use `getResourceAsStream` or appropriate module/runtime image APIs.

## 10. Security, Isolation, and New Plugin Loader Lifecycle

Compiling and running after migration does not guarantee operational safety. Moving from extension directories to custom loaders requires clear ownership and policy:

**Never treat a class loader as a security boundary.** A Java plugin running inside the same JVM can essentially invoke APIs with the host process's privileges unless proper OS/architecture isolation is enforced. Untrusted plugins belong in separate processes/containers with restricted filesystem, network, and resource permissions.

**Manage JARs and releases.** Never accept arbitrary plugin paths from unvalidated input; load only approved artifacts, verify hashes/signatures/versions, and enforce allowlists. Watch out for duplicate classes/resources or plugin-bundled dependencies already present in the parent.

**Manage lifecycle.** `URLClassLoader.close()` releases loader-owned resources such as JAR file handles and blocks new class loading per contract, yet **does not immediately reclaim already-defined classes**. Any live background thread, callback, static cache, `ThreadLocal`, TCCL, or `Class<?>` reference keeps the old loader from being garbage-collected.

**Guarantee shared APIs.** Host and plugins must share the exact same service interface/class identity; place the API in the parent/shared layer. If a plugin ships its own copy of the API with the same fully qualified name, expect `ClassCastException` or `ServiceConfigurationError`.

**Use generation snapshots when upgrading plugins.** Build the V2 loader/layer, run initialization/provider/health checks, atomically publish the active reference, keep V1 alive until in-flight V1 requests finish; then retire, close, and clear V1 references. Never overwrite a JAR currently open in a live loader expecting class definitions to swap.

**Bound resources.** Multiple concurrent class loaders retain JAR handles, threads, heap/metaspace, and connection pools. Track metrics for generation counts, in-flight requests, and cleanup failures; enforce drain timeouts or process isolation for uncooperative plugins.

## 11. Test Matrix for CI and Deployment

| Test Case | What Must Be Proven |
| --- | --- |
| Java 17 clean startup | Zero reliance on `lib/ext` or `java.ext.dirs` |
| Startup with `-Djava.ext.dirs` in test env | Legacy config is detected as rejected by runtime and blocked from deploy |
| Default system loader | Code never casts to `URLClassLoader` |
| Explicit plugin loader | Plugin classes and resources load from the right folder/JAR |
| Plugin absent from host classpath | Host still loads via its dedicated loader without accidentally hitting parent |
| Shared host API | Provider implements the exact shared class identity without API duplication |
| Duplicate class/resource across parent and child | Parent-first/namespace/version policy is verified |
| Wrong plugin directory | Clear diagnostic error without silently falling back to another provider |
| Classpath wildcard | JARs packaged properly; never relying on wildcard order for version selection |
| Named module | `ModuleFinder`, roots, `requires`, `uses`/`provides`, and layer work properly |
| Plugin update | New generation validated before cutover; old generation drains then closes |
| Missing dependency / incompatible Java version | Fails fast with root cause instead of blaming extension mechanism |
| TCCL and thread pools | Discovery consistent across threads; TCCL restored if mutated |
| Resource loading | Never assumes `jrt:` URLs are `jar:file:` or OS files |
| Repeated unload/reload | No retained listeners/threads/contexts/caches leaking class loaders |

**Do not test only inside an IDE.** IDEs often assemble classpaths where JARs that used to live in extension directories happen to appear. Test using **real packaged artifacts** with production launcher flags, Java runtime images, and directory layouts. At minimum, include an integration test separating plugin from host classpath like section 6's demo.

### Anti-Patterns to Stop Immediately

- **Writing JARs into `$JAVA_HOME/lib/ext`** in Dockerfiles or install scripts.
- **Using `java.ext.dirs`** as a plugin configuration knob.
- **Casting the system loader** to call `getURLs` for reading/editing the classpath.
- **Reflecting into JDK internal classes** to call `addURL`.
- **Turning a new `URLClassLoader` into an immortal singleton** without tracking plugin generations.
- **Duplicating plugin APIs in both parent and child** or assuming `ServiceLoader` reconciles class identity.
- **Treating the module path as a renamed classpath**, ignoring module resolution and encapsulation.
- **Loading plugins from untrusted folders** while treating a separate loader as a sandbox.
- **Closing the loader immediately after scanning SPI** while still calling providers on subsequent requests.

## 12. Pre-Release Migration Checklist

**Build and configuration:**

- [ ] Cataloged every `lib/ext`, `jre/lib/ext`, and `java.ext.dirs` across builds, startup scripts, and images.
- [ ] Every legacy JAR has an explicit owner: classpath, module path, or explicit plugin registry.
- [ ] No mutating JDK runtime installations by copying arbitrary JARs; app artifacts carry required manifests.
- [ ] Startup uses OS-appropriate classpath delimiters and never relies on wildcard order for version selection.
- [ ] Zero code expects runtime `rt.jar`/`tools.jar` URLs.

**Source and class loaders:**

- [ ] No casting `ClassLoader.getSystemClassLoader()` to `URLClassLoader`.
- [ ] Uses public `ClassLoader` APIs when simply loading classes/resources.
- [ ] Calls `getURLs()` only on a `URLClassLoader` you constructed or an object verified by contract.
- [ ] Parent loader preserves host/service API class identity; no habitual `null` parent.
- [ ] `ServiceLoader` mechanism matches plugin kind: classpath SPI or named modules.
- [ ] Dynamic plugins use fresh loaders/layers, versioned generations, and post-drain lifecycle close.

**Testing and operations:**

- [ ] Tests execute on a real Java 17 runtime, not merely compiling with JDK 17.
- [ ] Integration test isolates `host-out` and `plugins` like section 6's demo.
- [ ] Verified no extension properties rejected by the launcher exist in deployment environments.
- [ ] Verified exact loaded class origins, resources, and module/loader identities.
- [ ] Alerts configured for missing providers, duplicate classes, or version collisions.
- [ ] Canary/rollback plan, artifact hashes, and class-loader lifetime metrics in place.
- [ ] Never uses a Java class loader to run untrusted code without process-level isolation.

### Official Documentation

- [Oracle JDK 17 Migration Guide: Migrating From JDK 8 to Later JDK Releases](https://docs.oracle.com/en/java/javase/17/migrate/migrating-jdk-8-later-jdk-releases.html)
- [JEP 220 — Modular Run-Time Images](https://openjdk.org/jeps/220)
- [JEP 261 — Module System](https://openjdk.org/jeps/261)
- [Java 17 `ClassLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html)
- [Java 17 `URLClassLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html)
- [Java 17 `ServiceLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html)
- [Java 17 `ModuleLayer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html)

**Conclusion:** migrating away from `lib/ext` and `java.ext.dirs` is more than renaming a directory. It means **bringing all dependency and plugin discovery into reproducible, testable application configuration**, dropping reliance on system loader implementation types, and choosing classpath, explicit `URLClassLoader`, or JPMS `ModuleLayer` according to the plugin's actual lifecycle. You can still use `URLClassLoader` on Java 17—**provided it is a loader you explicitly create and manage**, not a cast of the default system loader.
