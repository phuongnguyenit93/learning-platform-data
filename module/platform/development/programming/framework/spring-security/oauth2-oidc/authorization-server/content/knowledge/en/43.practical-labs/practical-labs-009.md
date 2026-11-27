# Deploying Multiple Instances Behind a Proxy with Stable Issuer and Sessions

When Spring Authorization Server runs across multiple instances behind a reverse proxy or load balancer, every instance must collectively represent a single Authorization Server. Clients see one issuer, one HTTPS domain, and one set of public endpoints; backend nodes handle requests interchangeably without altering server identity, dropping login sessions, or issuing unverifiable tokens.

This lab builds a deployment consisting of a TLS-terminating reverse proxy, two Spring Authorization Server instances, shared PostgreSQL for clients/authorizations/consents, shared Redis for HTTP sessions, and a stable signing key set. The goal is to prove that a user can start logging in on node A and continue on node B, an authorization code issued on one node can be exchanged on the other, metadata always publishes the same issuer, and tokens from any node verify against the same JWKS.

Core guiding principles:

- The issuer is a fixed public identifier, independent of individual nodes or arbitrary request headers.
- The edge proxy strips or overwrites client-supplied forwarded headers, and backends accept traffic only from the trusted proxy.
- Every node shares the same client, authorization, consent, and signing key set stores.
- If login sessions must span multiple nodes, HTTP sessions must be shared or an explicit re-authentication policy must be accepted.
- The load balancer sends traffic only to ready nodes; rollouts and key rotations must preserve compatibility during transition windows.

## 1. Objectives and Deployment Topology

The lab scenario uses the domain auth.example.test, two application nodes, and two shared dependencies. The .test TLD is reserved for testing environments; in real deployments, replace it with a controlled domain.

~~~text
                     Browser / OAuth2 Clients
                               |
                               | HTTPS auth.example.test
                               v
                    +----------------------+
                    | Reverse Proxy / LB   |
                    | TLS + host allowlist |
                    | forwarded header     |
                    | normalization        |
                    +----------------------+
                         |            |
                  private HTTP   private HTTP
                         |            |
                         v            v
                +----------------+ +----------------+
                | Auth Server A  | | Auth Server B  |
                | same issuer    | | same issuer    |
                | same config    | | same key set   |
                +----------------+ +----------------+
                         |            |
              +----------+------------+-----------+
              |                                  |
              v                                  v
       +--------------+                  +---------------+
       | PostgreSQL   |                  | Redis         |
       | client       |                  | shared HTTP   |
       | authorization|                  | sessions      |
       | consent      |                  |               |
       +--------------+                  +---------------+
              |
              v
       Backup / monitoring

       KMS / HSM / Key Manager supplies the same active
       signing key set to both Authorization Server nodes.
~~~

| Component | Responsibility | HA Requirements |
|---|---|---|
| Reverse proxy/load balancer | TLS, host allowlist, routing, header normalization, health checks | Health checks, node draining, and trusting only designated upstreams |
| Authorization Server A/B | OAuth/OIDC endpoints, login, consent, token issuance | Same issuer, config, client policy, key set, and dependencies |
| PostgreSQL | RegisteredClient, OAuth2Authorization, consent | Backups, failover, compatible migrations, and connection limits |
| Redis | Shared HTTP sessions when Spring Session is enabled | Persistence/failover as required, ACLs, internal TLS, and TTLs |
| KMS/HSM/key manager | Private signing keys and key lifecycle | Both nodes permitted to use the same key version; operations audited |
| Resource Server/clients | Verifies access tokens/ID Tokens | Trust the same issuer and fetch JWKS from the stable public endpoint |

Do not collapse distinct state types into one concept. PostgreSQL holds OAuth state such as authorization codes, access token metadata, refresh tokens, and consents. Redis holds HTTP sessions such as SecurityContext, login state, and web state needed across requests. Signing keys maintain JWT signature continuity. Each has its own lifecycle, access controls, and recovery mechanism.

## 2. Issuer Must Remain Stable Across All Nodes

The issuer is the identifier of the Authorization Server. This value appears in metadata and the token's iss claim. For a system with a fixed public domain, all instances must use the exact same absolute value, including scheme, host, and path if present.

Explicit configuration:

~~~java
@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
            .issuer("https://auth.example.test")
            .build();
}
~~~

Do not configure the issuer with internal addresses such as http://auth-server-a:9000, localhost, a container hostname, or a node-specific address. Do not derive the issuer from unvalidated Host, Forwarded, or X-Forwarded-Host headers.

If supporting multiple domains or tenants, map each proxy-validated host to an allowlisted issuer. Never allow a client to send an arbitrary Host header and cause the Authorization Server to mint tokens bearing a client-chosen issuer.

### Checking Issuer and Metadata

Call metadata over the public domain:

~~~bash
curl -fsS https://auth.example.test/.well-known/openid-configuration
~~~

Verify at minimum:

- issuer is exactly https://auth.example.test.
- authorization_endpoint, token_endpoint, and jwks_uri use HTTPS and the public domain.
- Endpoints contain no internal hostnames, backend ports, or duplicated paths.
- Both nodes return identical metadata for issuer and endpoints.
- The iss claim of ID Tokens and JWT access tokens matches the published issuer according to the system profile.

If OIDC is not enabled, check the corresponding OAuth Authorization Server Metadata endpoint. Do not use the OIDC discovery endpoint to conclude an OIDC feature is active if configuration does not support it.

A useful smoke test is calling the public domain repeatedly and verifying the response does not change regardless of which node the load balancer picks. You can add a temporary header in test environments to identify the serving node, but never leak sensitive infrastructure details in production responses.

## 3. Establishing the Trust Boundary at the Reverse Proxy

When the proxy terminates TLS, traffic from the proxy to Spring Authorization Server may be internal HTTP. The application needs to know the client's original request used HTTPS, but should only trust that information when the request genuinely came through an authorized proxy.

The edge proxy must:

1. Accept only configured hosts/domains.
2. Strip client-supplied forwarded headers.
3. Reconstruct scheme, host, port, and source address from the connection observed by the proxy.
4. Forward traffic to backends only over a private network.
5. Never leave backends directly reachable from the Internet or untrusted networks.

Nginx example when Nginx receives connections directly from clients:

~~~nginx
upstream authorization_servers {
    least_conn;
    server auth-server-a:9000 max_fails=3 fail_timeout=10s;
    server auth-server-b:9000 max_fails=3 fail_timeout=10s;
    keepalive 32;
}

server {
    listen 443 ssl;
    server_name auth.example.test;

    # TLS certificate and private key are configured here.

    location / {
        proxy_pass http://authorization_servers;
        proxy_http_version 1.1;

        # This virtual host is restricted to the canonical public host.
        proxy_set_header Host auth.example.test;

        # Discard values supplied by the external client.
        proxy_set_header Forwarded "";
        proxy_set_header X-Forwarded-Host auth.example.test;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-Port 443;

        # This example assumes Nginx sees the client connection directly.
        proxy_set_header X-Forwarded-For $remote_addr;

        proxy_set_header Connection "";
    }
}
~~~

This example assumes Nginx is the direct edge proxy. If a CDN or load balancer sits in front of Nginx, $remote_addr may be the address of that upstream hop. Configure real IP extraction only after restricting exact trusted upstream CIDRs and verifying headers created by that upstream. Never treat Internet-supplied X-Forwarded-For values as trusted client IPs.

Do not send conflicting Forwarded and X-Forwarded-* headers simultaneously. Pick one convention and apply it consistently. With multiple proxies, clearly define which hop strips headers, which hop rewrites them, and which network range application nodes accept requests from.

### Restricting Backend Access Paths

Firewalls, security groups, or network policies must ensure:

- Only the proxy/load balancer can reach the Authorization Server's HTTP port.
- PostgreSQL accepts connections only from required service subnets.
- Redis accepts connections only from application instances and authorized management components.
- Actuator/management ports are never exposed publicly.
- No auxiliary ingress rule permits direct backend access for debugging in production.

If the backend can be called directly, an attacker can forge X-Forwarded-Proto: https and X-Forwarded-Host: auth.example.test. Enabling forwarded header handling in the application cannot authenticate the header sender; the network must enforce that boundary.

## 4. Configuring Spring to Handle Forwarded Headers

For a Spring Boot Servlet application, select the framework strategy so Spring interprets forwarded headers:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

The framework strategy uses Spring Framework capabilities, typically via ForwardedHeaderFilter, so downstream components observe the external scheme, host, port, and request URI.

Common Spring Boot options:

| Value | Behavior |
|---|---|
| none | Disable automatic forwarded header processing |
| framework | Use Spring Framework's processing |
| native | Use the web server/container's mechanism, if supported by the runtime |

Pick one strategy suited to your runtime. Do not enable native container processing while also registering another ForwardedHeaderFilter doing the same work if that causes headers to be processed twice. When Boot already registers the filter via the framework setting, do not create a duplicate filter.

For applications not using Spring Boot auto-configuration, register ForwardedHeaderFilter manually. The filter must run before components that read request scheme, host, port, or URI, including the Spring Security filter chain. Verify the application's effective filter order.

### Illustrative Application Configuration

~~~yaml
server:
  port: 9000
  forward-headers-strategy: framework
  shutdown: graceful

spring:
  datasource:
    url: jdbc:postgresql://postgres:5432/authorization
    hikari:
      maximum-pool-size: 20
      minimum-idle: 5
      connection-timeout: 3000
  session:
    timeout: 30m
    redis:
      namespace: auth-server:sessions
  data:
    redis:
      host: redis
      port: 6379

management:
  endpoint:
    health:
      probes:
        enabled: true
  endpoints:
    web:
      exposure:
        include: health,info,prometheus
~~~

Database username/password and Redis credentials are injected from a secret manager or runtime environment. Pool size and timeouts in the example are starting values; calculate them based on total instance count and database connection limits. Do not expose actuator endpoints publicly beyond controlled endpoints.

Session cookies must be configured for HTTPS and the public domain. Example attributes to consider:

~~~yaml
server:
  servlet:
    session:
      cookie:
        secure: true
        http-only: true
        same-site: lax
~~~

SameSite must match how clients perform redirects and response modes. Lax usually fits top-level GET navigations, whereas flows using cross-site POST or form_post may require a different policy. Do not switch to None without enabling Secure and evaluating CSRF risks. Test in a real browser with your system's callback and consent flows.

## 5. Sharing OAuth Persistence Across Nodes

Every node must share the same data source for clients, authorizations, and consents. With JDBC, the standard services are:

- JdbcRegisteredClientRepository
- JdbcOAuth2AuthorizationService
- JdbcOAuth2AuthorizationConsentService

Illustrative configuration:

~~~java
@Bean
RegisteredClientRepository registeredClientRepository(
        JdbcTemplate jdbcTemplate) {
    return new JdbcRegisteredClientRepository(jdbcTemplate);
}

@Bean
OAuth2AuthorizationService authorizationService(
        JdbcTemplate jdbcTemplate,
        RegisteredClientRepository registeredClients) {
    return new JdbcOAuth2AuthorizationService(
            jdbcTemplate, registeredClients);
}

@Bean
OAuth2AuthorizationConsentService authorizationConsentService(
        JdbcTemplate jdbcTemplate,
        RegisteredClientRepository registeredClients) {
    return new JdbcOAuth2AuthorizationConsentService(
            jdbcTemplate, registeredClients);
}
~~~

Both nodes must point to the same database/schema with compatible migrations applied. Never use a per-instance InMemoryOAuth2AuthorizationService in an HA deployment. If an authorization exists only in node A's memory, a token request routed to node B will not find the code or authorization.

### Distinguishing OAuth State from HTTP Sessions

| Data | Suitable Storage | Reason |
|---|---|---|
| RegisteredClient | Shared database | Every node must enforce the same client policy |
| Authorization code and OAuth2Authorization | Shared database | A code issued on node A must be exchangeable on node B |
| Consent | Shared database | Users should not be re-prompted just because requests hit another node |
| HTTP session/SecurityContext | Shared session store if login must span nodes | Browsers may send the next request to a different node |
| Signing private key | Shared KMS/HSM/key manager or securely synced key material | Tokens signed by any node must verify everywhere |
| Cache | Distributed cache or local cache with proper TTL/invalidation | Stale security data must never remain trusted past policy |

OAuth persistence and HTTP sessions solve two separate problems. Using PostgreSQL for authorizations alone does not automatically share login sessions. Using Redis for sessions alone does not make authorization codes durable.

### Migrations and Transactions

- Manage schemas with Flyway/Liquibase or a versioned migration process.
- Install the exact schema matching the Spring Authorization Server version in use.
- Run migrations once via a controlled deployment job; never let multiple nodes run destructive migrations concurrently.
- Test both from an empty database and from the previous release's schema.
- Use appropriate transactions and isolation for creating/updating authorizations.
- Test two concurrent requests exchanging the same authorization code; only one request may succeed per grant semantics.
- Do not assume `@Transactional` in tests covers requests hitting a server running on a separate thread/real port.

For large authorization tables, monitor indexes, locks, query latency, and connection pools. If using read replicas, never read freshly written authorization state from a replica with replication lag during token exchange or consent; read paths require appropriate consistency.

## 6. Sharing HTTP Sessions Across Instances

Login and consent are stateful web interactions. The browser sends the session cookie to the Authorization Server domain; the load balancer may route the first request to node A and the next request to node B. If each node keeps sessions only in its own memory, node B will not see the SecurityContext or web state needed to continue.

There are three strategies:

| Strategy | How It Works | Limitations |
|---|---|---|
| Local session + sticky sessions | LB tries to keep a browser on the same node | Node failure or rebalancing drops sessions; not true shared-session HA |
| Shared session via Spring Session Redis | Every node reads/writes sessions from Redis | Requires operating Redis, securing credentials, serialization, and failover |
| No long-lived sessions | Requires re-authentication on node change/session loss | Worse UX; suitable only when acceptable by policy |

This lab uses Spring Session Redis. Add the dependencies matching your project's Spring Boot version, for example in Maven:

~~~xml
<dependency>
    <groupId>org.springframework.session</groupId>
    <artifactId>spring-session-data-redis</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-redis</artifactId>
</dependency>
~~~

Artifact names and auto-configuration depend on the Spring Boot version in use; check your project's dependency management. When Spring Session Redis is configured, nodes use the same Redis endpoint and namespace to share sessions.

Example Redis configuration:

~~~yaml
spring:
  session:
    store-type: redis
    timeout: 30m
    redis:
      namespace: auth-server:sessions
  data:
    redis:
      host: redis.internal
      port: 6379
~~~

In production, enable TLS/ACLs or authentication mechanisms supported by your Redis platform; never expose Redis to the Internet. Configure timeouts per session policy and ensure session TTLs refresh properly. If the application uses Spring Boot auto-configuration, avoid simultaneously adding another EnableRedisHttpSession configuration if it creates competing session configurations.

### Session Serialization and Rolling Deployments

Shared sessions may contain serialized objects. During rolling deployments, new nodes must be able to read sessions written by old nodes. Therefore:

- Maintain class and serialVersionUID compatibility during rollouts.
- Avoid storing unnecessary custom objects or frequently changing classes in the session.
- Prefer small, stable, reconstructible session data.
- Evaluate serializers and formats supported by your Spring Session version.
- Test that new nodes can read sessions created by old nodes before shifting traffic.
- Have a plan for legacy sessions if incompatible changes occur, including requiring users to log in again if necessary.

Redis is a critical operational dependency when using shared sessions. Monitor availability, latency, connection exhaustion, memory, evictions, and replication/failover. Never configure an eviction policy that can unexpectedly evict active sessions.

## 7. Synchronizing Signing Keys and JWKS

All nodes must use the same active signing key set. If node A signs a token with key A while node B serves a JWKS lacking public key A, clients or resource servers may fail token verification depending on which node serves metadata/JWKS requests.

Never generate a new random key pair on every application startup. Use KMS, HSM, a protected keystore, or a key provider capable of supplying the same key set to all nodes. Private keys must never be logged or baked into images/repositories.

Each key has a unique kid. Within the same deployment phase, every node must:

- Receive the same key set and active signing key.
- Publish compatible JWKS.
- Sign new tokens with the key selected per rollout/key policy.
- Retain old public keys long enough to verify still-valid tokens.
- Never delete an old key before token lifetimes, cache windows, and required overlap expire.

### Cluster Rotation Procedure

1. Generate the new key in KMS/HSM.
2. Grant all nodes permission to use the new key.
3. Publish the new public key in JWKS on all nodes.
4. Wait for clients/resource servers to refresh JWKS or for relevant cache TTLs to expire.
5. Switch nodes to sign with the new key in a coordinated change.
6. Verify tokens issued by every node validate successfully.
7. Retain the old key until old tokens expire and the overlap window closes.
8. Remove the old public key as planned and record an audit log entry.

Do not deploy node A signing with a new key while node B still serves the old JWKS if the load balancer may route JWKS requests to node B. One pattern is having all nodes publish both old and new public keys before any node switches to signing with the new key.

## 8. Configuring Load Balancers, Cookies, and Graceful Shutdown

The load balancer needs dedicated health checks and should only add nodes to rotation after the application is ready. Health endpoints should check essential dependencies per policy, while avoiding cluster-wide restart loops when a shared dependency has an outage.

Principles:

- Readiness determines whether a node can receive traffic.
- Liveness only determines whether the process needs restarting.
- During deployment, drain old nodes before stopping the process.
- Allow in-flight requests to finish during graceful shutdown.
- Never wipe shared sessions or authorizations when a node stops.
- Set LB timeouts higher than or compatible with request durations and the shutdown grace period.
- Monitor per-node request distribution and nodes ejected from the pool.

Sticky sessions can reduce node hopping if sessions remain local, but they do not replace shared sessions in an HA design. If sticky sessions are chosen temporarily for compatibility, document the impact of node failures and how users resume sessions.

### Cookie Configuration

Session cookies must be returned from the public domain and sent by the browser along the expected flow. Verify:

- Secure is enabled over HTTPS.
- HttpOnly is enabled so JavaScript cannot read the session cookie.
- Domain and Path are scoped appropriately to the Authorization Server.
- SameSite is compatible with redirects and response modes.
- Cookies are not overwritten or stripped by the proxy.
- All nodes use the same session cookie name and signing/encryption config if applicable.

Do not use a broad cookie domain like .example.com unless sharing cookies across subdomains is required. Broad cookie sharing widens blast radius if any subdomain is compromised.

## 9. Ensuring Node Configuration Parity

A cluster needs more than the same issuer and database. Every node must run compatible configuration:

| Item | Parity Requirement |
|---|---|
| Application release | Same version or rolling-deployment compatible version |
| Issuer and endpoint settings | Identical public values |
| RegisteredClient policy | Read from the same data source or version |
| Security filter chains | Consistent matchers, CSRF, login, consent, and endpoint policies |
| Signing key set | Same public key set and active key policy |
| Token settings/customizers | Consistent claims, lifetimes, audience, and token formats |
| Database schema | Version compatible with all running nodes |
| Session cookies | Consistent Name, Secure, HttpOnly, SameSite, Path, and namespace |
| Time | NTP synchronized; clock drift within allowed tolerance |
| Trust store/TLS | Required CAs and trust policies aligned |

Secrets do not have to be identical if they are node-specific credentials, but their permissions and roles must be equivalent. For signing keys, nodes must use the same key set or the same signing service so tokens verify across the entire cluster.

Clock skew can cause tokens to be treated as not yet valid or already expired. Synchronize clocks across nodes, databases, and dependent systems. Do not overly inflate clock skew allowances to mask NTP drift.

## 10. Multi-Instance Deployment and Rollout

A safe rollout requires compatibility across database, session serialization, issuer, and key sets.

Reference procedure:

1. Build the image once and use the exact same artifact for all nodes.
2. Verify config, secret references, KMS permissions, and network policies.
3. Run backward-compatible database migrations before rollout if needed.
4. Ensure the new key set is distributed and JWKS has overlap.
5. Start the new node, wait for readiness, and query metadata/JWKS through that node.
6. Run login and token smoke tests using a test client.
7. Add the new node to the LB, then drain one old node.
8. Verify sessions are read on the new node and authorizations are read/exchanged from another node.
9. Monitor token errors, login failures, DB pool, Redis latency, and KMS errors.
10. Complete rollout or roll back based on predefined criteria.

### Expand-and-Contract for Schemas

When changing the database schema:

- Add new columns/tables in a way old code can still run.
- Deploy code capable of reading/writing the compatible schema during transition.
- Backfill and verify data.
- Shift all traffic to the new code.
- Drop the old schema only in a subsequent release once no old nodes remain.

Never run destructive migrations while old nodes still depend on that schema. Migrations must have backups, expected lock durations, and a rollback plan.

### Graceful Shutdown

Enable graceful shutdown in Spring Boot and configure LB draining. Never abruptly terminate a node while it is handling a token request or consent submission. If an in-flight request fails to complete before the deadline, the client may retry; authorization code/token semantics must still prevent issuing tokens twice.

## 11. Multi-Instance Integration Testing

Calling each node independently and seeing HTTP 200 is not enough. You must test state crossing between nodes.

### Testing Metadata on Both Nodes

Call each node directly from an internal test network and through the LB domain:

- issuer must be identical.
- Authorization/token/JWKS endpoints must use the public domain.
- JWKS must contain the same key set outside rotation windows.
- Location headers must never leak internal hosts.
- Neither node may return HTTP URLs in redirects when the original request is HTTPS.

### Testing Login Starting on A and Continuing on B

1. Send the browser to the authorization endpoint and force the first request onto node A.
2. Node A creates a session and redirects the user to login/consent.
3. Send the next request to node B with the same session cookie.
4. Node B must receive the required SecurityContext/session.
5. Complete consent and redirect to the exact registered URI.

If tests run behind sticky sessions, explicitly disable affinity in the test environment or hit node B directly to verify shared sessions. If the architecture accepts session loss on node failure, explicitly document that users must log in again and test that fallback safely.

### Testing Code Issued on A, Exchanged on B

1. Send the authorization request via node A.
2. Complete login/consent and obtain the authorization code.
3. Send the token request via node B.
4. Verify the issued token and valid claims/issuer.
5. Replay the same code via node A or B.
6. Verify the replay is rejected and no new token is issued.

This is the key test proving shared OAuth2AuthorizationService. Also run two concurrent requests exchanging the same code against two nodes to verify only one succeeds per authorization code semantics. Inspect database transaction/locking behavior for your exact version and configuration; do not rely solely on single-threaded tests.

### Testing Tokens and JWKS Across Nodes

- Obtain a token from node A and verify it using JWKS fetched through the load balancer.
- Obtain a token from node B and verify it using the same JWKS.
- Force JWKS requests to each node and verify both public key sets are compatible.
- Decode iss, aud, exp, scope, and kid claims per profile; verify signatures using a trusted library.
- During key rotation, verify both old and new tokens validate during the overlap window.

Do not merely decode a JWT and inspect its payload. You must verify signature, issuer, audience, and expiration.

### Failover Testing

| Test | How to Execute | Expected Result |
|---|---|---|
| Node A stops | Drain and terminate A | LB shifts traffic to B; sessions continue working with shared Redis |
| Node B stops | Drain and terminate B | A continues serving |
| Redis failover | Switch Redis primary or simulate interruption | Sessions continue or fail per policy; no forged auth state created |
| PostgreSQL failover | Simulate failover in staging | Nodes recover connections; failed requests handled safely |
| Temporary KMS failure | Deny key operations in test | No tokens minted with unknown keys; alerts fire |
| Proxy header spoofing | Send forged Host/Forwarded/X-Forwarded headers | Public URLs and issuer remain valid; backend distrusts direct sources |
| Rolling deploy | Replace nodes step by step | Sessions, schema, and JWKS remain compatible during transition |

Never run failover or kill nodes in production without an approved drill plan and scope. This lab uses isolated local/staging environments with synthetic data.

## 12. Testing Forwarded Headers and Host Spoofing

Send a request to the public domain with forged headers:

~~~bash
curl -i \
  -H 'Forwarded: host=attacker.example;proto=http' \
  -H 'X-Forwarded-Host: attacker.example' \
  -H 'X-Forwarded-Proto: http' \
  https://auth.example.test/.well-known/openid-configuration
~~~

The edge proxy must strip or overwrite client-sent values. Metadata and redirects must still use the valid issuer/domain. If attacker.example or http:// appears in server-generated URLs, check:

- Host allowlist on ingress.
- Stripping/rewriting rules for Forwarded and X-Forwarded-*.
- Backend network access controls.
- forward-headers-strategy.
- Filter ordering and duplicate filter registrations.
- Explicit issuer configuration.

Also test direct access to the backend from an unauthorized network. Requests must be blocked by firewall/security group/network policy. This is a network check; MockMvc cannot prove it.

## 13. Cluster Observability and Alerting

Monitor per node and cluster-wide:

- Request rate, latency, and error rate by endpoint.
- Login/consent successes and failures.
- invalid_client, invalid_grant, token issuance, and refresh failures.
- HikariCP active/idle/pending connections, timeouts, and query latency.
- Redis latency, connections, memory, evictions, and failover.
- KMS request latency, errors, and permission denials.
- JVM memory, CPU, thread pools, GC, and restart counts.
- Load balancer healthy/unhealthy targets, connection draining, and traffic distribution.
- Issuer/JWKS key versions published per node.
- Clock drift and health probe failures.

Logs should include correlation ID, node ID, endpoint category, and outcome. Never log access tokens, refresh tokens, authorization codes, client secrets, cookies, private keys, or device/user codes. Do not put usernames or tokens into metric labels due to cardinality and privacy risks.

An alert should indicate blast radius: one node vs. the whole cluster, one dependency vs. all, login vs. token endpoint. That helps on-call isolate issues before draining or rolling back.

## 14. Common Incident Troubleshooting

| Symptom | Possible Cause | Evidence to Inspect | Resolution |
|---|---|---|---|
| Issuer differs across requests | Issuer derived from request or node config drift | Metadata from each node, config versions | Set issuer explicitly and align rollout |
| Redirects contain HTTP or internal hostnames | Wrong proxy headers or unprocessed headers | Location, forwarded headers, proxy logs | Fix proxy normalization and network boundary |
| Login starts on A but B prompts again | Local sessions or differing Redis namespace/cookies | Cookies, session store, node logs | Enable shared sessions or accept intentional re-authentication |
| Token endpoint on B returns invalid_grant after code from A | Local OAuth storage or different DBs | Datasources, JDBC services, DB rows | Use shared OAuth2AuthorizationService and same schema |
| JWT signed on A fails verify against JWKS from B | Divergent key sets or mismatched kid | JWT headers, JWKS from each node, key inventory | Synchronize key sets and rotate with overlap |
| Some nodes return stale metadata | Config drift or incomplete rollout | Per-node release/config versions | Drain drifted node, finish rollout |
| Consent prompts repeat | Divergent or unshared consent persistence | Consent service and database | Align JDBC store, verify migrations |
| Sessions lost after deploy | Incompatible serialization or changed TTL/cookie | Redis session metadata, release diff | Maintain serialization compatibility or handle re-login safely |
| Token request timeouts | DB pool, locks, Redis/KMS, or thread pool | Metrics, traces, DB/KMS logs | Recover dependency, shed load, tune after root cause |
| Code exchanged twice on two nodes | Race condition/wrong transaction semantics | Concurrent tests, DB isolation, authorization updates | Fix atomic consume/locking and add regression test |

### Triage Procedure

1. Determine whether the failure occurs at login, consent, authorization endpoint, token endpoint, or JWKS.
2. Record correlation ID, timestamp, node ID, and release/config version.
3. Fetch metadata/JWKS through the LB and directly from each node on a test network.
4. Compare issuer, endpoints, active kid, and key sets.
5. Check session cookies and Redis if the failure occurs during login/consent.
6. Check PostgreSQL and OAuth2AuthorizationService if the failure involves codes/tokens/consent.
7. Check forwarded headers and host allowlists if URLs/redirects are wrong.
8. Drain any node with confirmed config/key/schema drift.
9. Run cross-node smoke tests before returning the node to the pool.
10. Document root cause, impact, and regression tests.

Never bulk-delete sessions or authorizations to work around a node issue. Never change the issuer or signing key merely to make one node's metadata temporarily match; such changes can break verification for valid active tokens at clients.

## 15. Capstone Practice

Use an isolated local or staging environment, a test domain, and synthetic data.

### Lab A — Standing Up Two Nodes

1. Run two Spring Authorization Server instances from the same image.
2. Configure the same issuer https://auth.example.test.
3. Configure the same PostgreSQL instance and migrations.
4. Configure the same key set via the key provider.
5. Verify each node returns metadata with the same issuer and endpoints.

**Expected result:** both nodes share the same Authorization Server identity and can issue tokens under shared trust.

### Lab B — Placing Both Nodes Behind a Proxy

1. Configure Nginx/load balancer with the test domain and TLS.
2. Strip/rewrite forwarded headers at the edge proxy.
3. Block direct access to the backends.
4. Enable forward-headers-strategy framework or the chosen native mechanism.
5. Query discovery over the domain and confirm no internal addresses leak.
6. Send spoofed headers and confirm responses are unaffected.

**Expected result:** public URLs always use HTTPS and the allowlisted host.

### Lab C — Sharing Sessions

1. Add compatible Spring Session Redis dependencies.
2. Configure the same Redis endpoint and namespace on both nodes.
3. Start login on A.
4. Send the next request with the same browser cookie to B.
5. Complete login/consent and verify the session.
6. Drain A while the session is active and continue requests via B.

**Expected result:** the browser continues its session across nodes per policy.

### Lab D — Sharing OAuth Authorizations

1. Send an authorization request to A.
2. Obtain the authorization code after login/consent.
3. Send the token request to B.
4. Verify the token and claims.
5. Attempt to replay the code via A.
6. Run two concurrent token requests to A and B with the same code.

**Expected result:** codes are stored in shared persistence and consumed at most once.

### Lab E — Key Synchronization and Failover

1. Obtain tokens from A and B.
2. Verify tokens using JWKS via the LB and each node.
3. Drain/terminate A and verify B keeps serving.
4. Perform key rotation with overlap in the test environment.
5. Verify both old and new tokens during the overlap period.

**Expected result:** failover does not alter the issuer or break token verification.

### Lab F — Writing the Runbook

Document the topology, issuer, proxy rules, database, Redis, key provider, health checks, rollout, rollback, alerts, and triage procedure. Every action must list an owner, command or config path, preconditions, and post-action verification steps.

**Expected result:** an on-call engineer can identify a failing node, drain it, inspect session/OAuth state, and restore service without guessing.

## 16. Production Readiness Checklist

- [ ] All nodes use the same public issuer and endpoint settings.
- [ ] Issuer is explicitly configured, never derived from arbitrary Host headers.
- [ ] Edge proxy strips/rewrites forwarded headers and enforces a host allowlist.
- [ ] Backends accept traffic only from the trusted proxy.
- [ ] Only one forwarded-header processing mechanism is enabled.
- [ ] All nodes share RegisteredClient, OAuth2Authorization, and consent stores.
- [ ] HTTP sessions are shared if login/consent must span multiple nodes.
- [ ] Session cookies have Secure, HttpOnly, and appropriate SameSite settings.
- [ ] Redis has ACLs, network isolation, TTLs, and a failover plan.
- [ ] Every node uses the same signing key set and compatible JWKS.
- [ ] Key rotation uses overlap; old keys are never deleted while tokens remain valid.
- [ ] Database migrations are compatible with rolling deployments.
- [ ] Load balancer has readiness, health checks, and graceful draining.
- [ ] Clocks are synchronized.
- [ ] Cross-node login, consent, and authorization code exchange are tested.
- [ ] Concurrent authorization code redemption succeeds only once.
- [ ] Tokens from every node verify against public JWKS.
- [ ] Forwarded header spoofing and direct backend access are tested.
- [ ] Metrics/logs/audits carry correlation IDs without exposing credentials.
- [ ] Failover, key rotation, rollback, and incident triage runbooks have been rehearsed.

Multi-instance deployment succeeds when nodes are compatible replicas of a single Authorization Server: same issuer, same client policies, same authorization data, same key trust, and same interpretation of external requests. The reverse proxy establishes the trust boundary, the database holds OAuth state, shared sessions preserve login state, and the key manager maintains signature continuity. Once cross-node and failover tests pass, the system can scale or replace nodes without clients ever seeing a different Authorization Server.

## References

- Spring Authorization Server — Configuration Model: https://docs.spring.io/spring-authorization-server/reference/configuration-model.html
- Spring Authorization Server — Core Model: https://docs.spring.io/spring-authorization-server/reference/core-model-components.html
- Spring Boot — Forwarded Headers: https://docs.spring.io/spring-boot/reference/howto/webserver.html
- Spring Framework — ForwardedHeaderFilter: https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html
- Spring Session — Redis: https://docs.spring.io/spring-session/reference/guides/boot-redis.html
- RFC 7239 — Forwarded HTTP Extension: https://datatracker.ietf.org/doc/html/rfc7239
- RFC 8414 — OAuth 2.0 Authorization Server Metadata: https://datatracker.ietf.org/doc/html/rfc8414
- RFC 7517 — JSON Web Key (JWK): https://datatracker.ietf.org/doc/html/rfc7517
