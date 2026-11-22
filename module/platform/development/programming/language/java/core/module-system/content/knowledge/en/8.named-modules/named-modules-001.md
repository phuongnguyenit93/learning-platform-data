# Named Modules and Module Identity

In the Java Platform Module System (JPMS), a **named module** is a module with a defined name. This name is declared in the module descriptor or derived when a legacy library becomes an automatic module. The module name helps the module system identify dependencies and resolve the module graph.

When the program runs, each module defined in a runtime environment also has a **java.lang.Module** object representing it. This object provides information about the name, descriptor, class loader, and associated ModuleLayer. Therefore, it is necessary to distinguish the module name in the descriptor from the identity of the module object at runtime, while not confusing module identity with Maven coordinates or class identity.

## 1. What is a named module?

A named module is a module that has a name. For an explicit named module, the name is declared directly in the **module-info.java** file at the root directory of the module's source.

Example:

~~~java
module com.acme.orders {
    requires java.logging;
    requires com.acme.customer;

    exports com.acme.orders.api;
}
~~~

The module name here is **com.acme.orders**. The descriptor also declares dependencies and exported packages. When compiled, the compiler creates **module-info.class**; this file is placed at the root of the compiled module directory or at the root of the modular JAR.

Example source structure:

~~~text
src/
└── com.acme.orders/
    ├── module-info.java
    └── com/acme/orders/
        ├── api/
        │   └── OrderService.java
        └── internal/
            └── OrderRepository.java
~~~

Module names usually follow the reverse domain name convention, such as **com.acme.orders** or **org.example.reporting**. This is a naming convention, not a requirement to own the corresponding domain name. Module names are case-sensitive and are not package names automatically inferred from every source directory.

An explicit named module has the following characteristics:

- Has an actual module descriptor compiled from **module-info.java**.
- Has a module name declared by the author.
- Can declare dependencies with **requires**.
- Can publish packages with **exports** and open packages for reflection with **opens**.
- Can declare service dependencies and providers with **uses** and **provides**.

## 2. How named modules differ from unnamed modules

Not all Java code belongs to a named module. Code loaded from the classpath belongs to the **unnamed module** associated with the class loader that loaded that code.

| Characteristic | Named module | Unnamed module |
|---|---|---|
| Module name | Has a name, e.g., **com.acme.orders** | Has no name; **Module.getName()** returns **null** |
| Descriptor | Has an explicit descriptor or the automatic descriptor of an automatic module | Has no module descriptor |
| Common sources | Module path, system modules | Classpath |
| Declaring **requires** | Can declare in the descriptor | Cannot declare via **module-info.java** |
| Package control | Packages are exported/opened according to the descriptor and module rules | Packages of an unnamed module are considered exported and open to other modules |

Each class loader has its own unnamed module. Therefore, two different class loaders can have two different unnamed modules, even though neither has a name.

Code on the classpath does not become a named module just because it calls an API in a named module. Similarly, adding a library to the classpath does not create a stable module name for that library.

## 3. Explicit named modules and automatic modules

It is necessary to distinguish between the two common types of named modules.

### 3.1. Explicit named module

This is a module that has **module-info.class** packaged with the code. The author proactively declares the name, dependencies, and package boundaries.

~~~java
module com.acme.customer {
    exports com.acme.customer.api;
}
~~~

When a modular JAR is placed on the module path, the module system reads this descriptor to identify the module. The module name in the descriptor is the authoritative name; the JAR file name does not determine the module name.

You can inspect the descriptor with:

~~~bash
jar --describe-module --file customer-api.jar
~~~

### 3.2. Automatic module

A legacy JAR without **module-info.class** can still be treated as a named module when placed on the module path. The module system generates an automatic descriptor for that JAR; this type of module is called an **automatic module**.

The automatic module name is determined in order:

1. If the manifest has the **Automatic-Module-Name** attribute, use the stable name declared there.
2. If this attribute is not present, the name is derived from the JAR file name according to the automatic module naming rules.

Manifest example:

~~~text
Automatic-Module-Name: com.acme.legacy.csv
~~~

An automatic module still has a name and can be declared by another named module in **requires**. However, its descriptor is generated automatically and does not express encapsulation intent as fully as an explicit descriptor. An automatic module exports all of its packages and has broad readability rules to support migration.

Therefore, an automatic module is a useful compatibility bridge when bringing legacy libraries onto the module path. When it is possible to modify or repackage the library, an explicit named module usually provides clearer control over dependencies and packages.

## 4. A module name is an identifier, not a library version

The name **com.acme.orders** identifies the module in the module descriptor and during resolution. It is not synonymous with:

- The JAR file name.
- The Maven groupId or artifactId.
- The dependency version.
- The file path on disk.
- The root package name of every class in the module.

For example, a build tool may manage an artifact by coordinates:

~~~groovy
dependencies {
    implementation 'com.acme:orders-api:2.1.0'
}
~~~

While the artifact's descriptor has the module name:

~~~java
module com.acme.orders {
    exports com.acme.orders.api;
}
~~~

The build tool selects the artifact and version to use. JPMS uses the module name along with the descriptor to establish module relationships. The two names may be related by project convention, but they do not belong to the same identification system.

A module descriptor can carry version metadata in certain packaging workflows, but the module name remains a separate field. The **requires com.acme.orders** directive does not declare a version range, and the module system does not replace Maven's or Gradle's version selection mechanisms.

Choosing a stable module name is especially important for libraries. For automatic modules, declare **Automatic-Module-Name** in the manifest so the name does not change merely because the JAR file name is changed.

## 5. Module name and runtime module identity

When a class loader defines a module, the JVM creates a **java.lang.Module** object representing that module. You can obtain the module object from a class:

~~~java
Module module = OrderService.class.getModule();

System.out.println(module.isNamed());
System.out.println(module.getName());
System.out.println(module.getDescriptor());
System.out.println(module.getLayer());
System.out.println(module.getClassLoader());
~~~

Commonly used information:

| API | Information |
|---|---|
| **Module.isNamed()** | Indicates whether the module is a named module. |
| **Module.getName()** | Returns the module name; returns **null** for an unnamed module. |
| **Module.getDescriptor()** | Returns the descriptor of a named module; an unnamed module has no descriptor. |
| **Module.getLayer()** | Returns the ModuleLayer that defines the module; an unnamed module does not belong to a named module layer so the result is **null**. |
| **Module.getClassLoader()** | Returns the class loader that defines the module; may be **null** if the module is defined by the bootstrap class loader. |
| **Module.getPackages()** | Returns the set of package names belonging to the module. |
| **Module.canRead(other)** | Checks whether the current module has readability to another module. |
| **Module.isExported(packageName, other)** | Checks whether a package is exported to the target module. |
| **Module.isOpen(packageName, other)** | Checks whether a package is open for deep reflection from the target module. |

For example, if **OrderService** belongs to the explicit named module **com.acme.orders**, the values can tell you the module name, descriptor, and the layer that defined the class. If the class is on the classpath, **isNamed()** is **false** and **getName()** returns **null**.

The module object is the runtime representation that can be used to inspect module relationships. In code that needs to compare or store a specific runtime module, do not just store the string name and assume that name is a global handle. Consider the **Module** object itself, along with the layer and class loader that defined it.

## 6. The role of ModuleLayer in identity

**ModuleLayer** is the runtime environment containing modules that have been resolved and defined. The JVM creates the boot layer when launching the application; this layer can be accessed via:

~~~java
ModuleLayer boot = ModuleLayer.boot();
~~~

You can find a module in a layer:

~~~java
Module ordersModule = boot
    .findModule("com.acme.orders")
    .orElseThrow(() ->
        new IllegalStateException("Module not found"));
~~~

A layer can have parent layers. Modules in a child layer can read modules in parent layers according to resolved dependencies. A layer also associates modules with the class loaders used to define them.

When an application uses multiple independent layers, you should not assume a string module name is always a unique runtime identifier across the entire process. Inspect the module object and its associated layer/class loader to identify the module being referenced. This approach is especially useful when building plugins, where groups of modules can be resolved and defined separately in different layers.

Some commonly used APIs:

~~~java
ModuleLayer layer = ModuleLayer.boot();

layer.modules().forEach(module -> {
    System.out.println(module.getName());
    System.out.println(module.getClassLoader());
});
~~~

- **ModuleLayer.boot()** gets the boot layer.
- **ModuleLayer.modules()** returns the modules defined directly in that layer.
- **ModuleLayer.findModule(name)** finds a module by name in the layer and its parent layers.
- **Module.getLayer()** indicates the layer that defined the module object.

The layer is part of runtime module identity; it is not a version name or artifact coordinate.

## 7. Module identity is not the same as class identity

Modules and classes are two different levels of identification.

A class is identified by the JVM by its binary name and defining class loader. The module system adds module context to enforce readability, exports, opens, and access rules. Therefore:

- Two classes with the same binary name but defined by two different class loaders are still two different runtime classes.
- Two classes belonging to the same module can share a module object while still having separate identities per class.
- A module name does not replace the defining class loader when analyzing class loading errors.
- Unexported packages affect accessibility across module boundaries; they do not rename classes or move classes to another module.

For example, if you encounter a **ClassCastException** even though two objects have the same displayed class name, check the class loader that defined each class. If you encounter a package not visible error or **IllegalAccessError**, check readability and exports. Both categories of errors can appear together in a modular application, but their causes lie at two different layers.

## 8. Inspecting named modules with JDK tools

JDK tools help verify module names and actual module states.

List modules available in the current runtime:

~~~bash
java --list-modules
~~~

Describe a JAR:

~~~bash
jar --describe-module --file orders.jar
~~~

Observe the resolution process at launch:

~~~bash
java --show-module-resolution \
  --module-path mods \
  -m com.acme.orders/com.acme.orders.Main
~~~

The commands above answer different questions:

- **java --list-modules** shows the modules that the current runtime can list.
- **jar --describe-module** shows the module descriptor or automatic module information of a JAR.
- **--show-module-resolution** shows which modules the module system resolves when running the application.

To inspect a specific class in a program, use **Class.getModule()** and check **getName()**, **getDescriptor()**, **getLayer()**, and **getClassLoader()**. Do not infer the runtime module solely from the JAR file name or the class's package.

## 9. Workflow for identifying modules in an application

When you need to determine which module a class belongs to, follow this order:

1. Determine whether the class is loaded from the module path or the classpath.
2. If it is a modular JAR, read **module-info.class** to get the explicit module name.
3. If the JAR has no descriptor but is on the module path, check **Automatic-Module-Name** or the automatic module name derived from the file.
4. If the class comes from the classpath, identify the unnamed module associated with the class loader that loaded the class.
5. At runtime, get **Class.getModule()** to inspect the actual module object.
6. If there are multiple layers, check **Module.getLayer()** and the class loader to distinguish runtime contexts.
7. When errors involve dependencies or packages, also check **canRead**, **isExported**, and **isOpen**.

This workflow helps distinguish errors caused by module names, artifacts not being on the module path, unexported packages, or classes loaded by a different loader.

## 10. Hands-on exercises

1. Create an explicit named module **com.acme.orders** with a **module-info.java** file and an API package.
2. Compile the module into an exploded module or modular JAR, then use **jar --describe-module** to verify the name.
3. Rename the JAR file while keeping **module-info.class** intact. Observe that the module name remains unchanged.
4. Create a JAR without a descriptor, add **Automatic-Module-Name** to the manifest, and place the JAR on the module path. Confirm that it becomes an automatic module with the declared name.
5. Place a Java class on the classpath and call **Class.getModule()**. Observe **isNamed()** and **getName()**.
6. Print **getLayer()** and **getClassLoader()** for a class in a named module and a class in an unnamed module.
7. Use **ModuleLayer.boot().findModule(...)** to locate a platform module or application module in the boot layer.
8. Compare a package-not-exported error with an error where a class is defined by two different class loaders; explain why module identity and class identity cannot be used interchangeably.

## 11. Key takeaways

- A named module is a module with a name; an explicit named module has a descriptor declared by the author.
- An automatic module is also a named module, but its descriptor is generated automatically from the manifest or the JAR name.
- Code on the classpath belongs to an unnamed module; its module name is **null**.
- A module name is an identifier in the module system, not Maven coordinates, a JAR file name, or a version string.
- **java.lang.Module** represents a module at runtime and provides information about its descriptor, layer, class loader, and access permissions.
- **ModuleLayer** defines the runtime environment where modules are defined.
- Class identity remains tied to the binary name and defining class loader; the module system adds module-level access rules.
- When debugging, inspect the actual module object rather than inferring solely from package names or JAR files.

Once you can distinguish module name, module object, ModuleLayer, and class loader, you will be able to read dependency graphs and diagnose JPMS errors more accurately. This is also the foundation for understanding multi-layer applications and runtime plugin mechanisms.