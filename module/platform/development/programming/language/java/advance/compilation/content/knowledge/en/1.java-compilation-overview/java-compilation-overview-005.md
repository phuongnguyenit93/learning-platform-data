# Inputs, Configuration, Diagnostics, and Outputs of a Java Compilation

A Java compilation is the process of turning **source code** into **bytecode and class metadata** so that the JVM can load, link, and execute it afterward. For the JDK's `javac` tool, four groups must be distinguished: **inputs** provide what the compiler must understand; **configuration** determines how compilation runs; **diagnostics** report what is right or wrong; **outputs** are the generated files. Understanding these four groups helps explain why the same source code can compile successfully on one machine yet fail or behave differently on another.

## 1. How Does a Compilation Happen?

Typical workflow:

1. The tool receives the list of `.java` files, options, dependency paths, and JDK environment.
2. The compiler reads and decodes text according to the chosen encoding, splits tokens, and parses syntax into a syntax tree.
3. It resolves names, imports, types, accessibility, generics, language rules, and which APIs are usable under the target version.
4. If configured, annotation processors can analyze program elements and generate additional source code or resources; the associated processing rounds run before compilation finishes.
5. After necessary checks, the compiler generates `.class` files for the types that require bytecode generation, while also emitting errors/warnings/notes.
6. The tool reports success or failure status. **Running** the program with `java` is a separate step: the JVM loads classes and may still raise errors at linking time or execution time.

This is a high-level model; internal phase ordering, number of passes, and optimizations may differ across compiler versions or distributions. Do not think of `javac` as a tool that directly turns `.java` into native machine code.

## 2. Inputs: What Does the Compiler Need?

| Input | Role | Example |
| --- | --- | --- |
| Source code | Compilation units containing `package`, `import`, type declarations, and statements | `src/demo/Main.java` |
| APIs and compiled types | Resolves references to classes, interfaces, methods, and fields | `.class` in directories or `.jar` |
| Module libraries | Provides named modules on the module path | Modular JAR, module directory |
| Compiler configuration | Specifies release, encoding, bytecode output location, warnings, processors | `--release 17`, `-d out` |
| Annotation processors (if used) | Inspects annotations and may generate source code or resources | Processor on processor path |
| JDK platform | Provides `javac` itself and accessible platform APIs | JDK 17, 21, ... |

**Direct source files** are the files passed to the `javac` command. The compiler can find and compile additional dependent source code according to path configuration; therefore, the number of generated `.class` files can exceed the number of `.java` files listed. Each `.java` file can also declare additional non-`public` top-level types and nested types.

**Classpath (`-cp`/`-classpath`/`--class-path`)** is where classes and libraries of the unnamed-module/traditional model are searched. Bytecode directories and JARs are two common entry forms. `--module-path` is used to find named modules in the Java module system; the two mechanisms have different readability/accessibility rules. Do not solve module errors by arbitrarily moving all libraries onto the classpath.

**Source path (`-sourcepath`/`--source-path`)** controls where the compiler looks for source files for types not passed directly. It differs from classpath, which is used to find compiled types. You should explicitly declare sources in the build process to avoid implicit compilation depending on directory layout or machine state.

**Encoding** is part of the input: the same sequence of bytes can be decoded into different characters if a different character encoding is used. For UTF-8 source code, specifying `-encoding UTF-8` makes results more consistent across environments. Source file encoding, terminal output encoding, and runtime resource encoding are three separate issues.

**Runtime resources** such as `.properties`, images, or configuration files are generally not placed into the bytecode directory by `javac` automatically. Build tools typically have a separate resource-copy step. `javac` also does not automatically download libraries from Maven Central: Maven/Gradle or another step must resolve libraries beforehand.

## 3. Configuration: Options That Determine the Outcome

Basic syntax:

```text
javac [options] <source-files>
java [runtime-options] <main-class>
```

In the commands below, `javac` comes from the **JDK**, while `java` is used to run bytecode. The commands need to be executed from the proper project directory.

| `javac` Option | Practical Meaning | What to Remember |
| --- | --- | --- |
| `--release 17` | Compiles with the syntax, bytecode, and public APIs of Java 17 | Requires a JDK supporting that target; preferable to setting only `-target` when compatibility is needed |
| `-source 17` | Specifies the source syntax level | Does not automatically restrict library APIs to the target JDK |
| `-target 17` | Specifies the class file version | Not a full substitute for `--release` |
| `-encoding UTF-8` | Reads `.java` files as UTF-8 | Does not govern the encoding of all data when the program runs |
| `-d out` | Writes class files to the `out` directory | Create the target directory beforehand; packages become subdirectories |
| `-cp libs/example.jar` | Specifies where to find dependencies on the classpath | With multiple entries: `;` on Windows, `:` on Unix |
| `--module-path mods` | Where to find named modules | Only works properly when structure/modules are suitably declared |
| `-sourcepath src` | Where to find additional dependent source code | Distinguish from classpath |
| `-Xlint:all` | Enables warning groups supported by `javac` | Can select specific groups such as `unchecked` or `deprecation` |
| `-Werror` | Treats compiler warnings as build errors | Can fail the build even when the program has no syntax errors |
| `-Xdiags:verbose` | Makes diagnostic messages more detailed | Useful when generics or overloads lead to hard-to-read errors |
| `-g` / `-g:none` | Adjusts debug info in class files | Affects debugging, does not alter intended source logic |
| `-parameters` | Records method parameter names for reflection | Different from local variable names in debug info |
| `-s generated` | Selects where to write source code generated by annotation processors | Only takes effect when generated sources actually exist |
| `-proc:none` | Disables annotation processing | Used when you need to control or isolate processors |
| `-h headers` | Generates native headers for native methods when needed | Not a mandatory output of every program |

When the target is Java 17 compatibility, e.g., `javac --release 17 ...` on a JDK supporting Java 17 is an explicit choice. Avoid combining `--release` with `-source`/`-target` in the same invocation. Compiling to version-17 class files **does not prove** that the entire application can run on a specific JVM: external dependencies, resources, configuration, and runtime behavior still must be tested.

`-cp` at the **compile** step and `-cp` at the **run** step serve two different phases. Running the program also requires the necessary runtime dependencies, even if the compilation phase succeeded.

## 4. End-to-End Example: Compiling Two Java 17 Classes

Suppose the initial project structure is as follows:

```text
project/
└── src/
    └── demo/
        ├── Calculator.java
        └── Main.java
```

File `src/demo/Calculator.java`:

```java
package demo;

public final class Calculator {
    private Calculator() {
    }

    public static int add(int left, int right) {
        return left + right;
    }
}
```

File `src/demo/Main.java`:

```java
package demo;

public final class Main {
    public static void main(String[] args) {
        int result = Calculator.add(2, 3);
        System.out.println("Kết quả: " + result);
    }
}
```

From the `project` directory, create the destination for class files and compile **both** files:

```sh
mkdir out
javac --release 17 -encoding UTF-8 -d out src/demo/Calculator.java src/demo/Main.java
java -cp out demo.Main
```

When compilation succeeds, `javac` normally prints no status line. **The stdout of the final `java` command is exactly:**

```text
Kết quả: 5
```

Bytecode output after compilation:

```text
out/
└── demo/
    ├── Calculator.class
    └── Main.class
```

Points to observe:

- `package demo;` makes the class's binary name `demo.Main`, and with `-d out` the file is placed under `out/demo`.
- `java -cp out demo.Main` uses the **fully qualified class name**; do not pass the path `out/demo/Main.class` in place of the main class name.
- `--release 17` selects the Java 17 target; the class files in this example have major version **61**. You can verify with `javap -verbose -classpath out demo.Main` and look for `major version: 61`.
- `javac` does not run the `main` method itself. The stdout above appears when executing `java`.
- If `-d out` is omitted, the location of generated files depends on source organization and remaining options; specifying an output directory makes management easier.
- Re-running `javac` over an old output directory can leave files from a previous build. When verifying reproducibility, use a clean output directory managed by a build tool or a deliberate build process.

**Why compile all required sources?** The `Main` class references `Calculator`. If only `Main.java` is passed, the ability to find `Calculator` depends on where the tool looks for sources/bytecode. Explicitly listing both files or configuring the source path properly makes the result less environment-dependent.

## 5. Diagnostics: Reading Errors and Warnings by the Right Phase

`javac` can emit:

- **Error**: a violation preventing the compilation unit from producing valid output, such as syntax errors, incompatible types, unresolved symbols, invalid member access, or missing modules or dependencies.
- **Warning**: something worth noting that does not necessarily stop compilation, such as raw/unchecked generics, deprecated APIs, or anomalies detected by `-Xlint`. Using `-Werror` causes warnings to fail the compilation command.
- **Note/other messages**: informational output emitted by the compiler or annotation processors, not automatically an error.

Example file `src/demo/Broken.java`:

```java
package demo;

public class Broken {
    public static void main(String[] args) {
        int total = "five";
        System.out.println(total);
    }
}
```

Command:

```sh
javac --release 17 -encoding UTF-8 -d out src/demo/Broken.java
```

A typical error message (spacing, formatting, and details may differ by JDK/options):

```text
src/demo/Broken.java:5: error: incompatible types: String cannot be converted to int
        int total = "five";
                    ^
1 error
```

Read the message from left to right: **source file → line (possibly plus column) → severity → error nature → relevant location**. Here `String` cannot be assigned to an `int` variable; fix the source code, for example `int total = 5;`, and recompile. Changing the classpath will not fix this type-incompatibility error.

Table distinguishing issue origins:

| Symptom | Commonly Related Phase | Diagnostic Question |
| --- | --- | --- |
| `';' expected`, `illegal start of expression` | Source syntax parsing | Brackets, semicolons, syntax valid under `--release`? |
| `cannot find symbol` | Name/type resolution | Wrong name, missing import, missing source or classpath? |
| `package ... does not exist` | Package/library resolution | Does the JAR have the right contents, version, path? |
| `incompatible types` | Type checking | Are return values/generics/casts valid? |
| `module not found` | Module resolution | Are `module-info.java` and `--module-path` correct? |
| `unchecked` warning | Generics checking | Is there a raw type or unchecked cast? |
| `UnsupportedClassVersionError` | Class loading/running, **after** compilation | Does the runtime JVM support the class file version? |
| `NoClassDefFoundError` | Class loading/running, **after** compilation | Is the class missing on the runtime classpath/module path? |

The last two rows illustrate **runtime/linkage** errors, not compiler messages from a normal `javac` run. Similarly, a `NullPointerException` or business-logic error occurring at runtime cannot be interpreted as a compile-time syntax error.

When investigating the cause of a build error:

1. Capture the **actual `javac` command**, `javac -version`, full stderr, working directory, and necessary dependency paths.
2. Read **the first error with a clear cause** first: a single declaration error or missing dependency can trigger many cascading errors afterward.
3. Categorize the error under source code, release/API, classpath/module path, encoding, or annotation processing.
4. Fix the true root cause, rebuild, and check the exit code, rather than merely checking whether an old `.class` file is present.
5. Use `-Xdiags:verbose` or `-Xlint:unchecked`/`-Xlint:deprecation` when more information is needed.

**Command exit code:** normally `javac` returns 0 when finishing successfully and non-zero when failing. Shells/build systems should decide success or failure based on the exit code; do not rely on empty stdout. The compiler normally writes diagnostics to stderr in default CLI invocations, though integrated tools may collect and display them differently. Do not treat the existence of a file location as proof that the current compilation succeeded.

## 6. Outputs: Bytecode, Metadata, and Packaged Artifacts

**`.class` is the primary output**. It contains the JVM class file structure, constant pool, type/member information, bytecode of methods with code, attributes such as source/debug info, and appropriate annotations. A single `.java` file can produce multiple `.class` files; for example, nested classes typically have file names containing `$`. Not every declaration produces exactly one class file as viewed from source code.

**Generated sources/resources** appear only when annotation processors or corresponding code-generation tools are enabled. Depending on configuration, generated sources may be written under the directory selected with `-s`, while compiled classes still reside in the `-d` directory. Do not confuse generated Java files with class files, and do not arbitrarily commit a generated directory managed by the build configuration.

**Native headers** can be generated with `-h` when an application uses the corresponding native integration approach; this is not a default product of a pure Java exercise.

**JAR** is a **post-compilation packaging** step, not something `javac -d` automatically creates. From the successful example in section 4, you can run:

```sh
jar --create --file demo.jar --main-class demo.Main -C out .
java -jar demo.jar
```

Stdout of `java -jar demo.jar` in this example is still:

```text
Kết quả: 5
```

The `--main-class` option records the program entry point in the JAR's manifest. Without an appropriate entry point, `java -jar` does not know which class to run. A JAR may need additional dependencies or configuration; this example has no external libraries, so it runs directly. Unlike `java -cp ...`, when using `java -jar`, the classpath from the launcher's `-cp` argument does not determine that JAR application's dependencies; the manifest or another packaging/launcher approach must handle them.

**Leftover files after errors:** do not rely on the assumption that every failed build cleans up all output. With multiple source files or multiple build tasks, the output directory may contain artifacts from a previous run or artifacts written before the error occurred. When you need proof of a single compilation, use fresh output, record the exit code, and verify the exact build's artifacts.

## 7. Compiling via Build Tools or the Compiler API

In large projects, Maven/Gradle/IDEs typically act as the orchestration layer. They locate sources, resolve dependencies, select the Java toolchain/release, configure processors, invoke the compiler, copy resources, run tests, and package. Therefore, an error appearing in Gradle/Maven may belong to the **dependency resolution/build configuration layer**, not necessarily to Java syntax. When debugging, look for the invocation and diagnostics of the specific compilation task.

Java also provides the **Java Compiler API** in `javax.tools`, typically:

- `ToolProvider.getSystemJavaCompiler()` to obtain the compiler available in an appropriate JDK environment; may return `null` if the environment does not provide a system compiler.
- `JavaCompiler.getTask(...)` to pass options, compilation units, and a file manager; call `call()` to see whether the task succeeded.
- `DiagnosticCollector<JavaFileObject>` to collect diagnostics with severity, file, line, column, code, and message.
- `StandardJavaFileManager` to manage sources, bytecode, and input/output paths.

IDEs and build plugins may use the Compiler API or another integration mechanism; do not assume every diagnostic will appear in the terminal. Even when invoked through the API, the concepts of source, release, classpath/module path, processors, outputs, and errors remain the same.

### Annotation Processing Is a Step with Its Own Configuration and Impact

An annotation processor can generate additional sources, resources, or report errors/warnings; it runs **during the build** and can execute build-library code. How processors are automatically discovered/run changes across JDK versions and build setups. For real projects, explicitly declare processors and processor paths through the build tool, check processor versions, and avoid treating every JAR on the classpath as trustworthy to run during a build. `-proc:none` is useful when you need to determine whether an issue comes from a processor.

## 8. Common Misconceptions

**"If compilation succeeds, running is guaranteed to succeed."** False: the target JVM may be older than the class file, missing runtime dependencies, missing resources, or have logic errors. Test both compile and run on the target environment.

**"Setting `-target 17` makes all APIs Java 17 compatible."** Insufficient: a newer JDK may allow source code to call APIs absent in 17. If the JDK supports it, use `--release 17` for the corresponding platform API constraints; external dependencies still need separate verification.

**"`cannot find symbol` always means a missing import."** It can also be caused by a wrong name, modifier, invalid declaration, unfound dependent source, or wrong classpath. Read the exact symbol and context in the diagnostic.

**"`javac` outputs a JAR."** `javac` produces class files and some optional outputs; `jar` or a build tool performs packaging.

**"Source path, classpath, and module path are interchangeable."** Each path serves a different resolution mechanism. In modular projects, you need to understand `module-info.java` and module readability relationships; in non-modular projects, you must specify the required JARs/classes on the classpath.

**"Having a `.class` file means the latest compilation succeeded."** Old files may remain; check the exit code and output of the exact build.

**"`-parameters` and `-g` are the same."** `-parameters` stores parameter-name metadata for reflection access; `-g` adjusts debug info. These serve different purposes.

## 9. Checklist to Explain and Reproduce a Compilation

Before concluding that a compilation is accurate, you can ask yourself:

1. **Inputs:** Which `.java` files are compiled? Which classes/JARs/modules/sources/processors are needed? Which step handles runtime resources?
2. **Environment:** What is `javac -version`? Where is the current working directory? Which encoding are the source files using?
3. **Configuration:** What are the actual `--release`, `-d`, classpath/module path, source path, and lint/processor options?
4. **Diagnostics:** What is the exit code? Which file/line/symbol did errors/warnings originate from? Did `-Werror` fail the build?
5. **Outputs:** Which new class files were created? Are there generated sources, native headers, or JARs? Do the artifacts belong to this exact build?
6. **Verification:** Run the exact class name or entry point on the target runtime and verify stdout/behavior; distinguish compile errors from runtime errors.

Having a firm grasp of all four groups—**input → configuration → diagnostics → output**—will help you accurately reproduce a `javac` run, pinpoint the exact fault, and avoid guessing from a single error line or an accidentally existing `.class` file.