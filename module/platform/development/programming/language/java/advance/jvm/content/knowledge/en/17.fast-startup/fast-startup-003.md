# AppCDS, Static Archives, and Dynamic Archives in HotSpot Java 17

**AppCDS (Application Class-Data Sharing)** is a HotSpot JVM mechanism that helps **reuse class data prepared in a format suitable for fast loading** via a **CDS archive** file. It extends the **CDS (Class Data Sharing)** idea from platform library classes to classes used by applications/libraries as well. With Java 17, there are two main ways to create a custom archive for an application:

- **Static archive:** run a trial of the application to collect a class list, then use **`-Xshare:dump`**, `-XX:SharedClassListFile`, and `-XX:SharedArchiveFile` to generate the archive.
- **Dynamic archive:** run the application with **`-XX:ArchiveClassesAtExit=<file.jsa>`**; upon exit, the VM creates an additional archive on top of the **base archive**. Subsequent runs specify `-XX:SharedArchiveFile=<dynamic.jsa>` to reuse it.

The goal of AppCDS is to improve **startup time** and potentially reduce **memory footprint** when multiple JVM processes use the same archive; it is **not** a tool to compile all Java source into a native executable, not a cache for business computation results, and does not guarantee that every class in the application will be archived.

This lesson is in the **Fast Startup** topic, focusing on HotSpot/JDK **17**. You will understand the nature of class metadata, the differences between static/dynamic archives, how to create a JAR for testing, the dump/use/verify workflow, constraints on class path, JDK build, base archive, real-world performance, and common deployment mistakes. The example programs use Java 17 with deterministic stdout; messages from CDS logging are **not presented as fixed stdout**.

## 1. Why does class loading affect startup?

When launching a Java application, the JVM needs to find and load the required classes; depending on the case, it also performs steps such as reading class files, decoding class structures, verification, linking, and initialization. In applications with many dependencies, operations with JAR files and metadata of thousands of classes can contribute significantly to the time before the first functionality is ready to serve.

```text
Normal:
  JAR / JDK runtime image
      │
      ▼
  Find bytes for class
      │
      ▼
  Load / verify / link according to JVM mechanism
      │
      ▼
  Runtime class metadata and execution

With CDS/AppCDS (conceptual model):
  Prepared CDS archive
      │ map appropriate data regions
      ▼
  Part of metadata can be reused faster
      │
      ▼
  Runtime classes must still comply with Java semantics
```

CDS reduces part of the startup work thanks to data in a HotSpot-friendly format and the **memory mapping** mechanism. It **does not skip every step of the Java class life cycle**; checks and operations that must occur when runtime actually uses the class must still ensure correctness.

### 1.1. How is CDS different from AppCDS?

| Concept | Main content | Purpose |
| --- | --- | --- |
| **Default CDS** | A set of platform classes pre-packaged by the JDK or already archived | Speeds up JVM processes even without application configuration |
| **AppCDS** | Extends archiving to eligible application and library classes | Reduces application-specific startup work |
| **Static CDS archive** | File built in an explicit dump step, can use a class list | Controls the set of prepared classes |
| **Dynamic CDS archive** | Additional file written at the end of a run or via runtime support | Fewer steps, based on classes that were actually loaded |
| **Base archive** | Archive mapped first, usually the JDK's default CDS archive | Serves as the foundation referenced by the dynamic archive |
| **Top-layer dynamic archive** | Contains additional classes not yet in the base archive | Extends the base without rewriting all platform classes |

In Java 17, the terms **static** and **dynamic** mainly refer to **how/which layer archives are created, used, and stacked**. "Dynamic" does not mean the archive file automatically updates continuously every time a new class is loaded across all runs.

### 1.2. A CDS archive is not a heap dump

A `.jsa` file is a file storing **data suitable for HotSpot's class data sharing mechanism**, not:

- A `.hprof` heap dump containing live Java objects.
- `.class` files generated directly by `javac`.
- A JAR/WAR packaging all bytecode and resources.
- A native executable like the result of a native-image build.
- A JIT profile dump or C2-compiled machine code for universal reuse.

**The archive does not replace the original JAR.** At runtime, the application still needs the right class path/module path, resources, configuration, and bytecode that can be checked for compatibility according to CDS rules.

## 2. Memory mapping mechanism and memory savings

When the JVM starts up and accepts a CDS archive, it can **memory-map** the prepared data regions. Read-only parts can be shared by the operating system as physical pages across multiple JVM processes on the same host.

```text
             CDS archive on disk
                    │
          ┌─────────┼─────────┐
          │         │         │
          ▼         ▼         ▼
      JVM proc A  JVM proc B  JVM proc C
          │         │         │
          └── mapped read-only pages ──┘
                 can be physically shared
```

**Two potential benefits:**

1. **Startup:** reduces the cost of having to re-read/re-prepare part of the class metadata in each process.
2. **Total footprint:** multiple JVMs can share some memory-mapped pages, reducing per-process private memory compared to each process having to create similar data on its own.

However:

- **Not the entire archive consists of perfectly shared read-only pages.**
- Each process's `RSS` may count shared pages, so **summing RSS across multiple JVMs easily double-counts**; use PSS/USS and OS-specific tools when evaluating total physical memory.
- The archive also takes up disk space and has metadata overhead.
- There is no guaranteed formula like "with 10 JVMs, RAM drops by exactly 10x."
- The savings depend on the number of classes actually shared, metadata volume, JDK, OS, and startup behavior.

### 2.1. Why not archive every available class?

An archive includes class metadata in a prepared format, which can be larger than the bytecode data in a JAR or runtime image. Oracle notes that storing CDS classes in an optimized format can take several times more space than the original class files. Archiving application classes that are never needed can waste disk and build time.

Therefore, it is necessary to distinguish between **classes present on the classpath** and **classes actually loaded on the code paths that need optimization**. If you only run a minimal startup to create the archive, classes loaded lazily by the first request may not be in the archive yet.

## 3. Default CDS archive of JDK 17

Modern JDK distributions usually provide a **default CDS archive** with the JDK, typically the `classes.jsa` file in the HotSpot runtime directory; Oracle java command documentation lists the corresponding locations depending on the OS.

```text
Linux/macOS, for example:
  $JAVA_HOME/lib/server/classes.jsa

Windows, for example:
  %JAVA_HOME%\bin\server\classes.jsa
```

**Do not use example paths as a mandatory assumption for every vendor/build.** Some distributions package differently, paths may change, and the default archive may be absent.

Since JDK 12, the default CDS archive has been packaged in many popular JDK builds. In JDK 17, this mechanism is usually **enabled in auto mode** when the JVM has a suitable archive; you do not need to run `-Xshare:dump` manually just to use an already available default archive.

### 3.1. Checking with `-Xshare` modes

| Option | Meaning | When to use? |
| --- | --- | --- |
| `-Xshare:auto` | Try to use CDS if possible; success is not mandatory | Suitable for normal application runs |
| `-Xshare:off` | Disable using shared archive | Comparison baseline or collecting a class list |
| `-Xshare:on` | Require CDS to be usable; if not, the JVM may fail to start | Only use in tests to verify the archive |
| `-Xshare:dump` | Static archive creation mode | Dump step, does not run the application's main in the usual sense |

**Warning:** Oracle recommends avoiding `-Xshare:on` in production because it can prevent the JVM from starting when the archive is incompatible or the configuration changes. `auto` is friendlier behavior for environments with varying runtime conditions.

## 4. Static archive: trial run → class list → dump → reuse workflow

A **Static AppCDS archive** is a file generated in a **separate dump step** based on a class list and prepared inputs.

```text
            appcds-demo.jar
                   │
          1. Trial application run
          -Xshare:off
          -XX:DumpLoadedClassList=app.classlist
                   │
                   ▼
             app.classlist
                   │
          2. Explicit static dump
          -Xshare:dump
          -XX:SharedClassListFile=app.classlist
          -XX:SharedArchiveFile=app-static.jsa
                   │
                   ▼
             app-static.jsa
                   │
          3. App runtime
          -XX:SharedArchiveFile=app-static.jsa
                   │
                   ▼
           startup can be faster
```

**Advantage:** the workflow can be set up as a build/release step with deterministic inputs, making it convenient to track the class list, archive, and deployment policies.

**Cost:** requires a trial run step to generate the class list and a separate dump step; has stricter constraints on class path/JAR files. Classes loaded outside the trial path may not benefit.

### 4.1. What does `DumpLoadedClassList` do?

When run with:

```bash
java -Xshare:off -XX:DumpLoadedClassList=app.classlist \
  -cp appcds-demo.jar AppCdsDemo
```

The JVM executes the program to collect the **list of loaded classes**. The `app.classlist` file is the input for the subsequent dump step; it **is not an archive containing optimized classes**.

Do not replace the meaning of `-XX:DumpLoadedClassList` with "record every class file in all JARs" — the list reflects the classes loaded during the trial run and runtime conditions, not the entire classpath.

### 4.2. `SharedClassListFile` and `SharedArchiveFile`

Dump step:

```bash
java -Xshare:dump \
  -XX:SharedClassListFile=app.classlist \
  -XX:SharedArchiveFile=app-static.jsa \
  -cp appcds-demo.jar
```

- `-Xshare:dump` tells the VM to create the archive.
- `SharedClassListFile` feeds the observed class list into the dump step.
- `SharedArchiveFile` sets the output archive file name.
- `-cp appcds-demo.jar` specifies the appropriate classpath for dumping.
- This is **not** a command to run `AppCdsDemo.main()` a second time; no main class is needed at the end.

**Important in Java 17:** According to Oracle launcher documentation, when creating a static archive with application classes, **the classpath in this illustrated phase contains only JAR files**. Avoid using a folder `out/` or `target/classes` with unpacked classes instead of a JAR; classes located in non-empty directories on the classpath are a source of errors/not archived under the corresponding CDS constraints.

### 4.3. `SharedArchiveFile` at runtime

To use the static archive:

```bash
java -XX:SharedArchiveFile=app-static.jsa \
  -cp appcds-demo.jar AppCdsDemo
```

The application still runs `AppCdsDemo.main()` normally. If the archive is valid and eligible for use, some class metadata is loaded from the shared archive instead of everything being prepared from the original source via the non-CDS path.

Do not infer "exiting with code 0" means 100% of application classes were shared; you must enable logging and check class sources.

## 5. Dynamic archive: writing additional classes when the application exits

**Dynamic CDS archive** was introduced to make AppCDS easier to use: run the application **once** with `-XX:ArchiveClassesAtExit=<file.jsa>`, HotSpot collects enough information for the archive from the classes loaded during the run, then writes the **top-layer archive** when the application finishes and performs the dump.

```text
              default base CDS archive
                       │
                       │ JVM runs AppCdsDemo
                       ▼
       java -XX:ArchiveClassesAtExit=app-dynamic.jsa
                 -cp appcds-demo.jar AppCdsDemo
                       │
                 Runtime class loading
                       │
                 JVM shutdown / archive dump
                       ▼
                 app-dynamic.jsa
            (additional classes vs base archive)
                       │
                       ▼
         next run -XX:SharedArchiveFile
                       │
                       ▼
                   Reuse base + top
```

Creation command:

```bash
java -XX:ArchiveClassesAtExit=app-dynamic.jsa \
  -cp appcds-demo.jar AppCdsDemo
```

Command to use the archive:

```bash
java -XX:SharedArchiveFile=app-dynamic.jsa \
  -cp appcds-demo.jar AppCdsDemo
```

With the default base archive, HotSpot can retrieve base information from the dynamic archive's header to re-map the appropriate base, so runtime does not necessarily have to explicitly write `base.jsa:app-dynamic.jsa`.

### 5.1. Does "Dynamic" mean the archive updates itself while the JVM is running?

Not in that colloquial sense. With `ArchiveClassesAtExit`:

1. While the JVM is running, it loads classes according to the workload.
2. Upon exit via a supported dump mechanism, the VM **creates the archive file**.
3. **The next run** is what uses the newly created file.

The file is not "a caching layer automatically rewritten after every class load" within a running process. If deployment changes classes/JARs, the old archive may no longer be usable and needs to be regenerated.

### 5.2. Why does a dynamic archive still need a base?

The JDK already has many platform classes in the default CDS archive. The dynamic archive **does not need to copy all those classes again**, instead adding application/library classes not yet in the base. This saves space and makes the creation process simpler.

If the default base is missing or incompatible with the configuration to be dumped, the dynamic dump command may fail. You must check the logs rather than treating every dynamic archive error as "no file write permission."

### 5.3. Common mistake: archive creation command and archive usage command are different

| Option | Phase | Result |
| --- | --- | --- |
| `-XX:ArchiveClassesAtExit=app-dynamic.jsa` | Sample run/dynamic dump | Requests **creating** the archive when the application exits |
| `-XX:SharedArchiveFile=app-dynamic.jsa` | Reuse run | Requests **using** an existing archive |
| `-XX:DumpLoadedClassList=app.classlist` | Trial run for static | **Only** creates a class list |
| `-Xshare:dump` + `SharedClassListFile` | Static dump | Creates a **static archive** |
| `-Xshare:off` | Baseline | Disables using archive |

Do not use `ArchiveClassesAtExit` instead of `SharedArchiveFile` and expect fast startup immediately in the very run that is creating the archive.

## 6. Two archive layers: static base and dynamic top

HotSpot Java 17 supports a base archive and a top-layer dynamic archive when configured according to the application mechanism. Oracle states the general form:

```text
-XX:SharedArchiveFile=<static_archive>:<dynamic_archive>
```

**On Windows, the separator is a semicolon `;` instead of a colon `:`.** Paths in the option need to be quoted appropriately for the shell if they contain spaces/special characters.

POSIX example, when a custom base named `base.jsa` has been built:

```bash
# Create dynamic archive on top of custom base:
java -XX:SharedArchiveFile=base.jsa \
  -XX:ArchiveClassesAtExit=top.jsa \
  -cp appcds-demo.jar AppCdsDemo

# Explicitly use both base and top:
java -XX:SharedArchiveFile=base.jsa:top.jsa \
  -cp appcds-demo.jar AppCdsDemo

# If dynamic archive header stores appropriate base info:
java -XX:SharedArchiveFile=top.jsa \
  -cp appcds-demo.jar AppCdsDemo
```

**Order matters:** base is mapped first, top is added after. However, distinguish "base archive" and "top archive" from "static/dynamic archive created at what time"; the two names describe **roles in the archive structure**, not an arbitrary two-tier cache system supporting chaining unlimited files.

### 6.1. What happens if a class is in both layers?

The dynamic archive mainly contains classes not yet in the base, because the goal is to avoid unnecessary duplicate class metadata. Users should not imagine manually merging two `.jsa` files via byte concatenation; **the archive format and relationship metadata between the two layers belong to the VM**.

If the base archive is replaced with an incompatible file, top may fail to map; do not try to solve this by freely copying/moving files and ignoring dependency checks.

### 6.2. Must match JDK version and build

CDS archives are **HotSpot VM implementation artifacts**, not a Java SE portable serialization format. They depend on the JDK build, VM settings, class metadata layout, and other components. Do not build on JDK 17.0.x from vendor A and assume it works on JDK 17.0.y from vendor B; even patch/build updates may require regenerating the archive.

**Safe deployment rule:** generate the archive using the exact same JDK image/VM build that will run the application in the same release artifact. When upgrading JDK, classpath, or application JAR, **regenerate archives and verify**.

## 7. Java 17 lab: standalone program and proper JAR for archiving

Save the file **`AppCdsDemo.java`**:

```java
import java.util.List;
import java.util.Locale;

public final class AppCdsDemo {
    static final class Formatter {
        String upper(String input) {
            return input.toUpperCase(Locale.ROOT);
        }
    }

    static final class Counter {
        int lengthSum(List<String> inputs) {
            int sum = 0;
            for (String input : inputs) {
                sum += input.length();
            }
            return sum;
        }
    }

    public static void main(String[] args) {
        List<String> data = List.of("alpha", "beta", "gamma");
        Formatter formatter = new Formatter();
        Counter counter = new Counter();

        System.out.println("records=" + data.size());
        System.out.println("lengthSum=" + counter.lengthSum(data));
        System.out.println("first=" + formatter.upper(data.get(0)));
        System.out.println("done");
    }
}
```

**Compile and package on JDK 17:**

```bash
mkdir -p out
javac --release 17 -d out AppCdsDemo.java
jar --create --file appcds-demo.jar --main-class AppCdsDemo -C out .
```

The commands above use a POSIX shell, creating a JAR file from compiled class files. `jar` is a tool bundled with the JDK. A JAR file with a proper `Main-Class` manifest can be run with `java -jar appcds-demo.jar`, but to compare CDS flags in this lesson we standardize on **`-cp appcds-demo.jar AppCdsDemo`** in all phases.

**Baseline without logging enabled:**

```bash
java -cp appcds-demo.jar AppCdsDemo
```

**Exact application stdout on Java 17:**

```text
records=3
lengthSum=14
first=ALPHA
done
```

`"alpha"` has length 5, `"beta"` has length 4, `"gamma"` has length 5, so `lengthSum=14`. `Locale.ROOT` keeps uppercase conversion rules stable, avoiding machine locale dependence. `Formatter` and `Counter` are separate inner classes, packaged into the JAR along with the main class.

### 7.1. Why create a JAR instead of running `java -cp out AppCdsDemo`?

For **static AppCDS archives** on JDK 17, Oracle java launcher documentation requires the classpath in archive creation examples to contain **only JAR files**, not non-empty directories of application classes. Using a consistent JAR for trial run, dump, and runtime helps:

- Match classpath consistently.
- Avoid class location mismatches.
- Reduce the risk of the archive being rejected due to classes residing in a directory.
- Have a clear artifact to put into CI/CD.

The command `java -cp out AppCdsDemo` is still a normal way to run class files outside the AppCDS lab workflow, but **is not chosen as the main path in the dump step** here.

### 7.2. "The program outputs the right stdout" does not prove AppCDS is working

All three of the following runs can produce the **same 4 lines of application stdout**:

```bash
java -Xshare:off -cp appcds-demo.jar AppCdsDemo
java -cp appcds-demo.jar AppCdsDemo
java -XX:SharedArchiveFile=app-static.jsa -cp appcds-demo.jar AppCdsDemo
```

The last line requires `app-static.jsa` to have been validly created. Actual startup time and class load sources may differ, but **Java semantics must not change** because of the archive. You must enable CDS/class-load logging to verify archives.

## 8. Lab A — creating and using a static archive in Java 17

**Step 1 — Trial run to collect the class list:**

```bash
java -Xshare:off \
  -XX:DumpLoadedClassList=app.classlist \
  -cp appcds-demo.jar AppCdsDemo
```

If successful, the application prints the 4 lines like the baseline and the VM creates `app.classlist`. Do not expect the class list file to be Java code or a `.jsa` binary.

**Step 2 — Dump static archive:**

```bash
java -Xshare:dump \
  -XX:SharedClassListFile=app.classlist \
  -XX:SharedArchiveFile=app-static.jsa \
  -cp appcds-demo.jar
```

This is the step that creates `app-static.jsa`, usually printing HotSpot logs/diagnostics; **it does not print the 4 business lines from `AppCdsDemo.main()`** because this is not a normal application execution.

**Step 3 — Run again with the archive:**

```bash
java -XX:SharedArchiveFile=app-static.jsa \
  -cp appcds-demo.jar AppCdsDemo
```

Business lines remain:

```text
records=3
lengthSum=14
first=ALPHA
done
```

**Step 4 — Verify classes are loaded from the archive:**

```bash
java -XX:SharedArchiveFile=app-static.jsa \
  -Xlog:cds=info,class+load=info \
  -cp appcds-demo.jar AppCdsDemo
```

In appropriate HotSpot logs, a class loaded from the shared archive may report a source equivalent to **`source: shared objects file`**. That is an indicator that the class could use CDS data. Conversely, a class reporting `source: file:/.../appcds-demo.jar` was usually loaded from the JAR in that run, which does not prove the entire archive failed.

**Do not use an assumed log line as proof** that `AppCdsDemo` definitely came from CDS in every environment. Filter by class name/GC/VM build and observe real logs.

### 8.1. What if the class list records too few classes?

The trial run only loads the classes that the program actually touches. If a framework has lazy initialization, plugins, reflection, or request paths not exercised during the trial, the class list may not contain them.

You need to build a **sufficiently representative warm-up scenario**: initialize the components to optimize, execute representative requests, then shut down cleanly to use the same artifact. Do not assume "opening the app for a few seconds means every class in the JAR is archived."

### 8.2. What if the static archive is created successfully but the app does not use it?

Check:

- Did runtime actually specify `-XX:SharedArchiveFile=app-static.jsa`?
- Are you using the same JDK build that created the archive?
- Was the JAR rebuilt/modified in bytecode/timestamps related to checks?
- Does runtime `-cp` have the exact same path and order as during dump?
- Are there options that disable CDS, such as `-Xshare:off`?
- Does `-Xlog:cds=debug` report why the archive was rejected?
- If the error is due to application classes in non-empty directories, use a packaged JAR instead of an exploded folder.

## 9. Lab B — creating and using a dynamic archive in Java 17

Dynamic dump is simpler because **there is no need to create a class list beforehand**.

**Step 1 — Run the application while requesting a dump on exit:**

```bash
java -XX:ArchiveClassesAtExit=app-dynamic.jsa \
  -cp appcds-demo.jar AppCdsDemo
```

Program stdout:

```text
records=3
lengthSum=14
first=ALPHA
done
```

After the JVM finishes and the dynamic dump succeeds, `app-dynamic.jsa` is created. Writing the archive at the end of the application can make **the archive-creating run slower**, especially at shutdown; this is preparation work for subsequent startups, **not an optimization that makes the dump run itself faster**.

**Step 2 — Run again using the dynamic archive:**

```bash
java -XX:SharedArchiveFile=app-dynamic.jsa \
  -cp appcds-demo.jar AppCdsDemo
```

Startup is allowed to use **default static base archive + dynamic top archive**. The application must have the same semantics and stdout.

**Step 3 — Verify CDS/class loading:**

```bash
java -XX:SharedArchiveFile=app-dynamic.jsa \
  -Xlog:cds=info,class+load=info \
  -cp appcds-demo.jar AppCdsDemo
```

Read the logs to distinguish classes from the base/archive from those still loaded directly from the JAR/runtime image. A dynamic archive does not necessarily contain all loaded classes; there are also conditions on class loader type, archive eligibility, and consistency checks.

### 9.1. Dynamic archive is not guaranteed to be written when the application dies abnormally

`ArchiveClassesAtExit` requires the JVM to perform the dump process upon an appropriate exit. If the process receives `SIGKILL`, crashes natively, gets a container hard kill, or the OS cuts resources, a complete archive is not guaranteed to be created.

In CI, **check the process exit code, file existence, reasonable size, and a re-run with logs proving the archive can be used**. Do not let a pipeline just run `test -f app-dynamic.jsa` and declare it production-ready.

### 9.2. Dynamic archive does not mean "no longer need the JAR"

Even with the archive present, runtime still needs the right JAR/classpath/resources. The archive does not package arbitrary resources, service provider configurations, native libraries, network endpoints, TLS materials, or application data.

If rebuilding `appcds-demo.jar` changes the binary, the archive may be rejected; the archive must be regenerated when packaging changes.

## 10. Comparison table of static and dynamic archives

| Criterion | Static archive | Dynamic archive |
| --- | --- | --- |
| Primary creation method | Trial run + create class list + `-Xshare:dump` | One run with `-XX:ArchiveClassesAtExit` |
| Intermediate class list file | **Yes** in common workflow | **Not needed** |
| Runs main during dump? | Trial run step **yes**, dump step **no** | Archive-creating run **yes** |
| Relationship with base | Can act as main/base archive | Usually a top-layer on top of base |
| Number of preparation steps | More | Fewer |
| Class contents | Based on observed list and eligibility | Eligible loaded classes not yet in base |
| Size | Can be larger due to more base data | Usually more compact as it only writes additional classes |
| Use case | Controlled release/build pipeline, custom base needed | Quickly enabling AppCDS or capturing from runtime |
| At runtime | `-XX:SharedArchiveFile=static.jsa` | `-XX:SharedArchiveFile=dynamic.jsa` or `base:dynamic` |
| Limitations | Classpath/JDK/archive compatibility and CDS rules | **Also** depends on base/JDK/classpath, successful exit/dump |
| Guarantees all classes? | **No** | **No** |
| Guarantees faster startup? | **No** | **No** |

**Mnemonic:** Static: **class list then dump**. Dynamic: **run app then dump at exit**. Both: **re-use via `SharedArchiveFile`**, Java-level results unchanged.

## 11. The `jcmd VM.cds` command in Java 17

The Oracle JDK 17 launcher manual states that a CDS archive can be created from a **running JVM** via `jcmd <pid> VM.cds ...`, reducing the need to modify startup scripts. This is a useful advanced technique when systems are complex.

Command template, replacing `<pid>` with the actual PID:

```bash
# Create static CDS archive from running JVM when environment supports it:
jcmd <pid> VM.cds static_dump live-static.jsa

# Create dynamic archive from JVM with recording enabled at startup:
jcmd <pid> VM.cds dynamic_dump live-dynamic.jsa
```

To support **dynamic_dump** per Oracle Java 17 documentation, the target JVM needs to be started with:

```bash
java -XX:+RecordDynamicDumpInfo \
  -cp appcds-demo.jar AppCdsDemo
```

Note: `AppCdsDemo` finishes very quickly so it is **not suitable for you to grab the PID in time and run jcmd**. The `jcmd` example here is meant to explain the syntax for a **long-lived service**, not to promise you can attach to the short demo.

### 11.1. `jcmd` requires operational conditions

Attaching requires the right process, OS/owner permissions, corresponding JDK tooling, HotSpot support, and an environment that allows attach. Container security policies, the disable-attach flag, or early process termination can prevent the command from running.

Do not use `jcmd VM.cds dynamic_dump` as a Java source command or a standard Java SE API inside an application. It is a diagnostic command of HotSpot/JDK tools.

### 11.2. Choosing between dump-at-exit and `jcmd`

- If you control the script and have a natural warm-up + shutdown path, `ArchiveClassesAtExit` is usually simpler.
- If the app/server is running in a warmed-up state and can be validly attached to, `jcmd` can capture class data after representative traffic has occurred.
- For a controlled static archive, class list + explicit dump is easy to put into a pipeline as deterministic steps.

Do not invoke `jcmd` in production under high load without measuring resource impact/overhead and having a rollback strategy.

## 12. Classpath and module path limitations on Java 17

### 12.1. Non-empty directories on the classpath are problematic

Oracle Java 17 CDS documentation specifies constraints for `-classpath`/`-Xbootclasspath/a` and module path. In AppCDS archive workflows, **non-empty directories** are a source of incompatibility; to archive application classes reliably, **package them as JARs**.

Example **not recommended** as the way to create a static archive in this lesson:

```bash
java -Xshare:off -XX:DumpLoadedClassList=app.classlist \
  -cp out AppCdsDemo
```

This command can run compiled Java source in the form of exploded class files, but does not satisfy the "classpath contains only JARs" condition for a static AppCDS archive in the dump step per the Oracle example.

**Do not interpret `java -cp out ...` as never running:** it runs like a normal Java application. The limitation here is **CDS archiving/sharing eligibility**, not that the Java launcher forbids directories.

### 12.2. Module path and modular JARs

With `--module-path`, CDS supports appropriate **modular JAR** cases; exploded modules/non-empty directories on the module path may be restricted per Oracle docs.

Do not infer that an application running on module path means classes from modules are definitely archived. You need to verify in logs and ensure valid module configuration.

### 12.3. Classpath must be consistent at dump time and runtime

According to Oracle JDK 17 launcher docs:

- **Classpath at archive creation time** must be **equal to or a prefix of the runtime classpath**, according to the corresponding CDS rules.
- The order of JARs matters in class resolution.
- If JAR files on the classpath or module path are **modified after archive creation**, the archive will not be used per integrity/compatibility checks.
- Some startup options such as `--upgrade-module-path`, `--patch-module`, and `--limit-modules` can cause CDS to be disabled.

Do not just compare the total number of JARs or directories: you need the exact contents, order/path, and appropriate VM config. A changed symbolic link or relative path can also make deployment hard to debug; use reproducible packaging/paths and verify.

### 12.4. Fat JAR, nested JAR, and custom class loaders

Frameworks using executable/fat JARs and nested library JARs have **different class loader behavior** than the `-cp appcds-demo.jar` example. AppCDS support for classes loaded by custom loaders has its own conditions/limitations; do not claim "every Spring Boot nested jar class is automatically archived like a flat jar classpath."

When an application uses a custom class loader:

1. Check the actual JDK 17 and framework versions.
2. Observe class loading sources using `-Xlog:class+load=info`.
3. Identify which classes come from the archive and which load from other loader paths.
4. Choose a static/dynamic dump workflow suited to how the loader receives bytecode and packages artifacts.
5. Do not use an archive from one build and swap in a fat jar from another build without regenerating.

## 13. Archive compatibility: JDK, classpath, JVM configuration

CDS is not a JVM-independent "write once, run anywhere" format. An archive can be rejected in the following cases:

- JDK vendor/build/patch differs from where the archive was created.
- Classpath JARs were rebuilt, modified, or ordered incompatibly.
- Application JAR changed path/content after dump.
- Dynamic top was created on top of a base archive that is no longer suitable.
- Some VM options/GC/platform settings affect archive layout or eligibility.
- The runner is using `-Xshare:off`.
- Runtime is restricted by environment filesystem permissions/memory mapping.
- The archive file is missing, corrupt, or incomplete.
- Different module configuration or options that disable CDS.

**Practical consequence:** treat the archive as an **artifact tied to the JDK image and application build**. When either changes, regenerate + rerun validation; do not blindly reuse an old `.jsa` file.

### 13.1. Do not manually edit `.jsa` files

Archive files have HotSpot's internal binary structure, not a text template. Do not use a text editor to change the list of classes in an archive or concatenate two archives with `cat`. To change classes, re-run the dump with the right inputs.

### 13.2. How does the JVM handle an invalid archive?

Behavior depends on `-Xshare` mode, error type, and HotSpot configuration:

- In auto mode, the VM may ignore an unusable archive and continue running without CDS in many situations.
- With `-Xshare:on`, being unable to use the archive is usually treated as a startup error.
- If running the archive-creating dump step itself, an error may cause the dump command to fail and not create a complete file.

Do not claim every CDS error silently falls back; **read the exit code and `-Xlog:cds` of the actual run**.

## 14. Verify the archive instead of guessing from the filename

Run:

```bash
java -XX:SharedArchiveFile=app-dynamic.jsa \
  -Xlog:cds=info,class+load=info \
  -cp appcds-demo.jar AppCdsDemo
```

Signs to look for (depending on HotSpot build):

- Logs show the corresponding archive was opened/mapped successfully.
- Information that one or more classes were loaded from **shared objects file**.
- No diagnostic indicating the archive was ignored or invalid.
- The Java program prints the exact 4 business lines as the baseline.
- Exit code 0 and no `LinkageError`/related resource access errors.

### 14.1. Three scenarios and how to interpret them

| Observed log | Can conclude | Cannot yet conclude |
| --- | --- | --- |
| `class+load` for a JDK class `source: shared objects file` | A platform class was shared | All application classes are in AppCDS |
| `class+load` for `AppCdsDemo` `source: shared objects file` | That application class actually loaded from the archive in this run | Every class in all dependencies has been archived |
| Log reports archive incompatible or ignored | The run could not use the archive as expected | The Java program must have wrong logic or be slower by how many ms |
| `-Xshare:off` and class loaded from JAR | Comparison mode without CDS | Proves the archive has no value in other modes |

### 14.2. Is reading logs by `GC ID` relevant?

GC logs such as `-Xlog:gc*=info` **are not a direct CDS verification tool**. CDS focuses on **class loading/startup metadata**; to know if classes use the archive, look at the `cds` and `class+load` tags. GC metrics can be useful for comparing memory/overall performance, but do not replace class load source information.

### 14.3. `-Xlog:cds=debug` when details are needed

```bash
java -XX:SharedArchiveFile=app-dynamic.jsa \
  -Xlog:cds=debug,class+load=info \
  -cp appcds-demo.jar AppCdsDemo
```

Debug logs may contain layout/mapping/checks information; output differs across JDK builds. In production, limit logging volume. Do not record an entire debug log as the "deterministic output" of the demo because timestamps, addresses, class counts, and VM choices vary.

## 15. Measuring AppCDS performance properly

**AppCDS is an optimization for startup and footprint**, not proof that a business program runs every task faster.

### 15.1. Defining the start-up metric

There are at least three common ways:

- **Process launch → first application log:** easy to measure but may not include all initialization.
- **Process launch → HTTP server ready:** suitable for real services, requires a reliable readiness probe.
- **Process launch → first successful business response:** includes first touch of lazy paths and upstream dependencies.

You must use the **same definition** when comparing `-Xshare:off`, default CDS, and AppCDS. For a simple demo, you can measure process wall time, but a very fast application makes OS/JIT/terminal noise large relative to the AppCDS difference.

### 15.2. Three comparison configurations

```bash
# Baseline completely without CDS:
java -Xshare:off -cp appcds-demo.jar AppCdsDemo

# Use default CDS when possible:
java -Xshare:auto -cp appcds-demo.jar AppCdsDemo

# Use custom dynamic archive:
java -Xshare:auto \
  -XX:SharedArchiveFile=app-dynamic.jsa \
  -cp appcds-demo.jar AppCdsDemo
```

**Only compare speed after verifying the third archive is actually used.** If the custom archive is not used and the JVM falls back, you are comparing two default CDS configurations, not AppCDS.

You can add the static archive to the benchmark as a fourth configuration. Keep the JDK image, classpath, heap/GC settings, workload, host, and equivalent warm-up page cache fixed.

### 15.3. Warm OS page cache can affect results

A first-time command run may read JARs/archive from uncached storage; subsequent runs have a warm page cache. If you always run "no CDS" first and "AppCDS" second, results may be skewed because the OS has cached the files.

You should interleave test run order, run multiple times, and report **median/p95/min/max**, along with resource contention status. Only record gains that are repeatable on target hardware and deployment.

### 15.4. Distinguishing startup time from throughput

A web app starting 200 ms faster does not necessarily have higher req/s throughput after warm-up. JIT compilation, database latency, lock contention, and GC behavior determine steady-state throughput.

Do not claim AppCDS lets C2 skip profiling, inline all methods, or replace all JIT compilation. AppCDS mainly reuses class-related metadata; JIT code/compilation still operates by its own mechanisms.

### 15.5. Measuring footprint across multiple JVM processes

To measure memory benefit when deploying multiple JVM instances:

1. Run the same app/JDK image in multiple processes on the same host.
2. Compare no-CDS, default-CDS, and AppCDS configurations.
3. Collect **PSS/USS** or memory counters that distinguish shared/private pages if the OS supports it.
4. Measure both CPU/startup and memory after readiness; avoid comparing at different lifecycle points.
5. Do not blindly sum RSS and interpret it as total physical RAM used.
6. Include `.jsa` disk footprint in operations if there are multiple versions.

In containers/Kubernetes, each pod has a different namespace/storage/mount; the ability to share pages depends on whether the archive is mapped from the same page-cache-backed file/host context. Do not assume every pod shares physical pages identically.

## 16. Integrating AppCDS into build and deployment

A practical workflow:

```text
1. Choose standard JDK 17 image/vm build
           │
           ▼
2. Build immutable application JARs
           │
           ▼
3. Run representative startup/warm-up paths
           │
           ▼
4A. Static: class list → Xshare:dump
4B. Dynamic: ArchiveClassesAtExit / runtime dump
           │
           ▼
5. Verify archive under SAME JDK + jars + classpath
           │
           ▼
6. Package JDK + app jars + CDS archive together
           │
           ▼
7. Deployment smoke test with -Xlog:cds / class+load
           │
           ▼
8. Measure startup/readiness, PSS/USS, rollback behavior
           │
           ▼
9. Rebuild archive whenever JDK/app packaging changes
```

### 16.1. When to choose static archive?

Static is suitable when:

- There is a tightly controlled build/release step and a trial app can be run.
- You want to use the class list as an artifact to inspect loaded classes.
- You want to proactively put the archive into the image before production.
- A custom static base archive is needed to serve another layering workflow.
- There is enough CI time to dump and verify.

Do not assume static is by default faster than dynamic in every app; you must benchmark. Specific optimization differences depend on JDK/collector/build.

### 16.2. When to choose dynamic archive?

Dynamic is suitable when:

- You want to try AppCDS quickly without a class-list step.
- The application has a warm-up path that runs naturally before shutdown.
- You want to save the loaded-class set of a representative run.
- You want a top-layer archive adding custom classes on top of the default base.
- You can verify archive-at-exit is written completely and runtime maps it back successfully.

If the app is always killed abruptly at the end of a workload (e.g., container forced SIGKILL), `ArchiveClassesAtExit` is not a reliable method to get a complete archive. Run a dedicated **archive-generation job** with a graceful JVM exit.

### 16.3. What about changing the JDK patch version?

When the JDK image/VM build changes, the archive may become incompatible. Set a pipeline rule: **change JDK ⇒ recreate archive ⇒ smoke test**. Do not take an archive built on a local Windows machine, run it on a Linux server, and assume it works.

### 16.4. Do not use archives created by untrusted sources

An archive is binary data that the JVM uses during startup. Even though the JVM has compatibility checks, only use archives created and distributed through a trusted pipeline; do not randomly download `.jsa` files from third parties and force `-Xshare:on`. Control permissions, artifact digests, supply-chain provenance, and reproducibility like other deployment binaries.

## 17. Common misconceptions

1. **"AppCDS is a compiler from Java source to native binary."** False; it shares class metadata for HotSpot.
2. **"JARs are no longer needed after creating the archive."** False; classpath/resources and bytecode must match.
3. **"CDS and AppCDS are two completely unrelated systems."** False; AppCDS extends CDS to app classes.
4. **"Dynamic archive can automatically re-record every time a new class is loaded."** That is not the meaning of `ArchiveClassesAtExit`.
5. **"Static archive is a Java `static` field snapshot."** False; the name static here describes archive role/creation.
6. **"Dynamic archive records the current values of objects on the heap at shutdown."** False; it is not a heap dump.
7. **"`DumpLoadedClassList` directly creates a `.jsa` file."** False; it creates the class-list input for dump.
8. **"`-Xshare:dump` runs `main()` as usual."** False; it is an archive creation mode.
9. **"`ArchiveClassesAtExit` speeds up the very run that creates the archive."** Not guaranteed; the dump run itself usually incurs extra work.
10. **"`SharedArchiveFile` can only be used for static archives."** False; dynamic is also supported.
11. **"To use dynamic top, you must always write the default base path explicitly."** False; the dynamic header can reference the base.
12. **"Windows and Linux both separate `base:top` with `:`."** False; Windows uses `;`.
13. **"You can stack dozens of `.jsa` files into arbitrary layers in Java 17."** False; it is not a freeform layering system.
14. **"AppCDS archives are always portable across all JDK 17 vendors."** False; build/VM compatibility matters.
15. **"As long as the filename is the same, the JAR still matches even if rebuilt."** False; content/path checks can reject the archive.
16. **"Seeing the right startup stdout means AppCDS is used."** False; class-load/CDS logs are needed.
17. **"A platform class like `java.lang.String` coming from the shared archive proves all app classes are shared."** False.
18. **"An application using CDS skips JIT and GC."** False; those are separate mechanisms.
19. **"All classes in every dependency are archived even if not loaded."** False; trial/profile is used to select classes.
20. **"`-Xshare:on` should always be enabled in production."** False; strict mode can block startup when the archive is invalid.
21. **"Adding `-Xshare:off` makes AppCDS more effective."** False; it disables using shared archives.
22. **"ClassPath with non-empty directories never affects AppCDS."** False; JDK 17 has restrictions.
23. **"Java source `new` creates new class metadata for every object."** False; class metadata relates to classes, object instances are a different concept.
24. **"Reducing startup time means process RAM drops by the exact same proportion."** False; the two metrics must be measured separately.
25. **"If each JVM process has 1 GiB RSS, 10 processes must use 10 GiB of physical RAM."** False; RSS includes shared pages.
26. **"Dynamic archive only works if the application runs for at least 10 minutes."** False; it depends on loaded-class set/exit dump, with no fixed minute threshold.
27. **"The static dump step does not need the right application JAR."** False; classpath is an important input.
28. **"`jcmd VM.cds dynamic_dump` automatically works for any PID."** False; it requires VM build/flags/attach permissions.
29. **"AppCDS replaces readiness/liveness probes."** False; startup optimization does not guarantee health.
30. **"If no benefit is seen in a single benchmark, the feature is definitely useless."** False; must measure multiple runs and the right startup metric.
31. **"`-Xlog:gc*` is the most accurate way to know if a class loads from the archive."** False; `cds` and `class+load` are more appropriate.
32. **"All custom class loaders are archived like the system loader with no constraints."** False; eligibility depends on loader mechanism and JDK.
33. **"Default CDS archive = full AppCDS archive of every Java app on the machine."** False; it mainly contains common platform classes.
34. **"Build an archive on JDK 21 and use it as-is on JDK 17."** False; not portable.
35. **"Just copy a `.jsa` file to production, omit the JAR and JDK version."** False; runtime dependencies/compatibility are required.
36. **"Memory mapping means every class shares even mutable static fields and application data across JVM processes."** False; mutable states of each process must remain semantically separate.
37. **"CDS archive is a place to store application secrets/config."** False; not its purpose, and an archive should not be turned into a carrier for sensitive data.
38. **"Static archive is always 2x larger and 2x slower than dynamic."** False; size and performance depend on the class set/data.

## 18. Self-check questions (with answers)

**Question 1.** Where does AppCDS mainly differ from default CDS?

**Answer:** AppCDS can archive eligible application/library classes in addition to platform classes; both aim to reduce startup/memory footprint via class data sharing.

**Question 2.** Does a `.jsa` file contain the entire object heap state at JVM exit?

**Answer:** No. It is a CDS archive for class-related data, not a heap dump.

**Question 3.** How many phases does the static workflow have?

**Answer:** Typically **trial run to create class list → explicit `-Xshare:dump` to generate static archive → runtime using archive**.

**Question 4.** What type of file does `-XX:DumpLoadedClassList=app.classlist` create?

**Answer:** A list of classes loaded during the trial run, **not a `.jsa` archive**.

**Question 5.** Which flag creates a dynamic archive on Java 17?

**Answer:** `-XX:ArchiveClassesAtExit=app-dynamic.jsa` during an application run, requiring a successful dump when the JVM exits.

**Question 6.** Which flag is used to reuse a dynamic archive?

**Answer:** `-XX:SharedArchiveFile=app-dynamic.jsa`, with compatible JVM/base/classpath.

**Question 7.** Why can a dynamic archive be smaller than a static archive?

**Answer:** It usually only stores additional classes relative to the base archive, avoiding duplicating metadata already in the default static base.

**Question 8.** Is `java -Xshare:on` suitable for production by default?

**Answer:** Not recommended; strict mode can cause the JVM to fail startup when the archive cannot be used. `auto` is usually more flexible.

**Question 9.** How is `-XX:SharedArchiveFile=base.jsa:top.jsa` written on Windows?

**Answer:** Use `-XX:SharedArchiveFile=base.jsa;top.jsa`, and quote the option/path if the shell requires it.

**Question 10.** What `lengthSum` does `AppCdsDemo` print?

**Answer:** **14**, because `"alpha"` has length 5, `"beta"` has length 4, `"gamma"` has length 5.

**Question 11.** Why should a JAR be used in the lab instead of the `out/` directory?

**Answer:** Java 17 AppCDS classpath constraints, especially static archive creation, require packages from JARs and reject non-empty directories in the corresponding situations.

**Question 12.** If JVM stdout is the same with and without AppCDS, does that mean the archive is not helping?

**Answer:** No. The archive is an internal optimization; Java semantics/stdout **must be the same**. Performance must be measured and usage must be verified from class loading/CDS logs.

**Question 13.** When updating a Java 17.0.x patch, what should be done with the archive?

**Answer:** Regenerate and verify with the new runtime JDK; archives depend on build/VM compatibility.

**Question 14.** The class load log reports `source: shared objects file` for a class. What does that tell you?

**Answer:** That class was loaded from the shared archive in that run; it does not yet prove all app classes are shared.

**Question 15.** The application runs for the first time with `ArchiveClassesAtExit` but the process is killed with `SIGKILL`. Is the archive file guaranteed to be complete?

**Answer:** No. Creating an archive at the end of the JVM requires an appropriate exit/dump path; you must check the artifact and startup use.

**Question 16.** Why is a representative warm-up needed when creating AppCDS?

**Answer:** Because archiving comes from loaded classes of a run; lazy paths that are not executed may not have loaded the classes needing optimization.

**Question 17.** Can a Linux amd64 JDK archive be used on Windows arm64?

**Answer:** Should not be assumed; HotSpot binary layout/VM build/platform differ, and archives are not portable.

**Question 18.** What is `-Xlog:cds=info,class+load=info` for?

**Answer:** Viewing archive mapping/acceptance and the load source of each class; not just checking Java program exit status.

## 19. Suggested operational checklist

- [ ] Clearly record **JDK vendor/build, OS/architecture**, `java -version`.
- [ ] Package application/dependencies as **stable JARs**, without modifying files after dump.
- [ ] Decide on **static class-list/dump** or **dynamic dump-at-exit** according to workflow.
- [ ] For static: generate `app.classlist` from a **representative trial run**.
- [ ] For static: generate `app-static.jsa` using `-Xshare:dump` and `SharedClassListFile`.
- [ ] For dynamic: confirm the JVM **exited and dumped successfully**.
- [ ] If using a custom base: save the exact dependency of dynamic top in packaging.
- [ ] At runtime: use `-XX:SharedArchiveFile` and `-Xshare:auto` appropriately.
- [ ] Verify some **application classes** have log source `shared objects file`.
- [ ] Compare business output and app readiness against baseline.
- [ ] Measure startup metric across multiple runs, interleaving test order, controlling OS page cache.
- [ ] If measuring memory: distinguish **PSS/USS/shared pages** from raw summed RSS.
- [ ] Regenerate archive whenever **JDK/JAR/classpath/module settings** change.
- [ ] Prepare rollback when an archive is rejected, especially avoiding `-Xshare:on` outside testing.
- [ ] Protect `.jsa` as a deployment artifact; do not accept binaries from untrusted sources.

## 20. Quick summary

```text
                   JAVA 17 APP STARTUP
                         │
                default CDS archive
                         │
             ┌───────────┴───────────┐
             │                       │
        STATIC AppCDS            DYNAMIC AppCDS
             │                       │
     trial run: class list       app run with
             │                   ArchiveClassesAtExit
      Xshare:dump                  │
             │                  exit/dump
      app-static.jsa                │
             │                app-dynamic.jsa
             │                  (base + top)
             └───────────┬───────────┘
                         │
                  RUN with SharedArchiveFile
                         │
                 -Xlog:cds,class+load
                         │
              VERIFY classes come from archive
                         │
            MEASURE startup and footprint
                         │
         Does not change Java semantics or omit JAR/JDK.
```

**Key takeaway:** **AppCDS** extends CDS to application classes to reduce startup work and can share class metadata across multiple JVMs. **Static archive** is created from **class list + explicit dump**, while **dynamic archive** is created **when the JVM exits** after a runtime run and uses a **base archive**. In Java 17, the main flags are `DumpLoadedClassList`, `SharedClassListFile`, `-Xshare:dump`, `ArchiveClassesAtExit`, `SharedArchiveFile`, and `-Xlog:cds,class+load`. Proper workflow requires **verifying the archive is loaded**, keeping **JDK/JAR/classpath compatible**, and **controlled benchmarking**. The archive is not a heap dump, does not replace JARs, does not cache JIT native code, and does not guarantee every class/application will start faster.

### Official references

- [Oracle JDK 17 — `java` command, Application Class Data Sharing](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): flags, static/dynamic archive workflows, two-archive layering, classpath restrictions, diagnostic logging.
- [Oracle Java SE 17 — Class Data Sharing, JVM Guide](https://docs.oracle.com/en/java/javase/17/vm/class-data-sharing.html): CDS mechanism, AppCDS, dynamic archive, memory sharing, and default behavior.
- [dev.java — CDS and AppCDS in HotSpot](https://dev.java/learn/jvm/other-tools/cds-appcds/): lab workflow, static/dynamic tradeoffs, and JDK version limitations.
- [JEP 310 — Application Class-Data Sharing](https://openjdk.org/jeps/310): architecture extending CDS to application classes.
- [JEP 341 — Default CDS Archives](https://openjdk.org/jeps/341): default archive packaged with JDK 12+.
- [JEP 350 — Dynamic CDS Archives](https://openjdk.org/jeps/350): archiving from loaded classes at JVM exit, dynamic top layer.
- [JDK 17 — `jcmd` manual](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): runtime diagnostic commands, including `VM.cds` if supported by the build.