# Tracking Class Initialization and Unloading with Appropriate Log Tags in Java

## 1. Goal: Properly Distinguishing Events in the Class Lifecycle

When analyzing a Java application with multiple libraries, plugins, frameworks, or reload mechanisms, the question "has this class been initialized yet?" is completely different from "has the JVM loaded the class yet?" or "has the class been unloaded from the JVM yet?". **Class loading**, **class initialization**, and **class unloading** are events with different conditions, timing, and meanings. The HotSpot JVM provides **Unified Logging** via the `-Xlog` option to observe them using separate tag groups.

This lesson focuses on **choosing the right log tags, reproducing events, reading logs on a sound basis, and understanding the limitations of the evidence** on HotSpot JDK 17+. The commands below are based on JDK 17 `java` syntax; other JVMs such as OpenJ9 may use different logging systems and options.

| Event | Meaning | HotSpot Log to Inspect |
|---|---|---|
| **Loading** | The JVM retrieves/defines a class or interface; the class now has a runtime identity by name and defining loader | `class+load` |
| **Linking/resolution** | The JVM verifies, prepares, or resolves symbolic references | `class+resolve` when deep analysis is needed; not identical to initialization |
| **Initialization** | The JVM executes the class/interface initialization procedure, including running static initializers when present | `class+init` |
| **Unloading** | The JVM records unloading a loaded class/interface when lifecycle and reclamation conditions permit | `class+unload` |
| **Garbage collection** | GC cycle; timing/collection-type data to correlate with unloading | `gc` or `gc*` groups when needed |
| **Metaspace** | Context for JVM metadata memory usage/allocation | `gc+metaspace` at an appropriate level and other statistical tools |

Do not infer "a load line is present ⇒ initialization definitely happened" or "GC ran ⇒ all unused classes have been unloaded." A class can be **loaded but not yet initialized**; a class loader having lost strong references only makes the classes it defines **eligible** for unloading, without making any guarantee about timing.

### Semantic Diagram

```text
Request to use class received
       │
       ▼
   Loading ──────────────► [class,load]
       │
       ▼
   Linking / resolution
       │
       ▼
Active use triggered? ── No ──► May remain uninitialized
       │ Yes
       ▼
   Initialization ───────► [class,init]
       │
       ▼
 Class/loader exists, used by application
       │
       ▼
 Loader/class eligible for reclamation?
       │ Yes, and JVM performs unloading
       ▼
   Unloading ────────────► [class,unload]
```

This diagram is for categorizing **log semantics**; it does not assert that the timing of all steps is linear, or that every step produces exactly one log line. The JVM may defer resolution; some logs may be written by different threads.

## 2. Choosing the Right `-Xlog` Tags and Levels

Unified Logging has the general syntax:

```text
-Xlog[:[tag-selection][:[output][:[decorators][:output-options]]]]
```

In `tag-selection`:

- `class+load` means the **combined tag set** of `class` and `load`.
- Commas in `class+load=info,class+init=info,class+unload=info` denote **multiple independent selections**.
- `=info` selects messages at level `info` and above within the severity threshold of that selection; `debug`/`trace` are more detailed and can increase log volume significantly.
- Without `*` after the tag combination, the selection matches **the exact tag set**. `class*=debug` matches tag sets containing `class` and will be broader/noisier.
- `-Xlog:help` displays the tags, levels, decorators, and output options of the **currently running Java runtime**. If a selection is not recognized by HotSpot, read the error and help output instead of assuming the flag works.

### Minimal Configurations by Question

**Only to know which classes are loaded:**

```bash
java -Xlog:class+load=info -cp . InitTrace
```

**Only to track when initialization occurs:**

```bash
java -Xlog:class+init=info -cp . InitTrace
```

**Only to track class unloading:**

```bash
java -Xlog:class+unload=info -cp . UnloadTrace
```

**To track all three event types and correlate with GC:**

```bash
java -Xlog:class+load=info,class+init=info,class+unload=info,gc=info -cp . InitTrace
```

`UnloadTrace` and `InitTrace` are created in the hands-on sections below. On HotSpot, `-verbose:class` is equivalent to logging class load and class unload at the `info` level according to the JDK 17 documentation; **it does not replace `class+init`** when the goal is to observe initialization.

Note that `-Xlog:class=info` is not synonymous with the three selections above. The `class` tag alone is a different tag set from `class+load` and `class+init`. When investigating specific events, use the exact combinations supported by the documentation.

### Writing to a File to Reduce stdout Noise

```bash
java -Xlog:class+load=info,class+init=info,class+unload=info,gc=info:file=class-events-%p.log:time,uptime,pid,tid,level,tags:filecount=5,filesize=10M -cp . InitTrace
```

In this configuration:

- `file=class-events-%p.log` writes logs to a file containing the PID, which is convenient for distinguishing multiple JVMs; the working directory requires write permission.
- `time,uptime,pid,tid,level,tags` adds wall-clock time, time since JVM startup, PID/TID, level, and tags to correlate events.
- `filecount=5,filesize=10M` limits size/rotation via the Unified Logging mechanism; rotation is described as occurring at approximately the configured size.
- JVM logs go to the file; the program's `System.out.println` statements still go to stdout, helping separate the two observation streams.

To view logs and application output on the same console without a file, keep `:stdout:uptime,level,tags`:

```bash
java -Xlog:class+load=info,class+init=info,class+unload=info:stdout:uptime,level,tags -cp . InitTrace
```

On Windows PowerShell, you can wrap the entire `-Xlog:...` parameter in quotes when required by the shell/parser. The comma-separated syntax is **a single JVM argument**, not separate arbitrary arguments.

## 3. Java 17+ Experiment: Clearly Observing Load Before Init

To observe initialization, you need to design the program so that the target class is loaded first, and **active use** happens only afterward. A `Class.forName` overload with `initialize=false` helps demonstrate the difference.

Create the file **`InitTrace.java`**:

```java
public final class InitTrace {
    static final class Target {
        // Constant variable: the compiler can inline the value.
        static final int CONSTANT = 7;

        // Not a compile-time constant.
        static int counter = 42;

        static {
            System.out.println("Target.<clinit> executed");
        }

        static void ping() {
            System.out.println("Target.ping");
        }
    }

    public static void main(String[] args) throws Exception {
        System.out.println("1. Class.forName(false)");
        Class.forName("InitTrace$Target", false,
                InitTrace.class.getClassLoader());

        System.out.println("2. Constant = " + Target.CONSTANT);
        System.out.println("3. Read counter");
        System.out.println("Counter = " + Target.counter);

        System.out.println("4. Call ping");
        Target.ping();

        System.out.println("5. Class.forName(true) after init");
        Class.forName("InitTrace$Target", true,
                InitTrace.class.getClassLoader());
        System.out.println("6. Done");
    }
}
```

Compile and run with HotSpot JDK 17+:

```bash
javac InitTrace.java
java -Xlog:class+load=info,class+init=info -cp . InitTrace
```

The program itself prints these exact lines, **interleaved with other JVM logging lines**:

```text
1. Class.forName(false)
2. Constant = 7
3. Read counter
Target.<clinit> executed
Counter = 42
4. Call ping
Target.ping
5. Class.forName(true) after init
6. Done
```

**How to analyze:**

1. `Class.forName("InitTrace$Target", false, loader)` requests loading the class but **does not request initialization**. You can see the `[class,load] InitTrace$Target ...` log line before the program prints "3. Read counter".
2. `Target.CONSTANT` is a primitive **constant variable** with a compile-time constant expression. Java typically inlines `7` into the caller, so merely reading this constant **does not trigger Target initialization**.
3. `Target.counter` is a static field that is not a constant variable: the first read is an **active use** and triggers initialization, running the static initializer. The JVM may log `[class,init] ... InitTrace$Target ...` around the time the program prints `Target.<clinit> executed`.
4. `Target.ping()` is called after the class has already been initialized, so it does not run the static initializer again.
5. `Class.forName(..., true, ...)` again requests initialization, but the class is already initialized; there is no second `<clinit>` execution for the same runtime class.

The internal name of the nested class is `InitTrace$Target`, which differs from the Java source notation `InitTrace.Target`. The class file `InitTrace$Target.class` is generated alongside `InitTrace.class` after compilation.

**Read event logs carefully:** HotSpot `[class,init]` lines may include an index, the class name in `InitTrace$Target` form, and a VM address. Those numbers/addresses are **run-dependent**, not fixed output. You do not need to look for a single immutable text format; check the **tag, class name, timestamp, and relative order**. In particular, init logs can report events for underlying JDK classes that your code does not directly mention.

### Why Don't `Target.class` and `Class.forName(false)` Prove Initialization by Themselves?

A `Target.class` literal can obtain the `Class` object without performing class initialization; meanwhile, `Class.forName(name, false, loader)` explicitly means **do not initialize at that call**. This is why the count of `[class,load]` lines cannot be used as the count of initialized classes.

Operations that normally trigger initialization according to JLS `12.4.1` include: creating an instance of the class, invoking a static method declared by the class, reading/assigning a static field declared by the class **except reading a constant variable**, and certain reflection operations. When initializing a class, the JVM processes uninitialized superclasses and qualifying superinterfaces according to the specification; the log sequence may contain more classes than just the target.

A class initializes **only once per runtime class identity** during its valid lifetime. If another loader defines a class with the same name, that is a different class and can initialize separately. Do not treat two events with the same name as proof that the JVM "re-initialized the same class" before checking the defining loader.

## 4. Reading `class+load`, `class+init`, and `class+unload` on a Sound Basis

Example of illustrative log format, with other lines omitted and **not representing exact fixed addresses/IDs**:

```text
[0.090s][info][class,load] InitTrace$Target source: file:/.../
[0.094s][info][class,init]  ... Initializing 'InitTrace$Target' ...
```

Breakdown of each part:

- `[0.090s]` is the uptime since JVM startup (if this decorator is enabled).
- `[info]` is the level.
- `[class,load]` or `[class,init]` is the **tag set of the log line**. Commas appear in the **log's tag output format**, whereas the selection syntax uses `+`.
- `source` in a load log can be a JAR path, directory, `shared objects file`, or another form; it does not necessarily always point to a simple local file.
- `class,init` reflects the JVM handling initialization; even if the class has no substantive static initializer, an initialization message may still appear. You do not need to see `System.out.println` from `<clinit>` to accept the log as valid.

**Limitations:** a "class loaded" log does not indicate whether the loader remains reachable over a long period; an init log does not measure the amount of allocated memory; an unload log does not prove the underlying reason the loader was eventually reclaimed. Each tag answers one question, and you should cross-check other evidence when diagnosing leaks or reloads.

## 5. Experiment: Creating a Custom Loader and Tracking Class Unloading

Class unloading is harder to produce deterministically than class initialization. Classes defined by long-lived loaders typically cannot be unloaded independently at will. We use a dedicated `URLClassLoader` to define a plugin class, execute it once, close the resource, drop **strong references**, and then observe the logs.

### Directory Structure

```text
working-directory/
  UnloadTrace.java
  plugin-src/
    plugin/
      Ephemeral.java
  plugin-bin/           (created by javac, DO NOT put on the host -cp)
```

File **`plugin-src/plugin/Ephemeral.java`**:

```java
package plugin;

public final class Ephemeral {
    static {
        System.out.println("plugin.<clinit>");
    }

    public static void touch() {
        System.out.println("plugin.touch");
    }
}
```

File **`UnloadTrace.java`**:

```java
import java.lang.ref.WeakReference;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class UnloadTrace {
    private static WeakReference<ClassLoader> runPlugin()
            throws Exception {
        URL url = Path.of("plugin-bin")
                .toAbsolutePath().toUri().toURL();

        try (URLClassLoader loader = new URLClassLoader(
                new URL[] { url },
                ClassLoader.getPlatformClassLoader())) {
            Class<?> clazz = Class.forName(
                    "plugin.Ephemeral", true, loader);
            clazz.getMethod("touch").invoke(null);

            System.out.println("Child defines class: "
                    + (clazz.getClassLoader() == loader));

            // Do not return Class<?> or a strong reference to the loader to main.
            return new WeakReference<>(loader);
        }
    }

    public static void main(String[] args) throws Exception {
        WeakReference<ClassLoader> weak = runPlugin();

        // Only creates a GC opportunity; does not guarantee unloading.
        for (int i = 0; i < 30 && weak.get() != null; i++) {
            System.gc();
            Thread.sleep(150);
        }

        System.out.println("Loader reference cleared: "
                + (weak.get() == null));
    }
}
```

To run in a Bash shell from the `working-directory` directory:

```bash
mkdir -p plugin-bin
javac -d plugin-bin plugin-src/plugin/Ephemeral.java
javac UnloadTrace.java
java -Xlog:class+load=info,class+init=info,class+unload=info,gc=info -cp . UnloadTrace
```

On Windows PowerShell, simply create the directory with `New-Item -ItemType Directory -Force plugin-bin` (or `mkdir plugin-bin`), then run the same three `javac` and `java` commands above.

The lines produced **by the application** at the beginning are always:

```text
plugin.<clinit>
plugin.touch
Child defines class: true
```

Then the application prints one of two possibilities:

```text
Loader reference cleared: true
```

or:

```text
Loader reference cleared: false
```

Either value can occur. If HotSpot actually unloads `plugin.Ephemeral` during the observation window and logging is enabled properly, the log may contain a message tagged `[class,unload]` naming that class. The timing of this line is determined by the JVM; do not write a fake unload line into the application output yourself.

**Why is this experiment meaningful?**

- The parent is `ClassLoader.getPlatformClassLoader()`, not the application class loader that loaded `UnloadTrace`. As long as `plugin-bin` is **not** on the host's classpath, `plugin.Ephemeral` will be defined by the child loader, matching the printed line `Child defines class: true`.
- `runPlugin()` has its own scope so that local references to `clazz`, `loader`, and reflection results go out of scope when the method returns. `WeakReference` does not keep the loader strongly reachable.
- `URLClassLoader.close()` only closes resources managed by the loader; **it is not an API that forces unloading**.
- `System.gc()` suggests a GC and may be ignored or fail to trigger class unloading within the observation window; options such as `-XX:+DisableExplicitGC` make relying on this call even less dependable.
- If `Loader reference cleared: false`, that is not enough to conclude there is a leak: there may not have been a suitable GC cycle yet, the JVM/JIT may still hold temporary references, or a strong reference path to the loader may still exist. Further inspection is required before drawing a conclusion.
- If the weak reference has been cleared, that is a useful data point regarding reachability/GC of the loader; however, the question of **whether a specific class has been unloaded** still needs to be verified against the `class+unload` log and the exact class loader.

In other test code using thread pools, listeners, `ThreadLocal`, static caches, or framework registries, strong references can still retain instances, `Class<?>`, or the loader; in that case, the unload event will not occur even after calling `close()`. In a real application, you must fully release the lifecycle and observe **multiple cycles** under appropriate load conditions.

## 6. Analyzing Timing with GC and Metaspace

When you see a class unload, you should also ask **which GC occurred near that timestamp**. For example:

```bash
java -Xlog:class+unload=info,gc=info:stdout:time,uptime,pid,level,tags -cp . UnloadTrace
```

Use the same log output and consistent decorators to compare timestamps. Note that GC logs may mention a "Pause", "Concurrent Cycle", or another phase depending on the collector; **you must not assume every GC will unload all eligible classes**. Do not infer from a "GC" line alone that unloading has definitely occurred.

If you need to investigate metaspace, you can use complementary signals such as:

```bash
jcmd <pid> VM.classloader_stats
jcmd <pid> VM.metaspace
jcmd <pid> help
```

`<pid>` is a placeholder to replace with the actual PID. The `jcmd` commands require attach permissions and a compatible JDK. They provide snapshots/statistics and **do not replace event logs containing class names**. Committed/reserved metaspace capacity also depends on the allocator, reuse policies, and other currently loaded classes, so **no decrease** after unloading does not by itself prove that classes are being retained.

When logs become too large, filter by `[class,unload]` lines and the target class/loader name (if loader details are present in your JVM build). However, you should **preserve the original log** along with PID, timestamps, JVM flags, and artifact version so you do not lose related load/init/GC milestones.

## 7. How to Read Evidence Across Scenarios

| Observation | What Can Be Confirmed | What Cannot Yet Be Confirmed |
|---|---|---|
| `[class,load]` appears for `com.example.Plugin` | The JVM recorded the loading event for this class | `<clinit>` has executed |
| `[class,init]` appears for the target class | The JVM started/performed the initialization procedure for the class | The class was subsequently unloaded |
| `[class,unload]` specifies the exact class/loader | The JVM recorded unloading at the logged time | The application has no other leaks |
| A GC log appears after plugin disposal | The JVM recorded GC activity | The plugin class was definitely unloaded |
| No `[class,unload]` seen after a single `System.gc()` | No matching unload was recorded in the observed data | This is definitely a class-loader leak |
| No `[class,init]` seen when printing a compile-time constant | This matches the constant-variable rule not requiring initialization | The class was never loaded |
| Two init events with the same binary name | At least two events associated with that name appear in the log | The same runtime class initialized twice; loader identity must be checked |

**The order of stdout output and log lines can be affected by buffering, multiple threads, and the use of file output.** When accurate timeline analysis is required, prioritize log timestamps/uptime, record application milestones using the same clock, and consider time-source synchronization and asynchronous logging settings. Do not infer strict causal order solely from appearance order when mixing stdout/stderr/file.

## 8. Diagnostic Workflow Applicable in Projects

1. **Ask a specific question:** "Was the class loaded but not yet initialized?", "Did the plugin initialize multiple times under different loaders?", or "After logical unloading, has the old class loader been GC'd and have the classes been unloaded?".
2. **Enable minimal tags before the event to capture:** `class+load` for loading, `class+init` for initialization, `class+unload` for unloading; add `gc` when timing correlation is needed. If a tag is only enabled after the event, logs do not reconstruct past data.
3. **Record environment identity:** JDK/vendor, collector, flags, PID, application/build version, classpath/module path, loader type, and load/redeploy timestamps. In multi-process systems, identify the exact PID before comparing.
4. **Perform controlled actions:** load the class, call static APIs, load the plugin, dispose the plugin. For unloading, drop strong references and provide an adequate observation window; avoid treating a single `System.gc()` call as a mandatory condition.
5. **Read events by the exact tag and exact class identity.** If the same class name has multiple loaders, do not lump them all into a single entity; cross-check the class source and loader when the JVM emits that information.
6. **Gather supplementary evidence if a root-cause conclusion is needed:** class load source, `Class.getClassLoader()`, loader statistics, GC roots, metaspace, and heap dump/JFR as appropriate.
7. **Conclude strictly from the data:** "observed unload of class X at time T" is stronger than "metaspace appeared to decrease"; "no event observed within the observation window" is different from "definitely a leak".

### Observing or Changing Logging of a Running JVM

On HotSpot, you can use the `VM.log` diagnostic command via `jcmd`, but it only takes effect for **events occurring from the moment the configuration is enabled onward**:

```bash
jcmd <pid> help VM.log
jcmd <pid> VM.log list
```

Depending on the version/runtime, use the syntax shown in `help VM.log` to enable or change outputs/selections. You should enable logging right at startup for reliable reproduction experiments; do not attempt to infer an initialization that occurred before logging was enabled.

## 9. Common Mistakes When Configuring and Interpreting Logging

**1. Enabling only `class+load` and drawing conclusions about init state.** The two log tags measure different events. Use `class+init` together with an active-use test.

**2. Using `-Xlog:class=info` instead of `class+init=info`.** Select the exact tags; `+` combines multiple tags, while `,` separates multiple selections.

**3. Using `-verbose:class` and assuming initialization is being logged.** According to JDK 17 documentation, this shortcut covers class loading and unloading, and does not replace the init tag.

**4. Turning off logging or enabling it after the class has initialized.** The JVM does not normally re-run `<clinit>` for the same runtime class just for logging. If you need to repeat from the beginning, start a new JVM or test with a new defining loader.

**5. Assuming classes with the same name are the same class.** Class identity is based on binary name and defining loader; a new plugin loader can define the same name as an old class loader.

**6. Confusing the absence of unload logs with a proven leak.** Class unloading depends on reachability, the collector, and collection timing. Missing evidence may be due to tag/level/output settings, observation duration, or the loader still having a valid strong reference path.

**7. Merging class logs with GC logs and concluding from a single line.** A GC log only describes GC; you need a class+unload event or appropriate loader/GC roots evidence.

**8. Failing to preserve complete log metadata.** When analyzing multiple JVMs, timestamps like `[0.100s]` are calculated from each process's own uptime; merging two processes solely by uptime will misorder events. Combine PID, wall time, JDK flags, and build version.

**9. Using `class*=trace` in production for long periods without capacity control.** Broad logging has overhead, increases I/O, and puts pressure on storage. Enable the right combinations/levels, use rotation, and limit collection duration.

**10. Reading the load log source and assuming it is the defining loader.** `source` indicates the origin of the bytes in the log context; to confirm class identity, you must verify the loader. For plugins/custom class loaders, verify `Class.getClassLoader()` and the delegation mechanism.

## 10. Practice Exercises and Answers

**Question 1.** After `Class.forName("InitTrace$Target", false, loader)`, `[class,load]` appeared, but `[class,init]` did not. Is this an error?  
**Answer:** No. This behavior is consistent with requesting loading without initialization. Reading `Target.counter` or another active use is what triggers initialization.

**Question 2.** Why does reading `static final int CONSTANT = 7` not necessarily trigger initialization?  
**Answer:** `CONSTANT` is a constant variable initialized with a compile-time constant expression; the caller can use the inlined value without accessing the field at runtime.

**Question 3.** Does `-Xlog:class+load=info,class+init=info,class+unload=info` mean the JVM automatically performs loading/init/unloading?  
**Answer:** No. This is an **observation configuration** for events when the JVM executes them, not a command that forces the lifecycle.

**Question 4.** After `URLClassLoader.close()` and `System.gc()`, no `[class,unload]` is observed. What can be concluded?  
**Answer:** Unloading was not observed within that window; you must verify strong references, GC configuration, logs, timing, and loader identity before claiming a leak.

**Question 5.** When diagnosing the same class name from two plugin loaders, what information helps avoid confusion?  
**Answer:** Identify the defining loader, class source, PID, version, and event timeline; a binary name alone is not sufficient to identify a runtime class.

## Official References

- [Oracle JDK 17 `java` command / Unified Logging / legacy flags mapping](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): `-Xlog` syntax, tags/levels/outputs, `TraceClassInitialization → class+init`, and `-verbose:class`.
- [Java Language Specification 17 — Chapter 12, Execution](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html): `12.4.1` specifies when a class/interface is initialized, `12.4.2` covers the detailed initialization procedure, and `12.7` covers unloading.
- [Java SE 17 — `Class.forName`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#forName(java.lang.String,boolean,java.lang.ClassLoader)): the `initialize` parameter and reflection behavior.
- [Java SE 17 — `URLClassLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html): loader lifecycle and `close()`.
- [JDK 17 — `jcmd` manual](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): `VM.log`, `VM.classloader_stats`, and `VM.metaspace` for runtime analysis.
