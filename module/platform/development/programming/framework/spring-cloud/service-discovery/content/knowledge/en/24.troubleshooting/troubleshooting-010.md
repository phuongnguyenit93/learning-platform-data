# DNS, NAT, TLS, Authentication, and Time Sync Failures

Service discovery may return a valid instance yet the consumer still fails to call the service. The cause usually falls into one of five groups: misconfigured DNS resolution, an advertised address that cannot traverse NAT/routing, TLS certificate verification failures, registry authentication/authorization rejections, or clock skew across machines.

When troubleshooting in Spring Cloud Service Discovery, distinguish the **registry address** from the **advertised instance address**. Providers use the first to register; consumers use the second to send business requests. A DNS error on the registry endpoint can prevent registration, while a NAT error on the advertised endpoint can allow registration to succeed while all requests time out.

This lesson belongs to the SPRING_CLOUD_SERVICE_DISCOVERY module, focusing on diagnosing Eureka, Consul, ZooKeeper, and Kubernetes from the perspectives of provider, consumer, registry, and health checker. The steps below move from lower network layers up to security and time synchronization to isolate root causes using evidence.

## 1. Identify Symptoms Before Changing Configuration

Do not start by renaming hostnames, disabling TLS, or opening firewalls broadly. First, classify the error by observed symptoms:

| Symptom | First layer to inspect | Common signs |
|---|---|---|
| Provider cannot reach registry | DNS, routing, TCP | `UnknownHostException`, timeouts, `Connection refused`. |
| Provider registers, yet consumer cannot call it | Advertised host, NAT, port, firewall | Registry has a record, yet requests time out or fail with connection refused. |
| HTTPS fails to connect | TLS, certificate, SNI, truststore | `SSLHandshakeException`, `PKIX path building failed`, hostname mismatch. |
| Registry returns `401` | Authentication | Missing or invalid credentials/token. |
| Registry returns `403` | Authorization/ACL/RBAC | Reached the server, yet the identity lacks operation permissions. |
| Token or certificate suddenly becomes invalid | Time synchronization | `not yet valid`, `expired`, JWT `nbf`/`exp`, Kerberos clock skew. |
| Health check fails while provider traffic works | Health checker network path | Agent/kubelet cannot reach the advertised health URL. |
| Failures vary by subnet or zone | DNS view, routing, NAT, firewall | One consumer group succeeds while another times out. |

An `UnknownHostException` is not yet an ACL problem. A `403` error usually indicates DNS, TCP, and HTTP already reached the server; at that point, inspect permissions rather than altering DNS. Separating layers prevents editing the wrong component and introducing new risks.

## 2. Distinguishing Addresses in Service Discovery

A system typically has at least three types of addresses:

1. **Registry endpoint:** the address providers/consumers use to connect to Eureka, Consul, ZooKeeper, or the Kubernetes API.
2. **Advertised service endpoint:** the hostname/IP and port the provider registers for consumers to call.
3. **Health-check endpoint:** the address and path used by the Consul agent, kubelet, or monitoring system to check the service.

Example:

```yaml
spring:
  application:
    name: payment-service
  cloud:
    consul:
      host: consul.internal.example
      port: 8500
      discovery:
        hostname: payment-01.apps.internal.example
        port: 8080
        health-check-path: /actuator/health
```

In this example, `consul.internal.example:8500` is the registry endpoint; `payment-01.apps.internal.example:8080` is the advertised service endpoint; the health checker calls `/actuator/health` on the registered endpoint as configured by the Consul integration.

Opening a firewall to Consul does not automatically let consumers reach the payment service. Similarly, a provider successfully calling `localhost:8080` on itself does not prove consumers in another subnet can reach the advertised hostname.

## 3. Diagnosing DNS and Domain Names

### 3.1. Testing from the Right Network Vantage Point

DNS can return different answers depending on private zones, search domains, resolvers, VPNs, or namespaces. Run checks directly from the provider, consumer, and health checker.

Linux:

```bash
getent hosts consul.internal.example
getent ahosts payment-01.apps.internal.example
nslookup payment-01.apps.internal.example
dig payment-01.apps.internal.example A
dig payment-01.apps.internal.example AAAA
```

Windows PowerShell:

```powershell
Resolve-DnsName consul.internal.example
Resolve-DnsName payment-01.apps.internal.example
Test-NetConnection payment-01.apps.internal.example -Port 8080
```

Compare A records, AAAA records, and the address the application actually picks. If DNS returns both IPv4 and IPv6 while only one has a valid route, clients may fail intermittently depending on address selection order and fallback behavior.

### 3.2. Private DNS and Split-Horizon DNS

Split-horizon DNS returns different answers depending on the querying network. For example:

- A provider in VPC A resolves `payment.internal.example` to a private IP in subnet A.
- A consumer in VPC B queries the same name yet gets an old IP or an IP routable only from VPC A.
- A laptop over VPN uses a public resolver instead of the private DNS zone.
- A container uses a different DNS resolver than its host.

How to handle:

- Identify which resolver the process actually uses.
- Check whether the private hosted zone is associated with the right VPC/network.
- Check DNS forwarding across VPCs, subnets, or clusters.
- Use explicit FQDNs with namespace/domain rather than relying on fragile search suffixes.
- Ensure every consumer needing to call the instance receives a routable address.

Do not fix split-horizon issues by hardcoding IPs in source code. IPs can change during rollouts, failovers, or subnet changes.

### 3.3. DNS Caching and Stale Records

Even after the DNS server updates a record, the JVM, OS resolver, sidecar proxy, or HTTP client may still hold old results. Cache duration depends on TTL, runtime, and specific configuration.

Check:

- The record's TTL on the DNS server.
- DNS caching in the OS/container runtime.
- The JVM's active DNS caching policy.
- DNS caches in proxies/service meshes and HTTP clients.
- Connection pools holding open TCP connections to the old address.

Do not assume a DNS change immediately closes existing connections. When testing, issue fresh requests after cache expiration or initialize a fresh client to separate DNS issues from connection reuse.

### 3.4. Checking Service Names in Kubernetes

In Kubernetes, Services typically resolve in the form:

```text
service-name.namespace.svc.cluster-domain
```

For example, `payment-service.commerce.svc.cluster.local`. `cluster.local` is common, though clusters may use another domain. Pods in different namespaces should use namespaced names/FQDNs to avoid misresolution via search paths.

Verification commands:

```bash
kubectl get svc payment-service -n commerce
kubectl get endpoints payment-service -n commerce
kubectl get endpointslices -n commerce -l kubernetes.io/service-name=payment-service
```

If DNS resolves the ClusterIP yet requests time out, inspect Service port, targetPort, endpoint readiness, CNI, and NetworkPolicy. Successful DNS only proves the name resolved, not that the backend receives traffic.

## 4. NAT, Routing, and Advertised Addresses

### 4.1. Bind Address Differs from Advertised Address

A server may bind to `0.0.0.0:8080` while needing to advertise a distinct hostname/IP for consumers to connect. `0.0.0.0` is a wildcard address for listening; it is not a valid destination address to register for consumers. `127.0.0.1` and `localhost` refer only to the caller's own network namespace.

Broken example:

```yaml
eureka:
  instance:
    hostname: localhost
```

The provider may register successfully, yet consumers receive `localhost` and connect to themselves. A valid configuration must advertise a DNS name or IP reachable by all authorized consumers.

### 4.2. Understanding Paths Through NAT

A request crossing NAT can traverse these hops:

```text
Consumer private IP
    -> route / VPN / peering
    -> NAT or load balancer
    -> provider private/public IP
    -> service port
```

Distinguish:

- **SNAT:** rewrites the packet's source IP.
- **DNAT:** rewrites the destination IP/port.
- **Port mapping:** maps an external port to a container or VM port.
- **Hairpin NAT:** an internal client accesses a public address and loops back to an internal backend.
- **Asymmetric routing:** outbound and return paths traverse different routes/firewalls.

A public address may be reachable from the Internet yet unreachable from an internal subnet if hairpin NAT is unsupported. Conversely, a private IP in the registry may be reachable within the same VPC yet unreachable from a consumer in another VPC without peering/VPN/routes.

### 4.3. Checking Ports and Listeners

Linux:

```bash
ss -lntp
ip route get 10.20.5.21
nc -vz payment-01.apps.internal.example 8080
```

Windows:

```powershell
Get-NetTCPConnection -State Listen
Test-NetConnection payment-01.apps.internal.example -Port 8080
```

Inspect the provider to confirm the process listens on the right interface and port. If bound only to `127.0.0.1`, requests from other machines cannot enter even with firewalls open. If a container listens on port `8080` while the host publishes port `18080`, the registry must advertise the endpoint consumers actually use per the network topology.

### 4.4. Configuring Advertised Addresses per Registry

| Technology | Registry endpoint | Instance info to verify |
|---|---|---|
| Eureka | `eureka.client.service-url.defaultZone` | `eureka.instance.hostname`, `ip-address`, `prefer-ip-address`, port. |
| Consul | `spring.cloud.consul.host` and `port` | `spring.cloud.consul.discovery.hostname`, `ip-address`, `port`, `prefer-ip-address`. |
| ZooKeeper | `spring.cloud.zookeeper.connect-string` | `spring.cloud.zookeeper.discovery.instance-host`, `instance-port`, `prefer-ip-address`. |
| Kubernetes | Kubernetes API endpoint | Service DNS/ClusterIP, Pod IP, port, and namespace per request path. |

Eureka example advertising an IP reachable by consumers:

```yaml
eureka:
  client:
    service-url:
      defaultZone: https://eureka.internal.example:8761/eureka/
  instance:
    prefer-ip-address: true
    ip-address: 10.20.5.21
    non-secure-port: 8080
```

Consul example advertising a hostname:

```yaml
spring:
  cloud:
    consul:
      host: consul.internal.example
      port: 8500
      discovery:
        hostname: payment-01.apps.internal.example
        prefer-ip-address: false
        port: 8080
```

Verify exact property names and host/IP preference behavior for your Spring Cloud version. After updating configuration, read back the record in the registry and `ServiceInstance` on the consumer. Do not inspect only the provider's environment variables.

### 4.5. Symptoms of NAT and Routing Errors

| Symptom | Possible cause | Check |
|---|---|---|
| Registry has record, yet TCP times out | Advertised private IP is not routable from consumer. | Route tables, VPN/peering, firewalls, flow logs. |
| Provider calls localhost fine, yet consumer fails | App binds only to loopback or advertises loopback. | `ss -lntp`, `getHost()`, `getUri()`. |
| Works within subnet, fails across VPCs | Missing route/peering or security group. | Bidirectional routes, SG/NACL, NAT. |
| Public works, internal times out | Hairpin NAT or split DNS misconfigured. | Compare internal vs. public DNS, test private endpoint. |
| One-way connect works, response times out | Asymmetric routing or NACL blocks ephemeral return ports. | Flow logs, firewall state, return route. |
| Container port right, host port wrong | Docker/Kubernetes port mapping mismatch. | Container port, Service port, targetPort, published port. |

## 5. TLS, Certificates, SNI, and mTLS

### 5.1. Separating TLS Errors from Network Errors

TLS starts only after a TCP connection is established. Therefore, the diagnostic order is:

1. Does DNS resolve accurately?
2. Does TCP connect to the right IP/port?
3. Does the server return a TLS handshake?
4. Does the client trust the certificate chain?
5. Is the certificate valid for the hostname and current time?
6. If using mTLS, can the server verify the client certificate?

Common errors:

- `PKIX path building failed`: client cannot build a trust chain to a trusted CA.
- `No subject alternative DNS name matching ...`: hostname does not match any SAN in the certificate.
- `certificate has expired` or `not yet valid`: certificate validity window fails against the client's clock.
- `handshake_failure` or `bad_certificate`: may be mismatched protocol/cipher, missing client certificate, or server rejecting certificate.
- Connecting by IP instead of hostname causing SNI or SAN mismatch.

### 5.2. SAN and SNI

The certificate must include a Subject Alternative Name matching the name the client uses. If a consumer connects to `https://payment.internal.example:8443`, the certificate must have DNS SAN `payment.internal.example`. If connecting via an IP literal, the certificate needs the corresponding IP SAN.

SNI allows the client to send the intended hostname during the TLS handshake so a reverse proxy/server selects the right certificate. If calling by IP or if a proxy rewrites the hostname, the server may serve a non-matching default certificate.

Test:

```bash
openssl s_client \
  -connect payment.internal.example:8443 \
  -servername payment.internal.example \
  -showcerts
```

Test HTTP with the issued CA:

```bash
curl --verbose \
  --cacert /etc/ssl/certs/internal-ca.pem \
  https://payment.internal.example:8443/actuator/health
```

Do not use `curl -k` or disable hostname verification as a production fix. Those flags skip server identity verification and mask real certificate errors.

### 5.3. Truststore and Keystore

| Component | Contains | Used for |
|---|---|---|
| Truststore | CAs or certificates the client trusts. | Verifying the registry/provider certificate. |
| Keystore | The application's own private key and certificate. | Presenting server or client identity in mTLS. |

In mTLS, the client needs a keystore holding the client's certificate/private key, as well as a truststore to verify the server. Configuring only a truststore gives the client no identity for the server to authenticate.

Inspect keystore/truststore contents:

```bash
keytool -list -v -keystore client-truststore.p12
keytool -list -v -keystore payment-client-keystore.p12
```

Never print or share private keys, keystore passwords, or secrets in logs. Use a secret manager or secret volume with least-privilege read access.

### 5.4. Checking Certificate Chain and Validity Period

Using OpenSSL:

```bash
openssl s_client \
  -connect eureka.internal.example:8761 \
  -servername eureka.internal.example \
  -verify_return_error
```

Inspect a saved certificate:

```bash
openssl x509 -in server.crt -noout -subject -issuer -dates -ext subjectAltName
```

Check:

- Is the issuer in a CA trusted by the client?
- Is the certificate currently valid?
- Does the SAN match the advertised hostname/IP?
- Does the server send the complete intermediate CA chain?
- Is a proxy/load balancer terminating TLS and serving a different certificate?
- Are client/server clocks skewed such that the certificate appears not yet valid or expired?

### 5.5. Debugging TLS in Java

When you need to pinpoint a handshake failure, you can temporarily enable debug logging in a test environment:

```text
-Djavax.net.debug=ssl,handshake,trustmanager
```

Logs can become huge and include certificate/connection details. Enable only during diagnostics, restrict log read permissions, and turn it off once done. Do not enable broadly on production traffic without assessing impact.

## 6. Registry Authentication and Authorization

Being able to reach the registry does not mean the client is authorized to act. Distinguish authentication (verifying identity) from authorization (checking permissions).

### 6.1. Identifying Error Codes

| Result | Common meaning | Inspection direction |
|---|---|---|
| DNS lookup failure | Cannot find server address. | DNS zone, resolver, hostname. |
| TCP timeout | Cannot establish connection or replies dropped. | Routes, firewalls, NAT, listeners. |
| Connection refused | Reached host, yet port has no listener or rejected connection. | Service status, bind address, port mapping. |
| TLS handshake failure | TCP connected, yet verification/encryption failed. | CA, SAN, SNI, protocol, mTLS, clock. |
| HTTP 401 | Missing/wrong credentials or token. | Username/password, token, secret rotation. |
| HTTP 403 | Identity recognized, yet lacks permission. | Roles, ACL policies, RBAC, HTTP methods. |
| HTTP 404 | Wrong path/service ID or resource missing. | Context path, API version, service name. |

Some servers return `404` instead of `403` to conceal resources; read server logs and security configuration rather than inferring solely from status codes.

### 6.2. Eureka

Eureka Server can be protected with Spring Security. Eureka Clients need valid credentials if the server enables HTTP Basic or another authentication scheme. Inspect the URL in `eureka.client.service-url.defaultZone`, scheme, context path, and injected secrets.

Configuration example without embedding credentials directly:

```yaml
eureka:
  client:
    service-url:
      defaultZone: ${EUREKA_SERVER_URL}
```

Secret `EUREKA_SERVER_URL` is supplied by a secret manager or runtime environment variable. Avoid committing URLs containing user-info to Git or printing full URLs to logs.

When Spring Security is enabled, check CSRF matchers for the HTTP methods Eureka Clients use to register/renew/deregister. Do not disable CSRF across the entire application just so clients can register; configure narrow exemptions only for required API paths per your security design.

### 6.3. Consul ACLs

Consul uses ACL tokens and policies to restrict service registration, catalog reads, health queries, or agent operations. Tokens should be separated by role:

- Provider: permissions only to register/update services it owns plus required health/agent integration permissions.
- Consumer: permissions only to read catalog/health of permitted services.
- Monitoring: permissions only to query required metrics/status.
- Operator: administrative permissions under dedicated procedures.

Verify the token in the secret store and its policy permissions. `401` can mean the token was omitted or invalid; `403` usually means the token is valid yet lacks policy permissions. Exact responses depend on the endpoint and ACL configuration.

Do not use a management token across all providers/consumers. When rotating tokens, update the secret and confirm clients picked up the new credentials before revoking the old token per procedure.

### 6.4. ZooKeeper Authentication and ACLs

ZooKeeper separates authentication schemes from znode ACLs. A client can connect to the ensemble yet still receive `NoAuth` when reading/writing registration paths.

Check:

- Does the client use the right SASL/digest/x509 identity?
- Does that identity have the right `CREATE`, `READ`, `WRITE`, `DELETE`, or `ADMIN` permissions?
- Do both the root path and child nodes have proper ACLs?
- Can providers create ephemeral znodes and can consumers read payloads?
- Do chroot/root paths match between provider and consumer?

Never grant write permissions to `world:anyone` in production. Updating ACLs must account for existing nodes, as updating client configuration does not automatically fix ACLs on pre-existing znodes.

### 6.5. Kubernetes RBAC and ServiceAccounts

Spring Cloud Kubernetes DiscoveryClient calls the Kubernetes API using the workload's identity, typically a ServiceAccount. `Forbidden` errors usually trace back to Roles/ClusterRoles or namespace scope.

Verify identity and permissions:

```bash
kubectl auth can-i list services \
  --as=system:serviceaccount:commerce:payment-consumer \
  -n commerce

kubectl auth can-i watch endpointslices.discovery.k8s.io \
  --as=system:serviceaccount:commerce:payment-consumer \
  -n commerce
```

Exact resources and verbs depend on your Spring Cloud Kubernetes version and implementation. Grant least privilege in the required namespaces; never grant `cluster-admin` to a service account merely to fix discovery.

## 7. Time Synchronization and Clock Skew

### 7.1. Distinguishing Timezone from Clock Skew

Timezones only affect how time is displayed. Two machines can use different timezones yet represent the exact same UTC instant. Clock skew is when actual clocks across machines drift apart.

For example, logs on one machine show 10:00 UTC+7 and another shows 03:00 UTC; they may be perfectly synchronized. Yet if both display UTC and differ by several minutes, investigate NTP/time synchronization.

Using UTC in logs and telemetry makes correlating events across provider, registry, and consumer straightforward. Do not change timezones to fix clock skew.

### 7.2. Impact of Clock Skew

Skewed clocks can cause:

- TLS certificates rejected as `not yet valid` or `expired`.
- JWT/OAuth tokens rejected due to `nbf` (not before) or `exp` (expiration).
- Kerberos authentication failures from exceeding allowed clock skew.
- Logs across provider, registry, and consumer appearing out of chronological order, complicating investigations.
- Schedulers, retry/backoff timers, or time-based jobs firing unexpectedly early/late.
- Timestamp- or lease-dependent multi-node operations becoming difficult to observe and analyze.

Do not assume every heartbeat/lease failure stems from clock skew. Many registries measure timeouts using the server's or session's internal timers/clocks. Treat clock sync as one check alongside verifying networking, heartbeats, leases, and sessions per registry mechanics.

### 7.3. Checking Time on Linux

```bash
date -u
timedatectl status
chronyc tracking
chronyc sources -v
```

`timedatectl` shows system clock and sync state. `chronyc tracking` shows offset and time source status if using Chrony.

If using another NTP service, check that the service is running and configured with valid time servers. Never run multiple competing NTP services on the same machine.

### 7.4. Checking Time on Windows

```powershell
([DateTime]::UtcNow).ToString("o")
w32tm /query /status
w32tm /query /source
w32tm /stripchart /computer:ntp.internal.example /samples:5 /dataonly
```

In a Windows domain, time sources generally follow the domain controller hierarchy. Use NTP sources per organizational policy rather than switching arbitrarily to an unapproved Internet server.

### 7.5. Time Synchronization in Containers and Kubernetes

Containers typically share the host kernel's clock; changing a timezone inside a container does not fix the host clock. If multiple Pods on one node exhibit the same drift, check the node first. If only one node drifts, compare that node's NTP source and offset.

In multi-node clusters, ensure all control plane nodes, workers, registry servers, VMs, and identity providers use a reliable time source. Monitor offset and alert before hitting operational thresholds for TLS/tokens/Kerberos.

Do not manually step clocks backward/forward on nodes running live workloads without impact analysis. Sudden clock jumps can disrupt logs, schedulers, and wall-clock-sensitive applications.

## 8. Illustrative Configurations for Common Failure Groups

### 8.1. Eureka: Registry URL and Advertised IP

```yaml
eureka:
  client:
    service-url:
      defaultZone: ${EUREKA_SERVER_URL}
  instance:
    prefer-ip-address: true
    ip-address: ${SERVICE_ADVERTISE_IP}
    non-secure-port: 8080
```

`EUREKA_SERVER_URL` points to the registry. `SERVICE_ADVERTISE_IP` must be an IP actually routable from consumers. If using HTTPS or a secure port, configure the corresponding scheme/port and certificates. Do not pick an interface IP that exists only inside the provider's subnet.

### 8.2. Consul: Separating Registry Endpoint and Instance Endpoint

```yaml
spring:
  cloud:
    consul:
      host: ${CONSUL_HOST}
      port: 8501
      scheme: https
      discovery:
        hostname: ${SERVICE_ADVERTISE_HOST}
        port: 8080
        prefer-ip-address: false
```

This example assumes the Consul API is configured with HTTPS on port `8501`. The provider must trust Consul's CA and have an ACL token if ACLs are enabled. `SERVICE_ADVERTISE_HOST` is the hostname consumers call; do not use a hostname resolvable only from the Consul agent if consumers sit on another network.

### 8.3. ZooKeeper: Separating Ensemble and Instance Address

```yaml
spring:
  cloud:
    zookeeper:
      connect-string: ${ZOOKEEPER_CONNECT_STRING}
      discovery:
        root: /services/production
        instance-host: ${SERVICE_ADVERTISE_HOST}
        instance-port: 8080
```

`ZOOKEEPER_CONNECT_STRING` is the ensemble's client endpoint. `instance-host` and `instance-port` are advertised to consumers. If TLS/SASL/ACLs are enabled, configure cluster-appropriate identities and trust; TCP connectivity to `2181` does not prove znode permissions are valid.

## 9. Layer-by-Layer Diagnostic Workflow

When a consumer cannot call a service, proceed in this order and record results at every step:

1. **Fetch registry data:** service ID, instance ID, hostname/IP, port, scheme, status, and metadata.
2. **Identify the test origin:** provider, consumer, health checker, or registry node. Never let an admin laptop represent all nodes.
3. **Test DNS:** resolve both the registry hostname and advertised hostname from the true origin.
4. **Test routing:** confirm routes to destination IP, NAT/peering/VPN, and return path.
5. **Test listener/TCP:** inspect bind address, port, security groups, firewalls, and NetworkPolicy.
6. **Test TLS:** SNI, SAN, CA chain, certificate validity dates, truststore/keystore, and mTLS.
7. **Test authentication:** username/password, ACL token, SASL identity, or ServiceAccount token.
8. **Test authorization:** roles, policies, ACLs, and RBAC for the exact API/resource/method.
9. **Test clock sync:** UTC, NTP source, offset, certificate validity, and token time claims.
10. **Re-test from consumer:** call the endpoint via `ServiceInstance.getUri()` or LoadBalancer and verify provider logs.

### 9.1. Quick Ordered Diagnostic Commands

Linux:

```bash
# DNS
getent hosts eureka.internal.example
getent hosts payment-01.apps.internal.example

# Route and listener
ip route get 10.20.5.21
ss -lntp

# TCP
nc -vz eureka.internal.example 8761
nc -vz payment-01.apps.internal.example 8080

# TLS
openssl s_client -connect eureka.internal.example:8761 \
  -servername eureka.internal.example -verify_return_error

# Time
date -u
timedatectl status
chronyc tracking
```

Windows:

```powershell
Resolve-DnsName eureka.internal.example
Resolve-DnsName payment-01.apps.internal.example
Test-NetConnection eureka.internal.example -Port 8761
Test-NetConnection payment-01.apps.internal.example -Port 8080
([DateTime]::UtcNow).ToString("o")
w32tm /query /status
```

These commands are just starting points. `nc`/`Test-NetConnection` verifies TCP, not TLS or API permissions. `openssl s_client` verifies handshake and certificates but does not prove HTTP-layer authorization. Combine multi-layer checks in the proper order.

## 10. Symptom and Root Cause Matrix

| Symptom | Possible cause | Evidence to collect | Remediation direction |
|---|---|---|---|
| `UnknownHostException` at provider startup | Wrong registry hostname or private DNS unlinked. | Resolver, A/AAAA records, search domain. | Fix DNS view/forwarding and test from provider. |
| Consumer gets host in wrong subnet | Registry stores wrong advertised IP/hostname. | Native record and `ServiceInstance.getHost()`. | Reconfigure advertised address for consumer network. |
| TCP timeout across VPCs | Routing, peering, NAT, SG/NACL, or firewall. | Route tables, flow logs, source/destination IPs. | Fix forward and return paths; scope rules by source/port. |
| TCP connection refused | No listener or wrong port mapping. | `ss -lntp`, container port, Service targetPort. | Fix bind address, port, or mapping. |
| TLS `PKIX path building failed` | Missing CA/intermediate or wrong truststore. | Issuer chain, truststore contents. | Update CA chain/truststore accurately. |
| TLS hostname mismatch | SAN missing advertised hostname/IP or wrong SNI. | Certificate SAN and requested hostname. | Use matching hostname or reissue certificate. |
| Unexpected TLS `not yet valid`/`expired` | Certificate dates or clock skew. | Certificate dates, UTC, NTP offset. | Fix clock sync or reissue certificate if truly expired. |
| Registry returns `401` | Missing or invalid credentials/token. | Auth config, secret version, server auth logs. | Update secret accurately and rotate safely. |
| Registry returns `403`/ZooKeeper `NoAuth` | Valid identity but missing ACL/RBAC. | Policies, roles, znode ACLs, Kubernetes `can-i`. | Grant least privilege for required resources/actions. |
| JWT fails `nbf` or `exp` | Clock skew or expired token. | Claims, issuer clock, client clock. | Sync NTP and issue fresh token. |
| Consul health check critical | Agent cannot reach endpoint or check TLS/auth fails. | Agent logs, health URL, source IP, check output. | Fix route/advertised host/credentials/check config. |
| Eureka registration keeps failing renew | Unstable registry URL, auth, TLS, or network. | Client logs, renew responses, server logs. | Isolate DNS/TCP/TLS/auth before adjusting leases. |
| ZooKeeper session repeatedly drops | Network flap, session timeout, ensemble endpoint, or TLS/SASL. | Curator connection state, server logs, network metrics. | Fix network/session config and authentication. |

## 11. Risky Fixes to Avoid

Avoid the following as long-term fixes:

- Disabling certificate verification or using `curl -k` in production.
- Advertising `localhost`, loopback, or `0.0.0.0` as an instance endpoint.
- Opening entire CIDRs or all ports just to "see if the error goes away."
- Granting Consul management tokens or Kubernetes `cluster-admin` to every service.
- Disabling ZooKeeper ACLs or giving `world:anyone` write permissions.
- Putting passwords, ACL tokens, private keys, or credentialed URLs into Git/logs.
- Raising lease/session timeouts without proving timeouts caused the failure.
- Swapping IPs to a public address without checking internal routes and hairpin NAT.
- Stepping clocks manually on production nodes without a proper time synchronization procedure.
- Testing only from the provider's localhost and assuming consumers can reach it.

Keep every change scoped to the exact source, destination, identity, and port required. After fixing, re-verify registration, health checks, and business requests.

## 12. Production Incident Runbook

When a service discovery alert fires, responders can follow this runbook:

**Step 1 — Record data**

- Timestamp in UTC.
- Affected provider, consumer, registry node, and zone/subnet.
- Service ID, instance ID, advertised hostname/IP, port, and scheme.
- Error codes, exception chains, and correlation IDs.
- Recent changes to DNS, NAT, certificates, ACL/RBAC, or NTP.

**Step 2 — Determine scope**

- One instance or all instances?
- One consumer subnet or all consumers?
- Only provider → registry or also consumer → provider?
- Does the health checker hit the same error as consumers?
- Does only HTTPS fail or HTTP as well?

**Step 3 — Test from the right origin**

- DNS lookup from provider, consumer, and checker.
- TCP connect to registry and advertised endpoint.
- TLS handshake with the right SNI.
- Authentication/authorization using the workload's actual credentials.
- Clock offset across the involved nodes.

**Step 4 — Apply controlled fixes**

- Fix records/advertised addresses or routes if misconfigured.
- Update CA/certificate/truststore if TLS is wrong.
- Rotate credentials or refine least-privilege policies if auth fails.
- Restore NTP if clocks drifted.
- Do not modify multiple layers simultaneously before identifying the cause.

**Step 5 — Verify recovery**

- Provider registers/renews successfully.
- Registry stores the right host, port, and status.
- Health checker reports passing/ready.
- Consumer `DiscoveryClient` sees the instance.
- Real requests via LoadBalancer or instance URI succeed.
- Metrics and logs show no recurring errors.

## 13. Prevention Checklist

- Registry hostnames and advertised service hostnames are intentionally managed via private DNS.
- DNS returns A/AAAA records compatible with each consumer group's routes.
- DNS TTLs and caching policies are understood during rollouts or failovers.
- Providers bind to the right interface and advertise consumer-reachable addresses.
- NAT/port mapping, forward routes, and return routes are verified.
- Registry endpoints and service endpoints have distinct firewall rules.
- Certificates include SANs for exact hostnames/IPs; CA chains and SNI are verified.
- Truststores and keystores are managed separately; private keys never reside in source code.
- mTLS client identities are provisioned and rotated under control.
- Eureka credentials, Consul ACL tokens, ZooKeeper identities, and Kubernetes ServiceAccounts follow least privilege.
- Secret rotation includes overlap and confirms clients loaded new secrets before revoking old ones.
- Nodes, container hosts, registries, and identity providers sync via NTP.
- Logs use UTC and include correlation IDs for cross-component tracing.
- Monitoring alerts on DNS failures, connection timeouts, TLS handshakes, auth denials, and clock offsets.
- Runbooks exist for testing from provider, consumer, and health checker perspectives.

## Conclusion

Service discovery failures are often the combined result of multiple dependent layers. DNS determines where names point; NAT and routing determine whether consumers reach the advertised endpoint; TLS verifies identity and encrypts traffic; authentication/authorization governs registry access; time synchronization ensures certificates, tokens, and logs are interpreted consistently.

Separate the registry endpoint from the advertised service endpoint, test from the true network vantage point, and follow the sequence DNS → route/TCP → TLS → authentication → authorization → time. After fixing, re-verify registration, health status, and data-plane requests. This evidence-based workflow addresses root causes directly without weakening security or overexposing networks.

## References

- Spring Cloud Netflix — Eureka Client: https://docs.spring.io/spring-cloud-netflix/reference/spring-cloud-netflix.html
- Spring Cloud Consul — Service Discovery: https://docs.spring.io/spring-cloud-consul/reference/discovery.html
- Spring Cloud Zookeeper — Service Discovery: https://docs.spring.io/spring-cloud-zookeeper/reference/discovery.html
- Kubernetes — DNS for Services and Pods: https://kubernetes.io/docs/concepts/services-networking/dns-pod-service/
- Kubernetes — RBAC: https://kubernetes.io/docs/reference/access-authn-authz/rbac/
- OpenSSL — s_client: https://docs.openssl.org/3.0/man1/openssl-s_client/
- Chrony — chronyc: https://chrony-project.org/doc/4.5/chronyc.html
