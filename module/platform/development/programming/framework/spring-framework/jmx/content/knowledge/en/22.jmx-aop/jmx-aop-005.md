# Transaction proxy on a bean with @ManagedResource in Spring JMX

## 1. Objectives

In the Spring Framework, \`@Transactional\` is typically implemented via a **Spring AOP proxy**. Meanwhile, \`@ManagedResource\` and annotations such as \`@ManagedAttribute\` and \`@ManagedOperation\` are used to describe the JMX management interface for a Spring bean.

When **the same bean both carries JMX metadata and is wrapped by Spring with a transaction proxy**, MBean registration and invocation gain an extra layer of indirection. Without understanding proxies, an application may exhibit symptoms such as:

- A bean has \`@ManagedResource\`, yet is not auto-detected for export.
- The \`ObjectName\` is absent or does not match expectations.
- JMX attributes/operations do not appear even though methods are annotated.
- A JMX operation appears, yet invoking it fails because the method is not on the proxy interface.
- The method can be invoked, yet a transaction does not start as expected.
- Internal method calls (\`self-invocation\`) prevent \`@Transactional\` from taking effect in proxy mode.
- The MBean exporter and transaction infrastructure initialize the wrong object class or hit lifecycle conflicts.

**Core mindset:** JMX metadata resides on the declared class/methods, whereas the object \`MBeanExporter\` actually receives may be an **AOP proxy**. Transactions take effect when calls pass through the Spring-managed proxy, not merely because the annotation exists in source code.

After this lesson, you will be able to:

1. Explain the interaction between \`@ManagedResource\` and \`@Transactional\`.
2. Distinguish between the target object, Spring bean reference, JDK dynamic proxy, and class-based proxy.
3. Identify scenarios where the JMX metadata reader must locate annotations on the target class.
4. Understand the conditions for a JMX operation to pass through the transaction interceptor.
5. Choose a stable management facade design for JMX.
6. Diagnose errors involving uninvokable methods via proxy, self-invocation, and anomalous transactions.
7. Write integration tests verifying registration, \`MBeanInfo\`, and actual transaction boundaries.

## 2. Two independent mechanisms to distinguish

### Spring JMX export

\`\`\`text
@ManagedResource / @ManagedOperation / @ManagedAttribute
                       |
                       v
             AnnotationJmxAttributeSource
                       |
              MetadataMBeanInfoAssembler
                       |
                 MBeanExporter
                       |
                   MBeanServer
                       |
                    JMX client
\`\`\`

The JMX exporter determines which beans appear and what the management interface contains. It **does not automatically create database transactions** merely because an operation is exposed.

### Spring transaction AOP

\`\`\`text
Caller --> Spring proxy --> TransactionInterceptor --> Target method
                                   |
                            begin / join transaction
                                   |
                            commit / rollback
\`\`\`

\`@Transactional\` requires transaction management to be enabled and a suitable \`PlatformTransactionManager\` or transaction manager to exist. In proxy mode, calls must pass through the proxy for the transaction interceptor to have a chance to apply.

### Where the two mechanisms meet

\`\`\`text
                    Spring ApplicationContext
                            |
                      Transaction proxy
                            |
                      Target service
                  @ManagedResource
                  @ManagedOperation
                  @Transactional
                            |
                       MBeanExporter
                            |
                       MBeanServer
                            |
                     JMX client invoke()
\`\`\`

In this diagram, Spring can provide the proxy as the bean object. The exporter needs to recognize metadata on the target class and build a JMX interface callable through the proxy.

**You cannot conclude generally that every annotation placement, proxy type, and Spring version behaves identically.** You must examine the proxy type and actually test the invocation path.

## 3. Target object and AOP proxy

Suppose you have a bean:

\`\`\`java
@Service
@ManagedResource(
    objectName = "com.example.monitoring:type=Payment,name=Settlement"
)
public class SettlementService {

    @Transactional
    @ManagedOperation(description = "Reconcile settlement records")
    public void reconcile() {
        // Write data inside a transaction.
    }
}
\`\`\`

If transaction advice is applied, \`ApplicationContext.getBean(SettlementService.class)\` may return a proxy object rather than a plain instance. That proxy forwards valid calls to the target, yet may have a different runtime type and set of exposed methods.

| Concept | Meaning |
|---|---|
| **Target class** | Class implementing the methods and carrying the annotations |
| **Proxy object** | Object returned by Spring to apply advice |
| **JDK dynamic proxy** | Proxy implementing one or more interfaces |
| **CGLIB/class-based proxy** | Proxy based on a subclass of the target class |
| **MBeanExporter** | Registers selected objects as MBeans |
| **JMX metadata** | Information used to describe names, attributes, and operations |

In some situations Spring AOP/JMX supports resolving the target class and target methods. However, if a management operation is unavailable through the exported proxy, clients may encounter \`ReflectionException\`, \`MBeanException\`, or another exception depending on the implementation.

## 4. JDK dynamic proxy and interface limitations

### 4.1. Service interface example

\`\`\`java
public interface SettlementOperations {
    void reconcile();
}
\`\`\`

Implementation:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@ManagedResource(
    objectName = "com.example.monitoring:type=Payment,name=Settlement"
)
public class SettlementService implements SettlementOperations {

    @Override
    @Transactional
    @ManagedOperation(description = "Reconcile payments")
    public void reconcile() {
        // Business work.
    }

    @ManagedOperation(description = "Read internal diagnostic details")
    public String diagnostics() {
        return "OK";
    }
}
\`\`\`

When Spring creates a **JDK proxy**, the proxy object exposes the methods of the proxied interfaces. \`reconcile()\` is in \`SettlementOperations\`; \`diagnostics()\` is only on the implementation and not on the interface.

This can lead to the situation:

\`\`\`text
JMX metadata:
  reconcile()              -> managed operation
  diagnostics()            -> managed operation

JDK proxy type:
  reconcile()              -> present
  diagnostics()            -> absent
\`\`\`

If the assembler builds operations from the target class yet the invoker tries to call the method directly on the JDK proxy, an operation missing from the proxy may not be executable.

**Principle:** With a JDK proxy, management methods should reside on an interface that the proxy actually exposes, or be separated into a dedicated management bean. Do not rely solely on annotations on implementation methods while ignoring the proxy interface.

### 4.2. When the interface is unsuitable for JMX

A large business service interface may contain many business methods that should not be exposed. Do not add every management method to the business interface just to satisfy a JDK proxy.

A better solution is to create a **management facade** with a small JMX API containing only operational methods. The facade is managed by Spring and calls the injected service, so the service's transaction proxy is still used.

## 5. Class-based proxy (CGLIB) and its limitations

A class-based proxy creates a runtime subclass to intercept calls on overridable methods.

Example enabling class-based proxies in transaction configuration:

\`\`\`java
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration
@EnableTransactionManagement(proxyTargetClass = true)
public class TransactionConfiguration {
}
\`\`\`

Or in Spring Boot, proxy type selection may be influenced by auto-configuration and the \`spring.aop.proxy-target-class\` property; check your actual Boot version.

Advantages of class-based proxies:
- Methods are not forced to appear on a service interface as with JDK proxies.
- Many public methods of the target class can be invoked through the proxy.

Limitations:
- \`final\` classes cannot be subclassed under this mechanism.
- \`final\` methods cannot be overridden for advice.
- \`private\` methods cannot be intercepted under proxy-based AOP.
- Self-invocation issues still remain.
- Metadata and proxy invocation still need to be verified at runtime.

Do not conclude "switching to CGLIB solves everything". It may resolve the issue of methods missing from a JDK proxy interface, yet it does not change the nature of proxy-based transactions or replace designing a clear management API.

## 6. Do JMX operation calls pass through @Transactional?

The answer depends on the **actual call path** and whether the registered object is a proxy or a target.

### Case A: JMX calls through a Spring transaction proxy

\`\`\`text
JMX client
   |
   v
MBeanServer.invoke()
   |
   v
Spring-exported proxy
   |
   v
TransactionInterceptor
   |
   v
Target method @Transactional
\`\`\`

If the exporter registers/adapts the proxy properly, the JMX operation maps to a method callable through the proxy, and with transaction management enabled, a transaction can begin just like a normal Spring call.

### Case B: JMX calls the target directly, bypassing the proxy

\`\`\`text
JMX client
   |
   v
MBeanServer.invoke()
   |
   v
Raw target object
   |
   v
@Transactional method
   |
   v
No transaction interceptor from Spring proxy
\`\`\`

The \`@Transactional\` annotation in source code **does not automatically create a transaction** if the call path does not pass through a transaction interceptor. This also happens when code instantiates an object with \`new\` or when an exporter directly registers an instance that is not a Spring proxy.

### Case C: Transaction advice is not configured

If the project lacks an appropriate transaction manager or transaction management is not enabled, having the annotation is insufficient to guarantee transactions at runtime.

**Do not assume transactions work merely by checking whether the class has \`@Transactional\`.** Verify the call path and transaction status in an integration test.

## 7. Self-invocation: a common trap

Example:

\`\`\`java
@Service
@ManagedResource(
    objectName = "com.example.monitoring:type=Worker,name=Import"
)
public class ImportService {

    @ManagedOperation
    public void runNow() {
        importBatch(); // called via this, not via Spring proxy
    }

    @Transactional
    public void importBatch() {
        // Database writes.
    }
}
\`\`\`

In Spring AOP proxy mode, \`runNow()\` calling \`importBatch()\` on the same target (\`this\`) typically **does not pass through the transaction proxy**. Therefore, \`@Transactional\` on \`importBatch()\` may not be applied to this internal call.

Distinguish:
- If \`runNow()\` is annotated with \`@Transactional\` and JMX calls via the proxy, a transaction can wrap the entire method.
- If only \`importBatch()\` is annotated and called from \`runNow()\` via \`this\`, the advice on \`importBatch()\` is not applied by the proxy.
- If \`runNow()\` calls a transactional method on **another injected bean**, calling through that bean's proxy can trigger advice.

### Separating into another service

\`\`\`java
@Service
public class ImportTransactionalService {

    @Transactional
    public void importBatch() {
        // Database work.
    }
}
\`\`\`

\`\`\`java
@Component
@ManagedResource(
    objectName = "com.example.monitoring:type=Worker,name=Import"
)
public class ImportManagement {

    private final ImportTransactionalService service;

    public ImportManagement(ImportTransactionalService service) {
        this.service = service;
    }

    @ManagedOperation(description = "Request an import batch")
    public void runNow() {
        service.importBatch(); // called via injected Spring bean
    }
}
\`\`\`

This model clearly separates:
- **Management facade:** the JMX management API.
- **Transactional service:** business logic and transaction boundary.
- **Spring proxy:** sits on the injected service reference when transaction advice is active.

This is usually easier to verify and maintain than directly exporting a large service that has both AOP and JMX methods.

## 8. Configuring Spring JMX and transactions

Spring Framework Java configuration example:

\`\`\`java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration
@EnableMBeanExport
@EnableTransactionManagement
public class AppConfiguration {
}
\`\`\`

\`@EnableMBeanExport\` enables annotation-driven JMX export. \`@EnableTransactionManagement\` enables transaction annotation processing in the context.

However, these configuration annotations do not automatically:
- Create a database or \`DataSource\`.
- Provide an appropriate \`PlatformTransactionManager\`.
- Configure security for remote JMX.
- Define full business rollback/commit semantics.
- Turn every Spring bean into an MBean.

You must have a \`DataSource\`, repositories, and an appropriate transaction manager for your actual stack. With Spring Boot, many pieces can be auto-configured, but you must still verify at runtime.

### XML configuration

For Spring XML projects:

\`\`\`xml
<tx:annotation-driven/>

<context:mbean-export/>
\`\`\`

You must declare the XML namespaces and schema locations for \`tx\` and \`context\` respectively. These two elements perform two different tasks: transaction proxying and JMX export.

A complete example:

\`\`\`xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:context="http://www.springframework.org/schema/context"
       xmlns:tx="http://www.springframework.org/schema/tx"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/context
           https://www.springframework.org/schema/context/spring-context.xsd
           http://www.springframework.org/schema/tx
           https://www.springframework.org/schema/tx/spring-tx.xsd">

    <context:component-scan base-package="com.example"/>

    <tx:annotation-driven/>

    <context:mbean-export/>

    <!-- DataSource / transaction manager must still be configured appropriately. -->
</beans>
\`\`\`

If a transaction manager is not properly configured/auto-wired in the context, \`<tx:annotation-driven/>\` does not automatically create a valid transaction boundary for all persistence technologies.

## 9. Annotation placement on classes and methods

A bean can be annotated at the class level:

\`\`\`java
@ManagedResource(...)
@Transactional
public class PaymentService { ... }
\`\`\`

or per method:

\`\`\`java
@ManagedOperation
@Transactional
public void reconcile() { ... }
\`\`\`

What to understand:

- \`@ManagedResource\` is class-level metadata for Spring JMX.
- \`@ManagedOperation\` is metadata for a method exposed via JMX.
- \`@Transactional\` is metadata for transaction advice.
- They are read by **different mechanisms**.
- There is no general rule that placing both annotations on the same method guarantees JMX invocation through a proxy in every configuration.

With JDK proxies, interface methods and annotation lookup must be checked. With CGLIB, subclass behavior and visibility govern interception capability.

If the JMX metadata reader finds the right method on the target class yet actual JMX invocation targets a different object/method, a mismatch can arise between **published metadata** and **executability**.

## 10. MBeanExporter, metadata assembler, and proxies

In Spring JMX annotation-based export, the components involved are:

- \`AnnotationJmxAttributeSource\`: reads \`@ManagedResource\`, \`@ManagedAttribute\`, \`@ManagedOperation\`.
- \`MetadataMBeanInfoAssembler\`: builds the management interface from metadata.
- \`MetadataNamingStrategy\`: obtains the \`ObjectName\` from class-level metadata.
- \`MBeanExporter\`: selects beans and registers MBeans on \`MBeanServer\`.
- Spring AOP infrastructure: creates proxies to apply transaction advice.

Things to watch out for:

1. **Autodetection:** the exporter must properly detect beans carrying metadata even when the runtime bean is a proxy.
2. **Naming:** the strategy must read the \`ObjectName\` from the target class if the annotation is not on the proxy class.
3. **Assembly:** the assembler must determine which management getters/methods can actually be invoked.
4. **Invocation:** calls must pass through the appropriate proxy if transactions are required.
5. **Lifecycle:** the exporter must register/unregister the right objects without breaking bean references.

The Spring Framework has support for AOP proxies in certain JMX export paths, but exact behavior depends on proxy type, interfaces, annotations, and version. **Do not replace integration tests with assumptions that the infrastructure handles every case automatically.**

## 11. A transaction proxy is not an MBean proxy

In JMX there is also the concept of a client-side **MBean proxy**:

\`\`\`java
MyMonitorMBean proxy = JMX.newMBeanProxy(
    connection,
    objectName,
    MyMonitorMBean.class
);
\`\`\`

This is a client-side proxy that translates method calls into JMX requests.

A Spring transaction proxy, on the other hand, is a server-side AOP proxy handling cross-cutting advice such as transactions.

\`\`\`text
JMX Client
  MBean proxy (optional)
       |
       v
  MBeanServerConnection
       |
       v
  JMX MBeanServer
       |
       v
  Spring transaction proxy (if exported/called through it)
       |
       v
  Target business method
\`\`\`

The two proxies exist at two different layers:
- An MBean proxy lets clients call JMX using a typed Java interface.
- A transaction proxy lets Spring apply transaction boundaries.
- An MBean proxy does not automatically guarantee transactions on the target.
- A transaction proxy does not automatically enable a JMX remote connector.

## 12. Diagnostics: the bean exists in Spring, yet the MBean is missing

If the application starts up successfully yet the MBean is missing:

1. Verify the Spring bean exists in \`ApplicationContext\`.
2. Check whether \`@ManagedResource.objectName\` is valid.
3. Check \`@EnableMBeanExport\`, XML \`<context:mbean-export/>\`, or Boot JMX auto-configuration.
4. Check the transaction proxy type and target class.
5. Check whether the metadata reader/naming strategy reads annotations properly.
6. Check whether the exporter selected the bean.
7. Check the target \`MBeanServer\`.
8. Check for \`ObjectName\` collisions or registration errors.
9. Use \`queryNames()\` or \`isRegistered()\` to verify.

Do not conclude that \`@Transactional\` automatically prevents an MBean from being exported. The issue lies in compatibility across discovery, metadata, and invocation in the specific configuration.

### Checking whether a bean is a Spring AOP proxy

\`\`\`java
import org.springframework.aop.support.AopUtils;

Object bean = context.getBean("settlementService");

System.out.println(AopUtils.isAopProxy(bean));
System.out.println(AopUtils.isJdkDynamicProxy(bean));
System.out.println(AopUtils.isCglibProxy(bean));
System.out.println(AopUtils.getTargetClass(bean));
\`\`\`

This provides diagnostic information about the runtime proxy, not final proof that a transaction actually starts on JMX calls.

## 13. Inspecting MBeanInfo and invoking operations

Suppose the MBean has been registered:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "com.example.monitoring:type=Payment,name=Settlement"
);

if (!server.isRegistered(name)) {
    throw new IllegalStateException(
        "MBean not registered: " + name
    );
}

MBeanInfo info = server.getMBeanInfo(name);

for (var operation : info.getOperations()) {
    System.out.println(
        "Operation: " + operation.getName()
    );
}
\`\`\`

Then invoke in a test environment:

\`\`\`java
server.invoke(
    name,
    "reconcile",
    new Object[0],
    new String[0]
);
\`\`\`

A successful return from \`invoke()\` proves the operation runs via the JMX interface, yet **does not by itself prove a transaction started**. You must observe active transaction state or commit/rollback results.

If the exporter uses a server other than the platform \`MBeanServer\`, you must query the right server. If calling remotely, you need an \`MBeanServerConnection\` and network error handling.

## 14. Verifying the transaction boundary at runtime

In a service using a transaction proxy, you can check whether a transaction is active inside the method using the Spring API:

\`\`\`java
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Transactional
public void reconcile() {
    boolean active =
        TransactionSynchronizationManager.isActualTransactionActive();

    System.out.println("Active transaction: " + active);

    // Business logic...
}
\`\`\`

In an integration test, it is better to assert:

\`\`\`java
if (!TransactionSynchronizationManager
        .isActualTransactionActive()) {

    throw new IllegalStateException(
        "Expected an active transaction"
    );
}
\`\`\`

**Note:** \`isActualTransactionActive()\` reflects Spring's thread-bound transaction state, not the sole proof for every transaction/reactive model. For reactive transactions using Reactor context, verification differs. This lesson primarily covers proxy-based imperative transaction management.

### Testing rollback

A reliable integration test can:
1. Invoke the JMX operation through \`MBeanServer\`.
2. Let the operation pass through the Spring service.
3. Have the service write a record to the database and then throw an unchecked exception.
4. After the call, query the database to verify the record was rolled back.
5. Repeat with an incorrect self-invocation design for comparison (in an isolated test environment).

Do not use a production database to test rollback or invoke operations with real effects solely to check proxies.

## 15. Good design pattern: JMX management facade

This is usually the easiest solution to operate when a business bean has complex transactions/AOP.

### Business service

\`\`\`java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class SettlementService {

    @Transactional
    public void reconcile() {
        // Database transaction.
    }

    @Transactional(readOnly = true)
    public long countPending() {
        return 12;
    }
}
\`\`\`

### Management facade

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.monitoring:type=Payment,name=Settlement",
    description = "Settlement administration"
)
public class SettlementManagement {

    private final SettlementService service;

    public SettlementManagement(SettlementService service) {
        this.service = service;
    }

    @ManagedAttribute(description = "Number of pending settlements")
    public long getPendingCount() {
        return service.countPending();
    }

    @ManagedOperation(description = "Request settlement reconciliation")
    public void reconcile() {
        service.reconcile();
    }
}
\`\`\`

Advantages:
- The MBean has a small, clear JMX interface.
- \`@ManagedResource\` sits on a facade that does not necessarily need to be wrapped by a transaction proxy.
- The business service is still injected via a Spring bean reference.
- Calls from the facade to the service pass through the transaction proxy in normal configurations.
- Easy to test \`ObjectName\`, \`MBeanInfo\`, and rollback separately.
- Validation and authorization can be enforced at the management layer before calling business logic.

Limitations:
- Adds a facade class and some delegate methods.
- If the facade runs overly heavy database queries inside getters, it can still impact JMX performance.
- Operations with side effects must still be protected by JMX security, not merely because a facade exists.

## 16. Transaction proxy and JMX scenarios

| Scenario | What may happen | Recommendation |
|---|---|---|
| Bean uses \`@ManagedResource\` and has no AOP proxy | Annotation export is relatively direct | Verify \`MBeanInfo\` and \`ObjectName\` |
| Bean uses JDK proxy; operation is in interface | Operation can be invoked via proxy | Test active transaction and method visibility |
| Bean uses JDK proxy; operation is only on implementation | Operation may be missing or uninvokable | Put method in an appropriate interface or use a facade |
| Bean uses CGLIB proxy | Many class methods can be intercepted | Avoid final/private and self-invocation |
| JMX registers raw target instead of proxy | \`@Transactional\` may be bypassed | Register the Spring-managed proxy or extract a facade |
| JMX facade injects transactional service | Service call can pass through transaction interceptor | Design is usually easy to maintain |
| JMX operation calls transactional method via \`this\` | Self-invocation bypasses advice on the called method | Move logic to another bean |
| Reactive transactions | Thread-bound check may not apply | Use reactive transaction APIs/tests |

Do not blame every JMX+AOP error on \`@Transactional\`. The cause may be naming, metadata, \`MBeanServer\`, the exporter, proxy method exposure, or transaction manager configuration.

## 17. Exception handling and rollback when invoking via JMX

A \`@Transactional\` method can roll back or commit depending on:
- Exception type.
- \`rollbackFor\`/\`noRollbackFor\` rules.
- Propagation behavior.
- Transaction manager.
- Whether the exception is caught before leaving the interceptor.

Example:

\`\`\`java
@Transactional(rollbackFor = Exception.class)
public void reconcile() throws Exception {
    repository.save(...);

    if (validationFailed()) {
        throw new Exception("Cannot reconcile");
    }
}
\`\`\`

If the exception passes through the transaction interceptor, Spring applies the configured rollback rules. At the JMX layer, the exception may be wrapped in \`MBeanException\` or appropriate JMX exceptions; clients need to inspect the cause to see the business error.

**Do not rely on JMX exception wrapping to infer commit/rollback.** The transaction decision occurs in the Spring transaction layer; results must be verified against the business contract.

### Remote JMX retries

For operations that modify a database, a network disconnect can occur after the server has committed yet before the client receives the response. If the client blindly retries, a new transaction may run again.

When using remote JMX operations:
- Design them to be idempotent if possible.
- Include an operation/request ID for reconciliation if needed.
- Avoid using remote JMX as a primary transactional business API.
- Do not allow sensitive operations to run twice solely because of client timeouts.

## 18. When should @Transactional be used directly on a management method?

You can use \`@Transactional\` directly on a JMX method if:
- The management method genuinely needs a transaction.
- A Spring transaction proxy is created.
- The exporter actually calls through the proxy.
- The method can be intercepted in the active proxy mode.
- Integration tests prove the boundary and rollback.

Example:

\`\`\`java
@Component
@ManagedResource(
    objectName = "com.example.monitoring:type=Cache,name=Admin"
)
public class CacheAdmin {

    @ManagedOperation
    @Transactional
    public void refreshDatabaseBackedCache() {
        // Transactional refresh.
    }
}
\`\`\`

This is not inherently wrong. However, with a JMX management interface that has multiple operations or complex business logic, separating a facade and a transactional service generally creates clearer boundaries.

Do not add \`@Transactional\` to every JMX getter. A getter querying a database inside a transaction can create overhead and locks; if only monitoring metrics are needed, optimize and consider snapshot/cached metrics.

## 19. Securing JMX transaction operations

A JMX operation can open a transaction and modify production data. This gives it risk equivalent to an administrative API:

- Export only genuinely necessary operations.
- Protect authentication/authorization on the JMX remote connector.
- Restrict \`invoke\` and \`setAttribute\` permissions.
- Do not expose credentials, tokens, or personal data in attributes/exceptions.
- Write audit logs for critical operations.
- Validate parameters and preserve idempotency or duplicate-execution guards.
- Configure appropriate concurrency limits and timeouts.
- Avoid long-running transactions triggered uncontrollably via JMX.
- Use a different business administration mechanism when workflows, approvals, or high delivery reliability are needed.

\`@ManagedOperation(description="Admin only")\` does not grant or check permissions by itself. Description is metadata, not an authorization policy.

## 20. Practice exercises

### Exercise A — Checking proxy type

1. Create a Spring service with \`@Transactional\`.
2. Enable transaction management.
3. Use \`AopUtils.isAopProxy()\` and \`getTargetClass()\` to inspect the bean.
4. Switch between JDK dynamic proxy and class-based proxy in a test environment.
5. Record which methods are actually callable on the proxy.

### Exercise B — Exposing the service directly

1. Put \`@ManagedResource\` on a transactional service.
2. Annotate a method with \`@ManagedOperation\`.
3. Enable JMX export.
4. Verify the \`ObjectName\` and \`MBeanInfo\`.
5. Call \`MBeanServer.invoke()\`.
6. Check whether a transaction is active inside the method.
7. If it fails, distinguish discovery/metadata/invocation/transaction errors.

### Exercise C — Self-invocation

1. Create a \`runNow()\` method calling \`this.importBatch()\`.
2. Annotate only \`importBatch()\` with \`@Transactional\`.
3. Call \`runNow()\` from JMX.
4. Observe whether a transaction is active inside \`importBatch()\`.
5. Move \`importBatch()\` into an injected Spring service.
6. Re-run the test and compare.

### Exercise D — JMX Facade

1. Create \`SettlementService\` with \`@Transactional\`.
2. Create \`SettlementManagement\` with \`@ManagedResource\`.
3. Inject \`SettlementService\` into the facade.
4. Expose one read-only getter and one operation.
5. Inspect \`MBeanInfo\` and rollback behavior.
6. Simulate a network timeout (test environment only) and discuss idempotency.

## 21. Self-check questions

**Question 1.** Does \`@ManagedResource\` automatically enable transactions?  
**Answer:** No. It provides JMX metadata; transactions are managed by Spring's transaction infrastructure.

**Question 2.** Why does a method with \`@Transactional\` sometimes not run in a transaction when invoked via JMX?  
**Answer:** The call may not pass through the Spring transaction proxy, the method may not be intercepted, or transaction management may not be configured properly.

**Question 3.** How do JDK proxies affect JMX methods?  
**Answer:** JDK proxies primarily expose methods belonging to proxied interfaces; methods only on the implementation may not be callable through the proxy.

**Question 4.** Does a CGLIB proxy solve self-invocation?  
**Answer:** No. Internal calls from the target that do not pass through the proxy can still bypass advice.

**Question 5.** What is the benefit of using a management facade that calls an injected transactional service?  
**Answer:** Management and business boundaries are separated; the facade can call the service through the Spring proxy so transaction advice operates.

**Question 6.** Can you prove a transaction is active merely because \`MBeanServer.invoke()\` returns?  
**Answer:** No. You must check the transaction status or commit/rollback in an integration test.

**Question 7.** Does a remote JMX invoke timeout prove the transaction did not commit?  
**Answer:** No. The server may have committed while the response was lost; idempotency and state reconciliation are needed before retrying.

## 22. Remember

- Spring JMX and Spring transaction AOP are two independent mechanisms that interact when the same bean carries both \`@ManagedResource\` and \`@Transactional\`.
- JMX metadata may live on the target class while the runtime Spring bean is a proxy.
- With JDK proxies, management methods must be available on an interface; class-based proxies have final/private limitations.
- \`@Transactional\` in proxy mode only takes effect when calls pass through the transaction interceptor.
- Self-invocation is a common cause of transaction annotations on internal methods not running.
- Registering the raw target instead of the Spring proxy can bypass transaction advice.
- **A management facade injecting a transactional service** is often a suitable design to reduce dependence on proxy types.
- Always verify both the JMX interface (\`MBeanInfo\`) and the transaction boundary (active transaction, rollback/commit).
- Remote JMX invoke has distributed-call failure semantics; do not blindly retry operations with side effects.
- Protect invocation permissions for management operations like any sensitive administrative API.

### References

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework Reference — Transaction Management: https://docs.spring.io/spring-framework/reference/data-access/transaction.html
- Spring Framework Reference — Understanding the Spring Framework’s Declarative Transaction Implementation: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html
- Spring Framework Reference — Proxying Mechanisms: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Framework Javadoc — \`@ManagedResource\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedResource.html
- Spring Framework Javadoc — \`MBeanExporter\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporter.html
- Spring Framework Javadoc — \`AopUtils\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/aop/support/AopUtils.html
- Java SE 21 API — \`MBeanServer\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
