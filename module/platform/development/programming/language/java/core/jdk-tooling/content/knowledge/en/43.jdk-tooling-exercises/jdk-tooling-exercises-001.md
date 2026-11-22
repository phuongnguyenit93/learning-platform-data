# Compiling Java Applications with javac

## 1. What is javac used for?

`javac` is the compiler included with the JDK. It reads Java source code in `.java` files, checks syntax, data types, access permissions, and references between classes, and then generates bytecode in `.class` files for the JVM to run.

A basic Java workflow has the following steps:

1. Write source code and organize it by package.
2. Use `javac` to compile source into class files.
3. Place required resources and dependencies into the output area or classpath.
4. Use `java` to run the main class or package with `jar`.
5. Test the artifact on the target runtime.

`javac` only compiles source code. It does not automatically package external libraries, copy resources, or create installers. Those tasks belong to classpath preparation, JAR packaging, or other build/distribution tools.

## 2. Checking the JDK before compiling

Check the compiler and runtime:

~~~bash
java --version
javac --version
jar --version
~~~

The three commands can accidentally point to different JDKs if multiple versions are installed on the machine. On Windows PowerShell:

~~~powershell
Get-Command java -All | Select-Object Source
Get-Command javac -All | Select-Object Source
where.exe java
where.exe javac
$env:JAVA_HOME
~~~

On Linux/macOS:

~~~bash
command -v java
command -v javac
echo "$JAVA_HOME"
~~~

Confirm that `java` and `javac` come from the intended JDK. For an application that needs to run on Java 17, you can use JDK 17 or a newer JDK with `--release 17` to produce Java 17-compatible class files.

## 3. Source and package structure

The package name in the source must match the directory containing the file. For example:

~~~text
javac-demo/
  src/
    main/
      java/
        com/
          example/
            app/
              Main.java
              Formatter.java
      resources/
        app.properties
  build/
    classes/
  dist/
~~~

If the source declares:

~~~java
package com.example.app;
~~~

then the file should be located under the `com/example/app/` directory. This path helps the compiler and other tools locate the class by its fully qualified name `com.example.app.Main`.

Common conventions:

- Package names are lowercase, with parts separated by dots.
- The public class name matches the file name, for example `Main` is in `Main.java`.
- Source files are placed separately from output class files.
- Resources are placed in a separate area and copied into the classpath output during the build.

It is possible to compile a Java file without a package declaration, but a well-structured application should use packages to avoid name collisions and manage access control.

## 4. Minimal Java program

Create the file `src/HelloWorld.java`:

~~~java
public class HelloWorld {
    public static void main(String[] args) {
        System.out.println("Hello, Java!");
    }
}
~~~

Compile:

~~~bash
javac HelloWorld.java
~~~

The compiler creates `HelloWorld.class` in the same directory because no output directory was specified. Run it by class name, without adding the `.class` extension:

~~~bash
java HelloWorld
~~~

Exact stdout:

~~~text
Hello, Java!
~~~

In a real application, you should use `-d` so that class files are not mixed with source files.

## 5. Compiling multiple source files at once

`javac` can compile multiple source files in a single invocation. The files are processed as a group so the compiler can resolve references between declarations within the group without needing to guess the compilation order.

Example `Formatter.java`:

~~~java
package com.example.app;

public final class Formatter {
    public static String greet(String name) {
        return "Hello, " + name;
    }
}
~~~

File `Main.java`:

~~~java
package com.example.app;

public final class Main {
    public static void main(String[] args) {
        String name = args.length == 0 ? "Java" : args[0];
        System.out.println(Formatter.greet(name));
    }
}
~~~

From the project root directory, compile both files:

~~~bash
javac --release 17 -d build/classes \
  src/main/java/com/example/app/Main.java \
  src/main/java/com/example/app/Formatter.java
~~~

Run:

~~~bash
java -cp build/classes com.example.app.Main Linh
~~~

Stdout:

~~~text
Hello, Linh
~~~

There is no need to compile `Formatter.java` before `Main.java` if both files are passed in the same command. If only `Main.java` is passed, specify a source path or ensure the compiler can find the dependent sources/classes.

## 6. Choosing the class file directory with -d

Use `-d` to specify the destination directory:

~~~bash
javac --release 17 -d build/classes src/main/java/com/example/app/Main.java
~~~

If the package is `com.example.app`, the output is created with the following structure:

~~~text
build/classes/
  com/
    example/
      app/
        Main.class
~~~

`javac` creates the destination directory and any required package directories if they do not exist. Separating the output helps:

- Keep source files from getting mixed with build files.
- Easily copy resources into the classpath.
- Easily create a JAR from the exact compiled files.
- Clean old output before rebuilding.
- Easily inspect artifacts and configure CI.

If `-d` is omitted, class files are placed next to the source files. This is suitable for small experiments, but should not be used as the build process for a multi-package application.

## 7. Selecting a compatible Java release with --release

If you use a newer JDK to build but the product needs to run on an older Java version, set `--release`.

For example, compiling with JDK 24 while targeting Java 17:

~~~bash
javac --release 17 -d build/classes src/main/java/com/example/app/Main.java
~~~

`--release 17` simultaneously controls:

- The Java language rules accepted in release 17.
- The major version of the output class files compatible with Java 17.
- The set of Java/JDK APIs that the source is allowed to reference according to release 17.

Do not just use `-source 17 -target 17` and assume API compatibility. Those two options control syntax and class file format; when compiling on a newer JDK, the source can still reference APIs that only appeared in the newer JDK. `--release` restricts the APIs to the target release as well.

Do not combine `--release` with `-source` or `-target` in the same command. Inspect the class file after compiling:

~~~bash
javap -verbose -classpath build/classes com.example.app.Main
~~~

For Java 17, the important line is:

~~~text
major version: 61
~~~

Choose the lowest release that the application actually needs to support. `--release` cannot make external dependencies compatible with older Java; every JAR on the runtime classpath must also support that baseline.

## 8. Specifying encoding for source files

You should explicitly specify UTF-8 so builds produce consistent results across Windows, Linux, macOS, and CI:

~~~bash
javac --release 17 -encoding UTF-8 -d build/classes src/main/java/com/example/app/Main.java
~~~

If `-encoding` is omitted, the compiler uses the environment's default character encoding. Source code containing Vietnamese or non-ASCII characters may compile differently across machines if the default encodings differ.

Note: `-encoding` controls how source files are read. It does not determine the encoding of all resource files or runtime data. Resources must be read using the encoding specified by the application.

## 9. Adding external libraries to the classpath

If the source uses classes from a JAR that is not part of the JDK, the compiler needs to know the library's location via the classpath.

Suppose there is a dependency:

~~~text
lib/
  greeting-api.jar
~~~

Compile the application:

~~~bash
javac --release 17 \
  -cp lib/greeting-api.jar \
  -d build/app-classes \
  src/main/java/com/example/app/Main.java
~~~

`-cp` is the short form of `--class-path`. Multiple directories/JARs can be passed in a single classpath. The separator character depends on the operating system:

| Operating System | Classpath example |
|---|---|
| Windows | `build/app-classes;lib/greeting-api.jar` |
| Linux/macOS | `build/app-classes:lib/greeting-api.jar` |

Enclose the classpath in quotes when it contains spaces or when the shell might interpret special characters. You should specify `-cp` explicitly instead of relying on the `CLASSPATH` environment variable.

The compile-time classpath and runtime classpath are two separate configurations. After compiling, the JVM still needs to find the dependencies:

Windows:

~~~powershell
java -cp "build/app-classes;lib/greeting-api.jar" com.example.app.Main
~~~

Linux/macOS:

~~~bash
java -cp "build/app-classes:lib/greeting-api.jar" com.example.app.Main
~~~

If a dependency JAR is forgotten at runtime, the program may compile successfully but fail with `NoClassDefFoundError` or `ClassNotFoundException`.

## 10. Distinguishing classpath and module path

The two paths serve two different ways of organizing code:

- **Classpath (`-cp` or `--class-path`):** locates classes and JARs by package. This is the common approach for traditional classpath applications.
- **Module path (`-p` or `--module-path`):** locates modules that have a module descriptor or automatic modules. Modules declare dependencies and exported packages using `module-info.java`.

If a dependency is a modular JAR, it can be placed on the module path. If the application does not yet use the Java Platform Module System, continuing to use the classpath is valid.

Do not arbitrarily mix classpath and module path to mask dependency errors. Determine whether the application is using unnamed modules or named modules and configure it according to the appropriate model.

## 11. Using source path for unlisted dependent sources

If only `Main.java` is passed on the command line but the source references another class that has not been compiled yet, `--source-path` tells the compiler where to look for dependent source files.

For example:

~~~bash
javac --release 17 \
  --source-path src/main/java \
  -d build/classes \
  src/main/java/com/example/app/Main.java
~~~

The compiler can find `Formatter.java` at:

~~~text
src/main/java/com/example/app/Formatter.java
~~~

The source path must be organized according to the package hierarchy. If you want to be certain of the exact files being compiled, list all source files on the command line or use an argument file.

`--source-path` is used for additional sources in package-oriented compilation. When compiling multiple modules, use `--module-source-path`.

## 12. Copying resources into the output directory

`javac` only produces class files and outputs generated by annotation processors. It does not automatically copy files such as `.properties`, `.xml`, images, or templates.

Example resource:

~~~text
src/main/resources/app.properties
~~~

Contents:

~~~properties
banner=READY javac
~~~

After compiling, copy resources into the classpath output.

PowerShell:

~~~powershell
Copy-Item src/main/resources/* build/classes/ -Recurse
~~~

Linux/macOS:

~~~bash
cp -R src/main/resources/. build/classes/
~~~

In Java, read the resource using the classloader:

~~~java
try (InputStream in = Main.class.getResourceAsStream("/app.properties")) {
    if (in == null) {
        throw new IllegalStateException("Missing app.properties");
    }
    Properties properties = new Properties();
    properties.load(in);
}
~~~

The resource path is resolved from the root of the classpath/JAR. When packaging a JAR, include resources in the same output structure so the runtime can find them.

## 13. Packaging class files into an executable JAR

After compiling and copying resources, you can package them into a JAR:

~~~bash
jar --create \
  --file dist/hello-app.jar \
  --main-class com.example.app.Main \
  -C build/classes .
~~~

Create the `dist` directory before running the command if it does not already exist. `-C build/classes .` tells `jar` to change into the `build/classes` directory and add its contents to the archive.

Run the JAR:

~~~bash
java -jar dist/hello-app.jar Linh
~~~

Stdout:

~~~text
READY javac: Hello, Linh
~~~

You can inspect the JAR contents:

~~~bash
jar --list --file dist/hello-app.jar
~~~

JAR is an archive format; it does not bundle the JDK. Users still need a compatible Java runtime to run it.

## 14. JARs with external dependencies

An executable JAR containing only application classes and resources does not automatically bundle all external dependencies.

When running with `java -jar`, external classpath settings on the command line are ignored. There are two common approaches:

1. Use `java -cp` with the application JAR and its dependencies, then invoke the fully qualified main class.
2. Declare `Class-Path` in the manifest so the JVM locates dependency JARs relative to the main JAR.

Classpath example:

Windows:

~~~powershell
java -cp "dist/app.jar;lib/greeting-api.jar" com.example.app.Main
~~~

Linux/macOS:

~~~bash
java -cp "dist/app.jar:lib/greeting-api.jar" com.example.app.Main
~~~

If using manifest `Class-Path`, the paths must match the deployment directory structure. Inspect the archive after packaging and test running from a different working directory to catch environment-dependent paths.

## 15. Compiling a modular application

A module has a `module-info.java` file. Example with two modules:

~~~text
src/
  com.example.greeter/
    module-info.java
    com/example/greeter/Greeter.java
  com.example.app/
    module-info.java
    com/example/app/Main.java
~~~

Library module:

~~~java
module com.example.greeter {
    exports com.example.greeter;
}
~~~

Library class:

~~~java
package com.example.greeter;

public final class Greeter {
    public static String message() {
        return "READY modular javac";
    }
}
~~~

Application module:

~~~java
module com.example.app {
    requires com.example.greeter;
}
~~~

Main class:

~~~java
package com.example.app;

import com.example.greeter.Greeter;

public final class Main {
    public static void main(String[] args) {
        System.out.println(Greeter.message());
    }
}
~~~

Compile both modules:

~~~bash
javac --release 17 \
  --module-source-path src \
  -d mods \
  -m com.example.greeter,com.example.app
~~~

Run the application module:

~~~bash
java --module-path mods -m com.example.app/com.example.app.Main
~~~

Stdout:

~~~text
READY modular javac
~~~

`--module-source-path` specifies the source location of the modules being compiled. `--module-path` specifies the location of compiled modules or dependency modules. The two options serve different purposes.

## 16. Annotation processing

`javac` supports annotation processors to analyze annotations and optionally generate additional source files or resources during compilation. Libraries such as code generators can use this mechanism.

Common options:

| Option | Purpose |
|---|---|
| `--processor-path` | Location of JARs containing annotation processors |
| `--processor-module-path` | Module path for processors |
| `-processor` | Specify the name of the processor to run |
| `-Akey=value` | Pass custom configuration to the processor |
| `-s` | Directory for source files generated by the processor |
| `-proc:none` | Disable annotation processing |
| `-proc:only` | Run annotation processing only |

Example of explicit processor configuration:

~~~bash
javac --release 17 \
  --processor-path tools/codegen.jar \
  --processor com.example.codegen.BuilderProcessor \
  -s build/generated-sources \
  -d build/classes \
  src/main/java/com/example/Order.java
~~~

An annotation processor is code that runs inside the build process and can access the resources granted to that process. Only use processors from trusted sources, pin their versions, and keep processor dependencies under build control. Do not arbitrarily enable or disable annotation processing if the application relies on auto-generated classes.

## 17. Common javac options

| Option | Meaning |
|---|---|
| `--release 17` | Select Java 17 source rules, APIs, and class file target |
| `-d build/classes` | Output directory for class files |
| `-cp` / `--class-path` | Dependencies on the classpath |
| `-p` / `--module-path` | Dependencies on the module path |
| `--source-path` | Location of dependent source files |
| `--module-source-path` | Source location for multiple modules |
| `-encoding UTF-8` | Source file encoding |
| `-g` | Generate debugging information |
| `-parameters` | Store method/constructor parameter names for reflection |
| `-Xlint:all` | Enable lint warnings |
| `-Werror` | Stop compilation if warnings occur |
| `-deprecation` | Show details of deprecated APIs |
| `-verbose` | Display compiler activity |

Strict compilation example:

~~~bash
javac --release 17 \
  -encoding UTF-8 \
  -Xlint:all \
  -Werror \
  -d build/classes \
  src/main/java/com/example/app/Main.java
~~~

`-Werror` is useful in CI when a team wants to treat warnings as errors. Before enabling it, resolve existing warnings or explicitly define which categories are allowed. Do not use `-nowarn` to hide quality issues.

## 18. Using argument files for multi-source projects

The command line can become too long when a project has many files. Use an argument file to store options and source files, then invoke `javac @filename`.

Example `compile.args`:

~~~text
--release
17
-encoding
UTF-8
-d
build/classes
src/main/java/com/example/app/Main.java
src/main/java/com/example/app/Formatter.java
~~~

Run:

~~~bash
javac @compile.args
~~~

You can place each option and value on its own line. If a path contains spaces, enclose the entire path in double quotes. Relative paths inside an argument file are resolved from the current working directory, not the directory containing the argument file.

Argument files help manage long compile commands, but they must be updated when adding or removing source files. Wildcards are not expanded inside argument files.

## 19. Inspecting class files and compilation results

After compiling, use `javap` to inspect the class:

~~~bash
javap -classpath build/classes com.example.app.Main
javap -verbose -classpath build/classes com.example.app.Main
~~~

`javap` can display methods, fields, the constant pool, and the class file version. This is how you confirm the compiler produced the expected target class file.

Use `jar --list --file` to inspect archive contents. Run `java -cp` or `java -jar` on the actual output to verify that the runtime finds the classes and resources.

A `javac` command returning exit code 0 only indicates that the compilation step succeeded. It does not prove that the program runs correctly, that all dependencies are present, that resources are packaged, or that the production runtime is compatible.

## 20. Distinguishing javac from java's source-file mode

The JDK can directly run a single source file:

~~~bash
java HelloWorld.java
~~~

This is the source-file mode of the `java` launcher. The launcher compiles the source to run it, which is useful for small scripts, demos, or quick experiments.

If you need to control compiler options, save class files, create JARs, run annotation processors, or integrate compilation into a pipeline, use `javac` explicitly. Source-file mode does not replace a full application build workflow.

## 21. Repeated compilation and avoiding stale class files

In real projects, old class files can remain behind after renaming packages, deleting classes, or changing source structure. If you only overwrite part of the output, the JAR may accidentally include classes that are no longer produced by the current source.

Clean build workflow:

Linux/macOS:

~~~bash
rm -rf build/classes
mkdir -p build/classes
javac --release 17 -encoding UTF-8 -d build/classes @compile.args
~~~

PowerShell:

~~~powershell
Remove-Item build/classes -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force build/classes | Out-Null
javac @compile.args
~~~

Ensure `compile.args` points to the right output directory. After a clean compile, copy resources and build the JAR from the fresh output.

For large projects, Maven/Gradle manage incremental compilation, dependencies, and lifecycles more conveniently. `javac` is still the underlying compiler; understanding how to invoke it directly helps you read logs and troubleshoot build failures.

## 22. Common errors when using javac

### javac is not recognized or command not found

The JDK is not installed on the machine or `PATH` does not point to the JDK's `bin` directory. Check `javac --version`, `JAVA_HOME`, and the executable path.

### package ... does not exist

The compiler cannot find the dependency package. Check `-cp`, `--module-path`, package names, JAR locations, and whether the repository/dependencies have been downloaded.

### cannot find symbol

This can be caused by a misspelled class/method/field name, a missing import, an unpassed dependent source file, or an incorrect source path/classpath. Read the first line of the diagnostic to find the symbol and error location.

### class X is public, should be declared in a file named X.java

The file name does not match the public top-level class name. Rename the file or the class according to Java rules.

### invalid source release

The current JDK compiler does not support the requested release, or the option syntax is incorrect. Check `javac --version` and use an appropriate JDK.

### bad class file or class file has wrong version

A dependency was compiled with a newer Java version than the target compiler/runtime. Upgrade the JDK or choose a dependency compatible with the baseline; do not just change `--release` on the current source.

### Compiles successfully but fails at runtime with NoClassDefFoundError

The dependency may have been on the compile classpath but missing from the runtime classpath. Reconfigure the `java` command, manifest `Class-Path`, or how dependencies are packaged.

### Resource not found

The resource was not copied into the output/JAR or the resource path is wrong. Check `jar --list --file` and use `getResourceAsStream` with the correct path from the classpath root.

### java -jar cannot find external libraries

When using `-jar`, external command-line classpaths are ignored. Put dependencies in manifest `Class-Path` or run the main class with `java -cp`.

### NoSuchMethodError after successful compilation

The class file may have loaded, but the runtime dependency does not have the method referenced by the compiled code. Check the JAR versions used at compile time and runtime; align the dependencies rather than changing `javac` syntax.

## 23. End-to-end application compilation workflow

Use the source structure:

~~~text
src/main/java/com/example/app/Main.java
src/main/java/com/example/app/Formatter.java
src/main/resources/app.properties
~~~

Example `Formatter.java`:

~~~java
package com.example.app;

public final class Formatter {
    public static String greet(String name) {
        return "Hello, " + name;
    }
}
~~~

Example `Main.java`:

~~~java
package com.example.app;

import java.io.InputStream;
import java.util.Properties;

public final class Main {
    public static void main(String[] args) throws Exception {
        String name = args.length == 0 ? "Java" : args[0];
        Properties properties = new Properties();

        try (InputStream in = Main.class.getResourceAsStream("/app.properties")) {
            if (in == null) {
                throw new IllegalStateException("Missing app.properties");
            }
            properties.load(in);
        }

        System.out.println(properties.getProperty("banner") + ": " + Formatter.greet(name));
    }
}
~~~

Resource file `app.properties`:

~~~properties
banner=READY javac
~~~

Compile on JDK 17 or later:

~~~bash
javac --release 17 -encoding UTF-8 -d build/classes \
  src/main/java/com/example/app/Main.java \
  src/main/java/com/example/app/Formatter.java
~~~

Copy resources into the classpath output.

PowerShell:

~~~powershell
Copy-Item src/main/resources/* build/classes/ -Recurse
~~~

Linux/macOS:

~~~bash
cp -R src/main/resources/. build/classes/
~~~

Run the application:

~~~bash
java -cp build/classes com.example.app.Main Linh
~~~

Exact stdout:

~~~text
READY javac: Hello, Linh
~~~

Create the `dist` directory, then package:

~~~bash
jar --create --file dist/hello-app.jar --main-class com.example.app.Main -C build/classes .
~~~

Run the JAR:

~~~bash
java -jar dist/hello-app.jar Linh
~~~

Stdout remains:

~~~text
READY javac: Hello, Linh
~~~

## 24. Practical testing and completion criteria

End-to-end example on Azul JDK 24.0.2 compiled with `--release 17`:

- Compiled two source files simultaneously into the output directory.
- Copied resources into the classpath output.
- Ran the main class with the argument `Linh`.
- Packaged an executable JAR and ran it with `java -jar`.
- Compiled an application with a JAR dependency using `-cp`.
- Compiled two named modules using `--module-source-path`.
- Used the argument file `@compile.args` to pass options and source files.

Test results:

~~~text
READY javac: Hello, Linh
READY javac: Hello, Linh
READY classpath
READY modular javac
READY javac argfile: Hello, Linh
~~~

`javap -verbose` confirmed the class file generated with `--release 17` has `major version: 61` and `minor version: 0`.

Before considering a build complete, verify:

1. `javac` comes from the intended JDK.
2. Package/source paths and file names are correct.
3. All required sources and dependencies are found by the compiler.
4. `--release` and encoding are explicitly pinned.
5. Class files are written to a separate output directory.
6. Resources have been copied into the classpath.
7. The runtime classpath/module path has all required dependencies.
8. The JAR contains the right classes, resources, and manifest.
9. The application runs on the lowest runtime supported by the product.

## 25. References

- [Oracle JDK 26 — javac command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html): compiler syntax, --release, classpath, module path, source path, annotation processing, diagnostics, and argument files.
- [Oracle JDK 26 — java command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html): running main classes, executable JARs, modules, classpath, and source-file mode.
- [Oracle JDK 26 — JAR File Specification](https://docs.oracle.com/en/java/javase/26/docs/specs/jar/jar.html): JAR structure, manifest, Main-Class, Class-Path, and modular JARs.
- [Oracle JDK 26 — JDK Tool Specifications](https://docs.oracle.com/en/java/javase/26/docs/specs/man/index.html): catalog of JDK tools such as javac, java, jar, javap, and javadoc.

`javac` turns Java source into class files that can run on the JVM. To compile applications reliably, organize packages properly, pin release and encoding, manage classpath/module path, copy resources, verify the output, and only then package and run the artifact.
