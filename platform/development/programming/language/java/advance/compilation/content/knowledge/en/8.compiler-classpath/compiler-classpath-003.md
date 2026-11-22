# Distinguishing \`import\` from Classpath Configuration in Java

When a Java file needs to use a class from another package, beginners often write \`import\` and assume the compiler will automatically find or download the library. Conversely, some people add a JAR to the classpath yet the code still reports \`cannot find symbol\` because a class name is used without being declared or imported properly. These two mechanisms address **two different questions**:

- **\`import\`** is a declaration in **source code** that lets Java refer to a type or \`static\` member by its **simple name** instead of having to write the fully qualified name.
- **Classpath** is configuration for the **compiler and launcher** that tells them where to look for the class definitions and resources needed when compiling/running an application that does not use named modules under JPMS.

An easy sentence to remember: **\`import\` helps write names; the classpath helps find the class's code**. Both may be needed in a project, but the presence of one does not automatically create the other.

## 1. Class Name, Package, Import, and Classpath

Suppose we have the class:

~~~java
package library;

public final class Greeting {
    private Greeting() {}

    public static String message(String name) {
        return "Xin chào, " + name + "!";
    }
}
~~~

The class has the **simple name** \`Greeting\`; its full package-qualified name is \`library.Greeting\`. If a file in package \`app\` wants to use this class, there are two ways to write it.

**Using \`import\` to shorten the name:**

~~~java
package app;

import library.Greeting;

public class Main {
    public static void main(String[] args) {
        System.out.println(Greeting.message("Mai"));
    }
}
~~~

**Without \`import\`, using the fully qualified name:**

~~~java
package app;

public class Main {
    public static void main(String[] args) {
        System.out.println(library.Greeting.message("Mai"));
    }
}
~~~

Both ways are valid **if \`library.Greeting\` exists and is accessible during compilation**. Changing how the name is written does not affect whether the class exists in the library.

In both ways, \`javac\` still must find the definition of \`library.Greeting\`: from specified sources / sources found according to source path rules, from class files on the classpath, or via an appropriate module mechanism. A single line \`import library.Greeting;\` **is not a directive to download a library from the network or add a JAR to the classpath**.

## 2. What Does \`import\` Actually Do?

The Java Language Specification (JLS) specifies that an import declaration lets you use a simple name to refer to an accessible type or static member. \`import\` is analyzed by the compiler when processing a **compilation unit** (the source file being compiled).

| Syntax | Effect in source code | Adds a library to the classpath? |
| --- | --- | --- |
| \`import java.util.List;\` | Allows writing \`List\` instead of \`java.util.List\` | No |
| \`import java.util.*;\` | Allows using simple names of matching types in package \`java.util\` when needed | No |
| \`import static java.lang.Math.max;\` | Allows calling \`max(3, 5)\` when there is no name conflict | No |
| \`import static java.lang.Math.*;\` | Brings eligible static members into name lookup scope | No |
| No import, writing \`java.util.List<String>\` | Uses the fully qualified name directly | No |

Important points:

1. **\`import\` does not copy code** of a class into the source file, does not unpack JARs, does not download Maven dependencies, and does not change how the JVM finds classes at runtime.
2. **The scope of an import is the source file containing that declaration**; it does not automatically apply to every file in the same package. Two files in package \`app\` still need their own imports if they need simple names from another package.
3. **Import does not grant extra access permissions.** A \`package-private\` class in another package still cannot be accessed merely because an import was written; in a named module, a non-\`exports\` package also does not become public through import.
4. **Import is not mandatory** if using a fully qualified name, yet both ways require the compiler to be able to find and access the type.
5. Types in the **same package** can usually be referred to by simple name without importing. Eligible types in **\`java.lang\`** also have an implicit import-on-demand mechanism per the JLS; for example \`String\`, \`System\`, \`Math\`.

An easy-to-see example with the standard library:

~~~java
import java.util.ArrayList;
import java.util.List;

public class BasicImport {
    public static void main(String[] args) {
        List<String> names = new ArrayList<>();
        names.add("Lan");
        System.out.println(names.get(0));
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac -d out BasicImport.java
java -cp out BasicImport
~~~

Result:

~~~text
Lan
~~~

In this example, the \`java.util\` classes belong to the Java platform provided by the JDK, so no external JAR needs to be added. **You should not infer that every package in \`import\` is built into the JDK.**

### 2.1. Import-on-Demand Does Not Search Every Subpackage

The declaration:

~~~java
import java.util.*;
~~~

does not mean automatically importing every class belonging to subpackages such as \`java.util.concurrent\`. To use \`ExecutorService\` by simple name, an appropriate import is needed:

~~~java
import java.util.concurrent.ExecutorService;
~~~

or use the full \`java.util.concurrent.ExecutorService\`.

The \`*\` in import-on-demand is a **language naming rule**, not a classpath path wildcard and not a glob traversing an entire JAR.

### 2.2. Import Cannot Rescue a Name Conflict

For example:

~~~java
import java.sql.*;
import java.util.*;

// Date d;  // Unclear whether it is java.sql.Date or java.util.Date
~~~

Both packages provide a type named \`Date\`, so the simple name becomes ambiguous in this context. Use a fully qualified name such as \`java.time.LocalDate\` or \`java.util.Date\`/\`java.sql.Date\` as intended, or add a valid single-type import to specify explicitly. Modifying the classpath is not the way to resolve a name conflict in this example.

### 2.3. Static Import Also Does Not Load a Library

~~~java
import static java.lang.Math.max;

public class StaticImport {
    public static void main(String[] args) {
        System.out.println(max(3, 5));
    }
}
~~~

Execution result:

~~~text
5
~~~

\`import static\` only lets you write \`max(...)\` instead of \`Math.max(...)\`. If the static member resides in an external JAR, that JAR must still be present on the appropriate class search path.

## 3. What Is the Classpath?

Classpath, short for **class search path**, is the list of locations that Java tools can use to find classes and resources under the classpath mechanism. An entry in the classpath is typically:

- **The root directory of a package tree** containing \`.class\` files.
- **A \`.jar\` file** (or compatible ZIP) containing class/resource entries.
- **Multiple entries** joined using the operating system's separator.

Example of a class output directory:

~~~text
out/
└── library/
    └── Greeting.class
~~~

To find a class named \`library.Greeting\`, the classpath needs to contain **\`out\`**, which is the **root of the package tree**, not \`out/library\`. From the classpath root \`out\`, the tool can look up a name of the form \`library/Greeting.class\`.

With a JAR:

~~~text
greeting.jar
└── library/Greeting.class
~~~

The classpath must reference the **JAR file**, for example \`-cp greeting.jar\`, or use a JAR wildcard inside the directory containing it when searching multiple JARs.

### 3.1. The Two Stages Have Separate Classpaths

**The compile-time classpath** of \`javac\` helps determine the classes/interfaces needed to check source code, method signatures, generic types, and accessibility. **The runtime classpath** of \`java\` helps the JVM/class loader find the bytecode to execute.

These two commands have distinct responsibilities:

~~~bash
javac -cp out/lib -d out/app src/app/app/Main.java
java -cp "out/app:out/lib" app.Main
~~~

In the first command, \`out/lib\` lets **javac** see the library when compiling \`Main.java\`. In the second command, both **out/app** (the main class) and **out/lib** (the dependency) must be present at runtime. The \`:\` character in the \`java\` command above is for **Linux/macOS**; **Windows uses \`;\`**, see section 4.

**Configuring the compiler successfully does not automatically ensure runtime is configured too.** With Java running on the classpath, runtime errors often occur because the runtime classpath is missing a dependency that was present at compile time, or has an incompatible JAR version.

### 3.2. Common Options

| Option | Where used | Meaning |
| --- | --- | --- |
| \`javac -cp PATH\` | Compile time | Where to find compiled dependencies and, by javac's rules, possibly sources if no source path is specified |
| \`javac -classpath PATH\` | Compile time | Synonym for \`-cp\` |
| \`javac --class-path PATH\` | Compile time | Longer spelling |
| \`java -cp PATH Main\` | Runtime | Where the launcher looks for the main class and classpath dependencies |
| \`java --class-path PATH Main\` | Runtime | Longer spelling |
| \`javac -d out\` | Compile time | Where to write output class files; does not replace \`-cp\` |
| \`javac --source-path src\` | Compile time | Where to find additional source files via the source path mechanism; distinct from the class file classpath |
| \`java --module-path PATH -m module/class\` | JPMS runtime | Search path for named modules, which is a different mechanism from the regular classpath |

The path in \`-cp\` can consist of multiple directories/JARs. Separator characters:

- **Linux/macOS:** colon \`:\`, for example \`"out/app:out/lib"\`.
- **Windows:** semicolon \`;\`, for example \`"out/app;out/lib"\`.

On Windows PowerShell, wrap the classpath list in quotes so that \`;\` is not treated by the shell as a command separator. When running cross-platform shell scripts, configure the separator appropriate for the operating system.

## 4. Full Example: Correct Import Without a Classpath Still Fails

This is the core hands-on exercise, using Java 17+. Project structure:

~~~text
demo/
└── src/
    ├── lib/
    │   └── library/
    │       └── Greeting.java
    └── app/
        └── app/
            └── Main.java
~~~

Create **src/lib/library/Greeting.java**:

~~~java
package library;

public final class Greeting {
    private Greeting() {}

    public static String message(String name) {
        return "Xin chào, " + name + "!";
    }
}
~~~

Create **src/app/app/Main.java**:

~~~java
package app;

import library.Greeting;

public class Main {
    public static void main(String[] args) {
        System.out.println(Greeting.message("Mai"));
    }
}
~~~

Run from the **demo** directory. First compile the library separately:

~~~bash
javac -d out/lib src/lib/library/Greeting.java
~~~

At this point:

~~~text
out/
└── lib/
    └── library/
        └── Greeting.class
~~~

### 4.1. Try Compiling the App Without Passing the Library to the Classpath

Assuming there is no copy of \`library.Greeting\` on the default classpath, run:

~~~bash
javac -d out/app src/app/app/Main.java
~~~

The command **fails to compile**, even though the Main file has the line \`import library.Greeting;\`. The compiler cannot find the package/type \`library.Greeting\` in the configured search locations. The message may contain:

~~~text
package library does not exist
cannot find symbol
~~~

This is an **illustration of part of the error message**, not the entire immutable stderr across every javac version. An environment that already sets \`CLASSPATH\` or has remaining sources/classes in default locations can yield different results; therefore, in hands-on practice, use clean directories and know your machine's classpath clearly.

### 4.2. Add the Classpath at the Compile Step

~~~bash
javac -cp out/lib -d out/app src/app/app/Main.java
~~~

This command **compiles successfully**. Javac sees \`out/lib/library/Greeting.class\`, verifies the method \`Greeting.message(String)\`, and writes \`out/app/app/Main.class\`.

If you are on **Linux/macOS**, run:

~~~bash
java -cp "out/app:out/lib" app.Main
~~~

If you are on **Windows PowerShell or CMD**, run:

~~~powershell
java -cp "out/app;out/lib" app.Main
~~~

Both produce stdout:

~~~text
Xin chào, Mai!
~~~

The name passed to \`java\` is **\`app.Main\`**, not the file path \`app/Main.class\`. The classpath brings the tool to the package root; the class name syntax uses dots following the package name.

### 4.3. Missing Dependency at Runtime Even Though Compile Succeeded

Keep the freshly compiled class output, but **remove the library** from the runtime classpath:

~~~bash
java -cp out/app app.Main
~~~

The launcher can find \`app.Main\` from \`out/app\`, yet when the \`main\` method needs \`library.Greeting\`, the class loader has no path to find \`Greeting.class\`. This specific case typically fails with **NoClassDefFoundError** involving \`library/Greeting\` (the root cause is a missing dependency at runtime).

You need to fix the **runtime classpath**, not change \`import\`, because the code is already compiled and import has no effect of automatically finding JARs at runtime.

### 4.4. Conversely: Omitting Import Still Runs When the Classpath Is Right

Change **src/app/app/Main.java** to:

~~~java
package app;

public class Main {
    public static void main(String[] args) {
        System.out.println(library.Greeting.message("Mai"));
    }
}
~~~

Recompile:

~~~bash
javac -cp out/lib -d out/app src/app/app/Main.java
~~~

And run with one of the complete runtime commands in section 4.2. The result is still:

~~~text
Xin chào, Mai!
~~~

In this version, **there is no import**. The full name \`library.Greeting\` replaces \`Greeting\`, while the dependency is still on the classpath at compile time and runtime.

**The two experiments above prove the independence between how names are referenced and how bytecode is found:** a correct import can still lack a classpath; a correct classpath still works without an import thanks to fully qualified names.

## 5. What Happens When the Classpath Is Right But Import Is Still Missing?

Change the Main file back to the following version:

~~~java
package app;

public class Main {
    public static void main(String[] args) {
        System.out.println(Greeting.message("Mai"));
    }
}
~~~

The command:

~~~bash
javac -cp out/lib -d out/app src/app/app/Main.java
~~~

still fails to compile: the compiler finds the library on the classpath, but **the simple name \`Greeting\` has not been brought into the usable name scope** in this compilation unit. Javac typically reports \`cannot find symbol\` for \`Greeting\`.

There are two valid fixes:

1. Write \`import library.Greeting;\` after \`package app;\` and before the class declaration.
2. Write \`library.Greeting.message("Mai")\` directly at the usage site.

There is no need to change \`-cp\` because the library search path is already correct. In an IDE, actions like **Organize Imports** or **Add Import** fix the missing-import short-name error, whereas configuring dependencies fixes the missing-library error.

## 6. Using a JAR Instead of a Class Directory

In real projects, libraries are often distributed as JARs. From the section 4 example structure, after compiling \`Greeting.class\`, you can package it using the JDK's \`jar\` tool:

~~~bash
jar --create --file greeting.jar -C out/lib .
~~~

This JAR contains the entry \`library/Greeting.class\`. Then you do not need to put \`out/lib\` on the classpath; use the JAR instead.

Compile the app:

~~~bash
javac -cp greeting.jar -d out/app src/app/app/Main.java
~~~

Run on Linux/macOS:

~~~bash
java -cp "out/app:greeting.jar" app.Main
~~~

Run on Windows:

~~~powershell
java -cp "out/app;greeting.jar" app.Main
~~~

The result is still:

~~~text
Xin chào, Mai!
~~~

Relative paths like \`greeting.jar\` are resolved from the **working directory** where the command is invoked. If you change where the program is run without updating the paths, the classpath may point to the wrong place. The import in \`Main.java\` remains unchanged because the package/class name did not change.

### 6.1. Classpath JAR Wildcard Differs from Import Wildcard

Suppose there is a \`libs\` directory containing \`greeting.jar\` and another JAR. Runtime can use:

~~~bash
# Linux/macOS
java -cp "out/app:libs/*" app.Main
~~~

~~~powershell
# Windows
java -cp "out/app;libs/*" app.Main
~~~

The \`*\` here is a classpath utility supported by the launcher to place **.jar/.JAR files directly inside the libs directory** onto the search path; it does not recursively search subdirectories, and the order in which JARs are expanded is not guaranteed. It is **completely different** from \`import library.*;\`, which only affects how simple names of types in a package are written.

Use a dependency manager or an explicit classpath when JAR versions and loading order matter.

## 7. Default Classpath, CLASSPATH, and Working Directory

If \`-cp\`/\`--class-path\` is not specified, in regular classpath cases \`javac\` and \`java\` may use the **CLASSPATH** environment variable if set; otherwise, the default user classpath is the **current working directory (\`.\`)**. This default explains why a single-file example sometimes runs, whereas the same command in another directory fails.

**Prefer specifying \`-cp\` explicitly** in examples, CI commands, and documentation. This avoids differences between machines when an environment has a pre-existing CLASSPATH configured.

For example:

~~~text
project/
├── out/
│   └── app/
│       └── Main.class
└── src/
    └── app/
        └── Main.java
~~~

If a class with package \`app\` is written under \`out/app/Main.class\`, the classpath root needs to be \`out\`, and the run command is:

~~~bash
java -cp out app.Main
~~~

Running \`java app.Main\` from \`project\` when the default classpath is only \`.\` will not find the file in **out**. Adding \`import app.Main;\` to another source file also will not make the launcher automatically find the class in out.

**Note that a provided \`-cp\` overrides the classpath taken from the CLASSPATH variable**, so if you want both the default location and another library, list the needed entries explicitly.

## 8. Classpath and Sourcepath Are Also Different

When the compiler does not yet have a \`.class\` file for a type but has the corresponding source, javac has a mechanism to find and compile additional sources. Two options serve different search purposes:

- **\`--class-path\` / \`-cp\`**: finds compiled class/JAR dependencies, and under javac's default configuration can be used to find sources if **no** source path is specified.
- **\`--source-path\` / \`-sourcepath\`**: explicitly specifies where to find **additional .java files** when the compiler needs them.

Example of a source root containing:

~~~text
src/
├── app/
│   └── Main.java
└── library/
    └── Greeting.java
~~~

You can compile both sources explicitly:

~~~bash
javac -d out src/library/Greeting.java src/app/Main.java
~~~

Or configure the source path for javac to find additional sources:

~~~bash
javac -sourcepath src -d out src/app/Main.java
~~~

In the second variant, **Main.java** must still reference \`library.Greeting\` via an import or full name as usual. \`-sourcepath src\` helps the compiler find \`src/library/Greeting.java\`. **There is no such thing as sourcepath writing imports automatically**.

Do not treat \`-cp\` as the standard way to build an entire source tree. For large projects, build tools manage source sets, sources to compile, outputs, dependencies, annotation processing, and incremental compilation much better.

## 9. Java Platform, External Libraries, and Build Tools

### 9.1. Why Does java.util Usually Not Need a Separate -cp JAR?

Standard APIs such as \`java.util.List\`, \`java.time.LocalDate\`, and \`java.lang.String\` are provided by the JDK/Java runtime via platform modules. When compiling a program on the **regular classpath**, javac already has access to the appropriate platform APIs that the program is allowed to use.

For example:

~~~java
import java.time.LocalDate;

public class TodayExample {
    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2026, 10, 28);
        System.out.println(date);
    }
}
~~~

Compile/run:

~~~bash
javac -d out TodayExample.java
java -cp out TodayExample
~~~

Stdout:

~~~text
2026-10-28
~~~

No external JAR outside the project needs to be added for \`java.time\`. But with a third-party library package, for example \`com.vendor.client\` provided by an external dependency, **importing that name alone is not enough**: the actual dependency must be provided to compile and runtime in an appropriate manner.

### 9.2. Maven/Gradle Connects Dependencies to the Compiler

In projects using Maven or Gradle, programmers typically declare dependencies in build configuration instead of hand-writing long \`-cp\` strings. The build tool resolves artifacts, configures class/JAR search paths per scope, and passes them to the compiler or run tasks.

**Gradle Java plugin (illustrating build.gradle configuration):**

~~~groovy
plugins {
    id 'java'
}

dependencies {
    implementation 'org.example:library-name:1.2.3'
}
~~~

This is **illustrative code**, using hypothetical artifact coordinates to show Gradle structure; it does not assert that such an artifact exists in a repository. When using a real project, substitute a valid dependency and a configured repository. \`implementation\` typically places the dependency on the compilation/runtime classpath of the main source set per the Java plugin configuration, though the exact effect on consumer APIs also depends on packaging and plugins.

After declaring a valid dependency, a source file **still needs an import** if you want to use the simple name of a type in another package. If you write the fully qualified name, the import can be omitted. **Adding an import does not automatically edit build.gradle**, and **adding a dependency does not automatically write imports into each .java file**.

## 10. Classpath Differs from Module Path and requires in JPMS

Since Java 9, the **Java Platform Module System (JPMS)** allows organizing packages into named modules. When a module has \`module-info.java\`, accessing types from another module involves **module readability** and **exports**.

Example illustrating two descriptors, not a full runnable project:

~~~java
// module-info.java of the library module
module example.library {
    exports library;
}
~~~

~~~java
// module-info.java of the application module
module example.app {
    requires example.library;
}
~~~

The application Java file can still write:

~~~java
import library.Greeting;
~~~

However, import does not replace \`requires example.library;\`, does not replace \`exports library;\`, and also does not replace **--module-path** when packaging/launching as named modules. Each mechanism has its own responsibility:

| Mechanism | Question answered |
| --- | --- |
| \`import library.Greeting;\` | "In this source, can I write \`Greeting\` as a short name?" |
| \`-cp path\` | "For a classpath-based program, which classes/JARs are used to compile/run?" |
| \`--module-path path\` | "Which modules can be found to resolve?" |
| \`requires example.library;\` | "Which library modules does the current module read?" |
| \`exports library;\` | "Which package's public types does the library module allow other modules to access?" |

**Being able to find a type does not mean being permitted to access the type.** If a class is package-private or its package is in a named module that does not export to the caller, import cannot bypass access rules. Conversely, proper requires/exports still requires placing the module on the module path or the corresponding module resolution form.

In newer JDKs there is **module import** syntax for some convenience scenarios, yet that is still a name-scoping concept and is not synonymous with downloading dependencies or fixing the classpath; the Java 17+ examples above use standard import syntax.

## 11. Common Errors and How to Distinguish Them

| Symptom | Common cause | What to check |
| --- | --- | --- |
| \`package library does not exist\` during compile | Dependency/source is not at a location where javac finds it | \`-cp\`, \`-sourcepath\`, JAR path, package path |
| \`cannot find symbol: Greeting\` | Simple name is not declared/imported, or compiler cannot find definition | Import/fully qualified name **and** classpath |
| \`class file for ... not found\` | Missing class needed to analyze dependency signatures | Compile classpath, transitive dependency JARs |
| \`Could not find or load main class app.Main\` | Runtime classpath does not contain the right main class or wrong name was passed | Runtime \`-cp\`, classpath root, package, main class name |
| \`NoClassDefFoundError\` at runtime | A class previously referenced cannot be loaded at runtime; may be due to missing JAR or initialization failure | Runtime classpath, root cause in stack trace |
| \`ClassNotFoundException\` | Class-loading API by name cannot find matching class | Fully qualified name, class loader, and runtime classpath |
| \`NoSuchMethodError\` | Class exists at runtime, yet version differs from compile-time API | Duplicate JARs, classpath order, dependency version |
| Ambiguous import on \`Date\` | Name conflict between multiple types with the same simple name | Single-type import or fully qualified name |
| Runs in IDE but fails in terminal | IDE automatically added dependencies/output to classpath | Copy the exact runtime classpath or use a build tool |
| Added JAR to build, yet running \`java -cp out ...\` lacks library | Compile and run classpaths differ | Pass full entries when launching |

Symptoms do not always have a single cause. In particular, \`NoClassDefFoundError\` can be caused by class initialization or another class loader issue, so read the **cause** in the stack trace; do not automatically conclude every \`NoClassDefFoundError\` is due to a missing JAR.

### 11.1. In What Order Should You Check?

If an external class cannot be used:

1. Confirm the **package name and public type** in the source/JAR; do not guess from the JAR name. The file \`Greeting.class\` must lie in the right package tree such as \`library/Greeting.class\`.
2. Determine whether the error is **compile-time** or **runtime**. When javac reports an error, examine the **compile classpath**; when java reports an error, examine the **runtime classpath**.
3. Try using the **fully qualified name** directly in the source. If this compiles cleanly, the previous error may simply be an import/short-name issue.
4. If using the fully qualified name still does not see the type, check the **dependency path, JAR version, accessibility**, and the appropriate source path/module path.
5. Ensure the classpath points to the **package root**, not directly to the class's folder when the class name has a package.
6. If using Maven/Gradle, check the actual dependency path of the source set/task; do not fix individual run commands manually and forget build configuration.
7. When encountering duplicate classes across multiple JARs, inspect the actual artifacts/classpath. Search order can affect which class gets loaded, yet order should not be used to mask version conflicts.

### 11.2. Which Commands Can You Use to Observe?

Depending on project scale:

~~~bash
javac -verbose -cp out/lib -d out/app src/app/app/Main.java
~~~

\`-verbose\` helps observe files/classes processed by javac. The output is multi-line and JDK-dependent, so it is not fixed in this lesson.

~~~bash
java -XshowSettings:properties -version
~~~

This command can display system properties, including information related to \`java.class.path\` in the runtime environment; the exact information depends on the runtime and arguments used.

~~~bash
jar --list --file greeting.jar
~~~

Used to inspect the package path and JAR contents, helping distinguish "the JAR was added" from "the JAR actually contains the needed class".

The commands above are only diagnostic tools. Read the output in your real environment because classpaths, locales, and JDK versions differ.

## 12. Common Misconceptions

1. **"With an import, Java automatically downloads the library."** No. Imports are only analyzed in source; downloading/resolving dependencies belongs to build tools or the JAR provisioning process.
2. **"Adding a JAR to the classpath eliminates the need for import."** Only true if using fully qualified names or if the type is already in name scope. Using simple names from another package usually requires import.
3. **"Once compiled with a classpath, runtime remembers it automatically."** No. The \`javac -cp\` and \`java -cp\` commands are two separate configurations.
4. **"\`import library.*\` puts every JAR on the classpath."** No. The import star only specifies a set of types by package; it does not adjust the class search path.
5. **"The classpath always points to the folder containing the .class file."** It must point to the **root of the package tree**; for \`library.Greeting\`, the relative path searched is \`library/Greeting.class\`.
6. **"\`-d out\` is enough for the compiler to find dependencies."** \`-d\` selects where bytecode is output; \`-cp\` selects where compiled dependencies are found.
7. **"Removing an import changes the bytecode or how the class loader finds JARs."** The two forms \`Greeting\` via import and full \`library.Greeting\` can reference the same type; imports are not stored as a runtime classpath configuration.
8. **"The classpath is the entire dependency mechanism in Java 9+."** Named modules have their own module path, requires/exports, and JPMS rules.
9. **"If it runs in the IDE, every java command will run."** IDEs often compute the compile/run classpath automatically; you must reproduce the configuration when running outside the IDE.
10. **"Changing imports fixes NoClassDefFoundError."** Runtime errors usually involve loading/initializing classes, whereas imports only play a role at compile time.

## 13. Self-Practice Exercises

**Exercise 1: Prove that import does not replace the classpath.** Use the two files **Greeting.java** and **Main.java** from section 4. Compile the library. Try compiling the app without \`-cp out/lib\`, then add \`-cp out/lib\`. Record the difference.

**Exercise 2: Prove that the classpath does not require import.** Delete \`import library.Greeting;\`, and replace the call with \`library.Greeting.message("Mai")\`. Compile/run with the right classpath, and verify stdout remains unchanged.

**Exercise 3: Create a simple-name error.** Keep the classpath right, yet write \`Greeting.message("Mai")\` without an import. Record the \`cannot find symbol\` diagnostic; fix it using one of the two appropriate ways.

**Exercise 4: Distinguish compile and runtime classpaths.** Compile successfully, then run \`java -cp out/app app.Main\` when the library is only in \`out/lib\`. Identify the missing dependency. Then run with both entries.

**Exercise 5: Package a JAR.** Create \`greeting.jar\`, compile the app with \`-cp greeting.jar\`, and run with \`-cp\` containing both app output and the JAR. Check the entry \`library/Greeting.class\` with \`jar --list\`.

**Exercise 6: Reason about wildcards.** Given \`import java.util.*;\`, explain why \`List\` can be used by simple name while \`ExecutorService\` still requires a separate import or fully qualified name.

## 14. Self-Check Questions

- At what stage is \`import\` used by the compiler? What are classpaths used for by javac/java?
- Why does \`import library.Greeting;\` not automatically add \`greeting.jar\` to the dependency list?
- Can a source file use a class from another package without writing an import? How?
- Why does \`javac -cp out/lib\` not guarantee \`java -cp out/app app.Main\` runs successfully?
- For the class \`library.Greeting\` in \`out/lib/library/Greeting.class\`, what must the classpath entry be?
- What is the difference between \`import java.util.*;\` and \`java -cp "libs/*" ...\`?
- Why can \`javac -d out\` and \`javac -cp out\` not replace each other?
- In JPMS, why can \`import\` not replace \`requires\` and \`exports\`?
- If a program only runs in an IDE but fails on the terminal, how will you inspect the compile and runtime classpaths?

## 15. Official References

- **Java Language Specification 21, §7.5 – Import Declarations:** https://docs.oracle.com/javase/specs/jls/se21/html/jls-7.html#jls-7.5
- **Java Language Specification 21, §6 – Names:** https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html
- **Oracle Java 21, The javac Command:** https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html
- **Oracle Java 21, The java Command:** https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html
- **Java Platform Module System, JLS §7.7 – Module Declarations:** https://docs.oracle.com/javase/specs/jls/se21/html/jls-7.html#jls-7.7

**Takeaway:** \`import\` controls **how to refer to the name** of a class or static member within a source file; the classpath controls **where javac and java look for classes/JARs**. Their errors must be handled in the right place: if an import is missing, fix the reference name; if a compile/runtime dependency is missing, fix the class search path configuration.