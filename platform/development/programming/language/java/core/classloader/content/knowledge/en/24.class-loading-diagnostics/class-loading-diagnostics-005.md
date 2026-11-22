# Diagnosing class loading with -verbose:class and -Xlog:class+load in Java 17

## 1. Why observe class loading?

When encountering `ClassNotFoundException`, `NoClassDefFoundError`, `ClassCastException`, `NoSuchMethodError`, `LinkageError`, or a plugin using the wrong library version, the key question is usually not “is the `.class` file somewhere on the machine?”, but rather:

1. **Which class binary name did the runtime actually load/define?**
2. **From which source was that class obtained** — JDK runtime image, application classpath, JAR, or plugin directory?
3. **Which class loader owns the definition**, and is it the loader the application expects?
4. **When was the class loaded**, when was the class initialized, and at which step did the error occur?
5. Does a second `loadClass` call **reuse the existing `Class<?>`** or define a new class by a different loader?

Java 17 has two basic diagnostic approaches:

```bash
java -verbose:class -cp out/host TraceLoadDemo
```

and:

```bash
java -Xlog:class+load=info -cp out/host TraceLoadDemo
```

In HotSpot/JDK 17, the second approach uses **Unified JVM Logging** with the `class+load` tag set. It lets you select log levels, output destinations, decorators, file rotation, and many other tags. The first approach is a traditional option still supported for convenient quick checks.

**One detail to keep in mind:** The Oracle JDK 17 `java` command documentation maps `-verbose:class` as equivalent to:

```text
-Xlog:class+load=info,class+unload=info
```

Therefore, if you only use `-Xlog:class+load=info`, you have selected **load events** and **have not automatically requested unload events**. Even though both approaches produce many similar lines, they should not be called strictly synonymous option strings.

## 2. Understanding the semantics: loading, linking, initialization, unloading

A runtime class can go through different phases:

```text
Class name / lookup request
          |
          v
       LOADING
  Find/define class
          |
          v
       LINKING
  Verify -> Prepare -> Resolve
  (resolution may be performed at appropriate times)
          |
          v
   INITIALIZATION
  <clinit> and static initialization
          |
          v
  Execute constructor/method as needed
          |
          v
  May UNLOAD when defining loader is eligible for GC
  and the JVM actually chooses unloading
```

**The `class+load` log observes the class loading process**, not initialization specifically. A class may have been loaded earlier while `static { ... }` has not yet run.

Example:

```java
Class<?> token = Class.forName(
        "demo.trace.PluginMarker", false, pluginLoader);
```

The three-parameter overload `Class.forName(name, initialize, loader)` with `false` **does not request initialization**. A `class+load` log entry may appear for `PluginMarker` while its static initializer has not run yet. When the static method is later invoked via reflection, the class may be initialized.

Also, do not equate **unloading** with an object instance going out of scope. According to JLS 12.7, a class can only be unloaded when its **defining loader** becomes eligible to be collected by the garbage collector; the JVM does not guarantee that a class will unload during a particular GC cycle. The absence of a `class+unload` log in a short demo **does not prove a memory leak**.

## 3. What does -verbose:class tell you?

The option:

```bash
java -verbose:class -cp out/host TraceLoadDemo
```

instructs the Java runtime to output class loading information via the verbose mechanism. On HotSpot/JDK 17, the actual output may use the Unified Logging format; for example, a line looks roughly like:

```text
[0.123s][info][class,load] demo.trace.PluginMarker source: file:/path/to/out/plugin/
```

**This is an example log format**, not a fixed timestamp, path, or stdout. Timing, paths, supporting log lines, decorators, module source, class loading policy, and the number of loaded classes vary by JDK, OS, and how it is run.

`-verbose:class` is useful when:

- You need to quickly check whether a binary name appears in the load log.
- You need a basic view of the class source when diagnosing duplicate JARs on the classpath.
- You want a familiar option and do not yet need file/rotation configuration.
- You need to rerun a small test and read all load/unload events.

**Limitation:** It typically generates a large amount of output from JDK classes and framework libraries. For production, you should filter by class name and use Unified Logging to limit the output.

### Can -verbose:class be used to identify the exact loader object?

**Do not assume so by default.** A `class,load` line at the `info` level typically includes the class name and source, but it may not display all identity/parent/loader object information that the application needs. The same URL or the same binary name does not necessarily mean the same defining loader.

In code, verify independently:

```java
ClassLoader actualDefiner = token.getClassLoader();
System.out.println(token.getName());
System.out.println(actualDefiner);
```

The snippet above requires the variable `token` to be of type `Class<?>`. If you need to establish identity, compare `tokenA == tokenB` and `token.getClassLoader() == expectedLoader`; do not just compare class names or loader names.

## 4. Unified Logging: overview of -Xlog syntax

JVM Unified Logging (JEP 158) allows configuring:

```text
-Xlog:<what>:<output>:<decorators>:<output-options>
```

Components:

| Component | Role | Example |
|---|---|---|
| `what` | Tag selector and log level | `class+load=info` |
| `output` | Sends logs to stdout/stderr or a file | `stdout`, `stderr`, `file=classload.log` |
| `decorators` | Information attached to each line | `uptime,level,tags` |
| `output-options` | Output/rotation configuration | `filecount=3,filesize=10M` |

Common usage pattern:

```bash
java -Xlog:class+load=info -cp out/host TraceLoadDemo
```

Equivalent to an explicit representation of the output:

```bash
java -Xlog:class+load=info:stdout:uptime,level,tags -cp out/host TraceLoadDemo
```

With `-Xlog`, the default output is `stdout`, and the default decorators typically include uptime, level, and tags.

Check the tags/levels/decorators that your own JVM supports:

```bash
java -Xlog:help
```

**Do not guess which tags exist across every vendor/version**. Unified Logging belongs to the HotSpot/JDK implementation and the `java` command documentation; actual display output may differ across Java distributions.

### Log levels

The main levels: `off`, `error`, `warning`, `info`, `debug`, and `trace`. The more detailed the level, typically the more lines are produced and the higher the logging overhead.

```bash
java -Xlog:class+load=info -cp out/host TraceLoadDemo
java -Xlog:class+load=debug -cp out/host TraceLoadDemo
```

According to the Oracle JDK 17 documentation, `info` is used for regular class loading; `debug` provides additional information depending on the log site. There is no guarantee that every class has exactly one `debug` line or that the `debug` format remains unchanged across JDK updates.

### A tag set is not an arbitrary logical plus

In Unified Logging, `class+load` represents a **tag set** attached to a log event. Without a wildcard, a selector normally matches the exact tag set defined for the event.

```text
class+load=info       -> selects the class+load tag set at info
class+unload=info     -> selects the class+unload tag set at info
class*=debug          -> selects tag sets containing class via wildcard
```

`class*=debug` is a broader approach; it can produce many other class-related logs. When learning or diagnosing a specific error, start with `class+load=info`, then expand once you determine which additional event types you need.

## 5. Key options to remember on JDK 17

| Option | Primary observation | Use case |
|---|---|---|
| `-verbose:class` | Legacy verbose class information; on HotSpot JDK 17 equivalent to load + unload info | Quick checks |
| `-Xlog:class+load=info` | Class loading events | Identify which class/source is loaded |
| `-Xlog:class+load=debug` | More detailed loading when log sites have data | Deep investigation |
| `-Xlog:class+load=info,class+unload=info` | Load and unload | Observe class loader lifecycle |
| `-Xlog:class+unload=info` | Unload events that actually occur | Hot reload/metaspace; does not replace GC roots analysis |
| `-Xlog:class+resolve=debug` | Constant-pool class/member resolution | Linkage or resolution errors |
| `-Xlog:class+init=info` | Class initialization log | Distinguish loading from static initialization |
| `-Xlog:class+loader+constraints=info` | Recorded loading constraints | Suspected linkage across loaders |
| `-Xlog:class+path=info` | Class path details | Suspected wrong classpath |
| `-Xlog:class+preorder=debug` | Load/reference preorder diagnostics | Trace references before class load |
| `-Xlog:help` | Options/tags supported by the JVM | Check the runtime before applying |

The mappings for `TraceClassLoading`, `TraceClassResolution`, `TraceClassInitialization`, and `TraceLoaderConstraints` are described in the Java 17 documentation via Unified Logging. Do not blindly copy `-XX:+TraceClassLoading` flags from very old JDK tutorials: those legacy flags may have been removed and prevent the JVM from starting. Choose the corresponding `-Xlog` option.

## 6. Complete Java 17 example: loading a plugin class and reusing the same Class<?>

This example intentionally places `demo.trace.PluginMarker` **outside the application classpath** and supplies it separately to a `URLClassLoader`. When run, we see one load event for the plugin class, yet two lookup requests still return **the same `Class<?>`**.

### 6.1. Project tree

```text
src/
  plugin/
    demo/
      trace/
        PluginMarker.java
  host/
    TraceLoadDemo.java

out/
  plugin/
  host/
```

`out` does not need to exist yet; `javac -d` will create the output packages, while the shell commands below create the root directories.

### 6.2. PluginMarker.java

Create the file `src/plugin/demo/trace/PluginMarker.java`:

```java
package demo.trace;

public final class PluginMarker {
    static {
        System.out.println("PLUGIN_INITIALIZED");
    }

    public static String run() {
        return "PLUGIN_OK";
    }
}
```

The static initializer is an **initialization** marker, distinct from the time the class is loaded. The class has a public method for the host to invoke via reflection.

### 6.3. TraceLoadDemo.java

Create the file `src/host/TraceLoadDemo.java`:

```java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class TraceLoadDemo {
    public static void main(String[] args) throws Exception {
        System.out.println("BEGIN_USER_LOOKUP");

        URL pluginRoot = Path.of("out/plugin").toUri().toURL();
        ClassLoader hostLoader =
                TraceLoadDemo.class.getClassLoader();

        try (URLClassLoader pluginLoader = new URLClassLoader(
                "demo-plugin",
                new URL[] {pluginRoot},
                hostLoader)) {

            Class<?> first = Class.forName(
                    "demo.trace.PluginMarker", false, pluginLoader);
            Class<?> second =
                    pluginLoader.loadClass("demo.trace.PluginMarker");

            System.out.println("SAME_CLASS=" + (first == second));
            System.out.println("DEFINED_BY_PLUGIN="
                    + (first.getClassLoader() == pluginLoader));

            System.out.println("BEFORE_STATIC_CALL");
            Object value = first.getMethod("run").invoke(null);
            System.out.println("RESULT=" + value);
        }

        System.out.println("END_USER_LOOKUP");
    }
}
```

Here:

1. `hostLoader` only has the host class; it does not have `demo.trace.PluginMarker`.
2. `pluginLoader` uses parent-first delegation, but the parent does not see the plugin class, so `URLClassLoader` searches for the file under `out/plugin`.
3. `Class.forName(name, false, pluginLoader)` requests loading but **does not request initialization**.
4. `pluginLoader.loadClass(name)` returns the class already recorded through that loader; it does not redefine a class with the same binary name.
5. `first.getClassLoader() == pluginLoader` proves the defining loader of the plugin class.
6. Invoking static `run` via reflection triggers initialization if the class is not yet initialized. Therefore `PLUGIN_INITIALIZED` appears after `BEFORE_STATIC_CALL`.
7. `URLClassLoader.close()`, via try-with-resources, releases the loader's resources; it **does not mean** the class unloads immediately upon exiting the try block.

### 6.4. Compiling and running without JVM logging enabled

Bash (Linux/macOS):

```bash
mkdir -p out/plugin out/host
javac -d out/plugin src/plugin/demo/trace/PluginMarker.java
javac -d out/host src/host/TraceLoadDemo.java
java -cp out/host TraceLoadDemo
```

Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force out/plugin,out/host
javac -d out/plugin src/plugin/demo/trace/PluginMarker.java
javac -d out/host src/host/TraceLoadDemo.java
java -cp out/host TraceLoadDemo
```

**Do not add `out/plugin` to `-cp`!** If the parent classpath sees PluginMarker, a parent-first `URLClassLoader` can obtain the class from the parent, turning `DEFINED_BY_PLUGIN` into `false` and defeating the purpose of the test.

**Deterministic** stdout on a clean run with the structure above:

```text
BEGIN_USER_LOOKUP
SAME_CLASS=true
DEFINED_BY_PLUGIN=true
BEFORE_STATIC_CALL
PLUGIN_INITIALIZED
RESULT=PLUGIN_OK
END_USER_LOOKUP
```

These markers are used for reading the logs. When JVM logging is enabled, log lines may interleave between markers, but **the logical order of the markers printed by the program remains correct**.

### 6.5. Enabling -verbose:class

```bash
java -verbose:class -cp out/host TraceLoadDemo
```

When filtering the logs, search for the name:

```text
demo.trace.PluginMarker
```

A similar `class,load` line (for shape illustration only):

```text
[0.080s][info][class,load] demo.trace.PluginMarker source: file:/.../out/plugin/
```

Afterward, near the reflection call, `PLUGIN_INITIALIZED` appears on stdout; if `class+init` is also enabled, a separate initialization log can be observed. Do not infer “the class is initialized” solely from a class-load log.

### 6.6. Enabling class+load alone

```bash
java -Xlog:class+load=info -cp out/host TraceLoadDemo
```

Focus on:

- `TraceLoadDemo` is loaded from `out/host` or the corresponding classpath source.
- `demo.trace.PluginMarker` is loaded from `out/plugin`.
- The runtime also loads many JDK classes and libraries needed to run. Do not mistake those lines for plugin classes.

**There is no guarantee that each `loadClass` call will print a new load log.** The two lookups in the demo return the same runtime `Class<?>`, so they are not two independent class definitions.

### 6.7. Writing logs to a file instead of mixing with application stdout

On JDK 17 HotSpot:

```bash
java -Xlog:class+load=info:file=classload.log:uptime,level,tags \
     -cp out/host TraceLoadDemo
```

In PowerShell:

```powershell
java -Xlog:class+load=info:file=classload.log:uptime,level,tags -cp out/host TraceLoadDemo
```

Then **application stdout** remains the seven fixed lines from section 6.4, while JVM class-load logs are written to `classload.log` in the working directory.

Filter on Linux/macOS:

```bash
grep -F 'demo.trace.PluginMarker' classload.log
```

Or PowerShell:

```powershell
Select-String -Path classload.log -Pattern 'demo.trace.PluginMarker'
```

A matching class-load record proves that the JVM recorded a loading event for that class name during the observed run; do not rely solely on this line to conclude class loader identity or authorization.

## 7. How to read a Unified Logging line

A log line has the form:

```text
[0.147s][info][class,load] demo.trace.PluginMarker source: file:/.../out/plugin/
```

Components:

| Component | Explanation |
|---|---|
| `[0.147s]` | Uptime at the time of the event, **not the elapsed time of that load operation** |
| `[info]` | Log level |
| `[class,load]` | Tag set |
| `demo.trace.PluginMarker` | Binary name displayed in the record |
| `source: ...` | Source of bytes/module/path according to JVM logging |

**Uptime is not class loading duration.** The difference between two timestamps may also include other work, JIT, I/O, or scheduling; that interval should not be used as a microbenchmark of `ClassLoader.loadClass` time.

**Source is not a trust certificate.** `file:/.../plugin.jar` indicates the class source reported by the JVM; it does not prove that the JAR has been hashed/signed or is authorized to execute. If you need to check provenance, a separate artifact verification mechanism is required.

**The source is not necessarily a file path.** Many JDK classes come from the `jrt:/` runtime image or a `shared objects file` depending on CDS/JVM. Dynamic/generated classes may not have a conventional source file.

## 8. Separating class loading from initialization with two kinds of traces

A common misconception: “I saw the class-load log when `Class.forName(name, false, loader)` ran, so the static initializer has already executed.”

Incorrect. In the example:

```text
BEGIN_USER_LOOKUP
[class,load] demo.trace.PluginMarker ...   <-- loading event
SAME_CLASS=true
DEFINED_BY_PLUGIN=true
BEFORE_STATIC_CALL
PLUGIN_INITIALIZED                      <-- static initialization of the class
RESULT=PLUGIN_OK
END_USER_LOOKUP
```

The interleaved diagram above is **illustrative**, not the full exact stdout/log of a JVM.

To instruct the JVM to also log initialization events:

```bash
java -Xlog:class+load=info,class+init=info \
     -cp out/host TraceLoadDemo
```

JDK 17 has a legacy mapping from `TraceClassInitialization` to `-Xlog:class+init=info`. The specific class initialization log depends on the VM, so reading the markers printed by the program alongside the `class+init` log is an easy-to-understand way to verify.

Different APIs:

| API | Loading? | Initialization? |
|---|---|---|
| `Class.forName(name)` | Requests class loading/lookup using the caller class's loader | **Requests** initialization |
| `Class.forName(name, false, loader)` | Requests lookup through the specified loader | **Does not request** initialization |
| `loader.loadClass(name)` | Requests lookup through the loader | **Does not automatically request** initialization |
| `SomeType.class` | Class literal | Does not request initialization merely because of the literal |
| Calling active static method `SomeType.run()` | May require the class to be loaded/linked | **May trigger** initialization according to JVM rules |

Do not assume initialization always happens “immediately after loading”. JVM resolution/initialization has its own rules, and some resolution may be deferred.

## 9. Using class-load logs to find a wrongly selected JAR

Suppose an application has:

```text
libs/common-v1.jar
plugins/report/lib/common-v2.jar
```

Both contain `com.example.common.Codec`. When the plugin encounters `NoSuchMethodError`, one possibility is that the plugin was compiled against v2 while the runtime loaded v1 from the parent classpath.

How to check:

1. Rerun with `-Xlog:class+load=info` and retain the log.
2. Filter by the binary name `com.example.common.Codec`.
3. Check whether `source` matches the expected runtime artifact.
4. Print `Codec.class.getClassLoader()` or retrieve the token via the plugin loader to confirm the defining loader.
5. Compare the ABI using `javap -classpath ... -s -p com.example.common.Codec` on both artifacts.
6. Check `parent-first` delegation and the private library location: if the parent has the same binary name, it can shadow the private copy.
7. Resolve the issue at the dependency ownership/delegation level; do not fix it by catching and ignoring `NoSuchMethodError`.

Illustrative bytecode inspection commands:

```bash
javap -classpath libs/common-v1.jar -s -p com.example.common.Codec
javap -classpath plugins/report/lib/common-v2.jar -s -p com.example.common.Codec
```

These are example paths and class names to replace to fit your project. `javap` only inspects **the specified artifact** and does not by itself prove that the runtime used that artifact; therefore, you must combine it with the class-load log.

### The same class name can appear multiple times in the log

Two custom loaders can **define two different runtime classes with the same binary name**. Do not conclude from duplicate-name log entries that the VM loaded the same class twice in a single loader.

To verify identity:

```java
Class<?> a = loaderA.loadClass("com.example.common.Codec");
Class<?> b = loaderB.loadClass("com.example.common.Codec");

System.out.println(a.getName().equals(b.getName()));
System.out.println(a == b);
System.out.println(a.getClassLoader() == b.getClassLoader());
```

This snippet requires two already-created loaders. If both delegate to the same parent, `a == b` may be `true`. If they actually define the classes independently, `a == b` is `false` despite having the same name. An info-level class log line does not replace comparing class tokens.

## 10. Debugging parent delegation: what can class loading logs tell you?

By default, `ClassLoader.loadClass(String, boolean)`:

1. Checks `findLoadedClass(name)`.
2. If not found yet, asks the parent; if the parent is null, asks the bootstrap loader per contract.
3. If still not found, calls `findClass(name)`.
4. Resolves the class when `resolve` is requested.

**A class-load event is not a branch-by-branch trace of the algorithm.** Not seeing a `findClass` event does not mean the method was never called; nor can you read a `class,load` line and deduce how many times parent lookups failed.

If you need to understand the delegation logic of **your own custom loader**, add selective instrumentation to the loader implementation:

```java
@Override
protected Class<?> findClass(String binaryName)
        throws ClassNotFoundException {
    System.out.println("FIND_CLASS_ATTEMPT=" + binaryName);
    return super.findClass(binaryName);
}
```

This is an **illustrative snippet** inside a `ClassLoader` subclass; the superclass's default method throws `ClassNotFoundException`, so this is not an actual JAR-reading loader. In production, avoid unbounded logging or leaking sensitive class names.

You can combine:

- `-Xlog:class+load=info` to see the classes recorded by the VM.
- Logs in `findClass`/factory to see the intended lookup source.
- `Class.getClassLoader()` to confirm the defining loader.
- `ClassLoader.getParent()` to inspect the parent chain.
- `Thread.currentThread().getContextClassLoader()` when an API uses the TCCL.

**Do not equate the TCCL with the defining loader.** The TCCL is state attached to a thread, whereas `Class.getClassLoader()` reflects the loader that defines the runtime class. `ServiceLoader.load(service)` uses the TCCL, whereas the single-parameter `Class.forName(String)` overload uses the loader of the calling class.

## 11. Combining unload events with evidence about loaders

To see when HotSpot actually records class unloading, enable `-Xlog:class+unload=info` on its own or combine it with `class+load=info`. Calling `URLClassLoader.close()` creates no guarantee that classes will unload immediately; the JVM can only unload them when the defining loader is eligible for GC and the runtime performs unloading.

When investigating redeploy/metaspace behavior, compare multiple `load → stop → GC/unload` cycles and cross-check surviving loaders, references from threads/TCCL, listeners, or caches. **Not seeing an unload event in a short run does not prove a leak.** The next article focuses specifically on `class+init`/`class+unload`, while the JFR/heap dump article explains how to trace GC roots to find the actual holder.
## 12. Writing Unified Logs to files, configuring decorators, and rotation

Production logs typically need size limits:

```bash
java -Xlog:class+load=info:file=classload-%p-%t.log:uptime,level,tags:filecount=3,filesize=10M \
     -cp out/host TraceLoadDemo
```

- `file=classload-%p-%t.log`: creates the log file; `%p` is the PID, and `%t` is the startup timestamp according to Java launcher logging.
- `uptime,level,tags`: retains timing, level, and tag information.
- `filecount=3,filesize=10M`: configures size-based log rotation with **approximate** limits, not a byte-exact retention SLA.
- The log path must have appropriate write permissions; do not allow untrusted parties to modify logs if incident investigation is needed.

Log rotation may **overwrite/delete older logs** according to the configuration. If an investigation requires complete retention, choose retention outside the runtime or collect logs through a secure process.

### Writing to stderr

```bash
java -Xlog:class+load=info:stderr:uptime,level,tags \
     -cp out/host TraceLoadDemo
```

Choosing stdout/stderr/file helps separate JVM diagnostics from application output. Keep in mind that some environments or log aggregation may merge streams, causing the displayed cross-stream order to differ from the actual flush order.

### Managing log volume

Enable verbose class logs in a controlled environment to avoid:

- Logging tens of thousands of unrelated classes.
- Increasing I/O overhead and disk usage.
- Complicating analysis due to log rotation.
- Exposing package structures, artifact paths, or environment information in logs.

On the first run, execute a small test and filter by the target class. Only raise the level to `debug` or widen the tag scope when necessary.

## 13. JDK 8 and JDK 17: do not mistakenly use legacy options

Many older articles suggest:

```text
-XX:+TraceClassLoading
-XX:+TraceClassUnloading
-XX:+TraceClassResolution
```

These historical JVM options have undergone changes/removals in newer JDKs. On JDK 17, the Oracle documentation instructs using Unified Logging:

```text
-XX:+TraceClassLoading    -> -Xlog:class+load=info
-XX:+TraceClassUnloading  -> -Xlog:class+unload=info
-XX:+TraceClassResolution -> -Xlog:class+resolve=debug
```

The table is a **conceptual mapping of legacy options**, not flags to pass simultaneously in a single launch command. Before copying a command from older documentation, verify the version:

```bash
java -version
java -Xlog:help
```

Especially when using shell scripts to deploy across multiple Java versions, do not enforce HotSpot/JDK 17 `-Xlog` options on older runtimes that do not support them. Manage runtime options per environment.

## 14. Diagnosing exceptions with the right kind of data

| Symptom | How does the class-load log help? | What else must be inspected? |
|---|---|---|
| `ClassNotFoundException` | Whether loading was ever recorded for the class name; whether the source makes sense | Loader visibility, binary name, classpath/module path |
| `NoClassDefFoundError` | Where related classes/dependencies were loaded from | Root cause, linkage/init failure, nested `Caused by` |
| `NoSuchMethodError` | Which artifact the library class actually came from | ABI/method descriptor via `javap`; compile-time version |
| `ClassCastException` | May reveal the same binary name appearing from multiple sources | Runtime `Class<?>` identity and defining loaders |
| `LinkageError` / loader constraint | Which classes are involved and their loading order | `class+loader+constraints`, method descriptors, shared API |
| `ExceptionInInitializerError` | Whether the class loaded before the init failure | `class+init`, `<clinit>`, static dependencies |
| `ServiceConfigurationError` | Whether the provider class was loaded | `ServiceLoader`, TCCL, provider descriptor/module, assignability |
| `IllegalAccessError` / reflection access | Which module the class was loaded from | Module readability, `exports`/`opens`, Java access modifiers |
| Metaspace growth after reload | Load/unload events across multiple cycles | GC roots, old loaders, heap dump, jcmd/JFR |

**Distinguish between “the class name is absent from the log” and “the class definitely does not exist”.** A class may never have been requested for loading, may have been loaded in another process/run, or the JVM logging selector may not capture the event you need. Do not draw conclusions solely from an empty grep result.

### Example: analyzing NoSuchMethodError

Suppose `com.acme.Parser` version 1 has `parse(String)`, while version 2 adds `parse(byte[])`. The plugin is compiled against v2, but at runtime the parent returns version 1.

One investigation path:

1. Capture the stack trace with the failing method.
2. Enable `-Xlog:class+load=info`; filter for `com.acme.Parser`.
3. Read the event's `source` and inspect the JAR/version there.
4. Compare `javap -s -p` on the v1 and v2 JARs.
5. Check whether the parent loader holds the v1 JAR and whether the plugin loader is parent-first.
6. Fix the dependency layout or plugin isolation per contract; do not catch `NoSuchMethodError` and continue.

This example only illustrates an ABI mismatch scenario; `NoSuchMethodError` also has other causes related to binary compatibility.

## 15. Observation recipes by goal

**To see which classes are loaded by the JVM:**

```bash
java -Xlog:class+load=info -cp out/host TraceLoadDemo
```

**To quickly compare with the traditional option:**

```bash
java -verbose:class -cp out/host TraceLoadDemo
```

**To log both load and unload together:**

```bash
java -Xlog:class+load=info,class+unload=info -cp out/host TraceLoadDemo
```

**To distinguish loading from initialization:**

```bash
java -Xlog:class+load=info,class+init=info -cp out/host TraceLoadDemo
```

**To inspect detailed class resolution:**

```bash
java -Xlog:class+resolve=debug -cp out/host TraceLoadDemo
```

**To separate JVM logs from application stdout:**

```bash
java -Xlog:class+load=info:file=classload.log:uptime,level,tags -cp out/host TraceLoadDemo
```

**To check which tags are actually supported by the runtime:**

```bash
java -Xlog:help
```

A time-saving workflow is usually: **enable info → filter by binary name → identify source → verify the defining loader in code → only enable additional debug/resolve/init/constraints when the evidence calls for it**.

## 16. Common mistakes when reading logs

| Misconception | Accurate interpretation |
|---|---|
| “`-verbose:class` only logs loads” | In Oracle JDK 17's mapping, it is equivalent to load and unload at info level |
| “`-Xlog:class+load=info` and `-verbose:class` are completely identical” | The second option also includes unload in the JDK 17 mapping |
| “Each `loadClass` call corresponds to a new class-load line” | A loader can reuse an already-loaded `Class<?>` |
| “A class appearing in the log means its static initializer has run” | Loading and initialization are two distinct phases |
| “The source path definitely identifies the defining loader object” | Source usually only indicates the origin of the bytes; class token/loader identity is also needed |
| “Not seeing a class in the log means the class does not exist” | The class may not have been requested yet, or the log may be configured differently |
| “Two lines with the same binary name mean duplicate definitions in one loader” | Two different loaders can define classes with the same name |
| “The uptime difference is the class loading duration” | Uptime is the log timestamp, not the elapsed load cost |
| “Closing a URLClassLoader must produce an unload event immediately” | Closing does not determine immediate GC/unloading |
| “`class+load=debug` always prints every parent/child relationship” | Debug output depends on log sites/JDK; verify using APIs/a profiler |
| “Enabling `class*=trace` in production is always fine” | The log volume/performance/privacy impact may be unacceptable |
| “Legacy `TraceClassLoading` flags are guaranteed to still work on 17” | Use the Unified Logging mappings in the JDK 17 documentation |

## 17. Self-check exercises

**Question 1.** Which Unified Logging configuration is `-verbose:class` equivalent to in Oracle JDK 17?

**Answer:** `-Xlog:class+load=info,class+unload=info` according to the `java` command documentation.

**Question 2.** Does using `-Xlog:class+load=info` guarantee that unload events will appear?

**Answer:** No. This selector is for the class+load tag set. To include unload events, add `class+unload=info`.

**Question 3.** In the demo, `Class.forName(name, false, pluginLoader)` followed by `pluginLoader.loadClass(name)` returns the same `Class<?>`. Must there be two separate load events?

**Answer:** No. The loader can use the already-loaded/recorded class; two lookup calls do not equal two class definitions.

**Question 4.** What does `-Xlog:class+load` appearing before `PLUGIN_INITIALIZED` indicate?

**Answer:** The class was loaded before static initialization ran. You cannot infer that initialization has completed solely from a class-load event.

**Question 5.** Why does the log `source: file:/.../plugin.jar` not prove that the artifact is trustworthy?

**Answer:** It reports the source according to the JVM; it does not verify the artifact's digest, signature, or approval.

**Question 6.** If a plugin loads `Parser` from parent v1 instead of child v2, how can the log help?

**Answer:** It can point out the source of the runtime `Parser`; combine this with the defining loader and `javap` to confirm an ABI/version mismatch.

**Question 7.** Why can two custom loaders cause a single binary name to appear multiple times in the log?

**Answer:** Because runtime type identity also includes the defining loader; each loader can define a separate class with the same name.

**Question 8.** Is an unload log immediately after `URLClassLoader.close()` guaranteed?

**Answer:** No. Closing releases resources; unloading depends on the loader being eligible for GC and the VM's decision.

**Question 9.** Does a line `[0.205s][info][class,load] ...` mean loading the class took 205 ms?

**Answer:** No. `0.205s` is the JVM uptime at the time of the event, not the duration of the operation.

**Question 10.** Which tags should be combined when investigating an `ExceptionInInitializerError`?

**Answer:** `class+load` with `class+init`, along with the stack trace/static initializer of the class.

**Question 11.** If `grep` does not find a class name, can we conclude that the class was definitely not loaded?

**Answer:** Not without being certain that the runtime log is complete for the relevant process/run and selectors; the class may never have been requested, or the log may have been filtered or rotated.

**Question 12.** Which example can be used to write class loading logs to a file, separated from application stdout?

**Answer:** `-Xlog:class+load=info:file=classload.log:uptime,level,tags`.

## 18. Summary and official sources

**Five key points:**

1. **`-verbose:class`** is a quick way to observe class loading and on HotSpot/JDK 17 maps to **class load + unload info**.
2. **`-Xlog:class+load=info`** is an explicit selector for **class loading** events; you can configure `debug`, output, decorators, and rotation.
3. **Class loading differs from initialization, resolution, and unloading.** Read logs in the right phase context, combining them with stack traces and appropriate tags.
4. **A log line is not complete proof of class identity or trust.** Check `Class.getClassLoader()`, `Class<?> ==`, the classpath/module path, and artifact digests when needed.
5. **Diagnose by hypothesis:** identify the binary name/source first, then expand logging in a targeted manner rather than enabling all tags indiscriminately.

Standard Java 17 documentation:

- [Oracle Java SE 17 — The java Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): `-verbose:class`, `-Xlog`, tags/levels/outputs, and legacy tracing flag mappings.
- [OpenJDK JEP 158 — Unified JVM Logging](https://openjdk.org/jeps/158): structure of log levels, tags, outputs, and decorators.
- [Java SE 17 — ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): `loadClass`, delegation, and `findLoadedClass`.
- [Java SE 17 — Class.forName](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): overload with `initialize` and loader parameters.
- [Java SE 17 — URLClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html): loading classes/resources from URLs and `close()`.
- [JLS 17 — 12 Execution](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html): loading, linking, initialization, and unloading.
- [JVMS 17 — 5 Loading, Linking, and Initializing](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): JVM rules for the class lifecycle.
