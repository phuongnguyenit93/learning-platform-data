# Impact of Multiple ApplicationContext Initialization Order on JMX Registration Policy

## 1. The Problem: Multiple Contexts Sharing One MBeanServer

In a Spring Framework application, there is not always only a single `ApplicationContext`. A system may have a root context and a servlet context, multiple independently loaded modules, multiple test contexts running in the same JVM, or separate contexts for different components. Each context may create an `MBeanExporter` to expose its beans via Java Management Extensions (JMX).

**The problem arises when two exporters in two contexts try to register the same `ObjectName` on the same `MBeanServer`.** ObjectName is the unique identifier of an MBean in that registry. Who registers first, which registration policy each exporter uses, and which context closes first can all change which MBean clients observe.

Example:

```text
JVM
 |
 +-- Platform MBeanServer
 |     |
 |     +-- demo.orders:type=Monitor,name=primary
 |
 +-- ApplicationContext A
 |     +-- OrderMonitor A
 |     +-- MBeanExporter A
 |
 +-- ApplicationContext B
       +-- OrderMonitor B
       +-- MBeanExporter B

Both A and B want to use:
demo.orders:type=Monitor,name=primary
```

To handle this, Spring `MBeanExporter` provides **registration policies** to decide how to react when an ObjectName is already registered. However, a policy only resolves **registry conflicts**; it does not define which module holds ownership or guarantee that observed data matches operational intent.

Lesson objectives:

- Understand the boundary between `ApplicationContext` and `MBeanServer`.
- Distinguish the three policies: `FAIL_ON_EXISTING`, `IGNORE_EXISTING`, and `REPLACE_EXISTING`.
- Analyze results when the initialization order of A and B is reversed.
- Understand the difference between registration, visibility takeover, and shutdown cleanup.
- Build an ObjectName and ownership strategy to avoid collisions.
- Practice inspecting actual runtime state rather than guessing merely from application startup success.

## 2. ApplicationContext Is Not an Independent JMX Namespace

Each Spring `ApplicationContext` has its own bean registry, lifecycle, and `BeanFactory`. However, JMX uses `MBeanServer` as the management point for MBeans.

```text
ApplicationContext A              ApplicationContext B
   bean name: monitor               bean name: monitor
          |                                 |
     MBeanExporter A                  MBeanExporter B
          |                                 |
          +-----------+---------------------+
                      |
           same platform MBeanServer
                      |
       ObjectName: demo:type=Monitor
```

Two beans can share the same **Spring bean name** in two different contexts without colliding inside the two bean factories. Conversely, if exporters generate the same **JMX ObjectName** in one MBeanServer, a conflict occurs even if their bean names, class loaders, or modules differ.

Three identities must be distinguished:

| Identity | Scope | Example |
|---|---|---|
| Spring bean name | BeanFactory/ApplicationContext | `orderMonitor` |
| JMX ObjectName | One `MBeanServer` | `demo.orders:type=Monitor,name=primary` |
| Java object identity | One instance in the JVM | `OrderMonitor@...` |

These identities are **not equivalent**. One ObjectName can point to different instances at different times if the MBean is unregistered and re-registered. JMX clients normally rely on ObjectName to locate objects, so changing “who stands behind the name” can have a larger impact than a single startup error.

## 3. Three Important Registration Policies

Spring provides `org.springframework.jmx.support.RegistrationPolicy` with commonly used options:

| Policy | When ObjectName Does Not Exist | When ObjectName Already Exists | Consequences to Note |
|---|---|---|---|
| `FAIL_ON_EXISTING` | Registers new MBean | Fails with an error | Detects collisions early; may cause context refresh to fail |
| `IGNORE_EXISTING` | Registers new MBean | Skips new registration | Later context can start normally, yet the visible MBean still belongs to the earlier context |
| `REPLACE_EXISTING` | Registers new MBean | Replaces existing registration per exporter mechanism | Context initialized later can swap out the managed object |

Configuration typically follows this pattern:

```java
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.support.RegistrationPolicy;

MBeanExporter exporter = new MBeanExporter();
exporter.setRegistrationPolicy(RegistrationPolicy.FAIL_ON_EXISTING);
```

**Do not equate registration policy with authentication or authorization.** The policy decides behavior when a JMX name collides; it does not check whether context A is “authorized” to replace context B from a business-boundary standpoint.

### 3.1. FAIL_ON_EXISTING

This is the right choice when **duplicate ObjectNames are a configuration error** and the team wants immediate detection. If context B registers an ObjectName already claimed by A, registration fails, usually causing an exception during exporter initialization or context refresh.

The advantage is avoiding silently using the wrong data source. The downside is that in systems with multiple contexts lacking clear naming design, later module startup can be blocked.

### 3.2. IGNORE_EXISTING

If the name already exists, the later exporter does not replace the current MBean. This avoids collision startup errors in some setups, at the cost of a trade-off: **the MBean visible in JConsole may represent the context started earlier rather than the context that just started**.

If monitor A returns `module=A` and monitor B returns `module=B` with the same ObjectName, JMX clients continue seeing A when B uses IGNORE. Team B should not conclude “B was exported” merely because B started without errors.

### 3.3. REPLACE_EXISTING

The later exporter can replace the existing registration. In a sequential experiment, if A registers first and B replaces it, the ObjectName can point to B's MBean.

However, this outcome must be understood as **swapping the object behind the name**, not a mechanism to “merge two monitors”. JMX clients that cached metadata, state, or subscriptions may need to refresh. If the two MBeans have different contracts, a stable ObjectName does not guarantee `MBeanInfo` remains unchanged.

Do not use REPLACE as a fix for duplicate names when MBean ownership is unknown. Replacing a platform MBean or another module's MBean can break that component's observability.

## 4. Initialization Order Matrix: A Then B or B Then A

Suppose both contexts use the same MBeanServer and the same ObjectName `demo:type=Status`. MBean A returns `Source=A`, and MBean B returns `Source=B`.

### 4.1. Both A and B Use FAIL_ON_EXISTING

```text
Initialize A -> A registers successfully
Initialize B -> B hits collision and fails
Active MBean -> A
```

If the order is reversed:

```text
Initialize B -> B registers successfully
Initialize A -> A hits collision and fails
Active MBean -> B
```

Thus, with identical source code and policies, **the context initialized first determines who wins**, while the one arriving later fails. This explains bugs that only appear when changing module startup order or running integration tests.

### 4.2. Both A and B Use IGNORE_EXISTING

```text
A first, B second -> A registers; B skips -> JMX sees A
B first, A second -> B registers; A skips -> JMX sees B
```

Both contexts can run without obvious collision errors, yet the observed outcome depends on initialization order. This is a dangerous monitoring bug: a dashboard may be reading metrics from a different module than the one thought to be exported.

### 4.3. Both A and B Use REPLACE_EXISTING

```text
A first, B second -> B replaces A -> JMX sees B
B first, A second -> A replaces B -> JMX sees A
```

In a sequential flow with no other actors, the context **registering last** typically determines the final instance. Under concurrent initialization, the result also depends on the actual timing of registration calls. Do not assume “bean creation order” from configuration listings equals the moment registration finishes.

### 4.4. Two Contexts Using Different Policies

Look at the policy on the **exporter acting second** when the name already exists:

| Context Created First | Policy of Context Created Second | Collision Outcome |
|---|---|---|
| A already registered | B = FAIL | B errors, A remains the active registration |
| A already registered | B = IGNORE | B skips, A remains visible |
| A already registered | B = REPLACE | B replaces A |
| B already registered | A = FAIL | A errors, B remains the active registration |
| B already registered | A = IGNORE | A skips, B remains visible |
| B already registered | A = REPLACE | A replaces B |

The earlier context's policy may affect prior registrations and later cleanup; however, at the moment the later context encounters an existing name, it is the policy of the exporter attempting registration that governs first.

## 5. Do Not Forget Lifecycle and Unregistration

Collisions do not only occur at startup. When a context closes, `MBeanExporter` typically unregisters the MBeans it manages as part of its lifecycle. In multi-context systems, shutdown timing can complicate things:

```text
T1: Context A registers ObjectName X
T2: Context B appears, policy allows replacing X
T3: Context A closes
T4: Context B continues running
```

You must know **which exporter tracks ownership of which registration** and how your Spring version/configuration handles cleanup, especially with REPLACE. Do not assume closing A will restore MBean A, nor assume B stays intact if another component touches the registry.

At the JMX level, an ObjectName points to **one registration at a time**. Replacing a registration does not mean JMX keeps a stack of versions to automatically “revert” to the previous MBean.

A proper verification workflow includes:

1. Query ObjectName and `MBeanInfo` after A starts.
2. Query again after B starts.
3. Query after A closes.
4. Query after B closes.
5. Record whether the registration still exists and which bean it belongs to.

Every shutdown can alter the management surface. Do not check only startup and conclude everything is done.

## 6. Do Parent/Child ApplicationContexts Create Two JMX Registries?

Spring supports a parent/child context model: the child can look up beans from the parent via appropriate lookup rules, while the parent does not automatically see child beans. This **does not imply there are two MBeanServers**.

Example web application:

```text
Root ApplicationContext
  - DataSource
  - BusinessService
  - MBeanExporter (possible)

Child WebApplicationContext
  - Controller
  - WebMonitor
  - MBeanExporter (possible)

Both exporters -> JVM platform MBeanServer
```

Even though root and child are two separate ApplicationContexts, if both exporters register into the platform MBeanServer and produce the same ObjectName, they still collide.

Carefully examine:

- Do both contexts create exporters, or should the child rely on infrastructure managed by the parent?
- Do they share the same ObjectNamingStrategy?
- Are MBeans selected via explicit beans or autodetection?
- Does autodetection in each context scan the same bean types?
- Does the ObjectName reflect context/module/instance?

Do not enable exporters in both root and child out of habit if exportable beans are owned by only one of them. A clear ownership strategy is usually simpler than resolving conflicts with policies.

## 7. Hands-On Spring Example: Two Contexts, One MBeanServer

The example below uses one interface and two distinct monitor instances to test collisions. It uses two independent `AnnotationConfigApplicationContext`s sharing one platform MBeanServer.

### 7.1. Management Interface and Implementation

```java
// SourceMonitorMBean.java
public interface SourceMonitorMBean {
    String getSource();
}
```

```java
// SourceMonitor.java
public class SourceMonitor implements SourceMonitorMBean {
    private final String source;

    public SourceMonitor(String source) {
        this.source = source;
    }

    @Override
    public String getSource() {
        return source;
    }
}
```

Standard MBean based on the `SourceMonitorMBean` interface. `Source` is a read-only attribute. Two objects can return different values while sharing the same management type.

### 7.2. Factory Creating Contexts with MBeanExporter

```java
// ContextFactory.java
import java.lang.management.ManagementFactory;
import java.util.Map;
import javax.management.MBeanServer;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.support.RegistrationPolicy;

public final class ContextFactory {

    public static AnnotationConfigApplicationContext create(
            String source,
            RegistrationPolicy policy) {

        AnnotationConfigApplicationContext context =
            new AnnotationConfigApplicationContext();

        MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();

        context.registerBean(
            "sourceMonitor",
            SourceMonitor.class,
            () -> new SourceMonitor(source)
        );

        context.registerBean(
            "jmxExporter",
            MBeanExporter.class,
            () -> {
                MBeanExporter exporter = new MBeanExporter();
                exporter.setServer(server);
                exporter.setRegistrationPolicy(policy);
                exporter.setBeans(Map.of(
                    "demo.multicontext:type=SourceMonitor,name=shared",
                    context.getBean("sourceMonitor")
                ));
                return exporter;
            }
        );

        context.refresh();
        return context;
    }
}
```

Here each context has an `MBeanExporter` with the same ObjectName, differing only in `source` and `RegistrationPolicy`. Calling `context.getBean("sourceMonitor")` happens when Spring creates the exporter and the context already holds the monitor's BeanDefinition.

In real environments, beans can be declared via `@Configuration` and dependency injection. This factory simply makes swapping the policy across runs explicit.

### 7.3. Reading ObjectName from the Platform Server

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();
ObjectName name = new ObjectName(
    "demo.multicontext:type=SourceMonitor,name=shared"
);

if (server.isRegistered(name)) {
    System.out.println(
        "Currently visible: " +
        server.getAttribute(name, "Source")
    );
} else {
    System.out.println("No MBean registered at " + name);
}
```

### 7.4. Testing A Then B

```java
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.jmx.support.RegistrationPolicy;

public class MultiContextDemo {
    public static void main(String[] args) throws Exception {
        try (AnnotationConfigApplicationContext a =
                 ContextFactory.create(
                     "A", RegistrationPolicy.REPLACE_EXISTING
                 );
             AnnotationConfigApplicationContext b =
                 ContextFactory.create(
                     "B", RegistrationPolicy.REPLACE_EXISTING
                 )) {

            // Call the getAttribute snippet here to see the Source of
            // the active registration right after B starts.
            Thread.sleep(30_000L);
        }
    }
}
```

When using `REPLACE_EXISTING` for both A and B in this sequence, the ObjectName is expected to end up pointing to B. Reversing the two `create` calls reverses the expected result.

Next, try:

```java
RegistrationPolicy.IGNORE_EXISTING
RegistrationPolicy.FAIL_ON_EXISTING
```

With `FAIL_ON_EXISTING`, creating the second context can throw an exception. Run these combinations in **separate JVM processes** or ensure proper cleanup so results are not affected by MBeans from a previous run. Do not test against a shared production MBeanServer.

### 7.5. Why the Example Needs Runtime Re-Checks

The state after both starts is only half the problem. Extend the test to close A before B or B before A and observe. With `try-with-resources` as shown above, resources close in reverse order: B then A. To test closing A first, create contexts and intentionally call `a.close()` in `try/finally`, then inspect the registration.

Do not infer unregistration outcomes solely from the policy name. Cleanup impact is influenced by exporter lifecycle, ownership, MBeanServer behavior, and may vary across Spring versions.

## 8. Where Is RegistrationPolicy Configured?

With `MBeanExporter`:

```java
@Bean
public MBeanExporter exporter(
        MBeanServer server,
        SourceMonitor monitor) {

    MBeanExporter exporter = new MBeanExporter();
    exporter.setServer(server);
    exporter.setRegistrationPolicy(
        RegistrationPolicy.FAIL_ON_EXISTING
    );
    exporter.setBeans(Map.of(
        "demo.source:type=Monitor,name=primary",
        monitor
    ));
    return exporter;
}
```

For `AnnotationMBeanExporter`, the inherited exporter mechanism supports adjusting the registration policy via the corresponding configuration. When using `@EnableMBeanExport` or Spring Boot auto-configuration, check the actual API/configuration of your version rather than assuming you can inject a setter into a framework-created exporter without affecting its lifecycle.

**Rule:** configure ownership and naming first, and use policy as a safeguard for collision behavior. Policy should not be the sole tool coordinating multiple contexts.

## 9. Why Using IGNORE_EXISTING Can Hide Misconfigurations

Consider a system with two modules:

- Module A owns `InventoryMonitor`, returning `InventorySize=1200`.
- Module B also has an `InventoryMonitor` bean, returning `InventorySize=30`.
- Both exporters want to register `company.inventory:type=Monitor`.

If B initializes later with IGNORE, application logs may show no startup exception, yet the dashboard querying that ObjectName still reads `1200` from A.

The danger is that **ApplicationContext B runs normally while the JMX API team B thinks it exposed does not point to B**. When metrics look wrong, operators may mistakenly suspect getter caching bugs or that service B is not updating.

Therefore, if two distinct monitors are intended, use distinct ObjectNames or partition MBeanServers rather than using IGNORE to “share a name”.

## 10. Why REPLACE_EXISTING Can Destabilize Clients

A JMX client often holds an `ObjectName` and reads metadata:

```java
MBeanInfo info = connection.getMBeanInfo(name);
```

If another exporter replaces the MBean at the same ObjectName, client assumptions may no longer hold:

- Attributes may change name or type.
- Operations may be added or removed.
- Notification subscriptions may be affected by unregistration/re-registration.
- Counters may reset to the new instance's initial values.
- Charts may show sudden jumps that mislead operators.
- A call made between the two replacement steps may hit `InstanceNotFoundException` or other errors.

REPLACE is not a continuous state-transfer mechanism or a transaction for clients. If an MBean must be upgraded while keeping the same ObjectName, manage API versioning, rollout sequencing, registration/unregistration, and client metadata refresh.

## 11. Contexts Starting Concurrently: A Real Race Condition

In modular applications or test suites, two contexts may refresh concurrently in the same JVM.

```text
Thread 1 (Context A)           Thread 2 (Context B)
    |                               |
    +-- create exporter             +-- create exporter
    +-- register X                  +-- register X
    |                               |
             timing-dependent
```

Even if A begins refreshing earlier, B might reach `registerMBean` first due to different dependencies. Hence, **“context started creating first” does not always mean “context registered its MBean first”**.

With `FAIL_ON_EXISTING`, a context can fail intermittently depending on scheduling. With IGNORE, the winner can vary across runs. With REPLACE, the final registration can change depending on timing.

To eliminate races:

1. Have a single context/exporter responsible for a specific MBean.
2. Build ObjectNames distinguishing module, instance, or tenant when multiple MBeans are needed.
3. If startup ordering is required, use explicit orchestration instead of relying on thread timing.
4. Avoid running independent integration tests that share an ObjectName on a shared platform server without isolation/cleanup.
5. Verify the registry after every startup and shutdown phase.

Registration policy decides **what happens on a name collision**, not sequential ordering across threads.

## 12. Designing ObjectNames to Avoid Unnecessary Collisions

A good ObjectName uniquely describes the managed resource:

```text
company.orders:type=QueueMonitor,service=checkout,instance=worker-1
company.orders:type=QueueMonitor,service=checkout,instance=worker-2
company.cache:type=CacheMonitor,context=web
company.cache:type=CacheMonitor,context=background
```

If two instances are genuinely distinct, differentiate them in the `ObjectName`. If they represent the same logical resource, designate **one owner** responsible for registering the MBean instead of letting two contexts compete.

Several notes:

- The domain should describe a subsystem or owned namespace.
- Key properties should be stable and free of secrets.
- Avoid PID, timestamp, or random UUID if clients expect a stable name across restarts, unless an appropriate discovery mechanism exists.
- If multiple instances are needed, instance identifiers should be distinct enough without exposing sensitive user data.
- Use `ObjectName.quote(...)` when key values contain characters that require quoting.
- Avoid changing naming strategies across versions without updating dashboards, alerts, and scripts.

A consistent naming strategy is far more valuable than configuring `IGNORE_EXISTING` to mask all collisions.

## 13. When Should You Choose Each Policy?

### Choose FAIL_ON_EXISTING When

- Every ObjectName must have a single unique owner.
- Collisions indicate a configuration error that must be caught quickly.
- The system prioritizes JMX API correctness over “silent” startup.
- There is no valid reason for one module to take over another module's MBean.

This is the right policy to expose ownership issues in most applications.

### Choose IGNORE_EXISTING When

- A pre-registered MBean is intentionally allowed to be the authoritative source.
- Later exporters must not overwrite the existing registration.
- The team clearly understands that the new bean may **not be exported**.
- There is a way to verify who holds the ObjectName and colliding names are not used for different resources.

Do not use it merely to make startup succeed without errors.

### Choose REPLACE_EXISTING When

- Ownership and lifecycle for transferring registrations are clearly defined.
- Replacing an MBean is an intentional design action, such as during a controlled upgrade process.
- Clients and monitoring can handle metadata, notification, and counter changes.
- Shutdown/restart effects and conflicts with other modules have been tested.

Do not use REPLACE to automatically “fix” every ObjectName collision.

## 14. Distinguishing Registration Policy from Other Lifecycle Mechanisms

| Mechanism | Addresses | Does Not Guarantee |
|---|---|---|
| `RegistrationPolicy` | Handling when an ObjectName already exists | Startup order, business ownership |
| `@DependsOn` | Bean initialization order by dependency | External readiness or ordering across different JVMs |
| Constructor injection | Ensures dependencies required to construct a bean | Completion of background warm-up |
| `SmartLifecycle` | Phased start/stop of lifecycle beans | That all MBeans register in the exact desired order |
| `@Primary` / `@Qualifier` | Bean selection during injection | JMX ObjectName ownership selection |
| ObjectNamingStrategy | Generating ObjectNames | Permission to replace an already-registered MBean |
| JMX connector authorization | Controls what clients are permitted to invoke | Does not prevent two exporters in the same JVM from racing on a name |

For example, putting `@DependsOn("exporterA")` on exporter B may ensure A is created before B in the same context, yet if B uses REPLACE, B can still overwrite A. If they belong to two independent contexts, `@DependsOn` in one context does not define global ordering between both.

## 15. Integration Testing: Verifying Collisions and Cleanup

A good test should not merely assert that `ApplicationContext` creation succeeded. Inspect the ObjectName and actual values at every stage.

### 15.1. Steps

1. Prepare a dedicated test MBeanServer isolated from production resources.
2. Create context A with monitor `Source=A`.
3. Verify the ObjectName is registered and attribute `Source` returns A.
4. Create context B with the policy under test.
5. Verify startup result and attribute `Source` after B.
6. Close B and inspect the registry.
7. Close A and inspect the registry.
8. Reverse the order of A and B and repeat to observe ordering dependency.

### 15.2. Sample Assertions

```java
assertTrue(server.isRegistered(name));
assertEquals("A", server.getAttribute(name, "Source"));
```

When B uses IGNORE, `Source=A` is expected if A registered first with no third actor. When B uses REPLACE, `Source=B` is expected after B registers sequentially. When B uses FAIL, verify the appropriate exception and do not assert that B started successfully.

For shutdown, observe actual results rather than hard-coding unverified assumptions about ownership cleanup. Tests should unregister MBeans they created and close contexts in `finally` to avoid affecting subsequent cases.

### 15.3. Why Use an Isolated MBeanServer in Tests?

A JVM's platform MBeanServer can persist across multiple test classes. If an earlier test fails to clean up, a later test can hit false collisions or read stale state. A dedicated test MBeanServer keeps the registry under control, provided all exporters in the test use that same instance.

If a test strictly needs to observe platform MXBeans or attach JConsole, use the platform server in an isolated test JVM. Do not assume changing the MBeanServer in one context isolates components using the platform server via other APIs.

## 16. Common Misconceptions

### 16.1. “Context B started successfully, so B was exported”

False if B used IGNORE and A already claimed the name. You must read the JMX attributes or metadata of the ObjectName.

### 16.2. “Context A was created first, so A is always the owner”

Not guaranteed under concurrent startup; arrival order at the MBeanServer depends on timing. With REPLACE, a context registering later can replace A.

### 16.3. “Different Spring beans automatically have different ObjectNames”

Not automatically. ObjectNames are generated from naming strategies or mappings, not Java object identity.

### 16.4. “REPLACE saves the old MBean for restoration”

There is no such standard JMX contract. A replaced registration does not create a rollback stack. Explicit lifecycle and ownership management is required.

### 16.5. “Closing the later context always brings back the earlier MBean”

Do not assume this. Unregistration/re-registration and ownership depend on the exporter, policy, and shutdown order.

### 16.6. “Using @DependsOn eliminates all collisions”

`@DependsOn` only orders bean creation; two exporters can still use the same name, and the policy determines the response.

### 16.7. “Multiple contexts require multiple MBeanServers in JMX”

Not required. One MBeanServer can hold MBeans from multiple contexts as long as ObjectNames are unique. Choose servers based on discovery, management, and operational needs.

### 16.8. “Using IGNORE makes the system safer”

IGNORE avoids overwriting an existing registration, but can mask a configuration error leaving the new module unmonitored. Operational safety requires accurate metric sources and transparent ownership.

## 17. Security and Blast Radius

Registration policy is not a security mechanism. An exporter in the same JVM can interact with the MBeanServer it is configured to use; the policy does not verify whether a context is “permitted to claim this name” by business rules.

Practical risks:

- Replacing a security-monitoring MBean with another causes dashboards to lose critical metrics.
- IGNORE prevents a new module from appearing in monitoring even though the application started.
- ObjectNames containing sensitive tenant/user information.
- Exposing operations with side effects to clients with broad access.
- Remote JMX not properly restricted by network and identity.

Countermeasures:

- Define owners and naming conventions per module.
- Limit the number of exporters responsible for the same ObjectName region.
- Choose policies aligned with collision expectations.
- Audit MBean registrations/replacements in compliance-sensitive systems.
- Verify the presence and contents of `MBeanInfo` after startup.
- Protect JMX connectors with authentication, transport security, and proper authorization.
- Do not let clients rely blindly on an MBean name if metadata/implementation can be swapped unexpectedly.

## 18. Scenario-Based Practice

**Scenario A — FAIL.** Create two contexts both registering `demo:test=Monitor`. Start A then B with `FAIL_ON_EXISTING`. Record the exception, A's state, and the result of `isRegistered(name)`.

**Scenario B — IGNORE.** Start A first, B second with `IGNORE_EXISTING`. Read `Source` from JMX. Reverse the order and explain why the result changes.

**Scenario C — REPLACE.** Start A first, B second with `REPLACE_EXISTING`. Read `Source` before and after B. Close B and keep observing; do not assume A automatically returns.

**Scenario D — Parent/child.** Create a root and child context, each exporting a monitor while sharing the platform MBeanServer. Design ObjectNames distinguishing `context=root` and `context=web` and confirm both coexist.

**Scenario E — Race.** Start two contexts on two threads with the same ObjectName in a test environment. Record how many times A vs. B wins across multiple runs. Do not treat statistical outcomes as a contract; fix the design to avoid races via naming/ownership.

**Scenario F — Integration test cleanup.** Run each test in an isolated MBeanServer, close contexts in `finally`, and verify the registry contains no test-owned MBeans afterward.

## 19. Self-Check Questions

1. Do two different ApplicationContexts automatically get two separate MBeanServers?
2. How does `FAIL_ON_EXISTING` handle a duplicate ObjectName?
3. With `IGNORE_EXISTING`, why can the second context start successfully while dashboards still see the first context?
4. With `REPLACE_EXISTING`, what happens if the order of A and B is reversed?
5. Why doesn't starting refresh earlier guarantee registering the MBean earlier in parallel runs?
6. How does an ObjectName differ from a Spring bean name?
7. Is `@DependsOn` sufficient to prevent collisions between two contexts?
8. Why must you observe the registry state after one context closes?
9. What impacts can JMX clients experience when an MBean with the same name is replaced?
10. When should explicit ownership and distinct ObjectNames be chosen instead of IGNORE?

## 20. Key Takeaways

**Within the same MBeanServer, an ObjectName is unique even when MBeans come from multiple ApplicationContexts.** `FAIL_ON_EXISTING` catches collisions with an error; `IGNORE_EXISTING` keeps the existing registration; `REPLACE_EXISTING` lets the new exporter replace the old registration. Consequently, initialization order, registration timing, and shutdown order can all change which MBean clients observe.

Reliable design cannot rely on policy alone. Assign clear ownership for each MBean, choose non-colliding ObjectNames, use the appropriate exporter, verify runtime state after startup/shutdown, and secure the JMX plane with proper security controls.
