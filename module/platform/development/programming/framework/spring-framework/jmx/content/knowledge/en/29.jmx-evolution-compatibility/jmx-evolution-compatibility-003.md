# Changing Attribute Types and Proxy Compatibility in Spring Framework JMX

## Learning Objectives

After this lesson, you will be able to:

- Understand that **the data type of a JMX attribute** is part of the management API contract, not just the attribute name.
- Distinguish between the Java type of a getter/setter, the type published in `MBeanAttributeInfo`, and the value received by a JMX client.
- Identify breaking changes when changing `int` to `long`, primitive to wrapper, `String` to enum, or a Java class to `CompositeData`/Open Type.
- Explain the roles of **Spring AOP proxies**, JDK dynamic proxies, class-based proxies, and target classes when the exporter discovers metadata and invokes attribute accessors.
- Understand why changing a method type on an interface or implementation can alter the JMX contract even when the attribute name and ObjectName remain unchanged.
- Design **management facades**, compatibility attributes, and migration plans to keep existing clients working.
- Use `MBeanServer.getMBeanInfo`, `getAttribute`, and integration tests to verify actual types before and after changes.
- Control read/write semantics and avoid bypassing transaction/security advice when changing proxies/exporters.

## 1. JMX Attributes Are Typed Contracts

In Java Management Extensions, an MBean can expose an attribute:

\`\`\`text
ObjectName: learning.jmx:type=Queue,name=Primary
Attribute: QueueDepth
Type: int
Readable: true
Writable: false
\`\`\`

A client may call:

\`\`\`java
Object value = connection.getAttribute(
    objectName,
    "QueueDepth"
);

Integer depth = (Integer) value;
\`\`\`

If a developer changes the getter:

\`\`\`java
@ManagedAttribute
public int getQueueDepth() {
    return service.depth();
}
\`\`\`

to:

\`\`\`java
@ManagedAttribute
public long getQueueDepth() {
    return service.depth();
}
\`\`\`

the JMX attribute may still be named `QueueDepth`, but the metadata type changes from `int` to `long` and the returned value may be boxed as `Long` instead of `Integer`.

Clients casting to `Integer` may encounter `ClassCastException`.

**First conclusion:** Preserving the attribute name is necessary, but **not sufficient** to guarantee JMX client compatibility. Types and semantics must be managed as part of the contract.

## 2. Elements That Form an Attribute Contract

A JMX attribute should be described across multiple dimensions:

| Element | Example | Risk when changed |
|---|---|---|
| MBean ObjectName | `learning.jmx:type=Queue,name=Primary` | Client cannot find MBean |
| Attribute name | `QueueDepth` | AttributeNotFoundException |
| JMX type | `int`, `long`, `java.lang.String` | Cast/conversion failure |
| Readability | `true` | Client can no longer read |
| Writability | `false` | Opens additional state mutation capability |
| Is-getter semantics | `isPaused()` | May change boolean getter metadata |
| Value semantics | Number of pending jobs | Client misinterprets data |
| Unit | Count, millis, bytes | Wrong alert thresholds |
| Nullability | Always present or nullable | Client cannot handle null |
| Representation | Primitive/String/Open Type | Different serialization/compatibility |
| Security policy | Which callers can read/write | Administrative risk |

Do not compare only source code or method names to claim a JMX API version is compatible with the previous one.

## 3. Published Type Is Not Identical to Runtime Boxed Class

A getter:

\`\`\`java
@ManagedAttribute
public int getActiveWorkers() {
    return 4;
}
\`\`\`

typically has metadata:

\`\`\`text
name=ActiveWorkers
type=int
\`\`\`

However, the Java API `MBeanServer.getAttribute(...)` returns `Object`. A primitive `int` value is boxed into `Integer`.

For example:

\`\`\`java
Object value = server.getAttribute(name, "ActiveWorkers");

System.out.println(value.getClass().getName());
// java.lang.Integer
\`\`\`

Similarly:

- `long` in metadata usually corresponds to `Long` in the returned value.
- `boolean` usually corresponds to `Boolean`.
- `double` usually corresponds to `Double`.

**Do not verify metadata by comparing against the runtime class name of the boxed value.** Use `MBeanAttributeInfo.getType()` for the type contract, and verify the runtime value separately.

## 4. Example: Changing int to long

Version 1:

\`\`\`java
@ManagedAttribute(description = "Processed requests since startup")
public int getProcessedRequests() {
    return processedRequests.intValue();
}
\`\`\`

Version 2:

\`\`\`java
@ManagedAttribute(description = "Processed requests since startup")
public long getProcessedRequests() {
    return processedRequests.longValue();
}
\`\`\`

The upgrade motivation is reasonable: `int` can overflow if the counter grows large. However, an old client might be written as:

\`\`\`java
Integer count = (Integer) connection.getAttribute(
    name, "ProcessedRequests"
);
\`\`\`

After changing the type, the cast fails.

If a client uses:

\`\`\`java
Number count = (Number) connection.getAttribute(
    name, "ProcessedRequests"
);

long value = count.longValue();
\`\`\`

it can adapt to several numeric types, but **do not rely on tolerant clients to skip contract migration**. Other scripts, exporters, and monitoring rules may still expect the old type.

Even a type change that fixes an overflow must be treated as schema evolution and communicated/tested accordingly.

## 5. Keep the Old Attribute, Add a New Attribute

A commonly clear migration approach is keeping the old attribute and adding an attribute whose name reflects the new type/range.

For example:

\`\`\`java
@ManagedResource(
    objectName = "learning.jmx:type=RequestMetrics,name=Primary"
)
public class RequestMetricsManagement {

    private final AtomicLong processed = new AtomicLong();

    @ManagedAttribute(
        description = "Legacy 32-bit processed request count"
    )
    public int getProcessedRequests() {
        long value = processed.get();

        // Conversion policy must be clearly defined.
        return value > Integer.MAX_VALUE
                ? Integer.MAX_VALUE
                : (int) value;
    }

    @ManagedAttribute(
        description = "64-bit processed requests since startup"
    )
    public long getProcessedRequestsLong() {
        return processed.get();
    }
}
\`\`\`

During the migration period:

- Old clients continue reading `ProcessedRequests` with type `int`.
- New clients use `ProcessedRequestsLong` with type `long`.
- Documentation clearly states that the legacy attribute uses a saturating value when exceeding `Integer.MAX_VALUE`, or another designed policy.
- Monitoring alerts do not silently interpret a clamped number as an exact total.
- Removing the legacy attribute later is a managed breaking change.

**Note:** Clamping to `Integer.MAX_VALUE` is just an example, not default Spring/JMX behavior. If the semantics require an exact cumulative count, clamping can be misleading; document it clearly or choose another suitable strategy.

## 6. Changing Primitive to Wrapper

For example, from:

\`\`\`java
@ManagedAttribute
public int getQueueDepth() {
    return depth;
}
\`\`\`

to:

\`\`\`java
@ManagedAttribute
public Integer getQueueDepth() {
    return depth;
}
\`\`\`

The attribute name may stay the same, but metadata can change from `int` to `java.lang.Integer`.

That creates a difference in the type contract and introduces the possibility of returning `null`.

Do not assume “autoboxing is automatic so JMX clients are unaffected”. JMX metadata describes the declared type, and some clients rely on the type string for conversion or validation.

When this refactoring brings no new management meaning, it is usually best to **preserve the old return type at the management facade**:

\`\`\`java
@ManagedAttribute
public int getQueueDepth() {
    Integer value = service.queueDepthOrNull();
    return value == null ? 0 : value;
}
\`\`\`

However, returning 0 on null must be semantically valid. If null means “no data available” rather than “empty queue”, returning 0 is semantically wrong. In that case, create a separate status attribute like `QueueDepthAvailable` or a new contract that explicitly represents missing data.

## 7. Changing String to Enum

A management getter might initially return:

\`\`\`java
@ManagedAttribute
public String getState() {
    return "RUNNING";
}
\`\`\`

After business refactoring:

\`\`\`java
public enum WorkerState {
    STARTING, RUNNING, PAUSED, FAILED
}
\`\`\`

If the JMX getter is changed to:

\`\`\`java
@ManagedAttribute
public WorkerState getState() {
    return service.state();
}
\`\`\`

the type contract changes, and a remote JMX client may need the matching enum class on its classpath or hit MBean adaptation limitations.

Way to keep the contract stable:

\`\`\`java
@ManagedAttribute
public String getState() {
    return service.state().name();
}
\`\`\`

Note that string value semantics still matter. If the enum adds a new state, clients switching on a fixed list must also be reviewed. Type compatibility does not automatically mean **value-set** compatibility.

## 8. Changing to Custom Objects and Open Types

An MBean attribute previously returned `String`:

\`\`\`java
@ManagedAttribute
public String getSummary() {
    return "pending=5,active=2";
}
\`\`\`

Later you want to return an object:

\`\`\`java
public record QueueSummary(long pending, long active) {
}
\`\`\`

Exposing a custom Java object directly via Standard MBean/remote JMX may require the class to be serializable and clients to have the corresponding class on their classpath; do not assume every client will decode it successfully.

For widely used JMX systems, consider:

- Separate primitive/String attributes.
- `CompositeData`, `TabularData`, or Open Types where appropriate.
- An MXBean contract, when you want Java types mapped to Open Types according to MXBean rules.
- A different API with explicit schema/versioning if data is richly structured.

**Important:** Switching from a Standard MBean to an MXBean or Open Type representation can alter metadata types and runtime values. Verify `MBeanInfo` together with actual `getAttribute` data, not just the Java return type.

## 9. Setters and Read/Write Compatibility

Suppose a writable attribute:

\`\`\`java
@ManagedAttribute
public int getMaxWorkers() {
    return maxWorkers;
}

@ManagedAttribute
public void setMaxWorkers(int value) {
    validate(value);
    maxWorkers = value;
}
\`\`\`

When the getter changes to `long` while the setter still accepts `int`, JavaBeans/JMX getter-setter compatibility rules can cause metadata to behave unexpectedly or the exporter to error depending on the assembler.

Do not let a getter and setter have different types without an explicit design.

If the contract must change from `int` to `long`:

1. Identify the impact on reading clients.
2. Identify the impact on clients writing via `setAttribute`.
3. Ensure getter/setter have compatible types per metadata.
4. Check `MBeanAttributeInfo.getType()`, `isReadable()`, `isWritable()`.
5. Test writing values across the JMX boundary.
6. If it is a major breaking change, expose a new attribute instead of changing in place.

## 10. How Do Spring AOP Proxies Relate to Attribute Types?

Spring AOP can return a proxy instead of the target bean:

\`\`\`text
Spring ApplicationContext
       |
       v
AOP proxy (JDK dynamic proxy / class-based proxy)
       |
       v
Target service
\`\`\`

This matters when the JMX exporter determines the bean type, reads annotation metadata, and invokes accessors.

For example, a target class:

\`\`\`java
@ManagedResource(
    objectName = "learning.jmx:type=WorkerPool,name=Primary"
)
public class WorkerPoolServiceImpl implements WorkerPoolService {

    @ManagedAttribute
    public long getCompletedTasks() {
        return completed.get();
    }

    // ...
}
\`\`\`

If a JDK dynamic proxy implements only `WorkerPoolService` and the interface does not contain `getCompletedTasks()`, the exporter needs to identify target metadata and an appropriate invocation path. Otherwise, the attribute may not appear or may not be invocable through the proxy under a given configuration.

Class-based proxies usually preserve more public methods of the concrete class, though not with absolute guarantees; final classes/methods and other factors can still interfere.

**Do not conflate “changing attribute type” with “changing proxy type”.** These are two independent variables and must be tested separately.

## 11. JDK Dynamic Proxy and Interface Contracts

Example interface:

\`\`\`java
public interface WorkerPoolService {
    int getActiveWorkers();
}
\`\`\`

Implementation:

\`\`\`java
public class WorkerPoolServiceImpl implements WorkerPoolService {

    @Override
    public int getActiveWorkers() {
        return 4;
    }
}
\`\`\`

If you want to change the interface method type to `long`, the Java interface contract must also change. A change such as:

\`\`\`java
public interface WorkerPoolService {
    long getActiveWorkers();
}
\`\`\`

can require updating implementations and every Java client compiled against the interface. For JMX, type metadata may change if operations/attributes are exposed from the new method.

In a JDK proxy, the method surface implemented by the proxy usually comes from its interfaces. Therefore, changing an interface method is a significant change for both the Java API and the JMX API when they share it.

**Solution:** Separate the **management facade** from the service interface so Java refactoring does not automatically pull in JMX type changes.

## 12. Management Facades Preserve JMX Types

The new business service has type `long`:

\`\`\`java
public interface WorkerPoolService {
    long activeWorkerCount();
}
\`\`\`

Facade keeping the old contract:

\`\`\`java
@ManagedResource(
    objectName = "learning.jmx:type=WorkerPool,name=Primary"
)
public class WorkerPoolManagement {

    private final WorkerPoolService service;

    public WorkerPoolManagement(WorkerPoolService service) {
        this.service = service;
    }

    @ManagedAttribute
    public int getActiveWorkers() {
        long value = service.activeWorkerCount();

        if (value > Integer.MAX_VALUE) {
            throw new IllegalStateException(
                "Active worker count exceeds legacy int range"
            );
        }
        return Math.toIntExact(value);
    }

    @ManagedAttribute
    public long getActiveWorkersLong() {
        return service.activeWorkerCount();
    }
}
\`\`\`

Here:

- The service API can use `long` as required by business logic.
- Legacy JMX `ActiveWorkers` remains `int`.
- The new attribute `ActiveWorkersLong` has a `long` contract.
- If the value exceeds the legacy range, the published policy is explicit: throw an error instead of silently overflowing.

This is only an illustrative policy; in production, you might consider clamping, an unavailable flag, separate metrics, or cutting over via a new version. What matters is **never silently corrupting numbers**.

The facade can call the Spring service proxy to preserve required transaction/security/logging advice, instead of registering the raw target outside the Spring lifecycle.

## 13. Do Not Use Runtime Proxy Class as a Contract

Anti-pattern example:

\`\`\`java
String objectName =
    "learning.jmx:type=" + bean.getClass().getSimpleName();
\`\`\`

If `bean` is a JDK proxy or class-based proxy, the runtime class name can change depending on Spring/JDK versions or AOP configuration.

Keep ObjectName explicit:

\`\`\`java
@ManagedResource(
    objectName = "learning.jmx:type=WorkerPool,name=Primary"
)
\`\`\`

At the same time, keep getter names and return types on the management facade stable. An unchanged ObjectName with altered metadata types can still break old clients.

## 14. Do Not Unwrap Proxies to “Fix Types” and Lose Advice

A hasty workaround is extracting the target object behind a Spring AOP proxy and exporting it directly.

Risks:

- JMX invocations bypass security advice or transaction interceptors.
- The target is not a valid Standard MBean without a wrapper/assembler.
- MBean lifecycle is no longer tightly managed by the Spring exporter.
- Metadata may differ from the proxy interface used by the application.
- A change in target lifecycle/scope may leave stale registrations.

Instead, the management facade should call the **Spring-managed service proxy**. If you deliberately need to export a proxy, define a clear management interface, check method visibility, and test invocation through JMX.

There is no absolute rule saying “always export target” or “always export proxy”; the goal is to publish a stable management contract and preserve the proper call path.

## 15. Using AopUtils to Inspect Proxies

In Spring AOP:

\`\`\`java
import org.springframework.aop.support.AopUtils;

Object bean = context.getBean("workerPoolService");

System.out.println(
    "Runtime class: " + bean.getClass().getName()
);
System.out.println(
    "Target class: " + AopUtils.getTargetClass(bean)
);
System.out.println(
    "Is proxy: " + AopUtils.isAopProxy(bean)
);
System.out.println(
    "JDK proxy: " + AopUtils.isJdkDynamicProxy(bean)
);
System.out.println(
    "Class proxy: " + AopUtils.isCglibProxy(bean)
);
\`\`\`

The output helps diagnose:

- Is the bean actually a proxy?
- Does the proxy use interfaces or the target class?
- Which target class holds the JMX metadata?
- Are the methods present on the proxy interface?

However, `AopUtils` does not replace verifying the JMX contract after export. Use `MBeanInfo` to see what clients actually observe.

## 16. MBeanInfo: Source of Truth for Actual Types

MBeanServer provides:

\`\`\`java
MBeanInfo info = server.getMBeanInfo(objectName);
\`\`\`

For each attribute:

\`\`\`java
for (MBeanAttributeInfo attribute : info.getAttributes()) {
    System.out.printf(
        "%s type=%s read=%s write=%s%n",
        attribute.getName(),
        attribute.getType(),
        attribute.isReadable(),
        attribute.isWritable()
    );
}
\`\`\`

This might output:

\`\`\`text
ActiveWorkers type=int read=true write=false
ActiveWorkersLong type=long read=true write=false
\`\`\`

If the exporter/assembler or proxy strategy changes, compare metadata before/after on the same logical ObjectName.

A contract test can check specifically:

\`\`\`java
boolean unchanged = java.util.Arrays.stream(
    server.getMBeanInfo(name).getAttributes()
).anyMatch(a ->
    "ActiveWorkers".equals(a.getName())
    && "int".equals(a.getType())
    && a.isReadable()
    && !a.isWritable()
);

if (!unchanged) {
    throw new AssertionError(
        "JMX ActiveWorkers contract changed"
    );
}
\`\`\`

This test catches breaking changes that the Java compiler cannot automatically detect for string-based JMX clients.

## 17. Testing Both Metadata and Returned Values

Checking MBeanInfo alone is not enough if actual values or semantics changed.

For example:

\`\`\`java
Object value = server.getAttribute(name, "ActiveWorkers");

assertInstanceOf(Integer.class, value);
assertEquals(4, value);
\`\`\`

After adding the long attribute:

\`\`\`java
Object wider = server.getAttribute(
    name,
    "ActiveWorkersLong"
);

assertInstanceOf(Long.class, wider);
assertEquals(4L, wider);
\`\`\`

When testing proxies, also verify that method invocations go through the expected call path, especially if a getter has authorization/transaction advice or the service uses proxy scopes.

If attributes return state from the same service, verify semantics at the same point in time rather than only checking types.

## 18. Practical Testing with Spring Context and Proxies

An integration test can be structured as follows:

1. Create an ApplicationContext with the target service and AOP configuration.
2. Enable the Spring JMX exporter for the management facade.
3. Obtain the configured MBeanServer.
4. Assert ObjectName is registered.
5. Use MBeanInfo to verify attribute name/type/read/write.
6. Call getAttribute via MBeanServer.
7. Verify runtime value class and semantics.
8. If testing JDK proxy/class proxy, run the test under both configurations.
9. Close the context and verify MBeans owned by the exporter are unregistered.

Example JUnit skeleton:

\`\`\`java
@Test
void jmxTypeContractRemainsStable() throws Exception {
    try (AnnotationConfigApplicationContext context =
            new AnnotationConfigApplicationContext(
                JmxTestConfiguration.class)) {

        MBeanServer server = context.getBean(
            "testMBeanServer", MBeanServer.class
        );

        ObjectName name = new ObjectName(
            "learning.jmx:type=WorkerPool,name=Primary"
        );

        assertTrue(server.isRegistered(name));

        MBeanAttributeInfo attribute = Arrays.stream(
            server.getMBeanInfo(name).getAttributes()
        ).filter(a -> "ActiveWorkers".equals(a.getName()))
         .findFirst()
         .orElseThrow();

        assertEquals("int", attribute.getType());
        assertTrue(attribute.isReadable());
        assertFalse(attribute.isWritable());

        Object result = server.getAttribute(name, "ActiveWorkers");
        assertInstanceOf(Integer.class, result);
    }
}
\`\`\`

`JmxTestConfiguration` must be defined in the test project to create the corresponding server, managed resource, proxy, and exporter. Using a dedicated server avoids collisions with the platform MBeanServer in parallel test runs.

## 19. Comparing JDK Proxy and Class-Based Proxy

An AOP configuration change can switch a runtime bean from a JDK proxy to a class-based proxy.

| Characteristic | JDK proxy | Class-based proxy |
|---|---|---|
| Method surface | Methods on proxy interfaces | Most methods of the target class can be proxied |
| Castability | Usually cast to interface | Can cast to target superclass |
| JMX metadata on target | Requires exporter/assembler to handle target metadata and invocable methods | Often sees concrete methods more easily |
| Constraints | Methods absent from interface may not be invocable via proxy | Final classes/methods can limit interception |
| Impact on type contract | Depends on interfaces and exporter | Depends on target methods and exporter |

`proxyTargetClass=true` can be helpful in some cases, but **is not a compatible way to change JMX types**. Choosing a proxy strategy is an AOP decision; choosing a JMX attribute type is management API design. The two decisions must be verified independently.

## 20. Checking the Impact of Method-Level Security

Suppose a service getter:

\`\`\`java
@PreAuthorize("hasAuthority('VIEW_WORKER_POOL')")
public long activeWorkerCount() {
    return count.get();
}
\`\`\`

If the management facade calls the Spring-managed service proxy, method-level security advice can run as configured.

However, if the raw target is exported directly and the getter is called, the advice may be bypassed. Moreover, JMX connector authentication/authorization is a separate layer; HTTP security filters do not automatically protect JMX.

When changing an attribute type and modifying proxies/exporters at the same time, test:

- Authorized clients read successfully.
- Unauthorized clients are denied.
- Type metadata and values remain accurate.
- Operations/writable attributes do not accidentally widen permissions.
- Security advice actually executes on the JMX call path.

Do not rely solely on seeing `@PreAuthorize` in source code to claim JMX is protected.

## 21. Type Changes with Remote JMX Carry Extra Risks

Remote JMX can transfer values over connectors and serialization. Simple primitives, wrappers, and Strings usually involve less complexity than custom objects.

When changing the type to a new class:

- Does the remote client's classpath contain that class?
- Is the value serializable under the connector mechanism?
- Have `serialVersionUID` or fields changed?
- Are MXBean mappings/Open Types used?
- How much does data size increase?
- How do clients handle nulls or new fields?
- Are there security policies for newly exposed data?

Even when an in-process JMX client works, remote clients can still encounter decoding or compatibility failures.

For management interfaces serving diverse clients, prefer types with clear contracts and minimal coupling to specific Java implementations.

## 22. Attribute Type Migration Plan

If an `int` attribute needs to be replaced with `long`, proceed with these steps:

1. **Inventory consumers:** scripts, dashboards, JMX exporters, operational tools, and client apps.
2. **Freeze current contract:** ObjectName, attribute name, type, readability, writability, unit.
3. **Add new contract:** a `...Long` attribute or a name expressing the new semantics.
4. **Keep legacy attribute:** continue returning the old type according to a defined conversion policy.
5. **Update clients:** use the new type or handle `Number` where appropriate.
6. **Monitor adoption:** confirm consumers have migrated; avoid removing prematurely.
7. **Write compatibility tests:** assert both old and new during the migration window.
8. **Test proxy strategies:** if AOP is changing, verify the call path.
9. **Plan removal:** deprecate according to release/support policy.
10. **Deploy with rollback:** if old clients fail, have a path to restore the contract.

A type change should be treated as schema evolution, not a simple Java refactoring.

## 23. Common Pitfalls

| Symptom | Possible cause | Resolution |
|---|---|---|
| Client casting `Integer` fails after deploy | Getter changed from `int` to `long` | Keep legacy int attribute or update consumer |
| Attribute name unchanged but tool reports type mismatch | `MBeanAttributeInfo.getType()` changed | Contract test, migration |
| Attribute disappears after enabling AOP | Exporter did not handle proxy/target metadata as expected | Check AopUtils, assembler, and registration |
| JDK proxy does not expose getter | Method is missing from proxy interface | Use facade, management interface, or proper config |
| CGLIB still fails | Final method/class or other exporter issue | Diagnose MBeanInfo and call path |
| SetAttribute rejected | Setter type or writability changed | Check getter/setter and MBeanAttributeInfo |
| Remote client cannot deserialize | Changed to custom object type | Open Types/MXBean or simple contract |
| Unexpected enum value breaks client | Value set expanded | Tolerant client + documented states |
| Type stable but values wrong | Silent unit/semantics change | Keep conversion or create new attribute |
| Security advice does not run | Raw target exported, bypassing proxy | Facade calls service proxy, test JMX path |
| Context shutdown removes other MBeans | Exporter ownership/ObjectName collision | Separate naming and test lifecycle |

## 24. Hands-on Exercises

### Exercise 1 — Detect a breaking change

Initial getter:

\`\`\`java
@ManagedAttribute
public int getProcessedJobs() { return 100; }
\`\`\`

After change:

\`\`\`java
@ManagedAttribute
public long getProcessedJobs() { return 100L; }
\`\`\`

Write an MBeanInfo test confirming type `int`. After changing the getter, explain why the test must fail and why clients casting Integer may be affected.

### Exercise 2 — Compatibility facade

The new service only provides `long activeWorkerCount()`. Design a facade exposing `ActiveWorkers` of type `int` for old clients and `ActiveWorkersLong` of type `long` for new clients. Define a policy if the value exceeds the int range.

### Exercise 3 — Primitive vs wrapper

Try changing a getter from `int` to `Integer`. Inspect `MBeanInfo.getAttributes()` and runtime `getAttribute`. Explain the difference between metadata type and boxed value class.

### Exercise 4 — Proxy strategy

Create a target service with an interface and a real AOP advisor. Run tests with a JDK dynamic proxy and a class-based proxy. Check ObjectName, attribute name, type, and readability via JMX.

### Exercise 5 — Remote type compatibility

A custom MBean attribute returns a `QueueSummary` class object. A client running in another JVM lacks this class. Propose a contract using primitive attributes or CompositeData/MXBean to reduce coupling.

## 25. Checklist When Changing Attribute Types

1. Does ObjectName change?
2. Does attribute name change?
3. What are the metadata types before/after?
4. What boxed type does the runtime value have?
5. Do readable/writable semantics change?
6. Do getter/setter have compatible types?
7. Do units and nullability change?
8. Do any clients directly cast primitive wrappers?
9. Are there new remote serialization/classpath dependencies?
10. Do proxy interfaces/target methods change?
11. Does the exporter still discover metadata properly?
12. Do invocations pass through required advice?
13. Are there contract tests via MBeanInfo and getAttribute?
14. Is there a deprecation/migration plan?
15. Is there a rollback plan if consumers fail?

## 26. Key Takeaways

- **The type of a JMX attribute is part of the contract**, just like its name and ObjectName.
- `int` vs `long`, primitive vs wrapper, String vs enum/custom object can create critical runtime/metadata differences.
- Do not rely on autoboxing to claim compatibility for JMX clients.
- Spring AOP proxies can affect metadata discovery and method invocation; verify MBeanInfo on the actual exported bean.
- Management facades keep JMX types and naming stable while the service API evolves.
- Do not bypass proxies just to fix JMX metadata if transaction/security advice is required.
- When a type change is required, adding a new attribute and migrating in a controlled way is usually safer than changing in place.
- Test metadata, returned values, writable semantics, remote representation, and lifecycle.

## References

- Spring Framework JMX Reference: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework AOP Proxying: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Framework API — ManagedAttribute: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedAttribute.html
- Spring Framework API — AopUtils: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/aop/support/AopUtils.html
- Java SE 21 API — MBeanAttributeInfo: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanAttributeInfo.html
- Java SE 21 API — MBeanServer: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
