# Module::canRead, isExported, and isOpen

## 1. Objectives

In the Java Platform Module System (JPMS), each module can read other modules, expose certain packages to other modules, or open packages so other modules can perform deep access via reflection. Three methods on the **java.lang.Module** class help inspect these three relationships at runtime:

- **canRead(Module other)**: can the current module read the other module?
- **isExported(String packageName)** and **isExported(String packageName, Module other)**: is the package exported unconditionally or exported to a specific module?
- **isOpen(String packageName)** and **isOpen(String packageName, Module other)**: is the package opened unconditionally or opened to a specific module for deep reflection?

The important point is the direction of the method call:

- Call **consumer.canRead(provider)** to ask whether the consuming module reads the providing module.
- Call **provider.isExported(packageName, consumer)** to ask whether the providing module exports the package to the consuming module.
- Call **provider.isOpen(packageName, consumer)** to ask whether the providing module opens the package to the consuming module.

These methods belong to the **Module** class in the **java.lang** package, available since Java 9. No separate import of the Module class is needed.

## 2. What does a Module object represent?

**Module** is a runtime object representing a module identified by the JVM. Every class can report the module that contains it via **Class.getModule()**:

~~~java
Module moduleOfCurrentClass = MyApplication.class.getModule();
Module moduleOfLibraryClass = LibraryApi.class.getModule();
~~~

If you only know the module name, you can look up the module in the boot layer:

~~~java
Module library = ModuleLayer.boot()
        .findModule("com.acme.library")
        .orElseThrow();

Module application = MyApplication.class.getModule();
~~~

A named module has a name and a module descriptor. An unnamed module has no name; each class loader has its own unnamed module for classes that do not belong to a named module. Most applications running on the classpath use an unnamed module.

The three methods under study inspect runtime relationships between Module objects. They do not take a String module name for the **other** parameter; pass a Module object obtained from **Class.getModule()** or **ModuleLayer**.

## 3. canRead(Module other): checking readability

Syntax:

~~~java
boolean canRead(Module other)
~~~

The method is called on the module to be checked. The result is **true** when that module reads the passed-in module.

Example:

~~~java
Module application = MyApplication.class.getModule();
Module library = LibraryApi.class.getModule();

boolean readable = application.canRead(library);
~~~

If **readable** is true, the application module has a readability relationship to the library module in the runtime module graph. If false, application does not read library.

### How is readability established?

For named modules, readability relationships usually start from **requires** directives in module-info.java:

~~~java
module com.acme.application {
    requires com.acme.library;
}
~~~

When the module graph is constructed, com.acme.application reads com.acme.library. The **requires transitive** directive also propagates readability to dependent modules according to module system rules:

~~~java
module com.acme.library {
    requires transitive com.acme.model;
}
~~~

Another module that reads com.acme.library can also read com.acme.model through that transitive edge, provided the relevant modules are in the corresponding graph.

A module always reads itself. In particular, calling **canRead** on an unnamed module always returns true because an unnamed module reads all modules.

### canRead does not mean every package is accessible

Readability only answers the question about module relationships. It does not automatically expose the target module's packages.

Suppose application reads library, but library does not export the package com.acme.internal to application. Application still cannot use public types in that package as normal API just because **application.canRead(library)** returns true.

To access the public API of a package in a named module, you must also check export rules and the accessibility of types/members according to the Java language.

## 4. isExported: checking whether a package is exported

There are two overloads:

~~~java
boolean isExported(String packageName)

boolean isExported(String packageName, Module other)
~~~

The package name must be a fully qualified dot-separated name, such as **com.acme.api**; do not pass a directory path with forward slashes.

### Unconditional export

~~~java
boolean exportedToEveryone =
        library.isExported("com.acme.api");
~~~

The single-parameter overload returns true when the package is exported unconditionally. In module-info.java, the typical case is:

~~~java
module com.acme.library {
    exports com.acme.api;
}
~~~

The package com.acme.api is exported to all other modules, rather than only a specified list of modules.

### Export to a specific module

~~~java
boolean exportedToApplication =
        library.isExported("com.acme.spi", application);
~~~

The two-parameter overload returns true if the package is exported to at least the passed-in module. A qualified export has the form:

~~~java
module com.acme.library {
    exports com.acme.spi to com.acme.plugin;
}
~~~

In this example, the package com.acme.spi is exported to com.acme.plugin. Another module does not automatically receive that export permission.

The method also returns true when checking a package against the module containing the package itself. When called on an unnamed module, the export overloads always return true.

### Important note about opened packages

According to the runtime API contract of **Module.isExported**, a package opened to a target module is also considered exported to that module. Therefore, **isExported(packageName, other)** can return true because the package has been opened, even when module-info.java has no corresponding exports directive.

Similarly, the single-parameter overload returns true if the package is opened unconditionally. Therefore, you should not use the **isExported** result alone to deduce with certainty whether the module descriptor declares an **exports** directive. If you need to read static declarations in the descriptor, inspect **Module.getDescriptor()** and the **ModuleDescriptor.exports()** / **ModuleDescriptor.opens()** sets.

The **isExported** overloads do not check whether the target module reads the current module. Check readability separately with **canRead** when your question requires both relationships.

## 5. isOpen: checking whether a package is open for deep reflection

There are two overloads:

~~~java
boolean isOpen(String packageName)

boolean isOpen(String packageName, Module other)
~~~

**opens** allows the target module to perform deep reflection on types and members in the package, including non-public members, through APIs that support deep access such as **AccessibleObject.setAccessible**, **trySetAccessible**, or **MethodHandles.privateLookupIn** when relevant conditions are met.

### Unconditional open

~~~java
boolean openToEveryone =
        library.isOpen("com.acme.model");
~~~

Corresponding declaration in module-info.java:

~~~java
module com.acme.library {
    opens com.acme.model;
}
~~~

The package com.acme.model is opened to all modules for deep reflection.

A broader declaration is **open module**:

~~~java
open module com.acme.library {
    // Packages in the module are open for deep reflection.
}
~~~

For an open module, **isOpen(packageName)** returns true for packages belonging to that module.

### Open to a specific module

~~~java
boolean openToJson =
        library.isOpen("com.acme.model", jsonFramework);
~~~

Qualified opens only grant package-opening permission to the named module:

~~~java
module com.acme.library {
    opens com.acme.model to com.acme.json;
}
~~~

The module com.acme.json can perform deep reflection on types and members in com.acme.model. Other modules do not gain this open permission merely because they also read com.acme.library.

When calling **isOpen** to check the module containing the package itself, the result is true. When called on an unnamed module, the open overloads always return true. The single-parameter overload also returns true for packages belonging to an open module.

### isOpen does not check readability

**isOpen(packageName, other)** only checks the package-opening relationship; it does not check whether the other module reads the current module.

The Java API specifies that a package open to module M allows code in M to perform deep reflection on the package's types and members. If M needs to obtain a **Lookup** with permission to define classes in that package via **MethodHandles.privateLookupIn**, M must also read the module containing the package.

Therefore, when diagnosing reflection errors, identify the reflection API being used, check whether the package is open to the calling module, and also check readability if the operation requires it.

## 6. Distinguishing readability, exports, and opens

| Relationship | Question | Typical configuration | Check API |
|---|---|---|---|
| Readability | Does module A read module B? | A declares requires B | A.canRead(B) |
| Export | Is B's package exposed to A for public API usage? | B declares exports package [to A] | B.isExported(package, A) |
| Open | Is B's package open to A for deep reflection? | B declares opens package [to A] or is an open module | B.isOpen(package, A) |

Example module descriptor:

~~~java
module com.acme.library {
    exports com.acme.api;
    exports com.acme.spi to com.acme.plugin;
    opens com.acme.model to com.acme.json;
}
~~~

A module using the regular API needs to declare the dependency:

~~~java
module com.acme.application {
    requires com.acme.library;
}
~~~

The three relationships can be interpreted by direction:

1. **application.canRead(library)** asks whether application reads library.
2. **library.isExported("com.acme.api", application)** asks whether the API package is exported to application.
3. **library.isOpen("com.acme.model", jsonFramework)** asks whether the model package is open to the JSON framework for deep reflection.

### exports and opens do not substitute for each other

- **exports** exposes the package's API under standard access rules: public types and their public members can be used by reading modules when other Java conditions are also satisfied.
- **opens** grants deep reflection permission into the package. An opens directive does not by itself make the package an API that can be imported and used directly at compile time.
- A package can be both exported and opened, but the two declarations serve two different purposes.
- At runtime, **Module.isExported** has a special rule treating a package opened to a target module as exported to that module. Keep this in mind when reading API results.

## 7. Runnable example: inspecting the java.sql module

The following example can run on Java 9 and later. When running this class on the classpath, ModuleApiDemo's Module is an unnamed module.

~~~java
public class ModuleApiDemo {
    public static void main(String[] args) {
        Module application = ModuleApiDemo.class.getModule();
        Module sql = java.sql.Driver.class.getModule();

        System.out.println(application.canRead(sql));
        System.out.println(sql.isExported("java.sql", application));
        System.out.println(sql.isOpen("java.sql", application));
    }
}
~~~

Output when running on the classpath with a standard JDK:

~~~text
true
true
false
~~~

Explanation:

- An unnamed module reads all modules, so **application.canRead(sql)** is true.
- The java.sql module exports the java.sql package, so **sql.isExported("java.sql", application)** is true.
- The java.sql package is not opened for deep reflection in this example, so **sql.isOpen("java.sql", application)** is false.

If running the application in a named module, the readability result depends on the module graph and the application's requires directives.

## 8. Example inspecting a library by module name

When you need to inspect a named module without directly referencing a class in the package under inspection, you can obtain the Module from the boot layer:

~~~java
import java.util.Optional;

public class InspectLibrary {
    public static void main(String[] args) {
        Module application = InspectLibrary.class.getModule();

        Module library = ModuleLayer.boot()
                .findModule("com.acme.library")
                .orElseThrow();

        boolean readable = application.canRead(library);
        boolean apiExported =
                library.isExported("com.acme.api", application);
        boolean modelOpen =
                library.isOpen("com.acme.model", application);

        System.out.println("Readable: " + readable);
        System.out.println("API exported at runtime: " + apiExported);
        System.out.println("Model open: " + modelOpen);
    }
}
~~~

The module name passed to **findModule** must be the actual module name defined in the layer's module graph. If the module is not in the boot layer, Optional will be empty; the module may belong to a separate custom layer.

The **apiExported** result here is the export status according to the runtime contract of the Module API. If the package is opened to application, this method can also return true. To determine the exact directives declared in the descriptor, inspect the descriptor separately.

## 9. Checking declarations in ModuleDescriptor

**Module.getDescriptor()** returns the descriptor of a named module; for an unnamed module, the result is null.

~~~java
var descriptor = library.getDescriptor();

if (descriptor != null) {
    descriptor.exports().forEach(export -> {
        System.out.println("exports " + export.source());
    });

    descriptor.opens().forEach(open -> {
        System.out.println("opens " + open.source());
    });
}
~~~

This approach is useful when distinguishing static configuration declared in module-info.java from runtime state affected by module-graph mutation operations. The descriptor describes module metadata; the **canRead**, **isExported**, and **isOpen** methods answer questions about runtime relationships.

## 10. Relationship with addReads, addExports, and addOpens

The **Module** class also has methods that modify certain runtime relationships:

- **addReads(other)** adds a readability edge from the current module to other.
- **addExports(packageName, other)** exports the package to other.
- **addOpens(packageName, other)** opens the package to other for deep reflection.

These methods enforce caller restrictions: for a named module, the calling module must satisfy API conditions to update that module itself; otherwise, it may receive **IllegalCallerException**. **addOpens** also requires the package to already be open to the caller module under the API contract.

These are runtime operations intended for frameworks, containers, or module infrastructure with a specific reason. For typical applications, design dependencies and module-info.java cleanly before considering dynamic relationship changes.

Once a runtime relationship is validly updated, the corresponding inspection methods reflect the new runtime state.

## 11. Common misunderstandings

### Calling in the reverse direction

Wrong direction:

~~~java
library.canRead(application);
~~~

This line asks whether library reads application. If you want to know whether application reads library, you must call:

~~~java
application.canRead(library);
~~~

Similarly, export and open are checked on the module that owns the package:

~~~java
library.isExported("com.acme.api", application);
library.isOpen("com.acme.model", application);
~~~

### Thinking canRead means packages are public

**canRead** does not replace **exports**. A module can read another module without being allowed to access internal packages of that module under standard rules.

### Thinking exports permits reflection on private members

Exporting a package is not the same as opening the package for deep reflection. If a framework needs to access private fields or private constructors, consider **opens** to the appropriate framework module.

### Using isExported to confirm an exports declaration for certain

A package opened to a target module is also considered exported at runtime under the **Module.isExported** contract. To know whether the module descriptor declares exports or opens, read **ModuleDescriptor.exports()** and **ModuleDescriptor.opens()**.

### Thinking isOpen automatically covers every reflection condition

**isOpen** confirms the package-opening relationship with the target module. Each reflection operation must still adhere to the contract of the API being used. For example, **privateLookupIn** also has a readability requirement; read the error message and contract of the specific API.

### Passing the wrong package name

A package name is a full Java name using dots:

~~~java
library.isOpen("com.acme.model", application);
~~~

Do not use **com/acme/model** or a class name like **com.acme.model.User**.

## 12. Rules and edge cases to remember

1. A module always reads itself; **module.canRead(module)** returns true.
2. An unnamed module reads every module; **canRead** on an unnamed module always returns true.
3. The **isExported** and **isOpen** overloads return true when called on an unnamed module.
4. Checking a package against the module containing the package itself also returns true under the contract of overloads taking a Module parameter.
5. A package opened to a target module is also considered exported to that module at runtime.
6. **isExported** and **isOpen** do not check readability; check separately with **canRead** when needed.
7. **isOpen** on an open module returns true for packages belonging to that module.
8. The passed-in package name is the fully qualified name, such as **java.sql** or **com.acme.model**.
9. Passing null to a required parameter of these methods throws **NullPointerException**.
10. These methods inspect runtime state; do not confuse the results with reading the literal directives in module-info.java.

## 13. Self-check exercises and answers

### Exercise 1 — Choose the right call direction

Module app wants to know whether it reads module lib. Which expression should be called?

A. **lib.canRead(app)**

B. **app.canRead(lib)**

**Answer:** B. The method is called on the module whose readability is being checked.

### Exercise 2 — Readability and export

If **app.canRead(lib)** returns true, can app definitely use every public class in every package of lib?

**Answer:** No. The package must still be exported to app, and the types/members must satisfy Java access rules. Readability does not expose all packages.

### Exercise 3 — Qualified export

Module lib declares:

~~~java
module com.acme.library {
    exports com.acme.spi to com.acme.plugin;
}
~~~

Assuming no related opens declarations, when checking from the plugin module, which overload is suitable to ask whether the package is exported to plugin?

**Answer:**

~~~java
lib.isExported("com.acme.spi", plugin);
~~~

The two-parameter overload checks the relationship with a specific target module.

### Exercise 4 — Export or open?

A framework needs to read private fields of classes in the com.acme.model package. Is declaring **exports com.acme.model** alone enough to grant deep reflection?

**Answer:** No. You need to open the package to the framework module using opens or an appropriate valid runtime mechanism. Export serves standard API access.

### Exercise 5 — Why does isExported return true?

Module lib declares:

~~~java
module com.acme.library {
    opens com.acme.model to com.acme.json;
}
~~~

Why can **lib.isExported("com.acme.model", json)** return true even though module-info.java has no exports line for this package?

**Answer:** The Module API specifies that a package opened to a target module is also considered exported to that module at runtime.

### Exercise 6 — Does isOpen check canRead?

If **lib.isOpen("com.acme.model", app)** returns true, does this result prove that app reads lib?

**Answer:** No. isOpen does not check readability. Use **app.canRead(lib)** to check separately. Some operations such as privateLookupIn also require the caller to read the target module.

### Exercise 7 — Unnamed module

An application running on the classpath obtains its own Module. Can the result of **app.canRead(anyNamedModule)** be false?

**Answer:** No. An unnamed module reads all modules, so canRead returns true.

### Exercise 8 — Checking the descriptor

To know whether module-info.java declares a package in exports or opens, is calling **isExported** alone enough?

**Answer:** No. isExported can return true because the package is opened at runtime. Inspect **module.getDescriptor().exports()** and **module.getDescriptor().opens()** to view the declarations in the descriptor.

## 14. Checklist when using the three methods

- Have you accurately identified the module owning the package and the module needing access?
- Did you call **canRead** on the consumer module and pass the provider module?
- Did you call **isExported** / **isOpen** on the provider module and pass the consumer module?
- Is the goal public API access or deep reflection?
- Have you distinguished exports from opens in module-info.java?
- Did you remember that **isExported** treats a package opened to the target module as exported at runtime?
- Do you need to read the descriptor to know the exact static declarations?
- Did you check readability separately when the operation requires it?
- Did you pass the exact full package name and valid Module objects?
- Did you account for unnamed modules and open modules when interpreting results?

**Remember:** **canRead** checks the readability edge from consumer to provider; **isExported** checks the runtime export status of a package; **isOpen** checks deep reflection permission. Identify the relationship direction properly before calling the methods, and do not treat these three results as a single kind of permission.

## References

- Oracle Java SE 21 API — **java.lang.Module**: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Module.html
- Oracle Java SE 21 API — **java.lang.module.ModuleDescriptor**: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/module/ModuleDescriptor.html
- Java Language Specification, Java SE 21 — **Chapter 7: Packages and Modules**: https://docs.oracle.com/javase/specs/jls/se21/html/jls-7.html
- OpenJDK JEP 261 — **Module System**: https://openjdk.org/jeps/261
