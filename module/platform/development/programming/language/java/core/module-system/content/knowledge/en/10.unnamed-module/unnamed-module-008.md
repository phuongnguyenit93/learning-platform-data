# Auditing dependencies still outside the module path

When migrating a Java application to the Java Platform Module System (JPMS), not every library automatically becomes a named module. An application may already have `module-info.java`, yet some dependencies are still placed on the **classpath** instead of the **module path**. Libraries on the classpath belong to the unnamed module; they have no explicit module descriptor and do not participate in the module graph the way explicit modules do.

Auditing dependencies that remain outside the module path helps uncover unmodularized libraries, inconsistent build configurations, or omitted runtime dependencies. This is an important step so the application can properly control dependencies and access permissions under JPMS.

## 1. Classpath, module path, and the unnamed module

Before JPMS, Java typically located classes and libraries via the classpath:

~~~bash
java -cp "app.jar:libs/*" com.example.app.Main
~~~

On Windows, the separator between classpath elements is a semicolon:

~~~powershell
java -cp "app.jar;libs/*" com.example.app.Main
~~~

When an application runs in this traditional way, classes and JARs on the classpath are loaded into the **unnamed module** corresponding to the class loader. The unnamed module has no stable module name in `module-info.java`; it is part of the classpath compatibility mechanism.

JPMS adds the module path to locate named modules:

~~~bash
java --module-path "mods:libs" -m com.example.app/com.example.app.Main
~~~

In the example above:

- `--module-path` specifies directories or JARs containing modules.
- `-m` specifies the main module and main class to launch.
- Modules with explicit descriptors or automatic modules can be found on the module path.

Both mechanisms can appear together in a single launch command:

~~~bash
java --module-path mods --class-path "legacy/*" -m com.example.app/com.example.app.Main
~~~

Here, the JARs in `legacy/*` still belong to the unnamed module; they do not automatically become named modules merely because the main application is launched with `-m`.

## 2. Three common states of a dependency

When auditing a JAR, determine which case it currently falls into.

### 2.1. Explicit named module

This is a library with an explicit module descriptor, typically compiled from `module-info.java` and packaged as `module-info.class`.

Example:

~~~java
module com.example.catalog {
    exports com.example.catalog.api;
}
~~~

A modular JAR can be placed on the module path. Another module can declare the dependency:

~~~java
module com.example.app {
    requires com.example.catalog;
}
~~~

This is the state that provides the clearest dependency and package control.

### 2.2. Automatic module

A JAR without `module-info.class`, when placed on the module path, can be treated as an **automatic module**. The module name is derived from the JAR filename, or taken from the `Automatic-Module-Name` attribute in the manifest if the library provides that attribute.

Manifest example:

~~~text
Manifest-Version: 1.0
Automatic-Module-Name: com.example.legacy
~~~

The application module can declare:

~~~java
module com.example.app {
    requires com.example.legacy;
}
~~~

An automatic module acts as a bridge allowing legacy libraries to join the module path. It has broader module readability and package exports than an explicit module, so it does not establish as strict encapsulation as a deliberately designed descriptor.

If the library cannot be modified immediately, an automatic module is often a useful transitional step. For libraries owned by the development team, consider adding an explicit module descriptor once APIs and dependencies are identified.

### 2.3. Dependency on the classpath (unnamed module)

A JAR on the classpath belongs to an unnamed module. It has no name for other modules to write in a `requires` directive.

Example:

~~~bash
java --module-path mods --class-path "legacy/old-client.jar" \
     -m com.example.app/com.example.app.Main
~~~

In this case, `old-client.jar` is outside the module path. The named module `com.example.app` does not automatically read the unnamed module. Therefore, code in the module may fail when importing or using classes coming from that library.

You cannot write:

~~~java
module com.example.app {
    requires unnamed;
}
~~~

`unnamed` is not a valid module name to use in `requires`. If you want to use the library via the module path, move it onto the module path as an automatic module or explicit module; if you must keep it on the classpath, consider a compatibility mechanism like `--add-reads` as shown later.

## 3. Why do dependencies outside the module path cause problems?

A named module can only use types from modules it reads, and the package being accessed must be appropriately exported by that other module.

If a library remains in the unnamed module:

- The named module has no explicit `requires` relationship to that library.
- The dependency does not appear as a named module in the module graph.
- It is hard to control which packages of the library are exposed.
- Dependency checks with JPMS tools do not reflect the full state of libraries on the classpath.
- A build may compile using the classpath while runtime launches with a different module path, leading to missing-class or unreadable-package errors.

A common error is having source code import:

~~~java
import com.vendor.legacy.Client;
~~~

while the library containing `com.vendor.legacy.Client` was only added to the classpath. When compiling the module, the compiler may report that the package does not exist or is not visible. What needs checking is the dependency location and module readability, not just the import name.

## 4. Inventorying dependencies from the build and launch command

Before changing configuration, compile a list of actual dependencies at both compile time and runtime.

With Gradle, you can inspect the project's dependency graph:

~~~bash
./gradlew :app:dependencies
~~~

To view a specific configuration:

~~~bash
./gradlew :app:dependencies --configuration compileClasspath
./gradlew :app:dependencies --configuration runtimeClasspath
~~~

With Maven:

~~~bash
mvn -pl app dependency:tree
~~~

These reports show which libraries are declared directly or transitively and which configurations contain them. However, a build tool's dependency report alone is not enough to prove a JAR is on the module path. Cross-check how plugins and build tasks configure the compiler and JVM.

When running the application, inspect all parameters:

- `--module-path` or `-p`: module path entries.
- `--class-path` or `-cp`: classpath entries.
- `-m` or `--module`: the main module being launched.
- Additional arguments such as `--add-reads`, `--add-modules`, or `--patch-module` if present.

Do not look solely at `build.gradle` or `pom.xml`; the actual launch command, IDE configuration, deployment scripts, and container commands can also add their own classpath/module path entries.

## 5. Using JDK tools to determine module status

### 5.1. Inspecting a JAR with jar --describe-module

Command:

~~~bash
jar --describe-module --file libs/legacy-client.jar
~~~

This can show:

- Whether the JAR has an explicit module descriptor.
- The derived module name if it is an automatic module.
- Exported packages or services declared in the descriptor.

If the JAR has no descriptor and is placed on the classpath, running the inspection command does not turn it into a named module. Interpret the output alongside the JAR's actual location in the launch command.

### 5.2. Analyzing dependencies with jdeps

`jdeps` analyzes dependencies at the class, package, and module levels. Some useful commands:

~~~bash
# View module-level dependencies of a JAR
jdeps --list-deps libs/legacy-client.jar

# Analyze dependencies with modules on the module path
jdeps --module-path mods:libs --check com.example.app

# Generate a sample module-info.java to assist migrating a JAR
jdeps --generate-module-info generated-modules libs/legacy-client.jar
~~~

Exact options and output depend on the JDK version. Descriptor files generated by the tool are a starting point for review; module names, exported packages, dependencies, and reflection requirements must be verified before production use.

`jdeps` can also report dependencies on JDK internal APIs or missing dependencies. Read messages carefully and provide sufficient classpath/module path entries during analysis to avoid conclusions based on incomplete data.

### 5.3. Observing module resolution at runtime

You can ask the JVM to print resolved module information:

~~~bash
java --show-module-resolution \
     --module-path mods:libs \
     -m com.example.app/com.example.app.Main
~~~

This output helps confirm which modules are found, which modules are required, and which modules join the module graph. If a dependency only resides on the classpath, cross-reference the `--class-path` parameter to identify that it belongs to the unnamed module.

### 5.4. Viewing modules recognized by the JVM

You can list modules in the runtime image:

~~~bash
java --list-modules
~~~

This command is mainly useful for inspecting platform modules and modules in the runtime image. It does not replace checking all external dependencies that the application brings in at launch.

## 6. Procedure for auditing a specific dependency

For each JAR suspected of still being outside the module path, follow these steps:

1. **Identify the artifact:** record the JAR name, version, declaration source, and why the application needs it.
2. **Identify the configuration:** check whether the dependency appears on the compile classpath, runtime classpath, or both.
3. **Identify the runtime location:** locate the JAR in `--module-path`, `--class-path`, a plugin directory, or a custom class loader.
4. **Inspect the descriptor:** use `jar --describe-module` to determine whether it is an explicit module, automatic module, or traditional JAR.
5. **Verify the module name:** compare the advertised name with the name in `requires`; do not guess the name from the filename if the tool provides an official name.
6. **Check transitive dependencies:** see which other JARs the library needs and where those dependencies reside.
7. **Check services and reflection:** if the library uses SPI, `ServiceLoader`, reflection, or framework injection, check the corresponding configuration when changing its location.
8. **Cross-check compile and runtime:** ensure the same dependency model is applied in both phases.

You can record the audit results in a table:

| Dependency | Current location | Module status | Action plan |
|---|---|---|---|
| `catalog-api.jar` | Module path | Explicit module | Keep corresponding `requires` |
| `legacy-client.jar` | Classpath | Unnamed module | Evaluate automatic or explicit module |
| `old-json.jar` | Module path | Automatic module | Plan modularization |
| `logging.jar` | Classpath | Unnamed module | Inspect API, runtime, and loading mechanism |

This is an illustrative example; actual status must come from the project's launch commands and artifact contents.

## 7. How to bring dependencies onto the module path

There are several approaches depending on your control over the library and compatibility constraints.

### 7.1. Prefer explicit modules when possible

If the development team owns the library's source code, create `module-info.java`:

~~~java
module com.example.legacy.client {
    requires java.net.http;

    exports com.example.legacy.client.api;
}
~~~

After compilation, the JAR must contain `module-info.class`. Then the JAR can be placed on the module path and declared:

~~~java
module com.example.app {
    requires com.example.legacy.client;
}
~~~

Export only the API packages that need to be exposed. Internal packages can be kept private to protect encapsulation.

### 7.2. Use automatic modules as a transitional step

If you cannot modify the library source yet, you can move the descriptorless JAR onto the module path. Java will treat it as an automatic module.

Example:

~~~bash
java --module-path "mods:libs/legacy-client.jar" \
     -m com.example.app/com.example.app.Main
~~~

Then the application module declares the actual automatic module name:

~~~java
module com.example.app {
    requires com.example.legacy.client;
}
~~~

The illustrative name above is only valid if the manifest or JAR filename actually produces that module name. Confirm with:

~~~bash
jar --describe-module --file libs/legacy-client.jar
~~~

If you have permission to modify the library, the `Automatic-Module-Name` attribute in the manifest helps keep the module name stable across JAR filename changes. Automatic modules aid migration but still have broad encapsulation, so treat this as a transitional state when appropriate.

### 7.3. Keep a dependency on the classpath as a controlled exception

During migration, it is sometimes necessary to keep a library on the classpath. Named modules do not read unnamed modules by default. A compatibility option can be used:

~~~bash
java --module-path mods \
     --class-path "legacy/old-client.jar" \
     --add-reads com.example.app=ALL-UNNAMED \
     -m com.example.app/com.example.app.Main
~~~

`--add-reads com.example.app=ALL-UNNAMED` adds a readability relationship from the specified module to the unnamed module. It can support cases where the classpath must continue to be used during migration.

This is an exception that must be managed carefully:

- It does not turn a JAR on the classpath into a named module.
- It does not create a module descriptor for the library.
- The dependency remains outside the explicit module graph.
- Packages of the unnamed module have broader access exposure than explicit modules.
- Build and runtime must pass the same appropriate policy; configuration in one phase does not automatically apply to the other.

Do not add `ALL-UNNAMED` to every module just to silence errors. Scope it strictly to modules needing compatibility and plan to remove the exception once the library is modularized or replaced.

## 8. Checking transitive dependencies and runtime

A dependency might already be on the module path while the dependencies it needs remain on the classpath or are missing at runtime. Therefore, checking a single JAR is not enough.

Example:

~~~text
app
  └── requires legacy.client
          ├── requires java.net.http
          └── uses legacy.spi.Transport
                  └── provider located in transport.plugin.jar
~~~

Verify:

- Which `requires` directives the library's module descriptor declares.
- Whether those dependencies are present on the module path at compile time and runtime.
- Whether required providers reside in the module layer searched by the application.
- Whether the library uses reflection into internal packages; if so, identify the exact packages and modules needing `opens`.
- Whether the same library is placed on both the classpath and the module path.

Duplicating an artifact in both places can cause confusion regarding class loaders, module identity, or which class version gets loaded. Remove duplicate declarations after determining the proper location to use.

## 9. Aligning Gradle/Maven configuration with JPMS

The build tool manages artifacts and the classpath/module path, while JPMS controls readability and encapsulation. Both layers must be consistent.

With Gradle, check the dependency report:

~~~bash
./gradlew :app:dependencies --configuration compileClasspath
./gradlew :app:dependencies --configuration runtimeClasspath
~~~

Further inspect the Java compile configuration and application run task to see whether dependencies are placed on the classpath or module path. The Gradle Java plugin has module path inference for modular sources; verify the actual plugin and task configuration rather than assuming every configuration automatically switches properly.

With Maven, inspect the dependency tree and corresponding compiler/plugin/exec configuration:

~~~bash
mvn -pl app dependency:tree
~~~

Do not modify `module-info.java` merely to mask a build configuration error. If a dependency belongs on the module path, ensure the build tool supplies the module properly; if intentionally keeping it on the classpath, document the exception clearly and configure corresponding readability where needed.

## 10. Common errors

**Source imports the library, yet the compiler reports the package does not exist.** Check whether the JAR is actually on the compile path used for the module; determine whether it is on the classpath or module path.

**`requires` reports module not found.** Check the module name with `jar --describe-module`, the module path location, and the dependency configuration.

**Compiles successfully, yet runtime reports missing class.** Compile path and runtime path may differ. Check launch arguments, container scripts, IDE run configurations, and runtime dependencies.

**Moved JAR to the module path, yet package access errors occur.** If it is an explicit module, the package might not be exported; if a framework uses reflection, restricted `opens` may be needed.

**Used filename as module name.** The module name may be normalized from the JAR filename or declared in the manifest. Always verify the name recognized by the JDK.

**Converted a dependency to an automatic module, yet forgot its dependencies.** Check transitive dependencies and related providers/services as well.

**Added `--add-reads` and assumed the dependency is now modularized.** This option only adds readability to the unnamed module; the JAR is still on the classpath.

## 11. Audit checklist

When auditing a modular application, check sequentially:

1. Direct and transitive dependency lists at compile time and runtime.
2. Location of each JAR in the launch command: module path, classpath, or custom class loader.
3. Status of each JAR: explicit module, automatic module, or classpath library.
4. Actual module names and corresponding `requires` directives.
5. Dependencies still residing in the unnamed module and why they have not been migrated.
6. Any `--add-reads ...=ALL-UNNAMED` configuration, its scope, and removal plan.
7. Packages needing exports or opens and which target modules are allowed access.
8. Whether providers/services are placed in the right module layer.
9. Consistency between compile path and runtime path.
10. Verification outputs from `jar --describe-module`, `jdeps`, and `--show-module-resolution` where appropriate.

Auditing dependencies outside the module path involves checking artifacts, build configurations, and launch commands together. By distinguishing explicit modules, automatic modules, and unnamed modules, you can migrate dependencies under control, maintain necessary compatibility, and gradually move the application toward a clear module graph.