# JMX-Supported Property Types in Spring @ManagedAttribute

## 1. Why Understand JMX Attribute Data Types?

In Spring Framework JMX, \`@ManagedAttribute\` marks getters or setters to be exposed as an MBean's **JMX attribute**. However, having the annotation does not mean every Java type can be read, written, or displayed the same way by every JMX client.

Three separate questions need to be distinguished:

1. **Does Spring recognize the property as a managed attribute?** This is the role of \`@ManagedAttribute\`, \`MBeanInfoAssembler\`, and \`MBeanExporter\`.
2. **Can the MBeanServer represent the attribute's type?** For Standard MBeans, Dynamic MBeans, and Model MBeans, metadata typically reflects the Java type name; for MXBeans, the Java Management API specifies mapping to *Open Types*.
3. **Can the JMX client consume the value?** Data transfer over remote JMX depends on serialization, class availability, security filters, and client rendering capabilities. A type valid on the server is not necessarily suitable for monitoring clients outside the JVM.

This lesson helps you choose safe, stable, and observable property types while avoiding confusion between **Spring managed attributes**, **JMX attributes**, and **MXBean OpenTypes**.

### Objectives

After this lesson, you will be able to:

- Distinguish property getters/setters from actual JMX attributes.
- Understand scalar types, arrays, enums, Java objects, and OpenType structures.
- Explain differences between Standard MBean/Model MBean and MXBean.
- Select appropriate data types for a JMX management API.
- Inspect \`MBeanAttributeInfo\`, \`MBeanInfo\`, and \`OpenMBeanAttributeInfo\`.
- Design managed attributes with clear read/write semantics, avoiding dependencies on internal Java classes.

## 2. From Java Property to JMX Attribute

Example Spring bean:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.monitoring:type=Queue,name=Orders"
)
public class OrderQueueMonitor {
    private volatile int pendingCount;

    @ManagedAttribute(description = "Number of pending orders")
    public int getPendingCount() {
        return pendingCount;
    }

    @ManagedAttribute(description = "Adjust pending count")
    public void setPendingCount(int pendingCount) {
        this.pendingCount = pendingCount;
    }
}
\`\`\`

By JavaBeans convention, the \`pendingCount\` property has a getter and setter. When Spring JMX annotation metadata is processed by the appropriate exporter/assembler, it can be exported as **one JMX attribute** named \`PendingCount\`, of type \`int\`, both readable and writable.

\`\`\`text
Java methods
    getPendingCount() : int
    setPendingCount(int) : void
           |
           v
Spring JMX attribute metadata
           |
           v
JMX MBeanInfo
    name = "PendingCount"
    type = "int"
    readable = true
    writable = true
           |
           v
MBeanServer.getAttribute/setAttribute
\`\`\`

Keep in mind:

- The annotation only provides metadata. The application must enable JMX export.
- Getter and setter must match in property name and type.
- Having an exposed getter without an exposed setter makes the attribute read-only.
- Having an exposed setter without an exposed getter makes the attribute write-only if the implementation supports it.
- The setter accepting a value **does not mean** the caller is authorized to change state. JMX access control is required.

## 3. At Which Layers Does JMX Support Types?

Key concepts:

| Component | Definition | Meaning for Types |
|---|---|---|
| **Standard MBean** | Interface following the \`XxxMBean\` convention | Java methods in the interface define attribute/operation types |
| **Dynamic MBean** | Implements \`DynamicMBean\` and returns \`MBeanInfo\` | Self-defines type metadata and value handling |
| **Model MBean** | A Dynamic MBean with management descriptors | Spring can use it to expose beans with annotation metadata |
| **MXBean** | MBean adhering to MXBean type mapping rules | Parameters and values are mapped to standard JMX **Open Types** |

**Important rule:** Do not say "JMX only supports primitives and String." Ordinary MBeans can use many serializable Java types; however, compatibility across the network and across clients decreases when exposing custom application types.

Conversely, do not say "as long as it's a Java object, remote JMX will work." Not every object is serializable; remote clients may lack the class or reject deserialization.

MXBeans help solve this problem with a set of Open Types that have well-defined conversion rules.

## 4. Basic Property Types That Usually Fit Well

For managed attributes used in monitoring and operations, prefer simple types:

| Java type | Common values | Used for |
|---|---|---|
| \`boolean\`/\`Boolean\` | \`true\`, \`false\` | Toggling a feature or state |
| \`byte\`/\`Byte\` | Small integers | Cases with defined bounds |
| \`short\`/\`Short\` | Small integers | Simple metrics |
| \`int\`/\`Integer\` | \`12\` | Worker count, connection count |
| \`long\`/\`Long\` | \`120000L\` | Total task count, numeric timestamps/durations |
| \`float\`/\`Float\` | \`0.5f\` | Measurements needing decimals |
| \`double\`/\`Double\` | \`98.6\` | Ratios, floating-point metrics |
| \`char\`/\`Character\` | \`'A'\` | Single control character |
| \`String\` | \`"RUNNING"\` | Status, hostname, version |

Example:

\`\`\`java
@ManagedAttribute
public boolean isHealthy() {
    return healthy;
}

@ManagedAttribute
public long getProcessedCount() {
    return processedCount.get();
}

@ManagedAttribute
public String getStatus() {
    return "RUNNING";
}

@ManagedAttribute
public double getLoadRatio() {
    return loadRatio;
}
\`\`\`

Benefits: readable metadata, convenient client display, minimal dependency on application classes. However, \`null\` for wrappers, \`NaN\`/\`Infinity\` for floating-point types, and out-of-range values still need handling per contract.

### Which Type to Use for Status?

If status belongs to a small set of values, you can use \`String\` with a clear contract:

\`\`\`java
@ManagedAttribute(description = "IDLE, RUNNING, FAILED or COMPLETED")
public String getState() {
    return currentState.name();
}
\`\`\`

This choice is friendly to JMX clients unaware of the application's enum. If using an enum directly, check compatibility of the MBean type and remote clients.

## 5. String Type and Representation Limits

\`String\` is typically a good choice for:

- Server status.
- Build version.
- Non-sensitive configuration names.
- Instance identifiers.
- Short descriptions for operators.

However, an unstructured string has limitations:

\`\`\`java
@ManagedAttribute
public String getQueueState() {
    return "pending=14,active=3,failed=1";
}
\`\`\`

Clients must parse the custom string, which breaks easily if the format changes. For three independent values, it is usually better to expose three scalar attributes (\`PendingCount\`, \`ActiveCount\`, \`FailedCount\`) or use a structured OpenType.

Do not stuff large JSON payloads into a \`String\` and treat it as a typed API. If structure is needed, consider \`CompositeData\` or \`TabularData\` with a stable contract.

Additionally, never expose passwords, tokens, keys, or personal data via managed attributes, even as a String "just for debugging."

## 6. Arrays and Collections

### 6.1. Arrays

JMX can represent arrays across many MBean types; with MXBean/OpenType, \`ArrayType\` describes arrays of valid OpenType elements.

Example:

\`\`\`java
@ManagedAttribute(description = "Configured cluster nodes")
public String[] getNodeNames() {
    return new String[] {"node-a", "node-b"};
}
\`\`\`

A \`String\` array is relatively easy for clients to consume. Return a copy or snapshot value if internal data can be mutated concurrently.

\`\`\`java
@ManagedAttribute
public int[] getQueueDepthHistory() {
    return history.clone();
}
\`\`\`

Avoid returning a mutable internal array directly when local code can modify it. For remote clients, serialization may create a copy, but do not rely on remote behavior to protect local state.

### 6.2. List, Set, Map

\`List<String>\`, \`Map<String, Integer>\`, or custom collections do not automatically correspond to a JMX OpenType in all cases.

In Standard/Model MBeans, you may encounter serialized Java object transfers. In that case, clients must be compatible with the related types and classes. For **MXBeans**, the framework has rules mapping eligible declared types to OpenType data; mapping conditions and structures must satisfy the JMX specification.

Therefore:

- Do not assume collections are unsupported.
- Do not assume every collection can be consumed by remote clients as class-independent data.
- When designing a management API for cross-JVM systems, consider exposing clear scalars, \`String\` arrays, \`CompositeData\`, or \`TabularData\`.
- Avoid very large or rapidly changing collections, because each \`getAttribute()\` call can consume significant CPU, memory, and network bandwidth.

## 7. Enum, Date, ObjectName, and Special Types

### Enum

\`\`\`java
public enum WorkerState {
    IDLE, RUNNING, FAILED
}
\`\`\`

A Standard MBean can expose an enum as a Java type when transport and clients support it; MXBeans have rules mapping enums to an appropriate open form, usually the String name.

To make the management API easily compatible with simple clients:

\`\`\`java
@ManagedAttribute
public String getWorkerState() {
    return state.name();
}
\`\`\`

Choosing between a direct enum and a \`String\` should be based on integration scope and MBean type, not merely Java compilation capability.

### Date and Time

\`java.util.Date\` is a Java object usable in some MBeans, though it is not part of the common Open MBean \`SimpleType\` set. MXBean mapping for time types depends on specific type-mapping rules.

If clients need a stable, easily comparable value:

\`\`\`java
@ManagedAttribute(description = "Last successful run, epoch millis")
public long getLastSuccessfulRunEpochMillis() {
    return lastSuccessMillis;
}
\`\`\`

Specify the unit clearly as \`milliseconds since Unix epoch\`. Avoid exposing ambiguous \`String\` timestamps lacking timezone/format specification.

### ObjectName

\`javax.management.ObjectName\` can also appear in metadata/management systems to reference another MBean. In Open MBeans, \`ObjectName\` belongs to the supported \`SimpleType\` set.

Example reference attribute:

\`\`\`java
@ManagedAttribute
public ObjectName getSchedulerMBean() {
    return schedulerName;
}
\`\`\`

Use it when clients genuinely need the JMX identity of a related object. Do not use \`ObjectName\` as a substitute for all business IDs.

### BigDecimal, BigInteger, and Open Numeric Types

\`java.math.BigDecimal\` and \`java.math.BigInteger\` are simple types supported by OpenType. They suit values requiring specific precision, but verify that clients display/compute them properly and avoid big-number types when a \`long\` with a clear unit suffices.

## 8. Open MBeans and Standard Open Types

JMX Open MBeans define types describable via standard metadata, sparing clients from knowing custom business classes.

Classes in \`javax.management.openmbean\`:

| OpenType | Representation |
|---|---|
| \`SimpleType\` | Standard scalar types such as String, Boolean, Integer, Long, Double, BigDecimal, BigInteger, ObjectName... |
| \`ArrayType\` | Array of elements of a valid OpenType |
| \`CompositeType\` | Schema of a record/object composed of named attributes |
| \`TabularType\` | Schema of an indexed table of \`CompositeType\` records |
| \`OpenType\` | Base class describing the Open MBean type system |

Actual values:

| OpenType schema | Value object |
|---|---|
| \`SimpleType\` | Object of the corresponding simple type |
| \`ArrayType\` | Array with the appropriate element type |
| \`CompositeType\` | \`CompositeData\` |
| \`TabularType\` | \`TabularData\` |

**Distinction:** \`CompositeType\` describes the **schema**, while \`CompositeData\` holds the **data**. Similarly, \`TabularType\` is the schema and \`TabularData\` is the tabular value.

### Why Are Open Types Useful?

A class like \`com.example.internal.QueueSnapshot\` may not exist on the classpath of JConsole or a remote monitoring service. If the server sends that object directly, the client may fail to decode it.

When data is represented using \`CompositeData\`, the client only needs to know the JMX Open MBean API and schema, reducing coupling to server-side business libraries.

## 9. CompositeData Example: A Multi-Field State

Suppose we need to export a queue snapshot containing \`pending\`, \`active\`, and \`status\`. You can construct \`CompositeDataSupport\`:

\`\`\`java
import javax.management.openmbean.CompositeData;
import javax.management.openmbean.CompositeDataSupport;
import javax.management.openmbean.CompositeType;
import javax.management.openmbean.OpenType;
import javax.management.openmbean.SimpleType;

public final class QueueOpenData {

    private static final CompositeType TYPE;

    static {
        try {
            TYPE = new CompositeType(
                "QueueSnapshot",
                "Current queue status",
                new String[] {"pending", "active", "status"},
                new String[] {
                    "Pending jobs",
                    "Active jobs",
                    "State"
                },
                new OpenType<?>[] {
                    SimpleType.INTEGER,
                    SimpleType.INTEGER,
                    SimpleType.STRING
                }
            );
        } catch (Exception ex) {
            throw new ExceptionInInitializerError(ex);
        }
    }

    private QueueOpenData() {}

    public static CompositeData snapshot(
            int pending,
            int active,
            String status) throws Exception {

        return new CompositeDataSupport(
            TYPE,
            new String[] {"pending", "active", "status"},
            new Object[] {pending, active, status}
        );
    }
}
\`\`\`

A getter can return \`CompositeData\`:

\`\`\`java
@ManagedAttribute(description = "Queue snapshot")
public CompositeData getQueueSnapshot() throws Exception {
    return QueueOpenData.snapshot(
        pendingCount.get(),
        activeCount.get(),
        state.get()
    );
}
\`\`\`

On the client:

\`\`\`java
CompositeData snapshot = (CompositeData) server.getAttribute(
    objectName, "QueueSnapshot"
);

int pending = (Integer) snapshot.get("pending");
String state = (String) snapshot.get("status");
\`\`\`

Benefit: clients discover fields through the OpenType schema. Drawback: constructing data and managing schemas is more complex than scalar getters. If only one or two metrics are needed, scalar attributes are usually easier to read and maintain.

### When to Use TabularData?

When you need to expose a set of records with a fixed schema, such as a list of cache regions with \`name\`, \`size\`, and \`hitCount\`, \`TabularData\` can be appropriate.

Do not use \`TabularData\` for very large tables or continuously streaming data if reading the whole snapshot causes significant load. JMX attributes are typically for management, not a query engine for high-volume business data.

## 10. MXBeans and Automatic Java Type Mapping

MXBeans represent Java management interfaces via Open Types.

Example:

\`\`\`java
public interface WorkerHealthMXBean {
    String getState();
    long getProcessedCount();
}
\`\`\`

\`\`\`java
public class WorkerHealth implements WorkerHealthMXBean {
    @Override
    public String getState() {
        return "RUNNING";
    }

    @Override
    public long getProcessedCount() {
        return 1200L;
    }
}
\`\`\`

MXBeans follow conventions mapping Java types to Open Types. For complex types, specific rules govern whether they can be converted to \`CompositeData\` or \`TabularData\`. If a Java type lacks a valid mapping, MBean registration or invocation can fail.

Do not assume the \`@ManagedResource\` annotation **turns a bean into an MXBean**. Typical Spring annotation-driven export produces Model MBean/metadata-based exposure; the MXBean mechanism has its own contract and type-mapping rules.

When the goal is remote interoperability and a typed management interface, consider an explicit MXBean or exposing OpenTypes from an MBean. When convenient annotation metadata is desired, use \`@ManagedAttribute\` with types clients can consume and verify over the actual connection path.

## 11. Types to Avoid Exposing Directly

### 11.1. Entity/JPA or Domain Objects

\`\`\`java
@ManagedAttribute
public CustomerEntity getLatestCustomer() {
    return repository.findLatest();
}
\`\`\`

This design is unsuitable in most contexts:
- May expose customer data.
- Couples to business classes/schemas.
- May trigger unintended lazy loading.
- Remote serialization may fail.
- May cause the getter to spend time querying.

Replace with appropriate management data:

\`\`\`java
@ManagedAttribute
public long getCustomerRecordsProcessed() {
    return processedCount.get();
}
\`\`\`

### 11.2. Spring Beans and Infrastructure Objects

Avoid returning \`ApplicationContext\`, \`DataSource\`, \`EntityManager\`, \`Thread\`, \`ExecutorService\`, \`HttpServletRequest\`, or objects with complex lifecycles/resources directly. Clients do not need a reference to the entire object to understand state.

Substitute with appropriate scalars, Strings, and snapshots:

\`\`\`java
@ManagedAttribute
public int getActiveThreads() {
    return executor.getActiveCount();
}
\`\`\`

### 11.3. Streams, Files, Sockets, Callbacks

Objects like \`InputStream\`, \`Socket\`, and \`Runnable\` should not be JMX attributes fetched over the network by clients. They do not represent stable management data snapshots and typically lack a suitable serialization contract.

### 11.4. Generic Object

\`\`\`java
@ManagedAttribute
public Object getState() {
    return someInternalObject;
}
\`\`\`

Metadata \`java.lang.Object\` is too ambiguous; clients do not know the concrete type and may fail deserialization. Avoid type \`Object\` whenever a specific type contract can be defined.

## 12. Read-Only, Writable, and Setter Types

An attribute can have these access properties:

- **Readable:** has an exposed getter.
- **Writable:** has an exposed setter.
- **Is:** boolean getter following the \`isEnabled()\` convention.

Read-only example:

\`\`\`java
@ManagedAttribute(description = "Current queue depth")
public int getQueueDepth() {
    return queueDepth.get();
}
\`\`\`

Writable example:

\`\`\`java
private volatile boolean paused;

@ManagedAttribute
public boolean isPaused() {
    return paused;
}

@ManagedAttribute
public void setPaused(boolean paused) {
    this.paused = paused;
}
\`\`\`

If an administrator needs to adjust an important setting, validate the value:

\`\`\`java
private volatile int maxConcurrentJobs = 8;

@ManagedAttribute
public int getMaxConcurrentJobs() {
    return maxConcurrentJobs;
}

@ManagedAttribute
public void setMaxConcurrentJobs(int count) {
    if (count < 1 || count > 128) {
        throw new IllegalArgumentException(
            "maxConcurrentJobs must be between 1 and 128"
        );
    }
    maxConcurrentJobs = count;
}
\`\`\`

JMX metadata only states the type is \`int\`; it **does not automatically guarantee** values fall within the business domain \`1..128\`. The setter must validate and the management mechanism must protect access permissions.

Do not expose a setter merely because the Java property has an internal setter. Every writable attribute expands the surface for mutating runtime state.

## 13. Inspecting Attribute Types via MBeanInfo

After exporting the MBean, you can inspect metadata:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "com.example.monitoring:type=Queue,name=Orders"
);

if (server.isRegistered(name)) {
    MBeanInfo info = server.getMBeanInfo(name);

    for (MBeanAttributeInfo attribute : info.getAttributes()) {
        System.out.printf(
            "%s | type=%s | readable=%s | writable=%s%n",
            attribute.getName(),
            attribute.getType(),
            attribute.isReadable(),
            attribute.isWritable()
        );
    }
}
\`\`\`

\`MBeanAttributeInfo.getType()\` indicates the declared type name in metadata, such as \`int\`, \`java.lang.String\`, or another class name. It is not sufficient to conclude that remote clients will definitely receive a complex object cleanly.

If the attribute has Open MBean metadata:

\`\`\`java
import javax.management.openmbean.OpenMBeanAttributeInfo;

for (MBeanAttributeInfo attr : info.getAttributes()) {
    if (attr instanceof OpenMBeanAttributeInfo openAttr) {
        System.out.println(openAttr.getOpenType());
    }
}
\`\`\`

Note that \`MBeanAttributeInfo\` and \`OpenMBeanAttributeInfo\` are distinct API types; not every \`MBeanAttributeInfo\` implements the Open MBean interface. Some implementations may expose OpenType info via descriptors. When writing generic tooling, handle the actual metadata possibilities returned.

### Checking Actual Values

\`\`\`java
Object value = server.getAttribute(name, "PendingCount");
System.out.println(value);
\`\`\`

When calling \`getAttribute\`, handle exceptions such as \`AttributeNotFoundException\`, \`MBeanException\`, \`ReflectionException\`, or communication errors in remote scenarios. A getter can fail even if its type appears in metadata.

For \`setAttribute\`, use \`javax.management.Attribute\`:

\`\`\`java
import javax.management.Attribute;

server.setAttribute(
    name,
    new Attribute("MaxConcurrentJobs", 16)
);
\`\`\`

The value must have the right type and pass validation; a client sending String \`"16"\` is not automatically equivalent to Integer \`16\`.

## 14. Checking Interoperability with Remote JMX

An MBean can work flawlessly in the same JVM yet fail when accessed remotely. Common causes:

- Application class is absent on the client.
- Object is not serializable.
- \`serialVersionUID\` or class version mismatch.
- Serialization filter rejects the class.
- Collection contains elements of incompatible types.
- Object graph is too large, has complex cycles, or transfers too much data.
- Remote client only knows how to display standard scalars/OpenTypes.

Risk mitigation strategies:

1. Use simple scalar types for common attributes.
2. Use String or status codes for enums when clients are independent of the application.
3. For structured data, prefer OpenTypes or MXBeans with stable schemas.
4. Provide clear units and meaning in descriptions.
5. Avoid objects with side effects, lazy loading, or dependencies on internal resources.
6. Test with a client **that does not include the full server classpath** to verify the remote contract.
7. Do not expose remote JMX to the Internet without appropriate protection.

## 15. Property Types and Monitoring Overhead

A \`@ManagedAttribute\` getter can be invoked repeatedly by management tools. Even an easily serializable data type can cause heavy load if the getter:

- Queries the database on every call.
- Scans millions of records.
- Snapshots a collection with hundreds of thousands of elements.
- Waits on I/O or locks.
- Allocates large objects.

Example to avoid:

\`\`\`java
@ManagedAttribute
public List<Order> getAllOrders() {
    return repository.findAll();
}
\`\`\`

Better design:

\`\`\`java
@ManagedAttribute(description = "Current active order count")
public long getActiveOrderCount() {
    return activeOrderCounter.get();
}
\`\`\`

If a detailed snapshot is needed, cap its size, use a paginated management endpoint, or use protected diagnostics mechanisms instead of stuffing entire business datasets into a JMX attribute.

A good rule is that **a managed attribute should describe state that is fast, stable, bounded in size, and safe to read**.

## 16. Distinguishing JMX Attributes from Micrometer Metrics

Example:

\`\`\`java
@ManagedAttribute
public int getQueueDepth() {
    return queueDepth.get();
}
\`\`\`

This is a JMX attribute. If the same measurement is registered in a Micrometer \`Gauge\`, it is also a metric. Both mechanisms can reflect the same underlying state source yet differ:

| JMX attribute | Metric |
|---|---|
| Read on demand via \`getAttribute\` | Scraped/recorded by the metrics system |
| Can be read-only or writable | Usually describes a measurement, not a config-change API |
| Can return Java objects/OpenTypes | Has meter type, name, tags, and numeric values |
| Suited for JVM diagnostics/management | Suited for dashboards and time-series alerting |

An attribute of type \`long\` is not automatically a counter metric; measurement semantics must be defined separately.

## 17. Common Misconceptions

**Misconception 1: "With \`@ManagedAttribute\`, any type is accessible from JConsole."**  
Incorrect. The exporter/assembler must register the attribute, and clients may not support serialized custom objects.

**Misconception 2: "JMX only supports numbers and strings."**  
Incorrect. JMX supports various Java types across different MBean kinds; Open MBeans provide structured type systems like \`CompositeData\`/\`TabularData\`.

**Misconception 3: "\`List<CustomObject>\` will definitely work remotely."**  
Cannot be assumed. You must check the MBean type, mapping/serialization, and client classpath.

**Misconception 4: "\`Object\` is flexible so it is always safe."**  
On the contrary, it makes the API contract ambiguous and can cause remote clients to hit deserialization errors.

**Misconception 5: "JMX metadata automatically validates value ranges."**  
Metadata expresses the type, not numeric bounds or business rules. Validation is needed inside the setter.

**Misconception 6: "MXBean and \`@ManagedResource\` are the same thing."**  
Incorrect. MXBeans follow standard mapping to Open Types; \`@ManagedResource\` is metadata for Spring JMX export.

**Misconception 7: "A read-only getter cannot affect performance."**  
Incorrect. Getters can query data, acquire locks, or serialize large objects. Read cost must be bounded.

**Misconception 8: "\`Date\` or any Java object has the same OpenType mapping."**  
Incorrect. Follow the JMX type-mapping rules for the MBean type in use and verify the specific implementation.

## 18. Practice Exercises

### Exercise A: Scalar Types

Create a \`QueueMonitor\` class with managed attributes:
- \`getQueueDepth(): int\`
- \`isPaused(): boolean\`
- \`getStatus(): String\`
- \`getProcessedCount(): long\`

Enable JMX export; inspect \`MBeanInfo.getAttributes()\`, verifying names and types.

### Exercise B: Read/Write Type Safety

Add \`getMaxConcurrentJobs()\` and \`setMaxConcurrentJobs(int)\`, restricting range to \`1..128\`. Test \`setAttribute\` with a valid \`Integer\`, an out-of-range value, and a \`String\` of the wrong type. Observe which exceptions or errors are wrapped at the JMX layer.

### Exercise C: OpenType

Expose \`CompositeData\` containing \`pending\`, \`active\`, and \`state\`. Read it back using \`getAttribute()\` and extract each field. Compare with three separate scalar getters in terms of simplicity and extensibility.

### Exercise D: Remote Compatibility

Create a custom DTO and a \`CompositeData\` with the same contents. Access them from a remote client lacking the DTO class. Compare the results and explain why OpenTypes are easier to exchange between independent applications.

## 19. Self-Check Questions

**Question 1.** Does \`@ManagedAttribute\` create an MBean and remote connector on its own?  
**Answer:** No. The annotation requires Spring JMX export; the remote connector is a separate mechanism.

**Question 2.** Are \`String\` and \`int\` suitable for most JMX management properties?  
**Answer:** Yes, because they are simple and easy to consume, though value bounds, getter cost, and security must still be checked.

**Question 3.** How does \`CompositeType\` differ from \`CompositeData\`?  
**Answer:** \`CompositeType\` is the schema; \`CompositeData\` is a value conforming to the schema.

**Question 4.** Does a Spring \`@ManagedResource\` with a getter returning a custom DTO automatically become an MXBean?  
**Answer:** No. MXBeans have their own conversion contract; Spring annotation metadata does not automatically change the MBean kind.

**Question 5.** Why might \`getAttribute()\` returning a custom Java object work locally but fail remotely?  
**Answer:** The client may lack the class, serialization may be invalid, or a security filter may reject it.

**Question 6.** Metadata \`getType()\` returns \`java.lang.Object\`. Is that enough for clients to understand the data?  
**Answer:** No. A concrete type contract or OpenType schema is needed.

**Question 7.** Does the setter \`setMaxConcurrentJobs(int)\` need to check for negative numbers?  
**Answer:** Yes, because the \`int\` type allows negative numbers; business constraints must be enforced separately.

## 20. Key Takeaways

- \`@ManagedAttribute\` describes getters/setters for Spring to export as JMX attributes; it does not redefine Java's type system.
- **Java types valid on the server** differ from **types easy to interoperate with over remote JMX**.
- Scalars like \`boolean\`, \`int\`, \`long\`, \`double\`, and \`String\` are usually good choices.
- Arrays, enums, collections, and custom objects require checking the MBean kind, type mapping, and remote serialization capability.
- MXBeans map Java types to Open Types; Open MBeans provide \`SimpleType\`, \`ArrayType\`, \`CompositeType\`, and \`TabularType\`.
- \`CompositeData\` and \`TabularData\` are schema-backed management data structures, useful when clients must remain independent of internal classes.
- Use \`MBeanInfo\` to inspect actual metadata; use real clients to verify interoperability.
- Writable attributes require validation and authorization; getters must be fast, bounded in data size, and avoid side effects.

### References

- Spring Framework Reference — JMX Exporting: https://docs.spring.io/spring-framework/reference/integration/jmx/exporting.html
- Spring Framework Javadoc — \`ManagedAttribute\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedAttribute.html
- Java SE 21 API — \`MBeanAttributeInfo\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanAttributeInfo.html
- Java SE 21 API — Open MBean package: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/openmbean/package-summary.html
- Java SE 21 API — \`CompositeData\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/openmbean/CompositeData.html
- Java SE 21 API — \`MXBean\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MXBean.html
- Oracle JMX Tutorial — MXBeans: https://docs.oracle.com/javase/tutorial/jmx/mbeans/mxbeans.html
