# When to use BatchLoaderRegistry instead of @BatchMapping

In Spring for GraphQL, both `@BatchMapping` and `BatchLoaderRegistry` help batch data loading to reduce N+1. They are not entirely competing mechanisms: **`@BatchMapping` is a concise declaration for a specific field, whereas `BatchLoaderRegistry` lets you register DataLoaders explicitly so resolvers can proactively load by key and reuse a loader across multiple places.**

For a simple relationship like `Book.author`, a single `@BatchMapping` method is usually enough. When the same type of data is loaded from multiple parent types, when a resolver needs to invoke a loader by ID or composite key, when you need fine control over cache/options/context, or when one loader is shared across multiple fields, registering via `BatchLoaderRegistry` is usually a better fit.

## 1. @BatchMapping already uses DataLoader under the hood

Suppose the schema has a list of books and an author field:

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

If every resolution of `Book.author` calls the repository individually, a query fetching 30 books can execute one query for books and 30 queries for authors. `@BatchMapping` allows receiving all source objects in a single invocation and loading authors in bulk:

```java
@Controller
public class BookController {

    private final AuthorService authorService;

    public BookController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @BatchMapping(typeName = "Book", field = "author")
    public Map<Book, Author> authors(List<Book> books) {
        Set<Long> authorIds = books.stream()
            .map(Book::authorId)
            .collect(Collectors.toSet());

        Map<Long, Author> authorsById = authorService.findAllByIds(authorIds);
        Map<Book, Author> result = new HashMap<>();
        for (Book book : books) {
            result.put(book, authorsById.get(book.authorId()));
        }
        return result;
    }
}
```

Spring for GraphQL registers the corresponding batch mechanism for the `Book.author` field. At runtime, requests are coordinated through DataLoader. Thus, using `@BatchMapping` does not mean bypassing DataLoader; the annotation hides loader registration and result-to-source mapping.

`@BatchMapping` typically receives `List<Book>` and can return `Map<Book, Author>` to match by source, or return `List<Author>` whose result order matches the input source order. When returning a list, the batch method must guarantee exact element count and order; when results are fetched by ID and the repository does not preserve order, a Map is usually easier to control.

## 2. What part does BatchLoaderRegistry solve?

`BatchLoaderRegistry` is Spring for GraphQL's abstraction for registering batch loader definitions. Spring uses those definitions to create `DataLoader`s and place them into the `DataLoaderRegistry` for each GraphQL execution/request.

Three components should be distinguished:

| Component | Role |
| --- | --- |
| `BatchLoaderRegistry` | Where the application registers how to load data in batches within Spring configuration |
| `DataLoaderRegistry` | Runtime registry holding the DataLoader instances for a single GraphQL execution |
| `DataLoader<K, V>` | API where a resolver calls `load(key)` to obtain a future for the value; the loader batches keys and caches per configuration |

`BatchLoaderRegistry` is typically managed by Spring as a bean used to register loaders. Actual DataLoader instances and caches are created per request. Never manually create a singleton DataLoader and share it across requests; the cache could retain stale data or leak data across users/tenants.

Example registering a mapped batch loader:

```java
@Configuration
public class DataLoaderConfiguration {

    public DataLoaderConfiguration(
            BatchLoaderRegistry registry,
            AuthorService authorService) {

        registry.forTypePair(Long.class, Author.class)
            .registerMappedBatchLoader((authorIds, environment) ->
                authorService.findAllByIdsAsync(authorIds));
    }
}
```

`forTypePair(Long.class, Author.class)` describes the key/value types. The batch function receives a set of author IDs and returns `CompletionStage<Map<Long, Author>>`. The Map does not need to match input key order because each result is matched by key. If an ID is absent from the Map, the loader has no value for that key; determine whether the GraphQL field allows `null`.

The resolver accepts the DataLoader and loads by ID:

```java
@SchemaMapping(typeName = "Book", field = "author")
public CompletableFuture<Author> author(
        Book book,
        DataLoader<Long, Author> authorLoader) {
    return authorLoader.load(book.authorId());
}
```

The resolver does not call the repository directly and does not call `join()` on the future. GraphQL Java coordinates dispatching keys during execution; Spring integrates DataLoader with the request lifecycle.

## 3. Case 1: Multiple parent types need the same data

This is the most common reason to use `BatchLoaderRegistry`. Suppose both `Book` and `Review` have an author. Using only `@BatchMapping`, you would write two separate batch methods:

```java
@BatchMapping(typeName = "Book", field = "author")
public Map<Book, Author> bookAuthors(List<Book> books) {
    // Load authors for the list of Books.
}

@BatchMapping(typeName = "Review", field = "author")
public Map<Review, Author> reviewAuthors(List<Review> reviews) {
    // Load authors for the list of Reviews.
}
```

Both methods perform the same domain task: loading `Author` by ID. However, each mapping can create a separate batch. If the same GraphQL operation requests both `Book.author` and `Review.author`, we want author keys batched into one shared loader.

Register a single loader for `Long -> Author`:

```java
@Configuration
public class AuthorLoaderConfiguration {

    public AuthorLoaderConfiguration(
            BatchLoaderRegistry registry,
            AuthorService authorService) {

        registry.forTypePair(Long.class, Author.class)
            .registerMappedBatchLoader((authorIds, environment) ->
                authorService.findAllByIdsAsync(authorIds));
    }
}
```

Two resolvers in two different controllers share that loader:

```java
@Controller
public class BookController {

    @SchemaMapping(typeName = "Book", field = "author")
    public CompletableFuture<Author> author(
            Book book,
            DataLoader<Long, Author> authorLoader) {
        return authorLoader.load(book.authorId());
    }
}
```

```java
@Controller
public class ReviewController {

    @SchemaMapping(typeName = "Review", field = "author")
    public CompletableFuture<Author> author(
            Review review,
            DataLoader<Long, Author> authorLoader) {
        return authorLoader.load(review.authorId());
    }
}
```

When resolvers invoke the same loader during one execution, author IDs can be grouped into the same batch. If multiple objects share the same ID, request-scoped caching can also prevent loading the same author multiple times. This benefit is difficult to achieve when each parent field has its own independent batch mapping.

## 4. Case 2: Resolver needs to load by key rather than by source object

`@BatchMapping` is designed around one field and its list of source objects. Meanwhile, many resolvers need to load data by an independent key, such as:

- Fetching an `Author` by `authorId`.
- Fetching `Inventory` by `productId`.
- Fetching permissions by `userId` and `resourceId`.
- Fetching an exchange rate by currency pair.
- Fetching a translation by `messageKey` and `locale`.

For example, `Book` and `Review` both have `authorId`, yet the loader only cares about the ID. The resolver does not need a separate batch method to map each source object type; it simply calls `authorLoader.load(authorId)`.

For composite keys, use a key type with stable `equals` and `hashCode`, such as a Java record:

```java
public record LocalizedKey(String messageKey, Locale locale) {
}
```

Register the loader by key/value types:

```java
registry.forTypePair(LocalizedKey.class, String.class)
    .registerMappedBatchLoader((keys, environment) ->
        translationService.findAllAsync(keys));
```

The resolver can construct the key from source data and context:

```java
@SchemaMapping(typeName = "Product", field = "displayName")
public CompletableFuture<String> displayName(
        Product product,
        DataFetchingEnvironment environment,
        DataLoader<LocalizedKey, String> translationLoader) {

    Locale locale = environment.getGraphQlContext().get("locale");
    return translationLoader.load(
        new LocalizedKey(product.messageKey(), locale));
}
```

In this case, DataLoader caches by both `messageKey` and `locale`, since two locales can return different values. Java records provide component-based equality, making them suitable as keys. If a mutable class or a key with improper equality is used, caching and result matching can break.

## 5. Case 3: Same loader used across multiple fields or resolver levels

A loader can be called from multiple places within the same operation, not just from a single parent-child relationship. For example, a query fetches books, fetches an individual author, and fetches dashboard metrics referencing an author:

```graphql
type Query {
    book(id: ID!): Book
    author(id: ID!): Author
    dashboard: Dashboard!
}

type Book {
    author: Author
}

type Dashboard {
    featuredAuthor: Author
}
```

If resolvers need to load the same `Author` by ID, using a shared DataLoader unifies batching and caching within the execution. The root resolver `author(id:)`, the `Book.author` resolver, and the `Dashboard.featuredAuthor` resolver can all call `load(id)`.

This is useful when fields are separated across domains/controllers while still sharing a data source. The batch loader centralizes query logic; resolvers simply turn input data into keys and return futures.

Note that batching only happens among `load` calls dispatched in the same execution cycle. Fields at different nesting levels may form batches in different rounds. DataLoader does not combine every key across the entire query into a single query regardless of execution structure.

## 6. Case 4: Need control over DataLoaderOptions

`@BatchMapping` suits simple configurations. When finer DataLoader control is needed, registering through `BatchLoaderRegistry` lets you configure `DataLoaderOptions` where the loader is registered.

Example limiting keys per batch and enabling caching:

```java
registry.forTypePair(Long.class, Author.class)
    .registerMappedBatchLoader(
        (authorIds, environment) -> authorService.findAllByIdsAsync(authorIds),
        options -> options
            .setMaxBatchSize(100)
            .setCachingEnabled(true)
    );
```

Options to consider:

| Need | How to configure or design |
| --- | --- |
| Limit the number of IDs sent in one query | `maxBatchSize` to split large key sets into smaller batches |
| Avoid loading the same key multiple times in one request | Enable key caching; this is usually the default behavior |
| Keys with special equality rules | Use an immutable key type with proper `equals`/`hashCode` or configure a cache key function |
| Batch loader needs context | Accept `BatchLoaderEnvironment` and read context passed into execution |
| Need cache control after mutation | Use `clear`, `clearAll`, or `prime` on the current DataLoader |

Method names and configuration overloads may depend on the version of GraphQL Java/Spring for GraphQL your project uses. Check the API of the dependency managed by Spring Boot when implementing.

`maxBatchSize` does not limit how many objects a client is allowed to request. It splits collected keys into smaller batches. Pagination and query complexity still must be enforced at the schema/API layer.

## 7. Case 5: Need to manipulate cache after mutation

DataLoader caches results by key within a single execution. If a mutation updates an `Author` and another resolver in the same execution reloads the same ID, the loader may return the stale cached object.

With an explicit DataLoader, the mutation resolver can clear the cache and prime the new result:

```java
@MutationMapping
public Author updateAuthor(
        @Argument("input") UpdateAuthorInput input,
        DataLoader<Long, Author> authorLoader) {

    Author updated = authorService.update(input);
    authorLoader.clear(updated.id());
    authorLoader.prime(updated.id(), updated);
    return updated;
}
```

`clear(id)` removes the old result from the current loader's cache. `prime(id, updated)` inserts the new result if the key is not present yet. Clearing first is typically necessary because `prime` does not overwrite an existing key.

This is only the cache inside the current execution's DataLoader. If the application has a service-level or distributed cache, separate invalidation is required. If a mutation modifies data cached by a different loader, update or clear that specific loader.

When using only `@BatchMapping`, manipulating the DataLoader instance and cache is not as direct as injecting DataLoader. If a use case frequently needs clear/prime or invoking the loader from multiple resolvers, that is a strong signal to register the loader explicitly via `BatchLoaderRegistry`.

## 8. Case 6: Need to pass context into the batch loader

Batch queries sometimes depend on an authenticated tenant, user, locale, or policy. For example, for the same `authorId`, different tenants might see different data fields. In that case, the batch loader needs the proper context to query within the right scope.

`BatchLoaderRegistry` supports registering batch loaders that accept `BatchLoaderEnvironment`. GraphQL execution context can be passed to the loader through Spring for GraphQL/GraphQL Java's context mechanism. Obtain the tenant or principal from server-authenticated context, never trusting an arbitrary tenant value supplied by the client.

Illustrative example:

```java
registry.forTypePair(Long.class, Author.class)
    .registerMappedBatchLoader((authorIds, environment) -> {
        GraphQLContext graphQLContext = environment.getContext();
        TenantId tenantId = graphQLContext.get("tenantId");
        return authorService.findVisibleAuthors(tenantId, authorIds);
    });
```

This illustrative snippet assumes the application placed `tenantId` in the GraphQL context before execution. Use the exact context type and retrieval method matching your GraphQL Java/Spring for GraphQL version. Do not retrieve context and then skip authorization in the service; the batch query must still apply tenant conditions and access permissions for every key.

DataLoader caches by key. If a single execution can span multiple security scopes, the key must include all factors affecting the result, or the loader must be confined to a consistent scope. Never share loaders/caches across requests or tenants.

## 9. Registering loaders by type pair vs. by name

`BatchLoaderRegistry` supports registering loaders based on a key/value type pair. This is the natural choice when a type pair has only one corresponding loader:

```java
registry.forTypePair(Long.class, Author.class)
    .registerMappedBatchLoader((ids, environment) ->
        authorService.findAllByIdsAsync(ids));
```

A resolver can accept `DataLoader<Long, Author>` directly as an annotated controller parameter. Spring resolves the loader based on the generic key/value types.

If the application needs multiple loaders with the same key/value types for different purposes, registering by name distinguishes them. Resolvers can then fetch the loader from `DataFetchingEnvironment` by its registered name:

```java
registry.forName("visibleAuthors")
    .registerMappedBatchLoader((authorIds, environment) ->
        authorService.findVisibleAuthors(authorIds));

DataLoader<Long, Author> loader =
    environment.getDataLoader("visibleAuthors");
```

The loader name must match between registration and lookup. Use custom names only when you genuinely need multiple loaders of the same types or distinct policies; otherwise, registering by type pair and injecting by type is usually simpler. Specific named-registration APIs and configuration must match the Spring for GraphQL version in your project.

## 10. When should you still choose @BatchMapping?

Using DataLoader does not mean you always need manual registration. `@BatchMapping` is usually the most readable choice when:

- Batching serves only a single field, such as `Book.author`.
- The natural key is the field's source object.
- The resolver receives a list of source objects and returns the corresponding Map/list.
- There is no need to share the loader with another field or parent type.
- There is no need to access DataLoader directly for clear/prime or use elsewhere.
- Default caching and batch size configuration meet requirements.

For example, if only `Book.reviews` needs to load a list of reviews for each book, a single `@BatchMapping` returning `Map<Book, List<Review>>` is clear enough. Creating an explicit loader just to replace a simple mapping adds extra components and names to manage.

## 11. Comparing the two approaches

| Criterion | `@BatchMapping` | `BatchLoaderRegistry` |
| --- | --- | --- |
| Abstraction level | Direct mapping for one GraphQL field | Registers DataLoader by key/value or name |
| Batch input | List of the field's source objects | Set of keys from resolver `load(key)` calls |
| Result mapping | Source-to-value Map or ordered list | Loader returns values by key; mapped loader returns Map by key |
| Sharing across fields/types | Usually needs a separate batch mapping per field | Can share a single loader within the same execution |
| Composite or source-independent keys | May require adapting through the source object | More natural because resolvers construct keys explicitly |
| Use in root and nested resolvers | Tied to one field mapping | Can be called from many different resolvers |
| Cache clear/prime | Not directly manipulated like an injected DataLoader | Can inject DataLoader and manipulate cache |
| Custom options/context | Suited for simple configuration | More explicit control at loader registration |
| Code complexity | Less boilerplate | Requires loader registration and calling `load` in resolvers |

Both `@BatchMapping` and `BatchLoaderRegistry` rely on DataLoader. The main difference is how they are modeled and the level of control: one describes a field's batch, while the other describes a key-based loader usable across multiple locations.

## 12. Key invariants when using BatchLoaderRegistry

**Keep the registry request-scoped.** Spring manages DataLoader instances per GraphQL execution. Register only loader definitions in configuration beans; never store a DataLoader instance in a static field or singleton and share it.

**Do not block futures.** `load(key)` returns a future. Return the future directly from the resolver without calling `join()` or `get()`; blocking negates asynchronous benefits and can cause thread starvation.

**Ensure results match keys.** With `BatchLoader`, the list must match the exact order of input keys. With `MappedBatchLoader`, the Map must rely on proper key equality. Choose mapped loaders when data source ordering is not guaranteed.

**Control batch size.** A large query can generate a huge number of keys. Limit batch size according to database and downstream service limits, while still enforcing pagination/depth/complexity at the GraphQL layer.

**Distinguish missing data from batch failure.** Not finding a key can be a valid result; a database or HTTP failure is an execution error. Do not convert every exception into an empty Map, as clients will misinterpret the data.

**Scope caches safely.** If results depend on tenant or principal, batch queries and keys/caches must reflect the proper security scope. DataLoader caching is not a substitute for authorization.

## 13. Testing shared loaders

An important test for `BatchLoaderRegistry` is proving that two parent types can call the same loader and have their keys batched within the same execution. For example, an operation requesting both books and reviews, where both fetch authors:

```graphql
query {
    books {
        title
        author {
            id
            name
        }
    }
    reviews {
        content
        author {
            id
            name
        }
    }
}
```

With `GraphQlTester`, verify both response branches. Use a spy/mock on `AuthorService` to verify the batch loader receives the combined set of IDs per execution instead of each resolver issuing a separate query. The exact batch count can be greater than one if dispatches are split by execution level or `maxBatchSize`; tests should assert call counts consistent with configuration rather than assuming an entire query always produces exactly one batch.

Cases to test:

- `Book.author` and `Review.author` share the same loader within one request.
- Two objects with the same author ID do not trigger two loads when caching is enabled.
- Two separate GraphQL requests have separate DataLoaders/caches.
- Missing keys return `null` according to the schema.
- Batch service errors translate into appropriate GraphQL errors.
- `maxBatchSize` splits large key sets according to the configured limit.
- `clear` and `prime` update the cache after a mutation in the current execution.
- A tenant or principal cannot read data outside its authorized scope.

Example testing a single field with `GraphQlTester`:

```java
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
```

To verify that a loader is actually shared across two parent types, send one operation containing both branches in the same document and verify the batch service, rather than running two separate operations and comparing total call counts.

## 14. Common pitfalls

| Symptom | Cause | Solution |
| --- | --- | --- |
| DataLoader not found on inject | Key/value generic types do not match registered loader | Check `forTypePair` and controller parameter generics |
| Ambiguity with multiple loaders of same types | Multiple loaders registered with same key/value types without distinction | Use named loaders and retrieve via `DataFetchingEnvironment` |
| Batches still run separately per field | Each field has its own loader or resolver queries directly | Share one loader by key/value type within the same execution |
| Using `@BatchMapping` but wanting to call from root resolver | Annotation is bound to a specific field | Register the loader explicitly via `BatchLoaderRegistry` |
| Results matched to wrong objects | BatchLoader returns wrong order or Map uses unstable keys | Use a mapped loader or immutable keys with proper equality |
| Cache returns stale data after mutation | Loader cached the key before the update | Inject DataLoader and `clear`/`prime` the affected key |
| Cross-tenant data leak | Cache/key ignores security scope or loader is shared | Keep registry request-scoped and apply tenant filters |
| Query still produces too many queries | Batch size, dispatch level, or another resolver bypasses loader | Measure batch calls and inspect every field path |

## 15. How to decide

Start from the shape of your use case. If you have a single nested field where the source object is the natural key and you just need to batch that field's source objects, choose `@BatchMapping`. If resolvers need to load by ID/key, if multiple fields or parent types need to share data, or if you need explicit control over DataLoader/caching/context/options, choose `BatchLoaderRegistry`.

In Spring for GraphQL, `BatchLoaderRegistry` is where loaders are registered, while `DataLoaderRegistry` holds the loader instances for the current execution. `@BatchMapping` still uses DataLoader under the hood and is a clean choice for simple field relationships. Choosing the right level of abstraction avoids N+1 while keeping code readable, testable, and safe regarding request-scoped caching.
