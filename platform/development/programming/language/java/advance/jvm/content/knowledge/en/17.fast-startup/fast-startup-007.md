# Distinguishing JVM AOT Cache from Compiling to a Native Program

## 1. Why are both approaches called “AOT”?

In Java, **Ahead-of-Time (AOT)** broadly means *preparing certain information or executable code in advance* instead of waiting until the application needs them. However, **AOT is not the name of a single file format**, and the phrase “AOT-compiled” is not enough to tell whether an application **needs a JVM to run or not**.

Two mechanisms to distinguish in this article:

1. **JVM AOT cache (HotSpot / Project Leyden):** runs the Java application on a **normal JVM**, but uses data pre-recorded from preparation/training runs. On **JDK 25**, the AOT cache can store class-loading/linking data, eligible objects, and **method profiles** to improve startup/warmup. The application still runs via `java`, uses the JVM runtime, garbage collector, and can use the **JIT compiler**.
2. **Native executable (e.g., GraalVM Native Image):** uses a build tool to analyze bytecode, determine the required components, and **compile the program into a native executable file** for an OS/CPU target. When deployed, the `app-native` / `app-native.exe` file is usually run **directly**, without starting HotSpot with the `java -jar ...` command. The executable still contains **the necessary parts of the Java runtime**, rather than Java semantics disappearing.

**One sentence to remember:** AOT cache = **preparing the JVM to run the application more efficiently**; Native Image = **compiling and packaging the application into a native executable**. Both approaches can improve startup, but they differ in **artifact, runtime, dynamic capabilities, build cost, portability, and subsequent optimization mechanisms**.

### Important warning about naming

- A `.aot` file from HotSpot JDK 25 is **not** a directly runnable native program.
- A `.jsa` file from CDS/AppCDS is also **not** a native executable.
- Normal `.class` and `.jar` files contain **Java bytecode**, not a native binary.
- The `native-image` tool in GraalVM is **not** a synonymous option for HotSpot's `-XX:AOTCacheOutput`.
- The word “AOT” in **Spring AOT processing** usually refers to code generation/analysis serving deployment paths, and does **not automatically** produce a native executable if a Native Image build has not been run.

## 2. Three paths from Java source to a running program

### 2.1. Regular Java/JVM

~~~text
StartupCompare.java
      |
      | javac
      v
StartupCompare.class   ->  startup-compare.jar
      |
      | java -jar startup-compare.jar
      v
HotSpot JVM
  - load/link/init classes according to Java rules
  - interpreter executes bytecode
  - profiling/JIT compile hot code when appropriate
  - GC and Java runtime active
      |
      v
Application result
~~~

In this mode, code can transition from the interpreter to C1/C2 (or another compiler depending on configuration), and then to native machine code **generated at runtime**. JIT compilation does not change the original `.jar` format.

### 2.2. JVM with AOT cache

~~~text
Build Java classes/JAR
      |
      v
JDK 25 training run (real Java application)
      |
      | record eligible classes, metadata, method profiles
      v
AOT configuration/training information
      |
      | assembly
      v
startup-compare.aot   (AOT cache artifact)
      |
      | java -XX:AOTCache=startup-compare.aot -jar ...
      v
HotSpot JVM still runs:
  - reads/maps compatible AOT cache
  - reuses eligible classes/linking/profiles data
  - interpreter/JIT still play a role at runtime
  - GC and Java runtime still play a role
      |
      v
Application result
~~~

**The cache does not replace the JVM**. It gives the VM “pre-prepared work” in advance; the application, JVM, and JDK must still be compatible with the cache.

### 2.3. Native Image

~~~text
Build Java classes/JAR
      |
      | native-image tool
      v
Reachability analysis (closed-world model)
  - determine reachable classes/methods/fields
  - process metadata for reflection/resources/JNI when needed
  - class initialization decisions
      |
      v
Ahead-of-time compilation + native linking
      |
      v
startup-compare-native[.exe]
  - application native code
  - necessary parts of Java runtime
  - corresponding GC/threading/safepoint support
      |
      | run executable directly
      v
Application result
~~~

**Native Image does not mean “no runtime left”.** The native executable still has logic/runtime supporting memory management, class metadata, and threading according to the Native Image mechanism; it simply **does not need to start a traditional HotSpot JVM** to execute the program in the `java -jar` manner.

## 3. Core comparison table

| Characteristic | HotSpot JVM + AOT cache | GraalVM Native Image |
| --- | --- | --- |
| Optimized artifact | `.aot` (and possibly `.aotconfig` in a split-step workflow) | Native executable such as `app-native`, `app-native.exe` |
| How to run | `java -XX:AOTCache=... -jar app.jar` | `./app-native` or `.\app-native.exe` |
| Does it run HotSpot JVM? | **Yes** | **No**, uses an embedded/linked runtime for Native Image |
| Needs a compatible JDK/JRE at runtime? | **Yes**, matching JVM and classpath/module state | Usually does not need a full JVM/JDK on the deployment machine; still has OS/native library requirements |
| Pre-build input | Java bytecode and a trial run of the application | Java bytecode, dependency graph, reachability metadata |
| How AOT works | Training and storing artifacts to help JVM startup/warmup | Whole-program reachability + ahead-of-time code generation/linking |
| Java JIT at runtime? | **Can still use** JIT; JDK 25 cache profiles help JIT optimize earlier | Does not use traditional HotSpot tiered JIT for the compiled application |
| Dynamic class loading | Normal JVM semantics, subject to cache usage conditions | Follows the **closed-world assumption**; code needs to be known at build time |
| Reflection/proxy/resources | Flexible JVM behavior like a normal application, with cache constraints | May require reachability metadata/configuration |
| Class initialization | Runtime semantics are preserved according to JVM rules | Distinguishes between **build-time** and **run-time initialization** |
| Compatibility | App/JDK release/OS/CPU must be compatible with the cache | Native binary depends on OS/CPU and required runtime native libraries |
| Build overhead | Training + assembly; can use a convenient single flag in JDK 25 | Static analysis and native linking typically consume significant CPU/RAM/build time |
| Main benefit | Reduces Java VM startup/warmup with minimal changes to the application model | Shortens startup, reduces runtime footprint, and removes traditional JVM requirement |
| Changing dependencies after build | Cache usually must be regenerated, app JAR remains the runtime input | Must **rebuild native executable** |
| Tooling | `java`, `jcmd`, JFR, HotSpot `-Xlog` depending on version | Native Image runtime/tooling and appropriate platform profiler |
| Post-deploy tunability | JVM flags/GC/JIT continue to apply, depending on compatibility | Options/native runtime have a different supported set and behavior; do not mechanically apply all HotSpot flags |

**Do not claim that Native Image is always faster than every JVM+AOT workload.** Native can excel at cold start; Java HotSpot JIT still has strengths in runtime optimization for some long-running workloads, especially when receiving many new runtime profiles. Conclusions must be based on actual metrics.

## 4. What does JDK 25's AOT cache store?

According to the Oracle JDK 25 `java` launcher manual and the JEPs under Project Leyden, the AOT cache is developed to shift some work from **production startup** to **training/assembly**.

### Foundation from CDS

**Class Data Sharing (CDS)** historically stored pre-processed class metadata in an archive, typically with the `.jsa` extension. Archived classes can be mapped into subsequent JVM processes, reducing class-loading work and sometimes reducing footprint through memory-mapped shared pages.

The AOT cache from JDK 24 extends this direction. Oracle JDK 25 describes the AOT cache as a container for artifacts capable of helping startup/warmup: processed classes, class loading/linking data, and eligible objects. **Do not treat the AOT cache as a full heap snapshot** of the entire app, nor as a new JAR.

### JEP 483: Ahead-of-Time Class Loading & Linking

**JEP 483 (JDK 24)** introduced the **training → assembly → production** workflow to record/store a portion of eligible class loading/linking state. The production JVM uses this prepared data if compatibility checks allow.

**Do not misunderstand** this as pre-executing all of `main`, saving all sockets/database connections, or restoring a process as if from a full OS process checkpoint.

### JEP 515: Ahead-of-Time Method Profiling

**JEP 515 (JDK 25)** brings method profiles collected during training into the AOT cache. When the JVM starts, these profiles help the JIT begin optimizing with better information **instead of having to wait to collect all new profiles from a cold runtime**.

**Point to distinguish:** Storing **JIT profiles** in `.aot` is not equivalent to storing a **native executable**. The JIT can still generate machine code **during production runtime**. This differs from Native Image, which AOT-compiles reachable application code into a binary at build time.

Some historical documentation pages may still describe “compiled methods and execution profiles will be stored in the cache in the future”. Cross-check the JDK release and **JEP 515**: JDK 25 already has **AOT Method Profiling**, but **that does not make the cache a Native Image executable**.

### JEP 514: AOT Command-Line Ergonomics

JDK 25 simplifies cache creation via `-XX:AOTCacheOutput=...`, allowing a single command to perform **training** and then launch the appropriate assembly phase to generate the cache. The documentation still describes the split **record/create/on** workflow for detailed automation.

## 5. JVM AOT cache artifacts

| Artifact | Role | Directly runnable? |
| --- | --- | --- |
| `.java` | Java source | Not a native executable |
| `.class` | JVM bytecode | Uses appropriate Java launcher/JVM |
| `.jar` | Packages classes/resources | Typically uses `java -jar` |
| `.classlist` | Class list for traditional CDS workflow | No |
| `.jsa` | CDS/AppCDS archive | **No**, used with JVM |
| `.aotconfig` | Configuration/training data of JDK 25 AOT workflow | **No** |
| `.aot` | Standard AOT artifacts cache on JDK 25 | **No**, JVM reads via `-XX:AOTCache` |
| `app-native` / `app-native.exe` | Native Image executable for target OS/CPU | **Yes**, runs directly when native runtime dependencies are satisfied |

Do not change the extension from `.aot` to `.exe` to turn it into a program. Also do not say `.aot` is a file containing complete CPU instructions to omit HotSpot.

## 6. Java 17+ program used to compare the two approaches

Create the file **`StartupCompare.java`**:

~~~java
public final class StartupCompare {
    private StartupCompare() {
    }

    static int sumTo(int n) {
        int sum = 0;
        for (int i = 1; i <= n; i++) {
            sum += i;
        }
        return sum;
    }

    static String message(String name) {
        return "Hello, " + name;
    }

    public static void main(String[] args) {
        System.out.println("message=" + message("AOT"));
        System.out.println("sum=" + sumTo(10));
    }
}
~~~

The program **needs no external libraries**, has no file/network I/O, does not depend on time, and does not use non-deterministic random or thread scheduling.

Compile with **Java 17+**:

~~~bash
javac -g StartupCompare.java
java StartupCompare
~~~

**Deterministic stdout on successful run, without VM diagnostic logs enabled:**

~~~text
message=Hello, AOT
sum=55
~~~

Because `sumTo(10)` adds `1+2+...+10 = 55`. This value remains the same when run with HotSpot without cache, HotSpot with cache, or a successfully compiled Native Image.

### Packaging a JAR for AOT cache experiments

Create a clean directory for artifacts, if you want to avoid using the class directory in subsequent commands.

**Linux/macOS or PowerShell (these Java/JAR commands work on both):**

~~~bash
javac -d classes StartupCompare.java
jar --create --file startup-compare.jar --main-class StartupCompare -C classes .
java -jar startup-compare.jar
~~~

**Beforehand, create the `classes` directory**:

- Linux/macOS: run `mkdir -p classes`.
- Windows PowerShell: run `New-Item -ItemType Directory -Force classes | Out-Null`.

The program output is still the two lines above. Inside the JAR are `StartupCompare.class` and a manifest specifying `Main-Class`. **Keep the JAR bytes unchanged** during cache creation/usage to avoid mismatches.

**Note:** the `javac -d classes` command requires the `classes` directory to exist; creating the directory is a mandatory part of the lab, not an assumption that the tool creates the root directory automatically.

## 7. Lab A — creating an AOT cache on HotSpot JDK 25

The commands in this section require **HotSpot JDK 25** or another JVM/JDK that fully documents the same options. **They do not run on JDK 17 just because the Java source code is Java 17 compatible.**

### Step A1. Confirm the running JDK

~~~bash
java -version
java -Xlog:help
~~~

Verify that the output shows **JDK 25 HotSpot**. If a system has multiple `java`/`javac` executables on PATH, you must clarify which JDK is used to create `.aot` and which JVM will use the cache at runtime.

**Do not try to enable AOT flags on Java 17 and conclude the feature is broken** when the JVM reports `Unrecognized VM option`. JDK 17 has CDS/AppCDS but does not have this JDK 25 AOT Cache workflow.

### Step A2. Run baseline without AOT cache

~~~bash
java -XX:AOTMode=off -jar startup-compare.jar
~~~

**Application stdout:**

~~~text
message=Hello, AOT
sum=55
~~~

`-XX:AOTMode=off` disables AOT cache usage according to Oracle JDK 25 semantics. To compare performance, multiple process starts need to be measured separately; this step only establishes a functional baseline.

### Step A3. Training + assembly in a single command

~~~bash
java -XX:AOTCacheOutput=startup-compare.aot -jar startup-compare.jar
~~~

In JDK 25, the default `AOTMode=auto` combined with `AOTCacheOutput` performs a **training execution** and an appropriate **assembly JVM process** to write artifacts. **Do not interpret this command as “compiled the JAR into a native exe”.**

The application output from the training run is still:

~~~text
message=Hello, AOT
sum=55
~~~

JVM diagnostic/build messages (if any) may appear alongside those two lines. After the command, check the artifact:

**Linux/macOS:**

~~~bash
ls -lh startup-compare.aot
~~~

**Windows PowerShell:**

~~~powershell
Get-Item .\startup-compare.aot
~~~

If the file is not created, check the exit code/logs and compatibility of VM flags; do not jump straight to concluding that a valid cache exists.

### Step A4. Run the application again with the cache

~~~bash
java -XX:AOTCache=startup-compare.aot -jar startup-compare.jar
~~~

**Application stdout is still:**

~~~text
message=Hello, AOT
sum=55
~~~

This is a **production run of the JVM**, not running the `startup-compare.aot` file directly.

### Step A5. Confirm the JVM is using the AOT cache

~~~bash
java -XX:AOTCache=startup-compare.aot -Xlog:aot=info -jar startup-compare.jar
~~~

At this point, the VM may print **AOT diagnostic logs** related to the cache. Check the information about **cache load / mapping / validation / rejection** that the actual JDK outputs; log format, exact text, and timing vary by release/build. To see valid tags/levels, use `java -Xlog:help`.

**Important:** a `.aot` file existing on disk **does not prove** that the runtime successfully mapped/read it. In automatic mode, the JVM may fall back or not use it because the cache is incompatible.

### Step A6. Strict verification in a test environment

~~~bash
java -XX:AOTMode=on -XX:AOTCache=startup-compare.aot -Xlog:aot=info -jar startup-compare.jar
~~~

`AOTMode=on` is the mode that requires using the AOT cache per the options; it is useful when diagnosing compatibility errors. **Do not use strict mode blindly in production**: if the cache is missing/invalid, the JVM may exit instead of falling back.

If the JVM rejects the cache, **do not report the experiment as successful just because the app still runs in another mode**. Read the AOT logs and confirm the correct path/JDK/JAR/options.

## 8. Separate three-stage workflow on JDK 25

Oracle documentation also defines the **`record` → `create` → `on`** modes to explicitly control each step.

### Training / record

~~~bash
java -XX:AOTMode=record -XX:AOTConfiguration=startup-compare.aotconfig -jar startup-compare.jar
~~~

The process runs the program to record appropriate statistics/configuration data. The `startup-compare.aotconfig` file is **not** a program and is **not yet** the final `.aot`.

### Assembly / create

~~~bash
java -XX:AOTMode=create -XX:AOTConfiguration=startup-compare.aotconfig -XX:AOTCache=startup-compare.aot -jar startup-compare.jar
~~~

According to Oracle JDK 25, **create mode performs assembly, not running the application's `main`**. If the operation succeeds, it creates `startup-compare.aot`.

### Production / on

~~~bash
java -XX:AOTMode=on -XX:AOTCache=startup-compare.aot -jar startup-compare.jar
~~~

The application runs on **HotSpot JVM with the cache**. Splitting into three stages is suitable for build pipelines, image builds, and deployment.

### Do not arbitrarily mix AOT options

Oracle JDK 25 sets constraints:

- `-XX:AOTCacheOutput=...` is an output option and must not be used simultaneously with `-XX:AOTCache=...`.
- `-XX:AOTConfiguration=...` is written in `record` and read in `create` depending on the mode.
- `-XX:AOTMode=off` ignores the cache; default `auto` decides record/on/off based on options.
- `-XX:AOTMode=create` does not mean invoking native-image; it only **assembles the cache**.
- The AOT cache requires **app/JDK/OS/CPU compatibility**.

**If the create step reports an error, keep the training data intact and read the logs**; do not tweak flags until “there are no errors” and then claim it is still the same experiment.

## 9. Incompatible cache: an important practical limitation

According to Oracle JDK 25, an AOT cache is an artifact for a specific combination:

1. **The application** as represented via `-classpath`, `-jar`, or `--module-path` and code/resources.
2. **A matching JDK release/build**.
3. **OS and CPU architecture**.

If any of these components change, you must **recreate the AOT cache**. Certain JVM options, JVMTI agents, or other runtime conditions may prevent the cache from being used. Do not assume an archive works on every node just because it has the same filename.

| Change after training | Recommended action |
| --- | --- |
| Change JDK 25 build/release | Recreate cache |
| Rebuild JAR/dependency | Recreate cache |
| Change architecture x86-64 ↔ ARM64 | Recreate cache |
| Switch OS Windows ↔ Linux | Recreate cache |
| Add agent/VM options affecting loading | Check compatibility; may need to recreate |
| Production workload differs heavily from training | Cache may lack useful profiles/classes; retrain |
| Change JVM vendor | Check option support, do not assume portable |

**Do not treat `.aot` as an independent artifact equivalent to a source JAR.** Build/release pipelines should manage **the cache together with the JDK/container image and application version**, rather than sharing it broadly across different runtimes.

### Training data must be representative

If the production app uses a hot route but training only prints `Hello` once, the cache may not contain important profiles. Training does not freeze Java methods permanently; production HotSpot can still profile and JIT according to the runtime workload.

**A valid cache without optimal profiles is not a broken cache.** Usefulness depends on which code paths were loaded/executed during training and the ability to apply the artifacts in production.

## 10. Lab B — compiling the same JAR into a native executable

To do this part, you need a **GraalVM distribution with the Native Image tool** along with an appropriate native compiler/linker toolchain, such as build tools on Linux/macOS or Visual Studio Build Tools on Windows according to the guide for the GraalVM version you use.

**Do not expect `native-image` to exist in a regular OpenJDK HotSpot JDK.** This is a distribution/installation-dependent tool.

### Step B1. Check tools

~~~bash
java -version
native-image --version
~~~

If the shell reports command not found, install the appropriate GraalVM Native Image/toolchain according to that version's documentation. **Do not create a fake `.exe` file** or rename `.jar` to “pass this step”.

### Step B2. Compile the native executable

From the directory containing `startup-compare.jar`:

~~~bash
native-image -jar startup-compare.jar startup-compare-native
~~~

This is a **Native Image build command**, not a production execution. The build tool analyzes reachable code, compiles/links native code, and produces an executable for the build target OS/CPU.

- On Linux/macOS, the output is usually `startup-compare-native` (executable).
- On Windows, the output is usually `startup-compare-native.exe`.
- A Native Image build **can take a long time and require significant CPU/RAM**, even for a small program compared to `javac`.
- Complex libraries with reflection/proxy/JNI/resources may need reachability metadata; the simple lab program needs no special configuration.

**Do not assume every version of `native-image` produces the same file size or build log.** Check `native-image --help` and the docs for your exact version if command-line options change.

### Step B3. Run the output directly

**Linux/macOS:**

~~~bash
./startup-compare-native
~~~

**Windows PowerShell:**

~~~powershell
.\startup-compare-native.exe
~~~

**Program stdout when native build/run succeeds:**

~~~text
message=Hello, AOT
sum=55
~~~

**Visible difference:** there is no `java -jar`, `-XX:AOTCache`, or JDK command to run the program. The native binary still depends on the operating system/architecture and may depend on system libraries; “standalone” does not mean “runs on every OS without anything else”.

### Step B4. Do not use the same name “AOT artifact” for both files

~~~text
HotSpot:
  startup-compare.jar + startup-compare.aot + compatible JDK
                 |
                 v
        java -XX:AOTCache=... -jar ...

Native Image:
  startup-compare-native[.exe] + native OS/runtime prerequisites
                 |
                 v
          ./startup-compare-native
~~~

**A native executable does not use HotSpot `.aot` as a default “plugin cache”.** The two build pipelines are independent even though both start from Java bytecode.

## 11. Native Image and the “closed-world assumption”

GraalVM Native Image relies on **static reachability analysis** from entry points: the compiler must know which classes/methods/fields are needed to include in the executable. If the application uses dynamic behavior that static analysis cannot see sufficiently, appropriate **reachability metadata** must be added.

Cases requiring special attention:

- `Class.forName(...)` with class names constructed from runtime config.
- Reflection looking up constructors/methods/fields by string from input.
- Dynamic proxies.
- JNI libraries and foreign/native integrations.
- Resources loaded from the classpath by runtime name.
- Serialization frameworks or libraries generating adapters/reflection.
- Framework dependency injection, runtime scanning, and generated classes.

**Do not interpret closed-world as “Native Image does not support reflection”.** It supports it under conditions different from flexible Java HotSpot: the used classes/methods/fields need to be appropriately known/reachable/configured at build time. GraalVM has tooling and a reachability metadata repository supporting many libraries.

### Reflection illustration example (not a standalone runnable file)

~~~java
String typeName = readNameFromConfig();
Class<?> type = Class.forName(typeName);
Object object = type.getDeclaredConstructor().newInstance();
~~~

This snippet is **Java pseudo-context**: `readNameFromConfig()` is not defined so it cannot be compiled standalone. On the JVM, the classpath at runtime may contain an appropriate additional implementation. With Native Image, the class type to be reflectively loaded must be known to the build tool or have proper metadata; adding a new JAR after the native executable is built does not automatically expand the closed-world code set.

**Limitation of the example:** dynamic library loading/JNI in Native Image has some specific support, but does not grant the ability to turn a packaged binary into a JVM classloader for arbitrary bytecode plugins.

## 12. Class initialization: a subtle but very important difference

**JVM+AOT cache** still runs on the JVM and preserves class-loading/linking/initialization semantics under documented conditions, so that training does not execute arbitrary side effects that would break the production application.

**GraalVM Native Image** distinguishes:

- **Build-time initialization:** a class static initializer can be executed when creating the native image, and the appropriate state is written into the **image heap** inside the binary.
- **Run-time initialization:** the class is initialized when the native executable runs.

A class containing:

~~~java
final class Settings {
    static final String ENV = System.getenv("APP_ENV");
}
~~~

This is an illustrative declaration; it has no `main`.

If a class is **build-time initialized**, reading an environment variable may be “frozen” to the build environment. That **can cause production to see the build-time env value** if configured improperly.

GraalVM Native Image provides options such as:

~~~bash
native-image --initialize-at-run-time=Settings -jar startup-compare.jar startup-compare-native
~~~

This is an **example command for the option**, not a request to run it immediately on the lab JAR because the lab **does not have a `Settings` class**. When applying this in a real application, replace the class name with the fully qualified name of the class with the appropriate static initialization and check the compiler/version docs.

**Lesson:** do not arbitrarily allow crypto providers, random seeds, time-dependent config, system properties, or environment-derived state to run at **build time**. With Native Image, class initialization policy is a very important part of correctness and reproducibility.

### Difference from an AOT cache snapshot

Do not treat a HotSpot AOT cache as a **Native Image image heap** or vice versa. They differ in what data is allowed to be stored, lifecycle, and runtime compatibility. **There is no implication** that a `.aot` cache stores the entire Java heap of a training run and restores object identities of production user sessions.

## 13. How do runtime, GC, JIT, and flags differ?

| Aspect | HotSpot + AOT cache | Native Image |
| --- | --- | --- |
| Launcher | `java` | Native executable |
| JIT compiler | Can continue C1/C2/tiered compilation | No standard HotSpot tiered JIT in the native runtime |
| Class data | JVM can map AOT cache | Many class/runtime artifacts are already linked into the binary |
| GC | Selected HotSpot GC (G1, etc.) | Native Image GC implementation/configuration |
| Heap flags | JVM flags like `-Xmx` | Native Image options may differ, check `--help`/docs |
| JVM diagnostic flags | `-Xlog:aot`, `-Xlog:class+load`, JFR/JVM tools | Native-image-specific runtime/diagnostics; do not use the full set of HotSpot `-XX` flags |
| Runtime reflection | Full JVM semantics per classpath/module rules | Typically constrained by reachability metadata |
| Runtime code discovery | JVM classloading can load JARs per APIs/configuration | Closed-world model, does not automatically load bytecode absent at build time |

**Native Image still has garbage collection** in the necessary Java runtime portion. The statement “Native Image does not run a JVM so there is no GC” is false. It does not use HotSpot GC/JIT in the way `java` does, rather than omitting memory management.

### JIT on HotSpot can win on long workloads

JDK 25's AOT cache helps HotSpot JIT get a better head start thanks to training profiles, **but can still continue observing the runtime workload and recompiling**. Native Image usually focuses on reducing runtime overhead/startup and packaging optimizations based on build-time knowledge. For some throughput-heavy long-running workloads, JIT adaptive optimization can be advantageous; **there is no single winner**.

## 14. How to compare startup and throughput properly

**The two lines `message=...` and `sum=55` show the same semantics**, but do not prove how much faster AOT cache/native image is.

Metrics to distinguish:

| Metric | Meaning | How to verify |
| --- | --- | --- |
| **Build time** | Time/effort to create JAR, cache, or native binary | Measure build pipeline |
| **Cold start** | From process launch to ready/first useful output | Measure end-to-end across multiple process starts |
| **Warmup** | Time to reach steady throughput | Benchmark/run staged load |
| **Steady-state throughput** | Number of requests/operations completed per unit of time | Sufficiently long and repetitive workload |
| **Tail latency** | P95/P99 response times | Load testing with real concurrency |
| **RSS/native memory** | Total process memory per OS | Process/container metrics |
| **Java heap/live-set** | Reachable Java objects + heap sizing | JVM/native-runtime-specific diagnostics |
| **Binary/artifact size** | Total deployed files and dependency footprint | Filesystem/container image inspection |
| **Operational effort** | Rebuild/training metadata, toolchains, flags, and portability | Per build/release pipeline |

### Comparing JVM without cache and with cache

~~~bash
java -XX:AOTMode=off -jar startup-compare.jar
java -XX:AOTCache=startup-compare.aot -jar startup-compare.jar
~~~

These two commands require **JDK 25**. In actual performance measurements, first verify the cache is loaded with `-Xlog:aot`, then measure **without verbose logs enabled** to avoid skewing results.

### Native comparison

~~~bash
./startup-compare-native
~~~

The command above is for POSIX OS with a successfully built binary. On Windows use `.\startup-compare-native.exe`.

**Do not perform a single run per mode and declare “Native is 100x faster”.** OS file cache, antivirus, page faults, JVM ergonomics, CPU frequency, container startup, app dependencies, and I/O can mask or amplify differences.

### Measurement recommendations

1. Use the **same business logic and inputs**.
2. Separate **build time** from runtime.
3. Multiple process starts, with median/P95 statistics.
4. Workload realistic enough to evaluate JIT steady-state.
5. Measure CPU, memory, peak RSS, and GC alongside latency.
6. Clearly record JDK/GraalVM versions, target OS/CPU, JVM/native flags.
7. Separate I/O/database/network latency from Java startup when needed.
8. Record the native compiler/toolchain/size of the binary and deployment image.
9. Do not force JVM flags onto Native Image when they are unsupported.
10. Re-benchmark whenever changing version/runtime/CPU.

**Results depend on the application.** A CLI/serverless function prioritizing cold-start may see large improvements from Native Image; a server running for weeks with dynamic plugins and a JIT-beneficial workload may suit HotSpot+AOT better. This is an **architectural hypothesis**, not a measurement for a specific application.

## 15. Deploying on containers and other machines

### HotSpot + cache

For example, a deployment needs:

~~~text
container/runtime:
  compatible JDK/JVM
  startup-compare.jar
  startup-compare.aot
  correct entry command:
    java -XX:AOTCache=startup-compare.aot -jar startup-compare.jar
~~~

You **should not** copy a `.aot` created on a different OS/CPU/JDK and assume compatibility. For image builds, training and production workloads must be sufficiently representative; if the pipeline builds on x86-64 while production runs ARM64, the appropriate cache must be recreated rather than renamed.

### Native Image

~~~text
container/runtime:
  startup-compare-native
  required native runtime libraries for target
  command:
    ./startup-compare-native
~~~

The binary can help reduce deployment size compared to a full JDK, but the smallest container image is not always native: base image/system dependencies, debug symbols, and static/dynamic linking choices have a big impact.

A native executable created on Linux **does not run directly on Windows** like a portable JAR. It usually must be cross-compiled/built with an appropriate toolchain or built on the target OS/architecture. A Java `.jar` is portable bytecode subject to version/dependencies; a `.aot` file has its own strict compatibility constraints.

## 16. Decision workflow for choosing a solution

### When to prioritize JVM + AOT cache

- Deploying on a HotSpot JDK that supports the cache.
- Wanting to improve **startup/warmup** while keeping Java runtime/JIT/classloading flexible.
- Having plugins/reflection-heavy libraries and not wanting complex closed-world metadata.
- Having hot endpoints that change with production load, so JIT adaptive optimization is valuable.
- Already having a toolchain stack of JDK/JFR/JMX/GC/tuning.
- Deployment always ships with a JDK image and has a reproducible training pipeline.

### When to try Native Image

- Cold startup and low idle RSS are critically important.
- The application has a stable dependency graph and controllable reflection/resources.
- Willing to invest in build time and a native toolchain.
- Able to test build-time class init, locale/timezone/resources/certificates/JNI.
- Deployment targets a specific OS/CPU, accepting rebuilds for other platforms.
- Already using a framework/tooling with good Native Image metadata support.

### When not to jump to conclusions yet

If the application has very heavy dynamic classloading, runtime-generated bytecode, or complex native libraries, do not assume Native Image cannot do it, but you must **actually test compatibility metadata and build limitations**. Conversely, if the goal is only to reduce JVM cold start, do not assume you must switch the entire runtime to Native Image when HotSpot AOT cache might be enough.

## 17. Important questions when designing a pipeline

**17.1. Does training an AOT cache require real production data?**  
Not necessarily. You should use a **representative workload** with appropriate dummy data, enough to touch important classes/methods without leaking secrets. Training selects artifacts based on behavior, so a poor workload makes the cache less useful.

**17.2. Does the cache automatically update after the JVM runs with new load?**  
Do not treat the generated `.aot` file as a continuously refreshed file just because the JIT keeps profiling in production. If you want the cache updated, you need a **retrain/reassemble** process according to the tool/version. The JVM can JIT new code normally even if the cache does not record the new profiles.

**17.3. Can a native binary use a different config file at runtime?**  
Yes, if the application/runtime is designed to read config at runtime. **Closed-world** constrains **code/class reachability**, not that all runtime data is hardcoded; however, class initialization at build time and packaged resources can make some values differ.

**17.4. Does using JVM+AOT lose JPMS compatibility?**  
No. The application still has classpath/module path and JVM semantics; however, the cache has compatibility conditions with the application/modules/options. With Native Image, analysis/linking must also handle module/library use according to the toolchain.

**17.5. Can Native Image use JFR/JMX like HotSpot?**  
Do not assume the full identical set of tools/flags. GraalVM Native Image has its own capabilities (which may include monitoring/profiling features depending on edition/version), so check the **documentation for the exact distribution**, rather than treating the HotSpot option list as a contract.

**17.6. Which one more clearly means “AOT compile machine code”?**  
**Native Image** clearly compiles reachable application bytecode into a **native executable**. **JDK 25 AOT cache** focuses on preloading/linking/profiles, and the JIT generates optimized machine code at runtime; do not say `AOTCacheOutput` alone natively compiles the entire application.

## 18. Troubleshooting by symptom

| Symptom | Category | Possible cause | Resolution |
| --- | --- | --- | --- |
| `Unrecognized VM option 'AOTCacheOutput'` | JVM cache | JDK 17/21 or non-supporting VM | Check `java -version`; use compatible JDK 25 |
| `.aot` does not appear | JVM cache | Training/assembly failed, permissions | Check exit code and AOT logs |
| App runs but cache is not used | JVM cache | Mismatch JDK/JAR/OS/CPU/options | `-Xlog:aot`; test strict `AOTMode=on` |
| Startup not noticeably faster | JVM cache | Workload too small, missing profiles/training | Measure multiple process starts and representative workload |
| Same cache runs on one node, fails on another | JVM cache | Different JDK/image/arch | Create cache for the exact target |
| `native-image: command not found` | Native Image | No GraalVM tool on PATH | Install appropriate toolchain/distribution |
| Native build missing native compiler | Native Image | GCC/Clang/MSVC dependencies | Install OS-specific build tools per docs |
| Native build missing reflection/proxy metadata | Native Image | Closed-world analysis does not know dynamic code | Add reachability metadata |
| Native binary has wrong config | Native Image | Static initialization ran at build time | Choose run-time init / read config at runtime |
| Native app does not run on another machine | Native Image | OS/CPU/libs mismatch | Build for exact target and check system libraries |
| Native build too slow/high RAM | Native Image | Whole-program analysis/codegen | Adjust build resources/pipeline |
| Native app OOME | Native Image | Inappropriate native runtime heap/memory policy | Check native runtime diagnostics, do not blindly use HotSpot flags |

**Diagnose by artifact type first.** A JDK 17 `AOTCacheOutput` error is unrelated to a Native Image build; a Native Image reachability error is not fixed by HotSpot's `-Xlog:aot`.

## 19. Common mistakes and misconceptions

| Misconception | Correct understanding |
| --- | --- |
| “AOT = everything is always compiled to machine code before runtime.” | AOT has many types of artifacts, from class metadata to profiles/code. |
| “`.aot` is Java's `.exe`.” | HotSpot's `.aot` is a **cache**, not directly runnable. |
| “CDS `.jsa` is a native executable.” | A CDS archive is read by the JVM, not self-executing. |
| “With an AOT cache, Java doesn't need a JVM.” | **Still needs HotSpot/JVM**. |
| “JDK 25 `AOTCacheOutput` creates a Native Image.” | It creates a JVM AOT cache, not a native executable. |
| “Native Image has no garbage collector.” | There is Java runtime support/GC in the native binary. |
| “Native Image still runs HotSpot C1/C2 JIT like `java`.” | It AOT-compiles into a binary; the runtime model is different. |
| “An AOT method profile is pre-saved machine code.” | Profiles help the JVM JIT compile earlier, not equivalent to a native binary. |
| “Native Image does not support reflection.” | Supported depending on analysis/reachability metadata and constraints. |
| “Native Image has arbitrary dynamic plugin classloading just like the JVM.” | The closed-world model places limits on code known only at runtime. |
| “Just renaming `.jar` to `.exe` makes it native.” | Must actually run the Native Image compiler/linker. |
| “A JAR runs on any machine without Java.” | Bytecode needs a Java runtime supporting its version/dependencies. |
| “AOT cache is portable across all JDK/OS/CPU.” | The cache depends on the application/JDK/OS/arch combination. |
| “A native binary built on Linux runs directly on Windows.” | Binary is target-specific. |
| “Native build does not need a native compiler/linker.” | Usually needs an appropriate native toolchain. |
| “AOT cache contains the entire heap state of training.” | Not a process snapshot, only supported artifacts. |
| “Native Image build-time init is always safe.” | Can freeze unwanted env/time/resources. |
| “JVM+AOT has no JIT warmup left.” | Can be reduced, but JIT/adaptive optimization still exists. |
| “Having a cache guarantees a 50% startup reduction.” | Must benchmark the real application; benefit depends on workload. |
| “Native Image always has the highest throughput.” | JIT can be more effective for some long-running workloads. |
| “HotSpot runtime flags all work on a native binary.” | The two runtimes have different options/capabilities. |
| “JEP 515 turns Java source into a binary.” | JEP 515 records AOT method profiles, not changing the application format. |
| “Changing the classpath after AOT cache is fine.” | Can invalidate the cache; need to recreate. |
| “Native executable has no libc/OS dependencies.” | May have system library/native runtime prerequisites. |
| “A single benchmark run is enough to conclude.” | System noise and workload require multiple controlled measurements. |

## 20. Review questions with answers

**1.** Can `startup-compare.aot` be run directly like a program?  
**Answer:** No. It is a JVM AOT cache, read when using `java -XX:AOTCache=...`.

**2.** What output does Native Image produce?  
**Answer:** A native executable/shared library for the OS/CPU target, containing compiled application code and necessary parts of the Java runtime.

**3.** Does a JVM with an AOT cache still use JIT?  
**Answer:** Yes, it can. JDK 25 supports AOT method profiles so the JIT has data to optimize right at the start of runtime.

**4.** Which JDK version in the article has the `AOTCacheOutput` workflow?  
**Answer:** **JDK 25** per the example documentation. Java source can still be compiled with Java 17.

**5.** Why are `java -jar startup-compare.jar` and `./startup-compare-native` different?  
**Answer:** One command starts a JVM executing bytecode, and one command starts a compiled native binary.

**6.** What kind of work does JEP 483 store?  
**Answer:** AOT class-loading/linking artifacts from training/assembly.

**7.** What does JEP 515 add in JDK 25?  
**Answer:** Ahead-of-Time Method Profiling — storing recorded method profiles for the JVM/JIT later.

**8.** Why might a cache fail to load after changing the JAR?  
**Answer:** The cache is tied to the application/JDK/OS/CPU configuration and consistency checks.

**9.** Why might Native Image need reflection configuration?  
**Answer:** Static reachability analysis may not know classes/methods that are only called by runtime name.

**10.** What is the risk of class initialization at Native Image build time?  
**Answer:** It can save static state depending on the build machine's env/config instead of the production machine's if configured incorrectly.

**11.** Does Native Image have GC?  
**Answer:** It can use a GC corresponding to the native binary's runtime; it is not “no GC left”.

**12.** When is `-XX:AOTMode=on` used?  
**Answer:** To require the cache and diagnose compatibility in a controlled testing environment.

**13.** Does the cache existing prove it was used?  
**Answer:** No. Runtime diagnostics like `-Xlog:aot` and checking validation/mapping are needed.

**14.** Is one run of Native Image being faster than HotSpot enough to conclude?  
**Answer:** No; cold start, warmup, throughput, and memory need to be measured multiple times under equivalent conditions.

## 21. Self-practice checklist

- [ ] Read `java -version`, clearly know which build supports JDK 25 AOT options.
- [ ] Run the Java 17+ program and confirm `message=Hello, AOT` / `sum=55`.
- [ ] Compile and package `startup-compare.jar` with the correct Main-Class.
- [ ] Use HotSpot JDK 25 to run baseline `AOTMode=off`.
- [ ] Create `startup-compare.aot` using `AOTCacheOutput` or record/create.
- [ ] Run `java -XX:AOTCache=... -jar startup-compare.jar` again.
- [ ] Read `-Xlog:aot` to confirm the cache is accepted; do not infer from file existence.
- [ ] Do not change JAR/JDK/OS/CPU between training and production test.
- [ ] On GraalVM with the Native Image tool, build an executable from the same JAR.
- [ ] Run the executable directly, without using `java -jar`.
- [ ] Compare outputs to prove the semantics of the sample program.
- [ ] Distinguish cache data and compiled binary in build artifacts.
- [ ] Only benchmark after ensuring both paths work correctly.
- [ ] If the real app uses reflection, evaluate Native Image reachability metadata.
- [ ] Check build-time/run-time initialization config before deployment.
- [ ] Record environmental constraints instead of concluding one solution always wins.

## 22. Official sources

- [Oracle JDK 25 — java Command, Ahead-of-Time Cache](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): `-XX:AOTCache`, `AOTCacheOutput`, `AOTConfiguration`, `AOTMode`; training/assembly/production and compatibility constraints.
- [OpenJDK JEP 483 — Ahead-of-Time Class Loading & Linking](https://openjdk.org/jeps/483): mechanism for recording/training AOT class loading/linking data, the JDK 24 foundation.
- [OpenJDK JEP 514 — Ahead-of-Time Command-Line Ergonomics](https://openjdk.org/jeps/514): improves commands to create AOT cache in JDK 25.
- [OpenJDK JEP 515 — Ahead-of-Time Method Profiling](https://openjdk.org/jeps/515): stores method profiles to improve JIT startup/warmup.
- [Inside.java — Run Into the New Year with Java's AOT Cache Optimizations](https://inside.java/2026/01/09/run-aot-cache/): illustrates the AOT cache workflow and JDK 25 changes.
- [Oracle GraalVM 25 — Native Image Basics](https://docs.oracle.com/en/graalvm/jdk/25/docs/reference-manual/native-image/basics/): executable model, build-time/run-time initialization, image heap, and closed-world analysis.
- [GraalVM Native Image Reference Manual](https://www.graalvm.org/reference-manual/native-image/): creating native executables with `native-image`, prerequisites, and build options.
- [GraalVM Native Image — Reachability Metadata](https://www.graalvm.org/latest/reference-manual/native-image/metadata/): reflection, JNI, dynamic proxy, and resource metadata.
- [GraalVM Native Image — Class Initialization](https://www.graalvm.org/latest/reference-manual/native-image/basics/#build-time-vs-run-time): distinguishing build-time and run-time class initialization.
- [JVMS Java SE 25](https://docs.oracle.com/javase/specs/jvms/se25/html/index.html): Java class-file/VM semantics; does not mandate a specific compiler/AOT implementation.
- [Oracle JDK 25 — Class Data Sharing](https://docs.oracle.com/en/java/javase/25/vm/class-data-sharing.html): background knowledge on CDS/archives on HotSpot.

**Conclusion:** **JVM AOT cache** and **native compilation** both “do some work in advance” but **are not the same solution**. On JDK 25, `.aot` helps HotSpot prepare class-loading/linking data and method profiles, **still using `java` and still having JIT/GC/Java runtime**. With GraalVM Native Image, the build tool analyzes reachable bytecode and generates a **target-specific native executable**, containing the necessary runtime without depending on starting HotSpot in the `java -jar` model. When choosing a technology, look at **startup/warmup, throughput, RSS, native build time, reflection/dynamic loading, initialization policy, platform compatibility, and real-world operations** — not just comparing the name “AOT”.