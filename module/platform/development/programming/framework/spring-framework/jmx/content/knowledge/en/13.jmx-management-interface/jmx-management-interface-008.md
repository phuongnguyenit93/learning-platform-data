# Inspecting actual MBeanInfo after export in Spring JMX

## 1. Learning objectives

After this lesson, you will be able to:

- Explain why you must inspect **MBeanInfo after the MBean is actually registered** rather than relying solely on interfaces, annotations, or \`MBeanExporter\` configuration.
- Use \`MBeanServer.getMBeanInfo(ObjectName)\` and \`MBeanServer.isRegistered(ObjectName)\` to verify the management surface.
- Read **attributes**, **operations**, **constructors**, **notifications**, **descriptors**, and data type details published by JMX.
- Distinguish metadata of **Standard MBean**, **MXBean**, **Model MBean**, and other implementations.
- Identify discrepancies between Spring JMX configuration and the contract actually seen by clients such as JConsole.
- Write automated checks for operation names and signatures, attribute read/write flags, absence of internal APIs, and metadata descriptions.
- Diagnose common exporter issues: wrong \`ObjectName\`, duplicate registration, wrong assembler, another exporter, wrong \`MBeanServer\`, or lifecycle issues.
- Design a safe JMX surface inspection workflow without accidentally invoking operations with side effects.

## 2. Why must runtime MBeanInfo be inspected?

In Spring Framework, a bean can be exported via JMX using \`MBeanExporter\`, \`@ManagedResource\`, \`@ManagedAttribute\`, \`@ManagedOperation\` annotations, or a management interface. However, source code only describes **intent**; actual metadata also depends on:

1. Which exporter is configured and initialized.
2. Which beans are included in the export list.
3. Which \`ObjectName\` is produced by the naming strategy.
4. Which assembler is used to select attributes/operations.
5. Whether the MBean is a Standard, MXBean, or Model MBean.
6. Whether registration succeeded or collided on name.
7. Which MBeanServer JConsole or clients connect to.
8. Whether the application has reached registration time or already unregistered the MBean.
9. Whether Spring/JDK versions and custom implementations alter metadata.

**Runtime MBeanInfo** is the contract that a JMX client can actually discover at query time. Inspecting it directly detects over-exposed interfaces, missing information, or deviations from intended configuration.

\`\`\`text
Java interface / annotations / configuration
                |
                v
   MBeanExporter + MBeanInfoAssembler
                |
                v
        MBeanServer.registerMBean
                |
                v
       Actual MBean's MBeanInfo
                |
         +------+------+
         |             |
         v             v
     JConsole     Java JMX client
         |             |
         +------> attributes / operations
                  signatures / descriptions
\`\`\`

If a Spring bean has valid annotations but the exporter did not register it, \`getMBeanInfo\` will not find the MBean. If the exporter uses an assembler that does not read annotations, intended operations may not appear. If the exporter discovers too many methods, internal methods may be exposed. Runtime verification catches those cases.

## 3. JMX APIs to know

| API | Meaning |
| --- | --- |
| \`MBeanServer.isRegistered(name)\` | Checks whether \`ObjectName\` is currently in the registry. |
| \`MBeanServer.getMBeanInfo(name)\` | Retrieves metadata of the registered MBean. |
| \`MBeanServer.queryNames(pattern, null)\` | Finds matching \`ObjectName\`s. |
| \`MBeanInfo.getClassName()\` | Class name describing the MBean. |
| \`MBeanInfo.getDescription()\` | General description of the MBean. |
| \`MBeanInfo.getAttributes()\` | List of attribute metadata. |
| \`MBeanInfo.getOperations()\` | List of operation metadata. |
| \`MBeanInfo.getConstructors()\` | Published constructor metadata. |
| \`MBeanInfo.getNotifications()\` | Published notification types. |
| \`MBeanInfo.getDescriptor()\` | Overall descriptor of the MBean. |
| \`MBeanAttributeInfo.getType()\` | JMX type of the attribute. |
| \`MBeanAttributeInfo.isReadable()\` | Whether the attribute is readable via JMX. |
| \`MBeanAttributeInfo.isWritable()\` | Whether the attribute is writable via JMX. |
| \`MBeanAttributeInfo.isIs()\` | Boolean getter of form \`isX()\` per JMX metadata. |
| \`MBeanOperationInfo.getSignature()\` | List of operation parameter types/details. |
| \`MBeanOperationInfo.getReturnType()\` | Operation return type. |
| \`MBeanOperationInfo.getImpact()\` | Impact level INFO/ACTION/ACTION_INFO/UNKNOWN. |
| \`MBeanFeatureInfo.getDescriptor()\` | Additional descriptor of a feature. |

**Not every piece of metadata is displayed completely by every GUI tool.** For accurate verification, use the JMX API to read full metadata.

## 4. Distinguishing “registered” from “exported as intended”

Successful registration is not enough to prove the contract is right.

Expected example:

\`\`\`text
com.example.jobs:type=ImportJob,name=Daily

Attributes:
  Running          boolean  read-only
  CompletedCount   long     read-only

Operations:
  requestPause()   void
\`\`\`

Possible discrepancies:

- \`isRegistered(name)=true\` yet \`CompletedCount\` is writable.
- \`requestPause\` is missing from the operation list.
- \`stopProcessNow\` appears even though it was not intended to be published.
- Descriptions are not attached to metadata due to the wrong assembler.
- Operation parameters have wrong names/types or overloads.
- Actual \`ObjectName\` differs from the name used by the operations team.
- An older MBean with the same name remains due to registration policy; clients see the old object's metadata instead of the new bean.

Therefore, verify at least: **registration → metadata identity → attribute/operation list → read/write flags → signatures → disallowed capabilities**.

## 5. Minimal Standard MBean example

Create the management interface:

\`\`\`java
package example.jmx;

public interface ImportJobMonitorMBean {
    boolean isRunning();
    long getCompletedCount();
    void requestPause();
}
\`\`\`

Implementation class:

\`\`\`java
package example.jmx;

public final class ImportJobMonitor implements ImportJobMonitorMBean {

    private volatile boolean running = true;
    private volatile long completedCount = 125L;

    @Override
    public boolean isRunning() {
        return running;
    }

    @Override
    public long getCompletedCount() {
        return completedCount;
    }

    @Override
    public void requestPause() {
        running = false;
    }

    // Public in Java but not in the MBean interface.
    public String getInternalCredentialAlias() {
        return "internal-alias";
    }
}
\`\`\`

Because this is a Standard MBean using the \`ImportJobMonitorMBean\` interface, methods in the interface are published by JMX as attributes and operations per convention.

- \`isRunning()\` → attribute \`Running\`, \`boolean\`, readable.
- \`getCompletedCount()\` → attribute \`CompletedCount\`, \`long\`, readable.
- \`requestPause()\` → zero-argument operation returning \`void\`.
- \`getInternalCredentialAlias()\` is **not** part of the management interface, so it is not exported through this Standard MBean contract.

**Note:** if a different reflective assembler is used on this object, the result can differ. The example here assumes the Standard MBean mechanism.

## 6. Registering the MBean and inspecting directly

Complete Java SE example to read metadata:

\`\`\`java
package example.jmx;

import java.lang.management.ManagementFactory;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanParameterInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public final class InspectMBeanInfoDemo {

    public static void main(String[] args) throws Exception {
        MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();

        ObjectName name = new ObjectName(
            "com.example.jobs:type=ImportJob,name=Daily"
        );

        server.registerMBean(new ImportJobMonitor(), name);
        try {
            System.out.println(
                "Registered: " + server.isRegistered(name)
            );

            MBeanInfo info = server.getMBeanInfo(name);
            System.out.println("Class: " + info.getClassName());
            System.out.println("Description: " + info.getDescription());

            for (MBeanAttributeInfo attribute
                    : info.getAttributes()) {
                System.out.printf(
                    "ATTRIBUTE name=%s type=%s read=%s write=%s is=%s%n",
                    attribute.getName(),
                    attribute.getType(),
                    attribute.isReadable(),
                    attribute.isWritable(),
                    attribute.isIs()
                );
            }

            for (MBeanOperationInfo operation
                    : info.getOperations()) {
                System.out.printf(
                    "OPERATION name=%s return=%s impact=%d%n",
                    operation.getName(),
                    operation.getReturnType(),
                    operation.getImpact()
                );

                for (MBeanParameterInfo parameter
                        : operation.getSignature()) {
                    System.out.printf(
                        "  PARAM name=%s type=%s desc=%s%n",
                        parameter.getName(),
                        parameter.getType(),
                        parameter.getDescription()
                    );
                }
            }
        } finally {
            server.unregisterMBean(name);
        }
    }
}
\`\`\`

Expected contract result: read-only \`Running\` and \`CompletedCount\`, \`requestPause\` present, and no \`InternalCredentialAlias\` attribute. Primitive types are described by names such as \`boolean\`, \`long\`, and \`void\`.

The presentation order of attributes/operations is not a guaranteed contract across implementations. In automated checks, compare sets of names and signatures rather than relying on arbitrary ordering.

## 7. Reading metadata of a Spring-exported MBean

With Spring, a bean can be annotated:

\`\`\`java
package example.springjmx;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.jobs:type=ImportJob,name=Daily",
    description = "Daily import job management"
)
public class ImportJobManagement {

    @ManagedAttribute(description = "Whether import is running")
    public boolean isRunning() {
        return true;
    }

    @ManagedAttribute(description = "Processed item count")
    public long getCompletedCount() {
        return 125L;
    }

    @ManagedOperation(
        description = "Request a graceful pause of the import job"
    )
    public void requestPause() {
        // Request the worker to pause.
    }

    public String readInternalSecret() {
        return "must-not-export";
    }
}
\`\`\`

When \`MBeanExporter\` uses \`MetadataMBeanInfoAssembler\` with \`AnnotationJmxAttributeSource\`, the annotations are used to generate management metadata for the bean. After export, clients read \`MBeanInfo\` to confirm:

- The MBean is registered at the expected \`ObjectName\`.
- \`Running\` and \`CompletedCount\` have appropriate descriptions.
- \`requestPause\` appears with the right return type and signature.
- \`readInternalSecret\` does not become an unintended operation/attribute.

### 7.1. Explicit Spring exporter configuration

\`\`\`java
package example.springjmx;

import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.annotation.AnnotationJmxAttributeSource;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;
import org.springframework.jmx.export.naming.MetadataNamingStrategy;

@Configuration
public class JmxExportConfig {

    @Bean
    public MBeanExporter mBeanExporter(ImportJobManagement admin) {
        AnnotationJmxAttributeSource source =
            new AnnotationJmxAttributeSource();

        MetadataMBeanInfoAssembler assembler =
            new MetadataMBeanInfoAssembler();
        assembler.setAttributeSource(source);

        MetadataNamingStrategy naming =
            new MetadataNamingStrategy();
        naming.setAttributeSource(source);

        MBeanExporter exporter = new MBeanExporter();
        exporter.setAssembler(assembler);
        exporter.setNamingStrategy(naming);
        exporter.setBeans(Map.of("importJobManagement", admin));

        return exporter;
    }
}
\`\`\`

In a Spring Boot application, JMX auto-configuration may already be active. If creating a standalone exporter, avoid exporting the same \`ObjectName\` twice and clearly identify the target MBeanServer. The example above is a standalone illustration explaining the mechanism.

### 7.2. Make sure to check the right MBeanServer

Not every application exports to the default platform MBeanServer. Spring can be configured to use a custom \`MBeanServer\` or another factory/provider.

If \`ManagementFactory.getPlatformMBeanServer().isRegistered(name)\` returns \`false\`, do not jump to the conclusion that the bean was not exported. Identify the exact \`MBeanServer\` that the exporter is configured to use before inspecting.

## 8. Writing a reusable MBeanInfo inspection helper

A utility can print the metadata of any MBean:

\`\`\`java
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanConstructorInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanNotificationInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanParameterInfo;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;

public final class JmxMetadataPrinter {

    public static void print(
            MBeanServerConnection connection,
            ObjectName name) throws Exception {

        MBeanInfo info = connection.getMBeanInfo(name);

        System.out.println("MBean: " + name.getCanonicalName());
        System.out.println("Class: " + info.getClassName());
        System.out.println("Description: " + info.getDescription());

        for (MBeanAttributeInfo attribute
                : info.getAttributes()) {
            System.out.println(
                "Attribute " + attribute.getName()
                + ", type=" + attribute.getType()
                + ", read=" + attribute.isReadable()
                + ", write=" + attribute.isWritable()
                + ", description=" + attribute.getDescription()
            );
        }

        for (MBeanOperationInfo operation
                : info.getOperations()) {
            System.out.println(
                "Operation " + operation.getName()
                + ", return=" + operation.getReturnType()
                + ", impact=" + operation.getImpact()
                + ", description=" + operation.getDescription()
            );

            for (MBeanParameterInfo parameter
                    : operation.getSignature()) {
                System.out.println(
                    "  Parameter " + parameter.getName()
                    + ", type=" + parameter.getType()
                    + ", desc=" + parameter.getDescription()
                );
            }
        }

        for (MBeanConstructorInfo ctor
                : info.getConstructors()) {
            System.out.println(
                "Constructor: " + ctor.getName()
            );
        }

        for (MBeanNotificationInfo notification
                : info.getNotifications()) {
            System.out.println(
                "Notification: " + notification.getName()
            );
        }
    }

    private JmxMetadataPrinter() { }
}
\`\`\`

Because the helper takes \`MBeanServerConnection\`, it works with either a local \`MBeanServer\` or a remote JMX connector, provided the connection has permission to read metadata. However, reading metadata remotely also requires proper network/JMX security configuration.

This is an inspection operation that does not call \`invoke\` or \`setAttribute\`, so it carries less risk of mutating state. Still, metadata can reveal class names, paths, domains, and internal topology details; restrict where the output is printed.

## 9. Viewing MBeanInfo with JConsole

A visual way:

1. Start the Spring application with JMX export enabled.
2. Open JConsole and connect to the right JVM, locally or remotely.
3. Select the **MBeans** tab.
4. Locate the domain and \`ObjectName\`, e.g., \`com.example.jobs:type=ImportJob,name=Daily\`.
5. Open **Attributes** to see the names, types, and values displayed by the tool.
6. Open **Operations** to see which operations can be invoked.
7. View descriptions and metadata supported by the UI.

JConsole is a convenient tool, yet it may not display every \`Descriptor\`, \`impact\`, or parameter metadata item. When precise inspection is required, use \`MBeanServer.getMBeanInfo\` or \`MBeanServerConnection.getMBeanInfo\`.

**Do not click an operation just to “check if it exists”**. Invoking an operation through JConsole can mutate application state. If you only need to inspect the API surface, read metadata.

## 10. Attributes: checking name, type, and read/write flags

A JMX attribute has:

- \`name\`: management name, e.g., \`Running\`.
- \`type\`: Java/JMX type, e.g., \`boolean\`, \`java.lang.String\`.
- \`readable\`: whether clients can call \`getAttribute\`.
- \`writable\`: whether clients can call \`setAttribute\`.
- \`isIs\`: \`isX\`-style getter for Boolean/boolean per JMX semantics.
- \`description\`: business explanatory details.
- \`descriptor\`: supplementary metadata if supplied by the MBean.

Expected example:

\`\`\`text
Running:
  type = boolean
  readable = true
  writable = false

CompletedCount:
  type = long
  readable = true
  writable = false
\`\`\`

If a metric attribute appears with \`writable=true\`, inspect the setter or the exporter's introspection strategy. A metric such as \`CompletedCount\` should usually not be arbitrarily modifiable by JMX clients.

### 10.1. Automated attribute assertion

\`\`\`java
import java.util.Arrays;
import javax.management.MBeanAttributeInfo;

MBeanAttributeInfo running = Arrays.stream(info.getAttributes())
    .filter(a -> a.getName().equals("Running"))
    .findFirst()
    .orElseThrow(() ->
        new AssertionError("Missing Running attribute")
    );

if (!running.isReadable() || running.isWritable()) {
    throw new AssertionError(
        "Running must be readable and not writable"
    );
}
\`\`\`

Do not check only one field. If a secret getter is accidentally over-exported, validate against a list of allowed attributes or forbidden attributes.

## 11. Operations: names and signatures matter

Operation metadata includes name, return type, and ordered parameter list.

Example:

\`\`\`java
public int retryFailedItems(int limit, boolean dryRun)
\`\`\`

Signature might be:

\`\`\`text
operation.name       = retryFailedItems
operation.returnType = int
operation.signature:
  0: int
  1: boolean
\`\`\`

Client invocation:

\`\`\`java
connection.invoke(
    objectName,
    "retryFailedItems",
    new Object[] { 10, true },
    new String[] { "int", "boolean" }
);
\`\`\`

However, test invocation should only happen in test/lab environments when an operation has side effects, not as a default metadata inspection step.

### 11.1. Verifying an exact operation

\`\`\`java
import java.util.Arrays;
import javax.management.MBeanOperationInfo;

boolean hasPause = Arrays.stream(info.getOperations())
    .anyMatch(o ->
        o.getName().equals("requestPause")
        && o.getSignature().length == 0
        && o.getReturnType().equals("void")
    );

if (!hasPause) {
    throw new AssertionError(
        "Expected requestPause() operation is missing"
    );
}
\`\`\`

When overloaded operations exist, name alone is insufficient; compare signatures. Changing primitive \`int\` to reference \`java.lang.Integer\` can alter the JMX signature even if some application code treats them similarly.

### 11.2. Checking for disallowed operations

\`\`\`java
boolean exposesInternalMethod =
    Arrays.stream(info.getOperations())
        .anyMatch(o ->
            o.getName().equals("stopAllServicesInternal")
        );

if (exposesInternalMethod) {
    throw new AssertionError(
        "Internal operation must not be exported"
    );
}
\`\`\`

With \`DynamicMBean\`, also verify that the \`invoke\` implementation actually rejects disallowed names. Hiding a method from metadata does not guarantee dynamic code will not handle a manual call by name.

## 12. Checking descriptions and parameter metadata

If a Spring annotation specifies:

\`\`\`java
@ManagedOperation(
    description = "Request a graceful pause of the import job"
)
public void requestPause() { }
\`\`\`

then in an appropriate annotation-based assembler configuration, \`MBeanOperationInfo.getDescription()\` should reflect the corresponding meaning.

With parameters:

\`\`\`java
@ManagedOperationParameters({
    @ManagedOperationParameter(
        name = "limit",
        description = "Maximum retry items (1..100)"
    )
})
\`\`\`

\`MBeanParameterInfo\` can supply name, type, and description. When management tools show names like \`p1\` or empty descriptions, check the assembler/annotations rather than assuming the Java compiler did not retain parameter names.

Description is neither validation nor authorization; the application must still reject out-of-range inputs and protect side-effecting operations.

## 13. Descriptors: additional data to inspect at the right level

Both an \`MBeanInfo\` and each \`MBeanFeatureInfo\` can carry a \`Descriptor\`:

\`\`\`java
import javax.management.Descriptor;

Descriptor beanDescriptor = info.getDescriptor();

for (String field : beanDescriptor.getFieldNames()) {
    System.out.println(
        field + "=" + beanDescriptor.getFieldValue(field)
    );
}
\`\`\`

Similarly, read the descriptor of each attribute or operation:

\`\`\`java
for (MBeanAttributeInfo attribute : info.getAttributes()) {
    System.out.printf(
        "%s descriptor=%s%n",
        attribute.getName(),
        attribute.getDescriptor()
    );
}

for (MBeanOperationInfo operation : info.getOperations()) {
    System.out.printf(
        "%s descriptor=%s%n",
        operation.getName(),
        operation.getDescriptor()
    );
}
\`\`\`

Some Model MBean descriptors contain fields such as \`currencyTimeLimit\`, \`persistPolicy\`, \`persistPeriod\`, \`persistName\`, or \`persistLocation\`. They only produce actual runtime behavior when a corresponding implementation uses that metadata. Do not treat these fields as Spring Cache TTL or database persistence.

**Note:** descriptors can also hold custom metadata or internal details. Do not dump all descriptors into public production logs without reviewing security policies.

## 14. ModelMBeanInfo and MXBean metadata

### 14.1. Model MBean

A Spring exporter with a metadata assembler can build metadata structures according to the Model MBean model. You can check:

\`\`\`java
import javax.management.modelmbean.ModelMBeanInfo;

if (info instanceof ModelMBeanInfo) {
    System.out.println("Model MBean metadata available");
}
\`\`\`

A \`ModelMBeanInfo\` provides additional APIs to retrieve descriptors by feature type. Use them when you want to inspect Model MBean-specific fields.

### 14.2. MXBean

An MXBean maps certain Java types to standard JMX open data, which may use \`CompositeData\` or \`TabularData\`. When inspecting an MXBean:

- Read the attribute type published by JMX rather than assuming it matches the business class.
- Inspect \`Descriptor\` or \`OpenType\` when needed to understand the data structure.
- With \`CompositeData\`, clients do not necessarily need the application's implementation classes.
- Do not infer that an MBean with \`CompositeData\` has only safe or read-only operations.

### 14.3. MBeanInfo differs from runtime values

\`MBeanInfo\` describes the **schema**, not all current attribute values. Fetching values requires \`getAttribute\` or \`getAttributes\`, though calling getters can incur cost or side effects if the implementation is unsafe. During contract verification, metadata is usually the safer starting point.

## 15. Distinguishing MBeanServer and MBeanServerConnection

\`MBeanServer\` is the registry/server inside the JVM or management environment. \`MBeanServerConnection\` is the client interface usable locally or remotely.

\`\`\`java
MBeanServer local = ManagementFactory.getPlatformMBeanServer();
MBeanInfo localInfo = local.getMBeanInfo(name);
\`\`\`

For remote access:

\`\`\`java
import javax.management.MBeanServerConnection;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

JMXServiceURL url = new JMXServiceURL(
    "service:jmx:rmi:///jndi/rmi://localhost:9010/jmxrmi"
);

try (JMXConnector connector =
         JMXConnectorFactory.connect(url)) {
    MBeanServerConnection remote =
        connector.getMBeanServerConnection();

    MBeanInfo remoteInfo = remote.getMBeanInfo(name);
    System.out.println(remoteInfo.getDescription());
}
\`\`\`

The remote example assumes a local lab endpoint exists and connection permissions allow it. In production, configure TLS, authentication, and appropriate network restrictions. Do not open remote JMX solely to run contract checks if local verification via MBeanServer is sufficient.

## 16. Handling MBean not found

When \`getMBeanInfo(name)\` throws \`InstanceNotFoundException\`, follow these steps:

1. **Check the exact ObjectName:** domain, key properties, and quoted values.
2. **Check the right server:** is the exporter using the platform MBeanServer or a custom server?
3. **Check the exporter:** is the bean in \`setBeans\`, auto-detected, or registered by the right component?
4. **Check the assembler:** are annotations and interfaces being interpreted?
5. **Check lifecycle:** has the context finished initializing, or was the MBean already unregistered?
6. **Check name collisions:** was the MBean skipped or replaced by the registration policy?
7. **Check security policy:** does the remote connection have sufficient permission to view metadata?

You can search names within a domain scope:

\`\`\`java
import javax.management.ObjectName;

for (ObjectName found :
        server.queryNames(
            new ObjectName("com.example.jobs:*"),
            null)) {
    System.out.println(found.getCanonicalName());
}
\`\`\`

Do not scan the entire MBeanServer on a production system and write all metadata to public logs without a specific operational reason.

## 17. Common mismatches between annotations/interfaces and metadata

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Class has \`@ManagedResource\` but no MBean | No exporter or bean was not selected. | Check Spring JMX config and \`isRegistered\`. |
| Empty description | Assembler does not read annotations or metadata was not transferred. | Check \`MetadataMBeanInfoAssembler\`. |
| Missing operation | Not annotated or interface/assembler selects differently. | Compare methods with runtime operation list. |
| Extra public methods exported | Autodetect/reflective assembler is too broad. | Use an allowlist interface or annotation-based metadata. |
| Attribute unintentionally writable | Setter was exported or introspection strategy. | Check \`isWritable\`, restrict setters. |
| Wrong ObjectName | Different naming strategy, bean key, or domain. | Query \`queryNames\` in the relevant domain. |
| Stale MBean remains | Ignore registration policy or improper cleanup. | Check ownership, lifecycle, and policy. |
| Client does not understand MXBean type | Different data mapping, version, or open data schema. | Read metadata and OpenType via JMX API. |
| Local and remote results differ | Client points to a different MBeanServer/JVM. | Verify PID, endpoint, and ObjectName. |
| Code is right but tests fail flakily | Shared MBeanServer, duplicate ObjectNames, or parallel tests. | Use unique domains/names and strict cleanup. |

## 18. Writing automated tests to protect the JMX contract

A test can run alongside the Spring ApplicationContext after the exporter initializes:

\`\`\`java
import java.lang.management.ManagementFactory;
import java.util.Arrays;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "com.example.jobs:type=ImportJob,name=Daily"
);

if (!server.isRegistered(name)) {
    throw new AssertionError("Expected MBean missing");
}

MBeanInfo info = server.getMBeanInfo(name);

MBeanAttributeInfo count =
    Arrays.stream(info.getAttributes())
        .filter(a -> a.getName().equals("CompletedCount"))
        .findFirst()
        .orElseThrow(() ->
            new AssertionError("Missing CompletedCount")
        );

if (!count.isReadable() || count.isWritable()) {
    throw new AssertionError(
        "CompletedCount must be read-only"
    );
}

boolean hasPause =
    Arrays.stream(info.getOperations())
        .anyMatch(op ->
            op.getName().equals("requestPause")
            && op.getSignature().length == 0
            && "void".equals(op.getReturnType())
        );

if (!hasPause) {
    throw new AssertionError("Missing requestPause()");
}

boolean leaked = Arrays.stream(info.getOperations())
    .anyMatch(op ->
        op.getName().equals("readInternalSecret")
    );

if (leaked) {
    throw new AssertionError(
        "Internal method unexpectedly exported"
    );
}
\`\`\`

This is a *contract* test; it does not need to execute the operation. It protects names, signatures, read/write capabilities, and prevents exporting internal APIs. In real tests, use JUnit and assert against a Spring context configured in the test.

### 18.1. Should you test an allowlist or a denylist?

A denylist only blocks known dangerous methods. An allowlist enumerates the permitted attributes/operations and is more useful when you want to prevent future methods from leaking via a reflective assembler.

Expected example:

\`\`\`text
Attributes allowed:
  Running
  CompletedCount

Operations allowed:
  requestPause()
\`\`\`

A test can compare the list of canonical names/signatures with the expected set; when a developer adds a new operation, the test forces them to intentionally update the contract.

Do not assert every piece of metadata against a long exact description string if wording may be tweaked frequently, unless the description is part of a contract required to remain stable.

## 19. Checking the lifecycle of exported MBeans

When a Spring context closes, \`MBeanExporter\` normally unregisters the MBeans it managed. You can verify this:

\`\`\`java
AnnotationConfigApplicationContext context =
    new AnnotationConfigApplicationContext(JmxExportConfig.class);

try {
    if (!server.isRegistered(name)) {
        throw new AssertionError(
            "MBean not registered after context startup"
        );
    }
} finally {
    context.close();
}

if (server.isRegistered(name)) {
    throw new AssertionError(
        "MBean still registered after context close"
    );
}
\`\`\`

This assumes no other exporter owns the same \`ObjectName\` and a single \`MBeanServer\` is used consistently. If the context does not close cleanly (hard JVM kill), cleanup callbacks cannot be guaranteed to run.

Do not unregister a production application's MBean just to test the contract while the system is serving users. Lifecycle checks that alter state should be executed in test environments.

## 20. Post-export MBeanInfo inspection checklist template

When a new MBean is added to Spring, follow these steps in order:

1. Identify the actual **MBeanServer** used by the exporter.
2. Identify the exact \`ObjectName\`.
3. Check \`isRegistered(name)\` after context initialization.
4. Read \`MBeanInfo\` with \`getMBeanInfo(name)\`.
5. Compare **attribute** names and types against the expected contract.
6. Check **readable/writable/isIs** for every important attribute.
7. Compare **operation** names and signatures.
8. Check descriptions and parameter metadata where needed.
9. Check descriptor/OpenType/ModelMBean metadata if applicable.
10. Verify **no** internal or sensitive attributes/operations are present.
11. Inspect constructor/notification metadata if relevant to functionality.
12. Confirm JConsole or remote clients target the right JVM/server.
13. Run tests with side effects only in appropriate environments.
14. Verify cleanup after context shutdown in integration tests.
15. If changing the contract, document compatibility/versioning for clients depending on JMX.

This is a workflow learners can apply during JMX development; when writing automated code, use a small expected schema rather than relying on metadata list ordering.

## 21. Practice exercises

### Exercise 1 — Standard MBean

Create \`ImportJobMonitorMBean\` and \`ImportJobMonitor\`. Register it on the platform MBeanServer, read \`MBeanInfo\`, and confirm \`Running\`, \`CompletedCount\`, and \`requestPause\` are present while \`InternalCredentialAlias\` is absent.

**Goal:** understand how the management interface defines the Standard MBean surface.

### Exercise 2 — Spring annotations

Create a \`@ManagedResource\` with two \`@ManagedAttribute\`s and one \`@ManagedOperation\`. Export it via an appropriate metadata assembler; check descriptions and runtime metadata.

**Goal:** prove that annotations flow through to MBeanInfo after export.

### Exercise 3 — Negative test

Add a public method \`deleteAllJobsInternal()\` to the Spring bean without annotating it. Write a check asserting that this method does not appear in \`MBeanInfo.getOperations()\`.

**Goal:** catch exporters or assemblers that expose too many methods.

### Exercise 4 — Signature

Create \`retry(int limit, boolean dryRun)\`, declare parameter metadata, and check \`MBeanOperationInfo.getSignature()\`. Try changing \`int\` to \`Integer\` and observe the contract change.

**Goal:** understand that signatures are part of the JMX API.

### Exercise 5 — Descriptor

Read \`MBeanInfo.getDescriptor()\` and each attribute/operation descriptor, noting the \`currencyTimeLimit\` field if present. Explain why a descriptor does not automatically imply business caching or persistence.

**Goal:** distinguish metadata from behavior.

### Exercise 6 — Wrong MBeanServer

Configure an exporter to use a custom MBeanServer in a lab environment. Compare \`isRegistered\` results from the custom server and the platform server.

**Goal:** know to check the right registry rather than guessing.

### Exercise 7 — Lifecycle

Start a Spring context and confirm the MBean is registered; close the context and confirm the MBean is unregistered. Use unique names to avoid collisions across tests.

**Goal:** understand exporter lifecycle and cleanup.

## 22. Review questions

**1. Why read runtime MBeanInfo instead of only reading @ManagedResource?** Because the exporter, naming strategy, assembler, and lifecycle determine what is actually registered and published.

**2. Does \`isRegistered(name)\` returning true mean the contract is completely right?** No. It only confirms the name exists; you must check attributes/operations/signatures.

**3. Which API indicates whether an attribute is writable?** \`MBeanAttributeInfo.isWritable()\`.

**4. Which API returns an operation's signature?** \`MBeanOperationInfo.getSignature()\`.

**5. If the description is empty, what should you inspect?** The metadata assembler and how the Spring JMX exporter processes annotations.

**6. Does a public Java method outside the management interface automatically become a Standard MBean operation?** No, if Standard MBean conventions are used properly.

**7. Does MBeanInfo contain current attribute values?** No. Metadata describes the schema; retrieving values requires \`getAttribute\`.

**8. Why should you have negative tests?** To detect accidental export of internal methods or attributes.

**9. If a client cannot see the MBean, what should you check first?** ObjectName, the right MBeanServer, exporter, lifecycle, and registration policy.

**10. Should you invoke \`requestPause()\` just to check that it exists?** No. Use \`MBeanInfo\` for safe inspection; invoke operations only in appropriate tests.

## 23. Summary

Inspecting **actual MBeanInfo after export** is a necessary step to confirm Spring published the right JMX contract. \`MBeanServer.getMBeanInfo\` provides metadata for attributes, operations, constructors, notifications, and descriptors; this information helps detect wrong ObjectNames, wrong assemblers, wrong read/write flags, missing operations, or leaked internal APIs.

The goal is to protect the management surface at **runtime**, rather than merely trusting annotations or interfaces in source code. A small contract test suite based on allowlists and negative assertions helps Spring applications keep their management interface stable and safe across changes.

## References

- Java SE 21 — \`MBeanInfo\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanInfo.html
- Java SE 21 — \`MBeanServer\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
- Java SE 21 — \`MBeanAttributeInfo\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanAttributeInfo.html
- Java SE 21 — \`MBeanOperationInfo\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanOperationInfo.html
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework Javadoc — \`MBeanExporter\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporter.html
- Spring Framework Javadoc — \`MetadataMBeanInfoAssembler\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/assembler/MetadataMBeanInfoAssembler.html