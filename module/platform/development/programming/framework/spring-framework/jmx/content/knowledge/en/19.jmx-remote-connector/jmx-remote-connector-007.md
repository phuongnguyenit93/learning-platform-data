# Latency, Timeouts, and Network Errors When Invoking Operations Over a Remote JMX Connector

## 1. Objectives and Context

When a Spring Framework application exports MBeans using JMX, a local client can invoke operations via \`MBeanServer.invoke(...)\`. With a **remote connector**, the client typically uses \`JMXConnector\` and \`MBeanServerConnection\` to send the call over the network. At that point, whether the operation succeeds or fails depends not only on business logic, but also on latency, DNS, TLS, authentication, RMI, firewalls, timeouts, and JVM lifecycle.

Example:

\`\`\`java
Object result = connection.invoke(
    new ObjectName("com.example:type=Queue,name=Orders"),
    "drain",
    new Object[0],
    new String[0]
);
\`\`\`

If the call loses connection mid-flight, the client may receive an \`IOException\` while **the operation already executed on the server**. This is the most critical issue: a transport error is not sufficient to claim the call had no effect.

After this lesson, you will be able to:

1. Distinguish connection wait time, operation execution time, and response retrieval time.
2. Trace the path of an \`invoke\` call over JMX/RMI.
3. Identify errors from the network, TLS, authorization, lookup, and MBean exceptions.
4. Understand the limitations of timeout settings in JMX/RMI clients.
5. Avoid blindly retrying non-idempotent operations.
6. Design asynchronous operations with an \`operationId\`, status, and result reconciliation capability.
7. Build tests for network errors and monitor latency layer by layer.

## 2. Where Does a Remote Operation Call Pass Through?

\`\`\`text
JMX Client
   |
   | JMXConnectorFactory.connect(serviceUrl, env)
   v
JMX/RMI connector client
   |
   +-- DNS / network route / TCP
   +-- TLS & authentication (if configured)
   +-- RMI registry lookup / connector stub
   |
   v
Remote JMX Connector Server
   |
   v
MBeanServerConnection.invoke(...)
   |
   v
MBeanServer
   |
   +-- look up ObjectName
   +-- resolve operation/signature
   +-- check permissions per configuration
   |
   v
Spring-exported MBean / managed bean
   |
   +-- business operation
   |
   v
Return value or exception
   |
   v
RMI serialization / network response
   |
   v
Client
\`\`\`

The time observed by the client consists of several parts:

\`\`\`text
T_client = T_dispatch_client
         + T_network_request
         + T_server_queue
         + T_operation
         + T_serialization
         + T_network_response
         + T_client_decode
\`\`\`

This is a mental model, not an exact measurement formula: components can overlap or be affected by reconnection, GC, and thread scheduling.

**Important:** \`JMXConnectorFactory.connect\` duration is not the same as \`connection.invoke\` duration. A successful connection does not prove operations will be fast or able to complete.

## 3. Distinguishing Latency, Timeouts, and Network Errors

| Concept | Symptom | Meaning |
|---|---|---|
| Connection latency | Slow to connect | DNS, TCP, TLS, RMI registry, authentication |
| Invocation latency | Slow when calling operation | Network, server dispatch, locks, business logic, GC |
| Connection timeout | Cannot establish connection within limit | Client could not connect; operation was not called over this connection |
| Read/response timeout | Waiting too long for response | Uncertain how far server execution progressed |
| Network disconnect | Active connection drops | Invocation outcome may be indeterminate |
| Server-side timeout | Logic or application layer limits duration itself | Implementation-dependent; no default deadline exists for all MBean operations |
| Business exception | MBean actively reports failure | May be wrapped by JMX in \`MBeanException\` or \`RuntimeMBeanException\` |

An operation can finish successfully after the client has run out of patience or lost connection. Therefore, a client-side wait timeout **is not a guaranteed operation cancellation mechanism**.

## 4. Remote JMX Using JMXConnector

Java client example:

\`\`\`java
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

public final class RemoteInvokeDemo {
    public static void main(String[] args) throws Exception {
        JMXServiceURL url = new JMXServiceURL(
            "service:jmx:rmi:///jndi/rmi://jmx.internal.example:9010/jmxrmi");

        try (JMXConnector connector =
                 JMXConnectorFactory.connect(url)) {

            MBeanServerConnection connection =
                connector.getMBeanServerConnection();

            ObjectName name = new ObjectName(
                "com.example:type=Queue,name=Orders");

            Object result = connection.invoke(
                name, "getDrainStatus",
                new Object[0], new String[0]);

            System.out.println(result);
        }
    }
}
\`\`\`

This example only illustrates the **client path**; it does not configure authentication/TLS itself. In real environments, never connect to an unprotected management endpoint. Supply the connection environment and trust/auth configuration appropriate for the connector in use.

JMX/RMI may involve two steps: looking up the connector via the RMI registry and connecting to the remote object using information in the stub. A firewall that allows the registry port yet blocks the RMI server port can still cause calls to fail.

## 5. When Does Latency Increase?

### 5.1. Network Latency

- Geographic distance or multi-hop network paths.
- Packet loss causing retransmissions.
- Multi-layered VPNs/tunnels or gateways.
- Slow DNS lookup or failover.
- NAT/firewalls managing connection state.

### 5.2. JVM and MBeanServer Latency

- Garbage collection or safepoints.
- CPU contention.
- Connector/thread pool waiting to serve requests.
- MBean implementation holding locks or waiting on I/O.
- Operation querying a database or calling another service.
- Serializing an overly large return value.

### 5.3. Management Tool Latency

- Client calling \`getMBeanInfo\` before \`invoke\`.
- Client polling many attributes sequentially.
- JConsole or monitoring agents opening multiple connections.
- JMX proxies issuing extra metadata lookups depending on configuration.

Do not conclude "the network is slow" merely because total \`invoke\` time is high. Separate connection time, network time, and server-side logic execution time.

## 6. Timeouts in JMX/RMI: No Single Button Fits Every Case

The JMX API \`MBeanServerConnection.invoke\` does not directly accept a \`Duration timeout\` parameter:

\`\`\`java
Object invoke(
    ObjectName name,
    String operationName,
    Object[] params,
    String[] signature)
    throws ...
\`\`\`

Thus, when a deadline is needed, consider:

1. Which protocol the JMX connector uses.
2. Which timeout settings the RMI implementation/JDK provides.
3. Whether networks/proxies/load balancers impose their own timeouts.
4. Whether the client configures a timeout at a wrapper or executor layer.
5. Whether the server operation supports deadlines/cancellation/idempotency.

Some RMI/JDK options like \`sun.rmi.transport.tcp.responseTimeout\` or \`sun.rmi.transport.connectionTimeout\` exist in certain implementations, but these are **implementation-specific options**, not standard guarantees of the JMX API. Names, scopes, support, and semantics may vary by JDK. Check the documentation for your running JDK and test end-to-end; do not rely on an implicit property for critical systems.

### 6.1. Do Not Confuse Connect Timeout with Invoke Timeout

A client can connect quickly:

\`\`\`text
connect: 120 ms
invoke : 45 seconds
\`\`\`

If a business operation waits 45 seconds on a database, increasing the connect timeout will not solve it. Analyze the operation itself, resource limits, and asynchronous approaches.

### 6.2. Java Future Timeouts Have Limits

For example, to prevent the caller from waiting too long:

\`\`\`java
ExecutorService executor = Executors.newSingleThreadExecutor();

try {
    Future<Object> task = executor.submit(
        () -> connection.invoke(
            name, "longRunningOperation",
            new Object[0], new String[0]));

    Object result = task.get(5, TimeUnit.SECONDS);

} catch (TimeoutException timeout) {
    // Client stopped waiting for result.
} finally {
    executor.shutdownNow();
}
\`\`\`

This is only a **client-side waiting deadline**. \`Future.cancel(true)\` or \`shutdownNow()\` does not guarantee the JMX/RMI call is aborted immediately, let alone that the server operation stops. The thread may remain blocked until the transport or server finishes. For high call volumes, manage executor capacity and avoid unbounded thread creation.

## 7. IOException and Uncertain Execution State

Scenario:

\`\`\`text
T0: Client sends drain() over JMX
T1: Server receives request
T2: Server begins draining queue
T3: Server completes drain
T4: Network connection drops before response
T5: Client receives IOException
\`\`\`

The client sees an error, yet the server completed the operation.

Another scenario:

\`\`\`text
T0: Client prepares to send drain()
T1: Connection drops
T2: Server never receives request
T3: Client receives IOException
\`\`\`

Both cases can appear identically as transport errors. Therefore:

**Do not retry an operation with side effects based solely on \`IOException\` or timeout.**

This is especially dangerous for:

- Batch cache clearing or invalidation.
- Restarting/shutting down workers.
- Rotating credentials.
- Replaying/consuming messages.
- Adjusting quotas or workflow states.
- Configuration changes with non-idempotent effects.

Even seemingly idempotent actions need well-defined semantics and clear impact on downstream systems.

## 8. Idempotency and operationId

One resilient management API design provides a request identifier:

\`\`\`text
startDrain(operationId: String) -> accepted: boolean
getDrainStatus(operationId: String) -> status
\`\`\`

If the client resends the same \`operationId\`, the server does not start the task a second time. This requires the server to retain state long enough and handle concurrency safely.

Model:

\`\`\`text
Client creates opId = "drain-2026-11-11-001"
         |
         v
invoke startDrain(opId)
         |
         +-- response received -> poll status
         |
         +-- timeout / IOException
                 |
                 v
             query getDrainStatus(opId)
                 |
          +------+------+
          |             |
       Found          Not found
          |             |
      Observe       Retry policy
      result        only if safe
\`\`\`

**Do not deduce from "not found" that the request definitely never ran**, especially if state is stored non-durably or has replication lag. Define retention, consistency, and duplicate handling.

### 8.1. Task States

A model might include:

\`\`\`text
UNKNOWN
ACCEPTED
RUNNING
SUCCEEDED
FAILED
CANCEL_REQUESTED
CANCELLED
\`\`\`

\`UNKNOWN\` is a **client-observed** state, not necessarily an internal server state. \`CANCEL_REQUESTED\` does not mean cancellation has already succeeded.

## 9. Designing Asynchronous Operations Instead of Long Calls

A synchronous JMX operation waits until the method returns. If an action takes minutes, holding a connection open risks timeouts and makes cancellation hard to manage.

Instead of:

\`\`\`java
@ManagedOperation
public void rebuildIndex() {
    expensiveRebuild();
}
\`\`\`

you can design:

\`\`\`java
@ManagedOperation
public String startRebuild() {
    String jobId = java.util.UUID.randomUUID().toString();
    executor.submit(() -> rebuild(jobId));
    return jobId;
}

@ManagedOperation
public String getRebuildStatus(String jobId) {
    return statusStore.getOrDefault(jobId, "UNKNOWN");
}
\`\`\`

This is structural pseudocode: \`executor\`, \`rebuild\`, and \`statusStore\` must be properly defined with real lifecycle, concurrency, error, and retention management.

Advantages:

- The initiation call returns quickly.
- Returns a \`jobId\` for reconciliation.
- Client tracks progress via operations/attributes.
- Reduces the risk of a client holding an RMI call for minutes.
- Enables controlled cancellation semantics.

However, if the response containing \`jobId\` is lost, the client still faces uncertainty. For safe retries, it is better to let the **client supply the operationId** rather than generating the ID solely on the server.

## 10. Classifying Exceptions When Calling Remote Operations

| Exception | Usually Suggests | Handling |
|---|---|---|
| \`InstanceNotFoundException\` | Wrong ObjectName or MBean unregistered | Query MBeans, check lifecycle/server |
| \`ReflectionException\` | Operation/signature mismatch | Read \`MBeanInfo.getOperations()\` |
| \`MBeanException\` | Checked exception returned by MBean/adapter | Inspect target exception, handle business error |
| \`RuntimeMBeanException\` | Runtime exception in MBean path | Inspect cause, check server logs |
| \`SecurityException\` | Insufficient permissions | Check policy/auth, never bypass |
| \`IOException\` | Transport/connector failure | Determine operation state before retrying |
| \`RuntimeErrorException\` | Java \`Error\` from MBean path | Alert on critical failure |
| \`ClassNotFoundException\` in deserialize/codec path | Data type unavailable on client | Check classpath, use Open Types where appropriate |

Wrappers and error details vary by MBean implementation, client, and connector. A client-side \`IOException\` is not conclusive proof of server state.

### 10.1. Client Exception-Branching Example

\`\`\`java
try {
    connection.invoke(
        name, "startDrain",
        new Object[]{"op-123"},
        new String[]{String.class.getName()});

} catch (InstanceNotFoundException ex) {
    // Wrong ObjectName or context lifecycle change.

} catch (ReflectionException ex) {
    // Wrong name/signature, inspect MBeanInfo.

} catch (MBeanException ex) {
    Throwable target = ex.getTargetException();
    // Operation failure reported by MBean.

} catch (RuntimeMBeanException ex) {
    Throwable target = ex.getTargetException();
    // Runtime failure reported through JMX.

} catch (SecurityException ex) {
    // Permission denied; do not retry with bypass.

} catch (IOException ex) {
    // Execution outcome may be unknown.
    // Reconcile using operationId/status when supported.
}
\`\`\`

In a real system, never swallow exceptions as in the snippet above. Emit structured logs, handle outcome states, and return safe operational feedback.

## 11. JMX/RMI: Registry Port, Connector Port, and Hostname

Remote JMX/RMI may involve:

\`\`\`text
Client -> RMI registry port -> connector stub
                                   |
                                   v
                             RMI server port
                                   |
                                   v
                               MBeanServer
\`\`\`

A URL such as:

\`\`\`text
service:jmx:rmi:///jndi/rmi://jmx.internal.example:9010/jmxrmi
\`\`\`

may indicate the registry lookup, while the RMI stub may contain a different host/port. Some JVM configurations use:

\`\`\`text
-Dcom.sun.management.jmxremote.port=9010
-Dcom.sun.management.jmxremote.rmi.port=9011
-Djava.rmi.server.hostname=jmx.internal.example
\`\`\`

This is an endpoint configuration example, **not a complete production configuration**. Authentication, TLS, firewalls, and authorization are still required per JDK and environment. Never enable unauthenticated remote JMX on a public network.

If the client reaches the registry yet \`invoke\` times out or fails to connect, check:

1. Which hostname the RMI stub advertises.
2. Whether the client resolves that hostname correctly.
3. Whether the RMI server port is permitted by the firewall.
4. Whether DNS/NAT/VPN alters the route.
5. Whether TLS and authentication are consistent.
6. Whether the server is overloaded or closing the connector.

## 12. Measuring Latency More Accurately

### 12.1. Measuring on the Client

\`\`\`java
long started = System.nanoTime();

try {
    connection.invoke(
        name, "getDrainStatus",
        new Object[0], new String[0]);
} finally {
    long elapsedNanos = System.nanoTime() - started;
    System.out.printf(
        "JMX invoke latency: %.2f ms%n",
        elapsedNanos / 1_000_000.0);
}
\`\`\`

\`System.nanoTime()\` is suitable for measuring relative elapsed time, not absolute timestamps. Log the operation name, normalized ObjectName, outcome (success/error), and correlation ID if available.

### 12.2. Measuring on the Server

Inside a managed operation, measure business processing time:

\`\`\`java
@ManagedOperation
public void refreshIndex() {
    long started = System.nanoTime();
    try {
        indexService.refresh();
    } finally {
        long elapsed = System.nanoTime() - started;
        metrics.recordRefreshDuration(elapsed);
    }
}
\`\`\`

\`indexService\` and \`metrics\` are illustrative dependencies. If the client measures 20 seconds while the server operation measures 50 ms, the problem likely lies outside business logic (network, queueing, serialization, connector). If both are slow, prioritize investigating server logic and resources.

### 12.3. Measuring Distributions Instead of a Single Sample

An average hides tail latency. For high-volume callers, track:

- Success/failure call counts.
- P50/P95/P99 latency given enough samples.
- Timeout/network disconnect counts.
- Connect time and invoke time separately.
- Active MBean operations and queue depths.
- Retry rates and reconciliation outcomes.

Never attach secrets or sensitive parameters to metric labels, logs, or ObjectNames.

## 13. Circuit Breaker, Retry, and Backoff

Common resilience patterns applied at the client layer:

**Timeout budget:** caps how long a workflow waits, though it does not cancel the server invocation automatically.

**Conditional retry:** retry only when an operation is defined as idempotent or guarantees operationId/deduplication.

**Exponential backoff:** reduces pressure when the connector/server is temporarily overloaded.

**Circuit breaker:** stops sending requests to a repeatedly failing endpoint, preventing extra load.

**Bulkhead:** limits concurrent slow JMX calls so they do not exhaust the client application's thread pool.

For management operations with side effects, classify them carefully:

| Operation | Auto-Retryable? | Reason |
|---|---|---|
| \`getStatus()\` | Usually yes with an appropriate policy | Primarily read-only |
| \`getQueueSize()\` | Usually yes | No expected side effects |
| \`setEnabled(true)\` | Conditionally | Idempotent if semantics match and no repeated side effects trigger |
| \`startJob(operationId)\` | Yes if server deduplicates properly | Same ID does not create a duplicate job |
| \`restart()\` | Do not retry blindly | Could trigger repeated restarts |
| \`drain()\` | Do not retry blindly | Could mutate state multiple times |
| \`rotateCredentials()\` | Do not retry blindly | Security impact and indeterminate state |

Never treat \`IOException\` as an automatic retry signal for every operation.

## 14. Testing Network Errors and Timeouts

A remote JMX integration test should use a lab environment, an isolated connector, and an MBean with controlled side effects.

### 14.1. Scenarios to Test

1. **Server not running:** client connection fails.
2. **Wrong hostname:** DNS or network failure.
3. **Wrong RMI port:** registry lookup succeeds, but connector handshake fails.
4. **Slow operation:** server sleeps in a controlled manner to measure latency.
5. **Disconnect before request:** invocation never reaches the server.
6. **Disconnect after request but before response:** client does not know the outcome state.
7. **Server restart:** ObjectName may require rediscovery.
8. **Authorization denied:** distinguish security failure from transport failure.
9. **Operation throws:** \`MBeanException\` or \`RuntimeMBeanException\`, not timeout.
10. **Concurrent requests:** test thread pool saturation and queueing.

Never intentionally sever production networks or run destructive operations for testing. Use an isolated test service and operations like incrementing a counter in a fixture.

### 14.2. Testing "At Most Once" Using operationId

Create \`startTask(String id)\` in the MBean backed by a concurrent map:

\`\`\`java
private final ConcurrentMap<String, String> states =
    new ConcurrentHashMap<>();

public String startTask(String id) {
    return states.computeIfAbsent(id, key -> {
        executor.submit(() -> runTask(key));
        return "ACCEPTED";
    });
}
\`\`\`

This is a starter model, not a complete production implementation. You must handle races, task submission failures, status updates, retention, restart/persistence, and atomicity of deduplication if strong guarantees are needed. If \`executor.submit\` throws inside the mapping function, the entry might not be stored. If the task finishes too quickly, writing \`ACCEPTED\` could overwrite a newer status; separate state tracking and submission carefully.

A test should send the same ID multiple times and verify the actual task runs only once. Then simulate response loss to verify the client can use the ID to query status.

## 15. Relationship to Spring Framework JMX

Spring supports exporting beans via \`MBeanExporter\`, \`@ManagedResource\`, and \`@ManagedOperation\`. This does not alter remote transport semantics.

Example:

\`\`\`java
@Component
@ManagedResource(
    objectName = "training.remote:type=Maintenance,name=Primary")
public class MaintenanceControl {

    @ManagedOperation
    public String startReindex(String requestId) {
        return maintenanceService.startIdempotent(requestId);
    }
}
\`\`\`

The MBean is exported by Spring into the \`MBeanServer\`. Remote clients need a \`JMXConnectorServer\` or management agent connected to that server. You can use Spring's \`ConnectorServerFactoryBean\` when configuring a connector, while managing networking, authentication, and TLS appropriately.

### 15.1. MBeanExporter Does Not Control Network Timeouts

\`MBeanExporter\` is only responsible for registering MBeans and metadata/exposure. It is not the component controlling packet loss, socket timeouts, or the RMI registry. To diagnose slow remote calls, inspect the connector/client and the operation implementation rather than just tweaking the exporter.

### 15.2. Local Proxy and Remote Proxy

\`MBeanProxyFactoryBean\` can provide a client-side Java interface. When the proxy uses a local MBeanServer, there is no network transport. When the proxy uses remote JMX, the same \`startReindex\` method can throw connector/network exceptions. A friendly wrapper interface does not eliminate timeouts or indeterminate outcomes.

## 16. A Layered Troubleshooting Process

When \`invoke\` times out or throws an error:

**Step 1 — Verify endpoint:** service URL, hostname, registry port, connector port, DNS, and routing.

**Step 2 — Verify TLS/auth:** certificates, truststore, credentials, access policy, and operation permissions.

**Step 3 — Verify MBean:** use \`queryNames\`, \`isRegistered\`, \`getMBeanInfo\`; check ObjectName and operation signature.

**Step 4 — Verify client latency:** separate connect from invoke, record timings and exception classes.

**Step 5 — Verify server execution:** inspect logs/correlation IDs, operation duration, and task status.

**Step 6 — Verify outcome:** if the client timed out after the request may have been sent, query status before deciding to retry.

**Step 7 — Improve design:** use asynchronous operations, operationId, deduplication, deadlines, and monitoring where needed.

Quick diagnostic table:

| Symptom | Likely Cause | Evidence |
|---|---|---|
| Connect timeout | DNS, TCP, firewall, RMI endpoint | Connector logs, network path |
| Connect OK but invoke is slow | Business logic, GC, server queue | Server execution timing |
| Registry reachable, client still fails | Wrong RMI stub host/port | RMI configuration |
| Invoke \`IOException\` after a few seconds | Disconnect or lost response | Reconcile status via request ID |
| Invoke \`ReflectionException\` | Wrong name/signature | \`MBeanInfo\` |
| Invoke \`InstanceNotFoundException\` | Wrong server/ObjectName or unregistered | \`queryNames\` |
| Invoke \`SecurityException\` | Missing permissions | Access logs and policy |
| Operation completed yet client timed out | Response path failed/slow | Correlation ID + server status |

## 17. Practice Exercises

### Exercise A — Measuring Local and Remote Latency

Create an MBean with a \`ping()\` operation returning a short string, then invoke it via a local MBeanServer and a lab JMXConnector. Measure P50/P95 over many runs. Explain why remote calls typically add connection and serialization overhead.

### Exercise B — Slow Operation

Create a \`sleepFor(long millis)\` operation only in the lab. Use a 2-second client wait deadline while the operation sleeps for 5 seconds. Observe that the client stopping its wait does not prove the server method stopped. Never use this operation in production.

### Exercise C — Disconnection

Use a counter operation accepting a request ID. Simulate disconnecting right after sending the request; verify how the client reconciles status instead of incrementing the counter a second time.

### Exercise D — RMI Ports

Configure a lab environment with fixed registry and RMI server ports. Test cases where the registry port is open while the server port is blocked; record the client errors. Deploy only in an authorized test network.

### Exercise E — Classifying Exceptions

Call a wrong operation name, a wrong ObjectName, and an operation that throws \`IllegalStateException\` in turn. Write a client distinguishing \`ReflectionException\`, \`InstanceNotFoundException\`, and \`RuntimeMBeanException\`. Add a disconnected connector case to observe how \`IOException\` differs from business errors.

### Exercise F — Start/Status Design

Convert a 30-second operation into \`startJob(id)\` and \`getJobStatus(id)\`. Write a test invoking repeatedly with the same ID and verify the side effect executes only once; add a retention and recovery policy for server restarts.

## 18. Self-Check Questions

1. How does a \`JMXConnectorFactory.connect\` timeout differ from an \`MBeanServerConnection.invoke\` timeout?
2. Why does \`IOException\` not prove the server operation never ran?
3. Which network endpoints might a remote JMX/RMI call require?
4. Does \`Future.get(timeout)\` cancel an MBean operation on the server?
5. When can an operation be safely retried?
6. How does \`operationId\` help handle duplicate requests?
7. Why should long-running operations expose a start/status API?
8. What factors can make total invoke latency high even when business logic is fast?
9. Does \`MBeanExporter\` control network timeouts?
10. Why must a client distinguish JMX exceptions from transport exceptions?

## 19. References

- Java SE 21 — \`MBeanServerConnection\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerConnection.html
- Java SE 21 — \`JMXConnectorFactory\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/remote/JMXConnectorFactory.html
- Java SE 21 — \`JMXConnector\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/remote/JMXConnector.html
- Java SE 21 — \`JMXServiceURL\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/remote/JMXServiceURL.html
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html

**Key takeaway:** remote JMX \`invoke\` is a call over the network, not a local method call with a guaranteed response. Timeouts or \`IOException\` can leave an indeterminate outcome. Separate connection latency from processing time, observe via correlation IDs, design operations to be safe on repetition, and **never blindly retry when side effects exist**.
