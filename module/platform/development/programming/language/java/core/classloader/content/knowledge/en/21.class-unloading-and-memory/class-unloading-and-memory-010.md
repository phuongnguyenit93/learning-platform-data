# Observing Class Unloading and Avoiding Conclusions from a Single `System.gc()` Call

## 1. Purpose and Nature of Class Unloading

**Class unloading** is the process by which the JVM may remove loaded class/interface definitions along with their associated metadata when they are no longer needed. This is a class lifecycle and memory management activity, distinct from **class loading**, **linking**, **initialization** (static initialization), and the collection of ordinary objects on the heap.

In Java, the identity of a class is not just its binary name such as `lesson.UnloadTarget`, but is also tied to the **defining class loader** that defined it. Two independent class loaders can define two classes with the same name, yet they remain two distinct types at runtime. When building applications with plugins, hot reload, redeployment, or dynamic creation of multiple class loaders, whether an old loader can be reclaimed determines whether the classes it defined can be unloaded.

Key conditions and limitations to remember:

- **A live object of a loaded class** can keep both the class and its defining loader reachable. A direct strong reference to a `Class<?>`, `Method`, `Constructor`, instance, loader, or related runtime structure can also prevent the loader from being reclaimed.
- For classes defined by an **application-created class loader**, the JVM can unload the classes only when the reachability conditions for reclaiming the defining loader are satisfied. Merely calling `close()` on a `URLClassLoader` closes resources such as JAR/file handles; **it is not a command to unload classes**.
- Classes defined by the bootstrap loader typically live for the lifetime of the JVM; you should not use `java.lang.String` as an example to verify the unloading of a plugin.
- The state of "no longer having strong references from the application" only makes the loader **eligible** for reclamation. When GC runs, when unloading occurs, and whether physical memory is returned to the OS depend on the JVM, collector, and configuration.

A common reference retention path:

```text
GC root
  └── static cache belonging to a long-lived application/loader
        └── plugin instance
              └── plugin class / defining class loader
```

If a cache, a running thread, or a thread context class loader still retains the plugin, the plugin's lifecycle **has not ended in terms of reachability**, even if application code has already "undeployed" it.

## 2. Why Does a Single `System.gc()` Prove Nothing?

`System.gc()` is **a hint to the JVM to make an effort toward garbage collection**, not a guarantee that "once GC finishes, every eligible class has been unloaded." The API specification does not guarantee the reclamation of specific objects, does not guarantee that a particular `Reference` will be cleared, and does not guarantee completion by the time the call returns. HotSpot can be configured to ignore explicit GC (for example, `-XX:+DisableExplicitGC`). The mechanism and timing of class unloading also depend on the garbage collector and its corresponding collection cycles.

You must distinguish four statements:

1. **"`System.gc()` was called"**: this only tells you the code executed the suggestion.
2. **"A GC occurred"**: requires GC logs/JFR or actual observed evidence; still **does not mean** a class loader is dead.
3. **"The class loader is no longer strongly reachable"**: is a prerequisite for the loader to be eligible for GC; does not mean the JVM has already unloaded the classes at that moment.
4. **"Class unloading occurred"**: requires an unloading event, or another direct signal with a clearly defined scope of interpretation.

Therefore, both of the following conclusions are wrong:

- "I called `System.gc()` once and saw no unloading, so there must be a leak."
- "After calling `System.gc()`, heap/metaspace usage dropped, so plugin class X must have been unloaded."

Heap object collection, class unloading, and a decrease in `metaspace committed` are related phenomena, but **they are not interchangeable measurements**. After unloading, the metaspace allocator may still retain chunks of memory for reuse; committed/reserved sizes do not necessarily drop immediately.

## 3. Which Signals Should You Observe?

On **HotSpot JDK 17+**, use a combination of event logs, JVM statistics, and reference inspection. Do not apply flag syntax verbatim across all JVM implementations.

| Signal | What does it confirm? | Limitations to note in conclusions |
|---|---|---|
| `-Xlog:class+unload=info` log shows the plugin class name | Direct evidence that the JVM recorded an unload event for that class | Logging must be enabled before the event; absence of a log line does not automatically prove a leak |
| `WeakReference<ClassLoader>.get() == null` | The weak reference to the loader was cleared by GC; useful to check that the loader is no longer kept alive | Does not replace per-class unload timestamps/events; an uncleared result does not prove a leak |
| `ClassLoadingMXBean.getUnloadedClassCount()` increases | Some classes were recorded by the JVM as unloaded since startup | Counted **JVM-wide**; does not confirm the specific class under investigation |
| `jcmd <pid> VM.classloader_stats` at multiple points in time | Class loader/class statistics at each observation point | Snapshot; differences may be caused by concurrent loading of other loaders/classes |
| `jcmd <pid> VM.metaspace` and GC logs | Metadata area trends, GC timing, and memory pressure | Unchanged or reduced usage is not enough to conclude that a specific class was unloaded |

To log from startup:

```bash
java -Xlog:class+unload=info,gc*=info -cp . UnloadingProbe
```

For real applications with heavy logging, you can direct output to a file:

```bash
java -Xlog:class+unload=info,gc*=info:file=class-gc.log:time,uptime,level,tags -jar app.jar
```

The value of logs lies in **actual events and timestamps**, not in guessing "after running the GC statement." `jcmd` commands require a JDK and appropriate attach permissions; you can check which commands the JVM supports with `jcmd <pid> help`.

## 4. Java 17+ Experiment: Loading a Class via a Dedicated Loader and Observing It

The experiment uses two Java files and a separately compiled plugin directory. The goal is to create conditions where the loader can be reclaimed, and then read the evidence. Reclamation/unloading **is not forced to happen on every run**.

### Step 1: Create the plugin class

File **`plugin-src/lesson/UnloadTarget.java`**:

```java
package lesson;

public class UnloadTarget {
    public static String answer() {
        return "ready";
    }
}
```

### Step 2: Create the driver program

File **`UnloadingProbe.java`**, located in the root working directory, **not** inside `plugin-classes`:

```java
import java.lang.management.ClassLoadingMXBean;
import java.lang.management.ManagementFactory;
import java.lang.ref.WeakReference;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class UnloadingProbe {
    private static WeakReference<ClassLoader> loadOnce() throws Exception {
        URL pluginDirectory =
                Path.of("plugin-classes").toAbsolutePath().toUri().toURL();

        // The parent platform loader does not see the plugin class in plugin-classes.
        try (URLClassLoader loader = new URLClassLoader(
                new URL[] { pluginDirectory },
                ClassLoader.getPlatformClassLoader())) {
            Class<?> pluginClass =
                    Class.forName("lesson.UnloadTarget", true, loader);
            Object result = pluginClass.getMethod("answer").invoke(null);
            System.out.println("Plugin: " + result);

            // Return only a weak reference: do not retain Class, instance,
            // Method, or loader via a strong reference in the caller.
            return new WeakReference<>(loader);
        } // close() releases resources; it does not automatically unload classes.
    }

    public static void main(String[] args) throws Exception {
        ClassLoadingMXBean counter =
                ManagementFactory.getClassLoadingMXBean();
        long unloadedBefore = counter.getUnloadedClassCount();

        WeakReference<ClassLoader> loaderRef = loadOnce();

        for (int attempt = 0;
             attempt < 20 && loaderRef.get() != null;
             attempt++) {
            System.gc(); // Suggestion, NOT a guarantee.
            byte[] temporary = new byte[256 * 1024];
            temporary[0] = (byte) attempt;
            Thread.sleep(100);
        }

        System.out.println(
                "Loader weak reference cleared: " + (loaderRef.get() == null));
        System.out.println(
                "JVM-wide unloaded classes delta: "
                + (counter.getUnloadedClassCount() - unloadedBefore));
    }
}
```

**Explanation of design decisions:**

- `plugin-classes` must be outside the driver program's classpath so that `lesson.UnloadTarget` is actually defined by the dedicated `URLClassLoader`. If the class is loaded by the parent loader first, the experiment no longer measures the intended loader.
- `loadOnce()` is separated into its own method so that local variables `pluginClass`, the reflection result, and `loader` go out of scope; the JVM/JIT may still retain some temporary references longer than expected, so empirical observation is still required.
- `WeakReference` does not keep the loader alive via a strong reference. `URLClassLoader.close()` only closes resources. The loop gives the JVM more GC **opportunities** than a single call, but the iteration count still does not turn unloading into a guarantee.
- The counter from `ClassLoadingMXBean` is JVM-wide. Besides the plugin, the JVM may load/unload other classes; therefore, a delta greater than 0 is a supporting indicator, **not identification of a specific class**.
- Do not call `System.exit()` to "verify," because when a process exits, all process memory is reclaimed by the OS; that is not class unloading **within a running JVM**.

### Step 3: Compile and run

Create the `plugin-src/lesson` and `plugin-classes` directories beforehand. From the directory containing the two files above, run on JDK 17+:

```bash
javac -d plugin-classes plugin-src/lesson/UnloadTarget.java
javac UnloadingProbe.java
java -Xlog:class+unload=info -cp . UnloadingProbe
```

**Note:** Do not add `plugin-classes` to the `-cp` of `UnloadingProbe`; the host program only needs `.`. On Windows, the classpath separator differs when using multiple entries, but this example uses a single entry so `-cp .` works on both Windows and Unix.

The application output **will definitely start with**:

```text
Plugin: ready
```

The last two application lines have **run-dependent values**:

```text
Loader weak reference cleared: true
JVM-wide unloaded classes delta: 1
```

This is **one possible example output**, **not a guaranteed output**. The first value may be `false`; the delta may be 0 or greater than 1. If an unload event occurs, the HotSpot log may contain a line with the `[class,unload]` tag and the name `lesson.UnloadTarget`; the prefix/timestamp/internal addresses are dynamic. This log is closer evidence for the question "did the plugin class unload?" than seeing that `System.gc()` was called.

Run again with HotSpot configured to ignore explicit GC to observe behavioral differences; this is a **comparative test**, not a way to force the JVM to unload or prove a leak:

```bash
java -XX:+DisableExplicitGC -Xlog:class+unload=info -cp . UnloadingProbe
```

Even when explicit GC is ignored, **natural GC triggered by memory pressure can still occur**. Do not use the absence of an unload line in this run as a final conclusion.

## 5. How to Interpret Results by Scenario

**Scenario A — There is an unload log entry for `lesson.UnloadTarget`.** You can conclude that the JVM recorded the unloading of the test class. You should record the timestamp, JVM flags, corresponding log, and the loader that loaded the class for reproducibility and scoping.

**Scenario B — `loaderRef.get() == null` but no unload log line is seen.** This is a signal that the loader was cleared by GC via the weak reference. Check whether logging was enabled early enough with the right tags, check the observation window, and check the JVM being used. Do not infer "unloading was logged" if it actually was not.

**Scenario C — The loader reference is still not cleared after the loop.** There is not yet sufficient basis to label it a leak. There may not have been a suitable GC cycle, explicit GC may have been ignored, the JIT may still hold temporary references, or there may be a real strong reference. Extend the observation window and verify the reference graph before diagnosing.

**Scenario D — The counter delta is positive, but there is no log for the target class.** You can only state that **some classes** in the process were unloaded. Do not misattribute a JVM-wide result to plugin X.

**Scenario E — Metaspace committed has not decreased.** Not sufficient to prove that classes did not unload. The allocator may retain chunks for reuse, and other loaders may be loading new classes concurrently.

## 6. Monitoring Workflow in Real Plugin/Redeploy Applications

1. **Formulate a precise hypothesis.** For example: "After plugin version A stops and leaves the cache, loader A has no remaining live roots; class `com.example.plugin.Handler` is expected to be eligible for unloading after several GC cycles."
2. **Record a baseline before the action:** JVM/JDK version, collector, GC flags, timestamp, class unload logs, and loader/metaspace snapshots; name or record the loader's identity rather than relying solely on the class name.
3. **Execute lifecycle operations:** stop tasks/timers, unregister listeners/MBeans/drivers, clear caches, close loader resources, and drop strong references. Verify whether the software actually releases the old loader.
4. **Observe over a time window and multiple real GC cycles** under controlled load; collect unload logs and snapshots at least before plugin loading, after logical unloading, and after the observation period. Do not use a single `System.gc()` call as a boundary.
5. **Cross-check at least two independent sources of evidence:** unload logs naming the target class/loader; loader weak references or GC root analysis; JVM-wide statistics serve only as contextual data.
6. **If there are signs of abnormally long loader retention**, trace back from GC roots to the loader/plugin. Compare repeated load→use→dispose cycles to distinguish a legitimate long lifetime from cumulative growth.

Common HotSpot diagnostic commands while the application is still running:

```bash
jcmd
jcmd <pid> VM.classloader_stats
jcmd <pid> VM.metaspace
jcmd <pid> help
```

`jcmd` inspects snapshots; it does not "trigger class unloading." Inside containers, attaching may require matching user/JVM namespace permissions and available JDK tools; record the context along with the results.

For long-running programs, class loading information can be retrieved via `ManagementFactory.getClassLoadingMXBean()`:

- `getLoadedClassCount()`: number of classes currently loaded (snapshot).
- `getTotalLoadedClassCount()`: total classes ever loaded since JVM startup.
- `getUnloadedClassCount()`: total classes ever unloaded since JVM startup.

Do not subtract `totalLoaded - unloaded` to "identify loader X," and do not treat an upward metadata trend as a leak without controlling for class loading rate, plugin count, and GC cycles.

## 7. Why Does a Closed Plugin Still Fail to Unload?

Closing a loader does not remove **host references**. When no class unload event is seen, inspect `path to GC roots` through static caches/`Class<?>`, callbacks/listeners, `ServiceLoader` providers, thread TCCL/`ThreadLocal`, pending executor tasks, and JMX/JDBC/logging registries.

However, **the absence of an unload event does not prove a leak**: the VM may simply not have chosen to perform unloading yet. You must cross-check loader generations, event logs, and heap retaining paths across multiple operational cycles.

## 8. Conclusions to Avoid and How to State Things Accurately

| Hasty Inference | Better-Grounded Conclusion |
|---|---|
| "`System.gc()` returned, so the classes have unloaded." | "GC was requested; a class unloading event or separate reachability/loader evidence is needed." |
| "One `System.gc()` produced no event, so there is definitely a memory leak." | "No event was recorded within that observation window; inspect GC/roots and repeat." |
| "`URLClassLoader.close()` unloads classes immediately." | "`close()` closes the loader's resources; references and GC determine whether it can be reclaimed." |
| "A non-null weak reference means the JVM cannot unload it." | "The loader was still observed as reachable/uncleared at the time of reading; the cause is not yet known." |
| "`unloadedClassCount` increased, so the plugin was just unloaded." | "The JVM-wide unloaded class count increased; identify the exact class/loader via logs or additional evidence." |
| "Metaspace did not shrink, so the classes are still alive." | "Metaspace used/committed may not shrink immediately or may be offset by newly loaded classes." |

A good observation report should clearly record: **JDK/JVM, collector and flags; class name + defining loader; release actions; timestamps; number/cycles of actual GCs; `class+unload` logs; weak reference state; stats snapshots; and what remains inconclusive**.

## 9. Self-Check

1. Why can the same binary name be loaded by two loaders into two different runtime types?
2. Why are stopping plugin usage and calling `close()` not enough to confirm unloading?
3. If the unload counter increases from 100 to 105 without seeing a plugin event, what can you say?
4. If after the first `System.gc()` call `WeakReference` is still not cleared, which hypotheses should you check before saying "leak"?
5. Which evidence is more specific to the question "has `lesson.UnloadTarget` unloaded yet": general GC logs, metaspace changes, or a `class+unload` log containing the class name?

**Guided Answers:** (1) A runtime type is determined by both its name and its defining loader; (2) strong references may still retain the loader, and `close` does not unload classes; (3) you only know that 5 classes unloaded JVM-wide; (4) GC timing/type, JVM flags, strong references, stack/JIT/debugger; (5) a `class+unload` event bearing the target class name, combined with loader identification when needed.

## Standard Reference Documentation

- [Java SE 17 — `System.gc()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html): documentation clearly stating the guarantee limits of a GC request.
- [Java SE 17 — `ClassLoadingMXBean`](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ClassLoadingMXBean.html): JVM-wide loaded/unloaded counters.
- [JDK 17 — `jcmd`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): `VM.classloader_stats`, `VM.metaspace`, and HotSpot diagnostic commands.
- [Java Language Specification `12.7`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.7): unloading of classes and interfaces.
