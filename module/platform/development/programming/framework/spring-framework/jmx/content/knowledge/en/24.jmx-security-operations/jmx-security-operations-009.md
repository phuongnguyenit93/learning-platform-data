# Spring Framework JMX: Monitoring Connector Errors and Failed Logins

## 1. Objectives

In systems using Spring Framework JMX, connection errors and login failures at the JMX connector prevent clients from reading MBeans or invoking operations. This lesson distinguishes network failures, TLS failures, authentication failures, authorization denials, MBean registration issues, and business operation failures; it also covers logging, metrics, alerting, reconnecting, and protecting sensitive information.

## 2. Request Path of a JMX Call

```text
Spring JMX client -> JMXConnector -> network/RMI/TLS
                 -> JMX connector server -> authentication
                 -> authorization -> MBeanServer -> MBean
```

A failure at an earlier layer can prevent later layers from ever running. For example, when DNS fails, password verification is never reached; when connection succeeds yet an operation is blocked, that is an authorization denial rather than a login failure.

| Layer | Symptom | Check |
|---|---|---|
| DNS/TCP | `UnknownHostException`, connection refused, or timeout | DNS, firewall, port |
| JMX RMI | Registry reachable yet RMI stub fails to connect | Advertised hostname, RMI server port |
| TLS | `SSLHandshakeException` or untrusted certificate | Truststore, certificate, hostname |
| Authentication | Credentials rejected | Server authenticator, secret rotation |
| Authorization | Login succeeds yet action is denied | Policy, role, and operation |
| MBean registry | `InstanceNotFoundException` | ObjectName, target server |
| Contract | `AttributeNotFoundException` or `ReflectionException` | `MBeanInfo`, signature |
| Business | `MBeanException`, `RuntimeMBeanException` | Target exception, business state |

## 3. Monitoring on the JMX Client Side

With `JMXConnectorFactory`, record connect attempts, connect successes/failures, and connection latency. Example application-defined metrics:

- `jmx_connect_attempts_total{target}`
- `jmx_connect_failures_total{target,category}`
- `jmx_connect_duration_seconds{target}`
- `jmx_connection_up{target}`
- `jmx_connection_last_success_timestamp_seconds{target}`

Do not put raw IPs, URLs containing credentials, or arbitrary usernames into metric labels due to leakage risk and high cardinality. `target` should be a logical ID like `orders-prod` rather than a dynamic per-pod identifier.

```java
long start = System.nanoTime();
try (JMXConnector connector =
        JMXConnectorFactory.connect(serviceUrl, environment)) {
    metrics.recordConnectSuccess(System.nanoTime() - start);
    MBeanServerConnection connection = connector.getMBeanServerConnection();
    connection.getDefaultDomain(); // lightweight read probe
} catch (SecurityException ex) {
    metrics.recordConnectFailure("security");
    throw ex;
} catch (IOException ex) {
    metrics.recordConnectFailure("transport");
    throw ex;
}
```

In this example, `metrics` is an illustrative application-defined interface. Do not assume every `SecurityException` is a wrong password; determine the stage where the error occurred, the provider, and the cause chain.

## 4. Tracking JMXConnectionNotification

`JMXConnector` supports lifecycle notifications, including `JMXConnectionNotification.OPENED`, `CLOSED`, `FAILED`, and `NOTIFS_LOST`. Register a `NotificationListener` to update health and record errors:

```java
NotificationListener listener = (notification, handback) -> {
    if (!(notification instanceof JMXConnectionNotification event)) return;
    switch (event.getType()) {
        case JMXConnectionNotification.OPENED -> monitoring.opened();
        case JMXConnectionNotification.CLOSED -> monitoring.closed();
        case JMXConnectionNotification.FAILED -> monitoring.failed();
        case JMXConnectionNotification.NOTIFS_LOST -> monitoring.lostEvents();
        default -> { }
    }
};
connector.addConnectionNotificationListener(listener, null, null);
```

This Java example uses switch arrow syntax; `monitoring` is a custom dependency. If the client calls `JMXConnectorFactory.connect` before registering the listener, the initial `OPENED` event may already have fired. Therefore, connect success must be recorded separately; the listener is not the sole source for connect success.

`NOTIFS_LOST` indicates notifications may have been lost: re-read attributes or MBean state to resynchronize, and do not assume lost events can be replayed automatically.

## 5. Spring MBeanServerConnectionFactoryBean

In Spring, `MBeanServerConnectionFactoryBean` creates an `MBeanServerConnection` for injection:

```java
@Configuration
public class RemoteJmxConfiguration {
    @Bean
    public MBeanServerConnectionFactoryBean ordersConnection(
            @Value("${app.jmx.orders.url}") String url) throws Exception {
        var factory = new MBeanServerConnectionFactoryBean();
        factory.setServiceUrl(url);
        return factory;
    }
}
```

The `FactoryBean` reduces client boilerplate, yet does not automatically provide built-in metrics, exactly-once operations, or reliable reconnection across all configurations. Monitor startup exceptions, post-connection calls, lifecycle, and endpoint health. If detailed connector transport observability is required, consider an application-managed connection manager paired with `JMXConnectorFactory`.

## 6. Authentication Failure and Authorization Denial

Authentication verifies the identity accepted on connection. Authorization decides whether the signed-in identity may invoke operations or read/write attributes.

Example of two distinct audit events:

```json
{"event":"jmx.authentication","target":"orders-prod","outcome":"denied","category":"invalid_credentials"}
{"event":"jmx.authorization","target":"orders-prod","outcome":"denied","action":"resetQueue"}
```

The JSON events only illustrate an application-designed schema. Do not use a single login failure counter for both cases. Auth failures may stem from stale secrets after rotation, clients pointing to the wrong realm, or unauthorized access. Authorization denials may come from a read-only monitoring account attempting to invoke a write operation.

On the server side, a custom `JMXAuthenticator` or connector integration can count authentication successes/failures. Never log raw credentials, passwords, tokens, full environment maps, or certificate private keys. You may log target ID, timestamp, error category, and authenticated principal if allowed by policy.

## 7. Operational Alerting

Distinguish several alert types:

1. Connector unavailable: health probes fail repeatedly or time since last successful connection exceeds threshold.
2. Unusual spike in authentication failures: may indicate a failed credential rotation or a source repeatedly attempting connections.
3. Authorization denials on sensitive operations: investigate permissions and request source.
4. TLS failures: check certificate expiry, truststore, and hostname.
5. `JMXConnectionNotification.NOTIFS_LOST`: resynchronize state via read-only queries.

Rules should combine error rate, minimum error count, baseline, and target criticality. Looking only at failure ratio over very small connection counts easily causes false alerts. If the connector is completely unreachable, authentication failures may be zero even though the service is unavailable.

## 8. Safe Health Checks

Choose a lightweight read action, such as checking a stable marker MBean:

```java
boolean healthy(MBeanServerConnection connection) {
    try {
        ObjectName marker = new ObjectName("java.lang:type=Memory");
        return connection.isRegistered(marker);
    } catch (Exception ex) {
        return false;
    }
}
```

The platform Memory MBean might not be present on a custom server, so that environment should use its own marker. Do not use `setAttribute` or `invoke` (for side-effecting operations) as health probes. Use appropriate timeouts, concurrency limits, and polling frequency.

## 9. Reconnecting with Backoff

When the target JVM restarts or the network drops:

- Mark the connection degraded/unavailable.
- Establish a new connection using exponential backoff and jitter, avoiding tight loops.
- Close the old connector when replacing it and verify the target server identity.
- Re-register notification listeners if needed.
- Re-read MBean state after any period of lost events.
- Do not blindly retry side-effecting operations if the prior request timed out.

If a client invokes `clearQueue` and loses the response, the server may already have finished executing it. Retrying immediately can cause unintended duplicate execution. Unknown states must be resolved by checking post-state or using an idempotent contract with a request ID.

## 10. RMI, TLS, and Containers

With JMX RMI in Docker/Kubernetes, the registry port may be reachable while the remote stub points to an unreachable hostname or server port. Check `java.rmi.server.hostname`, RMI server port settings, firewalls/NAT, DNS, TLS, and network policies. Do not open all ports or disable authentication as a quick fix. Instead, identify the failing stage and fix the corresponding configuration.

## 11. Test Scenarios

| Scenario | Expected Outcome |
|---|---|
| Host fails to resolve | Connection failure classified under DNS/transport |
| Port closed | Failure and reconnect backoff |
| Wrong password | Auth denial logged at server boundary |
| Valid password but insufficient permissions | Auth success, separate authorization denial |
| Untrusted certificate | TLS handshake failure |
| JVM restart | Health down, reconnect and reconcile |
| Wrong operation signature | Contract/invocation error, not counted as login failure |
| Wrong ObjectName | `InstanceNotFoundException`, not counted as auth failure |

Run invalid-credential tests in an authorized environment with a bounded number of attempts to avoid lockouts or impacting production.

## 12. Practice Exercises

**Exercise 1:** Classify `UnknownHostException`, `SSLHandshakeException`, `SecurityException` during authenticate, and `InstanceNotFoundException` into distinct error groups.

**Exercise 2:** Design the metrics `connect_attempts_total`, `connect_failures_total{category,target}`, and `connection_up{target}`; explain why passwords or arbitrary usernames must not be used as labels.

**Exercise 3:** Create a `NotificationListener` handling `FAILED` and `NOTIFS_LOST`, updating the health metric and triggering read-only reconciliation after reconnect.

**Exercise 4:** An account can read attributes yet cannot invoke `shutdown()`: this is typically an authorization denial, not necessarily a login failure.

**Exercise 5:** When `resetCounters()` times out, explain why you must not blindly retry without knowing the server-side outcome.

## 13. Summary

Monitoring connector errors and failed logins in Spring JMX requires observing the client, connector server, and MBean invocations. Collect connect attempts, latency, failure categories, health state, and `JMXConnectionNotification` events; distinguish authentication from authorization, network, TLS, and JMX contract errors. Protect secrets in logs, use baseline-aware alerting, reconnect with backoff, and avoid retrying non-idempotent operations when outcomes are unknown.
