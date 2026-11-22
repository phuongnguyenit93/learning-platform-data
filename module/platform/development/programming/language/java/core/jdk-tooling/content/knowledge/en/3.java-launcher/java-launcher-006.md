# Module path runtime

## 1. What is the runtime module path?

Since Java 9, the Java Platform Module System (JPMS) allows applications to be organized into named modules with explicit dependency declarations and access rules. When launching a modular application, the Java launcher must locate the required modules, resolve the dependency graph, verify module rules, and only then invoke the application's `main` method.

The **module path** is where the Java launcher searches for modules at runtime. Depending on how it is packaged, a module on the module path can be:

- A modular JAR containing a **module-info.class** file.
- A compiled module directory in exploded module form, with **module-info.class** at the root directory.
- A JAR without a module descriptor, which is treated as an automatic module when placed on the module path.

The module path is typically a directory containing modular JARs or compiled module directories. It can consist of multiple directories separated by the operating system's path separator character. The Java launcher searches these locations for modules by their declared module names and then builds the module graph for the process.

Simple example:

~~~bash
java --module-path mods --module com.example.app/com.example.app.Main
~~~

In this command:

- **--module-path mods** (short form **-p mods**) specifies the directory containing the modules.
- **--module** (short form **-m**) selects the root module to launch and the main class.
- **com.example.app** is the module name, which does not necessarily match the JAR file name.
- **com.example.app.Main** is the fully qualified name of the class containing the `main` method.

The module path belongs to the runtime launch and module loading phase. It is closely related to the module descriptor, but should be distinguished from the compile-time module path configuration used with `javac`.

## 2. Distinguishing the module path and classpath

Both the module path and the classpath help the JVM locate bytecode, but they have different access models.

| Criterion | Module path | Classpath |
|---|---|---|
| Unit of organization | Named modules; may have a module descriptor | Classes and JARs placed in the unnamed module |
| Dependency declaration | Uses **requires** in the module descriptor | Typically based on classpath and build configuration |
| Package exposure | Modules select packages using **exports** | Packages on the classpath have no JPMS exports rules |
| Deep reflection access | Enforces encapsulation rules; typically requires **opens** or package-opening options | Classes in the unnamed module follow a different access model with fewer module restrictions |
| Selecting the class to run | **-m module/class** | **-cp path package.Class** or **-classpath** |

A modular application is typically launched as:

~~~bash
java --module-path mods -m com.example.app/com.example.app.Main
~~~

A traditional classpath application is typically launched as:

~~~bash
java -cp "classes:lib/*" com.example.app.Main
~~~

The colon in the classpath example is the separator on Linux/macOS; Windows uses a semicolon. The module path also uses the operating system's separator. The two launch mechanisms are not arbitrarily interchangeable: placing a JAR on the classpath does not automatically turn it into a named module with a descriptor.

If a legacy library JAR without a module descriptor is placed on the module path, the JVM can treat it as an **automatic module**. This serves as a bridge to help migrate legacy applications to JPMS. If the JAR is on the classpath, its classes belong to the unnamed module. Do not confuse these two cases.

With a named module, other modules can only read it through a readability relationship and can only access public types in exported packages. This is the core difference compared to traditional classpath dependencies.

## 3. What does the module descriptor determine at runtime?

A module declares its name and dependency rules in a **module-info.java** file. After compilation, the descriptor becomes **module-info.class** and is placed at the root of the modular JAR or the root of the module directory.

Example:

~~~java
module com.example.orders {
    requires com.example.customer;
    exports com.example.orders.api;
}
~~~

Common directives:

- **requires**: declares a module dependency. At launch time, the required module must be found and included in the module graph, except in special cases such as `requires static`.
- **requires transitive**: in addition to the current module reading the required module, any module that reads the current module also gains readability to that dependency.
- **exports**: exposes a package so other modules can access public types in that package.
- **exports package to module**: exports a package only to the listed modules.
- **opens**: allows deep reflection access to types in a package; can be opened to all modules or restricted to specific modules.
- **opens package to module**: selectively opens a package to modules that need reflection.
- **uses** and **provides ... with ...**: declares service consumers and providers under the `ServiceLoader` mechanism.

A module can read another module without being allowed to access all packages of that module. **Readability** and **exports** are two distinct conditions: `requires` establishes a readability relationship, while `exports` determines which packages are exposed.

For example, if module A has **requires B** but module B does not export the package that A wants to use, A still cannot access the public types in that package. Conversely, exporting a package does not automatically create a `requires` relationship for the consuming module.

When the Java launcher resolves the module graph, it checks the root modules and declared dependencies. All required modules must be present and must not violate the module system's rules. Errors related to missing modules, module names, dependencies, or conflicts usually appear before the `main` method runs.

## 4. Types of modules that can be placed on the module path

### Explicit named module

This is a module with an explicit module descriptor. A modular JAR contains **module-info.class**; an exploded module has this file in its root directory.

The module name is taken from the descriptor. The JAR file name is just the artifact name and may differ from the module name. Therefore, when writing the **-m** option, use the module name rather than inferring it from the file name.

### Automatic module

A JAR without a module descriptor that is placed on the module path can be treated as an automatic module. Its module name is usually determined by the **Automatic-Module-Name** attribute in the manifest; if absent, the name is derived from the JAR file name according to JPMS rules.

Automatic modules help legacy libraries participate in the module graph during migration. They have more relaxed rules than explicit modules, such as reading all observable modules and exporting all their packages. However, a name derived from the file name can change if the artifact naming changes. For libraries developed by a team that need a stable module name, provide a module descriptor or an appropriate `Automatic-Module-Name` attribute.

### Unnamed module

Classes and JARs on the classpath belong to the unnamed module of the corresponding class loader. The unnamed module has no fixed module name in a descriptor. This is the compatibility model for applications that have not migrated to JPMS.

Named modules do not automatically read the unnamed module. When integrating classpath libraries into a modular application, additional configuration such as **--add-reads module.name=ALL-UNNAMED** may be needed; use this only when you understand the dependency boundaries and plan to remove compatibility flags if possible.

### Exploded module and modular JAR

During development, the compiled output directory can be used directly as an exploded module. When packaging, a module can be built into a modular JAR. Both can be discovered via the module path if their structure and descriptor are valid.

Avoid placing multiple different releases of the same module name on the same module path. Doing so makes version selection depend on lookup and path ordering, making the runtime difficult to reproduce. Keep a single version of each named module in your runtime configuration.

## 5. Two-module application example

The following example has a **com.example.greeter** module providing a greeting API and a **com.example.hello** module consuming that API. Source directory structure:

~~~text
src/
  com.example.greeter/
    module-info.java
    com/example/greeter/api/Greeting.java
  com.example.hello/
    module-info.java
    com/example/hello/Main.java
~~~

### API provider module

File **src/com.example.greeter/module-info.java**:

~~~java
module com.example.greeter {
    exports com.example.greeter.api;
}
~~~

File **src/com.example.greeter/com/example/greeter/api/Greeting.java**:

~~~java
package com.example.greeter.api;

public final class Greeting {
    private Greeting() {
    }

    public static String message() {
        return "Hello from module path";
    }
}
~~~

The module exports the **com.example.greeter.api** package, allowing other modules to read the public `Greeting` type in this package.

### Application module

File **src/com.example.hello/module-info.java**:

~~~java
module com.example.hello {
    requires com.example.greeter;
}
~~~

File **src/com.example.hello/com/example/hello/Main.java**:

~~~java
package com.example.hello;

import com.example.greeter.api.Greeting;

public class Main {
    public static void main(String[] args) {
        System.out.println(Greeting.message());
    }
}
~~~

The application module declares **requires com.example.greeter**. If this declaration is omitted, the module lacks the readability relationship required by JPMS rules to compile against or access the greeter module's API.

### Compiling into exploded modules

From the project directory, create the **mods** output directory, then run:

~~~bash
javac -d mods --module-source-path src -m com.example.greeter,com.example.hello
~~~

Depending on the operating system, you may need to create the **mods** directory beforehand using the appropriate directory creation command. The **--module-source-path src** option tells `javac` where the source tree organized by module name is located; **-m** selects the two modules to compile. The output looks like:

~~~text
mods/
  com.example.greeter/
    module-info.class
    com/example/greeter/api/Greeting.class
  com.example.hello/
    module-info.class
    com/example/hello/Main.class
~~~

### Launching with the module path

Run the command:

~~~bash
java --module-path mods --module com.example.hello/com.example.hello.Main
~~~

Output:

~~~text
Hello from module path
~~~

At runtime, the Java launcher finds the **com.example.hello** module in the **mods** directory, reads its descriptor, discovers that it requires **com.example.greeter**, locates the dependency module, builds the module graph, and invokes the main class. There is no need to specify the greeter JAR separately on the classpath because both modules are on the module path.

### Packaging into modular JARs

You can package each module directory into a JAR:

~~~bash
jar --create --file mlib/com.example.greeter.jar -C mods/com.example.greeter .
jar --create --file mlib/com.example.hello.jar -C mods/com.example.hello .
~~~

The **mlib** directory must be created beforehand. The JARs preserve the compiled module descriptors. Then run:

~~~bash
java --module-path mlib --module com.example.hello/com.example.hello.Main
~~~

The output remains:

~~~text
Hello from module path
~~~

This example shows that the runtime module path can point to a directory containing exploded modules or a directory containing modular JARs. Source layout and packaging format can vary, but module names, descriptors, `requires`, and `exports` relationships must remain consistent.

## 6. Common Java launcher syntax

Syntax for launching a module:

~~~bash
java --module-path <module-path> --module <module-name>[/<main-class>] [application-args...]
~~~

Important options:

| Option | Meaning |
|---|---|
| **--module-path**, **-p** | Specifies the locations containing modules for the runtime to search. |
| **--module**, **-m** | Selects the root module to run, optionally specifying the main class after a slash. |
| **--add-modules** | Adds modules to the set of root modules to resolve, in addition to the default ones. |
| **--limit-modules** | Limits the universe of observable modules when resolving the module graph. |
| **--show-module-resolution** | Displays module resolution diagnostics, useful for troubleshooting. |
| **--list-modules** | Lists observable modules under the current launcher configuration. |
| **--add-reads** | Adds a readability relationship from a source module to a target module. |
| **--add-exports** | Exports a module's package to a target module at runtime. |
| **--add-opens** | Opens a package for deep reflection at runtime. |
| **--patch-module** | Adds or overrides classes/resources in a module for certain testing or compatibility scenarios. |

The **--add-reads**, **--add-exports**, **--add-opens**, and **--patch-module** options intervene in the module graph or encapsulation. They are useful during migration, testing, and handling legacy libraries, but should not become default settings to mask missing module descriptors or incorrect dependencies.

You can instruct the launcher to print module resolution details:

~~~bash
java --show-module-resolution --module-path mods --module com.example.hello/com.example.hello.Main
~~~

Or list observable modules:

~~~bash
java --module-path mods --list-modules
~~~

To inspect the descriptor of a packaged module, use the `jar` tool:

~~~bash
jar --describe-module --file mlib/com.example.hello.jar
~~~

The output describes the module name, packages, and dependency/export directives recognized by the tool. This is how you verify whether a packaged artifact has the expected descriptor.

## 7. Module paths across operating systems

A module path can contain multiple directories. The separator character between entries depends on the operating system:

- Windows: semicolon **;**.
- Linux and macOS: colon **:**.

Example on Linux/macOS:

~~~bash
java --module-path "mods:vendor-mods" --module com.example.hello/com.example.hello.Main
~~~

Example on Windows:

~~~powershell
java --module-path "mods;vendor-mods" --module com.example.hello/com.example.hello.Main
~~~

If a path contains spaces, wrap the entire module path value in quotes appropriate for your shell. The module path only searches for modules according to supported structures; do not assume the launcher recursively scans arbitrary subdirectories. Place modular JARs or module directories directly in the locations searched by the module path.

When running the application in an IDE, check whether the Run/Debug configuration uses the correct module path and module. IDEs may generate a command line that differs from a manual command; inspect the actual command line when results differ between the IDE and the terminal.

In Gradle or Maven, the runtime module path configuration depends on how the plugin/build tool constructs the runtime classpath/module path and how the application is launched. Do not assume every Java task automatically places all dependencies on the module path simply because the project has a `module-info.java` file. Check the run/test configuration, plugins, and actual command line.

## 8. Readability, exports, and reflection at runtime

Three frequently confused concepts:

1. **Readability:** whether the current module has permission to read another module. This relationship is usually declared with `requires`.
2. **Exports:** whether a package is exposed so other modules can access its public types.
3. **Opens:** whether a package is opened for deep reflection, such as when a framework needs to access non-public members.

For example, a library might export its API package without opening its implementation package for deep reflection. This allows applications to call the public API while keeping implementation details encapsulated.

If a framework throws **InaccessibleObjectException** when using reflection, first check which package is closed and which module needs access. A runtime configuration can use:

~~~bash
java --add-opens com.example.app/com.example.app.internal=ALL-UNNAMED --module-path mods --module com.example.app/com.example.app.Main
~~~

This example opens the **com.example.app.internal** package of the **com.example.app** module to the unnamed module. This is a compatibility workaround for classpath libraries that require deep reflection. If the accessor is a specific named module, specify that target module name instead of **ALL-UNNAMED**.

**--add-exports** differs from **--add-opens**. `add-exports` grants access to public types in an unexported package; `add-opens` allows deep reflection into a package. Using the wrong option may not resolve the error. The sustainable solution is usually to use exported APIs or update the library to support the module system properly.

Do not open entire modules or packages just to get an application past an error. Every relaxation of access weakens the encapsulation provided by the module system.

## 9. Services and the module path

JPMS integrates with the Java `ServiceLoader` mechanism. A consumer module can declare:

~~~java
module com.example.app {
    uses com.example.spi.GreetingProvider;
}
~~~

A provider module implementing the service can declare:

~~~java
module com.example.provider {
    requires com.example.spi;
    provides com.example.spi.GreetingProvider
        with com.example.provider.DefaultGreetingProvider;
}
~~~

When using services, ensure both the SPI module and the provider module are placed where the runtime can observe them and resolve them into the module graph according to the launch configuration. The consumer module declares **uses**; the provider module declares **provides ... with ...**. Simply placing a JAR file in an arbitrary directory does not guarantee the provider will be discovered if the JAR is not on the module path or not included in the graph by module resolution.

When service providers need to be bound during module resolution, the launcher provides the **--bind-services** option. Enable it only when the application model genuinely requires that service binding behavior; verify the result with **--show-module-resolution** and test service discovery.

## 10. Common errors when running with the module path

### Could not find or load main class / module

Common causes are an incorrect module path, the module missing from the specified directory, the module name in the command not matching the descriptor, or malformed **-m** syntax. Check the artifact location, inspect the module name with **jar --describe-module**, and verify the actual command line.

### Module not found

A module is declared via `requires`, but the runtime cannot find the corresponding module. Check whether the module path contains that dependency, whether the module name is correct, and whether the dependency is in a valid modular JAR, exploded module, or automatic module format.

### Module does not read / package is not visible

The consuming module has not declared `requires`, or the dependency module's package is not exported. Check the module descriptors on both sides. Avoid fixing this by moving all JARs to the classpath if the application is intended to remain modular.

### Package is not exported

The module was found and is readable, but the needed package has not been exported. Add a selective `exports` directive in the owning module's descriptor if it is meant to be a public API. The `--add-exports` option should only be a deliberate workaround for special runtime cases.

### InaccessibleObjectException

A framework or library is performing deep reflection on a package that is not open. Check the module and package named in the exception. Consider updating the framework or declaring a restricted `opens` directive; if using `--add-opens`, open only the specific package to the specific target module.

### Duplicate module or split package errors

The module path may contain multiple artifacts declaring the same module name or multiple modules with conflicting packages. Inspect the dependency tree, remove duplicate versions, and align library versions. Do not rely on directory ordering to accidentally pick one version.

### Works in the IDE but fails in the terminal or production

IDEs, Gradle/Maven, launch scripts, and containers may use different module paths. Compare the command line, environment variables, module path entries, module list, and launcher options. Also verify the actual runtime JDK version.

### Missing class even though the JAR is in the lib directory

A JAR existing on disk does not mean it is on the module path or classpath. Verify where the dependency is placed and how the launcher picks it up. The module path does not automatically scan nested subdirectories.

## 11. Deployment verification workflow

When a modular application fails to run properly, check in order:

1. Confirm the correct runtime JDK using **java --version**.
2. Inspect the full command line used by the IDE, script, or service to launch the application.
3. Confirm that **--module-path** points to the directory containing the right modular JARs or exploded modules.
4. Confirm the root module name and main class in the **-m** option.
5. Use **jar --describe-module** to inspect the descriptor of each key artifact.
6. Use **--show-module-resolution** to see which modules are found and added to the graph.
7. Check `requires`, `exports`, `opens`, and `uses`/`provides` declarations.
8. Check for duplicate module names, split packages, and dependency versions.
9. Re-run using the exact production runtime configuration, including inside a container if applicable.

When packaging for deployment, keep the module path reproducible: explicitly record the modular JARs, dependency versions, and how the runtime directory is assembled. Avoid placing JARs with duplicate module names across multiple search directories. Do not use a broad module path containing hundreds of unrelated libraries when the application only needs a small set of modules.

## 12. Checklist before handing off a modular application

- [ ] The main module has a valid module descriptor and a clearly defined module name.
- [ ] All required modules are present on the runtime module path.
- [ ] Every package needed by other modules is appropriately exported.
- [ ] Packages requiring deep reflection have restricted `opens` declarations, or the library properly supports JPMS.
- [ ] There are no multiple versions of the same module name or unintended split packages.
- [ ] The launcher command uses `--module-path` and `--module` correctly.
- [ ] Module resolution has been verified with `--show-module-resolution` when needed.
- [ ] IDE, build tool, scripts, and production use compatible module path configurations.
- [ ] The runtime in containers or servers has been tested with the exact set of modules.
- [ ] Dependencies and module path construction steps are documented for reproducibility.

The runtime module path enables Java to run applications according to a module graph with explicit names, dependencies, and access boundaries. When descriptors, the module path, and launcher commands are configured consistently, missing module or package access errors become easier to diagnose while preserving the encapsulation provided by JPMS.