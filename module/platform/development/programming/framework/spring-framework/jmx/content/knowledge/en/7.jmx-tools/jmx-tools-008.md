# Tool Access Permissions for JMX Connectors

## 1. Objectives and Scope

JMX (Java Management Extensions) allows a management tool such as JConsole, VisualVM, or a custom JMX client to access MBeans registered in an MBeanServer. The tool can read attributes, write attributes, invoke operations, and receive notifications if the connection and security policy allow.

A **JMX connector** is the entry point delivering administrative calls to the MBeanServer. A tool's permissions depend on how the connector is configured, the session's authentication credentials, the server's authorization layer, and the capabilities exposed by each MBean. Seeing an MBean in a list does not mean every action on that MBean is permitted.

This lesson focuses on operational questions:

- Is the tool connecting locally or remotely to the JVM?
- Who is allowed to open a JMX connection?
- Is the tool allowed to read data, modify attributes, invoke operations, or only receive notifications?
- How do you distinguish connection permissions from permissions to act on MBeans?
- How do you configure and verify the **least privilege** principle?
- How does Spring Framework JMX affect the management surface and access permissions?

The illustrative examples use standard JMX/JDK and Spring Framework; exact configuration properties, authentication mechanisms, and authorization models may vary across JDKs, connector providers, application servers, and runtime platforms.

## 2. Access Control Architecture Model

\`\`\`text
             JConsole / VisualVM / JMX client
                            |
                   credentials / TLS
                            |
                            v
                  JMX connector server
                            |
                 authentication policy
                            |
                 authorization / access
                            |
                            v
                        MBeanServer
                            |
              +-------------+--------------+
              |             |              |
        ObjectName A   ObjectName B   ObjectName C
              |             |              |
         attributes     operations   notifications
              |             |              |
              +------ Spring-managed MBeans -+
\`\`\`

Control layers that must be kept distinct:

| Layer | Question | Example |
| --- | --- | --- |
| Network | Can the client reach the connector port? | Firewall, allowlist, VPN, private network |
| Transport | Is the channel protected? | TLS, remote connector configuration |
| Authentication | Who is the client? | Username/password, connector/provider authentication mechanism |
| Authorization | What is that identity allowed to do? | Read-only or read-write, per-operation policy if infrastructure supports it |
| MBean contract | What capabilities does each MBean expose? | \`@ManagedAttribute\`, \`@ManagedOperation\`, Standard MBean interface |
| Application validation | Is an action valid and safe? | Parameter bounds, allowed state, audit |

**Principle:** one layer does not replace another. For example, a firewall restricting connection sources does not mean clients are properly authorized; an interface merely exposing an operation does not mean that operation is protected by role-specific authorization.

## 3. Local JMX vs. Remote JMX

### 3.1. Local Connections

Tools running on the same machine can use the local attach mechanism to discover and access a JVM, depending on JDK, operating system, user permissions, and attach policies. JConsole/VisualVM typically support selecting a local process when the environment permits.

Notes:

- Local access is typically governed by OS controls, process ownership, and attach policies.
- Do not assume every user on the machine can attach to every JVM, or that local connectors always share the same authentication configuration as remote RMI.
- Some container environments, hardened JVMs, JDK builds, or security policies disable or restrict attach.
- Do not rely solely on "local only" when multiple users have shell access on the same host.

### 3.2. Remote Connections

Remote JMX creates a management surface over the network. With the JDK's RMI-based JMX management agent, applications can use system properties such as \`com.sun.management.jmxremote.port\`, \`com.sun.management.jmxremote.authenticate\`, \`com.sun.management.jmxremote.ssl\`, and related settings.

Enabling a remote connector does not automatically mean it is adequately secured: you must evaluate authentication, encryption, RMI transport, bind addresses, and secondary ports. Remote JMX is a high-privilege administrative interface; it should not be exposed directly on the Internet.

A safer deployment typically keeps the endpoint inside a private management network or uses an authenticated, access-controlled secure tunnel. Using an SSH tunnel only changes the network path; permissions at the JMX layer still need to be appropriate.

## 4. Read-Only and Read-Write Permissions in the JDK Management Agent

When configuring the JDK JMX remote agent with password/access files, \`jmxremote.access\` can assign an access level to each principal. Two common levels are:

- \`readonly\`: permits observational actions considered reads by the policy.
- \`readwrite\`: permits mutating actions such as writing attributes or invoking operations, depending on policy and configured options.

Illustrative access file example:

\`\`\`text
monitorRole  readonly
operatorRole readwrite
\`\`\`

And the corresponding password file (illustrating structure only—do not use sample passwords in production):

\`\`\`text
monitorRole  <secret-from-secure-deployment>
operatorRole <another-secret-from-secure-deployment>
\`\`\`

Values in angle brackets are placeholders; real configurations must hold valid credentials without the brackets. These files require restricted filesystem read permissions per JDK rules and must never be committed to a repository.

Conceptual properties example:

\`\`\`properties
-Dcom.sun.management.jmxremote.port=9010
-Dcom.sun.management.jmxremote.authenticate=true
-Dcom.sun.management.jmxremote.password.file=/secure/jmxremote.password
-Dcom.sun.management.jmxremote.access.file=/secure/jmxremote.access
-Dcom.sun.management.jmxremote.ssl=true
\`\`\`

The lines above represent individual JVM system properties; they are not the verbatim contents of a regular \`.properties\` file with \`-D\` prefixes. When launching the JVM, pass these \`-D...\` arguments on the startup command or in the corresponding runtime configuration. If using another setup (application server, custom \`JMXAuthenticator\`, custom connector), configuration may differ from this example.

The \`readwrite\` level is very broad: any exposed operation could restart a subsystem, clear a cache, or alter application state. Therefore, restrict who holds this role and narrow the exported MBean surface itself.

### Limitations of the Two-Level Model

The JDK management agent's \`readonly\`/\`readwrite\` model is a starting point, not a fine-grained RBAC system per ObjectName or per operation. Some configurations include extra permissions around MBean creation/unregistration or registration; exact capabilities depend on access-file syntax and the JDK. Implementing granular per-role/per-operation policies requires an additional authorization layer or a supporting connector/provider.

Do not claim that declaring two lines \`monitorRole readonly\` and \`operatorRole readwrite\` constitutes a complete policy for a multi-tenant system.

## 5. Authentication Is Not Authorization

**Authentication** verifies the client's identity, such as via username/password or another mechanism. **Authorization** decides which JMX requests that verified identity is allowed to perform.

Example:

\`\`\`text
monitorRole
   |
   +-- authenticated = true
   |
   +-- queryNames(...)        -> allowed if read-only policy permits
   +-- getAttribute(...)      -> allowed if read-only policy permits
   +-- setAttribute(...)      -> denied
   +-- invoke(...)            -> typically restricted in read-only
\`\`\`

A tool may authenticate successfully yet receive \`SecurityException\` when invoking an operation, and that can be the exact intended outcome under the policy. Conversely, connection failures may happen before authentication due to firewalls, DNS, TLS, RMI ports, or the service URL.

In logging and operations, distinguish:

1. **Connection refused/timeout:** endpoint is unreachable or connector is not active.
2. **SSL handshake failed:** TLS/certificate/protocol mismatch.
3. **Authentication failed:** invalid credentials or authentication mechanism failure.
4. **Authorization denied:** connected, but the action was blocked by policy.
5. **InstanceNotFound/AttributeNotFound:** MBean/attribute does not exist—not necessarily a permission error.
6. **MBeanException/ReflectionException:** error invoking the operation or inside implementation logic.

## 6. Impact of Permissions on Tool Actions

The table below describes common expectations; final enforcement depends on the specific connector/MBeanServer policy:

| Action | Meaning | Policy Considerations |
| --- | --- | --- |
| List domains, ObjectNames | Discover management surface | Can reveal application structure; grant only to those who need visibility |
| \`getMBeanInfo\` | Read attribute/operation/notification schema | Metadata can reveal system names or resource types |
| \`getAttribute\` | Read operational data | Read-only, yet data may still be sensitive |
| \`setAttribute\` | Change state/configuration | Write access; separate validation and auditing |
| \`invoke\` | Run management operation | Can have major side effects; must be tightly controlled |
| \`addNotificationListener\` | Subscribe to notifications | Notification payloads can also disclose information |
| \`createMBean\`, \`unregisterMBean\` | Modify registry | High administrative privilege; do not grant by default |

A tool like JConsole may render an Operation button or Attribute input box based on metadata even when the current policy forbids executing it. **A UI showing a control is not proof of granted permission.** Always verify the actual request outcome and returned errors.

## 7. Spring Framework JMX and the Management Surface

Spring adds \`MBeanExporter\`, annotations such as \`@ManagedResource\`, \`@ManagedAttribute\`, \`@ManagedOperation\`, naming strategies, and JMX client proxies. Spring helps declare what the application wants to export, but **it does not automatically implement an RBAC system for remote JMX connectors** simply because an MBean carries annotations.

Example:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.jobs:type=JobControl,name=Main",
    description = "Job status and management operations"
)
public class JobControl {
    private volatile boolean paused;

    @ManagedAttribute(description = "Pause state")
    public boolean isPaused() {
        return paused;
    }

    @ManagedOperation(description = "Pause accepting new jobs")
    public void pauseNewJobs() {
        paused = true;
    }
}
\`\`\`

Enabling JMX annotation export:

\`\`\`java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxConfiguration {}
\`\`\`

In this MBean, \`Paused\` is an observable attribute; \`pauseNewJobs()\` is a state-changing operation. A monitoring principal should only need to read \`Paused\`. An operations principal permitted to change state may need to invoke the operation, but must be authorized at the appropriate connector/policy layer.

If an application only needs monitoring, **avoid exporting side-effecting operations** merely for debugging convenience. Removing an operation from the management contract generally reduces risk more reliably than exposing it and relying entirely on a broad policy.

## 8. Why Is Read-Only Still Risky?

Even a read-only client may still see:

- Host names, environments, instances, and cluster topology via ObjectNames.
- Heap information, thread counts, JVM arguments, and runtime configuration.
- System properties, file paths, and configuration values that may contain sensitive data.
- MBean metadata or notification messages emitted by the application.
- Data from custom MBeans if developers expose too much information.

Therefore, "readonly" does not mean "public." Never place tokens, passwords, credentials, or customer data in \`@ManagedAttribute\`, ObjectNames, notifications, or descriptions. When observation is required, expose aggregated metrics, non-sensitive identifiers, and safe descriptions.

For particularly sensitive data, omit it from the MBean contract entirely; hiding a field in a UI is not protection because other JMX clients can still invoke the API if the server permits it.

## 9. Accessing Remote JMX from a Java Client

A standard client uses \`JMXServiceURL\` and \`JMXConnectorFactory\`:

\`\`\`java
import java.util.HashMap;
import java.util.Map;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXConnector.CREDENTIALS;
import javax.management.remote.JMXServiceURL;

public class RemoteJmxReader {
    public static void main(String[] args) throws Exception {
        JMXServiceURL url = new JMXServiceURL(
            "service:jmx:rmi:///jndi/rmi://localhost:9010/jmxrmi"
        );

        Map<String, Object> environment = new HashMap<>();
        environment.put(
            JMXConnector.CREDENTIALS,
            new String[] {
                System.getenv("JMX_USER"),
                System.getenv("JMX_PASSWORD")
            }
        );

        try (JMXConnector connector =
                 JMXConnectorFactory.connect(url, environment)) {
            MBeanServerConnection connection =
                connector.getMBeanServerConnection();

            ObjectName memory =
                new ObjectName("java.lang:type=Memory");

            System.out.println(
                connection.getAttribute(memory, "HeapMemoryUsage")
            );
        }
    }
}
\`\`\`

The example only uses \`JMXConnector.CREDENTIALS\`; importing \`javax.management.remote.JMXConnector.CREDENTIALS\` is unnecessary and a real project only needs to import \`JMXConnector\`. Reading credentials from environment variables is an illustrative example, not a complete secrets management strategy. With SSL, configure the truststore/certificates and connection setup matching the server connector; never bypass certificate validation as a "quick fix" for connectivity.

If the client uses read-only credentials, read calls can succeed while \`invoke\` or \`setAttribute\` calls may be rejected. Exact behavior depends on the actual access policy on the server.

## 10. Configuring a Spring Client with MBeanServerConnectionFactoryBean

Spring provides \`MBeanServerConnectionFactoryBean\` to establish a JMX connection through IoC. Service URL configuration example:

\`\`\`java
import javax.management.MBeanServerConnection;
import javax.management.remote.JMXServiceURL;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.support.MBeanServerConnectionFactoryBean;

@Configuration
public class JmxClientConfiguration {
    @Bean
    public MBeanServerConnectionFactoryBean remoteConnection()
            throws Exception {
        MBeanServerConnectionFactoryBean factory =
            new MBeanServerConnectionFactoryBean();

        factory.setServiceUrl(
            new JMXServiceURL(
                "service:jmx:rmi:///jndi/rmi://localhost:9010/jmxrmi"
            )
        );
        return factory;
    }
}
\`\`\`

In authenticated environments, pass the JMX connector environment properties to the factory via the API/configuration supported by your Spring version; load secrets from an appropriate secrets management mechanism. Avoid hard-coding passwords in Java source or version-controlled configuration files.

The client receives \`MBeanServerConnection\` and uses standard JMX APIs:

\`\`\`java
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;

public class JmxStatusClient {
    private final MBeanServerConnection connection;

    public JmxStatusClient(MBeanServerConnection connection) {
        this.connection = connection;
    }

    public Object readPaused() throws Exception {
        ObjectName name =
            new ObjectName("com.example.jobs:type=JobControl,name=Main");
        return connection.getAttribute(name, "Paused");
    }
}
\`\`\`

Spring helps manage the connection lifecycle and dependencies, but **client permissions are still enforced by the JMX server**. If an MBean proxy is created via \`MBeanProxyFactoryBean\`, that proxy does not bypass connector authorization either.

## 11. Designing Roles Under Least Privilege

An operational role matrix might look like:

| User Group | Need | Authorization Approach |
| --- | --- | --- |
| Monitoring dashboards | Read metrics/state | Read-only principal, restricted network |
| On-call diagnostics | Browse MBeans, thread/heap metrics | Read-only principal; consider restricting sensitive data |
| Authorized operators | Specific state-changing operations | Dedicated identity, audited; sufficiently granular authorization |
| Platform admins | Modify registry or JVM management | Privileged access; not granted by default |

In systems requiring fine-grained authorization such as "an operator may invoke \`pauseNewJobs\` but no other operation," a simple read/write access file may fall short. Options include a custom connector/forwarder/authorization layer, administering via another RBAC-enabled API, or splitting MBeans/endpoints by permitted scope. Policies must be tested directly; do not assume every JMX provider supports the same permission granularity.

Generally, issue dedicated credentials per tool rather than sharing an admin password. Each identity can then be revoked or rotated individually if a monitoring system is compromised or retired.

## 12. Verifying Permissions with Practical Test Cases

To know permissions actually work, test with the exact identity the tool will use rather than just reading config files.

Example scenario:

1. Connect with the monitoring account using the same service URL the dashboard uses.
2. Call \`queryNames\` for the target domain to confirm the visible MBean scope.
3. Call \`getMBeanInfo\` and \`getAttribute\` for expected observable attributes.
4. In an isolated test environment, attempt a safe write action to confirm the read-only account is **denied**; do not use destructive operations for the test.
5. Connect with the operator account and confirm only the designed permissions work (if the infrastructure supports granular authorization).
6. Inspect server-side logs/audits and returned errors.

Verify both denied requests and allowed requests. In production, avoid testing operations with real side effects; prefer testing in staging with safe MBeans.

### Authorization Error Handling Example

\`\`\`java
import java.io.IOException;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;

public final class AttributeReader {
    public static Object read(
            MBeanServerConnection connection,
            ObjectName name,
            String attribute) throws Exception {
        try {
            return connection.getAttribute(name, attribute);
        } catch (SecurityException denied) {
            throw new IllegalStateException(
                "JMX principal is not allowed to read this attribute",
                denied
            );
        } catch (IOException disconnected) {
            throw new IllegalStateException(
                "JMX connector communication failed",
                disconnected
            );
        }
    }
}
\`\`\`

A remote JMX environment may wrap policy failures in a different exception wrapper; record the actual exception chain for diagnosis. Never log credentials or the entire connection environment map.

## 13. RMI Connectivity: Network Ports and Hostname

Remote JMX over RMI can use one port for the registry and another for the RMI server. Thus, opening a single TCP port while the tool still times out is not necessarily a permission error. In deployments with firewalls, containers, or NAT, properly configure:

- Connector/registry port.
- RMI server port if the management agent supports fixing it via \`com.sun.management.jmxremote.rmi.port\`.
- Hostname/RMI advertised address reachable by clients.
- TLS, certificates, and network ACLs.
- JMX authentication and authorization.

\`java.rmi.server.hostname\` can be configured to match network topology, but it must not accidentally advertise an unprotected public address. Specifics must match your JDK and deployment network; no single RMI URL works across every deployment.

## 14. Configurations That Should Never Be Used as Defaults

\`\`\`properties
-Dcom.sun.management.jmxremote.authenticate=false
-Dcom.sun.management.jmxremote.ssl=false
\`\`\`

This combination disables both authentication and encryption on remote JMX, which is especially dangerous if the connector is reachable over untrusted networks. Never use it as a production default. If an isolated development environment needs a simplified setup, strictly restrict network connectivity and never copy that configuration verbatim to other environments.

Do not:

- Expose remote JMX directly to the Internet.
- Share one readwrite credential across dashboards and operators.
- Put JMX passwords into Git, command history, logs, or public documentation.
- Disable TLS certificate validation to bypass configuration errors.
- Expose dangerous operations assuming nobody knows their ObjectName.
- Use "read-only" as an excuse to export all internal information.

## 15. Distinguishing JMX from Spring Boot Actuator

Spring Framework JMX provides \`MBeanExporter\`, annotation-based export, naming strategies, MBean proxies, and notification integration. Spring Boot Actuator provides management endpoints exposable over JMX or HTTP depending on configuration; these endpoints follow their own enablement/exposure model.

Do not apply a conclusion like "the HTTP endpoint is protected by Spring Security, so every JMX operation is automatically protected by Spring Security too." The two access paths can have different security mechanisms. Inspect actual exposure, connector configuration, and authorization on each path independently.

If an application does not need remote JMX, keep JMX local or disable unnecessary exposure, and use alternative metrics/health systems suited to operational requirements.

## 16. Synthesis Scenario

Suppose a Spring application exports:

\`\`\`text
com.example.jobs:type=JobControl,name=Main
  Attribute: Paused (read-only)
  Operation: pauseNewJobs() (changes runtime state)

java.lang:type=Memory
  Attribute: HeapMemoryUsage
\`\`\`

The monitoring team wants to observe \`Paused\` and heap usage. The operations team occasionally needs \`pauseNewJobs()\`.

Design:

1. Monitoring receives only an observer account and connects strictly from the monitoring network.
2. Operators have separate identities and are permitted to change only what is necessary per policy; if the JMX policy is too coarse, use a management layer with appropriate granular authorization.
3. \`pauseNewJobs\` includes validation, audit logging, and is designed so repeated calls do not cause unexpected state.
4. Do not place secrets, request payloads, or customer data in JMX attributes.
5. The remote connector uses proper encryption and authentication, with non-public ports.
6. Verify with a real client that the read-only principal cannot perform write operations.

This is authorization driven by administrative need, rather than granting a readwrite connection to every tool out of convenience.

## 17. Mental Model

\`\`\`text
Can the tool connect?
    |
    +-- No -> check network / service URL / TLS
    |
    +-- Yes
         |
         v
Is the identity authenticated?
    |
    +-- No -> credentials / authenticator
    |
    +-- Yes
         |
         v
Is the operation allowed by the authorization policy?
    |
    +-- No -> SecurityException / access denied
    |
    +-- Yes
         |
         v
Does the MBean expose the corresponding attribute/operation?
    |
    +-- No -> MBeanInfo / AttributeNotFound / ReflectionException
    |
    +-- Yes
         |
         v
Check validation, state, and actual impact
\`\`\`

**Key takeaway:** A JMX connector is the access boundary to the MBeanServer; tool permissions must be protected in layers across network, transport, authentication, authorization, MBean surface, and business validation. Spring assists with exporting MBeans and establishing JMX connections, but it does not automatically grant or enforce role-based permissions for tools. Apply least privilege, prefer read-only for monitoring, restrict side-effecting operations, and verify permissions using the exact tool identity.
