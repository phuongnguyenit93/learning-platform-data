# Creating a CompilationTask with getTask and Reading the call Result

## 1. Use Case: Compiling Java While the Application Is Running

A Java application sometimes needs to accept Java source code at runtime and turn it into bytecode without invoking the **javac** command in a separate OS process. Examples include a programming learning tool compiling user-submitted exercises, a plugin platform generating implementations from controlled templates, or a system building auto-generated code.

Java provides the **Java Compiler API** in package **javax.tools**, part of module **java.compiler**. With a JDK that has an available compiler, the typical flow is:

~~~text
Java source (.java file or JavaFileObject from String)
                     |
                     v
        ToolProvider.getSystemJavaCompiler()
                     |
                     v
           JavaFileManager + options
                     |
                     v
    JavaCompiler.getTask(...) -> CompilationTask
                     |
                     | configure further if needed
                     v
               task.call()
              /           \
           true           false
            |               |
      no compilation    compilation errors
         errors         -> inspect diagnostics
            |
     .class may exist
     in chosen output
~~~

**Key point:** **JavaCompiler.getTask(...)** only **creates a compilation task**; it does not run compilation yet. **JavaCompiler.CompilationTask.call()** is what **executes the task** and returns a **Boolean** result.

Even if compilation succeeds, the application does not automatically **execute** the new class. Compiling, loading classes, and invoking methods are separate responsibilities; this lesson focuses on creating a `CompilationTask`, executing it, and reading the result.

## 2. Participating API Types

Commonly used classes/interfaces:

| Type | Role |
|---|---|
| **ToolProvider** | Obtains the system compiler via **getSystemJavaCompiler()** |
| **JavaCompiler** | Interface controlling the Java compiler |
| **JavaCompiler.CompilationTask** | Preconfigured task not yet run; exposes **call()** |
| **JavaFileObject** | Represents a Java source unit or related Java file |
| **SimpleJavaFileObject** | Convenient base class for building in-memory source from a string |
| **StandardJavaFileManager** | Manages compiler sources/outputs and standard paths |
| **DiagnosticCollector<JavaFileObject>** | Collects errors/warnings/notes emitted by the compiler |
| **Diagnostic<? extends JavaFileObject>** | Details of a diagnostic: kind, location, message |

Initial step:

~~~java
// Illustrative snippet inside a Java method.
JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();

if (compiler == null) {
    throw new IllegalStateException("A JDK compiler is required");
}
~~~

Use **JDK 17+** for the examples here. **`getSystemJavaCompiler()` can return null** if the runtime image does not contain a compiler—for example, an environment packaged with only essential runtime modules and missing **jdk.compiler**. Having the **java** command on the machine does not guarantee the compiler is packaged. For a named module using `javax.tools`, the application module declares **requires java.compiler**; actually compiling also requires an available compiler implementation at runtime.

Do not use **com.sun.tools.javac.Main** or internal APIs just to invoke `javac` from Java code; **javax.tools** is the standard interface for this purpose.

## 3. Understanding the Full getTask(...) Signature

Method on **JavaCompiler**:

~~~java
JavaCompiler.CompilationTask getTask(
    java.io.Writer out,
    JavaFileManager fileManager,
    DiagnosticListener<? super JavaFileObject> diagnosticListener,
    Iterable<String> options,
    Iterable<String> classes,
    Iterable<? extends JavaFileObject> compilationUnits
);
~~~

Meaning of the six parameters:

| Parameter | Meaning | Typical Usage |
|---|---|---|
| **out** | Writer receiving additional compiler output | `null` to use default destination or `StringWriter` to capture output |
| **fileManager** | Coordinates reading sources, classpath/module path, and writing outputs | Pass configured `StandardJavaFileManager`; `null` for compiler default |
| **diagnosticListener** | Receives diagnostics per event | `DiagnosticCollector` to retain structured errors/warnings |
| **options** | Compiler options as separate strings | `List.of("--release", "17", "-d", "out")` |
| **classes** | Class names for **annotation processing** | Usually **null** when only compiling source units |
| **compilationUnits** | List of `JavaFileObject`s representing source units to compile | File manager converts `.java` files to `JavaFileObject`, or construct in-memory sources |

**Two mistakes to avoid:**

- **classes** is not a "target output class name" parameter or the name of the class to run. It is primarily for class names to be processed by annotation processors. When you already have source `JavaFileObject`s, pass **classes = null** in most cases.
- Each option and its value should be **two separate elements**, e.g. **"-d", "out"** rather than combining **"-d out"** into one string; likewise **"--release", "17"**.

Short configuration example:

~~~java
// Illustrative snippet: compiler, manager, diagnostics, and units already exist.
JavaCompiler.CompilationTask task = compiler.getTask(
    null,                          // compiler output Writer
    manager,                       // JavaFileManager
    diagnostics,                   // DiagnosticCollector
    List.of("--release", "17",
            "-proc:none",
            "-d", "out"),          // compiler options
    null,                          // class names for annotation processing
    units                          // source JavaFileObject
);
~~~

When this statement finishes, **the task exists but has not compiled anything yet**. You can customize certain aspects of the task before running it, then call **task.call()**.

### How Do Writer and DiagnosticCollector Differ?

**out** receives additional output that the compiler writes to the `Writer`. **diagnosticListener** receives structured diagnostics; these can include **ERROR**, **WARNING**, **MANDATORY_WARNING**, **NOTE**, and **OTHER**, along with source, position, diagnostic code, and message.

To categorize errors programmatically or attach them to source lines in a UI, **DiagnosticCollector** is more useful than parsing console text. Do not assume every JDK release or locale prints the exact same error wording. The return value of **call()** tells you whether the task succeeded or failed; the diagnostics list helps explain why.

## 4. What Does CompilationTask.call() Do?

The **JavaCompiler.CompilationTask** interface extends **Callable<Boolean>**. When called:

~~~java
// Illustrative snippet.
Boolean result = task.call();
boolean success = Boolean.TRUE.equals(result);
~~~

- **call()** executes the compilation task **synchronously on the current call** and returns only when compilation finishes or throws an error. It does not automatically submit work to a background thread.
- **Boolean.TRUE** indicates that **all source units compiled without errors**. Warnings/notes may still be present.
- **Boolean.FALSE** indicates compilation had errors. It is a **normal compilation result**, not an exception by default.
- A task **executes only once**. Calling **call()** a second time on the same task throws **IllegalStateException**; to recompile, you must create a **new CompilationTask**.
- Settings such as **setProcessors(...)**, **setLocale(...)**, and **addModules(...)** (where applicable) must be configured **before** starting the task; do not change them mid-run or after completion.
- Certain configuration errors or severe failures in application-provided components can cause **getTask/call to throw an exception**. Do not equate every exception with `Boolean.FALSE`.

Proper phrasing:

~~~java
// Illustrative snippet.
JavaCompiler.CompilationTask task = compiler.getTask(
        null, manager, diagnostics, options, null, sourceFiles);

// At this point the task is only created.
Boolean compiled = task.call(); // Starts compilation.

if (Boolean.TRUE.equals(compiled)) {
    System.out.println("Compilation succeeded");
} else {
    System.out.println("Compilation failed");
}
~~~

**Avoid repeated calls:** **task.call()** is not an idempotent status-check method. If you need to know elsewhere whether compilation succeeded, **store the Boolean result** instead of calling the task again.

## 5. Complete Java 17 Example: Two Tasks, One Succeeding and One Failing

The following program creates **in-memory `JavaFileObject`s from strings** so you only need a single source file to run the example. It will:

1. Obtain the JDK's `JavaCompiler`.
2. Prepare a dedicated output directory for `.class` files.
3. Create a valid source **demo.Good** and a source **demo.Bad** containing a type error.
4. Create a **separate CompilationTask** for each compilation using **getTask(...)**.
5. Invoke **call()**, print success/failure, and check whether any `ERROR` diagnostic is present.

### 5.1. Contents of CompilationTaskDemo.java

~~~java
import java.io.IOException;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Locale;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public final class CompilationTaskDemo {

    private static final class StringSource extends SimpleJavaFileObject {
        private final String code;

        StringSource(String className, String code) {
            super(
                URI.create(
                    "string:///" + className.replace('.', '/')
                        + JavaFileObject.Kind.SOURCE.extension
                ),
                JavaFileObject.Kind.SOURCE
            );
            this.code = code;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return code;
        }
    }

    private static void compile(
            JavaCompiler compiler,
            String label,
            JavaFileObject unit,
            Path output) throws IOException {

        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();

        // Create a file manager for this compilation run.
        try (StandardJavaFileManager manager =
                compiler.getStandardFileManager(
                    diagnostics, Locale.ROOT, StandardCharsets.UTF_8)) {

            List<String> options = List.of(
                "--release", "17",
                "-proc:none",
                "-d", output.toString()
            );

            JavaCompiler.CompilationTask task = compiler.getTask(
                null,               // Writer for additional output
                manager,            // Manages source and class output
                diagnostics,        // Collects diagnostics
                options,            // Compiler options
                null,               // No classes supplied for annotation processing
                List.of(unit)       // Single source unit
            );

            // Only upon this call does the compiler execute the task.
            Boolean result = task.call();

            boolean hasErrors = diagnostics.getDiagnostics().stream()
                .anyMatch(d -> d.getKind() == Diagnostic.Kind.ERROR);

            System.out.println(
                label + " success=" + Boolean.TRUE.equals(result));
            System.out.println(label + " hasErrors=" + hasErrors);
        }
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("Requires a JDK compiler");
        }

        Path output = Path.of("out");
        Files.createDirectories(output);

        String validSource = """
                package demo;
                public class Good {
                    public static int answer() {
                        return 42;
                    }
                }
                """;

        String invalidSource = """
                package demo;
                public class Bad {
                    public static int answer() {
                        return "not-an-int";
                    }
                }
                """;

        compile(
            compiler,
            "good",
            new StringSource("demo.Good", validSource),
            output
        );

        compile(
            compiler,
            "bad",
            new StringSource("demo.Bad", invalidSource),
            output
        );
    }
}
~~~

**Compile and run** with JDK 17 or later, from the directory containing the file:

~~~bash
javac --release 17 -encoding UTF-8 CompilationTaskDemo.java
java CompilationTaskDemo
~~~

**Exact expected stdout on JDK 17 with the example above:**

~~~text
good success=true
good hasErrors=false
bad success=false
bad hasErrors=true
~~~

The program avoids printing verbatim compiler error text because messages can vary by JDK version and locale. **Bad** contains a type error returning a `String` from an `int` method, so compilation fails with at least one `ERROR` diagnostic. **Good** is valid, so there is no `ERROR` diagnostic. The example uses **-proc:none** to prevent unexpected annotation processors from affecting the compilation.

After running, the **out/demo/** directory contains **Good.class** if compilation succeeded. **Bad** is not expected to produce a valid class. To be cautious in real applications, do not treat the presence of a `.class` file from a previous run as proof that the current compilation succeeded; rely on the return value of **call()** and manage output directories per build.

### 5.2. Why Is StringSource Needed?

**SimpleJavaFileObject** represents an in-memory source. The URI:

~~~text
string:///demo/Good.java
~~~

tells the compiler the logical path corresponding to the binary name **demo.Good** and file kind **Kind.SOURCE**. Method **getCharContent(...)** returns the source string. The program does not need to write real **Good.java** and **Bad.java** files on disk prior to compiling.

If you only need to compile existing `.java` files, **StandardJavaFileManager** already provides ways to convert files into `JavaFileObject`s; you do not have to write `StringSource`. Section 7 illustrates that approach.

### 5.3. Why Use Two CompilationTasks?

**Each task calls `call()` only once.** To compile `Good` and then compile `Bad`, the program creates two separate tasks via two **compiler.getTask(...)** calls. You could create one task containing multiple source units to compile both at once, yet when one source has an error, the overall result becomes **false**, making it harder to demonstrate the success and failure branches separately.

The output **good success=true** comes from the first task's **Boolean** result; **bad success=false** comes from the second task's result. The two **hasErrors** lines come from **DiagnosticCollector**, serving to explain the outcome without completely replacing it.

### 5.4. Why Is a File Manager Needed?

**StandardJavaFileManager** helps the compiler locate sources, resolve classpath/module path, and write `.class` files to output. In the example, option **-d out** specifies the output directory; **Files.createDirectories(out)** creates the directory upfront to avoid errors from a nonexistent path. **try-with-resources** closes the file manager whether compilation succeeds or fails.

The file manager is a compiler-related resource; in a system compiling repeatedly in sequence, you can reuse a `StandardJavaFileManager` in a controlled manner to benefit from caching. However, do not close it before **call()** finishes, and coordinate safely if multiple tasks exist.

## 6. Distinguishing the call() Result from Diagnostics

The **Boolean result** and **DiagnosticCollector** answer two different questions:

| Observation | Correct Conclusion |
|---|---|
| **call() == true** | All source units in the task compiled without errors |
| **call() == false** | Compilation errors occurred in the task |
| **diagnostic.Kind.ERROR** | Compiler reported a specific error, with source/line/column/message available |
| Only **WARNING/NOTE** present | Task can still succeed if no `ERROR` occurred |
| **call() throws an exception** | An error occurred that is not represented simply as `false`; handle the cause |
| **call() == true** but class later fails to load | Compilation success does not guarantee runtime dependencies, classpath, bytecode loading, or business behavior |

Example of handling the result and printing diagnostic info (illustrative snippet, placed where **task** and **diagnostics** already exist):

~~~java
Boolean result = task.call();

if (Boolean.TRUE.equals(result)) {
    System.out.println("Compilation OK");
} else {
    System.out.println("Compilation has errors");
}

for (Diagnostic<? extends JavaFileObject> d
        : diagnostics.getDiagnostics()) {
    System.out.printf(
        "%s at line %d: %s%n",
        d.getKind(),
        d.getLineNumber(),
        d.getMessage(Locale.ROOT)
    );
}
~~~

**Diagnostic.getLineNumber()** or **getColumnNumber()** may return **Diagnostic.NOPOS** when an error is not tied to a specific position; some diagnostics also have no source. Error-display UIs should provide fallbacks for such cases.

For stable test assertions, prefer checking **Kind**, **getCode()**, error counts, or true/false status rather than matching full diagnostic text verbatim. Compiler wording and message details are not an immutable display contract across versions.

### Example Warning Condition

Valid source can produce warnings when using deprecated APIs or unchecked generic conversions. In that case:

~~~text
result = true
diagnostics contains WARNING or MANDATORY_WARNING
~~~

If your build policy treats warnings as errors, you can pass compiler option **-Werror** to promote warnings into failure causes. Do not assume **non-empty diagnostics** automatically means compilation failed.

## 7. Compiling One or More Real .java Files

If source already resides on disk, use **getJavaFileObjectsFromPaths** instead of `StringSource`. For **src/demo/Greeting.java**, example:

~~~java
// Illustrative snippet, assuming compiler and diagnostics already exist.
try (StandardJavaFileManager manager =
        compiler.getStandardFileManager(
            diagnostics, Locale.ROOT, StandardCharsets.UTF_8)) {

    Iterable<? extends JavaFileObject> units =
        manager.getJavaFileObjectsFromPaths(
            List.of(Path.of("src/demo/Greeting.java"))
        );

    JavaCompiler.CompilationTask task = compiler.getTask(
        null,
        manager,
        diagnostics,
        List.of("--release", "17", "-d", "out"),
        null,
        units
    );

    boolean ok = Boolean.TRUE.equals(task.call());
    System.out.println("Compilation OK: " + ok);
}
~~~

This is an **illustrative code snippet**, not a standalone program: it requires imports, `compiler`, `diagnostics`, and an existing **out** directory. The snippet shows the same **getTask/call** API, differing only in how **compilationUnits** are created. For multiple source files, provide multiple `JavaFileObject`s:

~~~java
// Illustrative snippet when two files exist.
Iterable<? extends JavaFileObject> units =
    manager.getJavaFileObjectsFromPaths(List.of(
        Path.of("src/demo/Greeting.java"),
        Path.of("src/demo/Helper.java")
    ));
~~~

When sources depend on each other, compiling them together in one task usually helps the compiler resolve names/types consistently. If sources use external libraries, add **-classpath** or **--module-path**, and possibly **--add-modules**, depending on the deployment model. Do not automatically pass the entire application's dependencies as the compile classpath for untrusted code or when controlled reproducible builds are needed.

## 8. Compiler Options and Classpath for CompilationTask

Common options passed in the **options** parameter of `getTask`:

| Option | Effect |
|---|---|
| **--release 17** | Compile against Java 17 language, bytecode, and public APIs |
| **-d outputDir** | Specify class output directory |
| **-classpath path** or **-cp path** | Set classpath containing types/dependencies needed by the compiler |
| **--module-path path** | Set module path to resolve named modules when needed |
| **-proc:none** | Disable annotation processing for the task |
| **-Xlint:all** | Request detailed lint diagnostics |
| **-Werror** | Treat warnings as compilation errors |

In the API, each string is a separate element:

~~~java
// Illustrative snippet, using the OS-specific classpath string.
List<String> options = List.of(
    "--release", "17",
    "-d", "out",
    "-classpath", "lib/api.jar",
    "-proc:none"
);
~~~

If multiple JARs appear on the classpath, the path separator is **:** on Linux/macOS and **;** on Windows. Do not format options/output locations by inserting arbitrary shell quotes into the `List`: **getTask** receives already-split arguments without going through a shell parser.

**Do not fabricate a source list by passing class names in the `classes` parameter.** If you have a class name like **demo.Greeting** and want to compile **Greeting.java**, convert that file into a **JavaFileObject** and place it in **compilationUnits**. The **classes** parameter is primarily for annotation processing on class names.

### For Dynamically Generated Sources

When new code uses a host interface like **plugin.api.Extension**, the compiler must see the matching API version on the classpath/module path. Successful compilation against a different API version does not guarantee the class loaded into the host runtime will be compatible; managing classpath and class loaders is the work that follows **call()**.

## 9. One Task, One Run: State and Reuse

Common misconceptions about `CompilationTask` lifecycle:

**getTask() is not an already-submitted Future.** Javadoc states the task represents a compilation to be performed later. It extends **Callable<Boolean>**, so if code calls **task.call()** directly, compilation runs synchronously. Running it on a separate executor is the application's decision; in that case you must manage concurrency and separate file managers/outputs, and must not assume the compiler spawns threads itself.

**Do not call `call` twice.**

~~~java
// Illustrative snippet:
JavaCompiler.CompilationTask task = compiler.getTask(
        null, manager, diagnostics, options, null, units);
Boolean first = task.call();

// Wrong: this is not how to re-read the result.
Boolean second = task.call(); // IllegalStateException
~~~

To recompile source, create a **new task**. To retain the outcome, store the **first** variable. For systems that load new sources repeatedly, create a new task per compilation, choose a per-run output directory, and avoid mutating artifacts currently in use by the runtime.

**Processor/locale configuration must happen before call():**

~~~java
// Illustrative snippet, task created but not yet started.
task.setLocale(Locale.ROOT);

// If specifying annotation processors explicitly:
// task.setProcessors(List.of(myProcessor));

// The task begins here.
Boolean result = task.call();
~~~

Calling **setLocale** or **setProcessors** after a task has started can throw **IllegalStateException**. **setProcessors(...)** overrides processor autodiscovery with an application-supplied list; understand this clearly when using annotation processing. The main example uses **-proc:none**, so no processors run.

## 10. Handling Failures in the Right Place

Divide failures into three stages:

### 10.1. Cannot Obtain Compiler

~~~java
JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();

if (compiler == null) {
    throw new IllegalStateException(
        "No system Java compiler; run on a JDK with jdk.compiler");
}
~~~

This error occurs **before `getTask`**. Inspect the process's actual JDK, runtime image configuration, and modules. Do not treat this as a user source error.

### 10.2. Task Configuration Failure

For example, invalid options, a file manager not supporting a required location, bad inputs, or I/O issues can prevent task setup or `call` from running properly. Distinguish configuration/deployment errors from source code errors.

~~~java
// Illustrative snippet: prepare the task inside an appropriate try block.
try {
    JavaCompiler.CompilationTask task = compiler.getTask(
        null, manager, diagnostics, options, null, units);
    Boolean result = task.call();
    System.out.println("compiled=" + result);
} catch (IllegalArgumentException e) {
    throw new IllegalStateException("Invalid compiler configuration", e);
}
~~~

Not every setup error is an `IllegalArgumentException`; this snippet highlights one type rather than an exhaustive catch list. With application-supplied components like `JavaFileManager`, `DiagnosticListener`, or `JavaFileObject`, runtime errors in callbacks can cause the task to throw `RuntimeException`, per the API contract. Log causes with context rather than swallowing errors and pretending the source is invalid.

### 10.3. Java Source Contains Errors

This is the normal case:

~~~java
Boolean result = task.call();

if (!Boolean.TRUE.equals(result)) {
    for (Diagnostic<? extends JavaFileObject> diagnostic
            : diagnostics.getDiagnostics()) {
        if (diagnostic.getKind() == Diagnostic.Kind.ERROR) {
            System.err.println(diagnostic.getMessage(Locale.ROOT));
        }
    }
}
~~~

**false** means compilation did not succeed. In service code, return the status and valid errors to the caller rather than turning every source error into an unclassified exception.

**Failure does not guarantee no output:** The compiler may have already emitted some `.class` files before encountering another error, or the output directory may contain files from an earlier run. Never consume outputs when **call() == false**; build in an isolated staging directory and publish artifacts only after a successful outcome.

## 11. Safe Design When Accepting Java Code at Runtime

Runtime compilation is valuable in IDE tooling, coding exercises, rule engines, or plugin hosts, but clear boundaries are necessary:

- **Compiling differs from running:** `JavaCompiler` analyzes and generates bytecode; executing new classes requires another class loader/module layer, contract type verification, lifecycle management, and usage permissions.
- **Running annotation processors is also running code:** Do not expose unexpected processors to compiler invocations on untrusted source. Use **-proc:none** when processing is unnecessary, as in the example.
- **Do not use an overly broad classpath:** Avoid exposing unnecessary secrets/internal classes to the compiler; manage source dependencies and API versions.
- **Limit resources:** Compiling complex code can consume substantial CPU, RAM, and I/O. If processing untrusted sources, enforce strong process/container isolation, timeouts, and appropriate quotas. Do not treat `JavaCompiler` as a sandbox.
- **Bind outputs to each compilation run:** Use dedicated output directories and diagnostic collectors to prevent races between compilations and reading stale outputs.
- **Close resources:** File managers, streams, and post-compile class loaders have their own lifecycles. `JavaCompiler.CompilationTask` does not automatically close all resources passed by the application.

**Simply having `call()` succeed does not verify the code is safe to execute.** Bytecode can contain dangerous logic or calls to external libraries; running third-party code inside the same JVM should only be done under appropriate trust and policy.

## 12. Comparing getTask/call with Other Compilation Approaches

| Approach | When Appropriate | Key Difference to Remember |
|---|---|---|
| **JavaCompiler.getTask + call** | Application wants programmatic control over source, options, diagnostics/file manager, and status in Java | Separates task creation and execution; supports in-memory `JavaFileObject` |
| **JavaCompiler.run(...)** | Need a simple command-line-style interface from Java | Takes input/output streams and arguments, returns `int` exit code; less structural control |
| **ProcessBuilder running javac** | Need an external process and clear process isolation, or a custom toolchain | Must manage process, stdout/stderr, exit code, and classpath |
| **javac via terminal** | Manual compilation of projects/files | CLI tool, does not integrate structured diagnostics directly into the application |
| **JShell API** | Executing interactive snippets, REPL, session state | Snippet model differs from full compilation units and tasks from `getTask` |

If the goal is **reading compilation results and returning structured diagnostics**, `getTask/call` paired with `DiagnosticCollector` is more suitable than parsing terminal text. If you only need to compile standard projects, a build tool is usually a more practical choice than building custom compiler orchestration.

## 13. Testing and Observing Behavior

### Test 1: getTask Does Not Start Compiling Yet

Create a task without calling **call()**, then inspect a clean output directory. No request has been made for the compiler to process the compilation unit; results appear only when `call()` runs. Do not confuse this with file manager setup accessing the filesystem.

### Test 2: Valid Source

**Good** in the example returns **true**, with no **Kind.ERROR** diagnostics. The corresponding class output appears in **out/demo/Good.class**.

### Test 3: Source with Type Error

**Bad** returns **false**, **hasErrors=true**. Use diagnostics to pinpoint the error returning a `String` from an `int`-returning method. Do not test by trying to run `Bad.class`.

### Test 4: Calling call a Second Time

~~~java
// Illustrative snippet:
task.call();
task.call(); // IllegalStateException
~~~

Emphasize this is not a way to "retrieve the result again," but a task lifecycle error.

### Test 5: Warnings Are Not Failures

Use source that triggers a warning without errors; **call()** can still return **true**. Enable **-Werror** when build policy requires warnings to fail compilation.

### Test 6: Compiler Absent

Run the application on a runtime image lacking the compiler; verify **ToolProvider.getSystemJavaCompiler() == null** is reported as a clear infrastructure error rather than mistaken for a Java source error.

## 14. Self-Check Questions

**Question 1.** Does calling **compiler.getTask(...)** immediately compile the source?

**Answer:** No. It creates an unexecuted **CompilationTask**. Only **task.call()** runs compilation.

**Question 2.** Does **Boolean.FALSE** from `call()` mean the Java program crashed at runtime?

**Answer:** No. It indicates a **compilation error**. Code has not necessarily been loaded or executed; runtime errors belong to a later stage.

**Question 3.** If the compiler emits warnings without errors, what does `call()` return?

**Answer:** Normally **true**, since compilation had no errors; a policy flag such as **-Werror** can turn warnings into errors and make the task fail.

**Question 4.** Why pass **classes = null** when compiling source from `JavaFileObject`?

**Answer:** That parameter supplies **class names for annotation processing**, not source file locations. The sources to compile are already provided in **compilationUnits**.

**Question 5.** Should you invoke the same **task.call()** again after editing Java source?

**Answer:** No. A task runs only once. Create a new task with new `JavaFileObject`s and appropriate options/file manager.

**Question 6.** Why shouldn't unit tests compare verbatim compiler error strings?

**Answer:** Diagnostic messages can change across JDKs, locales, and versions; rely on status, `Kind`, codes, or appropriate structured attributes instead.

**Question 7.** Does successful compilation guarantee the new class works with the host API?

**Answer:** No. Runtime classpath/module path, class loader identity, dependency versions, and business logic can still fail. The load/execute stage must validate separately.

## 15. Application Integration Checklist

1. **Runtime has compiler:** verify `getSystemJavaCompiler()` is non-null and required JDK/modules are present.
2. **Valid source:** supply `JavaFileObject` from file or string with matching URI name, UTF-8 encoding, and needed source dependencies.
3. **Proper task configuration:** set file manager, diagnostics, options, and annotation processing policy; understand `classes` vs. `compilationUnits`.
4. **Isolated output:** point `-d` to an explicit directory, avoiding mixing successful/failed compilations or concurrent runs.
5. **Call `call()` exactly once:** store the `Boolean`, distinguish `true`/`false` and exceptions; never treat `getTask` as execution.
6. **Inspect diagnostics:** use `Kind.ERROR`, line/column/source/code where appropriate; do not depend strictly on exact prose.
7. **Close resources:** `StandardJavaFileManager` via try-with-resources; manage class loader/lifecycle separately if consuming bytecode.
8. **Test both branches:** valid source returns `true`, invalid returns `false`; verify null compiler, warnings, bad options, and callback exceptions if needed.
9. **Execute only trusted/controlled code:** the compiler provides no sandbox; isolate untrusted sources separately.

**Remember:** **getTask(...)** prepares a **CompilationTask** with sources, file manager, options, and diagnostics. **call()** actually runs compilation and returns a **Boolean** success/failure, callable only once. Inspecting both that result and the **Diagnostic** entries is foundational for accurately reporting runtime Java compilation outcomes to users.

### Java SE 17 Documentation

- JavaCompiler: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.html
- JavaCompiler.CompilationTask: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.CompilationTask.html
- Diagnostic / DiagnosticCollector: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/Diagnostic.html
- StandardJavaFileManager: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/StandardJavaFileManager.html
- ToolProvider: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/ToolProvider.html
