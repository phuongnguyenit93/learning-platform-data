# JMX access control and security

JMX (Java Management Extensions) provides a management interface for Java applications through MBeans. In a Spring Integration application, JMX is commonly used to observe the state and metrics of message channels, endpoints, adapters, handlers, or other integration components. Some MBeans also expose management actions such as modifying attributes or controlling component lifecycles.

Therefore, JMX belongs to the **management plane**, separate from the message flow and protocols connecting to external systems. Having an adapter use HTTPS, SFTP, JMS, AMQP, or Kafka with strong authentication does not automatically protect the JVM's JMX port. If JMX access is overly permissive, unauthorized parties can read operational data or manipulate components actively processing messages. JMX permissions must be designed like administrative access to the application itself.

## Where does JMX sit in a Spring Integration application?

An integration flow typically consists of inbound or outbound data adapters, message channels, endpoints, and handlers. JMX does not replace those components, nor does it transport business messages. It provides an interface for management tools to query or invoke operations exposed by MBeans.

With Spring Integration, `IntegrationMBeanExporter` and the `@EnableIntegrationMBeanExport` annotation can register supported integration components as MBeans. The exact MBeans and exposed attributes or operations depend on the component type and framework version. Inspect the actual MBean list in a running environment rather than assuming every bean is exported or every internal attribute is accessible.

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.config.EnableIntegrationMBeanExport;

@Configuration
@EnableIntegration
@EnableIntegrationMBeanExport
public class IntegrationJmxConfiguration {
}
```

Enabling the exporter allows JMX tools to observe integration components. Enabling the exporter only provides manageability; it does not establish a complete security policy for remote JMX connections on its own. Authentication, authorization, transport encryption, and network restrictions must still be configured at the JVM or JMX connector layer.

## Identifying resources and actions to protect

Before enabling JMX, list the data and actions the operations team actually needs. For an adapter system, common categories include:

| Category | Examples | Risk of overly broad permissions |
|---|---|---|
| Observation | Endpoint status, message counts, error counters, processing durations | Leaks system topology, queue/channel names, processing rates, and operational details |
| Configuration | Readable or writable MBean attributes | Leaks connection config; misconfiguration can disrupt the integration flow |
| Control | Start, stop, or other exposed management operations | Halts endpoints, breaks sending/receiving messages, or mutates application state |
| Custom MBeans | Application-published information | Can leak sensitive data if tokens, credentials, headers, or payloads are exposed in management attributes |

Read access also needs scrutiny. Even a read-only account can gather system names, service addresses, status details, or metrics useful for mounting an attack. Never place broker passwords, private keys, access tokens, message contents, or personal data into MBean attributes. If payload diagnostics are needed, use a separate controlled mechanism with strict data and retention limits.

## Distinguishing local JMX and remote JMX

Local JMX allows tools on the same host or process namespace to attach to the JVM. This mechanism typically relies on OS permissions and process-attach capabilities. Accordingly, only trusted OS users should be permitted to run management tools or access the namespace hosting the JVM. Do not treat local JMX as a security boundary when multiple workloads or users share a host or container host.

Remote JMX typically uses the JDK's RMI connector. When remote JMX is enabled, the JVM may open both an RMI registry port and an RMI connector port. Pinning only one port while leaving the other dynamically assigned makes firewalls and network policies hard to control. Pin both ports explicitly, set an RMI address reachable by clients, and permit connections only from approved management networks or bastion hosts.

Example JVM configuration for an environment requiring remote JMX:

```text
-Dcom.sun.management.jmxremote
-Dcom.sun.management.jmxremote.port=9010
-Dcom.sun.management.jmxremote.rmi.port=9011
-Djava.rmi.server.hostname=jmx-host.internal
-Dcom.sun.management.jmxremote.authenticate=true
-Dcom.sun.management.jmxremote.password.file=/run/secrets/jmxremote.password
-Dcom.sun.management.jmxremote.access.file=/etc/jmx/jmxremote.access
-Dcom.sun.management.jmxremote.ssl=true
```

This is an example for the JDK management agent; paths, hostnames, and ports must be replaced with deployment-specific values. Port `9010` is the registry port in this example, and `9011` is the RMI connector port. `java.rmi.server.hostname` must be an address that management workstations can resolve and reach. If the application runs in a container or behind NAT, verify the network path for both ports from the client to the exact JVM.

If there is no remote management need, do not enable remote JMX. In production, prefer access over a dedicated management network, VPN, or bastion; never expose JMX ports on the public Internet or user networks. If the deployment platform already offers an alternative management mechanism that meets requirements, consider using it instead of opening an RMI connector.

## Authentication and authorization

With the JDK's remote JMX agent, enable authentication explicitly. Two commonly used files are the password file and the access file. The password file maps usernames to passwords; the access file defines each user's permission level.

Example access file:

```text
monitorUser readonly
operatorUser readwrite
```

`readonly` is intended for monitoring accounts that only need to read MBeans. `readwrite` grants broader privileges, including modifying attributes or invoking operations exposed by MBeans. Therefore, grant `readwrite` only to operations teams with clear accountability; never share an administrative account for dashboards or metrics collection jobs.

The password file may hold plaintext passwords. Protect the file with strict OS permissions: only the account running the JVM or an explicitly designated account should be able to read it. On Unix systems, owner-only read/write permissions are typically required; on Windows, apply equivalent ACLs. Keep the file outside source control and application images, fetch secrets from a secret manager or platform secret mount, and enforce password rotation. Never put real passwords into examples, logs, publicly stored deployment parameters, or runbooks.

The example above demonstrates basic per-user authorization. An access file does not replace fine-grained per-MBean permission design. If a group should see only a specific subset of MBeans or invoke only specific operations, design an appropriate authentication and access-control layer—such as a connector with a custom authenticator and `MBeanServerForwarder`. Test actual operations because a custom MBean may grant more power than expected.

## Transport encryption and network restrictions

Authentication does not encrypt data on the wire. Enable TLS on the JMX remote connector and manage certificates with the same rigor as other administrative services. When mutual identity verification is required, configure client certificate authentication (mutual TLS) and trust only the CAs or certificates of authorized management hosts.

Key deployment principles:

- Open pinned JMX ports only on required interfaces or network zones; firewalls, security groups, and network policies must restrict source addresses.
- Use valid certificates, verify hostnames and trust chains, and maintain renewal and revocation plans.
- Never disable authentication or TLS to quickly work around connection failures in production. Identify whether the failure lies in DNS, ports, firewalls, certificates, or credentials.
- Keep OS-level access to JVM processes and secret files minimal.
- Audit management activity according to platform policy. Never write passwords, tokens, or sensitive data into logs.

If the connector uses RMI, TLS and firewalls must be configured consistently for both the registry and the connector. Encrypting or opening only one port can let the client reach the registry and then fail when calling the connector. Test from the exact network and client machine the operations team will use.

## Spring Integration JMX vs. Spring Boot Actuator JMX

Both mechanisms often appear in the same Spring Boot application but serve different purposes:

- The Spring Integration JMX exporter publishes MBeans related to integration components, depending on component types and configuration.
- Spring Boot Actuator JMX exposure publishes Actuator endpoints as MBeans for JMX tools to query.

Example Actuator JMX configuration in `application.yml`:

```yaml
spring:
  jmx:
    enabled: true

management:
  endpoints:
    jmx:
      exposure:
        include: health,info,metrics
```

The actual list of endpoints depends on the Spring Boot version and which endpoints exist in the application. Include only the necessary endpoints; avoid wildcard `*` in production unless you have audited all data exposed by every endpoint. If the application enables both the Integration exporter and Actuator JMX, review both sets of MBeans. Protecting the JMX connector at the JVM layer still applies to remote connections, yet enabling one exporter does not automatically restrict the MBeans exposed by the other.

## Pre-production verification checklist

1. **Define requirements:** document exactly which metrics and operations the operations team genuinely needs. Disable remote JMX if unneeded.
2. **Audit MBeans:** list all MBeans and exposed attributes or operations in a staging environment. Inspect custom MBeans to ensure no credentials, payloads, or personal data are exposed.
3. **Create separate identities:** use read-only accounts for monitoring; separate accounts with mutation or control permissions for operators. Never share one account across multiple systems.
4. **Configure connectivity:** pin registry and connector ports, enable authentication and TLS, and restrict source networks.
5. **Test permissions:** connect with a monitoring account and confirm it can read required data without modifying attributes or invoking management operations. Test permitted actions separately with an operator account.
6. **Test failure modes:** test wrong credentials, invalid certificates, connections from unauthorized networks, and scenarios where RMI returns an unreachable address. These cases must fail securely.
7. **Post-deployment monitoring:** monitor JMX connection errors, permission changes, endpoint control actions, and administrative account usage. Rotate or revoke credentials when users change roles.

A minimal permission test can use JConsole or an equivalent JMX tool from a host on the management network. Connect under each role, read an allowed MBean, and then attempt a write or control operation in a test environment. Expected results: the read-only account is denied write/control actions, admin accounts only work from allowed network sources, and connections lacking valid certificates or credentials are rejected.

## Troubleshooting common issues

| Symptom | Causes to check |
|---|---|
| Cannot connect to JMX | JVM remote agent not enabled, wrong hostname, wrong registry port, blocked by firewall, or client cannot reach RMI connector port |
| Registry connects but MBean query fails | Connector port not open, RMI advertising an unreachable hostname, or NAT/network policy misconfigured |
| Login rejected | Wrong username/password, malformed password file, or JVM lacks read permission on the file |
| Login succeeds yet cannot invoke operation | Account has `readonly` access only, or the MBean does not expose that operation |
| Client reports SSL errors | Mismatched truststore/keystore, hostname, expired certificate, or client-auth config |
| Expected MBean is missing | Exporter not enabled, component unsupported by exporter, different domain/server configuration, or MBean not registered yet |

Never resolve errors by disabling authentication, disabling TLS, or granting `readwrite` to everyone. Use error messages and JVM logs to pinpoint which layer failed, then fix the hostname, port, certificate, file permissions, or exporter configuration accordingly.

## Principles to maintain

JMX enables operations teams to observe and control Spring Integration applications at the JVM level. Protect it by exposing only necessary MBeans, separating monitoring accounts from administrative accounts, enabling authentication and TLS on remote connectors, restricting network access, and guarding secrets with OS permissions. Whenever modifying adapters or adding custom MBeans, re-audit exposed data and operations as part of that change. That way, management tools support tracking message flows without becoming an uncontrolled backdoor into the application.
