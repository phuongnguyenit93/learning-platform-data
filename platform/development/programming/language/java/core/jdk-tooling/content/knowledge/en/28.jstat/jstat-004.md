# Reading Class Loading Statistics with jstat

Class loading statistics show how many classes the JVM has loaded and unloaded, the volume of class data processed, and the time spent on class loading and unloading operations. This data is useful when investigating slow startup, applications that continuously generate new classes, dynamically loaded plugins, hot redeployment, or suspected class loader leaks causing Metaspace growth.

In JDK 17, the primary command for this task is `jstat -class`. The output has five columns: `Loaded`, `Bytes`, `Unloaded`, `Bytes`, and `Time`. This guide explains how to take samples, read each column, distinguish cumulative counts from the number of currently loaded classes, recognize abnormal trends, and choose deeper tools when you need per-class-loader statistics.

> **Tooling note:** Oracle marks `jstat` as experimental and unsupported; its output format or options may change in future JDK releases. Always check `jstat -options` on the exact JDK you are using and avoid writing long-term parsers that depend on the output format.

## 1. What is Class Loading in the JVM?

Before reading the metrics, it helps to understand what the JVM is counting.

Class loading is the process by which the JVM finds and loads a class definition into the runtime. A class loader locates the bytecode, the JVM reads it and creates a class representation, and then links and initializes the class as needed.

The commonly referenced phases are:

1. **Loading:** locating bytecode by class name and creating a class representation object in the JVM.
2. **Linking:** verifying the bytecode (verification), preparing data structures (preparation), and resolving symbolic references (resolution).
3. **Initialization:** running static initializers and assigning initial values to static fields according to Java rules.

`jstat -class` reflects class loader activity at an aggregate statistical level. It does not display individual class names or the stack traces that requested class loading.

### 1.1. Class Loaders and Class Identity

Java has multiple types of class loaders:

- **Bootstrap class loader:** loads core Java platform classes.
- **Platform class loader:** loads modules/platform classes assigned to the platform loader.
- **Application class loader:** typically loads classes from the application classpath/module path.
- **Custom class loader:** created by the application or framework, such as a plugin loader, application server loader, or module loader.

A class's identity is not just its fully qualified name. It is tied to both the class name and the class loader that defined it. Two classes with the same name defined by two different loaders can be two distinct types; this affects casting, type compatibility, and class unloading.

Plugin frameworks, application servers, hot deployment, proxy generation, and runtime bytecode generation can create multiple class loaders or multiple class definitions throughout an application's lifecycle.

## 2. Getting the PID and Invoking jstat -class

List running JVMs:

~~~powershell
jps -l
~~~

Example:

~~~text
8120 com.example.ClassLoadingStatsTarget
9204 org.apache.catalina.startup.Bootstrap
10440 jdk.jcmd/sun.tools.jps.Jps
~~~

Use the PID of the process you want to inspect:

~~~powershell
jstat -class 8120
~~~

If you do not pass an interval and count, the tool takes one sample and exits. To observe changes over time, add an interval and sample count:

~~~powershell
jstat -class 8120 1000 5
~~~

The command above takes five samples, 1000 milliseconds (one second) apart.

You can use a time suffix:

~~~powershell
jstat -class 8120 1s 5
~~~

To monitor continuously until stopped with Ctrl+C:

~~~powershell
jstat -class 8120 1s
~~~

Run this on the same machine as the target JVM using an account with appropriate permissions. With Docker/containers, the PID seen from the host may differ from the PID inside the container; run the tool in the appropriate namespace or use the PID required by your diagnostic environment.

## 3. Output Structure of jstat -class

Sample output looks like this:

~~~text
Loaded  Bytes  Unloaded  Bytes     Time
  812   1542.3        12    18.6    0.43
  825   1568.7        12    18.6    0.44
  841   1601.2        12    18.6    0.45
  841   1601.2        12    18.6    0.45
~~~

The numbers above are illustrative examples to explain how to read the output, not fixed results of a specific program.

The five columns are:

| Column | Meaning |
|---|---|
| `Loaded` | Number of classes loaded |
| `Bytes` (after Loaded) | Kilobytes (KB) of class data loaded |
| `Unloaded` | Number of classes unloaded |
| `Bytes` (after Unloaded) | Kilobytes (KB) of class data unloaded |
| `Time` | Time spent on class loading and unloading operations |

The two `Bytes` columns have different meanings depending on their position: the first is KB loaded, and the second is KB unloaded. When reading the output, always check both the header and column position, not just the column name.

The class load/unload counters are cumulative metrics over the JVM's lifetime. They generally increase monotonically; an unchanged row across several samples simply means no activity altered those counters during that sampling interval.

## 4. Understanding Each Column

### 4.1. Loaded

`Loaded` is the number of classes that have been loaded. This is a cumulative counter, not the number of classes currently present at the exact time of sampling.

Example:

~~~text
Loaded
812
825
841
~~~

The number of loaded classes increased from 812 to 841 across the samples, indicating additional class loading activity during the observation window.

An increasing `Loaded` count is normal during startup, warm-up, framework initialization, plugin loading, or when an application generates dynamic proxies/bytecode. This number increasing on its own does not prove a memory leak.

### 4.2. Loaded Bytes

The `Bytes` column immediately following `Loaded` is the number of KB of class data loaded.

Example:

~~~text
Loaded  Bytes
812     1542.3
825     1568.7
841     1601.2
~~~

Both the number of classes and the KB loaded increased. This indicates the JVM continued loading classes and their corresponding class data.

This value is neither total heap used nor a direct measurement of committed Metaspace. It describes the amount of class-loading-related data according to the tool's internal counters.

### 4.3. Unloaded

`Unloaded` is the number of classes unloaded since the JVM started.

Example:

~~~text
Unloaded
12
12
15
~~~

The counter increasing from 12 to 15 indicates that three more classes were unloaded during the observation window.

A class can typically only be unloaded when the class loader that defined it is no longer reachable and the JVM performs an appropriate collection cycle. If the class loader is still retained by a static field, thread, `ThreadLocal`, cache, MBean, callback, or another live object, classes from that loader may not be unloaded.

Not all classes are unloaded during a JVM's lifetime. Core platform classes loaded by the bootstrap loader typically remain for the entire lifetime of the process.

### 4.4. Unloaded Bytes

The second `Bytes` column is the number of KB of class data unloaded.

If `Unloaded` increases while `Bytes` changes very little, the unloaded classes may be small. If both increase, the JVM unloaded additional classes and their corresponding class data.

Do not compare the `Bytes` column alone to conclude that Metaspace shrank by that exact amount. Metaspace has its own allocation, chunking, fragmentation, and reclamation mechanisms; `jstat -class` metrics do not replace memory pool statistics.

### 4.5. Time

`Time` represents the time the JVM spent on class loading and unloading operations.

This is the duration of class loading/unloading activity, not the sampling interval you passed at the end of the command. `-t` is a separate option that adds a column showing elapsed time since the JVM started.

If `Time` increases rapidly alongside `Loaded` or `Unloaded`, heavier class loading/unloading activity is occurring. If `Time` increases while the class count rises only slightly, inspect the types of classes being loaded, the cost of reading/verifying/linking, and overall system load. You cannot draw conclusions from a single column; compare multiple samples and cross-reference startup logs or JFR.

## 5. Reading Trends Across Multiple Samples

The most important aspect of `jstat -class` is the trend, not any single number.

### 5.1. Normal Startup

Example:

~~~text
Loaded  Bytes  Unloaded  Bytes   Time
  420   780.0         0     0.0   0.12
  610  1120.5         0     0.0   0.19
  790  1460.2         0     0.0   0.27
  805  1482.4         0     0.0   0.28
  805  1482.4         0     0.0   0.28
~~~

`Loaded` rises sharply at first and then stabilizes. This is typically expected as the application loads frameworks, libraries, and application classes during startup/warm-up.

### 5.2. Application Continuously Loading Dynamic Classes

Example:

~~~text
Loaded  Bytes  Unloaded  Bytes   Time
  805  1482.4         0     0.0   0.28
  910  1660.8         0     0.0   0.35
 1040  1912.6         0     0.0   0.43
 1195  2204.1         0     0.0   0.55
~~~

`Loaded` and `Bytes` keep rising while `Unloaded` stays flat. The application may be loading plugins, generating proxies, loading modules per request, or creating new class loaders. If this is intentional behavior, the trend may be normal; if the metrics keep climbing indefinitely after warm-up, inspect the class loader lifecycle.

### 5.3. Class Unloading Occurring

Example:

~~~text
Loaded  Bytes  Unloaded  Bytes   Time
 1200  2210.0        10    18.0   0.60
 1300  2400.0        10    18.0   0.68
 1315  2430.0        25    42.0   0.74
 1315  2430.0        25    42.0   0.74
~~~

`Unloaded` increased from 10 to 25, showing that classes were unloaded during that period. This can happen when a custom class loader becomes unreachable and the JVM performs class unloading during an appropriate GC cycle.

### 5.4. Signs That Warrant Investigating a Class Loader Leak

A notable pattern:

- After each redeployment or new plugin creation, `Loaded` keeps increasing.
- `Unloaded` barely increases across multiple cycles.
- `VM.classloader_stats` shows many old loaders still present.
- Metaspace used steadily climbs and does not return to a stable baseline after collection cycles.
- A heap dump shows old loaders still referenced by a static cache, thread, `ThreadLocal`, MBean, or registry.

This combination of signals is much stronger than just seeing `Loaded` increase. Investigate what is holding the references before concluding there is a leak.

## 6. Distinguishing Total Loaded from Currently Loaded Classes

`jstat -class` focuses on cumulative load/unload counts. When you need to know how many classes are currently loaded at the time of inspection, use the Java Management API `ClassLoadingMXBean`.

Three key values:

- `getTotalLoadedClassCount()`: total number of classes loaded since the JVM started.
- `getLoadedClassCount()`: number of classes currently loaded.
- `getUnloadedClassCount()`: total number of classes unloaded since the JVM started.

Within the same JVM and under the same counter definitions, total loaded minus total unloaded corresponds to the number of currently loaded classes. When you need the current count, call `getLoadedClassCount()` directly rather than deriving it from stale output.

## 7. Java 17+ Example: Reading ClassLoadingMXBean

Create `ClassLoadingStatsTarget.java`:

~~~java
import java.lang.management.ClassLoadingMXBean;
import java.lang.management.ManagementFactory;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.util.concurrent.CountDownLatch;

public final class ClassLoadingStatsTarget {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.err.println("Usage: java ClassLoadingStatsTarget <plugin.jar>");
            return;
        }

        ClassLoadingMXBean bean =
                ManagementFactory.getClassLoadingMXBean();

        printStats("before", bean);

        Path pluginPath = Path.of(args[0]).toAbsolutePath();
        URL pluginUrl = pluginPath.toUri().toURL();

        try (URLClassLoader loader = new URLClassLoader(
                new URL[] { pluginUrl },
                ClassLoader.getPlatformClassLoader())) {

            Class<?> pluginClass = Class.forName(
                    "demo.PluginMarker",
                    true,
                    loader
            );

            System.out.println("Loaded plugin class: " + pluginClass.getName());
        }

        printStats("after", bean);
        System.out.println("PID: " + ProcessHandle.current().pid());
        System.out.println("READY - use jstat -class with this PID.");

        new CountDownLatch(1).await();
    }

    private static void printStats(
            String label,
            ClassLoadingMXBean bean
    ) {
        System.out.printf(
                "%s: current=%d total=%d unloaded=%d%n",
                label,
                bean.getLoadedClassCount(),
                bean.getTotalLoadedClassCount(),
                bean.getUnloadedClassCount()
        );
    }
}
~~~

Create the plugin class in `plugin-src/demo/PluginMarker.java`:

~~~java
package demo;

public final class PluginMarker {
    public String message() {
        return "Plugin loaded";
    }
}
~~~

Compile the plugin and package it into a JAR:

~~~powershell
javac -d plugin-classes plugin-src/demo/PluginMarker.java
jar --create --file plugin.jar -C plugin-classes .
~~~

Compile the target application:

~~~powershell
javac ClassLoadingStatsTarget.java
~~~

Run the application:

~~~powershell
java ClassLoadingStatsTarget plugin.jar
~~~

The application prints the current loaded class count, total loaded classes, and total unloaded classes before and after creating the `URLClassLoader`. Exact numeric values depend on the JDK and runtime classes already loaded; the line `Loaded plugin class: demo.PluginMarker` confirms the plugin class was found and loaded successfully.

Keep the process running. Open a second terminal and use the printed PID to collect statistics:

~~~powershell
jstat -class <PID> 1000 5
~~~

If needed, cross-check with:

~~~powershell
jcmd <PID> VM.classloader_stats
~~~

Stop the test program with Ctrl+C in the first terminal. This example demonstrates loading a class with a custom loader; class unloading after the loader becomes unreferenced is not guaranteed to happen immediately.

## 8. Useful Sampling Options

### 8.1. Taking a Single Sample

~~~powershell
jstat -class 8120
~~~

Use this for a quick point-in-time check.

### 8.2. Taking Multiple Samples with an Interval

~~~powershell
jstat -class 8120 1s 10
~~~

Takes 10 samples, one second apart. Useful for observing startup or plugin loading.

### 8.3. Adding the JVM Timestamp

~~~powershell
jstat -class -t 8120 1s 10
~~~

A `Timestamp` column is prepended to the output, showing the elapsed seconds since the target JVM started. This is not wall-clock date/time.

### 8.4. Repeating the Header

~~~powershell
jstat -class -h 5 8120 1s 20
~~~

Reprints the header every five data rows, making long outputs easier to read.

### 8.5. Combining Timestamp and Header

~~~powershell
jstat -class -t -h 5 8120 1s 20
~~~

Note: the stat option `-class` must precede output options such as `-t` and `-h`.

### 8.6. Listing Available Stat Options

~~~powershell
jstat -options
~~~

This command lists the statistics options supported by the current JDK/platform. Besides `-class`, useful options include:

- `-compiler`: JIT compilation statistics.
- `-gc`: capacity and utilization of heap regions, Metaspace, and GC metrics.
- `-gcutil`: utilization percentages of memory spaces and GC counters.
- `-gcmetacapacity`: Metaspace capacity statistics.
- `-printcompilation`: information on the most recently compiled methods.

## 9. How Class Loading Statistics Differ from Metaspace Statistics

Class metadata is stored in Metaspace in modern HotSpot JVMs. However, do not confuse the `Bytes` column in `jstat -class` with used Metaspace capacity.

| Metric | Meaning |
|---|---|
| `jstat -class` Loaded/Unloaded Bytes | KB of class data loaded or unloaded per class loading counters |
| `jstat -gc` MC/MU | Metaspace committed size and utilization |
| `jstat -gc` CCSC/CCSU | Compressed class space committed and used |
| `jstat -gcmetacapacity` | Capacity of Metaspace and compressed class space |
| `jcmd VM.classloader_stats` | Per-ClassLoader statistics |

If `Loaded Bytes` increases, it indicates increased class loading activity and class data. To see how much Metaspace is currently used, read `MU` in `jstat -gc` or the corresponding Metaspace metrics.

Example:

~~~powershell
jstat -gc 8120 1s 5
jstat -gcmetacapacity 8120 1s 5
~~~

`MU` is Metaspace utilization in KB in `-gc` output; `MC` is committed size. Committed does not mean used. Metaspace can retain committed regions for reuse even after some classes have been unloaded.

## 10. Viewing Per-ClassLoader Statistics

`jstat -class` only provides JVM-wide aggregates. When you need to know which loader is holding classes, use the `jcmd` diagnostic command:

~~~powershell
jcmd 8120 VM.classloader_stats
~~~

This command prints statistics for all ClassLoaders. It is the logical next step when you suspect plugin loaders, application server loaders, or custom loaders are accumulating over time.

You can also use `jmap -clstats` to retrieve class loader statistics:

~~~powershell
jmap -clstats 8120
~~~

In JDK 17, the Oracle Troubleshooting Guide describes using `jcmd <PID> VM.classloader_stats` and `jmap -clstats <PID>` to investigate class loader and Metaspace-related memory leaks.

If you need to inspect the class hierarchy or specific classes, check the available diagnostic commands:

~~~powershell
jcmd 8120 help
jcmd 8120 help VM.classloader_stats
~~~

Not every command has the same options across all JDK versions. Always check `help` on the target JVM.

## 11. Analyzing Class Loader Leaks

Class loader leaks typically occur when an application creates new loaders while old loaders remain referenced after a module/plugin/redeploy finishes.

Common causes include:

- Static collections holding classes, instances, or the `ClassLoader` of an old application.
- Long-lived threads retaining a context class loader pointing to an old loader.
- `ThreadLocal` values not removed on reused thread pool threads.
- MBeans or registries retaining objects belonging to an undeployed application.
- JDBC drivers, logging frameworks, callbacks, or shutdown hooks not deregistered.
- Caches or listeners holding class instances from an old loader.
- Plugin managers closing a `URLClassLoader` while still holding references to the loader or objects defined by it.

Investigation steps:

1. Capture `jstat -class` after the application stabilizes.
2. Perform a deploy/undeploy or plugin load/unload cycle.
3. Capture `Loaded`, `Unloaded`, and Metaspace again.
4. Repeat for several cycles to see if there is an accumulating trend.
5. Run `jcmd PID VM.classloader_stats` to identify loaders and their class counts.
6. If needed, take a heap dump and trace reference paths keeping old class loaders alive.
7. Check threads, `ThreadLocal`, static caches, MBeans, driver registries, and callbacks.

If `Loaded` increases after each cycle while `Unloaded` does not, that is a signal to investigate, not a final verdict. Confirm with class loader stats and heap references before modifying code.

## 12. Distinguishing Class Loading from JIT Compilation

Class loading and JIT compilation are two separate activities:

- **Class loading:** loading class definitions into the JVM.
- **JIT compilation:** compiling method bytecode into machine code for more efficient execution.

A class can be loaded without its methods being JIT-compiled yet. Conversely, the JIT compiler can compile methods in classes that were loaded long ago.

Use:

~~~powershell
jstat -class 8120
jstat -compiler 8120
~~~

`-class` tracks class loader activity; `-compiler` tracks compilation tasks, failures, and the most recently compiled method. Do not use `Loaded` to conclude how many methods have been JIT-compiled.

## 13. Common Errors When Reading jstat -class

| Symptom | Common Cause | Resolution |
|---|---|---|
| `jstat is not recognized` | JDK is not installed or JDK `bin` is not in PATH | Install an appropriate JDK or invoke `jstat` using its full path |
| `Could not find any processes matching` | Wrong PID/VMID or the JVM has stopped | Use `jps -l` or OS tools to find the correct PID |
| Cannot connect to target JVM | Different user, container namespace, or perfdata/attach restrictions | Use the same account and environment as the target JVM |
| `-class` does not produce expected output | Wrong option order or target VM lacks matching instrumentation | Check `jstat -help`, `jstat -options`, and JDK version |
| `Loaded` increases continuously | Startup, plugins, proxy generation, or newly created class loaders | Compare after warm-up and across multiple cycles |
| `Unloaded` stays at 0 | No class loaders became eligible for unloading during observation | Check loader lifecycle; do not assume a leak by default |
| `Bytes` increases without matching Metaspace growth | Class bytes counter and Metaspace used measure different aspects | Cross-check `jstat -gc`, `-gcmetacapacity`, and `VM.classloader_stats` |
| Metaspace grows while `Loaded` is stable | Old loaders/class metadata may still be retained or other allocations grew | Inspect classloader stats and heap dump |
| Metrics remain flat | Application has stabilized with no class loading/unloading in the interval | Sample during startup, deployment, or class-generating workloads |

## 14. Notes on Reliability and Operational Impact

`jstat` reads HotSpot VM instrumentation data. It is a quick monitoring tool, not a stable management interface for applications.

- Output format may change across JDK releases; avoid building long-term dashboard parsers based on fixed columns and spacing without controlling the JDK version.
- A very short `interval` can generate excessive output without adding meaningful diagnostic value.
- PIDs can change after a JVM restart.
- Use the same environment/JDK matching the target process to avoid tool and permission mismatches.
- Never use a single sample to conclude a class loader leak.
- When collecting per-loader statistics, remember that class loader stats and heap dumps can expose class names, application structure, and internal implementation details; restrict access to output files.

For long-term monitoring, consider JMX `ClassLoadingMXBean`, JFR class loading events, APM, or metrics designed for production. Use `jstat` for live checks and trend cross-referencing during investigations.

## 15. Class Loading Statistics Checklist

- [ ] Identified the correct JVM PID.
- [ ] Ran `jstat -class` and read all five columns correctly.
- [ ] Distinguished the two `Bytes` columns: KB loaded vs. KB unloaded.
- [ ] Understood that `Loaded` and `Unloaded` are cumulative counters.
- [ ] Did not confuse total loaded classes with currently loaded classes.
- [ ] Collected multiple samples with an appropriate interval.
- [ ] Used `-t` when JVM uptime timestamps were needed.
- [ ] Checked trends after startup/warm-up or after redeployment.
- [ ] Did not conclude a memory leak solely from `Loaded` increasing or `Unloaded` being 0.
- [ ] Distinguished class loading bytes from Metaspace used/committed.
- [ ] Used `ClassLoadingMXBean` when current loaded class count was needed.
- [ ] Used `jcmd VM.classloader_stats` or `jmap -clstats` when per-loader stats were needed.
- [ ] Checked classloader lifecycle, `ThreadLocal`, threads, static caches, and registries if a leak was suspected.
- [ ] Kept in mind that `jstat` is experimental and unsupported, avoiding reliance on a fixed output format.

`jstat -class` is a fast way to observe class loading and unloading activity in a JVM. Read `Loaded`, `Unloaded`, the two KB columns, and `Time` across a series of samples to spot trends after startup or redeployment. When you need the current class count, use `ClassLoadingMXBean`; when you need to find which loader is holding classes and affecting Metaspace, use `jcmd VM.classloader_stats` or `jmap -clstats`. Only conclude a class loader leak after confirming that old loaders are still being held by references.

## References

- Oracle, The jstat Command, JDK 17: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jstat.html
- Oracle, The jcmd Command, JDK 17: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html
- Oracle, Troubleshooting Memory Leaks, JDK 17: https://docs.oracle.com/en/java/javase/17/troubleshoot/troubleshooting-memory-leaks.html
- Oracle, ClassLoadingMXBean, Java SE 17 API: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ClassLoadingMXBean.html
