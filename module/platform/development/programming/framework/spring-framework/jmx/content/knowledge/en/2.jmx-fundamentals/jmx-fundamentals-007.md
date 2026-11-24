# DynamicMBean and Runtime-Generated Interface Descriptions

## 1. Learning Objectives

JMX (Java Management Extensions) uses MBeans to expose the state and management operations of a Java application. With a **Standard MBean**, Java infers the management interface from an interface following naming conventions. With a **DynamicMBean**, the object itself supplies metadata and handles attribute reads, attribute writes, and operation invocations directly. As a result, the management interface can be built from configuration or component characteristics at runtime.

After completing this lesson, you will be able to:

- Explain why DynamicMBean is suitable when the list of attributes or operations is not fixed at compile time.
- Understand the six methods of \`javax.management.DynamicMBean\` and how they work together.
- Build a DynamicMBean with \`MBeanInfo\`, \`MBeanAttributeInfo\`, \`MBeanOperationInfo\`, and \`MBeanParameterInfo\`.
- Register a DynamicMBean in \`MBeanServer\` and observe it from JConsole or a Java JMX client.
- Control errors, write permissions, data types, concurrency, and metadata stability.
- Distinguish core JMX capabilities from how Spring Framework exports MBeans.

## 2. Mental Model: Metadata Is the Management Contract

A JMX client may not know the concrete Java class of an MBean beforehand. It asks the MBeanServer: "What attributes does this object have, what data types are they, are they readable/writable, and which operations can be invoked?" The MBeanServer retrieves this information from \`getMBeanInfo()\`; the client uses it to render UI/controls, then calls the corresponding access methods.

\`\`\`text
             Client: JConsole / JMX client
                         |
                 getMBeanInfo()
                         |
                     MBeanServer
                         |
                 DynamicMBean
             /            |            \
 getAttribute(s)     setAttribute(s)   invoke(...)
             \            |            /
                  Business state
\`\`\`

Core point: **metadata describes capabilities; the read/write/invoke methods execute those capabilities**. If metadata declares an attribute writable yet \`setAttribute\` always rejects it, clients encounter an inconsistent contract. If metadata declares type \`java.lang.Integer\` yet \`getAttribute\` returns a \`String\`, clients may fail or misinterpret data.

A "dynamic" DynamicMBean does not mean JMX automatically discovers every method on the object. The DynamicMBean author actively decides what to expose, maps names to data, and returns the metadata.

## 3. The Six Methods of DynamicMBean

\`\`\`java
public interface DynamicMBean {
    Object getAttribute(String attribute)
        throws AttributeNotFoundException, MBeanException, ReflectionException;

    void setAttribute(Attribute attribute)
        throws AttributeNotFoundException, InvalidAttributeValueException,
               MBeanException, ReflectionException;

    AttributeList getAttributes(String[] attributes);

    AttributeList setAttributes(AttributeList attributes);

    Object invoke(String actionName, Object[] params, String[] signature)
        throws MBeanException, ReflectionException;

    MBeanInfo getMBeanInfo();
}
\`\`\`

| Method | Role | Notes |
|---|---|---|
| \`getMBeanInfo()\` | Returns MBean metadata | Attributes, operations, constructors, notifications, className, description |
| \`getAttribute(name)\` | Reads one attribute | Must clearly report when the attribute does not exist or is unreadable |
| \`setAttribute(attribute)\` | Writes one attribute | Validate name, write permission, type, and value domain |
| \`getAttributes(names)\` | Reads multiple attributes | Returns \`AttributeList\`; failing attributes may be skipped |
| \`setAttributes(list)\` | Writes multiple attributes | Returns successfully written attributes; not atomic by default |
| \`invoke(name, params, signature)\` | Invokes an operation | Must validate name, arguments, signature, and invocation permissions |

\`MBeanInfo\` is not a snapshot of attribute values. It is an **interface description**; values are fetched via \`getAttribute\` at read time.

## 4. How Is Metadata Represented?

Key metadata classes live in \`javax.management\`:

- \`MBeanInfo\`: overall information, including class name, description, arrays of attributes, constructors, operations, notifications, and an optional descriptor.
- \`MBeanAttributeInfo\`: name, Java type, description, readability/writability, isGetter flag.
- \`MBeanOperationInfo\`: operation name, description, parameter list, return type, and impact.
- \`MBeanParameterInfo\`: parameter name, type, and description.
- \`MBeanNotificationInfo\`: notification types the MBean may emit, if any.
- \`Descriptor\`: additional metadata per the JMX contract, if needed by a tool or framework.

Example:

\`\`\`java
new MBeanAttributeInfo(
    "Enabled",                // name queried by clients
    Boolean.class.getName(),  // exposed attribute type
    "Whether processing is enabled",
    true,                     // readable
    true,                     // writable
    false                     // isGetter
);
\`\`\`

Type names in metadata must reflect the runtime types returned or accepted. \`int.class.getName()\` yields \`"int"\`, whereas \`Integer.class.getName()\` is \`"java.lang.Integer"\`. Choose a representation consistent with boxed values passed through the JMX API.

Operation description:

\`\`\`java
new MBeanOperationInfo(
    "reset",
    "Reset the completed count",
    new MBeanParameterInfo[0],
    Void.TYPE.getName(),
    MBeanOperationInfo.ACTION
);
\`\`\`

Common impact values: \`INFO\` (read-only query), \`ACTION\` (state-changing), \`ACTION_INFO\` (both), \`UNKNOWN\`. This is informational for tools/clients; it **does not enforce authorization by itself**.

## 5. Complete Example: DynamicMBean for a Task Counter

The following example creates an MBean with three attributes: \`Name\` (read-only), \`Enabled\` (read/write), \`Completed\` (read-only); and a \`reset\` operation that sets the completed task count back to 0.

File \`TaskCounterDynamic.java\`:

\`\`\`java
import javax.management.*;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;

public final class TaskCounterDynamic implements DynamicMBean {
    private final String name;
    private final AtomicInteger completed = new AtomicInteger();
    private volatile boolean enabled = true;
    private final MBeanInfo metadata;

    public TaskCounterDynamic(String name) {
        this.name = Objects.requireNonNull(name, "name");

        MBeanAttributeInfo[] attributes = {
            new MBeanAttributeInfo(
                "Name", String.class.getName(),
                "Logical counter name", true, false, false),
            new MBeanAttributeInfo(
                "Enabled", Boolean.class.getName(),
                "Whether counting is enabled", true, true, false),
            new MBeanAttributeInfo(
                "Completed", Integer.class.getName(),
                "Completed task count", true, false, false)
        };

        MBeanOperationInfo[] operations = {
            new MBeanOperationInfo(
                "reset", "Reset the completed count",
                new MBeanParameterInfo[0],
                Void.TYPE.getName(),
                MBeanOperationInfo.ACTION)
        };

        this.metadata = new MBeanInfo(
            getClass().getName(),
            "Dynamic task counter used for JMX training",
            attributes,
            null,
            operations,
            null
        );
    }

    public void taskCompleted() {
        if (enabled) {
            completed.incrementAndGet();
        }
    }

    @Override
    public Object getAttribute(String attribute)
            throws AttributeNotFoundException {
        if (attribute == null) {
            throw new AttributeNotFoundException("Attribute name is null");
        }
        switch (attribute) {
            case "Name":
                return name;
            case "Enabled":
                return enabled;
            case "Completed":
                return completed.get();
            default:
                throw new AttributeNotFoundException(attribute);
        }
    }

    @Override
    public void setAttribute(Attribute attribute)
            throws AttributeNotFoundException,
                   InvalidAttributeValueException {
        if (attribute == null) {
            throw new InvalidAttributeValueException(
                "Attribute must not be null");
        }
        String key = attribute.getName();
        if (!"Enabled".equals(key)) {
            throw new AttributeNotFoundException(
                "Unknown or read-only attribute: " + key);
        }
        if (!(attribute.getValue() instanceof Boolean value)) {
            throw new InvalidAttributeValueException(
                "Enabled expects java.lang.Boolean");
        }
        enabled = value;
    }

    @Override
    public AttributeList getAttributes(String[] attributes) {
        AttributeList values = new AttributeList();
        if (attributes == null) {
            return values;
        }
        for (String key : attributes) {
            try {
                values.add(new Attribute(key, getAttribute(key)));
            } catch (AttributeNotFoundException ignored) {
                // JMX bulk reads return only successful entries.
            }
        }
        return values;
    }

    @Override
    public AttributeList setAttributes(AttributeList attributes) {
        AttributeList changed = new AttributeList();
        if (attributes == null) {
            return changed;
        }
        for (Object candidate : attributes) {
            if (!(candidate instanceof Attribute attribute)) {
                continue;
            }
            try {
                setAttribute(attribute);
                changed.add(new Attribute(
                    attribute.getName(),
                    getAttribute(attribute.getName())));
            } catch (AttributeNotFoundException |
                     InvalidAttributeValueException ignored) {
                // JMX bulk writes return only successful entries.
            }
        }
        return changed;
    }

    @Override
    public Object invoke(String actionName,
                         Object[] params,
                         String[] signature)
            throws ReflectionException {
        boolean noParams = params == null || params.length == 0;
        boolean noSignature =
            signature == null || signature.length == 0;
        if ("reset".equals(actionName) && noParams && noSignature) {
            completed.set(0);
            return null;
        }
        throw new ReflectionException(
            new NoSuchMethodException(
                String.valueOf(actionName)),
            "Unknown operation or invalid signature");
    }

    @Override
    public MBeanInfo getMBeanInfo() {
        return metadata;
    }
}
\`\`\`

**Why is the example intentionally simple?**

- \`metadata\` is built once in the constructor: the interface is constructed at runtime yet remains stable over the object's lifecycle.
- \`AtomicInteger\` allows thread-safe counter updates/reads across threads.
- \`volatile boolean\` makes \`Enabled\` state updates visible to other threads.
- \`setAttribute\` checks for \`Boolean\` properly instead of arbitrarily parsing strings.
- \`invoke\` rejects invalid names or signatures.
- Bulk methods only report successful entries; production code should log/emit telemetry or report errors per an appropriate policy for easier diagnostics.

Note: checking \`enabled\` and incrementing \`completed\` do not form an atomic transaction across both variables. If business logic requires guaranteeing no increments after a specific state transition point, stronger synchronization or a more consistent state structure is needed.

## 6. Registering in MBeanServer and Running a Test

File \`Main.java\`:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public final class Main {
    public static void main(String[] args) throws Exception {
        MBeanServer server = ManagementFactory.getPlatformMBeanServer();

        TaskCounterDynamic counter =
            new TaskCounterDynamic("batch-worker");
        ObjectName objectName = new ObjectName(
            "training.dynamic:type=TaskCounter,name=Batch");

        server.registerMBean(counter, objectName);

        for (int i = 0; i < 3; i++) {
            counter.taskCompleted();
        }

        System.out.println("Registered: " + objectName);
        System.out.println("PID: " + ProcessHandle.current().pid());
        Thread.sleep(300_000);
    }
}
\`\`\`

With JDK 21, place both files in the same directory and run:

\`\`\`bash
javac TaskCounterDynamic.java Main.java
java Main
\`\`\`

In another terminal:

\`\`\`bash
jconsole
\`\`\`

Select the running Java process, open the **MBeans** tab, and locate the \`training.dynamic\` domain. Verify:

1. Reading \`Name\` shows \`batch-worker\`.
2. Reading \`Completed\` shows \`3\`.
3. Changing \`Enabled\` from \`true\` to \`false\`, then reading it back.
4. Invoking \`reset\` and confirming \`Completed = 0\`.
5. Inspecting MBean info: three attributes, one operation with descriptions from \`MBeanInfo\`.

When running the example above, local JMX relies on the platform \`MBeanServer\`. The example does not create a remote JMX/RMI endpoint and does not open any firewall ports.

## 7. Programmatic Access Using a JMX Client

Besides JConsole, Java clients can use \`MBeanServerConnection\` to read metadata, attributes, and invoke operations; within the same JVM, \`MBeanServer\` implements this interface.

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.*;

public class Inspect {
    public static void inspect(ObjectName name) throws Exception {
        MBeanServerConnection connection =
            ManagementFactory.getPlatformMBeanServer();

        MBeanInfo info = connection.getMBeanInfo(name);

        for (MBeanAttributeInfo attr : info.getAttributes()) {
            System.out.printf("%s: %s; read=%s; write=%s%n",
                attr.getName(), attr.getType(),
                attr.isReadable(), attr.isWritable());
        }

        Object before = connection.getAttribute(name, "Completed");
        System.out.println("Before reset: " + before);

        connection.invoke(name, "reset",
            new Object[0], new String[0]);

        System.out.println("After reset: " +
            connection.getAttribute(name, "Completed"));
    }
}
\`\`\`

The \`inspect\` method assumes the MBean name is registered in the **same JVM**. If it resides in another JVM, you must obtain \`MBeanServerConnection\` from a valid \`JMXConnector\`. These are two separate steps: exporting the MBean to the server and establishing the client channel to the server.

A generic management tool typically operates in this sequence:

\`\`\`text
queryNames(pattern) → getMBeanInfo(name)
                   → render attribute / operation controls
                   → getAttribute / setAttribute / invoke
\`\`\`

Returned data can be Java primitive wrappers, Strings, simple types/enums, or JMX Open Types. If non-Java clients are anticipated, consider serialization and type compatibility; do not assume an arbitrary POJO will display properly on every client.

## 8. When Does Metadata Actually Change at Runtime?

In the previous example, metadata was **created in the constructor** and kept unchanged. That is already a DynamicMBean because the class itself implements the JMX contract, even though the interface does not change after registration.

An advanced scenario: an application loads a list of metrics from configuration, for example:

\`\`\`text
metric CPU_Load   → readable Double
metric Queue_Size → readable Integer
metric Enabled    → readable/writable Boolean
operation reload  → no arguments
\`\`\`

When the application reloads configuration, it can build a new snapshot for both the **attribute list** and **how values are read**. The goal is that clients never view version A's metadata while querying values against version B's registry.

Suggested design:

\`\`\`java
record AttributeSpec(
    String type,
    boolean readable,
    boolean writable,
    String description
) {}

record ModelSnapshot(
    java.util.Map<String, AttributeSpec> attributes,
    MBeanInfo info
) {}

private volatile ModelSnapshot currentModel;
\`\`\`

Reload procedure:

1. Read and validate all new definitions into a temporary structure.
2. Construct the corresponding \`MBeanInfo\` from the validated data.
3. Publish an immutable snapshot via a single reference assignment.
4. For each read/write request, read the snapshot reference once and process against that snapshot.
5. Clearly define behavior if an attribute is removed between when the client reads metadata and calls \`getAttribute\`.

**Limitation to understand:** two independent JMX calls do not form a transaction with each other. Even with atomic snapshot updates, a client may receive old \`MBeanInfo\` and then encounter \`AttributeNotFoundException\` because the schema changed. Good operational design uses versioning, change notifications when appropriate, or retains old names during a transition period.

JMX provides notification mechanisms to inform clients when MBeans are registered/unregistered (via \`MBeanServerDelegate\`), and a DynamicMBean can emit its own notifications if it implements the corresponding interfaces. Do not assume that merely changing \`getMBeanInfo()\` will automatically cause every client to refresh its UI immediately.

## 9. DynamicMBean vs. Standard MBean, MXBean, and Spring JMX

| Type | Who Describes the Interface? | When to Use? | Limitations |
|---|---|---|---|
| Standard MBean | Interface by naming convention | Stable interface, minimal boilerplate | Requires a static Java contract |
| MXBean | MXBean interface and Open Types mapping | Interoperable management data exchange | Has data mapping rules |
| DynamicMBean | \`getMBeanInfo()\` and dispatch methods | Configurable schemas, plugins, or runtime discovery | More metadata/error-handling code |
| Spring-exported bean | Spring \`MBeanExporter\` and assembler | Exposing Spring beans with centralized configuration | Depends on mapping/export mechanisms |

A DynamicMBean can still be an object managed by the Spring container. However, do not conflate Spring's export model with JMX's: Spring manages lifecycle/registration; \`DynamicMBean\` provides the JMX request-handling contract. Check how the specific exporter and assembler handle objects that already implement \`DynamicMBean\`; avoid assuming automatic combination of all annotations and dynamic metadata.

**Selection rule:** if the interface is known at compile time, start with Standard MBean or MXBean. Choose DynamicMBean only when metadata flexibility brings real value, such as plugins with varying structures, runtime rules, or configuration-driven module management.

## 10. Common Errors and How to Diagnose Them

### 10.1. \`NotCompliantMBeanException\` at Registration

Verify the class properly implements \`DynamicMBean\` and valid methods. For Standard MBeans, check interface naming conventions; do not mix Standard MBean naming rules into DynamicMBean definitions.

### 10.2. \`AttributeNotFoundException\`

The name in \`MBeanAttributeInfo\` must exactly match the name accepted by \`getAttribute\` and \`setAttribute\`. JMX is case-sensitive. It is also possible the client cached metadata prior to a schema reload.

### 10.3. \`InvalidAttributeValueException\`

Verify exact type and value domain. Some consoles send boxed types (\`Boolean\`, \`Integer\`), not strings. Do not arbitrarily convert \`"false"\` into \`Boolean\` if metadata declared a specific type.

### 10.4. \`ReflectionException\` on Invoke

Confirm action name, argument count, \`signature[]\`, and parameter type class names. With overloads, the operation name alone is insufficient to resolve the method.

### 10.5. Metadata and Runtime Mismatch

For example, metadata says an attribute is writable yet \`setAttribute\` always rejects it; an operation declares returning \`int\` yet execution returns \`String\`. Generate metadata and handlers from the same specification set, and test with an actual client.

### 10.6. Race Conditions During Reload

Do not mutate a global \`HashMap\` directly while JMX threads are reading. Prefer immutable snapshots and safe publication; keep exception contracts clear when clients use an old schema.

### 10.7. Remote Access Fails

If an MBean appears in local JConsole but cannot be accessed remotely, the issue may lie in connector/RMI, hostname, firewall, TLS, or authentication. **DynamicMBean does not configure remote connections by itself**.

## 11. Security and Operability

JMX is a management channel capable of reading system state or triggering data-mutating operations. Consider:

- Expose only appropriate data; do not place tokens, passwords, or user data in attributes or ObjectNames.
- Distinguish read-only operations from state-changing operations, but do not treat \`INFO\`/\`ACTION\` flags as an access-control mechanism.
- Use authentication, encryption, and network restrictions when remote access is enabled; do not expose JMX endpoints directly to the Internet.
- Limit resource-intensive queries; avoid long-running operations or locking the entire application.
- Write thread-safe handlers; avoid holding long locks inside \`getAttribute\`.
- Monitor dispatch errors, schema changes, denied access, and management operation counts, if permitted by operational policy.
- Plan ObjectNames to be stable, unique, and easy to query.
- Do not promise all-or-nothing semantics for \`setAttributes\`; document partial success and provide business operations when transactional behavior is required.

## 12. Applied Exercises

### Exercise A — Metadata from Configuration

Given configuration lines \`name,type,readable,writable\`, construct \`MBeanAttributeInfo[]\` in the constructor. Accept only types from an allowlist such as \`String\`, \`Integer\`, \`Boolean\`; reject invalid types before publishing the MBean.

**Expected result:** adding a valid metric to configuration and restarting makes JConsole show the new attribute without manually editing \`getMBeanInfo()\` code.

### Exercise B — Dispatch from a Registry

Replace the \`switch\` in \`getAttribute\` with a map of type-checked handlers. Ensure arbitrary Java methods are not exposed via reflection.

**Expected result:** nonexistent names return \`AttributeNotFoundException\`, writable=false is blocked, and returned data matches the declared type.

### Exercise C — Schema Reload

Use an immutable snapshot to swap the entire metadata in a single publication step. Write two threads: thread A continuously calls \`getMBeanInfo\`/reads attributes, while thread B reloads the attribute list.

**Expected result:** no \`ConcurrentModificationException\`; when the client uses an old schema, exceptions are handled cleanly and the system continues running.

### Exercise D — UI-Independent Verification

Write an automated JMX client:
1. Find the ObjectName using \`queryNames\`.
2. Fetch \`MBeanInfo\` and print name/type/readable/writable.
3. Attempt to read readable attributes.
4. Test the \`reset\` operation.
5. Verify nonexistent attributes and wrong-type inputs report appropriate errors.

## 13. Self-Check Questions

1. What reason makes DynamicMBean more useful than Standard MBean in a plugin system?
2. How does \`getMBeanInfo\` differ functionally from \`getAttribute\`?
3. Why must writable metadata match \`setAttribute\`?
4. Is \`getAttributes\` required to return an entry for every requested name?
5. Why does an operation need both \`actionName\` and \`signature\`?
6. Does \`MBeanOperationInfo.ACTION\` automatically block unauthorized clients?
7. Why can changing metadata at runtime cause errors for clients that cache schemas?
8. How can you prevent definition data from being read in a half-updated state during reload?
9. Which part does Spring \`MBeanExporter\` solve compared to \`DynamicMBean\`?
10. If local JConsole sees the MBean but a remote client does not, which layers should be checked?

## 14. Further Reading

- Java SE 21 — \`DynamicMBean\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/DynamicMBean.html
- Java SE 21 — \`MBeanInfo\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanInfo.html
- Java SE 21 — \`MBeanAttributeInfo\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanAttributeInfo.html
- Java SE 21 — \`MBeanOperationInfo\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanOperationInfo.html
- Java SE 21 — \`MBeanServer\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html

**Takeaway:** DynamicMBean gives the developer direct control over the management contract. What matters is keeping metadata, request handling, and application state consistent; only after that should runtime-changing schemas and remote JMX be considered.
