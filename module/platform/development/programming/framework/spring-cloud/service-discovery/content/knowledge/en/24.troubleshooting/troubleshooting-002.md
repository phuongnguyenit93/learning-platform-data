# Wrong Service Name or Duplicate instanceId Across Replicas

When a consumer calls a service by logical name, such as `inventory-service`, Spring Cloud must locate the right group of registered instances in the registry. If the provider registers under a different name, the consumer may receive an empty list even though the application is running. If multiple replicas share the same `instanceId`, the registry may treat them as the same registration, causing lost instances, overwritten addresses, or heartbeat/deregister operations that affect another replica's record.

These two failures must be distinguished. **Service name** identifies the service group; having multiple instances share a service name is normal behavior. **Instance ID** identifies a specific running instance within the uniqueness scope defined by the registry; concurrently active replicas must have non-conflicting IDs within that scope.

This lesson belongs to the `Troubleshooting` chapter in the `SPRING_CLOUD_SERVICE_DISCOVERY` module. The module helps learners understand how to look up instances by service name via `DiscoveryClient`, `ServiceRegistry`, Eureka, or Consul, along with registration lifecycle, health checks, load balancing, security, and handling registry mismatches. This content guides you through diagnosing wrong service IDs, duplicate instance IDs, and how to fix them in Eureka, Consul, and Zookeeper.

## 1. Distinguishing Service Name, Service ID, and Instance ID

In service discovery, several identifiers look similar yet carry different meanings:

| Concept | Meaning | Example |
|---|---|---|
| Application name | Spring Boot application name, usually declared with `spring.application.name`. | `inventory-service` |
| Service name / service ID | Logical name a consumer uses to look up a group of instances. | `inventory-service` |
| Instance ID | Identifies a specific running instance in the registry. | `inventory-service:pod-7f2a` |
| Host/address | Network address of the instance. | `10.10.2.17` |
| Port | Port on which the application receives traffic. | `8080` |
| Metadata | Additional information used for filtering or routing. | `zone=zone-a`, `version=v2` |

`spring.application.name` is usually used as the default service name, though the registry integration may allow overrides. Instance IDs have different uniqueness scopes depending on the registry:

| Registry | Service name | Required uniqueness scope of instance ID |
|---|---|---|
| Eureka | Application name (`appName`). | Within a single `appName`. |
| Consul | Service name (`Name`). | Within a single Consul agent/node; registering the same service name across multiple nodes is normal. |
| Zookeeper / Curator | Service name located in the znode branch. | Within a single service path, because the instance ID forms the child znode name. |

Because uniqueness scopes differ, do not apply a blanket assumption like "IDs must be unique across the entire cluster" to every registry. Understand the rules of the integration you are using and design IDs that are unique within that scope.

## 2. Symptoms of a Wrong Service Name

Common signs include:

- `DiscoveryClient.getInstances("inventory-service")` returns an empty list.
- `DiscoveryClient.getServices()` does not include the service the consumer is looking for.
- The consumer reports no instance found or LoadBalancer has no server available to select.
- The registry shows a similar service under a different name, such as `inventory`, `Inventory-Service`, or `inventory-service-v2`.
- Provider and consumer run under different profiles or environments, causing one side to use an overridden name.
- An application has multiple DiscoveryClients and `CompositeDiscoveryClient` returns results from a different registry than expected.

Example where the provider registers as:

```yaml
spring:
  application:
    name: inventory-api
```

But the consumer calls:

```java
webClient.get()
        .uri("http://inventory-service/api/items")
        .retrieve();
```

The two names do not match. Without service ID `inventory-service`, LoadBalancer cannot find an instance even though `inventory-api` is healthy.

Overrides to check alongside `spring.application.name`:

| Registry | Property that can change the registered name |
|---|---|
| Eureka | `eureka.instance.appname` (registered application name). |
| Consul | `spring.cloud.consul.discovery.service-name`. |
| Zookeeper | Typically uses `spring.application.name` as the service name; check custom integrations or dependency mappings if any. |

In Spring Boot, environment variables or command-line arguments can override YAML files. For example, `SPRING_APPLICATION_NAME`, `EUREKA_INSTANCE_APPNAME`, and `SPRING_CLOUD_CONSUL_DISCOVERY_SERVICE_NAME` can make runtime values differ from what you see in `application.yml`.

### 2.1. A Wrong Service Name Is Different from an Instance Connection Error

Distinguish by layer:

| Inspection result | Most likely cause |
|---|---|
| `getInstances(serviceId)` is empty and the registry does not have that service ID. | Wrong name, provider not registered, or wrong registry/namespace. |
| Registry has the service, but the discovery client does not see it. | Wrong server, namespace, profile, cache, or registry read permissions. |
| Discovery returns instances, but host/port is unreachable. | Wrong advertised address, network, DNS, firewall, or readiness. |
| Only one instance is visible despite multiple replicas running. | Duplicate instance ID, failed registration, or replicas not registering to the registry being inspected. |
| Instance appears then disappears or switches addresses unexpectedly. | Two processes may be writing the same identifier, deregistering by mistake, or lease/session changing. |

Do not change the instance ID when the actual error is an unreachable host/port; likewise, do not fix networking when the consumer is querying the wrong service ID.

## 3. Symptoms of a Duplicate instanceId

Suppose a Deployment runs three replicas of `inventory-service`:

| Replica | Host | Port | Instance ID |
|---|---|---:|---|
| Pod A | `10.10.1.11` | 8080 | `inventory-1` |
| Pod B | `10.10.1.12` | 8080 | `inventory-1` |
| Pod C | `10.10.1.13` | 8080 | `inventory-3` |

Pod A and Pod B use the same ID. Depending on the registry, they may collide on the same registration slot, the same service ID on an agent, or the same znode path. Outcomes can include:

- The registry shows only two instances instead of three.
- The record has Pod A's host/port and is then overwritten by Pod B, or vice versa.
- A heartbeat from one replica renews the lease of the record currently representing the other replica.
- When one replica shuts down and deregisters, the registration that the remaining replica relies on may be removed.
- Metadata or status flips back and forth according to the order of registration operations.
- Consumers see an unstable instance list and requests intermittently succeed or fail.

This is the classic symptom group of an identity collision. However, seeing fewer instances than replicas can also happen because a provider failed to register, health checks are not passing, or the consumer is reading the wrong registry. Verify the IDs in the registry before concluding.

## 4. Eureka: Application Name and Instance ID

With Spring Cloud Netflix Eureka, the default service ID is taken from `spring.application.name`. The instance ID is configured with `eureka.instance.instance-id`.

Spring Cloud Netflix documentation describes the default instance ID format as:

```text
${spring.cloud.client.hostname}:${spring.application.name}:${spring.application.instance_id:${server.port}}
```

For example:

```text
node-a:inventory-service:8080
```

Eureka identifies a registration by the pair of application name and instance ID. `instanceId` must be unique within an `appName`. If two replicas with the same `appName` use the same `instanceId`, they can overwrite the same registration.

### 4.1. Configuring Eureka with a Unique ID per Replica

In a multi-replica environment, include a process/container-specific identifier in the instance ID. With Kubernetes, you can obtain the Pod UID via the Downward API:

```yaml
spring:
  application:
    name: inventory-service

eureka:
  instance:
    instance-id: "${spring.application.name}:${POD_UID:${spring.cloud.client.hostname}:${server.port}}"
```

Declare the environment variable in the Deployment:

```yaml
env:
  - name: POD_UID
    valueFrom:
      fieldRef:
        fieldPath: metadata.uid
```

Pod UID is the Pod's unique identifier in the cluster. Each replica therefore gets its own instance ID; when a Pod is recreated, the new UID also produces a new registration ID. If not running on Kubernetes, you can use a platform-provided instance ID, a genuinely unique hostname, or an environment variable unique per process.

### 4.2. Inspecting the Eureka Registry

Open the Eureka Dashboard and look up the application name. Check the instance count, instance ID, hostname, IP, port, and status. You can use the REST API:

```bash
curl -H "Accept: application/json" \
  http://eureka-server:8761/eureka/apps/INVENTORY-SERVICE
```

The application name on the Eureka Dashboard/API is usually displayed in uppercase. Compare the actual service name with the value the consumer queries and the integration's normalization rules.

Read the logs of each replica to confirm which instance ID each process registers with. If two processes log the same application name and instance ID, fix the configuration before removing old records.

## 5. Consul: Service Name and Service ID

In Consul, a service registration has `Name`, `ID`, address, port, tags, and checks. Spring Cloud Consul takes the service name from `spring.application.name` by default; it can be overridden via `spring.cloud.consul.discovery.service-name`.

Spring Cloud Consul uses the Spring Application Context ID as the default instance ID. It can be explicitly set with `spring.cloud.consul.discovery.instance-id`.

Consul requires the service ID to be unique on the same agent. Multiple nodes/agents may register the same service name to form a group of service instances; this is normal operation. Therefore, distinguish duplicate `Name` (usually desired) from duplicate `ID` on the same agent (a conflict).

### 5.1. Configuring Consul

```yaml
spring:
  application:
    name: inventory-service
  cloud:
    consul:
      discovery:
        service-name: inventory-service
        instance-id: "${spring.application.name}:${POD_UID:${spring.cloud.client.hostname}:${server.port}}"
```

When running on Kubernetes, you can use the same `POD_UID` variable exposed via the Downward API. If each Pod has its own Consul Agent sidecar, the ID should still be stable and unique within that agent; if multiple instances register with the same agent, ensure IDs do not collide within that agent.

### 5.2. Checking Consul Catalog and Health

Read the service by name:

```bash
curl http://consul:8500/v1/catalog/service/inventory-service
```

Read instances along with health checks:

```bash
curl "http://consul:8500/v1/health/service/inventory-service?passing=false"
```

Inspect `ServiceName`, `ServiceID`, `Address`, `Port`, `Node`, and `Checks` fields. Two registrations with the same service name on two different nodes are normal; two registrations with the same service ID on one agent require investigation.

If ACLs are enabled, use a token with permission to read the Catalog/Health API. Do not put real ACL tokens into command history or shared logs.

## 6. Zookeeper: Service Path and Instance ID

Spring Cloud Zookeeper typically uses `spring.application.name` as the service name and stores instances under a root path, commonly `/services` by default. You can configure `spring.cloud.zookeeper.discovery.root` and `spring.cloud.zookeeper.discovery.instance-id`.

Conceptual znode layout:

```text
/services
  /inventory-service
    /inventory-pod-a
    /inventory-pod-b
    /inventory-pod-c
```

Curator Service Discovery stores instances using the structure `base path / service name / instance id`. Thus, if two replicas share the same service name and instance ID, they target the same znode path.

Spring Cloud Zookeeper provides the `spring.cloud.zookeeper.discovery.instance-id` property; configuration docs describe the default as a random UUID in some versions. Discovery docs also mention the instance ID based on the Spring Context ID. Verify the default of the release train you are using rather than assuming across versions. Even when relying on defaults, ensure the actual IDs of running replicas do not collide.

Explicit configuration example:

```yaml
spring:
  application:
    name: inventory-service
  cloud:
    zookeeper:
      connect-string: zk-1:2181,zk-2:2181,zk-3:2181
      discovery:
        root: /services/production
        instance-id: "${spring.application.name}:${POD_UID:${spring.cloud.client.hostname}:${server.port}}"
```

Inspect znodes:

```text
ls /services/production
ls /services/production/inventory-service
get /services/production/inventory-service/<instance-id>
```

If two processes write to the same service path and instance ID, they can collide at the same node. Exact behavior depends on the registration mode and Curator/Spring Cloud Zookeeper version; do not assume two processes will be stored as two independent instances.

## 7. Designing a Proper Instance ID

A good instance ID should satisfy:

1. **Unique within the scope required by the registry:** per `appName` in Eureka, per agent in Consul, per service path in Zookeeper.
2. **Stable across the process lifecycle:** heartbeats, updates, and deregistration must reference the same ID.
3. **Distinct across concurrent replicas:** do not use only the service name or a shared static value across all Pods.
4. **Traceable:** from the ID, you can identify the corresponding Pod, container, or node.
5. **Free of secrets:** IDs can appear in Dashboards, logs, and registry APIs.

Common ID sources:

| Source | Advantages | Notes |
|---|---|---|
| Kubernetes Pod UID | Unique per Pod and traceable via the Kubernetes API. | A recreated Pod after rollout gets a new UID; must be passed via the Downward API. |
| Hostname + port | Easy to configure; useful on VMs or bare metal. | Hostnames can collide or be unstable; multiple processes on one host need distinct ports. |
| Container ID | Distinguishes containers on the same host. | ID changes when container is recreated; can be long and need normalization. |
| Platform instance ID | Suitable for PaaS/Cloud Foundry/Kubernetes operators. | Must ensure a distinct value is injected for each replica. |
| Random UUID at startup | Easy uniqueness when no platform ID exists. | Harder to trace and changes on restart; stale registrations must be handled via lifecycle/lease. |

Do not use `spring.application.name` alone as the instance ID because all replicas of the same service will have the same value. Likewise, do not use a static `INSTANCE_ID` variable copied identically in manifests for all replicas.

### 7.1. Distinguishing Instance ID from Metadata

Do not pack everything into the ID. Use metadata for information that can change or needs filtering:

```yaml
eureka:
  instance:
    metadata-map:
      zone: zone-a
      version: v2
      pod-name: ${HOSTNAME}
```

The instance ID should identify a running instance; metadata describes that instance. If version or zone changes, you do not necessarily have to change the ID if the process remains the same instance in the registry lifecycle.

## 8. Checking the Service Name on Provider and Consumer

When a consumer cannot find a service, check in order:

1. **Provider config:** read `spring.application.name` and registry integration overrides.
2. **Consumer target:** check the service ID in the URL `http://<service-id>` or the `getInstances(serviceId)` argument.
3. **Environment/profile:** compare `application.yml`, profile files, environment variables, command-line arguments, and config server.
4. **Registry endpoint:** confirm provider and consumer use the same Eureka cluster, Consul datacenter/namespace, or Zookeeper root/ensemble.
5. **Services list:** call `DiscoveryClient.getServices()` to see the names the client actually knows about.
6. **Instance list:** call `getInstances()` with the exact service ID and inspect host, port, and metadata.
7. **Health state:** check whether the registry filters out non-passing or non-`UP` instances.
8. **Cache/refresh:** check when the provider registered and when the consumer last refreshed.

Diagnostic endpoint example inside the application:

```java
import java.util.List;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Service;

@Service
public class DiscoveryDiagnostics {

    private final DiscoveryClient discoveryClient;

    public DiscoveryDiagnostics(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public List<String> services() {
        return discoveryClient.getServices();
    }

    public List<ServiceInstance> instances(String serviceId) {
        return discoveryClient.getInstances(serviceId);
    }
}
```

Only expose this diagnostic endpoint in an authenticated administrative environment; service lists and hosts/ports are internal infrastructure details.

## 9. Checking Duplicate Instance IDs in Each Registry

### 9.1. Eureka

- Open the application in the Dashboard and count instances.
- Compare the `instanceId` of each replica.
- Check `eureka.instance.instance-id` and the resolved placeholder value.
- Check `appName`; the same ID under two different `appName`s is not the same Eureka registration.
- Check register, heartbeat, and cancel logs for each process.
- Use the REST API to confirm which host/port the server stores for that ID.

Eureka uses the `appName`/`instanceId` pair to register, renew, and cancel. Therefore, when two processes share that pair, one process can overwrite the other's info; when one process cancels, the shared record can be deleted even while the other process is still running.

### 9.2. Consul

- Check `ServiceName`, `ServiceID`, and `Node` in the Catalog.
- Determine whether registrations with the same Service ID are on the same Consul agent.
- Compare `spring.cloud.consul.discovery.instance-id` configuration across replicas.
- Check local agent logs for service registrations being updated or deregistered.
- Compare health checks to distinguish ID collisions from `critical` services.

Consul allows the same service name to appear across multiple nodes; the service ID must be unique per agent. If two processes register the same ID on one agent, the local registration may be updated/replaced instead of creating two independent services.

### 9.3. Zookeeper

- Verify `spring.cloud.zookeeper.discovery.root` is identical on provider and consumer.
- List child nodes under the service path.
- Compare the instance ID in each replica's logs with the znode name.
- Inspect the znode payload to see the advertised host/port.
- Check sessions, ephemeral nodes, and deregistration when a process stops.

Curator uses the service name and instance ID to determine the registration path. The same name/ID pair leads to the same path, so it cannot represent two independent instances simultaneously.

## 10. Fixing a Wrong Name or Duplicate ID

Follow this order to avoid accidentally deleting an active registration:

**Step 1 – Record current state.** Save service name, instance ID, host, port, node/Pod, status, and timestamp from the registry.

**Step 2 – Identify the process owning the ID.** Cross-reference logs of each replica, hostname, Pod UID, and deployment metadata. Do not infer from a single Dashboard row alone.

**Step 3 – Fix the configuration source.** Fix `spring.application.name` or the registry-specific service name if the provider registered under the wrong name; fix the instance ID if multiple replicas share the same ID.

**Step 4 – Deploy the new configuration.** Ensure each replica receives a distinct ID value after placeholders/environment variables resolve. Verify at least two concurrent replicas.

**Step 5 – Verify the new registrations.** The registry must show the full number of instances, each ID distinct within the required scope, and accurate hosts/ports.

**Step 6 – Clean up old records in a controlled way.** Only deregister stale registrations after verifying the corresponding process has stopped or the old ID is no longer in use. Never manually delete an ID currently used by a healthy replica.

**Step 7 – Verify the consumer.** Call `getServices()` and `getInstances(serviceId)`, then send requests through LoadBalancer to confirm multiple replicas can be selected.

**Step 8 – Monitor post-deployment.** Watch heartbeats, health checks, instance counts, request errors, and cache convergence time.

## 11. Quick Error and Remediation Table

| Symptom | Possible Cause | How to Fix |
|---|---|---|
| Consumer cannot find the service | Wrong `spring.application.name` or service override. | Standardize the service name on provider/consumer and check `getServices()`. |
| Service appears under two names | Different profile or environment overrides. | Compare resolved configuration on each replica. |
| Eureka shows only one instance despite multiple replicas | Duplicate `appName`/`instanceId`. | Generate a unique instance ID within `appName`. |
| Consul keeps only one registration on the same agent | Duplicate service ID on the agent. | Assign a unique ID for each process registering to that agent. |
| Zookeeper shows only one child node for two replicas | Duplicate service name/instance ID producing the same znode path. | Generate a unique instance ID per replica. |
| Registry has instances, but consumer does not see them | Consumer uses wrong registry, namespace/root, or stale cache. | Check endpoint, namespace, refresh, and DiscoveryClient. |
| Instance displays properly, but calls fail | Wrong host/port or unreachable network. | Check address, port, DNS, firewall, and readiness. |
| Instance disappears when one replica shuts down | Two replicas shared an ID and one deregistered the shared record. | Fix the ID first, then re-register and clean up stale records. |
| Old instance remains after rollout | Deregistration/lease/session not expired or cache not refreshed. | Check lifecycle, lease/session, and cache; clean up stale entries safely. |
| ID changes on every restart and is hard to trace | Using random UUID without identifying metadata. | Use a platform ID or record hostname/Pod UID in metadata. |

## 12. Testing Multiple Replicas Before Deployment

A simple test should run at least two replicas with the same service name:

1. Start replicas A and B simultaneously.
2. Confirm both register under the same service name.
3. Confirm instance IDs are distinct according to the registry's uniqueness scope.
4. Verify each registration's host/port points to the right replica.
5. Gracefully stop replica A.
6. Confirm only A's registration is removed; B remains present and healthy.
7. Restart A or start replica C.
8. Confirm the new registration does not overwrite B.
9. Call from a consumer through LoadBalancer and observe that multiple instances can be selected.

In automated tests, you can assert the instance count and set of IDs:

```java
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class DiscoveryRegistrationTest {

    @Autowired
    DiscoveryClient discoveryClient;

    @Test
    void replicasHaveUniqueIds() {
        List<ServiceInstance> instances =
                discoveryClient.getInstances("inventory-service");

        Set<String> instanceIds = instances.stream()
                .map(ServiceInstance::getInstanceId)
                .collect(Collectors.toSet());

        assertThat(instances).hasSize(2);
        assertThat(instanceIds).hasSize(2);
    }
}
```

This test assumes the registry implementation exposes `instanceId` via `ServiceInstance` and both replicas are registered and health-passing. If an integration does not expose the instance ID that way, check the native ID field in the registry response.

## 13. Observability and Prevention

Log the following fields during registration at startup:

- Resolved service name/service ID.
- Resolved instance ID.
- Advertised host/IP and port.
- Active profile and namespace/datacenter/root path.
- Registry endpoint or agent the client connects to.
- Registration success/failure and timestamp.

Do not log registry credentials or tokens. For metrics, track instance count per service, empty-discovery rate, registration/deregistration counts, health state, and heartbeat failures.

Preventive measures:

1. Use a standard, lowercase DNS-label service name consistent across provider, consumer, deployment, and documentation.
2. Only override the service name for a clear reason; document overrides so consumers use the right ID.
3. Build instance IDs from a per-replica identifier such as Pod UID or platform instance ID.
4. Do not use `spring.application.name` alone as the instance ID.
5. Respect the specific uniqueness scopes of Eureka, Consul, and Zookeeper.
6. Do not hardcode an identical instance ID in replicated manifests.
7. Test scaling to at least two replicas and shutting down individual replicas.
8. Monitor registration, heartbeats, health checks, and deregistration.
9. Clean up stale records only after verifying the owning process has stopped.
10. Protect diagnostic endpoints because service catalogs expose internal topology.

## 14. Diagnostic Checklist

| Question | Expected Result |
|---|---|
| Which service name does the provider register? | Resolved name matches what the consumer looks up. |
| Which service ID does the consumer call? | Matches the registry integration and namespace exactly. |
| Does `getServices()` include that service? | Contains the expected service name. |
| How many instances does `getInstances(serviceId)` return? | Matches the number of healthy running replicas. |
| What is each replica's instance ID? | Distinct within the scope required by the registry. |
| Are host/port values accurate? | Each ID points to the right replica. |
| Which registry is in use? | Provider and consumer read/write the same cluster, datacenter, or root. |
| Is health passing/UP? | Instances are eligible for discovery/load balancing. |
| Are there stale registrations? | Old records are identified and cleaned up after verification. |
| When one replica stops, does the remaining replica stay up? | Deregistration does not accidentally delete another registration. |

## Conclusion

The service name identifies the service group; the instance ID identifies each running instance within the registry's scope. Multiple replicas sharing a service name is by design, but they must have non-conflicting instance IDs: Eureka requires uniqueness within the application name, Consul requires the service ID to be unique per agent, and Zookeeper uses the service name/instance ID pair to construct the znode path.

When a consumer cannot find a service, compare the resolved service names on provider and consumer, inspect `DiscoveryClient.getServices()`, and confirm the registry/namespace in use. When fewer instances appear than replicas or records unexpectedly change addresses, inspect instance IDs, hosts/ports, register/heartbeat/deregister logs, and registry uniqueness rules. Use per-replica identifiers like Kubernetes Pod UID, test with at least two replicas, and only delete stale registrations after verifying the owning process has stopped.

## References

- [Spring Cloud Netflix – Changing the Eureka Instance ID](https://docs.spring.io/spring-cloud-netflix/docs/current/reference/html/index.html): default service ID, default instance ID, and configuring a unique ID per appName.
- [Spring Cloud Netflix – Configuration Properties](https://docs.spring.io/spring-cloud-netflix/reference/configprops.html): `eureka.instance.instance-id` and uniqueness scope within appName.
- [Spring Cloud Consul – Service Discovery](https://docs.spring.io/spring-cloud-consul/reference/discovery.html): service name, default instance ID, and `service-name`/`instance-id` configuration.
- [Consul Agent Service API](https://developer.hashicorp.com/consul/api-docs/agent/service): service ID must be unique per agent.
- [Consul Service Definition](https://developer.hashicorp.com/consul/docs/reference/service): service name and ID, per-node ID scope.
- [Spring Cloud Zookeeper – Service Discovery](https://docs.spring.io/spring-cloud-zookeeper/reference/discovery.html): service name, instance ID, and default port.
- [Spring Cloud Zookeeper – Common Application Properties](https://docs.spring.io/spring-cloud-zookeeper/reference/appendix.html): `spring.cloud.zookeeper.discovery.instance-id` and root path.
- [Apache Curator – Service Discovery](https://curator.apache.org/docs/service-discovery/): base path/service/instance ID structure and registration/deregistration APIs.
