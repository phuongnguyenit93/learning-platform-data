# Module descriptor in Java

A module descriptor is the formal declaration of a Java module: the module name, the modules it depends on, which packages are exported, which packages are opened for reflection, and which services the module uses or provides. In the Java Platform Module System (JPMS), the descriptor is written in the **module-info.java** file and compiled into **module-info.class**.

The module descriptor is part of the Java toolchain: `javac` reads the descriptor to check dependencies and access permissions at compile time; the JVM uses it to resolve modules at startup; and tools such as `jar`, `jdeps`, and `javap` help package, analyze, and inspect module configurations.

Example descriptor:

~~~java
module com.example.orders {
    requires java.logging;
    exports com.example.orders.api;
    opens com.example.orders.model;
}
~~~

Here, the module is named com.example.orders, depends on java.logging, exports the api package, and opens the model package for deep reflection. These directives form the contract between the module and the rest of the application.

## 1. Java modules and the module descriptor

A Java module is a unit for organizing source code and dependencies at a higher level than a package. A module can contain multiple packages; the descriptor specifies how those packages and dependencies are visible from other modules.

JPMS was introduced in Java 9. Before JPMS, Java primarily organized code using packages and managed dependencies via the classpath. The classpath has no dependency declarations or clear export boundaries; multiple libraries can see each other simply because they are on the same classpath.

The module system adds:

- **Readability:** a module declares which modules it needs to read via requires.
- **Strong encapsulation:** a package is only accessible from another module when it is exported or opened according to the rules.
- **Dependency resolution:** the JVM checks and links the required modules at startup.
- **Service binding:** a module can declare uses/provides to use the ServiceLoader mechanism.
- **Module metadata:** directives are stored in module-info.class for tools and the JVM to read.

The module descriptor does not replace packages. Packages still organize class names; modules organize packages and define dependency boundaries.

Module names typically use reverse-domain notation, such as com.example.orders or org.acme.reporting. Module names are case-sensitive and consist of Java identifiers separated by dots. Do not use hyphens like those in Maven artifact names as Java module names.

## 2. module-info.java and module-info.class

The descriptor source file must be named exactly **module-info.java**. It is located at the root of the module's source tree, not inside a package.

Example:

~~~text
src/
└── com.example.orders/
    ├── module-info.java
    └── com/
        └── example/
            └── orders/
                ├── api/
                │   └── OrderService.java
                └── internal/
                    └── OrderRepository.java
~~~

Contents of module-info.java:

~~~java
module com.example.orders {
    requires java.logging;
    exports com.example.orders.api;
}
~~~

When compiled, javac generates module-info.class in the module's output root. This class file has a special structure:

- The internal class name is module-info.
- Class access_flags contains ACC_MODULE.
- It has a Module attribute storing the module name and directives.
- It has no regular fields or methods like a standard Java class.
- It may contain other related attributes such as ModulePackages or ModuleMainClass depending on the artifact.

ACC_MODULE has the value 0x8000 in ClassFile.access_flags. This is a flag identifying a module descriptor, not a modifier to be written on regular classes.

A typical module source has only one module-info.java. A module descriptor compilation unit declares exactly one module; multiple module declarations cannot be placed in the same file.

## 3. Basic structure of a descriptor

General syntax:

~~~java
module module.name {
    requires other.module;
    exports package.name;
    opens package.name;
    uses service.Type;
    provides service.Type with provider.Type;
}
~~~

Not all directives are required to appear. Only declare the dependencies, APIs, and services that the module actually needs.

A valid empty descriptor:

~~~java
module com.example.empty {
}
~~~

The module is still a named module, even without declaring any dependencies or package exports. A regular module still implicitly reads java.base; there is no need to write requires java.base.

Some important rules:

- requires declares a module dependency.
- exports exposes a package for normal Java access.
- opens allows deep reflection.
- uses declares a service that the module needs to look up.
- provides declares an implementation for a service.
- open module opens all packages of the module for deep reflection.
- An open module must not simultaneously declare individual opens directives inside the descriptor body.

## 4. requires: declaring dependencies

The requires directive indicates that the current module needs to read another module.

~~~java
module com.example.orders {
    requires java.logging;
    requires com.example.customer;
}
~~~

When compiling the orders module, javac needs to find java.logging and com.example.customer on the module path or in the appropriate module system image.

### requires transitive

requires transitive makes a dependency part of the transitively propagated dependency API. Other modules that read the current module also read that transitive dependency.

Example:

~~~java
module com.example.api {
    requires transitive java.sql;
    exports com.example.api;
}
~~~

If the public API of com.example.api exposes types from java.sql, modules using this API may need to read java.sql. requires transitive expresses that relationship in the descriptor.

Do not use transitive just to make a build pass. Only declare it when the dependency is genuinely part of the public API contract.

### requires static

requires static indicates a dependency required at compile time, but not mandatory during runtime resolution in the same way as a regular requires.

~~~java
module com.example.reporting {
    requires static java.compiler;
}
~~~

This directive is useful for optional dependencies, such as annotations or APIs needed only at compile time. If the code actually needs classes from that module when executing a specific branch, the application must ensure the dependency is present at runtime when that branch is used.

Modifiers can be combined:

~~~java
module com.example.adapter {
    requires static transitive com.example.spi;
}
~~~

static and transitive are modifiers of requires. In the class file, they are represented by module-specific flags such as ACC_STATIC_PHASE and ACC_TRANSITIVE in requires_flags.

### java.base is an implicit dependency

Every regular module reads java.base. Therefore, you do not need to write:

~~~java
requires java.base;
~~~

If you inspect the compiled descriptor with javap, you will see requires java.base with the mandated flag even though the source did not declare this directive. This is a dependency added by the module system by rule.

## 5. exports: exposing packages

The exports directive allows other modules to access public types in the exported package.

~~~java
module com.example.orders {
    exports com.example.orders.api;
}
~~~

If another module declares:

~~~java
module com.example.app {
    requires com.example.orders;
}
~~~

then code in the app module can import public types from com.example.orders.api.

Exports does not automatically turn package-private or private members into public ones. Java language access rules still apply after module readability and package export are satisfied.

Subpackages are not automatically exported along with parent packages. For example, exports com.example.api does not imply exports com.example.api.internal.

### Qualified exports

You can restrict a package to be exported only to specific modules:

~~~java
module com.example.orders {
    exports com.example.orders.spi to
        com.example.plugin,
        com.example.integration;
}
~~~

This is a qualified export. A module not in the list cannot access the package through that export, even if it has a requires on the orders module.

Qualified exports are useful when you want to expose an SPI to a specific set of integration modules while keeping internal packages from being broadly accessed.

## 6. opens: allowing deep reflection

Exports and opens serve two different purposes:

- exports allows normal access to the public API of a package.
- opens allows deep reflection into a package according to JPMS rules.

ORM, dependency injection, or serialization frameworks sometimes need to access non-public fields, constructors, or members. For named modules, the package may need to be opened to that framework.

~~~java
module com.example.model {
    opens com.example.model.entity;
}
~~~

The directive above opens the package for deep reflection from other modules according to module system rules.

### Qualified opens

You can open a package only to a specific module:

~~~java
module com.example.model {
    opens com.example.model.entity to com.example.orm;
}
~~~

Only the com.example.orm module is granted deep reflection access by this directive.

### open module

If you want to open all packages of a module:

~~~java
open module com.example.model {
    requires com.example.orm;
}
~~~

An open module opens all of its packages for deep reflection. Inside an open module, do not declare separate opens directives. You can still declare requires, exports, uses, and provides.

Only open the packages that actually need it. Opening an entire module reduces encapsulation and may allow frameworks or other code to access internals more deeply than intended.

## 7. uses and provides: ServiceLoader

JPMS integrates service binding into the module descriptor.

- uses declares that a module needs a service interface.
- provides ... with ... declares that a module supplies an implementation for that service.

Example application module:

~~~java
module com.example.app {
    requires com.example.greeter.api;
    uses com.example.greeter.GreetingService;
}
~~~

Example provider module:

~~~java
module com.example.greeter.provider {
    requires com.example.greeter.api;

    provides com.example.greeter.GreetingService
        with com.example.greeter.impl.DefaultGreetingService;
}
~~~

In Java code, the application can look up the implementation:

~~~java
GreetingService service = ServiceLoader
        .load(GreetingService.class)
        .findFirst()
        .orElseThrow();
~~~

The app module does not need to directly require the provider module to use the service abstraction. When running with the module path and service binding, the module system can locate providers declared for the service that app uses.

The provider class in the example uses a public no-argument constructor. JPMS also supports provider methods according to ServiceLoader rules, provided they follow the specified structure and return type.

ServiceLoader helps modules depend on abstractions. New providers can be added without modifying the service lookup code, as long as the provider module is present and properly configured.

## 8. Module readability and accessibility

For a public type from another module to be usable, the following conditions typically need to be met:

1. The current module reads the module containing that type.
2. The module containing the type exports the corresponding package to the current module.
3. The type and member being used have appropriate access levels under Java language rules.
4. Module resolution locates the required module and dependencies.

For example, the app module needs to read the API module:

~~~java
module com.example.app {
    requires com.example.api;
}
~~~

The API module must export the package:

~~~java
module com.example.api {
    exports com.example.api;
}
~~~

If requires is missing, javac may report that the package is in a module but the current module does not read it. If exports is missing, the package exists but is not exposed to the app module.

requires does not imply exports: one directive describes which dependencies the current module needs; the other describes which packages the current module allows other modules to access.

The module system also has an implicit readability relationship with java.base, as well as relationships extended through requires transitive, automatic modules, or compatibility options.

## 9. Classpath, module path, and module types

Java has two common ways to load libraries:

### Classpath and the unnamed module

JARs or class directories on the classpath are treated as belonging to the unnamed module of the corresponding class loader. The unnamed module can read other modules, and its packages are not governed by a descriptor in the way named modules are.

Traditional classpath execution:

~~~bash
java -cp "lib/*:build/classes" com.example.app.Main
~~~

On Windows, the classpath separator is a semicolon:

~~~powershell
java -cp "lib/*;build/classes" com.example.app.Main
~~~

### Module path and named modules

The module path contains modular JARs or exploded modules. The JVM resolves modules according to their descriptors and dependencies.

~~~bash
java --module-path mlib -m com.example.app/com.example.app.Main
~~~

--module-path specifies where to find modules. -m or --module specifies the module and main class to run.

### Automatic modules

A JAR without module-info.class that is placed on the module path can become an automatic module. Its module name can be determined by Automatic-Module-Name in the manifest or derived from the JAR filename.

Automatic modules support the transition period from the classpath to JPMS. They have broader compatibility behavior than regular named modules, but do not provide a detailed encapsulation contract like an explicit descriptor.

### Unnamed module and named modules

Code on the classpath belongs to the unnamed module. A named module cannot declare requires on the unnamed module. When migrating legacy libraries to JPMS, you can start with automatic modules or organize dependencies to gradually transition to named modules.

Do not treat automatic modules as the final design if a library needs clear module boundaries. Add an explicit descriptor whenever possible.

## 10. Module descriptors in the javac, jar, and java toolchain

A modular build workflow typically includes the following steps:

1. Organize source code by module.
2. Write module-info.java for each module.
3. Compile with javac using module source path and module path as needed.
4. Inspect module-info.class with javap.
5. Package modules into modular JARs with jar.
6. Inspect JARs with jar --describe-module.
7. Run with java --module-path and --module.

### javac --module-source-path

When multiple modules reside under the same source root:

~~~text
src/
├── com.example.api/
│   ├── module-info.java
│   └── com/example/api/Greeter.java
└── com.example.app/
    ├── module-info.java
    └── com/example/app/Main.java
~~~

You can compile by module name:

~~~bash
javac --release 17 \
    --module-source-path src \
    -d mods \
    -m com.example.api,com.example.app
~~~

--module-source-path specifies the source root containing the modules. -d specifies the output root. -m selects the modules to compile.

### javac --module-path

If the app module depends on pre-built modular JARs:

~~~bash
javac --release 17 \
    --module-path mlib \
    -d mods \
    --module-source-path src \
    -m com.example.app
~~~

The module path contains the required dependency modules. Javac reads the descriptors of those modules to verify requires and exports.

### jar packaging modular JARs

After compiling, each exploded module can be packaged into a JAR:

~~~bash
jar --create \
    --file mlib/com.example.api.jar \
    -C mods/com.example.api .
~~~

The module descriptor module-info.class is kept at the root of the JAR. When the JAR is placed on the module path, the JVM can recognize it as a named module.

### java running a module

~~~bash
java --module-path mlib \
    --module com.example.app/com.example.app.Main
~~~

You can use the shorthand -m instead of --module. If the module declares a main class via ModuleMainClass or an appropriate manifest, the invocation can be simpler, but explicitly specifying module/class makes the command clearer.

## 11. Complete Java 17+ example: three modules using ServiceLoader

This example creates three modules:

- **com.example.greeter.api:** exposes the service interface.
- **com.example.greeter.provider:** provides the implementation.
- **com.example.greeter.app:** looks up the service and runs the application.

Source structure:

~~~text
module-demo/
└── src/
    ├── com.example.greeter.api/
    │   ├── module-info.java
    │   └── com/example/greeter/GreetingService.java
    ├── com.example.greeter.provider/
    │   ├── module-info.java
    │   └── com/example/greeter/impl/DefaultGreetingService.java
    └── com.example.greeter.app/
        ├── module-info.java
        └── com/example/greeter/app/Main.java
~~~

### Step 1: API module

File src/com.example.greeter.api/module-info.java:

~~~java
module com.example.greeter.api {
    exports com.example.greeter;
}
~~~

File src/com.example.greeter.api/com/example/greeter/GreetingService.java:

~~~java
package com.example.greeter;

public interface GreetingService {
    String greeting();
}
~~~

The package is exported so that the app and provider modules can import the interface.

### Step 2: provider module

File src/com.example.greeter.provider/module-info.java:

~~~java
module com.example.greeter.provider {
    requires com.example.greeter.api;

    provides com.example.greeter.GreetingService
        with com.example.greeter.impl.DefaultGreetingService;
}
~~~

File src/com.example.greeter.provider/com/example/greeter/impl/DefaultGreetingService.java:

~~~java
package com.example.greeter.impl;

import com.example.greeter.GreetingService;

public final class DefaultGreetingService
        implements GreetingService {

    public DefaultGreetingService() {
    }

    @Override
    public String greeting() {
        return "Hello from JPMS ServiceLoader.";
    }
}
~~~

The provider module reads the API module and advertises the implementation via provides. The implementation package does not need to be exported just for the module system to load the provider declared in the descriptor.

### Step 3: application module

File src/com.example.greeter.app/module-info.java:

~~~java
module com.example.greeter.app {
    requires com.example.greeter.api;
    uses com.example.greeter.GreetingService;
}
~~~

File src/com.example.greeter.app/com/example/greeter/app/Main.java:

~~~java
package com.example.greeter.app;

import com.example.greeter.GreetingService;
import java.util.ServiceLoader;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        GreetingService service = ServiceLoader
                .load(GreetingService.class)
                .findFirst()
                .orElseThrow();

        System.out.println(service.greeting());
    }
}
~~~

The app module declares uses so the module system knows which service needs to be bound at runtime.

### Step 4: compile the modules

From the module-demo root directory:

~~~bash
mkdir -p mods
javac --release 17 \
    --module-source-path src \
    -d mods \
    -m com.example.greeter.api,com.example.greeter.provider,com.example.greeter.app
~~~

The output looks like:

~~~text
mods/
├── com.example.greeter.api/
│   ├── module-info.class
│   └── com/example/greeter/GreetingService.class
├── com.example.greeter.provider/
│   ├── module-info.class
│   └── com/example/greeter/impl/DefaultGreetingService.class
└── com.example.greeter.app/
    ├── module-info.class
    └── com/example/greeter/app/Main.class
~~~

### Step 5: run from exploded modules

~~~bash
java --module-path mods \
    --module com.example.greeter.app/com.example.greeter.app.Main
~~~

Output:

~~~text
Hello from JPMS ServiceLoader.
~~~

The module system locates the app module, reads requires and uses, and then finds a matching provider on the module path.

### Step 6: package into modular JARs

Create the directory:

~~~bash
mkdir -p mlib
~~~

Package each module:

~~~bash
jar --create --file mlib/com.example.greeter.api.jar \
    -C mods/com.example.greeter.api .

jar --create --file mlib/com.example.greeter.provider.jar \
    -C mods/com.example.greeter.provider .

jar --create --file mlib/com.example.greeter.app.jar \
    -C mods/com.example.greeter.app .
~~~

Inspect the module:

~~~bash
jar --describe-module --file mlib/com.example.greeter.app.jar
~~~

This command describes the app module, requires API, and uses service. The exact line formatting depends on the JDK.

Run the modular JARs:

~~~bash
java --module-path mlib \
    --module com.example.greeter.app/com.example.greeter.app.Main
~~~

The output is still:

~~~text
Hello from JPMS ServiceLoader.
~~~

## 12. Inspecting descriptors with javap and jar

### javap -v

You can read module-info.class directly:

~~~bash
javap -v mods/com.example.greeter.app/module-info.class
~~~

Key parts of the output include:

- flags: (0x8000) ACC_MODULE: confirms this is a module descriptor.
- Module: attribute containing the module name and directives.
- requires: dependencies, including the mandated java.base.
- uses: services the module needs.
- exports or opens: packages and corresponding target modules.
- provides: services and provider classes.

Constant pool indices and line formatting vary by class file; read the actual directive and module names rather than comparing index numbers against another sample output.

### jar --describe-module

For modular JARs:

~~~bash
jar --describe-module --file mlib/com.example.greeter.app.jar
~~~

This command displays a human-readable module description, suitable for quick verification after packaging.

List JAR contents:

~~~bash
jar --list --file mlib/com.example.greeter.app.jar
~~~

Confirm that module-info.class is at the root of the archive. If the descriptor is placed in a nested subdirectory, the JAR may not be recognized as a named module as intended.

### jdeps

jdeps analyzes dependencies at the package and module levels:

~~~bash
jdeps --module-path mlib --check com.example.greeter.app
~~~

You can use jdeps to check module dependencies, find undeclared dependencies, or analyze library modules. The exact options depend on the analysis goal and JDK version; see jdeps --help when needed.

## 13. Module flags and attributes in class files

A module descriptor has a class access flag and module-specific flags in the Module attribute.

### ACC_MODULE

- Value: 0x8000.
- Location: ClassFile.access_flags.
- Meaning: the class file is a module descriptor module-info.class.

### Module flags

| Flag | Hex value | Meaning |
|---|---:|---|
| ACC_OPEN | 0x0020 | The module is an open module |
| ACC_SYNTHETIC | 0x1000 | The module was synthetically generated |
| ACC_MANDATED | 0x8000 | The module was included by mandatory rule |

### requires_flags

| Flag | Hex value | Meaning |
|---|---:|---|
| ACC_TRANSITIVE | 0x0020 | The dependency is transitive |
| ACC_STATIC_PHASE | 0x0040 | The dependency is required at compile time |
| ACC_SYNTHETIC | 0x1000 | The directive was synthetically generated |
| ACC_MANDATED | 0x8000 | The directive was added by mandatory rule |

Bit values must be decoded according to the specific field. For example, 0x0020 is ACC_SUPER in class access_flags, ACC_SYNCHRONIZED in method access_flags, ACC_OPEN in Module flags, and ACC_TRANSITIVE in requires_flags.

The Module attribute may also be accompanied by attributes such as ModulePackages, ModuleMainClass, ModuleTarget, or ModuleHashes depending on the artifact. Not every module-info.class contains all of these attributes.

## 14. Automatic modules and migration from the classpath

Legacy libraries often lack module-info.class. When placing such a JAR on the module path, Java can create an automatic module.

The automatic module name can be taken from the manifest attribute:

~~~text
Automatic-Module-Name: com.example.legacy
~~~

If this attribute is absent, the name can be derived from the normalized JAR filename. Derived names can be unstable if the artifact is renamed; libraries that want to support JPMS should publish a stable Automatic-Module-Name or provide a real module descriptor.

An automatic module can read other modules and broadly exports its packages to support migration. This is a transitional mechanism; it does not have clear API boundaries like an explicit named module.

A typical migration path is:

1. Identify the library's dependencies and packages.
2. Place the legacy JAR on the module path as an automatic module.
3. Note the actual module name using jar --describe-module.
4. Gradually replace dependencies or update libraries to have explicit descriptors.
5. Declare requires and exports clearly.
6. Move application code to the module path and test reflection.

You cannot write requires on the unnamed module. If a dependency is only available on the classpath, consider placing it on the module path as an automatic module or keeping the corresponding application part in the unnamed module during the transition.

## 15. Compatibility options for migration

The JVM provides several options to support legacy applications during the transition to JPMS:

- --add-reads: adds a readability relationship between modules.
- --add-exports: exports a package to a target module at runtime.
- --add-opens: opens a package for deep reflection at runtime.
- --patch-module: adds or replaces classes/resources in a module.

Example:

~~~bash
java --add-opens java.base/java.lang=ALL-UNNAMED \
    -jar legacy-app.jar
~~~

This command opens the java.lang package of java.base to the unnamed module to support deep reflection. This is a compatibility example; use it only when you understand why the framework needs internal access.

These options should be treated as migration measures or deliberate configuration. Do not use them to mask an incorrect descriptor or grant broader access than needed. Once libraries properly support JPMS, remove overrides that are no longer necessary.

## 16. Common errors and how to diagnose them

**Module not found at compile time**

Check the module path, the module name in requires, and whether the module has been built. If the dependency is a modular JAR, ensure the JAR is located directly on or in a directory scanned by the module path.

**Package exists but is not visible**

The current module may be missing a requires, or the module providing the package has not exported it. Check both descriptors.

**Package is not exported**

The package may exist but is not accessible to the other module. Add exports if it is genuinely part of the public API; use opens only when deep reflection is needed.

**IllegalAccessException or InaccessibleObjectException**

A framework may need the package to be opened. Prefer updating the framework or declaring a narrow opens to the specific module; only use --add-opens when temporary runtime configuration is needed.

**ServiceLoader cannot find provider**

Check that the consumer module has uses, the provider module has provides, the provider module is on the module path, and the implementation satisfies ServiceLoader rules.

**Module name mismatch**

The module source directory name, the name in module-info.java, the module name in requires, and the module name used at runtime must be consistent. For automatic modules, check the name displayed by jar --describe-module.

**Works on classpath but fails on module path**

The classpath does not enforce readability/export boundaries like named modules do. Check package access, reflection, and undeclared dependencies.

**JAR is not recognized as a modular JAR**

Verify that module-info.class is at the root of the JAR, not inside a nested subdirectory. Use jar --describe-module to confirm how the JDK identifies the artifact.

**Stale module descriptor left behind**

Clean the output directory before rebuilding if you have changed module-info.java or the package layout. Avoid packaging a stale module-info.class from an earlier compile.

## 17. Workflow for designing and testing a module descriptor

1. Choose a stable, recognizable module name.
2. Identify which packages belong to the public API and which are internal.
3. Declare minimal requires; use transitive when a dependency is part of the public API.
4. Use requires static for dependencies needed only at compile time when appropriate.
5. Only exports packages that need to be public.
6. Use narrow opens for frameworks that need deep reflection.
7. Declare uses/provides if using ServiceLoader in named modules.
8. Compile with javac using an explicit module source path and module path.
9. Inspect module-info.class with javap -v.
10. Package and inspect with jar --describe-module.
11. Run the application with java --module-path on the target runtime.
12. Test the API, reflection, service binding, and dependency migration.
13. Remove temporary --add-reads/--add-exports/--add-opens options when no longer needed.

The module descriptor is the contract for a module's dependencies and access boundaries. When requires, exports, opens, uses, and provides are declared properly, the Java toolchain can check dependencies early, package modules consistently, and help the JVM resolve the application cleanly.
