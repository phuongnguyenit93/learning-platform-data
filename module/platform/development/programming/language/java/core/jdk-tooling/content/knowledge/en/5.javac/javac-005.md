# Classpath in javac

When compiling a Java program that uses classes from external libraries, the `javac` compiler needs to know where to find those classes. The **classpath** is the list of directories, JAR files, or ZIP files that the compiler and the JVM search to load Java classes.

During compilation, the classpath helps `javac` find the compiled classes referenced by the source code. When running the application, the JVM also needs the corresponding classpath to find those classes. These two configurations are two separate operations.

## 1. What is the Classpath?

The classpath is a list of locations containing `.class` class files and Java libraries in JAR/ZIP format. A classpath entry can be:

- A root directory containing the package structure and `.class` files.
- A `.jar` library file.
- A ZIP file containing Java classes.

Example directory structure:

```text
project/
  out/
    app/
      Main.class
  lib/
    helper.jar
```

If the `app.Main` class needs to use classes in `helper.jar`, the classpath needs to include the root directory `out` at runtime and the JAR file `lib/helper.jar`.

**The path must point to the root of the package structure.** If a class has the fully qualified name `com.example.Tool`, the classpath directory must be the directory containing the `com` subdirectory, not the `com/example` directory itself.

The classpath is not a mandatory location for storing source code. Source code is passed directly to `javac` or found via the source path; the classpath primarily specifies where to find compiled classes and libraries.

## 2. javac Classpath Options

There are three equivalent ways to specify the classpath:

- `-cp`
- `-classpath`
- `--class-path`

Example:

```bash
javac -cp lib/helper.jar -d out src/app/Main.java
```

The command above means:

- `javac`: invokes the Java compiler.
- `-cp lib/helper.jar`: searches for dependent classes in the JAR.
- `-d out`: writes the generated `.class` files into the `out` directory.
- `src/app/Main.java`: the source file to compile.

This can be written equivalently as:

```bash
javac --class-path lib/helper.jar -d out src/app/Main.java
```

If the library has multiple JARs, place the entries in the same classpath string and separate them with the character appropriate for the operating system.

**Windows (semicolon):**

```powershell
javac -cp "lib\helper.jar;lib\logging.jar" -d out src\app\Main.java
```

**macOS/Linux (colon):**

```bash
javac -cp "lib/helper.jar:lib/logging.jar" -d out src/app/Main.java
```

If a path contains spaces, enclose the entire classpath value in quotes so the shell passes it as a single argument.

## 3. Default Classpath and the CLASSPATH Variable

If `-cp`, `-classpath`, or `--class-path` is not passed, `javac` uses the default classpath. This value can come from the `CLASSPATH` environment variable; if that variable is not set, the current directory is typically used.

For example, if the terminal is in the project directory and `CLASSPATH` is not configured, the compiler can search for classes in the current directory.

When `-cp` is explicitly specified, that value replaces the default classpath for that compilation. It does not automatically append the current directory or the `CLASSPATH` value.

If both the current directory and libraries are needed, include both in the list.

**Windows:**

```powershell
javac -cp ".;lib\helper.jar" -d out src\app\Main.java
```

**macOS/Linux:**

```bash
javac -cp ".:lib/helper.jar" -d out src/app/Main.java
```

In real-world projects, you should specify the classpath explicitly in build commands or Maven/Gradle configurations rather than relying on a global `CLASSPATH`. This keeps compilation results consistent across personal machines, IDEs, and CI.

## 4. Complete Example: Compiling with a JAR Library

The following example creates a small library, packages it into a JAR, and then uses that library when compiling an application.

Source file structure:

```text
project/
  lib-src/
    greeter/
      Greeting.java
  src/
    app/
      Main.java
```

### Step 1: Create the Library Class

File **`lib-src/greeter/Greeting.java`**:

```java
package greeter;

public class Greeting {
    public static String message() {
        return "Hello from dependency JAR";
    }
}
```

### Step 2: Create the Application Class

File **`src/app/Main.java`**:

```java
package app;

import greeter.Greeting;

public class Main {
    public static void main(String[] args) {
        System.out.println(Greeting.message());
    }
}
```

The `Main` class uses `greeter.Greeting`, but this class resides in a separate library. Therefore, the library needs to be compiled and packaged first.

### Step 3: Compile the Library

At the `project` root directory, create the output directories:

**macOS/Linux:**

```bash
mkdir -p lib-classes lib out
```

**Windows PowerShell:**

```powershell
New-Item -ItemType Directory -Force lib-classes, lib, out | Out-Null
```

Compile the library class:

```bash
javac -d lib-classes lib-src/greeter/Greeting.java
```

After compiling, the class is generated at:

```text
lib-classes/
  greeter/
    Greeting.class
```

The `-d lib-classes` option specifies the root directory containing the compilation output. `javac` automatically creates subdirectories corresponding to the `greeter` package.

### Step 4: Package into a JAR

Run:

```bash
jar --create --file lib/greeter.jar -C lib-classes .
```

This command creates `lib/greeter.jar` from the contents inside `lib-classes`. The `-C` option changes the working directory of the `jar` command to `lib-classes` before adding the contents.

You can inspect the JAR contents:

```bash
jar --list --file lib/greeter.jar
```

The listing should include the entry:

```text
greeter/Greeting.class
```

### Step 5: Compile the Application with the Classpath

Run from the `project` root directory:

```bash
javac -cp lib/greeter.jar -d out src/app/Main.java
```

At this point, `javac` searches for the `greeter.Greeting` class inside `lib/greeter.jar` to check the `Greeting.message()` call.

The application class is generated at:

```text
out/
  app/
    Main.class
```

If the `-cp lib/greeter.jar` option is omitted, the compiler cannot find the `greeter.Greeting` class and typically reports errors like `package greeter does not exist` or `cannot find symbol`.

### Step 6: Run the Application

The runtime classpath must include both the directory containing the application class and the library JAR.

**Windows:**

```powershell
java -cp "out;lib\greeter.jar" app.Main
```

**macOS/Linux:**

```bash
java -cp "out:lib/greeter.jar" app.Main
```

Expected output:

```text
Hello from dependency JAR
```

This example illustrates two separate classpaths:

- At compile time: `javac -cp lib/greeter.jar ...` to find library classes.
- At runtime: `java -cp "out;lib/greeter.jar" ...` on Windows or `java -cp "out:lib/greeter.jar" ...` on macOS/Linux to find both application and library classes.

The classpath used during compilation is not automatically saved into `.class` files. The JVM needs to be provided with the classpath at runtime, or the application needs to be packaged and launched using another mechanism that declares the appropriate library paths.

## 5. Difference Between Classpath and Sourcepath

Classpath and source path serve two related but distinct purposes:

- **Classpath (`-cp`, `--class-path`):** where to find compiled classes and libraries.
- **Source path (`-sourcepath`):** where to find `.java` source files that the compiler needs to compile additionally.

If `-sourcepath` is not specified, the classpath can also be used to search for dependent source code. When specifying a separate source path, include the necessary source directories in it.

For example, if a dependent library has its source code in `lib-src` and has not been packaged into a JAR yet, you can use:

```bash
javac -sourcepath lib-src -d out src/app/Main.java
```

In that case, `javac` can find `greeter/Greeting.java` in `lib-src` and compile the dependent class as needed.

In this scenario, a pre-built JAR for the `greeter` library is not needed. However, for large projects, explicitly compiling all source code or using a build tool usually helps control dependencies and outputs more clearly.

You can specify both the classpath and the source path:

```bash
javac -cp lib/external.jar -sourcepath src:lib-src -d out src/app/Main.java
```

The separator in the example above is the macOS/Linux colon. On Windows, use a semicolon between source path entries.

## 6. Using a Directory of Compiled Classes as a Dependency

A classpath does not have to be a JAR. A directory containing `.class` files can also be used as a dependency.

With the structure:

```text
project/
  library-classes/
    greeter/
      Greeting.class
  src/
    app/
      Main.java
```

Compile the application:

```bash
javac -cp library-classes -d out src/app/Main.java
```

`javac` searches for `greeter/Greeting.class` relative to the root directory `library-classes`.

At runtime, both `out` and `library-classes` need to be added to the classpath.

**Windows:**

```powershell
java -cp "out;library-classes" app.Main
```

**macOS/Linux:**

```bash
java -cp "out:library-classes" app.Main
```

This approach is useful when modules are built into separate directories before being packaged into JARs.

## 7. Using Wildcards to Add Multiple JARs

When a directory contains multiple libraries, you can use the `*` wildcard to include all JAR files directly inside that directory in the classpath.

Example:

```bash
javac -cp "lib/*" -d out src/app/Main.java
```

A few points to keep in mind:

- The wildcard `lib/*` includes JAR files inside the `lib` directory.
- It does not search recursively into subdirectories.
- The `lib` directory must exist and contain the required JARs.
- Enclosing the value in quotes prevents the shell from expanding `*` before passing it to the Java tool.
- You should not rely on the order in which JARs are loaded by a wildcard if there are classes with duplicate names.

You can combine the current directory and JARs:

**Windows:**

```powershell
javac -cp ".;lib\*" -d out src\app\Main.java
```

**macOS/Linux:**

```bash
javac -cp ".:lib/*" -d out src/app/Main.java
```

Wildcards are convenient for experimentation or consistently managed library directories. For production builds, let Maven, Gradle, or a build tool generate the exact classpath from declared dependencies.

## 8. Classpath Order and Duplicate Classes

When the classpath contains multiple entries, the JVM and compiler search for classes in the order the entries are listed. If two JARs both contain a class with the same fully qualified name, the entry that appears first may be used.

Example on macOS/Linux:

```bash
javac -cp "lib/v2.jar:lib/v1.jar" -d out src/app/Main.java
```

On Windows, use a semicolon:

```powershell
javac -cp "lib\v2.jar;lib\v1.jar" -d out src\app\Main.java
```

If both JARs contain `com.example.Helper`, the classpath order can change which version of the class is selected. This easily causes hard-to-trace bugs, especially when the API differs between the two versions.

To avoid conflicts:

- Remove duplicate dependency versions.
- Use Maven/Gradle's dependency tree to find the source of libraries.
- Avoid putting both old and new versions of a library on the classpath.
- Do not rely on wildcard ordering when multiple JARs contain classes with duplicate names.

## 9. Classpath and Module Path

Since Java 9, the Java platform has had a module system. Classpath and module path are not equivalent.

| Criterion | Classpath | Module path |
| --- | --- | --- |
| javac option | `-cp`, `--class-path` | `-p`, `--module-path` |
| Primary unit | Classes and packages | Modules |
| Module descriptor | Does not require `module-info.java` | Modules can declare `module-info.java` |
| Access relationship | Classes on the classpath belong to the unnamed module | Modules have boundaries and reads/exports rules |
| Suitable for | Traditional classpath applications and libraries | Applications/modules using the Java Platform Module System |

If a project uses modules, read `javac`'s guide on `--module-path`, `--module-source-path`, and how to compile modules. Do not put all dependencies on the classpath just because `-cp` is easier to use; doing so can change how the module system handles libraries.

## 10. Common javac Options Used with Classpath

| Option | Purpose |
| --- | --- |
| `-cp` / `--class-path` | Specifies where to find classes and libraries |
| `-sourcepath` | Specifies where to find dependent source code |
| `-d` | Specifies the root directory for output `.class` files |
| `-encoding` | Specifies the encoding of source files |
| `--release` | Specifies the target Java platform version |
| `-verbose` | Displays detailed information about compilation and class loading |
| `-implicit:none` | Does not generate class files for implicitly compiled sources |

Example combining options:

```bash
javac --release 17 -encoding UTF-8 -cp "lib/*" -d out src/app/Main.java
```

The command uses a JDK that supports `--release 17`, reads UTF-8 source code, searches for dependencies in the JARs inside `lib`, and writes the compiled classes to `out`.

The `--release` option does not replace the classpath. It controls the Java platform version the code is compiled for; the classpath still determines where to find dependent libraries.

## 11. Common Errors When Configuring the Classpath

| Error or symptom | Common cause | Solution |
| --- | --- | --- |
| `package ... does not exist` | Missing dependency JAR/directory or incorrect classpath path | Verify the JAR contains the package and add the correct entry to `-cp` |
| `cannot find symbol` | Missing class, wrong import/class name, or library version lacks the called API | Verify the dependency and its version |
| Compiles successfully, but running throws `ClassNotFoundException` | Runtime classpath is missing a library or the output directory | Add both the compiled classes directory and required JARs to `java -cp` |
| `NoClassDefFoundError` | Required class is missing at runtime or class initialization failed | Check the root cause and runtime classpath; check transitive dependencies |
| Library is in the directory, but javac cannot find it | Provided the package directory instead of the root directory, wrong JAR name, or wildcard not passed properly | Inspect the JAR structure with `jar --list` and check the `-cp` value |
| Multi-entry classpath does not work on Windows | Used a colon instead of a semicolon | Use `;` to separate entries on Windows |
| Multi-entry classpath does not work on macOS/Linux | Used a semicolon instead of a colon | Use `:` to separate entries |
| Program loads the wrong library version | Multiple JARs contain the same class and classpath order is unintended | Remove duplicate dependencies and check the classpath order |

### How to Diagnose

When you are unsure where the compiler is searching for classes, try:

```bash
javac -verbose -cp "lib/*" -d out src/app/Main.java
```

Verbose output helps you observe the class searching and loading process. You can combine it with `jar --list --file lib/helper.jar` to check whether the library contains the expected class paths.

Check each factor in order:

1. The package name in the source code.
2. The package path inside the directory or JAR.
3. Whether the classpath points to the correct root directory/JAR.
4. Whether the library version contains the class and method being used.
5. Whether the runtime classpath has all the same dependencies as the compile-time classpath.

## 12. Best Practices for Managing the Classpath

- Declare dependencies explicitly with specific versions.
- Use paths relative to the project directory or classpaths generated by a build tool.
- Do not rely on a global `CLASSPATH` on your development machine.
- Separate the source code directory, output class directory, and library directory.
- Keep compile-time and runtime classpaths compatible with each other.
- Avoid placing multiple versions of the same library on the classpath.
- Do not put untrusted libraries on the classpath; code inside a library can execute in the application process.
- For projects with many dependencies, prefer Maven or Gradle to resolve dependencies and generate a consistent classpath.
- If using Java modules, configure the module path instead of assuming all libraries belong on the classpath.

## 13. Key Takeaways

- The classpath is a list of directories, JARs, or ZIPs where Java tools search for classes.
- Use `javac -cp`, `-classpath`, or `--class-path` to declare dependencies during compilation.
- Use `-d` to set the root directory for generated class files.
- Use `-sourcepath` when you need to explicitly specify where to find dependent source code.
- Use `-cp` for `java` at runtime as well; the compile-time classpath is not automatically saved into class files.
- Windows separates classpath entries with `;`; macOS/Linux uses `:`.
- You can use `lib/*` to add JARs directly inside a directory.
- The classpath is different from the module path; choose the right mechanism based on your project structure.

Once you understand the classpath, you can compile Java programs that depend on external libraries, diagnose missing-class errors, and precisely control which dependencies the compiler and JVM use.
