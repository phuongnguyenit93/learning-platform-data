# Compatibility Conditions of an Archive or Cache with the JDK, Application, and Environment

## Learning Objectives

**JVM fast-startup** techniques often shift part of the work from application runtime to a preparation step: creating a **CDS/AppCDS archive**, writing a form of cache, or packaging analyzed data for a subsequent run to reuse. That raises a question more important than “whether the cache file exists or not”:

> **For which JVM, which application, and which environment was the archive/cache file generated? When is the JVM actually allowed to reuse it, and when must it skip or regenerate it?**

On **HotSpot Java 17**, the clearest practical and officially documented example is **Class Data Sharing (CDS) / Application Class-Data Sharing (AppCDS)** with `.jsa` files. This archive can speed up class loading and reduce part of the memory footprint, but **it is not a standard Java file that can run on every JDK, every OS, and every application version**. The JVM rejecting an archive does not mean Java bytecode becomes incorrect; in many configurations, the JVM can start via the non-archive path, with different performance.

This lesson helps you:

1. Distinguish **CDS archive**, **JIT Code Cache**, **framework cache**, and **product-specific snapshots/caches** — they do not share the same compatibility contract.
2. Grasp **the JDK build, classpath/JAR, module path, class loader, and JVM configuration conditions** that affect Java 17 archive reusability.
3. Understand **base archive and dynamic top archive**: their dependency relationship and why files cannot be arbitrarily combined.
4. Know how to **verify with CDS/class-load logs**, test configuration-change cases, and choose appropriate fallback/fail-fast behavior.
5. Create a **runnable Java 17 lab** with a JAR, static archive, dynamic archive, and a basic compatibility check suite for pipelines.
6. Avoid equating “the application prints the correct output” with “CDS is active” or “having an archive” with “faster startup”.

**Scope:** JDK/HotSpot **17** and how to evaluate related startup caches. AOT cache features in newer JDKs or snapshots of specific runtimes/frameworks may have their own rules; **do not impose options/mechanisms of newer versions onto Java 17**.

---

## 1. What Does a Compatible Archive Mean?

A Java application can run normally without an archive. Compatibility of an archive is a different matter: the JVM needs to trust that **the pre-prepared data still accurately describes the classes and runtime assumptions in the current run**.

```text
                 BUILD / PREPARE
      JDK image + app JARs + JVM options + environment
                         │
                         ▼
               Create CDS archive
                    app.jsa
                         │
               deploy / restart
                         ▼
                  RUNTIME CHECKS
      JVM build, OS/arch, base archive, JAR identities,
       classpath/module configuration, relevant VM options
                         │
               ┌─────────┴─────────┐
               │                   │
           compatible         incompatible
               │                   │
               ▼                   ▼
       Map/reuse archive     Reject/skip/error
               │                   │
               ▼                   ▼
         Java semantics       Java semantics
         remain correct       must remain correct
```

When the runtime confirms the archive is suitable, it can map the prepared class data into allowed memory addresses and reduce the corresponding load/parse/verify/link work. Compatibility depends on the **internal VM format** and its relationship to the original inputs.

If the archive cannot be used, two questions must be separated:

- **Startup capability:** Will the VM automatically fall back or halt startup? Depends on the `-Xshare` mode and the error type.
- **Performance benefit:** Is any application class data actually being shared? You must check the logs, not infer from the file being present.

### 1.1. Not Every Environment Change Has the Same Consequence

| Change | With Java 17 CDS/AppCDS | Verification Mindset |
| --- | --- | --- |
| Changing **JDK build/vendor/patch** | Archive may be incompatible | Regenerate and verify |
| Changing **JAR bytecode/content** | Archive may be rejected | Tie archive to artifact digest |
| Changing **classpath order** | May change class resolution, violating conditions | Keep classpath consistent |
| Runtime classpath appends **JAR at end of list** | Has documented prefix conditions that are allowed | Verify which classes are actually shared |
| Runtime classpath removes/reorders JARs | Risks being unusable | Compare dump/runtime details |
| Changing module path | Has its own rules, unlike classpath prefix | Check module JARs and logs |
| Adding **`--patch-module`** | Oracle JDK 17 states CDS is disabled | Do not expect to use the archive |
| Changing OS/CPU architecture | VM/memory mapping format is platform-dependent | Build archive on the exact target runtime |
| Changing hostname or pure-data business config | Do not automatically conclude it breaks CDS | Check whether it changes class-loading behavior |
| Changing heap size/GC option | Some VM options affect compatibility; not every flag causes an error | Use logs/negative tests with real configuration |
| Changing archive filename/path | May affect file lookup and dynamic layer dependency | Verify path/base mapping |
| Running multiple processes with the same valid archive file | Capable of sharing read-only pages | Compare startup and PSS/USS, do not blindly sum RSS |

**Key lesson:** whether an archive is “usable or not” is not based solely on `java -version`. Two Java 17 builds with the same version number can still differ in vendor/build/VM flags/arch or classpath.

## 2. Distinguishing “Archives” and “Caches” That May Be Lumped Together

| Type | Primary Content | Lifetime | Reuse Guaranteed Across JVM Runs? |
| --- | --- | --- | --- |
| **Default CDS archive** | Base class data prepared by the JDK | File bundled with JDK image | Yes, when compatible with that exact runtime image |
| **Static AppCDS archive** | Class metadata per class list and build/runtime inputs | `.jsa` file created by dump step | Yes, with matching JDK/classpath/VM settings |
| **Dynamic CDS top archive** | Class metadata recorded from a run, on top of a base archive | Additional `.jsa` file | Yes, when both top **and base** are compatible |
| **HotSpot JIT Code Cache** | Machine code compiled by C1/C2 during JVM execution | Process-internal memory | **Not by default** a persistent cache file reused across Java 17 processes |
| **OS page cache** | File pages already read by the OS | Managed by kernel | May help cold/warm startup, not defined by Java `SharedArchiveFile` |
| **Framework cache** | Metadata, indexes, generated config, templates, transformed data | Depends on framework | Must follow that framework's contract/version/checksum |
| **Native-image / other product snapshot** | Native binary or tool-specific serialized runtime snapshot | Separate build/runtime artifact | Does not follow CDS `.jsa` rules, has its own compatibility rules |

**Do not conflate them:** if app startup is faster on the second run, the cause may be a warm OS page cache, not that the AppCDS archive was used. Conversely, the JIT Code Cache in a warmed-up process is not a file that can be copied to another process via `-XX:SharedArchiveFile`.

### 2.1. Class Data Differs from Object Data

CDS/AppCDS is not a heap dump. It does not “freeze” the state of mutable static fields, session data, in-memory caches, database connections, or business objects so that a new process resumes at the same state.

```text
CDS archive:
  appropriate reusable class-related metadata

Not:
  Java object heap snapshot
  static field values at dump time
  JIT code/CPU register snapshot
  open sockets and thread stacks
  tokens/sessions/application secrets
```

If a product outside HotSpot supports a **checkpoint/restore** mechanism, it requires its own compatibility for OS/kernel, filesystem, PID/network, clock, encryption secrets, JVM state, and warm-up; **do not use CDS documentation to conclude it is also compatible**.

## 3. JDK and VM Build Conditions

A CDS archive stores VM data structures optimized for **a specific internal representation**. Therefore, it is not a portable format like a JAR or class file.

### 3.1. Same “Java 17” Is Not Enough

Consider these runtime changes:

```text
Temurin JDK 17 build A  → Oracle JDK 17 build B
OpenJDK 17.0.8         → OpenJDK 17.0.9
Linux x86_64           → Linux aarch64
Windows                → Linux
JDK 17                 → JDK 21
```

Do not assume a `.jsa` archive retains usability across the changes above. Specific compatibility checks belong to the HotSpot implementation; the JDK build process can change metadata layout. **Packaging the archive with the JDK image used to run it and regenerating the archive after JDK changes** is the safe operational choice.

In container environments, `image:tag` may point to a new image after a repull. Therefore, if reproducibility is needed, pin the **image digest** (and record `java -version`), not just the tag name.

### 3.2. JDK Home and Default Archive

Java 17 usually has a **default CDS archive** bundled with the distribution, such as `$JAVA_HOME/lib/server/classes.jsa` on Linux/macOS in some packaging layouts, or an equivalent path under the JDK home on Windows. The exact path depends on the JDK image/vendor/platform.

**Do not download a `classes.jsa` file from another JDK and copy it into the current JDK**. The default archive belongs to the distribution and is compatible with the runtime that built it; manually replacing it with a binary from another source can cause rejection or create a supply-chain risk.

### 3.3. Class-File Version Is Not Archive-File Version

A JVM can run Java 17 `major version 61` class files, yet a CDS archive created by a different JDK build can still be incompatible. Reasons:

- **Class files** have a format specified by the JVMS, with versioning and verification rules.
- **CDS archives** are HotSpot internal implementation data, not specified as a portable Java SE artifact.

`javac --release 17` ensures class/API output targets Java 17 within compiler scope; **it does not guarantee a `.jsa` generated from JDK build A can be mapped by JDK build B**.

### 3.4. Certain VM Flags Affect Archive Mapping Capability

CDS may require assumptions about data layout, runtime modules, compressed references, heap/memory reservation, and VM features. Certain flags/conditions can make the archive unusable or only partially usable.

Avoid making a short list of “5 flags guaranteed to disable CDS in all HotSpot Java 17 builds” if the documentation does not guarantee that. The right approach:

1. Record **all effective launcher JVM flags** at the archive creation step.
2. Run a smoke test with the **actual production configuration**, not just the build configuration.
3. Use `-Xlog:cds=info` / `-Xlog:cds=debug` to inspect skip/reject reasons.
4. If suspecting a specific option, run an A/B test changing that one option and observe.

**Specifically for Java 17, documentation explicitly states** that `--upgrade-module-path`, `--patch-module`, or `--limit-modules` disable CDS; do not automatically infer this applies to every other module-related option.

## 4. Application Conditions: JAR Content, Classpath, and Order

Both **static AppCDS** and **dynamic CDS** have important constraints on class-loading inputs. An archive is only useful when the classes loaded at runtime have identity/code/source matching when the archive was created.

### 4.1. Classpath Used at Dump Time and at Rerun Time

Oracle JDK 17 documentation specifies:

> **The classpath when creating the archive must be the same as, or a prefix of, the classpath at runtime.**

Example:

```text
Create archive:
  -cp core.jar:service.jar

Runtime:
  -cp core.jar:service.jar
→ same list, classpath condition passes if all other checks pass

Runtime:
  -cp core.jar:service.jar:optional.jar
→ archive classpath is a prefix, can pass this condition

Runtime:
  -cp service.jar:core.jar
→ order changed, no longer the same prefix

Runtime:
  -cp core.jar
→ missing component used during dump, fails this condition
```

On **Windows**, classpath elements are separated by `;`, whereas Linux/macOS typically use `:`. Do not confuse the classpath separator with the JAR file format or the **base/top archives** separator.

**Important:** “prefix allowed” does not mean an appended JAR at the end is always harmless. If the new JAR alters class resolution/loader behavior, the VM must still preserve correctness and class-sharing eligibility. Only when verification/logs confirm it should the archive be considered useful.

### 4.2. Modifying a JAR After Dump

Oracle JDK 17 states that **a CDS archive cannot be loaded if a JAR on the class path or module path was modified after archive creation** within the relevant check scope.

Operations that can cause invalidation:

- Rebuilding the application JAR with new class bytes.
- Upgrading a dependency library version.
- Replacing a JAR in `lib/` while keeping the same filename.
- Repackaging a JAR changing its manifest, entries, or related metadata.
- Copying a new file onto the same path after the archive was created.

**Do not hash only the filename.** Use content digests, release manifests, or artifact IDs to bind the archive to exact binary inputs. There are cases where rebuilding “the same source code” still produces different bytes/metadata, so do not promise the archive will work.

### 4.3. JAR Paths and Reproducible Deployment

Absolute paths, relative paths, symlinks, current working directory, and how the launcher opens JARs can all cause differences:

```text
Build:
  java -cp /app/lib/core.jar:/app/myapp.jar ...

Run:
  java -cp ./lib/core.jar:./myapp.jar ...
```

Do not assume the two notations are equivalent for every CDS compatibility check. The JVM has source path/classpath verification conditions; **keep startup commands, cwd, and layout stable**, especially in container images.

If you must relocate the application, regenerate the archive in the new layout or at least run `cds`/`class+load` verification on the target layout. Do not “solve” the “archive file exists but isn't used” problem by disabling all checks.

### 4.4. Non-Empty Directories Are Not the Same as JAR Files

According to Oracle Java 17 **CDS restrictions**:

- Classpath (`-classpath` and `-Xbootclasspath/a`) must not contain **non-empty directories** when creating/using a CDS archive under the documented constraints.
- Module path must not contain non-empty directories; only **modular JARs** are supported for archiving under the stated conditions.
- Exploded modules are not supported on the module path in the corresponding CDS workflow.

```bash
# Running a normal Java app can work:
java -cp out MyMain

# But to reliably create a Java 17 AppCDS archive, use a packaged JAR:
java -cp myapp.jar MyMain
```

These two commands illustrate **class-loading packaging**; class `MyMain` must be supplied accordingly. It does not mean the Java launcher forbids using the `out` directory in general; it simply **does not meet certain CDS archive conditions**.

### 4.5. Wildcards and Dependency Resolution

Launchers may allow `-cp "lib/*"`, but the actual JAR order and dependency set should be confirmed rather than treating a wildcard as a stable list as intended by the developer. If the JAR set changes, AppCDS conditions and class resolution behavior change.

Recommendations:

- Record the effective classpath when creating the archive.
- Keep JAR order/scope consistent between dump and run.
- Use immutable build artifacts in images/containers.
- Avoid hot-swap updating JARs under paths currently used for the archive.
- Regenerate the archive when the dependency graph changes.

## 5. Module Path: Different Rules from Classpath

Java 9+ has a module system; modular applications can be launched with `--module-path` and `-m`. With Java 17, CDS supports eligible **modular JARs**, though not every kind of module placement qualifies.

**Three principles:**

1. Classpath has the **same-or-prefix** rule between dump and runtime per docs.
2. Oracle states **there is no equivalent prefix requirement for the module path**.
3. However, JARs on the module path must still remain eligible and **unmodified** after archive creation; special module options can disable CDS.

```bash
# Example modular launcher (package/module artifacts must exist):
java --module-path mods -m com.example.app/com.example.app.Main
```

This is a **launcher syntax snippet**, not a standalone runnable app since it does not provide module descriptors/JARs. Do not assume `--module-path mods` is eligible for archiving if `mods` is an exploded directory rather than containing eligible modular JARs.

### 5.1. Module-Related Options That Disable CDS in JDK 17

The Oracle Java SE 17 launcher manual explicitly lists three groups:

```bash
--upgrade-module-path
--patch-module
--limit-modules
```

If these options appear, CDS **is disabled**. When using them to create an archive, the VM may report a dump error; when used at runtime, the JVM runs without loading CDS archives as described in the documentation.

Do not use `-Xshare:on` to “force CDS despite module patching”: strict mode does not make an incompatibility safe.

### 5.2. Custom Class Loaders, Reflection, and Plugin Systems

Frameworks with custom class loaders, proxies, generated classes, nested JARs, or runtime weaving have additional archive eligibility conditions. Java 17 CDS supports some class loading via custom class loaders under certain rules, but **does not guarantee every dynamic proxy/generated class is always archived**.

Examples of changes to watch:

- A plugin class loader loads JARs differently in startup A vs startup B.
- A new framework version generates classes with different names/contents.
- A bytecode instrumentation agent alters classes before/during loading.
- The application toggles feature flags that change the set of loaded classes.
- A “Fat JAR” launcher unpacks nested JARs differently from a flat classpath.

**Workflow:** use the framework's exact startup script, warm up representative code paths, enable `-Xlog:class+load=info`, and check whether **the application's own classes** show `source: shared objects file`. Seeing a core class shared does not prove the entire framework is shared.

## 6. Static Archive, Dynamic Archive, and Base–Top Conditions

In HotSpot Java 17, **up to two CDS archive layers** can be configured according to the Java launcher docs:

```text
           Static/base archive
                   │
                   ▼
           Dynamic/top archive
                   │
                   ▼
          Runtime maps base + top
```

General form:

```text
-XX:SharedArchiveFile=<static_archive>:<dynamic_archive>
```

On Windows, use `;` as the separator instead of `:`. If there is only one archive file, the VM determines the corresponding format/layer via the file's metadata; a dynamic archive stores information about the compatible base archive, so `-XX:SharedArchiveFile=top.jsa` alone may suffice when the default/custom base matches.

### 6.1. Static Archive

Typical workflow:

1. Run the application to record `app.classlist`.
2. Create `app-static.jsa` with `-Xshare:dump` + `SharedClassListFile`.
3. Rerun with `SharedArchiveFile`.

Compatibility must consider JDK build, classpath/other options, and JAR files. Having a static archive does not mean “input JARs are unnecessary” at runtime.

### 6.2. Dynamic Archive

Typical workflow:

1. Have a compatible base CDS archive.
2. Run the application with `-XX:ArchiveClassesAtExit=app-dynamic.jsa`.
3. The JVM writes the dynamic **top** archive upon proper exit.
4. Subsequent runs use `-XX:SharedArchiveFile=app-dynamic.jsa` or specify base/top.

**A dynamic archive does not exist independently of base compatibility assumptions**. If the default CDS archive is replaced or the JDK build changes, the dynamic top may be rejected. You cannot copy only the top archive to another image and assume it carries all base class data with it.

### 6.3. “Dynamic” Does Not Mean Auto-Updating the Cache on Every Run

`ArchiveClassesAtExit` writes at the **end of a run**. It does not mean:

- Whenever a new class is loaded, the `.jsa` file is updated immediately.
- Old files always auto-sync if JARs change.
- The JVM automatically deletes every incompatible archive.
- Every HotSpot Java 17 build already has an `AutoCreateSharedArchive` behavior like newer JDKs.

If the application changes, you must **regenerate the archive** following the proper workflow, not wait for the old cache to “update” itself.

### 6.4. When Base Changes While Top Is Forgotten

```text
Run A:
  JDK image A → base-A.jsa → app-top-A.jsa

Run B:
  JDK image B → base-B.jsa + app-top-A.jsa
                                 │
                                 ▼
                      compatibility is not guaranteed
```

A good release strategy is publishing **JDK image + application JARs + custom/base/top archives** as a single versioned unit. Change any significant component → regenerate and test on target.

## 7. AppCDS Does Not Share Rules with the JIT Code Cache

HotSpot Java 17 also has the term **Code Cache**, which is the memory region holding compiled machine code generated by C1/C2 at runtime. Despite having “cache” in the name, it differs from CDS:

- JIT compiled code typically depends on CPU instructions, receiver type profiles, compiler decisions, VM runtime addresses, and class-loading assumptions.
- It is managed by the JVM process; there is no standard Java SE 17 mechanism to dump the entire JIT Code Cache into `jit.jsa` and pass it to `SharedArchiveFile`.
- `-XX:ReservedCodeCacheSize` controls code cache capacity (per HotSpot), **it does not create a persistent disk archive**.
- Code cache can be reclaimed/swept during runtime when compiled code is no longer used.
- With warm-up in the same process, the JIT has compiled methods and later calls run faster; that is **not** evidence of CDS compatibility between two processes.

```text
CDS .jsa:          disk artifact → mapping class data across JVM processes
JIT Code Cache:    in-process machine code → JIT runtime optimization
OS page cache:     kernel-managed file pages → may affect disk I/O/startup
Framework cache:   provider-defined data → version/config validity rules
```

**Note:** Profile-guided optimization or AOT compilation mechanisms available in other JDKs/VMs/products do not automatically turn HotSpot JDK 17 into “having a portable AOT cache”. If a project actually uses a separate accelerator, read the documentation for **that exact version** and define its own compatibility rules, rather than mechanically applying the CDS table.

## 8. Framework Caches: Must Define Cache Key and Invalidation

A framework may cache generated serializers, JSON schemas, classpath scanning indexes, dependency injection metadata, or generated bytecode. Validity may depend on:

- Framework version, serializer/compiler version.
- Set of classes/JARs and content digests.
- Configuration flags, annotations, profiles, and active modules.
- Data model/schema version, database mappings.
- Locale/timezone or resource bundles if the cache holds environment-dependent data.
- OS/architecture if the cache stores native code or addresses.
- Secrets/tenant-specific config if the cache holds sensitive data.

There is no universal Java SE rule that “a framework cache is valid as long as the JDK major version is the same”.

### 8.1. Defining a Compatibility Contract for Caches You Build Yourself

Example metadata manifest (illustrative data format only, not a format HotSpot reads automatically):

```text
cacheFormatVersion=3
javaVendor=ExampleVendor
javaRuntimeVersion=17.0.x+build
osArch=amd64
appArtifactSha256=...
dependencyGraphSha256=...
configFingerprint=...
serializerVersion=...
generationEpoch=...
```

An application cache should have a **versioned cache format**, hashes or signatures of underlying inputs, integrity checks, atomic publication, and measurable fallback. Which fields matter depends on that specific cache; do not assume you should store or send secrets in plaintext inside a manifest.

**For CDS archives**, an external manifest can be used for release/CI management, but it **does not replace VM internal compatibility checks**.

## 9. Java 17 Runnable Lab: One JAR for Archive Tests

Here is a minimal application with two nested classes to observe class loading. Save **`ArchiveCompatibilityDemo.java`**:

```java
import java.util.List;
import java.util.Locale;

public final class ArchiveCompatibilityDemo {
    static final class Catalog {
        List<String> items() {
            return List.of("java", "jvm", "cache");
        }
    }

    static final class Formatter {
        String format(String value) {
            return value.toUpperCase(Locale.ROOT);
        }
    }

    public static void main(String[] args) {
        Catalog catalog = new Catalog();
        Formatter formatter = new Formatter();
        List<String> items = catalog.items();

        int count = 0;
        for (String item : items) {
            count += item.length();
        }

        System.out.println("items=" + items.size());
        System.out.println("totalChars=" + count);
        System.out.println("first=" + formatter.format(items.get(0)));
        System.out.println("version=" +
                Runtime.version().feature());
        System.out.println("done");
    }
}
```

**Prepare with JDK 17:**

```bash
mkdir -p out
javac --release 17 -d out ArchiveCompatibilityDemo.java
jar --create --file archive-demo.jar \
    --main-class ArchiveCompatibilityDemo -C out .
```

The commands use POSIX shell syntax; on Windows you can write the `javac`/`jar` commands on one line and use `mkdir out` according to your shell.

**Run normally on JDK 17:**

```bash
java -cp archive-demo.jar ArchiveCompatibilityDemo
```

**Exact application stdout on JDK 17, without diagnostic logs enabled:**

```text
items=3
totalChars=12
first=JAVA
version=17
done
```

Because `"java"` has 4 characters, `"jvm"` has 3 characters, `"cache"` has 5 characters, totaling **12**. `Runtime.version().feature()` equals **17** on a JDK 17 runtime. If you intentionally run this JAR on a newer JDK, the `version=...` line will change; therefore the example specifies stdout **within the stated Java 17 scope**.

### 9.1. Why Package Into a JAR After Compiling?

Oracle Java 17 AppCDS restrictions do not support non-empty classpath directories in archive creation/usage scenarios. We package `archive-demo.jar` to keep the same binary input across trial/dump/runtime.

**Do not modify the JAR file contents between the dump step and the runtime step**. If you edit `out` and re-run `javac` without rebuilding the JAR, the JAR remains old; if you rebuild the JAR, the old archive may become incompatible — both situations must be clearly distinguished.

## 10. Static Archive Lab — Create, Run, Verify

### 10.1. Trial Run to Create Class List

```bash
java -Xshare:off \
  -XX:DumpLoadedClassList=archive-demo.classlist \
  -cp archive-demo.jar ArchiveCompatibilityDemo
```

The command runs `main` and writes the **class list file**. File contents depend on which classes the runtime actually loads. The classlist file is not an archive; creating the archive requires the next step.

### 10.2. Create Static Archive

```bash
java -Xshare:dump \
  -XX:SharedClassListFile=archive-demo.classlist \
  -XX:SharedArchiveFile=archive-static.jsa \
  -cp archive-demo.jar
```

In `dump` mode, the JVM creates `archive-static.jsa`. This is **not** an execution of `ArchiveCompatibilityDemo.main()`, so it is not required to produce business stdout like Section 9.

### 10.3. Rerun and Verify

```bash
java -Xshare:auto \
  -XX:SharedArchiveFile=archive-static.jsa \
  -Xlog:cds=info,class+load=info \
  -cp archive-demo.jar ArchiveCompatibilityDemo
```

The application **must still produce the same business output** as Section 9. In addition, there are VM logging lines, which may include class-loading sources like **`source: shared objects file`**. Timing, line counts, addresses, and class loading order depend on the JDK build, so **do not fabricate a fixed logger transcript**.

### 10.4. Baseline Without CDS

```bash
java -Xshare:off -cp archive-demo.jar ArchiveCompatibilityDemo
```

This is the baseline comparison: the application runs with correct Java semantics without using CDS. When comparing startup time, run multiple times with the same JDK/CPU/heap/cwd/JARs and account for a warm filesystem page cache.

### 10.5. What Proves Compatibility?

- The archive file exists and has no read-permission errors.
- Runtime logs show CDS mapping succeeded.
- Some **application classes** in the logs have `source: shared objects file`, not just `java.base` classes.
- No relevant archive reject/skip messages appear.
- Business output remains correct.
- Results are repeatable in the target environment.

Simply having exit code 0 and `done` **is not enough to prove** the archive was used.

## 11. Dynamic Archive Lab — Base/Top and Compatibility

### 11.1. Create Dynamic Top Archive on JVM Exit

```bash
java -Xshare:auto \
  -XX:ArchiveClassesAtExit=archive-dynamic.jsa \
  -cp archive-demo.jar ArchiveCompatibilityDemo
```

If the JVM has a compatible base archive and shutdown/dump succeeds, `archive-dynamic.jsa` will be created. It adds eligible classes that were loaded but not present in the base; it does **not** contain a copy of the entire heap.

### 11.2. Use the Dynamic Archive

```bash
java -Xshare:auto \
  -XX:SharedArchiveFile=archive-dynamic.jsa \
  -Xlog:cds=info,class+load=info \
  -cp archive-demo.jar ArchiveCompatibilityDemo
```

HotSpot uses information about the associated base archive from the dynamic archive. If the base changes or no longer maps compatibly, the dynamic top may not be used. Do not copy the top archive to another JDK and assume it is standalone.

### 11.3. Option to Specify Both Base and Top

If you have a compatible custom static base archive, you can try:

```bash
# Once you have a custom base and created a top on top of this base:
java -XX:SharedArchiveFile=base.jsa:top.jsa \
  -cp archive-demo.jar ArchiveCompatibilityDemo
```

The `:` is the delimiter on POSIX; Windows uses `;`. This is an **illustrative snippet** because `base.jsa`/`top.jsa` must be created beforehand from the exact JDK and application.

**Do not concatenate binary files with `cat base.jsa top.jsa > both.jsa`**. Header/layer structure is managed by HotSpot; the proper configuration option is `SharedArchiveFile`.

## 12. Hands-On Testing of Incompatibility Scenarios

The following experiments should be done in an **isolated lab workspace**; do not modify production JARs to test:

### Scenario A — Replace App JAR After Dump

1. Create `archive-static.jsa` with JAR version A.
2. Intentionally modify the source and build JAR version B at the same path.
3. Run with archive A and enable `-Xlog:cds=debug,class+load=info`.
4. Record exit code, CDS reason, and classes actually loaded.
5. Regenerate the archive with version B and verify again.

**Verifiable expectation:** the old archive file is not trusted if the source JAR changed according to CDS checks. **Do not claim every VM build prints the exact same error sentence**, and do not use strict mode in production.

### Scenario B — Change JAR Order

```text
Archive creation classpath:
  lib/a.jar:lib/b.jar

Runtime classpath:
  lib/b.jar:lib/a.jar
```

The runtime classpath no longer has the same order/prefix. This can alter class resolution. Do not force the JVM to use the archive by renaming files; standardize JAR order and regenerate the archive if production startup classpath differs.

### Scenario C — Change JDK Patch/Vendor

- Archive on build X.
- Launch with JDK build Y.
- Observe logs/exit code.
- Regenerate archive under build Y.
- Verify under that same build Y.

There is no rule that “same major version 17 means the `.jsa` file is definitely portable”. Use build-specific artifact metadata in CI.

### Scenario D — Add `--patch-module`

When a command line effectively contains `--patch-module`, Oracle JDK 17 docs state **CDS is disabled**. This is a clear negative test to teach the difference between JDK module configuration and a binary archive:

```text
CDS enabled app run ≠ app run with --patch-module
```

Do not test it by passing a fake module path and blaming every launch failure on CDS; only test when you have a proper modular application and legitimate patching.

### Scenario E — Default Base Is Replaced

A dynamic top is created on JDK X's default base. If JDK Y's base archive differs, the dynamic top may be incompatible. Regenerate the top with runtime Y's own base; do not reuse it based on faith in an identical filename.

## 13. How `-Xshare:off`, `auto`, and `on` Affect Fallback

| Mode | Intent | When Archive Is Unusable |
| --- | --- | --- |
| `-Xshare:off` | Do not use CDS | JVM still runs via the non-archive path if there are no other errors |
| `-Xshare:auto` | Use CDS when eligible | Typically can skip an unsuitable archive per policy; must check error type and logs |
| `-Xshare:on` | Require CDS via strict mode | If archive cannot be used, may **halt startup with an error** |
| `-Xshare:dump` | Create static archive | Dump error fails the preparation step; not application startup |

**Do not treat `-Xshare:on` as “enabling stronger optimization”.** It mainly sets a strict expectation that CDS must be usable. Oracle Java 17 CDS docs state `on` is **for testing purposes** and should not be used in production if the environment might change JDK/options.

### 13.1. Production Fallback Is an Operational Decision

A service that must prioritize startup availability can use `-Xshare:auto` with metrics to detect skipped archives, then rebuild in the next release. A CI preflight that needs early error detection can run a **strict smoke test** in a controlled environment.

Avoid two extremes:

- **Silent ignore:** “The app runs so AppCDS must be fine”; can silently lose startup benefits.
- **Strict everywhere:** “Every JVM process must force CDS with `on`”; can turn an archive mismatch into an outage.

Good design: **fail-fast in CI, availability-conscious in production, alert when expected sharing disappears**.

## 14. Reading Logs to Distinguish Mismatch from Miss Due to Unloaded Class

Key HotSpot Java 17 options:

```bash
-Xlog:cds=info
-Xlog:cds=debug
-Xlog:class+load=info
-Xlog:cds=debug,class+load=info
```

**`cds` logs** show archive open/map/validation operations. **`class+load` logs** show the source of each class when loaded.

An **illustrative** line example, not a lab transcript:

```text
[info][class,load] ... source: shared objects file
[info][class,load] ... source: file:/app/archive-demo.jar
```

How to read it:

- `source: shared objects file` for a class: that class was loaded from the shared archive.
- `source: file:/...jar`: in that run the JVM read from the JAR; does not prove the entire archive was unused.
- Log reports archive skipped/incompatible: must address the reason before expecting startup benefits.
- Only seeing JDK core classes from the shared archive: **default CDS may be working**, while AppCDS classes may not be shared yet.
- A class not loaded in the workload has no evidence to conclude it is shared, even if the class file is in the JAR.

### 14.1. Check Application Classes, Not Just JVM Classes

The example has nested classes:

```text
ArchiveCompatibilityDemo
ArchiveCompatibilityDemo$Catalog
ArchiveCompatibilityDemo$Formatter
```

In the run's `class+load` log, search for these classes and their sources. Do not infer from `java.lang.String` or `java.util.List` being shared that the custom AppCDS archive worked.

### 14.2. Check After Upgrade, Not Just After Build

An archive verified on the build machine **does not prove** it works on the target container/host because the environment may differ. Add a controlled **post-deploy smoke test** or startup log inspection.

When runtime must handle a mismatch error, record **JDK/vendor/build, archive ID/checksum, app artifact digest, classpath/module options, and CDS log reason**. This data helps distinguish “JDK changed” from “JAR changed” instead of only looking for a missing file.

## 15. Compatibility Check Mechanism for CI/CD

A release pipeline can follow these steps:

```text
    Pin JDK image digest and runtime architecture
                        │
                        ▼
    Build immutable JARs + dependency manifest
                        │
                        ▼
    Record effective classpath/module configuration
                        │
                        ▼
       Create static or dynamic CDS archive
                        │
                        ▼
       Record metadata/digests of artifact inputs
                        │
                        ▼
      Smoke test on SAME runtime image/flags
         -Xlog:cds,class+load
                        │
                 ┌──────┴──────┐
                 │             │
             PASS used?      NO / fallback?
                 │             │
                 ▼             ▼
      Package JDK+JAR+JSAs   Regenerate/diagnose
                 │
                 ▼
      Deploy immutable unit + post-deploy verify
                 │
                 ▼
       Monitor startup time + memory footprint
```

### 15.1. Metadata Manifest — External Helper, Not a VM Format

Example release information to record:

```text
runtime.version=17.0.x+build
runtime.vendor=<vendor>
runtime.imageDigest=<digest>
os.arch=<architecture>
archive.type=static-or-dynamic
archive.baseId=<base-id-if-any>
archive.sha256=<sha256>
application.jar.sha256=<sha256>
dependencies.lock.sha256=<sha256>
classpath.signature=<canonicalized-cp-hash>
modulepath.signature=<canonicalized-mp-hash>
required.vm.options=<recorded-keys>
```

The placeholders only represent an **illustrative schema** for CI, not a Java program to compile. **CDS archives do not read this manifest file**: the VM still checks internal conditions itself.

### 15.2. Atomic Publication and File Permissions

Create the archive at a **temporary path** in the build/job, verify success, then rename/publish **once** using the appropriate filesystem mechanism. Avoid letting one process read the file while another process is still writing it.

- Mount only archives from trusted sources.
- The run user must have **read permission on the archive** and **traverse/access permission on parent directories**.
- Dumping requires **create/write permission** at the destination.
- Do not use the same `app.jsa` name for multiple concurrent builds.
- Perform checksum/size sanity checks when moving artifacts through storage systems.
- Avoid manually editing binary `.jsa` files; the format belongs to HotSpot.
- If multiple runtime processes share an immutable archive, keep the file stable so the OS can share mapped pages under platform conditions.

## 16. Deployment Environment: Containers, OS, CPU, and Storage

### 16.1. Docker/Kubernetes

A container image can hold the JDK, application JARs, and archive in a clean layout:

```text
/app/
  jdk/
  lib/
    app.jar
    dep-a.jar
  cds/
    app.jsa
```

This is a **deployment layout**. When building the image:

- Pin the **JDK image/build** and architecture in the build stage.
- If using a multi-stage build, do not create the archive with a builder JDK different from the runtime JDK.
- Keep JARs/dependencies immutable and paths compatible.
- If building a multi-arch image, create/verify the archive for **each target architecture**.
- Distinguish the ephemeral writable layer from the immutable archive used at startup.
- If the archive is created at pod shutdown via `ArchiveClassesAtExit`, an ephemeral filesystem/pod deletion can cause the file not to exist for the next pod; use a dedicated archive-generation build job or persistent artifact publishing.
- Do not rely on `SIGKILL` shutdown for archive-at-exit to complete.

### 16.2. CPU Instruction Set and OS

Machine code stored in the JIT Code Cache can use specific CPU instructions. A CDS archive is not JIT-compiled code, yet it is still a binary VM artifact with platform/build assumptions; **do not assume an archive can be moved from Linux x86_64 to Windows/aarch64**.

File paths, separators, and permissions also differ. On Windows, `-XX:SharedArchiveFile=base.jsa;top.jsa` uses `;` as the delimiter. On POSIX, use `:` per Oracle documentation.

### 16.3. Storage, Memory Mapping, and File Permissions

CDS needs to read/map the archive file according to OS/VM capabilities. Issues can include missing file, permission denied, truncation, mapping constraints, or artifact corruption.

A file named `app.jsa` with 0 bytes is clearly not a useful archive. Yet a large file with a valid checksum **is also not enough**: the JVM must validate internal contents and compatibility.

### 16.4. Multiple JVM Processes and Shared Pages

One benefit of CDS is that the OS can share read-only mapped pages across multiple processes on the same host. However, **it is not guaranteed** that every container/pod shares the same physical pages if filesystems/mounts/builds differ.

When measuring memory:

- `RSS` across multiple processes can include shared pages and get double-counted when summed.
- `PSS` or metrics separating shared/private memory (if supported by the OS) are more useful when evaluating total savings.
- Each process's heap objects/static mutable states do not become shared business data just because of AppCDS.

## 17. Measuring “Compatibility” and “Faster” Are Two Different Tests

**Compatibility test** asks:

> Is the archive **accepted and actually used** by the JVM?

**Performance test** asks:

> Does the application's startup/readiness/memory footprint **improve significantly and repeatably** compared to the baseline?

Compatibility **does not automatically guarantee** measurable benefit. If the app is very small, class-loading time may be negligible compared to OS process startup. Conversely, a large app with many startup classes may benefit more.

### 17.1. Choose the Right Startup Metric

- JVM process launch → first Java log.
- Process launch → service listen port opened.
- Process launch → readiness check satisfied.
- Process launch → first successful business request.

Measure the same definition across all configurations. If the process has lazy initialization, “main printed done” is not necessarily when the service is actually ready.

### 17.2. Meaningful Three-State Comparison

```bash
# Without CDS:
java -Xshare:off -cp archive-demo.jar ArchiveCompatibilityDemo

# With default CDS (if eligible):
java -Xshare:auto -cp archive-demo.jar ArchiveCompatibilityDemo

# With verified AppCDS archive:
java -Xshare:auto -XX:SharedArchiveFile=archive-static.jsa \
  -cp archive-demo.jar ArchiveCompatibilityDemo
```

Run multiple times, alternate order to reduce OS page cache bias, fix host load/JDK/CPU quotas, and analyze median/p95 along with counts. Do not claim one configuration is X% faster from a single run of a very short demo.

### 17.3. Do GC and JIT Logs Replace CDS Logs?

No. `-Xlog:gc*` focuses on GC events, and `-XX:+PrintCompilation` on JIT compilation. To check whether classes use CDS, inspect `-Xlog:cds` and `-Xlog:class+load`; then use GC/JIT logs when explaining other performance aspects.

An accurate statement: **“AppCDS can reduce class loading cost; JIT, GC, and application initialization still remain.”**

## 18. Common Failure Scenarios and Recommended Actions

| Symptom | Possible Cause | Action |
| --- | --- | --- |
| JVM reports archive rejected after JDK upgrade | VM build/internal layout changed | Regenerate on exact runtime JDK |
| Run succeeds but no app classes seen shared | Default CDS used, AppCDS mismatched or classes ineligible | Check `cds`/`class+load` and classpath |
| Static dump reports non-empty directory issue | Archive classpath not using proper JARs | Package classes into JAR |
| Dynamic top unused after image change | Base archive dependency mismatch | Regenerate top on new runtime's base |
| Runtime classpath differs from build/dump | JAR order/path/content changed | Sync classpath and rebuild archive |
| Module patching in effect | `--patch-module` disables CDS per Java 17 docs | Accept running without CDS or change design |
| App runs with `-Xshare:off` | Configuration disables sharing | Fix launcher if archive usage is desired |
| Strict `-Xshare:on` fails startup | Archive fails compatibility/availability | Do not use strict in production; fix archive in CI |
| Archive file missing in container | Not copied into runtime image, different mount/path | Verify image filesystem/digest |
| Archive file not created on shutdown | App killed/did not finish dumping | Dedicated generation run + graceful exit |
| Startup time unchanged | Classes not benefiting or another bottleneck | Verify class sources and profile startup |
| Only default classes shared | App-specific archive unused/low hits | Representative warm-up, check eligibility |
| Multi-pod memory does not decrease | Not actually sharing pages, data mostly heap | Measure PSS/USS and deployment file mapping |
| Wrong app logic after upgrade | Classpath/class loader/deployment bug, do not blame archive immediately | Run `-Xshare:off` baseline + analyze logs |
| Framework cache returns wrong data | Cache key missing dependency/config version | Fix framework-specific invalidation strategy |

### 18.1. `-Xshare:off` Is an A/B Diagnostic, Not a Cure-All

If the JVM starts with `-Xshare:off` but fails with a custom archive, that is a compatibility/option clue. However, if the application still throws `ClassNotFoundException` or corrupts business data in both modes, do not blame the archive.

Keep logs from both runs and compare effective classpath, JVM version, and exceptions.

## 19. Misconceptions to Eliminate

1. **“An archive works on any machine with Java 17.”** False. VM build/arch/classpath and runtime assumptions may differ.
2. **“Java class files are portable so `.jsa` is also portable.”** False. A CDS archive is a HotSpot-specific binary artifact.
3. **“AppCDS replaces JAR files.”** False. JARs/classpath/resources are still required and must match.
4. **“Renaming a JAR is enough to make the cache compatible again.”** False. Validity depends on checked contents/resolution paths.
5. **“Changing a dependency while keeping the JAR name means the archive will still work.”** False.
6. **“Runtime classpath can freely reorder JARs.”** False. Order affects class resolution and the prefix rule.
7. **“A classpath directory that works with `java -cp` can always be AppCDS-archived.”** False. Non-empty directory restrictions apply.
8. **“Module path must always be a prefix like classpath.”** False. Oracle docs distinguish the two cases.
9. **“`--patch-module` is unrelated to CDS.”** False. Per Java 17 docs, it disables CDS.
10. **“Both static and dynamic archives are self-contained with all JDK classes.”** False. Dynamic top depends on base.
11. **“You can concatenate any `.jsa` files into one shared file.”** False. The VM manages archive format/layering.
12. **“A dynamic archive from JDK A will definitely work with JDK B's base.”** False.
13. **“`ArchiveClassesAtExit` continuously updates the cache file while the app runs.”** False.
14. **“App exiting 0 proves AppCDS was used.”** False. Must check CDS/class-load logs.
15. **“Seeing `java.lang.String` shared is enough to prove the custom app archive works.”** False.
16. **“`-Xshare:on` is a faster mode than `auto`.”** False. `on` is strict and risks failing startup.
17. **“JIT Code Cache is saved by default to `.jsa` for other JVMs to reuse.”** False.
18. **“A warm OS page cache is a sign CDS is enabled.”** False. Two independent mechanisms.
19. **“A framework cache has the same rules as a CDS archive.”** False. Each provider defines its own contract.
20. **“Adding CPU will make an archive compatible.”** False. CPU can improve speed, not alter binary compatibility.
21. **“CDS shares the entire Java heap and static fields across processes.”** False. Shares class data, not mutable business state.
22. **“Same major JDK 17 is enough when building multi-arch images.”** False.
23. **“CDS compatibility failures must always crash the process.”** False. `auto` can fall back, `on` typically fails strictly.
24. **“Seeing few GC events proves the archive was used.”** False. GC logs do not inspect class metadata sources.
25. **“Increasing `-Xmx` always fixes archive mapping failures.”** False.
26. **“An archive accepted by the JDK means startup is guaranteed to drop by 50%.”** False. Must measure real workloads.
27. **“You can dump an archive when an app is SIGKILLed and still get a complete file.”** False.
28. **“A `.jsa` file with a valid name must have valid contents.”** False. Requires integrity and VM validation.
29. **“CDS caches carry application config and secrets.”** False. It is not a heap/config snapshot.
30. **“A new JDK vendor is guaranteed compatible with an old vendor's archive if build numbers match.”** Not guaranteed.
31. **“With `java -jar`, runtime classpath is always identical to `-cp` at dump time.”** Not a general rule; launcher/class-loader behavior can differ.
32. **“On archive mismatch, disable VM internal validation.”** False. Regenerate the archive with the right inputs.
33. **“AppCDS automatically caches all future plugin classes.”** False. Eligibility/loading/trial profile have limits.
34. **“Need to use `-Xshare:on` to verify in production.”** False. Test strictly in CI, avoid making services outage-prone.
35. **“A Docker tag is immutable by name so the archive is immutable too.”** Not certain; tags can be republished, need image digest.
36. **“CDS archive compatibility means input source code didn't change.”** Not enough; VM build, JAR bytes/paths, options, and module config also matter.

## 20. Self-Check and Answers

**Q1.** An archive is created from JDK 17.0.8 vendor A, run under JDK 17.0.9 vendor B. Can you be sure the `.jsa` file is valid?

**Answer:** No. A CDS archive is a VM-build-specific artifact; regenerate on the target runtime JDK and verify.

**Q2.** Dump classpath is `a.jar:b.jar`; runtime classpath is `a.jar:b.jar:c.jar`. Does this necessarily violate the classpath prefix rule?

**Answer:** No. The dump classpath is a prefix of the runtime classpath; however, other conditions must still hold, and classes must be verified from logs.

**Q3.** Dump classpath is `a.jar:b.jar`; runtime becomes `b.jar:a.jar`. How to handle?

**Answer:** Restore the correct order and JARs or regenerate the archive with the target classpath; do not just rename the archive file.

**Q4.** Why is having `.jsa` and the program printing the right output not enough to prove AppCDS?

**Answer:** The JVM can run without using the archive and still preserve Java semantics. Need `-Xlog:cds` and `-Xlog:class+load` to check mapping/class source.

**Q5.** Can a dynamic archive be moved to another JDK by keeping only the top file?

**Answer:** Not guaranteed. Top depends on base and corresponding VM assumptions.

**Q6.** Does `-XX:ReservedCodeCacheSize` make `.jsa` archive files hold machine code after JIT warm-up?

**Answer:** No. It controls the in-process JIT code cache size, not creating a persistent AppCDS artifact.

**Q7.** How does `--patch-module` affect CDS according to Java 17 docs?

**Answer:** Disables CDS within the scope of Oracle launcher guidance.

**Q8.** If you want to use an archive but do not want the service to fail just because CDS is unusable, should you choose `-Xshare:off` or `-Xshare:auto`?

**Answer:** Usually choose `-Xshare:auto` with logging/monitoring; `off` does not use CDS, while strict `on` can fail startup.

**Q9.** Are the JDK's default CDS archive and a custom AppCDS archive the same?

**Answer:** No. Default mainly contains base classes; custom AppCDS can add application classes and dependencies per workflow.

**Q10.** Seeing class `ArchiveCompatibilityDemo` from shared objects file is enough to conclude all application classes are shared?

**Answer:** Not yet. It only concludes that specific class was shared in this run; check other classes if needed.

**Q11.** In the Java 17 lab, what is the stdout `totalChars`?

**Answer:** **12** from the lengths of `java`(4), `jvm`(3), `cache`(5).

**Q12.** In the lab, what value does `Runtime.version().feature()` print when running on JDK 17?

**Answer:** **17**.

**Q13.** Why does updating an app JAR at the same path still cause the archive to be rejected?

**Answer:** Binary contents/metadata and class identity assumptions no longer match the data at dump time.

**Q14.** If an app uses many custom class loaders/nested JARs, can all classes be assumed archivable?

**Answer:** No. Eligibility and startup behavior depend on loader/VM/framework and must be checked via runtime logs.

**Q15.** How can measuring memory savings across multiple JVMs by summing RSS be wrong?

**Answer:** Shared mapped pages are counted in the RSS of multiple processes; total RSS can double-count. Consider PSS/USS or appropriate OS tools.

**Q16.** Why can the OS page cache skew startup benchmark results?

**Answer:** Later runs may read JARs/archives from a warmed page cache, appearing faster even though CDS policy did not change. Need multiple runs and alternating order.

**Q17.** If CI uses JDK 17 but the production image contains JDK 21, what should be done?

**Answer:** Do not carry the JDK 17 archive over as a portable artifact. Use the exact production JDK/image when generating and verifying the archive.

**Q18.** Where should `-XX:ArchiveClassesAtExit` write in an ephemeral pod environment?

**Answer:** Use an archive-generation job with appropriate filesystem/artifact publishing and graceful exit; files written in a pod's ephemeral layer can be lost when the pod is deleted.

## 21. Pre-Deployment Checklist

- [ ] **JDK:** check vendor/version/build, VM variant, OS/CPU architecture.
- [ ] **Inputs:** keep application/dependency JARs immutable, store digests.
- [ ] **Classpath:** keep exact JARs and order; check same-or-prefix rule.
- [ ] **Module path:** use eligible modular JARs, avoid exploded modules in CDS flow.
- [ ] **Module flags:** verify none of the options that disable CDS per Java 17 guide are used.
- [ ] **Custom loaders:** verify application classes are actually archived/shared.
- [ ] **Base–top:** dynamic top must be paired with the exact static/default base and same runtime.
- [ ] **Archive file:** correct path, read permissions, uncorrupted, not partially written.
- [ ] **Build pipeline:** create and verify archive using production runtime image/configuration.
- [ ] **CI:** run smoke test checking CDS logs and application stdout.
- [ ] **Production:** prioritize availability and logging, do not enforce strict mode without a fallback strategy.
- [ ] **Observability:** record CDS reject/skip reasons and class load sources.
- [ ] **Benchmark:** compare no-CDS/default/custom under the same environment and metrics.
- [ ] **Multi-arch:** generate/check artifacts appropriate for each architecture.
- [ ] **Rebuild trigger:** JDK/JAR/modules/classpath changed ⇒ regenerate and test.
- [ ] **Other caches:** apply provider-specific version/config/integrity contracts.

## 22. Summary

```text
                       HAVE ARCHIVE / CACHE
                              │
                              ▼
                  IDENTIFY THE EXACT TYPE
                ┌─────────────┼──────────────┐
                │             │              │
             CDS/AppCDS     JIT Code       Framework cache
               .jsa          Cache          / snapshot
                │             │              │
                ▼             ▼              ▼
       JVM build + jars   Runtime-only    Provider-specific
       paths + VM flags   compiled code   compatibility key
       + base/top + OS         │              │
                │             │              │
                └─────────────┴──────────────┘
                              │
                              ▼
                VALIDATE IN TARGET RUNTIME
                              │
             ┌────────────────┴───────────────┐
             │                                │
         COMPATIBLE                       INCOMPATIBLE
             │                                │
             ▼                                ▼
     Share archived class data         Fallback / fail / rebuild
             │                                │
             └────────────────┬───────────────┘
                              ▼
                  SAME JAVA SEMANTICS
                              │
                              ▼
       VERIFY logs and measure real startup/footprint
```

**Conclusion:** A fast-startup archive or cache **is only valuable when inputs and runtime still match the assumptions made at creation time**. For **Java 17 CDS/AppCDS**, check **JDK/HotSpot build, OS/architecture, application JARs, classpath prefix/order, module constraints, base–dynamic archives, and relevant JVM flags**. **`-Xshare:auto`** is better suited for a service needing availability; **`-Xshare:on`** is useful for fail-fast in testing but can prevent production from starting. Always inspect `cds`/`class+load` logs to prove the archive is actually used; only then measure startup/footprint. **Do not apply CDS rules to JIT Code Cache, framework caches, or AOT mechanisms of other JDKs**.

### Official References

- [Oracle JDK 17 — `java` launcher, Application Class Data Sharing](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): classpath/module rules, static/dynamic archive, base/top syntax, `Xshare` modes, `jcmd`.
- [Oracle Java SE 17 — Class Data Sharing](https://docs.oracle.com/en/java/javase/17/vm/class-data-sharing.html): default archive, dynamic archive, memory/startup goals, availability notes.
- [JEP 310 — Application Class-Data Sharing](https://openjdk.org/jeps/310): mechanism extending CDS to applications.
- [JEP 341 — Default CDS Archives](https://openjdk.org/jeps/341): default archive built with the JDK.
- [JEP 350 — Dynamic CDS Archives](https://openjdk.org/jeps/350): dynamic top archive and usage principles.
- [Oracle JDK 17 — `jcmd` reference](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): diagnostic commands in environments with attach.
- [Oracle Java SE 17 — JVMS Chapter 4](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html): Java class-file format differs from binary CDS archive.
