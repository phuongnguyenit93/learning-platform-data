# JPMS: Distinguishing Descriptor Discovery from Class Definition

In the Java Platform Module System (JPMS), **finding a module descriptor** only means the system has located metadata describing a module. It **is not equivalent** to the JVM having found, loaded, or defined any specific class inside that module. This is an important boundary when reading the **module resolution** flow and diagnosing runtime errors.

## 1. Two Completely Different Questions

**Question A — “Does this module have a descriptor?”**

JPMS uses module finders to discover observable modules. Given a module name, **ModuleFinder.find(String)** can return a **ModuleReference**; from that reference, you can obtain a **ModuleDescriptor**. The descriptor describes the module's name, requires dependencies, exports/opens packages, uses/provides, version, and other attributes.

This is an operation at the **module and metadata level**. It does not require creating a **Class<?>** object, does not execute static initializers, and does not prove that an arbitrary class name exists.

**Question B — “Has the JVM defined this class, or can it load it?”**

At the class level, the JVM coordinates with a **ClassLoader** to locate bytecode, verify its format, define the class, and perform linking/initialization steps when requested. The result is a **Class<?>** object associated with a specific class loader and a specific module. A valid descriptor does not guarantee that every class mentioned by the program will load successfully.

For example: module **demo.catalog** has a descriptor and exports package **demo.catalog.api**; an attempt to load **demo.catalog.api.Missing** can still fail because the class file does not exist.

## 2. Concepts and APIs to Distinguish

| Component | What Question Does It Answer? | Typical Result | Does It Define Classes? |
|---|---|---|---|
| **ModuleFinder** | Can module named X be found from the source under consideration? | **Optional<ModuleReference>** | No |
| **ModuleReference** | Which source is the found module in, and what descriptor does it have? | Descriptor, location (if available), **ModuleReader** | No |
| **ModuleDescriptor** | How does the module declare name, requires, exports, opens, uses, provides, packages? | Immutable metadata | No |
| **Configuration** | Can the module dependency graph be resolved from the given finders? | Set of resolved modules and readability relationships | No |
| **ModuleLayer** | Which modules have been defined into a layer? | **Module** objects and mappings to class loaders | Does not load all classes automatically |
| **ClassLoader / JVM** | Can a class with a specific name be loaded, defined, and linked? | **Class<?>** or an error during loading/linking | Yes, when actually loaded |
| **Class.forName(Module, String)** | Is there a class named Y loaded from module X? | **Class<?>** or **null** if not found in that module | May trigger class loading; does not initialize the class |

Note: **exports** is a package access rule for other modules; **opens** serves deep reflective access. Neither is a list of classes. **ModuleDescriptor.packages()** is a set of package names, not a complete catalog of classes inside the packages.

## 3. Position of Each Step in Module Resolution

Overview flow of a modular application:

~~~text
Module sources: runtime image, module path, custom ModuleFinder
    |
    v
ModuleFinder.find("demo.catalog")
    |
    v
ModuleReference -> ModuleDescriptor
    |
    v
Configuration.resolve(...) / resolveAndBind(...)
    |  Checks required modules and dependency relationships
    v
ModuleLayer created, or boot layer already set up by the JVM
    |  Associates modules with the corresponding class loaders
    v
Program code references a class or requests class loading
    |
    v
ClassLoader / JVM finds bytecode, defines class, links, initializes when needed
~~~

Points to remember:

1. **Discovery**: ModuleFinder locates an observable module from configured sources. It may see a module that the current application has not resolved.
2. **Resolution**: the resolver relies on descriptors to build the module graph, handling requires and module-level constraints. Finding a descriptor is an input condition, not yet sufficient to confirm resolution succeeds.
3. **Layer definition**: a configuration is used to define modules in a layer, select class loaders, and establish module relationships.
4. **Class loading**: specific classes are normally loaded by the JVM on demand. There is no rule that resolving a module must load all classes in the module.
5. **Initialization**: even after a class has been loaded/defined, its static initializer may not have run yet. Initialization is a separate point in time from finding the descriptor.

**ModuleFinder.ofSystem()** observes modules in the runtime image; **ModuleFinder.of(Path...)** observes modules on the supplied paths. A finder locating a module name does not prove that module is in **ModuleLayer.boot()**.

## 4. Runnable Java Example

The example consists of two modules. The library module has the class **Widget** but does not have the class **Missing**; the application module requires the library.

Directory structure:

~~~text
src/
  demo.catalog/
    module-info.java
    demo/catalog/api/Widget.java
  demo.app/
    module-info.java
    demo/app/Main.java
~~~

**src/demo.catalog/module-info.java**

~~~java
module demo.catalog {
    exports demo.catalog.api;
}
~~~

**src/demo.catalog/demo/catalog/api/Widget.java**

~~~java
package demo.catalog.api;

public class Widget {
    public static String label() {
        return "JPMS";
    }
}
~~~

**src/demo.app/module-info.java**

~~~java
module demo.app {
    requires demo.catalog;
}
~~~

**src/demo.app/demo/app/Main.java**

~~~java
package demo.app;

import java.lang.module.ModuleDescriptor;
import java.lang.module.ModuleFinder;
import java.lang.module.ModuleReference;
import java.nio.file.Path;

public class Main {
    public static void main(String[] args) {
        // (1) Find metadata at the path containing compiled modules.
        ModuleFinder finder = ModuleFinder.of(Path.of("mods"));
        ModuleReference reference =
                finder.find("demo.catalog").orElseThrow();
        ModuleDescriptor descriptor = reference.descriptor();

        System.out.println("Finder sees: " + descriptor.name());
        System.out.println("Package in descriptor: "
                + descriptor.packages().contains("demo.catalog.api"));

        // (2) The application requires demo.catalog so the module is in the boot layer.
        Module catalog = ModuleLayer.boot()
                .findModule("demo.catalog").orElseThrow();
        System.out.println("Layer contains: " + catalog.getName());

        // (3) Check two class names inside the same module.
        Class<?> existing =
                Class.forName(catalog, "demo.catalog.api.Widget");
        Class<?> absent =
                Class.forName(catalog, "demo.catalog.api.Missing");

        System.out.println("Widget loaded: " + (existing != null));
        System.out.println("Missing loaded: " + (absent != null));
        System.out.println("Module owning Widget: "
                + existing.getModule().getName());
    }
}
~~~

From the directory containing **src**, compile and run with JDK 9 or later:

~~~sh
javac --module-source-path src -d mods -m demo.catalog,demo.app
java --module-path mods -m demo.app/demo.app.Main
~~~

Expected output:

~~~text
Finder sees: demo.catalog
Package in descriptor: true
Layer contains: demo.catalog
Widget loaded: true
Missing loaded: false
Module owning Widget: demo.catalog
~~~

**Explanation:** ModuleFinder found the **demo.catalog** descriptor. Configuration resolved the module because **demo.app requires demo.catalog**. When the program requests loading **Widget**, the JVM finds the class. For **Missing**, **Class.forName(Module, String)** returns **null**; the descriptor still exists and graph resolution remains valid.

If you delete the **Widget** class and modify Main so it does not depend directly on that class at compile time, the module's metadata can still be found; yet at runtime, requesting to load the name Widget will not succeed. Conversely, a class having a bytecode file on disk is not automatically accessible from every module either.

## 5. Descriptor Also Differs from Checking a .class Resource

From **ModuleReference**, the **ModuleReader** API allows inspecting the resources of a module:

~~~java
import java.lang.module.ModuleFinder;
import java.lang.module.ModuleReference;
import java.lang.module.ModuleReader;
import java.nio.file.Path;

ModuleReference ref = ModuleFinder.of(Path.of("mods"))
        .find("demo.catalog").orElseThrow();

try (ModuleReader reader = ref.open()) {
    boolean hasBytes = reader
            .find("demo/catalog/api/Widget.class")
            .isPresent();
    System.out.println("Has resource Widget.class: " + hasBytes);
}
~~~

Three levels of evidence must be separated:

- **ModuleDescriptor found**: there is metadata describing the module.
- **Widget.class resource found**: the module source provides a resource at the corresponding path; this step does not yet prove the bytecode content is valid or that the class has been defined.
- **Class<?> obtained**: the runtime has loaded the class through the class loading mechanism; using the class can still produce linking, access, or initialization errors depending on the moment.

Do not use **descriptor.packages().contains("demo.catalog.api")** as a test for the existence of **demo.catalog.api.Widget**. It only checks the package name.

## 6. Why Can a “Descriptor Be Found” Yet a “Class Fails to Load”?

| Symptom | Possible Cause | How to Analyze |
|---|---|---|
| Finder has ModuleReference, layer lacks module | The module is observable but not in the resolved graph / layer under inspection | Distinguish the set of observable modules from the set of resolved modules |
| Descriptor has exports for package, class name absent | The module does not package that class, the name is wrong, or the class is elsewhere | Check the fully qualified name and the module contents |
| .class resource is present, class loading fails | Corrupt bytecode, missing dependencies during linking, or loader issues | Inspect the exception/error type and cause chain |
| Class is present, yet code from another module cannot access it | Missing exports, readability, or Java access conditions | Check requires/exports/opens and access levels |
| Right module name, yet class is defined by another module/loader | Wrong loader, wrong layer, or environment with multiple distributions | Check **clazz.getModule()** and **clazz.getClassLoader()** |
| Class loads, yet fails on first use | Initialization error or error during linking/execution | Distinguish class loading, linking, and initialization |

Several common error types at different stages:

- **FindException** or **ResolutionException**: errors related to finding or resolving a module configuration; depending on the case, these can happen before application code runs.
- **ClassNotFoundException**: commonly seen with **Class.forName(String)** or name-based class loading through a class loader.
- **NoClassDefFoundError**: the runtime needs a class definition but cannot find/complete that definition (or the class previously failed to initialize).
- **IllegalAccessError** and other linkage errors: the class exists, yet access or linkage rules are not satisfied.
- **ExceptionInInitializerError**: an error occurring during class initialization; not a result of reading the descriptor.

Do not equate the two overloads of **Class.forName**:

~~~java
Class<?> a = Class.forName("demo.catalog.api.Widget");
// Looks up using the caller's loader and initializes the class by default if found.

Module module = ModuleLayer.boot()
        .findModule("demo.catalog").orElseThrow();
Class<?> b = Class.forName(module, "demo.catalog.api.Widget");
// Looks up the class in the specified module; does not initialize the class.
// Returns null if the class is not found in that module.
~~~

Finding a class by module does not automatically prove the caller is allowed to access all members of that class. Java and JPMS access rules still apply when using the class.

## 7. How to Self-Check When Diagnosing Modules

First determine which level is failing:

1. **Observe the module**: use the appropriate ModuleFinder and check **find(name)**; for modular JARs, you can use **jar --describe-module --file path/to/library.jar** to read the descriptor.
2. **Resolve the module**: run the application with **--show-module-resolution** to observe the resolved module graph. Check requires, module names on the module path, and the actual layer.
3. **Locate the class/resource**: check the exact class path inside the artifact, the exact package, and the exact fully qualified name; if appropriate, try ModuleReader.
4. **Load the class**: use **Class.forName(module, fqcn)** when you already have the target Module object and need to know whether the class can be loaded from that exact module. If successful, check **getModule()** and **getClassLoader()**.
5. **Access/initialize**: if the class loaded yet the program still fails, inspect readability/exports/opens requirements, linkage errors, and static initializers.

Command to observe resolution for the example:

~~~sh
java --show-module-resolution --module-path mods -m demo.app/demo.app.Main
~~~

These checks answer questions at **different layers**; do not substitute a descriptor check for a class check.

## 8. Key Takeaways

**Module resolution resolves the module graph based on descriptors; class loading defines specific classes when needed at runtime.** A descriptor confirms a module's metadata; it is not a guarantee that a class name exists, is accessible, can be linked, or has been initialized.

The right mental formula:

~~~text
Finder finds descriptor
    != module is resolved into the current layer
    != specific class exists or is loaded
    != class is accessible from every module
    != class has been initialized successfully
~~~

When debugging JPMS, clearly identify whether you are asking about **module metadata**, the **module graph**, a **class file**, a **Class<?>**, or **access/initialization permissions**.
