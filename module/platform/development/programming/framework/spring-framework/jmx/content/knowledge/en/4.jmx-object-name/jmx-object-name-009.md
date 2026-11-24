# Validating ObjectNames Using the API Instead of Ad-Hoc String Concatenation

## 1. Objectives

In Java Management Extensions (JMX), \`javax.management.ObjectName\` is the identifier used to register, look up, and manage MBeans in an \`MBeanServer\`. An \`ObjectName\` has its own structure and syntax rules; it is not merely a string containing colons and commas.

When working with Spring Framework JMX, constructing MBean names through arbitrary string concatenation easily causes bugs because:
- Dynamic values may contain commas, equals signs, colons, double quotes, backslashes, or wildcard characters.
- Key property order may differ while still identifying the same MBean.
- A name may be a **pattern** used for querying rather than a concrete registered name.
- A syntactically valid string may not belong to a domain or MBean group permitted by the application.
- A valid name does not prove the MBean is currently registered in the JMX server.

This lesson focuses on using the **Java API**, from \`ObjectName\` to \`MBeanServer\`, to build and validate MBean names in a structured way.

After this lesson, you will be able to:
1. Understand \`domain:key=value,key=value\` syntax and the difference between a concrete name and a pattern.
2. Use constructors, \`ObjectName.quote()\`, \`ObjectName.unquote()\`, and \`MalformedObjectNameException\` appropriately.
3. Validate domains, required keys, values, wildcards, and canonical names via the API.
4. Distinguish between **syntactically valid**, **valid under application policy**, and **currently registered in the MBeanServer**.
5. Apply a validation workflow when Spring exports beans as MBeans.

## 2. Structure of an ObjectName

A typical name has the form:

\`\`\`text
com.example.orders:type=Worker,name=ImportJob
└──── domain ────┘ └──── key properties ────┘
\`\`\`

- **Domain** groups names, e.g., \`com.example.orders\`, \`java.lang\`.
- **Key property** is a \`key=value\` pair, e.g., \`type=Worker\`, \`name=ImportJob\`.
- The combination of domain and key properties identifies a JMX name. \`name\` alone cannot be treated as a global identifier.
- A domain may be empty at the API level, but applications should generally use an explicit domain by convention.
- The characters \`*\` and \`?\` can carry pattern-matching meaning, depending on position and escaping.

Examples of concrete names:

\`\`\`text
com.example.orders:type=Worker,name=ImportJob
java.lang:type=Memory
\`\`\`

Examples of patterns used in queries:

\`\`\`text
com.example.orders:type=Worker,*
com.example.orders:type=Worker,name=*
com.example.*:type=Worker,name=ImportJob
\`\`\`

**Important distinction:** \`ObjectName\` is an already-parsed Java object. Calling \`toString()\` for logging is fine, but comparison or validation logic should use the API's property accessor and comparison methods.

## 3. Three Levels of Validation That Must Not Be Conflated

| Level | Question | API / Measure |
|---|---|---|
| **Syntax** | Is the string a valid ObjectName? | \`new ObjectName(text)\`, catch \`MalformedObjectNameException\` |
| **Application policy** | Are the domain, keys, type, and wildcards within allowed bounds? | \`getDomain()\`, \`getKeyProperty()\`, \`getKeyPropertyList()\`, \`isPattern()\` |
| **Actual registration** | Is the MBean present in this MBeanServer? | \`MBeanServer.isRegistered(name)\` |

A string like \`java.lang:type=Memory\` may be syntactically valid yet invalid for an API that only permits custom MBeans in the \`com.example.orders\` domain. Conversely, \`com.example.orders:type=Worker,name=ImportJob\` may be syntactically valid and policy-compliant yet not currently registered.

A proper workflow evaluates each level as needed, never substituting the result of one level for another.

## 4. Building Names from Structured Data

### 4.1. Avoid Injecting Dynamic Values into Raw Syntax

Suppose a worker name comes from configuration or operational data:

\`\`\`java
String workerName = "Import,Asia=East";
String raw = "com.example.orders:type=Worker,name=" + workerName;
\`\`\`

\`raw\` becomes:

\`\`\`text
com.example.orders:type=Worker,name=Import,Asia=East
\`\`\`

Here the comma and equals sign inside \`workerName\` are interpreted as syntax declaring a **new key property** (\`Asia=East\`). If the name contains other characters, the parser may throw an error. String checks like \`contains("type=Worker")\` or splitting by commas do not fix the root cause.

### 4.2. Using Constructors and ObjectName.quote

When values are dynamic, fix the domain and keys in a naming factory and escape the **value** with \`ObjectName.quote()\`:

\`\`\`java
import java.util.Hashtable;
import javax.management.MalformedObjectNameException;
import javax.management.ObjectName;

public final class WorkerObjectNames {
    private static final String DOMAIN = "com.example.orders";

    private WorkerObjectNames() {}

    public static ObjectName forWorker(String workerName)
            throws MalformedObjectNameException {
        if (workerName == null || workerName.isBlank()) {
            throw new IllegalArgumentException("workerName must not be blank");
        }

        Hashtable<String, String> keys = new Hashtable<>();
        keys.put("type", "Worker");
        keys.put("name", ObjectName.quote(workerName));

        return new ObjectName(DOMAIN, keys);
    }
}
\`\`\`

Usage:

\`\`\`java
ObjectName objectName =
        WorkerObjectNames.forWorker("Import,Asia=East");

System.out.println(objectName.getDomain());
System.out.println(objectName.getKeyProperty("type"));
System.out.println(objectName.getCanonicalName());
\`\`\`

\`ObjectName.quote(value)\` adds double quotes and escapes characters that have special meaning in a **value** so the parser does not treat them as unintended structural elements. It also escapes \`*\` and \`?\` so they are interpreted as literal data characters rather than property-value wildcards.

Understand that the \`Hashtable\` constructor separates keys and values cleanly, **but you should not assume the constructor automatically escapes arbitrary value strings**. Therefore, in the example above, \`workerName\` is quoted intentionally.

You can use the three-argument constructor when there is only one key:

\`\`\`java
ObjectName name = new ObjectName(
        "com.example.orders",
        "name",
        ObjectName.quote("Import,Asia=East")
);
\`\`\`

If the domain or key names also come from an untrusted source, \`quote()\` on the property value is not enough to make them safe; domains and keys must be **validated/constrained separately**. In real applications, domains and keys are typically fixed, allowing only controlled value parts to vary.

### 4.3. Why Not Every String Concatenation Is Wrong

The goal is not an absolute ban on string concatenation. The following can still be valid when the domain and keys are fixed and the dynamic value is quoted:

\`\`\`java
ObjectName name = new ObjectName(
        "com.example.orders:type=Worker,name="
                + ObjectName.quote(workerName)
);
\`\`\`

However, structured constructors and a centralized name-building method make the domain, keys, dynamic value handling, and application policy clear to readers. Avoid duplicating name-formatting snippets across many places.

## 5. Parsing Names with the ObjectName API

When receiving a full name string from configuration, a CLI, or a management request, use JMX's parser:

\`\`\`java
import javax.management.MalformedObjectNameException;
import javax.management.ObjectName;

public static ObjectName parse(String input)
        throws MalformedObjectNameException {
    if (input == null || input.isBlank()) {
        throw new IllegalArgumentException("ObjectName is required");
    }
    return new ObjectName(input);
}
\`\`\`

Invalid strings—such as malformed key property syntax or improperly used special characters—result in \`MalformedObjectNameException\`. This is the official parsing mechanism and is far more reliable than custom regexes attempting to mirror the entire JMX grammar.

Error-handling example at an API boundary:

\`\`\`java
try {
    ObjectName objectName = parse(userInput);
    // Continue validating domain, keys, and pattern.
} catch (MalformedObjectNameException
         | IllegalArgumentException ex) {
    // Return an application-appropriate input error; do not register or query the MBean.
}
\`\`\`

**Note:** The constructor also accepts valid **ObjectName patterns**. Successful parsing does not mean the name is permitted for registering or accessing a single concrete MBean.

## 6. Blocking Unwanted Wildcards

JMX provides dedicated inspection methods:

- \`isPattern()\`: is the name a pattern in any component?
- \`isDomainPattern()\`: does the domain contain a pattern?
- \`isPropertyPattern()\`: does the key properties list or value contain a pattern?
- \`isPropertyListPattern()\`: is there a pattern extending the key properties list, e.g., \`type=Worker,*\`?
- \`isPropertyValuePattern()\`: does any property value carry a wildcard?
- \`isPropertyValuePattern("name")\`: does the \`name\` property value specifically have a pattern?

Example:

\`\`\`java
ObjectName query =
        new ObjectName("com.example.orders:type=Worker,name=*");

System.out.println(query.isPattern());                  // true
System.out.println(query.isPropertyValuePattern());     // true
System.out.println(query.isDomainPattern());            // false
\`\`\`

Meanwhile:

\`\`\`java
ObjectName exact = WorkerObjectNames.forWorker("Import*");
System.out.println(exact.isPattern()); // false
\`\`\`

In the second case, the \`*\` is a character in the worker name, already escaped by \`ObjectName.quote()\` to preserve its literal meaning.

**Design rule:** If an operation must identify exactly one MBean (such as \`getAttribute\`, \`invoke\`, \`unregisterMBean\`, or registering a concrete name), the input should be a **concrete ObjectName**, and \`isPattern() == true\` should be rejected. Patterns belong to intentional search operations such as \`queryNames()\`.

Do not use tricks like \`input.contains("*")\` to detect patterns. An escaped \`*\` may be literal data. Ask \`ObjectName\` itself.

## 7. Validating Domains and Key Properties Against Policy

A management API that only permits Worker MBeans in the \`com.example.orders\` domain can validate like this:

\`\`\`java
import java.util.Map;
import java.util.Set;
import javax.management.ObjectName;

public final class WorkerNamePolicy {
    private static final String DOMAIN = "com.example.orders";
    private static final Set<String> REQUIRED_KEYS =
            Set.of("type", "name");

    private WorkerNamePolicy() {}

    public static boolean isAllowed(ObjectName name) {
        if (name == null || name.isPattern()) {
            return false;
        }
        if (!DOMAIN.equals(name.getDomain())) {
            return false;
        }

        Map<String, String> keys = name.getKeyPropertyList();

        if (!REQUIRED_KEYS.equals(keys.keySet())) {
            return false;
        }
        if (!"Worker".equals(name.getKeyProperty("type"))) {
            return false;
        }

        String worker = name.getKeyProperty("name");
        if (worker == null) {
            return false;
        }

        // Under this policy, name must be a quoted value.
        if (worker.length() < 2
                || worker.charAt(0) != '"'
                || worker.charAt(worker.length() - 1) != '"') {
            return false;
        }

        try {
            String decoded = ObjectName.unquote(worker);
            return !decoded.isBlank() && decoded.length() <= 128;
        } catch (IllegalArgumentException ex) {
            return false;
        }
    }
}
\`\`\`

This example chooses a policy where **the \`name\` value is always quoted**, because the factory in Section 4 always creates names that way. If an application already has valid ObjectNames with unquoted values, this policy will intentionally reject them; adjust the convention to fit your real system.

Here:

- \`getDomain()\` checks the domain with exact equality, rather than an overly broad \`startsWith()\`.
- \`getKeyPropertyList().keySet()\` requires exact equality with the two keys, rather than silently accepting extra keys outside the contract.
- \`getKeyProperty("type")\` verifies the object category.
- \`getKeyProperty("name")\` retrieves the value formatted in ObjectName syntax; \`ObjectName.unquote()\` is used only when the value has a quoted representation.
- \`isPattern()\` blocks wildcards from entering contexts that require a concrete name.

This is **an example of one specific policy**, not a universal rule for all ObjectNames. Another system might allow extra keys such as \`instance\`, \`tenant\`, or \`node\`, and might accept unquoted names as well.

### Notes on Data and Authorization

Validating \`ObjectName\` structure does not replace authorization checks. If a caller is only permitted to manage a specific tenant or worker group, check **ownership and invocation permissions**, not merely that the name falls in an allowed domain.

Additionally, the \`name\` length limit is illustrative only. Pick a policy suited to real data to prevent abnormal inputs from wasting resources or cluttering logs.

## 8. Comparing Properly: equals and Canonical Name

Key properties can be written in different orders:

\`\`\`java
ObjectName a = new ObjectName(
        "com.example.orders:type=Worker,name=ImportJob");

ObjectName b = new ObjectName(
        "com.example.orders:name=ImportJob,type=Worker");

System.out.println(a.equals(b)); // true
System.out.println(a.getCanonicalName()
        .equals(b.getCanonicalName())); // true
\`\`\`

Do not treat \`a.toString().equals(b.toString())\` as the source of truth, because the representation may reflect original key order. \`getCanonicalName()\` provides a normalized form for logs, cache keys, or matching when contracts require strings, while \`ObjectName.equals()\` is the natural choice when comparing two \`ObjectName\` objects.

Some useful APIs:

| API | Purpose |
|---|---|
| \`getDomain()\` | Retrieve the domain |
| \`getKeyProperty("type")\` | Retrieve a specific key's value |
| \`getKeyPropertyList()\` | Retrieve parsed keys/values |
| \`getKeyPropertyListString()\` | String representation of the key properties part |
| \`getCanonicalKeyPropertyListString()\` | Normalized-order string representation of key properties |
| \`getCanonicalName()\` | Full name in canonical form |
| \`equals(other)\` | Compare identities per ObjectName semantics |
| \`isPattern()\` | Check for wildcards/patterns |
| \`apply(other)\` | Test whether an ObjectName pattern matches a given name |

When matching multiple MBeans in a query, construct an explicit pattern and use \`queryNames()\` or \`apply()\`. When identifying a single MBean precisely, construct a concrete ObjectName and use \`equals()\`.

## 9. Checking Whether an MBean Is Registered

After parsing and checking policy, use \`MBeanServer\` to verify existence:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();

ObjectName name = WorkerObjectNames.forWorker("ImportJob");

if (WorkerNamePolicy.isAllowed(name)
        && server.isRegistered(name)) {
    System.out.println("MBean is registered");
} else {
    System.out.println("MBean does not exist or name is not allowed");
}
\`\`\`

\`isRegistered(name)\` checks **the specified MBean server**. If the application uses another MBeanServer, a remote JMX connector, or an MBean registered in a different JVM, you must check the corresponding server/connection.

Additional notes:
- \`isRegistered()\` does not eliminate race checks before operating; state can change between the check and \`getAttribute()\`/\`invoke()\`.
- If the MBean is removed after the check, the subsequent operation can still throw \`InstanceNotFoundException\`.
- If an operation can mutate state, ensure proper authentication, authorization, and auditing.
- An existing name does not prove the MBean has the attribute or operation the caller wants. Inspect metadata via \`getMBeanInfo()\` or handle exceptions on access.

Pattern example to find all workers:

\`\`\`java
ObjectName pattern = new ObjectName(
        "com.example.orders:type=Worker,*");

for (ObjectName candidate : server.queryNames(pattern, null)) {
    System.out.println(candidate.getCanonicalName());
}
\`\`\`

Here \`queryNames\` fits because the goal is to find **multiple** MBeans. If you want only names satisfying the exact policy, filter further with the policy above; the pattern \`type=Worker,*\` can match MBeans carrying keys other than \`name\`.

## 10. Applying This to Spring Framework JMX

Spring Framework provides mechanisms to export Spring-managed beans as JMX MBeans, such as \`MBeanExporter\`, the \`@ManagedResource\` annotation, and MBean naming rules.

Example of an MBean assigned a static ObjectName:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.orders:type=Worker,name=ImportJob"
)
public class ImportWorkerMonitor {
    @ManagedAttribute
    public String getStatus() {
        return "RUNNING";
    }
}
\`\`\`

The name declared in the annotation is static. If the name needs dynamic values (tenant, instance, or worker name), do not stuff unvalidated configuration strings directly into the JMX representation. Construct the name via an \`ObjectName\` factory and then use a registration mechanism, naming strategy, or \`MBeanExporter\` suited to your application configuration.

Example of preparing a validated name mapping:

\`\`\`java
import java.util.Map;
import javax.management.ObjectName;
import org.springframework.jmx.export.MBeanExporter;

public static MBeanExporter exporterFor(
        Object monitorBean,
        String workerName
) throws Exception {
    ObjectName objectName =
            WorkerObjectNames.forWorker(workerName);

    MBeanExporter exporter = new MBeanExporter();
    exporter.setBeans(Map.of(objectName, monitorBean));
    return exporter;
}
\`\`\`

This illustrates programmatic export. In real Spring applications, \`MBeanExporter\` is usually declared as a Spring bean connected to the right \`MBeanServer\`, avoiding multiple exporters registering the same ObjectName. Lifecycle, duplicate-name behavior, and unregistration are configured consistently with the application context.

**Important:** The Spring bean name (\`importWorkerMonitor\`) and the JMX ObjectName (\`com.example.orders:type=Worker,name=ImportJob\`) are two identifiers belonging to two different systems. Do not verify an ObjectName by looking inside the Spring \`ApplicationContext\`; use the JMX API.

## 11. A Small Centralized Utility Class

In a real codebase, centralize name creation, parsing, and validation in a dedicated class so different parts of the app do not invent conflicting rules:

\`\`\`java
import java.util.Hashtable;
import java.util.Set;
import javax.management.MalformedObjectNameException;
import javax.management.ObjectName;

public final class JmxWorkerNames {
    private static final String DOMAIN = "com.example.orders";
    private static final Set<String> KEYS = Set.of("type", "name");

    private JmxWorkerNames() {}

    public static ObjectName create(String workerName)
            throws MalformedObjectNameException {
        if (workerName == null
                || workerName.isBlank()
                || workerName.length() > 128) {
            throw new IllegalArgumentException("Invalid worker name");
        }

        Hashtable<String, String> keyProperties = new Hashtable<>();
        keyProperties.put("type", "Worker");
        keyProperties.put("name", ObjectName.quote(workerName));
        return new ObjectName(DOMAIN, keyProperties);
    }

    public static ObjectName parseAndValidate(String input)
            throws MalformedObjectNameException {
        if (input == null || input.isBlank()) {
            throw new IllegalArgumentException("ObjectName required");
        }

        ObjectName name = new ObjectName(input);

        if (name.isPattern()
                || !DOMAIN.equals(name.getDomain())
                || !KEYS.equals(name.getKeyPropertyList().keySet())
                || !"Worker".equals(name.getKeyProperty("type"))) {
            throw new IllegalArgumentException(
                    "ObjectName outside Worker policy");
        }

        String encoded = name.getKeyProperty("name");
        if (encoded == null
                || encoded.length() < 2
                || encoded.charAt(0) != '"'
                || encoded.charAt(encoded.length() - 1) != '"') {
            throw new IllegalArgumentException(
                    "Worker name must be quoted");
        }

        String decoded = ObjectName.unquote(encoded);
        if (decoded.isBlank() || decoded.length() > 128) {
            throw new IllegalArgumentException("Invalid worker name");
        }

        return name;
    }
}
\`\`\`

An application can use it as:

\`\`\`java
ObjectName created = JmxWorkerNames.create("Import,Asia=East");
ObjectName restored = JmxWorkerNames.parseAndValidate(
        created.toString()
);

System.out.println(created.equals(restored)); // true
\`\`\`

This utility chooses **one concrete convention**: only the \`com.example.orders\` domain, strictly the two keys \`type\` and \`name\`, type \`Worker\`, no wildcards, and \`name\` always quoted. When you need to support legacy names, multiple MBean types, or multiple domains, extend the policy intentionally; do not drop validation altogether.

### Manually Testing Several Input Scenarios

| Input | Expected Result |
|---|---|
| \`com.example.orders:type=Worker,name="ImportJob"\` | Valid syntax; passes the policy above |
| \`com.example.orders:name="ImportJob",type=Worker\` | Passes policy; key order does not matter |
| \`com.example.orders:type=Worker,name=ImportJob\` | Valid syntax, but rejected by the example policy because \`name\` is unquoted |
| \`com.example.orders:type=Worker,name=*\` | Is a pattern; rejected for concrete-name operations |
| \`java.lang:type=Memory\` | Syntactically valid; fails domain/type policy check |
| \`com.example.orders:type=Worker,name="Import,Asia=East"\` | Dynamic value with delimiters represented validly |
| \`com.example.orders:type=Worker,name="Import\*"\` with literal \`*\` escaped by \`ObjectName.quote()\` | Concrete name; \`*\` is treated as data |

The table above illustrates **the example's policy**, not mandatory quoting rules for all JMX ObjectNames.

## 12. Common Mistakes and Better Alternatives

**Mistake 1 — Concatenating unescaped values manually.**

\`\`\`java
String text = domain + ":type=Worker,name=" + workerName;
\`\`\`

Fix the domain/keys, use \`ObjectName.quote(workerName)\`, and construct the \`ObjectName\` with an appropriate constructor.

**Mistake 2 — Validating structure with regex or splitting on commas.**

\`\`\`java
String[] parts = text.split(",");
\`\`\`

Commas can appear inside quoted values. Use \`new ObjectName(text)\` and \`getKeyPropertyList()\`.

**Mistake 3 — Comparing strings to determine name equality.**

\`\`\`java
first.toString().equals(second.toString());
\`\`\`

Use \`first.equals(second)\`; use \`getCanonicalName()\` when a normalized string representation is truly needed.

**Mistake 4 — Assuming successful parsing implies permission to operate.**

A valid pattern can be broader than the scope a user is allowed to access. Check domain, keys, values, \`isPattern()\`, and actual authorization.

**Mistake 5 — Searching for \`*\` manually to conclude a name is a pattern.**

An escaped wildcard may be a literal character in a property. Use \`isPattern()\` and the dedicated inspection APIs.

**Mistake 6 — Treating a valid ObjectName as proof that the MBean exists.**

Only \`MBeanServer.isRegistered()\` or an actual JMX operation on the right server confirms registration state at that moment.

**Mistake 7 — Validating only the name while forgetting security.**

An ObjectName is an identifier, not proof of authorization. For \`invoke\` or \`setAttribute\`, always enforce authentication/authorization and review operation impact.

## 13. Self-Check Exercises

**Question 1:** A worker is named \`East,Backup=1\`. Why is concatenating it directly after \`name=\` error-prone?  
**Suggested answer:** Commas and equals signs carry syntactic meaning in key properties. Use \`ObjectName.quote()\` for dynamic values.

**Question 2:** Two strings share the same domain and key/value pairs, but with reversed key order. Do they identify the same MBean?  
**Suggested answer:** Yes, they can. Parse them into \`ObjectName\` instances and compare with \`equals()\` or check their canonical names.

**Question 3:** \`new ObjectName(text)\` throws no exception. Can \`text\` immediately be used to unregister an MBean?  
**Suggested answer:** Not yet. You must verify it is a concrete name, belongs to an allowed domain/type, and that the caller is authorized to perform the operation.

**Question 4:** Which API finds all MBeans with \`type=Worker\` in the application's domain?  
**Suggested answer:** Create an intentional \`ObjectName\` pattern and call \`MBeanServer.queryNames(pattern, null)\`; results can be further filtered by application policy.

**Question 5:** An ObjectName passes policy, yet \`server.isRegistered(name)\` returns \`false\`. What can you conclude?  
**Suggested answer:** The name conforms to conventions, but is not registered on the inspected MBeanServer at the time of the call; check the target server, lifecycle, and export configuration.

## 14. Key Takeaways

- Use the \`ObjectName\` API to **parse, construct, compare, and inspect components**; avoid mimicking syntax via ad-hoc string slicing/concatenation.
- Use \`ObjectName.quote()\` for **dynamic property values**; it does not replace domain and key validation.
- \`MalformedObjectNameException\` signals syntax errors; \`isPattern()\` indicates wildcards; application policy decides which names are accepted.
- \`equals()\` and \`getCanonicalName()\` properly handle key-property semantics independent of input order.
- \`MBeanServer.isRegistered()\` checks registration on **one specific MBeanServer** and does not guarantee existence during a subsequent operation.
- With Spring JMX, validate ObjectNames at export and management boundaries, keeping responsibilities clear among Spring beans, MBeans, and authorized callers.

### References

- Java SE API — \`javax.management.ObjectName\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/ObjectName.html
- Java SE API — \`javax.management.MBeanServer\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework Reference — Exporting Beans: https://docs.spring.io/spring-framework/reference/integration/jmx/exporting.html
- Oracle JMX Tutorial — Using ObjectNames: https://docs.oracle.com/javase/tutorial/jmx/mbeans/objectname.html
