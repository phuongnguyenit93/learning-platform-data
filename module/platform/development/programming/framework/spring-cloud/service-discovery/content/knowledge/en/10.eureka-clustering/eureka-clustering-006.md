# Designing Regions, Zones, and Deployment Location Metadata

## 1. Why Do We Need a Region and Zone Model?

In a microservice system running across multiple servers or infrastructure zones, network distance and failure blast radius directly affect service invocation capabilities. Two instances of the same service may reside in two different availability zones, two data centers, or two geographic regions. If clients always pick distant instances, requests can incur higher latency and generate unnecessary cross-zone traffic.

Eureka supports the concepts of **region** and **zone** to describe how discovery infrastructure is organized. Applications can also publish deployment location metadata so observability tools or routing components can select appropriate instances.

These concepts should be distinguished:

- **Region:** a large area, typically representing a geographic region or a deployment domain with its own operational boundary.
- **Zone:** a smaller area inside a region, typically corresponding to an availability zone or failure domain.
- **Instance metadata:** key/value pairs published by each instance, such as region, zone, datacenter, rack, and version.

Regions and zones help organize Eureka endpoints and prioritize connections by location. Metadata provides information about the instance itself. Attaching metadata alone does not make Eureka or LoadBalancer route by location; you must configure a component that consumes that metadata.

## 2. Deployment Location Hierarchy

A common model can be represented as follows:

~~~mermaid
flowchart TB
    R[Region: ap-southeast-1]
    R --> ZA[Zone: zone-a]
    R --> ZB[Zone: zone-b]
    ZA --> A1[Datacenter / Rack A]
    ZB --> B1[Datacenter / Rack B]
    A1 --> APP1[Payment instance A]
    B1 --> APP2[Payment instance B]
~~~

A region contains multiple zones. Each zone can host one or more Eureka Servers and multiple business instances. When one zone experiences an outage, remaining zones in the same region can continue serving if networking, the registry, and applications have been deployed redundantly.

Region and zone names are logical labels standardized by the organization or sourced from the infrastructure platform. Do not mix hierarchy levels. For example, **ap-southeast-1** can be the region, **zone-a** the zone, **dc-hcm-1** the datacenter, and **rack-03** the rack.

## 3. Regions and Zones in Eureka Client

Eureka Client uses region and availability zones to determine which Eureka Servers it should connect to. Commonly used properties include:

| Property | Role |
|---|---|
| **eureka.client.region** | The region in which the Eureka Client operates |
| **eureka.client.availability-zones** | Maps a region to a list of zones in priority order |
| **eureka.client.service-url** | Maps a zone to one or more Eureka Server URLs |
| **eureka.client.prefer-same-zone-eureka** | Prefers a Eureka Server in the client's zone when possible |

The default region in Eureka is usually **us-east-1**. In real environments, declare region and zones matching your organization's topology to avoid relying on defaults.

### 3.1. Example Configuration for a Client in zone-a

Suppose the system has a region **ap-southeast-1**, containing two zones **zone-a** and **zone-b**. The client is running in zone-a:

~~~yaml
eureka:
  client:
    region: ap-southeast-1
    availability-zones:
      ap-southeast-1: zone-a,zone-b
    service-url:
      zone-a: http://eureka-a.internal:8761/eureka/
      zone-b: http://eureka-b.internal:8761/eureka/
    prefer-same-zone-eureka: true
~~~

In this configuration:

- The client belongs to region **ap-southeast-1**.
- **availability-zones** lists zone-a before zone-b, expressing the priority order of zones within the region.
- **service-url** declares the Eureka endpoint corresponding to each zone.
- **prefer-same-zone-eureka: true** instructs the client to prefer a Eureka Server in the zone closest to the client's location when choosing a server to talk to.

Zone names in **availability-zones** must match the zone keys in **service-url**. Eureka hostnames must be resolvable and reachable from workloads on the deployment network.

### 3.2. Clients in zone-b

Clients in zone-b can use the same region and endpoint list, but should be deployed with matching location settings. Zone priority order can be configured per client topology or by environment-wide convention. Do not copy the zone-a configuration verbatim to every workload if doing so forces clients to always prefer a distant zone.

When multiple endpoints exist within the same zone, you can declare a URL list using the syntax supported by your Spring Cloud Netflix version. Confirm the effective configuration via Eureka Client logs and test what happens when an endpoint becomes unreachable.

## 4. Eureka Servers Must Also Be Distributed Across Zones

To prevent a single zone from becoming a single point of failure, deploy multiple Eureka Servers across different failure domains. Nodes must know their peers and be able to communicate over the internal network.

Example of a Eureka node in zone-a:

~~~yaml
server:
  port: 8761

spring:
  application:
    name: eureka-server

eureka:
  instance:
    hostname: eureka-a1.internal
    metadata-map:
      region: ap-southeast-1
      zone: zone-a
  client:
    register-with-eureka: true
    fetch-registry: true
    region: ap-southeast-1
    availability-zones:
      ap-southeast-1: zone-a,zone-b
    service-url:
      zone-a: http://eureka-a2.internal:8761/eureka/
      zone-b: http://eureka-b.internal:8761/eureka/
    prefer-same-zone-eureka: true
~~~

Nodes in zone-b need their corresponding hostname and zone metadata, along with appropriate peer endpoints. URLs in a Eureka Server's service URL list must point to peers; do not add the node's own URL to its peer list. The example above assumes zone-a has another peer eureka-a2 and zone-b has eureka-b. In real deployments, Eureka Servers should span multiple failure domains; node counts and distribution should be based on load, availability requirements, and network topology.

Configuring **prefer-same-zone-eureka** applies to selecting which **Eureka Server** the client communicates with. It does not mean business requests are automatically routed to instances in the same zone. Those are two decisions at two different layers.

## 5. Location Metadata of Service Instances

A Eureka instance can publish custom metadata via **eureka.instance.metadata-map**. For example:

~~~yaml
spring:
  application:
    name: payment-service

eureka:
  instance:
    metadata-map:
      region: ap-southeast-1
      zone: zone-a
      datacenter: dc-hcm-1
      rack: rack-03
      version: 2.5.0
~~~

When an instance registers, these key/value pairs are stored in the registry and can be returned to clients via the Eureka API. Metadata helps:

- Identify which region or zone an instance is running in.
- Distinguish datacenters, racks, or deployment groups.
- Observe version distribution during rolling updates.
- Support dashboards, logs, metrics, and operational tooling.
- Serve as input for location-based instance filtering policies if clients are configured to consume metadata.

Metadata is application-published data. Eureka does not verify that the **zone** value in metadata actually matches the server's physical location. The deployment platform should supply accurate values via environment variables, ConfigMaps, or equivalent configuration.

### 5.1. Consistent Metadata Naming

Standardize key names and value conventions across the entire system:

| Key | Example | Meaning |
|---|---|---|
| **region** | ap-southeast-1 | Deployment region |
| **zone** | zone-a | Availability zone or failure domain |
| **datacenter** | dc-hcm-1 | Data center |
| **rack** | rack-03 | Rack or server group |
| **cluster** | payments-prod | Deployment cluster |
| **version** | 2.5.0 | Application version |
| **build** | 2026.11.24.1 | Build or release identifier |

Avoid using multiple key names for the same concept, such as **az**, **availabilityZone**, and **zone** appearing together without convention. If a routing component expects the **zone** key, ensure every instance publishes the exact key and value format.

Do not place tokens, passwords, secret keys, or sensitive data in metadata. The registry may be queried by many service clients; publish only information needed for discovery and operations.

## 6. Preferring Same-Zone Instances When Calling Services

Having a client connect to the nearest Eureka Server reduces latency when reading the registry. However, for business requests to prefer instances in the same zone, you must configure an instance-selection policy at the load balancing layer.

Spring Cloud LoadBalancer can use **ZonePreferenceServiceInstanceListSupplier** to prefer instances whose zone metadata matches the client's zone. Example configuration for a workload's zone:

~~~yaml
spring:
  cloud:
    loadbalancer:
      zone: zone-a
~~~

Target service instances must publish matching metadata:

~~~yaml
eureka:
  instance:
    metadata-map:
      zone: zone-a
~~~

For zone preference to take effect, the application must use a supplier that supports zone preference and ensure the Spring Cloud LoadBalancer version in use is configured accordingly. Setting only **spring.cloud.loadbalancer.zone** or adding metadata alone will not change instance selection if the supplier remains on a default configuration that does not filter by zone.

When same-zone instances exist, the supplier can prioritize that group. If no matching instances exist, fallback behavior depends on the supplier implementation and configuration. Test the empty-local-zone case to ensure the application still has a path to call another zone when policy requires it.

### 6.1. Distinguishing the Two Types of Preference

| Configuration | Affected Layer | Goal |
|---|---|---|
| **eureka.client.prefer-same-zone-eureka** | Eureka Client connecting to Eureka Server | Prefer registry endpoints in the same zone |
| **spring.cloud.loadbalancer.zone** combined with zone-aware supplier | Business request load balancing | Prefer service instances in the same zone |

Both settings can be used together, yet they do not replace each other. A client can fetch the registry from a Eureka Server in zone-a and still pick a business instance in zone-b if LoadBalancer lacks a zone preference policy.

## 7. Designing Fallback Between Zones and Regions

A fault-tolerant design typically follows a priority order:

1. Prefer instances in the same zone to minimize latency and cross-zone traffic.
2. If the local zone has no suitable instances left, allow fallback to another zone in the same region.
3. Fall back to another region only when business requirements, system capacity, and data policies allow it.

~~~mermaid
flowchart TD
    REQ[Request to payment-service] --> LOCAL{Healthy instance in same zone?}
    LOCAL -->|Yes| SAME[Select same-zone instance]
    LOCAL -->|No| REGIONAL{Instance in another zone in same region?}
    REGIONAL -->|Yes| OTHERZONE[Select other-zone instance]
    REGIONAL -->|No| REMOTE{Cross-region fallback allowed?}
    REMOTE -->|Yes| OTHERREGION[Select other-region instance]
    REMOTE -->|No| FAIL[Return controlled error]
~~~

This is an illustrative routing policy, not automatic behavior provided by Eureka. Applications must configure LoadBalancer, a gateway, or the corresponding routing layer to implement priority ordering and fallback.

When designing fallback, evaluate:

- Cross-zone/cross-region latency and data transfer costs.
- Reachability of databases, message brokers, and dependencies in the target region.
- Data residency or regional data storage requirements.
- Spare capacity in the zone/region receiving traffic.
- Timeouts, retries, circuit breakers, and retry storm risks.
- How to prevent two regions from accepting writes simultaneously if the business logic does not support active-active.

Do not fall back across regions merely because an endpoint still responds. An instance in another region may lack access to the data or dependencies required to process business logic.

## 8. Multi-Region in Eureka

In multi-region systems, each region can run its own Eureka cluster and applications prefer the registry closest to them. Eureka Client has the concept of region and can be configured to fetch registries from remote regions in architectures that require it.

When deploying multi-region, clearly decide:

- Which region is the primary registration location for each service instance.
- Whether clients need only the local region's registry or also registries from other regions.
- Which services are permitted to make cross-region calls.
- How to handle lost connectivity between regions.
- How registry information is synchronized or distributed across clusters.

Do not assume that configuring multiple Eureka URLs equates to a globally consistent registry. The ability to fetch registries from remote regions and how synchronization occurs across regions depend on configuration, Eureka version, and operational architecture. Check the documentation for your version and test cross-region failures before going to production.

## 9. Example: Injecting Deployment Location from the Environment into Metadata

In Kubernetes, zone information can be provided by the platform via node labels or environment variables injected into containers by manifests. Applications can read those values from environment variables and map them into Spring configuration.

Example configuration:

~~~yaml
eureka:
  instance:
    metadata-map:
      region: ${DEPLOY_REGION:local}
      zone: ${DEPLOY_ZONE:local}
      datacenter: ${DATACENTER_ID:dev}
~~~

Simplified manifest example:

~~~yaml
env:
  - name: DEPLOY_REGION
    value: ap-southeast-1
  - name: DEPLOY_ZONE
    value: zone-a
  - name: DATACENTER_ID
    value: dc-hcm-1
~~~

The values in this example are illustrative. In real environments, derive zone values from node metadata or the platform's scheduling mechanism to avoid manual mislabeling. If a pod can be rescheduled onto a node in a different zone, metadata must reflect the pod's actual location after startup.

## 10. Observing and Verifying Zone Distribution

Once metadata is published, inspect the registry via the Eureka Dashboard or REST API. For example:

~~~bash
curl -H "Accept: application/json" http://eureka-a.internal:8761/eureka/apps/PAYMENT-SERVICE
~~~

For each instance, verify:

- Whether hostname and IP are reachable from calling workloads.
- Whether **region** and **zone** metadata match where the instance is actually running.
- Whether instance counts per zone match expected capacity.
- Whether status is UP and leases are renewing steadily.
- Whether application versions are distributed properly during rollouts.

Track metrics by region and zone:

| Metric or Signal | Question to Answer |
|---|---|
| Instance count by region/zone | Is any zone short on instances or missing all instances? |
| Request count by target zone | Is traffic overly concentrated in one zone? |
| Request latency by source/target zone | Is cross-zone traffic causing high latency? |
| Error rate and timeouts by zone | Is one zone degrading? |
| Eureka peer/client fetch errors | Are nodes still exchanging and updating the registry? |
| Version/build by zone | Did the rollout complete evenly? |

When comparing instance counts, account for replication and client fetch timing. A single query right after a rollout may show an unconverged distribution; observe over a period of time and cross-check multiple Eureka Servers.

## 11. Common Design Mistakes

### 11.1. Confusing Eureka Server Zone with Service Instance Zone

**prefer-same-zone-eureka** prioritizes the registry server. It does not restrict which service instances LoadBalancer selects. To prefer same-zone instances, you need metadata and a supplier that supports zone preference.

### 11.2. Metadata Mismatch with Actual Location

If a pod runs in zone-b but advertises **zone-a**, the load balancer may send requests to the wrong failure domain. Source values from the deployment environment and verify them via the REST API.

### 11.3. Only One Eureka Server in a Region

A single server can become a single point of failure. Distribute servers across appropriate failure domains and configure reachable peers.

### 11.4. No Fallback When a Local Zone Loses All Instances

Local zone preference reduces latency under normal conditions, but it can render a service uncallable if policy permits only same-zone instances. Clearly define fallback to another zone and test when the local zone is empty.

### 11.5. Cross-Region Fallback Without Checking Dependencies and Data

Instances in another region may be unable to reach the right databases, queues, or regional data. Enable cross-region routing only after verifying the readiness of all dependencies.

### 11.6. Putting Too Much Internal Information in Metadata

Metadata can be read by clients. Publish only necessary location labels and versions; do not include secrets, sensitive administrative addresses, or information unrelated to discovery.

## 12. Design and Implementation Workflow

You can follow this workflow:

1. Define regions and zones according to your infrastructure's actual failure domains.
2. Distribute Eureka Servers across zones and configure peers.
3. Configure region, availability zones, and service URLs for each group of Eureka Clients.
4. Enable same-zone Eureka Server preference if appropriate for the topology.
5. Standardize region, zone, datacenter, rack, and version metadata for each service instance.
6. If same-zone routing is needed, configure a zone-aware supplier in Spring Cloud LoadBalancer.
7. Design intra-region and cross-region fallback according to business requirements.
8. Inspect the registry via the REST API and measure request distribution by zone.
9. Test losing a Eureka Server, losing a zone, losing cross-region links, and recovery.

## 13. Summary

Regions and zones describe the discovery infrastructure layout. Eureka Client uses **eureka.client.region**, **availability-zones**, **service-url**, and **prefer-same-zone-eureka** to select an appropriate Eureka Server. Instances can publish deployment location via **eureka.instance.metadata-map**, such as region, zone, datacenter, and rack.

Preferring a same-zone Eureka Server and preferring same-zone service instances are two separate decisions. To load-balance business requests by location, configure a supplier or routing policy capable of reading zone metadata. A sound design reduces cross-zone traffic during normal operation, provides fallback when a zone fails, and switches to another region only when dependencies, data, and capacity permit.
