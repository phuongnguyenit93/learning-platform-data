# Requiring JDK Modules and Runtime Images

## 1. The Role of requires in the Java Module System

In the Java Platform Module System (JPMS), every named module describes its direct dependencies in a **module-info.java** file. The **requires** directive declares that the current module needs to read another module to compile and run.

For example, an application using JDBC and Java Logging can declare:

~~~java
module com.example.app {
    requires java.sql;
    requires java.logging;

    exports com.example.app.api;
}
~~~

Here, module **com.example.app** depends on two JDK modules: **java.sql** and **java.logging**. When compiling or launching the application via the module path, the module system must resolve the requested modules along with their required dependencies.

**requires** establishes a readability relationship between modules. Through this relationship, code in the current module can access types exported by the required module via **exports**, while obeying JPMS encapsulation and access rules.

Distinguish three concepts:

- **requires** declares a module dependency and readability of that module.
- **exports** exposes a package so other modules can access public types in that package.
- **opens** permits deep reflective access to a package, typically for frameworks or libraries needing reflection.

One module can read another without automatically gaining access to every package inside that module. Packages must be exported or opened appropriately for the type of access.

## 2. Declaring Dependencies on JDK Modules

The JDK is organized into many named modules. Some commonly encountered modules:

| Module | Typical functionality |
|---|---|
| **java.base** | Foundational types such as Object, String, collections, basic I/O, and concurrency |
| **java.logging** | Java's standard logging API |
| **java.sql** | JDBC API |
| **java.xml** | XML, DOM, SAX, and related XML APIs |
| **java.net.http** | HTTP Client API |
| **java.desktop** | AWT, Swing, and several desktop APIs |
| **java.naming** | JNDI |
| **java.management** | JMX and JVM management APIs |

You can view the modules available in the JDK in use with:

~~~bash
java --list-modules
~~~

To view the contents and declarations of a module:

~~~bash
java --describe-module java.sql
~~~

The **java.base** module is implicitly read by the module system for every named module. Therefore, you normally do not need to write **requires java.base** in a module descriptor.

For instance, if an application calls JDBC, you can declare **requires java.sql**. If it uses the standard HTTP Client, declare **requires java.net.http**. Declare dependencies based on the APIs your module's code actually uses, rather than adding numerous JDK modules simply because they are present in a full JDK.

One JDK module may depend on other JDK modules. When the system resolves the module graph, required dependencies are pulled into the graph. As a result, the final runtime image may contain more modules than the **requires** lines written directly in the application.

## 3. Three Forms of requires to Distinguish

### Standard requires

This is the most common form:

~~~java
module com.example.report {
    requires java.sql;
}
~~~

Module **java.sql** must be present and resolved both at compile time and when resolving the runtime module graph. Use this form when code needs the dependent module's API during normal execution.

### requires transitive

Use **requires transitive** when the current module exposes a public API containing types from a dependent module, and modules reading your API also need to read that module.

~~~java
module com.example.data.api {
    requires transitive java.sql;

    exports com.example.data.api;
}
~~~

Suppose a public method of **com.example.data.api** returns **java.sql.Connection**. A module consuming this API needs to read **java.sql** to use the type in the method signature. Declaring transitive propagates readability of the dependent module to modules reading the current module.

Do not use transitive for every dependency. If a module only uses a library inside its implementation and does not expose that library's types in its public API, a regular **requires** is usually more appropriate. Overusing transitive declarations increases the dependencies consumers must read.

### requires static

Use **requires static** when a module needs a dependency at compile time, yet that dependency is optional during runtime resolution:

~~~java
module com.example.app {
    requires static com.example.annotations;
}
~~~

A common case is an annotations library needed only during compilation or tooling processing. The required module must still be present on the module path at compile time. At runtime, that module may be absent while the current module still resolves.

However, if the application actually invokes classes or methods from the optional module at runtime, omitting that module from the runtime can cause errors when that execution path runs. **requires static** neither loads the library automatically nor makes runtime API usage safe when the module is absent.

Summary to remember:

| Syntax | Primary meaning |
|---|---|
| **requires M** | Mandatory dependency at compile time and runtime resolution |
| **requires transitive M** | Mandatory dependency, also propagating readability to modules reading the current module |
| **requires static M** | Mandatory at compile time, optional during runtime resolution |

## 4. Choosing the Right Dependencies for Application Modules

Before building a runtime image, identify which modules actually belong to the application graph.

For example, consider an application with the following packages:

~~~text
com.example.app
com.example.app.api
com.example.app.db
com.example.app.internal
~~~

The application uses JDBC to access a database, writes logs, and exports an API without exposing JDBC types in public signatures. Its descriptor can be:

~~~java
module com.example.app {
    requires java.sql;
    requires java.logging;

    exports com.example.app.api;
}
~~~

If the application's public API returns **java.sql.Connection** or accepts it as a parameter, consider **requires transitive java.sql** so modules consuming the API can read that type. If JDBC is only used internally in the implementation, keep a regular **requires java.sql**.

Packages that are not **exports**ed can still be used inside the module. This is how internal implementation is kept encapsulated and the public API surface is minimized.

If a framework needs deep reflection into an internal package, consider **opens** or **opens ... to** targeting the specific framework module. Do not add **opens** merely to resolve a readability error caused by a missing **requires**; the two directives address different aspects.

## 5. From Module Descriptors to the Module Graph

When compiling or launching a named module, JPMS constructs a module graph from the root modules and their declared dependencies. Modules must be found on the module path or among the modules of the runtime in use.

For instance, an application module requires **java.sql**. The **java.sql** module in turn has its own dependencies. The resolver continues following required relationships to build a consistent graph.

You can inspect a JDK module's descriptor to understand those dependencies:

~~~bash
java --describe-module java.sql
~~~

Dependencies brought into the graph by the module system do not mean the application must list all of them in **module-info.java**. Each module should only declare the direct dependencies required by its own code or API.

For service modules, distinguish **uses** and **provides** declarations from **requires**:

~~~java
module com.example.app {
    uses com.example.spi.PaymentProvider;
}
~~~

**uses** declares that the module consumes a service; **provides ... with ...** declares that the module provides an implementation. If you want the runtime image to include providers discovered on the module path, you can use jlink's **--bind-services** option during image creation.

## 6. Preparing Modules to Create a Runtime Image

The **jlink** tool builds a custom runtime image from modules. The image includes the Java runtime and the selected modules along with their required dependencies. Building an image typically makes sense once an application has been organized into named modules.

An illustrative project structure:

~~~text
project/
  src/
    com.example.app/
      module-info.java
      com/example/app/Main.java
      com/example/app/api/
    com.example.data/
      module-info.java
      com/example/data/
  mods/
~~~

Example **module-info.java** for the application:

~~~java
module com.example.app {
    requires java.sql;
    requires java.logging;
}
~~~

Example launcher class:

~~~java
package com.example.app;

public class Main {
    public static void main(String[] args) {
        System.out.println("Application started");
    }
}
~~~

Compile the application module:

~~~bash
javac -d mods --module-source-path src -m com.example.app
~~~

After compilation, the **mods** directory contains the compiled modules. If the application depends on separate library modules, those modules must also be compiled or placed on the module path so jlink can resolve them.

You can verify the compiled modules with:

~~~bash
java --module-path mods --list-modules
~~~

This command shows the modules observable on the module path combined with the current runtime. It helps confirm module names and locations before creating the image.

## 7. Creating a Runtime Image with jlink

A basic command on Linux or macOS:

~~~bash
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.example.app \
  --output runtime-image
~~~

Where:

- **--module-path** specifies where jlink looks for modules. The **$JAVA_HOME/jmods** directory holds JDK modules; **mods** holds compiled application modules.
- **--add-modules** specifies the root modules to include in the image. jlink resolves required dependencies of the root modules.
- **--output** is the resulting runtime image directory.

On Windows, the separator between module path entries is a semicolon. For example, in PowerShell:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.example.app --output runtime-image
~~~

Replace **com.example.app** with the actual module name. If the application depends on other application modules, jlink will resolve them when they are present on the module path and properly declared.

You do not need to list every dependent JDK module manually if the module graph is declared accurately. Still, you can specify multiple root modules as a comma-separated list when the image needs to include additional independent modules:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" \
      --add-modules com.example.app,java.xml \
      --output runtime-image
~~~

Only add **java.xml** if the application or deployment requirements genuinely need that module.

## 8. Creating a Launcher and Optimizing the Runtime Image

You can ask jlink to generate a launcher for a module and main class:

~~~bash
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.example.app \
  --launcher app=com.example.app/com.example.app.Main \
  --strip-debug \
  --no-header-files \
  --no-man-pages \
  --output runtime-image
~~~

After creating the image, the launcher can be invoked with:

~~~bash
./runtime-image/bin/app
~~~

If you do not generate a custom launcher, you can run the module using the Java executable inside the image:

~~~bash
./runtime-image/bin/java -m com.example.app/com.example.app.Main
~~~

Some commonly used options:

- **--strip-debug** removes debug information from the runtime image.
- **--no-header-files** omits native header files.
- **--no-man-pages** omits manual pages.
- **--compress=2** enables resource compression in the image on JDKs supporting this option.
- **--bind-services** binds matching service providers and their dependent modules.
- **--launcher** creates a convenient launch command for the specified module and main class.

Optimization options alter the contents or size of the image. Check the available options with **jlink --help** on the exact JDK version in use. For applications relying on ServiceLoader, check which service providers are included in the image and consider **--bind-services**.

## 9. Verifying the Runtime Image After Creation

Once jlink finishes, do not treat directory creation alone as proof that the application is ready. Run the application using the runtime image itself:

~~~bash
./runtime-image/bin/app
~~~

Or if no launcher was created:

~~~bash
./runtime-image/bin/java -m com.example.app/com.example.app.Main
~~~

You can list the modules included in the image:

~~~bash
./runtime-image/bin/java --list-modules
~~~

At a minimum, verify:

1. The application starts with the Java executable inside the image.
2. Database access, logging, XML, HTTP, or desktop features work properly if the application uses them.
3. Service providers are discovered if the application uses ServiceLoader.
4. Classes loaded via reflection or dynamic configuration work properly.
5. Configuration files, resources, native libraries, and external data are distributed alongside the application.
6. Execution results on the target deployment environment match the environment where the image was built.

A runtime image is built for a specific operating system and architecture. Typically, build and test the image on each target platform using the appropriate JDK.

## 10. When the Application Is Not Yet Modular

If the application still runs on the classpath and does not yet have **module-info.java**, jlink cannot turn arbitrary classpath JARs into named modules simply by passing them to **--add-modules**.

There are two common approaches:

- Migrate the application and suitable libraries to named modules, add module descriptors, and place them on the module path.
- Create a runtime image containing only the necessary JDK modules, then distribute application JARs separately and launch them on the image's classpath.

As an example of the second approach, after creating an image with the required JDK modules, you can run:

~~~bash
runtime-image/bin/java -cp "lib/*:app.jar" com.example.app.Main
~~~

On Windows, the classpath uses a semicolon instead of a colon. This still yields a smaller runtime image, though the application and classpath JARs must still be distributed separately.

If you want jlink to bundle the application module itself into the image, that module needs to be in an appropriate module format on the module path. Automatic modules, commonly used for module path compatibility, are not a substitute input for named modules when building images with jlink; check the module requirements of the JDK in use.

## 11. Common Errors

**Module not found**

The requested module name was not found on the module path. Check the name in **module-info.java**, the location of the **mods** directory, the module path, and the JDK used to run the command.

**Module does not read ...**

The current module has not declared the proper readability relationship. Check **requires** in the descriptor of the module calling the API. If types from the dependent module appear in a public API, consider **requires transitive**.

**Package is not visible**

The module may be read, yet the required package is not exported by its owning module. Check that module's **exports**. If the error comes from deep reflection, check **opens** policies and reflective access configuration.

**jlink fails to resolve the application module**

Verify the module path contains the compiled module, the module descriptor has the right name, and all mandatory dependencies can be resolved. Use **java --describe-module** or **java --module-path ... --list-modules** to help diagnose.

**Application runs on full JDK but fails in the image**

The image may be missing dynamically loaded modules, service providers, resources, native libraries, or runtime components used only under a specific configuration. Inspect actual execution paths, service declarations, and the root modules passed to jlink. You can add needed modules to **--add-modules**, then rebuild and test the image.

## 12. Recommended Practical Workflow

When migrating an application to a minimal runtime image, follow this order:

1. Identify the application modules and required library modules.
2. Write **module-info.java** with the appropriate direct **requires** declarations.
3. Use **requires transitive** only when a public API needs to propagate readability to a dependent module.
4. Use **requires static** for dependencies that are optional at runtime but required at compile time.
5. Inspect the module graph with JDK tools and ensure all modules resolve.
6. Compile application and library modules on the module path.
7. Use **jlink --add-modules** to create the image from the application's root modules.
8. Add a launcher or optimization flags as needed.
9. Run and test real functionality using the runtime image.
10. Build separate images for each deployment platform and record the JDK, build commands, and selected module list.

## 13. Takeaways

- **requires** declares modules that current code needs to read.
- **requires transitive** propagates readability of a dependency to modules consuming the API.
- **requires static** is required at compile time but may be absent during runtime resolution.
- **java.base** is read implicitly by every named module.
- **exports** controls which packages other modules can access; **opens** serves deep reflective access.
- **jlink** creates a runtime image from resolved modules, starting from the modules selected via **--add-modules**.
- Both the module graph and runtime image must be verified by running the application on the generated image.

An accurate module descriptor lets JPMS build a clear dependency graph. jlink uses that graph to pick the modules needed for the runtime image. When tested on the exact deployment environment, the application can run on a smaller Java runtime while retaining all components required by its real functionality.
