# Diagnosing ClassNotFoundException and NoClassDefFoundError in the Java Module System

When a Java application cannot use a class at runtime, two error names that frequently appear are **ClassNotFoundException** and **NoClassDefFoundError**. They may both relate to missing bytecode or a class loader failing to find a class, yet they do not have the same meaning, do not arise at the same stage, and should not be treated with a blanket fix like "put every JAR on the classpath."

With the Java Platform Module System (JPMS), locating and loading classes is also affected by the module path, module resolution, module layers, the class loader associated with a module, and the separation between **readability** and **exports/opens**. Having a JAR present on disk does not guarantee its module participates in the runtime configuration. Conversely, a resolved module does not guarantee that every dependency class needed on late execution paths has been located and linked successfully.

This lesson provides an ordered diagnostic workflow: accurately identify the error type, read the root cause, verify the class name and artifacts, inspect the class loader/module, distinguish module resolution errors, check runtime dependencies and class initialization, then apply the fix and retest.

## 1. Core Differences Between the Two Error Types

**ClassNotFoundException** is a checked exception. It typically occurs when an application or framework actively requests to look up a class by name and the corresponding class loader cannot find it.

Example:

~~~java
Class<?> type = Class.forName("com.example.plugin.CsvPlugin");
~~~

If the class cannot be found by the loading mechanism used, the call can throw ClassNotFoundException.

**NoClassDefFoundError** is a LinkageError, not a checked exception. It typically occurs when the JVM needs a class definition to link or execute bytecode, yet that definition cannot be found at the time it is needed. It can also appear after initialization of a class failed on a previous usage.

Example:

~~~java
Report report = new Report();
~~~

If code compiled against Report but at runtime the JVM cannot find the required class definition, execution can encounter NoClassDefFoundError.

Comparison table:

| Aspect | ClassNotFoundException | NoClassDefFoundError |
| --- | --- | --- |
| Classification | Checked exception | Error, subclass of LinkageError |
| Typically occurs when | An API or framework requests loading a class by name | The JVM needs a class at runtime but cannot define or use it |
| Common examples | Class.forName, ClassLoader.loadClass | `new`, method invocation, field access, dependency linking |
| Can involve class initialization? | Not a typical symptom | Yes, after an earlier initialization failure |
| Can it be handled with catch? | Can be declared with throws or caught intentionally | Usually a configuration/packaging error needing root-cause fix; should not be caught as normal logic |
| First direction of investigation | The requested class name and loader being used | Root cause, missing runtime class, or failed class initialization |

Do not assume "ClassNotFoundException is always caused by reflection" or "NoClassDefFoundError is always caused by a missing JAR." Frameworks can wrap one error inside another; in every case, read the full stack trace and cause chain.

## 2. Three Stages to Separate: Module, Class, and Initialization

In a modular application, you can visualize:

~~~text
module path / classpath
         |
         v
ModuleFinder locates descriptors
         |
         v
Module resolution selects modules + dependencies
         |
         v
ModuleLayer defines runtime modules
         |
         v
ClassLoader locates and defines classes on demand
         |
         v
Linking: verification, preparation, resolution
         |
         v
Class initialization when triggered
~~~

Each layer can fail differently:

- **Module discovery/resolution** can throw FindException or ResolutionException before running the main class.
- **Class loading** can hit ClassNotFoundException when an API looks up a class by name.
- **Class linking/usage** can hit NoClassDefFoundError if a required class is unavailable.
- **Class initialization** can throw ExceptionInInitializerError or another Error; subsequent uses can hit NoClassDefFoundError with a message indicating the class failed to initialize.
- **Package access** can cause IllegalAccessError, IllegalAccessException, or InaccessibleObjectException; these are different issues from a class being completely missing.

The first step of diagnosis is identifying which stage the JVM reached, rather than randomly tweaking multiple module options.

## 3. Read the Stack Trace Before Changing Dependencies

Example ClassNotFoundException:

~~~text
java.lang.ClassNotFoundException: com.example.plugin.CsvPlugin
    at ...
    at java.base/java.lang.Class.forName(...)
    at com.example.app/com.example.app.PluginLoader.load(...)
~~~

Information to extract:

1. **Binary class name**: com.example.plugin.CsvPlugin.
2. **First application call**: PluginLoader.load.
3. **Loader used**: which Class.forName overload, which class loader.
4. **Environment**: running in IDE, tests, JAR, container, or custom ModuleLayer.

Example NoClassDefFoundError:

~~~text
java.lang.NoClassDefFoundError: com/example/codec/Codec
    at com.example.app/com.example.app.Main.main(Main.java:12)
Caused by: java.lang.ClassNotFoundException: com.example.codec.Codec
    at ...
~~~

Do not look only at the first line. The **Caused by** section may reveal that a loader could not find a dependency class.

The class name in NoClassDefFoundError is often represented with slashes (/), such as com/example/codec/Codec, whereas ClassNotFoundException typically displays a dot-separated binary name. Both notations may refer to the exact same Java class.

If a stack trace has multiple framework wrapper layers, find the deepest cause with concrete information. Do not overlook earlier errors that appeared first in startup logs.

## 4. Reproducing ClassNotFoundException with `Class.forName`

Create the class:

~~~java
package com.example.app;

public final class DynamicLookup {
    public static void main(String[] args) {
        try {
            Class<?> type = Class.forName(
                "com.example.missing.OptionalFeature"
            );
            System.out.println(type.getName());
        } catch (ClassNotFoundException e) {
            System.err.println(
                "Cannot find optional feature: " + e.getMessage()
            );
        }
    }
}
~~~

Compile:

~~~bash
javac -d out src/com/example/app/DynamicLookup.java
~~~

Run:

~~~bash
java -cp out com.example.app.DynamicLookup
~~~

If `com.example.missing.OptionalFeature` is absent from the class search path, the Class.forName call fails. The code in this example intentionally catches the checked exception to execute a fallback branch for an optional feature.

In a real application, a class name can come from:

- Configuration files.
- Command-line arguments.
- Plugin registries or framework discovery.
- JDBC drivers or providers loaded by name.
- Reflection, dependency injection, or serialization mechanisms.

Therefore, before hunting for JARs, confirm the class name has the right package, exact casing, and is not an old name changed after refactoring.

## 5. Reproducing NoClassDefFoundError from a Missing Runtime Dependency

Suppose we have two sources:

~~~java
// src/com/example/codec/Codec.java
package com.example.codec;

public final class Codec {
    public static String encode(String value) {
        return "[" + value + "]";
    }
}
~~~

~~~java
// src/com/example/app/Main.java
package com.example.app;

import com.example.codec.Codec;

public final class Main {
    public static void main(String[] args) {
        System.out.println(Codec.encode("hello"));
    }
}
~~~

Compile:

~~~bash
javac -d build/codec src/com/example/codec/Codec.java
~~~

~~~bash
javac -cp build/codec \
      -d build/app \
      src/com/example/app/Main.java
~~~

Run with all dependencies:

~~~bash
java -cp "build/app:build/codec" com.example.app.Main
~~~

Output:

~~~text
[hello]
~~~

Run without the directory containing Codec:

~~~bash
java -cp build/app com.example.app.Main
~~~

When the JVM needs to define class Codec, yet Codec bytecode is absent from the runtime classpath, the application can hit:

~~~text
java.lang.NoClassDefFoundError: com/example/codec/Codec
~~~

This example shows that **the compile-time classpath and the runtime classpath are two separate configurations**. The fact that `javac` found a class during compilation does not guarantee the Java launcher will find that class at runtime.

On Windows, use a semicolon for multi-entry classpaths:

~~~powershell
java -cp "build/app;build/codec" com.example.app.Main
~~~

Do not "fix" this example by renaming the class or adding `--add-opens`. The actual cause is missing bytecode at runtime.

## 6. How the Module Path Changes Dependency Resolution

With explicit named modules, mandatory dependencies are declared with `requires`:

~~~java
module com.example.app {
    requires com.example.codec;
}
~~~

If `com.example.codec` cannot be found among observable modules, launching with `-m` can fail before `Main.main` is even called:

~~~bash
java --module-path mods \
     -m com.example.app/com.example.app.Main
~~~

The message might look like:

~~~text
Error occurred during initialization of boot layer
java.lang.module.FindException: Module com.example.codec not found,
required by com.example.app
~~~

This is a **module resolution** error, not the same error as the NoClassDefFoundError from the classpath example.

Points of distinction:

- A missing module required by **requires** is typically detected immediately during resolution.
- A class not found when code uses reflection may appear later, depending on how loading occurs.
- An already-resolved module can still suffer other runtime errors if the artifact lacks the needed class, a dependency is not a required module, or class initialization fails.

When logs show FindException, inspect module names, descriptors, the module path, and the dependency graph. Do not simply search for the missing class name or drop a library onto the classpath expecting `requires` to be satisfied automatically.

## 7. Inspecting Module Names and JAR Contents

To check whether an artifact is an explicit named module or an automatic module, run:

~~~bash
jar --describe-module --file libs/com.example.codec.jar
~~~

An explicit modular JAR normally contains `module-info.class` at the root of the JAR. The module name is determined by the descriptor and does not necessarily match the JAR filename.

To check whether a class is inside a JAR:

~~~bash
jar --list --file libs/com.example.codec.jar
~~~

Look for the entry:

~~~text
com/example/codec/Codec.class
~~~

If the entry is missing, possible causes include:

- The build did not package the class into the JAR.
- The artifact was excluded, shaded, or relocated.
- The source set did not include the expected class.
- The wrong version of the JAR is being deployed.
- The JAR changed package structure while the consumer still references the old name.

If multiple versions of an artifact exist, check **the exact JAR file actually used at runtime**, not merely files in the source folder or local Maven repository.

## 8. ClassLoader Determines Where Classes Are Found

In the JVM, class loading does not rely solely on a single global list of JARs. Each class loader has its own search scope and delegation relationships.

Built-in loaders typically include:

- **Bootstrap loader** for many core classes such as `java.lang.Object`.
- **Platform loader** for platform modules assigned to it.
- **Application/system loader** for application classes and many application modules in standard launch configurations.

Example:

~~~java
System.out.println(
    "Object loader: " + Object.class.getClassLoader()
);

System.out.println(
    "System loader: " + ClassLoader.getSystemClassLoader()
);

System.out.println(
    "Platform loader: " + ClassLoader.getPlatformClassLoader()
);
~~~

`Object.class.getClassLoader()` typically returns `null` to represent the bootstrap loader.

If a custom class loader only knows about a `plugins` directory, it may fail to find a class residing in another directory even though that class is present on disk. Conversely, another class loader may already have loaded a class with the same name, but that does not automatically make the class appear within the scope of the queried loader.

Class identity in the JVM consists of the class name and **defining class loader**. Two classes with the same binary name defined by two different loaders are two different types; the resulting error may be ClassCastException or a linkage error, not necessarily ClassNotFoundException.

## 9. `Class.forName`, `loadClass`, and the `initialize` Parameter

You can specify a loader explicitly:

~~~java
ClassLoader loader = ClassLoader.getSystemClassLoader();

Class<?> type = Class.forName(
    "com.example.plugin.CsvPlugin",
    false,
    loader
);
~~~

Here:

- The class name must be a binary name with dots.
- **false** requests not initializing the class solely because of this call.
- The passed-in loader determines the search scope when the class needs to be loaded.
- The JVM may still perform necessary loading/linking steps; `false` does not guarantee avoiding every dependency.

For `ClassLoader.loadClass`:

~~~java
Class<?> type = loader.loadClass(
    "com.example.plugin.CsvPlugin"
);
~~~

This call typically does not initialize the class immediately. If you need to distinguish a loading error from a static initialization error, try loading the class without requesting initialization first, then execute the code path that actually triggers initialization.

A debugging note: **Class.forName(String)** uses a loader determined by the caller, which differs from the overload that takes an explicit loader. If an application/plugin runs across multiple class loaders, always check which overload the framework is calling.

## 10. ClassNotFoundException in a Custom ModuleLayer

JPMS lets applications create separate `ModuleLayer` instances to load modules dynamically. A module can belong to a child layer and be attached to a loader other than the application/system loader.

General example:

~~~java
ModuleLayer parent = ModuleLayer.boot();

ModuleFinder finder =
    ModuleFinder.of(Path.of("plugins"));

Configuration config =
    parent.configuration().resolve(
        finder,
        ModuleFinder.of(),
        Set.of("com.example.plugin")
    );

ModuleLayer.Controller controller =
    parent.defineModulesWithOneLoader(
        config,
        ClassLoader.getSystemClassLoader()
    );

ModuleLayer pluginLayer = controller.layer();

ClassLoader pluginLoader =
    pluginLayer.findLoader("com.example.plugin");
~~~

If the plugin class belongs to this loader, use the right loader when loading:

~~~java
Class<?> type = Class.forName(
    "com.example.plugin.impl.PluginImpl",
    false,
    pluginLoader
);
~~~

Using `ClassLoader.getSystemClassLoader()` to look up a class in the new layer will not necessarily succeed. A module's loader in a child layer can know about classes that the parent application loader does not.

Two questions must be separated:

1. **Is the module in the ModuleLayer?** Check `findModule`.
2. **Can the class be found using the module's loader?** Check `findLoader` and `Class.forName`.

A ModuleLayer finding a module does not mean an arbitrary loader in the application can load every class of that module.

## 11. Thread Context ClassLoader and Frameworks

Many frameworks, containers, and plugin mechanisms use the **thread context class loader** (TCCL) to locate providers or resources.

Inspecting the loader:

~~~java
Thread thread = Thread.currentThread();

ClassLoader contextLoader =
    thread.getContextClassLoader();

System.out.println(contextLoader);
~~~

TCCL can differ from the defining loader of the currently executing class. A service invoked in a thread pool might use the thread's TCCL, leading to failing to find a provider that another thread can find.

If a framework depends on TCCL, you can set it within the scope of the task:

~~~java
Thread thread = Thread.currentThread();
ClassLoader previous = thread.getContextClassLoader();

try {
    thread.setContextClassLoader(pluginLoader);

    // Call the framework that relies on the context class loader.
} finally {
    thread.setContextClassLoader(previous);
}
~~~

Always restore the previous loader in `finally` to avoid affecting subsequent tasks, especially with thread pools.

For JPMS service providers, you can select the ModuleLayer explicitly:

~~~java
ServiceLoader<MyService> services =
    ServiceLoader.load(pluginLayer, MyService.class);
~~~

When ServiceLoader cannot find a provider, check **uses**, **provides ... with**, resolution configuration, loader/layer, and how the framework loads services. A provider error may be generically reported by a framework wrapper as "class not found," so inspect the actual underlying cause.

## 12. NoClassDefFoundError After Class Initialization Fails

An easily overlooked cause is an error inside a static initializer or static field initialization.

Example:

~~~java
package com.example.app;

public final class BrokenConfig {
    static {
        if (System.getProperty("required.config") == null) {
            throw new IllegalStateException("Missing required.config");
        }
    }

    public static String value() {
        return "ready";
    }
}
~~~

The first time a thread actually triggers initialization:

~~~java
System.out.println(BrokenConfig.value());
~~~

If the `required.config` property is missing, the static initializer throws an exception. The JVM may wrap the cause in **ExceptionInInitializerError**.

The class is now in an initialization-failed state. Subsequent uses may report:

~~~text
java.lang.NoClassDefFoundError: Could not initialize class
com.example.app.BrokenConfig
~~~

In this situation, **the class file may be completely present on the classpath or module path**. The issue is not a JAR missing bytecode, but rather that class initialization failed.

How to diagnose:

1. Find the **first exception in the log**, especially ExceptionInInitializerError.
2. Check the `Caused by` section for config, permission, environment, or resource errors.
3. Do not solve it by adding unrelated JARs.
4. Fix the initialization condition and rerun in a fresh JVM to verify.

Some initialization failures can also occur when static fields depend on other classes, resource connections, or native libraries. Do not look only at the final NoClassDefFoundError message.

## 13. Indirect Missing Class Errors

The requested class may exist, while a class it depends on is absent.

Example:

~~~text
application.jar
  └── com.example.app.Main

feature.jar
  └── com.example.feature.Service

codec.jar
  └── com.example.codec.Codec
~~~

If Main uses Service and Service in turn needs Codec, a package missing `codec.jar` can cause an error to surface only when code calls a particular method.

The error message may mention **Codec**, even though the developer is focused on **Service**. Therefore, do not inspect only the JAR containing the directly called class.

Common causes:

- Dependency scope is compile-only and absent at runtime.
- Artifact was excluded from the package or container image.
- A transitive dependency was overridden by another version.
- Production configuration omits an optional plugin or module.
- A library changed binary names/packages between versions.
- Bytecode references a class that only appears on a rarely executed branch.

When diagnosing, trace the dependency actually reported in the stack trace and inspect the entire runtime dependency tree.

## 14. Maven: When Is a Dependency Present?

In Maven, a dependency can be declared with different scopes. For example:

~~~xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>codec</artifactId>
    <version>1.0.0</version>
</dependency>
~~~

For an ordinary application, a compile dependency not restricted by a special scope is included for both compile and runtime according to Maven's model.

If the dependency is placed in `provided` scope:

~~~xml
<scope>provided</scope>
~~~

then the build assumes the deployment environment will supply the dependency. If the actual environment lacks it, runtime may fail to find the class.

Similarly, if a dependency only has `test` scope, it is not included in the production application's runtime merely because tests compile.

Run:

~~~bash
mvn dependency:tree
~~~

to view the dependencies and versions selected by Maven. When using a modular application, you must also check whether plugins configure the module path or classpath and whether the final `java` command receives the artifact.

Do not merely look at a dependency in `pom.xml` and assume the JAR is in the final package. Containers, runtime launchers, and distributions may use a different set of artifacts.

## 15. Gradle: `runtimeClasspath` and `compileClasspath`

Gradle separates multiple configurations for different phases. A dependency can exist in `compileClasspath` yet be absent from `runtimeClasspath` if an inappropriate configuration is used.

Example standard declaration:

~~~groovy
dependencies {
    implementation 'com.example:codec:1.0.0'
}
~~~

If an API is only needed at compile-time and the library is absent at runtime, the configuration can differ. However, if the class is genuinely used in production, ensure the dependency appears on **runtimeClasspath** or the module path according to the application configuration.

You can inspect the dependency tree:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

And inspect a specific dependency:

~~~bash
./gradlew dependencyInsight \
  --dependency codec \
  --configuration runtimeClasspath
~~~

These tools show which version Gradle selected and whether exclusions or conflict resolution occurred.

When using the application plugin or a custom `JavaExec`, cross-check the running task against the actual classpath/module path. A test task with full dependencies does not guarantee the production distribution also includes all those dependencies.

## 16. Observing JVM Class Loading

Since JDK 9, you can use unified logging:

~~~bash
java -Xlog:class+load=info \
     --module-path mods \
     -m com.example.app/com.example.app.Main
~~~

The log shows many loaded classes and their corresponding sources. This is a useful way to check:

- Which JAR or module a class was loaded from.
- Whether an unexpected version of a class is being used.
- Whether a class was loaded before the time of the error.
- Which sources classes in the same package are loaded from.

You can increase the detail level for diagnostic purposes:

~~~bash
java -Xlog:class+load=debug \
     --module-path mods \
     -m com.example.app/com.example.app.Main
~~~

Class load logging can produce very many lines. Write it to a log file when analysis is needed, rather than mixing all logs into production application output.

Important: logging successfully loaded classes does not necessarily explain every missing class. You must combine stack traces, class loaders, and artifact content inspection.

## 17. Observing Module Resolution

To see which modules are selected at startup:

~~~bash
java --show-module-resolution \
     --module-path mods \
     -m com.example.app/com.example.app.Main
~~~

This tool is helpful when a module is missing a `requires` dependency or is resolved differently than expected.

You can list observable modules:

~~~bash
java --module-path mods --list-modules
~~~

The difference:

- **--list-modules** shows modules that can be found.
- **--show-module-resolution** shows modules included in the launch command's configuration.
- **ModuleLayer.boot().findModule(name)** checks whether a module is present in the boot layer of the running JVM.

Example:

~~~java
boolean available =
    ModuleLayer.boot()
        .findModule("com.example.codec")
        .isPresent();

System.out.println("Codec in boot layer: " + available);
~~~

A JAR present in the `mods` directory whose module is not requested as a root, dependency, or needed service provider may not end up in the boot layer.

If a module does not appear in the graph, check `requires`, `--add-modules`, service binding, and custom layer configuration. Do not use `--add-opens` to try to bring a module into the graph.

## 18. Module Found, Yet Package Not Accessible

This is not a typical class-not-found error, even though framework messages can be misleading.

Suppose:

~~~java
module com.example.codec {
    exports com.example.codec.api;
}
~~~

And:

~~~java
module com.example.app {
    requires com.example.codec;
}
~~~

App can use public APIs from package `com.example.codec.api`. However, if app attempts to import a public class from **com.example.codec.internal**, the compiler may report `package is not visible`.

If a framework uses reflection on a private member of an unopened package, it may report `InaccessibleObjectException`.

Distinguish:

| Symptom | Direction to check |
| --- | --- |
| Module not found | Module path, module name, `requires`, and roots |
| Package is not visible | `requires`/readability and `exports` |
| IllegalAccessError | Runtime access permissions and bytecode |
| InaccessibleObjectException | `opens` and caller's module identity |
| ClassNotFoundException | Loader and requested class name |
| NoClassDefFoundError | Runtime/linking class or failed initialization |

Do not pile on `--add-reads`, `--add-exports`, and `--add-opens` for every error. Those flags address different mechanisms and can weaken encapsulation if overused.

## 19. Class Loading from Automatic and Unnamed Modules

An **automatic module** is a JAR without an explicit descriptor that is placed on the module path and receives a module name per JPMS rules.

An **unnamed module** typically holds classes/JARs on a class loader's classpath.

The same legacy JAR can be handled differently when moving between the two paths:

~~~bash
java --class-path "libs/*" com.example.app.Main
~~~

versus:

~~~bash
java --module-path libs \
     --add-modules legacy.codec \
     -m com.example.app/com.example.app.Main
~~~

The name **legacy.codec** in the example must be the actual module name of the JAR; do not guess it from the filename without checking.

When moving to the module path:

- The JAR may become an automatic named module.
- Consumer named modules must have appropriate readability relationships.
- The module graph must satisfy JPMS constraints.
- Split packages or module name collisions can cause resolution to fail.

An error after migration may be FindException or ResolutionException, not necessarily ClassNotFoundException. Therefore, the first step is identifying the launch mode and the stage of failure.

## 20. Diagnosing ServiceLoader When a Provider Is Not Found

Modular applications often use ServiceLoader to discover implementations.

Example consumer module:

~~~java
module com.example.app {
    requires com.example.spi;
    uses com.example.spi.ReportProvider;
}
~~~

Provider module:

~~~java
module com.example.provider.csv {
    requires com.example.spi;

    provides com.example.spi.ReportProvider
        with com.example.provider.csv.CsvProvider;
}
~~~

Points to verify:

1. The service interface belongs to a shared module read by all sides.
2. The consumer declares `uses` appropriately.
3. The provider declares `provides ... with`.
4. The provider module actually participates in the configuration being used.
5. ServiceLoader is called with the right layer/loader.
6. The constructor or provider method can execute successfully.
7. The provider's dependencies are present and compatible.

With a custom layer:

~~~java
ServiceLoader<ReportProvider> services =
    ServiceLoader.load(pluginLayer, ReportProvider.class);
~~~

Using the layer-appropriate overload reduces confusion compared to relying on an out-of-scope TCCL.

ServiceLoader can throw **ServiceConfigurationError** if a provider is invalid or cannot be created. If the cause is ClassNotFoundException, NoClassDefFoundError, or an initialization error, fix the root cause instead of merely changing service configuration.

## 21. Tools for Inspecting Artifacts and Dependencies

A practical command toolkit:

Inspect module descriptor:

~~~bash
jar --describe-module --file libs/com.example.codec.jar
~~~

List classes in JAR:

~~~bash
jar --list --file libs/com.example.codec.jar
~~~

Inspect bytecode-level dependencies:

~~~bash
jdeps --module-path mods \
      --module com.example.app
~~~

Find references to internal JDK APIs in a library:

~~~bash
jdeps --jdk-internals libs/legacy-library.jar
~~~

Inspect runtime module graph:

~~~bash
java --show-module-resolution -p mods \
     -m com.example.app/com.example.app.Main
~~~

Observe class loading:

~~~bash
java -Xlog:class+load=info -p mods \
     -m com.example.app/com.example.app.Main
~~~

Each tool has different blind spots. For instance, `jdeps` analyzes dependencies detectable from bytecode; class names constructed dynamically from strings, reflection, or resources may not be fully inferred. Therefore, combine runtime logs with tests along the actual execution paths.

## 22. Step-by-Step Diagnostic Workflow

When receiving a bug reporting "class not found" or "no class definition," follow this order:

1. **Collect the initial log**: full stack trace, cause chain, failure timestamp, and JDK version.
2. **Record the class name**: binary name, package, old/new name after relocation, and which class is being requested.
3. **Identify the error type**: ClassNotFoundException, NoClassDefFoundError, FindException, ResolutionException, ServiceConfigurationError, or an access error.
4. **Inspect artifacts**: Does the JAR actually contain the class? Is the right version running?
5. **Check compile/runtime config**: classpath, module path, dependency scopes, and exclusions.
6. **Check the module graph**: root, `requires`, automatic modules, custom layers, and service binding.
7. **Check the specific loader**: system/application, platform, plugin loader, or TCCL.
8. **Look for earlier initialization errors**: especially when the message says "Could not initialize class."
9. **Check access permissions separately**: readability, `exports`, `opens` if logs indicate access denied.
10. **Apply the minimal root-cause fix**: add the right runtime dependency, fix the class name, adjust descriptors or loaders, or fix static initialization.
11. **Rerun with the same launcher style**: IDE and CLI can differ in classpath/module path setup.
12. **Add regression tests**: run in a production-like environment and cover the failing functional branch.

Quick decision table:

| Symptom | Check first | Common fix |
| --- | --- | --- |
| Class.forName throws ClassNotFoundException | Class name, loader, classpath/plugin layer | Use the right loader, fix the name, or package the class |
| NoClassDefFoundError: com/.../Codec | Runtime class actually missing or linkage error | Add the right dependency/version for runtime |
| NoClassDefFoundError: Could not initialize class | Earlier initialization failure | Locate ExceptionInInitializerError and fix its cause |
| FindException: required module not found | Module name, module path, and descriptor | Place the module in the right location or fix `requires` |
| ResolutionException involving packages | Split package or module graph | Restructure packages/dependencies |
| InaccessibleObjectException | Package not `opens` to caller | Adjust reflection or qualified `opens` |
| ServiceConfigurationError | Service provider descriptor and cause | Fix provider, dependencies, loader/layer |

## 23. Preventing Errors in CI/CD and Deployment

Many errors appear only after packaging or deployment. To reduce the risk:

- Use the same JDK major version in build, test, and production unless there is a specific compatibility reason.
- Test the **final artifact** instead of only running source code through an IDE.
- Record the actual `java` command line, especially `--module-path`, `--class-path`, `--add-modules`, and JVM args.
- Control dependency versions and remove duplicate JARs or leftover old versions in the distribution.
- Ensure required runtime-only dependencies are included in the image or deployment package.
- When using plugins, have integration tests that load plugins from real directories and layers.
- Test dynamic loading, ServiceLoader, and static initializers rather than testing startup alone.
- For optional dependencies, design fallback behavior and clear error messages if the class is absent.
- Do not broadly catch LinkageError to ignore serious configuration failures and continue in a half-working state.

A test can verify packaging:

~~~bash
jar --list --file dist/com.example.app.jar
~~~

Then use the production-like launch command and execute the code path that needs the packaged class or plugin.

## 24. Practical Exercises

1. Create the Codec example in Section 5, compile successfully, then remove `build/codec` from the runtime classpath. Record the NoClassDefFoundError.
2. Create DynamicLookup calling `Class.forName` with a nonexistent class. Record the ClassNotFoundException.
3. Compare the two stack traces and their `cause` sections if present.
4. Put Codec into an explicit named module, declare `requires`, then try running when the Codec module is absent from the module path. Observe FindException.
5. Place the Codec JAR on the module path, and run `--list-modules` and `--show-module-resolution` to distinguish observable modules from resolved modules.
6. Create a class with a failing static initializer; observe the first error and the NoClassDefFoundError on subsequent usage in the same JVM.
7. Create a separate plugin layer and try loading the plugin with the system loader, then with `pluginLayer.findLoader`.
8. Use `-Xlog:class+load=info` to see which sources classes are loaded from.
9. Try changing a Maven/Gradle dependency scope and compare `compileClasspath`/`runtimeClasspath`.
10. Write down a short debugging checklist that can be applied when production reports a missing class.

**ClassNotFoundException and NoClassDefFoundError differ in more than just name.** They help pinpoint whether you have an issue in looking up a class by name, JVM class linking/usage, or class initialization after an earlier error. In modular applications, further separating module resolution, class loader/module layer, and package access will lead you to the real root cause faster than trial-and-error addition of flags or JARs.
