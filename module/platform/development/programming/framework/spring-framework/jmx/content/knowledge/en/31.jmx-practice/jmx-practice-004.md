# Practice: Exposing Parameterized Operations with @ManagedOperation in Spring JMX

## 1. Lesson Objectives

Spring Framework supports exposing Java management methods to JMX via `@ManagedOperation`. When an operation accepts parameters, in addition to annotating the method, you need to understand how JMX describes parameter types in `MBeanInfo`, how clients invoke the operation via `MBeanServer.invoke`, and how to configure user-friendly metadata with `@ManagedOperationParameters`.

This lesson belongs to **Spring Framework JMX → Practice**. After completing it, you will be able to:

- Create a Spring bean containing a parameterized operation and annotate it with `@ManagedOperation`.
- Enable export using `@EnableMBeanExport` or an appropriate annotation-driven configuration.
- Use `@ManagedOperationParameter`/`@ManagedOperationParameters` to describe parameter names and meanings.
- Register the MBean under a clear `ObjectName`.
- Invoke the operation from JConsole/JMC or programmatically via `MBeanServer.invoke(name, operation, params, signature)`.
- Distinguish the primitive `int` signature from the boxed `java.lang.Integer` type.
- Write an integration test against a real `MBeanServer`, verifying results, validation, and cleanup.
- Design parameterized management operations safely, limiting impact and avoiding blocking the client.

## 2. What Is a Parameterized Operation in JMX?

An MBean typically has three functional groups:

| Component | Example | Client Usage |
| --- | --- | --- |
| Attribute | `PendingCount`, `Paused` | `getAttribute`/`setAttribute` |
| Operation | `retryFailed(int maxCount)` | `invoke` |
| Notification | `queue.overloaded` | `NotificationListener` |

Parameterized operations are appropriate when an operator needs to pass an explicit control value, such as:

- Retrying up to `maxCount` failed jobs.
- Refreshing a cache by `cacheName`.
- Adjusting a processing limit via `setLimit(int limit)`.
- Pausing a worker group by `poolName`.

In JMX, the client does not call the Java method on the target directly; instead it sends:

```text
ObjectName:
  com.example.orders:type=QueueAdmin,name=Payment

Operation name:
  retryFailed

Parameters:
  [25]

Signature:
  ["int"]
```

**The signature is an array of positional Java type names**, not a list of parameter variable names. For the method `retryFailed(int maxCount)`, the signature must correspond to `"int"`.

## 3. Prepare the Sample Application

Suppose the application has a service that processes failed jobs. Define the business contract:

```java
package com.example.orders.application;

public interface RetryService {
    int retryFailed(int maxCount);
}
```

Simulated implementation:

```java
package com.example.orders.application;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.stereotype.Service;

@Service
public class InMemoryRetryService implements RetryService {

    private final AtomicInteger failedJobs =
        new AtomicInteger(60);

    @Override
    public int retryFailed(int maxCount) {
        if (maxCount <= 0) {
            throw new IllegalArgumentException(
                "maxCount must be positive"
            );
        }

        while (true) {
            int current = failedJobs.get();
            int retryCount = Math.min(current, maxCount);

            if (failedJobs.compareAndSet(
                    current, current - retryCount)) {
                return retryCount;
            }
        }
    }

    public int getFailedJobs() {
        return failedJobs.get();
    }
}
```

This is a demo that performs no real work: the service only decrements a counter. In a production application, actual retries require a queue system, job state tracking, concurrency limits, and duplicate-effect controls.

**Principle:** business logic does not need to import JMX annotations. A management adapter calls the service.

## 4. Create a Management Adapter with @ManagedOperation

Example management resource:

```java
package com.example.orders.management;

import com.example.orders.application.RetryService;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedOperationParameter;
import org.springframework.jmx.export.annotation.ManagedOperationParameters;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName =
        "com.example.orders:type=QueueAdmin,name=Payment",
    description = "Operations for payment queue management"
)
public class PaymentQueueAdmin {

    private final RetryService retryService;

    public PaymentQueueAdmin(RetryService retryService) {
        this.retryService = retryService;
    }

    @ManagedOperation(
        description = "Retries up to maxCount failed jobs"
    )
    @ManagedOperationParameters({
        @ManagedOperationParameter(
            name = "maxCount",
            description =
                "Maximum number of failed jobs to retry (1..100)"
        )
    })
    public int retryFailed(int maxCount) {
        if (maxCount < 1 || maxCount > 100) {
            throw new IllegalArgumentException(
                "maxCount must be between 1 and 100"
            );
        }

        return retryService.retryFailed(maxCount);
    }
}
```

Key points:

1. `@ManagedResource` helps Spring recognize the bean as a managed resource and provides the ObjectName.
2. `@ManagedOperation` marks the `retryFailed` method as exposed to JMX.
3. `@ManagedOperationParameters` describes the parameters for management tools, helping users understand their meaning and constraints.
4. The `retryFailed` method returns an `int`, representing the number of jobs accepted for processing.
5. Validation happens before calling the service to prevent values with excessive impact.

`@ManagedOperationParameter(name = "maxCount")` **does not change the JMX type name** and is not an automatic validation mechanism. Value bounds still require explicit validation code.

## 5. Enable Annotation-Driven MBean Export

In Spring Java configuration:

```java
package com.example.orders.config;

import com.example.orders.application.RetryService;
import com.example.orders.management.PaymentQueueAdmin;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxConfiguration {

    @Bean
    public PaymentQueueAdmin paymentQueueAdmin(
            RetryService retryService) {
        return new PaymentQueueAdmin(retryService);
    }
}
```

And enable component scanning for the service:

```java
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;

@Configuration
@ComponentScan("com.example.orders.application")
public class ServiceConfiguration {
}
```

The application can create the context:

```java
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

try (var context = new AnnotationConfigApplicationContext(
        ServiceConfiguration.class,
        JmxConfiguration.class)) {

    // Spring registers annotated MBeans when the context initializes.
}
```

Ensure `spring-context`, `spring-aop`, and the Spring modules required by your chosen export mechanism are present for your project version. Do not use two different exporters to register the same ObjectName unintentionally.

If the application uses Spring Boot, enabling/disabling JMX may also be controlled by auto-configuration and version-specific properties. In this hands-on example, direct Java configuration makes the required infrastructure clear.

## 6. ObjectName Must Be Accurate and Stable

The operation is exposed under the ObjectName:

```text
com.example.orders:type=QueueAdmin,name=Payment
```

Do not confuse this with the Spring bean name:

```text
paymentQueueAdmin
```

The two strings serve two different purposes:

- The Spring bean name is for wiring inside the `ApplicationContext`.
- The `ObjectName` is for JMX clients to locate the MBean inside the `MBeanServer`.

The key properties can be reordered:

```text
com.example.orders:name=Payment,type=QueueAdmin
```

and it is still the same ObjectName, because JMX canonicalizes identity by key properties. Use `ObjectName.equals()` rather than comparing raw strings when needed.

## 7. Invoke a Parameterized Operation via MBeanServer.invoke

Once the resource is registered, a local client can invoke it:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "com.example.orders:type=QueueAdmin,name=Payment"
);

Object result = server.invoke(
    name,
    "retryFailed",
    new Object[] { 25 },
    new String[] { "int" }
);

System.out.println("Retried: " + result);
```

Syntax:

```java
Object invoke(
    ObjectName name,
    String operationName,
    Object[] params,
    String[] signature
);
```

Mapping:

| Parameter | Value | Meaning |
| --- | --- | --- |
| `name` | Queue management ObjectName | Which MBean receives the call |
| `operationName` | `"retryFailed"` | Exposed JMX method |
| `params` | `new Object[] { 25 }` | Argument values |
| `signature` | `new String[] { "int" }` | Java parameter types in order |

Note: `new Object[] { 25 }` uses autoboxing to `Integer`, but the method is declared with `int`, so **the signature is still `"int"`**, not `"java.lang.Integer"`.

The returned `Object` can be cast:

```java
int retried = (Integer) result;
```

If the method declares `long`, the returned wrapper type is typically `Long`; clients should verify the contract rather than casting arbitrarily.

## 8. Distinguish @ManagedOperation from @ManagedAttribute

JavaBeans accessors such as:

```java
public int getPendingCount();
public void setPaused(boolean paused);
```

can be exposed as JMX attributes if annotated with `@ManagedAttribute` and configured with an appropriate annotation exporter.

Conversely, the method:

```java
public int retryFailed(int maxCount);
```

is a parameterized action with business semantics, making it a fit for `@ManagedOperation`.

You can write an adapter:

```java
@ManagedAttribute(
    description = "Number of failed jobs currently waiting"
)
public int getFailedCount() {
    return retryService.failedCount();
}
```

The example `RetryService` would need a `failedCount()` method if you use this extension; the initial demo only includes `retryFailed(int)`.

**Do not put `@ManagedAttribute` on every parameterized method** just because you want them to appear in JConsole. Attribute getters/setters and action operations are two different JMX contracts.

## 9. Multiple Parameters with @ManagedOperationParameters

Suppose you want to choose a queue and a retry limit:

```java
@ManagedOperation(
    description = "Retries failed jobs from a named queue"
)
@ManagedOperationParameters({
    @ManagedOperationParameter(
        name = "queueName",
        description = "Logical queue name"
    ),
    @ManagedOperationParameter(
        name = "maxCount",
        description = "Maximum number of jobs to retry"
    )
})
public int retryFailedInQueue(
        String queueName, int maxCount) {

    if (queueName == null || queueName.isBlank()) {
        throw new IllegalArgumentException(
            "queueName is required"
        );
    }

    if (maxCount < 1 || maxCount > 100) {
        throw new IllegalArgumentException(
            "maxCount must be between 1 and 100"
        );
    }

    return retryService.retryFailedInQueue(
        queueName, maxCount
    );
}
```

This is an intentional extension: `RetryService` must implement `retryFailedInQueue(String, int)` accordingly.

Invoking via JMX:

```java
Object result = server.invoke(
    objectName,
    "retryFailedInQueue",
    new Object[] { "payment-dead-letter", 20 },
    new String[] { "java.lang.String", "int" }
);
```

The parameter order **must match the method declaration order**. The signature entry for `String` is the fully qualified `java.lang.String`, whereas `int` is the primitive type name.

If you swap the two signature elements or pass `"java.lang.Integer"` instead of `"int"`, JMX may fail to find the matching overload.

## 10. Does Parameter Metadata Appear in MBeanInfo?

JMX exposes operation metadata via `MBeanOperationInfo`, which contains the parameter signatures.

```java
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanParameterInfo;

MBeanInfo info = server.getMBeanInfo(name);

for (MBeanOperationInfo op : info.getOperations()) {
    if ("retryFailed".equals(op.getName())) {
        System.out.println("Return: " + op.getReturnType());

        for (MBeanParameterInfo param : op.getSignature()) {
            System.out.println(
                param.getName() + " : " + param.getType()
                + " — " + param.getDescription()
            );
        }
    }
}
```

If Spring's annotation metadata source and assembler are active, `@ManagedOperationParameter` provides parameter names and descriptions to `MBeanInfo`. Inspect metadata at runtime to verify that your configuration actually exports the expected details.

Do not assume the Java compiler always preserves source parameter names in bytecode or that every JMX client displays descriptions in the same way. Annotation metadata clarifies parameter meaning, though display behavior depends on the tool.

## 11. Interacting in JConsole and JMC

A test workflow:

1. Start the application with JMX enabled in an appropriate test environment.
2. Open JConsole or Java Mission Control and connect to the right JVM.
3. Open the MBeans view and locate the `com.example.orders` domain.
4. Select `type=QueueAdmin,name=Payment`.
5. Open the operations list.
6. Find `retryFailed`; inspect the parameter names/types if supported by the tool.
7. Enter `maxCount` (for example, 5 or 10) and execute the operation.
8. Check the return value or related attributes to verify the effect.

Distinguish between **the MBean being registered** and **the client connecting to the right server**. If the exporter uses a custom MBeanServer while the tool connects to the platform server, you may not see the resource even though export is configured properly.

Do not open a public remote JMX port just to practice. Use local development or a secured endpoint.

## 12. Spring XML When Not Using Java Configuration

In legacy XML projects, annotation-driven JMX export can be enabled via:

```xml
<context:mbean-export/>
```

In a complete XML configuration, ensure the `context` namespace and schema match the Spring version in use.

When the bean is declared:

```xml
<bean id="paymentQueueAdmin"
      class="com.example.orders.management.PaymentQueueAdmin">
    <constructor-arg ref="retryService"/>
</bean>
```

and annotation-driven infrastructure is enabled, Spring can detect `@ManagedResource` on the class and export `@ManagedOperation`.

If you already have a manual `MBeanExporter`, do not unintentionally enable a second export path for the same ObjectName. Conflicts can cause `InstanceAlreadyExistsException` or depend on `RegistrationPolicy`.

## 13. Testing with an Isolated MBeanServer

A good integration test does not depend on the shared platform MBeanServer:

```java
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;

MBeanServer testServer =
    MBeanServerFactory.newMBeanServer("test.management");
```

With annotation export, configure the exporter to **use the test server**. Merely defining an `MBeanServer` bean is not always enough if the annotation exporter prefers another server.

You can write a test configuration using Spring's `AnnotationMBeanExporter` or configure the exporter/metadata assembler suitable for your version. A straightforward approach is creating a Spring context with an explicitly configured `MBeanExporter` and `MetadataMBeanInfoAssembler`, then asserting the test server contains the MBean.

Example with Spring annotation configuration:

```java
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxTestConfiguration {
    @Bean
    public MBeanServer mbeanServer() {
        return MBeanServerFactory.newMBeanServer(
            "test.management"
        );
    }

    @Bean
    public RetryService retryService() {
        return maxCount -> Math.min(maxCount, 3);
    }

    @Bean
    public PaymentQueueAdmin paymentQueueAdmin(
            RetryService retryService) {
        return new PaymentQueueAdmin(retryService);
    }
}
```

Then the test should retrieve the `MBeanServer` from the context and verify the exporter uses this server. If the annotation exporter in your current version/configuration does not pick up the test server, configure the server reference explicitly instead of changing the assertion to query the platform server.

## 14. JUnit Integration Test Invoking the Real Operation

An illustrative test:

```java
import static org.junit.jupiter.api.Assertions.*;

import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

class ManagedOperationParameterTest {

    @Test
    void invokesOperationWithIntArgument() throws Exception {

        try (var context =
                 new AnnotationConfigApplicationContext(
                     JmxTestConfiguration.class)) {

            MBeanServer server =
                context.getBean(MBeanServer.class);

            ObjectName name = new ObjectName(
                "com.example.orders:type=QueueAdmin,name=Payment"
            );

            assertTrue(server.isRegistered(name));

            Object result = server.invoke(
                name,
                "retryFailed",
                new Object[] { 2 },
                new String[] { "int" }
            );

            assertEquals(2, ((Integer) result).intValue());
        }
    }
}
```

This test verifies:

- The annotation exporter registered the MBean into the test server.
- The `retryFailed` operation exists in MBean metadata.
- The `int` signature is correct.
- The argument value is passed to the implementation.
- The return value reflects the business result.

In real projects, if the Spring context has multiple `MBeanServer` beans, inject the right bean via `@Qualifier` or bean name so the test does not pick the wrong registry.

## 15. Testing Validation with Invalid Parameters

Management operations generally must not accept arbitrary values.

For example, `maxCount` must only be between 1 and 100:

```java
public int retryFailed(int maxCount) {
    if (maxCount < 1 || maxCount > 100) {
        throw new IllegalArgumentException(
            "maxCount must be between 1 and 100"
        );
    }
    return retryService.retryFailed(maxCount);
}
```

Testing via `MBeanServer`:

```java
assertThrows(
    Exception.class,
    () -> server.invoke(
        name,
        "retryFailed",
        new Object[] { 1000 },
        new String[] { "int" }
    )
);
```

In JMX/Spring implementations, the underlying exception may be wrapped in `MBeanException`, `ReflectionException`, or Spring's `JmxException`, depending on the export path and failure point.

Therefore, integration tests should inspect the **exception chain** to verify the root cause is validation and ensure the service performed no side effects. Do not simply assert any exception and ignore the cause.

To unit test business validation, you can call `PaymentQueueAdmin.retryFailed(1000)` directly and assert `IllegalArgumentException` without JMX.

## 16. Operation Overloading and Parameter Signatures

Suppose the adapter has two operations:

```java
@ManagedOperation
public void retryFailed(int maxCount) { ... }

@ManagedOperation
public void retryFailed(String queueName) { ... }
```

When invoking, the operation name is identical while the signature differs:

```java
server.invoke(
    name,
    "retryFailed",
    new Object[] { 25 },
    new String[] { "int" }
);

server.invoke(
    name,
    "retryFailed",
    new Object[] { "payment" },
    new String[] { "java.lang.String" }
);
```

Some exporters/metadata assemblers may handle overloaded methods differently depending on configuration. Inspect `MBeanInfo.getOperations()` to see which overloads are actually exposed, rather than assuming every annotated method is callable.

When operations have different meanings, using distinct names like `retryFailedByQueue` is often easier to operate and less prone to signature mistakes.

## 17. Does @ManagedOperationParameter Perform Type Conversion?

No. Annotation metadata only describes parameters. JMX invocation still depends on:

- The actual method signature exposed by the exporter.
- The `params` object values.
- The type name strings in `signature`.
- Conversion/serialization support in the connector and client.

For example:

```java
new Object[] { "25" },
new String[] { "int" }
```

is not equivalent to:

```java
new Object[] { 25 },
new String[] { "int" }
```

A JMX client UI may accept text input and convert strings to Java types, but code calling `MBeanServer.invoke` should not rely on the server automatically parsing `"25"` into an integer.

Keep parameter types simple and enforce explicit input validation.

## 18. Remote JMX and Parameterized Operations

An `MBeanServerConnection` obtained via `JMXConnector` supports the same API:

```java
MBeanServerConnection connection =
    connector.getMBeanServerConnection();

Object result = connection.invoke(
    name,
    "retryFailed",
    new Object[] { 5 },
    new String[] { "int" }
);
```

However, remote JMX introduces additional risks:

- Authentication/authorization.
- TLS and network connectivity.
- Serialization of parameters and return values.
- Timeouts or disconnects after the operation has already run.
- Retrying an operation with side effects can cause double execution.

**Do not blindly retry an operation like `retryFailed` after a network timeout**, because the server may have already executed the command while the client missed the response.

Prefer idempotent operations or a request ID for deduplication; for long-running work, consider an operation that starts a job and returns a `jobId` instead of blocking until completion.

## 19. Security When Exposing Parameterized Operations

A parameterized operation can create a broader control surface than a read-only attribute:

```java
@ManagedOperation
public void deleteJobs(String queueName, int count) { ... }
```

Do not expose high-impact operations just because they are convenient in JConsole.

You should:

1. Expose only operations truly needed for administration.
2. Validate values, string lengths, and queue/tenant scopes.
3. Limit invocation volume and frequency.
4. Enforce permissions at the JMX connector and in the service if needed.
5. Audit operations with side effects.
6. Avoid returning sensitive data in results/exceptions.
7. Design timeouts, job states, and idempotency.
8. Never let an operation bypass business invariants.

`@ManagedOperation(description = "...")` **is not a security annotation**. The description only documents the method; it does not restrict who can call it.

## 20. Spring AOP and Proxy Issues

If a management bean is wrapped by a JDK dynamic proxy, methods not declared on the proxy interface may not be exposed/callable as expected. If a CGLIB/class-based proxy is used, you still must watch out for `final`, `private`, and proxy advice constraints.

A maintainable design:

```text
JMX Client
    |
    v
PaymentQueueAdmin (management adapter)
    |
    v
RetryService Spring bean/proxy
    |
    v
Business implementation
```

The adapter carries the JMX annotations, while the service contains business logic and AOP advice. Calling through the service proxy preserves transaction/security boundaries better than exporting arbitrary target objects.

If `@ManagedOperation` is present but `MBeanInfo` does not show the operation, check the annotation exporter, metadata assembler, and proxy method surface.

## 21. Troubleshooting Common Errors

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| MBean not visible in JConsole | Exporter not enabled, wrong server, wrong ObjectName | `isRegistered`, config, endpoint |
| MBean visible but operation missing | Annotation not read by metadata source | `MBeanInfo.getOperations()` |
| `ReflectionException` on invoke | Operation name or signature mismatch | Inspect `MBeanOperationInfo` |
| Passed `Integer` with `Integer` signature fails | Method uses primitive `int` | Use `"int"` |
| UI parameter input cannot invoke operation | Client converted type differently than expected | Check exposed JMX types |
| Operation returns wrong result | Business service/validation issue | Unit test adapter and service |
| `InstanceAlreadyExistsException` | Two exporters registering same ObjectName | Pick single owner, check policy |
| Remote invoke timeout | Network latency or long-running operation | Design async job, avoid blind retries |
| Client invoke rejected | JMX authorization/connector policy | Check permissions and auth config |
| Operation runs without AOP advice | Wrong target/proxy exported | Use adapter calling service proxy |

## 22. Practice Checklist

- [ ] Create resource with `@ManagedResource` and valid ObjectName.
- [ ] Mark method to expose with `@ManagedOperation`.
- [ ] Document all parameters via `@ManagedOperationParameters`.
- [ ] Ensure annotation-driven exporter is active.
- [ ] Verify `MBeanServer.isRegistered` on the right server.
- [ ] Inspect `MBeanInfo` to verify operation name and signature.
- [ ] Call `invoke` with matching `params` and `signature`.
- [ ] Test parameter bounds and error paths.
- [ ] Do not expose sensitive operations accidentally.
- [ ] Do not mix runtime/remote configuration into business logic.
- [ ] Close context/connector after tests.
- [ ] For remote calls, verify idempotency and retry policy.

## 23. Extension Exercises

1. Change the operation to `reprocess(String queueName, int maxCount, boolean dryRun)`. Write `@ManagedOperationParameters` describing all three parameters.
2. Invoke that operation via `MBeanServer.invoke` with signature `"java.lang.String", "int", "boolean"`.
3. Inspect `MBeanInfo` to verify parameter count, names, descriptions, and types.
4. Create two overloads with different parameter types; invoke each overload with its exact signature.
5. Add validation that `dryRun=false` is only allowed when `maxCount <= 50`; test the error path.
6. Add a `@ManagedAttribute` reading the remaining job count; invoke the operation and compare state before/after.
7. Create an integration test with a dedicated Spring context and MBeanServer to avoid conflicts.
8. Simulate a remote invocation that loses its response; explain why it must not automatically retry if the operation has side effects.

## 24. Self-Check Questions

- What is the role of `@ManagedOperation`?
- What metadata does `@ManagedOperationParameters` provide?
- Should an `int` parameter appear in the signature as `"int"` or `"java.lang.Integer"`?
- Why is the variable name `maxCount` not what resolves an operation overload?
- What is the difference between `getAttribute` and `invoke`?
- How do you verify that an operation was actually exposed by the exporter?
- Why must parameterized operations validate input?
- When a remote invocation times out, can you be sure the server did not run the operation?
- Why should you use a management adapter instead of exposing every method of a business service?

**Key takeaway:** `@ManagedOperation` lets Spring expose a method as a **JMX operation**, including methods with parameters. `@ManagedOperationParameters` adds names/descriptions, but invocation still relies on **operation name, values, and ordered Java type signature**. Always verify runtime metadata with `MBeanInfo`, test `MBeanServer.invoke`, constrain parameters, and protect management actions with side effects.