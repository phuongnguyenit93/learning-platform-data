# Unnamed module reads all exported named modules

## 1. The unnamed module in JPMS

When Java runs an application via the classpath, the application's classes do not belong to a named module with a module descriptor. They belong to the **unnamed module** associated with the class loader that defined them.

Each class loader has its own unnamed module. In a typical application, the system class loader (application class loader) defines the classes on the classpath and has a corresponding unnamed module.

An unnamed module has several important characteristics:

- It has no module name and no separate module descriptor.
- It does not declare requires, exports, or opens in module-info.java.
- It reads the named modules in the corresponding module configuration.
- Packages of the unnamed module are exported and open so that other modules can access them according to the applicable rules.
- It cannot be referenced by a named module using a regular requires directive because the unnamed module has no name.

The characteristic of "reading all named modules" allows legacy applications on the classpath to use APIs exposed by resolved modules. As a result, applications can continue running in the traditional manner while using some libraries that have migrated to JPMS.

## 2. Reading a module and accessing a package are two separate conditions

In JPMS, the fact that one module can read another module does not mean every package of that module is accessible.

For a class in an unnamed module to use a public type of a named module, the following main conditions must be met:

1. **The named module must be resolved** in the running module configuration.
2. **The unnamed module must read that named module** according to the configuration's readability relationships.
3. **The package containing the type must be exported to the unnamed module**.
4. **The type and members being used must have an appropriate access level** under Java rules, typically public.

This can be visualized as:

~~~text
Application on the classpath
        |
        v
Unnamed module
        |
        | reads
        v
Resolved named module
        |
        | exports package.api
        v
Public type in package.api
        |
        v
Application can import and use it
~~~

With an unqualified exports clause, the package is exposed to all modules that read the providing module, including the unnamed module. If the package is not exported, the fact that the unnamed module can read the named module is still not enough to access types in that package.

## 3. A named module exports a package to the unnamed module

Suppose a library has been modularized:

~~~text
com.acme.library/
├── module-info.java
└── com/acme/library/api/
    └── Greeting.java
~~~

Module descriptor:

~~~java
module com.acme.library {
    exports com.acme.library.api;
}
~~~

Public type:

~~~java
package com.acme.library.api;

public class Greeting {
    public static String message() {
        return "Hello from a named module";
    }
}
~~~

The line exports com.acme.library.api exposes the API package. An application on the classpath can import Greeting if the module com.acme.library has been resolved in that run.

Classpath application:

~~~text
app/
└── com/acme/app/Main.java
~~~

Application code:

~~~java
package com.acme.app;

import com.acme.library.api.Greeting;

public class Main {
    public static void main(String[] args) {
        System.out.println(Greeting.message());
    }
}
~~~

The application does not need module-info.java. When run from the classpath, Main belongs to the unnamed module of the application class loader.

## 4. Combining classpath and module path at launch

Classpath and module path can appear together in a single Java command. The classpath holds the traditional application; the module path holds modular libraries.

For example, after compiling the library into a modular JAR:

~~~text
project/
├── app/
│   └── com/acme/app/Main.class
└── mods/
    └── com.acme.library.jar
~~~

Run the application on the classpath and include the library module in the configuration using --add-modules:

~~~bash
java --module-path mods \
     --add-modules com.acme.library \
     -cp app \
     com.acme.app.Main
~~~

Here:

- --module-path mods tells Java where to find named modules.
- --add-modules com.acme.library requests adding the library module to the root module set so it is resolved.
- -cp app places the application classes on the classpath.
- com.acme.app.Main is the main class run from the unnamed module.

If the library module has been resolved and exports the API package unconditionally, the classpath application can use public types in that package.

You should not assume every JAR on the module path is automatically resolved. A module can only be used if it participates in the process's module configuration. When you need to explicitly specify a library module, --add-modules is the explicit way.

You can use ALL-MODULE-PATH with --add-modules to add all observable modules on the module path to the root set:

~~~bash
java --module-path mods \
     --add-modules ALL-MODULE-PATH \
     -cp app \
     com.acme.app.Main
~~~

This is a broad option. For applications with known dependencies, you should specify the needed modules so the runtime configuration is easy to understand and control.

## 5. Why can an unnamed module read named modules?

Named modules describe dependencies using requires. An unnamed module has no module descriptor to declare individual dependencies, so JPMS applies a special readability rule to it.

Thanks to its ability to read named modules in the corresponding configuration, a classpath application can continue using modular APIs without immediately converting the entire application into a named module.

For example, if a library module declares:

~~~java
module com.acme.format {
    exports com.acme.format.api;
}
~~~

then classes on the classpath can import public types belonging to com.acme.format.api when com.acme.format has been resolved and the package is exported unconditionally.

This mechanism supports incremental migration:

~~~text
Legacy application on the classpath
          |
          | unnamed module
          |
          +------> Named module A (exported API)
          |
          +------> Named module B (exported API)
          |
          +------> Named module C (exported API)
~~~

The application does not need to be converted to a named module just to use modular libraries. However, keeping the application on the classpath also means the application does not yet have a module descriptor to declare dependencies, export its own APIs, or establish its own package boundaries.

## 6. The scope of an unnamed module is tied to a class loader

The unnamed module is not a single global module for every class in the JVM. Each class loader has its own unnamed module.

This matters in applications with plugins or custom class loaders:

- Classes defined by the application class loader belong to the unnamed module of the application class loader.
- Classes defined by a custom class loader belong to the unnamed module associated with that loader.
- Two classes with the same fully qualified name but defined by two different class loaders can still be two distinct types in the JVM.
- Readability and class lookup depend on the modules, layers, and class loaders involved.

Therefore, when an application uses multiple class loaders, you should not just look at a single shared classpath and conclude that every class has the same module readability. Identify which loader defines the consumer class and which loader/layer provides the named module.

## 7. An unnamed module cannot be directly required by a named module

The readability direction between an unnamed module and a named module is asymmetric.

An unnamed module can read named modules, but a named module does not automatically read unnamed modules. Because an unnamed module has no name, you cannot write:

~~~java
module com.acme.plugin {
    requires unnamed;
}
~~~

The syntax above is invalid because there is no module named unnamed to require.

If a named module needs to read classes located on the classpath in a compatibility scenario, a readability relationship can be added using a runtime option:

~~~bash
java --add-reads com.acme.plugin=ALL-UNNAMED \
     --module-path mods \
     --add-modules com.acme.plugin \
     -cp app \
     --module com.acme.plugin/com.acme.plugin.Main
~~~

The option --add-reads source=target adds a readability relationship at runtime. ALL-UNNAMED represents the relevant unnamed modules in the launcher context.

This is an intentional compatibility measure. A stable modular design should place shared contracts in a named API module so named modules can declare requires explicitly.

## 8. An unnamed module only accesses appropriately exported packages

A named module can export a package unconditionally:

~~~java
module com.acme.library {
    exports com.acme.library.api;
}
~~~

In that case, the unnamed module can access public types in package com.acme.library.api if the module has been resolved.

However, if the module only uses a qualified export to a named module:

~~~java
module com.acme.library {
    exports com.acme.library.api to com.acme.application;
}
~~~

then the package is only exported to the module named com.acme.application. The unnamed module is not the named target module com.acme.application, so it does not receive access from this qualified export.

If a classpath application needs access to that package in a compatibility scenario, the launcher can add an export to ALL-UNNAMED:

~~~bash
java --add-exports com.acme.library/com.acme.library.api=ALL-UNNAMED \
     --module-path mods \
     --add-modules com.acme.library \
     -cp app \
     com.acme.app.Main
~~~

General syntax:

~~~text
--add-exports source.module/package=target.module
~~~

ALL-UNNAMED is a special target name for launcher options such as --add-exports. It is not a valid module name to write into requires or qualified exports in module-info.java.

You should not use --add-exports=...=ALL-UNNAMED to open up all internal packages. Only add the packages that are truly necessary and consider moving the needed API to a publicly exported package.

## 9. Public still follows Java access rules

Even when an unnamed module reads a named module and the package is exported, Java access modifiers still apply.

For example:

~~~java
package com.acme.library.api;

public class Greeting {
    public String hello() {
        return "Hello";
    }

    protected void extensionHook() {
    }

    void reset() {
    }

    private void internalOperation() {
    }
}
~~~

From code in another package on the classpath:

- You can call hello on a valid instance.
- extensionHook is still restricted by protected rules, such as needing to be in an appropriate subclass context.
- reset is package-private so it cannot be called from another package.
- internalOperation is private so it can only be accessed according to Java private rules.

Similarly, a non-public type does not become public just because its package is exported:

~~~java
package com.acme.library.api;

class InternalMapper {
}
~~~

An application outside the package cannot import InternalMapper. exports opens a package at the module level; it does not bypass the language's access rules.

## 10. Distinguishing exports from opens

An unnamed module can access public APIs in an exported package. That does not mean it has deep reflection access into non-public members of the source module.

- **exports** allows normal Java access to public types and permitted members.
- **opens** allows deep reflection into non-public members of a package.
- **open module** opens all packages of a module for deep reflection.

Library module example:

~~~java
module com.acme.library {
    exports com.acme.library.api;
    opens com.acme.library.model;
}
~~~

A classpath application can use public APIs in com.acme.library.api. However, if a framework needs to access private fields in com.acme.library.model, that package needs to be opened appropriately.

You can use --add-opens to open a package to unnamed modules at runtime:

~~~bash
java --add-opens com.acme.library/com.acme.library.model=ALL-UNNAMED \
     --module-path mods \
     --add-modules com.acme.library \
     -cp app \
     com.acme.app.Main
~~~

Do not use exports as a substitute for opens when the actual error is an InaccessibleObjectException caused by deep reflection.

## 11. Observing modules and checking readability

You can use the Module API to inspect a class's module:

~~~java
Class<?> type = com.acme.app.Main.class;
Module module = type.getModule();

System.out.println("Module name: " + module.getName());
System.out.println("Is named: " + module.isNamed());
System.out.println("Class loader: " + type.getClassLoader());
~~~

For a class belonging to an unnamed module, getName() returns null and isNamed() returns false. The module descriptor of an unnamed module also has no value like a named module.

You can check the readability relationship to another module:

~~~java
Module consumer = Main.class.getModule();
Module library = com.acme.library.api.Greeting.class.getModule();

System.out.println(consumer.canRead(library));
~~~

If the result is true, consumer can read module library. That does not yet confirm that a specific package has been exported; you need to check the source module's descriptor or the corresponding API.

To view the module descriptor of a JAR:

~~~bash
jar --describe-module --file mods/com.acme.library.jar
~~~

To see which modules are resolved at launch:

~~~bash
java --show-module-resolution \
     --module-path mods \
     --add-modules com.acme.library \
     -cp app \
     com.acme.app.Main
~~~

These two commands help distinguish two separate issues: whether the module has been resolved, and whether the API package is exported.

## 12. Common errors when a classpath application uses named modules

**Module not resolved**

The JAR is on the module path, but the module is not in the runtime configuration. Add the module as a root using --add-modules or adjust the module configuration accordingly.

**Package not exported**

The unnamed module reads the source module, but the package containing the type is not exported. Update the library's module descriptor if the package belongs to the public API; in temporary compatibility cases, consider --add-exports with a narrow scope.

**Qualified export is only for another named module**

The package is exported to a specific named module, so the unnamed module does not receive access. If the classpath application genuinely needs access, use an unqualified public API or intentionally configure --add-exports ...=ALL-UNNAMED.

**Type or member is not public**

The package is exported, but the class or member being used does not have an appropriate access level. Fix the API design if that type truly needs to be public; do not arbitrarily widen access for implementation details.

**Named module needs to read the classpath**

The reverse direction is not automatic. A named module cannot requires an unnamed module. If compatibility is needed, use --add-reads module=ALL-UNNAMED or move the shared contract into a named module.

**Framework needs deep reflection**

The package is exported, but not opened. Add opens or --add-opens for the specific package needed by the framework; do not open the entire module if unnecessary.

## 13. Takeaways

- A classpath application is placed in the unnamed module associated with the class loader that defined the classes.
- The unnamed module has readability to named modules in the corresponding configuration, but the module must be resolved first.
- Reading a module and accessing a package are two separate conditions: the package must still be appropriately exported.
- Unqualified exports allow any module reading the source module to access the package; qualified exports only grant access to the stated target named modules.
- A named module does not automatically read unnamed modules and cannot requires an unnamed module.
- --add-modules can add a named module to the root set; --add-exports and --add-reads add limited access when compatibility is needed.
- public, protected, package-private, and private still follow Java rules.
- exports is for normal API access; opens is for deep reflection.

When combining a classpath application with modular libraries, determine which unnamed module the consumer class belongs to, whether the library module has been resolved, and whether the API package is exported to the consumer. These three pieces of information help separate module resolution errors from package or member access errors.