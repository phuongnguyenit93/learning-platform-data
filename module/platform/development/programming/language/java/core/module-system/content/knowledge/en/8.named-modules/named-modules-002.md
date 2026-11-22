# Explicit Named Modules from module-info.java

In the Java Platform Module System (JPMS), an explicit named module is a module that has a name and declares an explicit module descriptor in the **module-info.java** file. This descriptor defines the module's identity, the dependencies the module needs to read, which packages are published, and the services the module uses or provides.

When the compiler processes module-info.java, it validates the declaration structure and produces a **module-info.class** file in the compiled output. When packaging the module into a modular JAR, the descriptor file resides at the root of the JAR. Thanks to that descriptor, Java can identify the module by its declared name and apply JPMS module resolution, readability, and encapsulation rules.

This lesson focuses on how to create an explicit named module, the descriptor structure, the compilation and packaging workflow, how Java identifies modules on the module path, as well as common errors when migrating a library or application from the classpath to the module path.

## 1. What is an explicit named module?

An explicit named module has two characteristics:

1. Has a stable module name declared in the module descriptor.
2. Has a descriptor compiled into **module-info.class** and placed at the root of the compiled module or the root of the modular JAR.

Example:

~~~java
module com.example.inventory {
    exports com.example.inventory.api;
}
~~~

The module name is **com.example.inventory**. The package **com.example.inventory.api** is exported so other modules can use public types in that package when an appropriate readability relationship exists.

JPMS also has two other cases often placed alongside explicit named modules:

| Type | How it is identified | Characteristics |
| --- | --- | --- |
| Explicit named module | Has module-info.class with an explicit module descriptor | Name, dependencies, and package access are clearly declared |
| Automatic module | JAR without a module descriptor but placed on the module path | Module name is derived from Automatic-Module-Name or the JAR name; has compatibility behavior during migration |
| Unnamed module | Classes and JARs on the classpath | Has no explicit module name; traditional source code continues running under the classpath model |

An explicit named module is the most complete way to describe a module. The module name does not need to be inferred from the JAR file name, and dependency rules along with access permissions are stored in the descriptor.

## 2. The role of module-info.java

The **module-info.java** file is the module declaration. It resides at the root of the module's source, at the same level as the package tree, not inside a regular Java package.

Minimal structure:

~~~java
module com.example.inventory {
}
~~~

This is a named module named **com.example.inventory**. Even though the body is empty, the compiler still generates a descriptor for the module. Every normal module has an implicit dependency on the platform module **java.base**, so there is no need to write **requires java.base** in the descriptor.

A descriptor can declare the following directives:

| Directive | Role |
| --- | --- |
| requires | Declares a module dependency that the current module needs to read |
| requires transitive | Propagates readability of a dependency to modules that depend on the current module |
| requires static | Declares a dependency required at compile time but optional at runtime |
| exports | Publishes a package to modules that read the current module |
| exports ... to | Publishes a package only to the listed modules |
| opens | Opens a package for deep reflection |
| opens ... to | Opens a package only to specific modules |
| uses | Declares a service for which the module needs to find implementations |
| provides ... with | Declares an implementation provided for a service |

Example of a descriptor combining dependencies and API:

~~~java
module com.example.inventory {
    requires java.logging;

    exports com.example.inventory.api;
}
~~~

This module reads the **java.logging** module and publishes the API package. Other packages in the module remain closed to external modules unless a corresponding export directive is present.

The **requires** and **exports** directives solve two separate concerns: requires establishes module readability; exports establishes package accessibility. The fact that a module can read a dependency does not mean all packages of that dependency are published.

## 3. Organizing the source tree for an explicit named module

A modular source tree usually places each module in a separate directory whose name matches the module name:

~~~text
inventory-project/
└── src/
    └── com.example.inventory/
        ├── module-info.java
        └── com/
            └── example/
                └── inventory/
                    ├── Main.java
                    └── api/
                        └── Product.java
~~~

The module-info.java file sits directly inside the **com.example.inventory/** directory. Java classes sit inside the packages underneath.

Descriptor example:

~~~java
// src/com.example.inventory/module-info.java
module com.example.inventory {
    exports com.example.inventory.api;
}
~~~

API class:

~~~java
// src/com.example.inventory/com/example/inventory/api/Product.java
package com.example.inventory.api;

public final class Product {
    private final String name;

    public Product(String name) {
        this.name = name;
    }

    public String name() {
        return name;
    }
}
~~~

Launcher class:

~~~java
// src/com.example.inventory/com/example/inventory/Main.java
package com.example.inventory;

import com.example.inventory.api.Product;

public class Main {
    public static void main(String[] args) {
        Product product = new Product("Keyboard");
        System.out.println(product.name());
    }
}
~~~

The **Main** class does not need to be in an exported package for the Java launcher to run that module. Exporting is for access from other modules; the main class is selected directly by module name and class name in the run command.

The module directory name in the source tree is part of the source layout convention when using **--module-source-path**. The authoritative module name remains the name in module-info.java. Keeping the directory name and module name consistent makes the project easier to read and reduces confusion during builds.

## 4. Module naming conventions

Module names usually follow the reverse domain name convention, similar to package names:

~~~text
com.example.inventory
org.example.reporting
vn.company.learning.module
~~~

You should choose a name that is:

- Stable throughout the module's lifecycle.
- Unique within the module system used by the application.
- Easily associated with the organization or product that owns the module.
- Independent of version names or build artifact names.

Module names are case-sensitive. Name components are separated by dots and follow Java identifier rules. Do not arbitrarily use a package name or JAR name as the module name; choose a meaningful name and keep it consistent across the descriptor and consumer **requires** directives.

The JAR file name does not determine the identity of an explicit named module. For example, the file **inventory-release.jar** can still contain a module named **com.example.inventory**. When another module declares a dependency, it uses the name in the descriptor:

~~~java
module com.example.checkout {
    requires com.example.inventory;
}
~~~

To avoid confusion in builds and operations, it is good practice to name the JAR close to the module name, but the module name in the descriptor is the fundamental information used for resolution.

## 5. How the compiler turns module-info.java into a binary descriptor

The Java compiler reads module-info.java along with the source files in the module. The compilation output contains **module-info.class** at the root of the module's output directory.

Example compiling the inventory module:

~~~bash
javac -d out --module-source-path src -m com.example.inventory
~~~

After compilation, the output structure looks like:

~~~text
out/
└── com.example.inventory/
    ├── module-info.class
    └── com/
        └── example/
            └── inventory/
                ├── Main.class
                └── api/
                    └── Product.class
~~~

The module-info.class file contains the descriptor information as bytecode metadata. It is not an ordinary Java class that the application instantiates or invokes methods on. The Java compiler, JAR tool, and module system use this metadata to identify the module.

You can view the output structure with a file listing command:

~~~text
out/com.example.inventory/module-info.class
out/com.example.inventory/com/example/inventory/Main.class
out/com.example.inventory/com/example/inventory/api/Product.class
~~~

If the output does not have module-info.class at the module root, check the location of module-info.java in the source tree and how javac was invoked. Placing the descriptor file inside a package, such as **src/com.example.inventory/com/example/inventory/module-info.java**, is an incorrect layout.

## 6. Packaging into a modular JAR

An explicit named module is usually distributed as a modular JAR. When packaging, keep module-info.class at the root of the JAR alongside the compiled classes.

Create a directory for JARs:

~~~bash
mkdir -p mods
~~~

Package the compiled module:

~~~bash
jar --create --file mods/com.example.inventory.jar \
    -C out/com.example.inventory .
~~~

You can list the JAR contents:

~~~bash
jar --list --file mods/com.example.inventory.jar
~~~

The output should have the descriptor at the root:

~~~text
META-INF/
module-info.class
com/example/inventory/Main.class
com/example/inventory/api/Product.class
~~~

Specific entries may vary depending on module contents, but **module-info.class** must reside at the root of the JAR for a standard modular JAR. If the descriptor is placed in the wrong location or omitted from the JAR, module tools will not recognize that artifact as an explicit named module as intended.

To verify the module name and descriptor:

~~~bash
jar --describe-module --file mods/com.example.inventory.jar
~~~

This command displays the module name, packages, and directives recorded in the descriptor. This is a useful verification step after building or when receiving a JAR from another team.

## 7. Placing an explicit named module on the module path

The module path is where Java looks for modules to resolve. It can be a directory containing modular JARs or compiled module directories arranged in an exploded module layout.

Run the module from the output directory:

~~~bash
java --module-path out \
     -m com.example.inventory/com.example.inventory.Main
~~~

Run the module from the directory containing the JAR:

~~~bash
java --module-path mods \
     -m com.example.inventory/com.example.inventory.Main
~~~

The **-m module/class** syntax specifies the module and the class containing the main method. The module name must match the descriptor, and the class name must be the fully qualified name of the class containing main.

If you want to specify the main class via the module name without repeating the class name in the run command, you can configure Main-Class in the modular JAR's manifest and use a launch method compatible with the manifest. For learning examples, explicitly writing **module/class** helps clearly see the module and program entry point.

When using **--module-path**, Java performs module resolution. The selected root module along with the dependencies required by its descriptor form the runtime configuration. Not every JAR located in the module path directory automatically becomes an active module at runtime; the module system resolves from the root modules and their related dependencies.

## 8. Explicit named modules and encapsulation

One of the primary benefits of an explicit named module is controlling which packages other modules can access.

Example:

~~~java
module com.example.inventory {
    exports com.example.inventory.api;
}
~~~

Another module can declare:

~~~java
module com.example.checkout {
    requires com.example.inventory;
}
~~~

The checkout module can use public types in the **com.example.inventory.api** package. The **com.example.inventory.internal** package is not exported, so it does not become regular API for the checkout module.

A few important rules:

- Exports are declared at the package level, not per individual class or method.
- Only public types and members can be accessed according to standard Java rules; class and member modifiers still take effect.
- Exporting a parent package does not automatically export subpackages.
- **opens** serves deep reflection, unlike **exports** which serves normal API access.
- **exports ... to** restricts which consumers can access the package.
- A module that declares no exports can still use its own internal packages.

Example of opening a package to a persistence framework:

~~~java
module com.example.inventory {
    exports com.example.inventory.api;

    opens com.example.inventory.model
        to com.example.persistence;
}
~~~

In this descriptor, the API package is published for normal access, while the model package is opened only to the persistence module so the framework can perform deep reflection under JPMS rules.

## 9. Distinguishing explicit, automatic, and unnamed modules during migration

When migrating an application from the classpath to the module path, it is necessary to determine the module type of each dependency.

**Explicit named module**

A JAR with a valid module-info.class. The module name, requires, exports, opens, uses, and provides are clearly declared. This is the form to aim for once a module is designed and controlled.

**Automatic module**

A JAR without module-info.class but placed on the module path. The module name can be determined from the **Automatic-Module-Name** manifest attribute; if this attribute is absent, Java derives the name from the JAR file name according to module system rules. An automatic module typically reads other named modules and exports its packages to assist migrating legacy libraries. Therefore, it lacks explicitly designed encapsulation boundaries like an explicit module.

**Unnamed module**

Classes on the classpath belong to the unnamed module of their corresponding class loader. It has no module name declared in module-info.java. Traditional source code can continue running on the classpath while other parts of the application have been modularized, though it is necessary to understand the interaction rules between named modules and unnamed modules.

The **Automatic-Module-Name** attribute in the manifest helps assign a stable name to an automatic module; it does not replace module-info.java and does not turn the JAR into an explicit named module. To have an explicit descriptor, you need to create module-info.java, compile, and repackage the JAR.

## 10. Open packages and open modules

In addition to the regular declaration form:

~~~java
module com.example.inventory {
    opens com.example.inventory.model;
}
~~~

Java allows declaring an **open module**:

~~~java
open module com.example.inventory {
    requires java.sql;

    exports com.example.inventory.api;
}
~~~

An open module opens all packages of the module for deep reflection at runtime. It can be used when frameworks need deep access into many packages, though its scope is broader than declaring a few **opens** or **opens ... to** directives.

An open module is still an explicit named module: it still has a name and a module descriptor. The **open** keyword changes the package reflection policy; it does not remove dependencies, exports, or module identity. When only certain packages need reflection, consider opening just the necessary packages and restricting which modules receive access.

## 11. Inspecting module descriptors and dependencies

Several JDK tools help inspect artifacts after compilation and packaging:

~~~bash
# Display the descriptor of a modular JAR
jar --describe-module --file mods/com.example.inventory.jar
~~~

~~~bash
# List JAR contents to verify module-info.class
jar --list --file mods/com.example.inventory.jar
~~~

~~~bash
# Show module resolution when running
java --show-module-resolution \
     --module-path mods \
     -m com.example.inventory/com.example.inventory.Main
~~~

~~~bash
# Analyze module dependencies
jdeps --module-path mods --module com.example.inventory
~~~

When reading the output, check:

1. Does the module name in the descriptor match the name the consumer uses in requires?
2. Does the JAR contain module-info.class in the right location?
3. Can the declared dependencies be found on the module path?
4. Are the packages that need to be shared exported to the consuming module?
5. Is the runtime using the freshly built artifact or picking up an old JAR?

If a build tool creates the JAR, check the packaging configuration to make sure module-info.class is retained. A JAR built from the wrong output directory might contain classes but lack the descriptor, causing behavior on the module path to differ from expectations.

## 12. Common errors

**module not found**

The module name in requires does not match the descriptor name, or the module dependency is not on the module path. Use jar --describe-module to check the actual name of the JAR and review the module path location.

**module-info.java is not recognized**

The descriptor file was placed inside a package, has the wrong file name, or the javac command is not compiling with a modular structure. Place module-info.java at the module's source root and use appropriate modular compilation options.

**JAR has classes but is not recognized as an explicit module**

The JAR may have been packaged without module-info.class. List the JAR contents, inspect the descriptor in the output directory, and recreate the artifact from the correct module directory.

**Package is not visible**

The consuming module may not have a requires directive for the module owning the package, or the package has not been exported. Check both conditions; merely having the JAR on the module path does not grant package access.

**Works on the classpath but fails on the module path**

When moving to the module path, JPMS enforces the module graph and encapsulation. Identify which dependencies are undeclared, which packages are unexported, or which frameworks need opens. Do not resolve every error by opening all packages.

**JAR name and module name differ**

The JAR name does not determine the explicit module name. Use the descriptor as the source of truth and keep the module name stable in requires directives.

## 13. Complete workflow for creating an explicit named module

When starting a new module, you can follow this sequence:

1. Choose a stable module name, for example **com.example.inventory**.
2. Create the module source directory and place **module-info.java** at the root.
3. Declare dependencies using requires.
4. Export only packages that are truly public API.
5. Only use opens on packages when frameworks need deep reflection.
6. Compile with javac using the module source path.
7. Verify the output has module-info.class at the module root.
8. Package the JAR and inspect it with jar --describe-module.
9. Place the JAR on the module path and run using the module/class syntax.
10. Verify module resolution and dependencies in the deployment environment.

Once complete, you can explain how an explicit named module is created from module-info.java, where the descriptor is stored, how the module name is used in requires, and why a modular JAR can be resolved on the module path. This is the foundation for designing Java modules with clear dependencies, controlled public APIs, and maintainable structure.