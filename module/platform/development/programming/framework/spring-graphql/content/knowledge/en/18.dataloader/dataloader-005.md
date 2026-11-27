# Mapped batch loader

## 1. What problem does a mapped batch loader solve?

When a client queries a list of books and each book has an `author` field, that field's resolver may need to load the corresponding author. If the resolver calls the repository separately for each book, a query fetching 50 books can trigger 50 additional queries to fetch authors. This is the N+1 problem.

DataLoader gathers data-loading requests generated within the same GraphQL execution. Resolvers call `load(key)` and receive a future; DataLoader collects the keys and invokes the batch loader to load multiple values at once. Its per-request caching mechanism also avoids loading the same key repeatedly within a single execution.

Spring for GraphQL provides `BatchLoaderRegistry` to register batch loading functions and automatically instantiate DataLoaders for each request. Among the registration options, `registerMappedBatchLoader` fits when results are returned as a `Map<K, V>` mapping directly from key to value.

A mapped batch loader is especially useful when the repository returns data in its own order, when some keys have no corresponding record, or when you prefer representing the relationship as a map instead of sorting a result list to match input key order.

## 2. Distinguishing between list batch loaders and mapped batch loaders

Spring for GraphQL supports two common registration styles:

| Mechanism | Batch input | Result | Key requirement |
| --- | --- | --- | --- |
| `registerBatchLoader` | `List<K>` | `Flux<V>` | Results must match the exact count and order of the input key list; use `null` for missing values |
| `registerMappedBatchLoader` | `Set<K>` | `Mono<Map<K, V>>` | Each value is attached to its corresponding key; independent of result ordering |

For example, DataLoader receives author keys `a1`, `a2`, `a3`. The repository might return authors in the order `a3`, `a1`; with a list batch loader, the application must reorder the result strictly to `a1`, `a2`, `a3`. With a mapped batch loader, simply return a map:

```java
Map<String, Author> authors = Map.of(
    "a1", authorA1,
    "a3", authorA3
);
```

DataLoader looks up each key in the map. Key `a2` has no entry, so its corresponding result is `null`. This is why mapped batch loaders are convenient for `IN (...)` queries where the database does not guarantee return order.

## 3. Designing the example schema and data model

Suppose a query returns a list of books, each referencing an author via `authorId`:

```graphql
type Query {
    books: [Book!]!
}

type Book {
    id: ID!
    title: String!
    author: Author
}

type Author {
    id: ID!
    name: String!
}
```

The `Book.author` field is declared nullable because data may lack an author or the author may have been deleted. If business rules guarantee every book has a valid author, you can consider `Author!`, in which case the batch loader must ensure no key is missing a result.

Illustrative Java model:

```java
public record Book(
    String id,
    String title,
    String authorId) {
}

public record Author(
    String id,
    String name) {
}
```

Client query:

```graphql
query BookCatalog {
    books {
        id
        title
        author {
            id
            name
        }
    }
}
```

The GraphQL engine resolves `Query.books` first. Then, for each `Book`, the engine needs to resolve the `author` field. DataLoader batches the `authorId` values to load multiple authors at once.

## 4. Creating a service returning a Map by key

A mapped batch loader needs to return a map keyed by the requested identifiers with values being the corresponding objects. With Spring Data JPA, a repository can be declared as:

```java
import org.springframework.data.jpa.repository.JpaRepository;

public interface AuthorRepository extends JpaRepository<AuthorEntity, String> {
}
```

The service uses the repository to load all authors for a set of IDs:

```java
import java.util.Map;
import java.util.Set;
import java.util.function.Function;
import java.util.stream.Collectors;
import org.springframework.stereotype.Service;

@Service
public class AuthorQueryService {

    private final AuthorRepository authorRepository;
    private final AuthorMapper authorMapper;

    public AuthorQueryService(
            AuthorRepository authorRepository,
            AuthorMapper authorMapper) {
        this.authorRepository = authorRepository;
        this.authorMapper = authorMapper;
    }

    public Map<String, Author> findAllByIds(Set<String> ids) {
        if (ids.isEmpty()) {
            return Map.of();
        }

        return authorRepository.findAllById(ids).stream()
            .map(authorMapper::toDomain)
            .collect(Collectors.toMap(Author::id, Function.identity()));
    }
}
```

`AuthorRepository` can be a Spring Data repository, while `AuthorMapper` converts persistence entities into the `Author` domain type. The service returns a map indexed by `Author.id`, because that is the key the resolver passes into DataLoader.

Do not assume ordering from `findAllById`. With a mapped batch loader, the map is the essential contract; every entry must use the exact ID. If the repository returns a record whose ID was not in the requested set, verify your query or mapping rather than inserting unexpected entries into the map.

## 5. Registering a mapped batch loader with `BatchLoaderRegistry`

Spring Boot provides a `BatchLoaderRegistry` bean. You can inject the registry into a configuration class and register the loader in its constructor:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.execution.BatchLoaderRegistry;
import reactor.core.publisher.Mono;

@Configuration
public class GraphQlDataLoaderConfig {

    public GraphQlDataLoaderConfig(
            BatchLoaderRegistry registry,
            AuthorQueryService authorQueryService) {

        registry.forTypePair(String.class, Author.class)
            .registerMappedBatchLoader((authorIds, environment) ->
                Mono.fromCallable(() ->
                    authorQueryService.findAllByIds(authorIds)
                )
            );
    }
}
```

`forTypePair(String.class, Author.class)` registers a loader with a `String` key and `Author` value. `registerMappedBatchLoader` accepts a function taking the set of keys and `BatchLoaderEnvironment`, and returns `Mono<Map<String, Author>>`.

Spring for GraphQL uses this registry to register the DataLoader into each GraphQL request's `DataLoaderRegistry`. The application does not need to create a singleton DataLoader shared across requests.

In this example, `Mono.fromCallable` defers calling the service until the publisher is subscribed. If the service uses blocking JPA/JDBC inside a reactive application, offload the blocking work onto an appropriate scheduler such as `Schedulers.boundedElastic()`. Wrapping a blocking call in `Mono` does not magically make a database query non-blocking. If your service/repository is already reactive, return its reactive publisher directly instead of wrapping a blocking call.

Example with a service already returning `Mono<Map<String, Author>>`:

```java
registry.forTypePair(String.class, Author.class)
    .registerMappedBatchLoader((authorIds, environment) ->
        authorReactiveQueryService.findAllByIds(authorIds)
    );
```

## 6. Using DataLoader in `@SchemaMapping`

Once registered, a resolver can accept `DataLoader` as a method parameter:

```java
import java.util.concurrent.CompletableFuture;
import org.dataloader.DataLoader;
import org.springframework.graphql.data.method.annotation.SchemaMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookFieldController {

    @SchemaMapping(typeName = "Book", field = "author")
    public CompletableFuture<Author> author(
            Book book,
            DataLoader<String, Author> authorLoader) {

        if (book.authorId() == null) {
            return CompletableFuture.completedFuture(null);
        }

        return authorLoader.load(book.authorId());
    }
}
```

`authorLoader.load(book.authorId())` does not necessarily query the database on that line. It queues the key in DataLoader and returns `CompletableFuture<Author>`. GraphQL Java manages when accumulated keys are dispatched and completes the future once the batch loader returns results.

When registering with `forTypePair`, Spring for GraphQL defaults the loader name based on the value type's class name. Spring for GraphQL can infer the loader from the `DataLoader<String, Author>` generic parameter in the resolver signature, so specifying a name manually is usually unnecessary.

If the `author` field is declared as nullable `Author`, a key without a result can return `null`. If the field is `Author!`, a null result violates the non-null contract and GraphQL generates an execution error with corresponding null propagation.

## 7. How a mapped batch loader handles keys without data

Suppose DataLoader receives keys `{a1, a2, a3}` while the database only has `a1` and `a3`. The mapped batch loader returns:

```java
Map<String, Author> result = Map.of(
    "a1", authorA1,
    "a3", authorA3
);
```

Key `a2` has no entry in the map. DataLoader returns `null` for that load call. This differs from a list-based batch loader, where the application must return a `null` element at the exact position of the missing key.

How you handle missing keys must align with the schema and business rules:

- Optional relationship: the field can be nullable and the map omits the entry.
- Required relationship: missing data should be treated as an integrity or business error; do not silently treat it as success.
- Parent lacks `authorId`: the resolver can return a completed future with `null` without calling `load(null)`.
- Invalid ID: validate or reject according to domain rules prior to querying if needed.

Do not fabricate a dummy `Author` object just to fill a missing key. Doing so gives clients false data and masks data integrity bugs.

## 8. Mapped batch loader does not depend on result ordering

This is a major difference compared to the list-based `registerBatchLoader`.

Suppose the resolver requests IDs in this order:

```text
["a1", "a2", "a3"]
```

The database might return:

```text
[Author("a3"), Author("a1")]
```

With a list batch loader, returning this list directly causes DataLoader to pair the wrong authors with books because results must strictly follow input key order. With a mapped batch loader, the service builds a map:

```java
Map<String, Author> result = Map.of(
    "a3", authorA3,
    "a1", authorA1
);
```

DataLoader looks up results by key and ignores map iteration order. `a2` has no entry and resolves to `null`. This is a major advantage when running `WHERE id IN (...)` database queries, since many databases do not guarantee row order without an `ORDER BY`.

## 9. Request-scoped caching and duplicate keys

DataLoader includes per-request caching. If multiple books reference author `a1`, the resolver may call `load("a1")` multiple times, yet DataLoader by default reuses the already-requested result for that key within the same execution.

For example:

```text
Book 1 -> authorId = a1
Book 2 -> authorId = a1
Book 3 -> authorId = a2
Book 4 -> authorId = a3
```

The `load` calls can be combined into a single batch with unique keys `a1`, `a2`, `a3`. Thus, the database only needs to fetch each author once in that batch.

The default cache lives within the request's DataLoader scope, not as a long-lived cache shared across the entire application. Do not manually create a singleton DataLoader to store data across multiple users, because data may depend on tenant, permissions, or update state.

If a mutation updates data and the operation later re-reads the same key within the same execution, consider clearing the key from the cache or priming the new value using the appropriate DataLoader API. Otherwise, subsequent loads may receive the pre-update cached value.

## 10. Customizing loader names and DataLoaderOptions

When using `forTypePair`, Spring for GraphQL names the loader after the value class by default. This is convenient when an entity type only needs one primary loader.

If you need multiple loaders returning the same value type for different purposes or key types, you can register by name:

```java
registry.<String, Author>forName("authorsById")
    .registerMappedBatchLoader((ids, environment) ->
        Mono.fromCallable(() -> authorQueryService.findAllByIds(ids))
    );
```

When using `forName`, the `DataLoader` parameter name in the resolver method must match the registered name:

```java
@SchemaMapping(typeName = "Book", field = "author")
public CompletableFuture<Author> author(
        Book book,
        DataLoader<String, Author> authorsById) {
    return authorsById.load(book.authorId());
}
```

This example demonstrates a custom loader name; in actual configuration, keep the same `authorsById` name in both registration and the method parameter. If there is only one loader for `Author`, `forTypePair` is usually simpler.

You can configure `DataLoaderOptions` when you need to cap batch sizes or adjust caching:

```java
registry.forTypePair(String.class, Author.class)
    .withOptions(options -> options.setMaxBatchSize(100))
    .registerMappedBatchLoader((ids, environment) ->
        Mono.fromCallable(() -> authorQueryService.findAllByIds(ids))
    );
```

`maxBatchSize` limits how many keys go into a single batch. This is useful when a database limits bind parameters or oversized `IN` clauses. If DataLoader has more keys than the maximum, GraphQL Java splits them into multiple batches. Pick a limit based on database capabilities and actual query cost.

The signature of the `withOptions` callback depends on the `java-dataloader` version managed by Spring GraphQL. If your project version uses `DataLoaderOptions` directly instead of a builder callback, construct the options per that version's API and pass it to the `withOptions(DataLoaderOptions)` overload.

## 11. Using GraphQLContext in a mapped batch loader

A mapped batch loader receives `BatchLoaderEnvironment` alongside the key set. This environment provides access to the GraphQL execution context. Spring for GraphQL integrates `BatchLoaderRegistry` so batch loaders and resolvers share the same `GraphQLContext`, while supporting context propagation.

This is useful when queries depend on:

- The current tenant.
- Locale or display language.
- Correlation metadata for tracing.
- The data scope visible to the current user.

Conceptual example of tenant handling:

```java
registry.forTypePair(String.class, Author.class)
    .registerMappedBatchLoader((ids, environment) -> {
        GraphQLContext context = environment.getContext();
        String tenantId = context.get("tenantId");

        return Mono.fromCallable(() ->
            authorQueryService.findAllByIdsAndTenant(ids, tenantId)
        );
    });
```

`tenantId` must be populated into `GraphQLContext` during request handling or by an appropriate interceptor. The batch service must still enforce tenant filtering on the server; never trust a client-supplied tenant ID argument if the user is not authorized for that tenant.

Because loaders are registered per request, caches are never shared between requests from different tenants. However, within a single request, if one DataLoader serves multiple permission contexts across keys, include the distinguishing attributes in the key or design separate loaders to avoid inappropriately sharing results.

## 12. Distinguishing mapped batch loader and `@BatchMapping`

`@BatchMapping` is a shorthand for a common case: an object field needs to be batch-loaded from a list of source objects. Spring for GraphQL automatically registers the batch loading function and data fetcher for that field.

| Criterion | `registerMappedBatchLoader` | `@BatchMapping` |
| --- | --- | --- |
| Input | Set of keys sent by resolvers to DataLoader | List of source/parent objects |
| Output | `Mono<Map<K, V>>` | Typically `Mono<Map<Source, Value>>` or an ordered list/Flux variant |
| Registration site | `BatchLoaderRegistry` | Annotation on a controller method |
| Best suited for | Reusing a loader across resolvers, custom keys, context, or options | Batching one relational field by source object with minimal boilerplate |
| Separate resolver | Requires `@SchemaMapping` calling `DataLoader.load` | Spring registers the field's data fetcher automatically |

`@BatchMapping` example:

```java
@Controller
public class BookBatchController {

    private final AuthorQueryService authorQueryService;

    public BookBatchController(AuthorQueryService authorQueryService) {
        this.authorQueryService = authorQueryService;
    }

    @BatchMapping(typeName = "Book", field = "author")
    public Mono<Map<Book, Author>> author(List<Book> books) {
        Set<String> ids = books.stream()
            .map(Book::authorId)
            .filter(Objects::nonNull)
            .collect(Collectors.toSet());

        return Mono.fromSupplier(() -> authorQueryService.findAllByIds(ids))
            .map(authorsById -> books.stream()
                .filter(book -> authorsById.containsKey(book.authorId()))
                .collect(Collectors.toMap(
                    Function.identity(),
                    book -> authorsById.get(book.authorId())
                )));
    }
}
```

Here the map uses `Book` as the key, so `Book` needs stable `equals` and `hashCode` implementations. Because `Book` is a Java record in this example, Java generates both methods automatically from its record components. If the service uses blocking JPA/JDBC inside a reactive application, offload the query to an appropriate scheduler; `Mono.fromSupplier` alone does not make a blocking operation non-blocking. If you need an ID-keyed DataLoader shared across multiple resolvers, `registerMappedBatchLoader` is usually a better fit.

Do not register both `@BatchMapping` and a manual `@SchemaMapping`/DataLoader for the same type/field pair. Pick one mechanism to own the field.

## 13. Handling errors, missing values, and inconsistent data

A mapped batch loader can encounter several distinct cases:

- **One key not found:** omit that key from the map; DataLoader returns `null` for that key.
- **No keys found:** return `Map.of()`; all corresponding loads receive `null`.
- **Database or service failure:** return an error publisher or let the exception become a batch failure; configure proper GraphQL error handling.
- **Broken foreign-key data:** for example, `Book.authorId` points to a nonexistent author. Decide whether this is a nullable relation or a data integrity error.
- **Same key appears multiple times:** DataLoader caches by key within the request by default, reducing duplicate loads.

Do not convert infrastructure errors into an empty map. If the database is down, returning an empty map tricks clients into thinking none of the authors exist. Let errors propagate through error handling so clients and observability can detect the failure.

For non-null fields, a missing value triggers null propagation. If business rules forbid missing values, check data integrity or return an explicit error instead of letting random nullability errors surface.

## 14. Testing mapped batch loaders

Test two aspects: the batch function logic and the GraphQL operation using the DataLoader.

### Testing key-to-value mapping

With input keys `a1`, `a2`, `a3`, verify that:

- The map contains `a1` and `a3` if the repository finds those two authors.
- `a2` has no entry and its corresponding load yields `null`.
- Results do not depend on the order returned by the repository.
- The repository is called in batch rather than once per key.
- An empty key set returns an empty map without querying the database unnecessarily.

### Testing GraphQL with `GraphQlTester`

Operation example:

```java
@SpringBootTest
@AutoConfigureHttpGraphQlTester
class BookAuthorBatchTests {

    @Autowired
    GraphQlTester graphQlTester;

    @Test
    void loadsAuthorsForBooksInOneBatch() {
        graphQlTester.document("""
            query {
                books {
                    id
                    author {
                        id
                        name
                    }
                }
            }
            """)
            .execute()
            .path("books[0].author.name")
            .entity(String.class)
            .isEqualTo("Nguyen An");
    }
}
```

This example assumes the test context has at least one book written by `Nguyen An`. To prove batching actually works, use a spy or counter on the service/repository and assert that an operation returning multiple books invokes the batch author-loading method only the expected number of times. Verifying only a correct response does not prove N+1 was eliminated.

Additional test cases to include:

- Multiple books sharing the same `authorId`.
- Multiple books with different `authorId`s.
- One or more nonexistent authors.
- A book whose `authorId` is `null`.
- A batch with more keys than `maxBatchSize`.
- A repository failure during the batch.
- Two requests for different tenants not sharing cached data.
- Nullable and non-null fields handling missing values per contract.

## 15. Common mistakes with mapped batch loaders

| Symptom | Cause | Solution |
| --- | --- | --- |
| Resolver cannot find DataLoader | Key/value type mismatch or wrong loader name | Match `forTypePair`, `DataLoader<K,V>` generics, or `forName` name |
| Field is always `null` | Map uses wrong key, mismatched Java key type, or repository finds no data | Ensure map keys match the exact keys passed to `load` |
| Wrong author assigned to a book | Using a list batch loader without preserving key order | Use a mapped loader or sort the list to match key order |
| N+1 still occurs | Resolver calls repository directly instead of `DataLoader.load` | Register batch loader and switch resolver to DataLoader |
| Loader not registered in requests | Not using Spring-managed `BatchLoaderRegistry` or custom GraphQL setup bypasses registry | Verify registry is injected and wired into execution service |
| No result triggers non-null GraphQL error | SDL declares field non-null while map lacks the key | Adjust nullability or guarantee required relationship exists |
| Database queried with huge ID set | Batch has no size limit | Configure an appropriate `maxBatchSize` |
| Wrong tenant data returned | Batch query does not enforce tenant/authorization from server context | Read trusted context and filter in service/repository |
| Database fails yet client gets `null` | Exception swallowed and converted to an empty map | Only use empty maps for missing data; propagate infrastructure errors |
| Cache returns stale data after mutation | DataLoader cached the key before data was updated | Clear or prime the key after writes if re-read in the same request |

## 16. Mapped batch loader implementation checklist

- [ ] Clearly identify the N+1 relationship to batch and the key used to load data.
- [ ] Choose `registerMappedBatchLoader` when the natural output is a key-value map.
- [ ] Key type and value type match `DataLoader<K, V>` in the resolver.
- [ ] Batch function accepts `Set<K>` and returns `Mono<Map<K, V>>`.
- [ ] Map is indexed by the exact key sent by the resolver.
- [ ] Missing keys are handled according to nullability and business rules.
- [ ] Resolver calls `DataLoader.load` and returns a future rather than querying per parent.
- [ ] Use `BatchLoaderRegistry` so loaders are registered per request.
- [ ] Do not share DataLoader caches globally across multiple requests.
- [ ] Cap batch sizes according to database capabilities.
- [ ] Batch query enforces tenant and authorization checks on the server.
- [ ] Test order independence, missing keys, duplicate keys, errors, and query counts.
- [ ] Choose `@BatchMapping` if you only need to batch one field per parent without separate loader config.

## Conclusion

A mapped batch loader in Spring for GraphQL lets you load multiple entities by a set of keys and return results as `Map<K, V>`. `BatchLoaderRegistry.forTypePair(...).registerMappedBatchLoader(...)` registers the batch function; resolvers inject `DataLoader<K, V>` and call `load(key)`. DataLoader batches keys within the same GraphQL request, manages per-request caching, and matches results by key, avoiding dependence on repository return order.

Use a mapped loader when you need explicit key-value mapping, graceful missing-key handling, or loader reuse across multiple resolvers. Structure the map with exact keys, align SDL nullability, cap batch sizes, enforce tenant/authorization inside batch queries, and test actual query counts. When you only need to batch a simple relational field, `@BatchMapping` can be a more concise alternative.

## References

- [Spring for GraphQL — Request Execution: Batch Loading](https://docs.spring.io/spring-graphql/reference/request-execution.html#execution.graphql-datafetcher.batch-loading)
- [Spring for GraphQL — BatchLoaderRegistry API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/execution/BatchLoaderRegistry.html)
- [Spring for GraphQL — `@BatchMapping`](https://docs.spring.io/spring-graphql/reference/controllers.html#controllers.schema-mapping.batch-mapping)
