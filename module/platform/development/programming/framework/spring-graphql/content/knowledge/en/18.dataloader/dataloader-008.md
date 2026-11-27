# DataLoader method argument in Spring for GraphQL

In Spring for GraphQL, a `@SchemaMapping` method can accept `DataLoader<K, V>` directly as a method argument. Spring looks up the DataLoader registered for the current request, injects it into the method, and allows the resolver to call `load(key)` to fetch related data in a way that batches multiple requests together.

This approach is commonly used to load relationships from parent objects—for example, when each `Book` has an `authorId` and the `Book.author` field needs to return an `Author`. When a query fetches many books, each resolver calls `DataLoader.load(authorId)`. DataLoader batches the keys, invokes the batch loader, and caches results within the request scope, curbing N+1 queries.

## 1. Why use a DataLoader method argument?

Suppose the schema defines these types:

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

Client query:

```graphql
query {
    books {
        id
        title
        author {
            name
        }
    }
}
```

If the `Book.author` resolver calls the repository separately for each book, a query fetching 100 books can generate one query for the list of books and 100 additional queries for the authors. This is the N+1 problem.

DataLoader lets a resolver request data by key without loading immediately. `load()` calls within the same execution batch are grouped together; the batch loader receives the set of keys and loads data via a single appropriate operation, such as a `WHERE id IN (...)` query.

In Spring for GraphQL, you register the batch loading function via `BatchLoaderRegistry`, then declare `DataLoader<K, V>` in the `@SchemaMapping` method signature. Spring automatically locates and injects the matching DataLoader.

## 2. How the DataLoader method argument works

The process typically unfolds in these steps:

1. The application registers a batch loading function with `BatchLoaderRegistry`.
2. When a GraphQL request starts, Spring instantiates the corresponding DataLoaders in that request's `DataLoaderRegistry`.
3. The `Query.books` resolver returns the list of `Book`s.
4. GraphQL invokes the `Book.author` resolver for each book. Spring injects the corresponding `DataLoader` into each call.
5. The resolver calls `loader.load(book.authorId())`. Keys are queued instead of loaded individually at the moment of the call.
6. GraphQL dispatches the DataLoader; the batch loader receives the keys to load and queries data in bulk.
7. DataLoader completes the futures returned by `load()`, and GraphQL continues resolving the `Author.name` field.

```text
Query.books
    |
    +-- Book(1, authorId=10) --+
    +-- Book(2, authorId=20) --+--> DataLoader.load(key)
    +-- Book(3, authorId=10) --+          |
                                         v
                              BatchLoaderRegistry
                                         |
                                         v
                              Batch loader receives keys
                                  {10, 20}
                                         |
                                         v
                              One batch load
                                         |
                                         v
                              Map<id, Author>
                                         |
                                         v
                              Complete Futures
```

If keys repeat, DataLoader's per-request cache avoids loading the same key twice. In the example above, two books with `authorId = 10` normally require only one load entry for that key.

## 3. Registering a batch loader with `BatchLoaderRegistry`

The Spring Boot Starter provides a `BatchLoaderRegistry` bean. You can inject this bean into a configuration or component to register batch loaders.

Suppose the Java models are:

```java
public record Book(Long id, String title, Long authorId) {}

public record Author(Long id, String name) {}
```

Service accessing authors by a set of IDs:

```java
@Service
class AuthorService {

    private final AuthorRepository authorRepository;

    AuthorService(AuthorRepository authorRepository) {
        this.authorRepository = authorRepository;
    }

    Flux<Author> findAllByIds(Set<Long> ids) {
        return authorRepository.findAllById(ids);
    }
}
```

Registering a mapped batch loader:

```java
@Configuration
class GraphQlDataLoaderConfig {

    GraphQlDataLoaderConfig(
            BatchLoaderRegistry registry,
            AuthorService authorService) {

        registry.forTypePair(Long.class, Author.class)
            .registerMappedBatchLoader((authorIds, environment) ->
                authorService.findAllByIds(authorIds)
                    .collectMap(Author::id)
            );
    }
}
```

`forTypePair(Long.class, Author.class)` declares a `Long` key and an `Author` value. `registerMappedBatchLoader` accepts a set of keys and returns `Mono<Map<K, V>>`. In this example, the repository loads authors for the ID set and `collectMap(Author::id)` builds a map keyed by author ID.

A mapped batch loader fits well when some keys may have no corresponding value. The map can omit unfound keys; DataLoader returns an absent result for those keys. If you need to preserve input order and represent every slot, use `registerBatchLoader` returning a list/`Flux` matching the exact key order and count, with `null` at unfound positions.

Do not manually create a `DataLoaderRegistry` per resolver. `BatchLoaderRegistry` is Spring for GraphQL's central registration point; Spring uses it to register DataLoaders per request and supports sharing `GraphQLContext` as well as context propagation for batch loaders.

## 4. Accepting `DataLoader` in `@SchemaMapping`

After registering a batch loader for `Long` and `Author`, a resolver can declare `DataLoader<Long, Author>` in its method signature:

```java
@Controller
class BookController {

    private final BookService bookService;

    BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    List<Book> books() {
        return bookService.findAll();
    }

    @SchemaMapping(typeName = "Book", field = "author")
    CompletableFuture<Author> author(
            Book book,
            DataLoader<Long, Author> authorLoader) {

        return authorLoader.load(book.authorId());
    }
}
```

Here:

- `Book book` is the parent source of the `Book.author` field.
- `DataLoader<Long, Author> authorLoader` is the DataLoader Spring injects based on generic types.
- `authorLoader.load(book.authorId())` returns `CompletableFuture<Author>`.
- `@SchemaMapping` returns that future to GraphQL; there is no need to call `get()`, `join()`, or `block()`.

Spring's DataLoader argument resolver retrieves the DataLoader from the current field's `DataFetchingEnvironment`. With default configuration via `forTypePair`, the DataLoader name is inferred from the full class name of the value type—here, `Author`. Thus, the generic type `DataLoader<Long, Author>` is usually enough for Spring to find the right loader without specifying a name.

Main imports in the example:

```java
import org.dataloader.DataLoader;
import org.springframework.graphql.data.method.annotation.SchemaMapping;
import org.springframework.graphql.execution.BatchLoaderRegistry;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import java.util.Set;
import java.util.concurrent.CompletableFuture;
```

## 5. How Spring resolves DataLoader from a method argument

Spring for GraphQL uses `DataLoaderMethodArgumentResolver` to resolve parameters of type `DataLoader`. Loader lookup relies on:

1. **Full class name of the generic value type:** for `DataLoader<Long, Author>`, the default registration key derives from the fully qualified class name of `Author`.
2. **Method parameter name:** used as a fallback key or when the loader is registered with a custom name.

With `registry.forTypePair(Long.class, Author.class)`, Spring by default generates the name from the value type `Author`. Therefore, in many cases you only need:

```java
@SchemaMapping
CompletableFuture<Author> author(Book book, DataLoader<Long, Author> loader) {
    return loader.load(book.authorId());
}
```

The variable name `loader` does not need to match the `Author` class name because Spring can resolve the loader from the generic value type. However, the generics must match the key and value types used at registration.

If you declare `DataLoader<Long, Book>` while the loader was registered for `Author`, Spring looks up by value type `Book` and fails to find the right loader. Check both generic type arguments whenever a DataLoader is not found.

## 6. Customizing DataLoader names

When you need multiple loaders with the same value type or want a registration name that clearly expresses intent, use `forName("...")` or call `withName("...")` on the registration spec returned by `forTypePair(...)`.

Example registering under the name `authorsById`:

```java
registry.<Long, Author>forName("authorsById")
    .registerMappedBatchLoader((authorIds, environment) ->
        authorService.findAllByIds(authorIds)
            .collectMap(Author::id)
    );
```

In `@SchemaMapping`, the `DataLoader` parameter name must match the registered name:

```java
@SchemaMapping(typeName = "Book", field = "author")
CompletableFuture<Author> author(
        Book book,
        DataLoader<Long, Author> authorsById) {

    return authorsById.load(book.authorId());
}
```

In this case, `authorsById` is the parameter name Spring uses to locate the `authorsById` loader. If you rename the parameter without updating the registration name, Spring may fail to find the DataLoader. When relying on custom names, ensure parameter names are preserved in Java compilation metadata; configuring the compiler with `-parameters` lets Spring read parameter names.

If you have no need for a custom name, prefer `forTypePair` and default generic-type lookup to minimize reliance on parameter names.

## 7. DataLoader returns an asynchronous type

`DataLoader.load(key)` returns `CompletableFuture<V>`. Thus, `@SchemaMapping` can return `CompletableFuture<Author>` directly:

```java
@SchemaMapping
CompletableFuture<Author> author(Book book, DataLoader<Long, Author> loader) {
    return loader.load(book.authorId());
}
```

Do not wait on the future inside the resolver:

```java
@SchemaMapping
Author author(Book book, DataLoader<Long, Author> loader) {
    return loader.load(book.authorId()).join();
}
```

The second snippet blocks execution and can prevent GraphQL from dispatching batches at the proper time. Return the future to GraphQL so the execution engine can coordinate asynchronous tasks.

You can transform the future's result using `thenApply` when a synchronous conversion is needed:

```java
@SchemaMapping
CompletableFuture<AuthorView> author(Book book, DataLoader<Long, Author> loader) {
    return loader.load(book.authorId())
        .thenApply(author -> new AuthorView(author.id(), author.name()));
}
```

If you need to chain another asynchronous step returning a `CompletionStage`, use `thenCompose` instead of creating nested futures. Preserve errors in the pipeline so GraphQL processes them via exception resolution.

## 8. Batching, caching, and request scope

DataLoader offers two major benefits:

**Batching:** `load(key)` calls are grouped so the batch loader processes multiple keys at once. This reduces repository or service calls when a query has many parent objects.

**Per-request caching:** by default, DataLoader caches results by key for the lifetime of the GraphQL request. If multiple fields request the same author ID, subsequent calls can reuse the already-loaded result.

This cache is not application-wide. The next request gets its own `DataLoaderRegistry` and cache. Therefore, data is never automatically shared across different users or requests.

When a mutation updates an entity and subsequent fields read that entity within the same request, consider clearing or updating the relevant DataLoader cache using operations like `clear(key)` or `prime(key, value)`. Otherwise, DataLoader may return the value cached before the mutation within the same request.

If data depends on the user, tenant, or permissions, ensure the batch loader uses the proper `GraphQLContext`/security context and that keys/caches do not mix results across different access scopes. For data differentiated by filters or tenants, you may need to include those attributes in a composite key or handle them via appropriate context.

## 9. When to use a DataLoader method argument vs `@BatchMapping`?

`@BatchMapping` is a shorthand when a field resolver simply loads a relationship for a list of parent objects. For example:

```java
@BatchMapping(typeName = "Book", field = "author")
Mono<Map<Book, Author>> authors(List<Book> books) {
    Set<Long> authorIds = books.stream()
        .map(Book::authorId)
        .collect(Collectors.toSet());

    return authorService.findAllByIds(authorIds)
        .collectMap(Author::id)
        .map(authorsById -> {
            Map<Book, Author> result = new HashMap<>();
            for (Book book : books) {
                Author author = authorsById.get(book.authorId());
                if (author != null) {
                    result.put(book, author);
                }
            }
            return result;
        });
}
```

For this straightforward case, you do not need to write a `DataLoader` method argument and `BatchLoaderRegistry` manually. Spring creates the batch loader and data fetcher for the corresponding field. Since `Book` serves as the map key, the `Book` type needs stable `equals` and `hashCode`; Java records automatically generate both methods from their record components.

A DataLoader method argument is better suited when a resolver needs information specific to each field invocation, such as:

- `@Argument` to filter data per parent.
- `GraphQLContext`, principal, or local context.
- Multiple loaders or complex loading workflows.
- Explicitly needing to call `load`, `loadMany`, `clear`, or `prime`.
- Wanting to reuse a single loader across multiple distinct `@SchemaMapping` methods.

Do not pick manual DataLoader solely because it is more general. For simple relationships, `@BatchMapping` typically requires less boilerplate. When you need fine-grained loading control per field invocation, a DataLoader method argument is more flexible.

## 10. Testing DataLoader method arguments

Tests should verify both the returned data and that the batch loader is called with the expected key set. Slice test example:

```java
@GraphQlTest(BookController.class)
@Import(GraphQlDataLoaderConfig.class)
class BookDataLoaderTests {

    @Autowired
    GraphQlTester graphQlTester;

    @MockitoBean
    BookService bookService;

    @MockitoBean
    AuthorService authorService;

    @Test
    void batchesAuthorsForMultipleBooks() {
        given(bookService.findAll()).willReturn(List.of(
            new Book(1L, "Book A", 10L),
            new Book(2L, "Book B", 20L),
            new Book(3L, "Book C", 10L)
        ));

        given(authorService.findAllByIds(anySet())).willReturn(Flux.just(
            new Author(10L, "Author A"),
            new Author(20L, "Author B")
        ));

        GraphQlTester.Response response = graphQlTester.document("""
                query {
                    books {
                        id
                        author {
                            name
                        }
                    }
                }
                """)
            .execute();

        response.path("books[0].author.name").entity(String.class).isEqualTo("Author A");
        response.path("books[1].author.name").entity(String.class).isEqualTo("Author B");
        response.path("books[2].author.name").entity(String.class).isEqualTo("Author A");

        then(authorService).should(times(1)).findAllByIds(Set.of(10L, 20L));
    }
}
```

This is an illustrative example; imports, Mockito/BDDMockito static imports, models, services, and SDL must be provided in the test context. `@Import` brings the batch loader registration configuration into the test. Depending on your Spring Boot version, the mock bean annotation may be `@MockitoBean` or `@MockBean`.

The test includes three books but only two distinct author IDs. Assertions verify that all three `author` fields resolve accurately and the batch service is called once with the key set `{10, 20}`. In real tests, you can also add a case where an author is not found and verify the nullable field returns `null`.

## 11. Common mistakes

**Batch loader not registered.** Declaring `DataLoader<K, V>` in a controller does not create a loader automatically. It must be registered with `BatchLoaderRegistry` before requests execute.

**Generic type mismatch.** `DataLoader<Long, Author>` must match the registered key type and value type. In particular, the default loader name is inferred from the value type.

**Using a custom name with a mismatched parameter name.** With `forName("authorsById")`, the `DataLoader` parameter in the mapping method must be named `authorsById` for the resolver to find the right loader.

**Returning a batch list in the wrong order.** With `registerBatchLoader`, result count and order must match the key list. If results are missing for some keys, use a mapped batch loader or return `null` at the exact positions.

**Using `join()` or `get()` inside a resolver.** Waiting synchronously on the future breaks asynchronicity and hinders batching. Return `CompletableFuture` directly.

**Calling `dispatch()` manually inside a controller.** GraphQL execution manages DataLoader dispatching. Resolvers only need to call `load()` or `loadMany()`.

**Creating an application-wide shared cache.** DataLoader is designed with per-request caching. Never store a singleton `DataLoader` in a controller/service to share across multiple requests.

**Using DataLoader for overly simple relationships.** If you only need to batch-load by parent list without custom arguments/context, `@BatchMapping` is usually cleaner.

## Conclusion

DataLoader method arguments let Spring for GraphQL inject `DataLoader<K, V>` directly into `@SchemaMapping`. Register batch loading functions via `BatchLoaderRegistry`, let Spring instantiate per-request DataLoaders, and then call `load(key)` and return `CompletableFuture<V>` to GraphQL. With `forTypePair`, Spring defaults to looking up the loader by the value type's full class name; with custom names, the parameter name must match the registered name. Understanding batching, per-request caching, batch return shapes, and differences from `@BatchMapping` helps eliminate N+1 while keeping resolvers easy to test.

## References

- [Spring for GraphQL — Request Execution: Batch Loading](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring for GraphQL — Annotated Controllers: DataLoader](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL API — `BatchLoaderRegistry`](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/execution/BatchLoaderRegistry.html)
