# The exports Directive in the Java Module System

In the Java Platform Module System (JPMS), a module can contain multiple packages, but not every package is meant to be used by other modules. The **exports** directive in the module-info.java file exposes a package so that modules allowed to read that module can use the package's public API.

exports is a core part of module design: it defines the public API boundary, helps a module hide internal implementation details, and reduces coupling between components. To use a public type from another module, two conditions are usually required: the consuming module declares **requires** on the providing module, and the providing module **exports** the package containing that type.

## 1. What is exports used for?

A named module can contain:

- **Public packages:** contain the API that other modules are allowed to use.
- **Internal packages:** contain implementation classes, helpers, or internal details that should not be exposed.
- **Module descriptor:** the module-info.java file that declares the module name, dependencies, and access boundaries.

For example, a module named com.acme.library:

~~~java
module com.acme.library {
    exports com.acme.library.api;
}
~~~

This directive exposes the com.acme.library.api package. Another module can use the public types in that package if the consuming module reads com.acme.library.

The com.acme.library.internal package, if it exists but is not exported, can still be used inside the com.acme.library module; other modules cannot import types in that package as a normal API.

### exports controls packages, not individual classes

The exports directive applies to an entire package. It has no syntax to export only a single class within a package.

If a package is exported:

- Public types in the package can be accessed by modules that read the module.
- Java's access modifier rules still apply to classes, methods, and fields.
- Package-private types still do not become public.
- Internal classes can be kept in a separate, non-exported package.

Therefore, when designing an API, you should place types meant to be public in a dedicated API package and keep implementations in internal packages.

## 2. Syntax of exports

There are two main forms:

~~~java
exports package.name;
exports package.name to module.one, module.two;
~~~

### Unqualified export

The form without the to keyword:

~~~java
module com.acme.library {
    exports com.acme.library.api;
}
~~~

This is an **unqualified export**. The package is exposed to every module that reads com.acme.library. This is the appropriate choice for a public API that a module wants to support for many consumers.

### Qualified export

The form with the to keyword:

~~~java
module com.acme.library {
    exports com.acme.library.api;
    exports com.acme.library.spi to com.acme.plugin, com.acme.testkit;
}
~~~

This is a **qualified export**. The com.acme.library.spi package is exposed only to the modules listed in the to clause.

Qualified exports are useful when a package is intended only for a cooperating group of modules, for example:

- An SPI API intended only for controlled plugins.
- An internal integration package between two modules in the same system.
- A test-support package opened to a test harness module.
- An extension interface intended for a specific implementation.

A qualified export is still a package-level exposure mechanism; it does not make classes in the package private or change Java access modifiers.

### No wildcards and no automatic inclusion of subpackages

exports must specify a concrete package name. There is no syntax such as:

~~~java
exports com.acme.library.*;
~~~

If a module has the packages:

- com.acme.library.api
- com.acme.library.api.model
- com.acme.library.internal

then exports com.acme.library.api only exports the com.acme.library.api package. It does not automatically export com.acme.library.api.model or com.acme.library.internal. To expose a subpackage, you must declare each package separately.

## 3. Conditions for another module to use an exported package

For the com.acme.app module to call an API from com.acme.library, both module readability and package accessibility are required.

Library module descriptor:

~~~java
module com.acme.library {
    exports com.acme.library.api;
}
~~~

Application module descriptor:

~~~java
module com.acme.app {
    requires com.acme.library;
}
~~~

The two directives have different responsibilities:

- **requires com.acme.library** establishes a readability relationship: the app module can read the library module.
- **exports com.acme.library.api** allows modules that read library to access public types in the api package.

Having only requires without the package being exported means the app module still cannot use the API in that package in the normal way. Having only exports without the app module reading the library module means the application cannot automatically import the API either.

### Relationship diagram

~~~text
com.acme.app
    |
    | requires com.acme.library
    v
com.acme.library
    |
    | exports com.acme.library.api
    v
com.acme.library.api
    |
    v
Public API can be used by the app
~~~

The module descriptor describes both dependencies between modules and which packages form the API surface.

## 4. Complete example: exporting an API package

The example below has two modules:

- com.acme.greetings provides the Greeter class.
- com.acme.app uses Greeter.

Source tree structure:

~~~text
exports-demo/
└── src/
    ├── com.acme.greetings/
    │   ├── module-info.java
    │   └── com/
    │       └── acme/
    │           └── greetings/
    │               └── Greeter.java
    └── com.acme.app/
        ├── module-info.java
        └── com/
            └── acme/
                └── app/
                    └── Main.java
~~~

### Module providing the API

File src/com.acme.greetings/module-info.java:

~~~java
module com.acme.greetings {
    exports com.acme.greetings;
}
~~~

File src/com.acme.greetings/com/acme/greetings/Greeter.java:

~~~java
package com.acme.greetings;

public class Greeter {
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

### Module consuming the API

File src/com.acme.app/module-info.java:

~~~java
module com.acme.app {
    requires com.acme.greetings;
}
~~~

File src/com.acme.app/com/acme/app/Main.java:

~~~java
package com.acme.app;

import com.acme.greetings.Greeter;

public class Main {
    public static void main(String[] args) {
        Greeter greeter = new Greeter();
        String name = args.length == 0 ? "Java" : args[0];

        System.out.println(greeter.greet(name));
    }
}
~~~

### Compiling both modules

From the exports-demo directory, run with JDK 17 or later:

~~~bash
javac --release 17 --module-source-path src -d out \
  -m com.acme.greetings,com.acme.app
~~~

The command uses --module-source-path to locate the source tree, -d out to place class files, and -m to select the two modules to compile.

### Running the application

~~~bash
java --module-path out -m com.acme.app/com.acme.app.Main
~~~

Output:

~~~text
Hello, Java!
~~~

Passing an application argument:

~~~bash
java --module-path out -m com.acme.app/com.acme.app.Main "Module System"
~~~

Output:

~~~text
Hello, Module System!
~~~

This example shows that the application only needs to declare requires on the library module; the API package is accessible because the library module exported the com.acme.greetings package.

## 5. Qualified exports: exposing only to selected modules

Suppose a library has a public API for all consumers and an SPI intended only for a plugin module.

Library module descriptor:

~~~java
module com.acme.library {
    exports com.acme.library.api;
    exports com.acme.library.spi to com.acme.plugin;
}
~~~

Plugin module descriptor:

~~~java
module com.acme.plugin {
    requires com.acme.library;
}
~~~

In this design:

- com.acme.plugin can access public types in com.acme.library.api.
- com.acme.plugin can also access public types in com.acme.library.spi.
- Another module that reads com.acme.library but is not in the to list can only access the api package; the spi package remains closed to that module.

A qualified export does not replace requires. The plugin module must still declare requires com.acme.library to read the library module.

### When should you use a qualified export?

Use it when there is a controlled module boundary and a package only needs to be shared with specific modules. Avoid listing too many internal modules in a qualified export if the real goal is to build a public API; such a list increases coupling between modules and can make refactoring harder.

If a target module is renamed, the qualified export must also be updated to match the new module name. This is an intentional dependency and must be managed during the build process.

## 6. How do exports and opens differ?

Both directives relate to package accessibility, but they solve two different needs.

| Aspect | exports | opens |
|---|---|---|
| Purpose | Expose Java API to other modules | Allow deep reflective access into a package |
| Source-code access | Allows importing and using public types under Java rules | Does not by itself allow importing the package as an API |
| Reflection on public API | Allows normal reflective access to the exported API | Also allows deep reflection |
| Reflection on non-public members | Does not by itself grant deep reflection | Allowed within the scope of opens |
| Typical consumers | API consumers | Frameworks, serializers, dependency injection, and reflection tools |

Export example:

~~~java
module com.acme.model {
    exports com.acme.model.api;
}
~~~

Qualified open example:

~~~java
module com.acme.model {
    exports com.acme.model.api;
    opens com.acme.model.internal to com.acme.json;
}
~~~

In the second example:

- Modules that read com.acme.model can use the public API in com.acme.model.api.
- The com.acme.json module is allowed deep reflection into com.acme.model.internal.
- Other modules do not receive deep reflection access to the internal package through this scoped opens directive.

You can use opens package; to open a package to all modules, or opens package to module.name; for restricted opening. The open module option at the top of the module descriptor opens all packages of the module for deep reflection, but does not turn all packages into exported source-level APIs.

You should not use opens in place of exports when the goal is to let other modules import and call normal Java APIs.

## 7. exports does not bypass Java access modifiers

Exporting a package does not make every class and member in the package public.

Example:

~~~java
package com.acme.library.api;

public class PublicService {
    public void execute() {
        // Public API
    }

    void internalStep() {
        // package-private
    }

    private void hiddenStep() {
        // private
    }
}
~~~

If a module exports the com.acme.library.api package:

- Other modules can call new PublicService() and execute() because the class and method are public.
- Other modules cannot call internalStep() because the method is package-private.
- Other modules cannot call hiddenStep() via normal Java access because the method is private.

Java language access rules still apply after JPMS allows the package to be read. JPMS adds a module boundary outside traditional access modifiers.

## 8. exports and requires transitive

requires and exports are two independent parts of a module descriptor. A situation to watch out for is when the public API of module A uses a type defined in module B.

For example, the com.acme.api module returns a Type from com.acme.types in its API signature. If consumers of com.acme.api need to read Type to compile code that uses the API, the api module may need to declare:

~~~java
module com.acme.api {
    requires transitive com.acme.types;
    exports com.acme.api;
}
~~~

requires transitive causes modules that read com.acme.api to also read com.acme.types in the module graph. This is useful when a dependency is part of the public API.

Keep the distinctions clear:

- **exports** exposes a package belonging to the module declaring the directive.
- **requires** declares that the current module reads another module.
- **requires transitive** propagates readability to modules that depend on the current module.

requires transitive does not automatically export packages of the depended-upon module. Those packages must still be exported by the module that owns them according to its own rules.

## 9. How to inspect exported packages

You can use javap to inspect a compiled module descriptor:

~~~bash
javap -p -v out/com.acme.greetings/module-info.class
~~~

In the output, look for the module descriptor section and the exports directives. The module-info.class file sits at the root of the exploded module.

If the module has been packaged into a modular JAR, you can use:

~~~bash
jar --describe-module --file com.acme.greetings.jar
~~~

This command displays the module name, exported packages, and module relationships that the tool reads from the archive.

You can use javap to inspect the public signatures of an API class:

~~~bash
javap -classpath out/com.acme.greetings com.acme.greetings.Greeter
~~~

The last command only inspects class signatures on the classpath; it does not replace checking the module descriptor or module resolution of the entire application.

## 10. Common errors related to exports

### Package is not visible or package is not exported

The consuming module may already require the providing module, but the package containing the needed class has not been exported.

How to fix:

- Check the module descriptor of the module that owns the package.
- Add exports package.name; if the package is a public API.
- Use a qualified export if only specific modules are allowed to use the package.
- Recompile the modules and run again with the proper module path.

### Module not found

The consuming module cannot find the providing module. Check requires, the module name, the module path, and the output artifacts. exports does not automatically add a module to the module graph.

### Class is not public or member is not accessible

The package may already be exported, but the type or member is still not public. Check the access modifiers of the class, constructor, method, and field. exports does not change modifiers in source code.

### Used opens, but import still fails

opens serves deep reflection and does not replace exports for source-code access. If you need to import and call a public API, export the corresponding package.

### Subpackage is still inaccessible

exports applies only to the exact package declared. You must export a subpackage separately if it is also part of the public API.

### Qualified export does not work for the intended module

Check whether the module name in the to clause matches the module name in module-info.java. A package name or JAR name is not necessarily the module name. The target module must also read the providing module using requires.

### API exposed too broadly

An internal package exported unnecessarily can become an API surface that other modules depend on. Move implementation classes into a non-exported package or separate API and implementation packages to control the public contract.

## 11. API design principles with exports

When designing a module, treat each exports directive as a decision about the API contract:

1. **Export only packages that need to be public.** Keep helpers, implementations, and internal details in non-exported packages.
2. **Prefer clear API packages.** Names like com.acme.product.api or com.acme.product.spi help consumers recognize the supported surface.
3. **Use qualified exports intentionally.** Restrict access to target modules only when there is a specific collaboration boundary.
4. **Avoid exporting subpackages out of habit.** Each exported package expands the scope of consumer dependencies.
5. **Do not confuse exports with opens.** Source-level APIs and deep reflection are two different requirements.
6. **Manage public dependencies.** If an API signature uses types from another module, evaluate requires transitive.
7. **Maintain API compatibility.** Once a package is exported, other modules can depend on public types in it; changing or removing types must be managed as an API change.
8. **Verify module descriptors in CI.** Compile modules and test the application to catch missing package exports or missing requires dependencies.

## 12. Checklist when using exports

- Place the exports directive in the module-info.java of the module that owns the package.
- Determine whether the package is truly a public API.
- Use exports package.name; to expose it to every module that reads the current module.
- Use exports package.name to module.name; to restrict which modules can access it.
- Remember that exports does not automatically create a requires relationship.
- Remember that exporting a parent package does not automatically export subpackages.
- Keep Java access modifiers appropriate; exports does not turn package-private classes into public ones.
- Use opens for deep reflection needs, not as a substitute for exports.
- Consider requires transitive when a dependency appears in public API signatures.
- Inspect the module descriptor with javap or jar --describe-module.
- Compile and run examples on the module path to confirm the module graph and package visibility.
- Avoid exporting internal packages unless you want to turn them into a supported API surface.

## 13. Key terms to remember

| Term | Meaning |
|---|---|
| exports | Exposes a module's package to other modules |
| Unqualified export | Exports a package to every module that reads the current module |
| Qualified export | Exports a package only to the modules listed after to |
| Package accessibility | The ability of another module to access types in a package |
| Module readability | The read relationship between modules, typically declared with requires |
| requires | Declares a module dependency |
| requires transitive | Propagates readability to modules that depend on the current module |
| opens | Allows deep reflection into a package |
| open module | Opens all packages for deep reflection |
| API package | A package containing public types supported for consumers |
| SPI | Service Provider Interface, an interface intended for implementations or plugins |

Key takeaway: **requires determines which modules are read; exports determines which packages are exposed; opens determines which packages are open for deep reflection**. Designing these three parts clearly helps a module preserve encapsulation, expose the right API, and limit unnecessary dependencies.