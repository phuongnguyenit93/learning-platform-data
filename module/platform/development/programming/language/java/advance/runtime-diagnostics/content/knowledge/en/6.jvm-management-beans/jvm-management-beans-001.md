# 6.1 ManagementFactory, platform MXBeans, and the boundary between standard APIs and HotSpot extensions

> **Java Advance – runtime-diagnostics** · **6. MXBeans**

## 1. The problem: what does the Java runtime let us observe?

When a Java API is unusually slow, operators often ask: how much heap is currently in use, how many threads does the JVM have, how many times has GC run, how much CPU time has the process consumed, or is the operating system overloaded? Not every question requires a profiler, a heap dump, or an agent. Many foundational metrics are provided by the JVM through **platform MXBeans**, accessed directly from code or via **JMX (Java Management Extensions)**.

In Java, **ManagementFactory** is the most convenient entry point for these MXBeans. However, two layers must be distinguished:

- **The standard Java SE management API**, primarily located in the **java.management** module and the **java.lang.management** package. This is a cross-platform contract with documentation specifying bean types, methods, and unsupported cases.
- **JDK/HotSpot extensions**, notably the **jdk.management** module and the **com.sun.management** package. They can provide process CPU time, allocated bytes per thread, in-depth GC information, or HotSpot diagnostics; they should not be treated as a mandatory contract across every Java SE release and every JVM implementation.

This lesson moves from API objects to measured values, compatibility boundaries, how to write applications resilient to runtime differences, and limits when used during production incidents.

### After this lesson, you should be able to

1. Explain the relationship **ManagementFactory → platform MXBean → platform MBeanServer → JMX client/proxy**.
2. Choose the standard bean for memory, threads, runtime, class loading, operating system, garbage collector, and memory pool.
3. Distinguish between a **single MXBean (singleton)** and a **list of MXBeans**; avoid calling the singleton API for a type that has multiple instances.
4. Understand ObjectName, JMX OpenType, and why getters in code can return Java objects while JMX attributes use CompositeData.
5. Use Java 17+ to query standard MXBeans, recognizing **dynamic values**, **-1/unsupported**, **null**, and metrics that are counters/gauges.
6. Recognize and safely check **com.sun.management** extensions, especially OperatingSystemMXBean and HotSpotDiagnosticMXBean.
7. Never confuse the ability to *observe* with the permission to *mutate state*; never turn a JMX API into an unprotected public endpoint.

## 2. Architectural model: direct access or access via JMX

~~~text
                         +-------------------------------+
                         | Running JVM                   |
                         |                               |
  In-process Java code   |  ManagementFactory            |
  ----------------------->|       |                       |
                         |       v                       |
                         |  Platform MXBeans             |
                         |  Memory, Thread, Runtime ...  |
                         |       |                       |
                         |       v                       |
                         |  Platform MBeanServer         |
                         |  ObjectName + JMX attributes  |
                         +---------------+---------------+
                                         |
                      MBeanServerConnection / JMX connector
                                         |
                                         v
                          JMX client / dashboard / tool
~~~

There are **two different paths to read metrics**:

**Path A – direct call inside the same JVM:**

~~~java
// Illustration inside a Java method; this is not a complete program.
java.lang.management.MemoryMXBean bean =
        java.lang.management.ManagementFactory.getMemoryMXBean();
long heapUsedBytes = bean.getHeapMemoryUsage().getUsed();
~~~

This path does not need to start a networked JMX server just to read internally. The program invokes the corresponding Java interface on the running process itself.

**Path B – going through MBeanServer/JMX:**

~~~text
JMX client -> MBeanServerConnection -> ObjectName/attribute/operation
                                   -> platform MXBean
~~~

JMX provides a way to access management data from other tools or applications if an appropriate connection is available. **Calling ManagementFactory.getPlatformMBeanServer() does not automatically open a public JMX port**; publishing a remote endpoint requires configuring a connector and separate security controls. Opening an unauthenticated management port is a serious risk because many beans and operations can expose sensitive data or alter JVM state.

### How does an MXBean differ from an MBean?

**MBean** is the broad JMX concept: a managed object exposing attributes and operations. **MXBean** is a form of MBean that has rules for mapping Java data types to **JMX OpenTypes** (e.g., simple data, CompositeData, TabularData). As a result, a JMX client does not necessarily need the exact concrete Java class of the returned object to read the data.

An object called directly:

~~~text
MemoryMXBean.getHeapMemoryUsage() -> MemoryUsage
~~~

When reading the corresponding attribute through MBeanServer:

~~~text
MBeanServer.getAttribute(ObjectName, "HeapMemoryUsage")
    -> an OpenType value, typically CompositeData
~~~

These are not two different metrics; they are **two representations** of the same information under the JMX contract. Do not cast the value from MBeanServer to MemoryUsage without considering MXBean mapping. A runnable example in the practice section will demonstrate this point.

## 3. ManagementFactory: a consistent gateway for platform MXBeans

The **java.lang.management.ManagementFactory** class has static methods returning beans provided by the platform. There is no need to instantiate MemoryMXBean or ThreadMXBean with a constructor.

### 3.1 Factory methods to remember

| Factory method | Standard return type | Diagnostic question |
| --- | --- | --- |
| getRuntimeMXBean() | RuntimeMXBean | VM name/version, uptime, start time, input arguments |
| getMemoryMXBean() | MemoryMXBean | Heap/non-heap used/committed/max, pending finalization count if provided |
| getThreadMXBean() | ThreadMXBean | Live/daemon/peak thread count, thread CPU time, deadlock and ThreadInfo when supported |
| getOperatingSystemMXBean() | OperatingSystemMXBean | OS name/architecture, processors available, system load average |
| getClassLoadingMXBean() | ClassLoadingMXBean | Currently loaded classes, total loaded/unloaded |
| getGarbageCollectorMXBeans() | List<GarbageCollectorMXBean> | Available GC managers, total collection count/time |
| getMemoryPoolMXBeans() | List<MemoryPoolMXBean> | Eden/Old/Metaspace or VM-defined pools, usage/peak/threshold |
| getMemoryManagerMXBeans() | List<MemoryManagerMXBean> | Memory managers and related pools |
| getCompilationMXBean() | CompilationMXBean or null | Compiler/JIT system information when available |
| getPlatformMXBean(Class<T>) | T or null | Retrieve a platform management interface with **at most one** instance |
| getPlatformMXBeans(Class<T>) | List<T> | Retrieve **0 to many** beans of the same interface |
| getPlatformManagementInterfaces() | Set<Class<? extends PlatformManagedObject>> | Management interfaces supported by the platform, including implementation extensions |
| getPlatformMBeanServer() | MBeanServer | Standard in-process JMX gateway |

**Multiplicity matters.** MemoryMXBean and ThreadMXBean are classic singletons. GarbageCollectorMXBean, MemoryManagerMXBean, MemoryPoolMXBean, and BufferPoolMXBean belong to the group that can have multiple beans; the count, names, and order depend on the VM, GC, and configuration. CompilationMXBean may **not exist** and the method returns null.

Therefore, do **not** call getPlatformMXBean(GarbageCollectorMXBean.class) assuming there is a single collector: the singleton API may throw IllegalArgumentException because this interface type is not a singleton. Use:

~~~java
// Illustrative snippet, placed inside any method.
var collectors = java.lang.management.ManagementFactory
        .getPlatformMXBeans(java.lang.management.GarbageCollectorMXBean.class);
for (var gc : collectors) {
    System.out.println(gc.getName() + ": " + gc.getCollectionCount());
}
~~~

The loop above has no fixed stdout: GC names, bean counts, and counters vary by JVM, collector configuration, and observation time.

### 3.2 getPlatformMXBean can be null, and lists can be empty

For a singleton interface known to the platform but not implemented, **getPlatformMXBean(Class<T>) can return null**. For a management interface not recognized as a platform interface or when using the singleton API for a multi-instance type, **IllegalArgumentException** is a valid outcome of the API. Across different JDK versions/vendors, do not assume every extension is present.

For getPlatformMXBeans(Class<T>), the result can be an empty list, one bean, or many beans; **the order is not guaranteed to be stable**. Do not write code assuming "element 0 is always Old GC" or "pool name is always G1 Old Gen". If you need to distinguish pool types, read *getName()*, *getType()*, *getMemoryManagerNames()*, and actual metadata, while accepting that names may change across collectors/versions.

### 3.3 getPlatformManagementInterfaces is a capability catalog, not a portability guarantee for your code

This method returns the set of interfaces provided by the current platform; in OpenJDK/HotSpot it may include **JDK extension interfaces**, not just Java SE standard ones. Seeing an extension appear on the build you are testing only proves **that build** supports it, not that another JVM must do so.

A portable design should rely on Java SE interfaces when standard metrics suffice; extend only when there is a **clear diagnostic need**, with runtime capability checks and fallback.

## 4. Module boundaries and compatibility

| Group | Module and package | Contract | Examples |
| --- | --- | --- | --- |
| Java SE standard | java.management / java.lang.management | Foundational API specified in Java SE | ManagementFactory, MemoryMXBean, ThreadMXBean, RuntimeMXBean, OperatingSystemMXBean |
| JMX standard | java.management / javax.management and javax.management.openmbean | Connecting and accessing attributes/operations, OpenTypes | MBeanServer, MBeanServerConnection, ObjectName, CompositeData |
| JDK extensions | jdk.management / com.sun.management | Documented API in the JDK, not part of the core Java SE contract | Extended OperatingSystemMXBean, extended ThreadMXBean, HotSpotDiagnosticMXBean, GcInfo |
| Other HotSpot/diagnostic mechanisms | Tools, JFR, diagnostic commands, JDK-specific APIs | Dependent on VM and tools, cannot be replaced by Java SE calls if no standard interface exists | jcmd VM.*, heap dump, GC details |

**Two packages both have an interface named OperatingSystemMXBean**:

- **java.lang.management.OperatingSystemMXBean** only has basic properties such as OS name, architecture, available processors, and load average.
- **com.sun.management.OperatingSystemMXBean** extends the standard interface, adding process CPU time/load and memory/CPU environment information. In JDK 17, common methods include *getProcessCpuTime()*, *getProcessCpuLoad()*, *getCpuLoad()*, *getTotalMemorySize()*, and *getFreeMemorySize()*.

Do not write wildcard imports for both packages at the same time and then use the ambiguous name *OperatingSystemMXBean*. In extension examples, we intentionally write the full extended interface name to distinguish them.

In an **application with module-info.java**:

~~~java
module diagnostics.app {
    requires java.management;
}
~~~

That is a sufficient module descriptor for the part of the lesson using standard APIs (assuming the app has no other dependencies/modules). Only when code **directly references** com.sun.management and the actual JDK has that module do you need:

~~~java
module diagnostics.app {
    requires java.management;
    requires jdk.management;
}
~~~

These are two **alternative** descriptor examples; do not place both in the same file. Do not automatically add `requires jdk.management` to every service just to read standard heap used. The `jdk.management` module might not be packaged into a custom runtime image if `jlink` omits it, so referencing it can cause deployment to fail even when building on a developer machine succeeds.

**Remember:** "com.sun.management has public JDK documentation" is different from "com.sun.management is a mandatory standard Java SE API"; and both are different from "every class starting with sun.* is supported". Decisions should be based on the **specific module/package and contract**, not just the package name prefix.

## 5. PlatformManagedObject and ObjectName

Each platform MXBean implements **PlatformManagedObject**, which has the *getObjectName()* method used to identify the object in the platform MBeanServer. Some stable ObjectNames in the Java SE API:

| Interface | Standard ObjectName |
| --- | --- |
| MemoryMXBean | java.lang:type=Memory |
| ThreadMXBean | java.lang:type=Threading |
| RuntimeMXBean | java.lang:type=Runtime |
| OperatingSystemMXBean | java.lang:type=OperatingSystem |
| ClassLoadingMXBean | java.lang:type=ClassLoading |
| CompilationMXBean (if present) | java.lang:type=Compilation |
| GarbageCollectorMXBean | java.lang:type=GarbageCollector,name=<collector name> |
| MemoryPoolMXBean | java.lang:type=MemoryPool,name=<pool name> |

The table above illustrates the registration convention of standard beans. Rows with *name* may have values that vary across VMs/collectors and must be **properly encoded according to ObjectName syntax** when using the JMX API. It is best to **call bean.getObjectName() directly** once you have the bean, rather than concatenating name strings manually. ObjectName is neither a Java class name nor a PID.

The platform MBeanServer is obtained via:

~~~java
// Illustrative snippet.
javax.management.MBeanServer server =
        java.lang.management.ManagementFactory.getPlatformMBeanServer();
~~~

The first retrieval may initialize the server and register existing platform MXBeans; platform beans with dynamic lifecycles may be registered/unregistered accordingly. Having a local server **does not prove** there is an open remote JMX listener port.

### Three ways to access the same platform MXBean

1. **Direct Java interface:** `getMemoryMXBean().getHeapMemoryUsage()`, convenient when running inside the same JVM.
2. **MBeanServer/MBeanServerConnection:** retrieve attributes by ObjectName, e.g., *getAttribute(name, "HeapMemoryUsage")*, suited for management/JMX tools.
3. **Typed proxy:** *ManagementFactory.getPlatformMXBean(connection, MemoryMXBean.class)* or *newPlatformMXBeanProxy(connection, name, MemoryMXBean.class)*, forwarding method calls over MBeanServerConnection.

A proxy makes it easier to write typed code compared to raw ObjectName attributes, yet it still depends on the connection and OpenType conversion. A proxy call can raise I/O errors (even wrapped inside a dynamic proxy exception), so disconnects, timeouts, and version mismatches must be handled. Direct local access does not face those network connection issues.

**Do not apply the same semantics** to "a local bean held in a variable inside the application JVM" and "a remote proxy over a JMX connector". Both may share the same interface, yet differ in timeout, concurrency, and safety boundaries.

## 6. Standalone Java 17+ example using standard APIs and OpenType

Goals of the example:

- Access MemoryMXBean, RuntimeMXBean, ThreadMXBean, and OperatingSystemMXBean through **standard ManagementFactory**.
- Read dynamic heap/thread/uptime values while **avoiding printing absolute numbers** since they differ across machines.
- Access the platform MBeanServer and demonstrate that the Java *MemoryUsage* property is converted into **CompositeData** over JMX.
- Print check assertions with **stable stdout** on Java 17+ with standard platform MXBeans.

Create the file **StandardMxBeanDemo.java**:

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import java.lang.management.MemoryUsage;
import java.lang.management.OperatingSystemMXBean;
import java.lang.management.RuntimeMXBean;
import java.lang.management.ThreadMXBean;
import javax.management.MBeanServer;
import javax.management.openmbean.CompositeData;

public final class StandardMxBeanDemo {
    public static void main(String[] args) throws Exception {
        MemoryMXBean memory = ManagementFactory.getMemoryMXBean();
        RuntimeMXBean runtime = ManagementFactory.getRuntimeMXBean();
        ThreadMXBean threads = ManagementFactory.getThreadMXBean();
        OperatingSystemMXBean os = ManagementFactory.getOperatingSystemMXBean();
        MemoryUsage heap = memory.getHeapMemoryUsage();
        MBeanServer server = ManagementFactory.getPlatformMBeanServer();

        System.out.println("memoryObjectName=" + memory.getObjectName());
        System.out.println("runtimeObjectName=" + runtime.getObjectName());
        System.out.println("memoryRegistered=" + server.isRegistered(memory.getObjectName()));
        System.out.println("heapAttributeIsOpenData="
                + (server.getAttribute(memory.getObjectName(), "HeapMemoryUsage")
                   instanceof CompositeData));
        System.out.println("heapUsedNonnegative=" + (heap.getUsed() >= 0));
        System.out.println("heapCommittedNonnegative=" + (heap.getCommitted() >= 0));
        System.out.println("threadCountPositive=" + (threads.getThreadCount() > 0));
        System.out.println("uptimeNonnegative=" + (runtime.getUptime() >= 0));
        System.out.println("processorsPositive=" + (os.getAvailableProcessors() > 0));
        System.out.println("memoryInterfaceListed=" + ManagementFactory
                .getPlatformManagementInterfaces().contains(MemoryMXBean.class));
    }
}
~~~

In the directory containing the file:

~~~bash
javac -encoding UTF-8 StandardMxBeanDemo.java
java StandardMxBeanDemo
~~~

**Exact stdout of this test on a typical Java 17+ environment:**

~~~text
memoryObjectName=java.lang:type=Memory
runtimeObjectName=java.lang:type=Runtime
memoryRegistered=true
heapAttributeIsOpenData=true
heapUsedNonnegative=true
heapCommittedNonnegative=true
threadCountPositive=true
uptimeNonnegative=true
processorsPositive=true
memoryInterfaceListed=true
~~~

Because the program prints **condition checks** rather than absolute heap/uptime numbers, the output can be matched while learning. This standalone program was compiled/run on an actual JDK to obtain the lines above.

**Interpretation:**

- *memory.getObjectName()* is the platform bean identifier, independent of PID or implementation class name.
- *getHeapMemoryUsage()* returns a **MemoryUsage snapshot** containing byte counts at the moment of measurement; *getUsed()* differs from the process RSS measurement.
- *getAttribute(..., "HeapMemoryUsage")* returns an **MXBean OpenType**, here CompositeData. Another JMX client does not need the exact MemoryUsage class installed to read the data fields.
- *getThreadCount()* reflects the thread count at read time, not requests/s; *getUptime()* measures milliseconds since JVM startup, not the current timestamp.
- *getPlatformManagementInterfaces()* indicates that the MemoryMXBean interface is in the supported set; the set may also contain extension interfaces of the running JDK.

**Limitations of the example:** the checks above do not prove the results for every JVM version/vendor. Each snapshot may be taken at a different instant; there is no atomic simultaneous capture of all CPU/heap/threads. Before using metrics for alerting, know their semantics, units, and "unsupported" policies.

## 7. How to read standard metrics properly: gauge, counter, sentinel

Platform MXBeans are convenient because they require minimal configuration, yet the data itself is very easy to misinterpret.

| Method | Data type / unit | Metric type | Common pitfalls |
| --- | --- | --- | --- |
| MemoryMXBean.getHeapMemoryUsage().getUsed() | bytes | Gauge/snapshot | Not RSS, not total allocated |
| MemoryUsage.getCommitted() | bytes | Gauge/snapshot | Memory committed by JVM, not live bytes |
| MemoryUsage.getMax() | bytes or -1 | Limit if defined | -1 means max is undefined |
| RuntimeMXBean.getUptime() | milliseconds | Duration since JVM started | Resets near 0 after restart; not wall-clock calendar time |
| ThreadMXBean.getThreadCount() | threads | Gauge | Not request processing throughput |
| ThreadMXBean.getPeakThreadCount() | threads | High-water mark | Not current thread count; can be reset via operation |
| ClassLoadingMXBean.getTotalLoadedClassCount() | total classes | Cumulative counter | Differs from getLoadedClassCount(), which is currently loaded |
| ClassLoadingMXBean.getUnloadedClassCount() | total classes | Cumulative counter | Not classes unloaded/s unless taking a delta |
| GarbageCollectorMXBean.getCollectionCount() | count or -1 | Counter if supported | Not equal to GC pauses across all collectors/VMs |
| GarbageCollectorMXBean.getCollectionTime() | milliseconds or -1 | Cumulative duration if supported | Not latency of a single GC or p99 pause |
| OperatingSystemMXBean.getAvailableProcessors() | processor count | State/capacity | Can change due to quota/affinity/runtime |
| OperatingSystemMXBean.getSystemLoadAverage() | load average or negative | OS load indicator | Not CPU percentage; may be unsupported |

### 7.1 MemoryUsage has four components

A **MemoryUsage** snapshot contains *init*, *used*, *committed*, *max*:

- *init*: initial memory the JVM requests from the operating system, may be undefined.
- *used*: amount of memory used within the scope managed by the bean/pool at the snapshot.
- *committed*: committed memory guaranteed to be available for use by the JVM under the JVM model.
- *max*: maximum usable threshold if defined; **-1** means undefined.

Under valid conditions, *used ≤ committed*; *committed* and *max* are not the same metric. **Do not compute used/max as a percentage when max = -1**, because the expression has no meaning. And do not treat heap max as the entire container memory limit: the process also has metaspace, code cache, thread stacks, native allocations, direct buffers, and many other regions.

**MemoryMXBean.getNonHeapMemoryUsage()** is not equivalent to all RAM outside the heap. Various native allocations may not be included in the non-heap MXBean accounting; to determine RSS/native footprint, you need OS/container metrics or appropriate diagnostic tools.

### 7.2 GC count/time are counters, not latency histograms

For example, reading two snapshots of one collector separated by \(\Delta t\):

\[
\text{GC collections/s} = \frac{C_2-C_1}{\Delta t},
\qquad
\text{GC time ratio} = \frac{T_2-T_1}{1000\Delta t}
\]

Where \(T\) is in **milliseconds** and \(\Delta t\) is in **seconds**. However, this formula is meaningful only when:
- Both snapshots belong to the **same JVM/collector** and the counter has not reset.
- Both count and time are **not -1** (supported).
- They share the same definition scope; understand how the GC vendor/collector accounts for time.
- Do not use negative deltas after a process restart.

A total GC collection time increase of 300 ms over 60 s is **not** enough to know p99 pause: you need individual pause distributions from JFR/GC logs/appropriate histograms. Collection time reported by the bean can depend on how the implementation defines time; do not mechanically equate it with "milliseconds during which all application threads were stopped-the-world".

### 7.3 ThreadMXBean: check support before measuring

Some capabilities are conditional:

- *isThreadCpuTimeSupported()* and *isCurrentThreadCpuTimeSupported()* check CPU time measurement capability.
- *isThreadCpuTimeEnabled()* checks the current enabled/disabled state; the VM may support it while it is turned off.
- *getThreadCpuTime(threadId)* may return **-1** if unsupported, disabled, or the thread is invalid/terminated per contract.
- *isThreadContentionMonitoringSupported()* checks contention timing support; enabling measurement can introduce overhead.
- *findDeadlockedThreads()* and *dumpAllThreads(...)* can assist lock investigation, but data volume and impact grow with thread count.

Do not call *setThreadCpuTimeEnabled(true)* or *setThreadContentionMonitoringEnabled(true)* as a "read-only" step in production. These are **measurement-state-mutating operations** with their own cost and permissions. Check capability, policy, and necessity before enabling.

### 7.4 -1 and null are not synonymous with 0

In Java management documentation, **-1** is commonly the sentinel for "unsupported/undefined" for a specific method. However, not every method uses the same sentinel. *getCompilationMXBean()* can return null if the JVM has no compilation system; *MemoryPoolMXBean.getUsage()* can be unavailable in certain situations; *OperatingSystemMXBean.getSystemLoadAverage()* returns a negative value if not available.

**Wrong:** "System load = -1 so the machine is underloaded and can be ignored."

**Right:** "System load average is unavailable on this JVM/OS; use another OS metric." Do not plot -1 on a CPU load chart as a real measurement.

If a bean method throws *UnsupportedOperationException*, distinguish between feature support, access permissions, and runtime configuration. Do not catch all exceptions and pretend the metric is 0, because dashboards will easily draw false conclusions.

## 8. JDK/HotSpot extensions: com.sun.management

The **com.sun.management** package resides in the **jdk.management** module (JDK 17) and has official documentation. It is a **JDK extension**, not a core interface mandated across every Java SE runtime.

### 8.1 Common extension interfaces

| JDK extension interface | Relation to standard API | Typical additional capabilities |
| --- | --- | --- |
| com.sun.management.OperatingSystemMXBean | extends java.lang.management.OperatingSystemMXBean | Process CPU time/load, environment CPU load, physical/container memory metrics |
| com.sun.management.UnixOperatingSystemMXBean | extends extended OS bean | File descriptor information on Unix environments when available |
| com.sun.management.ThreadMXBean | extends java.lang.management.ThreadMXBean | Bytes allocated by thread and support check methods |
| com.sun.management.GarbageCollectorMXBean | extends standard GC bean | Information about the last GC (GcInfo) when the collector supports it |
| com.sun.management.HotSpotDiagnosticMXBean | Dedicated PlatformManagedObject | VM options and HotSpot operations such as heap dump |
| com.sun.management.DiagnosticCommandMBean | MBean for HotSpot diagnostic commands | VM-specific operations set, not a standard business API |

The presence of an interface in the package does not guarantee every method **works on every configuration/OS**, especially for CPU time, per-thread allocation, or detailed GC info.

### 8.2 OperatingSystemMXBean: typical standard/extension boundary

The following **do not exist** on the standard interface:

~~~text
com.sun.management.OperatingSystemMXBean.getProcessCpuTime()
com.sun.management.OperatingSystemMXBean.getProcessCpuLoad()
com.sun.management.OperatingSystemMXBean.getTotalMemorySize()
com.sun.management.OperatingSystemMXBean.getFreeMemorySize()
~~~

Thus code that only imports *java.lang.management.OperatingSystemMXBean* and calls *getProcessCpuTime()* will **fail to compile**: not because the JVM "lacks a CPU", but because **the standard interface does not declare that method**.

To observe process CPU time from the JDK extension on a supporting JVM, you need to access the extended interface **with a runtime check**. The standalone example below uses Java 17 pattern matching *instanceof*, and intentionally separates the standard variable from the extended variable.

Create the file **JdkManagementExtensionDemo.java**:

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.OperatingSystemMXBean;

public final class JdkManagementExtensionDemo {
    public static void main(String[] args) {
        OperatingSystemMXBean standard = ManagementFactory.getOperatingSystemMXBean();
        if (standard instanceof com.sun.management.OperatingSystemMXBean extended) {
            System.out.println("jdkExtensionAvailable=true");
            long processCpuNanos = extended.getProcessCpuTime();
            if (processCpuNanos < 0) {
                System.out.println("processCpuTime=unsupported");
            } else {
                System.out.println("processCpuTime=nonnegative");
            }
        } else {
            System.out.println("jdkExtensionAvailable=false");
        }
    }
}
~~~

On JDK 17+ with the **jdk.management** module and a suitable implementation:

~~~bash
javac -encoding UTF-8 JdkManagementExtensionDemo.java
java JdkManagementExtensionDemo
~~~

Observed output on a HotSpot JDK supporting CPU-time:

~~~text
jdkExtensionAvailable=true
processCpuTime=nonnegative
~~~

**This is the output of the test environment, not a guarantee for every VM.** If the runtime has the extension class but the implementation does not provide the bean, the "unavailable" branch runs; if CPU time is unsupported, the "unsupported" line is printed. If a JDK/runtime image **does not contain jdk.management**, code directly linking to com.sun.management may **fail to compile or fail to start**; in such environments you must choose a different build or separate the extension module/option.

Why does the code use *instanceof*? The standard interface is the contract you can always rely on when using Java SE with the corresponding MXBean. *instanceof* enters the JDK-dependent branch only when the implementation actually satisfies the interface, avoiding an unchecked cast that throws ClassCastException. However, a runtime guard **does not replace** verifying the module's presence during build/deploy.

### 8.3 CPU time and CPU load are not the same quantity

The extension's *getProcessCpuTime()* method returns **cumulative CPU time in nanoseconds** or **-1** if unsupported. If you want the average CPU consumption between two snapshots, compute:

\[
\frac{\Delta \text{processCpuNanos}}{\Delta \text{wallNanos}}
\]

The result can be greater than 1 if the process uses multiple CPU cores concurrently. To convert to a capacity ratio, you must choose how to normalize by **available processors/quota** and understand the runtime's metric contract; do not arbitrarily call it 100% when multiple cores are present.

Methods like *getProcessCpuLoad()* return a measure of **recent CPU usage** and may return a negative value when unsupported. Do not infer "the process is using 0% CPU" just because a call returns -1. Recent CPU load differs from cumulative CPU time, and they can react differently to sampling/containers.

Environment memory methods such as *getTotalMemorySize()* and *getFreeMemorySize()* belong to the extension, not the standard OS bean API; whether they reflect container limits or host capacity depends on the environment and implementation. Do not read total memory on one build and declare it to be max heap memory or the cgroup hard limit on every JVM.

### 8.4 HotSpotDiagnosticMXBean: beyond reading metrics

**HotSpotDiagnosticMXBean** has an ObjectName defined by the JDK implementation, typically:

~~~text
com.sun.management:type=HotSpotDiagnostic
~~~

It supports typical operations:

- *getDiagnosticOptions()*: VM options that can be diagnosed/changed depending on capabilities.
- *getVMOption(name)*: reads the state of the specified option.
- *setVMOption(name, value)*: **modifies** a VM option that supports dynamic updates; not all options are writable.
- *dumpHeap(path, live)*: creates a heap dump (*.hprof* file) on the filesystem visible to the JVM.

**Warning:** a heap dump can be very large, create CPU/I/O/disk pressure, impact latency, and contain application objects/secrets. Even though the bean exists, calling dumpHeap **is not a lightweight read operation**. Similarly, setVMOption is a runtime control operation requiring authorization and an operational plan. JDK documentation specifies errors for existing files, invalid paths, unwritable targets, or unsupported operations.

If you only need an initial check, prefer less invasive standard APIs such as heap usage, thread count, and runtime uptime; do not try dumpHeap just to "test whether the extension works".

## 9. Code design strategy: standard-first, capability check, fallback

An observability library is often reused across many services. If the core layer imports com.sun.management everywhere, a minimal runtime image or a different JVM implementation may fail to run, even though standard functionality is available.

Recommended design:

~~~text
DiagnosticsFacade
    |
    +-- StandardJmxReader (java.management)
    |     +-- memory, threads, runtime, OS basics, GC
    |
    +-- OptionalJdkReader (jdk.management) [if available]
    |     +-- process CPU, thread allocation, HotSpot-specific
    |
    +-- Metrics exporter / structured result
          +-- value
          +-- unit
          +-- source
          +-- instance scope
          +-- availability: supported / unavailable / error
~~~

**Specific principles:**

1. **Standard first:** if you want heap used, use MemoryMXBean instead of HotSpotDiagnosticMXBean.
2. **Isolate dependencies:** keep extensions in a separate adapter/module; core does not always have to load extension code.
3. **Capability detection:** check interfaces/modules and *isXxxSupported()*, null/-1 according to contract. Do not use a JVM name containing "HotSpot" as the sole check.
4. **Define absent results:** represent *unsupported* or *not available*, do not fabricate a 0 measurement.
5. **Record units and provenance:** "CPU time from JDK extension, nanoseconds" differs from "system load average from Java SE, dimensionless".
6. **Do not assume fixed bean names for multi-instance types:** collectors/pools may change after switching GC or version.
7. **Separate read-only metrics from control operations:** an endpoint serving metrics should not implicitly trigger dumpHeap or setVMOption.
8. **Test across environments:** at least the JDKs/GCs/OSes/containers your product actually supports; document the tested scope.

For example, when emitting JSON from an exporter: a field `"processCpuTimeNs = null; availability=unsupported; source=jdk.management"` is better than `"processCpuTimeNs = 0"`, because 0 could mislead alerts into concluding the process is idle when it actually could not be measured.

## 10. JMX client and MXBean proxy: portability at the data layer

When you need to read from another process, you can query MBeanServerConnection. A **secured JMX connector** provides the path from client to server; ManagementFactory supports creating typed proxies corresponding to MXBeans over that connection.

Example **code snippet, not standalone** — assuming the variable *connection* is a securely connected MBeanServerConnection:

~~~java
java.lang.management.MemoryMXBean remoteMemory =
        java.lang.management.ManagementFactory.getPlatformMXBean(
                connection, java.lang.management.MemoryMXBean.class);
if (remoteMemory != null) {
    long bytes = remoteMemory.getHeapMemoryUsage().getUsed();
    // Export bytes along with timestamp and target JVM identity.
}
~~~

This is the same standard interface, but **accessed remotely**. The connection can drop, the target JVM can restart, or the JMX client may use a different version. Timeouts, communication errors, disappearing objects, and OpenType mapping issues must be handled.

A non-proxy approach is:

~~~java
// Snippet, requires an available MBeanServerConnection connection.
javax.management.ObjectName name =
        new javax.management.ObjectName("java.lang:type=Memory");
Object value = connection.getAttribute(name, "HeapMemoryUsage");
// value is mapped via OpenType/CompositeData, do not cast directly to MemoryUsage.
~~~

**There are no secret ObjectNames:** the standard names are well known, which is no reason to expose JMX to a public network. **Authentication, TLS, network access control, and operation authorization** are essential whenever a JMX connector is enabled remotely, especially for MBeans with control operations.

JMX proxies are designed for cross-version interoperability thanks to OpenTypes, yet do not guarantee every new/old method on an interface keeps the same meaning or always exists. Clients should use an appropriate version contract, handle unsupported/unknown attributes, and have fallback rules.

## 11. ManagementFactory is not the tool for every diagnostic problem

**When MXBeans are a good fit:**

- Polling heap used/committed, thread count, class loading, GC count/time.
- Checking runtime uptime/start time to detect restarts.
- Reading OS available processors/load average via standard APIs.
- Identifying the number and names of pools/collectors provided by the actual JVM.
- Implementing a low-cost internal exporter for regular basic health checks.

**When data beyond MXBeans is needed:**

- **Exact p95/p99 GC pause:** GC logs, JFR, or histograms recording individual events; total collection time does not give a distribution.
- **Suspected object retention or memory leak:** heap dump/JFR allocation profiling/analysis tools; point-in-time heap used does not prove a leak.
- **Deadlock or detailed lock contention:** ThreadMXBean has supporting capabilities, but ThreadInfo/stacks/JFR and time-correlated states are needed.
- **Native memory/RSS:** OS metrics, container metrics, or Native Memory Tracking/appropriate tools; heap + non-heap does not equal total RSS.
- **Request latency and business errors:** application metrics/logs/tracing; MXBeans do not inherently know route/requestId.
- **Per-thread allocation or process CPU:** may require extensions and support checks.

### Illustration: why looking at a single bean leads to the wrong conclusion

A JVM runs with surging throughput while heap used fluctuates around 500 MiB. Looking only at *getHeapMemoryUsage().getUsed()*, one might conclude "memory is fine, no issue". Yet the application might be allocating objects at a very high rate and triggering GC continuously; heap used does not necessarily rise if the collector reclaims fast enough. You must read **GC count/time across multiple snapshots**, allocation metrics/JFR, and request latency, rather than looking at a single gauge.

Conversely, heap used rising during warmup and then stabilizing is not enough to prove a leak; you need a baseline, retained heap, collector behavior, and comparable load.

## 12. Diagnostic walkthrough: reading the right signals for four symptoms

### 12.1 Heap rising steadily after each load burst

**Standard sources:** MemoryMXBean.getHeapMemoryUsage(), MemoryPoolMXBeans by pool.

**Questions:** is heap used rising at all times or only before GC? Does the post-GC value climb across multiple cycles? Do committed/max change due to ergonomic sizing?

**Complementary measurements:** GC logs/JFR, memory pool usage, native/container memory; proceed to a heap dump only with authorization and clear investigative benefit.

**Limitations:** HeapMemoryUsage does not show the object graph or what holds references. DumpHeap via the extension can help, but is a high-impact operation.

### 12.2 Thread count rising while API throughput drops

**Standard sources:** ThreadMXBean.getThreadCount(), getPeakThreadCount(), getAllThreadIds()/getThreadInfo() depending on need and support.

**Questions:** are live threads growing due to pool expansion, blocked/waiting threads, deadlock, or a thread leak? How many requests are in flight, what is the queue depth, and what are timeouts?

**Complementary measurements:** thread dump/JFR/stacks, thread-pool gauges, dependency latency. Do not conclude "CPU exhausted" solely from thread count; threads in WAITING can consume very little CPU.

**Limitations:** some thread CPU times/lock contention metrics require support and enabling; enabling during an incident carries overhead. Thread count is also not identical to virtual thread count in newer JVMs; read the documentation for the exact release if the application uses virtual threads.

### 12.3 GC count rising, p99 degrading

**Standard sources:** List<GarbageCollectorMXBean>; read collection count/time at two or more timestamps.

**Questions:** how much did collection rate/total collection time increase? Was there a restart/counter reset? Do counters return -1? Which collector does the data belong to?

**Complementary measurements:** GC logging/JFR pause duration and timestamps, allocation rate, heap pools, CPU. "GC count increased" is only a correlation; confirm pauses are large enough and coincide with slow requests.

### 12.4 High CPU in a container

**Standard sources:** OperatingSystemMXBean.getAvailableProcessors()/getSystemLoadAverage().

**Possible additions from JDK extension:** process CPU time/load, environment CPU load. These metrics may depend on JDK, cgroup, quota, and host/container isolation.

**Complementary measurements:** OS/container metrics for CPU throttling/quota, process CPU, thread CPU time when supported, JFR CPU/profile. Do not treat system load average as CPU percentage and do not infer process CPU% from a single snapshot of cumulative CPU time.

## 13. Things that require special caution in production

### 13.1 Read-only methods vs. control operations

| Group | Examples | Impact level |
| --- | --- | --- |
| Snapshot reads | getHeapMemoryUsage(), getThreadCount(), getUptime() | Generally suitable for monitoring, though still has overhead if polled too frequently |
| Runtime list reads | getMemoryPoolMXBeans(), getGarbageCollectorMXBeans() | Must handle changing lists; avoid excessive polling |
| Stack/lock detail capture | ThreadInfo, dumpAllThreads() | Can consume CPU/memory and return large payloads |
| Toggle extra measurement | setThreadCpuTimeEnabled(), setThreadContentionMonitoringEnabled() | **Mutates state**, requires weighing cost and permissions |
| Request GC | MemoryMXBean.gc() | **Not read-only**; requests a GC run with no guarantee on result/timing, can hurt latency |
| Memory dump | HotSpotDiagnosticMXBean.dumpHeap() | **High impact**, consumes disk/I/O, sensitive data risk |
| Change VM option | HotSpotDiagnosticMXBean.setVMOption() | **Mutates runtime**, may be unsupported or option not writable |

A "read-only" exporter should avoid exposing control operations without safeguards. If heavy operations must be permitted, separate endpoints, authentication, authorization, auditing, rate limits, and approvals.

### 13.2 Sampling and overhead

A bean returns numbers at read time. Reading heap usage, GC count, and thread count across three calls does not produce a **global atomic snapshot**; if the JVM is changing rapidly, the three values may reflect three different instants. Attach individual timestamps or appropriate sampling windows, and avoid using slight inconsistencies as definitive proof of a causal chain.

Polling every few tens of milliseconds can add overhead without improving conclusion quality. Conversely, polling every 5 minutes can miss brief spikes. Choose frequency based on symptoms and combine scheduled metrics with event traces/JFR when investigating deeply.

### 13.3 Counter resets, GC changes, and JVM instance changes

If a service restarts, RuntimeMXBean uptime drops and GC/class-loading counters begin a new cycle. During autoscaling, a new instance starts with counters near 0 and old instances can disappear. Compute **rate/increase per instance before aggregating**; do not subtract raw fleet totals when instance counts change.

Do not cache GarbageCollectorMXBean names, MemoryPoolMXBean names, or list indices as an immutable contract across versions. Record VM version, collector, and ObjectName in observation metadata.

### 13.4 Viewing permissions and sensitive data

RuntimeMXBean.getInputArguments() can contain JVM options, file paths, or sensitive arguments. JMX management interfaces can reveal system configuration details. Heap dumps can contain credentials, customer data, and session state. Protect viewing permissions, storage, output paths, retention periods, and redaction.

Remotely, **unsecured JMX is an attack surface**. Do not expose a JMX/RMI connector to the Internet or unrestrictedly across an entire cluster "just to read CPU". Some operations genuinely have control capabilities, and even read-only data can be sensitive.

## 14. Common misconceptions and errors

| Mistake | Why it is wrong | Correct approach |
| --- | --- | --- |
| "ManagementFactory only has HotSpot interfaces" | Core API lives in Java SE java.management | Use java.lang.management first |
| "com.sun.management is a standard Java SE API" | It is a JDK extension in jdk.management | Design fallbacks and check module/vendor |
| "OperatingSystemMXBean has the same method names so either import works" | Standard and extension interfaces have different method sets | Use fully qualified type or explicit import |
| "getPlatformMXBean for GC collector returns a singleton" | GC bean is multi-instance | Use getPlatformMXBeans/list |
| "getPlatformMXBean always returns a bean" | Optional singleton platform beans may be unsupported | Handle null/IllegalArgumentException per contract |
| "GC/pool lists have a fixed order" | JVM can change count/names/order | Identify by bean metadata, not by index |
| "getHeapMemoryUsage.used = RSS" | Heap is only part of the footprint | Use OS/container/native memory metrics when needed |
| "MemoryUsage.max = -1 means no memory allocated" | -1 means undefined | Mark status unavailable, do not divide by -1 |
| "GC collection time is p99 pause" | Cumulative total time is not a distribution | Check GC logs/JFR/histograms |
| "Thread count = request throughput" | Thread count is a gauge | Check request counter/rate and in-flight requests |
| "ProcessCpuTime = process CPU%" | It is cumulative CPU nanoseconds | Take delta over time, normalize carefully |
| "Having platform MBeanServer means a JMX port is open" | Local MBeanServer differs from remote connector | Check connector and security configuration |
| "MBeanServer.getAttribute returns MemoryUsage" | MXBeans over JMX use OpenType mapping | Handle CompositeData or use typed proxy |
| "Enabling thread CPU time is always free" | Can incur overhead and change measurement state | Check support/permissions/before-and-after |
| "DumpHeap is just a harmless getter" | Can consume heavy resources and leak data | Require approval and impact assessment |
| "Other JVM vendors definitely have getProcessCpuLoad()" | It is an extension, may be missing/unsupported | Capability detection and fallback |
| "Changing JDK modules does not affect deployment" | Custom runtime image may omit jdk.management | Check jlink/module graph during build |

## 15. Practice exercises and answers

### Exercise A – Choosing standard beans

**Question:** You need to know heap used, live thread count, uptime, and available processors of a Java 17 JVM. Do you need com.sun.management?

**Answer:** No. Use MemoryMXBean, ThreadMXBean, RuntimeMXBean, and java.lang.management.OperatingSystemMXBean via ManagementFactory. These are standard interfaces, sufficient to read all four metrics.

### Exercise B – One or many beans?

**Question:** Why is calling getPlatformMXBean(GarbageCollectorMXBean.class) inappropriate, whereas getPlatformMXBean(MemoryMXBean.class) makes sense?

**Answer:** MemoryMXBean is a singleton platform MXBean; GarbageCollectorMXBean is a type that can have multiple instances. Use getPlatformMXBeans(GarbageCollectorMXBean.class) or getGarbageCollectorMXBeans().

### Exercise C – API boundary

**Question:** Java code only imports java.lang.management.OperatingSystemMXBean yet calls getProcessCpuTime(). Why does javac report no such method?

**Answer:** The method belongs to the com.sun.management.OperatingSystemMXBean interface in the jdk.management module, not the standard OS bean interface. You need the JDK extension, appropriate module, implementation check, and handling for -1 when unsupported.

### Exercise D – JMX OpenType

**Question:** Within the same JVM, getHeapMemoryUsage() returns MemoryUsage while MBeanServer.getAttribute("java.lang:type=Memory","HeapMemoryUsage") can return CompositeData. Is this a data mismatch?

**Answer:** No. MXBean mapping converts complex Java types into JMX OpenTypes for clients; you can use a typed proxy for convenient mapping.

### Exercise E – Sentinel and arithmetic

**Question:** MemoryUsage.getMax() returns -1. Is computing 100 × used/max to report heap percentage valid?

**Answer:** No. Max is undefined, so the ratio is meaningless. Use another metric or represent "unknown" explicitly.

### Exercise F – GC delta

**Question:** Collector A has collectionCount go from 120 to 132 over 60 seconds with no reset. What is the collector's rate?

**Answer:** 12/60 = 0.2 collections/s. The result does not tell you p95/p99 GC pause. If either snapshot returned -1, the formula cannot be used.

### Exercise G – Runtime image compatibility

**Question:** A project uses the java.management module, but after adding an import of com.sun.management and packaging a minimal jlink image, the service fails to start. What possibility should be checked?

**Answer:** The image might not contain jdk.management; inspect the module graph and JVM build, then either package the extension properly or isolate an optional adapter. Do not mistake a module error for the JVM lacking standard CPU metrics.

### Exercise H – Production debugging

**Question:** A dashboard wants to take a heap dump every 10 seconds to "measure memory". Is that reasonable?

**Answer:** No. Heap dumps are heavy and contain sensitive data; use MemoryMXBean/MemoryPoolMXBean for monitoring, and only dump under control when object retention analysis is needed.

### Exercise I – Remote JMX

**Question:** Code calls getPlatformMBeanServer() and then port 9010 is not open. Is that a bug?

**Answer:** No. Retrieving the local MBeanServer does not automatically create a remote JMX connector; to connect remotely, a secure connector must be configured according to environment policy.

### Exercise J – CPU time and CPU load

**Question:** ProcessCpuTime increases by 120 billion nanoseconds over 60 wall-clock seconds. Does 120 billion mean "120% CPU"?

**Answer:** No. The CPU-time/wall-time ratio is \(120\,s / 60\,s = 2\) CPU-seconds/second on average; that could be roughly two cores fully utilized during that time. To express %, you must define the denominator as one core, available processors, or quota, and account for how the runtime/OS measures it.

## 16. API selection checklist for runtime diagnostics

Before adding an MXBean measurement line to a service, answer for yourself:

1. **Question:** do I need a gauge, counter, rate, or distribution?
2. **Standard or extension:** is a Java SE API in java.lang.management sufficient to answer it?
3. **Module:** does the project have java.management; if using a JDK extension, is jdk.management in the runtime image?
4. **Multiplicity:** is this interface singleton or multi-instance? Can it be null/empty?
5. **Unit:** bytes, milliseconds, nanoseconds, classes, threads, load average, or ratio?
6. **Sentinel:** can the method return -1, null, or throw UnsupportedOperationException?
7. **Time:** which JVM's snapshot, when, and was there a process restart or GC change?
8. **Cost:** is it a lightweight getter or an operation capturing stacks/dumpHeap/mutating state?
9. **Security:** could data be sensitive, is the JMX server secured, and are operations authorized?
10. **Fallback:** when the extension does not exist, do we report unavailable or use another metric?
11. **QA:** has it been tested on the actual JDK/vendor/GC/container and cross-checked against logs/JFR/OS metrics?

A good report does not state "CPU=0 because MXBean is unsupported"; it states "process CPU metric unavailable" and looks for another source. It does not state "high GC time caused latency" without timestamped data, pause distributions, and corroborating traces.

## 17. Official references

- Java SE 17 – ManagementFactory: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ManagementFactory.html
- Java SE 17 – standard OperatingSystemMXBean: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/OperatingSystemMXBean.html
- Java SE 17 – ThreadMXBean: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadMXBean.html
- Java SE 17 – MemoryUsage: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryUsage.html
- Java SE 17 – GarbageCollectorMXBean: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/GarbageCollectorMXBean.html
- JDK 17 – com.sun.management package: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.management/com/sun/management/package-summary.html
- JDK 17 – OperatingSystemMXBean extension: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.management/com/sun/management/OperatingSystemMXBean.html
- JDK 17 – HotSpotDiagnosticMXBean: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.management/com/sun/management/HotSpotDiagnosticMXBean.html

Read the Javadoc matching the exact **version and implementation** of the running JVM. Bean types, methods, and default behavior can evolve across JDKs/VMs.

## Key takeaways

**ManagementFactory** is the gateway to platform MXBeans. **java.management / java.lang.management** is the standard foundation for reading memory, threads, runtime, operating system, class loading, and GC. **jdk.management / com.sun.management** extends JDK/HotSpot diagnostic information, which is useful but **must not be assumed portable**. Choose standard interfaces first, check capabilities and sentinels, distinguish singletons from lists, understand OpenTypes when going through JMX, and separate state-mutating operations from monitoring. Clarity on API contracts, units, and runtime scope is what makes MXBean metrics trustworthy evidence in Java diagnostics.