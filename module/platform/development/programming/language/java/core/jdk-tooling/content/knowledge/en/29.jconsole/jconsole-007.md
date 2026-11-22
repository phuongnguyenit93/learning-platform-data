# Class Tab in JConsole

The **Class tab** (displayed as **Classes** in the JConsole UI) is used to monitor class loading and unloading activity in a Java Virtual Machine. This tab displays the number of currently loaded classes, the total number of classes loaded since the JVM started, and the total number of classes unloaded.

It is a useful high-level monitoring screen when an application uses many frameworks, dynamic proxies, plugins, hot reload, or module redeployment within the same JVM. The chart can help identify continuously increasing class loading or class unloading that is not occurring as expected. However, these metrics are only aggregate counters; they do not identify specific classes, which class loader is holding a class, or which objects are preventing a class loader from being garbage-collected.

## 1. What Does the Class Tab Display?

After JConsole successfully connects to a JVM, the interface provides the Overview, Memory, Threads, Classes, VM, and MBeans tabs. Select **Classes** to view class loading details.

The tab features the **Number of Loaded Classes** chart with two lines:

| Line | Color in JConsole | Meaning |
|---|---|---|
| Total Loaded | Red | Total number of classes loaded since the JVM started, including classes that were later unloaded |
| Loaded | Blue | Number of classes currently loaded in the JVM |

The **Details** section below the chart displays three metrics:

- **Current classes loaded:** the number of classes currently loaded.
- **Total classes loaded:** the total number of classes loaded since the JVM started, including unloaded classes.
- **Total classes unloaded:** the total number of classes unloaded from the JVM since startup.

The red line is a cumulative counter: it increases when new classes are loaded and does not decrease when classes are unloaded. The blue line represents the current number of loaded classes, so it can go up or down. When the JVM is neither loading new classes nor unloading existing ones, both lines may stay flat.

JConsole also provides a **Verbose Output** checkbox in the upper-right corner. Enabling this option turns on verbose class-loading tracing in the target JVM; this is a JVM-wide state change, not just a change to how the chart is drawn.

## 2. Where Do the Three Metrics Come From?

JConsole uses JMX and the JVM's platform MXBeans. The Class tab is backed by the **java.lang.management.ClassLoadingMXBean** interface.

This MXBean has a single instance per JVM and can be obtained in a Java program with:

~~~java
ManagementFactory.getClassLoadingMXBean()
~~~

It is also registered in the platform MBean Server with the ObjectName:

~~~text
java.lang:type=ClassLoading
~~~

Key methods:

| Method | Return Value | Meaning |
|---|---|---|
| getLoadedClassCount() | int | Number of classes currently loaded |
| getTotalLoadedClassCount() | long | Total number of classes loaded since the JVM started |
| getUnloadedClassCount() | long | Total number of classes unloaded since the JVM started |
| isVerbose() | boolean | Checks whether verbose class-loading tracing is enabled or disabled |
| setVerbose(boolean) | void | Enables or disables verbose class-loading tracing |

These three counters are JVM-wide. They do not only count classes in the application's packages; library, framework, and JDK classes are counted as well.

A class defined by two different class loaders is two distinct classes in the JVM, even if they share the same binary name. Therefore, plugin-based or container applications can have multiple definitions of the same class name.

### Distinguishing Total Classes from Current Classes

Hypothetical example:

| Point in Time | Current loaded | Total loaded | Total unloaded |
|---|---:|---:|---:|
| After startup | 5,000 | 5,000 | 0 |
| After loading plugin | 5,400 | 5,400 | 0 |
| After unloading plugin and reclaiming class loader | 5,050 | 5,400 | 350 |
| After loading new plugin version | 5,430 | 5,780 | 350 |

The numbers above only illustrate how to read the metrics. They are not benchmarks or results from a real application.

In this example, the total number of loaded classes continues to rise because the JVM loaded additional new classes. The current class count drops after the old class loader is reclaimed and its classes are unloaded. When the new plugin is loaded, both current and total counts rise again.

## 3. Opening JConsole and Connecting to an Application

JConsole is located in the JDK's `bin` directory. Check your JDK first:

~~~bash
java --version
jconsole -help
~~~

### Local Connection

Open the process selection window:

~~~bash
jconsole
~~~

Select the Java application from the Local Process list and click Connect. The local list typically shows only JVMs observable under the same user ID as JConsole.

If you already know the application's PID, you can connect directly:

~~~bash
jconsole 12345
~~~

Replace `12345` with the actual PID. The target application and JConsole must run under the same user ID. The JVM must support attach and allow the management agent to be enabled; a non-attachable process may not accept connections.

You can find the PID using:

~~~bash
jps -l
~~~

Or use an OS process tool. Always verify the target process before connecting; PIDs can be reused after an application exits.

### Remote Connection

To connect to a JMX agent on another machine:

~~~bash
jconsole app-host.example:7091
~~~

The host and port must match the JMX agent configured when the target JVM started. You can also connect using a JMX service URL via the Remote Process dialog.

Remote JMX must be configured and secured according to operational policy: enable authentication, use TLS where appropriate, restrict firewall access, and allow access only from management networks. Never expose an unauthenticated JMX endpoint to the Internet or untrusted networks.

### Choosing the Update Interval

By default, JConsole updates data every 4 seconds. You can change this with:

~~~bash
jconsole -interval=2 12345
~~~

The command above requests updates roughly every 2 seconds. A shorter interval makes the chart more responsive but increases query frequency and management traffic. It is still periodic sampling, not a recording of every class load/unload event.

### Selecting the Classes Tab

After connecting:

1. Select the **Classes** tab.
2. Observe the red Total Loaded line and the blue Loaded line.
3. Read the three numbers—Current classes loaded, Total classes loaded, and Total classes unloaded—under Details.
4. Choose an appropriate Time Range to inspect the time window under investigation.
5. If you need to save the data, right-click the chart and select **Save data as...** to export a CSV file.

The CSV contains a timestamp column and the chart's data series, which can be opened in a spreadsheet to compare time windows.

## 4. How to Interpret Trends on the Chart

Do not judge based on a single data point. Observe the chart across startup, warm-up, steady load, redeployments, or configuration changes.

### Case A: Class count rises at startup and then stabilizes

This is usually normal behavior. The JVM and frameworks load classes during application startup, dependency initialization, or first-request handling. After the warm-up phase, the current class count may level off.

There is no need to force the red and blue lines to be flat from the very first second.

### Case B: Total Loaded increases while Current Loaded remains nearly stable

This indicates that the JVM continues loading new classes while some older classes are unloaded, or that the current class count changes little because the two trends offset each other.

Possible causes include:

- Dynamically generated proxies or classes.
- Frameworks loading implementations on demand.
- Plugins being loaded and unloaded as part of their lifecycle.
- Hot reload or module redeployment.
- Multiple class loaders defining classes with the same name.

This is not automatically a bug. Determine whether the new class loading aligns with expected business activity.

### Case C: Current Loaded rises continuously without dropping

This is a sign worth investigating if the trend persists after warm-up or repeats after every redeployment.

Possible causes include:

- The application generates new classes or proxies without bound.
- Plugins are loaded multiple times while old class loaders are still retained.
- A `Thread`, `ThreadLocal`, or static registry holds a reference to the class loader.
- A framework creates a new class loader on each reload without releasing the old loader.
- A cache or registry holds objects that have back-references to the class loader.

The Class tab only shows that the current class count is increasing. It does not prove that the root cause is a class loader leak.

### Case D: Total Unloaded increases and Current Loaded decreases

This indicates that the JVM has unloaded classes. For classes defined by an application or plugin, unloading can usually occur only when their defining class loader is no longer kept alive and the JVM performs an appropriate collection cycle.

A class loader becoming unreachable does not mean its classes are unloaded immediately. Collection timing depends on the garbage collector, configuration, and JVM implementation. Calling `System.gc()` does not guarantee that classes will be unloaded either.

### Case E: Class count spikes suddenly

Possible reasons include:

- A large module being initialized for the first time.
- A new plugin or framework being loaded.
- A redeployment or reload.
- A feature generating many proxies or generated classes.
- JConsole attaching to the JVM and enabling the management agent, causing the JVM to load additional management classes.

Correlate the timing with deployments, application logs, plugin activity, and configuration changes before concluding there is an issue.

## 5. How Do Class Loading and Class Unloading Work?

The JVM loads classes through class loaders. When the application references a class for the first time or a framework actively loads a class, the JVM may define the class in the corresponding class loader.

A class's identity is determined by its binary name and its defining class loader. Consequently, two classes with the same name defined by two different class loaders are not the same class under JVM identity rules.

### Class Unloading Depends on the Class Loader Lifecycle

In Java, classes cannot be directly unloaded by an application through a normal API call. The JVM can unload classes when their defining class loader becomes eligible for garbage collection.

For example, a plugin is loaded using a dedicated `URLClassLoader`. When unloading the plugin, the application must close the loader if needed, clear references to the loader, stop threads belonging to the plugin, and release registries/caches. If an external object still holds a reference to the class loader, the loader may remain reachable and its classes will not be unloaded.

### References That Commonly Retain a Class Loader Unintentionally

- A static field in a class loaded by a longer-lived class loader.
- A `Thread` or `ThreadLocal` still holding a plugin's class or instance.
- An executor, timer, or scheduler still running plugin tasks.
- A thread's context class loader that was not restored.
- A JDBC driver or logging provider registered without being deregistered.
- An MBean, listener, callback, or shutdown hook still registered.
- A cache, reflection metadata, or framework registry retaining a class or loader.

The Class tab cannot point out these references. You need class loader statistics, heap dumps, JFR, or GC root analysis to find the cause.

## 6. Using Verbose Output Properly

The **Verbose Output** checkbox on the Classes tab enables verbose class-loading tracing for the target JVM.

In the Java API, the corresponding functionality is:

~~~java
ClassLoadingMXBean bean =
        ManagementFactory.getClassLoadingMXBean();

bean.setVerbose(true);
~~~

Checking the status:

~~~java
boolean enabled = bean.isVerbose();
~~~

Disabling it again:

~~~java
bean.setVerbose(false);
~~~

When enabled, the JVM typically emits a message whenever a class is loaded. The format and output stream depend on the implementation; typically the output is written to the JVM's standard output.

### Why Shouldn't It Be Left Enabled in Production?

- A large application can load a very large number of classes.
- Logs can grow rapidly and consume significant disk space.
- Heavy logging can increase I/O and overhead.
- Class loading logs may expose packages, paths, or internal structure.
- Verbose tracing is a JVM-wide change affecting every component in the process.

Enable it only for the duration of the investigation, identify where the output is written, bound disk usage, and turn it off after collecting sufficient evidence.

An alternative is enabling unified logging at JVM startup:

~~~bash
java -Xlog:class+load=info -jar app.jar
~~~

To trace class unloading:

~~~bash
java -Xlog:class+unload=info -jar app.jar
~~~

These options write class load or unload events to the configured logging output. When writing to a file, configure appropriate log rotation and retention. Enable only the necessary log level because the output can be very large.

## 7. Reading ClassLoadingMXBean in Java

JConsole uses the same metrics that a Java program can access via JMX. The following Java 17+ example prints the current class count, total loaded classes, and unloaded classes every 5 seconds.

Create **ClassTabDemo.java**:

~~~java
import java.lang.management.ClassLoadingMXBean;
import java.lang.management.ManagementFactory;

public final class ClassTabDemo {
    public static void main(String[] args) throws InterruptedException {
        ClassLoadingMXBean bean =
                ManagementFactory.getClassLoadingMXBean();

        System.out.println("READY");

        while (true) {
            System.out.printf(
                    "current=%d total=%d unloaded=%d%n",
                    bean.getLoadedClassCount(),
                    bean.getTotalLoadedClassCount(),
                    bean.getUnloadedClassCount()
            );

            Thread.sleep(5_000);
        }
    }
}
~~~

Compile:

~~~bash
javac --release 17 ClassTabDemo.java
~~~

Run:

~~~bash
java ClassTabDemo
~~~

The output looks like:

~~~text
READY
current=... total=... unloaded=...
current=... total=... unloaded=...
~~~

The numeric values vary depending on the JDK, startup timing, and loaded classes. The ellipsis in the output above represents runtime values, not literal characters printed by the program.

While the program is still running, open another terminal:

~~~bash
jps -l
~~~

Find the PID of `ClassTabDemo` and launch JConsole:

~~~bash
jconsole <pid>
~~~

Select the **Classes** tab to view the chart. Compare the metrics in JConsole with the program's output lines. When finished, press `Ctrl+C` in the terminal running `ClassTabDemo` to stop the lab.

### Why Are the Numbers in the Lab Not Fixed?

The JVM loads different classes depending on the version, startup path, and runtime environment. When JConsole connects, the management agent may also be dynamically enabled if the JVM supports attach; this operation can cause additional management classes to be loaded. Therefore, do not use a fixed number as expected output across all machines.

## 8. Viewing ClassLoadingMXBean in the MBeans Tab

In addition to the Classes tab, you can view the same attributes in the MBeans tab:

1. Select **MBeans**.
2. Expand the **java.lang** domain.
3. Select the **ClassLoading** type.
4. Inspect the `LoadedClassCount`, `TotalLoadedClassCount`, `UnloadedClassCount`, and `Verbose` attributes.

These attributes correspond to the methods of `ClassLoadingMXBean`. `Verbose` is a writable attribute; when modified, JConsole invokes the mechanism to enable/disable verbose class-loading tracing on the target JVM.

The MBeans tab provides broader access to platform MXBeans and application MBeans. Modify attributes only when you clearly understand the impact; do not use JConsole for ad-hoc experimentation in production.

## 9. Limitations of the Class Tab

The Class tab is a view for observing class counts, not a class loader analyzer or profiler.

It does not directly show:

- Individual loaded class names.
- The defining class loader for each class.
- Parent/child relationships between class loaders.
- The source JAR or module of each class.
- Metadata bytes per class.
- Retained memory held by a class loader.
- Objects or references preventing a class loader from being collected.
- Stack traces at the time a class was loaded.
- Specific reasons why a class was unloaded or not unloaded.

The Class tab also does not directly measure Metaspace usage. To inspect memory pools, switch to the Memory tab; to identify specific class loaders and classes, use other diagnostic tools.

### Data Is Sampled

The chart updates according to JConsole's polling interval. A very brief burst of loading/unloading can occur between two samples. The plotted lines show trends, not an exact timeline of individual events.

For detailed event data, use unified logging or JFR. Do not use a 4-second sampled line to infer the exact moment a class was loaded.

### You Cannot Conclude a Memory Leak from a Single Chart

An increase in Current Loaded may be due to startup, warm-up, or legitimate framework behavior. An increase in Total Loaded is normal when an application continues loading classes dynamically. A class loader leak is only a hypothesis when the current class count rises persistently under the same workload and does not drop after unload/redeploy cycles.

Combine these metrics with class loader statistics, heap dumps, GC roots, JFR, and application lifecycle knowledge.

## 10. Diagnosing Class Loaders with jcmd

When the Class tab shows an unusual trend, use `jcmd` to inspect further.

List JVMs:

~~~bash
jcmd -l
~~~

View statistics for all class loaders:

~~~bash
jcmd <pid> VM.classloader_stats
~~~

This command reports the JVM's class loader statistics, which is useful when you suspect the number of loaders is growing or old loaders remain alive.

View the class hierarchy tree:

~~~bash
jcmd <pid> VM.class_hierarchy
~~~

This command prints the list of loaded classes in a hierarchical structure along with their corresponding class loader information. Output can be large when an application loads many classes; check the command's help and impact before running it in production.

View help from the target JVM:

~~~bash
jcmd <pid> help VM.classloader_stats
jcmd <pid> help VM.class_hierarchy
~~~

In OpenJDK 24.0.2 (tested), `VM.classloader_stats` has Low impact; `VM.class_hierarchy` has Medium impact depending on the number of loaded classes. Impact levels may vary by runtime.

## 11. Using JFR When Detailed Class Loading History Is Needed

Java Flight Recorder can collect events for class loading, class unloading, class loader statistics, and class loading statistics.

Start a time-bounded recording:

~~~bash
jcmd <pid> JFR.start name=class-audit settings=profile class-loading=true duration=60s filename=class-audit.jfr
~~~

This command records for 60 seconds and saves the file `class-audit.jfr`. A `profile` recording may have higher overhead than `default`; use it only for the necessary duration and evaluate its impact before running in production.

Read the relevant events:

~~~bash
jfr print --events jdk.ClassLoad,jdk.ClassUnload,jdk.ClassLoaderStatistics,jdk.ClassLoadingStatistics class-audit.jfr
~~~

Event names can be verified in the JDK's metadata:

~~~bash
jfr metadata
~~~

JFR provides timestamps and event details that are far more useful than the aggregate counters on the Class tab. However, the recorded event set depends on the recording settings; if an event is not enabled, the file will not contain that data.

## 12. Combining the Class Tab with Other JConsole Tabs

Class loading is often tied to memory, threads, and application activity. Use other tabs to test hypotheses:

| Tab | Data | How to Combine with Classes |
|---|---|---|
| Overview | CPU, memory, thread, and class summary | Check whether class count increases coincide with CPU/memory spikes |
| Memory | Heap, non-heap, and memory pools | Check Metaspace at the same time class count rises |
| Threads | Thread count and stack traces | Find threads or plugin tasks still running after redeploy |
| Classes | Current/total/unloaded class counts | Identify class loading trends |
| VM | JVM version, arguments, uptime, and summary | Cross-reference runtime, flags, and uptime |
| MBeans | Platform/application MXBeans | Read attributes and perform deeper management operations |

For example, if current loaded rises after every redeploy while Metaspace grows and class loader statistics show many old loaders, investigate plugin lifecycle, threads, `ThreadLocal`s, and registries.

If current loaded rises while Metaspace stays stable and the trend stops after warm-up, it may simply be normal class loading activity. Do not draw conclusions from a single metric.

## 13. Security and Operational Impact

JConsole can connect to and manage a JVM, not just read charts. Some operations via MBeans can modify attributes or invoke operations on the JVM or application.

Guidelines:

- Grant JMX access only to approved operations accounts.
- For remote JMX, enable authentication and TLS according to policy.
- Restrict ports using firewalls and network segmentation.
- Do not expose unauthenticated management endpoints on public networks.
- Avoid enabling verbose class loading in production.
- Store CSV exports and logs in locations with appropriate access controls.
- Do not include command lines, paths, or sensitive information in public reports.
- Close the JConsole connection when finished.
- Prefer running JConsole on a separate administration host when monitoring production.

Oracle notes that JConsole consumes significant resources; local monitoring is useful for development/prototyping but is not recommended for production. Remote monitoring separates the JConsole UI load from the machine running the application.

## 14. Common Issues

### Process Not Visible in Local Process

Verify that JConsole and the target JVM run under the same user ID. Confirm that the process is still running, the JVM supports attach, and the management agent can be enabled. If the process is not attachable and the agent was not enabled at startup, JConsole may not be able to connect.

### Classes Tab Shows No Data or Does Not Update

Verify that the JMX connection is still active, the JVM has not exited, and the management agent has not been disconnected. Wait at least a few update intervals. Check the MBeans tab to see if the `java.lang` domain and `ClassLoading` type are present.

### Current Loaded Increases Without Any Unloading

The application may not be unloading classes yet, the class loader may still be reachable, or the JVM may not have performed a collection cycle. Check class loader statistics, JFR, and plugin lifecycle. Do not force `System.gc()` and draw conclusions if the class count does not drop immediately.

### Total Loaded Increases While Current Loaded Stays Flat

This may be class churn: the JVM is loading new classes while unloading old ones. Check plugins, proxies, redeployments, and framework dynamic loading.

### Verbose Output Does Not Appear in JConsole

The checkbox enables tracing on the target JVM; the output stream depends on the implementation and is usually written to the target process's output/log. Check the application logs and ensure the user has read permissions. Disable verbose mode when no longer needed.

### Remote Connection Fails

Check the host, port, JMX agent, firewall, DNS, authentication, and TLS. Do not disable authentication or open public ports just to quickly work around a connection error.

### JConsole Slows Down the Application

JConsole has its own overhead, and attaching may enable the management agent or load additional classes. Reduce the polling frequency, limit observation duration, and switch to appropriate JFR/JMX monitoring for long-term collection.

## 15. Recommended Class Loading Investigation Workflow

1. Record the JDK vendor/version, JVM uptime, PID, and observation start time.
2. Connect JConsole using an account with appropriate permissions.
3. Select Classes and observe Total Loaded, Current Loaded, and Total Unloaded together.
4. Save a CSV if you need to compare time windows.
5. Correlate class count increases with startup, warm-up, redeployments, and plugin activity.
6. If Current Loaded increases persistently, check the Memory tab and Metaspace.
7. Run `jcmd VM.classloader_stats` to identify abnormal loaders.
8. Use `VM.class_hierarchy` or JFR if more detail is needed.
9. Inspect threads, `ThreadLocal`s, static registries, listeners, MBeans, and caches that may be retaining class loaders.
10. Fix lifecycle/cleanup and repeat the same workflow to confirm the trend has improved.
11. Disable verbose tracing, close JConsole, and store evidence according to your retention policy.

## 16. Checklist When Using the Class Tab

- Connect to the right JVM and environment.
- Remember the red line is the total classes loaded, including unloaded classes.
- Remember the blue line is the number of currently loaded classes.
- Record Current, Total Loaded, and Total Unloaded.
- Observe trends across startup, warm-up, and redeployments.
- Do not conclude a memory leak from a single snapshot.
- Remember the same class name defined by two loaders counts as two distinct classes.
- Use Verbose Output with a time limit.
- Use CSV when comparing data.
- Check Metaspace in the Memory tab.
- Use `jcmd VM.classloader_stats` when loader analysis is needed.
- Use JFR or class load/unload logging when event details are needed.
- Secure remote JMX with authentication, TLS, and firewalls.
- Close connections and disable tracing when finished.

## 17. Key Terminology

| Term | Meaning |
|---|---|
| Class loading | The process by which the JVM loads and defines a class |
| Class unloading | The process by which the JVM removes a class when its class loader becomes eligible for collection |
| Current classes loaded | The number of classes currently loaded |
| Total classes loaded | The total number of classes loaded since the JVM started |
| Total classes unloaded | The total number of classes unloaded since the JVM started |
| ClassLoadingMXBean | Platform MXBean that provides class loading counters |
| JConsole | GUI tool for monitoring and managing Java via JMX |
| JMX | Java Management Extensions |
| MBean | A managed object registered in an MBean Server |
| Class loader | Component responsible for loading and defining classes |
| Class loader leak | An old class loader not being garbage-collected because references to it remain |
| Metaspace | Native memory holding class metadata in modern HotSpot |
| Verbose class loading | Mode that logs information when classes are loaded |
| JFR | Java Flight Recorder, a tool for recording runtime events |
| Class churn | Phenomenon where classes are continuously loaded and unloaded |
| PID | Process ID of a JVM process |

The Class tab in JConsole is a quick observation tool for class loading trends. Read total loaded, current loaded, and total unloaded together; when you spot an unusual trend, combine `ClassLoadingMXBean`, `jcmd`, JFR, and class loader analysis to find the root cause.

## References

- Oracle JDK 24 — [Using JConsole](https://docs.oracle.com/en/java/javase/24/management/using-jconsole.html)
- Oracle JDK 24 — [The jconsole Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jconsole.html)
- Oracle Java SE 24 API — [ClassLoadingMXBean](https://docs.oracle.com/en/java/javase/24/docs/api/java.management/java/lang/management/ClassLoadingMXBean.html)
- Oracle JDK 24 — [The jcmd Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html)
- Oracle JDK 24 — [The jfr Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jfr.html)
- Oracle JDK 24 — [Troubleshooting Guide](https://docs.oracle.com/en/java/javase/24/troubleshoot/troubleshooting-guide.pdf)