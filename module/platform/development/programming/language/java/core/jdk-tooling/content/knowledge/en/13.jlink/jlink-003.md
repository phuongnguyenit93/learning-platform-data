# Selecting Required Modules When Creating a Runtime Image with `jlink`

`jlink` creates a runtime image from a selected set of modules and their required dependencies. Selecting the right modules ensures the image contains enough APIs for the application to run, while avoiding bundling all JDK modules into the deployment.

When selecting modules, you need to distinguish between **root modules** and **dependent modules**. Root modules are those directly requested in `--add-modules`; the linker automatically resolves `requires` relationships and adds mandatory dependencies. Modules loaded dynamically via reflection, string-based class names, service providers, or JNI may need separate consideration because static analysis cannot always detect them.

A reliable workflow is usually: read the module descriptor, analyze dependencies with `jdeps`, select root modules with `--add-modules`, decide whether service binding is needed, link with `jlink`, and then test the image against real functional flows.

## 1. Root Modules and Dependency Closure

In JPMS, a module declares its relationships with other modules using `requires` in `module-info.java`.

For example:

~~~java
module com.example.audit {
    requires java.logging;
    requires java.sql;
}
~~~

The application requires two platform modules, `java.logging` and `java.sql`. Each of these modules may in turn depend on other modules. During linking, `jlink` resolves the module graph and includes the required dependencies in the image.

Key concepts to distinguish:

- **Root module:** a module specified directly in `--add-modules`.
- **Required module:** a module declared by another module via `requires`.
- **Transitive dependency:** a dependency pulled in further through required module relationships.
- **Observable module:** a module that the module finder can see on the module path or in the JDK system.
- **Runtime image:** the set of linked modules along with the JVM and required runtime components.

For example:

~~~text
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.example.audit --output audit-image
~~~

`com.example.audit` is the root. The modules it strictly requires, such as `java.logging` and `java.sql`, are resolved automatically. `java.base` is also always Java's fundamental base module.

You do not need to manually list every dependency already properly declared in `module-info.java`. However, modules loaded indirectly or used in ways tools cannot analyze may need to be added explicitly.

## 2. Reading the Module Descriptor Before Selecting

`module-info.java` is the most important source of information about static module relationships.

| Directive | Meaning for Module Selection |
|---|---|
| `requires other.module` | Declares a mandatory dependency; that module must be resolved |
| `requires transitive other.module` | Dependency read indirectly by other modules that read the current module |
| `requires static other.module` | Dependency needed at compile time but potentially optional at runtime |
| `exports package.name` | Allows other modules to access public packages; does not pull in additional modules |
| `opens package.name` | Allows deep reflective access; does not pull in additional modules |
| `uses service.Type` | Declares that the module uses a service |
| `provides service.Type with Impl` | Declares that the module provides an implementation for a service |

### 2.1. `requires` and `requires transitive`

`requires` establishes readability and dependency relationships between modules. If an application module uses APIs from `java.sql`, declare `requires java.sql` so the compiler and runtime can resolve that module.

`requires transitive` also makes the dependency readable indirectly by other modules that read the current module. This commonly appears in public API modules when a type from the dependency appears in the API signature.

With `jlink`, mandatory dependencies are resolved according to the module graph. Declare relationships properly in the module descriptor rather than trying to fix missing dependencies by adding many modules to the command line.

### 2.2. `requires static`

`requires static` represents an optional dependency at runtime that is still needed when compiling the declaring module. If the corresponding feature is actually used at runtime, ensure that module is present in the image by adding it as a root or through another mandatory relationship.

Do not interpret `requires static` as a guarantee that the module is always excluded from the image. If the module is added directly or pulled in by another dependency, it can still appear.

### 2.3. `exports`, `opens`, `uses`, and `provides`

`exports` and `opens` control package access; they do not replace `requires` and do not select modules on their own.

`uses` and `provides` describe services. If the application uses `ServiceLoader`, you need to consider both the module declaring `uses` and the module providing the implementation. Depending on the linking configuration, you may need `jlink --bind-services` to include provider modules and their dependencies in the image.

## 3. Using `jdeps` to Discover Dependencies

`jdeps` is a tool for analyzing dependencies of Java class files, JARs, and modules. It helps identify platform modules referenced in bytecode and module relationships recorded by the compiler.

For a modular JAR on the module path, you can view dependencies in a human-readable format:

~~~text
jdeps --module-path mods --list-deps --module com.example.audit
~~~

To get a comma-separated list of modules:

~~~text
jdeps --module-path mods --print-module-deps --module com.example.audit
~~~

The `--print-module-deps` output can be used as input when constructing the linking command. For the example application in this article, you should see the direct modules `java.logging` and `java.sql`, along with `java.base`; the exact list may depend on bytecode, module descriptors, and the JDK version.

Useful options:

| Option | Purpose |
|---|---|
| `--list-deps` | Lists dependencies in a human-readable format |
| `--list-reduced-deps` | Shows reduced dependencies based on module relationships |
| `--print-module-deps` | Prints a CSV list of modules, convenient for `jlink` |
| `--module-path` | Specifies where to find modules |
| `--module` | Analyzes the named module |
| `--class-path` | Adds a classpath when analyzing applications or libraries |
| `--jdk-internals` | Detects dependencies on JDK internal APIs |
| `--ignore-missing-deps` | Continues analysis when dependencies are missing; use with caution |
| `--multi-release` | Selects the entry version when analyzing a multi-release JAR |

### 3.1. Analyzing JAR Applications

For a JAR that is not yet a named module, you can analyze platform dependencies:

~~~text
jdeps --print-module-deps app.jar
~~~

If the application has external library dependencies, add the appropriate classpath.

Windows PowerShell:

~~~powershell
jdeps --class-path "lib/*" --print-module-deps app.jar
~~~

macOS/Linux:

~~~sh
jdeps --class-path 'lib/*' --print-module-deps app.jar
~~~

The output helps identify which JDK modules the bytecode references. However, `jdeps` does not turn a classpath application into a named module. `jlink` requires modules that can be resolved on the module path; the application must be modularized or packaged as a proper named module before linking.

### 3.2. Limitations of Static Analysis

`jdeps` analyzes references it can see in class files and module descriptors. It may not fully detect dependencies chosen at runtime, such as:

- `Class.forName("com.vendor.Driver")` with class names in strings.
- Reflection or frameworks scanning packages to find implementations.
- Provider or plugin names read from configuration files.
- Native libraries loaded via JNI or `System.loadLibrary`.
- Resources and configuration files that determine which modules/plugins are loaded.

Do not rely solely on `jdeps` output to claim an image is sufficient for all features. Combine static analysis with module descriptors, framework configurations, service lists, and real-world testing.

## 4. Selecting Root Modules with `jlink --add-modules`

Basic syntax:

~~~text
jlink --module-path module-path --add-modules module-name[,module-name...] --output image-directory
~~~

`--add-modules` accepts one or more module names as roots. The linker resolves mandatory dependencies of the root modules and creates the image.

Example:

~~~text
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.example.audit --output audit-image
~~~

Where:

- `$JAVA_HOME/jmods` contains the JDK's JMOD files.
- `mods` contains the application's modular JARs or JMODs.
- `com.example.audit` is the root module.
- `audit-image` is the output runtime image directory.

If the application has additional dynamically loaded modules, such as a driver or plugin, you can add them to the root list:

~~~text
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.example.audit,com.vendor.driver --output audit-image
~~~

Only add modules that are genuinely needed and present on the module path. The module name must be the name from the module descriptor, which does not necessarily match the JAR filename.

## 5. Selecting Modules via Service Binding

Java's `ServiceLoader` allows a module to use a service without depending directly on a specific implementation.

The application module can declare:

~~~java
module com.example.audit {
    uses com.example.spi.AuditProvider;
}
~~~

The provider module declares:

~~~java
module com.example.audit.provider {
    requires com.example.audit.api;
    provides com.example.spi.AuditProvider
        with com.example.provider.DefaultAuditProvider;
}
~~~

In practical designs, the service API is often placed in a separate module so both the application and the provider can read it.

Option:

~~~text
jlink --bind-services --module-path "$JAVA_HOME/jmods:mods" --add-modules com.example.audit --output audit-image
~~~

`--bind-services` instructs the linker to find matching service provider modules among observable modules, and then link the providers along with their dependencies. This is useful when an application uses services and you do not want to manually list every implementation.

Considerations:

- Providers must be present on the module path or among observable system modules.
- The consuming module must declare the appropriate `uses` directive.
- The provider module must declare `provides` for the exact service type.
- Service binding can pull additional modules and dependencies into the image, increasing its size.
- Without service binding, you may have to add provider modules explicitly via `--add-modules`.

After linking, inspect the image and run real functionality to confirm providers are discovered.

## 6. Limiting Observable Modules with `--limit-modules`

`--limit-modules` restricts the set of modules the linker can observe and resolve. It is commonly used to control the module universe during resolution.

Illustrative example:

~~~text
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.example.audit --limit-modules com.example.audit,java.base,java.logging,java.sql --output audit-image
~~~

This option does not replace `--add-modules`:

- `--add-modules` selects the root modules to include in the image.
- `--limit-modules` restricts the set of modules that can be considered for resolution.

If the limit excludes a mandatory dependency, the linker will be unable to resolve the module graph. When using `--limit-modules`, account for transitive dependencies of the root modules and retest the image.

In many applications, explicitly specifying root modules with `--add-modules` is sufficient. Only add `--limit-modules` when there is a specific reason to constrain the module universe.

## 7. Special Selectors Supported by jlink

For `jlink`, the documented special selector for the `--add-modules` option is `ALL-MODULE-PATH`. This selector instructs the linker to include all observable modules on the module path in the root set for resolution. It is useful for exploration or creating experimental images, though it typically makes the runtime image larger than necessary.

| Value | Meaning in jlink |
|---|---|
| Explicit module name, e.g. `java.logging` | Selects that module as a root; the linker continues resolving its dependency closure |
| `ALL-MODULE-PATH` | Selects all observable modules on the module path as roots |

Do not copy `ALL-SYSTEM` or `ALL-DEFAULT` selectors from `javac` documentation into `jlink` commands. Syntax and supported selectors depend on the specific tool; verify with `jlink --help` for your exact JDK and its corresponding man page.

Example:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules ALL-MODULE-PATH --output all-modules-image
~~~

The command above intentionally creates an image from all modules visible on the module path. In production, prefer listing only the root modules actually needed, then inspect dependencies and test the image on the target environment.

## 8. Complete Example: Analyzing and Selecting Modules for Java 17

We will create a modular application that uses the logging and SQL APIs. The goal is to select the platform modules, create a runtime image, and run the application using that image.

Structure:

~~~text
project/
  src/
    module-info.java
    com/
      example/
        audit/
          Main.java
  out/
  mods/
  audit-image/
~~~

### 8.1. Module Declaration

File `src/module-info.java`:

~~~java
module com.example.audit {
    requires java.logging;
    requires java.sql;
}
~~~

File `src/com/example/audit/Main.java`:

~~~java
package com.example.audit;

import java.sql.DriverManager;
import java.util.logging.Logger;

public class Main {
    public static void main(String[] args) {
        System.out.println(
                "Logging module: " + Logger.class.getModule().getName());
        System.out.println(
                "SQL module: " + DriverManager.class.getModule().getName());
    }
}
~~~

The program prints the module names containing the two APIs being used. It does not open a database connection, so it can run standalone without a database driver.

### 8.2. Compiling and Packaging the Modular JAR

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out, mods | Out-Null
javac --release 17 -d out src/module-info.java src/com/example/audit/Main.java
jar --create --file mods/com.example.audit.jar -C out .
~~~

macOS/Linux:

~~~sh
mkdir -p out mods
javac --release 17 -d out src/module-info.java src/com/example/audit/Main.java
jar --create --file mods/com.example.audit.jar -C out .
~~~

The JAR has `module-info.class` at its root, so it can be resolved as a named module. Inspect the descriptor:

~~~text
jar --describe-module --file mods/com.example.audit.jar
~~~

Test running before creating the image:

~~~text
java --module-path mods -m com.example.audit/com.example.audit.Main
~~~

Stdout:

~~~text
Logging module: java.logging
SQL module: java.sql
~~~

### 8.3. Analyzing Dependencies with `jdeps`

List dependencies:

~~~text
jdeps --module-path mods --list-deps --module com.example.audit
~~~

Get a CSV list:

~~~text
jdeps --module-path mods --print-module-deps --module com.example.audit
~~~

For this application, you should see the two directly declared modules `java.logging` and `java.sql`; `java.base` is the base module. The output may show additional dependencies depending on the module graph and the JDK in use.

### 8.4. Creating a Runtime Image with Minimal Root Modules

On macOS/Linux:

~~~sh
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.example.audit --launcher audit=com.example.audit/com.example.audit.Main --output audit-image
~~~

On Windows PowerShell:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.example.audit --launcher audit=com.example.audit/com.example.audit.Main --output audit-image
~~~

Specify `com.example.audit` as the root. `jlink` automatically resolves `java.logging`, `java.sql`, and their mandatory dependencies. There is no need to add all JDK modules.

### 8.5. Running and Inspecting the Image

Linux/macOS:

~~~sh
./audit-image/bin/audit
./audit-image/bin/java --list-modules
~~~

Windows PowerShell:

~~~powershell
.\audit-image\bin\audit.exe
.\audit-image\bin\java.exe --list-modules
~~~

Stdout from the application launcher:

~~~text
Logging module: java.logging
SQL module: java.sql
~~~

The image's module list displays the application module along with its linked dependencies. The exact names and versions in `--list-modules` depend on the JDK version used to build the image.

## 9. When Do You Need to Add Modules Explicitly?

Static dependencies declared in the module descriptor are normally resolved automatically by the linker. However, some features require additional modules because their relationships cannot be fully inferred from `requires`.

### 9.1. Loading Classes by Name

Example:

~~~java
Class<?> driver = Class.forName("com.vendor.Driver");
~~~

Because the class name is a string, static analysis may not determine which module contains the class. If the module containing the driver must be in the image, add it to `--add-modules` or configure the appropriate service provider.

### 9.2. Plugins and Frameworks

Frameworks may discover implementations through configuration, package scanning, reflection, or registries. Identify the plugin modules actually used in production and place them on the module path; then select roots or use service binding according to the mechanism the framework supports.

### 9.3. JNI and Native Libraries

If the application calls native libraries, check the module containing the library and configure the corresponding native path. `jdeps` cannot infer all native dependencies from Java calls. You must verify binaries per OS/architecture and run smoke tests on the image.

### 9.4. Resources and Configuration Files

Module selection does not automatically guarantee that all external resources are copied into the image. Verify whether resources are inside the modular JAR or packaged through a separate deployment step. If resources determine which modules/plugins are loaded, check those corresponding modules.

## 10. Selecting Modules for Classpath Applications and Automatic Modules

`jlink` works with named modules that can be resolved on the module path. An application running only on the classpath belongs to the unnamed module; you cannot simply pass that classpath JAR to `--add-modules` and expect `jlink` to package it as a named module.

If you have an unmodularized JAR:

1. Use `jdeps` to analyze dependencies and detect internal APIs.
2. Determine the library's module name and packages.
3. Create or add an appropriate `module-info.java`.
4. Verify `requires`, `exports`, `opens`, `uses`, and `provides`.
5. Package it as a named module, then place it on the module path for `jlink`.

Automatic modules can be useful when running an application on the module path in certain configurations, but they are not suitable inputs for `jlink` to create a runtime image. Use proper named modules with valid module descriptors.

## 11. Optimizing the Image After Module Selection

After identifying the required modules, you can reduce auxiliary components using `jlink` options:

| Option | Effect |
|---|---|
| `--strip-debug` | Strips debug information from linked modules |
| `--no-header-files` | Excludes header files from the image |
| `--no-man-pages` | Excludes man pages from the image |
| `--compress` | Compresses resources/modules at supported levels |
| `--bind-services` | Adds provider modules for service binding |
| `--launcher` | Creates a launcher for a module and main class |
| `--list-plugins` | Lists available linker plugins |

Example:

~~~text
jlink --strip-debug --no-header-files --no-man-pages --module-path "$JAVA_HOME/jmods:mods" --add-modules com.example.audit --output audit-image
~~~

Only strip headers, man pages, or debug metadata if your operational workflow does not need them. Size reduction must not remove components that the application or operations team needs for diagnostics.

## 12. Common Errors When Selecting Modules

### `Module ... not found`

**Cause:** the module path is missing JDK `jmods` or the directory containing application modules; module name confused with filename.

**Resolution:** check `--module-path`, use `jar --describe-module` or `jmod describe` to confirm the module name, then rerun `jdeps`.

### `Module ... does not read ...` or Package Not Exported

**Cause:** the module descriptor is missing `requires`, or the module providing the API has not exported the required package.

**Resolution:** fix the module descriptor on the appropriate API provider/consumer side. `--add-modules` does not replace readability or export relationships.

### Application Runs on Full JDK but Fails in Image

**Cause:** dynamically loaded modules, service providers, native libraries, or resources were not included in the image.

**Resolution:** review `jdeps`, module descriptors, framework configuration, `uses`/`provides`, and add the needed modules. Retest real functionality using the launcher inside the image.

### Missing Service Provider

**Cause:** the provider module was not linked or the service declaration is incorrect.

**Resolution:** confirm the consumer module has `uses`, the provider has `provides`, the provider is on the module path, and try `--bind-services`. If necessary, add the provider module explicitly.

### Image Larger Than Expected

**Cause:** selecting `ALL-MODULE-PATH` or adding too many root modules; `--bind-services` can also link additional matching providers and their dependencies.

**Resolution:** revert to a minimal root module list, inspect the dependency closure, remove redundant roots, and retest. Do not drop a module based solely on size without confirming no functional flow needs it.

### `jdeps` Reports Missing Dependencies or Misses Features

**Cause:** missing JARs on the classpath/module path or dependencies loaded only dynamically.

**Resolution:** provide all dependencies during analysis, do not use `--ignore-missing-deps` to hide errors in final reports, and verify dynamic loading paths with integration tests.

### Image Does Not Run on Another Machine

**Cause:** the runtime image was built for a different OS/architecture, or native libraries are incompatible.

**Resolution:** build the image for the target platform and check native binaries, execute permissions, launchers, and deployment environment variables.

## 13. Reproducible Module Selection Workflow

When preparing a runtime image, follow these steps in order:

1. **Identify application modules:** check module names and `module-info.java`.
2. **Read static relationships:** list `requires`, `requires transitive`, `requires static`, `uses`, and `provides`.
3. **Analyze bytecode:** run `jdeps --list-deps` and `jdeps --print-module-deps`.
4. **Add dynamic dependencies:** check reflection, plugins, services, JNI, and resource configurations.
5. **Select roots:** specify the application module and genuinely needed dynamically loaded modules with `--add-modules`.
6. **Decide on service binding:** use `--bind-services` when provider modules need to be linked.
7. **Constrain the module universe if justified:** consider `--limit-modules` and ensure mandatory dependencies are not excluded.
8. **Link the image:** use a module path containing JDK `jmods` and application modules.
9. **Inspect the image:** use `java --list-modules` and check the launcher.
10. **Run smoke/integration tests:** confirm all critical features, services, plugins, and native calls work in the image.

Record the JDK version, module path, root list, service binding options, `jlink` command, and target platform. This makes image builds reproducible in CI.

## 14. Quick Checklist

- [ ] `--add-modules` selects root modules.
- [ ] `jlink` automatically resolves mandatory dependencies of root modules.
- [ ] `java.base` is the base module that is always required.
- [ ] `requires` and `requires transitive` describe static module relationships.
- [ ] `requires static` is an optional runtime dependency; verify if a feature needs it.
- [ ] `exports` and `opens` control access; they do not add modules on their own.
- [ ] `uses` and `provides` describe services; consider `--bind-services`.
- [ ] `jdeps --list-deps` provides readable dependencies; `--print-module-deps` prints a CSV list.
- [ ] Static analysis can miss reflection, plugins, JNI, and class loading by name.
- [ ] The module path must contain application modules and JDK `jmods`.
- [ ] `--limit-modules` restricts observable modules; it does not replace `--add-modules`.
- [ ] `ALL-MODULE-PATH` and `ALL-SYSTEM` can make the image larger than needed.
- [ ] `jlink` requires proper named modules; classpath JARs/automatic modules do not automatically become valid link inputs.
- [ ] Inspect the image with `--list-modules` and run integration tests.
- [ ] Build the image for the target machine's OS, architecture, and native dependencies.

Selecting the right modules starts with the module descriptor and dependency analysis, followed by checking dynamically loaded components. `jdeps` helps identify static dependencies; `--add-modules` selects roots; `--bind-services` handles providers; and `--limit-modules` controls the module universe. Combining these steps with testing on the runtime image produces a fully functional deployment without unnecessary modules.