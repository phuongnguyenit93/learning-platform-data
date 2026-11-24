# Testing Local, Remote, Proxy, and Network Failure Behavior in Spring Framework JMX

## 1. Review Objective

A Spring application can publish managed beans via `MBeanExporter`, allowing calls on an `MBeanServer` in the same JVM, via `MBeanProxyFactoryBean`, or from another JVM over a JMX RMI connector. These paths share the JMX interface, yet have different failure modes. Testing only a Java getter on the target bean does not tell us whether the MBean contract is right, whether the Spring proxy maps accurately, or whether the remote connector passes firewalls/TLS properly.

This lesson builds a four-part evaluation matrix:

1. **Local JMX:** registration, ObjectName, `MBeanInfo`, attributes/operations, and lifecycle.
2. **Spring JMX proxy:** `proxyInterface`, getter/setter/operation mapping, AOP, and forwarding errors.
3. **Remote JMX:** RMI Registry, connector, `MBeanServerConnection`, authentication/TLS, and serialization.
4. **Network failures:** timeouts, connection drops, reconnects, stale stubs, and uncertain invoke outcomes.

The desired outcome is not merely "can connect"; the system must fail in classifiable ways, avoid re-executing dangerous operations, and recover when connectors change.

## 2. Request Path and Failure Points

~~~text
Application caller
  |
  +--> Local MBeanServer -----------+
  |                                 |
  +--> MBeanProxyFactoryBean        |
  |       |                         |
  |       v                         |
  |  MBeanServerConnection          |
  |       |                         |
  |       +--> Local server --------+
  |       |
  |       +--> JMXConnector / RMI
  |                  |
  |            JMXConnectorServer
  |                  |
  +------------------+
                     |
                     v
                 MBeanServer
                     |
                     v
                  MBean
                     |
                     v
             Business target/AOP
~~~

A remote request can fail before reaching the MBean: during RMI Registry lookup, at the TLS/auth step, in JMX method dispatch, or inside the target method. Do not treat every `IOException` as a Spring exporter bug or every `ReflectionException` as a network error.

## 3. Sample Management Contract

Standard MBean:

~~~java
public interface WorkerControlMBean {
    int getQueueDepth();
    boolean isPaused();
    void pause();
    void resume();
}
~~~

~~~java
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

public final class WorkerControl implements WorkerControlMBean {
    private final AtomicBoolean paused = new AtomicBoolean();
    private final AtomicInteger queueDepth = new AtomicInteger(5);

    public int getQueueDepth() {
        return queueDepth.get();
    }

    public boolean isPaused() {
        return paused.get();
    }

    public void pause() {
        paused.set(true);
    }

    public void resume() {
        paused.set(false);
    }
}
~~~

MBeanServer registration with ObjectName:

~~~java
ObjectName name = new ObjectName(
    "com.example.jobs:type=Worker,name=Test"
);

server.registerMBean(new WorkerControl(), name);
~~~

Expected contract:

| Component | JMX Metadata |
| --- | --- |
| QueueDepth | Readable attribute of type `int` |
| Paused | Readable attribute of type `boolean` |
| pause | Zero-parameter operation |
| resume | Zero-parameter operation |
| ObjectName | `com.example.jobs:type=Worker,name=Test` |

In production-like tests, separate side-effecting operations from read-only probes. Tests must never be used to pause production workers.

## 4. Evaluation Matrix

| Test Area | Local | Spring Proxy | Remote | Fault Injection |
| --- | --- | --- | --- | --- |
| ObjectName registration | Yes | Yes | Yes | MBean unregistration |
| `getAttribute` | Yes | Getter proxy | Yes | Timeout/disconnect |
| `invoke` | Yes | Operation proxy | Yes | Uncertain outcome |
| `MBeanInfo` | Yes | Indirect | Yes | Metadata lookup fail |
| Getter/setter mapping | Yes | Required | Yes | Mismatched signature |
| Server-side AOP proxy | Config-dependent | Yes | Yes | Target failure |
| RMI Registry and stub | No | Remote only | Yes | Registry/port failure |
| Authentication/TLS | No | Per connection | Yes | Credential/cert failure |
| Reconnect | No | When remote | Yes | Connector restart |
| Notification | Yes | Possible | Yes | Listener disconnect |
| Performance | Getter/dispatch | Proxy overhead | Network overhead | Retry burst |

Each row needs a test or layer-isolating check. Do not treat a single integration test that connects successfully as covering all remaining scenarios.

## 5. Local Testing with an Isolated MBeanServer

~~~java
import static org.junit.jupiter.api.Assertions.*;
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import javax.management.ObjectName;
import org.junit.jupiter.api.Test;

class LocalJmxTest {
    @Test
    void registrationMetadataAndInvocationWork() throws Exception {
        MBeanServer server =
            MBeanServerFactory.createMBeanServer("jmx-test");

        ObjectName name = new ObjectName(
            "com.example.jobs:type=Worker,name=Test"
        );

        try {
            server.registerMBean(new WorkerControl(), name);

            assertTrue(server.isRegistered(name));
            assertEquals(5, server.getAttribute(name, "QueueDepth"));
            assertEquals(false, server.getAttribute(name, "Paused"));

            server.invoke(
                name, "pause", new Object[0], new String[0]
            );
            assertEquals(true, server.getAttribute(name, "Paused"));
        } finally {
            if (server.isRegistered(name)) {
                server.unregisterMBean(name);
            }
            MBeanServerFactory.releaseMBeanServer(server);
        }
    }
}
~~~

Testing with an isolated MBeanServer avoids ObjectName collisions with MBeans in the test runner JVM. It proves the Standard MBean contract; if production uses Spring `MBeanExporter`, add a test initializing the Spring context and exporter against the intended MBeanServer.

Always clean up registrations owned by the test. Never unregister platform JVM MBeans or another test's MBeans.

## 6. Inspecting MBeanInfo Instead of Guessing from Java Methods

~~~java
var info = server.getMBeanInfo(name);

for (var a : info.getAttributes()) {
    System.out.printf(
        "%s %s readable=%s writable=%s%n",
        a.getName(),
        a.getType(),
        a.isReadable(),
        a.isWritable()
    );
}

for (var op : info.getOperations()) {
    System.out.printf(
        "operation=%s return=%s%n",
        op.getName(),
        op.getReturnType()
    );

    for (var p : op.getSignature()) {
        System.out.println("  param=" + p.getType());
    }
}
~~~

Getter `getQueueDepth()` may be published as the `QueueDepth` attribute rather than appearing in the operations list. For overloaded operations, compare both names and parameter types. When Spring uses a metadata assembler, annotations, and server-side AOP proxies, `MBeanInfo` is the actual contract clients observe.

Do not conclude a method missing from `MBeanInfo` is a network issue. Verify the local contract first before testing remote access.

## 7. Testing Spring MBeanProxyFactoryBean

~~~java
import org.springframework.jmx.access.MBeanProxyFactoryBean;

MBeanProxyFactoryBean factory = new MBeanProxyFactoryBean();
factory.setServer(server);
factory.setObjectName(name);
factory.setProxyInterface(WorkerManagementClient.class);
factory.afterPropertiesSet();

WorkerManagementClient client =
    (WorkerManagementClient) factory.getObject();

if (client == null) {
    throw new IllegalStateException("Proxy not created");
}

int queued = client.getQueueDepth();
client.pause();
boolean after = client.isPaused();
~~~

Client interface:

~~~java
public interface WorkerManagementClient {
    int getQueueDepth();
    boolean isPaused();
    void pause();
    void resume();
}
~~~

Key checks:
- The proxy actually implements the expected client interface.
- Java getters map to JMX attributes, not operations of the same name.
- Operation names and signatures match `MBeanInfo`.
- Return types are compatible with the client interface.
- Unregistered or subsequently unregistered MBeans produce clear failure modes.
- Exceptions are translated/wrapped without hiding the root cause.
- Do not add methods to `proxyInterface` if the MBean does not export them.

Successfully creating a Spring proxy does not guarantee every method invokes cleanly; integration tests must invoke the methods in the contract.

## 8. Server-Side AOP Proxies vs. Client-Side JMX Proxies

A Spring service may be wrapped in a JDK/CGLIB proxy for transactions, caching, or security. Meanwhile, `MBeanProxyFactoryBean` creates a **client** proxy to dispatch calls to an `MBeanServer`.

~~~text
Client -> JMX client proxy -> MBeanServer
                                   |
                                   v
                             JMX adapter
                                   |
                                   v
                             AOP-proxied service
~~~

If the server directly exports a JDK proxy, a management method present only on the target class but absent from the proxy interface may run into trouble during exporter metadata selection or invocation.

You can inspect:

~~~java
import org.springframework.aop.support.AopUtils;

Object bean = context.getBean("workerService");

System.out.println("runtime=" + bean.getClass());
System.out.println("aop=" + AopUtils.isAopProxy(bean));
System.out.println("target=" + AopUtils.getTargetClass(bean));
~~~

Compare against the `MBeanInfo` of the registered object. Extracting a small management adapter usually keeps the contract far more stable than exporting an entire service carrying multiple advices.

## 9. Remote JMX: Client and Connector

Remote clients use `JMXServiceURL`:

~~~java
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

JMXServiceURL url = new JMXServiceURL(
    "service:jmx:rmi:///jndi/rmi://127.0.0.1:9010/jmxrmi"
);

try (JMXConnector connector =
        JMXConnectorFactory.connect(url)) {

    var remote = connector.getMBeanServerConnection();

    if (!remote.isRegistered(name)) {
        throw new IllegalStateException("Missing MBean");
    }

    System.out.println(
        remote.getAttribute(name, "QueueDepth")
    );
}
~~~

This example assumes a matching `JMXConnectorServer` and RMI Registry are running. The connector server must attach to the same `MBeanServer` where the exporter registered the MBean.

Production remote configurations require authentication, TLS, network isolation, and secret handling. Never expose an unauthenticated connector to the Internet; never disable auth/TLS just to simplify testing.

## 10. Two RMI Ports and the NAT Problem

An RMI endpoint typically involves two steps:

~~~text
Client -> RMI Registry on host:9010
       -> lookup jmxrmi
       -> receives RMI stub
       -> connects to advertised host:9011
       -> calls JMX operations
~~~

Successfully connecting to the registry port does not guarantee the client can reach the RMI endpoint. In Docker/Kubernetes, the stub may advertise an internal IP unreachable from clients outside the cluster.

Verify:
- Registry host/port are correct.
- Binding lookup matches the expected name.
- The advertised hostname resolves and routes from the client.
- The RMI endpoint port is opened/forwarded properly.
- TLS/auth on the required channels.
- The connector has a clear lifecycle owner.

JVM agent properties such as `com.sun.management.jmxremote.rmi.port` do not automatically control custom connectors created by Spring or libraries; verify the actual implementation.

## 11. Network Failure Scenarios to Test

| Scenario | Observed Result | Root-Cause Category |
| --- | --- | --- |
| Registry not running | Connection refused/unreachable | Bootstrap |
| Registry running but binding missing | Naming/lookup error | RMI JNDI |
| Stub advertises wrong host | Timeout after lookup | Network/NAT |
| RMI endpoint port blocked | Connection fails to complete | Firewall |
| Invalid credentials | Authentication failure | Security |
| Invalid TLS truststore | Handshake failure | Security |
| MBean not registered | `InstanceNotFound` | JMX registration |
| Proxy method mismatch | Attribute/operation missing | Contract |
| Disconnect during `getAttribute` | Read failed | Transport |
| Disconnect during `invoke` | Outcome may be unknown | Transport + business |
| Connector restart | Old connection stale | Lifecycle |
| Listener lost after reconnect | Notifications stop arriving | Registration |

Fault injection should only run in an isolated test environment or an approved environment. Never arbitrarily block remote JMX ports in production.

## 12. Uncertain Outcomes on `invoke`

Consider this sequence of events:

~~~text
Client sends restartWorker()
Server receives restartWorker()
Server executes operation
Network drops before response
Client sees IOException
~~~

The client cannot conclude on its own that the operation did not run. For side-effecting commands, blind retries can execute dangerous actions twice.

A sound contract requires:
- Desired-state operations like `setPaused(true)` instead of `togglePaused()`.
- A stable request ID for long-running or non-idempotent commands.
- A status attribute/operation to inspect the outcome.
- Server-side deduplication by key if needed.
- Bounded retries based on error type, with backoff and jitter.
- A version/epoch so a stale controller cannot overwrite a newer decision.

Do not confuse network delivery with an exactly-once business effect. Remote JMX does not guarantee exactly-once execution for custom operations.

## 13. Testing Reconnection

A complete scenario:

1. Start `MBeanServer` and register the MBean.
2. Start connector A and open a client connection.
3. Query `MBeanInfo` and read attributes successfully.
4. Stop connector A.
5. Observe calls failing on the old connection.
6. Start connector B configured for the intended endpoint.
7. Create a new `JMXConnector` on the client.
8. Re-query ObjectName and `MBeanInfo`.
9. Perform a read-only probe and an authorized test operation.
10. Clean up connectors, listeners, and MBean registrations.

Do not assume stopping a connector automatically closes a shared RMI Registry. During context redeploy, verify the exporter unregisters only the MBeans owned by that context.

If ObjectNames change due to unique-name rules or new instance names, clients must rediscover rather than hardcoding the old identity.

## 14. Notifications Over a Remote Connector

Clients can register a listener:

~~~java
NotificationListener listener =
    (notification, handback) ->
        System.out.println(notification.getType());

remote.addNotificationListener(
    name, listener, null, null
);
~~~

After a reconnect, do not assume the old listener registration still works. Depending on the connector and client lifecycle, re-register the listener and verify no duplicate callbacks occur.

Notification tests should verify type, source, filter, handback, and cleanup. JMX notifications are not a durable event log with guaranteed replay; if exactly-once event processing is needed, use an appropriate messaging mechanism.

## 15. Security Testing for the Remote Path

A security test matrix:
- Clients without credentials are rejected when auth is enabled.
- Wrong credentials are rejected.
- Valid principals can read authorized MBeans.
- Side-effecting operations are restricted on the server/connector.
- Valid TLS certificates are accepted.
- Invalid certificates are rejected per policy.
- Secrets are not logged in service URLs, exceptions, or metrics.
- Credential rotation/revocation is verified.
- Existing sessions after revocation are evaluated against the threat model.

Spring Security HTTP and JMX RMI are not the same channel; rules for `/actuator/**` do not automatically protect the remote JMX connector.

## 16. Comparing Local and Remote Metadata

~~~java
var localInfo = localServer.getMBeanInfo(name);
var remoteInfo = remoteConnection.getMBeanInfo(name);
~~~

Necessary contract checks:
- Attribute names/types/readable/writable flags.
- Operation names/signatures/return types.
- Notification types.
- Descriptions if they are part of the operational API.

Do not compare raw `toString()` output if metadata ordering or descriptors differ while the contract remains compatible. If remote metadata differs from local, verify the right JVM, right server, and right ObjectName before concluding the connector altered the data.

## 17. Performance and Load Testing

Different performance layers:
- Local getter/operation cost.
- Spring proxy dispatch overhead.
- RMI serialization, TLS, and network RTT.
- Concurrent client polling.
- MBean discovery and `getMBeanInfo` frequency.
- Notification rate/queue pressure.
- Target CPU/GC/lock contention.
- Reconnect/retry bursts when connectors fail.

Benchmarks must keep workloads close to production and measure service throughput/p95/p99 as well, not just JMX call latency. A getter running a DB query can slow down the service under polling load even if local tests run very fast.

## 18. Controlling Flaky Tests

For stable tests:
- Use an isolated `MBeanServer` or unique ObjectNames per fixture.
- Do not hardcode ports shared by a parallel test suite.
- Use bounded timeouts and condition-based waits instead of fixed `Thread.sleep`.
- Clean up client connectors, server connectors, registries, and listeners under their proper owners.
- Never invoke dangerous operations against production.
- Do not catch and swallow all exceptions.
- Distinguish transport, auth, metadata, and business errors.
- Log failures by stage: connect, lookup, authentication, `getMBeanInfo`, attribute, and invoke.
- If injecting network faults, roll back network policies cleanly after the test.

## 19. Design Review Checklist

- [ ] Local `MBeanServer` registers the right ObjectName.
- [ ] `MBeanInfo` contains the right attributes/operations/signatures.
- [ ] Local `getAttribute`/`invoke` work.
- [ ] `MBeanProxyFactoryBean` returns the expected `proxyInterface`.
- [ ] Server-side AOP proxies do not lose the management API.
- [ ] Remote connector attaches to the right server.
- [ ] RMI Registry and endpoint host/port are reachable.
- [ ] TLS/auth/authorization are tested.
- [ ] Network failures are classified and do not retry infinitely.
- [ ] Invoke timeouts handle uncertain outcomes/idempotency.
- [ ] Reconnect/redeploy does not leave stale connections.
- [ ] Notifications have a re-registration policy.
- [ ] Local/remote metadata are contract-equivalent.
- [ ] Concurrency/performance tests exist under realistic workloads.
- [ ] All fixture resources are cleaned up.

## 20. Key Takeaways

**Evaluating Spring JMX requires testing across local, proxy, remote, and controlled fault injection.** Local tests verify the MBean contract; proxy tests verify typed Java call mapping; remote tests verify connectivity, RMI/TLS, and security; network failure tests verify timeouts/reconnects and protections for side-effecting operations. Use the same intended ObjectName/`MBeanServer`, classify errors at the right layer, and test lifecycle to catch issues that otherwise only surface in production.
