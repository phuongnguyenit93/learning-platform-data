# Modular JARs and module-info.class

## Objectives

After this lesson, you can identify a modular JAR, explain the role of `module-info.class`, read basic module declarations, compile and package a module into a JAR, and then inspect and run that JAR on the module path.

## 1. What is a Modular JAR?

JAR (Java ARchive) is a ZIP-based packaging format that typically contains `.class` files, resources, and metadata of a Java application. A JAR can hold an application or a library, but packaging it as a JAR does not automatically turn it into a Java module.

A **modular JAR** is a JAR that contains a compiled module descriptor, i.e., a `module-info.class` file at the root directory of the JAR. The descriptor specifies the module name and the relationships that the Java Platform Module System (JPMS) needs to know: which modules this module depends on, which packages are exported, which packages are opened for reflection, which services the module uses, and which services the module provides.

For example, a JAR with the structure:

~~~text
com.acme.geometry.jar
  META-INF/
    MANIFEST.MF
  module-info.class
  com/
    acme/
      geometry/
        api/
          Point.class
          Shape.class
        internal/
          ShapeFactory.class
~~~

If a valid `module-info.class` is at the root level, this JAR is an explicit module. The module name is declared in the descriptor, such as `com.acme.geometry`; it does not necessarily have to match the JAR file name.

A modular JAR is still a regular JAR file in terms of archive storage format. What makes it an explicit module is the descriptor, not the `.jar` extension or a different binary packaging format.

## 2. module-info.java and module-info.class

When developing a module, developers write the descriptor in source form in a `module-info.java` file. The `javac` compiler compiles this file into `module-info.class` alongside the remaining Java classes of the module.

For example:

~~~java
module com.acme.geometry {
    exports com.acme.geometry.api;
}
~~~

The declaration above means:

- The module name is `com.acme.geometry`.
- The package `com.acme.geometry.api` is exported so that other modules can access public types in that package.
- Other packages in the module are not automatically exported.
- The module has an implicit dependency on `java.base`, because every Java module depends on this foundational module.

`module-info.class` is binary metadata that tools and the runtime read to resolve modules. It is not a normal Java class for applications to instantiate, invoke a constructor on, or import as an API. In the class file, the module descriptor is represented by a special JVM structure dedicated to modules.

Typically, each explicit module has exactly one `module-info.class` at the module root. For a modular JAR, this file appears at the JAR root; for a compiled directory module (exploded module), it appears at the root of the module directory.

## 3. Common Directives in a Module Descriptor

A module descriptor uses directives to describe the API and dependency relationships:

| Directive | Meaning |
|---|---|
| requires module.name; | The module needs to read another module |
| requires transitive module.name; | The module depends on and passes that readability on to modules that depend on it |
| requires static module.name; | A dependency required at compile time but optional at runtime |
| exports package.name; | Allows other modules to access public types in the package |
| exports package.name to other.module; | Exports the package only to the named modules |
| opens package.name; | Allows deep reflective access to the package at runtime |
| opens package.name to other.module; | Opens the package only to the named modules |
| uses service.Type; | Declares that the module uses a service |
| provides service.Type with ProviderType; | Registers a service provider class |

Example descriptor of a library module:

~~~java
module com.acme.report {
    requires java.sql;
    requires transitive com.acme.model;

    exports com.acme.report.api;
    exports com.acme.report.spi to com.acme.report.engine;

    opens com.acme.report.dto to com.fasterxml.jackson.databind;

    uses com.acme.report.spi.Formatter;
    provides com.acme.report.spi.Formatter
        with com.acme.report.internal.HtmlFormatter;
}
~~~

A few points to distinguish:

- `requires` establishes a module readability relationship. It does not automatically export packages of the required module.
- `exports` serves normal access to public types of a package. It is not synonymous with opening the entire package for reflective access.
- `opens` serves deep reflection, such as when a framework needs to access non-public fields or constructors. Opening a package does not mean the package's types become normal public API.
- `requires transitive` is useful when this module's public API exposes types belonging to a dependency module; modules using the API may need to read that dependency.
- `requires static` represents an optional dependency at runtime. If that module is present, readability still applies.
- `uses` and `provides` are declarations for the `ServiceLoader` mechanism; they do not replace `requires` and `exports`.

A module name should be stable, meaningful, and typically use reverse-domain style, for example `com.acme.geometry`. Avoid arbitrarily using a package name or a JAR file name in place of properly defining a module name.

## 4. Structure of a Module Before Packaging

Example of a simple module named `com.acme.hello`:

~~~text
src/
  com.acme.hello/
    module-info.java
    com/
      acme/
        hello/
          api/
            Greeter.java
          app/
            Main.java
~~~

`module-info.java` file:

~~~java
module com.acme.hello {
    exports com.acme.hello.api;
}
~~~

`Greeter.java` file:

~~~java
package com.acme.hello.api;

public class Greeter {
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

`Main.java` file:

~~~java
package com.acme.hello.app;

import com.acme.hello.api.Greeter;

public class Main {
    public static void main(String[] args) {
        Greeter greeter = new Greeter();
        System.out.println(greeter.greet("Java module"));
    }
}
~~~

The package containing `Main` does not need to be exported if no other module needs to access public types in that package. Java can still launch the module's main class by module name and class name.

## 5. Compiling a Module into Class Files

From the project directory containing the `src` directory, run:

~~~bash
javac -d out --module-source-path src -m com.acme.hello
~~~

Meaning of the options:

- `-d out` specifies the output directory for compiled results.
- `--module-source-path src` tells `javac` the source directory structure organized by module.
- `-m com.acme.hello` requests compiling the module with that name.

After compiling, the output structure looks like:

~~~text
out/
  com.acme.hello/
    module-info.class
    com/
      acme/
        hello/
          api/
            Greeter.class
          app/
            Main.class
~~~

Pay attention to the location of `module-info.class`: it sits directly in the root directory of the module, at the same level as the `com` package tree. If the `module-info.java` source file is not compiled or is placed in the wrong location, the output will lack the proper descriptor needed to package into an explicit modular JAR.

For a simple module, you can compile by specifying individual source files and writing the output to a directory. Using `--module-source-path` is more useful when a project has multiple modules following a common directory convention.

## 6. Packaging into a Modular JAR

Create the `mods` directory if it does not exist yet, then package the compiled contents:

~~~bash
mkdir -p mods

jar --create \
    --file mods/com.acme.hello.jar \
    --main-class com.acme.hello.app.Main \
    -C out/com.acme.hello .
~~~

Explanation:

- `--create` creates a new JAR.
- `--file` specifies the output file path and name.
- `--main-class` declares the application's main class; for a modular JAR, `jar` writes the launch class information into the module metadata so the module can be run without specifying the main class on the command line.
- `-C` changes the working directory of `jar` to the compiled module directory, then adds all contents there. Therefore `module-info.class` is placed at the JAR root.

You can omit `--main-class` if the module is only a library and has no entry point. In that case, users can still use the module from another application, but cannot ask Java to automatically choose the module's main class.

The file name is usually chosen close to the module name for easier management, but the actual module name is still determined by `module-info.class`.

## 7. Inspecting the Contents and Descriptor of a JAR

Use `jar --list` to view the entries:

~~~bash
jar --list --file mods/com.acme.hello.jar
~~~

In the output, verify that `module-info.class` sits at the JAR root and was not placed inside an unintended subdirectory.

Use `jar --describe-module` to inspect module information:

~~~bash
jar --describe-module --file mods/com.acme.hello.jar
~~~

The output can show the module name, exported packages, dependencies such as `java.base`, and the main class if declared. Abbreviated example:

~~~text
com.acme.hello jar:file:///.../com.acme.hello.jar!/module-info.class
exports com.acme.hello.api
requires java.base mandated
main-class com.acme.hello.app.Main
~~~

You can inspect the detailed class file structure using `javap`:

~~~bash
javap -v -p --module-path mods --module com.acme.hello module-info
~~~

`javap` displays the attributes in the class file, including the module metadata section. This is a useful way to observe the compiled output at the bytecode level when you need to examine how the descriptor is stored.

## 8. Running a Modular JAR on the Module Path

Use the module path to run the application:

~~~bash
java --module-path mods --module com.acme.hello
~~~

You can write this more concisely using the equivalent short options:

~~~bash
java -p mods -m com.acme.hello
~~~

Because the JAR declared a main class, Java can find the entry point from the module metadata. If you did not declare a main class when packaging, specify the class to run explicitly:

~~~bash
java --module-path mods \
     --module com.acme.hello/com.acme.hello.app.Main
~~~

Expected output:

~~~text
Hello, Java module!
~~~

If the module depends on other modules, the dependency modules must be present on the module path so Java can resolve the module graph. Depending on how the application is packaged, the module path can contain multiple modular JARs or compiled module directories.

## 9. How Do Module Path and Classpath Handle JARs Differently?

The same JAR file can be placed on the classpath or on the module path, but Java treats it differently:

| JAR Location | How Java Treats the JAR |
|---|---|
| Classpath (`-cp` or `-classpath`) | Classes belong to the unnamed module; `module-info.class` inside the JAR is not used for JPMS resolution |
| Module path, with valid `module-info.class` | Explicit named module; module name and relationships come from the descriptor |
| Module path, without `module-info.class` | Can be treated as an automatic module |

This means placing a modular JAR on the classpath does not activate the descriptor's `exports`, `requires`, or `opens` rules. When you want to use JPMS properly, run or compile with the module path.

A module path can contain both explicit modules and automatic modules. However, an automatic module is only a bridge to help legacy JAR libraries participate in the module graph; it does not provide clear encapsulation like an explicit module.

## 10. Distinguishing Modular JARs and Automatic Modules

These are two concepts that are easily confused:

**Explicit modular JAR**

- Has `module-info.class` at the JAR root.
- The module name and directives are explicitly declared in the module descriptor.
- Packages that are not `exports` or `opens` are subject to JPMS encapsulation rules.
- Usually created by compiling `module-info.java` together with the module source code.

**Automatic module**

- A JAR without `module-info.class` at the root.
- When placed on the module path, Java can treat that JAR as a named module.
- If the manifest has the `Automatic-Module-Name` attribute, that attribute provides a stable module name.
- Without this attribute, the module name is derived from the JAR file name and can change when the file name changes.
- Automatic modules have broad compatibility behavior to support legacy libraries, such as exporting all of their packages and reading other modules according to automatic module rules.

For example, the manifest of a legacy JAR library might declare:

~~~text
Manifest-Version: 1.0
Automatic-Module-Name: com.acme.legacy
~~~

This declaration helps keep the automatic module name stable when the JAR is placed on the module path. However, it does not turn the JAR into an explicit modular JAR and does not replace `module-info.class`.

Use `jar --describe-module --file legacy-library.jar` to see how the tool identifies the module. For a JAR without a descriptor, the output will show that it is an automatic module or indicate the derived name.

## 11. Common Packaging Mistakes

| Symptom | Common Cause | How to Check or Fix |
|---|---|---|
| JAR is not recognized as an explicit module | Missing `module-info.class` at the JAR root | Run `jar --list` and check the descriptor location |
| Module not found when running | JAR placed outside the module path or module name mistyped | Check `--module-path` and `jar --describe-module` |
| Module name differs from file name | The name in `module-info.java` is the source of the explicit module name | Use `jar --describe-module` to confirm the real name |
| Package is not accessible from another module | Package is not `exports`ed or the module does not read the module containing the package | Check `exports` and `requires` |
| Framework cannot access fields/constructors via reflection | Package is not opened for the framework | Use `opens` or `opens ... to ...` appropriately |
| Application runs on classpath but fails on module path | Application has not declared dependencies or package access per JPMS | Check the descriptor and module relationships |
| Legacy JAR has a changing automatic module name | Name is derived from the JAR file name | Declare `Automatic-Module-Name` in the manifest or migrate the library to an explicit module |

A common packaging mistake is accidentally adding the parent directory containing the module into the JAR, causing `module-info.class` not to sit at the root. With the `jar` command, choose the right working directory using `-C` and add the contents inside the compiled module directory.

When you have multiple modules, package each module into its own JAR or its own module directory on the module path. Do not merge independent modules into a single JAR in a way that erases module boundaries and each module's descriptor.

## 12. When Should You Create a Modular JAR?

You should create an explicit modular JAR when developing a library or application that needs to:

- Explicitly declare which modules are dependencies.
- Control which packages are exposed as public API.
- Reduce accidental access to internal packages.
- Describe reflection needs using `opens`.
- Declare service consumers/providers using `uses` and `provides`.
- Distribute a module with a stable name and descriptor to other applications.

For legacy libraries that cannot immediately migrate to JPMS, an automatic module can serve as a transitional step. For new modules under your control, declare `module-info.java` and publish an explicit modular JAR so module relationships are described clearly.

## Key Takeaways

A JAR is just a packaging format; a modular JAR is a JAR with `module-info.class` at its root. The `module-info.java` file is compiled by `javac` into a binary descriptor containing the module name and directives such as `requires`, `exports`, `opens`, `uses`, and `provides`. Use `jar --describe-module` to inspect the descriptor, `jar --list` to verify file placement, and `java --module-path` to run the module. A JAR without a descriptor can become an automatic module when placed on the module path, whereas when placed on the classpath, JPMS rules are not applied.