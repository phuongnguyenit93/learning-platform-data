# Protecting Metadata and Replica List Sources

Spring Cloud LoadBalancer chooses where to send requests based on the `ServiceInstance`s provided by the `ServiceInstanceListSupplier` chain. An instance typically carries a **service ID**, **host**, **port**, **secure** state, and `metadata` such as zone, version, or weight. This data looks like ordinary operational configuration, yet it directly affects **which network target receives the request**, **routing priority**, and **whether sensitive information can be exposed**.

If the instance list source is modified without authorization, a caller can be steered to a spoofed instance or shifted out of the intended deployment region. If metadata is tampered with, weighted algorithms or zone/version policies can route traffic to improper targets. This is why **communication security** covers more than TLS and tokens; it also covers **the integrity, change permissions, and provenance of the data used to select instances**.

This lesson belongs to the **Communication Security** chapter of the **SPRING_CLOUD_SERVICE_COMMUNICATION_LOAD_BALANCING** module. The goal is to protect Spring Cloud LoadBalancer's inputs when selecting `ServiceInstance`s by service ID, coordinating discovery, health checks, and routing policies, and applying this across RestClient, WebClient, and OpenFeign. We will establish a threat model, defensive layers, an instance-filtering example, and testing scenarios.

> **Assurance boundary:** metadata inside `ServiceInstance` is not signed or provenance-verified by Spring Cloud LoadBalancer by default. Protection must start at the **registry/configuration source**, continue through the **supplier chain**, and be reinforced at **transport, network egress, and target-service authorization**.

## 1. Instance Lists Are Routing Control Data

Suppose `order-service` calls:

~~~java
catalogRestClient.get()
    .uri("http://catalog-service/api/items/42")
    .retrieve()
    .body(String.class);
~~~

A supplier provides logical data:

~~~text
serviceId = catalog-service

A: instanceId=catalog-a
   host=10.0.1.11, port=8443, secure=true
   metadata={zone=zone-a, version=v1, weight=80}

B: instanceId=catalog-b
   host=10.0.2.12, port=8443, secure=true
   metadata={zone=zone-b, version=v1, weight=20}
~~~

These fields can originate from various sources: a service registry, Kubernetes API, Consul, Eureka, `SimpleDiscoveryClient` configuration, or a custom supplier. Metadata is represented as a `Map<String, String>`; how an algorithm or supplier interprets that map depends on the active configuration.

| Field | Potential Impact | Risk If Untrusted |
|---|---|---|
| `serviceId` | Matches logical requests to target lists | Accidental/spoofed service registration |
| `host` | Determines connection address | Redirects requests to an unauthorized host |
| `port` | Determines service port | Hits admin ports or other internal endpoints |
| `isSecure()` / scheme | Affects URL and TLS transport per integration | Connection downgrade or identity verification failure |
| `instanceId` | Observes and distinguishes replicas | ID spoofing, misleading logs/metrics |
| `zone` / region | Can be used by zone-aware policies | Routes requests into the wrong data region |
| `version` / canary | Can be used by custom routing policies | Sends traffic to unauthorized experimental builds |
| `weight` | Can influence target selection when weighted supplier is enabled | Concentrates traffic onto an adversary-controlled instance |
| Other custom metadata | Routing hints, tagging, feature flags | Injection, secret leakage, metric cardinality explosion |

**Distinguish data from authority:** a `metadata["weight"]` field only has an effect if a supplier/policy actually reads it. Once used as a control signal, however, that field must be treated as **high-privilege configuration**, not an arbitrary string self-published by an instance.

## 2. Trust Boundaries from Registry to HTTP Request

~~~mermaid
flowchart LR
    A["Control plane / authorized registrant"] --> R["Registry / Kubernetes API / config"]
    R --> D["DiscoveryClient"]
    D --> S["ServiceInstanceListSupplier"]
    S --> C["Cache / health / route filters"]
    C --> LB["Spring Cloud LoadBalancer"]
    LB --> H["RestClient / WebClient / Feign"]
    H --> I["Selected target instance"]

    U["Compromised source / spoofed config"] -. "alters host, port, metadata" .-> R
    M["Metadata from low-trust source"] -. "poisoning" .-> S
~~~

An architecture must answer three questions explicitly:

1. **Who is allowed to create, modify, or delete instances?** Write access to a registry/config source cannot be handed out broadly simply because it is "discovery data".
2. **Who authenticates the data source?** Over what connection, credentials, and permissions does `DiscoveryClient` fetch its data?
3. **Who enforces connection safety?** Does the caller check targets, TLS identity, and egress limits, or does it blindly trust whatever host/port came from the registry?

A registry with TLS where every workload can edit another service's entries still risks **rogue instance registration**. A well-permissioned registry paired with an HTTP client that disables certificate verification still risks **sending requests to spoofed targets**. Security requires multiple independent layers.

## 3. Threat Model for Discovery and Metadata

| Threat | Exploited Weakness | Consequence | Primary Defense Layer |
|---|---|---|---|
| Rogue instance registration | Overly broad registry write permissions | Caller sends requests to attacker-controlled host | ACL/RBAC, registry authentication, egress policy |
| Host/port tampering | Address data from discovery/config | SSRF into internal networks or admin ports | Source controls, target allowlists, network policies |
| Zone spoofing | Routing metadata | Wrong-region routing, data-residency violation | Trusted metadata authority, zone policy |
| Extreme weight injection | Weighted routing policy | Draws most traffic onto a single instance | Weight bounds and validation |
| Changing secure flag/scheme | `ServiceInstance` transport fields | HTTP downgrade or TLS identity mismatch | Mandatory HTTPS/mTLS per policy and cert verification |
| Cross-environment instance injection | Missing namespace/environment isolation | Prod accidentally calls staging | Registry isolation, environment-specific identity |
| Cache poisoning | Bad entries get cached | Spoofed target keeps getting picked after registry fix | TTL/revocation, cache invalidation, pre-routing checks |
| Health spoofing | Untrusted health endpoint | Malicious instance still marked healthy | Health checks over trusted channels, auth/network policies |
| Secrets in metadata | Putting tokens/credentials in map | Exposed via discovery APIs, logs, or metrics | Keep secrets out of metadata; use secret manager |
| Malformed metadata payloads | Custom parsers/formatters | Parser bugs, log injection, memory/cardinality spikes | Bounds, schemas, encoding, safe logging |

These are **risk scenarios**, not a claim that every discovery implementation is trivially exploitable. Exposure depends on topology, permissions, transport, registry read/write access, and application policy.

### Why Is This Also an SSRF Risk?

Server-Side Request Forgery (SSRF) is usually discussed when an app takes a URL from a user and fetches it. With client-side load balancing, **the target URL can also be indirectly controlled by a data source outside the trust boundary**.

For instance, a registry record is changed from `catalog-b:8443` to an internal admin address or a special link-local IP. If the caller trusts the list unconditionally, it can send requests and `Authorization` headers to an unauthorized target.

The crucial insight is that **metadata or registry records become inputs controlling network addresses**, even when external users never pass a `url` parameter to an API.

## 4. Never Treat Metadata as Proof of Identity

A forged record can self-declare:

~~~text
serviceId=catalog-service
metadata={
  environment=production,
  zone=zone-a,
  trusted=true,
  weight=100
}
~~~

The field `trusted=true` **does not make the record trustworthy**. If an attacker can edit metadata, they can also flip a self-asserted "trusted" flag. Likewise, `zone=zone-a` does not prove an instance actually runs in zone-a.

**Trustworthy identity** must come from authenticated, access-controlled sources, such as:

- Platform-verified service account/workload identity.
- Certificate identity verified via TLS/mTLS against the right CA and policy.
- Registry read/write permissions scoped by namespace, service, role, and environment.
- Admission policies or deployment pipelines governing labels/annotations.
- Independent rules constraining which service IDs and endpoints a caller may contact.

Metadata may serve as **routing hints**, but must never be used as **the sole authentication or authorization mechanism**. Security decisions must rest on verified identity/permissions, not self-claimed labels.

## 5. Protecting Where ServiceInstance Lists Are Born and Stored

### Registries Need Separate Read and Write Permissions

In Eureka, Consul, Kubernetes, or an internal registry, independently control:

- Who can **register** or **deregister** instances?
- Who can **modify metadata** such as zone/weight/version?
- Who can **read the list** for which services?
- Can a compromised workload overwrite another workload's records?
- Are control-plane mutations captured in **audit logs**?
- Is the registry accessed over authenticated and encrypted connections?

A caller normally only needs **read discovery** to pick instances. Workloads that only consume discovery should not receive full registry write permissions. Where self-registration is used, write access must be scoped to the workload's own identity/instances.

### Example Read Role in Kubernetes

An illustrative manifest for namespace `apps`:

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: catalog-discovery-reader
  namespace: apps
rules:
  - apiGroups: [""]
    resources: ["services", "endpoints"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["discovery.k8s.io"]
    resources: ["endpointslices"]
    verbs: ["get", "list", "watch"]
~~~

This manifest **only defines the Role**; it does not bind it to a service account yet. In real deployments, add the appropriate `RoleBinding` and verify which resources your Spring Cloud Kubernetes discovery implementation requires (which can vary by version/mode). Grant only the minimum APIs actually needed; never copy extra `create`, `update`, `patch`, or `delete` verbs if the caller does not need them.

Note that if the system reads across many namespaces, broad `list/watch` privileges expand data exposure. Isolate namespaces/service accounts and narrow scope accordingly.

### Static Configuration Also Needs Protection

When using `SimpleDiscoveryClient`:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: https://catalog-a.internal.example:8443
              - uri: https://catalog-b.internal.example:8443
~~~

The list sits in YAML, yet YAML can originate from Git, Config Server, ConfigMaps, environment variables, or deployment pipelines. You must therefore protect **repositories, merge permissions, CI/CD, secret stores, and runtime configs**; a "static" list is not automatically safe if every developer or workload can edit it.

## 6. Encrypting and Authenticating Paths to Discovery Sources

A discovery client can query a registry over the network or read platform APIs. Baseline requirements:

1. **Valid TLS** for networked protocols; never disable hostname verification or trust all certificates.
2. **Caller identity authentication** using appropriate credentials, client certificates, or service account tokens.
3. **Least-privilege authorization** on registry APIs.
4. **Secret management** via supported mechanisms—never hard-code tokens into public YAML, query strings, or `ServiceInstance.getMetadata()`.
5. **Freshness and cache lifecycle controls** so permission revocations take effect promptly.
6. **Audit changes** to instances and metadata, especially host/port/scheme and routing hints.

TLS protects the transport to **the data source**, not the authenticity of **every record inside that source**. You still need write authorization and workload authentication.

### Separating Three Security Channels

| Channel | Goal | What It Does Not Guarantee in Isolation |
|---|---|---|
| Caller → registry | Receive an authenticated list from a genuine source | Does not prove target instances are still healthy |
| Caller → instance | Protect requests, credentials, and responses | Does not control who can write to the registry |
| Instance → registry / control plane | Only legitimate workloads register or update metadata | Does not replace endpoint business authorization |

If one channel is left unprotected, encrypting the other two is not enough to secure the system.

## 7. Host, Port, Scheme, and TLS Identity Are Sensitive Control Data

Suppose the logical service ID is `catalog-service`, yet the selected instance returns:

~~~text
host = 192.0.2.50
port = 8080
secure = false
metadata = {zone=trusted-zone}
~~~

A client should never automatically trust this target merely because metadata says `trusted-zone`. In production, policy may require:

- **Service ID** matches an approved downstream for this caller.
- The endpoint resides in an **approved network/deployment zone**.
- **Port** belongs to the valid service port list.
- **TLS** is enabled with matching CA/certificates and identity.
- Never send `Authorization` headers to arbitrary hosts chosen by users or unverified registries.
- Never call loopback, link-local, metadata services, admin ports, or unexpected addresses specified by external data.

`ServiceInstance.isSecure()` and the scheme from `getUri()` are **data attributes**, not proof that a TLS session actually authenticated. TLS must be **enforced and verified at the real HTTP transport**.

### Notes on Certificate Names and Load Balancing

Once LoadBalancer picks instance A or B, the HTTP connector may connect to the instance's actual hostname or IP. TLS certificates must match **the host/service identity actually verified by the connector** under the system's TLS/SNI/sidecar/proxy design. If a certificate only has an SAN for the logical name `catalog-service` while the transport directly connects and verifies `catalog-a.internal.example`, a hostname mismatch error can occur.

Never "fix" that error with `trustAll` or by disabling hostname verification. Design certificate SANs, service DNS, sidecar/mTLS, or SNI config to match the real path and verify with integration tests.

## 8. Routing Metadata: Allowlists and Value Bounds

Fields commonly used in routing:

| Metadata | Proper Usage | Protective Bounds |
|---|---|---|
| `zone` | Prefer instances near the caller | Accept only platform-controlled zones |
| `region` | Data locality | Enforce data residency and authorization independently |
| `version` | Canary/blue-green | Version set by an authorized rollout controller |
| `weight` | Weighted traffic distribution | Numeric values within permitted bounds; reject extremes |
| `protocol` | Select HTTP/TLS policy | Never allow metadata to downgrade security |
| `tenant` | May act as a hint in specialized architectures | Never use as proof of tenant authorization |

A simple validator can bound `weight` before feeding it to a custom algorithm:

~~~java
import java.util.Set;

final class RoutingMetadataPolicy {

    private static final Set<String> ALLOWED_ZONES =
        Set.of("zone-a", "zone-b");

    static boolean acceptable(String zone, String rawWeight) {
        if (zone == null || !ALLOWED_ZONES.contains(zone)) {
            return false;
        }

        try {
            int weight = Integer.parseInt(rawWeight);
            return weight >= 1 && weight <= 100;
        } catch (NumberFormatException ex) {
            return false;
        }
    }
}
~~~

This function **only checks value structure**; it does not verify who supplied `zone`/`weight`. Even with valid-looking values, an attacker with registry write access could still set `weight=100`. Therefore combine **trusted sources, restricted write permissions, and independent routing policies**.

Never emit raw metadata into logs or metric labels without length, encoding, and cardinality limits. An arbitrary `version` string thousands of characters long can break log readability, inflate observability costs, or crash custom parsers.

## 9. Health Checks Do Not Replace Identity Verification

A health check returning HTTP `200` only proves **the endpoint responded as probed**, not that it belongs to the legitimate service.

A spoofed instance can easily return:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"status":"UP"}
~~~

If the registry has been poisoned, `HealthCheckServiceInstanceListSupplier` may consider the spoofed endpoint healthy, depending on probe config. Therefore:

- **Verify the list source** before treating any instance as a candidate.
- Use **TLS/mTLS identity** for connections to instances.
- Restrict network access to health endpoints where possible.
- Treat health-check responses/policies as **availability** signals, never **authentication**.
- Never fall back from "no trusted instances" to "all instances" just to preserve success rates.

Some health suppliers have a fallback policy when no healthy instances exist; that mechanism serves availability. **Lists rejected by security policy must fail closed**, never mixed with health-check fallbacks.

## 10. Caching and the Risk of Retaining Revoked Routing Data

Caching instance lists reduces load on the registry but introduces a delay between deleting a record and clients stopping its use.

~~~mermaid
sequenceDiagram
    participant Admin as Control plane
    participant Reg as Registry
    participant Cache as Instance list cache
    participant LB as LoadBalancer
    participant Net as Network egress control

    Reg-->>Cache: Cache [A, B]
    Admin->>Reg: Revoke B because no longer trusted
    Reg-->>Admin: Deleted B
    LB->>Cache: Fetch list before TTL expires
    Cache-->>LB: [A, B] (stale)
    LB->>Net: Attempt connection to B
    Net--xLB: Policy blocks B if revoked at network layer
    Note over Cache: Cache refreshes per configured lifecycle
~~~

**Instance cache TTL is not a guaranteed security revocation deadline.** It is also affected by multiple cache/discovery tiers, push/watch mechanisms, polling intervals, and supplier ordering.

If a compromised instance must be revoked urgently, use **cache-independent controls** such as network egress policies, certificate/identity revocation, or shutting down access at the backend. Also provide cache refresh/invalidation so clients stop trying the old target.

Do not tweak cache durations arbitrarily while ignoring transport and access controls. Too low a cache TTL can overload the registry; too high a TTL prolongs routing to changed instances.

## 11. Where to Place Checks in the Supplier Chain

A logical chain typically looks like:

~~~text
Discovery source
    → service instance list
    → [zone / version / health / caching per config]
    → LoadBalancer selects target
    → HTTP client connects
~~~

Exact ordering depends on the `ServiceInstanceListSupplier` builder and enabled layers; there is no single universal order across all applications.

Security checkpoints should be layered:

1. **Control plane/registry:** block unauthorized registrations—the strongest protection at the source.
2. **Supplier/filter:** drop instances failing identity/scope/endpoint rules before selection.
3. **At the outbound request / network boundary:** block connections outside allowed destinations, even if caches or suppliers misfire.
4. **TLS + backend authorization:** reject callers lacking valid identity/permissions.

If a security filter sits *before* a cache that may hold previously permitted entries, understand whether **revocation** propagates promptly. For strict guarantees, re-apply checks at the final decision point or enforce independent network policies.

**Fail closed:** if no instance satisfies requirements, return an empty list/select no target and let the caller handle the error explicitly. Never "just try an arbitrary host" when trust evidence is missing.

## 12. Practice Example: Letting LoadBalancer Pick Only Approved Instances

This lab uses `SimpleDiscoveryClient` to simulate a list containing **two valid instances** and **one unlisted instance**. All addresses use `localhost`; no external IPs/hosts outside the test environment are used.

| Instance | Port | Role |
|---|---:|---|
| `catalog-a` | 18081 | Valid |
| `catalog-b` | 18082 | Valid |
| `catalog-extra` | 18083 | Simulates an unauthorized injected record |

Example `application.yml` on the caller:

~~~yaml
server:
  port: 18090

spring:
  application:
    name: order-service
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://localhost:18081
              - uri: http://localhost:18082
              - uri: http://localhost:18083
~~~

In the lab, HTTP simplifies local execution to focus on **instance-selection policy**. **Production must never copy this HTTP loopback allowance**: use HTTPS/mTLS, trusted identities, egress restrictions, and proper endpoint policies.

### 12.1. Creating a Test Service That Distinguishes Instances

On the backend using Spring Boot Web MVC:

~~~java
package demo.catalog;

import java.util.Map;

import org.springframework.core.env.Environment;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CatalogWhoAmIController {

    private final String instanceId;

    CatalogWhoAmIController(Environment environment) {
        this.instanceId = environment.getProperty(
            "instance.id", "catalog-unknown");
    }

    @GetMapping("/api/whoami")
    Map<String, String> whoami() {
        return Map.of("instanceId", instanceId);
    }
}
~~~

Requires `@SpringBootApplication` and the Spring Web dependency in the backend app. Assuming it is packaged as `catalog-service.jar`, run three separate processes:

~~~bash
java -jar catalog-service.jar --server.port=18081 --instance.id=catalog-a
java -jar catalog-service.jar --server.port=18082 --instance.id=catalog-b
java -jar catalog-service.jar --server.port=18083 --instance.id=catalog-extra
~~~

First verify all three instances return `200` for `/api/whoami` when called directly. Since all return valid responses, basic health checks alone cannot distinguish the out-of-policy instance.

### 12.2. Attaching a Dedicated Supplier Configuration per Service ID

In the caller, wire a dedicated config for `catalog-service`:

~~~java
package demo.caller;

import demo.lbconfig.CatalogSecurityLbConfig;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.loadbalancer.annotation.LoadBalancerClient;

@SpringBootApplication
@LoadBalancerClient(
    name = "catalog-service",
    configuration = CatalogSecurityLbConfig.class
)
public class OrderApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

`CatalogSecurityLbConfig` resides outside the package tree scanned by `@SpringBootApplication` by default so the specialized supplier is not accidentally registered into the root application context. `@LoadBalancerClient` loads it into the LoadBalancer child context for that specific service ID.

### 12.3. Allowlist-Filtering Supplier for the Lab

~~~java
package demo.lbconfig;

import java.util.List;
import java.util.Set;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.cloud.loadbalancer.core.ServiceInstanceListSupplier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import reactor.core.publisher.Flux;

@Configuration(proxyBeanMethods = false)
public class CatalogSecurityLbConfig {

    private static final String SERVICE_ID = "catalog-service";

    private static final Set<Integer> ALLOWED_LAB_PORTS =
        Set.of(18081, 18082);

    @Bean
    ServiceInstanceListSupplier allowedCatalogInstances(
            DiscoveryClient discoveryClient) {

        return new ServiceInstanceListSupplier() {
            @Override
            public String getServiceId() {
                return SERVICE_ID;
            }

            @Override
            public Flux<List<ServiceInstance>> get() {
                return Flux.defer(() -> {
                    List<ServiceInstance> allowed =
                        discoveryClient.getInstances(SERVICE_ID)
                            .stream()
                            .filter(CatalogSecurityLbConfig::isAllowedLab)
                            .toList();

                    return Flux.just(allowed);
                });
            }
        };
    }

    private static boolean isAllowedLab(ServiceInstance instance) {
        if (instance == null || instance.getUri() == null) {
            return false;
        }

        return SERVICE_ID.equals(instance.getServiceId())
            && "localhost".equalsIgnoreCase(instance.getHost())
            && ALLOWED_LAB_PORTS.contains(instance.getPort())
            && !instance.isSecure()
            && "http".equalsIgnoreCase(
                instance.getUri().getScheme());
    }
}
~~~

This is a **fixed verification policy strictly for the lab**. When discovery returns three replicas, the supplier keeps only A/B in the list. When none match, the supplier returns an **empty list**, never falling back to the original list.

**Important technical warnings:**

- This example **replaces the default supplier** for `catalog-service` and **does not automatically compose caching, health checks, or zone filters**. When moving to production, design/decorate the supplier chain properly to preserve existing features and verify execution order.
- `DiscoveryClient.getInstances(...)` is a blocking API. In the lab with in-memory `SimpleDiscoveryClient` it returns immediately; with remote discovery it can block threads. In production reactive pipelines, prefer reactive suppliers/discovery instead of calling blocking sources on event loops.
- Fixed host/port allowlists are useful to **demonstrate filtering**, not for dynamic autoscaling. Production should rely on **workload identity, policy control planes, and network egress**; checking DNS suffixes or host strings alone cannot defend against DNS rebinding or spoofed targets.
- `getUri()` and `isSecure()` both read from the `ServiceInstance` supplied by discovery. Checking that both match is basic validation; it **does not authenticate the source or TLS peer**.
- If other HTTP clients bypass the policy—such as a standalone `RestClient.create()` or a proxy calling direct URLs—the LoadBalancer filter cannot protect those paths. Network egress policies are an essential independent layer.

### 12.4. Creating a LoadBalanced RestClient

~~~java
package demo.caller;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
class ClientConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedBuilder() {
        return RestClient.builder();
    }

    @Bean
    RestClient catalogRestClient(
            @Qualifier("loadBalancedBuilder")
            RestClient.Builder builder) {

        return builder.baseUrl("http://catalog-service").build();
    }
}
~~~

A verification endpoint:

~~~java
package demo.caller;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;

@RestController
class LabController {

    private final RestClient client;

    LabController(RestClient catalogRestClient) {
        this.client = catalogRestClient;
    }

    @GetMapping("/demo/whoami")
    String whoami() {
        return client.get()
            .uri("/api/whoami")
            .retrieve()
            .body(String.class);
    }
}
~~~

When called repeatedly:

~~~bash
for i in $(seq 1 20); do
  curl -s http://localhost:18090/demo/whoami
  echo
done
~~~

Expected result once active: only `catalog-a` and `catalog-b` appear, **never `catalog-extra`**. This verifies the lab's supplier input policy; proving production security still requires TLS identity, RBAC, and network policy evidence.

## 13. How to Handle Metadata Tampering

In production, metadata can be updated while host/port remain unchanged. For example, an instance changes `zone=zone-b` to `zone=zone-a`, or raises `weight` from 10 to 100.

Countermeasures:

1. **Only authorized humans/automation** may mutate routing metadata.
2. **Validate schemas:** supported keys, valid values, lengths, and data types.
3. **Bound impact:** cap weights, require approval for canary percentages; never let the metadata itself govern those rules.
4. **Separate authorization from hints:** `tenant=abc` does not prove a workload is authorized to process tenant abc's data.
5. **Observe changes:** alert when instance counts, zone distribution, or weights shift abnormally.
6. **Rapid revocation:** support invalidating compromised instances outside cache windows.

A custom configuration might permit only `zone-a` and `zone-b`, dropping or alerting on anything else. Still, seeing `zone-a` in metadata does not prove an instance physically runs in zone-a if the source was compromised.

### Handling weight=0 or Very Large Weights

When using a weighted supplier or custom algorithm:

- Explicitly define what `weight=0` means and whether it is accepted.
- Never parse weights as unbounded integers and multiply/divide without overflow checks.
- Never allow an instance to edit its own weight to capture all traffic without authority.
- Never trust weight values sent in user request headers unless explicitly authorized and mapped.

How Spring Cloud LoadBalancer interprets weight metadata depends on version and enabled suppliers/policies; **not every `ServiceInstance.metadata["weight"]` automatically changes Round Robin**.

## 14. Protecting Authorization Headers and Tokens per Selected Target

A caller may send Bearer tokens or service-to-service credentials. If the instance list is altered to route requests to an untrusted target, tokens can leak.

Principles:

- **Never copy `Authorization` unconditionally** to every downstream.
- Tokens need the right **audience and scopes** for the receiving service, short lifetimes, and rotation.
- Control paths through trusted proxies/sidecars and mTLS where appropriate.
- Attach tokens only after verifying the target service and policy approval—never based on user-supplied hosts.
- Never put tokens into URLs, discovery metadata, logs, or metrics.
- Backends must **authenticate and authorize independently** instead of assuming any request reaching them is valid.

~~~mermaid
flowchart TD
    A["Caller wants to call catalog-service"] --> B["Resolve service ID per API contract"]
    B --> C["Discovery from access-controlled source"]
    C --> D["Policy filters trusted instances"]
    D --> E{"Any approved target?"}
    E -->|No| F["Fail closed / emit alert"]
    E -->|Yes| G["TLS/mTLS identity verification + egress"]
    G --> H["Send right-audience credential"]
    H --> I["Backend authenticates and authorizes operation"]
~~~

How OAuth2/OIDC or service account tokens are used depends on the environment. There is no rule saying "all internal requests share one token"; propagating tokens with the wrong audience can also cause **confused deputy** bugs, where a service uses its own permissions to access unauthorized resources on a caller's behalf.

## 15. Never Use Metadata as a Secret Store

Never place the following into `ServiceInstance.getMetadata()`:

- Database or Redis passwords.
- API keys, access tokens, or refresh tokens.
- Private keys or client certificates.
- Session cookies or authorization headers.
- Encryption keys, webhook secrets, or sensitive user data.

Metadata is distributed much more widely than a secret store: many callers read discovery to route requests, logs may dump entire metadata maps, and operational tooling often snapshots the registry.

When a service needs credentials, fetch them from a dedicated secret manager or identity provider with scoping, rotation, and auditing. Metadata should hold only **non-sensitive routing descriptors** with controlled write access.

## 16. Logging Metadata Safely and Avoiding Metric Cardinality

When debugging, teams are often tempted to write:

~~~java
// Discouraged: dumping uncontrolled metadata indiscriminately:
log.info("Selected instance metadata: {}", instance.getMetadata());
~~~

Risks:

- Misconfigured metadata may contain sensitive data.
- Strings with newlines/control characters corrupt logs or cause log injection.
- Dynamic values like request IDs or long URLs trigger high metric cardinality.
- Logs become a secondary channel leaking stolen data.

Instead, log **approved and normalized fields**, for example:

~~~java
String zone = instance.getMetadata().get("zone");
String safeZone =
    ("zone-a".equals(zone) || "zone-b".equals(zone))
        ? zone
        : "unknown";

log.info(
    "Selected serviceId={}, instanceId={}, zone={}",
    instance.getServiceId(),
    instance.getInstanceId(),
    safeZone
);
~~~

This snippet assumes a logger `log` exists. Before production, also ensure `instanceId` cannot hold unexpected data and enforce length/character bounds. Never create Prometheus labels from unconstrained `instanceId`/`version` values.

## 17. Detecting Registry Poisoning and Anomalous Changes

Useful signals:

| Metric / Audit Event | Signal |
|---|---|
| Instance count per service ID | Unexpected spike or drop |
| Count of policy-rejected instances | Records violating trust rules |
| Host/port/scheme mutations | Endpoints may have been altered without authorization |
| Zone/version/weight distribution | Large swings in routing metadata |
| Registry write/delete events | Who edited an entry, when, and from which pipeline |
| TLS handshake failures | Identity/certificate or config mismatch |
| Network egress denies | Caller attempted to reach an unapproved target |
| Service ID lookup failures | Renamed service, missing permissions, or broken discovery source |
| Cache age/refresh failures | Stale data lingering too long |
| Health state transitions | Flapping or manipulated probes |
| Selected instance vs. actual peer | Reconciling routing decisions with actual connections |

Do not assume Spring Cloud LoadBalancer emits all these metrics out of the box. Many signals come from registry audits, Kubernetes audit logs, HTTP connectors, network policy logs, application instrumentation, or tracing.

When an anomalous record appears, follow an isolation runbook: verify ownership, revoke write access, purge the entry from the source, revoke related credentials/certificates, block egress if needed, invalidate caches, and inspect logs for requests routed to that target.

## 18. Incident Response Priority Order

An incident response workflow may follow:

1. **Triage risk:** purely operational metadata typo, or did addresses divert traffic to an unauthorized target?
2. **Block dangerous paths:** network policy/egress deny, revoke mTLS identities or keys if compromise is suspected.
3. **Lock down source write access:** tighten RBAC/ACLs, revoke compromised admin tokens or accounts.
4. **Clean registry/config:** delete bad records or restore approved metadata.
5. **Sync clients:** refresh discovery/caches, confirm the post-supplier instance set.
6. **Assess blast radius:** inspect traces/request logs to see which requests reached the suspect target.
7. **Rotate secrets:** if tokens may have been sent to an untrusted target, rotate/revoke them promptly.
8. **Add guardrails:** admission policies, auditing, controlled canaries, and regression tests.

**Deleting a record from the registry does not make every caller stop connecting instantly**; caches, in-flight requests, and connection pools remain. That is why network/identity-level blocks are crucial for emergency revocation.

## 19. Security Testing for ServiceInstanceListSupplier

A test suite should separate **validation**, **authorization**, **transport identity**, and **behavior when candidates vanish**.

| Scenario | Test | Expectation |
|---|---|---|
| Two valid instances | Discovery returns A/B | Can select A/B |
| Added `catalog-extra` instance | Port 18083 is outside allowlist | `catalog-extra` never seen via caller |
| Altered port on A | A switches to out-of-policy port | A is filtered out |
| Altered service ID | Record no longer matches `catalog-service` | Excluded |
| All replicas invalid | Supplier has zero candidates | **Fail closed**, never send requests to unapproved targets |
| Invalid weight metadata | Parsing/validation | Reject/quarantine per policy |
| Spoofed zone metadata | Registry permits bad writes | Caught by authority/policy, not schema alone |
| Registry credentials lack permission | Discovery cannot read | Error classified; no arbitrary fallback |
| Registry uses TLS with wrong cert | Handshake/identity verification | Connection rejected |
| Instance returns health 200 with wrong identity | Health check alone passes | Transport/authentication rejects |
| Cache holds recently revoked record | TTL has not expired | Egress policy still blocks target |
| Retry switches instance | Attempt picks another target | Every attempt passes through policy |
| Differently configured RestClient/WebClient/Feign | One client bypasses LoadBalancer | Test catches and removes bypass path |
| Request carries Bearer token | Rogue instance registered | Token never sent to out-of-scope target |
| Metadata contains newlines/secrets | Logging/metrics | Sanitized; raw values never leaked |

In section 12's lab, you can inspect the `instanceId` response body. For stronger assurance, write integration tests with stub servers on each port and assert zero requests actually arrive at `18083`; eyeballing a few responses is not absolute proof an out-of-policy target was never chosen.

### Side Test: Empty Allowlist

Change `ALLOWED_LAB_PORTS` to an empty set in a test environment and invoke the caller. Expect zero HTTP requests reaching any of the three backends. The exact exception class/caller HTTP error response varies by client and error mapping, so avoid hardcoding a single exception class in tests across library versions.

**Never** add an `if (allowed.isEmpty()) return rawList;` branch. Under a trust policy, that re-opens traffic to targets just deemed untrusted.

## 20. Common Design Mistakes

1. **Trusting `serviceId` or `trusted=true` in metadata as proof of identity.**
2. **Granting all workloads permission to write/delete other services' instances in the registry.**
3. **Disabling TLS hostname verification** because certificates do not match LoadBalancer-selected physical hosts.
4. **Enabling only health checks and treating every `200` instance as trustworthy.**
5. **Letting metadata from external requests/headers pick zones, weights, or target hosts** without authorization.
6. **Stuffing tokens/secrets into metadata** for convenient reading on the caller side.
7. **Using host-suffix allowlists without DNS, IP, or egress checks**, easily tricked by unusual configurations.
8. **Filtering in one supplier while letting another HTTP client call directly**, bypassing policy.
9. **Allowing fallback from a security-rejected list back to the full unfiltered instance list.**
10. **Treating cache TTL as a fast-enough security revocation mechanism.**
11. **Failing to audit registry/ConfigMap mutations**, making routing hijacks hard to trace.
12. **Using unbounded weights/zones/versions without authenticating who updated them.**
13. **Dumping all metadata into logs or metrics**, causing data leaks or cardinality explosions.
14. **Assuming the discovery endpoint's TLS certificate proves the identity of every backend.**
15. **Reusing one overly privileged token** across downstreams of different trust levels.
16. **Hardcoding lab host/port allowlists in production autoscaling**, breaking discovery while proving no identity.
17. **Adding a security filter while forgetting to preserve caching/health chains**, altering availability unexpectedly.
18. **Relaxing checks when no valid instance exists** just to avoid "no server available" errors.
19. **Failing to track `selectedInstance` vs. `actualPeer`** when investigating misrouting.
20. **Failing to separate security policy rejections from discovery/transport errors** in observability.

## 21. Secure Deployment Checklist

Before deploying a client-side LoadBalancer to production, answer:

- Who can **register/edit/delete** records for each service ID?
- Are RBAC/ACLs, audit logs, and approval workflows in place for routing metadata?
- Does the discovery client use an **authenticated and encrypted channel**?
- Are **hosts/ports/schemes** constrained by policies independent of self-declared metadata?
- Does the HTTP connector **verify TLS peer identity** with SAN/SNI aligned to the connection path?
- Does the caller have **network egress policies** preventing connections outside approved scopes?
- Which `ServiceInstance`s get rejected by policy, and what happens when the filtered list is empty?
- Are there bypass gaps via `RestClient.create()`, non-`@LoadBalanced` WebClients, or fixed-`url` Feign clients?
- Do `zone`, `weight`, and `version` fields have trustworthy sources and owners?
- Is metadata validated for type, range, length, and logging safety?
- Are health checks treated strictly as **availability**, never authentication?
- Are caching and TTLs compatible with emergency revocation needs?
- Do tokens carry the right audience/scope for downstream without unconditional forwarding?
- Does the backend authorize operations independently of network reachability?
- Are telemetry/audits sufficient to investigate rogue instances, stale caches, unauthorized writes, and TLS failures?
- Have you tested disallowed instances, wrong schemes, under-permissioned registries, and fail-closed policies?
- When metadata changes abruptly, are alerts and rollback/recovery procedures ready?

## 22. Conclusion

**`ServiceInstance` lists and routing metadata are security-sensitive control data.** An unauthorized change in **a service registry, config source, or supplier chain** can steer requests to wrong hosts/ports, skew zones/weights, and leak credentials. Using HTTPS on business APIs or enabling health checks alone **is not enough** to prove the instance list source is trustworthy.

In Spring Cloud LoadBalancer, defend every boundary: **RBAC/ACLs and auditing at the discovery source; validation/fail-closed behavior in suppliers; egress restrictions and TLS/mTLS identity at transport; and authorization at the target service**. Across RestClient, WebClient, and OpenFeign, ensure all service-ID calls obey the defined policy consistently, backed by independent network controls in case a client is misconfigured.

The operational principle is **control who may mutate metadata, understand how it affects routing, and verify the chosen destination is genuinely authorized**. Combining those layers with caching/health checks, bounded retries/timeouts, and observability keeps service-to-service communication resilient without turning metadata or discovery into a bypass around security controls.
