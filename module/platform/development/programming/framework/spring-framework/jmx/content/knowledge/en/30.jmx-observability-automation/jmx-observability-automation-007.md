# Restricting Automation Account Permissions When Using Spring Framework JMX

## Lesson Objectives

After this lesson, you will be able to:

- Explain why automation accounts accessing JMX must follow the **least privilege** principle.
- Distinguish permissions for **connecting**, **reading attributes**, **registering notification listeners**, **writing attributes**, and **invoking operations**.
- Understand how JMX remote connectors, JDK authentication/authorization mechanisms, and management infrastructure affect the permissions of a monitoring bot or automation service account.
- Limit the management surface by separating **read-only MBeans**, **management operations**, and **transport/connectors**.
- Avoid confusing HTTP Spring Security with protecting remote JMX; never assume an account with network access is allowed to perform every operation.
- Plan credential rotation, auditing, network isolation, and permission testing for both positive and negative cases.
- Identify the limitations of simple access files and when a finer-grained authorization model is needed.

## 1. Why Do Automation Accounts Need Least Privilege?

Automation accounts may be used by:

- A monitoring collector periodically reading \`ThreadCount\`, \`HeapMemoryUsage\`, or custom attributes.
- A periodic SRE task checking queue depth.
- An alerting system reading JMX notifications.
- An operations bot executing approved actions, such as refreshing configuration.
- A CI job or maintenance tool needing time-bounded actions.

These accounts usually run **unattended** and may store credentials in a secret store, environment variables, or an orchestration system.

If the same account used to read metrics also has permission to call \`shutdown\`, \`resetAllCounters\`, \`clearCache\`, or write configuration, credential exposure can cause impact far beyond the original observability requirement.

Example:

\`\`\`text
Monitoring bot
    |
    | Need: read QueueDepth
    v
JMX remote connector
    |
    +-- QueueDepth [read]
    +-- pauseProcessing() [write-like operation]
    +-- clearAllData() [dangerous operation]
\`\`\`

If the bot only needs to read \`QueueDepth\`, do not grant permissions equivalent to administering the entire MBeanServer by default.

**Core principle:** Each automation identity should only be granted the exact permissions required to complete its defined task, on the right resources, in the right environment, and for the required duration.

## 2. JMX Differs from a Read-Only Metrics Endpoint

JMX can expose:

1. **Read-only attributes**: e.g., number of active connections.
2. **Writable attributes**: e.g., raising/lowering worker limits.
3. **Operations**: e.g., resetting state, restarting components, flushing caches.
4. **Notifications**: clients can subscribe to receive events.
5. **Metadata**: MBean names, attributes, operations, and descriptions.

A JMX client with overly broad access can view or use capabilities far exceeding metric collection needs.

Spring example:

\`\`\`java
@ManagedResource(
    objectName = "learning.jmx:type=Queue,name=Primary"
)
public class QueueManagement {

    @ManagedAttribute
    public long getPendingJobs() {
        return queue.pendingJobs();
    }

    @ManagedOperation
    public void pauseProcessing() {
        queue.pause();
    }
}
\`\`\`

A monitoring job may only need to call:

\`\`\`java
connection.getAttribute(name, "PendingJobs");
\`\`\`

Yet the same MBean also has the \`pauseProcessing()\` operation that causes side effects. Whether the operation can be invoked depends on the connector's actual permissions and additional control layers.

Do not rely on an informal convention such as “this bot only calls getters” as a security control.

## 3. Three Permission Layers to Distinguish

### 3.1. Network Reachability

Can requests reach the JMX host/port? Firewalls, VPNs, bastions, security groups, Kubernetes NetworkPolicies, or private networking typically handle this layer.

### 3.2. Authentication

How does the connector verify who is connecting? Depending on the runtime, this may use the JMX management agent's authentication configuration or authentication integrated by the application/connector.

### 3.3. Authorization

What actions is the authenticated identity allowed to perform? Read, write, and operation invocation must be distinguished.

\`\`\`text
Network policy:  Can the endpoint be reached?
       |
       v
Authentication:  Who is calling?
       |
       v
Authorization:   What is permitted?
       |
       v
MBeanServer:     Action on specific MBean
\`\`\`

Network isolation does not replace authentication. Authentication does not automatically mean read-only. TLS protects the transport channel but does not restrict which operations can be invoked.

## 4. Classifying Accounts by Role

Example permission design:

| Identity | Purpose | Desired Permissions |
|---|---|---|
| \`jmx-metrics-reader\` | Poll counters, gauges | Read-only; scoped only to required resources if the mechanism allows |
| \`jmx-health-reader\` | Health/diagnostics | Read-only, may require metadata |
| \`jmx-notification-reader\` | Subscribe to notifications | Access only to required broadcasters and listener registration |
| \`jmx-maintenance-operator\` | Selected maintenance operations | Bounded, controlled, and audited write/invoke permissions |
| \`jmx-platform-admin\` | Emergency technical administration | Broader permissions, granted only to managed workflows |

This is a **suggested role model**, not role names understood by Java JMX by default. To enforce per-MBean/operation authorization, choose an authorization mechanism that supports that level of granularity.

A single service account should not be shared between monitoring and high-risk maintenance actions merely because both use JMX.

## 5. JDK Remote JMX Access File: read-only and readwrite

The JDK management agent can support configuring authentication credentials and access control via files read by the JVM according to runtime configuration.

Illustrative access file:

\`\`\`text
monitorRole readonly
operatorRole readwrite
\`\`\`

General meaning:

- \`readonly\`: the account is restricted under the read-only policy enforced by the management agent.
- \`readwrite\`: the account can perform write/invoke operations within the bounds of the supported mechanism.

**Very important warning:** \`readwrite\` in basic configuration is not equivalent to “allowed to call only one specific operation.” Never grant readwrite to a monitoring account just because one convenient operation needs to run.

Configuration details and options vary across JDK versions and deployment models. Always check the documentation for the JDK in use; do not treat the snippet above as a complete production configuration.

### What If Only readonly/readwrite Is Available?

There are several options:

- Keep monitoring on \`readonly\`.
- Move state-changing automation to a separate workflow with its own managed identity and endpoint.
- Do not expose dangerous operations on an MBeanServer accessible to a readwrite account.
- Use a connector or authorization layer capable of enforcing finer-grained permissions if actually required.
- Build a dedicated maintenance API with proper authorization/auditing if the JMX access file is too coarse.

It is essential to evaluate **the granularity the runtime actually enforces**, rather than assuming per-operation RBAC exists when only a basic access file is configured.

## 6. Do Not Confuse Read Access with Operation Invocation Rights

Even if an operator sees an MBean in JConsole, do not infer it has permission to mutate state. Conversely, if an account has broad write/invoke rights, the fact that a script currently only calls getters is not a technical restriction.

Example:

\`\`\`java
MBeanServerConnection connection =
        connector.getMBeanServerConnection();

Object count = connection.getAttribute(
    new ObjectName("learning.jmx:type=Queue,name=Primary"),
    "PendingJobs"
);
\`\`\`

Another automation task might try:

\`\`\`java
connection.invoke(
    new ObjectName("learning.jmx:type=Queue,name=Primary"),
    "pauseProcessing",
    new Object[0],
    new String[0]
);
\`\`\`

Both calls use the same JMX connection but have different intents. Policy must ensure a read-only account is rejected when calling state-changing actions, rather than merely asking developers “not to call it.”

### Read-Only Can Still Leak Data

Read-only does not mean zero risk. Attributes may contain:

- Secrets or API keys if poorly designed.
- Hostnames, database connection strings.
- Internal topology details.
- Personal data.
- Configurations that could aid an attack.

Therefore, least privilege also includes **limiting exposed data** and **connection scope**, not only restricting action types.

## 7. Designing MBeans by Sensitivity Level

One architectural approach is separating read-only MBeans from administrative MBeans.

\`\`\`text
MBeanServer / connector for monitoring
    |
    +-- QueueMetricsView
    +-- CacheMetricsView
    +-- PoolStatusView

Management context / connector with stronger controls
    |
    +-- QueueAdministration
    +-- CacheAdministration
\`\`\`

Read-only facade example:

\`\`\`java
package example.jmx;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "learning.jmx:type=QueueMetrics,name=Primary"
)
public class QueueMetricsView {

    private final QueueService service;

    public QueueMetricsView(QueueService service) {
        this.service = service;
    }

    @ManagedAttribute(
        description = "Current number of waiting jobs"
    )
    public long getPendingJobs() {
        return service.pendingJobs();
    }
}
\`\`\`

Administrative facade:

\`\`\`java
package example.jmx;

import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "learning.jmx:type=QueueAdmin,name=Primary"
)
public class QueueAdministration {

    private final QueueService service;

    public QueueAdministration(QueueService service) {
        this.service = service;
    }

    @ManagedOperation(description = "Pause accepting new jobs")
    public void pauseProcessing() {
        service.pause();
    }
}
\`\`\`

Two separate classes clarify management contracts and make security reviews easier.

**However:** if both are exported into the same MBeanServer and every readwrite account has server-wide access, splitting into two ObjectNames **does not automatically create per-MBean authorization**. True enforcement is needed at the connector/policy layer, or isolation into separate controlled registries/connectors.

## 8. Do Not Assume Spring Security HTTP Protects JMX

A Spring Boot application may configure HTTP security for Actuator endpoints and REST APIs.

For example, HTTP requests pass through a SecurityFilterChain, whereas a JMX remote connector normally does not pass through that servlet filter chain.

\`\`\`text
HTTP client
    |
    v
Spring Security HTTP filters
    |
    v
HTTP endpoint

JMX client
    |
    v
JMX connector / MBeanServer
    |
    v
MBean operation
\`\`\`

Therefore:

- Securing \`/actuator\` does not mean remote JMX is secured.
- A \`@PreAuthorize\` on a service method only takes effect along the proper Spring method-security proxy/advice call path.
- If a JMX operation invokes the target directly, it may bypass advice in certain designs.
- Connector-level authentication/authorization and network policies are still required.

If sensitive operations exist, test them directly over JMX with both authorized and unauthorized accounts.

## 9. Managing Automation Account Credentials

Never store JMX credentials directly in source code:

\`\`\`java
// Do not hardcode.
String username = "monitorRole";
String password = "hardcoded-password";
\`\`\`

Instead:

1. Use a secret manager or organization-approved secrets management mechanism.
2. Grant secret read access only to the workloads that need it.
3. Avoid printing passwords, tokens, or private keys in logs.
4. Maintain a credential rotation lifecycle.
5. Do not share the same secrets across development, staging, and production.
6. Revoke identities/credentials when an automation job is no longer needed.
7. Control file permissions on authentication configuration files and keystores on hosts.

For Java client JMX remote username/password, credentials are typically supplied via the connector environment. How they are loaded from a secret source depends on infrastructure.

\`\`\`java
Map<String, Object> environment = new HashMap<>();
environment.put(
    JMXConnector.CREDENTIALS,
    new String[] { username, password }
);
\`\`\`

This illustrates the client API, not a complete security mechanism. Production requires proper TLS, connector trust, secret lifecycles, and identity management.

## 10. Never Disable Authentication or TLS

Options such as:

\`\`\`text
com.sun.management.jmxremote.authenticate=false
com.sun.management.jmxremote.ssl=false
\`\`\`

disable critical layers of protection. They must never be copied into production just to make connecting a bot easier.

If an automation account cannot connect:

- Verify credentials and policies.
- Verify certificate/trust configuration.
- Check hostname/RMI port/networking.
- Read exceptions and server logs.
- Check whether the account has been granted the proper permissions.

Do not solve errors by granting readwrite to every account or turning off authentication/TLS.

## 11. Network Permissions Are Part of Least Privilege

A bot that only needs to poll one JVM in production should not be able to reach every JMX endpoint across the organization.

You can restrict:

- Source IP or workload identity.
- Destination host/namespace.
- Connector port.
- Connection time windows via bastion/VPN when required.
- NetworkPolicies or firewall rules for the exact route.
- Never expose remote JMX to the public Internet.
- Never allow unmanaged CI runners free access to the production management network.

When using Kubernetes, \`kubectl port-forward\` permissions or rights to create debug pods can open a path to management endpoints. Include those possibilities in your threat model and audit against actual permissions.

## 12. Characteristics of JMX Remote Connectors

Remote JMX typically uses a connector, which may be based on RMI. An automation account reading data must:

1. Be able to connect to the endpoint.
2. Verify the right server identity when TLS is enabled.
3. Complete authentication.
4. Be authorized for the intended action.
5. Query the right MBeanServer/ObjectName.

A client hitting the wrong endpoint or JVM may see different MBeans than expected.

A JMX remote connector can expose many MBeans beyond custom Spring MBeans, including JVM platform MBeans and MBeans registered by third-party libraries. Therefore, you must evaluate the **entire accessible registry**, not just the few beans written by your team.

## 13. Notification Subscription Permissions

An automation job may register a \`NotificationListener\` to receive events:

\`\`\`java
connection.addNotificationListener(
    objectName,
    listener,
    filter,
    handback
);
\`\`\`

This is a management action that must be permitted by connector policy. Depending on the authorization mechanism, it may follow different rules than \`getAttribute\`.

Considerations:

- Does the bot truly need to subscribe to notifications, or is polling sufficient?
- Which MBeans are allowed to emit information to the bot?
- Do notification messages/userData contain sensitive data?
- How must the listener handle reconnects/re-registration?
- Could the credentials be reused for write operations?
- Are listener counts or registration load bounded?

Do not assume \`readonly\` permits every subscription operation across all JMX runtimes. Test actual permissions against your target JDK version and connector.

## 14. Auditing Automation Account Activity

For sensitive operations, capture:

- Who/what connected?
- What was the authenticated identity?
- Which operation was invoked?
- What were the ObjectName and parameters?
- Did the call succeed or fail?
- When did it occur?
- Was the action approved?

Depending on the JMX connector and runtime, not every call produces detailed audit logs automatically. Instrumentation may be needed in the management facade, connector layer, or execution workflow.

Example:

\`\`\`java
@ManagedOperation
public void requestMaintenance() {
    audit.record("maintenance requested");
    maintenanceService.request();
}
\`\`\`

However, do not treat a static log string like this as sufficient to know caller identity. When accurate caller auditing is required, propagate identity through a trusted mechanism with enforcement at the management layer.

Never log raw secrets or sensitive data in logs/audits.

## 15. Environment-Based Permission Separation

Development, staging, and production carry different risk levels.

Example:

| Environment | Monitoring bot | Maintenance bot |
|---|---|---|
| Development | Read-only or limited experimental permissions | Can use separate test identities |
| Staging | Read-only against test endpoints | Tested action permissions; no production secrets |
| Production | Minimal read-only | Write/invoke permissions per runbook and approval |

Accounts or secrets across environments must not be shared if compromising one credential could grant cross-environment access.

Even in development, an unauthenticated JMX endpoint can be accessed from a shared network; never assume safety just because of a “dev” label.

## 16. Read-Only Client Example

Java client snippet reading an attribute:

\`\`\`java
import java.util.HashMap;
import java.util.Map;

import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

public class ReadOnlyJmxClient {

    public static long readPendingJobs(
            JMXServiceURL url,
            String username,
            String password) throws Exception {

        Map<String, Object> env = new HashMap<>();
        env.put(
            JMXConnector.CREDENTIALS,
            new String[] { username, password }
        );

        try (JMXConnector connector =
                JMXConnectorFactory.connect(url, env)) {

            MBeanServerConnection connection =
                connector.getMBeanServerConnection();

            ObjectName queue = new ObjectName(
                "learning.jmx:type=QueueMetrics,name=Primary"
            );

            Object value =
                connection.getAttribute(queue, "PendingJobs");

            return ((Number) value).longValue();
        }
    }
}
\`\`\`

This is a simple client pattern. It does not depict secure credential storage, TLS configuration, timeouts, or auditing. In production, username/password must come from a controlled secret source; the endpoint needs proper authentication, authorization, and TLS.

A read-only bot should not have methods that call arbitrary \`invoke\` in its workflow if unnecessary.

## 17. Testing Positive and Negative Cases

Testing only that a reader account succeeds is insufficient. You must prove the account **is denied** actions outside its scope.

### Test Matrix

| Test | Reader | Operator |
|---|---|---|
| Connect to assigned endpoint | Allowed | Allowed |
| Read \`PendingJobs\` | Allowed | As needed |
| Invoke \`pauseProcessing\` | Denied | Only if approved |
| Write writable attribute | Denied | Only allowed attributes |
| Access another environment's endpoint | Denied | Denied unless separately granted |
| Read unnecessary sensitive data | Should not be exposed | Only with approved need |

When an authorization layer only supports coarse permissions, the intended matrix cannot be enforced automatically. In that case, change the architecture to separate registries/connectors or APIs rather than just naming roles nicely.

### Practical Testing

A technical test can:

1. Start a protected connector in a test environment.
2. Connect with reader credentials.
3. Read an allowed attribute and verify its value.
4. Attempt a state-changing action on a safe test MBean.
5. Verify access is denied at the appropriate layer.
6. Connect with operator credentials and test an allowed operation.
7. Shut down the connector and clean up the MBeanServer and test credentials.

Never execute destructive operations in production to prove permissions; use a dedicated test fixture.

## 18. Never Mix Bot Identities with Human Operator Identities

A human operator and an automation bot have different requirements:

- Humans can approve and explain actions.
- Bots run periodically, repeatedly, without per-invocation approval.
- Bot credentials are typically stored in machine systems and face workload-compromise risk.
- A compromised bot can repeat actions rapidly.

Therefore, never give a human operator's admin credentials to a cron job.

Use dedicated service accounts with clear owners, purpose, scope, rotation policies, and auditing.

When a bot is decommissioned, revoke its credentials and remove unnecessary firewall routes or permissions.

## 19. Limiting Automation Frequency and Impact

Least privilege is not only “which action types are allowed,” but also scope and frequency.

A read-only bot polling \`getFullReport\` every 100 ms can cause CPU/GC pressure. A maintenance bot calling \`rebuildIndexes\` 50 times can cause downtime even with valid permissions.

Design for:

- Reasonable polling intervals.
- Backoff on errors.
- Rate limiting at the workflow or connector layer where supported.
- Concurrency controls for operations.
- Idempotency or job IDs to avoid duplicate retries.
- Timeouts and retry semantics.
- Monitoring of the automation bot itself.

If an operation can have major impact, holding valid permission does not mean the bot should run unboundedly or continuously.

## 20. Real-World Scenarios

### Scenario A — Metrics Bot Requests readwrite Permission

A metrics exporter only needs to read \`QueueDepth\` but is granted \`readwrite\` because an earlier test connection failed.

Risk: the bot can invoke state-changing operations if the connector permits them.

Solution: diagnose the actual error (authentication, networking, JMX read permissions, MBean semantics), use a read-only identity, and never broaden permissions without evidence.

### Scenario B — CI Job Needs to Refresh Configuration

A CI job wants to call \`refreshConfiguration\` in staging. Do not give the CI runner access to shared production admin credentials.

Solution: create a dedicated staging identity; restrict connector, credentials, role, and time window; audit invocations. If JMX policies only support overly broad readwrite, consider a dedicated maintenance API with tighter scoping.

### Scenario C — Bot Shares One Account for Monitoring and Maintenance

A monitoring agent and maintenance scheduler share the \`jmx-admin\` account. When the monitoring container is compromised, the attacker uses those credentials for write operations.

Solution: separate identities and permissions; revoke old credentials; inspect logs and all connector access.

### Scenario D — JMX Endpoint in Kubernetes

A bot in the monitoring namespace needs to poll a JVM. NetworkPolicy should allow only the required traffic; never expose JMX ports broadly across all pods/ingresses. Also audit port-forward and secrets access permissions.

### Scenario E — Readonly Account Leaks Secrets

A reader account cannot invoke operations, but the \`ApplicationConfig\` MBean has an attribute containing a database password.

Solution: fix the management API to remove secrets; restrict accessible MBeans/attributes; rotate exposed secrets if necessary.

## 21. Common Mistakes

| Issue | Cause | Resolution |
|---|---|---|
| Bot granted readwrite just to read metrics | Overly broad permissions | Grant readonly and fix the real connection issue |
| Bot reads secrets via attributes | MBean exports sensitive data | Stop exposing secrets; restrict access |
| HTTP Security enabled, yet JMX remains open | Two independent access paths | Secure the JMX connector separately |
| Bot fails to connect after enabling TLS | Wrong trust/identity/certificate | Fix TLS config; never turn off SSL |
| JMX port open to entire cluster | Loose network policy | Restrict source/destination |
| Bot cannot subscribe to notifications | Unsupported by authorization or denied by policy | Test permissions; adjust architecture |
| No audit trail for JMX operations | Default connector logs insufficiently | Instrument operations/workflows |
| Bot secret appears in logs | Logging credentials | Remove/redact logs and rotate credentials |
| Operation retries cause repeated side effects | Missing idempotency/rate control | Limit concurrency and use job IDs |
| One credential used across environments | Secret reuse | Separate identities and secrets per environment |
| Role named read-only but still able to write | Labels are not enforcement | Test negative cases over JMX |
| Split MBeans only, sharing one readwrite connector | No per-MBean policy | Separate connectors/registries or add enforcement |

## 22. Deployment Checklist

Before granting permissions to an automation account:

1. What business/operational purpose does the bot serve?
2. Does it need read, write, invoke, or notifications?
3. Are there MBeans/attributes/operations that need not be exposed at all?
4. Does the connector support permissions at the required granularity?
5. Is the MBeanServer shared with other sensitive MBeans?
6. Is the bot's identity separated from human operators and other bots?
7. Are credentials provisioned from a secret manager and rotatable?
8. Are network routes restricted by host, namespace, port, and environment?
9. Are TLS/authentication configured and not disabled?
10. Is there a test proving the reader cannot invoke operations?
11. Is there a test proving the operator can only invoke needed actions?
12. Are sensitive invocations audited?
13. Does the bot enforce polling, retry, rate, and concurrency limits?
14. Is there an owner and runbook for revoking permissions when no longer needed?
15. Is there a plan for periodic permission reviews and unused-account audits?

## 23. Hands-On Exercises

### Exercise 1 — Designing Roles

A system has a \`QueueMetrics\` MBean with \`PendingJobs\`, \`QueueAdmin\` with \`pauseProcessing\`, and \`CacheAdmin\` with \`clearAllCache\`. Design permissions for a metrics reader, queue operator, and cache operator. Explain the limitations of a simple readonly/readwrite access file.

### Exercise 2 — Positive/Negative Tests

Create a JMX connector test with two identities, reader and operator. Verify the reader can read attributes but cannot invoke state-changing operations. Use a safe test MBean rather than a production operation.

### Exercise 3 — Threat Model

A monitoring container is compromised. List what an attacker can do if the credentials have readwrite, compared to readonly with a restrictive network policy.

### Exercise 4 — Reviewing the MBean Contract

Identify attributes returning secrets or sensitive data, state-mutating operations, and writable attributes. Propose ways to shrink the surface without hurting observability needs.

### Exercise 5 — Rotation Runbook

A JMX automation account needs credential rotation. Write a checklist covering secret rotation, workload updates, connection verification, revoking the old secret, and confirming no credentials appear in logs.

## 24. Core Takeaways

- **Automation accounts must follow least privilege based on actual need.**
- JMX can permit reads, writes, and operation invocations; it is not a read-only channel by default.
- Distinguish network access, authentication, and authorization.
- JDK management agent readonly/readwrite permissions may be too coarse for per-operation needs; never assume fine-grained RBAC.
- Separate monitoring and maintenance identities, and manage secrets and network routes separately.
- Do not treat Spring HTTP Security as protection for remote JMX connectors.
- Restrict exported data/MBeans; readonly does not prevent secret leaks if an attribute exposes sensitive data.
- Test both allowed and denied behaviors over the real JMX connection path.
- Auditing, rotation, rate limiting, and cleanup are integral parts of permission restriction.

## References

- Oracle Java Management and Monitoring with JMX: https://docs.oracle.com/en/java/javase/21/management/monitoring-and-management-using-jmx-technology.html
- Oracle Java SE Management and Monitoring Guide: https://docs.oracle.com/en/java/javase/21/management/
- Java SE API — JMXConnector: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/remote/JMXConnector.html
- Java SE API — MBeanServerConnection: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerConnection.html
- Spring Framework JMX Reference: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework ManagedResource: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedResource.html
