# The \`domain:key=value\` Structure of ObjectName in JMX

## 1. What Is an ObjectName Used For?

In Java Management Extensions (JMX), each MBean is registered in an \`MBeanServer\` using a **\`javax.management.ObjectName\`**. An ObjectName is a structured identifier that helps management tools and Java programs locate an MBean, read/write attributes, invoke operations, and receive notifications.

An ObjectName typically has the form:

\`\`\`text
domain:key1=value1,key2=value2,...
\`\`\`

Examples:

\`\`\`text
java.lang:type=Memory
java.lang:type=Threading
demo.app:type=Cache,name=Primary
demo.app:type=Worker,name=invoice,instance=2
\`\`\`

**How to read it:** the part before the colon is the **domain**; after it are one or more **key properties** written in the form \`key=value\`, separated by commas. It is the pair \`domain + set of key properties\` that determines the MBean's name within an MBeanServer. A Java class name or a Spring bean name is not automatically identical to its ObjectName.

In the example:

\`\`\`text
demo.app:type=Cache,name=Primary
\`\`\`

- \`demo.app\`: the domain, i.e., the logical namespace.
- \`type=Cache\`: key property indicating the type of managed resource.
- \`name=Primary\`: key property distinguishing a specific cache.
- The entire string: the MBean's ObjectName; both properties \`type\` and \`name\` together contribute to its identity.

There is no mandatory rule that every MBean must have a \`type\` or \`name\` key. Those are common conventions, not two special fields required by JMX. A valid ObjectName only needs to follow \`ObjectName\` syntax and contain a valid list of key properties.

## 2. Three-Part Structure from Left to Right

### 2.1. Domain: Logical Namespace

The domain appears before the \`:\`:

\`\`\`text
java.lang:type=Memory
^^^^^^^^^
 domain
\`\`\`

The domain usually describes the group of MBeans or the application that owns them. For example, \`java.lang\` is the domain containing the JVM's platform MBeans; an application might choose \`com.example.orders\` or \`demo.app\`. A domain is **not** the host, IP, port, or URL of a JMX server. One server can hold MBeans belonging to multiple domains, and two different servers can have the same ObjectName.

In an **exact name** (not a pattern), the domain must not contain syntax-reserved characters such as \`:\`, \`*\`, \`?\`, or newline; \`*\` and \`?\` can be used in appropriate positions when creating a **domain pattern**. An empty domain is also permitted by the parser in some forms of ObjectName; when used with an MBeanServer, the server's default domain may be applied. In real applications, you should declare the domain explicitly to avoid confusion.

A domain should have an easily recognizable name that changes rarely across application versions, for example:

\`\`\`text
com.example.orders:type=Queue,name=Pending
com.example.orders:type=Cache,name=Product
\`\`\`

### 2.2. The Colon \`:\`: Boundary

The \`:\` separates the domain from the key properties list. For example:

\`\`\`text
com.example.orders : type=Queue,name=Pending
                   ^
                 separator
\`\`\`

Spaces in the illustration are for readability; you should not insert spaces when constructing names. The parser does not interpret two \`:\` characters as two namespace levels. If you need semantic hierarchy in the domain, you can use dots \`.\` by organizational convention.

### 2.3. Key Properties: key=value Pairs

To the right of the colon is the list of key properties:

\`\`\`text
demo.app:type=Cache,name=Primary,instance=2
         |---------| |----------| |--------|
          property1   property2   property3
\`\`\`

Each key may appear only **once** in an ObjectName; repeating the same key is invalid. A key cannot be empty and cannot contain the syntax characters \`:\`, \`,\`, \`=\`, \`*\`, \`?\`, or newline. Keys are case-sensitive: \`type\` is different from \`Type\`; \`name\` is different from \`Name\`.

Values are also case-sensitive: \`Primary\` is different from \`primary\`. In an exact name, simple values generally do not need quotation marks:

\`\`\`text
demo.app:type=Cache,name=Primary
\`\`\`

An ObjectName can have multiple keys depending on the problem, but keys must represent a stable identity; you should not put continuously fluctuating metrics like \`requestsPerSecond\` into the MBean name. Those metrics should be exposed as MBean **attributes**.

## 3. Identity Does Not Depend on Key Property Order

These two strings refer to the same ObjectName:

\`\`\`text
demo.app:type=Cache,name=Primary
demo.app:name=Primary,type=Cache
\`\`\`

JMX treats the key property list as a key → value mapping when determining equality. \`ObjectName.equals()\` compares the normalized identity; \`getCanonicalName()\` returns a representation with a stable key order.

\`\`\`java
import javax.management.ObjectName;

public class CanonicalObjectNameExample {
    public static void main(String[] args) throws Exception {
        ObjectName a =
            new ObjectName("demo.app:type=Cache,name=Primary");
        ObjectName b =
            new ObjectName("demo.app:name=Primary,type=Cache");

        System.out.println(a.equals(b)); // true
        System.out.println(a.getCanonicalName());
        // demo.app:name=Primary,type=Cache

        System.out.println(a.getDomain()); // demo.app
        System.out.println(a.getKeyProperty("type")); // Cache
        System.out.println(a.getKeyProperty("name")); // Primary
    }
}
\`\`\`

Therefore, you should not compare two \`ObjectName.toString()\` strings to decide whether they refer to the same MBean; construct \`ObjectName\` instances and use \`equals()\`. When logging or storing keys for matching, \`getCanonicalName()\` is often useful.

## 4. Rules for Commas, Equals Signs, and Quotes in Values

A value may contain special characters, in which case proper quoted-value syntax must be used. For example, an application name containing a comma:

\`\`\`text
demo.app:type=Service,name="order,processor"
\`\`\`

If you write:

\`\`\`text
demo.app:type=Service,name=order,processor
\`\`\`

the comma is interpreted as a property separator; the \`processor\` part has no \`=\`, so the string is invalid.

In Java, you should use \`ObjectName.quote(value)\` when an arbitrary value might contain special characters:

\`\`\`java
import javax.management.ObjectName;

String serviceName = "order,processor";
String quotedName = ObjectName.quote(serviceName);

ObjectName objectName =
    new ObjectName("demo.app:type=Service,name=" + quotedName);

System.out.println(objectName);
// demo.app:type=Service,name="order,processor"
\`\`\`

Notable special characters in a value include \`,\`, \`=\`, \`:\`, \`"\`, \`*\`, \`?\`, backslash, and newline. When quoting, JMX has its own escape rules; \`ObjectName.quote\` helps produce syntactically valid quoted values for literal data. Do not invent your own escape function that only replaces quotation marks, and do not concatenate unvalidated data into the domain or key.

Another example:

\`\`\`java
String fileLabel = "cache=\"hot\",region=west";
ObjectName name = new ObjectName(
    "demo.app:type=Resource,label=" + ObjectName.quote(fileLabel)
);
\`\`\`

Note: **quotation marks are part of ObjectName syntax**. When reading a property with \`getKeyProperty\`, a quoted value may still include the quotation marks and escapes from the ObjectName representation. If you need the original Java value, use \`ObjectName.unquote(...)\` on a validly quoted string:

\`\`\`java
String raw = ObjectName.unquote(name.getKeyProperty("label"));
System.out.println(raw); // cache="hot",region=west
\`\`\`

Do not automatically call \`unquote\` on a property value that is not in quoted form.

## 5. Exact ObjectName and ObjectName Pattern

ObjectName serves two important purposes:

1. **Exact name:** specifies a concrete MBean.
2. **Pattern:** describes a set of ObjectNames for querying.

Example of an exact name:

\`\`\`text
demo.app:type=Cache,name=Primary
\`\`\`

Examples of patterns:

\`\`\`text
demo.app:*
demo.app:type=Cache,*
demo.app:type=Cache,name=*
*:type=Cache,*
\`\`\`

Common symbols:

| Syntax | Meaning |
| --- | --- |
| \`*\` in domain | Matches a domain substring as a wildcard |
| \`?\` in domain | Matches a single domain character |
| \`name=foo*\` | Property value pattern starting with \`foo\` |
| \`name=foo?\` | Property value pattern starting with \`foo\` followed by exactly one character |
| \`,*\` at the end of the key properties list | Allows additional properties beyond the listed keys |
| \`domain:*\` | Matches any property list in the corresponding domain |

For example:

\`\`\`text
demo.app:type=Cache,*
\`\`\`

matches names such as:

\`\`\`text
demo.app:type=Cache,name=Primary
demo.app:type=Cache,name=Secondary,instance=2
\`\`\`

because they all have \`type=Cache\` and other properties are allowed. Conversely, the pattern:

\`\`\`text
demo.app:type=Cache,name=*
\`\`\`

has a different meaning: here there is a **value pattern** for \`name\`, but without \`,*\`, the key list in a matching object must correspond to the listed keys; an MBean with an additional \`instance=2\` may not match.

This is a common point of confusion: **wildcards in values** and **wildcards for the key properties list** are two separate mechanisms.

\`\`\`java
import javax.management.ObjectName;

ObjectName exact =
    new ObjectName("demo.app:type=Cache,name=Primary");
ObjectName byType =
    new ObjectName("demo.app:type=Cache,*");
ObjectName byNamePattern =
    new ObjectName("demo.app:type=Cache,name=Pri*");

System.out.println(exact.isPattern()); // false
System.out.println(byType.isPattern()); // true
System.out.println(byType.isPropertyListPattern()); // true
System.out.println(byNamePattern.isPropertyValuePattern()); // true
\`\`\`

ObjectName patterns are used for **querying**, such as \`MBeanServer.queryNames(pattern, null)\`. Do not register an MBean with an ObjectName pattern: each MBean is registered under an **exact name**.

## 6. Distinguishing Literal Wildcard Characters from Pattern Wildcards

When a value actually contains \`*\` or \`?\`, the application needs to represent them as data, not as search criteria. Placing a value in quotation marks **does not by itself guarantee** that wildcard characters lose their pattern meaning: ObjectName has dedicated escape rules for \`*\` and \`?\`. Use the \`ObjectName.quote(value)\` API, because this method escapes wildcards when needed.

\`\`\`java
String logicalName = "batch*special";
ObjectName literalName = new ObjectName(
    "demo.app:type=Job,name=" + ObjectName.quote(logicalName)
);

System.out.println(literalName.isPattern()); // false
\`\`\`

Conversely, if the goal is to find names starting with \`batch\`, intentionally construct a pattern:

\`\`\`java
ObjectName pattern =
    new ObjectName("demo.app:type=Job,name=batch*,*");

System.out.println(pattern.isPattern()); // true
\`\`\`

This is different from using \`ObjectName.quote("batch*")\`: the quote method expresses a literal string containing an asterisk. The right choice depends on whether you want to **identify a single MBean whose name contains special characters** or **find multiple MBeans using a wildcard**.

## 7. Creating ObjectName Safely with the Java API

For static names, the most readable way is to pass the whole string to the constructor:

\`\`\`java
ObjectName name =
    new ObjectName("com.example.orders:type=Queue,name=Pending");
\`\`\`

For dynamic keys/values, you can use the \`ObjectName(String domain, Hashtable<String,String> table)\` constructor:

\`\`\`java
import java.util.Hashtable;
import javax.management.ObjectName;

Hashtable<String, String> properties = new Hashtable<>();
properties.put("type", "Queue");
properties.put("name", "Pending");

ObjectName name =
    new ObjectName("com.example.orders", properties);
\`\`\`

This constructor avoids manually concatenating commas and equals signs for simple properties. When a value contains characters that require quoting, you still must ensure the value is represented using proper ObjectName syntax; the constructor does not automatically turn every invalid string into a safe literal value.

Example of a name-building method for an arbitrary name part:

\`\`\`java
import javax.management.MalformedObjectNameException;
import javax.management.ObjectName;

public final class JmxNames {
    private JmxNames() {}

    public static ObjectName queue(String queueName)
            throws MalformedObjectNameException {
        return new ObjectName(
            "com.example.orders:type=Queue,name="
            + ObjectName.quote(queueName)
        );
    }
}
\`\`\`

With \`queue("priority,west")\`, the returned name will contain the value \`"priority,west"\`, preventing it from being mistakenly split into two properties.

**Convention note:** once you decide what \`type\`, \`name\`, and \`instance\` mean, use them consistently across services and deployments. Changing a key or value changes the ObjectName, which can break dashboards or clients referencing the old name.

## 8. Registering and Looking Up MBeans by ObjectName

Here is an example using an existing platform MBean for lookup, without needing to write a new MBean:

\`\`\`java
import java.lang.management.ManagementFactory;
import java.util.Set;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class ObjectNameLookupDemo {
    public static void main(String[] args) throws Exception {
        MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();

        ObjectName exact =
            new ObjectName("java.lang:type=Memory");

        System.out.println(server.isRegistered(exact)); // true

        ObjectName pattern =
            new ObjectName("java.lang:type=GarbageCollector,*");

        Set<ObjectName> names = server.queryNames(pattern, null);

        names.stream()
            .map(ObjectName::getCanonicalName)
            .sorted()
            .forEach(System.out::println);
    }
}
\`\`\`

In the example:

- \`isRegistered(exact)\` checks whether the exact name is already on the MBeanServer.
- \`queryNames(pattern, null)\` returns the set of names that match the pattern and are currently registered.
- \`getCanonicalName()\` helps log in a stable key order; \`sorted()\` stabilizes display order because \`Set\` does not guarantee order.
- Garbage collector results depend on the JVM, GC configuration, and runtime; you should not hard-code collector names.

To read an attribute after looking up a specific name:

\`\`\`java
ObjectName memory =
    new ObjectName("java.lang:type=Memory");

Object heapUsage =
    server.getAttribute(memory, "HeapMemoryUsage");

System.out.println(heapUsage);
\`\`\`

If the ObjectName is not registered, \`getAttribute\` may throw \`InstanceNotFoundException\`. If the MBean does not expose the requested attribute, the call may throw \`AttributeNotFoundException\`. Check \`getMBeanInfo\` when unsure of an MBean's management interface.

## 9. How Does Spring Framework Use ObjectName?

Spring Framework integrates with JMX via \`MBeanExporter\`, management annotations, and naming strategies. ObjectName **still uses exact standard JMX syntax**.

Example of exposing a Spring bean:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.orders:type=Queue,name=Pending",
    description = "Number of pending jobs"
)
public class PendingQueueMonitor {
    @ManagedAttribute
    public int getPendingCount() {
        return 12; // Replace with real data.
    }
}
\`\`\`

Enable annotation export:

\`\`\`java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxConfiguration {}
\`\`\`

Spring reads the metadata, creates or adapts the MBean, and registers it with the MBeanServer. JMX tools still access it via:

\`\`\`text
com.example.orders:type=Queue,name=Pending
\`\`\`

If a static ObjectName is not specified via annotation, Spring can use an \`ObjectNamingStrategy\` to generate the name from bean/metadata information. For example, \`MetadataNamingStrategy\` uses management metadata; \`KeyNamingStrategy\` uses a configured name mapping. Regardless of which strategy generates the name, the final result is still a valid JMX \`ObjectName\`.

Several rules when designing ObjectNames in a Spring application:

1. Separate the **Spring bean name** from the **JMX ObjectName**: the two kinds of names serve two different registries.
2. Use meaningful domains and key properties, such as \`com.example.orders:type=Queue,name=Pending\`.
3. When deploying multiple instances into the same MBeanServer, ensure ObjectNames do not collide, for example by adding a stable \`instance=...\`.
4. Do not use secrets, tokens, passwords, or personal data as key properties: ObjectNames readily appear in monitoring tools and logs.
5. Do not use ObjectName to express continuously changing metrics; metrics belong in attributes or the corresponding observability source.

## 10. Common Syntax and Modeling Mistakes

| Case | Why It Is a Problem | How to Handle It |
| --- | --- | --- |
| \`demo.app:type=Cache,name=Primary\` | Valid exact name | Use when the specific MBean is known |
| \`demo.app:type=Cache,name=Primary,name=Other\` | Duplicate \`name\` key | Rename to distinct keys or remove the duplicate |
| \`demo.app:type=Cache,name=order,processor\` | \`processor\` is missing \`=...\` | Quote the entire value containing the comma |
| \`demo.app:type=Cache,name=order:processor\` | \`:\` appears in an unquoted value | Use \`ObjectName.quote\` |
| \`demo.app:type=Cache,*\` | It is a pattern, not a specific registration name | Use only for querying |
| \`demo.app:type=Cache,name=Primary\` and \`demo.app:name=Primary,type=Cache\` | Two strings with different key order but the same identity | Compare using \`ObjectName.equals()\` |
| \`demo.app:type=cache\` and \`demo.app:type=Cache\` | Values are case-sensitive | Standardize naming conventions |
| \`demo.app:Name=Primary\` and \`demo.app:name=Primary\` | Keys are case-sensitive | Standardize key names |
| \`demo.app:type=Cache,name=Primary\` across two JVMs | May be two different MBeans on two servers | Identify the right MBeanServer connection |

Useful methods for diagnostics:

\`\`\`java
ObjectName name =
    new ObjectName("demo.app:type=Cache,name=Primary");

System.out.println(name.getDomain());
System.out.println(name.getKeyPropertyList());
System.out.println(name.getKeyProperty("type"));
System.out.println(name.getCanonicalName());
System.out.println(name.isPattern());
System.out.println(name.isDomainPattern());
System.out.println(name.isPropertyPattern());
\`\`\`

When encountering \`MalformedObjectNameException\`, check the \`domain:properties\` boundary, duplicate keys, special characters in values, and quoting/escaping. When the name is valid but the MBean is not found, the cause usually relates to the connected server, the actual registered name, or the MBean lifecycle, not necessarily a syntax error.

## 11. Concise Mental Model

\`\`\`text
ObjectName = domain : key=value [, key=value ...]
             |          |
             |          +-- Properties that IDENTIFY the MBean
             +------------- Logical namespace

Example:
com.example.orders:type=Queue,name=Pending,instance=1
|----------------| |--------| |----------| |--------|
      domain       key/value   key/value   key/value

ObjectName exact  -> registerMBean / isRegistered / getAttribute / invoke
ObjectName pattern -> queryNames / queryMBeans
MBeanServer        -> registry storing ObjectNames and corresponding MBeans
\`\`\`

**Key takeaway:** ObjectName is a structured, case-sensitive name; the domain and **the entire set of key/value pairs** identify the MBean; key order does not change identity; values with special characters must be properly quoted/escaped; wildcards create patterns for querying. Spring makes publishing and naming MBeans more convenient, but the \`domain:key=value\` syntax remains entirely standard JMX.
