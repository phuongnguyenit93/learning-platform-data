# Declaring Multiple Addresses and Cluster Endpoint Selection

## 1. What is an endpoint in an Elasticsearch connection?

A Spring Data Elasticsearch application communicates with Elasticsearch through a Java client. The client sends HTTP or HTTPS requests to an Elasticsearch endpoint, receives responses, and passes data back to abstractions such as `ElasticsearchOperations` or repositories.

An endpoint is typically identified by a hostname and an HTTP port:

~~~text
http://es-node-1.internal:9200
https://search.example.com:9243
~~~

Where:

- `http` or `https` specifies the connection protocol.
- `es-node-1.internal` or `search.example.com` is a hostname resolvable and reachable from the machine running the application.
- `9200` or `9243` is the HTTP API port exposed by the Elasticsearch environment.

Distinguish the HTTP API port from the internal inter-node transport port. In common default setups, applications use HTTP port `9200`; the transport port is typically `9300` and is reserved for communication between nodes inside the cluster. Do not put the transport port into Spring Data Elasticsearch configuration for REST API calls.

A cluster can have multiple nodes, and each node can expose its own HTTP endpoint. The client may connect through a single stable endpoint provided by a load balancer or infrastructure service, or be configured with multiple endpoints of nodes capable of serving application requests.

## 2. Why declare multiple addresses?

If an application knows only a single node, every initial request goes through that node. When that node fails or becomes unreachable, the application can lose search capability even though other nodes in the cluster are still healthy.

Declaring multiple endpoints gives the client multiple addresses to send requests to. With the Elasticsearch REST client, configured nodes are used to distribute load; the client has mechanisms to handle node failures and switch to another node according to its client policy.

Example of a cluster with three nodes exposing HTTP endpoints:

~~~text
es-node-1.internal:9200
es-node-2.internal:9200
es-node-3.internal:9200
~~~

General flow:

~~~text
                         Spring Boot application
                                   |
                                   v
                         Spring Data Elasticsearch
                                   |
                                   v
                              REST client
                                   |
                    +--------------+--------------+
                    |              |              |
                    v              v              v
              es-node-1      es-node-2      es-node-3
                    \              |              /
                     \             |             /
                      +-------- Elasticsearch ---+
                                cluster
~~~

The client can pick a node from the list for each request. If a node cannot serve a request due to a connection error, the client can temporarily mark that node as unavailable and try another node via the REST client's failover mechanism.

This improves fault tolerance at the connection layer. It does not replace cluster high availability, replica shards, infrastructure monitoring, or application-level business error handling.

## 3. Two approaches: one stable endpoint or multiple direct endpoints

An application does not always need to know the address of every node. Two deployment approaches are common:

| Connection Approach | Application-Side Configuration | Best Suited When |
|---|---|---|
| Single endpoint via load balancer, proxy, or service DNS | One stable hostname and port | Using managed Elasticsearch, Kubernetes Service, or infrastructure that already has a load-distribution layer |
| Multiple direct node endpoints | List of node hostnames and ports | Application accesses HTTP nodes directly and needs client-side load distribution and failover |

### Single endpoint via load balancer or service DNS

For example:

~~~text
search.internal.example:9200
~~~

A load balancer or network service sits in front of the cluster and forwards requests to an appropriate node. The application only needs to configure that stable endpoint.

This approach reduces the application's coupling to a specific list of nodes. When nodes are replaced or IP addresses change, infrastructure can update backends behind the endpoint without changing application configuration.

In Kubernetes, a Service hostname is usually a better endpoint than individual Pod IPs because the Service provides a stable address and manages the backends.

### Multiple direct node endpoints

For example:

~~~text
es-node-1.internal:9200
es-node-2.internal:9200
es-node-3.internal:9200
~~~

This approach lets the REST client choose among the declared nodes. All addresses must belong to the same cluster, be reachable from the application, and share compatible protocol and authentication settings.

Do not mix endpoints from two independent clusters in the same list. The client could send consecutive requests to two different clusters, resulting in inconsistent search results, index states, or write operations.

## 4. Declaring multiple endpoints with ClientConfiguration

Spring Data Elasticsearch provides `ClientConfiguration` to describe addresses and connection options. The `connectedTo` method accepts multiple `host:port` strings.

Configuration example for a Spring Data Elasticsearch application using `Rest5Client`:

~~~java
import java.time.Duration;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.elasticsearch.client.ClientConfiguration;
import org.springframework.data.elasticsearch.client.elc.ElasticsearchConfiguration;

@Configuration
public class ElasticsearchClientConfig extends ElasticsearchConfiguration {

    @Override
    public ClientConfiguration clientConfiguration() {
        return ClientConfiguration.builder()
            .connectedTo(
                "es-node-1.internal:9200",
                "es-node-2.internal:9200",
                "es-node-3.internal:9200"
            )
            .withConnectTimeout(Duration.ofSeconds(3))
            .withSocketTimeout(Duration.ofSeconds(20))
            .build();
    }
}
~~~

Meaning of each part:

- `@Configuration` registers the Spring configuration class.
- `ElasticsearchConfiguration` provides the modern Spring Data Elasticsearch imperative client configuration.
- `clientConfiguration()` returns the connection description used to build the Elasticsearch client.
- `connectedTo(...)` declares the list of cluster endpoints.
- `withConnectTimeout(...)` limits the time allowed to establish a connection.
- `withSocketTimeout(...)` limits the time spent waiting for data on a connection as configured by the client.

Once configuration is complete, the application can inject `ElasticsearchOperations`, `ElasticsearchClient`, or repositories into services. These abstractions share the configured client; there is no need to create a new client for each repository.

Example service using operations:

~~~java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.stereotype.Service;

@Service
public class ProductSearchService {

    private final ElasticsearchOperations operations;

    public ProductSearchService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    // Search methods using operations
}
~~~

Let Spring manage the client's lifecycle as a shared bean. The REST client is designed to be shared across requests and holds network resources, a connection pool, and internal threads that must be closed properly at shutdown. Avoid creating and discarding a new client on every repository call or every user HTTP request.

## 5. Configuring endpoints from the environment

Cluster addresses vary by deployment environment. Development machines may use `localhost`, test environments may use internal services, and production uses DNS or platform-provided endpoints.

Do not hardcode production addresses directly in source code. You can place the endpoint list in external configuration:

~~~properties
app.elasticsearch.endpoints=es-node-1.internal:9200,es-node-2.internal:9200,es-node-3.internal:9200
~~~

Then read the list and pass it to `connectedTo`:

~~~java
import java.time.Duration;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.elasticsearch.client.ClientConfiguration;
import org.springframework.data.elasticsearch.client.elc.ElasticsearchConfiguration;

@Configuration
public class ElasticsearchClientConfig extends ElasticsearchConfiguration {

    private final String[] endpoints;

    public ElasticsearchClientConfig(
            @Value("${app.elasticsearch.endpoints}") String endpointList) {
        this.endpoints = endpointList.split("\\s*,\\s*");
    }

    @Override
    public ClientConfiguration clientConfiguration() {
        return ClientConfiguration.builder()
            .connectedTo(endpoints)
            .withConnectTimeout(Duration.ofSeconds(3))
            .withSocketTimeout(Duration.ofSeconds(20))
            .build();
    }
}
~~~

With Spring Boot, this value can be overridden via an environment variable using property binding conventions, such as `APP_ELASTICSEARCH_ENDPOINTS`. Provide separate values for each environment and verify that each hostname resolves from the container or VM running the application.

If endpoints are supplied as full URLs, parse out the hostname, port, and protocol according to the configuration API of the version in use. `connectedTo` in the example takes `host:port` strings, while HTTPS is enabled via a separate SSL option.

## 6. HTTPS connections, authentication, and proxies

When Elasticsearch requires TLS, enable SSL in the client configuration. For example:

~~~java
return ClientConfiguration.builder()
    .connectedTo(
        "es-node-1.internal:9200",
        "es-node-2.internal:9200"
    )
    .usingSsl()
    .withConnectTimeout(Duration.ofSeconds(3))
    .withSocketTimeout(Duration.ofSeconds(20))
    .build();
~~~

If the environment uses a private CA certificate or an Elasticsearch-issued fingerprint, configure certificate verification according to the documentation of your Spring Data Elasticsearch and Elasticsearch client versions. Do not disable TLS verification just to get a connection working.

Basic Auth authentication can be declared:

~~~java
return ClientConfiguration.builder()
    .connectedTo("search.internal.example:9200")
    .usingSsl()
    .withBasicAuth(username, password)
    .build();
~~~

`username` and `password` must come from a secret manager, environment variables, or an appropriate secrets mechanism. Never write real credentials into the repository or committed configuration files.

If the cluster sits behind a reverse proxy, you may need to configure a proxy or path prefix:

~~~java
return ClientConfiguration.builder()
    .connectedTo("gateway.internal.example:443")
    .usingSsl()
    .withPathPrefix("elasticsearch")
    .withProxy("proxy.internal.example:8080")
    .build();
~~~

Only configure `withPathPrefix` when the proxy actually requires that path. Verify that the proxy forwards all Elasticsearch APIs cleanly and does not alter requests or responses.

SSL, authentication, timeout, header, and proxy options apply to the client built from `ClientConfiguration`. When using multiple direct endpoints, ensure all endpoints support the same connection settings and credentials.

## 7. How does the client select nodes?

For the REST client, the node list is the set of candidate addresses to send requests to. The REST 5 Client distributes requests across available nodes via load balancing; client documentation describes round-robin selection. When a node error occurs, the client can perform failover and temporarily penalize the failing node before retrying.

Round-robin illustration with three nodes:

~~~text
Request 1 -> es-node-1
Request 2 -> es-node-2
Request 3 -> es-node-3
Request 4 -> es-node-1
Request 5 -> es-node-2
...
~~~

This is an illustrative model. Actual traffic may not be split evenly in strict proportion because requests have varying processing times, nodes carry different loads, and node failure handling can change the selection order.

Client-side load balancing chooses the HTTP node that receives the request. Elasticsearch then internally routes the operation to the shards and nodes holding the relevant data. Thus, the node receiving the HTTP request is not necessarily the node storing the shard for the queried document.

### When an endpoint fails

Suppose three endpoints are declared, but `es-node-2` loses connectivity:

~~~text
Request
   |
   v
REST client
   |
   +---- es-node-1: healthy
   |
   +---- es-node-2: connection error
   |
   +---- es-node-3: healthy
~~~

The REST client can mark the failed node as temporarily unavailable and try remaining nodes according to the client version's retry/failover policy. After a cooldown period, the node can be checked again and returned to the active rotation.

This mechanism handles errors at the connection layer. It does not mean every HTTP error or business error can be safely retried. For example, authentication errors, malformed requests, or data conflicts must be handled based on their root cause. For write operations, do not assume retries are always safe or that a request is guaranteed to execute exactly once.

## 8. Selecting nodes with NodeSelector

In some clusters, not every node should receive application requests. For example, a cluster may have dedicated master nodes focused solely on managing cluster state; the application should typically send queries to nodes with roles suited for HTTP traffic, such as coordinating nodes or data nodes.

The Elasticsearch REST client supports `NodeSelector` to filter the set of nodes allowed to receive requests. Spring Data Elasticsearch allows customizing the low-level client via `withClientConfigurer`.

Example with Spring Data Elasticsearch 6 and `Rest5Client`:

The following configuration is only appropriate when the client already has node metadata, such as when updated via sniffing. If the application only declares static endpoints without node discovery, omit this selector so the client uses all configured endpoints.

~~~java
import co.elastic.clients.transport.rest5_client.low_level.NodeSelector;
import org.springframework.data.elasticsearch.client.ClientConfiguration;
import org.springframework.data.elasticsearch.client.elc.ElasticsearchConfiguration;
import org.springframework.data.elasticsearch.client.elc.rest5_client.Rest5Clients;

import org.springframework.context.annotation.Configuration;

@Configuration
public class ElasticsearchClientConfig extends ElasticsearchConfiguration {

    @Override
    public ClientConfiguration clientConfiguration() {
        return ClientConfiguration.builder()
            .connectedTo(
                "es-node-1.internal:9200",
                "es-node-2.internal:9200",
                "es-node-3.internal:9200"
            )
            .withClientConfigurer(
                Rest5Clients.ElasticsearchRest5ClientConfigurationCallback.from(
                    restClientBuilder -> {
                        restClientBuilder.setNodeSelector(
                            NodeSelector.SKIP_DEDICATED_MASTERS
                        );
                        return restClientBuilder;
                    }
                )
            )
            .build();
    }
}
~~~

`NodeSelector.SKIP_DEDICATED_MASTERS` is a built-in selector to avoid sending requests to dedicated master-only nodes. It requires node metadata and roles, which are normally populated when using node discovery (sniffing). Without that metadata, do not enable this selector for a static endpoint list.

Understand the selector's limitations:

- `connectedTo(...)` defines the initial endpoints known to the client.
- `NodeSelector` filters candidate nodes based on the node information available to the client.
- The selector does not translate an address into another address, nor does it choose a different cluster.
- If the client lacks the required metadata, a role-based selector may not filter nodes as expected.
- Never configure a selector that excludes all nodes, as the client will have no valid node left to send requests to.

For clusters with one or a few stable endpoints behind a load balancer, `NodeSelector` is usually unnecessary. Distribution and backend selection are already the load balancer's responsibility.

## 9. Dynamic node discovery (sniffing)

The endpoint list declared via `connectedTo` is the starting point for client connectivity. In some environments, nodes may be added, removed, or replaced frequently. If you want the client to automatically update its node list from the cluster, you can use the sniffing mechanism supported by the Elasticsearch REST client.

The Sniffer periodically calls the nodes info API to retrieve the list of nodes advertised by the cluster, then updates the client's node list. Some implementations can also trigger a refresh when a node fails.

With Spring Data Elasticsearch 6, you can register a Sniffer as a bean depending on the low-level `Rest5Client`:

~~~java
import co.elastic.clients.transport.rest5_client.low_level.Rest5Client;
import co.elastic.clients.transport.rest5_client.low_level.sniffer.Sniffer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ElasticsearchSnifferConfig {

    @Bean(destroyMethod = "close")
    Sniffer elasticsearchSniffer(Rest5Client rest5Client) {
        return Sniffer.builder(rest5Client).build();
    }
}
~~~

Ensure the corresponding Sniffer dependency is on the classpath. The bean is closed when Spring shuts down the application; the Sniffer must be closed before the REST client to release background threads and resources cleanly.

General flow:

~~~text
REST client
    |
    +---- sends requests to known nodes
    |
    +---- Sniffer periodically calls Nodes Info API
                |
                v
          Elasticsearch cluster
                |
                v
        Advertised node list
                |
                v
        Updates client node list
~~~

Sniffing is useful when the application can directly reach the HTTP addresses advertised by the cluster. However, it can cause failures in networks with NAT, containers, or proxies if the addresses advertised by Elasticsearch are unreachable from the application.

The REST5 Sniffer defaults to assuming nodes use HTTP. If the cluster uses HTTPS, configure `ElasticsearchNodesSniffer` with the `HTTPS` scheme according to your client version's API; otherwise, node discovery may produce endpoints with the wrong protocol.

For example, an application accesses the cluster through a public load balancer, but the Nodes Info API returns internal addresses only reachable from another network. If the client switches to those addresses, requests will fail even though the original load balancer endpoint still works.

Therefore:

- Use an endpoint via a load balancer or Service DNS when infrastructure manages backend selection and exposes a stable address.
- Consider sniffing when the application is allowed to connect directly to nodes and advertised node addresses are reachable from the same network.
- Do not enable sniffing by default across all environments.
- If sniffing is enabled, verify the refresh interval, Sniffer shutdown lifecycle, and node list updates when the cluster topology changes.
- Only combine role/attribute-based selectors when node metadata is available and verified.

Sniffing is a node discovery mechanism, distinct from round-robin. Round-robin selects from the current node list; sniffing refreshes that list.

## 10. Choosing endpoints suited to each cluster topology

| Environment Type | Typical Configuration | Reason |
|---|---|---|
| Single-node local Elasticsearch | `localhost:9200` | Simple setup for development |
| Self-managed cluster, nodes with stable DNS | Multiple suitable node HTTP endpoints | Client can distribute load and fail over |
| Kubernetes | DNS of the Elasticsearch Service | Service maintains a stable endpoint as Pods change |
| Managed or cloud Elasticsearch | HTTPS endpoint provided by the vendor | Vendor manages topology and load balancing |
| Cluster behind a reverse proxy | Proxy hostname plus path prefix if needed | Application does not need to know backend node addresses |
| Private network with changing node IPs | Service discovery or load balancer | Avoids maintaining brittle static IP lists |

When choosing endpoints, verify:

1. The endpoint resolves via DNS and is reachable from the exact runtime where the application executes.
2. The port is the HTTP/HTTPS API port, not the internal transport port.
3. All endpoints in the list belong to the same cluster.
4. Receiving nodes have suitable roles and resources for the workload.
5. TLS, certificates, authentication, and index permissions are all compatible.
6. Firewalls, security groups, and network policies permit the connection.
7. Node addresses advertised by sniffing are reachable if using dynamic discovery.

## 11. Checking endpoints and cluster health

Before investigating Spring Data, test the endpoint from the exact machine or container running the application. You can use `curl`:

~~~bash
curl -k https://es-node-1.internal:9200/
~~~

In production, configure the proper CA/certificate and remove `-k`; the `-k` option should only be used as a temporary test in a controlled environment because it skips certificate verification.

Check cluster health:

~~~http
GET /_cluster/health
~~~

Check nodes and advertised HTTP addresses:

~~~http
GET /_nodes/http
~~~

You can inspect details such as:

- Node names and node roles.
- HTTP publish addresses.
- Cluster health and shard status.
- Which nodes are advertised for client use.

If an endpoint in the list cannot connect, determine whether it is a DNS issue, network route, firewall, TLS, authentication, or Elasticsearch service failure. Adding more addresses will not fix shared network configuration or certificate errors.

When the application starts but requests fail, check client logs for the hostname, port, timeout duration, and root cause. You can enable appropriate HTTP/client-layer logging in test environments to see which node received a request. Do not enable full request/response tracing containing sensitive data in production without a log protection policy.

## 12. Common mistakes when declaring multiple addresses

**Using the wrong port.** Configuring `9300` out of habit from node-to-node communication prevents the HTTP client from connecting. Use the HTTP API port exposed by the cluster.

**Declaring hostnames resolvable only on a developer machine.** An address that works on a laptop may not work inside a production container. Verify DNS and routing from the actual runtime.

**Mixing multiple clusters into one list.** Every endpoint in `connectedTo` must represent the same cluster and data environment. Do not use an endpoint list to alternate connections across independent clusters.

**Assuming adding endpoints creates a high-availability cluster.** Fault tolerance also depends on the cluster, shard replicas, quorum, load, network, and retry policies. The client can only pick among endpoints it can reach.

**Configuring sniffing behind a load balancer without checking publish addresses.** The client may receive unreachable internal IPs. Choose a stable load-balanced endpoint or configure networking so advertised addresses are reachable.

**Using NodeSelector without metadata.** Selectors based on roles or attributes need the corresponding node info. Confirm the client receives roles/attributes before applying a selector.

**Creating a client per request.** This wastes connection pools and threads while increasing connection counts to the cluster. Use a Spring-managed singleton bean.

**Retrying every error.** Not all errors can be fixed by switching nodes. HTTP 401/403, mapping, query, or data conflict errors must be handled at their root cause. Retrying write operations also requires considering duplicates and idempotency.

**Committing passwords or sensitive addresses to Git.** Use a secret manager or environment variables, and restrict endpoint access by network, account, and index.

## 13. Configuration workflow in a Spring Data Elasticsearch project

You can follow this sequence:

1. Determine the cluster topology: single node, multiple direct nodes, or an endpoint via load balancer/Service.
2. Select HTTP/HTTPS endpoints reachable from the application.
3. Confirm the endpoints belong to the same cluster and support the same security setup.
4. Externalize the endpoint list, timeouts, and connection settings per environment.
5. Create a `ClientConfiguration` and configure client beans according to your Spring Data Elasticsearch version.
6. Only add `NodeSelector` when role/attribute filtering is required and the client has matching metadata.
7. Only enable sniffing when advertised node addresses are reachable from the application.
8. Verify connectivity, cluster health, failover logs, and recovery when an endpoint becomes temporarily unavailable.

## 14. Client version differences to keep in mind

Elasticsearch client integration APIs change across Elasticsearch and Spring Data Elasticsearch generations. For example:

- Spring Data Elasticsearch 6.0 and later use Elasticsearch 9's `Rest5Client` in the default imperative configuration.
- Earlier versions use the legacy low-level `RestClient` alongside the Elasticsearch Java API Client.
- Callback class names, packages, and customized client types may differ between `Rest5Client` and the legacy `RestClient`.

With Spring Data Elasticsearch 6, the low-level `Rest5Client` configuration callback looks like:

~~~java
.withClientConfigurer(
    Rest5Clients.ElasticsearchRest5ClientConfigurationCallback.from(
        restClientBuilder -> {
            // Customize Rest5ClientBuilder here
            return restClientBuilder;
        }
    )
)
~~~

For versions using the legacy `RestClient`, Spring Data provides the corresponding callback in `RestClients`. Do not copy callback packages verbatim from a newer version into an older project. Check your actual dependencies and version-specific documentation before implementing.

## Conclusion

Declaring multiple endpoints gives Spring Data Elasticsearch multiple nodes for sending requests, distributing load, and failing over when a node errors out. `ClientConfiguration.connectedTo(...)` is the main configuration point for the address list; SSL, authentication, timeout, proxy, and callback options tailor the client to the deployment environment.

Endpoint selection should reflect the real topology: use a stable address via a load balancer or Service when infrastructure manages backends, or declare multiple direct nodes when the application can reach individual nodes. NodeSelector helps filter nodes by metadata; sniffing helps keep the node list updated. Both must be used under appropriate network conditions and matching client versions.

Good connection design starts with reachable endpoints, belonging to the same cluster, on the right HTTP API port, with valid security. Only then should load distribution, failover, and node discovery be layered on so the Spring Data Elasticsearch application communicates reliably with the cluster.

## References

- [Spring Data Elasticsearch — Elasticsearch Clients](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/clients.html)
- [Elasticsearch Java REST 5 Client](https://www.elastic.co/docs/reference/elasticsearch/clients/java/transport/rest5-client)
- [Elasticsearch REST 5 Client — Node Selector](https://www.elastic.co/docs/reference/elasticsearch/clients/java/transport/rest5-client/config/node_selector)
- [Elasticsearch REST 5 Client — Sniffer](https://www.elastic.co/docs/reference/elasticsearch/clients/java/transport/rest5-client/sniffer)
