# Preventing Rogue Registration and Malicious Service Address Publication

The service registry is the data source that controls routing between microservices. If an unauthorized actor can register a fake service, alter an instance address, or publish malicious metadata, consumers may send requests to an attacker-controlled host, confuse it with a legitimate service, or leak internal data. This is a form of registry poisoning: discovery data is poisoned to redirect traffic.

In Spring Cloud, `DiscoveryClient` and `ServiceRegistry` provide abstractions for lookup and registration; they do not authenticate workload identity on their own. Eureka must be protected at its HTTP API and network layer; Consul requires ACL tokens with least privilege. In both cases, consumers must still validate the endpoints returned by the registry and connect only to addresses within trusted boundaries.

## 1. Threat Model

A registration typically contains a service name, instance ID, hostname/IP, port, scheme, health-check URL, tags, and metadata. Consumers retrieve these fields from the registry to choose an endpoint. If a registrant is unauthenticated or granted overly broad permissions, it can declare false data that still looks syntactically valid.

| Threat | Example | Consequence |
|---|---|---|
| Rogue registration | An actor registers a new instance under the name `payment-service` | Consumers may pick the fake instance and send transaction data to it |
| Service identity spoofing | A workload other than `inventory-service` uses a shared credential to register that name | Loss of ability to distinguish legitimate services from fake workloads |
| Address poisoning | Registering `127.0.0.1`, an admin IP, a cloud metadata IP, or an attacker-controlled hostname | Consumers are redirected to unintended endpoints; may create SSRF |
| Port/scheme poisoning | Advertising an admin port or using HTTP instead of HTTPS | Exposes actuator/admin endpoints or strips TLS protection |
| Metadata/tag poisoning | Registering `trusted`, `zone=prod` tags, or forged metadata | Custom routing/filters may select the wrong instance |
| Fake health check | Endpoint always returns `UP` even though it is not a legitimate service | Malicious instance remains in the passing instance set |
| Unauthorized deregistration | Deleting a real instance or altering its status | Causes disruption or forces traffic onto a fake instance |
| Credential theft | Leaking a Eureka password or Consul ACL token | Attacker uses the real workload's permissions to manipulate the registry |

Do not assume a record with `UP` or `passing` status is a trusted record. A health check proves that the endpoint responds as expected to the configured check; it does not prove that the process belongs to the claimed service identity.

## 2. Defense Layers That Must Work Together

```mermaid
flowchart TD
    A[Workload starts] --> B[Workload identity / secret]
    B --> C[Authentication: TLS, Basic Auth, or ACL token]
    C --> D[Authorization: workload can only register allowed services]
    D --> E[Registry receives registration]
    E --> F[Validate service ID, address, port, and metadata]
    F --> G[Registry / consumer discovery cache]
    G --> H[Consumer checks endpoint and egress policy]
    H --> I[mTLS or TLS verifies target service]
    I --> J[Request reaches the right workload]
```

Defense should be multi-layered:

1. **Authentication:** identify which workload is calling the registry using individual credentials or certificates.
2. **Authorization:** restrict which services that workload can register, update, deregister, or read.
3. **Registration validation:** validate service ID, instance ID, address, port, scheme, and metadata against policy.
4. **Network isolation:** allow only authorized workloads and nodes to access the registry API; never expose management ports to the Internet.
5. **Consumer-side validation:** do not treat hostnames/IPs from the registry as unconditionally trusted connection targets.
6. **Service-to-service identity:** use TLS/mTLS or a service mesh to verify the actual peer when establishing connections.
7. **Audit and detection:** monitor registration changes, credential usage, and anomalous addresses.

## 3. Securing Eureka Server

Spring Cloud Netflix automatically registers the application when the Eureka Client starter is on the classpath. Therefore, an application can act as both a producer (registering itself) and a consumer (reading the registry). If an application only needs lookup, disable registration to reduce the attack surface and prevent accidental registration:

```yaml
eureka:
  client:
    register-with-eureka: false
    fetch-registry: true
```

For Eureka Server, only allow designated application networks to access `/eureka/**`. The dashboard and registry API should not be public. Restrict access at the firewall, security group, ingress, or network policy level before relying on application-level authentication.

### 3.1. Enabling Spring Security for Eureka Server

Add the Spring Security dependency to Eureka Server:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
</dependency>
```

Configure an account for local examples or test environments:

```yaml
spring:
  security:
    user:
      name: ${EUREKA_USERNAME}
      password: ${EUREKA_PASSWORD}
```

Example `SecurityFilterChain` for modern Spring Security:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class EurekaSecurityConfiguration {

    @Bean
    SecurityFilterChain eurekaSecurityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers("/actuator/health").permitAll()
                        .requestMatchers("/eureka/**").authenticated()
                        .anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults())
                .csrf(csrf -> csrf
                        .ignoringRequestMatchers("/eureka/**"))
                .build();
    }
}
```

Eureka clients typically do not carry CSRF tokens on registration/heartbeat requests. Therefore, Spring Cloud Netflix recommends ignoring CSRF for `/eureka/**`. Only ignore CSRF on this registry API; do not disable CSRF across the entire application if the dashboard or other endpoints use cookies/sessions.

The configuration above authenticates every request using HTTP Basic. In a multi-workload system, a shared account only confirms that the caller knows the same credential; it does not restrict `inventory-service` to registering only under the name `inventory-service`. To authorize by service name, each workload needs its own identity and a custom authorization layer checking the principal against the service ID in the registration request. Do not treat a `SecurityFilterChain` with only `.authenticated()` as sufficient control against registry poisoning.

### 3.2. Configuring Eureka Client Authentication to the Server

Spring Cloud Netflix automatically adds HTTP Basic authentication when the `defaultZone` URL contains a username and password:

```yaml
eureka:
  client:
    service-url:
      defaultZone: https://${EUREKA_USERNAME}:${EUREKA_PASSWORD}@eureka.internal:8761/eureka/
```

Inject credentials through a secret manager or environment variables. Special characters in the username/password must be URL-encoded. Avoid printing this URL to logs, exceptions, or Actuator environment endpoints because it embeds credentials.

When client certificate authentication is required, Spring Cloud Netflix supports configuring a key store and trust store:

```yaml
eureka:
  client:
    tls:
      enabled: true
      key-store: ${EUREKA_CLIENT_KEYSTORE}
      key-store-type: PKCS12
      key-store-password: ${EUREKA_CLIENT_KEYSTORE_PASSWORD}
      key-password: ${EUREKA_CLIENT_KEY_PASSWORD}
      trust-store: ${EUREKA_TRUSTSTORE}
      trust-store-type: PKCS12
      trust-store-password: ${EUREKA_TRUSTSTORE_PASSWORD}
```

TLS verifies the server and client certificates to protect the transport channel, and can authenticate workloads at the transport layer if the server is configured to require client certificates. Basic Auth and TLS address different layers; never transmit Basic credentials over plain HTTP.

### 3.3. Securing Peer Replication

In a Eureka cluster, peer replication is the internal communication path between Eureka Servers. The Spring Cloud Netflix documentation notes that replication requests such as `/eureka/peerreplication/**` do not pass through the standard Spring Security filter chain. Therefore, Basic Auth or OAuth2 filters used for client registration do not automatically protect peer replication.

For a multi-peer cluster:

- Restrict peer traffic using private networks, firewalls, and security groups limited strictly to Eureka nodes.
- Use TLS/mTLS for connections between peers.
- If a custom authentication header is needed, configure `ReplicationClientAdditionalFilters` to attach authentication headers to the replication client.
- Test application register/heartbeat and peer-to-peer replication separately; do not infer that peers are protected just because the dashboard requires login.

### 3.4. Eureka Addresses and Metadata

Eureka accepts host, port, health URL, and metadata from clients. These values are supplied by the client; the server does not independently prove that the IP belongs to a workload matching that service name.

Example configuration for a service advertising an HTTPS endpoint:

```yaml
eureka:
  instance:
    non-secure-port-enabled: false
    secure-port-enabled: true
    status-page-url: https://${SERVICE_HOST}/actuator/info
    health-check-url: https://${SERVICE_HOST}/actuator/health
```

Only advertise hostnames belonging to a trusted DNS zone with valid TLS certificates. Never place admin URLs, loopback addresses, metadata IPs, or hosts controlled by external requests into instance metadata.

## 4. Securing Consul with ACLs

Consul ACLs authenticate requests using tokens and enforce permissions per resource. For a new datacenter, set `acl.enabled=true` and `acl.default_policy="deny"` so that every operation must be explicitly permitted by a policy. When enabling ACLs on an active cluster, roll out tokens to servers/agents and workloads in stages; do not switch abruptly to deny before components have appropriate tokens.

Example agent configuration:

```hcl
acl {
  enabled = true
  default_policy = "deny"
}
```

### 4.1. Dedicated Tokens per Workload

A producer `inventory-service` that only needs to register its own service can use this policy:

```hcl
service "inventory-service" {
  policy = "write"
}
```

A consumer `order-service` that only needs to look up `inventory-service` can use:

```hcl
service "inventory-service" {
  policy = "read"
}

node_prefix "" {
  policy = "read"
}
```

`service:write` permits updating registrations for the specified service name; `service:read` permits reading the service; `node:read` may be required to read node/address information via the Health API. Keep rules scoped to specific service names whenever possible. If a consumer needs to read multiple services, expand prefixes only to the exact upstream services the workload is authorized to call.

HashiCorp provides the `builtin/service` templated policy for common service identity use cases. This template grants write/read permissions for the service and node read access; it is convenient when a service both registers and discovers. If a producer only needs to register one service and does not perform discovery, a custom policy `service "inventory-service" { policy = "write" }` is narrower.

Create the token from the policy using the administrative Consul CLI:

```bash
consul acl policy create \
  -name "inventory-register" \
  -rules @inventory-register.hcl

consul acl token create \
  -description "inventory-service registration token" \
  -policy-name "inventory-register"
```

The returned token contains an `AccessorID` and `SecretID`. Store `SecretID` in a secret manager; never commit tokens to repositories, Docker images, or logs.

### 4.2. Configuring Spring Cloud Consul

The producer requires its own registration token:

```yaml
spring:
  application:
    name: inventory-service
  cloud:
    consul:
      host: ${CONSUL_HOST}
      port: ${CONSUL_PORT:8500}
      discovery:
        register: true
        acl-token: ${CONSUL_DISCOVERY_TOKEN}
```

A consumer that only performs lookups and does not need to register itself:

```yaml
spring:
  cloud:
    consul:
      discovery:
        register: false
        acl-token: ${CONSUL_READ_TOKEN}
```

`spring.cloud.consul.discovery.acl-token` is the token for Discovery integration. If the application also uses Consul Config/KV, issue a separate token scoped to `key_prefix` read permissions and configure `spring.cloud.consul.config.acl-token`. Never use a management token as the discovery token across all services.

### 4.3. ACLs Do Not Validate Advertised Addresses

ACL service rules control service names and read/write operations. They are not policies that verify whether `Address`, `Port`, `TaggedAddresses`, or metadata submitted by a workload belong to a valid subnet or host. A valid token with `service:write` for `inventory-service` can still be abused to register a bad address if the credential is stolen.

Therefore, in addition to ACLs:

- Issue distinct tokens per workload and revoke them when workloads are decommissioned.
- Do not let applications use Consul Agent tokens or management tokens.
- Restrict the Agent HTTP API to management/trusted workload networks; do not expose port `8500` to the Internet.
- Enable HTTPS/TLS for the API and verify the server certificate; use client certificates when mutual authentication is required.
- Use network policies/firewalls so only legitimate producers can access the registration API.
- Audit service registration changes and reconcile addresses/ports against deployed infrastructure.

The Consul Agent API can also accept health check/script checks inside registrations. If the HTTP API is reachable remotely, keep `enable_script_checks=false` unless there is a specific requirement with strict safeguards; HashiCorp warns that script checks can create remote code execution risks when the API is exposed.

### 4.4. Consul Service Mesh as a Separate Traffic Verification Layer

Consul ACLs protect operations on the API/catalog. If using the Consul Connect service mesh, mTLS and service intentions can verify service identity when service-to-service traffic passes through proxies. This is an additional data-plane protection layer; enabling ACLs alone does not automatically encrypt or authenticate direct HTTP connections between two applications.

## 5. Validating Addresses and Ports Before Trusting the Registry

Consumers typically obtain `ServiceInstance` objects from `DiscoveryClient` and let the LoadBalancer choose an endpoint. If the registry is poisoned, consumers may call a host registered by an attacker. Therefore, for sensitive services, endpoints should be validated against a per-service-ID policy before sending requests.

Example policy:

| Service ID | Allowed Scheme | Allowed Network/Hostname | Allowed Port |
|---|---|---|---|
| `inventory-service` | `https` | `inventory-*.svc.internal` or specific inventory workload subnet | `8443` |
| `payment-service` | `https` | dedicated payment subnet or payment DNS zone | `9443` |
| `notification-service` | `https` | notification DNS zone | `8443` |

Minimum checks:

1. Is the service ID in the consumer's upstream allowlist?
2. Is the scheme `https` as required by policy?
3. Does the hostname belong to an approved DNS zone or the IP to an approved CIDR?
4. Is the port in the service's allowed port list?
5. Is the instance ID unique and compliant with naming conventions?
6. Do metadata/tags match the expected schema and permitted values?
7. Does the endpoint's TLS certificate verify the expected hostname/service identity?

Do not rely solely on regex checks against IP strings. For hostnames, consider DNS resolution and protect against DNS rebinding; simultaneously apply egress firewalls/network policies so the process cannot connect to loopback, link-local, metadata endpoints, or out-of-scope management networks. In infrastructure using private IPs, the allowlist must target specific workload CIDRs rather than blocking the entire private range.

### 5.1. Example Application-Level ServiceInstance Validation

The example below illustrates a policy checking service ID, HTTPS, port, and hostname suffix before making a request. In production, `allowedHosts` should come from trusted configuration, and DNS/CIDR checks plus egress policies must also be enforced:

```java
import java.net.URI;
import java.util.Set;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.stereotype.Component;

@Component
class ServiceInstancePolicy {

    private static final Set<String> ALLOWED_SERVICES =
            Set.of("inventory-service", "payment-service");

    boolean isAllowed(ServiceInstance instance) {
        if (!ALLOWED_SERVICES.contains(instance.getServiceId())) {
            return false;
        }

        URI uri = instance.getUri();
        if (!"https".equalsIgnoreCase(uri.getScheme())) {
            return false;
        }

        String host = uri.getHost();
        if (host == null || !host.endsWith(".svc.internal")) {
            return false;
        }

        return switch (instance.getServiceId()) {
            case "inventory-service" -> instance.getPort() == 8443;
            case "payment-service" -> instance.getPort() == 9443;
            default -> false;
        };
    }
}
```

This is only a simple consumer-side check. A hostname suffix does not replace DNS verification or TLS certificate validation; an attacker could control DNS if the zone is unprotected. For larger systems, place the policy inside a custom `ServiceInstanceListSupplier` or a shared discovery adapter so all call paths enforce the same rules.

Do not perform checks only in a controller or a single client wrapper if the application has multiple paths calling the same service. Every client using discovery must go through a unified control layer.

## 6. Protecting Metadata, Health Checks, and Management Endpoints

Registry metadata may contain zone, version, weight, tags, status URLs, and health URLs. If a custom LoadBalancer or gateway relies on metadata to select instances, metadata must not be treated as trusted merely because it came from the registry.

Apply these principles:

- Allow only predefined metadata keys; reject arbitrary keys if consumers could execute logic based on them.
- Never use tags like `trusted`, `admin`, `production`, or `internal` as authentication evidence.
- Never put secrets, tokens, passwords, or personal data in metadata.
- Publish only necessary health/status URLs; never advertise admin actuator URLs or endpoints exposing configuration data.
- Health checks must call the right endpoint and verify TLS; a passing status does not replace service identity.
- Protect Actuator with authentication/network policies and expose only required endpoints.

In Eureka, status page and health indicator URLs are stored in metadata. In Consul, health checks may be invoked by the agent against the application. A forged registration can declare a fake health endpoint if caller identity and addresses are not controlled.

## 7. Protecting Registry and Workload Networks

Application-level authentication does not replace network segmentation. The registry is a control plane affecting many consumers, so you must:

- Expose Eureka `/eureka/**` and the Consul HTTP API only to approved workload/management subnets.
- Separate the control plane network from business traffic when infrastructure supports it.
- Use TLS for client-to-registry and peer-to-peer communication; verify certificate chains and hostnames.
- Restrict dashboard/UI access strictly to operations teams.
- Restrict permission to create service registrations from CI/CD runners, developer laptops, and untrusted namespaces.
- Use Kubernetes NetworkPolicy, firewalls, or security groups to limit which producers can reach the registry.
- Never expose the Consul Agent API, Eureka dashboard, or admin endpoints to the public Internet.

If the registry runs in Kubernetes, RBAC must restrict who can create/modify/delete `Services`, `Endpoints`, and `EndpointSlices`. Admission policies can validate label selectors, ports, namespaces, and workload types permitted to publish endpoints. A service account with permission to edit EndpointSlices can alter the endpoints seen by consumers of a Kubernetes Service.

## 8. Detecting Registry Poisoning

Do not log only instance counts. Observe who modified the data and which fields changed.

| Signal | What to Alert On |
|---|---|
| New service name | Service ID not on the approved list |
| Instance ID | Duplicate IDs, unusual changes, or mismatch with workload identity |
| Address | IP outside the service CIDR, loopback, link-local, metadata IP, or hostname outside the DNS zone |
| Port/scheme | Admin port, disallowed port, or HTTP instead of HTTPS |
| Metadata/tags | New tags, unusual zone/version, or keys outside the schema |
| Registration rate | One token/host registering many services or rapidly creating/deleting instances |
| Health status | Unfamiliar instance consistently passing or real instance suddenly turning critical |
| Credential | Token used from an unexpected host/namespace or appearing after rotation/revocation |

With Consul, monitor ACL audit/logs, AccessorID, and response headers indicating ACL-filtered results. With Eureka, monitor registrations/cancellations, instance statuses, addresses, and peer replication. Correlate registry events with orchestrator inventory to reconcile instance IDs, pod/VM identities, and actual IPs.

## 9. Incident Response Procedure When Rogue Registration Is Detected

1. Record the service ID, instance ID, address, port, metadata, creation timestamp, and the registry node that received the registration.
2. Identify the principal/token/certificate that performed the request if auditing is enabled.
3. Compare the record against the orchestrator: pod, VM, deployment, namespace, service account, and image version.
4. Block traffic to the suspicious endpoint using network policy/egress rules; do not wait for registry caches to expire if active exploitation is possible.
5. Deregister or remove the rogue instance from rotation using controlled administrative permissions.
6. Revoke/rotate compromised credentials; review other services that may have been registered with the same token.
7. Inspect consumer caches, LoadBalancer caches, and connection pools to ensure no requests still go to the old endpoint.
8. Inspect logs, traces, and access logs to determine which requests or data may have been redirected.
9. Restore legitimate registrations and verify health and endpoints from the consumer's network.
10. Create alerts and fix the policy/validation gap that allowed the vulnerability.

Do not simply delete the record from the dashboard and close the investigation. If the credential remains valid or consumer caches have not refreshed, the actor may re-register or traffic may keep flowing to the old endpoint.

## 10. Pre-Deployment Security Testing

Execute these tests in a staging environment with mock tokens and services:

1. Send a registration without credentials; confirm it is rejected.
2. Use `inventory-service`'s token to register `payment-service`; confirm ACL/custom authorization rejects it.
3. Use a read-only consumer token to attempt registration and deregistration; confirm it is rejected.
4. Register a loopback address, an out-of-CIDR IP, a hostname outside the DNS zone, and an admin port; confirm validation or egress policy blocks them.
5. Register disallowed tags/metadata; confirm consumers do not use them for privilege escalation or endpoint selection.
6. Use an invalid TLS certificate or mismatched hostname; confirm clients refuse to connect.
7. Attempt to access the registry/dashboard from an unauthorized network; confirm firewall/network policy blocks it.
8. For a Eureka cluster, test peer replication after enabling authentication; confirm peers still sync and the replication endpoint is separately protected.
9. For Consul, test anonymous requests and invalid tokens; confirm default-deny works.
10. Revoke a test token and confirm new requests are rejected; verify rotation does not leak tokens in logs.

Test from both the producer and consumer sides. A rejected registration does not prove that a consumer will reject a forged endpoint if that record already existed or was injected from another source.

## 11. Deployment Checklist

- [ ] Registry API is reachable only from approved networks and workloads.
- [ ] Eureka Server requires authentication; CSRF is ignored only for `/eureka/**`.
- [ ] Eureka Client uses appropriate TLS/Basic Auth or client certificates; secrets are not in Git/logs.
- [ ] Eureka peer replication has dedicated network isolation and authentication/TLS.
- [ ] Workloads register only if genuinely needed; client-only roles disable `register-with-eureka` or `consul.discovery.register`.
- [ ] Consul ACLs are enabled with default policy deny; applications never use management tokens.
- [ ] Each producer has its own token/policy, restricting `service:write` to the exact service name.
- [ ] Consumers have read permissions only for authorized services/nodes.
- [ ] It is understood that `service:write` ACLs do not automatically validate advertised producer addresses/ports.
- [ ] Addresses, ports, schemes, hostnames, instance IDs, and metadata are validated against an allowlist.
- [ ] Consumers have egress policies; no arbitrary connections to loopback, link-local, metadata, or management networks.
- [ ] Target service TLS certificates are verified; mTLS/service identity is used for sensitive services.
- [ ] Health checks are not treated as identity authentication proof.
- [ ] Actuator, dashboards, and status endpoints are protected.
- [ ] Auditing/alerting is enabled for registrations, deregistrations, address changes, and metadata changes.
- [ ] Procedures exist for handling registry poisoning, credential rotation/revocation, and cache invalidation.
- [ ] Tests have covered rogue registration, unauthorized token permissions, malicious endpoints, and out-of-scope network access.

## References

- [Spring Cloud Netflix 5.1.0 — Authenticating with Eureka, Securing Eureka Server and Peer Replication](https://docs.spring.io/spring-cloud-netflix/reference/spring-cloud-netflix.html)
- [Spring Cloud Netflix — Configuration Properties](https://docs.spring.io/spring-cloud-netflix/reference/configprops.html)
- [Spring Cloud Consul 5.1.0 — Service Discovery and Registration](https://docs.spring.io/spring-cloud-consul/reference/discovery.html)
- [Spring Cloud Consul — Common Application Properties (`discovery.acl-token`, `discovery.register`)](https://docs.spring.io/spring-cloud-consul/reference/appendix.html)
- [HashiCorp Consul — ACL Best Practices](https://developer.hashicorp.com/consul/docs/secure/acl/best-practice)
- [HashiCorp Consul — Service Registration Tokens](https://developer.hashicorp.com/consul/docs/secure/acl/token/service)
- [HashiCorp Consul — ACL Rules: Service and Node Resources](https://developer.hashicorp.com/consul/docs/secure/acl/rule)
- [HashiCorp Consul — Agent Service Registration API](https://developer.hashicorp.com/consul/api-docs/agent/service)
- [HashiCorp Consul — Core Security Model](https://developer.hashicorp.com/consul/docs/secure/security-model/core)
- [Kubernetes — RBAC Authorization](https://kubernetes.io/docs/reference/access-authn-authz/rbac/)
- [Kubernetes — Network Policies](https://kubernetes.io/docs/concepts/services-networking/network-policies/)
