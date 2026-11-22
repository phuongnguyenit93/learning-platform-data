# Running Modules with `java --module-path`

> Scope: Java Platform Module System (JPMS, since Java 9). This lesson guides you through running a named module using the Java launcher with **--module-path** and **--module**.

## Objectives

After this lesson, you can:

- Write the correct **java --module-path ... --module ...** syntax.
- Distinguish between the module path and the class path.
- Run a module from a compiled module directory or from a modular JAR.
- Specify a main class and pass arguments to the program.
- Understand how the launcher resolves the main module along with dependencies declared via **requires**.
- Inspect the module path and troubleshoot common errors when running modular applications.

## 1. Basic Syntax

General syntax:

~~~bash
java [jvm-options] --module-path <module-path> --module <module-name>[/<main-class>] [application-args...]
~~~

You can write it using the short forms:

~~~bash
java -p <module-path> -m <module-name>[/<main-class>] [application-args...]
~~~

Where:

- **java**: Java application launcher.
- **--module-path** or **-p**: specifies where the launcher looks for application and library modules.
- **--module** or **-m**: specifies the main module to launch.
- **module-name**: the module name declared in **module-info.java** or the automatic module name of a JAR.
- **main-class**: the fully qualified name of the class containing the **public static void main(String[] args)** method.
- **application-args**: arguments passed to the **main** method.

Short example:

~~~bash
java --module-path mods \
     --module com.acme.app/com.acme.app.Main
~~~

The command above instructs the launcher to find the **com.acme.app** module on the **mods** module path, then invoke the **com.acme.app.Main** class in that module.

Equivalently, you can write:

~~~bash
java -p mods -m com.acme.app/com.acme.app.Main
~~~

The module name and the main class name are two separate components. The part before the slash is the module name; the part after is the fully qualified class name.

## 2. What Does the Module Path Contain?

The **module path** is where Java looks for observable modules during resolution. It can contain:

- Directories containing exploded modules (modules compiled into a directory tree).
- Modular JARs containing **module-info.class**.
- JARs without a module descriptor that are recognized as automatic modules.
- Directories containing modular JARs so the launcher can locate modules within them.

Example with exploded modules:

~~~text
project/
├── src/
│   ├── com.acme.lib/
│   │   ├── module-info.java
│   │   └── com/acme/lib/Message.java
│   └── com.acme.app/
│       ├── module-info.java
│       └── com/acme/app/Main.java
└── mods/
    ├── com.acme.lib/
    │   ├── module-info.class
    │   └── com/acme/lib/Message.class
    └── com.acme.app/
        ├── module-info.class
        └── com/acme/app/Main.class
~~~

In this structure, **mods** is the module path. Each subdirectory is an exploded module with **module-info.class** at the module root directory.

Example with modular JARs:

~~~text
project/
└── mlib/
    ├── com.acme.lib.jar
    └── com.acme.app.jar
~~~

In this case, **mlib** is the directory containing the module JARs and can be specified with **--module-path mlib**.

You can also list multiple JARs directly:

~~~bash
java --module-path "mlib/com.acme.app.jar:mlib/com.acme.lib.jar" \
     --module com.acme.app/com.acme.app.Main
~~~

The separator between elements in the module path depends on the operating system:

| Operating System | Separator |
|---|---|
| Windows | Semicolon **;** |
| Linux, macOS | Colon **:** |

Example on Windows:

~~~powershell
java --module-path "mlib/com.acme.app.jar;mlib/com.acme.lib.jar" -m com.acme.app/com.acme.app.Main
~~~

If the module path has only one directory, no separator is needed.

## 3. Example: Running Exploded Modules

Suppose an application has two modules: **com.acme.lib** provides a simple API and **com.acme.app** calls that API.

### Library Module

File **src/com.acme.lib/module-info.java**:

~~~java
module com.acme.lib {
    exports com.acme.lib;
}
~~~

File **src/com.acme.lib/com/acme/lib/Message.java**:

~~~java
package com.acme.lib;

public class Message {
    public static String greet(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

The module descriptor exports the **com.acme.lib** package so other modules can use the public API in that package.

### Application Module

File **src/com.acme.app/module-info.java**:

~~~java
module com.acme.app {
    requires com.acme.lib;
}
~~~

File **src/com.acme.app/com/acme/app/Main.java**:

~~~java
package com.acme.app;

import com.acme.lib.Message;

public class Main {
    public static void main(String[] args) {
        String name = args.length == 0 ? "Java" : args[0];
        System.out.println(Message.greet(name));
    }
}
~~~

The **requires com.acme.lib** directive declares the app's dependency on the library module.

### Compiling

From the root **project** directory, run:

~~~bash
javac -d mods --module-source-path src \
      -m com.acme.lib,com.acme.app
~~~

Explanation:

- **--module-source-path src**: indicates the directory tree containing the module sources.
- **-d mods**: writes the compiled files into the **mods** directory.
- **-m com.acme.lib,com.acme.app**: instructs `javac` to compile the two specified modules.

After compiling, **mods** contains the corresponding exploded modules.

### Running the Main Module

~~~bash
java --module-path mods \
     --module com.acme.app/com.acme.app.Main
~~~

Output:

~~~text
Hello, Java!
~~~

Passing arguments to the program:

~~~bash
java --module-path mods \
     --module com.acme.app/com.acme.app.Main Lan
~~~

Output:

~~~text
Hello, Lan!
~~~

Arguments after the **module/main-class** part are passed into the **args** parameter of the **main** method. They are not module names or launcher options.

## 4. Running a Module from a Modular JAR

In real-world projects, modules are typically packaged into JARs for distribution.

Assuming they have been compiled as in the previous section and the **mods** directory contains:

- **mods/com.acme.lib/module-info.class**
- **mods/com.acme.app/module-info.class**

Create the directory for the JARs:

~~~bash
mkdir mlib
~~~

Package the library module:

~~~bash
jar --create --file mlib/com.acme.lib.jar \
    -C mods/com.acme.lib .
~~~

Package the application module:

~~~bash
jar --create --file mlib/com.acme.app.jar \
    -C mods/com.acme.app .
~~~

Run the application with the JAR directory as the module path:

~~~bash
java --module-path mlib \
     --module com.acme.app/com.acme.app.Main
~~~

The launcher finds the main module in **mlib**, reads the app's descriptor, sees **requires com.acme.lib**, and resolves the dependency from the module path.

You can specify each JAR file directly:

~~~bash
java --module-path "mlib/com.acme.app.jar:mlib/com.acme.lib.jar" \
     -m com.acme.app/com.acme.app.Main
~~~

If the module path contains both the application JAR and the library JAR, the file order does not change the meaning of the **requires** directive. What matters is that the required module can be found and the module names match.

## 5. Running a Module Without Specifying the Main Class in the Command

The typical syntax looks like this:

~~~bash
java --module-path mods -m com.acme.app/com.acme.app.Main
~~~

Here the main class is explicitly specified after the slash. In some cases, you can specify only the module name:

~~~bash
java --module-path mlib -m com.acme.app
~~~

The second approach requires the module to have its main class recorded in the module descriptor (the **ModuleMainClass** attribute). You can set this attribute when creating a modular JAR using the **--main-class** option of the **jar** tool:

~~~bash
jar --create \
    --file mlib/com.acme.app.jar \
    --main-class com.acme.app.Main \
    -C mods/com.acme.app .
~~~

Then run:

~~~bash
java --module-path mlib --module com.acme.app
~~~

If the module does not have a main class recorded in its descriptor and the command omits **/main-class**, the launcher does not know which class to run. In that case, add the main class to the command or repackage the JAR with **--main-class**.

## 6. How Does the Launcher Resolve Modules?

When running:

~~~bash
java --module-path mods \
     --module com.acme.app/com.acme.app.Main
~~~

the launcher performs the main steps:

1. Reads the module path to locate the module named **com.acme.app**.
2. Identifies the main module to launch.
3. Reads the module descriptor of the main module.
4. Resolves the dependencies declared by the module using **requires**, along with any required transitive dependencies.
5. Checks whether a valid module graph can be constructed.
6. Loads the main class from the main module and invokes the **main** method.

Example descriptor:

~~~java
module com.acme.app {
    requires com.acme.lib;
}
~~~

If **com.acme.lib** is not on the module path or cannot be resolved, the application will fail to run. Specifying the main module does not automatically make every JAR in the project a dependency; module relationships must be declared and resolved appropriately.

Key points to remember:

- **requires** specifies a module dependency.
- **exports** specifies public packages accessible to other modules.
- The module path specifies where to find modules.
- **--module** specifies the root module to run.
- A JAR filename is not necessarily the module name. For an explicit module, the name is in the descriptor; for an automatic module, the name can come from the manifest or be derived from the filename.

If you need to add a module to the root module set beyond the main module, the launcher provides the **--add-modules** option. Use it only when the application genuinely needs to resolve that module even though it is not pulled in through the normal **requires** chain.

## 7. Distinguishing --module-path from --class-path

The two options serve two different class-loading mechanisms.

| Option | Meaning | How It Is Referenced |
|---|---|---|
| **--module-path** or **-p** | Where to find named modules and automatic modules | Module name, **requires**, **-m** |
| **--class-path** or **-cp** | Where to find classes and JARs under the class path mechanism | Class name; classes belong to the unnamed module |

Example of running a class path application:

~~~bash
java -cp libs/*:classes com.acme.app.Main
~~~

Example of running a modular application:

~~~bash
java --module-path mods -m com.acme.app/com.acme.app.Main
~~~

Do not confuse these two commands. When using **-m**, the launcher looks up a resolved module in the module graph. When passing a class name after the class path, the launcher runs the class using the class path mechanism.

The **-jar** option is also a separate launch mode:

~~~bash
java -jar app.jar
~~~

This command runs the JAR under the **-jar** mechanism based on the manifest's **Main-Class**; it is not equivalent to placing a modular JAR on the module path and running with **-m**. When the goal is to run an application as a named module, use **--module-path** and **--module**.

## 8. Useful Options When Running Modules

| Option | Purpose |
|---|---|
| **--module-path**, **-p** | Specifies the module path |
| **--module**, **-m** | Specifies the main module and optionally the main class |
| **--add-modules** | Adds modules to the set of root modules to resolve |
| **--show-module-resolution** | Prints information about the module resolution process |
| **--list-modules** | Lists the modules observable by the launcher |
| **--describe-module** | Displays the descriptor information of a module |
| **--class-path**, **-cp** | Specifies the class path for classes/JARs under the class path mechanism |
| **-Dname=value** | Sets a system property |
| **-Xmx<size>** | Sets the maximum heap size for the JVM |

Example to inspect the resolution process:

~~~bash
java --show-module-resolution \
     --module-path mods \
     --module com.acme.app/com.acme.app.Main
~~~

Example to list modules:

~~~bash
java --module-path mods --list-modules
~~~

Example to describe a module:

~~~bash
java --module-path mods --describe-module com.acme.app
~~~

You can use **jar --describe-module --file <jar-file>** to inspect the descriptor of a specific JAR.

## 9. Common Errors and Troubleshooting

| Symptom | Common Cause | Resolution |
|---|---|---|
| **Module ... not found** | The main module is not on the module path or the module name is wrong | Check the path and the name in **module-info.class**; use **jar --describe-module** |
| **FindException: Module ... not found, required by ...** | A dependency in **requires** cannot be found | Add the required module JAR/directory to the module path; verify the module name |
| **Error occurred during initialization of boot layer** | The module graph cannot be resolved or has a conflict | Run with **--show-module-resolution**; check for duplicate module names, split packages, and dependencies |
| **Main method not found** or main class not found | Wrong class name, wrong module, or the module does not declare a main class when omitting **/main-class** | Specify the full **module/main-class** or package the main class with **jar --main-class** |
| **ClassNotFoundException** | The class is not in a resolved module/JAR or the path is incorrect | Check the JAR structure, package, and module path |
| **NoClassDefFoundError** | A class needed at runtime cannot be loaded, often due to a missing dependency or differences between runtime and compile-time environments | Check runtime dependencies and the module graph |
| Works on class path but fails on module path | The descriptor is missing required dependencies/exports or the application relies on class path behavior | Check **requires**, **exports**, packages, and the module graph |

Debugging sequence:

1. Check whether the command uses the right **--module-path** and **--module**.
2. Verify that the module path points to the right directory or JAR.
3. Use **jar --describe-module** to confirm the module name of each JAR.
4. Check whether the main module is on the module path or is an observable system module.
5. Verify that every dependency in **requires** can be resolved.
6. Re-run with **--show-module-resolution** to see which modules the launcher selects and resolves.
7. Confirm that the main class has the right package name and resides inside the main module.

## 10. Takeaways

- **--module-path** (**-p**) is where modules are located; **--module** (**-m**) selects the main module to run.
- The common full syntax is **-m module.name/package.MainClass**.
- You can run either exploded modules or modular JARs.
- The main module and its dependent modules must resolve into a valid module graph.
- **requires** declares dependencies; **exports** exposes API packages.
- Application arguments are placed after the module/main class.
- If the main class is omitted from the command, the module must have its main class recorded in its descriptor.
- Running with **-m** differs from running a JAR with **-jar** or running a class with **-cp**.

## References

- [Java Launcher — Java SE 21 Tool Specification](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html)
- [The javac Command — Java SE 21 Tool Specification](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html)
- [The jar Command — Java SE 21 Tool Specification](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jar.html)
- [JEP 261 — Module System](https://openjdk.org/jeps/261)
