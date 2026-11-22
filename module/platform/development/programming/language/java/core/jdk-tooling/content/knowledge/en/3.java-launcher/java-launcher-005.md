# Runtime Classpath

The **runtime classpath** is the list of locations where the Java application class loader searches for classes and libraries while the program is running. These locations are typically directories containing `.class` files, or JAR/ZIP archives containing bytecode. If the program references a class outside the JDK that is not present on the runtime classpath, the application may compile successfully but still fail at runtime.

The classpath is part of how the Java launcher starts an application. It answers the question: **Where will the JVM find the bytecode for application classes and dependencies?** Understanding the runtime classpath properly helps resolve errors such as `ClassNotFoundException`, `NoClassDefFoundError`, and running with the wrong library version.

## 1. Distinguishing the compile-time classpath from the runtime classpath

The two phases need to locate dependencies at two different times:

- **Compile-time classpath:** used by the `javac` compiler to find the types referenced by the source code. The commonly used option is `-cp` or `--class-path` when invoking `javac`.
- **Runtime classpath:** used by the Java launcher/JVM when running the program to find the classes to load. The commonly used option is `-cp` or `--class-path` when invoking `java`.

For example, if `Main.java` imports the `com.example.Greeter` class, `javac` needs to find that class during compilation. After producing `Main.class`, the bytecode still contains references to the class names and members it uses; compilation does not automatically embed every dependency into the `.class` file. At runtime, the JVM still must locate `Greeter.class` or the JAR containing it.

Therefore, a compile command with the right classpath does not guarantee the run command also has the right classpath. Configure dependencies for both phases, or let Maven/Gradle manage the compile classpath and runtime classpath according to the project configuration.

## 2. What can be placed on the classpath

An entry on the classpath is typically one of the following:

1. **A directory containing compiled packages.** If the class name is `com.example.app.Main`, the classpath directory must be the root directory containing the subdirectory `com/example/app/Main.class`.
2. **A JAR file.** JAR is the most common packaging format for Java classes and resources.
3. **A ZIP file.** The Java launcher can also locate classes inside a ZIP archive with the appropriate structure.
4. **A wildcard for JARs in a directory.** For example, `lib/*` represents the JAR files in the `lib` directory; this wildcard does not search subdirectories recursively.

The classpath is not a list of `.java` files. It points to locations containing compiled classes and resources that the application needs at runtime.

### A classpath directory must be the package root

Suppose the file is located at:

```text
build/classes/
└── com/
    └── example/
        └── app/
            └── Main.class
```

The fully qualified class name is `com.example.app.Main`. The classpath must contain `build/classes`, because from that root the JVM resolves the path `com/example/app/Main.class`.

If you set the classpath to `build/classes/com/example/app` and still run `com.example.app.Main`, the JVM will look in the wrong location. When running a class in a package, use the fully qualified class name and point the classpath to the directory above the package tree.

## 3. Passing the runtime classpath to the Java launcher

Use `-cp` or the full option name `--class-path`:

```sh
java --class-path "<entries>" package.name.Main
```

The following two forms are equivalent:

```sh
java -cp "app-classes:lib/greeter.jar" com.example.app.Main
java --class-path "app-classes:lib/greeter.jar" com.example.app.Main
```

The separator between entries depends on the operating system:

| Operating System | Separator | Example |
|---|---|---|
| Windows | Semicolon `;` | `app-classes;lib/greeter.jar` |
| macOS, Linux, and Unix | Colon `:` | `app-classes:lib/greeter.jar` |

Enclose the entire classpath value in quotes when it contains spaces or uses a wildcard. This ensures the shell passes it as a single argument to the Java launcher. The separator between entries is still the OS-specific character, not a directory separator `/` or `\`.

### Default classpath and the CLASSPATH environment variable

If `-cp` or `--class-path` is not passed, the Java launcher uses the `CLASSPATH` environment variable if it is set. If that variable is not set, the current directory (`.`) is the default classpath.

Example on macOS/Linux:

```sh
export CLASSPATH="build/classes:lib/greeter.jar"
java com.example.app.Main
```

On Windows PowerShell:

```powershell
$env:CLASSPATH = "build\classes;lib\greeter.jar"
java com.example.app.Main
```

When `-cp` or `--class-path` is passed, that value is used as the application classpath instead of the `CLASSPATH` environment variable. Avoid relying on a global `CLASSPATH` in development or CI environments: this hidden configuration easily causes a program to work on one machine and fail on another. The run command should declare dependencies explicitly or use a build tool to construct the runtime classpath.

## 4. Example of running an application with a separate dependency

The example below has two parts: a `Greeter` library and a `Main` application that uses it.

Directory structure:

```text
classpath-demo/
├── src/
│   ├── library/
│   │   └── com/example/greeting/Greeter.java
│   └── app/
│       └── com/example/app/Main.java
├── build/
└── lib/
```

File `src/library/com/example/greeting/Greeter.java`:

```java
package com.example.greeting;

public class Greeter {
    public String greet(String name) {
        return "Xin chào, " + name + "!";
    }
}
```

File `src/app/com/example/app/Main.java`:

```java
package com.example.app;

import com.example.greeting.Greeter;

public class Main {
    public static void main(String[] args) {
        Greeter greeter = new Greeter();
        System.out.println(greeter.greet("Java"));
    }
}
```

### 4.1. Compiling the two parts separately

Open a terminal in the `classpath-demo` root directory. Create the output directories before compiling.

macOS/Linux:

```sh
mkdir -p build/library build/app lib
javac -d build/library src/library/com/example/greeting/Greeter.java
javac --class-path build/library -d build/app src/app/com/example/app/Main.java
```

Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force build\library, build\app, lib | Out-Null
javac -d build\library src\library\com\example\greeting\Greeter.java
javac --class-path build\library -d build\app src\app\com\example\app\Main.java
```

In the first command, `javac -d build/library` places the library bytecode in `build/library`. In the second command, `--class-path build/library` lets the compiler find `Greeter` while compiling `Main`; the application bytecode is placed in `build/app`.

### 4.2. Running with two classpath directories

macOS/Linux:

```sh
java --class-path "build/app:build/library" com.example.app.Main
```

Windows PowerShell:

```powershell
java --class-path "build\app;build\library" com.example.app.Main
```

Output on both operating systems:

```text
Xin chào, Java!
```

The run command needs both entries: `build/app` contains `Main.class`, while `build/library` contains `Greeter.class`. If you omit the library entry, the application can fail to find `com.example.greeting.Greeter` when the JVM needs to load that class.

## 5. Packaging the library into a JAR and running with the classpath

Instead of pointing to the bytecode directory, you can package the library into a JAR:

macOS/Linux:

```sh
jar --create --file lib/greeter.jar -C build/library .
java --class-path "build/app:lib/greeter.jar" com.example.app.Main
```

Windows PowerShell:

```powershell
jar --create --file lib\greeter.jar -C build\library .
java --class-path "build\app;lib\greeter.jar" com.example.app.Main
```

The output is still:

```text
Xin chào, Java!
```

The `-C build/library .` option tells the `jar` tool to change into `build/library` and then package its contents. As a result, the JAR preserves the package structure, such as `com/example/greeting/Greeter.class`.

A classpath can contain both directories and JARs at the same time. The application does not need to know whether a library is stored as a bytecode directory or a JAR file, as long as the classpath entry points to the right location and contains the expected class structure.

## 6. Runtime dependencies in an executable JAR manifest

You can package the application classes into a JAR and declare both the entry point and dependent libraries in the manifest. This approach is useful when you want to launch with `java -jar`.

Create `manifest.mf` in the root directory:

```text
Main-Class: com.example.app.Main
Class-Path: lib/greeter.jar

```

The trailing blank line in the manifest is required to terminate the header section. Attributes:

- `Main-Class`: the fully qualified name of the class that has the `public static void main(String[] args)` method.
- `Class-Path`: URLs of libraries or additional locations required by the JAR. Entries are separated by spaces; relative paths are resolved relative to the location of the JAR containing the manifest.

Package the application:

```sh
jar --create --file app.jar --manifest manifest.mf -C build/app .
```

Resulting structure:

```text
classpath-demo/
├── app.jar
├── manifest.mf
└── lib/
    └── greeter.jar
```

Run the application:

```sh
java -jar app.jar
```

Output:

```text
Xin chào, Java!
```

In this example, `app.jar` contains `Main.class`, while `lib/greeter.jar` contains `Greeter.class`. The manifest tells Java where to find dependencies when launching the JAR.

**Note:** When using the `-jar` option, other classpath settings on the command line and the `CLASSPATH` environment variable are ignored. If you need to use `java -jar app.jar`, declare the appropriate dependencies in the manifest or package the application another way. Do not expect `java -cp ... -jar app.jar` to add to the classpath the way it does when running a class name directly.

The `Class-Path` attribute in a manifest uses URLs, follows space-separated rules, and resolves relative to the JAR containing the manifest. It does not use an OS-specific classpath string like `-cp`. For file names with spaces or special characters, appropriate URL encoding is required.

## 7. Wildcards for directories containing multiple JARs

When the `lib` directory contains multiple libraries, you can use a wildcard:

macOS/Linux:

```sh
java --class-path "build/app:lib/*" com.example.app.Main
```

Windows PowerShell:

```powershell
java --class-path "build\app;lib\*" com.example.app.Main
```

`lib/*` includes the JAR files directly inside the `lib` directory. The wildcard does not scan subdirectories and does not mean every file in the directory is added to the classpath. The order in which JARs are expanded from a wildcard is not guaranteed; therefore, do not rely on that order when multiple JARs contain the same class.

Wildcards are convenient for a dependency directory managed as a single set. In applications that require exact reproducibility, let Gradle/Maven manage dependencies and the runtime classpath to avoid depending on leftover JARs or unintended versions in a directory.

## 8. Class lookup order and version conflicts

With the standard classpath of the application class loader, entries are searched in the order they are declared. If multiple entries contain the same fully qualified class name, the class found first can shadow the class in later entries. This is a common reason an application accidentally loads an older library version.

For example, if both `lib/old-api.jar` and `lib/new-api.jar` contain `com.example.ApiClient`, which JAR is placed first can affect which class gets loaded. You should not resolve conflicts by arbitrarily reordering entries without determining which dependency version the application actually needs.

Practical guidelines:

- Only include dependencies that the application actually needs on the classpath.
- Avoid keeping multiple versions of the same library unless intentional.
- Do not assume any JAR ordering when using wildcards.
- Use the same dependency set across local runs, testing, and deployment.
- If using Gradle or Maven, inspect the runtime dependency graph when conflicts occur instead of manually adding JARs.

Class loaders also use a delegation mechanism between loaders. Therefore, classpath entry order is only one part of class loading; it does not mean an application can arbitrarily replace any Java platform class or any class provided by a parent loader.

## 9. Classpath and module path

Since Java 9, the Java Platform Module System added the **module path** for locating named modules. These two mechanisms serve two different styles of application organization:

| Mechanism | Purpose | Java launcher option |
|---|---|---|
| Classpath | Run applications and libraries under the traditional classpath model | `-cp`, `--class-path` |
| Module path | Locate named modules, typically described by `module-info.java` | `-p`, `--module-path` |

Classes loaded from the traditional classpath belong to the unnamed module. Placing a JAR that has `module-info.class` on the classpath does not automatically launch it as a named module.

If a project uses the module system, use the module path and the corresponding module launch syntax, for example:

```sh
java --module-path mods --module com.example.app/com.example.app.Main
```

The command above illustrates the syntax for running a module named `com.example.app` with main class `com.example.app.Main`. The module name and directory structure must match the compiled module. For applications not using the module system, continuing to use the classpath is the right choice.

## 10. Inspecting the classpath and tracing class loading

You can print the classpath the application was launched with:

```java
System.out.println(System.getProperty("java.class.path"));
```

This property is useful for checking the entries passed to the application. It is not a complete list of all loaded classes, nor does it reflect dependencies that may be added dynamically by custom class loaders.

To observe where the JVM loads classes from on JDK 9 and later, run:

```sh
java -Xlog:class+load=info --class-path "build/app:lib/greeter.jar" com.example.app.Main
```

The log can be long because the JVM loads both platform classes and application classes. Search for the class name you want to inspect, such as `com.example.greeting.Greeter`, and check the source printed in the log. On Windows, replace the `:` separator between entries with `;`.

When troubleshooting manually, also check the current working directory. Relative entries such as `lib/greeter.jar` are resolved from the **process working directory** when using the classpath on the command line; they are not automatically resolved relative to the directory containing `.java` files or IDE configuration files.

## 11. Common runtime classpath errors

| Error or symptom | Possible cause | How to check |
|---|---|---|
| `Error: Could not find or load main class ...` | Classpath is missing the directory/JAR containing the main class, package root is wrong, or fully qualified class name is incorrect | Check the package name, class name, and `.class` location; the classpath must point to the root of the package tree |
| `ClassNotFoundException` | Code loads a class by name, e.g., `Class.forName`, and the loader cannot find the class | Verify the class name and that the dependency is present on the classpath of the loader in use |
| `NoClassDefFoundError` | A required class was available at compile time but could not be found when the runtime needed to load or link it | Check the runtime classpath and transitive dependencies; ensure the JAR is deployed with the application |
| `NoSuchMethodError` or `NoSuchFieldError` | Runtime loaded a library version incompatible with the version used at compile time | Check for duplicate JARs, classpath order, and actual dependency versions |
| Works in the IDE but fails from the terminal | The IDE configures a different runtime classpath or working directory | Inspect the IDE Run/Debug configuration and reproduce the classpath in the terminal command |
| Works on a development machine but fails on another | A dependency exists only locally, relies on a hidden `CLASSPATH`, or relative paths differ | Package/provide all dependencies and use a reproducible run command |
| Updated a JAR but the program still uses the old API | Multiple copies of the JAR exist or an old process/daemon is still running | Check class-loading logs, the runtime dependency graph, and restart the process |

Distinguishing two commonly confused errors:

- `ClassNotFoundException` is an exception typically thrown when the application asks a loader to find a class by name and it cannot be found.
- `NoClassDefFoundError` is a linkage/class-loading error thrown when the JVM needs a class definition that the runtime cannot provide. A common case is a missing dependency at runtime even though the source code compiled.

If the class is found but the API of the runtime version differs from the API the application was compiled against, you may encounter `NoSuchMethodError` or `NoSuchFieldError`. In that situation, simply adding another random JAR can make diagnosis harder; determine which library version is actually being loaded.

## 12. Checklist before concluding an application is missing a dependency

1. Verify the fully qualified class name and package root.
2. Verify the `.class` file or JAR containing the class exists at the declared path.
3. Check the classpath of the run command, not just the compile command.
4. Use the OS-appropriate separator: `;` on Windows, `:` on macOS/Linux.
5. Check the working directory if the classpath contains relative paths.
6. Check for JARs with duplicate class names or multiple versions of the same dependency.
7. If running with `java -jar`, check `Main-Class` and `Class-Path` in the manifest.
8. If the project uses the module system, confirm you are configuring the module path rather than confusing it with the classpath.
9. Use class-loading logs or the runtime dependency graph to find the exact source of the class.

The runtime classpath is the configuration for locating classes at runtime. When the compile-time classpath and runtime classpath are consistent, all libraries are provided, and paths are resolved correctly, the Java launcher can load application classes and dependencies reliably.