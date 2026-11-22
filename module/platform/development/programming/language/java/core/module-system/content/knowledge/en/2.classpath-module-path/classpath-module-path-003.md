# Placing JARs on the Classpath, Module Path, and Consequences

In Java, classes and JARs can be supplied to a program via the **classpath** or the **module path**. Both mechanisms help the JVM find the code to run, but they create different organization and access control models. Choosing the wrong location can cause a module not to be found, a dependency to be unreadable, or JPMS encapsulation boundaries not to be enforced as expected.

This lesson focuses on how to place JARs, how to compile and run applications, and the direct consequences for the module graph, package accessibility, and legacy application migration.

## 1. What Is the Classpath Used For?

The classpath is Java's traditional class search path. It can contain directories of compiled classes or JAR files. When running an application, use **-cp** or **--class-path**:

~~~bash
java -cp "out:libs/legacy.jar" com.example.app.Main
~~~

On Windows, the separator between classpath entries is a semicolon (**;**); on Linux and macOS, the separator is a colon (**:**). Double quotes can be used to group multiple entries into a single argument when the shell requires it.

Example of compiling a classpath application:

~~~bash
javac -cp libs/legacy.jar -d out src/com/example/app/Main.java
java -cp "out:libs/legacy.jar" com.example.app.Main
~~~

Key characteristics:

- The JVM searches for classes in the listed directories and JARs.
- Dependencies do not need to be declared using **requires**.
- Packages do not have JPMS export boundaries; classes loaded from the classpath belong to the unnamed module of the corresponding class loader.
- If multiple locations contain a class with the same name, search order and class loaders can affect which class gets loaded.
- Any **module-info.class** inside a JAR on the classpath is not used to build the module graph.

The classpath fits traditional Java applications, non-modularized libraries, and systems that need to preserve legacy execution modes. However, it does not create an explicit dependency graph and does not provide package encapsulation per named module.

## 2. How Does the Module Path Work?

The module path is where the JVM and compiler locate JPMS modules. Use **-p** or **--module-path**:

~~~bash
java --module-path mods --module com.example.app/com.example.app.Main
~~~

The module path can contain:

- Modular JARs containing **module-info.class**.
- Exploded module directories containing **module-info.class** at the root.
- JARs without a descriptor; when placed on the module path, this type of JAR can be treated as an automatic module.

For modular JARs, Java reads the module descriptor to learn the module name, **requires** dependencies, **exports** or **opens** packages, and service declarations. The module resolver uses that information to build the module graph before running the application.

A named module needs to declare direct dependencies in **module-info.java**:

~~~java
module com.example.app {
    requires java.sql;
    requires com.example.logging;
}
~~~

If **com.example.logging** is not on the module path or cannot be resolved by the requested name, compilation or launch can fail. This is an important difference from the classpath: a named module's dependencies are verified via the module graph, rather than merely checking whether a JAR appears in a classpath list.

## 3. The Same JAR Can Be Handled Differently

The module kind is determined by both the JAR's contents and where it is placed.

| JAR contents | Placed on classpath | Placed on module path |
|---|---|---|
| Has module-info.class | Loaded as part of the unnamed module; descriptor does not participate in resolution | Recognized as a named module according to the descriptor |
| Lacks module-info.class | Loaded as part of the unnamed module | Recognized as an automatic module |

For example, a **logging.jar** library with `module-info.class`:

~~~bash
# Put the JAR on the classpath
java -cp "app.jar:logging.jar" com.example.app.Main

# Put the JAR on the module path
java --module-path "app.jar:logging.jar" --module com.example.app/com.example.app.Main
~~~

The two commands are not equivalent. In the first command, the JVM does not apply the JPMS directives in **logging.jar**'s descriptor. In the second command, the JAR is processed as a named module; the application must declare and satisfy the corresponding module relationships.

Similarly, an older JAR without a descriptor can still run on the module path as an automatic module. That helps integrate legacy libraries gradually, though it does not yet establish an explicitly designed `exports`/`opens` contract like a complete named module.

## 4. Consequences for Dependencies and Module Readability

On the classpath, an application usually only needs to put the required JARs in **-cp**. On the module path, a named module needs a read edge to the module containing the API it uses. This edge is typically declared with **requires**.

For example:

~~~java
module com.example.app {
    requires com.example.payment;
}
~~~

If **com.example.payment** is on the module path but the application lacks **requires**, the module graph does not have the required read relationship. Having the JAR exist on disk does not automatically make it usable by every named module.

Access toward the classpath also has its own rules. Classes on the classpath belong to the unnamed module, and a named module does not automatically read the unnamed module. In some transition scenarios, a temporary read edge can be added:

~~~bash
java --module-path mods --class-path libs/legacy-helper.jar --add-reads com.example.app=ALL-UNNAMED --module com.example.app/com.example.app.Main
~~~

The **--add-reads** option in the example above allows **com.example.app** to read the unnamed module. It is useful when a library must remain on the classpath during migration, though it reduces the explicitness of the module graph. Whenever possible, move dependencies onto the module path and establish their module kinds stably.

Module readability must also be distinguished from package accessibility:

- **requires** creates a read relationship between modules.
- **exports** exposes a package so other modules can access its **public** types.
- **opens** allows deep reflection into a package at runtime according to the declared scope.

Having **requires** without the package being exported means the calling module still cannot use APIs in that package. Conversely, exporting a package does not automatically create a **requires** dependency for the consuming module.

## 5. Consequences for Encapsulation and Reflection

The classpath does not enforce named module encapsulation boundaries. When a JAR is placed on the module path and becomes a named module, only exported packages serve as normal accessible APIs from other modules.

For example:

~~~java
module com.example.domain {
    exports com.example.domain.api;
}
~~~

Another module can use **public** types in **com.example.domain.api** after declaring **requires com.example.domain**. The **com.example.domain.internal** package is not exported, so it does not become a public API across module boundaries.

Frameworks using reflection may need to access private fields or constructors. **exports** does not grant such deep access. The module owning the package can open it to the framework module:

~~~java
module com.example.domain {
    exports com.example.domain.api;
    opens com.example.domain.model to com.example.mapper;
}
~~~

During transition, **--add-exports** and **--add-opens** can grant additional runtime access for specific situations. For example:

~~~bash
java --add-opens com.example.domain/com.example.domain.model=com.example.mapper ...
~~~

These options should be scoped precisely to the target package and module. If an application runs on the classpath but hits **InaccessibleObjectException** after moving to the module path, check reflection needs and **opens** directives before opening up the entire module.

## 6. Compiling and Running a Modular Application

Suppose the application source has the structure:

~~~text
src/
└── com.example.app/
    ├── module-info.java
    └── com/example/app/Main.java

libs/
└── com.example.logging.jar
~~~

The module descriptor declares the dependency:

~~~java
module com.example.app {
    requires com.example.logging;
}
~~~

Compile the module:

~~~bash
javac --module-path libs --module-source-path src -d out -m com.example.app
~~~

Run the application:

~~~bash
java --module-path "out:libs" --module com.example.app/com.example.app.Main
~~~

Here:

- **--module-source-path** indicates the location of the module sources.
- **--module-path** helps **javac** and the JVM locate modular dependencies.
- **-d out** places compilation results into the output directory.
- **-m** selects the module to compile or run; in the run command, the part after **/** is the main class name.

On Windows, replace **:** in path lists with **;**. When a module has multiple dependencies, all required modules must be locatable on the module path at both compile time and runtime.

## 7. Combining Classpath and Module Path

Java allows a single process to use both mechanisms. This is useful when migrating large systems, where some libraries already have module descriptors while others are still kept on the classpath.

For example:

~~~bash
java --module-path mods --class-path "config:libs/old-driver.jar" --module com.example.app/com.example.app.Main
~~~

Identify clearly which module uses which library. If a named module needs to read classes on the classpath, **--add-reads** may be needed as shown earlier. If an older library needs to access an internal package of a named module, additional export/open configuration may arise; handle it specifically for the actual module and package.

Some points to keep in mind when combining them:

- Do not assume a JAR on the classpath automatically becomes a module just because the process is launched with **--module**.
- Do not assume a named module automatically reads every library on the classpath.
- Keep dependencies that have module descriptors on the module path so JPMS applies their descriptors.
- Avoid having the same library or different-version copies appear in multiple places, as class loaders and module resolution can produce unpredictable behavior.
- Check the actual module name of a JAR before writing **requires**; Maven/Gradle artifact names can differ from module names.

## 8. How to Inspect a JAR's Location and Module

To see how Java recognizes a JAR, use:

~~~bash
jar --describe-module --file libs/example.jar
~~~

The output shows the module name and directives if the JAR is a modular JAR; for a JAR without a descriptor, the tool can display the automatic module name derived or declared in the manifest.

To observe modules available in the runtime:

~~~bash
java --list-modules
~~~

When diagnosing, check in order:

1. Is the JAR or class directory actually passed to the launch command?
2. Is it on the classpath or the module path?
3. If on the module path, what is the actual module name?
4. Has the named module using the dependency declared **requires**?
5. Has the API package been **exports**-ed?
6. If a framework uses reflection, has the required package been **opens**-ed to the proper scope?

These steps help pinpoint whether an error belongs to the class search path, module resolution, read relationships, or package access permissions.

## 9. Common Errors

**ClassNotFoundException** or **NoClassDefFoundError**

The JAR or class directory may not be on the process's classpath/module path, or the runtime path differs from the path used during compilation. Check the actual launch command and dependencies, not just IDE settings.

**Module ... not found**

The module declared in **requires** cannot be found or resolved. Check **--module-path**, the module name in the descriptor/manifest, and required transitive dependencies.

**package ... is not visible** or package access errors

Check both the **requires** relationship and the **exports** directive of the module owning the package. These two conditions address two different issues.

**Application fails with reflection errors after moving to the module path**

Check the error message to identify the target package and module. Add a narrowly scoped **opens** if the application truly needs deep reflection; avoid opening the entire module when only one package needs access.

**Library on the classpath is not visible to a named module**

A named module does not automatically read the unnamed module. You can temporarily use **--add-reads ...=ALL-UNNAMED** as a transitional measure, or move the dependency onto the module path and declare the appropriate module.

**Application runs in the IDE but fails from the command line**

The IDE may configure a different classpath, module path, VM options, or working directory than the standalone command. Compare the actual launch configurations, especially **-cp**, **--module-path**, **--module**, and **--add-*** options.

## 10. Roadmap for Migrating from Classpath to Module Path

You do not need to migrate the entire application at once. You can proceed step by step:

1. Inventory the JARs and class directories the application uses, including runtime dependencies and compile-only dependencies.
2. Inspect each JAR with **jar --describe-module** to see whether it already has a descriptor.
3. Choose an application module or library with clear package boundaries to create **module-info.java**.
4. Move the converted module along with appropriate dependencies onto the module path; keep unready libraries on the classpath if needed.
5. Declare **requires** and **exports** only the packages that form the public API.
6. Handle reflection needs with **opens** targeting the exact package and target module.
7. Re-run both compilation and runtime using the actual module path configuration.
8. Once a dependency has been modularized, remove temporary **--add-reads**, **--add-exports**, or **--add-opens** options if no longer needed.

During this process, keep module names stable and avoid having two versions of the same library appear across different paths simultaneously. For libraries without a descriptor that must remain on the module path long-term, prefer artifacts with a stable **Automatic-Module-Name** or versions that already provide a module descriptor.

## 11. Takeaways

- **-cp** / **--class-path** places directories and JARs on the traditional class search path.
- **-p** / **--module-path** places modules in the search space for Java to resolve the module graph.
- A modular JAR on the classpath is treated as part of the unnamed module; its descriptor is not used.
- A JAR with a descriptor on the module path becomes a named module; a JAR without a descriptor on the module path can become an automatic module.
- Named modules need **requires** to read other modules; API packages need **exports**; deep reflection typically needs **opens**.
- Classpath and module path can be combined in one process, but read edges and access permissions must be controlled explicitly.
- During migration, inspect paths at both compile time and runtime because the two configurations can differ.