# Restricting Network Access and Protecting Redis from the Public Internet

**Redis should never be exposed directly to the public Internet.** In a Spring Data Redis application, Redis may hold caches, login sessions, temporary tokens, rate-limit counters, queues, business state, and data shared across multiple services. An exposed Redis port not only puts data at risk of unauthorized reading, but also creates opportunities for data modification/deletion or system disruption if protective layers are insufficient.

Securing Redis must start at the **network boundary**: only authorized applications, workers, and administrative tools should have a network path to Redis. Only then come **TLS to protect traffic in transit**, **Redis ACLs to restrict identities and commands**, **secret management**, and **access monitoring/testing**.

In the **Spring Data Redis** ecosystem, configuring connections with `LettuceConnectionFactory`, `RedisTemplate`, or `ReactiveRedisTemplate` is only the client layer. You cannot make Redis secure with a Java annotation if the infrastructure still exposes the Redis port to every IP address.

The goal of this lesson is to design a multi-layered protection model, recognize common deployment mistakes, and establish a concrete verification process before going live.

## 1. Why Does Redis Carry High Risk When Exposed to the Internet?

Redis is a high-performance data store typically accessed directly by applications over the Redis protocol. Redis is not an HTTP application gateway with built-in end-user access controls designed for every business workflow.

If a Redis endpoint is exposed to the public network, the consequences can include:

- Reading keys containing cached data, sessions, or internal information if access is not restricted.
- Overwriting or deleting data, corrupting caches, sessions, and state used by the application.
- Causing CPU, RAM, network, or connection count exhaustion leading to denial of service.
- Executing dangerous administrative commands if the account is granted overly broad permissions.
- Exploiting misconfigurations in authentication, ACLs, TLS, replication, or modules.
- Using compromised data access to affect other services that depend on Redis.

This still matters even if Redis is "just for caching." A cache that is not a source of truth can still be poisoned with false values, causing the application to serve forged data or pushing all traffic back to the database when mass-evicted.

**Do not expose a Redis port to the Internet just because a password is set.** A password helps identify the client, but it does not replace firewalls, network segmentation, TLS, and least privilege.

## 2. Multi-Layered Defense Architecture

A proper deployment should include at least the following boundaries:

```text
                   Public Internet
                           |
                           v
                    Load Balancer/WAF
                           |
                      HTTPS (443)
                           |
                           v
                  Spring Boot API tier
                           |
                   Private networking
                           |
                  Allowed sources only
                           |
                           v
                 Firewall/Security Group
                           |
                       TLS + ACL
                           |
                           v
                    Private Redis
                           |
                      Replica(s)
                 (internal network only)
```

In this model:

1. Browsers can only reach the HTTP/API gateway according to policy.
2. Redis has no public address or endpoint routed directly from the Internet.
3. Firewalls allow only designated applications to reach the Redis port.
4. Redis authenticates clients and restricts keys and commands by role.
5. TLS secures data and credentials while in transit across the network.
6. Redis primary/replica, Sentinel, or Cluster nodes use separate internal channels with only the necessary permissions.
7. The system collects logs/metrics to detect anomalous access and misconfigurations.

A well-protected system should withstand **the failure of a single layer** without immediately exposing data. For example, if a firewall rule is configured too broadly, ACLs and TLS still act as additional layers of defense; however, they must never be used as an excuse to leave a broken firewall rule in place.

## 3. Distinguishing Security Layers

| Layer | Question Answered | Cannot Replace |
|---|---|---|
| **Private Network/VPC** | Does the client have a network path to Redis? | Does not authenticate commands or users |
| **Firewall/Security Group** | Which sources can connect to which ports? | Does not inspect the contents of Redis operations |
| **Redis bind** | Which interfaces does Redis listen on? | Does not create per-client policies on its own |
| **Protected mode** | Helps block some unsafe Redis configurations | Does not replace firewalls, ACLs, or TLS |
| **TLS** | Is traffic encrypted and the server verified? | Does not authorize Redis commands on its own |
| **Redis ACL** | Which keys and commands can a user access? | Does not prevent endpoint scanning/DoS at the network layer |
| **Spring Security** | Which HTTP users can call an API? | Does not replace Redis ACLs and network boundaries |
| **Secret management** | How are passwords/certificates stored, issued, and rotated? | Cannot fix a publicly exposed Redis port |
| **Monitoring/Audit** | Are there signs of unauthorized access or abnormal changes? | Does not prevent incidents if only observing |

Protective layers should be designed independently yet consistently. Just because a user is allowed to call `GET /products/42` on the API does not mean that client is allowed to connect directly to Redis.

## 4. Threat Modeling Before Writing Configuration

Before deciding on firewalls and ACLs, identify the client groups:

- Spring Boot API instances.
- Background workers or scheduled jobs.
- Higher-privileged migration/maintenance tools.
- Monitoring/health-check components.
- Redis primary and replicas.
- Sentinel or Cluster nodes.
- Administrators accessing through approved procedures.
- Systems that **must not** connect, including Internet users, unrelated containers, and other test environments.

Example matrix:

| Source | Redis data port | Commands/keys needed | Policy |
|---|---|---|---|
| Catalog API private subnet | Allow | GET/SET/DEL in `cache:catalog:*` | Restricted ACL user |
| Order worker private subnet | Allow | A different set of commands/namespaces | Separate ACL user |
| Public CI runner | Deny by default | No access to production | Use a separate test environment |
| Bastion/admin host | Only via approved session/procedure | Audited operations | Privileges separated from application |
| Internet `0.0.0.0/0` and `::/0` | Deny | None | No direct route to Redis |
| Redis replica/Cluster node | Allow within internal network | Replication/cluster protocols | Restricted to known nodes |

**Allowlists must come from infrastructure roles and identities**, not an overly broad IP range chosen just for "convenient connectivity."

## 5. Rule Number One: Place Redis in a Private Network

For cloud infrastructure, Redis should reside in:

- A private subnet/VPC or equivalent private network.
- A private endpoint provided by a managed Redis service.
- An internal Kubernetes Service, not a public LoadBalancer.
- A dedicated Docker network for the relevant application, without publishing ports to a public host.
- An on-premises network with a firewall between the application tier and the data tier.

```text
Wrong:
Browser/Internet ---- TCP 6379 ----> Redis public IP

Better:
Browser/Internet ---- HTTPS 443 ----> API
                                      |
                                 Private route
                                      |
                                      v
                                Redis private IP
```

Applications running in another network zone need controlled private connectivity, such as VPN/site-to-site, VPC peering, private networking, or a suitable private endpoint mechanism. Do not use opening Redis to the Internet as the default solution for connecting two environments.

### 5.1. A Private IP Is Necessary, Not Sufficient

Having an RFC 1918 address for Redis does not guarantee that it is protected:

- A VPN or network peering setup might connect too many networks.
- A subnet might host multiple untrusted workloads.
- A reverse proxy/tunnel or port-forward might accidentally expose Redis externally.
- A Docker/Kubernetes ingress or Service might publish traffic to Redis.
- A compromised container in the same network might attempt to connect to Redis.

Therefore, beyond a private IP, you also need **source-based firewall allowlists** and Redis ACLs.

### 5.2. Check Both IPv4 and IPv6

A firewall that blocks `0.0.0.0/0` while leaving `::/0` open can still leave the endpoint exposed over IPv6. Redis can listen on IPv4, IPv6, or both depending on its bind configuration and operating system.

When auditing:

- Check public IPv4 and public IPv6 addresses.
- Check IPv6 inbound rules.
- Check dual-stack Kubernetes/Load Balancer configurations if applicable.
- Do not assume that a port unreachable via IPv4 is definitely unreachable from the Internet.

## 6. Firewalls and Security Groups: Open Only Strictly Necessary Sources

Suppose the API runs in a private subnet and Redis listens on port 6379. The policy should look like:

```text
Destination: Redis private endpoint
Protocol: TCP
Destination port: 6379
Allowed source: API security group / workload identity
Everything else: deny
```

On clouds that support security group references, it is usually better to allow the **application's source security group** rather than a broad CIDR range like the entire VPC. This tracks workload membership closely as instances scale up and down.

Example logical policy:

| Rule | Source | Destination | Port | Action |
|---|---|---|---:|---|
| Inbound Redis | Catalog API group | Redis endpoint | TCP 6379 | Allow |
| Inbound Redis | Order worker group | Redis endpoint | TCP 6379 | Allow if needed |
| Inbound Redis | Controlled admin/bastion | Redis endpoint | TCP 6379 | Allow per procedure |
| Inbound Redis | Internet and other networks | Redis endpoint | TCP 6379 | Deny |
| HTTP public | Internet | API load balancer | TCP 443 | Allow per WAF/API policy |

For stateful firewalls, return traffic for an allowed connection is usually handled by connection state. For stateless Network ACLs, you must account for both inbound/outbound directions and ephemeral ports. Do not simply copy security group rules to another firewall type while ignoring statefulness.

### 6.1. Open Only the Ports Actually Used

The default Redis port is typically `6379`, though managed Redis services, TLS endpoints, or custom deployments may use different ports. Do not assume every TLS-enabled Redis uses `6380`; always verify the actual environment's endpoint.

Related ports in a larger architecture:

| Component | Common Port | Principle |
|---|---:|---|
| Redis data service | 6379 default | Only authorized applications/workers |
| Redis TLS data service | Determined by config | Private network only; requires real TLS |
| Redis Sentinel | 26379 default | Only authorized Sentinel clients/Redis nodes |
| Redis Cluster bus | Typically data port + 10000 | Only between Cluster nodes |
| Redis admin/metrics sidecars | Deployment-specific | Never publish publicly; require auth and authorization |

**Never expose Cluster bus ports or Sentinel ports to the Internet.** These protocols exist for infrastructure coordination, not for browsers or untrusted clients.

## 7. Redis bind and protected-mode: Understand Their Actual Scope

In Redis server configuration, two common settings are:

- `bind`: selects the addresses/interfaces Redis listens on.
- `protected-mode yes`: adds a safeguard against certain unsafe configurations.

Example of Redis used only on a single machine for development:

```conf
bind 127.0.0.1 -::1
protected-mode yes
port 6379
```

When binding only to loopback, clients on other machines cannot connect directly via the host's private or public IP.

If Redis serves applications from other machines, bind to the **appropriate private interface**, while also using firewalls, ACLs, and TLS:

```conf
# Example host with an actual private IP assigned to the machine.
bind 10.20.30.15
protected-mode yes
port 6379
```

The address `10.20.30.15` is illustrative only and must be replaced with a real address on the host. Furthermore, **this configuration only addresses the interface; it does not yet enable TLS or ACLs**. For production use, the protective layers in the following sections are required.

### 7.1. Why 0.0.0.0 Requires Caution

```conf
bind 0.0.0.0
```

means Redis listens on all relevant IPv4 interfaces in its network namespace. If the host/container has an Internet-reachable interface and the firewall is open, the port can be exposed.

In Kubernetes, a Redis pod sometimes has to bind `0.0.0.0` **inside the pod** so that a Service and other pods can reach it. In that case, protection must come from **ClusterIP/private networking, NetworkPolicy, firewalls, and Redis ACLs/TLS**. Do not treat `0.0.0.0` inside a container as always equivalent to public exposure, nor assume it is safe just because it runs in a container.

### 7.2. Protected Mode Is Not a Firewall

Redis protected mode can block certain remote connections when the server lacks proper protective configuration, but its exact behavior depends on the Redis version and actual bind/auth settings. Never use `protected-mode yes` as an excuse to:

- Open inbound `6379` to all IP addresses.
- Skip Redis ACLs/passwords.
- Skip TLS.
- Consider a Redis instance listening on a public interface safe.
- Disable all NetworkPolicies and security groups.

**Restricting the network path is the first line of defense; protected mode is only an extra safeguard.**

## 8. TLS: Protecting Data and Credentials in Transit

If Redis passwords or ACL credentials are sent over an unencrypted connection, they can be exposed to anyone able to observe traffic. Redis may store sensitive data such as session IDs or tokens, so the path between the app and Redis must be protected according to your threat model.

**TLS** encrypts data in transit and, when properly configured, allows the client to verify the server via its certificate chain and hostname.

```text
Spring Boot / Lettuce
      |
      | TLS handshake + server certificate validation
      |
      v
Redis TLS endpoint (private network)
      |
      v
Redis ACL/commands
```

TLS **does not replace ACLs**, because a client that successfully completes TLS authentication still needs to be restricted in which commands and keys it can use.

### 8.1. Redis TLS-Only Example

Example Redis server configuration:

```conf
# Do not listen on a plain TCP data port.
port 0

# Explicit TLS port configured.
tls-port 6379

tls-cert-file /etc/redis/tls/server.crt
tls-key-file /etc/redis/tls/server.key
tls-ca-cert-file /etc/redis/tls/ca.crt

# This example only requires the client to verify the server;
# Redis ACLs still authenticate the application user.
tls-auth-clients no

protected-mode yes
```

This is an illustrative server-side snippet, not a complete deployment configuration. You also need to:

- Bind the appropriate interface or restrict sources via firewall.
- Issue certificates with SANs matching the hostname clients connect to.
- Protect private keys and file permissions.
- Rotate certificates periodically and test reconnection.
- Allow only TLS protocols/ciphers that meet organizational policy.
- Enable Redis ACLs for all application clients.

If you want **mutual TLS (mTLS)**, you can require client certificates with `tls-auth-clients yes`, while configuring the client certificate/key and corresponding trust chain in the Lettuce client. Do not enable mTLS on the server and then only turn on `spring.data.redis.ssl.enabled` on the client expecting it to magically supply a certificate.

### 8.2. Do Not Disable Certificate Verification to "Fix" Connections

If a client fails because the certificate does not match the hostname or the CA is not trusted, fix the certificate/SAN, trust store, or endpoint. Never ship configurations to production that arbitrarily disable certificate validation or hostname verification.

TLS only protects against eavesdropping and spoofing when the client **actually verifies the peer**, not simply when a socket has an "encrypted" flag.

## 9. Redis ACLs: Separating Application Identities from Administrators

Since Redis 6, ACLs let you define users, passwords, key patterns, and allowed commands.

An application that only needs to read the catalog cache should not have permission to:

- Flush the entire Redis database.
- Run configuration or Cluster administration commands.
- Modify Redis ACLs.
- Access sessions or keys belonging to another service.
- Execute scripting/module commands outside business requirements.

Example permission design:

```text
User: catalog-reader
Key scope: cache:catalog:*
Commands: GET, EXISTS, TTL, PTTL, PING

User: catalog-writer
Key scope: cache:catalog:*
Commands: GET, SET, DEL, EXPIRE, ...
 
User: redis-operator
Separate admin permissions, never used in API instances
```

These user names and command sets are examples only. For `RedisCacheManager`, Spring Session, Spring Data Redis Streams, or Hash/Set/ZSet structures, the required commands may differ; observe the **actual commands used by the application** before crafting a minimal ACL.

### 9.1. Illustrative ACL Example

In an administrative Redis CLI session in a controlled environment, the rule syntax might look like:

```redis
ACL SETUSER catalog_reader on >CHANGE_TO_A_STRONG_SECRET ~cache:catalog:* +get +exists +ttl +pttl +ping
```

Meaning:

- `on`: enables the user.
- `>...`: sets the password for the user.
- `~cache:catalog:*`: restricts keys to the matching pattern.
- `+get +exists +ttl +pttl +ping`: allows only the commands needed for this read example.

**Do not use `CHANGE_TO_A_STRONG_SECRET` as a real password**, and never place real secrets into shell history, source repositories, or tickets/logs. In real systems, passwords should be generated, distributed, and rotated via a secure secret management mechanism; ACL configuration should be deployed through approved administrative workflows.

The rule above grants **very narrow read permissions** and is not a sufficient ACL for every Spring Data Redis application. Connection negotiation, ping, pub/sub, scripts, cache locks, sessions, or cluster operations may require additional commands depending on the driver/version.

### 9.2. Do Not Leave the Default User Unrestricted

If you create dedicated ACL users while leaving the `default` user with unrestricted, passwordless access, the ACL layer may fail to achieve its goal.

Manage the `default` user according to policy, and verify that every client has migrated to a dedicated user before disabling or restricting `default` to avoid outages. Never abruptly change production ACLs without first inventorying all connected applications, workers, monitoring agents, replication links, and admin tools.

### 9.3. Authentication and Authorization Are Different

- **AUTH/ACL user:** identifies which Redis identity the client logs in as.
- **ACL key patterns:** restricts which keys the user can operate on.
- **ACL command rules:** restricts which commands the user can execute.
- **Network policy:** restricts where connections can originate from.
- **Spring Security:** restricts which HTTP users can invoke application features.

An ACL user with a strong password that still has `+@all` and `~*` across all keys remains an overly broad account. If that password leaks from one service, the blast radius can affect all of Redis.

## 10. Secure Connection Configuration in Spring Boot / Spring Data Redis

For Spring Boot using Spring Data Redis and Lettuce, configuration can use these properties:

```yaml
spring:
  data:
    redis:
      host: ${REDIS_HOST}
      port: ${REDIS_PORT:6379}
      username: ${REDIS_USERNAME}
      password: ${REDIS_PASSWORD}
      ssl:
        enabled: true
      connect-timeout: 2s
      timeout: 2s
```

This example assumes:

- `REDIS_HOST` points to Redis's **private DNS name**.
- The Redis server **has TLS enabled** on the corresponding port.
- `REDIS_USERNAME` is a least-privilege Redis ACL user.
- The password is provided by a secret manager or secure configuration mechanism.
- The JVM/Lettuce trusts the appropriate CA and verifies the server certificate.
- Firewalls allow only authorized applications to connect to Redis.

If the Redis server does not have TLS enabled, setting `ssl.enabled: true` alone will prevent the client from completing the handshake. Conversely, if the server requires TLS while the client uses a plain connection, it will also fail; both sides must be configured consistently.

### 10.1. Be Careful with URIs Containing Secrets

Some configurations use a URI:

```text
rediss://user:password@private-redis.example.internal:6379
```

`rediss://` typically specifies TLS when used with a compatible driver URI. However, **embedding a password in a URI** risks leaks through logs, exceptions, monitoring, command lines, or configuration systems. Never hardcode credential-bearing URIs in a repository; use secret injection and platform masking mechanisms instead.

### 10.2. Never Log Secrets or Full Redis URLs

Avoid:

```java
log.info("Redis connection {}", redisUrlWithPassword);
```

Instead, log sanitized metadata, for example:

```text
Redis connection target:
    environment=production
    service=catalog-cache
    tls=true
    endpointClass=private
```

Never log passwords, tokens, session IDs, private keys, or sensitive payload data.

### 10.3. Use LettuceConnectionFactory Instead of Ad-Hoc Sockets

Spring Boot normally auto-configures `LettuceConnectionFactory` when the Spring Data Redis starter and appropriate properties are present. `RedisTemplate`, `StringRedisTemplate`, and `ReactiveRedisTemplate` should receive a securely configured connection factory rather than each service opening its own Redis connection with separate hardcoded IPs/users/passwords.

This keeps the following consistent:

- TLS and trust stores.
- The ACL user being used.
- Timeouts, reconnection, and topology handling.
- Secret rotation strategy.
- Observability and environment configuration.

Never spin up a custom connection with a hardcoded password just so a job "doesn't have to depend on Spring configuration."

## 11. Java Example: Using RedisTemplate and Restricting API Paths

A service reading the catalog cache:

```java
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class CatalogCacheReader {

    private final StringRedisTemplate redis;

    public CatalogCacheReader(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public String findCachedProduct(String productId) {
        String key = "cache:catalog:product:" + productId;
        return redis.opsForValue().get(key);
    }
}
```

This code does not itself decide whether Redis is private or uses TLS; those guarantees belong to the **connection factory and deployment infrastructure**.

With an API controller:

```java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/catalog")
public class CatalogController {

    private final CatalogCacheReader cache;

    public CatalogController(CatalogCacheReader cache) {
        this.cache = cache;
    }

    @PreAuthorize("hasAuthority('catalog:read')")
    @GetMapping("/{id}/cached")
    public String cached(@PathVariable String id) {
        return cache.findCachedProduct(id);
    }
}
```

`@PreAuthorize` only takes effect when method security is enabled and Spring Security authentication/authorization is properly configured; this snippet does not include the full `SecurityFilterChain`.

The two permission layers must remain independent:

1. Spring Security allows/denies the **HTTP user** from reading the catalog.
2. Redis ACL allows the **service identity** to read keys under `cache:catalog:*`.

Even when HTTP users are allowed to call an endpoint, they **must never receive Redis credentials** or open a direct Redis socket from the browser.

### 11.1. Do Not Expose an Arbitrary Redis Command Endpoint

An API like:

```text
POST /admin/redis-command
body: {"command": "ANY", "key": "..."}
```

turns the server into a proxy executing arbitrary Redis commands on behalf of callers. Never design such endpoints for end users. Dedicated administrative tooling, if genuinely needed, must have narrow permissions, auditing, operation allowlists, and strict access procedures.

Prefer business APIs with fixed commands instead of letting clients choose raw Redis commands or keys.

## 12. Docker: Avoid Publishing the Redis Port on the Host

Docker Compose is very convenient in development, but `ports` configuration can easily expose Redis on the host:

```yaml
services:
  redis:
    image: redis:7.4-alpine
    ports:
      - "6379:6379"
```

When published this way, Docker may bind the host port across interfaces depending on Docker and network settings. If the host has a public IP and the firewall is open, Redis can be reached from outside.

**In container deployments, applications sharing a Docker network usually do not need to publish the Redis port to the host.**

### 12.1. Example Without Publishing the Redis Port

```yaml
services:
  api:
    image: example/catalog-api:1.0
    environment:
      REDIS_HOST: redis
      REDIS_PORT: "6379"
    networks:
      - app-private

  redis:
    image: redis:7.4-alpine
    volumes:
      - ./redis.conf:/usr/local/etc/redis/redis.conf:ro
    command:
      - redis-server
      - /usr/local/etc/redis/redis.conf
    networks:
      - app-private
    # Do not declare ports to publish Redis to the host.

networks:
  app-private:
    internal: true
```

This illustrative configuration **only partially addresses container network boundaries**; you still need Redis ACLs, TLS where appropriate, secret provisioning, and least privilege for containers on the same network.

`internal: true` may restrict outbound connectivity from this network; if the API needs the Internet or a database on another network, you must arrange separate networks and controlled rules. Do not copy an internal network configuration blindly into every application without checking connectivity requirements.

Another container attached to `app-private` can still attempt to reach Redis. A Docker network is not a substitute for ACLs.

### 12.2. Local Development Requiring Host Access

When Redis CLI tooling is needed from a developer's machine, you can publish only on the machine's loopback address:

```yaml
ports:
  - "127.0.0.1:6379:6379"
```

This **restricts host binding to the IPv4 loopback** in supported setups, suitable for controlled developer environments. Do not treat it as an absolute guarantee across all Docker versions/platforms, and do not carry it over unnecessarily as a production pattern.

On machines with multiple network adapters, VMs, tunnels, or remote dev environments, still verify actual exposure with connectivity checks.

### 12.3. EXPOSE and ports Do Not Mean the Same Thing

- `EXPOSE` in a Dockerfile or `expose` in Compose mainly documents container ports for internal networking/metadata.
- `ports` publishes container ports to the host according to Docker rules.
- Omitting host port publishing does not prevent other containers on the same network from connecting.
- `network_mode: host` alters network namespace boundaries and must be evaluated separately.

Never use the absence of `EXPOSE` in a Dockerfile as proof that Redis cannot be reached.

## 13. Kubernetes: Redis Should Use ClusterIP

In Kubernetes, Redis is commonly exposed via an internal `Service`.

```yaml
apiVersion: v1
kind: Service
metadata:
  name: redis
  namespace: data
spec:
  type: ClusterIP
  selector:
    app: redis
  ports:
    - name: redis-tls
      port: 6379
      targetPort: 6379
      protocol: TCP
```

`ClusterIP` creates an internal cluster endpoint. This is generally the right choice for Redis when applications also run inside Kubernetes.

Avoid creating:

```yaml
spec:
  type: LoadBalancer
```

for Redis unless there is an explicit private load balancer architecture and strict source restrictions. Some cloud providers provision a public LoadBalancer by default, which can expose Redis.

Similarly, a Kubernetes `NodePort` can expose a port via node IPs, affecting exposure depending on networking and firewalls. Do not use NodePort just to "avoid configuring DNS."

### 13.1. ClusterIP Alone Is Not Enough

If a cluster has hundreds of namespaces, a `ClusterIP` Service may still be reachable by many pods across the cluster by default. Network segmentation must continue with **NetworkPolicy** and Redis ACLs.

## 14. Kubernetes NetworkPolicy: Allow Only Designated Pods

Suppose the Redis pod has label `app: redis` in namespace `data`, and the API pod has label `app: catalog-api` in namespace `apps`.

NetworkPolicy for Redis:

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: redis-only-catalog-api
  namespace: data
spec:
  podSelector:
    matchLabels:
      app: redis
  policyTypes:
    - Ingress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: apps
          podSelector:
            matchLabels:
              app: catalog-api
      ports:
        - protocol: TCP
          port: 6379
```

Meaning:

- The policy applies to Redis pods selected by `podSelector`.
- Ingress from pods labeled `app: catalog-api` in namespace `apps` is allowed to TCP 6379.
- Other sources not permitted by this policy are blocked **if no other NetworkPolicy allows them** and the CNI enforces NetworkPolicy properly.
- `namespaceSelector` and `podSelector` inside **the same `from` item** combine (AND) to select matching pods in the matching namespace.

### 14.1. NetworkPolicy Takes Effect Only When Supported by the CNI

Not all Kubernetes networking setups enforce NetworkPolicy in the same way. You must verify your cluster's CNI and network policy controller.

In addition, Kubernetes NetworkPolicy generally uses **additive allow semantics**. If another policy already allows all pods to reach Redis, adding the narrow policy above will **not revoke access already granted by the other policy**.

Therefore, review **all NetworkPolicies applying to Redis pods**, not just the newly created file.

### 14.2. Ingress and Egress Are Two Separate Directions

The policy above restricts **ingress to Redis**. If the application namespace has a default-deny egress policy, the application also needs an egress policy allowing connections to Redis and required DNS.

Likewise, Redis replication, Cluster, or Sentinel may require pod-to-pod connections among Redis pods. If you add an ingress policy only for the API and accidentally block inter-node traffic, the Cluster can lose quorum or failovers can break.

Do not copy a single port 6379 rule and assume it suffices for Redis Cluster/Sentinel; build a dedicated port and source/destination matrix for your actual topology.

## 15. Redis Cluster: Protect Both Data Ports and the Cluster Bus

Redis Cluster partitions the keyspace into hash slots, with primaries and replicas coordinating with one another. Nodes may need to communicate over:

- **Data/client ports** configured by the deployment.
- **Cluster bus ports**, commonly defaulting to data port + 10000 in standard configurations.
- Replication paths and TLS cluster bus if enabled.
- Endpoints received by the Lettuce client during topology discovery.

```text
                  Application private tier
                           |
                       TLS + ACL
                           |
                    Cluster data ports
                           |
             +-------------+-------------+
             |             |             |
          Primary A     Primary B     Primary C
             |             |             |
          Replica A     Replica B     Replica C
             \_____________|_____________/
                  Private cluster bus
                     (not public)
```

A Redis Cluster returns node addresses when clients discover topology. If those addresses are public IPs or hostnames unreachable from the private application network, clients may fail redirects/routing or be directed over paths violating network policy.

Verify that:

- Cluster announcement/advertised addresses are **private addresses reachable** from valid clients.
- The Redis Cluster bus is never published to the Internet.
- Firewalls allow node-to-node traffic only on the required ports, not all ports.
- Slot changes or failovers do not break client connectivity to new nodes.
- TLS certificates are valid for the hostnames clients actually use.
- ACLs allow only commands needed by the application; never grant cluster-admin rights to a service.
- `SCAN`/maintenance jobs cannot be turned into external full-cluster scanning tools.

### 15.1. TLS for Replication and Cluster

When using Redis TLS in deployments with replication or Cluster, settings such as `tls-replication yes` or `tls-cluster yes` may be needed depending on the version and mode. Certificates/trust, ports, and firewalls must be synchronized across nodes.

Enabling TLS only for app→primary while leaving primary→replica or node→node traffic unprotected **may fail internal security requirements**, depending on the threat model.

## 16. Sentinel: Separately Control Discovery and Failover Ports

Redis Sentinel typically uses port `26379` by default for clients and Sentinel nodes to access infrastructure state. In a Sentinel setup:

```text
             Spring Data Redis / Lettuce
                      |
                  Sentinel nodes
                      |
                Primary discovery
                      |
                      v
                   Redis primary
                      |
                   Replica(s)
```

If you allow the application to reach Sentinel but block it from connecting to the primary/replica returned by Sentinel, the client still cannot read or write data.

Therefore, firewall rules must accurately reflect both the **discovery flow and the data flow**:

1. Application → Sentinel endpoints, only on required ports.
2. Application → active Redis data endpoints.
3. Redis primary ↔ replicas/replication traffic according to topology.
4. Sentinel ↔ Redis/Sentinel communication per design.
5. No direct public access to any of these endpoints.

Sentinel also requires authentication/TLS and appropriate permissions. Never treat Sentinel as "just metadata so anyone can connect."

## 17. Managed Redis: Do Not Assume the Service Is Secure by Default

With cloud-managed Redis services, you may not directly edit `redis.conf` or bind interfaces. Instead, protective layers are provided through:

- Private endpoints and network placement.
- Cloud security groups / firewall rules.
- Service-level authentication/ACLs.
- TLS in transit and encryption at rest where supported.
- IAM/role-based controls for cloud management APIs.
- Audit logs, metrics, and failover mechanisms.
- Backup, retention, and key management policies.

Some cloud offerings provide a "publicly accessible" or public endpoint option, while others support private connectivity only. Never assume that because a service has "managed" in its name, it cannot be exposed.

### 17.1. Cloud Networking Checklist

- Which VPC/private network does the Redis resource live in?
- Is there any public IP or public DNS endpoint?
- Do security group inbound rules contain `0.0.0.0/0` or `::/0`?
- Is there any unintended cross-VPC/account connectivity or peering?
- Is there any public load balancer, tunnel, or port-forward to Redis?
- Which application identities are allowed to connect?
- How is the admin console/CLI accessed?
- What addresses do Redis Cluster/Sentinel nodes advertise?
- Are TLS and ACLs enabled properly?
- Can logging/alerting detect network policy changes?

These questions apply across AWS/Azure/GCP and equivalent infrastructures, even though specific product names and configuration fields differ.

## 18. Partitioning by Environment and by Application

Do not share a single production Redis across:

```text
production API
staging API
developer laptops
CI tests
experimental background workers
```

when all share equivalent credentials or write permissions. A test bug can wipe real caches/sessions, and secrets on laptops widen the attack surface into production.

Prefer:

- Separate Redis deployments, or at minimum separate networks and credentials per environment.
- No direct access to production from public CI/test runners.
- Separate application ACL users per role.
- Restricted key namespaces; however, **namespaces do not replace ACLs or network segmentation**.
- Clearly defined authorization for migrations or administrative commands.
- Do not use `SELECT databaseIndex` as a security boundary: Redis logical databases are not tenant isolation, and Redis Cluster has its own restrictions.

A module using `cache:*` and a module using `session:*` on the same Redis instance do not become security-isolated if both use a user with `~*` permissions and can connect from every network.

## 19. Least Privilege for Spring Cache, Spring Session, and Streams

Spring Data Redis is a broad library; actual ACL permissions depend on what the application uses.

| Workload | Data | Permissions to Evaluate |
|---|---|---|
| Simple `StringRedisTemplate` GET/SET | Catalog cache | GET/SET, TTL, DEL within namespace |
| `RedisCacheManager` | Cache entries | Appropriate cache get/put/evict/clear commands |
| Spring Session Redis | Session keys/indexes/expiry | Commands for session, index, TTL, and repository notifications |
| Redis Streams consumer | Streams and consumer groups | XREADGROUP, XACK, XPENDING, claim, and required lifecycle commands |
| Redis Pub/Sub listener | Channels | SUBSCRIBE/PSUBSCRIBE and matching channel patterns |
| Lua rate limiter | Counters/TTLs | Scripting/key permissions required by design |
| Health check | Connectivity probe | PING or defined check; never full Redis permissions |

### 19.1. Redis ACLs Also Support Channel Patterns

For Pub/Sub, key permissions are not enough to describe channels. Redis ACL versions support separate channel pattern restrictions according to server capabilities. Review ACL settings for `SUBSCRIBE`/`PUBLISH` to prevent services from listening or publishing on arbitrary channels unnecessarily.

### 19.2. Do Not Grant Broad Permissions to Fix NOPERM Errors

When migrating to restricted ACLs, you may hit `NOPERM` errors because the application uses unexpected commands. Do not "fix" this by giving every application user `+@all` and `~*`.

A better workflow:

1. Identify the exact command being denied.
2. Verify whether the use case is legitimate.
3. Add only the required command/key/channel pattern if needed.
4. Test read/write paths, expiration, reconnection, and failover.
5. Continue monitoring ACL failures.

Activities like session indexing, script evaluation, or cluster topology discovery may need extra permissions; always verify in a test environment.

## 20. Managing Passwords, Certificates, and Secret Rotation

Putting credentials in source code:

```java
String password = "redis-production-password"; // Do not do this.
```

or in configuration files committed to a repository:

```yaml
spring:
  data:
    redis:
      password: "hardcoded-production-secret"
```

is a major operational risk.

Instead:

- Use a cloud secret manager, vault, or platform secret injection mechanism.
- Restrict who and which workloads can read secrets.
- Separate production, staging, and development credentials.
- Never print secrets in logs, stack traces, CI output, or connection URIs.
- Manage credential rotation and lifetimes.
- Revoke old credentials after confirming applications have switched over.
- Ensure pods/containers can reload or reconnect when secrets change.

### 20.1. Zero-Outage Rotation

A rotation strategy may include:

```text
Create new credential with equivalent, restricted permissions
            |
            v
Distribute to application instances
            |
            v
Canary reconnect and verify GET/SET
            |
            v
Roll out to remaining instances
            |
            v
Verify no active sessions remain on old credential
            |
            v
Revoke old credential
```

Redis ACLs can support configuring users/passwords according to version-specific mechanisms, but rotation ordering and support for multiple simultaneous credentials must be designed for your deployment system. Never delete the old credential immediately before connections have migrated unless downtime is planned.

### 20.2. Certificate Rotation

When rotating TLS certificates:

- The new certificate must match the expected hostname.
- The client trust chain must be updated.
- Old and new connections may behave differently during the rollout window.
- Test reconnection and failover behavior.
- Never "fix" issues by disabling hostname verification.

Protect server certificates and client private keys if using mTLS; never mount certificate/private key files with overly broad permissions.

## 21. Detecting Publicly Exposed Redis

You cannot confirm Redis is secure merely because configuration files look reasonable. You must **verify actual network paths** from both allowed and disallowed sources within the infrastructure you manage.

### 21.1. Inspecting Listening Configuration

In an environment where you have administrative access, verify:

- Which IPs/ports is Redis listening on?
- Are both IPv4 and IPv6 active?
- Is there an unintended plain TCP listener?
- Does Docker publish any host ports?
- Is a Kubernetes Service of type `LoadBalancer` or `NodePort`?
- Do security groups/firewalls allow broad sources?
- Is any load balancer, proxy, or tunnel forwarding to Redis?

Common inspection commands:

```bash
# On an authorized Linux host administering Redis:
ss -lnt

# In a Docker environment:
docker ps

# In Kubernetes:
kubectl get svc -A
kubectl get networkpolicy -A
```

These commands inspect local configuration in environments you are authorized to manage. `ss -lnt` shows listening sockets on the queried machine; it does not prove whether Internet traffic can traverse external firewalls. `kubectl get svc` shows Services, but does not replace checking cloud load balancers and security groups.

### 21.2. Testing Connectivity from an Allowed Source

From an authorized application instance or test pod:

```bash
redis-cli --tls \
  --host private-redis.example.internal \
  --port 6379 \
  --user catalog_reader \
  PING
```

This illustrative command omits the password; in a test environment, supply credentials securely via environment secrets or credential prompts supported by Redis CLI and your platform. Never pass real passwords directly on a command line visible in process lists or shell history.

A `PONG` response confirms at least one Redis command completed, but it **does not prove**:

- That the client has only minimal ACL permissions.
- That the server certificate was verified under real policy.
- That all commands required by the application succeed.
- That the Redis address is unreachable from untrusted sources.
- That Replication/Cluster/Sentinel and failover operate securely.

### 21.3. Testing from a Disallowed Source

From a test network owned and authorized by administrators, direct connections to the private Redis endpoint **must be rejected or time out per firewall policy** if the source is not on the allowlist.

Keep these distinctions clear:

- Unresolvable private DNS from outside can be a helpful layer, not final proof.
- If a public endpoint exists, a private DNS record does not stop the public IP from being reachable.
- No `PING` response might be due to TLS/auth failure while a TCP socket was still accepted from the Internet.
- The goal is **no unauthorized network path to Redis**, not merely "unable to AUTH."

Never scan or attempt to connect to third-party systems without authorization; keep testing strictly within infrastructure/networks you own and administer.

## 22. Testing ACL Permissions and Distinguishing Errors

A security test suite should verify both directions:

### Allowed Permissions

- The API user can read keys in its granted namespace.
- The API writer can write/evict allowed keys.
- Spring Session/Streams operate with their dedicated, properly scoped users.
- Reconnect after failover still uses the right ACLs.
- TLS handshake and hostname validation succeed with a valid certificate.

### Disallowed Permissions

- The API user **cannot** read keys in another service's session namespace.
- The API user **cannot** run dangerous administrative commands.
- A read-only user cannot write.
- Unauthorized clients cannot connect across network policies.
- Invalid credentials are clearly rejected.
- Untrusted certificates or mismatched hostnames cause TLS connections to fail.

In Spring Data Redis, errors such as connection timeouts, `NOAUTH`/`NOPERM`, certificate failures, or configuration errors surface as driver or Spring Data Access exceptions. Never turn those errors into cache misses via `catch (Exception) { return null; }`.

### 22.1. Fail Closed for Sensitive Data

When Redis holds only a catalog cache backed by a database as source of truth, bounded fallback on Redis errors may be acceptable. However, for:

- Session authentication.
- Anti-replay tokens.
- Rate limits protecting sensitive endpoints.
- Locks protecting critical invariants.
- Revocation state.

you must never treat a Redis access error as "key does not exist" and allow the request through. Choosing fail-open vs. fail-closed must come from the threat model and source of truth, not a convenient catch block.

## 23. Application-Layer Protection Against Traffic Storms and Denial of Service

Even a Redis instance with only a private endpoint can be overloaded by internal clients if an application has bugs or traffic bursts.

Safeguards:

- Enforce timeouts on Redis commands.
- Use connection/pool/concurrency policies suited to the workload.
- Never issue thousands of blocking Redis requests from an event loop.
- Limit retries to avoid retry storms when Redis is unavailable.
- Never let HTTP clients directly trigger large scan commands.
- Use bulkheads/rate limits on database fallbacks during a Redis outage.
- Bound value sizes, expensive collection commands, and long-running scripts.
- Alert on abnormal spikes in connected clients, CPU, memory, and command latency.

Redis Cluster/replicas are not an automatic shield against DoS: a hot key still concentrates on one shard, and long Lua scripts still block the primary's execution thread.

### 23.1. Never Run Administrative Commands in User Requests

Avoid endpoints that execute `KEYS *`, `FLUSHALL`, `CONFIG SET`, or equivalent administrative operations from client input. If maintenance jobs are needed, run them through controlled channels with restricted permissions, bounded key counts, rate limits, and auditing.

## 24. Observability and Auditing While Securing Redis

Metrics to monitor:

| Metric/Log | Question |
|---|---|
| Redis connections by source/network | Are unexpected clients connecting? |
| Authentication failure count | Are there wrong credentials or auth probing attempts? |
| ACL denied commands/keys/channels | Is the app missing permissions or attempting abnormal actions? |
| Redis command QPS/latency | Did anything change abnormally after a deploy? |
| Connected clients | Is there a connection leak or burst? |
| Redis memory/evictions | Is there memory pressure or unexpected data eviction? |
| TLS handshake/certificate errors | Are there trust, expiry, or SAN errors? |
| Firewall/security group change logs | Was an overly broad rule added? |
| Public endpoint inventory | Was a new Redis resource published? |
| Cluster/Sentinel failover events | Were there unexpected node or connection shifts? |
| Slowlog/commandstats | Are there overly slow commands or new workloads? |
| Secret access/rotation logs | Who accessed or rotated credentials? |

Redis provides several inspection tools:

```bash
redis-cli INFO clients
redis-cli INFO stats
redis-cli INFO commandstats
redis-cli INFO memory
redis-cli ACL LOG 10
redis-cli SLOWLOG GET 10
```

Some commands such as `ACL LOG` may require administrative privileges and should not be granted to standard API services. When collecting logs, avoid shipping sensitive data or internal addresses into public systems.

### 24.1. High-Value Alerts

Examples of conditions to alert on:

- Redis inbound security group rules containing `0.0.0.0/0` or `::/0`.
- A Kubernetes Redis Service changing from `ClusterIP` to `LoadBalancer` without approval.
- A newly published port on Docker or the host.
- Redis starting to listen unexpectedly on a public interface.
- `ACL LOG` showing unusual `NOPERM`/authentication failures.
- TLS certificates nearing expiration or hostname verification starting to fail.
- Replica/Cluster bus endpoints exposed to broad networks.
- Sudden spikes in Redis connection counts and command latency.

Do not alert only when Redis CPU is high: many network exposure security failures occur long before heavy load or suspicious traffic arrives.

## 25. Separating Client Path and Internal Redis Path Protection

In Redis deployments with replication/Cluster, there are two traffic groups:

1. **Client → Redis:** GET/SET/EVAL/Streams/PubSub from applications.
2. **Redis node ↔ Redis node:** replication, Cluster bus, and Sentinel coordination per the architecture.

If you control only the client path while leaving inter-node links unprotected, an attacker with network access inside internal infrastructure could target replication or coordination components where protocols and permissions allow.

You need to:

- Separate client and inter-node rules.
- Restrict node sources strictly to the Redis node list.
- Use appropriate TLS and authentication for replication/Cluster/Sentinel.
- Verify node/replica changes during failover.
- Account for autoscaling node CIDRs and private DNS.
- Never place unprotected management endpoints or metrics exporters on public interfaces.

In particular, a deployment where the Redis data port uses TLS while the Cluster bus has no network restrictions **still needs remediation**.

## 26. Safe Administrative Access Operations

Operators sometimes need `redis-cli` to inspect keys or check Redis health. Direct access from laptops over a public port should never be the default path.

Better options:

- A bastion/private jump host with strong authentication and auditing.
- A managed VPN with group-based and time-bound authorization.
- Privileged administration jobs inside the private network with least privilege.
- Temporary port-forwarding over a secured channel, tied to controlled permissions and sessions.
- A managed provider console/connection tool if it supports private networking and auditing.

Administrative procedures should:

1. Define the purpose and time window of access.
2. Use dedicated admin ACL users rather than borrowing application credentials.
3. Restrict network sources and opening durations.
4. Keep secrets out of shell history and logs.
5. Record infrastructure changes via change management.
6. Revoke temporary permissions/tunnels when finished.

Never create a "temporarily open to the entire Internet" firewall exception and leave it behind as permanent configuration.

## 27. Incident Scenario: Redis Found Exposed on a Public Port

Suppose a production Redis instance is discovered to have a public endpoint or overly broad inbound rule. Response should prioritize **containment and preserving investigative evidence**, rather than just changing the password and calling it done.

### 27.1. Immediately Isolate Unnecessary Paths

- Block public inbound access to Redis using security groups, firewalls, or network policies.
- Audit any port-forwards, load balancers, or tunnels that might provide alternate paths.
- Keep private routes working for legitimate applications to avoid unnecessary self-inflicted outages.
- If compromise is suspected, follow your organization's incident response process and preserve relevant logs/evidence.

### 27.2. Assess Blast Radius

- How long was Redis exposed?
- Was authentication enabled and sufficiently strong?
- What permissions did the ACL `default` user and application users have?
- Are there signs of unauthorized access, unusual commands, or ACL/CONFIG changes?
- What data was stored: caches, sessions, tokens, PII, or business state?
- Could any replicas or backups have been affected?
- Do sessions/tokens need to be revoked or business state reconciled?

### 27.3. Remediate and Recover

- Rotate credentials/secrets and certificates as needed.
- Revoke overly broad privileges; separate users by workload.
- Verify data integrity and reconcile against authoritative sources.
- If needed, restore from a trusted backup at an appropriate point in time.
- Revoke sessions/tokens if exposure risk exists.
- Audit hosts/containers and administrative access paths.
- Re-verify private connectivity, firewalls, and TLS from both allowed and disallowed sources.
- Prevent recurrence via IaC, policy-as-code, and drift/exposure alerts.

**Do not assume changing the Redis password fixes overwritten data or exposed tokens.** You must evaluate business state and downstream systems that consumed Redis data.

## 28. Security Testing Across Environments

A test plan should cover the following categories:

### 28.1. Network

- Redis has no unapproved public-facing endpoint.
- IPv4/IPv6 firewalls block Internet traffic to data, Sentinel, and Cluster ports.
- Application private subnets can connect to Redis.
- Workloads in unauthorized namespaces/networks **cannot** connect.
- Load balancers, Docker port publishing, and Kubernetes Services do not accidentally expose public ports.
- Redis Cluster/Sentinel internal nodes continue communicating properly after policies are applied.

### 28.2. TLS

- Clients validate legitimate Redis certificates.
- TLS certificates with mismatched hostnames are rejected.
- Untrusted CAs are rejected.
- No unintended plain TCP path exists.
- Certificate rotation does not cause prolonged client disconnections.
- Replication/Cluster traffic is protected per policy.

### 28.3. ACL

- Reader user can `GET` only allowed keys.
- Reader user cannot `SET`/`DEL`.
- Application users cannot run admin commands.
- Users cannot access keys in another service's namespace.
- Wrong credentials are rejected.
- Actual Spring Cache/Session/Streams commands work under least privilege.

### 28.4. Failover and Rollout

- When the primary changes, clients connect over private routes to the new primary.
- Redis Cluster redirects do not require opening public IPs.
- Sentinel discovery returns endpoints the application can actually reach.
- Secret rotation and TLS renewal keep the application within SLOs.
- A Redis outage does not cause the API to bypass session, rate-limit, or authorization checks.

### 28.5. Logging

- No Redis passwords, credential-bearing Redis URIs, or session IDs appear in logs.
- No sensitive data is used as metric labels.
- Firewall/ACL changes are audited.
- Alerts fire for exposed ports and authentication failures.

Run these tests in controlled environments within infrastructure you own. You do not need to run destructive actions or attacks against production to verify that Redis ports are restricted.

## 29. Common Misconfiguration Table

| Mistake | Risk | Remediation |
|---|---|---|
| Redis listens on `0.0.0.0` on a host with a public IP and open port | Internet reaches Redis | Private bind/firewall, no public endpoint |
| Security group inbound `0.0.0.0/0` or `::/0` | Broad attack surface | Allow only application identities/private sources |
| Assuming `protected-mode yes` is sufficient | Other settings can still expose Redis | Defense in depth |
| Using a password without TLS | Credentials/data observable on the network | TLS and certificate verification |
| Disabling certificate validation for quick connectivity | Endpoint spoofing risk | Fix CA/SAN/trust store |
| Redis ACL user `+@all ~*` for API | Overly broad blast radius if app/secret compromised | Least privilege by command/key/channel |
| Leaving `default` user unrestricted | Undermines ACL segmentation | Audit and restrict/disable default user |
| Putting passwords in Git/URI/logs | Credential leakage | Secret manager and rotation |
| Docker Compose publishing `6379:6379` | Host port may be exposed publicly | Do not publish; use private networks |
| Public Kubernetes Redis `LoadBalancer` Service | Internet path to Redis | `ClusterIP` and `NetworkPolicy` |
| Relying on `ClusterIP` without `NetworkPolicy` | Many internal pods can reach Redis | Ingress/egress allowlists, CNI enforcement |
| Another overly broad `NetworkPolicy` exists | Narrow policy does not revoke old allow rules | Audit all additive policies |
| Exposing Cluster bus/Sentinel publicly | Infrastructure protocol exposure | Inter-node private rules |
| Cluster announces public addresses | Unsafe or unstable client routing | Private advertised addresses |
| Sharing prod Redis across all environments | Test/dev can affect real data | Separate deployments and users |
| Using database index as tenant security | Insufficient isolation | ACLs/network/namespaces by boundary |
| Treating Redis errors as security cache misses | Can bypass security checks | Classify errors; fail closed when required |
| Opening temporary public port and forgetting to close it | Prolonged exposure | IaC policy, alerts, and change control |
| Not monitoring auth/ACL/network changes | Misconfigurations go undetected | Auditing, metrics, and alerting |

## 30. Private Redis Deployment Decision Tree

```text
Does the Spring Data Redis app need Redis?
                  |
                  v
         Does Redis have a public endpoint?
              /          \
            Yes       Unknown / No
             |                 |
             v                 v
       Remove public      Verify routing,
         exposure        IPv4/IPv6, firewalls
             |                 |
             +--------+--------+
                      |
                      v
        Do only authorized apps/workers
         have a private route to Redis?
                  /          \
                No           Yes
                 |            |
                 v            v
        Fix firewall/SG   Enable Redis ACLs
        NetworkPolicy     by role/key
                 |            |
                 +-----+------+
                       |
                       v
                   TLS enabled?
                  /       \
                No        Yes
                 |         |
                 v         v
             Enable TLS   Verify certs,
             server/app   hostname/trust
                 |         |
                 +----+----+
                      |
                      v
          Using Sentinel/Cluster/replicas?
                   /         \
                 Yes          No
                  |            |
                  v            |
       Protect inter-node ports|
       and private discovery   |
                  |            |
                  +-----+------+
                        |
                        v
         Test allowed/denied connections,
         ACLs, TLS, failover, and logs
                        |
                        v
            Codify policies in IaC,
            monitor drift, and rotate
            credentials periodically
```

## 31. Phased Implementation Plan

### Phase 1: Inventory

- List all Redis deployments, endpoints, and environments.
- Identify stored data, current users/clients, and required permissions.
- Identify whether Redis is Standalone, Sentinel, or Cluster.
- Inspect public endpoints, firewalls, and Docker/Kubernetes exposure.
- Collect connection metrics and command groups to prepare ACLs.

### Phase 2: Close Public Paths

- Move Redis into a private network or private endpoint.
- Block inbound traffic from the Internet, including IPv4/IPv6.
- Allow only approved workloads.
- Protect Cluster/Sentinel/inter-node ports.
- Verify applications still connect over private routes.

### Phase 3: Secure Connections and Identities

- Configure TLS, CAs, hostnames, and client trust.
- Create Redis ACL users per service/role.
- Distribute secrets via a secret manager.
- Test GET/SET/Streams/Session permissions per use case.
- Restrict the `default` user and administrative commands.

### Phase 4: Fault Testing and Rollout

- Test denied network paths, wrong credentials, and invalid TLS.
- Test failover/resharding to verify private connectivity.
- Verify a Redis outage does not cause the application to bypass security.
- Run a canary rollout, watching timeouts and auth failures.
- Revoke old credentials after verifying migration.

### Phase 5: Maintain

- Manage firewalls/Services/NetworkPolicies via IaC.
- Detect drift and alert on public rules.
- Rotate secrets and certificates.
- Review ACL permissions after feature changes.
- Practice incident response drills and inspect new endpoints.

## 32. Summary

**Restricting network access is the primary requirement for protecting Redis from the public Internet.** In a Spring Data Redis architecture, browsers and untrusted clients should interact only with authenticated APIs, while Redis stays inside a private network and accepts connections only from authorized workloads.

Key principles to remember:

1. **Never publish Redis directly to the Internet.** Audit public IPv4/IPv6, firewalls, Docker ports, Kubernetes Services, and cloud endpoints.
2. **Private network + allowlist is the foundation.** Allow only designated APIs, workers, and administrative components to reach data ports.
3. **Redis `bind` and `protected-mode` do not replace firewalls.** They must work together within a defense-in-depth model.
4. **TLS protects traffic in transit; ACLs restrict permissions.** Both must be configured consistently with Spring Data Redis/Lettuce.
5. **Credentials must be managed and rotated.** Never hardcode passwords or expose them in URIs/logs.
6. **Redis Cluster/Sentinel have multiple ports and connection paths.** Protect the data path, discovery, replication, and cluster bus; use private node addresses.
7. **Environments must be isolated.** Test/dev must never share production-equivalent credentials or permissions.
8. **Verify over real network paths.** Connections from allowed sources must succeed; unauthorized sources must have no path to Redis.
9. **Monitor drift and incidents.** ACL failures, TLS errors, public port changes, and network policy changes are critical operational signals.
10. **Applications must still handle errors safely.** A Redis timeout must never become a reason to skip authentication, rate limiting, or security checks.

**Core rule:** Redis should only ever be visible to authorized clients inside a controlled network, and each client should only be able to perform the operations it genuinely needs. Blocking public access, securing transport, enforcing least privilege, and continuously verifying configuration are indispensable parts of a secure Spring Data Redis system.
