# How Does Class Data Sharing (CDS) Share Class Data?

## 1. What is CDS and what problem does it solve?

**Class Data Sharing (CDS)** is a **HotSpot JVM** mechanism that allows the JVM to prepare and store **part of the metadata of Java classes** into an archive file, typically with the **`.jsa`** extension. When another JVM is launched under compatible conditions, it can **memory-map** this archive into the process address space and use the stored class representation instead of repeating all of the loading, parsing, verification, and metadata creation steps from bytecode/JAR.

Main goals:

- **Reduce startup time**, especially the class loading and linking overhead for archived classes.
- **Reduce total memory footprint** when multiple JVM processes use the same archive: read-only memory pages can point to the same physical pages managed by the operating system.
- **Reduce the work of initializing class representations**, especially for many frequently reused classes.

CDS is **not** a mechanism for sharing the regular Java heap between two Java programs; it **does not** pre-execute every static initializer; it **does not** JIT/AOT compile the entire program into machine code; and it is **not** an automatic cache for databases, HTTP, or business state.

### A conceptual diagram

```text
                When preparing the archive
.class/JAR/runtime classes
          |
          v
  HotSpot identifies classes to archive
          |
          v
     CDS archive (.jsa)
     metadata in reusable form
          |
          +------------------------------+
          |                              |
          v                              v
     JVM process A                   JVM process B
  maps the same archive           maps the same archive
     |                              |
     +-- shared read-only pages -----+
     |                              |
     +-- private / COW state         +-- private / COW state
     +-- private Java heap A         +-- private Java heap B
     +-- private static state A      +-- private static state B
     +-- private JIT/code cache A    +-- private JIT/code cache B
```

**Key point:** *Sharing class data* means sharing appropriate metadata representations **via operating system mappings**; it does not grant two applications permission to arbitrarily mutate the same object.

### Questions this lesson answers

1. What kinds of data does the archive contain, and why can it be read faster than a JAR?
2. What data is actually **shared**, and what data remains **private**?
3. How do Default CDS, AppCDS, static base archive, and dynamic top archive differ?
4. How do `-Xshare:auto`, `-Xshare:off`, and `-Xshare:on` behave?
5. How do you create and use an archive with JDK 17?
6. How do you prove that an application class was loaded from the archive rather than from a JAR?
7. Why doesn't CDS skip `<clinit>`, JIT warm-up, class loaders, and Java semantics?
8. When can an archive not be used, and how should fallback/experiments be designed?

## 2. What work does traditional class loading cost?

If a class is not yet loaded into the runtime, the processing path may involve:

1. The class loader locating the appropriate bytecode source.
2. Reading the class bytes from the runtime image, JAR, filesystem, or a custom source.
3. Parsing the class file/constant pool and building the required metadata.
4. Verifying constraints and preparing static fields.
5. Resolving symbolic references when needed.
6. Initialization at the appropriate first active use, per JLS §12.4.
7. During execution, profiling/JIT compilation may occur separately.

```text
No suitable CDS archive:
   class path / module image / JAR bytes
                  |
           locate + read
                  |
             class parsing
                  |
          verify / metadata setup
                  |
         link + runtime class state
                  |
         initialize when required
```

There is no formula stating “each class costs exactly X microseconds”. The cost varies by class size, loader behavior, file cache, JVM build, agents, classpath scanning, resolution, and other runtime activities.

### What does CDS save?

The archive stores **class data prepared in a reusable HotSpot format**. When conditions are valid, the JVM can **map and utilize this metadata**, avoiding repeating part of the work of finding, reading, parsing, and organizing class metadata from JARs for classes present in the archive.

This is not a command to “skip all verification/security checks on all classes”; HotSpot must still ensure class identity, loader configuration, compatibility, and correct Java semantics.

**The benefit comes from reusing work that has already been done**, not from changing the program's outcome.

## 3. What does a CDS archive store?

In HotSpot, **class metadata** represents the information the VM needs to execute a class/interface, which may include:

- Class structure information, superclass/interfaces.
- Method and field descriptors, constant-pool information.
- Parsed/linked/preprocessed metadata suitable for the archive format.
- Runtime data structures eligible for archiving according to the HotSpot/JDK release.
- In certain configurations, specialized **archived heap objects** such as certain String objects/constant data suitably prepared by the VM.

Do not assume that “CDS copies the application's entire object graph into the archive”. Shared contents and representation vary by JDK/collector/platform. The **HotSpot implementation** determines exactly which data is archived and which metadata versions must be recreated or relocated.

### 3.1. Metadata is different from a Java object instance

```java
class Customer {
    long id;
    String name;
}
```

This is a class snippet, not a standalone runnable program.

The archive can support **metadata describing `Customer`** if the class is archived. When each process runs `new Customer()`, they **do not receive a single shared Java object**, do not share the value of `id`, and do not share a mutable `name` variable across JVMs.

```text
Shared idea:
  class shape / metadata for Customer
Per JVM:
  new Customer() object allocations
  instance fields (id, name)
  application data and state
```

### 3.2. “Archiving classes” does not mean archiving source code

CDS does not store Java source (`.java`) for compilation. It stores runtime-friendly representations based on known classes. The JVM must still obey class loading/security/initialization rules and may have to fall back to regular class files when the archive cannot be used.

### 3.3. An archive can be larger than class files

According to the **Oracle JDK 17 Application Class Data Sharing** documentation, class representations in the archive can take up more disk space than class bytes in a JAR/runtime image (the documentation notes roughly 2–5 times depending on the class). The reason is that the format is optimized for fast reuse, not just maximum file compression.

Therefore, **do not archive every class of every library by default**. It should only contain classes actually used frequently by the application, unless profiling and deployment policy indicate a different scope is needed.

## 4. “Sharing” happens at the OS level: memory mapping

The core idea does not lie in a global Java singleton, but in the OS's **memory-mapped files**.

At runtime:

1. The JVM opens a compatible archive.
2. Regions of the archive are mapped into the process's **virtual address space**.
3. Multiple JVM processes can map the same file/physical file-cache pages.
4. **Read-only** pages can be physically shared.
5. Writable regions can use **copy-on-write (COW)** or be provided as appropriate private data.

```text
File on disk: cds-demo.jsa
        |
        v
Operating-system page cache / mapped file pages
        |
        +--------------------------+
        |                          |
       JVM A                      JVM B
 virtual address A             virtual address B
        |                          |
        +---- shared RO pages -----+
        |                          |
    private RW/COW pages       private RW/COW pages
        |                          |
     Heap A                       Heap B
```

### 4.1. Identical virtual addresses are not a strict requirement

The JVM can map the archive at suitable virtual addresses and handle relocation/pointer adjustments according to HotSpot/JDK requirements. Do not assume processes must have the exact same absolute pointer addresses to share file pages.

### 4.2. What does copy-on-write mean?

A file-backed page can **be shared while unmodified**; when a process needs to write to a mapped page under COW, the OS provides a private page for that modification. The JVM also has separate private state regions not placed in shared archive pages.

**Do not assume “all archive regions are permanently read-only”**, because HotSpot logs can show archive regions labeled `ReadOnly` and `ReadWrite`. The pages actually shared depend on OS mapping, memory page modifications, and implementation.

### 4.3. When does shared physical memory help?

If multiple Java processes use the same JDK/CDS archive and pages are mapped/shared, total **physical memory consumption** can be lower than if each process stored its own metadata copies.

However:

- Each JVM still has its own private Java heap, threads, native allocations, and code cache.
- Not every page can be shared.
- The RSS of each individual process may include shared mapped pages, so **simply summing RSS across processes can double-count**. On Linux, PSS or appropriate metrics can be considered when evaluating total shared-memory footprint.
- A single standalone JVM can still see reduced startup even when there is no second process to share pages with.

### 4.4. Not Java-level shared mutable memory

CDS does not provide an API like a shared-memory queue or distributed cache. There is no Java Memory Model condition that allows a thread in process A to directly access `static int counter` of process B just because both map the archive.

## 5. What remains private to each JVM?

Even when class `CDSDemo` is loaded from a shared archive, each JVM process has independent runtime state:

| Component | Shared via CDS? | Notes |
| --- | --- | --- |
| Archived read-only metadata pages | **Can be shared via OS** | Depends on archive/mapping conditions |
| Written/COW archive pages | **Does not retain sharing for copied parts** | Private modified pages |
| Regular Java heap | **No** | Each JVM has its own heap |
| Objects created by `new` in app | **No** | Each process creates its own objects |
| Mutable static values of a class | **No** | Per-JVM runtime class state |
| Java threads and stack frames | **No** | Created separately per process |
| Monitor locks and synchronization state | **No in the sense of app sharing across processes** | JMM applies within each JVM process |
| JIT profiles, C1/C2 compiled methods | **Not merely from enabling CDS** | Separate code cache and JIT state |
| GC state, roots, and heap generations | **No** | GC manages each process's heap |
| Network connections / DB pools | **No** | App must initialize separately |
| CDS archive file | **Can be used together** | File/page cache shared by OS |

**Rule of thumb:** *shared class metadata* ≠ *shared live application state*.

## 6. CDS does not skip class initialization (`<clinit>`)

This is the most common point of confusion.

```java
final class Settings {
    static final int LIMIT;

    static {
        LIMIT = 42;
        System.out.println("Settings initialized");
    }
}
```

This is a class snippet. When a first process active-uses `Settings`, the JVM must perform the appropriate initialization and print the marker. A second process, even when using the same CDS archive, **still has its own class initialization state** and may print the marker upon active-use in that process.

### Why can't an archive “pre-execute” arbitrary `<clinit>`?

A static initializer can:

- Read environment variables/config.
- Create objects tied to the process.
- Open files/sockets.
- Call JNI/native code.
- Register shutdown hooks.
- Initialize static fields that depend on runtime.

If the JVM skipped all these side effects just because class metadata was archived, semantics could be wrong. CDS is therefore **not an arbitrary cache of application static initialization results**.

### 6.1. Archived heap objects are a narrower scope

Some JVM versions/GC configurations support archiving specialized heap objects that have been safely prepared by the VM. This **does not mean** any object produced by a user-defined `<clinit>` can be archived and reused as a mutable singleton across JVM processes.

### 6.2. Class load != class init

CDS primarily focuses on reducing work during **loading/linking**. JLS §12.4 still governs when initialization happens. A class can be loaded from the archive while its static block still runs on first active use.

## 7. CDS does not replace JIT warm-up

The two optimizations address two different kinds of work:

```text
CDS:    bytecode/class representation -> shared archived metadata
        Reduces corresponding load/link overhead

JIT:    executable hot bytecode -> machine code
        Improves execution performance of hot methods/loops
```

An application running multiple times:

- Can use CDS to help load metadata faster.
- Yet C1/C2 may still need runtime profiles to optimize.
- If code is not hot yet, it may still run in the interpreter.
- Once code is hot, the JVM has compiled code in its **private code cache**, rather than automatically taking C2 native code from a previous process out of `.jsa`.

Do not write “enabling CDS means the program is already C2 warmed up before `main`” or “the archive is a Java executable”.

### 7.1. Avoid confusing CDS with AOT code caching

There are other AOT/native-image/code precompilation mechanisms across JDK and JVM distributions. CDS `.jsa` within the scope of JDK 17 is not a general JIT-compiled method cache. If a newer release adds related AOT capabilities, one must read the **documentation for that exact version** rather than conflating semantics.

## 8. Default CDS archive — why do you see an effect without creating anything yourself?

Since JDK 12, many 64-bit JDK distributions (including Oracle JDK) ship with a pre-built **default CDS archive**, typically containing commonly used platform/core library classes.

According to Oracle JDK 17 documentation, on common configurations, the default archive path is:

```text
Linux/macOS: $JAVA_HOME/lib/server/classes.jsa
Windows:     %JAVA_HOME%\bin\server\classes.jsa
```

Note: the location and presence of the archive depend on the JDK vendor/distribution/install layout, not a JLS guarantee.

### 8.1. Three common modes

| Option | Meaning | Recommendation |
| --- | --- | --- |
| **`-Xshare:auto`** | Use CDS when a compatible archive is available; can fall back | Suitable default on many HotSpot builds |
| **`-Xshare:off`** | Disable CDS for baseline comparison | Suitable for testing/diagnostics |
| **`-Xshare:on`** | Require CDS; error/exit if unavailable | **Testing only**, not recommended for production |

Test commands:

```bash
java -Xshare:auto -version
java -Xshare:off -version
java -Xshare:on -version
```

With `-Xshare:on`, the JVM may **fail to start** when a compatible archive is missing or configurations conflict. Do not use this flag in production just to “force it to be fast”.

### 8.2. What if no suitable archive is available?

In **auto mode**, the JVM can skip the archive and perform normal class loading according to HotSpot policy. In **on mode**, inability to use CDS can cause the VM to fail instead of continuing.

**A process running successfully is not enough to prove CDS was used.** Observe `-Xlog:cds=info` and the class loading source.

## 9. AppCDS — bringing application classes into the archive

**Application Class Data Sharing (AppCDS)** extends the idea from core JDK classes to eligible application/library classes.

Scenario:

- 10 JVM instances all run the same application JAR.
- The same classes/framework libraries are loaded repeatedly.
- If metadata has been suitably archived, the processes can map part of that data.

AppCDS **can** help startup and footprint. However, if the program spends most of its time connecting to a DB, reading config, or running expensive initialization, AppCDS will not solve everything.

### 9.1. It does not mean the archive “contains all classes of the JAR”

An archive typically contains **the set of eligible classes that were observed/included in the class list** during build/dump.

Classes in unexecuted code paths or classes that are not archive-eligible may still be loaded normally later.

### 9.2. Runtime class loaders and archive eligibility

HotSpot AppCDS supports built-in loaders and certain custom-loader classes subject to version/class-source/compatibility conditions. **There is no guarantee that every custom bytecode generator, runtime proxy, or custom classloader will be fully archived and reused**.

### 9.3. Why must the archive match the exact artifact?

CDS metadata reflects the classes/JARs and VM configuration at the time the archive was created. If the code changes and we try to use old metadata, results could be wrong; therefore the JVM performs compatibility checks and may reject/stop using the archive.

**Do not use an archive built from artifact A expecting it to accurately represent artifact B**.

## 10. Base archive and dynamic top archive

HotSpot can use up to **two archive layers** in documented JDK 17 configurations:

1. **Base (static) archive:** usually the default archive containing core classes from the JDK.
2. **Dynamic (top) archive:** adds classes identified from an application run that are not in the corresponding base archive.

```text
               Base archive
         $JAVA_HOME/.../classes.jsa
          (core / base classes)
                     |
                     v
          Dynamic top archive
                app.jsa
        (application/library classes)
                     |
                     v
         Java process startup:
    map base + dynamic when compatible
                     |
                     v
      load archived metadata on demand
```

The words “static”/“dynamic” here refer to **archive creation method/layer**, **not** the Java keyword `static`, not initialized state, and not “static/dynamic” data in the heap.

### 10.1. Dynamic archive does not replace the base

A dynamic top archive usually **depends on the base archive** used when creating it. At startup, the JVM needs a compatible base archive to map the top archive properly.

### 10.2. `SharedArchiveFile` paths

In documented supported cases:

```text
-XX:SharedArchiveFile=app.jsa
```

can directly use a dynamic archive, letting the JVM locate the recorded base archive.

When specifying both explicitly:

```text
Linux/macOS: -XX:SharedArchiveFile=base.jsa:app.jsa
Windows:     -XX:SharedArchiveFile=base.jsa;app.jsa
```

The separator **differs across OSes**. On a Windows shell command line, `;` can also have special meaning, so quote the entire JVM argument if needed.

## 11. Standalone Java 17+ example: CDS does not share static state

Create the file **`CDSDemo.java`**:

```java
public final class CDSDemo {
    private static volatile long sink;

    static final class Engine {
        static final int base;

        static {
            base = 7;
            System.out.println("engine initialized");
        }

        static int mix(int x) {
            return (x * 31 + (x >>> 3) + base) & 1023;
        }
    }

    static long compute() {
        long sum = 0;
        for (int i = 0; i < 10_000; i++) {
            sum += Engine.mix(i);
        }
        sink = sum;
        return sum;
    }

    public static void main(String[] args) {
        System.out.println("started");
        long result = compute();
        System.out.println("checksum=" + result);
        System.out.println("sinkMatches=" + (sink == result));
    }
}
```

Place the file in a separate practice directory; no module/package is needed.

### 11.1. Compile and package the JAR

```bash
javac --release 17 CDSDemo.java
jar --create --file cds-demo.jar CDSDemo.class 'CDSDemo$Engine.class'
```

**Important note about shells:** The `jar` command above is an example for Bash/POSIX shells using **single quotes** to prevent `$Engine` from being interpreted as a variable by the shell. On Windows PowerShell, you can use:

```powershell
javac --release 17 CDSDemo.java
jar --create --file cds-demo.jar CDSDemo.class 'CDSDemo$Engine.class'
```

PowerShell also accepts a single-quoted literal string as above. Depending on your layout, if an old JAR already exists in the directory, safely delete/rename the test JAR before recreating it; do not overwrite production artifacts.

### 11.2. Run without CDS

```bash
java -Xshare:off -cp cds-demo.jar CDSDemo
```

**Exact stdout on a successful run:**

```text
started
engine initialized
checksum=5113344
sinkMatches=true
```

### 11.3. Run with default CDS

```bash
java -Xshare:auto -cp cds-demo.jar CDSDemo
```

The program produces the **same four stdout lines** as above. Default CDS can help some core JDK classes, but **does not necessarily** archive `CDSDemo` because it is an application class not present in the default archive.

### 11.4. Why does the static initializer still print?

Each time a new Java process starts, class `CDSDemo$Engine` is active-used for the first time, running the static block per JLS and printing `engine initialized`.

The `.jsa` file can provide prepared class metadata, **not share static variable values across two JVM processes** or eliminate the side effects of the source initializer.

### 11.5. Verification performed

The file was compiled with **`javac --release 17`**, then successfully run with CDS-related options on **OpenJDK/HotSpot JDK 24.0.2** in the test environment.

**Clear distinction:** This is Java 17-compatible code, **not a claim that it was run on a specific JDK 17 binary**. The commands use options documented for JDK 17. Build/runtime numbers must be re-verified in your deployment environment.

## 12. Dynamic AppCDS: top archive and the meaning of the preparation run

On **HotSpot JDK 17**, using the application JAR created in section 11:

```bash
java -XX:ArchiveClassesAtExit=cds-demo.jsa -cp cds-demo.jar CDSDemo
```

The program still executes normally; the JVM writes the **dynamic top archive** during the appropriate exit phase. The archive contains **metadata of eligible loaded classes** not yet in the base archive, **not a Java heap snapshot for another process to resume**. If the process is killed abruptly, the base archive is incompatible, or the configuration fails, do not assume the `.jsa` file is ready. Verify the file/exit code and logs.

## 13. Using the dynamic archive — verifying shared classes

In a **new JVM process**, with the same JDK build and application JAR:

```bash
java -XX:SharedArchiveFile=cds-demo.jsa -Xlog:class+load=info -cp cds-demo.jar CDSDemo
```

The application must still exhibit the same behavior: `started`, `engine initialized`, `checksum=5113344`, `sinkMatches=true`. In HotSpot diagnostic logs, a class actually loaded from the dynamic top archive can have the marker `source: shared objects file (top)`. A class still read from a JAR can display `source: file:...`. **Merely having a `.jsa` file on disk or seeing the JVM run successfully is not enough to conclude an application class used CDS**.

CDS reuses metadata, does not share mutable `static` fields across JVM processes, and does not pre-run arbitrary static initializers. The upcoming lesson on **static/dynamic AppCDS** teaches the full workflow; the lesson on **class-loading logs** helps identify mapped archives, class sources, and fallbacks.

## 14. Observing memory mapping with `-Xlog:cds`

A diagnostic command:

```bash
java -XX:SharedArchiveFile=cds-demo.jsa \
     -Xlog:cds=info \
     -cp cds-demo.jar CDSDemo
```

HotSpot events may show:

```text
... Opened archive .../classes.jsa
... Opened archive cds-demo.jsa
... Mapped static  region #... (ReadOnly)
... Mapped dynamic region #... (ReadOnly)
... Mapped dynamic region #... (ReadWrite)
```

This is a **condensed sample log**, not a required order/timestamps/addresses. The JVM may map archives at different addresses and log additional pointer relocation/heap object handling.

### 14.1. Why are there multiple regions?

HotSpot can split an archive into regions protected/positioned differently depending on implementation. Regions can contain read-only metadata, writable/COW data, bitmap/relocation metadata, etc. **There is no promise that each archive has only a single memory-mapped region**.

### 14.2. Why might relocation be needed?

An archive is created with certain layout/pointer assumptions. When mapped into a new process, the address-space layout and runtime pointer encoding may differ; the VM handles compatibility or relocations if supported.

This does not break the sharing principle; shared file pages can still provide benefits if compatible, though private adjustments may sometimes be needed.

### 14.3. Do not use `-Xlog:cds` as an accurate stopwatch

Logging has I/O overhead and event content is diagnostic, not a pure isolation of all memory mapping/preparation CPU costs. Use logs to **confirm and explain**, then measure startup benchmarks **without logging**.

## 15. Static AppCDS — class list, dump, and reuse

Static AppCDS separates **collecting the class list** and **creating the archive** into two phases. Minimal example on HotSpot JDK 17:

```bash
java -Xshare:off -XX:DumpLoadedClassList=cds-demo.classlist -cp cds-demo.jar CDSDemo
java -Xshare:dump -XX:SharedClassListFile=cds-demo.classlist -XX:SharedArchiveFile=cds-static.jsa -cp cds-demo.jar
java -XX:SharedArchiveFile=cds-static.jsa -cp cds-demo.jar CDSDemo
```

The first command **runs the application**, the second creates the archive **without calling `main`**, and the last launches a new JVM. JDK/classpath/JAR conditions must be compatible; the application continues to follow Java class initialization semantics. Full exercises on classlists, dynamic top archives, flags, CI/CD, and failure cases are the dedicated focus of the **AppCDS, Static and Dynamic Archives** lesson.

| Comparison | Static archive | Dynamic archive |
| --- | --- | --- |
| Separate class list | Yes in common workflow | Not required |
| Creation time | `-Xshare:dump` phase | At app exit with `ArchiveClassesAtExit` |
| Base/top | Custom static/base | Top layer depending on base |
| Java objects/state shared across processes | Not automatic | Not automatic |

On HotSpot JDK 17, static dump has classpath constraints; therefore use a JAR instead of assuming a non-empty class directory is always valid. Verify the archive with `-Xlog:cds` and **class source** with `-Xlog:class+load`, not just by checking that the file exists.

## 16. Using `jcmd VM.cds` when appropriate

Oracle JDK 17 `java` documentation notes that the `jcmd` tool can assist in creating CDS archives from a running JVM, with diagnostic commands such as:

```text
jcmd <pid> VM.cds static_dump my_static_archive.jsa
jcmd <pid> VM.cds dynamic_dump my_dynamic_archive.jsa
```

**`<pid>` is a placeholder**; use the actual PID. Commands/arguments may depend on build/permissions.

### 16.1. Dynamic dump requires appropriate configuration

According to JDK 17 `java` documentation, `VM.cds dynamic_dump` may require the JVM to be started with:

```text
-XX:+RecordDynamicDumpInfo
```

Do not assume every already-running process allows dynamic dump. Check:

```bash
jcmd <pid> help
```

### 16.2. Do not touch uncontrolled production processes

Diagnostic operations can increase CPU/memory/I/O, create files, and alter profiling state. Test in test/staging environments before adding dump operations to production runbooks.

## 17. Why can an archive sometimes not be used?

An archive may be unsuitable because:

- **JDK vendor/build/version** does not match or is incompatible with the archive created.
- **Classpath/JAR changes**: a JAR file containing archived classes was modified after dumping.
- **Module/classpath restrictions** or options like `--upgrade-module-path`, `--patch-module`, `--limit-modules` have effects that make CDS unavailable in documented JDK 17 configurations.
- **Base archive** of the dynamic top archive is incompatible.
- **VM options/GC/pointer encoding** or other runtime assumptions do not match.
- **Custom classloader behavior** makes the class ineligible or unusable from the archive.
- **Java agents/instrumentation/class transformation** alter class shape at load time.
- The archive is missing, unreadable, corrupted, or has inappropriate permissions.

### 17.1. Fallback vs fail-fast

- `-Xshare:auto`: attempts to use if compatible, can fall back when unusable.
- `-Xshare:on`: requires use, so it errors when the archive is unavailable; testing only.
- `-Xshare:off`: does not use the archive, useful for creating a baseline.

**Do not conclude CDS is active just because VM options include `-Xshare:auto`**. Evidence from `-Xlog:cds=info` and `-Xlog:class+load=info` is required.

### 17.2. Rebuild when the deployment artifact changes

A CI/CD pipeline producing a new application JAR must treat the old archive as a **versioned artifact with a dependency** on the JDK + app. If the classpath/JAR changes, regenerate the archive under the same corresponding deployment configuration.

### 17.3. Safety, consistency, and provenance

Do not treat `.jsa` as an arbitrary data source that can be downloaded from a third party and mapped into production. It is a **VM-specific binary artifact**, so it must be built/controlled via a trusted build pipeline and protected with appropriate file permissions, image signatures, and deployment policy.

## 18. CDS and Class Data Sharing in containers

A common mental model:

```text
Container image:
  JDK runtime + classes.jsa
  application.jar
  cds-demo.jsa (optionally generated at image build)
          |
       deployment
          |
  +-------+--------+
  |                |
Pod/JVM A        Pod/JVM B
  |                |
Same host image layers + compatible mapping?
  -> OS can share file-backed physical pages
  -> each JVM still has private heap, threads, JIT state
```

### 18.1. Shared pages across containers can happen

When containers on the **same OS kernel/host** map suitable file-backed pages, the filesystem/page cache and memory mappings can yield sharing similar to regular processes. However, do not assume **containers on different hosts have a single shared physical RAM**.

### 18.2. Image build can generate the archive before deployment

If the build pipeline generates the archive using the **exact JDK build, app JAR, and options** intended for use, the runtime can map it on the first startup. This can be useful for services that restart/scale frequently.

### 18.3. Application mutable state is not shared

Pod A changing `static int count` does not change Pod B's `static int count`. CDS only helps reuse eligible class data; synchronizing state across pods still requires network/database/messaging or an appropriate distributed mechanism.

### 18.4. Do not measure only container boot events

Separate:

- Container image pull/unpack/start.
- OS/JVM process startup.
- Application readiness.
- First-request latency.
- Memory footprint/RSS/PSS.
- Resource pressure when many JVMs share a host.

CDS mainly helps **inside Java startup/class loading**; it does not solve all image pull/network initialization.

## 19. JAR packaging and classpath consistency

An archive created from an application JAR is validated against classpath/JAR metadata, so:

1. Keep classpath path/order valid according to JDK rules.
2. Do not modify the JAR after creating the archive.
3. Do not mix classes from different versions without rebuilding the archive.
4. Check symlinks/mount paths in the deployment environment if incompatibility arises.
5. Do not assume source code equivalence guarantees identical binary artifacts; timestamps/manifests/layouts can affect checks.

### 19.1. Fat JARs, nested JARs, and custom loaders

A fat JAR or framework launcher may use class loader/URL/resource semantics different from a regular classpath JAR. Do not assume every framework nested-JAR structure is handled by CDS the same way as `java -cp cds-demo.jar CDSDemo`.

The right approach is to create the archive using the **exact supported production launch method** and then inspect class origins in the logs.

### 19.2. Classpath changes yet the archive is still partially used?

Different JDK releases have different classpath validation rules for base/top archives. Oracle JDK 17 documentation describes specific constraints such as the dump-time classpath needing to match or be a prefix of the runtime classpath in relevant workflows. **Do not assume every type of change renders the archive completely useless, nor promise any change is safe**. Check the logs and build/version policy.

## 20. Evaluating startup with controlled experiments

At minimum, create these groups:

| Group | JVM options | Meaning |
| --- | --- | --- |
| **A** | `-Xshare:off` | Baseline without CDS |
| **B** | `-Xshare:auto` | Default core-class CDS |
| **C** | `-XX:SharedArchiveFile=cds-demo.jsa` | Default base + AppCDS dynamic top |
| **D** | `-Xshare:on` (appropriate testing only) | Confirm availability, not a default production tuning |

Keep the following identical:

- JDK vendor/version/build.
- App JAR and classpath.
- JVM heap/GC/cpu flags, container quotas.
- Input workload and correctness checksum.
- Host/OS and comparable CPU/I/O contention levels.
- Number of repetitions, randomization/alternating order.
- Measurement milestones (process wall time, time to ready, first request).

### 20.1. Collect the right metrics

**External process elapsed time**: includes launch/bootstrap/execution/shutdown. Use GNU `time`, PowerShell `Measure-Command`, or a parent benchmark harness.

**Application readiness time**: use a readiness marker/health probe, not just when `main` begins.

**First request latency**: measure separately because CDS may shift some startup cost, yet the application still has lazy init/JIT/network work.

**Total memory footprint**: measure when multiple JVM instances run concurrently, distinguishing RSS and shared pages/PSS where the OS supports it.

### 20.2. Do not measure baselines while printing class-load logs

`-Xlog:class+load=info` can generate thousands of lines and create I/O overhead. **Run diagnostics separately from the baseline** to verify archive use, then measure performance without heavy logging enabled.

### 20.3. Do not treat a single sample as guaranteed speed

A new JVM restart may use a warm OS page cache; C2 runtime state is still fresh. CDS benefits are usually larger in class-heavy workloads, whereas an I/O-bound application may see almost unchanged end-to-end startup.

Measure **median/spread/p95** across multiple runs and state assumptions clearly.

## 21. Example benchmark script in PowerShell

After having `cds-demo.jar` and `cds-demo.jsa`:

```powershell
foreach ($mode in @("off", "base", "app")) {
    Write-Output "MODE=$mode"
    foreach ($trial in 1..5) {
        if ($mode -eq "off") {
            Measure-Command { java -Xshare:off -cp cds-demo.jar CDSDemo }
        } elseif ($mode -eq "base") {
            Measure-Command { java -Xshare:auto -cp cds-demo.jar CDSDemo }
        } else {
            Measure-Command {
                java -XX:SharedArchiveFile=cds-demo.jsa -cp cds-demo.jar CDSDemo
            }
        }
    }
}
```

This is a **demonstration of repeated measurement**, not an automated statistics report. If you need the median, collect `TotalMilliseconds` from `Measure-Command` into a CSV and ensure valid Java process exit codes/checksums.

### 21.1. Common measurement pitfalls

- Measuring the first run with a cold filesystem cache and the second run with a warm cache.
- Using `-Xshare:off` for baseline while forgetting the archive fell back in another mode.
- Enabling verbose logs in only one mode.
- Comparing a short-lived process against a long-running service.
- Adding `-Xcomp` or different heap/GC flags to one group, losing variable control.
- Benchmark too short, so shell/process scheduling noise overwhelms CDS effects.

## 22. Benefits CDS must not unconditionally promise

**CDS can**:

- Reduce work when loading/linking classes contained in the archive.
- Reduce startup time of class-heavy JVM applications.
- Reduce total memory footprint across multiple processes sharing archive pages.
- Reduce the JVM startup portion in service scale-out/container workloads.

**CDS does not guarantee**:

- Every class is loaded from the archive.
- Every class initializes early or does not initialize.
- Every Java object or static field is shared.
- Hot methods automatically have C2 compiled code at startup.
- Runtime execution throughput increases by an exact percentage.
- All Java process startup time is class loading, or can all be eliminated by CDS.
- Archives remain compatible across every JDK update, app version, or JVM flag.
- Avoiding all class verification/resolution work that may arise.

**Do not turn an external benchmark's “up to X% faster startup” into a performance claim for all services.**

## 23. Comparing CDS with other concepts

| Concept | Mechanism | How is it different from CDS? |
| --- | --- | --- |
| **JIT C1/C2** | Compiles hot bytecode to machine code | Not just sharing class metadata |
| **Class initialization** | Runs `<clinit>` on active use | CDS does not skip init side effects |
| **Classpath scanning** | Framework searches for classes/annotations/resources | Scanning is separate work, may not even define classes yet |
| **JAR compression** | Compresses classes/resources on disk | CDS stores runtime-ready data for reuse |
| **OS filesystem page cache** | Caches file pages | CDS leverages mappings and runtime format, not just caching JAR bytes |
| **Metaspace** | HotSpot's runtime metadata area | Archived metadata has its own sharing/mapping rules |
| **Shared mutable Java heap** | Mechanism for sharing object state across processes | CDS does not provide that kind of API |
| **CRaC/checkpoint restore** | Saves/restores process state in respective technology | Not synonymous with CDS; lifecycle and side effects differ |
| **Native-image/AOT compilation** | Compiles part of code ahead of runtime | Not the same format/contract as JDK 17 AppCDS |

## 24. Common misconceptions

| Misconception | Correct understanding |
| --- | --- |
| “CDS shares all Java objects between JVM processes.” | Primarily shares eligible metadata/archive pages; each process has its own heap/state. |
| “Two JVMs have the same static field value because of the same archive.” | Mutable static state is initialized/managed separately per runtime. |
| “With `.jsa`, static initializers don't run.” | `<clinit>` still follows JLS initialization rules. |
| “CDS is a cache of C2 compiled code.” | Not HotSpot JDK 17's general JIT code cache. |
| “A class loaded from shared objects file is a class with a pre-built Java instance.” | Shared class representation is different from an object instance. |
| “CDS enabled means every class in the JAR is archived.” | Only eligible classes are archived and used. |
| “Archive disk file is always smaller than the JAR.” | Runtime-ready archive data can be larger than class bytes. |
| “`-Xshare:on` is the best production choice.” | Oracle explicitly states it is for testing only because it can cause VM startup failure. |
| “`-Xshare:auto` always forces archive usage.” | It can fall back when the archive is incompatible. |
| “Just running with defaults and seeing the right output means CDS is working.” | `cds` and `class+load` logs are needed to confirm. |
| “CDS shares data across RAM between two different hosts.” | OS page sharing is on the same host/kernel, not distributed RAM. |
| “Without RO page sharing, all CDS performance benefits disappear.” | Even a single process can get startup benefits from the archive. |
| “Summing RSS of N JVMs gives total non-overlapping RAM.” | RSS can count shared pages multiple times. |
| “Dynamic top archive can stand alone without a base.” | In the JDK 17 model, dynamic archives depend on a compatible base. |
| “Editing the JAR after dump will still reliably use the old archive.” | Runtime validation may reject it and require a rebuild. |
| “`-XX:ArchiveClassesAtExit` saves the heap at exit.” | It writes a class data archive, not an arbitrary snapshot of the app heap. |
| “CDS replaces DB connection setup or TLS warm-up.” | No. Those are separate application/environment initialization tasks. |
| “Class sharing erases class identity by loader.” | Loader/class identity semantics must still hold. |
| “If a class is in the archive, the runtime doesn't need the class initialization lock.” | Class init synchronization/lifecycle is still preserved. |
| “The default archive contains all application classes.” | Default usually targets core JDK classes. |
| “Enabling class-load logging does not affect benchmarks.” | Verbose logging has overhead and must be separated from diagnostic runs. |
| “CDS is only useful when there are two JVMs.” | One JVM can save startup time; multiple JVMs add memory sharing. |

## 25. Self-check with answers

**Q1.** What does CDS stand for?

**Answer:** Class Data Sharing — a HotSpot mechanism to archive/reuse eligible class data to improve startup and memory footprint.

**Q2.** What extension do archives usually have?

**Answer:** `.jsa`, for example `classes.jsa` or `cds-demo.jsa`.

**Q3.** Through what OS-level mechanism do multiple JVMs share an archive?

**Answer:** Memory mapping of the file, which can share read-only physical pages and use COW/private writable state.

**Q4.** Can you change JVM B's `static int counter` by modifying JVM A's counter?

**Answer:** No. Application static/runtime state is private to each process.

**Q5.** Does CDS automatically skip `<clinit>`?

**Answer:** No. Initialization code/side effects still follow Java semantics.

**Q6.** Can CDS make class loading faster than reading from a JAR?

**Answer:** Yes. Archived runtime-ready metadata helps avoid repeating part of the read/parse/link work for eligible classes.

**Q7.** What does `-Xshare:off` do?

**Answer:** Disables CDS, commonly used for baselines/diagnostics.

**Q8.** How does `-Xshare:auto` differ from `-Xshare:on`?

**Answer:** Auto uses CDS if a suitable archive exists and can fall back; on requires it, errors if unavailable, and should only be used for testing.

**Q9.** What classes does the default CDS archive usually contain?

**Answer:** Commonly used platform/core library classes pre-built by the JDK, depending on distribution.

**Q10.** What is AppCDS?

**Answer:** Application Class Data Sharing, extending archiving to eligible application/library classes.

**Q11.** Which option creates a dynamic top archive?

**Answer:** `-XX:ArchiveClassesAtExit=app.jsa` in a JDK 17-compatible workflow.

**Q12.** Does a top archive need a base archive?

**Answer:** Yes, in the JDK 17 dynamic AppCDS model it requires a compatible base archive.

**Q13.** Why does `CDSDemo$Engine` still print the marker on subsequent runs with the archive?

**Answer:** The static initializer runs according to the new process's class initialization; metadata sharing does not preserve live static state from an old process.

**Q14.** Which log proves an application class came from the archive?

**Answer:** `-Xlog:class+load=info` with the source reporting `shared objects file` or `shared objects file (top)` on a compatible HotSpot.

**Q15.** What does `-Xlog:cds=info` show?

**Answer:** Information on opening/mapping archives, region handling, and compatibility/relocation according to the JVM build.

**Q16.** Why shouldn't you download arbitrary `.jsa` archives from the Internet?

**Answer:** It is a VM-specific binary artifact; it needs a trusted source and matching build/configuration to avoid compatibility/security issues.

**Q17.** How does static AppCDS differ from dynamic in the initial step?

**Answer:** Static workflow usually requires capturing a class list and running `-Xshare:dump`; dynamic can archive at process exit without a separate class list.

**Q18.** Why shouldn't you sum the RSS of three JVMs and call that dedicated RAM?

**Answer:** Shared mapped pages may be counted repeatedly in each process's RSS; PSS/OS metrics help evaluate sharing.

**Q19.** Can you use an archive created on JDK 24 on a JDK 17 binary without checking?

**Answer:** No. CDS archives are very sensitive to JDK build/format compatibility.

**Q20.** Does CDS make `compute` methods C2-compiled before the first run?

**Answer:** No. JIT profiling/compilation is a separate runtime part from CDS class metadata.

**Q21.** Why might an app benchmark not see a large startup improvement even when CDS is used properly?

**Answer:** Class load/link is only part of total time; framework initialization, I/O, networking, JIT, GC, and OS launch can dominate.

**Q22.** If an archive cannot be used under `-Xshare:auto`, how do you check?

**Answer:** Inspect `-Xlog:cds=info`, `-Xlog:class+load=info`, and compatibility conditions, then rebuild the archive if appropriate.

**Q23.** Do two pods on different hosts share physical pages via CDS?

**Answer:** No. Each host has its own page cache/RAM; CDS files can be deployed identically, but do not create cross-host shared physical memory.

**Q24.** When should archives be created?

**Answer:** In CI/build/staging with the JDK/application/config matching production, then measure before/after; avoid stale archives from different releases.

## 26. Practical adoption checklist

1. Identify the target system's **JDK vendor/build/version**.
2. Verify default CDS with `-Xlog:cds=info`.
3. Compare `-Xshare:off` and `-Xshare:auto` with the same workload.
4. If you want to archive application classes, package the JAR per the JDK 17 workflow.
5. Run the application with `ArchiveClassesAtExit` to create an appropriate dynamic top archive.
6. Use `SharedArchiveFile` on subsequent runs.
7. Verify class origin via `-Xlog:class+load=info`.
8. Verify static initializers still run properly in each process.
9. Record archive size and class coverage; do not optimize just for the sake of having a file.
10. Check that the JAR is unchanged, classpath/modulepath validity, and base archive compatibility.
11. Do not rely on `-Xshare:on` in production.
12. If custom loaders/agents are present, test with the exact production launch command.
13. For containers, distinguish restart time from image pull/start overhead.
14. For memory, compare footprint when multiple JVMs run concurrently; do not sum RSS without context.
15. Run diagnostic logging **separately** from performance baselines.
16. Measure process wall time, application readiness, first request, and memory footprint across multiple runs.
17. Do not confuse CDS with JIT warm-up, class init, or database connection setup.
18. Treat the archive as a managed/versioned artifact alongside the JDK and app, regenerating it when the build changes.

### Conclusion

```text
JAR/class bytes              CDS archive (.jsa)
     |                             |
  conventional                    runtime-ready
  loading path                    class metadata
     |                             |
     +---------- HotSpot ----------+
                       |
              map compatible archive
                       |
         +-------------+-------------+
         |                           |
    JVM process A               JVM process B
         |                           |
    shared file pages when supported
         |                           |
    private JVM heap             private JVM heap
    private statics              private statics
    private JIT state            private JIT state

CDS speeds eligible class data reuse.
CDS does NOT replace class initialization or JIT.
```

**In summary:** CDS helps HotSpot **avoid recreating all metadata for common classes** every time a new JVM process starts. The archive is **memory-mapped**, enabling OS-level sharing of read-only pages and reuse of runtime-ready data. When extended to AppCDS, many application/library classes can also participate. However, each JVM still has its own **heap, static fields, threads, GC, and JIT state**; `<clinit>`, application, and business workflows must still operate under standard Java semantics. Evaluate benefits via **archive-use logs and real startup/memory benchmarks**, not merely by the existence of a `.jsa` file.

### Official documentation

- [Oracle JDK 17 — Class Data Sharing](https://docs.oracle.com/en/java/javase/17/vm/class-data-sharing.html): default archives, memory footprint, dynamic AppCDS, `-Xshare` options.
- [Oracle JDK 17 — `java` Command, Application Class Data Sharing](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): static/dynamic workflows, classpath/modulepath restrictions, `SharedArchiveFile`, `ArchiveClassesAtExit`, and `jcmd VM.cds`.
- [dev.java — CDS and AppCDS in HotSpot](https://dev.java/learn/jvm/other-tools/cds-appcds/): memory mapping mechanism, `-Xshare:auto` default, and guide.
- [OpenJDK JEP 310 — Application Class-Data Sharing](https://openjdk.org/jeps/310): extension to application classes.
- [OpenJDK JEP 341 — Default CDS Archives](https://openjdk.org/jeps/341): default archive bundled with the JDK.
- [OpenJDK JEP 350 — Dynamic CDS Archives](https://openjdk.org/jeps/350): dynamic top archive and dump at process exit.
- [JVMS §5 — Loading, Linking, Initializing (Java SE 17)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): JVM class loading/initialization semantics.
- [JLS §12.4 — Initialization of Classes and Interfaces (Java SE 17)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4): active use and class initialization.
