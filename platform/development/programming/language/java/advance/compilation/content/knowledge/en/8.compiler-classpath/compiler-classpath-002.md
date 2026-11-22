# Using Class Directories and JAR Files as Dependencies

A Java program rarely consists of just one class. A `Main` class may call `NumberUtils` written by your team, a class from an external library, or multiple precompiled components. To **compile** code that references those classes, `javac` needs to know where to find the declared types/methods; to **run** the program, the JVM also needs to find the corresponding dependency classes.

**Classpath** is the list of locations that Java tools use to find classes and resources on the class path. For code running in the **unnamed module** under the traditional classpath mechanism, each entry is typically **a root directory of `.class` files** or **a JAR file**. This lesson practices both forms, explains package structure, how to use `-cp`/`-classpath`, and common errors when the compile classpath differs from the runtime classpath.

Running example: a library `demo.tools.NumberUtils` has a doubling method; an application `demo.app.Main` calls that method to print `Kết quả: 14`. You will compile and run the application once using a **class directory**, and then once using a **JAR containing the same class**.

## 1. What Search Roots Make Up the Classpath?

When code uses the class `demo.tools.NumberUtils`, the fully qualified class name is mapped to a relative path:

~~~text
demo.tools.NumberUtils
          |
          v
demo/tools/NumberUtils.class
~~~

Java tools concatenate **each classpath element** with the package-relative path to locate the class file. For example:

~~~text
out/lib/                           <- a classpath root
  demo/
    tools/
      NumberUtils.class

lib/math-utils.jar                 <- another classpath entry
  demo/tools/NumberUtils.class     <- entry inside the JAR
~~~

When passing `out/lib`, the tool looks for `out/lib/demo/tools/NumberUtils.class`. When passing `lib/math-utils.jar`, it looks for the entry `demo/tools/NumberUtils.class` **inside the JAR**.

**Do not pass the directory `out/lib/demo/tools` as the classpath root** if the class has package `demo.tools`. Doing so will make the tool search the wrong path. The classpath element is the **root above the package tree**, not the directory directly containing the final class.

A classpath entry can be:

| Entry | Example | Purpose |
| --- | --- | --- |
| Class directory | `out/lib` | Find classes and resources following the package structure under the directory |
| JAR file | `lib/math-utils.jar` | Find class/resource entries inside the archive |
| Multiple entries | `out/app:out/lib` on Unix | Search across the specified locations |
| JAR wildcard | `lib/*` | Includes JARs directly inside the `lib` directory; does not search JARs in subdirectories |

A directory containing multiple JARs **does not automatically place those JARs on the classpath** when you only pass the directory path. To use each JAR, list the corresponding files or use the wildcard `lib/*`.

### The `import` Keyword Does Not Download or Load Libraries

The statement:

~~~java
import demo.tools.NumberUtils;
~~~

allows source code to use the short name `NumberUtils` according to Java's name resolution rules. It **does not download libraries from the Internet, does not add JARs to the classpath, and does not guarantee the class exists**. If there is no corresponding class on the compile classpath (or an appropriate source input for `javac`), you will still get a compilation error.

Maven and Gradle can download dependencies from repositories, but that behavior is performed by the **dependency management tool**. After downloading, they configure the classpath for the compiler/runtime; `import` is merely a language construct.

## 2. Preparing a Small Project with a Library and an Application

Create the directories/files following this tree, with the exact contents and package names:

~~~text
classpath-demo/
├── libsrc/
│   └── demo/
│       └── tools/
│           └── NumberUtils.java
├── appsrc/
│   └── demo/
│       └── app/
│           └── Main.java
├── out/
│   ├── lib/               (library compilation output)
│   └── app/               (application compilation output)
└── lib/                   (location holding the JAR after packaging)
~~~

The directories `out/lib`, `out/app`, and `lib` are output/artifact directories; before running `javac -d`/`jar --file` commands, they must exist. In a Unix/macOS shell, from the `classpath-demo` directory you can run:

~~~sh
mkdir -p out/lib out/app lib
~~~

On Windows PowerShell, if the directories do not exist yet, you can create them with:

~~~powershell
New-Item -ItemType Directory -Force out/lib, out/app, lib | Out-Null
~~~

The two commands above are OS-specific options; **you do not need to run both**. To create `libsrc/demo/tools` and `appsrc/demo/app`, you can use an IDE/editor to create packages, or create the directories before saving the source files. All subsequent commands run from the `classpath-demo` root.

**File `libsrc/demo/tools/NumberUtils.java`:**

~~~java
package demo.tools;

public final class NumberUtils {
    private NumberUtils() {
    }

    public static int doubleOf(int number) {
        return number * 2;
    }
}
~~~

This class is `public`, and the method `doubleOf` is `public static` so application code in another package can call it directly without creating a `NumberUtils` object. The `private` constructor prevents unnecessary instantiation.

**File `appsrc/demo/app/Main.java`:**

~~~java
package demo.app;

import demo.tools.NumberUtils;

public class Main {
    public static void main(String[] args) {
        int input = 7;
        int result = NumberUtils.doubleOf(input);
        System.out.println("Kết quả: " + result);
    }
}
~~~

`Main` and `NumberUtils` are two classes in two different packages. `Main` has a **compile-time** dependency on the declaration `NumberUtils.doubleOf(int)` and has a **runtime** dependency on the matching bytecode of `NumberUtils`.

## 3. Method 1: Using a Directory Containing `.class` Files as a Dependency

### Step 1 — Compile the library

~~~sh
javac -encoding UTF-8 -d out/lib libsrc/demo/tools/NumberUtils.java
~~~

`-d out/lib` tells the compiler to place the build output into that output directory while creating the package structure inside. Main result:

~~~text
out/lib/
└── demo/
    └── tools/
        └── NumberUtils.class
~~~

At this point, the application has not been compiled yet. `out/lib` is the **classpath root** of the library class.

### Step 2 — Compile the application with the library directory

~~~sh
javac -encoding UTF-8 -cp out/lib -d out/app appsrc/demo/app/Main.java
~~~

In this command:

- `-cp out/lib` (equivalent to `-classpath out/lib`) tells `javac` where to find the declaration of `demo.tools.NumberUtils`.
- `-d out/app` places `Main.class` into `out/app/demo/app/`.
- `appsrc/demo/app/Main.java` is the application source file being compiled.
- The compiler uses the compiled library class; this command **does not package the library into `Main.class`**.

Main result:

~~~text
out/
├── lib/
│   └── demo/tools/NumberUtils.class
└── app/
    └── demo/app/Main.class
~~~

### Step 3 — Run the application with both classpath roots

The separator between **classpath elements** depends on the operating system. On Linux/macOS, use a colon `:`:

~~~sh
java -cp "out/app:out/lib" demo.app.Main
~~~

On Windows (Command Prompt or PowerShell), use a semicolon `;`:

~~~powershell
java -cp "out/app;out/lib" demo.app.Main
~~~

Run **one** command appropriate for your environment. Result:

~~~text
Kết quả: 14
~~~

Because `demo.app.Main` is in `out/app` and `demo.tools.NumberUtils` is in `out/lib`, the JVM needs to see **both roots**. The class name passed to `java` is `demo.app.Main`, not `Main.class` or `out/app/demo/app/Main.class`.

You can swap the order of the two roots in this example because there are no duplicate classes; however, **classpath order can affect which class/resource is found first if duplicate names exist**. Therefore, you should not rely on an arbitrary order of artifacts.

## 4. Method 2: Packaging the Library Class into a JAR

JAR (Java Archive) is a ZIP-based archive format used to group class files, resources, and metadata. In this scenario, we only package the **library**; `Main.class` remains outside in `out/app`.

From the `classpath-demo` root, after compiling the library and creating the `lib` directory, run:

~~~sh
jar --create --file lib/math-utils.jar -C out/lib .
~~~

Explanation:

- `jar --create` creates a new archive.
- `--file lib/math-utils.jar` specifies the output JAR name.
- `-C out/lib .` switches the file-collection context to `out/lib` and includes all contents there into the archive. It does not include the `out/lib` string in each entry's path.
- As a result, the JAR contains `demo/tools/NumberUtils.class` following the correct package structure (and a manifest generated by the tool).

Inspect the entry list:

~~~sh
jar --list --file lib/math-utils.jar
~~~

The list must contain:

~~~text
demo/tools/NumberUtils.class
~~~

The `jar --list` command may print additional entries such as `META-INF/` and `META-INF/MANIFEST.MF`; presentation order is not what we use to determine correctness. If the JAR contains the path `out/lib/demo/tools/NumberUtils.class` instead of `demo/tools/NumberUtils.class`, the packaging is wrong for the expected package and classpath root.

### Compile the application with the JAR instead of the class directory

~~~sh
javac -encoding UTF-8 -cp lib/math-utils.jar -d out/app appsrc/demo/app/Main.java
~~~

Exactly the same application source code; only **the dependency input is changed from the `out/lib` directory to the JAR**. When looking up `demo.tools.NumberUtils`, `javac` reads the entry inside the archive.

Run on Linux/macOS:

~~~sh
java -cp "out/app:lib/math-utils.jar" demo.app.Main
~~~

Run on Windows:

~~~powershell
java -cp "out/app;lib/math-utils.jar" demo.app.Main
~~~

Stdout is still:

~~~text
Kết quả: 14
~~~

**A JAR used as a dependency does not necessarily need to be runnable standalone with `java -jar`.** This library JAR does not need `Main-Class`, because its job is to provide the `NumberUtils` class to the application. Running `java -jar lib/math-utils.jar` is not the right way to test library functionality when the JAR has no application entry point.

### Did we just create a "fat JAR"?

**No.** `lib/math-utils.jar` only contains the library class. `Main.class` is still outside in `out/app`; the runtime classpath still must specify both locations.

A fat/uber JAR (if packaged properly) can bundle multiple classes/dependencies into one artifact, but that is a **different packaging strategy**. In this lesson, what you need to understand is that a JAR can be **a classpath element**, equivalent in class-lookup role to a root directory containing `.class` files.

## 5. Compile Classpath Differs from Runtime Classpath

The following two commands answer two different questions:

| Stage | Example command | What needs to be found? |
| --- | --- | --- |
| Compile time | `javac -cp lib/math-utils.jar -d out/app appsrc/demo/app/Main.java` | Declarations of classes, methods, and types used by `Main.java` |
| Runtime | `java -cp "out/app:lib/math-utils.jar" demo.app.Main` | Actual bytecode for the JVM to load and execute the classes |

`javac` checks the call `NumberUtils.doubleOf(int)` against the compile-time library. But at runtime, the JVM must **look up the class again** from the runtime classpath. `javac` does not copy all dependencies into the application classfile.

Suppose compilation succeeds with the JAR, but you try to run **without the JAR**:

~~~sh
java -cp out/app demo.app.Main
~~~

This command is the same on Windows and Unix because there is only **one** classpath element. The JVM finds `demo.app.Main`, but when code calls `NumberUtils`, the JVM cannot find the library class and may throw an error like:

~~~text
java.lang.NoClassDefFoundError: demo/tools/NumberUtils
~~~

The full message and stack trace depend on the JDK; the key point is that **the library was present at compile time but absent at runtime**. Adding back the classpath containing the library resolves that specific case.

If `Main.java` is compiled without the dependency from the start, you typically see an error such as:

~~~text
package demo.tools does not exist
~~~

or an error related to not finding the symbol `NumberUtils`. That is a **compile classpath** error, different from `NoClassDefFoundError` at runtime.

### Further Distinguishing Common Errors

| Symptom | Possibilities to check |
| --- | --- |
| `package demo.tools does not exist` | The compiler cannot find the package on an appropriate source/classpath |
| `cannot find symbol` for `NumberUtils` | Typo/`import` error, missing class, or the dependency is not on the compile classpath |
| `Could not find or load main class demo.app.Main` | Wrong main class name or missing `out/app` in the runtime classpath |
| `NoClassDefFoundError: demo/tools/NumberUtils` | Code calls the class, but the class is not available to load at runtime; check JAR/root/dependencies |
| `ClassNotFoundException` | Usually related to dynamic class loading via API, or is an underlying cause inside a class-loading error |
| `NoSuchMethodError` | Possibly caused by using a library version at runtime with a different signature than at compile time |
| `UnsupportedClassVersionError` | Runtime does not understand the compiled classfile version |

**Not every `NoClassDefFoundError` has a single cause.** Besides a missing class, a prior class initialization failure can also lead to `NoClassDefFoundError` on subsequent usage. To diagnose accurately, read the entire exception/cause, inspect the artifacts, and check the actual dependencies.

## 6. How to Write Multiple Dependencies Together

When an application has multiple class directories and JARs, classpath entries are joined using the operating system's separator character:

- **Unix/Linux/macOS:** `:`
- **Windows:** `;`

Example on Unix:

~~~sh
javac -cp "out/lib:lib/math-utils.jar" -d out/app appsrc/demo/app/Main.java
java -cp "out/app:out/lib:lib/math-utils.jar" demo.app.Main
~~~

On Windows:

~~~powershell
javac -cp "out/lib;lib/math-utils.jar" -d out/app appsrc/demo/app/Main.java
java -cp "out/app;out/lib;lib/math-utils.jar" demo.app.Main
~~~

In the main example, including **both the directory and the JAR containing the same class** is redundant and can cause version confusion; the commands above only illustrate the syntax when multiple entries are present. In a real project, add only the dependencies needed, avoiding having one class appear in multiple places on the classpath.

### Wildcard for Multiple JARs in One Directory

If the `lib` directory directly contains one or more JAR files, you can use `lib/*` in the classpath. On Unix:

~~~sh
javac -cp "lib/*" -d out/app appsrc/demo/app/Main.java
java -cp "out/app:lib/*" demo.app.Main
~~~

On Windows:

~~~powershell
javac -cp "lib/*" -d out/app appsrc/demo/app/Main.java
java -cp "out/app;lib/*" demo.app.Main
~~~

The double quotes in the examples prevent **the shell from automatically expanding the wildcard** before the Java tool processes it. Java's classpath wildcard applies to JARs directly under the specified directory, does not look for loose classes there, and **does not recurse into subdirectories**. It also does not guarantee an ordering by name when selecting JARs; avoid using wildcards if there are multiple versions of the same class requiring strict control.

**Do not write `-cp lib` and expect the JVM to automatically read all `lib/*.jar`.** `lib` is a root directory classpath, whereas `lib/*` represents the JAR files directly inside it.

### When Do You Need to Add `.`?

If you place the application's classfile directly at a classpath root that is the current working directory, you can specify `.`:

~~~sh
java -cp ".:lib/math-utils.jar" demo.app.Main
~~~

On Windows:

~~~powershell
java -cp ".;lib/math-utils.jar" demo.app.Main
~~~

This is an example of **classpath syntax**; it only finds `demo.app.Main` if the `demo/app/Main.class` structure actually resides under the current directory. With this lesson's directory tree, the `Main` class is in `out/app`, so you must use `out/app` rather than arbitrarily substituting `.`.

When **no `-cp` is provided** and `CLASSPATH` is not configured, the default application classpath is usually the current directory. Once `-cp` is provided, you have specified a new search list; **`.` is not added automatically**. If you need the current directory, add `.` explicitly to the list. A `CLASSPATH` environment variable can take effect when `-cp` is absent; to keep lessons and CI reproducible, prefer explicit configuration.

## 7. Package, Class Name, and Path: Three Elements Must Match

In the example, the statement:

~~~java
package demo.tools;
~~~

makes the library class name `demo.tools.NumberUtils`. With compilation output via `-d out/lib`, the class path is `out/lib/demo/tools/NumberUtils.class`. With a JAR, the entry is `demo/tools/NumberUtils.class`.

Four common mistakes:

1. **Pointing too deep into a directory:** `-cp out/lib/demo/tools` instead of `-cp out/lib` makes the JVM/compiler look up the wrong package path.
2. **Passing a class file path to `java`:** `java out/app/demo/app/Main.class` is not the standard way to invoke the main class; you must use `java -cp out/app demo.app.Main`.
3. **Packaging the outer directory into the JAR:** An archive with the entry `out/lib/demo/tools/NumberUtils.class` will not match the class lookup path `demo/tools/NumberUtils.class`.
4. **Having the right `import` but missing the dependency:** `import` does not create classes; there must be source/class/JAR files on the appropriate search path.

Note that **source file path** and **package-based output path** are two different concepts. The convention `appsrc/demo/app/Main.java` helps humans manage code, whereas `javac -d out/app` determines the layout of output classfiles. Although source can be organized differently in some cases, projects should keep a structure matching packages so build tools and IDEs can understand them easily.

## 8. Non-`.class` Resources Can Also Be on the Classpath

A JAR or classpath directory can contain configuration/resource files. For example, if there is a resource `config/message.txt` under the root `out/lib` or inside a JAR under the entry `config/message.txt`, code using a class loader can read it by the corresponding resource name:

~~~java
try (var in = Main.class.getClassLoader().getResourceAsStream("config/message.txt")) {
    if (in == null) {
        throw new IllegalStateException("Khong tim thay resource");
    }
    // Read the InputStream using the appropriate encoding and format.
}
~~~

This is an **illustrative code snippet placed inside a method that allows throwing/handling exceptions**; it is not a standalone program and is not used in the experiment's `Main` command. It shows that the classpath does not serve only classes. When running for real, resources also need to be placed into the output folder/JAR; a resource existing in `src` does not mean it automatically appears in the compiled artifact.

JARs package resource files according to the exact entry paths. You should not construct a filesystem path to a resource inside a JAR and assume it is always a separate physical file.

## 9. Relationship with Gradle/Maven and JPMS

In large projects, classpaths are rarely written by hand. Maven/Gradle resolves dependencies, downloads artifacts if needed, and provides the appropriate classpath paths for each task.

- **Compile classpath** contains the types/APIs needed to compile source code.
- **Runtime classpath** contains the classes/resources needed when launching and running the application.
- Dependency configurations such as `implementation`, `compileOnly`, `runtimeOnly` (in the Gradle Java plugin) have different meanings for these path sets. Do not assume every dependency present at compile time will be present at runtime.

Example scenario: a library marked `compileOnly` allows code to compile against that API, but the distribution must be configured so the API is present by another means at runtime if the code actually needs it.

Since Java 9, the **Java Platform Module System (JPMS)** added the concept of **module path**. This study example uses the **traditional classpath (unnamed module)**, so `-cp` commands are appropriate. With a **named module** having `module-info.java`, finding dependencies may require `--module-path` and corresponding `requires`. Classpath and module path are not arbitrary names for the same mechanism.

### What About a JAR Passed to `java -jar`?

In the `java -jar app.jar` command, the JVM launches the application based on the main class information in the JAR's manifest; **the application classpath from `-cp` is not applied the same way as when launching by class name**. External dependencies may be declared via the manifest `Class-Path` or resolved through an appropriate launcher/packaging mechanism.

Therefore, the fact that this example runs with:

~~~sh
java -cp "out/app:lib/math-utils.jar" demo.app.Main
~~~

does not mean you can arbitrarily change it to `java -jar lib/math-utils.jar`. That JAR is a **library**, and does not contain the application's main class.

## 10. When Errors Occur, Check Methodically

If building or running fails, perform checks according to the exact stage:

**A. When `javac` reports that a package or class cannot be found:**

1. Check the exact package name and class casing.
2. Check whether the `.class` file exists in the right directory (for example `out/lib/demo/tools/NumberUtils.class`) or is already inside the JAR.
3. Verify the classpath root: pass `out/lib` or `lib/math-utils.jar`, not a nested package directory.
4. Identify which directory you are running `javac` from: all relative paths are resolved relative to the process's working directory.
5. If using a build tool, check that the dependency is declared for the right source set/compile configuration.

**B. When `java` cannot find the main class:**

1. Check that `out/app/demo/app/Main.class` exists.
2. Use the name `demo.app.Main` rather than a path to `.class`.
3. Put the **root `out/app`** on the runtime classpath.
4. Check that the right class has the `public static void main(String[] args)` method in this example.

**C. When main is found but a missing dependency is reported:**

1. Ensure `out/lib` or `lib/math-utils.jar` is in the **runtime classpath**, not only the compile classpath.
2. If passing a JAR, use `jar --list --file ...` to verify entries and package names.
3. Check the dependencies that the library JAR itself needs; a JAR usually does not package all the JARs it depends on.
4. Compare the JAR versions at compile time and runtime; differences can cause linkage errors or behavioral changes.

**D. When the class is right but the application still returns the wrong result:**

The classpath only determines where class/resource definitions are found; it **does not verify that the algorithm is correct**. Once the right class is loaded, test the logic, input data, and runtime configuration.

A simple way to avoid confusing old files in experiments is to clean only the output directories of this lesson and compile sequentially with the exact commands. When working in a repo containing other people's data, only delete artifacts you created and have permission to manage.

## 11. Consolidation Practice

**Exercise 1 — Class directory.** Use the two source files in the lesson, compile the library into `out/lib` and the application into `out/app`. Run with both roots and confirm stdout `Kết quả: 14`. Try removing `out/lib` from the runtime classpath; note the error and explain why compilation succeeded.

**Exercise 2 — JAR.** Create `lib/math-utils.jar`, verify the entry `demo/tools/NumberUtils.class` using `jar --list`. Recompile the application using `-cp lib/math-utils.jar` and run with the JAR on the classpath. Explain why the result does not change.

**Exercise 3 — Wrong root.** Replace `-cp out/lib` with `-cp out/lib/demo/tools` in the application compilation command and predict the error. Point out the path `javac` tries to find given the package and the chosen classpath root.

**Exercise 4 — Multiple dependencies.** Add a new auxiliary JAR directly into `lib`. Compare listing two separate JARs with `lib/*`. Explain why wildcards do not guarantee ordering when two JARs contain the same class.

**Exercise 5 — Environment verification.** Write two equivalent `java -cp` commands for Unix and Windows when there are three roots: `out/app`, `out/lib`, and `lib/math-utils.jar`. Specify the separator characters.

**Exercise 6 — Distinguishing compile and runtime.** Suppose the build passes, yet `java` reports `NoClassDefFoundError` for `NumberUtils`. Identify the first three places to check and propose the correct run command for the current directory tree.

### Self-Assessment Questions

1. **What is the classpath root of `demo.tools.NumberUtils` in `out/lib/demo/tools/NumberUtils.class`?** — `out/lib`.
2. **Why can a JAR serve as a dependency even without `Main-Class`?** — It only needs to provide classes/resources to another program; it is not a self-running application.
3. **Does `import` make Maven/Gradle download libraries?** — No; dependencies are handled by build configuration and management tools.
4. **Why is a dependency needed at runtime even though it was present at compile time?** — `javac` checks/compiles using the library, but the JVM must load the actual class during execution.
5. **What character separates classpath entries on Windows?** — `;`; Unix/Linux/macOS uses `:`.
6. **How do `lib` and `lib/*` differ?** — One is a root directory for finding loose classes/resources; the other expands direct JARs inside the directory.
7. **Are the classpath and module path the same?** — No; named modules use JPMS's own mechanism/module descriptors.

**Connecting Knowledge:** Once you understand class directories, JARs, and classpath roots, you can clearly analyze three different failures: **failing to compile due to missing dependencies**, **compiling successfully but the JVM failing to load the class**, and **loading the class but runtime using a different library version**. This is the foundation for working with Java libraries, dependency management, and the packaging/deployment process.