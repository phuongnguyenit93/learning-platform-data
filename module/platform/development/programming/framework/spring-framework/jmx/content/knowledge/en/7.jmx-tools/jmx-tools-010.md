# Hands-On: Observing a Small Java Application with JMX Tools

## 1. Lab Objectives

JMX (Java Management Extensions) enables observing and managing a running Java application without adding an HTTP endpoint for every internal value. In this hands-on lab, you will build a very small Java application, register a custom **Standard MBean**, and use **JConsole** to explore the JVM and interact with the MBean.

After this lesson, you can:

1. Start a Java process that stays alive long enough to connect with a JMX tool.
2. Distinguish built-in JVM metrics from management values exposed by the application itself.
3. Connect JConsole to a local JVM and locate the `Memory`, `Threads`, `Classes`, and `MBeans` observation tabs.
4. Read a read-only attribute, modify a read-write attribute, and invoke an MBean operation.
5. Understand the effect of sampling: metrics are point-in-time snapshots and can change between two observations.
6. Recognize the risks of runtime control actions and the limitations of observing via JMX.

This lab uses Java SE to expose the raw JMX mechanism. When moving to a Spring Framework or Spring Boot application, the underlying `MBeanServer`, `ObjectName`, and attribute/operation concepts remain unchanged; Spring primarily assists with exporting, configuration, and bean lifecycle.

## 2. Experiment Model

The application simulates periodically processing a small request. On each cycle, a counter increments and small objects may be allocated to create memory activity. A `DemoMonitor` MBean exposes several state items.

```text
                  Console / terminal
                         |
                 java DemoApplication
                         |
             +-----------+------------+
             |                        |
         Worker thread             MBeanServer
             |                        |
       simulated request        JVM platform MXBeans
             |                        |
       DemoMonitor MBean -------------+
             |                        |
        attribute / operation          |
             +-----------+------------+
                         |
               JConsole (local)
                         |
        Memory / Threads / Classes / MBeans
```

Difference between the two data groups:

- **JVM platform MXBeans** are provided by the JDK, such as memory usage, thread count, class loading, and garbage collector statistics. You do not need to write code to expose this baseline telemetry.
- **Application MBeans** are created by you, such as total processed items, alert thresholds, and simulation mode. They represent the application's specific management needs.

JConsole is a **JMX client**. It reads data through MBeanServer and provides a graphical interface. JConsole is not part of Spring Framework and does not itself store long-term history like a dedicated metrics system.

## 3. Environment Preparation

Use a JDK that includes `java`, `javac`, and `jconsole`, such as JDK 21. This lab does not require Maven, Gradle, Spring Boot, a database, or Docker.

Check in a terminal:

```bash
java -version
javac -version
jconsole
```

The `jconsole` command normally opens a graphical window. If the OS reports the command is not found, verify you are using a **full JDK** and that `JAVA_HOME/bin` or the JDK's `bin` directory is on `PATH`. In headless environments, containers without a desktop, or non-GUI SSH sessions, JConsole may fail to launch; in that case, use a suitable desktop machine or write a local JMX client as shown in the alternative section at the end of this lesson.

**Security:** this exercise uses a local connection to a process you started yourself. Do not enable remote JMX, do not set `com.sun.management.jmxremote.authenticate=false` or `...ssl=false`, and do not open public network ports. If JConsole requires permission to access the local process, run the tool under the same OS user context as appropriate.

Create a directory:

```text
jmx-observation-lab/
  DemoMonitorMBean.java
  DemoMonitor.java
  DemoApplication.java
```

Each public class/interface resides in its own matching file. You can place all three files in the same directory without declaring a `package` to keep compilation simple.

## 4. Building the DemoMonitorMBean Management Interface

Create `DemoMonitorMBean.java`:

```java
public interface DemoMonitorMBean {

    // Read-only attribute: data updated by worker.
    long getProcessedCount();

    // Read-only attribute: snapshot at the time the getter is called.
    int getLastBatchSize();

    // Read-write attribute: operators can modify at runtime.
    int getBatchSize();
    void setBatchSize(int batchSize);

    // Read-write attribute: controls the simulation.
    boolean isRunning();
    void setRunning(boolean running);

    // Operation: reset statistics.
    void resetCounters();
}
```

The **Standard MBean** convention links the name `DemoMonitor` with `DemoMonitorMBean`. `getX()` and `isX()` methods create readable attributes; `setX(...)` enables writing. A getter and setter for the same `BatchSize` or `Running` property create a read-write attribute. `resetCounters()` is an operation.

An MBean interface is a **public contract for management**. Methods present only in the implementation and absent from the interface are not exported by default through Standard MBean rules. Avoid exposing every internal detail when only a few operational properties are needed.

## 5. Implementing a Thread-Safe MBean

Create `DemoMonitor.java`:

```java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

public final class DemoMonitor implements DemoMonitorMBean {

    private final AtomicLong processedCount = new AtomicLong();
    private final AtomicInteger lastBatchSize = new AtomicInteger();

    private volatile int batchSize = 10;
    private volatile boolean running = true;

    @Override
    public long getProcessedCount() {
        return processedCount.get();
    }

    @Override
    public int getLastBatchSize() {
        return lastBatchSize.get();
    }

    @Override
    public int getBatchSize() {
        return batchSize;
    }

    @Override
    public void setBatchSize(int batchSize) {
        if (batchSize < 1 || batchSize > 1_000) {
            throw new IllegalArgumentException(
                "BatchSize must be between 1 and 1000"
            );
        }
        this.batchSize = batchSize;
    }

    @Override
    public boolean isRunning() {
        return running;
    }

    @Override
    public void setRunning(boolean running) {
        this.running = running;
    }

    @Override
    public void resetCounters() {
        processedCount.set(0L);
        lastBatchSize.set(0);
    }

    // Internal method: not in the MBean interface.
    public void recordBatch(int processed) {
        processedCount.addAndGet(processed);
        lastBatchSize.set(processed);
    }
}
```

Here, `AtomicLong` and `AtomicInteger` protect updates to individual counters across multiple threads. `volatile` lets the worker observe changes to `batchSize` and `running` without complex locking. Those mechanisms **do not create an atomic snapshot across multiple attributes**: if you read `ProcessedCount` and then `LastBatchSize`, the worker may update them between the two reads.

The setter `setBatchSize` rejects values outside 1..1000. Validation is the application's responsibility; a JMX client does not automatically know business rules unless metadata and documentation describe them.

## 6. Creating the Running Application That Updates State

Create `DemoApplication.java`:

```java
import java.lang.management.ManagementFactory;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public final class DemoApplication {

    public static void main(String[] args) throws Exception {

        DemoMonitor monitor = new DemoMonitor();

        MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();

        ObjectName name = new ObjectName(
            "lab.jmx:type=DemoMonitor,name=small-app"
        );

        server.registerMBean(monitor, name);

        System.out.println("JMX demo started");
        System.out.println("ObjectName: " + name);
        System.out.println("PID: " + ProcessHandle.current().pid());
        System.out.println("Connect with JConsole and inspect MBeans");

        // Worker simulates work and a small allocation.
        // Do not retain objects long, letting the JVM reclaim them as appropriate.
        List<byte[]> temporary = new ArrayList<>();

        while (!Thread.currentThread().isInterrupted()) {
            if (monitor.isRunning()) {
                int count = monitor.getBatchSize();

                temporary.clear();
                for (int i = 0; i < count; i++) {
                    temporary.add(new byte[4 * 1024]);
                }

                monitor.recordBatch(count);

                System.out.printf(
                    "ProcessedCount=%d, LastBatch=%d, BatchSize=%d%n",
                    monitor.getProcessedCount(),
                    monitor.getLastBatchSize(),
                    monitor.getBatchSize()
                );
            } else {
                System.out.println("Simulation paused");
            }

            TimeUnit.SECONDS.sleep(2);
        }
    }
}
```

The application registers the MBean in the platform MBeanServer via `ManagementFactory.getPlatformMBeanServer()`. `ObjectName` is the search identifier for the MBean, consisting of domain `lab.jmx` and key properties `type` and `name`. Those keys belong to the identifier; they have no direct relationship to Java class names or file paths.

The worker allocates small `byte[]` arrays per batch, holds them temporarily in a list, and replaces them on the next iteration. This is purely **illustrative allocation**, not a memory benchmark or production load model. GC counts, heap size, and memory charts depend on the JDK, collector, heap sizing, and other factors; do not expect a fixed curve.

The loop runs until the process is stopped, usually with `Ctrl+C` in the terminal. When the JVM exits, the MBean no longer exists. A production application may proactively unregister MBeans during shutdown lifecycle; for this short lab, JVM shutdown terminates the in-process MBeanServer automatically.

## 7. Compiling and Running

Inside `jmx-observation-lab`, run:

```bash
javac DemoMonitorMBean.java DemoMonitor.java DemoApplication.java
java DemoApplication
```

You will see output similar to:

```text
JMX demo started
ObjectName: lab.jmx:type=DemoMonitor,name=small-app
PID: 12345
Connect with JConsole and inspect MBeans
ProcessedCount=10, LastBatch=10, BatchSize=10
ProcessedCount=20, LastBatch=10, BatchSize=10
ProcessedCount=30, LastBatch=10, BatchSize=10
...
```

The PID is just an example; each run and each machine will have a different PID. While `Running=true`, `ProcessedCount` grows by the batch size roughly every two seconds. If the machine is busy or OS scheduling differs, actual intervals may drift slightly.

Keep this terminal running. Open a second terminal to launch `jconsole`. If you close the terminal running Java, kill the process, or the JVM exits, JConsole can no longer observe the old MBean.

### 7.1. File Structure After Compilation

```text
jmx-observation-lab/
  DemoMonitorMBean.java
  DemoMonitor.java
  DemoApplication.java
  DemoMonitorMBean.class
  DemoMonitor.class
  DemoApplication.class
```

The JDK may emit additional class files if code contains nested classes; for the three files above, three main class files suffice. No `module-info.java` or build-tool dependency management is required for this minimal experiment.

## 8. Opening JConsole and Selecting the Right JVM

In another terminal, run:

```bash
jconsole
```

JConsole typically lists local Java processes it can observe. Select the process with main class `DemoApplication` or the PID printed in the first terminal.

If the list has multiple Java processes, **do not guess by position**. Cross-check the PID and main class; an IDE, Gradle daemon, or other servers may also be running. When the tool asks to confirm a local connection or displays a warning, read carefully which JVM is selected.

Once connected, the UI typically presents tabs:

- `Overview`: usage summary and graphs.
- `Memory`: heap/non-heap and GC activity at an overview level.
- `Threads`: thread count, thread details, and deadlock detection depending on tool/JVM.
- `Classes`: loaded/unloaded class counts.
- `VM Summary`: VM details, runtime, arguments, and properties.
- `MBeans`: MBean tree for the JVM and application.

Tab names, layout, and display details may vary by JDK version or OS. The goal is recognizing the data and functions rather than relying on pixel layout or tab order.

## 9. Observing the JVM: Memory, Threads, and Classes

### 9.1. Memory

Select the `Memory` tab and inspect metrics such as heap usage, non-heap usage, and memory usage graphs over time.

Metrics to distinguish:

| Metric | Meaning |
|---|---|
| Used | Memory currently reported as in use by the JVM |
| Committed | Amount of memory the JVM has committed for use |
| Max | Reported maximum limit if determinable |
| Heap | Region storing most Java objects |
| Non-heap | Runtime-managed memory regions outside the heap |

`used` is not synonymous with `committed`, nor does it necessarily equal `max`. Seeing heap rise is normal when the worker allocates objects. The Java garbage collector reclaims unreachable objects when needed; heap used may rise and drop or follow another pattern depending on the collector.

Some JConsole versions include a button to request GC. That button is only for experimentation and can affect the process. Do not use it to conclude "the app has a memory leak" or "there is no memory leak." Requesting garbage collection does not guarantee heap will drop immediately by any fixed amount.

### 9.2. Threads

Select the `Threads` tab and inspect the current thread count and thread list. Although you wrote only one main worker, the JVM, JMX agent, and other runtime threads coexist. Thus, **thread count does not equal the number of business threads you explicitly created**.

You can observe different thread states (`RUNNABLE`, `WAITING`, `TIMED_WAITING`, `BLOCKED`) depending on timing. For example, `TimeUnit.SECONDS.sleep(2)` typically puts the main thread in `TIMED_WAITING` while sleeping.

A high thread count alone does not prove a deadlock. If JConsole offers a `Detect Deadlock` feature, it is a specific check, and real incidents still require thread dump analysis.

### 9.3. Classes

The `Classes` tab displays loaded/unloaded class counts. Since the experiment does not continuously load new classes, the graph should stabilize after startup. JConsole/JMX itself may cause a few extra classes to load during observation. Do not assume an increase in class count is a classloader leak.

### 9.4. VM Summary

Read the JVM name, Java version, VM arguments, and other runtime details. Compare the version with the `java -version` you ran. When running inside an IDE or a multi-JDK environment, checking this helps spot connecting to the wrong process or an unexpected classpath.

## 10. Finding Your Custom MBean in the MBeans Tree

Select the `MBeans` tab and expand the domain:

```text
lab.jmx
  type=DemoMonitor,name=small-app
```

Tree layout and key ordering may differ across tools, yet ObjectName still identifies the same MBean. Select the MBean and inspect `Attributes`, `Operations`, and metadata if JConsole displays them.

Expected attributes:

| Attribute | Type | Access | Explanation |
|---|---|---|---|
| `ProcessedCount` | `long` | Read-only | Simulated items processed since last reset |
| `LastBatchSize` | `int` | Read-only | Size of the last batch |
| `BatchSize` | `int` | Read-write | Number of objects allocated and count added per cycle |
| `Running` | `boolean` | Read-write | Enables/pauses the simulation loop |

Operation:

```text
resetCounters()
```

Attributes are recognized by JMX through the `DemoMonitorMBean` interface. `recordBatch(int)` is an internal detail and **does not appear** as a JMX operation because it is absent from the interface.

If the `lab.jmx` domain does not appear, verify the Java process is still running, JConsole is attached to the right PID, and startup output confirms registration succeeded. If `server.registerMBean` throws an exception, the program exits before you can connect; read the error in the terminal.

## 11. Experiment 1: Reading a Read-Only Attribute

Observe `ProcessedCount` under `MBeans -> Attributes`. While the worker runs, the value increments every cycle.

Steps:

1. Note the first value, e.g., `40`.
2. After a few seconds, instruct the tool to re-read it.
3. Note the new value, e.g., `70`, depending on how many cycles ran.
4. Check the terminal running Java and compare with the printed logs.

JConsole may auto-refresh or refresh only when triggered, depending on version/settings. Readings taken at two different moments will not match verbatim because the worker keeps running between observations.

Check metadata: `ProcessedCount` is readable but not writable. A client calling `setAttribute("ProcessedCount", ...)` must be rejected under the Standard MBean contract. Do not try to "edit the counter" by modifying source or using reflection in this lab; we are learning the boundaries enforced by the exposed management interface.

**What you learn:** read-only restricts writes via JMX—it does not mean the value cannot change due to internal threads.

## 12. Experiment 2: Modifying a Read-Write Attribute

Under `Attributes`, find `BatchSize`. Its default is `10`. Change it to `50` if JConsole allows editing that attribute, and confirm.

Observe the terminal:

```text
ProcessedCount=..., LastBatch=10, BatchSize=10
ProcessedCount=..., LastBatch=50, BatchSize=50
ProcessedCount=..., LastBatch=50, BatchSize=50
```

`ProcessedCount` grows faster per cycle because the program uses `monitor.getBatchSize()` as the number of items processed. `LastBatchSize` reflects the last batch and may not change immediately if read before the worker starts its next iteration.

Try entering `0` or `1001`. The setter is designed to reject them. JConsole's UI may display an attribute write error, while the runtime typically wraps the setter's exception in a JMX exception. The point is seeing that **writable does not mean accepting arbitrary values**.

Then set `BatchSize=10` to return to the normal pace.

## 13. Experiment 3: Pausing and Resuming

Find `Running` and change it from `true` to `false`. The terminal will print `Simulation paused`, and `ProcessedCount` will stop increasing once the worker observes the change.

At the moment of switching, an in-progress iteration may finish before `Running=false` takes effect. This is a concurrency characteristic of a flag polled periodically by a worker, not a JMX bug.

Change `Running=true` back. The counter resumes increasing. Ask yourself:

- Why is `Running` read-write rather than `pause()` and `resume()` operations?
- What extra safety checks would a production system need before pausing a real worker?
- Is a single read-write boolean attribute enough for a shutdown workflow with transitional states like `STOPPING` or `DRAINING`?

In complex systems, explicit operations like `pauseConsumer()` and `resumeConsumer()` can express intent and validation better. This lab uses a boolean solely to illustrate the JMX mechanism.

## 14. Experiment 4: Invoking the resetCounters() Operation

Select `Operations`, find `resetCounters`, and invoke it once. Then re-read `ProcessedCount` and `LastBatchSize`.

If `Running=true`, the worker may increment the counter again immediately after the reset. Thus `ProcessedCount` is not guaranteed to remain `0` when JConsole reads it again.

To observe cleanly:

1. Set `Running=false`.
2. Wait until the terminal shows the worker has paused.
3. Invoke `resetCounters()`.
4. Re-read `ProcessedCount` and `LastBatchSize`, which should now be `0`.
5. Set `Running=true` to resume.

**Operation vs. attribute:** `resetCounters()` is an action with side effects. `ProcessedCount` stays read-only because JMX exposes no setter for it, even though the operation is allowed to reset the value.

In production, operations can have major effects. Invoke only actions whose consequences you understand and that you are authorized to perform.

## 15. Observing with a Java Client Without JConsole

To demonstrate that JConsole is just one client, you can write Java code reading the same MBean through the JMX API. For an **in-JVM** client example, add the following lines to `DemoApplication` after registering the MBean:

```java
Object value = server.getAttribute(name, "ProcessedCount");
System.out.println("Initial ProcessedCount = " + value);

Object threshold = server.getAttribute(name, "BatchSize");
System.out.println("Initial BatchSize = " + threshold);
```

Or read a platform MXBean:

```java
import java.lang.management.MemoryMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryUsage;

MemoryMXBean memoryBean = ManagementFactory.getMemoryMXBean();
MemoryUsage heap = memoryBean.getHeapMemoryUsage();

System.out.println("Heap used bytes: " + heap.getUsed());
System.out.println("Heap committed bytes: " + heap.getCommitted());
```

These calls use the Java Management API supported by the JDK. When a real JMX client connects from another process, it can still use `MBeanServerConnection` to query the exact same ObjectNames, provided a connector and appropriate access are configured.

### 15.1. Inspecting Metadata Programmatically

After registering the MBean:

```java
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;

MBeanInfo info = server.getMBeanInfo(name);
for (MBeanAttributeInfo attr : info.getAttributes()) {
    System.out.printf(
        "%s: type=%s, read=%s, write=%s%n",
        attr.getName(),
        attr.getType(),
        attr.isReadable(),
        attr.isWritable()
    );
}
```

The output lets you verify the JMX contract seen by MBeanServer. Reading metadata is more reliable than guessing from UI appearance. It also distinguishes read-only attributes from read-write attributes.

## 16. Alternative When No Graphical Interface Is Available

In headless environments, you can still inspect MBeans via the API inside the JVM. Create a small periodic task reading through `MBeanServer`, or log metadata and selected values after each processing cycle.

A simple snippet to print every ObjectName in the lab domain:

```java
for (ObjectName objectName : server.queryNames(
        new ObjectName("lab.jmx:*"), null)) {
    System.out.println("Found MBean: " + objectName);
}
```

You can also read common platform MBeans:

```java
var threadingBean = ManagementFactory.getThreadMXBean();
System.out.println("Threads: " + threadingBean.getThreadCount());

var classBean = ManagementFactory.getClassLoadingMXBean();
System.out.println("Loaded classes: " +
    classBean.getLoadedClassCount());
```

These examples demonstrate local observation; **they do not prove remote JMX is configured properly**. If the goal is testing a remote connector, run a separate experiment with proper security design—never use options disabling authentication/TLS just for quick access.

## 17. Extension: Applying This to Spring Framework

When an application moves to Spring, the underlying JMX mechanism remains the same:

```text
Spring-managed bean
       |
MBeanExporter / annotation export / explicit registration
       |
MBeanServer
       |
JConsole / Java client
```

You can create a Spring bean managing state, using `@ManagedResource`, `@ManagedAttribute`, and `@ManagedOperation` to expose getters, setters, and operations. Spring provides registration/metadata conveniences, while clients still interact with `ObjectName`, `MBeanInfo`, and the JMX API.

Example bean class:

```java
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(objectName = "lab.spring:type=TaskMonitor")
public class TaskMonitor {
    private final AtomicLong count = new AtomicLong();
    private volatile int batchSize = 10;

    public void recordBatch(int size) {
        count.addAndGet(size);
    }

    @ManagedAttribute
    public long getCount() {
        return count.get();
    }

    @ManagedAttribute
    public int getBatchSize() {
        return batchSize;
    }

    @ManagedAttribute
    public void setBatchSize(int value) {
        if (value < 1 || value > 1000) {
            throw new IllegalArgumentException("Invalid batch size");
        }
        batchSize = value;
    }

    @ManagedOperation
    public void reset() {
        count.set(0L);
    }
}
```

For the annotations to take effect, the application must configure an appropriate JMX exporter. In plain Spring Framework, you can use `@EnableMBeanExport`; in Spring Boot, export behavior typically depends on Boot's JMX configuration, such as `spring.jmx.enabled` in your version. Having `@Component` alone does not guarantee the bean appears in JConsole.

Do not place both `DemoMonitor` and `TaskMonitor` under the same ObjectName in the same MBeanServer. ObjectName must be unique; otherwise registration may fail with an instance-already-exists error.

## 18. Common Errors During Practice

### 18.1. JConsole Cannot Find the Java Process

Verify the JVM is still running, JConsole belongs to a compatible JDK, and the process is attachable under your OS/user context. In containers or machines with restricted attach permissions, local discovery may not work. Do not assume the app crashed solely because JConsole fails to list the process.

### 18.2. Connected to the Wrong JVM

Multiple Java processes have similar names. Cross-check the PID printed by the application or use an appropriate Java process listing tool. After connecting, inspect the `lab.jmx` domain to make sure it is the right target.

### 18.3. Custom MBean Does Not Appear

Check that `server.registerMBean(monitor, name)` ran without errors, the interface is named `DemoMonitorMBean`, the class implements it, and the ObjectName is valid. An unregistered MBean will not appear on its own.

### 18.4. Writing an Attribute Is Rejected

`ProcessedCount` is read-only; JMX disallows writing via `setAttribute`. For `BatchSize`, values outside 1..1000 are also rejected by the setter. Read metadata and actual errors to distinguish write permission from validation.

### 18.5. Invoked Reset, Yet Counter Still Increases

The worker is running and updated the counter after the reset. Pause with `Running=false` before resetting if you want to clearly observe `0`.

### 18.6. Memory Graph Does Not Change as Expected

Object allocation is small, heap was pre-allocated by the JVM, GC has not run yet, or tool sampling is slow. Do not raise memory usage unboundedly to force the chart; if you want clearer movement, try adjusting `BatchSize` within a safe range, observe long enough, and interpret metrics according to their semantics.

### 18.7. JConsole Reports a Security/Connection Error

This lesson covers local JMX only. Check local attach permissions and process status. Never solve this by opening a remote port or disabling authentication over a network.

### 18.8. Process Consumes CPU or Prints Too Much Log Output

The loop sleeps two seconds yet keeps printing logs. Stop with `Ctrl+C` once observation is complete. For long-running applications, replace `System.out.println` with leveled logging, tune pacing, and limit allocations to avoid operational impact.

## 19. Recording Results and Explanations

You can build an observation table like this:

| Action | Expectation | Data to Record |
|---|---|---|
| Connect JConsole | Java process with matching PID visible | PID, JVM version |
| Open Memory | Heap and non-heap metrics present | Used/Committed/Max at a point in time |
| Open Threads | Thread count and states visible | Thread count, one example state |
| Open Classes | Loaded class count visible | Loaded class count |
| Read `ProcessedCount` twice | Value increases while Running=true | Values and timestamps of both reads |
| Set `BatchSize=50` | LastBatch and growth rate change | Before/after, terminal logs |
| Set `Running=false` | Counter stops increasing after active iteration | Timestamp and two reads |
| Invoke `resetCounters()` while paused | Counters become 0 | Values after operation |
| Set `BatchSize=0` | Setter rejects | Observed error message |

This table is an **expected recording template**, not pre-populated results. Fill in actual numbers from your running machine to distinguish verifiable behavior from illustrative figures.

When explaining findings, avoid over-interpreting. For example, `Heap Used` rising across a few samples does not prove a memory leak; a rising thread count alone does not prove a deadlock. Correlate multiple data sources and observe over time.

## 20. Extension Exercises

### Exercise A — Adding a Read-Only Attribute for Uptime

Add startup timestamp tracking to the implementation:

```java
private final long startedAt = System.currentTimeMillis();

@Override
public long getUptimeMillis() {
    return System.currentTimeMillis() - startedAt;
}
```

Add `long getUptimeMillis();` to `DemoMonitorMBean`, recompile, and start the application. In JConsole, verify that `UptimeMillis` is read-only and increases over time.

### Exercise B — Creating Mode-Switching Operations

Replace the `Running` setter pair with two operations `pause()`/`resume()` and a getter `isRunning()`. Compare how they appear in the `MBeans` tab and how the API expresses intent. When is a read-write boolean convenient, and when are explicit operations clearer?

### Exercise C — Adding Notifications

Have the MBean extend `NotificationBroadcasterSupport` and emit a JMX `Notification` when `ProcessedCount` crosses a predefined threshold. Register a `NotificationListener`, filter by `type`, and record `sequenceNumber`. Note that if the counter keeps exceeding the threshold, you must decide whether to emit every time or only on state transition.

### Exercise D — Comparing JVM and Application Attributes

Use `MemoryMXBean` to read `HeapMemoryUsage`, then use `MBeanServer` to read `ProcessedCount`. Identify which metric is defined by the JVM and which is defined by the application. Why can a JMX tool observe both through one interface?

### Exercise E — Checking Consistency

Enable the worker and consecutively read `LastBatchSize` and `ProcessedCount`. Can the values ever come from two different points in time? Propose a combined snapshot attribute if a more consistent metric set is needed.

## 21. Knowledge Self-Check

1. Why don't you need to create a custom MBean just to check JVM heap memory usage?
2. What is the purpose of ObjectName `lab.jmx:type=DemoMonitor,name=small-app`?
3. Does JConsole need to know the `DemoMonitor` implementation class to read attributes?
4. Why doesn't `recordBatch(int)` appear as an operation of the Standard MBean?
5. `ProcessedCount` is read-only yet keeps increasing: is that a contradiction?
6. Why does writing `BatchSize=0` fail even though `BatchSize` is read-write?
7. Does a single click on `resetCounters()` guarantee JConsole always sees `ProcessedCount=0` while the worker is not paused?
8. How do the roles of JConsole and MBeanServer differ?
9. Why can't you conclude a memory leak from a single high heap used observation?
10. When applying this lab to Spring, which parts are handled by Spring and which remain standard JMX?

## 22. Conclusion

Through a three-file Java application, you built a **directly observable management interface**: `DemoMonitorMBean` defines the contract, `DemoMonitor` manages state, `MBeanServer` registers the object under an ObjectName, and JConsole acts as the client reading attributes and invoking operations. At the same time, platform MXBeans show that the JVM already provides memory, thread, and class telemetry out of the box.

Each observation is a point-in-time reading; values change as the worker runs. Understanding data sources, read/write permissions, operation side effects, and metric limits forms the foundation for using JMX in Spring applications and real operational environments.
