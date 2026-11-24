# Changing Domains When Splitting Modules in Spring Framework JMX

## 1. Context

In JMX, each MBean is identified by a `javax.management.ObjectName` with the structure:

\`\`\`text
domain:key1=value1,key2=value2,...
\`\`\`

When a Spring Framework application is split from a monolith into independent modules or services, development teams often want to split the **JMX domain** as well to reflect ownership more clearly. For example, previously all MBeans lived under `com.example.application`, and after splitting into `orders`, `payments`, and `inventory`, they may want to use:

\`\`\`text
com.example.orders:type=Queue,name=Import
com.example.payments:type=Processor,name=Settlement
com.example.inventory:type=Cache,name=Catalog
\`\`\`

This change looks like a simple rename, yet in practice it is a **management contract change**: monitoring scripts, dashboards, alerts, JMX notifications, automation tools, and runbooks may depend on the old ObjectNames. Changing domains without a plan can cause clients to think MBeans disappeared, miss metrics, or call the wrong MBean.

This lesson focuses on designing and executing a safe domain migration when splitting an application.

### Learning Objectives

After this lesson, you will be able to:

1. Distinguish JMX domain, Spring module, Java package, Spring bean name, and runtime process.
2. Identify the impact of changing domains on ObjectNames and JMX clients.
3. Plan migration from a monolith domain to modular domains.
4. Choose between direct cutover, time-boxed legacy name support, or compatibility facades.
5. Configure domains in Spring JMX via `@ManagedResource`, `MBeanExporter`, and naming strategies.
6. Handle situations where old and new MBeans represent the same resource.
7. Test ObjectNames, attributes, operations, registration lifecycle, and client compatibility.
8. Design rollback, alerting, and communication plans when changing management APIs.

## 2. What Is a Domain, and What Is It Not?

An ObjectName:

\`\`\`text
com.example.application:type=Queue,name=Import
\`\`\`

consists of:
- Domain: `com.example.application`.
- Key properties: `type=Queue,name=Import`.

A JMX domain is an identifier string inside an MBeanServer; it **does not automatically create a Java package, Spring ApplicationContext, network boundary, or security boundary**.

Comparison:

| Concept | Purpose | Changes automatically when JMX domain changes? |
|---|---|---|
| Java package | Organizes source code | No |
| Maven/Gradle module | Build/dependency unit | No |
| Spring bean name | Identifies bean in ApplicationContext | No |
| Spring ApplicationContext | Container managing Spring beans | No |
| JMX domain | Part of ObjectName | Yes |
| JMX ObjectName | Identifies MBean in MBeanServer | Yes |
| JMX connector URL | Connection address to JMX server | Not necessarily |
| MBeanServer | JMX registry | Not necessarily |
| Monitoring target | Endpoint queried by collector | May need updating |

For example, changing:

\`\`\`text
com.example.application:type=Queue,name=Import
\`\`\`

to:

\`\`\`text
com.example.orders:type=Queue,name=Import
\`\`\`

changes the **identity** of the MBean even when the Java class, Java methods, and internal data remain unchanged.

## 3. Why Does Splitting Modules Often Lead to Changing Domains?

Before splitting:

\`\`\`text
Monolith JVM
  |
  +-- Orders module
  +-- Payments module
  +-- Inventory module
  |
  +-- Platform MBeanServer
        |
        +-- com.example.application:type=Queue,name=Import
        +-- com.example.application:type=Processor,name=Settlement
        +-- com.example.application:type=Cache,name=Catalog
\`\`\`

After splitting:

\`\`\`text
Orders JVM                  Payments JVM                 Inventory JVM
  |                             |                             |
  +-- Orders MBeans             +-- Payments MBeans          +-- Inventory MBeans
  |                             |                             |
  +-- com.example.orders:*      +-- com.example.payments:*   +-- com.example.inventory:*
\`\`\`

Benefits of per-module domains:
- Distinguishes teams responsible for management.
- Helps clients query the right set of MBeans.
- Avoids namespace ambiguity when multiple modules share one JVM.
- Simplifies organizing management docs per domain.
- Aligns naming rules with application/team ownership.
- Reduces the chance of modules accidentally colliding on ObjectNames in one MBeanServer.

However, not every module split requires changing domains. If clients are stable and the old domain is published as a public contract, keeping the old domain can be lower risk. Splitting code and changing management APIs are two independent changes.

## 4. Impact of Changing Domains

Suppose an old monitoring query:

\`\`\`java
ObjectName oldPattern = new ObjectName(
    "com.example.application:*"
);

Set<ObjectName> names =
    connection.queryNames(oldPattern, null);
\`\`\`

When all MBeans move to `com.example.orders:*`, this query finds none of the new MBeans. That can cause:
- Metrics to "disappear" from dashboards.
- False `missing metrics` or `service down` alerts.
- Scripts calling `isRegistered(oldName)` returning false.
- Automation calling `getAttribute(oldName, ...)` hitting `InstanceNotFoundException`.
- JConsole tree showing a different domain.
- Event listeners bound to the old ObjectName missing notifications from the new MBean.
- Outdated runbooks and operational documentation.
- Historical time series splitting in two when monitoring labels embed ObjectName.

**Changing a domain is not a cosmetic change.** Clients directly or indirectly depending on ObjectNames can be affected.

## 5. Three Module-Splitting Scenarios to Distinguish

### Scenario A: Splitting Source Code Only, Same JVM

Maven modules are split, yet the application still deploys together:

\`\`\`text
Monolith process
  |
  +-- orders.jar
  +-- payments.jar
  +-- inventory.jar
  |
  +-- one MBeanServer
\`\`\`

Here, changing domains helps clarify ownership and prevent collisions, though it is not strictly mandatory. MBeans and the JMX connector can remain in the same JVM.

### Scenario B: Splitting into Separate JVMs/Services

Each service has its own MBeanServer. In this case, also address:
- New domain/ObjectName.
- New JMX connector URL.
- Separate firewall/credentials/network rules.
- Collector discovery/configuration.
- Metric labels and instance identity.

A monitoring client using the right new domain while still connecting to the old JVM will not see the MBean either. Domain migration and connector migration must be coordinated.

### Scenario C: Hybrid Transition Phase

Some MBeans remain in the monolith while others move to new services. The following may coexist:
- Old domain on the monolith.
- New domain on services.
- The same logical resource observed through two MBeans during cutover.

This scenario requires controlling double-counted metrics and duplicate administrative operations.

## 6. Inventory Before Making Changes

Before migrating, list current MBeans:

| Old ObjectName | Owner | Dependent clients | Sensitive operations | Proposed New ObjectName |
|---|---|---|---|---|
| `com.example.application:type=Queue,name=Import` | Orders | JConsole, collector | pause/resume | `com.example.orders:type=Queue,name=Import` |
| `com.example.application:type=Processor,name=Settlement` | Payments | Alerting, script | retrySettlement | `com.example.payments:type=Processor,name=Settlement` |
| `com.example.application:type=Cache,name=Catalog` | Inventory | Dashboard | clearCache | `com.example.inventory:type=Cache,name=Catalog` |

For each ObjectName:
1. Confirm the MBean owner.
2. List attributes and descriptions.
3. List operations, parameters, and side effects.
4. List notification types and listeners.
5. Identify the current MBeanServer/connector endpoint.
6. Find all monitoring clients and automation references.
7. Choose a new domain with a stable structure.
8. Record the deadline for retiring the old name if needed.

Do not merely grep source code: monitoring configurations, scripts, dashboard queries, and runbooks may live outside the application repository.

## 7. Designing the New Domain

A convention can be:

\`\`\`text
<organization>.<application-or-module>:type=<Type>,name=<Name>[,instance=<Instance>]
\`\`\`

Examples:

\`\`\`text
com.example.orders:type=Queue,name=Import
com.example.orders:type=Worker,name=Fulfillment
com.example.payments:type=Processor,name=Settlement
com.example.inventory:type=Cache,name=Catalog
\`\`\`

Avoid:
- Arbitrary domains tied to refactored class names.
- Domains containing dynamic hostnames without reason.
- Domains changing per deployment ID when clients need stable names.
- Domains containing customer IDs or secret data.
- Domains built from unvalidated user input.
- Creating too many domains, making JConsole hard to browse.

If environments need distinction, use an `env=prod` key or collector target labels. A new domain alone does not solve separating prod/staging/local.

### A Domain Is a Contract Name, Not Just a Package Name

Packages may change from `com.example.orders.impl` to `com.example.orders.core` while the management domain stays `com.example.orders`. That prevents implementation refactorings from affecting JMX clients.

## 8. Approach 1: Change @ManagedResource.objectName

Spring Framework JMX supports:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.jmx.export.annotation.ManagedAttribute;

@ManagedResource(
    objectName = "com.example.orders:type=Queue,name=Import",
    description = "Orders import queue monitoring"
)
public class ImportQueueMonitor {

    @ManagedAttribute(description = "Pending imports")
    public int getPendingCount() {
        return 42;
    }
}
\`\`\`

Pros:
- Name is immediately visible in source.
- MetadataNamingStrategy can use the declared metadata.
- Easy to understand for an MBean with one fixed ObjectName.

Cons:
- It is a Java annotation constant.
- One class might be reused across multiple environments or instances.
- Changing the domain in an annotation requires deploying a new binary.
- Scripts depending on the old name do not update automatically.

**Remember:** Annotations do not register MBeans by themselves. An appropriate Spring JMX exporter/annotation-driven configuration must exist, such as `@EnableMBeanExport` or XML `<context:mbean-export/>`.

## 9. Approach 2: Explicit MBeanExporter Mapping

With a Standard MBean:

\`\`\`java
public interface ImportQueueMonitorMBean {
    int getPendingCount();
}
\`\`\`

\`\`\`java
public class ImportQueueMonitor implements ImportQueueMonitorMBean {
    @Override
    public int getPendingCount() {
        return 42;
    }
}
\`\`\`

Can be configured as:

\`\`\`java
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class JmxConfiguration {

    @Bean
    public MBeanExporter mBeanExporter(
            ImportQueueMonitor monitor) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setBeans(Map.of(
            "com.example.orders:type=Queue,name=Import",
            monitor
        ));
        exporter.setAutodetectMode(
            MBeanExporter.AUTODETECT_NONE
        );
        return exporter;
    }
}
\`\`\`

During migration, the map becomes the place managing the naming contract. For annotation-based POJOs, add an appropriate assembler/metadata source; `setBeans` does not automatically turn arbitrary POJOs into annotated MBeans with full metadata.

When a Spring Boot application already has JMX auto-configuration, avoid accidentally creating two exporters registering the same MBean under the same ObjectName.

## 10. Approach 3: Centralized ObjectNamingStrategy

When modules share a convention but have distinct domains, a custom naming strategy can unify the rules.

\`\`\`java
import java.util.Map;
import javax.management.MalformedObjectNameException;
import javax.management.ObjectName;
import org.springframework.jmx.export.naming.ObjectNamingStrategy;

public final class ModuleNamingStrategy
        implements ObjectNamingStrategy {

    private final Map<String, String> domainsByBeanKey;

    public ModuleNamingStrategy(
            Map<String, String> domainsByBeanKey) {
        this.domainsByBeanKey = Map.copyOf(domainsByBeanKey);
    }

    @Override
    public ObjectName getObjectName(
            Object managedBean,
            String beanKey) throws MalformedObjectNameException {

        String domain = domainsByBeanKey.get(beanKey);
        if (domain == null) {
            throw new IllegalArgumentException(
                "No JMX domain mapping for " + beanKey
            );
        }

        return new ObjectName(
            domain + ":type=Queue,name=" + ObjectName.quote(beanKey)
        );
    }
}
\`\`\`

This example illustrates config-driven mapping instead of inferring the domain from runtime package/class names. In real systems, map both `type` and `name` per business contract rather than hard-coding every MBean as Queue.

Do not rely on `managedBean.getClass().getPackageName()` as the sole source for the domain because Spring AOP proxies and implementation refactorings can change the runtime class or package.

## 11. Direct Cutover

The simplest option:
1. Change the domain in the application.
2. Update all monitoring clients/scripts.
3. Deploy as planned.
4. Verify MBeans in the new domain.
5. Retire old ObjectNames.

Pros:
- No prolonged period where old and new names coexist.
- Less code complexity.
- Lower risk of duplicate operations.

Cons:
- Old clients may lose access during migration.
- Requires tight deployment coordination.
- A missed consumer may stop working.

Suitable when:
- There are few clients.
- You control the entire deployment.
- There is a clear maintenance window and rollback plan.
- All external dependencies have been found.

## 12. Dual-Name Compatibility: Should You Register an Alias?

A common idea is exporting the same resource under both the old and new names:

\`\`\`text
com.example.application:type=Queue,name=Import
com.example.orders:type=Queue,name=Import
\`\`\`

In JMX, two names can coexist in one MBeanServer if validly registered. However, assess the risks:

- Metrics collectors may scrape two series for the same logical resource.
- Operations like pause/resume may be invoked from both endpoints.
- Notifications may be observed twice.
- Registration/unregistration lifecycle becomes more complex.
- An exporter or MBean implementation may not trivially support registering the exact same object instance under two names as assumed.
- Clients may not know which name is recommended.

**Do not assume “adding an alias solves everything”.** If compatibility is required, design a dedicated facade MBean for the old name that delegates in a controlled manner to the new service while publishing a deprecation deadline.

### Compatibility Facade

\`\`\`text
Old ObjectName
      |
      v
Deprecated compatibility MBean
      |
      v
Shared management service
      ^
      |
New MBean
      ^
      |
New ObjectName
\`\`\`

To stay safe, you can:
- Keep attributes read-only on the alias.
- Restrict sensitive operations on the alias.
- Mark the description as deprecated.
- Log/audit alias usage.
- Announce an end-of-support date.
- Prevent double-counting in collectors.

If compatibility is only needed for metrics, updating collector mappings is sometimes better than registering an extra alias MBean.

## 13. Accurate Registry and MBeanServer Lifecycle

An MBean is registered into a specific MBeanServer. When splitting modules:
- The monolith may use the platform MBeanServer.
- A new service has its own MBeanServer.
- Each process has a different connector URL.
- The old ObjectName on the old JVM may remain active during the hybrid phase.

A client querying the right new ObjectName against the old server can still receive `InstanceNotFoundException`.

Verify all of:
1. **Connection target**.
2. **MBeanServer identity**.
3. **ObjectName**.
4. **Registration status**.
5. **Management interface contract**.

When closing the Spring ApplicationContext, the exporter must unregister the MBeans it owns per lifecycle/configuration. Never leave a compatibility MBean registered while delegating to a closed service.

## 14. Migrating Notification Listeners

If a client registered a listener on:

\`\`\`text
com.example.application:type=Queue,name=Import
\`\`\`

after the MBean moves to:

\`\`\`text
com.example.orders:type=Queue,name=Import
\`\`\`

the listener on the old name does not automatically move to the new name. The client needs to:
- Connect to the new server.
- Locate the new ObjectName.
- Re-register the listener.
- Handle cleanup of the old listener.
- Read a state snapshot after cutover.
- Never assume notifications missed during the switch are fully replayed.

If both the alias and the new MBean emit notifications for the same event, clients must distinguish a logical event ID or avoid subscribing to both without deduplication.

## 15. Migrating Operations with Side Effects

Operations such as:
- `clearCache()`.
- `pauseWorker()`.
- `resumeWorker()`.
- `resetStatistics()`.
- `reloadConfiguration()`.

might be invoked through both old and new names during migration. Decide:
- Which endpoint is canonical?
- Should write operations be disabled on the old alias?
- On remote timeout, will clients retry on the new name?
- Is there an idempotency key or state check to prevent double execution?
- Are auditing and permissions separated?

Do not retry a side-effecting operation on the new domain simply because calling the old domain timed out: the old server may have executed the operation while the response was lost.

For critical operations, allowing mutations only on the new canonical MBean and keeping the old name read-only reduces risk.

## 16. Migrating Monitoring and Metrics

If metric identity includes ObjectName, changing the domain can create a new time series.

Before:
\`\`\`text
jmx_queue_pending{object_name="com.example.application:type=Queue,name=Import"} 12
\`\`\`

After:
\`\`\`text
jmx_queue_pending{object_name="com.example.orders:type=Queue,name=Import"} 12
\`\`\`

Even though it measures the same indicator, the metrics backend may treat them as two separate series.

Mitigations:
- Use stable metric names and app/module/resource labels decoupled from raw ObjectName.
- Update collector mappings at cutover.
- Verify thresholds/alerts before and after deployment.
- Avoid double-counting when the same metric is scraped via old/new aliases.
- Annotate the change timestamp for dashboard analysis.
- Ensure dashboards display historical data with accurate semantics.

When a module moves to another JVM, also update target identity, instance labels, and service discovery. Do not try to solve everything by editing only the ObjectName domain.

## 17. Testing Before Migration

### 17.1. Mapping Unit Test

\`\`\`java
import static org.junit.jupiter.api.Assertions.*;
import javax.management.ObjectName;
import org.junit.jupiter.api.Test;

class ModuleDomainNamingTest {

    @Test
    void ordersUsesOrdersDomain() throws Exception {
        ObjectName name = new ObjectName(
            "com.example.orders:type=Queue,name=Import"
        );
        assertEquals("com.example.orders", name.getDomain());
        assertEquals("Queue", name.getKeyProperty("type"));
        assertEquals("Import", name.getKeyProperty("name"));
        assertFalse(name.isPattern());
    }
}
\`\`\`

### 17.2. Registration Integration Test

\`\`\`java
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = /* MBeanServer used by Spring exporter */ null;

ObjectName newName = new ObjectName(
    "com.example.orders:type=Queue,name=Import"
);

if (!server.isRegistered(newName)) {
    throw new AssertionError("New MBean name is missing");
}
\`\`\`

In a real test, replace the placeholder with the MBeanServer retrieved from ApplicationContext or configured for the exporter. Do not assume the platform server if Spring uses a custom MBeanServer.

### 17.3. Inspecting MBeanInfo

\`\`\`java
var info = server.getMBeanInfo(newName);
for (var attr : info.getAttributes()) {
    System.out.println(attr.getName() + ": " + attr.getType());
}
for (var op : info.getOperations()) {
    System.out.println(op.getName());
}
\`\`\`

Compare the old and new management interfaces:
- Are required attributes preserved?
- Have read/write flags changed?
- Do operations have matching signatures and semantics?
- Were any notifications or descriptions lost?
- Are other differences intentional and documented?

## 18. Contract Tests for Clients

A test more useful than just `isRegistered()` exercises the client flow:

1. Connect to the right JVM/service.
2. Query the new ObjectName.
3. Read a critical read-only attribute.
4. Inspect MBeanInfo.
5. Test notification subscription if used by the application.
6. Verify client automation no longer uses the old domain.
7. With an alias, verify the old name only exposes permitted capabilities.
8. Verify reconnection when the new endpoint/service restarts.

For state-mutating operations, test only in staging/test environments. Never run destructive operations on real data just to verify migration.

## 19. Observing Whether the Old Domain Is Still Used

When using a compatibility period, measure usage of the old name to know when it can be removed.

Observation sources:
- Monitoring collector configurations.
- Logs from the compatibility facade.
- Admin operation audits.
- Inventory of scripts/clients.
- Dashboard/alert query references.
- Listener subscription counts on the old endpoint if measurable.

Not every JMX server provides out-of-the-box granular data on "which client called the old MBean". Recording usage may require a custom facade or instrumentation at the connector/application layer.

A deprecation policy can include:
- Announcing support start and end dates.
- Marking the old MBean deprecated in its description.
- Tracking usage during the transition period.
- Updating runbooks and client libraries.
- Removing the alias once consumers have migrated.

## 20. Rollback When Migration Fails

Distinguish between:
- **Naming rollback:** reverting to the old domain.
- **Service split rollback:** moving the module back into the monolith.
- **Collector rollback:** reverting monitoring queries to the old name.

All three do not always need to be rolled back together.

A practical plan:
1. Keep copies of both old and new mapping configurations.
2. Version the naming contract across releases.
3. Run JMX smoke tests to catch missing MBeans immediately after deploy.
4. Keep a way to switch collectors back to the old domain if needed.
5. Do not remove the old compatibility path before verifying clients.
6. Check for duplicate or missing data in monitoring.
7. Account for downtime needed if operations cannot run in parallel.

If a rolling deployment leaves some instances on the old domain and others on the new domain, collectors may briefly need controlled dual support.

## 21. Security When Changing Domains

A domain is not an authentication/authorization mechanism. When a module moves to a new service, the remote JMX surface may change:
- A new connector opens an additional network endpoint.
- New credentials and access roles apply.
- The MBeanServer contains a different set of MBeans.
- An operation previously limited to local access is now remotely exposed.
- An old alias may become a less-reviewed access path.

Therefore, treat migration as a **security topology** change, not just naming:
- Secure the connector.
- Restrict network interfaces.
- Verify TLS/credentials and permissions.
- Review sensitive operations.
- Do not expose secrets in attributes.
- Separate read-only monitoring permissions from admin invoke permissions.
- Audit production actions where appropriate.

Having `payments` in the domain name does not stop callers from accessing the MBean if connector security allows it.

## 22. Common Mistakes

**Mistake 1: “Changing the Java package means you must change the JMX domain.”**  
No. Domain is an independent management contract and should stay stable.

**Mistake 2: “Changing the domain doesn't affect behavior.”**  
Management clients using the old ObjectName may stop working.

**Mistake 3: “A new ObjectName automatically appears to clients connected to the old JVM.”**  
No. Connection target and server registry must also match.

**Mistake 4: “Keeping both names is always safe.”**  
It can double-count metrics, duplicate notifications, and execute operations twice.

**Mistake 5: “Only update the exporter, no need to touch dashboards.”**  
Monitoring clients, alert rules, and runbooks may depend on the old domain.

**Mistake 6: “You can use REPLACE_EXISTING to switch domains.”**  
RegistrationPolicy handles collisions on the same ObjectName; it does not redirect clients from an old name to a new name.

**Mistake 7: “Using getClass().getPackageName() gives stable naming.”**  
Refactorings, proxies, or package moves cause the management contract to drift.

**Mistake 8: “Notification listeners automatically migrate to the new ObjectName.”**  
No. Clients must re-register listeners and refresh state.

**Mistake 9: “Changing the domain is enough when splitting a service.”**  
Connectors, networks, credentials, target discovery, lifecycle, and metrics mappings also matter.

**Mistake 10: “The new domain is more secure because of its separate name.”**  
Names are not security boundaries; access is controlled by connector/application policies.

## 23. Step-by-Step Migration Plan

### Step 1 — Inventory

- List all old ObjectNames.
- Confirm owners.
- Identify clients, dashboards, scripts, alerts, and notifications.
- Assess risky operations.

### Step 2 — Design the New Domain

- Choose domains following logical ownership.
- Keep key properties stable when possible.
- Define instance/environment naming.
- Set a version/deprecation policy if needed.

### Step 3 — Choose a Compatibility Strategy

- Direct cutover if consumers are small and controllable.
- Compatibility facade when old clients must be supported.
- Collector mapping if only metrics continuity is needed.
- Do not register aliases for every MBean blindly without review.

### Step 4 — Implement Code/Config

- Update annotations, exporter mappings, or naming strategies.
- Verify the target MBeanServer.
- Avoid exporter duplication.
- Ensure management interfaces and lifecycles do not change unintentionally.

### Step 5 — Test

- Unit test ObjectNames.
- Integration test MBean registration.
- Contract test attributes/operations/notifications.
- End-to-end test collectors or JMX clients.
- Verify access controls.

### Step 6 — Cut Over and Monitor

- Deploy in a controlled sequence.
- Verify new-domain MBeans exist.
- Watch for gaps/double-counting in metrics.
- Track usage of old aliases.
- Update runbooks.

### Step 7 — Planned Cleanup

- Remove old domains/aliases only after clients have migrated.
- Document changes in release notes.
- Remove compatibility code when no longer needed.
- Keep verifying ObjectNames in smoke tests.

## 24. Example Runbook

\`\`\`text
Migration: com.example.application -> com.example.orders

Before:
  1. Confirm inventory for orders MBeans.
  2. Verify monitoring queries support new domain.
  3. Check access to new JMX connector.
  4. Freeze changes to JMX operations during migration.

Deploy:
  1. Deploy orders module/service.
  2. Query com.example.orders:* on correct server.
  3. Read PendingCount on Queue Import.
  4. Inspect MBeanInfo.
  5. Verify collector sees expected metrics.

After:
  1. Check alerting and dashboard continuity.
  2. Confirm no duplicate metric ingestion.
  3. Validate only intended old aliases remain.
  4. Record outcome and deprecation deadline.

Rollback:
  1. Restore prior connector/collector mapping if needed.
  2. Roll back application naming configuration when appropriate.
  3. Confirm old ObjectNames are registered.
  4. Re-run safe read-only smoke tests.
\`\`\`

## 25. Hands-on Exercises

### Exercise A: Inventory and Mapping

1. Take three MBeans in `com.example.application`.
2. Assign owners: orders/payments/inventory.
3. Propose three new domains.
4. Record complete old/new ObjectNames.
5. List three groups of clients needing updates.

### Exercise B: Spring JMX Code Migration

1. Create a `@ManagedResource` in the old domain.
2. Change ObjectName to the orders domain.
3. Enable annotation JMX export.
4. Start the Spring context.
5. Use `queryNames()` and `isRegistered()` to verify the new domain.

### Exercise C: Client Compatibility

1. Write a client querying the old domain.
2. Change the MBean domain.
3. Observe `InstanceNotFoundException` or empty query results.
4. Update the client to the new domain.
5. Test migrating via a compatibility facade if needed.

### Exercise D: Duplicate Metrics

1. Export both old and new MBeans for one logical resource in a test environment.
2. Configure a collector to scrape both.
3. Observe duplicate series or double-counting.
4. Design a collector mapping to avoid duplication.
5. Define an alias removal deadline.

### Exercise E: Remote Service Split

1. Move an MBean to another test JVM.
2. Update `JMXServiceURL` in the client.
3. Use the new domain.
4. Read attributes via `MBeanServerConnection`.
5. Verify security and listener registration.

## 26. Self-Check Questions

**Question 1.** Does changing the JMX domain mean changing the Java package?  
**Answer:** No. The two concepts are independent.

**Question 2.** Why can changing domains cause monitoring to lose data?  
**Answer:** Collectors/scripts may query the old ObjectNames.

**Question 3.** Does a new domain secure MBeans?  
**Answer:** Not directly. Security depends on connectors and access permissions.

**Question 4.** Should old and new aliases always be registered simultaneously?  
**Answer:** No. Assess double-counting, duplicate notifications, side effects, and lifecycle.

**Question 5.** When a module moves to another JVM, is changing the domain enough?  
**Answer:** No. Connector URLs, network/security, and target discovery must also be updated.

**Question 6.** Do listeners registered on the old ObjectName automatically receive notifications from the new ObjectName?  
**Answer:** No. Clients must re-register against the new name/server.

**Question 7.** Why use a management facade for compatibility?  
**Answer:** To preserve the old contract in a controlled way, reduce the risk of exposing duplicate operations, and log deprecation.

**Question 8.** When should the old domain be removed?  
**Answer:** After confirming clients have migrated, monitoring is stable, and the deprecation policy is met.

## 27. Key Takeaways

- JMX domain is part of ObjectName and of the management API contract.
- Splitting source modules **does not force** changing domains, though it can be an opportunity to standardize ownership.
- Changing domains affects JMX clients, scripts, alerts, dashboards, and notification listeners.
- For a service split, handle connector targets and security topology as well, not just ObjectName.
- Choose direct cutover or a compatibility facade based on client count and risk level.
- Do not assume dual aliases are safe; they can double-count metrics or duplicate operations.
- Test MBeanInfo, ObjectName, registration lifecycle, and client contracts.
- Document rollback plans and deprecation deadlines before deployment.
- A new domain is a name, not a security boundary.
- Keep ObjectNames stable after migration so operational tools do not depend on internal refactoring.

### References

- Spring Framework Reference — JMX Exporting: https://docs.spring.io/spring-framework/reference/integration/jmx/exporting.html
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework Javadoc — `MBeanExporter`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporter.html
- Spring Framework Javadoc — `MetadataNamingStrategy`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/naming/MetadataNamingStrategy.html
- Java SE 21 API — `ObjectName`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/ObjectName.html
- Java SE 21 API — `MBeanServer`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
