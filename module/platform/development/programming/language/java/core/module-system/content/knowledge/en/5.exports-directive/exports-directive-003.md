# Qualified Exports to a Specific Module

In the Java Platform Module System (JPMS), the **exports** directive exposes a module's package so other modules can use the public types inside that package. When using qualified exports, a module exposes a package only to explicitly named modules.

This syntax is suitable when a package is an API that needs to be shared among certain known internal modules, adapters, or plugins, but should not become a general API for every module that reads the current module. Qualified exports help design narrower, more intentional module boundaries.

## 1. Syntax and Meaning

Basic syntax:

~~~java
module com.example.catalog {
    exports com.example.catalog.api
        to com.example.catalog.ui,
           com.example.catalog.reporting;
}
~~~

In this example, module **com.example.catalog** exports package **com.example.catalog.api** to two modules:

- **com.example.catalog.ui**
- **com.example.catalog.reporting**

Another module, even if it declares **requires com.example.catalog**, still cannot access this package if its module name is not in the list following the **to** keyword.

Multiple target modules can be declared, separated by commas. The names after **to** are module names, not package names, class names, or JAR file names. The module name must match the name declared in the consuming module's descriptor.

Two conditions must be met for source code in a consuming module to use a type in a qualified-exported package:

1. The consuming module must read the module that owns the package, typically via the **requires** directive.
2. The consuming module must be in the target module list of the qualified exports.

Qualified exports do not create a dependency by themselves, nor do they replace **requires**. They determine which modules can access the package after a module readability relationship already exists.

## 2. Example with an API Module and Two Consuming Modules

Suppose an application has three modules:

~~~text
src/
├── com.example.catalog/
│   ├── module-info.java
│   └── com/example/catalog/api/Product.java
├── com.example.catalog.ui/
│   ├── module-info.java
│   └── com/example/catalog/ui/Main.java
└── com.example.catalog.reporting/
    ├── module-info.java
    └── com/example/catalog/reporting/Report.java
~~~

The catalog module defines the API:

~~~java
// src/com.example.catalog/module-info.java
module com.example.catalog {
    exports com.example.catalog.api
        to com.example.catalog.ui,
           com.example.catalog.reporting;
}
~~~

A public class resides in the exported package:

~~~java
// src/com.example.catalog/com/example/catalog/api/Product.java
package com.example.catalog.api;

public final class Product {
    public String name() {
        return "Mechanical Keyboard";
    }
}
~~~

The UI module declares its dependency:

~~~java
// src/com.example.catalog.ui/module-info.java
module com.example.catalog.ui {
    requires com.example.catalog;
}
~~~

The UI module can use the API:

~~~java
// src/com.example.catalog.ui/com/example/catalog/ui/Main.java
package com.example.catalog.ui;

import com.example.catalog.api.Product;

public class Main {
    public static void main(String[] args) {
        Product product = new Product();
        System.out.println(product.name());
    }
}
~~~

The reporting module is also granted access to the package:

~~~java
// src/com.example.catalog.reporting/module-info.java
module com.example.catalog.reporting {
    requires com.example.catalog;
}
~~~

Because **com.example.catalog.reporting** appears in the qualified exports list, source code in this module can import and call public types in package **com.example.catalog.api** under normal Java access rules.

## 3. Modules Not in the List Will Be Restricted

Add an audit module:

~~~text
src/com.example.catalog.audit/
├── module-info.java
└── com/example/catalog/audit/Audit.java
~~~

Descriptor of the audit module:

~~~java
module com.example.catalog.audit {
    requires com.example.catalog;
}
~~~

If the audit source code tries to use Product:

~~~java
package com.example.catalog.audit;

import com.example.catalog.api.Product;

public class Audit {
    public void inspect() {
        Product product = new Product();
        System.out.println(product.name());
    }
}
~~~

The compiler reports that package **com.example.catalog.api** is not exported to module **com.example.catalog.audit**. Adding **requires com.example.catalog** only establishes module readability; it does not grant access to a package that is conditionally exported to other modules.

If audit genuinely needs this API, you can add that module to the list:

~~~java
module com.example.catalog {
    exports com.example.catalog.api
        to com.example.catalog.ui,
           com.example.catalog.reporting,
           com.example.catalog.audit;
}
~~~

After changing the catalog module's descriptor, you need to recompile that module and the related consuming modules to verify the module graph and access permissions.

## 4. Compiling and Running the Example

From the project root directory, you can compile the catalog module and the UI module as follows:

~~~bash
javac --module-source-path src \
      -d out \
      -m com.example.catalog,com.example.catalog.ui
~~~

After compiling, run the UI module:

~~~bash
java --module-path out \
     -m com.example.catalog.ui/com.example.catalog.ui.Main
~~~

Output:

~~~text
Mechanical Keyboard
~~~

To test the access restriction, add the audit module to the compile command:

~~~bash
javac --module-source-path src \
      -d out \
      -m com.example.catalog,com.example.catalog.ui,com.example.catalog.audit
~~~

If the audit source code imports **com.example.catalog.api.Product** while audit is not yet in the qualified exports list, the compiler will deny access to the package. This is an important check: access permissions are determined from the descriptors and module graph, not based on whether the JAR file is on the module path.

When changing the descriptor to add audit, recompile from the full source tree. If testing packaged JARs, rebuild the JAR containing the new module descriptor and use that exact JAR on the module path.

## 5. How Do Qualified Exports Differ from Unqualified Exports?

The two forms of exports have different scopes:

~~~java
// Export the package to every module reading this module
exports com.example.catalog.api;
~~~

~~~java
// Export the package only to the named modules
exports com.example.catalog.api
    to com.example.catalog.ui,
       com.example.catalog.reporting;
~~~

| Criterion | Unqualified exports | Qualified exports |
| --- | --- | --- |
| Syntax | exports package; | exports package to moduleA, moduleB; |
| Scope | Modules reading the current module can access the package | Only the listed modules can access the package |
| Consumer extensibility | New consumers can use the package when they have a valid readability relationship | New consumers must be added to the list |
| Suitability | Public, stable API for many modules | Restricted shared internal API |
| Maintenance effort | Less updating required when adding consumers | Descriptor must be updated when adding valid consumers |

Unqualified exports are usually suitable for APIs that a module actively exposes for ecosystem use. Qualified exports are suitable for packages shared among an identified group of modules, such as APIs for adapters, integration modules, or certain components within the same product.

You should not put an entire module's packages into a qualified exports list just because one consumer needs a single class. JPMS exports by package, not by individual class or method. If you need to expose a smaller API, separate that API into its own package with an appropriate boundary.

## 6. Qualified Exports Only Expose Public APIs

Qualified exports do not turn a package into a completely open zone. Java access rules still apply:

- Consumers are allowed to access public types in the exported package.
- Consumers must still obey class, constructor, field, and method modifiers.
- Private or package-private members do not become public APIs.
- Subpackages are independent packages; exporting a parent package does not automatically export subpackages.

For example, the descriptor only exports:

~~~java
exports com.example.catalog.api
    to com.example.catalog.ui;
~~~

It does not automatically export:

~~~text
com.example.catalog.api.internal
com.example.catalog.persistence
com.example.catalog.admin
~~~

If the UI module needs to access another package, the module owning that package must have a corresponding directive. This is why packages should be organized along API boundaries rather than relying on the assumption that exporting one package opens the entire package tree underneath.

## 7. Distinguishing exports from opens

Qualified exports control normal API access. Frameworks using deep reflection may need different permissions.

Example:

~~~java
module com.example.catalog {
    exports com.example.catalog.api
        to com.example.catalog.ui;

    opens com.example.catalog.model
        to com.example.catalog.persistence;
}
~~~

In this descriptor:

- The UI module can access public types in the API package.
- The persistence module is allowed deep reflection into the model package under JPMS rules.
- Exporting the API does not automatically open the model package.
- Opening the model package does not turn the API package into an API that can be imported and called normally.

Qualified opens can be used when only one framework or module needs reflection. This approach is often suitable for ORMs, serializers, or frameworks that need to read/write non-public fields. Open only the packages that are truly necessary.

## 8. Appropriate Use Cases

**APIs for specific adapters**

A domain module can expose an SPI package to known adapter modules. Other modules cannot depend directly on that SPI unless granted access.

**Internal APIs between modules of the same product**

A platform module can provide a package to UI and reporting modules. Other application modules use only the specifically designed public API portion.

**Limiting the integration surface**

A module can maintain a broadly public API package while using qualified exports for an integration support package needed by only a few consuming modules.

**Separating implementation from contract**

An implementation module can export a contract package to a coordinating group of modules. Packages containing internal details and implementations remain closed.

Qualified exports are most useful when the consumer list is manageable and there is a clear architectural reason. If the target module list changes constantly or there are many unpredictable external consumers, a stable public API may be a better choice.

## 9. Inspecting Descriptors and Access Permissions

When a module has been packaged into a JAR, use the jar tool to view the descriptor:

~~~bash
jar --describe-module --file out/com.example.catalog.jar
~~~

The module description shows the exported packages and the target modules of qualified exports. Make sure to inspect the exact JAR file being placed on the module path, because the source descriptor and an older JAR may not match.

You can use **jdeps** to analyze module dependencies:

~~~bash
jdeps --module-path mods --module com.example.catalog.ui
~~~

This command helps inspect which modules a module depends on. It does not replace checking qualified exports: module read dependencies and package access permissions are two separate conditions.

At runtime, the Module API lets you check whether a package is exported to a specific module:

~~~java
Module owner = Product.class.getModule();
Module consumer = Main.class.getModule();

boolean exported =
    owner.isExported("com.example.catalog.api", consumer);

System.out.println("Qualified export available: " + exported);
~~~

The call **isExported(packageName, targetModule)** returns true when the package is exported to the target module under the current runtime configuration. It is useful when debugging modular applications or when confirming the relationship between two modules.

## 10. Common Errors and How to Handle Them

**Package is not visible**

Check whether the consuming module requires the module owning the package. Then check whether the package is exported and whether the consuming module's name is in the qualified exports list.

**Module not found or module name mismatch**

Check the module name in the consumer's module-info.java and the list after **to**. Compare against the actual descriptor using **jar --describe-module**. The JAR filename is not necessarily the module name.

**Added the module to the list, yet the error persists**

The compiler or runtime may be using a different version of the module on the module path. Identify the exact output directory, JAR, and module path the command is using; then rebuild the module descriptor and run with the new artifact.

**Consumer reads the module but cannot import the package**

This is a common point of confusion between **requires** and **exports**. requires creates module readability; exports specifies which packages can be accessed, and qualified exports further restricts which modules receive access.

**Framework reports reflection errors**

Check whether the package needing deep access is opened to the framework module. Add qualified opens when needed, rather than expanding qualified exports to handle private reflection.

**Code on the classpath cannot access a qualified-exported package**

Classes on the classpath belong to the unnamed module. The unnamed module cannot be named as a target module in a qualified exports directive. If the application needs to use that package from the classpath, consider designing an unqualified exports API or converting the consumer into a named module with a stable name.

## 11. Design and Maintenance Principles

- Use qualified exports only when there is a specific list of consuming modules and a clear reason to restrict access.
- Keep target module names accurate, stable, and matching the names in the consumer descriptors.
- Keep API packages small, separating implementation and internal packages.
- Remember that exported packages are the unit of access; there is no mechanism to export individual classes.
- Update descriptors when adding or removing consuming modules, then recompile and retest all related modules.
- Use qualified opens for deep reflection needs instead of confusing them with exports.
- Inspect the actual JAR on the module path when errors appear only after packaging or deployment.
- Do not treat qualified exports as a sandbox mechanism or security boundary for untrusted code.

Qualified exports help a module expose the right packages to the right group of consumers. When combined with clearly designed requires, exports, and opens, an application can maintain necessary APIs between modules while keeping internal packages out of reach of other modules.