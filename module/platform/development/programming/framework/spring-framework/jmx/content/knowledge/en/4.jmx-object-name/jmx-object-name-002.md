# ObjectName: Property Keys, Property Values, and Characters Requiring Escaping

## 1. What Is an ObjectName Used For?

In Java Management Extensions (JMX), \`javax.management.ObjectName\` identifies an MBean inside an \`MBeanServer\`. When registering, reading attributes, invoking operations, or searching for MBeans, an application uses an \`ObjectName\` rather than an arbitrary string name.

A name has the structure:

\`\`\`text
domain:key1=value1,key2=value2,...
\`\`\`

For example:

\`\`\`text
com.example.orders:type=Cache,name=Products,region=asia
\`\`\`

Here \`com.example.orders\` is the **domain**; \`type\`, \`name\`, and \`region\` are **property keys** (attribute names in the key-property list), while \`Cache\`, \`Products\`, and \`asia\` are **property values**. These key-properties establish the MBean's identity. They **differ from MBean attributes** read via \`MBeanServer.getAttribute(name, "Size")\`: \`name=Products\` is part of the identity, whereas \`Size\` is a management attribute of the MBean.

Three concepts need to be distinguished:

1. **Domain**: the namespace before the \`:\`.
2. **Key properties**: \`key=value\` pairs after the \`:\`, separated by commas.
3. **Pattern**: an \`ObjectName\` using wildcards to query multiple MBeans, not a concrete name used for registration.

## 2. Syntax and Basic Rules

\`\`\`text
domain:key=value[,key=value...]
\`\`\`

- The domain can use a reverse package name, such as \`com.example.app\`, to avoid collisions.
- Each property key must have a valid name, cannot be empty, and cannot be repeated within the same \`ObjectName\`.
- A property value can be **unquoted** or **enclosed in double quotes**. Double quotes have syntactic significance; when displaying the full name, they remain in the value's string representation.
- For a concrete name, special characters must be handled so that the \`ObjectName\` does not unintentionally become a pattern.
- The order of key-property pairs in the input string does not determine identity. Two names with the same domain and the same set of key/value pairs are considered the same \`ObjectName\`, even if the pair order differs.

For example:

\`\`\`java
import javax.management.ObjectName;

ObjectName first =
    new ObjectName("com.example:type=Cache,name=Products");
ObjectName second =
    new ObjectName("com.example:name=Products,type=Cache");

System.out.println(first.equals(second)); // true
System.out.println(first.getCanonicalName());
// com.example:name=Products,type=Cache
\`\`\`

\`getCanonicalName()\` sorts the key properties in canonical order. When storing names for matching, logging, or deduplication, using \`ObjectName\` or the canonical name is more reliable than raw string comparison.

## 3. Property Key Names: What Is Valid?

The key sits to the left of the \`=\`. It must be a non-empty name and must not contain reserved syntax characters such as:

\`\`\`text
,  =  :  *  ?
\`\`\`

Newline and double-quote characters are also invalid in property keys. Spaces are syntactically allowed, but you should use short, stable, readable keys without spaces, such as \`type\`, \`name\`, \`component\`, \`tenant\`, and \`instance\`.

Example of a clear name:

\`\`\`text
com.example:type=Worker,name=Import,instance=one
\`\`\`

Avoid directly using user-supplied names as keys. If a dynamic dimension such as a tenant ID is needed, keep the key name fixed (\`tenant\`) and handle the tenant ID as the **value** after normalization/quoting.

Keys like \`type\` or \`name\` are common conventions, not mandatory fields with special meaning in JMX. You can use \`service\`, \`shard\`, \`region\`, or \`pool\` as long as the names are valid and consistent.

## 4. Unquoted Values and Quoted Values

An unquoted property value is generally suitable for simple values:

\`\`\`text
com.example:type=Queue,name=jobs
com.example:type=Queue,name=jobs-prod
com.example:type=Queue,name=jobs_01
\`\`\`

Characters such as comma \`,\`, equals sign \`=\`, colon \`:\`, or double quote \`"\` cannot be placed arbitrarily in an unquoted value; they can cause parsing failures or lead the parser to interpret a different structure. The characters \`*\` and \`?\` are particularly dangerous because they act as wildcards in patterns.

For values containing special characters, use the quoted form:

\`\`\`text
com.example:type=Queue,name="jobs,urgent"
com.example:type=Queue,name="region=apac"
com.example:type=Queue,name="https://internal.example"
\`\`\`

The outer double quotes are part of the value syntax. Java provides the \`ObjectName.quote(String)\` API to construct safe values from dynamic data instead of replacing characters manually.

\`\`\`java
import javax.management.ObjectName;

String displayName = "orders,priority=high";
String safeValue = ObjectName.quote(displayName);

ObjectName objectName = new ObjectName(
    "com.example:type=Queue,name=" + safeValue
);

System.out.println(objectName.getKeyProperty("name"));
// "orders,priority=high" (quoted form)
System.out.println(
    ObjectName.unquote(objectName.getKeyProperty("name"))
);
// orders,priority=high
\`\`\`

**Common pitfall:** \`getKeyProperty("name")\` may return the value **with double quotes and escapes**, without automatically unquoting it. If you want the original string that was quoted, use \`ObjectName.unquote(...)\` in the appropriate case. \`unquote\` expects a valid quoted string; do not call it indiscriminately on every unquoted value.

## 5. Escape Characters in Quoted Values

Inside a quoted value, the backslash \`\\\` is the escape character. Important representations:

| Character in Data | Representation Inside Quoted ObjectName Value | Notes |
| --- | --- | --- |
| Double quote \`"\` | \`\"\` | Does not terminate the quoted value |
| Backslash \`\\\` | \`\\\` | Preserves the backslash in the data |
| Newline | \`\n\` | Escapes a newline in the value |
| Asterisk \`*\` | \`\\*\` | Literal asterisk, does not become a wildcard |
| Question mark \`?\` | \`\\?\` | Literal question mark, does not become a wildcard |
| Comma \`,\` | Left as-is between double quotes | Not treated as a key-property separator |
| Equals sign \`=\` | Left as-is between double quotes | Not treated as a key/value separator |

Examples of names representing literal wildcards:

\`\`\`text
com.example:type=Queue,name="orders\*"
com.example:type=Queue,name="requests\?"
\`\`\`

Both can serve as concrete names because the wildcards are escaped. Conversely, \`name="orders*"\` represents a value pattern, even though it is inside double quotes.

To avoid confusing escape layers, distinguish:

- **Java data string:** the characters the application wants to name.
- **ObjectName string:** quoted/escaped according to JMX grammar.
- **Java source literal:** to put a \`\\\` in a String in Java source code you must write \`\\\\\`; to put a double quote you must write \`\"\` in the literal.

The reliable approach is to construct the ObjectName value via the API:

\`\`\`java
import javax.management.ObjectName;

String raw = "order\"batch\\A,*?\nnext";
String quoted = ObjectName.quote(raw);
String recovered = ObjectName.unquote(quoted);

System.out.println(raw.equals(recovered)); // true

ObjectName name = new ObjectName(
    "com.example:type=Queue,name=" + quoted
);

System.out.println(name.isPattern()); // false
\`\`\`

\`quote\` performs the necessary escaping for double quotes, backslashes, newlines, asterisks, and question marks. It does not alter the meaning of the original data when calling \`unquote\`. This is the default choice when values come from service names, tenants, files, URLs, external system keys, or user input.

## 6. Wildcards: Literal Value or Pattern?

In \`ObjectName\`, \`*\` matches any sequence of characters and \`?\` matches a single character. Patterns are used for **querying**, typically with \`MBeanServer.queryNames\`. A pattern name is not valid to use as a concrete MBean name during registration.

\`\`\`java
import javax.management.ObjectName;

ObjectName exact =
    new ObjectName("com.example:type=Queue,name=orders");

ObjectName valuePattern =
    new ObjectName("com.example:type=Queue,name=order*");

ObjectName propertyListPattern =
    new ObjectName("com.example:type=Queue,*");

System.out.println(exact.isPattern());                // false
System.out.println(valuePattern.isPattern());         // true
System.out.println(propertyListPattern.isPattern());  // true
\`\`\`

Three pattern types to distinguish:

1. **Domain pattern:** \`com.example.*:type=Cache\` matches qualifying domains.
2. **Property value pattern:** \`com.example:type=Cache,name=cache*\` finds names with a matching value part.
3. **Property list pattern:** \`com.example:type=Cache,*\` allows an additional list of key-properties.

When a concrete name contains \`*\` or \`?\` supplied by user data, use \`ObjectName.quote(rawValue)\` to escape them as literals. If you write \`name=orders*\` directly, the object will be a pattern and may cause \`registerMBean\` to reject it.

\`\`\`java
String rawName = "orders*";
ObjectName safe = new ObjectName(
    "com.example:type=Queue,name=" + ObjectName.quote(rawName)
);

System.out.println(safe.isPattern()); // false
\`\`\`

Do not construct patterns from untrusted data when the goal is to look up exactly one MBean.

## 7. Creating ObjectName with Multi-Argument Constructors

For names with multiple keys, dedicated constructors avoid having to assemble \`key=value\` parts and commas manually:

\`\`\`java
import javax.management.ObjectName;
import java.util.Hashtable;

Hashtable<String, String> properties = new Hashtable<>();
properties.put("type", "Queue");
properties.put("name", "orders");

ObjectName name =
    new ObjectName("com.example", properties);
\`\`\`

However, this constructor **does not automatically quote value data** for you. If \`name\` contains special characters, you should still supply the value as \`ObjectName.quote(rawValue)\`:

\`\`\`java
properties.put("name", ObjectName.quote("orders,urgent"));
ObjectName safelyNamed = new ObjectName("com.example", properties);
\`\`\`

For single-property parameters, you can use the constructor:

\`\`\`java
ObjectName one = new ObjectName(
    "com.example",
    "type",
    "Queue"
);
\`\`\`

For **dynamic** domains or property keys, \`quote\` does not solve domain/key name validity; validate them with a separate rule or prefer fixed, controlled domains and keys.

## 8. Normalizing, Reading, and Comparing Names

Useful APIs:

\`\`\`java
ObjectName objectName =
    new ObjectName("com.example:region=asia,type=Cache,name=Products");

String domain = objectName.getDomain();
String type = objectName.getKeyProperty("type");
String rawList = objectName.getKeyPropertyListString();
String canonical = objectName.getCanonicalName();
boolean pattern = objectName.isPattern();
\`\`\`

The value of \`getKeyPropertyListString()\` is the properties string in its representation order, whereas \`getCanonicalKeyPropertyListString()\` returns the properties sorted in canonical order. When identity matters, avoid relying on the original input order.

**Do not equate domain with hostname:** \`ObjectName\` is only a logical identifier within an \`MBeanServer\`. Different JVMs can register \`com.example:type=Queue,name=orders\` simultaneously without conflict because they belong to different registries.

## 9. Complete Example: Registering an MBean with Names from External Data

Suppose an application has queues named \`priority,eu\` and \`bulk*\`. We want to register MBeans safely with both names without turning the names into patterns.

\`\`\`java
import javax.management.MBeanServer;
import javax.management.ObjectName;
import java.lang.management.ManagementFactory;
import java.util.List;

public class QueueRegistration {
    public interface QueueMetricsMBean {
        int getPending();
    }

    public static final class QueueMetrics implements QueueMetricsMBean {
        private final int pending;
        public QueueMetrics(int pending) { this.pending = pending; }
        public int getPending() { return pending; }
    }

    public static void main(String[] args) throws Exception {
        MBeanServer server = ManagementFactory.getPlatformMBeanServer();

        for (String queueName : List.of("priority,eu", "bulk*")) {
            ObjectName name = new ObjectName(
                "com.example.queues:type=Queue,name=" +
                ObjectName.quote(queueName)
            );

            server.registerMBean(new QueueMetrics(12), name);

            System.out.printf("%s -> %s%n", queueName, name);
            System.out.println("Pattern? " + name.isPattern());
        }
    }
}
\`\`\`

In a long-running application, Spring's \`MBeanExporter\` typically manages registration and unregistration lifecycles; in a plain Java SE example, you must proactively unregister the created names when the module shuts down if the server remains alive. For two queues with the same name, you must design an additional dimension/instance or handle name collisions, because a single server cannot register two MBeans under the same \`ObjectName\`.

## 10. Some Invalid Inputs and How to Fix Them

| Input | Problem | Fix |
| --- | --- | --- |
| \`com.example:type=Queue,name=a,b\` | \`b\` is not a key=value pair | \`name="a,b"\` |
| \`com.example:type=Queue,name=a=b\` | \`=\` character in an unquoted value | \`name="a=b"\` |
| \`com.example:type=Queue,name=a*b\` | Becomes a property-value pattern | \`name="a\*b"\` |
| \`com.example:type=Queue,name=a?b\` | Becomes a property-value pattern | \`name="a\?b"\` |
| \`com.example:type=Queue,name=one,name=two\` | Duplicate property key | Use only one \`name\` key, or add another distinguishing key |
| \`com.example:type=Queue,=abc\` | Empty key | Choose a named key, e.g., \`name=abc\` |
| \`com.example:type=Queue,name="a"b"\` | Unescaped double quote | Use \`ObjectName.quote\` on the raw input |

In the table above, strings with double quotes are in **ObjectName notation**, not Java string literals. If you place them directly in Java source code, additional escaping per Java rules is required.

## 11. Spring Framework: Setting ObjectName for Managed Beans

Spring JMX allows declaring the name directly:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example:type=Queue,name=Orders",
    description = "Operational state of the orders queue"
)
public class OrdersQueueManagement {
    // Appropriate @ManagedAttribute and @ManagedOperation methods.
}
\`\`\`

When the name value comes from dynamic configuration, do not concatenate it directly into a literal \`objectName\` without quoting. You can configure \`MBeanExporter\` with a map from constructed and validated \`ObjectName\` instances, or place naming logic into Spring's \`ObjectNamingStrategy\`. The goal is for management code to take responsibility for converting data into a valid \`ObjectName\`, rather than forcing business classes to understand JMX syntax.

Example of a small reusable factory:

\`\`\`java
import javax.management.MalformedObjectNameException;
import javax.management.ObjectName;

public final class QueueObjectNames {
    private QueueObjectNames() {}

    public static ObjectName forQueue(String queueName)
            throws MalformedObjectNameException {
        if (queueName == null || queueName.isBlank()) {
            throw new IllegalArgumentException("Queue name is required");
        }

        return new ObjectName(
            "com.example:type=Queue,name=" +
            ObjectName.quote(queueName)
        );
    }
}
\`\`\`

This factory keeps the domain and keys stable, quoting only the dynamic data portion. You can add \`instance\`, \`region\`, or \`tenant\` if they are genuinely necessary identity components and are managed consistently.

## 12. Testing Names and Escaping

You do not need to run an \`MBeanServer\` to test every naming case. Use \`ObjectName\` directly:

\`\`\`java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import javax.management.ObjectName;

class ObjectNameEscapingTest {
    @Test
    void quoteRoundTripsSpecialCharacters() throws Exception {
        String raw = "orders,eu=\"priority\"\\tier*?\nnext";
        ObjectName name = new ObjectName(
            "com.example:type=Queue,name=" + ObjectName.quote(raw)
        );

        assertFalse(name.isPattern());
        assertEquals(
            raw,
            ObjectName.unquote(name.getKeyProperty("name"))
        );
    }

    @Test
    void canonicalNameIgnoresPropertyOrder() throws Exception {
        ObjectName a =
            new ObjectName("com.example:type=Queue,name=orders");
        ObjectName b =
            new ObjectName("com.example:name=orders,type=Queue");

        assertEquals(a, b);
        assertEquals(a.getCanonicalName(), b.getCanonicalName());
    }

    @Test
    void unescapedStarMakesPattern() throws Exception {
        ObjectName pattern =
            new ObjectName("com.example:type=Queue,name=orders*");

        assertTrue(pattern.isPropertyValuePattern("name"));
        assertTrue(pattern.isPattern());
    }
}
\`\`\`

For JMX integration, add tests for registering/looking up with the exact \`ObjectName\`, handling \`MalformedObjectNameException\` from configuration, and detecting collisions when two components produce the same identity.

## 13. Practical Guidelines

1. Keep **domains and keys fixed** with clear naming conventions.
2. For all **dynamic values**, use \`ObjectName.quote(raw)\` and only call \`unquote\` when you know the value is in quoted form.
3. Use \`isPattern()\` or \`isPropertyValuePattern(key)\` to detect wildcards when a name must be a concrete identifier.
4. Use \`ObjectName\` or \`getCanonicalName()\` for comparisons; do not assume property pair order.
5. Handle **invalid keys**, **special values**, **patterns**, and **MBean name collisions** separately; they are distinct kinds of errors.
6. Do not put sensitive information into an \`ObjectName\`: MBean names commonly appear in logs, dashboards, and operational tools.

## 14. Key Takeaways

\`ObjectName\` is an identifier with a formal grammar, not an arbitrary label. **Keys** are the names of the identifying dimensions, **values** are the data for those dimensions, and \`quote\` and escaping determine whether special characters are interpreted as literals or syntax. When naming from dynamic data, keep keys stable and use \`ObjectName.quote\`; when querying in bulk, use patterns intentionally. These two principles help prevent subtle issues such as an MBean being treated as a pattern, malformed names, or clients failing to find an MBean under its expected name.
