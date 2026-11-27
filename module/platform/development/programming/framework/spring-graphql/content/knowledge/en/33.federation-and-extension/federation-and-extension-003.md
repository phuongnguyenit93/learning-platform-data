# Entity mapping

In Apollo Federation, multiple subgraphs can contribute fields to the same data type. The router needs a way to ask each subgraph: "For this entity, given the known identifying key, return the portion of data that your subgraph owns." That mechanism is based on **entity representations** and **entity resolvers**.

With Spring for GraphQL, entity resolvers are declared using `@EntityMapping`. This annotation maps a controller method to an entity type in the Federation schema. When the router sends an `_entities` request, Spring reads `__typename` and the key fields in each representation, locates the matching method, binds the input data, and invokes the method to load the entity.

`@EntityMapping` and `FederationSchemaFactory` have been available since Spring for GraphQL 1.3.0.

This lesson covers how to enable Federation schema support, declare entity keys, read representations, implement `@EntityMapping` for single entities or batches, integrate `DataLoader`, handle errors, and test the `_entities` flow.

## 1. What is an entity in Apollo Federation?

An entity is an object type that can be uniquely identified by one or more key fields. Entities are declared with the `@key` directive.

For example, the Books subgraph owns book information:

~~~graphql
type Book @key(fields: "id") {
    id: ID!
    title: String!
    isbn: String!
}
~~~

Another subgraph can contribute additional fields to the same `Book` entity, such as review information:

~~~graphql
extend type Book @key(fields: "id") {
    id: ID! @external
    averageRating: Float
    reviewCount: Int
}
~~~

The router can combine fields from multiple subgraphs into a single `Book` type in the supergraph. Each subgraph is responsible for loading the fields it provides.

A subgraph contributing fields to an entity must provide a way to retrieve the entity instance from its key. In Apollo Server, this mechanism is commonly called `__resolveReference`; in Spring for GraphQL, a controller method annotated with `@EntityMapping` fulfills the equivalent role.

`@key(fields: "id")` tells the router which value identifies a specific instance. In this example, `id` must uniquely identify a book within the data managed by the Books subgraph.

Entity is a Federation concept, not a JPA annotation or a requirement that a Java class share the exact same name. The Java object returned from an entity resolver only needs to be mapped appropriately by Spring/GraphQL Java to the GraphQL object type.

## 2. What is an entity representation?

When the router needs to fetch additional fields of an entity from a subgraph, it sends a representation. A representation contains:

- `__typename`: the name of the GraphQL object type to resolve.
- Fields belonging to a valid `@key` of the entity.
- The key values corresponding to the instance to find.

Example representation of a book:

~~~json
{
    "__typename": "Book",
    "id": "book-42"
}
~~~

With a key consisting of multiple fields:

~~~graphql
type InventoryItem @key(fields: "tenantId sku") {
    tenantId: ID!
    sku: String!
    availableQuantity: Int!
}
~~~

The representation will contain both key fields:

~~~json
{
    "__typename": "InventoryItem",
    "tenantId": "tenant-7",
    "sku": "SKU-100"
}
~~~

A representation provides only enough information to identify the entity. It does not necessarily contain all of the entity's data, nor is it a full database record.

Keys must identify entities stably and uniquely. If a non-unique key is used, a subgraph may return the wrong entity and the router will merge fields from different objects into a single GraphQL object.

Key fields should not accept arguments and cannot be fields returning a union or interface. For a composite key, each field must hold enough value for the subgraph to locate a single exact instance.

## 3. How does the router call entity resolvers via _entities?

A Federation subgraph has special schema components:

- `_Any` is a scalar used to accept representations with a flexible shape.
- `_Entity` is a union containing the entity types supported by the subgraph.
- `Query._entities` accepts a list of representations and returns the corresponding entities.
- `Query._service` provides the subgraph's SDL for the router to discover the schema.

An illustrative request:

~~~graphql
query ResolveBook {
    _entities(
        representations: [
            { __typename: "Book", id: "book-42" }
            { __typename: "Book", id: "book-84" }
        ]
    ) {
        ... on Book {
            id
            title
        }
    }
}
~~~

The router sends a list of representations to `_entities`. The subgraph relies on `__typename` to select the entity resolver, then uses key fields to load the data. The results must correspond to the input representations in the exact same order.

In Spring for GraphQL, `FederationSchemaFactory` configures the schema and the DataFetcher/TypeResolver needed for `_entities`. Controller methods annotated with `@EntityMapping` handle loading each entity type.

A list of representations can contain multiple different `__typename` values. Spring routes each representation to its corresponding entity mapping; a method accepting a `List` typically processes a batch for a specific entity type.

You do not need to write a resolver for `Query._entities` yourself when using Spring for GraphQL's integration.

## 4. Enabling Federation support in Spring for GraphQL

Spring for GraphQL integrates with the `federation-jvm` library to create an Apollo Federation-compatible schema. With Spring Boot, declare a `FederationSchemaFactory` bean and connect it to `GraphQlSource` using `GraphQlSourceBuilderCustomizer`.

~~~java
import org.springframework.boot.autoconfigure.graphql.GraphQlSourceBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.data.federation.FederationSchemaFactory;

@Configuration(proxyBeanMethods = false)
public class FederationConfiguration {

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

`FederationSchemaFactory` detects controller methods annotated with `@EntityMapping` and builds the corresponding Federation schema. It must be declared in Spring configuration so it receives the ApplicationContext and locates controllers.

The package of `GraphQlSourceBuilderCustomizer` varies by Spring Boot major version: with Spring Boot 3.x use `org.springframework.boot.autoconfigure.graphql.GraphQlSourceBuilderCustomizer`; with Spring Boot 4.x use `org.springframework.boot.graphql.autoconfigure.GraphQlSourceBuilderCustomizer`. The rest of the configuration stays the same.

If using Apollo Federation 2, the subgraph SDL also needs to declare `@link` with the Federation version and import the directives used. Abbreviated example:

~~~graphql
extend schema
    @link(
        url: "https://specs.apollo.dev/federation/v2.0"
        import: ["@key", "@external"]
    )

type Book @key(fields: "id") {
    id: ID!
    title: String!
}
~~~

When a subgraph only extends an entity owned by another subgraph, the key field must be declared external according to the Federation schema in use. Keep the Federation version and directive imports synchronized across subgraphs before composing the supergraph.

## 5. Writing your first entity resolver with @EntityMapping

Suppose the schema has a `Book` entity with key `id`:

~~~graphql
type Book @key(fields: "id") {
    id: ID!
    title: String!
    isbn: String!
}
~~~

A controller can declare a method:

~~~java
import org.springframework.graphql.data.federation.EntityMapping;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.stereotype.Controller;

@Controller
public class BookEntityController {

    private final BookService bookService;

    public BookEntityController(BookService bookService) {
        this.bookService = bookService;
    }

    @EntityMapping
    public Book book(@Argument String id) {
        return bookService.findById(id)
                .orElseThrow(() -> new BookNotFoundException(id));
    }
}
~~~

Spring receives the `Book` entity representation, extracts the `id` key value, and binds it to the `@Argument` parameter. The method returns a `Book` object so GraphQL can continue resolving the selected fields.

In this example, the method name is `book`. By default, Spring capitalizes the first letter to infer the entity name `Book`. Therefore, the method is mapped to the GraphQL type `Book`.

`@EntityMapping` only handles restoring the entity from the representation. Other fields of the entity can still use `@SchemaMapping`, `@BatchMapping`, or standard property access.

## 6. Explicitly specifying the entity name with @EntityMapping

When the method name does not match the GraphQL type name, specify the entity name explicitly:

~~~java
@EntityMapping(name = "Book")
public Book loadBook(@Argument String id) {
    return bookService.findById(id)
            .orElseThrow(() -> new BookNotFoundException(id));
}
~~~

`value` is an alias for the `name` attribute, so `@EntityMapping("Book")` can also be used to specify the name.

If omitted, Spring uses the method name with the first character capitalized. For example:

| Method | Default entity type |
| --- | --- |
| `book(...)` | `Book` |
| `product(...)` | `Product` |
| `inventoryItem(...)` | `InventoryItem` |

The entity name must match the object type in the SDL exactly. If a representation has `__typename` equal to `Book` but no matching method exists, Spring cannot route the representation to a controller handler.

## 7. Binding key fields with @Argument or the entire representation with Map

For simple keys, `@Argument` lets you retrieve the key value directly:

~~~java
@EntityMapping
public Book book(@Argument String id) {
    return bookService.findById(id)
            .orElseThrow(() -> new BookNotFoundException(id));
}
~~~

When an entity uses a composite key or needs to inspect additional metadata, you can accept the full representation:

~~~java
@EntityMapping
public InventoryItem inventoryItem(Map<String, Object> representation) {
    String tenantId = (String) representation.get("tenantId");
    String sku = (String) representation.get("sku");

    return inventoryService.findByTenantAndSku(tenantId, sku)
            .orElseThrow(() ->
                    new InventoryItemNotFoundException(tenantId, sku));
}
~~~

The representation map also contains `__typename`. If you need to check the type or support multiple key formats, you can read that value inside the method.

Spring also supports parameters such as `GraphQLContext`, `@ContextValue`, `@LocalContextValue`, `Principal`, `@AuthenticationPrincipal`, `DataFetchingFieldSelectionSet`, `Locale`, and `DataFetchingEnvironment`.

These parameters are useful when entity lookup depends on the tenant, current user, locale, or selection set. Do not pull identifying data from context in place of keys if the schema contract requires the representation to supply the key explicitly.

## 8. Handling composite keys and multiple keys

An entity can have a key composed of multiple fields:

~~~graphql
type ProductVariant @key(fields: "productId variantCode") {
    productId: ID!
    variantCode: String!
    displayName: String!
}
~~~

The method receives the full representation:

~~~java
@EntityMapping
public ProductVariant productVariant(Map<String, Object> representation) {
    String productId = (String) representation.get("productId");
    String variantCode = (String) representation.get("variantCode");

    return variantService.find(productId, variantCode)
            .orElseThrow(() ->
                    new ProductVariantNotFoundException(productId, variantCode));
}
~~~

An entity can also declare multiple `@key` directives if the Federation version and schema composition allow it:

~~~graphql
type Product @key(fields: "id") @key(fields: "sku") {
    id: ID!
    sku: String!
    name: String!
}
~~~

In this case, the router can send a representation based on the appropriate key. The entity resolver must understand the representation shapes the subgraph advertises as supported.

With multiple different keys, accepting `Map<String, Object>` is usually clearer than assuming there is only an argument named `id`. Verify that key fields are present, have the right types, and can be queried efficiently in the persistence layer.

## 9. Resolving multiple representations at once

An `_entities` request can contain multiple representations of the same type. Spring for GraphQL allows an entity mapping method to accept a list of keys and return a list of entities:

~~~java
@EntityMapping
public List<Book> book(@Argument List<String> idList) {
    List<Book> loadedBooks = bookRepository.findAllById(idList);

    Map<String, Book> byId = loadedBooks.stream()
            .collect(Collectors.toMap(Book::id, Function.identity()));

    return idList.stream()
            .map(id -> {
                Book book = byId.get(id);
                if (book == null) {
                    throw new BookNotFoundException(id);
                }
                return book;
            })
            .toList();
}
~~~

The parameter name `idList` tells Spring this is a list of values for the `id` key. This convention supports dropping the plural suffix `List` to determine the argument name. You can set the argument name explicitly with `@Argument("id")` if needed.

Crucially, the returned list must preserve the exact order of the input keys. `findAllById` or a SQL `IN (...)` clause does not always guarantee the same order as the supplied ID list. Therefore, the example builds a map by ID and reconstructs the list according to `idList`.

If results are returned out of order, the router can attach fields of one entity to another representation. This is a severe data corruption bug even though each returned object is individually valid.

## 10. Accepting the entire list of representations

If a method needs to process multiple representations and multiple key fields, it can accept `List<Map<String, Object>>`:

~~~java
@EntityMapping
public List<Book> book(List<Map<String, Object>> representations) {
    List<String> ids = representations.stream()
            .map(representation -> (String) representation.get("id"))
            .toList();

    Map<String, Book> byId = bookService.findAllByIds(ids).stream()
            .collect(Collectors.toMap(Book::id, Function.identity()));

    return ids.stream()
            .map(id -> {
                Book book = byId.get(id);
                if (book == null) {
                    throw new BookNotFoundException(id);
                }
                return book;
            })
            .toList();
}
~~~

This form provides the complete representation for each entity. It is useful when a controller method needs to handle multiple key shapes itself or read extra metadata from representations.

Preserve the input order when constructing the result list. If representations have multiple key fields, construct a composite key or call the service with the exact required field set; do not read only `id` if the SDL does not define it as the key.

## 11. Using DataLoader to avoid N+1 when resolving entities

If each representation triggers a separate database query or HTTP call, a request with 100 entities can produce 100 I/O calls. This is the N+1 problem at the entity lookup step.

Spring for GraphQL provides `BatchLoaderRegistry` to register batch loaders. You can inject the registry into a controller or configuration:

The Spring Boot GraphQL starter provides a `BatchLoaderRegistry` bean out of the box, so you can inject it directly as shown in the example below.

~~~java
import org.dataloader.DataLoader;
import org.springframework.graphql.execution.BatchLoaderRegistry;
import org.springframework.stereotype.Controller;

@Controller
public class BookEntityController {

    public BookEntityController(
            BatchLoaderRegistry registry,
            BookService bookService) {

        registry.forTypePair(String.class, Book.class)
                .registerMappedBatchLoader((ids, environment) ->
                        bookService.findAllByIds(ids)
                                .collectMap(Book::id));
    }

    @EntityMapping
    public CompletableFuture<Book> book(
            @Argument String id,
            DataLoader<String, Book> dataLoader) {

        return dataLoader.load(id);
    }
}
~~~

`registerMappedBatchLoader` receives a set of keys and returns `Mono<Map<K, V>>`. This approach works well when the database has no result for some keys, because the map only contains the keys that were found.

In the example above, `BookService.findAllByIds` is assumed to return `Flux<Book>`. If the service uses synchronous JPA, offload the blocking call to an appropriate executor instead of running directly on the WebFlux event loop.

Spring registers DataLoaders per request. Calls to `load(id)` are batched together, allowing the batch loader to load multiple entities in a single data access call. DataLoader also caches results by key within the scope of the request.

Do not create a single DataLoader shared across the entire application. Per-request caching prevents data leakage across users or tenants and limits data lifetime to a single GraphQL operation.

## 12. How do registerBatchLoader and registerMappedBatchLoader differ?

`BatchLoaderRegistry` has two commonly used registration methods:

| API | Return data | When to use |
| --- | --- | --- |
| `registerBatchLoader` | `Flux<V>` whose count and order match the input key list | Every key must have a corresponding result slot |
| `registerMappedBatchLoader` | `Mono<Map<K, V>>` mapping keys to values | Some keys may not have an entity |

Example with `registerBatchLoader`:

~~~java
registry.forTypePair(String.class, Book.class)
        .registerBatchLoader((ids, environment) ->
                bookService.findAllByIdsInRequestedOrder(ids));
~~~

The function `findAllByIdsInRequestedOrder` must return results matching the exact count and order of keys; if an entity is not found, the corresponding position must be `null` per the batch loader contract.

With `registerMappedBatchLoader`, the result is a map keyed by ID, so map ordering is not used to match results. DataLoader matches each value by key automatically. This is usually the more convenient option for entity lookups when IDs may no longer exist in the system.

## 13. Combining @EntityMapping with @SchemaMapping and @BatchMapping

`@EntityMapping` only restores the entity object from the representation. Other fields are still resolved via standard mapping mechanisms.

For example, the `Book` entity has an `author` field:

~~~java
@Controller
public class BookController {

    @EntityMapping
    public Book book(@Argument String id) {
        return bookService.findById(id)
                .orElseThrow(() -> new BookNotFoundException(id));
    }

    @SchemaMapping(typeName = "Book", field = "author")
    public Author author(Book book) {
        return authorService.findById(book.authorId());
    }
}
~~~

If a request fetches many Books and each Book has an Author, the resolver above can cause N+1 queries. You can use `@BatchMapping`:

~~~java
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

import reactor.core.publisher.Mono;

@BatchMapping(typeName = "Book", field = "author")
public Mono<Map<Book, Author>> author(List<Book> books) {
    Set<String> authorIds = books.stream()
            .map(Book::authorId)
            .collect(Collectors.toSet());

    return authorService.findAllByIds(authorIds)
            .collectMap(Author::id)
            .map(byId -> {
                Map<Book, Author> result = new HashMap<>();
                for (Book book : books) {
                    Author author = byId.get(book.authorId());
                    if (author != null) {
                        result.put(book, author);
                    }
                }
                return result;
            });
}
~~~

The example skips Books without a matching Author, so the `author` field needs to be nullable in the SDL. If the field is declared non-null, convert a missing Author into an exception according to the API's error contract.

`@BatchMapping` is a shortcut for simple batch field-loading cases. Entity mapping and batch mapping solve two distinct steps:

- `@EntityMapping` loads entities based on representations sent by the router.
- `@BatchMapping` loads related fields for multiple parent entities at once.
- `DataLoader` can be used directly in entity mapping or schema mapping when more flexible control is needed.

If using the `Book` object as a map key in `@BatchMapping`, that class must have stable `equals` and `hashCode` implementations.

## 14. Supporting reactive and asynchronous return types

An entity mapping method can return the entity directly or an asynchronous type supported by Spring:

- Entity object.
- `Mono<T>`.
- `CompletableFuture<T>`.
- `Callable<T>`.

Reactive example:

~~~java
@EntityMapping
public Mono<Book> book(@Argument String id) {
    return bookRepository.findById(id);
}
~~~

Asynchronous example:

~~~java
@EntityMapping
public CompletableFuture<Book> book(@Argument String id) {
    return bookService.findByIdAsync(id);
}
~~~

With a reactive repository, returning `Mono` directly lets Spring process the pipeline without blocking. With `DataLoader`, `CompletableFuture` is the natural return type from `load`.

Do not call `block()` inside a resolver on the WebFlux event loop. Blocking can stall request-processing threads and slow down other Federation requests.

## 15. Missing entities and representation error handling

Spring for GraphQL has dedicated exceptions for representation resolution:

| Exception | Cause |
| --- | --- |
| `RepresentationException` | Missing `__typename` or no controller method found for the entity type |
| `RepresentationNotResolvedException` | Entity mapping method returns `null` or reactive/async result completes empty |

If a method returns `null`, Spring does not simply skip the representation. It raises `RepresentationNotResolvedException` to indicate the entity could not be resolved.

Example of explicitly throwing a business exception:

~~~java
@EntityMapping
public Book book(@Argument String id) {
    return bookService.findById(id)
            .orElseThrow(() -> new BookNotFoundException(id));
}
~~~

You can use `@GraphQlExceptionHandler` in a controller or `@ControllerAdvice` to convert exceptions from entity mapping into `GraphQLError`. The error will appear in the response of the `_entities` operation.

Avoid returning an empty or dummy object just to avoid errors. If the key does not exist or the caller lacks access rights, apply an error policy consistent with the API and ensure sensitive information is not leaked.

## 16. Context, tenant, and authorization during entity resolution

An entity representation comes from the router, yet it is still request input data. Never assume that having a valid key means the caller is authorized to read that entity.

An entity mapping method can accept `Principal`, `@AuthenticationPrincipal`, or `GraphQLContext`. For example:

~~~java
@EntityMapping
public Book book(
        @Argument String id,
        Principal principal,
        @ContextValue("tenantId") String tenantId) {

    return bookService.findVisibleBook(id, tenantId, principal)
            .orElseThrow(() -> new BookNotFoundException(id));
}
~~~

In a multi-tenant application, queries must be scoped to the current user's tenant. Do not look up solely by `id` and return the object regardless of tenant.

A subgraph should generally only accept requests from a trusted router or service gateway. If a subgraph endpoint is exposed publicly, clients could call `_entities` with crafted representations and attempt to access entities. Protect it with network policies, service-to-service authentication, and resolver-level authorization.

Do not place secrets, credentials, or authorization claims inside representations. Representations should only contain keys and identifying data required for Federation.

## 17. Testing entity mapping with GraphQlTester

You can test `_entities` directly with `GraphQlTester` or a specialized tester like `WebGraphQlTester`. For example:

~~~java
@Test
void resolvesBookFromFederationRepresentation() {
    graphQlTester.document("""
            query ResolveBook($representations: [_Any!]!) {
                _entities(representations: $representations) {
                    ... on Book {
                        id
                        title
                    }
                }
            }
            """)
            .variable("representations", List.of(
                    Map.of(
                            "__typename", "Book",
                            "id", "book-42"
                    )
            ))
            .execute()
            .path("_entities[0].id")
            .entity(String.class)
            .isEqualTo("book-42");
}
~~~

This test verifies both the Federation schema wiring and the controller method mapped by `@EntityMapping`.

You should also test:

- Representations with valid `__typename` and key.
- Representations missing `__typename`.
- `__typename` with no matching entity mapping.
- Non-existent entity keys.
- Composite keys being bound completely.
- Multiple representations returning results in the right order.
- DataLoader batching multiple keys in a single service call.
- Unauthorized users/tenants attempting to access an entity.
- Exceptions from entity mapping being converted into GraphQL errors as expected.

## 18. Testing ordering and batch loading

Ordering is part of the contract when an entity mapping accepts a list of representations. You can intentionally send IDs in a different order from the database:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.graphql.test.tester.GraphQlTester;

class FederationEntityMappingTests {

    private final GraphQlTester graphQlTester;

    @Autowired
    FederationEntityMappingTests(GraphQlTester graphQlTester) {
        this.graphQlTester = graphQlTester;
    }

    record BookView(String id) {
    }

    @Test
    void preservesRepresentationOrder() {
        graphQlTester.document("""
                query ResolveBooks($representations: [_Any!]!) {
                    _entities(representations: $representations) {
                        ... on Book {
                            id
                        }
                    }
                }
                """)
                .variable("representations", List.of(
                        Map.of("__typename", "Book", "id", "book-84"),
                        Map.of("__typename", "Book", "id", "book-42")
                ))
                .execute()
                .path("_entities")
                .entityList(BookView.class)
                .satisfies(books -> {
                    assertThat(books).extracting(BookView::id)
                            .containsExactly("book-84", "book-42");
                });
    }
}
~~~

To test DataLoader batching, you can use a mock service and verify it receives a multi-element key collection in a single invocation. Avoid checking only that the response is correct; a correct response can still be produced by N separate queries.

In integration tests, you can record how many times the repository or HTTP client is called. For a request containing multiple representations of the same entity type, the batch loader should receive multiple keys in one dispatch if they fall within the same batch window.

## 19. Common pitfalls when implementing Entity mapping

| Symptom | Cause | Solution |
| --- | --- | --- |
| `_entities` missing from schema | `FederationSchemaFactory` not used when creating `GraphQlSource` | Register the factory and schema customizer |
| No handler found for entity | `__typename` does not match entity mapping name | Rename method or set `@EntityMapping(name = "...")` |
| Key argument receives null | `@Argument` name does not match key in representation | Check field name and use explicit `@Argument("id")` |
| Composite key fails to resolve | Method accepts only one key while `@key` has multiple fields | Accept the full representation via Map |
| Batch results attach to wrong entity | Result list order differs from representation order | Rebuild results according to the input key list |
| Entity mapping causes N+1 | Each representation calls repository/service individually | Use list mapping or DataLoader |
| Method returning null causes error | Entity not found for representation | Handle missing entities per the error contract |
| Entity field is null | `@SchemaMapping` or `@BatchMapping` misconfigured | Check source object, field name, and mapping |
| `_entities` test fails before resolver | Invalid Federation schema wiring or query type | Check factory, SDL, keys, and inline fragments |
| Entity exposes another tenant's data | Resolver trusts key without checking permissions | Verify principal/tenant in the service or resolver |
| Service called multiple times despite DataLoader | Key type/name mismatch or loader not registered per request | Align generic key/value types and BatchLoaderRegistry |

## 20. Workflow for building Entity mapping

When adding an entity to a Spring for GraphQL subgraph, you can follow this sequence:

1. Identify which object types need to be shared across multiple subgraphs.
2. Choose unique and stable key fields for the entity.
3. Declare `@key` in the SDL according to the Federation version in use.
4. Enable Federation support with `FederationSchemaFactory`.
5. Write an `@EntityMapping` controller method for the entity type.
6. Bind the key with `@Argument` or accept the full representation via Map.
7. If accepting multiple representations, preserve the exact result order.
8. Use DataLoader or list entity mapping to avoid N+1 queries.
9. Use `@SchemaMapping` or `@BatchMapping` to resolve remaining fields.
10. Handle missing entities, exceptions, and tenant/user authorization.
11. Test the `_entities` operation with valid, invalid, and multi-key representations.
12. Ensure the subgraph endpoint is secured and reachable by the router over the right transport.

## 21. Key takeaways

- An entity is a keyed object type marked with `@key`.
- A representation contains `__typename` and the key fields needed to identify an entity.
- The router calls `_entities` to ask a subgraph to resolve entities.
- `FederationSchemaFactory` builds the Federation schema and wiring for `_entities`.
- `@EntityMapping` maps a controller method to an entity type.
- `@Argument` extracts a single key field; `Map<String, Object>` provides the entire representation.
- Entity mapping can accept multiple keys/representations and must preserve the return order.
- DataLoader batches entity lookups, reduces N+1 queries, and caches within the request scope.
- `@SchemaMapping` and `@BatchMapping` continue handling the entity's other fields.
- Null or empty returns are represented by Spring via `RepresentationNotResolvedException`.
- Always enforce authorization by user/tenant; never trust a representation as proof of access rights.

Entity mapping is the bridge between entity keys in a Federation schema and the actual data in each subgraph. When keys are designed stably, representations are bound accurately, batch results preserve order, and DataLoader is used appropriately, subgraphs can contribute fields to the same entity while maintaining clear data ownership.

## References

- [Spring for GraphQL — Federation](https://docs.spring.io/spring-graphql/reference/federation.html)
- [Spring for GraphQL — FederationSchemaFactory API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/data/federation/FederationSchemaFactory.html)
- [Spring for GraphQL — EntityMapping API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/data/federation/EntityMapping.html)
- [Spring for GraphQL — Request Execution and Batch Loading](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Apollo Federation — Introduction to Entities](https://www.apollographql.com/docs/graphos/schema-design/federated-schemas/entities/intro)
- [Apollo Federation — Subgraph Specification](https://www.apollographql.com/docs/graphos/schema-design/federated-schemas/reference/subgraph-spec)
