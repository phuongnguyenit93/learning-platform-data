# Looking Up MBeans by ObjectName in MBeanServer

## 1. Objectives

Once an MBean has been registered in JMX, to read attributes, invoke operations, or subscribe to notifications, an application must identify the exact **ObjectName** of that MBean. **MBeanServer** stores the set of registered MBeans and provides query APIs by ObjectName.

This lesson focuses on the question: **How do you look up MBeans by ObjectName?** We will move from understanding ObjectName and distinguishing exact names from patterns, to the `isRegistered`, `queryNames`, and `queryMBeans` methods, and how to combine them with `MBeanServerConnection` in a Spring application.

## 2. ObjectName Is the Address of an MBean

An ObjectName has the form:

\`\`\`text
domain:key1=value1,key2=value2
\`\`\`

Examples:

\`\`\`text
demo.app:type=Cache,name=Primary
java.lang:type=Memory
java.lang:type=GarbageCollector,name=G1 Young Generation
\`\`\`

Where:

- **Domain** is a logical namespace, such as `demo.app` or `java.lang`.
- **Key properties** are key/value pairs that distinguish MBeans within the domain; for example `type=Cache`, `name=Primary`.
- **Canonical name** is the normalized representation of an ObjectName. The order of key properties in the input string does not determine ObjectName identity.
- **An exact ObjectName** represents a specific MBean, whereas an **ObjectName pattern** describes a set of MBeans matching a pattern.

The following two representations identify the same ObjectName:

\`\`\`text
demo.app:type=Cache,name=Primary
demo.app:name=Primary,type=Cache
\`\`\`

Therefore, when comparing two ObjectNames, use `equals()` instead of raw string comparison. To obtain a stable string for logging, use `getCanonicalName()`.

\`\`\`java
import javax.management.ObjectName;

ObjectName first =
    new ObjectName("demo.app:type=Cache,name=Primary");
ObjectName second =
    new ObjectName("demo.app:name=Primary,type=Cache");

System.out.println(first.equals(second)); // true
System.out.println(first.getCanonicalName());
// demo.app:name=Primary,type=Cache
\`\`\`

**Key point:** ObjectName identifies **an MBean registered in an MBeanServer**. It is not a Java class name, Spring bean name, URL address, or heap object reference. The same ObjectName can appear on different MBeanServers; to look up the right object, you must connect to the right server.

## 3. Looking Up by Exact Name

When you know the exact ObjectName, the simplest approach is to create an ObjectName and check with `isRegistered`.

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class ExactMBeanLookup {
    public static void main(String[] args) throws Exception {
        MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();

        ObjectName memoryName =
            new ObjectName("java.lang:type=Memory");

        boolean exists = server.isRegistered(memoryName);
        System.out.println("Registered: " + exists);

        if (exists) {
            Object heapMemoryUsage =
                server.getAttribute(memoryName, "HeapMemoryUsage");
            System.out.println("Heap usage: " + heapMemoryUsage);
        }
    }
}
\`\`\`

In this example, `java.lang:type=Memory` is a built-in platform MBean on a standard JVM; the `HeapMemoryUsage` attribute returns aggregated heap memory data (typically as `CompositeData` when accessed via JMX).

Exact workflow:

1. Obtain an `MBeanServer` or `MBeanServerConnection` pointing to the server to query.
2. Create an `ObjectName` matching the MBean's domain and set of key properties.
3. Use `isRegistered(name)` to check presence when needed.
4. Use `getMBeanInfo`, `getAttribute`, `setAttribute`, or `invoke` according to the MBean interface.

`isRegistered` only reflects the state at the moment of the call. An MBean could be unregistered between the check step and the read step; production code must still handle `InstanceNotFoundException`.

## 4. Looking Up Multiple MBeans with queryNames

When you do not know the full name, or need to find multiple MBeans in the same group, use:

\`\`\`java
Set<ObjectName> queryNames(ObjectName name, QueryExp query)
\`\`\`

Where:

- `name`: an exact `ObjectName` or a pattern; `null` means no restriction by name.
- `query`: an additional filter expression `QueryExp`; `null` means no additional filter condition.
- The return value is a `Set<ObjectName>` of matching MBeans currently registered on the server.

Example finding all MBeans in the `java.lang` domain:

\`\`\`java
import java.lang.management.ManagementFactory;
import java.util.Set;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class PatternLookup {
    public static void main(String[] args) throws Exception {
        MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();

        ObjectName pattern = new ObjectName("java.lang:*");
        Set<ObjectName> names = server.queryNames(pattern, null);

        for (ObjectName name : names) {
            System.out.println(name.getCanonicalName());
        }
    }
}
\`\`\`

Example filtering by MBean type:

\`\`\`java
ObjectName pattern =
    new ObjectName("java.lang:type=GarbageCollector,*");

Set<ObjectName> collectors = server.queryNames(pattern, null);
for (ObjectName collector : collectors) {
    System.out.println(collector);
}
\`\`\`

The `*` after the comma allows the ObjectName to have additional key properties beyond `type=GarbageCollector`. This is especially useful when MBean names vary across JVM versions or GC implementations.

If you need metadata along with the name and `ObjectInstance` reference, use `queryMBeans(pattern, null)`, which returns `Set<ObjectInstance>`. When you only need the list of names for further reading, `queryNames` is usually sufficient and simpler.

### Distinguishing Common Patterns

| ObjectName | Meaning |
| --- | --- |
| `demo.app:type=Cache,name=Primary` | Exact name of a single MBean |
| `demo.app:*` | All MBeans in the `demo.app` domain |
| `demo.app:type=Cache,*` | MBeans with property `type=Cache`, allowing other keys |
| `demo.*:type=Cache,*` | Domain matching `demo.*`, property `type=Cache` |
| `*:type=Cache,*` | Any domain with `type=Cache` |
| `java.lang:type=Memory` | Specific platform Memory MBean |

`ObjectName` supports patterns in both the domain and key properties. Not every string containing `*` works like a regex: JMX applies **ObjectName pattern matching**, with its own syntax. Check `pattern.isPattern()` to know whether an ObjectName is a pattern.

Example:

\`\`\`java
ObjectName exact =
    new ObjectName("demo.app:type=Cache,name=Primary");
ObjectName wildcard =
    new ObjectName("demo.app:type=Cache,*");

System.out.println(exact.isPattern());    // false
System.out.println(wildcard.isPattern()); // true
\`\`\`

## 5. Querying with QueryExp When Patterns Alone Are Not Enough

The second parameter of `queryNames` can be a `QueryExp` to filter further by attribute values or information evaluable from the MBean.

\`\`\`java
import java.util.Set;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import javax.management.Query;
import javax.management.QueryExp;

ObjectName pattern = new ObjectName("demo.app:type=Worker,*");

QueryExp enabledFilter = Query.eq(
    Query.attr("Enabled"),
    Query.value(true)
);

Set<ObjectName> enabledWorkers =
    server.queryNames(pattern, enabledFilter);
\`\`\`

Here, the candidate MBeans need to have a readable JMX attribute `Enabled` that satisfies the condition. The attribute name in `Query.attr("Enabled")` is the **JMX attribute** name, which does not necessarily match the Java field name. Some MBeans that lack the attribute, do not allow reading it, or fail while evaluating the condition may not appear in the result; an empty result must not be interpreted as confirmation that every worker is disabled.

You can combine conditions with `Query.and`, `Query.or`, `Query.gt`, `Query.lt`, or appropriate operators. In normal work, prefer filtering by domain/key properties first since it is stable and easy to observe, and only use QueryExp when you need to filter by runtime attributes.

## 6. Discovering Metadata Before Reading or Invoking Operations

A valid ObjectName does not guarantee that all expected attributes or operations are present. After finding an MBean, `getMBeanInfo(name)` returns a description of its management interface:

\`\`\`java
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
import javax.management.ObjectName;

ObjectName name = new ObjectName("java.lang:type=Memory");
MBeanInfo info = server.getMBeanInfo(name);

System.out.println("MBean class: " + info.getClassName());

for (MBeanAttributeInfo attribute : info.getAttributes()) {
    System.out.printf(
        "Attribute %s, readable=%s, writable=%s%n",
        attribute.getName(),
        attribute.isReadable(),
        attribute.isWritable()
    );
}

for (MBeanOperationInfo operation : info.getOperations()) {
    System.out.println("Operation: " + operation.getName());
}
\`\`\`

The metadata discovery step helps determine:

- Which attributes are readable or writable.
- Which operations exist and what parameter types need to be passed.
- Whether the MBean name and attribute names match the client's assumptions.
- Whether the MBean is a Standard MBean, MXBean, Spring-exported ModelMBean, or another type at the level of published metadata and descriptors.

For example, to call an operation you use `invoke(ObjectName name, String operationName, Object[] params, String[] signature)`. For operations with parameters, the signature must match the Java types published in MBeanInfo.

## 7. Reading Attributes After Lookup

Example reading heap usage from the platform MBean:

\`\`\`java
import javax.management.ObjectName;
import javax.management.openmbean.CompositeData;

ObjectName name = new ObjectName("java.lang:type=Memory");
CompositeData heap = (CompositeData)
    server.getAttribute(name, "HeapMemoryUsage");

long used = (Long) heap.get("used");
long max = (Long) heap.get("max");

System.out.println("Heap used: " + used);
System.out.println("Heap max: " + max);
\`\`\`

`HeapMemoryUsage` is represented by JMX as `CompositeData`, with fields such as `init`, `used`, `committed`, and `max`. `max` can be `-1` if undefined, so you must not unconditionally perform `used/max` division when displaying percentages.

Example reading multiple MBeans and handling errors per object:

\`\`\`java
ObjectName pattern =
    new ObjectName("java.lang:type=GarbageCollector,*");

for (ObjectName name : server.queryNames(pattern, null)) {
    try {
        Object count = server.getAttribute(name, "CollectionCount");
        System.out.println(name + " -> " + count);
    } catch (javax.management.InstanceNotFoundException e) {
        // The MBean disappeared after the query.
        System.out.println("MBean no longer registered: " + name);
    } catch (javax.management.AttributeNotFoundException e) {
        // The current MBean does not expose the expected attribute.
        System.out.println("Attribute unavailable on: " + name);
    }
}
\`\`\`

For remote connections, you also need to handle `IOException`, security errors, and JMX errors depending on the call. Do not assume the entire `queryNames` list remains immutable throughout the loop.

## 8. MBeanServerConnection and Spring Applications

`MBeanServer` is typically used when accessing a server within the same JVM; `MBeanServerConnection` is the common interface for both local and remote connections. The core lookup methods `queryNames`, `queryMBeans`, `isRegistered`, and `getMBeanInfo` are all present on `MBeanServerConnection`.

In Spring, you can inject a JMX connection into a service:

\`\`\`java
import java.io.IOException;
import java.util.Set;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import org.springframework.stereotype.Service;

@Service
public class JmxDiscoveryService {
    private final MBeanServerConnection connection;

    public JmxDiscoveryService(MBeanServerConnection connection) {
        this.connection = connection;
    }

    public Set<ObjectName> findCacheMBeans() throws Exception {
        ObjectName pattern = new ObjectName("demo.app:type=Cache,*");
        return connection.queryNames(pattern, null);
    }

    public boolean exists(String objectName) throws Exception {
        return connection.isRegistered(new ObjectName(objectName));
    }
}
\`\`\`

Example configuring a local connection using the platform MBeanServer:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServerConnection;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class LocalJmxClientConfiguration {
    @Bean
    public MBeanServerConnection mbeanServerConnection() {
        return ManagementFactory.getPlatformMBeanServer();
    }
}
\`\`\`

For remote JMX, Spring provides `MBeanServerConnectionFactoryBean` to bring the connection into the container through configuration. Regardless of whether the connection is created with Spring or plain JMX APIs, using `ObjectName` and `queryNames` remains the same.

Note that `MBeanProxyFactoryBean` is intended for **accessing a specific MBean by ObjectName**, not replacing querying multiple MBeans via `queryNames`. If dynamic discovery is needed, query the names first and then create or use the corresponding clients for the discovered names.

## 9. Registering a Custom MBean to Test Lookup

You can run the following minimal example using plain Java JMX; Spring only adds export utilities and lifecycle management around this mechanism.

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import java.util.Set;

interface CacheStatsMBean {
    int getItemCount();
}

public static class CacheStats implements CacheStatsMBean {
    @Override
    public int getItemCount() {
        return 42;
    }
}

MBeanServer server = ManagementFactory.getPlatformMBeanServer();
ObjectName target =
    new ObjectName("demo.app:type=Cache,name=Primary");

// In a runnable example, the public interface and class must be placed in
// the proper Java/classpath structure to comply with the Standard MBean convention.
server.registerMBean(new CacheStats(), target);

ObjectName pattern = new ObjectName("demo.app:type=Cache,*");
Set<ObjectName> matches = server.queryNames(pattern, null);
System.out.println(matches.contains(target)); // true

System.out.println(server.getAttribute(target, "ItemCount")); // 42

server.unregisterMBean(target);
System.out.println(server.isRegistered(target)); // false
\`\`\`

The code snippet shows logic fragments to place inside an appropriate class/method. `CacheStatsMBean` and `CacheStats` must be declared public in a class/interface form compliant with Standard MBean rules, or wrapped with `StandardMBean` when the class structure does not follow the default naming convention.

With Spring `@ManagedResource` and `@EnableMBeanExport`, you can omit manual registration/unregistration: Spring will export the bean under the configured ObjectName. The client's `queryNames` lookup step remains unchanged.

## 10. Common Errors and How to Distinguish Them

| Symptom | Common Cause | How to Handle |
| --- | --- | --- |
| `queryNames` returns an empty Set | Wrong domain, wrong key, wrong pattern, or connected to the wrong MBeanServer | Print canonical ObjectName, try `queryNames(null, null)` in a controlled environment, verify server |
| `MalformedObjectNameException` | Invalid ObjectName syntax, unquoted special characters | Use `ObjectName.quote(value)` for values containing special characters |
| `InstanceNotFoundException` | Name not yet registered or unregistered between two calls | Check lifecycle and handle race conditions |
| `AttributeNotFoundException` | Wrong attribute name or attribute not exposed | Inspect `getMBeanInfo` instead of guessing Java fields |
| `ReflectionException`, `MBeanException` | Operation signature mismatch or MBean-side code throws an error | Check name, parameters, signature, and root error |
| `SecurityException` or connection error | JMX access permissions, remote configuration, or network | Check authentication, TLS, firewall, and connector permissions |
| MBean found but data is unexpected | Connected to wrong server/instance or similar ObjectName | Verify JVM, server, and instance-identifying keys |

### Special Characters in ObjectName

Property values passed from user configuration may contain commas, equals signs, colons, quotation marks, asterisks, or question marks. When building names dynamically, do not concatenate strings without considering escaping rules.

\`\`\`java
String applicationName = "order,service";
String quoted = ObjectName.quote(applicationName);
ObjectName name = new ObjectName(
    "demo.app:type=Service,name=" + quoted
);
\`\`\`

`ObjectName.quote` handles the **value** part; it is not a substitute for validating the key or domain. If you must find an MBean based on a value containing a literal wildcard, you need to distinguish JMX patterns from actual quoted/escaped characters.

### Performance and Stability

- `queryNames(null, null)` searches all MBeans and can be expensive, especially when called remotely; prefer narrowing by domain/type.
- Query results are a set with no guaranteed order. If you want stable display, sort by `getCanonicalName()`.
- Do not use an ObjectName pattern as an authorization criterion. The MBeanServer/connector must enforce permissions independently.
- Avoid caching the MBean list indefinitely when components are registered/unregistered dynamically.
- If there are multiple JVMs, each connection represents one server/target; JMX does not automatically aggregate MBeans across all JVMs.

## 11. Mental Model

\`\`\`text
Spring application / JMX client
             |
             v
    MBeanServerConnection
             |
             +-- isRegistered(exactName) ------> Does specific MBean exist?
             |
             +-- queryNames(namePattern, null) -> Set of ObjectNames
             |                                     |
             |                                     +--> select ObjectName
             |                                               |
             +-- getMBeanInfo(name) <-------------------------+
             +-- getAttribute(name, attr)
             +-- invoke(name, operation, args, signature)
             |
             v
    MBeanServer registering MBeans
             |
             +-- demo.app:type=Cache,name=Primary
             +-- demo.app:type=Cache,name=Secondary
             +-- java.lang:type=Memory
\`\`\`

Quick summary: **ObjectName is the identifier; MBeanServer is the registry; `isRegistered` checks an exact name; `queryNames` searches names by pattern; `getMBeanInfo` reveals management capabilities; `getAttribute`/`invoke` perform interactions.** Spring makes configuring connections and exporting MBeans more convenient, but these JMX APIs perform the actual lookup.
