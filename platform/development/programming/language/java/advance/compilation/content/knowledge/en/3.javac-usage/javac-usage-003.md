# Compiling Multiple Files in a Single javac Invocation

## 1. Objective and Use Cases

A Java application rarely consists of only a single `.java` file. The main runnable class may call business logic classes, helper classes located in other packages, or data types that reference one another. When files belong to **the same compilation unit**, `javac` lets you pass multiple source paths in **a single invocation**:

```bash
javac -d out src/demo/core/PriceCalculator.java src/demo/core/Receipt.java src/demo/app/Main.java
```

The files passed into the same invocation are analyzed and compiled by the compiler **as a group**. During name resolution and type checking, `javac` can use declarations from source files in the same group; therefore you do not need to compile each file in order of usage, and the order of filenames on the command line does not determine the program's execution order. If no errors occur, `.class` files are generated for use on the JVM.

After this lesson, you can:

- Compile multiple files in the same package or different packages simultaneously, then run the exact class containing `main`.
- Distinguish explicitly listed sources, sources found via `--source-path`, and `.class`/JAR libraries on the classpath.
- Use `@argfile` when the source list is long; understand where paths are resolved relative to.
- Identify "cannot find symbol" errors, duplicate classes, wrong packages, missing dependencies, stale outputs, and the difference between a single compiler invocation and an incremental build system.
- Choose a stable command organization for small projects, scripts, and CI.

**Scope:** the main examples use a Java project without module declarations (`module-info.java`), runnable on JDK 17 and later. Multi-module JPMS projects have additional `--module-source-path` and `--module-path` rules, which are distinguished in a later section.

## 2. Basic Syntax: Multiple Source Files, One javac Process

```text
javac [options] SourceA.java SourceB.java SourceC.java ...
```

Each source argument is a path to a `.java` file. For example:

```bash
javac Alpha.java Beta.java Gamma.java
```

Without `-d`, the compiler by default places `.class` files in the directory containing the corresponding source file. For projects with packages, place the output in a separate directory:

```bash
javac -d out Alpha.java Beta.java Gamma.java
```

`-d out` instructs `javac` to organize output files by package under `out`; `javac` creates the destination directory and necessary package directories if they do not exist. This separates sources from artifacts. When running a program belonging to the unnamed module, put the **output root directory** on the classpath using `java -cp out <fully.qualified.class.name>`.

One command with three source files is **not equivalent** to three separate compiler invocations:

```bash
# Single invocation: the compiler sees the three specified sources at the same time
javac -d out Alpha.java Beta.java Gamma.java
```

```bash
# Three invocations: each command has its own separate environment seeing sources/class files
javac -d out Alpha.java
javac -d out Beta.java
javac -d out Gamma.java
```

With separate commands, each invocation must locate the types referenced by the source through the specified sources themselves, the classpath, or the source path. The result may depend on `.class` files generated in the previous step, and **`-d out` does not automatically add `out` to the compile classpath of a non-modular project**. By contrast, a single group invocation allows source declarations to support one another without manually ordering files.

## 3. Complete Example: Three Files, Two Packages, One Command

Suppose we have the directory structure:

```text
compile-together/
└── src/
    └── demo/
        ├── app/
        │   └── Main.java
        └── core/
            ├── PriceCalculator.java
            └── Receipt.java
```

### File 1 — `src/demo/core/PriceCalculator.java`

```java
package demo.core;

public final class PriceCalculator {
    private PriceCalculator() {
    }

    public static int total(int quantity, int unitPrice) {
        return quantity * unitPrice;
    }
}
```

This class provides the calculation. Because it has `public`, the file name must match the class name `PriceCalculator`.

### File 2 — `src/demo/core/Receipt.java`

```java
package demo.core;

public final class Receipt {
    private Receipt() {
    }

    public static String format(int quantity, int unitPrice) {
        int total = PriceCalculator.total(quantity, unitPrice);
        return quantity + " x " + unitPrice + " = " + total;
    }
}
```

`Receipt` uses `PriceCalculator` in the same `demo.core` package, requiring no intra-package `import`.

### File 3 — `src/demo/app/Main.java`

```java
package demo.app;

import demo.core.Receipt;

public class Main {
    public static void main(String[] args) {
        System.out.println(Receipt.format(3, 12));
    }
}
```

`Main` is in package `demo.app`, so it imports the public `Receipt` class from package `demo.core`.

### Compiling and Running

Open a terminal in the `compile-together` directory, which contains `src`. Run:

```bash
javac -encoding UTF-8 -d out src/demo/core/PriceCalculator.java src/demo/core/Receipt.java src/demo/app/Main.java
java -cp out demo.app.Main
```

Output of the `java` command:

```text
3 x 12 = 36
```

A successful `javac` invocation normally prints no messages. Expected output after compilation includes:

```text
out/
└── demo/
    ├── app/
    │   └── Main.class
    └── core/
        ├── PriceCalculator.class
        └── Receipt.class
```

Points to understand:

1. `src` is the **source tree root**; `out` is the **class file tree root**.
2. The package names declared in code are `demo.app` and `demo.core`; dots in a package name correspond to subdirectories in the output.
3. All three files are included in the same invocation, so the compiler can link the references `Main → Receipt → PriceCalculator` using declarations from those files.
4. When running, use the fully qualified class name `demo.app.Main`. Calling `java -cp out Main` will fail to find the right class because its binary name includes the package.
5. Adding a source file to the command line only requests compiling that file; it does **not** mean that file's class automatically becomes the entry point. The `main` method must be selected when invoking the `java` command.
6. `-encoding UTF-8` makes explicit how source text is read. If targeting a Java 17 runtime from a newer JDK, you can add `--release 17` according to project compatibility policy.

## 4. Source File Order and Dependency Resolution

Try changing the order of the arguments:

```bash
javac -encoding UTF-8 -d out src/demo/app/Main.java src/demo/core/Receipt.java src/demo/core/PriceCalculator.java
```

Both ways of listing are valid; `javac` compiles the source group together. **There is no need to list a dependency file before the file that uses it.** This is a major difference from designing scripts that run multiple independent `javac` commands.

### Case Where Two Classes Reference Each Other

The following two files can be compiled in the same pass even though each type uses the other file's type name.

`NodeA.java`:

```java
public class NodeA {
    NodeB other;
}
```

`NodeB.java`:

```java
public class NodeB {
    NodeA other;
}
```

```bash
javac -d out NodeA.java NodeB.java
```

Two mutually referencing fields are valid. This is **not** an example of a class inheritance cycle (for instance `A extends B` while `B extends A`), which is a compile-time error. A single group invocation resolves mutual dependency declarations, but it does not make relationships forbidden by Java valid.

Depending on directory location and source lookup configuration, compiling `NodeA.java` alone sometimes succeeds too because `javac` finds `NodeB.java` on its own. Therefore, you should not claim that "compiling a single file always fails"; check the exact **source path/classpath** at invocation time.

## 5. Three Ways for javac to See Dependent Types

When encountering `import demo.core.Receipt;` or a type reference, the compiler must locate its declaration. There are three common paths:

| Provision Method | Example | Meaning |
| --- | --- | --- |
| **Directly list source files** | `javac -d out A.java B.java` | Both `A.java` and `B.java` are input sources of the same invocation |
| **Place additional sources on source path** | `javac --source-path src -d out src/demo/app/Main.java` | Allows the compiler to find dependent sources under the `src` tree by package |
| **Place binaries/JARs on classpath** | `javac -cp out -d other-out Consumer.java` | Uses already-compiled types without requiring every original source to be recompiled |

### 5.1. Explicit Listing — Easy Scope Control

For the three-file example, the safest and most readable approach is the command in section 3. Especially when annotation processors are present or when you need to know the exact set of sources being built, an explicit list reduces discrepancies caused by implicit file discovery.

### 5.2. `--source-path` — Discovering Additional Source Files

You can start with `Main.java` and tell the compiler the source tree containing the other types:

```bash
javac -encoding UTF-8 -d out --source-path src src/demo/app/Main.java
```

Because `Receipt.java` and `PriceCalculator.java` are in the proper package locations under `src`, `javac` can find and compile them as dependent sources when needed. By default, `javac` may generate class files for implicitly discovered sources; `-implicit:none` can disable generating those class files. If the build requires all sources to undergo annotation processing predictably, consider explicitly listing every file to compile.

If you **do not** specify a source path when compiling a non-modular project, the user classpath is also searched for source files. This sometimes makes a command that passes only one file "know about" the remaining files on its own. For stable and reproducible scripts, actively configure the source path or list everything completely, avoiding reliance on accidental working directory behavior.

### 5.3. `-cp` / `--class-path` — Using Already-Compiled Dependencies

If `Receipt` already has a `.class` file under `out` and you want to compile only a client using it:

```bash
javac -cp out -d client-out src/demo/app/Main.java
```

This command uses `out` as a **compile-time classpath**. When running `Main`, you still need to make both the client and the dependencies visible to the JVM. The classpath separator depends on the operating system:

```bash
# Linux/macOS:
java -cp "client-out:out" demo.app.Main
```

```powershell
# Windows PowerShell:
java -cp "client-out;out" demo.app.Main
```

The two commands above are used **after** `PriceCalculator` and `Receipt` have already been compiled into `out`. Note: this is a scenario for using already-compiled dependencies; there is no need to recompile the entire group if dependencies have not changed, but you must ensure the binaries are sufficiently up to date and compatible.

For external JARs, pass the library paths with `-cp` when compiling and use an appropriate classpath when running. `-cp` does not install or download libraries.

## 6. Long File Lists: Argument File `@sources.txt`

Operating systems have command-line length limits. When there are many files, instead of a long hard-to-maintain command, create a file containing the source names:

`sources.txt`:

```text
src/demo/core/PriceCalculator.java
src/demo/core/Receipt.java
src/demo/app/Main.java
```

Then from the `compile-together` directory:

```bash
javac -encoding UTF-8 -d out @sources.txt
java -cp out demo.app.Main
```

The output of `java` is still:

```text
3 x 12 = 36
```

`@sources.txt` tells `javac` to read arguments from the file instead of typing them all on the command line. This is still **a single compiler invocation**; the source files are still compiled as a group.

Important rules:

- Each file name can sit on its own line; the arg file can also contain other `javac` options.
- Source paths **inside an argfile** are resolved relative to the **working directory when invoking `javac`**, not the directory containing the argfile. If run from another directory, adjust the paths.
- If a file name or path contains spaces, enclose the **entire name** in double quotes inside the argfile: `"src/demo/my sources/Extra.java"`.
- Do not write `src/**/*.java` or `*.java` in an argfile expecting `javac` to expand wildcards automatically: such wildcard syntax is not supported in argument file lists.
- Do not use `@other-file` inside an argfile to nest argfiles: such recursive expansion is not supported.
- If the source list is generated automatically, it must produce a list of actual paths and properly quote paths containing spaces.

Options can also be included in `compile.args`:

```text
-encoding
UTF-8
-d
out
src/demo/core/PriceCalculator.java
src/demo/core/Receipt.java
src/demo/app/Main.java
```

```bash
javac @compile.args
```

With this example, the output still goes under `out`. When combining `@argfile` with direct arguments, understand that `javac` ultimately receives one expanded list of options and source files, not two compilation passes.

## 7. Selecting File Lists by Environment

### 7.1. Explicit Listing

For small projects or learning materials, explicitly naming the three files as in the example is the least environment-dependent approach.

### 7.2. Shell Wildcards Are Not Equivalent to javac Wildcards

A command such as:

```bash
javac -d out src/demo/core/*.java src/demo/app/Main.java
```

can work in a POSIX shell because **the shell** expands `*.java` into actual files before `javac` receives the arguments. However, when running in PowerShell, CMD, an IDE, or a program invoking `javac` directly, you must not assume the same glob expansion mechanism. This wildcard also selects only files directly inside the `core` directory, rather than automatically scanning the entire `src` tree recursively.

To scan a large project across platforms, use a build tool like Gradle/Maven or write a script that generates a real list of sources and passes it to `javac`. In particular, avoid putting `*` into `@sources.txt` hoping it will be expanded.

### 7.3. Do Not Blindly Compile Every `.java` File

A repository may contain multiple source sets and modules: `src/main/java`, `src/test/java`, sample code, auto-generated code, or multiple independent applications. Combining everything into one command can cause duplicate classes, unconfigured test dependencies, annotation processors running out of scope, or module conflicts. "Compiling multiple files in a single invocation" means passing the **appropriate source group** to the compiler, not compiling every file found under the repository.

## 8. What Does a Compile Command Produce and What Does It Not Do?

Suppose `javac` successfully compiles the three files above. More class files than source files may appear in `out` if the sources also contain nested classes, anonymous classes, or additional types. Thus the number of `.class` files does not always equal the number of `.java` files.

Distinguish:

- **Compile:** check syntax/types and generate class files (`javac`).
- **Run:** choose a class with an appropriate entry point and execute (`java`).
- **Package:** create a JAR or distribution artifact (`jar` or a build tool).
- **Test:** run a test suite, which is not automatically triggered just because compilation succeeded.

`javac` does not execute the `main` methods of the source files. When multiple classes contain `main`, a single compilation can still produce class files for all of them; at runtime you choose the right main class. Successful compilation also does not guarantee that the program will find all dependencies at runtime or will not throw exceptions.

For source files with packages, output file locations are determined by the package name and the `-d` option; placing `out/demo/app/Main.class` on the classpath does **not** mean using `java -cp out/demo/app Main` when the class declares `package demo.app`. The classpath root must be `out`.

## 9. Common Errors and How to Diagnose Them

| Symptom | Possible Cause | Check / Fix |
| --- | --- | --- |
| `cannot find symbol` for a type in another file | Dependent file is not in the group, source path, or classpath; wrong name/package declaration | Check `.java` paths, `package`, `import`, `--source-path`, and `-cp` |
| `package ... does not exist` | Compiler cannot find the required types belonging to that package | List the right source files or add appropriate source/classpath paths |
| `duplicate class` | Multiple definitions with the same binary name in the group or duplicate sources selected by mistake | Remove duplicate files, separate source sets properly; do not merge arbitrary directories |
| File-naming error for `public class` | Source file name does not match the public top-level class | Rename `.java` to match the public type |
| `Could not find or load main class` after compile | Wrong fully qualified name or wrong classpath root | Run `java -cp out demo.app.Main` and confirm `out/demo/app/Main.class` |
| `NoClassDefFoundError` / `ClassNotFoundException` when running | Runtime classpath is missing a dependency or artifact | Provide the right libraries and compiled output in the `java` command |
| `NoSuchMethodError` / `NoSuchFieldError` | Binary dependency is incompatible with the version the client was compiled against | Clean and recompile the relevant modules; check the runtime classpath |
| Old `.class` files remain after a failed build | `javac -d` does not mean clearing old output directories or atomic commits | Build into a clean output directory; check the exit code and discard failed artifacts |
| `@sources.txt` does not find files | Paths inside the argfile are resolved relative to the current working directory | Check `pwd`/working directory and exact file names |
| Paths with spaces get split | Arguments or argfile contents not properly quoted | Wrap paths in double quotes using the appropriate syntax |

**Note on errors and artifacts:** a single `javac` invocation is not an atomic transaction in the filesystem sense. If one or more sources fail, you should not rely on the output directory being guaranteed free of new or old class files. Check `javac`'s exit code and use a clean output directory when you need to verify build results accurately.

**Note on warnings:** `-Xlint` and `-Werror` can be enabled per project policy. These options do not change the nature of "single invocation with multiple sources" but may cause the command to fail when warnings are encountered.

## 10. Repeated Compilation, Incremental Builds, and Reproducibility

The command:

```bash
javac -d out src/demo/core/PriceCalculator.java src/demo/core/Receipt.java src/demo/app/Main.java
```

instructs the compiler to process the source set passed in that invocation; **it does not automatically become a complete dependency management and incremental build system**. `javac` can discover/compile additional sources as configured, but it does not maintain the entire repository task graph, manage test resources, dependency versions, build caches, or delete binaries that no longer correspond to source code.

When changing the signature of `PriceCalculator.total`, files using that method may need to be recompiled. If you run separate commands repeatedly with old `.class` files, you may accidentally compile or run with inconsistent definitions. Compiling the same group from a clean output reduces this problem in small examples. Real projects should let Gradle/Maven define source sets, classpaths, task ordering, and rebuild scope.

To make results reproducible, explicitly record:

1. JDK/compiler version: `javac -version`.
2. Desired API/language/runtime level: for example `--release 17` when building on a supporting JDK.
3. Source list or how the source list is generated.
4. Compile classpath/module path and annotation processors.
5. A clean output directory and compiler exit code; do not use artifacts from a failed command to verify results.

For this lesson's small project, the following command can be used to target Java 17 when using JDK 17+ that supports that target:

```bash
javac --release 17 -encoding UTF-8 -d out @sources.txt
java -cp out demo.app.Main
```

The result is still `3 x 12 = 36`. `--release 17` constrains the language, class file format, and corresponding Java SE APIs; however, you still must ensure an appropriate runtime and dependencies when running in a real environment.

## 11. When a Project Uses the Java Platform Module System (JPMS)

The earlier examples compile classes on the classpath without `module-info.java`. If a project has explicit modules, distinguish:

- Sources inside **a single module** can be listed together, along with `module-info.java`, and output placed into the corresponding module structure.
- When compiling **multiple modules** in a single pass, `javac` has a dedicated mode using `--module-source-path` to recognize and locate module sources; binary dependencies can be located via `--module-path`.
- Running a modular program typically uses `java --module-path ... --module moduleName/package.Main`, rather than treating all class files as an unnamed classpath tree.

Do not mechanically swap `--source-path` and `--module-source-path`. This section only defines scope: the "multiple files in a single invocation" topic still applies, but JPMS directory layout, dependencies, and execution must follow module mode.

## 12. Practical Workflow for a Source Group

1. **Identify the source group** to compile together; check packages and types of dependencies.
2. **Set a separate output directory**, such as `out`; use `-d out` to generate class files following the package structure.
3. **Choose inputs:** list files explicitly when there are few, or generate an accurate `@sources.txt` when there are many. If using `--source-path`, understand implicit source discovery and compilation.
4. **Provide binary dependencies** on the compile classpath/module path, and choose an appropriate `--release`.
5. **Run a single `javac` invocation**, check the exit code and error logs. Do not assume a file listed earlier on the command line is compiled first.
6. **Run the exact main class** from the output directory using `java` with the appropriate classpath/module path.
7. When build verification is needed, **avoid leftover class files**, and record the JDK and options used.

## 13. Self-Check

**Question 1.** In the three-file example, if you change the command-line order to `Main.java Receipt.java PriceCalculator.java`, do you have to add a new `import`?

**Answer:** No. `import` depends on package/type names, not on the order of source arguments. `javac` resolves declarations from the files passed in the same group.

**Question 2.** The file `sources.txt` is placed in the `config` directory, with contents `src/demo/app/Main.java`. Does running `javac @config/sources.txt` from another parent directory guarantee finding the right file?

**Answer:** No. Paths inside an argfile are resolved from the working directory when invoking `javac`; the argfile's location does not change the base path of entries.

**Question 3.** Is the command `javac -d out src/demo/app/Main.java` guaranteed to fail because only one file is passed?

**Answer:** You cannot conclude that from the command alone. The compiler may locate class files or dependent sources according to the configured classpath/source path. Listing all required sources or setting `--source-path` explicitly makes results predictable.

**Question 4.** After compiling successfully, why does `java -cp out Main` fail to run `demo.app.Main`?

**Answer:** `Main` declared `package demo.app`. Its full binary name is `demo.app.Main`, and the classpath root is `out`.

**Question 5.** One file in the group has a type error. May all `.class` files under `out` be treated as valid artifacts of the compilation just performed?

**Answer:** No. Check the exit code, do not use artifacts after a failed build; use a clean output directory to avoid leftover class files from a previous build.

## 14. References

- **Oracle JDK 21 — The javac Command:** https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html — sections *Synopsis*, *Example of Compiling Multiple Source Files*, *Command-Line Argument Files*, *Configuring a Compilation*, and *Searching for Module, Package and Type Declarations*.
- **Java Language Specification, Java SE 21:** https://docs.oracle.com/javase/specs/jls/se21/html/ — rules on packages, type names, accessibility, and compile-time errors.
- **Java Virtual Machine Specification, Java SE 21:** https://docs.oracle.com/javase/specs/jvms/se21/html/ — class file structure and runtime type linking.

What to remember in practice: **a single `javac` invocation can take multiple source files and compile them as a group; package organization, source path, classpath, and output directory determine what the compiler finds and whether the program runs**.