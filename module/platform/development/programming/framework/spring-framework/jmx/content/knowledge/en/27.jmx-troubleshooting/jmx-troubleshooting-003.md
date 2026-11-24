# Diagnosing Duplicate ObjectNames on Startup or Redeploy in Spring Framework JMX

## 1. Symptoms and Objectives

In Spring Framework JMX, `MBeanExporter` registers a Spring-managed bean into an `MBeanServer` under an `ObjectName`. When a name is already occupied by an existing MBean, attempting to register another MBean with the same name will fail or behave according to the active registration policy. This situation commonly appears during startup, context restart, hot reload, or application redeployment within the same JVM.

Related messages may include `javax.management.InstanceAlreadyExistsException`, `UnableToRegisterMBeanException`, the duplicate `ObjectName`, and stack traces from Spring's `MBeanExporter`/`MBeanRegistrationSupport`. Some systems do not report a startup error, yet the new MBean does not appear because `RegistrationPolicy.IGNORE_EXISTING` skips registration; this is also a symptom that requires diagnosis.

This lesson guides you to:

- Understand the uniqueness boundary of an ObjectName within each MBeanServer.
- Distinguish name collisions caused by **two active exporters**, by **a leftover old MBean after redeploy**, and by **incorrect name generation**.
- Inspect the actual ObjectName in the registry rather than guessing from the Spring bean name.
- Resolve safely through naming conventions, ownership, and lifecycle cleanup.
- Choose a `RegistrationPolicy` without hiding bugs or accidentally replacing another application's MBean.
- Prevent memory leaks, classloader leaks, and stale monitoring data after redeployment.

**Handling principle:** Do not blindly call `unregisterMBean` or turn on `REPLACE_EXISTING` just to get through startup. First determine who owns the existing MBean and why it has not been cleaned up.

## 2. ObjectName Must Be Unique Within a Single MBeanServer

ObjectName syntax:

```text
domain:key1=value1,key2=value2,...
```

For example:

```text
com.example.jobs:type=WorkerPool,name=Main
```

Within **one** MBeanServer, only one MBean can be registered under this name. However, across two different JVMs or two different MBeanServers, the same name can coexist without a registry conflict.

| Scenario | Can Registry Collision Occur? |
| --- | --- |
| Two MBeanExporters in the same Spring context, same server, same ObjectName | Yes |
| Parent and child ApplicationContexts both registering an MBean to the platform MBeanServer | Yes |
| Two WARs in the same app server sharing an MBeanServer | Yes |
| Old version failed to unregister and new version registers the same name | Yes |
| Two independent JVMs with the same name using separate MBeanServers | No direct conflict |
| Two different MBeanServers in the same JVM | No collision in the same registry, though it can confuse clients |

Do not use the Spring bean name, such as `workerPool`, to infer collisions. The decision rests on the final ObjectName: two differently named Spring beans can still be exported under a single ObjectName.

## 3. Common Failure Flow on Redeploy

```text
First deployment
  ApplicationContext A
       |
       +-- MBeanExporter -> register ObjectName X
       |                         |
       |                         v
       |                      MBeanServer
       |
       +-- shutdown/redeploy
              |
              +-- expected: unregister X
              +-- bug: X still registered

Second deployment
  ApplicationContext B
       |
       +-- MBeanExporter -> register ObjectName X
                                  |
                                  v
                     InstanceAlreadyExistsException
```

Not every duplicate-name case is caused by a failed unregistration. The new deployment may also instantiate **two exporters** during the same startup, or a single exporter may receive two beans whose naming strategy produces the same name. Therefore, you must distinguish **collision on initial startup** from **collision only after restart/redeploy**.

## 4. Symptoms That Help Isolate the Cause

| Symptom | Primary Suspect |
| --- | --- |
| Fails on initial startup | Two exporters/beans share an ObjectName, or a platform MBean already claims the name |
| First startup succeeds, second redeploy fails | Cleanup/unregister did not run or the registry still holds an old MBean |
| Occurs only when `@EnableMBeanExport` is enabled | Annotation-based exporter collides with manual/XML exporter |
| Occurs only under one profile | Naming/domain configuration or bean definitions differ across profiles |
| No exception thrown, but MBean shows stale data | `IGNORE_EXISTING` keeps the old MBean |
| Always shows the new version's MBean, while another app loses its MBean | `REPLACE_EXISTING` may be enabled |
| Two environments in two separate JVMs use the same name | Not a direct collision if servers are separate |
| JConsole sees the MBean, but code `isRegistered` returns false | Connected to a different MBeanServer or wrong ObjectName |

## 5. Reading the Root Cause from Logs

Illustrative stack trace:

```text
org.springframework.jmx.export.UnableToRegisterMBeanException:
  Unable to register MBean [workerPoolManagement]
  with key 'com.example.jobs:type=WorkerPool,name=Main'
Caused by: javax.management.InstanceAlreadyExistsException:
  com.example.jobs:type=WorkerPool,name=Main
```

Record three details: **the duplicate ObjectName**, **the exporter/context performing registration**, and **the target MBeanServer**. Do not simply spot `InstanceAlreadyExistsException` and immediately rename it. Determine whether the error occurs on initial registration, after a reload, or when multiple modules initialize concurrently.

In logs, exact message wording may vary by Spring Framework/JDK version. What matters is the exception chain, the ObjectName, and the lifecycle phase.

## 6. Finding the Existing MBean with the JMX API

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "com.example.jobs:type=WorkerPool,name=Main"
);

System.out.println("registered=" + server.isRegistered(name));

if (server.isRegistered(name)) {
    MBeanInfo info = server.getMBeanInfo(name);
    System.out.println("class=" + info.getClassName());
    System.out.println("attributes=" + info.getAttributes().length);
    System.out.println("operations=" + info.getOperations().length);
}
```

This snippet assumes the exporter uses the platform MBeanServer. If the application has a dedicated MBeanServer, use that exact instance or corresponding `MBeanServerConnection`. MBeanInfo reveals the registered contract, though it does not always pinpoint the exact application/classloader owner, especially with ModelMBeans or AOP proxies.

You can query by domain:

```java
import java.util.Set;

Set<ObjectName> names = server.queryNames(
    new ObjectName("com.example.jobs:*") ,
    null
);
for (ObjectName item : names) {
    System.out.println(item.getCanonicalName());
}
```

Do not read all attribute values just to diagnose a name collision: some getters may return secrets/PII or perform heavy work. Metadata and the canonical name are usually enough for the first step.

## 7. Checking Canonical Names to Avoid Key-Order Confusion

```text
com.example.jobs:type=WorkerPool,name=Main
com.example.jobs:name=Main,type=WorkerPool
```

These two strings describe the same ObjectName. Key property order does not change JMX identity.

```java
ObjectName a = new ObjectName(
    "com.example.jobs:type=WorkerPool,name=Main"
);
ObjectName b = new ObjectName(
    "com.example.jobs:name=Main,type=WorkerPool"
);
System.out.println(a.equals(b)); // true
System.out.println(a.getCanonicalName());
```

If a naming strategy produces two strings in different orders with the same keys and values, they still collide. You should also check case differences and values quoted via `ObjectName.quote`.

## 8. Checking Sources of MBeanExporter

A Spring application can have multiple JMX infrastructures:

- `@EnableMBeanExport` creates an annotation-based exporter.
- A Java `@Bean` manually instantiates `MBeanExporter` and calls `setBeans(...)`.
- XML `<context:mbean-export/>` or `<bean class="org.springframework.jmx.export.MBeanExporter">`.
- Another framework/module or application server registers its own MBeans.
- Spring Boot Actuator has a JMX endpoint exporter in addition to custom MBeans.

Running multiple mechanisms is not automatically an error; the error occurs when they register **the same ObjectName on the same MBeanServer**. Design clear ownership: each MBean should have one responsible exporter.

Example anti-pattern: the same context uses `@EnableMBeanExport` while also configuring a manual exporter to export the same adapter under the same name. In that case, one infrastructure may already register the target before the other attempts registration.

Do not disable all JMX exports to dodge the error if the system still needs monitoring. Eliminate the duplicate registration or separate the ObjectNames clearly.

## 9. RegistrationPolicy: Behavior When a Name Already Exists

Spring supports `org.springframework.jmx.support.RegistrationPolicy`:

| Policy | When an MBean with the Same ObjectName Is Registered | Things to Note |
| --- | --- | --- |
| `FAIL_ON_EXISTING` | Throws an error instead of replacing | Helps surface unexpected collisions |
| `IGNORE_EXISTING` | Keeps the old MBean, skips the new registration | New application may lack its own MBean; data may be stale |
| `REPLACE_EXISTING` | Replaces the registered MBean with the new one | Risk of hijacking another application's endpoint |

Example:

```java
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.support.RegistrationPolicy;

@Bean
public MBeanExporter exporter(WorkerPoolManagement management) {
    MBeanExporter exporter = new MBeanExporter();
    exporter.setBeans(Map.of(
        "com.example.jobs:type=WorkerPool,name=Main",
        management
    ));
    exporter.setRegistrationPolicy(
        RegistrationPolicy.FAIL_ON_EXISTING
    );
    return exporter;
}
```

`FAIL_ON_EXISTING` is a good choice for exposing issues rather than hiding conflicts. With `IGNORE_EXISTING`, verify that the existing MBean is actually one the client is allowed to use. With `REPLACE_EXISTING`, establish clear ownership and a replacement plan; do not pick it simply so "redeploy stops failing."

## 10. Distinguishing Naming Collisions from Lifecycle Leaks

### 10.1. Naming collision

Two different services accidentally use a shared name:

```text
com.example:type=Cache,name=Main
```

Fix using distinct namespaces:

```text
com.example.billing:type=Cache,name=Main
com.example.shipping:type=Cache,name=Main
```

Or add a key:

```text
com.example.services:application=billing,type=Cache,name=Main
com.example.services:application=shipping,type=Cache,name=Main
```

### 10.2. Lifecycle leak after redeploy

The old application stopped, but the old MBean remains in the shared server. You must fix unregistration/cleanup of the old owner. If the MBean retains references to classes from the old WAR, it can prevent garbage collection of the classloader.

### 10.3. Double registration

The same target is exported via two `MBeanExporter` instances, or registered both through direct JMX API calls and through Spring. Choose a single owner; do not double-register.

### 10.4. Wrong MBeanServer

Exporter A uses the platform server, while Exporter B uses a dedicated server. Two servers having the same ObjectName do not collide; if logs or management tools inspect the other server, you might misdiagnose "already exists" or "does not exist."

## 11. Cleanup When the Spring Context Closes

`MBeanExporter` manages the lifecycle of the MBeans it exports and normally unregisters them when the Spring context closes properly. However, problems can arise if:

- The context is not closed during redeploy/hot reload.
- An MBean was registered manually without a matching unregistration.
- A bean was created in a secondary context whose owning context did not shut down properly.
- Multiple exporters obscure ownership of the same ObjectName.
- A shared MBeanServer retains MBeans from an old application.
- The process terminated abnormally: if the JVM dies completely, its registry disappears as well; the "leftover old MBean" problem only applies if the JVM/server stays alive.

For containers running multiple WARs in the same JVM, observe the lifecycle of the individual WAR rather than confusing it with a full JVM restart.

## 12. Manual MBean Management Must Have Matching Unregistration

Plain JMX example:

```java
import javax.management.MBeanServer;
import javax.management.ObjectName;

public final class RegistrationOwner implements AutoCloseable {
    private final MBeanServer server;
    private final ObjectName name;
    private boolean owned;

    public RegistrationOwner(
            MBeanServer server, ObjectName name) {
        this.server = server;
        this.name = name;
    }

    public synchronized void register(Object mbean) throws Exception {
        if (owned) {
            throw new IllegalStateException("Already registered by owner");
        }
        server.registerMBean(mbean, name);
        owned = true;
    }

    @Override
    public synchronized void close() throws Exception {
        if (owned) {
            server.unregisterMBean(name);
            owned = false;
        }
    }
}
```

This code illustrates ownership for a single lifecycle owner. The MBean must be an appropriate Standard MBean/MXBean/DynamicMBean. If another component can replace the name between register and close, tracking only a boolean `owned` is insufficient to prove the current object still belongs to this owner; in shared-server systems, unauthorized replacement must be prevented or ownership coordinated more explicitly.

Do not use this example to unregister a pre-existing MBean when this owner never successfully registered it.

## 13. Check-Then-Register Does Not Eliminate Race Conditions

Anti-pattern:

```java
if (!server.isRegistered(name)) {
    server.registerMBean(bean, name);
}
```

Two threads or two exporters can both observe `false`, after which only one succeeds in registering. `isRegistered` is a snapshot check; it does not lock the registry to reserve the name.

Therefore:

- Let the `registerMBean` operation decide duplicates and handle the specific exception.
- Design unique naming from the start.
- Coordinate ownership when an MBean must be a singleton in a shared server.
- Avoid looping register/unregister retries to "fight over the name."

If an old MBean is still actively being served, deleting it to make room for a new MBean can corrupt data and break clients using the old endpoint.

## 14. Startup and Shutdown Ordering

Some errors occur only when modules run concurrently:

```text
Module A start ------ register X ------ OK
Module B start ------ register X ------ collision
```

With redeploy:

```text
Old module stop ------ unregister X (expected)
New module start ----- register X
```

If the unregistration step has not completed or does not happen, an error can occur. Do not merely add sleep delays or increase timeouts to mask the issue. Determine the server/container lifecycle sequence and ensure the old owner stops before the new owner registers the same name.

When using Spring `@DependsOn`, you can control bean initialization order within **one** context, but do not treat it as an ownership coordination mechanism between two independent contexts or two WARs.

## 15. MBeanInfo and Classloader Leaks

An old MBean persisting after redeploy can retain object references to the old application's implementation, annotation metadata, listeners, or classloader. Symptoms include:

- JConsole still shows the ObjectName even after the old WAR is undeployed.
- MBeanInfo shows old descriptions/classes or stale data.
- Memory usage climbs after repeated redeployments.
- Class loading/serialization errors from JMX clients.
- Old listeners continue receiving notifications or calling into stopped resources.

To avoid leaks:

1. Use an exporter/lifecycle owner managed by Spring.
2. Ensure `ApplicationContext.close()`/shutdown hooks or container lifecycle callbacks execute.
3. Remove notification listeners registered by the application itself.
4. Shut down executors or background tasks associated with MBeans.
5. Do not hold static references to application objects in server/global registries.

Do not rely on GC to automatically unregister MBeans. MBeanServer holds strong references to registered objects until they are unregistered or the server is destroyed.

## 16. Diagnosing an Old MBean with an Unknown Owner

Controlled investigation workflow:

1. Confirm the right JVM/MBeanServer from logs and tooling.
2. Obtain the canonical ObjectName that exists.
3. Read MBeanInfo safely; do not dump all attribute values.
4. Search the app configuration for where that name's exporter/naming is declared.
5. Identify which context/application/version registered it in the lifecycle.
6. Check whether there is a duplicate exporter or manual `registerMBean` call.
7. Inspect shutdown hooks/undeploy logs to determine whether unregistration ran.
8. Only after verifying ownership should you decide to unregister/redeploy or fix naming.

You can add non-sensitive management attributes such as `ApplicationId`, `DeploymentVersion`, or `InstanceId` to the management adapter for diagnostics, though it is optional and must never expose credentials or personal data.

## 17. Choosing Stable Names Across Multiple Applications

ObjectNames should distinguish:

- `application`: application/microservice when sharing a server.
- `type`: MBean type.
- `name`: role or component.
- `instance`: only when multiple instances on the same server require distinct names.

For example:

```text
com.example.services:application=billing,type=Queue,name=Main
com.example.services:application=shipping,type=Queue,name=Main
```

You do not necessarily need to append a PID, timestamp, or random UUID to the name on every deployment; clients and dashboards usually need stable ObjectNames. If replicas run in separate JVMs, the same ObjectName can be used in each server without conflict.

## 18. Avoiding Breaking Monitoring When Fixing Names

When changing an ObjectName to resolve a collision, the following clients may be affected:

- `MBeanProxyFactoryBean` configured with `setObjectName(...)`.
- JMX collectors querying by a specific domain/key.
- JConsole bookmarks or `getAttribute/invoke` scripts.
- Alert rules and dashboards.
- Notification listener registrations.

Thus, a naming fix is a management API change. Synchronize client/server configurations and plan an appropriate migration. Do not arbitrarily change the domain on each start just to eliminate duplicate errors if you can fix the underlying ownership/lifecycle instead.

## 19. Mistakes to Avoid

| Mistake | Why It Is Dangerous |
| --- | --- |
| Switching every exporter to `IGNORE_EXISTING` | New app may fail to export while monitoring keeps reading stale data |
| Using `REPLACE_EXISTING` by default in production | Can hijack another app's endpoint and break lifecycle |
| Calling `unregisterMBean` on every colliding name at startup | Deletes an MBean you do not own |
| Reordering key properties | Both ObjectNames remain equal |
| Adding `Thread.sleep` before registering | Masks the race condition without solving ownership |
| Assuming bean name equals ObjectName | Naming strategy may produce a different name |
| Testing only cold starts | Misses leaks and hot-reload issues |
| Dumping all attributes into logs | Can leak secrets and trigger heavy getters |
| Looking at only one JMX connection | May be inspecting the wrong server/JVM |

## 20. Operational Checklist

- [ ] Identify the exporter's target MBeanServer.
- [ ] Identify the colliding canonical ObjectName.
- [ ] Distinguish cold-start errors from post-redeploy errors.
- [ ] Locate all exporters/manual registrations for the ObjectName.
- [ ] Check parent-child contexts, WARs/modules, and Boot Actuator if applicable.
- [ ] Confirm which owner owns the existing MBean before unregistering.
- [ ] Use `FAIL_ON_EXISTING` in cases where conflicts must be surfaced.
- [ ] Design a sensible application/type/name/instance namespace.
- [ ] Ensure context shutdown and exporter unregistration follow the lifecycle properly.
- [ ] Remove listeners, stop executors, and clean up references after redeploy.
- [ ] Update JMX clients if the name changes.
- [ ] Test both cold start and repeated redeployments in a test environment.

## 21. Quick Triage Model

```text
Startup / redeploy throws InstanceAlreadyExistsException
                    |
                    v
            Confirm MBeanServer
                    |
                    v
             Canonical ObjectName
                    |
                    v
           Query registered MBean
                    |
          +---------+----------+
          |                    |
   Existing active owner    Old stale registration
          |                    |
   Fix naming / one owner   Fix shutdown / unregister
          |                    |
          +---------+----------+
                    |
          Verify stable registration
                    |
              Update clients if renamed
```

**Conclusion:** Duplicate-name errors during startup or redeployment must be treated as an **ObjectName identity + MBeanServer scope + lifecycle ownership** issue. Confirm the existing MBean on the right server, distinguish duplicate exporters from stale registrations, fix naming or root cleanup, and only unregister/replace once ownership is verified. `RegistrationPolicy` controls registration-time behavior—it is not a substitute for namespace design and lifecycle management.
