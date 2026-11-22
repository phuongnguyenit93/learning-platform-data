# Named Modules on the Module Path

In the Java Platform Module System (JPMS), the **module path** is where the compiler and JVM search for observable modules. A named module only participates in the module graph when Java finds that module on the module path or in the correspondingly configured module sources. The module path therefore plays a crucial role at both compile time and runtime.

When migrating from the traditional classpath to JPMS, it is necessary to understand what module forms the module path contains, how Java resolves dependencies, and how to specify the application module to launch.

## 1. What is the module path?

The module path is a list of locations that Java uses to locate modules. Commonly used options:

- **--module-path**: full name of the option.
- **-p**: short form of **--module-path**.

Example:

~~~bash
java --module-path mods --module com.example.app/com.example.app.Main
~~~

In the example above, the **mods** directory is where the JVM searches for modules. The **--module** (or **-m**) option selects the root module and the main class to run.

The module path differs from the classpath in purpose and resolution behavior:

- The classpath is a path for locating classes and JARs under the traditional model.
- The module path is a path for locating named modules, so Java can read descriptors and build the module graph.
- Named modules must declare dependencies via **requires**.
- Packages published across module boundaries must be appropriately exported via **exports**.
- The module path allows Java to verify certain dependency issues and package boundaries before or during execution.

Placing a JAR onto the module path does not automatically make every class inside it a public API. Java also evaluates the module descriptor and that module's directives.

## 2. What can the module path contain?

The module path can provide the following forms of modules:

**Modular JAR**

This is a JAR with a **module-info.class** file at its root. The descriptor contains the module name, dependencies, and export/open rules. When found on the module path, the JAR is recognized as a named module according to its descriptor.

**Exploded module**

This is a module extracted into a directory. The **module-info.class** file lies at the root of the module directory, alongside the compiled packages. This form commonly appears in the output directory after running javac.

**Automatic module**

This is a JAR without **module-info.class** that is placed on the module path. Java generates a module name for the JAR, prioritizing the **Automatic-Module-Name** manifest attribute if present; otherwise, it derives the name from the file name. Automatic modules help legacy libraries participate in the module graph during migration.

A module path directory typically contains multiple modules:

~~~text
mods/
├── com.example.app/
│   ├── module-info.class
│   └── com/example/app/Main.class
├── com.example.greeting/
│   ├── module-info.class
│   └── com/example/greeting/Message.class
└── com.example.logging.jar
~~~

In the example, the first two directories are exploded modules; the last JAR can be a modular JAR or an automatic module depending on its contents.

## 3. How are named modules found and resolved?

The module path provides the set of observable modules. Java does not simply load every module found on the path. The resolver starts from the root modules, then follows **requires** directives to determine which modules are needed and builds the module graph.

Example application module:

~~~java
module com.example.app {
    requires com.example.greeting;
    requires java.sql;
}
~~~

When launching **com.example.app**, Java needs to find **com.example.greeting** and its required dependencies. The application module also reads the system module **java.sql**.

If a required module cannot be found or cannot be resolved, the application can fail before the main method runs. Therefore, merely having the JAR file on disk is not enough; it must be placed in a location observable by the module path and the module name must match the name in the **requires** directive.

The root module can be selected with:

~~~bash
java --module-path mods --module com.example.app
~~~

If you want to specify the main class explicitly:

~~~bash
java --module-path mods --module com.example.app/com.example.app.Main
~~~

The **--add-modules** option can add root modules to the set of modules to resolve in special cases. It does not replace declaring direct required dependencies in the application's module descriptor.

## 4. Declaring dependencies in module-info.java

A named module describes its dependencies using the **requires** directive:

~~~java
module com.example.app {
    requires com.example.greeting;
    requires java.sql;
}
~~~

Some common forms of requires:

- **requires module.name;**: declares a mandatory dependency.
- **requires transitive module.name;**: declares a dependency and propagates readability to modules that use the current module.
- **requires static module.name;**: a dependency needed at compile time but optional at runtime.

The name in **requires** is the module name, not necessarily the JAR name or the dependency name in Maven/Gradle. For example, an artifact might be named **greeting-library-2.1.jar**, while its declared module name is **com.example.greeting**.

When encountering a module-not-found error, check the name that the JAR actually declares instead of guessing from the file name.

## 5. Example: compiling named modules into an output directory

Suppose there are two module sources:

~~~text
src/
├── com.example.greeting/
│   ├── module-info.java
│   └── com/example/greeting/Message.java
└── com.example.app/
    ├── module-info.java
    └── com/example/app/Main.java
~~~

The library module exports its API package:

~~~java
// src/com.example.greeting/module-info.java
module com.example.greeting {
    exports com.example.greeting;
}
~~~

~~~java
// src/com.example.greeting/com/example/greeting/Message.java
package com.example.greeting;

public class Message {
    public static String text() {
        return "Hello from module path";
    }
}
~~~

The application module declares the dependency:

~~~java
// src/com.example.app/module-info.java
module com.example.app {
    requires com.example.greeting;
}
~~~

~~~java
// src/com.example.app/com/example/app/Main.java
package com.example.app;

import com.example.greeting.Message;

public class Main {
    public static void main(String[] args) {
        System.out.println(Message.text());
    }
}
~~~

Compile both modules:

~~~bash
javac --module-source-path src -d out -m com.example.greeting,com.example.app
~~~

After compilation, the output directory has a structure similar to:

~~~text
out/
├── com.example.greeting/
│   ├── module-info.class
│   └── com/example/greeting/Message.class
└── com.example.app/
    ├── module-info.class
    └── com/example/app/Main.class
~~~

The subdirectories inside **out** are exploded modules. You can use the **out** directory itself as the module path:

~~~bash
java --module-path out --module com.example.app/com.example.app.Main
~~~

Output:

~~~text
Hello from module path
~~~

Here, Java locates the app module and greeting module in **out**, reads their descriptors, resolves the **requires** relationship, and runs the application module's main class.

## 6. Putting a modular JAR onto the module path

After compilation, a module can be packaged into a modular JAR. Example packaging the greeting module:

~~~bash
jar --create --file mods/com.example.greeting.jar -C out/com.example.greeting .
~~~

Then the application module can run with the directory containing the JAR on the module path:

~~~bash
java --module-path mods --module com.example.app/com.example.app.Main
~~~

In this example, **mods** is the directory containing the necessary modular JARs. If the application module is still in exploded module form in **out**, you can combine both locations:

~~~bash
java --module-path "out:mods" --module com.example.app/com.example.app.Main
~~~

On Windows, the separator between path elements is a semicolon (**;**); on Linux and macOS it is a colon (**:**). When writing cross-platform launch scripts, use the build tool's classpath/module path configuration mechanism rather than hard-coding the separator.

## 7. Using the module path at compile time

The **javac** compiler also needs to find modular dependencies. The **--module-path** option can be used together with **--module-source-path**:

~~~bash
javac --module-path libs \
      --module-source-path src \
      -d out \
      -m com.example.app
~~~

In this example:

- **libs** contains the module dependencies required by the application source.
- **src** contains the module source directories.
- **out** receives the compiled output.
- **-m com.example.app** selects the module to compile along with the required sources/dependencies according to the configuration.

If the application module depends on a library on the module path, the application's descriptor must still declare **requires**. Merely adding a JAR to **--module-path** does not automatically create a dependency in source.

Ensure that the compile-time and runtime module path configurations are consistent. An application may compile successfully in an IDE because the IDE configured the dependencies, yet fail when run from the command line if the runtime module path is missing a JAR or module directory.

## 8. The module path and classpath do not replace each other

The classpath and module path can coexist in the same process, but each location follows its own rules.

| Configuration | How Java handles it |
|---|---|
| Modular JAR on the module path | Named module according to the module descriptor |
| JAR without a descriptor on the module path | Automatic module |
| JAR on the classpath | Member of the unnamed module |
| Compiled module directory on the module path | Exploded module |
| Class directory on the classpath | Classes are searched using the classpath mechanism |

For example, a modular application can still use a legacy library on the classpath:

~~~bash
java --module-path mods \
     --class-path libs/legacy-helper.jar \
     --module com.example.app/com.example.app.Main
~~~

A named module does not automatically read the unnamed module. If the application module needs to access classes on the classpath, an additional read edge such as **--add-reads com.example.app=ALL-UNNAMED** may be needed during migration. Consider moving the library onto the module path and using an automatic module if appropriate, instead of maintaining unnecessary extra permissions.

## 9. Module names and conflicts on the module path

The module name in the descriptor is the identifier used in the module graph. When there are multiple modules on the module path, ensure module names are clear and that multiple different versions do not publish the same module name in the configuration.

You can inspect a JAR with:

~~~bash
jar --describe-module --file libs/example.jar
~~~

This command displays the module name and directives of a modular JAR; for a JAR without a descriptor, the tool can display the automatic module name derived or declared in the manifest.

Some common errors:

- **Module not found**: the required module is not on the module path or the name in requires does not match.
- **FindException / ResolutionException**: the module graph cannot be resolved due to missing dependencies or conflicts.
- **Package ... is not visible**: the package is not exported appropriately, even though the module was found.
- **Duplicate module**: multiple sources on the module path publish the same module name, causing a conflict or unintended selection.

Do not solve errors by blindly adding all JARs to the module path. Identify the actual dependencies, module names, and module types of each library.

## 10. Common errors when configuring the module path

**Pointing to the wrong module path directory**

If you specify a directory that does not contain valid modules in the expected layout, Java will not find the modules. Check whether the directory contains modular JARs, exploded modules, or observable modules.

**JAR is present but the module is still not found**

The JAR might be on the classpath instead of the module path, or the module name in **requires** differs from the name published in the descriptor. Use **jar --describe-module** to verify.

**Works in the IDE but fails in the terminal**

The IDE may have configured its own module path. Check the actual command line, especially **--module-path**, **--module**, and runtime dependencies.

**Compiles successfully but runtime is missing a module**

Compile-time and runtime configurations may differ. Ensure all required modules are included on the module path at runtime, not just at compile time.

**Module path contains multiple copies of a module**

Remove redundant versions and maintain a consistent module name in the configuration. Avoid mixing JARs of multiple versions of a library on the same module path.

## 11. Key takeaways

- The module path is where Java searches for observable named modules, exploded modules, and automatic modules.
- Use **--module-path** or **-p** to configure the module path.
- Use **--module** or **-m** to select the root module to run.
- Named modules declare dependencies with **requires**; simply having a JAR on the module path does not create a dependency relationship in source.
- The module path can be used at both compile time with javac and runtime with java.
- The module path and classpath can be combined, but classes on the classpath belong to the unnamed module and named modules do not automatically read it.
- Inspect the module name with **jar --describe-module** when encountering resolution errors.
- Keep the module path consistent across development, testing, and deployment environments.

When configuring a modular application, treat the module path as part of the build and runtime configuration. Placing the right modules in the right locations, declaring dependencies explicitly, and checking the module graph help the application launch reliably outside the IDE.