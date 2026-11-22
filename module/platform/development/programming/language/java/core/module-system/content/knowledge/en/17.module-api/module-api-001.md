# `java.lang.Module` and module identity at runtime

## Objectives

After this lesson, you can explain what `Module` represents when an application is running, distinguish between a module name and the identity of a module instance, trace a class's module, and read readability, exports, and opens relationships at runtime.

## 1. From module declaration to runtime object

In the Java Platform Module System (JPMS), the `module-info.java` file declares the module name and relationships such as `requires`, `exports`, `opens`, `uses`, and `provides`. When compiled, this declaration is stored in `module-info.class`. When the application is resolved and loaded, the JVM creates module instances to enforce module boundaries and access rules.

`java.lang.Module` is the class representing a module instance at runtime. It is neither the `module-info.java` file nor a `ClassLoader`. A `Module` object indicates which module a class belongs to, what the module is named, which layer it resides in, which class loader it uses, and what access relationships it currently has with other modules.

You typically obtain this object from a class:

~~~java
Module module = SomeType.class.getModule();
~~~

Every runtime class can be traced back to the module that contains it. Therefore, when encountering access errors like `IllegalAccessError`, reflection errors like `InaccessibleObjectException`, or issues when loading plugins, `Class.getModule()` is a useful starting point for inspection.

## 2. Module name and module identity are two different concepts

A module name is a label used in module declaration and resolution, for example `java.base` or `com.acme.payment`. This name helps the module system locate dependencies and express relationships in configuration.

Runtime identity is the specific module instance created by the JVM. When you need to know whether two classes belong to the same module instance, compare the `Module` objects they return:

~~~java
Module first = FirstType.class.getModule();
Module second = SecondType.class.getModule();

boolean sameRuntimeModule = first == second;
~~~

You should not use `getName()` alone as a global identifier key. Different module layers can contain module instances with the same name. This is useful when an application loads independent plugin versions in separate layers. Two modules with the same name residing in two different layers are still two different module instances.

A module instance is also not synonymous with a class loader. A single class loader can define multiple named modules; conversely, layers can use different class loaders. A module represents module boundaries and access rules, whereas a class loader is responsible for defining classes.

For classes, type identity in the JVM is tied to the binary name of the class and its defining class loader. If two class loaders actually define two separate classes with the same name, those two `Class` objects are still two distinct types, even if their bytecode is identical. Modules provide additional context about a class's access boundaries.

## 3. Three common types of modules at runtime

### Explicit named module

This is a module explicitly declared in `module-info.java`. For example:

~~~java
module com.acme.orders {
    requires java.logging;
    exports com.acme.orders.api;
    opens com.acme.orders.model;
}
~~~

This module is named `com.acme.orders` and has a `ModuleDescriptor` describing its declarations.

### Automatic module

A JAR without `module-info.class`, when placed on the module path, can be treated as an automatic module. The module system creates an automatic descriptor based on the JAR's information and derives the module name from the file name or manifest. An automatic module is still a named module, so `Module.isNamed()` returns `true`.

An automatic module has broader compatibility rules than an explicit module, such as the ability to read other modules and export its packages. You should not rely on these broad rules as a long-term design for a module with clear API boundaries.

### Unnamed module

Classes loaded from the class path typically belong to the unnamed module of their corresponding class loader. Each class loader has its own unnamed module. An unnamed module does not have a module name and does not have a `ModuleDescriptor` like a named module.

~~~java
Module module = SomeClasspathType.class.getModule();

System.out.println(module.isNamed()); // false
System.out.println(module.getName()); // null
System.out.println(module.getDescriptor()); // null
~~~

Do not confuse an unnamed module with an automatic module: an automatic module is a named module derived from a JAR; an unnamed module is typically associated with the class path and a class loader.

## 4. Important APIs of `java.lang.Module`

| API | Meaning |
| --- | --- |
| `getName()` | Returns the module name; returns `null` for an unnamed module. |
| `isNamed()` | Indicates whether the module is a named module. |
| `getDescriptor()` | Returns the `ModuleDescriptor` of a named module; may be `null` for an unnamed module. |
| `getLayer()` | Returns the `ModuleLayer` containing the module; may be `null` if the module does not belong to a layer. |
| `getClassLoader()` | Returns the class loader that defines the module; `null` represents the bootstrap class loader. |
| `getPackages()` | Returns the set of package names belonging to the module. |
| `canRead(Module)` | Checks whether the current module has a readability edge to the passed-in module. |
| `isExported(String, Module)` | Checks whether a package of the current module is exported to the target module. |
| `isOpen(String, Module)` | Checks whether a package of the current module is open to the target module. |
| `getResourceAsStream(String)` | Reads a resource by name from the module, obeying the module's resource encapsulation rules. |

The following example prints runtime information for a class:

~~~java
import java.lang.module.ModuleDescriptor;

public final class ModuleInspector {
    public static void print(Class<?> type) {
        Module module = type.getModule();
        ModuleDescriptor descriptor = module.getDescriptor();

        System.out.println("class       : " + type.getName());
        System.out.println("module      : "
                + (module.isNamed() ? module.getName() : "<unnamed>"));
        System.out.println("module obj  : " + module);
        System.out.println("class loader: " + module.getClassLoader());
        System.out.println("layer       : " + module.getLayer());
        System.out.println("packages    : " + module.getPackages());

        if (descriptor != null) {
            System.out.println("requires: " + descriptor.requires());
            System.out.println("exports : " + descriptor.exports());
            System.out.println("opens   : " + descriptor.opens());
        }
    }
}
~~~

`ModuleDescriptor` belongs to the `java.lang.module` package. It describes the metadata of a named module, such as dependencies and exported or opened packages. The descriptor is metadata; the `Module` object is the module instance existing at runtime. For an unnamed module, `getDescriptor()` returns `null`, so you need to check before reading the descriptor.

`System.identityHashCode(module)` is sometimes useful when logging to distinguish objects within a run, but hash values can collide. When you need to check whether two references point to the exact same module instance, use the `==` comparison.

## 5. Reading the three relationships correctly: readability, exports, and opens

These three concepts often appear together but answer three different questions.

- **Readability**: Can the client module read the API module? This relationship is typically declared with `requires`.
- **Exports**: Is the API package exported by the source module to the client module? Exporting allows other modules to use public types in the package according to standard Java access rules.
- **Opens**: Is the package opened to the client module for deep reflection? Opens enables reflective access, including non-public members when reflection conditions are met.

Example check from the client module side:

~~~java
Module clientModule = Client.class.getModule();
Module apiModule = PublicApi.class.getModule();

boolean canReadApi =
        clientModule.canRead(apiModule);

boolean apiIsExported =
        apiModule.isExported("com.acme.api", clientModule);

boolean internalsAreOpen =
        apiModule.isOpen("com.acme.internal", clientModule);

System.out.println("readable: " + canReadApi);
System.out.println("exported: " + apiIsExported);
System.out.println("open    : " + internalsAreOpen);
~~~

Pay attention to the call direction:

- Call `clientModule.canRead(apiModule)` because the client is the module that needs to read the API.
- Call `apiModule.isExported(packageName, clientModule)` because the package resides in the API module and we need to check if it is exported to the client.
- Call `apiModule.isOpen(packageName, clientModule)` because the API module is the owner of the package that needs to be opened for reflection.

Having readability does not automatically mean every package of the dependency is exported. Export is also not synonymous with open. A package can be exported for public API usage while still remaining closed to deep reflection.

In `module-info.java`, you can declare an export or open without restricting target modules, or explicitly specify target modules:

~~~java
module com.acme.domain {
    exports com.acme.domain.api;
    exports com.acme.domain.spi to com.acme.plugin;

    opens com.acme.domain.model;
    opens com.acme.domain.internal to com.acme.serializer;
}
~~~

Declaring `open module com.acme.domain { ... }` opens all packages of the module for deep reflection. This does not mean all packages are exported for other modules to access the API in the standard way.

## 6. `ModuleLayer` and module identity across multiple layers

`ModuleLayer` is a group of modules resolved into a runtime graph. The JVM starts the application with the boot layer, accessible via `ModuleLayer.boot()`. An application can also create new layers to load plugins or components that need their own lifecycle and class loader.

~~~java
Module javaBase = ModuleLayer.boot()
        .findModule("java.base")
        .orElseThrow();

System.out.println(javaBase.getName());
System.out.println(javaBase.getLayer() == ModuleLayer.boot());
~~~

Advanced example: loading a plugin module from the `plugins` directory into a new layer. The plugin module must be present on the module path scanned by `ModuleFinder`.

~~~java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.Set;

ModuleFinder finder = ModuleFinder.of(Path.of("plugins"));

Configuration configuration =
        ModuleLayer.boot().configuration().resolve(
                finder,
                ModuleFinder.of(),
                Set.of("com.example.plugin"));

ModuleLayer pluginLayer =
        ModuleLayer.boot().defineModulesWithOneLoader(
                configuration,
                ClassLoader.getSystemClassLoader());

Module pluginModule = pluginLayer
        .findModule("com.example.plugin")
        .orElseThrow();

System.out.println(pluginModule.getName());
System.out.println(pluginModule.getLayer() == pluginLayer);
~~~

In this example, `defineModulesWithOneLoader` creates a new layer and uses a single class loader for the modules defined in that layer. The `defineModulesWithManyLoaders` API is another option when you want each module to have its own class loader.

A module name has meaning within the scope of a configuration/layer. When a system has multiple layers, do not assume that a module name has only a single module instance in the entire process. If debugging a plugin, inspect the module name, layer, and class loader together:

~~~java
Module module = PluginEntry.class.getModule();

System.out.println("name   = " + module.getName());
System.out.println("layer  = " + module.getLayer());
System.out.println("loader = " + module.getClassLoader());
~~~

## 7. Using the Module API when debugging access errors

When a module cannot access a class or package, check in the following order:

1. Obtain the modules of the calling class and the accessed class using `Class.getModule()`.
2. Print `getName()`, `getLayer()`, and `getClassLoader()` of both modules to identify the exact module instances.
3. Check whether the calling module reads the target module using `canRead`.
4. Check whether the package containing the API is exported to the calling module using `isExported`.
5. If the error occurs when using reflection to access non-public members, check whether the package is open to the calling module using `isOpen`.

JVM options such as `--add-reads`, `--add-exports`, and `--add-opens` can add relationships when running the application or assist with compatibility diagnostics. They affect readability, export, and open respectively. For a stable design, the necessary relationships should be declared in `module-info.java`; only open internal packages when there is a clear reason.

## 8. Common misconceptions

- **Using the module name as a global ID**: the same name can appear in different layers. Inspect the module instance and layer when you need to distinguish them.
- **Treating `Module` as `ClassLoader`**: one loader can define multiple modules; a module has its own class loader returned by `getClassLoader()`.
- **Assuming `requires` is enough to access every package**: readability does not replace exports.
- **Treating exports and opens as identical**: exports serve public API access; opens serve deep reflection.
- **Assuming every module has a descriptor**: an unnamed module returns `null` from `getDescriptor()`.
- **Logging only the module name when debugging plugins**: also log the layer and class loader to understand the module instance and class definition source.

## Key takeaways

`java.lang.Module` is the runtime view of a module instance. `getName()` gives the name, `getLayer()` gives the containing layer, `getClassLoader()` gives the loader that defines the module, and `canRead`, `isExported`, and `isOpen` help inspect access relationships. When working with multiple module layers, the module name is not enough to uniquely identify a module instance; inspect the `Module` object itself and its layer context.
