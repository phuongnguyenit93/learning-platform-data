# Platform, Application, and Module ClassLoaders in Java

A class loader is the JVM mechanism used to locate and define classes when a program needs them. Since Java 9, the Java Platform Module System (JPMS) adds modules to organize packages, declare dependencies, and restrict access. The two mechanisms work together: the class loader loads classes, while the module determines which unit a class belongs to and which modules are allowed to access exported packages.

This lesson explains the three common built-in class loaders — bootstrap, platform, and application (system) — along with how they participate in loading named modules, module layers, and applications.

## 1. Learning Objectives

After this lesson, you will be able to:

- Describe the roles of the bootstrap, platform, and application class loaders.
- Explain the parent-child relationship among the built-in loaders.
- Distinguish between classpath, module path, named modules, and unnamed modules.
- Identify the class loader and module of a class using Java APIs.
- Explain why two classes with the same name can still be two different runtime types.
- Recognize when a module layer or custom class loader is useful for a plugin system.

## 2. Class Loaders in the Class Loading Process

When the JVM needs to use a class, it must have the definition of that class at runtime. The class processing lifecycle is commonly divided into three major phases:

1. **Loading:** locates the bytecode and creates the class representation in the JVM. The class loader participates directly in this phase.
2. **Linking:** verifies the bytecode, prepares the required data structures, and resolves references when needed.
3. **Initialization:** executes static initializers and `static` blocks according to Java rules.

The class loader is responsible for locating and defining the class; the JVM performs the linking and initialization steps according to the platform rules.

A class has a **defining class loader** — the loader that defined that class. The runtime identity of a class depends on both its fully qualified name (binary name) and its defining loader. If two separate loaders each define the class `com.example.Plugin`, the JVM treats them as two different types, even though the class names are identical. This is an important principle when developing plugins, application servers, and frameworks with multiple class-loading scopes.

## 3. The Three Built-in Class Loaders

Since Java 9, the common structure of the default loaders can be visualized as follows:

```text
Bootstrap Class Loader
        |
        v
Platform Class Loader
        |
        v
Application (System) Class Loader
        |
        v
Custom class loaders (if created by the application)
```

The diagram illustrates the common parent delegation relationship. Custom loaders can be attached to the tree according to a specific design; they are not required to be children of the application loader.

### 3.1. Bootstrap Class Loader

The bootstrap class loader is the lowest-level foundational loader of the JVM, responsible for loading the core classes needed to start and run the Java runtime, such as `java.lang.Object` and `java.lang.String`.

Characteristics:

- Implemented at the JVM/runtime level, not an ordinary Java `ClassLoader` object that applications can manipulate directly.
- Serves as the root parent of the platform class loader.
- For a class defined by the bootstrap loader, `SomeClass.class.getClassLoader()` returns `null`. Here, `null` represents the bootstrap loader; it does not mean the class has not been loaded.
- Many core classes belonging to foundational modules are defined by the bootstrap loader; you should not assume that every class in the JDK is loaded by the bootstrap loader.

### 3.2. Platform Class Loader

The platform class loader is the parent loader of the application/system class loader. It loads Java platform classes that are not defined by the bootstrap loader.

Retrieve this loader via the public API:

```java
ClassLoader platform = ClassLoader.getPlatformClassLoader();
System.out.println(platform);
```

Characteristics:

- Available since Java 9.
- Its parent is the bootstrap loader; because the bootstrap loader is represented by `null`, calling `platform.getParent()` typically returns `null`.
- Responsible for loading platform classes assigned to the platform loader, including many classes belonging to Java SE/JDK modules.
- Serves as the parent of the application loader in the default structure.

Before Java 9, Java had the Extension Class Loader (commonly called ExtClassLoader). The extension mechanism was removed when the platform moved to the module system; the platform class loader takes over the loader role for the corresponding platform classes. When reading legacy code or documentation, you need to distinguish the names and behavior of the two generations.

### 3.3. Application Class Loader (System Class Loader)

The application class loader is commonly called the system class loader. In a standard Java configuration, it is the default loader that loads application classes.

Retrieve the loader via:

```java
ClassLoader app = ClassLoader.getSystemClassLoader();
System.out.println(app);
System.out.println(app.getParent());
```

Characteristics:

- Its default parent is the platform class loader.
- Loads application classes from the classpath, such as paths passed via `-cp` or `--class-path`.
- Also participates in loading named modules assigned to the system/application loader on the module path.
- Can be replaced by a custom system class loader via runtime configuration; therefore, you should not assume every environment has the same concrete implementation class.

In a typical application, `ClassLoader.getSystemClassLoader()` returns the default application loader of the process.

## 4. Parent Delegation and Class Lookup

The built-in class loaders use a parent delegation model: when a class needs to be loaded, a loader usually asks its parent first; if the parent cannot find it, the current loader then searches within the scope it manages. The goal is to prevent applications from accidentally redefining platform classes such as `java.lang.String`.

General flow:

1. The application requests the JVM to load a class.
2. The application loader checks whether the class has already been loaded.
3. If not, the loader delegates up to the platform loader.
4. The platform loader further delegates up to the bootstrap loader.
5. If the parent loaders cannot find it, the appropriate loader searches for the class in the sources it manages.
6. If it is not found, the JVM throws `ClassNotFoundException` or a related error depending on the API and the timing of loading/linking.

The model above helps explain the common flow, but it is not a mandatory contract for every custom loader. A custom-written `ClassLoader` can change the strategy in `loadClass`; the built-in loaders also have specialized mechanisms for handling classes in modules.

Example of observing the parent:

```java
ClassLoader app = ClassLoader.getSystemClassLoader();
ClassLoader platform = ClassLoader.getPlatformClassLoader();

System.out.println(app.getParent() == platform); // usually true
System.out.println(platform.getParent());        // null: bootstrap
```

Do not use `toString()` or the internal implementation class name of a loader as conditional logic. Compare loader objects or use public APIs when identification is needed.

## 5. Classpath and Module Path

Since Java 9, there are two common ways to supply code to an application:

| Code source | How declared | Runtime module |
| --- | --- | --- |
| Classpath | `-cp`, `-classpath`, `--class-path` | Classes typically belong to the unnamed module of the corresponding class loader. |
| Module path | `--module-path`, `-p` | Contains named modules; the JVM resolves dependencies and places them into a module layer. |

### 5.1. Classes on the Classpath

Example:

```bash
javac -d out src/com/example/Main.java
java -cp out com.example.Main
```

In the default configuration, `com.example.Main` is loaded by the application/system class loader. Classes on the classpath belong to the unnamed module associated with that loader. An unnamed module has no name to declare in `module-info.java`, yet it still has a `Module` object at runtime.

A class loader can have its own unnamed module. Therefore, two different loaders can be associated with two different unnamed modules.

### 5.2. Named Modules on the Module Path

A modular project can have the structure:

```text
src/
└── com.example.app/
    ├── module-info.java
    └── com/example/Main.java
```

Contents of `module-info.java`:

```java
module com.example.app {
    requires java.sql;
}
```

Compile and run:

```bash
javac --module-source-path src -d mods -m com.example.app
java --module-path mods -m com.example.app/com.example.Main
```

The JVM resolves module `com.example.app` along with its required dependencies. The modules are placed in a module layer and associated with the appropriate class loader. In the default configuration, the application/system loader can load multiple named modules on the module path; **there is no rule that every module always needs its own class loader**.

The module path determines which modules can be resolved, whereas the loader is responsible for defining the module's classes. The module graph and the loader hierarchy are related, but they are not the same graph.

## 6. How Are Modules Linked to Class Loaders?

A `Module` object represents a module at runtime. A named module is associated with a class loader and belongs to a module layer. A class loader can define classes for multiple modules; therefore, you cannot infer a module name solely from the loader's name.

Useful APIs:

- `SomeClass.class.getClassLoader()` returns the loader that defined the class; returns `null` if the class was defined by the bootstrap loader.
- `SomeClass.class.getModule()` returns the runtime module containing the class.
- `module.getClassLoader()` returns the loader associated with the module; may be `null` for modules defined by the bootstrap loader.
- `module.getLayer()` indicates the module layer containing the module, if present.
- `ClassLoader.getUnnamedModule()` returns the unnamed module associated with the current loader.

Example:

```java
Class<?> type = java.sql.Driver.class;

ClassLoader loader = type.getClassLoader();
Module module = type.getModule();

System.out.println("Class: " + type.getName());
System.out.println("Loader: " + loader);
System.out.println("Module: " + module.getName());
System.out.println("Module loader: " + module.getClassLoader());
System.out.println("Layer: " + module.getLayer());
```

`java.sql.Driver` belongs to the `java.sql` module. The specific loader can be observed directly when running on your JDK. Do not hard-code loader names or internal implementation classes, because implementation details may vary across distributions/runtimes.

### Module Is Not Synonymous with Class Loader

Distinguish these three concepts:

- **Module:** the unit of package encapsulation that declares `requires`, `exports`, `opens`, `uses`, `provides`, and establishes access boundaries.
- **Class loader:** the mechanism for locating and defining classes at runtime.
- **Module layer:** a collection of resolved and linked modules at runtime; a layer can have parent relationships with other layers.

Two modules can share the same class loader. Conversely, an application can create a new module layer with new loaders to isolate groups of modules. The fact that a loader can load bytecode does not automatically grant access to every package of a module; JPMS readability and `exports` rules still apply.

## 7. Module Layers and Custom Class Loaders

Module layers allow an application to build a separate module region after the JVM has started. This feature is useful for plugin systems, dynamically extensible applications, or platforms that need to load multiple components by configuration.

The boot layer can be obtained with:

```java
ModuleLayer bootLayer = ModuleLayer.boot();
System.out.println(bootLayer.modules().size());
System.out.println(bootLayer.findModule("java.base").isPresent());
```

When creating a new layer, Java provides loader configuration options:

- `defineModulesWithOneLoader(...)`: the modules in the new layer share a single loader whose parent is specified.
- `defineModulesWithManyLoaders(...)`: each module in the new layer is associated with its own loader, with the specified parent.
- `defineModules(...)`: allows the application to supply a function mapping module names to class loaders.

These methods belong to the `ModuleLayer` API. Before creating a layer, an application typically locates modules using `ModuleFinder`, creates a `Configuration` via the resolve/resolveAndBind APIs, and only then defines the layer. Resolving determines the modules and dependencies; defining the layer associates modules with loaders.

Do not create a separate class loader for each module merely because the module is named. Choose a strategy based on isolation requirements, class sharing, plugin lifecycle, and dependency management capabilities.

## 8. Inspecting Class Loaders and Modules Programmatically

The following example runs as a modular application to observe the loaders of classes belonging to different modules.

`src/com.example.inspect/module-info.java`:

```java
module com.example.inspect {
    requires java.sql;
}
```

`src/com.example.inspect/com/example/inspect/LoaderInfo.java`:

```java
package com.example.inspect;

public class LoaderInfo {
    public static void main(String[] args) {
        printInfo(String.class);
        printInfo(java.sql.Driver.class);
        printInfo(LoaderInfo.class);

        ClassLoader platform = ClassLoader.getPlatformClassLoader();
        ClassLoader system = ClassLoader.getSystemClassLoader();

        System.out.println("Platform loader: " + platform);
        System.out.println("System loader: " + system);
        System.out.println("System parent is platform: "
                + (system.getParent() == platform));
        System.out.println("Platform parent: " + platform.getParent());
    }

    private static void printInfo(Class<?> type) {
        ClassLoader loader = type.getClassLoader();
        Module module = type.getModule();

        String loaderRole;
        if (loader == null) {
            loaderRole = "bootstrap";
        } else if (loader == ClassLoader.getPlatformClassLoader()) {
            loaderRole = "platform";
        } else if (loader == ClassLoader.getSystemClassLoader()) {
            loaderRole = "application/system";
        } else {
            loaderRole = loader.getClass().getName();
        }

        String moduleName = module.isNamed()
                ? module.getName()
                : "<unnamed>";

        System.out.printf(
                "%s | loader=%s | module=%s%n",
                type.getName(), loaderRole, moduleName
        );
    }
}
```

Compile and run:

```bash
javac --module-source-path src -d mods -m com.example.inspect
java --module-path mods -m com.example.inspect/com.example.inspect.LoaderInfo
```

The output typically shows:

- `java.lang.String` is defined by the bootstrap loader; `getClassLoader()` returns `null`.
- `java.sql.Driver` belongs to the `java.sql` module; the printed loader depends on how the JDK assigns platform classes.
- `LoaderInfo` belongs to the `com.example.inspect` module and is typically defined by the application/system loader in the default configuration.
- The system loader typically has the platform loader as its parent; the parent of the platform loader is represented by `null`.

Use the output on your actual JDK to observe this. Do not rely on the specific `toString()` string because it may vary by implementation.

## 9. Defining Loader and Context Class Loader

In addition to the defining class loader, Java also has the **thread context class loader**:

```java
ClassLoader defining = LoaderInfo.class.getClassLoader();
ClassLoader context =
        Thread.currentThread().getContextClassLoader();

System.out.println("Defining loader: " + defining);
System.out.println("Context loader: " + context);
```

These two loaders can differ:

- The defining loader is the loader that defined the class in question. It determines the runtime identity of the class.
- The context class loader is the loader attached to the current thread, which can be set by a host/framework so library code can load resources or providers supplied by the application.

Some frameworks and mechanisms such as `ServiceLoader.load(...)` use the context class loader in their corresponding overloads. Therefore, when a framework fails to find a plugin even though the application classes are already loaded, check the context loader, module visibility, and provider configuration rather than checking only the defining loader.

The context loader does not replace the loader parent relationship, nor does it automatically grant `exports` permissions to a module.

## 10. Common Errors and How to Handle Them

### 10.1. `ClassNotFoundException`

Typically occurs when an application requests to load a class by name, but the loader used cannot find the bytecode.

Check:

- Is the JAR/directory containing the class on the appropriate classpath or module path?
- Is the fully qualified class name correct?
- Is the class placed in the correct module and package?
- Is the framework using the defining loader or the context class loader?
- For the module path, was the module resolved into the running layer?

### 10.2. `NoClassDefFoundError`

This is a linking or class-usage error when the JVM cannot find a required definition at that moment. It can happen after a failed load/initialization or when a runtime dependency is missing. Read the root cause and stack trace; do not try to fix it by adding random JARs to the classpath.

### 10.3. `ClassCastException` Even Though Two Classes Have the Same Name

A plugin might be loaded by loader A, while the API used by the application is loaded by loader B. If each loader separately defines a class with the same binary name, the JVM considers them two different types and the cast can fail.

How to handle:

- Place the shared API in a parent loader visible to both the host and the plugin.
- Avoid packaging duplicate copies of the shared API inside each plugin.
- Design consistent parent delegation.
- Verify both the class name and the defining loader when diagnosing.

### 10.4. `IllegalAccessError` or Module Access Errors

The class may have been loaded, yet the caller module cannot read the module containing the type, or the package has not been exported appropriately. Successful class loading does not mean access permission has been granted.

Check `requires`, `exports`, and module layer relationships. For legacy integration, options such as `--add-reads` or `--add-exports` can assist with diagnostics, but a long-term design should be expressed in the module descriptor.

### 10.5. Confusion Between Platform and Application Loaders

Not every class in the JDK is defined by the bootstrap loader. Check using `Class.getClassLoader()` and `Class.getModule()` instead of inferring from package prefixes like `java.*` or `jdk.*`.

## 11. Design Principles When Using Class Loaders with Modules

1. **Let the default loaders do their job when there are no special requirements.** Typical applications should use the module path/classpath and the built-in loaders.
2. **Keep shared APIs in a shareable location.** For plugins, the API exchanged between the host and plugins should be defined by a common parent loader.
3. **Distinguish class loading from module access permissions.** If you encounter `not visible` or `IllegalAccessError` errors, check the module graph and exports; changing the loader will not necessarily solve the right problem.
4. **Only create separate loaders when there is an isolation need.** Clearly define lifecycle, dependencies, API sharing capabilities, and resource release mechanisms.
5. **Do not assume one module corresponds to one loader.** A single loader can define multiple modules within the same layer.
6. **Do not hard-code internal implementation names.** Prefer public APIs such as `getPlatformClassLoader()`, `getSystemClassLoader()`, `Class.getClassLoader()`, and `Class.getModule()`.
7. **Check the context class loader when integrating frameworks.** A framework may use the thread's loader to locate providers/resources instead of the loader that defined the framework itself.

## 12. Self-Check Exercises

**Exercise 1.** `String.class.getClassLoader()` returns `null`. Does that mean `String` has not been loaded?

**Answer:** No. `null` represents the bootstrap class loader, the foundational loader that is not returned as an ordinary `ClassLoader` object.

**Exercise 2.** In the default configuration, what is the parent of the system/application class loader?

**Answer:** The platform class loader. The parent of the platform class loader is the bootstrap loader and is represented by `null`.

**Exercise 3.** Must a named module on the module path have its own class loader?

**Answer:** No. Multiple named modules can be defined by the same class loader. A module layer lets you choose a single-loader, many-loaders, or custom-mapping strategy.

**Exercise 4.** Two different class loaders both load the class `com.demo.Plugin`. Can the two classes be cast to each other merely because their names are the same?

**Answer:** No. Class identity also depends on the defining loader; two classes defined by two different loaders are two different runtime types.

**Exercise 5.** A framework fails to find a provider supplied by the application. Besides the framework's defining loader, what should you check?

**Answer:** Check the thread context class loader, `ServiceLoader`/provider configuration, module `uses` and `provides` if using JPMS, as well as module resolution capability and package access permissions.

## Key Takeaways

The bootstrap loader loads core classes; the platform loader loads platform classes assigned to it; the application/system loader loads application code and usually application named modules on the module path. In JPMS, modules define dependencies and package boundaries, while class loaders define classes at runtime. A module is not synonymous with a loader, and a class with the same name can still be a different type if the defining loader differs.