# Procedures to Disable or Revoke Remote JMX in Spring Framework

## 1. Objectives and Scope

Remote JMX allows operational tools to access `MBeanServer` over a connection from another JVM or machine. Common configurations use JMX RMI, which can be started by the **JVM management agent**, a Java-constructed `JMXConnectorServer`, or a Spring component such as `ConnectorServerFactoryBean`.

When a connection is found to be no longer needed, credentials are exposed, security policies change, or an application is being decommissioned, operations teams must know how to **disable or revoke remote JMX in a controlled manner**. Closing a single firewall port is sometimes insufficient; calling `stop()` on one connector does not guarantee other connectors are no longer active.

This lesson guides distinguishing these goals:

- **Temporarily blocking network access:** new clients cannot traverse the blocked network layer, yet the connector inside the JVM may still be running.
- **Stopping the JMX remote connector:** shutting down a specific endpoint owned by the application/JVM.
- **Revoking credentials or permissions:** invalidating authentication/authorization capabilities of an exposed principal or secret.
- **Removing configuration so it does not reopen:** adjusting JVM options, Spring configuration, and deployment manifests.
- **Verifying no remote access path remains:** inspecting effective configuration and testing connectivity from an authorized client perspective.

A safe procedure must consider **restartability**, **existing sessions/connections**, **monitoring continuity**, and **rollback capability**.

## 2. Map of Remote JMX Paths That May Exist

Not every application exposes JMX the same way:

```text
                          Application JVM
                +---------------------------+
                |        MBeanServer        |
                |             ^             |
                |             |             |
                |  JVM management agent     | <-- JVM flags / launcher
                |             |             |
                |  ConnectorServerFactoryBean| <-- Spring context
                |             |             |
                |  Custom JMXConnectorServer | <-- code/library
                +-------------|-------------+
                              |
                    RMI Registry / RMI stub
                              |
                    Network / firewall
                              |
                    Remote management client
```

All three sources can coexist in one JVM. For instance, a development team disables `ConnectorServerFactoryBean`, yet the JVM still launches with `-Dcom.sun.management.jmxremote.port=...`; as a result, remote JMX keeps listening on the port.

Therefore, the first step of any revocation procedure is **inventorying connector owners**, not starting by randomly editing one property.

## 3. Distinguishing Local JMX and Remote JMX

Local JMX is typically used by tools in the same JVM or via the JDK's local attach mechanism. Remote JMX requires a connector/network endpoint for remote clients to establish an `MBeanServerConnection`.

- `MBeanExporter` registers MBeans into `MBeanServer`.
- `JMXConnectorServer` exposes access to that server through a connector.
- `RMI Registry` serves stub lookups if the connector uses the JNDI/RMI model.
- The JVM management agent can open a remote endpoint via JVM-specific configuration.
- `spring.jmx.enabled` relates to Spring MBean export capability, **not a switch guaranteeing every remote JMX connector is disabled**.

In many situations, you need to **keep local MBeans** for in-JVM diagnostics while **blocking remote clients**. Do not rush to disable all MBean exporting when the goal is only revoking network access.

## 4. Phased Standard Procedure

A runbook should have four phases:

1. **Assess scope and urgency:** which endpoints, which JVMs, who is using them, and whether credentials were compromised.
2. **Cut off new access paths:** apply appropriate firewall/security group/network policy controls or stop the connector.
3. **Remove re-enablement sources:** update launch flags, Spring config, secrets, and deployment manifests.
4. **Verify and record:** inspect listeners/endpoints, run controlled client connection checks, update monitoring, audit records, and rollback plans.

For credential exposure incidents, prioritize immediate containment at the network/identity layer, then roll out durable changes. For planned shutdowns, notify monitoring owners so dashboards and alerts do not raise false alarms.

## 5. Inventorying JVM Management Agent Configuration

For remote JMX provided by the JVM agent, common properties include:

```text
-Dcom.sun.management.jmxremote
-Dcom.sun.management.jmxremote.port=9010
-Dcom.sun.management.jmxremote.rmi.port=9011
-Djava.rmi.server.hostname=jmx.example.internal
-Dcom.sun.management.jmxremote.authenticate=true
-Dcom.sun.management.jmxremote.ssl=true
```

Some environments also configure password files, access files, SSL socket factories, or start the management agent via attach tools. Do not infer remote JMX is protected solely from `authenticate=true`; check certificates, policies, file permissions, and how credentials are distributed.

To **prevent the remote agent from starting on the next run**:

- Identify the source of JVM options: systemd units, container commands, `JAVA_TOOL_OPTIONS`, `JDK_JAVA_OPTIONS`, startup scripts, IDEs, Helm charts, or platform configuration.
- Remove/update the options that actually enable the remote listener according to the JDK version and launcher.
- Do not merely change the hostname/port to another address while leaving the connector open if the goal is complete shutdown.
- Redeploy/restart the JVM under appropriate maintenance procedures so the new configuration takes effect.
- After restart, confirm no unintended remote connector remains.

**Note:** Deleting a line of configuration in a repository does not stop a running agent. Runtime action and verification on the live process are required.

## 6. Disabling a Spring-Managed Connector

If the application uses `ConnectorServerFactoryBean`, the Spring context lifecycle can start/stop the `JMXConnectorServer` owned by the factory. Example:

```java
import javax.management.MBeanServer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.support.ConnectorServerFactoryBean;

@Configuration
public class RemoteJmxConfiguration {

    @Bean
    ConnectorServerFactoryBean remoteConnector(
            MBeanServer mbeanServer) throws Exception {
        ConnectorServerFactoryBean factory =
            new ConnectorServerFactoryBean();
        factory.setServer(mbeanServer);
        factory.setServiceUrl(
            "service:jmx:rmi:///jndi/rmi://127.0.0.1:9010/jmxrmi"
        );
        return factory;
    }
}
```

This is an illustrative skeleton; registry, authentication, and TLS are not fully configured.

If remote JMX is controlled by Spring configuration, a clear design pattern places the connector bean behind a property:

```java
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;

@Configuration
public class OptionalRemoteJmxConfig {

    @Bean
    @ConditionalOnProperty(
        name = "management.remote-jmx.enabled",
        havingValue = "true"
    )
    ConnectorServerFactoryBean remoteConnector(
            MBeanServer server) throws Exception {
        var factory = new ConnectorServerFactoryBean();
        factory.setServer(server);
        factory.setServiceUrl(
            "service:jmx:rmi:///jndi/rmi://127.0.0.1:9010/jmxrmi"
        );
        return factory;
    }
}
```

Here `management.remote-jmx.enabled` is an **application-defined custom property**, not a standard Spring Boot property. Choosing a safe default means not creating the bean when the property is not enabled.

To apply changes to a running context, most static configurations require restarting/recreating the context; changing a property in a config file does not automatically destroy an already-created bean. If a runtime toggle mechanism exists, design synchronization and explicit stop/restart lifecycles carefully.

## 7. Stopping a Custom JMXConnectorServer by Lifecycle

For a connector created via the JMX API:

```java
import javax.management.remote.JMXConnectorServer;

public final class JmxConnectorOwner
        implements AutoCloseable {

    private final JMXConnectorServer connector;

    public JmxConnectorOwner(JMXConnectorServer connector) {
        this.connector = connector;
    }

    @Override
    public void close() throws Exception {
        connector.stop();
    }
}
```

If a component creates a connector via `JMXConnectorServerFactory.newJMXConnectorServer`, calling `stop()` must be managed by **the same owner**. Do not stop a connector shared with other applications without operational agreement.

Edge cases to review carefully:

- The connector might not have started yet when `stop` is called during cleanup.
- Multiple connectors may be attached to a single `MBeanServer`.
- The RMI registry may keep running after the connector stops; registry existence does not necessarily mean remote JMX is still active.
- Some clients or callback threads may still be using connections; verify behavior after stopping.
- If the Spring container owns the connector, prefer Spring's lifecycle rather than an external management thread stopping it asynchronously.

Do not use `MBeanServer.unregisterMBean(...)` as a substitute for stopping the connector. Unregistering individual MBeans only removes managed objects from the server; it does not close the network endpoint.

## 8. Firewalls and Network Policy: Rapid Containment

When emergency access blocking is needed, operations teams can restrict ingress to:

- The JMX RMI registry port.
- The actual RMI endpoint port advertised by the stub.
- Auxiliary connector ports if configured.
- The dedicated management network segment.

JMX RMI can use **two ports**: a registry port for lookup and an RMI endpoint port for invocations. Closing only the registry port may block new lookups, yet should not be treated as proof that all existing RMI connections/endpoints are invalidated.

In Docker/Kubernetes, inspect host port mappings, pod/service networking, firewalls, security groups, network policies, and port-forwards/tunnels. Do not look solely at container `EXPOSE` or a single isolated rule.

Operational steps:

1. Identify actual endpoints and routes from clients.
2. Apply deny rules or allowlists permitting only authorized sources.
3. Assess impact on monitoring tools relying on JMX.
4. Verify from the client network with an appropriate connectivity test.
5. Save changes into infrastructure-as-code so they are not overwritten in the next deployment.

Cutting network access is a **containment measure**, not a replacement for stopping the connector or revoking credentials when required.

## 9. Revoking Credentials and Access Rights

If a JMX secret is exposed, changing the port alone is insufficient: old credentials can still be used at another endpoint or if the endpoint reopens.

A revocation workflow should:

1. Identify all accounts/credentials accepted by the connector.
2. Locate where secrets are stored: password files, secret stores, deployment variables, client configurations.
3. Revoke or rotate credentials on the **server**, then update authorized clients.
4. Review permissions of each role/account; narrow privileges if needed.
5. Verify old credentials can no longer establish new sessions.
6. Verify new credentials work for legitimate clients while service continuity is maintained.
7. Check for pre-existing authenticated sessions created prior to rotation.

With the JVM management agent's password/access file mechanism, modifying files might not immediately apply new policies to all running connectors; behavior depends on implementation and initialization. Verify and restart the connector/JVM if necessary to ensure revocation truly takes effect.

When credential compromise is suspected, **rotation is only one step**. Inspect audit/network logs, review dangerous operations that may have been invoked, and resolve any lingering sessions or routes.

## 10. Securing Connections When Complete Shutdown Is Not Possible

In some systems, remote JMX remains necessary for operations. Instead of leaving broad permissions open, redesign access:

- Use a dedicated management network or controlled tunnel/VPN.
- Enable authentication and least-privilege authorization.
- Protect traffic with TLS and verify endpoint identity.
- Pin the RMI hostname and port so firewalls can control them cleanly.
- Restrict sensitive MBeans/operations.
- Audit access and state-mutating actions.
- Limit client counts and monitor anomalous activity.
- Never publish passwords or JMX URLs containing secrets in public documentation.

JMX connector security and application Spring Security are not identical. HTTP rules for `/actuator/**` do not automatically protect the RMI connector.

## 11. Distinguishing Stopping Remote JMX from Disabling Spring JMX Export

Some Spring Boot configurations use:

```properties
spring.jmx.enabled=false
```

This property can disable Spring Boot's JMX export mechanism under the corresponding auto-configuration. However, if the JVM management agent is still enabled via `-Dcom.sun.management.jmxremote.port`, the remote connector can still run and expose JVM platform MBeans.

Conversely, disabling the JVM remote agent does not necessarily remove local MBeans already registered by Spring.

Distinguish the goals:

| Goal | Mechanism to Review |
| --- | --- |
| Prevent other machines from accessing JMX | Stop remote connectors; network isolation; authentication |
| Stop exporting Spring-managed MBeans | Spring JMX/exporter configuration |
| Stop exposing Actuator endpoints via JMX | `management.endpoints.jmx.exposure.*` and Actuator configuration |
| Revoke a specific JMX user | Credential store/identity/access policy |
| Ensure no network listener after restart | Startup flags, connector beans, infra manifests |
| Clean up MBeans after context closes | Exporter unregistration and context lifecycle |

Do not treat disabling one layer as certification that all layers are disabled.

## 12. Checking State Before and After Changes

Before disabling:

- Record hostname, PID/JVM, container/pod, and deployment version.
- Record connector owner, service URL, and registry/RMI ports.
- List clients and monitoring tools actually using the endpoint.
- Record the credential/authorization mechanism without storing secrets.
- Confirm rollback procedures for approved changes.

After disabling, verify in two directions:

### 12.1. Server Side

Inspect JVM startup arguments and runtime configuration, processes listening on management ports, active connector beans, registry bindings, and internal access routes.

A closed TCP port is a useful signal, yet **does not prove every connector has stopped** if the application has multiple endpoints.

### 12.2. Client Side

Attempt a connection from a client that previously had access:

```java
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

JMXServiceURL url = new JMXServiceURL(
    "service:jmx:rmi:///jndi/rmi://jmx.example.internal:9010/jmxrmi"
);

try (var connector =
        JMXConnectorFactory.connect(url)) {
    throw new IllegalStateException(
        "Unexpected: remote JMX is still reachable"
    );
} catch (java.io.IOException expected) {
    System.out.println("Remote JMX unavailable via this path");
}
```

The snippet above only proves **one specific connection path failed**. `IOException` could stem from DNS or a network fault, not necessarily because the connector stopped. With authentication models, tests should distinguish old credentials being rejected from the endpoint no longer existing. A single test attempt is not enough to conclude all networks/clients have been revoked.

To verify credential revocation, test the old credential (without logging the secret) and expect authentication rejection, then test the new valid credential if some clients remain permitted.

## 13. Existing Sessions and Connections

With JMX RMI connections, operators often care whether revocation terminates already-open sessions.

- **Blocking new ingress** does not always immediately close established TCP sessions.
- **Rotating credentials** does not inherently terminate every previously authenticated session.
- **Stopping the connector** may halt connections/operations depending on implementation, yet behavior of clients holding stubs must be verified.
- **Restarting the JVM** usually closes all connectors owned by the process, though it also causes application downtime and requires approval under uptime requirements.

During severe incidents, inspect existing sessions with available evidence: connection audits, network flows, client disconnects, or a test keeping a client connection open prior to containment and attempting an action afterward.

Do not declare full revocation until both active sessions and re-enablement paths are addressed under the threat model.

## 14. Graceful Shutdown and Production Operations

For a planned shutdown, a sensible sequence is:

1. Announce the remote JMX shutdown window and rationale.
2. Identify dashboards/alerts depending on JMX and switch to suitable metric sources if available.
3. Prevent new session creation if supported by the design.
4. Stop or close the connector through its lifecycle owner.
5. Verify no unwanted listeners or registry bindings remain.
6. Update configuration sources so the connector does not auto-enable after restart.
7. Restart/redeploy if necessary.
8. Test access from relevant network zones and credentials.
9. Update operational documentation, inventory, runbooks, and change records.

Do not disable the MBean exporter if local monitoring or application code still needs `MBeanServer`. And do not unregister all JVM MBeans “just to be safe”: doing so can break memory, thread, and monitoring tools of other components.

## 15. Redeployment and Lingering RMI Registry Issues

When an application server or container keeps a JVM alive longer than a single Spring `ApplicationContext`, connectors can be recreated multiple times. If context shutdown fails to stop the connector cleanly:

- The port remains occupied on the next startup.
- The `jmxrmi` binding may point to an old endpoint.
- Classloaders from old deployments can be retained by the registry, connector, or listeners.
- Clients receive stale stubs and fail to connect.
- An `IGNORE_EXISTING` MBean configuration may mask cleanup bugs in MBean registration without fixing the connector.

In integration/redeploy tests, verify:

```text
Start context A -> remote JMX works
Close context A -> endpoint and owned registration disappear
Start context B -> remote JMX works with new instance
Close context B -> no leftover connector/registration
```

If the registry is owned by a shared service, do not unexport the shared registry merely to clean up context A's connector. Separate registry ownership from connector ownership.

## 16. Emergency Revocation Checklist

During unauthorized access or credential compromise incidents:

- [ ] Identify the relevant JVM/deployment, RMI Registry, and RMI endpoints.
- [ ] Block ingress from untrusted sources at the appropriate network layer.
- [ ] Inventory all connectors created by the JVM agent, Spring, or libraries.
- [ ] Stop unnecessary connectors via their proper owners.
- [ ] Rotate/revoke credentials and update server access policies.
- [ ] Handle existing sessions according to risk severity.
- [ ] Remove launcher flags and Spring configs that could reopen endpoints.
- [ ] Check for secrets in logs, env vars, configs, and deployment templates.
- [ ] Test connectivity from client perspectives across required network zones.
- [ ] Record results, operator, timestamps, and scope.
- [ ] Monitor startups/redeploys to catch remote JMX reopening.
- [ ] Ensure alternative monitoring services are ready where needed.

## 17. Post-Disable Troubleshooting Matrix

| Symptom | Possible Cause | Remediation |
| --- | --- | --- |
| Registry port closed yet old client still works | Open RMI session/endpoint | Check RMI server port and active flows |
| Spring connector stopped yet port remains open | JVM management agent or another connector | Inventory all owners |
| Removed JVM flags yet still open | Process not restarted or flags from another source | Check effective startup command |
| Old credentials still log in | Secret not applied, connector cache, or old session | Check auth mechanism and perform controlled restart |
| Port hidden yet internal service still accesses | Different network path or endpoint | Inventory bind addresses/routes |
| Dashboard loses metrics | Monitoring relied on remote JMX | Switch scrape/exporter or another source |
| Redeploy reopens connector | Config/Helm/template not updated | Update infrastructure-as-code |
| `Address already in use` error | Old registry or connector not cleaned up | Check ownership, stop/unexport |
| Disabled `spring.jmx.enabled` yet client still connects | Spring-independent agent/connector still running | Stop remote agent/connector |

This matrix guides diagnosis; it does not replace environment-specific verification evidence.

## 18. Regression Testing: Ensuring Remote JMX Does Not Reopen

A pipeline test or staging environment check can verify:

1. Deploy the application with remote JMX disabled.
2. Verify JVM startup arguments contain no unintended remote agent flags.
3. Verify the Spring context has no running connector bean under custom configuration.
4. Attempt connections to previously permitted JMX ports from an appropriate network.
5. Restart the JVM/application context.
6. Retry from the client to ensure the disabled state persists.
7. When adding a new config profile, verify it does not override the property and re-enable the connector.
8. Confirm local MBean monitoring still works if operationally required.

Do not use an `isRegistered` check on `MBeanServer` to prove remote JMX is disabled: local MBeans can still exist even after the network connector stops. Likewise, do not treat a single timeout as proof that security policies work properly.

## 19. Key Takeaways

**Disabling or revoking remote JMX is a multi-layered problem:** identify all connectors, block network paths when needed, stop endpoints with proper lifecycle management, revoke credentials/permissions, and fix configurations to prevent reopening. `spring.jmx.enabled=false` affects only part of the Spring JMX system and does not automatically shut down an independent JVM management agent. Verification must happen on both server and client sides, distinguish new connections from existing sessions, and include restart/redeploy tests to ensure durable results.
