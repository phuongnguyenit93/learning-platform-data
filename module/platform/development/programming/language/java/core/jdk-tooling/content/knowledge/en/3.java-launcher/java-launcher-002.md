# Running a Class with the Java Launcher

## 1. What does the Java launcher do?

The Java launcher is the `java` command-line program included with the JDK. It starts the Java Virtual Machine (JVM), locates and loads the target class, and then invokes that class's entry-point method. When working with a compiled Java program, the launcher takes the fully qualified class name and the path containing the bytecode files.

It is important to distinguish between two commands in the basic workflow:

- `javac` compiles `.java` source code into `.class` bytecode.
- `java` launches the compiled class on the JVM.

Example workflow:

~~~text
Hello.java --javac--> Hello.class --java--> JVM runs the main method
~~~

General command to run a class on the classpath:

~~~bash
java [JVM options] -cp <classpath> <fully-qualified-class-name> [application-args...]
~~~

Where:

- `JVM options` are VM configuration options, such as `-Xmx512m` or `-Dapp.mode=dev`.
- `-cp` or `--class-path` specifies where the launcher looks for classes and libraries.
- `<fully-qualified-class-name>` is the class name following Java conventions, including the package if the class belongs to a package.
- Values after the class name are passed into the program's `main(String[] args)`.

Options intended for the launcher/JVM must appear before the main class name. Arguments placed after the class name are treated as application arguments.

## 2. Program entry point: the `main` method

In Java 17, a class can be launched in the standard way when it provides a public, static `main` method returning `void`:

~~~java
public static void main(String[] args)
~~~

`String[] args` is an array containing the arguments passed by the caller. You can also declare the parameter using varargs `String... args` because it is equivalent to a `String[]` array at the type level.

Simple class example:

~~~java
public class Hello {
    public static void main(String[] args) {
        System.out.println("Hello from Java!");
    }
}
~~~

Suppose the file is saved as `Hello.java`. Compile and run:

~~~bash
javac Hello.java
java Hello
~~~

Output:

~~~text
Hello from Java!
~~~

Here, you do not include the `.class` extension in the `java Hello` command. The launcher takes the class name `Hello`, locates the `Hello.class` bytecode file on the classpath, and invokes the `main` method.

For a class in a package, the class name must include the package. For example:

~~~java
package com.example;

public class Hello {
    public static void main(String[] args) {
        System.out.println("Hello from com.example!");
    }
}
~~~

Save the source file at `src/com/example/Hello.java`, compile into the `out` directory, and run using the fully qualified name:

~~~bash
javac -d out src/com/example/Hello.java
java -cp out com.example.Hello
~~~

Output:

~~~text
Hello from com.example!
~~~

Some important rules:

- Use the fully qualified class name such as `com.example.Hello`, not the file path `com/example/Hello.class`.
- Do not append the `.class` extension after the class name.
- If the class declares a `package`, the bytecode directory structure must reflect that package.
- Package and class names are case-sensitive.
- Under Java 17 conventions, the `main` method must be `public static void main(String[] args)` or its varargs equivalent. A `main` method that is non-static, non-public, or has a different return type is not the standard entry point that the launcher looks for.

## 3. Complete example: compiling and running a class

Create the following directory structure from the project root:

~~~text
java-launcher-demo/
├── src/
│   └── com/
│       └── example/
│           └── Greeter.java
└── out/
~~~

Contents of `src/com/example/Greeter.java`:

~~~java
package com.example;

public class Greeter {
    public static void main(String[] args) {
        String name = args.length == 0
                ? "Java"
                : String.join(" ", args);

        System.out.println("Hello, " + name + "!");
    }
}
~~~

Compile with JDK 17 or later, while instructing the compiler to target Java 17 APIs and bytecode:

~~~bash
javac --release 17 -encoding UTF-8 -d out src/com/example/Greeter.java
~~~

Run the class without passing any arguments:

~~~bash
java -cp out com.example.Greeter
~~~

Stdout:

~~~text
Hello, Java!
~~~

Pass arguments to the application:

~~~bash
java -cp out com.example.Greeter Ada Lovelace
~~~

Stdout:

~~~text
Hello, Ada Lovelace!
~~~

Pass a name containing a space as a single argument by enclosing it in quotes:

~~~bash
java -cp out com.example.Greeter "Ada Lovelace"
~~~

Stdout is still:

~~~text
Hello, Ada Lovelace!
~~~

In this example, the program uses `String.join(" ", args)`, so both passing two separate words and passing a single quoted string with a space produce the same greeting. If the application needs to distinguish each argument individually, read `args[0]`, `args[1]` separately instead of joining them.

On Windows PowerShell, the corresponding commands can be run from the project root:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -encoding UTF-8 -d out src/com/example/Greeter.java
java -cp out com.example.Greeter "Ada Lovelace"
~~~

If the `out` directory already exists, the directory creation command preserves its existing contents. For a clean build, use a dedicated output directory for the current compilation to avoid accidentally running stale bytecode left over from previous builds.

## 4. Classpath: where to find classes and libraries

The classpath is the list of directories and JAR files that the Java launcher uses to locate classes on the classpath (the unnamed module). When running a program, the classpath must contain the main class and all libraries required at runtime.

Two common ways to specify it:

~~~bash
java -cp out com.example.Greeter
java --class-path out com.example.Greeter
~~~

`-cp` and `--class-path` have the same meaning. You can pass multiple classpath entries, separated by an OS-dependent character:

| Environment | Separator | Example |
|---|---|---|
| Windows | Semicolon `;` | `out;lib/example.jar` |
| Linux/macOS | Colon `:` | `out:lib/example.jar` |

Example where the application requires JARs located in the `lib` directory:

~~~bash
# Windows
java -cp "out;lib/*" com.example.Greeter

# Linux/macOS
java -cp "out:lib/*" com.example.Greeter
~~~

The `lib/*` pattern instructs the launcher to include JAR files directly inside the `lib` directory on the classpath. It does not search for JARs recursively in subdirectories. Enclose the entire classpath in quotes to prevent the shell from interpreting special characters unexpectedly.

The classpath is resolved from left to right. If multiple entries contain the same class name, the entry appearing earlier may be used first. Therefore, avoid having multiple versions of the same library on the classpath; they can cause unpredictable errors such as `NoSuchMethodError` or inconsistent behavior.

If neither `-cp` nor `--class-path` is specified, the launcher uses the default classpath, which is typically the current working directory. The `CLASSPATH` environment variable can also set this default. When `-cp` is specified on the command line, the classpath in the command overrides the default value from `CLASSPATH`.

In practice, it is best to declare the classpath explicitly in launch scripts or IDE/CI configurations. Relative paths such as `out` are resolved relative to the process's current working directory, not automatically relative to the location of the `.java` file.

## 5. Passing arguments to a program

Every value placed after the main class name is passed into the `args` array. The launcher does not interpret these values as JVM options.

Example:

~~~bash
java -cp out com.example.Greeter "Ada Lovelace" 3
~~~

With the command above, the program receives:

| Expression | Value |
|---|---|
| `args.length` | `2` |
| `args[0]` | `Ada Lovelace` |
| `args[1]` | `3` |

If a numeric value is needed, the program must parse and validate the input itself:

~~~java
public class Sum {
    public static void main(String[] args) {
        if (args.length != 2) {
            System.err.println("Usage: Sum <a> <b>");
            System.exit(1);
            return;
        }

        try {
            int a = Integer.parseInt(args[0]);
            int b = Integer.parseInt(args[1]);
            System.out.println(a + b);
        } catch (NumberFormatException ex) {
            System.err.println("Arguments must be integers.");
            System.exit(1);
        }
    }
}
~~~

Compile and run:

~~~bash
javac -d out Sum.java
java -cp out Sum 12 30
~~~

Stdout:

~~~text
42
~~~

If the wrong number or format of arguments is passed, the application handles it and may exit with a non-zero exit code. The launcher only forwards the arguments; validating their meaning and correctness is the program's responsibility.

## 6. JVM options and argument ordering

Some options commonly placed before the class name:

| Option | Effect |
|---|---|
| `-Xms128m` | Sets the initial heap size. |
| `-Xmx512m` | Sets the maximum heap limit. |
| `-Dapp.mode=dev` | Sets a system property named `app.mode` with value `dev`. |
| `-ea` or `-enableassertions` | Enables assertion statements. |
| `-verbose:class` | Prints class loading information; useful for diagnosing class loading issues. |
| `--version` | Prints the launcher/JDK version and exits. |
| `--help` | Displays launcher help. |

Example combining JVM configuration and classpath:

~~~bash
java -Xms128m -Xmx512m -Dapp.mode=dev -ea -cp out com.example.Greeter "Ada Lovelace"
~~~

Inside the program, you can read the system property:

~~~java
String mode = System.getProperty("app.mode", "default");
System.out.println(mode);
~~~

Ordering matters. For example:

~~~bash
# -Dapp.mode=dev is a JVM option
java -Dapp.mode=dev -cp out com.example.Greeter

# --debug is an application argument
java -cp out com.example.Greeter --debug
~~~

In the second command, `--debug` is passed into `args`. It is not a launcher option because it appears after the class name. If the application needs to understand `--debug`, the application code itself must parse that argument.

## 7. Running a class that depends on other classes

A class can compile successfully yet still fail to run if required dependency libraries are missing from the runtime classpath. Compile-time classpath and runtime classpath are two independent configurations: the compiler needs to find the types referenced by the source code, while the launcher needs to find the bytecode of all classes used at runtime.

Example with two classes:

`src/com/example/Message.java`:

~~~java
package com.example;

public class Message {
    public static String greeting(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

`src/com/example/Main.java`:

~~~java
package com.example;

public class Main {
    public static void main(String[] args) {
        String name = args.length == 0 ? "Java" : args[0];
        System.out.println(Message.greeting(name));
    }
}
~~~

Compile both classes into `out`:

~~~bash
javac --release 17 -d out src/com/example/Message.java src/com/example/Main.java
~~~

Run the class containing the `main` method:

~~~bash
java -cp out com.example.Main "JDK Tooling"
~~~

Stdout:

~~~text
Hello, JDK Tooling!
~~~

In a project with external libraries, add the output directory and dependency JARs to the runtime classpath. Example on Linux/macOS:

~~~bash
java -cp "out:lib/library-a.jar:lib/library-b.jar" com.example.Main
~~~

On Windows:

~~~powershell
java -cp "out;lib/library-a.jar;lib/library-b.jar" com.example.Main
~~~

Do not assume that because the compiler found a library at build time, the launcher will automatically find it at runtime. Both stages must be configured.

## 8. Running a class in a named module

For projects using the Java Platform Module System (JPMS), modules are placed on the module path. In this case, use the `--module-path` and `-m` (or `--module`) options to specify the module and main class.

Example structure:

~~~text
src/
├── module-info.java
└── com/
    └── example/
        └── Main.java
~~~

`module-info.java`:

~~~java
module com.example.app {
}
~~~

`src/com/example/Main.java`:

~~~java
package com.example;

public class Main {
    public static void main(String[] args) {
        System.out.println("Hello from module!");
    }
}
~~~

Compile the module into `mods/com.example.app`:

~~~bash
javac --release 17 -d mods/com.example.app src/module-info.java src/com/example/Main.java
~~~

Run the module's main class:

~~~bash
java --module-path mods -m com.example.app/com.example.Main
~~~

Stdout:

~~~text
Hello from module!
~~~

The `-m module/class` syntax specifies the module name and the fully qualified name of the main class. The module path contains compiled modules or modular JARs. This mechanism differs from the classpath:

- The classpath primarily locates classes on the classpath and places them into the unnamed module.
- The module path locates modules with module descriptors and enforces JPMS dependency and encapsulation rules.

Do not place a module directory on the classpath and expect the launcher to run it automatically as a named module. Choose either the classpath or the module path according to how the project is packaged.

## 9. Comparing running a class, running a JAR, and source-file mode

The Java launcher supports multiple launch modes. They share the `java` command, but how the program is specified differs.

| Mode | Syntax | When to use |
|---|---|---|
| Run a class | `java -cp out com.example.Main` | You have compiled main class bytecode and want to specify the classpath. |
| Run an executable JAR | `java -jar app.jar` | The JAR has a manifest declaring `Main-Class`. |
| Run a module | `java --module-path mods -m module.name/com.example.Main` | The application is organized as a named module. |
| Source-file mode | `java Hello.java` | Run a single source file directly; the launcher compiles it automatically in source-file mode, available since Java 11. |

When running a JAR:

~~~bash
java -jar app.jar
~~~

The launcher reads the entry class from the `Main-Class` attribute in the manifest. Application arguments are placed after the JAR name. In `-jar` mode, a classpath passed separately via `-cp` is not used to override the classpath defined by the JAR; if external libraries are needed, package them or configure the appropriate dependency paths.

Source-file mode:

~~~bash
java Hello.java
~~~

is a convenient way to run small programs or experiments. Once you have `.class` files and want explicit control over output, dependencies, and runtime configuration, use the class-running mode described in the earlier sections.

## 10. Running from terminal, IDE, and scripts

Whether launching from a terminal, an IDE, or a script, the JVM still requires the same information: the selected JDK/runtime, the main class or module, the classpath/module path, JVM options, and application arguments.

In an IDE, a Run configuration typically includes:

- Main class: for example `com.example.Main`.
- Working directory: the directory from which the application's relative paths are resolved.
- Use classpath of module: the module/project output and required libraries.
- VM options: for example `-Xmx512m` or `-Dapp.mode=dev`.
- Program arguments: arguments passed into `main(String[] args)`.

When running from a script, specify the working directory and classpath explicitly. Bash example:

~~~bash
#!/usr/bin/env bash
set -eu
cd /path/to/project
java -cp "out:lib/*" com.example.Main "$@"
~~~

`"$@"` forwards each argument received by the script as a separate argument to the Java program. On Windows, a PowerShell script can use:

~~~powershell
Set-Location "C:\path\to\project"
java -cp "out;lib/*" com.example.Main @args
exit $LASTEXITCODE
~~~

Use the actual project paths when configuring scripts. In CI, pin the required JDK and have the build step produce the output directory before the run step.

## 11. Common errors when running a class

| Error/symptom | Common cause | How to resolve |
|---|---|---|
| `Could not find or load main class` | Classpath is missing the output directory, wrong class name, or running from a different working directory. | Check `-cp`, working directory, package, and fully qualified class name. |
| `ClassNotFoundException` | Code uses reflection or a library requests a class not present on the runtime classpath/module path. | Add the right JAR/module version and check the runtime configuration. |
| `NoClassDefFoundError` | A required class could not be found when the JVM loads or uses a class. | Check runtime dependencies; compare the runtime classpath against build dependencies. |
| `Main method not found` | Missing a standard entry point or invalid `main` signature. | Use `public static void main(String[] args)`. |
| `UnsupportedClassVersionError` | Bytecode was compiled with a newer Java version than the active runtime. | Use a matching runtime or build with `javac --release` for the lower target version. |
| `NoSuchMethodError` / `NoSuchFieldError` | Runtime loaded a library version incompatible with the version used at compile time. | Remove duplicate or mismatched JAR versions and align dependencies. |
| `Exception in thread "main"` | The program started successfully but threw an unhandled exception. | Read the stack trace, locate the first frame belonging to application code, and fix the root cause. |
| `java` command not recognized | JDK is not on `PATH` or the terminal is using stale environment settings. | Check `java -version`, `where java` on Windows, or `which java` on macOS/Linux. |

A quick diagnostic checklist:

1. Verify the runtime: run `java -version`.
2. Verify the current directory: check where the `out` directory is located.
3. Verify bytecode was generated: check `out/com/example/Main.class`.
4. Re-run with the fully qualified class name and an explicit classpath.
5. If the error is a missing dependency, add the right JAR/module to the runtime path.
6. If the error occurs after the program starts running, treat the stack trace as an application bug rather than a launcher error.

When you need to see where classes are loaded from, you can use `-verbose:class` to print class loading information. This output can be verbose; enable it only when investigating.

## 12. Checklist before running a class

- Source code compiled successfully with `javac`.
- Running the intended JDK/runtime.
- Main class name is correct, including its package.
- Classpath contains the output directory and all required dependencies.
- Working directory matches any relative paths used.
- JVM options are placed before the class name.
- Application arguments are placed after the class name and properly quoted if they contain spaces.
- If using JPMS, the module path and module/main class name are declared correctly.
- Stdout, stderr, and exit code are checked when running in scripts or CI.

When running a compiled class, identify the fully qualified class name and the location of its bytecode first, then run `java -cp <classpath> <fully-qualified-class-name>`. If the program requires libraries, modules, or JVM configuration, place those before the class name; arguments placed after the class name are passed to `main`.
