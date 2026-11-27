# Kubernetes Client Options and Usage Scope

## Objectives

After this lesson, you will be able to:

- Distinguish Kubernetes Service DNS from Spring Cloud Kubernetes `DiscoveryClient`.
- Choose between Fabric8 Kubernetes Client, Kubernetes Java Client, and HTTP DiscoveryClient.
- Understand when deploying Spring Cloud Kubernetes Discovery Server is needed.
- Configure dependencies, namespace scope, service filters, and RBAC permissions at the required level.
- Evaluate the impact of EndpointSlice, caching, and instance selection on application architecture.

## 1. Not every application needs a Kubernetes API client

Kubernetes already provides a service lookup mechanism through Services and DNS. An application running in the cluster can call a Service by DNS name, such as `inventory` or `inventory.commerce.svc.cluster.local`. The Kubernetes Service provides a stable address; the cluster's dataplane forwards traffic to an eligible backend.

Spring Cloud Kubernetes adds implementations of Spring Cloud abstractions such as `DiscoveryClient` so applications can query service and instance lists via a Java API. This is useful when an application needs to know individual endpoints, read metadata, filter by namespace/label, or integrate with Spring Cloud LoadBalancer.

Current Spring Cloud Kubernetes documentation supports three types of `DiscoveryClient`:

1. Fabric8 Kubernetes Client.
2. Kubernetes Java Client.
3. HTTP-based DiscoveryClient connecting to Spring Cloud Kubernetes Discovery Server.

Spring Cloud Kubernetes documentation illustrates enabling discovery with `@EnableDiscoveryClient`. Auto-configuration behavior also depends on version and cloud platform detection; check the configuration for the release train in use if the bean is not created.

Beyond those three options, calling Kubernetes Service DNS directly is a native choice that does not require adding Spring Cloud Kubernetes just to resolve hostnames. Spring Cloud Kubernetes is a helpful integration library, not a mandatory requirement for running Spring Boot on Kubernetes.

## 2. Four approaches and their scope

| Option | How information is obtained | Required components | Best suited when |
| --- | --- | --- | --- |
| Kubernetes Service DNS | Resolves the Service hostname via in-cluster DNS. | Kubernetes Service and cluster DNS. | You only need to call a stable service address and do not need an instance list in code. |
| Fabric8 DiscoveryClient | Application calls the Kubernetes API via the Fabric8 client. | Fabric8 starter, ServiceAccount/RBAC, or kubeconfig. | You want to use Spring Cloud DiscoveryClient and the Fabric8 ecosystem. |
| Kubernetes Java Client DiscoveryClient | Application calls the Kubernetes API via Kubernetes Java Client. | Kubernetes Client starter, ServiceAccount/RBAC, or kubeconfig. | You want to use the official Kubernetes Java client and its models/APIs. |
| HTTP DiscoveryClient | Application calls Discovery Server over HTTP; the server queries the Kubernetes API. | HTTP discovery starter on the client and Discovery Server in the cluster. | You want to centralize Kubernetes API access permissions in a separate component. |

Do not treat these four options as different names for the same mechanism. DNS returns addresses according to Service DNS rules; the two API clients query the Kubernetes API directly; the HTTP client queries an intermediary discovery service.

## 3. Option 1: Kubernetes Service DNS

Every Kubernetes Service can be accessed by its DNS name. For example, a Service `inventory` in the `commerce` namespace typically has the fully qualified name:

~~~~text
inventory.commerce.svc.cluster.local
~~~~

Pods in the same namespace can use the short name `inventory`. Pods in another namespace should specify the namespace, such as `inventory.commerce`. The cluster domain suffix can be configured differently per cluster.

For a ClusterIP Service, DNS resolves the name to a stable ClusterIP. The Kubernetes dataplane forwards traffic from the ClusterIP to matching endpoints. The application only needs to know the Service hostname and port:

~~~~java
import org.springframework.web.reactive.function.client.WebClient;

public class InventoryGateway {

    private final WebClient webClient;

    public InventoryGateway(WebClient.Builder builder) {
        this.webClient = builder
                .baseUrl("http://inventory.commerce.svc.cluster.local")
                .build();
    }

    public String getStatus() {
        return webClient.get()
                .uri("/actuator/health")
                .retrieve()
                .bodyToMono(String.class)
                .block();
    }
}
~~~~

The example above calls the Service via DNS. The application does not need to call the Kubernetes API to retrieve Pod IPs, does not need `DiscoveryClient`, and does not need `list/watch` permissions on Services or Endpoints just to perform a DNS lookup.

### Headless Service

If a Service sets `clusterIP: None`, DNS can return the addresses of Pod endpoints instead of a shared ClusterIP. This model fits when the client needs to know each Pod, such as certain stateful systems. When using a headless Service, the application or networking library must handle multiple addresses and endpoint changes across the Pod lifecycle.

### Scope and limitations

- DNS provides a hostname and addresses; it does not return full Kubernetes metadata as `ServiceInstance` objects.
- ClusterIP gives callers a single stable access point; backend selection is handled by the Kubernetes dataplane.
- A headless Service can return multiple Pod addresses; distribution and DNS caching depend on the resolver and client.
- DNS does not cover needs such as filtering services by label, reading namespace metadata, or querying instance lists from Java.
- An `ExternalName` Service resolves via a DNS CNAME; this is a special DNS case.

On the Spring Cloud Kubernetes side, `ExternalName` Services are not included in `getInstances()` results by default. If you need discovery for this Service type, enable `spring.cloud.kubernetes.discovery.include-external-name-services=true` according to the version in use.

Choose DNS when the application only needs to call a Service within the cluster. If business requirements call for reading individual endpoints, metadata, or selecting instances yourself via Spring Cloud LoadBalancer, consider DiscoveryClient.

## 4. Option 2: Fabric8 Kubernetes Client

Fabric8 is a Java client library providing a fluent DSL API for communicating with the Kubernetes API server. Spring Cloud Kubernetes provides a Fabric8 integration starter:

### Maven dependency

~~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-kubernetes-fabric8</artifactId>
</dependency>
~~~~

Import the Spring Cloud BOM compatible with your project's Spring Boot version and let the BOM manage the starter version. Do not manually choose a Fabric8 version different from Spring Cloud Kubernetes dependency management.

This starter provides a `DiscoveryClient` implementation based on Fabric8. Applications can inject the Spring Cloud abstraction instead of calling the Fabric8 API directly in business code:

~~~~java
import java.util.List;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Service;

@Service
public class ServiceCatalog {

    private final DiscoveryClient discoveryClient;

    public ServiceCatalog(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public List<String> listServices() {
        return discoveryClient.getServices();
    }

    public List<ServiceInstance> findInstances(String serviceId) {
        return discoveryClient.getInstances(serviceId);
    }
}
~~~~

`getServices()` returns the names of Kubernetes Services currently visible to the client. `getInstances(serviceId)` returns the list of `ServiceInstance` objects corresponding to that service.

`getServices()` returns unique service names, even if the same name appears in multiple namespaces. `getInstances()` adds namespace and instance metadata so callers have more context. If multiple namespaces contain Services with the same name, restrict namespaces or filter by label to avoid selecting the wrong one. For Services with multiple ports, name ports clearly and configure the primary port instead of relying on picking the first port.

### When to choose Fabric8?

- The project already uses Fabric8 to work with Kubernetes resources.
- The team is familiar with its fluent DSL and `io.fabric8.kubernetes.api.model` models.
- You want to use the same client for discovery and other Spring Cloud Kubernetes integrations that support Fabric8.
- You want to run the application outside the cluster for development/debugging using an appropriate Kubernetes client configuration, such as kubeconfig.

Fabric8 is a client library. It does not replace the Kubernetes API server, scheduler, or cluster dataplane. Application access permissions must still be restricted via ServiceAccount/RBAC or appropriate credentials.

## 5. Option 3: Kubernetes Java Client

Kubernetes Java Client is the official Kubernetes Java library, providing Java APIs and models corresponding to the Kubernetes API. Spring Cloud Kubernetes integrates this client through a separate starter:

### Maven dependency

~~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-kubernetes-client</artifactId>
</dependency>
~~~~

This starter also provides a `DiscoveryClient` implementation. At the Spring Cloud layer, calling `getServices()` and `getInstances()` is identical to the Fabric8 option. Differences lie in the underlying Kubernetes library, Java models, and low-level client customization.

For example, SpEL filters for this client are evaluated against `io.kubernetes.client.openapi.models.V1Service`. With Fabric8, the corresponding model is `io.fabric8.kubernetes.api.model.Service`. Therefore, if an application uses custom filters or accesses client models directly, it must be written for the specific client chosen.

### When to choose Kubernetes Java Client?

- The project wants to use the official Java library maintained by Kubernetes SIG API Machinery.
- The team already has code or utilities built on `io.kubernetes.client` models.
- You want consistency with internal integrations already using Kubernetes Java Client.
- You need to work directly with APIs/models provided by the official library.

Choosing the official client does not automatically make discovery faster or reduce RBAC permissions. Both Fabric8 and Kubernetes Java Client need access to the API server, read the appropriate resources, and require matching permissions.

### Do not mix both client families in the same application

Spring Cloud Kubernetes requires choosing one of the two client families. Do not combine starters starting with `spring-cloud-starter-kubernetes-fabric8` and starters starting with `spring-cloud-starter-kubernetes-client` in the same application. Choose one implementation and consistently use starters from that family.

Example:

~~~~text
Allowed:
- spring-cloud-starter-kubernetes-fabric8
- spring-cloud-starter-kubernetes-fabric8-config

Or:
- spring-cloud-starter-kubernetes-client
- spring-cloud-starter-kubernetes-client-config

Do not select both groups at the same time.
~~~~

If the application only needs discovery, use the corresponding discovery starter. Starters with the `-config` suffix are for reading ConfigMaps/Secrets; starters with the `-all` suffix bring in more features. There is no need to pull in every feature if the application only queries Services.

## 6. Option 4: HTTP DiscoveryClient and Discovery Server

Spring Cloud Kubernetes provides an HTTP-based `DiscoveryClient` implementation:

~~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-kubernetes-discoveryclient</artifactId>
</dependency>
~~~~

This starter is designed to be used with Spring Cloud Kubernetes Discovery Server. Discovery Server runs in the cluster, queries the Kubernetes API, and exposes HTTP endpoints for applications to fetch service/instance lists.

Main Discovery Server endpoints:

| Endpoint | Content |
| --- | --- |
| `GET /apps` | List of services and instance details. |
| `GET /apps/{name}` | List of instances for a given service. |
| `GET /app/{name}/{instanceid}` | Details of a specific instance. |

Workflow:

~~~~mermaid
flowchart LR
    A[Spring Boot app] -->|HTTP DiscoveryClient| D[Discovery Server]
    D -->|Kubernetes API| K[Kubernetes API Server]
    K -->|Services, Pods, Endpoints| D
    D -->|ServiceInstance JSON| A
~~~~

### Access permission scope

Discovery Server needs a ServiceAccount and RBAC permissions to read Pods, Services, and Endpoints. An application consuming HTTP DiscoveryClient only needs reachability to Discovery Server's HTTP endpoints; it does not need Kubernetes API read permissions simply for using HTTP DiscoveryClient. If the application also uses other Kubernetes features, those permissions must still be granted separately.

### When to choose HTTP DiscoveryClient?

- Multiple applications need the same discovery source and you want to centralize Kubernetes API access permissions.
- You do not want every application carrying a Kubernetes API client or a ServiceAccount with resource read permissions.
- You can operate Discovery Server as a shared infrastructure component.
- You want to provide an HTTP boundary for applications running outside the cluster or not integrating directly with the Kubernetes API.

### Trade-offs

- Adds an intermediary service and an extra network hop.
- Discovery Server becomes a component that must be deployed, monitored, scaled, and secured.
- Namespace/filter configuration lives on the server; HTTP clients do not independently decide the API scope the server queries.
- If the catalog watcher is enabled, configuration must be enabled properly on both server and client per supported version.
- HTTP DiscoveryClient and Discovery Server versions must be aligned to avoid API contract differences.

HTTP DiscoveryClient is useful when centralizing permissions and reducing the number of applications calling the Kubernetes API directly. For a small application that only needs a single Service DNS name, deploying Discovery Server is usually unnecessary.

## 7. Namespace scope: where to look for services?

When using DiscoveryClient to query the Kubernetes API, you must define which namespaces the client is allowed to search. Spring Cloud Kubernetes supports three modes:

### Single namespace

This is the default mode if no other option is declared. The application searches for services in the namespace determined by namespace resolution rules, typically the namespace where the Pod is running.

### Specific namespaces

Example:

~~~~yaml
spring:
  cloud:
    kubernetes:
      discovery:
        namespaces:
          - commerce
          - platform
~~~~

Searches for services only in the selected namespaces. This is usually the right choice when an application needs to call a few service groups across specific namespaces.

### All namespaces

~~~~yaml
spring:
  cloud:
    kubernetes:
      discovery:
        all-namespaces: true
~~~~

This mode can increase the number of resources read/watched, load on the Kubernetes API server, and application cache memory. It also requires broader RBAC permissions, typically a ClusterRole/ClusterRoleBinding. Enable it only when genuinely needed and after evaluating permission scope.

With HTTP DiscoveryClient, namespace configuration is set on Discovery Server via deployment environment variables, not solely on the HTTP client application.

## 8. Filtering services and shrinking the catalog

By default, DiscoveryClient can see every Service in the selected namespace scope. When a namespace has many Services, narrow the dataset using labels:

~~~~yaml
spring:
  cloud:
    kubernetes:
      discovery:
        service-labels:
          discovery-enabled: "true"
          team: commerce
~~~~

Only Services with all matching labels are included in discovery results. Spring Cloud Kubernetes documentation notes that implementations use an asynchronously populated lister/cache; label filtering helps shrink the set of Services held in cache.

You can use SpEL via `spring.cloud.kubernetes.discovery.filter` for finer-grained filtering. The model type in the expression depends on the client:

| Client | Service model type in SpEL |
| --- | --- |
| Fabric8 | `io.fabric8.kubernetes.api.model.Service` |
| Kubernetes Java Client | `io.kubernetes.client.openapi.models.V1Service` |
| HTTP DiscoveryClient | `io.kubernetes.client.openapi.models.V1Service` on Discovery Server |

SpEL is evaluated in a read-only context and does not permit arbitrary method calls. Use SpEL operators and map indexing as documented. Avoid expressions that depend on disallowed method invocations.

## 9. Endpoints and EndpointSlices

DiscoveryClient needs to know the backend addresses of a Service. Spring Cloud Kubernetes currently uses the `Endpoints` API by default; `EndpointSlices` can be enabled with:

~~~~yaml
spring:
  cloud:
    kubernetes:
      discovery:
        use-endpoint-slices: true
~~~~

EndpointSlice is the Kubernetes API for representing backend endpoints in slices, helping Services support large numbers of backends and update endpoints more efficiently. A Service can have multiple EndpointSlices; slices are linked by the `kubernetes.io/service-name` label.

Before enabling EndpointSlice:

- Confirm the Kubernetes cluster supports the `discovery.k8s.io/v1` API.
- Confirm the Spring Cloud Kubernetes version in use supports this property.
- Grant RBAC `get`, `list`, `watch` permissions on the `endpointslices` resource.
- Verify application startup, because enabling EndpointSlice on an unsupported cluster can prevent the application from starting.

Example Role rule in a single namespace:

~~~~yaml
rules:
  - apiGroups: ["discovery.k8s.io"]
    resources: ["endpointslices"]
    verbs: ["get", "list", "watch"]
~~~~

Do not enable EndpointSlice simply because it is a newer API. Consider endpoint scale, cluster version, compatibility, and actual access permissions.

## 10. RBAC and Kubernetes API authentication

When Fabric8 or Kubernetes Java Client calls the API server directly, the application needs authentication credentials and read permissions on resources. Inside the cluster, this typically uses the ServiceAccount attached to the Pod. Outside the cluster, the client can use kubeconfig or credentials provisioned per environment policy.

An illustrative minimal Role for discovery in a single namespace:

~~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: service-discovery-reader
  namespace: commerce
rules:
  - apiGroups: [""]
    resources: ["services", "endpoints"]
    verbs: ["get", "list", "watch"]
~~~~

If reading Pod labels/annotations is enabled or Discovery Server needs Pod details, add `pods` to `resources`. Do not grant Pod read permissions if the application does not use that data.

Bind the Role to the workload's ServiceAccount using a RoleBinding:

~~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: inventory-discovery-reader
  namespace: commerce
subjects:
  - kind: ServiceAccount
    name: inventory-service
    namespace: commerce
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: service-discovery-reader
~~~~

This is a basic example. Grant only the resources actually used by enabled features. If only reading Services and Endpoints, do not grant write permissions. If enabling Pod metadata or EndpointSlices reading, add the corresponding read permissions. For multiple namespaces, consider per-namespace Roles/RoleBindings; use ClusterRole/ClusterRoleBinding only when cluster-wide scope is truly needed.

Discovery Server needs permission to read Pods, Services, and Endpoints to aggregate data. Roles can be granted per namespace that the server is allowed to read. Protect Discovery Server's HTTP endpoints via internal networking, authentication, and appropriate access policies; do not turn the discovery API into a public endpoint.

## 11. Using DiscoveryClient and LoadBalancer in their proper roles

Example injecting Spring Cloud `DiscoveryClient`:

~~~~java
import java.util.List;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Service;

@Service
public class InventoryDiscovery {

    private final DiscoveryClient discoveryClient;

    public InventoryDiscovery(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public List<ServiceInstance> instances() {
        return discoveryClient.getInstances("inventory");
    }
}
~~~~

`DiscoveryClient` provides the list of instances currently known to the client. If you want to call a service by name and choose an instance per request, integrate Spring Cloud LoadBalancer with the corresponding HTTP client. Do not assume that merely adding DiscoveryClient makes every HTTP request automatically load-balanced.

Distinguish the two paths:

- **Service DNS:** caller invokes the Service hostname; the Kubernetes dataplane picks the backend.
- **DiscoveryClient + LoadBalancer:** the application retrieves the instance list; Spring Cloud LoadBalancer picks an instance on the client side.

If you pick a Pod IP instance from DiscoveryClient and then send the request through a Service's ClusterIP, two backend selections can occur. This is occasionally intentional, but it must be clearly understood to avoid confusion around sticky sessions, health state, and locality.

In addition, `spring.application.name` does not automatically create or rename a Kubernetes Service. If a Spring Cloud component needs to look up the local service instance by application name, the Kubernetes Service name must be aligned with `spring.application.name`.

## 12. Choosing a client by scenario

| Scenario | Recommended option | Reason |
| --- | --- | --- |
| Application only calls an internal Service | Kubernetes Service DNS | Minimal dependencies, no Kubernetes API read permissions required. |
| Application needs `getServices()`/`getInstances()` and team knows Fabric8 | Fabric8 DiscoveryClient | Uses Spring abstractions alongside Fabric8 APIs/models. |
| Project has standardized on Kubernetes Java Client | Kubernetes Java Client DiscoveryClient | Uses the same client/models as existing integration code. |
| Many apps need discovery without each having cluster-read RBAC | HTTP DiscoveryClient + Discovery Server | Centralizes Kubernetes API access and permissions on the server. |
| Need to filter services by namespace/label and select Pods client-side | Fabric8 or Kubernetes Java Client + LoadBalancer | Provides instance lists and metadata for client-side selection logic. |
| Services have many endpoints and need high scale | Evaluate EndpointSlices | Uses the modern endpoint API when supported by the cluster and Spring Cloud version. |

There is no single client that is always best for every system. Choose based on API needs, permission model, libraries the team already uses, number of applications, number of namespaces, and operational cost of Discovery Server.

## 13. Common errors

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| `DiscoveryClient` bean is not created | Missing starter, cloud platform config, or incompatible auto-configuration. | Check dependencies, condition evaluation logs, and Spring Cloud Kubernetes config. |
| HTTP 403 from Kubernetes API | ServiceAccount lacks Role/ClusterRole or missing verb/resource. | Check the Pod's ServiceAccount and run `kubectl auth can-i` for that identity. |
| Only finds Services in the current namespace | Discovery is using the default namespace scope. | Configure the namespace list or `all-namespaces` if genuinely needed. |
| Cluster-wide discovery is slow | Scanning too many namespaces/resources or cache is too large. | Restrict namespaces, filter by label, and monitor API server load. |
| Fails to start with EndpointSlice enabled | Cluster does not support the API or RBAC lacks `endpointslices`. | Check the `discovery.k8s.io/v1` API and get/list/watch permissions. |
| Two Kubernetes client types conflict | Both Fabric8 and Kubernetes Java Client starters were added. | Keep only one consistent starter family. |
| HTTP DiscoveryClient cannot find services | Discovery Server is not running, wrong URL, or server scope excludes that namespace. | Check server endpoints, server logs, and deployment configuration. |
| SpEL filter does not work | Expression uses the other client's model or calls a forbidden method. | Use the right Service model and supported read-only syntax. |
| Service name differs from Spring application | `spring.application.name` does not automatically change the Kubernetes Service's `metadata.name`. | Align names in the Service manifest and application configuration. |
| Empty instance list or wrong port | Service has no ready endpoints or port selection is ambiguous. | Check selector, readiness, Endpoints/EndpointSlices, and port names. |

## 14. Pre-selection checklist

- [ ] Determine whether the application only needs a DNS hostname or needs an instance list via `DiscoveryClient`.
- [ ] If using an API client, choose either Fabric8 or Kubernetes Java Client; do not mix both starter families.
- [ ] Import the Spring Cloud BOM compatible with Spring Boot.
- [ ] Choose the smallest namespace scope that meets requirements.
- [ ] Use service labels/filters to shrink the catalog if the cluster has many Services.
- [ ] Grant read-only RBAC to the right ServiceAccount and resources.
- [ ] Enable EndpointSlice only when the cluster, library version, and RBAC all support it.
- [ ] If using HTTP DiscoveryClient, deploy and secure Discovery Server.
- [ ] Align Discovery Server and HTTP client versions.
- [ ] Explicitly decide which layer selects backends: Kubernetes dataplane or Spring Cloud LoadBalancer.
- [ ] Verify the Kubernetes Service name matches `spring.application.name` when Spring components need to look up the local instance.
- [ ] Monitor caching, API server load, 403 errors, endpoint readiness, and refresh times.

## Key takeaways

- Kubernetes Service DNS is a simple option when an application only needs a stable hostname inside the cluster.
- Spring Cloud Kubernetes supports Fabric8, Kubernetes Java Client, and HTTP DiscoveryClient backed by Discovery Server.
- Fabric8 and Kubernetes Java Client starters must not be mixed in the same application.
- The two direct clients require RBAC to read resources; HTTP Discovery Server keeps API read permissions on the server side.
- Namespace scope, label filters, and EndpointSlices affect data volume, permissions, and Kubernetes API load.
- `DiscoveryClient` provides the instance list; Spring Cloud LoadBalancer handles instance selection when integrated.
- Choose a client based on permission scope, endpoint needs, existing libraries, and operational overhead—not merely library name.

## Official references

- [Spring Cloud Kubernetes – DiscoveryClient](https://docs.spring.io/spring-cloud-kubernetes/reference/discovery-client.html)
- [Spring Cloud Kubernetes – Starters](https://docs.spring.io/spring-cloud-kubernetes/reference/getting-started.html)
- [Spring Cloud Kubernetes – Discovery Server](https://docs.spring.io/spring-cloud-kubernetes/reference/spring-cloud-kubernetes-discoveryserver.html)
- [Spring Cloud Kubernetes – Project Overview](https://docs.spring.io/spring-cloud-kubernetes/reference/index.html)
- [Kubernetes – Service](https://kubernetes.io/docs/concepts/services-networking/service/)
- [Kubernetes – DNS for Services and Pods](https://kubernetes.io/docs/concepts/services-networking/dns-pod-service/)
- [Kubernetes – EndpointSlices](https://kubernetes.io/docs/concepts/services-networking/endpoint-slices/)
