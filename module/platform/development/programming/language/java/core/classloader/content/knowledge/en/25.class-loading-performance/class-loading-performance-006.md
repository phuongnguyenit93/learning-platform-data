# CDS, AppCDS, and Limitations by ClassLoader or Runtime Configuration

> **Java Core → ClassLoader → Performance.** Class Data Sharing (**CDS**) and Application Class Data Sharing (**AppCDS**) are HotSpot/OpenJDK techniques for storing processed class representations in an **archive**, allowing subsequent JVM startups to load them faster and share part of the metadata memory across compatible JVMs. The key point in a plugin system is: **CDS does not mean only the bootstrap loader benefits**, but the ability to archive and reuse classes loaded by custom loaders still depends on the **JDK, class loading path, archive, classpath/module path, JARs, and launch options**. There is no guarantee that every class from every loader will be archived. The Java 17+ example in the hands-on section creates a dynamic AppCDS archive and verifies it via JVM logs, including a class from a separate `URLClassLoader`.

## 1. What Costs Does CDS Address?

When starting a Java application, the JVM has to perform many steps:

1. Locate the class according to the loader and delegation model.
2. Read the `.class` file from the runtime image, directory, JAR, or another source.
3. Parse the class-file format, validate its structure, and perform linking/verification phases as required by JVM timing rules.
4. Create and manage class metadata.
5. Run initialization when required by Java semantics, create instances, and serve application logic.

CDS places certain prepared class metadata results into an archive that the JVM can **memory-map** on subsequent startups. The goal is to reduce reading/parsing/metadata-setup overhead and provide an opportunity to share eligible data pages across multiple JVM processes.

```text
Without application CDS:
   JVM start -> locate JAR/class -> parse class bytes -> metadata -> run

With valid AppCDS:
   Trial/training run -> create *.jsa archive
   Next JVM start     -> map compatible archive
                      -> use archived representation when eligible
                      -> fall back to normal loading for other classes
                      -> run
```

CDS can improve **startup time**, and can reduce **total footprint** when multiple JVMs share archived pages. It is **not** a replacement for every process's heap, does not pre-cache every Java object, and does not guarantee a specific amount of business-logic throughput improvement or peak heap reduction. Archive creation cost and actual benefits depend on the workload, filesystem, OS page cache, JVM build, and the set of loaded classes.

### "Shared class data" does not erase type identity

A runtime class is still identified by the JVM by **(binary name, defining loader)**. CDS does not merge two independent custom loaders into the same defining loader, nor does it turn two `Class<?>` instances with different loaders into the same object just because they appeared in the same `.jsa`. The JVM manages classes and checks load/archive conditions according to Java-compatible semantics.

Therefore:

- AppCDS is a **class-loading optimization**, not a mechanism that alters parent delegation order.
- It does not replace dependency isolation or namespace separation in a plugin system.
- It is not a security/sandboxing mechanism for untrusted bytecode.
- It does not turn a class already loaded from plugin-v1 into plugin-v2 just by swapping a JAR while the JVM is still running.

## 2. Distinguishing CDS, AppCDS, Default Archives, and Dynamic Archives

| Term | Meaning | Key Takeaway |
| --- | --- | --- |
| **CDS** | JVM Class Data Sharing, originally serving core runtime classes. | Many JDKs ship with a **default CDS archive**. |
| **AppCDS** | Expands the eligible class set to include application and library classes. | Can extend startup benefits beyond core classes. |
| **Default/base archive** | An archive from the JDK distribution or generated appropriately, typically `classes.jsa`. | Usually used by the JVM by default when possible. |
| **Static/custom archive** | An archive built using a classlist and `-Xshare:dump` or an appropriate tool. | Multi-step; suited for controlled build/training pipelines. |
| **Dynamic/top archive** | A supplementary archive created during a trial run, e.g., `-XX:ArchiveClassesAtExit=app.jsa`. | Can sit **on top of** the default/base archive; easy for practicing AppCDS. |
| **Newer AOT cache** | An evolution from CDS that extends caching to class loading/linking and more optimizations. | JDK 24+ introduces JEP 483; **do not conflate** AOT commands with classic CDS commands. |

According to the Oracle Java SE 25 `java` launcher docs, the JVM can use **one base archive and one dynamic archive**. In log files, the dynamic archive is often referred to as the **top** archive. If you pass only the `app.jsa` name of the dynamic archive, the archive header contains a reference to the appropriate base archive; the JVM can locate the default base.

### Default CDS

In many modern OpenJDK/Oracle JDK distributions, default CDS is enabled automatically when a valid archive is present. Common locations include:

```text
JAVA_HOME/lib/server/classes.jsa      (Linux/macOS, depending on the distribution)
JAVA_HOME/bin/server/classes.jsa      (Windows, depending on the distribution)
```

These are **illustrative paths**; you must verify the JDK you actually run. Since JDK 12, Oracle JDK typically ships with a default archive. Do not always assume a custom JDK build has a default archive or a fixed path.

`java -Xshare:auto`: uses CDS when possible; this is the default behavior in many configurations.

`java -Xshare:off`: disables CDS for baseline/control testing.

`java -Xshare:on`: requires CDS; **if the archive cannot be used, the JVM may report an error and exit**. Per the Oracle launcher docs, this is a diagnostic mode, **not an option to enforce in production**.

`-Xshare` belongs to HotSpot/OpenJDK; other JVMs may have different option names, scopes, and support.

## 3. Why Doesn't AppCDS "Cache Every Class"?

The set of classes that can use an archive is typically **the classes observed and eligible** during archive creation, subject to format, loader, and configuration constraints.

For example:

```text
Application has 20,000 class files in dependencies
Training run only uses 1,800 classes
Archive may contain a subset of those 1,800 classes (eligible ones)
Production startup:
   - matching and eligible classes can be loaded from the archive
   - other classes are loaded normally
```

These numbers are **illustrative assumptions**, not a guaranteed coverage ratio. What actually happens must be inspected through class-load and CDS logs.

A class may not be archived or reused when:

- The trial run did not trigger the code path containing that class.
- The class was defined by a custom loader or bytecode transformation that does not meet implementation requirements.
- Classpath, JAR, or module options changed, causing the JVM not to trust the old archive.
- The JVM version/build/architecture differs, or the archive header is incompatible.
- The loader in the subsequent run uses a source, identity, or delegation that does not match the archived metadata.
- The JVM cannot map the archive and falls back according to the `-Xshare` policy.
- Certain dynamically generated/hidden classes or arrays have separate support rules depending on the release.

**Do not conclude that every class printed by `-XX:DumpLoadedClassList` will definitely be restored from the archive.** The list of loaded classes, the set of eligible classes, and the set of classes actually **used from the archive** are three different groups.

## 4. Limitations by ClassLoader: Understanding Plugin Systems Accurately

Distinguish three cases:

### A. Bootstrap, platform, and application class loaders

Java runtime/core classes generally have a high chance of using the default CDS archive. With AppCDS, classes from the system/application loader and platform loader can also be eligible. This is the common path for applications packaged as JARs.

However, even with the application loader, you should not claim that **all classes** are archived. If a class did not appear in the trial run or the environment mismatches, it can still load through the normal path.

### B. Custom URLClassLoader

A **false** conclusion is that "CDS does not support user-defined class loaders at all." Oracle's CDS documentation for Java 24 states that AppCDS can serve **custom class loaders**. Dynamic archives introduced in JDK 13 improved support for this use case.

An application can do:

```java
URL jar = Path.of("plugin.jar").toUri().toURL();
try (URLClassLoader pluginLoader = new URLClassLoader(
        new URL[]{jar}, ClassLoader.getPlatformClassLoader())) {
    Class<?> plugin = Class.forName(
            "plugin.Greeter", true, pluginLoader);
}
```

The snippet requires `import java.net.URL; import java.net.URLClassLoader; import java.nio.file.Path;` and sits inside a method. It creates a dedicated plugin loader. If the code path and archive meet the conditions, a class defined by that loader **can** be stored in and reused from AppCDS.

**Verified on OpenJDK 24:** the dynamic archive from the section 8 example contains `plugin.Greeter`, and `-Xlog:class+load=info` on the subsequent run reports:

```text
plugin.Greeter source: shared objects file (top)
```

The line is abbreviated to omit timestamps/decorations, while the source string is the actual observed output. At the same time, the program returns `true` for `c.getClassLoader() == pluginLoader`. Archive reuse **does not erase the defining loader**.

### C. Custom loaders loading non-standard bytes or defining classes dynamically

A loader might read bytes from a database/network, generate bytecode via ASM, instrument individual classes, or override `loadClass` to alter delegation. In this case:

- A custom `CodeSource` is **not a guarantee** that the class is supported by CDS.
- Having the same binary name across two runs is not enough to guarantee an archive class match.
- Specific class registration/identification mechanisms and archive support tied to the implementation/JDK release may be required.
- If generated bytes depend on timestamps, randomness, or environment state, archive reuse may not be feasible.
- If some classes are not archived, the JVM typically loads them through the standard path; do not declare the entire optimization "broken" just because one class falls back.

**Practical rule:** ask via logs **"for class X, loaded by loader Y, in this run, was it loaded from the shared objects file?"**. Do not guess based on the name `URLClassLoader` or `SecureClassLoader`.

## 5. Static Archive vs. Dynamic Archive: When to Use Which?

### Class-list-based static dump

Typical Oracle Java launcher workflow:

```bash
java -Xshare:off -XX:DumpLoadedClassList=app.classlist \
     -cp app.jar demo.CdsDemo
java -Xshare:dump -XX:SharedArchiveFile=app-static.jsa \
     -XX:SharedClassListFile=app.classlist -cp app.jar
java -XX:SharedArchiveFile=app-static.jsa \
     -cp app.jar demo.CdsDemo
```

This is a **flag-illustration pattern**; you need real application, arguments, and dependencies. The main exercise in section 8 chooses **dynamic** to avoid depending on classlist contents and the static dump sequence. For static CDS, Oracle Java 25 docs require `-cp` to contain the appropriate JARs when recording the classlist and creating the archive; release-specific restrictions must be checked.

### Dynamic AppCDS

A fewer-step approach:

```bash
java -XX:ArchiveClassesAtExit=app.jsa \
     -cp app.jar demo.CdsDemo
java -XX:SharedArchiveFile=app.jsa \
     -cp app.jar demo.CdsDemo
```

On the first run, the JVM can write the top archive to `app.jsa` when the process exits normally. On the second run, the JVM maps the archive if compatible. It does not guarantee that every class loaded during the trial run will be archived successfully or that every run will get a cache hit.

**Cost:** the trial/dump run performs extra processing at shutdown, creates an archive file, and consumes I/O/disk. According to Oracle, the archived form can sometimes be **much larger** than the bytes in the JAR. Do not generate an archive on every production startup as if it were a free step.

### Can an archive be created from a running JVM?

Some JDKs support `jcmd <pid> VM.cds static_dump ...` / `dynamic_dump ...`. Dynamic dump via `jcmd` may require the JVM to be started with `-XX:+RecordDynamicDumpInfo`. Syntax and capabilities depend on the release; consult the `java`/`jcmd` docs for your exact JDK.

**Do not** treat an illustrative `jcmd` command as a recipe that works on every JDK vendor or process; the tool may require attach permissions, specific JVM flags, and certain runtime conditions.

## 6. Limitations from Classpath, Module Path, and JAR Layout

In the Oracle `java` launcher CDS/AppCDS docs, important restrictions include:

1. **Classpath/module path:** creating/reusing archives for app classes typically requires appropriate JAR sources. Non-empty class directories or exploded modules may not be supported for archive creation/reuse in certain configurations. Avoid using an IDE's `-cp out/classes` to conclude that production coverage will match a JAR.
2. **Classpath order:** for static/dynamic archives, the classpath when using the archive must satisfy compatibility rules relative to when it was created—usually **equal to or an extension of a prefix**, as documented by each JDK. Changing JAR order can cause the classpath check to fail.
3. **JAR contents:** when a JAR is modified after archive generation, the JVM may reject the archive or ignore incompatible entries. Do not unconditionally reuse an archive after deploying plugin-v2.
4. **Module path:** only certain layouts/module paths are supported; exploded modules, patched modules, upgrade module paths, and certain flags can disable CDS or archived module graph optimizations depending on the JDK.
5. **JDK build:** the archive is tied to the runtime build/architecture/format. It is **not a portable JAR** that can be built on JDK A and applied to any JDK B.
6. **Platform/JVM options:** module resolution options, heap/object layout, and flags affecting archives can alter reusability.
7. **Current working directory/relative paths:** if archive/classpath URLs were generated from relative paths, changing the working directory between the trial run and production can cause mismatches. Prefer stable deployment paths and configurations.

A common pitfall: a developer generates `app.jsa` using a local JDK 24 build, then places it in a Linux container running JDK 21. You should not expect it to work: **generate the archive with the exact JDK distribution/build/architecture of the target environment**, or have the production build pipeline generate the archive.

**Emphasis:** restrictions differ across JDK 17, 21, 24, 25, and 26; consult the docs matching your version. Do not turn a static-dump restriction into a claim that "no classes from a directory use default CDS," because the default archive can still load core classes even when app classes are ineligible.

## 7. Module Options and Archives: Why Changing Flags Can Lose Benefits

For modular applications, not only `-cp`, but `--module-path` and options such as `--module`, `--add-modules`, and `--enable-native-access` can affect archive matching. Oracle Java 25 docs require several module-related options to have identical values between archive creation and archive use for full optimization.

For example:

```bash
java --module-path libs -m m.app/com.example.Main \
     -XX:ArchiveClassesAtExit=module-app.jsa

java --module-path libs -m m.app/com.example.Main \
     -XX:SharedArchiveFile=module-app.jsa
```

This is a **configuration pattern**, not a runnable program, because real modular artifacts are required. If the trial run uses `--add-modules m.analytics` while production uses `--add-modules m.reporting`, the JVM may **not use the archived full module graph** or may drop optimizations depending on class/linking data.

Some flags such as `--upgrade-module-path`, `--patch-module`, and `--limit-modules` can disable CDS according to Oracle docs. Do not assume a build-time or test configuration running with `--patch-module` will still allow archive reuse in production.

### Custom ModuleLayer

Class loaders created by `ModuleLayer.defineModulesWithOneLoader`/`defineModulesWithManyLoaders` have their own module configurations and mappings. AppCDS can optimize some classes depending on how the JVM records them, but **it does not promise that all classes in every layer will be archived**.

Ask:

- Was module `X` resolved during the training run?
- Was class `Y` loaded through the same loader/module path as during archive creation?
- In production, do the configuration, loader identity, and URLs still match?
- Does the class appear in `-Xlog:class+load` as coming from the shared archive or from a file/module image?

Do not use `--add-reads`/`--add-exports`/`--add-opens` as a way to "enable AppCDS"; they adjust the JPMS access graph, not archive creation.

## 8. Complete Java 17+ Hands-On: app.jar + plugin.jar + URLClassLoader

This experiment creates an application `demo.CdsDemo` in `app.jar` and a plugin `plugin.Greeter` in `plugin.jar`. `CdsDemo` uses a `URLClassLoader` with the platform loader as its parent to define the plugin class. By using `-XX:ArchiveClassesAtExit` and then `-XX:SharedArchiveFile`, we inspect **JVM logs** to determine whether classes come from archived data.

### Directory structure

```text
src/
  demo/CdsDemo.java
  plugin/Greeter.java
classes/
  app/            (generated by javac)
  plugin/         (generated by javac)
app.jar           (generated by jar)
plugin.jar        (generated by jar)
app.jsa           (generated by the dump run)
```

**File `src/demo/CdsDemo.java`:**

```java
package demo;

import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public class CdsDemo {
    public static void main(String[] args) throws Exception {
        System.out.println("main class: "
                + CdsDemo.class.getName());
        System.out.println("main system loader: "
                + (CdsDemo.class.getClassLoader()
                    == ClassLoader.getSystemClassLoader()));

        URL pluginUrl = Path.of("plugin.jar")
                .toAbsolutePath().toUri().toURL();

        try (URLClassLoader loader = new URLClassLoader(
                new URL[]{pluginUrl},
                ClassLoader.getPlatformClassLoader())) {

            Class<?> c = Class.forName(
                    "plugin.Greeter", true, loader);

            System.out.println("plugin defining loader: "
                    + (c.getClassLoader() == loader));
            System.out.println("plugin message: "
                    + c.getMethod("greet").invoke(null));
        }
    }
}
```

**File `src/plugin/Greeter.java`:**

```java
package plugin;

public class Greeter {
    public static String greet() {
        return "hello-appcds";
    }
}
```

### Compile with JDK 17+ and package JARs

From the root directory containing `src`:

```bash
javac --release 17 -d classes/app src/demo/CdsDemo.java
javac --release 17 -d classes/plugin src/plugin/Greeter.java
jar --create --file app.jar -C classes/app .
jar --create --file plugin.jar -C classes/plugin .
```

Note that `plugin.jar` **is not added to the application classpath**: only `-cp app.jar` is used in subsequent steps. The plugin is located via a dedicated `URLClassLoader`, allowing us to properly test the custom defining loader case.

### Baseline run

```bash
java -cp app.jar demo.CdsDemo
```

**Exact stdout on OpenJDK 24.0.2 (the same JVM build used in the following runs):**

```text
main class: demo.CdsDemo
main system loader: true
plugin defining loader: true
plugin message: hello-appcds
```

### Create the dynamic AppCDS archive

```bash
java -XX:ArchiveClassesAtExit=app.jsa \
     -cp app.jar demo.CdsDemo
```

The command above uses Bash line continuation; in PowerShell, run it on **one line**:

```powershell
java -XX:ArchiveClassesAtExit=app.jsa -cp app.jar demo.CdsDemo
```

After the run, `app.jsa` appears when the JVM supports/meets the conditions and archive creation succeeds. **The experiment on OpenJDK 24.0.2 created `app.jsa` successfully**, and the program still printed the four baseline lines.

### Use the archive and inspect CDS logs

```bash
java -Xlog:cds=info -XX:SharedArchiveFile=app.jsa \
     -cp app.jar demo.CdsDemo
```

On the test run, the log included these signals:

```text
[info][cds] Opened archive ...classes.jsa.
[info][cds] Opened archive app.jsa.
```

This is an **abbreviated excerpt omitting timestamps and exact paths**, not the full fixed stdout/stderr. Both base and top archives were opened; the program still returned the same four lines as the baseline.

### Prove that classes were used from the archive

```bash
java -Xlog:class+load=info \
     -XX:SharedArchiveFile=app.jsa \
     -cp app.jar demo.CdsDemo
```

In the OpenJDK 24 test, the two log entries shorten to:

```text
demo.CdsDemo source: shared objects file (top)
plugin.Greeter source: shared objects file (top)
```

**This is the concrete class-level evidence**, rather than merely seeing that `app.jsa` exists. In particular, `plugin.Greeter` is a class defined by a **custom `URLClassLoader`** (as confirmed by stdout).

### Control run with CDS disabled

```bash
java -Xshare:off -Xlog:class+load=info \
     -cp app.jar demo.CdsDemo
```

With the same artifacts in the test, the class-load logs switched back to the JAR sources:

```text
demo.CdsDemo source: file:/.../app.jar
plugin.Greeter source: file:/.../plugin.jar
```

The paths are **excerpts with absolute paths omitted**; do not treat these two lines as complete stdout. Both runs printed the same functional output: the program works correctly with or without the archive.

### Technical explanation

1. `app.jar` contains the main class and goes through the **system loader**.
2. `plugin.jar` is only in the `URLClassLoader` created by the program, not on `-cp`.
3. During the trial run, the plugin class is loaded, giving the JVM an opportunity to record it for archiving.
4. On the next run with the same JDK/JARs/configuration, eligible classes can be found in the top archive; the test shows both `demo.CdsDemo` and `plugin.Greeter` reported as `shared objects file (top)`.
5. `plugin defining loader: true` remains true: CDS does not turn the plugin class into a system-loader class.
6. `-Xshare:off` serves as a control confirming Java still works when the archive is not involved, and the JVM reads the class from JAR bytes.

**Environment-dependent results:** JDK 24.0.2 was tested. With a different JDK, a different custom loader, or an archive mismatch, `plugin.Greeter` might fall back or be ineligible. Check the logs of **your own JVM and deployment**, rather than copying logs from this article as assumptions.

## 9. Reading Class-Load Logs and CDS Diagnostics Correctly

Common HotSpot options:

```text
-Xlog:cds=info
-Xlog:class+load=info
-Xlog:class+load=debug
-Xshare:off
-Xshare:auto
-Xshare:on
```

Meanings:

- `-Xlog:cds=info`: were any archives opened, and are there basic mapping/configuration details or issues?
- `-Xlog:class+load=info`: reports the **specific** source of each class, such as `shared objects file`, `shared objects file (top)`, `file:/...jar`, or the runtime image source.
- `-Xlog:class+load=debug`: provides extra diagnostic information, though logs are verbose and version-specific.
- `-Xshare:off`: control option to disable CDS.
- `-Xshare:on`: useful for catching mismatches in testing because it can fail startup; **avoid enforcing in production**.

**Do not treat `source: shared objects file` for `java.lang.String` as proof that AppCDS succeeded for your plugin.** That may just be the **default base archive**; you need to look for your exact plugin class name and check for `(top)` or the appropriate source.

A practical filter:

```bash
java -Xlog:class+load=info -XX:SharedArchiveFile=app.jsa \
     -cp app.jar demo.CdsDemo 2>&1 |
     grep -E 'demo.CdsDemo|plugin.Greeter'
```

The `grep` command uses Bash/Linux/macOS syntax; on PowerShell, you can replace it with `Select-String 'demo.CdsDemo|plugin.Greeter'`. Because `-Xlog` prints many classes, filtering helps identify the exact loader and source. When running this command in production, logging can affect performance/I/O and expose deployment paths.

### What NOT to infer from logs

- A class loading from an archive does not prove the **entire application** is faster in production.
- A `shared objects file` log does not tell you the exact byte/RSS savings per class.
- Having `app.jsa` does not prove all classes load from the top archive.
- Having many unarchived classes does not automatically mean CDS is useless overall; default JDK classes may still benefit.
- `CodeSource.location` reflects the loader's provenance metadata, whereas the class-load log reflects the JVM source for that load, and archive usage is another layer of information. Read them together rather than conflating the two concepts.

## 10. Common Configuration Mistakes with Plugin Frameworks

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| `app.jsa` exists, yet plugin class still shows `source: file:/...plugin.jar` | Plugin class was not archived, loader is ineligible, config mismatches, or archive was not selected. | Inspect training path, class-loader behavior, and dump/use logs. |
| `app.jsa` is not created | Trial run did not exit cleanly, invalid archive path/write permissions, no compatible base, or conflicting JDK flags. | Check stderr/exit code, verify base archive and permissions. |
| Archive stops working after a JDK update | JDK build/format mismatch. | Regenerate the archive using the new JDK runtime. |
| `plugin.jar` updated while still using the old archive | Artifact/path/checksum no longer matches; the JVM may reject or skip archived entries. | Version the archive alongside the image/artifacts; regenerate the archive. |
| App tested fine with IDE `-cp out/classes`, but AppCDS shows little effect | Directory layout differs from production JAR/config, and archived app classes have restrictions. | Train from packaged artifacts matching production. |
| `-Xshare:on` prevents service from starting | CDS archive is unusable, and `on` mode requires it. | Do not use `on` in prod; investigate mismatch, use `auto`. |
| Static classlist is large, but archive lacks custom loader classes | Different eligibility/loader/classlist constraints. | Try dynamic archives and check logs; do not assume all loaders are supported. |
| Parent-first loads plugin API from host instead of plugin JAR | Different loader than expected; archive is not the direct cause. | Check defining loader and delegation. |
| CDS disabled, yet startup is still slow | Bottleneck is I/O, DI container, reflection, network, DB, JIT warmup, or app init. | Profile startup, separating parse/link time from application init. |
| Multiple archive files consume disk space | AppCDS stores metadata representations, which can be larger than class bytes. | Select high-value class sets and clean up archives by version. |
| Using `--patch-module` when dumping an archive | Certain JVM/module options disable CDS. | Read restrictions for the exact JDK; remove incompatible flags in the pipeline. |

A custom `ClassLoader` **should not override delegation or `defineClass` just to force class archiving**; doing so can break class identity, package sealing, source verification, or plugin logic. Test the JVM's existing CDS behavior first, then optimize using mechanisms supported by the JDK/framework.

## 11. Measuring CDS/AppCDS Effectiveness Meaningfully

To know whether AppCDS is worth deploying, measure three configurations using the **exact same artifacts and JDK build**:

A. **Without CDS:** `-Xshare:off`.

B. **Default CDS:** omit `-XX:SharedArchiveFile`, letting the JVM use the default base archive if available.

C. **AppCDS:** `-XX:SharedArchiveFile=app.jsa` with an archive generated from a suitable trial run.

Measurement targets:

| Metric | Why It Matters | Suggested Measurement Method |
| --- | --- | --- |
| Startup latency (p50/p95) | AppCDS typically improves cold-start phases. | Ready-to-serve timestamp across multiple independent runs. |
| Time-to-first-request | Closer to user needs than total `main` duration. | Hit a health/readiness endpoint and measure end-to-end. |
| RSS/PSS across multiple JVM processes | Shows shared-page benefits on the same host. | OS memory tools; avoid just summing heap sizes. |
| Heap/metaspace memory | Analyzes different memory pressures. | JFR/jcmd/metrics, understanding CDS metadata is mmapped outside the heap. |
| Archive size | Disk cost and deployment/cache management. | Size of `.jsa` and artifact images. |
| Number of actual archived class loads | Evaluates coverage rather than guessing. | `-Xlog:class+load=info` filtered by name. |

**Do not claim unmeasured percentage improvements.** An app that mostly waits on network or database calls may see minimal benefit even if hundreds of core classes are shared. A frequently invoked CLI tool may see significant gains.

### Simple benchmark procedure

1. Use the same host, JDK build, key JVM flags, artifacts, and environment.
2. Separate **archive generation** cost from production startup measurements.
3. Run enough iterations (e.g., a few dozen runs) for A/B/C; alternate order to reduce page-cache/thermal bias.
4. If cold-cache behavior is needed, describe the OS page cache state accurately—do not label every run after the first as "cold."
5. Do not enable `-Xlog:class+load` during standard latency benchmarks if logging adds I/O/overhead; use logs in a separate archive-coverage verification pass.
6. Report sample count, JDK version, archive/JAR hashes, median/p95, and variance/spread.
7. Measure multiple JVM processes concurrently if shared footprint is the goal; a single JVM does not reflect cross-process savings.

Example commands for each configuration (measured with external tools like `time`, `Measure-Command`, or telemetry):

```bash
java -Xshare:off -cp app.jar demo.CdsDemo
java -cp app.jar demo.CdsDemo
java -XX:SharedArchiveFile=app.jsa -cp app.jar demo.CdsDemo
```

These commands **do not compute benchmark statistics on their own**. Section 8 only verifies functionality and archive source, not speed.

## 12. AppCDS in Plugin Hot Reload: Archives and Lifecycle

In a reloadable plugin system:

```text
Host process
   |
   +-- PluginLoader v1 -> plugin.jar v1
   |        (used in the AppCDS trial run)
   |
   +-- PluginLoader v2 -> plugin.jar v2
            (different artifact/bytes; cannot assume v1 archive reuse)
```

A CDS cache **does not** guarantee that plugin v2 is compatible with v1's archived representation. When versions change, treat the archive as an **artifact tied to the deployment/JDK image lifecycle**, not a permanent database valid for every plugin revision.

Also distinguish:

- **Closing a loader**: `URLClassLoader.close()` releases the loader's file/JAR handles per the API; it does not force immediate class unloading.
- **Reduced load work via archive**: some class metadata can be restored quickly at JVM startup or class loading, yet classes still obey defining-loader identity.
- **Hot reload within the same process**: can use a new loader generation; archive reuse for one generation does not mean the runtime replaces old-generation class objects.
- **GC/unloading**: depends on reachability of the loader, threads, TCCL, `ThreadLocal`, and host static caches; AppCDS does not fix lifecycle leaks.
- **Security**: archives do not sandbox plugins; untrusted bytecode still requires proper boundaries.

A sound operational approach: pin JDK/JAR/plugin-set versions, generate the archive as part of a **versioned deployment image**, verify logs on startup, regenerate the archive when builds/JARs change, and keep a non-CDS fallback if the environment is unsuitable.

## 13. CDS vs. JDK 24+ AOT Cache: Do Not Conflate Them

Starting in **JDK 24**, JEP 483 introduces *Ahead-of-Time Class Loading & Linking*: an advance over traditional CDS that allows caching class loading/linking states built during a training run for subsequent JVM startups. JDK 25 continues adding improvements to creating and using AOT caches (JEP 514, 515).

**Key differences to learn:**

| Traditional CDS/AppCDS | Modern AOT Cache |
| --- | --- |
| Focuses on storing archived class data/metadata for faster loading. | Can additionally store class loading/linking state and extended optimizations. |
| Commonly uses `.jsa` with `-XX:ArchiveClassesAtExit` and `-XX:SharedArchiveFile`. | Uses `-XX:AOT...` workflows/flags, varying by JDK release. |
| Long-standing foundation compatible across many JDK 17+ releases. | JDK 24+ with evolving syntax; do not copy JDK 25 commands into JDK 17. |
| Does not merge loader identities into one shared namespace. | Must also preserve class/module semantics. |

Do not mistake "JDK 24+ recommends AOT cache for startup" for "CDS no longer works." The section 8 experiment on OpenJDK 24 shows **dynamic CDS still runs**. When choosing a production solution, consult the actual JDK and framework documentation, and compare profiling data and operational overhead.

Sources: [JEP 483](https://openjdk.org/jeps/483), [Oracle Java SE 25 java launcher](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html), and [JEP 514](https://openjdk.org/jeps/514).

## 14. Common Misconceptions to Avoid

1. **"CDS only helps bootstrap classes."** Not true in general. AppCDS can support application, platform, and custom-loader classes depending on eligibility; the section 8 test confirms a custom `URLClassLoader` on JDK 24.
2. **"Having a JAR on the classpath means it is archived."** No. Classes must be loaded during the trial run and meet archive requirements.
3. **"AppCDS turns classes from loader A and loader B into the same Class object."** No. The defining loader remains part of class identity.
4. **"`getURLs()` proves a class was used from the archive."** No. It shows the URL search configuration; to verify archive usage, check JVM load logs.
5. **"The existence of `app.jsa` means AppCDS is active."** No. There can be a mismatch and fallback; check `-Xlog:cds` + `-Xlog:class+load`.
6. **"An archive from a different JDK build will still work."** Do not assume so; archives are tied to the JVM distribution/build/architecture and are not portable like JARs.
7. **"An archive from app v1 must help plugin v2."** Not guaranteed; changing JARs/bytes/classpath can invalidate archived class reuse.
8. **"`-Xshare:on` is a production best practice."** No; Oracle describes it as a testing option that can abort startup if the archive is unusable.
9. **"An archive with thousands of classes guarantees startup is faster by a fixed percentage."** No; you must benchmark your real workload.
10. **"CDS shares the entire Java heap across multiple processes."** No; JVM processes still have separate heaps/states, and only a portion of archived metadata memory can be shared.
11. **"No plugin classes were archived, so we should drop all class-loader abstractions."** No; plugin loaders solve correctness/lifecycle problems, whereas CDS is a best-effort optimization.
12. **"Using `-Xshare:off` will break app logic."** An application should never rely on CDS for functional correctness; if behavior differs, that signals a compatibility issue or bug to investigate.

## 15. Review Questions

1. **What does CDS primarily improve?** Startup/class-loading metadata and memory footprint across certain JVMs; not all runtime CPU operations.
2. **What does AppCDS add to CDS?** The ability to archive application and library classes beyond core runtime classes.
3. **How does a default base archive differ from a top/dynamic archive?** The base archive usually ships with the JDK; the top archive holds additional classes recorded after a training run.
4. **Can a custom `URLClassLoader` use archived classes?** Yes, under suitable conditions, depending on the JDK and eligibility; the OpenJDK 24 example verified this.
5. **What does `source: shared objects file (top)` mean for a class?** The JVM reports that the class was loaded from the top/dynamic shared archive during that load.
6. **Does `CodeSource.location == file:/...plugin.jar` prove a CDS hit?** No. It is artifact provenance metadata, not the class-load archive source.
7. **Why should a training run exercise multiple features?** Only classes loaded and eligible during the trial run have a chance of being archived.
8. **What happens if a JAR changes after archive creation?** Archive compatibility may be lost; regenerate it with the matching artifacts and JDK.
9. **How does `-Xshare:on` differ from `-Xshare:auto`?** `on` requires archive usage and can fail startup, while `auto` uses it when possible.
10. **Why is `-Xshare:off` useful?** As a control with CDS disabled to observe class-file loads and measure differences.
11. **Why avoid forcing non-empty directories on the classpath in a dump pipeline?** CDS/AppCDS restrictions vary by JVM release and layout; use JARs matching production and verify the docs.
12. **Does CDS fix TCCL/`ThreadLocal` leaks holding a custom loader?** No; that is a lifecycle and reference-management issue.
13. **If `String` is loaded from `shared objects file`, does that prove the app plugin is archived?** No; that may come from the default base archive.
14. **When should you consider the newer AOT cache?** On JDK 24+ when your framework/JVM supports it and measurements show a benefit; do not mix options across versions.

## 16. Official References

- [Oracle Java SE 25 — java command: Application Class Data Sharing](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): `-Xshare`, `-XX:ArchiveClassesAtExit`, `-XX:SharedArchiveFile`, static/dynamic archives, classpath/module restrictions, and AOT.
- [Oracle Java SE 24 — Class Data Sharing](https://docs.oracle.com/en/java/javase/24/vm/class-data-sharing.html): CDS/AppCDS, default archives, startup/footprint goals, and class loaders.
- [Oracle Java SE 17 — java command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): options for the Java 17 baseline.
- [dev.java — CDS and AppCDS in HotSpot](https://dev.java/learn/jvm/cps-appcds/): creating static/dynamic archives and practical limitations.
- [OpenJDK JEP 310 — Application Class-Data Sharing](https://openjdk.org/jeps/310): history of AppCDS.
- [OpenJDK JEP 350 — Dynamic CDS Archives](https://openjdk.org/jeps/350): dynamic archives and custom loader support.
- [OpenJDK JEP 483 — Ahead-of-Time Class Loading & Linking](https://openjdk.org/jeps/483): JDK 24 AOT cache.
- [OpenJDK JEP 514 — Ahead-of-Time Command-Line Ergonomics](https://openjdk.org/jeps/514): JDK 25 AOT cache creation improvements.
- [Java SE 21 — ClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): runtime class identity, defining loader, and delegation.
- [Java SE 21 — URLClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URLClassLoader.html): URL/JAR lookup, `getURLs()`, and close behavior.
