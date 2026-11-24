# Concrete ObjectNames and Wildcard ObjectName Patterns in JMX

## 1. Goals and Context

In Java Management Extensions (JMX), each MBean is registered in an \`MBeanServer\` using an **\`ObjectName\`**. An ObjectName contains a *domain* and a set of *key property* pairs, for example:

\`\`\`text
com.example.orders:type=Queue,name=Checkout
\`\`\`

When managing an application with many MBeans, you must distinguish between two usages:

- **Concrete ObjectName:** uniquely identifies a single MBean for registration, reading attributes, or invoking operations.
- **ObjectName pattern:** an expression containing wildcards or markers that match a set of key properties, used to query a list of MBeans.

This lesson helps you design stable names, understand pattern matching, and apply them correctly in both plain Java JMX and Spring Framework JMX.

After this lesson, you will be able to:

1. Analyze the domain and key properties of an ObjectName.
2. Create valid concrete ObjectNames using the Java API.
3. Distinguish wildcards in the domain, property values, and the \`,*\` property-list pattern.
4. Use \`MBeanServer.queryNames\` to find MBeans by name and pattern.
5. Explain the matching behavior of common patterns, including easily confused cases.
6. Design maintainable ObjectName conventions and avoid issues with security, name changes, or duplicate registrations.

## 2. ObjectName Structure

General syntax:

\`\`\`text
<domain>:<key1>=<value1>,<key2>=<value2>,...
\`\`\`

Example:

\`\`\`text
com.example.orders:type=Queue,name=Checkout,region=ap-southeast-1
\`\`\`

| Component | Example Value | Role |
|---|---|---|
| Domain | \`com.example.orders\` | Logical grouping of MBeans |
| Key \`type\` | \`Queue\` | Resource classification |
| Key \`name\` | \`Checkout\` | Instance identification |
| Key \`region\` | \`ap-southeast-1\` | Separates instances by region |
| Full ObjectName | Entire string | Unique identifier within an MBeanServer |

**Important:** the list of key properties does not carry ordering significance for identity. Two ObjectNames with the same domain and the same set of key/value pairs are equal even if the order of the property pairs differs.

\`\`\`java
import javax.management.ObjectName;

ObjectName first = new ObjectName(
    "com.example.orders:type=Queue,name=Checkout"
);
ObjectName second = new ObjectName(
    "com.example.orders:name=Checkout,type=Queue"
);

System.out.println(first.equals(second)); // true
\`\`\`

An ObjectName can be created from a string or via constructors accepting a domain along with key/value properties. Use the naming API instead of manually concatenating segments taken from untrusted data.

### 2.1. Character and Quoting Rules

An ObjectName uses special characters as syntax delimiters. If an actual value contains a comma, equals sign, colon, asterisk, question mark, double quote, or newline character, you must understand quoting/escaping rules and validate appropriately. \`ObjectName.quote(...)\` converts a string into a quoted property value according to ObjectName syntax.

\`\`\`java
String displayName = "Orders, Priority";
ObjectName quotedName = new ObjectName(
    "com.example:type=Queue,name=" + ObjectName.quote(displayName)
);
System.out.println(quotedName);
\`\`\`

**Distinction:** quoting to represent characters in a value and wildcard matching are related topics, not identical ones. When creating a concrete identifier containing characters that could carry pattern meaning, always check \`isPattern()\` to confirm the intended purpose of that name. An ObjectName used for \`registerMBean\` must be a concrete name.

## 3. Concrete ObjectName: Identifying Exactly One MBean

Example:

\`\`\`java
ObjectName exact = new ObjectName(
    "training.jmx:type=Cache,name=Products"
);

System.out.println(exact.isPattern()); // false
\`\`\`

A concrete \`ObjectName\` has a specific domain and specific key properties. On a single \`MBeanServer\`, the same ObjectName cannot be used to register two separate MBeans concurrently. Attempting duplicate registration typically throws \`InstanceAlreadyExistsException\`.

\`\`\`java
import javax.management.*;
import java.lang.management.ManagementFactory;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();
ObjectName name = new ObjectName(
    "training.jmx:type=Cache,name=Products"
);

// server.registerMBean(cacheMBean, name);
// A second registration with the same name will be rejected.
\`\`\`

In operations, concrete names are suitable for:

- Reading an attribute: \`connection.getAttribute(exact, "Size")\`.
- Invoking an operation: \`connection.invoke(exact, "clear", new Object[0], new String[0])\`.
- Verifying registration: \`connection.isRegistered(exact)\`.
- Unregistering: \`server.unregisterMBean(exact)\` with appropriate permissions and lifecycle handling.

An ObjectName does not specify a JMX server URL or host address. To identify a remote MBean, a client must know **which MBeanServer to connect to** and **the MBean's ObjectName within that server**.

## 4. ObjectName Patterns and Wildcard Mechanisms

An ObjectName pattern is used for query operations such as \`queryNames\`. The Java API distinguishes:

1. **Domain pattern:** wildcards \`*\` or \`?\` in the domain.
2. **Property value pattern:** wildcards in a *property value* when expressed according to ObjectName pattern rules.
3. **Property list pattern:** \`,*\` at the end of the property list (or \`*\` right after the colon when no properties are specified), allowing additional key properties beyond those specified.

\`*\` matches any sequence of characters, including the empty string; \`?\` matches exactly one character. The \`,*\` at the property-list level has different semantics from \`*\` inside a value.

### 4.1. Domain Pattern

\`\`\`text
training.*:type=Cache,name=Products
training.?:type=Cache,name=Products
\`\`\`

- The first pattern can match \`training.east:type=Cache,name=Products\`.
- The second pattern requires one character after \`training.\`, such as \`training.a:type=Cache,name=Products\`.

If the key properties do not include a property-list wildcard, the pattern still requires an **exact match on the set of key properties**; the domain wildcard only relaxes the domain part.

### 4.2. Property Value Pattern

\`\`\`text
training.jmx:type=Cache,name=Prod*
training.jmx:type=Cache,name=Product?
\`\`\`

- \`name=Prod*\` can match \`Products\` and \`Production\`.
- \`name=Product?\` can match \`Products\` because the last character is \`s\`, but does not match \`Product\` because a character is missing.

When using the Java API, construct the object and check:

\`\`\`java
ObjectName pattern = new ObjectName(
    "training.jmx:type=Cache,name=Prod*"
);

System.out.println(pattern.isPattern());              // true
System.out.println(pattern.isPropertyValuePattern()); // true
\`\`\`

### 4.3. Property List Pattern

This is a very common point of confusion in JMX:

\`\`\`text
training.jmx:type=Cache,*
\`\`\`

The pattern above only requires \`type=Cache\`; additional properties such as \`name\`, \`region\`, and \`tenant\` may also be present.

Meanwhile:

\`\`\`text
training.jmx:type=Cache
\`\`\`

has no \`,*\`, so it only matches ObjectNames that have **solely** the property \`type=Cache\`, and does not match names that also have \`name=Products\`.

The pattern:

\`\`\`text
training.jmx:*
\`\`\`

matches every set of key properties in the \`training.jmx\` domain. The pattern:

\`\`\`text
*:*
\`\`\`

matches every accessible ObjectName registered on the MBeanServer, subject to the client's permissions.

\`*:* \` is a very broad query; on large servers, prefer a specific domain/type to reduce query overhead and returned data.

## 5. Exact Comparison: Which Patterns Match Which Names?

Suppose an MBeanServer has registered:

\`\`\`text
A = shop.orders:type=Queue,name=Checkout
B = shop.orders:type=Queue,name=Checkout,region=vn
C = shop.orders:type=Queue,name=Returns
D = shop.orders:type=Cache,name=Checkout
E = shop.billing:type=Queue,name=Checkout
F = shop.orders:type=Queue
\`\`\`

| ObjectName Used for Query | Matching Results | Explanation |
|---|---|---|
| \`shop.orders:type=Queue,name=Checkout\` | A | Concrete name, exact match on key/value set |
| \`shop.orders:type=Queue,name=Checkout,*\` | A, B | Requires 2 keys, allows extra keys |
| \`shop.orders:type=Queue,*\` | A, B, C, F | Requires type Queue, remaining keys arbitrary |
| \`shop.orders:type=Queue\` | F | No property-list wildcard |
| \`shop.orders:type=Queue,name=Check*\` | A | Name value pattern, but key set must match exactly: B has extra region |
| \`shop.orders:type=Queue,name=Check*,*\` | A, B | Value pattern combined with property-list pattern |
| \`shop.*:type=Queue,name=Checkout\` | A, E | Domain pattern; B excluded due to extra region |
| \`shop.*:type=Queue,name=Checkout,*\` | A, B, E | Domain wildcard and open key list |
| \`shop.orders:*\` | A, B, C, D, F | Any key properties in the exact domain |
| \`*:*\` | A, B, C, D, E, F | Queries the entire MBeanServer |

The table above illustrates **matching by ObjectName**; a \`queryNames\` call can also take a second \`QueryExp\` argument to filter by a conditional expression.

## 6. Java Practice: Registering MBeans and Querying by Pattern

### 6.1. Writing a Simple Standard MBean

File \`QueueStatsMBean.java\`:

\`\`\`java
public interface QueueStatsMBean {
    int getPendingCount();
}
\`\`\`

File \`QueueStats.java\`:

\`\`\`java
public class QueueStats implements QueueStatsMBean {
    private final int pendingCount;

    public QueueStats(int pendingCount) {
        this.pendingCount = pendingCount;
    }

    @Override
    public int getPendingCount() {
        return pendingCount;
    }
}
\`\`\`

File \`ObjectNameDemo.java\`:

\`\`\`java
import java.lang.management.ManagementFactory;
import java.util.Set;
import java.util.TreeSet;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class ObjectNameDemo {
    private static final String DOMAIN = "shop.orders";

    public static void main(String[] args) throws Exception {
        MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();

        ObjectName checkout = new ObjectName(
            DOMAIN + ":type=Queue,name=Checkout");
        ObjectName checkoutVn = new ObjectName(
            DOMAIN + ":type=Queue,name=Checkout,region=vn");
        ObjectName returns = new ObjectName(
            DOMAIN + ":type=Queue,name=Returns");

        server.registerMBean(new QueueStats(5), checkout);
        server.registerMBean(new QueueStats(8), checkoutVn);
        server.registerMBean(new QueueStats(2), returns);

        printMatches(server, DOMAIN + ":type=Queue,name=Checkout");
        printMatches(server, DOMAIN + ":type=Queue,name=Checkout,*");
        printMatches(server, DOMAIN + ":type=Queue,name=Check*");
        printMatches(server, DOMAIN + ":type=Queue,name=Check*,*");
        printMatches(server, DOMAIN + ":type=Queue,*");

        System.out.println("JConsole can inspect this process.");
        Thread.sleep(120_000);
    }

    private static void printMatches(MBeanServer server, String expression)
            throws Exception {
        ObjectName search = new ObjectName(expression);
        Set<ObjectName> found = server.queryNames(search, null);
        System.out.println("\\nPattern: " + search);
        for (String name : new TreeSet<>(
                found.stream()
                     .map(ObjectName::getCanonicalName)
                     .toList())) {
            System.out.println("  " + name);
        }
    }
}
\`\`\`

Run with JDK 21 (or a compatible JDK):

\`\`\`bash
javac QueueStatsMBean.java QueueStats.java ObjectNameDemo.java
java ObjectNameDemo
\`\`\`

Expected results:

- \`name=Checkout\`: one name.
- \`name=Checkout,*\`: two names.
- \`name=Check*\`: one name because \`,*\` is missing.
- \`name=Check*,*\`: two names.
- \`type=Queue,*\`: three names.

Note that \`getCanonicalName()\` may sort key properties into canonical order, even if the name was entered in a different order. Therefore, when comparing, use \`ObjectName.equals\` or the canonical name; do not rely on the original string order.

### 6.2. Why Use \`queryNames\` Instead of Only \`isRegistered\`?

\`\`\`java
server.isRegistered(checkout); // checks a single exact ObjectName
server.queryNames(
    new ObjectName("shop.orders:type=Queue,*"), null
); // searches for multiple MBeans
\`\`\`

\`isRegistered\` is for a concrete name. \`queryNames\` accepts a pattern and returns a \`Set<ObjectName>\`. A concrete name can also be passed to \`queryNames\` to query just that single name. If the goal is to find a set of MBeans, use an explicit pattern.

When you need detailed information directly, iterate over each name in the result and call \`getMBeanInfo\`, \`getAttribute\`, or \`invoke\` depending on your needs and access permissions.

## 7. Inspecting the ObjectName API in Java

Some methods to remember:

\`\`\`java
ObjectName n = new ObjectName(
    "shop.orders:type=Queue,name=Checkout,*"
);

System.out.println(n.getDomain());
// shop.orders

System.out.println(n.getKeyProperty("type"));
// Queue

System.out.println(n.getKeyPropertyList());
// Map containing type=Queue, name=Checkout

System.out.println(n.getCanonicalName());
// normalized name ordered by keys

System.out.println(n.isPattern());
// true

System.out.println(n.isDomainPattern());
// false

System.out.println(n.isPropertyPattern());
// true

System.out.println(n.isPropertyListPattern());
// true

System.out.println(n.isPropertyValuePattern());
// false
\`\`\`

Use \`ObjectName.apply(ObjectName)\` to test matching rules on the client side if needed:

\`\`\`java
ObjectName pattern = new ObjectName(
    "shop.orders:type=Queue,name=Checkout,*"
);
ObjectName candidate = new ObjectName(
    "shop.orders:type=Queue,name=Checkout,region=vn"
);
System.out.println(pattern.apply(candidate)); // true
\`\`\`

**Note:** \`apply\` evaluates name matching; it does not access the server and does not check whether the MBean is actually registered. Actual queries use \`MBeanServer.queryNames\`.

## 8. Wildcards in Domain, Value, and Property-List: Three Different Levels

Read a pattern layer by layer instead of simply seeing \`*\` and concluding "matches everything":

\`\`\`text
shop.*:type=Queue,name=Check*,*
^^^^^^ ^^^^^^^^^^^^^^^^^^^^^^
domain  key-value matching +
pattern property-list matching
\`\`\`

Rules:

1. The domain must match the domain pattern.
2. All key properties specified in the pattern must exist and have matching values.
3. If there is **no** property-list pattern, the candidate must not have extra keys beyond the list in the pattern.
4. If there **is** a property-list pattern, the candidate may have additional keys.
5. If a value contains a wildcard, the wildcard applies only to the value of that specific key.

For example:

\`\`\`text
Pattern:   shop.orders:type=Queue,name=Check*,*
Candidate: shop.orders:type=Queue,name=Checkout,region=vn
\`\`\`

Matches because the domain matches, the type matches, name matches \`Check*\`, and \`,*\` allows the extra \`region\`.

Conversely:

\`\`\`text
Pattern:   shop.orders:type=Queue,name=Check*
Candidate: shop.orders:type=Queue,name=Checkout,region=vn
\`\`\`

Does not match because the pattern requires the exact property set \`{type,name}\`.

## 9. Rules for Naming ObjectNames in Large Applications

### 9.1. Use Domains with Clear Namespaces

Choose stable domains, for example:

\`\`\`text
com.example.shop.orders:type=Queue,name=Checkout
com.example.shop.orders:type=Queue,name=Returns
com.example.shop.billing:type=InvoiceProcessor,name=Primary
\`\`\`

Avoid using a generic domain like \`app\` across multiple applications that may share an MBeanServer if it could lead to name collisions.

### 9.2. Choose Meaningful Key Properties

Common keys are \`type\`, \`name\`, \`component\`, \`instance\`, and \`region\`. They are **application-chosen conventions**, not a list of attributes mandated by JMX.

Standardize naming so queries are consistent:

\`\`\`text
com.example.shop:type=Cache,name=Products
com.example.shop:type=Cache,name=Customers
com.example.shop:type=Queue,name=Checkout
\`\`\`

Query by group:

\`\`\`text
com.example.shop:type=Cache,*
\`\`\`

### 9.3. Avoid Frequently Changing Data in Identifiers

Do not put values such as current request counts, instantaneous timestamps, or \`online/offline\` status into the ObjectName. Those belong in **attributes**; MBean names should remain stable across the management lifecycle.

For example:

\`\`\`text
Avoid:     com.example:type=Queue,name=Checkout,pending=123
Prefer:    com.example:type=Queue,name=Checkout
Attribute: PendingCount = 123
\`\`\`

When MBeans are short-lived, you need an appropriate registration/unregistration and querying strategy. Avoid creating unbounded ObjectNames driven by request input data.

### 9.4. Do Not Put Sensitive Data in Names

ObjectNames may appear in logs, management consoles, or monitoring tools. Avoid user IDs, emails, tokens, secrets, or personal data unless truly necessary. Use safe internal identifiers and controlled attributes when additional state must be represented.

### 9.5. Canonical Name and Uniqueness

If a client receives:

\`\`\`text
shop.orders:name=Checkout,type=Queue
shop.orders:type=Queue,name=Checkout
\`\`\`

the two strings have different key orders but represent the same ObjectName. \`getCanonicalName()\` helps present them consistently; \`ObjectName.equals\` compares them with the right semantics.

## 10. Connection to Spring Framework JMX

Spring Framework provides mechanisms to export Spring beans as MBeans, in which \`MBeanExporter\` and \`@ManagedResource\` can use concrete ObjectNames.

Illustrative example:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.shop:type=Queue,name=Checkout",
    description = "Checkout queue management view"
)
public class CheckoutQueueMonitor {
    private volatile int pendingCount;

    @ManagedAttribute(description = "Current pending jobs")
    public int getPendingCount() {
        return pendingCount;
    }

    public void setPendingCountForDemo(int pendingCount) {
        this.pendingCount = pendingCount;
    }
}
\`\`\`

In an application with appropriate JMX export enabled (such as Spring Framework's \`@EnableMBeanExport\` or an equivalent \`MBeanExporter\` configuration), the bean can be registered under the declared name. **The ObjectName in export metadata must be a concrete name; wildcard patterns are reserved for queries.**

On the client side, you do not need to know whether a bean was exported by Spring or plain Java in order to find it:

\`\`\`java
ObjectName allQueues = new ObjectName(
    "com.example.shop:type=Queue,*"
);
Set<ObjectName> names = connection.queryNames(allQueues, null);
\`\`\`

The same query works for MBeans matching the name structure, regardless of whether registration came from Spring or \`registerMBean\` directly.

### 10.1. ObjectNamingStrategy in Spring

When an application has many beans, \`MBeanExporter\` can use a naming strategy such as \`ObjectNamingStrategy\` to determine the ObjectName from the bean. The goal is to maintain consistent domain/key conventions rather than naming each bean ad hoc. However, a naming strategy does not change \`ObjectName\` semantics: each registered MBean must have a concrete, non-colliding name on the same MBeanServer.

### 10.2. Naming a Spring Bean Is Not Naming an MBean

A bean named \`checkoutQueueMonitor\` in the ApplicationContext does not mean its JMX ObjectName is also \`checkoutQueueMonitor\`. Bean names and ObjectNames belong to two different namespaces. The MBeanExporter/metadata/naming strategy determines the actual mapping. When debugging, inspect the name actually registered on the MBeanServer.

## 11. Diagnosing Common Errors

| Symptom | Common Cause | How to Check |
|---|---|---|
| \`MalformedObjectNameException\` | Malformed name string or improperly quoted characters | Construct \`new ObjectName(...)\` in a small test; inspect domain/key/value |
| \`InstanceAlreadyExistsException\` | Registering the same ObjectName twice | Check \`isRegistered\`, naming strategy, and exporter lifecycle |
| \`queryNames\` returns empty | Mismatched domain/key or overly strict pattern | Compare \`getCanonicalName\`; check for missing \`,*\` |
| Query returns more results than expected | Using \`:*\` or \`,*\` too broadly | Narrow down domain, type, and name |
| Pattern fails to match names with region | Missing property-list wildcard | Compare \`type=Queue,name=X\` with \`type=Queue,name=X,*\` |
| Client queries exact name yet finds no MBean | Connected to wrong MBeanServer/process | Verify JVM, connector, and registered name list |
| Spring bean exists but is not visible via JMX | Not exported or JMX name differs from expected | Inspect MBeanExporter, annotations, and naming strategy |

Do not fix an empty \`queryNames\` result by immediately running \`*:* \` on a large system. Prefer reading actual domains from a narrow list first, then broadening the query intentionally.

## 12. Hands-On Exercises

### Exercise A — Classifying Names

Given the strings:

\`\`\`text
alpha:type=Worker,name=A
alpha:type=Worker,*
alpha:type=Worker,name=A*
alpha:*
*:type=Worker,*
\`\`\`

Construct an \`ObjectName\` for each string and print \`isPattern\`, \`isDomainPattern\`, \`isPropertyValuePattern\`, and \`isPropertyListPattern\`. Explain why the results differ.

### Exercise B — Choosing the Right Pattern

Suppose the server has:

\`\`\`text
training:type=Cache,name=Products
training:type=Cache,name=Products,region=vn
training:type=Cache,name=Customers
training:type=Queue,name=Orders
\`\`\`

Write patterns to:

1. Find only the Products cache with no other properties.
2. Find the Products cache across all regions.
3. Find all Caches.
4. Find every resource type in the training domain.
5. Find all resources whose \`name\` starts with \`Prod\`, even when other keys are present.

Suggested answers:

\`\`\`text
1. training:type=Cache,name=Products
2. training:type=Cache,name=Products,*
3. training:type=Cache,*
4. training:*
5. training:name=Prod*,*
\`\`\`

### Exercise C — Names with Special Characters

Create a name for a queue with the display name \`Urgent, East\`. Use \`ObjectName.quote\`, compare it with passing the unquoted string directly, and explain why the comma is interpreted differently.

### Exercise D — Canonical Comparison

Create two ObjectNames with the same domain and the same \`type/name\` pairs in reversed order. Print \`equals\`, \`toString\`, and \`getCanonicalName\`. Explain in your own words why comparing only the original input strings can cause bugs.

### Exercise E — Spring JMX

In a Spring application with JMX export enabled, create two managed beans with the ObjectNames:

\`\`\`text
com.example.demo:type=Worker,name=Email
com.example.demo:type=Worker,name=Export
\`\`\`

Use JConsole or a client calling \`queryNames("com.example.demo:type=Worker,*")\` and inspect both. Try changing one name to collide and observe the registration error.

## 13. Self-Check Questions

1. Within what scope does an ObjectName identify an MBean?
2. What is the difference between a concrete ObjectName and an ObjectName pattern?
3. How does \`*\` in the value \`name=App*\` differ from \`,*\` at the end of the key properties list?
4. Why does \`shop:type=Queue\` fail to find \`shop:type=Queue,name=Checkout\`?
5. Why can \`shop:type=Queue,*\` find both of those names?
6. When should you use \`isRegistered\` instead of \`queryNames\`?
7. Why must data used in an ObjectName be normalized or quoted?
8. Does \`ObjectName.apply\` confirm that an MBean exists on the server?
9. If a Spring bean is named \`workerService\`, must its JMX ObjectName match this name?
10. What risks arise if you use \`*:* \` as a default monitoring query?

## 14. References

- Java SE 21 — \`ObjectName\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/ObjectName.html
- Java SE 21 — \`MBeanServer\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
- Java SE 21 — \`MBeanServerConnection\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerConnection.html
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html

**Key takeaway:** A concrete ObjectName uniquely identifies and lets you operate on a specific MBean; an ObjectName pattern lets you find a set of MBeans. When writing patterns, always keep domain wildcards, value wildcards, and the property-list wildcard \`,*\` distinct — this is the key to accurate and reliable querying.
