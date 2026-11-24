# Choosing Autodetection vs. Explicit Registration by Risk in Spring JMX

## 1. The Problem to Solve

In Spring Framework JMX, \`MBeanExporter\` can expose Spring beans to an \`MBeanServer\` in two common ways:

- **Autodetection:** the exporter scans for eligible beans in the \`ApplicationContext\` according to the configured detection mode.
- **Explicit registration:** specifically configuring the set of beans to export, usually with \`MBeanExporter.setBeans(...)\` and intentional \`ObjectName\`s.

Both have value. Autodetection reduces repetitive configuration when there are many management beans. Explicit registration helps bound the JMX surface in an easily auditable way. The right decision depends on environment risk, sensitivity of operations/attributes, bean count, code changes over time, and operational control requirements.

**Central question:** When a new bean is added to the application or when JMX metadata changes, should the system automatically push that bean into \`MBeanServer\`, or must it be actively added to the export list?

After this lesson, you will be able to:

1. Explain autodetection and explicit registration mechanisms in \`MBeanExporter\`.
2. Distinguish autodetect modes and the role of \`MBeanInfoAssembler\`.
3. Identify risks to evaluate before automatically exposing a bean.
4. Choose the right mode for development, test, production, or sensitive systems.
5. Design a verification workflow for \`ObjectName\`, \`MBeanInfo\`, and exporter ownership.
6. Avoid common pitfalls such as duplicate MBeans, accidentally exposing dangerous operations, and expecting annotations to self-register.

## 2. Mental Model

\`\`\`text
                   Spring ApplicationContext
                      /               \
                     /                 \
             AUTODETECTION        EXPLICIT REGISTRATION
                   |                      |
       Scan beans by mode          Specified list
       (MBean/assembler/...)       (setBeans map)
                   |                      |
                   +----------+-----------+
                              |
                         MBeanExporter
                       +------+------+
                       |             |
               ObjectNamingStrategy  MBeanInfoAssembler
                       |             |
                       +------+------+
                              |
                         MBeanServer
                              |
                     JConsole/JMX client
\`\`\`

Distinguish:

- **A bean managed by the Spring container** does not automatically mean it is an MBean.
- **A bean selected by the exporter** is not guaranteed to register successfully, because \`ObjectName\`, metadata, or conflicts may fail.
- **A successfully registered MBean** is not automatically remotely accessible; JMX remote connectors and network permissions are configured separately.
- **Autodetection** selects candidates; \`MBeanInfoAssembler\` determines the management interface and \`ObjectNamingStrategy\` determines the name.

Do not confuse JMX autodetection with Spring component scanning. Component scanning finds classes to create Spring beans; JMX autodetection inspects beans already in the container to see which ones are suitable for export.

## 3. Autodetection Modes

\`MBeanExporter\` provides primary detection modes:

| Mode | Meaning | Intended Outcome |
|---|---|---|
| \`AUTODETECT_NONE\` | Do not automatically discover beans | Only explicitly configured objects are considered for export |
| \`AUTODETECT_MBEAN\` | Discover beans matching JMX MBean conventions/interfaces | Automatically exports beans that have a JMX management interface |
| \`AUTODETECT_ASSEMBLER\` | Discover based on an autodetect-capable \`MBeanInfoAssembler\` | Fits metadata-driven JMX and annotation assemblers |
| \`AUTODETECT_ALL\` | Combines MBean-based and assembler-based discovery | Potentially widest scope among the modes above |

These values govern **candidate discovery**, not security policies or authorization.

### 3.1. AUTODETECT_NONE

This mode is easy to control when every exported bean needs an explicit decision. Using \`setBeans(...)\`, the exporter knows the exact declared bean set.

Advantage: changes to another bean in the container do not automatically expand the MBean set via scanning.

Limitation: when adding a new MBean, configuration must be updated; an operationally needed component can be missed if processes do not keep up.

### 3.2. AUTODETECT_MBEAN

This mode targets beans already conforming to JMX MBean conventions or an appropriate MBean contract.

Standard MBean example:

\`\`\`java
public interface QueueMonitorMBean {
    int getPendingCount();
    void resetStatistics();
}

public class QueueMonitor implements QueueMonitorMBean {
    @Override
    public int getPendingCount() {
        return 42;
    }

    @Override
    public void resetStatistics() {
        // Illustrates a management operation only.
    }
}
\`\`\`

When the bean is created by Spring and detected by the exporter as a compliant MBean, it can be exported. However, naming still must align with the naming strategy.

**Risk:** A new class that happens to follow MBean conventions can become a candidate if autodetection is enabled. Control which modules are scanned and which MBeans are actually exposed.

### 3.3. AUTODETECT_ASSEMBLER

This mode relies on an assembler, such as \`MetadataMBeanInfoAssembler\` with \`AnnotationJmxAttributeSource\`.

\`\`\`java
@ManagedResource(
    objectName = "com.example.monitoring:type=Queue,name=Orders"
)
public class QueueMonitor {
    @ManagedAttribute
    public int getPendingCount() {
        return 42;
    }
}
\`\`\`

A bean with matching metadata can be selected through the assembler. Yet \`@ManagedResource\` is **only metadata**; the source, assembler, and exporter must be properly configured.

**Risk:** A developer adds \`@ManagedResource\` for debugging, and because autodetection is enabled, the new bean may appear on the production JMX management surface.

### 3.4. AUTODETECT_ALL

This mode covers both detecting beans conforming to an MBean contract and beans recognized by the assembler.

It reduces per-bean declarations but makes export scope change with source code, dependencies, and the Spring context.

Do not assume \`AUTODETECT_ALL\` is best merely because its name contains “ALL”. It fits when there is a clear discovery goal and strong change control; in systems requiring strict security or tenant isolation, broad scope can be harder to audit.

## 4. Explicit Registration with setBeans

Example of two specifically chosen beans:

\`\`\`java
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class JmxConfiguration {
    @Bean
    public MBeanExporter mBeanExporter(
            QueueMonitor queueMonitor,
            CacheMonitor cacheMonitor) {

        Map<String, Object> exports = new LinkedHashMap<>();
        exports.put(
            "com.example.monitoring:type=Queue,name=Orders",
            queueMonitor
        );
        exports.put(
            "com.example.monitoring:type=Cache,name=Products",
            cacheMonitor
        );

        MBeanExporter exporter = new MBeanExporter();
        exporter.setBeans(exports);
        exporter.setAutodetectMode(
            MBeanExporter.AUTODETECT_NONE
        );
        return exporter;
    }
}
\`\`\`

In the example:

- Two objects are passed directly into the export map.
- Each entry specifies an intentional ObjectName.
- Autodetection is disabled to avoid expanding the export set outside the list.
- When adding a third MBean, configuration must be updated.

The classes \`QueueMonitor\` and \`CacheMonitor\` must be valid MBeans or supported for adaptation by the exporter with an appropriate assembler. If they are POJOs using only annotations, an annotation metadata assembler must be configured; \`setBeans\` alone does not create intentional management metadata.

**Note on keys:** \`setBeans\` uses keys/names in the export configuration; how the final name is determined can interact with \`ObjectNamingStrategy\`. When exact control is needed, verify the actually registered \`ObjectName\` rather than inferring all behavior from a key string.

## 5. Annotation-Based Autodetection

Example using \`@ManagedResource\` with an annotation-driven exporter.

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.monitoring:type=Queue,name=Orders",
    description = "Order queue monitoring"
)
public class QueueMonitor {
    @ManagedAttribute(description = "Current queue depth")
    public int getPendingCount() {
        return 42;
    }
}
\`\`\`

Spring Framework allows using:

\`\`\`java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxConfiguration {
}
\`\`\`

With suitable annotation export configuration, Spring can locate managed beans from metadata. This is concise for projects with clear annotation conventions.

What must be managed is that **a new annotation can expand the set of exported MBeans** if autodetection is enabled. Therefore, code reviews must treat \`@ManagedResource\` and member annotations as management API changes, not harmless comments.

### Difference with Spring Boot

If the application uses Spring Boot, check auto-configuration and properties like \`spring.jmx.enabled\` in the version in use. Do not add \`@EnableMBeanExport\` or a manual \`MBeanExporter\` if Boot already configures the same capability, because multiple exporters may attempt to register the same ObjectName.

Exporter autodetection and exposing Spring Boot Actuator endpoints via HTTP/JMX are related topics, not identical ones. Manage each configuration according to its purpose.

## 6. Evaluating Risk Before Choosing a Mode

There is no single right answer for every application. You can evaluate across these dimensions:

| Factor | Signs Favoring Explicit Registration | Signs Where Autodetection Can Fit |
|---|---|---|
| Sensitivity | MBean has critical state-changing operations | MBean is primarily read-only, non-sensitive data |
| Scale | Few MBeans, stable set of names | Many monitor types, frequent additions |
| Access rights | Multi-tenant/role groups needing strict allowlist | Controlled internal operational environment |
| Code sources | Multiple teams, plugins/dependencies may add beans | Management beans are centrally controlled |
| Change governance | Want every new MBean reviewed individually | Want to add managed beans via annotations |
| Debugging | Must guarantee no extra MBeans outside the list | Need quick discovery of observability MBeans |
| Environment | Sensitive or regulated production | Test/dev or well-governed production |
| Ownership | Multiple contexts/exporters sharing an MBeanServer | Single context with clear naming and permissions |

**Do not equate explicit with “absolute safety”.** An explicitly registered MBean with dangerous operations and an improperly secured remote JMX setup still carries high risk.

Conversely, autodetection can fit production when annotation sets are controlled, the management surface is tested, and JMX access is properly restricted.

## 7. Risk-Based Selection Matrix

A decision guide:

| Level | Examples | Usually Suitable Strategy | Additional Conditions |
|---|---|---|---|
| **Low** | Read-only counters/health attributes, dev environments | Assembler or MBean autodetection | Verify metadata and avoid sensitive data |
| **Medium** | Cache monitors, lightweight refreshes, staging | Reviewed autodetection or explicit | Limit access and control operations |
| **High** | Resetting production state, changing runtime config | Explicit registration/allowlist | Authentication, authorization, audit, validation |
| **Very High** | Financially impactful MBeans, sensitive data, multi-tenant | Minimize export, typically explicit | Possibly avoid exposing operations directly via JMX |

This table is a mental framework, not an automatically enforced security policy. Actual decisions must consider impact level, access model, and deployment.

### Questions to Ask Before Enabling Autodetection

1. Who can connect to this MBeanServer?
2. Do MBeans have writable attributes or state-changing operations?
3. Does the export mechanism scan beans in dependencies/modules outside your control?
4. Can ObjectNames collide when multiple contexts run in the same JVM?
5. Do monitoring tools depend on current MBean names?
6. Is every annotation change reviewed like a management API change?
7. Can MBeans be accurately inventoried after startup?

If you cannot answer the questions about permissions and export scope, narrow the MBean set before expanding auto-discovery.

## 8. Technical Risk Categories of Autodetection

### 8.1. Accidentally expanding the management surface

A developer adds:

\`\`\`java
@ManagedResource(
    objectName = "com.example.monitoring:type=Maintenance,name=System"
)
public class MaintenanceMonitor {
    @ManagedOperation
    public void clearAllCaches() {
        // High impact.
    }
}
\`\`\`

If \`AUTODETECT_ASSEMBLER\` is enabled, this bean may be exported without editing a separate allowlist. If the MBeanServer is reachable by a broader operator group than anticipated, risk increases.

Solution: review annotations, check the actual published MBean set, enforce JMX authorization, and avoid putting sensitive methods on general management interfaces.

### 8.2. Unexpected changes when upgrading dependencies

A new library or module may introduce compliant MBeans or beans with JMX metadata. In a context with broad autodetection, the MBean set changes even though the export config file did not change.

Solution: inventory ObjectNames in integration tests and compare against the expected MBean list. Consider \`AUTODETECT_ASSEMBLER\` over \`AUTODETECT_ALL\` if you want to select only annotation-based managed resources.

### 8.3. Name collisions

Two beans might both declare:

\`\`\`text
com.example.monitoring:type=Worker,name=Import
\`\`\`

on the same MBeanServer. When autodetection discovers both, the exporter may hit \`InstanceAlreadyExistsException\` or follow the registration policy.

Solution: define a domain/type/name/instance naming convention; avoid having multiple exporters try to register the same object under the same name.

### 8.4. Metadata and proxies

Spring AOP or proxies can make a runtime bean differ from its target class. The annotation source/assembler must locate the right metadata, and exposed operations must be invocable on the actual object.

Solution: write integration tests for beans with \`@Transactional\`, \`@Async\`, or special proxies. If needed, extract a separate management facade bean.

### 8.5. Differences across environments

Dev may enable JMX/exporter while production disables it, or vice versa. An operator might wrongly conclude a bean is broken just by looking at JConsole.

Solution: verify exporter configuration, target MBeanServer, and remote connectors for each environment. Do not confuse a client failing to connect with a bean not being registered.

## 9. Risks of Explicit Registration

Explicit registration also has costs and failure modes:

### 9.1. Missing a new MBean

A developer creates a valid monitor bean but forgets to add it to the export map. The bean still works in Spring, but JMX clients cannot see it.

How to handle: manage the expected MBean list as a contract and write tests verifying critical ObjectNames.

### 9.2. Configuration drift

An ObjectName or bean reference changes, yet the export map is not updated. This can lead to startup failures or exporting the wrong object.

How to handle: centralize configuration; use constants/factories for ObjectNames where appropriate, and verify registration.

### 9.3. Overly large configuration map

With hundreds of MBeans, a long \`setBeans\` map becomes hard to read, especially when components continually add their own monitors.

How to handle: split configuration by module, or use controlled autodetection with naming conventions and post-startup inventorying.

### 9.4. False sense of security

An explicit list can still contain an MBean exposing sensitive data or dangerous operations.

How to handle: review \`MBeanInfo\`, actual attributes/operations, remote JMX permissions, and access paths; do not treat the presence of an allowlist as sufficient by itself.

## 10. Registration Policies and Collisions

\`MBeanExporter\` supports \`RegistrationPolicy\` to handle existing ObjectNames:

\`\`\`java
import org.springframework.jmx.support.RegistrationPolicy;

exporter.setRegistrationPolicy(
    RegistrationPolicy.FAIL_ON_EXISTING
);
\`\`\`

Policies:

| Policy | Meaning | Risk to Consider |
|---|---|---|
| \`FAIL_ON_EXISTING\` | Fails when name already exists | May fail app startup, but surfaces config errors early |
| \`IGNORE_EXISTING\` | Does not replace existing registration | May keep a different MBean than you expected |
| \`REPLACE_EXISTING\` | Replaces existing registration | May affect an MBean owned by another context/library |

A registration policy does not replace the autodetection/explicit decision. It handles **when a collision has already occurred**, rather than deciding the right set of beans allowed to be exposed.

In sensitive production systems, failing fast on duplicate names usually helps catch misconfigurations; however, evaluate the impact of startup failure on the system.

## 11. Verifying the Exported MBean Set

A good way to govern both strategies is **verifying the actual MBeanServer** after the Spring context starts.

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import java.util.Set;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName pattern = new ObjectName(
    "com.example.monitoring:*"
);

Set<ObjectName> names =
    server.queryNames(pattern, null);

for (ObjectName name : names) {
    System.out.println(name.getCanonicalName());
}
\`\`\`

**Note:** \`ManagementFactory.getPlatformMBeanServer()\` returns the current JVM's platform MBeanServer. If the exporter selects a different server, query that exact server. If the client is in another JVM, use \`JMXConnector\` and \`MBeanServerConnection\`.

\`queryNames()\` shows that names exist, which is not enough to determine safety. Read \`MBeanInfo\` next:

\`\`\`java
for (ObjectName name : names) {
    var info = server.getMBeanInfo(name);

    System.out.println("MBean: " + name.getCanonicalName());

    for (var attribute : info.getAttributes()) {
        System.out.printf(
            "  attribute=%s readable=%s writable=%s%n",
            attribute.getName(),
            attribute.isReadable(),
            attribute.isWritable()
        );
    }

    for (var operation : info.getOperations()) {
        System.out.printf(
            "  operation=%s%n",
            operation.getName()
        );
    }
}
\`\`\`

This is how to catch an attribute suddenly becoming writable or a new operation being exposed after a code change.

### Testing the Expected Name Set

In integration tests, compare the ObjectName list for the application domain against an allowlist or approved name set.

Logic example:

\`\`\`java
Set<String> actual = names.stream()
    .map(ObjectName::getCanonicalName)
    .collect(java.util.stream.Collectors.toSet());

Set<String> expected = Set.of(
    new ObjectName(
        "com.example.monitoring:type=Queue,name=Orders"
    ).getCanonicalName(),
    new ObjectName(
        "com.example.monitoring:type=Cache,name=Products"
    ).getCanonicalName()
);

if (!actual.equals(expected)) {
    throw new AssertionError(
        "Unexpected JMX exposure: " + actual
    );
}
\`\`\`

In environments where infrastructure also creates MBeans in the same domain, the comparison scope must be clearly defined. Do not compare all of \`java.lang\` or system domains as if every name were owned by the application.

## 12. A Hybrid Design

Autodetection and explicit registration do not have to apply uniformly across every part of a system. Management groups can be split by risk level.

Examples:

- **Read-only monitoring:** use reviewed autodetection in an observability-only domain.
- **Sensitive operations:** use an explicit exporter, restrict the bean set, and separate domains/permissions if architecture supports it.
- **Library MBeans:** let libraries manage them or define explicit ownership to avoid duplicate exports.
- **Dynamic instances:** use programmatic registration with controlled lifecycle/naming instead of sharing one annotation name across all instances.

Note that **multiple exporters in the same context/JVM can overlap on beans or ObjectNames**. When using a hybrid model, ensure every MBean has a single clear registration owner.

A simpler organization is keeping one exporter with an explicit set in production, and enabling autodetection only in experimental profiles if truly needed. However, environment profiles must not become an excuse for untested differences in management behavior.

## 13. Security and Access Scope

Separate three layers:

1. **Selection:** which beans the exporter selects.
2. **Management interface:** which attributes/operations the bean exposes.
3. **Access control:** who is allowed to read/write/invoke over JMX.

Autodetection/explicit primarily handle the **selection** layer. They do not themselves enforce the third layer.

A secure deployment needs to evaluate:

- Whether remote JMX is open and on which network interfaces.
- Authentication, authorization, TLS, or channel protection when needed.
- Which users are allowed to call \`invoke\`, \`setAttribute\`.
- Whether operations affect data, caches, workers, or external systems.
- Whether attributes expose secrets, tokens, system paths, or personal info.
- Whether sensitive management actions are audited.

Even a “read-only” MBean needs review because diagnostic data can be sensitive. Conversely, an explicit MBean with state-changing operations still needs protection.

## 14. Risk-Based Configuration: Two Examples

### 14.1. Internal System with Monitoring Only

Suppose an application has a couple dozen read-only monitors maintained by one code-owning team. Assembler-based autodetection can reduce map boilerplate and provide a consistent extension mechanism.

\`\`\`java
MBeanExporter exporter = new MBeanExporter();
exporter.setAssembler(assembler);
exporter.setNamingStrategy(namingStrategy);
exporter.setAutodetectMode(
    MBeanExporter.AUTODETECT_ASSEMBLER
);
\`\`\`

Suitable conditions:
- Only classes marked with JMX annotations are evaluated.
- Sensitive operations are excluded under the same policy.
- ObjectNames are verified via integration tests.
- Remote access is restricted.
- Every \`@ManagedResource\` change is reviewed.

### 14.2. Production System with Critical Management Operations

Suppose the system has \`flushQueue\`, \`reloadCredentials\`, \`resetState\`. Having a new annotation accidentally open an operation can have serious consequences.

An explicit list:

\`\`\`java
MBeanExporter exporter = new MBeanExporter();
exporter.setAutodetectMode(
    MBeanExporter.AUTODETECT_NONE
);
exporter.setBeans(Map.of(
    "com.example.admin:type=Cache,name=SafeCache",
    safeCacheMonitor
));
\`\`\`

This keeps export scope explicit. You still need to inspect interface contents and access control. If \`safeCacheMonitor\` is an annotation-based POJO, add the appropriate metadata assembler.

**There is no fixed threshold** on bean count or risk level for choosing. It is an engineering judgment based on impact and required control.

## 15. Common Errors and Misconceptions

**Misconception 1: “Autodetection means every @Component becomes an MBean.”**  
False. The exporter detects according to mode and JMX/assembler contracts, not by automatically grabbing all Spring beans regardless of metadata.

**Misconception 2: “@ManagedResource registers itself into MBeanServer.”**  
No. The annotation provides metadata; an active export mechanism is needed.

**Misconception 3: “AUTODETECT_ALL is the safest mode.”**  
No. It is a broad detection scope, not a security mode.

**Misconception 4: “Explicit registration requires no permission checks.”**  
False. An explicit list does not restrict who can invoke JMX if access control is not configured.

**Misconception 5: “Successfully registering an MBean makes it reachable by remote clients.”**  
No. Remote connectors, networking, and security are configured separately.

**Misconception 6: “RegistrationPolicy.REPLACE_EXISTING cleanly solves duplicate names.”**  
No. It can mask conflicts and replace other MBeans, causing ownership/lifecycle bugs.

**Misconception 7: “If it works in dev, production has the same MBean set.”**  
Not guaranteed. Profiles, dependencies, auto-configuration, and created beans can differ across environments.

**Misconception 8: “Checking ObjectName is enough to review exposure.”**  
No. You also need \`MBeanInfo\`, especially writable attributes and operations.

## 16. Pragmatic Decision Workflow

You can follow this sequence in a new design:

1. **List management needs:** health/counters, diagnostics, runtime configuration, state-changing operations.
2. **Classify impact:** read-only, config writes, sensitive operations, confidential data.
3. **Identify who can connect:** local tools, internal production, or remote systems.
4. **Choose export scope:** explicit when a strict allowlist is needed; autodetect when metadata governance is strong and explicit config overhead is high.
5. **Choose naming policy:** domain, type, name, instance to avoid collisions.
6. **Control interfaces:** annotations or Standard MBean interfaces exposing only what is needed.
7. **Verify at runtime:** export MBeans in a test context, query ObjectNames and \`MBeanInfo\`.
8. **Verify access control:** remote network, credentials, invoke/set privileges.
9. **Verify lifecycle:** startup, shutdown, restart, multi-context, and collisions.
10. **Document conventions:** so developers adding new beans know when to update the allowlist or annotations.

If changing exporter mode after deployment, treat it as a management surface change: which MBeans appear/disappear, which clients are affected, and which permissions need updating.

## 17. Practice Exercises

### Exercise A — Compare two strategies

1. Create two monitor beans \`QueueMonitor\` and \`CacheMonitor\`.
2. Annotate both with \`@ManagedResource\`.
3. Use \`AUTODETECT_ASSEMBLER\`; verify both are exported when an appropriate assembler/metadata source is configured.
4. Switch to \`AUTODETECT_NONE\` and \`setBeans\` containing only \`QueueMonitor\`.
5. Verify \`CacheMonitor\` is no longer registered by the exporter.
6. Compare ObjectNames and MBeanInfo between the two runs.

### Exercise B — Add an operation

1. Use an MBean with only read-only getters.
2. Add \`@ManagedOperation\` on a state-changing method in a test environment.
3. Re-read \`MBeanInfo.getOperations()\`.
4. Explain why this is a management API change even though the exporter configuration did not change.

### Exercise C — ObjectName collision

1. Create two beans with the same \`@ManagedResource.objectName\`.
2. Enable autodetection on the same MBeanServer.
3. Observe the error/policy.
4. Give them distinct names or export only one bean.
5. Verify the result with \`queryNames()\`.

### Exercise D — Production allowlist check

1. List permitted ObjectNames in the application domain.
2. Start the context.
3. Call \`queryNames()\` to get the actual list.
4. Call \`getMBeanInfo()\` to inspect writable attributes and operations.
5. Fail the test if any MBean or operation is outside the approved contract.

## 18. Self-Check Questions

**Question 1.** What does \`AUTODETECT_NONE\` mean?  
**Answer:** Do not automatically discover beans; the export set is determined from explicit configuration.

**Question 2.** When is \`AUTODETECT_ASSEMBLER\` appropriate?  
**Answer:** When using an assembler capable of recognizing beans declared with metadata such as Spring JMX annotations.

**Question 3.** Why can autodetection increase risk without changing configuration files?  
**Answer:** A new bean or annotation can automatically expand the set of exported MBeans.

**Question 4.** Does explicit registration replace JMX authentication/authorization?  
**Answer:** No. It bounds the set of selected beans, not who has permission to operate on them.

**Question 5.** Why must you read \`MBeanInfo\` after registration?  
**Answer:** To verify the actually exposed attributes/operations, including writable flags.

**Question 6.** Is choosing \`REPLACE_EXISTING\` the best fix for name collisions?  
**Answer:** No. Determine ownership, fix naming or export scope; replace policy can cause unintended side effects.

**Question 7.** What should a system with many plugins/contexts and sensitive MBeans prioritize?  
**Answer:** An easily auditable export scope, controlled permissions, and collision-free naming rules; explicit registration is usually easier to govern.

## 19. Takeaways

- Autodetection and explicit registration are **two bean selection strategies**, not two security mechanisms.
- \`AUTODETECT_NONE\` keeps the export set explicit; \`AUTODETECT_MBEAN\` discovers compliant MBeans; \`AUTODETECT_ASSEMBLER\` relies on the assembler; \`AUTODETECT_ALL\` combines discovery sources.
- Autodetection is convenient when annotations are governed consistently and scaling rapidly is needed, but it can grow the MBean set when code/dependencies change.
- Explicit registration provides a clear allowlist for sensitive systems, at the cost of configuration maintenance.
- Regardless of choice, review ObjectNames, MBeanInfo, state-mutating operations, authentication/authorization, and lifecycle.
- Never use registration policy to mask naming conflicts.
- Verify in practice with \`MBeanServer.queryNames()\` and \`getMBeanInfo()\` on the right server.

### References

- Spring Framework Reference — JMX Exporting: https://docs.spring.io/spring-framework/reference/integration/jmx/exporting.html
- Spring Framework Javadoc — \`MBeanExporter\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporter.html
- Spring Framework Javadoc — \`MetadataMBeanInfoAssembler\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/assembler/MetadataMBeanInfoAssembler.html
- Spring Framework Javadoc — \`RegistrationPolicy\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/support/RegistrationPolicy.html
- Spring Framework Javadoc — \`@EnableMBeanExport\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/annotation/EnableMBeanExport.html
- Java SE 21 API — \`MBeanServer\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
