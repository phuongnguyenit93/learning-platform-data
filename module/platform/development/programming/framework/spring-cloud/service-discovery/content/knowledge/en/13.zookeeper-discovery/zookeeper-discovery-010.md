# ZooKeeper Connection State Is Different from Business Health Status

In a system using ZooKeeper for service discovery, a service may maintain its ZooKeeper connection while no longer being able to process business requests. Conversely, an application may continue processing active requests normally while its connection to ZooKeeper is interrupted.

These two states describe different aspects:

- **ZooKeeper connection/session state** indicates whether the client can still communicate with ZooKeeper and whether its registration session remains valid.
- **Business health status** indicates whether the application is ready to accept and process requests, based on the operational state of the application itself and its required dependencies.

If you rely solely on ZooKeeper connection state to decide whether a service is healthy, the registry can retain an instance that can no longer serve requests. If you rely solely on application health, consumers may fail to locate the instance after its ZooKeeper session expires. Track both signals separately and combine them according to your system's readiness policy.

## 1. Distinguishing status signals

An application can have multiple independent status signals:

| Signal | Question answered | Examples |
|---|---|---|
| ZooKeeper connection state | Is the client connected to the ZooKeeper cluster or disconnected? | CONNECTED, SUSPENDED, RECONNECTED, LOST |
| ZooKeeper session state | Is the current session still valid? | Session active or expired |
| Registration state | Is the ephemeral znode representing the instance still in the data tree? | Node exists or was deleted upon session expiration |
| Business health | Are the application and business dependencies functioning? | Database reachable, inventory operations succeeding |
| Liveness | Is the process alive and able to continue running? | JVM not deadlocked, event loop still running |
| Readiness | Should the application accept new requests right now? | Initialization complete, required dependencies ready |

These states are related but not synonymous. For instance, CONNECTED only tells you the client has a connection to ZooKeeper; it does not prove the application's database is working. An existing ephemeral znode tells you the session owning the node has not been evicted by ZooKeeper; it does not prove the HTTP endpoint still returns valid business responses.

In clients such as Apache Curator, common connection states include:

| Curator ConnectionState | Meaning | What to keep in mind |
|---|---|---|
| CONNECTED | Client established initial connection | Not sufficient by itself to conclude the application is ready |
| SUSPENDED | Connection temporarily interrupted | The session may still remain valid within the timeout window |
| RECONNECTED | Client reconnected | Must verify session and registration |
| LOST | Session expired or lost | Ephemeral nodes belonging to the old session were deleted |
| READ_ONLY | Client connected in read-only mode if allowed by configuration | Can read data but cannot register/update nodes |

Exact names and event delivery semantics depend on the client library. Do not assume every ZooKeeper client exposes the same enum or identical self-recovery behavior.

## 2. ZooKeeper sessions and ephemeral znode lifecycle

ZooKeeper maintains a session per client. Clients send heartbeats/pings to keep sessions alive. Session timeout is negotiated between client and server within configured limits. If the client fails to reconnect before timeout, ZooKeeper marks the session expired.

Service discovery commonly uses ephemeral znodes to represent registered instances. An ephemeral znode is created by a session and automatically deleted when that session ends or expires.

A simple flow:

1. The application creates a ZooKeeper client and connects to the ensemble.
2. The client creates an ephemeral znode containing service name, instance ID, host, port, and metadata.
3. Consumers watch or read child nodes to find instances.
4. If the application closes its session gracefully, or if the session expires, ZooKeeper deletes ephemeral znodes belonging to that session.
5. If the application reconnects with a new session, it must re-register its ephemeral znode.

Example data tree:

~~~text
/services
  /inventory-service
    /instances
      /inventory-node-a
      /inventory-node-b
  /payment-service
    /instances
      /payment-node-a
~~~

Each instance node can store information such as:

~~~json
{
  "service": "inventory-service",
  "instanceId": "inventory-node-a",
  "host": "10.20.1.11",
  "port": 8081,
  "version": "v2"
}
~~~

This is registration and routing data. The node's existence only reflects session lifecycle or the client's registration mechanism. If the application experiences a business failure while maintaining its session, the node can remain until the application proactively unregisters or the session expires.

Also distinguish ephemeral nodes from persistent nodes. Persistent nodes are not automatically deleted when a client session ends. Using persistent nodes for registrations without a cleanup mechanism can leave stale nodes behind after processes stop. With ephemeral nodes, losing a session cleans up the registration automatically, but still does not replace business health checks.

## 3. Connection state is not business health

Consider an inventory service with the following components:

- A Spring Boot application receiving HTTP requests.
- ZooKeeper storing registrations so consumers can locate instances.
- A database storing inventory quantities.
- A pricing service supplying product prices.

If ZooKeeper reports CONNECTED while the database fails, the application may still retain its ephemeral znode. Consumers reading the registry still see that instance and may send requests to an API that cannot complete business work.

Conversely, if the database and pricing service are working normally while networking to ZooKeeper is interrupted, the application can still process in-flight requests or requests arriving over existing connections. However, the application cannot reliably update registrations, create new nodes, or receive discovery updates from ZooKeeper.

Diagram illustrating the two independent check flows:

~~~mermaid
flowchart TB
    App["Inventory application"]
    ZKClient["ZooKeeper client"]
    ZK["ZooKeeper ensemble"]
    Registry["Ephemeral registration"]
    Health["Business health / readiness"]
    DB["Inventory database"]
    Pricing["Pricing service"]
    Consumer["Service consumer"]

    App --> ZKClient
    ZKClient -->|"Session and heartbeat"| ZK
    ZKClient -->|"Create / update node"| Registry
    App -->|"Check dependency"| DB
    App -->|"Check dependency"| Pricing
    DB --> Health
    Pricing --> Health
    Health -->|"Application readiness"| App
    Consumer -->|"Read instances"| Registry
    Consumer -->|"HTTP request"| App
~~~

ZooKeeper provides coordination and discovery mechanics. Application health indicators must verify the business conditions required to accept requests. Never use session state to replace those checks.

## 4. Matrix combining session and business health

Four basic scenarios should be handled distinctly:

| ZooKeeper session | Business health | Interpretation | Typical appropriate action |
|---|---|---|---|
| CONNECTED | UP | Discovery connectivity works and application is healthy | Can receive requests if readiness is also UP |
| CONNECTED | DOWN | Registry still knows the instance, but application is unhealthy | Mark unready or remove registration per policy |
| SUSPENDED/LOST | UP | Application may still handle requests, but discovery is uncertain or session was lost | Monitor session, avoid claiming registration is fresh; recover and re-register as needed |
| SUSPENDED/LOST | DOWN | Both discovery and business functionality have problems | Stop accepting new requests; recover each component and re-verify before advertising |

There is an important difference between SUSPENDED and LOST:

- SUSPENDED signals the connection was interrupted. The session may still exist within the timeout window; ephemeral znodes have not necessarily been deleted.
- LOST signals the old session has expired. Ephemeral znodes belonging to the old session have been deleted; the client must establish a new session and restore registrations.

During SUSPENDED, the client cannot be sure whether the server received its latest write. Do not prematurely conclude the node is gone. Once LOST is emitted, the client has a clear signal that the old session can no longer be used.

READ_ONLY also requires separate handling: the application can read registry state but cannot create or update ephemeral registrations. A consumer can keep looking up stale data, whereas a provider cannot guarantee a new registration is written successfully.

## 5. What should business health check?

Business health should reflect the ability to fulfill the work the service promises. Not every dependency needs to be included in readiness; check only dependencies essential for serving incoming requests.

Example for inventory-service:

| Component | Verification question | Can it affect readiness? |
|---|---|---|
| Inventory database | Can it connect and read/write required data? | Yes, if APIs require the database to process requests |
| Pricing service | Is it reachable when requests need price calculation? | Depends on the API and fallback capability |
| Cache | Is it operational? | Depends on whether cache is mandatory or direct database reads are possible |
| ZooKeeper | Can it connect and update discovery? | May affect readiness per deployment policy, but does not replace business health |
| HTTP server | Is it accepting requests and running worker threads/event loop? | Yes |
| Background processor | Is it running if the service depends on it to complete business flows? | Depends on its role |

Separate three kinds of checks:

- **Liveness:** the process is alive and not wedged to the point of needing a restart.
- **Readiness:** the instance can safely accept new requests.
- **Dependency/business health:** components required for business logic are functioning.

For instance, a temporary database disconnect may turn readiness DOWN without necessarily turning liveness DOWN. If liveness also turns DOWN and the orchestrator repeatedly restarts the application, the system can enter a restart loop while the real fault lies in an external database.

Spring Boot Actuator can expose health endpoints and readiness/liveness states. A custom health indicator can verify a business dependency:

~~~java
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;

@Component
public class InventoryDatabaseHealthIndicator implements HealthIndicator {

    private final InventoryRepository repository;

    public InventoryDatabaseHealthIndicator(InventoryRepository repository) {
        this.repository = repository;
    }

    @Override
    public Health health() {
        try {
            repository.ping();
            return Health.up().build();
        } catch (RuntimeException ex) {
            return Health.down()
                    .withDetail("dependency", "inventory-database")
                    .build();
        }
    }
}
~~~

InventoryRepository and ping() are illustrative examples; production implementations must use lightweight checks with timeouts that do not overload the database. Never expose stack traces, connection strings, or secrets on health endpoints.

For the readiness endpoint to aggregate this health indicator, enable probes and include the business contributor in the readiness group using the name exposed by Actuator. Illustrative configuration example:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        readiness:
          include: readinessState,inventoryDatabase
~~~

Contributor names in the group must match actual health component names. If you omit inventoryDatabase from the readiness group, the indicator may appear in aggregate health without affecting the readiness endpoint.

## 6. Combining ZooKeeper sessions with readiness

No single policy fits every service. Readiness decisions must reflect how the application uses ZooKeeper.

### Case where ZooKeeper only serves discovery

If the application can keep processing received requests without ZooKeeper, a temporary disconnection need not make business health DOWN. However, the application may miss registry changes and be unable to register new instances.

A reasonable policy:

- Keep liveness UP.
- Mark discovery connectivity as DEGRADED or UNKNOWN while SUSPENDED.
- Do not claim registration is up to date during disconnection.
- If the session is LOST, wait for a new session and verify registration is restored.
- Determine readiness based on consumers' ability to locate the instance and system requirements.

### Case where requests depend directly on ZooKeeper

If every request must read or write coordination data in ZooKeeper, losing the session may prevent the application from fulfilling business work. In that case, readiness should go DOWN until connectivity and required operations resume.

### Case where ZooKeeper holds locks or resource ownership

If a service uses ephemeral nodes to hold a leader lock, distributed lock, or ownership of a resource, losing the session can mean the application has lost ownership. The application must stop actions requiring that right as soon as session validity becomes uncertain. Never keep writing data merely because the process is alive or local business health still returns UP.

In this case, readiness and business health must reflect current ownership. Upon reconnecting, never assume the old right still holds; rejoin the election or lock-acquisition process according to system rules.

## 7. Tracking connection state with Apache Curator

Curator provides ConnectionStateListener for applications to receive connection events. The following example illustrates separating connection state from business health and flagging registrations for recovery after session loss.

~~~java
import java.util.concurrent.atomic.AtomicBoolean;

import org.apache.curator.framework.CuratorFramework;
import org.apache.curator.framework.state.ConnectionState;
import org.apache.curator.framework.state.ConnectionStateListener;

public class ZooKeeperConnectionMonitor {

    private final AtomicBoolean registrationWritable = new AtomicBoolean(false);
    private final AtomicBoolean sessionLost = new AtomicBoolean(false);
    private final ServiceRegistration registration;

    public ZooKeeperConnectionMonitor(ServiceRegistration registration) {
        this.registration = registration;
    }

    public void attach(CuratorFramework client) {
        client.getConnectionStateListenable().addListener(
                new ConnectionStateListener() {
                    @Override
                    public void stateChanged(
                            CuratorFramework ignored,
                            ConnectionState state) {

                        switch (state) {
                            case CONNECTED:
                                registrationWritable.set(true);
                                break;

                            case SUSPENDED:
                                registrationWritable.set(false);
                                // Session may still be alive within timeout.
                                break;

                            case READ_ONLY:
                                registrationWritable.set(false);
                                // Can read but cannot write registration.
                                break;

                            case LOST:
                                registrationWritable.set(false);
                                sessionLost.set(true);
                                // Ephemeral nodes of the old session were deleted.
                                break;

                            case RECONNECTED:
                                registrationWritable.set(true);
                                if (sessionLost.getAndSet(false)) {
                                    registration.scheduleEnsureRegistered();
                                }
                                break;
                        }
                    }
                });
    }

    public boolean canWriteRegistration() {
        return registrationWritable.get();
    }
}
~~~

ServiceRegistration is an application abstraction, not a built-in Curator class. The scheduleEnsureRegistered() method should offload work to a separate executor; that task performs safe registration when invoked: recreating the ephemeral node under the current session, verifying data, and handling the node-already-exists case. The name canWriteRegistration() clearly expresses ability to write registrations; READ_ONLY is still a connection, yet cannot update nodes.

Notes when using listeners:

- SUSPENDED does not mean the session has expired. Do not delete registrations or manually create a new session solely for this event.
- LOST means the old session was lost; ephemeral nodes belonging to that session are gone.
- After RECONNECTED, verify registration. If the client library or service discovery recipe already recovered automatically, avoid creating duplicate nodes.
- READ_ONLY does not allow registration writes; this state should not be treated as full connectivity for a provider.
- Callbacks must return quickly; do not run long network tasks or block the event thread. Offload recovery work to a dedicated executor.
- Depending on Curator version and configuration, initial state or event sequences may differ. Check documentation for your version.

The example above only manages connection signals and invokes a registration-recovery abstraction. It does not compute business health. Business health indicators still need to check databases, dependent APIs, and actual serving conditions.

## 8. Registering the service only when the instance is ready

A straightforward design is to create the ephemeral registration only after the application has initialized and passed initial readiness checks.

Startup flow:

1. JVM and HTTP server start.
2. Application initializes configuration and dependencies.
3. Business health checks confirm mandatory dependencies are working.
4. Application connects to ZooKeeper and creates the ephemeral registration.
5. Consumers see the instance and can send requests.

If health transitions to DOWN while the session remains CONNECTED, there must be a mechanism to update discovery state. Options include:

- Remove the ephemeral registration when the instance stops serving and recreate it when readiness returns UP.
- Use a separate status node or updated metadata, and require consumers to filter instances by status.
- Use independent health checks at the load balancer/service mesh layer to pull the instance out of traffic.
- Keep the registration while having consumers check a readiness endpoint before sending requests, if supported by the architecture.

Do not just change data in a znode and assume every consumer will automatically filter on that content. Consumers must actively read, watch, and apply the filtering rule. When using Curator Service Discovery or Spring Cloud Zookeeper, inspect how the library registers, updates, and deregisters services before adding manual mechanisms.

In Spring Cloud Zookeeper, DiscoveryClient supplies instance lists to consumers, while ServiceRegistry is the abstraction for registering and deregistering services. These two APIs manage discovery metadata; they do not automatically check databases or business health. If auto-registration is enabled, determine when the library registers during the application lifecycle and how readiness integrates. Avoid letting auto-registration create a node while also creating a second manual registration for the same instance.

When removing an ephemeral node, the operation must be performed by a client/session with appropriate permissions. If the session is LOST, the old node has usually already been deleted by ZooKeeper; the new client simply re-registers once the application is ready.

## 9. Watchers and health checks are two different mechanisms

A ZooKeeper watcher notifies a client that a piece of data has changed. A watcher is not a health check and does not actively invoke the application's HTTP endpoints.

A watcher can report that:

- An instance node was created.
- An instance node was deleted.
- A node's data changed.
- Children of a path changed.

Watchers help consumers update their instance lists. Business health checks evaluate whether the application can actually serve requests.

With traditional watchers, certain watch types fire only once for the next change; clients must re-register the watcher after handling an event. Curator recipes or caches can manage this automatically. Whether using watchers or caches, consumers must still handle disconnections, stale data, and session expiration.

Never infer that an instance is healthy just because watchers report no errors. Watchers do not check databases, call business APIs, or measure request-handling capacity.

## 10. Incident matrix and resolution

| Situation | What is happening | Verification/resolution action |
|---|---|---|
| ZooKeeper CONNECTED, business health DOWN | Session is alive so the ephemeral node may still exist | Check dependencies; mark readiness DOWN and remove/exclude registration per policy |
| ZooKeeper SUSPENDED, business health UP | Temporary disconnection; session may not have expired | Monitor session timeout, do not conclude the node is deleted; apply appropriate readiness policy |
| ZooKeeper LOST, business health UP | Old session expired, ephemeral node deleted | Establish a new session, verify dependencies, then re-register |
| ZooKeeper RECONNECTED, node missing | Application has a new connection, but registration has not recovered yet | Run ensureRegistered workflow and verify node in registry |
| ZooKeeper CONNECTED, consumer sees node but HTTP times out | Registration exists, but address, port, or application has an issue | Check service address, network, and readiness endpoint |
| ZooKeeper READ_ONLY, business health UP | Can read registry, but cannot write nodes | Do not consider provider successfully registered; wait for writable connection |
| Session alive, watcher not updating | Watcher not re-registered or consumer cache stale | Check watcher lifecycle, cache, and event logs |
| Server answers simple probe, client lacks stable quorum | One ZooKeeper node responding does not prove ensemble readiness | Check quorum, leader/follower status, latency, and client sessions |

When the application is healthy while discovery loses connectivity, it may need to continue serving current requests. When the application is unhealthy while its session remains alive, prevent the instance from receiving further traffic. This is why readiness should be computed from serving conditions while connection state is tracked separately.

## 11. Checking ZooKeeper servers and client sessions

Do not confuse ZooKeeper server health with application session state.

- Server processes may be running while the ensemble lacks quorum to accept write operations.
- A client may retain its session while failing over between servers.
- A client may suffer session expiration even while one server still responds to a simple probe.
- A server answering a basic check command does not prove every ephemeral node write will succeed.

Four-letter commands such as ruok typically confirm only that the server process responds to that probe. To assess the ensemble, check quorum status, leader/follower roles, participating node count, latency, and client errors. Administrative commands work only when permitted in ZooKeeper configuration; never broaden the whitelist recklessly in production.

On the application side, observe:

- Current connection state and counts of SUSPENDED/LOST events.
- Session expiration counts and registration recovery duration.
- Expected ephemeral registration count versus actual nodes present.
- Age of discovery data in consumer caches.
- Readiness, liveness, and business dependency health.
- Request failures caused by no instances found or calls routed to unready instances.

Do not monitor only node counts in ZooKeeper. A node may exist yet contain an outdated address, wrong port, or an unhealthy instance.

## 12. Security and reliability

Registrations in ZooKeeper directly govern how consumers route requests. An unauthorized client writing nodes into another service's path can corrupt discovery or impersonate an instance.

Apply the following:

- Use ACLs to restrict read, create, update, and delete permissions per service/path.
- Use client authentication and TLS as required by ensemble security policies.
- Never store tokens, passwords, or personal data in znode metadata.
- Never grant permission to delete the entire service tree to arbitrary clients.
- Inspect owner/session of ephemeral nodes when investigating stale registrations.
- Set timeouts on business health checks and dependency calls.
- Use bounded retries with backoff; avoid tight registration loops when ZooKeeper is disconnected.
- Ensure registration recovery is idempotent and does not create duplicate nodes.
- Monitor readiness and discovery connectivity separately to distinguish root causes.

If an instance loses its session, never keep assuming it still holds a distributed lock or leadership role. For business logic requiring exclusive ownership, use fencing tokens or an equivalent safeguard to prevent an old process from continuing writes after ownership has transferred to another process.

## 13. Hands-on practice workflow

You can practice with inventory-service using these steps:

1. Start the ZooKeeper ensemble and confirm quorum exists.
2. Start two inventory-service instances; each creates an ephemeral node with a unique ID.
3. Inspect instance nodes under /services/inventory-service/instances.
4. Call the business health endpoint and confirm readiness is UP.
5. Stop the test database or a mandatory dependency in the lab environment; observe business health transition to DOWN while the ZooKeeper session may remain CONNECTED.
6. Restore the dependency; confirm readiness returns UP and registration is restored if it was removed.
7. Temporarily cut networking between one client and ZooKeeper; observe SUSPENDED and the wait during session timeout.
8. Let the session expire; confirm the old ephemeral node is deleted.
9. Restore networking; observe LOST then RECONNECTED per client library behavior and confirm the application creates a fresh registration.
10. Send requests through a consumer; verify the consumer stops calling instances removed from the ready list.

Never test quorum loss in production. Network-cut or server-stop experiments must only run in a controlled lab environment.

## 14. Design checklist

Before deploying service discovery with ZooKeeper, confirm:

1. The application distinguishes connection state, session state, and business health.
2. Ephemeral nodes representing registrations have clear owner/session and instance IDs.
3. Readiness reflects dependencies required for business requests.
4. When business health is DOWN, the instance is removed from traffic per an explicit policy.
5. When a session is LOST, the old registration is treated as gone and recreated after connectivity recovers.
6. When SUSPENDED, the system does not jump to the conclusion that the session has expired.
7. Consumers handle stale watchers/caches and do not rely on outdated addresses indefinitely.
8. Liveness is not dragged down merely because a remote dependency temporarily disconnects.
9. Distributed locks or leader ownership enforce fencing/permission checks before writing.
10. ACLs, authentication, TLS, timeouts, retries, and metrics are properly configured.

The core takeaway is: **ZooKeeper connection state indicates whether the client can communicate with the ensemble and maintain a session; business health indicates whether the application can process business work; ephemeral znodes represent session-bound registrations rather than a guarantee that the service is healthy.** Combine these signals to drive readiness and safe routing.
