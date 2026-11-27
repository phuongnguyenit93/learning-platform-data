# DocumentSource

When using the Spring for GraphQL client, applications often send repetitive GraphQL documents: a query to fetch book details, a mutation to update a profile, or a subscription to track order status. Writing documents inline inside every Java call makes code hard to reuse, hard to manage, and hard to check against schema changes.

**DocumentSource** is the abstraction that lets the Spring GraphQL client look up GraphQL document content by an application-assigned name. Combined with the **documentName(...)** method, the client can reference a document by name, while the DocumentSource implementation is responsible for finding the corresponding content from a map, the classpath, or an appropriate storage source.

This lesson covers the role and contract of DocumentSource, how to configure it with GraphQlClient, how to organize documents in resources, how to use documentName with variables, how document name differs from operation name and persisted queries, how to handle missing documents, caching, security, testing, and common issues.

## 1. What problem does DocumentSource solve?

A GraphQL client call can write a document inline:

~~~java
Mono<Book> book = graphQlClient.document("""
        query BookById($id: ID!) {
            book(id: $id) {
                id
                title
            }
        }
        """)
    .variable("id", "book-01")
    .retrieve("book")
    .toEntity(Book.class);
~~~

For short documents, this approach is clear. However, when an application has many queries and mutations, GraphQL content can occupy a large portion of the client code and be duplicated across multiple services.

DocumentSource separates the document content from the execution site:

- Client call sites only reference the document name.
- The document source is responsible for finding the corresponding GraphQL content.
- Documents can be stored as separate resources, making them easy to review and reuse.
- The application can change how documents are stored without modifying every client call.

Example:

~~~java
Mono<Book> book = graphQlClient.documentName("bookById")
        .variable("id", "book-01")
        .retrieve("book")
        .toEntity(Book.class);
~~~

Here bookById is a document lookup name established by application convention. DocumentSource resolves that name into the GraphQL document string for the client to send to the server.

## 2. Where does DocumentSource sit in client architecture?

Basic processing flow:

~~~mermaid
flowchart TD
    A[Application service] --> B[GraphQlClient.documentName]
    B --> C[DocumentSource]
    C --> D[GraphQL document text]
    D --> E[GraphQlClient RequestSpec]
    E --> F[Variables and operation]
    F --> G[HTTP / WebSocket / RSocket transport]
    G --> H[GraphQL server]
    H --> I[Client response]
~~~

DocumentSource operates on the client side, prior to sending the request over the transport. It answers the question: "For this document name, what is the GraphQL content to send?"

Each component has its own role:

- **DocumentSource**: looks up document text by name.
- **documentName(...)**: instructs GraphQlClient to use the document with the matching name.
- **RequestSpec**: attaches variables, headers, or other request options.
- **GraphQlClient transport**: sends the GraphQL request over HTTP, WebSocket, or RSocket.
- **GraphQL server**: parses, validates, and executes the received document.

DocumentSource does not execute queries and does not parse results. It only supplies document content to the client.

## 3. The DocumentSource contract

DocumentSource is a strategy interface in the org.springframework.graphql.client package. It allows the client to request document content by name.

The contract can be pictured via its method:

~~~java
public interface DocumentSource {
    String getDocument(String documentName);
}
~~~

An application can provide its own implementation to fetch documents from:

- A Java Map loaded at startup.
- Resource files on the classpath.
- A document directory packaged with the application.
- An internal registry or repository controlled by the application.

For static documents, the classpath or a map is usually a simple and controllable choice. Avoid calling a database or synchronous network service on every getDocument call if the content can be preloaded and cached.

If a document name is not found, the implementation should fail clearly. Do not return an empty string or a default document, as doing so can cause the client to send the wrong operation and produce hard-to-diagnose errors.

## 4. Configuring DocumentSource with GraphQlClient

The GraphQlClient builder allows configuring the DocumentSource used when a request calls documentName(...).

Example creating a document source from a map:

~~~java
Map<String, String> documents = Map.of(
        "bookById", """
                query BookById($id: ID!) {
                    book(id: $id) {
                        id
                        title
                    }
                }
                """,
        "books", """
                query Books {
                    books {
                        id
                        title
                    }
                }
                """
);

DocumentSource documentSource = documentName -> {
    String document = documents.get(documentName);
    if (document == null) {
        throw new IllegalArgumentException(
                "GraphQL document not found: " + documentName);
    }
    return document;
};

GraphQlClient graphQlClient = HttpGraphQlClient.builder(webClient)
        .documentSource(documentSource)
        .build();
~~~

In this example:

- The Map stores document text by key.
- DocumentSource looks up content from the map.
- documentSource(...) registers the strategy on the builder.
- The client uses the same document source for named requests.

If the application uses WebSocketGraphQlClient or RSocketGraphQlClient, the principle of configuring DocumentSource on the GraphQlClient builder remains similar; the transport only changes how requests are sent and responses are received.

### Where should DocumentSource be placed?

In a Spring application, you can declare GraphQlClient as a bean:

~~~java
@Configuration
public class GraphQlClientConfiguration {

    @Bean
    GraphQlClient graphQlClient(
            WebClient webClient,
            DocumentSource documentSource) {

        return HttpGraphQlClient.builder(webClient)
                .documentSource(documentSource)
                .build();
    }
}
~~~

This example assumes the application has already configured WebClient and provided a DocumentSource bean. Using a centrally configured client keeps transports, interceptors, timeouts, and the document source consistent across services.

There is no need to create a new GraphQlClient for every query. Reuse the client bean and create a separate RequestSpec for each operation.

## 5. Organizing GraphQL documents on the classpath

A common organization pattern is storing documents in src/main/resources:

~~~text
src/
  main/
    resources/
      graphql/
        bookById.graphql
        books.graphql
        createBook.graphql
        updateBook.graphql
~~~

Example bookById.graphql file:

~~~graphql
query BookById($id: ID!) {
  book(id: $id) {
    id
    title
    author {
      name
    }
  }
}
~~~

A custom DocumentSource can read files from the classpath:

~~~java
@Component
public class ClasspathDocumentSource implements DocumentSource {

    private static final Pattern NAME_PATTERN =
            Pattern.compile("[A-Za-z0-9_-]+");

    private final ResourceLoader resourceLoader;

    public ClasspathDocumentSource(ResourceLoader resourceLoader) {
        this.resourceLoader = resourceLoader;
    }

    @Override
    public String getDocument(String documentName) {
        if (!NAME_PATTERN.matcher(documentName).matches()) {
            throw new IllegalArgumentException(
                    "Invalid GraphQL document name");
        }

        Resource resource = resourceLoader.getResource(
                "classpath:graphql/" + documentName + ".graphql");

        try (InputStream input = resource.getInputStream()) {
            return new String(
                    input.readAllBytes(),
                    StandardCharsets.UTF_8);
        }
        catch (IOException exception) {
            throw new IllegalArgumentException(
                    "Unable to read GraphQL document: " + documentName,
                    exception);
        }
    }
}
~~~

The imports needed in the example include java.io.IOException, java.io.InputStream, java.nio.charset.StandardCharsets, java.util.regex.Pattern, org.springframework.core.io.Resource, org.springframework.core.io.ResourceLoader, org.springframework.stereotype.Component, and org.springframework.graphql.client.DocumentSource.

The Pattern restricts the document name to a simple character set. This prevents input names from containing path segments such as ../ when the implementation builds the classpath location.

This example reads the resource on every request. For static documents, you can load the contents once at startup and store them in a map to avoid repeated I/O. If using ClassPathResource directly, you still need to handle missing resources and file read errors.

## 6. Using documentName in requests

After configuring DocumentSource, call documentName(...) instead of document(...).

Example:

~~~java
Mono<Book> result = graphQlClient.documentName("bookById")
        .variable("id", "book-01")
        .retrieve("book")
        .toEntity(Book.class);
~~~

Steps:

1. documentName("bookById") asks the client to look up the document.
2. DocumentSource returns the GraphQL document content.
3. variable("id", "book-01") binds the variable value.
4. retrieve("book") selects the book field in the response.
5. toEntity(Book.class) converts the field result into a Java object.

DocumentSource does not change how variables or response mapping are used. Once the RequestSpec has the document, it supports all GraphQlClient operations just like requests written inline with document text.

### Reusing the same document with different variables

One document can be used for multiple requests:

~~~java
Mono<Book> first = graphQlClient.documentName("bookById")
        .variable("id", "book-01")
        .retrieve("book")
        .toEntity(Book.class);

Mono<Book> second = graphQlClient.documentName("bookById")
        .variable("id", "book-02")
        .retrieve("book")
        .toEntity(Book.class);
~~~

The document text stays the same while variables change per request. Never concatenate user values directly into a GraphQL document. Using variables separates the operation structure from input data and avoids escaping bugs.

## 7. Distinguishing document name and operation name

Two concepts are frequently confused:

- **Document name**: the internal name an application uses to look up a document via DocumentSource.
- **Operation name**: the name declared inside the GraphQL document after the query, mutation, or subscription keyword.

Example of a file looked up by the name bookById:

~~~graphql
query BookById($id: ID!) {
  book(id: $id) {
    id
    title
  }
}
~~~

Here:

| Value | Role |
|---|---|
| bookById | Document name used in documentName("bookById") |
| BookById | Operation name inside the GraphQL document |
| book | Root field selected in the operation |
| id | Operation variable |

The document name can differ from the operation name. DocumentSource does not automatically rename operations inside the document.

A document can contain multiple operations. When sending such a document, the client and GraphQL server must know which operation is selected according to GraphQL request rules. For simplicity and maintainability, each document file used with documentName should usually contain a single clearly named operation.

## 8. How does DocumentSource differ from persisted queries?

DocumentSource is a client-side content lookup mechanism. When a client calls documentName("bookById"), DocumentSource typically returns the full GraphQL string for GraphQlClient to send in the request.

A persisted query is a different mechanism: client and server cooperate to identify a pre-registered or pre-stored operation, usually via a hash or identifier. The server may not need to receive the full query text in every request if a persisted-query protocol is implemented.

| Criterion | DocumentSource | Persisted query |
|---|---|---|
| Primary lookup location | Client application | Server or shared registry system |
| Lookup input | Application-defined document name | Protocol-defined ID/hash |
| Lookup output | GraphQL document text for the client | Registered or recognized query on the server |
| Automatically reduces request payload? | No | Possibly, depending on protocol |
| Automatically creates server-side allowlist? | No | Only if the server enforces an allowlist policy |
| Primary purpose | Organizing and reusing documents in the client | Managing/identifying queries on the server |

DocumentSource does not automatically enable Automatic Persisted Queries, generate hashes, or register queries on the server. If a system needs persisted queries or an operation allowlist, a separate protocol and server-side enforcement must be implemented.

## 9. DocumentSource is not a security operation registry

Having a client only call known document names helps keep client code organized. However, it does not prevent another client from sending arbitrary queries to the GraphQL endpoint.

For example:

- A mobile app may only use documentName values from a bundled list.
- Another tool can still send a raw GraphQL document over HTTP.
- The GraphQL server must still enforce authentication, authorization, validation, and query limits.

If you want to restrict operations, the server must verify persisted query IDs or an allowlist that is properly implemented and configured. Do not treat DocumentSource as a security boundary.

## 10. Handling missing documents

An incorrect document name can happen because of:

- A typo in the key passed to documentName.
- The resource file not being packaged onto the classpath.
- A filename that differs from DocumentSource's convention.
- A resource being renamed or deleted without updating client code.
- DocumentSource not being configured on the GraphQlClient builder.

Detect this error early and provide a message including the document name:

~~~java
String document = documents.get(documentName);
if (document == null) {
    throw new IllegalArgumentException(
            "GraphQL document not found: " + documentName);
}
~~~

Do not return an empty document and let the request proceed. If a document does not exist, that is a client-side configuration or programming bug; it is not a GraphQL execution error from the server.

If the implementation reads classpath resources, distinguish between:

- The resource does not exist.
- The resource exists but cannot be read.
- The resource has empty content.
- The document text has invalid GraphQL syntax.

DocumentSource is only responsible for reading content. GraphQL parsing and validation are still performed by the server when receiving the request, unless the client adds its own verification step.

## 11. Caching and document lifecycle

GraphQL documents are usually static content, so files do not need to be read from disk on every request.

Several strategies:

| Storage approach | When appropriate | Notes |
|---|---|---|
| Immutable Map | Few documents, known at build time | Easy to control and fast |
| Load classpath at startup | Documents reside in resources | Detects missing files at startup |
| Name-keyed cache | Source read has cost and documents can change | Requires an invalidation policy |
| External registry | Multiple clients share a catalog | Must handle availability and versioning |

For classpath resources, documents can be loaded into a map in the constructor or during bean initialization. Afterward, DocumentSource simply looks up the map.

Do not query a database or call a remote registry synchronously on every request if the document can be cached. If documents can change at runtime, clearly define:

- Cache TTL or invalidation.
- Document versioning.
- How to roll back when a new document is incompatible with the server.
- Behavior when the registry is temporarily unavailable.

## 12. Versioning and document organization

Documents typically depend on the server schema. When the server changes fields or arguments, client documents may need to be updated.

Organizational approaches:

~~~text
graphql/
  book/
    bookById.graphql
    books.graphql
    createBook.graphql
  author/
    authorById.graphql
  order/
    orderStatus.graphql
~~~

DocumentSource can use namespaced keys, such as book.bookById, or map keys according to project conventions.

Avoid having multiple documents with the same key, as a request could inadvertently pick up different content depending on load order. Document names should be unique within the scope of the lookup source.

When changing a document:

1. Review GraphQL document changes alongside schema changes.
2. Verify variable types and field selections.
3. Verify Java response mapping.
4. Run contract/integration tests against the corresponding server.
5. Deploy client and server in a compatible order.

## 13. Security when building DocumentSource

DocumentSource may read files or access a registry, so document names must be controlled.

Principles:

- If a backend uses DocumentSource on behalf of external callers, do not allow callers to pass arbitrary document names for the application to read files by path; map names through an allowlist.
- Do not concatenate unvalidated names into filesystem paths or classpath locations.
- Use a document name allowlist if names originate from untrusted input.
- Do not load GraphQL documents from arbitrary user-supplied URLs.
- Do not store tokens or secrets inside GraphQL documents.
- Do not log full documents if they contain sensitive literals.
- Use GraphQL variables for runtime data instead of embedding it directly in documents.

In typical architectures, documentName is a value set by client code. If an application exposes an API allowing users to pick a document name, validate that name against an allowlist.

A GraphQL document may be shared or bundled inside an application, but the document itself is not a credential. Data access permissions must still be enforced on the server.

## 14. Combining DocumentSource with GraphQlClient types

GraphQlClient provides a unified abstraction across transports:

- **HttpGraphQlClient**: sends requests over HTTP.
- **WebSocketGraphQlClient**: sends requests over WebSocket.
- **RSocketGraphQlClient**: sends requests over RSocket.

DocumentSource resolves the document before the transport sends the request. Therefore, the same document source can be used across multiple clients as long as those clients support configuring DocumentSource.

HTTP example:

~~~java
HttpGraphQlClient httpClient =
        HttpGraphQlClient.builder(webClient)
                .documentSource(documentSource)
                .build();
~~~

WebSocket example:

~~~java
WebSocketGraphQlClient websocketClient =
        WebSocketGraphQlClient.builder(webSocketClient)
                .documentSource(documentSource)
                .build();
~~~

Exact builder names and transport-specific configurations depend on the client implementation and Spring for GraphQL version. The common trait is that document text is resolved before the request goes through the transport.

A document can only run on a transport compatible with the operation type and server endpoint. For example, Subscriptions require a streaming-capable transport; DocumentSource does not turn a standard HTTP JSON request into a subscription transport.

## 15. Testing DocumentSource

DocumentSource is a small component and can be unit tested independently.

Example:

~~~java
class MapDocumentSource implements DocumentSource {

    private final Map<String, String> documents;

    MapDocumentSource(Map<String, String> documents) {
        this.documents = Map.copyOf(documents);
    }

    @Override
    public String getDocument(String documentName) {
        String document = documents.get(documentName);
        if (document == null) {
            throw new IllegalArgumentException(
                    "GraphQL document not found: " + documentName);
        }
        return document;
    }
}
~~~

Unit test:

~~~java
class MapDocumentSourceTest {

    private final DocumentSource source = new MapDocumentSource(
            Map.of("bookById", "query BookById { book { id } }"));

    @Test
    void shouldResolveDocumentByName() {
        assertThat(source.getDocument("bookById"))
                .contains("query BookById");
    }

    @Test
    void shouldFailForUnknownDocument() {
        assertThatThrownBy(() -> source.getDocument("missing"))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("missing");
    }
}
~~~

Beyond unit testing the source, test that GraphQlClient actually uses the resolved document:

1. Configure the client with a test DocumentSource.
2. Call documentName("bookById").
3. Attach variables.
4. Verify the transport receives the right GraphQL document text and variables.
5. Verify the response is mapped to the right fields.
6. Verify error handling when the document name does not exist.

You can use a mock HTTP server or transport test double to verify the request body. Testing DocumentSource in isolation only verifies the lookup; it does not verify that the GraphQlClient builder actually wired that source.

## 16. Common issues when using DocumentSource

| Symptom | Possible cause | Resolution |
|---|---|---|
| documentName fails to find document | Key does not exist or wrong convention | Check the key name and map/resource |
| Classpath document cannot be read | File not packaged or wrong path | Check resources and classpath location |
| Client sends empty document | Source returns empty string when lookup fails | Throw a clear error when not found |
| Request runs a different operation than expected | Confused document name with operation name | Check lookup key and operation name inside file |
| Variables do not match | Document changed without updating client code | Synchronize document and request variables |
| Different clients use different content | DocumentSource configured inconsistently | Use a shared bean/configuration |
| Every request reads from file | Source performs I/O on every lookup | Preload or cache documents |
| Path outside directory can be read | Unvalidated name concatenated into resource path | Validate key or use an allowlist map |
| Assumed server enabled persisted queries | Confused client-side lookup with server protocol | Implement persisted-query/allowlist separately |
| Query text leaked in logs | Full request body logged | Log selective metadata without secrets |

## 17. DocumentSource implementation workflow

When organizing GraphQL documents for a client:

1. Identify reused queries, mutations, and subscriptions.
2. Extract document text into resources or a map with stable names.
3. Declare a clear operation name in each GraphQL document.
4. Create a DocumentSource to look up documents by name.
5. Validate input names and handle missing documents explicitly.
6. Configure DocumentSource on the GraphQlClient builder.
7. Use documentName(...) to create requests.
8. Attach variables specific to each call.
9. Reuse the GraphQlClient bean instead of creating a new client per operation.
10. Cache static documents and manage versions as the schema evolves.
11. Do not confuse DocumentSource with persisted queries or a server-side allowlist.
12. Test lookup, missing documents, request bodies, and response mapping.

DocumentSource separates locating GraphQL document content from request-sending code. Applications can use documentName to reference documents by name and supply content from a map, the classpath, or a controlled registry. Document name differs from the operation name inside the GraphQL document; nor does DocumentSource automatically implement persisted queries or server-side allowlists. Organize versioned documents, use variables for runtime data, validate lookup names, cache static documents, and test both lookup and actual requests so the client always sends the intended operation.
