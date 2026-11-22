# Classpath libraries when an application is already modular

A Java application that already uses the Java Platform Module System (JPMS) may still need legacy libraries that do not yet have a module-info.java file. These libraries can remain on the classpath while the main application is compiled and launched as a named module on the module path.

This is a step-by-step migration approach: the application keeps its module descriptor and module graph, while non-modularized libraries are loaded into an unnamed module. The point to handle is the readability relationship between the named module and the unnamed module. By default, a named module does not read unnamed modules, so the application typically needs the **--add-reads** option at compile time and runtime.

## 1. Model combining module path and classpath

Suppose an application has the structure:

~~~text
application/
├── src/
│   └── com.example.app/
│       ├── module-info.java
│       └── com/example/app/Main.java
├── mods/
│   └── com.example.api.jar
└── libs/
    ├── legacy-client.jar
    └── legacy-codec.jar
~~~

Where:

- **com.example.app** is an explicit named module with module-info.java.
- **com.example.api.jar** is a modular JAR on the module path.
- **legacy-client.jar** and **legacy-codec.jar** are libraries without module descriptors, placed on the classpath.

When the application runs, the module system resolves named modules on the module path. JARs on the classpath are loaded into the unnamed module of the application class loader. Classpath JARs do not automatically become separate named modules just because the main application has been modularized.

Overview model:

~~~text
                  JVM
                   |
        +----------+-----------+
        |                      |
    Module path             Classpath
        |                      |
        v                      v
  Named modules           Unnamed module
        |                      |
  com.example.app        legacy-client.jar
  com.example.api        legacy-codec.jar
        |
        |  --add-reads
        +---------------------> Unnamed module
~~~

Named modules and unnamed modules can coexist within a single process. An appropriate readability relationship must be configured so code in the named module can reference classes from classpath libraries.

## 2. Unnamed modules and module readability rules

Each class loader has one unnamed module. For a typical application, classes and JARs on the classpath are placed in the unnamed module of the application class loader.

An unnamed module has two important characteristics:

- It reads all named modules.
- All of its packages are exported and open.

The reverse is not automatically true: a named module does not read unnamed modules by default. Therefore, even if a JAR is present on the classpath and the class loader can locate its bytecode, code in a named module may still encounter compilation or access errors due to a missing readability relationship.

You cannot write a directive like the following in module-info.java:

~~~java
module com.example.app {
    requires ALL-UNNAMED;
}
~~~

**ALL-UNNAMED** is a special target name for command-line options of the Java compiler and launcher. It is not a valid module name to declare in requires. To add a readability relationship from a named module to unnamed modules, use **--add-reads**.

## 3. Declaring dependencies of a modular application

Suppose a classpath library provides the class:

~~~java
// legacy-client.jar
package com.legacy.client;

public final class LegacyClient {
    public String fetch() {
        return "data from legacy service";
    }
}
~~~

The modular application uses that class:

~~~java
// src/com.example.app/com/example/app/Main.java
package com.example.app;

import com.legacy.client.LegacyClient;

public class Main {
    public static void main(String[] args) {
        LegacyClient client = new LegacyClient();
        System.out.println(client.fetch());
    }
}
~~~

The application's descriptor can declare dependencies on other named modules:

~~~java
module com.example.app {
    requires com.example.api;
}
~~~

Do not add requires for the legacy library on the classpath because that library has no module name of its own in this configuration. Instead, the compiler and JVM need to be granted a readability relationship to the unnamed module using the option **--add-reads com.example.app=ALL-UNNAMED**.

## 4. Compilation: classpath for libraries, module path for modules

When compiling a modular application, distinguish the two search paths:

- **--module-path** contains the named modules that the compiler needs to resolve.
- **--class-path** contains legacy libraries and classes not belonging to named modules.

Example on Linux or macOS:

~~~bash
javac --module-source-path src --module-path mods --class-path "libs/*" --add-reads com.example.app=ALL-UNNAMED -d out -m com.example.app
~~~

Explanation:

- **--module-source-path src** tells the compiler where module sources are located.
- **--module-path mods** tells the compiler where to find named modules, such as **com.example.api**.
- **--class-path "libs/*"** puts the legacy JARs on the classpath during compilation.
- **--add-reads com.example.app=ALL-UNNAMED** allows the application module to read the unnamed module to reference classes of classpath libraries.
- **-d out** specifies the output directory.
- **-m com.example.app** selects the module to compile.

On Windows, the separator for multiple entries in the classpath is a semicolon (**;**); on Linux and macOS, it is a colon (**:**). The wildcard **libs/*** adds JARs located directly in the libs directory to the classpath; it does not search subdirectories recursively.

If **--add-reads** is omitted, the compiler may report that the package from the legacy library is not visible or that the module does not read that package. When encountering this error, verify whether the library is actually on the classpath or the module path before modifying the descriptor.

## 5. Running: pass the classpath and readability relationship again

Options used at compile time do not automatically become the runtime configuration. When running, you must supply the classpath and readability relationship again to the JVM.

Linux or macOS:

~~~bash
java --module-path "mods:out" --class-path "libs/*" --add-reads com.example.app=ALL-UNNAMED -m com.example.app/com.example.app.Main
~~~

Windows PowerShell:

~~~powershell
java --module-path "mods;out" --class-path "libs/*" --add-reads com.example.app=ALL-UNNAMED -m com.example.app/com.example.app.Main
~~~

Meaning of the components:

- **--module-path** contains the compiled application module and named dependencies.
- **--class-path** contains the legacy libraries needed at runtime.
- **--add-reads** adds a readability relationship from the named module to the unnamed module.
- **-m module/class** launches the main class belonging to the named module.

The runtime classpath must also contain any transitive dependencies that the legacy library needs during execution. A JAR present at compile time but missing at runtime can still cause **NoClassDefFoundError**.

Do not rely solely on the terminal or IDE classpath. Run scripts, containers, and deployment configurations must pass the same set of libraries and required module options.

## 6. What does ALL-UNNAMED mean?

**ALL-UNNAMED** represents all unnamed modules, not a module with a fixed name. Several Java module options use it to apply a relationship or access permission for modules without names.

For example:

~~~bash
--add-reads com.example.app=ALL-UNNAMED
~~~

This means the named module **com.example.app** is allowed to read unnamed modules.

This option can be used at compile time and runtime. If added only at runtime, the compiler can still reject source code referencing classpath libraries. If added only at compile time, the application can compile successfully yet fail at runtime because the runtime module graph still lacks the readability relationship.

Do not confuse the following options:

| Option | Purpose |
| --- | --- |
| --add-reads | Adds a readability relationship between the source module and target module |
| --add-exports | Allows the target module to access a package of the source module |
| --add-opens | Allows deep reflection into a package of the source module |

When a named module needs to call public APIs from a classpath library, **--add-reads** is usually needed. If a classpath library needs to access a package of a named module, exporting or opening in the reverse direction may need to be considered.

## 7. When a classpath library needs to access a package of a modular application

Another case is when a legacy library on the classpath uses reflection or calls an API belonging to the application's named module.

Suppose the application module has a package:

~~~java
module com.example.app {
    exports com.example.app.api;
}
~~~

An unnamed module can read a named module, but packages of the named module are only exported according to its directives and module configuration. If a classpath library needs to access a specific package, **--add-exports** can be used to grant API access to all unnamed modules:

~~~bash
--add-exports com.example.app/com.example.app.internal=ALL-UNNAMED
~~~

If a framework on the classpath needs deep reflection into private members of a package:

~~~bash
--add-opens com.example.app/com.example.app.model=ALL-UNNAMED
~~~

These two options serve different purposes:

- **--add-exports** allows access to public types in the package.
- **--add-opens** allows deep reflection into the package.

Only add permissions when a specific library requires them. Do not open all packages of the application to ALL-UNNAMED because doing so reduces the encapsulation benefits that JPMS provides.

## 8. Keep the library on the classpath or convert it to an automatic module?

A legacy JAR without module-info.class can be handled in two ways when the application is modular.

**Approach A: Keep the JAR on the classpath**

The JAR belongs to the unnamed module. The application needs to add a readability relationship with ALL-UNNAMED if a named module references classes in the library. This approach is suitable when wanting to preserve legacy execution behavior during the transition period.

**Approach B: Place the JAR on the module path**

If a JAR lacks module-info.class but is placed on the module path, Java can treat it as an automatic module. The module name can be taken from the **Automatic-Module-Name** manifest attribute or derived from the JAR filename.

Then, the application declares requires using the automatic module name:

~~~java
module com.example.app {
    requires com.legacy.client;
}
~~~

The application does not need to use **--add-reads ...=ALL-UNNAMED** for that dependency because it is already recognized as a named automatic module.

An automatic module normally exports its packages and can read other named modules. This helps legacy libraries participate in the module graph, but does not establish strict encapsulation boundaries like an explicit named module.

| Criterion | Classpath / unnamed module | Automatic module |
| --- | --- | --- |
| Location | Classpath | Module path |
| Module name | No explicit name | Name from manifest or JAR filename |
| requires in app | Cannot require directly | Can require by automatic module name |
| Readability from app | Usually needs add-reads to ALL-UNNAMED | Uses dependency in the module graph |
| Encapsulation | Unnamed module packages are exported and open | Packages are exported according to automatic module behavior |
| Goal | Compatibility and incremental migration | Intermediate step to modularize dependencies |

If the library can be formally modularized, an explicit module with module-info.java provides clearer results and better control than an automatic module.

## 9. Classpath libraries and transitive dependencies

The classpath has no module descriptor to describe requires relationships. Therefore, the application or build tool must ensure all necessary JARs are present on the runtime classpath.

For example:

~~~text
libs/
├── legacy-client.jar
├── legacy-codec.jar
└── legacy-logging.jar
~~~

If **legacy-client.jar** needs **legacy-codec.jar**, adding only the client JAR to the classpath may suffice to compile part of the code but not to run it. Add the necessary runtime dependencies:

~~~bash
--class-path "libs/*"
~~~

The wildcard only expands JARs in a single directory. If dependencies are placed in **libs/codec/**, that directory must be added as a separate classpath entry.

You should also avoid putting multiple versions of the same library on the classpath. When JARs contain classes with the same name, the class loader may load an unexpected version depending on search order. Using Maven or Gradle to resolve and lock dependencies helps reduce this error.

## 10. Integration with Maven and Gradle

In real projects, you should not have to manually type a long javac/java command on every run. Configure the build tool to keep the compile classpath, module path, and module options separate.

With Maven, legacy dependencies can be declared as normal dependencies. The compiler plugin configuration can pass **--add-reads** via compiler arguments. Test or application execution configurations must also pass the corresponding options to the forked JVM or Java launcher.

With Gradle, legacy dependencies are usually declared in an appropriate configuration such as **implementation**. If the build uses module path inference or separate module path configuration, verify whether the dependency is actually placed on the classpath or the module path. Compiler arguments can be configured via **options.compilerArgs**, while JVM runtime arguments can be passed via **applicationDefaultJvmArgs**, **JavaExec.jvmArgs**, or the corresponding test configuration.

Things to verify in the build:

- Is the legacy library on the classpath or module path?
- Does the compiler receive **--add-reads**?
- Does the JVM running the application receive the same options?
- Are all transitive dependencies of the library present at runtime?
- Do the test runner and production application resolve modules in the same way?

Do not infer dependency placement solely from the configuration name. Inspect the task command line or the build tool's dependency report to confirm.

## 11. Using ServiceLoader with legacy libraries

Some legacy libraries provide implementations through service configuration files at **META-INF/services/** instead of declaring **provides ... with** in a module descriptor.

When combining services between named modules and the classpath, clearly identify:

- The module containing the service interface.
- The module consuming the service and the **uses** directive.
- Whether the provider library is on the classpath or module path.
- Which class loader is used to locate the provider.

If the provider is on the classpath, it belongs to the unnamed module and usually uses the traditional provider configuration file mechanism. For modular applications, choose the **ServiceLoader** overload and class loader appropriate for the deployment; check whether the provider is found by the class loader the application is using.

When possible, convert the provider into a named module and declare **provides ... with**. That makes service relationships explicit in the module descriptor and module graph.

## 12. Common errors when using classpath libraries in a modular app

**Package is not visible or module does not read dependency**

The named module is referencing a classpath library but lacks a readability relationship. Check the classpath and add **--add-reads module=ALL-UNNAMED** for the compiler and runtime.

**Compiles successfully but runtime reports NoClassDefFoundError**

A library dependency is missing from the runtime classpath or the launch command does not use the same configuration as the compile command. Check all transitive dependencies and deployment scripts.

**ClassNotFoundException when loading by name**

The class loader used to locate the class cannot see the library or the class name is wrong. Check the runtime classpath, working directory, and the class loader passed to the class-loading API.

**Legacy library calls a named module API and is blocked**

The unnamed module reads the named module, but the package of the named module may not be exported to the unnamed module. Check **--add-exports**; if a framework needs deep reflection, consider **--add-opens**.

**Added --add-reads at compile time but running still fails**

Compile-time readability is not automatically carried over to runtime. Pass the **--add-reads** option again in the java command or the build tool's runtime configuration.

**JAR has Automatic-Module-Name but still belongs to the unnamed module**

The Automatic-Module-Name attribute only takes effect when the JAR is placed on the module path to become an automatic module. If the JAR is on the classpath, it still belongs to the unnamed module.

**Duplicate classes or mismatched library versions**

Inspect the dependency tree and classpath order. Remove duplicate versions, lock versions, and verify the actual source of loaded classes when needed.

## 13. Observing classpath and runtime modules

You can print system properties to inspect the launch environment:

~~~java
System.out.println("java.class.path = "
    + System.getProperty("java.class.path"));

System.out.println("jdk.module.path = "
    + System.getProperty("jdk.module.path"));
~~~

You can check the module containing a class:

~~~java
Class<?> type = com.legacy.client.LegacyClient.class;

System.out.println("Module: " + type.getModule());
System.out.println("ClassLoader: " + type.getClassLoader());
System.out.println("Is named: " + type.getModule().isNamed());
~~~

If the class belongs to an unnamed module, **type.getModule().isNamed()** returns false. This is how to confirm the library is actually being loaded from the classpath under the unnamed module model.

To view class loading logs on JDK 9 and later:

~~~bash
java -Xlog:class+load=info --module-path mods --class-path "libs/*" --add-reads com.example.app=ALL-UNNAMED -m com.example.app/com.example.app.Main
~~~

The log helps find which class is loaded and its source, useful when there are multiple copies of a library or differences in classpath between local and production.

## 14. Legacy dependency migration roadmap

You can manage the migration in steps:

1. List all legacy JARs and their transitive dependencies.
2. Identify which libraries must remain on the classpath because they cannot yet be modularized.
3. Add the classpath and **--add-reads** for named modules that actually need to use those libraries.
4. Verify compile-time and runtime separately.
5. If a library needs access to internal packages of the application, grant **--add-exports** or **--add-opens** with the proper scope and clear justification.
6. Once a library is stable, consider moving it to the module path as an automatic module.
7. When able to modify or upgrade the library, add module-info.java to create an explicit named module.
8. Remove add-reads/add-exports/add-opens options that are no longer needed and re-verify the application.

Classpath libraries remain a valid part of Java modularization. Understanding unnamed modules, readability relationships, ALL-UNNAMED, and the difference between the classpath and module path helps modern applications continue using legacy libraries while gradually moving toward a module structure with controlled dependencies and APIs.