# Connection Sessions, Session Timeouts, and Ephemeral Node Lifecycle

In ZooKeeper, a client does not merely open a TCP connection and send independent commands. The client creates a **session** with the ZooKeeper cluster and maintains that session across network connections. The session is the unit the server uses to track the client, ownership of ephemeral znodes, and when the client is considered lost.

This is critical for service discovery. When a service instance registers with an ephemeral znode, that node exists bound to the session that created it. If the network connection fluctuates while the session remains valid, the znode can continue to exist. If the session expires, ZooKeeper automatically deletes all ephemeral znodes belonging to that session. An instance wishing to reappear in the registry must establish a new session and re-register.

In Spring Cloud Zookeeper Discovery, the Curator library manages connections and session lifecycle on the client side. Understanding connection states, session timeouts, and ephemeral nodes helps handle network drops, restarts, JVM pauses, and service re-registration properly.

## 1. What is a session in ZooKeeper?

A session is a logical working session between a ZooKeeper client and the ZooKeeper cluster. When a client connects for the first time, the server creates a session and issues a session ID along with session credentials. The client uses this session across subsequent connections.

A session has the following characteristics:

- It has a distinct identifier, the session ID.
- It is kept alive via heartbeat packets and client-server activity.
- It has a timeout requested by the client and negotiated by the server.
- It can survive a connection drop if the client reconnects before the session expires.
- When it expires, the server deletes all ephemeral znodes belonging to the session.

A session is not synonymous with a single TCP connection. A TCP connection can be dropped and re-established while the session remains valid. This is the key to distinguishing a temporary disconnection from a client genuinely losing ownership of its ephemeral nodes.

~~~mermaid
flowchart TD
    C["ZooKeeper client"] -->|"Create session"| S[("ZooKeeper ensemble")]
    S -->|"Session ID and negotiated timeout"| C
    C <-->|"Heartbeat / request / response"| S
    C -->|"Create ephemeral znode"| E["Ephemeral znode"]
    E -->|"Bound to session owner"| S
~~~

In service discovery, each instance can create a znode representing itself. The session is how ZooKeeper knows which instance owns that znode.

## 2. Session timeout and connection timeout

Two types of timeouts are frequently confused:

| Timeout | Meaning | Consequence on expiration |
|---|---|---|
| Connection timeout | Time spent waiting to establish a connection to a server or endpoint | The current connection attempt fails; the client may try another server |
| Session timeout | Maximum time the server waits for valid activity from the client before considering the session expired | The session is terminated and ephemeral znodes belonging to the session are deleted |

Connection timeout is usually shorter and applies to an individual connection attempt. Session timeout governs the logical lifecycle of the session. A connection timeout does not automatically mean the session has expired.

### Client requests, server negotiates

The client requests a session timeout when creating a session. The ZooKeeper server negotiates an effective value within the bounds the server permits. In ZooKeeper configuration, those bounds are typically controlled by minSessionTimeout and maxSessionTimeout; if not configured explicitly, default values are derived from the server's tickTime.

Therefore, the value requested by the client is not necessarily the final value. Check client logs or session info and cluster configuration when you need to determine the actual timeout.

A session timeout that is too short can cause a JVM pause, long GC, or brief network glitch to expire the session. A timeout that is too long keeps ephemeral nodes in the registry longer after an instance has died, slowing down detection of inactive instances.

### Choosing a session timeout

When choosing a timeout, consider:

- JVM or container pauses that can occur under heavy load.
- Network latency between the application and the ZooKeeper ensemble.
- Recovery time when a ZooKeeper node fails or the client fails over to another server.
- How long stale instances are acceptable in discovery results.
- Heartbeat load and total session count on the cluster.

Avoid setting an ultra-short timeout just to detect failures quickly. Overly sensitive failure detection can cause instances to repeatedly lose sessions and re-register when the system only experiences brief slowdowns.

## 3. Heartbeats keep the session alive

A ZooKeeper client keeps its session alive by sending heartbeats and requests to the server. The server updates the session's last active timestamp. If it receives no activity within the negotiated timeout, the server may consider the session expired.

Heartbeats are normally managed automatically by the client library. A Spring Boot application does not need to write its own ping scheduler to keep a session alive when using Spring Cloud Zookeeper and Curator properly.

~~~mermaid
sequenceDiagram
    participant A as Application / Curator
    participant Z as ZooKeeper server
    participant N as Ephemeral znode
    A->>Z: Open session
    Z-->>A: Session ID and timeout
    A->>N: Create ephemeral znode
    loop While session is valid
        A->>Z: Heartbeat or request
        Z-->>A: Response
    end
~~~

Heartbeats are not business health checks. They prove that the client can still maintain communication with ZooKeeper. They do not prove that the service's API is processing correctly, that the database is working, or that the instance is ready to serve every request.

Thus, distinguish carefully between:

- **Session liveness:** whether the client can still maintain a session with ZooKeeper.
- **Process liveness:** whether the application process is still running.
- **Service health/readiness:** whether the instance is eligible to receive business requests.

An application can keep a healthy session while its business endpoints are failing. Conversely, an application may still be running and serving requests while temporarily disconnected from ZooKeeper.

## 4. What is an ephemeral znode?

A znode is the data unit in ZooKeeper's hierarchical tree. Two common types exist:

- **Persistent znode:** remains until deleted by a client or administrator.
- **Ephemeral znode:** created bound to a session and automatically deleted when that session expires.

In service discovery, ephemeral znodes are well-suited to represent registered instances. When an instance loses its session, the registry automatically removes the corresponding record without requiring the dead process to run cleanup code.

Illustrative tree structure:

~~~text
/services                         (persistent)
  /inventory-service              (persistent)
    /instance-01                  (ephemeral)
    /instance-02                  (ephemeral)
  /payment-service                (persistent)
    /instance-01                  (ephemeral)
~~~

Parent znodes are usually persistent to preserve the tree structure. Instance znodes are ephemeral, holding data such as host, port, metadata, or routing info. The exact structure is determined by the discovery library and deployment version; the tree above illustrates the relationship between services and instances.

### Characteristics of ephemeral znodes

- Bound to the session that created the node.
- Automatically deleted when the owning session expires.
- Cannot have child znodes beneath an ephemeral znode.
- Ephemeral sequential nodes can be used if you need ZooKeeper to append a sequential suffix to the name.
- Does not expire merely because a TCP connection closes; deletion is tied to session expiration.

The ephemeralOwner field in a znode's stat indicates the session ID that owns an ephemeral node. For persistent znodes, ephemeralOwner is 0.

## 5. Ephemeral node lifecycle when a service registers

Suppose inventory-service runs two instances. Each instance creates its own session and registers its ephemeral znode:

~~~mermaid
sequenceDiagram
    participant I1 as Inventory instance 01
    participant I2 as Inventory instance 02
    participant Z as ZooKeeper
    participant C as Discovery consumer
    I1->>Z: Open session S1
    I2->>Z: Open session S2
    I1->>Z: Create ephemeral /services/inventory/01
    I2->>Z: Create ephemeral /services/inventory/02
    Z-->>C: Watch /services/inventory
    C->>Z: Read instance list
    Z-->>C: Instance 01, Instance 02
    Note over I2,Z: Session S2 expires
    Z->>Z: Delete S2's ephemeral node
    Z-->>C: Watch event: instance 02 deleted
    C->>Z: Re-read instance list
    Z-->>C: Only instance 01 remains
~~~

Typical flow:

1. The instance starts and establishes a session with ZooKeeper.
2. The discovery client creates an ephemeral znode containing instance information.
3. Consumers read the instance list and may register watches to be notified when the tree changes.
4. When the instance stops gracefully, the client can proactively delete the node and close the session.
5. If the process crashes or suffers a prolonged network loss, the server detects session expiration and deletes the node automatically.
6. Consumers receive the change notification, re-read the data, and update their instance list.

Registering and unregistering through the application lifecycle keeps registry state cleaner. However, automatic deletion of ephemeral nodes on session expiration remains essential because shutdown hooks cannot run in every failure scenario.

## 6. Temporary disconnection does not mean the session has expired

This is the most important scenario when operating ZooKeeper.

Suppose an application loses connectivity to ZooKeeper for a few seconds due to a network interruption. During this time, the client cannot send heartbeats. If the session timeout has not elapsed, the server keeps the session and ephemeral znodes alive. When the client reconnects and resumes the old session, the znodes remain intact.

~~~mermaid
flowchart TD
    A["Client is CONNECTED"] --> B["Network connection lost"]
    B --> C["Session still within timeout"]
    C --> D{"Reconnected in time?"}
    D -->|"Yes"| E["RECONNECTED with old session"]
    E --> F["Ephemeral node still exists"]
    D -->|"No"| G["Server expires session"]
    G --> H["Ephemeral node is deleted"]
    H --> I["Client creates new session"]
    I --> J["Re-register ephemeral node"]
~~~

Therefore:

- Do not delete and recreate the entire registration just because a socket briefly dropped if the session can still recover.
- Do not declare an instance dead immediately upon receiving a connection-lost signal.
- Distinguish temporary connection states from session-expired events.
- If the session has already expired, the old node cannot be preserved by reconnecting to that session.

During the disconnection window, consumers may still see the ephemeral node in the registry. This does not guarantee the instance can still accept requests. Consumer timeouts and error handling remain necessary.

## 7. Session expiration and re-registration

Session expiration is fundamentally different from a successful reconnect. Once the server marks a session expired:

1. The old session is no longer valid.
2. ZooKeeper deletes every ephemeral znode owned by that session.
3. The client cannot continue using the old session ID.
4. The client must establish a new session.
5. The discovery integration must re-register the ephemeral nodes representing the instance.

An application process and even its API may still be running when a session expires. For example, the JVM may pause longer than the timeout, or the node may be network-partitioned for an extended period. Upon resuming activity, the application must recognize that the session was lost and complete re-registration before considering itself a published instance in discovery.

### Do not blindly reuse the old registration

When a new session is created, the old ephemeral node has already been deleted. Keeping an old znode path or stale data copy in client memory does not mean that node still exists on the server.

A recovery procedure should:

- Establish a new session and confirm connection stability.
- Recreate the registration znode with the appropriate instance ID.
- Handle the case where the node already exists due to another registration or a repeated recovery flow.
- Update watches and caches on consumers.
- Report the instance as registered only after node creation succeeds.

If multiple recovery threads can run concurrently, synchronize them to prevent creating the same path twice. Use idempotent operations, verify node ownership, and handle NodeExistsException according to instance identity.

## 8. Connection states in Curator

Spring Cloud Zookeeper typically uses Apache Curator to manage the ZooKeeper client. Curator exposes connection states that help applications distinguish temporary disconnections from session loss.

Common states:

| Curator state | Meaning | Interpretation in service discovery |
|---|---|---|
| CONNECTED | Connection and session are ready | Discovery operations can proceed |
| SUSPENDED | Connection interrupted or temporarily uncertain | Do not conclude the session has expired; pause registry-dependent decisions if needed |
| RECONNECTED | Client reconnected | Can resume the old session if it has not expired |
| LOST | Session expired or invalidated | Ephemeral node was deleted; must establish a new session and re-register |

Exact state names and callback details depend on the Curator version, but the principle of distinguishing SUSPENDED, RECONNECTED, and LOST remains crucial.

Conceptual handling:

~~~text
CONNECTED:
  Allow normal discovery operations.

SUSPENDED:
  Mark registry state as uncertain.
  Restrict operations that require guaranteed session ownership.
  Wait for reconnect outcome or session loss.

RECONNECTED:
  If the old session is still valid, continue watching and verify registration.
  Refresh discovery snapshot if needed.

LOST:
  Do not rely on registrations tied to the old session.
  Create a new session and re-register ephemeral nodes.
  Advertise the instance after registration succeeds.
~~~

Do not treat SUSPENDED the same as LOST. Deleting nodes or creating new registrations immediately upon a brief network drop causes unnecessary churn. Conversely, ignoring LOST can leave a running instance missing from the registry.

## 9. Session configuration in Spring Cloud Zookeeper

Applications using Spring Cloud Zookeeper Discovery need to declare the ZooKeeper ensemble endpoints and may tune connection timeout and session timeout according to deployment needs.

Illustrative configuration example:

~~~yaml
spring:
  application:
    name: inventory-service
  cloud:
    zookeeper:
      connect-string: zk-1.internal:2181,zk-2.internal:2181,zk-3.internal:2181
      session-timeout: 10000
      connection-timeout: 15000
      discovery:
        enabled: true
        register: true
        root: /services
        instance-id: inventory-service-node-01
~~~

In this example, timeouts are expressed in milliseconds following common Spring Cloud Zookeeper configuration style. Verify data types and property names in the exact Spring Cloud version in use. The client-requested value remains subject to the min/max session timeout limits negotiated by the ZooKeeper server.

Each property serves a distinct role:

- **connect-string:** list of hosts and client ports of the ZooKeeper ensemble.
- **session-timeout:** session timeout requested by the client; affects when the server considers a session expired.
- **connection-timeout:** wait limit when establishing a connection.
- **discovery.root:** root node used to organize service registrations.
- **discovery.instance-id:** identifier of the registered instance; must be unique within the service scope.
- **discovery.register:** enables or disables instance registration.

Do not confuse client port 2181 with quorum, election, or internal server-to-server ports of ZooKeeper. Applications connect to the ensemble's client port; servers manage internal ports.

## 10. Observing ephemeral nodes with ZooKeeper CLI

You can use the ZooKeeper CLI to inspect nodes and owner state. For example, in a test environment after connecting to the server:

~~~text
create /services ""
create /services/inventory-service ""
create -e /services/inventory-service/instance-01 "{\"host\":\"10.0.1.11\",\"port\":8081}"
ls /services/inventory-service
stat /services/inventory-service/instance-01
get -s /services/inventory-service/instance-01
~~~

The two parent nodes are created as persistent; the instance node is created with the ephemeral option. The stat output reveals the node's ephemeralOwner. A non-zero value indicates the node is bound to a session.

When the CLI client exits or its session is lost, the server does not necessarily delete the node at the exact moment the socket closes. The node is deleted when the owning session expires. You can observe this by waiting past the session timeout and re-reading the tree:

~~~text
ls /services/inventory-service
~~~

The commands above illustrate observation only. In real environments, do not manually create dummy nodes colliding with paths managed by Spring Cloud Zookeeper. Node ACLs must also be configured appropriately; never use open ACLs allowing anyone to write in production.

## 11. Watchers and registry changes

Consumers often need to know when ephemeral nodes are created or deleted. ZooKeeper supports watches so clients receive notifications when a znode or its child list changes.

For example, a consumer watches the children of:

~~~text
/services/inventory-service
~~~

When a new instance registers, a child node appears. When the owning session expires, the ephemeral node is deleted and the consumer receives a change notification.

ZooKeeper watches are one-time triggers: after an event is delivered, the client typically must register a new watch to keep listening. Abstractions such as Curator Cache or service discovery integrations can manage watch re-registration and data updates automatically.

Do not treat a watch event as a complete replica of registry state. The event signals that a change occurred; consumers should re-read the current list to obtain a fresh snapshot. If connectivity drops while watches are inactive, clients must restore watches and reconcile state.

## 12. Impact on service discovery and in-flight requests

When an ephemeral node is deleted, consumers gradually remove that instance from their discovery list after receiving and processing the update. However, requests already dispatched to the instance before the update may still be in flight or fail because the process has stopped.

Therefore, session mechanisms do not replace resilience policies:

- Configure appropriate connection timeouts and request processing timeouts.
- Bound retries and only retry safe/idempotent operations.
- Use circuit breakers when needed to prevent repeated calls to failing endpoints.
- Refresh discovery caches after watch events or reconnections.
- Never assume an instance is ready solely because its ephemeral node still exists.
- When a session is LOST, avoid claiming to be a registered instance until the node is recreated.

For operations requiring exclusivity such as leader election or distributed locks, session expiration can also create situations where an old process continues running after losing ownership. A fencing token or epoch mechanism is needed to prevent the stale process from writing data after a new owner has been elected. Relying solely on ephemeral nodes for locking without fencing can cause bugs during network partitions or long JVM pauses.

## 13. Security and znode ownership

Ephemeral nodes are bound to a session, but create, read, update, and delete permissions are still enforced by ZooKeeper ACLs. A session does not automatically grant access to arbitrary other clients.

Key points to watch:

- Use an authentication scheme and ACLs suitable for the application.
- Restrict permission to create or delete nodes within a service's registry branch.
- Do not use permissive ACLs such as world:anyone with write access in production.
- Protect session passwords and credentials in logs, dumps, or secret stores.
- Separate namespaces or root paths when multiple applications or deployment teams share an ensemble.
- Monitor session counts, ephemeral node counts, and session expiration events.

If a client loses credentials or fails authentication, reconnection may not restore the session as expected. Distinguish authentication errors from network failures and session expirations during diagnostics.

## 14. Common failure scenarios

| Symptom | Possible cause | Resolution |
|---|---|---|
| Instance remains in registry briefly after process death | Server is waiting for session timeout | Check session timeout and when the node is actually deleted |
| Instance disappears during a long JVM pause | Session expired while the client could not send heartbeats | Tune timeout and investigate GC pauses |
| Socket reconnects successfully, but node is gone | Old session expired; client created a new session or has not re-registered | Handle LOST and recreate the ephemeral node |
| Instance removed on a brief network blip | Timeout too short or interruption exceeded negotiated limit | Check actual negotiated timeout, network latency, and pauses |
| Two registrations for the same service instance | Non-unique instance ID or path, non-idempotent retry | Standardize instance IDs and handle NodeExists |
| Consumer does not update after node deletion | Watch was not re-registered or cache did not refresh | Re-read snapshot and restore watch |
| Instance is running but missing from discovery | New session has not created registration yet or ACL rejected it | Check Curator logs, session state, and ACLs |
| Service is discovered but unreachable | Ephemeral node still present during timeout window after process died | Use request timeouts and consumer resilience |

## 15. Operational principles

- Distinguish TCP connections from ZooKeeper sessions.
- Understand connection timeout and session timeout as two separate mechanisms.
- Choose session timeout based on network latency, JVM pause duration, and tolerance for stale registrations.
- Let Curator manage heartbeats; avoid writing a parallel heartbeat unnecessarily.
- Use ephemeral znodes for registrations tied to instance lifecycle.
- On temporary disconnection, wait for reconnect outcome rather than assuming the session is lost immediately.
- When receiving LOST or session expired, establish a new session and re-register ephemeral nodes.
- Use watches to detect changes, but re-read snapshots to confirm current state.
- Monitor session expirations, reconnects, ephemeral owners, and registration counts.
- Combine discovery with timeouts, retries, circuit breakers, and fencing when business logic requires ownership guarantees.

A session defines the period during which ZooKeeper believes a client is still present. Ephemeral znodes use that session to represent the existence of a service instance in the registry. Temporary disconnections may leave nodes intact if the session remains valid; session expiration deletes the nodes and forces the client to re-register with a new session. Mastering this boundary helps Spring Cloud Zookeeper Discovery reflect instance lifecycles more accurately and recover safely after network disruptions.
