# When to Use JShell for Interactive Java Snippets Instead of JavaCompiler?

## 1. The Architectural Question to Solve

Suppose a Java application lets users test an expression, define variables, call a method, tweak a few lines, and see the result immediately. One option is to invoke `JavaCompiler` to emit `.class` files, create a new class loader, and execute them each time. Another option is to embed the `jdk.jshell.JShell` API to maintain an interactive session.

Both APIs involve **Java compilation**, but they have different usage contracts:

- **`JShell`:** evaluates each *snippet*—an expression, statement, variable declaration, method, class, or import—in **a stateful session**. Subsequent inputs can use declarations from previous inputs. The API returns `SnippetEvent` instances, expression results, and diagnostics so REPL/IDE tools can display them immediately.
- **`JavaCompiler`:** compiles *compilation units* following an explicit build workflow, typically producing bytecode as `.class`/JAR files or in-memory artifacts via `JavaFileManager`. Loading, instantiating, and executing the artifact is a **separate phase** that the application must build.
- **Neither is a secure sandbox for untrusted code.** Choose JShell for the interactive experience, not because you assume it is harmless when accepting source code from strangers.

The real question is not "Which API compiles faster in every scenario?", but rather: **Does the application need a step-by-step code experimentation session, or does it need a stable, storable, deployable compiled artifact?**

## 2. The Nature of JShell: A Stateful REPL, Not Just `eval(String)`

JShell was introduced in Java 9 and resides in the `jdk.jshell` module. The central API is `jdk.jshell.JShell`:

```java
try (jdk.jshell.JShell shell = jdk.jshell.JShell.create()) {
    shell.eval("int n = 7;");
    shell.eval("n * 3");
    shell.eval("int twice(int x) { return x * 2; }");
    shell.eval("twice(n)");
}
```

The snippet above is an **API illustration**; a standalone program with proper `SnippetEvent` and stdout handling is in section 6.

A JShell session stores **source state** (variables, methods, types, imports, and active declarations) along with their **execution state**. That is why `n` still exists when evaluating `n * 3`, and the `twice` method remains usable in the next input. Developers do not have to manually wrap every expression in a complete Java class.

Several distinctions are important:

1. **JShell also compiles source code.** It uses the Java compiler infrastructure to process snippets, but hides the boilerplate of generating wrapper classes and managing execution state. It is incorrect to say "JShell runs Java without compiling."
2. **JShell is not a generic `javax.script.ScriptEngine` for arbitrary languages.** It is dedicated to Java snippets and the analysis APIs of `jdk.jshell`.
3. **The JShell CLI and the Java API are different.** Commands like `/vars`, `/methods`, and `/reset` in the interactive `jshell` program are not Java snippets to pass directly to `JShell.eval`. The API provides `variables()`, `methods()`, `drop(...)`, `close()`, and other methods to implement equivalent operations.
4. **Each `eval` call should receive one complete snippet.** To accept arbitrary multi-line text blocks from an editor, the application should use `SourceCodeAnalysis.analyzeCompletion(...)` to split input and determine syntactic completeness rather than splitting on newlines.
5. **State belongs strictly to a specific JShell session.** Creating a new session does not automatically carry over variables declared in an old session. Any data the application wants to persist requires a controlled snapshot/replay mechanism.

## 3. JavaCompiler: Compile Artifacts First, Then Load and Execute

The `javax.tools.JavaCompiler` API fits complete code generation pipelines where the source may be one or more Java files with packages, dependencies, and compiler configuration:

```text
Source .java / JavaFileObject
       |
       v
JavaCompiler.getTask(...) + JavaFileManager
       |
       v
CompilationTask.call()  -> diagnostics / success / failure
       |
       v
 .class files / in-memory bytecode / JAR
       |
       v
validate + publish artifact
       |
       v
ClassLoader or ModuleLayer
       |
       v
instantiate/invoke/deploy/test
```

`JavaCompiler` **has no concept of a REPL session that retains `n` after a call** as part of its general contract. Each compilation task processes the sources and classpath/module path provided by the caller. To support multiple consecutive inputs, the application must manage generated code, class names, outputs, versions, class loaders, and artifact lifecycles itself.

Conversely, `JavaCompiler` offers major advantages when a build artifact is needed:

- Compiles structured source code: packages, named classes, multiple compilation units, module descriptors, annotation processing, and output paths.
- Produces artifacts that can be **stored, tested, packaged, signed, scanned, cached, or deployed**, independent of a live JShell session.
- Integrates with build/CI tools, classpath/module path, and appropriate compilation policies.
- Clearly separates compilation outcomes from execution; successful compilation does not mean runtime logic will succeed.

`JavaCompiler` can be used with **in-memory sources or outputs** via a custom `JavaFileObject`/`JavaFileManager`. The difference between the two APIs is **not simply that JShell uses RAM while JavaCompiler must write files to disk**.

## 4. Decision Table: When to Prefer JShell?

| Practical Need | Preferred Choice | Reason |
|---|---|---|
| User types `1 + 2` and wants to see `3` immediately | JShell | Expression snippets yield a value without building a full class |
| Create a variable and reuse it across multiple inputs | JShell | State persists across `eval` calls within the same session |
| Learning Java, playgrounds, internal consoles, IDE REPLs | JShell | Provides snippet status, error diagnostics, and source completion |
| Test a short method, import an API, and call it immediately | JShell | Declarations/methods/imports persist in session, easy to edit and re-evaluate |
| Compile dozens of Java files into a releasable plugin JAR | JavaCompiler | Requires compilation units, artifacts, and dependency/output management |
| Generate an SPI implementation for long-term host use | Usually JavaCompiler | Control over binary names, bytecode, class loaders, and lifecycle |
| Run repeatable builds with caching, reproducibility, and test/CI | JavaCompiler | Output artifact is decoupled from an interactive session |
| Need module descriptors, annotation processing, or standard outputs | JavaCompiler | Fits a build model better than a snippet model |
| User wants to both experiment with code and save it as a product feature | JShell to prototype; JavaCompiler for final build | Experimental code must be converted to standard source and re-tested |
| Accept untrusted Java and restrict file/network/CPU usage | Do not choose solely via these two APIs | Requires a dedicated process/OS/container security boundary |

**Quick takeaway:** If the primary workflow is **"enter a snippet → get feedback → edit immediately in the same context"**, JShell is usually the right fit. If the primary workflow is **"take complete source code → produce a stable artifact → test/deploy"**, `JavaCompiler` is usually the right fit.

## 5. Key Differences in Input and Output

### JShell Input

An input can be:

```java
int score = 10;
```

or:

```java
score * 2
```

or:

```java
int bonus(int x) { return x + 5; }
```

These are **individual snippets**, not a full source file. JShell retains definitions across `eval` calls. The expression `score * 2` can be assigned to a JShell-generated temporary variable without the user having to write `class Main { ... }`.

### JavaCompiler Input

A compilation unit has standard Java structure:

```java
package demo;

public final class Discount {
    public static int apply(int price) {
        return price - 5;
    }
}
```

This is the source of `demo/Discount.java`, **not a standalone program with `main`**. `JavaCompiler` can turn this source into `demo/Discount.class`. Calling `Discount.apply(10)` is a separate runtime step.

### Different Outputs

- `JShell.eval(input)` returns `List<SnippetEvent>`—snippet status changes, expression values (if any), exceptions, and information about direct/indirect events.
- `JShell.diagnostics(snippet)` returns error/warning messages from the **most recent evaluation** of that snippet; `JShell.status(snippet)` returns its current status.
- `JavaCompiler.CompilationTask.call()` returns a `Boolean` indicating task success; diagnostics come from a listener/collector; output bytecode is managed via the file manager.
- `SnippetEvent.value()` is not always present: method or import declarations typically have `null` because they do not produce an expression value to print.
- `JavaCompiler` does not automatically invoke methods on the newly compiled class. The caller must load and execute it separately if that is the goal.

The two APIs therefore have different **units of work**: JShell handles stateful interaction; `JavaCompiler` handles a compilation task with caller-defined inputs and outputs.

## 6. Standalone Java 17 Example with the JShell API

This program creates a JShell session, declares a variable, evaluates an expression, declares a method, updates the variable's value, and detects an invalid snippet. It only prints deterministic data, omitting temporary variable IDs or compiler error text that may vary.

**File `JshellChoiceDemo.java`:**

```java
import java.util.List;
import jdk.jshell.JShell;
import jdk.jshell.Snippet;
import jdk.jshell.SnippetEvent;

public final class JshellChoiceDemo {
    private static String evaluate(JShell shell, String input) {
        List<SnippetEvent> events = shell.eval(input);
        return events.stream()
                .filter(e -> e.status() == Snippet.Status.VALID)
                .map(SnippetEvent::value)
                .filter(v -> v != null)
                .findFirst()
                .orElse("(no value)");
    }

    public static void main(String[] args) {
        try (JShell shell = JShell.create()) {
            System.out.println("declare=" + evaluate(shell, "int n = 7;"));
            System.out.println("expression=" + evaluate(shell, "n * 3"));
            System.out.println("method=" + evaluate(shell,
                    "int twice(int x) { return x * 2; }"));
            System.out.println("call=" + evaluate(shell, "twice(n)"));
            System.out.println("update=" + evaluate(shell, "n = 9;"));
            System.out.println("call-again=" + evaluate(shell, "twice(n)"));

            List<SnippetEvent> errors = shell.eval("int broken = ;");
            boolean rejected = errors.stream().anyMatch(
                    e -> e.status() == Snippet.Status.REJECTED);
            long errorDiagnostics = errors.stream()
                    .flatMap(e -> shell.diagnostics(e.snippet()))
                    .filter(d -> d.isError())
                    .count();
            System.out.println("invalid-rejected=" + rejected);
            System.out.println("has-errors=" + (errorDiagnostics > 0));
        }
    }
}
```

### 6.1. Compile/Run Commands

In a terminal with JDK 17 or newer, from the directory containing the file:

```powershell
# Windows PowerShell
javac --release 17 --add-modules jdk.jshell JshellChoiceDemo.java
java --add-modules jdk.jshell -cp . JshellChoiceDemo
```

```bash
# Linux/macOS
javac --release 17 --add-modules jdk.jshell JshellChoiceDemo.java
java --add-modules jdk.jshell -cp . JshellChoiceDemo
```

`--add-modules jdk.jshell` ensures the module providing the JShell API is resolved into the module graph when the host class runs on the classpath. Do not use `java.compiler` as a substitute for `jdk.jshell`: they are two different modules. A custom runtime image may not bundle the JShell module, so you should verify the deployment environment.

### 6.2. Verified Stdout

```text
declare=7
expression=21
method=(no value)
call=14
update=9
call-again=18
invalid-rejected=true
has-errors=true
```

This output was verified using `javac --release 17` and running Java. Analysis:

1. `int n = 7;` creates a variable in JShell state; the valid event has value `7`.
2. `n * 3` uses the existing variable and returns `21` without needing to compile a new source file from scratch from the caller's perspective.
3. The `twice` method declaration is valid, but it is not a call that yields a value; the helper prints `(no value)`.
4. `twice(n)` returns `14`, proving the method persists across multiple `eval` calls.
5. `n = 9;` updates the state, so the subsequent call returns `18`.
6. `int broken = ;` is marked `REJECTED` and produces an error diagnostic; the program can still use valid declarations in the same session.
7. `try-with-resources` closes JShell after use instead of keeping the execution engine alive indefinitely.

**Limitation of the `evaluate` helper:** It picks the first value from an event with status `VALID`, which suffices for a demo program sending **one complete snippet per call**. A real REPL tool must process **all** events, because an evaluation or redefinition can emit additional events that update dependent snippets. Never just grab `events.get(0)` and assume the rest do not matter.

## 7. Comparison Program: JavaCompiler Produces Explicit Artifacts

If the requirement is to create a standard Java class that can be saved or deployed, use `JavaCompiler`. This Java 17 example writes a source file to a temporary directory, compiles it using a file manager, closes the file manager, and verifies that the `.class` file was generated. It **does not execute the compiled class**, because that is the responsibility of a separate runtime step.

**File `CompilerChoiceDemo.java`:**

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Locale;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.StandardLocation;
import javax.tools.ToolProvider;

public final class CompilerChoiceDemo {
    public static void main(String[] args) throws Exception {
        Path workspace = Files.createTempDirectory("compiler-choice-");
        Path source = workspace.resolve("src/demo/Generated.java");
        Path classes = Files.createDirectories(workspace.resolve("classes"));
        Files.createDirectories(source.getParent());
        Files.writeString(source, """
                package demo;
                public final class Generated {
                    public static int twice(int number) {
                        return number * 2;
                    }
                }
                """, StandardCharsets.UTF_8);

        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("JDK compiler is not available");
        }

        var diagnostics = new DiagnosticCollector<JavaFileObject>();
        boolean success;
        try (StandardJavaFileManager manager =
                compiler.getStandardFileManager(
                        diagnostics, Locale.ROOT, StandardCharsets.UTF_8)) {
            manager.setLocationFromPaths(
                    StandardLocation.CLASS_OUTPUT, List.of(classes));
            var units = manager.getJavaFileObjectsFromPaths(List.of(source));
            success = Boolean.TRUE.equals(compiler.getTask(
                    null, manager, diagnostics,
                    List.of("--release", "17", "-proc:none"),
                    null, units).call());
        }

        System.out.println("compiled=" + success);
        System.out.println("artifact=" +
                Files.isRegularFile(classes.resolve("demo/Generated.class")));
    }
}
```

**Compile and run on Windows/Linux/macOS** (from the directory containing the file):

```bash
javac --release 17 CompilerChoiceDemo.java
java -cp . CompilerChoiceDemo
```

**Exact stdout:**

```text
compiled=true
artifact=true
```

This result has been verified by compiling and running the code. The temporary directory name has a random component, which does not appear in stdout. In a real application, after compiling, inspect diagnostics and source/artifact versions, close the file manager, and package or publish the artifact. Only then decide whether to create a `URLClassLoader`/`ModuleLayer` to run it.

**Direct comparison:** The JShell demo records `n` and reuses it within the same session; the `JavaCompiler` demo produces `demo.Generated.class` with a deterministic binary name and path. Which model you choose depends on whether the application needs **interactive state** or a **distributable artifact**.

## 8. Using SnippetEvent, Status, and Diagnostics Properly

A tool embedding JShell should not assume `eval` returns "a result string or an exception." In reality it returns a list of `SnippetEvent`, and each event has:

- `snippet()`: the associated snippet, allowing you to inspect `kind()` and `source()`.
- `status()`: the status of the snippet after the transition described by the event.
- `previousStatus()`: the prior status when a change occurred.
- `value()`: string representation of the value if the evaluation produced one; never assume it is always non-`null`.
- `exception()`: exception thrown by executing the snippet according to JShell's exception model; distinct from compile errors.
- `causeSnippet()`: identifies whether the event occurred indirectly because another snippet was added, modified, or dropped.

Key statuses:

| Status | Practical Meaning |
|---|---|
| `VALID` | The snippet is validly defined/evaluated in the current state |
| `REJECTED` | The snippet was rejected, usually due to errors that cannot be deferred |
| `RECOVERABLE_DEFINED` | Declaration can be defined despite unresolved dependencies; calling it is not yet guaranteed to succeed |
| `RECOVERABLE_NOT_DEFINED` | Declaration is recoverable, but a usable definition could not be created yet |
| `OVERWRITTEN` | An old declaration was replaced by a new one with a matching signature/identifier |
| `DROPPED` | The declaration was removed from active state |
| `NONEXISTENT` | Non-existent snippet state during certain transitions |

**Do not lump every non-`REJECTED` status together as "succeeded."** A method with unresolved dependencies can be in a recoverable state; calling it may fail, and `unresolvedDependencies(...)` is needed to explain why.

To report errors meaningfully, use:

```java
for (SnippetEvent event : shell.eval(input)) {
    System.out.println(event.status());
    if (event.exception() != null) {
        System.err.println(event.exception().getMessage());
    }
    shell.diagnostics(event.snippet()).forEach(diag -> {
        if (diag.isError()) {
            System.err.println(diag.getMessage(java.util.Locale.ROOT));
        }
    });
}
```

This is an **illustrative snippet meant to be placed inside a scope with `shell` and `input`**. Diagnostic messages can differ across JDK versions and locales; do not write tests asserting exact compiler wording. Prefer asserting status, kind, event value, and the presence of error diagnostics.

### Execution Errors vs. Compile Errors

`shell.eval("1 / 0")` can compile as a valid snippet and then fail during execution, producing a non-`null` `SnippetEvent.exception()`. A syntax error like `int broken = ;`, on the other hand, produces `REJECTED` and diagnostics. A REPL should present these two situations differently: the user fixing syntax versus debugging a runtime exception.

If JShell's default execution engine runs out-of-process as the JDK typically configures it, user-code exceptions are described through the JShell API rather than necessarily being `Throwable` instances from the same host class loader. Do not cast `exception()` directly to an exception class from the evaluated source code.

## 9. Multi-Line Input UI: `SourceCodeAnalysis` Is the Splitting Step

A user might enter:

```java
int total(int x) {
    return x + 10;
}
```

This is **one method snippet** spanning multiple lines, not three separate snippets. If the UI passes each line individually to `shell.eval(...)`, the input may be rejected even though the final method is valid.

The `shell.sourceCodeAnalysis()` API provides `SourceCodeAnalysis.analyzeCompletion(buffer)` to determine completeness and identify the portion of source ready for processing. One approach:

1. Append each line the user enters to a **session-specific** input buffer.
2. Use `analyzeCompletion(buffer)` to determine whether a complete snippet is ready or more closing braces/semicolons are needed.
3. Once a snippet is complete, pass the **exact source of the complete snippet** to `eval`; retain any remaining text for further analysis without dropping characters.
4. Iterate over all `SnippetEvent`s and update the UI: source, status, value, diagnostics, unresolved dependencies, and stdout/stderr.
5. Store source/history by session ID if the application needs recovery or auditing.

API sketch (not a standalone program):

```java
var analysis = shell.sourceCodeAnalysis();
var completion = analysis.analyzeCompletion(buffer);
if (completion.completeness().isComplete()) {
    String completeSource = completion.source();
    shell.eval(completeSource);
    buffer = completion.remaining();
}
```

CLI commands like `/list` or `/drop` must not be sent through `eval`; the UI must map them to the corresponding API calls. The JShell CLI also has its own history, prompt, and command parser. **Embedding the API does not automatically give you a complete REPL UI.**

## 10. State: JShell's Greatest Strength and Greatest Risk

Within a single session, entering:

```java
int discount = 5;
```

then:

```java
int price(int base) { return base - discount; }
```

then:

```java
discount = 7;
```

means a method evaluated earlier observes the updated state. This is very useful for teaching, experimenting with algorithms, or building an interactive console. However, production systems must watch out for:

- **Redefining declarations:** JShell lets you replace certain declarations with the same name/signature. Events may report the old snippet as `OVERWRITTEN`; other variables/methods depending on it can change status or behavior.
- **Dropping declarations:** `shell.drop(snippet)` mutates source state and can affect many dependent snippets. Do not treat `drop` as "rolling back all side effects" of previously executed code.
- **Unresolved dependencies:** A declaration can be accepted conditionally. Call `shell.unresolvedDependencies(declarationSnippet)` when you need to show missing names rather than claiming the user ran it successfully.
- **Side effects persist:** Writing files, sending HTTP requests, mutating objects, spawning threads, or updating databases are not rolled back just because the user drops or redefines a snippet.
- **Resetting a session:** To return to a completely clean context, the simplest approach is to `close()` the old session and call `JShell.create()` for a new one. `close()` does not restore external systems that were already modified.
- **Long-lived sessions:** Accumulating many snippets and class definitions increases memory usage, analysis time, and engine coordination overhead. Enforce limits on session lifetime, snippet count, history size, and open session count.

For multi-user systems, do not use **one shared singleton JShell for all requests**: state will leak across users, and output/behavior will become unpredictable. Use a session ID bound to an owner with an explicit lifecycle and timeout.

## 11. Lifecycle: `JShell.close` vs. `JavaFileManager.close`

`JShell` implements `AutoCloseable`. In host code:

```java
try (JShell shell = JShell.create()) {
    // Evaluations, drops, and diagnostics reads for this session.
}
// shell.close() has been called.
```

This is an illustrative pattern. `close()` releases engine resources; a closed session must not continue to be used as an active session. If a new session is needed, create a new instance.

`JavaCompiler` typically follows this lifecycle:

```java
JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
try (StandardJavaFileManager manager =
        compiler.getStandardFileManager(null, null, null)) {
    // Create task, configure classpath/output, and call task.call().
}
// Manager is closed, but the .class artifact may still exist.
```

This is also an illustrative snippet, not a standalone program. Key differences:

| JShell | JavaCompiler |
|---|---|
| Manages an interactive session and execution state | Manages compilation tasks and artifacts |
| Close `JShell` when the session ends | Close `JavaFileManager` after the compilation task/phase |
| Supports `drop` and snippet redefinition within the same session | Does not provide interactive state or overwrite semantics via tasks |
| Internal compiled classes of JShell should not be taken as default deployment artifacts | The output artifact is the direct design goal |
| External side effects may persist even after the session is closed | Loaded artifacts/classes remain alive with the application lifecycle, not the manager's |

In both cases, **closing the API resource does not undo Java code that has already executed**. With `JavaCompiler`, class loading/execution might not have happened yet. With JShell, each `eval` call may have already executed side effects immediately.

## 12. Classpath, Modules, and the Host–Snippet Boundary

A JShell session runs inside an execution environment. It is not guaranteed to see every class or object visible to the host application simply because both are Java.

Key factors:

1. **The `jdk.jshell` module:** the host needs this module in the runtime image and in the module graph. `javac --add-modules jdk.jshell`/`java --add-modules jdk.jshell` in the example makes this explicit.
2. **Classpath for snippets:** `shell.addToClasspath(pathString)` appends a path to the classpath used by `eval`. The path must contain JARs or classes readable by the execution engine; misconfiguration can lead to diagnostics or runtime errors.
3. **Host classpath differs from snippet classpath:** host classes may be loaded by the application loader, whereas snippet classes run in another loader/engine. Do not assume a host `Class<?>` or object can be passed directly via a Java source expression.
4. **Default package:** classes defined in the host's unnamed package are not a stable integration path for snippets. The JShell API explicitly notes that classes in the unnamed package cannot be accessed from the package where `eval` code is placed; public APIs should have explicit packages and configured dependencies.
5. **Named modules and reflection:** JShell does not automatically resolve every `requires/exports/opens` configuration of your application. If the product needs to build standard named modules, `JavaCompiler` + module path/`ModuleLayer` is usually a better fit.
6. **Multiple sessions:** each session has its own state; classloader and engine lifetimes must be managed to avoid retaining stale classes or plugin JARs. Do not indiscriminately cache `Class<?>`, outputs, or objects expecting them to work across sessions.

Do not design an API that "runs an expression in JShell and grabs the live object directly from the host heap" without a supported data bridge. For workflows that exchange values, consider serializing via JSON/strings or calling a contract-based API/IPC; note that JShell's `SnippetEvent.value()` is only a **display string**, not a live Java object you can cast arbitrarily.

## 13. Concurrency, Timeouts, and Cancellation

The Javadoc states that `JShell` is **not thread-safe** (unless explicitly noted otherwise). Avoid having two requests call `eval` or `drop` concurrently on the same instance without explicit queuing or synchronization.

For a multi-user web application:

- A JShell session should have a single **owner** and serialize state-mutating operations. You can use a single-threaded actor/queue per session.
- Cap the number of sessions, snippet length, history depth, and total resources. Long-lived sessions need an idle timeout and `close()`.
- `shell.stop()` only **attempts** to stop a running snippet; the Javadoc does not guarantee it can always stop execution, for instance if code catches exceptions or blocks in an uncooperative operation.
- `Future.cancel(true)` on a host thread does not guarantee stopping code running inside the execution engine.
- If snippets can loop infinitely, spawn threads, write to disk, or access the network, real limits are needed at the **process/OS/container level**. JShell's default execution engine typically runs out-of-process, but that alone must not be treated as a guaranteed sandbox.
- Do not invoke `eval/drop` back from callbacks in ways that cause reentrancy. When using `onSnippetEvent`, per the API docs, callbacks fire while state is mutating; adhere to restrictions on calling JShell methods inside callbacks.

With `JavaCompiler`, a compilation task can also be slow or resource-intensive, though it does not create a REPL session. You must manage compile workers, timeouts, source limits, and artifact cleanup, and then manage runtime workers **separately** if the compiled code is executed.

## 14. Performance: Optimize by Lifecycle Rather Than Assuming One API Is Faster

JShell is designed to reduce **interactive UX overhead**: each input does not require the caller to generate, compile, and load a complete class source file manually. It excels at prototyping and rapid feedback. However:

- Creating a JShell session incurs startup costs for the compiler/engine and remote process.
- Keeping a session alive across turns saves startup overhead compared to spawning a new session on every Enter keystroke, but increases memory, state history, and resource usage.
- Frequent redefinitions can force many dependent snippets to be re-analyzed or updated.
- `eval` time includes parsing, compilation, and potentially code execution—not just a bare computation.
- `JavaCompiler` with batched sources, caching, a custom file manager, and a proper build pipeline can be more efficient when compiling a large source set or long-lived artifacts.
- Benchmarks must measure **source analysis, compilation, class loading, execution, I/O, warmup, process startup, and cleanup**—not compare a single `eval("1+1")` against a build of hundreds of classes.

A claim like "JShell is always faster than JavaCompiler" has no general validity without defining the workload. For runtime extensibility, it matters more to choose the right **session granularity** and **build/artifact granularity**.

## 15. Security: Do Not Run Untrusted Source Just Because You Use JShell

JShell makes it convenient to build a playground, but evaluating source code can lead to **real Java code execution**. That code can access the filesystem, network, CPU, memory, threads, or libraries within the granted permissions. A bad snippet can throw errors, exhaust resources, or cause side effects before the user clicks "reset."

Meaningful controls for untrusted sources include:

1. Run code in an **isolated worker process/container** with its own OS identity, filesystem/network permissions, resource limits, and independent lifecycle.
2. Enforce limits on time, CPU, RAM, threads/processes, snippet count, and session count; have a reliable way to kill the worker rather than relying solely on `JShell.stop()`.
3. Restrict the classpath/module path, and avoid mounting host documents, secrets, or credentials into the execution environment.
4. Log sessions for auditing, and avoid exposing variable values or diagnostics containing sensitive data in public outputs.
5. Do not treat `JavaCompiler` as a "safer mechanism" if you subsequently load and run untrusted artifacts inside the host JVM. With the compiler, annotation processing also needs its own policy in the build pipeline.
6. Do not confuse **no compile errors** with **safe code**: a `VALID` snippet proves Java accepted it at evaluation time, not that its logic is benign.

JShell's default engine may use a separate JVM by JDK design, but without OS permission controls and isolation, a separate process alone is insufficient to establish a strong security boundary.

## 16. Practical Architecture Patterns

### 16.1. IDE / Java Learning Environment with an Interactive Prompt

```text
User enters statement
  -> validate source and character limit
  -> SourceCodeAnalysis: is it a complete snippet?
  -> dedicated JShell session
  -> eval
  -> SnippetEvent/status/diagnostics/value
  -> update UI/history
  -> continue using state for the next statement
```

This is where JShell shines brightest. The UX can display current variables, defined methods, incomplete code, and error locations. Session ownership and timeouts must be standardized.

### 16.2. Generating Plugin Classes from Templates

```text
Template/source generator
  -> JavaCompiler + JavaFileManager
  -> .class or JAR + metadata
  -> validate, test, sign/publish
  -> ClassLoader / ModuleLayer
  -> plugin lifecycle
```

`JavaCompiler` fits better because the output needs deterministic class names, artifacts, dependencies, and rollouts; JShell session state should not be used as an uncontrolled deployment source.

### 16.3. Prototype First, Production Later

```text
Enter expression / test API with JShell
  -> choose suitable solution
  -> convert to standard Java source/class/method
  -> JavaCompiler or build tool
  -> unit tests + integration tests
  -> publish artifact
```

This is a sensible hybrid workflow: JShell lowers the cost of exploring ideas, while `JavaCompiler` builds long-lived artifacts. However, do not assume you can copy raw snippet strings verbatim and compile them as a source file; top-level declarations, `$1` temporary variables, and REPL semantics must be converted into standard Java structure.

### 16.4. Short Business Rules in Enterprise Systems

If rules are written in Java by trusted internal specialists who want to test them immediately in a console, JShell can serve as an **interactive authoring and testing tool**. However, if rules must run millions of times in production with versioning, auditing, transactions, classloader isolation, and proper testing, consider compiling standard Java artifacts, a dedicated rule DSL, or a runtime mechanism with a stricter contract. Never use an admin's JShell session to serve all production requests.

## 17. Test Suite for API Choice and Implementation Correctness

| Test Case | With JShell | With JavaCompiler |
|---|---|---|
| Using a variable across two calls | Second call sees the session's state | Appropriate source/dependencies must be fed into a new task |
| Expression `n * 3` | Event returns value directly | Expression must be placed inside a valid method/class |
| Declare a method and call it | Method is active in the session | Method exists in the compiled class output |
| Syntax error in source | `REJECTED`/diagnostics, session stays alive | Task fails/diagnostics, no artifact published |
| Code throws an exception at runtime | `SnippetEvent.exception()` | Exception at runtime loader/invocation, not a compiler result |
| Duplicate declaration name | `OVERWRITTEN` and dependent updates per REPL rules | Depends on input/version/artifact; not session overwrite |
| Stop/reset | Drop/close/recreate session; side effects do not auto-rollback | End task, close file manager; artifacts may still exist |
| Multiple users | State isolated per session; no concurrent JShell sharing | Isolated per build/output/class loader per request/version |
| Need a binary artifact to deploy | Not a primary product of the API | Direct use case |
| Stripped-down runtime environment | Requires `jdk.jshell` and a suitable engine | Requires an appropriate compiler/toolchain |
| Untrusted source | Must isolate execution and limit resources | Must also isolate compilation/annotation processing and execution |

A useful integration test for JShell is: create session A, declare `int n=7`, evaluate an expression in the same session, verify the output; create session B and verify B **does not** see `n`; close both. For `JavaCompiler`, test compiling two source versions into two separate artifacts and verify the loader does not accidentally load stale bytecode.

## 18. Common Pitfalls and How to Avoid Them

- **Treating JShell as a stateless mini-JavaCompiler:** throws away its interactive strengths and leads to flawed session boundaries.
- **Feeding multiple disconnected Java lines into one `eval` without completeness analysis:** easily causes unnecessary `REJECTED` results. Use `SourceCodeAnalysis` to split snippets.
- **Sending CLI commands like `/vars` to `shell.eval("/vars")`:** wrong API layer; use `variables()` and render your own UI.
- **Reading only the first event:** misses status changes on dependent declarations; iterate through every `SnippetEvent`.
- **Treating `value()==null` as an error:** valid methods, classes, and imports typically return no value.
- **Treating `status()==VALID` as safe code:** says nothing about file/network access, side effects, or infinite loops.
- **Conflating error diagnostics with runtime exceptions:** leads to misleading messages about the root cause of failure.
- **Using a single JShell singleton across tenants or threads:** leaks state and causes race conditions; enforce ownership and concurrency limits.
- **Assuming snippets can directly return host objects:** values are typically string representations; the engine and class loader may differ.
- **Keeping sessions alive indefinitely or forgetting `close()`:** can leak compiler/engine processes, class definitions, and resources.
- **Assuming `JavaCompiler` executes classes after compiling:** the caller needs a separate load/execute phase.
- **Assuming `JavaCompiler` only works on disk:** custom `JavaFileManager` implementations support in-memory compilation and output.
- **Using JShell to release production JARs:** lacks artifact/versioning/testing workflows; use a build/compiler pipeline.
- **Using the remote JShell engine as a sandbox:** API selection alone does not provide a full OS security boundary.

## 19. Solution Selection Checklist and Conclusion

Before choosing, answer these questions in order:

1. **Is the input an interactive Java snippet or a set of standard source files/classes/modules?** Stateful snippets point to JShell; standard build sources point to `JavaCompiler`.
2. **Do variables, methods, and imports need to persist across inputs?** If yes, JShell provides a stateful session out of the box.
3. **Is the needed result an immediate value/diagnostic or a storable/deployable artifact?** Immediate values favor JShell; stable artifacts favor `JavaCompiler`.
4. **Should code execute immediately as entered, or after review/testing/publishing?** JShell fits interactive testing; `JavaCompiler` cleanly separates compilation from execution.
5. **Who owns runtime state and resources?** JShell requires session lifecycle management; `JavaCompiler` requires file manager + artifact + class loader lifecycles.
6. **Is the source code trusted and isolated at the OS/process level?** If not, do not rely solely on either API for security.
7. **Does a prototype need to become a production feature?** Consider JShell for exploration and `JavaCompiler`/build tools for official packaging.

**Key takeaway:** *JShell is an API for building stateful, interactive Java experimentation sessions; JavaCompiler is an API for building Java compilation pipelines with artifacts and separate execution responsibilities.* JShell uses a compiler under the hood, so they should not be viewed as "interpreted Java" versus "compiled Java." The difference lies in the **usage contract, level of interactivity, state lifecycle, and type of output the system requires**.

**Java 17 Standard Documentation:** [jdk.jshell package](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jshell/jdk/jshell/package-summary.html), [JShell](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jshell/jdk/jshell/JShell.html), [SnippetEvent](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jshell/jdk/jshell/SnippetEvent.html), [SourceCodeAnalysis](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jshell/jdk/jshell/SourceCodeAnalysis.html), [JavaCompiler](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.html), and [StandardJavaFileManager](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/StandardJavaFileManager.html).
