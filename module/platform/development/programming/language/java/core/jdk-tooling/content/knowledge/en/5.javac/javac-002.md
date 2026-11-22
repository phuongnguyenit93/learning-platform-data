# Compiling a Java Class with javac

`javac` is the Java compiler included with the JDK. It takes `.java` source code, checks syntax and data types, and then generates bytecode in `.class` files so the JVM can load and execute them.

When compiling a class, you need to identify the source file, class name, package, dependent libraries, and output directory. For a simple class with no package or external libraries, simply run `javac HelloOne.java` in the directory containing the file. For a project with packages, you should specify the output directory with `-d` to preserve the proper package structure.

## 1. From .java File to .class File

Basic workflow:

~~~text
HelloOne.java
     |
     | javac
     v
HelloOne.class
     |
     | java (JVM)
     v
Program runs
~~~

- **Source file (.java)** contains class, interface, enum, record declarations, and Java source code.
- **Compiler (javac)** parses syntax, performs type checking, runs annotation processors if any, and generates bytecode.
- **Class file (.class)** contains bytecode along with the metadata needed for the JVM to link and execute the class.
- **Java launcher (java)** initializes the JVM, locates the class via the classpath/module path, and invokes the `main` method if it is the application entry point.

Compiling a class does not produce a standalone native executable. A `.class` file requires a compatible JVM to run. It also does not bundle dependent libraries automatically; the classpath or module path at runtime must still provide the required dependencies.

A source file can declare multiple non-public top-level classes. `javac` may produce multiple `.class` files from a single `.java` file; nested classes can also generate separate class files with names containing `$`. Therefore, compiling a single source file does not necessarily produce only one class file.

## 2. Simple Example: Compiling a Class Without a Package

Create a file named `HelloOne.java` with the following content:

~~~java
public class HelloOne {
    public static void main(String[] args) {
        System.out.println("Hello from javac!");
    }
}
~~~

The file name must match the name of the top-level public class exactly: `HelloOne.java`. Java is case-sensitive in class names. If you declare `public class HelloOne` but save it as `helloone.java`, the compiler will typically report an error stating that the public class name must match the file name.

Open a terminal in the directory containing the source file and check the compiler:

~~~sh
javac -version
~~~

Compile:

~~~sh
javac HelloOne.java
~~~

If there are no errors, the compiler creates `HelloOne.class` in the current directory (for an example without a package declaration). Run the class using the Java launcher:

~~~sh
java HelloOne
~~~

Stdout output:

~~~text
Hello from javac!
~~~

When running, specify the class name `HelloOne`, without the `.class` extension. The Java launcher expects a class name, not a class file path.

## 3. Compiling into a Separate Output Directory with -d

In real-world projects, `.class` files should not be mixed with source files. The `-d` option specifies the destination directory for class files:

~~~sh
mkdir out
javac -d out HelloOne.java
java -cp out HelloOne
~~~

The `out` directory must exist before calling `javac -d out`; the compiler does not create the root output directory automatically. If the directory already exists, there is no need to recreate it.

In PowerShell, you can create the directory if it does not already exist:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
javac -d out HelloOne.java
java -cp out HelloOne
~~~

`-d out` causes the class file to be written into `out`. When running, `-cp out` adds that directory to the classpath so the Java launcher can find the class. The compiler's `-d` and the launcher's `-cp` are two options used at two different stages.

Directory structure after compiling the package-less example:

~~~text
project/
├── HelloOne.java
└── out/
    └── HelloOne.class
~~~

## 4. Compiling a Class with a Package

When a source file declares a package, the directory path should reflect the package name. For example, create `src/com/example/Greeter.java`:

~~~java
package com.example;

public class Greeter {
    public static void main(String[] args) {
        System.out.println("Hello from com.example!");
    }
}
~~~

The `package com.example;` statement places the class in the `com.example` package. The fully qualified class name is `com.example.Greeter`.

Create the output directory and compile from the project root directory:

~~~sh
mkdir -p out
javac -d out src/com/example/Greeter.java
~~~

In PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
javac -d out src/com/example/Greeter.java
~~~

After compiling, the output structure is:

~~~text
out/
└── com/
    └── example/
        └── Greeter.class
~~~

Run using the fully qualified class name and set the classpath to the root directory of the package tree:

~~~sh
java -cp out com.example.Greeter
~~~

Output:

~~~text
Hello from com.example!
~~~

Do not set the classpath to `out/com/example` when trying to run `com.example.Greeter`. The classpath must point to the root directory containing the `com` directory; the JVM appends the package components automatically to locate the class file.

## 5. Compiling a Class That Depends on Another Class

A class can reference another class in the same project or in a JAR library. The compiler must be able to find the referenced types to check and compile them.

Suppose you have two source files:

~~~text
src/
└── com/example/
    ├── MessageFormatter.java
    └── Main.java
~~~

`MessageFormatter.java`:

~~~java
package com.example;

public class MessageFormatter {
    public String format(String name) {
        return "Welcome, " + name + "!";
    }
}
~~~

`Main.java`:

~~~java
package com.example;

public class Main {
    public static void main(String[] args) {
        MessageFormatter formatter = new MessageFormatter();
        System.out.println(formatter.format("Java"));
    }
}
~~~

The clearest way to compile a group of classes is to list all source files:

~~~sh
mkdir -p out
javac -d out src/com/example/MessageFormatter.java src/com/example/Main.java
java -cp out com.example.Main
~~~

Output:

~~~text
Welcome, Java!
~~~

If you only pass `Main.java` and the compiler needs `MessageFormatter`, `javac` can locate and compile the source dependency via the source path. You can explicitly specify the source path:

~~~sh
javac -sourcepath src -d out src/com/example/Main.java
~~~

To keep build commands reproducible and avoid relying on implicit source lookup rules, it is best to explicitly specify the source path or list the source files to compile.

## 6. Adding External Libraries with Classpath

If a class references a library packaged in a JAR, provide that JAR to the compiler using `-cp` (or `-classpath`). The classpath is a list of directories and JARs containing the classes the compiler needs to find.

For example, if the dependency is located at `lib/utility.jar`:

~~~sh
javac -cp lib/utility.jar -d out src/com/example/Main.java
~~~

When there are multiple classpath entries, use the OS-specific path separator:

- Windows: semicolon `;`.
- macOS/Linux: colon `:`.

Example on Linux/macOS:

~~~sh
javac -cp "lib/utility.jar:lib/logging.jar" -d out src/com/example/Main.java
~~~

Example on Windows:

~~~powershell
javac -cp "lib\utility.jar;lib\logging.jar" -d out src\com\example\Main.java
~~~

The classpath is required at both stages if the application uses that library: at compile time so the compiler can find types, and at runtime so the JVM can find the referenced classes. Example of running on Linux/macOS:

~~~sh
java -cp "out:lib/utility.jar:lib/logging.jar" com.example.Main
~~~

On Windows, use semicolons in the classpath:

~~~powershell
java -cp "out;lib\utility.jar;lib\logging.jar" com.example.Main
~~~

Setting the classpath in the `javac` command does not automatically save that configuration into the `.class` file. At runtime, you must pass the corresponding classpath or configure the runtime environment of your build tool/IDE.

## 7. Selecting the Target Java Version with --release

By default, `javac` compiles against the language version and APIs of the JDK currently in use. If a project needs to be compatible with a specific Java version, consider using the `--release` option:

~~~sh
javac --release 17 -d out HelloOne.java
~~~

`--release 17` instructs the compiler to target Java 17 and produce class files compatible with Java 17, while restricting the platform APIs that can be used to those available in that version. This option was introduced in JDK 9; the compiler must be JDK 17 or newer to target release 17.

Do not confuse `--release` with merely switching the `java` version used to run the compiler. You should check both the compiler and target runtime:

~~~sh
javac -version
java -version
~~~

If you are using a newer compiler but need to generate bytecode that runs on an older Java version, `--release` is generally safer than the separate `-source` and `-target` options, because `--release` also constrains the allowed Java SE API set.

## 8. Useful javac Options When Compiling a Class

| Option | Purpose |
|---|---|
| `-d <directory>` | Specify the destination directory for class files |
| `-cp` / `-classpath` | Specify the classpath to locate dependent classes/JARs |
| `-sourcepath` | Specify where to find dependent source files |
| `--release <version>` | Select the target Java version and corresponding platform APIs |
| `-encoding UTF-8` | Specify the character encoding of source files |
| `-g` | Generate debugging information in class files |
| `-parameters` | Preserve method parameter names for reflection |
| `-Xlint:all` | Enable recommended compiler warnings |
| `-Werror` | Treat warnings as errors |
| `-verbose` | Output detailed information about compilation activity |

Example of a compilation command that checks warnings and specifies the target version:

~~~sh
javac --release 17 -encoding UTF-8 -Xlint:all -d out src/com/example/Greeter.java
~~~

Using `-encoding UTF-8` ensures consistent results when source files contain Vietnamese (or other non-ASCII) characters across different build environments. You should enable warnings to catch issues early; avoid adding `-Werror` if the project does not yet have a clear policy for handling warnings.

You can place a long list of source files into an argument file to avoid overly long commands:

~~~text
# sources.args
--release
17
-d
out
src/com/example/Greeter.java
src/com/example/Main.java
~~~

Run:

~~~sh
javac @sources.args
~~~

Argument files are useful in build scripts or when there are many source files; for a single simple class, a direct command is easier to read.

## 9. End-to-End Workflow for Compiling a Class

For a simple class without a package, you can follow these steps:

1. Install the JDK and ensure the terminal can find `javac` and `java`.
2. Create a source file whose name matches the public class.
3. Check the package declaration; if a package is used, maintain the matching source directory tree.
4. Identify the dependencies needed for compilation and runtime.
5. Create the output directory if using `-d`.
6. Run `javac` with the necessary options.
7. Verify that the class file is created in the correct location.
8. Run the class with `java` using the fully qualified class name and the correct classpath.
9. Compare stdout or actual behavior against expectations.

For larger projects, let Gradle or Maven manage source sets, dependencies, output directories, and Java versions. Manual `javac` commands are well suited for learning how compilation works, quickly compiling a single class, or diagnosing compiler errors.

## 10. Common Errors and Troubleshooting

| Error/Symptom | Common Cause | Resolution |
|---|---|---|
| `'javac' is not recognized` or `command not found` | JDK is not installed or PATH does not include the JDK `bin` directory | Check JDK installation, `JAVA_HOME`, and PATH; open a new terminal |
| `class X is public, should be declared in a file named X.java` | File name does not match the public top-level class name | Rename the file or class so they match exactly |
| `package ... does not exist` | Missing dependency or incorrect classpath/sourcepath | Add the appropriate JAR, class directory, or source path |
| `cannot find symbol` | Typo, missing import, unfound class dependency, or case-sensitivity mismatch | Check declarations, imports, packages, and classpath |
| `';' expected` or syntax error | Invalid syntax or missing delimiter in source code | Read the line reported by the compiler; check braces, semicolons, and structure |
| `invalid source release` | Compiler does not support the requested version | Use a newer JDK or select a supported `--release` version |
| `error: release version ... not supported` | Compiler JDK is older than the target release | Upgrade the JDK used for compilation |
| `Could not find or load main class` | Incorrect class name, classpath does not point to package root, or class has not been compiled | Use the fully qualified class name and point the classpath to the root directory |
| `UnsupportedClassVersionError` | Runtime is older than the compiled bytecode version | Run with a compatible JDK or compile with a lower `--release` |
| Old class file still runs even though source was edited | Running from the wrong output directory or forgot to recompile | Verify `-d` and classpath; rebuild the class |

Compilation errors usually prevent the compiler from generating valid class files for the erroneous source. When the compiler reports errors, fix the first error and recompile; subsequent errors may simply be cascading consequences of the earlier one.

## 11. Verification Checklist

- [ ] Using a JDK that includes `javac` and `java`.
- [ ] File name matches the public top-level class name.
- [ ] Package declaration and source directory path are consistent.
- [ ] Classpath/sourcepath contains all required dependencies.
- [ ] Output directory exists if using `-d`.
- [ ] Target Java version matches the intended runtime.
- [ ] Compiler completes without errors.
- [ ] Class file is in the expected directory and package path.
- [ ] Run command uses the fully qualified class name and correct classpath.
- [ ] Execution output matches expectations.

When compiling a class, keep clear control over the source file, package, dependencies, and output directory. `javac` produces bytecode; `java` uses the JVM to load the class file and run the program. Mastering these two steps helps you understand build errors and easily scale from a single class to multiple packages or a complete Java project.