# Connector Connects Successfully, Yet Proxy Calls Fail in Spring JMX

## 1. Symptom: Successful JMX Connection Does Not Prove the MBean Proxy Works

In Spring Framework JMX, a client may create a `JMXConnector`, obtain an `MBeanServerConnection`, and even list MBeans from the target JVM, yet calls on an `MBeanProxyFactoryBean` still fail.

Example:

```java
JMXConnector connector = JMXConnectorFactory.connect(serviceUrl, env);
MBeanServerConnection connection = connector.getMBeanServerConnection();

System.out.println(connection.getDefaultDomain()); // Succeeds

WorkerManagement proxy = context.getBean(
    "workerManagementProxy", WorkerManagement.class
);

proxy.getActiveWorkers(); // Fails
```

This scenario is confusing because the same target application and network path already accepted the connection. However, **connector readiness** and **MBean invocation readiness** are two different verification levels:

```text
JMX connector established
         |
         v
MBeanServerConnection available
         |
         +--> queryNames(...) succeeds
         |
         v
ObjectName found?
         |
         v
Does MBeanInfo have the right attribute / operation?
         |
         v
Does proxy interface map metadata properly?
         |
         v
Are authorization, input, and runtime state valid?
         |
         v
MBean target executes successfully
```

A failure at any layer after connect can cause proxy calls to fail while the connector stays alive. Therefore, do not tweak networking or rotate credentials blindly once the connector works; pinpoint **the first specific failing step**.

## 2. Distinguishing Connection, Registration, and Execution Layers

| Layer | Check | What It Confirms | What It Does Not Confirm |
|---|---|---|---|
| Remote transport | `JMXConnectorFactory.connect(...)` | Connector can be created | Target MBean exists |
| JMX session | `getMBeanServerConnection()` | Connection API is available | Permission to invoke every operation |
| Server metadata | `getDefaultDomain()` / `queryNames()` | Server answers JMX requests | Proxy interface compatibility |
| Registration | `isRegistered(objectName)` | ObjectName exists at check time | MBean satisfies expected methods |
| Contract | `getMBeanInfo(objectName)` | Attributes/operations are published | Business logic will succeed |
| Invocation | `getAttribute`, `setAttribute`, `invoke` | Raw JMX call actually executes | Spring proxy is always compatible |
| Spring proxy | Calling interface method | End-to-end adapter + JMX | Remote stability going forward |

**A proxy error is not synonymous with a connection error.** An MBeanServer may serve `queryNames` to a caller while denying a sensitive operation; an MBean may return valid metadata yet throw an exception in a getter when a dependency is not ready.

## 3. Components to Identify Before Debugging

A Spring application using a remote JMX proxy typically involves:

- **`JMXServiceURL`**: address of the target connector, e.g., RMI/JMX.
- **`JMXConnector`**: client session to the server.
- **`MBeanServerConnection`**: client interface for JMX operations.
- **`ObjectName`**: exact address of the MBean in the registry.
- **`MBeanInfo`**: active attribute/operation/notification metadata.
- **`MBeanProxyFactoryBean`**: Spring `FactoryBean` producing a typed proxy.
- **`MBeanClientInterceptor`**: class translating proxy method calls into JMX requests.
- **Management interface**: Java contract implemented by the proxy.
- **`MBeanExporter`** on the server side, if the MBean is exported by Spring.

Diagram:

```text
Spring client context
   |
   +-- MBeanProxyFactoryBean
          |
          +-- proxyInterface = WorkerManagement
          +-- objectName     = company.workers:type=Pool,name=primary
          +-- server         = MBeanServerConnection
          |
          v
      MBeanClientInterceptor
          |
          v
      JMXConnector / transport
          |
Remote MBeanServer
          |
          +-- ObjectName
          +-- MBeanInfo
          +-- target MBean
```

When debugging, record the URL, ObjectName, Java interface name, client/server app versions, and Spring version. Avoid logging credentials, tokens, raw requests, or sensitive exception payloads.

## 4. First Step: Keep the Connection, Test the Raw JMX API

Before modifying `MBeanProxyFactoryBean`, take the exact `MBeanServerConnection` used by the proxy and run small checks.

```java
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;

ObjectName name = new ObjectName(
    "company.workers:type=Pool,name=primary"
);

System.out.println("Registered: " + connection.isRegistered(name));
System.out.println("Domain: " + connection.getDefaultDomain());
```

If `isRegistered(name)` returns `false`, the connection succeeded, yet **no MBean exists at that ObjectName**. Proceed to step 5. If `true`, proceed to inspect `MBeanInfo` in step 6.

A scoped listing approach:

```java
for (ObjectName candidate : connection.queryNames(
        new ObjectName("company.workers:*"), null)) {
    System.out.println(candidate.getCanonicalName());
}
```

Do not print every MBean and all attribute values in production. Query only the application's domain to avoid exposing operational information beyond what is needed.

### Why must you use the **exact same** connection?

If you test the raw API using `ManagementFactory.getPlatformMBeanServer()` on the **client JVM**, you are querying the client's local server, not the remote server. That result proves nothing about the endpoint the proxy calls.

Similarly, if the client has multiple connection beans, one connection may point to JVM A while the proxy uses JVM B. Verify the actual identity and connection configuration.

## 5. Case 1: ObjectName Does Not Exist or Is Incorrect

This is a common cause:

```text
Proxy objectName:
  company.workers:type=Pool,name=primary

Server registration:
  company.worker:type=Pool,name=primary
```

The two names differ by a single letter, making them two different ObjectNames. `JMXConnector` still works; `getAttribute` on the wrong name can throw `InstanceNotFoundException` or the corresponding Spring wrapper.

### 5.1. Diagnosis

```java
Set<ObjectName> names = connection.queryNames(
    new ObjectName("company.*:*"), null
);

names.forEach(System.out::println);
```

This snippet requires importing `java.util.Set`. In large production domains, use a narrower query pattern to avoid excessively long output.

Check:

1. Is the domain exact?
2. Are key properties `type`, `name`, `instance` accurate?
3. Was the ObjectName altered by a naming strategy or Spring Boot auto-configuration?
4. Did the server actually register the target, or does the bean merely exist in `ApplicationContext`?
5. Was the target unregistered/re-registered after the proxy initialized?

ObjectName is a **registry address**, not a Spring bean name. A bean named `workerManagement` in the context does not mean the JMX ObjectName is `workerManagement`.

### 5.2. An ObjectName pattern does not replace a concrete target name

A pattern:

```text
company.workers:type=Pool,*
```

is useful for `queryNames`, yet a typed proxy usually needs an ObjectName locating **one specific MBean**. Do not supply a pattern and expect the proxy to pick an arbitrary instance. If multiple MBeans match, select the exact target using explicit criteria.

### 5.3. Even a valid ObjectName can change at runtime

`isRegistered(name)` is a point-in-time check. Between the check and the proxy call, the MBean may be unregistered or replaced. Therefore, handle `InstanceNotFoundException` on the call path rather than treating a one-time `true` check as a permanent guarantee.

## 6. Case 2: MBeanInfo Does Not Match the Proxy Interface

This is another foundational cause. A Spring proxy translates Java method calls into JMX calls based on the management interface. However, the server only supports attributes and operations present in its metadata.

Suppose the client uses:

```java
public interface WorkerManagement {
    int getActiveWorkers();
    void pause();
    void setConcurrency(int value);
}
```

Yet the server exports:

```text
Attributes:
  ActiveWorkerCount (int, read-only)
  ConcurrencyLimit (int, read-write)

Operations:
  pauseProcessing()
```

`proxy.getActiveWorkers()`, `proxy.pause()`, and `proxy.setConcurrency(4)` may fail because **method/attribute names differ**, even though both sides refer to the worker pool.

### 6.1. Reading the actual metadata

```java
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;

MBeanInfo info = connection.getMBeanInfo(name);

for (MBeanAttributeInfo attr : info.getAttributes()) {
    System.out.printf(
        "ATTR %s type=%s readable=%s writable=%s%n",
        attr.getName(),
        attr.getType(),
        attr.isReadable(),
        attr.isWritable()
    );
}

for (MBeanOperationInfo op : info.getOperations()) {
    System.out.println("OP " + op.getName());
    for (var parameter : op.getSignature()) {
        System.out.println(
            "  PARAM " + parameter.getType()
        );
    }
}
```

`MBeanInfo` is the authoritative source for the contract offered by the server, rather than guessing from an interface in client source code or an old README.

### 6.2. JavaBean getters and JMX attributes

Typically:

```java
int getActiveWorkers();
```

maps to JMX attribute `ActiveWorkers`. If the server only has attribute `ActiveWorkerCount`, the proxy will not translate the name automatically.

Similarly:

```java
void setWarningThreshold(int value);
```

typically maps to writable attribute `WarningThreshold`. If the server only exposes a read-only attribute, the setter call will be rejected.

Do not call `getSomething()` as an arbitrary operation when the server exported it as an attribute. JMX distinguishes `getAttribute` from `invoke`; Spring's adapter relies on metadata to choose the action.

## 7. Case 3: Operation Signature or Parameter Type Mismatch

JMX operations are identified by name and parameter type signature.

Server:

```java
public void resizePool(int newSize);
```

Client proxy:

```java
void resizePool(long newSize);
```

Although the name matches, `int` differs from `long`. If the call translates into `invoke` with signature `long`, the server may not find a matching operation.

Raw call example:

```java
connection.invoke(
    name,
    "resizePool",
    new Object[]{8},
    new String[]{"int"}
);
```

In JMX, primitive signatures typically use names like `"int"`, while object types use fully qualified names such as `"java.lang.String"`. Read the signature from `MBeanOperationInfo.getSignature()` and keep client/server compatible.

Do not assume the server automatically coerces `String` to `int`, or `Integer` to `Long`, for every ModelMBean. Both contract and value conversion must align.

### 7.1. Overloads and interface drift

If the management interface has:

```java
void reset(String scope);
void reset(int scopeId);
```

the proxy must pick the exact signature. When a team changes an overload on the server while the client still holds an older interface version, the code compiles yet JMX at runtime may report the operation does not exist.

Prevention involves sharing a versioned management interface between client/server or checking compatibility against metadata in integration tests.

## 8. Case 4: MBean Is Readable, Yet Operations Are Denied by Permissions

Not all connections hold identical privileges. A client might:

- Connect successfully.
- List MBean names.
- Read metadata.
- Read certain attributes.
- Yet be denied when invoking an operation or writing an attribute.

For example, a monitoring account configured as read-only while the proxy has:

```java
void pause();
```

Calling `pause()` may fail due to authorization or security policy. That can be **correct security behavior**, not a proxy bug.

Distinguish:

| Check | If It Succeeds | If It Fails |
|---|---|---|
| `queryNames` | Client can query names per policy | May lack metadata permissions |
| `getMBeanInfo` | Metadata is readable | May be restricted |
| `getAttribute` | Permitted to read specific attribute | Could be permissions or attribute issue |
| `setAttribute` | Permitted to write and input valid | Could be permissions or validation |
| `invoke` | Operation permitted and target ran | Could be permissions, contract, or runtime |

Do not fix this by granting broad privileges to all JMX clients. If an operation requires higher privilege, provision a dedicated management identity or separate a controlled management interface.

## 9. Case 5: Is the Proxy Target a Standard MBean, MXBean, or Spring ModelMBean?

There are multiple export mechanisms in JMX:

- **Standard MBean**: class implements an interface following the `SomethingMBean` convention or uses an appropriate wrapper.
- **MXBean**: `SomethingMXBean` interface, `@MXBean`, or wrapper with OpenType mapping rules.
- **Dynamic MBean**: self-describes metadata and handles access/invoke directly.
- **Spring ModelMBean**: Spring exporter + assembler generates metadata from annotations/interfaces/method names.

A proxy using a Standard MBean interface does not automatically fit an MXBean DTO. MXBeans may return `CompositeData` or `TabularData` over the raw API, whereas a typed MXBean proxy maps them back to the corresponding Java types.

JDK example:

```java
MyStatusMXBean proxy = JMX.newMXBeanProxy(
    connection,
    name,
    MyStatusMXBean.class
);
```

Here `MyStatusMXBean` must be a genuine MXBean interface and the target must be registered with MXBean semantics. If using `JMX.newMBeanProxy` for an MXBean with complex DTOs, type conversion may not work as expected.

With Spring's `MBeanProxyFactoryBean`, verify your specific Spring version's support for proxying MXBeans/ModelMBeans and choose the corresponding interface. Do not treat successful proxy creation as proof that every return type can be converted.

## 10. Case 6: Server Object Is Not Yet READY

An MBean may be registered as soon as the Spring `ApplicationContext` refreshes while background initialization is still incomplete. For example:

```text
JMX connector: READY
MBean registered: YES
Worker service: STARTING
Dependency database: NOT READY
```

`getActiveWorkers()` may work if it simply reads a local counter. However, `reloadConfiguration()` may fail because the database/config server is not ready yet.

This is a **target runtime failure**, not a network failure. Inspect server-side stack traces/causes, lifecycle state, and which dependency the getter/operation calls.

Good MBean design should:

- Export states such as `STARTING`, `READY`, `DEGRADED`.
- Allow simple getters to work even before the service is READY.
- Guard state-mutating operations when dependencies are unready.
- Avoid heavy network calls inside getters.
- Return clear error codes/exceptions without leaking secrets.

Do not treat successful JMX registration as proof the service is healthy.

## 11. Case 7: Logic Error Inside the MBean

A proxy call may reach the exact MBean and method, yet the method throws an exception:

```java
@ManagedOperation
public void refreshCache() {
    if (!cacheBackend.isAvailable()) {
        throw new IllegalStateException("Cache backend unavailable");
    }
    cacheBackend.refresh();
}
```

JMX may wrap the exception in `MBeanException`, `RuntimeMBeanException`, or a Spring JMX access wrapper. Thus, the client's stack trace may start at the proxy/interceptor while the root cause lies inside the target.

When diagnosing:

1. Find the exception root cause in `getCause()` and matching server logs.
2. Determine whether the operation already started executing.
3. Inspect input values and dependency state.
4. Avoid logging raw payloads or credentials in exception messages.
5. Do not retry side-effecting operations just because the client received an unclear exception.

An exception thrown after partial execution can still leave modified state behind.

## 12. Case 8: Connector Exists, Yet Session/Network Is Unstable

A connector that once connected successfully does not guarantee every subsequent call will succeed. The remote RMI endpoint may have restarted, a firewall may have dropped an idle connection, or the network may have glitched.

Scenarios:

```text
T0: connect() succeeds
T1: getMBeanInfo() succeeds
T2: remote JVM restarts
T3: proxy.getActiveWorkers() -> I/O error
```

In this case, inspect the network/session and reconnection strategy. This differs from **the MBean target throwing an exception** while the server remains healthy.

If a read-only call fails due to a connection drop, reconnecting and retrying under a bounded policy may be reasonable. For side-effecting operations, **a timeout does not prove the operation never ran**. The server may have executed it while the response was lost, so blind retries can repeat side effects.

`MBeanClientInterceptor` or connection factories in some Spring versions offer a refresh-connection-on-failure option, though it does not guarantee exactly-once delivery or recover from every failure mode. Check the policy of the Spring dependency version you use.

## 13. Case 9: Pointing to the Wrong JVM or MBeanServer

An application may have multiple JVMs:

```text
worker-a.example.internal
worker-b.example.internal
worker-c.example.internal
```

Or a single JVM may have multiple MBeanServers. The connector connects successfully, yet the service URL points to another node where the ObjectName exists with a different contract/version.

Indicators:

- Same ObjectName, yet different metadata.
- Attributes like `Version` or `InstanceId` (if present and non-sensitive) do not match the expected environment.
- Responses change after failover/load balancing.
- Local JConsole on server A sees the MBean, while remote client connects to server B.
- Client uses local `ManagementFactory.getPlatformMBeanServer()` to inspect while the proxy uses a remote connection.

The solution is to determine the actual endpoint from effective configuration, verify non-sensitive target identity, and read `MBeanInfo` over **the exact connection the proxy uses**.

Do not randomly edit `ObjectName` until a call succeeds, because you could accidentally invoke operations on a similarly named MBean belonging to another instance.

## 14. Case 10: Spring Proxy Created Before the Target Appears

`MBeanProxyFactoryBean` is a `FactoryBean` that creates a typed proxy for a target MBean. Creating a proxy does not register the MBean.

Ways this fails:

- The proxy initializes and attempts to fetch metadata before the MBean is registered.
- Proxy creation succeeds, yet the first call happens before the exporter registers the target.
- The target is unregistered while the context is STOPPING.
- The server restarted and registration was recreated later than the connector.
- Configured ObjectName or `MBeanServerConnection` differs from reality.

If proxy and target share a Spring context, organize dependencies/lifecycle to prevent premature calls. If the target lives in another JVM, use readiness checks and proper connection handling; do not place `@DependsOn` on the client and expect it to order startup of a remote server.

## 15. Debugging the Raw API Before Debugging the Spring Proxy

A repeatable sequence in a lab:

### Step 1 — Check registration

```java
if (!connection.isRegistered(name)) {
    throw new IllegalStateException(
        "MBean not registered: " + name
    );
}
```

### Step 2 — Check metadata

```java
MBeanInfo info = connection.getMBeanInfo(name);
System.out.println("Class: " + info.getClassName());
```

Do not assume `getClassName()` is always the exact Java business class, since Spring ModelMBeans may report a wrapper/adapter.

### Step 3 — Read a safe attribute

```java
Object active = connection.getAttribute(name, "ActiveWorkers");
System.out.println("ActiveWorkers=" + active);
```

Choose an attribute containing no sensitive data and performing no heavy queries.

### Step 4 — Invoke a test operation in a test environment

```java
connection.invoke(
    name,
    "ping",
    new Object[0],
    new String[0]
);
```

Call this only if `ping` **is actually exported and safe**. Never use operations like `reset`, `delete`, `restart`, or `rotateSecret` just to test connectivity.

### Step 5 — Call the proxy with the same contract

If raw access succeeds while the proxy fails, the issue likely lies in how the proxy interprets the interface, MBean type, getter/setter mapping, signature, or a config mismatch between raw connection and proxy.

If raw access fails as well, focus on ObjectName, permissions, metadata, and target runtime first.

## 16. End-to-End Example: Standard MBean and JMX Proxy

### 16.1. Shared Management Interface

```java
// WorkerManagementMBean.java
public interface WorkerManagementMBean {
    int getActiveWorkers();
    int getConcurrencyLimit();
    void setConcurrencyLimit(int limit);
    void pause();
}
```

### 16.2. Server-Side Implementation

```java
// WorkerManagement.java
public class WorkerManagement implements WorkerManagementMBean {
    private volatile int activeWorkers = 4;
    private volatile int concurrencyLimit = 8;
    private volatile boolean paused;

    @Override
    public int getActiveWorkers() {
        return activeWorkers;
    }

    @Override
    public int getConcurrencyLimit() {
        return concurrencyLimit;
    }

    @Override
    public void setConcurrencyLimit(int limit) {
        if (limit < 1 || limit > 64) {
            throw new IllegalArgumentException("limit must be 1..64");
        }
        concurrencyLimit = limit;
    }

    @Override
    public void pause() {
        paused = true;
    }
}
```

Because the class name `WorkerManagement` and interface `WorkerManagementMBean` match the convention, an instance can be registered as a Standard MBean.

Local registration on the server:

```java
MBeanServer server = ManagementFactory.getPlatformMBeanServer();
ObjectName name = new ObjectName(
    "company.workers:type=WorkerManagement,name=primary"
);
server.registerMBean(new WorkerManagement(), name);
```

The code above **does not automatically open a remote connector**. If the client is in another JVM, the server must configure a `JMXConnectorServer` and appropriate security.

### 16.3. Spring Client Configuration

```java
import javax.management.MBeanServerConnection;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.access.MBeanProxyFactoryBean;

@Configuration
public class WorkerProxyConfiguration {

    @Bean
    public MBeanProxyFactoryBean workerProxy(
            MBeanServerConnection connection) {

        MBeanProxyFactoryBean factory =
            new MBeanProxyFactoryBean();

        factory.setServer(connection);
        factory.setObjectName(
            "company.workers:type=WorkerManagement,name=primary"
        );
        factory.setProxyInterface(WorkerManagementMBean.class);
        return factory;
    }
}
```

`MBeanServerConnection` is provided by another connection factory or connection configuration bean, not the client's local `MBeanServer`. Ensure the client receives the right remote connection.

A caller:

```java
public class WorkerDashboard {
    private final WorkerManagementMBean management;

    public WorkerDashboard(WorkerManagementMBean management) {
        this.management = management;
    }

    public int readActiveWorkers() {
        return management.getActiveWorkers();
    }
}
```

If `readActiveWorkers()` fails, run the raw API steps on **the exact same connection** to distinguish a server/contract failure from a proxy failure.

## 17. Spring MBeanProxyFactoryBean and Interceptor

`MBeanProxyFactoryBean` creates a proxy for the specified interface. Underneath, `MBeanClientInterceptor` handles method invocations and decides whether to perform JMX attribute access or an operation invocation.

Example:

```text
proxy.getActiveWorkers()
  -> getAttribute(ObjectName, "ActiveWorkers")

proxy.setConcurrencyLimit(16)
  -> setAttribute(ObjectName, Attribute("ConcurrencyLimit", 16))

proxy.pause()
  -> invoke(ObjectName, "pause", [], [])
```

This is a generalized model. Exact behavior may depend on metadata, MBean type, and Spring version. A JavaBeans-named getter does not guarantee the target exported that attribute; inspect `MBeanInfo`.

### 17.1. When should you use MBeanClientInterceptor directly?

If you want a custom `ProxyFactory`, additional advice, or custom error handling, you can configure the interceptor at a lower level. When the goal is standard typed access, `MBeanProxyFactoryBean` is simpler.

Do not write a custom adapter that swallows every exception and returns `0` for metrics: `0` is a meaningful business value, distinct from an `UNKNOWN` status caused by connection failure. Monitoring clients should explicitly represent stale or unavailable data.

## 18. Exception Classification Table for Root-Cause Analysis

| Exception / Symptom | Common Cause | Next Step |
|---|---|---|
| `InstanceNotFoundException` | Wrong ObjectName or target not registered | `queryNames`, lifecycle |
| `AttributeNotFoundException` | Attribute does not exist / not readable | `MBeanInfo.getAttributes()` |
| `InvalidAttributeValueException` | Setter received an invalid value | Input types, validation |
| `ReflectionException` | Matching JMX method not found | Name, signature, overload |
| `MBeanException` | Target operation threw a JMX-wrapped exception | Root cause in server logs |
| `RuntimeMBeanException` | Runtime exception from MBean | Validation, target state |
| `SecurityException` | Insufficient permissions or policy denial | Authentication/authorization |
| `IOException` / timeout | Broken session, network, or connector | Server status, reconnect |
| `ClassCastException` / conversion error | Return type incompatible with client | Standard/MXBean mapping |
| Spring JMX access exception | Adapter/interceptor translated/wrapped JMX error | Inspect cause chain and metadata |

These are directional indicators, not strict one-to-one mappings. The same root cause can be wrapped in different exceptions across Spring/JMX versions.

## 19. Inspecting Effective Configuration of the Spring Client

Configuration in a file is not guaranteed to be what is running. In the `ApplicationContext`, determine:

- Which proxy bean is created by `MBeanProxyFactoryBean`.
- Whether the configured ObjectName matches the server deployment.
- Whether the connection bean comes from `MBeanServerConnectionFactoryBean` or another source.
- Whether the active service URL/credentials are overridden by a profile/environment.
- Whether multiple beans implement the management interface, causing injection to pick the wrong proxy.
- Whether the proxy is the object produced by the FactoryBean or the caller injected a local target.

With a `FactoryBean`, `context.getBean("workerProxy")` typically returns the **product proxy**, whereas `context.getBean("&workerProxy")` returns the FactoryBean itself. That distinction is very useful when debugging wiring.

If multiple beans share the management interface, use `@Qualifier` to specify the proxy bean:

```java
public WorkerDashboard(
    @Qualifier("workerProxy") WorkerManagementMBean management) {
    this.management = management;
}
```

Never log passwords, truststore contents, or credential environments during investigations.

## 20. Branching Troubleshooting Workflow

```text
Can connector connect?
    |
    +-- No -> network, URL, RMI, TLS, auth
    |
    +-- Yes
         |
         v
    isRegistered(ObjectName)?
         |
         +-- No -> naming, registration, right JVM?
         |
         +-- Yes
              |
              v
        Can getMBeanInfo?
              |
              +-- No -> permissions/registry/target
              |
              +-- Yes
                   |
                   v
         Metadata matches proxy interface?
                   |
                   +-- No -> fix interface/mapping/version
                   |
                   +-- Yes
                        |
                        v
              Raw JMX read/invoke works?
                        |
                        +-- No -> permissions, validation, runtime
                        |
                        +-- Yes
                             |
                             v
                    Proxy call fails?
                             |
                             +-- Yes -> Spring wiring,
                             |          interceptor, type mapping
                             |
                             +-- No -> monitor stability,
                                        lifecycle, reconnect
```

Run one small test per branch instead of changing URL, ObjectName, interface, and security simultaneously and losing track of which change made the difference.

## 21. Safe Investigation with Logs and Metadata

When an error occurs, record useful details:

```text
timestamp
client application/module/version
target logical environment
service URL host/port (without credentials)
ObjectName
proxy interface name
method being called
exception class and root cause
relevant MBeanInfo attribute/operation signatures
server lifecycle state if available
```

Avoid:

- Printing the entire `Environment`, system properties, or credentials.
- Dumping all JMX attributes, as some may hold secrets.
- Logging raw request bodies or user payloads.
- Invoking dangerous operations just to confirm connectivity.
- Widening permissions to full access without root-cause analysis.

If server logs are needed for comparison, use a non-sensitive correlation ID or operation timestamp. Keep clock skew between the two machines in mind when correlating timestamps.

## 22. Preventing Errors Before Deployment

### 22.1. Shared Management Interfaces

Package the interface in a versioned artifact shared by client and server when sensible. This lowers the risk of signature and type drift; still check runtime metadata since the server might use a different assembler.

### 22.2. JMX Contract Testing

In integration tests, register the MBean into a test server and assert:

- Exact ObjectName.
- `MBeanInfo` contains the right attributes, operations, and signatures.
- Safe getters can be read.
- Writable attributes enforce validation.
- Unexpected operations are absent.
- A proxy with the same interface can invoke it.

### 22.3. Monitoring Deployment and Lifecycle

An MBean exported during startup may not be ready yet. Export `STARTING`/`READY` states and require callers to check before sensitive operations.

### 22.4. Minimizing Surface Area

Export only necessary MBeans. Never expose tokens, passwords, or raw config; separate read-only monitoring from control operations when needed.

### 22.5. Bounded Reconnects

Design appropriate timeouts and reconnects. Retrying read-only operations can be sensible; side-effecting operations require idempotency or state verification.

### 22.6. Identifying the Right Server

Across multiple JVMs/namespaces, establish clear naming conventions—for instance, ObjectNames containing a module or non-sensitive instance ID. Do not use a load-balanced endpoint in a way that causes the proxy to hit MBeans with different contracts randomly.

## 23. Hands-on Exercises

**Exercise 1 — Wrong ObjectName.** Register an MBean at `company.workers:type=WorkerManagement,name=primary` and configure the proxy with `name=secondary`. Confirm the connector/raw server metadata work while the proxy fails, then use `queryNames` to find the right name.

**Exercise 2 — Wrong Attribute Name.** The server exports `ActiveWorkers`, while the client interface only has `getActiveWorkerCount()`. Use `MBeanInfo` to identify the difference and align the contract.

**Exercise 3 — Signature Mismatch.** The server has `resizePool(int)`, while the client declares `resizePool(long)`. Compare `MBeanOperationInfo.getSignature()` and the error from raw `invoke`.

**Exercise 4 — Read-Only Credentials.** Create a monitoring identity with read-only permissions and try invoking a state-changing operation. Explain why connecting and reading metadata succeed yet the operation is denied.

**Exercise 5 — Runtime Exception.** Create an `@ManagedOperation` that throws `IllegalStateException` when the service is not READY. Observe the exception chain on both proxy and server.

**Exercise 6 — MXBean Mapping.** Create an MXBean returning a DTO with OpenType mapping. Compare raw `CompositeData` with typed `JMX.newMXBeanProxy` and explain why a Standard proxy may fail on types.

**Exercise 7 — Server Restart.** Use a separate test JVM, connect, and then restart the target. Distinguish a session failure from an unregistered ObjectName after restart; design reconnect/readiness handling.

**Exercise 8 — Permissions and Auditing Test.** Configure a test JMX endpoint with authentication/TLS and use identities with different permission levels to call attributes and operations; document differences without disclosing credentials.

## 24. Self-Check Questions

1. What does a successful `JMXConnectorFactory.connect(...)` confirm?
2. Why does `getDefaultDomain()` succeeding not prove the proxy will work?
3. How do `ObjectName` and a Spring bean name differ?
4. How does `MBeanInfo` help diagnose interface drift?
5. Why might `getActiveWorkers()` fail to match attribute `ActiveWorkerCount`?
6. What types do JMX operation signatures require?
7. Can a read-only client connect yet fail to `invoke`?
8. Why can `MBeanException` merely be a wrapper around an error inside the target?
9. Does a timeout guarantee the operation never ran?
10. Why must the raw API test use the same `MBeanServerConnection` as the proxy?
11. How do a `FactoryBean` and its product proxy differ when calling `getBean`?
12. Why should you not call side-effecting operations to test connectivity?

## 25. Key Takeaways

**A successful JMX connection only confirms the connector can talk to the MBeanServer—it does not prove a specific MBean can be called successfully through a proxy.** Follow this sequence: **right connection → right ObjectName → compatible MBeanInfo → raw JMX call → Spring proxy**.

If the raw API also fails, inspect registration, permissions, data types, and target runtime state. If the raw API works while the proxy fails, inspect the management interface, mapping, Spring wiring, MXBean conversion, and interceptor. For network errors, separate session failures from operation failures and never blindly retry side-effecting operations.
