# Protecting the Connector with Authentication and TLS in Spring Framework JMX

## Objectives

JMX is a powerful management interface: clients can read runtime attributes, invoke operations, change configuration, trigger reconnects, pause workers, clear caches, or perform expensive diagnostics. In Spring Framework, \`MBeanExporter\` and \`AnnotationMBeanExporter\` register beans onto the \`MBeanServer\`, while **securing remote connections** belongs to the JMX connector, JVM management agent, network configuration, and access control policy.

A remote JMX connection can work without being secure if it lacks user authentication or sends credentials over an unencrypted channel. Conversely, enabling TLS without authorization can still allow authenticated users to invoke dangerous operations. For production operations, you must combine **authentication, TLS, authorization, network isolation, audit, and lifecycle**.

After this lesson, you will be able to:

- Distinguish MBeanServer, JMXConnectorServer, JMXConnector, and MBeanServerConnection.
- Explain why authentication and TLS are two separate mechanisms that must be configured consistently on both server and client.
- Understand JMX RMI authentication options, password/access files, custom authenticators, and how credentials are passed.
- Set up a keystore/truststore model, verify certificates and hostnames without disabling security verification.
- Identify specific risks of the RMI registry, RMI stubs, multiple ports, firewalls, and containers.
- Organize read-only/control authorization, restrict access outside the management network, and record audit logs.
- Diagnose authentication failures, TLS handshake failures, and cases where registry lookup succeeds yet invocation fails.
- Build a testing, rotation, and safe operations checklist for JMX connectors.

## 1. JMX Security Boundaries

JMX consists of independent layers:

\`\`\`text
Spring ApplicationContext
    |
    | @ManagedResource / MBeanExporter
    v
MBeanServer
    |
    | JMXConnectorServer (server-side)
    | authentication + TLS + access policy
    v
Network boundary (firewall, VPN, tunnel)
    |
    v
JMXConnectorFactory / JMXConnector (client-side)
    |
    | credentials + TLS trust configuration
    v
MBeanServerConnection
    |
    +-- getAttribute(...)
    +-- queryNames(...)
    +-- invoke(...)
\`\`\`

In this model:

| Mechanism | Question It Solves |
|---|---|
| Authentication | Which client or user is connecting? |
| Authorization | Which components can that user read/invoke? |
| TLS | Is the connection encrypted and is the endpoint verified? |
| Firewall/network isolation | Who can reach the connector at the network layer? |
| Audit | Who did what, when, and on which MBean? |
| Input validation | Does the operation accept and process parameters safely? |
| Lifecycle management | Are connectors, certificates, and permissions managed across changes? |

**One mechanism does not replace the others.** TLS does not decide whether a user may invoke \`clearCache()\`; authentication does not ensure packets are encrypted; firewalls do not replace user identity and permission checks.

## 2. Why Is the JMX Connector a Sensitive Target?

A connector serving an MBeanServer can let clients read many MBeans at once, including JVM platform MXBeans and exported application beans. Operations can alter runtime state. If an untrusted client has invoke permission, the consequences can go far beyond leaking a few metrics.

Example MBean with:

\`\`\`java
@ManagedResource(
    objectName = "com.example.ops:type=Worker,name=Import")
public class WorkerAdministration {

    @ManagedAttribute
    public String getState() {
        return "RUNNING";
    }

    @ManagedOperation
    public void requestPause() {
        // Request pausing new job intake.
    }
}
\`\`\`

If the remote connector is exposed without authentication, someone outside operations may get the chance to invoke \`requestPause()\` via \`MBeanServerConnection.invoke()\`. Do not expect Spring annotations to protect this action by themselves. JMX export **exposes capability**, whereas who is permitted to use it must be enforced at management boundaries.

First design rule: **never leave an unprotected remote JMX endpoint on a public network**.

## 3. What Is Authentication?

Authentication establishes the client/user identity before permitting access to the MBeanServer. With JMX RMI, some JVM management agents support password file and access file configuration. Additionally, a custom \`JMXAuthenticator\` or identity-system integration can be applied when creating a dedicated \`JMXConnectorServer\`.

A Java client typically passes credentials via the environment map:

\`\`\`java
import java.util.HashMap;
import java.util.Map;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

JMXServiceURL url = new JMXServiceURL(
    "service:jmx:rmi:///jndi/rmi://jmx.internal:1099/jmxrmi");

Map<String, Object> environment = new HashMap<>();
environment.put(
    JMXConnector.CREDENTIALS,
    new String[]{username, password}
);

try (JMXConnector connector =
         JMXConnectorFactory.connect(url, environment)) {
    // Obtain MBeanServerConnection and query MBeans.
}
\`\`\`

\`JMXConnector.CREDENTIALS\` is a standard key in the JMX API. The \`String[]{username,password}\` form is commonly used with the JMX RMI management agent when password authentication is supported. Not every connector provider is required to accept the exact same credentials object; understand the contract of the provider implementation.

**Crucial point:** passing credentials via the environment map **does not automatically enable TLS**. A client can authenticate successfully while still using an unencrypted channel if the server and transport are configured insecurely.

### 3.1 Password File and Access File

In the JVM management agent model that supports JMX configuration files, distinguish:

- Password file: stores credential information used for authentication.
- Access file: maps identities to permissions such as \`readonly\` or \`readwrite\` according to the runtime mechanism.
- Other policies or authenticators: may be needed to apply more specialized permissions.

Do not commit password files to a repository, do not put passwords on the command line if the OS or monitoring tools can read process arguments, and restrict file permissions according to JVM runtime requirements.

Password/access files belong to the **JVM management agent**, not a feature provided by \`@ManagedResource\`. When creating a custom \`JMXConnectorServer\`, certain components must be configured separately in the environment or factory.

### 3.2 Authentication Does Not Equal Authorization

A validly logged-in user does not necessarily have permission to execute data-destructive operations. If an access policy only distinguishes read-only and read-write, it may not suffice to define permissions per MBean/tenant or per operation. When fine-grained control is needed, use a custom authorization layer, a management gateway, or another control plane with explicit permissions.

## 4. What Does TLS Protect?

TLS encrypts traffic in transit and can verify the server via certificates. In a mutual TLS (mTLS) setup, the server can also require the client to present a certificate to authenticate the peer, though mapping certificate identity to JMX permissions must be designed separately.

TLS addresses at least three goals:

1. **Confidentiality** — reduces the risk of third parties reading credentials, attributes, and operation parameters.
2. **Integrity** — detects tampering with data in transit.
3. **Endpoint authentication** — clients can verify they are connecting to the right server when the certificate chain and hostname are checked.

TLS only provides value when verification is properly enforced. A client using a trust-all certificate manager or disabling hostname verification just to “get connected” undermines endpoint authenticity and introduces man-in-the-middle risk.

## 5. Keystore, Truststore, and Certificates

### 5.1 Server-Side Keystore

The server needs a private key and certificate chain to prove its TLS identity, depending on how the connector/socket factory is configured. A keystore holds these components in a supported format such as PKCS#12.

Do not store private keys or keystore passwords in source code. Use a secret manager or proper key management mechanism, restrict file read permissions, and avoid printing keystore contents to logs.

### 5.2 Client-Side Truststore

The client must trust the server's CA or certificate chain. A truststore can hold CA certificates used to verify the endpoint. If certificates are issued by an internal organization CA, distribute trust anchors via standard procedures.

When the server rotates certificates, clients can experience TLS handshake failures if the certificate is untrusted, expired, missing an intermediate certificate, uses a disallowed algorithm, or fails hostname matching.

### 5.3 Hostname and SAN

If a client connects to \`jmx.ops.example.internal\`, the server certificate should have a Subject Alternative Name matching the hostname actually verified by TLS. In RMI environments, the host advertised in the stub may differ from the host in the registry URL. That is why endpoint hosts, DNS, certificates, and proxies/tunnels must be designed consistently.

Do not resolve certificate hostname mismatch errors by disabling hostname verification in production. Fix DNS, certificate SANs, or advertised endpoint configuration to match the architecture.

## 6. JMX RMI Can Use Multiple Network Connections

With a common Service URL:

\`\`\`text
service:jmx:rmi:///jndi/rmi://jmx.internal:1099/jmxrmi
\`\`\`

The client may go through two steps:

\`\`\`text
Client
   |
   | 1. Lookup at RMI registry, e.g., port 1099
   v
RMI Registry
   |
   | return connector stub
   v
Client
   |
   | 2. Connect to host/port in stub
   v
RMI ConnectorServer
   |
   v
MBeanServer
\`\`\`

If only the registry path is protected while the actual RMI endpoint remains unencrypted or improperly controlled, the system does not meet security requirements. Conversely, a firewall that opens the registry port while blocking the RMI endpoint lets JConsole look up the stub and then fail on invoke.

Inspect **every socket/transport** used by the deployment: registry, connector endpoint, JNDI provider if present, and callback/notification mechanisms when needed. Do not assume enabling a single SSL property automatically secures all components in every custom connector deployment.

## 7. Why Does the RMI Stub Hostname Matter?

An RMI server can export a stub containing a host such as \`localhost\`, a container's internal IP, or a hostname unresolvable from the client. When the client receives the stub, the subsequent connection step can fail even though registry lookup succeeded.

In some JVM management agent setups, properties such as \`java.rmi.server.hostname\`, \`com.sun.management.jmxremote.port\`, and \`com.sun.management.jmxremote.rmi.port\` affect the host/port advertised or used. Those properties belong to the respective JVM agent/RMI configuration, not a universal syntax for every custom JMXConnectorServer.

With TLS, fixing the endpoint helps both network policy and certificate verification. Avoid having RMI advertise a host that does not match the SAN or the hostname in the actual connection path.

## 8. Safe JVM Management Agent Configuration

A JVM management agent configuration may include properties such as:

\`\`\`text
-Dcom.sun.management.jmxremote
-Dcom.sun.management.jmxremote.port=<registry-port>
-Dcom.sun.management.jmxremote.rmi.port=<server-port>
-Dcom.sun.management.jmxremote.authenticate=true
-Dcom.sun.management.jmxremote.ssl=true
\`\`\`

These lines are only a **configuration skeleton**, not a complete production command. A real deployment requires password/access files or an authenticator, an SSL keystore, certificate trust, bind addresses, and firewalling. Supported options, defaults, and registry/connector SSL capabilities depend on the JDK distribution and version; check the documentation of the JVM you operate.

Do not enable:

\`\`\`text
-Dcom.sun.management.jmxremote.authenticate=false
-Dcom.sun.management.jmxremote.ssl=false
\`\`\`

on an endpoint reachable from an untrusted network for debugging convenience. That can open administrative access to many MBeans, not just the metrics you wanted to inspect.

### 8.1 What Must Be Defined in Deployment

- Registry port and RMI server port per the JDK/runtime in use.
- Public/internal hostname advertised by the RMI stub.
- Actual bind address/interface.
- Access policy from the management network.
- Authentication mechanism.
- Certificates, private key, CA trust, and rotation.
- Read-only/read-write roles or custom authorization.
- Auditing and limits on side-effecting operations.
- Port, connection, and shutdown lifecycle management.

## 9. Custom JMXConnectorServer in a Spring Application

An application can create its own connector server instead of relying on the default JVM management agent.

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.remote.JMXConnectorServer;
import javax.management.remote.JMXConnectorServerFactory;
import javax.management.remote.JMXServiceURL;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();

JMXServiceURL serviceUrl = new JMXServiceURL(
    "service:jmx:rmi:///jndi/rmi://localhost:1099/jmxrmi");

JMXConnectorServer connector =
    JMXConnectorServerFactory.newJMXConnectorServer(
        serviceUrl,
        connectorEnvironment,
        server
    );

// connectorEnvironment must be securely configured.
// A suitable registry is required for URLs using /jndi/rmi://...
connector.start();

// On shutdown:
// connector.stop();
\`\`\`

The example is an architectural skeleton and cannot be run in production without defining \`connectorEnvironment\`, SSL socket factories, and authentication. Crucially, the \`MBeanServer\` attached to the connector must be the same server where the Spring exporter registers MBeans.

If each Spring context independently starts a JMX connector on the same port, bind failures can occur. A connector should have one clear owner, typically in the bootstrap/infrastructure layer rather than individual domain modules.

### 9.1 Custom Authenticator

\`JMXConnectorServer.AUTHENTICATOR\` is the key for configuring an authenticator on the connector server in the JMX Remote API when supported by the provider. A \`JMXAuthenticator\` can verify credentials and return a \`Subject\` representing the identity.

However, a custom authenticator does not automatically enforce fine-grained permissions across all operations. The system needs a corresponding authorization policy, protection of data returned via MBeans, and reliable identity auditing.

If using a centralized identity system, do not write a minimal authenticator that compares hard-coded passwords and grants full permissions. Combine secret rotation, brute-force protection, redacted logging, and defined failure modes.

## 10. TLS Socket Factories and Server/Client Consistency

With RMI, TLS may involve \`SslRMIClientSocketFactory\` and \`SslRMIServerSocketFactory\` or equivalent SSL configuration, depending on the agent/provider. Both sides must agree on transport and trust configuration.

Points to verify:
- Does the server present a valid certificate?
- Does the client trust the certificate chain?
- Does hostname verification match expectations and is it actually enabled?
- Are protocols/cipher suites compatible and compliant with the security baseline?
- Are both the registry socket and connector socket protected per the architecture?
- Does the firewall allow the required endpoints?
- Does mTLS (if used) map certificate identity to appropriate permissions?

Do not treat a successful client connection as guaranteed proof that every hop uses TLS. Verify the configuration and test from the actual client network.

## 11. Spring Client-Side MBeanServerConnectionFactoryBean

Spring provides \`MBeanServerConnectionFactoryBean\` to create an \`MBeanServerConnection\` from a Service URL:

\`\`\`java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.support.MBeanServerConnectionFactoryBean;

@Configuration
public class JmxClientConfiguration {

    @Bean
    MBeanServerConnectionFactoryBean remoteConnection() {
        MBeanServerConnectionFactoryBean factory =
            new MBeanServerConnectionFactoryBean();
        factory.setServiceUrl(
            "service:jmx:rmi:///jndi/rmi://jmx.internal:1099/jmxrmi");
        return factory;
    }
}
\`\`\`

This only specifies where to connect; **it does not automatically enable authentication/TLS**. When the server requires credentials or custom SSL socket factories, the client must supply compatible environment settings and trust configuration. Never store passwords directly in Java source or \`application.yml\` committed to a repository.

If the remote JMX endpoint may be temporarily unavailable, decide explicitly whether connection happens at startup or lazily; do not let remote monitoring failures crash business flows unless the application requires it.

## 12. Read Permissions and Control Permissions

Many MBeans contain two kinds of capabilities:

\`\`\`text
Read-only:
  getQueueDepth()
  getEffectiveState()
  getHitCount()

State changing:
  requestPause()
  reloadConfiguration()
  clearCache()
  resetStatistics()
\`\`\`

An account that only needs observability should not have permission to invoke state-mutating operations. With the JVM agent's access file mechanism, review \`readonly\` and \`readwrite\` permissions against your specific JDK documentation. When per-domain, per-operation, or per-tenant permissions are required, use a management gateway or custom policy rather than giving everyone write access to the whole JMX registry by default.

**No Spring annotation automatically turns a JMX operation into an administrator-only operation.** HTTP controller security does not protect the JMX connector. Permissions must be designed at the proper ingress.

## 13. Authentication Is Not Enough If MBeans Expose Sensitive Data

Even read-only access can be dangerous if an MBean returns:

\`\`\`java
@ManagedAttribute
public String getDatabasePassword() { ... }
\`\`\`

Or returns raw request bodies, tokens, customer PII, or connection strings containing secrets. Do not expose such data. Design a small management interface containing only summaries and redacted metrics.

Better example:

\`\`\`java
@ManagedAttribute
public String getDatabaseConnectionState() {
    return "CONNECTED";
}

@ManagedAttribute
public long getConnectionErrorCount() {
    return 0L;
}
\`\`\`

Protecting the connector is one layer, but **minimizing the MBean surface** is another critical layer. If sensitive data is not exported, leakage risk drops even if credentials are compromised.

## 14. TLS Termination and Proxies/Tunnels

Some deployments use a VPN, SSH tunnel, or network proxy. Never assume a tunnel completely replaces JMX authentication/authorization. A tunnel can protect transport between hops, yet the endpoint, the host advertised by the RMI stub, and network policies still must be controlled.

If using SSH port forwarding to the registry port, the RMI stub may point to another port/host so the client still fails. You may need to pin the RMI port, ensure the stub hostname aligns with the tunnel path, and check certificate hostnames if TLS operates at the JMX layer.

TLS termination at a proxy must be designed explicitly: is the segment from proxy to connector encrypted or inside an appropriate trust boundary? Do not overlook an unprotected hop simply because the client speaks HTTPS/TLS to the proxy.

## 15. Logging and Auditing

A management system should capture:
- Time of connection attempt/success/failure.
- Source network or client identity when trustworthy.
- Authentication outcome (without logging passwords).
- Side-effecting operation invocations.
- ObjectName, operation name, redacted parameters.
- Request ID or correlation ID.
- Result: accepted, rejected, succeeded, failed, and duration.

Audit example:

\`\`\`text
timestamp: 2026-11-11T08:00:00Z
principal: ops-reader-01
event: jmx.operation.attempt
target: com.example.ops:type=Worker,name=Import
operation: requestPause
result: REJECTED_NOT_AUTHORIZED
\`\`\`

This is an illustrative audit structure; do not assume an MBean method inherently has a trusted principal. If identity is merely passed in a caller-supplied argument, that is not proof of authentication. Identity and permissions should be wired from the actual security boundary.

## 16. Credential Rotation and Certificate Lifecycle

A secure connector is not configured once and forgotten. Operational plans need:
1. Owners for credentials, keystores, and truststores.
2. Certificate expiration dates and advance expiry alerts.
3. Procedures to create, distribute, and revoke credentials.
4. Verification of zero-downtime rotation or explicit maintenance windows.
5. Recovery procedures when truststores go out of sync.
6. Secure secret storage rather than reading from public config.
7. Documentation of JDK/provider versions and supported properties.
8. Post-rotation testing using real least-privilege accounts.

In multi-JVM systems, replacing a certificate does not necessarily mean all clients update trust simultaneously. A controlled transition period trusting both old and new CAs/certificates may be needed before retiring old values. Do not extend broad trust states longer than necessary.

## 17. Diagnosing Authenticated and TLS Connection Failures

| Symptom | Possible Failure Layer | Investigation Path |
|---|---|---|
| Connection refused | Port/bind/firewall | Check listening server and network path |
| RMI registry lookup succeeds, invoke fails | Stub host/port or TLS endpoint | Check host/port inside stub and firewall |
| Authentication failed | Credentials, authenticator, account policy | Check secrets and access configuration |
| \`SSLHandshakeException\` | Certificate chain, protocol, truststore | Inspect TLS logs and trust chain |
| Hostname verification failure | SAN does not match host | Fix certificate or endpoint naming |
| Client reports unknown protocol/provider | Unsupported Service URL/provider | Check JMXServiceURL and JDK modules |
| Connection OK but MBean missing | Connector points to another server | Compare exporter and connector server |
| Read-only client fails to invoke operation | Authorization working or policy mismatch | Check access role and contract |
| MBean operation timeout | Network/provider or long operation | Do not blindly retry side-effecting calls |

### Recommended Check Sequence

\`\`\`text
A. Confirm Service URL, DNS, host, and port.
B. Check registry and actual RMI endpoint.
C. Check firewall/network policy.
D. Verify TLS certificate, trust, and hostname.
E. Verify authentication and role.
F. Obtain MBeanServerConnection.
G. Query expected ObjectName.
H. Read read-only attributes.
I. Only test control operations in an appropriate environment with proper permissions.
\`\`\`

Do not fix handshake errors by disabling TLS or trusting all certificates in production. Fix the root cause.

## 18. Safe Testing: Positive and Negative Cases

An integration test for a secured connector should verify:

- A client with valid credentials and valid truststore connects successfully.
- Invalid credentials are rejected.
- A client without credentials is rejected when required by the server.
- An untrusted certificate is rejected.
- A mismatched hostname is rejected when hostname verification applies.
- A read-only identity cannot execute control operations.
- An appropriately privileged identity reads expected MBeans.
- No sensitive MBeans exist outside the published scope.
- After stopping the connector, ports/resources are cleaned up.
- After rotating certificates or credentials, the new policy takes effect.

Do not run side-effecting tests in production merely to verify permissions. Use a test MBean in an isolated environment with harmless operations.

### Client Read-Only Verification

\`\`\`java
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;
import java.util.Map;

JMXServiceURL url = new JMXServiceURL(serviceUrl);

try (JMXConnector connector = JMXConnectorFactory.connect(
        url, Map.of(JMXConnector.CREDENTIALS,
                    new String[]{username, password}))) {
    MBeanServerConnection connection =
        connector.getMBeanServerConnection();

    ObjectName expected = new ObjectName(
        "com.example.ops:type=Worker,name=Import");

    if (!connection.isRegistered(expected)) {
        throw new IllegalStateException("Expected MBean not found");
    }

    System.out.println(connection.getAttribute(expected, "State"));
}
\`\`\`

This is a client skeleton. It does not configure the truststore/TLS by itself; it assumes the runtime environment provides trust and socket setup compatible with the connector. Do not print credentials and do not turn a read-only connectivity test into invoking dangerous admin commands.

## 19. Checklist for Spring JMX in Production

### Server

- Target MBeanServer is clearly identified.
- Connector server has an owner and lifecycle.
- Bound only to necessary network interfaces.
- Authentication enabled with identity management.
- TLS enabled per security baseline.
- Certificate/trust/hostname verified.
- RMI registry/connector ports restricted.
- No unprotected JMX endpoints exist.
- Read-only and control roles separated by policy.
- Sensitive operations removed or controlled.

### Client

- Service URL targets the right environment/JVM.
- Credentials retrieved from secret store, not hard-coded.
- Truststore/certificates kept up to date.
- No trust-all or disabled hostname verification.
- Connector closed on shutdown.
- Bounded retry/backoff.
- Do not retry side-effecting operations after timeout if outcome is unknown.
- Monitoring and auditing suffice to diagnose connection failures.

### Operations

- Monitor certificate expiry and credential rotation.
- Monitor connection failures and auth failures.
- Re-evaluate permissions when new modules/MBeans are exported.
- Re-check JMX access policy after JDK upgrades.
- Audit side-effecting actions.
- Maintain runbooks for network, RMI stub, TLS, and authentication failures.

## 20. Common Misconceptions

**“Having a username/password makes the connector secure.”** Not enough; transport needs protection and the server needs proper authorization.

**“Enabling TLS means every client is allowed to invoke operations.”** TLS only protects transport and verifies endpoints; permissions are a separate policy.

**“@ManagedResource automatically uses Spring Security.”** No; HTTP security does not automatically apply to the JMX connector.

**“Opening only the registry port is enough.”** RMI may use a second endpoint inside the stub.

**“Disabling certificate verification to fix errors is acceptable.”** Unsuitable for production; fix trust/hostname/certificates instead.

**“Read-only means there is no sensitive data.”** Getters can still return secrets or PII if poorly designed.

**“Separating ObjectName domains is authorization.”** Domains are namespaces, not security boundaries.

**“A custom MBeanServer creates complete isolation by itself.”** A separate server may still share the same JVM and trust boundary; proper connector/access policies are required.

**“Timeout means the operation did not run.”** No. The command may have executed while the response was lost.

## 21. Practice Exercises

**Exercise 1 — Authentication and TLS.** A service uses credentials in \`JMXConnector.CREDENTIALS\` but the connector has not enabled TLS. Explain the risks and the layers that need to be added.

**Exercise 2 — RMI in Containers.** A client can reach registry port 1099 but fails when invoking an MBean. The stub advertises an unreachable internal host. Fix the hostname, endpoint port, and firewall without exposing JMX publicly.

**Exercise 3 — Certificates.** The server certificate has a SAN for \`jmx.internal\`, and the client connects to another IP. Why can hostname verification fail and what is the proper fix?

**Exercise 4 — Authorization.** There are two roles: metric-reader and operations-admin. Design a way to allow metric-reader only to read attributes and operations-admin to invoke controls, while recording audit logs.

**Exercise 5 — Rotation.** JMX certificates are about to expire across hundreds of nodes. Design an update order for trust, server certificates, and client config to avoid widespread outages.

**Exercise 6 — Security Tests.** Write tests for valid/invalid credentials, valid/invalid truststore, and verifying a read-only role cannot invoke a reset command, using a harmless MBean in an isolated test environment.

## Summary

Securing a remote JMX connector is a multi-layered design. **Authentication** identifies clients, **TLS** protects data and verifies endpoints, **authorization** limits actions, while **network isolation, audit, and lifecycle** reduce operational risk. With JMX RMI, pay attention to registry lookup and connector stubs that may use multiple hosts/ports; every connection path must conform to TLS and firewall policies. The Spring exporter only publishes MBeans and does not secure the remote connector by itself. A trustworthy production deployment establishes least privilege, manages secrets/certificates, tests negative security cases, and avoids workarounds like disabling TLS or authentication.
