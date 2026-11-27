# Distinguishing Temporary Disconnection from Session Expiration

## Objectives

After this lesson, you will be able to:

- Distinguish a temporary network disconnection from an actual ZooKeeper session expiration.
- Explain the roles of heartbeats, session timeout, and ephemeral znodes in service registration.
- Read and handle Apache Curator's CONNECTED, SUSPENDED, RECONNECTED, and LOST states.
- Understand how each state affects service registration, watches, caches, and service discovery.
- Design a safe recovery flow when the application reconnects or must establish a new session.

## 1. Why distinguish these two scenarios?

In Spring Cloud Service Discovery, an application can register instance information such as service name, instance ID, host, and port into ZooKeeper. Spring Cloud Zookeeper uses Apache Curator to perform service registration and discovery. Therefore, ZooKeeper connection status directly affects whether an instance remains visible in the registry.

An application that loses connectivity to ZooKeeper has not necessarily lost its session. If the network recovers before the session timeout, the client can reconnect with its previous session ID. The ephemeral znodes belonging to that session remain intact.

Conversely, if the ZooKeeper ensemble receives no heartbeat within the session timeout period, the server expires the session. The ephemeral znodes created by that session are deleted. When the client reconnects, it must establish a new session and re-register the required data.

Both scenarios can occur while the application process is still running. For instance, a network partition, firewall rule, long GC pause, or suspended VM can prevent the client from sending heartbeats on time. Hence, you cannot rely solely on the process being alive to conclude that its service registration is still valid.

## 2. ZooKeeper sessions and heartbeats

When an application connects to ZooKeeper, the client library establishes a session. ZooKeeper assigns the session a session ID and corresponding session credentials. The client keeps the session alive with requests and periodic heartbeats.

The session timeout is the window ZooKeeper uses to determine a session is inactive if the server receives no heartbeats. The timeout is negotiated between client and server: the client sends a requested value, and the server returns the accepted value. According to current ZooKeeper documentation, the negotiated timeout has a minimum of 2 times tickTime and a maximum of 20 times the server's tickTime.

When the client temporarily loses connectivity, the ZooKeeper library attempts to reconnect to servers in the connection string. If it reconnects within the session timeout, the client can resume using its old session. Once the session has expired on the server side, the client cannot revive that session merely by reopening a TCP connection.

Key concepts to distinguish:

| Concept | Meaning |
| --- | --- |
| TCP connection | Network link between the client and a specific ZooKeeper server. It can close or drop while the session remains valid. |
| ZooKeeper session | Logical state managed by the ensemble, with a session ID and timeout. It can survive the client failing over to another server. |
| Heartbeat | Signal letting the server know the client is still maintaining the session. |
| Session timeout | Time limit the server waits for heartbeats before expiring the session. |
| Ephemeral znode | Znode bound to the session that created it; ZooKeeper deletes the node when the session ends or expires. |
| Watch | Znode change notification mechanism; not an independent connection and must be restored/resynchronized along with the session lifecycle. |

### Session timeout vs. connection timeout

Spring Cloud Zookeeper has two separate settings:

~~~~yaml
spring:
  cloud:
    zookeeper:
      connect-string: zk-1.internal:2181,zk-2.internal:2181,zk-3.internal:2181
      connection-timeout: 10000
      session-timeout: 30000
~~~~

- `spring.cloud.zookeeper.connection-timeout` is the wait time for establishing a connection, in milliseconds.
- `spring.cloud.zookeeper.session-timeout` is the configured/negotiated session timeout, in milliseconds.

The values in the example are illustrative. The server may negotiate a different session timeout based on tickTime and ensemble limits. Verify the actual value received by the client rather than assuming the requested value is always accepted verbatim.

Retry properties such as `spring.cloud.zookeeper.max-retries`, `spring.cloud.zookeeper.base-sleep-time-ms`, and `spring.cloud.zookeeper.max-sleep-ms` control retry counts and backoff intervals for retryable operations. They do not replace the session timeout and cannot resurrect an old session after the server has expired it.

## 3. What happens when connectivity is interrupted?

Suppose inventory-service has registered an instance in ZooKeeper using an ephemeral znode.

1. The application connects successfully and establishes a session.
2. Curator registers the instance; ZooKeeper stores a znode bound to the session.
3. The network between the application and ZooKeeper is interrupted. The client cannot send heartbeats.
4. Curator reports the disconnection state as SUSPENDED.
5. ZooKeeper continues tracking the session on the server side. Within the timeout window, the ephemeral znode is not necessarily deleted yet.
6. If the client reconnects in time, the old session resumes and Curator emits RECONNECTED.
7. If the server has already expired the session, the ephemeral znode is deleted. When connectivity is restored, the client detects the session was lost and must establish a new session and re-register the instance.

Lifecycle diagram:

~~~~mermaid
sequenceDiagram
    participant App as Spring Boot service
    participant Curator
    participant ZK as ZooKeeper ensemble
    participant Consumer as Service consumer

    App->>Curator: Initialize client
    Curator->>ZK: Create session and heartbeat
    Curator->>ZK: Register ephemeral znode
    ZK-->>Consumer: Instance appears in registry

    Note over App,ZK: Network partition
    ZK--xCurator: Connection lost
    Curator-->>App: SUSPENDED

    alt Reconnect before session expires
        Curator->>ZK: Reconnect with old session ID
        ZK-->>Curator: Session still valid
        Curator-->>App: RECONNECTED
        Note over ZK: Ephemeral znode still belongs to old session
    else Session expired
        ZK->>ZK: Delete ephemeral znode
        ZK-->>Consumer: Watch notifies instance removed
        Curator->>ZK: Reconnect and detect session expired
        Curator-->>App: LOST
        App->>Curator: Create new session and re-register
        Curator->>ZK: Create new ephemeral znode
        ZK-->>Consumer: Instance re-advertised
    end
~~~~

An important point is that the moment the server deletes the ephemeral znode and the moment the client receives the expiration notice can differ. While disconnected, the client cannot immediately receive server notifications. Already-connected consumers may receive the znode deletion event as soon as the session expires, whereas the expired client itself learns about it only after reconnecting.

## 4. How do ephemeral znodes affect service discovery?

Curator Service Discovery stores ServiceInstance records in a znode tree organized by base path and service name. An instance holds information such as service name, instance ID, address, port, and metadata payload. Spring Cloud Zookeeper uses the Curator Service Discovery extension for registration and discovery.

Ephemeral znodes fit registration records of live instances because the node lifecycle is tied to its creating session:

- Session still valid: the znode persists, even if the TCP connection temporarily drops.
- Session expired: ZooKeeper deletes ephemeral znodes belonging to the session.
- Normal application shutdown: Spring Cloud ServiceRegistry can deregister the instance during shutdown; if deregistration fails due to a network error, session expiration still serves as the ultimate cleanup mechanism for ephemeral nodes.

When a session is lost, consumers may see the instance vanish from the service list. When the provider re-registers under a new session, the instance may reappear. The duration of disappearance and reappearance depends on session timeout, state detection, retries, and re-registration timing.

Do not treat an instance remaining in the registry during SUSPENDED as proof that the instance is serving requests healthily. The registry only reflects registration state as observed by consumers. A network partition can cut off the provider from ZooKeeper while consumers still view stale information.

## 5. Curator connection states

Curator provides ConnectionStateListener for applications to track connection state. Key states include:

| State | Meaning | Operational interpretation |
| --- | --- | --- |
| CONNECTED | Initial connection to ZooKeeper succeeded. | The client has a session and begins normal operations. |
| SUSPENDED | Curator detected a connection interruption. | Cannot yet conclude the session expired; however, do not trust locks, leadership, or coordination rights as safe. |
| RECONNECTED | Connection re-established after SUSPENDED or LOST. | Re-verify discovery data, watches, caches, and session-dependent resources. |
| LOST | Curator believes the session has expired or the internal session was closed. | Treat the old session as invalid; establish a new session and recover registration/coordination state. |
| READ_ONLY | Client switched to read-only mode if configured to allow it. | Do not perform operations requiring writes or registration while in read-only mode. |

### SUSPENDED does not mean LOST

SUSPENDED is a connection-loss signal. It occurs before it can be determined whether the session has expired. If the network recovers while the session remains valid, Curator can transition to RECONNECTED without creating a new session.

However, Curator recommends treating SUSPENDED as a complete loss of connectivity for tasks requiring distributed correctness. For example, a process holding a distributed lock cannot be sure it still owns the lock while disconnected. The process should halt actions depending on the lock until connectivity is re-verified.

### LOST means different things across Curator versions

Check the Curator version managed by your Spring Cloud release train:

- Prior to Curator 3.0.0, LOST could simply mean the retry policy exhausted its attempts. It did not necessarily prove the ZooKeeper server had expired the session.
- Starting in Curator 3.x, Curator simulates session expiration client-side with a timer started upon entering SUSPENDED. By default, the timer uses the full negotiated session timeout; if the timer expires before connectivity is restored, Curator transitions to LOST.
- Curator may emit RECONNECTED after LOST in certain recovery flows. Even after connectivity resumes, the application must treat locks, leader state, and resources tied to the old session as untrustworthy.

Curator's LOST is a library session-lifecycle signal. It is not an exact clock matching the moment the ZooKeeper server deletes ephemeral nodes. Curator Tech Note 14 explains that the server may close a connection once roughly 2/3 of the session timeout has elapsed since the last heartbeat, whereas Curator only starts its simulated timer upon receiving SUSPENDED. Additionally, a connection can drop due to a server crash or TCP error. The client does not always know the exact cause when a connection closes, so the client-side timer cannot precisely replicate the server's session clock.

Curator's default error policy treats both SUSPENDED and LOST as error states for recipes in order to prioritize safety. Curator provides SessionConnectionStateErrorPolicy if an application wants to treat only LOST as a true session error. Only change this policy once you understand the risk of continuing to rely on stale state during SUSPENDED.

## 6. Watches and caches during reconnection

Standard ZooKeeper watches are one-shot: after a change triggers a watch, the client must re-register if it wants subsequent events. The Java client automatically re-registers existing watches on reconnect by default. However, during disconnection, the client receives no watch events.

One edge case can miss changes: a watch is set to monitor the existence of a znode not yet created; while the client is disconnected, the znode is created and then deleted before the client reconnects. The client may miss that intermediate event.

Curator ServiceCache maintains an in-memory instance list updated via watches. The cached list is only the latest state known to the client, not a guarantee of instant freshness. After reconnecting, wait for the cache to resynchronize and process emitted change events.

Operational principles:

- On SUSPENDED, mark discovery/cache data as potentially stale.
- On RECONNECTED, wait for watch/cache synchronization and re-read required state.
- Do not rely on a single event to infer every change that happened while disconnected.
- On LOST, establish a new session and verify registrations, watches, caches, and initialized recipes.
- If the application uses raw watches directly, re-register watches per the API and ZooKeeper version in use.

## 7. Spring Cloud Zookeeper configuration

Spring Cloud Zookeeper enables discovery via the dependency:

~~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-zookeeper-discovery</artifactId>
</dependency>
~~~~

Applications need to connect to a ZooKeeper ensemble and can register instances with configuration:

~~~~yaml
spring:
  application:
    name: inventory-service
  cloud:
    zookeeper:
      connect-string: zk-1.internal:2181,zk-2.internal:2181,zk-3.internal:2181
      connection-timeout: 10000
      session-timeout: 30000
      discovery:
        enabled: true
        register: true
        root: /services
~~~~

In the configuration above:

- connect-string lists servers the client can try connecting to.
- connection-timeout limits connection establishment wait time.
- session-timeout is the configured/negotiated session duration, in milliseconds.
- discovery.register enables service registration; the default in current Spring Cloud Zookeeper documentation is true.
- discovery.root is the root directory storing registrations; the default is /services.

The session-timeout value in the example is illustrative. The ZooKeeper server may adjust it based on tickTime. Do not lower session timeout too aggressively just to make the registry delete instances faster: GC pauses, high load, or network jitter can cause unintended session expirations.

Spring Cloud Zookeeper uses Curator for service registration and discovery. Depending on the Spring Cloud and Curator versions, how connection state, caches, and re-registration are managed may differ. Inspect the dependency tree to confirm the actual Curator version before applying specific listeners or policies.

## 8. Monitoring state with ConnectionStateListener

You can attach a listener to CuratorFramework to log and trigger actions appropriate for each state:

~~~~java
import org.apache.curator.framework.CuratorFramework;
import org.apache.curator.framework.state.ConnectionState;
import org.apache.curator.framework.state.ConnectionStateListener;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

@Component
public class ZooKeeperConnectionMonitor {

    private static final Logger log =
            LoggerFactory.getLogger(ZooKeeperConnectionMonitor.class);

    private final CuratorFramework curator;

    private final ConnectionStateListener listener = (client, state) -> {
        if (state == ConnectionState.CONNECTED) {
            log.info("Connected to ZooKeeper");
        } else if (state == ConnectionState.SUSPENDED) {
            log.warn("ZooKeeper connection suspended; enter safe mode");
            // Pause tasks requiring locks or coordination guarantees.
        } else if (state == ConnectionState.RECONNECTED) {
            log.info("ZooKeeper connection re-established; verify state");
            // Re-sync cache and verify registration.
        } else if (state == ConnectionState.LOST) {
            log.error("ZooKeeper session lost; rebuild session-bound state");
            // Recreate session-bound resources per application lifecycle.
        }
    };

    public ZooKeeperConnectionMonitor(CuratorFramework curator) {
        this.curator = curator;
    }

    public void start() {
        curator.getConnectionStateListenable().addListener(listener);
    }

    public void stop() {
        curator.getConnectionStateListenable().removeListener(listener);
    }
}
~~~~

This example only shows how to receive events. In real applications, bind the listener to bean lifecycle, ensure it is registered only once, and remove it when the bean is destroyed. Safe-mode actions, cache sync, or re-registration should be implemented via the service registry and Curator recipes used by the application; avoid creating a second session in parallel with the Spring-managed client.

Do not perform long-running work, synchronous network calls, or lengthy retry waits directly inside the listener callback. Offload recovery tasks to an appropriate executor and ensure event handling is idempotent.

## 9. Safe recovery workflow

### Case A: SUSPENDED then RECONNECTED

When the client loses connectivity but recovers before the session expires:

1. Mark discovery state as degraded or uncertain.
2. Pause operations requiring locks, leadership, or session ownership.
3. Wait for Curator to emit RECONNECTED.
4. Resynchronize ServiceCache or re-read necessary znodes.
5. Verify the instance registration still exists and metadata remains accurate.
6. Resume ZooKeeper-dependent tasks only after required state is verified.

The old session may still be valid, so ephemeral znodes are not deleted. Do not create a new session merely upon receiving SUSPENDED.

### Case B: LOST then RECONNECTED

When Curator reports LOST:

1. Mark all state tied to the old session as invalid.
2. Stop using old locks, leader tokens, ephemeral nodes, or prior ownership assumptions.
3. Let the Curator/ZooKeeper client manage establishing a new session per client lifecycle.
4. Re-initialize registration via the Spring-managed service discovery component.
5. Re-register watches and resynchronize caches.
6. Re-acquire distributed locks or rejoin leader election as a new participant.
7. Resume business work only after verifying the instance is advertised and coordination rights have been re-granted.

In Spring Cloud, avoid calling ServiceRegistry.register() indiscriminately in every RECONNECTED callback if auto-registration or Curator ServiceDiscovery already manages re-registration. Registering twice can cause duplicate instances or node-already-exists errors. First verify the behavior of your Curator/Spring Cloud versions, then designate a single component responsible for registration recovery.

## 10. Handling operations with uncertain outcomes

A connection failure can happen after the server has executed an operation but before the client receives the response. For example, a client sends a znode creation command, ZooKeeper writes it successfully, and the response packet is lost. The client sees connection loss and does not know whether the operation succeeded.

Do not blindly retry a node creation with a fixed name because you may hit NODEEXISTS. For registration operations, you should:

- Use a stable instance ID within the registration lifecycle.
- Re-read the node or registration state before deciding to recreate it.
- Handle NODEEXISTS and NONODE contextually rather than treating every error as fatal.
- Use idempotent operations or check ownership/session before retrying.
- Never reuse an expired session ID.
- Ensure an old instance cannot overwrite a new instance's registration simply because two processes share the same ID.

Curator offers retry policies for many operations and recipes, but retries do not replace idempotent application design. Clearly identify which operations Curator retries automatically and which require business logic to verify results.

## 11. Scenarios causing unintended session expiration

| Cause | Mechanism of impact | Risk mitigation |
| --- | --- | --- |
| Prolonged network partition | Client fails to send heartbeats to the ensemble within the session limit. | Include sufficient peers in the connection string; inspect network paths and firewalls. |
| Long JVM stop-the-world GC | Heartbeat thread cannot run in time within the timeout window. | Monitor GC pauses, heap pressure, and set an appropriate session timeout. |
| CPU starvation or slow thread scheduling | ZooKeeper/Curator I/O threads do not run on schedule. | Monitor CPU throttling and avoid blocking callback threads. |
| Overloaded ZooKeeper ensemble | Heartbeats and requests are delayed; clients may drop connections. | Monitor latency, outstanding requests, and server load. |
| DNS or routing failures | Client cannot fail over to another peer or reconnect. | Use reliable DNS, verify connection string, and check cross-zone routes. |
| Session timeout too short | Even brief glitches exceed the threshold. | Choose timeout based on GC, network, tickTime, and instance detection needs. |
| Client closed or process restarted | Session ends; ephemeral nodes are deleted. | Perform graceful shutdown and verify fresh registration after startup. |

A session timeout that is too long delays detection of unreachable instances. A session timeout that is too short can cause healthy instances to be purged from the registry during pauses or brief network instability. Balance failure detection speed against system stability.

## 12. Testing both scenarios

A good test should prove the application handles both same-session reconnection and session expiration properly.

| Scenario | How to induce the condition | Expected observed outcome |
| --- | --- | --- |
| Brief disconnection | Temporarily block traffic from client to ZooKeeper, then restore before session timeout. | Curator emits SUSPENDED then RECONNECTED; ephemeral registration persists. |
| Long disconnection | Block traffic longer than the negotiated session timeout. | ZooKeeper deletes the ephemeral znode; client receives LOST upon reconnecting and must restore registration. |
| JVM pause | Induce a controlled pause exceeding session timeout in a test environment. | Observe SUSPENDED/LOST, znode deletion, and re-registration flow. |
| Single peer outage | Shut down one ZooKeeper server while keeping quorum and other peers running. | Client switches peers and can reconnect under the same session if still valid. |
| Ensemble quorum loss | Simulate quorum loss in a test environment. | Client cannot perform normal writes; track recovery time and session state. |

When inspecting the registry, use the ZooKeeper CLI or monitoring tools to check service paths and ephemeral nodes. Record session state, session ID, timestamps of SUSPENDED/LOST/RECONNECTED, when the node vanished, and when it was recreated.

Do not inspect only provider logs. Verify from the consumer's perspective: does the instance disappear from the discovery list, when does the cache update, and are requests routed to the disconnected address?

## 13. Operational checklist

- [ ] Know the actual negotiated session timeout, not just the requested configuration value.
- [ ] Distinguish connection-timeout, session-timeout, and retry policy.
- [ ] Monitor SUSPENDED, LOST, and RECONNECTED separately.
- [ ] On SUSPENDED, transition tasks requiring coordination guarantees into safe mode.
- [ ] On LOST, discard state tied to the old session and recreate required resources.
- [ ] Verify ephemeral registration and instance metadata after reconnection.
- [ ] Resynchronize watches/caches; do not rely solely on events during disconnection.
- [ ] Do not create a new session for a temporary TCP connection drop.
- [ ] Do not blindly retry node creation when the previous outcome is uncertain.
- [ ] Check Curator version since LOST semantics changed in Curator 3.0.0.
- [ ] Test network partitions, GC pauses, peer failover, and session expiration in an isolated environment.
- [ ] Monitor the registry from both provider and consumer sides.

## Key takeaways

- Losing a TCP connection does not mean the session has expired.
- If reconnecting before the session timeout, the client can keep using the old session and ephemeral znodes persist.
- When a session expires, ZooKeeper deletes ephemeral znodes owned by that session; the client must establish a new session and recover registrations.
- Curator emits SUSPENDED on connection loss; LOST indicates Curator believes the session has expired.
- LOST semantics changed in Curator 3.0.0, so verify your actual dependency version.
- RECONNECTED after LOST does not make locks, leadership, or registrations bound to the old session valid again.
- Watches and caches must be resynchronized after reconnecting; registry views can go stale during disconnections.
- Session timeout, connection timeout, and retry policies solve different problems.

## Official references

- [Apache ZooKeeper – Programmer's Guide: ZooKeeper Sessions](https://zookeeper.apache.org/doc/current/zookeeperProgrammers.html#ch_zkSessions)
- [Apache ZooKeeper – Programmer's Guide: Ephemeral Nodes and Watches](https://zookeeper.apache.org/doc/current/zookeeperProgrammers.html)
- [Apache Curator – Error Handling](https://curator.apache.org/docs/errors/)
- [Apache Curator – Tech Note 12: Connection Semantics](https://curator.apache.org/docs/tech-note-12/)
- [Apache Curator – Tech Note 14: Session Expiration](https://curator.apache.org/docs/tech-note-14/)
- [Apache Curator – Service Discovery](https://curator.apache.org/docs/service-discovery/)
- [Spring Cloud Zookeeper – Service Discovery](https://docs.spring.io/spring-cloud-zookeeper/reference/discovery.html)
- [Spring Cloud Zookeeper 4.3 – Common Application Properties](https://docs.spring.io/spring-cloud-zookeeper/reference/4.3/appendix.html)
