# Spring Boot Client Auto-Configuration Mechanism

Spring Boot can automatically create Elasticsearch connection components based on dependencies and configuration in `application.yml` or `application.properties`. Thanks to auto-configuration, an application typically only needs to declare the cluster address, authentication credentials, and necessary timeouts, and then inject `ElasticsearchClient`, `ElasticsearchOperations`, or a repository to work with data.

To understand this mechanism, it is necessary to distinguish three layers:

- **Elasticsearch client** handles HTTP communication with Elasticsearch.
- **Spring Data Elasticsearch** provides Java object-to-document mapping, the operations API, and the repository abstraction.
- **Spring Boot auto-configuration** wires these components together based on the classpath, properties, and existing beans in the ApplicationContext.

General flow:

```text
application.yml / environment variables
                 |
                 v
       ElasticsearchProperties
                 |
                 v
       Low-level REST client
                 |
                 v
        Elasticsearch transport
                 |
                 v
          ElasticsearchClient
                 |
                 v
      Spring Data Elasticsearch
       ├── Mapping context / converter
       ├── ElasticsearchOperations
       └── Repository proxies
                 |
                 v
        Elasticsearch cluster
```

The exact bean names and creation conditions depend on the Spring Boot version, but the responsibilities of the layers remain similar. In Spring Boot 3 and Spring Data Elasticsearch 5 lines, the primary client is the Elasticsearch Java API Client (`co.elastic.clients.elasticsearch.ElasticsearchClient`), built on top of the REST client and transport. This is the modern client API used to call Elasticsearch APIs in an idiomatic Java style.

## 1. How does auto-configuration work?

Spring Boot auto-configuration is a conditional bean configuration mechanism. When the application starts, Boot inspects the classpath, properties, and already-declared beans to decide which configurations apply.

For Spring Data Elasticsearch, the process typically includes the following steps:

1. The application has the appropriate Elasticsearch dependencies on the classpath.
2. Boot reads the properties under the `spring.elasticsearch` group.
3. Boot configures the REST client to connect to one or more HTTP endpoints.
4. The REST client is combined with a transport and JSON mapper to create `ElasticsearchClient`.
5. Spring Data uses the client to configure the converter, mapping context, and `ElasticsearchOperations`.
6. Repository auto-configuration scans packages and creates implementation proxies for matching repository interfaces.

As a result, services can inject the client or operations directly without having to create connections manually in each place.

### Conditions for auto-configuration to apply

Auto-configuration only works when the required dependencies are present and the application does not replace the corresponding configuration with its own custom configuration. Common conditions include:

- The Elasticsearch client and Spring Data Elasticsearch are on the classpath.
- Connection properties are provided, or default values suitable for the running environment are used.
- The ApplicationContext does not already contain a custom bean that causes the corresponding default configuration to back off.
- The package containing the repositories is within the application's scan scope or is explicitly specified.

Boot commonly uses conditions such as `@ConditionalOnClass`, `@ConditionalOnMissingBean`, and property conditions to avoid creating unnecessary configurations or overriding beans intentionally provided by the application. Therefore, when declaring a custom client bean, part of the auto-configuration may back off. You need to verify dependent beans such as transport, operations, and repositories to ensure the entire chain remains fully configured.

## 2. Declaring the dependency

For a Spring Boot application using Spring Data Elasticsearch, usually only the corresponding starter is needed:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-elasticsearch'
}
```

The starter brings compatible Spring Data and Elasticsearch client libraries into the dependency graph. Spring Boot dependency management coordinates the related versions so they work together.

You should not arbitrarily declare a different version of `elasticsearch-java` or the REST client than the one managed by Spring Boot. The client and server must also fall within the compatibility matrix supported by Elasticsearch. Upgrading a client library independently can cause binary/API errors or runtime communication failures.

For projects using Spring Boot dependency management, prefer Boot's starter and BOM. Only override versions when you have clearly identified the reason and compatibility scope, and have tested the connection against the target cluster.

## 3. Configuring the connection via application.yml

Spring Boot's main configuration group is `spring.elasticsearch`. For example:

```yaml
spring:
  elasticsearch:
    uris:
      - http://localhost:9200
    connection-timeout: 2s
    socket-timeout: 30s
```

`uris` is the list of Elasticsearch HTTP endpoints. Multiple addresses can be configured so that the REST client has multiple node endpoints for connecting and distributing requests. The application does not need to determine which node holds a document; Elasticsearch routes the request to the appropriate shard.

Commonly used properties:

| Property | Meaning |
|---|---|
| `spring.elasticsearch.uris` | One or more Elasticsearch HTTP/HTTPS URIs. |
| `spring.elasticsearch.username` | Username when the cluster uses HTTP Basic Authentication. |
| `spring.elasticsearch.password` | Password corresponding to the username. |
| `spring.elasticsearch.connection-timeout` | Time to wait when establishing a connection. |
| `spring.elasticsearch.socket-timeout` | Time to wait for data on the socket while a request is in progress. |
| `spring.elasticsearch.path-prefix` | Path prefix if the endpoint is placed behind a reverse proxy with a path prefix. |
| `spring.elasticsearch.socket-keep-alive` | Configures TCP keep-alive for sockets as supported by the client. |

Property names and customization capabilities should be checked against the project's Spring Boot version. Do not copy configurations from older Boot documentation without verifying the namespace supported by your current version.

### Connecting to an authenticated cluster

Example using HTTPS and Basic Authentication:

```yaml
spring:
  elasticsearch:
    uris:
      - https://es-01.example.com:9200
      - https://es-02.example.com:9200
    username: ${ELASTICSEARCH_USERNAME}
    password: ${ELASTICSEARCH_PASSWORD}
    connection-timeout: 3s
    socket-timeout: 45s
```

The username and password are read from environment variables to avoid putting secrets directly into source code or committed configuration files. In deployment environments, these variables should be supplied via a secret manager or the platform's secret management mechanism.

HTTPS only encrypts traffic properly when the client verifies the server certificate. If the cluster uses an internal CA or custom certificate, configure an appropriate truststore or trust mechanism. Never disable certificate verification as a temporary workaround for TLS errors in production.

The username/password properties above are for Basic Authentication. If the service requires an API key, dynamic token, client certificate, or a custom authentication mechanism, use the extension point or custom client appropriate for your Boot version and Elasticsearch provider; do not assume that putting an API key into the password field is sufficient.

### Configuring via environment variables

Spring Boot supports externalized configuration, allowing settings to be kept outside the application. For example:

```text
SPRING_ELASTICSEARCH_URIS=https://es.example.com:9200
SPRING_ELASTICSEARCH_USERNAME=app-user
SPRING_ELASTICSEARCH_PASSWORD=<secret>
```

These variables map to the corresponding properties according to relaxed binding rules. You can use dedicated profiles such as `application-dev.yml`, `application-test.yml`, and `application-prod.yml` so each environment has different endpoints.

Do not set `localhost` in production configuration if the application runs on a different machine or container from the cluster. `localhost` always points to the application process's own network namespace. For example, when Spring Boot runs in Docker Compose, `localhost:9200` refers to port 9200 inside the application container itself; you typically need to use the Elasticsearch service name on the Compose network.

## 4. Beans commonly configured by Boot

Depending on the version, beans may be created across multiple auto-configuration classes. Functionally, it is important to understand the following components:

### 4.1. REST client

The REST client manages HTTP connections to Elasticsearch. It handles endpoints, requests, responses, timeouts, connection pooling, and related transport settings. This is the lower-level communication layer used by the Java API Client.

Applications normally do not need to create a new REST client per request. A single client managed in the ApplicationContext can be shared across services.

### 4.2. Elasticsearch transport and Java API Client

The transport connects the REST client with the JSON serialization/deserialization mechanism. The Java API Client provides typed Java APIs for operations such as index, get, search, update, delete, and cluster APIs.

You can inject the client directly:

```java
import co.elastic.clients.elasticsearch.ElasticsearchClient;
import org.springframework.stereotype.Service;

@Service
public class ProductSearchService {

    private final ElasticsearchClient elasticsearchClient;

    public ProductSearchService(ElasticsearchClient elasticsearchClient) {
        this.elasticsearchClient = elasticsearchClient;
    }
}
```

`ElasticsearchClient` is suitable when you need to use the Java API Client directly or call an Elasticsearch API not yet exposed by the Spring Data abstraction in the desired way.

### 4.3. ElasticsearchOperations

Spring Data provides `ElasticsearchOperations` to operate at the domain object and mapping metadata level. The Operations API is typically appropriate when the application needs control over queries or index operations while still leveraging Spring Data's converters and mapping.

Injection example:

```java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.stereotype.Service;

@Service
public class ProductIndexService {

    private final ElasticsearchOperations operations;

    public ProductIndexService(ElasticsearchOperations operations) {
        this.operations = operations;
    }
}
```

Spring Data also provides `ElasticsearchTemplate` as an implementation of the operations abstraction. In your application, depend on the `ElasticsearchOperations` interface unless you specifically need to bind to a concrete implementation.

### 4.4. Repository proxy

When repository support is enabled, Spring Data creates implementation proxies for repository interfaces. For example:

```java
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {
}
```

Services can inject the repository and call CRUD methods or query methods supported by Spring Data. The application does not need to write an implementation for this interface in normal cases.

## 5. Repository scanning and enabling/disabling configuration

In a Spring Boot application, repositories are typically scanned from the package of the `@SpringBootApplication` class downwards. For example:

```text
com.example.store
  ├── StoreApplication.java
  ├── product
  │    ├── Product.java
  │    └── ProductRepository.java
  └── search
       └── ProductSearchService.java
```

If repositories reside outside the default scan package scope, you can specify them explicitly with `@EnableElasticsearchRepositories`:

```java
@SpringBootApplication
@EnableElasticsearchRepositories(
    basePackages = "com.example.store.search.repository"
)
public class StoreApplication {
    public static void main(String[] args) {
        SpringApplication.run(StoreApplication.class, args);
    }
}
```

Do not add this annotation if Boot already scans the right package and repository auto-configuration is active. Declaring duplicate scans or multiple unnecessary repository configurations can make the setup harder to understand.

You can disable repository auto-configuration with:

```yaml
spring:
  data:
    elasticsearch:
      repositories:
        enabled: false
```

Disabling repositories does not mean disabling the entire Elasticsearch client. The application can still use `ElasticsearchClient` or `ElasticsearchOperations` if the corresponding beans remain configured.

## 6. When should you replace auto-configuration?

Auto-configuration covers most standard connections. Custom configuration should only be added when there is a specific requirement, for example:

- Using an API key, token, or custom authentication mechanism.
- Requiring a custom truststore/certificate or special SSL context.
- Needing custom HTTP headers, a proxy, connection pool settings, or request callbacks.
- Connecting to multiple Elasticsearch clusters for different purposes within the same application.
- Needing low-level control over the transport, serializer, or client lifecycle.

Spring Boot provides extension points for the REST client builder in the corresponding versions. You can declare a customizer bean to add settings while keeping most of the default auto-configuration. Conceptual example:

```java
@Bean
RestClientBuilderCustomizer elasticsearchClientCustomizer() {
    return builder -> {
        // Add HTTP configuration suitable for the deployment environment.
    };
}
```

The customizer interface and package must be imported according to your exact Spring Boot version. If requirements exceed what a customizer can do, you can declare client/transport beans manually. In that case, check the auto-configuration back-off conditions and take responsibility for closing resources, sharing the client, and configuring related mapping and operations beans.

### Multiple clusters in one application

The `spring.elasticsearch.*` properties mainly serve the default client configuration. If the application connects to two independent clusters—for example, a product search cluster and an audit cluster—you need to configure two separate clients with explicit endpoints, credentials, and bean names.

You can create separate `ElasticsearchClient` beans and then use `@Qualifier` to inject the right client into each service. If you need Spring Data operations or repositories for each cluster, you must also configure the corresponding operations template, mapping context, and repository binding; simply creating two client beans is not enough for two groups of repositories to automatically know which cluster to use.

Avoid using the same bean name or injecting by type when multiple clients exist without specifying `@Qualifier`, as Spring may fail to resolve a unique bean.

## 7. Verifying connections and handling startup errors

When an application starts successfully, that alone does not always prove the cluster can handle every business query. You should verify actual connectivity with an appropriate operation or a health check designed for the system.

Some common errors:

| Symptom | Causes to check |
|---|---|
| `Connection refused` | Elasticsearch is not running, wrong port, wrong address, or the service is not ready to accept connections. |
| DNS/unknown host | Hostname cannot be resolved in the application's network, often due to an incorrect service/container name. |
| Timeout | Slow network, firewall, unresponsive endpoint, timeout too short, or overloaded cluster. |
| HTTP 401 | Missing or invalid authentication credentials. |
| HTTP 403 | Authenticated, but the user/API key lacks permissions for the operation. |
| SSL handshake/certificate error | Broken trust chain, certificate hostname mismatch, or improper TLS configuration. |
| Version/API compatibility error | Incompatible client, Spring Data, and server versions, or the request uses an API unsupported by the server. |
| Repository bean does not exist | Repository is outside the scan scope, missing dependency, or repository auto-configuration is disabled. |

You can enable Spring Boot's condition evaluation report when investigating why an auto-configuration was applied or skipped. Run the application in debug mode to inspect the condition evaluation report, then check the actual beans in the ApplicationContext. Do not assume solely from having the dependency in Gradle that all Elasticsearch beans were definitely created.

In production, monitor both connectivity and cluster state. Health checks should consider timeouts, frequency, and request impact; avoid sending heavy queries or index create/delete operations on every health check.

## 8. Client lifecycle and usage principles

The client is created and managed by Boot as a Spring ApplicationContext bean. When the application stops, Spring manages the lifecycle and closes bean resources according to their configuration. Therefore:

- Inject and reuse the Spring-managed client.
- Do not create a new client for each request or each repository call.
- Do not manually close a client injected from the ApplicationContext after each operation.
- If you create a client manually, clearly define who owns and closes the REST client/transport on application shutdown.
- Do not log passwords, API keys, the `Authorization` header, or sensitive data in requests/responses.

A shared client enables connection pool reuse and avoids creating excessive sockets. Services should focus on queries and business logic; connection details, timeouts, and authentication belong to environment configuration.

## 9. Testing client configuration

You should not make every unit test depend on a real Elasticsearch instance. Testing can be divided by purpose:

- **Unit tests:** mock the repository or operations when testing service logic; tests do not need a cluster connection.
- **Context tests:** verify that required beans are created and injected properly using the application's configuration.
- **Integration tests:** run a compatible Elasticsearch instance in Testcontainers or a dedicated test environment to verify mapping, queries, serialization, and actual behavior.

Spring Boot provides a test slice for Spring Data Elasticsearch in supported versions to focus on testing the repository layer. When using a test slice, you still need to provide a suitable endpoint or test infrastructure; the test annotation does not spin up a production cluster by itself.

For integration tests, verify index/mapping creation, document writes, reads by ID, and search. If a test depends on searching immediately after writing, explicitly handle refresh timing rather than relying on arbitrary timing.

## 10. Key takeaways

- `spring.elasticsearch.*` is the property group for configuring Elasticsearch connections in modern Spring Boot.
- Boot reads properties and the classpath to auto-configure the REST client, transport, and Elasticsearch Java API Client.
- Spring Data uses the client to create `ElasticsearchOperations`, mapping/converters, and repository proxies.
- `ElasticsearchClient` fits direct Java API Client usage; `ElasticsearchOperations` and repositories fit the Spring Data abstraction.
- Repository scanning typically relies on the `@SpringBootApplication` package; only use `@EnableElasticsearchRepositories` when a custom scope is needed.
- Declaring custom beans can cause parts of auto-configuration to back off; verify the entire chain of dependent beans.
- Use externalized configuration for endpoints and credentials; never commit secrets to the repository.
- Reuse the Spring-managed client rather than creating new clients per request.
- Only customize the client when you have clear requirements such as API keys, custom TLS, proxies, or multiple clusters.

Understanding the auto-configuration mechanism helps keep Spring Data Elasticsearch connection settings concise, consistent across environments, and easy to control when extensions are needed. When errors occur, trace the chain from properties, REST client, transport, and Java API Client through to Spring Data operations and repositories to pinpoint the exact configuration layer having an issue.
