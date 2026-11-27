# The Relationship Between Spring Data, Elasticsearch, and the Elasticsearch Java Client

Spring Data Elasticsearch is an integration layer that helps Spring applications work with Elasticsearch in the familiar style of the Spring Data ecosystem: mapping Java objects to documents, declaring repositories, performing CRUD operations, and building queries. In modern versions, Spring Data Elasticsearch uses the Elasticsearch Java Client as its primary client to send requests to the Elasticsearch cluster.

These three names belong to three different layers:

- **Elasticsearch** is the server-side search and analytics engine. It stores documents in indices, builds inverted indices, and executes operations such as search, aggregations, indexing, and index management.
- **Elasticsearch Java Client** is the official Java library provided by Elastic. It represents Elasticsearch APIs with strongly typed Java request, response, and data types, and sends requests over an HTTP transport.
- **Spring Data Elasticsearch** is a Spring Data integration module. It provides mapping, repositories, and abstractions such as ElasticsearchOperations to make working with Elasticsearch more convenient in Spring applications. In modern release lines, this module uses the Elasticsearch Java Client at the communication layer.

You can visualize the relationship as follows:

    Spring Boot application
            |
            v
    Spring Data Elasticsearch
    - Repository
    - ElasticsearchOperations
    - Mapping and converter
            |
            v
    Elasticsearch Java Client
    - Typed request / response
    - APIs for search, index, update...
            |
            v
    HTTP transport
            |
            v
    Elasticsearch cluster
    - Index
    - Document
    - Search and aggregation

Spring Data Elasticsearch is not the Elasticsearch server, and the Elasticsearch Java Client is not a repository framework. They work together at different layers.

## 1. What is Spring Data in this relationship?

Spring Data is a family of Spring projects that provides relatively consistent abstractions for working with various kinds of data sources. Specific modules target JPA, MongoDB, Redis, Cassandra, Elasticsearch, and other systems.

Spring Data Elasticsearch is the module dedicated to Elasticsearch. It understands Elasticsearch's document model and APIs while integrating with common Spring Data mechanisms. As a result, application code can focus on entities and search logic instead of building every HTTP request manually.

The main responsibilities of Spring Data Elasticsearch include:

1. **Mapping:** converting between Java objects and Elasticsearch JSON documents. Mapping metadata is declared using annotations such as @Document, @Id, and @Field.
2. **Repository:** providing repository interfaces for common operations and supporting query generation from method names or annotations.
3. **Operations:** offering a higher-level API to save, retrieve, delete, search, and perform index operations.
4. **Query integration:** allowing queries to be built using Spring Data abstractions or native queries matching Elasticsearch's API.
5. **Spring integration:** supporting dependency injection, client configuration, data conversion, and integration with the Spring application lifecycle.

For example, a Java class can represent a document in the products index:

    @Document(indexName = "products")
    public class Product {

        @Id
        private String id;

        @Field(type = FieldType.Text, analyzer = "standard")
        private String name;

        @Field(type = FieldType.Keyword)
        private String category;

        // constructors, getters and setters
    }

The annotations above serve as metadata that Spring Data Elasticsearch uses when mapping objects. @Document specifies the index bound to the entity; @Id marks the document identifier field; @Field describes the field type and necessary mapping attributes.

From this entity, the application can declare a repository:

    public interface ProductRepository
            extends ElasticsearchRepository<Product, String> {

        List<Product> findByCategory(String category);
    }

When the application calls productRepository.findByCategory("book"), Spring Data intercepts the repository call, interprets the method according to the Elasticsearch module's query rules, constructs the appropriate operation, and delegates it down to the client layer. Business logic authors do not need to craft HTTP requests manually for standard cases.

A repository is not where data is stored. Data still resides in the Elasticsearch cluster. A repository is an application-side API that lets you invoke data operations in the Spring Data style.

## 2. What does the Elasticsearch Java Client do?

The Elasticsearch Java Client is the official Java library for calling Elasticsearch APIs. The artifact commonly used in modern applications is co.elastic.clients:elasticsearch-java. The client provides request and response types corresponding to server APIs such as search, index, update, delete, create index, and bulk.

A client is configured with connection details and a transport. The transport is responsible for sending HTTP requests, receiving responses, and converting JSON. In typical setups, the transport uses a REST client at the HTTP layer and a JSON-P mapper to serialize or deserialize data.

The relationship between components at this layer:

    ElasticsearchClient
            |
            v
    ElasticsearchTransport
            |
            v
    HTTP client / REST transport
            |
            v
    Elasticsearch server

The Elasticsearch Java Client has the following characteristics:

- Its API is generated from Elasticsearch's API specification and uses concrete Java types for requests, responses, and queries.
- It can call endpoints directly without needing Spring Data.
- It can be used in plain Java applications, Spring applications, or components that do not use repositories.
- It does not provide Spring Data's repository model or understand Spring Data mapping annotations on its own.

For example, calling the search API directly with the Elasticsearch Java Client:

    SearchResponse<ProductDocument> response =
        elasticsearchClient.search(
            request -> request
                .index("products")
                .query(query -> query
                    .match(match -> match
                        .field("name")
                        .query("spring data")
                    )
                ),
            ProductDocument.class
        );

The code above directly reflects the Elasticsearch API: specifying an index, creating a match query, sending the request, and receiving a SearchResponse. The application must decide how to structure requests, handle responses, and map results to domain models.

ProductDocument in the example is the type used to deserialize the Java Client's response. The Java Client uses the mapper configured on its transport; it does not automatically apply Spring Data's MappingElasticsearchConverter or @Field annotations. Therefore, when calling the client directly, you must ensure the Java type and JSON mapping match the actual documents.

## 3. How does Spring Data Elasticsearch connect to the Java Client?

In modern Spring Data Elasticsearch release lines, the Elasticsearch Java Client is the client layer the module uses to communicate with the server. Spring Data builds abstractions and mapping on top; the Java Client handles calling the underlying APIs.

A repository call typically goes through these steps:

1. A service calls a method on ElasticsearchRepository.
2. Spring Data processes the repository method and determines the operation to execute.
3. Spring Data's mapping metadata and converter transform Java data into document form or convert returned results into entities.
4. ElasticsearchOperations/ElasticsearchTemplate coordinates the operation at the Spring Data layer.
5. The client integration layer builds the corresponding request and calls the Elasticsearch Java Client.
6. The Java Client sends the request through its transport to the Elasticsearch server.
7. The server executes the operation and returns a response.
8. The response flows back up through the Spring Data layer to produce the result usable by the service.

Overall flow:

    Service
      |
      v
    ProductRepository
      |
      v
    ElasticsearchOperations / ElasticsearchTemplate
      |
      v
    Spring Data mapping and client integration
      |
      v
    Elasticsearch Java Client
      |
      v
    Elasticsearch cluster

ElasticsearchOperations is an important abstraction when more flexibility than a repository is needed. ElasticsearchTemplate is a common implementation of this abstraction. A service can depend on ElasticsearchOperations to execute queries while Spring Data still handles entity mapping and conversion.

Example using NativeQuery via ElasticsearchOperations:

    NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q
            .match(m -> m
                .field("name")
                .query("spring data")
            )
        )
        .build();

    SearchHits<Product> hits =
        elasticsearchOperations.search(query, Product.class);

NativeQuery lets you describe queries following the Elasticsearch API structure. However, the call still passes through ElasticsearchOperations, so Spring Data continues to participate in mapping results to Product. This is how it differs from calling ElasticsearchClient directly.

Not every Spring Data method corresponds one-to-one with a repository method or a specific Java Client endpoint. Spring Data has its own abstractions and rules; it translates requests at the abstraction level into requests compatible with Elasticsearch's API.

## 4. Three ways to access Elasticsearch in a Spring application

Depending on complexity, an application can operate at one of three levels.

### Repository

Repositories are suitable for CRUD and common queries. They keep services less coupled to Elasticsearch request details.

    public interface ProductRepository
            extends ElasticsearchRepository<Product, String> {

        List<Product> findByCategory(String category);
    }

    @Service
    public class ProductService {

        private final ProductRepository repository;

        public ProductService(ProductRepository repository) {
            this.repository = repository;
        }

        public List<Product> findBooks() {
            return repository.findByCategory("book");
        }
    }

### ElasticsearchOperations

ElasticsearchOperations is suitable when you need more query control than a repository provides while still wanting Spring Data's mapping and abstractions. Types such as Query, NativeQuery, SearchHits, and the APIs on ElasticsearchOperations express queries and results cleanly.

This level is useful when you need complex queries, combined conditions, pagination, sorting, aggregations, or search hit metadata that repository methods cannot conveniently express.

### Direct Elasticsearch Java Client

Inject ElasticsearchClient and call the API directly when you need an endpoint or capability that Spring Data abstractions do not conveniently expose, or when that component intentionally operates at the Elasticsearch API level.

    @Service
    public class ProductIndexService {

        private final ElasticsearchClient client;

        public ProductIndexService(ElasticsearchClient client) {
            this.client = client;
        }

        public SearchResponse<ProductDocument> search(String keyword)
                throws IOException {
            return client.search(
                request -> request
                    .index("products")
                    .query(query -> query
                        .match(match -> match
                            .field("name")
                            .query(keyword)
                        )
                    ),
                ProductDocument.class
            );
        }
    }

When using the client directly, application code must manage API details more explicitly: index names, queries, response types, errors, and mapping data to domain models. Spring Data does not automatically apply its converters, mapping rules, or callbacks to direct client calls.

These three levels can coexist within the same application. For example, repositories handle CRUD, ElasticsearchOperations handles search screen queries, and the direct Java Client handles specialized index administration tasks. Choose the abstraction based on each component's responsibilities and keep data mapping consistent.

## 5. Configuration and dependencies

With Spring Boot, the standard approach is to use the starter:

    dependencies {
        implementation("org.springframework.boot:spring-boot-starter-data-elasticsearch")
    }

The starter brings Spring Data Elasticsearch and the necessary integration dependencies into the application. Spring Boot manages compatible dependency versions according to the Boot version in use. Therefore, applications typically do not need to declare a separate Elasticsearch Java Client version without a specific reason.

Example cluster address configuration in application.yml:

    spring:
      elasticsearch:
        uris: http://localhost:9200

Authentication credentials and TLS must be configured according to the deployment environment; real passwords should never be written into configuration files committed to Git. Sensitive values can be supplied via environment variables or runtime secrets.

When Spring Boot auto-configures Elasticsearch, the corresponding client and Spring Data operations beans can be injected into services or repositories. If special connection settings are needed, the application can provide a custom client configuration using the mechanisms supported by the Spring Boot and Spring Data versions in use.

If not using Spring Boot, the application can declare Spring Data Elasticsearch directly and configure the client and transport itself. In that case, the application must manage dependencies, configuration beans, connections, and compatible versions manually.

## 6. Notes on versions and legacy clients

Not every Spring Data Elasticsearch project uses the same client.

- Starting with Spring Data Elasticsearch 5.0, the module switched to the new Elasticsearch Java Client under the co.elastic.clients package.
- Spring Data Elasticsearch 4.x and earlier typically used the Elasticsearch Rest High Level Client under the org.elasticsearch.client package.
- Rest High Level Client is a previous-generation API. When maintaining legacy projects, consult the documentation for the exact version and keep dependencies aligned with the running Spring Data release line.

Therefore, do not copy configuration examples from one Spring Data release line and apply them verbatim to another. Verify the versions of Spring Boot, Spring Data Elasticsearch, the Elasticsearch Java Client, and the Elasticsearch server before consulting docs or changing dependencies.

When using Spring Boot, prefer the dependency versions managed by Boot's dependency management. When upgrading, check the compatibility matrix between Spring Data Elasticsearch and Elasticsearch rather than bumping only the client version. An application may compile cleanly yet fail at runtime if client, transport, server, or security configurations are incompatible.

## 7. Common misconceptions

### Confusing Spring Data Elasticsearch with Elasticsearch

Spring Data Elasticsearch runs inside the Java application and provides data access abstractions. Elasticsearch is a standalone server that receives requests and stores/indexes documents. Adding Spring Data to a project does not mean an Elasticsearch cluster is already running.

### Thinking the Java Client replaces Spring Data

The Java Client provides APIs to call Elasticsearch. It does not automatically provide repositories, annotation-based Spring Data entity mapping, or Spring abstractions. If an application uses only the Java Client, it must organize those layers itself when needed.

### Thinking Spring Data does not need the Java Client

In modern Spring Data Elasticsearch release lines, the Java Client is the primary communication layer. Repositories and ElasticsearchOperations are APIs the application uses; they still require a client and transport to send requests to the server.

### Using Spring Data annotations and expecting the Java Client to understand them

@Document, @Id, and @Field belong to Spring Data Elasticsearch's mapping model. Direct calls on ElasticsearchClient use the Java Client's mapper. Do not assume the Java Client will read Spring Data annotations or automatically apply MappingElasticsearchConverter.

### Mixing dependencies from multiple client generations

Adding RestHighLevelClient to an application running a newer Spring Data release line can create complex configurations or dependency conflicts. Identify the client supported by the active Spring Data version and only introduce another client when there is a clear architectural requirement.

### Not distinguishing between text and keyword

Field mappings in Elasticsearch directly affect query results. Text fields are typically analyzed into tokens for full-text search; keyword fields preserve values suitable for exact matching, filtering, and aggregations. @Field annotations should reflect how the application queries data, not just the Java type.

## 8. Which layer should you choose for a requirement?

| Requirement | Layer to start with |
|---|---|
| Save, find, update, or delete entities in a standard way | ElasticsearchRepository |
| Multi-condition queries, pagination, aggregations, and entity-bound results | ElasticsearchOperations |
| Need to call a specific endpoint or newer API not conveniently exposed by abstractions | Elasticsearch Java Client |
| Application does not use Spring Data | Direct Elasticsearch Java Client |
| Application requires reactive APIs | ReactiveElasticsearchRepository or ReactiveElasticsearchOperations per the active version's reactive setup |

For reactive applications, use the corresponding reactive APIs of Spring Data Elasticsearch. ElasticsearchClient is a synchronous client; do not call it directly inside a reactive pipeline expecting the call to become non-blocking automatically.

## Conclusion

Elasticsearch is the server-side search engine. The Elasticsearch Java Client is the official Java library for calling its APIs. Spring Data Elasticsearch sits above the client, adding mapping, repositories, and abstractions tailored to Spring applications.

When calling a repository, the application goes through Spring Data first, then to the Java Client and the Elasticsearch server. When calling ElasticsearchClient directly, the application works closer to the Elasticsearch API and takes more responsibility for requests, responses, and mapping. Understanding this boundary helps you pick the right layer for each requirement, configure the right client generation's dependencies, and avoid confusing Spring Data annotations with the Java Client's JSON conversion mechanism.
