# Costs of JAR reading, verification, linking, and initialization in Java ClassLoader

When a Java application experiences **first-call latency (cold path)**, the cause may lie in **finding and reading classes from JARs**, **class loading**, **bytecode verification**, **linking/resolution**, **running static initializers**, or in **JIT compilation, dependency loading, I/O, and framework code** that occur afterward. These are **distinct** costs in terms of mechanism, timing, and optimization approach.

**Most importantly:** Do not treat all time spent in `ClassLoader.loadClass(...)` as **JAR reading** time, and do not treat all latency on the first method invocation as **verification**. Java allows the JVM to perform certain linking/resolution steps **early or late** as long as it complies with the Java Language Specification (JLS) and the Java Virtual Machine Specification (JVMS). Accurate diagnosis requires understanding semantic boundaries, observing class loading/initialization, and measuring actual workloads.

This lesson uses **Java 17+**, distinguishing between code running on the classpath, inside JARs, and via `URLClassLoader`. With named modules/JPMS, the JVM adds module resolution steps and access rules, but the foundational load → link → initialize model remains the starting point.

## 1. Lifecycle map and where costs can arise

```text
First time the program needs a class
          |
          v
[1] Choose ClassLoader / delegation / look up already loaded class
          |
          v
[2] Locate the class bytecode
    - find entry in JAR/directory/module
    - read bytes, possibly decompress ZIP/JAR
    - possibly check JAR signer/metadata
          |
          v
[3] Loading / create Class<?> and runtime type metadata
          |
          v
[4] Linking
    ├── Verification: verify class/bytecode validity
    ├── Preparation: prepare storage, default static values
    └── Resolution: resolve symbolic references (can be lazy)
          |
          v
[5] Initialization when required by the JVM
    - initialize superclass/relevant superinterfaces
    - run static field initializers and static blocks (<clinit>)
          |
          v
[6] Execute method/constructor
    - bytecode interpreter/JIT
    - I/O, network, DB, framework initialization if any
```

This diagram only helps **categorize activities**; it does not assert that each step always happens sequentially, once, and can be isolated with a single timer. Verification/preparation must complete before initialization, but the JVM is permitted to perform symbolic reference resolution at appropriate points, even after the class has already been initialized.

Some activities can also occur **recursively**: loading class A triggers loading B, verifying B, and then loading C; A's static initializer in turn reads config and opens network connections. A measurement saying "loading A took 200 ms" may include the behavior of many dependencies/callbacks, not just the `A.class` file itself.

## 2. Cost types and the right perspective

| Phase | Work that may occur | Common symptoms | Misconception to avoid |
|---|---|---|---|
| **Class lookup** | `findLoadedClass`, parent delegation, classpath/JAR/module search | Many classpath entries, plugin loaders, class not yet in cache | "Every `loadClass` re-reads the JAR" |
| **JAR/ZIP reading** | Open archive, locate central directory/entry, read/decompress bytes | Cold filesystem/cache, large archives, many class loads | "Larger JARs are always proportionally slower" |
| **JAR signature/metadata** | Process manifest, signers/certificates depending on how the loader/JAR verifier works | Signed JARs, many entries, security/package checks | "JAR signature verification = bytecode verification" |
| **Class definition** | Create runtime type, metadata, constant pool, loader/module/package relationships | Metaspace and class count grow | "Calling `Class.forName` always defines a new class" |
| **Bytecode verification** | Check structure, type correctness, stack/control flow | `VerifyError` or class linking time | "Disabling the verifier is a recommended production optimization" |
| **Preparation** | Allocate default static fields, method tables/VM structures | Metadata/static storage begins to exist | "Preparation runs `static {}`" |
| **Resolution** | Look up symbolic references to classes/fields/methods and validate them | First-use latency, `NoSuchMethodError` on linkage | "Every reference is resolved completely at load time" |
| **Initialization** | Execute `<clinit>`, static field expressions, potentially I/O/locks | Logs from static blocks, first-use spike | "`loadClass` always runs static blocks" |
| **JIT/runtime warmup** | Interpreter profiling, compilation, GC, caches | Faster after multiple runs | "The second run is faster solely due to class caching" |

Phases can overlap within a single execution. A single microbenchmark metric is not enough to strictly split total latency into individual parts.

## 3. Costs of finding and reading classes from JARs

### 3.1. JAR is a ZIP format with a lookup structure

A standard JAR is essentially a ZIP archive with a manifest/metadata and entries, for example:

```text
plugins/greeter.jar
├── META-INF/MANIFEST.MF
├── demo/Plugin.class
├── demo/settings.txt
└── demo/internal/Helper.class
```

When `URLClassLoader` looks for `demo.Plugin`, it needs to find the resource entry `demo/Plugin.class` (or follow the appropriate source policy), open/read the bytes, and define the class. The work can include:

1. Selecting the **responsible loader** and checking the parent/already-loaded classes.
2. Finding the JAR/URL containing the class; this may probe across multiple URLs when the class is not in the first source.
3. Reading ZIP central directory/entry metadata information depending on the implementation.
4. Reading entry data; if the ZIP entry uses **DEFLATED**, it must be decompressed.
5. Applying manifest handling, package sealing, and signer/certificate processing where relevant.
6. Passing the bytecode into the JVM's class definition/linking mechanism.

**There is no rule that "a 100 MB JAR means decompressing the entire 100 MB whenever one class is needed."** Loaders typically access the relevant entry, and the OS/JDK performs caching. The amount of I/O and decompression depends on the implementation, compression, search order, caching, and packaging.

### 3.2. A long classpath does not mean linear slowdown on every call

Having many JARs on the classpath means **finding a class whose JAR is unknown** may require inspecting multiple sources. However:

- The JVM/loader retains already-loaded results keyed by runtime class identity.
- ZIP indexes, file handles, archive readers, and the filesystem page cache can be reused.
- With parent delegation, a platform class can be returned immediately by the parent **without scanning plugin JARs**.
- A custom class loader may have a different cache/index/lookup policy than `URLClassLoader`.
- Most applications only load **a subset** of the total class entries across all dependencies.

Therefore, **the number of JARs** and **total JAR bytes** are indicators to investigate, not a reliable time formula.

### 3.3. Cold filesystem cache and warm cache

Reading a JAR for the first time after machine boot/deployment may hit actual storage. Subsequent reads may be served from the **OS page cache**, the runtime's ZIP/JAR cache, or the filesystem cache. Conversely, slow disks/network filesystems, antivirus/file scanning, storage contention, or archives from remote sources can sharply increase costs.

A comparison within the **same JVM** is also affected by class-loader caching. A comparison in a **new JVM** may still benefit from the OS page cache. Therefore, you must clearly define what "cold" means:

- A fresh JVM or an already-running JVM?
- A new loader or a reused loader?
- A new process while the OS page cache is still warm?
- Is the JIT already warm?
- Has the framework/plugin already been initialized?
- Is the JAR on a local SSD or a network mount?

Do not lump all of these cases together as "cold start" and then compare measurements.

### 3.4. JAR signing is different from bytecode verification

When using a **signed JAR**, JAR verification/signature processing may check digests, signer metadata, and certificate associations of entries depending on the access path/loader. This work differs from **JVM bytecode verification**, which verifies class file structure as well as type, stack, branch, and instruction safety.

| Action | Objective |
|---|---|
| JAR entry/signature verification | Entry contents and signer metadata/signatures conform to JAR rules |
| Package signer consistency | Classes in the **same runtime package/defining loader** have a consistent certificate set |
| Bytecode verification | Valid instructions, type safety, stack/control flow/class file |
| Authorization/trust | Whether the application/organization decides to trust the JAR source — this is a separate question |

**Do not disable signature checks or bytecode safety just to speed up startup.** These checks serve different purposes; practical optimization should start with dependency scope, I/O, and initialization code.

## 4. Loading: obtaining bytecode and creating the runtime class

JLS `12.2 and JVMS `5.3 describe **loading**: finding the binary representation of a class/interface and creating the corresponding runtime class.

`ClassLoader.loadClass("demo.Plugin")` uses the **binary name**, not the path `demo/Plugin.class`. A typical parent-first implementation:

```text
loadClass(name)
  |
  +-- class already loaded/recorded? -> return Class<?>
  |
  +-- try parent loader first
  |       |
  |       +-- parent has class -> return parent's class
  |
  +-- findClass(name) in this loader
          |
          +-- find class bytes and defineClass(...)
```

Class identity:

```text
(binary name, defining loader)
```

Calling `loadClass` again on the same loader for an already-present class typically returns the same `Class<?>`; it does not repeat `defineClass`, bytecode verification, and static initialization as if loading a new runtime class.

**However, the cost of repeated lookup is not zero.** There is still a method call, lookup/locking checks depending on the loader, and JIT/runtime impact. A custom loader can perform redundant I/O/logic before the cache lookup if the code is written poorly.

### A new loader creates a new "cold class"

Two different loaders can define the same binary name as **two separate runtime classes**. For plugin reload:

```text
LoaderV1 -> demo.Plugin (runtime class V1)
LoaderV2 -> demo.Plugin (runtime class V2)
```

V2 must perform the load/link/init work for its runtime type under the corresponding conditions; V2 cannot be considered "warm" merely because V1 was loaded earlier in a different defining loader. Some JVM/OS-level caches may still help, but it cannot reuse all runtime type identity/state.

Creating hundreds of class loaders to "parallelize startup" is not necessarily effective: it adds class metadata, duplicate dependencies, I/O contention, repeated verification/initialization, and memory pressure.

## 5. Verification: the JVM checks bytecode before execution

Verification is part of **linking**. The JVM checks whether the class representation/bytecode conforms to the rules of the Java Virtual Machine, for example:

- The class file is well-structured, with a valid constant pool and metadata.
- Instruction opcodes and operands have valid formats.
- Branch targets fall on valid instruction boundaries.
- Operand stack/local variables have appropriate types across control-flow branches.
- Method descriptors, return operations, and certain type relationships are checked.
- Verification information such as `StackMapTable` has appropriate structure/semantics when required.

**Verification cost** depends on code size/complexity, the number of methods/classes, dependency loading, and JVM implementation decisions. It is not necessarily proportional to **compressed JAR size**.

In particular, a class loader successfully finding bytes **does not guarantee** valid bytecode. The JVM may throw:

- `ClassFormatError`: the binary class file is malformed.
- `VerifyError`: bytecode fails type/control-flow checks.
- `UnsupportedClassVersionError`: the class-file version is newer than the runtime supports.
- Other `LinkageError`s if runtime type/reference relationships are invalid.

**Do not use options that disable/bypass bytecode verification as a "default optimization."** They may be unsupported or have semantics that vary across JDKs, weakening JVM invariants. If verification appears prominently in a profile, measure the number of new classes/methods being loaded and why the codegen/transform pipeline is generating so many classes.

## 6. Linking: preparation and resolution are not initialization

**Linking** consists of verification, preparation, and resolution of symbolic references. However, resolution can be performed **eagerly or lazily** depending on the JVM, and is not always completed in full before the class is used.

### 6.1. Preparation

Preparation allocates storage for static fields and sets **default values**, while the VM may also prepare internal structures for method dispatch. For example:

```java
class State {
    static int count = compute();
    static Object cache = new Object();

    static int compute() { return 7; }
}
```

This is an **illustrative snippet**, without a standalone `main`.

Under the JLS model, preparation is responsible for preparing static storage; the assignments `count = compute()` and `new Object()` belong to **initialization**, not preparation. The JVM is permitted to optimize/prepare additional metadata, but it must not alter Java observable semantics.

A special case is **constant variables** under the JLS (such as `static final int LIMIT = 10;`): the compiler/JVM handles compile-time constant values specially. Do not infer that every `static final` is a constant variable; for example, `static final Integer BOXED = 10;` or `static final String ID = fetch();` must be evaluated during initialization.

### 6.2. Resolution

Bytecode contains symbolic references to:

- Other classes/interfaces.
- Fields and methods of other classes/interfaces.
- Method handles, dynamically-computed constants, and invokedynamic call sites where applicable.

Resolution replaces/checks symbolic references so the runtime can use them in accordance with type/access rules. For example, suppose class A has a method that calls `helper.Missing.run()`; the JVM might **not yet resolve** the relevant method/class until that code path requires it.

Diagram:

```text
A loaded
  |
  +-- A symbolic reference -> B.method
          |
          +-- JVM may resolve beforehand or when used
          +-- check B/lookup/access/descriptor
          +-- use resolution result per runtime implementation
```

**Misconception:** "If calling `loadClass("A")` succeeds, every method/dependency of A is guaranteed to be usable." Certain errors such as `NoSuchMethodError`, `NoSuchFieldError`, `IllegalAccessError`, or `NoClassDefFoundError` may only appear when a code path needs that reference.

JLS `12.3 allows implementation flexibility regarding the timing of resolution, while requiring errors to surface at a point when the program may directly or indirectly require linkage.

### 6.3. Linking can be spread out over time

A startup profiler should not try to attribute the entire **resolution cost** to the initial `Class.forName` phase. Part of it can arise during later invocations, reflection, lambda bootstrap, or dynamic linkage. Measure both the **cold first request** and **steady-state** if service latency is the goal.

## 7. Initialization: where static code can make startup extremely slow

Initialization executes **class variable initializers** and **static initializer blocks** according to the rules of JLS `12.4. This is **arbitrary application code**: it can build caches, parse configuration, open database connections, read JAR resources, start threads, or wait on locks.

For example:

```java
public final class ExpensiveConfig {
    static final java.util.Map<String, String> SETTINGS = loadAll();

    private static java.util.Map<String, String> loadAll() {
        // Read files, parse JSON, look up environment, etc.
        return java.util.Map.of("mode", "default");
    }
}
```

This snippet compiles in a file named `ExpensiveConfig.java`, though it has **no `main`**; the comment describes real work that may occur. Class initialization time can be significant if `loadAll()` performs I/O/network operations.

**Important distinctions:**

- `loader.loadClass("demo.Plugin")` **does not actively request initialization** under its normal contract.
- `Class.forName("demo.Plugin", false, loader)` finds and links the class per its contract, **without requesting initialization**.
- `Class.forName("demo.Plugin", true, loader)` **requests initialization** if the class has not yet been initialized.
- Creating an instance of the class or invoking a static method/writing a static field can trigger initialization.
- Reading a **compile-time constant variable** via the class name does not necessarily trigger initialization of the declaring class.
- Obtaining the class literal `SomeClass.class` generally **does not by itself trigger initialization** of that class.
- Reflection/method handles/initialization dependency paths have their own rules; read the specific JavaDoc/JLS.

You should not claim that `loadClass` only performs I/O and "does no linking at all" — you can only assert that `loadClass` **does not itself request running `<clinit>`**.

### 7.1. Initialization runs once per runtime class

Within a JVM, a specific runtime class is initialized via a synchronization-guaranteed JVM procedure. If two threads concurrently request initialization of an uninitialized class, there may be **wait time on the initialization lock**. A static initializer with slow I/O or a lock/dependency cycle can amplify latency and cause unintended deadlocks.

Creating a new-generation loader for the same binary name creates a **new runtime class** with independent initialization. Reloading a plugin multiple times can re-trigger static setup/I/O/allocations on every generation.

### 7.2. Failures can make a class unusable

If a static initializer throws an exception, the JVM may throw `ExceptionInInitializerError` on the first attempt. The runtime class is recorded in an **erroneous state**, and subsequent uses may throw `NoClassDefFoundError` indicating that initialization failed. You cannot successfully "retry" simply by calling `Class.forName` again on the **same runtime class/defining loader**.

For a plugin that needs retry logic, move I/O or network initialization into a lifecycle method with explicit state management and error handling rather than hiding everything inside `static {}`.

## 8. Java 17+ demo: loading from a JAR and observing load vs. initialize

The demo creates:

- A class `demo.Plugin` located **only inside plugin.jar**, not on the host's runtime classpath.
- A resource `demo/settings.txt` inside the same JAR.
- A `URLClassLoader` created in the host.
- Steps that read the JAR resource, load the class, call `Class.forName(..., false, loader)`, and then request initialization.

**Purpose:** Demonstrate the **observable ordering** via stdout and prove that `<clinit>` does not run immediately when the loader returns `Class<?>`. This example **does not attempt to assign exact timings to each step**.

### 8.1. Directory structure

```text
phase-demo/
├── src/
│   ├── plugin/demo/Plugin.java
│   └── host/host/PhaseProbe.java
├── out/
│   ├── plugin/demo/settings.txt
│   └── host/
└── plugin.jar
```

### 8.2. Plugin code

File **`src/plugin/demo/Plugin.java`**:

```java
package demo;

public final class Plugin {
    static {
        System.out.println("PLUGIN <clinit>");
    }

    public static String greet() {
        return "hello";
    }
}
```

The string `PLUGIN <clinit>` is a **line printed by the application's static block**, not a VM log. We use it to identify when the initialization code executes.

### 8.3. Host code

File **`src/host/host/PhaseProbe.java`**:

```java
package host;

import java.io.InputStream;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;

public final class PhaseProbe {
    public static void main(String[] args) throws Exception {
        URL jar = Path.of(args[0]).toUri().toURL();

        try (URLClassLoader loader = new URLClassLoader(
                new URL[] {jar},
                PhaseProbe.class.getClassLoader())) {

            System.out.println("loader created");

            try (InputStream in = loader.getResourceAsStream(
                    "demo/settings.txt")) {
                if (in == null) {
                    throw new IllegalStateException(
                            "missing resource");
                }
                System.out.println("resource: "
                        + new String(in.readAllBytes(),
                                StandardCharsets.UTF_8).trim());
            }

            Class<?> type = loader.loadClass("demo.Plugin");

            System.out.println("loaded by child: "
                    + (type.getClassLoader() == loader));
            System.out.println("after loadClass");

            System.out.println("forName(false) same: "
                    + (Class.forName(
                            "demo.Plugin", false, loader) == type));
            System.out.println("before initialization request");

            Class.forName("demo.Plugin", true, loader);

            System.out.println("after initialization request");
            System.out.println("call: "
                    + type.getMethod("greet").invoke(null));

            System.out.println("cached type: "
                    + (loader.loadClass("demo.Plugin") == type));
        }
    }
}
```

**Mechanism explanation:**

1. Creating `URLClassLoader` does not mean `demo.Plugin` has been loaded or the entire JAR has been read.
2. `getResourceAsStream("demo/settings.txt")` reads a resource from the JAR without needing to initialize `demo.Plugin`.
3. `loadClass("demo.Plugin")` finds and loads the class, but does not request running `Plugin`'s static block.
4. `Class.forName(..., false, loader)` returns the same runtime class, still without running `<clinit>`.
5. `Class.forName(..., true, loader)` requests initialization, and the static block prints `PLUGIN <clinit>`.
6. Calling `greet` afterward uses the already-initialized class; the final lookup returns the exact same `Class<?>` object.
7. `try-with-resources` closes the loader/file handles when the scope ends; it does not mean immediate class unloading.

### 8.4. Build/run on Linux, macOS, or Git Bash

From the `phase-demo` directory:

```bash
mkdir -p out/plugin/demo out/host

javac --release 17 -d out/plugin \
  src/plugin/demo/Plugin.java

javac --release 17 -d out/host \
  src/host/host/PhaseProbe.java

printf 'mode=fast\n' > out/plugin/demo/settings.txt

jar --create --file plugin.jar -C out/plugin .

java -cp out/host host.PhaseProbe plugin.jar
```

**Do not add `plugin.jar` to the host's `-cp`**, because the goal is for the child `URLClassLoader` to **actually define the plugin class**. `Path.of(args[0]).toUri().toURL()` converts the JAR path from the command argument into a URL for the loader to open.

### 8.5. Build/run on PowerShell

```powershell
New-Item -ItemType Directory -Force -Path out/plugin/demo, out/host | Out-Null

javac --release 17 -d out/plugin src/plugin/demo/Plugin.java
javac --release 17 -d out/host src/host/host/PhaseProbe.java

[System.IO.File]::WriteAllText(
    "out/plugin/demo/settings.txt",
    "mode=fast",
    [System.Text.UTF8Encoding]::new($false))

jar --create --file plugin.jar -C out/plugin .

java -cp out/host host.PhaseProbe plugin.jar
```

### 8.6. Verified output

The example was **compiled with `javac --release 17`** and ran successfully on **OpenJDK 24**; exact stdout:

```text
loader created
resource: mode=fast
loaded by child: true
after loadClass
forName(false) same: true
before initialization request
PLUGIN <clinit>
after initialization request
call: hello
cached type: true
```

The output shows:

- `loaded by child: true` confirms that the plugin's defining loader is not the host loader.
- The line `PLUGIN <clinit>` appears only **after** `before initialization request` and **before** `after initialization request`.
- No new `PLUGIN <clinit>` occurs when calling the static method or looking up the class again, because the runtime class is already initialized.
- The fact that `loader.getResourceAsStream` finds the right entry **does not prove** that the plugin bytecode was already verified/initialized at the moment the resource was read.

**Do not over-infer:** Stdout does not reveal the exact moment the JVM verifies each method or resolves each reference. The JLS permits flexible linking timing, so detailed investigation requires using JVM logging/profiling.

## 9. Observing class load, verification, and initialization with JVM logging

On HotSpot/OpenJDK Java 17+, **unified logging** helps observe class loading/initialization events. You can re-run the demo with:

```bash
java '-Xlog:class+load=info,class+init=info' \
  -cp out/host host.PhaseProbe plugin.jar
```

PowerShell (single line):

```powershell
java "-Xlog:class+load=info,class+init=info" -cp out/host host.PhaseProbe plugin.jar
```

The command was tested on OpenJDK 24; the JVM log contains lines similar to:

```text
[...][info][class,load] demo.Plugin source: file:/.../plugin.jar
[...][info][class,init] Start class verification for: demo.Plugin
[...][info][class,init] End class verification for: demo.Plugin
[...][info][class,init] ... Initializing 'demo/Plugin' ... by thread "main"
```

The `[...]` markers and the `file:/.../plugin.jar` path are **shorthand notation**: timestamps, addresses, threads, JAR location, and log ordering depend on the JVM, OS, logging options, and other classes loaded during execution. This is an **illustrative log format from a test run**, not fixed stdout to assert on.

When you need less log output, write to a file and filter by class name:

```bash
java '-Xlog:class+load=info,class+init=info:file=classes.log' \
  -cp out/host host.PhaseProbe plugin.jar
```

Depending on the JVM vendor/version, tags and detail levels may differ. Check which log tags the JVM supports with:

```bash
java -Xlog:help
```

**Logging also takes time.** Do not measure production startup latency and conclude "enabling verbose logs makes verification N% slower" without isolating the logging and I/O overhead of the measurement mechanism itself.

### 9.1. Logs are not a stopwatch for individual steps

`[class,load]` reports a class-loaded event at that logging level, but it does not directly allow subtracting timestamps and claiming the difference is **pure JAR I/O**. Between `class,load` and `class,init` there can also be scheduling, other class loading, linking, application code, safepoints, or tool overhead.

`-Xlog:class+init` provides many events about verification/initialization, but it **does not turn every linking activity into a complete causal graph**. Combined tooling is needed if the goal is to track down bottlenecks in a real environment.

## 10. Why is a single measurement with System.nanoTime misleading?

A piece of code can measure the wall-clock elapsed time (actually elapsed monotonic time) of an operation:

```java
long t0 = System.nanoTime();
Class<?> type = loader.loadClass("demo.Plugin");
long elapsedNs = System.nanoTime() - t0;

System.out.println("loadClass elapsed ns: " + elapsedNs);
```

This is an **illustrative snippet inside a method** with an existing `loader` variable; it is not a standalone application. The printed number **varies from run to run** and does not represent "the cost of reading only the bytes of plugin.jar."

Why?

- `loadClass` may delegate to the parent, search JARs, load dependencies, and perform part of linking depending on the JVM.
- Scheduling, GC, the OS page cache, CPU frequency scaling, and I/O contention alter the elapsed time.
- `System.nanoTime` measures elapsed time between two points; **it does not label the cause**.
- Measuring the first and second calls on the **same loader** compares an **unloaded class** with an **already-loaded class**, which are two different workloads.
- If you measure repeatedly on one loader with the same binary name, you are usually only benchmarking a cached lookup.
- If you create a new loader on each iteration, you add the costs of loader creation, archive handling, GC/metaspace, and class generation, and results can be skewed by the new pressure.

### End-to-end measurements are still useful when the goal is clearly defined

For example, suppose you want to know **how long the user waits until a plugin is ready**. Measure the actual pipeline:

```text
start request
   -> create loader
   -> load provider
   -> verify/link per JVM
   -> initialize/instantiate
   -> read config
   -> start plugin
   -> ready
```

That is an **end-to-end latency metric**, which is meaningful to users. Just do not call it "verification time" simply because `Class.forName(...)` appears in the call stack.

### Categorize into at least three types of measurements

| Measurement type | How it is structured | Question answered |
|---|---|---|
| **Cold startup** | Fresh JVM process with workload/OS cache/flags recorded | How long does starting the service/plugin take? |
| **First use** | An already-running JVM; the class/module/provider is used for the first time | What cost does the first request incur? |
| **Steady state** | Many requests after warmup, once the JVM/JIT has relatively stabilized | What is the typical latency after class loading? |

All three should inspect **p50, p95/p99, and variance**, not just a single run. For Java micro-level benchmarks, use **JMH** when appropriate to structure warmup, forks, and repeated measurements; you still need to design state carefully so you do not accidentally measure the same already-loaded class or use an OS cache state that does not match the scenario under investigation.

## 11. Measuring and finding bottlenecks with the right tools

### 11.1. Unified logging and Java Flight Recorder

Useful tools across many HotSpot/JDK releases:

- **`-Xlog:class+load=info`**: identify which classes are being loaded and from which source; observe many loads.
- **`-Xlog:class+init=info`**: track events related to initialization and, depending on the release, verification.
- **Java Flight Recorder (JFR)**: analyze JVM activity during startup/first request; observe class-loading events, CPU samples, allocation/GC, and I/O when events/configuration are appropriately enabled.
- **`jcmd <pid> VM.classloader_stats`**: inspect class-loader footprint statistics when supported by the JVM.
- **Async profiler / sampling profiler**: inspect CPU stacks/time spent in ZIP, verifier, linker, reflection, class initialization, or application code itself.
- **I/O/file diagnostics**: file opens, bytes read, page faults, and storage latency; specific tools depend on the OS.

Not every event is enabled by default or available across all vendors/JDKs. Check JFR and logging configuration before concluding that an event "did not happen" merely because it was not recorded in the trace.

### 11.2. Reading stack profiles by cause category

| Frequent stack/signals observed | Hypothesis to investigate |
|---|---|
| ZIP/JAR reading, `JarFile`, filesystem read | Frequent JAR opens/class bytes/resource reads; cache/storage |
| `ClassLoader.loadClass`, custom `findClass`, URL search | Lookup policy, parent delegation, scanning, custom overhead |
| Class verification/linking VM code | Number of classes/methods/code generation or resolution |
| Class initialization routines, `<clinit>` | Static initializer doing CPU/I/O/locks |
| Reflection, service provider discovery | Framework scanning, class/link/init, provider constructors |
| JIT compilation threads | Warmup/code generation distinct from class loading |
| GC/safepoint pressure | Allocation/metadata churn, plugin loader generations |
| DB/network client connect | Application initialization code, not JAR I/O |

**Find the root cause before optimizing.** If 95% of the startup delay is inside a static block opening network connections, switching the JAR from DEFLATE to STORED will likely be far less effective than moving I/O out of `<clinit>`.

## 12. Targeted optimization of JAR reading and class loading

### 12.1. Reduce the number of classes that actually must be loaded at startup

- Avoid scanning and initializing every plugin when the user only needs a few.
- With SPI, avoid iterating/instantiating all providers early if the request does not use them yet.
- Defer loading optional features until needed (with a state machine and error handling).
- Audit framework annotation/reflection scanning, auto-configuration, and dependency discovery.
- Reduce unnecessary plugin reloads/loader creation; reuse loaders within a valid lifecycle.

**Note:** Being "more lazy" can reduce startup time, but it **shifts latency to the first request**. Decide where your latency budget belongs instead of treating laziness as an unconditional win.

### 12.2. Sensible packaging and classpath design

- Remove genuinely unused dependencies, especially JARs scanned by frameworks or opened on the startup path.
- Reduce split/duplicate classes and package conflicts.
- Place resources/classes that typically go together in an easily accessible deployment.
- For plugin loaders, scope URLs to the right plugin group instead of passing hundreds of unrelated JARs into every loader.
- Avoid unnecessarily opening/closing the same archive inside business loops.
- Check the compression level if profiling shows inflate/decompression is genuinely significant; measure the tradeoff between file size, I/O, and CPU.

**There is no rule that "the least-compressed JAR is always the fastest"**: reducing compression saves decompression CPU but increases the bytes that must be read, affecting I/O and caching. On a network filesystem, the tradeoff can reverse. Nor is there a rule that every application runs fastest when packaged as a single fat JAR — nested JAR loaders, scanning/indexing, and framework behavior can differ from a standard classpath.

### 12.3. Do not build a custom ClassLoader for minor goals

`URLClassLoader` and the system/module loaders already implement many necessary optimizations and constraints. A custom loader should only be used when there are requirements such as:

- The source of class bytes is not a standard JAR/directory.
- Dedicated namespace/dependency isolation is genuinely needed.
- Intentional bytecode transformation/loading policies.
- A plugin lifecycle/domain that differs from existing loaders.

A hand-rolled loader that reads the entire JAR on every `findClass` or fails to maintain state can turn class lookup into a severe bottleneck. However, **do not improperly cache `Class<?>` or bypass parent delegation/linking** to "speed things up": this easily causes `LinkageError` and class identity mismatches.

### 12.4. CDS and AppCDS

**Class Data Sharing (CDS)** on HotSpot can help reduce startup costs, increase class metadata sharing, and lower memory footprint for supported class/loader/archive configurations. **Application CDS (AppCDS)** extends sharing to certain application classes.

You can read the Java launcher docs/HotSpot CDS docs and check:

```bash
java -Xshare:auto -version
```

This command illustrates the option to share data when a suitable archive exists; **do not measure it in isolation** to infer how much an application has sped up. You can use CDS-related unified logging to confirm whether the runtime is using the shared archive.

Important limitations:

- CDS does **not** make a `static {}` block containing network calls free.
- CDS does not guarantee that every class from **custom class loaders** or plugins is shared the same way as bootstrap/platform/application loader classes.
- Sharing class metadata and sharing **runtime static state/plugin instances** are two different things.
- Benefits depend on the archive, JDK, classpath/module path, deployment, and actual workload.

Do not claim that "enabling CDS completely skips verification, linking, and initialization of every class." Measure under supported configurations and verify actual behavior.

## 13. Optimize initialization instead of making the JVM "lazy about checking"

A class with a complex static initializer:

```java
final class ExpensiveStart {
    static final Map<String, String> CONFIG = readRemoteConfig();

    static Map<String, String> readRemoteConfig() {
        // Synchronous I/O on the first use of the class.
        throw new UnsupportedOperationException(
                "Illustrative only");
    }
}
```

This is a **non-standalone illustrative snippet** that requires `import java.util.Map;`. Throwing an exception here emphasizes the danger of I/O/failures during static initialization, **not a pattern to follow**.

Problems:

- The first active use may incur network cost and timeouts.
- Other threads wait on initialization of the same runtime class.
- If initialization fails, the class can enter an erroneous state, making retries difficult.
- Reloading a loader generation can re-run all of that work.

A usually better alternative: **an explicit lifecycle**.

```java
public final class PluginService {
    private volatile Config config;

    public void start(Config loaded) {
        if (loaded == null) {
            throw new IllegalArgumentException("config required");
        }
        config = loaded;
    }

    public String mode() {
        Config c = config;
        if (c == null) {
            throw new IllegalStateException("not started");
        }
        return c.mode();
    }

    public record Config(String mode) {}
}
```

This is a compilable class in `PluginService.java` on Java 17+, **without `main`**. It lets the host decide **when to read the config**, configure timeouts/retries, and mark the plugin as ready. `volatile` only provides reference visibility in this example; a multi-step production lifecycle requires appropriate synchronization/a state machine.

**Tradeoff:** Explicit initialization does not make the total work disappear; it lets you move, measure, retry, and manage that work according to the proper lifecycle. Do not just move code into a constructor and declare it optimized if startup still has to instantiate all objects immediately.

### Lazy holder for CPU-only internal data

If you want to lazily initialize an immutable structure only when actually used:

```java
public final class LookupTable {
    private LookupTable() {}

    private static final class Holder {
        static final java.util.Map<String, Integer> TABLE =
                java.util.Map.of("a", 1, "b", 2);
    }

    public static int get(String key) {
        return Holder.TABLE.getOrDefault(key, -1);
    }
}
```

This is a compilable utility class in `LookupTable.java`. `Holder` is initialized when a code path uses the `Holder.TABLE` field per active-use rules, usually avoiding that work when only loading the outer class.

However, do **not** put network I/O that could persistently fail into a lazy holder without a retry/timeout mechanism: a failure is still a class initialization failure of `Holder`.

## 14. JIT warmup and initialization are two different phenomena

Sometimes after 1,000 requests, a method runs noticeably faster. Possible reasons include:

- The JVM has loaded classes that were previously unused.
- Class initialization has completed.
- OS/JAR caches are warm.
- The JIT compiler has enough profiling data to compile/optimize methods.
- Heap caches/application data structures have been created.
- Network/DB connection pools are ready.

The 1st method call may be slow because of `<clinit>`; the 1,000th call is fast because of JIT compilation. Both fall under "warmup" in everyday language, but they must be **distinguished when profiling**.

JIT also incurs CPU/compilation thread and code cache costs; that is **not verification**. If you want to measure the time of a Java business method at steady state, use a benchmark/profiler tool suited to that purpose, and avoid mixing class loading into algorithm performance benchmarks.

## 15. Impact of JPMS, ServiceLoader, and plugin architecture

### Named modules and the module graph

JPMS involves module resolution, readability, exports/opens, and service provider declarations. These activities can affect startup/discovery:

- Resolving the module configuration happens when the launcher or a `ModuleLayer` is set up per contract.
- Class load/link/init still apply to classes in named modules.
- `ModuleLayer.defineModulesWithOneLoader` and `defineModulesWithManyLoaders` create different loader mappings, affecting the number of runtime namespaces.
- Class-loader caching and resource access also depend on module membership/encapsulation.

Do not attribute all module resolution time to "JAR reads." Module configuration and runtime class linking have different purposes and costs.

### ServiceLoader

`ServiceLoader.load(Service.class)` uses the **thread context class loader** per the Java SE 17 API; the overload taking an explicit loader uses that loader. Providers are discovered/instantiated **lazily** according to `ServiceLoader`'s mechanism; iterating through all provider instances can trigger:

```text
descriptor/module discovery
    -> provider class loading
    -> verification/linking
    -> initialization
    -> provider constructor/factory
    -> application initialization
```

Therefore, a framework running `for (Service s : ServiceLoader.load(Service.class))` during startup can incur multiple phases at once. When accounting for latency, distinguish between **creating the ServiceLoader object** and **iterating and actually instantiating providers**.

### Per-plugin loader vs. shared loader

- **One loader per plugin** can isolate dependencies and lifecycles, but may load/verify/initialize the same private classes multiple times across multiple defining loaders.
- **A shared loader** can share classes/static state and reduce duplicate metadata, but causes version conflicts or prevents plugins from hot-reloading independently with a new class identity.
- Both approaches must keep **shared SPI/DTO contracts** in an appropriate common loader if the host and plugins exchange typed objects.
- Multiple uncollected loader generations can increase metaspace usage and GC pressure, affecting long-term performance.

Do not switch to a shared loader just to reduce startup time without checking class identity, dependency versioning, and lifecycle.

## 16. Common errors and how to classify them

### A. `ClassNotFoundException`

The selected loader cannot find the binary class name. Check the classpath/JAR URL, parent delegation, TCCL, and custom loader resource mapping. This is typically a **lookup issue**, not proof that "verification is too slow."

### B. `NoClassDefFoundError`

This can occur because a required dependency is not present when the JVM resolves, due to a binary name mismatch, or because the class has entered a **failed initialization** state. Read the full cause/message and identify which class failed first.

### C. `ClassFormatError` / `VerifyError`

The class-file bytes are malformed or bytecode verification failed. Do not "fix" this by disabling the verifier for faster startup. Check transformers/code generators, the class-file version, and the cause of the invalid bytecode.

### D. `NoSuchMethodError` / `NoSuchFieldError`

A symbolic reference does not resolve as the bytecode expects, usually due to a runtime dependency version mismatch. The error may appear **when the method path actually runs for the first time**, not necessarily during initial class loading.

### E. `ExceptionInInitializerError`

A static initializer threw an exception. The class can enter an erroneous state; retrying on the same defining loader usually fails. Move I/O/failure-prone logic out of `static {}` if retry/lifecycle management is needed.

### F. `SecurityException` during class loading

This can be caused by JAR package sealing, signer/certificate set inconsistency, or a prohibited `java.*` namespace. These are class-loading constraints, **not necessarily due to SecurityManager**.

### G. `OutOfMemoryError: Metaspace`

Multiple loader generations/classes/metadata can increase memory pressure. Inspect classloader retention, TCCL, reflection caches, `ServiceLoader` instances, thread pools, and GC/unloading behavior. Do not merely increase `MaxMetaspaceSize` to mask a classloader leak.

## 17. Performance optimization workflow you can apply immediately

1. **Define the target metric:** process startup to ready, first-request latency, or steady-state throughput/p99.
2. **Lock down the environment:** Java vendor/version, CPU, storage, OS, heap/metaspace, GC, CDS, JAR packaging, and container CPU quota.
3. **Distinguish cold vs. warm:** fresh JVM, OS cache, loader generation, and JIT state.
4. **Capture class-load/class-init logs** once to identify relevant classes and JAR sources; remember to account for logging overhead separately.
5. **Collect JFR/CPU/I/O profiles** on the exact slow path, not just total milliseconds.
6. **Separate application phases:** module/plugin discovery, class load, provider instantiation, config I/O, framework startup, and readiness.
7. **Optimize the actual root cause:** reduce scanning/unused dependencies, reduce loader churn, lazily load optional features, improve filesystem access, and replace static I/O with a managed lifecycle.
8. **Preserve invariants and security:** do not disable JVM verification, and do not bypass signer/sealing/module checks.
9. **Re-benchmark** across multiple runs/forks, tracking p50/p95/p99 and class/memory footprint; compare on equivalent workloads.
10. **Run functional tests** under cold/warm/parallel startup, especially covering thread safety, dependency failures, and plugin reload.

Do not measure on a JVM that has already loaded all classes and conclude that "JAR reading is negligible" for fresh startups. Likewise, do not measure a single fresh JVM while background antivirus is scanning files and conclude that all users will experience the same slowdown.

## 18. Self-check questions

**1. Does calling `loader.loadClass("demo.Plugin")` necessarily run `static {}`?** No. The method does not by itself request initialization under its normal contract.

**2. How does `Class.forName("demo.Plugin", false, loader)` differ from the `true` overload?** `false` does not request initializing the class; `true` requests initialization if it has not yet been performed.

**3. Does `Preparation` execute `static int n = expensive()`?** No. Preparation sets default static values; the static initializer expression is executed during initialization.

**4. Is the JVM required to resolve all symbolic references immediately during initial linking?** No. It can be eager or lazy per specification requirements.

**5. Does every call to `loadClass` re-read class bytes from the JAR?** Not necessarily; an already-loaded class can be returned from the loader cache.

**6. Does reading `settings.txt` from a JAR automatically initialize `Plugin` in the same JAR?** No. Resource lookup is not equivalent to class initialization.

**7. Why is class-file verification different from JAR signature verification?** One checks bytecode/type safety; the other concerns JAR entry metadata/signatures/integrity.

**8. Does `Class.forName(..., true, ...)` taking 300 ms mean the verifier took 300 ms?** No. That time may include loading/linking, dependencies, and application static initializers.

**9. Does `NoSuchMethodError` only appear right at `loadClass` time?** No. Symbolic resolution may be deferred until the relevant point of use.

**10. Does CDS eliminate network I/O inside `<clinit>`?** No. CDS can optimize certain aspects of class metadata/load paths, but it does not skip application initialization code.

**11. Why can creating a new loader for every request incur high costs?** Each loader creates a separate namespace, which can repeat class definition/link/init, metadata, and archive work.

**12. What is the right way to compare cold startup and steady state?** Define separate test conditions, measure across multiple runs/forks, record OS/JIT/cache state, and profile bottlenecks.

## 19. Official documentation

- **Java Language Specification Java SE 17, Chapter 12 — Execution:** loading (`12.2), linking (`12.3), initialization (`12.4), timing, and lazy resolution: https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html
- **Java Virtual Machine Specification Java SE 17, Chapter 5 — Loading, Linking, and Initializing:** https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html
- **Java SE 17 `ClassLoader` API:** delegation, `loadClass`, `findClass`, and class loading rules: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- **Java SE 17 `Class.forName` API:** the `initialize` parameter: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
- **Java SE 17 `URLClassLoader`:** loading from URLs/JARs and resource lookup: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html
- **Java SE 17 JAR File Specification:** manifest, entry structure, signed JARs, and package metadata: https://docs.oracle.com/en/java/javase/17/docs/specs/jar/jar.html
- **Java SE 17 `java` launcher reference:** `-Xlog`, `-Xshare`, and JVM options: https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- **Java SE 17 `ServiceLoader` API:** provider loading/discovery: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html
- **OpenJDK JEP 310 — Application Class-Data Sharing:** https://openjdk.org/jeps/310

**Key takeaway:** Finding bytecode in a JAR, JVM verification, linking/resolution, and running `<clinit>` are **costs with different origins**. `loadClass` does not mean `initialize`, `getResourceAsStream` does not mean loading a class, and resolution can be lazy. To optimize effectively, you must **measure the right phase, distinguish cold/warm states, and address the actual bottleneck**, rather than trading away JVM correctness or safety for seemingly faster startup numbers.
