# ObjectName, Domain, Key Properties, and MBean Identification

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain why every MBean registered in an \`MBeanServer\` requires an \`ObjectName\` identifier.
- Read and construct names in the form \`domain:key=value,key2=value2\`; distinguish the domain from key properties.
- Understand whether an \`ObjectName\` represents a concrete name or a pattern used for querying.
- Distinguish display names, Java class names, Spring bean names, and JMX identifiers.
- Register, search, operate on, and unregister MBeans using Java Management Extensions (JMX).
- Avoid errors with special characters, property ordering, and duplicate identifiers in applications.

## 2. Context: Where Are MBeans Identified?

JMX (Java Management Extensions) is the standard Java mechanism for monitoring and managing resources while an application is running. A resource can be a cache, queue, connector, counter, or a business component with operational state.

An **MBean** provides readable/writable attributes, invocable operations, and management notifications. **MBeanServer** is where MBeans are registered so management tools can access them. Upon registration, each MBean has a **\`javax.management.ObjectName\`** as its identifier key within the scope of that MBeanServer.

For example, an application has two caches:

\`\`\`text
com.example.app:type=Cache,name=products
com.example.app:type=Cache,name=customers
\`\`\`

Both share the same domain and resource type, but differ in the \`name\` value. Tools like JConsole can list two separate MBeans, read \`Size\`, invoke \`clear()\`, etc., if those attributes/operations are actually provided by the MBean.

**Note:** \`ObjectName\` does not create attributes, operations, or access permissions by itself. It is solely an identifier for the server to look up the right MBean. Available management capabilities are defined by the MBean's interface/metadata.

## 3. Structure of an ObjectName

General form:

\`\`\`text
<domain>:<key1>=<value1>,<key2>=<value2>,...
\`\`\`

Example:

\`\`\`text
com.example.shop:type=Cache,name=productCache,instance=primary
\`\`\`

| Component | Value in Example | Meaning |
|---|---|---|
| Domain | \`com.example.shop\` | Namespace for grouping resources |
| Key property \`type\` | \`Cache\` | Categorizes the MBean |
| Key property \`name\` | \`productCache\` | Specific resource name |
| Key property \`instance\` | \`primary\` | Distinguishes an instance when needed |

Domain names usually follow reverse DNS conventions (\`com.example.shop\`, \`org.acme.orders\`) to reduce collisions between libraries and applications, though JMX does not require the domain to be a valid Java package or DNS name. The domain is part of the identifier, not a hostname, URL, or where the MBean is deployed.

A **key property** is a \`key=value\` pair. They do not necessarily correspond to fields or JMX attributes of the MBean. For example, the key \`name=productCache\` is only used for identification; the MBean does not automatically get a \`Name\` attribute.

A concrete \`ObjectName\` must have a domain, a \`:\` character, and at least one key property. An \`ObjectName\` can be an exact name (to register or access a single MBean) or a pattern (to find MBeans matching a condition). The two kinds serve different roles.

## 4. Domain: Logical Namespace

Domains help distinguish MBeans coming from different systems/libraries within the same MBeanServer.

\`\`\`text
java.lang:type=Memory
java.lang:type=Threading
com.example.shop:type=Cache,name=products
com.example.shop:type=Queue,name=orders
\`\`\`

- \`java.lang\` is a standard domain commonly seen in the platform MBeanServer.
- \`com.example.shop\` is the application's own domain in the example.
- Domains can be shared across multiple MBeans; the combination of **domain + all key properties** forms the identifier.
- JMX domains do not guarantee security isolation or multi-tenancy by themselves. Access permissions and connection mechanisms are managed separately.

If you create an \`ObjectName\` with an empty domain, the MBeanServer may apply a default domain upon registration. In application code, it is best to specify an explicit domain so names are stable and easy to look up across environments.

When multiple libraries use \`type=Cache,name=default\` in the same server, separate domains help prevent collisions. However, a separate domain does not solve the case where two instances of the same application use the same name: a distinguishing key must be added.

## 5. Key Properties and Unique Names

Common keys by convention are:

- \`type\`: resource type, e.g. \`Cache\`, \`DataSource\`, \`Worker\`.
- \`name\`: logical name, e.g. \`products\`, \`orders\`.
- \`id\`, \`instance\`, or \`node\`: instance identifier.
- \`module\`, \`component\`, \`tenant\`: application group or business scope, if genuinely needed.

JMX does not mandate having \`type\` or \`name\`: that is a design choice. There is no special meaning for these keys at the \`ObjectName\` level. Two \`ObjectName\`s with the same domain and the same *set* of key-value pairs represent the same identifier even if the keys are written in a different order.

Example:

\`\`\`text
com.example.shop:type=Cache,name=products
com.example.shop:name=products,type=Cache
\`\`\`

The two lines above represent the same JMX name according to \`ObjectName.equals()\`, because key ordering does not create a new identifier.

Conversely:

\`\`\`text
com.example.shop:type=Cache,name=products
com.example.shop:type=Cache,name=customers
\`\`\`

are two different names because the value of the \`name\` key differs.

Within one \`MBeanServer\`, two MBeans cannot be registered under the same concrete \`ObjectName\` at the same time. If the name already exists, \`registerMBean\` throws \`InstanceAlreadyExistsException\`. Identical name strings in two independent MBeanServers do not automatically point to the same object; the server is part of the lookup context.

### Designing Stable Keys

Use enough keys to distinguish resources that truly need independent management. For instance, each database pool has its own \`name\`:

\`\`\`text
com.example.shop:type=ConnectionPool,name=orders
com.example.shop:type=ConnectionPool,name=analytics
\`\`\`

Avoid putting fast-changing values into the name, such as cache size, current request count, or update timestamps. Changing a key means changing the identifier; tools looking up the old name may no longer be able to access the MBean. Dynamic measurements should be JMX attributes.

## 6. Constructing ObjectName in Java

\`ObjectName\` belongs to the \`javax.management\` package, which is a JDK API; no separate Spring library is needed to construct names.

\`\`\`java
import javax.management.MalformedObjectNameException;
import javax.management.ObjectName;

public class ObjectNameExample {
    public static void main(String[] args)
            throws MalformedObjectNameException {

        ObjectName cache = new ObjectName(
                "com.example.shop:type=Cache,name=products");

        System.out.println(cache.getDomain());
        // com.example.shop

        System.out.println(cache.getKeyProperty("type"));
        // Cache

        System.out.println(cache.getKeyProperty("name"));
        // products

        System.out.println(cache.isPattern());
        // false

        System.out.println(cache.getCanonicalName());
        // com.example.shop:name=products,type=Cache
    }
}
\`\`\`

\`getCanonicalName()\` represents key properties in canonical order sorted by key. \`toString()\`/\`getKeyPropertyListString()\` may preserve the display order as entered; do not use the order in that string to infer different names. When semantic comparison is needed, use \`equals()\` or data structures backed by \`ObjectName\`.

You can construct an \`ObjectName\` from a \`Hashtable\` of key properties to reduce manual string-assembly errors:

\`\`\`java
import java.util.Hashtable;
import javax.management.ObjectName;

Hashtable<String, String> props = new Hashtable<>();
props.put("type", "Cache");
props.put("name", "products");

ObjectName name = new ObjectName("com.example.shop", props);
\`\`\`

Both string and table constructors must adhere to \`ObjectName\` character rules. For user-supplied values, do not concatenate them directly into a string without handling special characters.

## 7. Special Characters, Quoting, and Dynamic Values

\`ObjectName\` grammar uses characters like \`:\`, \`,\`, \`=\`, \`*\`, and \`?\` for syntax or wildcard purposes. Values containing commas, equals signs, colons, double quotes, newlines, or wildcards must be handled properly if you want to preserve that value as intact data.

JMX provides \`ObjectName.quote(String)\` to produce a quoted representation of a value; \`ObjectName.unquote(String)\` decodes a valid quoted representation.

\`\`\`java
import javax.management.ObjectName;

String logicalName = "inventory,west=primary";
String encoded = ObjectName.quote(logicalName);

ObjectName name = new ObjectName(
        "com.example.shop:type=Cache,name=" + encoded);

System.out.println(name.getKeyProperty("name"));
// "inventory,west=primary" (value in quoted syntax)

System.out.println(ObjectName.unquote(
        name.getKeyProperty("name")));
// inventory,west=primary
\`\`\`

Pay close attention: \`getKeyProperty("name")\` on a name with a quoted value returns the quoted key property representation, not always the unquoted data string. This matters when mapping bidirectionally between system names and JMX names.

**Wildcards inside quotes can still carry pattern semantics.** \`ObjectName.quote\` escapes syntax properly, but it is not a mechanism to neutralize all wildcards: \`*\` and \`?\` characters belong to \`ObjectName\` pattern rules; check \`isPattern()\` if the name must be a concrete registration name. Avoid passing arbitrary input containing wildcard characters into registration names. If an absolutely safe name is needed for arbitrary data, encode the data into a non-special character set (e.g., unpadded URL-safe Base64) and store the original value in an MBean attribute. Do not attempt to register a pattern.

Verification example:

\`\`\`java
ObjectName concrete = new ObjectName(
        "com.example.shop:type=Cache,name=products");

if (concrete.isPattern()) {
    throw new IllegalArgumentException(
            "MBean registration name must be a concrete ObjectName");
}
\`\`\`

### Case Sensitivity Rules

JMX names are case-sensitive:

\`\`\`text
com.example.shop:type=Cache,name=products
com.example.shop:type=cache,name=products
\`\`\`

These are two different \`ObjectName\`s. Standardize the casing convention for \`type\`, \`name\`, and domain so queries and dashboards do not miss resources.

## 8. ObjectName Patterns for Finding MBeans

\`MBeanServer.queryNames\` allows looking up names matching an \`ObjectName\` pattern. \`*\` represents any sequence of characters, and \`?\` represents a single character in permitted parts. Besides value patterns, there is also a property-list pattern with \`,*\`.

Examples:

\`\`\`text
com.example.shop:type=Cache,*
com.example.shop:type=Cache,name=prod*
com.example.*:type=Cache,*
*:type=Cache,*
\`\`\`

- \`com.example.shop:type=Cache,*\` matches MBeans in that exact domain with \`type=Cache\`, even if they have additional key properties.
- \`com.example.shop:type=Cache,name=prod*\` matches names whose \`name\` key starts with \`prod\` and may contain additional keys.
- \`com.example.*:type=Cache,*\` denotes a domain pattern.
- \`*:type=Cache,*\` queries across multiple domains by the \`type\` property.

Commonly confused difference:

\`\`\`text
com.example.shop:type=Cache
com.example.shop:type=Cache,*
\`\`\`

The first name is a **concrete** name with exactly one key. The second is a **property-list pattern** that can match MBeans containing \`type=Cache\` plus other keys. Use \`isPropertyListPattern()\`, \`isPropertyValuePattern()\`, and \`isDomainPattern()\` to identify the pattern kind.

Query example:

\`\`\`java
import java.lang.management.ManagementFactory;
import java.util.Set;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();

ObjectName query = new ObjectName(
        "com.example.shop:type=Cache,*");

Set<ObjectName> matching = server.queryNames(query, null);

for (ObjectName candidate : matching) {
    System.out.println(candidate.getCanonicalName());
}
\`\`\`

\`null\` for the \`QueryExp\` parameter means no additional \`QueryExp\` filter is added; filtering still applies based on the passed \`ObjectName\`. The result is a \`Set\`, so stable iteration order should not be assumed. Sort when deterministic display ordering is needed.

Do not register an MBean under a pattern \`ObjectName\`. Patterns are only for matching/querying.

## 9. Complete Example: Registering and Querying a Standard MBean

A Standard MBean is defined by an interface named by the \`<ClassName>MBean\` convention, with public getters and operations, alongside a corresponding implementation class.

**File \`CacheMetricsMBean.java\`:**

\`\`\`java
public interface CacheMetricsMBean {
    int getEntryCount();
    void clear();
}
\`\`\`

**File \`CacheMetrics.java\`:**

\`\`\`java
public class CacheMetrics implements CacheMetricsMBean {
    private int entryCount = 3;

    @Override
    public int getEntryCount() {
        return entryCount;
    }

    @Override
    public void clear() {
        entryCount = 0;
    }
}
\`\`\`

**File \`JmxRegistrationDemo.java\`:**

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class JmxRegistrationDemo {
    public static void main(String[] args) throws Exception {
        MBeanServer server =
                ManagementFactory.getPlatformMBeanServer();

        ObjectName name = new ObjectName(
                "com.example.shop:type=Cache,name=products");

        if (server.isRegistered(name)) {
            throw new IllegalStateException(
                    "MBean already exists: " + name);
        }

        server.registerMBean(new CacheMetrics(), name);

        try {
            Object before =
                    server.getAttribute(name, "EntryCount");
            System.out.println("Before clear: " + before);

            server.invoke(name, "clear",
                    new Object[0], new String[0]);

            Object after =
                    server.getAttribute(name, "EntryCount");
            System.out.println("After clear: " + after);
        } finally {
            server.unregisterMBean(name);
        }
    }
}
\`\`\`

Expected output:

\`\`\`text
Before clear: 3
After clear: 0
\`\`\`

Flow explanation:

1. \`getPlatformMBeanServer()\` obtains the JMX server of the running JVM.
2. \`new ObjectName(...)\` builds the concrete identifier.
3. \`registerMBean\` maps the identifier to the \`CacheMetrics\` instance.
4. \`getAttribute\` reads the JMX attribute \`EntryCount\`, exposed by \`getEntryCount()\`.
5. \`invoke\` calls the \`clear\` operation, then checks the attribute again.
6. \`unregisterMBean\` removes the registration, preventing the identifier from lingering after the demo lifecycle.

Checking \`isRegistered\` before \`registerMBean\` is only for a clear message; it does not prevent race conditions if multiple threads register concurrently. Production application code must still handle \`InstanceAlreadyExistsException\` thrown by the registration call.

To run the demo, place all three files in the same directory, compile with \`javac *.java\` (or the shell equivalent), and run \`java JmxRegistrationDemo\`. The demo program exits immediately, making it hard to observe with JConsole. To observe via a GUI, keep the JVM running while the MBean remains registered.

## 10. Interacting with Spring Framework

Spring JMX supports exporting beans as MBeans via \`MBeanExporter\` or \`@ManagedResource\`/\`@ManagedAttribute\`/\`@ManagedOperation\`, if the application configures an appropriate export mechanism. The annotations support declaring an ObjectName within the resource definition.

Illustrative example:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.shop:type=Cache,name=products",
    description = "Cache metrics")
public class ProductCacheMonitor {

    private volatile int entryCount;

    @ManagedAttribute
    public int getEntryCount() {
        return entryCount;
    }
}
\`\`\`

\`@ManagedResource\` and \`@ManagedAttribute\` describe the resource and attribute; the class must be managed by Spring and exported through an appropriate JMX mechanism for the MBean to appear in the MBeanServer. Do not assume that merely adding annotations to an arbitrary class will automatically register an MBean.

The same Spring bean can have an application context name like \`productCacheMonitor\` and a JMX name like \`com.example.shop:type=Cache,name=products\`. The two names belong to **two different namespaces**. If you move or rename the Spring bean, the JMX name may or may not change, depending on the exporter/naming strategy configuration.

Spring provides mechanisms for selecting names on export and resolving collisions. Whether using Spring Boot or plain Spring Framework, inspect the actual \`ObjectName\` in MBeanServer/JConsole instead of assuming every bean is exported with a single naming pattern.

## 11. Common Errors and How to Handle Them

| Symptom | Common Cause | How to Handle |
|---|---|---|
| \`MalformedObjectNameException\` | Invalid \`domain:key=value\` syntax, unencoded special characters, or invalid key | Use the right constructor, quote/encode data, check patterns |
| \`InstanceAlreadyExistsException\` | An MBean with the same ObjectName already exists in the same server | Standardize naming conventions, add an \`instance\` key if needed, manage lifecycle |
| \`InstanceNotFoundException\` | Looking up a nonexistent name or an unregistered MBean | Verify exact name and target server, check domain/key/case |
| Query \`type=Cache\` returns no results | Query lacks \`,*\` while the MBean has other keys | Use \`type=Cache,*\` if you want to allow additional keys |
| MBean exists but attribute is missing | ObjectName is right, but MBean interface/metadata does not expose that attribute | Check Standard MBean/MXBean interface or annotations/exporter |
| Dashboard loses data after deploy | Key contains an ID that changes unnecessarily or naming convention changed | Use stable names for logical resources, move dynamic metadata to attributes |
| Name collision when running multiple instances | Same domain and key-values in one MBeanServer | Add an instance-identifying key when objects coexist in the server |
| Query returns unexpected results | Using a broad wildcard or passing pattern values | Restrict domain/keys and check \`isPattern()\` |

Other exceptions relate to invalid MBean interfaces, access control, or remote JMX connections. Distinguishing **identification** errors from **export configuration / networking / access permission** errors speeds up diagnosis.

## 12. Practice: Verifying Identifiers and Patterns

### Exercise A — Comparing ObjectNames

Predict the output:

\`\`\`java
ObjectName a = new ObjectName(
        "com.example.shop:type=Cache,name=products");
ObjectName b = new ObjectName(
        "com.example.shop:name=products,type=Cache");
ObjectName c = new ObjectName(
        "com.example.shop:type=Cache,name=customers");

System.out.println(a.equals(b));
System.out.println(a.equals(c));
\`\`\`

**Answer:** \`true\` then \`false\`. Key order does not distinguish names; the \`name\` value does.

### Exercise B — Querying with Additional Keys

Suppose MBeans are registered with the names:

\`\`\`text
com.example.shop:type=Cache,name=products,instance=a
com.example.shop:type=Cache,name=products,instance=b
com.example.shop:type=Queue,name=orders
\`\`\`

Choose a pattern to find both caches:

\`\`\`text
com.example.shop:type=Cache,name=products,*
\`\`\`

The pattern with \`,*\` matches names containing the extra \`instance\` key. The name \`com.example.shop:type=Cache,name=products\` (without wildcard) will not match the two names that have an extra key.

### Exercise C — Creating an ObjectName with Special Data

Given the logical name \`inventory,west=primary\`, use \`ObjectName.quote\` to create the representation, call \`ObjectName.unquote\` to recover the exact data, and check \`isPattern()\`. Then test data containing \`*\` or \`?\` to see why syntax quoting must be distinguished from wildcard patterns.

### Exercise D — Registration Lifecycle

Run the \`JmxRegistrationDemo\` demo and observe:

- Before registration, \`server.isRegistered(name)\` returns \`false\`.
- After registration, it returns \`true\`; call \`getAttribute\` and \`invoke\` by name.
- After unregistration, it returns \`false\`; accessing the attribute by the old name will not find the instance.

## 13. Takeaways

- \`ObjectName\` is the JMX identifier for an MBean within a **specific MBeanServer**.
- Syntax consists of domain and key properties: \`domain:key=value,...\`.
- Domain groups namespaces; the set of key properties distinguishes resources. Key order does not affect equality; case sensitivity does.
- \`getCanonicalName()\` normalizes key representation; \`equals()\` compares identifiers.
- Concrete \`ObjectName\`s are used for registering, reading attributes, and invoking operations; pattern \`ObjectName\`s are used for querying.
- Externally received values need handling for special characters and wildcards. \`quote\` solves quoting syntax, but \`isPattern()\` should be checked before registration.
- Spring bean names, Java class names, and JMX names are conceptually independent; export and naming strategies determine their actual relationship.
- Choose a stable, intentional naming convention that is easy to query and does not mix fast-changing operational data into the ObjectName.

## 14. References

- Java SE API — \`javax.management.ObjectName\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/ObjectName.html
- Java SE API — \`javax.management.MBeanServer\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
- Oracle JMX Technology Tutorial: https://docs.oracle.com/javase/tutorial/jmx/
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
