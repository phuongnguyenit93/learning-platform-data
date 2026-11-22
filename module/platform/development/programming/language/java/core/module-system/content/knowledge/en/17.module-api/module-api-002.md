# ModuleDescriptor: reading module metadata

## 1. The role of ModuleDescriptor

Since Java 9, the Java Platform Module System (JPMS) allows an application to be split into named modules, declare dependencies, and control which packages can be accessed by other modules. These declarations are written in the `module-info.java` source file, and then compiled into metadata in `module-info.class`.

`java.lang.module.ModuleDescriptor` is the API that represents that metadata as an immutable Java object. You can use it to read the module name, modifiers, version, module dependencies, exported or opened packages, services the module uses, and service implementations the module provides.

`ModuleDescriptor` resides in the `java.lang.module` package, belonging to the foundational `java.base` module. This API is well suited when you need introspection, to write module inspection tools, display dependencies, or analyze JPMS configurations without manually parsing the binary structure of `module-info.class`.

Two concepts must be distinguished:

- `Module` (`java.lang.Module`) represents a module existing in the JVM.
- `ModuleDescriptor` (`java.lang.module.ModuleDescriptor`) describes the declared metadata of that module.

A descriptor describes the module's declarations. It is not a complete record of every access change made dynamically in the JVM.

## 2. Obtaining ModuleDescriptor from a running module

If you already have a class belonging to the module you want to inspect, call `Class.getModule()` to obtain the `Module` object, then call `Module.getDescriptor()`.

~~~java
import java.lang.module.ModuleDescriptor;

public class CurrentModuleInfo {
    public static void main(String[] args) {
        Module module = CurrentModuleInfo.class.getModule();
        ModuleDescriptor descriptor = module.getDescriptor();

        if (descriptor == null) {
            System.out.println("Class belongs to the unnamed module");
            return;
        }

        System.out.println("Module name: " + descriptor.name());
        System.out.println("Module modifiers: " + descriptor.modifiers());
    }
}
~~~

For a named module, `getDescriptor()` typically returns the corresponding descriptor. If the class runs on the classpath and belongs to an unnamed module, this method returns `null`, because an unnamed module does not have a module descriptor like a named module. Therefore, always check the result before accessing its properties.

You can obtain the module of any class, for example:

~~~java
ModuleDescriptor descriptor = String.class.getModule().getDescriptor();
~~~

In this case, the descriptor describes the `java.base` module, because `String` belongs to that module.

## 3. Finding a descriptor with ModuleFinder

A module does not need to be loaded into the JVM in order to read its metadata. The `java.lang.module` package provides `ModuleFinder` to find modules on the module path or among system modules. The result of `find(name)` is an `Optional<ModuleReference>`; from a `ModuleReference` you can obtain the descriptor via `descriptor()`.

### 3.1. Reading a system module

The following example finds the `java.sql` module among the JDK's system modules:

~~~java
import java.lang.module.ModuleDescriptor;
import java.lang.module.ModuleFinder;
import java.lang.module.ModuleReference;

public class FindSystemModule {
    public static void main(String[] args) {
        ModuleDescriptor descriptor = ModuleFinder.ofSystem()
                .find("java.sql")
                .map(ModuleReference::descriptor)
                .orElseThrow(() ->
                        new IllegalArgumentException("Module java.sql not found"));

        System.out.println(descriptor.name());
        System.out.println(descriptor.requires());
    }
}
~~~

`ModuleFinder.ofSystem()` finds modules belonging to the JDK runtime image. The name passed to `find()` is the module name, such as `java.sql`, not a package name like `java.sql` in an import statement interpreted as a package.

### 3.2. Reading a module from the module path

When you have a directory containing modular JARs or compiled modules, use `ModuleFinder.of(Path...)`:

~~~java
import java.lang.module.ModuleDescriptor;
import java.lang.module.ModuleFinder;
import java.lang.module.ModuleReference;
import java.nio.file.Path;

public class FindApplicationModule {
    public static void main(String[] args) {
        Path modulePath = Path.of("mods");

        ModuleDescriptor descriptor = ModuleFinder.of(modulePath)
                .find("com.acme.catalog")
                .map(ModuleReference::descriptor)
                .orElseThrow(() ->
                        new IllegalArgumentException("com.acme.catalog not found"));

        System.out.println("Found: " + descriptor.name());
    }
}
~~~

The path passed to `ModuleFinder.of()` can point to a module directory or a modular JAR. If the result is empty, check the actual module name in `module-info.java`, the JAR file location, and the module path being used.

`ModuleFinder` reads and describes modules without requiring initialization of classes in that module. This is a good choice for dependency analysis tools, inspecting distribution structures, or generating reports before launching an application.

## 4. Important metadata

`ModuleDescriptor` methods return metadata in strongly typed forms. Most returned sets are unmodifiable collections; you should not assume any element order. If you need deterministic output when printing reports, sort before displaying.

| Method | Meaning |
| --- | --- |
| `name()` | Module name, for example `java.sql` or `com.acme.catalog`. |
| `modifiers()` | Module modifiers such as `OPEN`, `AUTOMATIC`, `SYNTHETIC`, `MANDATED`. |
| `version()` | Parsed version, returning `Optional<ModuleDescriptor.Version>`. |
| `rawVersion()` | Raw version string, returning `Optional<String>`. |
| `requires()` | Modules on which this module declares dependencies. |
| `exports()` | Packages exported to other modules. |
| `opens()` | Packages opened for reflection access. |
| `uses()` | Names of services that the module needs to consume. |
| `provides()` | Services along with the list of provider implementations the module supplies. |
| `packages()` | Set of package names belonging to the module according to the descriptor metadata. |
| `mainClass()` | Main class name if declared by the descriptor, returning `Optional<String>`. |
| `isOpen()` | Indicates whether the module is declared as an open module. |
| `isAutomatic()` | Indicates whether this is an automatic module. |

### 4.1. Name, modifiers, and version

`name()` returns the module name. `modifiers()` indicates special attributes of the descriptor. Two states that often need separate checking are:

- `isOpen()`: the module is declared using the `open module` syntax, meaning the module's packages are open for reflection access according to JPMS rules.
- `isAutomatic()`: the module is an automatic module, typically inferred from a JAR without `module-info.class` when that JAR is placed on the module path.

Not every module declares a version or main class. Therefore, `version()`, `rawVersion()`, and `mainClass()` return `Optional`; only read the value when present.

### 4.2. requires — module dependencies

Each element in `requires()` is a `ModuleDescriptor.Requires`. You can read the dependent module's name with `name()` and its modifiers with `modifiers()`.

Important modifiers:

- `TRANSITIVE`: the dependency is passed along to modules that depend on the current module.
- `STATIC`: the dependency is required at compile time but may not be mandatory at runtime.
- `SYNTHETIC` and `MANDATED`: metadata marked as synthetic or mandated by tools/the language.

For example, declaring `requires transitive com.acme.domain;` creates a dependency with the `TRANSITIVE` modifier. A descriptor can also contain the `java.base` dependency with the `MANDATED` modifier, even if you did not directly write `requires java.base;` in source. Therefore, do not treat every element in `requires()` as an explicit declaration line added by the module author.

### 4.3. exports — exposed packages

Each element in `exports()` is a `ModuleDescriptor.Exports`. Use `source()` to get the exported package name.

- An unqualified export allows other modules to read the package's public API.
- A qualified export only allows modules whose names are in `targets()` to access that package.
- `isQualified()` indicates whether the export restricts target modules.

Export controls accessibility of public types at the module level. It does not make every package member public; Java's access rules such as `public`, `protected`, package-private, and `private` remain in effect.

### 4.4. opens — packages open for reflection

Each element in `opens()` is a `ModuleDescriptor.Opens`. Its structure is similar to `Exports`, consisting of the source package, modifiers, and list of target modules.

`opens` serves deep reflection, such as when a framework needs to access non-public fields or constructors. It differs from `exports`: export serves API access under standard Java access rules, whereas open permits deep reflection under module rules.

A module declared with `open module` opens all packages for reflection. For a normal module, you can open specific packages with individual `opens` directives. `isOpen()` checks the open state at the whole-module level; `opens()` lists the package-opening directives in the descriptor.

### 4.5. uses and provides — ServiceLoader

JPMS integrates the service mechanism:

- `uses()` contains the names of interface or abstract services that the module consumes.
- `provides()` contains `ModuleDescriptor.Provides`; `service()` returns the service name, and `providers()` returns the names of the implementation classes.

This metadata corresponds to the `uses` and `provides ... with ...` directives in `module-info.java`. It helps tools inspect plugin/service configurations without parsing source code themselves.

### 4.6. packages and mainClass

`packages()` provides the set of package names recorded by the descriptor. You should not use `exports()` alone to infer all packages of a module, because a module can contain internal unexported packages.

`mainClass()` returns the main class name if metadata declares it. This value is useful when checking whether a module has a specified entry point; it does not launch that class by itself.

## 5. Example reading full metadata

Suppose a module has the following descriptor:

~~~java
module com.acme.catalog {
    requires java.sql;
    requires transitive com.acme.domain;

    exports com.acme.catalog.api;
    exports com.acme.catalog.spi to com.acme.plugin;

    opens com.acme.catalog.model to com.fasterxml.jackson.databind;

    uses com.acme.spi.Formatter;
    provides com.acme.spi.Formatter
            with com.acme.catalog.JsonFormatter;
}
~~~

You can use the following program snippet to read the descriptor of the `java.sql` system module. Change `ModuleFinder.ofSystem()` to `ModuleFinder.of(Path.of("mods"))` and change the module name if you want to inspect an application module.

~~~java
import java.lang.module.ModuleDescriptor;
import java.lang.module.ModuleFinder;
import java.lang.module.ModuleReference;
import java.util.Comparator;

public class ModuleDescriptorInspector {
    public static void main(String[] args) {
        ModuleDescriptor descriptor = ModuleFinder.ofSystem()
                .find("java.sql")
                .map(ModuleReference::descriptor)
                .orElseThrow();

        print(descriptor);
    }

    private static void print(ModuleDescriptor descriptor) {
        System.out.println("Name: " + descriptor.name());
        System.out.println("Modifiers: " + descriptor.modifiers());
        System.out.println("Open module: " + descriptor.isOpen());
        System.out.println("Automatic module: " + descriptor.isAutomatic());

        descriptor.version().ifPresent(
                version -> System.out.println("Version: " + version));
        descriptor.rawVersion().ifPresent(
                version -> System.out.println("Raw version: " + version));
        descriptor.mainClass().ifPresent(
                mainClass -> System.out.println("Main class: " + mainClass));

        System.out.println("\nRequires:");
        descriptor.requires().stream()
                .sorted(Comparator.comparing(ModuleDescriptor.Requires::name))
                .forEach(required -> System.out.printf(
                        "  %s %s%n", required.name(), required.modifiers()));

        System.out.println("\nExports:");
        descriptor.exports().stream()
                .sorted(Comparator.comparing(ModuleDescriptor.Exports::source))
                .forEach(export -> {
                    String targets = export.isQualified()
                            ? String.join(", ", export.targets())
                            : "all modules";
                    System.out.printf("  %s -> %s%n", export.source(), targets);
                });

        System.out.println("\nOpens:");
        descriptor.opens().stream()
                .sorted(Comparator.comparing(ModuleDescriptor.Opens::source))
                .forEach(open -> {
                    String targets = open.isQualified()
                            ? String.join(", ", open.targets())
                            : "all modules";
                    System.out.printf("  %s -> %s%n", open.source(), targets);
                });

        System.out.println("\nUses:");
        descriptor.uses().stream().sorted().forEach(
                service -> System.out.println("  " + service));

        System.out.println("\nProvides:");
        descriptor.provides().stream()
                .sorted(Comparator.comparing(ModuleDescriptor.Provides::service))
                .forEach(provides -> System.out.printf(
                        "  %s -> %s%n", provides.service(), provides.providers()));

        System.out.println("\nPackages:");
        descriptor.packages().stream().sorted().forEach(
                packageName -> System.out.println("  " + packageName));
    }
}
~~~

Actual output depends on the found module's descriptor and the JDK version. This example sorts the sets by name so logs are readable and deterministically ordered. For the `com.acme.catalog` module, the metadata groups will reflect the dependencies, public API packages, package opened to Jackson, and service provider declared in the example.

## 6. Reading a module-info.class file directly

When you already have the path to a compiled `module-info.class` file, you can use `ModuleDescriptor.read(InputStream)`:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.lang.module.ModuleDescriptor;
import java.nio.file.Files;
import java.nio.file.Path;

public class ReadModuleInfoClass {
    public static ModuleDescriptor read(Path moduleInfoClass)
            throws IOException {
        try (InputStream input = Files.newInputStream(moduleInfoClass)) {
            return ModuleDescriptor.read(input);
        }
    }
}
~~~

This method reads compiled bytecode descriptors; it does not read `module-info.java` source files and also does not accept an entire JAR as if it were a `module-info.class` stream. If the descriptor resides inside a modular JAR or module path, `ModuleFinder` is usually more convenient because it handles finding modules and provides a `ModuleReference`.

Invalid descriptor data can cause the read operation to fail. When reading from a file, handle `IOException`; malformed descriptors can throw `InvalidModuleDescriptorException`.

## 7. Creating a descriptor with Builder

In addition to reading existing metadata, the API also lets you create a `ModuleDescriptor` in memory using a builder:

~~~java
import java.lang.module.ModuleDescriptor;

public class BuildDescriptor {
    public static void main(String[] args) {
        ModuleDescriptor descriptor = ModuleDescriptor
                .newModule("com.acme.tools")
                .requires("java.logging")
                .exports("com.acme.tools.api")
                .build();

        System.out.println(descriptor.name());
        System.out.println(descriptor.requires());
        System.out.println(descriptor.exports());
    }
}
~~~

The builder is useful when writing tests or tools that need to construct a descriptor for further processing. The created object is only in-memory metadata; calling `build()` does not create a `module-info.class` file, does not write a JAR, and does not add a module to a `ModuleLayer`.

## 8. Limitations and common misconceptions

1. **A descriptor may not exist.** `Module.getDescriptor()` returns `null` for an unnamed module. Check for null before reading metadata.
2. **A descriptor reflects declarations.** Dynamic operations such as `Module.addReads()`, `addExports()`, or `addOpens()` can change accessibility at runtime. Those changes do not turn the original descriptor into a full record of runtime state.
3. **Do not equate exports with opens.** `exports` exposes a package according to module access rules; `opens` permits deep reflection. A framework needing deep reflection may need a package opened even if that package is not public API.
4. **Do not equate isOpen() with opens().** `isOpen()` indicates whether the module is declared as an open module. `opens()` describes package-opening directives in the descriptor of a normal module.
5. **Not every dependency is explicitly written.** `requires()` can include dependencies marked `MANDATED`, such as `java.base`. Read the modifiers before drawing conclusions about the declaration's origin.
6. **Do not assume a version or main class exists.** Both properties are optional; code must handle the case where no value is present.
7. **Do not rely on Set ordering.** `requires()`, `exports()`, `opens()`, `uses()`, `provides()`, and `packages()` are sets. Sort them when needing deterministic logs, snapshots, or reports.
8. **Module names differ from package names.** `ModuleFinder.find()` accepts a module name, such as `java.sql` or `com.acme.catalog`; it does not search by an arbitrary package name.

## 9. Choosing the right API

| Need | API to use |
| --- | --- |
| Read the descriptor of the module containing a running class | `SomeClass.class.getModule().getDescriptor()` |
| Find metadata of a JDK module | `ModuleFinder.ofSystem().find(name)` |
| Find metadata of a modular JAR/module directory | `ModuleFinder.of(path...).find(name)` |
| Read bytes of a compiled `module-info.class` file | `ModuleDescriptor.read(inputStream)` |
| Create a temporary descriptor in memory | `ModuleDescriptor.newModule(name)` or its corresponding builder |
| Check actual accessibility between modules at runtime | `Module` methods, such as `canRead()`, `isExported()`, `isOpen()` |

When writing JPMS analysis tools, use `ModuleDescriptor` to read declared structure and use `Module` when the question concerns the actual access state of a running module. Combining the two APIs properly helps avoid confusing compiled metadata with JVM runtime state.
