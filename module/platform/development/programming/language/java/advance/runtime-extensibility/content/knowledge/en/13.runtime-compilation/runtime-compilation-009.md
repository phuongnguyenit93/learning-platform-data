# Closing the File Manager and Separating Compilation from Execution in Java

## 1. Goal and Use Cases

Java supports **compiling code while an application is running** through the `javax.tools.JavaCompiler` API. A host can accept source code from a code generator, create an SPI implementation, compile custom classes, and load the result to invoke via reflection or a shared interface. However, **the compilation task is not the execution task**, and `JavaFileManager` is not the class loader used to run code.

When designing this pipeline, you must clearly answer:

- Who owns and closes `StandardJavaFileManager`?
- When does `JavaCompiler.CompilationTask.call()` finish, and when is it safe to load classes?
- If compilation or resource closing fails, how do you guarantee **no invalid code or stale bytecode** gets executed?
- Can a file manager be reused across multiple compilations, and when should its lifecycle end?
- After closing the file manager, do `.class` files still exist, and who is responsible for releasing the class loader?
- How must the structure change for in-memory compilation, JAR dependencies, concurrent requests, or plugin hot reload?

**Core principle:** the **COMPILE** phase produces verified artifacts and owns a file manager with a bounded lifecycle; after both the task and file manager complete cleanly, the **LOAD/EXECUTE** phase consumes those artifacts with a **separate** loader and lifecycle. Never let a class loader or plugin code keep using a closed file manager.

## 2. Participating Objects and Scope of Responsibility

| API / Object | Responsibility | When to Close? |
|---|---|---|
| `ToolProvider.getSystemJavaCompiler()` | Obtains the Java compiler provided by the current runtime | Not a `Closeable`; may return `null` if no compiler exists |
| `JavaCompiler` | Creates compilation tasks | Not synonymous with a class loader or file manager |
| `JavaCompiler.CompilationTask` | Compiles a set of compilation units when `call()` is invoked | Wait for `call()` to finish before using artifacts |
| `StandardJavaFileManager` | Reads sources/classes/JARs, locates outputs, and creates file objects | `close()` at the end of its ownership scope; use `try-with-resources` |
| `DiagnosticCollector<JavaFileObject>` | Collects compiler errors/warnings | Not a file manager; readable after the task completes |
| `Path outputDirectory` | Holds `.class` bytecode artifacts | Not deleted when closing the file manager; cleaned by the application owner |
| `URLClassLoader` or custom class loader | Locates/defines classes in artifacts for execution | Close the loader once usage and plugin references/lifecycle end |
| Loaded objects/classes | Execute methods and can keep the class loader alive | Must be released per runtime contract |

Per Java 17, `JavaFileManager.close()` releases resources opened **directly or indirectly** by the manager and may throw `IOException`. Continuing to call the manager or file objects obtained from it **after closing** has unspecified effects except where explicitly permitted by the API. Do not rely on a specific implementation occasionally still working after `close()`.

`JavaFileManager.flush()` differs from `close()`: `flush()` pushes pending output resources; `close()` ends the usage lifecycle and releases related handles/caches. Calling `flush()` **does not replace** `close()` once the owner finishes the compilation phase.

## 3. Separating the Two Phases into a Clear Contract

A safe execution flow looks like:

```text
Receive source / validate request
              |
              v
Create ISOLATED output directory per build
              |
              v
          COMPILE PHASE
  ┌─────────────────────────────────────────┐
  │ JavaCompiler + DiagnosticCollector      │
  │ try (StandardJavaFileManager manager)   │
  │   CLASS_OUTPUT = output directory       │
  │   create compilation units              │
  │   CompilationTask.call()                │
  │ }  <-- close() at end of scope          │
  └─────────────────────────────────────────┘
              |
              v
    Task SUCCESS and close() SUCCESS?
          /                  \
         no                  yes
         |                    |
  report error, DO NOT run    v
                      verify artifact
                             |
                             v
                       EXECUTE PHASE
                      try (ClassLoader)
                        Class.forName(...)
                        call API / reflection
                      close loader
                             |
                             v
                    clean up old build
```

**The decisive boundary:** `CompilationTask.call()` returning `true` shows the task reported compilation success. Yet a wrapper method using `try-with-resources` only returns to the caller **after** `StandardJavaFileManager.close()` finishes. If `close()` throws an error, the wrapper method does not return normal success, and the caller never starts execution.

This prevents situations where "the task finished, yet a file handle, JAR cache, or output stream is still open" when a runtime immediately wants to consume, replace, or delete artifacts.

For asynchronous tasks, instead of assuming scheduling compilation equals having an artifact, complete the future only **after compile + close + validate all finish**. Only consumers receiving a success status may proceed to load/execute.

## 4. Complete Java 17+ Program: Compile, Close Manager, Then Execute

This example uses `JavaCompiler` to create a `dynamic.Message` class from a Java string, writes the source to disk, compiles into a new output directory, and loads it via `URLClassLoader`. The host must not load this generated class directly from its own classpath.

The example is kept standalone, requiring no third-party libraries and no pre-placed class name on the source path. Each run creates a unique output directory, avoiding the case where a failed compilation leaves `.class` files from a previous run in an old output folder.

**Single file `CompileThenRun.java` (placed in the working directory):**

```java
import java.io.IOException;
import java.net.URL;
import java.net.URLClassLoader;
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
import javax.tools.StandardLocation;
import javax.tools.ToolProvider;

public final class CompileThenRun {
    private static boolean compile(Path sourceFile, Path output,
                                   DiagnosticCollector<JavaFileObject> diagnostics)
            throws IOException {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("A JDK with jdk.compiler is required");
        }

        try (StandardJavaFileManager files = compiler.getStandardFileManager(
                diagnostics, Locale.ROOT, StandardCharsets.UTF_8)) {
            files.setLocationFromPaths(StandardLocation.CLASS_OUTPUT, List.of(output));
            Iterable<? extends JavaFileObject> sources =
                    files.getJavaFileObjectsFromPaths(List.of(sourceFile));
            List<String> options = List.of("--release", "17", "-proc:none");

            return Boolean.TRUE.equals(compiler.getTask(
                    null, files, diagnostics, options, null, sources).call());
        } // files.close() runs before compile(...) returns.
    }

    public static void main(String[] args) throws Exception {
        Path root = Path.of("build", "compiler-demo").toAbsolutePath();
        Path source = root.resolve("src/dynamic/Message.java");
        Files.createDirectories(source.getParent());
        Path output = Files.createTempDirectory(
                Files.createDirectories(root.resolve("outputs")), "run-");

        Files.writeString(source, """
                package dynamic;
                public final class Message {
                    public static String say() {
                        return "Hello from runtime compilation";
                    }
                }
                """, StandardCharsets.UTF_8);

        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();
        boolean compiled = compile(source, output, diagnostics);

        if (!compiled) {
            for (Diagnostic<? extends JavaFileObject> diagnostic
                    : diagnostics.getDiagnostics()) {
                if (diagnostic.getKind() == Diagnostic.Kind.ERROR) {
                    System.err.println(diagnostic.getMessage(Locale.ROOT));
                }
            }
            throw new IllegalStateException("Compile failed; execution skipped");
        }

        System.out.println("compiled=" + compiled);
        System.out.println("class-file-present=" +
                Files.isRegularFile(output.resolve("dynamic/Message.class")));

        try (URLClassLoader loader = new URLClassLoader(
                new URL[] { output.toUri().toURL() },
                ClassLoader.getPlatformClassLoader())) {
            Class<?> generated = Class.forName("dynamic.Message", true, loader);
            Object result = generated.getMethod("say").invoke(null);
            System.out.println("message=" + result);
        }
    }
}
```

### 4.1. Compile and Run Commands on Windows PowerShell

From the directory containing `CompileThenRun.java` using JDK 17 or later:

```powershell
New-Item -ItemType Directory -Force -Path build/host | Out-Null
javac --release 17 -d build/host CompileThenRun.java
java -cp build/host CompileThenRun
```

### 4.2. Commands on Linux/macOS

```bash
mkdir -p build/host
javac --release 17 -d build/host CompileThenRun.java
java -cp build/host CompileThenRun
```

The host only needs `build/host` on its classpath. Generated code is placed under `build/compiler-demo/outputs/run-.../dynamic/Message.class`; do not put that directory on the JVM's classpath when launching the host.

### 4.3. Exact Stdout on the Success Branch

```text
compiled=true
class-file-present=true
message=Hello from runtime compilation
```

The program was compiled with `javac --release 17` and verified on a newer JDK supporting release 17. The `run-...` directory has a random name generated by `Files.createTempDirectory`, which is not printed so stdout stays deterministic.

**Why is this sequence correct?**

1. `Files.createTempDirectory` creates a fresh output under the demo-owned root. You never accidentally load an old class when compiling a new version fails.
2. `ToolProvider.getSystemJavaCompiler()` verifies the environment has a compiler. Custom runtime images may lack `jdk.compiler`, in which case you must report unsupported capability instead of assuming it always exists.
3. `getStandardFileManager(...)` is created **inside `compile`**; the caller holds no reference to it and cannot use the manager outside its scope.
4. `setLocationFromPaths(StandardLocation.CLASS_OUTPUT, List.of(output))` instructs the compiler to write class files to an existing directory; output files may reside in package subdirectories.
5. `getJavaFileObjectsFromPaths(List.of(sourceFile))` turns `Path` into a compilation unit readable by the compiler. `List.of(...)` selects the `Collection<? extends Path>` overload, avoiding the deprecated `Iterable<Path>` overload.
6. `getTask(...).call()` executes the actual task; `Boolean.TRUE.equals(...)` treats only `Boolean.TRUE` as success, not `false` or `null`.
7. `try-with-resources` guarantees `files.close()` runs even if compilation fails or throws. The caller receives a normal return only after `compile` exits scope.
8. The `!compiled` branch prints error diagnostics and **throws before creating a class loader**. There is no "try running temporarily" an artifact that failed to compile.
9. After compiling, the host verifies the output file before using `URLClassLoader` and `Class.forName`. The loader uses the platform class loader as parent since the demo class uses only Java platform APIs. For code needing a host SPI, pick a parent that provides that SPI.
10. `URLClassLoader` has its own scope and `close()` call. Closing it is distinct from closing the compiler manager; the two resources belong to two different phases.

**Limitation of the example:** the code prints `class-file-present`, then calls `Class.forName`. In production, if a required artifact is missing, throw **right during validation** rather than continuing. The demo leaves behind sources and `run-...` directories so learners can inspect them; a real runtime needs a garbage-collection policy for artifacts once no loader uses them.

## 5. Why Must the File Manager Be Closed with try-with-resources?

An error-prone way to write it is:

```java
StandardJavaFileManager manager =
        compiler.getStandardFileManager(null, null, null);
boolean ok = compiler.getTask(null, manager, null,
        options, null, sources).call();
runGeneratedClass();  // executes while the manager may still be open
manager.close();       // skipped if runGeneratedClass throws
```

This is an **anti-pattern snippet** using undeclared variables/methods; it is not a standalone program. In the flawed pattern:

- `manager.close()` sits after execution code; if runtime logic throws an exception, the manager is never closed.
- The boundary between compiler and runtime is blurred, making it hard to define when JARs can be replaced or outputs deleted.
- If you forget to check `ok`, the code may load an old class from the same output directory.
- Across consecutive tasks, an exception in one step can leak file manager resources from other compilations.

Replace it with:

```java
boolean compiled;
try (StandardJavaFileManager manager =
        compiler.getStandardFileManager(diagnostics, null, null)) {
    // configure locations, create compilation units
    // ...
    compiled = Boolean.TRUE.equals(
            compiler.getTask(null, manager, diagnostics,
                    options, null, sources).call());
} // manager.close() runs here, even if an exception occurs

if (!compiled) {
    throw new IllegalStateException("Compilation failed");
}
// Use the validated output to load/execute.
```

This is an **illustrative snippet** assuming `compiler`, `diagnostics`, `options`, and `sources` exist; the complete program is in Section 4. In production, creating compilation units must also reside inside the manager's scope.

**Note on exceptions:** `close()` can throw `IOException`. With `try-with-resources`, if code inside the block also throws, the close error is attached as a **suppressed exception** on the primary exception. Never catch broadly, ignore `IOException` from close, and still treat the artifact as "ready to run."

## 6. Successful Compilation Does Not Mean Successful Execution

Separate outcomes into distinct states:

| State | Meaning | Action |
|---|---|---|
| `SOURCE_RECEIVED` | Input received, not yet analyzed/compiled | Validate source, encoding, and configuration |
| `COMPILING` | `CompilationTask.call()` is running | Do not allow loading yet |
| `COMPILE_FAILED` | Task returned false or failed to produce valid artifacts | Return diagnostics; strictly do not execute |
| `COMPILED` | Task succeeded and file manager closed cleanly | Proceed to artifact verification |
| `VALIDATED` | Expected class files, version, manifest/hash, and scope verified | Allow loader creation |
| `EXECUTING` | Load classes, initialize, instantiate, invoke per contract | Apply separate timeouts/lifecycle |
| `EXECUTION_FAILED` | Linkage, class init, constructor, or business logic error | Do not alter the compile-success verdict |
| `RETIRED` | No active run uses the artifact/loader anymore | Clear references, close loader, and delete artifacts when safe |

The state names above are **application design suggestions**, not built-in `JavaCompiler` enums. The compiler only reports compilation results and diagnostics; the application must manage its own state machine and execution preconditions.

For example, `ClassNotFoundException` when loading outputs may result from a wrong output path/loader even when `CompilationTask.call()` succeeded. `NoClassDefFoundError` or `UnsupportedClassVersionError` can arise from mismatched dependencies/versions. `InvocationTargetException` on reflection calls typically wraps an exception thrown by the running method. Those errors happen in the **execute phase** and should not be lumped into compiler diagnostics.

## 7. Compilation Error Path: Diagnostics and Stop Conditions

`DiagnosticCollector<JavaFileObject>` collects warnings and errors with severities such as `ERROR`, `WARNING`, `MANDATORY_WARNING`, `NOTE`, and `OTHER`. You can read `Diagnostic.getKind()`, `getLineNumber()`, `getColumnNumber()`, `getCode()`, `getMessage(locale)`, and `getSource()` when available. Avoid assuming every diagnostic has a valid line/column; when unknown, Javadoc defines a sentinel value indicating missing position info.

Reasonable handling:

1. Create a fresh collector **for each compilation job** or manage per-session collector resets.
2. Allocate an isolated output directory and build identifier before compiling.
3. Call `task.call()` exactly once per task. Never execute code just because a `.class` file exists.
4. When `false`, record diagnostics, transition to failed state, and never build a runtime class loader.
5. If `getTask`/`call` throws a runtime exception or `manager.close()` throws `IOException`, report a system/compile-infrastructure error; never flip it to `compiled=true`.
6. Never return sensitive source code or server paths in error messages to untrusted users; log full details in controlled storage.

Note: Some compiler messages may go to the writer or stderr rather than strictly into `DiagnosticCollector`. `getTask(out, ...)` lets you supply a writer; for thorough capture in production, handle both channels. `DiagnosticCollector` itself does not decide which severity counts as failure; **the `call()` result is the primary signal**.

### 7.1. When Compilation Fails Yet Old Classes Still Exist

With a reused output path like `build/classes`:

```text
Run 1: class A compiles successfully -> A.class appears.
Run 2: source A has a syntax error -> call() returns false.
Design flaw: still loads A.class from Run 1 -> runs stale code.
```

Proper solutions:

- Write each build into a **new, immutable** directory/namespace; publish a build only after compile, close, and validate all succeed.
- Delete outputs belonging **specifically to that build** when the job fails and no consumer holds references (never blindly wipe a shared directory).
- Record build ID/hash, expected file set, and artifact manifest; runtime verifies the right version rather than relying solely on class name.
- If forced to reuse a fixed output path, clean old artifacts **before** compiling under clear ownership and locking. Watch out for readers holding handles to class files/JARs on Windows.
- Never silently fall back to old bytecode unless application policy permits it; if falling back to a stable version, record it explicitly as a rollback decision.

Creating a new output directory in Section 4 illustrates the first option.

## 8. Does Closing the File Manager Delete .class Files or Unload Classes?

**No.** There are three distinct kinds of resources:

1. **Compiler/file manager resources:** streams, file handles, JAR read caches, file objects; terminated by `JavaFileManager.close()`.
2. **Generated artifacts:** `.class`/JAR/metadata files on disk or byte arrays in memory; persist per the output owner and do not disappear just because the manager closed.
3. **Classes defined in the JVM:** `Class<?>` objects and instances tied to a defining class loader; never "directly unloaded" by `manager.close()` or `URLClassLoader.close()`.

`URLClassLoader.close()` releases resources owned by the URL loader; it does not automatically stop threads, callbacks, registries, static references, or created instances. A class loader becomes eligible for collection only when no strong references keep it or its classes alive, depending on GC and runtime.

Thus the complete lifecycle comprises:

```text
Compile manager: OPEN -> task.call -> CLOSED
Artifact:        CREATED -> VALIDATED -> PUBLISHED -> RETIRED -> DELETED
Runtime loader:                       OPEN -> USE -> CLOSE -> eligible for GC
```

Do not hold `StandardJavaFileManager` inside a plugin object or cache spanning multiple executions. Do not delete class files the moment `manager.close()` finishes if loading has not completed yet. On Windows, deleting JARs while a loader still holds handles is especially prone to failure; tie cleanup timing to the **runtime loader's** lifetime, not just the compiler's.

## 9. When Can StandardJavaFileManager Be Reused?

The `JavaCompiler` Javadoc allows **reusing a standard file manager across multiple sequential compilation tasks**. The benefit is reducing JAR reading and filesystem scanning overhead. That does not mean every implementation supports concurrent tasks.

Two common strategies:

### 9.1. Dedicated File Manager per Build

```text
Job A: open manager A -> compile A -> close A -> validate A
Job B: open manager B -> compile B -> close B -> validate B
```

Advantages: clear ownership, no leakage of options/locations/caches between builds, easier error isolation. Disadvantage: repeated cost of reopening JARs and scanning paths. This is a sound choice for applications with moderate compile volume or strict isolation needs; Section 4 uses this strategy.

### 9.2. Reusing Across Sequential Tasks Within a Compile Session

```java
try (StandardJavaFileManager manager =
        compiler.getStandardFileManager(diagnostics, null, null)) {
    // Task 1 with open manager: .call() completes.
    // Sequential Task 2 also uses this manager after adjusting configuration.
    // Compilation units can be recreated within this scope.
}
// End of session: close manager once.
```

This is a **lifecycle pattern**, not a standalone program. Reuse only when tasks are ordered **sequentially**, the manager has not been closed, output/classpath settings are reset properly for each task, and no reader accesses incomplete artifacts. If multiple tenants/plugins compile concurrently, never share a manager without an explicit synchronization contract; give each job its own manager or serialize through a sequential compile queue.

`JavaFileManager` is permitted **not to support multi-threaded access on the manager itself**. The API requires supporting concurrent access to **distinct generated file objects**, yet that does not make the entire manager thread-safe. That is another reason to avoid an uncontrolled JVM-wide shared manager.

## 10. Separating via a Result API: Keep the Manager Inside the Compile Phase

In larger systems, represent the contract between the two phases with a DTO:

```java
record CompilationArtifact(
        String buildId,
        java.nio.file.Path outputDirectory,
        String mainClassName) {
}
```

This is an **illustrative snippet**. A service method like `CompilationArtifact compile(Request request)` can:

- Allocate fresh output/metadata and a dedicated manager.
- Collect diagnostics for that specific job.
- Return the artifact only when `call()` succeeds, the manager has closed, and files/checksums are verified.
- On failure, return structured compile errors/diagnostics without publishing an artifact.
- Never return `JavaFileManager`, `JavaFileObject`, or `CompilationTask` to runtime consumers.

The execution side receives `CompilationArtifact`, constructs the class loader/layer, verifies the entry point, executes within a managed lifecycle, and finally cleans up the loader/artifact.

To prevent races when deploying multiple versions, use **immutable build IDs**, staging directories, and atomic publish operations where supported by the filesystem. The "artifact ready" state must belong to a **specific compile job**, not a global field like `lastSuccessfulCompile` that another job could overwrite.

## 11. Classpath, Module Path, and Relationship Between Compile and Execute

Both phases must see the right dependencies, yet **the compiler's search path does not automatically become the runtime class loader's search path**.

For instance, the compile phase may supply dependency JARs:

```java
files.setLocationFromPaths(
        StandardLocation.CLASS_PATH, List.of(apiJar, dependencyJar));
files.setLocationFromPaths(
        StandardLocation.CLASS_OUTPUT, List.of(outputDirectory));
```

This is an **illustrative snippet** with `apiJar`, `dependencyJar`, and `outputDirectory` as existing `Path`s, not a standalone program.

The runtime must construct a loader with matching paths or expose the API via a parent; otherwise, a successfully compiled class may throw `NoClassDefFoundError` during execution. Conversely, do not blindly load all host libraries into the plugin loader when only one SPI is authorized.

With named modules (JPMS), compilation may need `MODULE_PATH`, `MODULE_SOURCE_PATH`, `--module-path`, `--module-source-path`, or per-module output locations. Runtime may need `ModuleFinder`, `Configuration`, and `ModuleLayer`; a simple `URLClassLoader` over a classpath directory **does not automatically create a named module layer**.

**Key separation:** choosing classpath vs. module path in the compiler is a build-time setting, whereas module/class readability at execution depends on the runtime's class loaders and module graph. Compilation success only proves the artifact was valid when checked by the compiler, not that runtime visibility is necessarily equivalent.

### 11.1. Choosing the API Shared Between Host and Generated Code

If generated code implements a host-defined SPI, the runtime parent loader must provide **the exact same `Class` object for that interface**; never let the child load a duplicate copy of the SPI. In Section 4, the parent is `ClassLoader.getPlatformClassLoader()` because the generated class depends only on Java platform APIs. For custom SPIs, usually use the host/API loader as parent or select an appropriate module layer.

## 12. In-Memory Compilation: Still Close the Manager and Output Streams

An application can supply source via in-memory `SimpleJavaFileObject` and use `ForwardingJavaFileManager` to capture `.class` bytes into `ByteArrayOutputStream`. This reduces disk writes, yet **does not eliminate lifecycle management**:

- The wrapper manager should properly delegate `close()`/`flush()` to the underlying manager and close any streams it owns.
- Never use `JavaFileObject`s tied to a closed manager as long-term artifact storage.
- After `task.call()` succeeds, **snapshot completed byte arrays** into an immutable `binaryName -> byte[]` map or separate artifact object.
- Only after the manager closes and data is verified should you pass that map to a custom class loader using `defineClass`.
- Custom managers must honor the `getJavaFileForOutput` contract, stream closing, thread safety, and diagnostic flow. Simply overriding one method does not guarantee compatibility with every compiler.

Equivalent flow:

```text
In-memory source JavaFileObject
  -> JavaCompiler + ForwardingJavaFileManager
  -> output streams / byte buffers
  -> task.call() succeeds
  -> close output streams and JavaFileManager
  -> immutable artifact snapshot
  -> ByteArrayClassLoader defines classes
  -> invoke
```

This is an **architecture diagram**, not runnable code. For basic use cases, `StandardJavaFileManager` with an output directory as in Section 4 is simpler and more reliable. If an in-memory compiler is required, rigorously test stream closing, immutability between compile and load, interdependent classes, and class identity.

## 13. Layer-Accurate Error Handling: Compile, Close, Load, and Execute

| Symptom | Common Origin | Correct Response |
|---|---|---|
| `getSystemJavaCompiler() == null` | No compiler in current runtime image/JDK | Do not compile; report requirement for runtime with `jdk.compiler` |
| `CompilationTask.call() == false` | Bad source or compiler error | Collect diagnostics and stop before loading |
| `IllegalArgumentException` from `getTask` or options | Invalid options/compilation units | Fix job config; never fall back to old artifacts |
| `IOException` creating output/getting files/closing manager | Filesystem, permissions, handles, or storage | Mark build incomplete; do not publish |
| `Files.isRegularFile(...) == false` | Expected artifact was not emitted | Validation fails; do not execute |
| `ClassNotFoundException` | Class loader cannot find binary name/path | Inspect output path and loader configuration |
| `NoClassDefFoundError` | Missing dependency or linkage failure | Inspect classpath/module graph at execute time |
| `UnsupportedClassVersionError` | Artifact built for a newer runtime | Use matching `--release` and verify environment |
| `ExceptionInInitializerError` | Static initializer of generated class threw | Diagnose execution logic; do not alter compile verdict |
| `InvocationTargetException` | Reflection-invoked method/constructor threw | Inspect `getCause()` and execution policy |
| Cannot delete/replace JAR after compile | Manager or runtime loader still holds handles | Close manager in compile phase and loader per lifecycle; never delete while in use |
| Wrong version runs after compile failure | Reused output path; stale class remained | Output per build ID; publish only verified new builds |

A system must distinguish **compilation errors**, **resource-closing errors**, **artifact validation errors**, and **execution errors** to report accurately. Collapsing everything into `catch (Exception) { return false; }` loses diagnostics, hinders resource cleanup, and can trigger dangerous fallbacks.

## 14. Concurrency, Thread Pools, and File Manager Ownership

Compilation is typically CPU-, I/O-, and memory-intensive. When concurrent requests arrive:

1. Assign a separate job ID and separate output directory.
2. Provide a new file manager per job, or use a pool/queue with bounded concurrency and an explicit policy.
3. Prevent the same file manager from being accessed concurrently by two compilation tasks unless thread safety is contracted.
4. Ensure source files and dependency inputs are not mutated mid-read by the compiler. For strict pipelines, snapshot selected sources/JARs before compiling.
5. Never let an executor proceed to execution solely because "a compile task was submitted"; wait for compile + close + artifact validation of that exact job.
6. When cancelling a task, verify real interrupt/cancellation behavior of the compiler implementation. Do not assume `Future.cancel(true)` immediately halts `javac` and cleans all output; clean unpublished artifacts only after confirming the job is no longer writing.
7. When unloading a plugin, detach callbacks/threads/references before closing the class loader, then delete artifacts once no executions remain active.

**Proper ownership:** the compiler manager belongs to a single compile scope; the runtime loader belongs to an execution/plugin scope; the output artifact belongs to a build/version scope. Never collapse these three lifecycles into one hard-to-control singleton.

## 15. Security: Runtime Compilation Is Not a Sandbox

Just because `JavaCompiler` accepts a source string does not mean generated code is safe to run in the same JVM. The compiler can read multiple files/classpath entries or execute **annotation processors** if configured; compiled code can open files, access networks, spawn threads, block threads, or call dangerous APIs with the process's privileges.

Required safeguards per trust model:

- Limit source size, file count, complexity, and concurrency; apply timeout/CPU/memory limits **at the process boundary** when strong isolation is needed.
- Expose only owner-authorized classpaths/module paths, avoiding leaks from an uncontrolled application classpath.
- The example uses `-proc:none` to disable annotation processing in the demo job. That **is not a sandbox** and does not stop generated code from running after compilation.
- Compile with `--release 17` to target Java 17 API/language/class-file levels, yet still audit runtime dependencies; that flag does not restrict runtime execution privileges.
- Do not run untrusted source directly in the same JVM relying solely on `URLClassLoader`/`ProtectionDomain`. Class loaders provide type/visibility boundaries, not OS resource and privilege isolation.
- When accepting code from outside the organization, consider a dedicated worker process/container with restricted filesystem, network, memory, and privileges, clear IPC, and cleanup lifecycle.

Security requirements for the compile phase and execute phase can differ: a compiler worker may only need write access to staging, while a runtime worker only needs read access to published artifacts. This separation aids auditing, rollback, and least-privilege design.

## 16. Recommended Test Suite for a Runtime Compiler

| Test Case | Expected Behavior |
|---|---|
| Valid source | `call()` true, manager closed, artifacts present, loader loads and invokes properly |
| Syntax-invalid source | `call()` false, `ERROR` diagnostics received, no loader created and no execution |
| Missing/invalid output file | Validation stops before execution; no fallback to another artifact |
| `close()` throws `IOException` | Job is not published as successful; exception is preserved/suppressed properly |
| Two compiles with same binary name | Separate outputs/build IDs; runtime never accidentally loads previous version's class |
| Compiler unavailable | Clearly reports missing `jdk.compiler`; never invokes old class via reflection |
| Two concurrent jobs | Outputs, diagnostics, file managers, and states isolated per job |
| Wrong dependency at execution | Records separate load/link error; does not treat compiler diagnostics as sole source |
| Generated method throws exception | Compile succeeds yet execution fails; `InvocationTargetException.getCause()` handled properly |
| Task cancellation / timeout | Partial artifacts never published; outputs not deleted while worker still writes |
| In-memory manager | Streams closed, bytes snapshotted, underlying manager closed, loader independent of manager |
| Plugin unload/redeploy | No listeners, threads, caches, TCCL, or loader references retaining old version |
| Runtime lacks I/O permissions | Reports accurate file manager/output error; strictly no silent fallback |

One of the highest-value integration tests is: **compile version A successfully → edit source to fail in version B → verify B never runs A.class**. If this test fails, the pipeline has not truly separated compilation from execution by build identity.

## 17. Design Mistakes to Avoid

- Calling `getTask(...).call()` and immediately executing code inside the manager's `try` block with no reason to keep the manager open.
- Closing the manager only on the success path, forgetting `try-with-resources` so runtime or compile errors leak file handles.
- Confusing `flush()` with `close()`, or continuing to use file objects after closing the manager.
- Reusing one manager across concurrent compilation jobs with no thread-safety contract.
- Sharing one output directory and checking only "does a `.class` file exist" without verifying build ID + task result.
- Equating `compiled=true` with `executed=true`, or failing to distinguish compile errors from exceptions thrown by generated methods.
- Using the compiler classpath as the default runtime classpath without verifying SPI/type-identity boundaries.
- Closing `URLClassLoader` as if it automatically unloads classes or kills live threads/callbacks.
- Writing class files into a predictable shared directory where multiple tenants overwrite each other.
- Treating `-proc:none` or a custom class loader as a complete security solution for untrusted code.
- Deleting artifacts immediately upon closing the file manager even though the runtime class loader has not finished reading or still lazy-loads dependencies.

**Quick code review checklist:** (1) file manager has clear owner and scope; (2) compile + close finish before execute; (3) outputs are isolated per build; (4) compile failures block loading; (5) artifacts are validated; (6) runtime loader closes per its own lifecycle; (7) cleanup never touches an active build.

## 18. Conclusion and Official References

The pair `JavaCompiler` + `StandardJavaFileManager` handles **bytecode generation**; `ClassLoader`/`ModuleLayer` handles **bytecode loading and execution**. The two sides exchange data via artifacts, yet should never share resource lifecycles.

Rules you can apply immediately:

1. Accept source and create an isolated per-build output directory.
2. Run `JavaCompiler.getTask(...).call()` inside a `try (StandardJavaFileManager ...)` scope.
3. Exit the scope so the manager is `close()`d; treat compilation as successful only if both the task and close succeed.
4. If compilation fails, stop and return diagnostics; never load stale outputs.
5. Verify artifacts belong to the right build before creating a loader, loading classes, and executing.
6. Close loaders and reclaim artifacts per the execution lifecycle, not the file manager lifecycle.

Official Java SE 17 documentation: [JavaCompiler](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.html), [JavaFileManager](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaFileManager.html), [StandardJavaFileManager](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/StandardJavaFileManager.html), [ToolProvider](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/ToolProvider.html), [URLClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html).
