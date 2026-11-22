# Reading a Descriptor with javap or ModuleDescriptor

## 1. What Information Does a Module Descriptor Store?

In the Java Platform Module System (JPMS), each module has a **module descriptor** that describes the module's identity and dependency/access contract. The descriptor is declared via the source file module-info.java and converted by the compiler into the binary file module-info.class.

A descriptor can contain:

- **Module name**: the identifier used in dependency declarations.
- **requires**: modules that the current module reads and depends on.
- **exports**: packages exposed to other modules; can be exported to all reading modules or only named modules.
- **opens**: packages opened for deep reflection access; can also be opened to all or only specified modules.
- **uses**: service types that the module needs to use.
- **provides**: service types that the module supplies along with implementation classes.
- **Optional version and main class**: additional metadata if declared by the descriptor.

Example source descriptor:

~~~java
module com.acme.greeting {
    requires java.logging;
    requires transitive com.acme.model;

    exports com.acme.greeting;
    exports com.acme.greeting.spi to com.acme.app;

    opens com.acme.greeting.internal to com.acme.test;

    uses com.acme.greeting.spi.GreetingProvider;
    provides com.acme.greeting.spi.GreetingProvider
        with com.acme.greeting.internal.DefaultGreetingProvider;
}
~~~

When compiled, Java generates module-info.class in the module's output. If packaged into a modular JAR, this file sits at the root of the JAR. Reading the descriptor helps determine exactly what the module declared without guessing from directory names or class lists.

## 2. Choosing the Right Tool

There are two common ways to read a descriptor:

| Tool | When to Use | Output |
|---|---|---|
| javap | Quickly inspect compiled descriptors, view bytecode details and flags | Disassembly text, optionally including the constant pool and Module attribute |
| java.lang.module.ModuleDescriptor | Read descriptors programmatically in Java, filter and process info in code | Java object with requires, exports, opens, uses, provides... properties |

Both approaches read compiled metadata. They do not automatically prove that all module dependencies are present or that the module has been included in the current runtime configuration.

## 3. Reading module-info.class with javap

### When the Output Is an Exploded Module

Suppose the module has been compiled into the out directory:

~~~text
out/
└── com.acme.greeting/
    ├── module-info.class
    └── com/
        └── acme/
            └── greeting/
                └── Greeting.class
~~~

You can pass the path to the descriptor file directly to javap:

~~~bash
javap -v out/com.acme.greeting/module-info.class
~~~

The -v (verbose) option displays detailed information about the class file. For a module descriptor, the key part is the Module attribute, which contains the module name, flags, requires, exports, opens, uses, and provides.

If you only want a readable summary view, you can use:

~~~bash
javap out/com.acme.greeting/module-info.class
~~~

The output depends on the JDK version and requested level of detail. When checking modifiers or binary metadata, use -v.

### When the Module Is in a Modular JAR

If the module is packaged as a JAR on the module path, you can specify the module path and module name:

~~~bash
javap -v --module-path mods --module com.acme.greeting module-info
~~~

Where:

- --module-path mods specifies the location containing modules.
- --module com.acme.greeting selects the module to read.
- module-info tells javap to display that module's descriptor.
- -v shows detailed information rather than just the abbreviated declaration.

The name after --module must be the module name, not the JAR filename. This name must match the module's descriptor.

### Which Section to Read in the Output?

The Module section typically has a form similar to:

~~~text
Module:
  #... // com.acme.greeting
  requires java.base
  requires java.logging
  requires transitive com.acme.model
  exports com.acme.greeting
  exports com.acme.greeting.spi to com.acme.app
  opens com.acme.greeting.internal to com.acme.test
  uses com.acme.greeting.spi.GreetingProvider
  provides com.acme.greeting.spi.GreetingProvider
    with com.acme.greeting.internal.DefaultGreetingProvider
~~~

This is an example illustrating information structure; constant-pool indices and exact formatting may vary across JDKs.

When reading the output, note:

1. The module name at the top to ensure you are inspecting the right artifact.
2. The requires list to know which dependencies the module declares.
3. transitive or static modifiers on requires to understand dependency scope.
4. The exports list to determine which packages belong to the public API.
5. The opens list to identify packages intended for reflection.
6. uses and provides to see how the module participates in ServiceLoader.

A requires java.base line usually appears in the compiled descriptor even if not written directly in source code, because every regular module implicitly depends on this platform module.

### Using jar for a Quick View

Besides javap, the jar tool has an option to describe a module:

~~~bash
jar --describe-module --file mods/com.acme.greeting.jar
~~~

This command is useful when you only need the module name, exported packages, dependencies, and service info in summary form. Use javap -v when you need to inspect a more detailed binary descriptor.

## 4. Reading Descriptors with ModuleDescriptor in Java

The java.lang.module.ModuleDescriptor API represents a descriptor as an immutable Java object. You can use it to read names, modifiers, dependencies, exported/opened packages, and services without parsing javap string output.

Two situations should be distinguished:

- **Reading a module from a storage location**: use ModuleFinder to find the module on the module path or among system modules.
- **Reading a module already present at runtime**: get the Module from a loaded class and call getDescriptor().

### Reading from the Module Path with ModuleFinder

Suppose the modular JAR resides in the mods directory. The following program finds the module by name and retrieves its descriptor:

~~~java
import java.lang.module.ModuleDescriptor;
import java.lang.module.ModuleFinder;
import java.lang.module.ModuleReference;
import java.nio.file.Path;

public class InspectModule {
    public static void main(String[] args) {
        Path modulePath = Path.of("mods");

        ModuleReference reference = ModuleFinder.of(modulePath)
            .find("com.acme.greeting")
            .orElseThrow(() ->
                new IllegalArgumentException("Module com.acme.greeting not found")
            );

        ModuleDescriptor descriptor = reference.descriptor();

        System.out.println("Module: " + descriptor.name());
        System.out.println("Automatic: " + descriptor.isAutomatic());
        System.out.println("Open: " + descriptor.isOpen());

        descriptor.requires().forEach(requirement ->
            System.out.println(
                "requires " + requirement.name()
                    + " " + requirement.modifiers()
            )
        );
    }
}
~~~

Key components:

- ModuleFinder.of(modulePath) creates a module finder from one or more locations on disk.
- find(name) returns an Optional containing a ModuleReference if the module is found.
- ModuleReference represents a module found in a storage location.
- descriptor() returns the ModuleDescriptor of that module.

If the module name does not exist in the search locations, find returns an empty Optional. If the location containing modules is invalid or an error occurs reading a module, the search operation may throw FindException. Distinguish these two cases when diagnosing issues.

To read a JDK module, you can use ModuleFinder.ofSystem():

~~~java
ModuleDescriptor systemDescriptor = ModuleFinder.ofSystem()
    .find("java.sql")
    .orElseThrow()
    .descriptor();

System.out.println(systemDescriptor.name());
systemDescriptor.requires().forEach(r ->
    System.out.println("requires " + r.name())
);
~~~

This approach lets you inspect system module descriptors without copying JDK JARs into the project.

## 5. Iterating Through Components of ModuleDescriptor

ModuleDescriptor provides strongly typed collections. You can read each section to generate reports or check a module convention.

~~~java
import java.lang.module.ModuleDescriptor;

static void printDescriptor(ModuleDescriptor descriptor) {
    System.out.println("Module: " + descriptor.name());
    System.out.println("Packages: " + descriptor.packages());

    System.out.println("Requires:");
    descriptor.requires().forEach(r ->
        System.out.println("  " + r.name() + " " + r.modifiers())
    );

    System.out.println("Exports:");
    descriptor.exports().forEach(e -> {
        String target = e.targets().isEmpty()
            ? "all modules"
            : e.targets().toString();

        System.out.println("  " + e.source() + " -> " + target);
    });

    System.out.println("Opens:");
    descriptor.opens().forEach(o -> {
        String target = o.targets().isEmpty()
            ? "all modules"
            : o.targets().toString();

        System.out.println("  " + o.source() + " -> " + target);
    });

    System.out.println("Uses:");
    descriptor.uses().forEach(service ->
        System.out.println("  " + service)
    );

    System.out.println("Provides:");
    descriptor.provides().forEach(provider ->
        System.out.println(
            "  " + provider.service() + " with " + provider.providers()
        )
    );
}
~~~

Notable methods:

| Method | Return Value or Meaning |
|---|---|
| name() | Module name |
| modifiers() | Descriptor modifiers |
| isOpen() | Whether the module is declared open at the module level |
| isAutomatic() | Whether the descriptor represents an automatic module |
| requires() | Declared dependencies |
| exports() | Exported packages |
| opens() | Packages opened for reflection |
| uses() | Service types used by the module |
| provides() | Services and providers supplied by the module |
| packages() | Set of packages belonging to the module |
| mainClass() | Optional containing the main class name if declared |
| version() | Optional containing the module version if present |

The returned collections describe descriptor contents, not lists of already-loaded classes. For example, packages() indicates which packages belong to the module; it does not mean all classes in those packages have been loaded by the JVM.

## 6. Understanding requires, exports, and opens in the Results

### requires

Each ModuleDescriptor.Requires element provides the dependent module name and modifiers:

- TRANSITIVE: readability is propagated to modules that depend on the current module.
- STATIC: dependency may be absent at runtime under requires static rules.
- MANDATED or SYNTHETIC: flags generated by the platform or tools in respective cases.

You can check a specific dependency:

~~~java
boolean requiresModelTransitively = descriptor.requires().stream()
    .anyMatch(r ->
        r.name().equals("com.acme.model")
            && r.modifiers().contains(
                ModuleDescriptor.Requires.Modifier.TRANSITIVE
            )
    );
~~~

Note that requires in a descriptor is declared module information. It does not by itself prove the dependent module is present on the module path or was resolved successfully.

### exports

Each ModuleDescriptor.Exports describes a source package and a set of target modules (if any).

- targets() is empty: the package is exported unqualified to modules reading the current module.
- targets() is non-empty: this is a qualified export, granting package access only to the listed modules.

Example of inspecting exposed packages:

~~~java
descriptor.exports().forEach(exported -> {
    System.out.println("Package: " + exported.source());
    System.out.println("Targets: " + exported.targets());
});
~~~

Do not confuse exports with a class's public modifier. A class may be declared public, yet if its package is not exported, other modules still cannot use that API under standard module access rules.

### opens

ModuleDescriptor.Opens also has a source package and a set of target modules, but serves deep reflection.

- opens package does not mean that package is exported for importing and calling regular APIs.
- qualified opens opens the package only to the named modules.
- open module opens all packages of the module for deep reflection under JPMS rules; in that case the descriptor reflects open status at the module level.

When a framework reports a reflection access error, check both isOpen() and opens() to determine whether the module opens the necessary package.

### uses and provides

uses() contains the names of service types the module needs to use. provides() contains the service description and provider classes.

Example of iterating providers:

~~~java
descriptor.provides().forEach(provision -> {
    System.out.println("Service: " + provision.service());

    provision.providers().forEach(provider ->
        System.out.println("  Provider: " + provider)
    );
});
~~~

This information helps understand how the module participates in the ServiceLoader mechanism. The descriptor indicates that a provider has been declared; it does not prove the provider can be instantiated successfully in every runtime environment.

## 7. Reading the Descriptor of a Running Module

If you already have a class belonging to the module to inspect, you can retrieve the module attached to that class:

~~~java
Module module = Greeting.class.getModule();
ModuleDescriptor descriptor = module.getDescriptor();

if (descriptor == null) {
    System.out.println("Class belongs to the unnamed module");
} else {
    System.out.println("Running module: " + descriptor.name());
    System.out.println("Requires: " + descriptor.requires());
    System.out.println("Exports: " + descriptor.exports());
}
~~~

Module.getDescriptor() returns the descriptor of a named module. For an unnamed module, the result is null because an unnamed module does not have a module descriptor like a named module.

You can also inspect a module resolved in the boot layer:

~~~java
Module module = ModuleLayer.boot()
    .findModule("com.acme.greeting")
    .orElseThrow(() ->
        new IllegalStateException("Module is not present in the boot layer")
    );

ModuleDescriptor descriptor = module.getDescriptor();
System.out.println(descriptor);
~~~

ModuleLayer.boot() represents the application's boot layer. If the application creates custom module layers, you need to check the right layer rather than searching only in the boot layer.

Reading from a Module object is useful when you want to observe the module actually attached to a class at runtime. Reading from ModuleFinder is useful when you want to inspect an artifact on disk before bringing it into runtime.

## 8. Reading a Descriptor Does Not Equal Successful Module Resolution

This is an important point when analyzing JPMS issues:

- javap can display the descriptor of a modular JAR even when that module is not used in the current run.
- ModuleFinder can find and read a module's descriptor in a directory, but that operation does not build a module configuration for the application.
- ModuleDescriptor describes declared requirements and access permissions; it does not verify that all requires are satisfied.
- Module.getDescriptor() reads the descriptor of an existing Module object; to know whether a module is in a specific layer, you must query that layer.

If the goal is to find out **what the module declared**, use javap or ModuleDescriptor. If the goal is to determine **which modules were resolved in a run**, observe the runtime configuration/layer or use a diagnostic option such as --show-module-resolution.

An inspection workflow can proceed in order:

1. Identify the exact JAR or module directory to inspect.
2. Use javap -v or ModuleFinder to read the descriptor on disk.
3. Cross-check requires against the modules the application supplies on the module path.
4. Use --show-module-resolution when running to see the modules actually resolved.
5. If the error involves access, check exports, opens, and the appropriate readability relationships.

## 9. Common Errors When Reading Descriptors

**Module not found by name**

The name passed to ModuleFinder.find must be the module name, not the JAR filename. Verify the descriptor name using javap or jar --describe-module before calling find.

**javap reports module or class not found**

Check the module path, module name, and class name passed. When reading a descriptor in an exploded module, pass the exact path to module-info.class; when reading from the module path, select the module by its declared name.

**Reading the descriptor of the wrong artifact**

A directory may contain multiple JARs or multiple versions of a module. Ensure the path and module name point to the exact artifact the application is using. When you need to identify the runtime class source, combine class loading logs with module layer information.

**Not seeing expected exports**

The package might only be opened via opens, or the module being viewed may be an automatic module or unnamed module. Check the actual descriptor and module kind before drawing conclusions.

**Descriptor has requires, but the dependent module does not exist**

This is not an error reading the descriptor. The descriptor can still be read; the error appears only when the resolver needs to satisfy the dependency and cannot find the corresponding module.

**getDescriptor() returns null**

Check whether the class belongs to the unnamed module. This is a valid result for an unnamed module, not a file-reading error.

## 10. Key Takeaways

- module-info.java is the source declaration; module-info.class is the binary descriptor stored in output or a modular JAR.
- javap -v reads details of the compiled descriptor, especially the Module section.
- ModuleFinder finds modules on the module path or among system modules; ModuleReference.descriptor() returns a ModuleDescriptor.
- ModuleDescriptor provides a typed API for requires, exports, opens, uses, provides, packages, and other metadata.
- Empty targets() in exports/opens indicates scope unrestricted by target module name; non-empty targets indicates a qualified export/open.
- Module.getDescriptor() reads the descriptor of the named module attached to a class; unnamed modules return null.
- Reading a descriptor only reveals what the module declared; to know which modules were resolved in a run, inspect the runtime configuration or module layer.

When you need to understand a module before integrating it, read the descriptor of the exact artifact using javap or ModuleFinder. Then compare those declarations against the module path and runtime configuration to determine actual dependencies, public APIs, and reflection permissions.