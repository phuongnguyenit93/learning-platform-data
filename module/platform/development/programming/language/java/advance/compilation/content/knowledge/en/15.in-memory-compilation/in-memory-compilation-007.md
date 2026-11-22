# Managing buffer, file manager, and failure-result lifecycles

**In-memory Java compilation** is the technique of passing source code to `JavaCompiler` without having to save each `.java` file to disk, and capturing `.class` classfiles into byte buffers instead of an ordinary output directory. It is useful for dynamic code generation, solution grading, code analysis, or experimenting with short Java sources inside a developer tool.

However, writing a `SimpleJavaFileObject` holding a source code string is only the first step. A reliable design must also answer:

- **Who owns the buffers?** Who creates, holds, copies, and releases the bytecode?
- **How long does the file manager live?** When does the compiler need it, when must `close()` be called, and can it be reused?
- **What if compilation fails?** May partially created classfiles be returned, or should the previous result be retained?
- **Where do diagnostics go?** How do you distinguish source errors, configuration errors, I/O exceptions, and environments lacking a compiler?
- **What about multiple concurrent tasks?** How do you avoid one task writing into another task's buffers?

Core design principle: **each compilation attempt owns its own temporary state; only publish a result snapshot after the entire attempt succeeds; every exit path closes the file manager and never leaks partial buffers.**

This lesson uses **Java 17+**, the standard `javax.tools` API, and an example compiling a class in RAM followed by compiling an intentionally ill-typed version. The main program runs and prints the status of both attempts without writing generated classfiles to disk.

## 1. Data flow in an in-memory compilation attempt

Basic diagram:

~~~text
Java source string
      |
      v
StringSource : SimpleJavaFileObject
      |
      |  JavaCompiler.getTask(... compilationUnits)
      v
MemoryFileManager : ForwardingJavaFileManager
      |
      |  compiler calls getJavaFileForOutput(...)
      v
MemoryClass : SimpleJavaFileObject
      |
      |  openOutputStream() returns ByteArrayOutputStream
      v
Temporary bytecode buffer for the compilation attempt
      |
      +-- task.call() == true
      |       |
      |       v
      |   Copy result -> BuildResult SUCCESS
      |
      +-- task.call() == false
      |       |
      |       v
      |   Do not publish bytecode -> BuildResult FAILED
      |
      +-- Exception / missing compiler
              |
              v
          Handle separately by root cause

Finally: close file manager, drop references to temporary state
~~~

This is a **transactional flow enforced by application policy**, not a guarantee that `javac` performs an automatic "transaction." The compiler may have already emitted one or more classfiles before discovering an error in another compilation unit. Therefore, **the application deliberately chooses not to publish outputs if the overall attempt fails**.

### Objects with different lifecycles

| Object | Recommended lifecycle | Responsibility |
| --- | --- | --- |
| Source string/`StringSource` | During the attempt or retained longer if needed for diagnostics | Holds the text of one compilation unit |
| `DiagnosticCollector` | **Per compilation attempt** | Records diagnostics for that specific attempt |
| `StandardJavaFileManager` | Single attempt or controlled reuse | Looks up classes, sources, modules, and resources from the standard environment |
| `MemoryFileManager` | **Per attempt** in the reference design | Redirects class outputs from the compiler to RAM, holding the temporary output map |
| `MemoryClass`/`ByteArrayOutputStream` | From when the compiler requests output until snapshot/cleanup | Receives bytes of a single classfile |
| `CompilationTask` | **One `call()` invocation** | Coordinates a single compilation |
| `BuildResult` | After the attempt completes | Returns status and approved data |

Caching and component reuse can be designed, but that requires dedicated rules for opening/closing, invalidation, and synchronization. To learn the mechanism and avoid state leaks, **a new file manager + collector per attempt** is the clear choice.

## 2. A FileObject does not have to be a real file

`JavaFileObject` is an abstract model for a source unit or class. They can be backed by physical files, URIs, or in-memory data.

A string-backed Java source typically extends `SimpleJavaFileObject`, providing:

~~~java
@Override
public CharSequence getCharContent(boolean ignoreEncodingErrors) {
    return sourceCode;
}
~~~

This is a **method snippet inside a subclass**, not a standalone program. The compiler will call `getCharContent(...)` to read the contents. The source's URI must be valid and typically ends with `.java` matching `JavaFileObject.Kind.SOURCE`.

An output class written to RAM typically overrides:

~~~java
@Override
public OutputStream openOutputStream() {
    return buffer;
}
~~~

This is also a **method snippet inside a subclass**, where `buffer` is a `ByteArrayOutputStream`. When the compiler creates a classfile, it writes bytes into that stream. `ByteArrayOutputStream.toByteArray()` returns a **copy** of the current contents, allowing the result to exist independently of the temporary stream.

**Note:** closing an `OutputStream` does not necessarily clear memory. `ByteArrayOutputStream.close()` does not immediately release its backing array; the buffer continues holding bytes as long as it remains referenced. When designing lifecycles, **drop references** or `reset()` when appropriate, rather than calling `close()` and assuming memory is cleared.

## 3. Why is `ForwardingJavaFileManager` needed?

`JavaCompiler` uses `JavaFileManager` to locate sources/classes and to create output files. You should not reimplement the JDK's entire class lookup mechanism just to change where classfiles are written.

`ForwardingJavaFileManager` lets you **delegate** complex operations to the standard file manager and override only what needs changing, such as:

~~~java
@Override
public JavaFileObject getJavaFileForOutput(
        JavaFileManager.Location location,
        String className,
        JavaFileObject.Kind kind,
        FileObject sibling) throws IOException {

    if (kind == JavaFileObject.Kind.CLASS) {
        // Create a JavaFileObject whose output stream stores bytes in RAM.
    }
    return super.getJavaFileForOutput(location, className, kind, sibling);
}
~~~

This is **illustrative code inside a subclass of `ForwardingJavaFileManager`**. It explains the hook where the compiler requests a destination for a classfile. In the main example, output class objects are held in a `Map` scoped to the compilation attempt.

A file manager is not an immutable data store: it holds state, references its delegate, and may hold resources. `JavaFileManager` supports `close()`; the standard file manager should normally be closed when no longer needed. Using `try-with-resources` is a clean way to guarantee closing **even if the task fails or throws an exception**.

Do not close the file manager **before** `task.call()` completes: the compiler may still need it to read dependencies, write classfiles, or run annotation processing rounds.

## 4. Java 17+ example: compiling source to bytes, publishing only on success

Create the file **`InMemoryLifecycleDemo.java`** with the following contents. The complete example includes a source object, class output object, forwarding file manager, and build result. No auxiliary source files are created at runtime: both input source and class output remain in RAM.

~~~java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.FileObject;
import javax.tools.ForwardingJavaFileManager;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileManager;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public final class InMemoryLifecycleDemo {
    private InMemoryLifecycleDemo() {
    }

    private static final class StringSource extends SimpleJavaFileObject {
        private final String sourceCode;

        StringSource(String binaryName, String sourceCode) {
            super(URI.create(
                    "string:///" + binaryName.replace('.', '/')
                            + JavaFileObject.Kind.SOURCE.extension),
                    JavaFileObject.Kind.SOURCE);
            this.sourceCode = sourceCode;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return sourceCode;
        }
    }

    private static final class MemoryClass extends SimpleJavaFileObject {
        private final ByteArrayOutputStream bytes =
                new ByteArrayOutputStream();

        MemoryClass(String binaryName, Kind kind) {
            super(URI.create(
                    "mem:///" + binaryName.replace('.', '/')
                            + kind.extension),
                    kind);
        }

        @Override
        public OutputStream openOutputStream() {
            bytes.reset();
            return bytes;
        }

        byte[] snapshot() {
            return bytes.toByteArray();
        }
    }

    private static final class MemoryFileManager
            extends ForwardingJavaFileManager<StandardJavaFileManager> {

        private final Map<String, MemoryClass> generated =
                new LinkedHashMap<>();

        MemoryFileManager(StandardJavaFileManager delegate) {
            super(delegate);
        }

        @Override
        public JavaFileObject getJavaFileForOutput(
                JavaFileManager.Location location,
                String className,
                JavaFileObject.Kind kind,
                FileObject sibling) throws IOException {

            if (kind == JavaFileObject.Kind.CLASS) {
                MemoryClass output = new MemoryClass(className, kind);
                generated.put(className, output);
                return output;
            }
            return super.getJavaFileForOutput(
                    location, className, kind, sibling);
        }

        Map<String, byte[]> snapshot() {
            Map<String, byte[]> copy = new LinkedHashMap<>();
            for (var entry : generated.entrySet()) {
                copy.put(entry.getKey(), entry.getValue().snapshot());
            }
            return Map.copyOf(copy);
        }

        @Override
        public void close() throws IOException {
            try {
                super.close();
            } finally {
                generated.clear();
            }
        }
    }

    private record BuildResult(
            boolean success,
            Map<String, byte[]> classes,
            boolean hasErrors) {
    }

    private static BuildResult compile(
            JavaCompiler compiler, String sourceCode) throws IOException {

        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();

        StandardJavaFileManager delegate =
                compiler.getStandardFileManager(
                        diagnostics, Locale.ROOT, StandardCharsets.UTF_8);

        try (MemoryFileManager manager = new MemoryFileManager(delegate)) {
            JavaFileObject source =
                    new StringSource("demo.Generated", sourceCode);

            List<String> options = List.of(
                    "--release", "17",
                    "-proc:none");

            JavaCompiler.CompilationTask task = compiler.getTask(
                    null,
                    manager,
                    diagnostics,
                    options,
                    null,
                    List.of(source));

            boolean success = Boolean.TRUE.equals(task.call());
            boolean hasErrors = diagnostics.getDiagnostics().stream()
                    .anyMatch(d -> d.getKind() == Diagnostic.Kind.ERROR);

            // Do not use temporary classfiles if the whole attempt fails.
            Map<String, byte[]> published = success
                    ? manager.snapshot()
                    : Map.of();

            return new BuildResult(success, published, hasErrors);
        }
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            System.err.println("COMPILER_UNAVAILABLE");
            return;
        }

        String valid = """
                package demo;
                public class Generated {
                    public static int answer() {
                        return 42;
                    }
                }
                """;

        String invalid = """
                package demo;
                public class Generated {
                    public static int answer() {
                        return "not an int";
                    }
                }
                """;

        BuildResult ok = compile(compiler, valid);
        BuildResult bad = compile(compiler, invalid);

        System.out.println("ok=" + ok.success());
        System.out.println("okClasses=" + ok.classes().size());
        System.out.println("bad=" + bad.success());
        System.out.println("badClasses=" + bad.classes().size());
        System.out.println("badHasErrors=" + bad.hasErrors());
    }
}
~~~

Compile the **driver program** and run with a JDK that includes a compiler:

~~~sh
javac --release 17 -encoding UTF-8 InMemoryLifecycleDemo.java
java InMemoryLifecycleDemo
~~~

When a compiler is present and the compilation environment is valid, **exact stdout**:

~~~text
ok=true
okClasses=1
bad=false
badClasses=0
badHasErrors=true
~~~

Explanation:

- `valid` is a `demo.Generated` class with a proper `int` return type. The first attempt compiles successfully and returns a map containing **one** classfile.
- `invalid` returns the string `"not an int"` from a method whose return type is `int`. The second attempt emits an `ERROR` diagnostic and fails compilation.
- For the failing attempt, `bad.classes().size()` is **0 by policy of the `compile` method**: the code calls `manager.snapshot()` only when `success == true`.
- Temporary buffers from the failing attempt are not published. This **does not mean the compiler never wrote any bytes** before reporting the error.
- The two calls to `compile` each have their own file manager, output map, and collector. Results from the first attempt do not leak into the next.

In the missing-compiler branch, the program only prints `COMPILER_UNAVAILABLE` to **stderr** and returns, so the five stdout lines above do not appear. Only when running on a runtime with a compiler should you expect the stdout shown above.

### Notable design points in the example

**1. Sources separated from outputs.** `StringSource` uses a `.java` URI and supplies content via `getCharContent`. `MemoryClass` uses a `.class` URI and supplies an `OutputStream` to the compiler.

**2. Using the standard file manager as delegate.** `MemoryFileManager` intercepts only `getJavaFileForOutput` for `Kind.CLASS`; source lookup, JDK APIs, and non-intercepted operations remain handled by the standard file manager.

**3. Intercepting outputs where the compiler requests them.** Each class requested by the compiler creates one `MemoryClass` stored by `className`. Real projects may generate additional inner/nested/anonymous classes; **do not assume one source file produces only one classfile**. This simple example generates only one class.

**4. Snapshot before closing.** Once `task.call()` succeeds, `manager.snapshot()` copies bytes via `toByteArray()`. When `try-with-resources` closes the manager, `generated.clear()` drops references to temporary buffers. The result map retains the copied byte arrays.

**5. Not mixing failed results.** The failing attempt returns `Map.of()`, even though temporary buffers might have received partial output. Never cache or load bytecode from an unsuccessful attempt.

**6. Disabling annotation processing in the experiment.** `-proc:none` keeps the example focused on pure Java compilation and avoids accidentally loading discovered annotation processors. In systems requiring processors, enable them intentionally and configure the processor path and trust boundaries accordingly.

**7. The result map is not deeply immutable.** `Map.copyOf(copy)` prevents adding/removing keys, but `byte[]` remains a **mutable** array. If a public API returns bytecode to multiple callers, copy arrays on return, use a read-only wrapper, or design clear ownership. A point-in-time snapshot **does not automatically make every nested value immutable**.

## 5. Buffer lifecycle: allocate, write, snapshot, discard

A `ByteArrayOutputStream` is allocated when the compiler requests class output. During writes, the internal array capacity can grow. With many classes or a large classfile, total memory used during compilation can exceed the total size of the final bytecode.

### Before compiling

- Create a new collector for diagnostics.
- Create a new file manager for the current attempt.
- Create source `JavaFileObject` instances holding known contents.
- Set limits on source size, concurrent tasks, and processing time per system requirements.

### During compilation

- The compiler calls `getJavaFileForOutput(...)` to request a destination for a classfile.
- The buffer receives bytes across write calls.
- Never treat any buffer currently being written as a classfile ready to load.
- The compiler may generate multiple classes from one or more compilation units.

### When compilation succeeds

- Only after `Boolean.TRUE.equals(task.call())`, create a snapshot of all classfiles.
- Confirm that required outputs are actually present before passing them to a class loader or cache.
- Transfer ownership of the copied data to the result object.
- Close the file manager and then release temporary copies.

### When compilation fails

- Record diagnostics to report back to the caller.
- Exclude all temporary classfiles **from the public result**.
- Close the file manager even when there is no output or only partial output.
- Do not overwrite the cache of a previous good build with a failed build.
- If errors must be kept for users, keep **copied diagnostics**, not the compiler/manager/buffers past their lifetime.

### Why `reset()` is not the same as `close()`

`ByteArrayOutputStream.reset()` resets the valid byte count so the buffer can be reused from the start, yet typically **retains the allocated array capacity**. `close()` does not eliminate references holding the buffer. Neither clears sensitive data from memory.

For sources with sensitive data, enforce strict lifecycle policies, restrict logs/raw dumps, and avoid uncontrolled caching. Do not claim that calling `reset()` is sufficient to guarantee wiping bytes from RAM.

## 6. Managing `JavaFileManager` properly

Resources must be closed when no longer used. In the example:

~~~java
try (MemoryFileManager manager = new MemoryFileManager(delegate)) {
    // Create task, call task.call(), snapshot if successful.
}
~~~

This is an **illustrative snippet inside the `compile` method**, not a standalone program. `MemoryFileManager.close()` calls `super.close()` to close the delegate, then `generated.clear()` in a `finally` block to drop output references. Even if `task.call()` throws an exception, Java still calls `close()`.

### Why not close the file manager immediately after creating the task?

`getTask(...)` only prepares compilation. The compiler still needs the file manager during `task.call()` to look up the classpath, platform classes, source files, and output paths. If closed too early, the task may fail due to using a closed file manager.

### Why not keep a file manager indefinitely?

A file manager may maintain resources and caches related to paths, ZIPs/JARs, or lookup results. If kept long-term, an invalidation strategy and usage bounds are needed. For multi-request services, using a dedicated manager per request makes it easier to avoid stale state and mixed-up outputs.

### Can `StandardJavaFileManager` be reused?

The API allows controlled file manager reuse across compiler tasks, especially to reduce filesystem scanning costs. However, **that does not mean it is safe to use the same instance concurrently from multiple threads**. Reusing requires understanding API and implementation contracts, resetting custom locations, and managing lifecycles tightly. This lesson uses a new manager per attempt to avoid relying on concurrency assumptions.

### What if opening the file manager succeeds but task preparation throws an exception?

Wrapping the file manager in `try-with-resources` right after creation ensures closing if an exception occurs when creating `JavaFileObject`, configuring options, calling `getTask(...)`, or calling `call()`. If creating the standard file manager itself fails before returning an object, the caller must handle the exception at the environment-setup level.

## 7. Failure outcomes are more than just `false`

Distinguish:

| Scenario | Signal | How to handle |
| --- | --- | --- |
| Compiler missing | `ToolProvider.getSystemJavaCompiler() == null` | Return `UNAVAILABLE` status; do not invoke task |
| Source syntax/type error | `task.call() == false`, `ERROR` diagnostic | Return `FAILED` and source error list; do not publish output |
| Warnings yet compilation succeeds | `task.call() == true` and warnings exist | May publish, along with warnings per policy |
| Invalid option configuration | May throw exception or report tool error | Classify as `CONFIGURATION_ERROR`; do not pretend it is a source error |
| File manager/path hits I/O error | `IOException` or related implementation error | Return `INFRASTRUCTURE_ERROR`, close resources |
| Task cancelled or timed out by orchestrator | Application-defined cancel/timeout status | Do not publish output; clean state and avoid partial cache |

In the sample code, `compile` returns `BuildResult` for the two cases where **the task returns normally** (success or compile error). It throws `IOException` if an I/O error occurs at the file manager layer; other unexpected exceptions can still propagate. **Do not turn every exception into a `false` result resembling a user's Java error.**

For a production API, you can use a result type containing:

~~~text
BuildOutcome
  status: SUCCESS | COMPILE_FAILED | UNAVAILABLE | INFRASTRUCTURE_ERROR
  diagnostics: immutable / copied list
  classBytes: present only on SUCCESS
  metadata: timestamp, compiler version, source hash (if needed)
~~~

This is a **design schema**, not Java code. The goal is letting callers distinguish the handling path: user fixes code, admin fixes runtime, or system retries per policy. `status` must come with the **constraint that classBytes is absent on failure**.

### Why keep diagnostics when a build fails?

`DiagnosticCollector` may report:

- `Diagnostic.Kind.ERROR`: language error or configuration error with an associated location.
- `WARNING` / `MANDATORY_WARNING`: compiler warnings.
- `NOTE` / `OTHER`: other messages.

You can read `kind`, `source`, `lineNumber`, `columnNumber`, and `getMessage(Locale)`. There is no guarantee that every diagnostic has a line/column; `Diagnostic.NOPOS` indicates an unavailable position. When returning results through an API, **copy the needed diagnostic fields** rather than retaining compiler/file manager objects after closing.

An extension inside `compile` can count errors:

~~~java
long errors = diagnostics.getDiagnostics().stream()
        .filter(d -> d.getKind() == Diagnostic.Kind.ERROR)
        .count();
~~~

This is an **illustrative snippet placed inside the `compile` method** after the task executes. Do not infer error count to equal broken classfile count or invalid file count. One source can produce multiple errors; the compiler can also stop early.

## 8. Why can a failure leave behind temporary output?

A real characteristic of compiling multiple sources/rounds is that the compiler may request and write several classfiles before detecting an error elsewhere. Thus:

~~~text
Build attempt:
  A.java -> A.class already written to buffer
  B.java -> compile error
  --------------------------
  task.call() -> false

Proper policy:
  DO NOT return A.class as a complete build
  Do not update the "latest successful" cache
  Return diagnostics to the caller
  Clear the A.class buffer and all temporary outputs
~~~

This is an **illustrative scenario**, not a promise on the order in which the compiler writes classfiles across all runs. Do not design tests requiring A.class specifically to appear before B.java reports an error. What must be tested is that **regardless of whether temporary output exists, a failed outcome never publishes partial bytecode**.

If the system stores a previous good build, separate:

~~~text
committedBuild : usable artifact from the most recent SUCCESS
workingBuild   : temporary buffer for a new compile attempt

SUCCESS -> verify, copy, replace committedBuild atomically
FAILURE -> discard workingBuild, keep committedBuild as before
~~~

This model resembles **application-managed commit/rollback**, not a rollback guaranteed by `JavaCompiler`. For long-lived caches or class loaders, this prevents situations where some classes belong to the new version while others belong to the old version.

### Is returning `Map.of()` on error enough?

That is a **publishing policy**, not an automatic resource-release strategy. If the manager stays alive holding `generated`, temporary bytes still occupy memory. Therefore **both** are needed: do not return output in a failed result **and** close/dereference the file manager so memory can be reclaimed when no longer in use.

## 9. Multiple compilation attempts and concurrency

A service typically handles multiple tasks simultaneously. Key risks:

1. Two requests share the **same `Map<String, MemoryClass>`** and the same class name, causing overwritten or mismatched bytecode.
2. An old collector is not reset, causing user B to receive user A's diagnostics.
3. One request closes the file manager while another request is still using it.
4. The classfile cache is updated entry by entry; another request reads a half-new, half-old result.
5. Large source code or many concurrent compiler tasks increase heap pressure.

Safe default approach:

- Each request gets its own `DiagnosticCollector`, `MemoryFileManager`, and output map.
- Call `task.call()` on that request's task; do not share the same `CompilationTask` across threads.
- After `SUCCESS`, create a dedicated snapshot and update the cache atomically by version/build ID.
- On `FAILED`/cancelled, clean up the request's state without touching published builds.
- Cap concurrency and input/output sizes; for untrusted code, use an isolated resource-bounded environment.

**Not every JavaCompiler object can be shared arbitrarily across parallel tasks.** Thread-safety must be verified per the API/implementation used. Organizing without sharing mutable file managers is a lower-risk starting point.

## 10. When to use `SoftReference`, caches, or pools

Memory optimizations prone to misunderstanding:

**`SoftReference`:** merely a reference mechanism the GC may reclaim; not a cache strategy with guaranteed lifetime/capacity. Avoid using it to represent the "current active build" that must always exist when callers use it.

**Reusing ByteArrayOutputStream:** can reduce allocations if reuse and resetting are understood accurately, yet buffers can retain large arrays, holding heap after large tasks. Never reuse buffers across two concurrent requests.

**Classfile caching:** useful when the same source, compiler options, and dependencies stay unchanged. Cache keys must capture all conditions affecting output (source, version, compiler, classpath/module path, processors, options, etc.), not just class name.

**File manager pooling:** can reduce overhead in specialized workloads, yet requires managing ownership, state, closing, invalidation, and concurrency. Avoid premature optimization before measuring. A fresh manager per attempt is usually easier to keep correct.

Remember that `byte[]` is mutable, so a read-only map alone does not guarantee classfile contents cannot be altered. When sharing results with untrusted parties, use defensive copies or structures protecting data ownership.

## 11. Optimizing diagnostics and lifecycle testing

To ensure code is not only "right on the happy path," include the following tests:

| Test case | Expectation |
| --- | --- |
| One valid Java source, one class | `SUCCESS`; exactly one non-empty classfile |
| Source with method returning wrong type | `COMPILE_FAILED`, with ERROR diagnostic; public output empty |
| Two sources, one fails mid-process | Publish **no** output whatsoever from the failing attempt |
| Compiler API lacks implementation | Return `UNAVAILABLE`; do not invoke `getTask` |
| File manager throws exception on write | Return infrastructure error; resources closed in `finally` |
| Same class name, two consecutive attempts | No leaking of classfiles from previous attempt into next attempt |
| Two concurrent requests | Outputs/diagnostics separated; no cross-talk |
| Compiler generates inner/nested classes | Output map contains all classfiles generated by compiler |
| Callback fails during snapshot | Do not publish partial results; consistent state |

A good testing strategy uses instrumentation in the file manager to record the counts of `openOutputStream`, `close`, and classfiles; those metrics need not be exposed in the production API, but help detect state leaks.

When testing compilation failures, **do not assert that partial classfiles must exist**: compilation ordering is not guaranteed identical across JDK versions. Assert only that public output is empty when `task.call()` does not succeed.

### Which commands to test with?

The example file above is a standalone program. Run:

~~~sh
javac --release 17 -encoding UTF-8 InMemoryLifecycleDemo.java
java InMemoryLifecycleDemo
~~~

Then try changing `invalid` to another valid source and observe `bad` becoming `true`. If you want error details, print each `Diagnostic` inside `compile` or return a structured diagnostic list in `BuildResult`. You do not need to run or load RAM classfiles into the JVM just to check compiler status.

If you want to **load succeeded bytecode**, that is the next step for an appropriate `ClassLoader`. The classloader should only receive bytes after SUCCESS and only when the source is trusted. **Never automatically load/execute class bytes from untrusted users** solely because compilation succeeded.

## 12. Common design mistakes

| Mistake | Why it is dangerous | Better approach |
| --- | --- | --- |
| Using a static output map for all attempts | Data mixes across multiple builds | Dedicated map per attempt |
| Returning bytes immediately inside `getJavaFileForOutput` | File has not been finished by the compiler yet | Snapshot after the task completes successfully |
| Returning all bytes when `task.call() == false` | Partial output may be inconsistent | Do not publish failed outputs |
| Only calling `ByteArrayOutputStream.close()` | Does not mean the buffer was released | Drop references, bound caches, close manager |
| Not closing the file manager | May retain file handles/caches/buffers | `try-with-resources` and cleanup in `finally` |
| Calling `close()` before `task.call()` | Compiler still needs the file manager | Keep the manager alive throughout the task |
| Treating every exception as a source error | Masks I/O, option, and runtime errors | Separate compile failures from infrastructure failures |
| Holding diagnostic objects and file managers long-term | Easily retains object graphs/resources | Copy needed diagnostic fields |
| Sharing a manager across threads | Risk of race conditions and state contamination | Request-level isolation or verified synchronization |
| `Map.copyOf` and assuming byte arrays are immutable | `byte[]` is still mutable | Defensive copy/wrapper when handing out access |
| Publishing cache class by class | Readers observe an incomplete build | Publish the whole snapshot atomically by version |
| Assuming the compiler is always present | Minimal runtimes may return null | Check `ToolProvider` first |

## 13. Reinforcement exercises

**Exercise 1 — Success and failure.** Run `InMemoryLifecycleDemo.java`, and explain why `okClasses=1` while `badClasses=0`. Confirm that empty output on the failing attempt is the **wrapper's policy**, not a guarantee that the compiler wrote zero bytes.

**Exercise 2 — Printing diagnostics.** Replace `boolean hasErrors` with a list of diagnostic values containing `kind`, `line`, `column`, and `message`. Copy the required data into the result without keeping the file manager alive.

**Exercise 3 — Multiple classfiles.** Add a named inner class to `demo.Generated`. Predict which additional classfile will appear in the map and why one source does not equal one output class.

**Exercise 4 — Improper state reuse.** Intentionally change the output map from instance-level on `MemoryFileManager` to static, then run two attempts with the same name `demo.Generated`. Analyze the stale-cache risk and how to isolate it.

**Exercise 5 — I/O exception.** Design a test file manager that throws `IOException` when creating output. Distinguish that exception from `task.call() == false` caused by invalid source, and verify `close` is still called.

**Exercise 6 — Atomic publishing.** Suppose a service has build A currently in use and begins build B. Design `workingBuild` and `committedBuild` so that B's failure does not corrupt A.

**Exercise 7 — Concurrency.** Two requests compile the same class name with different contents. Identify the objects that must be kept separate and how to prevent one request from returning another request's bytes.

### Self-assessment questions

1. **What is the role of `MemoryFileManager`?** — Intercepting class output creation requests and providing `JavaFileObject` instances that write to RAM, while delegating other operations to the standard file manager.
2. **When can class bytes be snapshotted?** — After the task finishes **successfully** and outputs are ready.
3. **Does `task.call() == false` guarantee no classfile was written?** — No; it only indicates the overall attempt did not succeed.
4. **Why is `try-with-resources` needed?** — Guarantees closing the file manager on both success and exception paths.
5. **Does `ByteArrayOutputStream.close()` immediately free all RAM?** — No; references must be dropped so data can be reclaimed.
6. **Should the same diagnostic collector be kept across builds?** — Not without a clear reset/ownership mechanism; create a new one per attempt by default.
7. **Does `Map.copyOf` make byte arrays immutable?** — No; the map forbids structural edits, but `byte[]` inside remains mutable.
8. **If the compiler is missing, what status kind applies?** — `UNAVAILABLE`, distinct from `COMPILE_FAILED`.
9. **Can one Java file generate multiple classfiles?** — Yes, for example nested/anonymous classes.
10. **Why must cache updates be published as a snapshot?** — Prevents other consumers from seeing a partially completed new build.

**Summary:** With in-memory compilation, the hardest part is not creating a `ByteArrayOutputStream`, but **managing ownership and exit paths**. Create a dedicated file manager and buffer per attempt; let the compiler finish before reading bytes; copy/publish outputs only on success; retain useful diagnostics on failure; close resources in all cases; and never let state from a failed build leak into a good build or another request.