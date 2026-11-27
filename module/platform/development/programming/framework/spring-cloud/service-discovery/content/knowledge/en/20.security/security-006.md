# Consul ACL Tokens and Least Privilege for Registration or Lookup

Consul ACLs (Access Control Lists) control who can register services, read service lists, update health checks, and administer the cluster. When ACLs are enabled, a Spring Cloud Consul application must send a token with the exact permissions required for the operations it performs. Using a single management token across all services means a single secret leak can compromise the entire Consul cluster.

Secure design starts by separating roles: a service producer needs permission to register itself; a service consumer needs permission to read only the services it is allowed to call; applications using TTL heartbeats additionally need check-update permissions; and the Consul Agent has its own token for internal operations. Spring Cloud Consul provides separate token properties for Discovery and Consul Config, so these permissions should not be combined unnecessarily.

## 1. Which Operations Do ACLs Protect?

Consul ACLs attach policies to tokens. When a client calls the Consul HTTP API or Consul Agent API, Consul evaluates the token and its resource rules.

In service discovery, the primary operations include:

| Operation | Common API | Primary ACL Permission |
|---|---|---|
| Register service with local agent/catalog | `PUT /v1/agent/service/register` | `service:write` for the registered service name |
| Deregister service | `PUT /v1/agent/service/deregister/:service_id` | `service:write` for the corresponding service |
| Register standalone check via Agent API | `PUT /v1/agent/check/register` | `node:write` and `service:write` |
| Read service in Catalog | Catalog API | `service:read`; node rules may restrict returned nodes |
| Look up service with health state | Health API `/v1/health/service/:name` | `service:read` and `node:read` for corresponding discovery data |
| Renew TTL check | `/v1/agent/check/pass/:check_id`, `warn`, `fail`, `update` | `node:write` and `service:write` |
| Create/edit ACL policy or token | ACL API/CLI | `acl:write` |

`service:write` allows updating the service's catalog entries. `service:read` allows reading the service. `node:read` allows reading node metadata and is part of discovery queries via the Health API. `node:write` allows updating node information and is required by certain check operations on the Agent API, including TTL updates.

Never grant `acl:write`, `operator:write`, `key:write`, or broad administrative permissions to an application that only needs to register and look up services.

## 2. Distinguishing Token Types in Consul

Consul has multiple token types with different roles. Their names look similar, but they cannot be substituted arbitrarily:

| Token | Who Uses It? | Purpose |
|---|---|---|
| Initial management token | ACL administrator | Create policies, tokens, roles, and perform ACL admin operations; very broad permissions |
| Application/service token | Spring Boot service or workload | Register service, send heartbeats, or read services according to attached policies |
| Agent token (`acl.tokens.agent`) | Consul Agent | Internal operations such as syncing node metadata and anti-entropy |
| Default token (`acl.tokens.default`) | Consul Agent for requests lacking a specific token, including some DNS queries | Default agent permissions when no explicit token is provided; should be scoped to required access |
| Config-file service-registration token | Consul Agent registering services/checks declared in agent config files | Allows the agent to register static services/checks from configuration files |
| Anonymous token | Requests sent without a token | Permissions assigned to the anonymous token; should never be given broad permissions |

Spring Cloud Consul's `spring.cloud.consul.discovery.acl-token` is the token used by Discovery integration for discovery/registration operations. This is an application token, not the Consul Agent's `acl.tokens.agent`.

Spring Cloud Consul's `spring.cloud.consul.config.acl-token` is a separate token for Consul Config when reading data from KV. If an application does not use Consul Config, do not grant KV permissions just because it uses service discovery.

## 3. Enabling ACLs and Bootstrapping the Management Token

ACLs must be enabled on both Consul servers and client agents. Example configuration on a Consul server:

```hcl
acl {
  enabled = true
  default_policy = "deny"
}
```

`default_policy = "deny"` is the server-side default policy for operations not explicitly allowed by a policy. Enable `acl.enabled` on client agents and configure the required tokens for each agent; do not blindly copy `default_policy` to client configs. When transitioning a live cluster from ACLs disabled to ACL enforcement, plan a phased rollout and provision agent tokens before switching to deny; flipping abruptly to deny can break agent and service synchronization.

Bootstrap ACLs on a Consul server:

```bash
consul acl bootstrap
```

Consul returns an initial management token, where `SecretID` is the credential used for authentication. This token carries `global-management` permissions, granting unrestricted access across resources/APIs. Only ACL administrators should hold this token; never place it in `application.yml`, shared workload environment variables, or build pipelines.

In the CLI examples that follow, assume the administrator temporarily supplies the management token to the Consul CLI:

```bash
export CONSUL_HTTP_TOKEN="<INITIAL_MANAGEMENT_SECRET_ID>"
```

PowerShell:

```powershell
$env:CONSUL_HTTP_TOKEN = "<INITIAL_MANAGEMENT_SECRET_ID>"
```

The `CONSUL_HTTP_TOKEN` variable here is only for the administrative CLI session. Spring Boot applications will receive their own service tokens via a secret store or environment injection. Never commit real token values to Git.

## 4. Creating a Policy That Permits Registering Only One Service

Suppose a producer has the service name `inventory-service` and only needs to register/deregister that exact service. Create a policy file `inventory-register.hcl`:

```hcl
service "inventory-service" {
  policy = "write"
}
```

This policy grants `service:write` for that exact service name. It does not grant permission to read all services, write KV, create tokens, or administer agents.

Register the policy:

```bash
consul acl policy create \
  -name "inventory-register" \
  -description "Allow inventory-service registration" \
  -rules @inventory-register.hcl
```

Create a token attached to the policy:

```bash
consul acl token create \
  -description "Spring Cloud token for inventory-service registration" \
  -policy-name "inventory-register"
```

The CLI returns an `AccessorID` and `SecretID`. Store `SecretID` in a secret manager; `AccessorID` is useful for managing, inspecting, and revoking the token. This registration-only token is sufficient for service registration operations via the Agent Service Registration API. If the service also needs to look up other services, add scoped read permissions as shown in the next section.

## 5. Creating a Policy That Permits a Consumer to Query Services

Consumer `order-service` needs to look up `inventory-service` and `payment-service`. With the Health API, granting only `service:read` may not be enough to receive complete node/address data; `node:read` is also needed for the scope the consumer is allowed to see.

Example policy allowing reads on only two specific services:

```hcl
service "inventory-service" {
  policy = "read"
}

service "payment-service" {
  policy = "read"
}

node_prefix "" {
  policy = "read"
}
```

If the consumer is permitted to discover all services in the datacenter, `service_prefix ""` can be used instead of individual service rules:

```hcl
service_prefix "" {
  policy = "read"
}

node_prefix "" {
  policy = "read"
}
```

Do not expand to `service_prefix ""` if the consumer only needs two services. Broader permissions increase the scope of service/node information the token can read.

Register the policy and create the token using the same workflow:

```bash
consul acl policy create \
  -name "order-discovery-read" \
  -description "Allow order-service to discover approved upstreams" \
  -rules @order-discovery-read.hcl

consul acl token create \
  -description "Spring Cloud token for order-service discovery" \
  -policy-name "order-discovery-read"
```

In Consul Enterprise, if namespaces or admin partitions are used, policies and tokens must also be scoped to the proper namespace/partition. Rules in one namespace cannot arbitrarily access resources in another namespace.

## 6. A Service That Both Registers Itself and Calls Other Services

In practice, `inventory-service` might both register its own instances and call `pricing-service`. In that case, the policy needs write permission for its own service and read permission for the services it is permitted to call.

Example:

```hcl
service "inventory-service" {
  policy = "write"
}

service "pricing-service" {
  policy = "read"
}

node_prefix "" {
  policy = "read"
}
```

If the service needs to discover multiple services, replace individual service read rules with an appropriate `service_prefix`. This structure matches the custom policy pattern documented by HashiCorp: a service identity gets write permission for itself and read permission for the services/nodes it needs to discover.

HashiCorp also provides the `builtin/service` templated policy. This template automatically grants `service:write` and `service:read` for the specified service plus `node:read`; it is recommended for common service discovery/service mesh use cases. Example creating a token for `inventory-service`:

```bash
consul acl token create \
  -description "Service identity for inventory-service" \
  -templated-policy "builtin/service" \
  -var "name:inventory-service"
```

Templates are convenient and less error-prone, though a custom policy can be narrower if the application only needs to register without reading other services. Choose policies based on actual workload behavior rather than template availability.

## 7. Additional Permissions When Using TTL Heartbeats

Registering a service with a health check and updating a TTL check are two different operations. The Consul Agent API requires `node:write` and `service:write` for TTL check pass/warn/fail/update endpoints.

If Spring Cloud Consul sends TTL heartbeats directly using the application token, the token needs write permission on the corresponding service and the node managed by the Consul Agent. You can add a specific node rule:

```hcl
service "inventory-service" {
  policy = "write"
}

node "consul-client-01" {
  policy = "write"
}
```

`consul-client-01` must match the exact node name of the Consul Agent where the check is registered. Never use `node_prefix "" { policy = "write" }` just to make TTL heartbeats work, because that grants broad write permissions across all nodes.

If the same token also needs to query other services, add appropriately scoped `service:read` and `node:read`. If using an HTTP health check polled proactively by the Consul Agent, the application does not send TTL heartbeats; do not grant extra TTL permissions just because an HTTP check exists.

Distinguish application token permissions from agent tokens: `acl.tokens.agent` is used by the Consul Agent for internal operations and requires write access on the agent's own node plus service read access for anti-entropy. Never copy a Spring Boot service token into the agent token configuration.

## 8. Configuring Tokens in Spring Cloud Consul

Spring Cloud Consul 5.1.0 provides separate properties for Discovery and Config:

| Property | Used For |
|---|---|
| `spring.cloud.consul.discovery.acl-token` | Consul service registration, discovery queries, and related Discovery integration operations |
| `spring.cloud.consul.config.acl-token` | Reading Consul KV via Consul Config |

Example of an application that both registers `inventory-service` and looks up `pricing-service`:

```yaml
spring:
  application:
    name: inventory-service
  cloud:
    consul:
      host: ${CONSUL_HOST:localhost}
      port: ${CONSUL_PORT:8500}
      discovery:
        acl-token: ${CONSUL_DISCOVERY_TOKEN}
        register: true
        deregister: true
```

In a TTL heartbeat setup, that token must also have `node:write` on the corresponding node as shown earlier. If only HTTP health checks are used, the policy does not need extra TTL permissions.

If the application uses Consul Config to read key/values:

```yaml
spring:
  cloud:
    consul:
      config:
        acl-token: ${CONSUL_CONFIG_TOKEN}
```

KV policies should restrict access to the exact prefix the application reads. For example, if configuration data lives under `config/`, use:

```hcl
key_prefix "config/" {
  policy = "read"
}
```

Never grant `key_prefix "" { policy = "write" }` to a service that only reads configuration. If the application does not use Consul Config, `CONSUL_CONFIG_TOKEN` is unnecessary.

The `CONSUL_DISCOVERY_TOKEN` and `CONSUL_CONFIG_TOKEN` variables should be injected from Vault, Kubernetes Secrets, the platform secret manager, or an equivalent secret management mechanism. Environment variable names can follow Spring Boot's relaxed binding, such as `SPRING_CLOUD_CONSUL_DISCOVERY_ACL_TOKEN`, though secret references help decouple credentials from configuration files.

## 9. Consul Agent Tokens Differ from Application Tokens

Consul Agent has its own tokens in the agent configuration. Example structure:

```hcl
acl {
  enabled = true
  default_policy = "deny"

  tokens {
    agent = "<AGENT_INTERNAL_TOKEN_SECRET_ID>"
    default = "<AGENT_DEFAULT_READ_TOKEN_SECRET_ID>"
  }
}
```

An agent token typically needs:

```hcl
node "consul-client-01" {
  policy = "write"
}

service_prefix "" {
  policy = "read"
}
```

The node write rule lets the agent update its own node metadata and tagged addresses. Service read allows the agent to read needed services during anti-entropy. When remote execution is disabled (the default), there is no need to grant KV `_rexec` permissions for this purpose.

The default token should hold permissions suited to default requests, such as reading services/nodes if the agent serves DNS discovery. Never use a management token as the default token. When a request supplies an explicit token, that token is used instead of the default/anonymous token.

`config_file_service_registration` is a different token, used when the Consul Agent registers services/checks declared in agent config files. It is not the `spring.cloud.consul.discovery.acl-token` property of a Spring Boot application registering itself via the Agent API.

## 10. Management Tokens and Application Tokens Must Be Separate

The initial management token is bound to `global-management`, granting extensive permissions. This token is needed to bootstrap ACLs, create policies/tokens, and handle administrative tasks, but it should never appear in a microservice runtime.

Typical authorization workflow:

1. Administrators use the management token to create policies and tokens.
2. Issue application tokens aligned with each workload's service identity and role.
3. Inject tokens into Spring Cloud Consul via secret injection.
4. Verify required APIs succeed and out-of-scope APIs are denied.
5. Record `AccessorID` for lifecycle management; protect `SecretID` like a password.
6. Revoke tokens when a service is decommissioned, credential exposure is suspected, or the workload no longer needs access.

Never place real tokens in Git, Docker images, logs, tickets, chats, shell command history, or Actuator environment endpoints. Avoid publicly exposing `/actuator/env` or `/actuator/configprops` because they can leak properties containing tokens.

## 11. Passing Tokens When Calling the Consul HTTP API

The Consul HTTP API accepts tokens via the `X-Consul-Token` header. Example querying service health:

```bash
curl --header "X-Consul-Token: ${CONSUL_DISCOVERY_TOKEN}" \
  "http://127.0.0.1:8500/v1/health/service/inventory-service?passing=true"
```

PowerShell:

```powershell
$headers = @{ "X-Consul-Token" = $env:CONSUL_DISCOVERY_TOKEN }
Invoke-RestMethod -Headers $headers -Uri "http://127.0.0.1:8500/v1/health/service/inventory-service?passing=true"
```

Never pass tokens in query strings, because URLs routinely appear in access logs, proxy logs, and shell history. Use HTTPS/TLS to protect tokens over the network; ACLs authenticate and authorize requests but do not encrypt transport on their own.

## 12. Verifying Granted Permissions

Test both permitted and forbidden operations. Do not simply verify that service registration succeeds and conclude the policy is least-privilege.

| Test Case | Producer Token | Consumer Token |
|---|---|---|
| Register `inventory-service` | Allowed if holding `service:write` | Denied if read-only |
| Register `payment-service` | Denied if policy only writes `inventory-service` | Denied if read-only |
| Read `inventory-service` | Depends on whether policy includes `service:read` | Allowed if granted service/node read |
| Read out-of-scope service | Denied if policy names specific services | Denied if policy names specific services |
| Write KV | Denied without key write | Denied with only service/node read |
| Create ACL token or policy | Denied without `acl:write` | Denied without `acl:write` |
| Send TTL pass/warn/fail | Requires `node:write` and `service:write` for that check | Usually unnecessary and should be denied |

You can inspect policies attached to a token using the appropriate administrative ACL command. When debugging, verify the actual token sent by Spring Cloud, attached policies, exact service name, node name, datacenter, and namespace/partition if using Enterprise.

## 13. Common ACL Errors

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Spring Cloud Consul receives HTTP 403 on registration | Token lacks `service:write` for the service name or token is wrong | Check `spring.cloud.consul.discovery.acl-token` and service policy |
| Registration succeeds but consumer sees no instances | Query token lacks `service:read` or `node:read`; ACL filters results | Test the Health API with the actual consumer token and service/node scope |
| Catalog API reads work but Health API returns no endpoints | Missing `node:read` or node rule restricts nodes | Add properly scoped node read and check node name |
| TTL heartbeat gets 403 | Token has service write but lacks `node:write` for the node hosting the check | Grant node write on that single node, or use a different health check model |
| Consul Agent reports anti-entropy errors | `acl.tokens.agent` lacks node write for itself or service read | Fix the agent token separately; do not arbitrarily escalate application tokens |
| Consul Config cannot read KV | `spring.cloud.consul.config.acl-token` lacks key read or wrong prefix | Grant `key_prefix` read on the exact config path |
| Works locally but gets 403 in production | Local uses anonymous/un-enforced ACLs or a different token than production | Check real ACL enforcement config and runtime-injected token |
| Token stops working after rotation | New secret not deployed consistently or old token revoked prematurely | Verify rollout and test requests with the new token before revoking the old one |

ACLs can make discovery results look as if a service does not exist because the API filters out services/nodes the token cannot read. When a consumer receives an empty list, verify permissions using the actual token before concluding the producer failed to register.

## 14. Token Rotation and Revocation Procedure

Token rotation should not disrupt service discovery:

1. Create a new policy or confirm the existing policy is still accurate.
2. Create a new token attached to that policy.
3. Store the new `SecretID` in the secret store.
4. Update workloads to pick up the new token and restart/refresh per deployment mechanism.
5. Verify registration, heartbeats, and discovery using the new token.
6. Wait until old instances are no longer using the old token.
7. Revoke the old token via ACL token revoke once certain no consumers still use it.
8. Inspect audit/logs and remove the old secret from storage per procedure.

Do not revoke the old token before workloads have switched to the new token. If a token is compromised, emergency revocation may be necessary while accepting operational impact; then create a new token with a narrow policy and re-verify registration/health.

## 15. Least Privilege Checklist

- [ ] ACLs are enabled on Consul agents and `default_policy` matches enforcement mode.
- [ ] Management tokens are used only for ACL administration, never injected into microservices.
- [ ] Each workload has its own token aligned with its service identity and responsibilities.
- [ ] Producers have only `service:write` for their own service name if they only register.
- [ ] Consumers have `service:read` and `node:read` for the services/nodes they are allowed to discover.
- [ ] Services acting as both producer and consumer have write for themselves and read for required upstreams.
- [ ] TTL heartbeats are granted `node:write` only for the node hosting the check alongside corresponding `service:write`.
- [ ] Agent internal token (`acl.tokens.agent`) is separate from application tokens.
- [ ] `acl.tokens.default` is not a management token and has only minimum read permissions needed for DNS/default requests.
- [ ] Consul Config uses a separate token with scoped `key_prefix` read if the application actually uses KV.
- [ ] SecretID is stored in a secret manager, never committed or logged.
- [ ] Tokens are transmitted over HTTPS/TLS via the `X-Consul-Token` header when calling the HTTP API.
- [ ] Both allowed operations and operations that must be denied have been tested.
- [ ] Processes exist for rotation, revocation, and compromised token handling.

## References

- [Spring Cloud Consul 5.1.0 — Common Application Properties (`discovery.acl-token`, `config.acl-token`)](https://docs.spring.io/spring-cloud-consul/reference/appendix.html)
- [HashiCorp Consul — Create Tokens for Service Registration](https://developer.hashicorp.com/consul/docs/secure/acl/token/service)
- [HashiCorp Consul — ACL Rules](https://developer.hashicorp.com/consul/docs/secure/acl/rule)
- [HashiCorp Consul — Create Tokens for Agent Registration](https://developer.hashicorp.com/consul/docs/secure/acl/token/agent)
- [HashiCorp Consul — ACL Bootstrap](https://developer.hashicorp.com/consul/docs/secure/acl/bootstrap)
- [HashiCorp Consul — Agent Service Registration API](https://developer.hashicorp.com/consul/api-docs/agent/service)
- [HashiCorp Consul — Agent Check API and TTL permissions](https://developer.hashicorp.com/consul/api-docs/agent/check)
- [HashiCorp Consul — ACL Agent Configuration](https://developer.hashicorp.com/consul/docs/reference/agent/configuration-file/acl)
