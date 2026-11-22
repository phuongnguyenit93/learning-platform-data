# Minimizing error examples and comparing IDE configuration with the command line

## Objectives

After this lesson, you can:

1. Turn a Java error that only occurs in a large project into a **minimal reproducible example** (MRE) that others can rerun.
2. Distinguish errors at **compile time**, **launch/class loading**, **execution**, and **testing** before choosing a diagnostic tool.
3. Compare the effective environment in the IDE with the terminal: **JDK/javac**, release level, classpath/module path, dependencies, annotation processors, working directory, arguments, encoding, environment variables, and output directories.
4. Reproduce a case where **the IDE runs successfully while `javac`/`java` commands fail** because a dependency exists only on the IDE's classpath; fix it by declaring complete inputs rather than treating symptoms.
5. Write a bug report containing commands, output, tool versions, and the minimal change proving the root cause.

The lesson uses Java 17+, a shell, and a text editor. The IDE can be IntelliJ IDEA, Eclipse, or VS Code with Java extensions; specific option names may differ across IDEs, but the verification principles remain the same.

## 1. Diagnosing by evidence, not by guessing

A statement like "it runs in the IDE but fails in the terminal" describes a **symptom**, not yet the cause. An IDE often does many things on your behalf: selecting the compiler, identifying sources, resolving dependencies, creating outputs, passing the runtime classpath, setting the working directory, running annotation processors, and possibly delegating builds to Gradle/Maven. The terminal executes only the exact commands, environment variables, and paths you supply.

Therefore, clicking the "Run" button and running `java App` are not necessarily two executions of the same program in the same environment.

A good approach is testing a falsifiable hypothesis:

- Hypothesis: "The terminal is missing the library module's classes."
- Verification evidence: Compile the library into a separate output directory, then add that output to both the compile classpath and runtime classpath.
- Expected result: The compiler stops reporting `package ... does not exist` and the JVM runs with the expected result.
- What cannot be inferred: "Every difference between the IDE and the terminal is caused by the classpath."

The goal of an MRE is to **keep enough components for the error to still reproduce**, while removing unrelated factors until only a single decisive difference remains.

## 2. Classifying errors by phase of occurrence

| Phase | Common symptoms | Questions to ask |
| --- | --- | --- |
| **Compile-time** | `cannot find symbol`, `package ... does not exist`, `incompatible types`, `release version ... not supported` | Are the sources, compiler, release level, and compile classpath right? |
| **Launch/class loading** | `Could not find or load main class`, `ClassNotFoundException`, `NoClassDefFoundError` | Are the fully qualified class name and runtime classpath/module path right? |
| **Linkage/runtime** | `NoSuchMethodError`, `UnsupportedClassVersionError`, application exceptions | Which bytecode/dependencies were loaded by the JVM? Is the runtime compatible? |
| **Test-time** | Assertion failures, fixture errors, tests pass in IDE but fail in CI | Are the test engine, data, timezone, working directory, and configuration the same? |
| **Build-tool/configuration** | Task not found, dependency resolution failure, stale output | Is the IDE delegating builds to Gradle/Maven? Which build profile/toolchain is active? |

Not every exception appearing at runtime is a "runtime classpath error." For example, a `NullPointerException` in business logic and a `NoClassDefFoundError` due to a missing dependency require very different investigation strategies.

**First rule:** save the exact command just run, the first meaningful error, exit code, compiler/runtime versions, and current directory. Do not capture only the last line of the stack trace.

## 3. What is an MRE and how small is small enough?

A good MRE has four properties:

- **Minimal:** keeps only the source, configuration, dependencies, inputs, and steps actually needed for the error to occur.
- **Reproducible:** has clear commands or steps so others can rerun it from a clean state.
- **Complete:** does not rely on a secret file/JAR, undocumented environment variable, or IDE state that the recipient lacks.
- **Observable:** has expected behavior, actual behavior, or a characteristic diagnostic showing that the error still happens.

An MRE does not mean forcing every error into a single file. If the error stems from a classpath mismatch between two modules, **two source files and two output directories** may be the smallest MRE preserving the root cause. Removing the library module just to "make it short" loses the exact bug being tested.

### 3.1 Controlled minimization process

1. **Freeze the symptom:** record the test/method name, command, stack trace or compiler diagnostic, expected, and actual.
2. **Create a copy for investigation:** work in a small project or separate branch; do not break the main source while testing hypotheses.
3. **Identify the failure phase:** compile, launch, link, business logic execution, or test.
4. **Remove in groups:** try removing unnecessary frameworks/configs, unrelated files, annotations, resources, modules, or intermediate layers.
5. **Rerun after each removal:** if the error disappears, restore what was just removed or split it smaller; if the error persists, keep the simpler version.
6. **Fix the environment:** state the exact JDK, compiler options, dependencies, and steps to build outputs.
7. **Test a hypothesis with one change:** for example, only add the library output to the classpath, without simultaneously changing the JDK and editing source.
8. **Keep both the failing and fixed versions:** to show which condition makes the issue appear or disappear.

Decision model:

~~~text
Does the error still reproduce with current data/logic?
        |
        +-- No ---> Restore the removed part, find the boundary causing the error
        |
        +-- Yes --> Can another unrelated component be removed?
                          |
                          +-- Yes --> Remove and rerun
                          |
                          +-- No ---> Record the MRE and verify from a clean build
~~~

This is manual **delta debugging**. For intermittent bugs, also record seeds, trial counts, concurrency, schedulers, and environmental conditions; do not declare "the bug is gone" just because one run failed to reproduce it.

### 3.2 Do not lose the error-triggering condition

For example, if an error only occurs after switching a JAR version: if you minimize by deleting that JAR and replacing it with non-equivalent mock code, the MRE may run normally yet no longer represent the original issue.

For IDE-only errors, keep at least the **IDE run/build configuration** details that create the difference. For file path errors, keep the relative path and working directory; for encoding errors, keep the bytes/encoding and file-reading command.

### 3.3 Recording actual, expected, and confidence level

An example log template:

~~~text
Environment: JDK 17, terminal at the project root directory
Command: javac --release 17 -cp out/empty -d out/app src/app/Main.java
Expected (assuming all dependencies are declared): compilation succeeds
Actual: error package lib does not exist / cannot find symbol
Check: lib output contains lib/Greeter.class; current compile classpath is missing out/lib
Conclusion: missing compile-time dependency in the reproduction command
~~~

The conclusion above is only valid after testing by adding the exact dependency and observing the outcome. A single compiler diagnostic does not prove all possible causes.

## 4. Creating an MRE: classpath mismatch between IDE and terminal

The example uses **two Java 17+ files** with no third-party libraries. Idea: an IDE may automatically add a library module's output to the classpath because it knows the module relationship; whereas a terminal command compiling only the application module reports that the package cannot be found.

### 4.1 Project structure

Create the `ide-cli-repro` project:

~~~text
ide-cli-repro/
├── src/
│   ├── lib/
│   │   └── Greeter.java
│   └── app/
│       └── Main.java
└── out/
    ├── lib/
    ├── app/
    └── empty/
~~~

The three `out` directories are separate outputs; they must be created fresh and kept clearly separated by purpose. From the project root directory, create the directories if they do not exist:

**PowerShell:**

~~~powershell
New-Item -ItemType Directory -Force src/lib, src/app, out/lib, out/app, out/empty | Out-Null
~~~

**Bash/Zsh:**

~~~bash
mkdir -p src/lib src/app out/lib out/app out/empty
~~~

If sources already exist, `-Force` or `-p` does not overwrite or delete source contents. The cleanest experiment is performed in a fresh project.

### 4.2 Library source: `src/lib/Greeter.java`

~~~java
package lib;

public final class Greeter {
    private Greeter() {
    }

    public static String message(String name) {
        return "Xin chao, " + name + "!";
    }
}
~~~

The file has a top-level public class `Greeter` and package name `lib`. The compiler will emit `lib/Greeter.class` under the output root.

### 4.3 Application source: `src/app/Main.java`

~~~java
package app;

import lib.Greeter;

public final class Main {
    public static void main(String[] args) {
        String name = args.length == 0 ? "Java" : args[0];
        System.out.println(Greeter.message(name));
    }
}
~~~

`Main` references `lib.Greeter`. The compiler must know that symbol from **provided sources** or from **class files/JARs on the compiler classpath**.

### 4.4 Reproducing the error when compiling only the application

Before compiling the library, from the project root run:

~~~bash
javac --release 17 -encoding UTF-8 -cp out/empty -d out/app src/app/Main.java
~~~

Because `out/empty` has no `lib/Greeter.class` and there is no `lib` source on the compiler search path, the command fails. The diagnostic typically indicates:

~~~text
package lib does not exist
cannot find symbol
~~~

Do not copy this entire stderr verbatim as "guaranteed output": formatting, line numbers, and caret positions depend on the JDK. What is stable is that **the command fails to compile because `lib.Greeter` cannot be resolved**.

If your IDE runs an equivalent project and automatically builds the `lib` module, it can succeed because the IDE supplies an extra dependency that the terminal command lacked. It is not that the IDE is "smarter than the compiler" about syntax; **the input sets differ**.

### 4.5 Fixing the cause with the proper compile classpath

First compile the library:

~~~bash
javac --release 17 -encoding UTF-8 -d out/lib src/lib/Greeter.java
~~~

Then compile the application with the declared dependency:

~~~bash
javac --release 17 -encoding UTF-8 -cp out/lib -d out/app src/app/Main.java
~~~

`-cp out/lib` is the **compiler classpath**, while `-d out/app` is the **output directory** of the application. Do not confuse these two roles. The class files have the structure:

~~~text
out/
├── lib/
│   └── lib/
│       └── Greeter.class
└── app/
    └── app/
        └── Main.class
~~~

The `lib/lib` part is not a bug: `out/lib` is the **output root**, while `lib/Greeter.class` is the package-relative path.

### 4.6 Running on Linux/macOS

~~~bash
java -cp "out/app:out/lib" app.Main Minh
~~~

Stdout:

~~~text
Xin chao, Minh!
~~~

### 4.7 Running on Windows

In PowerShell or CMD:

~~~powershell
java -cp "out/app;out/lib" app.Main Minh
~~~

Stdout is still:

~~~text
Xin chao, Minh!
~~~

The separator for **multiple classpath entries** on Linux/macOS is a colon (`:`), and on Windows is a semicolon (`;`). The class name `app.Main` contains no slashes and has no `.class` suffix.

### 4.8 Providing only the application runtime classpath: a different error

Now run:

~~~bash
java -cp out/app app.Main Minh
~~~

At this point the JVM finds `app.Main` but cannot find `lib.Greeter` when needed. Typically `NoClassDefFoundError: lib/Greeter` appears with a related `ClassNotFoundException` cause. The specific stack trace is not a fixed output of this lesson.

**Comparing the two errors:**

- `javac ... -cp out/empty ...`: missing dependency **at compile time**, usually `package ... does not exist`.
- `java -cp out/app app.Main`: missing dependency **at runtime**, usually `NoClassDefFoundError`.

An IDE might configure the compile classpath properly while the run configuration uses a runtime classpath missing the library, or vice versa. Therefore, check **both**.

## 5. Analyzing the MRE: what is minimal, and what is not?

In the example above, you can drop logging systems, frameworks, config files, test runners, and unrelated classes, but you must keep:

- `Greeter.java`: defines the dependency.
- `Main.java`: code containing the call to the dependency.
- At least **two compile classpath configurations**: missing `out/lib` and including `out/lib`.
- A separate runtime classpath to demonstrate the class-loading phase error.
- Compile commands and output roots so others do not accidentally run stale classes.

Removing `Greeter` completely and creating a method with the same name inside `Main` will no longer prove what we are looking for. An MRE must be small enough **while still preserving the causal relationship**.

### 5.1 Why clean output matters

An output directory that previously contained `lib/Greeter.class` can make a new compilation accidentally succeed if the classpath points to it. When diagnosing missing dependencies, create **fresh outputs** and use a classpath containing only the intended inputs.

Similarly, if you compile `Main` and then edit the source without rebuilding, the `java` command may be running old bytecode. This is a common cause of "I fixed it in the IDE, yet the terminal still prints old output."

You do not need to wipe the whole workspace to get a clean build. Clean only **output directories that are safe to clean**; do not blindly delete source files, system caches, or shared folders. In practice exercises, starting with a fresh project and fresh output directories avoids risky deletion.

### 5.2 When is a single file the right MRE?

If the bug is simply a `NullPointerException` from a null variable inside a method, a single-file MRE is usually enough. If the bug is due to **two JARs containing the same class name** or an **IDE resource path**, keep the corresponding minimal structure. The smallest size is the point where **nothing more can be removed while the error still reflects the cause under investigation**, not a goal of counting lines.

## 6. Comparing IDE and terminal configurations with a matrix

Compare **effective values**, not just setting names. An IDE may have Project SDK, Module SDK, Gradle JVM, compiler compliance level, and Run Configuration JRE as separate items.

| Check axis | Verify in IDE | Verify in terminal | Mismatch impact |
| --- | --- | --- | --- |
| **Compiler JDK** | SDK/toolchain used at build time, whether build is delegated | `javac -version`; `javac` executable path | Different language/API features; compiler does not support flags |
| **Application runtime JVM** | JRE/JDK in Run Configuration | `java -version`; executable invoked | `UnsupportedClassVersionError` or different behavior |
| **Source/release/target** | Language level, compiler release/compliance | `javac --release 17 ...`, actual flags | Source compiles in one place but fails in another |
| **Compile classpath** | Module dependencies, external libraries, generated classes | `javac -cp ...` / `--class-path` | `package ... does not exist`, `cannot find symbol` |
| **Runtime classpath** | Run configuration, module/JAR selection | `java -cp ...` / `java -jar ...` | `NoClassDefFoundError`, wrong version loaded |
| **Module path** | Java module dependencies, run config | `--module-path`, `--module`, `--add-modules` when applicable | Module does not read/export package |
| **Annotation processors** | Enable/disable processors, processor path, generated sources | `-processorpath`, `-processor`, `-proc:none`, build tool | Missing or different generated classes/code |
| **Output/build cache** | Build/rebuild, source sets, incremental output | `-d`, clean output, loaded class path | Stale `.class` files mask errors |
| **Working directory** | Run Configuration working directory | `pwd`/`Get-Location` | Relative files not found |
| **Arguments** | Program arguments vs. VM options | Arguments after main class; flags before main class | Different input; flags interpreted as data |
| **Environment** | Environment variables, profiles, credentials | `PATH`, `JAVA_HOME`, and relevant variables | Runs against different resources/services |
| **Encoding/locale/timezone** | Editor encoding, file encoding, VM properties | `-encoding UTF-8`; console locale/settings | Corrupted Vietnamese characters, different sorting/dates |
| **Build tool/profile** | Internal IDE build vs. invoking Maven/Gradle | `mvn ...` / `gradlew ...`; profiles/tasks | Two pipelines process different inputs |

Not every item needs immediate comparison. Prioritize by failure phase: if the compiler reports a missing symbol, check compiler options and compile classpath; if the app only fails when reading a file, check the working directory/file content first.

## 7. Gathering evidence of the active compiler and runtime

### 7.1 Windows PowerShell

~~~powershell
Get-Location
Get-Command java
Get-Command javac
java -version
javac -version
~~~

`Get-Command` shows the executable path resolved by the shell. A JDK chosen by the IDE may **differ** from the one found via `PATH` in the terminal.

### 7.2 Linux/macOS Bash/Zsh

~~~bash
pwd
command -v java
command -v javac
java -version
javac -version
~~~

If multiple JDKs exist, record the full paths to `java` and `javac` in each environment. `JAVA_HOME` is useful but does not guarantee that the `java` command on `PATH` uses that directory.

### 7.3 Capturing Java runtime configuration

~~~bash
java -XshowSettings:properties -version
~~~

This command prints runtime info such as `java.home`, `java.version`, `java.class.path`, `file.encoding`, `user.dir`, and other properties (JDK-dependent), usually to stderr. When sharing logs, **filter out sensitive information** such as usernames, personal paths, or tokens present in environment config.

In a Java program, you can also check a specific property:

~~~java
System.out.println(System.getProperty("user.dir"));
System.out.println(System.getProperty("java.class.path"));
~~~

The two lines above are an **illustrative snippet inside a method**; the printed values depend on where the program runs and the actual classpath, with no fixed standard stdout.

### 7.4 More detailed compiler diagnostics

~~~bash
javac -Xdiags:verbose --release 17 -encoding UTF-8 -cp out/empty -d out/app src/app/Main.java
~~~

`-Xdiags:verbose` makes diagnostics more detailed in compiler-supported scenarios. `javac -verbose` shows which source/class files the compiler is loading and writing, though the output can be long:

~~~bash
javac -verbose --release 17 -encoding UTF-8 -cp out/lib -d out/app src/app/Main.java
~~~

When suspecting a stale class, the list of where the compiler is **loading** files from is more valuable than just looking at a "build successful" message.

### 7.5 Diagnosing class sources at runtime

On HotSpot with unified logging (such as many JDK 17+ builds), you can use:

~~~bash
java -Xlog:class+load=info -cp "out/app:out/lib" app.Main Minh
~~~

The command above uses the **Linux/macOS classpath separator**; on Windows switch to `"out/app;out/lib"`. Class loading logs are very long and details depend on the JVM. Look for the path/source of `app.Main` and `lib.Greeter`, rather than memorizing individual log lines.

In programs with duplicate class names across JARs, class-loading source info helps verify whether the runtime uses the intended dependency version.

## 8. Second MRE: different working directories

Not every IDE/CLI difference is the classpath. An IDE Run Configuration might set the working directory to the project root, a module, or another folder; the terminal uses whichever directory you have `cd`'d into.

Create the file **`src/WorkingDirDemo.java`**:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;

public class WorkingDirDemo {
    public static void main(String[] args) throws Exception {
        Path config = Path.of("settings.txt");
        System.out.println(Files.readString(config).strip());
    }
}
~~~

Create the file **`settings.txt`** right at the **project root** with exact contents:

~~~text
mode=demo
~~~

Compile:

~~~bash
javac --release 17 -encoding UTF-8 -d out/app src/WorkingDirDemo.java
~~~

Run from the **project root**:

~~~bash
java -cp out/app WorkingDirDemo
~~~

Stdout:

~~~text
mode=demo
~~~

If the IDE runs the same class while the working directory is another folder not containing `settings.txt`, the program may report `NoSuchFileException: settings.txt`. Bytecode and JDK are identical; the cause is that **relative paths resolve against the working directory**, not the source file's location.

**How to check:** inspect the working directory in Run Configuration; in the terminal run `pwd` or `Get-Location`. If the intent is reading an external file, specify the path explicitly and handle missing-file errors. If the intent is a resource packaged in a JAR, use the classpath resource API rather than assuming it is a file sitting next to source.

### Path to classes does not set the working directory

Even if you run:

~~~bash
java -cp out/app WorkingDirDemo
~~~

`out/app` is where the launcher looks for classes, **not something that automatically changes `user.dir` to `out/app`**. These are two independent concepts.

### Note on encoding

`Files.readString(Path)` reads the file as UTF-8 in this Java 17 example. `javac -encoding UTF-8` controls how the compiler decodes **source code**; it does not change the contents or location of `settings.txt`. Do not try to fix `NoSuchFileException` by changing source encoding.

## 9. Third MRE: mismatched source level and JDK

Create the file **`src/LanguageProbe.java`**:

~~~java
public class LanguageProbe {
    public static void main(String[] args) {
        var total = 4 + 5;
        System.out.println(total);
    }
}
~~~

`var` enables local variable type inference starting in Java 10. Compile with JDK 17+ targeting release 17:

~~~bash
javac --release 17 -encoding UTF-8 -d out/app src/LanguageProbe.java
java -cp out/app LanguageProbe
~~~

Stdout:

~~~text
9
~~~

Try targeting Java 8:

~~~bash
javac --release 8 -encoding UTF-8 -d out/empty src/LanguageProbe.java
~~~

The compiler will reject using `var` under the Java 8 language level; exact diagnostics depend on the JDK. If the IDE sets language level 17 while the build tool's command line targets Java 8, differing behavior is expected.

Note: the `out/empty` directory in this command is only a test output; it does not affect the `LanguageProbe.class` already built in `out/app`. A successful run from the old class **does not prove** the Java 8 compile command succeeded.

### `-source/-target` differs from `--release`

If the compiler runs on a newer JDK than the target runtime, setting only source/target may not suffice to constrain **Java platform APIs**. For example, code with Java 17 syntax calling an API only present in Java 21 may compile using a JDK 21 compiler with `-source 17 -target 17`, even though running on JVM 17 will fail linkage. `--release 17` is what instructs the compiler to enforce the Java 17 language level, platform APIs, and class-file target.

When comparing IDE and terminal configurations, explicitly record **both the javac version and flags**. Do not rely solely on a "language level" number to infer runtime compatibility.

## 10. Annotation processors, generated sources, and build pipelines

Some errors do not reproduce when you simply copy source into a Java file because the real project uses **annotation processing or code generation**.

For example, a library may generate auxiliary sources from annotations at compile time; the IDE enables the annotation processor while manual `javac` lacks the processor on the processor path. In that case, a generated class will not exist.

Points to check:

1. Are processors enabled in the IDE/build tool?
2. Is the processor artifact on the **processor path** or configured appropriately for annotation processing?
3. Where are generated sources written?
4. Is the compiler reading **newly generated sources** or stale artifacts?
5. Are any sources generated by a build step running **before** `javac`?

The `javac -proc:none` option disables annotation processing in compilers that support it. It is useful as a **root-cause isolation test**, not as a fix if the real application requires generated classes.

Example illustrating command differences:

~~~bash
javac -proc:none --release 17 -d out/app src/app/Main.java
~~~

This command is a flag-comparison sample; with the `app.Main` MRE, you still need the `out/lib` compile classpath to resolve `lib.Greeter`. Do not run it and conclude that annotation processors caused the classpath error under test.

**Do not confuse:** an annotation like `@Override` does not by itself require an annotation processor. Only configured and activated processors participate in generating sources/classes during the build.

### When should frameworks/build tools be kept in an MRE?

If the error stems from a code generator, plugin, processor, or dependency resolution, a minimal MRE **may need to keep** a trimmed `pom.xml`/`build.gradle` with the exact tool versions. A single `Main.java` file cannot reproduce build task ordering or generated source issues.

The goal is not eliminating all tools, but **keeping only the exact tooling parts needed for the error to still reproduce**.

## 11. IDE builds vs. build tools in the terminal

An IDE can:

- Compile with its internal compiler or invoke the `javac` of the JDK selected by the IDE.
- Delegate build/run/test to Gradle.
- Import a Maven model while using separate run/test configurations.
- Maintain caches/incremental builds, generated sources, and module output directories.

Therefore, asking "does the IDE have the same config as `javac`?" is sometimes not enough; identify **which compiler the IDE actually runs and with which tasks/flags**.

### 11.1 With Gradle

A Gradle Java project typically has elements such as: Java toolchain, `JavaCompile` tasks, `compileClasspath`, `runtimeClasspath`, `testRuntimeClasspath`, `sourceSets`, and execution tasks. If the IDE delegates to Gradle, Gradle logs are a key source for finding compiler tasks and inputs.

Example commands from a project with Gradle Wrapper:

~~~bash
./gradlew clean classes
./gradlew test
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat clean classes
.\gradlew.bat test
~~~

Tasks exist only if configured by the corresponding plugins/build. `clean` clears outputs managed by Gradle, but does not guarantee that all external system libraries or environment variables match.

To view compiler options in the build script, inspect `options.release`, the Java toolchain, and any relevant `options.compilerArgs`. Do not assume that because the IDE window displays "JDK 17", every Gradle task runs that compiler.

### 11.2 With Maven

When a project uses Maven, you can compare:

~~~bash
mvn clean compile
mvn test
~~~

Check the effective plugin configuration, Maven Compiler Plugin `release`, dependencies, and active profiles. An IDE importing a Maven project can construct classpaths from the model, whereas a manual javac command does not read `pom.xml`.

For example, the command:

~~~bash
javac -d out/app src/app/Main.java
~~~

**does not automatically resolve dependencies declared in the Maven POM**. To create an MRE for a dependency bug, either use a minimal Maven build or manually build a compile classpath containing the exact dependencies to compare.

### 11.3 Comparing two builds as an experiment

Explicitly record:

| Question | IDE | CLI / build tool |
| --- | --- | --- |
| Which source files are compiled? | Which module/source set | Which file list or source task |
| Which Java compiler? | Project SDK/Gradle JVM and task | Path to `javac` or toolchain |
| Release/source level? | Effective setting | `--release`, compiler config |
| Compile dependencies? | Module/library mapping | `-cp` or dependency graph |
| Output root? | IDE output directory | `-d` or build output |
| Runtime JDK? | Run Configuration JRE | `java` binary being invoked |
| Program args and VM args? | Separate configuration fields | Position of each argument on the command line |
| Working directory? | Working directory setting | `pwd`/`Get-Location` |
| Generated sources? | Processor and generated output | Processor task/path and output |
| Clean or incremental? | Rebuild/Invalidate policy | Clean output or clean task |

Then change **one key difference** in the CLI to see whether the error disappears. Changing the JDK, cache, dependencies, and working directory simultaneously makes results hard to explain because you do not know which factor was actually decisive.

## 12. Run commands and argument ordering must match

An example prone to misunderstanding:

~~~bash
java -cp out/app app.Main Minh
~~~

In this invocation:

- `-cp out/app` is the **launcher option** and classpath value.
- `app.Main` is the **fully qualified name** of the class with `main`.
- `Minh` is a program argument, placed in `args[0]`.

However, in:

~~~bash
java app.Main -cp out/app Minh
~~~

after `app.Main`, tokens are passed to the application as program arguments. `-cp` no longer configures the launcher. If the environment does not already have the right classpath, the command may fail to load the class or misbehave with unexpected arguments.

When comparing IDE and terminal, separate **VM options** from **Program arguments**. Swapping the two groups can make you think code behavior changed even though configuration was simply passed in the wrong position.

### IDE running tests instead of main

The "Run Test" button may invoke JUnit/TestNG or the Gradle/Maven runner, creating a separate classpath and fixture. The command `java -cp ... app.Main` is a different program entrypoint. If the error occurs only in tests, the MRE should include **the test class and appropriate test runner**; you cannot draw conclusions from the main program running normally.

## 13. Avoiding "source edited but terminal still runs old version"

An IDE may compile automatically when you click Run, whereas the plain `java` command **does not compile `.java` files** sitting in the project. If you edit `src/app/Main.java` and only run `java -cp out/app app.Main`, the JVM still loads the `Main.class` created from the previous compilation.

Proper workflow when source changes:

~~~bash
javac --release 17 -encoding UTF-8 -cp out/lib -d out/app src/app/Main.java
~~~

Then run using a classpath containing both app and lib according to the operating system.

Note: `java path/to/File.java` offers **source-file mode** on supported JDKs, but that is a different execution mode. Do not silently switch between `java -cp ... app.Main` and `java src/app/Main.java` within the same experiment without noting the difference; source-file mode has its own rules and limits regarding classpath, packages, and compilation.

### Classes with the same name in multiple directories

If class `app.Main` appears in both `out/app` and an old JAR, Java class loading may choose based on classpath order and class loaders. When a run prints stale output, check the loaded class source via logs or a simple marker in the new example; do not guess that the JVM definitely runs the `.class` file you just looked at.

## 14. Common mistakes when minimizing and comparing environments

| Symptom | Diagnostic mistake | Right direction |
| --- | --- | --- |
| Removing classes makes the error "disappear" | Thinking the bug is solved, when you actually removed the error-triggering code path | Restore the minimal part that brings the error back |
| IDE compiles, `javac` reports missing symbol | Only editing imports or creating fake classes | Compare compile classpath and source sets |
| CLI compiles, `java` fails with `NoClassDefFoundError` | Continuing to add compiler flags | Check runtime classpath/module path |
| IDE cannot find config file | Changing source encoding or redoing dependencies | Compare working directory and file paths |
| Different source levels | Looking only at `java -version` | Check `javac -version` and compiler flags |
| Error only in CI | Blaming CI while ignoring local caches | Reproduce from clean checkout/output and declared dependencies |
| Output unchanged after editing | Assuming the JVM ignored source | Recompile and check loaded output/classes |
| Annotation-generated class missing | Hand-writing a new class in the MRE to bypass | Keep minimal processor/task and compare processing configs |
| Same class name in two JARs | Checking only filenames without versions/paths | Trace class loading sources and dependency graphs |
| Changing 5 settings at once fixes the error | Over-concluding about a single cause | Retest each variable individually to isolate causality |
| Bug report without reproduction commands | Others cannot verify it | Provide minimal source, commands, JDK, expected/actual |
| Copying logs containing tokens or private paths | Exposing unnecessary information | Redact secrets and sensitive info while keeping enough for debugging |

## 15. Effective workflow for a real bug

### Step 1 — Record the original failure

Copy the error log including the root cause, record IDE/version if applicable, JDK compiler/runtime, build tool, OS, branch/commit when relevant, and how to trigger the error. Do not equate "error when clicking Run" with "compiler error."

### Step 2 — Identify the phase

Ask in order: Did the IDE/build tool finish compiling? Can the JVM load the main class? Did the error happen immediately during class loading or after business code ran? Was the same input used?

If the compiler has not finished, changing runtime VM options usually will not fix a `cannot find symbol` error.

### Step 3 — Establish a command-line baseline

From the project directory, print:

~~~bash
java -version
javac -version
~~~

Use explicit paths and classpaths to compile and run. If the project relies on Gradle/Maven, run the system's exact build task to get a baseline. Record the output and exit status, not just the IDE UI state.

### Step 4 — Minimize

Remove unrelated dependencies, modules, classes, methods, or code snippets one at a time; rerun after each change. When the error disappears, identify the last change and restore part of it to find the essential condition.

### Step 5 — Compare against the matrix

Based on the failure phase, select the corresponding axes: compiler JDK, `--release`, source path, compile classpath, output; or JVM, runtime classpath, working directory, VM args, program args, environment.

### Step 6 — Test exactly one variable

For the MRE in section 4, the only difference to test is **adding `out/lib` to the compile classpath**. If compilation goes from failing to succeeding, that is evidence supporting the missing-dependency hypothesis. Then test adding `out/lib` to the runtime classpath to check the runtime phase.

### Step 7 — Verify from a clean state and on supported environments

Use fresh outputs, locked dependency versions, and recorded compiler/runtime versions. If your bug is CI-only or production-only, test under equivalent conditions rather than only inside a local IDE.

### Step 8 — Write a regression test or guard

Once the cause is verified, add tests or configuration checks accordingly: clean builds, classpath tests, smoke tests under the target runtime, or assertions for inputs exposing the bug. This helps detect configuration drift in the future.

## 16. Bug report template to share with teammates

~~~text
Title:
  Compilation succeeds in the IDE but javac CLI cannot find lib.Greeter.

Environment:
  JDK: 17 (both javac and java)
  OS / shell: state the actual one
  Working directory: <ide-cli-repro root directory>
  Build mode: direct javac CLI (no Gradle/Maven)

Source:
  src/lib/Greeter.java
  src/app/Main.java

Command to reproduce:
  javac --release 17 -encoding UTF-8 -cp out/empty -d out/app src/app/Main.java

Actual:
  Compilation failed: package lib does not exist / cannot find symbol.

Expected:
  Once the lib module dependency is provided, compilation should succeed.

Differential experiment:
  javac --release 17 -encoding UTF-8 -d out/lib src/lib/Greeter.java
  javac --release 17 -encoding UTF-8 -cp out/lib -d out/app src/app/Main.java

Result:
  The second application compilation command succeeded.
  Running java with out/app and out/lib outputs "Xin chao, Minh!"

Assessment:
  The command-line compile classpath is missing the lib module.
  The IDE may have added the lib module output per the project model;
  verify this against the actual IDE configuration.
~~~

This is a report template **for the practice exercise**, not information from a specific tested environment. When reporting real bugs, replace placeholder lines with observed values; do not include credentials, API keys, or personal data in logs.

## 17. Self-practice exercises

### Exercise 1 — Distinguishing two errors in the same project

With `src/lib/Greeter.java` and `src/app/Main.java`:

1. Compile the application with `-cp` pointing only to `out/empty`.
2. Compile the library, then compile the application with `-cp out/lib`.
3. Run the application with only `out/app`.
4. Rerun with both `out/app` and `out/lib`.

**Answer:** (1) compile-time missing symbol; (2) compilation succeeds; (3) runtime cannot find `lib.Greeter`; (4) the program prints `Xin chao, Minh!` when given argument `Minh`. Errors (1) and (3) occur in different phases.

### Exercise 2 — Explaining the classpath root

Why is it right to use:

~~~bash
javac -cp out/lib -d out/app src/app/Main.java
~~~

instead of `-cp out/lib/lib`?

**Answer:** `out/lib` is the classpath root, under which lies the package path `lib/Greeter.class`. The compiler/JVM appends the package name to the root to locate the class.

### Exercise 3 — Same bytecode, different working directory

Use `WorkingDirDemo` and `settings.txt`. Why does running from the project root succeed while running from another directory can hit `NoSuchFileException`?

**Answer:** `Path.of("settings.txt")` is a relative path, depending on the working directory. This is not a classpath error for `WorkingDirDemo.class`.

### Exercise 4 — Mismatched source level

Build `LanguageProbe` with `--release 17` and then try `--release 8`. Why might source code be valid in the IDE yet rejected by the CLI compiler?

**Answer:** The IDE or build task is using a different language level. `var` has been supported since Java 10, not in Java 8.

### Exercise 5 — Minimizing a dependency error

A project has 40 classes, 5 libraries, and 3 modules. The actual error is failing to find `lib.Greeter` when compiling `app.Main`. What would you keep in the MRE?

**Answer:** Keep the dependency source and application source, the compile command for the library module, the compile command for the application, the failing/working classpaths, and the output roots. Drop classes, JARs, resources, and tests that do not contribute to the error. If the error requires a build tool, keep the smallest configuration file reproducing the exact dependency relationship.

### Exercise 6 — Identifying the cause instead of just "it ran"

The IDE and CLI differ in JDK, classpath, and working directory. After changing all three, the error disappears. Can you conclude that classpath was the sole cause?

**Answer:** Not yet. You must test each change individually or create an MRE holding the other two variables fixed to identify the decisive factor.

### Exercise 7 — Diagnosing stale class files

You deleted `OldApi.java` source, yet the application still resolves `OldApi` in the terminal. State a hypothesis and a safe test.

**Answer:** An old `OldApi.class` may remain on the compile classpath or in a JAR. Create a **fresh** output directory, compile with explicitly declared dependencies, and check which file/JAR is being loaded. Do not blindly delete shared directories.

## 18. Completion checklist

- [ ] I clearly stated **expected** and **actual**.
- [ ] I classified the error into the right phase: compile, launch, runtime, or test.
- [ ] The MRE keeps only the sources/dependencies/configs needed for the error to persist.
- [ ] Someone else can create fresh outputs and rerun the commands from scratch.
- [ ] I know which versions of the `javac` compiler and `java` JVM are being used.
- [ ] I compared the compiler classpath and runtime classpath.
- [ ] I checked the working directory, program arguments, and VM options.
- [ ] When using a build tool, I know whether the IDE delegates or compiles internally.
- [ ] I am not drawing conclusions from stale class outputs or undeclared environments.
- [ ] I tested one variable at a time and kept before/after evidence.
- [ ] I removed secrets and sensitive information from shared logs.
- [ ] I have a test/guard to prevent the error from recurring.

## Key takeaways

**An MRE is not just short code; it is an experiment with enough facts to reproduce the cause.** When the IDE and command line produce different results, inspect the **effective configuration**: compiler, JDK, release, compile/runtime classpath, working directory, arguments, build tool, generated sources, and output. Minimizing errors step by step, changing one variable at a time, and verifying on clean builds is far more reliable than tinkering randomly until the program happens to run.