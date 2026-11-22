# Main Class in the Module Descriptor or on the Command Line

## Objectives

After this lesson, you can:

- Identify the main class used to launch a named module.
- Distinguish between a main class stored in the module descriptor and a main class passed directly on the command line.
- Use `jar --main-class` to set the entry point for a modular JAR.
- Launch a module with `java -m` or `java --module`.
- Understand how the command line overrides a main class already stored in the module.
- Distinguish the module main class from the `Main-Class` attribute in the manifest when running `java -jar`.

## 1. The Main Class of a Named Module

A Java application needs an entry point so the launcher knows which class to invoke first. With the traditional classpath approach, you usually specify the fully qualified class name:

~~~bash
java -cp out com.example.app.Main
~~~

When an application is organized as a named module, you can launch it by module name. The launcher needs to know which module is the starting module and which main class to invoke.

For example, an application has module name `com.example.app` and main class `com.example.app.Main`:

~~~bash
java --module-path out \
     --module com.example.app/com.example.app.Main
~~~

There are two places that can provide the main class:

1. The module descriptor can store a module main class.
2. The command line can explicitly specify the main class after a `/` in the `module/mainclass` syntax.

If the command line provides only the module name, the launcher uses the main class stored in the module descriptor. If the command line provides both the module name and the main class, the class on the command line is used; it can override the stored main class.

## 2. Module Descriptors Do Not Have a main-class Directive

A typical module descriptor source is written in `module-info.java`:

~~~java
module com.example.app {
    requires java.logging;
    exports com.example.app.api;
}
~~~

Java does not have a `main-class` directive syntax in `module-info.java`. You do not write a line such as `main-class com.example.app.Main;` in the module declaration.

Main class information is stored as a binary attribute named `ModuleMainClass` in the `module-info.class` file. This is metadata in the module descriptor, not a Java source directive.

The `java.lang.module.ModuleDescriptor` API provides the method:

~~~java
Optional<String> mainClass = descriptor.mainClass();
~~~

The `mainClass()` method returns the fully qualified name of the module main class if the descriptor declares one; otherwise, it returns `Optional.empty()`.

In a typical build workflow, you can use the JDK `jar` tool to add this information to a modular JAR with the `--main-class` option.

## 3. Preparing the Module and Main Class

Suppose the project has the following structure:

~~~text
project/
└── src/
    └── com.example.app/
        ├── module-info.java
        └── com/
            └── example/
                └── app/
                    └── Main.java
~~~

Module descriptor:

~~~java
module com.example.app {
}
~~~

Main class:

~~~java
package com.example.app;

import java.util.Arrays;

public class Main {

    public static void main(String[] args) {
        System.out.println("Application started");
        System.out.println("Arguments: " + Arrays.toString(args));
    }
}
~~~

The main class uses the standard entry point method:

~~~java
public static void main(String[] args)
~~~

Compile the module using the module source path:

~~~bash
javac --module-source-path src \
      -d out \
      -m com.example.app
~~~

After compilation, the output looks like:

~~~text
out/
└── com.example.app/
    ├── module-info.class
    └── com/
        └── example/
            └── app/
                └── Main.class
~~~

At this point, `module-info.class` has a module descriptor, but does not yet have a module main class because we have not set that metadata with the packaging tool. You can still run the application by specifying the main class on the command line.

## 4. Specifying the Main Class on the Command Line

Syntax to launch a module:

~~~text
java [options] -m module[/mainclass] [args...]
~~~

Or using the long form:

~~~text
java [options] --module module[/mainclass] [args...]
~~~

Using the example above:

~~~bash
java --module-path out \
     --module com.example.app/com.example.app.Main \
     hello world
~~~

Explanation:

- `--module-path out` points to the location containing the named modules.
- `--module` or `-m` instructs the launcher to run a module.
- `com.example.app` is the module name.
- `com.example.app.Main` is the fully qualified name of the main class.
- `hello world` are two arguments passed into `main(String[] args)`.

You can write this more concisely:

~~~bash
java -p out -m com.example.app/com.example.app.Main hello world
~~~

`-p` is the short form of `--module-path`; `-m` is the short form of `--module`.

This approach is suitable when:

- Running exploded modules in a build directory.
- Wanting to select a different entry point per run.
- The module descriptor does not yet store a module main class.
- Wanting to override the default main class declared by a modular JAR.

## 5. Storing the Main Class in the Module Descriptor with `jar --main-class`

When packaging a module into a modular JAR, use the `--main-class` option of `jar`:

~~~bash
jar --create \
    --file dist/com.example.app.jar \
    --main-class com.example.app.Main \
    -C out/com.example.app .
~~~

The `--main-class` option (short form `-e`) specifies the entry point for an application packaged in a modular JAR. For a modular JAR, `jar` writes the module main class information into the binary module descriptor.

You can update an existing JAR:

~~~bash
jar --update \
    --file dist/com.example.app.jar \
    --main-class com.example.app.Main
~~~

To inspect the descriptor after packaging:

~~~bash
jar --describe-module --file dist/com.example.app.jar
~~~

The output will show information similar to:

~~~text
com.example.app
requires java.base mandated
main-class com.example.app.Main
~~~

The `main-class` line indicates that the module descriptor has stored the entry point.

Now you can run the module without typing the class name:

~~~bash
java --module-path dist \
     --module com.example.app \
     hello world
~~~

The launcher reads the module descriptor, retrieves the module main class, and invokes that class's `main` method.

## 6. The Command Line Can Override the Stored Main Class

Suppose the module descriptor stores `com.example.app.Main`, but the application also has a `com.example.app.AdminMain` class with a valid `main` method.

You can select the second class at launch time:

~~~bash
java --module-path dist \
     --module com.example.app/com.example.app.AdminMain
~~~

In this case, the launcher uses the class specified on the command line instead of the stored module main class.

Behavior table:

| Command | Result |
|---|---|
| `java -p dist -m com.example.app` | Uses the main class in the module descriptor |
| `java -p dist -m com.example.app/com.example.app.Main` | Runs the explicitly specified `Main` |
| `java -p dist -m com.example.app/com.example.app.AdminMain` | Runs `AdminMain`, overriding the default entry point |
| `java -p out -m com.example.app/com.example.app.Main` | Runs the explicit main class, even though the descriptor stores no main class |

If the module descriptor has no main class and the command line also provides only the module name, the launcher has no entry point to invoke and the launch command fails. In that case, specify `module/mainclass` explicitly or package the module with `--main-class`.

## 7. Distinguishing Module Main Class and Manifest `Main-Class`

Two mechanisms are frequently confused:

- `ModuleMainClass` is an attribute in the binary module descriptor `module-info.class`.
- `Main-Class` is a manifest attribute in `META-INF/MANIFEST.MF`, used by the launcher when running `java -jar`.

Comparison:

| Launch Method | Source of Main Class |
|---|---|
| `java -m module` | Module main class in the module descriptor |
| `java -m module/mainclass` | Main class specified on the command line |
| `java -jar app.jar` | `Main-Class` in the JAR manifest |
| `java -cp out package.Main` | Class name specified directly on the command line |

`java -jar` and `java -m` are two different launch modes. When using `-jar`, the launcher obtains the entry point from the manifest. When using `-m`, the launcher obtains the module main class from the descriptor if the command line does not provide a class.

The `jar --main-class` option is a convenient way to package a modular JAR with an entry point. If you need to inspect both pieces of metadata after packaging, you can view the module descriptor with `jar --describe-module` and inspect the manifest with:

~~~bash
jar --extract --file dist/com.example.app.jar META-INF/MANIFEST.MF
~~~

## 8. Inspecting the Main Class with the Java API

If an application or build tool needs to read module metadata, you can use `ModuleDescriptor`:

~~~java
import java.lang.module.ModuleDescriptor;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;

public class InspectModule {

    public static void main(String[] args) {
        ModuleFinder finder =
                ModuleFinder.of(Path.of("dist/com.example.app.jar"));

        ModuleDescriptor descriptor =
                finder.find("com.example.app")
                        .orElseThrow()
                        .descriptor();

        descriptor.mainClass().ifPresentOrElse(
                name -> System.out.println("Main class: " + name),
                () -> System.out.println("No module main class configured")
        );
    }
}
~~~

In this example:

1. `ModuleFinder.of(...)` reads the module from the modular JAR.
2. `find(...)` looks up the module by name.
3. `descriptor()` retrieves the module descriptor.
4. `mainClass()` returns an `Optional<String>`.
5. `ifPresentOrElse(...)` handles whether or not the descriptor has a main class.

This is a way to inspect metadata without extracting `module-info.class` or manually parsing class-file attributes.

## 9. Common Errors

| Symptom | Common Cause | Resolution |
|---|---|---|
| Main class not found when passing only module name | Descriptor has not stored an entry point | Use `-m module/mainclass` or package with `jar --main-class` |
| `Could not find or load main class` | Incorrect fully qualified class name or class is not inside the module | Check package, class name, and module output |
| `Module ... not found` | Module path does not contain the module to run | Check `--module-path` and module name |
| `Main method not found` or invalid method | Main class lacks an entry point accepted by the launcher | Check the `public static void main(String[] args)` signature |
| `java -jar` does not use the expected main class | Manifest is missing or sets the wrong `Main-Class` | Check `META-INF/MANIFEST.MF` |
| `java -m` runs a different class than expected | Command line specified `/mainclass` and overrode the metadata | Recheck the part after the `/` |

Always verify the module name and fully qualified class name. A module name does not necessarily match the package name or the JAR filename.

## 10. Summary

A named module can store its main class in the binary module descriptor via the `ModuleMainClass` attribute. `module-info.java` has no `main-class` directive; for a modular JAR, use `jar --main-class` to write the entry point into the descriptor.

At launch time, `java -m module` uses the main class stored in the descriptor. If the command line explicitly specifies `module/mainclass`, the specified class is run and can override the default value. Meanwhile, `java -jar` uses `Main-Class` in the manifest. Understanding these three places where an entry point is stored/selected helps build and run modular applications consistently.

References:

- [The java Command — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html)
- [The jar Command — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jar.html)
- [ModuleDescriptor — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/module/ModuleDescriptor.html)
- [The Java Virtual Machine Specification: ModuleMainClass](https://docs.oracle.com/javase/specs/jvms/se21/jvms21.pdf)
