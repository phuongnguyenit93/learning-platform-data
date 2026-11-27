# Roles of ElasticsearchClient, Transport, and the HTTP Layer

In a Java application, calling Elasticsearch is not just creating a client object and sending a query. Behind the API that developers use, there is a transport layer that converts requests into transmittable data, an HTTP client that manages connections, and the HTTP protocol for communicating with the Elasticsearch server.

With the modern Elasticsearch Java API Client, three components need to be distinguished:

- **ElasticsearchClient:** the high-level, strongly typed Java API with methods corresponding to Elasticsearch APIs such as search, index, update, delete, and index management.
- **ElasticsearchTransport:** the intermediary layer that executes requests, converts requests/responses between Java models and JSON format, and connects the API client to a specific transport mechanism.
- **HTTP client and HTTP layer:** responsible for sending HTTP requests over the network to Elasticsearch's REST API, receiving HTTP responses, and handling connection concerns such as timeouts, TLS, authentication, and connection pooling.

These components work together. ElasticsearchClient provides the API for application code; the transport bridges that API to a transmission mechanism; the HTTP client performs network communication; and the Elasticsearch server receives and processes the request.

## 1. End-to-end view of a request path

A Spring Boot application may use Elasticsearch through repositories, ElasticsearchOperations, or by calling ElasticsearchClient directly. When a query is sent via the Java API Client, the typical flow looks like this:

    Service
       |
       v
    Spring Data Elasticsearch
    Repository / ElasticsearchOperations
       |
       v
    ElasticsearchClient
    Typed Java API
       |
       v
    ElasticsearchTransport
    Coordination and data conversion
       |
       v
    RestClientTransport
    Adapter to low-level client
       |
       v
    RestClient
    Manages HTTP requests and connections
       |
       v
    HTTP / HTTPS
       |
       v
    Elasticsearch REST API
       |
       v
    Elasticsearch node

The response travels back from the server to the HTTP client, through the transport to be deserialized into a Java response type, then back to ElasticsearchClient, and finally to the service.

The diagram above illustrates the common setup using RestClientTransport. ElasticsearchTransport is an abstraction of the transport layer; an application can use another implementation if the architecture requires it. Do not equate ElasticsearchClient with RestClient: they serve two different API levels.

## 2. ElasticsearchClient: the Java API called by the application

ElasticsearchClient belongs to the Elasticsearch Java API Client, typically used via the `co.elastic.clients.elasticsearch` package. It is the high-level client providing Java methods corresponding to Elasticsearch APIs.

For example, suppose the application wants to search for products whose name relates to the keyword coffee:

    SearchResponse<Product> response = elasticsearchClient.search(
        request -> request
            .index("products")
            .query(query -> query
                .match(match -> match
                    .field("name")
                    .query("coffee")
                )
            ),
        Product.class
    );

The snippet demonstrates the characteristics of ElasticsearchClient:

- Developers call the Java `search` method instead of manually assembling URLs and HTTP bodies.
- Requests are constructed using builders and types from the Java API Client.
- Responses are deserialized into `SearchResponse<Product>`.
- The `Product` class is supplied so the client maps the document part of the response into Java objects.

The client provides APIs across many functional groups:

| API Group | Example Operations |
|---|---|
| Document | index, get, update, delete |
| Search | search, count, explain |
| Bulk | send multiple document operations in a single request |
| Index management | create, get, update mapping, delete index |
| Cluster and other APIs | call endpoints supported by that client version |

ElasticsearchClient is not an Elasticsearch server; it does not store data and does not create a cluster on its own. It is strictly an application-side component used to invoke server APIs.

### High-level client vs. low-level REST client

The Elasticsearch Java API Client is built on top of a transport. In the common REST setup, the transport connects to the low-level RestClient.

The low-level RestClient operates closer to HTTP: it sends requests to endpoints and receives HTTP responses. If you use the low-level client alone, application code must manually manage details like endpoint paths, HTTP methods, JSON bodies, and response parsing.

ElasticsearchClient provides an abstraction aligned with Elasticsearch APIs. For example, developers call `search` and build queries using Java types rather than manually constructing a POST request to the search endpoint.

| Criterion | ElasticsearchClient | Low-level RestClient |
|---|---|---|
| API Level | Strongly typed Elasticsearch API | Low-level HTTP/REST |
| Request | Java builders and request types | HTTP request, path, method, entity/body |
| Response | Elasticsearch API response types | HTTP response |
| JSON | Handled by transport and mapper | Handled manually by application or caller |
| Purpose | Convenient, typed Elasticsearch API calls | Low-level control over HTTP requests |

Do not confuse the low-level RestClient with the Elasticsearch REST API. The REST API is the set of endpoints exposed by the Elasticsearch server; RestClient is the Java library used to send HTTP requests to those endpoints.

## 3. ElasticsearchTransport: the layer bridging the API and network communication

ElasticsearchTransport is the central abstraction between ElasticsearchClient and a specific transmission mechanism. The Java API Client does not need to hard-bind all API logic to a single HTTP library. Instead, the client sends requests through the transport.

The transport handles these core tasks:

1. Receives requests built by ElasticsearchClient.
2. Converts requests into a form the underlying transmission mechanism can send.
3. Uses a JSON mapper to serialize Java data to JSON when needed.
4. Executes requests via the transport implementation.
5. Reads HTTP responses and deserializes JSON into Java response types.
6. Propagates execution or response errors back to the calling API client.

You can think of the transport as the boundary between the typed Java API and how requests are actually transmitted to the server.

### What does the JSON mapper do?

The Elasticsearch Java API Client uses the JSON-P model to represent and process JSON. When an application wants to map documents to a custom Java class, the transport needs a suitable mapper to convert the data.

A commonly used mapper is JacksonJsonpMapper. It integrates Jackson with the client's JSON-P mechanism, enabling mapping between application Java classes and JSON.

For example, given the class:

    public class Product {
        private String id;
        private String name;
        private double price;

        // constructors, getters and setters
    }

When indexing a Product, the mapper converts the object into JSON to send in the request. When a search returns documents, the mapper reads the JSON and constructs the corresponding Product objects.

The mapper does not validate whether a query is correct and does not perform searching itself. It only handles data representation between Java and JSON. Storing, analyzing, indexing, and searching documents are still performed by the Elasticsearch server.

### RestClientTransport

RestClientTransport is an implementation of ElasticsearchTransport for the low-level RestClient. It connects the Java API Client to Elasticsearch's existing REST client.

In this configuration:

- ElasticsearchClient provides high-level Java APIs.
- RestClientTransport translates Java API Client requests into requests that RestClient can execute, and converts responses back.
- RestClient handles HTTP communication.
- JacksonJsonpMapper or a compatible mapper handles JSON conversion.

RestClientTransport is typically initialized with a RestClient and a JSON mapper. This is the common setup in Java applications and in modern Spring Boot / Spring Data Elasticsearch configurations.

## 4. The HTTP layer: where requests actually cross the network

Elasticsearch exposes its REST API over HTTP. The Java client sends requests to server endpoints, usually using JSON for the body format.

A search request at the HTTP level can be represented broadly as:

    POST /products/_search
    Content-Type: application/json

    {
      "query": {
        "match": {
          "name": "coffee"
        }
      }
    }

When using ElasticsearchClient, developers normally do not need to write this HTTP request by hand. The client and transport construct the corresponding request and hand it off to RestClient to execute.

The HTTP layer has responsibilities unrelated to search logic:

- **Destination address:** host, port, and path prefix if used by the deployment.
- **HTTP method and path:** e.g., POST to the search endpoint or PUT to an index/document endpoint.
- **Headers:** Content-Type, Accept, Authorization, and other required headers.
- **TLS/HTTPS:** encrypting network traffic and verifying certificates as configured.
- **Timeouts:** limiting how long to wait for connections or responses.
- **Connection pooling:** reusing connections to avoid opening a new connection for every request.
- **Node selection and retry:** choosing the target node and handling certain error scenarios according to the REST client's policy.

Exact settings depend on the REST client version and deployment configuration. Not all errors can be safely retried: read requests are usually easier to retry than write requests with business side effects when the execution outcome is uncertain. Applications must evaluate idempotency and retry policies for each operation.

### HTTP, HTTPS, and TCP

The communication layers relate as follows:

    ElasticsearchClient
          |
          v
    Transport and HTTP client
          |
          v
    HTTP request / response
          |
          v
    TLS if using HTTPS
          |
          v
    TCP connection
          |
          v
    Network and Elasticsearch node

HTTP defines how the client and server exchange requests and responses. HTTPS adds TLS to encrypt and authenticate the connection. TCP is the transport protocol beneath the HTTP connection in the standard model.

TLS does not replace Elasticsearch user authentication. TLS protects the transport channel and verifies the server according to configuration; authentication credentials such as Basic Authentication or API keys are still sent via Elasticsearch's authentication mechanism in HTTP headers.

## 5. Configuring the components in plain Java

The example below creates a low-level RestClient, wraps it in a RestClientTransport, and then creates an ElasticsearchClient:

    RestClient restClient = RestClient.builder(
        new HttpHost("localhost", 9200, "http")
    ).build();

    ElasticsearchTransport transport = new RestClientTransport(
        restClient,
        new JacksonJsonpMapper()
    );

    ElasticsearchClient elasticsearchClient =
        new ElasticsearchClient(transport);

Key imports in the example:

    import co.elastic.clients.elasticsearch.ElasticsearchClient;
    import co.elastic.clients.json.jackson.JacksonJsonpMapper;
    import co.elastic.clients.transport.ElasticsearchTransport;
    import co.elastic.clients.transport.rest_client.RestClientTransport;
    import org.apache.http.HttpHost;
    import org.elasticsearch.client.RestClient;

After initialization, the application can use `elasticsearchClient` to invoke APIs like search, index, or delete. When the application manages the client lifecycle manually, it must close HTTP client resources on shutdown:

    restClient.close();

RestClient manages connection resources and must be closed according to its lifecycle. In a Spring application, if the client is created and managed by the Spring container, let the container handle bean destruction according to configuration; services should simply inject and use the client rather than closing a shared client after every request.

### Example search call after initialization

    SearchResponse<Product> response = elasticsearchClient.search(
        search -> search
            .index("products")
            .query(query -> query
                .match(match -> match
                    .field("name")
                    .query("coffee")
                )
            ),
        Product.class
    );

    for (Hit<Product> hit : response.hits().hits()) {
        Product product = hit.source();
        // Process product
    }

The search call passes through ElasticsearchClient, transport, RestClient, and HTTP before the Elasticsearch server processes it. When the response returns, the JSON document is mapped into Product using the configured mapper.

## 6. Configuration in Spring Boot and Spring Data Elasticsearch

In a Spring Boot application, the standard approach is to use the starter:

    dependencies {
        implementation("org.springframework.boot:spring-boot-starter-data-elasticsearch")
    }

With Spring Boot auto-configuration, the cluster address can be declared in `application.yml`:

    spring:
      elasticsearch:
        uris: http://localhost:9200

Spring Boot and Spring Data Elasticsearch coordinate to create the beans required for connections and data operations. In modern Spring Data Elasticsearch lines, ElasticsearchClient is used at the communication layer; ElasticsearchOperations/ElasticsearchTemplate provides the abstraction for the application.

Services can inject ElasticsearchClient if they genuinely need to call Java APIs directly:

    @Service
    public class ProductAdminService {

        private final ElasticsearchClient client;

        public ProductAdminService(ElasticsearchClient client) {
            this.client = client;
        }

        public void deleteProduct(String id) throws IOException {
            client.delete(request -> request
                .index("products")
                .id(id)
            );
        }
    }

When CRUD or queries can be expressed via a repository, prefer using the repository. When complex queries are needed while keeping Spring Data entity mapping, ElasticsearchOperations is the appropriate abstraction. Calling ElasticsearchClient directly is useful when you need a specific API or low-level request control via the Java API Client.

If you provide a custom client configuration, ensure Spring Data, ElasticsearchClient, the transport, and the REST client all share the same connection configuration. Avoid accidentally creating two independent client sets with different addresses, credentials, or TLS settings and injecting them inconsistently within the same application.

### Authentication and TLS

Production environments typically require HTTPS and authentication. Configuration items to address:

- URIs use HTTPS and hostnames match the server certificate.
- Trust material or certificates are configured according to the environment's security policy.
- Username/password or API keys are passed via an appropriate authentication mechanism.
- Timeouts, proxies, and path prefixes are set according to the deployment infrastructure.
- Secrets are supplied via a secret store or environment variables, never committed directly to source control.

Do not disable TLS certificate verification just to make a connection work. Configure the CA or truststore properly for Elasticsearch's certificate.

## 7. Error handling at each layer

When a request fails, you need to identify which layer produced the error because remediation differs by layer.

| Layer | Example Error | What to Check |
|---|---|---|
| Client configuration | Wrong host, port, path prefix | Check URIs and environment configuration |
| HTTP connection | Connection refused, timeout, DNS | Check network, firewall, nodes, and timeouts |
| TLS | Untrusted certificate, hostname mismatch | Check certificate, CA, and hostname |
| Authentication | HTTP 401 or 403 | Check credentials, API key, and privileges |
| Elasticsearch API | Index missing, invalid mapping/query | Read server status and error response |
| JSON mapping | Cannot deserialize response into Java class | Check mapper, field types, and JSON data |

For synchronous calls, I/O errors at the communication layer are typically represented by IOException. Elasticsearch API errors may be represented by a client exception containing response details and server error causes. Inspect the specific exceptions of the client version in use rather than lumping all errors into one category.

Do not blindly retry every exception. For instance, a timeout on a write operation leaves the client uncertain whether the server already executed it. Before retrying, evaluate whether the operation is idempotent and whether an identifier or version control mechanism exists to prevent duplicate writes.

## 8. Reusing the client and managing its lifecycle

An application typically creates the client at the application level and reuses it across many requests. Do not create a new RestClient and ElasticsearchClient for every repository call or every incoming HTTP request.

Reasons:

- The HTTP client manages a connection pool and network resources.
- Reusing the client reduces connection setup overhead.
- Timeouts, TLS, and authentication settings are managed centrally.
- Resource lifecycles are easier to control when the client is managed by the Spring container.

In Spring, inject the client bean into services that need it. Do not close the shared client inside a service method after completing a query. Closing resources belongs to the application lifecycle or the bean that owns the client.

At the same time, do not share a client configured for one cluster or security identity with business logic targeting another cluster if that violates security boundaries. When multiple clusters are needed, each connection configuration should have an explicit bean and lifecycle.

## 9. Separating responsibilities across components

| Component | Question It Answers | Primary Responsibility |
|---|---|---|
| Spring Data Elasticsearch | Through what abstraction does a Spring app manipulate data? | Repositories, operations, entity mapping, and Spring integration |
| ElasticsearchClient | How are Elasticsearch APIs called in Java? | Strongly typed request/response APIs |
| ElasticsearchTransport | How are requests/responses converted between the Java API and the transmission method? | Execution coordination and data conversion |
| RestClientTransport | How is the Java API Client connected to the low-level RestClient? | Adapter between transport and REST client |
| RestClient | How are HTTP requests sent and connections managed? | HTTP requests, nodes, connections, and responses |
| HTTP/HTTPS | Over which protocol is data exchanged? | Requests/responses, headers, bodies, and channel security |
| Elasticsearch REST API/server | Where are requests processed? | Executing searches, indexing, updates, and data management |

This separation of responsibilities helps isolate errors quickly. If the query DSL is wrong, inspect the request and mapping. If connectivity fails, inspect the HTTP client, TLS, network, and address. If JSON fails to map to objects, inspect the mapper and document structure.

## 10. Common misconceptions

### Assuming ElasticsearchClient sends HTTP directly without a transport

ElasticsearchClient provides the high-level API. Requests must be executed via ElasticsearchTransport and a transport implementation. In the common REST setup, that implementation is RestClientTransport.

### Confusing ElasticsearchTransport with the HTTP client

Transport is an abstraction at the Java API Client layer responsible for coordination and request/response conversion. RestClient is the HTTP client performing network communication. RestClientTransport is the adapter connecting the two layers.

### Confusing RestClient with ElasticsearchClient

RestClient operates at a lower HTTP/REST level. ElasticsearchClient provides Elasticsearch-domain APIs with typed requests and responses. A RestClient can be used underneath an ElasticsearchClient via RestClientTransport.

### Assuming JacksonJsonpMapper handles index mapping

JacksonJsonpMapper converts data between Java objects and JSON. It does not create index mappings on the Elasticsearch server, nor does it decide analyzers, field types, or how the server searches. Index mapping is a server-side Elasticsearch configuration that can be managed via APIs or Spring Data metadata.

### Creating a new client for every operation

Repeatedly creating clients wastes resources and defeats the benefits of connection pooling. Reuse a shared client across the application lifecycle.

### Closing the client after every service call

If a client is shared across multiple services or requests, closing it after one call will cause subsequent operations to fail. Only the resource-owning component is responsible for closing it at the end of its lifecycle.

### Thinking HTTPS automatically grants access rights

HTTPS encrypts the transport channel and enables server verification. It does not automatically grant access to indices. Elasticsearch still enforces authentication and authorization according to its security configuration.

## Conclusion

ElasticsearchClient is the high-level Java API that applications use to invoke Elasticsearch features. ElasticsearchTransport is the layer connecting that API to a transmission mechanism and handling request/response conversion. In the common REST configuration, RestClientTransport connects to the low-level RestClient; RestClient is responsible for sending HTTP requests and managing connections to the Elasticsearch REST API.

HTTP/HTTPS is the network communication protocol, while the Elasticsearch server is where queries are actually executed and documents are stored. Understanding these boundaries enables developers to choose the right abstraction, configure the client and mapper appropriately, manage resource lifecycles properly, and pinpoint whether an error originates at the API, transport, HTTP, or server layer.
