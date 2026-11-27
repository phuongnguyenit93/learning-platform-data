# Setting Up ZooKeeper and Observing Disconnects and Session Expiration

This practice sets up a local ZooKeeper server, connects a Curator client, creates an ephemeral node, and observes that node when the client loses network connectivity. Two scenarios are tested separately: restoring connectivity before the session timeout expires and restoring it after the session has expired.

The objective is to understand the session lifecycle in ZooKeeper and its impact on service discovery in Spring Cloud. ZooKeeper stores instance registration data as znodes; ephemeral znodes are tied to a client's session. When a session expires, the server deletes the ephemeral nodes owned by that session. Consumers watching the registry will learn that the instance has left the system.

## 1. Expected Outcomes

After completing this, you will be able to:

- Set up ZooKeeper with Docker Compose and verify the server is running.
- Create persistent and ephemeral znodes using the ZooKeeper CLI.
- Connect a Java application using Apache Curator.
- Observe the `CONNECTED`, `SUSPENDED`, `RECONNECTED`, `LOST`, and `READ_ONLY` states.
- Distinguish temporary TCP loss from session expiration.
- Verify that ephemeral nodes are deleted after session expiration.
- Restore registrations after the client receives a new session.
- Configure Spring Cloud Zookeeper Discovery and inspect service instances from `DiscoveryClient`.

## 2. Understanding Sessions Before Testing

ZooKeeper does not treat a TCP connection as a client's long-lived identity. Clients interact with the server through a **session** with a session ID and a negotiated timeout.

When a client creates an ephemeral node, ZooKeeper binds that node to the current session. The node is deleted when the session ends or expires. A client can lose TCP connectivity briefly while the session remains valid; if connectivity returns before the server expires the session, the client continues using the old session and the ephemeral node remains intact.

### 2.1. Distinguishing the States

| State | Meaning | Appropriate Action |
|---|---|---|
| `CONNECTED` | Curator connected successfully for the first time | Register instance and begin work |
| `SUSPENDED` | Connection to ZooKeeper was interrupted | Pause operations requiring coordination guarantees; do not assume writes succeeded |
| `RECONNECTED` | Connection was restored | Check state and continue if the old session is still valid |
| `LOST` | Curator considers the session expired or no longer usable | Treat old session as lost; re-register ephemeral nodes, re-acquire locks, and rejoin leader election |
| `READ_ONLY` | Client entered read-only mode when configuration allows | Do not perform writes or treat the instance as fully registered |

`SUSPENDED` does not mean `LOST`. A brief network interruption can produce a `SUSPENDED` then `RECONNECTED` sequence; the old session remains valid. If the outage lasts beyond the session timeout, the client enters `LOST`; after reconnecting, Curator can establish a new session and emit `RECONNECTED`.

Curator recommends treating `SUSPENDED` as a disconnect for safety-critical recipes like locks and leader election. While suspended, the application should pause work that depends on lock ownership or leadership. Upon `LOST`, assumptions about old locks, leadership, or ephemeral registrations must not be reused.

### 2.2. The Server Decides Expiration Time

When creating a session, the client sends its desired timeout. The ZooKeeper server negotiates the timeout within server-configured bounds.

With default settings:

- `tickTime` is typically 2,000 ms.
- `minSessionTimeout` defaults to `2 × tickTime`.
- `maxSessionTimeout` defaults to `20 × tickTime`.

If `tickTime=2000`, the server typically accepts session timeouts in the 4,000–40,000 ms range. Clients requesting values outside bounds may receive a server-adjusted timeout. Therefore, observe the actual negotiated timeout rather than looking solely at client-side config.

Session expiration is managed by the ZooKeeper server. When the server receives no heartbeat or valid request within the timeout window, the server expires the session and deletes all ephemeral nodes belonging to that session. A disconnected client cannot receive immediate notification at the moment the server deletes the node; it typically only learns the session expired upon reconnecting.

~~~mermaid
sequenceDiagram
    participant C as Curator client
    participant Z as ZooKeeper server
    participant O as Observer client

    C->>Z: Open session S1
    C->>Z: Create ephemeral node
    Z-->>O: Node appears
    Note over C,Z: Network partition
    C--xZ: Heartbeat / request unavailable
    Note over Z: Session timeout elapses
    Z-->>O: Ephemeral node deleted
    Note over C: Client still disconnected
    C->>Z: Network restored, reconnect with S1
    Z-->>C: Session S1 expired
    Note over C: Curator reports LOST
    C->>Z: Establish new session S2
    C->>Z: Re-create ephemeral node
    Z-->>O: New registration appears
~~~

A still-connected observer client will see the ephemeral node disappear when the server expires the session, even while the owner client remains disconnected and has not yet received the `LOST` event.

## 3. Setting Up ZooKeeper with Docker Compose

Create a `compose.yaml` file in the lab directory:

~~~yaml
services:
  zookeeper:
    image: zookeeper:3.9.7
    container_name: zk-lab
    hostname: zookeeper
    ports:
      - "127.0.0.1:2181:2181"
    environment:
      ZOO_TICK_TIME: "2000"
      ZOO_4LW_COMMANDS_WHITELIST: "ruok,stat,srvr,mntr"
    volumes:
      - zk-data:/data
      - zk-datalog:/datalog
    networks:
      - lab

volumes:
  zk-data:
  zk-datalog:

networks:
  lab:
    name: zk-discovery-lab
~~~

This configuration is for a single-node learning environment:

- `2181` is the client port.
- `ZOO_TICK_TIME` sets the tick time to 2 seconds.
- `ZOO_4LW_COMMANDS_WHITELIST` enables only the diagnostic commands needed for the lab.
- `/data` and `/datalog` are stored in named volumes so data is not lost when the container is recreated.
- The port is bound to `127.0.0.1`, avoiding exposing the client port on every interface of the machine.

ZooKeeper 3.9.7 is a current release in the 3.9 branch at the time of writing. In CI and deployment environments, pin the image digest after selecting a tested version.

Start it:

~~~bash
docker compose up -d
docker compose ps
docker compose logs -f zookeeper
~~~

On Windows PowerShell, test the port from the host:

~~~powershell
Test-NetConnection 127.0.0.1 -Port 2181
~~~

A result of `TcpTestSucceeded: True` only proves the TCP port is reachable. It does not verify quorum status or the ability to execute ZooKeeper operations.

### 3.1. Checking the Server with CLI

Open the ZooKeeper CLI inside the container:

~~~bash
docker compose exec zookeeper zkCli.sh -server 127.0.0.1:2181
~~~

Inside the CLI, inspect the znode tree:

~~~text
ls /
create /lab "root"
create /lab/sessions "sessions"
create -e /lab/sessions/manual "owner=cli"
ls /lab/sessions
stat /lab/sessions/manual
~~~

In the `stat` output, a non-zero `ephemeralOwner` field indicates the node belongs to a session. For persistent nodes, `ephemeralOwner` is 0.

Open a second CLI to observe the node:

~~~text
ls /lab/sessions
stat /lab/sessions/manual
~~~

Exit the CLI that created the node using `quit` or by closing the terminal session. When the session closes normally, the ephemeral node disappears. This is a basic lifecycle check; subsequent sections keep the client running and disrupt only the network to distinguish `SUSPENDED` from `LOST`.

### 3.2. Four Letter Words Diagnostic Commands

You can perform quick checks using these commands:

- `ruok`: the server returns `imok` when the process is alive and the client port is bound.
- `stat`: server status and connection info.
- `srvr`: server information.
- `mntr`: key/value monitoring metrics.

`ruok` does not prove the server has joined a quorum. With a multi-node ensemble, use `stat` or `mntr` to check mode/role and sync status. The `cons` and `dump` commands can reveal sessions, connections, and ephemeral nodes; enable them only in controlled labs and never expose diagnostic endpoints to public networks.

In production, prefer secured AdminServer/metrics endpoints and enable only the diagnostic interfaces strictly needed.

## 4. Connecting Spring Cloud Zookeeper Discovery

Spring Cloud Zookeeper uses Apache Curator and its service-discovery extension to register instance metadata such as host, port, ID, and service name. When the discovery dependency is on the classpath, the application can both register itself and query other services.

### 4.1. Dependency

Add the starter to the Spring Boot application:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-zookeeper-discovery</artifactId>
</dependency>
~~~

Manage versions with a Spring Cloud BOM compatible with your project's Spring Boot version. Do not pin a different Curator version than Spring Cloud's dependency management without checking compatibility.

### 4.2. Connection and Registration Configuration

If the application runs directly on the host:

~~~yaml
spring:
  application:
    name: inventory-service
  cloud:
    zookeeper:
      connect-string: localhost:2181
      connection-timeout: 3000
      session-timeout: 10000
      discovery:
        enabled: true
        register: true
        root: /services
~~~

If the application runs in a container on the same network as ZooKeeper, use the service hostname:

~~~yaml
spring:
  cloud:
    zookeeper:
      connect-string: zookeeper:2181
~~~

`session-timeout` is specified in milliseconds. The 10,000 ms value in the example falls within the server's typical default range when `tickTime=2000`. The server retains the right to negotiate the value within its configured bounds.

Do not confuse `connection-timeout` with `session-timeout`:

- Connection timeout limits how long establishing a connection takes.
- Session timeout defines how long the server tolerates receiving no heartbeat/request before expiring the session.

### 4.3. Inspecting Service Registration

Start the application and open the ZooKeeper CLI:

~~~text
ls /services
ls /services/inventory-service
~~~

Spring Cloud Zookeeper uses `/services` as the default root. Under the service name sits instance metadata managed by the discovery extension. Instance registration nodes are tied to the session lifecycle; do not manually edit or delete nodes managed by a running application.

Consumers can query using Spring Cloud's common abstraction:

~~~java
import java.util.List;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Service;

@Service
public class InventoryLookup {

    private final DiscoveryClient discoveryClient;

    public InventoryLookup(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public List<ServiceInstance> findInventoryInstances() {
        return discoveryClient.getInstances("inventory-service");
    }
}
~~~

During testing, record the number of instances returned before inducing a disconnect, while the session is expired, and after registration is restored.

## 5. Creating a Standalone Curator Session Probe

To observe session states directly, you can run a standalone Java probe. This probe creates an ephemeral node, prints connection states, and re-registers itself when Curator reports `LOST` and then reconnects.

### 5.1. Curator Dependency

If building a standalone Java program without a Spring Cloud starter, add `curator-framework`:

~~~xml
<dependency>
    <groupId>org.apache.curator</groupId>
    <artifactId>curator-framework</artifactId>
    <version>5.9.0</version>
</dependency>
~~~

Curator 5.9.0 is the current Apache Curator release at the time of writing. If the probe runs inside a Spring Cloud application, prefer the Curator version managed by the application's BOM.

### 5.2. Code to Observe Session and Ephemeral Node

~~~java
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

import org.apache.curator.framework.CuratorFramework;
import org.apache.curator.framework.CuratorFrameworkFactory;
import org.apache.curator.framework.state.ConnectionState;
import org.apache.curator.retry.ExponentialBackoffRetry;
import org.apache.zookeeper.CreateMode;

public class SessionProbe {

    private static final String PATH = "/lab/sessions/probe-1";

    private static final byte[] DATA =
            "service=inventory-probe;port=8080"
                    .getBytes(StandardCharsets.UTF_8);

    public static void main(String[] args) throws Exception {
        String connectString =
                System.getProperty("zk", "localhost:2181");

        CuratorFramework client = CuratorFrameworkFactory.builder()
                .connectString(connectString)
                .sessionTimeoutMs(10_000)
                .connectionTimeoutMs(3_000)
                .retryPolicy(new ExponentialBackoffRetry(500, 5))
                .build();

        AtomicBoolean sessionWasLost = new AtomicBoolean(false);
        ExecutorService recoveryExecutor =
                Executors.newSingleThreadExecutor();

        client.getConnectionStateListenable().addListener((ignored, state) -> {
            System.out.println(Instant.now() + " state=" + state);

            if (state == ConnectionState.SUSPENDED) {
                System.out.println(
                        "Connection lost; pause work that requires coordination");
            }

            if (state == ConnectionState.LOST) {
                System.out.println(
                        "Session expired; old ephemeral nodes are no longer valid");
                sessionWasLost.set(true);
            }

            if (state == ConnectionState.RECONNECTED
                    && sessionWasLost.compareAndSet(true, false)) {
                recoveryExecutor.submit(() -> register(client));
            }

            if (state == ConnectionState.READ_ONLY) {
                System.out.println(
                        "Read-only connection; do not assume writes are available");
            }
        });

        client.start();

        if (!client.blockUntilConnected(15, TimeUnit.SECONDS)) {
            client.close();
            throw new IllegalStateException("Cannot connect to ZooKeeper");
        }

        register(client);

        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            recoveryExecutor.shutdown();
            client.close();
        }));

        new CountDownLatch(1).await();
    }

    private static void register(CuratorFramework client) {
        try {
            String createdPath = client.create()
                    .creatingParentsIfNeeded()
                    .withMode(CreateMode.EPHEMERAL)
                    .forPath(PATH, DATA);

            System.out.println(
                    Instant.now() + " registered ephemeral node " + createdPath);
        } catch (Exception ex) {
            System.err.println(
                    Instant.now() + " registration failed: " + ex.getMessage());
        }
    }
}
~~~

Points to note:

- The listener is registered before `client.start()` so initial states are not missed.
- `SUSPENDED` only notes connection loss; the probe does not immediately recreate the node because the old session may still be valid.
- Only upon receiving `LOST` is the `sessionWasLost` flag set.
- After `RECONNECTED`, if `LOST` occurred previously, the probe runs re-registration on a separate executor.
- Do not perform long synchronous ZooKeeper operations directly inside the listener callback.
- If `NodeExistsException` occurs, investigate instance ID/session conflicts. Do not blindly delete the node.

For real applications, ephemeral registrations, locks, and leader elections must be recovered using the exact abstractions the application uses. This example only illustrates a standalone node; Spring Cloud Zookeeper Discovery manages service registration itself through the discovery extension. Test the recovery behavior of your actual library version rather than manually creating extra znodes under `/services`.

## 6. Observing Sessions with Two Clients

Two independent clients are needed:

- **Owner client:** runs `SessionProbe`, creating `/lab/sessions/probe-1`.
- **Observer client:** another ZooKeeper CLI used to check whether the node still exists.

The `docker network disconnect` command in subsequent steps only applies when the Owner client is running inside a container attached to the `zk-discovery-lab` network. For example, after packaging the probe into an image:

~~~bash
docker run -d --name zk-probe --network zk-discovery-lab -e JAVA_TOOL_OPTIONS="-Dzk=zookeeper:2181" <probe-image>
docker logs -f zk-probe
~~~

Replace `<probe-image>` with the application image containing the `SessionProbe` class. If running the probe directly on the host, move the probe into a lab container or use a separate firewall isolation mechanism; `docker network disconnect` does not affect processes running outside Docker.

Keep the Owner client running continuously. In the Observer CLI:

~~~text
ls /lab/sessions
stat /lab/sessions/probe-1
~~~

Record `ephemeralOwner` and the timestamp the node appeared. When Owner loses network access, Observer remains connected to ZooKeeper and can observe when the server deletes the node.

Do not close the Owner client during the test. Calling `client.close()` or exiting the program intentionally terminates the session and deletes the ephemeral node immediately; that action does not simulate a network partition.

## 7. Experiment A: Disconnect Shorter Than Session Timeout

Assume the probe requests a 10-second session timeout. Use a client running inside a container attached to the `zk-discovery-lab` network. If the application runs in a container, use the address `zookeeper:2181`.

Identify the client container running the probe. Disconnect only that container from ZooKeeper's network:

~~~bash
docker network disconnect zk-discovery-lab <probe-container>
~~~

Wait about 3 seconds, significantly shorter than the 10-second session timeout. Then reconnect:

~~~bash
docker network connect zk-discovery-lab <probe-container>
~~~

Watch the probe's logs. Typical output:

~~~text
CONNECTED
SUSPENDED
RECONNECTED
~~~

Inspect the node again from Observer:

~~~text
ls /lab/sessions
stat /lab/sessions/probe-1
~~~

The node still exists because the old session has not expired. `sessionWasLost` was not set, so the probe did not recreate the node and did not encounter a `NodeExists` conflict.

**Conclusion of Experiment A:** losing TCP connectivity does not automatically delete ephemeral nodes. When the client returns in time, ZooKeeper can resume the old session.

## 8. Experiment B: Disconnect Longer Than Session Timeout

Return the probe to a stable connected state and confirm the node exists. Disconnect the client container from the network again:

~~~bash
docker network disconnect zk-discovery-lab <probe-container>
~~~

Keep the outage longer than the negotiated timeout. With the 10-second example, wait around 20 seconds to allow safety margin for heartbeat schedules, timers, and processing time.

While owner is disconnected, use the Observer CLI to inspect:

~~~text
ls /lab/sessions
~~~

After the server expires the session, `/lab/sessions/probe-1` will vanish. Owner still cannot receive a notification because it is disconnected.

Restore the network:

~~~bash
docker network connect zk-discovery-lab <probe-container>
~~~

When Curator reconnects, observe the state sequence:

~~~text
SUSPENDED
LOST
RECONNECTED
registered ephemeral node /lab/sessions/probe-1
~~~

Exact log ordering may vary depending on when the client receives events and the Curator version. What must be verified is:

1. Observer sees the old ephemeral node disappear when the server expires the session.
2. Owner learns the old session was lost upon reconnecting.
3. Curator establishes a new session.
4. The probe re-registers the ephemeral node.
5. Observer sees the node reappear.

**Conclusion of Experiment B:** session expiration is a session lifecycle event, not just a TCP reconnect. Ephemeral nodes from the old session have been deleted and must be recreated under a new session.

## 9. Why Does the Owner Not Receive Expiration Notification Immediately?

When a client undergoes a network partition, the ZooKeeper server keeps running and continues managing sessions. After the timeout elapses, the server deletes the ephemeral node and notifies other connected clients watching the node.

The Owner client is disconnected, so it cannot receive events at that time. When the network is restored and the client tries to reconnect, the server reports that the old session has expired. Only then does the client receive the expired status / Curator `LOST`.

Therefore, two different moments can be observed:

- **When the registry changes:** the ephemeral node has been deleted by the server; observers see the service instance disappear.
- **When the owner learns:** the client reconnects and is informed the session expired.

This is why consumers can stop seeing an instance before the provider itself logs `LOST`.

## 10. Monitoring the Server with stat and mntr

In the lab, use the Four Letter Words commands enabled in the allowlist:

~~~bash
docker compose exec zookeeper zkServer.sh status
~~~

Or send `ruok`, `stat`, `mntr` via a netcat-capable TCP client:

~~~bash
printf ruok | nc 127.0.0.1 2181
printf stat | nc 127.0.0.1 2181
printf mntr | nc 127.0.0.1 2181
~~~

Useful fields in `mntr`:

| Metric | Meaning |
|---|---|
| `zk_server_state` | Role/state such as standalone, leader, or follower |
| `zk_num_alive_connections` | Number of active client connections |
| `zk_znode_count` | Number of znodes |
| `zk_watch_count` | Number of watches |
| `zk_outstanding_requests` | Number of requests awaiting processing |
| `zk_avg_latency` | Average request processing latency |
| `zk_max_latency` | Maximum processing latency per server statistics |

During the session expiration experiment, observe connection count and znode count simultaneously. Znode count may decrease when the ephemeral node is deleted. In environments with multiple applications, filter by path/service instead of inferring from total znode count.

`ruok` returning `imok` only shows the server process is alive and the client port is bound; it does not confirm quorum. In an ensemble, inspect leader/follower status and synced follower count.

## 11. Connecting to Spring Cloud Zookeeper Discovery

Spring Cloud Zookeeper uses the Curator service-discovery extension to manage registrations. When a provider registers, instance metadata is stored under the `/services` tree. Because registrations are tied to a session, they can be deleted when the session expires.

When running provider and consumer applications, record three perspectives:

| Perspective | How to Observe | Question |
|---|---|---|
| ZooKeeper tree | `ls /services/inventory-service` | Does the registration znode still exist? |
| Provider client | Curator connection state logs | Is the client SUSPENDED, LOST, or RECONNECTED? |
| Consumer | `DiscoveryClient.getInstances()` | Does the consumer still see the instance? |

Expected experiment outcomes:

- Brief disconnect: provider may log `SUSPENDED` then `RECONNECTED`; the old session keeps the registration.
- Disconnect exceeding timeout: old session expires and ephemeral registration disappears; consumer no longer sees the instance after updating its discovery view.
- Provider reconnects: the discovery extension must restore registration per the lifecycle of the version in use; consumer will see the instance return once the registry/discovery cache converges.

Do not conclude the consumer has updated solely because the provider logged `RECONNECTED`. Re-query `DiscoveryClient` from the consumer or check the znode on ZooKeeper.

### 11.1. Distinguishing Session Timeout from Discovery Cache

There can be latency between milestones:

1. ZooKeeper server expires the session.
2. Ephemeral znode is deleted.
3. Watcher/Curator receives the event.
4. Spring Cloud discovery extension updates its state.
5. Consumer refreshes discovery results or cache.

If the consumer still sees the instance after the znode disappears, inspect the discovery client cache and query timing. Do not lengthen session timeout just to mask an unrefreshed cache.

### 11.2. Do Not Use Registration Znodes as Authorization Sources

An entry appearing under `/services` only proves a registration exists under the discovery mechanism. It does not replace identity authentication or authorization when consumers call APIs. Business endpoints still require TLS, authentication, and proper access control policies.

## 12. Verifying Safe Recovery After LOST

When Curator reports `LOST`, the application should treat all state tied to the old session as no longer trustworthy:

- Ephemeral registrations must be recreated.
- Distributed locks must be re-acquired via a fresh acquire operation.
- Leader election must be rejoined.
- Watches must be re-established according to the corresponding recipe/lifecycle.
- Do not continue writing based on the assumption that the instance still holds the old lock or leadership.

Not every operation needs manual recreation. Curator recipes and the Spring Cloud Zookeeper discovery extension have their own lifecycle mechanisms. However, application-managed business logic must still recognize session loss and restore state accordingly.

If locks are used to protect resources outside ZooKeeper, fencing tokens or an equivalent mechanism are needed at the protected resource. Session expiration cannot by itself stop an old process from continuing to execute if that process has not yet received notification due to a network partition.

## 13. Tuning Session Timeout and Retry Policy

Session timeout is a trade-off between how fast client disconnects are detected and tolerance for network jitter:

- Short timeout: ephemeral registrations are cleaned up quickly, yet healthy clients may expire during transient network blips.
- Long timeout: reduces risk of expiry from brief outages, yet stale registrations linger longer and failover is slower.

Do not lower the timeout just to see `LOST` quickly in the lab and carry that exact setting into production. Measure reconnect time, heartbeats, network latency, and ensemble processing time before choosing a value.

Curator's retry policy governs how failed operations are retried. It does not turn an expired session back into a valid old session. After `LOST`, the application must use a new session and recover ephemeral state.

With an ensemble, the client connection string should list multiple servers so the client can connect to surviving nodes. If only one server is listed, an outage on that server leaves the client with no alternate endpoint even while quorum remains intact.

## 14. Scaling from Standalone to Ensemble

The Compose file in this lesson runs only one server to observe lifecycle behavior. It does not provide high availability: when the single node stops, there is no quorum to serve requests.

In production, ZooKeeper is typically deployed with an odd number of voting members, commonly 3 or 5:

- A 3-node ensemble tolerates losing 1 node because quorum 2 remains.
- A 5-node ensemble tolerates losing 2 nodes because quorum 3 remains.
- Losing more than half of voting members deprives the ensemble of quorum to continue processing writes.

When one node fails while quorum remains, clients can reconnect to another node and continue their old session if it has not expired. When a client is isolated from the entire ensemble for too long, its session can expire even though the remaining servers are still running.

Do not use a single local ZooKeeper node to simulate all quorum scenarios. This practice tests session lifecycle and ephemeral registration; testing leader election, quorum loss, and failover requires a multi-node ensemble.

## 15. Troubleshooting

| Symptom | Possible Cause | How to Verify |
|---|---|---|
| `CONNECTED` never appears | Wrong connect string, server not ready, or TCP blocked | Check ports, logs, `zkServer.sh status` |
| `SUSPENDED` then `RECONNECTED`, node remains | Connectivity restored before session expiry | Check `ephemeralOwner` and node path |
| `LOST` appears, node vanishes | Session expired or Curator deemed session unusable | Observer inspects znode and server logs |
| No `LOST` after waiting | Network not completely blocked or negotiated timeout larger than expected | Check container network, session timeout, and server min/max |
| Node does not vanish | Owner still heartbeating over another network path or timeout not yet exceeded | Check all addresses in connect string and observer |
| Node is not recreated | Recovery listener did not run, Curator not reconnected, or create failed | Check `RECONNECTED`, exceptions, and ACL permissions |
| `NodeExistsException` on re-registration | Another registration uses the same path or old owner not yet expired | Check `ephemeralOwner`; do not blindly delete node |
| Consumer still sees old instance | Discovery cache not refreshed or query occurred before update | Check znode, discovery client, and cache timestamp |
| `ruok` returns `imok` but writes fail | Server process alive but lacks quorum or is read-only | Use `stat`, `mntr`, and server logs |
| Only one app fails to reconnect | Container not reattached to network or wrong connect string | Check network attachments and DNS |

## 16. Lab Completion Checklist

- [ ] ZooKeeper container running and client port 2181 accessible.
- [ ] CLI can create persistent parent and ephemeral child nodes.
- [ ] Curator probe connects and logs `CONNECTED`.
- [ ] Observer sees the ephemeral node and reads `ephemeralOwner`.
- [ ] Disconnecting shorter than timeout produces `SUSPENDED` then `RECONNECTED`.
- [ ] After the short outage, the ephemeral node still exists.
- [ ] Disconnecting longer than timeout causes the server to delete the ephemeral node.
- [ ] Owner receives `LOST` upon reconnecting.
- [ ] Curator establishes a new session and probe recreates the ephemeral node.
- [ ] Spring Cloud Zookeeper consumer re-verified via `DiscoveryClient`.
- [ ] Distinguished connection timeout, session timeout, and cache refresh.
- [ ] Understood limits of a standalone node compared to a production ensemble.

## 17. Key Takeaways

- A session is a longer-lived identity than a TCP connection; losing TCP does not equate to session expiration.
- `SUSPENDED` indicates connection loss; `RECONNECTED` may resume the old session.
- `LOST` means the application must treat the old session as invalid.
- The ZooKeeper server decides session expiration and deletes ephemeral nodes owned by that session.
- A disconnected owner client typically learns about expiration only upon reconnecting.
- Curator's retry policy cannot rescue an already expired session.
- After `LOST`, recreate ephemeral registrations and re-acquire coordination state.
- `ruok` only confirms process/client port; check quorum using `stat` or metrics.
- Spring Cloud Zookeeper uses Curator's service-discovery extension; verify provider, znode, and consumer alike.
- Timeouts must be chosen based on network jitter and failover requirements; never choose them just for fast tests.
- One ZooKeeper node fits labs; production requires an ensemble and quorum.

This practice shows that service discovery depends directly on ZooKeeper's session lifecycle. Once the boundary between reconnect and session expiration is clear, development teams can predict when instances leave the registry, design proper recovery, and avoid continuing to rely on registrations or locks belonging to an expired session.

## References

- [Apache ZooKeeper — Programmer's Guide](https://zookeeper.apache.org/doc/current/zookeeperProgrammers.html)
- [Apache ZooKeeper — Administrator's Guide](https://zookeeper.apache.org/doc/current/zookeeperAdmin.html)
- [Apache ZooKeeper — Releases](https://zookeeper.apache.org/releases/)
- [Docker Official Image — ZooKeeper](https://hub.docker.com/_/zookeeper)
- [Apache Curator — Error Handling and Connection States](https://curator.apache.org/docs/errors/)
- [Apache Curator — Tech Note 12: Connection Semantics](https://curator.apache.org/docs/tech-note-12/)
- [Apache Curator — Tech Note 14: Session Timeout](https://curator.apache.org/docs/tech-note-14/)
- [Apache Curator — Releases](https://curator.apache.org/download/)
- [Spring Cloud Zookeeper — Service Discovery](https://docs.spring.io/spring-cloud-zookeeper/reference/discovery.html)
- [Spring Cloud Zookeeper — Configuration Properties](https://docs.spring.io/spring-cloud-zookeeper/reference/appendix.html)
