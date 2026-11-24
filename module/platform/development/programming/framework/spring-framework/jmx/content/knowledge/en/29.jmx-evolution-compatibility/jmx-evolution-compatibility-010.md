# Keeping Documentation and JMX Contract Tests Updated After Spring Framework Upgrades

## 1. Objective

JMX (Java Management Extensions) is a management API of a Java application. When Spring Framework exports beans as MBeans, elements such as `ObjectName`, attributes, operations, notification types, signatures, and data types form a **management contract** that JConsole, VisualVM, monitoring agents, automation scripts, or other Java applications may depend on.

Upgrading Spring Framework, the JDK, Spring Boot, monitoring libraries, or exporter configuration can alter this contract in non-obvious ways. For example, a new naming strategy generates a different ObjectName, an assembler exposes or omits methods, a return type changes, a notification type is renamed, or an MBean stops being auto-detected. The application may still start and run business logic normally while monitoring and operations are broken.

**Principle:** treat the JMX API as a contract with real consumers. Before upgrading, save a verifiable baseline; after upgrading, compare the contract automatically and update documentation/runbooks to match actual behavior. Never rely solely on successful application startup.

## 2. What Does a JMX Contract Include?

A management contract has multiple parts:

| Element | Meaning | Impact when changed |
| --- | --- | --- |
| `ObjectName` | MBean identifier in MBeanServer | Clients fail to find old MBean or call wrong resource |
| Attribute name | Property name such as `QueueDepth` | Collectors or dashboards lose metrics |
| Attribute type | Data type such as `int`, `long`, `String`, Open Types | Cast/deserialization errors or wrong alerts |
| Readable/writable | Read/write permissions in metadata | A read-only attribute may accidentally become writable |
| Operation name | Management command name | Automation calling `invoke` fails |
| Operation signature | Parameter count/order/types | Client proxies no longer match API |
| Operation return type | Return type and data | Parsers or clients fail |
| Notification types | Event identifiers | Listener filters stop receiving events |
| Notification payload | Message/userData schema and meaning | Consumers misprocess or lose compatibility |
| Semantics | Meaning, side effects, bounds, and permissions | Behavior can change even when API names do not |
| Lifecycle/registration | When MBeans appear/disappear | Monitoring reports missing or duplicate MBeans |

Do not save just a list of names. Two versions can share the same ObjectName and operation name yet differ in signature, or keep the same type while changing meaning. A good contract test checks both **structure** and **critical semantics**.

## 3. Paths by Which Contracts Change During Upgrades

In Spring Framework JMX, factors that can affect registered metadata include:

- `MBeanExporter`: beans in explicit maps or autodetection.
- `@ManagedResource`: ObjectName, description, and resource metadata.
- `@ManagedAttribute`/`@ManagedOperation`: exposed members.
- `@ManagedOperationParameters`: parameter descriptions/names.
- `@ManagedNotifications`/`@ManagedNotification`: notification metadata.
- `ObjectNamingStrategy`: generated ObjectNames when not hard-coded.
- `MBeanInfoAssembler`: algorithm selecting getters, setters, operations, and descriptions.
- Standard JMX interfaces such as `ExampleMBean` or `ExampleMXBean`.
- Spring AOP proxies and JDK/CGLIB proxy types affecting metadata/call paths.
- JDK version and Open MBean type mappings.
- MBeanServer configuration and `RegistrationPolicy`.

Not every upgrade changes these components. However, **even small configuration or code changes can break the management contract**, so post-upgrade verification must inspect the actual registered MBeans, not just config files.

## 4. What Should Contract Documentation Record?

Every critical management API should have a descriptive document:

```text
MBean: com.example.jobs:type=QueueDiagnostics,name=Main
Owner: jobs-service
Purpose: read-only monitoring for worker queue
Since: 1.0
Status: supported

Attributes:
  QueueDepth: int, readable=true, writable=false
  CompletedCount: long, readable=true, writable=false
  HealthSummary: java.lang.String, readable=true, writable=false

Operations:
  requestRefresh(): void
    Effect: schedules refresh; may change runtime state
    Permission: privileged operator only
    Retry: not unconditional; check status first

Notifications:
  com.example.jobs.queue.threshold
    Meaning: backlog crossed warning threshold
    Payload: safe integer depth, best-effort

Compatibility:
  Name stable across deployments
  QueueDepth semantics: current pending jobs
  No secrets/PII
```

The block above is a documentation template, not a standard JMX schema. It supplements details that `MBeanInfo` does not always fully describe, such as ownership, side effects, retry policies, security, and business meaning.

**Documentation should have a version and owner**, stored in the repository or controlled operational docs. Never place tokens, passwords, or personal data in example ObjectNames, notification payloads, or sample outputs.

## 5. Baselines Must Come from a Real MBeanServer

Do not build a baseline solely by scanning annotations in source code. A bean carrying `@ManagedResource` might not be exported due to component scan scope, exporter config, conditional beans, profiles, or registration failures. The final name may differ from the annotation due to a naming strategy; a different assembler may select different methods.

A reliable baseline must read `MBeanInfo` from an **actually started MBeanServer**, using the right Spring profile and representative deployment configuration.

```text
ApplicationContext + Spring exporter
            |
            v
         MBeanServer
            |
            v
        queryNames
            |
            v
      getMBeanInfo(name)
            |
            v
     Versioned contract snapshot
```

Snapshots should normalize ordering to prevent noisy diffs. In particular, ObjectName key properties have no semantic order; use `getCanonicalName()` instead of raw string comparisons.

## 6. Retrieving ObjectNames and MBeanInfo

Plain JMX example:

```java
import java.lang.management.ManagementFactory;
import java.util.Set;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName domainPattern = new ObjectName(
    "com.example.jobs:*") ;

Set<ObjectName> names = server.queryNames(domainPattern, null);

for (ObjectName name : names) {
    MBeanInfo info = server.getMBeanInfo(name);
    System.out.println(name.getCanonicalName());
    System.out.println("class=" + info.getClassName());
    System.out.println("attrs=" + info.getAttributes().length);
    System.out.println("ops=" + info.getOperations().length);
}
```

This example assumes MBeans are registered in the platform MBeanServer. If Spring uses a custom server, access that exact server or `MBeanServerConnection`. Query only application-owned domains to avoid pulling JVM-owned or other-module MBeans into your own contract.

Do not read every attribute value when building a baseline; getters may be expensive or return secrets. Most structural checks only need metadata from `MBeanInfo`.

## 7. Snapshotting Attributes Accurately

```java
import javax.management.MBeanAttributeInfo;

for (MBeanAttributeInfo attr : info.getAttributes()) {
    System.out.printf(
        "attribute=%s type=%s readable=%s writable=%s is=%s%n",
        attr.getName(),
        attr.getType(),
        attr.isReadable(),
        attr.isWritable(),
        attr.isIs()
    );
}
```

Properties to save: name, Java type, readable, writable, and boolean getter convention (`isIs` if needed). Descriptions can be kept in documentation, though framework-generated descriptions may change phrasing across versions; distinguish **contract-breaking diffs** from **descriptive-only diffs**.

Example contract-breaking change:

```text
Before: QueueDepth, int, readable=true, writable=false
After:  PendingJobs, long, readable=true, writable=false
```

Clients reading `QueueDepth` will receive `AttributeNotFoundException`; even though changing to `long` widens the Java type in some contexts, legacy JMX clients expecting `int` can still hit cast errors.

Example risky permission change:

```text
Before: Enabled, boolean, readable=true, writable=false
After:  Enabled, boolean, readable=true, writable=true
```

This opens up a new control surface requiring permissions and semantics review, rather than merely treating it as a compatible feature.

## 8. Snapshotting Operations and Signatures

MBean operations are identified by name and parameter list. Record order, types, return type, and impact metadata.

```java
import javax.management.MBeanOperationInfo;
import javax.management.MBeanParameterInfo;

for (MBeanOperationInfo op : info.getOperations()) {
    System.out.println(
        "operation=" + op.getName() +
        " return=" + op.getReturnType() +
        " impact=" + op.getImpact()
    );
    for (MBeanParameterInfo p : op.getSignature()) {
        System.out.println(
            "  parameter=" + p.getName() + " type=" + p.getType()
        );
    }
}
```

Example initial contract:

```text
requestScaleUp(int desiredWorkers): void
```

Replacing with:

```text
requestScaleUp(long desiredWorkers): void
```

is a signature change that can break `MBeanServerConnection.invoke` and old JMX proxies even though the operation name is unchanged. If the API must expand, consider adding an overload or a new operation with a deprecation path, and test old clients against the new version.

For operations with side effects, contract tests must never accidentally invoke them in production just to verify existence. Inspect `MBeanInfo` for presence/signatures; run behavior tests in isolated environments with test data.

## 9. Notification Types Are Also Contracts

Notification listeners can subscribe by type using `NotificationFilterSupport`. If the type changes, old listeners stop receiving events:

```text
Before: com.example.jobs.queue.threshold
After:  com.example.jobs.queue.warning
```

Retrieve metadata:

```java
import javax.management.MBeanNotificationInfo;

for (MBeanNotificationInfo n : info.getNotifications()) {
    for (String type : n.getNotifTypes()) {
        System.out.println("notificationType=" + type);
    }
}
```

Metadata alone does not prove events fire properly. In a test environment, trigger a safe state transition, register a listener, and verify type, sequence, message/userData schema, and meaning. Never treat notifications as a durable message broker, since clients can miss events.

Document payloads clearly and ensure they contain no passwords/tokens/PII; changing `userData` types across releases can cause remote clients to fail deserialization or casting.

## 10. Distinguishing Breaking Changes from Compatible Changes

| Change type | Preliminary assessment |
| --- | --- |
| Change domain or `ObjectName` | Usually breaking for clients hard-coding names |
| Remove attribute | Breaking |
| Change attribute type | Can be breaking even when the type is "widened" |
| Read-only to writable | Opens mutation permissions; requires security review |
| Remove/rename operation | Breaking |
| Change signature or return type | Usually breaking |
| Add read-only attribute/operation | Usually additive, though review security surface |
| Add control operation | Structurally additive, yet high security risk |
| Change notification type | Breaking for type-filtering listeners |
| Add notification type | Additive; document semantics |
| Change descriptive text | Usually non-breaking for API, though may affect special tooling |
| Change getter/operation semantics | Can be breaking even with unchanged metadata |

Do not just check whether method names still exist. `getQueueDepth()` still returning an `int` while now counting delayed jobs too is a semantic change; dashboard alert thresholds may need updating.

## 11. Normalizing Snapshots for Stable Diffs

To avoid meaningless snapshot churn:

1. Canonicalize ObjectNames using `getCanonicalName()`.
2. Sort MBeans by ObjectName.
3. Sort attributes by name/type.
4. Sort operations by name + parameter type list + return type.
5. Sort notification types.
6. Exclude runtime timestamps, random PIDs, or instantaneous metric values from structural baselines.
7. Snapshot only domains/beans managed by your application.
8. Store descriptions separately if policy does not treat wording changes as compatibility contracts, preventing them from breaking CI.

A baseline should be easy to read and review in pull requests, such as JSON or Markdown. Never mix structural diffs with dynamic metric values like `QueueDepth=17`, as they make tests flaky.

## 12. Example Contract Test Using JUnit 5

Suppose a test initializes a Spring context with an MBean exporter, then inspects the MBeanServer used for registration. Key contracts can be asserted directly:

```java
import static org.junit.jupiter.api.Assertions.*;

import java.util.Arrays;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(JmxTestConfiguration.class)
class QueueJmxContractTest {
    @Autowired
    MBeanServer server;

    @Test
    void shouldPreserveQueueDiagnosticsContract() throws Exception {
        ObjectName name = new ObjectName(
            "com.example.jobs:type=QueueDiagnostics,name=Main"
        );

        assertTrue(server.isRegistered(name));
        MBeanInfo info = server.getMBeanInfo(name);

        assertTrue(Arrays.stream(info.getAttributes())
            .anyMatch(a -> a.getName().equals("QueueDepth")
                && a.getType().equals("int")
                && a.isReadable()
                && !a.isWritable()));

        assertTrue(Arrays.stream(info.getAttributes())
            .anyMatch(a -> a.getName().equals("CompletedCount")
                && a.getType().equals("long")
                && a.isReadable()
                && !a.isWritable()));
    }
}
```

`JmxTestConfiguration` is a project-defined Spring test configuration creating the management bean, exporter, and appropriate MBeanServer. In parallel test runs, consider dedicated MBeanServers or test namespaces to avoid ObjectName collisions across test contexts.

The example above is a structural contract test that invokes no state-mutating methods. You can add assertions for operation signatures/notification types and verify no sensitive attributes exist.

## 13. Testing Operation Signatures and Compatibility

```java
import java.util.Arrays;
import javax.management.MBeanOperationInfo;

private static boolean hasOperation(
        MBeanInfo info, String name, String... parameterTypes) {
    return Arrays.stream(info.getOperations()).anyMatch(op ->
        op.getName().equals(name)
        && Arrays.equals(
            Arrays.stream(op.getSignature())
                .map(p -> p.getType())
                .toArray(String[]::new),
            parameterTypes
        )
    );
}
```

In tests:

```java
assertTrue(hasOperation(info, "requestRefresh"));
assertTrue(hasOperation(info, "setWorkerLimit", "int"));
```

If return type and impact must be verified, add comparisons for `op.getReturnType()` and `op.getImpact()`. For overloaded methods, comparing only operation names is insufficient to pin down the contract.

## 14. Safe Behavior Testing

Structural contract tests do not catch all semantic changes. For critical APIs, add behavior tests:

- Management getters do not mutate business state.
- Getters return safe data with no secrets/PII.
- State-mutating operations validate input ranges.
- Operations adhere to documented idempotency or concurrency policies.
- Expected notification types fire on state transitions in test environments.
- Metric attributes preserve their units and definitions.
- Management APIs cause no significant side effects under frequent polling.

Run behavior tests with mock/fake services or isolated environments. Never invoke `clearCache`, `shutdown`, or `resetDatabase` in production to test "compatibility".

## 15. Testing JMX Proxy Compatibility

Spring `MBeanProxyFactoryBean` lets clients invoke MBeans via an interface. If the contract changes, old proxies may become incompatible.

Client-side example:

```java
public interface QueueManagementClient {
    int getQueueDepth();
    void requestRefresh();
}
```

After upgrading, contract tests can instantiate a proxy from the interface **of the supported client version** and call safe read-only methods, or inspect signatures via MBeanInfo.

```text
Old client interface + new MBean server
               |
               v
     Compatibility test suite
               |
        +------+-------+
        |              |
      PASS           BREAKING
```

If client and server upgrade independently, maintain a compatibility matrix instead of only building everything against the same new dependency version. A test using a freshly updated interface can miss that older clients are still running the previous version.

## 16. Impact of Spring AOP and Proxy Target-Class

AOP-proxied Spring beans can change their public surface when switching between JDK dynamic proxies and class-based proxies. `MBeanExporter`, assemblers, or metadata detection may see different interfaces/methods depending on configuration.

If a Spring upgrade changes proxy behavior or the application toggles `proxyTargetClass`, verify:

- The managed bean still registers under the expected ObjectName.
- Expected getters/operations remain in MBeanInfo.
- Annotation metadata is still read properly by the exporter.
- Call paths through the proxy still enforce transaction/security advice where needed.
- Methods present only on the concrete class are not accidentally exposed.

Relying solely on unit tests of the business service is insufficient; contract tests must run with a real Spring context and exporter.

## 17. Spring Boot Actuator Is a Separate Surface

In Spring Boot applications, Actuator endpoints can be exposed via JMX alongside custom Spring Framework MBeans. Configuration of these endpoints depends on the Boot version and exposure/access properties.

For example:

```properties
management.endpoints.jmx.exposure.include=health,info,metrics
```

Do not treat this property as an automatic filter for custom MBeans exported manually by `MBeanExporter`. After upgrading, inspect both groups: Actuator JMX endpoints and custom application MBeans, especially if naming domains, endpoint IDs, or included endpoints changed.

`management.endpoints.web.exposure.include` is independent of JMX exposure. An endpoint can still appear in JMX even if not exposed over HTTP, and vice versa.

## 18. Security Is Also Part of the Contract

Adding a writable attribute or a side-effecting operation is not merely a structural change. It can open control capabilities absent in the older release.

For example:

```text
Before:
  CacheSize: int, readable=true, writable=false

After:
  CacheSize: int, readable=true, writable=true
```

JMX users with broad write/invoke permissions can alter runtime behavior. Therefore, upgrade checks must verify:

- Do any new attributes return secrets, tokens, or PII?
- Are there unexpected new writable attributes?
- Do any new operations allow shutdown/reset/delete?
- Does the connector enforce matching authentication, authorization, TLS, and network policies?
- Are monitoring users restricted to read-only or allowed to invoke?
- Were any endpoints exposed due to wildcard/default config changes?

Never rely on the name `diagnostics` to conclude safety. Actual semantics and permissions determine risk.

## 19. Versioning and Deprecation Management

When changing a JMX API that already has clients, apply this progression:

1. **Additive first:** add new attributes/operations alongside the old contract when possible.
2. **Document:** clearly record the new API, old API, deprecation timing, and migration path.
3. **Dual support:** temporarily support both old and new names when sensible, taking care to avoid two MBeans performing duplicate side effects.
4. **Client migration:** update collectors, dashboards, JMX proxies, and scripts.
5. **Observe usage:** detect clients still using the old API via safe mechanisms without collecting secrets.
6. **Removal window:** remove the old API only after consumers are migrated and tested.

Parallel registration of two ObjectNames for the same resource is not always feasible. When done, establish clear ownership, lifecycle, and duplicate notification/operation semantics.

For unit changes—such as milliseconds to seconds—prefer creating a new attribute with a clear name and unit and deprecating the old attribute rather than silently changing semantics.

## 20. Pre- and Post-Upgrade Checklist

### Before upgrading

- [ ] List supported MBeans and the owner of each ObjectName.
- [ ] Snapshot MBeanInfo for attributes, operations, and notifications.
- [ ] Document schemas, semantics, units, security, and side effects.
- [ ] List dependent clients: dashboards, collectors, JMX proxies, scripts.
- [ ] Record Spring/JDK/Boot versions and active profiles.
- [ ] Have contract tests running on the current version as a baseline.

### After upgrading

- [ ] Re-run tests with the real context/exporter.
- [ ] Diff normalized ObjectNames and metadata, not just startup checks.
- [ ] Confirm legacy getters remain readable with legacy types.
- [ ] Confirm operation signatures and notification types did not change unexpectedly.
- [ ] Verify new attributes return no secrets and did not become writable unintentionally.
- [ ] Test JMX proxies of all still-supported client versions.
- [ ] Check registration policy, duplicate ObjectNames, and cleanup/redeploy behavior.
- [ ] Check Actuator JMX exposure/access configuration if using Spring Boot.
- [ ] Update runbooks, monitoring, dashboards, security docs, and release notes.

## 21. Common Pitfalls

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Service starts cleanly, dashboard loses metrics | Attribute/ObjectName changed | Compare baseline and runtime MBeanInfo |
| JMX proxy throws AttributeNotFoundException | Getter or naming differs from old release | Keep alias/compatibility or update client |
| `invoke` throws ReflectionException | Operation signature changed | Contract test parameter types and order |
| Listeners miss notifications | Notification type changed or registration differs | Keep old type or migrate subscriptions systematically |
| Tests pass only because they run against new client | Old-client compatibility untested | Run matrix against supported interfaces/clients |
| Duplicate MBean after upgrade/redeploy | Exporter/lifecycle/naming changed | Clarify owner and RegistrationPolicy |
| New endpoint exposed unintentionally | Auto-detection or wildcard exposure | Use allowlists and verify actual registry |
| Diff tests report excessive noisy changes | Snapshot lacks canonicalization/sorting | Normalize metadata before diffing |
| API still exists but semantics changed | Only metadata checked, no behavior tests | Add semantic tests and documentation |

## 22. CI/CD Integration Workflow

```text
Build new version
       |
       v
Start isolated Spring test context
       |
       v
Export MBeans to controlled MBeanServer
       |
       v
Collect canonical MBeanInfo snapshot
       |
       v
Compare with approved baseline
       |
       +--> Compatible: continue integration tests
       |
       +--> Breaking: require explicit migration review
       |
       v
Run safe behavior/security tests
       |
       v
Update contract docs + release notes
       |
       v
Deploy / monitor consumer compatibility
```

In parallel test suites, avoid multiple contexts registering the same ObjectName into the shared platform MBeanServer. Use a dedicated MBeanServer, isolated namespaces, or separate test JVMs. Never alter production ObjectNames merely to avoid test collisions.

Test suites should not execute every side-effecting operation indiscriminately. Use metadata tests for presence/signatures and invoke only operations designed safely for isolated environments.

## 23. Mental Model

```text
JMX API contract
  |
  +-- ObjectNames
  +-- Attributes (name/type/access)
  +-- Operations (name/signature/return/semantics)
  +-- Notifications (type/payload)
  +-- Security and lifecycle
  |
  v
Versioned baseline + documentation
  |
  v
Spring/JDK/Boot upgrade
  |
  v
Runtime MBeanInfo snapshot
  |
  v
Compatibility diff + safe behavior tests
  |
  +-- compatible -> update docs and deploy
  +-- breaking -> migration, deprecation, client changes
```

**Conclusion:** after upgrading Spring Framework, the JDK, or Spring Boot, **keep documentation and JMX contract tests updated** as part of the release process. Capture baselines from a real MBeanServer, canonicalize ObjectNames/metadata, compare attributes/operations/notifications, and include tests for semantics, security, lifecycle, and client compatibility. Proper documentation and tests prevent situations where the application "runs normally" while JMX monitoring and operational tooling are broken.
