# DNS, IP Addresses, and Host Information Can Change

In the CRaC lifecycle, an application can be checkpointed and remain inactive for a period of time before being restored. During that time, the network environment continues to change: DNS records may point to new IP addresses, hosts may be replaced, service discovery may select different instances, and resolver or route configurations may be updated. The restored process still carries the saved memory state, which may include resolved addresses, the JVM DNS cache, client configurations, and connection pools created before the checkpoint.

Therefore, a hostname may still be valid while the old IP address may no longer serve the application. If after restore the application continues to use cached addresses or reuse old connections without checking, requests may time out, be rejected, or reach a host that is no longer appropriate. A CRaC application needs to manage hostnames and network resources according to the checkpoint–restore lifecycle: preparing connections before checkpoint, re-resolving hostnames, and recreating necessary connections after restore.

## 1. What network information can change?

A hostname is a logical identifier. DNS and service discovery systems map that identifier to a reachable address or endpoint at a specific point in time. The following information can change while the application is checkpointed:

| Information | Example change | Impact after restore |
| --- | --- | --- |
| DNS A/AAAA records | `api.example.com` changes from `192.0.2.10` to `192.0.2.25`, or an IPv6 address is added | The application may continue using the old IP if the resolution result is still in the cache. |
| CNAME and resolution chain | Alias name points to a different target hostname | The final endpoint may change even though the configured application hostname remains the same. |
| Multiple-address list | Load balancer or DNS returns a different set of IPs | The old set of addresses may no longer be complete or may no longer receive traffic. |
| Service discovery | Service instances are scaled, replaced, or moved across zones | Instance addresses and health states may change. |
| Configured port and endpoint | Service is moved to a new port, hostname, or endpoint | The old configuration may connect to the wrong destination or fail to connect. |
| Host/container resolver and network | `/etc/resolv.conf`, DNS proxy, routes, network namespace, or firewall are updated | The same hostname may be resolved or routed differently after restore. |
| Certificates and security policies | TLS certificates are renewed, or CAs or credentials are rotated | New connections may require new trust material or credentials. |

DNS is not the only source of host information. Applications can also obtain endpoints from environment variables, configuration files, service registries, the Kubernetes API, cloud metadata, or a custom discovery system. These sources also need to be re-checked if their values can change during the checkpoint period.

## 2. Why can a checkpoint retain stale network information?

A checkpoint saves the memory state of the process. If the application resolved a hostname before the checkpoint, the result may be held in the JVM cache or a network library cache. If the application stores an IP address in a field, configuration object, or custom cache, that value will also be restored along with the process.

Example:

```java
public final class RemoteServiceConfig {
    private final String host = "api.example.com";
    private InetAddress resolvedAddress;

    public void initialize() throws UnknownHostException {
        this.resolvedAddress = InetAddress.getByName(host);
    }
}
```

If `resolvedAddress` is created before the checkpoint and retained on the heap, after restore the application may continue using the previously created `InetAddress` object. External DNS changes do not automatically update this field.

Another situation is a connection pool that has already opened connections to an old IP. Connection objects may store sockets, peer addresses, and protocol state. Restoring does not mean this information is synchronized with current DNS. Socket restoration capability also depends on the runtime, CRIU, kernel, and connection type; applications should not assume that all old sockets remain valid.

Distinguish between two types of state:

- **Identity information:** hostname, port, service name, and TLS configuration. This is usually logical configuration data that the application can retain, though it needs to be refreshed if the configuration source has changed.
- **Point-in-time connection information:** resolved IP, sockets, connection pools, routes, and session state. This is state that can expire or become invalid after the checkpoint duration.

A safe design typically keeps the hostname or service identity as the root configuration, then resolves and creates new connections at an appropriate stage after restore.

## 3. DNS caching exists at multiple layers

A DNS query can pass through multiple cache layers. Having a short TTL on a DNS record does not guarantee that every application will immediately see the new address when that TTL expires, because each layer has its own caching policy.

```text
Application
   |
   +--> HTTP client / discovery library cache
   |
   +--> JVM DNS cache (InetAddress)
   |
   +--> Operating system resolver / NSS
   |
   +--> DNS proxy or recursive resolver
   |
   +--> Authoritative DNS
```

Common layers:

1. **Authoritative DNS:** returns records and TTLs configured by the domain owner.
2. **Recursive resolver or DNS proxy:** may cache answers for the duration of the TTL, depending on the resolver's policy.
3. **Operating system resolver:** may use DNS, `/etc/hosts`, NSS, or other mechanisms depending on the platform.
4. **JVM:** `InetAddress` has a caching policy for both successful and failed resolution results.
5. **HTTP client or service discovery library:** may have its own DNS cache or endpoint pool, independent of the JVM cache.
6. **Application-built cache:** may hold `InetAddress`, string IPs, or server lists in memory.

Therefore, changing the TTL on the DNS server does not necessarily cause the client cache to change immediately. It is necessary to identify which layer is holding the old result and the caching policy of that layer.

## 4. DNS caching policy in Java

Java provides security properties to control the caching of name resolution results via `InetAddress`:

| Security property | Meaning |
| --- | --- |
| `networkaddress.cache.ttl` | Cache duration for successful resolution results, in seconds. A value of `-1` means cache forever; `0` disables caching; a positive number sets the cache duration. |
| `networkaddress.cache.negative.ttl` | Cache duration for failed resolution results, in seconds. A value of `0` disables negative caching; a positive number sets the error cache duration. |

These are **security properties**, not regular JVM system properties. Configuration is typically placed in the JDK's `java.security` file, for example `$JAVA_HOME/conf/security/java.security`:

```properties
networkaddress.cache.ttl=30
networkaddress.cache.negative.ttl=5
```

The values above are only examples. Choose TTLs based on failover requirements, DNS load, and infrastructure policy. A TTL that is too long can cause clients to keep using stale addresses; a TTL of 0 can increase DNS queries and latency. A negative cache that is too long can cause a newly created or recovered hostname to still be treated as unresolvable for a period of time.

You can configure security properties early during startup using `java.security.Security.setProperty(...)`, before the application performs the lookups you want to control:

```java
import java.security.Security;

public final class DnsCachePolicy {
    private DnsCachePolicy() {}

    public static void configure() {
        Security.setProperty("networkaddress.cache.ttl", "30");
        Security.setProperty("networkaddress.cache.negative.ttl", "5");
    }
}
```

Changing the policy after lookups have already occurred is not a reliable way to clear all DNS caches across all layers. Set the policy before the first lookups and verify behavior on the exact JDK being deployed. HTTP clients or discovery libraries may use their own resolvers/caches and therefore need to be configured separately according to their documentation.

Do not assume the JVM always caches strictly according to the authoritative DNS TTL. Security properties and per-JDK defaults may determine the actual cache duration. Inspect the runtime configuration in use rather than inferring solely from the DNS record's TTL.

## 5. Why is re-resolution needed after restore?

Suppose an application is checkpointed when `payments.internal` points to `10.10.1.15`. During the checkpoint period, the payment cluster is redeployed and DNS changes to `10.10.2.20`.

```text
Before checkpoint                During checkpoint
-----------------                ---------------------------
payments.internal                payments.internal
        |                                |
        v                                v
    10.10.1.15                       10.10.2.20
        |                                |
        v                                v
  Old connection kept              New instance serving
  in memory                        traffic
```

After restore, if the application reuses `10.10.1.15`, the connection may fail because the old server has been removed, the address has been reassigned to another service, or firewall rules have changed. If the application re-resolves `payments.internal` through the current resolver and creates a new connection, it has a chance to receive the new endpoint.

Re-resolution also helps refresh multi-address lists, for example when DNS returns a group of IPs for load distribution. However, successful resolution only confirms that the resolver returns an address; it does not prove that the server is healthy or that the port is reachable. The application still needs a connect/health validation step.

## 6. Managing connection pools and sockets across the CRaC lifecycle

Connection pools typically reuse already-opened connections. DNS is usually only queried when a client creates a new connection; an open socket does not automatically change its peer address just because a DNS record changes.

Therefore, if a checkpoint lasts a long time or the network environment can change, the application should treat open network connections as resources that require explicit management:

- Before checkpoint, stop accepting new work and wait for in-flight requests to complete within a bounded timeout.
- Stop or pause creating new connections while preparing for the checkpoint.
- Close or transition connection pools to a re-initializable state according to the API of the pool and CRaC library in use.
- Do not keep an old socket in a field and assume it will automatically connect to a new IP after restore.
- After restore, re-resolve hostnames and create new connection pools/clients as needed.
- Only resume accepting traffic after critical dependencies are connected and health checks pass.

Not all connection pools share the same lifecycle API. Some pools can be closed but cannot be restarted on the same object; some HTTP clients may not support full closure in the version being used. In such cases, keep a factory or provider in a long-lived owner and replace the client/pool with a new instance after restore.

## 7. Example Resource refreshing endpoints after restore

The example below illustrates a `Resource` that retains the hostname as its root configuration. Before checkpoint, it stops using the current client and closes connections according to the abstraction's API. After restore, it resolves the hostname to observe the current endpoints and then recreates the client.

```java
import org.crac.Context;
import org.crac.Resource;

import java.net.InetAddress;
import java.util.Arrays;

public final class NetworkResource implements Resource {
    private final String host;
    private final int port;
    private final NetworkClientFactory clientFactory;
    private NetworkClient client;

    public NetworkResource(
            String host,
            int port,
            NetworkClientFactory clientFactory) {
        this.host = host;
        this.port = port;
        this.clientFactory = clientFactory;
        this.client = clientFactory.create(host, port);
    }

    @Override
    public void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {
        stopAcceptingRequests();
        if (!awaitRequestsToDrain()) {
            throw new IllegalStateException("Requests did not drain before checkpoint");
        }

        if (client != null) {
            client.closeConnections();
            client = null;
        }
    }

    @Override
    public void afterRestore(
            Context<? extends Resource> context) throws Exception {
        InetAddress[] addresses = InetAddress.getAllByName(host);
        System.out.println("Resolved " + host + ": " + Arrays.toString(addresses));

        // Factory uses the hostname to create a new client and apply the
        // DNS, TLS, timeout, and load balancing policies of the library in use.
        client = clientFactory.create(host, port);
        client.validateConnectivity();
        resumeAcceptingRequests();
    }

    private void stopAcceptingRequests() { /* application-specific */ }
    private boolean awaitRequestsToDrain() { return true; /* bounded wait */ }
    private void resumeAcceptingRequests() { /* application-specific */ }
}
```

`NetworkClient` and `NetworkClientFactory` are application-defined abstractions; the methods in the example need to be mapped to the actual APIs of the HTTP client, database pool, or network library in use. Calling `InetAddress.getAllByName(host)` may still return results from the JVM cache if the entry is still valid. To obtain fresh results, you must design an appropriate caching policy and handle the client library's own cache.

The example also keeps `host` instead of keeping only an `InetAddress` or IP. When the factory creates a new client using the hostname, the library can perform resolution according to its own resolver and policy. Do not pass an IP saved before the checkpoint into the factory if the goal is to pick up a new endpoint.

The `stopAcceptingRequests` and `awaitRequestsToDrain` methods illustrate blocking new traffic before closing the client. Draining needs a bounded timeout. When the application is quiesced and has not yet opened traffic after restore, the callback can swap the client without holding an application lock during DNS or network I/O. If the design requires a lock to protect state, hold the lock only for the brief client swap and perform resolution/connection outside the critical section.

## 8. Hostname, IP, and TLS

When multiple IP addresses exist, prefer using the hostname/service name in application configuration and let the client resolve the name according to an appropriate policy. Connecting directly by IP can bypass DNS failover or service discovery mechanisms.

The hostname is also important for TLS:

- TLS SNI usually requires the hostname for the server to select the right certificate.
- Certificate hostname verification checks the host name the client intends to connect to.
- If the application replaces the hostname with an IP in the URL or TLS configuration, certificate verification may fail or require specific IP SAN configuration.
- Do not disable hostname verification just to bypass connection errors after restore.

If a static IP must be used, there needs to be a process to update configurations, verify routes, and update corresponding certificates. An IP should not be treated as a long-term identifier if the infrastructure can change addresses.

## 9. Updating server information from configuration and service discovery

Not every application uses DNS directly. Some applications read endpoint lists from configuration, registries, or discovery APIs. When checkpointed, these lists may become stale after restore.

The design should separate:

- **Configuration source:** hostname, service ID, port, TLS policy, and authentication information. These are logical inputs to create the client.
- **Endpoint snapshot:** resolved IPs or instance lists at a point in time. This is temporary data that needs to be refreshed according to policy.
- **Connection state:** sockets, pools, sessions, and health status. These are resources that need to be checked or recreated after restore.

In `afterRestore`, the application can re-read dynamic configuration or refresh the service registry before creating the client. If configuration comes from environment variables loaded only at process start, restoring the same process may retain old values; an explicit refresh mechanism is needed if the environment can change values during the checkpoint period.

When updating endpoints, handle cases where DNS returns multiple addresses, some addresses are unreachable, or IPv4/IPv6 preference order changes. Clients should have bounded retries, backoff, and a total reconnection time limit so a faulty address does not cause the callback to wait indefinitely.

## 10. Common errors after restore

| Symptom | Possible cause | Investigation direction |
| --- | --- | --- |
| Connection to old IP times out | `InetAddress`, custom cache, or application config still holds the old IP | Check the hostname, current DNS results, JVM cache, and client cache. |
| New hostname resolution fails even though DNS was updated | Negative DNS cache or resolver/proxy still holds the old result | Check `networkaddress.cache.negative.ttl`, the resolver, and when the record was updated. |
| Some instances connect while others do not | DNS returns multiple addresses or some backends are unhealthy | Check each IP, port, health, routing, and load balancing. |
| DNS resolves correctly but requests still fail | Connection pool reuses an old socket or TLS/session is no longer valid | Create a new client/pool; check peer address, handshake, and certificate. |
| Restore on a new container cannot resolve names | Different DNS config, search domain, resolver, or network namespace | Check `/etc/resolv.conf`, `/etc/hosts`, NSS, DNS proxy, and container network configuration. |
| Reconnection hangs or callback stalls | Missing connect/read timeout or infinite retries | Set an overall deadline, per-layer timeouts, and bounded retries/backoff. |
| TLS connection fails after endpoint changes | Mismatched certificate, SNI, trust store, or hostname verification | Check hostname, SAN, CA, certificate expiration, and TLS configuration. |

## 11. Observing and testing DNS changes

For diagnostics, log the hostname/service ID, the list of IPs received, resolution timestamp, reconnection duration, and health check results. Logs should not contain credentials, tokens, or sensitive data.

OS tools can help inspect resolver results outside the JVM:

```bash
getent hosts api.example.com
```

In environments with `dig`, you can inspect records and TTLs from the configured resolver:

```bash
dig api.example.com A
dig api.example.com AAAA
```

Results from `dig` or `getent` do not necessarily match the application's immediate results if the JVM or HTTP client maintains its own cache. Therefore, inspect from the same container/namespace and observe the actual client the application uses.

An integration test scenario can be carried out as follows:

1. Configure a test hostname pointing to server A.
2. Start the application, confirm the client connects to A, and create a checkpoint.
3. Change DNS or service discovery so the hostname points to server B.
4. Wait according to the expected TTL and caching policy, or use a controllable test resolver to determine when the update takes effect.
5. Restore the application in a compatible environment.
6. Confirm the callback closes old connections, resolves the new endpoint, and creates a new client.
7. Verify that post-restore requests actually reach B and the application achieves readiness.
8. Also test cases where DNS temporarily fails to resolve, returns multiple IPs, or a backend is unreachable to confirm bounded timeouts and retries.

Do not just test `InetAddress.getAllByName()` and conclude that the client is already using the new endpoint. You must verify the client's actual connections, because connection pools may retain old sockets and libraries may have their own resolvers.

## 12. Checklist for managing DNS and endpoints in CRaC

- [ ] Store the hostname or service identity as the root configuration instead of only storing resolved IPs.
- [ ] Identify all DNS cache layers: JVM, OS resolver, HTTP client, service discovery, and application caches.
- [ ] Configure positive/negative DNS caches appropriately for failover requirements.
- [ ] Do not confuse `networkaddress.cache.*` security properties with regular JVM system properties.
- [ ] Before checkpoint, stop new work and handle connection pools/sockets according to the library's lifecycle.
- [ ] After restore, refresh configuration or service discovery if endpoints can change.
- [ ] Re-resolve hostnames according to an appropriate caching policy and create new connections as needed.
- [ ] Set connect/read timeouts, an overall deadline, and bounded retries/backoff.
- [ ] Verify TLS SNI, hostname verification, trust store, and certificates after endpoints change.
- [ ] Only resume accepting traffic after critical dependencies are connected and health checks pass.
- [ ] Test DNS IP changes between checkpoint and restore in the actual CRaC deployment environment.

## 13. Conclusion

A checkpoint preserves the process memory state at a point in time, while external DNS, IPs, server instances, and network configurations can still change. After restore, the hostname may still be valid, but saved addresses or old sockets may no longer be appropriate. Distinguish JVM DNS caching from OS, resolver, HTTP client, and service discovery caches; each layer has its own policy.

Keep the hostname/service identity as the identifier source, manage connection pools through `beforeCheckpoint`, refresh endpoint information and create new connections in `afterRestore`, and verify readiness before accepting traffic. Configuring TTLs, timeouts, and bounded retries helps the application adapt to DNS changes without turning the restore process into an indefinitely blocking callback.
