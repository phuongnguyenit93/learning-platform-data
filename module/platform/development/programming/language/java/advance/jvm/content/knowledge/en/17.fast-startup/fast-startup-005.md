# HotSpot AOT Cache: Learning from Training Runs, Creating the Cache, and Reusing It by Supported Version

**HotSpot's Ahead-of-Time (AOT) cache** is a mechanism for saving a portion of the preparation work that the JVM learned while running an application, so that subsequent startups can **reuse eligible information** and reduce startup/warm-up time. The main idea: instead of every Java process having to completely discover, load/link, and profile all of the same execution paths on its own right when serving users, we let the JVM observe a **training run**, create an **AOT cache**, and then run the application on a matching version/build with that cache.

**Key point to remember immediately:** this is a feature with specific **HotSpot** support milestones, not “every Java 17 has the new AOT cache”. **JDK 24** introduces AOT class loading/linking into the AOT cache (JEP 483). **JDK 25** adds **Ahead-of-Time Method Profiling** (JEP 515) and simplifies the cache creation command with **JEP 514**. **JDK 26** expands how object caching works with multiple GCs, including ZGC under **JEP 516**. You must verify the JVM vendor, JDK build, OS/CPU, and flags of the version **actually running**.

This AOT cache **is not** a process that converts `.class` files into a standalone native executable, **is not** GraalVM's `native-image`, and **does not guarantee** that every method of the application has already been precompiled into native code before production start.

## 1. The Problem: HotSpot Startup and Warm-up

A newly launched JVM typically has to complete many tasks:

- Initialize VM and runtime components.
- Read the classpath/modules, find and open the required classes.
- Parse class files, verify bytecode, and load and link classes.
- Perform class initialization when the program actually needs it (`<clinit>`, according to Java semantics).
- Prepare certain runtime objects and metadata.
- Run the interpreter/C1 and collect invocation/branch/type profiles.
- Compile hot methods with JIT (C1/C2) once there is sufficient evidence.
- Complete application warm-up (connection caches, object graphs, libraries).

```text
WITHOUT USING AOT CACHE
Process start
     │
     ├──► Load and link classes
     ├──► Prepare certain JVM structures
     ├──► Run and observe method profiles
     ├──► JIT compile hot methods
     └──► Serve workload
               │
               ▼
           steady state (if reached)
```

If the same application is restarted repeatedly, part of this work may be done **over and over again**. The AOT cache allows shifting the **appropriate portion** to a preparation phase and reusing it across compatible startups.

### Two Metrics That Are Not the Same

| Metric | Meaning | How to Measure |
| --- | --- | --- |
| **Startup latency** | From invoking the launcher until the application reaches ready / first useful response | Objective timestamps, ready probe, trace |
| **Warm-up time** | Time to reach relatively stable throughput/latency after startup | Multiple workload windows, compiler/CPU/latency telemetry |
| **Steady-state throughput** | Processing capacity once sufficiently warmed up | Multiple load test runs, equivalent work |
| **CPU during warm-up** | Effort used by JVM/JIT/class loading and the application | JFR/OS CPU/profile |
| **Memory footprint** | Heap, native memory, and cache mapping overhead | Heap/RSS/NMT when available |

The AOT cache aims to **improve startup/warm-up**; it **does not guarantee** that steady-state throughput always increases or that every application gets faster by the same ratio.

## 2. What Does the AOT Cache Actually Contain?

The cache contents **depend on the JDK release and HotSpot build**:

| Component | Role | Notes |
| --- | --- | --- |
| **Processed classes** | Allows reusing class loading/linking results permitted by JEP 483 | Does not guarantee every class in the entire application is in the cache |
| **Linked metadata / resolved information** | Reduces eligible repeated link/load work | Has consistency restrictions; depends on configuration |
| **Certain JVM-cacheable heap objects** | Pre-initializes selected object structures | Not a snapshot of the entire production heap |
| **Method execution profiles (JDK 25+)** | JIT can use profiles learned from training before new profiles are gathered | Does not mean the cache stores all precompiled C2 native methods |
| **Future artifacts (release-dependent)** | The AOT framework may expand | Always verify release notes; do not predict unimplemented cache contents |

**In particular:** on JDK 25, “Ahead-of-Time Method Profiling” means **saving profiles so the JIT can start optimizing earlier**; it should not be interpreted as JEP 515 having packaged all of the program's optimized C2 machine code into `.aot` like a standalone native binary.

### An AOT Cache Is Not a Heap Dump

A heap dump records an object graph snapshot for debugging; an AOT cache only stores artifacts considered valid by the JVM for reuse under consistency rules. Do not take an `.hprof` file and rename it to `.aot`. Do not expect an AOT cache to preserve runtime user sessions, TCP connection state, credentials of a process, or non-portable resources.

### The AOT Cache Does Not Bypass Java Correctness Requirements

Class loading, linking, initialization, class-loader identity, JVMTI/instrumentation, reflection, and dynamic loading all have semantics that must be preserved. If a cache is incompatible, the runtime may refuse to use the cache or refuse to start in strict mode; an old cache **must not** be used to run mismatched class definitions.

## 3. Three Core Phases: record → create → production

JEP 483 (JDK 24) uses an explicit three-phase model:

```text
Phase A: TRAINING / RECORD
  Run the application with a representative workload
         │ JVM observes classes/paths
         ▼
  AOT Configuration (.aotconfig)
         │
         ▼
Phase B: ASSEMBLY / CREATE
  Read configuration, prepare artifacts
         │ Application main does NOT run in the create phase
         ▼
  AOT Cache (.aot)
         │
         ▼
Phase C: PRODUCTION / ON
  Run the application with a compatible cache
         │
         └──► Reuse artifacts, still executes Java normally
```

### Why Separate record and create?

Recording captures **what the real application does** on a typical execution path. Cache assembly can further process classes and linked objects in a separate VM process, without needing to execute the business workload again as a production request.

Separating the phases also helps split **resource budgets**: training can be close to the deployment environment, while assembly runs in a build/CI environment with appropriate resources.

**Do not confuse:** “AOT” does not mean everything happens at `javac` compile time. Training can **actually run Java code** with simulated inputs/systems, and then assembly builds artifacts for the next run.

## 4. Important AOT Flags by HotSpot Version

The flags below belong to **HotSpot JDKs with AOT cache support (JDK 24+)**:

| Flag | Effect |
| --- | --- |
| `-XX:AOTMode=record` | Runs the application in the training phase and writes the configuration |
| `-XX:AOTConfiguration=file.aotconfig` | Path to the AOT configuration file to be created/read |
| `-XX:AOTMode=create` | Assembly phase reads the configuration and creates the cache |
| `-XX:AOTCache=file.aot` | Uses/locates the cache, depending on mode; in `create` it is the output |
| `-XX:AOTMode=on` | Production mode requiring a matching cache, helping detect errors clearly |
| `-XX:AOTMode=off` | Does not use an AOT cache in the current run |
| `-XX:AOTCacheOutput=file.aot` | From **JDK 25**: convenient record + assembly in a single invocation |
| `-XX:AOTMode=auto` | JVM automatically selects appropriate behavior based on available options/cache in supported versions |

**Do not apply these flags to JDK 17:** a standard HotSpot 17 build does not have JEP 483. Trying `java -XX:AOTCacheOutput=app.aot ...` on JDK 17 can cause `Unrecognized VM option`; that is a **version/feature availability** error, not wrong Java code.

### Do Not Enable Conflicting Modes

When using an input cache `-XX:AOTCache=app.aot`, do not simultaneously define an output cache `-XX:AOTCacheOutput=...` in the same invocation if the version docs state the two options conflict.

Before creating a cache, check the documentation for the **exact JDK release** and run `java -version` from the **exact java executable**. Do not use `-XX:+IgnoreUnrecognizedVMOptions` to “hide” unsupported AOT flags: the application may run **without actually using the cache**.

## 5. A Java 17+ Program Used as an AOT Demo

The following code **compiles with Java 17+**, while **the AOT cache workflow must run on a supported HotSpot JDK 24/25/26**. Create the file **`AotCacheDemo.java`**:

```java
public final class AotCacheDemo {
    interface Rule {
        int apply(int value);
    }

    static final class AddOne implements Rule {
        @Override
        public int apply(int value) {
            return value + 1;
        }
    }

    static final class Twice implements Rule {
        @Override
        public int apply(int value) {
            return value * 2;
        }
    }

    private static volatile long resultSink;

    static long runScenario() {
        Rule first = new AddOne();
        Rule second = new Twice();
        long total = 0;

        for (int i = 0; i < 20_000; i++) {
            total += first.apply(i % 10);
        }
        for (int i = 0; i < 8_000; i++) {
            total += second.apply(i % 4);
        }
        resultSink = total;
        return total;
    }

    public static void main(String[] args) {
        if (args.length != 0) {
            throw new IllegalArgumentException("No arguments expected");
        }
        long answer = runScenario();
        System.out.println("application: AotCacheDemo");
        System.out.println("checksum: " + answer);
        System.out.println("ready: true");
    }
}
```

### Compiling and Packaging into a JAR

```bash
javac -encoding UTF-8 AotCacheDemo.java
jar --create --file app.jar --main-class AotCacheDemo AotCacheDemo.class
```

If the JDK `jar` tool does not support this syntax, check `jar --help` for the exact version. The **nested classes** also need to be in the JAR. The `jar` command above only adds `AotCacheDemo.class`, and **does not add** `AotCacheDemo$Rule.class`, `AotCacheDemo$AddOne.class`, and `AotCacheDemo$Twice.class` generated during compilation. Therefore, to have a **fully runnable JAR**, use the following command instead of the `jar` line just illustrated:

```bash
jar --create --file app.jar --main-class AotCacheDemo AotCacheDemo.class AotCacheDemo$Rule.class AotCacheDemo$AddOne.class AotCacheDemo$Twice.class
```

**Shell note:** the `$` character in class file names may be interpreted differently by PowerShell/bash. To avoid shell errors, replace both `jar` commands above with a **more portable command on a clean build directory**:

```bash
jar --create --file app.jar --main-class AotCacheDemo -C . .
```

**Only use `-C . .` when the working directory is clean, containing only the source/classes to be packaged and no existing JAR**; otherwise, the command may unintentionally package extra files. For the lab, a reliable approach is to put all files in a separate directory, use a single class without nested classes (see the variant below), or pass the class file names with proper shell quoting. In the subsequent AOT commands, assume you already have a **valid `app.jar` containing the required classes**; you can check with `jar --list --file app.jar`.

### Recommended Packaging Version for the Lab

To avoid relying on shell globbing/quoting, specifically in **PowerShell**, use:

```powershell
jar --create --file app.jar --main-class AotCacheDemo 'AotCacheDemo.class' 'AotCacheDemo$Rule.class' 'AotCacheDemo$AddOne.class' 'AotCacheDemo$Twice.class'
```

On **bash/sh**, use:

```bash
jar --create --file app.jar --main-class AotCacheDemo 'AotCacheDemo.class' 'AotCacheDemo$Rule.class' 'AotCacheDemo$AddOne.class' 'AotCacheDemo$Twice.class'
```

Both commands add the exact four class files; use **one** command depending on your shell, and do not run all variants consecutively to overwrite the JAR and change artifacts between training and production.

### Running Regular Java Before Doing AOT

```bash
java -cp app.jar AotCacheDemo
```

**Exact standard output printed by the application:**

```text
application: AotCacheDemo
checksum: 134000
ready: true
```

**Verifying the calculation:**

- With `i % 10` running 0..9, `AddOne` gives a sum per 10 iterations = **55**. There are 2,000 cycles in 20,000 iterations → **110,000**.
- With `i % 4` running 0..3, `Twice` gives a sum per 4 iterations = **12**. There are 2,000 cycles in 8,000 iterations → **24,000**.
- Total = **134,000**. The arithmetic result does not depend on AOT/JIT, because the cache must preserve Java semantics.

The lab uses `volatile resultSink` to keep the result with an observable effect under the Java Memory Model; **that does not force the JIT to compile the method at a specific tier**.

## 6. JDK 24: The Explicit Three-Phase Workflow

**Requirements:** HotSpot JDK 24 build supporting JEP 483, matching OS/architecture. `app.jar` compiled and created validly in section 5.

### 6.1. Record

```bash
java -XX:AOTMode=record -XX:AOTConfiguration=app.aotconfig -cp app.jar AotCacheDemo
```

In this phase **the application actually runs**, so stdout is produced:

```text
application: AotCacheDemo
checksum: 134000
ready: true
```

The JVM simultaneously writes training information to `app.aotconfig`. There may be additional logs if diagnostic options are enabled; **do not predict in advance** the timing and file size.

### 6.2. Create

```bash
java -XX:AOTMode=create -XX:AOTConfiguration=app.aotconfig -XX:AOTCache=app.aot -cp app.jar
```

The **create** phase uses the AOT configuration to generate `app.aot`. **The application `main` is not invoked** in this phase; do not expect to see the three computation stdout lines. When cache creation fails, you must fix the compatibility/input issue and **not** use an unverified output file.

### 6.3. Run with the Cache

```bash
java -XX:AOTMode=on -XX:AOTCache=app.aot -cp app.jar AotCacheDemo
```

The application must still print:

```text
application: AotCacheDemo
checksum: 134000
ready: true
```

**Distinction to make:** correct output proves the application logic **has not changed**, **not by itself** that the cache was used. `AOTMode=on` is useful for forcing the VM to check cache loadability; startup logs are also needed to verify that artifacts were used.

### 6.4. Do Not Modify the JAR Between the Three Phases

After recording, **keep `app.jar` unchanged** for assembly and production testing. Recompiling, repackaging, or changing the classpath even with the “same” source can alter file timestamps/bytes and break cache consistency conditions. If the application build changes, **delete the old cache and recreate it** on the final artifacts.

## 7. JDK 25+: The Concise Way from Training to Cache

**JEP 514** allows using `-XX:AOTCacheOutput=...` to record and assemble in one convenient invocation:

```bash
java -XX:AOTCacheOutput=app.aot -cp app.jar AotCacheDemo
```

The JVM runs the application's training workload and may launch **a second JVM** to create the cache when the record phase finishes. Therefore, “one shell command” **does not mean a single JVM process** or no additional memory usage. The resulting `app.aot` is only considered valid when the process completes successfully.

Reuse run:

```bash
java -XX:AOTMode=on -XX:AOTCache=app.aot -cp app.jar AotCacheDemo
```

This is a simple two-command workflow suitable for labs/training in a build pipeline when the runtime supports it.

### When Should You Still Use Three Phases?

- You want to separate the **training workload** from the assembly job.
- The training container has low CPU/memory, while assembly needs higher resources.
- You want to save/configure `.aotconfig` independently for inspection/tracing.
- You need clear control over build vs production artifacts.
- You want to reduce the risk of memory pressure from the assembly JVM being launched in the same command.

**Especially in containers:** in some cases the assembly JVM uses memory options equivalent to training. Do not set `-Xmx` right at the container limit and then be surprised when training + assembly OOMs. Separate the three phases or allocate an appropriate memory budget.

### JEP 515: Saving Method Profiles from Training

Starting in JDK 25, the AOT cache can store **method execution profiles** so the JIT does not have to wait for profiles to build from scratch in subsequent runs. Possible results include:

- Hot methods are identified earlier.
- C1/C2 have type/branch/call activity information from training.
- Warm-up stabilizes faster on suitable workloads.
- Some extra startup/warm-up CPU work is reduced or shifted in time.

**There is no guarantee that all hot methods are already precompiled**; the JIT still has to run and adapt if production traffic differs. Profile data does not “lock in” runtime type choices; HotSpot must preserve Java semantics via guards/fallback/deoptimization if the profile differs from reality.

## 8. JDK 26: AOT Object Cache and GCs

A notable limitation in the initial milestone of the AOT cache was support for **GC-specific AOT object caching**. Under **JEP 516 (JDK 26)**, HotSpot expands AOT object caching so it can work with **supported garbage collectors**, including ZGC, instead of the limitations present in JDK 24–25.

**Points to read carefully:**

- The main feature is improving the collector portability of the **AOT object cache** within the implementation scope; **it does not mean a JDK 25 `.aot` automatically works with JDK 26**.
- The cache is still tied to **a specific JDK release, application, and OS/CPU**; when upgrading the JDK, **regenerate** it.
- Do not infer from JEP 516 that every collector in every vendor build and architecture is supported.
- If startup reports an incompatibility, **read the reason**; do not enable `IgnoreUnrecognizedVMOptions`.

### Milestone Table to Remember

| JDK | Relevant AOT Cache Point | Inference to Avoid |
| --- | --- | --- |
| 17 | **No new JEP 483 workflow** | Do not use JDK 24–25 `AOTMode`/`AOTCacheOutput` |
| 24 | JEP 483, class loading/linking cache; explicit record/create/on | No convenient JEP 514 `AOTCacheOutput` flag |
| 25 | JEP 514 and JEP 515, concise CLI + method profiles | Method profiles do not mean the cache already contains all native methods |
| 26 | JEP 516, AOT object caching with any GC within supported scope | Caches from other JDKs are **not** automatically valid |
| Newer | Check exact docs/version and release notes | Do not treat an old table as a permanent feature catalog |

The information here is tied to **upstream OpenJDK/HotSpot milestones**. A distribution may have backports/patches; verify the **actual binary** rather than guessing solely by major version.

## 9. Does the Cache Depend on the Application and Environment?

**Yes.** Oracle JDK `java` docs state that the AOT cache depends on key dimensions:

- **Application identity**: matching classpath/JAR/module path and artifacts.
- **JDK release/build**: changing the runtime requires recreating the cache.
- **OS/CPU architecture**: do not copy caches across different platforms and assume they will run.
- **Relevant JVM options**: collectors, instrumentation/JVMTI, class loading/linking flags, or other options may be incompatible.
- **Training context**: classpath, class loaders, class initialization/linking behavior, and environment must be valid upon production reuse.

### Consistency Checklist

- [ ] Same JDK release and appropriate binary/runtime.
- [ ] Same OS/CPU architecture/ABI per version documentation.
- [ ] JAR/classpath artifacts were not rebuilt after recording.
- [ ] Important file timestamps are preserved.
- [ ] Classpath uses paths/JARs per release guidance, avoiding arbitrary wildcards/directories/nested JARs.
- [ ] Runtime classpath has a compatible relationship with the training classpath per docs.
- [ ] Java agents/JVMTI class-file transformations do not violate constraints.
- [ ] JDK options during train/create/run have no incompatibilities.
- [ ] Training covers the startup paths and methods that will actually be used.
- [ ] The AOT cache is released together with the application artifact, not reused across builds.

**Do not read the checklist as a 100% guarantee that the cache will always work:** each release has more detailed constraints; test strict mode and read the logs.

### Classpath JAR Changes Easily Make the Cache Stale

Changing a transitive dependency, adding a plugin, modifying the manifest, changing the fat JAR layout, or repackaging alters the application identity. A good build pipeline should treat `app.aot` as a **derived artifact** of **the exact `app.jar` + JDK + target platform**, not a permanent configuration file.

## 10. The Training Workload Must Be Representative Without Dangerous Side Effects

The AOT cache learns from the class/method paths exercised in the **training run**. If training only calls `--version` or prints a banner, the cache may fail to cover:

- HTTP server startup.
- Serialization/deserialization code paths.
- JSON validation and route matching.
- Dependency injection wiring.
- ORM initializations.
- Hot request processing methods.
- Branches dependent on config/feature flags.

However, training on the entire suite of integration tests indiscriminately can also cause the cache to store **test framework classes**, creating artifacts irrelevant to production.

### Designing Good Training

1. Identify the **ready/startup milestone** and the hottest workload.
2. Keep the **production classpath/JAR**.
3. Mock databases/external services when needed, while still exercising similar code paths.
4. Do not trigger real business transactions or send emails/charge cards during training.
5. Run representative smoke scenarios; avoid both “hello world only” and “stress test everything”.
6. Exercise the classes/methods that are traversed.
7. Shut down the application and let the JVM complete cache creation successfully.
8. Use that exact cache on staging and measure startup/warm-up under representative load.
9. Regenerate when application dependencies or the JDK change.

### Training Does Not “Predict” All of Production

An application with feature flags, dynamic class loading, or a plugin ecosystem may use completely new classes in production. The AOT cache does not require every future class/method to be in the cache; the JVM still has valid runtime handling paths for uncached artifacts when conditions are supported.

**Do not turn runtime class loading into a logic error** just because training never covered it. The result may be **no AOT benefit** on that path; if dynamic loading/JVMTI options break consistency, strict startup mode may reject the cache.

## 11. Verifying That the AOT Cache Is Actually Being Used

**Identical application output** is required for correctness, but is not enough to prove the cache was loaded.

On HotSpot with supported AOT logging, try:

```bash
java -XX:AOTMode=on -XX:AOTCache=app.aot -Xlog:aot,class+path=info -cp app.jar AotCacheDemo
```

Some builds may emit messages related to loaded/linked classes being reused. **Read the logs of the actual JVM**; do not hard-code a fixed stdout log pattern for every build.

### Three Comparisons

| Run | Command | Question |
| --- | --- | --- |
| **No cache** | `java -XX:AOTMode=off -cp app.jar AotCacheDemo` | Baseline running without AOT artifacts |
| **Cache, fail-fast** | `java -XX:AOTMode=on -XX:AOTCache=app.aot -cp app.jar AotCacheDemo` | Is the cache valid and loadable? |
| **Cache, logging** | `java -XX:AOTMode=on -XX:AOTCache=app.aot -Xlog:aot,class+path=info -cp app.jar AotCacheDemo` | Is there evidence the JVM reused artifacts? |

`-XX:AOTMode=on` is useful when you need strict startup failure if the cache is missing/incompatible, rather than letting default automatic behavior fall back to running without a cache. Log/option syntax must be verified on the exact release.

### Debugging When Logs Are Unclear

- Use `java -version` to confirm the exact JDK and VM name.
- Use `java -Xlog:help` to see the tags of that exact VM.
- Check errors/warnings during cache creation.
- Check the existence, read permissions, and size of the `.aot` file.
- Check cache format/magic using vendor-supported tools; **do not edit the binary manually**.
- Ensure training/create/production use the exact same app JAR/dependencies.
- Do not let the build pipeline “silently drop AOT flags on error” and then label the run “cache-enabled”.

## 12. Comparing Startup/Warm-up Fairly

AOT is often expected to reduce startup overhead, but measurements are easily noisy. To compare fairly:

- **Same** JDK vendor/build, CPU/memory quota, GC, container image.
- **Same** JAR/app arguments, classpath, config, and external dependencies.
- Choose the **no-cache baseline** using `AOTMode=off` instead of using a different JDK version.
- Run **cache-enabled** with `AOTMode=on` confirmed valid.
- Define the metric: JVM process launch → app ready, or first useful request.
- Measure **multiple cold process launches**. Avoid comparing a warm file-system cache run against a cold disk cache run.
- Keep JIT warm-up and startup work equivalent.
- Separate **elapsed startup**, **memory footprint**, **warm-up CPU**, and **steady-state throughput**.
- Report median/percentiles and dispersion, not just the best run.

### Do Not Report Guessed Measurement Results

Some official benchmarks from OpenJDK/Oracle teams may show significant improvements on specific workloads. **You cannot apply those numbers directly** to AotCacheDemo or an arbitrary web service.

Standard report example:

```text
Runtime: HotSpot JDK <measured version + build>
Application artifact: app.jar <verified digest>
No-cache command: ...
AOT-cache command: ...
Run count: <actual number of runs>
Ready-time median A/B: <measured data>
p95 startup A/B: <measured data>
CPU / RSS / heap A/B: <measured data>
Compiler/JFR differences: <observed evidence>
Conclusion: limited strictly to the measured environment/workload
```

This is a **template to be filled with real measurements**, not fixed results. Do not put these descriptive fields into the expected stdout of the Java program.

## 13. How Does AOT Cache Differ from CDS, AppCDS, and Dynamic CDS?

**Class Data Sharing (CDS)** existed before JEP 483's AOT cache and helps reuse saved class metadata via an archive. For example, HotSpot has historical flags:

```text
-Xshare:on
-XX:SharedArchiveFile=archive.jsa
-XX:ArchiveClassesAtExit=archive.jsa
```

These are **examples of HotSpot CDS options by supported version**, not commands to create a JEP 483 AOT cache. `.jsa` and `.aot` files have different workflows/semantics by release.

| Mechanism | Main Goal | Key Distinction |
| --- | --- | --- |
| CDS/AppCDS | Share a portion of class metadata/archive to reduce startup/memory | Usable on HotSpot before JDK 24 |
| Dynamic CDS archive | Create class archives in supported runs | Do not equate `.jsa` with `.aot` |
| JEP 483 AOT cache | New framework to reuse loaded/linked classes/selected objects | Has training/config/create phases |
| JEP 515 method profiling | Reuse execution profiles from training | Feeds data to JIT; not a native executable |
| GraalVM Native Image | Build a native executable with a distinct runtime | Not HotSpot's `java -XX:AOTCache=...` |

**JDK 17:** you can study CDS and classic performance tuning, but do not mislabel that mechanism as **“JEP 483 AOT cache”**. To experiment with the feature in this section, prepare a proper HotSpot JDK 24+.

## 14. AOT Cache Does Not Mean the Old Ahead-of-Time Native Compilation

Before JEP 483, HotSpot had other AOT compilation experiments. **JEP 295** introduced experimental ahead-of-time compilation (`jaotc`), and then **JEP 410** removed the experimental AOT compiler and `jaotc` from JDK 17.

These milestones are often conflated:

- **JEP 295/410:** relates to the **experimental AOT compiler/`jaotc`** removed from upstream JDK 17.
- **JEP 483:** AOT cache class loading/linking introduced in JDK 24.
- **JEP 515:** adds method profile caching starting in JDK 25.
- **GraalVM Native Image:** a different native compilation system, with a different builder and runtime.

Therefore, the statement “JDK 17 removed AOT, so Java 25 no longer has AOT cache” is **wrong because it confuses two different features**. Conversely, “Java 25 has AOT cache so `jaotc` is back” is also incorrect.

## 15. Startup Optimizations Do Not Change Class Initialization Rules

AOT class linking is not allowed to arbitrarily alter observable Java semantics regarding:

- Class initialization when required by active use.
- Proper `<clinit>` ordering.
- Exceptions from static initializers.
- Runtime/linkage errors.
- Thread synchronization of class initialization.
- Reflection/dynamic loading under supported conditions.

Example:

```java
final class InitDemo {
    static {
        System.out.println("class initialization");
    }

    static void run() {
        System.out.println("run");
    }
}
```

This is a class snippet, **without `main` yet**. AOT optimization has no right to print the string “class initialization” at an arbitrary time that alters the required observable behavior of Java code. Preparing artifacts ahead of runtime may only be done within the compatibility boundaries guaranteed by HotSpot.

### Distinguishing Load/Link from Initialize

A class can be **loaded/linked** before it is actually **initialized**. The AOT cache helps prepare eligible portions of work but must not equate “already in cache” with “static initializers have already run for the production process”.

**Do not use the AOT cache to work around bugs in static initializers.** If a class initializes incorrectly/fails in the application, the cache does not make the logic bug valid.

## 16. Dynamic Classes, Agents, and Instrumentation

Some applications load classes or modify class bytes at runtime:

- Java agents/bytecode instrumentation.
- Application server class loaders.
- Dependency injection proxies.
- Dynamic proxies / hidden classes.
- Hot-reload/redefinition tools.
- Custom class loaders.
- Plugin frameworks.

That does not mean all such applications cannot benefit from AOT. However, **certain JVMTI operations**, especially agents that modify the bootstrap/system classloader search path, may be incompatible with a pre-linked cache.

### What to Check When Using an Agent?

1. Which agents run in training and production?
2. Do they transform class bytes?
3. Do they add to the bootstrap/system class loader search path?
4. Did agent version/options change?
5. Does `AOTMode=on` accept this configuration?
6. Are dynamic classes exercised and reused?
7. If the cache is rejected, can optimization be disabled or training/config adjusted per docs while preserving correctness?

**Do not** solve this by forcing monitoring/security agents off in production without evaluating operational requirements. Performance optimization must fit real-world instrumentation and security.

## 17. Symptoms and Diagnosis

| Symptom | Possible Cause | Check |
| --- | --- | --- |
| `Unrecognized VM option 'AOTMode'` | JDK too old or non-HotSpot JVM | `java -version`, release/build docs |
| `AOTCacheOutput` not recognized on JDK 24 | JEP 514 is a JDK 25 feature | Use record/create on JDK 24 |
| `app.aot` does not exist | Training/assembly incomplete, wrong path/permission | Exit code, filenames, logs |
| Cache fails to load in `on` mode | Incompatible JDK/app/OS/CPU/flags | Read error details, compare artifacts |
| Runs but no faster | Shallow training, app too small, or bottleneck not in load/link/profile | JFR/class logs and multiple benchmarks |
| Same JAR name but stale cache | Rebuilt JAR, changed dependencies, different timestamps/bytes | File digests and build pipeline |
| AOT assembly OOM | Second JVM consumes memory, low container quota | Memory limit, separate phases |
| Running AOT on ZGC JDK 25 hits limits | JEP 516 arrives in JDK 26 | Check release and collector support |
| App output differs with cache | Correctness/config issue or app non-determinism | Reproduce, compare flags/config, file bug if needed |
| `-Xlog:aot` does not produce expected events | Different tag/level, cache not reused, logging config | `-Xlog:help`, startup flags, strict mode |
| First request still slow | DB/network/framework init not covered, JIT still warming up | Request tracing/JFR, training profile |
| RAM/RSS increases | Cache mapping/assembly overhead, config/runtime memory | OS metrics, NMT, compare same windows |

### Errors Are Not Always “JVM Does Not Support It”

A flag that is **recognized** but rejected by the VM due to **class path mismatch** is different from a flag **not built into the JVM**. Record the exact error and classify **availability vs compatibility vs effectiveness** before choosing a fix.

### Auto Mode and Dangerous Silence

`AOTMode=auto` may run the application **without using the cache** if a cache cannot be loaded in permitted cases. In CI/benchmarks where you want to prove the cache works, use **on** mode and read the logs. **Do not conclude “because `-XX:AOTCache=...` is on the command line, the cache was definitely used”.**

## 18. Operational Pitfalls When Packaging the Cache

### Do Not Bundle `.aot` into a Container Image of a Different Build

A cache created with JDK build A and copied into image B with a different JDK may no longer be valid. The right way: build **application artifact + AOT cache** for the specific target release/platform, store manifest metadata, and release them versioned together.

### Do Not Modify the JAR After Training

Even changing a timestamp or repackaging can cause the JVM to treat classpath artifacts as mismatched. In a release pipeline:

```text
Compile source
    ↓
Package immutable app.jar
    ↓
Train → assemble app.aot (same immutable app.jar)
    ↓
Validate strict AOT on staging
    ↓
Publish app.jar + app.aot + manifest
    ↓
Deploy both with matching JDK runtime image
```

**Every time source/dependencies/JDK change**, you should regenerate the cache. If targets have multiple OS/CPU architectures, build/verify artifacts appropriate for each target rather than assuming `app.aot` is a portable binary.

### The AOT Cache Is an Artifact That Must Be Protected

The cache file contains information about classes/metadata/runtime artifacts and is not public by default. It needs file permissions, checksum/digest, provenance, artifact signing/policy when required by the organization, and access control over who can modify it.

Do not upload `.aot` or training logs containing sensitive content to public repositories just for debugging. When logging/cache configs contain user information, apply appropriate retention/security policies.

## 19. Training in Tests vs Production

### Training with Integration/Smoke Tests

Pros:

- Can be run in CI without accessing the production database.
- Easy to repeat, record artifacts, and set quality gates.
- Can test several representative startup/request paths.

Limitations:

- Test-only classes bloat the cache without helping production.
- Mocked paths do not cover actual production hot methods.
- Synthetic traffic differs in receiver type/request distribution.
- Some integrations are hard to reproduce accurately.

### Training Under Production-Like Workload

Pros:

- Can observe class/method paths close to reality.
- Suitable for applications with dynamic initialization.

Limitations:

- Risks business side effects and sensitive resources.
- Hard to pin classpath/environment during rolling deployments.
- Cache output must be transferred safely to the build/deploy flow.
- Time windows may miss hot paths from other times of day.

**Recommendation:** prefer isolated, repeatable training that reflects production; if training only in production, strict policies are needed for side effects, data, security, and artifact promotion. Do not think of training as “just run the app once arbitrarily”.

## 20. A/B Experiment: Cache as the Only Variable

A proper experiment should compare:

**A — no cache:**

```bash
java -XX:AOTMode=off -cp app.jar AotCacheDemo
```

**B — strict AOT cache:**

```bash
java -XX:AOTMode=on -XX:AOTCache=app.aot -cp app.jar AotCacheDemo
```

Both commands use the **same JDK**, app JAR, OS/CPU, GC/heap, input, and environment. In this small example, **stdout must match** in both A and B when supported.

### Collecting Meaningful Metrics

- Process elapsed startup to the `ready: true` line, if using that marker as a proxy.
- Time to first request ready in a real server application.
- Compiler/class loading CPU during warm-up.
- Number of class loads, JFR events, compilation events.
- Heap committed/used, process RSS, memory maps of the cache.
- Number of runs, median/p95, and variability.
- Error rates and output correctness.
- Cache artifact size vs savings.

**Do not use a single run** of `time java ...` to claim “AOT reduces startup by 40%”; filesystem cache, OS scheduler, JIT, entropy, and process launch overhead all vary.

### Performance Can Improve on One Metric and Worsen on Another

Caching can improve startup while increasing storage footprint or memory mapping overhead. Cache assembly also consumes CPU/RAM during the build stage. If an application runs continuously for a long time, startup benefit may not be the primary KPI.

**The choice depends on the use case:** batch jobs, CLIs, serverless cold starts, and autoscaled services often care about startup; systems with months of uptime may prioritize steady-state throughput/latency.

## 21. Debugging Experience from Program Output

You should separate at least three types of output:

1. **Java application stdout:** the `application`, `checksum`, `ready` lines; in the demo these have fixed expected values.
2. **JVM AOT/GC/class loading logs:** format/timing/files vary by JDK and flags; **do not write fixed expected stdout** for them.
3. **Timing/benchmark metrics:** belong to the measurement environment; not a Java language contract.

A proper report can be written as:

```text
Functional QA: PASS
  application=AotCacheDemo
  checksum=134000
  ready=true

AOT startup validation: PASS/FAIL per strict mode + actual logs
  JVM vendor/version/build: recorded from actual machine
  AOT cache path/digest: recorded from actual build
  Classpath/JAR digest: recorded from actual build

Startup performance:
  Runs A/B: actual measurements
  Median, p95, variation: actual measurements
  Conclusion: limited to measured workload/target
```

**This is an experimental recording template, not a report of actually measured results.** Each status needs specific logs/evidence if used to decide a rollout.

## 22. Common Misconceptions

| Misconception | Correct Understanding |
| --- | --- |
| “HotSpot AOT cache was already in Java 17.” | JEP 483 starts in JDK 24 upstream |
| “`jaotc` exists on JDK 25 because AOT cache exists.” | Experimental `jaotc` was removed in JDK 17 |
| “AOT cache means the whole app becomes a native executable.” | `.aot` are artifacts for the HotSpot JVM, not an executable |
| “JEP 515 packages all compiled C2 methods.” | Method profiles are reused so JIT optimizes earlier |
| “Training only needs `java -version`.” | Training must run real application code paths |
| “When the app build changes, the old cache still works.” | Regenerate per application/JDK/platform constraints |
| “`AOTMode=auto` always guarantees the cache is loaded.” | There are cases where the VM runs without using the cache |
| “`AOTCacheOutput` works on JDK 24.” | This ergonomic flag is from JDK 25 |
| “A JDK 25 cache works directly on JDK 26.” | Caches are release-specific and must be recreated |
| “Using a cache skips static initialization.” | Java class-init semantics are still preserved |
| “The cache contains all runtime objects and app secrets.” | Only artifacts permitted by the JVM are cached |
| “Changing the JVM GC always keeps the cache compatible.” | Compatibility depends on JDK/GC and options; JEP 516 expands JDK 26 |
| “The JAR only needs the same filename.” | Artifact contents/timestamps/classpath consistency must match |
| “JVM printing the right checksum proves the cache loaded.” | Must use strict mode/logs |
| “Training with as many test frameworks as possible is better.” | Adding unused classes can bloat the cache |
| “AOT definitely increases post-warm-up throughput.” | Primarily targets startup/warm-up; must be measured |
| “One `.aot` works identically on Windows/Linux/ARM.” | No, caches are platform-specific |
| “Missing AOT file error means Java code is wrong.” | Could be output path/permission/assembly failed |
| “One output command uses no extra memory.” | JDK 25 may launch another assembly JVM |
| “Just enable AOT flags on OpenJ9 and it works.” | HotSpot-specific; verify the implementation |
| “Having a Java agent means AOT always works.” | Some JVMTI classloader changes are incompatible |
| “CDS `.jsa` and JEP 483 `.aot` are the same file format.” | Different mechanisms/workflows by release |

## 23. Self-Check Exercises

**Exercise 1.** Which JDK milestone has JEP 483 AOT cache class loading/linking?  
**Answer:** **JDK 24**.

**Exercise 2.** What does JDK 25 add for AOT?  
**Answer:** JEP 514 (ergonomic `AOTCacheOutput`) and JEP 515 (method profiling).

**Exercise 3.** What GC-related improvement does JDK 26 have?  
**Answer:** JEP 516 expands AOT object caching to supported GCs, including ZGC.

**Exercise 4.** Why can `-XX:AOTMode=record` fail on JDK 17?  
**Answer:** JEP 483 does not exist in standard JDK 17; the new flags are unrecognized.

**Exercise 5.** What are the three AOT phases?  
**Answer:** Training/record → assembly/create → production/on.

**Exercise 6.** When `create` mode runs, does application `main` need to run again to compute the checksum?  
**Answer:** No. Assembly reads the configuration and creates the cache; application `main` does not run in this phase.

**Exercise 7.** How does `AOTCacheOutput` differ from explicit record/create?  
**Answer:** Starting in JDK 25, the JVM conveniently performs record and assemble from a single invocation, potentially using a secondary JVM to assemble.

**Exercise 8.** Can a JDK 25 cache still be used after upgrading to JDK 26?  
**Answer:** Not by default; it must be regenerated for the new JDK release/build and environment.

**Exercise 9.** Training only hits one endpoint, while production has ten endpoints. What limitation might occur?  
**Answer:** Classes/method profiles do not cover the remaining paths, reducing AOT benefits.

**Exercise 10.** Does the cache change `static` initializer observable Java semantics?  
**Answer:** It must not; HotSpot must keep class loading/linking/initialization rules valid.

**Exercise 11.** Is an AOT cache a native executable used instead of `java`?  
**Answer:** No. It is a cache for the JVM, unlike GraalVM Native Image.

**Exercise 12.** With JDK 25 AOT profiles, does the JIT still run after startup?  
**Answer:** Yes. Cached profiles help the JIT make decisions earlier, without guaranteeing all native code is pre-built.

**Exercise 13.** What checksum does AotCacheDemo print?  
**Answer:** **134000**, the sum of 110000 from AddOne and 24000 from Twice.

**Exercise 14.** To fail fast when the cache is missing, what do you use?  
**Answer:** `-XX:AOTMode=on` combined with the `-XX:AOTCache=...` path on a supported JVM, then check startup exit/logs.

**Exercise 15.** Same JAR filename, but a dependency was rebuilt; should you keep `.aot`?  
**Answer:** No; regenerate it, do not just compare filenames.

**Exercise 16.** Can a cache created on x86-64 Linux be used directly on AArch64 Windows?  
**Answer:** Not by default; different OS/CPU makes the cache incompatible.

**Exercise 17.** There is a Java agent modifying classloading paths; what must you do?  
**Answer:** Verify JVMTI constraints and strict startup on the actual build/agent config.

**Exercise 18.** Cache is enabled, but p99 does not drop; is there a bug?  
**Answer:** Inconclusive. AOT targets startup/warm-up; p99 may be dominated by DB/I/O/locks/GC.

**Exercise 19.** Does running `java -Xlog:aot,class+path=info` prove the entire cache is valid?  
**Answer:** It only helps observe events; it must be combined with strict mode, matching artifacts, successful startup, and measurement.

**Exercise 20.** Why shouldn't you use `-XX:+IgnoreUnrecognizedVMOptions` to “guarantee deployments always run”?  
**Answer:** It can silently ignore the AOT flag; the service runs, but benchmarks/operational expectations are wrong.

**Exercise 21.** Is training that loads the entire test framework beneficial?  
**Answer:** Not necessarily; it can increase unused classes/cache size and reduce effectiveness.

**Exercise 22.** Can you copy a cache from staging to production?  
**Answer:** Only when the application, JDK, OS/CPU, and compatibility constraints match, the artifact is managed securely, and strict verification passes.

**Exercise 23.** An old cache encounters an error; should you manually edit `.aot` bytes with a hex editor?  
**Answer:** No. It is a VM-derived binary artifact; find the root cause and regenerate on the proper build.

**Exercise 24.** For a startup benchmark aiming to attribute AOT benefits, what should you compare?  
**Answer:** Same JDK/app/workload/heap/CPU, comparing `AOTMode=off` vs `AOTMode=on`, multiple cold-process runs, and cache verification logs.

## 24. End-of-Lesson Practical Checklist

- [ ] Used a suitable **HotSpot JDK 24+**, not mistaking it for JDK 17?
- [ ] Know exactly which release supports **JEP 483 / 514 / 515 / 516**?
- [ ] Compiled the Java code and created a JAR containing all required classes?
- [ ] Checked `jar --list --file app.jar` before training?
- [ ] Kept the app JAR immutable between record, create, and run?
- [ ] Did training exercise representative startup/hot paths?
- [ ] No real business side effects executed during training?
- [ ] `.aotconfig`/`.aot` written completely, with read/write permissions and sufficient disk space?
- [ ] When using `AOTCacheOutput`, budgeted memory for the assembly JVM?
- [ ] Production test uses `AOTMode=on` to detect cache mismatches clearly?
- [ ] Checked `-Xlog:aot,class+path=info` and `java -Xlog:help` on the exact release?
- [ ] Verified application output preserves exact meaning with and without the cache?
- [ ] Did not copy the cache across different OS/CPU/JDK releases?
- [ ] Checked agent/JVMTI/classpath/GC constraints?
- [ ] Regenerated the cache if source/dependencies/JDK changed?
- [ ] Measured A/B startup/warm-up multiple times with the same CPU/heap/GC?
- [ ] Reported limitations and work not covered in training?
- [ ] Managed provenance, digest, and security of the cache file?
- [ ] Distinguished JEP 483 AOT cache from CDS `.jsa`, `jaotc`, and GraalVM Native Image?

## 25. Conclusion

**HotSpot AOT cache is a learning and reuse mechanism, not a magic wand that compiles all of Java into a native binary.** Starting in JDK 24, the JVM can observe a training run, build loading/linking artifacts, and reuse them at startup. JDK 25 makes the workflow more convenient and adds method profiles for earlier JIT warm-up. JDK 26 expands object caching support across GCs.

To operate it properly:

```text
Immutable application artifact + matching HotSpot release
              │
              ▼
Representative training run
              │
              ▼
AOT configuration / cache assembly
              │
              ▼
Strict cache validation on target
              │
              ▼
Production startup using verified cache
              │
              ▼
A/B benchmark startup + warm-up + memory
              │
              ▼
Regenerate cache on every build/JDK/OS/CPU change
```

**Focus on what can be proven:** correct application functionality, cache file created successfully, HotSpot actually loads it, and startup/warm-up results measured in a representative environment. Do not promise a fixed speedup, do not bypass consistency constraints, and do not use flags from a newer JDK on an unsupported runtime.

### Primary References

1. **OpenJDK JEP 483 — Ahead-of-Time Class Loading & Linking (JDK 24):** https://openjdk.org/jeps/483
2. **OpenJDK JEP 514 — Ahead-of-Time Command-Line Ergonomics (JDK 25):** https://openjdk.org/jeps/514
3. **OpenJDK JEP 515 — Ahead-of-Time Method Profiling (JDK 25):** https://openjdk.org/jeps/515
4. **OpenJDK JEP 516 — Ahead-of-Time Object Caching with Any GC (JDK 26):** https://openjdk.org/jeps/516
5. **Oracle JDK 24 — `java` command and AOT cache options:** https://docs.oracle.com/en/java/javase/24/docs/specs/man/java.html
6. **Oracle JDK 25 — `java` command, `AOTCacheOutput`, `AOTMode`:** https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html
7. **Oracle JDK 26 — `java` command, AOT cache mode/compatibility:** https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html
8. **Inside Java (Oracle, 2026) — Run Into the New Year with Java’s AOT Cache Optimizations:** https://inside.java/2026/01/09/run-aot-cache/
9. **OpenJDK JEP 410 — Remove the Experimental AOT and JIT Compiler:** https://openjdk.org/jeps/410
10. **OpenJDK Project Leyden:** https://openjdk.org/projects/leyden/

**Remember:** a configuration is properly evaluated when recording **JDK version + application digest + OS/CPU + training coverage + strict AOT reuse evidence + A/B metrics**, not merely because a file named `app.aot` sits on disk.
