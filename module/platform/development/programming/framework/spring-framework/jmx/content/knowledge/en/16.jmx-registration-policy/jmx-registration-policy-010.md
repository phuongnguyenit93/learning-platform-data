# Choosing an MBean Registration Policy by Environment and Safety Level

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain **registration policy** in Spring Framework JMX and why duplicate `ObjectName`s can cause MBean export to fail.
- Distinguish the three `RegistrationPolicy` options: `FAIL_ON_EXISTING`, `IGNORE_EXISTING`, and `REPLACE_EXISTING`.
- Evaluate each policy by **environment** (local, test, staging, production) and **safety level** (avoiding claiming another MBean's name, lifecycle stability, preserving the management contract).
- Understand that registration policy only governs **registration-time conflict handling**, not authentication, authorization, or transaction rollback.
- Design conventions for `ObjectName` ownership, exporters, MBeanServers, and unregistration lifecycles.
- Write Spring configurations and integration tests to detect conflicts instead of masking bugs.
- Plan controlled MBean replacements when upgrading implementations or metadata.

## 2. Background: Why Can MBean Registration Conflict?

In Java Management Extensions (JMX), an MBean is registered with an `MBeanServer` under a specific `ObjectName`:

```text
com.example.shop.orders:type=Queue,name=outbox
```

Within **one MBeanServer**, two MBeans cannot simultaneously hold the same specific ObjectName. If a bean already exists and code registers another bean under the same name, JMX normally throws `InstanceAlreadyExistsException`.

In Spring, `MBeanExporter` exposes Spring beans to the MBeanServer. When a conflict occurs, the exporter can apply a **registration policy** to decide whether to fail, skip the new bean, or replace the currently registered bean.

Example diagram:

```text
Spring ApplicationContext
    |
    +-- Exporter A --> QueueMonitor A
    |                    |
    |                    v
    |       com.example.shop.orders:type=Queue,name=outbox
    |
    +-- Exporter B --> QueueMonitor B
                         |
                         v
              same ObjectName, same MBeanServer
                         |
                         v
                  REGISTRATION CONFLICT
```

Conflicts can come from two exporters, two beans annotated with `@ManagedResource` sharing a name, auto-configuration combined with manual mappings, or an MBean instance already present in the MBeanServer.

**Decision question:** When a conflict is detected, should the application **halt and report a misconfiguration**, **keep the existing MBean**, or **replace the old MBean**?

## 3. Three Registration Policies in Spring

Spring provides the `org.springframework.jmx.support.RegistrationPolicy` enum with three common policies:

| Policy | When ObjectName Is Not Yet Registered | When ObjectName Already Exists | Operational Meaning |
|---|---|---|---|
| `FAIL_ON_EXISTING` | Registers new bean | Fails registration | Detects duplicate configuration; prioritizes clarity |
| `IGNORE_EXISTING` | Registers new bean | Keeps existing MBean, skips new registration | Avoids disrupting the existing MBean |
| `REPLACE_EXISTING` | Registers new bean | Attempts to replace existing MBean with new MBean | Intentionally transfers ObjectName ownership |

This describes the policy semantics when the Spring exporter handles an already-occupied ObjectName. Exact exception and lifecycle details still depend on the MBeanServer, MBean type, exporter configuration, and Spring version.

### 3.1. FAIL_ON_EXISTING

This is the **fail-fast** approach: conflicts are surfaced rather than hidden.

```text
ObjectName does not exist -> register
ObjectName already exists  -> fail
```

It fits when an ObjectName requires a single owner and a duplicate name is a configuration error that must be fixed. In test, staging, or production environments with strict management-contract requirements, fail-fast prevents dashboards from connecting to the wrong MBean.

**Note:** A JMX registration error can cause Spring context startup to fail depending on how the exporter/bean lifecycle handles exceptions. This is a trade-off to weigh if JMX is not business-critical.

### 3.2. IGNORE_EXISTING

If the name already exists, the exporter can skip the new bean and let the old MBean stay registered:

```text
ObjectName does not exist -> register
ObjectName already exists  -> keep old MBean
```

This can be useful when an MBean is pre-provided by the container or a library and the application does not want to claim the name. However, JMX consumers will see the **implementation/metadata of the existing MBean**, not necessarily the bean you just configured.

Risks:

- The new configuration has `@ManagedAttribute`, yet clients still read old metadata.
- A naming bug or duplicate export is masked.
- Environment A registers MBean X first, environment B registers MBean Y first; both share the name yet yield different results.
- The team assumes the newly written bean exported cleanly because the context did not error.

Therefore, `IGNORE_EXISTING` should not be used as a blanket fix for every `InstanceAlreadyExistsException`.

### 3.3. REPLACE_EXISTING

This policy instructs the exporter to replace the MBean holding the name with the new bean. A conceptual flow:

```text
ObjectName already exists
     |
     v
unregister existing MBean
     |
     v
register new MBean
```

Possible consequences include:

- JMX clients using the old MBean may see a brief gap or transient errors during replacement.
- The old MBean may receive unregistration callbacks/lifecycle effects.
- Attribute/operation metadata changes abruptly, breaking monitoring.
- If registering the new MBean fails after unregistration, the name may be left with no valid MBean.
- Two competing exporters can produce startup-order-dependent behavior.

**Especially important:** `REPLACE_EXISTING` is not an atomic migration, has no automatic rollback, and does not prove you have the right to replace another component's MBean.

## 4. Registration Policy Is Not Equivalent to JMX Security

The words `FAIL`, `IGNORE`, and `REPLACE` describe how to handle **name collisions**, not client authorization.

Registration policy does not inherently provide:

- Authentication for remote JMX clients.
- TLS or network encryption.
- Role-based authorization per operation.
- Audit logs for management actions.
- Payload/parameter validation for management operations.
- Legal/organizational ownership of an ObjectName.
- Transaction or rollback guarantees when swapping MBeans.

An application using `FAIL_ON_EXISTING` can still expose sensitive operations if the JMX connector is unprotected. And an application using `IGNORE_EXISTING` can still suffer security issues if the old MBean exposes dangerous APIs.

**Safety level** when choosing a policy must be understood across at least two layers: *registry/metadata* safety and *access-path/operation* safety.

## 5. Understanding ObjectName Scope Properly

An ObjectName has the form:

```text
domain:key=value,key2=value2
```

Example:

```text
com.example.shop.orders:type=Queue,name=outbox
```

Registration uniqueness is evaluated per **MBeanServer**, not cluster-wide. Two JVMs in two different pods can register the same ObjectName in their two independent platform MBeanServers without conflict.

Thus, before changing the policy because “production has multiple replicas”, ask:

1. Do the replicas actually share **the same MBeanServer**?
2. Or does each JVM have its own platform MBeanServer?
3. Are multiple exporters in the same JVM attempting duplicate registrations?
4. Do container, library, or Actuator MBeans use the same ObjectName?
5. Are two ApplicationContexts/child contexts exporting the same bean into one server?

Do not put random pod names/instance IDs into ObjectNames just to fix a collision across independent JVMs. Dynamic names can break dashboards and alert rules.

## 6. Choosing a Policy by Operational Goal

| Goal | Usually Suitable Direction | Explanation |
|---|---|---|
| Want to detect duplicate export configurations | `FAIL_ON_EXISTING` | Errors surface immediately |
| MBean managed by a single owner | `FAIL_ON_EXISTING` | Prevents unexpected replacement or skipping |
| Integrating into an environment with a pre-existing MBean where the old owner takes precedence | Controlled `IGNORE_EXISTING` | Does not overwrite the current owner |
| Intentionally replacing your own old MBean | `REPLACE_EXISTING` with a procedure | Requires lifecycle/metadata planning |
| Source of conflict unknown | Do not use replace to mask the error | Investigate object name/owner first |
| Critical production requiring predictable contracts | Usually prefer fail-fast or clear export owner | Avoids startup-order-dependent outcomes |
| Need two management API versions running in parallel | Different ObjectName/version or explicit migration | Avoids accidentally overwriting the same name |

This table is a practical guide, not a mandatory Spring rule. If a system requires the application not to halt startup solely due to a JMX conflict, another policy may be chosen alongside corresponding **monitoring and verification**.

## 7. Recommendations by Environment

### 7.1. Local Development

The goal is fast feedback and easy root-cause discovery.

A strong default is usually **`FAIL_ON_EXISTING`**:

- Developers immediately see which exporter or bean registered twice.
- Prevents silently using an MBean from another run or configuration.
- Encourages fixing ObjectNames and ownership clearly.

In a local environment experimenting with hot reload or a special embedded container, lingering registrations can occur. Do not automatically switch permanently to replace without understanding why the lifecycle failed to unregister properly.

### 7.2. Automated Tests / CI

Usually prefer **`FAIL_ON_EXISTING`** to verify:

- Only one exporter owns each ObjectName.
- Test contexts clean up properly.
- No conflicts occur between suites sharing a JVM/MBeanServer.
- ObjectNames and contracts remain stable.

If multiple tests share the platform MBeanServer, design test isolation (separate MBeanServer, unique test ObjectNames, or thorough cleanup). Using `REPLACE_EXISTING` in tests can mask MBean leaks between test cases.

### 7.3. Staging

Staging should reflect the **intended production policy** and validate deployments/migrations. If production uses fail-fast, staging should catch duplicate names too. If production has an intentional replacement flow, staging should test mid-way failures, connected clients, and dashboard compatibility.

Use staging to verify:

- How many exporters are active after auto-configuration.
- Which MBeanServer is used.
- Full ObjectName of each MBean.
- Whether `MBeanInfo` has the right attributes/operations.
- How logs/metrics surface registration conflicts.
- Whether deployment rollbacks restore management endpoints.

### 7.4. Production

Production must prioritize **predictability** and minimizing unintended impact.

In most systems with clear ownership, `FAIL_ON_EXISTING` is an easily auditable starting point because it neither steals nor skips an ObjectName already used by another component. However, if a JMX error causes application startup to fail and business availability is top priority, design handling aligned with availability objectives: e.g., ensure duplicate configs are blocked in CI/staging, decouple management components, or use ignore alongside alerts and clear verification of the existing MBean's source.

Do not set `REPLACE_EXISTING` as a default just to “avoid deployment errors”. It can replace an MBean outside the exporter's ownership and disrupt monitoring.

## 8. Spring Configuration: Declaring registrationPolicy

Example of an exporter managing a Standard MBean:

```java
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.support.RegistrationPolicy;

@Configuration
public class JmxConfiguration {

    @Bean
    MBeanExporter queueExporter(QueueMonitorMBean queueMonitor) {
        MBeanExporter exporter = new MBeanExporter();

        exporter.setBeans(Map.of(
                "com.example.shop.orders:type=Queue,name=outbox",
                queueMonitor));

        exporter.setRegistrationPolicy(
                RegistrationPolicy.FAIL_ON_EXISTING);

        return exporter;
    }
}
```

Assume `QueueMonitorMBean` is a valid management interface with a matching implementation exposed as a Spring bean. The mapping has one explicit ObjectName and a single exporter.

If the bean is Spring-proxied, verify JMX compliance/metadata and method exposure. Setting `setRegistrationPolicy` alone does not solve proxying or annotation lookup issues.

### Minimal Standard MBean

```java
public interface QueueMonitorMBean {
    int getPendingCount();
}

public class QueueMonitor implements QueueMonitorMBean {
    @Override
    public int getPendingCount() {
        return 5;
    }
}
```

This is an interface/implementation pair following the Standard MBean convention. When deploying via Spring, declare `QueueMonitor` as a bean and wire an appropriate exporter.

### Using an Environment Property

You can read the policy from Spring `Environment`/configuration instead of hard-coding it:

```java
import org.springframework.core.env.Environment;
import org.springframework.jmx.support.RegistrationPolicy;

RegistrationPolicy policy = RegistrationPolicy.valueOf(
        environment.getRequiredProperty(
                "app.jmx.registration-policy"));
```

Configuration file example:

```yaml
app:
  jmx:
    registration-policy: FAIL_ON_EXISTING
```

This approach requires startup validation and configuration error handling. Do not let a production application automatically fall back to `REPLACE_EXISTING` when the property value is invalid.

In Spring Boot projects, inspect existing auto-configured exporters before manually creating an `MBeanExporter`. You may not need a manual exporter if the framework already manages bean export.

## 9. Choosing a Policy with Annotation-Driven Export

Suppose you have a Spring bean:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.shop.catalog:type=Cache,name=products",
    description = "Product cache")
public class ProductCacheManagement {

    @ManagedAttribute
    public int getEntryCount() {
        return 42;
    }
}
```

With annotation-driven JMX, the exporter/assembler detects the managed resource and registers the `ObjectName`. Registration policy still applies to **ObjectName collisions**, not attribute contents.

If two beans both declare:

```text
com.example.shop.catalog:type=Cache,name=products
```

then:

- `FAIL_ON_EXISTING` reports a conflict.
- `IGNORE_EXISTING` may keep the previously registered MBean.
- `REPLACE_EXISTING` may replace the existing MBean with the bean exported later.

They do not merge annotations or metadata. If the new MBean has `getHitRate()` and the old MBean does not, choosing ignore will not make that attribute appear.

## 10. When Is IGNORE_EXISTING an Intentional Choice?

A fairly reasonable case: the application runs in a container that already registered an infrastructure MBean and you want to preserve that MBean, while your exporter has a colliding mapping by convention.

Procedure:

1. Identify the **current owner** of the ObjectName.
2. Read `MBeanInfo` to inspect exposed attributes/operations.
3. Confirm the new bean can be skipped **without losing required monitoring capabilities**.
4. Set `IGNORE_EXISTING` as an explicit, documented policy.
5. Emit a log/metric for the ignored case so operations remain aware.
6. Test across different startup conditions to avoid order-dependent behavior.

Do not simply write:

```java
exporter.setRegistrationPolicy(
        RegistrationPolicy.IGNORE_EXISTING);
```

and assume every conflict is handled properly. One exporter starting first can claim the name; another starting later gets skipped. Outcomes can differ between local and production.

## 11. When Might REPLACE_EXISTING Be Considered?

An intentional scenario: the same owner manages a registered MBean and needs to swap it with a new implementation in a runtime with a specialized lifecycle.

Recommended conditions:

- Ownership of the ObjectName is confirmed.
- No third party holds the name.
- The old MBean can be unregistered safely.
- Clients tolerate a brief MBean absence or metadata changes.
- The new MBean has been verified by tests and staging.
- A recovery procedure exists if the new registration fails.
- Alerts/monitoring can detect a missing MBean after replacement.
- Two exporters are not continuously fighting for registration rights.

If these conditions cannot be met, prefer a **versioned ObjectName** design or a two-phase migration.

### Rollback Risk

Some mistakenly assume `REPLACE_EXISTING` means “if the new registration fails, the old MBean comes back”. There is no general guarantee of this. Before migrating, prepare a plan to re-register/restore the old component, and test mid-way failures.

## 12. Single Registration Source: Prevention Is Better Than Policy

Registration policy only resolves conflicts **after they occur**. A better design prevents conflicts altogether.

A sound convention should specify:

- Each ObjectName has one **registration owner**.
- Each MBean has one primary source of management metadata: interface, MXBean, or annotation assembler.
- Domain reflects the product/module, and key properties reflect type/name.
- Only one exporter or one `MBeanServer.registerMBean` site is allowed to own the ObjectName.
- Auto and manual exporters do not unintentionally export the same bean.
- Unregistration is tied to the component lifecycle.
- Integration tests verify the registered set of ObjectNames and contracts.

Example:

```text
ObjectName:
com.example.shop.orders:type=Queue,name=outbox

Contract owner:
OrderQueueManagement

Export owner:
Spring JMX exporter (annotation-driven)

Registration policy:
FAIL_ON_EXISTING

Consumer:
JConsole + exporter metrics
```

This is architectural documentation you can record in project docs; you do not necessarily need a complex registry config file, as long as ownership rules are clear.

## 13. Checking Conflicts Directly via MBeanServer

A Java snippet to check whether an ObjectName already exists:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class RegistrationInspection {

    public static void main(String[] args) throws Exception {
        MBeanServer server =
                ManagementFactory.getPlatformMBeanServer();

        ObjectName name = new ObjectName(
                "com.example.shop.orders:type=Queue,name=outbox");

        System.out.println("Registered: "
                + server.isRegistered(name));
    }
}
```

A `true` result indicates an MBean already exists under that name on the queried server. It does not automatically identify the owner or concrete Java implementation.

Reading metadata:

```java
import javax.management.MBeanInfo;

MBeanInfo info = server.getMBeanInfo(name);

System.out.println(info.getClassName());
System.out.println(info.getDescription());
```

`MBeanInfo` helps inspect the exposed contract, but class name or description alone is insufficient to verify ownership. To identify the registration source, cross-check exporter configurations, startup logs, and lifecycle.

**Race condition:** calling `isRegistered(name)` before `registerMBean` does not create an atomic check-and-register. Another thread/exporter can still register right after the check. Registration policy and owner design govern what happens when a conflict actually occurs.

## 14. Integration Test: FAIL_ON_EXISTING

Goal: create an isolated MBeanServer, register the first MBean, then attempt to register again under the same ObjectName.

Plain Java example:

```java
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import javax.management.ObjectName;

public class DuplicateRegistrationDemo {

    public static void main(String[] args) throws Exception {
        MBeanServer server =
                MBeanServerFactory.createMBeanServer("test");

        ObjectName name = new ObjectName(
                "com.example.test:type=QueueMonitor,name=main");

        server.registerMBean(new QueueMonitor(), name);

        try {
            server.registerMBean(new QueueMonitor(), name);
            throw new AssertionError("Expected duplicate registration failure");
        } catch (javax.management.InstanceAlreadyExistsException expected) {
            System.out.println("Duplicate ObjectName rejected");
        } finally {
            server.unregisterMBean(name);
        }
    }
}
```

This example demonstrates baseline `MBeanServer` behavior without calling `MBeanExporter`. To test the Spring policy, start a Spring exporter using the same MBeanServer, set the appropriate policy, and verify which bean is actually registered.

With `FAIL_ON_EXISTING`, the conflict is expected not to be masked. Tests should assert the exception/configuration appropriate to the Spring version without hard-coding a brittle stack trace.

## 15. Integration Test: IGNORE_EXISTING

A Spring integration test should:

1. Create a dedicated MBeanServer.
2. Register `MonitorA` under `com.example.test:type=Monitor,name=main`.
3. Configure `MBeanExporter` to export `MonitorB` under the same name with `IGNORE_EXISTING`.
4. Start the exporter.
5. Read an attribute identifying MonitorA's contract to confirm the old bean was kept.
6. Clean up the context and unregister in a controlled manner.

What to assert:

```text
Before:
  ObjectName exists -> MonitorA

After IGNORE_EXISTING:
  ObjectName still exists -> MonitorA
  MonitorB was not installed under that name
```

Asserting only `isRegistered(name) == true` is insufficient; it does not distinguish MonitorA from MonitorB. Use a `Version` attribute with two distinct values or check an operation/metadata unique to each contract.

## 16. Integration Test: REPLACE_EXISTING

For the replace policy, the test should confirm:

1. Before export, the MBean is MonitorA.
2. After export, the MBean reflects MonitorB.
3. Clients observe the expected metadata.
4. Lifecycle callbacks of the old/new MBeans are handled.
5. If the new registration fails, the system has a designed recovery mechanism.
6. Dashboards or consumers are able to reconnect/requery.

Diagram:

```text
T0: ObjectName -> MonitorA
T1: exporter REPLACE_EXISTING
T2: ObjectName -> MonitorB
```

Do not treat a passing replacement test as license to use this policy in every environment. It only shows that a replacement path worked under test conditions.

### Note on Service Availability

MBean replacement can interrupt management/monitoring; depending on the client, losing the MBean causes polling to fail for a brief interval. If the application requires uninterrupted observability, consider a new ObjectName version, or a management facade that keeps the ObjectName stable while swapping the underlying implementation.

## 17. Spring Boot and Auto-Configuration

In a Spring Boot application, multiple JMX-related setups can coexist:

- JVM platform MBeans.
- Spring `@ManagedResource` beans.
- Actuator endpoints exposed over JMX depending on configuration.
- Application-created custom `MBeanExporter`s.
- MBeans registered directly by libraries/database pools.

Do not assume there is only one exporter or one MBeanServer. When adding a custom exporter, inspect the effective configuration and avoid colliding with auto-configuration.

In particular, if a library already registers a connection-pool management MBean, registering another under the same ObjectName to “add attributes” will not merge metadata. Using `IGNORE_EXISTING` simply keeps the old one; using `REPLACE_EXISTING` can break the library's management capabilities.

Keep a separate namespace for custom MBeans:

```text
com.example.shop.orders:type=Queue,name=outbox
com.example.shop.payments:type=PoolMonitor,name=primary
```

Rather than trying to take over platform or library ObjectNames.

## 18. Question-Driven Policy Decision Guide

Before picking a policy, answer:

**Question 1. Who owns the ObjectName?**

- If the name belongs to your module, ensure a single owner.
- If the name belongs to a library/container, do not replace unless the API supports it and it is explicitly designed.

**Question 2. Is the duplicate name a configuration error?**

- If yes, `FAIL_ON_EXISTING` surfaces it.
- If no, justify why skipping or replacing is right.

**Question 3. How does the new MBean differ from the old MBean?**

- Are there new attributes/operations?
- Did data types, descriptions, permissions, or semantics change?
- Which fields do dashboards depend on?

**Question 4. If the MBean disappears for 1–2 polling cycles, what happens?**

- Does the collector just log missing data?
- Will alerts fire false positives?
- Are control operations actively running?

**Question 5. If the new registration fails, what is the recovery path?**

- Can the old MBean be re-registered?
- Can the deployment be rolled back?
- Is a versioned ObjectName needed?

**Question 6. Which environments does the policy apply to?**

- Do CI/tests detect conflicts?
- Does staging mirror production?
- Does production have monitoring to detect skipped or replaced MBeans?

A quality policy decision rests on these answers, not solely on “the app starts up”.

## 19. Example Internal Policy Table

A team can document a policy matrix:

| ObjectName or MBean Group | Owner | Environment | Policy | Rationale |
|---|---|---|---|---|
| `com.example.shop.orders:*` | Orders service | test/staging/prod | `FAIL_ON_EXISTING` | Single owner, stable contract |
| `com.example.shop.legacy:*` | Legacy adapter | staging/prod | Checked `IGNORE_EXISTING` | Respect pre-existing MBean and alert on skip |
| `com.example.shop.migration:*` | Migration component | controlled staging | `REPLACE_EXISTING` | Intentional MBean transition testing |
| JVM platform `java.lang:*` | JVM | all environments | Do not overwrite | Use standard platform MBeans |

This is an **example internal policy**, not a Spring default configuration. In many projects, you only need `FAIL_ON_EXISTING` and elimination of all duplicate exports.

## 20. Common Pitfalls

| Symptom | Possible Cause | Fix |
|---|---|---|
| Startup fails with duplicate MBean | Two exporters/beans share ObjectName | Identify owner, fix naming, keep fail-fast |
| JConsole shows old metadata | `IGNORE_EXISTING` kept existing MBean | Check MBeanInfo and registration order |
| Dashboard loses attributes after deploy | `REPLACE_EXISTING` changed contract | Versioning/migration and compatibility tests |
| ObjectName registered by another library | Namespace collision, custom exporter claims name | Choose product/module-specific domain |
| Flaky tests passing/failing intermittently | Test contexts share platform server | Isolated MBeanServer and proper cleanup |
| Multiple replicas assumed to conflict | Misunderstood per-MBeanServer scope | Do not add instance key if JVMs are independent |
| MBean missing after failed replace | No automatic rollback | Recovery plan, avoid uncontrolled replace |
| Slow app startup due to JMX | Registration callbacks or exporter waiting | Inspect lifecycle and dependencies |
| Enabling ignore to “fix” a config bug | New MBean skipped unintentionally | Alert on skip, resolve root conflict |
| Right policy yet operations remain dangerous | Registration policy is not authorization | Configure security and restrict operations |

## 21. Hands-On Exercises

### Exercise 1 — Choose a Policy by Scenario

You have four scenarios:

1. Two teams accidentally use the same ObjectName in one JVM.
2. The container already owns a system MBean, and the application is required to leave that MBean intact.
3. The platform team wants to swap its own management implementation during a planned maintenance window.
4. A test suite has contexts that fail to clean up registrations after tests finish.

Select the policy/solution:

- (1) `FAIL_ON_EXISTING`, fix ownership/naming.
- (2) Conditional `IGNORE_EXISTING` or rename the custom MBean to avoid conflict.
- (3) Controlled `REPLACE_EXISTING`, test migration/lifecycle.
- (4) Isolate test MBeanServer and clean up; do not use replace to hide leaks.

### Exercise 2 — Predict MBeanInfo

An old MBean has attribute `State`. The new MBean has attributes `State` and `QueueDepth`. If the ObjectName already exists:

- `FAIL_ON_EXISTING`: new export fails.
- `IGNORE_EXISTING`: clients keep seeing the old MBean's metadata, so `QueueDepth` does not appear.
- `REPLACE_EXISTING`: clients can see `QueueDepth` after replacement succeeds.

Use `MBeanInfo.getAttributes()` to verify rather than only checking `isRegistered`.

### Exercise 3 — Design an Integration Test

Create an isolated MBeanServer and two MBeans with a `Version` attribute set to `"A"` and `"B"`, respectively. Run the exporter with each policy in its own test context. Assert outcomes and perform full cleanup.

### Exercise 4 — Assess Production Risk

A team proposes setting `REPLACE_EXISTING` for all MBeans in production to avoid startup failures. List at least four risks and propose alternatives:

- Claiming an MBean name owned by another owner.
- Losing old metadata/operations.
- Monitoring disruption.
- No automatic rollback.
- Registration-order-dependent behavior.

Alternative: single owner/naming contract, fail-fast in test/staging, planned migration, or versioned ObjectNames.

### Exercise 5 — Multi-JVM Check

Two pods `orders-1` and `orders-2` both register:

```text
com.example.shop.orders:type=Queue,name=outbox
```

Each pod is an independent JVM. Explain why there is no conflict between the two MBeanServers, and why the monitoring aggregator still needs to distinguish instances via target labels.

## 22. Self-Check Questions

**1. What does `FAIL_ON_EXISTING` do when an ObjectName is already registered?**

It reports a conflict instead of silently skipping or replacing the existing MBean.

**2. Does `IGNORE_EXISTING` create a new MBean with merged metadata?**

No. It keeps the registered MBean; new attributes/operations are not merged automatically.

**3. Does `REPLACE_EXISTING` guarantee atomic rollback if the new registration fails?**

There is no general guarantee of that.

**4. Does registration policy protect sensitive operations from JMX clients?**

No. That is the responsibility of security configuration and separate management authorization.

**5. Do two JVMs sharing the same ObjectName automatically throw `InstanceAlreadyExistsException`?**

No, if the two MBeanServers are independent.

**6. Why can `IGNORE_EXISTING` make bugs hard to spot?**

Because the context may report no errors, yet the new bean is not exported and clients continue seeing the old MBean.

**7. In production, what criteria matter more than “no startup errors”?**

Correctness, stability, MBean ownership, monitoring compatibility, and a recovery plan.

## 23. Key Takeaways

- Spring JMX registration policy determines how `MBeanExporter` behaves when an **ObjectName already exists** in the same MBeanServer.
- `FAIL_ON_EXISTING` exposes conflicts; `IGNORE_EXISTING` keeps the old MBean; `REPLACE_EXISTING` replaces the old MBean with the new MBean per the registration mechanism.
- Policy does not merge metadata, does not alter JMX contract semantics, and is not a security mechanism.
- In development/CI/staging, fail-fast catches configuration and lifecycle mistakes.
- Production policies should be driven by ownership, availability objectives, and the impact of losing/changing management endpoints, not merely startup success.
- `IGNORE_EXISTING` fits when intentionally prioritizing the existing MBean with verification/alerts; `REPLACE_EXISTING` should only be used for migrations with clear ownership and recovery.
- Each ObjectName needs a single registration owner and a consistent management contract.
- Inspect `MBeanServer.isRegistered`, `getMBeanInfo`, and actual export logs to verify which bean is present.
- Replicas running in independent JVMs do not conflict just from sharing an ObjectName; uniqueness is scoped per MBeanServer.

## 24. References

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework Javadoc — `RegistrationPolicy`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/support/RegistrationPolicy.html
- Spring Framework Javadoc — `MBeanExporter`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporter.html
- Spring Framework Reference — Controlling MBean Registration Behavior: https://docs.spring.io/spring-framework/reference/integration/jmx/exporting.html
- Java SE 21 — `MBeanServer`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
