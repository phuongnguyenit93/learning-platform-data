# Module::isNamed, getName, and getDescriptor

JPMS provides the **java.lang.Module** class to represent a module at runtime. From a Module object, a program can determine whether the module is named, retrieve the module name, and read the descriptor describing dependencies, exported packages, packages opened for reflection, and services. The three APIs **isNamed()**, **getName()**, and **getDescriptor()** are the starting point when observing a class's module or inspecting modules in a ModuleLayer.

You must distinguish the **Module** object from **ModuleDescriptor**. Module is the runtime object representing a defined module; ModuleDescriptor is an immutable description of the module's structure and metadata. An unnamed module has no descriptor, so code must handle null results when reading the name or descriptor.

## 1. Obtaining the Module object from a class

Every class defined by the JVM can report the module it belongs to via **Class.getModule()**:

~~~java
Module module = OrderService.class.getModule();

System.out.println(module.isNamed());
System.out.println(module.getName());
System.out.println(module.getDescriptor());
~~~

In the example, **OrderService** is a class belonging to an application module. If the class was compiled in a named module, the returned object represents that module. If the class was loaded from the classpath, it belongs to the unnamed module of the corresponding class loader.

You can obtain the module of the currently running class itself:

~~~java
Module currentModule = Main.class.getModule();
~~~

Or obtain the module of a JDK type:

~~~java
Module baseModule = String.class.getModule();
System.out.println(baseModule.getName()); // java.base
~~~

This is a useful way to check actual runtime state. Do not infer a module solely from package names, JAR file names, or source locations; a class may have been loaded from the module path, classpath, or a dynamically created ModuleLayer.

## 2. Module.isNamed()

**Module.isNamed()** returns a boolean indicating whether the module object is a named module.

~~~java
Module module = OrderService.class.getModule();

if (module.isNamed()) {
    System.out.println("Named module");
} else {
    System.out.println("Unnamed module");
}
~~~

A named module has a name recognized by the module system. Common cases include:

- **Explicit named module:** a module with a **module-info.class** descriptor declared by the author.
- **Automatic module:** a JAR without an explicit module descriptor placed on the module path, so the module system generates an automatic descriptor.
- **System module:** a module belonging to the runtime image/JDK, such as **java.base**.

An automatic module is still a named module, so **isNamed()** returns **true**. Do not use this method to distinguish an explicit module from an automatic module; read **Module.getDescriptor()** and then check **ModuleDescriptor.isAutomatic()**.

Code on the classpath belongs to an **unnamed module**, so **isNamed()** returns **false**. Each class loader has its own unnamed module. Therefore, two different class loaders can have two different unnamed modules, even though both are unnamed.

## 3. Module.getName()

**Module.getName()** returns the name of the module if it is a named module. For an unnamed module, the method returns **null**.

~~~java
Module module = OrderService.class.getModule();
String moduleName = module.getName();

if (moduleName != null) {
    System.out.println("Module name: " + moduleName);
} else {
    System.out.println("Class belongs to an unnamed module");
}
~~~

For example, a class in a module with descriptor:

~~~java
module com.acme.orders {
    exports com.acme.orders.api;
}
~~~

will have the module name **com.acme.orders**. The **String** class belongs to the **java.base** module, so **String.class.getModule().getName()** returns **java.base**.

If a class is on the classpath, the module name result is null. Do not call operations like **module.getName().equals(...)** without checking for null. You can use **Objects.equals(...)** for safe comparison:

~~~java
boolean isOrdersModule =
    Objects.equals(module.getName(), "com.acme.orders");
~~~

If you only need to filter named modules in a stream, the method reference **Module::isNamed** keeps code clear:

~~~java
ModuleLayer.boot().modules().stream()
    .filter(Module::isNamed)
    .forEach(module -> System.out.println(module.getName()));
~~~

Modules in the boot layer are already named modules; this example illustrates using the method reference on a set of Modules. For a set of modules that might contain an unnamed module, keep the filter step before using the name.

## 4. Module.getDescriptor()

**Module.getDescriptor()** returns the **java.lang.module.ModuleDescriptor** describing the module. If the module is an unnamed module, the method returns **null**.

~~~java
Module module = OrderService.class.getModule();
ModuleDescriptor descriptor = module.getDescriptor();

if (descriptor != null) {
    System.out.println("Descriptor name: " + descriptor.name());
} else {
    System.out.println("Unnamed module has no descriptor");
}
~~~

For an explicit named module, the descriptor is produced from **module-info.java**. For an automatic module, the module system constructs an automatic descriptor from metadata such as **Automatic-Module-Name** or the JAR name. Therefore, the presence of a descriptor does not mean the module is definitely an explicit module.

You can distinguish an automatic module with:

~~~java
if (descriptor != null && descriptor.isAutomatic()) {
    System.out.println("Automatic module");
}
~~~

A descriptor is an immutable descriptive object. Reading the descriptor does not modify the module or grant additional access permissions. It allows tools and applications to observe metadata declared or inferred by the module system.

## 5. Reading information from ModuleDescriptor

**ModuleDescriptor** provides important information about module structure:

| API | Information |
|---|---|
| **name()** | Module name in the descriptor. |
| **requires()** | Set of declared dependencies. |
| **exports()** | Exported packages, including qualified exports. |
| **opens()** | Packages opened for deep reflection, including qualified opens. |
| **uses()** | Service types that the module uses. |
| **provides()** | Services and provider implementations that the module supplies. |
| **packages()** | Set of package names belonging to the module. |
| **isOpen()** | Indicates whether the descriptor declares an open module. |
| **isAutomatic()** | Indicates whether the descriptor represents an automatic module. |
| **version()** | Module version if the descriptor declares version metadata. |
| **mainClass()** | Main class if declared by the descriptor. |

Example printing the name, dependencies, and exported packages:

~~~java
Module module = OrderService.class.getModule();
ModuleDescriptor descriptor = module.getDescriptor();

if (descriptor != null) {
    System.out.println("Name: " + descriptor.name());

    descriptor.requires().forEach(requirement ->
        System.out.println("Requires: " + requirement.name())
    );

    descriptor.exports().forEach(exportedPackage ->
        System.out.println("Exports: " + exportedPackage.source())
    );

    System.out.println("Automatic: " + descriptor.isAutomatic());
}
~~~

**requires()** returns a set of **ModuleDescriptor.Requires** objects; **exports()** returns a set of **ModuleDescriptor.Exports**. These objects contain details such as dependent module name, source package, and related modifiers. Use the descriptor to observe metadata, whereas whether a module actually reads or exports a package to a specific module at runtime must be checked on the Module object.

For example, **Module.canRead(other)** checks readability at runtime; **Module.isExported(packageName, other)** checks whether a package is exported to the target module; **Module.isOpen(packageName, other)** checks deep reflection permission. The descriptor shows declared directives, while APIs on Module reflect access permissions in the runtime context.

## 6. Comparing the three methods

The three methods answer three different questions:

| Method | Return type | Question |
|---|---|---|
| **isNamed()** | boolean | Is this module a named module? |
| **getName()** | String or null | What is the module name? |
| **getDescriptor()** | ModuleDescriptor or null | What is the descriptor describing the module? |

Example:

~~~java
Module module = OrderService.class.getModule();

System.out.println("Named: " + module.isNamed());
System.out.println("Name: " + module.getName());

ModuleDescriptor descriptor = module.getDescriptor();
if (descriptor != null) {
    System.out.println("Automatic: " + descriptor.isAutomatic());
    System.out.println("Packages: " + descriptor.packages());
}
~~~

Common results:

| Module type | isNamed() | getName() | getDescriptor() |
|---|---:|---|---|
| Explicit named module | true | Name in module-info.class | Explicit descriptor |
| Automatic module | true | Automatic module name | Automatic descriptor |
| Unnamed module | false | null | null |
| System module such as java.base | true | java.base | System module descriptor |

This table describes the common cases. When writing code shared across multiple class sources, check for null results rather than assuming every Module object has a name and descriptor.

## 7. Using method references in the Stream API

The lesson title mentions the forms **Module::isNamed**, **Module::getName**, and **Module::getDescriptor**. These are method references pointing to instance methods of the **Module** type. They can be used when a stream is processing Module objects.

Example retrieving the names of named modules in the boot layer:

~~~java
List<String> names = ModuleLayer.boot()
    .modules()
    .stream()
    .filter(Module::isNamed)
    .map(Module::getName)
    .sorted()
    .toList();
~~~

Example retrieving descriptors of modules that have a descriptor:

~~~java
List<ModuleDescriptor> descriptors = ModuleLayer.boot()
    .modules()
    .stream()
    .map(Module::getDescriptor)
    .filter(Objects::nonNull)
    .toList();
~~~

Combined example printing name and automatic status:

~~~java
ModuleLayer.boot().modules().stream()
    .filter(Module::isNamed)
    .forEach(module -> {
        ModuleDescriptor descriptor = module.getDescriptor();

        System.out.printf(
            "%s | automatic=%s%n",
            module.getName(),
            descriptor != null && descriptor.isAutomatic()
        );
    });
~~~

**Module::getName** is equivalent to calling **module.getName()** for each element. **Module::getDescriptor** is equivalent to calling **module.getDescriptor()**. When using a method reference that returns a possibly null value, filter out nulls before invoking further methods on the result.

## 8. Observing modules of classes from different sources

A program can contain classes from multiple sources: application modules, system modules, automatic modules, or the classpath. You can write a helper to print information:

~~~java
static void printModuleInfo(Class<?> type) {
    Module module = type.getModule();

    System.out.println("Class: " + type.getName());
    System.out.println("Named: " + module.isNamed());
    System.out.println("Name: " + module.getName());

    ModuleDescriptor descriptor = module.getDescriptor();
    if (descriptor == null) {
        System.out.println("Descriptor: none (unnamed module)");
    } else {
        System.out.println("Descriptor name: " + descriptor.name());
        System.out.println("Automatic: " + descriptor.isAutomatic());
        System.out.println("Packages: " + descriptor.packages());
    }
}
~~~

You can call:

~~~java
printModuleInfo(Main.class);
printModuleInfo(String.class);
printModuleInfo(OrderService.class);
~~~

The output depends on how the classes are packaged and loaded:

- **String.class** belongs to **java.base**.
- **OrderService.class** belongs to the application module if compiled and loaded as a named module.
- **Main.class** belongs to an unnamed module if the application is running from the classpath; if running from the module path, it belongs to the corresponding named module.

This helper is suitable for diagnosing runtime configuration. If a class is loaded from a custom ModuleLayer, the module name and descriptor may match a module in another layer, but the Module object is the runtime object belonging to a specific layer/class loader.

## 9. A module name is not a unique runtime identity

**getName()** returns the module name, but the string name should not be used as a unique identifier for every module object across the entire JVM. Independent ModuleLayers can contain modules with the same name defined in different runtime contexts.

When you need to distinguish actual modules, keep or compare the Module object and check the layer:

~~~java
Module module = OrderService.class.getModule();

System.out.println("Name: " + module.getName());
System.out.println("Layer: " + module.getLayer());
System.out.println("Loader: " + module.getClassLoader());
~~~

The module name is useful for logging, lookup, and displaying descriptors. The Module object, layer, and class loader provide runtime context to distinguish modules when an application uses multiple layers or plugins.

Also remember that **ModuleDescriptor** describes structure, while **Module** represents the module existing at runtime. The two objects have different roles; do not use the descriptor in place of the Module object when you need to check readability or actual access permissions.

## 10. Common errors

| Symptom | Cause | How to handle |
|---|---|---|
| Calling **getName().equals(...)** causes NullPointerException | Class belongs to an unnamed module so getName() returns null | Check **isNamed()** or use **Objects.equals(...)** |
| **getDescriptor()** returns null | Module is an unnamed module | Determine whether the class was loaded from the classpath |
| isNamed() returns true but module is still automatic | An automatic module is also a named module | Check **getDescriptor().isAutomatic()** |
| Module name differs from JAR filename | Explicit descriptor or Automatic-Module-Name determines the module name | Use **jar --describe-module** to confirm |
| Two modules have the same name in logs | They may belong to different layers/runtime contexts | Check the Module object, **getLayer()**, and class loader |
| Descriptor has export but runtime access still fails | Readability, qualified export, or runtime context does not match | Check **canRead** and **isExported(packageName, targetModule)** |

When debugging, obtain the Module object directly from the class encountering the error. Then read isNamed, getName, and getDescriptor before making assumptions about the module type. This helps avoid wrong conclusions based on package names or artifact names.

## 11. Practice exercises

1. Create an explicit named module **com.acme.orders** and obtain the Module object via **OrderService.class.getModule()**.
2. Print the results of **isNamed()**, **getName()**, and **getDescriptor()**.
3. Run a class on the classpath and compare the three results with a class in a named module.
4. Place a legacy JAR without module-info.class on the module path; confirm **isNamed()** returns true and check **getDescriptor().isAutomatic()**.
5. Use **String.class.getModule()** to observe information about **java.base**.
6. Use **ModuleLayer.boot().modules()** combined with **Module::isNamed** and **Module::getName** to print module names.
7. Use **Module::getDescriptor** in a stream, filter null descriptors, and then print requires and exports.
8. Attempt to access **getName()** and **getDescriptor()** from an unnamed module, handling null safely.
9. Create two layers containing modules with the same name in two different runtime contexts and compare the name with the Module object/layer.
10. Use **ModuleDescriptor.isAutomatic()** to distinguish an automatic module from an explicit named module.

## 12. Key points to remember

- **Module.isNamed()** returns true for explicit named modules, automatic modules, and system modules; unnamed modules return false.
- **Module.getName()** returns the module name or null if the module is an unnamed module.
- **Module.getDescriptor()** returns a ModuleDescriptor or null if the module is an unnamed module.
- An automatic module's descriptor still exists and can be identified via **ModuleDescriptor.isAutomatic()**.
- **ModuleDescriptor** describes requires, exports, opens, uses, provides, and module metadata.
- **Module::isNamed**, **Module::getName**, and **Module::getDescriptor** are useful method references when processing Stream<Module>.
- The module name is identifying data for reading/logging; when you need to distinguish a specific runtime module, inspect the Module object, ModuleLayer, and class loader.
- Always handle null when code might encounter classes belonging to an unnamed module.

Once you know how to obtain a Module object from a class and read these three basic methods, you can determine what kind of module a class belongs to, inspect the module name/descriptor, and begin investigating dependencies or access permissions at runtime.
