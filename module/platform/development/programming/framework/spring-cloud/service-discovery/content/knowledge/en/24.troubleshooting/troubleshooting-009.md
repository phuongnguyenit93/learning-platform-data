# ZooKeeper Session Loss, Path Errors, or Access Control Failures

## 1. Incident Scope

Spring Cloud Zookeeper Discovery uses Apache Curator to register and locate services in ZooKeeper. When this integration fails, symptoms usually fall into three groups:

- **Session or connectivity:** client repeatedly reconnects, reports SUSPENDED, LOST, SessionExpired, or cannot maintain ephemeral registrations.
- **Znode paths:** encounters NoNode, NodeExists, wrong chroot, wrong discovery root, or the application looks at the wrong namespace.
- **Authentication and ACLs:** encounters AuthFailed, NoAuth, or Insufficient permission when reading, creating, updating, or deleting znodes.

All three error groups can appear simultaneously. For example, an application reconnects after session expiration, re-creates its registration, yet hits NoAuth because the new credentials lack CREATE permission on the parent path. Identify the first error in the chain rather than treating only the final exception.

This article focuses on diagnosing Spring Cloud Zookeeper in service discovery: checking sessions, verifying paths, reading ACLs, authenticating clients, and recovering registrations.

## 2. Registration Structure and Paths to Know

Spring Cloud Zookeeper Discovery uses Curator Service Discovery to register instance information such as service name, instance ID, host, port, and metadata. The default discovery root is typically `/services`.

Conceptual path layout:

~~~text
/services
  /payment-service
    /payment-instance-a
    /payment-instance-b
  /inventory-service
    /inventory-instance-a
~~~

This is an illustrative layout to explain namespaces. Actual instance names depend on `instance-id`, provider, and version. By default, `spring.cloud.zookeeper.discovery.instance-id` may be generated automatically; if you need to correlate registrations across restarts, inspect the actual ID in configuration and stored data.

Common properties to check:

~~~yaml
spring:
  application:
    name: payment-service
  cloud:
    zookeeper:
      connect-string: zk1.internal:2181,zk2.internal:2181,zk3.internal:2181
      session-timeout: 30000
      connection-timeout: 15000
      discovery:
        enabled: true
        register: true
        root: /services
        instance-id: payment-instance-a
~~~

The timeout values above are only examples illustrating millisecond properties; pick values suited to your version, network, tickTime, and JVM pause times. Do not apply an arbitrary session timeout to every cluster.

ZooKeeper negotiates session timeout with the server. In common setups, the server bounds timeouts based on tickTime; the value requested by the app is not guaranteed to be the final granted value. When investigating session expiration, record the actual negotiated timeout from client logs/metrics rather than only reading YAML.

| Property | Role during diagnostics |
|---|---|
| spring.cloud.zookeeper.connect-string | ZooKeeper client endpoint list, optionally with chroot suffix |
| spring.cloud.zookeeper.session-timeout | Session timeout requested/negotiated with ZooKeeper |
| spring.cloud.zookeeper.connection-timeout | Connection wait timeout |
| spring.cloud.zookeeper.max-retries | Maximum retry count per Spring Cloud Zookeeper config |
| spring.cloud.zookeeper.base-sleep-time-ms | Initial sleep interval between retries |
| spring.cloud.zookeeper.max-sleep-ms | Upper bound on sleep duration between retries |
| spring.cloud.zookeeper.discovery.root | Root path containing registrations; commonly `/services` by default |
| spring.cloud.zookeeper.discovery.register | Enables/disables automatic application registration |
| spring.cloud.zookeeper.discovery.instance-id | ID used to identify the registration |

Properties can vary across release trains. Consult the Common Application Properties for your exact Spring Cloud Zookeeper version before concluding a property was removed or has a specific default.

## 3. Distinguishing Connection Loss from Session Loss

A ZooKeeper client maintains a session with the ensemble. When a TCP connection drops, the client typically transitions to disconnected and attempts to reconnect to servers in the connect string. If connectivity is restored before session timeout, the existing session can continue.

If the ensemble determines the session has expired, that session cannot resume. ZooKeeper deletes ephemeral znodes owned by that session; the client must establish a new session and ephemeral registrations must be recreated according to the application/provider lifecycle.

Key points:

- TCP disconnect does not mean ephemeral znodes are deleted immediately.
- Session expiration is decided by the ZooKeeper ensemble, not solely by a local timeout observed on the client.
- When a session expires, ephemeral znodes are deleted even if the client has not received notification yet because it is still disconnected.
- After reconnecting, the client may receive a session expired notification and must handle it as a new session.
- Do not spin up a brand new ZooKeeper client/session solely upon seeing a disconnect; let Curator manage retries/reconnects and only rebuild registrations when the session is truly LOST/expired.

~~~mermaid
sequenceDiagram
    participant App as Spring Boot / Curator
    participant ZK as ZooKeeper ensemble
    participant Watcher as Another watching client
    App->>ZK: Create session and ephemeral registration
    ZK-->>App: CONNECTED
    Note over App,ZK: Network partitions
    App-xZK: Heartbeat / request
    App-->>App: SUSPENDED
    Note over ZK: Session stays valid within timeout
    alt Reconnects before session expires
        App->>ZK: Reconnect with existing session
        ZK-->>App: RECONNECTED
        Note over ZK: Ephemeral registration still exists
    else Session expired
        ZK->>ZK: Expire session and delete ephemeral znodes
        ZK-->>Watcher: Watch event: registration deleted
        App->>ZK: Reconnect
        ZK-->>App: LOST / session expired reported
        App->>ZK: Create new session and re-register
    end
~~~

## 4. Reading Curator Connection States

Curator provides ConnectionStateListener to track connection state. Common states:

| State | Meaning | Safe action |
|---|---|---|
| CONNECTED | Initial connection established | Can start operations once application is ready |
| SUSPENDED | Temporary loss of connectivity | Pause registry-dependent operations; do not assume locks/registrations remain reliable |
| RECONNECTED | Connectivity restored after interruption | Re-verify data/watches and registration status |
| LOST | Curator considers the session expired | Treat old session as invalid; recreate ephemeral registrations and restore required watches |
| READ_ONLY | Client is in read-only mode if allowed by config | Do not perform register, update, or deregister writes |

In Curator, SUSPENDED should be treated as a full disconnect for safety-critical decisions such as locks, leadership, or registrations requiring uniqueness guarantees. RECONNECTED merely indicates connectivity returned; it does not prove all application state is consistent. LOST signals the need to rebuild the session and session-bound resources.

Curator listener example:

~~~java
import org.apache.curator.framework.CuratorFramework;
import org.apache.curator.framework.state.ConnectionState;
import org.apache.curator.framework.state.ConnectionStateListener;

public class ZookeeperConnectionListener
        implements ConnectionStateListener {

    @Override
    public void stateChanged(
            CuratorFramework client,
            ConnectionState newState) {
        switch (newState) {
            case CONNECTED:
                // Initial connection is ready.
                break;
            case SUSPENDED:
                // Pause operations requiring a reliable registry.
                break;
            case RECONNECTED:
                // Reconcile registrations and cached data.
                break;
            case LOST:
                // Old session is lost; rebuild ephemeral registration.
                break;
            case READ_ONLY:
                // Read-only; do not treat writes as succeeded.
                break;
            default:
                break;
        }
    }
}
~~~

Supported enum names and states depend on the Curator version. Use the Curator API managed by Spring Cloud Zookeeper; do not force an incompatible Curator version just for newer enums.

## 5. Common Session Errors

| Error or symptom | Possible cause | How to handle |
|---|---|---|
| Repeated SUSPENDED | Flaky network, firewall idle timeouts, JVM pauses, or overloaded ZooKeeper server | Check latency, packet loss, GC pauses, server logs, and bidirectional TCP paths |
| SessionExpiredException / SESSIONEXPIRED | Session timeout elapsed before client reconnected | Treat as a new session; re-register ephemeral nodes and re-establish watches |
| ConnectionLossException | Connection dropped mid-operation | Operation outcome is uncertain; read state before retrying create/delete |
| OperationTimeoutException | Retry policy or operation exceeded timeout | Check timeouts, retry budget, latency, and quorum |
| Registration disappears after brief network loss | Session expired so ephemeral node was deleted | Confirm LOST, establish new session, and re-register |
| Old registration remains after app stopped | Session not yet expired, deregister failed to reach server, or node is non-ephemeral | Check stat, owner/session, ACLs, and znode type |
| Reconnect succeeds yet discovery misses instance | Registration not recreated, wrong root/instance ID, or stale client cache | Check znode on server and discovery config |

### 5.1. Do Not Blindly Retry `create`

ConnectionLoss can happen after the server already processed the request while the response never reached the client. If the application immediately retries create, the second attempt can receive NodeExists. That is not necessarily a data error; the first call may have succeeded.

For registrations:

1. Determine the expected path and instance ID.
2. After an ambiguous error, read the path back if the client can query.
3. If the node already exists, inspect data, ephemeral owner, and metadata to confirm it belongs to the expected registration.
4. Only recreate when the node does not exist or the old session expired and lifecycle requires a fresh registration.
5. Never delete a node merely upon seeing NodeExists; it might belong to another instance.

## 6. Diagnosing Path Errors: NoNode, NodeExists, and Chroot

ZooKeeper uses absolute paths separated by `/`. Paths must start with `/`; ZooKeeper does not support relative paths like `.` or `..`.

Common errors:

| Error | Meaning | Common cause |
|---|---|---|
| NoNode | A znode in the path does not exist | Parent path not created, wrong discovery root, or wrong chroot |
| NodeExists | Path already exists | Retrying create after ConnectionLoss, duplicate instance ID, or stale registration not cleaned up |
| BadVersion | Znode version mismatch on conditional update | Client wrote based on stale data or another writer intervened |
| InvalidPath | Invalid path syntax | Relative path, forbidden characters, or bad format |
| NotEmpty | Cannot delete a node that still has children | Delete children before deleting the parent |

### 6.1. Checking the Discovery Root

Spring Cloud Zookeeper Discovery defaults to root `/services` in common configurations. A custom root can be set:

~~~yaml
spring:
  cloud:
    zookeeper:
      discovery:
        root: /platform/services
~~~

If one service registers under `/platform/services` while another client reads `/services`, both sides use different namespaces and will not see each other even while connected to the same ensemble.

Ensure every service needing to communicate shares the same discovery root and service ID naming conventions. Check profiles, environment variables, and config imports since configuration can be overridden per environment.

### 6.2. Chroot Suffix in the Connect String

The connect string may include a chroot suffix:

~~~yaml
spring:
  cloud:
    zookeeper:
      connect-string: zk1.internal:2181,zk2.internal:2181,zk3.internal:2181/platform
      discovery:
        root: /services
~~~

With this setting, the client treats `/platform` on the server as its own `/` root. When the application accesses `/services`, the physical path on the ensemble is `/platform/services`.

If chroot `/platform` does not exist yet, connections or path operations can fail. Create this namespace before starting clients. If chroot is already used, do not also prepend `/platform` to `discovery.root`; otherwise, the client may accidentally access `/platform/platform/services`.

Chroot is a logical namespace, not a replacement for ACLs. Access permissions must still be configured on each znode on the server side.

### 6.3. Inspecting Paths with the CLI

Connect to the ZooKeeper server without chroot to observe physical paths:

~~~bash
bin/zkCli.sh -server zk1.internal:2181
~~~

Read the paths:

~~~text
ls /
ls /platform
ls /platform/services
ls /platform/services/payment-service
~~~

If the application does not use chroot, inspect `/services` and its corresponding children. If chroot is used, inspect both the physical path from a non-chrooted CLI and the logical path seen by the application.

## 7. Distinguishing Authentication from Authorization Errors

ZooKeeper has two distinct layers:

- **Authentication:** client proves its identity via schemes such as digest, sasl, x509, or custom schemes.
- **Authorization:** ACLs on each znode determine which operations an authenticated identity is allowed to perform.

Therefore:

- AuthFailed typically indicates authentication failed, credentials or scheme are wrong, or the server does not accept that authentication mechanism.
- NoAuth / Insufficient permission typically indicates the client connected, yet its identity lacks the required permissions on the znode.

Adding credentials to Curator does not automatically grant permissions on znodes. Conversely, creating an ACL for a digest identity will not help a client if that client does not send matching authentication info.

### 7.1. ACL Permissions

| Permission | Capability |
|---|---|
| CREATE | Create children beneath the current znode |
| READ | Read data and list children of the current znode |
| WRITE | Write data of the current znode |
| DELETE | Delete children beneath the current znode |
| ADMIN | Read/set ACLs per ZooKeeper permission rules |

An easily missed detail: CREATE and DELETE are checked on the **parent** of the node being created/deleted. For example:

- Create `/services/payment-service`: requires CREATE on `/services`.
- Create `/services/payment-service/instance-a`: requires CREATE on `/services/payment-service`.
- Delete `instance-a`: requires DELETE on `/services/payment-service`.
- List instances under `/services/payment-service`: requires READ on `/services/payment-service`.
- Read instance metadata: requires READ on the instance znode itself.
- Update instance data: requires WRITE on the instance znode itself.

A znode's ACL **does not automatically inherit** down to children. Having rights on `/services` does not mean a client can read or write every znode beneath it. Permissions must be verified at every path level an operation traverses.

### 7.2. Common Authentication Schemes

| Scheme | Identifier | Notes |
|---|---|---|
| world | anyone | Usually for public data; avoid granting full permissions on the registry |
| auth | Any authenticated identity | Convenient ACL for creator/authenticated identity; must authenticate before creating |
| digest | Username/password | Credentials must be sent over protected connections; never put passwords in source/logs |
| sasl | SASL/Kerberos or configured mechanism | Requires synchronized principals, keytabs, and server/client config |
| x509 | X.509 principal over TLS | Certificates and trust chains must be valid |
| ip | Client IP address | Sensitive to NAT, proxies, and IP changes |

Never use `world:anyone` with `cdrwa` permissions for a production registry. Such an open ACL allows any client to read, write, create children, delete children, and alter ACLs.

## 8. Reading and Verifying ACLs

Connect the CLI to the server using an account with permission to read ACLs:

~~~bash
bin/zkCli.sh -server zk1.internal:2181
~~~

If using digest, authenticate in the CLI:

~~~text
addauth digest service-reader:REDACTED
~~~

Never place real passwords in shell history, tickets, logs, or documentation. Use environment secrets and enter credentials only in secured admin sessions.

Read ACLs at each level:

~~~text
getAcl /services
getAcl /services/payment-service
getAcl /services/payment-service/instance-a
~~~

If `getAcl` also reports NoAuth, the current account lacks appropriate READ or ADMIN rights on that node. Use an appropriately authorized admin identity; never widen ACLs merely for quick reading.

Verify identity and permissions for each operation:

1. Does the client authenticate with the right scheme?
2. Does the parent allow CREATE to create service/instance children?
3. Does the service parent allow READ so discovery can list children?
4. Does the instance node allow READ so clients can read metadata?
5. Does the instance node allow WRITE if providers need to update data?
6. Does the parent allow DELETE to deregister children?
7. Does the node allow ADMIN if the app needs to alter ACLs?

## 9. Configuring Authentication for Spring Cloud Zookeeper

Spring Cloud Zookeeper uses CuratorFramework. Spring Cloud documentation describes adding authentication info via `addAuthInfo` on the CuratorFramework bean during bootstrap. Actual setup must follow the auto-configuration and bootstrap mechanism of the release train in use.

Illustrative example showing digest authentication:

~~~java
import java.nio.charset.StandardCharsets;

import org.apache.curator.RetryPolicy;
import org.apache.curator.framework.CuratorFramework;
import org.apache.curator.framework.CuratorFrameworkFactory;
import org.apache.curator.retry.ExponentialBackoffRetry;

public final class CuratorAuthExample {
    public static CuratorFramework createClient(
            String connectString,
            String credential) {
        if (credential == null || credential.trim().isEmpty()) {
            throw new IllegalArgumentException("Digest credential is required");
        }
        RetryPolicy retryPolicy = new ExponentialBackoffRetry(1000, 3);
        CuratorFramework client = CuratorFrameworkFactory.builder()
                .connectString(connectString)
                .sessionTimeoutMs(30000)
                .connectionTimeoutMs(15000)
                .authorization(
                        "digest",
                        credential.getBytes(StandardCharsets.UTF_8))
                .retryPolicy(retryPolicy)
                .build();
        client.start();
        return client;
    }
}
~~~

This example builds a Curator client with authorization configured directly on the builder so authentication info persists across reconnects. In a Spring Cloud Zookeeper application, attach authorization to the CuratorFramework bean actually used by discovery/config. Do not spin up an extra standalone client while auto-configuration still uses an unauthenticated client. Some release trains require a custom CuratorFramework bean or BootstrapConfiguration; follow the documentation for your exact version.

If creating a CuratorFramework bean manually, preserve critical defaults provided by Spring Cloud auto-configuration such as connect string, timeouts, retry policy, namespace, and lifecycle. Avoid inadvertently creating a second client and leaving discovery on the unauthenticated one.

Credentials should come from a secret manager or secret mount, never hardcoded. With digest, ZooKeeper authenticates using the scheme's digest mechanism; TLS should still be configured to protect credentials in transit.

## 10. Parent and Child ACLs During Service Registration

To register successfully, an application usually traverses multiple path levels. For example:

~~~text
/services
/services/payment-service
/services/payment-service/payment-instance-a
~~~

Minimum permissions depend precisely on how the provider creates paths and updates registrations:

| Path | Operations | Permissions to consider |
|---|---|---|
| `/services` | Create service name child; list services | CREATE, READ |
| `/services/payment-service` | Create/delete instance children; list instances | CREATE, DELETE, READ |
| `/services/payment-service/payment-instance-a` | Read metadata; update data; read ACL if needed | READ, WRITE, or ADMIN depending on operation |

This table is a permission analysis checklist, not a fixed ACL policy. Curator Service Discovery may create parent paths, create ephemeral nodes, and update metadata depending on version. Verify actual operations in logs or provider docs before granting least-privilege permissions.

ACLs are non-recursive, so you must create or update ACLs for parents and children appropriately. When changing policies, plan migration for existing znodes; updating a parent ACL does not automatically alter ACLs of pre-existing children.

## 11. ACL Errors and How to Fix Them

| Symptom | Possible cause | Remediation direction |
|---|---|---|
| AuthFailed immediately on connect | Wrong credentials, wrong scheme, or SASL/TLS mismatch | Check auth scheme, secret, principal, certificate, and server config |
| NoAuth on `ls /services` | Missing READ on `/services` or accessed namespace | Check identity and ACL on the exact path |
| NoAuth when creating instance | Missing CREATE on parent service znode | Check parent ACL, not just instance ACL |
| NoAuth when deregistering | Missing DELETE on parent | Check child deletion permission on service parent |
| NoAuth when updating metadata | Missing WRITE on instance znode | Check instance node ACL |
| NoAuth on `getAcl` | Missing appropriate READ or ADMIN | Use an authorized admin account |
| Client has credentials yet still denied | Credentials added after operation ran or discovery uses a different Curator client | Check bootstrap order and actual Curator bean |
| Some services register, others fail | Different ACLs on parent/child or legacy paths | Compare ACLs across each service branch |

## 12. Ordered Diagnostic Runbook

When a service fails to register or DiscoveryClient cannot find instances, follow this sequence:

### Step 1: Identify Provider and Effective Configuration

- Confirm whether the app uses Spring Cloud Zookeeper Discovery or only ZooKeeper Config.
- Check starter dependencies, active profiles, and final overridden configuration.
- Record connect-string, session timeout, connection timeout, discovery root, chroot, and instance ID.
- Confirm all instances in the same namespace share a single discovery root.

### Step 2: Check Connectivity and Session

- Test DNS and TCP to the client port of every server in the connect string.
- Read Curator logs for SUSPENDED, RECONNECTED, LOST, ConnectionLoss, and SessionExpired.
- Check that the ZooKeeper ensemble has a leader/quorum and the client port is serving.
- Correlate network drop timestamps with session timeout and JVM/GC pauses.
- Do not create a new session/client merely upon seeing SUSPENDED; let Curator handle reconnects.

### Step 3: Check Paths

- Use a non-chrooted CLI to inspect physical paths.
- Inspect `/services` or your custom discovery root.
- If the connect string uses chroot, map logical paths to physical paths.
- Confirm parent paths exist and match the right service ID/instance ID.
- If NodeExists occurs, read the node and check owner/data before deciding to delete or recreate.

### Step 4: Check Authentication and ACLs

- Confirm the client sends the right auth scheme and credentials.
- Read ACLs at root, service parent, and instance node.
- Verify CREATE/DELETE on parents, READ/WRITE on nodes.
- Inspect child ACLs because ACLs do not inherit automatically.
- Verify credentials are configured before Spring Cloud Discovery uses Curator.

### Step 5: Recover and Verify

- If the session was LOST, verify a new session and ephemeral registration were recreated.
- If the path was wrong, fix the discovery root/chroot and align across services.
- If ACLs were wrong, grant least-privilege permissions at the right path levels.
- Confirm DiscoveryClient returns the expected service ID and instances.
- Monitor logs and registry over an observation window to ensure the error does not recur.

~~~mermaid
flowchart TD
    A[Service registration missing] --> B{Curator connection state?}
    B -->|SUSPENDED / ConnectionLoss| C[Check network, server, and timeouts]
    B -->|LOST / SessionExpired| D[Rebuild session and ephemeral registration]
    B -->|CONNECTED / RECONNECTED| E[Check path and namespace]
    E -->|NoNode / NodeExists| F[Cross-check root, chroot, parent, and instance ID]
    E -->|Path valid| G[Check authentication and ACLs]
    G -->|AuthFailed / NoAuth| H[Check scheme, credentials, and parent/child permissions]
    G -->|Permissions valid| I[Check registration provider and DiscoveryClient]
    C --> J[Re-verify session and path]
    D --> J
    F --> J
    H --> J
    I --> K[Confirm service instance appears and is queryable]
~~~

## 13. Recovering After Session Expiration

When Curator reports LOST or ZooKeeper reports session expired:

1. Mark the old registration/session as no longer reliable.
2. Do not attempt to reuse the old ephemeral owner or session ID.
3. Let Curator establish a new connection/session per framework lifecycle.
4. Check whether Spring Cloud Zookeeper/Curator Service Discovery recreates the service registration.
5. If the application manages registrations manually, re-register using a stable instance ID/path per application policy.
6. Re-establish watches or caches tied to the old session.
7. Verify the new instance has an ephemeral owner belonging to the new session and is visible to DiscoveryClient.

Do not assume every version/provider re-registers identically. Spring Cloud Zookeeper manages discovery through Curator Service Discovery, yet exact recovery behavior depends on version and how the application customizes Curator. If you replaced CuratorFramework or built custom registrations, test session-loss scenarios in integration tests.

If the application runs multiple replicas, each replica must have a unique instance ID. Sharing the same ID across two processes can cause NodeExists, overwrites, or registration contention depending on how the provider creates nodes.

## 14. Safely Fixing Paths and ACLs

When encountering NoNode:

- Confirm chroot exists on the server side.
- Confirm discovery root is accurate and parent paths are created before registering children.
- Check whether the service name was altered by profiles or environment settings.
- Create missing parent paths only after verifying the target namespace.

When encountering NodeExists:

- Read the node's stat and data.
- Check ephemeral owner to see whether the node belongs to the current session.
- Compare instance ID and metadata.
- Do not delete the node without identifying its owner or if it still belongs to a running process.

When encountering NoAuth:

- Do not switch the entire registry to `OPEN_ACL_UNSAFE`.
- Identify the missing operation permission and exact path.
- Grant least-privilege permissions on the required parent and child nodes.
- Test register, list, read, update, and deregister using the exact service identity.

Changing ACLs requires an appropriate ADMIN account. Before editing in production, record existing ACLs, check active clients, and prepare a rollback plan. Changing a parent ACL does not propagate down to existing children.

## 15. Preventive Testing

Maintain integration tests with a ZooKeeper test container or test ensemble covering:

- Normal connection and service registration.
- Network interruption shorter than session timeout followed by reconnect; session and ephemeral node persist.
- Network interruption long enough to expire the session; old registration is removed and the app recreates registration as designed.
- Wrong chroot or discovery root; application surfaces diagnosable path errors.
- Missing parent path; bootstrap creates the intended namespace.
- Wrong credentials; client receives clear authentication errors.
- Missing CREATE, READ, WRITE, or DELETE at the right level; tests verify the corresponding operation fails.
- Valid ACLs; registration, discovery, and deregistration all succeed.
- Multiple replicas with distinct instance IDs; no registration conflicts.

Unit tests can mock Curator or ServiceRegistry to verify error-handling logic. However, only integration tests verify real ZooKeeper session expiration, ephemeral znode, ACL, and path semantics.

## 16. Design Mistakes to Avoid

- Creating a new ZooKeeper client on every SUSPENDED event, unnecessarily multiplying sessions and connections.
- Treating RECONNECTED as proof that registrations still exist.
- Deleting a znode upon seeing NodeExists without checking ephemeral owner.
- Confusing the logical post-chroot path with the physical path on the server.
- Granting `world:anyone` full permissions as a quick fix for NoAuth.
- Updating parent ACLs while forgetting child znodes.
- Adding credentials after DiscoveryClient has already started registering.
- Using identical instance IDs across multiple replicas.
- Retrying indefinitely on NoAuth or NoNode; these are configuration/permission/path errors needing fixes, not transient network glitches.
- Putting digest passwords into source code, logs, or shell history.

## 17. References

- [Apache ZooKeeper Programmer's Guide — Sessions, Watches, ACLs, and Error Handling](https://zookeeper.apache.org/doc/current/zookeeperProgrammers.html)
- [Apache ZooKeeper Administrator's Guide](https://zookeeper.apache.org/doc/current/zookeeperAdmin.html)
- [Apache Curator — Error Handling and ConnectionStateListener](https://curator.apache.org/docs/errors/)
- [Apache Curator — Tech Note 12: Connection Semantics](https://curator.apache.org/docs/tech-note-12/)
- [Apache Curator — Tech Note 14: Session Expiration](https://curator.apache.org/docs/tech-note-14/)
- [Spring Cloud Zookeeper — Service Discovery](https://docs.spring.io/spring-cloud-zookeeper/reference/discovery.html)
- [Spring Cloud Zookeeper — Common Application Properties](https://docs.spring.io/spring-cloud-zookeeper/reference/appendix.html)
- [Spring Cloud Zookeeper — Access Control Lists](https://docs.spring.io/spring-cloud-zookeeper/reference/config.html)

Select documentation matching your application's ZooKeeper, Curator, Spring Boot, and Spring Cloud release train versions.

## 18. Summary

When ZooKeeper fails in Spring Cloud Discovery, separate three layers: session/connectivity, path/chroot, and authentication/ACLs. Losing TCP only puts the client into an interrupted state; ephemeral registrations are deleted only when the session expires. Curator uses SUSPENDED, RECONNECTED, and LOST to signal state, where LOST requires rebuilding the session and registrations.

NoNode usually points to parent paths, discovery root, or chroot; NodeExists calls for checking prior operation outcomes and ownership; NoAuth calls for verifying permissions on both the exact znode and its parent; AuthFailed points to credentials/schemes. ACLs do not inherit down to children, so verify permissions at every path level. After recovery, verify actual registrations, DiscoveryClient results, and deregistration rather than relying solely on Curator having reconnected.
