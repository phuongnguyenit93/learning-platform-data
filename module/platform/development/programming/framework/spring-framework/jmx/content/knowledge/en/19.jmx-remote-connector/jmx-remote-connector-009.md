# Checking Versions, Firewalls, and Ports to Open for Spring Framework JMX Remote Connector

> **Topic:** Spring Framework JMX  
> **Knowledge group:** Remote connector  
> **Lesson:** Checking versions, firewalls, and ports to open

## 1. Lesson Objectives

When deploying remote JMX, failures often stem not from annotations or MBeans, but from **JDK/JMX client versions**, **how the connector advertises its address**, **RMI ports**, or **firewall/NAT rules**. After this lesson, you will be able to:

- Distinguish Spring JMX export from the JMX remote connector.
- Check server and client Java versions, JMX agent configuration, and the connector type in use.
- Understand why with RMI/JNDI, opening a single registry port is sometimes **not enough**.
- Configure the JMX registry port and RMI server port under a clear network policy.
- Distinguish \`java.rmi.server.hostname\`, \`com.sun.management.jmxremote.port\`, and \`com.sun.management.jmxremote.rmi.port\`.
- Verify connectivity step by step: which ports the JVM listens on, DNS, TCP, firewall, RMI stub, authentication, TLS, MBeanServer, and ObjectName.
- Set up a controlled test configuration and avoid turning the JMX port into a dangerous public management surface.

## 2. Separating Two Questions: Are There MBeans, or Is There Remote Connectivity?

A Spring application can export MBeans:

\`\`\`java
@Configuration
@EnableMBeanExport
public class JmxConfig {
}
\`\`\`

Exported bean:

\`\`\`java
@Component
@ManagedResource(
    objectName = "app.management:type=Queue,name=orders"
)
public class QueueMonitor {

    @ManagedAttribute
    public int getDepth() {
        return 12;
    }
}
\`\`\`

However, **\`@EnableMBeanExport\` does not open any network port**. It activates the infrastructure that places beans into the MBeanServer. The remote connector is a separate layer:

\`\`\`text
Spring bean / @ManagedResource
              |
              v
       Spring MBeanExporter
              |
              v
          MBeanServer
              ^
              |
       JMXConnectorServer
              ^
              |  TCP / RMI / TLS / authentication
              |
          JMX client
     JConsole / VisualVM /
     Java MBeanServerConnection
\`\`\`

If local JConsole sees the MBean while a client from another machine cannot connect, first inspect **the connector, address, and network**. Only if the remote client connects yet does not see the MBean should you inspect **which MBeanServer the connector and exporter are using**.

## 3. Versions to Check

A "JMX version" is not an independent number sufficient to describe all connectivity capabilities. In practice, inspect all of the following components:

| Component | Example Check | Why It Matters |
|---|---|---|
| Server JDK/JRE | \`java -version\` | Agent, RMI, TLS, ciphers, and JVM options depend on the JDK |
| Client JDK | \`java -version\`, which JDK JConsole uses | Client may encounter TLS/protocol differences |
| Spring Framework | Running dependency version | Affects export mechanics; does not decide RMI ports itself |
| Spring Boot (if used) | Dependencies and JMX configuration | May enable/disable export or alter domain |
| JMX connector | RMI/JNDI, custom connector, JMXMP if added | Determines endpoint and protocol model |
| OS/container | Linux/Windows/Docker/Kubernetes | Determines listening-port commands, NAT, and service routing |
| Firewall/network | Host firewall, security group, network policy | Can block connections even when the JVM is bound to the port |
| Security settings | Authentication, SSL/TLS, and access rules | TCP success does not guarantee JMX access |

On the server:

\`\`\`bash
java -version
\`\`\`

To know which JDK the running JVM actually uses, you can use the corresponding JDK tools:

\`\`\`bash
jcmd <PID> VM.version
jcmd <PID> VM.command_line
jcmd <PID> VM.system_properties
\`\`\`

\`jcmd\` requires appropriate permissions, and the attach tool must be able to access the process. Never paste all of \`VM.system_properties\` into shared logs, because system properties can contain secrets or tokens.

For Java processes running inside containers, run the tools in an environment that can see the corresponding PID and JVM. The Java version on the host machine is **not necessarily** the JVM version running inside the container.

### Why Does Version Compatibility Affect Remote JMX?

JMX RMI relies on Java RMI and can be affected by:

- JDK version and connector implementation.
- Authentication and authorization mechanisms.
- Default TLS protocols/ciphers on both ends.
- Java serialization and classpath for custom payloads.
- Security policies and disabled algorithms on newer JDKs.
- Hostname or RMI endpoint sent by the server to the client.

Do not assume a given Spring Framework version mandates a fixed JMX port. Spring export is in-JVM logic; port settings are governed by the JMX agent/connector and network infrastructure.

## 4. Two Key Endpoints in JMX RMI

With standard RMI/JNDI remote JMX, there are at least two roles:

1. **RMI registry/JNDI lookup**: where the client obtains the connector stub/address.
2. **RMI connector endpoint**: where the client actually continues communicating with the JMX server.

\`\`\`text
                       Client machine
                           |
             1) Lookup to registry port
                           |
                           v
                  HOST:REGISTRY_PORT
                         RMI registry
                           |
                  receive RMI stub / endpoint
                           |
             2) Connect to RMI server port
                           |
                           v
                HOST:RMI_SERVER_PORT
                           |
                           v
                JMXConnectorServer
                           |
                           v
                       MBeanServer
\`\`\`

An initial successful connection to the registry **does not guarantee** the entire JMX session works. The client still has to connect to the host/port advertised by the RMI stub.

Example URI:

\`\`\`text
service:jmx:rmi:///jndi/rmi://jmx.example.internal:9010/jmxrmi
\`\`\`

In this URL, \`9010\` is the port serving **registry lookup**. The subsequent endpoint may use a separate RMI port. Looking at the URL alone is not enough to claim the client will use only one TCP connection or a single port.

## 5. Common System Properties

With the built-in JMX management agent on HotSpot/OpenJDK, commonly used properties include:

| Property | Function |
|---|---|
| \`com.sun.management.jmxremote\` | Enables JVM JMX management capability per the matching agent mechanism |
| \`com.sun.management.jmxremote.port\` | Remote JMX registry/lookup port of the built-in agent |
| \`com.sun.management.jmxremote.rmi.port\` | Fixed RMI connector endpoint port, if supported by the agent/JDK |
| \`java.rmi.server.hostname\` | Hostname/IP advertised by RMI to clients |
| \`com.sun.management.jmxremote.authenticate\` | Enables/disables authentication for the built-in agent |
| \`com.sun.management.jmxremote.ssl\` | Enables/disables SSL/TLS for the built-in agent |
| \`com.sun.management.jmxremote.access.file\` | Path to the access-control file if using file-based control |
| \`com.sun.management.jmxremote.password.file\` | Path to the password file if using file-based control |
| \`com.sun.management.jmxremote.local.only\` | Option related to restricting local access on supported JDKs; verify semantics on your actual JDK |

Availability and semantics must be verified against the **actual JDK vendor/version**. These system properties belong to the built-in agent mechanism, not to Spring's \`@ManagedResource\` annotation.

### Illustrative Configuration for an Internal Environment

\`\`\`bash
java \
  -Dcom.sun.management.jmxremote \
  -Dcom.sun.management.jmxremote.port=9010 \
  -Dcom.sun.management.jmxremote.rmi.port=9011 \
  -Djava.rmi.server.hostname=jmx.example.internal \
  -Dcom.sun.management.jmxremote.authenticate=true \
  -Dcom.sun.management.jmxremote.ssl=true \
  -jar application.jar
\`\`\`

This is an illustrative template: before running in reality, prepare authentication/authorization files, keystores/truststores, or SSL setup appropriate for the agent/JDK and network. Do not assume that merely adding \`authenticate=true\` and \`ssl=true\` completes a secure configuration.

Ports \`9010\` and \`9011\` are only examples; choose ports suited to your infrastructure.

## 6. Why Must Both Ports Be Checked?

Not pinning \`rmi.port\` can cause the connector endpoint to use a dynamic port. In a firewalled environment, the client may:

- Establish TCP to \`9010\`.
- Look up the registry.
- Receive a stub pointing to a port blocked by the firewall.
- Hang or time out while establishing the JMX connection.

Therefore, firewall design should be based on **the actual list of connector ports**, not solely on the port appearing in the URL.

Example:

\`\`\`text
Client subnet            Server
10.10.20.0/24            10.10.30.15

  TCP 9010  -----------> RMI registry
  TCP 9011  -----------> RMI endpoint
\`\`\`

If both roles are configured to share a port on a compatible implementation, verify the exact behavior. Do not assume the same port can always be shared across every JMX agent or custom connector configuration.

## 7. What Problem Does java.rmi.server.hostname Solve?

The RMI stub can contain a hostname/IP that the client must connect to. In environments with multiple network interfaces, containers, NAT, or internal DNS, the advertised host may be unreachable from the client.

For example, the server has:

\`\`\`text
Container internal hostname: app-pod-7
Container IP: 172.18.0.4
Client-accessible address: jmx.example.internal
\`\`\`

The client opens the URL to \`jmx.example.internal:9010\`, yet the stub directs it to \`172.18.0.4:9011\`. If the client outside the container cannot route to \`172.18.0.4\`, the next connection step fails.

Use:

\`\`\`text
-Djava.rmi.server.hostname=jmx.example.internal
\`\`\`

to configure the address advertised by RMI according to the appropriate infrastructure.

**Note:** this is the **advertised** address; it does not mean the JVM will bind every network interface as desired. Controlling bind/listen interfaces also depends on the agent/socket factory implementation and OS configuration. Inspect the actual listening sockets.

## 8. What Must the Firewall Open?

A realistic policy should begin with the question: "Which clients are allowed to manage which JVMs?"

Example firewall requirement table:

| Flow | Source | Destination | Protocol | Purpose |
|---|---|---|---|---|
| JMX lookup | Approved bastion/monitoring subnet | JVM server | TCP 9010 | RMI registry |
| JMX endpoint | Same approved client set | JVM server | TCP 9011 | RMI connector |
| DNS | Client or DNS infrastructure | DNS resolver | Per DNS policy | Hostname resolution |
| TLS/identity backend | Connector if using external auth system | Corresponding system | Per design | Authentication support |

Only allow inbound traffic from approved administrative addresses. Never open \`0.0.0.0/0\` on a firewall/security group just so JConsole can connect.

Distinguish three commonly confused layers:

- **Host firewall**: Windows Firewall, nftables/iptables, firewalld, etc.
- **Cloud firewall/security group**: rules in front of VMs or load balancers.
- **Container/Kubernetes network policy**: controls traffic between pods/nodes/namespaces.

One layer permitting traffic does not guarantee the entire path permits it. Check all layers involved in the actual topology.

## 9. Checking Which Ports the JVM Is Listening On

On Linux, you can use:

\`\`\`bash
ss -ltnp
\`\`\`

Or filter by selected ports:

\`\`\`bash
ss -ltnp | grep -E ':(9010|9011)\b'
\`\`\`

On Windows PowerShell:

\`\`\`powershell
Get-NetTCPConnection -State Listen |
    Where-Object { $_.LocalPort -in 9010, 9011 } |
    Select-Object LocalAddress, LocalPort, OwningProcess
\`\`\`

The listening ports must belong to the expected JVM/PID or designed proxy/forwarding process. When a service runs inside a container, a port listening inside the container does not prove the port is published or routed externally.

If no process is listening:

1. Check whether the JVM received the right system properties.
2. Check startup logs for JMX agent errors.
3. Check whether another process already occupies the port.
4. Verify the agent/connector was actually initialized.
5. Check bind addresses or local-only restrictions.

Do not start by opening firewall rules if the JVM itself is not listening on the expected endpoint.

## 10. Testing TCP from the Client Side

From the machine running JConsole or the monitoring agent, test each port.

Linux/macOS:

\`\`\`bash
nc -vz jmx.example.internal 9010
nc -vz jmx.example.internal 9011
\`\`\`

Windows PowerShell:

\`\`\`powershell
Test-NetConnection jmx.example.internal -Port 9010
Test-NetConnection jmx.example.internal -Port 9011
\`\`\`

If \`nc\` is unavailable, use an OS-appropriate TCP check tool. A TCP connection result only proves a socket is open or reachable; **it does not verify the JMX handshake, SSL, authentication, or MBean lookup**.

Interpretation:

| Result | Possibility | Next Step |
|---|---|---|
| Connection refused | No listener or rejected | Check process/listen/host |
| Timeout | Firewall, network path, routing, or target not responding | Check rules and routes |
| Port 9010 OK, 9011 fails | RMI endpoint blocked/unbound/wrong host | Check rmi.port and stub |
| Both TCP OK, JMX fails | TLS, authentication, URL, RMI hostname, or protocol | Inspect JMX handshake |
| JMX connect OK, MBean missing | Wrong MBeanServer/ObjectName/exporter | Inspect registry |

A TCP test does not guarantee the endpoint is actually a JMX service. Another process could occupy the port; correlate the result with the PID on the server.

## 11. Connecting with JConsole

Launch JConsole using a compatible JDK:

\`\`\`bash
jconsole
\`\`\`

Select remote process and supply the endpoint or service URL as supported by JConsole/JDK.

Example service URL:

\`\`\`text
service:jmx:rmi:///jndi/rmi://jmx.example.internal:9010/jmxrmi
\`\`\`

Workflow:

1. Confirm the client-side hostname resolves to the intended address.
2. Verify both the registry and RMI endpoint are reachable.
3. Prepare authentication credentials and trust configuration if TLS is enabled.
4. Connect JConsole.
5. Open the **MBeans** tab and locate the application domain/ObjectName.
6. Read attributes or test **read-only/non-destructive** operations.
7. If connected yet no MBeans appear, check the MBeanServer used by the connector and exporter.

Depending on the JDK, JConsole may require JVM options to use a truststore or specific authentication mechanism. Avoid placing passwords on the command line or in unprotected log files.

## 12. Testing with a Java Client Instead of Only a GUI

An example JMX client:

\`\`\`java
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

public class JmxClientProbe {
    public static void main(String[] args) throws Exception {
        JMXServiceURL url = new JMXServiceURL(
            "service:jmx:rmi:///jndi/rmi://" +
            "jmx.example.internal:9010/jmxrmi"
        );

        try (JMXConnector connector =
                 JMXConnectorFactory.connect(url)) {

            MBeanServerConnection connection =
                connector.getMBeanServerConnection();

            ObjectName name = new ObjectName(
                "app.management:type=Queue,name=orders"
            );

            System.out.println(
                "registered=" + connection.isRegistered(name)
            );

            if (connection.isRegistered(name)) {
                System.out.println(
                    "MBeanClass=" +
                        connection.getMBeanInfo(name).getClassName()
                );
            }
        }
    }
}
\`\`\`

The example above does not provide credentials or an SSL environment. For connectors requiring authentication, pass appropriate configuration in the environment map or configure the client per the current JDK's JMX documentation; never disable authentication to make an example work in production.

Being able to invoke \`isRegistered\` successfully shows the connection goes through JMX and queries the registry. Yet an absent ObjectName can still mean the exporter has not registered it or uses a different MBeanServer.

## 13. Checking Hostname, DNS, and the Advertised Address

On the client, check:

\`\`\`bash
nslookup jmx.example.internal
\`\`\`

or use an appropriate DNS command:

\`\`\`bash
getent hosts jmx.example.internal
\`\`\`

Compare the result with the address permitted by firewall/service routes. Since RMI has two steps, also find out which host/port the stub advertises.

Typical indicators:

- Client reports a connection error to a hostname different from the original URL's hostname.
- Stack trace contains a container's private IP.
- Registry lookup succeeds, yet the JMX handshake times out.
- Clients on the same server connect, while clients from other networks cannot.

Focus on checking \`java.rmi.server.hostname\`, rmi.port, port forwarding, and network topology. Never "fix" it by opening a wide, unscoped port range.

## 14. Docker and Port Publishing

With Docker, think of two sets of ports: container ports and host ports.

\`\`\`text
JConsole on host/network
        |
        | host:9010 / host:9011
        v
Docker port publish
        |
        | container:9010 / container:9011
        v
JVM built-in JMX RMI agent
\`\`\`

Illustrative Docker Compose configuration snippet:

\`\`\`yaml
services:
  application:
    image: example/java-app
    ports:
      - "9010:9010"
      - "9011:9011"
    environment:
      JAVA_TOOL_OPTIONS: >-
        -Dcom.sun.management.jmxremote
        -Dcom.sun.management.jmxremote.port=9010
        -Dcom.sun.management.jmxremote.rmi.port=9011
        -Djava.rmi.server.hostname=jmx.example.internal
        -Dcom.sun.management.jmxremote.authenticate=true
        -Dcom.sun.management.jmxremote.ssl=true
\`\`\`

This illustrates **topology**, not a complete production configuration: you still need authentication files, TLS/key material, published interface restrictions, Docker networking, and firewalls. If the hostname in the stub is unreachable from the client, it will still fail even with both ports published.

For local testing on a single machine, port forwarding/tunneling can restrict access scope. Ensure the address advertised by RMI is compatible with the tunnel path; not every arbitrary NAT port-mapping configuration works with Java RMI.

## 15. Kubernetes: Service, Pod, and NetworkPolicy

In Kubernetes, JMX RMI errors commonly relate to the advertised endpoint and pod forwarding mechanisms:

- The container inside the pod listens on JMX ports.
- \`Service\` exposes the registry and RMI ports.
- \`NetworkPolicy\` allows traffic from approved namespaces/clients.
- The RMI stub must advertise an address the client can actually reach.
- A load-balanced service across multiple pods may route the lookup and the endpoint call to **two different pods**, causing failures.

With RMI-style management endpoints, you typically need to connect to **a specific instance** rather than distributing randomly across replicas. One approach is port-forwarding to a pod or a properly managed per-pod endpoint, combined with authentication and security.

Do not assume a shared load-balanced Kubernetes Service is always suitable for stateful RMI sessions.

Example diagnostic commands:

\`\`\`bash
kubectl get pods -n application
kubectl get svc -n application
kubectl describe svc jmx-service -n application
kubectl get networkpolicy -n application
\`\`\`

Resource names and namespaces here are examples only. Never alter production NetworkPolicy or make a service public solely to access JConsole.

## 16. Firewalls and Security Groups: Least Privilege

Remote JMX is a **JVM administrative channel**. It can allow clients to read attributes, invoke operations, and alter runtime state depending on permissions.

You should:

1. Expose it only within a private network or through a controlled administrative path.
2. Restrict source IPs/subnets to monitoring hosts or bastions.
3. Enable appropriate authentication/authorization.
4. Use TLS whenever data crosses unprotected networks.
5. Never use \`authenticate=false\` and \`ssl=false\` on a public port.
6. Manage credentials in a secret manager or files with strict permissions.
7. Restrict MBeans/operations with side effects; avoid exporting sensitive APIs.
8. Monitor unusual access and establish procedures for revoking privileges.

Monitoring tools typically only need **read** access, not permission to invoke state-changing operations. Design permissions accordingly instead of giving every client readwrite access.

## 17. JDK Versions and Security Configuration Changes

Across different JDKs, there may be changes in:

- Default enabled TLS protocols/ciphers.
- Mechanisms for reading password/access files and file permission requirements.
- Management agent configuration properties.
- How local attach and remote management are initialized.
- Serialization/filter policies or restrictions on legacy protocols.
- Default behavior regarding local-only mode and socket binding.

Therefore, when upgrading the JDK:

\`\`\`text
Before upgrade:
  server JDK version
  client JDK version
  JMX agent flags
  hostname + registry port + RMI port
  TLS/auth settings
  firewall rules

After upgrade:
  re-verify all of the above factors
  + confirm actual JConsole/monitoring agent connectivity
\`\`\`

Do not just check \`java -version\` on the host; verify the binary/JVM runtime of the exact process. If new errors appear after an upgrade, check JDK changes, truststores, security properties, and handshake logs before modifying firewall rules.

## 18. Diagnosing by Symptom

| Symptom | Likely Cause | What to Check |
|---|---|---|
| No listening port | Agent not enabled, misconfigured, startup failure | VM flags, process, logs |
| TCP connection refused | No listener or rejected | PID, bind address, port |
| TCP timeout | Firewall, routing, network policy | Source/destination, subnet, rules |
| Registry port OK, endpoint port fails | RMI port not pinned, endpoint blocked | \`jmxremote.rmi.port\`, \`ss\`, firewall |
| Connects to unexpected IP | RMI stub advertises wrong hostname | \`java.rmi.server.hostname\`, DNS/NAT |
| \`SSLHandshakeException\` | Incompatible TLS version/cipher/truststore | JDK, cert, client trust |
| Authentication failure | Wrong credentials or access control | Credential source, file permissions |
| JMX session OK yet MBeans missing | Exporter/connector use different servers or wrong ObjectName | \`getMBeanInfo\`, \`queryNames\` |
| Can query MBean yet invoke fails | Signature, permissions, implementation exception | Metadata and cause |
| Flaky connections in k8s | Load balancing across pods, unstable endpoint | Per-pod endpoint and service routing |

## 19. Layer-by-Layer Verification Process

A troubleshooting workflow can follow this order:

\`\`\`text
[1] Right JVM and JDK version?
        |
        v
[2] JMX agent / connector enabled?
        |
        v
[3] Registry and RMI endpoint ports defined?
        |
        v
[4] Right bind/listen address and PID?
        |
        v
[5] DNS + route + firewall for both ports?
        |
        v
[6] Hostname/port advertised by RMI stub reachable?
        |
        v
[7] TLS + authentication succeed?
        |
        v
[8] JMXConnector connects?
        |
        v
[9] Right MBeanServer and ObjectName?
        |
        v
[10] Read metadata/attributes and test safe operations
\`\`\`

Layering prevents "fixing the wrong thing". Do not tweak Spring annotations when TCP is actually blocked, and do not widen firewalls when the client simply lacks a TLS truststore.

## 20. Pre-Operations Checklist

- [ ] Verified the target JVM/PID and server JDK version.
- [ ] JConsole/agent client uses compatible JDK and TLS settings.
- [ ] Distinguished Spring export from the JMX remote connector.
- [ ] Identified the ObjectName of the MBean to observe.
- [ ] Identified the actual registry port and endpoint port.
- [ ] If static firewall rules are required, configured \`jmxremote.rmi.port\` accordingly.
- [ ] \`java.rmi.server.hostname\` points to an address reachable by clients.
- [ ] Host, cloud, and container network policies allow only approved sources.
- [ ] DNS/routing/NAT verified against the address inside the RMI stub.
- [ ] TLS/authentication/authorization configured and genuinely tested.
- [ ] Have a way to test TCP on each port from the client machine.
- [ ] Tested actual JMX connectivity, not just socket reachability.
- [ ] Connector and exporter use the same intended MBeanServer.
- [ ] Appropriate operational logging is enabled without leaking passwords/secrets.
- [ ] Remote JMX is not exposed to the public Internet.

## 21. Practice Exercises

### Scenario A: Registry Port Open, JConsole Times Out

JVM:

\`\`\`text
-Dcom.sun.management.jmxremote.port=9010
\`\`\`

No flag pinning the RMI endpoint port.

**Question:** Why does \`nc -vz host 9010\` succeed while JConsole still times out?

**Hint:** the client may receive an RMI stub containing another endpoint using a dynamic port blocked by the firewall. Identify and pin the endpoint port if required by infrastructure, then verify the corresponding network path.

### Scenario B: Docker Publishes Both Ports, Still Fails

Configuration:

\`\`\`text
registry port: 9010
RMI port: 9011
stub hostname: 172.18.0.4
client location: outside Docker host
\`\`\`

**Question:** What needs to be fixed?

**Hint:** the advertised hostname must be reachable from the client; a private container IP may not be routable externally. Check \`java.rmi.server.hostname\`, published mappings, and security constraints.

### Scenario C: Both TCP Ports OK, Rejected

JConsole reports authentication failure after opening the connection.

**Question:** Will opening another firewall port solve this?

**Hint:** No. The error has reached the authentication layer; check credentials and access policies instead of opening more ports.

### Scenario D: JMX Connects Successfully, MBeans Not Found

The Spring exporter registers beans into a custom MBeanServer, while the connector exposes the platform MBeanServer.

**Question:** What should be done?

**Hint:** use the same MBeanServer for both exporter and connector, or connect to the server used by the exporter; verify with \`isRegistered\` and \`getMBeanInfo\` on the right instance.

## 22. Self-Check Questions

1. Does \`@EnableMBeanExport\` automatically open a remote JMX port?
2. Why can JMX RMI require two TCP ports?
3. What roles do \`com.sun.management.jmxremote.port\` and \`com.sun.management.jmxremote.rmi.port\` play?
4. Does \`java.rmi.server.hostname\` govern socket binding or the advertised endpoint?
5. Why does a reachable TCP port not prove JMX login succeeds?
6. When upgrading the JDK, which TLS factors might change?
7. Why can JMX RMI fail behind a load-balanced Kubernetes Service?
8. If JConsole connects yet cannot see an MBean, what is the right next check?
9. Why should you avoid opening remote JMX to all IPs for debugging?
10. When a timeout occurs, what process helps distinguish firewall, endpoint, and authentication issues?

## 23. Key Takeaways

\`\`\`text
Remote JMX = exporter + MBeanServer + connector + network + security

RMI/JNDI typically involves:
  registry lookup port
  + RMI connector endpoint port

Must check:
  JDK version
  + agent flags
  + bind/listen ports
  + advertised hostname
  + DNS/route/firewall
  + TLS/authentication
  + MBeanServer/ObjectName
\`\`\`

**Core principle:** opening the right port is only part of remote JMX. Check **both RMI steps**, the advertised address, network reachability, and security requirements thoroughly, and only then verify MBeans on the actual registry. Never use disabling security or widening firewalls as a default solution.