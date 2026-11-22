# Using Reflection to Observe Modules Without Breaking Encapsulation

Since Java 9, the Java Platform Module System (JPMS) places each module within clear boundaries: which modules can be read, which packages are exposed, and which packages allow deep access via reflection. When debugging or building runtime inspection tools, we often need to know which module a class belongs to and what kinds of access that module permits.

This information can be observed using the Reflection API combined with the Module API. Reading metadata does not mean opening access to private fields or methods. The goal of this lesson is to inspect current structure and access permissions without calling setAccessible, without mutating the module graph, and without reading internal data.

## 1. From Class to Module

Every Class object can report the module containing that class via Class.getModule():

~~~java
Module module = String.class.getModule();

System.out.println(module.getName()); // java.base
System.out.println(module.isNamed()); // true
~~~

Some commonly used APIs:

| API | Meaning |
| --- | --- |
| Class.getModule() | Gets the module containing a class |
| Module.getName() | Gets the module name; returns null if it is an unnamed module |
| Module.isNamed() | Checks whether the module is named |
| Module.getDescriptor() | Gets the module descriptor; may return null for an unnamed module |
| Module.getPackages() | Gets the packages belonging to the module |
| Module.getLayer() | Gets the ModuleLayer containing the module; may return null |
| Module.canRead(other) | Checks whether the current module can read module other |
| Module.isExported(package, other) | Checks whether the package is exported to module other |
| Module.isOpen(package, other) | Checks whether the package is open for deep reflection from module other |

The Module API is a runtime API. It indicates which module the JVM associates with a running class, even when the class was loaded from the classpath or from a module layer.

### Named modules and unnamed modules

- **Named module** has a name and is typically described by a module-info.java file. Example: java.base.
- **Unnamed module** typically contains classes loaded from the classpath. It has no name and Module.getDescriptor() returns null.
- **Automatic module** is typically created when placing a JAR onto the module path without the JAR declaring module-info.java. It is still a named module; ModuleDescriptor.isAutomatic() indicates this case.

Therefore, do not assume every class belongs to a named module or has a ModuleDescriptor.

## 2. Reading ModuleDescriptor to view module structure

For a named module, Module.getDescriptor() returns a ModuleDescriptor. The descriptor reflects declarations in module-info.java, such as:

- requires: which modules this module depends on and reads.
- exports: which packages are exposed so other modules can use public types.
- opens: which packages allow other modules to perform deep access via reflection.
- uses and provides: declarations related to Java ServiceLoader.
- packages: the list of packages recorded in the descriptor.

You can read these declarations without opening packages:

~~~java
Module module = String.class.getModule();
ModuleDescriptor descriptor = module.getDescriptor();

if (descriptor != null) {
    descriptor.requires().forEach(requirement ->
        System.out.println("requires " + requirement.name())
    );

    descriptor.exports().forEach(export ->
        System.out.println("exports " + export.source())
    );

    descriptor.opens().forEach(open ->
        System.out.println("opens " + open.source())
    );
}
~~~

ModuleDescriptor is an immutable description of module configuration. If an application changes access permissions at runtime using APIs such as addOpens or addExports, the descriptor is not the place to verify the effective state after that change. When you need to check current access permissions, use methods on Module such as isOpen and isExported.

## 3. Distinguishing requires, exports, and opens

These three concepts answer three different questions:

| Declaration/API | Question answered | Effect |
| --- | --- | --- |
| requires / canRead | Can the calling module read the target module? | Establishes a readability relationship |
| exports / isExported | Does the package expose public API to the calling module? | Allows using public types and public members under Java access rules |
| opens / isOpen | Does the package allow deep reflection from the calling module? | Allows reflection to bypass certain standard access checks when opened |

Example module declaration:

~~~java
module inventory {
    requires java.sql;

    exports com.example.inventory.api;

    opens com.example.inventory.model
        to com.fasterxml.jackson.databind;
}
~~~

In this example:

- Another module can use public API in the com.example.inventory.api package if that module reads inventory.
- The com.example.inventory.model package is opened to the Jackson module so the framework can perform deep reflection.
- Exporting a package does not automatically open that package. A package can be exported while remaining closed to accessing private fields.
- Opens does not replace exports. Opening a package for reflection does not mean exposing that package as standard Java API.

From the calling module side, check in the correct direction:

~~~java
Module caller = MyApplication.class.getModule();
Module target = SomeLibrary.class.getModule();
String packageName = SomeLibrary.class.getPackageName();

boolean readable = caller.canRead(target);
boolean exported = target.isExported(packageName, caller);
boolean open = target.isOpen(packageName, caller);
~~~

Note: canRead is called on the calling module; isExported and isOpen are called on the target module, with the calling module as an argument. Only one of these conditions is not enough to conclude that every reflection operation is permitted. The public, private, protected, and package-private modifiers and Java's access rules still apply.

## 4. Example: writing a runtime module observation tool

The following example takes a Class, prints the module containing the class, checks relationships between the calling module and the target module, reads declarations in the descriptor, and then lists field names. The field-listing part only reads metadata such as names and modifiers; the program does not read field values.

~~~java
import java.lang.module.ModuleDescriptor;
import java.lang.reflect.Field;
import java.lang.reflect.Modifier;
import java.util.Comparator;
import java.util.Objects;

public class ModuleInspector {

    public static void main(String[] args) {
        inspect(String.class);
        inspect(ModuleInspector.class);
        listBootLayerModules();
    }

    private static void inspect(Class<?> type) {
        Module target = type.getModule();
        Module caller = ModuleInspector.class.getModule();
        String packageName = type.getPackageName();

        System.out.printf("%nClass: %s%n", type.getName());
        System.out.printf(
            "Module: %s (named=%s)%n",
            Objects.toString(target.getName(), "<unnamed>"),
            target.isNamed()
        );

        System.out.printf(
            "Caller reads target: %s%n",
            caller.canRead(target)
        );
        System.out.printf(
            "Package exported to caller: %s%n",
            target.isExported(packageName, caller)
        );
        System.out.printf(
            "Package open to caller: %s%n",
            target.isOpen(packageName, caller)
        );

        ModuleDescriptor descriptor = target.getDescriptor();

        if (descriptor == null) {
            System.out.println(
                "No ModuleDescriptor: this is an unnamed module."
            );
        } else {
            System.out.printf(
                "Automatic module: %s%n",
                descriptor.isAutomatic()
            );
            System.out.printf(
                "Open module: %s%n",
                descriptor.isOpen()
            );

            System.out.println("Requires:");
            descriptor.requires().stream()
                .sorted(Comparator.comparing(
                    ModuleDescriptor.Requires::name
                ))
                .forEach(requirement ->
                    System.out.printf(
                        "  %s %s%n",
                        requirement.name(),
                        requirement.modifiers()
                    )
                );

            System.out.println("Exports:");
            descriptor.exports().stream()
                .sorted(Comparator.comparing(
                    ModuleDescriptor.Exports::source
                ))
                .forEach(export ->
                    System.out.printf(
                        "  %s -> %s%n",
                        export.source(),
                        export.isQualified()
                            ? export.targets()
                            : "ALL"
                    )
                );

            System.out.println("Opens:");
            descriptor.opens().stream()
                .sorted(Comparator.comparing(
                    ModuleDescriptor.Opens::source
                ))
                .forEach(open ->
                    System.out.printf(
                        "  %s -> %s%n",
                        open.source(),
                        open.isQualified()
                            ? open.targets()
                            : "ALL"
                    )
                );
        }

        System.out.println("Declared fields (metadata only):");
        for (Field field : type.getDeclaredFields()) {
            System.out.printf(
                "  %s %s%n",
                Modifier.toString(field.getModifiers()),
                field.getName()
            );
        }
    }

    private static void listBootLayerModules() {
        System.out.println("%nModules in the boot layer:");

        ModuleLayer.boot().modules().stream()
            .sorted(Comparator.comparing(
                module -> Objects.toString(module.getName(), "")
            ))
            .forEach(module ->
                System.out.println("  " + module.getName())
            );
    }
}
~~~

If run on the classpath, ModuleInspector normally belongs to an unnamed module so its descriptor is null. String.class belongs to the named module java.base. If packaged as a named module, ModuleInspector.class will report the application module name.

ModuleLayer.boot().modules() lists the modules in the boot layer. Applications can create additional custom module layers, so this list does not represent every module layer existing in the JVM.

## 5. Observing member metadata without reading private data

Reflection allows retrieving the list of members declared on a class:

~~~java
Field[] fields = SomeClass.class.getDeclaredFields();

for (Field field : fields) {
    System.out.println(field.getName());
    System.out.println(
        Modifier.toString(field.getModifiers())
    );
}
~~~

getDeclaredFields(), getDeclaredMethods(), and getDeclaredConstructors() help observe class structure, including members with the private modifier. Retrieving this metadata does not imply permission to read or invoke that member.

If you need to check access permission for a specific member, AccessibleObject.canAccess(target) can check current accessibility without enabling the override flag. For an instance field or method, pass the corresponding object; for a static member, pass null.

~~~java
Field field = SomeClass.class.getDeclaredField("status");
Object instance = new SomeClass();

boolean accessible = field.canAccess(instance);
System.out.println("Can access now: " + accessible);
~~~

The check above does not read the field value and does not change the access policy. If the member is static, use field.canAccess(null).

## 6. Why can setAccessible(true) fail?

Before JPMS, many libraries routinely called setAccessible(true) to read private fields. With named modules, this behavior is governed by module controls:

- If the package is not opened to the calling module, the JVM can reject deep reflection.
- setAccessible(true) can throw InaccessibleObjectException.
- trySetAccessible() returns false when access permission cannot be enabled.
- A package that is exported but not opened can still reject deep access to private members.

When the goal is purely observation, do not call setAccessible(true), trySetAccessible(), or use the --add-opens option. Those actions alter or attempt to alter accessibility, making the observation no longer non-intrusive.

If an application genuinely needs deep reflection, ask the module owning the package to open the exact package to the exact calling module, for example via a targeted opens. Only broaden scope when architectural requirements genuinely require it.

## 7. Running the example

You can run the simple example on the classpath using JDK 9 or later:

~~~shell
javac ModuleInspector.java
java ModuleInspector
~~~

To observe the application as a named module, place the following file at src/module-info.java:

~~~java
module app {
}
~~~

Keep ModuleInspector in package com.example.app, then compile and run:

~~~shell
javac -d out src/module-info.java src/com/example/app/ModuleInspector.java
java --module-path out --module app/com.example.app.ModuleInspector
~~~

When run this way, ModuleInspector.class belongs to module app. The calling module is app and the target module of String.class is java.base.

## 8. Common misconceptions

1. **Confusing exports with opens:** exports exposes public API; opens permits deep reflection. The two declarations have different purposes.
2. **Calling canRead on the target module:** the check direction must be caller.canRead(target), because the question is whether the calling module reads the target module.
3. **Assuming you can read a private field because you obtained the Field:** obtaining metadata and reading a value are two different operations.
4. **Assuming a descriptor always exists:** an unnamed module has no ModuleDescriptor.
5. **Assuming the boot layer contains all modules:** an application can create other module layers.
6. **Using setAccessible to check permissions:** this operation interferes with the access mechanism. Use canAccess and Module.isOpen to observe state.
7. **Looking only at module-info.java to conclude runtime state:** the descriptor reflects initial declarations; queries on Module are more suitable when you need to check effective access permissions.

## 9. Recommended inspection workflow

When a reflection library cannot access a class or member, you can inspect in order:

1. Obtain the target class's module with Class.getModule().
2. Obtain the calling code's module with Class.getModule().
3. Check caller.canRead(target).
4. Check target.isExported(packageName, caller) if public API usage is needed.
5. Check target.isOpen(packageName, caller) if the framework needs deep reflection.
6. Read ModuleDescriptor to understand requires, exports, and opens declarations.
7. Use getDeclaredFields or getDeclaredMethods to view metadata; use canAccess to check permission on a specific member.

This approach helps identify module boundaries and the cause of access denial without breaking encapsulation or reading a class's internal data.

## Conclusion

Reflection combined with the Module API provides enough information to observe which module a class belongs to, how the module graph permits reading, which packages are exported, and which packages are open for deep reflection. Prefer Class.getModule(), Module, ModuleDescriptor, ModuleLayer, isExported(), isOpen(), and canRead() for inspection. Only modify access permissions when it is an intentional requirement of the application design.
