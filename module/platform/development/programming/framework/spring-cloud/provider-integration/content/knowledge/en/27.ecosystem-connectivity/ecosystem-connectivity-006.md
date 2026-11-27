# Boundaries with Service Discovery, Kubernetes, and Service Brokers

## 1. Context and Objectives

In the **Spring Cloud Provider Integration** module, Spring Boot applications connect to managed services from AWS, Azure, and Google Cloud via the corresponding Spring Cloud libraries, SDKs, and connectors. When a system is split into multiple services, an application must solve three distinct questions:

- **Service Discovery:** where is the target service located, and which endpoints are currently available?
- **Service Binding:** how does an application receive endpoints, resource metadata, and authentication details to connect to a service instance?
- **Service Broker:** who provisions, binds, unbinds, updates, or deprovisions a managed service at the platform's request?

These questions are related, yet they sit on different architectural boundaries. Discovery primarily helps locate and route to running services. Binding supplies connection data to workloads. Brokers manage resource lifecycles via the control plane. Kubernetes adds primitives such as Services, DNS, EndpointSlices, Ingress/Gateway, and discovery APIs. Spring Cloud provides abstractions for discovery clients and load balancing, but it does not replace Kubernetes networking or service broker APIs.

This lesson helps learners clearly separate these components, choose the right mechanism for a runtime/platform, understand how Spring Cloud DiscoveryClient and Spring Cloud Kubernetes operate, and identify equivalent or near-equivalent services across AWS, Azure, and Google Cloud.

After this lesson, you will be able to:

1. Distinguish between service discovery, service binding, service brokers, and service meshes.
2. Describe discovery and request routing flows in a Spring Boot application.
3. Explain Kubernetes Services, DNS, EndpointSlices, and the kube-proxy/data plane.
4. Use Spring Cloud DiscoveryClient and Spring Cloud LoadBalancer where appropriate.
5. Choose among Kubernetes-native discovery, Eureka, Consul, or DNS-based discovery.
6. Distinguish the Open Service Broker API from the Kubernetes Service Binding Specification.
7. Compare AWS Cloud Map, Azure discovery options, and Google Cloud Service Directory/DNS.
8. Identify boundaries across control plane, data plane, identity, and network policies.
9. Test discovery, failover, endpoint updates, and broker lifecycles.
10. Design observability, security, and runbooks for production.

> **Scope:** Service Discovery locates service endpoints; Service Binding supplies connection details; Service Brokers manage service instance/binding lifecycles. A platform may integrate multiple mechanisms, yet they should not be treated as a single API or component.

## 2. Four Concepts to Keep Separate

### 2.1. Service Discovery: Locating Service Addresses

Suppose the Reservation Service needs to call the Pricing Service. Locally, the address might be localhost on a fixed port. In production, the Pricing Service runs multiple replicas whose IPs change during rollouts or scaling. Hard-coding an IP in application config quickly renders clients stale.

Service discovery provides a way to look up current endpoints by logical service name. Clients or load balancers query a registry, DNS, or platform API to obtain one or more instances:

~~~mermaid
flowchart LR
    A["Reservation Service"] --> B["Discovery client / DNS"]
    B --> C["Registry or platform endpoints"]
    C --> D["Pricing instance A"]
    C --> E["Pricing instance B"]
    C --> F["Pricing instance C"]
    A --> G["Load balancer"]
    G --> D
    G --> E
    G --> F
~~~

Discovery answers routing questions: which service to call, which endpoints exist, and whether an endpoint is healthy. It does not necessarily supply credentials or provision databases/queues.

### 2.2. Service Binding: Supplying Connection Information

Service binding attaches a workload to a service instance. Binding data may contain host, port, database name, username, password, URI, certificates, bucket, queue URL, or resource identifiers. The platform may mount files, inject environment variables, or expose metadata under contracts such as the Kubernetes Service Binding Specification or Cloud Foundry `VCAP_SERVICES`.

For example, a database binding enables Spring Boot to create a datasource. Binding does not necessarily look up instances dynamically on every request; many bindings are read at startup and retained for the process lifetime.

For cloud APIs using IAM/Managed Identity/Workload Identity, bindings typically need only resource names, project/Region/endpoints. SDKs acquire tokens from the workload identity provider. There is no need to embed access keys in bindings when the runtime identity already holds permissions.

### 2.3. Service Broker: Managing Resource Lifecycles

A service broker is a control-plane component receiving platform requests to act on services:

- Provision a service instance.
- Bind an application/workload to an instance and issue binding data/credentials.
- Unbind and revoke binding credentials.
- Update plans/parameters if supported by the broker.
- Deprovision an instance when requested by the platform.

For example, a developer requests PostgreSQL plan `standard`. The platform calls the broker to create the database, then binds the database to the application. The broker can create a dedicated user, return endpoint/credentials, and revoke that user on unbind.

A service broker is not a runtime discovery registry. A broker can create a service and return an endpoint; the application subsequently uses that endpoint or an appropriate discovery mechanism.

### 2.4. Service Mesh: Managing Inter-Service Communication

Service meshes such as Istio, Linkerd, or Consul service mesh provide an infrastructure layer for service-to-service traffic, typically covering mTLS, identity, policies, telemetry, retries, and traffic shifting. A mesh may use Kubernetes service discovery or its own registry as the source of endpoints.

A mesh is not synonymous with service discovery. Discovery provides endpoint lists/addresses; a mesh governs how traffic is secured and forwarded. There is no need to deploy a service mesh merely to resolve Kubernetes Service DNS names.

### 2.5. Comparison Table

| Component | Core Question | Input | Output |
| --- | --- | --- | --- |
| Service Discovery | Where is the service located? | Logical service name | Endpoint/instance list |
| Service Binding | How does a workload connect to a service instance? | Binding resource/metadata | Connection properties/credentials |
| Service Broker | Who creates and manages service instances? | Provision/bind/unbind requests | Resource and binding lifecycles |
| Service Mesh | How is inter-service traffic secured/controlled? | Service identity, policies, routes | mTLS, routing, telemetry |
| Kubernetes Service | How do clients call a stable group of pods? | Selector/EndpointSlice | Virtual IP and DNS name |
| Ingress/Gateway | How does external traffic enter the cluster? | Host/path/routes | Entry point and routing |

## 3. Discovery in Spring Cloud Architecture

### 3.1. The DiscoveryClient Abstraction

Spring Cloud Commons defines the `DiscoveryClient` abstraction so applications or frameworks can query service instances by service ID. Implementations may be backed by Eureka, Consul, Zookeeper, Kubernetes, or other discovery providers.

Usage idea:

~~~java
import java.util.List;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Component;

@Component
public class PricingEndpointLookup {

    private final DiscoveryClient discoveryClient;

    public PricingEndpointLookup(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public List<ServiceInstance> instances() {
        return discoveryClient.getInstances("pricing-service");
    }
}
~~~

`getInstances` returns the instances known to the implementation. The code above only illustrates lookup; do not naively pick the first instance and send requests directly in production if you need load balancing, retries, health-aware routing, or circuit breaking.

### 3.2. Spring Cloud LoadBalancer

Spring Cloud LoadBalancer selects an instance for a request based on service ID. With Spring `RestClient`, `RestTemplate`, or `WebClient`, load-balancing interceptors/filters can be integrated depending on the Spring Cloud version.

Example declaring an HTTP client able to use logical service names:

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration
class HttpClientConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }
}
~~~

A client using a service ID instead of a concrete hostname:

~~~java
@Service
class PricingClient {

    private final RestClient restClient;

    PricingClient(RestClient.Builder builder) {
        this.restClient = builder.build();
    }

    PricingQuote quote(String productId) {
        return restClient.get()
                .uri("http://pricing-service/api/quotes/{id}", productId)
                .retrieve()
                .body(PricingQuote.class);
    }
}
~~~

In this example, `pricing-service` is resolved by the resolver/load balancer when the builder is configured properly with a DiscoveryClient implementation. Do not use a load-balanced builder for arbitrary external URLs; reserve it for logical service IDs belonging to the discovery namespace.

### 3.3. Discovery Is Not Health Checking

A registry may retain an instance that has died or stopped accepting requests. Endpoint sources and health signals must stay synchronized. Systems may use:

- Kubernetes readiness probes to decide whether a pod belongs in Service endpoints.
- Eureka heartbeats/leases and health status.
- Consul health checks.
- Cloud Map health checks or orchestrator integrations.
- Network/application-layer load balancer health checks.

Liveness and readiness serve distinct purposes. Liveness determines whether a process needs restarting; readiness determines whether an instance should receive traffic. Do not tie liveness probes to a flaky database if doing so triggers cascading pod restarts.

### 3.4. Client-Side vs. Server-Side Load Balancing

| Model | How It Works | Examples |
| --- | --- | --- |
| Client-side | Client fetches instance list and picks an endpoint | Spring Cloud LoadBalancer + Eureka/Consul |
| Server-side | Client calls one stable address; proxy/load balancer picks backend | Kubernetes Service ClusterIP, cloud load balancers |
| DNS-based | DNS returns one or more addresses; client/resolver chooses | Kubernetes Service DNS, Route 53 private DNS |
| Mesh/proxy-based | Sidecar/node proxy picks upstream per policy | Istio/Envoy, Linkerd |

Kubernetes Services typically use a server-side virtual IP/data plane: clients call a stable DNS name and traffic is routed to eligible endpoints. Applications do not query the Kubernetes API per request. With Spring Cloud Kubernetes DiscoveryClient, applications can pull instance metadata and perform client-side load balancing; that is a different choice from calling Service DNS directly.

### 3.5. When Do You Need DiscoveryClient?

Use the discovery abstraction when the application genuinely needs the instance list or dynamic endpoint selection at the application layer. If you only need to call a Kubernetes Service via DNS, a standard HTTP client using the DNS name is usually simpler. If you need traffic policies, mTLS, and cross-service telemetry, consider a service mesh or gateway.

Do not add Eureka/Consul to a cluster solely to use `@LoadBalanced`. Identify what discovery the current platform already provides and which semantics clients actually require.

## 4. Kubernetes-Native Service Discovery

### 4.1. Services and Pod IPs

Pod IPs can change when pods are recreated, rescheduled, or scaled. A Kubernetes Service creates a stable logical endpoint for a group of pods matched by a label selector.

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: pricing-service
  namespace: commerce
spec:
  selector:
    app: pricing
  ports:
    - name: http
      port: 80
      targetPort: 8080
  type: ClusterIP
~~~

Pods with label `app: pricing` and container port `8080` become backend endpoints when eligible. A `ClusterIP` Service provides a stable address inside the cluster; kube-proxy or an equivalent data plane forwards the traffic.

### 4.2. DNS Names Inside the Cluster

CoreDNS provides DNS records for Services. Within the same namespace, clients can typically call `http://pricing-service`; other namespaces can use `pricing-service.commerce` or the FQDN `pricing-service.commerce.svc.cluster.local`.

DNS names are more stable than Pod IPs. However, DNS caching and client connection pooling can delay seeing updated endpoints. With headless Services, DNS may return Pod IPs directly instead of a ClusterIP; clients may need to handle multiple addresses and endpoint churn.

### 4.3. EndpointSlices

EndpointSlices store sets of endpoints belonging to a Service and scale better than a single large Endpoints object. Controllers update EndpointSlices as Pod readiness, selectors, or topology change. The data plane uses endpoint information to route traffic.

Do not edit EndpointSlices manually for selector-managed Services unless you have a specialized use case. For diagnostics:

~~~bash
kubectl get service pricing-service -n commerce
kubectl get endpointslice -n commerce -l kubernetes.io/service-name=pricing-service
kubectl get pods -n commerce -l app=pricing -o wide
~~~

If a Service has no endpoints, check selectors/labels, readiness probes, port mappings, and namespaces.

### 4.4. Readiness and Traffic Eligibility

A Running pod is not necessarily ready to receive traffic. Its readiness probe must succeed for the endpoint to be marked ready per configuration. Example:

~~~yaml
readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: 8080
  periodSeconds: 5
  failureThreshold: 3
~~~

Spring Boot Actuator can expose readiness/liveness health groups. Expose only necessary health endpoints. Readiness checks should verify ability to serve traffic; do not automatically fail readiness just because an optional dependency is temporarily unavailable.

### 4.5. Headless Services and StatefulSets

A headless Service (`clusterIP: None`) allocates no virtual IP. DNS returns records per Pod endpoint, suited for StatefulSets or systems needing per-replica addressing. StatefulSets provide stable ordinal/network identities, such as `database-0.database-headless.namespace.svc.cluster.local`.

Do not use headless Services as a default replacement for ClusterIP. Clients must handle multi-record DNS, endpoint lifecycles, and readiness semantics.

### 4.6. Ingress, Gateway, and East-West Traffic

Kubernetes Services handle internal traffic. Ingress/Gateway API handles traffic entering the cluster or routing between gateways and backends. They do not replace Service DNS for general internal communication. NetworkPolicies govern which pods may communicate; successful DNS resolution does not mean connections are permitted.
## 5. Spring Cloud Kubernetes and Kubernetes DiscoveryClient

### 5.1. When Is Spring Cloud Kubernetes Needed?

Spring Cloud Kubernetes integrates Spring applications with the Kubernetes API. Depending on the starter/implementation, it can provide DiscoveryClient, ConfigMap/Secret integration, load-balancing integration, and additional features.

Two common connection approaches:

- **DNS via Kubernetes Service:** the application calls the Service's hostname. The Kubernetes data plane handles endpoint routing; the application never reads the Kubernetes API.
- **DiscoveryClient via Kubernetes API:** the application fetches service/endpoint metadata from the API and Spring Cloud LoadBalancer picks an instance.

Choose DNS for ordinary internal service calls. Choose DiscoveryClient when the application needs instance metadata, custom routing, or client-side load balancing. Avoid enabling both mechanisms for the same call path without a clear reason.

### 5.2. Dependencies and Version Alignment

Spring Cloud Kubernetes offers starters built on the Kubernetes Java Client or Fabric8. Example discovery dependency using the Kubernetes Client:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-kubernetes-client-discovery</artifactId>
</dependency>
~~~

Exact artifacts and starter names vary across release trains. Pick one client implementation (Kubernetes Client or Fabric8), manage versions through the Spring Cloud BOM, and verify the Spring Boot compatibility matrix. Do not include multiple discovery implementations simultaneously without intent.

### 5.3. Service IDs and Namespaces

The discovery client typically maps Kubernetes service names to service IDs. Services can be discovered in the current namespace or across namespaces depending on configuration. Cross-namespace discovery requires explicit API permissions and policies.

For example, `pricing-service` in namespace `commerce` can be queried by logical ID, yet namespace selection, ports, and protocols depend on the implementation. Never infer ports solely from container ports; Kubernetes Services separate `port` and `targetPort`.

### 5.4. RBAC for DiscoveryClient

If the discovery implementation queries the Kubernetes API, the pod's ServiceAccount needs read permissions on relevant resources. Minimal example policy for a use case might include `get`, `list`, `watch` on Services, Endpoints/EndpointSlices, and possibly Pods:

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: service-discovery-reader
  namespace: commerce
rules:
  - apiGroups: [""]
    resources: ["services", "endpoints", "pods"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["discovery.k8s.io"]
    resources: ["endpointslices"]
    verbs: ["get", "list", "watch"]
~~~

Bind the Role only to the ServiceAccount of workloads requiring discovery. Reading across multiple namespaces requires RoleBindings in each namespace or carefully reviewed ClusterRoles/ClusterRoleBindings. Never grant `cluster-admin` to fix discovery errors.

If an application merely calls Service DNS, it usually needs no Kubernetes API read permissions. That is a major operational and security advantage of the native DNS approach.

### 5.5. Discovery Lifecycle and Caching

Kubernetes API watches/caches keep endpoints updated without continuous polling. Still, API connectivity, watch reconnects, cache staleness, and permission failures must be handled. Determine:

- From which namespaces does the discovery client fetch services/endpoints?
- Which port is chosen when a Service exposes multiple ports?
- Are not-ready endpoints filtered out?
- How do cache updates and watch reconnects behave?
- When the API server is unavailable, does the client use cached endpoints or fail?
- How does LoadBalancer select instances and retry?

Never call the API server on every request. Use a client/cache implementation with a clear lifecycle and bounded scope.

### 5.6. Spring Cloud Kubernetes Does Not Replace NetworkPolicy

Discovery only reveals endpoints. NetworkPolicies, security groups, service mesh policies, and cloud firewalls decide whether traffic is allowed through. If a service is discovered yet connections time out, check DNS, routing, NetworkPolicy, ports, TLS, and readiness separately.

## 6. Eureka, Consul, and DNS-Based Discovery

### 6.1. Eureka

Eureka is a registry in the Spring Cloud Netflix ecosystem. Service instances register with Eureka Server and send heartbeats; clients fetch the registry to pick instances. This is an application-level registry model, commonly useful in Spring Cloud systems already built on Eureka or environments lacking shared discovery primitives.

Common dependencies:

~~~xml
<!-- Eureka Server -->
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-netflix-eureka-server</artifactId>
</dependency>

<!-- Eureka Client -->
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-netflix-eureka-client</artifactId>
</dependency>
~~~

The server is enabled via `@EnableEurekaServer`; clients use `spring.application.name` and configure server URLs. Protect the registry, enable appropriate TLS/authentication, and tune self-preservation and heartbeats/leases. A Eureka registry adds a runtime dependency; do not deploy it if Kubernetes Service DNS already meets your needs.

### 6.2. Consul

Consul provides a service registry, health checks, and additional capabilities such as KV/service mesh depending on architecture. Spring Cloud Consul Discovery allows services to register and clients to query Consul.

Dependency:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-consul-discovery</artifactId>
</dependency>
~~~

Consul suits hybrid/multi-platform environments needing a shared registry across VMs, Kubernetes, and out-of-cluster services. You must design Consul cluster quorum, ACL tokens, gossip encryption, TLS, health checks, and cross-environment network connectivity.

Consul health status alone does not prove the entire request path works. Health checks should reflect readiness and be protected against credential leakage.

### 6.3. DNS-Based Discovery

DNS is a simple choice when platforms provide stable service names. Kubernetes Service DNS, Route 53 private hosted zones, Azure Private DNS, or Cloud DNS can resolve internal hostnames.

DNS discovery depends on TTLs, JVM/OS/resolver caching, connection pooling, and downstream load balancing. A DNS record returning multiple IPs does not guarantee clients distribute requests evenly; understand resolver behavior and connection reuse.

### 6.4. Choosing a Registry

| Runtime / Need | Option to Consider | Reason |
| --- | --- | --- |
| Internal Kubernetes services | Kubernetes Service DNS | Native, fewer components, routing via cluster data plane |
| Spring app needing endpoint metadata from Kubernetes API | Spring Cloud Kubernetes DiscoveryClient | Integrated discovery and LoadBalancer |
| Legacy Spring Cloud or existing platform registry | Eureka | Application-level registry already present in the system |
| Hybrid VMs + Kubernetes + multiple network zones | Consul | Shared registry and cross-environment health checks |
| Stable external/private endpoints | DNS/private DNS | Simple and language-agnostic |
| Advanced traffic policy/mTLS/telemetry | Service mesh or gateway | Manages data plane and policies |

No single registry fits every architecture. Evaluate topology, failure domains, protocols, identity, latency, operational ownership, and the cost of running a cluster/registry.

## 7. Service Brokers and the Open Service Broker API

### 7.1. Brokers Belong to the Control Plane

The Open Service Broker API (OSB API) defines an HTTP contract between platforms and service brokers to manage service offerings, plans, instances, and bindings. Many Cloud Foundry platforms use OSB-compatible brokers to provision managed databases, caches, messaging, or external services.

High-level flow:

~~~mermaid
sequenceDiagram
    participant User as Developer / Operator
    participant Platform as Platform control plane
    participant Broker as Service Broker
    participant Managed as Managed Service
    participant App as Application

    User->>Platform: Request service instance
    Platform->>Broker: Catalog / provision
    Broker->>Managed: Create resource
    Managed-->>Broker: Resource details
    Broker-->>Platform: Provision result
    User->>Platform: Bind application
    Platform->>Broker: Bind instance
    Broker->>Managed: Create scoped credential
    Broker-->>Platform: Binding data
    Platform->>App: Inject binding data
    App->>Managed: Connect at runtime
~~~

The broker executes lifecycle operations via APIs. Applications normally do not invoke the OSB API during business requests. The platform calls the broker and distributes binding data to workloads.

### 7.2. Common Operations

| Operation | Meaning |
| --- | --- |
| Catalog | Lists service offerings and plans supported by the broker |
| Provision | Creates a service instance |
| Update | Changes plans/parameters if supported by the broker |
| Bind | Generates binding credentials/metadata for a consumer |
| Unbind | Revokes or deletes a binding |
| Deprovision | Deletes a service instance |
| Last operation | Polls status of asynchronous operations |

Provision/bind may be asynchronous operations. The platform must poll status per the contract and handle retries/idempotency. Brokers must handle repeated requests safely, because a platform timeout does not prove the broker failed to create the resource.

### 7.3. OSB API Is Not the Kubernetes Service Binding Specification

The two specifications address different layers:

- **OSB API:** platform calls broker to provision, bind, unbind, and deprovision.
- **Kubernetes Service Binding Specification:** standardizes how binding data is represented and delivered to workloads, usually via a directory/filesystem.
- **Spring Cloud Bindings:** application-side library reading supported binding formats and mapping them into the Spring Environment.

All three can work together: the platform calls an OSB broker to create a database and binding credentials; the platform/operator projects binding data into the pod per the Service Binding Specification; Spring Cloud Bindings reads the data and configures datasource properties.

Not every Kubernetes Service Binding Operator calls the OSB API; operators may pull data from Kubernetes resources/Secrets or provider-specific resources. Do not infer OSB API usage merely because a pod has a binding directory.

### 7.4. Broker Lifecycle and Idempotency

Brokers must handle platforms retrying provision/bind after timeouts. Use stable instance IDs/binding IDs per contract, persist operation state, and ensure repeated calls do not create duplicate databases/users. Unbind must revoke credentials for the exact binding; deprovision deletes the underlying resource only after platform lifecycle confirmation.

For destructive actions, brokers must distinguish unbind from deprovision. Deleting a binding does not mean deleting a database holding data. Backup, retention, and deletion policies must follow the plan/service contract.

### 7.5. Security of the Broker API

Broker APIs can create/delete databases, users, queues, IAM policies, or cloud resources; this is a high-privilege control plane. Protect it with TLS, platform-to-broker authentication, per-operation authorization, auditing, and network isolation. Do not expose broker endpoints to the public internet unnecessarily.

Broker credentials used to provision resources typically hold broader privileges than workload runtime identities. Separate the two identities:
- **Broker/platform identity:** provisions, binds, unbinds, rotates, and deprovisions resources.
- **Application workload identity/credential:** accesses only bound resources.
## 8. Service Discovery on AWS, Azure, and Google Cloud

### 8.1. AWS Cloud Map and Route 53

AWS Cloud Map is a registry service for registering and discovering resources/service instances. A namespace can support discovery via API or DNS. ECS Service Discovery integrates with Cloud Map to register task endpoints when tasks start and deregister them when tasks stop. Route 53 private hosted zones provide DNS discovery inside VPCs.

Common choices:

- **ECS service discovery:** ECS registers tasks in Cloud Map; clients use DNS or the Cloud Map API.
- **EKS:** prefer Kubernetes Services/DNS for in-cluster services; Cloud Map can help with out-of-cluster discovery or hybrid integrations when configured.
- **EC2/VMs:** instances can register via the Cloud Map API or use Route 53 private DNS.
- **Application clients:** can use the AWS SDK Cloud Map `DiscoverInstances` or a DNS resolver. Do not assume Spring Cloud provides a compatible Cloud Map DiscoveryClient implementation; check connectors or write an adapter if you want the Spring abstraction.

A Cloud Map registry does not grant permission to call resources. AWS IAM roles/policies, VPC routing, security groups, and TLS still determine whether requests succeed. When using DNS, account for TTLs and caching; when using the API, manage caching, API throttling, and health filtering.

### 8.2. Azure AKS, Container Apps, and Private DNS

Azure does not have one universal registry across every compute/service. Discovery depends on runtime:

- **AKS:** Kubernetes Services, CoreDNS, EndpointSlices, and Ingress/Gateway are native in-cluster choices.
- **Azure Container Apps:** environments provide internal ingress/service discovery for app-to-app communication; use app names/internal FQDNs per environment configuration.
- **Azure Private DNS:** resolves private endpoints and internal hostnames inside virtual networks.
- **Service Fabric:** provides its own Naming Service and discovery for Service Fabric workloads.
- **Hybrid:** Consul or a dedicated registry can fit when discovery must span VMs, AKS, and datacenters.

With Container Apps, verify internal/external ingress, environment boundaries, and regional/configured DNS suffixes. Do not route east-west traffic over public endpoints when internal ingress satisfies the requirement.

Spring Cloud applications can call internal FQDNs via standard HTTP clients. DiscoveryClient is needed only when instance lists or registry integration are required. Managed Identity authenticates to Azure APIs/services; DNS or internal endpoints do not grant data-plane permissions.

### 8.3. Google Cloud GKE, Cloud DNS, and Service Directory

Common options:

- **GKE:** Kubernetes Services/DNS and EndpointSlices for in-cluster discovery.
- **Cloud DNS private zones:** hostname resolution within VPCs or hybrid networks.
- **Service Directory:** managed registry for service endpoints/metadata, useful for discovery across environments/networks.
- **Cloud Run:** services have stable URLs; service-to-service invocation requires IAM authentication and can use internal ingress/network paths by design.
- **Hybrid:** Service Directory or Consul can bridge Kubernetes and VM workloads when a shared registry is needed.

Service Directory API/Cloud DNS does not automatically create a Spring Cloud DiscoveryClient. Use the Google Cloud client or a custom adapter if the application needs runtime registry queries. When a Cloud Run service URL is already stable, HTTP clients can call it directly; add a registry only when dynamic metadata/routing is required.

A Cloud Run service URL is not authorization. Callers need an identity with invoke permissions and must attach an appropriate ID token. On GKE, Workload Identity gives credentials to workloads; Kubernetes Service DNS provides only addresses.

### 8.4. Comparing Discovery Options

| Environment | Typical Native Discovery | When an Additional Registry Is Needed |
| --- | --- | --- |
| AWS ECS | ECS Service Discovery + Cloud Map/Route 53 | Hybrid, custom attributes, or cross-platform registry |
| AWS EKS | Kubernetes Service/DNS | Cross-cluster/VPC or out-of-Kubernetes discovery |
| Azure AKS | Kubernetes Service/DNS | Hybrid or multi-cluster/network zone topologies |
| Azure Container Apps | Internal ingress and app DNS | Multi-environment/hybrid registry |
| GKE | Kubernetes Service/DNS | Cross-cluster/VPC or external workloads |
| Cloud Run | Service URLs and internal routing | Dynamic registry by service metadata/endpoints |
| VM/multi-cloud | Private DNS, Cloud Map, Service Directory, Consul | Unified health-aware registry |

No generic Spring Cloud starter automatically supports every native discovery service. Verify available connectors, protocols/APIs, and maintenance status before deciding to build a custom DiscoveryClient adapter.

## 9. Service Brokers and Cloud Resource Provisioning

### 9.1. Not Every Cloud Service Catalog Is an OSB Broker

AWS, Azure, and Google Cloud offer multiple ways to provision managed resources, not all of which implement the Open Service Broker API.

| Platform / Mechanism | Role | Automatically OSB API? |
| --- | --- | --- |
| Cloud Foundry service broker | Provisions/binds managed services for the platform | Commonly implements OSB API |
| Kubernetes operator/controller | Reconciles resources from Kubernetes custom resources | No, unless the operator provides an OSB adapter |
| AWS Service Catalog | Governs approved AWS product catalogs and provisioning | Not by default |
| AWS Controllers for Kubernetes (ACK) | Manages AWS resources via Kubernetes APIs | No |
| Azure Service Operator | Manages Azure resources via Kubernetes custom resources | No |
| Google Config Connector | Manages Google Cloud resources from Kubernetes | No |
| Crossplane providers | Exposes cloud resources as Kubernetes APIs and compositions | Not by default |
| Provider SDK/CLI/IaC | Provisions resources via pipelines or code | No |

An operator may create a database/queue and write connection details into a Secret, yet that does not make it an OSB API service broker. Look at the actual contract used by the platform and application.

### 9.2. AWS Service Catalog, ACK, and CloudFormation

AWS Service Catalog manages approved AWS product catalogs and provisioning permissions. CloudFormation/IaC or pipelines can create RDS, S3, SQS, MSK, and other resources. ACK enables managing many AWS resources via Kubernetes custom resources.

These tools can provision resources, while application binding still needs its own mechanism: creating Secrets/config, injecting resource ARNs/URLs, attaching IAM roles, or providing a service binding contract. Never confuse pipeline/controller provisioning permissions with application runtime permissions.

### 9.3. Azure Service Operator and Resource Management

Azure Service Operator lets you declare Azure resources as Kubernetes custom resources while controllers reconcile desired state with the Azure control plane. Azure Resource Manager/Bicep/Terraform can also provision managed services.

After creating resources, the platform must decide how to distribute connection details:
- Endpoints/resource IDs via ConfigMaps or binding metadata.
- Secrets via Key Vault/Secret Store CSI/Kubernetes Secrets.
- Identity via Managed Identity/Workload Identity.
- Network access via VNet/private endpoints/firewalls.

Operator provisioning does not automatically grant the application permission to access the resource.

### 9.4. Google Config Connector and Crossplane

Config Connector manages Google Cloud resources from Kubernetes custom resources; Crossplane can compose resources and expose platform API abstractions. These are control-plane reconciliation/provisioning tools. Binding data and runtime identities must be designed separately.

For instance, Config Connector creates a Cloud SQL instance and a Secret with database metadata; the workload still needs the Cloud SQL Client IAM role or connector permissions and valid database authentication. Never grant project-admin permissions to an application just because a controller needs provisioning rights.

### 9.5. When to Use the OSB API?

The OSB API fits when a platform already has a broker ecosystem or needs a standardized contract across multiple service brokers. Use Kubernetes operators/controllers when teams run a Kubernetes-native control plane managing resource lifecycles via CRDs. Use IaC/pipelines when provisioning aligns with infrastructure releases and self-service app bind/unbind is unnecessary.

Decide based on:
- Does the platform speak OSB API?
- Who owns provisioning and deprovisioning?
- Are self-service catalogs/plans needed?
- Do binding credentials need per-application scoping?
- Does unbinding revoke credentials and deprovisioning protect data?
- Are auditing, approvals, quotas, and cost allocation required?
- Can drift reconciliation and operation timeouts be recovered cleanly?
## 10. Combining Discovery, Binding, and Brokers in One Architecture

### 10.1. Separating Control Plane and Data Plane

A complete architecture can employ all three mechanisms:

- The control plane provisions databases/queues via brokers or operators.
- The binding layer delivers endpoints/resource metadata/credentials to workloads.
- The discovery layer helps services locate endpoints of other services.
- The data plane sends requests to services or managed resources.
- The identity/network layer authenticates and authorizes requests.

~~~mermaid
flowchart TB
    subgraph Control["Control plane"]
      P["Platform / GitOps / IaC"]
      B["Service Broker / Operator"]
      M["Managed resource provisioning"]
      P --> B --> M
    end
    subgraph Runtime["Workload runtime"]
      S["Service binding / config"]
      D["Service discovery / DNS"]
      A["Spring Boot application"]
      I["Workload identity"]
      A --> S
      A --> D
      A --> I
    end
    M --> S
    D --> A
    A --> M
~~~

Example:
1. The platform creates an SQS queue or PostgreSQL database.
2. The operator/broker writes the queue URL or DB endpoint into a binding.
3. The workload receives the binding directory/Secret and IAM role.
4. Spring Boot maps the binding into a datasource or AWS client configuration.
5. Reservation Service uses Kubernetes DNS or DiscoveryClient to call Pricing Service.
6. The AWS SDK uses the IAM role to call SQS; the binding supplies only the queue URL/Region.

### 10.2. Requests Do Not Pass Through the Service Broker

The service broker does not sit on the path of ordinary HTTP requests. When Reservation Service calls Pricing Service, traffic flows through DNS/registry, load balancers, networks, and service endpoints. The broker participates only when the platform provisions/updates/binds/unbinds resources.

If every business request queries a broker to obtain endpoints or credentials, the architecture has mixed the control plane with the data plane, introducing unnecessary dependencies and latency.

### 10.3. Choosing Mechanisms per Dependency

| Dependency | Appropriate Mechanism | Reason |
| --- | --- | --- |
| Pricing Service in the same Kubernetes cluster | Kubernetes Service DNS | Stable endpoint and native routing |
| Service across multiple clusters | Private DNS, multi-cluster service mesh, Consul, or suitable registry | Cross-network/cluster discovery needed |
| Managed PostgreSQL instance | Service binding/config + workload/database identity | Endpoint and credentials/authorization needed |
| S3 bucket | Resource metadata via config/binding + IAM role | Bucket name is not a credential |
| Platform self-service provisioned queue | Broker/operator provisioning + binding | Lifecycle and scoped access needed |
| Cloud Run service | Service URL/internal routing + IAM invocation identity | URL and authorization are two separate layers |

### 10.4. Avoid Creating Two Sources of Truth

If Kubernetes Service DNS is already the endpoint source for Pricing Service, do not simultaneously maintain a Eureka registry for the same endpoints without a synchronization requirement. If a broker supplies the database endpoint in a binding, do not hard-code another endpoint in Config Server. If workload identity provides short-lived credentials, do not create parallel static passwords.

Every resource needs a single owner for endpoints, credentials, and lifecycles. Other systems should hold only references or necessary metadata.

## 11. Security Boundary: Discovery Does Not Grant Authorization

### 11.1. Discovering an Endpoint Does Not Mean Access Is Allowed

Successful DNS resolution or a DiscoveryClient returning instances does not prove the caller is authorized to invoke the service. Authorization must be enforced at the application, gateway, mesh, or resource IAM policy layer.

Examples:
- Kubernetes NetworkPolicy restricts which pods can open connections.
- mTLS/service mesh authenticates workload identities and enforces east-west policies.
- JWT/OAuth verifies principals/claims at application APIs.
- AWS IAM, Azure RBAC, or Google IAM permits API operations on managed resources.
- Database roles govern SQL privileges after connecting.

Never treat a service's presence in a registry as an authorization check.

### 11.2. Protecting Registries and the Kubernetes API

Registries hold hostnames, IPs, ports, health metadata, and occasionally internal tags/attributes. Restrict who can register, deregister, and query the registry. Enable TLS/authentication, ACLs, and auditing. Never put tokens/passwords into service metadata or tags.

With Spring Cloud Kubernetes DiscoveryClient, the ServiceAccount should have read permissions strictly for the required namespaces/resources. Do not grant write access on Services/EndpointSlices or read access on Secrets if discovery does not need them.

### 11.3. Broker Credentials vs. Workload Credentials

A broker may need administrative permissions to create databases, users, queues, IAM policies, or secrets. Application workloads typically need only permissions to use resources. Keep the two identities separate:

- Broker credentials: stored in a secret store, read only by platform/broker runtimes.
- Binding credentials: scoped per instance/binding/application, revocable.
- Workload identities: use short-lived tokens bound to the workload's role/identity.
- Human/admin identities: used for approvals, break-glass, and audited operations.

Never mount broker master credentials into a Spring Boot application.

### 11.4. SSRF and Endpoint Injection

If an application reads endpoints from bindings/config, validate schemes, hosts, and ports against an allow-list. Never allow user HTTP requests to override service URLs or binding paths. If service discovery carries custom metadata, never use untrusted values as arbitrary target URLs; doing so risks SSRF against metadata endpoints or internal admin services.

When building custom binding readers, defend against path traversal/symlinks and pick binding names strictly from trusted configuration. Never read arbitrary filesystem paths based on request parameters.

### 11.5. TLS, mTLS, and Certificate Lifecycles

Discovery provides endpoints; it does not establish trust. For HTTPS/mTLS:
- Verify DNS names match certificate SANs.
- Manage CA/client certificates and rotation.
- Never disable hostname verification.
- With a service mesh, understand where TLS terminates and where identities are verified.
- For managed service private endpoints, verify private DNS and certificate hostnames.

## 12. Testing Discovery and Service Brokers

### 12.1. Unit Testing Service Selection

If an application implements custom service selection logic, test it with a fake DiscoveryClient or mock instance list. Verify:
- Exact service ID matching.
- Empty instance lists are handled safely.
- Unhealthy instances or missing metadata are filtered out.
- Ports/protocols are selected accurately.
- No fallback to hard-coded production hostnames.

There is no need to mock the Kubernetes API in every unit test if the logic simply uses a standard HTTP client calling Service DNS.

### 12.2. Kubernetes Integration Tests

On kind/minikube or a test cluster, verify:
1. Deployment pods carry the expected labels.
2. Service selectors match pods.
3. EndpointSlices contain ready endpoints.
4. DNS resolves Service names.
5. Readiness failures remove pods from endpoints.
6. Pod restarts/scaling update endpoints.
7. NetworkPolicies permit intended traffic.
8. DiscoveryClient has exact RBAC permissions if used.

Testcontainers can provide dependencies, yet it does not replace testing Kubernetes DNS, RBAC, and EndpointSlices.

### 12.3. Testing Spring Cloud DiscoveryClient

Use a test registry or test context with the relevant discovery implementation. Verify client-side load balancing picks instances from the registry, handles empty lists, and refreshes when instances deregister. When using Eureka/Consul, verify heartbeats/health statuses and registry availability.

For DNS-based discovery, test resolvers/network paths and connection pool behavior. Tests should not assume a DNS record change immediately switches all active JVM connections to a new endpoint.

### 12.4. Testing Broker Lifecycles

Broker/operator integration tests should verify:
- Catalog returns expected service offerings/plans.
- Provision creates the expected resource and operation status.
- Retrying provision does not create duplicate resources.
- Bind creates scoped credentials and returns expected metadata.
- Unbind revokes credentials for the target binding.
- Deprovision obeys retention/backup/deletion policies.
- Provider API failures trigger retries/backoff with clear operation state.
- Auditing records actors/resources/operations.

Use fake provider APIs or ephemeral cloud resources in CI. Never test deprovisioning on resources holding production data.

### 12.5. Binding Handoff Contract Tests

After a broker/operator creates a binding, verify the platform delivers data to the workload per contract:
- Kubernetes Service Binding directories contain expected metadata/types/keys.
- Cloud Foundry `VCAP_SERVICES` contains expected labels/names/credentials.
- Secret/volume mounts land in the right namespace with proper permissions.
- Spring Cloud Bindings reads the binding cleanly.
- Spring Boot initializes datasources/clients.
- Workload identities hold independent permissions to call managed resources.

This is the contract between control plane and runtime; a broker test passing on its own does not prove the application received the binding properly.

## 13. Observability and Operations

### 13.1. Discovery Signals

Monitor:
- Registered and healthy instance counts per service ID.
- Discovery lookup latency/error rates.
- DNS lookup failures and latency.
- Endpoint churn/deregister/re-register events.
- LoadBalancer selected instances and retries.
- Kubernetes EndpointSlice count and ready endpoints.
- Registry heartbeats, leader/quorum health, and watch reconnects.

Do not use high-cardinality IPs or instance IDs as unbounded metric labels.

### 13.2. Broker Signals

Monitor:
- Provision/bind/unbind/deprovision request counts.
- Operation duration and asynchronous polling age.
- Broker API error/retry rates.
- Resource provisioning failures and orphan resource counts.
- Binding credential creation/revocation.
- Catalog/plan versions and quotas.
- Drift between desired resources and actual provider resources.

A broker outage can disrupt self-service provisioning without necessarily halting runtime requests to existing services. Runbooks must distinguish control-plane unavailability from data-plane unavailability.

### 13.3. Correlation and Auditing

Each lifecycle operation should carry request/instance/binding IDs and a correlation ID across platform, broker, and provider APIs. Log metadata such as service offering, plan, operation state, duration, and provider error codes. Never log binding credentials, access tokens, or secret payloads.

Discovery logs can record service IDs, policy-masked selected endpoints, request correlation IDs, and error categories. Never log authorization headers or full URLs if query strings hold tokens.

### 13.4. Symptom-Based Runbooks

**Service DNS fails to resolve:** check namespace, Service name, CoreDNS, search domains, NetworkPolicies to DNS, and private DNS zones.

**Service resolves but fails to connect:** check EndpointSlices, readiness, port/targetPort, network routes, security groups/NetworkPolicies, TLS, and application listeners.

**DiscoveryClient returns an empty list:** check registry registration, namespaces/filters, ServiceAccount RBAC, caches/watches, and service ID mappings.

**Old instances keep receiving calls:** check readiness/deregistration propagation, DNS TTLs, client caches, connection pools, and registry health checks.

**Broker provision timeout:** inspect the operation ID and broker state before retrying; never send a fresh request with a different instance ID if the prior operation may have succeeded.

**Binding exists yet app fails to connect:** check binding parser/property mappings, credential versions, workload identity, resource IAM, and networking separately.

## 14. Common Architectural Pitfalls

| Symptom / Design | Cause | Resolution |
| --- | --- | --- |
| Calling Pod IPs directly | Pod IPs change on rescheduling | Call Kubernetes Service DNS or a discovery registry |
| Deploying Eureka in every cluster | Not leveraging Kubernetes Service DNS | Evaluate DNS first; add a registry only when needed |
| Service discovered yet `AccessDenied` | Discovery does not grant IAM/RBAC | Configure workload identity and resource policies |
| Service Broker called in request path | Mixing control plane and data plane | Use brokers strictly for lifecycle operations |
| Confusing OSB API with Service Binding Spec | Mixing provisioning contract with binding delivery contract | Separate broker API from runtime binding format |
| Operator creates resource yet app cannot connect | Missing binding/secret/identity/network | Verify each handoff boundary |
| Discovery returns stale instances | Slow health checks/caches/deregistration | Inspect TTLs, heartbeats, watches, and readiness |
| DNS changes yet requests hit old IPs | JVM/client caching or keep-alive connections | Tune DNS caching and connection lifecycles deliberately |
| Broker retries create duplicate resources | Provision/bind not idempotent | Use operation/instance IDs and persisted state |
| Unbind deletes database by mistake | Confusing unbind with deprovision | Separate lifecycles and deletion policies |
| Granting cluster-admin for discovery | Overly broad RBAC | Role/RoleBinding reading strictly required resources |
| Using binding credentials instead of IAM roles | Ignoring authentication model differences | Prefer workload identity for cloud APIs |

## 15. Production Readiness Checklist

1. **Boundaries:** discovery, binding, broker, and mesh clearly separated in architecture diagrams.
2. **Discovery source:** Kubernetes DNS, registry, Cloud Map, Service Directory, or private DNS chosen per runtime.
3. **Routing:** client-side/server-side load balancing, health checks, TTLs, and connection reuse understood.
4. **Kubernetes:** Service selectors, ports, EndpointSlices, readiness, and DNS verified.
5. **Spring integration:** DiscoveryClient/LoadBalancer enabled only when needed; versions/BOM compatible.
6. **RBAC:** DiscoveryClient reads only required namespaces/resources.
7. **Broker contract:** OSB API, operators/CRDs, or IaC provisioning clearly defined without conflating with binding specs.
8. **Idempotency:** provision/bind/unbind handle retries and operation timeouts safely.
9. **Binding handoff:** endpoints/metadata/credentials delivered in the expected format to workloads.
10. **Identity:** broker identity and application workload identity separated; least privilege applied.
11. **Network/TLS:** DNS, routes, firewalls, NetworkPolicies, certificates, and mTLS verified.
12. **Lifecycle:** rotation, unbind, deprovision, backups, and retention have owners and runbooks.
13. **Testing:** unit, registry, Kubernetes, broker lifecycle, and binding contract tests.
14. **Observability:** discovery health, endpoint churn, broker operations, and orphan resources have metrics/alerts.
15. **Recovery:** recovery plans exist for registry outages, broker outages, and stale bindings.

## 16. Practice Exercises

1. Diagram the boundaries separating Service Discovery, Service Binding, Service Broker, and Service Mesh for a Reservation/Pricing/Billing system.
2. Create a Kubernetes Service for Pricing Service; inspect DNS and EndpointSlices when scaling the deployment.
3. Compare calling Service DNS directly against Spring Cloud Kubernetes DiscoveryClient and Spring Cloud LoadBalancer.
4. Design minimal RBAC for DiscoveryClient reading Services/EndpointSlices in a single namespace.
5. Choose among Eureka, Consul, or Kubernetes DNS for a system spanning VMs, Kubernetes, and Cloud Run; explain failure domains and operations.
6. Compare AWS Cloud Map, Azure Container Apps internal discovery, AKS DNS, GKE DNS, and Google Service Directory.
7. Describe OSB API provision/bind/unbind/deprovision and distinguish it from the Kubernetes Service Binding Specification.
8. Design an idempotent broker when a platform retries provision after a timeout.
9. Use an operator/ACK/Config Connector to provision a resource; describe separately how binding metadata and workload identity are supplied.
10. Simulate a state where a binding exists yet the application receives `AccessDenied`; isolate whether the fault lies in identity, IAM/RBAC, or networking.
11. Write a runbook for when stale endpoints continue receiving calls after a rollout.
12. Diagram the control plane/data plane and determine whether a broker outage affects live runtime traffic.

**Completion criteria:** learners can distinguish discovery, binding, and brokers; choose an appropriate discovery mechanism for Kubernetes or managed cloud runtimes; explain Service Brokers/OSB API and binding handoffs; configure Spring Cloud discovery when needed; and test endpoint lifecycles, identities, networking, and provisioning idempotency.

## References

- [Spring Cloud Commons — DiscoveryClient](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html): discovery abstraction and common client features.
- [Spring Cloud Kubernetes Reference](https://docs.spring.io/spring-cloud-kubernetes/reference/): Kubernetes discovery, configuration, and load balancing.
- [Spring Cloud Netflix Eureka](https://docs.spring.io/spring-cloud-netflix/reference/spring-cloud-netflix.html): Eureka server/client integration.
- [Spring Cloud Consul](https://docs.spring.io/spring-cloud-consul/reference/): Consul discovery and health checks.
- [Kubernetes Services, Load Balancing, and Networking](https://kubernetes.io/docs/concepts/services-networking/service/): Services, ClusterIP, headless services, and endpoint routing.
- [Kubernetes DNS for Services and Pods](https://kubernetes.io/docs/concepts/services-networking/dns-pod-service/): cluster DNS names.
- [Kubernetes EndpointSlices](https://kubernetes.io/docs/concepts/services-networking/endpoint-slices/): endpoint representation and lifecycles.
- [Kubernetes Service Binding Specification](https://servicebinding.io/spec/core/1.0.0/): binding data contract for workloads.
- [Open Service Broker API](https://github.com/openservicebrokerapi/servicebroker): broker lifecycle API contract.
- [Cloud Foundry Services](https://docs.cloudfoundry.org/services/): service brokers, catalogs, provisioning, and binding.
- [AWS Cloud Map](https://docs.aws.amazon.com/cloud-map/latest/dg/what-is-cloud-map.html): service registry and discovery.
- [Amazon ECS Service Discovery](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/service-discovery.html): ECS integration with Cloud Map.
- [Azure Container Apps service discovery](https://learn.microsoft.com/azure/container-apps/connect-apps): internal app-to-app connectivity.
- [Azure Private DNS](https://learn.microsoft.com/azure/dns/private-dns-overview): private DNS zones and name resolution.
- [Google Cloud Service Directory](https://cloud.google.com/service-directory/docs/overview): managed service registry.
- [Google Kubernetes Engine Services](https://cloud.google.com/kubernetes-engine/docs/concepts/service): service networking in GKE.
- [Google Cloud Run service-to-service authentication](https://cloud.google.com/run/docs/authenticating/service-to-service): IAM identity and ID tokens when calling services.
