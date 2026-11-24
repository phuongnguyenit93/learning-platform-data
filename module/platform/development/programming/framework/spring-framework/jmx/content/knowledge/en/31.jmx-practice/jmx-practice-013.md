# Practice: Establishing a Security Checklist for Remote JMX in Spring Framework

## 1. Objectives and Context

Remote JMX allows tools such as JConsole, Java Mission Control, or monitoring agents to connect from another JVM/machine to read attributes, invoke operations, and subscribe to notifications. While very useful when administering Spring applications in staging/production, it also opens a **sensitive management surface**: an MBean can expose configuration, operational details, internal data, or even state-changing operations such as pausing workers, resetting statistics, or shutting down application components.

This lab belongs to **Spring Framework JMX → Practice** and focuses on building an **actionable, verifiable security checklist** before enabling remote JMX.

After this lesson, you will be able to:

- Explain the difference between **Spring `MBeanExporter`** and a **remote JMX connector**.
- Design defense layers: authentication, authorization, encryption, network restrictions, secrets management, and operation controls.
- Understand the roles of the RMI registry port, RMI server port, and `java.rmi.server.hostname`.
- Build checklists applicable to development, staging, and production.
- Test both **allowed** and **denied** cases when accessing JMX.
- Recognize insecure settings such as `authenticate=false`, `ssl=false`, public ports, or overly broad `readwrite` permissions.
- Integrate remote JMX into operational workflows with auditing, rotation, rollback, and periodic reviews.

## 2. What Is Remote JMX and Why Must It Be Secured?

A common architecture:

```text
JConsole / JMC / Monitoring agent
                 |
                 |  JMX over RMI
                 v
        Network / firewall / TLS
                 |
                 v
        Remote JMX connector
                 |
                 v
             MBeanServer
                 |
          +------+------+
          |             |
    Platform MBeans   Spring MBeans
    java.lang:*      com.example:*
```

`MBeanServer` is the JMX registry. Spring can use `MBeanExporter` or `@ManagedResource` annotations to register application beans into the registry. **Exporting an MBean does not mean the application has opened a remote JMX port.** A remote connector is an additional configuration on the JVM or application infrastructure.

A remote JMX client can do much more than read metrics:

```java
connection.getAttribute(name, "PendingCount");
connection.setAttribute(name, new Attribute("Paused", true));
connection.invoke(name, "restartWorker", new Object[0], new String[0]);
```

Access permissions must be designed around the nature of these actions. An endpoint meant only for system observability should never have permission to invoke state-mutating operations.

## 3. Defense-in-Depth Principle

No single setting replaces comprehensive security. Build multiple layers of control:

| Defense Layer | Purpose |
| --- | --- |
| Network exposure | Allow only approved management hosts/segments |
| Authentication | Verify client identity |
| Authorization | Restrict who can read/write/invoke |
| TLS | Protect data and credentials in transit |
| Secrets management | Prevent passwords/keys from leaking in repositories, logs, or images |
| MBean surface | Do not export unnecessary sensitive operations or attributes |
| Operational controls | Auditing, rotation, patching, incident response |
| Validation | Test allow/deny rules, connectivity, metadata, and operations |

**Foundational principle: deny by default.** Enable and grant access only after establishing a clear purpose, owner, client, and usage lifetime.

## 4. Checklist 1: Inventory Targets and JMX Surface

Before creating an endpoint, document:

- [ ] Which application/JVM needs remote JMX? Environment: dev, staging, production.
- [ ] Who is the operational owner and who approves the configuration?
- [ ] Which client needs to connect: JConsole, JMC, an automated agent, or a runbook?
- [ ] Is only **read-only monitoring** required, or are state-changing operations needed?
- [ ] Which MBeans will be exposed via the target server?
- [ ] Which ObjectNames/domains belong to the application's resources?
- [ ] Do any attributes contain secrets, PII, or internal topology?
- [ ] Do platform/third-party MBeans expose dangerous operations?
- [ ] Is the connection temporary for diagnostics or continuously active?
- [ ] Is there a safer observability mechanism (metrics endpoint / dedicated agent) that fits better?

Remote JMX typically exposes not only your application's MBeans, but also platform and third-party MBeans on the same server. **Never assess risk based solely on a single custom `@ManagedResource`.**

## 5. Checklist 2: Network and Endpoint Restrictions

- [ ] Never expose JMX ports to the public Internet.
- [ ] Place the connector on a private network, management VLAN, VPN, or secure tunnel.
- [ ] Restrict firewalls/security groups to approved management clients only.
- [ ] Verify inbound/outbound rules between clients and the server.
- [ ] Explicitly define the RMI registry port, RMI server port, and stub hostname.
- [ ] Check container/Kubernetes NAT, DNS, and port mappings.
- [ ] Do not rely on `localhost` as a sole security boundary.
- [ ] Restrict access through a jump host/bastion if needed.
- [ ] Configure network logging/alerts for anomalous connections.

Example RMI-based JMX service URL:

```text
service:jmx:rmi:///jndi/rmi://jmx.internal.example:9010/jmxrmi
```

This address typically handles lookup via the RMI registry, yet after lookup the client uses the RMI stub to connect to the server object. Consequently, **opening only a registry port may not be enough** for a full connection.

Some JDKs allow setting the registry port and RMI server port to the same value via `com.sun.management.jmxremote.port` and `com.sun.management.jmxremote.rmi.port`. Verify this on your actual JDK and network rather than assuming all connectors/JDKs behave identically.

## 6. Checklist 3: Authentication

- [ ] Always enable authentication for endpoints reachable across untrusted networks.
- [ ] Give each role/client a distinct identity or credential whenever possible.
- [ ] Do not share one broad password across all operators and agents.
- [ ] Never commit credentials to Git or bake them into Docker images.
- [ ] Protect password files with strict OS file permissions.
- [ ] Maintain a plan for rotation, revocation, and updates when personnel/access changes.
- [ ] Test that access without credentials fails.
- [ ] Test that invalid credentials fail without falling back to anonymous access.
- [ ] Have a response procedure if credentials are compromised.

The JDK management agent has password-file-based authentication, though it is only one option. In enterprise systems, you may prefer connecting over an organization-standardized mechanism such as a controlled VPN/tunnel or an appropriate connector/authentication provider.

### Example password file for a lab

```text
# jmxremote.password (illustrative values, do not use in real environments)
observer strong-example-secret-CHANGE-ME
operator another-example-secret-CHANGE-ME
```

This file must never be stored as deployment documentation with real passwords. With JDK password-file configuration, file permissions must satisfy JDK/OS protection requirements. On Unix systems, for example:

```bash
chmod 600 /secure/jmx/jmxremote.password
```

Beyond permission modes, ensure the file has the right owner and is not bundled into publicly distributed artifacts.

## 7. Checklist 4: Authorization and Least Privilege

Authentication answers "who is connecting"; authorization answers "what are they allowed to do".

The JDK management agent typically uses an access file to define administrative roles. Example:

```text
# jmxremote.access
observer readonly
operator readwrite
```

- `readonly`: appropriate for agents that primarily read data.
- `readwrite`: grants broader privileges and requires tight control.

**Warning:** `readwrite` roles can have wide-ranging impact on the JVM/application, beyond just the MBeans you explicitly created. A basic access file is not fine-grained authorization per business operation.

Checklist:

- [ ] Monitoring agents normally use `readonly` only.
- [ ] Do not grant `readwrite` to accounts that only read metrics.
- [ ] Operators with write privileges must have an approved business need.
- [ ] Test that `setAttribute` and `invoke` are rejected for `readonly` clients.
- [ ] Test that sensitive management operations can only be invoked under the proper role and workflow.
- [ ] If per-MBean/operation permissions are needed, implement and review a dedicated authorization mechanism; do not assume a basic access file suffices.
- [ ] Audit permissions against least privilege after every configuration change.

Do not confuse `@ManagedOperation(description = "...")` with a security annotation. That annotation describes the operation; **it does not control who can invoke it**.

## 8. Checklist 5: Protect Transport with TLS

- [ ] Enable encryption for remote management connections in environments requiring protection.
- [ ] Use managed certificates with expiration tracking and a rotation process.
- [ ] Ensure clients verify the server's identity/certificate under the chosen TLS policy.
- [ ] Verify truststore/keystore setup and private key access permissions.
- [ ] Never disable certificate verification as a temporary production workaround.
- [ ] Verify JDK/client support for organization-approved TLS protocols and cipher suites.
- [ ] Test the handshake with the actual client used in operations.
- [ ] Review protection requirements for the RMI registry/lookup path under your current JDK configuration.

Setting `com.sun.management.jmxremote.ssl=true` can enable TLS for the JMX management connector per JDK mechanics, though RMI registry and client setup details depend on the JDK/provider. Do not set one flag and assume the entire path and certificate verification satisfy all policies.

If using a VPN/tunnel, still clarify which layer is responsible for encryption and authentication, as well as the risks if the tunnel is misconfigured.

## 9. Example JVM Configurations for Remote JMX

### 9.1. Loopback-only lab

An example for **isolated experimentation on a personal machine**—never copy verbatim to production:

```bash
java \
  -Dcom.sun.management.jmxremote \
  -Dcom.sun.management.jmxremote.port=9010 \
  -Dcom.sun.management.jmxremote.rmi.port=9010 \
  -Dcom.sun.management.jmxremote.local.only=true \
  -Djava.rmi.server.hostname=127.0.0.1 \
  -Dcom.sun.management.jmxremote.authenticate=false \
  -Dcom.sun.management.jmxremote.ssl=false \
  -jar order-service.jar
```

**Do not treat `local.only=true` and hostname `127.0.0.1` as absolute proof that the network is blocked.** `java.rmi.server.hostname` primarily affects the hostname advertised in the RMI stub; socket binding behavior and `local.only` must be verified on your JDK. Inspect listening addresses using OS tools and firewall checks.

### 9.2. Production-oriented baseline configuration

Example of components that must be specified:

```bash
-Dcom.sun.management.jmxremote
-Dcom.sun.management.jmxremote.port=9010
-Dcom.sun.management.jmxremote.rmi.port=9010
-Dcom.sun.management.jmxremote.authenticate=true
-Dcom.sun.management.jmxremote.ssl=true
-Dcom.sun.management.jmxremote.password.file=/secure/jmx/jmxremote.password
-Dcom.sun.management.jmxremote.access.file=/secure/jmx/jmxremote.access
-Djava.rmi.server.hostname=jmx.internal.example
```

This is an **illustrative baseline**, not a complete production configuration. You must add TLS key/trust material, client configuration, network policies, and testing on your actual JDK/runtime. Management agent options can vary across JDK distributions/versions; always consult the documentation for the JDK you deploy.

Never put raw password values on the command line, to prevent secrets from appearing in process lists/logs. Paths to secret files may still be visible and must have appropriate permissions.

## 10. Checklist 6: Protecting Secrets and Configuration

- [ ] Keep password/access files outside the source repository.
- [ ] Do not place secrets in environment variables if your organization's pipeline/logging/process inspection easily exposes them; evaluate an appropriate secret injection method.
- [ ] Never print credentials in logs, exceptions, or debug output.
- [ ] Control backups and permissions of secret files.
- [ ] Enforce TTL/rotation policies on secrets.
- [ ] When rotating, verify connectors and clients use the new credentials properly.
- [ ] Never put real secrets in READMEs, test fixtures, or examples.
- [ ] Never leave password/readwrite role files inside unencrypted container layers or public images.
- [ ] Separate credentials across dev, staging, and prod.
- [ ] Have a revocation procedure if an operator's laptop or agent is lost or compromised.

Consider using your deployment environment's secret manager. The goal is to limit who can view, modify, or extract credentials.

## 11. Checklist 7: Limiting the MBean Surface

Spring can export beans via:

```java
@ManagedResource(
    objectName = "com.example.orders:type=QueueAdmin,name=Payment"
)
public class QueueAdmin {

    @ManagedAttribute
    public int getPendingCount() { return 12; }

    @ManagedOperation
    public void pauseIntake() { /* ... */ }
}
```

Before deploying:

- [ ] Export only attributes/operations necessary for operations.
- [ ] Review every operation that has side effects.
- [ ] Use a dedicated management adapter instead of exposing an entire business service API.
- [ ] Avoid attributes containing passwords, tokens, full request bodies, PII, or overly detailed internal state.
- [ ] Validate operation parameters and reject dangerous values.
- [ ] Never provide `eval`, arbitrary classloading, shell execution, or equivalent operations over JMX.
- [ ] Control error handling and do not leak stack traces or secrets in return messages.
- [ ] Enforce auditing and approval workflows for sensitive operations.
- [ ] Regularly inspect `MBeanInfo` of platform and third-party MBeans, not just custom ones.

### Safer management adapter

```java
public interface QueueService {
    int pendingCount();
    void pauseIntake();
}

@ManagedResource(
    objectName = "com.example.orders:type=QueueAdmin,name=Payment"
)
public class QueueManagementAdapter {

    private final QueueService service;

    public QueueManagementAdapter(QueueService service) {
        this.service = service;
    }

    @ManagedAttribute
    public int getPendingCount() {
        return service.pendingCount();
    }

    @ManagedOperation
    public void pauseIntake() {
        service.pauseIntake();
    }
}
```

An adapter narrows the JMX contract. However, even with a tiny adapter, remote JMX access can still reach **other MBeans** on the same `MBeanServer`. Restricting exports is one defense layer, not a substitute for network/auth controls.

## 12. Checklist 8: Protecting Operations with Side Effects

Actions such as `restartWorker`, `retryFailed`, `clearCache`, and `rebuildIndex` can impact availability or data.

- [ ] Review permissions before exposing.
- [ ] Limit invocation frequency and volume.
- [ ] Do not grant dangerous operations to `readonly` clients.
- [ ] Validate inputs.
- [ ] Expose before/after state so operators can confirm effects.
- [ ] Design operations to be idempotent where possible.
- [ ] For long-running operations, use a job ID/status instead of blocking indefinitely.
- [ ] When a remote call times out, **never blindly retry**, because the server may have already executed it.
- [ ] Emit audit events with principal, target instance, ObjectName, operation, timestamp, and outcome where supported.
- [ ] For high-impact tasks, prefer dedicated administrative channels with full approval/auditing over simple JMX.

An operation like `togglePaused()` is generally riskier than `setPaused(true)` if retries occur. Setting a target state is easier to make idempotent, though you still must account for side effects such as event publication.

## 13. Checklist 9: Verify Clients Connect Securely

A basic Java client can use:

```java
import java.util.HashMap;
import java.util.Map;
import javax.management.MBeanServerConnection;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXConnector.CREDENTIALS;
import javax.management.remote.JMXServiceURL;

Map<String, Object> env = new HashMap<>();
env.put(JMXConnector.CREDENTIALS, new String[] {
    System.getenv("JMX_USER"),
    System.getenv("JMX_PASSWORD")
});

JMXServiceURL url = new JMXServiceURL(
    "service:jmx:rmi:///jndi/rmi://jmx.internal.example:9010/jmxrmi"
);

try (JMXConnector connector =
         JMXConnectorFactory.connect(url, env)) {

    MBeanServerConnection connection =
        connector.getMBeanServerConnection();

    System.out.println(connection.getDefaultDomain());
}
```

In real projects, retrieve credentials via controlled secret management instead of assuming environment variables are always the best option. For TLS, the client needs proper trust configuration and must not disable server certificate verification. Add timeout/reconnect policies matching your connector provider and JDK.

**Never log `env` or credentials.**

## 14. Checklist 10: Negative Authorization Testing

A checklist that only verifies "the operator can log in" is incomplete. You must test accesses that **must be rejected**.

| Test Case | Expected Result |
| --- | --- |
| Connect without credentials | Rejected (when authentication is required) |
| Wrong username/password | Rejected |
| `readonly` account reads a valid attribute | Succeeds |
| `readonly` account invokes a write operation | Rejected |
| `readonly` account writes a writable attribute | Rejected |
| `readwrite` account performs an approved action | Succeeds, properly audited |
| Untrusted source IP connects | Blocked by network controls |
| Untrusted certificate / policy mismatch | TLS handshake rejected |
| Revoked secret | Cannot log in with old secret |
| Valid credential on wrong environment | Target verification procedure catches it |

To avoid business impact, use a **test MBean** with harmless operations in staging or an isolated environment. Never test `readwrite` by invoking operations that destroy production data.

When authorization fails, exceptions may be wrapped by the connector/JMX API. Tests should assert rejection and zero side effects rather than relying on an exact error message string.

## 15. Testing TLS and Server Identity

TLS verification checklist:

1. Clients connect only using approved trust material.
2. Connections with untrusted certificates are rejected.
3. Server hostname/identity verification policies are enforced per transport/client configuration.
4. Expiring certificates trigger alerts and are rotated ahead of expiry.
5. Private keys are readable only by the account running the JVM/connector.
6. Clients and servers disallow deprecated protocols/ciphers.
7. After JDK updates, test the end-to-end handshake instead of just checking the `ssl=true` property.

Note: RMI/JMX has TLS nuances regarding registry/stubs and socket factories. A JConsole client may require JDK-specific flags; test with the **actual tools** used in operations.

## 16. Network Testing: Do Not Check Only Whether a Port Is Open

A common operational failure:

```text
telnet jmx.internal.example 9010
-> connected

JConsole connect
-> failed
```

The cause may be that the RMI registry returns a stub pointing to another hostname/port.

Checklist:

- [ ] DNS resolves accurately.
- [ ] Registry port is reachable from approved clients.
- [ ] RMI server port is also reachable.
- [ ] The RMI stub advertises a hostname reachable by clients.
- [ ] Firewalls block unapproved clients.
- [ ] Container port publishing and `hostNetwork`/NAT are verified.
- [ ] Remote `getAttribute`/`queryNames` succeeds, not just TCP connect.
- [ ] When using an SSH tunnel, port mappings and the advertised hostname are compatible.

With containers, `127.0.0.1` inside a pod/container is not `127.0.0.1` on the client machine. Design proper network routing and avoid exposing endpoints publicly.

## 17. Checklist 11: Observability and Auditing

Monitor:

- Count and source IPs of JMX connections.
- Authentication failures.
- Authorization denials.
- Connector startup/shutdown and RMI/TLS errors.
- Latency of side-effecting operations.
- Status/counters of administrative tasks.
- Security configuration changes.
- Secret/certificate rotations and expiration dates.
- Anomalous access requests over time.

Not every JDK management agent provides detailed auditing for every `invoke` by default. If recording principal/operation is required for compliance, ensure an **implemented and tested audit mechanism**, such as in the management service/adapter or an appropriate connector authorization layer.

Logs must not contain passwords, TLS private keys, or sensitive data. Balance diagnostic utility with data minimization.

## 18. Checklist 12: Hardening and Version Updates

- [ ] Use a supported JDK distribution and apply security patches.
- [ ] Re-verify JMX/RMI/TLS flags still behave properly after JDK upgrades.
- [ ] Re-check Spring `MBeanExporter` and AOP proxies after framework upgrades.
- [ ] Audit third-party dependencies/agents for sensitive MBeans.
- [ ] Re-check file access permissions after redeploys/container rebuilds.
- [ ] Audit security group/firewall drift.
- [ ] Ensure no old debug endpoints remain open after an incident.
- [ ] Re-run allow/deny and TLS tests after upgrades.
- [ ] Maintain a rollback plan and designated owner.
- [ ] Document a runbook to disable the connector and revoke credentials if compromise is suspected.

Never treat remote JMX as a "set it and forget it" service. It requires lifecycle and security ownership just like any other management endpoint.

## 19. Sample Deployment Acceptance Checklist Table

You can use this table for a change request:

| Item | Acceptance Criterion | Suggested Evidence |
| --- | --- | --- |
| Endpoint exposure | Private/VPN/tunnel only, never public | Firewall rules, internal network scan |
| Authentication | Anonymous and invalid credentials rejected | Negative connection tests |
| Authorization | `readonly` cannot write/invoke | Harmless test MBean |
| TLS | Client verifies server; approved protocols | Handshake test/certificate review |
| Secrets | No secrets in repo/image/logs | Repo/image scanning, file permissions |
| MBeans | No unnecessary data/operations exposed | `MBeanInfo` inventory |
| RMI configuration | Registry + server ports and host accurate | Remote `getAttribute` from real client |
| Lifecycle | Connector can be stopped/revoked | Startup/shutdown test |
| Operations | Side effects bounded and auditable | Code review and integration test |
| Monitoring | Signals exist to detect errors/attacks | Dashboards/alerts |
| Version compatibility | JDK/Spring/JMC work together | Compatibility matrix tests |

If any criterion is not met, require formal risk acceptance or remediation before opening the endpoint under organizational policy.

## 20. Safe Practice Scenario

**Context:** a Spring application named `order-service` needs its queues observed from JConsole on an internal bastion.

### Step 1: Define requirements

- Purpose: read JVM memory, threads, and queue metrics.
- Users: one monitoring agent + one operator group.
- Write operations: not needed in the initial phase.
- Network: internal bastion/agent only.
- Duration: per approved operational need.

### Step 2: Prepare a read-only MBean

```java
@ManagedResource(
    objectName = "com.example.orders:type=Queue,name=Payment"
)
public class PaymentQueueMetrics {

    @ManagedAttribute
    public int getPendingCount() {
        return 12;
    }
}
```

Do not add state-mutating `@ManagedOperation` methods without a specific requirement.

### Step 3: Configure authentication and permissions

Use dedicated credentials for the observer with `readonly` access, and protect password/access files. Place files in a secret volume or managed configuration directory—never commit to the repository.

### Step 4: Enable TLS and restrict the network

Assign stable registry/RMI ports and an appropriate advertised hostname, opening the firewall only to the bastion/agent. Configure certificates and client truststores matching your JDK.

### Step 5: Test allow and deny cases

- Observer reads `PendingCount` successfully.
- Anonymous client cannot connect.
- Incorrect password cannot connect.
- Observer cannot execute writes/invokes.
- Hosts outside the allowlist cannot connect.
- Invalid client certificate/trust is rejected per policy.

### Step 6: Test lifecycle

Restart the JVM and verify the connector and MBean return under the expected endpoint/ObjectName. Follow the runbook to stop/revoke and verify the endpoint stops serving when disabled.

## 21. Incident Response and Emergency Shutdown

If remote JMX exposure or compromise is suspected:

1. Immediately restrict or block network access to the endpoint per incident procedures.
2. Revoke/rotate affected credentials and certificates.
3. Identify which JVMs, connectors, and MBeans may have been accessed.
4. Review available logs/audit records; if auditing was incomplete, document investigation limits clearly.
5. Inspect side-effecting operations and system/data integrity.
6. Patch/reconfigure the endpoint and verify negative tests.
7. Re-enable only after controls are approved.
8. Update runbooks/checklists to reduce recurrence risk.

Whether updating a password file while the JVM is running takes effect immediately depends on JDK/connector mechanics; never assume rotation is instantaneous. Restarting the connector/JVM and re-verifying may be required.

## 22. Misconceptions to Avoid

**"If the ObjectName is secret, nobody can call the MBean."** False. An ObjectName is a management identifier, not a credential. An authorized client can query and list MBeans.

**"TLS is enabled, so authentication is unnecessary."** False. TLS protects transport and may provide certificate-based identity depending on configuration, yet access permissions still must be designed.

**"Opening one firewall port guarantees remote JMX works."** False. RMI can use distinct registry and server endpoints.

**"Exporting only one Spring bean means remote clients only see that bean."** False. A connector to the `MBeanServer` can expose other platform and third-party MBeans.

**"A `readonly` account only blocks `invoke`, while `setAttribute` still works."** False. Read-only permissions must block state-modifying operations per the security implementation.

**"`@ManagedOperation` describes the operation, so only admins can call it by default."** False. Metadata annotations do not enforce authorization.

**"A timeout proves the operation did not run."** False. The call may have already produced side effects on the server before the response was lost.

**"Running on localhost needs no security."** Not always true. Localhost can be reached by untrusted processes on the host, port forwarding, or misconfigured containers/tunnels. Evaluate your actual threat model.

## 23. Compact Checklist for Change Review

```text
REMOTE JMX SECURITY ACCEPTANCE

[ ] Endpoint is necessary, with a clear owner and purpose.
[ ] No public exposure; firewall/allowlist/VPN/tunnel appropriate.
[ ] Registry port + RMI server port/hostname verified.
[ ] Authentication enabled; anonymous and invalid credentials blocked.
[ ] Readonly role for monitoring; minimal write privileges.
[ ] TLS/certificate/trust policy meets requirements.
[ ] Password, access, and key files have proper permissions/secrets management.
[ ] No credentials leaked in repos, images, or logs.
[ ] MBeans inventoried; no unnecessary sensitive data/operations exposed.
[ ] Dangerous operations have guardrails, input validation, and auditing.
[ ] Negative tests: auth, authz, TLS, and network all pass.
[ ] Remote getAttribute/invoke tests run using the real client and environment.
[ ] Authentication failures, connection anomalies, and config drift monitored.
[ ] Rotation, revocation, incident response, and shutdown runbooks ready.
[ ] JDK/Spring/connector compatibility tested.
[ ] Change approval, rollback plan, and acceptance evidence recorded.
```

## 24. Practice Exercises

1. Create a read-only `PaymentQueueMetrics`, export it via Spring JMX, and verify the MBean appears under a fixed ObjectName.
2. Create two roles in a lab: `observer readonly` and `operator readwrite`; verify `observer` cannot invoke write operations.
3. Place password/access files outside the repository and verify OS permissions.
4. Configure TLS in staging and connect with JConsole/JMC using approved trust material.
5. Intentionally misconfigure `java.rmi.server.hostname` in a lab, and record the symptom where clients look up the registry yet fail to invoke the MBean.
6. Test from a blocked host to verify firewall rules rather than relying only on config files.
7. Read `MBeanInfo` and list every writable attribute/operation before granting any client `readwrite` access.
8. Write a runbook to revoke credentials and shut down the endpoint upon detecting public exposure.
9. Re-run tests after upgrading the JDK or changing container base images.
10. Draft an acceptance report covering allow/deny tests, TLS, network, secrets, and lifecycle.

## 25. Self-Check Questions

- Why does enabling `MBeanExporter` not automatically open a remote JMX port?
- What is the difference between authentication and authorization?
- Is a `readonly` role suitable for a monitoring agent? Why?
- Does `java.rmi.server.hostname` guarantee sockets bind only to that address?
- Why might JMX over RMI require checking multiple endpoints?
- Why is `@ManagedOperation` not a security boundary?
- Does TLS replace least-privilege access control?
- Why should you run negative tests instead of only verifying successful connections?
- What happens if a remote client times out after invoking a side-effecting operation?
- When a credential is compromised, what must the incident response checklist do first?

**Key takeaway:** Securing remote JMX is more than setting a password. You must combine **network restrictions**, **authentication**, **least-privilege authorization**, **TLS**, **secrets management**, **MBean surface minimization**, **allow/deny testing**, and **operational runbooks**. Only consider an endpoint production-ready once those exact controls are verified on your actual JDK, client, and deployment environment.