# Organizing Source Packages and Environment-Specific Configuration

A Spring Data Elasticsearch application usually has several collaborating parts: the Spring Boot startup class, document models, repositories, business services, Elasticsearch connection configuration, index configuration, and per-environment configuration files. Putting everything in a single package or scattering connection details throughout source code makes the application hard to extend, test, and deploy.

Good source organization helps developers locate the exact place to make changes, clarifies boundaries between business logic and search infrastructure, and reduces the risk of mixing up endpoints or credentials across local, development, staging, and production. Environment-specific configuration lets the same build artifact run across multiple environments simply by changing external configuration.

In this lesson, we design package organization for a Spring Boot application using Spring Data Elasticsearch, separate business logic from Elasticsearch integration, and set up shared defaults alongside environment-specific configuration.

## 1. Common Components in an Application

A product search application may consist of the following components:

| Component | Responsibility |
| --- | --- |
| Application | Starts Spring Boot and enables component scanning and auto-configuration |
| Domain | Application business models and rules |
| Document or persistence model | Represents data stored in Elasticsearch |
| Repository | Accesses documents via Spring Data Elasticsearch |
| Application service | Orchestrates business logic and invokes repositories or ElasticsearchOperations |
| Web/API | Receives HTTP requests, validates input, and returns responses |
| Configuration | Declares required beans and integration settings |
| Resources | Holds application.yml, profile configurations, and mapping JSON files |
| Tests | Verifies logic, repositories, and integration behavior with Elasticsearch |

Not every project needs to split all of these into separate modules. A small application can use a single Gradle or Maven module with well-defined packages. As the system grows, these boundaries make it easier to extract modules or services.

## 2. Choosing a Package Organization Strategy

Two common strategies exist: by technical layer and by business feature. Both work with Spring Data Elasticsearch; the choice depends on project scale and how the team works.

### 2.1. Organizing by Technical Layer

With this approach, classes sharing a role are grouped into the same package:

~~~text
com.example.catalog
├── CatalogApplication.java
├── controller
│   └── ProductController.java
├── service
│   └── ProductSearchService.java
├── repository
│   └── ProductRepository.java
├── document
│   └── ProductDocument.java
├── config
│   └── ElasticsearchConfiguration.java
└── dto
    ├── ProductSearchRequest.java
    └── ProductSearchResponse.java
~~~

The advantage is an intuitive structure for small projects—newcomers can find controllers, services, or repositories in familiar places. The disadvantage surfaces as the project gains more features: `service` and `repository` packages grow large, and classes for a single feature become scattered across many folders. Editing one feature often requires opening multiple packages.

### 2.2. Organizing by Business Feature

With this approach, classes serving the same feature are placed together:

~~~text
com.example.catalog
├── CatalogApplication.java
├── product
│   ├── api
│   │   ├── ProductController.java
│   │   ├── ProductSearchRequest.java
│   │   └── ProductSearchResponse.java
│   ├── application
│   │   └── ProductSearchService.java
│   ├── domain
│   │   └── Product.java
│   └── infrastructure
│       └── elasticsearch
│           ├── ProductDocument.java
│           └── ProductRepository.java
├── category
│   ├── api
│   ├── application
│   ├── domain
│   └── infrastructure
└── shared
    └── config
        └── ElasticsearchConfiguration.java
~~~

The advantage is keeping a feature's code cohesive in one area. When adding category or order features, the team can extend the corresponding package without bloating global packages. This fits applications with many business features or those evolving toward a modular monolith.

On the flip side, the team must agree on the meaning of subpackages. If every feature invents its own layout, the project becomes difficult to navigate. Only create `domain`, `application`, `api`, and `infrastructure` packages when they genuinely clarify responsibility boundaries.

### 2.3. Which Approach Should You Choose?

For small applications, organizing by technical layer is sufficient. As the number of features grows, organizing by feature generally reduces coupling across code groups. A practical option is organizing by feature at the top level and using lightweight layers inside each feature.

Whichever approach you choose, keep these principles:

- Place the startup class in the root package so component scanning covers subpackages.
- Elasticsearch repositories and documents belong to the storage/search infrastructure layer.
- Services orchestrate business logic and do not contain connection-creation details or direct environment variable lookups.
- Controllers only handle HTTP communication and forward requests to application services.
- API DTOs should not automatically serve as persistence documents if the two models have different lifecycles or structures.
- Shared configuration lives in an easy-to-find location; environment-specific configuration lives in resources or is supplied by the deployment platform.

## 3. Placing the Startup Class in the Root Package

Spring Boot uses component scanning to discover components such as `@Component`, `@Service`, `@Repository`, `@Controller`, and `@Configuration` classes. By default, `@SpringBootApplication` enables component scanning from the package containing the application class and its subpackages.

Example:

~~~java
package com.example.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogApplication {

    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

Placing `CatalogApplication` in `com.example.catalog` allows Spring to discover classes in `com.example.catalog.product`, `com.example.catalog.category`, and `com.example.catalog.shared`.

If you place the startup class in a subpackage like `com.example.catalog.bootstrap` while repositories reside outside that package branch, Spring may fail to discover them automatically. When a different layout is genuinely required, you can configure `scanBasePackages` on `@SpringBootApplication` or explicitly declare `@EnableElasticsearchRepositories` and `@EntityScan` as needed. However, placing the startup class in the root package is usually simplest and least error-prone.

## 4. Organizing the Spring Data Elasticsearch Integration

A search feature typically includes a document, repository, and service. We use a Product example to illustrate.

### 4.1. Elasticsearch Document

The document represents data indexed in Elasticsearch:

~~~java
package com.example.catalog.product.infrastructure.elasticsearch;

import java.math.BigDecimal;

import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "catalog-products")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Double)
    private BigDecimal price;

    // Constructors, getters, and setters
}
~~~

`@Document` binds the class to an index. `@Id` marks the document ID, and `@Field` describes how Elasticsearch indexes each field. The index name in the example is a stable name or alias used by the application. Index creation and mapping versioning should be defined in your project's deployment process.

In simple applications, the domain model and document can be the same class. In complex systems, separate `Product` in `domain` from `ProductDocument` in `infrastructure` when the storage schema differs from the business model. A service or adapter is then responsible for converting between the two types.

### 4.2. Repository

Place the repository alongside the document in the Elasticsearch infrastructure package:

~~~java
package com.example.catalog.product.infrastructure.elasticsearch;

import java.util.Optional;

import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {

    Optional<ProductDocument> findBySku(String sku);
}
~~~

Spring Data generates the implementation for the repository interface during application startup. The repository provides CRUD operations and query derivation from method names. For complex queries, `@Query` or `ElasticsearchOperations` can be used as needed.

Do not place repositories in controller or domain packages. A repository is a data-access detail; business classes should depend on appropriate abstractions rather than creating `ElasticsearchClient` instances or making direct HTTP calls.

### 4.3. Application Service

The service orchestrates search requests:

~~~java
package com.example.catalog.product.application;

import java.util.Optional;

import org.springframework.stereotype.Service;

import com.example.catalog.product.infrastructure.elasticsearch.ProductDocument;
import com.example.catalog.product.infrastructure.elasticsearch.ProductRepository;

@Service
public class ProductSearchService {

    private final ProductRepository productRepository;

    public ProductSearchService(ProductRepository productRepository) {
        this.productRepository = productRepository;
    }

    public Optional<ProductDocument> findBySku(String sku) {
        return productRepository.findBySku(sku);
    }
}
~~~

The example above keeps the service simple to focus on package placement. If applying a separated domain architecture, the service should return domain types or application results, with an infrastructure adapter converting documents into domain objects. This keeps business logic free from direct dependencies on Spring Data annotations.

For search queries involving dynamic filters, pagination, aggregations, or complex criteria, the service can use `ElasticsearchOperations`. Place specific Elasticsearch operations in the corresponding adapter or infrastructure layer so the service does not accumulate all technical details.

## 5. Distinguishing Shared Configuration and Environment-Specific Configuration

Applications typically run across multiple environments:

| Environment | Purpose | Typical Elasticsearch |
| --- | --- | --- |
| local | Development on a personal machine | Local container or node |
| dev | Integrating in-progress changes | Shared cluster for the team |
| staging | Testing close to production | Cluster with configuration and security similar to production |
| production | Serving real users | Managed cluster with authentication, TLS, and monitoring |
| test | Running automated tests | Dedicated Elasticsearch for tests or Testcontainers |

Values such as timeouts, application name, or general behavior can reside in default configuration. Endpoints, credentials, TLS, and certain resource limits can vary by environment.

A key principle is that the same build artifact should be deployable across environments simply by passing runtime configuration. You should not need to build a separate JAR just because the Elasticsearch URL differs.

## 6. Configuring with `application.yml` and Spring Profiles

Spring Boot supports externalized configuration. You can place default settings in `application.yml` and overrides in `application-{profile}.yml` files.

### 6.1. Shared Configuration

`src/main/resources/application.yml`:

~~~yaml
spring:
  application:
    name: catalog-service
  elasticsearch:
    connection-timeout: 2s
    socket-timeout: 5s

app:
  search:
    products-index: catalog-products
~~~

This file holds shared defaults. The timeout values are illustrative; real values should reflect network latency, query execution time, and system requirements. `products-index` is application-specific configuration grouped under the `app.search` prefix.

### 6.2. Local Configuration

`src/main/resources/application-local.yml`:

~~~yaml
spring:
  elasticsearch:
    uris: http://localhost:9200

app:
  search:
    products-index: catalog-products-local
~~~

When running locally, the application connects to the Elasticsearch node on the developer machine. If the local node has authentication enabled, supply username and password via corresponding environment variables. Never write personal passwords into committed configuration files.

### 6.3. Development Configuration

`src/main/resources/application-dev.yml`:

~~~yaml
spring:
  elasticsearch:
    uris: ${ELASTICSEARCH_URIS}
    username: ${ELASTICSEARCH_USERNAME}
    password: ${ELASTICSEARCH_PASSWORD}

app:
  search:
    products-index: catalog-products-dev
~~~

Endpoints and credentials are supplied when the application runs. In CI or deployment environments, these variables should be injected via a secret store or the platform's secret management mechanism.

### 6.4. Production Configuration

`src/main/resources/application-prod.yml`:

~~~yaml
spring:
  elasticsearch:
    uris: ${ELASTICSEARCH_URIS}
    username: ${ELASTICSEARCH_USERNAME}
    password: ${ELASTICSEARCH_PASSWORD}
    connection-timeout: 2s
    socket-timeout: 10s

app:
  search:
    products-index: catalog-products
~~~

In production, the endpoint must point to the cluster provisioned for the application. Enable TLS and certificate verification according to the cluster's security setup. How trust material or SSL bundles are supplied depends on your Spring Boot version and platform certificate setup; use the exact mechanism supported by your project's version.

Do not place passwords, API keys, private keys, or secret certificate contents in Git. `application-prod.yml` should only contain variable names or references to platform-provided secrets.

### 6.5. Activating a Profile

You can activate a profile using an environment variable:

~~~bash
SPRING_PROFILES_ACTIVE=local
~~~

Or when running the JAR:

~~~bash
java -jar catalog-service.jar --spring.profiles.active=dev
~~~

In containerized environments, `SPRING_PROFILES_ACTIVE` is commonly passed alongside `ELASTICSEARCH_*` variables from deployment configuration. Avoid hardcoding `spring.profiles.active=prod` in `application.yml`, as doing so makes running the same artifact locally or in tests harder to control.

Spring Boot merges defaults, profiles, and external configuration sources according to its precedence rules. Environment variables, command-line arguments, and platform config can override file values. When an unexpected value takes effect, check the active profile and higher-precedence property sources.

## 7. Binding Application Configuration with `@ConfigurationProperties`

Avoid reading environment variables directly in every service. For application-defined settings, use `@ConfigurationProperties` to bind them into a strongly typed object.

Example:

~~~java
package com.example.catalog.shared.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.search")
public class SearchProperties {

    private String productsIndex = "catalog-products";

    public String getProductsIndex() {
        return productsIndex;
    }

    public void setProductsIndex(String productsIndex) {
        this.productsIndex = productsIndex;
    }
}
~~~

Register the properties:

~~~java
package com.example.catalog.shared.config;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableConfigurationProperties(SearchProperties.class)
public class SearchConfiguration {
}
~~~

Then inject `SearchProperties` wherever needed:

~~~java
public class ProductIndexNameProvider {

    private final SearchProperties properties;

    public ProductIndexNameProvider(SearchProperties properties) {
        this.properties = properties;
    }

    public String getIndexName() {
        return properties.getProductsIndex();
    }
}
~~~

The example uses a small provider to illustrate reading configuration. In a real application, you can inject `SearchProperties` directly into an index management adapter or any class needing the value. If using records or constructor binding, apply them according to your project's Spring Boot version and Java conventions.

`@ConfigurationProperties` provides several benefits:

- Groups related settings into a clearly named type.
- Supports binding from YAML, properties, environment variables, and other configuration sources.
- Can be combined with validation to catch missing or invalid settings at startup.
- Reduces scattering raw property key strings across source code.
- Makes unit testing configuration and dependent components easier.

For Elasticsearch connection configuration managed by Spring Boot, prefer the standard `spring.elasticsearch.*` properties supported by the starter. Only write manual client configuration when a specific requirement—such as specialized TLS or multiple independent clusters—exceeds what auto-configuration handles.

## 8. Client and Repository Configuration: When Is Java Configuration Needed?

If the application uses `spring-boot-starter-data-elasticsearch` and standard Spring Boot properties, auto-configuration usually creates the client and beans needed by Spring Data. In that case, there is no need to write an `ElasticsearchConfiguration` class just to redeclare default beans.

You can inject Spring Data abstractions into services or adapters:

~~~java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.stereotype.Component;

@Component
public class ProductSearchAdapter {

    private final ElasticsearchOperations operations;

    public ProductSearchAdapter(ElasticsearchOperations operations) {
        this.operations = operations;
    }
}
~~~

`ElasticsearchOperations` provides a high-level API for saving, reading, and searching documents. Using this abstraction reduces coupling between application code and HTTP client details.

### 8.1. When Is `@EnableElasticsearchRepositories` Needed?

Spring Boot normally discovers repositories within component scan scope. You can use `@EnableElasticsearchRepositories` when you need to specify repository packages explicitly, such as when repositories lie outside the root package:

~~~java
package com.example.catalog.shared.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.elasticsearch.repository.config.EnableElasticsearchRepositories;

@Configuration
@EnableElasticsearchRepositories(
    basePackages = "com.example.catalog.product.infrastructure.elasticsearch"
)
public class ElasticsearchRepositoryConfiguration {
}
~~~

Only add this configuration when you need to customize scan scope or repository settings. Avoid declaring multiple configurations scanning the same package without a clear reason.

### 8.2. When Do You Need to Create the Client Manually?

Some systems must connect to multiple clusters, use special authentication mechanisms, or configure custom TLS. In those cases, you may need to create client beans and configure `ElasticsearchOperations` accordingly. That belongs in infrastructure or `config` packages and must properly manage lifecycle, timeouts, and resource cleanup.

Do not instantiate a new client in every service or on every repository call. Clients are typically managed as shared beans in the application context. Also avoid mixing low-level client APIs with repositories everywhere; isolate low-level queries in dedicated adapters.

Class names, builders, and client configuration APIs change across Elasticsearch Java client and Spring Data Elasticsearch generations. When manual configuration is necessary, use APIs compatible with the dependencies managed by your project's Spring Boot BOM; avoid copying legacy `RestHighLevelClient` examples into new applications.

## 9. Organizing Mapping and Index Resources

Mappings can be declared via annotations on documents or in separate JSON files. When mappings are complex, use many dynamic templates, or require schema reviews independent of Java entities, JSON files can be easier to manage.

One way to organize resources:

~~~text
src/main/resources
├── application.yml
├── application-local.yml
├── application-dev.yml
├── application-prod.yml
└── elasticsearch
    └── mappings
        └── product-mapping.json
~~~

A document can reference a mapping file with `@Mapping` if your Spring Data Elasticsearch version supports that declaration:

~~~java
@Document(indexName = "catalog-products")
@Mapping(mappingPath = "/elasticsearch/mappings/product-mapping.json")
public class ProductDocument {
    // Document fields
}
~~~

Do not define the same schema in two places without establishing a single source of truth. If annotations and JSON mapping both describe a field with conflicting types or analyzers, maintainers will struggle to tell which configuration takes effect. Pick one primary management approach, document the convention, and inspect the actual mapping after index creation.

For systems with strict index lifecycle control, mappings and settings can reside in resources dedicated to separate migration or deployment steps. The runtime application can then simply read/write against provisioned aliases. That way, index-creation permissions do not necessarily have to be granted to every application instance.

## 10. Configuration and Testing by Environment

Do not share a single Elasticsearch cluster across all test types and environments. Local development, integration tests, and production have different goals, datasets, and access controls.

### 10.1. Local Development

A common option is running Elasticsearch with Docker or Docker Compose. The application activates the `local` profile and connects to the endpoint on the developer machine. Local data should be safe to wipe and recreate without affecting shared data.

The `local` profile example above assumes Elasticsearch listens at `localhost:9200`. With Docker Compose, the hostname can be the service name when the application also runs on the same Docker network; `localhost` inside an application container points to the application container itself, not the Elasticsearch container.

### 10.2. Unit Tests

Unit tests for services should mock repositories or adapters to verify business logic without starting Elasticsearch:

~~~java
@ExtendWith(MockitoExtension.class)
class ProductSearchServiceTest {

    @Mock
    private ProductRepository productRepository;

    @InjectMocks
    private ProductSearchService productSearchService;

    @Test
    void returnsProductBySku() {
        // Arrange, Act, and Assert
    }
}
~~~

This snippet illustrates placement and dependency isolation. Specific assertions depend on the service behavior your application requires.

### 10.3. Integration Tests

Integration tests should verify actual interactions between Spring Data Elasticsearch and a compatible Elasticsearch node. You can use Testcontainers to launch a container for the test lifecycle and supply its dynamic endpoint via `@DynamicPropertySource`.

Skeleton configuration example:

~~~java
@Testcontainers
@SpringBootTest
class ProductRepositoryIntegrationTest {

    @Container
    static final ElasticsearchContainer elasticsearch =
        new ElasticsearchContainer("docker.elastic.co/elasticsearch/elasticsearch:<version>");

    @DynamicPropertySource
    static void elasticsearchProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.elasticsearch.uris", elasticsearch::getHttpHostAddress);
    }
}
~~~

Replace `<version>` with an Elasticsearch version supported by your Spring Data Elasticsearch version. Some Elasticsearch versions enable security by default and require password or certificate setup in tests; configure according to the chosen image and version. Do not use the `latest` tag for stable tests because the image can change without source code changes.

Integration tests should verify at minimum:

- The application initializes repositories and connects to the node.
- Mappings are created properly or indices are prepared properly.
- Documents can be saved and queried.
- Queries, sorting, and pagination behave as expected.
- Invalid data or undeclared fields are handled properly.

### 10.4. Staging and Production

Staging should closely match production in Elasticsearch version, authentication, TLS, mappings, and configuration delivery. Production must use platform-managed endpoints and secrets. Parameters such as connection counts, timeouts, and retries should be tuned based on real-world monitoring.

Do not use sensitive production data for local or dev testing without proper data protection and masking procedures. Each environment should maintain separate access permissions and datasets.

## 11. Common Organizational Pitfalls

**Placing the startup class in too deep a package.** Spring cannot scan repositories or services located outside the default package branch. Place the application class in the root package or configure scan scope intentionally.

**Having controllers call `ElasticsearchRepository` directly.** The controller then mixes HTTP handling with data access logic. Move orchestration into an application service or use case.

**Putting every class into the `config` package.** The `config` package should only hold Spring configuration and infrastructure beans. Documents, repositories, and business logic need their own packages.

**Hardcoding URLs and passwords in Java code.** Changing environments then requires editing and rebuilding the application, while risking secret leaks. Use externalized configuration and secret stores.

**Committing passwords into `application-prod.yml`.** Config files may be committed if they only contain variable references or names. Real secrets must be supplied by a secret management system.

**Creating a new client in every service.** This duplicates configuration, wastes connections, and complicates lifecycle management. Use Spring-managed beans or shared adapters.

**Using profiles to alter business logic unnecessarily.** Profiles suit configuration or beans that exist only in specific environments. Differences in endpoints, credentials, and timeouts should normally be expressed via properties.

**Failing to validate configuration at startup.** A wrong endpoint or missing environment variable might only surface on the first request. Validate required properties and check connectivity according to your application's readiness policy.

**Using incompatible client versions.** Manually adding a client dependency mismatched with Spring Data Elasticsearch can cause runtime or configuration errors. Prefer Spring Boot-managed dependencies and check the compatibility matrix.

## 12. A Complete Reference Structure

For a catalog application with product and category search APIs, the structure might look like:

~~~text
catalog-service
├── build.gradle
└── src
    ├── main
    │   ├── java
    │   │   └── com/example/catalog
    │   │       ├── CatalogApplication.java
    │   │       ├── product
    │   │       │   ├── api
    │   │       │   │   ├── ProductController.java
    │   │       │   │   ├── ProductSearchRequest.java
    │   │       │   │   └── ProductSearchResponse.java
    │   │       │   ├── application
    │   │       │   │   └── ProductSearchService.java
    │   │       │   ├── domain
    │   │       │   │   └── Product.java
    │   │       │   └── infrastructure
    │   │       │       └── elasticsearch
    │   │       │           ├── ProductDocument.java
    │   │       │           ├── ProductRepository.java
    │   │       │           └── ProductSearchAdapter.java
    │   │       ├── category
    │   │       │   ├── api
    │   │       │   ├── application
    │   │       │   ├── domain
    │   │       │   └── infrastructure
    │   │       └── shared
    │   │           └── config
    │   │               ├── SearchConfiguration.java
    │   │               └── SearchProperties.java
    │   └── resources
    │       ├── application.yml
    │       ├── application-local.yml
    │       ├── application-dev.yml
    │       ├── application-prod.yml
    │       └── elasticsearch
    │           └── mappings
    │               └── product-mapping.json
    └── test
        ├── java
        │   └── com/example/catalog
        │       ├── product
        │       │   ├── application
        │       │   │   └── ProductSearchServiceTest.java
        │       │   └── infrastructure
        │       │       └── elasticsearch
        │       │           └── ProductRepositoryIntegrationTest.java
        │       └── support
        └── resources
            └── application-test.yml
~~~

This is a reference structure, not a mandatory package list. Do not create empty folders merely to match the diagram. When features are small, merge layers; as features grow, expand following the same conventions.

## 13. Workflow for Integrating Configuration into the Application

When starting a project or standardizing an existing application, you can follow this sequence:

1. Identify business features and pick package organization by layer or by feature.
2. Place the `@SpringBootApplication` class in the root package so component scanning works properly.
3. Place Elasticsearch documents, repositories, and adapters in an appropriate `infrastructure` package.
4. Keep controllers, application services, and domain models separated by responsibility.
5. Put shared configuration in `application.yml`; create `local`, `dev`, `staging`, or `prod` profiles when values truly differ.
6. Externalize endpoints and credentials outside source code; inject secrets via the deployment environment.
7. Use `@ConfigurationProperties` for application-specific settings and validate required values.
8. Only write Java configuration for beans or repository scanning not covered by auto-configuration.
9. Prepare mapping and index configuration using a clearly managed single source of truth.
10. Write unit tests for business logic and integration tests against a compatible Elasticsearch instance.
11. Run the same artifact across environments by supplying different profiles and configuration.
12. Verify startup logs, actual endpoints, connection state, and query behavior after deployment.

A clean package structure clarifies where code belongs and the direction of dependencies. Environment-specific configuration clarifies which values vary at deployment time. When both are organized consistently, Spring Data Elasticsearch integrates as a clean, testable, and maintainable infrastructure component.
