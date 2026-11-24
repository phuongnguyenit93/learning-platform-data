# Authorizing Attribute Reads and Operation Invocations in Spring Framework JMX

## 1. Learning Objectives

After this lesson, you will be able to:

- Distinguish **authentication**, **authorization**, and **transport security** in JMX.
- Understand the difference between attribute read permission, attribute write permission, and operation invocation permission for an MBean.
- Know the limits and capabilities of **readonly/readwrite** permissions in the JDK remote JMX access file; avoid confusing those levels with fine-grained per-method RBAC.
- Design administrative MBeans with a small surface area, separating high-impact operations from observability metrics.
- Understand that **\`@ManagedAttribute\`**, **\`@ManagedOperation\`**, and Spring \`MBeanExporter\` only describe/export management capabilities and do not automatically enforce per-user permissions.
- Explore authorization enforcement points at the **remote connector**, **MBeanServer layer**, **application/service layer**, and network layer.
- Know how to write integration tests to verify that a read-only account cannot perform state-mutating operations.
- Deliberately handle multi-user scenarios, local JMX, internal proxies, Actuator, and JVM/container security.

## 2. The Big Picture: Securing an MBean

JMX (Java Management Extensions) provides an interface to observe and control the JVM or application via **MBeans**. An MBean can expose:

- **Attributes**: name, type, readable/writable flags; for example \`QueueDepth\`, \`Running\`, \`MaxWorkers\`.
- **Operations**: name, signature, return type, and metadata; for example \`requestPause()\`, \`clearCache()\`, \`reloadConfiguration()\`.
- **Notifications**: events that clients can subscribe to, if supported by the implementation.
- **Descriptors**: additional metadata.

In terms of risk, not all permissions are equal:

\`\`\`text
JMX client / operator
          |
          v
Authentication: who is connecting?
          |
          v
Authorization: what is allowed?
          |
          +--> Query MBean metadata
          +--> Read attribute
          +--> Write attribute
          +--> Invoke operation
          +--> Register / unregister MBean
          +--> Subscribe notification
          |
          v
MBeanServer / target MBean
          |
          v
Java application / JVM state
\`\`\`

Someone permitted to view \`QueueDepth\` should not necessarily be permitted to invoke \`clearQueue()\`. Someone permitted to adjust \`MaxWorkers\` should not necessarily be permitted to call \`shutdown()\`.

Definitions of **read-only** and **read-write** must be tied to **the enforcement mechanism in use**. JMX does not automatically infer business roles from operation names or from \`MBeanOperationInfo.getImpact()\`.

## 3. Security Layers to Distinguish

| Layer | Role | Examples |
| --- | --- | --- |
| Network boundary | Reduce the scope of machines that can connect | Firewall, VPN, private network, tunnel |
| Transport security | Prevent eavesdropping/tampering in transit | TLS for the JMX connector |
| Authentication | Verify the client's identity | Password file, JAAS, or custom connector |
| Connector authorization | Specify which groups of actions are allowed | JDK access file \`readonly\`/\`readwrite\` |
| MBeanServer authorization | Control commands at the server layer | \`MBeanServerForwarder\` or custom interceptor |
| Business authorization | Check business permissions at execution time | Permission check in service |
| Audit | Trace administrative actions | Log actor, ObjectName, action, result |

These layers complement each other; they do not replace each other.

For example, TLS protects data in transit, but does not decide whether a user is allowed to clear a cache. A password file authenticates users, but does not by default implement complex per-\`ObjectName\` policies.

## 4. Read Attribute, Write Attribute, and Invoke Operation

### 4.1. Reading an Attribute

\`\`\`java
Object value = connection.getAttribute(
    objectName,
    "QueueDepth"
);
\`\`\`

This call usually reads information. However, getters are real Java code; if a getter is written with side effects or causes heavy load, even a “read” operation can affect the system.

Therefore, design JMX getters so they:

- Do not unexpectedly update business state.
- Do not expose secrets or personal data.
- Do not execute expensive queries on every poll unless necessary.
- Have clear freshness/caching semantics.

### 4.2. Writing an Attribute

\`\`\`java
import javax.management.Attribute;

connection.setAttribute(
    objectName,
    new Attribute("MaxWorkers", 8)
);
\`\`\`

This call changes configuration or state when the MBean allows a writable attribute.

Even when connector permission is readwrite, the application still needs to validate values: \`MaxWorkers=1000000\` could exhaust resources. Action permission and validation are two separate responsibilities.

### 4.3. Invoking an Operation

\`\`\`java
connection.invoke(
    objectName,
    "requestPause",
    new Object[0],
    new String[0]
);
\`\`\`

An operation may merely return data, or it may perform a critical action. **Never infer that an \`INFO\` operation is completely safe, or that an \`ACTION\` operation is automatically protected**. Impact is metadata, not an authorization rule.

### 4.4. Other Actions

Highly privileged clients may perform actions such as \`createMBean\`, \`registerMBean\`, \`unregisterMBean\`, or subscribing to notifications depending on the implementation and policy. Therefore, controls must cover more than just \`getAttribute\` and \`invoke\`.

## 5. Spring @ManagedAttribute and @ManagedOperation Are Not Authorization

Spring example:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.orders:type=Queue,name=Primary",
    description = "Queue administration"
)
public class QueueManagement {

    private volatile int maxWorkers = 8;

    @ManagedAttribute(description = "Current worker limit")
    public int getMaxWorkers() {
        return maxWorkers;
    }

    @ManagedAttribute(description = "Update worker limit")
    public void setMaxWorkers(int maxWorkers) {
        if (maxWorkers < 1 || maxWorkers > 64) {
            throw new IllegalArgumentException(
                "maxWorkers must be between 1 and 64"
            );
        }
        this.maxWorkers = maxWorkers;
    }

    @ManagedOperation(description = "Request a graceful queue pause")
    public void requestPause() {
        // Delegates to an application service.
    }
}
\`\`\`

If the Spring JMX exporter is configured properly, clients can see the readable/writable attribute \`MaxWorkers\` and the operation \`requestPause\`.

However:

- \`@ManagedAttribute\` does not attach \`ROLE_VIEWER\`.
- \`@ManagedOperation\` does not attach \`ROLE_OPERATOR\`.
- Description does not require confirmation on invoke.
- \`setMaxWorkers\` validates input bounds; it does not know who is calling.
- Enabling \`spring.jmx.enabled=true\` does not automatically create per-user authorization.

To enforce authorization, you need an actual security boundary at the connector, server, or service.

## 6. Authentication and Authorization in JDK Remote JMX

The HotSpot/OpenJDK management agent supports remote JMX with a password file and an access file in supported configurations.

Common properties:

\`\`\`text
-Dcom.sun.management.jmxremote
-Dcom.sun.management.jmxremote.port=9010
-Dcom.sun.management.jmxremote.rmi.port=9010
-Dcom.sun.management.jmxremote.authenticate=true
-Dcom.sun.management.jmxremote.ssl=true
-Dcom.sun.management.jmxremote.password.file=/secure/jmxremote.password
-Dcom.sun.management.jmxremote.access.file=/secure/jmxremote.access
\`\`\`

This is an example illustrating property orientation, not a complete TLS configuration. When deploying, configure certificates/keystore/truststore and the RMI advertised hostname for your specific infrastructure.

### 6.1. Password File

A JMX agent password file typically contains identities and passwords in the format supported by the JDK:

\`\`\`text
monitorRole CHANGE_ME_FROM_SECRET_STORE
controlRole CHANGE_ME_FROM_SECRET_STORE
\`\`\`

The strings above are illustrative only; do not use these literals as real credentials. In production, retrieve secrets from a protected source and restrict filesystem permissions according to JDK/OS rules.

On some platforms/JDKs, the password file has strict permission requirements. If the file is readable by other users, the agent may refuse to start. Do not fix that by loosening file permissions.

### 6.2. Access File: readonly and readwrite

Example access file:

\`\`\`text
monitorRole readonly
controlRole readwrite
\`\`\`

Intent:

- **monitorRole** has read/observation access within the scope permitted by the JDK agent mechanism.
- **controlRole** has permission to perform mutating actions, including invoking operations within the allowed scope.

This is **coarse-grained authorization**, not a custom matrix like “role A can only call \`refreshCache\`, role B can only call \`pauseWorker\`”.

When role-specific per-operation authorization is needed, consider a server forwarder or another security design.

### 6.3. Limitations of readwrite

A \`readwrite\` user is not automatically restricted to only specific methods annotated with \`@ManagedOperation\` by the application. If the client is allowed to invoke MBean operations and policy does not forbid it, the operation can run.

Some JDK access file syntaxes support optional restrictions such as \`create\` or \`unregister\` for MBean management actions, depending on the JDK/version. That is still not a fine-grained RBAC system for every method; consult the corresponding JDK documentation.

**Do not share a single readwrite account across all dashboards or monitoring collectors** if those systems only need to read metrics.

## 7. Does Readonly Allow Calling Read-Only Operations?

This is an easily misunderstood question.

In the JDK management agent access control mechanism, **\`readonly\` should not be understood as allowing invocation of every operation named \`getSomething\` or having impact \`INFO\`**. Invoke permission is typically treated as a separately controlled administrative action, not classified by the operation's business logic.

Therefore, when designing an API for read-only monitoring clients:

- Prefer readable **attributes** for retrieving state.
- Do not require monitoring collectors to invoke a custom operation just to fetch a simple metric.
- If parameterized data queries are needed, determine whether connector policy permits invoke; do not assume permission from \`INFO\`.
- Test in practice with the readonly account of the connector/JDK in use.

An MBean with a business-wise read-only \`calculateSummary()\` method may still fail to be invoked by a readonly account if policy forbids invoke. That is security boundary behavior, not a Spring exporter bug.

## 8. Why MBeanInfo.isWritable Is Not User Permission

\`MBeanAttributeInfo.isWritable()\` returns **MBean structural information**: whether the attribute has a setter or is defined as writable in its contract.

For example:

\`\`\`java
MBeanInfo info = connection.getMBeanInfo(objectName);

for (var a : info.getAttributes()) {
    System.out.printf(
        "%s readable=%s writable=%s%n",
        a.getName(),
        a.isReadable(),
        a.isWritable()
    );
}
\`\`\`

If \`isWritable=true\`, you can only conclude that the MBean **declares write capability** for the attribute. It does not mean the current caller has sufficient permission for \`setAttribute\`.

Similarly, \`MBeanInfo.getOperations()\` lists declared operations, not the list of operations a specific user is permitted to invoke.

These are two independent checking layers:

\`\`\`text
MBeanInfo: does the operation exist?
    |
    v
Authorization policy: is the caller allowed to invoke it?
    |
    v
Business validation: are the value/state valid?
    |
    v
Operation actually runs
\`\`\`

Do not use MBeanInfo as a substitute for authorization tests.

## 9. Spring Boot and JMX Security

In Spring Boot, management properties such as:

\`\`\`properties
spring.jmx.enabled=true
management.endpoints.jmx.exposure.include=health,info
\`\`\`

govern MBean export or exposure of Actuator JMX endpoints, not a full role-based authorization system for all operations.

In particular, distinguish:

- **Spring Security web filters** protect HTTP requests.
- **JMX/RMI connector** accepts JMX clients over the management protocol.
- **MBeanServer** dispatches JMX APIs.
- **Spring JMX exporter** exposes MBeans from selected beans.

**HTTP security configuration does not automatically protect the JMX connector.** For instance, requiring authentication on \`/actuator/**\` over HTTP does not mean JConsole will go through the same Spring Security chain.

If a JMX operation needs to know the authenticated user, design a reliable mechanism to propagate identity from the connector to the authorization layer. Do not assume an HTTP request's SecurityContext exists on a JMX thread.

## 10. Local JMX and Remote JMX Have Different Trust Models

### 10.1. Local MBeanServer

Code in the same JVM can obtain the platform MBeanServer:

\`\`\`java
MBeanServer server =
    java.lang.management.ManagementFactory
        .getPlatformMBeanServer();
\`\`\`

Then invoke:

\`\`\`java
server.invoke(name, "requestPause",
    new Object[0], new String[0]);
\`\`\`

A local call does not go through the **remote connector's** password/access file authentication. If code inside the application holds a reference to \`MBeanServer\`, connector policy is not a barrier for that code.

Therefore, do not treat \`jmxremote.access\` as a way to guard against every in-process Java caller.

### 10.2. Local Attach with JConsole

JConsole local attach also has conditions around user, OS permissions, and the attach mechanism. It is not simply identical to the remote JMX agent with a password file.

In multi-user environments, you must control OS permissions, the account running the application, process attach/debug capabilities, and host/container access policies.

### 10.3. Remote JMX

A remote connector adds:

- Authentication.
- TLS/network encryption.
- Authorization layer.
- Firewall/network restrictions.
- Auditing and connection lifecycle.

These layers must be designed together, not based solely on whether MBeans are annotated as “read-only”.

## 11. Designing Separate MBeans for Monitoring and Control

An easier-to-govern architecture separates observation from control.

\`\`\`text
com.example.orders:type=Queue,name=PrimaryStatus
  Attributes:
    PendingMessages    long (read-only)
    Running            boolean (read-only)
    LastFailureTime    String (read-only)

com.example.orders:type=Queue,name=PrimaryControl
  Operations:
    requestPause()     void
    requestResume()    void
    clearRetryQueue()  int
\`\`\`

Benefits:

- Monitoring collectors only need attributes from the status MBean.
- Side-effecting operations are concentrated in the control MBean.
- Easy to build allowlists/denylists by \`ObjectName\`.
- Easy to log/audit control actions.
- Possible to export the control MBean only in permitted environments or contexts.

However, splitting MBeans **does not create permissions by itself** if the connector still grants readwrite across the entire MBeanServer. To block specific roles, you need enforceable policy such as a custom forwarder, separate connectors with different permissions, or service-level authorization.

### 11.1. Status MBean Example

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.orders:type=Queue,name=PrimaryStatus"
)
public class QueueStatusMBeanAdapter {

    @ManagedAttribute(description = "Current pending message count")
    public long getPendingMessages() {
        return 12L;
    }

    @ManagedAttribute(description = "Whether worker is running")
    public boolean isRunning() {
        return true;
    }
}
\`\`\`

### 11.2. Control MBean Example

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.orders:type=Queue,name=PrimaryControl"
)
public class QueueControlMBeanAdapter {

    private final QueueControlService control;

    public QueueControlMBeanAdapter(QueueControlService control) {
        this.control = control;
    }

    @ManagedOperation(
        description = "Request graceful pause of queue consumers"
    )
    public void requestPause() {
        control.requestPause();
    }
}
\`\`\`

\`QueueControlService\` is an application-defined service. It must enforce authorization and validation where needed; the example above only illustrates surface separation.

## 12. Fine-Grained Authorization via MBeanServerForwarder

The JMX remote API has the **\`MBeanServerForwarder\`** interface in \`javax.management.remote\`. It allows placing a forwarder layer in front of \`MBeanServer\` to intercept and authorize calls from the connector.

Idea:

\`\`\`text
JMX client
    |
    v
JMXConnectorServer
    |
    v
MBeanServerForwarder
    |   \
    |    +--> Identify caller/subject
    |    +--> Check action + ObjectName
    |    +--> Allow / deny
    v
MBeanServer
    |
    v
Target MBean
\`\`\`

An illustrative policy:

\`\`\`text
role=viewer:
    allow getMBeanInfo
    allow queryNames
    allow getAttribute on com.example.orders:type=Queue,name=PrimaryStatus
    deny  setAttribute
    deny  invoke

role=operator:
    allow getAttribute on status MBean
    allow invoke requestPause on PrimaryControl
    deny  invoke clearRetryQueue
    deny  unregisterMBean

role=administrator:
    allow selected management operations
    apply stronger authentication/audit
\`\`\`

This is pseudo-policy to describe the logic, **not standard JDK configuration file syntax**.

### 12.1. What Must Be Protected When Writing a Custom Forwarder?

If implementing authorization at the \`MBeanServerForwarder\` layer, do not only block \`invoke\`:

- \`getAttribute\` and \`getAttributes\`.
- \`setAttribute\` and \`setAttributes\`.
- \`invoke\`.
- \`queryNames\`, \`queryMBeans\`, \`getMBeanInfo\` if metadata is sensitive.
- \`createMBean\`, \`registerMBean\`, \`unregisterMBean\`.
- \`addNotificationListener\`, \`removeNotificationListener\`.
- Operations that can achieve the same effect via another API path.

Watch out for **bulk operations**: a policy that guards \`getAttribute\` but misses \`getAttributes\` can create a bypass. Likewise, blocking an operation while leaving a writable attribute with the same effect still lets a client mutate state.

A forwarder must fail-closed, evaluate policy against the true caller identity, avoid caching permissions across wrong contexts, and never log sensitive data.

### 12.2. Caller Identity and Subject

Remote JMX can associate the authenticated session's \`Subject\` with an invocation via connector/JDK mechanisms. How identity is retrieved and used depends on the auth configuration, Java version, and corresponding security APIs.

Do not write:

\`\`\`java
String user = "admin";
\`\`\`

or trust caller information sent in an operation argument as a reliable identity.

In modern JDK versions, many security APIs and SecurityManager have changed or been removed; when implementing custom authorization, consult documentation for the specific JDK version and test against a real connector rather than relying on outdated examples.

## 13. Enforcing Permissions at the Service Layer

If an administrative operation has major impact, relying only on connector roles may not be enough. For example, the same service method might be called from:

- Remote JMX.
- Local Java code.
- HTTP admin API.
- Message consumer.
- Scheduled job.

If business authorization lives only in the connector forwarder, other call paths can bypass it. You can place permission checks at the service boundary or in a shared application authorization component.

Conceptual example:

\`\`\`java
public interface ManagementAuthorization {
    void requirePermission(String permission);
}
\`\`\`

Service:

\`\`\`java
public void clearRetryQueue() {
    authorization.requirePermission(
        "queue.retry.clear"
    );
    // Execute the controlled action.
}
\`\`\`

However, the \`ManagementAuthorization\` implementation must determine a trustworthy caller. If a JMX operation has no identity propagated from the connector to the service, the service cannot guess who is calling; connector-specific principal mapping, a command gateway, or separate management APIs may be needed.

**Do not pass passwords or admin tokens as ordinary JMX operation parameters** without thoroughly evaluating logging, transport, storage, and access implications.

## 14. Impact Metadata and the Name-Based Authorization Trap

A JMX operation has an \`impact\`:

- \`INFO\`
- \`ACTION\`
- \`ACTION_INFO\`
- \`UNKNOWN\`

For example:

\`\`\`java
MBeanInfo info = server.getMBeanInfo(name);

for (var operation : info.getOperations()) {
    System.out.println(
        operation.getName() + ": " + operation.getImpact()
    );
}
\`\`\`

A management tool may use impact metadata to render operations differently. However, impact is not a guarantee that a method does not mutate state.

For example, an operation \`getAndResetCounter()\` might be mistakenly marked \`INFO\` even though it resets a counter. If authorization relies solely on \`INFO\`, a read-only user could trigger unintended side effects.

Therefore, security policy should rely on a reviewed **allowlist of action + ObjectName + signature**, rather than \`get*\` naming, descriptions, or impact.

## 15. Reading and Writing an Attribute Can Be Separate Permissions

The same attribute \`MaxWorkers\` can be readable/writable:

\`\`\`text
Attribute MaxWorkers:
  type = int
  readable = true
  writable = true
\`\`\`

Business policy might require:

- Viewer: may read \`MaxWorkers\`.
- Operator: may read and write within permitted bounds.
- Admin: may also change advanced settings.

If the connector only has two global levels—readonly/readwrite—across the whole registry, it does not automatically satisfy per-attribute/per-value authorization. Custom authorization or splitting JMX surfaces by permission domain is required.

Even when an operator is granted write access, the setter still must validate:

\`\`\`java
if (maxWorkers < 1 || maxWorkers > 64) {
    throw new IllegalArgumentException(
        "maxWorkers must be between 1 and 64"
    );
}
\`\`\`

An access check cannot replace validation, concurrency control, or transaction semantics.

## 16. Remote JMX TLS and Firewall

Authorization is only trustworthy when the management endpoint's transport and connectivity are properly secured:

\`\`\`text
Monitoring host
   |
   | authenticated + encrypted
   v
Private management network / VPN / tunnel
   |
   v
JMX connector
   |
   v
Authorization
   |
   v
MBeanServer
\`\`\`

When using JMX/RMI, both a registry port and an RMI server port may be needed. If remote JMX uses dynamic ports or advertises an unreachable hostname, clients can fail even with valid authentication.

Especially in Docker/Kubernetes:

- Only publish the JMX port when truly necessary.
- Keep it separate from public HTTP ingress.
- Specify the exact RMI advertised host/port.
- Protect port-forward permissions and Kubernetes RBAC.
- Do not store credentials in container images or version control.
- Regularly verify JDK versions and security policies.

Do not set \`authenticate=false\`, \`ssl=false\` on a production-exposed endpoint to “quickly fix” connection issues.

## 17. Testing Permissions with Two Accounts

Suppose a lab has two roles:

\`\`\`text
monitorRole readonly
controlRole readwrite
\`\`\`

And MBean:

\`\`\`text
com.example.orders:type=Queue,name=PrimaryControl
\`\`\`

An authorization check must use a **real remote JMX connector** with each credential, not just call local \`ManagementFactory.getPlatformMBeanServer()\`.

### 17.1. Connecting to JMX with Credentials

\`\`\`java
import java.util.HashMap;
import java.util.Map;
import javax.management.MBeanServerConnection;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;
\`\`\`

With the JMX API, the standard environment key used to pass credentials is \`JMXConnector.CREDENTIALS\` (a constant), corresponding to a \`String[]\` containing username and password.

Code example:

\`\`\`java
Map<String, Object> env = new HashMap<>();
env.put(
    JMXConnector.CREDENTIALS,
    new String[] { username, password }
);

JMXServiceURL url = new JMXServiceURL(
    "service:jmx:rmi:///jndi/rmi://localhost:9010/jmxrmi"
);

try (JMXConnector connector =
         JMXConnectorFactory.connect(url, env)) {

    MBeanServerConnection connection =
        connector.getMBeanServerConnection();

    // Run assertions corresponding to the role.
}
\`\`\`

\`username\` and \`password\` must come from a secure secret/test fixture. Do not log credential values.

### 17.2. Testing Read-Only

With the readonly account:

1. \`getMBeanInfo\` and \`getAttribute\` for permitted MBeans.
2. Attempt \`setAttribute\` on a writable attribute.
3. Attempt \`invoke\` on a safe operation in the test environment.
4. Assert that mutating actions are rejected according to the actual security configuration.
5. After rejection, verify that state remains unchanged.

Use a test operation with a small, isolated side effect, such as \`incrementTestCounter()\`, so you can prove it **does not run** when the client lacks permission. Do not use \`clearProductionQueue()\` or \`shutdown()\` for tests.

### 17.3. Testing Readwrite

With the readwrite account:

1. Verify attributes can be read.
2. Write an attribute permitted in the lab, then read it back.
3. Invoke an allowed test operation and assert state changes as expected.
4. If using a custom forwarder, try an operation forbidden by policy even though the account is in the operator group.
5. Confirm the audit event records the correct actor/action/result.

**Important point:** A JDK access file can grant broad actions to a readwrite group. A readwrite test does not prove per-operation RBAC unless a dedicated policy has been implemented.

## 18. Integration Tests Should Not Only Catch Exceptions

Suppose a readonly client tries calling:

\`\`\`java
connection.invoke(
    objectName,
    "incrementTestCounter",
    new Object[0],
    new String[0]
);
\`\`\`

A test that only checks “the call throws an exception” is insufficient. The exception could come from \`InstanceNotFoundException\`, a wrong signature, or a business error, rather than authorization.

A good test should:

- Confirm the MBean exists and the operation signature is correct using a privileged admin/fixture.
- Use the exact readonly credential.
- Classify the exception raised due to the permission policy.
- Verify the counter did not increment after the rejected call.
- Run the same operation with an authorized credential to prove the test fixture works.

The JDK connector mechanism may wrap errors into \`SecurityException\`, \`IOException\`, or protocol/version-specific exceptions. Do not hardcode a fixed error message if multiple versions must be supported.

## 19. Local Tests Differ from Remote Tests

A local test:

\`\`\`java
MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "com.example.orders:type=Queue,name=PrimaryControl"
);

server.invoke(
    name,
    "incrementTestCounter",
    new Object[0],
    new String[0]
);
\`\`\`

proves the operation executes in the local registry. However, it does not pass through remote authentication/access files. It **does not prove** that the JMX connector's readonly account is blocked.

A good test suite should have two layers:

1. **Local contract tests:** MBeanInfo, attribute read/write metadata, method signatures, business validation.
2. **Remote security integration tests:** authentication, role permissions, TLS, and actual denial.

With a custom forwarder, also test bulk API paths and operations with equivalent effects.

## 20. Auditing and Logging Administrative Operations

Operations with side effects require appropriate auditing:

\`\`\`text
timestamp=2026-11-11T10:00:00Z
actor=operator-123
source=jmx
objectName=com.example.orders:type=Queue,name=PrimaryControl
operation=requestPause
result=accepted
requestId=abc123
\`\`\`

This is an illustrative format, not an automatic Spring/JMX standard. The actor must come from an authenticated identity or a trusted mechanism, not an arbitrary parameter passed by the user.

Do not log:

- JMX passwords.
- Access tokens.
- Attribute values containing secrets.
- Full sensitive parameters.
- Detailed credentials/keystore paths in unprotected logs.
- Stack traces containing unsanitized secret data.

An audit event should distinguish:

- **Request accepted**: the action was accepted.
- **Operation completed**: the task finished.
- **Operation rejected**: denied by authorization or validation.
- **Operation failed**: an error occurred during execution.

For async operations, \`invoke\` returning successfully does not mean the job has finished. Task state and corresponding auditing are needed.

## 21. Common Mistakes

| Symptom | Possible Cause | Remediation |
| --- | --- | --- |
| Readonly still sees operations in JConsole | MBeanInfo describes operations, not user permissions. | Check policy at invoke time; do not use metadata as authorization. |
| Readonly can call dangerous operations | Connector has auth/authorization disabled or uses unexpected permissions. | Verify endpoint, credentials, access file, custom connector. |
| \`spring.jmx.enabled=false\` yet JVM MBeans still appear | JVM platform MBeans are independent of Spring exporter. | Distinguish registration sources. |
| Spring Security HTTP enabled yet JConsole still accesses | Remote JMX does not traverse the HTTP filter chain. | Configure JMX authentication/TLS/policy separately. |
| \`isWritable=true\` yet set is rejected | Metadata says writable, caller lacks permission. | Check connector authorization. |
| Readwrite can invoke operations outside intended scope | JDK roles are coarse-grained and lack fine-grained policy. | Separate APIs or implement a controlling forwarder/gateway. |
| Local security test passes while remote fails | Local bypasses connector auth or remote identity differs. | Test with a real remote connection. |
| Authentication fails due to file permissions | JDK agent requires secure password file permissions. | Set proper owner/permissions; do not loosen them. |
| JConsole connection times out | RMI hostname/port, firewall, or TLS. | Check network and connector before blaming permissions. |
| Test rejected yet state still changes | Authorization occurs after side effect, or test is not isolated. | Block before dispatch; check races and audit logs. |
| QueryNames exposes topology | Metadata discovery is uncontrolled. | Evaluate metadata permissions and network boundaries. |
| Notifications leak data | Policy does not check subscribe/notification payloads. | Protect listener registration and event contents. |

## 22. Workflow for Designing an Authorization Policy

### Step 1 — Inventory MBeans

List domains, ObjectNames, and actually exported attributes/operations using \`MBeanInfo\`. Do not rely only on source annotations.

### Step 2 — Classify Data and Actions

Example:

\`\`\`text
QueueDepth       read-only telemetry
MaxWorkers       configurable operational setting
requestPause     operational command
clearRetryQueue  destructive command
\`\`\`

Evaluate actual side effects, not just names or \`impact\`.

### Step 3 — Define Roles

A model:

\`\`\`text
viewer    -> read status
operator  -> read status + selective control
admin     -> advanced administration within approved scope
\`\`\`

### Step 4 — Choose the Enforcement Mechanism

- If two levels—readonly/readwrite—are enough, a JDK agent access file may fit.
- If per-MBean/per-operation control is needed, use a custom forwarder or policy-enforcing gateway.
- If operations have major business impact, add service-layer authorization.
- If multiple paths call the same service, ensure authorization does not reside in just one transport.

### Step 5 — Test Denial

For each role, attempt forbidden actions and verify state does not change. Also test bulk operations, overloads, and alternative API paths.

### Step 6 — Deploy Connection Security

TLS, authentication, firewalling, secrets management, log retention, and infrastructure permissions must match the JVM's sensitivity level.

### Step 7 — Monitor and Maintain

When adding a new \`@ManagedOperation\`, update the security allowlist and tests before deployment. Audit sensitive actions; do not grant broad permissions just to quickly work around an authorization error.

## 23. Practice Exercises

### Exercise 1 — Two JMX Accounts

In an isolated lab, configure \`monitorRole readonly\` and \`controlRole readwrite\`. Connect with both accounts and test reading \`QueueDepth\`, writing \`MaxWorkers\`, and invoking \`incrementTestCounter\`.

**Goal:** demonstrate the connector's actual read/write permissions.

### Exercise 2 — Metadata Is Not Permission

Read \`MBeanInfo\` with the readonly account and observe that \`incrementTestCounter\` appears. Attempt to invoke it and verify it is rejected.

**Goal:** understand that \`getOperations()\` is not an authorization allowlist.

### Exercise 3 — Read-Only Operation

Create a read-only operation \`calculateSummary()\` that only returns information and declares an appropriate INFO impact. Check whether the readonly account is permitted to invoke it under the JMX access policy.

**Goal:** do not infer permissions from impact or naming.

### Exercise 4 — Separating Status/Control

Create two MBeans: \`QueueStatus\` with read-only attributes and \`QueueControl\` with state-mutating operations. Design a policy so the monitoring role only reads status.

**Goal:** reduce the management surface and simplify authorization.

### Exercise 5 — Fine-Grained Policy

Design a pseudo-policy for \`MBeanServerForwarder\` blocking all operations except \`requestPause\` for the operator role. Write a test blocking \`clearRetryQueue\` and verifying no side effects occur.

**Goal:** understand that per-operation permissions must be enforced by a dedicated mechanism.

### Exercise 6 — Checking Local vs. Remote

Invoke successfully via the local MBeanServer, then connect via remote JMX with a readonly credential and prove that the mutating action is rejected.

**Goal:** recognize that connector authorization does not automatically apply to local Java code.

### Exercise 7 — Security Review

Inventory 10 existing MBeans, classify attributes/operations, and propose permission groups. Also evaluate metadata discovery and notifications.

**Goal:** protect the entire JMX surface rather than only a few prominent operations.

## 24. Review Questions

**1. Does \`@ManagedOperation\` itself define which roles may invoke it?** No. It describes an exported operation; authorization is handled by another security layer.

**2. What question does \`MBeanAttributeInfo.isWritable()\` answer?** Whether the attribute is writable according to the MBean contract, not whether the current caller has sufficient permission.

**3. Does \`readonly\` in the JDK JMX access file mean a user can invoke every INFO operation?** No. Do not infer invoke permissions from impact metadata.

**4. Does a \`readwrite\` account come with per-ObjectName authorization built in?** Do not treat readonly/readwrite as fine-grained RBAC; a dedicated policy is needed for per-MBean or per-operation permissions.

**5. Why does Spring Security HTTP not automatically protect remote JMX?** Because the JMX connector does not pass through Spring Security's HTTP filter chain.

**6. Does the local MBeanServer use the remote JMX agent's password file?** No; local Java calls do not connect through that remote connector.

**7. When is \`MBeanServerForwarder\` needed?** When you want to intercept/authorize JMX actions at the connector/server layer according to a custom policy.

**8. Why must authorization tests check state?** To ensure the call is rejected before any side effects occur, not merely that an exception was thrown.

**9. If a state-mutating operation requires dedicated permissions, what should you do?** Separate status/control surfaces, use an allowlist, and place trustworthy enforcement at the connector/server/service.

**10. What layers are needed when enabling remote JMX in production?** Appropriate network restrictions, TLS, authentication, authorization, auditing, and secret management.

## 25. Summary

**Authorizing attribute reads and operation invocations in Spring JMX** does not live inside the \`@ManagedAttribute\` or \`@ManagedOperation\` annotations themselves. The Spring exporter decides **what is exposed**, while security infrastructure decides **who is permitted to do what**.

The JDK remote JMX access file can provide coarse-grained roles like \`readonly\` and \`readwrite\`. When fine-grained per-MBean, per-attribute, or per-operation permissions are required, you must add enforcement such as \`MBeanServerForwarder\` or business authorization. Every permission must be verified with remote security integration tests, including denial cases and unchanged state. In production, separate monitoring from control, protect the connector with TLS and network policies, and never base security decisions on impact metadata.

## References

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework Javadoc — \`MBeanExporter\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporter.html
- Oracle JDK Monitoring and Management Guide — Using JMX Technology: https://docs.oracle.com/en/java/javase/21/management/monitoring-and-management-using-jmx-technology.html
- Java SE 21 — \`MBeanServerConnection\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerConnection.html
- Java SE 21 — \`MBeanServerForwarder\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/remote/MBeanServerForwarder.html
- Java SE 21 — \`MBeanOperationInfo\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanOperationInfo.html
- Java SE 21 — \`MBeanAttributeInfo\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanAttributeInfo.html