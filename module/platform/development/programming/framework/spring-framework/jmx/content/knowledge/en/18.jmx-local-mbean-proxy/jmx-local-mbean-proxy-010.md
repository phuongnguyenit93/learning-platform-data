# Choosing a Proxy to Decouple the Client from the Implementation

> **Topic:** Spring Framework JMX  
> **Knowledge area:** Local MBean Proxy  
> **Lesson:** Choosing a proxy to decouple the client from the implementation

## 1. Objectives

After this lesson, you will be able to:

- Explain why a management client should not depend directly on a Spring bean's implementation.
- Distinguish **calling a service directly** from **calling an MBean through a JMX proxy** in the same JVM.
- Understand the roles of \`MBeanServerConnection\`, \`ObjectName\`, management interface, and \`MBeanProxyFactoryBean\`.
- Use \`JMX.newMBeanProxy\` or Spring \`MBeanProxyFactoryBean\` to invoke operations and read attributes.
- Know when to choose a proxy for a stable management boundary, while recognizing when direct service injection is more appropriate.
- Handle unregistered MBean errors, wrong ObjectNames, mismatched interface contracts, and lifecycle changes.

## 2. Design problem: what does the client depend on?

An application has a service implementation:

\`\`\`java
public class CacheService {
    public long currentEntries() { ... }
    public void refresh() { ... }
}
\`\`\`

If an admin tool or another module injects \`CacheService\` directly, that module must know its implementation class, dependencies, and lifecycle.

\`\`\`text
Admin client
    |
    | directly calls Java method
    v
CacheService implementation
\`\`\`

When swapping classes, splitting modules, or changing how data is exposed, the client may need recompilation. If the goal is **management communication through a JMX contract**, this direct dependency loses the benefit of a management boundary layer.

A JMX proxy introduces an additional layer:

\`\`\`text
Admin client
    |
    | calls CacheManagement interface
    v
JMX proxy
    |
    | ObjectName + MBeanServerConnection
    v
MBeanServer
    |
    v
Cache MBean / Spring-managed implementation
\`\`\`

The client only knows the management interface, \`ObjectName\`, and connection. The server-side business class can change as long as the management contract remains compatible.

**Key point:** decoupling from the implementation does not mean removing all coupling. The client still depends on the MBean name, attribute/operation signatures, data types, and reachability of the MBeanServer.

## 3. Concept of a local MBean proxy

A **local MBean proxy** is a Java object in the same JVM as the MBeanServer that lets callers invoke Java methods while the framework translates calls into JMX operations or attribute accesses.

\`\`\`text
Same JVM
+--------------------------------------------------+
| Spring admin component                           |
|    |                                             |
|    v                                             |
| CacheManagement proxy                            |
|    |                                             |
|    +--> MBeanServerConnection                    |
|              |                                   |
|              v                                   |
|          MBeanServer                             |
|              |                                   |
|              v                                   |
|     MBean registered by exporter                 |
|              |                                   |
|              v                                   |
|        CacheService/facade                       |
+--------------------------------------------------+
\`\`\`

Because a local proxy needs no network connector, it can be used within the same process, yet JMX rules still apply: the ObjectName must exist, methods must be published, and signatures must match.

\`MBeanServer\` implements \`MBeanServerConnection\`, so the same connection type can work with a local server or a remote connector. Using a proxy today does not automatically guarantee switching to remote later without changes: data types, exceptions, security, and latency must be reviewed.

## 4. Comparing direct injection with a proxy

| Criterion | Calling Spring bean directly | Calling through a JMX proxy |
|---|---|---|
| Dependency on implementation | Usually knows class/service or business interface | Knows management interface and ObjectName |
| Call path | Java method call | JMX invocation through server |
| Requires registered MBean | No | Yes |
| JMX metadata | Not relevant | Attributes/operations must be published |
| Data types | Can use any internal Java type | Should choose JMX/client-compatible types |
| Exceptions | Per business API | May have lookup, invoke, and connector errors |
| Lifecycle | Per Spring bean | Per Spring bean/exporter/MBean registration |
| When to use | Internal business logic where coupling is acceptable | Management components needing a stable boundary |
| Remote-capable | Not by default | Connection can be swapped if interface/transport fit |

A proxy is not “better by default” for every call. If a Spring component needs to perform ordinary business work on the same service, direct interface injection is usually simpler and more efficient. A JMX proxy fits when the client genuinely wants to follow an MBean's **management API**.

## 5. The interface contract is central

To have a stable proxy, first design a small management interface:

\`\`\`java
package example.management;

public interface CacheManagement {
    long getEntryCount();
    void refresh();
}
\`\`\`

These methods represent what the caller is allowed to observe or control.

With a Standard MBean, the interface convention is normally the class name plus the \`MBean\` suffix:

\`\`\`java
public interface CacheMonitorMBean {
    long getEntryCount();
    void refresh();
}
\`\`\`

With Spring JMX annotations, a bean can be exported via \`@ManagedResource\`, \`@ManagedAttribute\`, and \`@ManagedOperation\`. In that case, the client-side proxy interface does not have to match the implementation class, yet **method names and signatures** must map to the registered MBean metadata.

More important than the interface name is the actual JMX contract: \`getEntryCount()\` corresponds to attribute \`EntryCount\`, while \`refresh()\` corresponds to operation \`refresh\`.

## 6. Plain Standard MBean example with JMX.newMBeanProxy

### 6.1. Management interface

\`\`\`java
package example.jmx;

public interface CacheMonitorMBean {
    long getEntryCount();
    void refresh();
}
\`\`\`

### 6.2. Implementation

\`\`\`java
package example.jmx;

import java.util.concurrent.atomic.AtomicLong;

public class CacheMonitor implements CacheMonitorMBean {

    private final AtomicLong entries = new AtomicLong(12);

    @Override
    public long getEntryCount() {
        return entries.get();
    }

    @Override
    public void refresh() {
        entries.incrementAndGet();
    }
}
\`\`\`

\`CacheMonitor\` is the implementation, while \`CacheMonitorMBean\` is the contract.

### 6.3. Registering and using the proxy

\`\`\`java
package example.jmx;

import java.lang.management.ManagementFactory;
import javax.management.JMX;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class LocalProxyDemo {

    public static void main(String[] args) throws Exception {
        MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();

        ObjectName name = new ObjectName(
            "learning.jmx:type=Cache,name=primary"
        );

        server.registerMBean(new CacheMonitor(), name);

        try {
            CacheMonitorMBean proxy = JMX.newMBeanProxy(
                server,
                name,
                CacheMonitorMBean.class,
                false
            );

            System.out.println(proxy.getEntryCount());
            proxy.refresh();
            System.out.println(proxy.getEntryCount());
        } finally {
            server.unregisterMBean(name);
        }
    }
}
\`\`\`

Illustrative output:

\`\`\`text
12
13
\`\`\`

Here the caller holds no reference to the registered \`CacheMonitor\`. It only holds the proxy, using the interface and ObjectName to call through the MBeanServer.

\`JMX.newMBeanProxy\` is a standard JMX API, not specific to Spring. The local server is passed directly because \`MBeanServer\` is also an \`MBeanServerConnection\`.

### Why can the ObjectName differ from the class name?

The example uses \`type=Cache\` instead of \`type=CacheMonitor\` or a full Java class name. This intentionally decouples the management identity from the implementation name. Renaming \`CacheMonitor\` to \`CacheTelemetryAdapter\` does not necessarily require clients to change their ObjectName if the contract is preserved.

## 7. Spring MBeanProxyFactoryBean

Spring provides \`org.springframework.jmx.access.MBeanProxyFactoryBean\`, a \`FactoryBean\` that creates a proxy to an MBean identified by an ObjectName.

A Java configuration:

\`\`\`java
package example.jmx;

import javax.management.MBeanServerConnection;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.access.MBeanProxyFactoryBean;

@Configuration
public class ManagementClientConfig {

    @Bean
    public MBeanProxyFactoryBean cacheManagementProxy(
            MBeanServerConnection managementConnection
    ) throws Exception {
        MBeanProxyFactoryBean factory =
            new MBeanProxyFactoryBean();

        factory.setServer(managementConnection);
        factory.setObjectName(
            "learning.jmx:type=Cache,name=primary"
        );
        factory.setProxyInterface(CacheManagement.class);

        return factory;
    }
}
\`\`\`

Client injection:

\`\`\`java
import org.springframework.stereotype.Component;

@Component
public class CacheAdminPanel {

    private final CacheManagement cacheManagement;

    public CacheAdminPanel(CacheManagement cacheManagement) {
        this.cacheManagement = cacheManagement;
    }

    public void displayAndRefresh() {
        System.out.println(cacheManagement.getEntryCount());
        cacheManagement.refresh();
    }
}
\`\`\`

In the example, \`CacheManagement\` is the management interface known to the client. To succeed, the MBean at \`learning.jmx:type=Cache,name=primary\` must actually publish \`EntryCount\` and \`refresh()\`.

Note on the Spring \`MBeanServerConnection\` bean: the configuration must register an appropriate connection bean, such as the platform MBeanServer or a custom server. Do not assume every Spring context automatically provides an \`MBeanServerConnection\` bean.

### Configuring a local connection

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServerConnection;

@Bean
public MBeanServerConnection managementConnection() {
    return ManagementFactory.getPlatformMBeanServer();
}
\`\`\`

To avoid ambiguity, you can create an \`MBeanServer\` bean and use the exact same object for both the exporter and the proxy. If the exporter uses a server other than the platform server, a proxy pointing to the platform server may not find the MBean.

## 8. Spring export via annotations and a client proxy

A Spring bean can be published via annotations:

\`\`\`java
package example.management;

import java.util.concurrent.atomic.AtomicLong;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "learning.jmx:type=Cache,name=primary",
    description = "Primary cache management"
)
public class CacheManagementFacade {

    private final AtomicLong entries = new AtomicLong(12);

    @ManagedAttribute(description = "Cached entry count")
    public long getEntryCount() {
        return entries.get();
    }

    @ManagedOperation(description = "Refresh cache")
    public void refresh() {
        entries.incrementAndGet();
    }
}
\`\`\`

Enabling the annotation exporter:

\`\`\`java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxExportConfig {
}
\`\`\`

Once the context finishes initializing and the exporter registers successfully, the client can use \`MBeanProxyFactoryBean\` to call the corresponding methods.

\`\`\`text
CacheAdminPanel
      |
      v
CacheManagement (proxy interface)
      |
      v
MBeanProxyFactoryBean proxy
      |
      v
MBeanServerConnection
      |
      v
ObjectName: learning.jmx:type=Cache,name=primary
      |
      v
CacheManagementFacade @ManagedResource
\`\`\`

The client does not need to import \`CacheManagementFacade\` from the server module. This is a clear layering benefit when managing through a narrow API.

## 9. How does the proxy translate calls into JMX operations?

For a Standard MBean proxy, basic rules:

| Client-side Java method | JMX meaning |
|---|---|
| \`getEntryCount()\` | Read attribute \`EntryCount\` |
| \`isEnabled()\` | Read Boolean attribute \`Enabled\` |
| \`setEnabled(boolean)\` | Write attribute \`Enabled\` |
| \`refresh()\` | Invoke operation \`refresh\` |
| \`resize(int)\` | Invoke \`resize\` with signature \`int\` |

Operation call path:

\`\`\`text
proxy.resize(8)
    |
    v
MBeanServerConnection.invoke(
    name,
    "resize",
    new Object[] {8},
    new String[] {"int"}
)
    |
    v
Registered MBean
\`\`\`

In practice, the proxy handler performs the translation. The client just calls a Java method, yet exceptions still occur if JMX metadata is incompatible.

If a client-side method changes from \`resize(int)\` to \`resize(long)\`, even though the name stays the same, the JMX signature changes. Do not rely on automatic boxing/widening like the Java compiler to assume every overload will be compatible.

## 10. Choose a proxy to decouple the implementation, not to avoid all dependencies

A proxy is useful when the client only needs a contract:

\`\`\`java
public interface WorkerControl {
    int getActiveCount();
    void pause();
}
\`\`\`

The implementation can be:

\`\`\`text
ThreadPoolWorker
ExecutorServiceAdapter
RemoteWorkerManager
\`\`\`

As long as the same attributes and operations are exported under a stable ObjectName, the client does not need to know which implementation is executing.

However, the proxy still depends on:

- The chosen ObjectName.
- Whether \`MBeanServerConnection\` points to the right registry.
- The list of attributes/operations and signatures.
- Data types understood by the client.
- MBean lifecycle and connection state.
- Appropriate access permissions.

Therefore, the management interface must be managed like an API. Do not attach an entire service interface full of internal methods to a proxy and expect those methods to appear in JMX automatically.

## 11. When should you use a local MBean proxy?

Several suitable scenarios:

### 11.1. Admin module independent of business module

An admin module in the same JVM needs to read status and invoke a few management operations, without depending on the service's package and implementation classes. A proxy via a management interface preserves module boundaries.

### 11.2. Operational tooling sharing a JMX access path

An application has JConsole, a monitoring agent, and a local admin component. If all use the same management contract, a local proxy saves the admin component from building a separate direct API to the service.

### 11.3. Potential to move the client to a remote connection

If the interface uses types compatible with JMX transport, a local \`MBeanServerConnection\` can be swapped for a connection from \`JMXConnector\`. However, moving to remote requires additional handling for networking, authentication, latency, serialization, and reconnection.

### 11.4. Client needs to mock the management contract

A narrow interface can be mocked in unit tests of the admin module:

\`\`\`java
CacheManagement management = mock(CacheManagement.class);
when(management.getEntryCount()).thenReturn(42L);
\`\`\`

The example uses a mocking framework like Mockito in tests. This is a benefit of depending on an interface; using a JMX proxy is not mandatory in every test.

## 12. When should you avoid a proxy?

A proxy carries configuration, lookup, and runtime condition costs. Do not use it merely to “add another architectural layer” in cases such as:

- Two Spring beans in the same module coordinating routine business logic.
- The client needing a richly typed domain API or complex transaction boundaries.
- No requirement to publish a management interface.
- Extremely latency-sensitive, high-frequency call paths with no reason to go through MBeanServer.
- Needing service-layer transaction/security control that a JMX boundary is not designed to replicate.
- Calls needing context such as request identity, tracing, or session state outside the JMX contract.

Example:

\`\`\`java
@Service
class OrderProcessor {
    private final PaymentService paymentService;

    OrderProcessor(PaymentService paymentService) {
        this.paymentService = paymentService;
    }
}
\`\`\`

This is ordinary business injection and should not replace \`PaymentService\` with a JMX proxy solely to reduce coupling. To decouple from the implementation, inject a **business interface**; there is no need to detour through MBeanServer.

## 13. Choosing a management facade instead of exporting the service directly

A service can have a wide API:

\`\`\`java
class CacheService {
    void refresh();
    void deleteAllData();
    String getProviderToken();
    void setCriticalFlag(boolean enabled);
}
\`\`\`

Do not export everything and create a proxy to it.

Instead:

\`\`\`java
public interface CacheManagement {
    long getEntryCount();
    void refresh();
}
\`\`\`

Facade:

\`\`\`java
@Component
@ManagedResource(
    objectName = "app.management:type=Cache,name=primary"
)
public class CacheManagementFacade {

    private final CacheService cacheService;

    public CacheManagementFacade(CacheService cacheService) {
        this.cacheService = cacheService;
    }

    @ManagedAttribute
    public long getEntryCount() {
        return cacheService.entryCount();
    }

    @ManagedOperation
    public void refresh() {
        cacheService.refresh();
    }
}
\`\`\`

The client proxy sees only the required contract. The benefit of a proxy comes from a **curated management contract**, not merely from having a Java object called a proxy.

## 14. A stable ObjectName matters more than the implementation name

Suppose the implementation was originally named \`RedisCacheManagementFacade\`, then renamed to \`CaffeineCacheManagementFacade\`.

If the client locates the MBean via:

\`\`\`text
app.management:type=Cache,name=primary
\`\`\`

it does not need to change when the class is renamed, provided the server keeps registering the same ObjectName and maintains compatible attributes/operations.

Conversely, if the ObjectName is derived from the runtime class:

\`\`\`text
com.example.cache:type=RedisCacheManagementFacade
\`\`\`

changing the class can break the client.

Use \`@ManagedResource(objectName = "...")\` or an appropriate \`ObjectNamingStrategy\` to decouple management names from implementations. Also avoid letting CGLIB/JDK dynamic proxy names become the sole management contract.

## 15. Lifecycle and initialization timing issues

A proxy created in a Spring context may require the target MBean to be ready. Yet the exporter and client proxy can initialize in the same context.

\`\`\`text
Context startup
  |
  +-- Create business bean
  +-- Create exporter
  +-- Register MBean
  +-- Create proxy
  +-- Client begins using proxy
\`\`\`

If initialization order is unsuitable, a proxy may try to connect to an MBean that does not exist yet.

With Spring \`MBeanProxyFactoryBean\`, check the \`connectOnStartup\` setting of the access component appropriate to your Spring version. Connecting eagerly helps fail fast when the MBean is missing; if deferring, organize bounded retry/availability logic and clear startup contracts.

Another approach is isolating the management client into a component that only operates after the context is ready. Avoid calling JMX operations from constructors or \`@PostConstruct\` before the exporter finishes its lifecycle.

## 16. Wrong MBeanServerConnection is a common mistake

An application may create a dedicated server:

\`\`\`java
MBeanServer custom = MBeanServerFactory.newMBeanServer(
    "isolated.management"
);
\`\`\`

The exporter registers the MBean into \`custom\`, while the proxy uses:

\`\`\`java
ManagementFactory.getPlatformMBeanServer()
\`\`\`

In that case, the proxy will not find the MBean even though export succeeded.

Explicitly configure the same server:

\`\`\`java
@Bean
public MBeanServer managementServer() {
    return ManagementFactory.getPlatformMBeanServer();
}
\`\`\`

Exporter:

\`\`\`java
@EnableMBeanExport(server = "managementServer")
\`\`\`

Client:

\`\`\`java
@Bean
public MBeanServerConnection managementConnection(
        MBeanServer managementServer
) {
    return managementServer;
}
\`\`\`

An \`MBeanServer\` is an \`MBeanServerConnection\`, so the same instance can be used. Do not only compare ObjectName strings; verify that the client and exporter use the **same registry**.

## 17. Exceptions when calling through a proxy

Cases:

| Error | Situation | How to handle |
|---|---|---|
| \`InstanceNotFoundException\` | ObjectName is not registered | Check server, startup, and lifecycle |
| \`AttributeNotFoundException\` | Getter maps to a nonexistent attribute | Read \`MBeanInfo\` |
| \`ReflectionException\` | Operation does not exist or signature is wrong | Match method/metadata |
| \`MBeanException\` | Server-side operation threw a checked exception | Inspect underlying exception |
| \`RuntimeMBeanException\` | Implementation threw a runtime exception | Handle logic/validation |
| \`IOException\` | Remote connector failed | Reconnect and bound retries |
| Spring JMX access error | Exception wrapped by proxy/interceptor | Read cause and log appropriately |

When using a Java proxy, some JMX checked exceptions may be wrapped in a runtime exception or \`UndeclaredThrowableException\` depending on the invocation handler/interface. Therefore, the client should inspect the root cause and not assume every method throws only exceptions declared on the interface.

### Reading metadata instead of guessing

\`\`\`java
MBeanInfo info = connection.getMBeanInfo(name);

for (MBeanOperationInfo op : info.getOperations()) {
    System.out.println(op.getName());
}

for (MBeanAttributeInfo a : info.getAttributes()) {
    System.out.println(a.getName());
}
\`\`\`

Metadata classes reside in \`javax.management\`. Cross-check names, types, and signatures against the client-side management interface.

## 18. Proxies do not handle unregister/re-register automatically

An MBean can be unregistered because the Spring context closes, an exporter replaces a registration, or an application restarts.

The client-side proxy still exists as a Java object holding the \`ObjectName\`, yet calls can fail while the MBean is unregistered.

\`\`\`text
Proxy exists
    |
    | MBean is unregistered
    v
invoke/getAttribute -> error
    |
    | MBean is re-registered under same ObjectName
    v
Callable again if contract is compatible
\`\`\`

Do not assume the proxy automatically restores connections or listeners. In a local environment, establish explicit lifecycle ordering between exporter and client. If moving to remote, implement status checks and policy-driven reconnection.

## 19. Notifications through a proxy

The JMX API \`JMX.newMBeanProxy\` has a \`notificationBroadcaster\` parameter:

\`\`\`java
CacheMonitorMBean proxy = JMX.newMBeanProxy(
    connection,
    name,
    CacheMonitorMBean.class,
    true
);
\`\`\`

With \`true\`, the proxy can support \`NotificationEmitter\` when the server-side MBean is capable of emitting notifications.

A client can cast to \`NotificationEmitter\` and register listeners per the JMX contract, provided the MBean actually publishes and emits notifications. This is an optional capability, not required for proxies that only read attributes/invoke operations.

In Spring \`MBeanProxyFactoryBean\`, listeners can be managed using the direct JMX API or appropriate configuration; do not assume every Spring proxy automatically exposes a notification emitter in the same way.

## 20. Local proxy and migrating to remote

Local model:

\`\`\`java
MBeanServerConnection connection =
    ManagementFactory.getPlatformMBeanServer();
\`\`\`

Remote model:

\`\`\`java
JMXServiceURL url = new JMXServiceURL(
    "service:jmx:rmi:///jndi/rmi://localhost:9999/jmxrmi"
);

JMXConnector connector =
    JMXConnectorFactory.connect(url);

MBeanServerConnection connection =
    connector.getMBeanServerConnection();
\`\`\`

The client proxy can continue using the management interface and ObjectName. However, remote requires additionally:

- JMX connector server properly enabled.
- Authentication, authorization, and TLS when required.
- Working network and RMI endpoints.
- Parameter/return types that are serializable or JMX-compatible.
- Timeout, disconnect, and connector lifecycle handling.
- Restraint when calling side-effecting operations where previous retry outcomes are unknown.

\`@EnableMBeanExport\` only exports MBeans; it does not automatically open a remote JMX port. A local client using a proxy does not prove the system has secure remote access configured.

## 21. Cost and performance

Each proxy call passes through the JMX invocation layer, metadata, and corresponding adapter layers. Compared to a direct method call, it carries some overhead, even within the same JVM.

Therefore:

- Do not use a JMX proxy on hot paths with thousands of calls per request.
- Do not use JMX as a high-throughput business API.
- Prefer low-frequency, purposeful management operations.
- Do not return a large object graph merely to display a few metrics.
- Consider a dedicated metrics API if high-frequency metric collection is all that is needed.

A proxy reduces coupling at the **management boundary**, rather than optimizing every kind of call.

## 22. Hands-on exercise

**Context:** module \`admin-ui\` and module \`inventory-core\` run in the same JVM. \`inventory-core\` has class \`InventoryServiceImpl\`. Admin UI only needs to read aggregated inventory count and request a data refresh.

**Suggested design:**

Management interface:

\`\`\`java
public interface InventoryManagement {
    long getTotalItems();
    void refreshSnapshot();
}
\`\`\`

Server-side facade:

\`\`\`java
@Component
@ManagedResource(
    objectName = "app.management:type=Inventory,name=main"
)
public class InventoryManagementFacade {

    private final InventoryService service;

    public InventoryManagementFacade(InventoryService service) {
        this.service = service;
    }

    @ManagedAttribute
    public long getTotalItems() {
        return service.totalItems();
    }

    @ManagedOperation
    public void refreshSnapshot() {
        service.refreshSnapshot();
    }
}
\`\`\`

The admin client uses \`MBeanProxyFactoryBean\` with interface \`InventoryManagement\` and ObjectName \`app.management:type=Inventory,name=main\`.

**Question:** When \`InventoryServiceImpl\` is replaced by another implementation, does the client have to change code?

If the management interface, ObjectName, and data types remain compatible, the client does not need to know the new implementation.

**Question:** When does admin UI not need a JMX proxy?

If both modules only need a business interface and have no requirement to cross a management boundary, injecting the business interface directly can be simpler and more appropriate.

## 23. Self-check questions

1. To what extent does a JMX proxy decouple the client from the implementation?
2. Why does a proxy still need an ObjectName and the right MBeanServerConnection?
3. How do \`JMX.newMBeanProxy\` and \`MBeanProxyFactoryBean\` differ in configuration responsibilities?
4. Why does \`getEntryCount()\` usually map to an attribute access?
5. When is injecting a service interface directly better than an MBean proxy?
6. Why should you export a management facade instead of the entire service?
7. When an MBean is unregistered, does an already-created Java proxy disappear automatically?
8. What additional factors must be considered when moving from local to remote?
9. What happens if a proxy interface declares a method not exported by the MBean?
10. How do you verify an MBean contract after refactoring?

## 24. Key takeaways

\`\`\`text
Client depends on:
  management interface
  + ObjectName
  + MBeanServerConnection

Proxy:
  Java method -> JMX attribute/operation

Server depends on:
  Spring bean / management facade
  + MBeanExporter
  + MBeanServer registry
\`\`\`

**Conclusion:** choose a local MBean proxy when the goal is to **decouple the management client from the implementation class**, share an explicit JMX contract, and allow swapping the backing implementation. Do not use a proxy merely to replace every internal bean call. Real value comes from a small management interface, stable ObjectName, right registry, and intentionally managed lifecycle.