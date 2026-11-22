# module-info.java and the Role of the Module Descriptor

The Java Platform Module System (JPMS) adds a structural layer to Java applications: instead of merely placing directories and JARs on the classpath, you can declare which modules exist, which other modules a module requires, and which packages are allowed to be used from the outside. The source-level declaration point of a named module is the `module-info.java` file.

This file is compiled into `module-info.class`, which contains metadata called the **module descriptor**. The descriptor does not contain business logic. It describes the module's contract with the system: identity, dependencies, public API, reflection permissions, and the services that the module uses or provides.

## 1. What Is module-info.java?

`module-info.java` is a special Java compilation unit. It contains a top-level module declaration, does not declare a regular class, and does not reside inside the packages of business classes.

Example of a module named `com.example.catalog`:

```text
catalog/
└── src/
    └── com.example.catalog/
        ├── module-info.java
        └── com/
            └── example/
                └── catalog/
                    ├── api/
                    │   └── Product.java
                    └── internal/
                        └── ProductRepository.java
```

The descriptor file sits at the module's source root. The remaining classes are still organized into regular Java packages.

A module can start with an empty descriptor:

```java
module com.example.catalog {
}
```

When you need to use other modules or expose packages, you add directives:

```java
module com.example.catalog {
    requires java.sql;

    exports com.example.catalog.api;
}
```

In this example, the module is named `com.example.catalog`, needs to read the `java.sql` module, and exposes the `com.example.catalog.api` package.

Module names usually follow the reverse domain name convention, such as `com.example.catalog`, to reduce the chance of name collisions. Module names and package names are two separate concepts: a single module can contain multiple packages.

## 2. From module-info.java to Module Descriptor

When compiling a module, `javac` processes `module-info.java` together with the module's source files. The source-form descriptor file is transformed into `module-info.class`.

```text
module-info.java + .java files
             |
             | javac
             v
       module-info.class
       .class files
             |
             | JAR packaging
             v
       modular JAR
             |
             | module path
             v
       module resolution and module graph
```

Two terms should be distinguished:

- **`module-info.java`** is the source file written by the developer.
- **Module descriptor** is the metadata describing the module; in compiled artifacts, this metadata is stored in `module-info.class`.

A modular JAR typically places `module-info.class` at the root of the JAR, alongside the compiled packages and classes. When the JAR is placed on the module path, Java tools read the descriptor to recognize the module and its directives.

The descriptor does not contain business logic code, nor is it the entire module graph of the application. Each descriptor describes the module it belongs to. At runtime, Java combines the descriptors of the relevant modules to resolve the module graph for that environment.

## 3. General Syntax

A module declaration has the form:

```java
[open] module module.name {
    requires other.module;
    exports some.package;
    opens another.package;
    uses some.service.Interface;
    provides some.service.Interface
        with some.provider.Implementation;
}
```

Components:

- `module` begins the module declaration.
- `module.name` is the module name.
- The `open` keyword is optional, used to open all packages for deep reflection.
- Directives inside the declaration body describe dependencies, packages, reflection, and services.

A descriptor may have no directives at all. When a module needs additional capabilities, you declare only the relationships that are genuinely required. Directives can be grouped so readers can easily spot dependencies and the public API.

## 4. Directives in a Module Descriptor

### 4.1. requires: Declaring Dependencies

`requires` declares that the current module needs to read another module:

```java
module com.example.orders {
    requires com.example.catalog;
    requires java.sql;
}
```

If the source code of `com.example.orders` uses types exposed by `com.example.catalog`, the orders module must declare this relationship. Java uses this information during compilation and when resolving the module graph.

Every named module implicitly has a readability relationship to `java.base`, so you do not need to write `requires java.base;`. Other JDK modules such as `java.sql`, `java.logging`, or `java.xml` must be declared when the module uses them.

There are two common modifiers:

**`requires transitive`**

```java
module com.example.catalog {
    requires transitive com.example.money;
    exports com.example.catalog.api;
}
```

`transitive` exposes the dependency to modules that read the current module. If catalog's public API uses types belonging to `com.example.money`, a module using catalog may also need to read money to compile and use that API. In that case, `requires transitive` expresses that this dependency is part of the API contract.

You should not use `transitive` merely as a convenience to pass dependencies along. It affects the readability of modules that depend on the current module.

**`requires static`**

```java
module com.example.reporting {
    requires static com.example.annotations;
}
```

`static` indicates a dependency that is required at compile time but not mandatory at runtime solely because the descriptor declares it. This modifier is typically suitable for certain annotation libraries or compile-time-only dependencies. If the actual code needs that class when running, the application must still provide the corresponding runtime dependency.

The two modifiers can be combined:

```java
requires static transitive com.example.annotations;
```

Use this combination only when both compile-time semantics and transitive dependency match the module contract.

### 4.2. exports: Exposing Packages

`exports` allows other modules to access public types in the exposed package:

```java
module com.example.catalog {
    exports com.example.catalog.api;
}
```

Suppose the module has two packages:

```text
com.example.catalog
├── api
└── internal
```

In the descriptor above, `com.example.catalog.api` is exposed. The `com.example.catalog.internal` package does not automatically become API just because it contains classes with the `public` modifier.

You can restrict exporting to specific modules using qualified exports:

```java
module com.example.catalog {
    exports com.example.catalog.api;
    exports com.example.catalog.integration
        to com.example.orders, com.example.reporting;
}
```

In this example, the integration package is exported only to the two named modules. This approach is useful when a package serves only certain identified integration components.

Exporting does not bypass Java's access modifiers. Classes or members must still satisfy normal access rules such as `public`, `protected`, package-private, and `private`. `exports` establishes boundaries at the package/module level; it does not turn private members into public ones.

### 4.3. opens: Allowing Deep Reflection

Some frameworks need deep reflection to access non-public members, such as object-mapping, dependency injection, or serialization frameworks. `opens` permits that operation on the specified package:

```java
module com.example.catalog {
    exports com.example.catalog.api;

    opens com.example.catalog.model
        to com.example.json;
}
```

Here, the model package is opened to the `com.example.json` module. The open scope can be restricted by target module, giving the framework the permissions it needs.

A distinction should be made:

- `exports` exposes regular Java API.
- `opens` allows deep reflection at runtime.
- An exported package is not implicitly opened for deep reflection.
- An opened package does not automatically become public API for regular Java code.

If you want to open a package to all modules, you can use:

```java
opens com.example.catalog.model;
```

You should limit the open scope to the packages and frameworks that genuinely need it.

### 4.4. open module: Opening All Packages for Reflection

You can declare the entire module as open:

```java
open module com.example.legacy {
    requires java.sql;
    exports com.example.legacy.api;
}
```

With `open module`, all packages of the module are opened for deep reflection at runtime. However, packages still need `exports` if you want to expose regular Java API.

An open module does not declare individual `opens` directives inside. You should use this approach only when frameworks truly need broad reflection; if only a few packages need it, qualified `opens` maintains clearer boundaries.

### 4.5. uses and provides: Declaring Services

JPMS integrates the service model with `ServiceLoader`.

A module that uses a service declares `uses`:

```java
module com.example.application {
    requires com.example.catalog.api;

    uses com.example.catalog.spi.PriceProvider;
}
```

A module that supplies an implementation declares `provides ... with ...`:

```java
module com.example.catalog.provider {
    requires com.example.catalog.api;

    provides com.example.catalog.spi.PriceProvider
        with com.example.catalog.provider.DefaultPriceProvider;
}
```

The application can look up providers using the `ServiceLoader` API:

```java
ServiceLoader<PriceProvider> providers =
        ServiceLoader.load(PriceProvider.class);

for (PriceProvider provider : providers) {
    System.out.println(provider.priceFor("BOOK-01"));
}
```

The service interface usually resides in an exported package so consuming modules can reference it. The provider implementation class does not need to be exported solely for ServiceLoader to discover the provider declared in the descriptor.

This mechanism allows a consuming module to depend on a service interface rather than being tightly coupled to a specific implementation class.

## 5. Which Stages Does the Module Descriptor Participate In?

### 5.1. Module Identification

The name in the descriptor helps Java tools identify an explicit named module on the module path. The module name is the identity used in `requires` directives and when resolving the module graph.

A JAR without `module-info.class` can still be used as an automatic module when placed on the module path. Its name can come from the `Automatic-Module-Name` manifest attribute or be derived from the JAR filename. Automatic modules assist with migrating legacy libraries, but do not provide an explicit descriptor with fine-grained API boundaries like an explicit module.

### 5.2. Resolving the Module Graph

`requires` directives establish dependency relationships. When launching a modular application, Java starts from the root modules and resolves the required modules based on descriptors and the modules available on the module path.

If a required dependency cannot be found or the module graph cannot be validly resolved, the application can fail before business logic runs. As a result, certain structural errors are caught early.

Each module's descriptor describes only the relationships that module declares. The complete module graph is the result of the resolution process in a specific execution environment.

### 5.3. Controlling Readability and Accessibility

`requires` determines readability relationships between modules. `exports` determines which packages are accessible as public API. `opens` determines which packages are allowed for deep reflection.

At compile time, `javac` can report errors if source code uses a module that is not read or accesses a package that is not exported. At runtime, the module system continues to enforce the corresponding access rules.

### 5.4. Publishing Services

`uses` and `provides` describe service-consuming and service-providing modules. The runtime can use this metadata when locating implementations via `ServiceLoader`.

As a result, an application can swap providers without modifying every call site using the service interface, provided the new provider satisfies the same contract.

### 5.5. Supporting Java Tools

JDK tools read the module descriptor to display module information, analyze dependencies, or build runtime images. Some useful commands:

```shell
jar --describe-module --file libs/catalog.jar
java --describe-module java.sql
jdeps --summary libs/catalog.jar
```

`jar --describe-module` displays module information for a JAR; `java --describe-module` displays module information in the runtime image; `jdeps` assists in analyzing dependencies from artifacts. These tools help inspect metadata and cross-check the descriptor against compiled code structure.

## 6. Complete Example of a Module Descriptor

Suppose the geometry module has an API package, an internal package, and a class to run the application:

```text
src/
└── com.example.geometry/
    ├── module-info.java
    └── com/example/geometry/
        ├── api/
        │   └── Shape.java
        ├── internal/
        │   └── Circle.java
        └── app/
            └── Main.java
```

The `Shape.java` file:

```java
package com.example.geometry.api;

public interface Shape {
    double area();
}
```

The `Circle.java` file:

```java
package com.example.geometry.internal;

import com.example.geometry.api.Shape;

public final class Circle implements Shape {
    private final double radius;

    public Circle(double radius) {
        this.radius = radius;
    }

    @Override
    public double area() {
        return Math.PI * radius * radius;
    }
}
```

The `Main.java` file:

```java
package com.example.geometry.app;

import com.example.geometry.internal.Circle;

public class Main {
    public static void main(String[] args) {
        Circle circle = new Circle(2);
        System.out.println(circle.area());
    }
}
```

Descriptor:

```java
module com.example.geometry {
    exports com.example.geometry.api;
}
```

The geometry module exports only the API package. The `Main` class can still use `Circle` because they belong to the same module. External modules can only use public types in the exported API package.

With the source root structure above, you can compile with:

```shell
javac --module-source-path src -d out -m com.example.geometry
```

After compiling, run the main class:

```shell
java --module-path out -m com.example.geometry/com.example.geometry.app.Main
```

The `-m` option specifies the module and the main class. The `module-info.java` syntax has no directive for declaring a main class; the main class is specified at launch time or via appropriate packaging metadata.

## 7. How Does a Descriptor Differ from Maven or Gradle Configuration?

`module-info.java` belongs to the Java platform's module model. It does not replace `build.gradle`, `pom.xml`, or build tool dependency configurations.

For example, Gradle declares artifact dependencies:

```groovy
dependencies {
    implementation project(":catalog")
    implementation "org.example:json-library:1.2.0"
}
```

The descriptor declares the module relationships that Java code needs to read:

```java
module com.example.orders {
    requires com.example.catalog;
    requires com.example.json;
}
```

These two layers of information have different goals:

- Gradle/Maven manage projects, artifacts, versions, repositories, plugins, and build tasks.
- JPMS describes module identity, readability relationships, and package boundaries.
- The build configuration must supply dependencies on the right compile and runtime paths so that modules can be resolved.

Gradle project names, Maven artifact names, JAR filenames, and JPMS module names can differ. When integrating a library, you should check the actual module name published by the JAR, especially for automatic modules or third-party libraries.

## 8. Common Misconceptions

**Mistaking module-info.java for a configuration class.**

This is a special compilation unit containing only a module declaration. It has no runnable methods and is not a place for business logic.

**Confusing module names with package names.**

A module has its own identity and can contain multiple packages. A package is not automatically a module.

**Confusing exports with opens.**

Export exposes regular Java API; open allows deep reflection. A framework needing reflection does not necessarily require exporting every package.

**Assuming exporting a package makes all members public.**

Java's access modifiers remain in effect. Exporting does not turn private or package-private members into public ones.

**Declaring too many requires.**

Each dependency is a published architectural relationship. Unnecessary dependencies complicate the module graph and obscure true relationships.

**Using requires transitive for every dependency.**

This modifier affects the readability of dependent modules. Use it only when the dependency is part of the API contract.

**Opening the entire module to fix a single reflection error.**

If only one package needs deep access by a framework, consider qualified opens to limit permissions.

**Assuming the descriptor manages library versions.**

JPMS declares module relationships; it does not select artifact versions. Maven or Gradle still handles dependency resolution.

## 9. Principles for Designing module-info.java

When writing a descriptor, you should apply the following principles:

1. **Choose a stable module name:** use a consistent convention and minimize the chance of name collisions.
2. **Declare only genuinely needed dependencies:** add `requires` only for modules used by your source code or API.
3. **Export API intentionally:** expose the packages that consumers of the module need to depend on.
4. **Keep implementations internal:** do not export packages just for more convenient access from another module.
5. **Open reflection narrowly:** prefer qualified `opens` when only specific frameworks need this permission.
6. **Use services for extension points:** consider `uses` and `provides` when you want to decouple consuming modules from implementations.
7. **Control transitive dependencies:** use `requires transitive` only when the API genuinely exposes that dependency.
8. **Cross-check the descriptor with the build:** ensure the module path provides all required modules and module names match the declarations.

A clear descriptor is usually short and expresses core dependencies and API. If you have to export nearly every package or open the entire module, you should revisit module boundaries and how frameworks are integrated.

## Conclusion

`module-info.java` is where a module is declared in source code. When compiled, it produces `module-info.class`, the module descriptor used by Java tools. The descriptor specifies the module name, dependencies, packages exported or opened for reflection, and service relationships.

The descriptor supplies data for the compiler to check readability and accessibility, for the JVM to resolve the module graph and enforce module boundaries, and supports runtime analysis and packaging tools.

Think of `module-info.java` as the contract between a module and the rest of the application: what the module needs, which APIs it provides, and which packages remain internal. A clear contract makes application structure easier to understand and helps development teams change implementation details with lower risk.