# 7.2 Accessing MXBeans directly, via MBeanServerConnection, or via proxy

> **Java Advance – runtime-diagnostics** · **7. JMX**

## 1. One JVM management datum, three access paths

When you need to know how many bytes of heap are in use, how many threads exist, or how many times a garbage collector has run, Java provides **platform MXBeans**. The same MXBean can be accessed through multiple paths depending on whether your code runs **inside the target JVM** or in **another observability tool**, and whether you prefer working with **strongly typed Java interfaces** or with **JMX ObjectNames/attributes/operations**.

Three central paths:

1. **Direct:** call a *ManagementFactory* getter inside the Java process itself, receive an interface such as *MemoryMXBean*, and call *getHeapMemoryUsage()*.
2. **Via MBeanServerConnection (raw JMX):** use an *ObjectName* to read attributes, fetch MBean metadata, or invoke operations. If an attribute has a complex Java type, the data may have been mapped into *CompositeData* or *TabularData*.
3. **Via MXBean proxy (typed JMX):** obtain an object implementing the *MemoryMXBean* interface that actually **forwards** calls over an *MBeanServerConnection*. The proxy handles MXBean type mapping more conveniently than raw JMX.

**Key point:** *direct bean*, *MBeanServerConnection*, and *typed proxy* are **access paths**, not three different sets of measurements. The data can originate from the exact same bean, while **cost**, **remote reachability**, **value representation**, **failures**, and **security boundaries** differ.

By the end of this lesson, you will be able to:

- Distinguish direct MXBean calls from access over a JMX transport.
- Understand *MBeanServer*, *MBeanServerConnection*, *JMXConnector*, *ObjectName*, and *MXBean proxy*.
- Retrieve the *HeapMemoryUsage* attribute properly over JMX and handle *CompositeData*.
- Create typed proxies using *ManagementFactory.getPlatformMXBean(connection, ...)* or *newPlatformMXBeanProxy(...)*.
- Handle **single-instance** vs. **multi-instance** platform beans.
- Write a standalone Java 17+ program demonstrating all three access paths with verifiable stdout.
- Use remote JMX when authorized, handle connection failures, and avoid dangerous management endpoint configurations.

## 2. Architecture diagram: bean, server, connector, and client

~~~text
                        TARGET JVM PROCESS
+------------------------------------------------------------------+
|                                                                  |
|  Code running in the same JVM                                    |
|        |                                                         |
|        | A. Direct call                                          |
|        v                                                         |
|  ManagementFactory.getMemoryMXBean()                             |
|        |                                                         |
|        v                                                         |
|  MemoryMXBean (JVM heap metrics)                                 |
|        ^                                                         |
|        | registered/managed via ObjectName                       |
|        v                                                         |
|  Platform MBeanServer                                            |
|        ^                                                         |
|        | B. Local MBeanServerConnection                          |
|        | C. MXBean proxy using local connection                  |
|        |                                                         |
+--------|---------------------------------------------------------+
         |
         | JMX Connector server (only if configured/published)
         | protocol + authentication + encryption + authorization
         v
+------------------------------------------------------------------+
|  Another JVM or host: JMX client                                 |
|      JMXConnector.getMBeanServerConnection()                     |
|        |                                                         |
|        +--> B. getAttribute(ObjectName, "HeapMemoryUsage")       |
|        |       -> CompositeData                                  |
|        |                                                         |
|        +--> C. ManagementFactory.getPlatformMXBean(              |
|                 connection, MemoryMXBean.class)                  |
|                  -> typed proxy -> MemoryUsage                    |
+------------------------------------------------------------------+
~~~

Read the paths in the diagram accurately:

- **Direct** always reads **the JVM executing that code**. Calling *ManagementFactory.getMemoryMXBean()* on your laptop cannot automatically read the heap of a service running on a server.
- **MBeanServerConnection** is the common interface for reading, writing, and browsing MBeans. It can be an *MBeanServer* in the same process or a client-side proxy to an MBeanServer **over a remote JMX connection**.
- **Proxy** still needs a connection as its forwarding channel. A proxy does not bypass firewalls, configure authentication, know the target URL on its own, or eliminate network latency.
- **The local Platform MBeanServer existing** does not mean a remote JMX listener is enabled. Connector setup, security, and network routing are completely separate steps.

### From API to measurement

| Question | Direct path | Raw MBeanServerConnection | Typed MXBean proxy |
| --- | --- | --- | --- |
| Which bean? | Getter, e.g. *getMemoryMXBean()* | *ObjectName("java.lang:type=Memory")* | Interface / exact ObjectName |
| Heap read call | *getHeapMemoryUsage()* | *getAttribute(name, "HeapMemoryUsage")* | *getHeapMemoryUsage()* |
| Return value | *MemoryUsage* | *CompositeData* via OpenType mapping | *MemoryUsage* via proxy mapping |
| Same JVM? | Yes | Possible | Possible |
| Read another JVM? | Not via direct getter | Yes, if connection is remote | Yes, if proxy uses a remote connection |
| Main error types | Bean state/support, JVM permissions | Name/attribute, JMX access, I/O if remote | Interface compatibility, JMX I/O, mapping, and runtime exceptions |
| When to use? | In-process instrumentation | Flexible tools needing MBean discovery | Clients wanting typed Java APIs without manual OpenType parsing |

The access path does not change the **unit** of a metric. For example, *MemoryUsage.getUsed()* is still measured in **bytes** whether accessed directly or via proxy.

## 3. Foundations: MBean, MXBean, OpenType, and ObjectName

### 3.1 MBean and MXBean are not two separate processes

In JMX, an **MBean** is a managed object exposing **attributes**, **operations**, and optionally **notifications**. An **MXBean** is a variant with rules mapping Java types onto **JMX OpenTypes**: primitive/basic types, arrays, *CompositeData*, *TabularData*, and other compliant types.

Why is mapping needed? A client might run on a different classpath or JDK version than the server. If an attribute returned an arbitrary server-specific Java class, the client might lack that class to deserialize it. OpenTypes allow structured data exchange without depending strictly on custom implementation classes.

For the platform memory bean:

~~~text
Direct:
MemoryMXBean.getHeapMemoryUsage()
    -> java.lang.management.MemoryUsage

Raw JMX:
connection.getAttribute(
    ObjectName("java.lang:type=Memory"),
    "HeapMemoryUsage")
    -> javax.management.openmbean.CompositeData

Typed MXBean proxy:
proxy.getHeapMemoryUsage()
    -> java.lang.management.MemoryUsage
       (proxy maps CompositeData back to the Java type)
~~~

**Never cast** a *CompositeData* returned from raw JMX directly to *MemoryUsage*. If you want to reconstruct the Java type following the CompositeData mapping, use *MemoryUsage.from(CompositeData)* or a typed MXBean proxy. If you only need the *used* field, *CompositeData.get("used")* also returns a *Long* in bytes.

### 3.2 ObjectName: logical address of an MBean inside a server

An MBean is identified by an **ObjectName** within the scope of one MBeanServer. For the standard MemoryMXBean, the conventional and specified identifier is:

~~~text
java.lang:type=Memory
~~~

This consists of **domain** *java.lang* and key property *type=Memory*; it is not the bean's Java package, PID, or hostname. Two JVMs can simultaneously have beans with the exact same ObjectName because they belong to **two separate MBeanServers/processes**.

Common platform ObjectName examples:

| Bean | ObjectName |
| --- | --- |
| MemoryMXBean | *java.lang:type=Memory* |
| RuntimeMXBean | *java.lang:type=Runtime* |
| ThreadMXBean | *java.lang:type=Threading* |
| ClassLoadingMXBean | *java.lang:type=ClassLoading* |
| OperatingSystemMXBean | *java.lang:type=OperatingSystem* |
| MemoryPoolMXBean | *java.lang:type=MemoryPool,name=<pool name>* |
| GarbageCollectorMXBean | *java.lang:type=GarbageCollector,name=<collector name>* |

Names containing *name* **vary by collector, pool, and JVM**. Once you hold a bean, **prefer bean.getObjectName()** rather than concatenating strings manually where escaping/quoting can go wrong. For JMX discovery, you can use a valid *ObjectName pattern* to find existing beans.

*ObjectName* identifies a bean **within a server**; diagnostic reports still need **host/pod/JVM instance/PID and timestamp** to identify the source server. You cannot conclude two rows came from the same JVM just because both have ObjectName *java.lang:type=Memory*.

### 3.3 Attributes and methods do not share the same name syntax

From the Java getter *getHeapMemoryUsage()* on MemoryMXBean, the corresponding JMX attribute is named:

~~~text
HeapMemoryUsage
~~~

Accordingly:

~~~java
// Illustrative snippet: assumes connection and memoryName already exist.
Object raw = connection.getAttribute(memoryName, "HeapMemoryUsage");
~~~

This is correct rather than calling *getAttribute* with *"getHeapMemoryUsage()"* or *"heapUsed"*. Attribute names are **case-sensitive** and described in `MBeanInfo`. For boolean getters, properties, and operation signatures, inspect the JMX contract instead of guessing every name by stripping the `get` prefix.

Read the list of exposed attributes/operations with:

~~~java
// Illustrative snippet: assumes connection and memoryName already exist.
javax.management.MBeanInfo info = connection.getMBeanInfo(memoryName);
// info.getAttributes(), info.getOperations() to discover metadata.
~~~

Not every Java method on an implementation class is a JMX attribute. The MBeanServer only exposes members specified by the registered bean's management contract.

## 4. Path A: accessing MXBeans directly in-process

### 4.1 How to read in Java code

Inside the exact JVM you want to measure, you can write:

~~~java
// Snippet inside a method, not a standalone program.
java.lang.management.MemoryMXBean memory =
        java.lang.management.ManagementFactory.getMemoryMXBean();

java.lang.management.MemoryUsage usage = memory.getHeapMemoryUsage();
long usedBytes = usage.getUsed();
~~~

No URL, username, JMX port, or *JMXConnector* is required. This is convenient for:

- Controlled **internal** health/diagnostic endpoints.
- Metrics exporters running **inside the service**.
- Periodically logging selected runtime management gauges/counters.
- Measurements inside unit/integration tests of the current Java process.

**Be careful:** if this code runs in a test runner rather than the production JVM, the direct getter reads the test JVM. The *memory* variable carries no remote machine identity.

### 4.2 Getters from ManagementFactory

| Standard API | Common values |
| --- | --- |
| *getMemoryMXBean()* | Heap and non-heap usage |
| *getThreadMXBean()* | Live/peak thread counts, ThreadInfo, and conditional CPU time features |
| *getRuntimeMXBean()* | Start time, uptime, input arguments, VM name |
| *getClassLoadingMXBean()* | Loaded/unloaded class counters |
| *getOperatingSystemMXBean()* | Processor count, OS name, load average if supported |
| *getGarbageCollectorMXBeans()* | List of collectors, count/time per collector |
| *getMemoryPoolMXBeans()* | List of memory pools and usage |
| *getPlatformMBeanServer()* | Local MBeanServer; **does not open a remote JMX port** |

Calling beans directly gives a compile-time type-safe API, though **not every metric is guaranteed to be available**. For example, *getSystemLoadAverage()* can return a negative value indicating unsupported; GC collection count/time can return -1; `MemoryUsage.getMax()` can return -1. Never convert sentinel values into 0 on dashboards.

### 4.3 Single-instance vs. multi-instance types

**Singleton platform MXBeans:** MemoryMXBean, RuntimeMXBean, and ThreadMXBean typically use *getPlatformMXBean(MemoryMXBean.class)* or their dedicated getters.

**Multi-instance platform MXBeans:** GarbageCollectorMXBean and MemoryPoolMXBean require *getPlatformMXBeans(...)* (a list of 0 to many elements).

~~~java
// Illustrative snippet: runs inside a method.
var localPools = java.lang.management.ManagementFactory
        .getPlatformMXBeans(java.lang.management.MemoryPoolMXBean.class);
for (var pool : localPools) {
    System.out.println(pool.getObjectName());
}
~~~

The count, order, and names of memory pools depend on the JVM/GC; **there is no fixed stdout**. Do not call *getPlatformMXBean(GarbageCollectorMXBean.class)* as if GC has only one bean; the singleton API is strictly for interfaces specified to have at most one instance.

### 4.4 The direct path also has cost

Reading a heap snapshot or uptime is usually cheap; however, some ThreadMXBean methods gather extensive ThreadInfo/stacks, and contention monitoring requires enabling or carries noticeable overhead. Do not place *dumpAllThreads()* on an HTTP request path serving tens of thousands of requests/s just because it looks like a normal Java method.

Rule of thumb: choose an **appropriate level of detail**, sensible polling frequency, and verify whether a method **mutates state** (such as enabling contention monitoring or requesting GC) before calling it.

## 5. Path B: MBeanServerConnection and raw access

### 5.1 MBeanServerConnection is an interface, not synonymous with a network connection

*javax.management.MBeanServerConnection* defines operations such as:

- *getAttribute(ObjectName, attributeName)*, *getAttributes(...)*: read attributes.
- *getMBeanInfo(ObjectName)*: inspect MBean metadata.
- *queryNames(ObjectName pattern, QueryExp query)*: discover ObjectNames.
- *isRegistered(ObjectName)*: check whether an MBean is registered.
- *invoke(ObjectName, operation, arguments, signature)*: invoke operations.
- *setAttribute(...)* and related methods: **mutate state if permissions and the MBean allow**.

**MBeanServerConnection is not a read-only interface.** Any client with sufficient permissions can invoke state-altering operations; never expose a management endpoint as if it merely serves metrics.

To obtain a **local** connection:

~~~java
// Illustrative snippet.
javax.management.MBeanServerConnection local =
        java.lang.management.ManagementFactory.getPlatformMBeanServer();
~~~

This works because **MBeanServer implements MBeanServerConnection**. Calls through `local` still pass through the JMX abstraction and OpenType conversion, without crossing the network. Distinguish between:

~~~text
ManagementFactory.getPlatformMBeanServer()
    -> local platform server, inside the same JVM.

connector.getMBeanServerConnection()
    -> connection representing the server that JMXConnector is connected to,
       potentially in another JVM/process.
~~~

The interface name is identical so client code can work with both, yet **failure modes and latencies are not identical**.

### 5.2 Reading MemoryMXBean by ObjectName

~~~java
// Illustrative snippet; requires two initialized variables.
javax.management.ObjectName memoryName =
        new javax.management.ObjectName("java.lang:type=Memory");

Object raw = connection.getAttribute(memoryName, "HeapMemoryUsage");
javax.management.openmbean.CompositeData data =
        (javax.management.openmbean.CompositeData) raw;
long usedBytes = (Long) data.get("used");
~~~

Here *connection* can be a local or remote MBeanServerConnection. If remote, reading the attribute is **a round trip to the target JVM**; if the connection drops, the result cannot safely be replaced with 0.

For *CompositeData*, the keys of *MemoryUsage* are *init*, *used*, *committed*, and *max*. Each element has its corresponding OpenType; use *data.get("used")* to read bytes.

If you want to convert back to the standard Java type matching the mapping contract:

~~~java
// Illustrative snippet.
java.lang.management.MemoryUsage mapped =
        java.lang.management.MemoryUsage.from(data);
long used = mapped.getUsed();
~~~

When code needs only one simple attribute, raw JMX is handy. When reading many attributes with complex types, manual OpenType handling gets cumbersome; a typed proxy helps reduce mapping mistakes.

### 5.3 When is queryNames needed?

If you do not know the exact ObjectName — for example, a JVM has multiple GarbageCollectorMXBeans — **discover the registered objects**:

~~~java
// Illustrative snippet; may throw checked exceptions.
javax.management.ObjectName pattern =
        new javax.management.ObjectName("java.lang:type=GarbageCollector,*");
var names = connection.queryNames(pattern, null);
for (var objectName : names) {
    System.out.println(objectName.getCanonicalName());
}
~~~

The result is the set of ObjectNames in the queried MBeanServer; names and order may vary across JVMs. Do not rely on output order to guess the primary collector. **A successful query also speaks only for that connection's server**, not every JVM on the host.

If a client needs *CollectionCount* per collector, it can call *getAttribute* for each ObjectName. Yet for familiar platform beans, the typed API *ManagementFactory.getPlatformMXBeans(connection, GarbageCollectorMXBean.class)* is usually simpler and avoids manual ObjectName handling.

### 5.4 Exceptions when querying raw JMX

Important errors:

| Error / group | Possible meaning | What to check |
| --- | --- | --- |
| *MalformedObjectNameException* | Invalid name syntax when constructing ObjectName | Check domain, key/value, escaping |
| *InstanceNotFoundException* | No bean registered under ObjectName at query time | Query names, verify target |
| *AttributeNotFoundException* | Wrong attribute name or not exposed by bean | MBeanInfo, case-sensitive names |
| *ReflectionException/MBeanException* | Failure dispatching/executing operation or bean method | Exception message and bean contract |
| *IOException* | Remote connection failed, server unresponsive, or transport issue | Endpoint, network, connector, TLS/auth, retry policy |
| *SecurityException/authorization failure* | Policy forbids query or operation | Principal/permissions; do not disable security to test |
| *ClassCastException* | Wrong raw OpenType assumption | Inspect *CompositeType*/OpenData, apply proper MXBean mapping |

Several methods throw specific checked exceptions; do not lump them all into one catch block and assume the JVM crashed. **Missing bean**, **broken connection**, and **missing attribute** are three different conditions.

## 6. Path C: typed MXBean proxy over a connection

### 6.1 Proxy factory for platform MXBeans

Given an *MBeanServerConnection*, *ManagementFactory* provides typed proxies:

~~~java
// Illustrative snippet; requires an existing connection.
java.lang.management.MemoryMXBean memory =
        java.lang.management.ManagementFactory.getPlatformMXBean(
                connection, java.lang.management.MemoryMXBean.class);

if (memory != null) {
    long heapUsed = memory.getHeapMemoryUsage().getUsed();
}
~~~

Here *memory* implements the **MemoryMXBean interface**, yet its methods are **forwarded through the connection** by the proxy. It is not necessarily the actual bean object in the calling JVM; if the connection is remote, the **target** JVM provides the metrics.

*getPlatformMXBean(connection, Class<T>)* is for **singleton platform MXBean interfaces** and can return `null` if an optional single-instance interface is not implemented by the server. If the interface is not a platform bean or not a singleton, the API can throw *IllegalArgumentException*. With a remote connection, the factory can throw *IOException* while querying the server.

### 6.2 Proxy by specific ObjectName

If you already know the bean's name (e.g., *memoryName*), use:

~~~java
// Illustrative snippet; requires memoryName and connection.
java.lang.management.MemoryMXBean memory =
        java.lang.management.ManagementFactory.newPlatformMXBeanProxy(
                connection,
                memoryName.getCanonicalName(),
                java.lang.management.MemoryMXBean.class);
~~~

Differences:

- *getPlatformMXBean(connection, MemoryMXBean.class)* picks the singleton platform bean by **interface**, without passing an ObjectName manually.
- *newPlatformMXBeanProxy(connection, name, interface)* creates a proxy for a **specified ObjectName**, useful when targeting explicitly and validating metadata.
- Both communicate through *connection* and apply **MXBean mapping** for complex types.

Do not use *newPlatformMXBeanProxy* arbitrarily for custom MBeans that do not follow platform MXBean interfaces. For application-defined MXBeans, the JMX API provides *JMX.newMXBeanProxy(connection, objectName, CustomMXBean.class)*; that is a separate use case with its own contract.

### 6.3 Creating a proxy list for multi-instance MXBeans

~~~java
// Illustrative snippet.
var collectors = java.lang.management.ManagementFactory
        .getPlatformMXBeans(
                connection,
                java.lang.management.GarbageCollectorMXBean.class);

for (var gc : collectors) {
    System.out.println(gc.getName() + ": " + gc.getCollectionCount());
}
~~~

Each element represents one collector bean. **Do not assume the list has a single element or that G1/CMS/Shenandoah names match across JDKs.** The API permits 0, 1, or more results depending on the interface/JVM, with no guaranteed stable order.

Reading attributes sequentially across many proxies can generate **multiple network round trips**. For dashboards, calculate polling cost as beans × metrics × frequency × JVMs, avoiding redundant queries when a server is slow.

### 6.4 Typed proxy returns do not mean atomic snapshots

Calling *memory.getHeapMemoryUsage()* at time T1 and *raw getAttribute* at T2 can return **different used bytes** because the application continues allocating or running GC. That is not a proxy bug.

Likewise, calling *getHeapMemoryUsage()* followed by *getNonHeapMemoryUsage()* yields two close snapshots, not a transaction or event stream. Never write tests asserting that all three paths return **identical byte counts**. Instead check types, readability, and invariants such as non-negative used/committed values.

### 6.5 Proxy failures can surface differently from raw JMX

Methods on *MemoryMXBean* do not necessarily declare checked *IOException*. However, a proxy using an *MBeanServerConnection* can hit I/O failures during forwarding. Depending on the call, exceptions may be wrapped in a dynamic proxy runtime wrapper (e.g., *UndeclaredThrowableException*). Therefore, when writing a JMX client:

- Handle errors when **both creating and using the connection/proxy**, not only during *connect()*.
- Capture the root cause carefully, distinguishing unreachable endpoints from missing beans/attributes.
- Apply proper timeouts/retries/backoff/circuit breakers; never hammer a struggling JVM with infinite diagnostic retries.
- Keep error handling aligned with the exceptions documented in the specific method's Javadoc.

Never catch all *RuntimeException*s and substitute metric value 0; when connectivity drops, dashboards will report misleading status.

## 7. Standalone Java 17+ lab: three access paths on the same JVM

This lab demonstrates all three paths **against the local platform MBeanServer**, so **no JMX ports need opening, no credentials are required, and no external libraries are needed**. Its purpose is to verify **return shapes and API paths**, not to prove remote connectivity will succeed.

Create **MxBeanThreePathsDemo.java**:

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import java.lang.management.MemoryPoolMXBean;
import java.util.List;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.openmbean.CompositeData;

public final class MxBeanThreePathsDemo {
    public static void main(String[] args) throws Exception {
        MemoryMXBean direct = ManagementFactory.getMemoryMXBean();
        MBeanServerConnection connection = ManagementFactory.getPlatformMBeanServer();
        ObjectName memoryName = direct.getObjectName();

        Object raw = connection.getAttribute(memoryName, "HeapMemoryUsage");
        CompositeData data = (CompositeData) raw;
        long rawUsed = (Long) data.get("used");

        MemoryMXBean typed = ManagementFactory.getPlatformMXBean(
                connection, MemoryMXBean.class);
        MemoryMXBean named = ManagementFactory.newPlatformMXBeanProxy(
                connection, memoryName.getCanonicalName(), MemoryMXBean.class);

        List<MemoryPoolMXBean> localPools = ManagementFactory.getMemoryPoolMXBeans();
        List<MemoryPoolMXBean> proxiedPools = ManagementFactory.getPlatformMXBeans(
                connection, MemoryPoolMXBean.class);

        System.out.println("objectName=" + memoryName);
        System.out.println("rawIsCompositeData=" + (raw instanceof CompositeData));
        System.out.println("rawUsedNonnegative=" + (rawUsed >= 0));
        System.out.println("directUsedNonnegative="
                + (direct.getHeapMemoryUsage().getUsed() >= 0));
        System.out.println("typedUsedNonnegative="
                + (typed.getHeapMemoryUsage().getUsed() >= 0));
        System.out.println("namedUsedNonnegative="
                + (named.getHeapMemoryUsage().getUsed() >= 0));
        System.out.println("typedNameMatches=" + typed.getObjectName().equals(memoryName));
        System.out.println("namedNameMatches=" + named.getObjectName().equals(memoryName));
        System.out.println("localPoolsAvailable=" + !localPools.isEmpty());
        System.out.println("proxiedPoolsAvailable=" + !proxiedPools.isEmpty());
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac -encoding UTF-8 MxBeanThreePathsDemo.java
java MxBeanThreePathsDemo
~~~

**Program stdout on a typical Java 17+ JVM:**

~~~text
objectName=java.lang:type=Memory
rawIsCompositeData=true
rawUsedNonnegative=true
directUsedNonnegative=true
typedUsedNonnegative=true
namedUsedNonnegative=true
typedNameMatches=true
namedNameMatches=true
localPoolsAvailable=true
proxiedPoolsAvailable=true
~~~

This example has been compiled and run on the JDK, confirming the 10 stdout lines above. The boolean checks avoid depending on exact heap byte counts or pool counts (which vary by load/VM); on unusual Java SE environments without pools or differing support assumptions, the final checks may differ. **Do not treat stdout strings as a mandatory specification across every VM implementation.**

### Explaining each code branch

**Direct branch**

~~~java
MemoryMXBean direct = ManagementFactory.getMemoryMXBean();
~~~

The Java process executing the demo class itself is the measurement target.

**Raw branch**

~~~java
Object raw = connection.getAttribute(memoryName, "HeapMemoryUsage");
CompositeData data = (CompositeData) raw;
long rawUsed = (Long) data.get("used");
~~~

Fetches data through `MBeanServerConnection` and receives an **OpenType**. This operation reads a single attribute. There is no direct cast from raw to *MemoryUsage*.

**Typed branch (singleton interface)**

~~~java
MemoryMXBean typed = ManagementFactory.getPlatformMXBean(
        connection, MemoryMXBean.class);
~~~

Creates a typed proxy interface for the platform memory bean over `connection`. In this program, the connection is local. If replaced with an appropriate remote connection, **the typed proxy logic is the same**, though errors, connectivity, and permissions must be handled separately.

**Named proxy branch**

~~~java
MemoryMXBean named = ManagementFactory.newPlatformMXBeanProxy(
        connection, memoryName.getCanonicalName(), MemoryMXBean.class);
~~~

Selects the bean by **specific ObjectName**, rather than letting the factory locate it from a singleton interface.

**List branch**

~~~java
List<MemoryPoolMXBean> proxiedPools = ManagementFactory.getPlatformMXBeans(
        connection, MemoryPoolMXBean.class);
~~~

Demonstrates that for **multi-instance** platform beans, you use a list of typed proxies instead of trying to look up a single bean.

### What the lab does not prove

- It does not prove remote JMX is open or secured. The code uses only the local platform MBeanServer.
- It does not prove the three *used* readings occurred simultaneously; they are read sequentially.
- It does not prove all implementations share the same GC/pool names or counts.
- It does not verify every operation on `MBeanServerConnection` is read-only.
- It does not benchmark overhead across thousands of JVMs; benchmarking requires testing under realistic load.

The lab is sufficient to see **API and data-type differences** before moving on to actual remote connections.

## 8. Accessing another JVM: JMXConnector and remote MBeanServerConnection

### 8.1 Where does a remote connection fit?

In an environment with a **properly configured and secured** remote JMX connector, a client can use:

~~~text
JMXServiceURL
     |
JMXConnectorFactory.connect(url, environment)
     |
JMXConnector
     |
getMBeanServerConnection()
     |
MBeanServerConnection (to target JVM)
     |
getAttribute(...) or platform MXBean proxy
~~~

*JMXServiceURL* is the address of the **JMX connector**, not an application HTTP endpoint URL. An RMI URL might use the scheme *service:jmx:rmi:///jndi/rmi://host:port/name*; exact address, port mapping, DNS, server endpoint, and TLS/auth depend on the deployment.

Specifically with RMI, understand that the **RMI registry port** and **RMI server endpoint** may differ. Inside Docker/Kubernetes/NAT, exposing only one port without configuring the server hostname/port properly can allow clients to retrieve the stub yet fail on the subsequent connection. Never "fix" this by disabling authentication or TLS.

### 8.2 Structurally safe remote client illustration

The code below is a **snippet, not a standalone program**: it assumes *url* is a valid *JMXServiceURL* pointing to an operations-approved endpoint, and *environment* is a *Map<String, ?>* supplied by a secure connection layer (containing appropriate authentication/TLS/connector settings). It contains no hardcoded credentials and does not enable servers or disable security:

~~~java
// Snippet inside a method declaring checked exceptions.
// url: JMXServiceURL to a managed connector.
// environment: Map<String, ?> with preconfigured secure connection settings.
try (javax.management.remote.JMXConnector connector =
        javax.management.remote.JMXConnectorFactory.connect(url, environment)) {
    javax.management.MBeanServerConnection remote =
            connector.getMBeanServerConnection();

    java.lang.management.MemoryMXBean memory =
            java.lang.management.ManagementFactory.getPlatformMXBean(
                    remote, java.lang.management.MemoryMXBean.class);

    if (memory != null) {
        long usedBytes = memory.getHeapMemoryUsage().getUsed();
        // Record usedBytes along with target JVM identity and timestamp.
    }
}
~~~

**Mandatory notes:**

- This is **not** a standalone runnable example: it lacks endpoint, DNS, protocol, and credential/TLS configuration. Its goal is to show **how to use a connection once securely obtained**.
- *JMXConnector* must be closed to release resources, handled here via *try-with-resources*.
- Opening a connection does not guarantee subsequent getters will succeed; the target JVM might restart, the network might drop, permissions might be revoked, or the server might overload.
- Results must be tagged with the **target's identity** (host/pod/JVM start time), not merely the ObjectName.
- Never place passwords in command-line examples or log credentials; never disable SSL/authentication for quick production testing.

**Security design:** restrict network reachability, enable authentication and TLS per policy, enforce least privilege, and audit access. Remote JMX can reach administrative operations; a username meant only for "viewing metrics" must be restricted rather than given full privileges by default. When diagnosing from operator workstations, prefer approved administrative channels over exposing JMX to the public Internet.

### 8.3 Local JMX and remote JMX do not share the same failures

| Condition | Local connection | Remote connection |
| --- | --- | --- |
| Connection creation | *getPlatformMBeanServer()* | Typically via *JMXConnectorFactory.connect()* |
| Network issues | No network needed | DNS, firewall, NAT, RMI/TLS, timeouts |
| Auth/authorization | Local process/JMX policy permissions | Connector authentication, TLS, and MBean permissions |
| JVM restart | Process/local data ends | Stale connection, controlled reconnect needed |
| Overhead | Depends on bean/mapping | Mapping + marshalling + network + round trips |
| Dynamic metrics | Changing snapshots | Changing snapshots plus network delay |
| ObjectName/attribute errors | Possible | Possible, plus connection failures |

**A passing local test does not prove remote production access will work.** You must verify the server endpoint, user/role, TLS, network routing, and version compatibility in the real environment.

## 9. Which path to choose for each need?

| Scenario | Preferred choice | Reason |
| --- | --- | --- |
| In-service exporter reading heap/threads | Direct platform MXBean | No connection management, type-safe |
| Internal actuator/health with a few JVM metrics | Direct, if endpoint policy allows | Simple, avoids JMX transport overhead |
| Generic JMX client listing beans and metadata | Raw MBeanServerConnection | *queryNames*, *getMBeanInfo*, runtime discovery |
| Java dashboard needing MemoryMXBean specifically | Typed proxy | *getHeapMemoryUsage()* returns *MemoryUsage*, less manual OpenType parsing |
| Targeting a bean by specific ObjectName | *newPlatformMXBeanProxy()* | Explicit control of bean identity |
| Listing collectors/pools on a remote JVM | *getPlatformMXBeans(connection, Interface.class)* | No guessing counts/names, typed list |
| Custom MXBean registered by application | Raw JMX or *JMX.newMXBeanProxy()* | Not necessarily a platform interface |
| Extension bean not guaranteed across JVM/OS/vendors | Standard APIs first, capability check then fallback | Portable and avoids ClassNotFound/NoClassDefFoundError |
| Heap dumps, changing VM options, or triggering GC | Separate approved diagnostic workflow | Not treated as lightweight monitoring getters |

There is no single "fastest" way in absolute terms. For in-JVM code with a few getters, direct access is simplest. For generic tools, `MBeanServerConnection` is foundational; for application clients wanting strong typing, proxies are more convenient. Yet remote cost depends on call count and network overhead, not just proxy instantiation.

## 10. Common programming pitfalls

### 10.1 Getting a typed object from a connection is not getting the local bean

These two lines share the *MemoryMXBean* type yet read from different places:

~~~java
// Illustrative snippet.
var local = java.lang.management.ManagementFactory.getMemoryMXBean();
var viaConnection = java.lang.management.ManagementFactory
        .getPlatformMXBean(connection, java.lang.management.MemoryMXBean.class);
~~~

If `connection` is remote, *viaConnection* measures the **target** JVM, while *local* measures the **client** JVM. Never merge both results into one series without recording the instance. This is a common bug when testing in a local IDE and porting to a monitoring backend.

### 10.2 Raw getAttribute returns OpenTypes

Wrong:

~~~java
// Wrong code: CompositeData cannot be cast directly to MemoryUsage.
java.lang.management.MemoryUsage usage =
        (java.lang.management.MemoryUsage)
        connection.getAttribute(memoryName, "HeapMemoryUsage");
~~~

Right:

~~~java
// Illustrative snippet.
javax.management.openmbean.CompositeData data =
        (javax.management.openmbean.CompositeData)
        connection.getAttribute(memoryName, "HeapMemoryUsage");
java.lang.management.MemoryUsage usage =
        java.lang.management.MemoryUsage.from(data);
~~~

Or use a *MemoryMXBean* typed proxy so the proxy handles the mapping.

### 10.3 Not every bean is a singleton

Wrong: trying to read *GarbageCollectorMXBean* via the singleton platform MXBean getter.

Right: call *ManagementFactory.getPlatformMXBeans(connection, GarbageCollectorMXBean.class)* or the local list getter.

GC/MemoryPool names vary across G1, Parallel, ZGC, Shenandoah, JDK versions, and vendors; never hardcode "the second collector is always Old GC."

### 10.4 ObjectName is not a process URL and is not unique across JVMs

*java.lang:type=Memory* identifies the memory bean **within one MBeanServer**. If a client holds two MBeanServerConnections to two different JVMs, the same ObjectName represents two beans **in two different places**. Always attach host/container/process start time when storing metrics.

### 10.5 Creating a proxy does not guarantee the bean exists at all times

Optional platform beans may be absent, and multi-instance beans can change at runtime. Before reading attributes, check for null/empty per the API contract, or *isRegistered* for a specific ObjectName when needed. Still, **pre-checking does not eliminate race conditions**: a bean can disappear right after *isRegistered*. Handle failures on the actual operation.

### 10.6 JMX operations can mutate the JVM

*invoke*, *setAttribute*, and some MXBean operations belong to the control plane. For instance, requesting GC, enabling thread contention monitoring, or invoking HotSpot diagnostic operations can incur overhead or risk. Never grant a dashboard that only needs *getAttribute* permission to invoke arbitrary operations. JMX authorization depends on connector/policy; never assume an interface is read-only.

### 10.7 Remote JMX errors can be buried inside a dynamic proxy

A typed proxy invokes methods that do not declare checked `IOException`, yet the underlying remote connection performs I/O. Some errors may be wrapped by dynamic proxy wrappers. Log the root cause selectively, record the endpoint identifier, and never conflate connection errors with sentinel metrics.

### 10.8 Java SE APIs and JDK extensions are not uniform

MemoryMXBean in *java.lang.management* is standard; certain deep process CPU/GC metrics reside in *com.sun.management* (module *jdk.management*). JDK extension interfaces are not guaranteed on every vendor or runtime image. Never assume *ManagementFactory* implies every extension is present. Design fallbacks rather than unchecked casts.

## 11. Reading metrics meaningfully, not just retrieving values

Having a working connection and valid code still does not mean the numbers make sense.

### 11.1 Asynchronous snapshots

In the lab, *direct*, *raw*, *typed*, and *named* read heap used **sequentially**. GC/allocations between calls can change the byte counts. Never assert exact equality, especially over remote connections.

To plot values over time, capture a timestamp with each sample and retain JVM identity; never substitute the collector's polling timestamp for event timestamps when analyzing very short pauses.

### 11.2 Different measurement semantics

| MXBean method | Unit / kind | Notes |
| --- | --- | --- |
| *MemoryUsage.getUsed()* | bytes / gauge | Heap/non-heap within bean scope, not process RSS |
| *MemoryUsage.getCommitted()* | bytes / gauge | Committed memory, distinct from used |
| *MemoryUsage.getMax()* | bytes or -1 | -1 means undefined limit |
| *ThreadMXBean.getThreadCount()* | threads / gauge | Not request throughput |
| *RuntimeMXBean.getUptime()* | milliseconds / elapsed time | Resets on JVM restart |
| *GarbageCollectorMXBean.getCollectionCount()* | count or -1 | Cumulative counter if supported |
| *GarbageCollectorMXBean.getCollectionTime()* | milliseconds or -1 | Not equal to p99 GC pause |
| *ClassLoadingMXBean.getTotalLoadedClassCount()* | count | Cumulative counter; differs from currently loaded classes |
| *OperatingSystemMXBean.getSystemLoadAverage()* | load average or negative | Not CPU% and may be unavailable |

Counters require computing deltas/rates on the **same instance** while handling restarts. Never subtract a pre-restart GC count from a post-restart count and report a negative result as "negative GCs." Sentinel -1/null values must never appear on dashboards as 0. Standard bean metrics still require proper interpretation, sampling, and metadata.

### 11.3 Remote cost and N+1 calls

Suppose a monitoring client polls 200 JVMs, reading 15 attributes each every 5 seconds. In a naive design, that generates roughly **3,000 attribute reads per cycle** before counting connects, metadata, or retries. Each read is not necessarily a new TCP connection, yet round trips and serialized payload volume can be substantial.

Optimization strategies:

- Select only genuinely needed metrics; avoid querying every MBean just to populate one gauge.
- Use *getAttributes* with result checks where appropriate to cut overhead vs. many single-attribute reads.
- Cache metadata/ObjectNames sensibly while refreshing after restarts/reconfiguration; **never cache metric measurements** as if static.
- Batch per server, bound concurrency, enforce timeouts/backoff, and monitor collector errors.
- Read histograms/GC logs/JFR for event-distribution questions; cumulative MXBean totals cannot replace them.
- If the system already uses an internal Prometheus/OpenTelemetry exporter, there is no reason to open a new remote JMX port.

## 12. Diagnostic workflow when three paths yield different results

Suppose an in-service direct getter reports one heap used value while a remote JMX dashboard shows another. **Do not jump to concluding the proxy is broken.**

### Step 1 – Verify the exact JVM

- Which JVM executes the direct code?
- Which pod/host/JVM does the remote URL target?
- Did the process restart between the two snapshots?
- Could a load balancer, sidecar, or registry be pointing at the wrong target?

Two beans both named *java.lang:type=Memory* on two different JVMs can legitimately report completely different values.

### Step 2 – Verify the exact metric and unit

- *HeapMemoryUsage* or *NonHeapMemoryUsage*?
- *used*, *committed*, *init*, or *max*?
- Bytes or MiB? \(1\,\mathrm{MiB}=1{,}048{,}576\) bytes.
- Were the reads close in time? Did GC happen between them?

### Step 3 – Verify raw OpenType mapping

- Did raw *getAttribute* return *CompositeData* per the contract?
- Is the *used* field a *Long* in bytes?
- Did code mis-cast *CompositeData → MemoryUsage*?
- Are client and server JDK versions compatible for proxy mapping?

### Step 4 – Verify connectivity and authorization

- Does a real remote JMX connector exist?
- Are protocol/hostname/RMI endpoint/port/TLS/auth all correct?
- Does the account have permission to read that MBean?
- Is the remote server still healthy, or do errors appear only when the JVM is overloaded?

### Step 5 – Verify error handling in the app

- Are *IOException*s silently converted into 0?
- Is stale cached data displayed without a staleness indicator?
- Are aggressive retries increasing load on the target?
- Are multiple JVMs merged into a single series without an instance label?

**Correct conclusion:** If raw and proxy share **the same connection + ObjectName + close timestamps**, they must follow the same value contract; small differences in bytes come from snapshot timing. If only one path fails at the same instant, inspect mapping, access policy, or the exact exception instead of guessing.

## 13. Practical exercises with solutions

### Exercise 1 – Classifying three statements

**Given:**

~~~java
// Illustrative snippet.
var a = java.lang.management.ManagementFactory.getMemoryMXBean();
var b = connection.getAttribute(memoryName, "HeapMemoryUsage");
var c = java.lang.management.ManagementFactory.getPlatformMXBean(
        connection, java.lang.management.MemoryMXBean.class);
~~~

**Question:** Which line always reads the JVM executing the code? Which lines can read a remote JVM?

**Answer:** *a* is the direct bean of the current JVM. *b* is raw JMX and *c* is a typed MXBean proxy; both *b* and *c* access whichever JVM **connection** points to, whether local or remote.

### Exercise 2 – Identifying data types

**Question:** Why does a method declared to return *MemoryUsage* yield a *CompositeData* value when read via raw JMX?

**Answer:** MXBeans convert Java values into JMX OpenTypes when accessed through the MBeanServer interface. Typed MXBean proxies convert them back to Java types. You can parse *CompositeData* or call *MemoryUsage.from()*.

### Exercise 3 – Missing CPU method on OperatingSystemMXBean

**Question:** You obtain *java.lang.management.OperatingSystemMXBean* and try calling *getProcessCpuTime()*, but `javac` cannot find the method. Is this caused by using a proxy?

**Answer:** No. *getProcessCpuTime()* belongs to the JDK extension interface *com.sun.management.OperatingSystemMXBean*, not the standard Java SE interface. You need a compatible module/vendor and fallback logic; switching between direct and proxy will not add methods to the standard interface.

### Exercise 4 – Reading GarbageCollectorMXBean from a remote JVM

**Question:** Why should you avoid *getPlatformMXBean(connection, GarbageCollectorMXBean.class)*?

**Answer:** There can be multiple GC collector beans; the singleton method does not fit. Use *getPlatformMXBeans(connection, GarbageCollectorMXBean.class)* and iterate over the list without relying on indices.

### Exercise 5 – Local MBeanServer

**Question:** A program called *ManagementFactory.getPlatformMBeanServer()*. Does that guarantee a JMX client on another machine can connect?

**Answer:** No. It only provides the local server. Remote access requires a connector/service URL plus separate security and network configuration.

### Exercise 6 – Wrong cast

**Question:** What error does a direct cast *MemoryUsage usage=(MemoryUsage) connection.getAttribute(...)* usually cause?

**Answer:** A runtime *ClassCastException* when the raw attribute is *CompositeData*. You must parse the OpenType or use a typed proxy.

### Exercise 7 – Errors from a remote proxy

**Question:** *JMXConnectorFactory.connect()* succeeded, yet minutes later *proxy.getHeapMemoryUsage()* fails. Why?

**Answer:** The connection may have dropped afterward, the JVM restarted, a firewall/NAT timed out, permissions changed, or the server became unresponsive. A proxy uses the remote connection on every call; you need runtime error handling and controlled reconnect/backoff.

### Exercise 8 – Two different heap numbers

**Question:** Direct reads 120 MiB, raw reads 116 MiB, and proxy reads 118 MiB. Does this prove one API is buggy?

**Answer:** No. JVM allocations/GC can run between snapshots. Check timestamps, same instance, and the same *used* field. Never write tests assuming three separate reads must be equal.

### Exercise 9 – Does ObjectName distinguish processes?

**Question:** Two JVMs both have *java.lang:type=Memory*. Are they the same MXBean object on one host?

**Answer:** No. ObjectName is scoped to each MBeanServer. Attach endpoint/JVM identity to distinguish them.

### Exercise 10 – Permission scoping

**Question:** A dashboard only needs heap used, yet it is granted every JMX operation, including triggering GC and heap dumps. Is this "read-only monitoring"?

**Answer:** No. Administrative privileges are far too broad; separate read-only access, restrict operations, and secure transport/authentication/TLS.

### Exercise 11 – Computing rate from GC MXBean

**Question:** A collector's *CollectionCount* rises from 40 to 70 over 150 seconds with no restart, and both snapshots are valid. What is the average rate?

**Answer:** \((70-40)/150=0{,}2\) collections/s. This figure does not reveal p99 pauses; use GC logs/JFR or distribution data for that.

### Exercise 12 – QueryNames returning multiple MBeans

**Question:** *queryNames("java.lang:type=MemoryPool,*")* returns 8 names. Should you label them "memoryPool1...memoryPool8" based on set order?

**Answer:** No. Set ordering has no stability contract. Use the ObjectName/canonical name, pool name, and memory type to identify them; results can vary on later runs.

## 14. Practical checklist before deploying JMX monitoring

**Target layer**

- Which exact JVM is it? Do you know the host, PID or pod/container, and start time?
- Is the bean/interface guaranteed by Java SE or is it a vendor/JDK extension?
- Singleton or multi-instance? Handled null/empty/-1/unsupported?
- Does the ObjectName/attribute exist per *getMBeanInfo* or the standard contract?

**Connection layer**

- Does direct code run inside the target JVM or on the client?
- Is the connection a **local MBeanServer** or a **remote JMXConnector**?
- When remote, are endpoint, RMI port mapping, firewall, TLS, authentication, and authorization correct?
- Does the client close the connector and bound concurrency/retries?

**Data layer**

- What OpenType does raw access return? Is CompositeData parsed per schema?
- Does the proxy have a compatible interface and valid mapping?
- What unit is used, is it a gauge or counter, and does it need a delta?
- Are timestamp and instance labels sufficient to correlate across readings?
- Are unavailable metrics distinguished from 0, and stale data from fresh data?

**Operations and safety layer**

- Are frequency, overhead, and round trips reasonable under high load?
- Are root-cause exceptions logged without leaking credentials/secrets?
- Are remote JMX endpoints protected from overly broad/public exposure?
- Are dashboards needing only getters restricted from state-changing operations?
- Are corroborating paths available via app metrics, GC logs, JFR, or OS metrics when needed?

## 15. Official documentation for your JDK version

- **ManagementFactory — Java SE 17**, direct getters, local/remote platform MXBean proxies, and multi-instance access: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ManagementFactory.html
- **MemoryMXBean — Java SE 17**: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryMXBean.html
- **MemoryUsage — Java SE 17**, including *from(CompositeData)*: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryUsage.html
- **MBeanServerConnection — Java SE 17**, getAttribute/queryNames/getMBeanInfo/invoke: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/javax/management/MBeanServerConnection.html
- **JMX — Java SE 17**, OpenTypes mapping and typed MXBean proxies: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/javax/management/JMX.html
- **CompositeData — Java SE 17**: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/javax/management/openmbean/CompositeData.html
- **JMXConnectorFactory — Java SE 17**: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/javax/management/remote/JMXConnectorFactory.html
- **JMX remote API — Java SE 17**: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/javax/management/remote/package-summary.html
- **Oracle JMX Security — Java SE 17**: https://docs.oracle.com/en/java/javase/17/jmx/security.html

Remote JMX capabilities and policies depend on JDK version, vendor, runtime flags, connector, and actual security configuration. Cross-check documentation against the exact environment you are diagnosing.

## Conclusion

**Direct MXBeans** fit when code runs in the **same JVM** and wants strongly typed Java getters. **MBeanServerConnection** provides general-purpose access via *ObjectName, attribute, and operation*, either locally or remotely. **Typed MXBean proxies** sit atop a connection, turning calls into convenient Java interfaces and handling MXBean mapping automatically—yet they **do not eliminate** network I/O, authorization, timeouts, or operational risk.

A trustworthy measurement requires **the right target JVM, the right bean, the right attribute/unit, the right timestamp, and the right permissions**. Choose the access path based on where code executes and whether you need discovery or typing, never simply because it compiles.