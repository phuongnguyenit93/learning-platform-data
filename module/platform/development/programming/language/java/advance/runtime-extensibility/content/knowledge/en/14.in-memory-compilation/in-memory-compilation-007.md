# Limiting Source Size, Output, and Duration of In-Memory Compilation Jobs

JavaCompiler (JSR 199, package `javax.tools`) enables accepting Java source code as Strings/JavaFileObjects, compiling it, and storing `.class` files in memory. This suits grading tools, code generation systems, dynamic expressions, and host-managed compilation services. However, if a user submits overly large source code, triggers excessive bytecode generation, or supplies a code construct that makes the compiler work for a long time, a single task can consume most of the JVM's resources.

This lesson designs and experiments with **three distinct limits**: input size, output size/count, and execution duration. The core point is distinguishing **logical limits that `JavaCompiler`/file managers can check** from **hard resource limits** that are only truly reliable when compilation runs inside a monitored and isolated process.

## 1. Why Is a Single Input Limit Not Enough?

Suppose an API receives an 8 KiB Java source file. A small size does not guarantee lightweight compilation: the source might generate many anonymous/nested classes, trigger complex type inference, or contain expressions that consume heavy compiler CPU and heap. Conversely, a valid source file larger than a few KB is not necessarily complex. Policies should therefore check multiple dimensions:

| Resource | Risk if uncontrolled | Where to enforce the limit |
| --- | --- | --- |
| Source UTF-8 byte count | Request body, JSON/String, parsing, and diagnostics consume RAM | Request ingress, **before** reading the full body |
| UTF-16 code unit count and source file count | Many Strings/file objects already allocated; filenames and total size exceed bounds | Input validator before `getTask` |
| Number of generated class files | Many classes/inner classes inflate entry counts and metadata | `JavaFileManager.getJavaFileForOutput` |
| Total `.class` bytes emitted | Consumes memory when holding bytecode in `ByteArrayOutputStream`/Map | `OutputStream` returned by file manager, checked on every write |
| Diagnostics and compiler text | Many errors can cause log amplification and huge responses | Bounded `DiagnosticListener` and `Writer` storage |
| Wait time (wall-clock) | Request or worker held open for too long | Deadline when waiting on `Future` or child process |
| Actual CPU, heap, native memory | One task degrades or crashes the host JVM | Separate process and OS/container limits |
| Concurrent task count | Many small jobs add up and exhaust resources | Queue + concurrency cap at the scheduler layer |

**There is no standard `JavaCompiler` parameter meaning "compile for at most 2 seconds and 64 MiB RAM".** The API provides extension points to control file I/O and receive diagnostics; enforcing CPU, heap, or task lifecycles must be handled by the execution layer.

The numbers used in the lab are **examples**, not safety thresholds guaranteed by Java: at most 8,192 UTF-16 units, 8,192 source UTF-8 bytes, 8 class files, 65,536 total `.class` bytes, 5 retained diagnostic messages capped at 160 characters each, 1,024 characters of auxiliary compiler text, and a 2-second `Future` wait.

## 2. Input Limits: What to Measure and When?

A Java `String` is indexed by UTF-16 code units. `String.length()` is **not** the UTF-8 byte count: Vietnamese text, non-BMP Unicode characters, and escapes can produce different byte sizes. If an API receives data over the network, distinguish:

- **Request bytes**: bytes transmitted over the wire, which may be compressed before sending; set quotas for both compressed size and decompressed size if `Content-Encoding` is allowed.
- **Decoded source bytes**: byte count when the source is encoded as UTF-8, appropriate for source artifact size policies.
- **String length**: UTF-16 units held on the heap, useful as an early gate before re-encoding.
- **File count and batch total bytes**: do not limit only individual files; 100 files × 8 KiB is still a substantial total.

A simple check after the `String` has already been created:

~~~java
// Illustration: applied before creating the compilation task.
if (source.length() > 8_192) {
    throw new IllegalArgumentException("source UTF-16 length limit");
}
if (source.getBytes(StandardCharsets.UTF_8).length > 8_192) {
    throw new IllegalArgumentException("source UTF-8 byte limit");
}
~~~

The snippet above **does not protect the HTTP ingress layer** because the input has already been read into a `String`. In a real service, stop reading when exceeding the quota at the `InputStream`/`BodyPublisher`/parser level, bounding item counts and total bytes before constructing large `String` objects. Only after that should you wrap them into `JavaFileObject` instances for the compiler.

Set explicit policies for encoding (UTF-8), package/class names, valid filenames, single vs. multiple compilation units, and allowed compiler options. Never accept a raw command-line options string concatenated arbitrarily by users; options can alter the classpath, processors, output paths, or compiler behavior.

## 3. Output Limits: Do Not Wait Until All Bytecode Is Emitted

In in-memory compilation, we typically implement:

- **`SimpleJavaFileObject`** for sources: `getCharContent` returns a `String`.
- **`ForwardingJavaFileManager`** wrapping the standard file manager and overriding `getJavaFileForOutput` to intercept class files.
- **Output `JavaFileObject`** whose `openOutputStream` returns a dedicated stream writing bytecode into a `ByteArrayOutputStream`.
- **`DiagnosticListener`** capturing errors/warnings, instead of letting unbounded messages accumulate in an unlimited buffer.

A flawed check is summing byte array sizes after `compilationTask.call()` finishes and only then deciding "over limit". By that time, memory has already been consumed. Better: **before each `write(byte[], off, len)`, check remaining quota before writing**. If the quota is exhausted, throw `IOException` and mark the output as over-limit.

You also need a quota on **the number of `.class` files**: very many empty or tiny files still carry object, hash map, URI, and metadata overhead. Do not count bytes for only a single class; count the **sum** of outputs across all classes emitted by the same task.

A byte quota in the file manager **is not equivalent to a heap quota**. The compiler also holds ASTs, symbol tables, constant pools, diagnostics, and temporary buffers in RAM. `ByteArrayOutputStream` can over-allocate capacity and `toByteArray()` copies the array. Thus a bytecode cap does not bound total RAM usage.

## 4. Java 17+ Lab: In-Memory Compiler with Quotas and Soft Timeout

The following example is **a complete program**. It compiles a Java class from a `String`, stores emitted `.class` files in a memory map, caps total bytecode and file count, limits stored diagnostics, bounds the text writer, and waits up to a timeout. It does not execute the newly compiled class.

Single file: **BudgetCompilerDemo.java**. Runs on **JDK 17+**, requiring no external libraries.

~~~java
import java.io.ByteArrayOutputStream;
import java.io.FilterOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.io.Writer;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticListener;
import javax.tools.FileObject;
import javax.tools.ForwardingJavaFileManager;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public final class BudgetCompilerDemo {
    private static final int MAX_SOURCE_CHARS = 8_192;
    private static final int MAX_SOURCE_BYTES = 8_192;
    private static final int MAX_CLASS_FILES = 8;
    private static final long MAX_CLASS_BYTES = 65_536;
    private static final int MAX_DIAGNOSTICS = 5;
    private static final int MAX_DIAG_CHARS = 160;
    private static final int MAX_OTHER_TEXT = 1_024;
    private static final long WAIT_MILLIS = 2_000;

    private record Result(
            String status,
            int classCount,
            long classBytes,
            boolean classPresent,
            int diagnosticsStored) {}

    private static Result empty(String status) {
        return new Result(status, 0, 0, false, 0);
    }

    private static final class MemorySource extends SimpleJavaFileObject {
        private final String source;

        MemorySource(String binaryName, String source) {
            super(URI.create("mem:///src/"
                    + binaryName.replace('.', '/') + Kind.SOURCE.extension),
                    Kind.SOURCE);
            this.source = source;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return source;
        }
    }

    // Bounded storage; do not use DiagnosticCollector which retains every diagnostic.
    private static final class LimitedDiagnostics
            implements DiagnosticListener<JavaFileObject> {
        private final List<String> kept = new ArrayList<>();

        @Override
        public void report(Diagnostic<? extends JavaFileObject> diagnostic) {
            if (kept.size() >= MAX_DIAGNOSTICS) {
                return;
            }
            String message = diagnostic.getMessage(Locale.ROOT);
            if (message.length() > MAX_DIAG_CHARS) {
                message = message.substring(0, MAX_DIAG_CHARS);
            }
            kept.add(diagnostic.getKind() + ": " + message);
        }
    }

    // Cap auxiliary text written by the compiler via the Writer parameter of getTask.
    private static final class LimitedWriter extends Writer {
        private final StringBuilder buffer = new StringBuilder();
        private boolean truncated;

        @Override
        public void write(char[] chars, int off, int len) {
            Objects.checkFromIndexSize(off, len, chars.length);
            int room = MAX_OTHER_TEXT - buffer.length();
            int n = Math.min(len, Math.max(room, 0));
            buffer.append(chars, off, n);
            if (n < len) {
                truncated = true;
            }
        }

        @Override
        public void write(String text, int off, int len) {
            Objects.checkFromIndexSize(off, len, text.length());
            int room = MAX_OTHER_TEXT - buffer.length();
            int n = Math.min(len, Math.max(room, 0));
            buffer.append(text, off, off + n);
            if (n < len) {
                truncated = true;
            }
        }

        @Override public void flush() {}
        @Override public void close() {}
    }

    // Keep class bytecode only in memory; do not write classes to a directory.
    private static final class LimitedFileManager
            extends ForwardingJavaFileManager<StandardJavaFileManager> {
        private final Map<String, byte[]> classes = new HashMap<>();
        private int outputFiles;
        private long outputBytes;
        private boolean limitReached;

        LimitedFileManager(StandardJavaFileManager delegate) {
            super(delegate);
        }

        private void reserve(int amount) throws IOException {
            // Subtraction avoids overflow when adding to the amount already used.
            if (amount < 0 || amount > MAX_CLASS_BYTES - outputBytes) {
                limitReached = true;
                throw new IOException("class bytes quota exceeded");
            }
            outputBytes += amount;
        }

        @Override
        public JavaFileObject getJavaFileForOutput(
                Location location, String binaryName,
                JavaFileObject.Kind kind, FileObject sibling)
                throws IOException {
            if (kind != JavaFileObject.Kind.CLASS
                    || outputFiles >= MAX_CLASS_FILES) {
                limitReached = true;
                throw new IOException("class file count/type limit");
            }
            outputFiles++;

            URI uri = URI.create("mem:///classes/"
                    + binaryName.replace('.', '/') + kind.extension);

            return new SimpleJavaFileObject(uri, kind) {
                @Override
                public OutputStream openOutputStream() {
                    ByteArrayOutputStream bytes = new ByteArrayOutputStream();

                    return new FilterOutputStream(bytes) {
                        @Override
                        public void write(int value) throws IOException {
                            reserve(1);
                            out.write(value);
                        }

                        @Override
                        public void write(byte[] data, int off, int len)
                                throws IOException {
                            Objects.checkFromIndexSize(off, len, data.length);
                            reserve(len);
                            out.write(data, off, len);
                        }

                        @Override
                        public void close() throws IOException {
                            super.close();
                            classes.put(binaryName, bytes.toByteArray());
                        }
                    };
                }
            };
        }

        // Disallow the task from writing additional resource/source files to disk.
        @Override
        public FileObject getFileForOutput(
                Location location, String packageName,
                String relativeName, FileObject sibling) throws IOException {
            limitReached = true;
            throw new IOException("non-class output is disabled");
        }
    }

    private static Result compileNow(
            String binaryName, String source, Path emptyClasspath)
            throws IOException {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            return empty("NO_JDK_COMPILER");
        }

        LimitedDiagnostics diagnostics = new LimitedDiagnostics();
        LimitedWriter text = new LimitedWriter();

        try (LimitedFileManager files = new LimitedFileManager(
                compiler.getStandardFileManager(
                        diagnostics, Locale.ROOT, StandardCharsets.UTF_8))) {

            List<String> options = List.of(
                    "--release", "17",
                    "-proc:none",
                    "-classpath", emptyClasspath.toString());

            JavaCompiler.CompilationTask task = compiler.getTask(
                    text,
                    files,
                    diagnostics,
                    options,
                    null,
                    List.of(new MemorySource(binaryName, source)));

            boolean success = Boolean.TRUE.equals(task.call());
            String status;
            if (files.limitReached) {
                status = "OUTPUT_LIMIT";
            } else if (text.truncated) {
                status = "COMPILER_TEXT_LIMIT";
            } else {
                status = success ? "OK" : "COMPILATION_ERROR";
            }

            return new Result(
                    status,
                    files.classes.size(),
                    files.outputBytes,
                    files.classes.containsKey(binaryName),
                    diagnostics.kept.size());
        }
    }

    private static Result compileWithBudget(
            String binaryName, String source, Path emptyClasspath) {

        // Fast-fail before creating JavaFileObject/CompilationTask.
        if (source.length() > MAX_SOURCE_CHARS) {
            return empty("SOURCE_LIMIT");
        }
        if (source.getBytes(StandardCharsets.UTF_8).length
                > MAX_SOURCE_BYTES) {
            return empty("SOURCE_LIMIT");
        }

        // Daemon thread is for lab purposes only: does not enforce a hard CPU/heap deadline.
        ExecutorService executor = Executors.newSingleThreadExecutor(job -> {
            Thread worker = new Thread(job, "compiler-demo-worker");
            worker.setDaemon(true);
            return worker;
        });

        Future<Result> future = executor.submit(
                () -> compileNow(binaryName, source, emptyClasspath));
        try {
            return future.get(WAIT_MILLIS, TimeUnit.MILLISECONDS);
        } catch (TimeoutException ex) {
            future.cancel(true); // Only requests interruption; may still be running.
            return empty("SOFT_TIMEOUT");
        } catch (InterruptedException ex) {
            future.cancel(true);
            Thread.currentThread().interrupt();
            return empty("INTERRUPTED");
        } catch (ExecutionException ex) {
            // In production: log exception/cause; do not return stack traces to the client.
            return empty("COMPILER_FAILURE");
        } finally {
            executor.shutdownNow(); // Best effort; does not guarantee the thread stops immediately.
        }
    }

    public static void main(String[] args) throws Exception {
        // Empty classpath directory used to avoid seeing host classes.
        // The example source and .class outputs are still kept in memory.
        Path emptyClasspath = Files.createTempDirectory("empty-javac-cp-");
        try {
            String source =
                    "package demo; public final class Hello { "
                    + "public static int answer() { return 42; } }";

            Result normal = compileWithBudget(
                    "demo.Hello", source, emptyClasspath);
            System.out.println("status=" + normal.status());
            System.out.println("classPresent=" + normal.classPresent());
            System.out.println("classCount=" + normal.classCount());
            System.out.println("withinOutputBudget="
                    + (normal.classBytes() <= MAX_CLASS_BYTES));
            System.out.println("diagnosticsStored="
                    + normal.diagnosticsStored());

            // Rejected before the compilation step.
            Result huge = compileWithBudget(
                    "demo.Hello", "x".repeat(MAX_SOURCE_BYTES + 1),
                    emptyClasspath);
            System.out.println("oversize=" + huge.status());
        } finally {
            Files.deleteIfExists(emptyClasspath);
        }
    }
}
~~~

Notes on the code:

- `Result` retains metadata for demonstration. In a real system, you can retain `Map<String, byte[]>` in a **verified successful result** to load classes afterward. The lab deliberately does not execute the bytecode.
- Each `getJavaFileForOutput` event counts toward the file count; every `write` call checks the quota before retaining bytes. Even if the compiler catches an `IOException` and turns it into a diagnostic or `RuntimeException`, the `limitReached` flag still classifies the class-output quota violation.
- The lab uses the standard file manager for classpath/JDK module lookup, while redirecting **class output** into memory. An empty temporary directory is created solely to specify the classpath; it is not where `.class` files are stored.
- The **`-proc:none`** option disables annotation processing. This reduces one vector of external code execution during compilation, without turning `JavaCompiler` into a sandbox. Never pass arbitrary options, classpaths, or processor paths from a request.
- `LimitedDiagnostics` caps only **the number of retained messages** and characters stored per message; the compiler itself may still generate many diagnostics or construct large messages before the callback receives them.
- `LimitedWriter` caps the number of characters retained from the auxiliary writer. It cannot limit the CPU/heap used by the compiler to construct strings before calling `write`.
- Aborting via `IOException` is a **lab output-control mechanism**. Different compiler/provider implementations might throw different errors; any bytes recorded before failure must be discarded, and **no class must be published when status is not OK**.
- If `SOFT_TIMEOUT` occurs, the task may still be running on the daemon thread and holding references to inputs, the file manager, or the classpath. Thus this program is meant for learning quota mechanics, and is **not sufficient for serving untrusted source code inside a shared JVM**.

### 4.1. Build and Run

Using JDK 17+:

~~~bash
javac -encoding UTF-8 BudgetCompilerDemo.java
java BudgetCompilerDemo
~~~

With normal input, the compiler finishes within the wait limit and produces one class. Expected stdout:

~~~text
status=OK
classPresent=true
classCount=1
withinOutputBudget=true
diagnosticsStored=0
oversize=SOURCE_LIMIT
~~~

These output lines assume the compiler finishes within **2 seconds** on a machine with sufficient resources. If the machine is overloaded or the JVM initializes the compiler slower than the lab's deadline, the status can be `SOFT_TIMEOUT`: **wall-clock timeouts are not deterministic output behavior**. Do not use 2 seconds as a cross-machine compatibility requirement; choose deadlines based on measured latency and service levels.

If running the program on a Java runtime lacking the `jdk.compiler` module, `ToolProvider.getSystemJavaCompiler()` may return `null`. Run with a JDK distribution that includes the compiler. No separate source file, external dependencies, or host classpath changes are required.

### 4.2. Why All Three Limits Are Useful

In the normal branch: the source is checked before the compiler starts; the file manager receives and gates every byte of bytecode; the host waits only up to the set deadline. In the oversize branch: the string is rejected before creating the task; the status is explicitly `SOURCE_LIMIT`.

A trickier case: a 2 KiB input that compiles into 30 classes. The counter in `getJavaFileForOutput` catches exceeding **`MAX_CLASS_FILES`** even while total bytes remain small. Another case emits a single 100 KiB class: `reserve(...)` catches exceeding **`MAX_CLASS_BYTES`** the moment a write crosses the threshold. Both must result in `OUTPUT_LIMIT` and never return a partial artifact to the caller.

If syntax is invalid, the compiler can report `COMPILATION_ERROR`, while the listener retains at most the first `MAX_DIAGNOSTICS` messages, each at most `MAX_DIAG_CHARS`. If the compiler attempts to write auxiliary text beyond `MAX_OTHER_TEXT`, the code flags `COMPILER_TEXT_LIMIT`. Output limits are independent of parse/type-check outcomes.

## 5. Timeouts in the JVM: Wait Timeout vs. CPU Limit

In the demo, `Future.get(timeout, TimeUnit.MILLISECONDS)` **sets a limit on how long the calling thread waits for a result**. Upon expiration, `future.cancel(true)` attempts to interrupt the worker. That **does not mean** the compiler thread has stopped. The compiler might be computing without checking interrupts, holding heap/CPU, and continuing after the API has returned `SOFT_TIMEOUT`.

Also note:

- `Future.isDone()` after cancel may report the future as finished per the `Future` contract, **without confirming that all running work has stopped**.
- `ExecutorService.shutdownNow()` attempts to interrupt running tasks, but JDK documentation does not guarantee it will stop an uncooperative task.
- A daemon thread still consumes resources while the JVM is alive; marking it daemon only allows the JVM to exit without waiting for that thread.
- A timed-out request whose worker has not exited must still count toward **resource-consuming active jobs**; you cannot immediately hand its concurrency slot to another user as if the job had actually stopped.
- Trying to force-stop a thread with `Thread.stop()` is not a safe compiler management solution. Process-level isolation is required if forced termination is needed.

Therefore, name statuses and SLAs accurately: **`SOFT_TIMEOUT`** means the caller stopped waiting; it does not promise that the compiler's CPU/RAM budget was enforced.

A subtle bug is closing the file manager, deleting the temporary classpath, or publishing outputs **immediately after `Future.get` expires** while the worker is still using those objects. A real design must ensure resources have unified ownership and lifecycles. If the compiler cannot be safely interrupted, move the work into a worker process that can be terminated before cleanup.

## 6. Architecture to Use When Hard Limits Are Required

To compile code from multiple users or untrusted sources, a stronger design is:

~~~text
HTTP/request gateway
    |
    | byte/source count quota + authentication + queue limit
    v
scheduler (max concurrent compiles, per-tenant budget)
    |
    v
isolated compiler worker process/container
    |   pinned JDK version, -proc:none
    |   allowlisted options, dedicated classpath
    |   OS/container CPU + memory + process + filesystem limits
    |   in-memory source/class output with quotas
    |
    +--> response only on successful compile, eligible output/diagnostics
    |
    +--> timeout/quota violation: terminate worker, cleanup, mark FAILED
~~~

A worker process can continue using **`javax.tools.JavaCompiler` and an in-memory file manager** just like the lab; separating processes does not force compiling via files on disk. Sources can enter the worker over controlled IPC, and bytecode can be returned via a size-bounded protocol. The host must verify message lengths before allocating buffers.

If accepting the `javac` CLI compiler in a separate process, the host can set a timeout on `Process` (the code below is an **illustrative snippet, not a standalone program**):

~~~java
// Assumes the executable path, source file, classpath, and output dir
// are all host-controlled; output is redirected to avoid pipe blocking.
Process process = new ProcessBuilder(
        javacPath,
        "--release", "17",
        "-proc:none",
        "-classpath", safeClasspath,
        "-d", controlledOutputDirectory,
        sourceFilePath)
        .redirectOutput(ProcessBuilder.Redirect.DISCARD)
        .redirectError(ProcessBuilder.Redirect.DISCARD)
        .start();

boolean finished = process.waitFor(2, TimeUnit.SECONDS);
if (!finished) {
    process.destroyForcibly();
    process.waitFor();
    throw new IllegalStateException("COMPILER_TIMEOUT");
}
if (process.exitValue() != 0) {
    throw new IllegalStateException("COMPILATION_ERROR");
}
~~~

Here `Process.waitFor(timeout, unit)` returns `false` if the deadline expires, and `destroyForcibly()` requests process termination. This is a **more useful enforcement path than `Future.cancel(true)`**, though still incomplete for production:

- A child process can spawn child processes; you must manage the **process tree/process group/container** appropriately for the OS, not just kill a single PID.
- After `destroyForcibly`, the process may not die instantly; calling `waitFor()` afterward helps reap it, though you still need an overall deadline policy and OS error handling.
- Compiler outputs, stdout/stderr, files in the output directory, logs, and IPC volume must all be bounded. The code above discards text to avoid pipe deadlocks, so it **captures no diagnostics**; production systems need bounded readers if error messages must be returned.
- A Java process using `-Xmx` bounds only part of the Java heap; native memory, CPU, file descriptors, process count, and filesystem usage require container/cgroup/Windows Job Objects or equivalent constraints.
- Compiling with the `javac` CLI writes files to a directory; if bytecode must stay entirely in memory, run the `JavaCompiler` API **inside the isolated process** and send results back over size-bounded IPC.

Hard-limit enforcement depends on the OS/container execution layer and resource configuration. `Process.kill` does not itself impose heap, CPU, or disk limits, nor prevent every side effect of an over-privileged process.

## 7. Security Policy for Classpath, Processors, and Runtime

A dynamic compilation service has an attack surface beyond source size. Key controls:

| Component | Recommended policy | Reason |
| --- | --- | --- |
| JDK and `--release` | Pin worker JDK and supported language/target version | Reproducible results, prevents incompatible APIs |
| Annotation processing | Default `-proc:none`; enable only vetted processors | Processors are code executable during compilation |
| Classpath/module path | Allowlist vetted dependencies; never blindly forward full host classpath | Limits impact and information leakage from the host |
| Compiler options | Construct option list server-side; reject arbitrary flags from clients | Prevents altering file read/write paths and policies |
| File manager | Capture `ClassOutput` and forbid/control all other output kinds | Avoids leaking task-generated files/resources |
| Diagnostics | Cap count, text size, and returned details | Prevents log amplification or unnecessary source exposure |
| Compiled artifact | Publish only after `OK` status, size checks, and class name validation | Never use bytecode from failed/timed-out jobs |
| Execution | Never run freshly compiled classes in a high-privilege host JVM | Successful compilation does not prove code is safe |

A class can compile cleanly and then, upon loading/initialization, access files, open network connections, spawn threads, or burn CPU. `JavaCompiler` **does not verify the safety of the generated program**. Therefore, if user programs must be executed, execution requires its own sandbox/process isolation and separate budgets, decoupled from compilation budgets.

You can log binary names, artifact hashes, JDK version, byte counts, diagnostic counts, and actual duration for auditing; avoid logging full sources unnecessarily and protect sensitive details inside diagnostics.

## 8. Measuring, Budgeting, and Handling Concurrency

Per-job limits are insufficient if the host accepts many jobs simultaneously. Even if each job has a 64 KiB output cap, compiling can temporarily use hundreds of MiB of heap; 100 concurrent jobs can still overload the host. The service also needs:

1. **Concurrency ceiling**: maximum number of compiler workers/processes, with per-tenant limits.
2. **Bounded queue**: cap waiting requests and queue wait time; return `BUSY`/429 when full instead of queuing without bound.
3. **Admission control**: check source quotas right before queuing or assigning a worker, avoiding buffering many decoded bodies.
4. **End-to-end deadline**: define clearly whether duration covers queueing, JVM startup, compiler initialization, compilation, result transfer, and cleanup, or compilation alone; never mix metrics.
5. **Per-process resource quotas**: CPU, RAM, process count, file descriptors, disk space, and IPC output.
6. **Metrics**: total source bytes, class count/bytes, diagnostics retained/truncated, queue wait, wall-clock runtime, CPU time where reliably measured, and timeout/kill rates.
7. **Lifecycle cleanup**: cancel the job and verify the worker/process has exited before reusing the slot. If a worker timed out yet remains alive, track it as an active job.
8. **Conditional result cache**: if caching compilations, keys must include source hash, JDK/version, compiler options, and dependency set. The cache also needs size/TTL limits.

A deadline measured only from when the worker starts can leave requests waiting indefinitely in the queue. A deadline measured from request arrival must leave enough time for downstream stages; a job that already expired in the queue should be rejected before starting a compiler.

In a multi-task file manager, never share a JVM-global static counter across all jobs without proper concurrency design. The lab creates a fresh `LimitedFileManager` per invocation and writes outputs on that job's compiler thread; counters belong to **a single task**, not shared across concurrent compilation jobs.

## 9. Further Experiments to Understand Limits

The following experiments can be performed on the lab program itself, changing **one policy at a time** and rebuilding:

### A. Exceeding Source Limit

Keep the source as `"x".repeat(MAX_SOURCE_BYTES+1)`. Expected `SOURCE_LIMIT` occurs **before submitting the compiler task**, so no bytecode or compiler diagnostics are produced. Once a request has already been materialized as a `String`, the lab's check only prevents further work, without protecting the heap already spent receiving the request.

### B. Exceeding Class File Count

Change `MAX_CLASS_FILES` to `0` and run with valid `Hello` source. `getJavaFileForOutput` flags the output limit when the compiler requests the first class. The job should return `OUTPUT_LIMIT` or `COMPILER_FAILURE` depending on how `IOException` is interpreted by the compiler/driver; unsuccessful runs must never publish artifacts. With the lab code, if `task.call` returns and `limitReached` is observed afterward, the status is `OUTPUT_LIMIT`. When consistent error codes across compiler implementations are needed, catch/normalize causes in the worker layer.

### C. Exceeding `.class` Byte Count

Change `MAX_CLASS_BYTES` to `64`. The compiler begins emitting class output, but writes exceed the quota. Do not collect into one large byte array and check length only at the end; the file manager must abort before the write that crosses the threshold. Inspect the count and flag, confirming the resulting class is not published.

### D. Too Many or Overlong Diagnostics

Supply a source deliberately containing many syntax and type-checking errors. `LimitedDiagnostics` stores at most 5 strings, each truncated to at most 160 message characters (excluding the kind prefix). However, the compiler may still have constructed long original messages: this cap bounds **memory inside the listener's collection**, not the entire compiler cost.

### E. Soft Timeout

Reduce `WAIT_MILLIS` to `1` and run repeatedly several times. You can observe `SOFT_TIMEOUT` even for tiny programs because initializing the compiler takes time. This demonstrates why you must measure latency and never infer from "timed out" that the in-JVM task was killed. Do not turn this experiment into a stress test on a shared machine if you cannot track still-alive workers.

### F. Same Source, Many Concurrent Jobs

Send many simultaneous requests through a queued scheduler. Even when each job's source and output stay within quota, aggregate CPU/heap/latency can spike dramatically. Bounding worker count and rejecting when out of capacity is mandatory for multi-tenant systems.

## 10. Common Pitfalls When Designing Compilation Quotas

| Symptom | Common cause | Fix |
| --- | --- | --- |
| API runs out of RAM before compiler starts | Read request into a `String` before checking size | Enforce quotas during streaming/decoding and cap total file count |
| ASCII source works, Vietnamese exceeds byte limit | Confused `length()` with UTF-8 byte count | Check both UTF-16 length and UTF-8 byte count |
| Bytecode exceeds cap despite post-`call()` check | Buffered entire `ByteArrayOutputStream` before checking | Gate every `write` in the output stream |
| Hundreds of tiny classes inflate heap | Capped bytes but forgot to cap class count | Cap output file count, metadata, and total bytes |
| Logs/diagnostics exhaust memory | Unbounded `DiagnosticCollector`, `Writer`, or response | Apply quotas to listener and writer; cap response size |
| `Future` reports timeout while CPU stays high | `cancel(true)` is cooperative interruption; compiler may not stop | Use process isolation, real termination, and cleanup |
| On timeout, scheduler immediately admits a new job | Released permit while worker was still running | Release capacity only after worker/process actually exits |
| Compiler reads host dependencies or runs unknown processors | Used default classpath/processor path or client-controlled options | Host-controlled classpath and options, `-proc:none` |
| Limit error caught, yet partial class output returned | Stream had already written some bytes before failure | Publish artifacts only when the entire task succeeds and passes checks |
| After compilation, code runs and accesses host resources | Confused compilation with an execution sandbox | Execute separately inside an isolated environment |

## 11. Deployment Checklist and References

Before deploying an in-memory compilation service to real users, explicitly verify:

- Input sources are bounded **at byte ingress**, covering both file count and post-decode total size.
- `JavaCompiler` receives server-controlled compilation units and options, with a pinned version and classpath, and annotation processing disabled unless explicitly authorized.
- Every class output is metered **during writes**, with caps on entry count and total bytes; non-standard outputs or failed artifacts are discarded.
- Diagnostics, writer text, response size, and logs each have dedicated caps; error details stay useful without causing unbounded load.
- Timeouts are clearly defined as either **soft wait deadlines** or **hard process terminations**, with status names accurately reflecting which one.
- Workers still running after a timeout are not treated as having freed resources. For untrusted code, workers should live in a process/container with CPU/RAM/disk limits and a kill mechanism.
- The scheduler enforces queue, concurrency, and tenant budgets, and tests cover `SOURCE_LIMIT`, `OUTPUT_LIMIT`, `COMPILATION_ERROR`, `SOFT_TIMEOUT`, and worker failures.
- Compiled bytecode is never executed inside the same host JVM merely because the compiler returned OK; execution requires its own isolation policy.

**JDK 17 Documentation:** [JavaCompiler](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.html), [JavaFileManager and ForwardingJavaFileManager](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/ForwardingJavaFileManager.html), [DiagnosticListener](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/DiagnosticListener.html), [Future.cancel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html), [ExecutorService.shutdownNow](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html), and [Process.waitFor/destroyForcibly](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Process.html).

Practical conclusion: **validate sources before creating the task; gate outputs in the file manager; bound diagnostics and writer text; distinguish waiting on a `Future` timeout from actually stopping the compiler; and use process isolation when hard resource enforcement is required**. These four boundaries keep an in-memory compilation service's failure behavior predictable and prevent a single Java request from overloading the entire host.