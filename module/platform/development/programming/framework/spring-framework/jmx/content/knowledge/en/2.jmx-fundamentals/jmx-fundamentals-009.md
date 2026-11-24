# Open MBeans and Standard Extended Data Types

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain why JMX provides **Open MBeans** and the **OpenType** model to exchange management data in a structure easily understood by JMX tools, without requiring clients to know custom business classes.
- Distinguish **Standard MBean**, **MXBean**, **DynamicMBean**, and **Open MBean** in terms of management contracts and data description.
- Recognize the standard types \`SimpleType\`, \`ArrayType\`, \`CompositeType\`, and \`TabularType\`; understand the corresponding data representations \`CompositeData\` and \`TabularData\`.
- Create \`CompositeDataSupport\` and \`TabularDataSupport\`, describe schemas using \`OpenMBeanAttributeInfoSupport\` and \`OpenMBeanOperationInfoSupport\`, and expose an Open MBean via \`MBeanServer\`.
- Know how to handle complex values, schema stability, client compatibility, and limitations when integrating with Spring Framework.

## 2. Context: The Problem Open MBeans Solve

JMX allows tools like JConsole and custom clients to observe or operate on MBeans registered in \`MBeanServer\`. With ordinary Java objects, return types might be application classes, for example:

\`\`\`java
public final class QueueSnapshot {
    private final long pending;
    private final long processed;
    // Application-specific fields and APIs...
}
\`\`\`

If a custom type is exposed directly, remote clients may need that class on their classpath and must know how to deserialize it. This causes difficulties when management tools are independent of the application or when class versions change.

**Open MBeans** use a standard set of data types, described by metadata discoverable via JMX. Instead of requiring the client to know \`QueueSnapshot\`, the server can return a \`CompositeData\` whose schema consists of \`pending: Long\` and \`processed: Long\`. Clients only need the standard JMX API to read the keys and values.

\`\`\`text
Internal state
QueueSnapshot(pending=12, processed=840)
              |
              | convert to open data
              v
CompositeType "QueueSnapshot"
  pending   -> SimpleType.LONG
  processed -> SimpleType.LONG
              |
              v
CompositeData
  {pending=12, processed=840}
              |
              v
MBeanServer -> JMX client
              |
              v
Client reads metadata + key/value
without needing QueueSnapshot class
\`\`\`

The word "open" here means data types and structures can be discovered and understood by management tools under the JMX contract. It **does not mean opening public access, bypassing authentication, or allowing arbitrary method calls**.

## 3. Core Classes and Interfaces

Open MBean components reside primarily in the \`javax.management.openmbean\` package.

| Component | Purpose |
| --- | --- |
| \`OpenType<T>\` | Describes a data type recognized by JMX in the open data model. |
| \`SimpleType<T>\` | Standard scalar types, e.g., \`STRING\`, \`INTEGER\`, \`LONG\`, \`BOOLEAN\`, \`DATE\`, \`OBJECTNAME\`. |
| \`ArrayType<T>\` | Array type of a valid OpenType. |
| \`CompositeType\` | Record schema with named fields and corresponding types. |
| \`CompositeData\` | Record value conforming to \`CompositeType\`. |
| \`CompositeDataSupport\` | Common implementation class of \`CompositeData\`. |
| \`TabularType\` | Schema for a collection of \`CompositeData\` rows with index keys. |
| \`TabularData\` | Table-formatted value conforming to \`TabularType\`. |
| \`TabularDataSupport\` | Common implementation class of \`TabularData\`. |
| \`OpenMBeanInfoSupport\` | Open MBean metadata: class name, description, attributes, constructors, operations, notifications. |
| \`OpenMBeanAttributeInfoSupport\` | Attribute metadata, including OpenType, readability/writability, and optional constraints. |
| \`OpenMBeanOperationInfoSupport\` | Operation metadata, including return type and parameters. |
| \`OpenMBeanParameterInfoSupport\` | Parameter metadata for an operation or constructor. |

Note the distinction between **type description** and **value**:

\`\`\`text
CompositeType   = structure: which fields, what types?
CompositeData   = concrete values matching that structure.

TabularType     = structure of rows + index columns.
TabularData     = collection of actual rows.

OpenMBeanInfo   = describes the MBean's management surface.
MBeanServer     = receives and executes requests based on that surface.
\`\`\`

## 4. SimpleType: Standard Scalar Values

\`SimpleType\` describes the standard Java types JMX permits in open data. Common constants:

| Constant | Corresponding Java Type | Use Case |
| --- | --- | --- |
| \`SimpleType.STRING\` | \`String\` | Names, statuses, short descriptions. |
| \`SimpleType.BOOLEAN\` | \`Boolean\` | Enabling/disabling features. |
| \`SimpleType.INTEGER\` | \`Integer\` | Small counts, limits, thresholds. |
| \`SimpleType.LONG\` | \`Long\` | Counters, sizes, or durations. |
| \`SimpleType.DOUBLE\` | \`Double\` | Ratios, measured values. |
| \`SimpleType.BIGDECIMAL\` | \`BigDecimal\` | Decimal numbers requiring precision. |
| \`SimpleType.BIGINTEGER\` | \`BigInteger\` | Large integers. |
| \`SimpleType.DATE\` | \`Date\` | Timestamps. |
| \`SimpleType.OBJECTNAME\` | \`ObjectName\` | MBean name references. |
| \`SimpleType.VOID\` | \`Void\` | \`void\` return type of operations. |

Smaller integer types such as \`BYTE\` and \`SHORT\`, as well as \`FLOAT\` and \`CHARACTER\`, are also supported. Even if an application has enums or custom classes, \`SimpleType\` does not automatically accept them just because they implement \`Serializable\`. They must be represented with an appropriate OpenType, such as converting an enum to \`String\`.

Some types allow \`null\` in value positions per the rules of their containing data, but the meaning of \`null\` must be explicitly designed; do not treat \`null\` as a new \`SimpleType\`.

\`\`\`java
import javax.management.openmbean.SimpleType;

System.out.println(SimpleType.STRING.getClassName());
System.out.println(SimpleType.LONG.getTypeName());
System.out.println(SimpleType.BOOLEAN.isValue(Boolean.TRUE));
System.out.println(SimpleType.LONG.isValue("123")); // false: String is not Long
\`\`\`

\`isValue\` checks whether a Java object matches the declared open data type. Converting \`"123"\` to \`Long\` is the application code's responsibility if the input is a String.

## 5. CompositeType and CompositeData: Multi-Field Records

### 5.1. Declaring the Schema

Composite data can describe a snapshot consisting of multiple metrics:

\`\`\`java
import javax.management.openmbean.CompositeType;
import javax.management.openmbean.OpenType;
import javax.management.openmbean.SimpleType;

CompositeType queueType = new CompositeType(
    "QueueSnapshot",             // typeName
    "Current queue statistics",  // description
    new String[] { "pending", "processed", "paused" },
    new String[] {
        "Tasks awaiting processing",
        "Tasks already processed",
        "Whether the queue is paused"
    },
    new OpenType<?>[] {
        SimpleType.LONG,
        SimpleType.LONG,
        SimpleType.BOOLEAN
    }
);
\`\`\`

\`CompositeType\` describes items by name and type. Each item name must be valid and unique; the \`itemNames\`, \`itemDescriptions\`, and \`itemTypes\` arrays must match in length. The constructor throws \`OpenDataException\` if the schema is invalid.

### 5.2. Creating Values Matching the Schema

\`\`\`java
import javax.management.openmbean.CompositeData;
import javax.management.openmbean.CompositeDataSupport;

CompositeData snapshot = new CompositeDataSupport(
    queueType,
    new String[] { "pending", "processed", "paused" },
    new Object[] { 12L, 840L, false }
);

System.out.println(snapshot.get("pending")); // 12
System.out.println(snapshot.get("paused"));  // false
System.out.println(snapshot.getCompositeType().getTypeName());
\`\`\`

You can use the \`Map<String, ?>\` constructor to reduce the risk of misaligned value order:

\`\`\`java
import java.util.Map;

CompositeData snapshot = new CompositeDataSupport(
    queueType,
    Map.of(
        "pending", 12L,
        "processed", 840L,
        "paused", false
    )
);
\`\`\`

When using \`Map.of\`, neither keys nor values may be \`null\`; if a valid \`null\` value needs to be represented, use an appropriate \`Map\` implementation before creating \`CompositeDataSupport\`.

Reading each field without business classes:

\`\`\`java
long pending = (Long) snapshot.get("pending");
boolean paused = (Boolean) snapshot.get("paused");
\`\`\`

Clients still need to handle missing fields and unexpected types, especially when schemas change between server versions.

### 5.3. CompositeData Is Not Equivalent to a Java Bean

\`CompositeData\` provides a dictionary-like interface with a fixed schema. It holds no business logic, service methods, or arbitrary object reference graphs. Nested data must be represented by permitted OpenTypes, such as a nested \`CompositeType\`, \`ArrayType\`, or \`TabularType\`.

Do not push large object graphs, circular references, or sensitive data over JMX merely because \`CompositeData\` can hold multiple fields.

## 6. ArrayType: Homogeneous Lists of Values

\`ArrayType\` represents a one- or multi-dimensional array containing values of a corresponding OpenType:

\`\`\`java
import javax.management.openmbean.ArrayType;
import javax.management.openmbean.SimpleType;

ArrayType<?> tagsType = new ArrayType<>(1, SimpleType.STRING);
ArrayType<?> matrixType = new ArrayType<>(2, SimpleType.INTEGER);
\`\`\`

\`tagsType\` corresponds to \`String[]\`; \`matrixType\` corresponds to \`Integer[][]\`. Note that primitive array types such as \`int[]\` are declared differently from \`Integer[]\`; the API also provides \`ArrayType\` mechanisms for supported primitive arrays. Do not assume \`ArrayType<>(1, SimpleType.INTEGER)\` accepts \`int[]\`.

\`\`\`java
String[] tags = { "critical", "worker" };
System.out.println(tagsType.isValue(tags)); // true
\`\`\`

A \`CompositeType\` can contain an \`ArrayType\` item, such as \`workerNames: String[]\`. However, multi-row tables with keys are usually represented more clearly with \`TabularType\`.

## 7. TabularType and TabularData: Indexed Tables of Records

### 7.1. Defining Rows and Keys

Suppose we want to expose statistics keyed by queue name:

\`\`\`text
name          pending   paused
email         12        false
billing       4         true
search        37        false
\`\`\`

First define the schema of a single row using \`CompositeType\`, then define the table schema with key \`name\`:

\`\`\`java
import javax.management.openmbean.CompositeType;
import javax.management.openmbean.OpenType;
import javax.management.openmbean.SimpleType;
import javax.management.openmbean.TabularType;

CompositeType rowType = new CompositeType(
    "QueueRow",
    "A queue status row",
    new String[] { "name", "pending", "paused" },
    new String[] { "Queue name", "Pending tasks", "Paused" },
    new OpenType<?>[] {
        SimpleType.STRING,
        SimpleType.LONG,
        SimpleType.BOOLEAN
    }
);

TabularType tableType = new TabularType(
    "QueueTable",
    "Current queues",
    rowType,
    new String[] { "name" }
);
\`\`\`

\`indexNames\` is the list of item names in \`rowType\` used as the key. In this example, each \`name\` must be unique in the table. If a composite key is needed, pass multiple item names, such as \`{ "tenant", "name" }\`.

### 7.2. Creating the Table and Adding Rows

\`\`\`java
import java.util.Map;
import javax.management.openmbean.CompositeData;
import javax.management.openmbean.CompositeDataSupport;
import javax.management.openmbean.TabularData;
import javax.management.openmbean.TabularDataSupport;

TabularData table = new TabularDataSupport(tableType);

CompositeData email = new CompositeDataSupport(
    rowType,
    Map.of("name", "email", "pending", 12L, "paused", false)
);
CompositeData billing = new CompositeDataSupport(
    rowType,
    Map.of("name", "billing", "pending", 4L, "paused", true)
);

table.put(email);
table.put(billing);

System.out.println(table.size()); // 2

CompositeData selected = table.get(new Object[] { "email" });
System.out.println(selected.get("pending")); // 12
\`\`\`

\`TabularDataSupport\` stores \`CompositeData\` entries conforming to the row schema; each row is accessed by the index defined in \`TabularType\`.

**Distinguishing JMX tables and databases:** \`TabularData\` is a structure for representing and exchanging management data, not an SQL system; it has no built-in pagination, transactions, or query optimizer. Avoid returning overly large tables via JMX due to copying, serialization, and rendering costs on management tools.

### 7.3. When to Choose CompositeData vs. TabularData?

| Need | Appropriate Type | Example |
| --- | --- | --- |
| A single snapshot with fixed fields | \`CompositeData\` | Request count, average processing time, status. |
| Multiple snapshots with the same structure and stable keys | \`TabularData\` | Statistics per queue, cache, or tenant. |
| An array of homogeneous elements | \`ArrayType\` | List of tags, top error codes. |
| A single simple value | \`SimpleType\` | \`Long\` counter, \`Boolean\` enabled/disabled. |

## 8. How Does Open MBean Differ from Standard MBean and MXBean?

### 8.1. Standard MBean

Standard MBean typically uses an interface suffixed with \`MBean\` to expose attributes and operations:

\`\`\`java
public interface QueueAdminMBean {
    int getPendingCount();
    void reset();
}
\`\`\`

JMX introspection derives metadata from the Java interface. A Standard MBean can have useful data types, but it does not enforce that every signature uses an OpenType.

### 8.2. MXBean

MXBean is a convenient mechanism for mapping certain Java types to standard **open data**. For instance, \`@MXBean\` or the \`MXBean\` interface-name suffix convention enables JMX to map types covered by MXBean rules, such as properly structured record/bean types into \`CompositeData\`.

\`\`\`java
import javax.management.MXBean;

@MXBean
public interface QueueMonitorMXBean {
    long getPending();
    String getStatus();
}
\`\`\`

MXBean is useful when you want typed Java code friendly to server/client authors while still exposing open data at the JMX boundary. Not every arbitrary object has a valid MXBean mapping.

### 8.3. Metadata-Driven Open MBean

Open MBean uses \`OpenMBeanInfo\` metadata and OpenTypes to describe the management contract. It is typically implemented via \`DynamicMBean\` with \`OpenMBeanInfoSupport\`, or through a framework that supports generating appropriate metadata.

| Criterion | Standard MBean | MXBean | Explicitly Described Open MBean |
| --- | --- | --- | --- |
| Starting point | Convention-based Java interface | Java interface with MXBean mapping | JMX metadata with \`OpenType\` |
| Programming interface | Typed getters/setters/operations | Typed getters/setters/operations plus mapping | Can handle dynamically by name and metadata |
| Client type understanding | May depend on custom types | Data is mapped to open data | Data is exposed directly as open data |
| When appropriate | Simple internal management | Typed API with independent clients | Dynamic MBeans, explicit schemas, or JMX frameworks |

**Important relationship:** Open MBean is a contract about metadata and open data types; \`DynamicMBean\` is a Java interface allowing custom implementation of get/set/invoke/getMBeanInfo. The two concepts are related but not synonymous. An arbitrary \`DynamicMBean\` does not necessarily expose full OpenTypes.

## 9. Complete Open MBean Example Using DynamicMBean

This example returns a read-only \`CompositeData\` and provides a \`reset\` operation. The entire management interface is explicitly described with \`OpenMBeanInfoSupport\`.

### 9.1. Source Code

\`\`\`java
package example.jmx;

import java.lang.management.ManagementFactory;
import java.util.Map;
import javax.management.Attribute;
import javax.management.AttributeList;
import javax.management.AttributeNotFoundException;
import javax.management.DynamicMBean;
import javax.management.InvalidAttributeValueException;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanConstructorInfo;
import javax.management.MBeanException;
import javax.management.MBeanInfo;
import javax.management.MBeanNotificationInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanParameterInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import javax.management.ReflectionException;
import javax.management.openmbean.CompositeData;
import javax.management.openmbean.CompositeDataSupport;
import javax.management.openmbean.CompositeType;
import javax.management.openmbean.OpenDataException;
import javax.management.openmbean.OpenMBeanAttributeInfoSupport;
import javax.management.openmbean.OpenMBeanInfoSupport;
import javax.management.openmbean.OpenMBeanOperationInfoSupport;
import javax.management.openmbean.OpenType;
import javax.management.openmbean.SimpleType;

public final class OpenQueueMonitor implements DynamicMBean {

    private final CompositeType snapshotType;
    private final MBeanInfo mbeanInfo;
    private long pending = 12L;
    private long processed = 840L;

    public OpenQueueMonitor() throws OpenDataException {
        snapshotType = new CompositeType(
            "QueueSnapshot",
            "Snapshot of queue counters",
            new String[] { "pending", "processed" },
            new String[] { "Pending tasks", "Processed tasks" },
            new OpenType<?>[] { SimpleType.LONG, SimpleType.LONG }
        );

        OpenMBeanAttributeInfoSupport snapshotInfo =
            new OpenMBeanAttributeInfoSupport(
                "Snapshot",
                "Current queue counters",
                snapshotType,
                true,   // readable
                false,  // writable
                false   // isIs
            );

        OpenMBeanOperationInfoSupport resetInfo =
            new OpenMBeanOperationInfoSupport(
                "reset",
                "Reset the counters",
                new javax.management.openmbean.OpenMBeanParameterInfo[0],
                SimpleType.VOID,
                MBeanOperationInfo.ACTION
            );

        mbeanInfo = new OpenMBeanInfoSupport(
            getClass().getName(),
            "Queue monitor with open data",
            new javax.management.openmbean.OpenMBeanAttributeInfo[] {
                snapshotInfo
            },
            new javax.management.openmbean.OpenMBeanConstructorInfo[0],
            new javax.management.openmbean.OpenMBeanOperationInfo[] {
                resetInfo
            },
            new MBeanNotificationInfo[0]
        );
    }

    @Override
    public synchronized Object getAttribute(String attribute)
            throws AttributeNotFoundException, MBeanException,
                   ReflectionException {
        if ("Snapshot".equals(attribute)) {
            try {
                return new CompositeDataSupport(
                    snapshotType,
                    Map.of("pending", pending, "processed", processed)
                );
            } catch (OpenDataException e) {
                throw new MBeanException(e, "Invalid queue snapshot");
            }
        }
        throw new AttributeNotFoundException(attribute);
    }

    @Override
    public void setAttribute(Attribute attribute)
            throws AttributeNotFoundException,
                   InvalidAttributeValueException, MBeanException,
                   ReflectionException {
        throw new AttributeNotFoundException(
            attribute == null ? "null" : attribute.getName()
        );
    }

    @Override
    public AttributeList getAttributes(String[] attributes) {
        AttributeList values = new AttributeList();
        if (attributes != null) {
            for (String attribute : attributes) {
                try {
                    values.add(new Attribute(
                        attribute,
                        getAttribute(attribute)
                    ));
                } catch (Exception ignored) {
                    // Skip attributes that cannot be read.
                }
            }
        }
        return values;
    }

    @Override
    public AttributeList setAttributes(AttributeList attributes) {
        // Sample MBean has no writable attributes.
        return new AttributeList();
    }

    @Override
    public synchronized Object invoke(
            String actionName,
            Object[] params,
            String[] signature)
            throws MBeanException, ReflectionException {
        if ("reset".equals(actionName)
                && (params == null || params.length == 0)
                && (signature == null || signature.length == 0)) {
            pending = 0L;
            processed = 0L;
            return null;
        }
        throw new ReflectionException(
            new NoSuchMethodException(actionName)
        );
    }

    @Override
    public MBeanInfo getMBeanInfo() {
        return mbeanInfo;
    }

    public static void main(String[] args) throws Exception {
        MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();

        ObjectName name = new ObjectName(
            "com.example:type=QueueMonitor,name=Orders"
        );
        server.registerMBean(new OpenQueueMonitor(), name);
        try {
            CompositeData before = (CompositeData)
                server.getAttribute(name, "Snapshot");

            System.out.println(before.get("pending"));   // 12
            System.out.println(before.get("processed")); // 840

            server.invoke(
                name, "reset", new Object[0], new String[0]
            );

            CompositeData after = (CompositeData)
                server.getAttribute(name, "Snapshot");
            System.out.println(after.get("pending"));    // 0
            System.out.println(after.get("processed"));  // 0
        } finally {
            server.unregisterMBean(name);
        }
    }
}
\`\`\`

### 9.2. Explaining the Execution Flow

1. The constructor creates \`CompositeType\` as the schema for the \`Snapshot\` attribute.
2. \`OpenMBeanAttributeInfoSupport\` exposes the attribute of type \`CompositeType\`, readable but not writable.
3. \`OpenMBeanOperationInfoSupport\` describes the \`reset\` operation returning \`void\` via \`SimpleType.VOID\`.
4. \`OpenMBeanInfoSupport\` combines the metadata into a management interface for \`MBeanServer\` and clients to discover.
5. The client calls \`server.getAttribute(name, "Snapshot")\`; \`getAttribute\` returns \`CompositeDataSupport\` containing the counters.
6. The client calls \`invoke(..., "reset", ...)\`; the counters reset and the next read returns the new values.
7. \`finally\` ensures the MBean is unregistered after the example.

For real projects, swallowing per-attribute errors in \`getAttributes\` should follow a logging strategy suited to the specification and observability needs; the example above simply preserves returning the list of readable attributes. If a getter is resource-intensive or has side effects, the getter itself needs to be redesigned.

### 9.3. Discovering Metadata from a Client

\`\`\`java
MBeanInfo info = server.getMBeanInfo(name);

for (MBeanAttributeInfo attribute : info.getAttributes()) {
    System.out.println(
        attribute.getName()
        + " : " + attribute.getType()
        + " (readable=" + attribute.isReadable() + ")"
    );
}

for (MBeanOperationInfo operation : info.getOperations()) {
    System.out.println("Operation: " + operation.getName());
}
\`\`\`

Metadata of an Open MBean uses the corresponding info classes; clients can check \`instanceof OpenMBeanAttributeInfo\` to retrieve \`getOpenType()\`:

\`\`\`java
import javax.management.openmbean.OpenMBeanAttributeInfo;

for (MBeanAttributeInfo attribute : info.getAttributes()) {
    if (attribute instanceof OpenMBeanAttributeInfo open) {
        System.out.println(open.getOpenType());
    }
}
\`\`\`

\`MBeanInfo\` shows the Java/JMX type class name, while \`OpenMBeanAttributeInfo.getOpenType()\` provides the detailed schema required to interpret nested values.

## 10. Complex Type Values, Nullability, and Schema Errors

### 10.1. Checking Type Compatibility Before Creating Data

\`CompositeDataSupport\` and \`TabularDataSupport\` validate values against the schema. For example:

\`\`\`java
CompositeType type = new CompositeType(
    "Counter", "One counter",
    new String[] { "count" },
    new String[] { "Current count" },
    new OpenType<?>[] { SimpleType.LONG }
);

// Valid:
CompositeData valid = new CompositeDataSupport(
    type, Map.of("count", 12L)
);

// Wrong type: Integer instead of Long, so OpenDataException occurs.
CompositeData invalid = new CompositeDataSupport(
    type, Map.of("count", 12)
);
\`\`\`

The proper approach is explicit type mapping, such as \`Long.valueOf(sourceValue)\`, ensuring the data does not exceed representation bounds. Never stuff a String into a field declared as LONG to "avoid errors", as that breaks the client contract.

### 10.2. Nulls and Nonexistent Attributes

For \`CompositeData\`, a field may hold a \`null\` value per API/implementation rules, yet the schema must still include the **exact field name**. A \`null\` value does not mean "missing field". Some immutable structures like \`Map.of\` forbid \`null\` when building the map; that is a Java Collections constraint, separate from open data rules.

Distinguish clearly:

- **Field not defined in CompositeType**: clients must treat this as a schema mismatch or invalid request.
- **Field present with null value**: attribute has no value yet or is not applicable, per the published contract.
- **Field with a different type**: data violates schema and must be rejected or explicitly converted.

### 10.3. Hierarchical Data

A \`CompositeType\` can contain items that are another \`CompositeType\` or \`TabularType\`. For example, describing a service with \`status: String\` and \`queues: TabularData\`. Each level should keep stable names and types, avoiding bloated data that becomes hard to read in JConsole.

If paginated lists, complex queries, or large datasets are needed, JMX is not a pagination-first data API. You can expose only aggregated metrics and a link/reference to a dedicated operational interface.

## 11. Open MBeans, Remote JMX, and Compatibility

### 11.1. Remote Clients Do Not Need Business Classes

When a client uses \`JMXConnector\` to obtain an \`MBeanServerConnection\`, it can call:

\`\`\`java
CompositeData snapshot = (CompositeData)
    connection.getAttribute(objectName, "Snapshot");

long pending = (Long) snapshot.get("pending");
\`\`\`

The client uses types from the standard JMX API and the returned schema. Nevertheless, remote access still requires a connector, network configuration, authentication, authorization, and appropriate protections.

### 11.2. Compatibility When Schemas Change

Suppose version 1 returns \`{pending: Long, processed: Long}\`, and version 2 adds \`paused: Boolean\`. Clients should inspect the schema and use only the fields they need, while having a policy to handle additional fields. On the other hand, clients that blindly cast and access fields directly can break if \`pending\` is renamed, \`Long\` changes to \`String\`, or an item is removed.

Design recommendations:

1. Choose clear attribute names, item names, and data types from the start.
2. Keep core fields stable and avoid changing the semantics of fields in use.
3. For breaking changes, publish a clearly versioned schema or new \`ObjectName\` when necessary.
4. Read \`OpenType\`/metadata to verify the schema, especially before writing attributes or invoking operations.
5. Test with actual observability tools because each client renders \`CompositeData\` and \`TabularData\` differently.

Do not assume every kind of client will automatically accept arbitrary schema changes just because the data is "open".

## 12. Open MBeans in the Spring Framework Ecosystem

Spring Framework provides JMX mechanisms such as \`MBeanExporter\`, \`@ManagedResource\`, \`@ManagedAttribute\`, and \`@ManagedOperation\` to expose application beans. In many scenarios, using a Spring exporter or MXBean reduces boilerplate code.

However:

- Spring beans and Open MBeans are two distinct models. A bean in \`ApplicationContext\` does not automatically become an Open MBean.
- The Spring exporter manages MBean registration and converts Spring beans into appropriate metadata per configuration; it does not by default turn every business object type into valid \`CompositeData\`.
- When you want to expose data with an explicit standard schema, you can register a \`DynamicMBean\` exposing \`OpenMBeanInfoSupport\`, or choose an MXBean if the Java contract fits the mapping mechanism.
- Only one owner should manage registration for a given \`ObjectName\` in each \`MBeanServer\`, avoiding conflicts between manual registration and \`MBeanExporter\`.

Component organization example:

\`\`\`text
Spring service / repository
         |
         | provides business snapshot
         v
OpenQueueMonitor (JMX adapter)
         |
         | CompositeData / OpenMBeanInfo
         v
MBeanServer (platform or configured server)
         |
         v
JConsole / JMX client / collector
\`\`\`

This organization keeps business logic in the service, type-mapping logic in the JMX adapter, and registry responsibilities in MBeanServer. Layer separation helps control what content is allowed to be exposed.

## 13. Security, Performance, and Operations

**Security.** Open data does not protect sensitive information by itself. If a \`CompositeData\` contains tokens, passwords, user emails, or secret configuration, they can be read via JMX once access is granted. Expose only fields meant for operations, and enforce strict remote JMX controls.

**Performance.** A large \`TabularData\` can consume significant CPU and memory to construct, serialize, and render. JMX getters are often polled periodically; avoid full database scans, holding long locks, or executing heavy business logic inside \`getAttribute\`.

**Consistency.** When a snapshot is gathered from multiple changing counters, the data may not reflect a single instant without synchronization. Define consistency requirements clearly: short-lock snapshots, atomic counters, or documented eventual consistency.

**Control permissions.** Operations like \`reset\`, \`clearCache\`, and \`pauseWorker\` have real impact. Expose as few state-mutating operations as possible, clarify permissions, and log operational actions as needed.

**Lifecycle.** Registering via \`MBeanServer.registerMBean\` must have a matching \`unregisterMBean\` path on shutdown. Each MBean should have clear ownership to avoid \`InstanceAlreadyExistsException\` during context restarts.

**Stability.** Do not put dynamic values into \`CompositeType\` item names when they can be represented as \`TabularData\` rows with a key column; schemas that change with data make client handling difficult.

## 14. Common Misconceptions

| Misconception | Correct Understanding |
| --- | --- |
| "Open MBean allows public JMX access." | "Open" refers to data types and metadata; connection security is an independent concern. |
| "CompositeData is an arbitrary Java Map." | \`CompositeData\` conforms to a \`CompositeType\` schema with defined names and OpenTypes. |
| "TabularData is an SQL table." | It is an in-memory JMX data table indexed by described keys, with no SQL engine. |
| "Every Serializable class is a SimpleType." | Only Java types allowed by OpenType are valid open data. |
| "A DynamicMBean is always an Open MBean." | \`DynamicMBean\` can expose arbitrary metadata/types; Open MBean has requirements on OpenTypes and OpenMBeanInfo. |
| "MXBean and Open MBean are the same class." | MXBean provides typed-Java-to-open-data mapping; Open MBean is a metadata/open-data model implementable in multiple ways. |
| "JMX has built-in pagination for TabularData." | The TabularData API does not provide remote pagination automatically. |
| "OpenType data is always understood across versions by clients." | Clients still must handle renames, type changes, and schema evolution. |

## 15. Hands-On Exercises

### Exercise 1 — A Schema-Backed Snapshot

Create a \`CompositeType\` named \`ThreadPoolSnapshot\` with fields \`active: Integer\`, \`queued: Long\`, and \`shutdown: Boolean\`. Instantiate \`CompositeDataSupport\` with valid values, then read each field. Try passing \`"10"\` for \`queued\` and observe the error.

**Expected result:** understanding that a schema declaring \`SimpleType.LONG\` requires a matching Java \`Long\` value, not a numeric String.

### Exercise 2 — A Keyed Table

Create a \`CompositeType\` \`WorkerRow\` containing \`name: String\` and \`completed: Long\`; create a \`TabularType\` using index \`name\`. Add two workers, read via \`get(new Object[] { "worker-1" })\`, then try adding a row with a duplicate key to observe the uniqueness rule.

**Expected result:** distinguishing table keys from row order, as well as accessing values by key.

### Exercise 3 — A Practical MBean

Run the \`OpenQueueMonitor\` example, using \`ManagementFactory.getPlatformMBeanServer()\` and \`ObjectName\` for registration. Read the metadata of \`Snapshot\`, then invoke \`reset\` and read again.

**Expected result:** \`Snapshot.pending\` changes from 12 to 0; the JMX client does not need to know the hypothetical business \`QueueSnapshot\` class.

### Exercise 4 — Compatibility

Write a client that reads only \`pending\`. Extend the server schema with \`oldestAgeMs: Long\` and verify whether the client can still read it. Then rename \`pending\` to \`queued\` and observe the difference. Propose an appropriate schema versioning approach.

### Exercise 5 — Spring Adapter

Create a Spring service providing queue snapshots, a JMX adapter converting snapshots to \`CompositeData\`, and manage adapter registration with the Spring lifecycle. Verify the same \`ObjectName\` is not registered twice. Explain why business logic should remain outside the adapter.

## 16. Review Questions

**1. What does OpenType describe?** It describes standard data types permitted for exchange in the JMX open data model.

**2. How does CompositeType differ from CompositeData?** CompositeType is the record schema; CompositeData is a concrete record conforming to that schema.

**3. What does TabularType use indexNames for?** It defines which items of each row serve as the unique identifying key in TabularData.

**4. Why does open data help remote clients?** Types and schemas are represented by standard JMX classes, reducing dependency on server-specific business classes.

**5. Does ArrayType always accept primitive arrays?** No. Array types must be declared according to \`ArrayType\` rules; \`Integer[]\` and \`int[]\` are two different Java forms.

**6. Why should you avoid returning very large TabularData?** Constructing, transmitting, and rendering the entire table can consume substantial resources and has no automatic pagination mechanism.

**7. Should you change the type of \`pending\` from LONG to STRING while keeping the same schema/version?** No. That is a client-breaking change; a compatible contract or explicit versioning is required.

**8. What role does MBeanServer play with Open MBeans?** It acts as the registry and forwarding point for management requests; the Open MBean determines the exposed data and metadata.

## 17. Summary

**Open MBeans** normalize management structures into data types discoverable via standard JMX. \`SimpleType\` expresses single values; \`ArrayType\` describes arrays; \`CompositeType\` + \`CompositeData\` represent fixed-field snapshots; \`TabularType\` + \`TabularData\` represent keyed collections of rows. \`OpenMBeanInfoSupport\` and related metadata classes expose the schemas of attributes and operations.

In Spring Framework applications, you can use exporters/MXBeans where appropriate or build an explicit Open MBean adapter for complex management data. Protect sensitive information, keep schemas stable, control data sizes, and tie registration lifecycles to the application lifecycle.

## References

- Java SE 21 — \`javax.management.openmbean\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/openmbean/package-summary.html
- Java SE 21 — \`CompositeData\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/openmbean/CompositeData.html
- Java SE 21 — \`TabularData\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/openmbean/TabularData.html
- Java SE 21 — \`OpenMBeanInfoSupport\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/openmbean/OpenMBeanInfoSupport.html
- Java SE 21 — \`javax.management.MXBean\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MXBean.html
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html