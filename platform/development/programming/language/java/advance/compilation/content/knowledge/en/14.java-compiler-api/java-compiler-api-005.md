# Creating a CompilationTask with getTask and Passing Compiler Options

## 1. Why Is the JavaCompiler API Needed?

Normally, a compilation run is invoked from a terminal:

~~~bash
javac --release 17 -encoding UTF-8 -d build/classes src/demo/Hello.java
~~~

With Java's **Compiler API** (JSR 199, package `javax.tools`, module `java.compiler`), a Java program itself can create a compilation run, pass source files, options, and class output locations, and receive diagnostics without parsing logs from a shell command. This is useful for editors, code generators, submission testing systems, build integrations, and Java source verification programs.

Operation flow:

~~~text
ToolProvider.getSystemJavaCompiler()
               |
               v
JavaCompiler + StandardJavaFileManager
               |
       JavaFileObject SOURCE
       List<String> options
       DiagnosticListener / Writer
               |
               v
      compiler.getTask(...)
               |
        CompilationTask
               |
             call()
               |
      Boolean success + diagnostics
               |
       .class at CLASS_OUTPUT
~~~

**`getTask` only creates the task; `CompilationTask.call()` actually performs the compilation.** The compile result does not automatically run the newly generated Java program. To run the class afterward, you need a JVM/class loader with the corresponding runtime classpath.

Article objectives: understand all six parameters of `getTask`, use `JavaFileObject` properly, convert compiler options into an argument list, collect structured diagnostics, read success/failure results, and manage the file manager lifecycle.

## 2. Related APIs and Responsibilities

| API | Role |
| --- | --- |
| `ToolProvider.getSystemJavaCompiler()` | Obtains the Java compiler provided by the runtime, if available |
| `JavaCompiler` | Creates `CompilationTask` and file managers |
| `JavaCompiler.CompilationTask` | Represents one compilation run; invoke `call()` |
| `StandardJavaFileManager` | Converts `File`/`Path` to `JavaFileObject` and locates/writes files |
| `JavaFileObject` | Abstracts a Java source or class file |
| `DiagnosticCollector<JavaFileObject>` | Collects structured errors/warnings |
| `Diagnostic.Kind` | Classifies `ERROR`, `WARNING`, `NOTE`, and other kinds |
| `StandardLocation` | Specifies standard locations such as `CLASS_OUTPUT`, `CLASS_PATH`, `SOURCE_PATH` |
| `SimpleJavaFileObject` | Base class if you want to provide source directly from a string |

For a named Java module, the host using the Compiler API must declare:

~~~java
module my.compiler.host {
    requires java.compiler;
}
~~~

This is a **module-info.java fragment**, not a standalone program. If the host runs on the classpath of a full JDK, `javax.tools` can be used like ordinary standard Java packages.

Important point: `getSystemJavaCompiler()` can return `null` on a runtime image that does not contain a compiler provider. Having `java` to run an application does not mean `javac` or `jdk.compiler` is always present. Check the result before using the API.

## 3. JavaCompiler.getTask Signature and Its Six Parameters

~~~java
JavaCompiler.CompilationTask getTask(
        Writer out,
        JavaFileManager fileManager,
        DiagnosticListener<? super JavaFileObject> diagnosticListener,
        Iterable<String> options,
        Iterable<String> classes,
        Iterable<? extends JavaFileObject> compilationUnits);
~~~

This is an **interface signature** for learning the API, not an independent runnable class.

| Parameter | Meaning | Common usage |
| --- | --- | --- |
| `out` | Writer for additional output; if null, the tool uses stderr by default | `new PrintWriter(System.err, true)` |
| `fileManager` | Service for locating/reading/writing sources/classes | `compiler.getStandardFileManager(...)` |
| `diagnosticListener` | Receives structured compiler diagnostics | `DiagnosticCollector<JavaFileObject>` |
| `options` | List of compiler options as individual arguments | `List.of("--release","17","-d","build/classes")` |
| `classes` | Names of classes designated for **annotation processing**, not regular source files to compile | `null` |
| `compilationUnits` | Iterable of `JavaFileObject` with `Kind.SOURCE` to compile | `manager.getJavaFileObjectsFromPaths(...)` |

**Especially easy to confuse:** `classes` is not where you put `"src/demo/Hello.java"`; pass a source file as a `JavaFileObject` in the `compilationUnits` parameter. Meanwhile, `options` holds compiler flags, not the entire shell command or CLI-style source file list. In ordinary source compilation tasks, `classes = null`.

If `fileManager = null`, the compiler uses a standard file manager. If `diagnosticListener = null`, the compiler uses its default error reporting mechanism; when a listener is supplied, some output that does not fit the `Diagnostic` interface may still be written to the writer/default channel. Do not rely on a `StringWriter` having no output to conclude the task succeeded.

## 4. Complete, Tested Java 17+ Example

Create the directory tree:

~~~text
project/
├── CompileWithApi.java
├── src/
│   └── demo/Hello.java
└── build/
    ├── tool/       # host class
    └── classes/    # output of compiler invoked via the API
~~~

### 4.1. File src/demo/Hello.java

~~~java
package demo;

public final class Hello {
    public static void main(String[] args) {
        System.out.println("Hello, Compiler API");
    }
}
~~~

### 4.2. File CompileWithApi.java

~~~java
import java.io.IOException;
import java.io.PrintWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Locale;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public final class CompileWithApi {
    public static void main(String[] args) throws IOException {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Expected: source-file output-directory");
        }

        Path source = Path.of(args[0]);
        Path output = Path.of(args[1]);
        Files.createDirectories(output);

        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException(
                    "A JDK compiler is required");
        }

        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();

        boolean success;
        try (StandardJavaFileManager manager =
                     compiler.getStandardFileManager(
                             diagnostics,
                             Locale.ROOT,
                             StandardCharsets.UTF_8)) {

            Iterable<? extends JavaFileObject> units =
                    manager.getJavaFileObjectsFromPaths(
                            List.of(source));

            List<String> options = List.of(
                    "--release", "17",
                    "-encoding", "UTF-8",
                    "-d", output.toString(),
                    "-proc:none");

            JavaCompiler.CompilationTask task = compiler.getTask(
                    new PrintWriter(System.err, true),
                    manager,
                    diagnostics,
                    options,
                    null,
                    units);

            success = Boolean.TRUE.equals(task.call());

            for (Diagnostic<? extends JavaFileObject> d :
                    diagnostics.getDiagnostics()) {
                System.err.printf(Locale.ROOT,
                        "%s at line %d: %s%n",
                        d.getKind(),
                        d.getLineNumber(),
                        d.getMessage(Locale.ROOT));
            }
        }

        System.out.println(success ? "COMPILE_OK" : "COMPILE_FAILED");
        if (!success) {
            System.exit(1);
        }
    }
}
~~~

**Behavior explanation:**

1. `Files.createDirectories(output)` creates the output directory so the compiler has a place to write `.class`.
2. `ToolProvider.getSystemJavaCompiler()` retrieves the compiler of the JVM/JDK running the host. When a provider is missing, it stops with a clear message.
3. `getStandardFileManager` takes `Locale.ROOT` and `UTF-8` to specify how source is read and diagnostics are displayed.
4. `manager.getJavaFileObjectsFromPaths(List.of(source))` creates a compilation unit for the source file, without automatically scanning every Java file in a directory.
5. `options` passes `--release`, `-encoding`, `-d`, and `-proc:none` as **separate string arguments**. `-proc:none` deliberately disables annotation processing so the example does not depend on external processors.
6. `compiler.getTask(...)` creates the task; `task.call()` executes compilation; `Boolean.TRUE` means success.
7. `DiagnosticCollector` stores errors and warnings; the program prints each diagnostic to stderr.
8. `try-with-resources` closes `StandardJavaFileManager` when finished, releasing JAR/file reading resources.
9. The host prints status on stdout; if compilation fails, the host exits with a non-zero code so scripts/CI detect it.

### 4.3. Compile/run commands

From the project directory in Bash (Linux/macOS/Git Bash):

~~~bash
mkdir -p build/tool build/classes
javac --release 17 -encoding UTF-8 -d build/tool CompileWithApi.java
java -cp build/tool CompileWithApi src/demo/Hello.java build/classes
java -cp build/classes demo.Hello
~~~

Stdout of the command **running the Compiler API host**:

~~~text
COMPILE_OK
~~~

Stdout of the command **running the newly compiled class**:

~~~text
Hello, Compiler API
~~~

These are two programs run in two separate steps. There is no external `javac src/demo/Hello.java` command: the host itself performs this compilation run.

The example was tested on **OpenJDK 21 with `--release 17`**, and the two output lines above were observed directly.

On Windows PowerShell, replace the directory-creation command with:

~~~powershell
New-Item -ItemType Directory -Force build/tool, build/classes | Out-Null
~~~

The remaining two `java -cp` commands stay the same because each classpath has a single entry. With multiple entries: Linux/macOS use a colon (`:`), Windows uses a semicolon (`;`); quote the classpath if the shell requires it.

## 5. When Source Has Errors: task.call and DiagnosticCollector

Also create **src/demo/Broken.java**:

~~~java
package demo;

public final class Broken {
    MissingType value;
}
~~~

`MissingType` is undeclared, so when running:

~~~bash
java -cp build/tool CompileWithApi src/demo/Broken.java build/classes
~~~

the host still creates `CompilationTask`, but compilation fails; `task.call()` returns false. The host prints status:

~~~text
COMPILE_FAILED
~~~

Errors such as `cannot find symbol` are printed to stderr. **The line above is only stdout produced by the host**, not the full compiler stderr; wording, line numbers, and diagnostic counts may vary across JDKs. The host exits with code 1, helping callers recognize that the task failed.

When integrating with an IDE or CI, preserve `Diagnostic.Kind`, file position, and message, but do not write tests depending on a verbatim formatted stderr snippet. In the code above, `d.getLineNumber()` can return the actual error position, or a sentinel if the diagnostic has no position.

A failed task run does not necessarily wipe old outputs. To avoid accidentally using a previous class, compile into a fresh/clean output directory when verifying results.

## 6. Passing Compiler Options: Important Rules

**In the API, options is a list of strings**, not a single whitespace-separated shell command string.

Terminal command:

~~~bash
javac --release 17 -encoding UTF-8 -d build/classes -classpath lib/api.jar src/demo/Hello.java
~~~

Converts to:

~~~java
List<String> options = List.of(
        "--release", "17",
        "-encoding", "UTF-8",
        "-d", "build/classes",
        "-classpath", "lib/api.jar");

// Source files go through compilationUnits, not inside options.
~~~

**Wrong:**

~~~java
List<String> wrong = List.of("--release 17", "-d build/classes");
~~~

`"--release 17"` is a single string, not two compiler arguments. Unless a specific option supports a joined form such as `--key=value`, place the option and value as separate elements.

| Option | Meaning and notes |
| --- | --- |
| `--release 17` | Restricts syntax, bytecode, and Java SE APIs to the supported release |
| `-d outputDir` | Selects the directory to write `.class` files; create the directory beforehand |
| `-encoding UTF-8` | Sets the source charset; should match the file manager |
| `-cp paths` or `-classpath paths` | Compile dependencies: JARs and class directories; `paths` is **one argument** with the OS path separator |
| `--source-path roots` | Where to search for related sources; does **not** automatically request compiling every file |
| `--module-path paths` | Module dependencies in JPMS |
| `-processor name` | Selects a specific annotation processor |
| `-processorpath paths` | Where to look for processor code |
| `-proc:none` | Disables annotation processors for this compile run |
| `-Xlint:all` | Enables additional compiler warnings |
| `-Werror` | Makes warnings cause the build to fail |

**Do not put an entire shell command verbatim** into a single options element, and do not add `src/demo/Hello.java` to options as if it were the trailing command-line argument. Source inputs belong in `compilationUnits`.

**`-J-Xmx512m` is not how to configure heap for the JavaCompiler API.** The `-J` flag is for the `javac` launcher to pass arguments to the JVM running javac. When the host invokes the Compiler API in the same JVM, configure heap on **the JVM running the host**, for example:

~~~bash
java -Xmx512m -cp build/tool CompileWithApi src/demo/Hello.java build/classes
~~~

`compiler.isSupportedOption(optionName)` can check whether the compiler recognizes an option and its argument count per the contract. Even if an option is supported, a specific combination of options and values can still be invalid or absent from the filesystem.

### --release differs from just -source / -target

`--release 17` controls the source language, class file version, and APIs of the target Java platform release. Using only `-source 17 -target 17` lacks a full API barrier when cross-compiling for an older release on a newer JDK. A host using the Compiler API must also select the right toolchain and target version, rather than omitting release configuration just because the host itself runs on a newer JDK.

## 7. File Manager Locations vs. -d / -cp

Example using compiler options:

~~~java
List<String> options = List.of("-d", "build/classes");
~~~

Another approach is configuring **StandardJavaFileManager** with `StandardLocation`:

~~~java
// Host fragment, with manager already created and output directory existing.
manager.setLocationFromPaths(
        javax.tools.StandardLocation.CLASS_OUTPUT,
        List.of(Path.of("build/classes")));

manager.setLocationFromPaths(
        javax.tools.StandardLocation.CLASS_PATH,
        List.of(Path.of("lib/api.jar")));
~~~

`CLASS_OUTPUT` specifies where bytecode is written, `CLASS_PATH` specifies compiled dependencies, `SOURCE_PATH` is the root for finding Java sources, and `SOURCE_OUTPUT` is where annotation processors write generated sources. Do not mix up these locations.

`setLocationFromPaths` takes a `Collection` of `Path` values and replaces the previous search path for that location; an output location must satisfy the contract, typically **an existing directory**. For `CLASS_PATH`, multiple JAR and directory paths can be provided.

**Choose one configuration source per location.** If you already set `CLASS_OUTPUT` in the file manager, do not simultaneously pass `-d` pointing to another directory and expect no conflict. Using `-d` in the main example is the simplest way for learners to observe compile output.

**The host's classpath differs from the compiled program's compile classpath:** running `java -cp build/tool CompileWithApi` only lets the JVM load the host. The `Hello.java` source may have external dependencies, in which case the compile task needs its own classpath in options/file manager. After compiling, running the program requires a runtime classpath containing those classes/JARs.

## 8. Diagnostic and Writer Are Two Separate Channels

`DiagnosticCollector<JavaFileObject>` stores the structure of each diagnostic. You can inspect:

~~~java
// Host fragment having a valid diagnostics variable.
for (Diagnostic<? extends JavaFileObject> d
        : diagnostics.getDiagnostics()) {
    System.out.println("kind=" + d.getKind());
    System.out.println("code=" + d.getCode());
    System.out.println("line=" + d.getLineNumber());
    System.out.println("column=" + d.getColumnNumber());
    System.out.println("message=" + d.getMessage(Locale.ROOT));
}
~~~

- `getKind()`: error, warning, note, etc.
- `getSource()`: source file object if the diagnostic relates to a file; may be null.
- `getLineNumber()` / `getColumnNumber()`: position if available; may be `Diagnostic.NOPOS`.
- `getCode()`: diagnostic code supplied by the compiler.
- `getMessage(Locale)`: human-readable message, which may vary by JDK version or locale.

Compiler errors can appear in the collector; additional information may still go through `out`, and diagnostics not tied to a specific source may lack line numbers. Therefore, do not rely solely on an empty Writer or exact error message string matching.

To determine success, use **the Boolean from `call()`**; to explain failure, use **the diagnostics list**, along with any exceptions thrown while setting up the file manager/options.

## 9. Selecting Multiple Source Files and In-Memory Sources

`getJavaFileObjectsFromPaths` allows compiling multiple files:

~~~java
// Fragment: both files must exist; a valid manager is required.
Iterable<? extends JavaFileObject> units =
        manager.getJavaFileObjectsFromPaths(List.of(
                Path.of("src/demo/Hello.java"),
                Path.of("src/demo/Helper.java")));

JavaCompiler.CompilationTask task =
        compiler.getTask(null, manager, diagnostics,
                options, null, units);
~~~

That is a **fragment**, not a standalone program; distinct from the path list in the classpath. The compiler processes the exact initial compilation units and searches for additional dependencies per the corresponding configuration.

Sometimes source is generated in memory. Use `SimpleJavaFileObject` instead of forcing temporary disk files:

~~~java
// Fragment: imports java.net.URI and javax.tools.SimpleJavaFileObject.
final class TextSource extends SimpleJavaFileObject {
    private final String source;

    TextSource(String qualifiedName, String source) {
        super(URI.create("string:///"
                + qualifiedName.replace('.', '/')
                + Kind.SOURCE.extension), Kind.SOURCE);
        this.source = source;
    }

    @Override
    public CharSequence getCharContent(boolean ignoreEncodingErrors) {
        return source;
    }
}
~~~

Then:

~~~java
// Host fragment having compiler, manager, diagnostics, and options.
JavaFileObject input = new TextSource(
        "demo.Generated",
        "package demo; public class Generated {}");
JavaCompiler.CompilationTask task = compiler.getTask(
        null, manager, diagnostics, options, null, List.of(input));
boolean success = Boolean.TRUE.equals(task.call());
~~~

**Distinction:** this is **in-memory source**, not automatically **in-memory class output**. With the standard file manager, compiled classes may still be written to the filesystem. Keeping bytecode in memory requires a custom `JavaFileManager`/`JavaFileObject` and an appropriate class loader.

`compilationUnits` must consist of file objects representing `Kind.SOURCE`. Passing an object of another kind or an invalid option into `getTask` can throw `IllegalArgumentException` before `call()` executes. Do not confuse an API setup exception with a diagnostic for a Java source missing a type.

## 10. Annotation Processing, classes, and Task Lifecycle

`CompilationTask` also provides setters such as `setProcessors(Iterable<? extends Processor>)` and `setLocale(Locale)` for configuring before compiling. Conceptual example:

~~~java
// Fragment: processors, compiler, manager, diagnostics, options, and units available.
JavaCompiler.CompilationTask task = compiler.getTask(
        null, manager, diagnostics, options, null, units);
task.setProcessors(processors);
task.setLocale(Locale.ROOT);
boolean ok = Boolean.TRUE.equals(task.call());
~~~

Setters must be called **before `call()`**. The `classes` parameter of `getTask` is for names of classes to be processed by annotation processors when appropriate; it is **not** class names to load/run, not a list of source files, and is usually left null.

If the project uses annotation processors, deliberately configure the processor path, discovery, generated source output, and rounds. The runnable example in section 4 passes `-proc:none` to prevent any processor incidentally present in the environment from altering results. When using processors, omit this flag and configure per the build tool.

A `CompilationTask` instance is for **a single `call()` invocation**. To compile again, create a new task; the standard file manager may be reused **for sequential compile runs** while still open, reducing JAR/directory reading overhead. Do not assume a task or custom file manager is safe for concurrent use across multiple threads.

## 11. Exception Handling, Resources, and Safety Limits

There are three status categories:

1. **No compiler:** `getSystemJavaCompiler() == null`; no task can be created.
2. **Invalid inputs/options:** `getTask` can throw `IllegalArgumentException` or an exception from a supplied component; such errors do not necessarily become normal diagnostics.
3. **Compilation ran but source is invalid:** `task.call()` returns `false` and the listener receives diagnostics; the host should report failure with an appropriate exit code.

Also manage:

- Use **try-with-resources** for the file manager. If reusing a file manager multiple times, close it after the last run and avoid races between tasks.
- Create the output directory intentionally; do not assume a failed compile rolls back all previously written files. If transactional output is needed, compile into a temporary directory and publish only upon success.
- Do not assume newly compiled classes are already loaded into the host's class loader. Runtime has its own classpath and module path.
- With named modules, choose `--module-path`, `--module-source-path`, and module-oriented locations per JPMS; `getTask` does not automatically resolve all dependencies.
- **The Compiler API is not a sandbox.** Annotation processors can execute code inside the compile JVM, and newly generated programs can be dangerous if executed. For untrusted source, enforce process/OS isolation and limit I/O permissions, time, CPU, memory, and processor policies. `-proc:none` is not a substitute for isolation.

## 12. Comparing getTask, Tool.run, and Out-of-Process javac

| Approach | Characteristics | Suitable scenarios |
| --- | --- | --- |
| `JavaCompiler.getTask` | API with compilation units, file manager, and structured diagnostics | Compiler hosts, IDEs/plugins, verifying/generating Java source |
| `JavaCompiler.run(...)` | Tool interface taking command-line-style arguments and returning a numeric status code | Simple CLI-style compiler invocation inside the JVM |
| Separate `javac` process | Has an OS process boundary, output, and exit code | Using a different compiler toolchain or needing process isolation for the compiler |

`getTask` runs the compiler via the host's existing API. It does not select a different JDK just from the `--release 17` target. If a specific JDK compiler version is needed, select the toolchain or launch an appropriate process.

## 13. Common Errors and How to Avoid Them

| Symptom | Reason | Resolution |
| --- | --- | --- |
| `compiler == null` | Runtime lacks a compiler provider | Use a JDK with a compiler or deploy the toolchain |
| `getTask` rejects option | Passed single string `"--release 17"` or unsupported option | Pass tokens individually; check compiler/JDK |
| Class output missing | Missing `-d` / `CLASS_OUTPUT`, wrong output dir | Create and explicitly specify output dir |
| Desired source not compiled | Failed to pass `JavaFileObject` into `compilationUnits` | Build units from the exact source files |
| Passed files into `classes` | Confused with class names for annotation processing | Pass `classes=null` when compiling source |
| Diagnostics hard to read | Missing collector or missing locale/source positions | Use `DiagnosticCollector` and read positions |
| Task fails yet script treats as success | Ignored `Boolean call()` | Check true/false; return nonzero when appropriate |
| `ClassNotFoundException` running new class | Runtime classpath lacks output dir | Run with `-cp build/classes` or appropriate loader |
| Compile passes but dependency missing at runtime | Compile/runtime classpaths differ | Control dependencies in both phases |
| Second task fails when calling `call()` again | Reused task object | Create a new `CompilationTask` |
| Annotation processor does not run | `-proc:none` passed or missing processor config | Enable and configure processors intentionally |
| Compiling untrusted code in same JVM | Risks from processors, file I/O, class loading | Isolate the environment and execution permissions |

## 14. JavaCompiler API Testing Checklist

Before `getTask`:

- Have you verified a JavaCompiler provider exists?
- Have you accurately selected the `.java` files to compile and converted them into `JavaFileObject.Kind.SOURCE`?
- Are `options` properly split into separate arguments, and are the paths/release appropriate?
- Do the compile classpath/module path and annotation processor options match the source set?
- Does the output directory exist, and does `-d` avoid conflicting with file manager locations?

After `call()`:

- Is the result actually `Boolean.TRUE`, rather than merely not throwing an exception?
- Are there `ERROR` diagnostics, warnings, or positions that need reporting to the user?
- Is the class output located in the exact expected directory?
- Was the file manager closed cleanly per its lifecycle?
- Has the compiled program been run/tested with the proper runtime classpath and toolchain?
- Was a failed compilation masked by stale output?

### Practice exercises

1. Create `CompileWithApi.java` and `src/demo/Hello.java` as in section 4. Compile the host and run it; verify `COMPILE_OK`. Run the output class; verify `Hello, Compiler API`.
2. Add `Broken.java` with `MissingType`; run the host to receive `COMPILE_FAILED` and diagnostics; do not assert stderr has a fixed exact number of lines.
3. Replace `--release 17` with another release supported by your JDK; inspect the bytecode major version with `javap -verbose` and ensure code/APIs match.
4. Use `StandardLocation.CLASS_OUTPUT` instead of `-d`; ensure no two conflicting output locations are declared.
5. Create a new second task with another source file, try reusing the file manager sequentially, and then close resources.
6. When annotation processing is genuinely needed, remove `-proc:none`, configure processors, and observe generated sources/diagnostics.

**Conclusion:** creating a `CompilationTask` properly requires three things: **sources as `JavaFileObject`**, **options as a list of separate arguments**, and **`task.call()` checked alongside diagnostics**. The API provides programmatic compiler control in Java code, without replacing management of JDKs, dependencies, runtimes, or secure execution environments.

## References

- [Java SE 17 — JavaCompiler](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.html): `getTask` signature, file managers, and diagnostics.
- [Java SE 17 — StandardJavaFileManager](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/StandardJavaFileManager.html): obtaining file objects from Path, configuring locations.
- [Java SE 17 — JavaCompiler.CompilationTask](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.CompilationTask.html): `call()`, `setProcessors`, `setLocale`.
- [JDK 17 — javac](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): compiler options, source/target/release.