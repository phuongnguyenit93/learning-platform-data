# JDK jmods and Module Metadata

The Java Platform Module System (JPMS), introduced in Java 9, divides the Java platform and applications into named modules with explicit dependency relationships and encapsulation boundaries. When working with JDK modules, distinguish two related things with different roles: the **module descriptor** describes a module's structure and contract; **JMOD** is the packaging format holding a module along with resources needed for linking a runtime image.

This lesson uses JDK 21 as a baseline. Module names and some output lines may vary across JDK releases or distributions.

## 1. Where Does Module Metadata Live?

A module is declared via a `module-info.java` file. When compiled, javac produces `module-info.class`, containing binary metadata used by Java tools and the JVM to understand the module.

Example:

~~~java
module com.acme.reporting {
    requires java.sql;
    requires transitive com.acme.model;
    requires static org.slf4j;

    exports com.acme.reporting.api;
    opens com.acme.reporting.internal to com.acme.di;

    uses com.acme.spi.ReportExporter;
    provides com.acme.spi.ReportExporter
        with com.acme.reporting.csv.CsvReportExporter;
}
~~~

Key directives:

- `requires` declares a module that the current module needs to read and use. Every ordinary module implicitly depends on `java.base`; there is no need to write `requires java.base`.
- `requires transitive` propagates readability of the dependent module to client modules as well. Use it only when public types in your API depend on types from that module.
- `requires static` requires the dependency at compile time while allowing it to be absent at runtime, provided no other relationship forces that module to be loaded.
- `exports` exposes a package so other modules can access its public types and members under Java access rules. If written as `exports package.name to module.a, module.b`, the package is exported only to the listed modules.
- `opens` permits deep reflective access into a package, commonly needed by frameworks reading non-public fields or constructors. `opens` does not replace `exports` for normal Java API usage.
- `uses` declares that the module consumes a service.
- `provides ... with ...` registers an implementation for that service, typically discovered via `ServiceLoader`.

A module descriptor also contains the module name, module modifiers, package list, dependencies, exports, opens, services used/provided, and optional metadata such as version or main class. The module name in the descriptor is the authoritative identifier; do not infer a module name from a filename alone.

Descriptor location depends on packaging format:

- Directory module (exploded module): `module-info.class` sits at the module root directory.
- Modular JAR: `module-info.class` sits at the root of the JAR file.
- JMOD: the descriptor sits under `classes/module-info.class`.

## 2. What Is a JMOD?

JMOD is an archive format provided by the JDK to package modules for **link time**, especially when building a runtime image with `jlink`. Files typically carry the `.jmod` extension; module files of a full JDK normally reside in the `jmods` directory under the JDK installation directory.

A JMOD can contain several groups of content:

| Section | Typical contents |
|---|---|
| `classes/` | Java classes, resources, and `module-info.class` |
| `bin/` | Native commands bundled with the module |
| `conf/` | Configuration files |
| `include/` | Headers used when integrating native code |
| `legal/` | Licensing and legal notices |
| `lib/` | Native libraries |
| `man/` | Command manual pages |

Not every module has every section. For example, a pure Java module may store its contents primarily in `classes/`.

### How Does JMOD Differ from a Modular JAR?

| Criterion | Modular JAR | JMOD |
|---|---|---|
| Purpose | Distributing Java libraries or applications | Providing input for runtime image linking tools |
| Module metadata | Can contain `module-info.class` | Can contain `module-info.class` under `classes/` |
| Native/config/header/legal/man content | Lacks dedicated JMOD sections | Can package those sections |
| Used directly with `java --module-path` | Yes | No |
| Input to `jlink` | Supported | Yes, primary use case |

A JMOD is not simply a JAR with a different extension. The JVM launcher does not load `.jmod` files directly as runtime modules. When running an application, use modular JARs or exploded directory modules on the module path. JMODs are primarily used by `jlink` to construct runtime images.

## 3. The JDK jmods Directory and Runtime Images

In a full JDK installation, the `$JAVA_HOME/jmods` directory typically contains files such as:

- `java.base.jmod`
- `java.sql.jmod`
- `java.logging.jmod`
- `jdk.compiler.jmod`
- `jdk.management.jmod`

Exact filenames and counts depend on the JDK release. These modules form the input source from which the linker selects the required platform components.

Distinguish the `jmods/` directory from the JDK's runtime image:

- `jmods/` holds the module packages used during linking.
- The installed runtime image holds the modules executed by the JVM. On a standard JDK, module data is stored in the internal image, commonly found at `lib/modules`.
- A minimal runtime image created with `jlink` may contain only the selected modules and have no `jmods/` directory.

Therefore, lacking a `jmods` directory usually means you are using a minimal runtime image or an installation intended only for running applications rather than a full JDK. To run `jlink`, use a JDK matching the target operating system and architecture.

## 4. Reading JDK Module Metadata via the Command Line

First, inspect the modules present in the current runtime:

~~~bash
java --list-modules
~~~

This command lists the modules provided by the current runtime image, with versions if available. It helps verify whether a module exists in the running JDK.

View the descriptor of a module in the runtime image:

~~~bash
java --describe-module java.sql
~~~

Abbreviated output might look like (versions and details may vary):

~~~text
java.sql@21
exports java.sql
exports javax.sql
requires java.base mandated
requires java.logging transitive
requires java.transaction.xa transitive
uses java.sql.Driver
~~~

How to read it:

- `exports` indicates publicly exposed packages.
- `requires` indicates dependencies.
- `mandated` is a modifier imposed by the platform; for example, the implicit dependency on `java.base`.
- `transitive` indicates a dependency propagated to modules reading the current module.
- `uses` lists services consumed by the module.

To read a JMOD file directly inside the JDK directory, use the `jmod` tool:

~~~bash
jmod describe "$JAVA_HOME/jmods/java.sql.jmod"
jmod list "$JAVA_HOME/jmods/java.sql.jmod"
~~~

- `jmod describe` prints the module's metadata inside the JMOD file.
- `jmod list` lists the packaged entries.

On Windows PowerShell, you can use:

~~~powershell
$jmodFile = Join-Path $env:JAVA_HOME "jmods/java.sql.jmod"
jmod describe $jmodFile
jmod list $jmodFile
~~~

If you need to inspect the extracted structure:

~~~bash
jmod extract --dir extracted "$JAVA_HOME/jmods/java.sql.jmod"
~~~

Then you can read the descriptor bytecode:

~~~bash
javap -v extracted/classes/module-info.class
~~~

`javap -v` displays class file details, including the `Module` attribute. This is useful when inspecting metadata at the bytecode level; in day-to-day work, `java --describe-module` or `jmod describe` is easier to read.

For a modular JAR, use the command for JARs:

~~~bash
jar --describe-module --file library.jar
~~~

Choose the tool according to the input type: `jmod describe` for JMODs, `jar --describe-module` for JARs, and `java --describe-module` to query the running runtime image.

## 5. Reading Module Metadata via the Java API

Java provides APIs in the `java.lang.module` package. `ModuleFinder.ofSystem()` locates modules belonging to the current runtime image; `ModuleReference` represents a found module source; `ModuleDescriptor` provides the parsed metadata.

Example reading dependencies, exported packages, and services of the `java.sql` module:

~~~java
import java.lang.module.ModuleDescriptor;
import java.lang.module.ModuleFinder;
import java.lang.module.ModuleReference;
import java.util.Comparator;

public class InspectSystemModule {
    public static void main(String[] args) {
        ModuleReference reference = ModuleFinder.ofSystem()
            .find("java.sql")
            .orElseThrow();

        ModuleDescriptor descriptor = reference.descriptor();

        System.out.println("module " + descriptor.name());

        descriptor.requires().stream()
            .sorted(Comparator.comparing(ModuleDescriptor.Requires::name))
            .forEach(r -> System.out.println(
                "requires " + r.name() + " " + r.modifiers()));

        descriptor.exports().stream()
            .sorted(Comparator.comparing(ModuleDescriptor.Exports::source))
            .forEach(e -> System.out.println(
                "exports " + e.source()
                    + (e.isQualified() ? " to " + e.targets() : "")));

        descriptor.uses().stream().sorted()
            .forEach(service -> System.out.println("uses " + service));

        descriptor.provides().stream()
            .sorted(Comparator.comparing(ModuleDescriptor.Provides::service))
            .forEach(p -> System.out.println(
                "provides " + p.service() + " with " + p.providers()));
    }
}
~~~

Notable APIs:

- `ModuleFinder.ofSystem()`: finds modules of the current runtime image.
- `ModuleFinder.of(path)`: finds modules in one or more application-supplied paths, such as a directory of modular JARs.
- `ModuleReference.descriptor()`: retrieves the descriptor of a found module.
- `ModuleDescriptor.requires()`, `exports()`, `opens()`, `uses()`, `provides()`: reads each category of metadata.

If running inside an application and wanting to know which module a class belongs to, you can use the `Module` API:

~~~java
Module module = java.sql.Driver.class.getModule();

System.out.println(module.getName());
System.out.println(module.isNamed());
System.out.println(module.getDescriptor());
~~~

`ModuleDescriptor` describes a module; `Module` represents a module loaded into a `ModuleLayer` at runtime. For an unnamed module, `getName()` returns `null` and `getDescriptor()` may also return `null`.

Note: `ModuleFinder.ofSystem()` only finds system modules in the runtime image. When inspecting application modules on the module path, create a finder with `ModuleFinder.of(Path.of("mods"))` using the appropriate path.

## 6. How Are JMODs Used When Building a Runtime Image?

`jlink` combines selected modules together with their dependencies to produce a runtime image smaller than a full JDK. Module descriptors serve as the basis for resolving dependencies; JMODs supply the module contents and required additional resources.

For example, creating a runtime containing only the `java.sql` module and its required dependencies:

~~~bash
jlink   --module-path "$JAVA_HOME/jmods"   --add-modules java.sql   --output runtime-sql
~~~

If your application is the `com.acme.app` module, already compiled and packaged as a modular JAR in the `mods` directory, you can place both JDK JMODs and the application directory on the module path:

~~~bash
jlink   --module-path "$JAVA_HOME/jmods:mods"   --add-modules com.acme.app   --output runtime-app
~~~

On Windows, the separator between module path entries is a semicolon:

~~~powershell
$jmods = Join-Path $env:JAVA_HOME "jmods"
jlink --module-path "$jmods;mods" --add-modules com.acme.app --output runtime-app
~~~

After creation, inspect the new runtime:

~~~bash
runtime/bin/java --list-modules
~~~

On Windows, the corresponding executable is `runtime\bin\java.exe`.

Some common options:

- `--add-modules`: specifies root modules to include in the image; mandatory dependencies are resolved from descriptors.
- `--bind-services`: adds matching provider modules for service binding.
- `--strip-debug`: strips debug information.
- `--no-header-files` and `--no-man-pages`: omits header files and man pages if the runtime does not need them.
- `--compress=2`: compresses resources in the runtime image according to levels supported by the tool.

JMODs are typically platform-specific because they may contain native libraries and native commands. Do not mix JMODs from JDKs targeting different operating systems or architectures. Use the `jmods` set bundled with the JDK matching the target runtime image.

## 7. Common Errors and How to Fix Them

**Command `jmod` or `jlink` not found.** Both tools belong to the JDK. Check `JAVA_HOME` and `PATH`, then verify `java`, `javac`, and `jmod` come from the same installation. On Windows you can run `where java` and `where jmod`; on macOS/Linux use `which java` and `which jmod`.

**Missing `$JAVA_HOME/jmods` directory.** You may be pointing `JAVA_HOME` to a minimal runtime image or a runtime-only installation. Install or select a full JDK that provides the `jmods` directory.

**Passing `.jmod` files to `java --module-path` fails to load at runtime.** This confuses link time with runtime. Use modular JARs or exploded directory modules to run the application; use JMODs as input to `jlink`.

**`jlink` reports module not found.** Check the module name in the descriptor, verify the module path points to the directory containing the JMODs/JARs, and confirm the root module is listed in `--add-modules`. A filename is not necessarily the authoritative module name; the descriptor is.

**Descriptor output differs from online documentation.** Check the JDK version in use. JDK releases can add, remove, or change modules, exported packages, dependencies, and service providers. Inspect output from the exact target JDK before drawing conclusions.

## 8. Quick Comparison of Concepts

| Concept | Role | How to inspect |
|---|---|---|
| `module-info.java` | Module declaration source written by developers | Read source |
| `module-info.class` | Binary descriptor after compilation | `javap -v` |
| Modular JAR | Module package used on the module path at compile/run time | `jar --describe-module` |
| JMOD | Module package that can also carry native/config/header/legal/man sections, mainly used at link time | `jmod describe`, `jmod list` |
| Module in runtime image | Actual module provided by that runtime's JVM | `java --list-modules`, `java --describe-module` |
| `ModuleDescriptor` | Java API for reading parsed metadata | `ModuleFinder` and `ModuleReference` |

## 9. Practice

1. Run `java --list-modules`, and locate `java.sql`, `java.logging`, and `jdk.compiler`.
2. Run `java --describe-module java.sql`. Note the exported packages and dependencies with modifiers.
3. Run `jmod describe` on `java.sql.jmod` in the `jmods` directory; compare it with the output from step 2.
4. Use `jmod extract` to unpack into a separate directory, then run `javap -v` on `classes/module-info.class`.
5. Compile and run the `InspectSystemModule` example; confirm the program prints the module name, dependencies, exports, and services.
6. Use `jlink` to create a runtime containing only `java.sql`, then run `--list-modules` on the newly created runtime to observe the selected module set.

When reading the JDK's module structure, start from the descriptor to understand what a module requires and exposes. Then use JMOD tools to inspect packaged contents and `jlink` to observe how those modules assemble into a deployable runtime image.
