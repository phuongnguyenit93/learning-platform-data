# Restricting Network and Access Permissions for Dashboard, API, and Actuator

The service registry and Spring Boot Actuator expose critical information about topology, instance addresses, health status, and operational configuration. If the Dashboard, administrative APIs, or Actuator are open to every network and user, an attacker can harvest internal topology maps, register rogue instances, alter service status, or read sensitive details.

In a Spring Cloud Service Discovery system, each access surface must be protected independently: the **Dashboard** is for operators; the **registry API** is for providers/consumers and administrative tools; and **Actuator** is for health checkers, monitoring, and application operations. These surfaces may share the same process or port, but they should never default to sharing the same access permissions.

## 1. Surfaces That Must Be Protected

| Surface | Example | Accessible Data/Actions | Appropriate Access Group |
|---|---|---|---|
| Eureka Dashboard | Web page at `/` on Eureka Server | Application list, instances, hosts, ports, statuses, and metadata. | SRE/platform operators over the management network. |
| Eureka REST API | `/eureka/**` | Read registry, register, renew, deregister, and update instance status. | Authenticated Eureka clients; admins with elevated permissions. |
| Consul UI | Consul web interface | Catalog, health, nodes, services, and operational info. | Operators issued an appropriate ACL token. |
| Consul HTTP API | `/v1/agent/**`, `/v1/catalog/**`, `/v1/health/**`, and other APIs | Register services, read catalog, query health, and certain admin operations. | Providers/consumers with least-privilege ACLs; admins with dedicated permissions. |
| ZooKeeper admin/management | AdminServer, admin tools, and znode client interface | Znode tree, sessions, ACLs, and ensemble status. | ZooKeeper administrators on the management network. |
| Spring Boot Actuator | `/actuator/health`, `/actuator/info`, `/actuator/prometheus`... | Health, metrics, application info, and operational endpoints. | Health checkers, monitoring, or operators per endpoint. |
| Kubernetes API | API server and Service/Endpoints/EndpointSlices resources | Read or modify resources depending on RBAC. | ServiceAccounts/workloads with least privilege; operators via admin identity. |

Dashboards and APIs typically reveal much more information than ordinary user interfaces. A registry read endpoint can expose hostnames, IPs, ports, versions, and inter-service relationships. A write endpoint can create or alter registrations. Actuator can expose configuration, environment variables, thread dumps, or the ability to alter log levels. Therefore, authorize by purpose rather than granting one shared admin privilege to all components.

## 2. Layered Protection Principles

A secure configuration typically combines multiple layers:

1. **Network segmentation:** allow only required subnets, namespaces, or workloads to reach the Dashboard, APIs, and management ports.
2. **Authentication:** verify the identity of users, providers, consumers, agents, or monitoring scrapers.
3. **Authorization:** restrict read, registration, status-change, metrics-query, and administrative actions.
4. **Encryption:** use TLS/mTLS for network connections; verify certificates on both sides when needed.
5. **Endpoint restriction:** expose only required endpoints; never expose all Actuator endpoints publicly.
6. **Monitoring and auditing:** record accesses, registration operations, ACL changes, and rejected requests.

Firewalls or NetworkPolicies limit where connections can originate, but they do not define what a user inside that network is allowed to do. Conversely, Basic Auth or ACLs do not replace network segmentation. Both are needed when an access surface impacts system topology and operations.

## 3. Separating Networks for Operators, Registry Clients, and Monitoring

Define the allowed source groups for each surface:

| Source | Dashboard | Registry API | Actuator health | Actuator metrics/management |
|---|---|---|---|---|
| Provider instance | Not needed | Only required register/renew/deregister endpoints | Usually no need to call each other | Not needed by default |
| Consumer instance | Not needed | Read/fetch registry permission only if using a registry client | Not needed by default | Not needed by default |
| SRE/platform operator | Yes, via management network | Yes, per administrative role | Yes | Yes, per granted permissions |
| Health checker | No | Only if the check mechanism needs the registry API | Yes, from the right agent/node | Not needed by default |
| Monitoring scraper | No | Not needed by default | May read health if required | Metrics endpoint only |
| Public Internet | No | No | No | No |

For example, place the Dashboard and admin APIs on a private subnet or strictly behind a VPN/bastion. Providers are allowed to connect to the registry API via security group/workload identity; consumers receive read-only permissions. Monitoring scrapers are allowed to access `/actuator/prometheus` from the monitoring namespace. End users never need access to these administrative endpoints.

### 3.1. Registry Port and Management Port

Do not confuse the application port with the management port. For example, a provider can use:

```yaml
server:
  port: 8080

management:
  server:
    port: 9001
```

Port `8080` serves business requests; port `9001` serves Actuator. Firewalls can allow consumers to call `8080`, while `9001` permits only monitoring and operators. Even if sharing the same port, paths and access rights must still be protected at the HTTP layer.

When configuring `management.server.address`, that address must be a real interface in the runtime environment. Never bind the management port to a public interface when access is only needed from a management network. When running in containers, check both the bind address inside the container and external port mappings/Services.

## 4. Securing the Eureka Dashboard and REST API

Eureka Server exposes the Dashboard and REST API on server endpoints. The Dashboard lets operators observe the registry; the API serves Eureka Clients registering, renewing, fetching the registry, and deregistering. A production setup must authenticate callers and restrict network paths to the server.

### 4.1. Enabling Spring Security for Eureka Server

You can add `spring-boot-starter-security` to Eureka Server and configure URL-based permissions. The example below illustrates distinguishing operators from registry clients:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class RegistrySecurityConfiguration {

    @Bean
    SecurityFilterChain registrySecurity(HttpSecurity http) throws Exception {
        http
            .csrf(csrf -> csrf.ignoringRequestMatchers("/eureka/**"))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/eureka/**")
                    .hasAnyRole("REGISTRY_READER", "REGISTRY_CLIENT", "OPS")
                .requestMatchers("/eureka/**")
                    .hasAnyRole("REGISTRY_CLIENT", "OPS")
                .anyRequest().hasRole("OPS")
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
```

In this example:

- Users with the `OPS` role can open the Dashboard and perform administrative operations.
- `REGISTRY_READER` can only perform GET calls on the registry API.
- `REGISTRY_CLIENT` can perform GETs and the API operations required by Eureka Client.
- CSRF is ignored only for `/eureka/**`, because Eureka Client uses HTTP methods such as POST, PUT, and DELETE. Never disable CSRF application-wide just to get client registration working.

This is a Spring Security example for a servlet application. Configure a `UserDetailsService`, LDAP, or identity provider to map accounts to these roles; never use default users or uncontrolled shared accounts. If a custom context path or Eureka path is used, matchers must match the actual path. Re-test Dashboard, register, renew, fetch, and deregister flows after enabling security.

### 4.2. Authenticating Eureka Client

Eureka Client can use HTTP Basic credentials in the `defaultZone` URL. Values must be provided via secrets or environment variables; never commit usernames/passwords to repositories:

```yaml
eureka:
  client:
    service-url:
      defaultZone: ${EUREKA_SERVER_URL}
```

The runtime value of `EUREKA_SERVER_URL` may include user-info in the format supported by Eureka Client, such as `https://user:password@eureka.internal.example:8761/eureka/`. In production, use a secret manager/Kubernetes Secret and restrict secret read permissions. Avoid writing URLs containing credentials into logs, exceptions, or metric labels.

When using HTTPS, configure a truststore so the client verifies Eureka Server's certificate. When mTLS is required, configure the appropriate client certificate and private key. Never use HTTP Basic over unencrypted connections on untrusted subnets.

### 4.3. Restricting Dashboard Network Access

The Dashboard generally does not need to be reachable from every microservice. Permit only management networks, VPNs, or bastions to access the UI. An internal reverse proxy can be placed in front to enforce SSO, MFA, audit logging, and rate limiting; the proxy does not replace protecting the REST API behind it.

## 5. Securing Consul UI and HTTP API

Consul exposes a UI and an HTTP API. Both use Consul's ACL system when ACLs are enabled. Tokens can grant permissions to read the catalog, query health, register services, or operate agents; permissions must be scoped by role.

### 5.1. Enabling ACLs and Using Per-Workload Tokens

In production, enable ACLs with a default-deny policy and issue distinct tokens per role. Example HCL policy for a read-only service consumer:

```hcl
service_prefix "" {
  policy = "read"
}

node_prefix "" {
  policy = "read"
}
```

A provider registering only `payment-service` can be given a restricted policy:

```hcl
service "payment-service" {
  policy = "write"
}
```

Agent API or catalog operations may need additional matching permissions depending on how the application connects to the Consul agent/server and the Consul version. Verify least-privilege permissions against the real API; never hand out `global-management` tokens to all services.

Issue separate tokens for providers, consumers, monitoring, and operators. If a token is compromised, that exact token can be revoked without replacing credentials across the entire cluster.

### 5.2. Passing Tokens Safely

The Consul HTTP API typically accepts tokens via the `X-Consul-Token` header or the client's configured token mechanism:

```bash
curl \
  -H "X-Consul-Token: ${CONSUL_READ_TOKEN}" \
  https://consul.internal.example:8501/v1/catalog/services
```

Never pass tokens in query strings or write real tokens into shell history, source code, or logs. With Spring Cloud Consul, use the token property supported by your integration version and inject it from a secret store; verify the configuration for your release train.

### 5.3. Restricting Consul UI and API

- Bind the HTTP API to loopback or an appropriate private interface; do not open unnecessary public listeners.
- Use HTTPS/TLS for API traffic over the network.
- Enable ACLs and scope tokens by service, node, or operation.
- Allow only operator subnets to reach the UI.
- Separate client API ports from internal Consul cluster RPC/gossip ports.
- Audit token creation, policy changes, service registrations, and administrative actions.

The UI is not an independent security boundary: UI users can execute whatever API requests their token allows. Therefore, restrict both UI tokens and network access simultaneously.

## 6. Securing ZooKeeper and Administrative Tools

ZooKeeper stores registrations as znodes. Security must control read, create, update, and delete permissions on the root path and child nodes. Administrative tools or AdminServer must also be restricted to the management network.

Key principles:

- Never use `world:anyone` ACLs with write permissions (`cdrwa`) for service discovery namespaces in production.
- Use SASL, digest, or an authentication mechanism supported by the cluster to identify clients.
- Grant read permissions to consumers and permissions to create/update/delete ephemeral nodes to providers in the required namespace.
- Use TLS for client connections if infrastructure policy requires transport encryption.
- Restrict client ports and AdminServer using firewalls/private interfaces.
- Open quorum ports such as peer synchronization and leader election only between ZooKeeper servers; never open them to all microservices.
- Never expose administrative tools or four-letter commands to user networks.

When changing ACLs on the root znode, verify child-node permissions and Spring Cloud Zookeeper/Curator's ephemeral node creation flow. A policy that allows reading the root without allowing providers to create child nodes will cause registration to fail.

## 7. Restricting Spring Boot Actuator

Actuator provides endpoints for health, metrics, and operations. Spring Boot exposes only a few endpoints over HTTP by default; other endpoints must be enabled and explicitly exposed. Exposing an endpoint and protecting an endpoint are two separate steps: exposed endpoints still require authentication/authorization and network restrictions.

### 7.1. Expose Only Required Endpoints

Example of a provider exposing only health, info, and Prometheus metrics:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,prometheus
  endpoint:
    health:
      show-details: when-authorized
      roles: OPS
      probes:
        enabled: true
```

To use `/actuator/prometheus`, the application needs the corresponding Micrometer Prometheus registry dependency. Only add endpoints to `include` when genuinely required. Avoid `include: "*"` on applications reachable from untrusted networks.

Several sensitive endpoints warrant careful thought before exposure:

| Endpoint | Risk | Recommendation |
|---|---|---|
| `/actuator/env` | Can expose properties and environment variables. | Do not expose publicly; restrict to operators and sanitize sensitive data. |
| `/actuator/configprops` | Exposes application configuration bindings. | Use only during controlled investigations. |
| `/actuator/heapdump` | May contain sensitive data in memory. | Never expose to ordinary networks; capture only via incident procedures. |
| `/actuator/threaddump` | Exposes stacks, thread names, and operational details. | Restrict to operator permissions. |
| `/actuator/loggers` | Can alter log levels via write operations. | Grant only to authorized operators. |
| `/actuator/mappings` | Exposes routes and API structure. | Do not expose broadly. |
| `/actuator/conditions` | Exposes auto-configuration conditions and classpath behavior. | Internal diagnostics only. |
| `/actuator/shutdown` | Can stop the application if enabled and exposed. | Disabled by default; never expose unless special procedures and strict protections exist. |

`health` can also expose dependency names or internal details if `show-details` is overly permissive. Use `when-authorized` or `never` depending on requirements; health checkers usually need only overall status.

### 7.2. Separating the Management Port

Actuator can be isolated onto a dedicated port bound to a management interface:

```yaml
server:
  port: 8080

management:
  server:
    port: 9001
    address: 10.20.5.21
  endpoints:
    web:
      base-path: /actuator
      exposure:
        include: health,info,prometheus
  endpoint:
    health:
      show-details: when-authorized
      roles: OPS
      probes:
        enabled: true
```

In this example, business requests use port `8080`, while Actuator uses port `9001` on management address `10.20.5.21`. The bind address must exist inside the application's network namespace. In containers, check interfaces and mappings; never bind to a host IP if that IP does not exist inside the container.

If kubelet needs to call readiness/liveness endpoints on the dedicated management port, configure the matching probe port and verify node-to-Pod routing. If probes should go through the application port, keep health groups on the server port using the appropriate Spring Boot configuration. Do not split ports and forget to update health checkers or monitoring scrapers.

## 8. Protecting Actuator with Spring Security

The example below illustrates a servlet application: aggregate health can be read without login, Prometheus is restricted to a monitoring role, and other Actuator endpoints require an operator role. Remaining requests require authentication according to application policy.

```java
import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ActuatorSecurityConfiguration {

    @Bean
    SecurityFilterChain applicationSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(EndpointRequest.to("health")).permitAll()
                .requestMatchers(EndpointRequest.to("prometheus"))
                    .hasRole("METRICS")
                .requestMatchers(EndpointRequest.toAnyEndpoint())
                    .hasRole("OPS")
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
```

`EndpointRequest` matches by Actuator endpoint instead of hardcoding every URL. Health details remain controlled by `show-details` and `roles`. Prometheus scrapers need credentials with the `METRICS` role; operators with the `OPS` role can access remaining exposed endpoints.

This example is for Spring MVC/Servlet. For WebFlux, use `SecurityWebFilterChain` and corresponding matchers. Configure your user store/identity provider, role mapping, session policy, and CSRF according to how the application authenticates. Do not copy the snippet and remove authentication for all requests. If the application has multiple `SecurityFilterChain` beans, verify their order and `securityMatcher` so Actuator requests actually traverse the intended chain.

## 9. Protecting the Kubernetes API and Admin Dashboards

When Spring Cloud Kubernetes DiscoveryClient uses the Kubernetes API, the ServiceAccount should only have read permissions on required resources. Typical discovery consumers do not need permissions to create or delete Services/Pods.

Example Role permitting only reads of Service and EndpointSlice in namespace `commerce`:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: service-discovery-reader
  namespace: commerce
rules:
  - apiGroups: [""]
    resources: ["services", "endpoints"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["discovery.k8s.io"]
    resources: ["endpointslices"]
    verbs: ["get", "list", "watch"]
```

Then bind the Role to the application's ServiceAccount using a RoleBinding. Exact resources and verbs depend on your Spring Cloud Kubernetes version and which resource implementation is queried. If the client does not read EndpointSlices, do not grant permissions merely because an example includes them; inspect `Forbidden` logs and version docs to determine minimum permissions.

Kubernetes Dashboard or cluster administration tools should never be exposed publicly with cluster-admin rights. Use an identity provider, MFA, namespace-scoped RBAC, and audit logs. Never hand out an admin kubeconfig to a microservice merely to read service discovery.

## 10. Example NetworkPolicy Restricting Actuator and Registry Management

A NetworkPolicy can restrict the Actuator port solely to the monitoring and operator namespaces. The following example applies to Pods labeled `app: payment` in namespace `commerce`:

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: payment-management-ingress
  namespace: commerce
spec:
  podSelector:
    matchLabels:
      app: payment
  policyTypes:
    - Ingress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: monitoring
      ports:
        - protocol: TCP
          port: 9001
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: platform-ops
      ports:
        - protocol: TCP
          port: 9001
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: orders
      ports:
        - protocol: TCP
          port: 8080
```

The policy permits monitoring and operators to reach management port `9001`; consumers from the `orders` namespace can only reach application port `8080`. This is an illustrative example—replace namespaces, labels, and ports to match your cluster. If Prometheus runs outside the cluster, use CIDRs or an appropriate policy mechanism. If health probes are executed by kubelet/nodes, check CNI behavior for node-to-Pod traffic before applying default-deny.

NetworkPolicy does not authenticate users and does not authorize HTTP endpoints. A Pod permitted to reach port `9001` still requires Spring Security protecting `/actuator/**`. Similarly, security groups/firewalls should restrict source subnets while APIs still enforce authentication/authorization.

## 11. Reference Access Control Matrix

| Role | Registry Dashboard | Registry read API | Registry write API | Actuator health | Metrics | Admin Actuator |
|---|---|---|---|---|---|---|
| `OPS` | Allowed | Allowed | Allowed per procedure | Allowed | Allowed | Approved endpoints allowed |
| `REGISTRY_READER` | No by default | Allowed | Denied | No by default | No by default | Denied |
| `REGISTRY_CLIENT` | Denied | Allowed | Only APIs needed for register/renew/deregister | No by default | No by default | Denied |
| `METRICS` | Denied | Denied | Denied | May read aggregate status | Allowed | Denied |
| `HEALTH_CHECKER` | Denied | Denied | Denied | Minimal health endpoint allowed | Denied | Denied |
| `APP_USER` | Denied | Denied | Denied | Very restricted need only | Denied | Denied |

This is a reference matrix, not built-in roles in Spring Cloud or Consul. Map roles into Spring Security, ACL policies, your identity provider, and environment NetworkPolicies. Some registry APIs share the same endpoint for reads and writes; in those cases, authorize by HTTP method or registry policy.

## 12. Auditing, Logging, and Incident Handling

Events to monitor:

- Failed logins or requests returning `401`/`403`.
- Changes to Consul ACL tokens, policies, roles, and service registrations.
- Eureka instance registrations, renewals, deregistrations, or status changes.
- ZooKeeper ACL operations and znode changes under the discovery root.
- Requests to sensitive Actuator endpoints, especially `env`, `heapdump`, `loggers`, and `shutdown` if enabled.
- Kubernetes API requests denied by RBAC or accesses outside expected namespaces.
- Flow logs for connections to registry ports, management ports, and service ports.

Never write access tokens, passwords, session cookies, or sensitive `/env` contents to logs. Logs should capture identity, endpoint, timestamp, outcome, and a correlation/request ID sufficient for investigation without leaking credentials.

### 12.1. Diagnosing by Error Code

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Dashboard returns `401` | Unauthenticated or wrong credentials. | Check identity provider and operator account. |
| Dashboard returns `403` | Authenticated but insufficient role. | Grant the appropriate least-privilege role; do not promote everyone to admin. |
| Eureka Client fails to register after enabling Security | Wrong Basic Auth, CSRF blocking POST/PUT/DELETE, or wrong matcher. | Check URL credentials, ignore CSRF only for Eureka API paths, and verify client roles. |
| Consul API returns `403` | ACL token lacks matching service/node/agent permissions. | Inspect ACL audit/logs and grant least-privilege policy for the actual API. |
| ZooKeeper reports `NoAuth` | ACL/SASL identity lacks permissions on znode. | Check root and child ACLs, auth scheme, and create/write/delete permissions. |
| Actuator returns `404` | Endpoint not enabled/exposed or different base path/port. | Check `management.endpoints.web.exposure` and management port. |
| Actuator returns `401`/`403` | Disallowed by security chain or role. | Check matchers, role mappings, and scraper/operator credentials. |
| Prometheus scrape fails | Endpoint not exposed, missing registry dependency, port/network blocked, or missing role. | Check `/actuator/prometheus`, dependencies, NetworkPolicy, and auth. |
| Health checker times out | Probe cannot reach management port or endpoint responds too slowly. | Check source subnet, routing, probe path/port, and timeouts. |
| Public users can reach Dashboard/API | Public listener, overly broad reverse proxy, or overly permissive firewall rule. | Restrict bind/network, require auth, and inspect ingress paths. |

## 13. Pre-Production Checklist

- Dashboard is accessible only from management networks/VPN/bastions.
- Registry API requires authentication and role-based or ACL-based authorization.
- Providers have dedicated credentials for register/renew; consumers have appropriate read permissions.
- Consul ACLs are enabled, default tokens lack broad permissions, and per-workload tokens can be revoked individually.
- ZooKeeper root znodes and child nodes use ACLs; no `world:anyone` write permissions exist.
- Kubernetes ServiceAccounts have only the RBAC read permissions required for discovery resources.
- Actuator exposes only genuinely needed endpoints; `include: "*"` is not used arbitrarily.
- Health details do not leak dependencies or internal information to unauthorized callers.
- Prometheus endpoints are reachable only by monitoring scrapers and authenticated if required by environment policy.
- Actuator management port is separated and bound to an appropriate network/interface if needed.
- Spring Security protects endpoints by role; matchers and filter chain order have been tested.
- Eureka CSRF exemptions are limited strictly to API paths needed by clients.
- TLS/mTLS is verified with proper certificate SANs, CAs, and client identities.
- Firewalls, security groups, and NetworkPolicies permit only exact sources/destinations/ports.
- Audit logs exist for Dashboard, API, Actuator accesses, and registry-modifying operations.
- Tests cover valid roles, invalid roles, missing credentials, and disallowed network sources.

## Conclusion

The Dashboard, registry API, and Actuator are critical administrative surfaces of service discovery. Management networks must be separated from business traffic, distinct permissions must be assigned to operators, registry clients, health checkers, and monitoring, and only genuinely required endpoints should be exposed. Eureka can be secured with Spring Security; Consul uses ACL tokens and policies; ZooKeeper uses authentication alongside per-znode ACLs; Kubernetes discovery requires least-privilege ServiceAccounts/RBAC; and Actuator requires exposure allowlists, appropriate management ports, and per-endpoint authorization.

No single protection layer is sufficient on its own. Network segmentation, authentication, authorization, TLS, endpoint restriction, and auditing must work together to prevent topology disclosure or unauthorized registry modifications from unapproved workloads. After configuring them, test every role and every network path to verify permissions match operational needs.
