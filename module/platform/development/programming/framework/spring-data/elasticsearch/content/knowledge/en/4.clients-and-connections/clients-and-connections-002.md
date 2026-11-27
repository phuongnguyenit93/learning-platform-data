# Configuring with `ElasticsearchConfiguration` and `ClientConfiguration`

Spring Data Elasticsearch requires a client to communicate with an Elasticsearch cluster. In the Java configuration of Spring Data Elasticsearch 5.x, two components typically go together:

- **`ClientConfiguration`** describes how to connect: node addresses, TLS, authentication credentials, timeouts, HTTP headers, proxies, and path prefixes.
- **`ElasticsearchConfiguration`** is the base configuration class of Spring Data Elasticsearch. You extend this class and provide a `ClientConfiguration`; Spring Data uses that configuration to register the client along with integration components such as `ElasticsearchOperations`.

`ClientConfiguration` is not the client that sends requests. It is an object describing the connection settings. `ElasticsearchConfiguration` uses that object to set up the Spring Data infrastructure.

This article focuses on Java configuration based on the Elasticsearch Java API Client in Spring Data Elasticsearch 5.x. Spring Data Elasticsearch 4.x versions use an older client mechanism with a different configuration API; do not mix the two configuration styles in the same application.

## 1. Configuration flow and components

The initialization flow can be visualized as follows:

~~~mermaid
flowchart TD
    A["Spring ApplicationContext"] --> B["ElasticsearchConfiguration"]
    B --> C["clientConfiguration()"]
    C --> D["ClientConfiguration"]
    D --> E["REST transport and Elasticsearch Java API Client"]
    E --> F["ElasticsearchOperations"]
    E --> G["ElasticsearchRepository"]
    F --> H["Application calls search, save, delete..."]
    G --> H
    H --> I["Elasticsearch cluster"]
~~~

The components have distinct responsibilities:

| Component | Responsibility |
|---|---|
| `ClientConfiguration` | Declares endpoints and HTTP/TLS/authentication options |
| `ElasticsearchConfiguration` | Creates and registers Elasticsearch integration infrastructure for Spring |
| `ElasticsearchClient` | Java API Client used to call Elasticsearch APIs |
| `ElasticsearchOperations` | High-level Spring Data operations API with entity mapping and conversion |
| `ElasticsearchRepository` | Repository abstraction for CRUD and query operations |

In a Spring Data application, business code usually works with repositories or `ElasticsearchOperations`. When direct access to newer Elasticsearch APIs is needed, the application can inject `ElasticsearchClient`.

## 2. Minimal configuration for a local environment

Suppose Elasticsearch is running at `localhost:9200` and does not require TLS or authentication. You can create a configuration class like this:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.elasticsearch.client.ClientConfiguration;
import org.springframework.data.elasticsearch.client.elc.ElasticsearchConfiguration;

@Configuration
public class ElasticsearchConfig extends ElasticsearchConfiguration {

    @Override
    public ClientConfiguration clientConfiguration() {
        return ClientConfiguration.builder()
                .connectedTo("localhost:9200")
                .build();
    }
}
~~~

Key points:

- `@Configuration` lets Spring discover the configuration class.
- `extends ElasticsearchConfiguration` uses the client configuration mechanism provided by Spring Data.
- `clientConfiguration()` returns the connection description.
- `connectedTo("localhost:9200")` specifies the Elasticsearch address.
- `build()` finalizes the configuration object.

Once the configuration is loaded into the application context, the corresponding infrastructure beans are registered for repositories and `ElasticsearchOperations` to use.

Addresses in `connectedTo` are typically written as `host:port`. TLS configuration is declared separately via `usingSsl()`; there is no need to include `http://` or `https://` in the host string.

## 3. Configuring repository scanning

If the application uses interfaces extending `ElasticsearchRepository`, Spring needs to know which packages contain those repositories.

You can declare `@EnableElasticsearchRepositories` on the configuration class:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.elasticsearch.client.ClientConfiguration;
import org.springframework.data.elasticsearch.client.elc.ElasticsearchConfiguration;
import org.springframework.data.elasticsearch.repository.config.EnableElasticsearchRepositories;

@Configuration
@EnableElasticsearchRepositories(
        basePackages = "com.example.catalog.repository"
)
public class ElasticsearchConfig extends ElasticsearchConfiguration {

    @Override
    public ClientConfiguration clientConfiguration() {
        return ClientConfiguration.builder()
                .connectedTo("localhost:9200")
                .build();
    }
}
~~~

Repository example:

~~~java
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {
}
~~~

Spring Data generates implementations for repository interfaces when repository scanning is properly configured.

`@EnableElasticsearchRepositories` controls repository discovery; `ElasticsearchConfiguration` provides client and operations infrastructure. These are related but distinct responsibilities.

In a Spring Boot application, auto-configuration may already set up repository scanning based on the default package. In that case, check the active configuration before adding `@EnableElasticsearchRepositories` to avoid duplicate repository setups or scanning the wrong packages.

## 4. Configuring multiple nodes

An Elasticsearch cluster can have multiple nodes capable of receiving requests. `connectedTo` accepts multiple addresses:

~~~java
@Override
public ClientConfiguration clientConfiguration() {
    return ClientConfiguration.builder()
            .connectedTo(
                    "es-node-1.internal:9200",
                    "es-node-2.internal:9200",
                    "es-node-3.internal:9200"
            )
            .build();
}
~~~

This list supplies endpoints for the HTTP client to use. When one node becomes unreachable, the client can continue working with other endpoints according to the transport's node selection and retry mechanisms.

A few notes when configuring multiple nodes:

- All endpoints must belong to the cluster the application is permitted to access.
- Nodes must have compatible protocol and security configurations.
- If deployed behind a load balancer or reverse proxy, use the endpoint the application can actually reach.
- Declaring multiple nodes does not replace health checks, cluster monitoring, or application-level retry design.

In a Docker Compose environment, if the application and Elasticsearch run in two separate containers on the same network, the hostname is usually the service name, such as `elasticsearch:9200`. `localhost` inside the application container points to the application container itself, not automatically to the Elasticsearch container.

## 5. Configuring timeouts

Two timeouts typically need attention:

- **Connect timeout**: maximum time allowed to establish a connection to an endpoint.
- **Socket timeout**: time to wait for response data after the connection has been established.

They can be configured using `Duration`:

~~~java
import java.time.Duration;

@Override
public ClientConfiguration clientConfiguration() {
    return ClientConfiguration.builder()
            .connectedTo("localhost:9200")
            .withConnectTimeout(Duration.ofSeconds(5))
            .withSocketTimeout(Duration.ofSeconds(30))
            .build();
}
~~~

The two values have different meanings. If the connect timeout is too short, the application may fail when the network is slow or a node is busy accepting connections. If the socket timeout is too short, a valid but time-consuming query may be aborted before receiving a response.

Do not set overly large timeouts just to mask slow queries or an overloaded Elasticsearch cluster. Choose values based on network characteristics, expected processing time, and the requirements of each business flow.

Client timeouts also do not override timeouts on load balancers, reverse proxies, gateways, or servers. Those layers can have their own limits.

## 6. Connecting over HTTPS and authentication

In deployed environments, Elasticsearch is typically protected by TLS and an authentication mechanism.

### HTTPS with Basic Authentication

You can combine `usingSsl()` and `withBasicAuth`:

~~~java
import java.time.Duration;

@Override
public ClientConfiguration clientConfiguration() {
    return ClientConfiguration.builder()
            .connectedTo("es.example.internal:9200")
            .usingSsl()
            .withBasicAuth(
                    System.getenv("ELASTICSEARCH_USERNAME"),
                    System.getenv("ELASTICSEARCH_PASSWORD")
            )
            .withConnectTimeout(Duration.ofSeconds(5))
            .withSocketTimeout(Duration.ofSeconds(30))
            .build();
}
~~~

In the example, credentials are read from environment variables so username/password are not hardcoded in source code. The variable names are examples; the deployment environment must supply appropriate values.

`usingSsl()` instructs the client to use a TLS connection. Elasticsearch's certificate must be trusted by the JVM, and the hostname must match the certificate. If the system uses an internal CA, configure an appropriate truststore or SSL context in accordance with your environment's security policy.

Do not disable certificate verification as a quick fix for TLS errors in production. Fix the certificate chain, truststore, or hostname properly.

### Sending custom HTTP headers

Some environments use API keys or require custom headers. You can create `HttpHeaders` and pass them via `withHeaders`:

~~~java
import org.springframework.http.HttpHeaders;

@Override
public ClientConfiguration clientConfiguration() {
    HttpHeaders headers = new HttpHeaders();
    headers.add(
            HttpHeaders.AUTHORIZATION,
            "ApiKey " + System.getenv("ELASTICSEARCH_API_KEY")
    );

    return ClientConfiguration.builder()
            .connectedTo("es.example.internal:9200")
            .usingSsl()
            .withHeaders(() -> headers)
            .build();
}
~~~

The header in the example illustrates passing an API key in the format Elasticsearch expects. The API key value must be generated and managed in Elasticsearch; the application should not fabricate an arbitrary string and treat it as a valid credential.

Choose the authentication mechanism required by the cluster. There is no need to send Basic Authentication and an API key simultaneously unless the server requires it.

## 7. Other connection options

In addition to endpoints, TLS, authentication, and timeouts, `ClientConfiguration` supports several options for network infrastructure.

| Option | Purpose |
|---|---|
| `withPathPrefix("elasticsearch")` | Adds a path prefix when Elasticsearch sits behind a reverse proxy with a path prefix |
| `withProxy("proxy-host:8080")` | Connects through an HTTP proxy |
| `withHeaders(...)` | Supplies HTTP headers for requests |
| `withConnectTimeout(...)` | Limits connection establishment time |
| `withSocketTimeout(...)` | Limits waiting time for response data |
| `usingSsl()` | Enables HTTPS/TLS |
| `withBasicAuth(...)` | Configures HTTP Basic Authentication |

Path prefix example:

~~~java
@Override
public ClientConfiguration clientConfiguration() {
    return ClientConfiguration.builder()
            .connectedTo("gateway.example.internal:443")
            .usingSsl()
            .withPathPrefix("search")
            .build();
}
~~~

The path prefix option should only be used when the gateway actually routes Elasticsearch under that path. If the endpoint already points directly to Elasticsearch, adding an incorrect prefix can lead to HTTP 404 errors.

Method names and overloads may change across library versions. When using advanced options, check the API of the exact Spring Data Elasticsearch version managed by your project.

## 8. Using the client and Spring Data operations after configuration

Once the configuration is loaded, services can inject `ElasticsearchOperations` to work with entities:

~~~java
import lombok.RequiredArgsConstructor;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.stereotype.Service;

@Service
@RequiredArgsConstructor
public class ProductSearchService {

    private final ElasticsearchOperations operations;

    public void save(Product product) {
        operations.save(product);
    }

    public Product findById(String id) {
        return operations.get(id, Product.class);
    }

    public void deleteById(String id) {
        operations.delete(id, Product.class);
    }
}
~~~

`ElasticsearchOperations` is Spring Data's high-level abstraction. It coordinates mapping metadata, converters, and the client to convert between Java entities and Elasticsearch documents.

If you need to call APIs directly, you can inject the Java API Client:

~~~java
import co.elastic.clients.elasticsearch.ElasticsearchClient;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;

@Service
@RequiredArgsConstructor
public class NativeElasticsearchService {

    private final ElasticsearchClient elasticsearchClient;

    // Call Elasticsearch Java API Client APIs here.
}
~~~

The two approaches operate at different levels of abstraction:

- Use `ElasticsearchOperations` or repositories when working with the Spring Data and entity model.
- Use `ElasticsearchClient` when you need direct access to the Elasticsearch Java Client API or a feature not conveniently covered by the high-level abstraction.

Do not create a second client inside a service. Use the Spring-managed beans so components share configuration, transport, and lifecycle.

## 9. Comparing Java configuration with Spring Boot auto-configuration

In a Spring Boot application, there are two common ways to organize this:

**Approach 1 — Use Spring Boot auto-configuration**

Spring Boot reads configuration from application properties/YAML and creates Elasticsearch beans based on the available dependencies. This is typically the most concise approach when endpoints and connection options have no special customization requirements.

Example endpoint configuration using Spring Boot properties for the corresponding version:

~~~yaml
spring:
  elasticsearch:
    uris: http://localhost:9200
~~~

Property names, SSL structure, and supported options should be verified against the Spring Boot version in use.

**Approach 2 — Configure manually with `ElasticsearchConfiguration`**

The application creates a configuration class extending `ElasticsearchConfiguration` and returns a `ClientConfiguration`. This approach fits when you need programmatic Java control over endpoints, TLS, authentication, headers, timeouts, or connection behavior.

Once Java configuration is chosen, clearly establish which beans are owned by your custom configuration and which are auto-created by Boot. Avoid declaring multiple competing clients or repository configurations.

Do not configure a client via an `ElasticsearchConfiguration` class while also manually creating another `RestClient`/`ElasticsearchClient` in the same application context without a deliberate reason. Doing so easily leads to bean name collisions, inconsistent dependencies, or services using differently configured connections.

## 10. Which configuration suits which environment?

| Environment | Typical configuration |
|---|---|
| Local development | Single endpoint, usually without TLS if the local cluster is configured that way |
| Docker Compose | Hostname is the service name and Elasticsearch's internal port |
| Integration testing | Endpoint of the Elasticsearch test instance, timeouts tailored for CI |
| Staging/production | Multiple endpoints or load balancer, TLS, credentials from secrets, explicitly tuned timeouts |
| Behind a reverse proxy | Gateway endpoint, TLS, and path prefix if required by the gateway |

Do not copy local configuration verbatim to production. Network addresses, authentication, TLS, access privileges, and timeouts depend on the deployment environment.

## 11. Common connection errors

### Connection refused

Example error:

~~~text
Connection refused: localhost/127.0.0.1:9200
~~~

Common causes:

- Elasticsearch has not started or is not ready yet.
- Wrong port or endpoint.
- Application runs in a container but uses `localhost` instead of the service name.
- Port is not exposed or the network blocks access.

Check Elasticsearch's status and reachability from the exact environment where the application runs.

### Unknown host or DNS resolution failed

The hostname cannot be resolved. Check the service/container name, internal DNS, network, and endpoint configuration.

### HTTP 401 Unauthorized

The server rejected the credentials. Verify the username, password, API key, how headers are passed, and whether the credentials are still valid.

### HTTP 403 Forbidden

The credentials may be valid, but the principal lacks permission to perform the operation. Check roles and privileges on the cluster/index.

### SSLHandshakeException

TLS errors usually relate to:

- The JVM does not trust the CA that signed the server certificate.
- The certificate is expired or missing an intermediate certificate.
- The connection hostname does not match the certificate's Subject Alternative Name.
- The client is using HTTP while the endpoint requires HTTPS, or vice versa.

Fix the trust chain and endpoint to match the actual server configuration.

### Timeout

Distinguish connect timeout from socket timeout. If a connection cannot be established, check DNS, firewall, routing, and node status. If already connected but responses are slow, check the query, cluster load, network, and timeouts of intermediate layers.

### Repository bean not found

Check the repository package, component/repository scanning scope, and whether `@EnableElasticsearchRepositories` matches how the application is structured.

### Library compatibility errors

Spring Data Elasticsearch and the Elasticsearch Java API Client require compatible versions. In Spring Boot applications, prefer the dependency management provided by Spring Boot; avoid independently upgrading a client library to a version incompatible with the Spring Data version in use.

## 12. Checklist when adding configuration to an application

When creating or modifying configuration, verify:

1. You are using the right generation of Spring Data Elasticsearch and the right client type.
2. The endpoint is reachable from where the application runs.
3. The HTTP/HTTPS protocol matches the server configuration.
4. TLS certificates are trusted by the JVM.
5. Credentials or API keys are retrieved from a secure configuration source.
6. Connect timeout and socket timeout fit the workload.
7. Repository scanning covers the right packages.
8. Services use Spring-managed client/operations beans.
9. No duplicate clients or repository configurations are created.
10. Local, test, and production configurations accurately reflect each environment's infrastructure.

## Conclusion

`ClientConfiguration` describes how the application connects to Elasticsearch; `ElasticsearchConfiguration` uses that description to register the client and Spring Data infrastructure. Once properly configured, repositories and `ElasticsearchOperations` can share the Spring-managed connection. Choose configuration settings based on your deployment environment, security requirements, timeouts, and the Spring Data Elasticsearch version in use.
