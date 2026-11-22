# Module Descriptor in a Modular JAR

A **modular JAR** is a JAR file that packages a named Java module. The component that determines that the JAR is an explicit named module is the **module descriptor**: the binary file `module-info.class` placed at the root directory of the JAR. The descriptor records the module name, its dependencies, and the packages that the module exposes or opens for reflection.

The module descriptor is written in source code as `module-info.java`, and then the compiler generates `module-info.class`. When the JAR is placed on the module path, the JVM reads the descriptor to resolve the module and enforce JPMS rules. Java class contents and resources are still packaged in the JAR as usual.

## 1. Structure of a Modular JAR

A simple modular JAR can have the following structure:

~~~text
com.acme.geometry.jar
├── META-INF/
│   └── MANIFEST.MF
├── module-info.class
└── com/
    └── acme/
        └── geometry/
            └── api/
                └── Point.class
~~~

The components serve different roles:

- `module-info.class` is the binary descriptor of the module. It sits at the root directory of the JAR, not inside an application package.
- Package directories contain the bytecode of Java classes, such as `com/acme/geometry/api/Point.class`.
- `META-INF/MANIFEST.MF` contains JAR metadata such as manifest version, main class, or other attributes. The manifest does not replace the module descriptor.
- Resources such as configuration files, images, or data can be packaged along with the JAR.

A modular JAR typically represents a single named module. The module name is declared inside the descriptor; it does not have to match the JAR filename. For example, the file `geometry-library-2.1.jar` can still declare the module `com.acme.geometry`.

## 2. Creating a Module Descriptor from Source Code

Suppose we build the `com.acme.geometry` module with a public API and a class to run the application. Source structure:

~~~text
src/
└── com.acme.geometry/
    ├── module-info.java
    └── com/
        └── acme/
            └── geometry/
                ├── api/
                │   └── Point.java
                └── app/
                    └── Main.java
~~~

The `module-info.java` file:

~~~java
module com.acme.geometry {
    exports com.acme.geometry.api;
}
~~~

The descriptor declares the module name as `com.acme.geometry` and exports the `com.acme.geometry.api` package. Other modules can read this module and access public types in the exported package if they declare an appropriate dependency.

Example API class:

~~~java
package com.acme.geometry.api;

public record Point(int x, int y) {
}
~~~

Example application runner class in an internal package:

~~~java
package com.acme.geometry.app;

import com.acme.geometry.api.Point;

public class Main {
    public static void main(String[] args) {
        Point point = new Point(3, 4);
        System.out.println(point);
    }
}
~~~

The `com.acme.geometry.app` package is not exported. The `Main` class can still be launched directly by module name and main class name, but other modules cannot use this package as a public API.

A module does not need to declare `requires java.base` because the `java.base` module is implicitly required for every named module.

## 3. Common Directives in a Descriptor

A module descriptor does more than name the module. Directives describe dependency relationships, APIs, and service mechanisms.

### requires

`requires` declares that the current module needs to read another module:

~~~java
module com.acme.report {
    requires java.sql;
}
~~~

In this example, the `com.acme.report` module depends on `java.sql`. The required module must be locatable at compile time and when resolving the runtime configuration, except when using the `requires static` variant.

### requires transitive

`requires transitive` propagates readability of the dependent module to modules that depend on the current module:

~~~java
module com.acme.persistence {
    requires transitive java.sql;
    exports com.acme.persistence.api;
}
~~~

If another module declares `requires com.acme.persistence`, that module also reads `java.sql`. This declaration is appropriate when the current module's public API exposes types belonging to the dependent module, requiring API consumers to read that module as well.

Do not use `transitive` for every dependency. Use it only when the dependent module is genuinely part of the API contract passed to consumers.

### requires static

`requires static` indicates a dependency needed at compile time that may be absent at runtime:

~~~java
module com.acme.integration {
    requires static com.acme.optional.annotations;
}
~~~

This directive is often useful for annotation libraries or compile-time tooling. If executing code genuinely needs classes from that module at runtime, the absence of the module can still cause errors when the class is loaded or used.

### exports

`exports` exposes a package to other modules:

~~~java
module com.acme.geometry {
    exports com.acme.geometry.api;
}
~~~

Only public types in the exported package can be accessed by other modules under JPMS rules. `exports` does not turn package-private or private members into public ones.

You can restrict an exported package to specific modules:

~~~java
module com.acme.geometry {
    exports com.acme.geometry.api;
    exports com.acme.geometry.spi to com.acme.plugin;
}
~~~

In this example, `com.acme.geometry.spi` is exported only to `com.acme.plugin`; `com.acme.geometry.api` remains exported without restriction.

### opens

`opens` permits deep reflection into a package at runtime:

~~~java
module com.acme.domain {
    opens com.acme.domain.model to com.acme.json;
}
~~~

This directive is useful when serialization, dependency injection, or persistence frameworks need to access non-public fields, constructors, or members via reflection. `opens` does not replace `exports`: it does not create an API for other modules to import and call types in the package at compile time.

You can open all packages of a module with the declaration:

~~~java
open module com.acme.domain {
    exports com.acme.domain.api;
}
~~~

An open module allows deep reflection into all of its packages. Use this approach only when broad scope is truly required; if only one framework needs access to one package, `opens package.name to module.name` has a clearer scope. Do not declare individual `opens` directives inside an `open module`.

### uses and provides

JPMS supports the service provider mechanism. A service-consuming module declares `uses`:

~~~java
module com.acme.app {
    requires com.acme.geometry.spi;
    uses com.acme.geometry.spi.ShapeProvider;
}
~~~

A module supplying an implementation declares `provides ... with ...`:

~~~java
module com.acme.geometry.provider {
    requires com.acme.geometry.spi;

    provides com.acme.geometry.spi.ShapeProvider
        with com.acme.geometry.provider.DefaultShapeProvider;
}
~~~

The application can discover implementations via `ServiceLoader`. The provider type must satisfy service provider rules; the implementation class does not necessarily have to be exported like a regular API.

## 4. Compiling and Packaging into a Modular JAR

With the source structure above, use JDK 21 to compile the module:

~~~bash
javac --module-source-path src -d out -m com.acme.geometry
~~~

Meaning of the options:

- `--module-source-path src` specifies the root directory containing module source directories named after modules.
- `-d out` places compilation outputs into the `out` directory.
- `-m com.acme.geometry` requests compiling the module with the corresponding name.

After compilation, the output directory looks like:

~~~text
out/
└── com.acme.geometry/
    ├── module-info.class
    └── com/
        └── acme/
            └── geometry/
                ├── api/
                │   └── Point.class
                └── app/
                    └── Main.class
~~~

Use the `jar` tool to package the entire contents of the compiled module:

~~~bash
jar --create --file com.acme.geometry.jar -C out/com.acme.geometry .
~~~

The `-C` option switches `jar`'s working directory to the module's output directory before adding contents. As a result, `module-info.class` is placed at the root of the JAR file along with the packages, matching the structure of a modular JAR.

If `module-info.class` is omitted during packaging, the JAR file no longer has the intended explicit descriptor. When placed on the module path, a JAR without a descriptor may be treated as an automatic module; that behavior differs from an explicit named module.

## 5. Inspecting the Descriptor Inside a JAR

After packaging, use `jar --describe-module`:

~~~bash
jar --describe-module --file com.acme.geometry.jar
~~~

The output shows the module name and the properties recognized by the tool, for example:

~~~text
com.acme.geometry jar:file:///.../com.acme.geometry.jar!/module-info.class
exports com.acme.geometry.api
requires java.base mandated
~~~

These lines confirm:

- The module name is `com.acme.geometry`.
- The descriptor is read from `module-info.class` inside the JAR.
- The `com.acme.geometry.api` package is exported.
- The module has an implicit dependency on `java.base`.

You can list the JAR contents to verify the descriptor file and packaged classes:

~~~bash
jar --list --file com.acme.geometry.jar
~~~

In the output, you should see `module-info.class` at the JAR root and classes in their proper package paths. If the descriptor does not appear or the module name is wrong, revisit the compilation/packaging steps to verify the source structure and directories added to the JAR.

## 6. Running a Modular JAR on the Module Path

Place the JAR file on the module path and specify the module along with the main class:

~~~bash
java --module-path com.acme.geometry.jar \
     -m com.acme.geometry/com.acme.geometry.app.Main
~~~

The part before the `/` in the `-m` argument is the module name; the part after is the fully qualified name of the main class. The JVM reads the descriptor, resolves the module, and launches the specified class.

If the module requires other modules, those dependencies must also be present on the module path and declared in the descriptor with `requires`. For example, when there are multiple JARs in a `mods` directory:

~~~bash
java --module-path mods \
     -m com.acme.app/com.acme.app.Main
~~~

There is no need to place a modular JAR on the classpath for the JVM to recognize the module descriptor. If the same JAR is placed on the classpath using `-cp`, the JVM loads its classes into the unnamed module and ignores the JPMS descriptor.

## 7. How Do Module Descriptor and Manifest Differ?

`module-info.class` and `META-INF/MANIFEST.MF` are both JAR metadata, yet they serve different mechanisms.

| Component | Role |
|---|---|
| `module-info.class` | Declares module name, dependencies, exported/opened packages, and services |
| `Main-Class` in manifest | Specifies the main class for launching an executable JAR with `java -jar` |
| `Class-Path` in manifest | Declares related JARs/classpath entries when running via the manifest mechanism |
| `Automatic-Module-Name` in manifest | Sets a stable name for an automatic module when the JAR lacks an explicit descriptor |

When a JAR has a valid `module-info.class`, the descriptor is the source of the module declaration. The `Automatic-Module-Name` attribute does not replace or override the module name in the descriptor.

A legacy library without `module-info.class` can declare `Automatic-Module-Name` so the automatic module name does not depend on how the JVM derives it from the filename. However, that JAR becomes an automatic module only when placed on the module path. When placed on the classpath, its classes still belong to the unnamed module.

## 8. Common Errors When Creating a Modular JAR

| Symptom | Possible Cause | How to Check |
|---|---|---|
| JVM does not recognize the expected module name | JAR is missing `module-info.class` or the descriptor is not at the JAR root | Run `jar --list --file ...` and `jar --describe-module --file ...` |
| `FindException: Module ... not found` | Dependent module is missing from the module path or wrong module name | Check `requires` directives and the runtime path |
| `IllegalAccessError` or package access error | Needed package is not exported or consuming module does not read source module | Check `exports` and `requires` |
| `InaccessibleObjectException` | Framework needs deep reflection into an unopened package | Check `opens` or `open module` |
| Package does not exist when compiling descriptor | Package name in `exports`/`opens` does not match actual package | Check source structure and package declarations |
| Module runs on classpath but fails on module path | Code relies on cross-package access or undeclared dependencies | Check module descriptor, exported APIs, and module graph |

In particular, do not confuse being able to run a JAR on the classpath with the JAR being properly modularized. The classpath ignores the descriptor and therefore does not fully check the module boundaries the application will encounter on the module path.

## 9. Checklist for Verifying a Modular JAR

Before publishing or integrating a JAR into a JPMS application, confirm:

- [ ] The source code has exactly one `module-info.java` for the module being packaged.
- [ ] The module name in the descriptor is stable and matches the dependencies declared in consuming modules.
- [ ] The compilation process produces `module-info.class`.
- [ ] The JAR file has `module-info.class` at its root directory.
- [ ] `jar --describe-module --file ...` shows the correct module name and directives.
- [ ] Packages meant to be public are exported with `exports` at the right scope.
- [ ] Packages needing deep reflection are opened with scoped `opens`.
- [ ] Required dependencies are declared with `requires` and present on the module path.
- [ ] `uses`/`provides` directives are accurate if the module uses ServiceLoader.
- [ ] The application has been test-run using `--module-path` and `-m`.

## 10. Key Takeaways

The module descriptor is the JPMS contract packaged in `module-info.class` at the root of a modular JAR. It tells the JVM what the module's name is, which modules it needs to read, which packages it exposes, which packages it opens for reflection, and how it provides or consumes services. The basic workflow is to write `module-info.java`, compile it alongside source code, package the descriptor into the JAR, inspect it with `jar --describe-module`, and then run the JAR via the module path.

When inspecting a JAR file, check both its deployment location and its actual contents: the descriptor matters only when the JAR is used via the module path mechanism. Placing a modular JAR on the classpath still causes its classes to run in the unnamed module and bypasses the encapsulation rules declared by the descriptor.