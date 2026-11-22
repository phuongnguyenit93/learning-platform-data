# Mixing Classpath and Module Path in Java: Boundaries and Safe Integration

Java has two mechanisms for locating and organizing code outside the JDK: the **classpath** and the **module path**. They can appear together in a single build or run command, but each mechanism creates a different access model.

The classpath groups classes and JARs into the **unnamed module** of a class loader. The module path locates named modules, reads module descriptors, resolves the dependency graph, and enforces exports/opens rules. An application can combine both mechanisms during a migration phase, but it needs to know which code belongs to which module and which module is allowed to read which.

The anti-pattern to avoid is mixing paths arbitrarily: placing the same library in both places, putting a legacy JAR on the classpath and then declaring `requires` as if it were a named module, or adding many `--add-reads`/`--add-opens` flags to mask an incorrect module graph. This article explains the differences, the supported integration patterns, runnable examples on Java 17+, and a safe migration workflow.

## 1. Classpath and module path solve two different problems

### Classpath

The classpath is a list of directories and JARs containing classes/resources. Code loaded from the classpath belongs to the unnamed module of the corresponding class loader.

Example:

~~~bash
javac --release 17 -d out src/com/acme/app/Main.java
java --class-path out com.acme.app.Main
~~~

Equivalent forms of the classpath option:

~~~text
-cp
-classpath
--class-path
~~~

A legacy application can use multiple JARs:

~~~bash
java --class-path "app.jar;lib/*" com.acme.app.Main
~~~

On Windows, a semicolon separates classpath entries. On Linux/macOS, use a colon:

~~~bash
java --class-path "app.jar:lib/*" com.acme.app.Main
~~~

The classpath does not require each JAR to have a module descriptor. If a JAR has `module-info.class` and is placed on the classpath, that descriptor is ignored; the JAR's classes are treated as code in the unnamed module.

### Module path

The module path contains modules for the Java compiler or runtime to resolve. A module can be:

- Explicit module: a JAR with `module-info.class` or an exploded module with `module-info.class`.
- Automatic module: a JAR without a module descriptor that is placed on the module path.

Example:

~~~bash
java --module-path mods -m com.acme.app/com.acme.app.Main
~~~

Equivalent forms:

~~~text
-p
--module-path
~~~

The module path has a module graph. Each named module declares dependencies with `requires` and public packages with `exports`. The runtime checks readability and package access when resolving the module configuration.

### Quick comparison

| Characteristic | Classpath | Module path |
|---|---|---|
| Unit of organization | Class/JAR | Module |
| Module membership | Unnamed module | Explicit or automatic named module |
| module-info.class | Ignored | Used if it is an explicit module |
| Dependency | List of paths | Module graph |
| Package access | No JPMS exports | Follows exports/opens |
| Encapsulation | Looser | Strong encapsulation with explicit modules |
| Module name | Not required | Requires explicit or automatic name |
| Suitable for | Legacy applications, non-modular libraries | JPMS applications and libraries |

The classpath is not another version of the module path. Moving a JAR from the classpath to the module path can change module membership, readability, reflection, and how service providers are discovered.

## 2. Unnamed module, explicit module, and automatic module

### Unnamed module

Code on the classpath belongs to the unnamed module. The unnamed module reads all observable modules and exports/opens its own packages. However, a named module cannot declare `requires` on the unnamed module via `module-info.java`.

This asymmetry explains why a classpath application can use public APIs from resolved named modules, whereas a named module cannot naturally import a library that resides only on the classpath.

Each class loader can have its own unnamed module. For typical applications, JARs on the application classpath belong to the unnamed module of the application class loader.

### Explicit module

An explicit module has `module-info.java`:

~~~java
module com.acme.greeter {
    exports com.acme.greeter;
}
~~~

A consumer module declares:

~~~java
module com.acme.app {
    requires com.acme.greeter;
}
~~~

The consumer can only read public APIs belonging to packages exported by the `greeter` module.

### Automatic module

A legacy JAR without `module-info.class` becomes an automatic module when placed on the module path.

The module name is taken from the `Automatic-Module-Name` attribute in the manifest if present. Otherwise, Java derives the name from the JAR filename. Because the derived name can change when the file is renamed or its version suffix changes, libraries should provide a stable `Automatic-Module-Name` in the manifest.

Example manifest for a legacy library:

~~~text
Manifest-Version: 1.0
Automatic-Module-Name: com.acme.legacy
~~~

Create the JAR:

~~~bash
jar --create --file mods/legacy-lib.jar --manifest legacy.mf -C legacy-classes .
~~~

Check the module name:

~~~bash
jar --describe-module --file mods/legacy-lib.jar
~~~

Representative output:

~~~text
No module descriptor found. Derived automatic module.

com.acme.legacy automatic
requires java.base mandated
contains com.acme.legacy
~~~

An automatic module is a migration bridge and does not have the same level of encapsulation as an explicit module. When resolved, it reads other modules and its packages are treated as broadly exported/open. Replace automatic modules with explicit modules when the library is ready.

## 3. Can classpath and module path be used at the same time?

Yes. Both the Java launcher and `javac` support specifying both paths in a single run.

Launcher example:

~~~bash
java --module-path mods --add-modules com.acme.greeter --class-path app-classes com.acme.app.Main
~~~

In this example:

- `com.acme.greeter` is resolved from the module path.
- `app-classes` is loaded from the classpath and belongs to the unnamed module.
- The unnamed module can read packages exported by `com.acme.greeter`.
- `--add-modules` adds `com.acme.greeter` to the set of resolved modules.

The key point is that the two paths do not automatically merge into one shared path. Each library still belongs to the module determined by its location.

### Directional readability rules

| Calling code | Dependency location | Result |
|---|---|---|
| Classpath/unnamed module | Named module that is resolved and exports API | Can read public API |
| Named module | Explicit module on module path | Use `requires` |
| Named module | Automatic module on module path | Use `requires` with the automatic module name |
| Named module | JAR only on classpath | Not readable by default |
| Classpath/unnamed module | JAR on classpath | Used via normal classpath rules |

Do not assume that because two JARs appear in the same `java` command, they automatically read each other. The module graph still applies.

## 4. Integration pattern 1: classpath application using a named module

This is useful when a legacy application still runs on the classpath but needs to use a modularized library.

Example structure:

~~~text
hybrid/
├── greeter-src/
│   └── com.acme.greeter/
│       ├── module-info.java
│       └── com/acme/greeter/Greeter.java
├── mods/
└── app-src/
    └── com/acme/app/Main.java
~~~

File `greeter-src/com.acme.greeter/module-info.java`:

~~~java
module com.acme.greeter {
    exports com.acme.greeter;
}
~~~

File `Greeter.java`:

~~~java
package com.acme.greeter;

public final class Greeter {
    public static String message() {
        return "Hello from named module";
    }
}
~~~

Compile the module:

~~~bash
javac --release 17 --module-source-path greeter-src -d mods -m com.acme.greeter
~~~

The result is an exploded module `mods/com.acme.greeter`. It can be run directly from the module path, or packaged into a JAR:

~~~bash
jar --create --file mods/com.acme.greeter.jar -C mods/com.acme.greeter .
~~~

File `app-src/com/acme/app/Main.java` has no `module-info.java`:

~~~java
package com.acme.app;

import com.acme.greeter.Greeter;

public final class Main {
    public static void main(String[] args) {
        System.out.println(Greeter.message());
    }
}
~~~

Compile the classpath code while informing the compiler of the module dependency:

~~~bash
javac --release 17 --module-path mods --add-modules com.acme.greeter -d app-classes app-src/com/acme/app/Main.java
~~~

Run:

~~~bash
java --module-path mods --add-modules com.acme.greeter --class-path app-classes com.acme.app.Main
~~~

Exact stdout:

~~~text
Hello from named module
~~~

This is a valid combination: the application remains in the unnamed module, while `greeter` is a named module. The API package `com.acme.greeter` must be exported.

If `--add-modules` is omitted, custom modules on the module path may not be included in the module configuration for the classpath launcher. When a classpath application needs a specific named module, resolve that module with `--add-modules`.

## 5. Integration pattern 2: named module using a legacy library as an automatic module

This is often a convenient transition step when an application already has `module-info.java` but a dependency has not yet published an explicit module descriptor.

Example legacy library class:

~~~java
package com.acme.legacy;

public final class LegacyGreeting {
    public String message() {
        return "Hello from legacy library";
    }
}
~~~

Compile the library:

~~~bash
javac --release 17 -d legacy-classes src/com/acme/legacy/LegacyGreeting.java
~~~

Create a manifest with `Automatic-Module-Name`:

~~~text
Manifest-Version: 1.0
Automatic-Module-Name: com.acme.legacy
~~~

Package onto the module path:

~~~bash
jar --create --file mods/legacy-lib.jar --manifest legacy.mf -C legacy-classes .
~~~

The app module declares:

~~~java
module com.acme.app {
    requires com.acme.legacy;
}
~~~

Main class:

~~~java
package com.acme.app;

import com.acme.legacy.LegacyGreeting;

public final class Main {
    public static void main(String[] args) {
        System.out.println(new LegacyGreeting().message());
    }
}
~~~

Compile:

~~~bash
javac --release 17 --module-path mods --module-source-path app-src -d out -m com.acme.app
~~~

Run on Windows:

~~~powershell
java --module-path "mods;out" -m com.acme.app/com.acme.app.Main
~~~

On Linux/macOS:

~~~bash
java --module-path "mods:out" -m com.acme.app/com.acme.app.Main
~~~

Exact stdout:

~~~text
Hello from legacy library
~~~

Maven or Gradle must still declare the dependency to download/build the JAR. `module-info.java` is where the JPMS `requires` relationship is declared. Both dependency graphs need to be consistent.

### When are automatic modules not suitable?

Avoid relying on automatic modules if:

- The JAR contains split packages with another module.
- The module name derived from the filename is unstable.
- The library has many uncontrolled dependencies.
- The library relies on package-private access across multiple JARs.
- A framework needs deep reflection but the module does not have appropriate `opens`.
- You need strict encapsulation or a small runtime image.

Prefer libraries with `module-info.class` and intentionally exported public APIs.

## 6. Integration pattern 3: named module temporarily reading the classpath via ALL-UNNAMED

Sometimes a dependency cannot be moved to the module path right away. Java supports `--add-reads` to create a temporary readability edge from a named module to the unnamed module.

The module descriptor remains:

~~~java
module com.acme.app {
}
~~~

The main class uses the legacy library on the classpath:

~~~java
package com.acme.app;

import com.acme.legacy.LegacyGreeting;

public final class Main {
    public static void main(String[] args) {
        System.out.println(new LegacyGreeting().message());
    }
}
~~~

Compile on Java 17+:

~~~bash
javac --release 17 --class-path legacy.jar --add-reads com.acme.app=ALL-UNNAMED --module-source-path src -d out -m com.acme.app
~~~

Run:

~~~bash
java --module-path out --class-path legacy.jar --add-reads com.acme.app=ALL-UNNAMED -m com.acme.app/com.acme.app.Main
~~~

Exact stdout:

~~~text
Hello from ALL-UNNAMED
~~~

Readability must be granted at both compile time and runtime. Adding the flag only at runtime will not fix compile errors; adding it only at compile time will not establish readability at runtime.

This is an escape hatch for migration or legacy frameworks. It makes the dependency graph less explicit and widens readability to all unnamed modules. Whenever possible, turn the JAR into an automatic module or create an explicit module descriptor.

## 7. Anti-pattern: placing a JAR on the classpath while declaring requires

A common mistake is putting a legacy JAR on the classpath and then writing:

~~~java
module com.acme.app {
    requires com.acme.legacy;
}
~~~

Incorrect compile command:

~~~bash
javac --class-path legacy.jar --module-source-path src -d out -m com.acme.app
~~~

Representative error:

~~~text
error: module not found: com.acme.legacy
module com.acme.app { requires com.acme.legacy; }
~~~

Reason: `requires` only searches for named modules in the module graph. A JAR on the classpath belongs to the unnamed module and therefore cannot be found by the module name `com.acme.legacy`.

Fix this in one of the following ways:

1. Move the JAR to the module path so it becomes an automatic module and keep `requires`.
2. Use an explicit module version of the library.
3. During a transition period, use `--add-reads module=ALL-UNNAMED` and keep the JAR on the classpath.
4. Keep the application on the classpath until dependencies are ready for modularization.

Do not rename the JAR or add an empty `module-info` just to make the error disappear. The descriptor must reflect real dependencies and package boundaries.

## 8. Anti-pattern: placing the same JAR on both paths

Do not add the same library to both the classpath and the module path:

~~~bash
java --module-path "mods;lib/customer.jar" --class-path "lib/customer.jar;app.jar" ...
~~~

One copy on the module path may be resolved as a named/automatic module; the copy on the classpath belongs to the unnamed module. The same class name defined by different modules or class loaders can produce two distinct runtime types.

Possible consequences include:

- Class casts fail even though the class names are identical.
- Service providers are discovered twice or unexpectedly.
- Different versions are loaded depending on the path.
- The module graph and classpath graph do not match.
- Hard to trace which actual class is running.

Each artifact should have one clear runtime location. Inspect the dependency tree and launch command to ensure no duplicate copies of the same library exist on both paths.

## 9. Anti-pattern: moving every JAR to the module path without inspection

A JAR without `module-info.class` can become an automatic module, but not every legacy library is immediately compatible.

Inspect each JAR:

~~~bash
jar --describe-module --file lib/example.jar
~~~

If the output reports an automatic module, note the actual module name and the packages contained in the JAR.

Use `jdeps`:

~~~bash
jdeps --multi-release 17 --print-module-deps lib/example.jar
~~~

Check the application's module graph:

~~~bash
jdeps --module-path mods --check com.acme.app
~~~

Issues to look for:

- Split packages across multiple modules.
- Unstable module names.
- Missing dependencies.
- Internal packages being accessed.
- Reflection into unopened packages.
- Undeclared or undiscovered service providers.
- JARs that rely on classpath-specific behavior.

Do not put an entire `lib` directory onto the module path without knowing its contents. The module path is a set of modules; every JAR is treated as a module, not an anonymous classpath entry.

## 10. Split packages and duplicate classes

### Split package

A split package occurs when the same package is divided across multiple named modules.

Example:

~~~text
module com.acme.core
    contains com.acme.shared

module com.acme.plugin
    contains com.acme.shared
~~~

JPMS does not allow a standard module configuration to resolve two named modules containing the same package. The runtime may report a package conflict or split package error.

Solutions:

- Consolidate the package into a single module.
- Create a shared API module.
- Move implementations into separate packages.
- Merge libraries if an older design intentionally split one package across multiple JARs.

The classpath does not enforce the same split-package rule as named modules, but duplicate classes and package sealing can still cause errors.

### Duplicate class on the classpath

If two JARs contain the same fully qualified class name, the class loader may pick the first one according to classpath search order. Changing the JAR order can cause the application to run a different version of the code.

Do not use classpath ordering as a version selection mechanism. Remove duplicate dependencies or lock a single version.

### Duplicate module name on the module path

If two modules with the same module name appear on the module path, resolution may fail or a module may not be selected as the project intends. Keep module names unique and stable.

## 11. Anti-pattern: using add-reads, add-exports, and add-opens instead of module design

These flags solve different problems:

| Option | Problem solved | Example |
|---|---|---|
| --add-reads | Readability between modules | `com.acme.app` reads `ALL-UNNAMED` |
| --add-exports | Allows access to public types in an unexported package | `java.base/sun.nio.ch=ALL-UNNAMED` |
| --add-opens | Allows deep reflection into a package at runtime | `java.base/java.lang=ALL-UNNAMED` |
| --patch-module | Adds/replaces classes or resources in a module | Used for tests or controlled patching |

Examples:

~~~bash
java --add-reads com.acme.app=ALL-UNNAMED ...
~~~

~~~bash
java --add-exports java.base/sun.nio.ch=ALL-UNNAMED ...
~~~

~~~bash
java --add-opens java.base/java.lang=ALL-UNNAMED ...
~~~

Do not use these flags as a trial-and-error set of options just to make the program run. They alter the module graph or access boundaries, so their reason and scope must be clearly documented.

### exports and opens are not the same

- `exports` allows code in other modules to access public types/public members in a package.
- `opens` allows deeper reflective access at runtime, including non-public members via reflection.
- `opens` does not replace `requires`.
- `add-exports` does not automatically grant deep reflection.
- `add-opens` does not make a public API a valid compile-time dependency.

If a framework needs reflection on DTOs in the `app` module, prefer:

~~~java
module com.acme.app {
    opens com.acme.app.dto to com.acme.json;
}
~~~

If the framework is on the classpath, the target can be `ALL-UNNAMED`. Open only the specific packages that are needed.

## 12. Anti-pattern: confusing module path with class loader

The module path and class loaders are related, but they are not identical.

The module system determines module configuration, readability, exports, and opens. Class loaders are responsible for defining/loading classes. A module can be associated with a class loader; module layers can be created via APIs to build custom runtime configurations.

Do not assume:

- Every module always has its own separate class loader.
- Moving a JAR from the classpath to the module path automatically creates a new class loader as desired.
- Adding a JAR to the module path automatically fixes all class conflicts.
- All dependencies on the module path are resolved without a root module.
- The module path is just the classpath with module names added.

If a plugin application needs class loader isolation, design a dedicated `ModuleLayer`/`ClassLoader` instead of relying on where JARs are placed on the command line.

## 13. Classpath wildcards, environment, and the java -jar command

### Do not rely on wildcard order

A classpath wildcard such as:

~~~bash
java -cp "lib/*" com.acme.app.Main
~~~

loads multiple JARs in the `lib` directory, but the wildcard expansion order is not guaranteed. Do not place two versions of the same dependency in a wildcard directory and expect one version to always be chosen first.

### Limit use of the CLASSPATH environment variable

The `CLASSPATH` environment variable can cause local builds and CI to behave differently. Prefer passing an explicit classpath from Maven, Gradle, or a version-controlled launch script.

### Notes on java -jar

When using:

~~~bash
java -jar app.jar
~~~

the JAR is the primary source of user classes, and classpath options on the command line are ignored. If dependencies are needed, declare them in the manifest `Class-Path`, use a launcher script with `-cp`, or use an appropriate module launch command.

Do not assume that `java -jar app.jar -cp lib/*` will add dependencies as expected.

### OS-dependent separator

| Operating System | Path separator |
|---|---|
| Windows | ; |
| Linux/macOS | : |

In PowerShell, wrap a module path containing semicolons in quotes because a semicolon is a command separator.

## 14. Reflection and ServiceLoader when switching paths

### Reflection

Code running on the classpath may have relied on the broader access it previously had. When a dependency moves to a named module, framework reflection may encounter:

~~~text
java.lang.reflect.InaccessibleObjectException
~~~

Identify the closed module/package and choose a solution:

1. Update the framework to use public APIs or module-aware access.
2. Add a scoped `opens` in the module descriptor.
3. Use `--add-opens` as a temporary compatibility workaround.
4. Redesign the API to avoid deep reflection if possible.

### ServiceLoader

On the classpath, service providers are traditionally registered using:

~~~text
META-INF/services/com.acme.spi.Formatter
~~~

In an explicit module, the service consumer and provider can declare:

~~~java
module com.acme.app {
    uses com.acme.spi.Formatter;
}
~~~

~~~java
module com.acme.json {
    requires com.acme.spi;
    provides com.acme.spi.Formatter
        with com.acme.json.JsonFormatter;
}
~~~

When moving a provider from the classpath to the module path, recheck the service metadata. A classpath application can read a provider module if the module has been resolved and the service is properly configured. Modular applications should explicitly declare `uses`/`provides`.

If using `jlink` to create a runtime image, consider `--bind-services` to link the required service providers.

## 15. Maven and Gradle configuration

Maven/Gradle manage artifact dependencies. JPMS manages module readability and package access. These are two different configuration layers.

### Maven

POM dependency:

~~~xml
<dependency>
    <groupId>com.acme</groupId>
    <artifactId>legacy-lib</artifactId>
    <version>1.4.0</version>
</dependency>
~~~

Module descriptor:

~~~java
module com.acme.app {
    requires com.acme.legacy;
}
~~~

The POM makes the JAR present in the build dependency graph. `requires` declares the JPMS relationship. If the JAR has no `module-info.class`, the module name can come from `Automatic-Module-Name` in the manifest.

When using the Maven Compiler Plugin, check the plugin version and how it infers the module path from `module-info.java`. Ensure the test runtime, surefire/failsafe, and application launcher use the same verified dependency model.

Run:

~~~bash
mvn clean verify
mvn dependency:tree
~~~

### Gradle

For a modular project:

~~~groovy
plugins {
    id 'java'
}

java {
    modularity.inferModulePath = true
}

dependencies {
    implementation files('libs/legacy-lib.jar')
}
~~~

Module descriptor:

~~~java
module com.acme.app {
    requires com.acme.legacy;
}
~~~

Gradle can infer the module path for Java compilation when the project is modular. The automatic module name must be stable; verify with `jar --describe-module`.

For pure classpath projects without `module-info.java`, dependencies are typically on `compileClasspath`/`runtimeClasspath` and code belongs to the unnamed module.

Inspect the dependency graph:

~~~bash
./gradlew dependencies
./gradlew dependencyInsight --dependency legacy-lib --configuration runtimeClasspath
~~~

Do not assume that declaring `implementation`/`api` in Gradle automatically generates `requires` directives. Maintain `module-info.java` and build dependencies together.

## 16. Migration workflow from classpath to module path

Migrate step by step so every error can be traced.

1. **Record the current state:** save the classpath, JDK version, build tool, dependency tree, and test baseline.
2. **Inventory JARs:** use `jar --describe-module` to identify explicit/automatic modules; use `jdeps` to analyze dependencies.
3. **Inspect packages:** look for split packages, duplicate classes, reflective access, and service descriptors.
4. **Pick the first module:** prefer a small library with a clear API and few dependencies.
5. **Move dependencies to the module path:** if not yet modular, use an automatic module with a stable name.
6. **Create `module-info.java`:** declare minimal `requires` and `exports`.
7. **Align compile and runtime:** compiler, test runner, IDE, and launcher must use the same module graph.
8. **Verify services/reflection:** add appropriate `uses`/`provides`/`opens`.
9. **Replace automatic modules:** use explicit module versions when available.
10. **Remove workarounds:** eliminate `add-reads`/`add-exports`/`add-opens` that are no longer needed.
11. **Run integration tests:** verify on the exact target JDK and release environment.
12. **Document the module graph:** document module names and API boundaries.

You do not need to modularize the entire application at once. A system can keep some applications on the classpath while core libraries become explicit modules.

## 17. Diagnosing the module graph and class loading

Useful commands:

### Inspect descriptor

~~~bash
jar --describe-module --file lib/example.jar
~~~

### Inspect module resolution

~~~bash
java --show-module-resolution --module-path mods -m com.acme.app/com.acme.app.Main
~~~

### Validate module path

~~~bash
java --validate-modules --module-path mods
~~~

### List modules

~~~bash
java --list-modules
~~~

### Analyze dependencies

~~~bash
jdeps --module-path mods --check com.acme.app
~~~

~~~bash
jdeps --module-path mods --print-module-deps app.jar
~~~

### View where classes are loaded from

~~~bash
java -Xlog:class+load=info --class-path "app.jar;lib/*" com.acme.app.Main
~~~

On Linux/macOS, replace the separator with a colon. Class loading logs help identify which JAR or directory a class comes from when there are duplicate dependencies.

### View actual compiler commands

With Maven, use `mvn -X` to inspect compiler arguments. With Gradle, use `--info` or `--debug` and check the `compileJava`/`compileTestJava` tasks. Compare the module path across compile, test, and run; a project can compile successfully yet miss a module at runtime.

## 18. Troubleshooting

### error: module not found

A module requires another module, but the JAR is only on the classpath. Move the JAR to the module path with the right module name, or use `--add-reads` as a temporary workaround.

### package is not visible

The consumer module has not declared `requires` on the provider module, or the provider has not exported the package. Check both module descriptors.

### module does not read unnamed module

A named module is importing code that is only on the classpath. Turn the dependency into an automatic/explicit module, or temporarily grant `--add-reads module=ALL-UNNAMED`.

### package is declared in module but module does not export it

The package is not exported. Export only the intended public API; do not export all packages to mask a design flaw.

### split package or package conflict

Two named modules contain the same package. Split the package, consolidate ownership, or create a shared API module.

### NoClassDefFoundError

The JAR may be missing from the runtime path, on the wrong path, or present only at compile time. Compare the compile classpath/module path with the runtime path.

### ClassCastException despite identical class names

The class may have been defined from two different JARs or two different class loaders. Identify the class source with `-Xlog:class+load=info` and remove the duplicate artifact.

### InaccessibleObjectException

Framework reflection is accessing an unopened package. Prefer updating the framework or declaring a scoped `opens`. `--add-opens` should only be a documented compatibility workaround.

### ServiceConfigurationError or provider not found

Check `META-INF/services`, `uses`/`provides`, module resolution, and `--bind-services` when using `jlink`.

### Application runs in IDE but fails in terminal/CI

The IDE may be using a different classpath/module path than the build tool. Export or inspect the launch configuration, checking the JDK, working directory, dependencies, and module flags.

### Two environments pick different dependency versions

Check wildcard classpaths, transitive dependencies, dependency locking, repository metadata, and path ordering. Pin dependency versions and remove duplicate JARs.

## 19. Checklist before mixing classpath and module path

- Know exactly whether each JAR is on the classpath or the module path.
- Do not place the same artifact on both paths.
- Verify module names with `jar --describe-module`.
- Use a stable `Automatic-Module-Name` for legacy libraries.
- Named modules only `requires` modules that can be resolved on the module path.
- Classpath applications resolve named modules with `--add-modules` when needed.
- Do not rely on the module path to automatically make every dependency readable.
- Check `exports`/`opens` before running framework reflection.
- Check for split packages and duplicate classes.
- Check `META-INF/services` and `uses`/`provides`.
- Compile, test, and run use a consistent module graph.
- Limit `--add-reads`/`--add-exports`/`--add-opens` in production.
- Do not use wildcard classpaths when duplicate versions exist.
- Check the Maven/Gradle dependency graph alongside the JPMS graph.
- Run smoke tests on the exact JDK/runtime that will be released.
- Document workarounds and a plan to remove them.

## 20. Key terminology

| Term | Meaning |
|---|---|
| Classpath | List of directories/JARs providing classes for the unnamed module |
| Module path | List of named modules for the module system to resolve |
| Unnamed module | Module containing code without a module descriptor, typically from the classpath |
| Explicit module | Module with `module-info.class` |
| Automatic module | JAR without a descriptor treated as a module when placed on the module path |
| Module graph | Dependency/readability graph between modules |
| Readability | Relationship allowing one module to read another module |
| exports | Exposes a package to other modules |
| opens | Allows deep reflective access into a package |
| ALL-UNNAMED | Target referring to all unnamed modules |
| --add-reads | Adds a readability edge at runtime/compile time |
| --add-exports | Adds a qualified export |
| --add-opens | Opens a package for reflection |
| Split package | A package split across multiple named modules |
| Duplicate class | Same fully qualified class name appearing in multiple places |
| Automatic-Module-Name | Manifest attribute setting a stable module name for a legacy JAR |
| ModuleLayer | Runtime layer containing a module configuration |
| ServiceLoader | Mechanism for discovering service providers |
| jdeps | Java dependency analysis tool |
| jlink | Tool for creating custom runtime images |

The classpath and module path can work together in a Java system, but each path establishes its own module membership and access rules. Choose a clear model for each dependency, use automatic modules as a controlled bridge, declare `requires`/`exports`/`opens` purposefully, and only use `add-reads`/`add-opens` flags when needed for migration. When compile, test, and runtime share a well-understood module graph, the application is easier to diagnose, package, and maintain.

## References

- Oracle JDK 24 — The java Command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/java.html
- Oracle JDK 24 — The javac Command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/javac.html
- Oracle Java SE 24 — java.lang.module package: https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/module/package-summary.html
- Oracle Java SE 24 — ModuleDescriptor and automatic modules: https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/module/ModuleDescriptor.html
- Oracle Java SE 24 — ModuleFinder: https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/module/ModuleFinder.html
- Oracle JDK 24 — jdeps Command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jdeps.html
- OpenJDK — JEP 261: Module System: https://openjdk.org/jeps/261
- Gradle — Building Java Modules: https://docs.gradle.org/current/userguide/java_library_plugin.html
