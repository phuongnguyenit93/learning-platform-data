# Entity resolvers in Spring for GraphQL Federation

## Objectives

After this lesson, you will be able to:

- Explain entity representations and the role of resolvers in a Federation subgraph.
- Understand how the gateway calls the _entities field.
- Configure FederationSchemaFactory in Spring for GraphQL.
- Use @EntityMapping to map representations to Java entities.
- Read keys via @Argument or the full representation map.
- Distinguish single-entity resolvers, batch resolvers, and DataLoader-backed resolvers.
- Preserve entity order when handling multiple representations.
- Combine @EntityMapping with @SchemaMapping and @BatchMapping.
- Handle missing entities, errors, and access control.
- Test entity resolvers at the GraphQL subgraph level.

## 1. What is an entity resolver in Federation?

In Apollo Federation, an entity is a GraphQL type that can be identified by one or more keys. The gateway uses keys to reference the same entity when planning queries across multiple subgraphs.

For example, the Catalog subgraph owns Book data:

~~~graphql
type Book @key(fields: "id") {
    id: ID!
    title: String!
}
~~~

The Reviews subgraph can extend the Book type to provide review fields:

~~~graphql
type Book @key(fields: "id") @extends {
    id: ID! @external
    reviews: [Review!]!
}

type Review {
    id: ID!
    rating: Int!
    comment: String
}
~~~

The Reviews subgraph does not own Book.title, but needs to know which Book is being referenced in order to load its reviews.

An entity resolver receives representations sent by the Federation gateway and turns them into Java objects that remaining field resolvers can use.

In Spring for GraphQL, the method handling this is annotated with @EntityMapping.

## 2. Representations and entity keys

An entity representation is an object describing an entity that needs to be resolved by a subgraph. It contains the __typename field to identify the GraphQL type and the key fields declared via the @key directive.

Example representation of Book:

~~~json
{
  "__typename": "Book",
  "id": "book-42"
}
~~~

__typename indicates the representation belongs to the Book entity; id is the key used to locate or create a reference to the Book.

With a compound key:

~~~graphql
type Product @key(fields: "sku tenantId") {
    sku: ID!
    tenantId: ID!
    name: String!
}
~~~

The representation needs all key fields:

~~~json
{
  "__typename": "Product",
  "sku": "SKU-100",
  "tenantId": "tenant-a"
}
~~~

The entity resolver must understand every key shape advertised by the subgraph. Do not assume every representation always contains only id.

## 3. How does the gateway call _entities?

A Federation schema includes the _entities field so the gateway can ask a subgraph to resolve one or more entity representations.

Example internal operation the gateway might send to the Reviews subgraph:

~~~graphql
query ResolveEntities($representations: [_Any!]!) {
    _entities(representations: $representations) {
        ... on Book {
            id
            reviews {
                id
                rating
                comment
            }
        }
    }
}
~~~

Variables:

~~~json
{
  "representations": [
    {
      "__typename": "Book",
      "id": "book-42"
    }
  ]
}
~~~

The subgraph receives the list of representations, uses __typename to pick the matching entity mapping, and then executes the requested fields on the resolved entities.

Normally, client applications call the gateway rather than calling _entities directly. The gateway uses this field when its query plan needs to fetch additional fields from another subgraph.

## 4. Enabling FederationSchemaFactory

Spring for GraphQL integrates with the federation-jvm library. FederationSchemaFactory builds a GraphQL schema with Federation components and detects controller methods annotated with @EntityMapping.

With Spring Boot, declare the factory and attach it to GraphQlSource:

~~~java
import org.springframework.boot.autoconfigure.graphql.GraphQlSourceBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.data.federation.FederationSchemaFactory;

@Configuration
class FederationConfig {

    @Bean
    FederationSchemaFactory federationSchemaFactory() {
        return new FederationSchemaFactory();
    }

    @Bean
    GraphQlSourceBuilderCustomizer federationSchemaCustomizer(
            FederationSchemaFactory factory) {

        return builder ->
                builder.schemaFactory(factory::createGraphQLSchema);
    }
}
~~~

GraphQlSourceBuilderCustomizer instructs Spring Boot to use FederationSchemaFactory to build the schema. This ensures Federation directives and fields like _entities are configured alongside the subgraph's schema.

Without this step, the SDL may contain @key, yet the runtime schema is not built for Federation. Entity mapping cannot work simply by adding the @EntityMapping annotation.

## 5. Declaring SDL for the subgraph

Example of the Reviews subgraph extending Book:

~~~graphql
type Book @key(fields: "id") @extends {
    id: ID! @external
    reviews: [Review!]!
}

type Review {
    id: ID!
    rating: Int!
    comment: String
}
~~~

Meaning:

- @key(fields: "id") specifies the key used to reference Book.
- @extends indicates the subgraph is extending an entity defined in another subgraph.
- @external marks id as owned by another subgraph.
- reviews is the field provided by the Reviews subgraph.

FederationSchemaFactory processes Federation directives when building the schema. With Federation v2, SDL can use extend schema @link(...) and import directives according to the Federation version chosen by the system. Ensure all subgraphs and the gateway are compatible with the same Federation specification.

## 6. Single-entity resolver with @EntityMapping

For example, the Reviews subgraph only needs to create a Book reference carrying id, then use that reference to load reviews:

~~~java
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.federation.EntityMapping;
import org.springframework.stereotype.Controller;

@Controller
class BookEntityController {

    @EntityMapping
    public Book book(@Argument String id) {
        return new Book(id);
    }
}
~~~

By default, Spring infers the entity name from the method name by capitalizing the first character: the book method maps to entity type Book.

The @Argument String id parameter is bound from the id key field in the representation map. The method returns Book so GraphQL can continue resolving the requested fields.

Example domain object:

~~~java
public record Book(String id) {
}
~~~

In a real subgraph, an entity resolver can also load the full entity from a local database or service. Creating a stub reference is appropriate when the fields owned by the subgraph only need the key to query its own data.

## 7. Specifying the entity name explicitly

When a method name does not follow the entity type naming convention, pass the name explicitly via @EntityMapping:

~~~java
@Controller
class CatalogEntityController {

    @EntityMapping(name = "Book")
    public Book resolveBook(@Argument String id) {
        return bookService.findById(id)
                .orElseThrow(() -> new BookNotFoundException(id));
    }
}
~~~

name specifies the GraphQL entity type the method handles. If omitted, Spring takes the method name and capitalizes its first letter to infer the entity type.

Use an explicit name when methods are named resolveBook, loadProduct, or findCustomer, making it clear that the mapping does not depend on the method name.

## 8. Reading the full representation map

Besides @Argument, an entity mapping method can accept the entire representation as Map<String, Object>:

~~~java
import java.util.Map;

@EntityMapping(name = "Product")
public Product product(Map<String, Object> representation) {
    String sku = (String) representation.get("sku");
    String tenantId = (String) representation.get("tenantId");

    return productService.findBySkuAndTenant(sku, tenantId)
            .orElseThrow(() -> new ProductNotFoundException(sku));
}
~~~

This approach is useful when an entity has a composite key or needs to inspect __typename and multiple properties in the representation.

If you only need a few known key fields, @Argument is usually easier to read and offers explicit type conversion.

Do not treat non-key fields as trusted data. The gateway may send extra fields depending on the query plan, but entity identity must be determined from published keys and verified by the subgraph.

## 9. Supported method arguments

@EntityMapping supports multiple method argument types to read data from the representation and GraphQL execution context:

| Argument | Purpose |
| --- | --- |
| @Argument | Extracts a key or bound value from the representation |
| Map<String, Object> | The entire representation of a single entity |
| List<Map<String, Object>> | List of representations when processing multiple entities in one method |
| @ContextValue | Reads a value from the main GraphQL context |
| @LocalContextValue | Reads a value from the local GraphQL context |
| GraphQLContext | Accesses the GraphQL context |
| Principal | Retrieves the principal from Spring Security context if present |
| @AuthenticationPrincipal | Retrieves the Authentication principal |
| DataFetchingFieldSelectionSet | Inspects the selection set |
| DataLoader<I, E> | Loads entities via DataLoader |
| DataFetchingEnvironment | Direct access to the execution environment |
| Locale | Retrieves the request locale |

Context and security arguments allow the entity resolver to apply tenant, locale, or access permissions for the current user. They do not alter the meaning of keys in the representation.

The method can return the entity directly or supported asynchronous types such as `Mono`, `CompletableFuture`, and `Callable`. Choose a return type matching the subgraph's data access layer; do not block inside a reactive pipeline.

## 10. Handling multiple representations of the same type

The gateway can send multiple representations of the same entity type in a single _entities call. When multiple entities need to be loaded at once, Spring supports a method accepting a list of IDs and returning a List or Flux of entities.

~~~java
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.federation.EntityMapping;

@EntityMapping
public List<Book> book(@Argument List<String> idList) {
    Map<String, Book> booksById = bookService.findAllByIds(idList)
            .stream()
            .collect(Collectors.toMap(Book::id, Function.identity()));

    return idList.stream()
            .map(id -> {
                Book book = booksById.get(id);
                if (book == null) {
                    throw new BookNotFoundException(id);
                }
                return book;
            })
            .toList();
}
~~~

The idList naming convention helps Spring recognize this as a list of values for the id key. You can specify the argument name explicitly with @Argument if needed.

Crucially, the results must preserve the exact order of the input representation list. Do not return an arbitrary database order because the first element in the _entities response must correspond to the first representation.

If the entity has a composite key or varying representations, you can accept List<Map<String, Object>> and process each representation in exact order.

## 11. Preserving order during batch loading

Databases generally do not guarantee a return order matching the input ID list. Therefore, do not write:

~~~java
return bookRepository.findAllById(idList);
~~~

and assume the results already match the representation order.

Build a map by key and reconstruct the list in the input order:

~~~java
Map<String, Book> booksById = loadedBooks.stream()
        .collect(Collectors.toMap(Book::id, Function.identity()));

List<Book> orderedBooks = idList.stream()
        .map(booksById::get)
        .toList();
~~~

If a key is not found, decide on an explicit policy: represent the entity as unresolved, return a null result according to supported semantics, or raise a business error. Never silently drop an element because doing so shifts the positions of subsequent entities.

The behavior of a missing entity can depend on the return type and Spring for GraphQL version. The API provides RepresentationNotResolvedException for cases where a resolver returns null or completes empty; test this contract on your runtime version instead of assuming Mono.empty() always becomes a null element in _entities.

## 12. Using DataLoader in @EntityMapping

When the gateway sends multiple representations, DataLoader can batch entity loads together. Spring for GraphQL allows accepting DataLoader directly in @EntityMapping.

Register a batch loader:

~~~java
import org.springframework.graphql.execution.BatchLoaderRegistry;
import org.springframework.stereotype.Controller;

@Controller
class BookEntityController {

    BookEntityController(
            BatchLoaderRegistry registry,
            BookService bookService) {

        registry.forTypePair(String.class, Book.class)
                .registerBatchLoader((bookIds, environment) ->
                        bookService.findAllByIds(bookIds)
                                .collectMap(Book::id)
                );
    }
}
~~~

Use DataLoader in the entity mapping:

~~~java
import java.util.concurrent.CompletableFuture;

import org.dataloader.DataLoader;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.federation.EntityMapping;

@EntityMapping
public CompletableFuture<Book> book(
        @Argument String id,
        DataLoader<String, Book> dataLoader) {

    return dataLoader.load(id);
}
~~~

DataLoader.load(id) returns a future. Multiple calls can be batched so the batch loader loads entities in groups rather than querying each ID individually.

The batch loader must return results mapped to the exact keys. DataLoader manages dispatching results back to each load call, so the key-value map must be accurate and never mix up IDs.

## 13. Combining @EntityMapping with @SchemaMapping

@EntityMapping only solves creating the entity from a representation. Remaining fields of the entity can still be handled with @SchemaMapping.

Example Book reference created:

~~~java
public record Book(String id) {
}
~~~

Resolver for the reviews field:

~~~java
import java.util.List;

import org.springframework.graphql.data.method.annotation.SchemaMapping;

@SchemaMapping(typeName = "Book", field = "reviews")
public List<Review> reviews(Book book) {
    return reviewService.findByBookId(book.id());
}
~~~

Processing flow:

1. The gateway sends a Book representation with key id.
2. @EntityMapping returns a Book object.
3. GraphQL continues resolving the reviews field.
4. @SchemaMapping uses book.id() to load reviews from local data.

This separation keeps responsibilities clear: the entity resolver builds the reference, and the schema mapping handles fields owned by the subgraph.

## 14. Using @BatchMapping for entity fields

If a query requests reviews for multiple Books, a single @SchemaMapping resolver can cause N+1 queries. Use @BatchMapping to load data in groups:

~~~java
import java.util.List;
import java.util.Map;

import org.springframework.graphql.data.method.annotation.BatchMapping;

@BatchMapping(typeName = "Book", field = "reviews")
public Map<Book, List<Review>> reviews(List<Book> books) {
    return reviewService.findReviewsForBooks(books);
}
~~~

@BatchMapping receives a list of parent Books and returns a map from each Book to its corresponding list of reviews.

Entity resolvers and field batch resolvers operate at two distinct layers:

- @EntityMapping: resolves representations into entities.
- @BatchMapping: loads a field for multiple parent entities at once.

You can combine batch entity resolution and batch field resolution to reduce round trips when the gateway sends multiple representations and requests relational fields.

## 15. Entities with multiple keys or composite keys

An entity can declare multiple keys or a key consisting of multiple fields:

~~~graphql
type Product
    @key(fields: "sku")
    @key(fields: "upc")
{
    sku: ID!
    upc: String!
    name: String!
}
~~~

Or a composite key:

~~~graphql
type TenantProduct @key(fields: "tenantId productId") {
    tenantId: ID!
    productId: ID!
    name: String!
}
~~~

The entity resolver must be able to resolve representations for whichever key the gateway uses. With a composite key, accept the individual fields:

~~~java
@EntityMapping(name = "TenantProduct")
public TenantProduct tenantProduct(
        @Argument String tenantId,
        @Argument String productId) {

    return productService.find(tenantId, productId)
            .orElseThrow(() ->
                    new ProductNotFoundException(productId)
            );
}
~~~

When multiple @key directives exist, test every key shape. Do not assume the gateway always picks the first key in the SDL; the query planner may use whichever key matches data already available from another subgraph.

## 16. Handling non-existent entities and exceptions

An entity resolver may fail to find an entity because data was deleted, the key is invalid, or the subgraph is not permitted to resolve the representation.

Avoid returning an empty object with a dummy ID because the gateway will treat it as a valid entity and subsequent fields may return incorrect data.

You can throw a business exception and map it to a GraphQL error:

~~~java
import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;

import org.springframework.graphql.data.method.annotation.GraphQlExceptionHandler;

@GraphQlExceptionHandler
public GraphQLError handleBookNotFound(BookNotFoundException exception) {
    return GraphqlErrorBuilder.newError()
            .message("Requested Book not found.")
            .build();
}
~~~

@GraphQlExceptionHandler can be placed inside the controller containing @EntityMapping or inside @ControllerAdvice. Spring for GraphQL includes mapped errors in the response of the _entities query.

Do not return stack traces, SQL, table names, or internal details in error messages. Record diagnostics in controlled server logs and return messages conforming to the public contract.

## 17. Securing entity resolvers

Representations are sent by the gateway, yet they are still input data to the subgraph. Do not treat the fact that a request came through the gateway as proof that the user has permission to access every entity.

Important checks:

- Authenticate users using Spring Security mechanisms.
- Verify the entity belongs to the current tenant.
- Check read permissions on the entity before returning references or data.
- Do not trust tenantId, ownerId, or roles simply because they appear in the representation.
- Do not return internal fields merely because the gateway requested them.
- Enforce permissions in the subgraph, especially if the subgraph can be called directly within an internal network.

Example passing principal into an entity resolver:

~~~java
import org.springframework.security.core.annotation.AuthenticationPrincipal;

@EntityMapping
public Book book(
        @Argument String id,
        @AuthenticationPrincipal AppPrincipal principal) {

    return bookService.findVisibleBook(id, principal.tenantId())
            .orElseThrow(() -> new BookNotFoundException(id));
}
~~~

Here the tenant comes from the authenticated principal. The representation only supplies the id key; the service itself verifies whether the entity belongs to that tenant.

If authorization depends on specific fields, continue protecting @SchemaMapping or the services called by field resolvers. An entity being resolved does not imply all of its fields are accessible.

## 18. Testing entity resolvers

You can test _entities directly via a GraphQL tester after configuring the Federation schema and controllers.

Example:

~~~java
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.graphql.test.tester.HttpGraphQlTester;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class BookEntityMappingTests {

    @LocalServerPort
    int port;

    HttpGraphQlTester graphQlTester;

    @BeforeEach
    void setUp() {
        WebTestClient webTestClient = WebTestClient.bindToServer()
                .baseUrl("http://localhost:" + port)
                .build();

        graphQlTester = HttpGraphQlTester.create(webTestClient);
    }

    @Test
    void shouldResolveBookRepresentation() {
        var response = graphQlTester.document("""
                query ResolveBook($representations: [_Any!]!) {
                    _entities(representations: $representations) {
                        ... on Book {
                            id
                            reviews {
                                id
                            }
                        }
                    }
                }
                """)
                .variable("representations", List.of(
                        Map.of(
                                "__typename", "Book",
                                "id", "book-42"
                        ),
                        Map.of(
                                "__typename", "Book",
                                "id", "book-99"
                        )
                ))
                .execute();

        response.path("_entities[0].id")
                .entity(String.class)
                .isEqualTo("book-42");

        response.path("_entities[1].id")
                .entity(String.class)
                .isEqualTo("book-99");
    }
}
~~~

Tests must run with the Federation schema enabled. If the application uses a real HTTP endpoint, you can use HttpGraphQlTester; if you only need to test the web GraphQL handler, use the tester matching your application's handler.

You should also test:

- Representations with valid __typename and key.
- Representations missing a key.
- Entity types with no mapping.
- Composite keys and each alternate key.
- Multiple representations of the same type and result ordering.
- Batch loaders receiving multiple IDs and distributing the right entities.
- Non-existent entities.
- Exceptions converted into GraphQL errors.
- Principals from a different tenant being rejected.
- Field resolvers and batch resolvers loading the right local data.

## 19. Common pitfalls

| Symptom | Cause | Solution |
| --- | --- | --- |
| _entities does not exist | Schema was not created with FederationSchemaFactory | Register the factory and schema customizer |
| Entity mapping not found | Method name does not match entity type or missing name | Use conventional method name or @EntityMapping(name = "...") |
| Key received is null | Representation missing key or wrong @Argument name | Check @key and argument name |
| Resolver cannot read composite key | Method accepts only one key field | Bind all key fields or read the representation map |
| Batch result returns wrong entity | Returned list does not preserve representation order | Rebuild results in the input ID order |
| Batch loader returns wrong entity | Inaccurate key-value map | Use entity key as map key and test each ID |
| DataLoader still issues per-item queries | Loader not registered or key type mismatch | Check forTypePair and DataLoader argument |
| Entity resolver runs but fields have no data | Missing @SchemaMapping or @BatchMapping for extended fields | Add the subgraph's field resolvers |
| Missing entity produces confusing response | Missing-entity/error policy not defined | Map exceptions and test _entities responses |
| User can read another tenant's entity | Trusting gateway or key in representation blindly | Enforce permissions in the subgraph/service |
| Federation directives report SDL errors | Gateway and subgraph disagree on Federation version/directives | Check @link, @extends, @external, and schema factory |

## 20. Workflow for implementing an entity resolver

When adding an entity to a Federation subgraph, follow this sequence:

1. **Identify the entity and key.** Pick a stable, unique @key resolvable by the subgraph.
2. **Declare the SDL.** Use an entity type or extend type with the appropriate Federation directives.
3. **Enable Federation schema.** Register FederationSchemaFactory with GraphQlSource.
4. **Write @EntityMapping.** Bind keys via @Argument or representation map.
5. **Choose the loading strategy.** Use a single resolver, batch resolver, or DataLoader.
6. **Preserve representation order.** Ensure batch results match the input order exactly.
7. **Write field resolvers.** Use @SchemaMapping or @BatchMapping for fields owned by the subgraph.
8. **Secure the data.** Verify principal, tenant, and entity access permissions.
9. **Standardize errors.** Handle missing entities and exceptions per the GraphQL contract.
10. **Test _entities.** Cover keys, batching, ordering, errors, and authorization before integrating with the gateway.

## 21. Summary

@EntityMapping is the entry point for Spring for GraphQL to resolve entity representations sent by the Federation gateway via _entities. Spring binds keys from the representation into method arguments, and the method returns the entity so GraphQL can continue processing remaining fields.

FederationSchemaFactory must be attached to GraphQlSource to generate the Federation schema and detect entity mappings. For multiple representations, you can accept a list of keys and return a List or Flux in exact input order; DataLoader is another option to batch entity loads. Use @SchemaMapping and @BatchMapping for fields owned by the subgraph, while verifying tenant, access permissions, and missing-entity errors. Testing _entities directly confirms the mapping works before connecting the subgraph to the gateway.

## References

- [Spring for GraphQL – Federation](https://docs.spring.io/spring-graphql/reference/federation.html)
- [Spring for GraphQL – EntityMapping API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/data/federation/EntityMapping.html)
- [Apollo Federation – Entities](https://www.apollographql.com/docs/graphos/schema-design/federated-schemas/entities)
- [Apollo Federation – Subgraph Specification](https://www.apollographql.com/docs/federation/subgraph-spec)
