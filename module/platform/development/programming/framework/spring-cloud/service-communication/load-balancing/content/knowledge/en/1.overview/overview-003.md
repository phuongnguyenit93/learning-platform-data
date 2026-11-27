# Service Name, Host, Port, and ServiceInstance

In a microservices system, a service often runs multiple replicas to increase availability and fault tolerance. When another service needs to call it, it should target the **logical name of the service**. Spring Cloud LoadBalancer uses that name to find the servers providing the service, picks a suitable server, and forwards the request to that specific address.

To understand this flow, distinguish four concepts: service ID, host address, port, and the `ServiceInstance` object.

## 1. From Service Name to a Specific Server

Suppose a system has an order service and a product catalog service. The catalog service is deployed as two replicas:

| Property | First Replica | Second Replica |
|---|---|---|
| Service ID | `catalog-service` | `catalog-service` |
| Instance ID | `catalog-1` | `catalog-2` |
| Host | `10.0.1.21` | `10.0.1.22` |
| Port | `8081` | `8081` |
| URI | `http://10.0.1.21:8081` | `http://10.0.1.22:8081` |

Both replicas provide the same logical service `catalog-service`, but have different network addresses. When the order service calls:

~~~text
http://catalog-service/products/42
~~~

it is calling by **service ID**. With an HTTP client integrated with Spring Cloud LoadBalancer, this logical name is resolved to a list of available replicas. The load balancer picks one replica, such as `catalog-2`, and sends the request to the corresponding URI.

~~~mermaid
flowchart LR
    A["Order Service"] -->|"GET /products/42<br/>catalog-service"| B["Spring Cloud LoadBalancer"]
    B -->|"selects a ServiceInstance"| C["catalog-1<br/>10.0.1.21:8081"]
    B -->|"or selects"| D["catalog-2<br/>10.0.1.22:8081"]
~~~

In a typical call, the load balancer chooses one instance to handle the request. It does not broadcast the same request to all replicas.

## 2. Service ID Is the Logical Name of the Service

A **Service ID** (also called service name in many systems) is the identifier a client uses to request a service. For example:

- `catalog-service`: product catalog service.
- `order-service`: order management service.
- `payment-service`: payment service.

A Service ID represents a group of instances providing the same functionality. It is not the IP address, hostname, or port of a specific server.

This distinction allows the system to change the number and locations of instances without forcing every client to modify its configuration. If `catalog-service` adds a third replica, clients still call the same service ID; the instance supplier updates the list so LoadBalancer can select the new replica.

The Service ID must match the identifier used by the discovery source or instance configuration. If the client calls `catalog-service` while the registry only registers `catalog`, the load balancer may find no instances.

### How Do Service ID and Instance ID Differ?

These two names answer two different questions:

- **Service ID:** which logical service does this instance provide?
- **Instance ID:** which specific deployment is this within that service group?

For example, `catalog-service` may consist of `catalog-1`, `catalog-2`, and `catalog-3`. Instances share the same Service ID, while Instance ID must distinguish each replica within the scope of the discovery source in use.

Instance ID is useful when inspecting logs, dashboards, the registry, or handling instance registration and deregistration events. Depending on the discovery source, this value may be generated automatically or supplied by application configuration.

## 3. Host and Port Identify Where an Instance Accepts Connections

Once an instance is selected, the client needs to know where to connect. That address is typically built from **scheme**, **host**, and **port**.

### Host

Host is the machine name or network address that the client can use to reach the instance. Common forms include:

- IPv4 address, for example `10.0.1.21`.
- IPv6 address, for example `2001:db8::21`.
- DNS name, for example `catalog-2.internal.example`.
- Machine/container name resolvable within the deployment network.

The host must be meaningful from the **calling client's** perspective. An address might be reachable from a developer machine but unreachable from a container or another Kubernetes network. Therefore, the host published in the service registry must be an address that clients in the deployment environment can actually route to.

### Port

Port is the network port on which the instance process is listening. For example, a Spring Boot application may listen on port `8081`.

In container environments, distinguish between the port inside the container and the port mapped outside. If the client and server reside in the same container network, the client typically must use the port the service listens on inside that network. Using the published host port by mistake can cause connections to fail.

### Scheme and URI

Scheme indicates the protocol, typically `http` or `https`. Host and port combined with the scheme form the instance's base URI:

~~~text
http://10.0.1.21:8081
https://catalog-2.internal.example:8443
~~~

In Spring Cloud, an instance's security status is represented by `isSecure()`; the instance's URI represents the address usable to build the target call. Do not assume every instance uses HTTP or the same port: each instance can have its own configuration.

The API path and query string are typically appended to the base URI when making a request, for example:

~~~text
http://10.0.1.21:8081/products/42?include=price
~~~

## 4. ServiceInstance Represents a Specific Deployment

In Spring Cloud Commons, `org.springframework.cloud.client.ServiceInstance` is the interface describing a service instance. Spring Cloud LoadBalancer works with instance objects to select the call target.

A `ServiceInstance` typically provides the following information:

| Method | Meaning |
|---|---|
| `getServiceId()` | Service ID provided by the instance |
| `getInstanceId()` | Identifier of the deployment; depending on the implementation, a value may not be provided |
| `getHost()` | Host of the instance |
| `getPort()` | Port on which the instance accepts connections |
| `isSecure()` | Indicates whether the instance uses a secure connection |
| `getUri()` | URI of the instance, combining protocol and address information |
| `getMetadata()` | Key/value metadata map associated with the instance |

Example reading information from an instance:

~~~java
import java.net.URI;
import java.util.Map;

import org.springframework.cloud.client.ServiceInstance;

void inspect(ServiceInstance instance) {
    String serviceId = instance.getServiceId();
    String instanceId = instance.getInstanceId();
    String host = instance.getHost();
    int port = instance.getPort();
    boolean secure = instance.isSecure();
    URI uri = instance.getUri();
    Map<String, String> metadata = instance.getMetadata();

    System.out.println("serviceId = " + serviceId);
    System.out.println("instanceId = " + instanceId);
    System.out.println("address = " + uri);
    System.out.println("secure = " + secure);
    System.out.println("metadata = " + metadata);
}
~~~

This is an example for inspecting information. In real applications, clients typically let Spring Cloud LoadBalancer select an instance through an integrated HTTP client; there is no need to manually fetch the list and write a server selection algorithm.

### What Is Metadata Used For?

Metadata consists of key/value pairs supplied by the discovery source or instance configuration. For example:

~~~text
zone=ap-southeast-1a
version=v2
environment=staging
~~~

Metadata can support partitioning by deployment zone, version, environment, or other operational criteria. However, simply declaring metadata does not automatically alter routing decisions. To prefer instances in the same zone, call only a matching version, or apply a custom criterion, the application needs a corresponding supplier, filter, or LoadBalancer policy.

### Who Creates ServiceInstance?

ServiceInstance is an abstraction; concrete objects can come from multiple sources:

- **Service registry/discovery:** such as Eureka or Consul registering instances and providing address details.
- **Deployment platform:** an integration can obtain endpoints from the orchestration environment.
- **Static configuration list:** useful for simple environments, development, or testing when a separate registry is not needed.

A common implementation in Spring Cloud Commons is `DefaultServiceInstance`. Other integrations may provide their own implementations. Clients should work through the `ServiceInstance` interface rather than depending on how a specific registry stores data.

## 5. How Spring Cloud LoadBalancer Uses ServiceInstance

Conceptually, resolving a service ID and selecting an instance proceeds in these steps:

1. The HTTP client sends a request to a URI whose logical hostname is the service ID, e.g., `http://catalog-service/products/42`.
2. The LoadBalancer integration component recognizes the service ID `catalog-service`.
3. `ServiceInstanceListSupplier` provides the list of instances matching that service ID. The supplier may fetch data from a discovery client, static configuration, or an application-customized source.
4. The load balancer picks an instance from the list according to the configured policy, such as round-robin.
5. The HTTP client uses the selected instance's address to execute the request.

`DiscoveryClient` and `ServiceInstanceListSupplier` have related roles but are not synonymous. The discovery client is an abstraction for querying registered instances. The supplier is the component that provides candidate lists to Spring Cloud LoadBalancer; it can use a discovery client or another data source.

You can query instances from the discovery client to inspect discovery data:

~~~java
import java.util.List;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;

List<ServiceInstance> instances =
        discoveryClient.getInstances("catalog-service");

for (ServiceInstance instance : instances) {
    System.out.println(instance.getServiceId() + " -> " + instance.getUri());
}
~~~

The snippet above illustrates reading the instance list. It does not perform load balancing for an HTTP request. When using a LoadBalancer-integrated client, fetching the list, choosing an instance, and forwarding the request happen inside that integration flow.

If the list is empty, possible causes include a mismatched service ID, unregistered instances, an out-of-sync registry, misconfigured discovery, or no instances supplied by the supplier. If the list contains instances yet requests still fail, check host, port, protocol, network routing, and the actual server status.

## 6. HTTP Client Integration Example

With `RestClient`, you can annotate the builder with `@LoadBalanced` so requests using a service ID are handled through Spring Cloud LoadBalancer:

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

A client can call the service by logical name:

~~~java
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
class CatalogClient {

    private final RestClient restClient;

    CatalogClient(RestClient.Builder builder) {
        this.restClient = builder
                .baseUrl("http://catalog-service")
                .build();
    }

    Product findProduct(long id) {
        return restClient.get()
                .uri("/products/{id}", id)
                .retrieve()
                .body(Product.class);
    }
}
~~~

The example assumes the application already has the Spring Cloud LoadBalancer dependency compatible with the Spring Cloud release train in use and that the injected builder is the `@LoadBalanced`-qualified builder. In that case, `catalog-service` is the service ID resolved to a `ServiceInstance`. If you call a URI containing an instance's IP/host and port directly, the request already specifies a concrete target and no longer uses the service ID to choose among the instance group in this manner.

WebClient and OpenFeign can also integrate with Spring Cloud LoadBalancer when properly configured. Regardless of which HTTP client is used, the idea remains the same: the client sends by service ID, LoadBalancer finds an instance, and the request is sent to the selected instance's host and port.

## 7. Common Mistakes When Declaring Instance Addresses

| Symptom | Possible Cause | How to Check |
|---|---|---|
| No server found for service ID | Wrong service name or no registered instances | Compare the service ID in the request with the name in the registry/config; inspect the instance list |
| Connection refused | Wrong port or process not listening | Check the application's actual port and the published port |
| Host cannot be resolved | Host does not exist in DNS or is unusable from the client's network | Check DNS and routing from the environment running the client |
| Works on local machine but fails in container | `localhost` resolves to the client's own container | Use a hostname/IP reachable across the container network |
| Wrong protocol connection | Scheme or secure flag does not match server | Cross-check HTTP/HTTPS, certificates, and instance configuration |
| Request goes to stopped instance | Stale discovery data or supplier not filtering failed instances | Check heartbeat/health status, registry refresh interval, and instance filters |
| Metadata does not affect selection | No policy reading and using metadata | Check supplier, filter, or LoadBalancer algorithm configuration |

A common mistake is registering `localhost` as an instance's host in a multi-machine or multi-container system. `localhost` is always interpreted from the environment making the connection. Thus, when the client runs in another container, `localhost:8081` usually points to the client container itself rather than the service-providing container.

Also distinguish **present in the list** from **currently healthy**. A `ServiceInstance` object describes an endpoint supplied by a data source; the object itself does not prove the server is still accepting requests successfully. Health verification depends on the configured registry, supplier, health checks, or filtering mechanisms.

## 8. Checklist When Reading or Configuring ServiceInstance

Before troubleshooting a load-balanced request, confirm step by step:

1. The client is calling the correct service ID.
2. The discovery source or configuration supplies an instance list for that service ID.
3. Each instance has a host and port valid for the client's network environment.
4. Scheme/secure matches the protocol the server is serving.
5. The selected instance is running and reachable.
6. If metadata is used for routing, a LoadBalancer policy is configured to read that metadata.

Keep the core relationship in mind: **service ID identifies the service group; ServiceInstance describes one deployment in that group; host and port identify that deployment's network address**. Spring Cloud LoadBalancer uses the `ServiceInstance` list to choose a target for the request, enabling clients to communicate with services via logical names instead of hardcoding a single server's address.
