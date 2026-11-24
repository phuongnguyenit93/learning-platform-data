# IdentityNamingStrategy and Identity-Based Naming in Spring Framework JMX

## 1. Lesson Objectives

When Spring Framework exposes a bean to JMX using \`MBeanExporter\`, each MBean must be registered under a unique \`javax.management.ObjectName\` within the \`MBeanServer\` scope. Spring provides the \`ObjectNamingStrategy\` interface to determine this name. One of the built-in implementations is **\`IdentityNamingStrategy\`**, which creates an ObjectName based on the *identity* of the exported object.

The idea is to distinguish **different object instances**, even when they share the same class or the same logical bean name. In return, a name generated from identity may not be stable across application restarts or when instances are recreated. Therefore, this strategy fits certain technical needs, but is not by default the best choice for long-term monitoring/dashboards.

After this lesson, you will be able to:

- Understand the role of \`ObjectNamingStrategy\` in the Spring JMX export path.
- Distinguish object identity, \`equals()\`, \`hashCode()\`, and a resource's logical name.
- Describe how \`IdentityNamingStrategy\` generates names to distinguish instances.
- Configure the naming strategy in \`MBeanExporter\`.
- Understand benefits and limitations regarding multiple instances, proxies, restarts, and \`ApplicationContext\`.
- Verify the actual name via \`MBeanServer.queryNames()\` instead of guessing.
- Choose between identity naming and a stable naming strategy according to the consumer contract.

## 2. ObjectName Is a JMX Identity, Not a Java Bean Name

An \`ObjectName\` has the syntax:

\`\`\`text
<domain>:<key1>=<value1>,<key2>=<value2>
\`\`\`

Example:

\`\`\`text
com.example:type=Worker,name=Primary
\`\`\`

This name is unique to one MBean **within a single \`MBeanServer\`**. The same ObjectName can exist in two different MBeanServers. On the other hand, two Spring beans of the same class but different instances cannot both be registered into one MBeanServer under the exact same ObjectName.

For example:

\`\`\`java
Worker first = new Worker();
Worker second = new Worker();

System.out.println(first == second); // false
\`\`\`

If you use the same name \`com.example:type=Worker,name=Default\` for both, the second registration will hit an \`InstanceAlreadyExistsException\` conflict, unless the exporter has a different duplicate-handling policy.

\`IdentityNamingStrategy\` aims to solve the problem of distinguishing objects by identity instead of forcing developers to assign a unique logical name to every instance.

### 2.1. Object Identity Differs from Logical Equality

In Java:

\`\`\`java
a == b
\`\`\`

checks whether two references point to the same object.

\`\`\`java
a.equals(b)
\`\`\`

checks the equality rules defined by the class. Two distinct objects can have \`equals() == true\`.

\`\`\`java
System.identityHashCode(a)
\`\`\`

returns a hash code based on the object's identity semantics, independent of any \`hashCode()\` implementation overridden by the class. However, this value is not a durable identifier and is not guaranteed to be strictly unique at all times.

**Note:** "identity-based naming" is an identifier within the JVM/object lifecycle, not a business key, stable UUID, or hostname.

## 3. ObjectNamingStrategy in the Export Path

In Spring JMX, \`org.springframework.jmx.export.naming.ObjectNamingStrategy\` is the strategy that returns an \`ObjectName\` for the exported object.

General flow:

\`\`\`text
Spring-managed bean / object to export
                  |
                  v
             MBeanExporter
                  |
                  +----> ObjectNamingStrategy
                  |            |
                  |            v
                  |        ObjectName
                  |
                  +----> MBeanInfoAssembler
                  |      (MBean metadata)
                  |
                  v
      MBeanServer.registerMBean(...)
                  |
                  v
         JMX clients / JConsole
\`\`\`

\`ObjectNamingStrategy\` determines **naming**, while \`MBeanInfoAssembler\` determines which **attributes/operations** are published. The two mechanisms do not replace each other. When metadata or a JMX interface is invalid, changing the naming strategy will not fix MBean compliance errors.

Common options:

| Strategy | Name Source | Suitable For |
|---|---|---|
| \`IdentityNamingStrategy\` | Identity of the exported object | Temporary instances, needing to distinguish objects of the same class |
| \`KeyNamingStrategy\` | Defined mapping/configuration key | Management names with stable conventions |
| \`MetadataNamingStrategy\` | Metadata on the managed resource | Names declared via \`@ManagedResource\` |
| Custom naming strategy | Standardized class/module/tenant/instance | Monitoring contracts with specialized naming conventions |

Spring can use an explicit \`ObjectName\` from a mapping, or a naming strategy depending on configuration. Do not assume all exporters always default to \`IdentityNamingStrategy\`: check the actual exporter configuration and the Spring version in use.

## 4. How Does IdentityNamingStrategy Create Names?

\`IdentityNamingStrategy\` is an implementation of \`ObjectNamingStrategy\` that uses the identity of the managed object to build an ObjectName. The key idea is that the name can distinguish instances, rather than relying purely on the bean name.

\`\`\`text
Instance A of Worker ----> ObjectName A
Instance B of Worker ----> ObjectName B
\`\`\`

When the same instance is asked for its name again using the same strategy, the goal is a name tied to that instance. However, the specific details of domain, key-properties, and identity representation are determined by Spring's implementation. **Do not guess a specific ObjectName string** without calling the strategy or observing the registered name on your own JVM.

A direct way to check:

\`\`\`java
import org.springframework.jmx.export.naming.IdentityNamingStrategy;
import javax.management.ObjectName;

public class IdentityNameDemo {
    static class Worker {}

    public static void main(String[] args) throws Exception {
        IdentityNamingStrategy naming = new IdentityNamingStrategy();

        Worker a = new Worker();
        Worker b = new Worker();

        ObjectName nameA = naming.getObjectName(a, "worker");
        ObjectName nameB = naming.getObjectName(b, "worker");

        System.out.println("A = " + nameA);
        System.out.println("B = " + nameB);
        System.out.println("Equal? " + nameA.equals(nameB));
        System.out.println("A is pattern? " + nameA.isPattern());
    }
}
\`\`\`

When running the example with the appropriate Spring JMX dependency, read the actual runtime output to see the real ObjectName. If the \`ObjectName\` changes across JVM runs, that is a sign the strategy suits per-instance identification rather than a fixed contract.

**Limitation to remember:** identity hash codes can theoretically collide; therefore it is not a solution that guarantees global uniqueness for every object or every JVM. When a system requires absolute, long-term identifiers, use a separately managed stable key.

## 5. Example: Two Objects of the Same Class

Suppose an application manages two workers:

\`\`\`java
public class QueueWorker {
    private final String queue;

    public QueueWorker(String queue) {
        this.queue = queue;
    }

    public String getQueue() {
        return queue;
    }
}
\`\`\`

Two instances:

\`\`\`java
QueueWorker orders = new QueueWorker("orders");
QueueWorker returns = new QueueWorker("returns");
\`\`\`

A naming strategy that only uses the class name might generate the same ObjectName for both:

\`\`\`text
example:type=QueueWorker
example:type=QueueWorker
\`\`\`

Identity naming aims to produce two distinct ObjectNames without needing to know that \`orders\` or \`returns\` are the queue names. However, a dashboard wanting to observe the \`orders\` queue specifically will have a harder time if the name is only tied to the instance. If the need is a **business** resource, prefer naming like:

\`\`\`text
example.queue:type=QueueWorker,name=orders
example.queue:type=QueueWorker,name=returns
\`\`\`

Those names stay stable when the same queues are recreated on subsequent startups.

### 5.1. Different Selection Goals

If the goal is diagnosing short-lived objects within a single JVM, identity naming can be useful.

If the goal is configuring long-term alerts:

\`\`\`text
Alert when example.queue:type=QueueWorker,name=orders is unhealthy
\`\`\`

naming by business key saves clients from having to rediscover new ObjectNames after every restart.

## 6. Configuring MBeanExporter with IdentityNamingStrategy

A Spring Java configuration example using explicit export:

\`\`\`java
package example.jmx;

import java.util.Map;
import javax.management.MBeanServer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.naming.IdentityNamingStrategy;

@Configuration
public class JmxConfiguration {

    @Bean
    public WorkerStatus workerStatus() {
        return new WorkerStatus();
    }

    @Bean
    public MBeanExporter mbeanExporter(
            MBeanServer mbeanServer,
            WorkerStatus workerStatus) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(mbeanServer);
        exporter.setNamingStrategy(new IdentityNamingStrategy());
        exporter.setBeans(Map.of("workerStatus", workerStatus));
        return exporter;
    }
}
\`\`\`

The managed class can follow a Standard MBean interface:

\`\`\`java
// WorkerStatusMBean.java
public interface WorkerStatusMBean {
    boolean isHealthy();
}
\`\`\`

\`\`\`java
// WorkerStatus.java
public class WorkerStatus implements WorkerStatusMBean {
    @Override
    public boolean isHealthy() {
        return true;
    }
}
\`\`\`

And provide \`MBeanServer\` in configuration:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import org.springframework.context.annotation.Bean;

@Bean
public MBeanServer mbeanServer() {
    return ManagementFactory.getPlatformMBeanServer();
}
\`\`\`

The \`@Bean\` snippet for the server needs to be inside a \`@Configuration\` class, or you can use another configuration class that provides the server bean. In the example, \`setBeans\` contains the logical key \`workerStatus\`, while the naming strategy determines the ObjectName when the exporter uses that strategy.

**Important configuration point:** a mapping key can be an explicit ObjectName or a key interpreted by the naming strategy; the exact combination must be understood according to the Spring API. Do not assume \`IdentityNamingStrategy\` will override any hard-coded ObjectName supplied in another configuration.

## 7. Verifying Names in MBeanServer

The safe way to verify a bean's actual name is to query \`MBeanServer\` after the exporter completes registration.

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import java.util.Set;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

Set<ObjectName> names =
    server.queryNames(new ObjectName("*:*"), null);

for (ObjectName name : names) {
    System.out.println(name.getCanonicalName());
}
\`\`\`

In production, \`*:*\` can return many platform/application MBeans; replace it with a narrower domain or pattern after identifying the name format generated by the strategy. Use \`MBeanServer.queryNames\` because generated names may be unfamiliar to clients.

After finding the ObjectName, a client can:

\`\`\`java
MBeanInfo info = server.getMBeanInfo(name);
Object healthy = server.getAttribute(name, "Healthy");
\`\`\`

However, the client needs to select the right MBean and cannot rely solely on the class name if multiple instances share the same class. If identity naming does not contain distinguishing business information, an attribute like \`QueueName\` or a separate registry may be needed to map resources to ObjectNames.

### 7.1. Why Not Reuse a Name Printed from a Previous Run?

An object's identity is usually meaningful only within a single lifecycle. After a restart, the new object can receive a different identity. Hard-coding a generated ObjectName into dashboards creates a dependency on volatile runtime details.

## 8. Object Identity, equals, and hashCode

Three types of identification are often conflated:

\`\`\`java
a == b                      // same instance?
a.equals(b)                 // logical equality?
System.identityHashCode(a)  // identity-based hash value
\`\`\`

Example:

\`\`\`java
record WorkerKey(String queue) {}

WorkerKey a = new WorkerKey("orders");
WorkerKey b = new WorkerKey("orders");

System.out.println(a == b);                        // false
System.out.println(a.equals(b));                    // true
System.out.println(a.hashCode() == b.hashCode());  // true
\`\`\`

Even though \`a.equals(b)\` is true, they are still two different Java objects. Naming by **identity** aims to identify the object itself, not the \`queue\` key.

However, \`identityHashCode\` is just a hash code, **not a UUID**. This value is not guaranteed to be collision-free across all objects; it is not stable across JVM restarts; and it should not be used as a distributed or persistence key.

## 9. Spring AOP Proxies and Identity

Spring beans can be wrapped by a JDK dynamic proxy or CGLIB proxy to enforce transactions, security, caching, or logging.

\`\`\`text
Target object
    |
    v
Spring proxy
    |
    v
MBeanExporter registers an object
\`\`\`

The core question: which instance does the strategy receive? Target or proxy? That depends on the export path and configuration.

If naming computes based on the proxy's identity, recreating the proxy can change the MBean name even though the target logic has not changed. Therefore:

- Inspect the registered ObjectName rather than guessing based on the original object's identity.
- Test when switching a bean from non-proxied to proxied.
- If naming must be stable per resource, use a business key.
- Avoid depending on generated names when proxy lifecycle is not under your control.

Also check that the assembler/adapter exposes the right MBean attributes and operations when the object is a proxy; a naming strategy only handles the name, not metadata.

## 10. Multiple ApplicationContexts and Identity Naming

When multiple \`ApplicationContext\`s export MBeans into the same \`MBeanServer\`, identity naming can help distinguish different instances of the same class. However:

1. Each context may have its own exporter and lifecycle.
2. The generated name is not a stable contract for external clients.
3. If the same object is exported by two exporters, they may get the same identity-derived name and collide.
4. If two distinct objects collide in identity hash in rare cases, a hash-only strategy may not completely avoid collisions.
5. If an object is replaced on context refresh, the generated ObjectName may change.
6. Regardless of naming strategy, uniqueness is still checked in the shared \`MBeanServer\`.

For stable modules, consider:

\`\`\`text
example.platform:type=Worker,module=inventory,name=Primary
example.platform:type=Worker,module=billing,name=Primary
\`\`\`

For dynamic plugin instances, you can use an application-generated and managed instance ID, for example:

\`\`\`text
example.platform:type=PluginWorker,plugin=exporter,instance=8a7b
\`\`\`

Do not put tokens, emails, or sensitive data into an ObjectName. Instance IDs should be validated/escaped according to ObjectName rules and have a lifecycle policy.

## 11. Lifecycle: Registration and Unregistration

A generated ObjectName reflects an object existing during a period. When a Spring context closes, the exporter normally unregisters the MBeans it owns. If an application creates and destroys plugin contexts, ensure:

\`\`\`text
Context start -> new object -> new ObjectName -> registered
Context close -> exporter cleanup -> ObjectName unregistered
Context restart -> new object -> possibly new ObjectName
\`\`\`

Common mistakes:

- Failing to close a created \`ApplicationContext\`.
- Manually registering MBeans outside the exporter without unregistering them.
- Two exporters receiving the same object and registering the same name.
- Using \`RegistrationPolicy.REPLACE_EXISTING\`, obscuring ownership.
- Clients retaining stale ObjectNames after a context refresh.

**Do not solve lifecycle bugs by deleting every MBean in the same domain.** Another module may own them. Each exporter/context must manage its own registrations accurately.

## 12. IdentityNamingStrategy vs. KeyNamingStrategy and MetadataNamingStrategy

| Criterion | IdentityNamingStrategy | KeyNamingStrategy | MetadataNamingStrategy |
|---|---|---|---|
| Name source | Object identity | Configuration-specified name mapping | Management metadata |
| Name stable across restarts | Should not be expected | Yes, if mapping stays unchanged | Yes, if metadata stays unchanged |
| Distinguishing multiple instances of same class | Oriented toward distinguishing instances | Must supply different keys | Must supply different metadata/names |
| Easy for fixed dashboards | Not ideal | Usually good | Usually good |
| Dependency on instance/proxy | Higher | Lower if using logical IDs | Lower if metadata is stable |
| Easy to debug by resource name | Can be difficult | Good if keys are meaningful | Good if metadata is meaningful |

Choose based on **the kind of identity that needs to be preserved**:

- Java instance identity: the object currently alive in the JVM.
- Business identity: the \`inventoryQueue\` resource existing across multiple restarts.
- Deployment identity: application instance \`node-1\`, pod ID, or plugin instance.

There is no single best naming strategy for every system.

## 13. Designing a Custom Resource-ID-Based Naming Strategy

If clients need a stable ObjectName, you can implement \`ObjectNamingStrategy\` based on an identity-declaring interface.

\`\`\`java
public interface ManagedIdentity {
    String managementType();
    String managementName();
}
\`\`\`

\`\`\`java
import javax.management.MalformedObjectNameException;
import javax.management.ObjectName;
import org.springframework.jmx.export.naming.ObjectNamingStrategy;

public class ResourceNamingStrategy implements ObjectNamingStrategy {
    @Override
    public ObjectName getObjectName(Object managedBean, String beanKey)
            throws MalformedObjectNameException {
        if (!(managedBean instanceof ManagedIdentity resource)) {
            throw new IllegalArgumentException(
                "ManagedIdentity required: " + beanKey);
        }

        String type = ObjectName.quote(resource.managementType());
        String name = ObjectName.quote(resource.managementName());

        return new ObjectName(
            "example.management:type=" + type + ",name=" + name);
    }
}
\`\`\`

Note: \`ObjectName.quote\` produces a quoted property value; consider interaction with wildcards and check \`isPattern()\` if source values contain special characters. Resource ID values can be normalized and validated before creating the ObjectName. For this interface, avoid accepting uncontrolled arbitrary input.

If the bean is a Spring proxy that does not directly implement \`ManagedIdentity\`, a way to look up the ID via configuration/metadata or a suitable target-aware strategy is needed; do not assume casting always succeeds.

### 13.1. Stable ID and Uniqueness

A resource-ID-based naming strategy must guarantee uniqueness within the server:

\`\`\`text
example.management:type="Worker",name="orders"
example.management:type="Worker",name="returns"
\`\`\`

If two concurrent instances share the same resource ID, a collision still occurs. This is right: the system must decide whether two instances represent one resource or two separate resources and add an \`instance\` key if needed.

## 14. Testing a Naming Strategy

### 14.1. Testing the Same Instance and Two Instances

\`\`\`java
import org.junit.jupiter.api.Test;
import org.springframework.jmx.export.naming.IdentityNamingStrategy;

import javax.management.ObjectName;

import static org.junit.jupiter.api.Assertions.*;

class IdentityNamingStrategyTest {

    @Test
    void namingReflectsObjectIdentity() throws Exception {
        IdentityNamingStrategy strategy =
            new IdentityNamingStrategy();

        Object first = new Object();
        Object second = new Object();

        ObjectName a1 =
            strategy.getObjectName(first, "firstBean");
        ObjectName a2 =
            strategy.getObjectName(first, "firstBean");
        ObjectName b =
            strategy.getObjectName(second, "secondBean");

        assertEquals(a1, a2);
        assertFalse(a1.isPattern());
        assertFalse(b.isPattern());

        // Usually different for two distinct objects, but
        // do not treat identity hash as an absolute uniqueness guarantee.
    }
}
\`\`\`

### 14.2. Integration Testing via MBeanServer

A test should register two MBeans using an exporter, then query \`MBeanServer\`:

\`\`\`java
Set<ObjectName> names =
    server.queryNames(new ObjectName("*:*"), null);
\`\`\`

From the results, filter by the actual domain/keys generated by the strategy; verify there are two registrations for the two managed objects. The test must manage the context lifecycle and unregister after finishing.

### 14.3. Testing After Context Refresh

If the context recreates beans, the new ObjectName may change. Test **the contract clients actually require**: if clients must use dynamic queries, test queries; if clients must use stable names, identity naming is unsuitable and you should switch to a strategy based on stable resource IDs.

## 15. Common Errors and Diagnostics

| Symptom | Possible Cause | How to Check |
|---|---|---|
| Client does not find fixed ObjectName | Identity-generated name differs from expected | Query actual ObjectNames |
| Dashboard loses data after restart | ObjectName changed | Switch to stable names or dynamic discovery |
| \`InstanceAlreadyExistsException\` | Exporting same object multiple times, collision, or wrong naming config | Check exporters and actual ObjectNames |
| Two beans of same class only show one MBean | Registration policy ignores conflicts | Check \`IGNORE_EXISTING\` and naming |
| Naming strategy configured but name unchanged | Exporter uses explicit ObjectName or bean registered via another path | Check mapping keys, exporter, and naming strategy |
| Name changes when Spring AOP is enabled | Proxy/object named differently | Check the actual exported instance |
| JConsole sees MBean but attributes are wrong | Assembler/metadata error, not naming | Read \`MBeanInfo\` |
| Old MBean remains after context close | Improper unregistration/lifecycle | Track registrations per context |

Do not conclude \`IdentityNamingStrategy\` is "broken" just because the ObjectName does not match a hard-coded expectation. Its nature is to rely on runtime identity.

## 16. Operational Considerations

### 16.1. Dynamic Discovery

If using identity-generated names, consumers should:

1. Connect to the right \`MBeanServer\`.
2. Query using a sufficiently narrow domain/type pattern.
3. Read \`MBeanInfo\` and attributes to identify the managed resource.
4. Use the discovered \`ObjectName\` to operate on it.
5. Detect MBean unregistration/re-registration to refresh the name cache.

Do not save a generated ObjectName as permanent configuration without a discovery mechanism.

### 16.2. Access Control and Security

ObjectNames can be visible in JConsole or logs. Do not attach personal data or secrets to names. Identity naming does not create a security boundary between MBeans; access control must be placed at the management agent, connector, or application policy level.

### 16.3. Monitoring Cardinality

If MBeans are created for thousands of temporary objects, the number of ObjectNames and query/monitoring costs can grow rapidly. Do not use identity naming to arbitrarily export every request/session. Export only management resources with operational value and controlled lifecycles.

### 16.4. Stability for Dashboards

Dashboards typically want to track a **logical resource** across restarts. If identity naming must be used, a discovery/mapping layer from resource ID to current ObjectName is needed. Otherwise, metadata-based or stable key-based naming is usually easier to maintain.

## 17. Practice Exercises

### Exercise A — Comparing Object Identity

Create two objects of the same class whose \`equals()\` returns \`true\`, while \`==\` returns \`false\`. Use \`IdentityNamingStrategy\` to obtain their ObjectNames. Record the names and compare with \`System.identityHashCode\`. Explain why equality is insufficient to distinguish instances.

### Exercise B — Restarting the JVM

Run the identity naming demo twice. Observe the ObjectNames. Comment on the ability to keep names fixed and why dashboards should not hard-code runtime names.

### Exercise C — Comparing Strategies

Using the same two beans, sequentially configure \`IdentityNamingStrategy\`, \`KeyNamingStrategy\`, and names from \`@ManagedResource\`/metadata. Observe the names in \`MBeanServer\`. Choose the appropriate strategy for a long-running queue monitoring system.

### Exercise D — Two ApplicationContexts

Create contexts A and B containing the same \`WorkerStatus\` class. Export into the same \`MBeanServer\` with identity naming. Identify the ObjectNames, close context A, and verify only A's registration is removed. Verify context B still works.

### Exercise E — ResourceNamingStrategy

Using the custom implementation in Section 13, create two managed objects with management names \`orders\` and \`returns\`. Verify names stay stable across initializations and produce clear errors if two objects attempt to register the same resource ID.

## 18. Self-Check Questions

1. How does \`ObjectNamingStrategy\` differ from \`MBeanInfoAssembler\` in responsibility?
2. Why can two different Spring beans still encounter \`InstanceAlreadyExistsException\`?
3. How does object identity differ from \`equals()\`?
4. Is \`System.identityHashCode\` a globally unique identifier?
5. Why are identity-generated ObjectNames usually unsuitable for hard-coding in dashboards?
6. How can Spring AOP proxies affect identity naming?
7. If there are multiple \`ApplicationContext\`s, where is ObjectName uniqueness evaluated?
8. When are \`KeyNamingStrategy\` or \`MetadataNamingStrategy\` more suitable?
9. What must a client do to track an MBean whose name changes after a restart?
10. Does identity naming automatically create access permissions or a remote JMX endpoint?

## 19. References

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework API — \`IdentityNamingStrategy\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/naming/IdentityNamingStrategy.html
- Spring Framework API — \`ObjectNamingStrategy\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/naming/ObjectNamingStrategy.html
- Spring Framework API — \`MBeanExporter\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporter.html
- Java SE 21 API — \`ObjectName\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/ObjectName.html

**Remember:** \`IdentityNamingStrategy\` is a tool for naming by the identity of the managed object to distinguish instances in JMX. It does not represent a durable resource ID. When choosing a strategy, start from the JMX consumer's requirements: does it need to identify a live Java object, or track the same logical resource across multiple deployments?
