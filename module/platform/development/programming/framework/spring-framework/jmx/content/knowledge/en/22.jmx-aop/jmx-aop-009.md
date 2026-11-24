# Testing JMX with AOP, transactions, and async in the Spring Framework

## 1. Learning objectives

After this lesson, you will be able to:

- Describe the relationship among **JMX MBean**, **Spring AOP proxy**, **transaction interceptor**, and **asynchronous method invocation**.
- Distinguish calls passing through a **Spring proxy** from calls directly into the target object, especially when the MBean is exported via \`MBeanExporter\`.
- Design integration tests confirming a JMX operation actually triggers \`@Transactional\` or \`@Async\` as configured, rather than merely checking that annotations exist.
- Detect issues caused by **self-invocation**, JDK dynamic proxies, CGLIB class proxies, interface exposure, and metadata assemblers.
- Know how to avoid assuming an operation returning \`void\` or \`Future\` means business work has completed successfully.
- Inspect transaction status via \`TransactionSynchronizationManager\`, and verify async behavior via threads and controlled outcomes.
- Organize safe tests with \`MBeanServer\`, unique \`ObjectName\` values, lifecycle cleanup, and isolation.
- Understand the limitations of tests having \`@Transactional\` on the test method, different threads, and fake transaction managers.
- Handle exceptions, logging, timeouts, and observability so JMX operations do not create hard-to-control side effects.

## 2. Context: why do JMX + AOP need dedicated testing?

Spring JMX provides a way to export Java/Spring beans as MBeans. Spring AOP provides advice and interceptor mechanisms to apply transactions, async execution, logging, authorization, caching, or many other cross-cutting concerns.

In ordinary Java code:

\`\`\`java
service.processBatch();
\`\`\`

can pass through a Spring proxy if \`service\` is a proxied Spring bean. In JMX, however, calls pass through another layer:

\`\`\`text
JConsole / JMX client
          |
          v
     MBeanServer.invoke(...)
          |
          v
 MBean registered by Spring exporter
          |
          v
 ModelMBean / JMX adapter or Standard MBean
          |
          v
 Spring bean / Spring proxy / target object
          |
          v
 AOP interceptors:
    - TransactionInterceptor
    - AsyncExecutionInterceptor
    - custom aspects
          |
          v
 Business logic
\`\`\`

**Key point:** AOP takes effect only when invocations pass through the appropriate proxy/advice. You cannot conclude "because a method has \`@Transactional\`, every way of calling that method has a transaction", or "because a method has \`@Async\`, a JMX invoke definitely runs on another thread".

The JMX exporter can be configured to register a proxy object, a target object, a Standard MBean, or a Model MBean wrapper. Each approach has a different call path. Therefore, you must **observe runtime outcomes** via \`MBeanServer\` and transaction/async signals instead of trusting configuration alone.

## 3. Components to distinguish

| Component | Responsibility | What to verify |
| --- | --- | --- |
| \`MBeanExporter\` | Selects and registers beans in \`MBeanServer\`. | Are the right object, \`ObjectName\`, and metadata exported? |
| \`MBeanInfoAssembler\` | Determines published attributes and operations. | Do expected operations appear with the right signatures? |
| \`MBeanServer\` | JMX registry and dispatcher. | \`isRegistered\`, \`getMBeanInfo\`, \`invoke\`. |
| Spring AOP proxy | Applies advice/interceptors when calls pass through the proxy. | Is JMX calling the proxy or the target? |
| \`@Transactional\` | Directs transaction advice per policy and transaction manager. | Is a transaction active inside the executed code? |
| \`@Async\` | Directs async advice to dispatch execution to an executor. | On which thread does the body run, and when does it finish? |
| \`TransactionSynchronizationManager\` | Holds transaction state bound to the Spring thread. | Proves a transaction is genuinely active. |
| \`@EnableTransactionManagement\` | Activates transaction interception configuration. | Is transaction advice created? |
| \`@EnableAsync\` | Activates async invocation configuration. | Are the executor and advice applied? |

Distinguish **MBean export** as a management concern from **AOP proxying** as an invocation concern. Annotations for the two do not substitute for one another.

## 4. Common mistake: self-invocation

Suppose:

\`\`\`java
@Service
public class ImportService {

    public void requestRun() {
        runInTransaction();
    }

    @Transactional
    public void runInTransaction() {
        // Update database.
    }
}
\`\`\`

In normal Spring AOP proxy mode, the call from \`requestRun()\` to \`runInTransaction()\` via \`this\` does not pass through the proxy. The transaction interceptor may **not run** even though the target method has \`@Transactional\`.

If JMX publishes:

\`\`\`java
@ManagedOperation
public void requestRun() {
    importService.requestRun();
}
\`\`\`

then the outcome also depends on how \`importService\` is injected and which method calls next. When the service's \`requestRun()\` calls \`runInTransaction()\` on itself, self-invocation remains a problem.

A clearer separation of responsibilities:

\`\`\`text
JMX admin adapter
      |
      v
ImportOrchestrator (proxy)
      |
      v
TransactionalWorkerService (proxy)
      |
      v
Database transaction
\`\`\`

Here, **the JMX adapter injects the service** and invokes public methods managed by the Spring proxy. For \`@Async\`, extracting the async method into another bean also avoids self-invocation.

## 5. Recommended application structure example

### 5.1. Transactional service

\`\`\`java
package example.jmx;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Service
public class TransactionalJobService {

    @Transactional
    public boolean runTransactionalStep() {
        return TransactionSynchronizationManager
            .isActualTransactionActive();
    }
}
\`\`\`

This is an example for verifying transaction status inside the body. For a real transaction, the application context needs transaction management enabled and a suitable \`PlatformTransactionManager\`. Without a transaction manager, the method may not behave as expected or startup/invocation may fail.

### 5.2. Async service

\`\`\`java
package example.jmx;

import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class AsyncJobService {

    @Async("managementTaskExecutor")
    public CompletableFuture<String> runAsyncStep() {
        return CompletableFuture.completedFuture(
            Thread.currentThread().getName()
        );
    }
}
\`\`\`

\`@Async\` requires \`@EnableAsync\` (or equivalent configuration) and an executor with the matching bean name. Returning \`CompletableFuture.completedFuture(...)\` inside the method does not itself prove asynchronicity; the signal to check is **whether the body executes on an executor thread**.

### 5.3. JMX management adapter

\`\`\`java
package example.jmx;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.jobs:type=Probe,name=Aop",
    description = "JMX and AOP integration probe"
)
public class JmxAopProbe {

    private final TransactionalJobService transactionalJob;
    private final AsyncJobService asyncJob;

    public JmxAopProbe(
            TransactionalJobService transactionalJob,
            AsyncJobService asyncJob) {
        this.transactionalJob = transactionalJob;
        this.asyncJob = asyncJob;
    }

    @ManagedOperation(
        description = "Return whether a transactional service call is active"
    )
    public boolean probeTransaction() {
        return transactionalJob.runTransactionalStep();
    }

    @ManagedOperation(
        description = "Return worker thread used by the async service"
    )
    public String probeAsyncThread() throws Exception {
        CompletableFuture<String> future =
            asyncJob.runAsyncStep();

        return future.get(5, TimeUnit.SECONDS);
    }

    @ManagedAttribute(
        description = "Management adapter is available"
    )
    public boolean isAvailable() {
        return true;
    }
}
\`\`\`

Both operations return simple types for JMX clients. \`probeAsyncThread()\` uses \`future.get(...)\` to illustrate observation, yet **it blocks the caller** for up to the wait timeout; in a real system, consider a request/status pattern for long-running tasks.

**This is a probe for lab/test environments**, not a management API to publish in production without reviewing access control.

## 6. Configuring transaction, async, and exporter

Java configuration example:

\`\`\`java
package example.jmx;

import java.util.concurrent.Executor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration
@EnableMBeanExport
@EnableAsync
@EnableTransactionManagement
public class JmxAopTestConfiguration {

    @Bean(name = "managementTaskExecutor")
    public Executor managementTaskExecutor() {
        ThreadPoolTaskExecutor executor =
            new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(1);
        executor.setMaxPoolSize(2);
        executor.setQueueCapacity(20);
        executor.setThreadNamePrefix("management-async-");
        executor.initialize();
        return executor;
    }
}
\`\`\`

You must configure an environment-appropriate **transaction manager**. In a real integration test, you can use \`DataSourceTransactionManager\` with an embedded database or a JPA transaction manager. Adding \`@EnableTransactionManagement\` alone does not create a transaction manager if no matching bean exists.

If the application already uses Spring Boot, part of the transaction/async/JMX configuration may be auto-configured or project-defined. Do not create an extra exporter with a duplicate \`ObjectName\` when Boot already exports the corresponding MBeans.

### 6.1. Note on Spring profiles in tests

\`\`\`java
@Profile("test")
@EnableMBeanExport
@Configuration
public class TestOnlyJmxConfig {
}
\`\`\`

Profiles help restrict probes to test environments. However, they are **not a security boundary** if another exporter still exports this bean. Register probe beans only in the test \`ApplicationContext\`, rather than keeping them in production application component scanning when unnecessary.

## 7. Checking before invoking: MBeanInfo

An integration test should verify that operations exist with the right signatures before executing them:

\`\`\`java
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

ObjectName name = new ObjectName(
    "com.example.jobs:type=Probe,name=Aop"
);

if (!server.isRegistered(name)) {
    throw new AssertionError("JMX probe is not registered");
}

MBeanInfo info = server.getMBeanInfo(name);

boolean hasTransactionProbe = false;
boolean hasAsyncProbe = false;

for (MBeanOperationInfo operation : info.getOperations()) {
    if ("probeTransaction".equals(operation.getName())
            && operation.getSignature().length == 0
            && "boolean".equals(operation.getReturnType())) {
        hasTransactionProbe = true;
    }

    if ("probeAsyncThread".equals(operation.getName())
            && operation.getSignature().length == 0
            && "java.lang.String".equals(
                operation.getReturnType())) {
        hasAsyncProbe = true;
    }
}

if (!hasTransactionProbe || !hasAsyncProbe) {
    throw new AssertionError(
        "Missing expected JMX AOP operations"
    );
}
\`\`\`

Inspecting metadata is a step with no direct business side effect, whereas \`invoke\` can run code. Distinguish these two kinds of checks, especially in environments with side effects.

## 8. Testing that a transaction is genuinely active via JMX

Suppose the integration test has created a Spring context with the JMX exporter, \`TransactionalJobService\`, and an appropriate transaction manager. Perform:

\`\`\`java
Object value = server.invoke(
    name,
    "probeTransaction",
    new Object[0],
    new String[0]
);

if (!Boolean.TRUE.equals(value)) {
    throw new AssertionError(
        "Transaction advice was not applied"
    );
}
\`\`\`

Key points:

1. **Do not assert only that \`@Transactional\` is on the method.** Prove a transaction is active inside the body.
2. **Ensure the service is a Spring-managed proxy.** If you do \`new TransactionalJobService()\`, the annotation is not processed by Spring AOP.
3. **The test method itself should not open a transaction in a way that masks failures.** If a JUnit test has \`@Transactional\`, a local same-thread call can inherit the existing transaction, making the probe return true even when the service's transaction advice is broken.
4. **Verify the right transaction manager.** A transaction being active according to Spring does not mean actual database operations commit/roll back properly if misconfigured.
5. **Verify the path through JMX.** Calling the service directly in a test does not prove the MBean exporter dispatches through the proxy as expected.

### 8.1. Avoiding false positives from transactional tests

Misleading example:

\`\`\`java
@Transactional
@Test
void jmxOperationUsesTransaction() {
    boolean active = (Boolean) server.invoke(
        name,
        "probeTransaction",
        new Object[0],
        new String[0]
    );
    assertTrue(active);
}
\`\`\`

The test above may return true because of **the transaction opened by the test framework**, not because \`TransactionalJobService\` was advised. A better approach is testing without \`@Transactional\` on the test method, letting the service open its own transaction via its proxy when invoked.

If you need to test rollback, use a real repository/database in the test with a controlled rollback scenario, then read the data after the transaction to confirm. Checking \`isActualTransactionActive()\` alone is a minimum step, not a substitute for testing transaction semantics.

## 9. Testing that async actually switches threads via JMX

Suppose the test runs on thread:

\`\`\`text
Test thread: main
\`\`\`

Inside \`AsyncJobService.runAsyncStep()\`, return the name of the thread that ran the body. The JMX operation invokes:

\`\`\`java
Object value = server.invoke(
    name,
    "probeAsyncThread",
    new Object[0],
    new String[0]
);

String workerThread = (String) value;

if (!workerThread.startsWith("management-async-")) {
    throw new AssertionError(
        "Expected async executor thread, got: "
            + workerThread
    );
}
\`\`\`

This provides stronger evidence than merely seeing a method return \`CompletableFuture\`.

However, understand that:

- \`probeAsyncThread()\` in the adapter can still run synchronously on the caller thread and then **block waiting** on the async service.
- \`@Async\` takes effect on the service method if calls go through the async proxy and the right executor.
- If the executor is \`SyncTaskExecutor\`, some async calls may execute immediately on the caller thread per executor policy, so expecting a "different thread" must align with the chosen executor.
- Reading thread names is an illustrative test technique; in production you need more stable observability such as IDs/counters/status.
- An operation returning \`Future\` directly via JMX may have compatibility issues with JMX open types/clients. For management APIs, it is usually better to return a task ID and read status via a separate attribute/operation.

## 10. Production pattern: request/status instead of waiting on async

A JMX operation should have a clear contract between **accepting a request** and **completing the task**.

Example:

\`\`\`java
public interface ReindexAdminMBean {
    String requestReindex();
    String getRequestStatus(String requestId);
}
\`\`\`

The implementation can:

1. Check permissions and system state.
2. Generate a unique request ID and limit concurrent tasks.
3. Submit work to a monitored executor/queue.
4. Return the request ID immediately to the JMX client.
5. Provide statuses \`QUEUED\`, \`RUNNING\`, \`SUCCEEDED\`, \`FAILED\`.
6. Store sanitized exceptions and start/end timestamps.
7. Allow querying status instead of retrying the task-creating operation.

\`\`\`text
JMX invoke requestReindex()
          |
          v
Return requestId
          |
          +----> async execution
                     |
                     v
               transactional service
                     |
                     v
               persistent state / result

JMX getRequestStatus(id) -> observed status
\`\`\`

This pattern avoids false timeouts from JConsole having to wait on a long task; you still must handle cases where the task has started yet the client disconnects before receiving the ID.

## 11. Proxy types: JDK dynamic proxy and CGLIB

Spring AOP can create:

- **JDK dynamic proxy:** interface-based proxy.
- **CGLIB subclass proxy:** proxy via subclassing the target class, when configuration allows.

These proxy types differ in which methods can be accessed on the proxy and how introspection sees annotations.

Service example:

\`\`\`java
public interface ImportOperations {
    boolean execute();
}

@Service
public class ImportOperationsImpl
        implements ImportOperations {

    @Override
    @Transactional
    public boolean execute() {
        return TransactionSynchronizationManager
            .isActualTransactionActive();
    }

    public void internalOnly() {
        // Not part of the JDK proxy interface.
    }
}
\`\`\`

When using a JDK proxy, a bean injected as \`ImportOperations\` typically provides \`execute()\`, without automatically allowing \`internalOnly()\` to be called through the interface proxy. With CGLIB, the class proxy may expose more public methods, yet that does not itself determine what the JMX exporter should publish.

### 11.1. Why might an operation be missing?

When the exporter or assembler introspects the **proxy class** instead of the **target class**, annotations or management interfaces may be detected differently. Check:

- Whether the actual bean is an AOP proxy.
- \`AopUtils.isAopProxy(bean)\` and \`AopUtils.getTargetClass(bean)\`.
- Whether the exporter selects the proxy object or target.
- Whether actual \`MBeanInfo\` contains the right operations.
- Whether the JMX operation is dispatched to the right advised proxy.

A way to reduce complexity: **extract the JMX management adapter into a separate bean without applying complex advice to the adapter; the adapter injects transactional/async service proxies**. That way JMX operations have a clear interface, while transactions/async live at the service boundary.

## 12. Self-invocation and @Async

Example:

\`\`\`java
@Service
public class BatchService {

    public void submit() {
        runAsync();
    }

    @Async
    public void runAsync() {
        // Intended async work.
    }
}
\`\`\`

When \`submit()\` and \`runAsync()\` are on the same object, \`this.runAsync()\` can bypass the Spring proxy, making \`runAsync()\` run synchronously.

To fix by design:

\`\`\`java
@Service
public class BatchSubmissionService {

    private final BatchWorker batchWorker;

    public BatchSubmissionService(BatchWorker batchWorker) {
        this.batchWorker = batchWorker;
    }

    public void submit() {
        batchWorker.runAsync();
    }
}

@Service
public class BatchWorker {

    @Async
    public void runAsync() {
        // Executed through Spring async proxy.
    }
}
\`\`\`

The path through another bean is clearer and easier to test.

**Do not use \`AopContext.currentProxy()\` arbitrarily to "fix" self-invocation**; it depends on expose-proxy configuration and increases coupling to Spring AOP.

## 13. Combining @Transactional and @Async: which thread owns the transaction?

Traditional Spring transactions are typically bound to the current **thread**. When an \`@Async\` method executes on another thread, it does not automatically carry the caller's transaction context.

\`\`\`text
Thread A (JMX caller)
    |
    | MBean invoke
    v
Management adapter
    |
    +--> @Async service proxy
               |
               v
         Thread B (executor)
               |
               +--> @Transactional method/proxy
                         |
                         v
                    Transaction active
                    in Thread B
\`\`\`

If a \`@Transactional\` method sits on a service called **from inside an async worker thread through a Spring proxy**, the worker's transaction can start on thread B.

Conversely, a transaction opened on thread A **is not automatically propagated** to B. Therefore, tests must verify the transaction in the **worker thread**, not just in the caller thread.

### 13.1. Example separating async and transaction into two beans

\`\`\`java
@Service
public class AsyncCoordinator {

    private final TransactionalWorker worker;

    public AsyncCoordinator(TransactionalWorker worker) {
        this.worker = worker;
    }

    @Async("managementTaskExecutor")
    public CompletableFuture<Boolean> run() {
        boolean inTx = worker.executeInTransaction();
        return CompletableFuture.completedFuture(inTx);
    }
}

@Service
public class TransactionalWorker {

    @Transactional
    public boolean executeInTransaction() {
        return TransactionSynchronizationManager
            .isActualTransactionActive();
    }
}
\`\`\`

The JMX adapter calls \`asyncCoordinator.run()\` through the injected Spring proxy and waits for the result in the test. Returning \`true\` helps confirm a transaction is active on the worker execution path; add database assertions if the goal is verifying commit/rollback.

## 14. Testing that both async and transaction occur in the same workflow

Define a result DTO dedicated to internal testing:

\`\`\`java
public record ExecutionProbeResult(
    String callerThread,
    String workerThread,
    boolean transactionActive
) {}
\`\`\`

With JMX APIs, do not return arbitrary DTOs from a normal MBean if clients lack the corresponding class. One option is \`CompositeData\`, MXBean/OpenType, or **serializing the DTO to a String** in a test-only operation.

Example of what a lab JMX operation might return:

\`\`\`text
callerThread=main;
workerThread=management-async-1;
transactionActive=true
\`\`\`

However, test code should parse structured data rather than doing arbitrary substring checks. If testing the service layer directly, a plain Java DTO may be more suitable.

Crucially, do not check only:

\`\`\`java
assertTrue(future.isDone());
\`\`\`

because an already-completed \`Future\` can still be created by synchronous code. You must verify **thread execution** and **transaction activity** at the right points.

## 15. MBeanServer.invoke is synchronous at the JMX layer

A point of confusion: even if the underlying logic uses \`@Async\`, the call itself:

\`\`\`java
server.invoke(name, "run", new Object[0], new String[0]);
\`\`\`

remains a synchronous JMX call until the MBean operation returns a result/exception. If the operation only submits a task to an async executor and returns quickly, the JMX invoke returns quickly. If the operation calls \`future.get()\`, the JMX invoke still blocks waiting.

This affects:

- JConsole/client timeouts.
- Threads serving JMX requests and risk of resource exhaustion.
- Retries after errors when it is uncertain whether the task ran.
- How results and status are displayed.
- Application shutdown behavior while tasks are still running.

Therefore, operations with side effects should provide a clear boundary between "request accepted" and "business work completed".

## 16. Exception handling when invoking operations via JMX

When an operation is invoked, JMX can wrap exceptions in these types:

- \`MBeanException\`: checked exception from the managed resource or corresponding wrapper.
- \`RuntimeMBeanException\`: runtime exception from the MBean.
- \`ReflectionException\`: error locating/invoking the method or signature.
- \`InstanceNotFoundException\`: \`ObjectName\` is not registered or was unregistered.
- \`RuntimeErrorException\`: serious \`Error\` from the MBean.
- \`SecurityException\`: permission error.

Example:

\`\`\`java
import javax.management.MBeanException;
import javax.management.RuntimeMBeanException;

try {
    Object value = server.invoke(
        name,
        "probeTransaction",
        new Object[0],
        new String[0]
    );
    System.out.println(value);

} catch (MBeanException ex) {
    Exception target = ex.getTargetException();
    System.err.println("Managed operation failed: " + target);

} catch (RuntimeMBeanException ex) {
    RuntimeException target = ex.getTargetException();
    System.err.println("Managed runtime error: " + target);
}
\`\`\`

If an exception occurs on the async thread **after** the JMX operation has already returned, the JMX client does not necessarily receive that exception directly. You need task status, logs/auditing, or the \`Future\` result actually awaited by a caller.

### 16.1. Transaction errors

Transaction manager, datasource, or rollback errors can appear in the cause chain. With proxies, these errors may be further wrapped by Spring transaction/AOP/JMX layers.

Do not write tests that compare only a fixed exception message string; assert the error type and data state after rollback.

### 16.2. Async errors

If an \`@Async\` method returns \`CompletableFuture\`, exceptions can surface through the future upon \`join()\` or \`get()\`. If an \`@Async\` method returns \`void\`, errors occurring after task submission can be routed to an \`AsyncUncaughtExceptionHandler\` if configured.

Do not assume that a successful JMX invoke return means the async task succeeded.

## 17. Testing real rollback with a database

A "transaction active" check is necessary but not sufficient. To verify transaction semantics:

1. Use an embedded/test database such as H2 or Testcontainers per project requirements.
2. Have the \`@Transactional\` service insert a new row into a test table.
3. In the same method, intentionally throw a runtime exception after writing.
4. Invoke the workflow via the JMX operation.
5. After catching the exception, query the database using an independent transaction/connection.
6. Verify the row does not exist (rolled back).
7. Compare against a control path if needed.

Conceptual example:

\`\`\`java
@Transactional
public void writeThenFail(long taskId) {
    repository.insert(taskId);
    throw new IllegalStateException("rollback probe");
}
\`\`\`

The JMX adapter calls this service through the proxy. Without transaction advice, the insert may commit immediately depending on datasource/autocommit; the test will detect that the row was not rolled back.

**Important:** if the JUnit test method also has \`@Transactional\`, the test may roll back data under the outer transaction, producing a false positive. Test rollback in a test not masked by a test-framework transaction, and verify using an independent connection.

## 18. Testing concurrency and propagation

Transaction behavior can depend on \`propagation\`:

- \`REQUIRED\`: joins an existing transaction or creates a new one.
- \`REQUIRES_NEW\`: suspends the current transaction (if any) and creates a separate transaction when proxy/advice applies.
- \`SUPPORTS\`: uses a transaction if one exists; does not necessarily create a new one.
- \`NOT_SUPPORTED\`: executes non-transactionally per configured semantics.
- \`MANDATORY\`: requires an existing transaction.

When testing JMX, if caller transactions are uncontrolled, \`SUPPORTS\` can produce different results between a transactional test and a JConsole invocation that has no prior transaction.

With \`@Async\`, verify transactions on the worker thread according to the proper propagation and transaction manager. A test using only \`TransactionSynchronizationManager.isActualTransactionActive()\` does not describe full isolation/commit behavior; add database assertions if needed.

### 18.1. ThreadLocal and security context

AOP transactions often rely on thread-bound resources; async thread switching changes the context. \`ThreadLocal\` values such as transaction context, request context, logging MDC, and security context are not automatically propagated intact to the executor.

If a JMX operation depends on an HTTP request's \`RequestContextHolder\`, it may fail because a JMX call is not an HTTP request. If the application needs to pass a security principal or correlation context to async tasks, configure a safe, tested propagation mechanism; do not copy entire contexts containing sensitive data unconditionally.

## 19. Separating the JMX adapter from AOP services: a testable design

A maintainable structure:

\`\`\`text
MBeanServer
    |
    v
@ManagedResource ManagementAdapter
    |
    +--> Read-only attributes
    |
    +--> Controlled operations
              |
              v
       Business service interface
              |
              v
       Spring AOP proxy
          /       \
         /         \
 Transaction      Async
    advice        advice
         \         /
          \       /
           v     v
        Target service
\`\`\`

Benefits:

- The management interface is minimally published.
- Transaction logic stays in the appropriate service, avoiding DB logic inside JMX getters.
- Async execution is coordinated by an executor with a clear name and lifecycle.
- Tests can mock the service at the unit-test level, then use a real proxy/DB in integration tests.
- Changes to the Spring AOP target class minimally impact the adapter's JMX metadata.
- You do not have to expose all service methods to JMX clients.

The JMX adapter should avoid methods allowing arbitrary SQL execution, shell commands, file path changes, or unchecked modification of critical data; if necessary administrative operations exist, they must have authorization, validation, and auditing.

## 20. End-to-end Spring Boot integration test

An illustrative test with \`@SpringBootTest\`:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(
    properties = {
        "spring.jmx.enabled=true"
    }
)
class JmxAopIntegrationTest {

    @Test
    void jmxOperationRunsTransactionalService() throws Exception {
        MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();

        ObjectName name = new ObjectName(
            "com.example.jobs:type=Probe,name=Aop"
        );

        assertTrue(server.isRegistered(name));

        Object result = server.invoke(
            name,
            "probeTransaction",
            new Object[0],
            new String[0]
        );

        assertEquals(Boolean.TRUE, result);
    }

    @Test
    void jmxOperationCallsAsyncExecutor() throws Exception {
        MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();

        ObjectName name = new ObjectName(
            "com.example.jobs:type=Probe,name=Aop"
        );

        Object result = server.invoke(
            name,
            "probeAsyncThread",
            new Object[0],
            new String[0]
        );

        String thread = (String) result;
        assertTrue(thread.startsWith("management-async-"));
    }
}
\`\`\`

The test requires the project to have \`JmxAopProbe\`, \`TransactionalJobService\`, \`AsyncJobService\`, a transaction manager, and an executor configured as in earlier sections. With Spring Boot, depending on version, JMX auto-configuration may require a property to enable as shown.

**Do not run multiple contexts in parallel using the same \`ObjectName\`** in the platform \`MBeanServer\` without an isolation strategy; this can cause \`InstanceAlreadyExistsException\`.

## 21. Common errors and resolutions

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| \`@Transactional\` not active | Self-invocation, object is not a proxy, missing transaction manager, or wrong advice config. | Split service, inject Spring bean, verify transaction manager. |
| \`@Async\` runs on caller thread | Self-invocation, missing \`@EnableAsync\`, synchronous executor, or proxy not applied. | Check call path through proxy and executor. |
| JMX operation does not appear | Bean not exported, wrong assembler, proxy metadata differs from target. | \`getMBeanInfo\`, \`ObjectName\`, exporter. |
| JMX invoke throws \`ReflectionException\` | Wrong operation/signature, method not published. | Inspect runtime signatures. |
| \`InstanceNotFoundException\` | MBean not registered or already unregistered. | Check lifecycle and the right \`MBeanServer\`. |
| Transaction test passes yet prod fails | Test method had its own transaction, failing to reproduce actual JMX call path. | Remove \`@Transactional\` from test, use DB assertions. |
| JMX invoke succeeds yet async task fails | Task completed after method returned, exception not propagated to client. | Use request/status and inspect future/logs. |
| Async task keeps running after shutdown | Executor lifecycle not properly managed. | Configure graceful shutdown, cancellation, status. |
| Duplicate MBean registration | Boot exporter and custom exporter or test contexts sharing server. | Single owner per \`ObjectName\`, proper cleanup. |
| Operation blocks long in JConsole | \`future.get\` or long DB transaction inside operation. | Design async request/observe, appropriate timeouts. |
| \`SecurityContext\` missing on worker | Context does not propagate automatically across threads. | Use intentional propagation strategy, do not copy secrets. |

## 22. Layer-by-layer testing workflow

To diagnose a JMX + AOP issue, proceed in order:

\`\`\`text
1. Does the Spring bean exist?
          |
          v
2. Is the bean proxied?
          |
          v
3. Did the exporter register the MBean with the right ObjectName?
          |
          v
4. Does MBeanInfo have the right operation/signature?
          |
          v
5. Can MBeanServer.invoke call it?
          |
          v
6. Does transaction/async advice actually activate?
          |
          v
7. Are business state / DB / Future results correct?
          |
          v
8. Are exceptions, auditing, and cleanup handled?
\`\`\`

Each layer has its own inspection tools. When an operation is missing from \`MBeanInfo\`, inspect the exporter/assembler first; when the operation exists yet no transaction is active, inspect the proxy/self-invocation/transaction manager; when async runs on the wrong thread, inspect the executor and the call through the proxy.

## 23. Contract and security testing

In environments with real data, you should:

1. **Export only necessary management operations.** Do not expose an entire business service via reflection.
2. **Read \`MBeanInfo\` before invoking.** This is inspection without executing operations.
3. **Limit side effects.** Test mutations using an isolated database/test environment.
4. **Authenticate and authorize.** Remote JMX must have TLS, authentication, and appropriate permissions.
5. **Do not retry blindly.** A timeout may happen after the operation has already started.
6. **Use structured logging.** Log \`ObjectName\`, operation, error type—never log secrets.
7. **Observe async tasks.** Do not infer success merely from request acceptance.
8. **Verify rollback and final state.** Read results via an independent path when testing transactions.
9. **Clean up MBeans after tests.** Close \`ApplicationContext\` to avoid registry leaks.
10. **Do not experiment with destructive operations in production.**

A security test can assert that internal operations like \`deleteAllRecords\` do not appear in \`MBeanInfo.getOperations()\`. With \`DynamicMBean\`, also ensure \`invoke\` code rejects unauthorized names even if not published in metadata.

## 24. Practice exercises

### Exercise 1 — Verifying transactions via JMX

Create \`TransactionalJobService\` and \`JmxAopProbe\`. Connect to the local \`MBeanServer\`, call \`probeTransaction()\`, and verify it returns \`true\` when the transaction manager is properly configured.

**Objective:** prove JMX invocation passes through the transaction proxy.

### Exercise 2 — Self-invocation

Place \`@Transactional\` on an internal method called via \`this\` from another method in the same class. Compare results with a design using a separate service bean.

**Objective:** recognize why advice is bypassed.

### Exercise 3 — Async executor

Configure \`managementTaskExecutor\` with a distinct thread prefix. Call \`probeAsyncThread()\` and assert the thread name belongs to the executor.

**Objective:** prove the method body actually switches threads.

### Exercise 4 — Transaction inside an async thread

Create \`AsyncCoordinator\` calling \`TransactionalWorker\`. Return a result containing the thread name and transaction active state, and verify both in the test.

**Objective:** avoid confusing caller transactions with worker transactions.

### Exercise 5 — Database rollback

Create a test table, write inside a transaction, and then throw a runtime exception. Invoke the workflow via JMX, then use an independent connection to verify the row does not exist.

**Objective:** test real transaction behavior, not just annotations.

### Exercise 6 — Proxies and MBeanInfo

Try both JDK proxy and class proxy in a test environment. Compare \`MBeanInfo\` and the operation list; verify no internal methods are exposed.

**Objective:** understand proxy impact on JMX metadata.

### Exercise 7 — Async failure after JMX returns

Create an async task that throws an exception after a delay. Have the JMX operation return only a request ID. Poll status to observe the failure.

**Objective:** understand that asynchronous errors do not automatically become JMX invoke errors.

## 25. Review questions

**1. Why is having \`@Transactional\` on a method not enough?** Because transaction advice must be configured and calls must pass through the appropriate Spring proxy.

**2. How does self-invocation affect JMX?** JMX may call an outer method, yet that method calls a transactional/async method on the same object, bypassing advice.

**3. Does \`MBeanServer.invoke\` automatically start a transaction?** No. It dispatches the JMX operation; transactions are applied by Spring advice/the transaction manager if the call path matches.

**4. Does \`@Async\` guarantee \`MBeanServer.invoke\` always returns immediately?** No. The JMX operation may block waiting on a \`Future\` or run synchronous logic before returning.

**5. How do you know \`@Async\` actually ran on a worker thread?** Capture the executing thread inside the method body and compare it against the configured executor.

**6. Does a transaction opened on the caller thread automatically propagate to an async thread?** No; Spring transactions are normally thread-bound, so the worker needs its own transaction along a separate advice path.

**7. Why can a \`@Transactional\` test method cause a false positive?** Because the transaction opened by the test framework can make the probe return true even when the service advice is not working.

**8. Why should you avoid returning \`Future\` directly from a JMX operation?** Type compatibility/serialization/open types may not suit clients; request ID/status is usually easier to manage.

**9. If JMX invoke returns successfully, has the async task definitely succeeded?** No. The task may fail after the operation returns.

**10. How do you inspect the JMX contract?** Use \`MBeanServer.getMBeanInfo\` to inspect operations/signatures, attributes, and APIs that must not be exported.

## 26. Summary

Testing **JMX with Spring AOP, transactions, and async** requires checking both **the JMX dispatch path** and **the proxy/advice path**. Annotations in source code do not prove runtime behavior. A solid test reads \`MBeanInfo\`, invokes operations via \`MBeanServer\` in an isolated environment, confirms active transactions in the right method, and verifies async runs on the expected executor.

When combining transactions and async, remember transactions are normally thread-bound; async does not automatically inherit the caller's transaction. For production, keep JMX adapters small, call transactional/async services through Spring proxies, design request/status operations when needed, control permissions, and test commit/rollback, exceptions, and lifecycle cleanup.

## References

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework Reference — Proxying Mechanisms: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Framework Reference — Transaction Declarative Annotations: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework Reference — Task Execution and Scheduling: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
- Spring Framework Javadoc — \`EnableAsync\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/annotation/EnableAsync.html
- Spring Framework Javadoc — \`EnableTransactionManagement\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/annotation/EnableTransactionManagement.html
- Java SE 21 — \`MBeanServer\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html