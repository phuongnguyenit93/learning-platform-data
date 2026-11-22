# Checking Whether a Module Exists in the JDK Runtime

When developing modular applications, a module may be declared in `module-info.java` yet be absent from the runtime image used to run the application. This situation often arises when running an application on a custom JRE created with `jlink`, using the wrong JDK, or deploying to a container with a smaller module set than the development environment.

To check accurately, identify **the runtime image actually used by the Java process**, then look up the module in that image's system modules. You can use `java --list-modules`, `java --describe-module`, or the `ModuleFinder.ofSystem()` API.

## Objectives

After this lesson, you will be able to:

- Identify the Java runtime currently used by a terminal or application.
- List the modules contained in a runtime image.
- Look up the descriptor of a specific module.
- Use ModuleFinder to verify the existence of a system module in Java code.
- Distinguish a module present in the runtime image from a module resolved into the boot layer.
- Diagnose errors when a required module is missing from the runtime image.
- Verify the module set before creating a custom runtime with jlink.

## 1. JDK Modules and Runtime Images

The JDK is organized into many modules. Each module provides a named group of APIs or tools, for example:

| Module | General role |
|---|---|
| `java.base` | Foundational APIs such as `java.lang`, `java.util`, basic I/O, and reflection |
| `java.sql` | JDBC API |
| `java.xml` | XML APIs |
| `java.logging` | Standard logging API |
| `java.desktop` | AWT, Swing, and several desktop APIs |
| `java.compiler` | Compiler and language model APIs |
| `jdk.compiler` | The javac compiler tool and compiler implementation |
| `jdk.jlink` | Tool for creating custom runtime images |

A typical JDK installation contains many modules, whereas a runtime image can be built with a smaller set of modules. For instance, developers can use `jlink` to build a runtime containing only the modules the application requires.

Consequently, a module existing in a JDK installed on a development machine does not guarantee that module exists in the runtime image used in production.

### 1.1. Module Name Differs from Package Name

A module name is the module's identifier in the module graph. A package name is a class namespace.

Example:

- Module: `java.sql`
- Package: `java.sql`
- Class: `java.sql.Connection`

In this case the module and package share the same name, though that is not a mandatory rule. One module can contain multiple packages.

When checking a module, use the module name such as `java.sql`. When checking a class, use its fully qualified name such as `java.sql.Connection`.

### 1.2. java.base Is Always Present

Every named module depends directly or indirectly on `java.base`. It is Java's foundational module and is always present in a valid runtime image.

Other modules such as `java.sql`, `java.xml`, `java.desktop`, `jdk.compiler`, or `jdk.jlink` may be absent from a minimal runtime image.

## 2. Identifying the Runtime in Use

Before checking modules, identify the exact Java executable. A machine may have multiple JDK versions, multiple JREs, or a custom runtime image installed.

### 2.1. Checking the Java Version

Run:

~~~bash
java --version
~~~

Example output:

~~~text
openjdk 21.0.2 2024-01-16
OpenJDK Runtime Environment
OpenJDK 64-Bit Server VM
~~~

This command reports the version of the `java` executable found by the shell. It does not show the full installation path.

### 2.2. Checking the Executable Path

On Windows PowerShell:

~~~powershell
Get-Command java -All | Select-Object Source
Get-Command javac -All | Select-Object Source
~~~

Or in Command Prompt:

~~~cmd
where java
where javac
~~~

On Linux or macOS:

~~~bash
command -v java
command -v javac
~~~

If multiple results appear, the shell may be picking a different Java installation than the one used by an IDE or service. Check the specific executable rather than relying solely on the `JAVA_HOME` value.

You can invoke Java directly inside `JAVA_HOME`:

On Windows:

~~~powershell
& "$env:JAVA_HOME\bin\java.exe" --version
& "$env:JAVA_HOME\bin\java.exe" --list-modules
~~~

On Linux or macOS:

~~~bash
"$JAVA_HOME/bin/java" --version
"$JAVA_HOME/bin/java" --list-modules
~~~

### 2.3. Checking java.home Inside the Application

If the application runs via an IDE, service manager, container, or custom script, the process's runtime may differ from the terminal's runtime.

Print runtime details directly inside the application:

~~~java
public class RuntimeInfo {
    public static void main(String[] args) {
        System.out.println("java.version = "
            + System.getProperty("java.version"));

        System.out.println("java.home = "
            + System.getProperty("java.home"));

        System.out.println("java.vendor = "
            + System.getProperty("java.vendor"));

        System.out.println("Runtime.version = "
            + Runtime.version());
    }
}
~~~

`java.home` shows the runtime directory used by the running JVM. This is useful evidence when comparing terminal checks against the application's actual environment.

## 3. Listing Modules in the Runtime Image

### 3.1. Using java --list-modules

Basic command:

~~~bash
java --list-modules
~~~

Partial example output:

~~~text
java.base@21.0.2
java.compiler@21.0.2
java.datatransfer@21.0.2
java.desktop@21.0.2
java.logging@21.0.2
java.sql@21.0.2
java.xml@21.0.2
jdk.compiler@21.0.2
jdk.jlink@21.0.2
~~~

The name before the `@` character is the module name. The part after `@` is typically the module version supplied by the runtime.

When run without adding an application module path, the list shows the system modules observable from the current runtime image. This is a quick check to verify whether a JDK module is available.

### 3.2. Searching for a Specific Module

On Windows PowerShell:

~~~powershell
java --list-modules | Select-String '^java.sql(@|$)'
~~~

On Command Prompt:

~~~cmd
java --list-modules | findstr /B java.sql
~~~

On Linux or macOS:

~~~bash
java --list-modules | grep '^java.sql@'
~~~

If a match is printed, the current runtime image contains the `java.sql` module. If nothing is printed, double-check the Java executable and runtime image being inspected.

Example checking the compiler module:

~~~bash
java --list-modules | grep '^jdk.compiler@'
~~~

On Windows, `grep` can be replaced with `Select-String` or `findstr`.

### 3.3. Interpreting the Output Properly

If the output contains:

~~~text
java.sql@21.0.2
~~~

That indicates the system module `java.sql` is present in the queried runtime image.

If it produces nothing:

~~~text
~~~

Do not immediately conclude that the entire JDK is broken. The runtime may be a custom image containing only required modules. Check `java.home`, the executable path, and how the runtime image was built.

## 4. Viewing a Module's Descriptor with java --describe-module

Once you confirm a module exists, use:

~~~bash
java --describe-module java.sql
~~~

The command displays the module descriptor, including information such as:

- Module name.
- Packages contained or exported.
- `requires` dependencies.
- Services listed under `uses`.
- Providers listed under `provides`, if any.

Shortened example output might contain:

~~~text
java.sql
exports java.sql
exports javax.sql
requires java.logging
requires java.transaction.xa
requires java.base mandated
uses java.sql.Driver
~~~

Actual output depends on the JDK version. Use it to confirm the module name, packages, and dependencies published by the module.

You can check other modules:

~~~bash
java --describe-module java.xml
java --describe-module java.logging
java --describe-module jdk.compiler
~~~

If the module is not found in the runtime image, the command may report a module lookup error. In that case, go back and verify the module list and Java executable.

### 4.1. Distinguishing from jar --describe-module

The two commands serve different purposes:

~~~bash
java --describe-module java.sql
~~~

Queries a module in the current Java runtime environment.

~~~bash
jar --describe-module --file libs/payment.jar
~~~

Queries the descriptor or module name of a specific JAR file.

A JAR on disk may be an explicit module or an automatic module. The JAR's existence does not prove a module of the same name is a JDK system module.

## 5. Checking via the Java API with ModuleFinder.ofSystem()

If you need to check in code, use the `java.lang.module.ModuleFinder` API.

`ModuleFinder.ofSystem()` creates a finder for the system modules of the current runtime image. You can call `find(moduleName)` to check a specific module.

Example:

~~~java
import java.lang.module.ModuleFinder;
import java.lang.module.ModuleReference;
import java.util.Optional;

public class CheckSystemModule {
    public static void main(String[] args) {
        String moduleName = "java.sql";

        Optional<ModuleReference> reference =
            ModuleFinder.ofSystem().find(moduleName);

        System.out.println(
            moduleName + " exists: " + reference.isPresent()
        );

        reference.ifPresent(module ->
            System.out.println(
                "Found module: " + module.descriptor().name()
            )
        );
    }
}
~~~

If `find()` returns a present `Optional`, the module was found in the system modules of the current runtime image.

You can replace `java.sql` with `java.xml`, `java.desktop`, `jdk.compiler`, or any other module to inspect.

### 5.1. Checking Multiple Modules

Example checking a list:

~~~java
import java.lang.module.ModuleFinder;
import java.util.List;

public class CheckSeveralModules {
    public static void main(String[] args) {
        List<String> names = List.of(
            "java.base",
            "java.sql",
            "java.xml",
            "java.desktop",
            "jdk.compiler"
        );

        ModuleFinder finder = ModuleFinder.ofSystem();

        for (String name : names) {
            boolean exists = finder.find(name).isPresent();
            System.out.printf("%-18s %s%n", name, exists);
        }
    }
}
~~~

Results depend on the running runtime image. A custom image might have `java.base` and `java.sql` while missing `java.desktop` or `jdk.compiler`.

### 5.2. Inspecting the Descriptor

After finding the module, you can read its descriptor:

~~~java
ModuleFinder.ofSystem()
    .find("java.sql")
    .ifPresent(reference -> {
        var descriptor = reference.descriptor();

        System.out.println("Name: " + descriptor.name());
        System.out.println("Packages: " + descriptor.packages());
        System.out.println("Requires: " + descriptor.requires());
        System.out.println("Exports: " + descriptor.exports());
    });
~~~

This snippet lets you inspect the module structure provided by the runtime without manually opening JMOD files.

## 6. Being Present in the Runtime Image vs. Being Resolved Are Different States

This is a crucial point when debugging JPMS.

A system module may exist in the runtime image yet not be included in the running application's module graph. A module is resolved only when it is a root module or is pulled in indirectly via appropriate dependencies or service binding.

There are two different checks:

| Question | How to check |
|---|---|
| Does the runtime image provide the module? | `ModuleFinder.ofSystem().find(name)` or `java --list-modules` |
| Has the module been resolved into the boot layer? | `ModuleLayer.boot().findModule(name)` |

Example:

~~~java
import java.lang.module.ModuleFinder;

public class ModuleState {
    public static void main(String[] args) {
        String name = "java.sql";

        boolean inRuntimeImage =
            ModuleFinder.ofSystem().find(name).isPresent();

        boolean inBootLayer =
            ModuleLayer.boot().findModule(name).isPresent();

        System.out.println("In runtime image: " + inRuntimeImage);
        System.out.println("In boot layer: " + inBootLayer);
    }
}
~~~

If `inRuntimeImage` is `true` while `inBootLayer` is `false`, the module is available in the runtime image but was not resolved into the process's boot layer.

To have the module resolved at launch, the application can declare `requires` in its descriptor or add the appropriate root module via the `--add-modules` option.

Example:

~~~bash
java --add-modules java.sql --module-path mods -m com.acme.app/com.acme.app.Main
~~~

There is no need to add `--add-modules` if the application already declares the required dependency using `requires`.

## 7. Inspecting the Application's Actual Module Graph

When you need to see which modules are actually resolved at startup, use:

~~~bash
java --show-module-resolution --module-path mods -m com.acme.app/com.acme.app.Main
~~~

The `--show-module-resolution` option prints resolution details, including the modules chosen as roots and resolved dependencies.

Compare the three commands:

~~~bash
java --list-modules
java --describe-module java.sql
java --show-module-resolution --module-path mods -m com.acme.app/com.acme.app.Main
~~~

- `--list-modules`: lists observable modules in the invocation's runtime/module path.
- `--describe-module`: views a module's descriptor.
- `--show-module-resolution`: views the resolved module graph when running a specific application.

Do not use `--show-module-resolution` output to conclude that a module is absent from the runtime image. A module may be available yet not selected into the application's graph.

## 8. When a Required Module Does Not Exist in the Runtime

Suppose the app module declares:

~~~java
module com.acme.app {
    requires java.sql;
}
~~~

Yet the deployment runtime image lacks `java.sql`. During module graph resolution, the JVM cannot find the mandatory dependency and the application may fail with an error like:

~~~text
java.lang.module.FindException:
Module java.sql not found, required by com.acme.app
~~~

How to handle it:

1. Identify the exact runtime image the application is running on.
2. Use `java --list-modules` to verify the missing module.
3. Check whether the module is genuinely required by application features.
4. If needed, rebuild the runtime image to include that module.
5. Re-run the application using the newly built runtime image.

You cannot fix a missing system module merely by adding a `requires` line. `requires` declares a dependency; the runtime image must still provide the corresponding module.

## 9. Creating a Custom Runtime with Required Modules Using jlink

`jlink` builds a custom runtime image from available modules. This tool is suitable when packaging a runtime smaller than a full JDK.

Example:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods"       --add-modules com.acme.app,java.sql       --output app-runtime
~~~

In the example:

- `$JAVA_HOME/jmods` provides the JDK modules from the JDK in use.
- `mods` provides the application's modules.
- `--add-modules` selects the root modules for the runtime image.
- `--output` specifies the created runtime directory.

On Windows, the separator between module path locations is a semicolon:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.acme.app,java.sql --output app-runtime
~~~

If a specified module is absent from the module finder sources, `jlink` reports an error. If the app already declares `requires java.sql;`, that dependency is also included during resolution when building the image from the app root.

After building the image, inspect the new runtime itself:

~~~bash
app-runtime/bin/java --list-modules
~~~

On Windows:

~~~powershell
.\app-runtime\bin\java.exe --list-modules
~~~

This step confirms the created runtime image contains the desired modules. Do not check only the JDK used to run `jlink`, because the output image's module set can be smaller than the source JDK.

## 10. Using jdeps to Find Modules the Application Needs

When unsure which system modules an application needs, you can use `jdeps` for static dependency analysis.

For a regular JAR:

~~~bash
jdeps --print-module-deps --class-path "libs/*" app.jar
~~~

For a named module:

~~~bash
jdeps --print-module-deps --module-path mods --module com.acme.app
~~~

The output can be used as input to `jlink --add-modules`.

Shortened example output:

~~~text
java.base,java.logging,java.sql
~~~

Notes:

- `jdeps` analyzes dependencies inferable from bytecode.
- Reflection, class names read from configuration, plugins, and dynamic class loading may not be fully detected.
- Also verify modules used by the application via `ServiceLoader` or dynamic loading mechanisms.
- Always run tests on the final runtime image.

## 11. Common Errors and Misconceptions

### 11.1. The Terminal Has the Module, Yet the Application Still Reports It Missing

The usual cause is that the terminal and the application use two different Java executables. Check `java.home` inside the process and compare it with the path of the `java` command in the terminal.

### 11.2. The Module Exists in the JDK, Yet Is Absent from the Custom Runtime

A full JDK and a runtime image created with `jlink` can contain different module sets. Run `--list-modules` using the custom runtime's executable to verify.

### 11.3. The Module Is Unresolved Yet Actually Present

`java --list-modules` may list the module while `ModuleLayer.boot().findModule(name)` returns empty. This can be normal when the module has not been pulled into the startup graph.

### 11.4. Confusing a Module with a Package

A package may belong to a module without being exported. Finding the module does not guarantee consuming modules can access every package inside.

### 11.5. Confusing a JAR with a System Module

A library JAR on the module path may be an explicit named module or an automatic module. That does not make it a module of the JDK runtime image. Use `ModuleFinder.ofSystem()` to check system modules; use `ModuleFinder.of(path)` to locate modules from external sources.

## 12. Practical Verification Workflow

When tasked with verifying whether a module exists in a JDK runtime, follow this sequence:

1. Obtain the path to the Java executable running the application.
2. Print `java.home` and `java.version` from within the process itself if possible.
3. Run `java --list-modules` using that exact executable.
4. Search for the exact module name in the list.
5. Use `java --describe-module <module-name>` to inspect the descriptor.
6. If programmatic verification is needed, use `ModuleFinder.ofSystem().find(name)`.
7. If you need to know whether the module is resolved, check `ModuleLayer.boot().findModule(name)`.
8. If a module is missing in a custom runtime, update the root list for `jlink`, then rebuild and re-verify the image.
9. Run the application and observe `--show-module-resolution` to confirm the actual module graph.

## 13. Self-Check

**Scenario 1:** `java --list-modules` displays `java.sql@21.0.2`. What module name should be used in `requires`?

**Answer:** `java.sql`. The portion after `@` is version information.

**Scenario 2:** `ModuleFinder.ofSystem().find("java.sql")` is present, yet `ModuleLayer.boot().findModule("java.sql")` is empty. Is the runtime broken?

**Answer:** Not necessarily. The module exists in the runtime image, but has not been resolved into the process's boot layer.

**Scenario 3:** Why does `java --list-modules` on a development machine show `java.desktop`, while the custom runtime does not?

**Answer:** The custom runtime may have been built with jlink using a smaller set of root modules that does not include dependencies leading to `java.desktop`.

**Scenario 4:** `module-info.java` has `requires java.xml;`, yet the application reports module not found. What should you check?

**Answer:** Check the actual runtime image, the Java executable, and the output of `java --list-modules`. If the image lacks `java.xml`, rebuild the image to include that module.

**Scenario 5:** Which command displays the descriptor of the `java.sql` system module?

**Answer:** `java --describe-module java.sql`.

**Scenario 6:** Which API should you use to check inside a Java application whether a system module exists?

**Answer:** Use `ModuleFinder.ofSystem().find(moduleName)` and check the returned `Optional`.

**Scenario 7:** Which option reveals which modules are actually resolved when running an application?

**Answer:** Use `--show-module-resolution` in the launch command.

When checking JDK modules, always tie your findings to the exact runtime image running the application. Listing modules confirms availability; viewing descriptors confirms module contents; checking the boot layer confirms resolution; and module resolution logs show how the application's graph is formed.
