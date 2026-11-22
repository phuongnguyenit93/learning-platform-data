# Creating and Verifying CDS Archive Usage with Class-Loading Logs

## 1. Expected Outcomes

**Class Data Sharing (CDS)** is a HotSpot feature that stores preprocessed Java class data in an **archive** so that the JVM in subsequent runs can **load certain classes faster** instead of always going through the entire JAR-reading and metadata-processing path from scratch. **Application CDS (AppCDS)** extends that capability to eligible application and library classes.

This lab guides you through a complete sequence:

1. Create a small Java application and package it into a **JAR** to meet easily verifiable CDS conditions.
2. Run a baseline without CDS to observe the class-loading path from the JAR.
3. Create a **dynamic CDS archive** with `-XX:ArchiveClassesAtExit` and run it again.
4. Use **`-Xlog:class+load`** to verify that **the application's own classes** are loaded from **`shared objects file`**, rather than relying solely on the existence of the `.jsa` file.
5. Create a **static CDS archive** from `DumpLoadedClassList` and `-Xshare:dump`, and verify it similarly.
6. Distinguish between evidence that **the archive is mapped**, evidence that **a specific class is loaded from the archive**, and evidence that **startup is actually faster**.
7. Diagnose an unused archive, missing application classes in the archive, classpath/JDK mismatches, and differences in JDK 25.

**Key takeaway:** The existence of the `cdslab.jsa` file **does not prove** that HotSpot has used it. To confirm a specific class, you must read the class-loading log in the **run that uses the archive** and look for the class name and its corresponding `source: shared objects file`.

### Scope and Versions

The Java examples use **Java 17+** with traditional HotSpot CDS. The static/dynamic CDS commands are documented in the **Oracle JDK 25 `java` manual** and can run on many OpenJDK HotSpot 17/21/25 builds. An example was tested on **OpenJDK 21**: the program prints exactly two lines; both the dynamic archive and static archive cause `CdsHello`/`Greeting` to be loaded from `shared objects file`. The class names, the two lines of application output, and the load path type are verifiable; **startup time, class count, and archive size are not fixed**.

JDK 25 also has **AOT cache** (`-XX:AOTCacheOutput`, `-XX:AOTCache`) per JEP 483 and new improvements. AOT cache can do more than traditional CDS. This article prioritizes how to **create/verify `.jsa` files** as stated in the topic, then introduces the distinction with AOT.

## 2. Understanding CDS Correctly: Sharing Class Data, Not Caching Everything

When the JVM loads a class, the runtime must process class-file bytes and metadata: loading, verification, linking, and initialization when required by JVM semantics. Certain parts of eligible class metadata can be stored in **preprocessed** form in a CDS archive and then efficiently mmapped/mapped for processes to use.

~~~text
Without CDS:
  JAR / runtime image
        |
        v
  Load class bytes + process runtime metadata
        |
        v
  JVM continues running application

With CDS when compatible:
  Archived class data (.jsa)
        |
        v
  Mapped shared archive regions
        |
        v
  Class loader retrieves eligible archived classes
        |
        v
  JVM continues running application
~~~

Potential benefits:

- **Startup:** reduces the work of loading certain classes.
- **Memory footprint:** part of the mapped archive pages can be shared across multiple JVM processes using the same compatible archive.
- **Metadata processing cost:** reduces repeated work when the archive contains the exact classes the app uses.

**Do not assume that:**

- CDS automatically **pre-JIT-compiles every method**.
- Every class is loaded from CDS.
- CDS skips all class initialization, static initializers, or semantic checks.
- Having an archive means startup is guaranteed to be faster for every workload.
- CDS fixes network costs, database connections, dependency injection, or what the application itself runs in `main`.
- Every process using the archive has an identical startup time.

Oracle JDK 25 states that an archive containing class data can take **more disk space** than the class bytes in the JAR/JDK image because it is stored in a format optimized for fast loading. You should only archive classes that are actually useful to the workload.

## 3. Default CDS, AppCDS, Static and Dynamic Archives

| Concept | Target | Common Creation/Usage |
| --- | --- | --- |
| **Default CDS archive** | A set of core classes bundled in the JDK distribution | Usually used automatically on supported HotSpot |
| **AppCDS** | Eligible application and library classes | Create an archive from an actual training/demo run |
| **Static archive** | Archive pre-created from a list of loaded classes | `DumpLoadedClassList` → `-Xshare:dump` |
| **Dynamic archive** | Archive supplementing classes captured during an app run | `-XX:ArchiveClassesAtExit=...` |
| **Base/top archive** | Dynamic archive layered on top of a base static archive | Default base + dynamic top; logs may show `(top)` |
| **JDK 25 AOT cache** | Container storing AOT artifacts beyond traditional CDS scope | `-XX:AOTCacheOutput=...` and `-XX:AOTCache=...` |

**Static/dynamic here refers to how the archive is created, not a classification of static/dynamic classes in Java.** `.jsa` files do not contain "live objects" to restore all program state like an application snapshot.

In most HotSpot JDK builds, default CDS is already enabled unless `-Xshare:off` is used. However, **a default archive containing JDK/core classes does not by itself prove that application classes are saved**. To confirm AppCDS, you need to check the source of **`CdsHello` or `Greeting`** — not just `java.lang.Object` or `java.lang.String`.

### Two Levels of Evidence

~~~text
Level 1 — archive mapping:
  [info][cds] ... archive ... opened / mapped ...
  => the archive was considered/mapped, but app classes may still load from the JAR

Level 2 — app class source:
  [info][class,load] CdsHello source: shared objects file (top)
  => the CdsHello class in this run was taken from the shared archive
~~~

Log samples only illustrate the general format; timestamp prefixes, decorators, and the `(top)` suffix vary by VM/version/archive type.

## 4. Preparation: JDK, Directory, and Packaging the JAR

**First requirement:** have JDK 17+ on PATH, and use the **same JDK build** for creating and using the archive when you want consistent results.

~~~bash
java -version
javac -version
jar --version
~~~

All commands in the lab run in a **separate lab directory**, not a directory containing production artifacts. There is no need to install Maven/Gradle or download third-party dependencies.

### Create the Source File `CdsHello.java`

~~~java
public class CdsHello {
    public static void main(String[] args) {
        System.out.println("message=" + Greeting.message("CDS"));
        System.out.println("answer=" + Greeting.answer(40));
    }
}

class Greeting {
    static String message(String name) {
        return "Hello, " + name;
    }

    static int answer(int value) {
        return value + 2;
    }
}
~~~

Here **one Java file** declares the public class `CdsHello` and the package-private class `Greeting`. `javac` generates **two class files**; at runtime, the class loader will need to load both.

**Exact stdout of the application in a successful run without VM logs enabled:**

~~~text
message=Hello, CDS
answer=42
~~~

Explanation: `Greeting.message("CDS")` concatenates into the string `Hello, CDS`; `Greeting.answer(40)` returns 42. Neither operation depends on timing or thread scheduling.

### Compile, Package the JAR, and Test Run

**Linux/macOS shell:**

~~~bash
mkdir -p build
javac -d build CdsHello.java
jar --create --file cdslab.jar --main-class CdsHello -C build .
java -cp cdslab.jar CdsHello
~~~

**Windows PowerShell:**

~~~powershell
New-Item -ItemType Directory -Force build | Out-Null
javac -d build CdsHello.java
jar --create --file cdslab.jar --main-class CdsHello -C build .
java -cp cdslab.jar CdsHello
~~~

`-C build .` tells the `jar` tool to place the contents of the `build` directory at the root of the JAR (including `CdsHello.class` and `Greeting.class`). `--main-class` writes a manifest entry, though here we can run with `-cp cdslab.jar CdsHello` so that CDS creation and usage commands always have the same classpath.

**Why package a JAR instead of running from a class directory?** The Oracle JDK 25 CDS manual states that when creating/using AppCDS, the classpath/module path has **restrictions on non-empty directories**. Using **a single JAR** and a consistent command line avoids many cases where "the JVM has CDS logs, but app classes are not archived."

### Classpath Warning

Do not change `-cp cdslab.jar` to `-cp build` in the usage step and still claim the archive is compatible. With traditional CDS, **the classpath at creation time must match or be a prefix of the runtime classpath** per the conditions Oracle describes; a class JAR modified after dumping can make the archive unusable.

A newly repackaged JAR **can cause the metadata fingerprint/validation to differ**. To test a new archive, avoid recompiling/repackaging the JAR between creation and usage.

## 5. Baseline: Class-Loading Logs with CDS OFF

To see the difference, first run the app **without any CDS archive**.

~~~bash
java -Xshare:off -Xlog:class+load=info:file=baseline-load.log -cp cdslab.jar CdsHello
~~~

This command places the JVM options **before** the main class and redirects **class-loading logs to the file** `baseline-load.log`; stdout on the terminal remains:

~~~text
message=Hello, CDS
answer=42
~~~

In `baseline-load.log`, search for `CdsHello` and `Greeting`.

**Linux/macOS:**

~~~bash
grep -E "CdsHello source:|Greeting source:" baseline-load.log
~~~

**Windows PowerShell:**

~~~powershell
Select-String -Path baseline-load.log -Pattern "CdsHello source:|Greeting source:"
~~~

**Expected log format (exact path does not have to match):**

~~~text
[info][class,load] CdsHello source: file:/.../cdslab.jar
[info][class,load] Greeting source: file:/.../cdslab.jar
~~~

When running the baseline with `-Xshare:off`, the two application classes from the JAR will **not have `shared objects file` as their source**. The exact path may be `file:/...` or another file path format depending on JDK/OS.

**Why does the class source log matter?** It is evidence of **where a class is loaded from at runtime**, which is more useful than merely observing that an archive file exists or checking the number of classes known at VM startup.

## 6. Flow A: Creating a Dynamic CDS Archive (Fewer Steps, Easy to Learn)

### Step A1. Run a "training run" to create the archive on JVM exit

~~~bash
java -XX:ArchiveClassesAtExit=cdslab-dynamic.jsa -cp cdslab.jar CdsHello
~~~

The program output remains:

~~~text
message=Hello, CDS
answer=42
~~~

When the process exits normally, HotSpot can write **`cdslab-dynamic.jsa`** (dynamic/top archive) containing eligible classes that the application loaded, excluding classes already in the base archive. A dynamic archive requires a **base CDS archive** (usually provided by default by the JDK). If the base is unavailable or cannot be loaded, the operation may fail; check the diagnostic logs.

**Do not create an archive by renaming a JAR file to `.jsa`.** The archive is a HotSpot/JDK-build-specific format, not a ZIP/JAR.

### Step A2. Confirm the file was created

**Linux/macOS:**

~~~bash
ls -lh cdslab-dynamic.jsa
~~~

**Windows PowerShell:**

~~~powershell
Get-Item .\cdslab-dynamic.jsa
~~~

The file existing with a size greater than 0 means the creation step produced an artifact, **but still does not prove usage**.

### Step A3. Run again and log class loading

~~~bash
java -XX:SharedArchiveFile=cdslab-dynamic.jsa -Xlog:class+load=info:file=dynamic-load.log -cp cdslab.jar CdsHello
~~~

Application stdout is the same two lines as before. Open the log to search for:

~~~bash
grep -E "CdsHello source:|Greeting source:" dynamic-load.log
~~~

In **PowerShell** use:

~~~powershell
Select-String -Path dynamic-load.log -Pattern "CdsHello source:|Greeting source:"
~~~

**Log format verified on OpenJDK 21:**

~~~text
[info][class,load] CdsHello source: shared objects file (top)
[info][class,load] Greeting source: shared objects file (top)
~~~

The timestamp/decorators before `[info]` vary by version. **`(top)`** usually indicates the top/dynamic archive; the most important part is that both **application classes** have `source: shared objects file`.

### Step A4. Read the CDS mapping log as well (optional)

~~~bash
java -XX:SharedArchiveFile=cdslab-dynamic.jsa -Xlog:cds=info:file=dynamic-cds.log -cp cdslab.jar CdsHello
~~~

The CDS log can tell you which file was opened, mapped/validated, or why an archive was rejected. However, **the mapping log alone does not prove `CdsHello` was archived**; you must cross-check `class+load` for the specific class under test.

### Step A5. Compare baseline and dynamic

| Run step | `CdsHello` class source log | Conclusion |
| --- | --- | --- |
| `-Xshare:off` | From `cdslab.jar` | CDS not used for that class |
| `-XX:ArchiveClassesAtExit=...` | Training run creates top archive on exit | File created, usage not yet confirmed |
| `-XX:SharedArchiveFile=cdslab-dynamic.jsa` | `shared objects file (top)` when valid | **Confirmed CDS used for this app class** |

**Note:** If the app runs correctly but `CdsHello` still has `source: file:/.../cdslab.jar`, you must not say "AppCDS worked for CdsHello." It may be that only the default base CDS was used for JDK classes, while the app class was not archived or the archive was rejected.

## 7. Flow B: Creating a Static CDS Archive (classlist + dump)

A static archive demonstrates how to **identify classes from a trial run**, then **create the `.jsa` file in a separate step**.

### Step B1. Record the list of loaded classes

~~~bash
java -Xshare:off -XX:DumpLoadedClassList=cdslab.classlist -cp cdslab.jar CdsHello
~~~

The command runs the program, observes class loading in the VM, and writes **`cdslab.classlist`**. The application output remains the standard two lines.

Inspect the list:

**Linux/macOS:**

~~~bash
grep -E "CdsHello|Greeting" cdslab.classlist
~~~

**Windows PowerShell:**

~~~powershell
Select-String -Path cdslab.classlist -Pattern "CdsHello|Greeting"
~~~

The file may contain many core/library classes and directives; **do not manually delete unfamiliar lines**, because the classlist format is written by the VM. Class names in the classlist usually use JVM internal slash form for packaged classes (e.g., `example/Hello`); this lab example has no package, so the names are simple.

### Step B2. Dump the static archive

~~~bash
java -Xshare:dump -XX:SharedArchiveFile=cdslab-static.jsa -XX:SharedClassListFile=cdslab.classlist -cp cdslab.jar
~~~

**Important:**

- This is an **archive dump** command, **not running `main`** of the application.
- `-cp cdslab.jar` must match the path configured during training.
- Oracle JDK 25 describes that when using `-Xshare:dump`, the JVM usually runs interpreter-only to produce a deterministic archive output. For very large dumps, `-Xmixed` can be adjusted if the version supports it and bit-for-bit deterministic dumps are not required.
- If the dump fails, read the errors/`-Xlog:cds` and fix the cause rather than assuming `cdslab-static.jsa` is valid from a leftover file.

Check the file:

~~~bash
ls -lh cdslab-static.jsa
~~~

On Windows PowerShell, use `Get-Item .\cdslab-static.jsa`.

### Step B3. Run the application with the static archive

~~~bash
java -XX:SharedArchiveFile=cdslab-static.jsa -Xlog:class+load=info:file=static-load.log -cp cdslab.jar CdsHello
~~~

The program prints:

~~~text
message=Hello, CDS
answer=42
~~~

Search for the class source:

~~~bash
grep -E "CdsHello source:|Greeting source:" static-load.log
~~~

**Output format verified on OpenJDK 21:**

~~~text
[info][class,load] CdsHello source: shared objects file
[info][class,load] Greeting source: shared objects file
~~~

With a static archive, the log may not have `(top)`. The Oracle JDK 25 `java` manual uses the equivalent marker for classes in static AppCDS: `source: shared objects file`.

### Step B4. Distinguish creation commands from usage commands

| Task | Main flag | Output |
| --- | --- | --- |
| List loaded classes | `-XX:DumpLoadedClassList=...` | `.classlist` |
| Create static archive | `-Xshare:dump` + `SharedClassListFile` + `SharedArchiveFile` | `.jsa` |
| Create dynamic archive | `-XX:ArchiveClassesAtExit=...` | `.jsa` on exit |
| Use archive | `-XX:SharedArchiveFile=...` | Application runs, may load classes from archive |
| Prove class source | `-Xlog:class+load` | `source: shared objects file` for specific class |

**Do not confuse `-XX:DumpLoadedClassList` with `-XX:SharedClassListFile`**: the former **writes the classlist during a trial run**, while the latter **reads the list to dump the archive**.

## 8. `-Xshare` Options and Policy When an Archive Cannot Be Used

HotSpot has the following modes:

| Option | Meaning | When to use |
| --- | --- | --- |
| `-Xshare:off` | Do not use CDS | Baseline/troubleshooting |
| `-Xshare:auto` | Use archive when available, can fall back | Friendlier behavior in production |
| `-Xshare:on` | Require using CDS; failure may cause JVM exit | **Diagnostics/testing**, not recommended for production |
| `-Xshare:dump` | Create static archive | Archive build step, does not run application |

The Oracle JVM Guide explicitly states that **`-Xshare:on` is intended for testing**: when an archive is unavailable due to JDK/options changes, it can cause the JVM to **exit at startup** instead of falling back. Therefore, do not enable it blindly in production just hoping for fast startup.

### Intentional Fail-Fast Test

Once you have created the archive properly and want to verify that the archive is actually usable, in the lab you can run:

~~~bash
java -Xshare:on -XX:SharedArchiveFile=cdslab-dynamic.jsa -Xlog:cds=info -cp cdslab.jar CdsHello
~~~

If the JDK/flags/archive do not match, the JVM may report an error and exit. This command **does not replace the `class+load` log** for confirming **which classes** were loaded from the archive. Use `-Xshare:auto` (or the default depending on the JDK version) in real application environments when safe fallback is preferred.

## 9. Distinguishing "Archive Mapped" from "Class X Is Shared"

A common error pattern:

~~~text
[info][cds] Opened archive ... ...
[info][class,load] java.lang.Object source: shared objects file
[info][class,load] CdsHello source: file:/.../cdslab.jar
~~~

**Correct conclusion:** The JVM used CDS for at least one **JDK class**, but **AppCDS is not confirmed for `CdsHello`**. The dynamic archive may not contain that class or may be unusable, while the default/base archive still works.

Sufficiently strong cross-verification for the lab:

~~~text
(1) cdslab-dynamic.jsa exists
(2) runtime command actually specifies cdslab-dynamic.jsa
(3) class+load log contains:
    CdsHello source: shared objects file (top)
    Greeting source: shared objects file (top)
(4) application stdout is exactly two lines
~~~

This is enough to state that **this archive is providing those app classes in the observed run**. It is still **not** enough to prove a startup benefit of a specific number of ms.

### When Does `class+load` Output Logs?

`-Xlog:class+load=info` is **Unified Logging** for class loading. If `:file=...` is provided, logs are written to the file; if the output spec is omitted, logs normally go to the JVM's default output.

Example printed directly in the terminal:

~~~bash
java -XX:SharedArchiveFile=cdslab-dynamic.jsa -Xlog:class+load=info -cp cdslab.jar CdsHello
~~~

**In this run, terminal output includes both class logs and the two app lines.** You must not claim "stdout is strictly two lines" for the entire process when class logs are enabled on the console.

When using output-to-file as in the steps above, the two lines of application stdout remain separate, while `.log` contains the logs. However, `stderr` may still contain warnings/errors outside class logs depending on the JVM.

## 10. Log-Filtering Tools on Linux/macOS and Windows

### Linux/macOS: filter with grep

~~~bash
grep -E "CdsHello source:|Greeting source:" dynamic-load.log
grep -E "shared objects file|source: file:" dynamic-load.log
grep -E "CdsHello source:|Greeting source:" static-load.log
~~~

### Windows PowerShell: filter with Select-String

~~~powershell
Select-String -Path .\dynamic-load.log -Pattern "CdsHello source:|Greeting source:"
Select-String -Path .\static-load.log -Pattern "CdsHello source:|Greeting source:"
~~~

To inspect all class-load sources, you can open the log file in an editor with search instead of printing the entire log to the console.

**Do not use an overly broad regex such as just searching for the word "shared" and drawing a conclusion:** JDK core classes in the default archive will cause false positives. You must search for **the exact class name `CdsHello`/`Greeting`** or the target classes of your real application.

### Log Markers by JVM/JDK

Class logging lines may contain:

- timestamp `[0.024s]`;
- tags `[info][class,load]`;
- class name in dot notation;
- `source: shared objects file`, with or without `(top)`;
- path to a JAR or module image;
- additional details when `debug`/`trace` levels are enabled.

**Do not use exact timestamps or character positions as durable assertions.** Match the class source marker after identifying the exact class and JVM version.

## 11. `-Xlog:cds` Logs for Diagnosing Mapping and Fallback

A useful command:

~~~bash
java -XX:SharedArchiveFile=cdslab-dynamic.jsa -Xlog:cds=info:file=cds-check.log -Xlog:class+load=info:file=class-check.log -cp cdslab.jar CdsHello
~~~

In HotSpot Unified Logging, corresponding `-Xlog` flags can be used to specify different tag sets/outputs; verify with `java -Xlog:help` on the current JDK. If a log format or option is rejected, prefer running **each log in a separate test process** with simple options like the examples in previous steps.

`cds-check.log` can help detect:

- Why the archive could not be opened;
- Archive/base mismatch;
- Validation/JAR path issues;
- Memory layout/mapping issues;
- Why archived class metadata was disabled;
- Certain flags/module options that make CDS incompatible.

`class-check.log` clearly shows **which classes loaded from which source**.

**Do not equate `source: shared objects file` with `source: jrt:/...`**. The JRT module image can be the source of ordinary class loading when CDS is disabled; it is not a marker of using archived class data.

## 12. Compatibility Conditions of an AppCDS Archive

The Oracle JDK 25 `java` manual has notable restrictions:

1. **Classpath and module path:** CDS has restrictions on **non-empty directories**; the lab guide uses a **JAR** and `-cp cdslab.jar` to avoid them.
2. **Classpath consistency:** the classpath at dump time must be identical to or a prefix of the runtime classpath in supported cases.
3. **JAR modification:** If a JAR on the classpath/module path changes after dumping, the archive may not be loaded.
4. **JDK build:** archives are **build-specific**; creating with one JDK and switching to another JDK runtime may be incompatible.
5. **Modules:** options such as `--module-path`, `--module`, `--add-modules`, and `--enable-native-access` must be consistent per documented conditions.
6. **Certain module flags:** `--upgrade-module-path`, `--patch-module`, or `--limit-modules` can disable CDS according to Oracle JDK 25.
7. **Custom class loaders:** the ability to archive/reuse classes also depends on loader behavior and HotSpot support; do not assume every generated/dynamic class can be shared.
8. **VM flags/diagnostics:** GC/compiler/JVMTI or other runtime flags can affect archive mapping/compatibility depending on the version.
9. **File access/security:** the archive must be readable, at the right path, and not tampered with.

**Security warning:** CDS archives contain data used by the JVM runtime. Only use archives from a trusted build/training pipeline, with file permissions preventing unauthorized modification. Oracle notes `-XX:+VerifySharedSpaces` for CRC32 integrity checking against accidental corruption, **not a comprehensive security solution against an attacker modifying the file**.

### Example of Violated Conditions

~~~text
Create:
  java -XX:ArchiveClassesAtExit=cdslab-dynamic.jsa -cp cdslab.jar CdsHello

Then:
  javac -d build CdsHello.java
  jar --create --file cdslab.jar --main-class CdsHello -C build .
  (repackaged the JAR in between)

Use:
  java -XX:SharedArchiveFile=cdslab-dynamic.jsa -cp cdslab.jar CdsHello

Likely outcome:
  archive mismatch/rejected or app classes not loaded from archive
~~~

**It is not guaranteed** that every JAR repackaging will always fail, but treating the archive as needing to be **recreated** after binary/JAR changes is the right policy for reliable deployment.

## 13. Common Errors and How to Handle Them

| Symptom | Possible Cause | Check Step |
| --- | --- | --- |
| No `.jsa` file found | Training process did not exit successfully; wrong flag/path | Check exit code, stderr, and `-Xlog:cds` |
| Archive exists but app class loads from JAR | Does not contain app class or archive is not used | `class+load` for exact app class name and `-Xlog:cds` |
| Only `java.lang.Object` has shared source | Default CDS used, AppCDS not certain | Search for `CdsHello`/`Greeting` |
| `Unrecognized VM option` error | JVM does not support flag / wrong JDK | `java -version`, version-specific docs, VM vendor |
| "base archive not loaded" during dynamic dump | Default/base CDS unavailable | Test default archive, check `-Xshare:off` is not enabled |
| Static dump produces no app output | Normal: `-Xshare:dump` only dumps, does not run main | Check archive file/logs and subsequent runtime step |
| Class missing from classlist | Trial run did not load that class | Adjust training workload, then dump again |
| CDS not used when classpath is a directory | CDS restrictions on non-empty directories | Package into JAR, keep classpath consistent |
| Recently changed JAR/JDK version | Incompatible archive | Recreate archive on the exact deployment build |
| Only runs with `-Xshare:on` and VM exits | Strict mode fail-fast | Read logs; use `auto` in appropriate production setups |
| Log shows `jrt:/...` instead of shared | Normal class loading from runtime image | Check archive/source of the exact class |
| Startup not noticeably faster | Small workload, class loading not dominant, system noise | Benchmark multiple process starts, measure right metric |
| `.jsa` file shared across pods but fails on some nodes | Different JDK/OS/architecture/flags | Compare build/container image and runtime configuration |
| Has `source: shared objects file (top)` but wrong output | Another app bug; CDS does not change semantic correctness | Check program logic, classpath, and logs |

### Cleaning Up Old Files to Avoid Misreading

When repeating experiments, **do not randomly overwrite an archive already in use by another process**. Create a separate lab directory or rename archives/trace logs; delete old files only when you are sure they belong to the lab.

In automation, an archive file created by the wrong JDK build may remain on disk; a `SharedArchiveFile` path being passed does not mean it is mapped. **Always check the class source log at runtime**.

## 14. Creating a Dynamic Archive from a Running Runtime

Oracle JDK 25 documents options with `jcmd VM.cds` for a **running** JVM:

~~~text
jcmd <pid> VM.cds static_dump my_static_archive.jsa
jcmd <pid> VM.cds dynamic_dump my_dynamic_archive.jsa
~~~

These are **sample commands**; replace `<pid>` with the PID of a JVM you are permitted to operate on; do not copy angle brackets literally when running in the shell.

According to JDK 25 documentation, to invoke `VM.cds dynamic_dump`, the target JVM must have been started with `-XX:+RecordDynamicDumpInfo`. `jcmd` carries additional permissions/attach requirements and operational impact, so do not use it on production processes without proper authorization and procedures.

### When to Use `jcmd VM.cds`?

- The app has a complex startup script, making it hard to add training flags early.
- You want to dump a snapshot of loaded classes after representative traffic/workflow.
- You want to avoid manually building a classlist/dump outside the application lifecycle.

**Does not replace the final verification step:** even when the archive is created via `jcmd`, you must still **restart/start a new JVM with `-XX:SharedArchiveFile`**, then read `class+load` for the target classes.

## 15. `-XX:+AutoCreateSharedArchive` on Modern HotSpot

Oracle JDK 25 also describes a convenient approach:

~~~bash
java -XX:+AutoCreateSharedArchive -XX:SharedArchiveFile=cdslab-auto.jsa -cp cdslab.jar CdsHello
~~~

In versions with this feature, if the file does not exist yet, the VM can create a dynamic archive on exit. Subsequent runs with **the same command line** can use the created archive when compatible.

Advantage: avoids having to remember a separate training run and runtime command. However:

- The **recreate/replace** policy for the archive depends on the JDK version that created it; Oracle JDK 25 distinguishes between archives from before and after JDK 19.
- The archive file still has build/version compatibility constraints.
- You need to verify `CdsHello source: shared objects file` in **the subsequent run**, not just the initial creation run.
- Use `-Xlog:cds` if the archive cannot be used.

This feature is not a Java language requirement and is not present on all vendors/JDKs; for learners, the 2-step dynamic flow in section 6 is easier to reason about.

## 16. Static vs Dynamic: Which One to Choose?

| Criterion | Static (`-Xshare:dump`) | Dynamic (`ArchiveClassesAtExit`) |
| --- | --- | --- |
| Training step | Write `.classlist` | Run app to record classes and dump on exit |
| Dump step | Separate, with `-Xshare:dump` | Usually right when JVM exits |
| Base archive | Can create a standalone static one | Requires a compatible base static archive |
| Command complexity | More steps | Fewer steps |
| Size | Can include more classes | Usually smaller because it does not duplicate classes already in base |
| Optimizations | May support fuller optimizations | Some optimizations fewer than static |
| Verify usage | `SharedArchiveFile` + `class+load` | Same as static, may show `(top)` |
| When convenient | Controlled build pipeline/classlist | Trial run of app then reuse |
| Learning comparison | Clear separation of trial/dump/run | Clear archive-at-exit/run |

According to Oracle JDK 25, **dynamic archives, while convenient, support fewer optimizations than static archives** in some scenarios; for fuller optimizations in JDK 25, consider **AOT cache**.

## 17. CDS vs AOT Cache in JDK 25

JDK 24/25 supports **Ahead-of-Time Cache** (`.aot`), introduced via **JEP 483** and further extended with AOT method profiling in JDK 25 (**JEP 515**). The AOT cache can store artifacts **beyond** class data to improve startup and warmup.

Distinction:

- **`cdslab-dynamic.jsa` / `cdslab-static.jsa`:** traditional CDS archive.
- **`cdslab.aot`:** AOT cache from JDK 24+ using separate options, which may include additional artifacts.
- `-XX:SharedArchiveFile` is for CDS; `-XX:AOTCache` is for AOT cache.
- `-Xlog:class+load` remains useful to see class sources; `-Xlog:aot` provides specific information when handling AOT cache.

### Supplementary Lab Only for Supported JDK 25

~~~bash
java -XX:AOTCacheOutput=cdslab.aot -cp cdslab.jar CdsHello
java -XX:AOTCache=cdslab.aot -Xlog:aot=info -Xlog:class+load=info:file=aot-load.log -cp cdslab.jar CdsHello
~~~

According to the Oracle JDK 25 `java` manual, `AOTCacheOutput` may perform training and launch an additional assembly VM to generate the cache file. Policies and compatibility have **application/JDK/OS/CPU** conditions; do not use this JDK 25 command as an example guaranteed to work on Java 17.

**The main goal of this lesson remains CDS `.jsa`.** Do not mix the two artifact types and claim `.aot` and `.jsa` are equivalent, or apply the AOT flag list to all Java versions.

## 18. Why Class-Load Logs Do Not Prove Faster Startup

**Correctness evidence:** `CdsHello source: shared objects file` proves the specific class came from the archive.

**Performance evidence:** you must **measure startup time** across multiple runs/processes with the same workload, JVM build, CPU load, and memory conditions. This is independent of correctness.

Example experiment:

~~~bash
java -Xshare:off -cp cdslab.jar CdsHello
java -XX:SharedArchiveFile=cdslab-dynamic.jsa -cp cdslab.jar CdsHello
~~~

You cannot just look at two outputs and conclude how many ms were saved. For this small app, process startup, JVM initialization, JIT/class loading, filesystem cache, and scheduler noise can outweigh the benefit of AppCDS alone.

### A More Reliable Measurement Process

1. Keep **the same JDK build, unrelated flags, and JAR**.
2. Run multiple independent **process starts** in both modes: baseline without CDS and AppCDS.
3. Measure a wall-clock/process-start-to-ready metric relevant to the product, not just time inside `main`.
4. Avoid enabling verbose logs during the primary measurements, because logging adds overhead.
5. For servers, use readiness/first request latency on a representative workload; do not just measure `System.nanoTime` inside `main`.
6. Record median, P95, variation, CPU/load, and memory footprint.
7. Verify first with class-source logs that AppCDS is actually active, and only then benchmark.

**A small or unclear improvement on `CdsHello` does not refute CDS:** a tiny example is not representative of an application with thousands of classes. Conversely, a mapped archive does not guarantee production startup improves if the bottleneck is I/O/network or application initialization.

## 19. Common Misconceptions

| False Statement | Correct Understanding |
| --- | --- |
| "Having a `.jsa` file means the JVM already used it." | File existence only proves an artifact exists; runtime `class+load`/`cds` is needed. |
| "Seeing `java.lang.Object` from shared means the app is archived." | That may only be default JDK CDS; check app classes. |
| "App class loaded from `cdslab.jar` proves AppCDS." | On the contrary, it indicates that class was **not** loaded from the archive in that run. |
| "Dynamic archive and static archive are created with the same command." | Dynamic uses `ArchiveClassesAtExit`, static uses classlist + `Xshare:dump`. |
| "`DumpLoadedClassList` creates `.jsa`." | It creates a classlist, not an archive. |
| "`Xshare:dump` runs the application's `main`." | It dumps the archive, it does not run the app. |
| "CDS always caches JIT machine code." | Traditional CDS focuses on class data; JDK 25 AOT cache has a different scope. |
| "CDS skips all class initialization." | No, Java semantics of init/linking must be preserved. |
| "All classpath directories are supported by AppCDS." | There are restrictions on non-empty directories. |
| "Changing JDK and reusing `.jsa` is definitely fine." | Archives depend on version/build; recreate when changing deployment. |
| "Creating then repackaging the JAR has no effect." | A modified JAR can invalidate the archive. |
| "Changing classpath order arbitrarily has no effect." | CDS requires path consistency. |
| "`-Xshare:on` is safer than `auto` for production." | `on` is strict/testing and may exit if the archive fails. |
| "`-Xshare:off` only turns off AppCDS, keeping base CDS." | `off` disables class sharing for that run. |
| "`source: shared objects file (top)` is a JAR path." | It is the marker for the dynamic top archive in the HotSpot class-load log. |
| "Any log containing the word shared is enough." | You must check the exact class being verified. |
| "Archived classes are always faster than any loading path." | Benefits depend on workload and environment. |
| "CDS supports any custom loader/generated class." | Eligibility depends on HotSpot/loader/version. |
| "JDK 25's AOT cache is just a `.jsa` file." | AOT uses separate artifacts/options and has additional optimizations. |
| "Faster startup in one run is enough to conclude." | You must measure multiple times under the same conditions. |

## 20. Self-Check Questions (with Answers)

**Question 1.** What is CDS?  
**Answer:** HotSpot shares preprocessed class data in an archive to reduce part of the class-loading overhead and potentially reduce memory footprint across JVM processes.

**Question 2.** Why package the application into a JAR in the lab?  
**Answer:** To use a classpath that complies with AppCDS restrictions, making it easy to create the archive and reproduce the runtime path.

**Question 3.** What is the command to create a dynamic archive?  
**Answer:** `java -XX:ArchiveClassesAtExit=cdslab-dynamic.jsa -cp cdslab.jar CdsHello`.

**Question 4.** Which command confirms the class load source?  
**Answer:** Run with `-XX:SharedArchiveFile=...` and `-Xlog:class+load=info`, and look for `CdsHello source: shared objects file`.

**Question 5.** Why does `java.lang.Object source: shared objects file` not prove AppCDS?  
**Answer:** That may be the JDK default archive; you must check the application classes themselves.

**Question 6.** What two steps does static CDS require before use?  
**Answer:** `DumpLoadedClassList` to record the class list, then `-Xshare:dump` with `SharedClassListFile` to create the archive.

**Question 7.** Does `-Xshare:dump` print `message=Hello, CDS`?  
**Answer:** No, that is a dump step, not running `main`. The two lines of output belong to the app training/usage runs.

**Question 8.** What if the `.jsa` file exists but `CdsHello` still has `source: file:/...jar`?  
**Answer:** You must not claim this class uses AppCDS; check CDS logs/compatibility/contents.

**Question 9.** Why is replacing the JAR after the archive is created risky?  
**Answer:** Classpath/JAR consistency validation can make the archive invalid; it needs to be recreated for the new build.

**Question 10.** What is the risk of using `-Xshare:on` in production?  
**Answer:** Strict mode can cause the JVM to exit if the archive cannot be used; Oracle recommends it for testing.

**Question 11.** When should `jcmd VM.cds` be used?  
**Answer:** When you want to dump from a running JVM process, with proper attach permissions and flag conditions.

**Question 12.** What does `shared objects file (top)` usually suggest?  
**Answer:** The class was loaded from the top/dynamic archive layered on the base archive in the corresponding HotSpot version.

**Question 13.** Is JDK 25 `AOTCacheOutput` the same as `ArchiveClassesAtExit`?  
**Answer:** No. AOT cache is a container for additional optimizations and uses separate files/options.

**Question 14.** Is a log confirming an archived class enough to conclude a 20% startup reduction?  
**Answer:** No. You need an end-to-end startup benchmark with multiple runs and controlled conditions.

## 21. Practice Checklist

- [ ] `java -version` uses the exact HotSpot JDK 17+ in all steps.
- [ ] `CdsHello.java` compiles into two class files and packages into `cdslab.jar`.
- [ ] Baseline `-Xshare:off` loads `CdsHello` from the JAR.
- [ ] Dynamic training run creates `cdslab-dynamic.jsa`.
- [ ] Runtime run uses `-XX:SharedArchiveFile=cdslab-dynamic.jsa`.
- [ ] `dynamic-load.log` contains **`CdsHello source: shared objects file`** and **`Greeting source: shared objects file`**.
- [ ] Static trial run creates `cdslab.classlist` containing `CdsHello` and `Greeting`.
- [ ] `-Xshare:dump` creates `cdslab-static.jsa`.
- [ ] `static-load.log` contains the shared source of the exact app classes.
- [ ] All successful app runs produce `message=Hello, CDS` / `answer=42`.
- [ ] JDK/JAR/classpath/options do not change between creation and usage.
- [ ] If performance needs to be proven, measure startup multiple times **without verbose logs enabled** during measurement.

This checklist proves **the creation + usage + observation workflow**, avoiding mistaking an archive file's appearance for an actual optimization being applied.

## 22. Official Documentation

- [Oracle JDK 25 — `java` Command, Application Class Data Sharing](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): `SharedArchiveFile`, `DumpLoadedClassList`, `SharedClassListFile`, `ArchiveClassesAtExit`, `Xshare:dump`, `AutoCreateSharedArchive`, `jcmd VM.cds`, classpath restrictions, and `source: shared objects file` log examples.
- [Oracle JDK 25 — Java Virtual Machine Guide](https://docs.oracle.com/en/java/javase/25/vm/index.html): **Class Data Sharing**; explains `-Xshare:off`, `-Xshare:on`, `-Xshare:auto`, when strict mode is for testing.
- [Oracle JDK 25 — `java` Unified Logging](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html#enable-logging-with-the-jvm-unified-logging-framework): `-Xlog:class+load` and `-Xlog:cds` for observation.
- [OpenJDK JEP 310 — Application Class-Data Sharing](https://openjdk.org/jeps/310): bringing archived application classes into AppCDS.
- [OpenJDK JEP 350 — Dynamic CDS Archives](https://openjdk.org/jeps/350): archives created when an application exits, based on a base archive.
- [OpenJDK JEP 341 — Default CDS Archives](https://openjdk.org/jeps/341): background on the default CDS archive in the JDK.
- [OpenJDK JEP 483 — Ahead-of-Time Class Loading & Linking](https://openjdk.org/jeps/483): AOT cache and training/assembly/use workflow.
- [OpenJDK JEP 515 — Ahead-of-Time Method Profiling](https://openjdk.org/jeps/515): AOT method profiles in JDK 25, extending the warmup concept.
- [Oracle JDK 25 — `jcmd` Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jcmd.html): `VM.cds` options for dumping from a suitable JVM process.
- [OpenJDK — `java` Application Launcher Guide](https://dev.java/learn/jvm/tools/core/java/): explains dynamic CDS archives and using base/top files.

**Conclusion:** To prove that **CDS/AppCDS** has been leveraged, you need all of: **(1) the archive file is created successfully, (2) the process actually starts with a compatible archive, (3) `-Xlog:class+load` confirms the application's own classes are loaded from `shared objects file`**. Dynamic CDS is usually simple via `ArchiveClassesAtExit`; static CDS goes through `DumpLoadedClassList` and `-Xshare:dump`. Faster startup time is **a claim that requires a separate benchmark**, not something automatically proven from class-loading logs.
