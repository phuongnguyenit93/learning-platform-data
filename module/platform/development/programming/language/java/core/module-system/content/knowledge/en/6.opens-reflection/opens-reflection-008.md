# Limiting package opening instead of opening the entire module

The Java Platform Module System (JPMS) encapsulates packages along module boundaries. When a framework needs to use deep reflection to read or modify private members, the module owning the package must grant appropriate access. Both the **opens** directive and the **open module** declaration support reflection, but their opening scopes are very different.

In most applications, you should open only the exact packages that the framework needs to use. Opening the entire module is only justified when the design intent genuinely requires every package to be deeply accessible via reflection.

## 1. Why does reflection require opening packages?

Reflection allows a program to inspect classes, methods, fields, and constructors at runtime. Some frameworks use reflection to:

- Map entity fields to database columns.
- Read and write properties when serializing or deserializing JSON.
- Instantiate objects through constructors.
- Inject dependencies into fields or constructors.
- Inspect annotations and class metadata.

If a framework only calls already-exported public APIs, it typically does not need permission to open packages for deep reflection. However, when a framework needs to access private members or unexported packages, JPMS encapsulation rules can block the operation.

Example of an entity:

~~~java
package com.example.orders.model;

public class Order {
    private String orderCode;

    private Order() {
    }

    public String getOrderCode() {
        return orderCode;
    }
}
~~~

An ORM framework may need to invoke the private constructor or access the **orderCode** field to instantiate and populate the entity. Having a public class or a getter does not guarantee that the framework is permitted to use deep reflection on all members of the package.

When access is blocked, operations such as **setAccessible(true)** can produce **InaccessibleObjectException**. With **trySetAccessible()**, the result can be **false** if access cannot be enabled. In that case, you need to check which module owns the package and whether that module has opened the package to the framework.

## 2. Opening the exact package with opens

The **opens** directive placed in **module-info.java** allows deep reflection into a package at runtime.

Example of an order management module opening only the model package:

~~~java
module com.example.orders {
    exports com.example.orders.api;

    opens com.example.orders.model;
}
~~~

In this example:

- The package **com.example.orders.api** is exported for other modules to use the public API.
- The package **com.example.orders.model** is opened for deep reflection at runtime.
- The remaining packages stay encapsulated according to the module descriptor.

The **opens** directive does not make a package a public Java API for other modules to import and use directly. It addresses reflective access permissions, especially reflection into non-public members. To let other modules access normal APIs, appropriate **exports** and a module read relationship such as **requires** are still needed.

An important point: **opens** applies to the entire package, not selectively to a single class or field. Therefore, you should group classes that frameworks need to process into an appropriate package, avoiding placing too many unrelated internal implementation classes in the same opened package.

## 3. Qualified opens: opening only to frameworks that need it

If you know the exact framework module that needs reflection, use **qualified opens** to restrict the target modules:

~~~java
module com.example.orders {
    exports com.example.orders.api;

    opens com.example.orders.model to com.example.orm;
}
~~~

Only the module **com.example.orm** receives deep reflection permission into the model package under this directive. Other modules do not receive permission to open that package merely because they read the orders module.

You can open a package to multiple target modules:

~~~java
module com.example.orders {
    opens com.example.orders.model to
        com.example.orm,
        com.example.json;
}
~~~

This approach is suitable when an application uses multiple independent frameworks, such as an ORM and a JSON mapper. Each framework is granted permission only on the packages it actually needs.

The target module name must be the JPMS module name published by the framework. The artifact name on Maven or the dependency name in Gradle does not necessarily match the module name. You can inspect a JAR's module name with the **jar --describe-module** command before declaring qualified opens.

## 4. How broadly does open module expand the scope?

JPMS also supports the **open module** declaration:

~~~java
open module com.example.orders {
    exports com.example.orders.api;
}
~~~

This declaration opens all packages of the module for deep reflection at runtime. Other modules can perform deep reflection into packages in the orders module under JPMS opening mechanisms.

However, **open module is not synonymous with exporting all packages**:

- Unexported packages still do not become normal public Java APIs.
- Other modules cannot arbitrarily import classes from unexported packages just because the module is declared open.
- What is expanded here is deep reflective access permission at runtime.

An open module does not need to list individual **opens** directives. In fact, do not place individual **opens** directives inside an open module declaration; the open modifier already opens all packages. If you want to restrict packages or target modules, use a regular module with specific **opens** directives.

Comparison:

| Declaration | Deep reflection scope | Does it export APIs? |
|---|---|---|
| No opens | Does not open packages via directive | Only packages with exports |
| opens package | Opens one package to all modules | Does not automatically export |
| opens package to module | Opens one package to selected modules | Does not automatically export |
| open module | Opens all packages for deep reflection | Does not automatically export |

## 5. Why shouldn't you open the entire module by default?

Opening the entire module can help a framework work quickly in early stages, but it weakens the encapsulation boundaries that modules are designed to protect.

**Increases internal access surface**

When every package is opened, many modules can perform deep reflection into private fields, constructors, and methods of the implementation. Details meant to be controlled by the owning module can become implicit points of dependency.

**Increases coupling with frameworks**

Frameworks may start relying on field structures, constructors, or internal property names. When the implementation changes, external code can be affected even though the public API stays unchanged.

**Makes implementation changes harder**

If many frameworks can deeply access every package, renaming fields, moving packages, or changing how objects are instantiated can break integrations without the compiler catching it the way it does with normal public APIs.

**Makes root-cause analysis harder when errors occur**

When an entire module is opened, the framework's reflection permissions are broader than its actual needs. Inspecting the module descriptor will make it harder to tell which packages actually need to be opened and which frameworks depend on which details.

**Reduces the effectiveness of module boundaries**

One goal of JPMS is to expose APIs intentionally and keep implementations inside the module. Opening all packages reduces the benefit of that separation, even though it does not turn all packages into compile-time APIs.

Therefore, start from the package the framework needs to process, and open only the necessary scope.

## 6. Example module configuration for an application using ORM and JSON

Suppose the orders module has the following packages:

~~~text
com.example.orders
├── api
├── model
├── repository
├── internal
└── config
~~~

The application has an ORM module and a JSON mapper module. If both frameworks only need deep access to entities in the model package, the descriptor can be written as:

~~~java
module com.example.orders {
    requires com.example.orm;
    requires com.example.json;

    exports com.example.orders.api;

    opens com.example.orders.model to
        com.example.orm,
        com.example.json;
}
~~~

Result:

- Consuming modules can use the public API in the api package.
- The ORM and JSON mapper can perform deep reflection into the model package.
- The repository, internal, and config packages are not opened under the directive above.
- If a framework later needs another package, the owning module can evaluate and add that exact package.

If a framework only needs the public API, it may not need any package opened to it. Do not add opens merely because a library uses reflection somewhere; identify the actual package and reflection operation.

## 7. Using --add-opens when runtime configuration is needed

In some systems, it is not possible or not yet feasible to modify **module-info.java** of the module owning the package. Java provides the runtime option **--add-opens** to add package-opening permissions.

Syntax:

~~~bash
java --add-opens source.module/package.name=target.module ...
~~~

Example of opening the model package of the orders module to the ORM module:

~~~bash
java --add-opens com.example.orders/com.example.orders.model=com.example.orm \
     --module com.example.app/com.example.app.Main
~~~

If the framework is loaded from the classpath and belongs to the unnamed module, **ALL-UNNAMED** can be used as the target module:

~~~bash
java --add-opens com.example.orders/com.example.orders.model=ALL-UNNAMED \
     --module com.example.app/com.example.app.Main
~~~

This option applies at runtime and can be useful when integrating legacy libraries or handling a third-party module you do not own. However, it should be scoped by package and target module, and explicitly documented in run configurations for maintainability.

When the module owning the package belongs to your application, declaring **opens** or **opens ... to ...** in the module descriptor is usually a clearer way to express the requirement. Do not keep broad **--add-opens** options in launch scripts if the application no longer needs them.

## 8. Distinguishing exports, opens, and open module

Three commonly confused concepts:

**exports**

Allows other modules to access public types in the package under Java rules. This is the normal way to expose compile-time/runtime APIs.

~~~java
module com.example.orders {
    exports com.example.orders.api;
}
~~~

**opens**

Allows deep reflection into a package at runtime. Can be opened to all modules or only target modules.

~~~java
module com.example.orders {
    opens com.example.orders.model to com.example.orm;
}
~~~

**open module**

Opens every package in the module for deep reflection. It does not automatically export packages for normal access.

~~~java
open module com.example.orders {
    exports com.example.orders.api;
}
~~~

If the error is not being able to import a public class from another module, check **exports** and **requires**. If the error is that a framework cannot access private fields or constructors via reflection, check **opens** and the target module. Using the right directive keeps module boundaries clear.

## 9. Process for determining which package needs to be opened

When a framework reports a reflection error, you can handle it in steps:

1. Read the exception to identify the module owning the class, the blocked package, and the module performing reflection.
2. Determine which package, which class, and which operation the framework needs to deeply access.
3. Inspect the module descriptor of the module owning the package.
4. If the package is already opened, verify whether the target module in qualified opens matches the framework's actual module name.
5. If not yet opened, add **opens package to framework.module** for the required package.
6. Rerun the application to confirm the reflection operation works.
7. If **--add-opens** must be used temporarily, record the exact package and target module, then consider moving the configuration into the module descriptor when possible.

You should not fix it by changing the entire module to an open module as soon as you hit one reflection error. One error in the model package does not prove that the api, internal, repository, and config packages all need to be opened.

## 10. Common errors

**Used opens, but another module still cannot import the class**

Opens only supports deep reflection at runtime. To import and call public APIs, exports and an appropriate module read relationship are needed.

**Used exports, but the framework still cannot access private fields**

Exports does not replace opens. Open the package needing reflection to the framework module.

**Qualified opens has no effect**

The target module name may be wrong, or the framework is loaded in the unnamed module. Check the actual module name and consider **ALL-UNNAMED** only when the framework truly belongs to the classpath.

**Opened one package, and the error moved to another package**

The framework may be processing multiple entity or metadata types located in another package. Open the new package only after confirming it genuinely needs reflection; do not immediately switch to an entirely open module.

**Switched to open module, yet the API is still inaccessible**

Open module opens packages for reflection, not exporting all packages. If other modules need to use a public API, exports must still be declared for that package.

**Cannot combine open module with separate opens directives**

When a descriptor uses the **open** modifier, every package is already opened for reflection. If selective opening scope is needed, remove the open modifier and declare specific opens directives.

## 11. Key takeaways

- **opens package** opens a package for deep reflection at runtime.
- **opens package to module** grants deep reflection permission only to the specified target modules.
- **open module** opens all packages of a module for deep reflection, but does not export them as compile-time APIs.
- **exports** and **opens** address two different types of access.
- You should open the specific model or integration package that the framework needs, instead of opening the entire module.
- **--add-opens** is a useful runtime option for transitional configurations; scope it to the exact package and target module.
- An opened package remains owned by its module; the module descriptor clearly expresses the integration scope and helps control implementation changes.

When designing modules, identify where frameworks need reflection and then declare qualified opens for the exact packages. This keeps the public API and internal implementation separated while reducing hidden dependencies on the module's internal structure.