# RegistrationPolicy.IGNORE_EXISTING in Spring Framework JMX

## Learning Objectives

After this lesson, you will be able to explain the meaning of \`RegistrationPolicy.IGNORE_EXISTING\` when Spring Framework exports MBeans via \`MBeanExporter\`, determine what happens when an \`ObjectName\` already exists in the \`MBeanServer\`, distinguish the ignore mode from fail and replace modes, configure the policy using Java or XML, verify the instance actually being managed, and design the registration lifecycle to avoid conflicts across Spring \`ApplicationContext\`s.

## 1. Background: One Registration per ObjectName

JMX (Java Management Extensions) manages MBeans registered in an \`MBeanServer\`. Each registration has a \`javax.management.ObjectName\`, for example:

\`\`\`text
com.example.monitoring:type=CacheMonitor,name=primary
\`\`\`

Within **a single MBean server**, two MBeans cannot coexist with the exact same \`ObjectName\`. If a component tries to register a new object under an already-used name, the JMX \`registerMBean\` API normally throws \`InstanceAlreadyExistsException\`.

Spring Framework provides \`MBeanExporter\` to expose Spring beans to the JMX registry. When the exporter encounters a previously registered name, the **registration policy** determines how to handle the conflict:

| Policy | Outcome When Name Already Exists | Consequence |
| --- | --- | --- |
| \`RegistrationPolicy.FAIL_ON_EXISTING\` | Throws an error | Makes duplicate-name misconfigurations easy to detect |
| \`RegistrationPolicy.IGNORE_EXISTING\` | Skips the new registration | The old MBean remains intact |
| \`RegistrationPolicy.REPLACE_EXISTING\` | Replaces the old registration with the new object | Requires understanding ownership and impact on clients |

In Spring Framework versions using the \`RegistrationPolicy\` enum, it resides in the \`org.springframework.jmx.support\` package. The constants \`REGISTRATION_FAIL_ON_EXISTING\`, \`REGISTRATION_IGNORE_EXISTING\`, and \`REGISTRATION_REPLACE_EXISTING\` are integer constants appearing in older APIs/configurations. When writing new code, prefer the enum if supported by your Spring version's API.

## 2. Exact Meaning of IGNORE_EXISTING

\`RegistrationPolicy.IGNORE_EXISTING\` tells the exporter:

> If an MBean is already registered under the desired \`ObjectName\`, do not replace it with the current exporter's MBean and proceed according to the policy.

Key points to remember:

1. **The existing MBean remains the old instance.** Clients reading attributes or invoking operations under that name will continue interacting with the previously registered object.
2. **The new Spring bean can still exist in the \`ApplicationContext\`.** Skipping JMX registration does not destroy or disable the Spring bean.
3. **Does not create two MBeans with the same name.** The registry still holds a single entry for that \`ObjectName\`.
4. **Does not synchronize state between the two beans.** The old MBean does not automatically switch to the new bean's data, and the exporter does not create a merged proxy.
5. **Does not fix a flawed naming strategy.** If you need to manage two instances separately, assign a different \`ObjectName\` to each instance.

Example:

\`\`\`text
Exporter A -> cacheMonitorA -> com.example:type=CacheMonitor,name=primary
Exporter B -> cacheMonitorB -> com.example:type=CacheMonitor,name=primary
\`\`\`

If A registers first and B uses \`IGNORE_EXISTING\`, JMX clients still see \`cacheMonitorA\`; \`cacheMonitorB\` is not exported under this name. That can cause dashboards to show stale metrics or metrics from another context if operators assume B replaced A.

## 3. Standard MBean Example

Create a standard JMX interface and implementation to clearly observe each instance's state.

**CacheMonitorMBean.java**

\`\`\`java
package com.example.jmx;

public interface CacheMonitorMBean {
    String getInstanceId();
    long getHitCount();
    void incrementHits();
}
\`\`\`

**CacheMonitor.java**

\`\`\`java
package com.example.jmx;

import java.util.concurrent.atomic.AtomicLong;

public class CacheMonitor implements CacheMonitorMBean {
    private final String instanceId;
    private final AtomicLong hitCount = new AtomicLong();

    public CacheMonitor(String instanceId) {
        this.instanceId = instanceId;
    }

    @Override
    public String getInstanceId() {
        return instanceId;
    }

    @Override
    public long getHitCount() {
        return hitCount.get();
    }

    @Override
    public void incrementHits() {
        hitCount.incrementAndGet();
    }
}
\`\`\`

This is a Standard MBean following the \`CacheMonitor\` → \`CacheMonitorMBean\` convention. JMX exposes two attributes, \`InstanceId\` and \`HitCount\`, and the \`incrementHits\` operation. The increment operation has a side effect, so only invoke it in test environments or when its impact is understood.

Create two instances to distinguish their data:

\`\`\`java
CacheMonitor first = new CacheMonitor("context-A");
CacheMonitor second = new CacheMonitor("context-B");

first.incrementHits();
first.incrementHits();
second.incrementHits();
\`\`\`

At this point \`first\` has 2 hits while \`second\` has 1. If the JMX registry still holds \`first\`, the \`InstanceId\` attribute will return \`context-A\`, regardless of whether the context containing \`second\` initialized successfully.

## 4. Configuring RegistrationPolicy.IGNORE_EXISTING in MBeanExporter

Java configuration example with Spring Framework:

\`\`\`java
package com.example.jmx;

import java.lang.management.ManagementFactory;
import java.util.Map;
import javax.management.MBeanServer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.support.RegistrationPolicy;

@Configuration
public class JmxIgnoreExistingConfiguration {

    @Bean
    public MBeanServer platformMBeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    public CacheMonitor cacheMonitor() {
        return new CacheMonitor("spring-context-B");
    }

    @Bean
    public MBeanExporter mBeanExporter(
            CacheMonitor cacheMonitor,
            MBeanServer platformMBeanServer) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(platformMBeanServer);
        exporter.setRegistrationPolicy(
                RegistrationPolicy.IGNORE_EXISTING);
        exporter.setBeans(Map.of(
                "com.example.jmx:type=CacheMonitor,name=primary",
                cacheMonitor
        ));
        return exporter;
    }
}
\`\`\`

This configuration states: the exporter wants to expose \`cacheMonitor\` to JMX under the specified name; if the name is already in the server, the exporter skips registering this object.

**If the name does not yet exist**, the exporter still registers the new bean normally. \`IGNORE_EXISTING\` does not mean skipping all beans; it only changes behavior when a conflict occurs.

**If the name already exists**, the existing registered object is kept. Even though the \`ApplicationContext\` still contains the \`cacheMonitor\` from the new configuration, the values read by JMX clients under that name belong to the old MBean.

## 5. Simulating a Conflict with MBeanServer in the Same JVM

For an observable hands-on example, pre-register an MBean on the platform server and then create a Spring context using the IGNORE policy.

\`\`\`java
package com.example.jmx;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class IgnoreExistingDemo {

    public static void main(String[] args) throws Exception {
        MBeanServer server = ManagementFactory.getPlatformMBeanServer();
        ObjectName name = new ObjectName(
                "com.example.jmx:type=CacheMonitor,name=primary");

        CacheMonitor existing = new CacheMonitor("existing-owner");
        existing.incrementHits();
        existing.incrementHits();

        server.registerMBean(existing, name);

        try {
            try (var context = new AnnotationConfigApplicationContext(
                    JmxIgnoreExistingConfiguration.class)) {

                CacheMonitor candidate = context.getBean(CacheMonitor.class);
                candidate.incrementHits();

                System.out.println("Spring instance: "
                        + candidate.getInstanceId());

                System.out.println("JMX registered: "
                        + server.isRegistered(name));

                System.out.println("JMX instance: "
                        + server.getAttribute(name, "InstanceId"));

                System.out.println("JMX hits: "
                        + server.getAttribute(name, "HitCount"));
            }

            System.out.println("After Spring context closes: "
                    + server.isRegistered(name));
        } finally {
            if (server.isRegistered(name)) {
                server.unregisterMBean(name);
            }
        }
    }
}
\`\`\`

Expected output:

\`\`\`text
Spring instance: spring-context-B
JMX registered: true
JMX instance: existing-owner
JMX hits: 2
After Spring context closes: true
\`\`\`

Importantly, the JMX results belong to the pre-registered MBean. In a normal setup, an exporter that ignores an existing registration should not treat it as an MBean it created and should not unregister it when the context closes. Having explicit cleanup in the demo prevents leaving test MBeans behind after completion.

The example above is suitable for an isolated test environment. If that name is already used by another application in the same JVM, the first \`registerMBean\` call will report a collision; do not use the cleanup block to delete a registration that does not belong to the test.

## 6. Distinguishing IGNORE_EXISTING from FAIL_ON_EXISTING and REPLACE_EXISTING

Comparing the three strategies side by side:

### FAIL_ON_EXISTING

\`\`\`java
exporter.setRegistrationPolicy(
        RegistrationPolicy.FAIL_ON_EXISTING);
\`\`\`

When the name already exists, the exporter reports a registration error. This is usually useful in environments requiring strict configuration: conflicts are detected early instead of silently using another instance.

### IGNORE_EXISTING

\`\`\`java
exporter.setRegistrationPolicy(
        RegistrationPolicy.IGNORE_EXISTING);
\`\`\`

When the name already exists, the exporter skips the new bean at that name and continues. This strategy is useful when multiple contexts or modules can provide a complementary MBean, and the presence of a prior registration is acceptable.

### REPLACE_EXISTING

\`\`\`java
exporter.setRegistrationPolicy(
        RegistrationPolicy.REPLACE_EXISTING);
\`\`\`

When the name already exists, the exporter replaces the old MBean with the new MBean. This can change the target object monitored by management tools, switching metrics/operations to a different instance. You must clearly understand who owns the registration and what happens when the old or new context closes.

| Question | FAIL | IGNORE | REPLACE |
| --- | --- | --- | --- |
| Clearly detects conflicts? | Yes, via error | May log, but does not force stop | May alter the registration |
| Does the old instance remain the MBean? | Yes, until old owner unregisters | Yes | No, after replacement succeeds |
| Is the new instance registered under the colliding name? | No | No | Yes |
| Suitable for keeping both instances simultaneously? | No | No | No |

If the requirement calls for monitoring two separate instances, create two distinct \`ObjectName\`s. A registration policy is not a substitute for a naming strategy.

## 7. Scenarios for Using IGNORE_EXISTING

### 7.1. Multiple ApplicationContexts Sharing One JVM

An application may have a root context and a child context. Both use the same platform \`MBeanServer\`, and shared configuration inadvertently exports the same \`ObjectName\`.

Using \`IGNORE_EXISTING\` on the second context can prevent startup errors, but does not expose that context's bean under the colliding name. This is only appropriate if you genuinely want to keep the existing MBean.

### 7.2. Optional Module Providing a Fallback MBean

An auxiliary module may want to register a management MBean when the primary module has not provided one. If the primary MBean already exists, the auxiliary module does not need to replace it. \`IGNORE_EXISTING\` can express this intent.

Ensure that the management contract of the existing MBean matches how monitoring tools use that name. Simply sharing an \`ObjectName\` does not guarantee two implementations provide the same attributes or operations.

### 7.3. Test Environments or Application Contexts Initialized Multiple Times

In integration tests, multiple contexts sharing the platform server can cause conflicts. \`IGNORE_EXISTING\` makes tests easier to start, but risks having tests read an MBean left over from a previous run.

In tests that must prove the right bean was exported, use an isolated MBean server, test-specific names, and proper cleanup instead of relying on the IGNORE policy to mask conflicts.

### 7.4. Rolling Context Replacement in the Same Process

When a new context is built before the old context closes, both exporters may pick the same \`ObjectName\`. Using IGNORE prevents the new context from replacing the old MBean during the overlap period. After the old context unregisters the MBean, do not assume the new exporter will automatically re-register the skipped object.

Therefore, IGNORE is usually unsuitable if the goal is to reliably hand over MBean ownership to the new context. A handover procedure, a new name, or an explicit re-registration mechanism is needed.

## 8. MBean Lifecycle and Ownership

This is the most critical part when using IGNORE. An exporter should only manage the lifecycle of registrations it actually created or replaced according to its policy. If it ignores an existing name, that registration belongs to the original registering component.

Model:

\`\`\`text
Time T1:
  Context A / Exporter A
    register ObjectName X -> MBean A

Time T2:
  Context B / Exporter B (IGNORE_EXISTING)
    register ObjectName X -> detects existing
    skips registering MBean B

Registry at T2:
  X -> MBean A

Time T3:
  Context B closes
    no new registration X from B to remove

Time T4:
  Context A closes
    MBean A is unregistered by owner A

Registry at T4:
  X is gone, MBean B does not appear automatically
\`\`\`

The operational implication is that “context B initialized successfully” does not mean “JMX has switched to managing bean B”. If automation monitors JMX name X, it may keep reading MBean A until A closes, after which name X disappears.

When choosing IGNORE, clearly answer: Which MBean is allowed to keep the name? Who is responsible for unregistering? Is a re-registration step needed after the old owner stops?

## 9. Reading the Actual MBean to Avoid Instance Confusion

Do not check only \`server.isRegistered(name)\`. That call returns \`true\` even if the new exporter skipped registration. To know which object is actually managed, expose an instance-identifying attribute or inspect appropriate metadata.

Example:

\`\`\`java
MBeanServer server = ManagementFactory.getPlatformMBeanServer();
ObjectName name = new ObjectName(
        "com.example.jmx:type=CacheMonitor,name=primary");

if (server.isRegistered(name)) {
    Object instanceId = server.getAttribute(name, "InstanceId");
    System.out.println("Registry owner instance = " + instanceId);
}
\`\`\`

Compare \`InstanceId\` against the expected logical identity, such as context name, shard, or pool. Do not use secrets or personal data as display identifiers.

You can inspect metadata:

\`\`\`java
var info = server.getMBeanInfo(name);
System.out.println(info.getClassName());

for (var attribute : info.getAttributes()) {
    System.out.println(attribute.getName());
}

for (var operation : info.getOperations()) {
    System.out.println(operation.getName());
}
\`\`\`

Metadata helps verify whether the existing MBean has a matching contract. However, having the same class and interface is still not sufficient proof of the right instance. When distinguishing multiple objects of the same type, a logical identifying attribute and a stable \`ObjectName\` are very useful.

## 10. XML Configuration with registrationPolicy

Spring projects using XML can configure the registration policy on the exporter bean. Example:

\`\`\`xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
         http://www.springframework.org/schema/beans
         https://www.springframework.org/schema/beans/spring-beans.xsd">

    <bean id="cacheMonitor"
          class="com.example.jmx.CacheMonitor">
        <constructor-arg value="xml-context"/>
    </bean>

    <bean id="mBeanExporter"
          class="org.springframework.jmx.export.MBeanExporter">

        <property name="registrationPolicy" value="IGNORE_EXISTING"/>

        <property name="beans">
            <map>
                <entry
                    key="com.example.jmx:type=CacheMonitor,name=primary"
                    value-ref="cacheMonitor"/>
            </map>
        </property>
    </bean>
</beans>
\`\`\`

The example does not specify \`server\`; the exporter uses Spring/runtime's \`MBeanServer\` lookup mechanism. To be sure a specific server is used, declare an \`MBeanServer\` bean and inject it into the \`server\` property.

For configurations using the \`RegistrationPolicy\` enum, Spring can convert the string \`IGNORE_EXISTING\` to the enum during property binding. Check your Spring Framework version and actual API when implementing.

## 11. IGNORE_EXISTING and MBeanExporterListener

\`MBeanExporter\` supports callback/lifecycle mechanisms related to registration. If the application needs to inventory which registrations were created and which names were skipped, observe logs and appropriate exporter callbacks, or record state from a separate orchestration component.

However, do not assume a registration listener is invoked for the **ignored** case when no actual new registration occurs. To verify the final outcome, inspect the \`MBeanServer\` after exporter initialization and check the identifying info of the existing MBean.

If you want warnings when a conflict is ignored, design a health check or startup check comparing the expected identity against the identity in JMX. \`IGNORE_EXISTING\` is only a registration-layer conflict policy, not an ownership auditing system.

## 12. Common Pitfalls

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Spring context starts successfully, but JMX shows old metrics | IGNORE keeps the pre-existing MBean | Check \`InstanceId\`, owner, and \`ObjectName\` |
| \`isRegistered(name)=true\` yet the new bean is missing | Name already existed and exporter skipped it | Read identifying attribute; do not rely solely on \`isRegistered\` |
| MBean disappears after old context closes | New context skipped it and did not re-register | Design a handover or use a different name |
| Both instances need to be monitored simultaneously | Sharing the same \`ObjectName\` | Add \`name\`, \`pool\`, \`tenant\`, or another distinguishing key |
| No duplicate-name error so replacement was assumed | IGNORE does not fail registration like FAIL | Inspect the registry and actual instance |
| Test suite suffers from state pollution | Tests share the platform \`MBeanServer\` | Isolate the server or use test-specific names |
| Changed policy but saw no difference | Old context still running, old registration remains | Inspect lifecycle and current registry |
| Client does not see expected operations | Old MBean has a different contract | Read \`MBeanInfo\`, identify owner |
| Multiple JVMs share the same JMX name | Uniqueness is only per MBean server | Match JVM/PID and connection endpoint |

When troubleshooting, a sound investigation order is: confirm the right JVM/server, read the full \`ObjectName\`, check the exporter policy, verify whether a registration already existed, and compare the actual instance.

## 13. Procedure for Testing IGNORE_EXISTING

In integration tests, use an isolated \`MBeanServer\` to avoid touching the platform registry of other tests:

\`\`\`java
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;

MBeanServer testServer =
        MBeanServerFactory.createMBeanServer("test-jmx");

try {
    // 1. Register MBean A under ObjectName X.
    // 2. Create Spring context/exporter B using the same testServer.
    // 3. Set RegistrationPolicy.IGNORE_EXISTING.
    // 4. Ensure context B initializes successfully.
    // 5. Read identifying attribute and verify registry still points to A.
    // 6. Close context B, verify A remains registered.
    // 7. Unregister A in controlled cleanup.
} finally {
    MBeanServerFactory.releaseMBeanServer(testServer);
}
\`\`\`

Key assertions:

- Name X was already registered before exporter B ran.
- After B initializes, the registry still returns A's instance ID.
- Bean B still exists in the Spring \`ApplicationContext\`.
- After closing B, registration A still exists.
- After owner A unregisters, name X does not automatically switch to B.

The test fixture must inject **the exact \`testServer\`** into exporter B. If exporter B uses the platform server while the test checks \`testServer\`, the results will not reflect the policy under test.

### Testing Behavior When No Registration Exists Yet

Another test should start with an empty server and initialize an exporter with \`IGNORE_EXISTING\`. In this case, the registry must contain that exporter's MBean. This test proves “IGNORE_EXISTING only skips names that already exist”, rather than stopping the exporter from registering any MBeans.

## 14. When to Choose and Not Choose IGNORE_EXISTING?

**Appropriate when:**

- An existing MBean is considered a valid and preferred management source.
- The new component only provides a fallback/optional registration.
- The goal is to avoid name collisions at an integration point with clearly defined ownership.
- The existing registration's MBean contract is confirmed to match client expectations.

**Inappropriate when:**

- Both instances need to be managed simultaneously under separate identities.
- The new context must replace the old context in a formal handover workflow.
- Having the wrong MBean instance risks dashboards, automation, or operators reading wrong data.
- You need to detect duplicate-name configurations as early as possible.
- The test goal is to confirm the new bean was exported, yet the policy could preserve an MBean from a previous test.

In those cases, use \`FAIL_ON_EXISTING\`, assign unique \`ObjectName\`s, or design an explicit replacement/ownership workflow depending on the goal.

## 15. Hands-On Exercise

**Exercise 1 — Two exporters:** create two \`MBeanExporter\`s sharing a server, using the same \`ObjectName\` but different \`CacheMonitor\` instance IDs. Exporter A registers first; exporter B uses \`IGNORE_EXISTING\`. Verify clients still read instance A.

**Exercise 2 — Comparing policies:** run three independent scenarios with \`FAIL_ON_EXISTING\`, \`IGNORE_EXISTING\`, and \`REPLACE_EXISTING\`. Record registry state, which instance receives calls, and startup outcome.

**Exercise 3 — Lifecycle:** close context B (which ignored) and then close context A. Verify the JMX name disappears after A unregisters and B does not automatically replace it.

**Exercise 4 — Two distinct names:** change B's name to \`com.example.jmx:type=CacheMonitor,name=secondary\`, keeping \`IGNORE_EXISTING\`. Confirm both A and B appear because there is no longer a name conflict.

**Exercise 5 — Spring Test:** use JUnit Jupiter and \`AnnotationConfigApplicationContext\` with an isolated test server. Assert that bean B exists in the context while the \`InstanceId\` value via JMX still belongs to A after exporter B ignores registration.

## Conclusion

\`RegistrationPolicy.IGNORE_EXISTING\` allows \`MBeanExporter\` to proceed when an \`ObjectName\` is already registered, **keeping the existing MBean and skipping the new bean at that name**. This policy is useful when a prior registration takes precedence, but it does not create an extra instance, synchronize state, or automatically transfer ownership when the old context stops. When deploying Spring Framework JMX, distinguish \`ApplicationContext\` startup success from which MBean is actually exposed, and verify the \`ObjectName\`, instance identity, and lifecycle of each exporter.
