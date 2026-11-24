# Testing That Proxies or AOP Do Not Lose Metadata in Spring Framework JMX

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain why a Spring bean annotated with `@ManagedResource`, `@ManagedAttribute`, or `@ManagedOperation` can still lack JMX metadata when wrapped in an AOP proxy.
- Distinguish **target class**, **runtime proxy class**, **management interface**, and actual metadata returned by `MBeanServer.getMBeanInfo`.
- Understand the difference between **JDK dynamic proxies** and **class-based (CGLIB) proxies** when Spring discovers annotations and determines invocable methods.
- Write automated tests verifying `ObjectName`, attributes, operations, signatures, descriptions, and descriptors after `MBeanExporter` registers the MBean.
- Build negative tests to catch sensitive operations exported accidentally or management operations disappearing after adding `@Transactional`, `@Async`, `@Cacheable`, or another aspect.
- Test not only metadata, but also the **actual invocation path through the proxy**, avoiding false positives where annotations exist yet advice never runs.
- Design a dedicated management adapter that minimizes coupling to business service proxy details.
- Diagnose JMX export errors without confusing proxy issues with wrong `ObjectName`, naming strategy, registration policy, or wrong `MBeanServer`.

## 2. Problem: Metadata Can Change When a Bean Is Proxied

In Spring, methods are usually invoked on a bean obtained from `ApplicationContext`. When AOP is enabled, the object handed to consumers by the container may not be an instance of the original class, but a proxy wrapping that class.

```text
Source code
  @ManagedResource
  class WorkerManagement {
      @ManagedAttribute getQueueDepth()
      @ManagedOperation requestPause()
  }
             |
             v
Spring AOP infrastructure
             |
       +-----+------+
       |            |
 JDK proxy      CGLIB proxy
       |            |
       +-----+------+
             |
             v
        MBeanExporter
             |
             v
     MBeanInfoAssembler
             |
             v
         MBeanServer
             |
             v
  MBeanInfo seen by client
```

There are two independent questions:

1. **Is the bean exported?** Depends on the exporter, autodetection, metadata source, naming strategy, registration policy, and target server.
2. **Which members are exported?** Depends on the management interface, assembler, annotations, proxy/target class, and MBean type.

Adding AOP can affect both questions. For instance, if management annotations live on the implementation class while the runtime object is a JDK proxy directly exposing only the interface, and introspection fails to reach target-class annotations, the assembler may fail to recognize the resource or lose some method descriptions.

Do not assume every Spring version or every assembler hits this issue. Spring includes mechanisms supporting proxy introspection, yet **the result must be verified at runtime under your exact configuration**.

## 3. Defining the JMX Metadata to Preserve

`MBeanInfo` describes the MBean contract actually seen by clients. Items to verify:

| Group | Read API | Expected Example |
| --- | --- | --- |
| Identity | `ObjectName` | `com.example:type=Worker,name=Importer` |
| MBean description | `MBeanInfo.getDescription()` | Import worker monitoring |
| Attributes | `getAttributes()` | `QueueDepth` read-only |
| Attribute type | `MBeanAttributeInfo.getType()` | `long` |
| Writable flag | `MBeanAttributeInfo.isWritable()` | `false` |
| Operations | `getOperations()` | `requestPause()` |
| Operation return type | `MBeanOperationInfo.getReturnType()` | `void` |
| Operation signature | `MBeanOperationInfo.getSignature()` | `[]` or `int` |
| Operation description | `MBeanOperationInfo.getDescription()` | Request graceful pause |
| Parameter metadata | `MBeanParameterInfo` | name, type, description |
| Descriptor | `getDescriptor()` | fields actually created by the assembler |

The flag `isWritable=false` is metadata about the MBean's writability, not the current JMX account's permissions. Likewise, `impact` is operational metadata, not an authorization mechanism.

**Never test metadata by invoking every operation.** Read `getMBeanInfo` only to inspect the API surface; invoking operations can mutate application state.

## 4. JDK Dynamic Proxy vs. Class-Based Proxy

### 4.1. JDK Dynamic Proxy

If the target implements an interface and Spring chooses a JDK proxy, the proxy normally exposes methods declared on the interfaces it implements:

```java
public interface WorkerService {
    long getQueueDepth();
    void requestPause();
}

@Service
public class WorkerServiceImpl implements WorkerService {
    @Override
    public long getQueueDepth() { return 12; }

    @Override
    @Transactional
    public void requestPause() {
        // Update worker state.
    }
}
```

With a JDK proxy, reflection on the proxy class differs from reflection on the implementation class. An assembler or custom naming strategy inspecting only `proxy.getClass()` may miss target annotations as expected.

### 4.2. Class-Based Proxy (Usually CGLIB)

A class-based proxy subclasses the target class. Certain annotations can be discovered through the class hierarchy or method resolution, yet you should not assume all metadata is always preserved—especially for `final` methods, `final` classes, private methods, or methods the proxy cannot intercept.

```java
@EnableAspectJAutoProxy(proxyTargetClass = true)
@Configuration
class ClassProxyConfiguration {
}
```

This configuration illustrates one way to request class-based proxies in a Spring context; other AOP configurations such as transaction/async advisors can influence the actual proxy decision. Always verify `AopUtils.isJdkDynamicProxy`, `AopUtils.isCglibProxy`, and the bean's target class in tests.

### 4.3. Assumptions to Avoid

- A JDK proxy does not automatically mean metadata will be lost.
- A CGLIB proxy does not automatically mean every method is advised.
- `@ManagedResource` on a class does not prove the exporter actually used annotation metadata.
- A method with `@ManagedOperation` is not guaranteed to appear in `MBeanInfo` if the bean was skipped or the assembler did not read annotations.
- Metadata appearing in `MBeanInfo` does not guarantee that the corresponding Spring advice actually runs.

## 5. Design Pattern: Dedicated JMX Adapter

A maintainable approach is separating the JMX surface from heavily advised business beans:

```text
MBeanServer
    |
    v
@ManagedResource WorkerAdminAdapter
    |
    +-- @ManagedAttribute getQueueDepth()
    +-- @ManagedOperation requestPause()
    |
    v
WorkerService Spring proxy
    |
    +-- @Transactional
    +-- @Async
    +-- custom aspects
    |
    v
Target service
```

This keeps JMX metadata on a stable management class while behavior still flows through the Spring-managed service proxy. The adapter itself does not need transaction or async logic.

### 5.1. Service Contract

```java
package example.jmx;

public interface WorkerService {
    long queueDepth();
    void requestPause();
}
```

### 5.2. Service Implementation with AOP

```java
package example.jmx;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class WorkerServiceImpl implements WorkerService {
    @Override
    public long queueDepth() {
        return 12L;
    }

    @Override
    @Transactional
    public void requestPause() {
        // Perform actual state change at the service layer.
    }
}
```

For `@Transactional` to actually take effect, transaction management and an appropriate transaction manager must be configured. Adding the annotation alone is not enough.

### 5.3. Management Adapter

```java
package example.jmx;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example:type=Worker,name=Importer",
    description = "Import worker management"
)
public class WorkerAdminAdapter {
    private final WorkerService workerService;

    public WorkerAdminAdapter(WorkerService workerService) {
        this.workerService = workerService;
    }

    @ManagedAttribute(description = "Current queue depth")
    public long getQueueDepth() {
        return workerService.queueDepth();
    }

    @ManagedOperation(
        description = "Request a graceful pause of the worker"
    )
    public void requestPause() {
        workerService.requestPause();
    }

    public void deleteInternalState() {
        // No management annotation.
    }
}
```

This adapter exposes exactly the required management API. `deleteInternalState` should not be exported under a proper metadata-based assembler, and tests should verify that.

## 6. Configuring the Spring JMX Metadata Exporter

An explicit configuration eliminates ambiguity about which assembler is active:

```java
package example.jmx;

import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.annotation.AnnotationJmxAttributeSource;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;
import org.springframework.jmx.export.naming.MetadataNamingStrategy;

@Configuration
public class JmxExportConfiguration {
    @Bean
    public MBeanExporter jmxExporter(WorkerAdminAdapter admin) {
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
        exporter.setBeans(Map.of("workerAdminAdapter", admin));
        return exporter;
    }
}
```

If Spring Boot auto-configures an exporter, avoid creating a second exporter colliding on the same `ObjectName`. In tests, establish **one MBean registration owner** or ensure exporters have non-overlapping scopes.

In an existing application configuration, `@EnableMBeanExport` may be used instead of an explicit exporter bean. What must be verified is not how many annotations sit in source code, but the runtime `MBeanInfo` of the exported MBean.

## 7. Checking Whether a Bean Is AOP-Proxied

Spring provides utilities in `org.springframework.aop.support.AopUtils`:

```java
import org.springframework.aop.support.AopUtils;

Object bean = context.getBean(WorkerService.class);

System.out.println("Proxy? " + AopUtils.isAopProxy(bean));
System.out.println("JDK? " + AopUtils.isJdkDynamicProxy(bean));
System.out.println("CGLIB? " + AopUtils.isCglibProxy(bean));
System.out.println(
    "Target class: " + AopUtils.getTargetClass(bean)
);
```

This helps when tests verify JDK proxy versus CGLIB proxy behavior. If no advice applies, Spring may not create an AOP proxy at all. Tests comparing both proxy types must actively configure applicable advice and assert the actual proxy kind created.

### 7.1. Do Not Rely on Proxy Class Names

JDK proxies carry generated class names; CGLIB proxies also have generated names. Never treat runtime proxy class names as a stable management contract, and never hardcode proxy names into an ObjectName or test.

Prefer resolving target classes via Spring utilities and using explicit naming strategies/metadata.

## 8. Verifying the Registered ObjectName

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "com.example:type=Worker,name=Importer"
);

if (!server.isRegistered(name)) {
    throw new AssertionError("Expected MBean is missing");
}
```

This snippet assumes the exporter uses the platform MBeanServer. If it uses a custom server, inject/retrieve that exact server. `isRegistered=true` still does not prove which bean holds the ObjectName: under `RegistrationPolicy.IGNORE_EXISTING`, a pre-existing object may occupy it.

To verify completely, read `MBeanInfo` right afterward.

## 9. Printing Runtime Metadata and Comparing Against Contract

```java
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanAttributeInfo;

MBeanInfo info = server.getMBeanInfo(name);

System.out.println("Class: " + info.getClassName());
System.out.println("Description: " + info.getDescription());

for (MBeanAttributeInfo a : info.getAttributes()) {
    System.out.printf(
        "attribute=%s type=%s readable=%s writable=%s desc=%s%n",
        a.getName(), a.getType(),
        a.isReadable(), a.isWritable(), a.getDescription()
    );
}

for (MBeanOperationInfo op : info.getOperations()) {
    System.out.printf(
        "operation=%s return=%s signature=%d desc=%s%n",
        op.getName(),
        op.getReturnType(),
        op.getSignature().length,
        op.getDescription()
    );
}
```

Expectation for the sample adapter:

```text
Attribute: QueueDepth
  type = long
  readable = true
  writable = false
  description = Current queue depth

Operation: requestPause
  signature = []
  returnType = void
  description = Request a graceful pause of the worker

Absent operation: deleteInternalState
```

Do not rely on array ordering of `getAttributes()` or `getOperations()` in assertions; compare by name, signature, and properties.

## 10. Metadata Helper Unit Test

An assertion helper using Java streams:

```java
import java.util.Arrays;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanOperationInfo;

MBeanAttributeInfo depth =
    Arrays.stream(info.getAttributes())
        .filter(a -> "QueueDepth".equals(a.getName()))
        .findFirst()
        .orElseThrow(() ->
            new AssertionError("QueueDepth missing"));

if (!"long".equals(depth.getType())
        || !depth.isReadable()
        || depth.isWritable()) {
    throw new AssertionError("QueueDepth contract changed");
}

MBeanOperationInfo pause =
    Arrays.stream(info.getOperations())
        .filter(op -> "requestPause".equals(op.getName())
            && op.getSignature().length == 0)
        .findFirst()
        .orElseThrow(() ->
            new AssertionError("requestPause() missing"));

if (!"void".equals(pause.getReturnType())) {
    throw new AssertionError("Wrong return type");
}
```

This is a **runtime contract check**; it does not check that the business operation executed. Add checks for description/parameter metadata if those must remain stable.

## 11. Negative Test: Preventing Internal API Exposure

An important security requirement is that non-management methods must stay out of `MBeanInfo`:

```java
boolean leaked = Arrays.stream(info.getOperations())
    .anyMatch(op ->
        "deleteInternalState".equals(op.getName()));

if (leaked) {
    throw new AssertionError(
        "Internal method exposed through JMX"
    );
}
```

If using a custom `DynamicMBean`, also test that `invoke(...)` actually rejects unauthorized method names, since hiding an operation from metadata does not guarantee the dynamic implementation refuses it.

Never export an entire service bean containing sensitive methods just to save a few lines of config. A management adapter with explicit allowlist annotations is much easier to audit and control.

## 12. Testing with Both JDK Proxies and CGLIB Proxies

Organize a test matrix:

| Scenario | Proxy Kind | Metadata to Verify |
| --- | --- | --- |
| Baseline | No proxy | Attributes/operations match |
| Transaction advice | JDK proxy | No metadata lost |
| Transaction advice | Class-based proxy | No metadata lost |
| Custom logging aspect | JDK proxy | Stable ObjectName and descriptions |
| Custom logging aspect | Class-based proxy | Stable signatures and flags |
| Async service | Configured proxy | Adapter metadata stable, async runs through proxy |

In each test:

1. Start an isolated `ApplicationContext`.
2. Confirm the actual proxy kind (do not merely trust config flags).
3. Verify the MBean appears at the expected ObjectName.
4. Read `MBeanInfo` and compare against the expected contract.
5. Verify no internal methods leaked.
6. If testing advice behavior, invoke a safe probe operation.
7. Close the `ApplicationContext` and verify cleanup.

**Note:** if the adapter itself has no AOP while the backing service is proxied, that test proves adapter metadata stays stable when the service is proxied. To test an **annotated management bean** directly wrapped in AOP, add a variant with annotations on an AOP-proxied bean and verify the exporter handles target/proxy correctly for your Spring version.

## 13. Testing an Annotated Bean Directly Wrapped in AOP

Suppose JMX annotations are placed directly on the service:

```java
@Service
@ManagedResource(
    objectName = "com.example:type=Worker,name=Direct"
)
public class DirectWorkerManagement {

    @ManagedAttribute(description = "Current queue depth")
    public long getQueueDepth() {
        return 12;
    }

    @Transactional
    @ManagedOperation(description = "Request graceful pause")
    public void requestPause() {
        // Deliberately safe action in test.
    }
}
```

When an AOP proxy is created, the exporter may receive an object distinct from the target class. Tests must prove:

- The MBean registers under `com.example:type=Worker,name=Direct`.
- Attribute `QueueDepth` still appears with accurate metadata.
- Operation `requestPause` retains its description and signature.
- No internal methods are exported.
- When `requestPause` is invoked via JMX, Spring advice actually runs if required by the application.

Never "fix" a failing test by calling the method directly on the target class instead of `MBeanServer`: doing so stops testing the real JMX export path.

## 14. Verifying Advice Actually Runs After JMX Invocation

Accurate `MBeanInfo` proves **metadata**, not that AOP advice runs. To verify transaction or async behavior, observe the execution path.

### 14.1. Transaction Test

In the service method:

```java
@Transactional
public boolean isTransactionActiveOnInvocation() {
    return org.springframework.transaction.support
        .TransactionSynchronizationManager
        .isActualTransactionActive();
}
```

Test invocation through `MBeanServer`:

```java
Object answer = server.invoke(
    name,
    "isTransactionActiveOnInvocation",
    new Object[0],
    new String[0]
);

if (!Boolean.TRUE.equals(answer)) {
    throw new AssertionError("Transaction advice not applied");
}
```

Conditions: the method must be exposed as a test management operation and backed by a matching transaction manager. The test method itself **should not carry `@Transactional`** if that would cause the test framework's ambient transaction to mask a missing service advice.

### 14.2. Async Test

An `@Async` service can return a `CompletableFuture<String>` with the executing thread's name:

```java
@Async("managementExecutor")
public CompletableFuture<String> workerThreadName() {
    return CompletableFuture.completedFuture(
        Thread.currentThread().getName()
    );
}
```

A JMX adapter uses a separate operation to trigger/read state, or in a lab fixture can await the Future with a short timeout and return the thread name string. Assert that the thread name belongs to the configured executor; do not merely assert the annotation is present.

Do not return `CompletableFuture` as an arbitrary JMX object to general clients, or let production operations block for minutes on `future.get()`.

## 15. Self-Invocation and Why Tests Can Mislead

Spring AOP proxy mode normally does not intercept calls from one method on an object to another method via `this`:

```java
@Service
public class ExampleService {
    public void outer() {
        inner(); // Self-invocation: bypasses Spring proxy.
    }

    @Transactional
    public void inner() {
        // Expected transactional work.
    }
}
```

Here, the MBean can expose `outer` with proper metadata while the transaction on `inner` still fails to activate. That is an **advice call-path** bug, not lost metadata.

A maintainable fix is moving the transactional/async method into another bean and injecting that bean's proxy into the adapter or orchestrator.

## 16. Verifying Parameter Metadata on Operations with Signatures

An operation with parameters should have its parameter names, types, and descriptions verified:

```java
@ManagedOperation(
    description = "Retry up to maxTasks failed items"
)
@ManagedOperationParameters({
    @ManagedOperationParameter(
        name = "maxTasks",
        description = "Maximum retry items (1..100)"
    )
})
public int retryFailedTasks(int maxTasks) {
    return maxTasks;
}
```

Test:

```java
var operation = Arrays.stream(info.getOperations())
    .filter(op -> "retryFailedTasks".equals(op.getName()))
    .findFirst()
    .orElseThrow();

var signature = operation.getSignature();
if (signature.length != 1
        || !"int".equals(signature[0].getType())
        || !"maxTasks".equals(signature[0].getName())) {
    throw new AssertionError("Parameter metadata changed");
}
```

With JDK proxies, Java bytecode parameter names are not guaranteed to be what JMX exposes. Explicit annotation metadata and a suitable assembler keep the contract clear.

## 17. Descriptor Metadata and ModelMBean Differences

Spring `MetadataMBeanInfoAssembler` typically works with ModelMBean metadata. Descriptors can carry extra fields such as `currencyTimeLimit`, `role`, `descriptorType`, or specific metadata.

Inspecting runtime descriptors:

```java
System.out.println(info.getDescriptor());
for (var operation : info.getOperations()) {
    System.out.println(
        operation.getName() + " -> " + operation.getDescriptor()
    );
}
```

Tests should assert only fields that truly belong to the application contract. Do not assume all MBeans have identical descriptors: Standard MBeans, MXBeans, and ModelMBeans differ in metadata.

In particular, `currencyTimeLimit` relates to ModelMBean caching, not JMX operation timeouts or management thread limits.

## 18. Common Errors When Adding AOP

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| MBean disappears after enabling AOP | Autodetection/metadata source misses target class or exporter skips proxy bean | Check bean type, assembler, and target class |
| Operation disappears | JDK proxy does not expose method, assembler handles proxy unexpectedly | Check interface and `MBeanInfo` |
| Empty descriptions | Annotation source not applied or implementation metadata not found | Check `AnnotationJmxAttributeSource` and assembler |
| ObjectName changes | Naming strategy relies on runtime proxy class name | Use explicit ObjectName or stable naming |
| `NotCompliantMBeanException` | Proxy object violates Standard MBean conventions; wrong adapter/assembler | Export management adapter or suitable wrapper |
| `InstanceAlreadyExistsException` | Two exporters or two test contexts share an ObjectName | Define ownership and cleanup |
| JMX operation runs with inactive transaction | Self-invocation, target bypasses proxy, or missing transaction manager | Test runtime advice; split services |
| `@Async` runs on caller thread | Self-invocation or misconfigured executor/proxy | Assert worker thread, check `@EnableAsync` |
| Attribute unexpectedly writable | Setter exposed by assembler/interface | Check `MBeanAttributeInfo.isWritable()` |
| MBean missing on platform server | Exporter uses a custom MBeanServer | Query the exporter's server |
| Passes alone, fails in parallel | Colliding ObjectName on shared platform registry | Isolate context/ObjectName |

## 19. Lifecycle Integration Test

In Spring Test, a test should cover the full lifecycle:

1. Initialize context with exporter and AOP configuration.
2. Assert the bean exists in the context with the expected proxy kind.
3. Assert `MBeanServer.isRegistered(name)`.
4. Assert complete metadata as shown above.
5. If safe, invoke a probe operation and verify advice execution.
6. Close the context.
7. Assert the exporter-owned MBean is unregistered.

Never unregister another application's MBeans just to clean up a test. When using the JVM-wide platform MBeanServer, keep ObjectNames independent across test suites to prevent races.

Example verifying registration and cleanup:

```java
ObjectName name = new ObjectName(
    "com.example.tests:type=Worker,name=ProxyMetadata"
);

try (AnnotationConfigApplicationContext context =
         new AnnotationConfigApplicationContext()) {
    context.register(TestJmxConfiguration.class);
    context.refresh();

    if (!server.isRegistered(name)) {
        throw new AssertionError("MBean not registered");
    }
    MBeanInfo info = server.getMBeanInfo(name);
    assertExpectedContract(info);
}

if (server.isRegistered(name)) {
    throw new AssertionError("MBean not cleaned after close");
}
```

`TestJmxConfiguration` and `assertExpectedContract` are test-defined helpers, not built-in API classes. The test must use the exact ObjectName declared by its configuration.

## 20. Do Not Compare Metadata by Raw Ordering

`MBeanInfo.getAttributes()` and `getOperations()` return arrays whose order can vary by implementation, assembler, or reflection. Snapshot tests comparing raw ordered string dumps can report false failures even when functionality is unchanged.

Prefer building normalized key sets:

```text
Attribute key:
  name + type + readable + writable

Operation key:
  name + ordered parameter types + return type
```

Descriptions and descriptors should be asserted separately if they are part of a stable contract that must be preserved.

### 20.1. Why Not Assert Every Field?

Some descriptive fields, internal class names, or descriptor defaults can vary across Spring/JDK versions. Pin down only what clients rely on and what impacts security. Do not skip checking for excess exposure: an unapproved operation outside the allowlist is a critical change even when all expected operations remain intact.

## 21. Comparing Baseline and AOP Variants

One testing strategy builds two **separate** contexts:

```text
Context A:
  bean without AOP
  -> MBeanInfo baseline

Context B:
  bean with AOP
  -> MBeanInfo proxied

Normalize contract:
  attribute keys
  operation keys
  important descriptions
  forbidden operation check

Compare:
  baseline == proxied
```

If sharing the platform MBeanServer, close A before opening B or use distinct ObjectNames to avoid registration conflicts. If both contexts run concurrently, do not rely on `RegistrationPolicy.REPLACE_EXISTING` just to make tests pass.

**Do not assume the baseline is automatically secure.** Maintain an independent expected allowlist: if the baseline already leaked a sensitive method, equality comparison merely preserves that flaw.

## 22. Security When Proxies Alter the Export Surface

Losing metadata can break monitoring. Yet **unintended metadata expansion** is even more dangerous:

- Adding a public method to a service could get exposed by a reflective assembler.
- An internal getter could leak a configuration secret.
- A debug operation could allow clearing caches or mutating state.
- A JMX proxy could retain a handle to an old ObjectName if the registry changed.
- Read-write connector permissions could allow operating across many MBeans, not just the new bean.

Therefore, tests need both **positive assertions** (expected methods exist) and **negative assertions** (forbidden methods are absent).

Spring Security on HTTP does not automatically protect JMX/RMI connectors. Remote JMX requires authentication, TLS, network restrictions, and connector/server authorization. `@ManagedOperation` is not an authorization rule.

## 23. Organizing Tests in CI

A minimal test suite:

| Test | Goal |
| --- | --- |
| Bean proxy classification | Prove JDK/CGLIB proxy is actually created |
| Export registration | MBean has expected ObjectName |
| Attribute contract | Name, type, readable/writable |
| Operation contract | Name, parameter types, return types |
| Description contract | Descriptions preserved across proxying |
| Negative export test | No internal APIs leaked |
| Advice behavior | Transaction/async actually runs through proxy |
| Lifecycle cleanup | No leftover MBeans after context close |
| Cross-version smoke test | Catch changes when upgrading Spring/JDK |

If tests run in parallel, use a dedicated `MBeanServer` per test context or unique `ObjectName`s; avoid letting multiple tests contend for names on the platform server.

Do not test solely with mocks that bypass AOP proxy creation: mocks can skip the exact mechanism you need to verify. Unit tests verify small logic, whereas proving JMX + AOP requires integration tests with a real exporter and runtime `MBeanInfo`.

## 24. Practice Exercises

### Exercise 1 — Baseline Metadata

Create a `@ManagedResource` with one read-only attribute and one operation. Export it, read `MBeanInfo`, and write the expected contract.

**Goal:** learn how to extract the JMX contract from runtime.

### Exercise 2 — JDK Proxy

Add an interface and transaction advice to produce a JDK proxy. Assert the proxy kind using `AopUtils`, read `MBeanInfo`, and compare with baseline.

**Goal:** observe the impact of interface proxying.

### Exercise 3 — CGLIB Proxy

Enable class-based proxies in a separate test context. Compare metadata and behavior with the JDK proxy.

**Goal:** understand target classes, subclass proxies, and method interception.

### Exercise 4 — Annotations on Implementation Only

Place `@ManagedOperation` only on the implementation, then run with a JDK proxy. Observe whether the operation appears under your assembler/attribute source; try switching to a management adapter.

**Goal:** detect configurations sensitive to annotation placement.

### Exercise 5 — Negative Export

Add an unannotated public method `deleteInternalState()`. Assert it does not appear in operations after adding AOP.

**Goal:** prevent internal API leaks.

### Exercise 6 — Transaction Behavior

Add a probe operation returning `TransactionSynchronizationManager.isActualTransactionActive()` in a service with a transaction manager. Invoke via JMX and assert true.

**Goal:** distinguish preserved metadata from advice actually running.

### Exercise 7 — Async Behavior

Delegate work to an `@Async` service using a named executor. Invoke the service from the JMX adapter and verify the worker thread name in the test.

**Goal:** prevent false positives caused by self-invocation or synchronous executors.

### Exercise 8 — Cleanup

Start and close the context multiple times with an isolated ObjectName, confirming no registry leaks.

**Goal:** ensure stability when CI runs repeatedly or in parallel.

## 25. Review Questions

**1. Why test MBeanInfo when AOP is enabled?** Because proxies can change the object/type introspected by the exporter/assembler, affecting published metadata.

**2. How does a JDK proxy differ from a CGLIB proxy?** A JDK proxy typically exposes interface methods; CGLIB generates a subclass of the target class subject to class-based proxy constraints.

**3. Is having `@ManagedOperation` in source code enough?** No. A compatible exporter/assembler and runtime `MBeanInfo` verification are required.

**4. Does accurate metadata prove advice runs?** No. Execution behavior must be tested through the JMX path.

**5. Why does self-invocation usually bypass transaction advice?** Because `this.method()` calls do not pass through the Spring proxy.

**6. How do you prove an operation is not exposed?** Write negative assertions on the operations list and, for `DynamicMBean`, test `invoke` rejection behavior.

**7. Should tests assert exact operation ordering?** Generally no; key assertions by name and signature.

**8. When an MBean does not appear, should you blame AOP alone?** No. Check the exporter, ObjectName, naming strategy, MBeanServer, and registration policy.

**9. Why avoid `REPLACE_EXISTING` as a catch-all fix for test conflicts?** It can overwrite another context's MBean and mask ownership bugs.

**10. What design keeps metadata stable?** A small JMX management adapter calling business services through Spring proxies.

## 26. Summary

**Testing that proxies or AOP do not lose metadata** means verifying the JMX contract after Spring has created proxies and the exporter has registered the MBean. Never look only at annotations or raw classes: read `MBeanServer.getMBeanInfo(...)` on the exact MBeanServer to confirm attributes, operations, signatures, descriptions, and read/write flags remain intact.

When adding `@Transactional`, `@Async`, or aspects, test both **runtime metadata** and the **advice execution path**. Combine positive and negative contract tests, separate management adapters from business services when appropriate, and manage lifecycles/ObjectNames to avoid registration errors in CI.

## References

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework Reference — Proxying Mechanisms: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Framework Reference — Declarative Transaction Management: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework Javadoc — `AopUtils`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/aop/support/AopUtils.html
- Spring Framework Javadoc — `MBeanExporter`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporter.html
- Spring Framework Javadoc — `MetadataMBeanInfoAssembler`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/assembler/MetadataMBeanInfoAssembler.html
- Java SE 21 — `MBeanInfo`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanInfo.html
- Java SE 21 — `MBeanServer`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html