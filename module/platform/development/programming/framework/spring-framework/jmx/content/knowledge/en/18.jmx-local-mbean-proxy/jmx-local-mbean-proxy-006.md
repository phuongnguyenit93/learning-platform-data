# Invoking Operations and Handling Errors from MBeanServer via a Local MBean Proxy in Spring JMX

## 1. Learning objectives

After this lesson, you will be able to:

- Explain the flow of invoking a **JMX operation** from a client to \`MBeanServer\`, especially when the client and MBean are in the **same JVM**.
- Distinguish **calling \`MBeanServer.invoke(...)\` directly** from **calling through Spring's \`MBeanProxyFactoryBean\`**.
- Understand how \`ObjectName\`, operation name, arguments array, and signature array define a call.
- Identify and handle errors across categories: **MBean not found**, **operation not found**, **signature mismatch**, **business error**, **reflection error**, **security error**, and **lifecycle error**.
- Extract the real cause from \`MBeanException\` or \`ReflectionException\`, without confusing the JMX wrapper with the underlying error.
- Design management interfaces suitable for proxies, and know how to control timeouts, retries, and side effects.
- Verify behavior in Spring integration tests without accidentally impacting production.
- Apply logging, authorization, and operation observability practices for safe operation.

## 2. What is an operation in JMX?

JMX supports two key kinds of management capabilities:

- **Attribute:** read/write a property of an MBean using \`getAttribute\` or \`setAttribute\`.
- **Operation:** invoke a published management method using \`invoke\`.

Example of a worker management MBean:

\`\`\`text
ObjectName:
  com.example.jobs:type=Worker,name=Importer

Attributes:
  Running          boolean (read-only)
  QueueDepth       long    (read-only)

Operations:
  requestPause()                    void
  retryFailedTasks(int maxTasks)    int
\`\`\`

The \`requestPause()\` operation can alter application state; \`retryFailedTasks(int)\` can place load on the system. Invoking an operation is not like reading metadata: it instructs the server to actually execute logic.

With Standard MBeans, operations are published via a management interface following Java conventions. With Spring POJOs exported as Model MBeans, the assembler and annotations like \`@ManagedOperation\` can determine which operations are published. Regardless of the export mechanism, the client needs to look at the actual \`MBeanInfo\` to know the interface recognized by the MBeanServer.

## 3. Local MBean proxy architecture

When using a local proxy in Spring, the caller can work with an ordinary Java interface. The Spring proxy turns method calls into management operations on an \`MBeanServerConnection\` for an \`ObjectName\`.

\`\`\`text
Business/admin component (Spring bean)
              |
       WorkerAdmin interface
              |
              v
      MBeanProxyFactoryBean
              |
        JMX client proxy
              |
              v
   MBeanServerConnection (local)
              |
              v
      MBeanServer.invoke(...)
              |
              v
     Registered MBean
              |
              v
        Management logic
\`\`\`

A local proxy **does not register the MBean itself**. The MBean must exist in the MBeanServer and be registered by an exporter or other JMX code.

**Local** means the client proxy and MBeanServer are connected within the same appropriate JVM environment, requiring no remote JMX connector/RMI. If the client connects to another JVM via \`JMXConnector\`, the proxy can use a remote \`MBeanServerConnection\`, though additional network failure modes apply.

## 4. Example of a locally registered Standard MBean

Before using a proxy, create an MBean with explicit operations.

### 4.1. Management interface

\`\`\`java
package example.jmx;

public interface WorkerAdminMBean {
    boolean isRunning();
    long getQueueDepth();
    void requestPause();
    int retryFailedTasks(int maxTasks);
}
\`\`\`

### 4.2. Implementation

\`\`\`java
package example.jmx;

public final class WorkerAdmin implements WorkerAdminMBean {

    private volatile boolean running = true;

    @Override
    public boolean isRunning() {
        return running;
    }

    @Override
    public long getQueueDepth() {
        return 12L;
    }

    @Override
    public void requestPause() {
        running = false;
    }

    @Override
    public int retryFailedTasks(int maxTasks) {
        if (maxTasks < 1 || maxTasks > 100) {
            throw new IllegalArgumentException(
                "maxTasks must be between 1 and 100"
            );
        }
        return maxTasks; // Illustrative result.
    }

    // Not part of WorkerAdminMBean, not a Standard MBean operation
    // merely because the method is declared public.
    public void deleteAllInternalData() {
        // Not exposed through the management interface.
    }
}
\`\`\`

### 4.3. Registering in the platform MBeanServer

\`\`\`java
package example.jmx;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public final class LocalJmxRegistration {
    public static void main(String[] args) throws Exception {
        MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();

        ObjectName name = new ObjectName(
            "com.example.jobs:type=Worker,name=Importer"
        );

        server.registerMBean(new WorkerAdmin(), name);
        try {
            System.out.println(
                server.getAttribute(name, "Running")
            );

            Object result = server.invoke(
                name,
                "retryFailedTasks",
                new Object[] { 5 },
                new String[] { "int" }
            );

            System.out.println("Accepted: " + result);
        } finally {
            server.unregisterMBean(name);
        }
    }
}
\`\`\`

In this example, \`MBeanServer\` is a local object. The \`invoke\` call still uses JMX dispatch to the operation published by the MBean.

## 5. Syntax of MBeanServer.invoke(...)

Key method:

\`\`\`java
Object invoke(
    ObjectName name,
    String operationName,
    Object[] params,
    String[] signature
)
\`\`\`

Explanation:

| Parameter | Meaning |
| --- | --- |
| \`name\` | \`ObjectName\` identifying the target MBean in the registry. |
| \`operationName\` | Operation name published by the MBean. |
| \`params\` | Actual arguments in exact order. |
| \`signature\` | Java type names of each parameter, in matching order. |
| Return value | \`Object\`, or \`null\` if the operation returns \`void\`. |

No-argument example:

\`\`\`java
server.invoke(
    name,
    "requestPause",
    new Object[0],
    new String[0]
);
\`\`\`

Example with one primitive \`int\` parameter:

\`\`\`java
Object accepted = server.invoke(
    name,
    "retryFailedTasks",
    new Object[] { 10 },
    new String[] { "int" }
);
\`\`\`

**Common pitfall:** \`new String[] { "int" }\` differs from \`new String[] { "java.lang.Integer" }\`. A JMX signature is a list of **published type names**, not a list of compatible classes under Java boxing in all situations.

With overloaded methods, the signature is often the decisive factor distinguishing operations:

\`\`\`java
void refresh(String region);
void refresh(int partitionId);
\`\`\`

If the client only supplies the name \`refresh\` without passing the exact signature, the invocation may fail or match the wrong contract.

## 6. Getting signatures from MBeanInfo instead of guessing

To see which operations are published:

\`\`\`java
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanParameterInfo;

MBeanInfo info = server.getMBeanInfo(name);

for (MBeanOperationInfo op : info.getOperations()) {
    System.out.println(
        op.getName() + " -> " + op.getReturnType()
    );

    for (MBeanParameterInfo param : op.getSignature()) {
        System.out.println(
            "  " + param.getName()
                + ": " + param.getType()
        );
    }
}
\`\`\`

Example metadata:

\`\`\`text
requestPause -> void
retryFailedTasks -> int
  p1: int
\`\`\`

The parameter name \`p1\` is illustrative. If Spring \`@ManagedOperationParameter\` is processed, metadata may include clearer names and descriptions. Most important for \`invoke\` are the **operation name and signature types**.

Do not test-call dangerous operations merely to discover them. \`getMBeanInfo\` is the way to inspect the contract without executing operation side effects.

## 7. Spring MBeanProxyFactoryBean

Spring Framework provides **\`org.springframework.jmx.access.MBeanProxyFactoryBean\`** to create a Java proxy to an MBean. Components using the proxy call methods like an ordinary Java object; Spring translates the calls into the corresponding JMX accesses.

A proxy requires:

1. \`ObjectName\` of the MBean.
2. The management interface the caller will use.
3. An appropriate \`MBeanServerConnection\` or server.
4. The MBean already registered before access is needed.

### 7.1. Client-side interface

A separate interface can be used to describe the contract to invoke:

\`\`\`java
package example.springjmx;

public interface WorkerAdminClient {
    boolean isRunning();
    long getQueueDepth();
    void requestPause();
    int retryFailedTasks(int maxTasks);
}
\`\`\`

The proxy interface does not have to carry the \`MBean\` suffix; what matters is that methods and types are compatible with the operations/attributes published by the target MBean.

### 7.2. Local proxy configuration

\`\`\`java
package example.springjmx;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.access.MBeanProxyFactoryBean;

@Configuration
public class LocalJmxClientConfig {

    @Bean
    public MBeanProxyFactoryBean workerAdminProxyFactory()
            throws Exception {

        MBeanServer localServer =
            ManagementFactory.getPlatformMBeanServer();

        MBeanProxyFactoryBean factory =
            new MBeanProxyFactoryBean();

        factory.setServer(localServer);
        factory.setObjectName(
            "com.example.jobs:type=Worker,name=Importer"
        );
        factory.setProxyInterface(WorkerAdminClient.class);

        return factory;
    }
}
\`\`\`

\`MBeanProxyFactoryBean\` is a Spring \`FactoryBean\`, so the bean injected into consumers is normally the **interface-typed proxy**, not the factory object. To access the factory bean itself by name in Spring, the \`&\` prefix convention can be used, though application consumers usually only need the interface.

Consumer example:

\`\`\`java
package example.springjmx;

import org.springframework.stereotype.Component;

@Component
public class WorkerControlPanel {

    private final WorkerAdminClient worker;

    public WorkerControlPanel(WorkerAdminClient worker) {
        this.worker = worker;
    }

    public void pauseIfRunning() {
        if (worker.isRunning()) {
            worker.requestPause();
        }
    }
}
\`\`\`

**Important precondition:** the MBean must be registered under the exact name in the same server before the proxy needs to call it. If the proxy initializes or is invoked too early, errors can occur when the MBean or metadata is not yet ready.

## 8. Registering an MBean with Spring MBeanExporter

Example configuring a Standard MBean in Spring:

\`\`\`java
package example.springjmx;

import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class LocalJmxExporterConfig {

    @Bean
    public example.jmx.WorkerAdmin workerAdminTarget() {
        return new example.jmx.WorkerAdmin();
    }

    @Bean
    public MBeanExporter workerExporter(
            example.jmx.WorkerAdmin workerAdminTarget) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setBeans(Map.of(
            "com.example.jobs:type=Worker,name=Importer",
            workerAdminTarget
        ));
        return exporter;
    }
}
\`\`\`

In Spring Boot, an auto-configured exporter may already exist. When an application creates its own exporter, avoid two exporters registering the same \`ObjectName\`. The configuration above illustrates local JMX without needing to enable a remote JMX connector.

### 8.1. Managing initialization order

You may need to ensure the exporter finishes registering before the proxy accesses it. If beans are used in startup hooks or \`@PostConstruct\`, consider explicit dependencies/lifecycles.

One option is running client logic after the context finishes starting or using \`dependsOn\` appropriately. However, merely adding a dependency annotation does not automatically guarantee every custom exporter/connector is stably connected; integration tests should verify actual ordering.

## 9. How do MBeanServer.invoke and a Spring proxy differ?

| Criterion | Calling \`MBeanServer.invoke\` directly | Calling via \`MBeanProxyFactoryBean\` |
| --- | --- | --- |
| Client-side API | String operation name, args array, signature array. | Call Java interface method. |
| Catching signature mismatch | When client builds the call manually, usually surfaces at runtime. | Proxy has a typed interface, yet can still differ from actual MBean. |
| Readability | Makes JMX layer and ObjectName explicit. | Natural for Spring consumer code. |
| Coupling | Depends directly on JMX API. | Consumer depends on interface; config wires to JMX. |
| Error handling | Receives JMX checked exceptions directly. | May receive exceptions translated/wrapped by Spring. |
| Contract verification | Read \`MBeanInfo\` manually and compare. | Can configure interface/metadata checks and should still test at runtime. |
| Local/remote | Uses appropriate \`MBeanServerConnection\`. | Proxy factory can use the appropriate connection. |

The proxy **hides the JMX invocation mechanics** from the service consumer, but does not make exceptions, side effects, or permission issues disappear.

## 10. Important exceptions from MBeanServer

### 10.1. InstanceNotFoundException

Occurs when the MBean with the specified \`ObjectName\` does not exist in the MBeanServer being used.

\`\`\`java
try {
    server.invoke(
        name,
        "requestPause",
        new Object[0],
        new String[0]
    );
} catch (javax.management.InstanceNotFoundException ex) {
    // Wrong ObjectName, MBean not registered, or already unregistered.
}
\`\`\`

How to diagnose:

- Check \`server.isRegistered(name)\`.
- Check the domain and key properties of \`ObjectName\`.
- Ensure the exporter and client use the same \`MBeanServer\`.
- Verify the Spring context has started and the MBean has not been cleaned up.
- Check whether \`IGNORE_EXISTING\` registration policy left a different object under that name.

**Race condition note:** \`isRegistered(name)\` can return true yet the MBean gets unregistered before \`invoke\`; \`InstanceNotFoundException\` must still be handled.

### 10.2. ReflectionException

JMX can wrap reflection/dispatch failures in \`ReflectionException\`, such as an invalid operation name or mismatched signature.

\`\`\`java
try {
    server.invoke(
        name,
        "unknownOperation",
        new Object[0],
        new String[0]
    );
} catch (javax.management.ReflectionException ex) {
    System.err.println(
        "JMX reflection/dispatch failure: "
            + ex.getMessage()
    );
}
\`\`\`

A common error is:

\`\`\`text
NoSuchMethodException: unknownOperation
\`\`\`

However, do not treat every \`ReflectionException\` as “operation does not exist”; read the **cause** and \`MBeanInfo\` to understand the actual reflection failure.

### 10.3. MBeanException

\`MBeanException\` typically represents an exception thrown by invoked management code or during management method invocation.

Example of executing a getter/operation:

\`\`\`java
public void requestPause() {
    throw new IllegalStateException(
        "Cannot pause while committing a batch"
    );
}
\`\`\`

When passing through JMX, business errors can be represented as \`MBeanException\` if the exception type/contract corresponds. Retrieve the wrapped exception via \`getTargetException()\` or cause:

\`\`\`java
catch (javax.management.MBeanException ex) {
    Exception target = ex.getTargetException();

    System.err.println(
        "MBean operation failed: "
            + target.getClass().getSimpleName()
    );
}
\`\`\`

**Important:** Java runtime exceptions thrown by an operation can come through \`RuntimeMBeanException\`, not necessarily always inside \`MBeanException\`. Thus a handler catching only \`MBeanException\` is insufficient.

### 10.4. RuntimeMBeanException

\`RuntimeMBeanException\` wraps a \`RuntimeException\` thrown inside the MBean.

\`\`\`java
catch (javax.management.RuntimeMBeanException ex) {
    RuntimeException target = ex.getTargetException();
    // Classify business, state, or validation error.
}
\`\`\`

For example, \`IllegalArgumentException\` when \`maxTasks\` is out of range can travel this path. Applications should define clear error contracts; do not rely on clients parsing arbitrary exception message strings.

### 10.5. RuntimeErrorException

If an MBean throws a JVM \`Error\`, JMX can wrap it in \`RuntimeErrorException\`. This is a critical failure category and should not be automatically retried or ignored like an ordinary validation error.

### 10.6. SecurityException and permission errors

A JMX client may be denied an operation due to permission policies on the MBeanServer, connector, or application security layer.

\`\`\`java
catch (SecurityException ex) {
    // Not permitted to invoke operation in this security context.
}
\`\`\`

Do not work around permission errors by disabling authentication/authorization or switching to a broader administrative account without approval under system policy.

### 10.7. IOException when using remote

With a **local \`MBeanServer\`**, calls typically do not suffer network errors. However, when working with a remote \`MBeanServerConnection\`, the API can throw \`IOException\` due to endpoint/connector/network issues.

A network failure after sending \`invoke\` is a special case: you cannot deduce that the operation **definitely did not run**. If the client automatically retries a non-idempotent command, the action may execute twice.

## 11. Error classification and action table

| Error or symptom | Common cause | Action to take |
| --- | --- | --- |
| \`InstanceNotFoundException\` | MBean does not exist at that ObjectName. | Check registry, exporter, lifecycle, and right server. |
| \`ReflectionException\` | Method not found, wrong signature, or dispatch failure. | Read \`MBeanInfo.getOperations()\`, compare signature. |
| \`MBeanException\` | Checked exception from MBean operation or related wrapper. | Extract target exception, classify by contract. |
| \`RuntimeMBeanException\` | \`RuntimeException\` inside MBean code. | Inspect target, validation/state, do not blindly retry. |
| \`RuntimeErrorException\` | Critical \`Error\` from MBean. | Record incident and handle appropriately, avoid swallowing. |
| \`SecurityException\` | Insufficient permissions to operate. | Check policy/role, do not loosen permissions arbitrarily. |
| \`IOException\` (remote) | Connection/transport error. | Check connector, distinguish safe retries. |
| \`IllegalArgumentException\` | Invalid input; or error in client proxy. | Check range, types, validation, and throw origin. |
| Operation exists but returns wrong type | Proxy interface and metadata do not match. | Compare \`MBeanOperationInfo.getReturnType()\`. |
| Operation hangs | MBean code executes slowly or blocks on lock. | Design async request, timeout at appropriate layer, monitor threads. |

Do not catch \`Exception\` and merely print \`ex.getMessage()\` in every case, because you will lose the exception type and cause chain needed.

## 12. Example of direct invocation with classified error handling

Example utility method using only a local \`MBeanServer\`:

\`\`\`java
import javax.management.InstanceNotFoundException;
import javax.management.MBeanException;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import javax.management.ReflectionException;
import javax.management.RuntimeErrorException;
import javax.management.RuntimeMBeanException;

public final class WorkerJmxInvoker {

    private final MBeanServer server;
    private final ObjectName name;

    public WorkerJmxInvoker(
            MBeanServer server,
            ObjectName name) {
        this.server = server;
        this.name = name;
    }

    public int retryFailedTasks(int limit) throws Exception {
        if (limit < 1 || limit > 100) {
            throw new IllegalArgumentException(
                "limit must be between 1 and 100"
            );
        }

        try {
            Object value = server.invoke(
                name,
                "retryFailedTasks",
                new Object[] { limit },
                new String[] { "int" }
            );

            return ((Number) value).intValue();

        } catch (InstanceNotFoundException ex) {
            throw new IllegalStateException(
                "Worker MBean is not registered: " + name,
                ex
            );

        } catch (ReflectionException ex) {
            throw new IllegalStateException(
                "JMX operation/signature mismatch",
                ex
            );

        } catch (MBeanException ex) {
            Exception cause = ex.getTargetException();
            throw new IllegalStateException(
                "Worker operation failed",
                cause != null ? cause : ex
            );

        } catch (RuntimeMBeanException ex) {
            throw new IllegalStateException(
                "Worker rejected the operation",
                ex.getTargetException()
            );

        } catch (RuntimeErrorException ex) {
            throw ex; // Do not turn a critical Error into an ordinary error.
        }
    }
}
\`\`\`

This illustrates a classification approach, not a universal exception design for every project. In a real application, domain exceptions like \`WorkerUnavailableException\`, \`InvalidJmxContractException\`, and \`WorkerActionRejectedException\` can be created instead of collapsing everything into \`IllegalStateException\`.

Because this local method does not use a remote connection, it does not catch \`IOException\`; if switching to \`MBeanServerConnection\`, checked connection exceptions must also be considered.

## 13. Exception mapping when calling via a Spring proxy

When Spring \`MBeanProxyFactoryBean\` creates a proxy, the JMX invocation and exception handling are performed by Spring's proxy/interceptor layer. Clients typically do not catch all checked exceptions of \`MBeanServer.invoke\` directly if the Java interface does not declare them.

Depending on the error path and Spring version, an error may:

- Be propagated directly if the exception type matches the method signature.
- Be wrapped in a Spring/JMX access runtime exception.
- Travel as \`UndeclaredThrowableException\` if a Java dynamic proxy encounters an undeclared checked exception.
- Have a \`cause\` of \`MBeanException\`, \`ReflectionException\`, or the original exception from the MBean.

Do not write logic depending on a single wrapper class when supporting multiple Spring versions.

### 13.1. Walking the cause chain

\`\`\`java
public static Throwable rootCause(Throwable failure) {
    Throwable current = failure;
    while (current.getCause() != null
            && current.getCause() != current) {
        current = current.getCause();
    }
    return current;
}
\`\`\`

For diagnostic logging:

\`\`\`java
try {
    workerAdminClient.retryFailedTasks(10);
} catch (RuntimeException ex) {
    Throwable root = rootCause(ex);

    log.error(
        "Local JMX operation failed, target={}, errorType={}",
        "com.example.jobs:type=Worker,name=Importer",
        root.getClass().getSimpleName(),
        ex
    );
}
\`\`\`

This assumes the consumer has \`workerAdminClient\` and logger \`log\`. Note: the deepest cause does not always best describe the **context** of the incident; preserve the wrapper, \`ObjectName\`, operation, and signature in protected logs.

### 13.2. Do not automatically retry every exception

An operation may have started or even finished even though the client received an exception due to timeout or wrapping. For \`requestPause()\` or \`retryFailedTasks()\`, repeating can alter state a second time.

Design control operations to have:

- **Idempotency keys** or safety when called repeatedly.
- **Status queries** to confirm the action.
- **Retry limits** and appropriate backoff if retries are permitted.
- **Permission checks** before invocation.
- **Auditing** for high-impact operations.

## 14. Verifying that the proxy interface matches the MBean

A hard-to-diagnose issue occurs when the client Java interface does not match actual \`MBeanInfo\`.

Suppose the client interface has:

\`\`\`java
int retryFailedTasks(Integer maxTasks);
\`\`\`

while the MBean exports:

\`\`\`java
int retryFailedTasks(int maxTasks);
\`\`\`

Even though Java supports boxing in ordinary method calls, the signature name in JMX metadata may be \`java.lang.Integer\` versus \`int\`, respectively. The proxy may call with the wrong signature.

A simple verification:

\`\`\`java
MBeanInfo info = server.getMBeanInfo(name);

boolean found = false;

for (var operation : info.getOperations()) {
    if ("retryFailedTasks".equals(operation.getName())
            && operation.getSignature().length == 1
            && "int".equals(
                operation.getSignature()[0].getType())
            && "int".equals(operation.getReturnType())) {
        found = true;
    }
}

if (!found) {
    throw new IllegalStateException(
        "JMX interface mismatch for retryFailedTasks(int)"
    );
}
\`\`\`

Include this check in integration tests or startup validation when the JMX contract is a critical dependency.

## 15. Controlling state-changing operations

JMX is a management surface. An operation can reset caches, reload configurations, pause workers, or trigger retries. Therefore you need:

1. **Allowlist** of permitted published operations.
2. **Validation** of parameters and server state.
3. **Authorization** and protection of remote connectors if present.
4. **Idempotency** or duplicate-execution prevention.
5. **Scoped audit logging**, avoiding logging secrets.
6. **Timeouts/rate limits** where truly supported.
7. **Status attributes** so operators can inspect results after invoking.
8. **Avoid arbitrary operations** such as \`executeShell(String)\` or \`deleteAllData()\` unless genuinely necessary and strictly controlled.

### 15.1. Request/observe pattern

Instead of a call running for several minutes:

\`\`\`java
void rebuildEntireSearchIndex();
\`\`\`

you can design:

\`\`\`java
String requestIndexRebuild();
String getRebuildStatus(String requestId);
\`\`\`

The first operation only accepts the request and returns an ID; the client tracks progress using a read operation or attribute. A real implementation requires a queue/executor, state storage, validation, and concurrency protection.

### 15.2. Timeouts in a local proxy

With a local \`MBeanServer\`, operations may run **synchronously on the caller thread**. There is no guarantee that \`MBeanProxyFactoryBean\` automatically interrupts a long-blocking method merely because you set a \`currencyTimeLimit\` field in a descriptor.

If a real timeout is needed, design the operation asynchronously or enforce timeouts at the appropriate service/concurrency layer. If running the operation in a separate thread and timing out on the caller side, cancelling the task will not always stop server logic unless it supports interruption.

## 16. MBeanInfo and discovery before calling

A careful client can confirm the MBean is registered and the operation has the expected signature:

\`\`\`java
if (!server.isRegistered(name)) {
    throw new IllegalStateException(
        "Expected Worker MBean is missing"
    );
}

MBeanInfo info = server.getMBeanInfo(name);

for (MBeanOperationInfo operation : info.getOperations()) {
    System.out.printf(
        "Operation=%s return=%s%n",
        operation.getName(),
        operation.getReturnType()
    );
}
\`\`\`

However, a pre-check still has a **time-of-check/time-of-use race**: the MBean can be unregistered after \`isRegistered\` or \`getMBeanInfo\`, causing the invocation to fail. Hence exceptions must be handled at the actual call site, not only in preflight checks.

## 17. Spring lifecycle and MBean-not-ready errors

Common scenarios:

- Consumer invokes the proxy in \`@PostConstruct\` before the exporter registers.
- Two \`ApplicationContext\` instances start in different orders.
- Exporter registers into a custom MBeanServer while proxy points to the platform server.
- MBean is unregistered on context close while a consumer still holds the proxy.
- Bean is replaced or ObjectName changes after redeploy.
- Spring Boot auto-exporter and a custom exporter cause a name collision.

To reduce risk:

- Ensure the exporter and proxy use the same \`MBeanServer\`.
- Define lifecycle dependencies when truly needed.
- Invoke operations after the context is ready.
- Provide clear “MBean not available” handling for consumers.
- Avoid holding proxies beyond the lifecycle of the context containing the exporter.
- Run integration tests covering normal startup/shutdown.

If the exporter uses the \`IGNORE_EXISTING\` policy, the MBean name can still exist while being owned by a different component. The proxy will then invoke whatever actual object sits at that name; verify metadata before trusting it is the expected bean.

## 18. Log monitoring and error classification

A useful log when an invocation fails should contain:

\`\`\`text
event=JMX_OPERATION_FAILURE
objectName=com.example.jobs:type=Worker,name=Importer
operation=retryFailedTasks
signature=int
errorType=RuntimeMBeanException
rootCause=IllegalArgumentException
\`\`\`

This is an application-designed log example, not an automatic Spring format. Avoid logging full parameter values if they might contain tokens, PII, or sensitive business data.

### 18.1. Suggested severity classification

| Error category | Review level | Action |
| --- | --- | --- |
| Invalid input | Usually client/use-case error | Return clear message, do not retry. |
| MBean does not exist | Configuration or lifecycle error | Check exporter, ObjectName, and readiness. |
| Operation/signature contract mismatch | Compatibility or deploy error | Check runtime metadata, version. |
| Disallowed by business state | Intentional rejection | Read state and guide the operator. |
| Remote I/O timeout | Uncertain whether invocation ran | Check state, retry only when safe. |
| \`RuntimeErrorException\` | Critical error | Escalate, do not swallow exception. |
| \`SecurityException\` | Permission error | Do not self-grant broader permissions. |

### 18.2. Do not turn every error into “MBean unavailable”

If an operation ran and threw \`IllegalArgumentException\`, that is a validation error, distinct from an unregistered MBean. Lumping all errors into the same “unavailable” message degrades diagnostics and easily misleads clients into inappropriate retries.

## 19. Hands-on exercises

### Exercise 1 — Direct invocation

Register \`WorkerAdminMBean\` per section 4. Call \`retryFailedTasks(5)\` via \`MBeanServer.invoke\` with signature \`int\`. Check the return value.

**Goal:** understand \`ObjectName\`, operation name, params, and signature.

### Exercise 2 — Wrong signature

Invoke the same operation passing \`"java.lang.Integer"\` instead of \`"int"\`. Observe the exception and \`getMBeanInfo\` to understand published types.

**Goal:** avoid relying on Java autoboxing in JMX dispatch.

### Exercise 3 — Missing MBean

Unregister the MBean in an isolated test, then call the proxy or \`invoke\`. Record the error and check \`isRegistered\`.

**Goal:** recognize lifecycle and race errors.

### Exercise 4 — Operation throwing an exception

Call \`retryFailedTasks(0)\`, observe the JMX-wrapped exception, and extract \`getTargetException()\` where appropriate.

**Goal:** distinguish validation errors from the MBean versus JMX dispatch errors.

### Exercise 5 — Spring local proxy

Configure \`MBeanExporter\` and \`MBeanProxyFactoryBean\` in the same ApplicationContext. Inject \`WorkerAdminClient\`, call \`requestPause()\`, and check the \`Running\` attribute.

**Goal:** understand how a typed proxy replaces manual \`invoke\` code.

### Exercise 6 — Integration contract test

Write a test reading \`MBeanInfo\` to assert \`retryFailedTasks(int)\` exists, returns \`int\`, and \`deleteAllInternalData\` is absent. Only then run a safe operation in the test environment.

**Goal:** protect the JMX interface during refactoring.

## 20. Review questions

**1. What parameters does \`MBeanServer.invoke\` require?** \`ObjectName\`, operation name, arguments array, and signature type-name array.

**2. Why does \`"int"\` differ from \`"java.lang.Integer"\` in a signature?** Because JMX uses the declared type names in metadata to select operations, rather than defaulting to boxing like normal Java calls.

**3. Does \`MBeanProxyFactoryBean\` register an MBean itself?** No. It creates a proxy to access an MBean already existing in the MBeanServer.

**4. What does \`InstanceNotFoundException\` usually indicate?** The ObjectName does not exist in the server being used or the MBean has been unregistered.

**5. What should you inspect on \`ReflectionException\`?** Operation name, signature, and the wrapped reflection/dispatch failure.

**6. Are all operation errors wrapped in \`MBeanException\`?** No. Runtime exceptions can be inside \`RuntimeMBeanException\`; \`Error\`s can be inside \`RuntimeErrorException\`.

**7. Does a Spring proxy automatically retry safely?** Do not assume so. Clients need a retry policy based on idempotency and actual state.

**8. Does a local call need a JMX/RMI port?** No, when using a local MBeanServer directly in the same JVM.

**9. Why is reading \`MBeanInfo\` necessary?** To know the actually published operations, return types, and exact signatures.

**10. Why not invoke a production operation just to inspect metadata?** Because the operation can change state or add load; \`getMBeanInfo\` is the option with fewer side effects.

## 21. Summary

In Spring JMX, a **local MBean proxy** helps Spring code invoke management operations through a Java interface without manually writing \`MBeanServer.invoke\` everywhere. However, calls still traverse the JMX contract consisting of \`ObjectName\`, operation name, and signature, so they can still fail due to missing MBeans, contract mismatches, runtime errors, or permission errors.

Good design combines **runtime metadata verification**, **typed wrapper-exception handling**, **validation and authorization**, and **idempotency/outcome observation** for side-effecting operations, while managing the lifecycle between exporter and proxy. When diagnosing, preserve the cause chain and operation context instead of logging only a generic message.

## References

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework Javadoc — \`MBeanProxyFactoryBean\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/access/MBeanProxyFactoryBean.html
- Spring Framework Javadoc — \`MBeanClientInterceptor\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/access/MBeanClientInterceptor.html
- Java SE 21 — \`MBeanServer\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
- Java SE 21 — \`MBeanServerConnection\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerConnection.html
- Java SE 21 — \`MBeanException\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanException.html
- Java SE 21 — \`RuntimeMBeanException\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/RuntimeMBeanException.html
- Java SE 21 — \`ReflectionException\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/ReflectionException.html