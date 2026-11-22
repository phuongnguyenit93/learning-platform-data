# Isolating Each Scenario with a Fresh Loader or JVM Process

When verifying **Java class loading** mechanisms, running multiple scenarios consecutively within the same `ClassLoader` or the same JVM process can produce **skewed results due to leftover state**. A loaded class is cached by the loader, `static` fields have already been initialized, singletons already exist, `ServiceLoader` has cached providers, the JVM has already linked the class, or class initialization has failed previously. Subsequent runs may no longer truly start from the same starting point as the first run.

To compare fairly and reproduce bugs, there are two main levels of isolation:

1. **Create a new class loader for each scenario:** separates the namespace and state associated with **the classes actually defined by the new loader**. Fast, suitable for testing parent-first/child-first, class identity, `ClassCastException`, plugin `static` initialization, SPI, and hot redeploy.
2. **Create a new JVM process for each scenario:** creates an independent Java runtime, typically isolating the system class loader, heap, static state, JIT, JVM flags, loaded classes, internal thread pools, and many process-level global states. Incurs higher startup overhead, suitable for testing how the JVM is launched, initialization failure, native libraries, `System` properties, classpath/module path, GC/Metaspace, and experiments that could hang or corrupt the process.

**Do not equate these two levels.** A new loader **does not create a new JVM**; two new JVMs **do not guarantee isolation of external resources** such as files, databases, Redis, network services, ports, or user credentials. The isolation level must be chosen based on **the state that actually needs to be reset**.

This Knowledge article presents how to design independent experiments, explains technical boundaries, provides **a Java 17 example compiled and executed for verification** with two `URLClassLoader` instances and two child JVMs, and then guides how to organize a test matrix, loader/process lifecycles, expected results, and pitfalls that easily cause "false test passes".

## 1. Why Can the Same JVM Skew Results?

A JVM does not reload the same class in the **same defining class loader** every time code calls `loadClass`. If the first call already created `Class<?>`, subsequent calls return the same definition for the same binary name according to the standard caching/loading mechanism.

~~~text
Current JVM
   |
   +-- Loader A
   |     +-- plugin.Counter   → Class #A
   |     +-- static count = 2
   |
   +-- Loader B
   |     +-- plugin.Counter   → Class #B
   |     +-- static count = 1
   |
   +-- System/Application loader
         +-- HostRegistry    → host's global cache
         +-- library classes shared via delegation
~~~

In the diagram:

- `Class #A` and `Class #B` are **two different JVM classes** because their defining loaders differ, even though their binary names are identical.
- `static count` belongs to **the class definition**, so it can be separated between A/B.
- `HostRegistry` defined by the parent/system loader remains **a single shared instance** within the same process; A/B can both modify its static state.
- The JVM may continue retaining the old class/loader if references remain, even after `URLClassLoader.close()` has been called.

### States That Cause Tests to Interfere with One Another

| State | Does a new loader reset it automatically? | Does a new JVM isolate it? |
| --- | --- | --- |
| `static` fields belonging to a class defined by the plugin loader | **Yes**, if each loader actually defines its own copy of the class | **Yes**, across processes |
| Class identity of `pkg.Plugin` defined by the plugin | **Yes**, between two defining loaders | **Yes**, across processes; `Class<?>` cannot be compared directly across processes |
| `static` fields of a class defined by the system/parent loader | **No**; shares the parent `Class<?>` | **Yes**, in the new process |
| `System.setProperty` / process-wide Java system properties | **No**, same properties object in the current JVM | **Yes**, at the JVM instance level; startup args can pass the same initial values |
| Host singleton, cache, `ThreadLocal` on long-lived workers | **No by default** | **Yes**, in a separate child process upon termination, if not connected to external resources |
| `ServiceLoader` object/cache held by the host | **No**; must create a new object, use the right loader, and clear references | **Yes**, in the child process, except for service data outside the JVM |
| Class initialization failure of the same class definition | **No**, not reset by calling again in the old loader | **Yes**, with a new JVM; a new loader can also have a new class definition |
| `Thread.currentThread().getContextClassLoader()` | **Does not** automatically change to match the loader being created | New worker/thread has a new context according to how the runtime initializes |
| JVM flags, module path at launch, default charset/runtime image | **No** | **Can be changed** via a new launch command |
| JIT code cache, GC state, Metaspace in the runtime | **No** | **Yes**, when running a different JVM process |
| File, database, network, OS service | **No** | **Not automatically**; requires separate sandbox/fixtures/resource names |

The "Yes" cells in the new JVM column indicate **process-level isolation**; they do not mean the new JVM forgets written files, DB rows, network writes, logs, or shared kernel state.

## 2. A New Loader Only Isolates When It Defines the Right Class Under Test

The JVM identifies a runtime type by **(binary name, defining loader)**. Two independent `URLClassLoader` instances can separately define `lab.Counter`, but if parent-first returns a class that already exists from the parent, then `new URLClassLoader(...)` does not prove a new type exists. Each scenario needs to verify `type.getClassLoader()` and `typeA == typeB`. The duplicate-JAR fixture and the previous delegation article show how to choose the right defining loader.

## 3. Resettable Scope of Static State

Successful initialization occurs once per runtime class; an erroneous class is also not automatically retried by the JVM within the same defining loader. When a new loader **actually defines** a new `lab.Counter`, its static fields have their own state, whereas singletons/static state belonging to the parent loader and process-level resources can still be shared. Therefore, the experiment below compares **two fresh plugin loaders** with **two new JVM processes** to distinguish type-level isolation from process-level isolation.

## 4. Java 17 Example: Two Class Loaders and Two Independent JVM Processes

The example cleanly separates **the plugin's class** from **the host classpath**. `lab.Counter` is compiled only into `plugin-classes`, while the host `ScenarioIsolationDemo` runs in the current directory. The two `URLClassLoader` instances share the same bytecode source URL yet **separately define** `lab.Counter`, because the parent is the platform loader and does not find `lab.Counter` in the standard runtime.

Then the host uses `ProcessBuilder` to run `lab.Counter.main` in **two new JVMs**. Each child JVM gets a new `Counter` and an initial `static count` of 0.

### Directory Structure

~~~text
isolation-demo/
├── ScenarioIsolationDemo.java
├── src/
│   └── lab/
│       └── Counter.java
└── plugin-classes/          (javac output directory)
    └── lab/
        └── Counter.class
~~~

### File 1: src/lab/Counter.java

~~~java
package lab;

public final class Counter {
    private static int count;

    public static int next() {
        return ++count;
    }

    public static void main(String[] args) {
        System.out.println(next());
    }
}
~~~

`count` is a `static` field attached to **the `lab.Counter` class definition**. `main` allows running the same class as the entry point of a child JVM, while `next` allows the host to invoke it via reflection from the Classes defined by the child loaders.

### File 2: ScenarioIsolationDemo.java

~~~java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public final class ScenarioIsolationDemo {
    private static int next(ClassLoader loader) throws Exception {
        Class<?> type = loader.loadClass("lab.Counter");
        return (int) type.getMethod("next").invoke(null);
    }

    private static String runFreshJvm(Path classes) throws Exception {
        String executable = System.getProperty("os.name").toLowerCase()
                .contains("win") ? "java.exe" : "java";

        String java = Path.of(System.getProperty("java.home"),
                "bin", executable).toString();

        Process process = new ProcessBuilder(java, "-cp",
                classes.toString(), "lab.Counter")
                .redirectErrorStream(true)
                .start();

        String output = new String(
                process.getInputStream().readAllBytes(),
                StandardCharsets.UTF_8).trim();

        int exit = process.waitFor();
        if (exit != 0) {
            throw new IllegalStateException(
                    "Child JVM exit=" + exit + ": " + output);
        }
        return output;
    }

    public static void main(String[] args) throws Exception {
        Path classes = Path.of("plugin-classes")
                .toAbsolutePath().normalize();

        if (!Files.isRegularFile(classes.resolve("lab/Counter.class"))) {
            throw new IllegalStateException("Compile Counter first");
        }

        URL[] urls = { classes.toUri().toURL() };
        ClassLoader parent = ClassLoader.getPlatformClassLoader();

        try (URLClassLoader a = new URLClassLoader(urls, parent);
             URLClassLoader b = new URLClassLoader(urls, parent)) {

            Class<?> fromA = a.loadClass("lab.Counter");
            Class<?> fromB = b.loadClass("lab.Counter");

            System.out.println("Same Class in A: "
                    + (fromA == a.loadClass("lab.Counter")));
            System.out.println("A next: " + next(a));
            System.out.println("A next again: " + next(a));
            System.out.println("B next: " + next(b));
            System.out.println("Class A equals B: " + (fromA == fromB));
            System.out.println("A loader owns class: "
                    + (fromA.getClassLoader() == a));
            System.out.println("B loader owns class: "
                    + (fromB.getClassLoader() == b));
        }

        System.out.println("JVM run 1: " + runFreshJvm(classes));
        System.out.println("JVM run 2: " + runFreshJvm(classes));
    }
}
~~~

### Build and Run on JDK 17+

Using Bash/Linux/macOS from the `isolation-demo` directory:

~~~bash
mkdir -p plugin-classes
javac --release 17 -d plugin-classes src/lab/Counter.java
javac --release 17 ScenarioIsolationDemo.java
java ScenarioIsolationDemo
~~~

For Windows PowerShell, replace the directory-creation command:

~~~powershell
New-Item -ItemType Directory -Force plugin-classes | Out-Null
javac --release 17 -d plugin-classes src/lab/Counter.java
javac --release 17 ScenarioIsolationDemo.java
java ScenarioIsolationDemo
~~~

**Exact stdout** when the project/files are created exactly as above:

~~~text
Same Class in A: true
A next: 1
A next again: 2
B next: 1
Class A equals B: false
A loader owns class: true
B loader owns class: true
JVM run 1: 1
JVM run 2: 1
~~~

This program was **compiled with `javac --release 17` and run on OpenJDK**, producing the exact full output above.

### Detailed Explanation

1. Both `a` and `b` have URLs pointing to `plugin-classes`, yet they are **two separate URLClassLoader objects** and the `platform` parent does not contain `lab.Counter`.
2. Calling `a.loadClass("lab.Counter")` again still returns `fromA` itself, so the first line is `true`.
3. `next(a)` executes the static method of Class #A the first time and the next time: results are **1**, then **2**.
4. `next(b)` uses Class #B with its own static state, producing **1**.
5. `fromA == fromB` is `false`; the name is the same, but the defining loaders differ.
6. Both `getClassLoader() == a/b` checks evaluate to `true`: proof that the class was defined in the requested location rather than being taken over by the parent system loader.
7. `try-with-resources` calls `URLClassLoader.close()`. It closes the loader's resources; it **does not guarantee immediate class unloading/GC**. For demonstration purposes, closing does not affect the printed output.
8. `ProcessBuilder` locates the Java executable inside `java.home/bin` of the current runtime, using `java.exe` on Windows or `java` on Linux/macOS.
9. Each `ProcessBuilder.start()` spawns **a separate OS process/JVM** with the classpath pointing only to `plugin-classes`, and then invokes `lab.Counter.main`. The child process's static count starts at 0, so each run prints **1**.
10. The host reads child output as UTF-8, waits for exit, and checks the exit code. `redirectErrorStream(true)` merges stderr into stdout to avoid hanging while reading another unconsumed pipe; in a successful run, the child prints only an integer.

**Experiment limitation:** The `Counter` class has no dependencies outside the Java runtime, so `getPlatformClassLoader()` is an appropriate parent. If a plugin needs to call host API interfaces, the platform loader cannot simply be passed as the parent by default: a **shared API loader** is required and proper API identity must be ensured.

### How Would the Test Fail If the Classpath Were Arranged Improperly?

Suppose you compile `Counter.java` into the host directory `.` itself or put `plugin-classes` on the host classpath and then use:

~~~java
new URLClassLoader(urls);
~~~

This is a **fragment** whose default parent is the application/system loader. Parent-first delegation can find `lab.Counter` and return the same parent Class for both loaders. In that case:

~~~text
Class A equals B: true
B next: 3  (if A already called next twice on the same parent Class)
~~~

The output here **illustrates a conditional misconfiguration scenario**, not the result of the reference demo. Do not fix this by forcing child-first across all packages: for shared APIs, duplicating classes typically causes `ClassCastException`. Fix **the test packaging/classpath and target-specific delegation policy**.

## 5. When Is a New Loader Sufficient?

A new loader is suitable when the quantity being measured is tied directly to **the plugin's own class definition**:

- Two Classes with the same binary name and different defining loaders.
- Static fields/initializers of a class defined by the new loader.
- `ClassCastException` when an object from loader A is cast to the corresponding Class from loader B.
- Parent-first/child-first lookup and `ClassNotFoundException`/`LinkageError` per namespace.
- SPI/provider discovery within a specific custom loader or module layer.
- Reloading a plugin implementation while the host/API contract remains stable.
- Verifying the `URLClassLoader.close()` lifecycle, weak references, and class unloading after releasing references.

### However, a New Loader Does Not Reset Parent State

Consider an example test with a `HostMetrics` class in the **application loader**:

~~~java
public final class HostMetrics {
    public static int count;
}
~~~

This is a **fragment** (without a `package` or its own file). Even though plugins A and B belong to different loaders, if both delegate `HostMetrics` to the parent, they will use **the same `HostMetrics.count` field**. A new loader does not reset caches, singletons, logger registries, or `ThreadLocal` state of parent classes.

It is necessary to determine:

~~~text
State to reset?
   |
   +-- in a child-defined class? → a new child loader may suffice
   |
   +-- in a parent/JDK-defined class? → explicit reset or fork a JVM
   |
   +-- outside the process (file/DB/network)? → separate fixtures, cleanup outside the JVM
~~~

With **dynamic module layers**, each layer can create new loaders via `defineModulesWithOneLoader`/`defineModulesWithManyLoaders`, yet parent modules remain shared; do not equate a "new layer" with a "new JVM". `ModuleLayer.boot()` is the current boot layer and is not recreated when adding a child layer.

## 6. When Should You Fork a New JVM?

**A new JVM process** is the stronger choice for verification tests that may leave behind hard-to-reset state or leave the JVM no longer in a clean state:

| Test objective | Why forking a JVM is valuable |
| --- | --- |
| Static state in **system/JDK classes** | Has its own runtime, system/application loader, and heap. |
| JVM/class initialization errors without wanting to retry the same `Class<?>` | A new process recreates the class loading/initialization timeline. |
| `System.setProperty`, locale, default config, and property initialization | Has an independent set of startup properties; values must be explicitly passed via command-line arguments. |
| `-Xmx`, `-XX:*`, `--module-path`, `--add-opens`, `--add-exports` | Many startup options cannot be changed mid-flight within the same process. |
| GC/Metaspace/JFR or class unloading benchmark | Each run has its own JVM state and allocation/GC history. |
| Deadlock or a test causing `System.exit`, crash, or native code | Does not kill/hang the JVM running other tests; the supervisor can terminate the child. |
| Testing ClassLoader+JNI native library conflicts | Native library load scope has its own rules; a new process separates the native address space. |
| Guaranteeing startup/classpath/module resolution order | Each child is launched with a fresh classpath and module graph from the start. |

**Drawbacks:** Startup time, CPU, and RAM increase; you must manage command-line flags, environment, stdin/stdout/stderr, timeouts, exit codes, process tree cleanup, and file artifacts. A child JVM running under the same OS user/privileges as the parent **is not automatically a security sandbox**. To run genuinely untrusted plugins, combine process isolation with an OS account, sandbox/container, network policy, filesystem permissions, and secrets boundaries.

### How Does ProcessBuilder Differ from ClassLoader?

`new URLClassLoader(...)` creates an object **inside the current JVM**. `new ProcessBuilder(...).start()` spawns a new process. The child process does not directly share object addresses, `Class<?>`, singletons, or `static` fields with the parent; communication requires IPC/files/sockets or another protocol.

~~~text
Host JVM                               Child JVM
  separate heap / Class objects           separate heap / Class objects
  system loader / static state            system loader / static state
  URLClassLoader A                        plugin.Counter class
  URLClassLoader B                        static count = 1
      |                                          |
      +------------- ProcessBuilder ------------+
                             |
                        stdout / exit code
~~~

Across JVMs, you cannot write `hostObject == childObject` in the sense of a Java reference (the two objects do not reside on the same heap). When results need to be exchanged, serialize the data or pass strings/JSON/protobuf over IPC and check the status.

## 7. Managing ProcessBuilder So Tests Do Not Hang

The complete example in Section 4 takes a simple approach because the child is very small and always exits. For tests that might deadlock, start a server, or run for a long time, **timeouts and cleanup** are necessary.

Sample fragment (assuming `Process process` has already started):

~~~java
boolean finished = process.waitFor(
        10, java.util.concurrent.TimeUnit.SECONDS);

if (!finished) {
    process.destroyForcibly();
    process.waitFor();
    throw new IllegalStateException("Child JVM timeout");
}

int exitCode = process.exitValue();
if (exitCode != 0) {
    throw new IllegalStateException("Child JVM failed: " + exitCode);
}
~~~

This is a **fragment**, not a standalone program. When using it in a real application:

- **Read/redirect stdout and stderr** to prevent the child from blocking due to a full pipe buffer. If the child produces large output, use a thread to read the stream concurrently or redirect to a file; `readAllBytes()` holds the entire output in memory and should not be used for unbounded logs.
- **Timeouts** must account for cases where the child hangs due to a deadlock or waiting on I/O. If you call `readAllBytes()` before applying a timeout, the read itself could **wait for EOF forever**. For a child that may hang, design asynchronous reading or file redirection and proactively wait with a timeout.
- **Clean up process descendants** when the child spawns grandchildren; `destroyForcibly()` on a Process does not guarantee terminating all child/grandchild processes on every OS.
- **Pass only the necessary environment/working directory** to avoid inheriting secrets or environment variables that might unexpectedly alter runtime behavior. `ProcessBuilder.environment()` allows configuring the child process's environment.
- **Capture the exit code and stderr**; do not treat "stdout contains the expected line" as a PASS if the process ultimately exits with an error.
- **Do not depend on absolute PIDs**: PIDs differ across runs and can be reused; they are not logical identifiers for a scenario.

### A Failure Scenario That Can Break Subsequent Tests

If a test runs:

~~~java
System.setProperty("demo.mode", "broken");
~~~

This is a **fragment** running inside the same JVM; the property persists for other tests unless restored/reset. A new loader **does not replace** the process-wide `System.getProperties()`. A newly forked JVM has its own properties; however, command-line `-Ddemo.mode=...` and environment variables can still produce identical state if the runner passes the same configuration.

If you want independent tests without forking, use `try/finally` to save and restore the original values for properties and global hooks **only when you can guarantee no other thread is concurrently modifying that state**. For parallel test suites, global resets can race; forking a JVM is usually more reliable.

## 8. Distinguishing Between "Creating a New ClassLoader" and "Creating a New ModuleLayer"

Since Java 9, named modules have **module layers** and class loader mappings. A module loader can be created when:

~~~java
ModuleLayer layer = ModuleLayer.boot()
        .defineModulesWithOneLoader(configuration, parentLoader);
~~~

This is a **fragment**; `configuration` must be a valid resolved `Configuration` and `parentLoader` must be appropriate—it is not yet a standalone program. `defineModulesWithOneLoader` creates a new loader for the modules of the new layer, using the passed-in loader as the parent according to the API.

However:

- The parent layer/loader and runtime modules remain shared according to the configuration.
- `ModuleLayer.boot()` does not start a new JVM and is not recreated for each dynamic layer.
- Two separate new layers can define the same binary name using different loaders, but that **does not make their objects the same type**.
- Module readability, `exports`, `opens`, `uses`, and `provides` still affect behavior. Loader isolation is only part of module isolation.
- A layer has no `close()`; reclamation depends on the reachability of the layer, Class, loader, threads, and other references.

In module/plugin tests, if you are measuring **ModuleLayer resolution**, make sure the parent configuration does not inadvertently contain the target module. If you want to measure the full **startup module graph**, run a new child JVM with the corresponding `--module-path`/`-m`.

## 9. Preventing Framework State from Leaking Between Two Scenarios

`ServiceLoader` has its own provider cache, and `load(SPI)` APIs can use the **Thread Context ClassLoader**. If scenario A changes the TCCL or retains caches/listeners of the old plugin, the new loader in scenario B can still be affected. Upon completion, restore the TCCL in `finally`, unregister registries/listeners, and clear caches referencing the plugin. The resource/SPI and lifecycle articles in this chapter have dedicated tests for these reference paths.

## 10. Closing a Loader Does Not Mean Classes Are Unloaded

`URLClassLoader.close()` closes the class/resource lookup paths managed by that loader, but it does not automatically remove loaded `Class<?>` objects or clear all strong references. When an isolation test passes, it only proves that the observed state matches the scenario; it is not enough to confirm that the old loader has been garbage-collected. The article **Verifying Loader Closing Lifecycle, Plugin Shutdown, and Reference Release** provides shutdown criteria, TCCL cleanup, and how to observe unloading using weak references/heap tooling without assuming deterministic GC.

## 11. Building a Verification Matrix and PASS Criteria

A good test suite must define **the state to reset, loader ownership, and PASS observations** before running.

| Scenario | Isolation level to choose | Key assertion |
| --- | --- | --- |
| Same-loader cache | Same loader within a single test | `a.loadClass(name) == a.loadClass(name)` |
| Plugin static state | Two new loaders, class owned only by the child | A: 1→2; B: 1; `ClassA != ClassB` |
| Duplicate API class | Two defining loaders, or shared-parent control | Compare `Class<?> ==`, `isInstance`, and expected cast/error |
| Parent-first vs child-first | Custom-configured loader, fixed sources | Class is defined in the expected loader |
| Plugin initialization failure | New defining loader for each scenario | Failure occurs independently on the new definition |
| Global `System` property / host singleton | New JVM or synchronized reset | Property/singleton baseline is identical on every run |
| Native library/`System.exit`/crash | New child JVM/process | Exit code, timeout, logs, without killing the test runner |
| GC/Metaspace/class unloading | New JVM for independent measurement runs | JVM flags, workload, GC logs, JFR, GC count/loader counts |
| Plugin hot redeploy | New loader/layer per deploy cycle | New type identity, resources/old refs cleaned up |
| Full startup module path | Fork with `--module-path`/`-m` | Named modules/resolution per launch args |
| File/DB mutation | Process + separate test resource/fixture | No writes to shared data, cleanup after test |

If a test needs to **compare performance**, you must also control warm-up/JIT compilation, GC, CPU contention, and the environment. A new JVM helps reduce noise from prior warm-up, but **does not automatically give two benchmarks identical conditions**. For serious benchmarking, use an appropriate harness such as JMH, measure multiple forks/iterations, and report error margins.

### Suite Organization Pseudocode

~~~text
for each scenario:
    decide isolation policy:
        LOADER:
            allocate distinct loader, verify defining loader identity
            execute assertions
            cleanup tasks/caches/TCCL/resources
        JVM:
            spawn java process with explicit args, env, classpath/module path
            capture stdout/stderr, enforce timeout, read exit status
            cleanup process tree and external fixtures
    record test evidence and repeatability
~~~

This is **pseudocode**, not a specific test framework. Both isolation levels should be accompanied by cleanup and assertions on **the actual state**, rather than merely checking "no exception".

## 12. Common Testing Mistakes

**Mistake 1 — "new loader guarantees new class".** False. Parent-first delegation can return a class defined by the parent. Always check `type.getClassLoader()` and `Class<?> ==`.

**Mistake 2 — "new loader resets all static fields".** False. Only classes defined by the new loader have their own static state. Static state in parent/JDK classes remains shared.

**Mistake 3 — "ClassLoader.close() makes the JVM forget the class immediately".** False. Closing does not force class unloading; other strong references still retain the class/loader.

**Mistake 4 — "changing TCCL makes every loadClass use it".** False. Only APIs that actively query the context loader (certain ServiceLoader/resource lookups) are affected. `Class.forName(name, true, explicitLoader)` uses the explicitly passed loader.

**Mistake 5 — "reload() on ServiceLoader resets the loader".** False. `reload()` clears the provider cache of that ServiceLoader object; it does not create a new loader or reset class initialization.

**Mistake 6 — "running tests in a different order and passing is enough".** Not enough. If the outcome depends on order, there is an undeclared leak or shared state. Use a fresh loader/fork and control fixtures.

**Mistake 7 — "a new JVM completely cleans everything".** False. Files/databases/networks/external services, system time, environment, or shared temp directories may still contain data from a previous run.

**Mistake 8 — "calling ProcessBuilder.start without reading stderr is fine".** It can hang when the pipe fills up; you must drain/redirect stdout/stderr and manage exit status/timeouts.

**Mistake 9 — "forking a process equals a sandbox".** False. A child Java process runs under the process's OS user/permissions unless changed; OS/container-level isolation is needed for untrusted code.

**Mistake 10 — "using System.gc() to reset the JVM between tests".** False. GC does not reset singletons/parent classes/system properties, does not guarantee class unloading, and does not make the JVM equivalent to a new process.

**Mistake 11 — "ClassNotFoundException is the same result in every loader".** Incorrect: source classpath, parent delegation, module graph, and dynamic URLs can differ. You must specify which class loader was queried and the actual lookup path.

**Mistake 12 — "the same class name is enough to cast safely".** False. The defining loader participates in identity. If two loaders both define an API interface, `ClassCastException`/`ServiceConfigurationError` can occur; place shared APIs in the parent.

## 13. Debugging Guide When Two Scenarios Affect Each Other

When test A passes on its own, yet fails when run after test B:

1. **Print the defining loader:** `type.getClassLoader()`, class name, and module. Determine whether A and B actually use different Classes.
2. **Check parent delegation:** Is the ClassFile already present on the system classpath? Are shared APIs and implementations mixed together?
3. **Print static state before and after:** Which classes are defined by the parent? Do host singletons/caches need cleanup?
4. **Check TCCL directly on the worker:** The submitter and worker do not match by default.
5. **Inspect `ServiceLoader`/SPI provider caches:** Are they holding onto objects from an earlier scenario?
6. **Inspect live threads:** Did worker/task/callback/plugin threads terminate? Have ThreadLocal and TCCL been restored?
7. **Clean up files, databases, and system properties:** If forking still fails, look toward state outside the JVM.
8. **Run an independent fork:** If the error disappears only when forked, look for process-wide state or shared runtime state such as static host caches, JNI, or JVM startup options.
9. **Capture a heap dump/JFR when needed:** If the old loader remains reachable after undeploy, trace `Path To GC Roots` from caches/threads/listeners instead of relying solely on `close()`.
10. **Write a deterministic regression test:** Set up full preconditions, isolate scenarios, assert results, and clean up according to the lifecycle.

A useful diagnostic fragment:

~~~java
Class<?> type = loader.loadClass("lab.Counter");
System.out.println("Name: " + type.getName());
System.out.println("Defining loader: " + type.getClassLoader());
System.out.println("Module: " + type.getModule());
System.out.println("TCCL: "
        + Thread.currentThread().getContextClassLoader());
~~~

This is a **fragment**, requiring a `loader` variable. The loader/module/TCCL lines depend on the environment, so **no fixed stdout is attached** to this fragment. You can use `Class<?> ==` instead of comparing only name strings.

## 14. Knowledge Self-Check

**Question 1.** Calling `new URLClassLoader(urls)` twice returns `String.class` in both cases. Does that mean the `String` class was defined separately by each loader?

**Answer:** No. `String` is a core platform type defined by the bootstrap loader; parent delegation returns the same definition.

**Question 2.** Given two separate loaders A and B, `lab.Counter` is only on the parent's application classpath. Can `A.loadClass("lab.Counter") == B.loadClass("lab.Counter")` evaluate to `true`?

**Answer:** Yes. With parent-first delegation, both can use the same parent Class. To test child isolation, you must ensure the target class is not intercepted by the parent and verify the defining loader.

**Question 3.** Why can the static counter in A be 2 while in B it is 1?

**Answer:** Because `lab.Counter` is defined by two different defining loaders; each definition has its own static fields and initialization state.

**Question 4.** A test modifies `System.setProperty`; does switching the URLClassLoader reset the property?

**Answer:** No, because properties exist at the JVM/process scope. You must reset them properly with appropriate synchronization or fork a new JVM.

**Question 5.** Why is forking a JVM suitable for testing `System.exit` or `-XX:MaxMetaspaceSize`?

**Answer:** It provides an independent process that can terminate or crash without killing the test runner; JVM flags are set when launching separately.

**Question 6.** Does using a new JVM process automatically roll back database writes from the previous JVM?

**Answer:** No. A database is out-of-process state; isolated database fixtures, transaction cleanup, or namespaces are required.

**Question 7.** Does `URLClassLoader.close()` guarantee that the plugin's `Class<?>` disappears?

**Answer:** No. If Class, object, thread, or static cache references remain, the class/loader may still be reachable. Unloading is determined by the GC/JVM.

**Question 8.** Why is it necessary to check `fromA.getClassLoader() == loaderA` when testing static isolation?

**Answer:** To prove that the class was actually defined by loader A, rather than being provided by the parent loader and inadvertently sharing static state.

**Question 9.** What is the consequence if the runner spawns a child JVM without setting a timeout?

**Answer:** The test may hang indefinitely if the child deadlocks or waits on I/O; timeouts, exit monitoring, and process cleanup are required.

**Question 10.** Do two new loaders guarantee that two ServiceLoaders return different providers properly?

**Answer:** Not by default. Proper service API identity, TCCL/explicit loader, SPI metadata, parent delegation, and caching are required. A new loader only creates a namespace; the discovery policy must still be defined.

## Key Takeaways

**To verify independently, first ask: "Does this state belong to a class defined by a specific loader, or to a specific JVM/process?"** Use a **new loader** to test class identity, static fields, and plugin namespaces; use a **new JVM** when you need to reset process-wide state, runtime flags, initialization history, or isolate severe failures. In both cases, control **parent delegation, shared APIs, classpath/module path, TCCL, caches, and cleanup**. A forked JVM does not replace isolating **files/databases/networks**, and `URLClassLoader.close()` does not mean immediate unloading.

**Standard Java 17 References:**

- `ClassLoader` and `getClassLoadingLock`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- `URLClassLoader` and `close()`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html
- `ProcessBuilder`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ProcessBuilder.html
- `Process`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Process.html
- `ModuleLayer` and `defineModulesWithOneLoader`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html
- `ServiceLoader`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html
- JLS `12, Execution, Loading, Linking and Initialization: https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html
- JVMS `5, Loading, Linking and Initializing: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html
