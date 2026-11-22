# Controlling Time, Memory, and Write Paths When Providing a Java Compilation Service

## 1. Why Does a Compilation Service Need Resource Limits?

A compilation service typically receives source code or configuration from an HTTP request, queue, or automated tool and runs a Java compiler to produce class files, JARs, diagnostics, or generated sources. A normal job may consume significant CPU, memory, disk space, and temporary files; a buggy or maliciously heavy job can run indefinitely, emit millions of log lines, create files outside its granted directory, or saturate the entire server.

**Lesson objective:** a compilation job must have a defined deadline, resource budget, and write scope; when limits are exceeded, the system must stop and clean up resources while keeping other jobs' data safe.

Three main axes:

1. **Time:** distinguish time spent waiting in the queue, compiler execution time, and artifact processing time; enforce deadlines and timeout handling.
2. **Memory and resources:** cap JVM heap, total process/container memory, CPU, process/thread count, stdout/stderr, and disk quota.
3. **Write paths:** allow the compiler to write only inside the job's own workspace; protect against path traversal, symlinks, archive extraction flaws, and writing files into another user's/job's area.

Design around the **principle of least privilege**: do not grant the compiler direct access to the host filesystem, credentials, Docker socket, network, or shared artifact repository unless strictly necessary. When requests contain untrusted source code, **a separate Java process alone is not a security sandbox**; OS-level isolation, hardened containers, or dedicated virtual machines are needed.

## 2. Threat Model: Source Code, Processors, and Build Tools Have Different Trust Levels

A service may receive several types of input:

| Input | Primary risk | Default strategy |
| --- | --- | --- |
| Plain .java files | Overly large structure, flood of errors and diagnostics, parser/compiler bugs, abnormal filenames | Validate size/count; run javac inside an isolated worker |
| Annotation processor | A processor is **Java code executing at compile time**, able to write files, open network, or loop infinitely | Never load disallowed processors; disable processing when unneeded with -proc:none |
| Compiler plugin or build script | Plugins and Gradle/Maven tasks can execute arbitrary code | Treat as untrusted executable; stronger sandbox than plain compilation |
| User-provided JAR/classpath | May contain processors/plugins, forged classes, or bloated files | Resolve dependencies under control; pin hashes/versions; block paths outside permitted areas |
| ZIP/TAR source upload | Zip Slip, symlinks/hardlinks, decompression bombs, file flood | Cap compressed and uncompressed sizes, check each entry path; do not trust metadata |
| Output name or relative path | ../ traversal, absolute paths, Windows device names, symlink escape | Do not let clients pick absolute paths; create workspace server-side and check canonical paths |

**Key distinction:** Compiling a normal Java class does not mean automatically running that class's main() method. However, annotation processors, compiler plugins, build plugins, and test/generation steps can execute right inside the pipeline. Therefore, the entire compilation process on untrusted source cannot be treated as a harmless data transformation.

**Java SecurityManager is not a security boundary for modern compilation services.** Do not rely on it to block writes or network access from untrusted code or processors. Protect using OS isolation, unprivileged accounts, restricted mounts, and resource limiters.

## 3. Service Architecture Model

~~~text
Client
  |
  v
API: auth, request-size limit, file-count limit, quota
  |
  v
Job queue: maximum queued jobs, deadlines, and concurrency
  |
  v
Isolated worker / sandbox (each job has its own job ID)
  |-- /work/input       read-only
  |-- /work/output      writable, capacity-limited
  |-- /tmp              private temp, capacity-limited
  |-- compiler JDK      controlled image
  |-- CPU/RAM/PID/IO    enforced at OS/container level
  |-- watchdog          timeout -> terminate entire process group
  |
  v
Artifact validation: check files, sizes, paths, names
  |
  v
Publish artifact: store in trusted repository under server-issued name
  |
  v
Cleanup: delete workspace/job sandbox and record metrics
~~~

Avoid letting API handlers run javac synchronously on HTTP request-serving threads whenever possible. Instead, the API accepts the job, validates quotas, and enqueues it; dedicated workers run the compiler. Critical limits apply **immediately upon job admission**, before any runner is created.

Example table of configurable budgets; these are **illustrative numbers** to explain the design, not Java or Docker defaults:

| Budget | Example | Responsible boundary |
| --- | --- | --- |
| Upload request | 2 MiB source, up to 50 files | API / upload validator |
| Queue | 20 queued jobs, max 2 concurrent jobs on a small worker host | Queue + scheduler |
| Compile wall-clock | 10 seconds/job | Watchdog + controller |
| CPU | 1 CPU/job | cgroup/container |
| Total job RAM | 512 MiB | cgroup/container/VM |
| javac heap | -J-Xmx128m | javac's JVM; only a portion of total RAM |
| Process/thread count | 64 PIDs | cgroup/container |
| Artifact/temporary bytes | Output 20 MiB, /tmp 32 MiB | filesystem quota or tmpfs |
| Logs returned to client | 16 KiB retained | Output collector; while still draining the pipe |

Actual values depend on source volume, annotation processing, libraries, JDK, storage speed, trust level, and SLOs. Do not copy this table into production without benchmarking error rates and concurrent load.

## 4. Time Limits: Do Not Confuse Timeout with Kill

### 4.1. Clocks to Track

- **Queue timeout:** jobs waiting too long are cancelled before consuming compilation resources.
- **Compilation wall-clock timeout:** elapsed real time since the compiler starts, including I/O waits and resource contention.
- **CPU time budget:** total CPU time consumed, distinct from wall-clock; a job can use little CPU yet hang on I/O.
- **Artifact processing timeout:** post-compile time to read, package, and upload artifacts.
- **Overall deadline:** caps the total job lifecycle including retries and cleanup.

For example, if a job has a 10-second compile budget yet waited 30 seconds in the queue, the compile timeout alone does not reflect user latency. Similarly, timing out an HTTP request does not mean the javac process stopped — it can continue consuming CPU/RAM in the background.

### 4.2. Java Process API

When running the compiler with ProcessBuilder, Java 17 provides:

- **process.waitFor(timeout, TimeUnit.SECONDS)**: returns false on expiration; this method **does not terminate the process itself**.
- **process.destroy()**: requests termination according to platform semantics.
- **process.destroyForcibly()**: requests forcible termination; returning does not guarantee the process stopped immediately, so you must wait/reap.
- **process.toHandle().descendants()**: can observe child processes, though snapshots are prone to races if the process tree changes.

Do not just call Future.cancel(true) or Thread.interrupt() on a compiler running inside the same JVM expecting safe termination. An annotation processor or plugin can ignore interrupts and exhaust all server memory. For untrusted inputs, run the compiler in a **separate process inside a sandbox**, and upon timeout terminate the **entire process group/container/VM** and wait for confirmed cleanup.

If you only kill the javac PID after a processor/plugin spawned a child process, the child may survive. On Linux, delegate lifecycle to cgroups/containers; on Windows, use a Job Object or an equivalent process-tree management mechanism in the worker infrastructure.

### 4.3. Do Not Let stdout/stderr Hang the Compiler

If the service calls ProcessBuilder and waitFor before draining stdout/stderr, the pipe can fill up. The compiler blocks while writing logs while the parent waits for the compiler to finish: resulting in deadlock. Choose one of two approaches:

1. Read stdout/stderr **concurrently** with the compiler, storing at most N bytes while continuing to drain the rest.
2. Redirect to a file with a quota and appropriate reader; never stream logs unboundedly to memory or disk.

If using redirectErrorStream(true), stderr and stdout share one stream. Trailing diagnostics may be cut off if only keeping a prefix; include a **truncated=true** flag, error codes, and metadata so users know logs were capped. In production, a ring buffer can retain the tail as well, while still enforcing a total log/IO limit to prevent abuse.

## 5. Memory: Heap Is Not Total RAM

**-J-Xmx128m** passes a heap flag to the JVM running the javac launcher. This flag limits the **Java heap**, not the exact total memory footprint: native allocations, metaspace, thread stacks, JIT/code cache, and mapped files also consume memory. A compiler invoked via the Java Compiler API **in the same JVM** shares heap/GC with the service; there is no reliable per-compilation heap quota merely from spawning a new Thread.

Therefore two layers are required:

- **JVM heap:** for example -J-Xmx128m for javac as a separate process; choose after benchmarking real source sets.
- **OS/container memory:** for example 512 MiB for the whole worker job, covering the compiler and children. Distinguish memory hard limits from memory reservations (soft limits).

Upon hitting the memory limit, the runtime/kernel can kill the process, often without reporting a Java OutOfMemoryError as you might expect. The service must classify **OOM / killed by resource limit / compiler diagnostics / timeout / infrastructure error**. A non-zero exit code alone is not enough to conclude a Java syntax error.

A CPU quota (**--cpus**) is not a wall-clock timeout. A compilation consuming less than 1 CPU can still run for minutes; a dedicated watchdog is required. Likewise, limiting thread/PID counts lowers fork-bomb risk yet does not replace memory, disk, or concurrency limits.

## 6. Write Paths: Each Job Owns Only Its Own Workspace

Provision a fixed structure for each job:

~~~text
/work/jobs/job-opaque-id/
├── input/             read-only after upload/extract step
├── classes/           write only .class files from compiler
├── generated/         write only permitted sources/resources
├── temp/              private temp directory
└── result/            staging artifacts before publishing
~~~

The job ID is issued by the server; never use raw usernames, URLs, or archive names in filesystem paths. Workspaces must be created with private permissions and an unprivileged owner, never shared across tenants. With containers, mount input read-only, output writable, and the root filesystem read-only.

### 6.1. Two-Layer Path Validation

**Layer 1 — lexical validation:** reject absolute paths, invalid path characters/forms, and .. components escaping root; resolve + normalize and then verify startsWith(root).

~~~java
import java.nio.file.Path;

public static Path lexicalOutputPath(Path root, String relativeName) {
    Path relative = Path.of(relativeName);
    if (relative.isAbsolute()) {
        throw new IllegalArgumentException("Absolute path rejected");
    }
    Path normalizedRoot = root.toAbsolutePath().normalize();
    Path candidate = normalizedRoot.resolve(relative).normalize();
    if (!candidate.startsWith(normalizedRoot)) {
        throw new IllegalArgumentException("Path traversal rejected");
    }
    return candidate;
}
~~~

**This is only an illustrative method snippet, not a complete safe-writing mechanism.** On Windows, account for drive-relative paths, UNC paths, separators, and reserved device names specific to the service's filesystem. startsWith checks the path tree syntactically and does not prove the final target is safe if the path involves symlinks or junctions.

**Layer 2 — filesystem enforcement:** prevent requesters from creating/modifying symlinks, hardlinks, or parent directories while the service validates and writes; enforce sandbox permissions and mounts. For sensitive operations, use directory-handle-based APIs (such as SecureDirectoryStream when supported by the filesystem, or equivalent OS primitives) to mitigate TOCTOU. For newly created files, use appropriate CREATE_NEW/NOFOLLOW_LINKS semantics and never open any user-supplied path whose ancestors are uncontrolled.

A more pragmatic rule is **never passing user-supplied output paths directly to -d/-s options**. The server creates classes/ and generated/ with fixed names inside the workspace and passes controlled absolute paths to the compiler.

### 6.2. Zip Slip and Archive Bombs

If the client uploads a ZIP/TAR archive:

1. Cap total compressed bytes on upload.
2. Cap total uncompressed bytes, entry count, name length, and directory depth.
3. Validate every entry before creation; reject absolute paths, .. escapes, symlinks, or disallowed hardlinks.
4. Do not trust the entry size in archive metadata as final proof; count the actual decompressed bytes.
5. Extract into a dedicated quota-enforced directory; transition input to read-only only after validation finishes.

For instance, a ZIP containing **../../outside.txt** can write outside the target directory if extracted naively. A tiny compressed archive can expand to huge size. Both issues must be handled before invoking the compiler.

### 6.3. Controlling Where the Compiler Can Write

Javac can write classes via **-d**, generated sources via **-s**, and annotation processors can create resources through Filer. Compilers/plugins/build tools can also use temporary directories, caches, and script-specified folders.

Therefore:

- Determine absolute output directories on the server.
- Do not let users pass arbitrary options directly such as -d, -s, -J..., -Xplugin, -processorpath, or --class-path when the API only supports plain compilation.
- Use an option allowlist and fix classpath and sourcepath; never concatenate args into a shell string.
- Disable annotation processing when unneeded using **-proc:none**; if arbitrary processors must be supported, apply the sandbox for untrusted executable code.
- Limit total bytes, file count, and per-file size of outputs.
- Check symlinks and paths of all artifacts before publishing to shared storage.
- Never return raw absolute host paths or sensitive file listings in diagnostics.

**Note:** -proc:none only stops annotation processing; it does not replace a sandbox if javac has a vulnerability, if the service also runs build/plugin steps, or if users are given uncontrolled compiler options.

## 7. Runnable Java 17 Example: Deadline, Heap, and Log Limit

The example below runs **one javac invocation** on a small Java source generated by the program itself, retains up to 16 KiB of compiler output, and uses a 10-second deadline. It illustrates process management and server-provisioned output paths. **It is not yet a security sandbox**: OS/container memory, CPU, disk quotas, or isolation for untrusted inputs are not configured.

Save file **CompileBoundedDemo.java**:

~~~java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Locale;
import java.util.concurrent.TimeUnit;

public final class CompileBoundedDemo {
    private static final int LOG_LIMIT = 16 * 1024;

    private CompileBoundedDemo() {
    }

    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("compile-demo-");
        Path sourceDir = Files.createDirectories(root.resolve("src"));
        Path outputDir = Files.createDirectories(root.resolve("classes"));
        Path emptyClasspath = Files.createDirectories(root.resolve("empty-cp"));
        Path emptySourcepath =
                Files.createDirectories(root.resolve("empty-sourcepath"));

        Path source = sourceDir.resolve("Hello.java");
        Files.writeString(source, """
                public final class Hello {
                    public static void main(String[] args) {
                        System.out.println("Hello from compiled Java");
                    }
                }
                """, StandardCharsets.UTF_8);

        boolean windows = System.getProperty("os.name")
                .toLowerCase(Locale.ROOT).contains("win");
        Path javac = Path.of(System.getProperty("java.home"), "bin",
                windows ? "javac.exe" : "javac");

        if (!Files.isRegularFile(javac)) {
            throw new IllegalStateException("JDK javac not found: " + javac);
        }

        ProcessBuilder builder = new ProcessBuilder(
                javac.toString(),
                "-J-Xmx128m",
                "-proc:none",
                "--release", "17",
                "-encoding", "UTF-8",
                "-classpath", emptyClasspath.toString(),
                "-sourcepath", emptySourcepath.toString(),
                "-d", outputDir.toString(),
                source.toString());

        builder.directory(root.toFile());
        builder.redirectErrorStream(true);

        Process compiler = builder.start();
        compiler.getOutputStream().close();

        LogDrain drain = new LogDrain(compiler.getInputStream());
        Thread reader = new Thread(drain, "compiler-output");
        reader.setDaemon(true);
        reader.start();

        boolean finished = compiler.waitFor(10, TimeUnit.SECONDS);
        if (!finished) {
            compiler.destroyForcibly();
            if (!compiler.waitFor(2, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Compiler did not terminate");
            }
        }

        reader.join(2000);
        if (reader.isAlive()) {
            throw new IllegalStateException("Compiler output still open");
        }
        if (drain.failure != null) {
            throw drain.failure;
        }

        String status = !finished ? "TIMEOUT"
                : compiler.exitValue() == 0 ? "SUCCESS" : "COMPILE_ERROR";

        System.out.println("status=" + status);
        System.out.println("classPresent=" + Files.isRegularFile(
                outputDir.resolve("Hello.class")));
        System.out.println("logTruncated=" + drain.truncated);

        if (status.equals("COMPILE_ERROR")) {
            System.out.println(drain.text());
        }
    }

    private static final class LogDrain implements Runnable {
        private final InputStream input;
        private final ByteArrayOutputStream buffer =
                new ByteArrayOutputStream();
        private volatile boolean truncated;
        private volatile IOException failure;

        private LogDrain(InputStream input) {
            this.input = input;
        }

        @Override
        public void run() {
            try (InputStream stream = input) {
                byte[] chunk = new byte[4096];
                int n;
                while ((n = stream.read(chunk)) != -1) {
                    int kept = Math.min(n, LOG_LIMIT - buffer.size());
                    if (kept > 0) {
                        buffer.write(chunk, 0, kept);
                    }
                    if (kept < n) {
                        truncated = true;
                    }
                }
            } catch (IOException ex) {
                failure = ex;
            }
        }

        private String text() {
            return buffer.toString(StandardCharsets.UTF_8);
        }
    }
}
~~~

Run on **JDK 17+** from the directory containing the file:

~~~bash
javac --release 17 -encoding UTF-8 CompileBoundedDemo.java
java CompileBoundedDemo
~~~

With a normally working compiler, exact stdout:

~~~text
status=SUCCESS
classPresent=true
logTruncated=false
~~~

**Why these choices matter:**

1. **ProcessBuilder passes an argument list:** avoids a shell, reduces quoting errors, and prevents arbitrary input from becoming a shell command.
2. **Paths from a server-created workspace:** source, empty classpath, empty sourcepath, and output are separated; users do not choose host directory names.
3. **-proc:none:** disables annotation processing for this plain compilation demo.
4. **-J-Xmx128m:** limits javac's JVM heap in the demo; **does not guarantee total RAM stays under 128 MiB**.
5. **waitFor(10, SECONDS):** sets a timeout on the process; **destroyForcibly() + waitFor(...)** handles expiration, though only for the javac PID, not a child process tree.
6. **LogDrain:** reads the pipe in a concurrent thread, retaining up to 16 KiB in memory while draining the rest, preventing deadlocks from a full pipe.
7. **Separate input/output directories:** allows verifying that Hello.class was written to the expected place by the compiler.
8. **Does not invoke java Hello:** the example only compiles and never executes user-submitted code; if the service supports running results, that requires an independent sandbox and execution budget.

Limitations of the demo: the process inherits the caller's environment, the workspace sits in the default temp filesystem, and no OS-level quotas exist. When building for production, move the compiler into a tightly configured worker/container/VM, allowlist environment variables, restrict output I/O, validate artifacts, and clean up the directory when closing the job.

## 8. Enforcing Limits at the OS/Container Layer

Illustrative example on **Docker Engine/Linux** with a managed JDK image, where /work/input and /work/output are pre-mounted from the job workspace:

~~~bash
docker run --rm \
  --network none \
  --read-only \
  --memory 512m \
  --memory-swap 512m \
  --cpus 1 \
  --pids-limit 64 \
  --cap-drop ALL \
  --security-opt no-new-privileges \
  --user 10001:10001 \
  --tmpfs /tmp:rw,nosuid,nodev,size=32m,uid=10001,gid=10001 \
  --mount type=bind,src=/srv/jobs/demo/input,dst=/work/input,readonly \
  --mount type=bind,src=/srv/jobs/demo/output,dst=/work/output \
  --workdir /work \
  example-controlled-jdk:21 \
  javac -J-Xmx128m --release 17 -proc:none -encoding UTF-8 \
    -d /work/output /work/input/Hello.java
~~~

**This is an illustrative operational template**, not a standalone runnable command: it requires a compatible Docker Engine, a vetted image, a /work directory in the image, both host directories created with proper ownership, and a valid Hello.java file. Limit values must be tuned to workload. Options explained:

| Option | Meaning | What it does not solve |
| --- | --- | --- |
| --network none | No external network connection under this network config | Not a mechanism controlling every syscall or proving an absolutely secure sandbox |
| --read-only | Read-only root filesystem | Output/tmpfs mounts remain writable; require separate controls |
| --memory / --memory-swap | Sets hard RAM and swap budgets per kernel support | Does not replace disk output controls |
| --cpus 1 | CPU quota corresponding to roughly 1 CPU | Not a 10-second deadline |
| --pids-limit 64 | Caps processes/threads accounted to the cgroup | Does not replace memory quota |
| --cap-drop ALL, no-new-privileges | Reduces container privileges | Cannot fix flawed mount/host design |
| --user 10001:10001 | Avoids running as root inside the container by default | Must ensure the UID can write valid outputs |
| --tmpfs /tmp:size=32m | Dedicated size-limited temp storage | Does not cap /work/output when it is a bind mount |

**Critically important:** bind-mounting output to a host path can still fill the host disk unless filesystem quotas or byte limits are set. --read-only applies only to the container root filesystem and does not automatically make the output mount read-only. Never mount the Docker daemon socket, host root directory, credentials directories, or a writable shared cache.

Containers are not by default a strong enough boundary for every multi-tenant and malicious-code scenario: consider kernel hardening, seccomp/AppArmor/SELinux, rootless or isolated runtimes, user namespaces, ephemeral VMs, and trust in the compiler image. Verify in practice that the host cgroup/kernel actually supports the configured limits; do not treat flag acceptance as proof that all quotas are actively enforced.

## 9. Safe Artifact Publishing: Checking After the Compiler Finishes

After the compiler reports exit code 0, **do not automatically trust every file in the output**. A processor or build step could create symlinks, oversized files, unrelated files, or abnormal paths. Outputs inside the job workspace remain **untrusted data** until verified.

A safe processing sequence:

1. Confirm the job has not exceeded deadlines/quotas and the worker state is still valid.
2. Enumerate outputs without following symlinks; reject symlinks, hardlinks if policy requires, special files, and paths outside root.
3. Cap file counts, total bytes, and individual file sizes; inspect directory depth and filenames too.
4. Accept only artifact types declared by the API, such as .class files or JARs created by a trusted packaging step.
5. Copy or stream artifacts into staging **in a trusted area** using a server-issued ID; never use raw output names as storage keys outside a namespace.
6. If multiple files must be published as one result, use atomic commits/renames or transactions at the storage layer.
7. Clean up the sandbox via the controller whether the job succeeds, fails, times out, is cancelled, or the node fails.

If child processes remain alive, copying output files may read changing data. Confirm that the worker container/process group has stopped and the output filesystem is quiescent before publishing. Never let clients download directly from the job's writable working directory while the compiler is running.

**Do not confuse cleanup with ownership:** delete directories by job ID only after the root path is server-validated; never construct an rm -rf command from client-provided strings. The worker manages only its own job paths, and the controller reaps orphaned jobs after crashes/restarts.

## 10. Error Statuses That Must Be Distinguished

| Service status | Signal | Response |
| --- | --- | --- |
| SUCCESS | Compiler exit 0, artifacts verified | Publish valid files and metadata |
| COMPILATION_ERROR | Non-zero compiler exit with valid Java diagnostics | Return bounded diagnostics and source info |
| TIMEOUT | Deadline expired, process group stopped | Stop/purge, record duration, do not publish partial files |
| MEMORY_LIMIT | Container/cgroup hit OOM or memory limit | Mark as resource failure, do not interpret as syntax error |
| OUTPUT_LIMIT | Exceeded total bytes/file count/log policy | Stop or withhold publish per contract; clean up |
| INVALID_PATH | Input/output path violated scope | Reject job/entry, record appropriate audit log |
| INFRA_FAILURE | Missing compiler binary, broken file manager, container start failure | Do not blame user Java source |
| CANCELLED | Explicitly cancelled by user or policy | Stop worker and clean up, do not mark as timeout |
| QUEUE_EXPIRED | Job expired before execution | Do not spawn compiler process |

Define clear precedence when a job violates multiple budgets simultaneously: the controller records the primary observed cause and supporting telemetry, avoiding definitive claims from exit code 137 or incomplete logs alone. Exit codes depend on OS and runtime; OOM/cgroup and signal details are needed for accurate classification.

For an HTTP API, the statuses above can map to stable application error codes. Not every compilation error is an HTTP 500: invalid syntax in source is a normal request-processing outcome with a bounded diagnostic list.

## 11. Testing Limits with Controlled Scenarios

| Case | What to create or simulate | Assertion |
| --- | --- | --- |
| Valid | A small Hello.java file | Success, .class in job output, no unexpected files created |
| Timeout | Compiler/helper intentionally waits past deadline in test sandbox | Status TIMEOUT, PID/container dead, no public artifacts left |
| Heap too small | Heavy enough source set in isolated environment | Reports appropriate resource failure; host unaffected |
| Memory exceeds cgroup | Worker exceeds RAM limit | Job blocked/killed, controller classifies and cleans up |
| Log flood | Helper emits output exceeding 16 KiB | No deadlock; collector memory bounded; truncated true |
| Disk full | Output/temp reaches quota | Controlled stop/failure; no writes elsewhere |
| Traversal | ../outside.class or absolute path in request | Rejected before compile; no files outside root |
| Symlink escape | Parent/output symlink pointing outside | Not followed; no writes outside |
| ZIP bomb/Zip Slip | Archive with many entries or ../ paths | Rejected during extract; compiler never launched |
| Two concurrent jobs | Two tenants create same Hello.java name | Isolated workspaces, no overwrite |
| Surviving child process | Plugin/helper spawns child then times out | Entire group/container stopped |
| Cancel/race | Cancel right as job prepares to publish | Not published after cancel, idempotent cleanup |

Run quota-breaking tests in an actively controlled, quota-limited staging environment. To test deadlines, use a **test helper process** that intentionally sleeps or blocks rather than assuming a real compiler will hang: the test must reliably establish start conditions and threshold timing. Also verify cleanup after sudden worker process death.

Metrics to record: queue_wait_ms, compile_wall_ms, max_rss_bytes or measurable memory peak, cpu_time, output_bytes, log_bytes_dropped, process_count_peak, exit_status, cancellation_reason, and job_id. Do not log full source code, environment variables, or credentials without a clear need.

## 12. Common Mistakes

**Setting a timeout only on the HTTP request.** The HTTP request can end while javac keeps running. Deadlines must bind to the job lifecycle and sandbox.

**Using only -Xmx.** The JVM heap excludes native memory and child processes. Add hard limits at the OS/container level.

**Using only --cpus and expecting the process to terminate.** CPU quota slows CPU consumption; it does not cut off hang duration.

**Reading logs only after waitFor.** Pipes can fill and deadlock parent and child. Use concurrent readers and bound memory/files.

**Checking paths with string startsWith.** For example, /work/out2 starts with the string /work/out, yet is not inside directory /work/out. Use Path.resolve/normalize/startsWith by path components, while addressing symlinks and TOCTOU via filesystem boundaries.

**Believing compiler output is always safe.** Processors/plugins can create unexpected files. Inspect artifacts before publishing.

**Mounting host output without quotas.** A read-only container root does not prevent a writable bind mount from filling the host disk.

**Letting users choose compiler flags arbitrarily.** Users can redirect output paths, load processors/plugins, or reference the filesystem. Plain compile APIs need allowlists; full build features require sandboxing equivalent to running untrusted code.

**Running compilation inside the Java web server JVM.** GC pauses, OOM, thread leaks, or runaway processors can crash the API for all tenants. Separate processes and job sandboxes provide concrete stop/cleanup boundaries.

**Killing only the parent PID.** Child processes and inherited file descriptors can survive; manage the entire process group/container.

## 13. Pre-Production Design Checklist

- [ ] Threat model distinguishes plain Java source, annotation processors, compiler plugins, and build scripts.
- [ ] API enforces upload size, file count, paths, dependencies, compile flags, and queue quotas.
- [ ] Each job gets its own worker/workspace with a server-issued ID and no shared output directory.
- [ ] Overall deadline, queue deadline, compile timeout, and cancellation control the entire process tree.
- [ ] Heap, total RAM, CPU, PIDs, stdout/stderr, temp, and output bytes have separate budgets.
- [ ] Input is read-only; output and temp are writable only inside the restricted sandbox.
- [ ] Source/archive paths are checked for traversal, symlinks, hardlinks, and excessive decompression.
- [ ] Annotation processing is disabled when unneeded; arbitrary compiler flags or classpaths outside policy are rejected.
- [ ] No network, host mounts, credentials, or Docker socket are granted to untrusted compilation.
- [ ] Artifacts are never published before the worker stops and paths and sizes are verified.
- [ ] Cleanup handles success, compile errors, timeouts, OOM, cancellations, and worker crashes.
- [ ] Metrics/audit logs distinguish input errors from resource/infrastructure failures without leaking secrets.
- [ ] Tests verify path escapes, log floods, disk quotas, concurrent isolation, and surviving child processes.

## 14. References

- [Java SE 17 — Process](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Process.html): waitFor, destroyForcibly, descendants, and subprocess management.
- [Java SE 17 — ProcessBuilder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ProcessBuilder.html): creating processes, passing arguments, directory, environment, and streams.
- [Java SE 17 — javac options](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): -J, -proc:none, -d, -s, classpath, and options.
- [Java SE 17 — Files and Path](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): filesystem operations, symbolic links, and file access.
- [Docker — Resource constraints](https://docs.docker.com/engine/containers/resource_constraints/): memory/CPU constraints and OS limits.
- [Docker — docker container run](https://docs.docker.com/reference/cli/docker/container/run/): --read-only, --pids-limit, --network, --tmpfs, mounts, and security options.

**Core message:** timeouts and -Xmx in Java are only a small part of the picture. A trustworthy compilation service needs job orchestration, OS isolation, RAM/CPU/disk quotas, write-path controls, and artifact validation as one unified pipeline, especially when inputs can load executable processors or plugins.