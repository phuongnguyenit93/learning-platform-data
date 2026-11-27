# DataLoader keys and values

GraphQL often returns interrelated objects. For instance, a query fetches 50 books and the client also selects the `author` field for each book. If each `Book`'s resolver individually queries the author by `authorId`, the server can execute one query for books and 50 queries for authors. This is the N+1 problem.

DataLoader batches key-based data-loading requests together. In this example, the **key** is `authorId`, and the **value** is the corresponding `Author` object. Each resolver calls `load(authorId)`; DataLoader collects the keys within the same execution tick and invokes the batch loader to load multiple authors at once. Results are returned to the exact resolvers that requested them.

In Spring for GraphQL, DataLoader integrates with GraphQL Java via `BatchLoaderRegistry`, `DataLoaderRegistry`, and mechanisms like `@BatchMapping`. Understanding the key/value relationship is essential so that a batch loader returns data for the right objects, in the right order, and without producing wrong results when data is missing or keys are duplicated.

## What does DataLoader<K, V> represent?

DataLoader has two type parameters:

- **K (key):** the value used to identify the data to load, such as `authorId`, `productId`, or `userId`.
- **V (value):** the data returned for that key, such as `Author`, `Product`, or `User`.

With a `DataLoader<String, Author>` declaration, each `load` call accepts a `String` key and returns an asynchronous `Author` result:

~~~java
DataLoader<String, Author> authorLoader;

CompletableFuture<Author> authorFuture =
        authorLoader.load("author-12");
~~~

The key does not have to be the value's ID, but there must be a stable mapping rule from key to value. Keys are usually primary or foreign keys used for querying. For a one-to-many relationship, the value can be `List<Review>`:

~~~java
DataLoader<String, List<Review>> reviewsLoader;
~~~

Here the key is `bookId`, and the value is the list of `Review`s belonging to that `Book`. Choosing the value type must reflect the cardinality of the relationship the resolver needs to resolve.

## Key and value flow in a query

Suppose the schema has `Book` and `Author`:

~~~graphql
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
~~~

Java model:

~~~java
public record Book(
        String id,
        String title,
        String authorId) {
}

public record Author(
        String id,
        String name) {
}
~~~

Client request:

~~~graphql
query {
  books {
    id
    title
    author {
      id
      name
    }
  }
}
~~~

GraphQL executes `Query.books`, receives the list of `Book`s, and then resolves the `author` field for each element. The `author` resolver does not query the repository directly; it passes `authorId` to DataLoader:

~~~java
@Controller
public class BookController {

    @SchemaMapping(typeName = "Book", field = "author")
    public CompletableFuture<Author> author(
            Book book,
            DataLoader<String, Author> authorLoader) {
        return authorLoader.load(book.authorId());
    }
}
~~~

Suppose the list of books has `authorId` values `a-1`, `a-2`, `a-1`; DataLoader can batch the requests and load two unique authors if key caching is enabled. The `Author` results are distributed back to each `Book`'s `author` field.

Keys and values can be visualized as follows:

| Requesting resolver | Key passed in | Value expected |
| --- | --- | --- |
| Book 1 | `a-1` | Author with ID `a-1` |
| Book 2 | `a-2` | Author with ID `a-2` |
| Book 3 | `a-1` | Same Author with ID `a-1` |

DataLoader batches data-loading requests. It does not inherently know how to query a database; the batch loader registered by the application performs that part.

## BatchLoader: results must match key order

GraphQL Java DataLoader supports `BatchLoader<K, V>`. A batch loader takes a list of keys and returns a corresponding list of values:

~~~java
BatchLoader<String, Author> batchLoader = authorIds ->
        CompletableFuture.supplyAsync(() -> {
            Map<String, Author> authorsById =
                    authorRepository.findAllById(authorIds).stream()
                            .collect(Collectors.toMap(
                                    Author::id,
                                    Function.identity()));

            return authorIds.stream()
                    .map(authorsById::get)
                    .collect(Collectors.toList());
        });
~~~

The critical requirement of `BatchLoader` is that **value positions must match key positions in the input list**. If the input is `[a-1, a-2, a-3]`, the output must take the form `[author-a1, author-a2, author-a3]`. Never return the repository's list verbatim if the database returns rows in a different order.

For example, the repository might return `[author-a3, author-a1]` because `a-2` does not exist and query order is not guaranteed. Returning that list as-is can cause DataLoader to assign the wrong author to a resolver. A safe approach is to build an ID map and iterate through the original key list to construct an accurately ordered value list.

If a key is not found, the batch loader can place `null` at the corresponding index, provided the GraphQL type and data policy allow it. If the `author` field is declared `Author!`, `null` produces a GraphQL execution error and triggers null propagation. If the field is nullable, the response can contain `author: null`.

## MappedBatchLoader: returning results as a key/value map

When the repository does not guarantee order, `MappedBatchLoader<K, V>` is often easier to use. It takes a set of keys and returns a map where each key maps directly to its value:

~~~java
MappedBatchLoader<String, Author> mappedLoader = authorIds ->
        CompletableFuture.supplyAsync(() ->
                authorRepository.findAllById(authorIds).stream()
                        .collect(Collectors.toMap(
                                Author::id,
                                Function.identity())));
~~~

With this approach, element ordering in the map does not matter. DataLoader looks up values by the original key to distribute them to each `load` call. If a key is absent from the map, the result for that key is `null`.

Comparison:

| Criterion | BatchLoader | MappedBatchLoader |
| --- | --- | --- |
| Input | List of keys | Set of keys |
| Output | List of values | Map from key to value |
| Constraint | Values must match key order | Each value must be stored under the right key |
| Best suited for | Data sources returning results in matching order | Repositories returning unordered results or missing keys |

Choose a mapped loader when the data source returns records in its own order or may omit unfound keys. Choose a list batch loader when you can accurately guarantee result order and count.

## Registering a mapped batch loader with Spring for GraphQL

Spring for GraphQL provides `BatchLoaderRegistry` to register loaders by key/value type pair. The registry registers the loader definition and creates corresponding `DataLoader`s in each GraphQL request's registry.

Example registering an `Author` loader:

~~~java
@Configuration
public class DataLoaderConfiguration {

    public DataLoaderConfiguration(
            BatchLoaderRegistry registry,
            AuthorService authorService) {

        registry.forTypePair(String.class, Author.class)
                .registerMappedBatchLoader((authorIds, environment) ->
                        Mono.fromSupplier(() ->
                                authorService.findByIds(authorIds)));
    }
}
~~~

Suppose `authorService.findByIds` returns `Map<String, Author>` keyed by `Author` ID. The generic types in `forTypePair` must match the `DataLoader` type requested by the resolver: `DataLoader<String, Author>`.

The resolver obtains the loader by key/value type:

~~~java
@Controller
public class BookController {

    @SchemaMapping(typeName = "Book", field = "author")
    public CompletableFuture<Author> author(
            Book book,
            DataLoader<String, Author> authorLoader) {
        return authorLoader.load(book.authorId());
    }
}
~~~

Spring for GraphQL supplies the registered `DataLoader` to the resolver for the current request. The application does not need to manually instantiate a singleton shared `DataLoader`. Loaders are created from the request's registry so caches and data are never inadvertently shared across different requests or users.

If using a list-based `BatchLoader` instead of a mapped loader, register with `registerBatchLoader` and ensure the returned value list matches the input key list order. Choose the loader type that best matches how the repository returns data.

## DataLoader keys need stable equals and hashCode

DataLoader typically caches by key. Therefore, keys must have consistent comparison rules:

- Two keys representing the same data must be considered equal.
- `equals` and `hashCode` must be consistent.
- Do not mutate fields participating in `equals`/`hashCode` after a key has been passed to the loader.

Simple types like `String`, `Long`, `UUID`, or enums are usually suitable. If a composite key is needed, you can use a Java record:

~~~java
public record ProductPriceKey(
        String productId,
        String currency) {
}
~~~

Then the loader can have type:

~~~java
DataLoader<ProductPriceKey, Money> priceLoader;
~~~

A composite key distinguishes the same product across different currencies. If only `productId` were used as the key, DataLoader could return a price cached for another currency by mistake.

Avoid using a mutable object as a key if properties governing equality can change during processing. Unstable keys can prevent the cache from finding stored entries or create unexpected duplicate entries.

## Duplicate keys and caching

DataLoader usually enables caching by key. If multiple resolvers call `load("a-1")` within one request, DataLoader can share the future and load the value only once. This avoids both N+1 and loading the same key repeatedly.

For example:

~~~java
CompletableFuture<Author> first = authorLoader.load("a-1");
CompletableFuture<Author> second = authorLoader.load("a-1");
~~~

Two calls with the same key in the same `DataLoader` share the cached result. Consequently, the batch loader does not necessarily receive duplicate keys when caching is enabled.

If caching is disabled, the loader may receive multiple occurrences of the same key depending on configuration and call patterns. With `BatchLoader`, the output list must still match every input key position. With `MappedBatchLoader`, the map holds only one entry per key because a map cannot represent multiple distinct values for the same key.

Do not disable caching just to work around a mapping bug. First check whether keys are stable, whether the batch loader returns the right values, and whether the cache is properly scoped to the request.

## Missing values, null, and loading errors

Not every key has a value. For example, a `Book` references an `authorId` that was deleted or does not exist. The batch loader needs clear rules:

- Return `null` for nonexistent keys if the schema allows a nullable field.
- Return an error if missing data violates business rules.
- Never substitute another value into a missing key's position just to pad the element count.

With `BatchLoader`, the returned list must preserve a slot for each key; `null` values can represent keys with no data. With `MappedBatchLoader`, keys absent from the map are treated as having no corresponding value.

If a batch loader throws a batch-level error, all waiting calls in that batch may fail together. If an error applies to only a single key, consider DataLoader Java's per-key error representation or handle it in the service so remaining keys can still return results. Never swallow errors and return an empty map, because clients will struggle to distinguish truly nonexistent data from system failures.

## Values can be lists or complex objects

DataLoader does not restrict values to single objects. For a one-to-many relationship, the key can be `bookId` and the value a list of `Review`s:

~~~java
DataLoader<String, List<Review>> reviewsLoader;
~~~

Resolver:

~~~java
@SchemaMapping(typeName = "Book", field = "reviews")
public CompletableFuture<List<Review>> reviews(
        Book book,
        DataLoader<String, List<Review>> reviewsLoader) {
    return reviewsLoader.load(book.id());
}
~~~

The corresponding mapped loader can return `Map<String, List<Review>>`, mapping each `bookId` to that book's list of reviews. If a book has no reviews yet, return an empty list instead of `null` when the schema declares `[Review!]!`.

For multi-dimensional data, you can use records as values or keys. However, keep the model simple and clearly define each type's meaning so mapping remains easy to test.

## Request-scoped caching

DataLoader typically retains its cache for the duration of a single GraphQL request. Once the request ends, the corresponding registry and cache are discarded. Thus, the same key can be reloaded in the next request to reflect fresh data.

Spring for GraphQL integrates `BatchLoaderRegistry` with a per-request `DataLoaderRegistry`. Avoid declaring a static `DataLoader` or storing a `DataLoader` in a singleton controller/service field, which can cause:

- Stale data reused across multiple requests.
- Caches shared among users with different access permissions.
- Growing memory consumption from overly long-lived caches.
- One tenant's data leaking to another tenant if keys omit tenant scope.

If a loader needs context such as tenant or principal, use the request context in the batch loader and ensure data queries enforce the same authorization rules. Never rely on clients not knowing a key to protect data.

## Refreshing the cache after a mutation

If a mutation modifies a value already cached by DataLoader in the same request, subsequent calls may read the stale value. DataLoader provides cache management operations such as `clear(key)`, `clearAll()`, and `prime(key, value)`.

Example after updating an `Author`:

~~~java
authorLoader.clear(updatedAuthor.id())
        .prime(updatedAuthor.id(), updatedAuthor);
~~~

`clear` removes the old entry; `prime` inserts the new value into the cache. You can also just `clear` so the next `load` fetches fresh data. Cache updates must stay consistent with mutation and transaction outcomes: only prime a new value once the application has confirmed the change succeeded.

Normally, each HTTP GraphQL request has its own `DataLoaderRegistry`. Cache refreshing mainly matters when multiple fields within the same operation reuse a loader after a data modification. Never use these operations as a global cross-request cache.

## Distinguishing DataLoader and @BatchMapping

`@BatchMapping` is a convenient batch resolver declaration in Spring for GraphQL. The framework registers an underlying `DataLoader` and gathers source objects to invoke the batch method:

~~~java
@Controller
public class BookBatchController {

    private final AuthorService authorService;

    public BookBatchController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @BatchMapping(typeName = "Book", field = "author")
    public Map<Book, Author> author(List<Book> books) {
        return authorService.findAuthorsFor(books);
    }
}
~~~

In this example, the source `Book` acts as the key at the batch mapping layer, while `Author` is the value. When finer control over keys is needed, use `BatchLoaderRegistry` and `DataLoader<K, V>` directly as in the `authorId` example above.

Choose `@BatchMapping` when mapping straightforwardly from source objects to related data. Choose `DataLoader` directly when sharing a loader across multiple resolvers, using composite keys, controlling caching, or registering batch logic by key/value type pair.

## Testing key and value mapping

A batch loader should be tested with differently ordered data, duplicate keys, and missing keys. For example:

| Key input | Repository returned data | Expected result |
| --- | --- | --- |
| `[a-1, a-2]` | `[a-2, a-1]` | Values still attach properly to `a-1` and `a-2` |
| `[a-1, a-2]` | Only `a-1` | `a-2` receives `null` or error per contract |
| `[a-1, a-1]` | One `Author` `a-1` | Both resolvers receive the same value when caching is enabled |
| `[a-1, a-2]` | Batch loader throws exception | Affected fields receive errors per policy |

You can use `GraphQlTester` to verify end-to-end results:

~~~java
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
    .path("books")
    .entityList(BookView.class)
    .hasSize(3);
~~~

Beyond the response, verify how many times the repository or batch service is called. With multiple `Book`s sharing the same `authorId`, load counts should reflect unique keys when caching is enabled, rather than the number of `Book`s. For mapped loaders, reverse or shuffle repository return order to confirm key/value mapping remains accurate.

## Common mistakes

| Symptom | Possible cause | Solution |
| --- | --- | --- |
| Wrong author assigned to a book | `BatchLoader` returns list in repository order instead of key order | Build an ID map and rebuild the list in input key order |
| Some `author` fields become `null` | Key has no value or map is missing the entry | Define missing-key policy and check nullability |
| Batch loader is not called | Resolver does not use `DataLoader` or loader type pair is unregistered | Verify key/value generics and registry registration |
| Loader resolves to wrong type | `forTypePair` does not match `DataLoader` type in resolver | Align `K` and `V` in registry and method signature |
| Same key queried multiple times | Cache disabled, unstable key equality, or different loader registries | Check `DataLoaderOptions` and `equals`/`hashCode` |
| Stale data after mutation | Cache holds pre-update loaded value | `clear` or `prime` key after update succeeds |
| Data leaked between requests | Using `DataLoader`/cache in singleton scope | Use loaders created from the per-request registry |
| Entire batch fails together | Batch-level exception | Distinguish batch-wide errors from per-key errors |

## Key and value design principles

When designing `DataLoader`s in Spring for GraphQL, remember:

1. **Pick keys based on the data to load.** Use stable IDs or record keys, not mutable objects.
2. **Pick values based on cardinality.** A key may map to a single object, a list, or a DTO.
3. **Preserve the mapping contract.** `BatchLoader` returns a list in key order; `MappedBatchLoader` returns a map with exact keys.
4. **Handle missing keys intentionally.** Distinguish valid `null`s from missing data or system errors.
5. **Understand caching and key equality.** Keys must have stable `equals`/`hashCode`; default caching helps with duplicate keys.
6. **Keep loaders request-scoped.** Use Spring's `BatchLoaderRegistry` to avoid accidental cross-request cache sharing.
7. **Refresh the cache when needed.** `clear` or `prime` after mutations when subsequent fields in the same request need fresh data.
8. **Test ordering and duplicate keys.** Repository results may arrive out of the requested order.

DataLoader keys and values define how data-loading requests are batched and routed back to the right resolvers. The key identifies the data to load; the value is the corresponding result. `BatchLoader` relies on positional key/value order, whereas `MappedBatchLoader` relies on `Map` lookups. In Spring for GraphQL, `BatchLoaderRegistry` manages loaders per request, helping resolvers curb N+1 while preserving accurate mappings, scoped caching, and clear handling of missing data.
