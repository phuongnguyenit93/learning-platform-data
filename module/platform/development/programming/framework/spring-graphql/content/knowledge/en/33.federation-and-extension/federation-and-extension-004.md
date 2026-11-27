# `@EntityMapping` in Spring for GraphQL

`@EntityMapping` is a Spring for GraphQL annotation used to load an entity when a subgraph receives an entity resolution request from a Federation gateway. In Apollo Federation, multiple subgraphs can contribute fields to the same entity. The gateway uses the entity's key fields to pass part of a result from one subgraph to another; the receiving subgraph must turn the representation into a Java object in order to continue resolving the fields it owns.

`@EntityMapping` connects Federation representations with the models and services in a Spring application. It handles finding or creating an entity reference by key; the remaining fields of the entity can still be resolved using `@SchemaMapping`, `@BatchMapping`, or DataLoader.

## Entities and representations in Federation

In a supergraph, each subgraph is an independent GraphQL service. Multiple subgraphs can define the same entity and contribute different fields. The `@key` directive declares the set of fields used to identify an entity instance.

For example, the Products subgraph provides book information:

```graphql
extend schema
  @link(
    url: "https://specs.apollo.dev/federation/v2.3"
    import: ["@key"]
  )

type Query {
  bookById(id: ID!): Book
}

type Book @key(fields: "id") {
  id: ID!
  title: String!
}
```

The Reviews subgraph can contribute the `reviews` field to the same `Book` entity:

```graphql
extend schema
  @link(
    url: "https://specs.apollo.dev/federation/v2.3"
    import: ["@key"]
  )

type Query {
  reviewsForBook(bookId: ID!): [Review!]!
}

type Book @key(fields: "id") {
  id: ID!
  reviews: [Review!]!
}

type Review {
  id: ID!
  body: String!
}
```

In Federation 2, the Reviews subgraph declares `Book` with the same key and the fields it provides. There is no need to use `@extends` or mark the key field with `@external` as in the Federation 1 extension style. Federation 2 uses `@link` to import the required directives.

When the gateway needs to fetch `Book.reviews`, it sends the entity's representation to the Reviews subgraph. A representation is typically a JSON map containing `__typename` and the key fields:

```json
{
  "__typename": "Book",
  "id": "book-10"
}
```

`__typename` indicates which GraphQL type the representation belongs to; `id` is the key identifying the entity. If a key consists of multiple fields, the representation must contain all of those fields. The gateway does not necessarily send the entire object; the subgraph must use the key to load or create a minimal reference.

## How does the gateway call `_entities`?

Apollo Federation defines internal fields for subgraphs, including:

- `Query._entities(representations: [_Any!]!): [_Entity]!` takes a list of entity representations and returns the corresponding entities.
- `Query._service { sdl }` provides the subgraph's SDL for the gateway to read and compose the schema.
- `_Any` is a scalar representing a representation map.
- `_Entity` is a union containing the object types marked with `@key` that can be resolved in the subgraph.

An example internal request equivalent to what the gateway might send:

```graphql
query ResolveEntities($representations: [_Any!]!) {
  _entities(representations: $representations) {
    ... on Book {
      id
      reviews {
        id
        body
      }
    }
  }
}
```

```json
{
  "representations": [
    {
      "__typename": "Book",
      "id": "book-10"
    }
  ]
}
```

Normal client applications call business operations on the supergraph. The gateway automatically constructs `_entities` calls to subgraphs according to the query plan; clients do not need to call `_entities` themselves in the application.

## What does `@EntityMapping` do?

`@EntityMapping` registers a controller method as an entity resolver for a GraphQL type. Spring for GraphQL uses `FederationSchemaFactory` to detect these methods and wire them into the `_entities` DataFetcher.

For example, in the Reviews subgraph, you only need to create a `Book` reference from the `id` key. Then `@SchemaMapping` uses the ID to fetch the list of reviews:

```java
import org.springframework.graphql.data.federation.EntityMapping;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.SchemaMapping;
import org.springframework.stereotype.Controller;
import java.util.List;

@Controller
public class BookEntityController {

    private final ReviewService reviewService;

    public BookEntityController(ReviewService reviewService) {
        this.reviewService = reviewService;
    }

    @EntityMapping(name = "Book")
    public Book book(@Argument("id") String id) {
        return new Book(id);
    }

    @SchemaMapping(typeName = "Book", field = "reviews")
    public List<Review> reviews(Book book) {
        return reviewService.findByBookId(book.id());
    }
}

public record Book(String id) {
}
```

Here, `@EntityMapping` does not need to load the full Book from the database. It simply creates a reference object carrying the `id` key, which is enough for `@SchemaMapping` to query reviews by ID. This is useful when a subgraph contributes a relational field and local data only needs the entity's key.

If business logic needs to confirm the Book exists or requires other attributes to check permissions, load the entity from the service instead of creating a blind reference. Whether the entity resolver creates a reference or loads the full entity depends on the data required by the fields owned by the subgraph.

## Mapped entity name

By default, Spring takes the method name and capitalizes the first letter to infer the GraphQL entity name. For example, a `book(...)` method maps to type `Book`; a `product(...)` method maps to `Product`.

You can specify the name explicitly with `@EntityMapping(name = "Book")`. The `value` attribute is an alias for `name`:

```java
@EntityMapping("Book")
public Book resolveBook(@Argument("id") String id) {
    return new Book(id);
}
```

Use an explicit name when the method name differs from the convention, when multiple entities are resolved in the same controller, or when you want to avoid confusion between Java class names and GraphQL types.

`@EntityMapping` belongs to the `org.springframework.graphql.data.federation` package, a different package from `@SchemaMapping` and `@QueryMapping` in `org.springframework.graphql.data.method.annotation`.

## Enabling Federation for GraphQlSource

For `@EntityMapping` to work, the schema must be built using `FederationSchemaFactory`. This factory integrates with the `federation-jvm` library, generating Federation components such as `_Entity`, `_Any`, `_service`, `_entities`, and the corresponding type resolver.

Add the Federation JVM dependency compatible with the Spring for GraphQL and GraphQL Java versions your project uses:

```kotlin
dependencies {
    implementation("org.springframework.graphql:spring-graphql")
    implementation("com.apollographql.federation:federation-graphql-java-support:$federationJvmVersion")
}
```

In a Spring Boot application, declare `FederationSchemaFactory` and a `GraphQlSourceBuilderCustomizer`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.data.federation.FederationSchemaFactory;
// Spring Boot 4.x:
import org.springframework.boot.graphql.autoconfigure.GraphQlSourceBuilderCustomizer;
// Spring Boot 3.x uses package:
// org.springframework.boot.autoconfigure.graphql.GraphQlSourceBuilderCustomizer;

@Configuration(proxyBeanMethods = false)
public class FederationConfiguration {

    @Bean
    FederationSchemaFactory federationSchemaFactory() {
        return new FederationSchemaFactory();
    }

    @Bean
    GraphQlSourceBuilderCustomizer federationSchemaCustomizer(
            FederationSchemaFactory factory) {
        return builder -> builder.schemaFactory(factory::createGraphQLSchema);
    }
}
```

`$federationJvmVersion` is a version property managed by your project. Choose a `federation-graphql-java-support` release compatible with your Spring for GraphQL/GraphQL Java versions; do not automatically pick the latest version if it upgrades GraphQL Java's major version.

Spring Boot still auto-configures schema resources, annotated controllers, and `RuntimeWiringConfigurer` beans. The customizer only replaces the schema factory so Federation can add subgraph components. If your application builds `GraphQlSource` manually without Boot auto-configuration, pass `factory::createGraphQLSchema` directly to the `GraphQlSource` builder and preserve your existing runtime wiring configurers.

Do not declare a second `GraphQlSource` just to enable Federation if Boot already creates the schema source. Customize the existing builder instead to avoid losing schemas, controller mappings, scalars, or other exception resolvers.

## Method signature of `@EntityMapping`

Entity mapping methods support various parameter types depending on what data the resolver needs:

| Parameter | Purpose |
| --- | --- |
| `@Argument` | Extracts a specific field from the representation and binds it to a Java type. |
| `Map<String, Object>` | Receives the entire representation of a single entity, including `__typename` and key fields. |
| `List<Map<String, Object>>` | Receives the full list of representations when one method processes multiple entities of the same type. |
| `GraphQLContext` | Reads the shared GraphQL execution context. |
| `@ContextValue` / `@LocalContextValue` | Reads a value from the GraphQL context or local context. |
| `Principal` / `@AuthenticationPrincipal` | Reads the authenticated identity if a Spring Security context is available. |
| `DataLoader<I, E>` | Loads the entity via a DataLoader by key. |
| `DataFetchingEnvironment` | Direct access to the execution environment when needed. |
| `DataFetchingFieldSelectionSet` | Inspects the selection set of the entity query. |
| `Locale` | Reads the request locale. |

Example accepting the full representation:

```java
@EntityMapping(name = "Book")
public Book book(Map<String, Object> representation) {
    String id = (String) representation.get("id");
    String tenantId = (String) representation.get("tenantId");
    return new Book(id, tenantId);
}
```

Only read key fields that actually exist in the schema and representation. Do not assume the gateway always sends every field of the entity; representations are constructed from `@key` and any fields the query plan needs to forward across subgraphs.

Methods can return the entity directly or an asynchronous type such as `Mono<T>`, `CompletableFuture<T>`, and `Callable<T>`. Choose a return type appropriate for your data access approach; do not block the event loop when using a reactive transport.

## Single keys and composite keys

For an entity with a single key, you can bind directly to one parameter:

```graphql
type Product @key(fields: "upc") {
  upc: ID!
  name: String!
}
```

```java
@EntityMapping
public Product product(@Argument("upc") String upc) {
    return productService.findByUpc(upc);
}
```

For a key with multiple fields, declare each corresponding argument:

```graphql
type StoreProduct @key(fields: "storeId sku") {
  storeId: ID!
  sku: String!
  price: Float!
}
```

```java
@EntityMapping(name = "StoreProduct")
public StoreProduct storeProduct(
        @Argument("storeId") String storeId,
        @Argument("sku") String sku) {
    return storeProductService.findByStoreAndSku(storeId, sku);
}
```

For nested keys or representations with complex structures, accept `Map<String, Object>` and bind/validate the structure explicitly. Do not assume a composite key is a concatenated string; each field in the field set is a separate part of the representation.

## Resolving multiple entities at once

The gateway often sends a list of representations to `_entities`. If multiple representations belong to the same type, Spring for GraphQL allows an entity mapping method to accept a list of IDs and return a list of corresponding entities:

```java
@EntityMapping
public List<Book> book(@Argument List<String> idList) {
    Map<String, Book> booksById = bookService.findAllByIds(idList);

    return idList.stream()
            .map(booksById::get)
            .toList();
}
```

The `idList` naming convention lets Spring infer the representation field `id` and bind values from each representation into a list. You can specify the argument name explicitly via `@Argument` if you prefer a different parameter name.

**The order of results must match the order of input representations.** Do not directly return the result of `findAllById(...)` if the repository does not guarantee the same ordering as the key list. Build a map by ID and reconstruct the results according to `idList` as shown in the example.

Batch methods can also return `Flux<Book>`. For asynchronous data, you can use this instead of `List<Book>`. If a representation cannot be resolved, define how it is handled clearly and test the corresponding result position; you must not shift the order of the remaining entities.

## Combining `@EntityMapping` with DataLoader

When the gateway sends multiple representations, another approach is to resolve each entity with DataLoader. Calls to `load(id)` are batched within the same GraphQL execution and the batch loader loads them together.

Register a mapped batch loader:

```java
import org.springframework.graphql.execution.BatchLoaderRegistry;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public class BookBatchLoaderConfiguration {

    public BookBatchLoaderConfiguration(
            BatchLoaderRegistry registry, BookService bookService) {
        registry.forTypePair(String.class, Book.class)
                .registerMappedBatchLoader((ids, environment) ->
                        Mono.fromSupplier(() -> bookService.findAllByIds(ids)));
    }
}
```

`findAllByIds` in this example returns a `Map<String, Book>` keyed by ID. The entity mapping receives the DataLoader and returns an asynchronous result:

```java
import java.util.concurrent.CompletableFuture;
import org.dataloader.DataLoader;

@EntityMapping(name = "Book")
public CompletableFuture<Book> book(
        @Argument("id") String id,
        DataLoader<String, Book> dataLoader) {
    return dataLoader.load(id);
}
```

Spring for GraphQL has supported `DataLoader` as a method argument of `@EntityMapping` since version 1.4. With older versions, do not assume this argument resolver exists; use a batch mapping approach supported by that version or upgrade the framework.

Choose between list-based entity mapping and DataLoader based on your needs:

- List-based mapping fits when you want to receive all IDs of the same type in one method and load them in a group yourself.
- DataLoader fits when the resolver needs to return a single asynchronous entity per representation while the loader batches keys within the same execution.
- Both approaches must preserve the proper key/entity relationship and avoid individual queries per ID.

## Combining `@EntityMapping` with `@SchemaMapping` and `@BatchMapping`

`@EntityMapping` only handles obtaining the entity reference from a representation. Subsequent fields contributed by the subgraph are still resolved like standard GraphQL.

For example, the `Book` entity is constructed from `id`, while the list of reviews is batched across multiple Books:

```java
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;
import org.springframework.graphql.data.method.annotation.BatchMapping;
import org.springframework.graphql.data.federation.EntityMapping;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.stereotype.Controller;

@Controller
public class ReviewController {

    private final ReviewService reviewService;

    public ReviewController(ReviewService reviewService) {
        this.reviewService = reviewService;
    }

    @EntityMapping
    public Book book(@Argument("id") String id) {
        return new Book(id);
    }

    @BatchMapping(typeName = "Book", field = "reviews")
    public Map<Book, List<Review>> reviews(List<Book> books) {
        Set<String> bookIds = books.stream()
                .map(Book::id)
                .collect(Collectors.toSet());

        Map<String, List<Review>> reviewsByBookId =
                reviewService.findAllByBookIds(bookIds);

        return books.stream().collect(Collectors.toMap(
                book -> book,
                book -> reviewsByBookId.getOrDefault(book.id(), List.of())));
    }
}
```

Entity mapping creates a reference per representation; `@BatchMapping` loads reviews for multiple Books in a single batch. As a result, the subgraph does not need to call the review repository once per entity.

## Handling missing entities and representation errors

There are specific errors during entity resolution:

| Scenario | Behavior |
| --- | --- |
| Representation missing `__typename`. | Spring raises `RepresentationException`. |
| No `@EntityMapping` matches the typename. | Spring raises `RepresentationException`. |
| Single entity resolver returns `null` or `Mono.empty()`. | Spring raises `RepresentationNotResolvedException`. |
| Service/repository throws a business exception. | The exception can be mapped to a GraphQL error. |

You can use `@GraphQlExceptionHandler` in the same controller or `@ControllerAdvice` to standardize errors from `@EntityMapping`. Errors are included in the response of the `_entities` query:

```java
import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import java.util.Map;
import org.springframework.graphql.data.federation.EntityMapping;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.GraphQlExceptionHandler;
import org.springframework.graphql.execution.ErrorType;
import org.springframework.stereotype.Controller;

@Controller
public class BookEntityController {

    private final BookService bookService;

    public BookEntityController(BookService bookService) {
        this.bookService = bookService;
    }

    @EntityMapping
    public Book book(@Argument("id") String id) {
        return bookService.findById(id)
                .orElseThrow(() -> new BookNotFoundException(id));
    }

    @GraphQlExceptionHandler
    public GraphQLError handleBookNotFound(
            GraphqlErrorBuilder<?> builder, BookNotFoundException ex) {
        return builder
                .errorType(ErrorType.NOT_FOUND)
                .message("Book not found")
                .extensions(Map.of("code", "BOOK_NOT_FOUND"))
                .build();
    }
}
```

In this example, `bookService` is constructor-injected like in standard controllers. Do not include internal IDs, SQL statements, or stack traces in messages returned to the gateway. The gateway needs to receive an error code and enough information to handle or log it; implementation details belong in internal logs.

When representing a non-existent entity, choose a clear policy matching the subgraph contract and the Spring for GraphQL version in use. Do not assume every `null` case automatically turns into a null element in `_entities`; single entity mappings can currently convert null/empty into `RepresentationNotResolvedException`. With batch mappings, preserve order and verify how unresolved items are represented.

## Securing entity resolution

Representations come from the Federation gateway, yet they must still be treated as input outside the service's trust boundary. A key only identifies an entity; it does not prove the caller has permission to read the entity.

Principles to apply:

- Authenticate requests from the gateway using the system's service-to-service mechanism.
- Check access permissions and tenant in the service before returning sensitive data.
- Do not trust `tenantId`, owner, or scopes merely because they appear in a representation; obtain trusted scope from the security context or re-verify using server-side data.
- Restrict accepted key fields and validate formats before querying.
- Keep DataLoader/caches scoped to the GraphQL request to avoid sharing entities across users or tenants.
- Do not expose internal fields solely because the representation contains them.

`@EntityMapping` can accept `Principal` or `@AuthenticationPrincipal`. Even with a principal, you still need to check permissions for the entity ID. When using DataLoader, the batch query must apply the same tenant/security scope as single-item queries.

## Testing `@EntityMapping` with GraphQlTester

You can test `_entities` directly to verify that representations are converted into entities and fields provided by the subgraph are resolved accurately. This is a subgraph-level test; normal business client applications do not need to call `_entities`.

```java
import static org.assertj.core.api.Assertions.assertThat;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.graphql.ExecutionGraphQlService;
import org.springframework.graphql.test.tester.ExecutionGraphQlServiceTester;

@SpringBootTest
class FederationEntityMappingTests {

    @Autowired
    ExecutionGraphQlService executionGraphQlService;

    @Test
    void resolvesBookRepresentation() {
        ExecutionGraphQlServiceTester tester =
                ExecutionGraphQlServiceTester.create(executionGraphQlService);

        tester.document("""
                query ResolveBook($representations: [_Any!]!) {
                  _entities(representations: $representations) {
                    ... on Book {
                      id
                      reviews {
                        id
                        body
                      }
                    }
                  }
                }
                """)
                .variable("representations", List.of(Map.of(
                        "__typename", "Book",
                        "id", "book-10")))
                .execute()
                .path("_entities[0].id")
                .entity(String.class)
                .isEqualTo("book-10");
    }
}
```

This test assumes the subgraph has enabled `FederationSchemaFactory`, the schema has `Book @key(fields: "id")`, and `ExecutionGraphQlService` is configured by Spring Boot. You can add assertions for `reviews[*].id` to test the `@SchemaMapping`/`@BatchMapping` step after the entity reference is created.

Verify `_service.sdl` to confirm the subgraph publishes the correct Federation schema:

```java
ExecutionGraphQlServiceTester tester =
        ExecutionGraphQlServiceTester.create(executionGraphQlService);

tester.document("{ _service { sdl } }")
        .execute()
        .path("_service.sdl")
        .entity(String.class)
        .satisfies(sdl -> assertThat(sdl)
                .contains("@key"));
```

Recommended test cases:

- Representation with valid typename and key.
- Representation missing key or missing `__typename`.
- Typename with no corresponding entity mapping.
- Existing entity and non-existent entity.
- Composite key with all fields bound.
- Multiple representations of the same type returned in the exact order.
- DataLoader called in a batch instead of separate queries per representation.
- Business errors mapped to GraphQL errors with stable codes.
- Access control and tenant isolation enforced during entity lookups.
- `_service.sdl` containing the Federation directives the gateway needs for composition.

## Common pitfalls

| Symptom | Cause | Solution |
| --- | --- | --- |
| `_entities` does not exist | Schema is not using `FederationSchemaFactory`. | Declare the factory bean and schema customizer. |
| `@EntityMapping` is not invoked | Missing `@Controller`, typename mismatch, or entity mapping not detected. | Check component scan, method name, and `@EntityMapping(name=...)`. |
| Representation fails to bind key | `@Argument` name does not match field in `@key`. | Use `@Argument("id")` or accept the full representation map. |
| `RepresentationException` due to typename | Representation missing `__typename` or no handler for the type. | Check representation and entity type mapping. |
| Entity lookup returns wrong record | Composite key omits a field or binds wrong key. | Bind every field in `@key` and check the service lookup. |
| Batch entity returns wrong data | Repository results are not in the same order as representations. | Rebuild the list according to the input ID order. |
| N+1 occurs when resolving entities/child fields | Entity mapping or schema mapping queries each ID separately. | Use list-based mapping, DataLoader, or `@BatchMapping`. |
| New fields missing in supergraph | Subgraph SDL has not declared field/key properly or composition was not re-run. | Check `_service.sdl` and the gateway's composition output. |
| Entity error leaks internal details | Exception message returned verbatim. | Standardize with `@GraphQlExceptionHandler` and keep details in logs. |
| Entity returned even when user lacks permission | Only checks key existence without checking authorization. | Check permissions by principal, tenant, and entity in the service. |

## Takeaways

`@EntityMapping` is the entry point for Spring for GraphQL to resolve a Federation entity from a representation sent by the gateway via `_entities`. A representation contains `__typename` and the fields in `@key`; the method can bind each key with `@Argument`, accept the whole map, or accept a list of representations. The entity name defaults from the method name or is declared explicitly via `name`/`value`.

To enable Federation, configure `FederationSchemaFactory` as the schema factory for `GraphQlSource`. Entity mappings can return the entity directly, an async type, an ordered list, or use DataLoader to batch data loading. Afterward, `@SchemaMapping` and `@BatchMapping` continue resolving the entity's fields. Test `_entities`, `_service`, batch ordering, representation errors, and authorization to ensure the subgraph can be safely used by the gateway.

## References

- [Spring for GraphQL — Federation](https://docs.spring.io/spring-graphql/reference/federation.html)
- [Spring for GraphQL — `@EntityMapping` API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/data/federation/EntityMapping.html)
- [Spring for GraphQL — `FederationSchemaFactory` API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/data/federation/FederationSchemaFactory.html)
- [Apollo Federation — Subgraph Specification](https://www.apollographql.com/docs/graphos/schema-design/federated-schemas/reference/subgraph-spec)
- [Apollo Federation — Directives](https://www.apollographql.com/docs/graphos/schema-design/federated-schemas/reference/directives)
