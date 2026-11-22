# Identifying a Class's Module with getModule()

## 1. Objectives

In the Java Platform Module System (JPMS, since Java 9), a class is associated with a `java.lang.Module` object at runtime. The `Class.getModule()` method reveals **which module actually contains that class** in the JVM.

After this lesson, you will be able to:

- Call `SomeClass.class.getModule()` to identify the module of a loaded class.
- Distinguish named modules and the unnamed module (classpath) using `isNamed()` and `getName()`.
- Understand the results for JDK library classes, application classes, primitive types, and array types.
- Read `ModuleDescriptor`, `ModuleLayer`, and the class loader to analyze runtime context.
- Use `canRead()`, `isExported()`, and `isOpen()` to inspect cross-module access permissions.
- Avoid confusing package names, JAR names, Maven artifact names, and JPMS module names.

The examples use Java 11 or later; `Class.getModule()` itself was introduced in Java 9.

## 2. What Does Class.getModule() Return?

Method declaration in `java.lang.Class`:

~~~java
public Module getModule()
~~~

The result is a `java.lang.Module` object representing the module the class belongs to at runtime. The `Module` object holds module identity information, relationships with its layer and class loader, and supports checking readability of other modules and package open/export status.

Basic usage:

~~~java
Module module = String.class.getModule();

System.out.println(module.isNamed()); // true
System.out.println(module.getName());  // java.base
~~~

`String` belongs to the foundational module `java.base`. An application class running on the **classpath** normally belongs to the **unnamed module** of the class loader that loaded it:

~~~java
Module current = MyApp.class.getModule();

System.out.println(current.isNamed()); // false if MyApp runs on the classpath
System.out.println(current.getName());  // null for an unnamed module
~~~

The example output depends on how you **run** the application. If `MyApp` is compiled and launched as a named module, `isNamed()` will be `true` and `getName()` will return the declared module name.

**Important distinction:** package `com.example.demo` is not necessarily module `com.example.demo`. The same package name can appear in different module contexts; you cannot determine a module solely from `getPackageName()`.

## 3. Module Methods Commonly Used Alongside getModule()

| Method | Meaning |
| --- | --- |
| `module.isNamed()` | `true` if it is a named module; `false` if it is an unnamed module. |
| `module.getName()` | The named module's name; **`null` for an unnamed module**. |
| `module.getDescriptor()` | `ModuleDescriptor` of a named module; `null` if unnamed. |
| `module.getLayer()` | The layer containing the module if any; may be `null`. |
| `module.getClassLoader()` | The class loader defining the module; may be `null` for the bootstrap loader. |
| `module.getPackages()` | Packages known to belong to this module; not a list of all classes. |
| `module.canRead(other)` | Whether the current module has a readability relationship to another module. |
| `module.isExported(pkg)` | Whether the package is exported unconditionally. |
| `module.isExported(pkg, target)` | Whether the package is exported to the target module. |
| `module.isOpen(pkg, target)` | Whether the package is open for deep reflection from the target module. |

Do not call `module.getName().equals(...)` directly without checking `isNamed()`, because `getName()` can be `null`. Likewise, check `getDescriptor() != null` before accessing descriptor directives.

A named module may reside in the boot layer or a custom layer. An unnamed module has no `ModuleDescriptor` and does not belong to a `ModuleLayer`; `getLayer()` is `null`. For a dynamically created named module not yet placed into a layer, `getLayer()` can also be `null`, so do not infer `isNamed()` from the layer alone.

## 4. Example 1: Inspecting JDK Classes and an Application on the Classpath

Create `ModuleInspector.java`:

~~~java
import java.lang.module.ModuleDescriptor;

public class ModuleInspector {

    private static void inspect(Class<?> type) {
        Module module = type.getModule();
        ModuleDescriptor descriptor = module.getDescriptor();

        System.out.println("Class: " + type.getTypeName());
        System.out.println("  named: " + module.isNamed());
        System.out.println("  name: " +
                (module.isNamed() ? module.getName() : "<unnamed>"));
        System.out.println("  descriptor: " +
                (descriptor == null ? "<none>" : descriptor.name()));
        System.out.println("  layer: " +
                (module.getLayer() == null ? "<none>" : "present"));
        System.out.println();
    }

    public static void main(String[] args) {
        inspect(String.class);
        inspect(java.util.ArrayList.class);
        inspect(ModuleInspector.class);
        inspect(int.class);
        inspect(String[].class);
        inspect(ModuleInspector[].class);
    }
}
~~~

Compile and run in classpath mode:

~~~sh
javac ModuleInspector.java
java ModuleInspector
~~~

Key observations you can make:

| Class | Module at runtime |
| --- | --- |
| `String.class` | Named module `java.base`. |
| `java.util.ArrayList.class` | Named module `java.base`. |
| `ModuleInspector.class` | Unnamed module of the class loader that loaded the application, when run on the classpath. |
| `int.class` | `java.base` even though it is a primitive type. |
| `String[].class` | Same module as its element type `String`, namely `java.base`. |
| `ModuleInspector[].class` | Same module as its element type `ModuleInspector`, namely the unnamed module when run on the classpath. |

For primitive types or `void.class`, `getModule()` returns `java.base`. For array types, the result is the module of the **element type**. Java does not assign a separate standalone module just for arrays.

Note: `getModule()` returns a module object, not merely a name string; `Module.toString()` is useful for logging, yet should not be used as an API to parse module names. Call `isNamed()` and `getName()` directly.

## 5. Example 2: Same Source Code, Run as a Named Module

To see the difference between the classpath and the module path, create the project structure:

~~~text
src/
  com.example.modulecheck/
    module-info.java
    com/example/modulecheck/Main.java
~~~

**`src/com.example.modulecheck/module-info.java`**

~~~java
module com.example.modulecheck {
    exports com.example.modulecheck;
}
~~~

**`src/com.example.modulecheck/com/example/modulecheck/Main.java`**

~~~java
package com.example.modulecheck;

public class Main {
    public static void main(String[] args) {
        print(Main.class);
        print(String.class);
    }

    private static void print(Class<?> type) {
        Module module = type.getModule();
        System.out.printf(
                "%s -> named=%s, module=%s%n",
                type.getName(),
                module.isNamed(),
                module.getName()
        );
    }
}
~~~

Compile in modular form:

~~~sh
javac --module-source-path src -d out -m com.example.modulecheck
~~~

Then run via the **module path** with an explicit root module:

~~~sh
java --module-path out -m com.example.modulecheck/com.example.modulecheck.Main
~~~

Expected output:

~~~text
com.example.modulecheck.Main -> named=true, module=com.example.modulecheck
java.lang.String -> named=true, module=java.base
~~~

Class `Main` is in a named module because the JVM resolved and loaded `com.example.modulecheck` into a module layer. The `-m` option specifies the module and main class. The `out` directory contains the exploded module at `out/com.example.modulecheck`.

If you run that same application class directly via the classpath:

~~~sh
java -cp out/com.example.modulecheck com.example.modulecheck.Main
~~~

then `Main.class.getModule()` will reflect the **unnamed module**, even though the class directory contains `module-info.class`. Having a descriptor file on disk does not automatically turn a class run on the classpath into a named module.

Therefore, check **how the application is actually launched** before concluding which module a class is in.

## 6. Combining Reflection and getModule()

When you only know the fully qualified name of a class at runtime, you can load/look up the `Class<?>` first, then ask for its module:

~~~java
public class LookupModule {
    public static void main(String[] args) throws ClassNotFoundException {
        String className = "java.util.ArrayList";

        Class<?> type = Class.forName(className);
        Module module = type.getModule();

        System.out.println("Class: " + type.getName());
        System.out.println("Module: " + module.getName());
        System.out.println("Named: " + module.isNamed());
    }
}
~~~

`Class.forName(String)` initializes the class by default when appropriate. If you only need class information without triggering initialization, you can use the overload:

~~~java
Class<?> type = Class.forName(
        "java.util.ArrayList",
        false,
        ClassLoader.getSystemClassLoader()
);
Module module = type.getModule();
~~~

This example uses a JDK class that can be found by the loader used. For a custom plugin class, you must pass the right class loader and ensure the named module has been resolved and placed into the appropriate layer; otherwise, `Class.forName` can throw `ClassNotFoundException`.

Distinguish carefully:

- `Class.forName(...)` locates/loads a class via the class-loader mechanism.
- `type.getModule()` retrieves the module attached to that `Class<?>` object.
- `ModuleFinder.find(name)` locates a **module definition** on paths/module sources; it does not guarantee that the module has been resolved, loaded classes, or added to a layer.

`getModule()` does not automatically search a JAR on the module path or load an arbitrary class from a module name. You must first obtain the corresponding `Class<?>` object.

## 7. Checking Readability, Exports, and Opens

Knowing which module a class belongs to is only the first step. When analyzing cross-module access errors, inspect three relationships separately:

1. **Readability:** Can the calling module read the module containing the class? Use `caller.canRead(target)`.
2. **Exports:** Is the package containing the public type exported to the calling module? Use `target.isExported(packageName, caller)`.
3. **Opens:** Is the package opened for deep reflection from the calling module? Use `target.isOpen(packageName, caller)`.

Example:

~~~java
public class CheckAccess {
    public static void main(String[] args) {
        Class<?> targetType = java.util.ArrayList.class;

        Module caller = CheckAccess.class.getModule();
        Module target = targetType.getModule();
        String pkg = targetType.getPackageName();

        System.out.println("Caller module: " +
                (caller.isNamed() ? caller.getName() : "<unnamed>"));
        System.out.println("Target module: " + target.getName());
        System.out.println("Package: " + pkg);

        System.out.println("Can read: " + caller.canRead(target));
        System.out.println("Exported to caller: " +
                target.isExported(pkg, caller));
        System.out.println("Open to caller: " +
                target.isOpen(pkg, caller));
    }
}
~~~

Run with:

~~~sh
javac CheckAccess.java
java CheckAccess
~~~

`java.util` belongs to `java.base` and is exported to normal applications, so the example can use public classes such as `ArrayList`. However, that **does not mean** every private member of `ArrayList` can be accessed via reflection.

### How Does exports Differ from opens?

Suppose a module has the descriptor:

~~~java
module com.example.library {
    exports com.example.library.api;
    opens com.example.library.internal;
}
~~~

- `exports com.example.library.api` allows modules reading the library to use public types in the API package under normal access.
- `opens com.example.library.internal` allows deep reflection on the internal package under JPMS rules, yet does not automatically turn the internal package into a public API importable for compilation.
- `exports ... to ...` or `opens ... to ...` can be used to specify target modules.

If a package is only exported and not opened, calling `setAccessible(true)` on a private member via reflection can be blocked, e.g. with `InaccessibleObjectException`. `getModule()` itself does not bypass encapsulation rules.

**Interpretation limits:** `canRead` reflects the current readability relationship between module objects; `isExported` and `isOpen` reflect package conditions toward the target module. These values are diagnostic clues, yet accessing a member still depends on class/member visibility and other reflection rules.

## 8. ModuleDescriptor, ModuleLayer, and Class Loader

When analyzing why the same class name behaves differently across two runtime environments, do not log only `getName()`. Record the relevant context:

~~~java
import java.lang.module.ModuleDescriptor;

public class DescribeModule {
    public static void main(String[] args) {
        Module module = DescribeModule.class.getModule();
        ModuleDescriptor descriptor = module.getDescriptor();

        System.out.println("Name: " +
                (module.isNamed() ? module.getName() : "<unnamed>"));
        System.out.println("Descriptor: " +
                (descriptor == null ? "<none>" : descriptor.name()));
        System.out.println("Layer: " +
                (module.getLayer() == null
                        ? "<none>"
                        : module.getLayer().toString()));
        System.out.println("Class loader: " +
                (module.getClassLoader() == null
                        ? "<bootstrap>"
                        : module.getClassLoader().getClass().getName()));
    }
}
~~~

`ModuleDescriptor` describes the module structure, including its name, `requires`, `exports`, `opens`, `uses`, and `provides`. An unnamed module has no descriptor, so the program must handle `null`.

`ModuleLayer` is a group of modules resolved and defined to run together with class loaders. Loaded system modules typically belong to the boot layer; an application or plugin system can define modules in its own layer.

`ClassLoader` governs class definition. For platform classes like `String`, the loader may be the bootstrap loader, represented by `null`. For application classes, the value depends on the environment and loading mechanism.

Two modules with the same name appearing in **two different layers or class loaders** are not necessarily the same `Module` object. Similarly, two classes with the same binary name defined by two different loaders are distinct `Class<?>` objects, and their `getModule()` results may also differ. When debugging plugins or multi-layer applications, logging the module, layer, and class loader together helps pinpoint the context accurately.

## 9. Real-World Scenarios

### 9.1. Library Class Placed on the Classpath

A library JAR placed on the classpath does not automatically become a named module. Its classes typically belong to the unnamed module of the loader that loaded them. If the same JAR is used as an automatic module on the module path and is actually resolved, its classes belong to a named automatic module. Check its state with:

~~~java
Module m = SomeLibraryClass.class.getModule();
System.out.println(m.isNamed());
System.out.println(m.getName());
~~~

If it is a named module, you can inspect the descriptor:

~~~java
if (m.isNamed() && m.getDescriptor() != null) {
    System.out.println(m.getDescriptor().isAutomatic());
}
~~~

Do not guess a module name from Maven `groupId:artifactId` or a JAR filename. An automatic-module name can be declared via manifest or derived from the filename; the runtime result from `getModule()` is the reliable source to confirm how the loaded class was placed.

### 9.2. Class Whose Package Name Matches a Module Name

For example, class `org.example.api.Service` does not automatically reside in module `org.example.api`. The descriptor might name the module `org.example.service`, or the class might belong to the unnamed module. Only `Service.class.getModule()` reflects the class's module at runtime.

### 9.3. Unable to Import a Public Class Even Though Found in a JAR

Check whether the class actually resides in a resolved named module, whether the calling module reads the target module, and whether the package is exported. A public class in an unexported package can still be inaccessible to another module.

### 9.4. Reflection Denied

Use `targetType.getModule()` to identify the module containing the class, then check `isOpen(pkg, caller)` for the exact package and calling module. If the package is not open, design an appropriate API/public access or add an intentional `opens` declaration; avoid assuming `setAccessible(true)` will always succeed.

### 9.5. Class in a Module with No Layer

A newly created named module constructed via runtime mechanisms and not yet assigned to a layer can have `getLayer() == null`. Therefore, when writing diagnostics, use `isNamed()` to decide named vs. unnamed, and treat the layer as an additional attribute.

## 10. Common Errors

| Symptom | Causes to Consider | How to Check |
| --- | --- | --- |
| `getName()` returns `null` | The class belongs to an unnamed module. | Call `isNamed()`, inspect launch command `-cp`/`--module-path`. |
| `getDescriptor()` is `null` | Unnamed modules have no descriptor. | Check `isNamed()` before accessing the descriptor. |
| Expected module X but got something else | Class was loaded from classpath, a different loader, or a different layer. | Print `type.getModule()`, loader, and layer; inspect launch command. |
| `Class.forName` throws `ClassNotFoundException` | Loader cannot see the class, or module was not resolved/configured. | Check class loader, module resolution, and supplied paths. |
| `IllegalAccessError` or linkage access error | Readability/exports/visibility requirements not met. | Check `canRead`, `isExported`, and class/member access permissions. |
| `InaccessibleObjectException` during deep reflection | Package is not appropriately opened or access is restricted. | Check `isOpen` and `opens` declarations / relevant runtime options. |
| Same class name gives different module results | Multiple loaders/layers define separate classes. | Compare `Class<?>`, module, layer, and loader rather than just name strings. |

## 11. Practice Exercises

1. Run `ModuleInspector` in section 4. Predict the results for `String.class`, `int.class`, and `ModuleInspector[].class` before observing the output.
2. Compile the `com.example.modulecheck` example. Run it both with `--module-path ... -m ...` and with `-cp ...`, and explain why `Main.class.getModule()` changes.
3. In a named module program, print `module.getDescriptor().requires()` and `module.getLayer()`. Compare with an unnamed module.
4. Create module `com.example.library` with a public package that is `exports`-ed. Write module `com.example.client` with `requires com.example.library;`. From client, check `canRead` and `isExported(pkg, clientModule)` for the library package.
5. In exercise 4, try adding an internal package that is neither exported nor opened. Explain the difference between the compiler disallowing importing a public type from the internal package and reflection being unable to open private members.
6. If you have a library running on both classpath and module path, observe `isNamed()`, `getDescriptor()`, and `getName()` for a library class in both modes.

Self-check prompt questions: Can `Class.getModule()` return `null`? When does `Module.getName()` return `null`? How does a class on the classpath differ from a class in a named module? Why is `canRead() == true` not sufficient for deep reflection? Which module do primitive types and array types belong to?

## 12. Key Takeaways

`Class.getModule()` returns **the module associated with the existing class at runtime**. For named modules, use `isNamed()` and `getName()` to get the name. For unnamed modules, `getName()` is `null` and `getDescriptor()` is also `null`. `String.class`, primitive types, and arrays whose elements belong to the JDK can return `java.base`, while application classes on the classpath normally belong to an unnamed module.

To evaluate cross-module accessibility, inspect `canRead`, `isExported`, and `isOpen`. To troubleshoot differences between launch environments, inspect the layer and class loader as well. Most importantly, **a class's module is determined by how the class was loaded**, not merely by its package name or the JAR's location on disk.