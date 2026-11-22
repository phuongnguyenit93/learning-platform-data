# Distinguishing javac Options from JVM Options Passed via -J

When compiling Java, there are **two configuration layers** that are easily confused:

- **`javac` compiler layer:** determines how source code is read and checked, dependencies are found, `.class` files are generated, and the target Java version is chosen. For example: `-encoding UTF-8`, `-d out`, `--release 17`, `-classpath lib/*`, `-Xlint:all`.
- **Layer of the JVM running the compiler itself:** determines the configuration of the Java process executing `javac`, such as heap size, system properties, and some VM diagnostic options. When invoking `javac` via the command-line launcher program, use the **`-J` prefix** to pass a JVM option down to this layer. For example: `-J-Xmx512m` or `-J-Dlesson.mode=compile`.

Most important point: **the JVM running the compiler differs in role from the JVM that will run the application after compilation**. `-J-Xmx512m` does not automatically cause the Java application later to run with a 512 MiB heap. Similarly, `--release 17` does not change the JVM version currently running `javac`.

This lesson applies mainly to **the `javac` command in JDK 17+**. In an IDE, Gradle, Maven, or a program calling the Java Compiler API, how JVM settings are configured can differ because the compiler is not necessarily launched by an independent `javac` process.

## 1. Path Diagram of a Compilation Command

```text
Shell / terminal
  |
  | javac -J-Xmx512m --release 17 -encoding UTF-8 -d out Sample.java
  |
  v
javac launcher
  |                                 
  |-- -J-Xmx512m ------------> JVM running the compiler
  |                               | max heap 512 MiB
  |                               v
  |                           javac code
  |                               ^
  |-- --release 17 ---------------|
  |-- -encoding UTF-8 ------------| compiler options
  |-- -d out ---------------------|
  |-- Sample.java ---------------|
                                  |
                                  v
                             out/Sample.class
                                  |
                                  | run in the next command
                                  v
                         java -cp out Sample
                                  |
                                  v
                      JVM running the application
```

Diagram arrows illustrate **roles**, not mandatory internal details of every implementation. The JDK `javac` tool specification defines `-Joption` as the way to pass `option` to the Java runtime system on the compiler side.

| What You Want to Configure | Where to Write It? | Example | Primary Effect |
| --- | --- | --- | --- |
| Output directory | `javac` option | `-d out` | Location where class files are created |
| Target Java version | `javac` option | `--release 17` | Corresponding language, platform API, and class format |
| Source file encoding | `javac` option | `-encoding UTF-8` | How characters in `.java` are read |
| Compiler warnings | `javac` option | `-Xlint:deprecation` | Diagnostics during compilation |
| Classpath used for compilation | `javac` option | `-cp libs/example.jar` | Finds classes/libraries along the classpath |
| Max heap of the compiler JVM | JVM option via `-J` | `-J-Xmx512m` | Heap memory of the compilation process |
| Initial heap of the compiler JVM | JVM option via `-J` | `-J-Xms128m` | Initial heap size of the compiler JVM |
| System property for compiler JVM | JVM option via `-J` | `-J-Ddemo.mode=compile` | System property of the process running the compiler |
| Heap of the application after build | `java` command option at runtime | `java -Xmx512m -cp out Sample` | Heap of the JVM running the application |

`-Xlint` and `-Xmx` are alike only in the leading characters `-X`: **`-Xlint` is understood by javac; `-Xmx` is a JVM option**. Do not infer the parameter recipient from the `-X` prefix; look up the documentation of the exact tool instead.

## 2. Standard Syntax of -J

General form:

```text
javac -J<JVM-option> <javac-option> <source-file>
```

Typical valid commands:

```bash
javac -J-Xmx512m -d out Sample.java
javac -J-Xms128m -J-Xmx512m --release 17 -d out Sample.java
javac -J-Dlesson.mode=compile -encoding UTF-8 -d out Sample.java
```

In the three commands above, `Sample.java` is a hypothetical file name assumed to exist in the current directory. When passing an option to the JVM, **attach `-J` directly to that option itself**, keeping the `-` sign of the JVM option intact:

- `-J-Xmx512m` = passes `-Xmx512m` to the compiler's JVM.
- `-J-Xms128m` = passes `-Xms128m` to the compiler's JVM.
- `-J-Dlesson.mode=compile` = passes `-Dlesson.mode=compile` to the compiler's JVM.
- If multiple JVM options are needed, **repeat `-J` for each option**.

Error-prone forms:

```text
javac -Xmx512m Sample.java
javac -J -Xmx512m Sample.java
javac -J-Xmx 512m Sample.java
java -J-Xmx512m -cp out Sample
```

Explanation:

1. `javac -Xmx512m` passes `-Xmx512m` directly to the **compiler**, usually resulting in an invalid option error; to adjust the compiler's JVM, use `-J-Xmx512m`.
2. `-J -Xmx512m` separates `-J` into a separate argument. The documented syntax is **`-Joption`**, with no space between the prefix and the remainder.
3. `-J-Xmx 512m` splits the value `512m` into another argument; the heap size must be part of the `-Xmx512m` option.
4. The `java` command directly accepts the JVM option `-Xmx512m`; **do not add `-J` to the `java` command**.

When a value contains spaces, escaping/quoting depends on the shell; focus on the actual arguments the shell passes to the program. For examples like heap `512m` or property `key=value` without spaces, quotes are unnecessary.

## 3. Standalone Runnable Java 17+ Example: Compiler Property vs. Runtime Property

Create file `ModeCheck.java` in a separate learning directory:

```java
public class ModeCheck {
    public static void main(String[] args) {
        String mode = System.getProperty("lesson.mode", "unset");
        System.out.println("Mode: " + mode);
    }
}
```

Compile and run in the order below (JDK 17+):

```bash
javac -encoding UTF-8 -J-Dlesson.mode=compile -J-Xmx512m -d out ModeCheck.java
java -cp out ModeCheck
java -Dlesson.mode=run -cp out ModeCheck
```

In a normal environment **without external variables or configurations automatically setting `lesson.mode`**, the stdout of the two `java` commands is respectively:

```text
Mode: unset
Mode: run
```

A successful `javac` command normally **prints no lines**; the two lines above are output from **the two `java` runs**, not output from `javac`. The compile command creates `out/ModeCheck.class`; `-d out` lets `javac` create the target directory if needed.

Why does the first run print `unset`?

- `-J-Dlesson.mode=compile` sets a system property **in the JVM running `javac`**.
- The code of `ModeCheck.main` **has not yet been run** during the `javac` step; that property value is not automatically written into the class file.
- When running `java -cp out ModeCheck`, a new application JVM is started; without configuring the property, the call `getProperty(..., "unset")` returns the default value `unset`.
- Only when running `java -Dlesson.mode=run -cp out ModeCheck` does the application JVM have the property `lesson.mode=run`.

This is a **boundary test between the compiler JVM and the application JVM**. It shows that supplying a property at compile time does not automatically supply it at runtime; the application's own output is not a tool for measuring the compiler JVM's heap configuration.

### Comparing the Two Heap Commands

```bash
javac -J-Xmx512m -d out ModeCheck.java
java -Xmx512m -cp out ModeCheck
```

On the first line, `512m` is the heap limit of the **compiler JVM**. On the second line, it is the heap limit of the **application JVM**. Having identical numbers is just a coincidence of our choice, and a heap limit **does not mean** the process will definitely use exactly 512 MiB of physical RAM or 512 MiB of total process memory.

If you need to specify both, configure **both commands** (or both corresponding sections in build/deployment). No option automatically forwards settings from the previous command to the JVM in the next command.

## 4. javac Options: When Should They Be Used Directly?

The following parameters control **compilation work**, without needing `-J`:

### -d: Where Class Files Are Created

```bash
javac -d out ModeCheck.java
```

`out` is the **output directory** for class files. For classes in a package, `javac` lays out subdirectories following the package name. `-J-d out` is not a valid use of `-d`: the `-J` prefix would pass the content as an option to the JVM, which does not understand compiler output directives that way.

### -encoding: Source Encoding

```bash
javac -encoding UTF-8 -d out ModeCheck.java
```

This option ensures the compiler reads `.java` as UTF-8. Do not confuse it with `-J-Dfile.encoding=UTF-8`: a JVM property can affect the execution environment of the compiler, whereas **`-encoding UTF-8` is the explicit, purpose-built configuration for source code input** and is less ambiguous.

### --release: Target Version

```bash
javac --release 17 -d out ModeCheck.java
```

This option constrains the language level, available standard APIs, and class file format to the specified Java version. With a JDK supporting `--release 17`, this is the right way to produce class files targeting Java 17. It **does not launch a Java 17 JVM** to compile and has no effect on increasing/decreasing heap.

Example:

```bash
javac -J-Xmx512m --release 17 -encoding UTF-8 -d out ModeCheck.java
```

This command consists of **two independent parameter groups**: `-J-Xmx512m` is for compiler JVM memory; `--release 17`, `-encoding UTF-8`, and `-d out` are for the compilation operation.

### -cp / --class-path: Libraries for Compilation

```bash
javac -cp libs/example.jar -d out ModeCheck.java
```

`libs/example.jar` here merely illustrates **a path to an actually existing JAR** in a project. `-cp` selects the classes/libraries `javac` uses when resolving references in source code. It **does not configure the classpath launching the compiler implementation itself**; the JDK has separate modules/mechanisms containing the compiler. If you want to change the classpath used when running `ModeCheck`, put `-cp` on the `java` command after building.

### -Xlint: Compiler Warnings

```bash
javac -Xlint:deprecation -d out ModeCheck.java
javac -Xlint:all -d out ModeCheck.java
```

`-Xlint:deprecation` asks the compiler to warn about uses of deprecated APIs; `-Xlint:all` enables the group of warnings supported by `javac`. With the example `ModeCheck.java`, there are no deprecated calls, so there may be **no warning output**. Do not confuse it with `-J-Xlog:...` (a JVM logging configuration form on supporting JDKs).

### How to View Options from the Right Source

```bash
javac --help
javac -X
java --help
java -X
```

`javac --help` displays standard compiler options; `javac -X` provides extra compiler options. Meanwhile `java --help` or `java -X` describes options on the Java launcher/JVM side. Do not take an option name from a JVM manual page and pass it straight to `javac` without checking whether `-J` is needed.

## 5. JVM Options Passed via -J: When Are They Truly Useful?

### Increasing or Adjusting Heap for Compilation

```bash
javac -J-Xms128m -J-Xmx1g -d out LargeSource.java
```

`-Xms128m` is the initial heap setting; `-Xmx1g` is the maximum heap limit. The purpose may be to resolve out-of-heap errors in a large `javac` process, run memory-heavy annotation processors, or create a more stable measurement environment. They **do not** alter `.class` file sizes or make source code more valid.

This is a sample syntax; `LargeSource.java` must be a real file if you want to run it. Do not assume increasing heap will fix every `OutOfMemoryError`: you must first identify whether the error occurs in the compiler JVM, a build daemon, an annotation processor, the application JVM, or off-heap system memory.

### Setting a System Property for the Compiler Process

```bash
javac -J-Dbuild.profile=experiment -d out ModeCheck.java
```

The JVM running the compiler gets the property `build.profile=experiment`. This can affect Java code **executing inside the compiler JVM**, such as an annotation processor that actually reads `System.getProperty("build.profile")`; it does not turn the string `experiment` into a constant in every compiled class file.

If a build library/processor reads a different property, use the property name documented by that library itself. An arbitrary `-D` does nothing if no code reads it.

### Logging or Diagnosing the Compiler JVM

Example on HotSpot and JDKs supporting unified logging:

```bash
javac -J-Xlog:gc=info -J-Xmx512m -d out ModeCheck.java
```

The `-Xlog:gc=info` option is sent to **the JVM running the compiler**. Depending on GC activity, the JVM, and configuration, log lines may or may not appear; the content, timestamps, and log destination are not fixed lab outputs. It **does not enable GC logging** when running `java -cp out ModeCheck` afterward.

Advanced `-X` and `-XX` options can depend on JVM implementation/version. Only apply choices supported by the JVM in use; check `java -X` and the corresponding version's documentation. Warnings or “Unrecognized VM option” errors typically appear before source code is compiled.

### Why Is -J Not Always Needed?

Small projects compile normally with default JVM settings. `-J` is primarily useful when you genuinely need to configure **the compilation process**: heap, properties for processors/plugins, or VM diagnostics. Using it as a “general performance optimization” move without measurements can clutter configurations and make reproduction difficult across developer machines, IDEs, and CI.

## 6. Proving the Compiler JVM Property with an Annotation Processor (Advanced)

The `ModeCheck` example above proves independence between **compile-time properties** and **application-runtime properties**. If you want to **directly observe** a property passed via `-J` *inside the compiler JVM*, you can write a small annotation processor. This section is for those wanting verification via code executing inside the compiler; it is not necessary to use ordinary options.

Create file `CompilerPropertyProbe.java`:

```java
import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.TypeElement;
import javax.tools.Diagnostic;

@SupportedAnnotationTypes("*")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public class CompilerPropertyProbe extends AbstractProcessor {
    private boolean reported;

    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {
        if (!reported) {
            processingEnv.getMessager().printMessage(
                    Diagnostic.Kind.NOTE,
                    "Compiler property: " +
                            System.getProperty("lesson.mode", "unset"));
            reported = true;
        }
        return false;
    }
}
```

This class has no `main` because it is a processor invoked by **`javac` during compilation**. `@SupportedAnnotationTypes("*")` allows the processor to be triggered for matching annotation types; with `-processor` explicitly specified, the processor will be called across processing rounds when compiling the example file. Annotation processing documentation specifies how processors are discovered and executed.

Compile the processor first, then use it to compile `ModeCheck.java`, still with a JDK supporting Java 17:

```bash
javac --release 17 -d processor-out CompilerPropertyProbe.java
javac --release 17 -J-Dlesson.mode=compile \
  -processorpath processor-out \
  -processor CompilerPropertyProbe \
  -d out ModeCheck.java
```

The line-continuation syntax using `\` at the end of a line applies to **Bash/zsh**. In PowerShell or cmd, write the second `javac` command **on a single line**, without using `\` as a line-continuation symbol:

```text
javac --release 17 -J-Dlesson.mode=compile -processorpath processor-out -processor CompilerPropertyProbe -d out ModeCheck.java
```

In a simple environment, processor diagnostics include the line:

```text
Note: Compiler property: compile
```

This is a **diagnostic note emitted by the compiler**, not the stdout of the `ModeCheck` program. The `System.getProperty` call inside `CompilerPropertyProbe.process` runs **right inside the JVM running the compiler** (with command-line `javac` in the example), so it sees the property set by `-J-Dlesson.mode=compile`. If you omit `-J-Dlesson.mode=compile` and have no external configuration, the note displays `unset`.

Try running the newly compiled application:

```bash
java -cp out ModeCheck
```

Stdout is still:

```text
Mode: unset
```

This cleanly separates three layers: **processor code** running in the compiler JVM; **`ModeCheck` bytecode** generated for storage; and **`ModeCheck.main`** running in the application JVM afterward.

To avoid source warnings, the processor example uses `SourceVersion.RELEASE_17` and the application compile command also specifies `--release 17`. When moving to a newer release, evaluate appropriate source version support; do not force every older processor to automatically support all new releases.

## 7. How Do java -Xmx and javac -J-Xmx Differ?

Suppose you want to compile with a 1 GiB heap and then run the application with a 256 MiB heap. Two suitable commands are:

```bash
javac -J-Xmx1g -d out ModeCheck.java
java -Xmx256m -cp out ModeCheck
```

| Question | Command `javac -J-Xmx1g` | Command `java -Xmx256m` |
| --- | --- | --- |
| Configured process | Compilation process | Application process |
| Max heap | 1 GiB for compiler JVM | 256 MiB for application JVM |
| Creates class files? | Yes, if compilation is valid | No (runs existing classes) |
| Runs application's `main`? | No | Yes |
| Automatically saves heap setting to class file? | No | No |
| Common goal | Compilation/processors needing memory | Application needing memory limits at runtime |

Running `javac -J-Xmx1g` is useless if the out-of-memory error happens **when running the application**; conversely, `java -Xmx1g` does not give an already finished compiler JVM a larger heap.

Both can be configured with different amounts, because they are **two processes with independent lifecycles**. In some build tools, the entire compilation can sit inside a running daemon rather than a separate `javac` process; the next section explains this point.

## 8. When javac Is Invoked via API, Gradle, Maven, or an IDE

The `-J...` syntax is defined for the **command-line `javac` launcher**. Java has APIs such as `javax.tools.JavaCompiler` and `java.util.spi.ToolProvider` that allow running the compiler **inside an existing JVM**.

Illustrative example of principle, not a standalone Java program:

```java
javax.tools.JavaCompiler compiler =
        javax.tools.ToolProvider.getSystemJavaCompiler();
// compiler.run(...) uses the compiler inside the JVM running the calling program.
```

The snippet above only illustrates the API and neither creates source/target files nor invokes `run`; do not use it to attempt a standalone run. When the compiler is embedded in the **host tool's JVM**, heap and `-D` options typically have to be configured when **starting the host JVM**. One cannot assume passing a string `-J-Xmx...` into `JavaCompiler`'s option list will work like the `javac` command.

Nor can you infer from `java -version` in a terminal that an IDE or build tool is using that JVM. Cases to distinguish:

- **Running `javac` via terminal:** `javac -J-Xmx...` has a clear meaning per launcher documentation.
- **Compiler running in build tool's JVM:** the build tool JVM's heap may be the limiting source; check settings meant for that process itself.
- **Build tool forks compiler process:** the build tool may provide a configuration field for JVM arguments of the compiler process; setting names and passing mechanisms depend on the tool, not defaulting to the exact command-line string `-J-Xmx...`.
- **IDE:** the compiler may run in a separate process/daemon. Project JDK settings, build process memory, and application runtime are parts that can be separated.

For example, with Gradle: the JVM running the Gradle Daemon, the Java toolchain selected to compile, and the JVM used for running/testing can differ. Increasing `org.gradle.jvmargs` adjusts the Gradle daemon accordingly, and **does not automatically** mean every forked compilation task or application JVM gets the same heap. With Maven as well, check plugin/compiler mode and the actual process's JVM configuration.

**Practical rule:** identify **which process is raising the error** and then use the configuration that process supports. The name `javac` in a build log is not enough to conclude whether an independent launcher receives `-J` or the compiler is invoked inside a running process.

## 9. Two Related Mechanisms Easily Confused: @argument-file and JDK_JAVAC_OPTIONS

### @argument-file

`javac` supports placing multiple options/source file names into an argument file, such as `compile.args` containing:

```text
--release
17
-encoding
UTF-8
-d
out
ModeCheck.java
```

Then:

```bash
javac @compile.args
```

However, according to `javac` documentation, **`-J` options are not supported inside an argument file** because they must be processed by the launcher before the compiler reads the argument file. The right way when needing both is to put `-J` **outside the file**:

```bash
javac -J-Xmx512m @compile.args
```

Do not move `-J-Xmx512m` into `compile.args` and expect it to be equivalent. This behavior is very important when writing long custom build scripts.

### JDK_JAVAC_OPTIONS

In modern JDKs, the `JDK_JAVAC_OPTIONS` environment variable can provide default arguments prepended to `javac`'s argument list according to documented splitting/quoting rules. It differs from `JAVA_TOOL_OPTIONS`, `JDK_JAVA_OPTIONS`, and `JAVA_HOME`; each variable has its own scope of application and should not be assumed interchangeable.

Illustrative example in Bash:

```bash
export JDK_JAVAC_OPTIONS="--release 17 -encoding UTF-8"
javac -d out ModeCheck.java
```

When diagnosing a `javac` command with unexpected behavior, inspect this variable alongside build configuration. In particular, if you suspect the release target is silently being altered, a default variable supplying `--release` may explain the result. For reproducible project configurations, write important options explicitly in build/toolchain config rather than relying solely on personal environment settings.

Do not confuse `JDK_JAVAC_OPTIONS` with `-J` syntax: the environment variable concerns **the source providing arguments to the javac launcher**, whereas `-J` concerns **the recipient of a JVM option**.

## 10. Common Errors and How to Identify Root Causes

| Symptom | Possible Cause | What to Check |
| --- | --- | --- |
| `invalid flag: -Xmx512m` | Passed a JVM option directly to javac | Change to `javac -J-Xmx512m ...` |
| JVM reports `Unrecognized VM option` | Option after `-J` is unsupported by the compiler JVM | Check JDK/vendor/version and corresponding `java` documentation |
| Compilation hits `OutOfMemoryError: Java heap space` | The JVM actually running compiler/processor lacks heap | Identify the process and try configuring heap on the right process; measure memory |
| App runs out of heap despite compiling with `-J-Xmx1g` | `-J` applies only to the compiler JVM | Configure `java -Xmx...` or the application's runtime |
| `-J-Dflag=value` yet `main` does not see the property | Property was set on the compiler JVM | Supply `-Dflag=value` to the `java` command at runtime |
| `-J-Xmx...` inside `@args` does not work | Argument files do not support `-J` | Put `-J` on the command line |
| `--release 17` still runs on a newer JDK | Confusing target release with the runtime running the compiler | Check `javac -version`, class file target, and actual runtime |
| Compiler from IDE/Gradle ignores `-J` | May use API or fork with its own configuration | Check compiler invocation mode and the tool's JVM args |
| `javac` fails despite valid options | Source code, classpath, paths, or other settings have errors | Read specific diagnostics before adjusting heap |
| Compiler output contains unexpected GC logs | May be due to `-J-Xlog:...` or JVM options from environment | Inspect arguments and environment variables of the compiler JVM |

A common mistake is lumping everything together as “Java's JVM”. When debugging, explicitly write down **compiler JVM**, **build tool JVM** (if any), **test/application JVM**, and **target bytecode version**; these components can be independent.

## 11. Practice Checklist and Exercises

### Checklist for a javac Command with -J

1. Run `javac -version` to confirm the intended compiler version.
2. Identify the **task to solve**: output, encoding, warnings, target release, or JVM heap/properties.
3. Place each option into the right layer before running.
4. Write `-J-Xmx...`, `-J-D...` with no space, repeating `-J` if there are multiple JVM options.
5. Put `--release`, `-d`, `-encoding`, `-cp`, `-Xlint` as **compiler options**.
6. Compile a real source file; verify class files and exit code results.
7. Run the program using a separate `java` command, with JVM options for **the application** if needed.
8. If running via IDE/Gradle/Maven, verify whether the compiler is forked and configure the JVM of the actual process.

### Exercise 1: Classify Options

Given the command:

```bash
javac -J-Xms128m -J-Xmx768m -encoding UTF-8 \
  --release 17 -Xlint:deprecation -d out ModeCheck.java
```

In Bash/zsh, `\` continues lines; Windows PowerShell/cmd should write it on a single line. Classify it yourself:

- **Compiler JVM:** `-J-Xms128m`, `-J-Xmx768m`.
- **Compiler:** `-encoding UTF-8`, `--release 17`, `-Xlint:deprecation`, `-d out`, and input `ModeCheck.java`.
- **Application JVM:** not yet configured in this command because the application is not running yet.

### Exercise 2: Fix Incorrect Commands

A learner wrote:

```text
javac -Xmx1g --release 17 ModeCheck.java
java -J-Xmx256m ModeCheck
```

Fix it to:

```bash
javac -J-Xmx1g --release 17 -d out ModeCheck.java
java -Xmx256m -cp out ModeCheck
```

In the first command, `-J-Xmx1g` belongs to the compiler JVM. In the second command, `-Xmx256m` belongs to the application JVM. Add `-d out` and `-cp out` so the run command finds the right class file.

### Exercise 3: System Property Experiment

1. Run `javac -J-Dlesson.mode=compile -d out ModeCheck.java`.
2. Run `java -cp out ModeCheck` and observe `Mode: unset` if there is no external property configuration.
3. Run `java -Dlesson.mode=run -cp out ModeCheck` and observe `Mode: run`.
4. Explain why the compiler's property does not appear in the application JVM.
5. If you want to measure the compiler JVM's property itself, use `CompilerPropertyProbe` in the advanced section and explain why the processor sees `compile`.

### Exercise 4: Diagnose an Out-of-Memory Build

A pipeline reports `OutOfMemoryError` during **compilation**. Do not immediately change the service's `java -Xmx`. Verify which process compilation runs in: standalone `javac`, Gradle Daemon, forked compiler, or annotation processor. Then choose the right place to set JVM arguments, check logs and heap metrics, and re-run under the same conditions to confirm.

## 12. Takeaways and Reference Documentation

- **`javac` options** like `--release`, `-d`, `-encoding`, `-cp`, and `-Xlint` describe **the compilation work**.
- **`-Joption`** sends a **JVM option** to the runtime executing **command-line `javac`**, e.g., `-J-Xmx512m` or `-J-Dname=value`.
- **`java -Xmx...`** configures the **JVM running the program**; `-J` is neither needed nor allowed on the `java` command.
- **`-J` cannot be placed in an `@argfile`**, and you cannot assume a compiler invoked inside an existing JVM via API accepts the same `-J` mechanism.
- **Increasing compiler heap does not give the post-compilation program more heap**, and `--release` changes the compiler's target rather than selecting the compiler JVM.

Official documentation to cross-check against the version you are using:

1. [Oracle JDK 21 — The javac Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html): `-Joption`, `--release`, `-d`, `-encoding`, `-Xlint`, `@argument-file`, and `JDK_JAVAC_OPTIONS`.
2. [Oracle JDK 21 — The java Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html): `-Xms`, `-Xmx`, `-D`, and advanced VM options.
3. [Java SE 17 — Java Compiler API](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.html): using the compiler via API inside a running JVM.

When encountering an unfamiliar option, ask **“Who receives this argument: javac or which JVM?”** and check the manual of the exact tool version before adding it to a build command.