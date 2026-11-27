# Testing DataLoader in Spring for GraphQL

DataLoader batches multiple data loads into a single call and caches results within the scope of a single GraphQL execution. When testing, verify both behaviors: multiple fields requesting data are batched to reduce N+1 queries, and one execution's cache is never shared with another request.

Spring for GraphQL integrates DataLoader via `BatchLoaderRegistry` and `@BatchMapping`. `GraphQlTester` lets you test this behavior at the GraphQL operation level: send a query with multiple parent objects, assert the child data, and verify the batch service was called the expected number of times with the expected set of keys. You can combine this with direct GraphQL Java DataLoader unit tests to verify caching, dispatching, and batch loaders independently of Spring.

## 1. What to test

Suppose a query returns multiple books and each book needs its author details. If the resolver queries a repository separately for each book, the application can suffer from N+1 queries. DataLoader groups the keys together and invokes a batch loader.

Key behaviors to verify:

| Behavior | What to assert |
| --- | --- |
| Batching | Multiple keys are processed in one batch loader call when in the same dispatch batch |
| Execution-scoped caching | Loading the same key multiple times requires only one lookup under default cache policy |
| Request isolation | Two independent GraphQL executions have separate DataLoader/cache instances |
| Result mapping | Each parent receives the child object matching its key |
| Missing key | Keys absent from the mapped result are handled according to schema nullability and contract |
| Batch error | Errors from the batch loader become GraphQL errors with the right path |
| Context | Execution tenant/principal/locale is passed properly to the batch loader |
| Invalidation | Mutations clear or update cache entries within the execution when needed |

Do not merely assert that the query returns the right JSON. A resolver without DataLoader can return identical data while firing a separate query per parent. Verify the service/repository call count or the number of batches and actual keys passed.

## 2. Designing the Book and Author example

The schema has a query returning a list of books and a child `author` field:

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

Java models:

~~~java
public record Book(String id, String title, Long authorId) {}

public record Author(Long id, String name) {}
~~~

`Book.authorId` is the foreign key referencing the author. The `Book.author` field is resolved separately via DataLoader, while the root query only loads the list of books.

Service contract:

~~~java
import java.util.List;
import java.util.Map;
import java.util.Set;

import reactor.core.publisher.Mono;

public interface BookService {
    List<Book> findAll();
}

public interface AuthorService {
    Mono<Map<Long, Author>> findByIds(Set<Long> authorIds);
}
~~~

The mapped batch loader takes a set of author IDs and returns a map from ID to `Author`. Using `Set` makes it clear that keys are batched and deduplicated within a batch.

## 3. Registering a DataLoader via BatchLoaderRegistry

Register the batch loader once in application configuration:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.execution.BatchLoaderRegistry;

@Configuration(proxyBeanMethods = false)
public class AuthorDataLoaderConfiguration {

    public AuthorDataLoaderConfiguration(
            BatchLoaderRegistry registry,
            AuthorService authorService
    ) {
        registry.forTypePair(Long.class, Author.class)
                .registerMappedBatchLoader((authorIds, environment) ->
                        authorService.findByIds(authorIds)
                );
    }
}
~~~

`BatchLoaderRegistry` holds registration definitions. Spring uses those registrations to create a `DataLoaderRegistry` and DataLoader instances for each GraphQL execution. Thus, the registration configuration can be a singleton bean, while each DataLoader and its cache are scoped per execution.

## 4. Injecting DataLoader into a resolver

The root controller loads the list of books:

~~~java
import java.util.List;

import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookQueryController {

    private final BookService bookService;

    public BookQueryController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public List<Book> books() {
        return bookService.findAll();
    }
}
~~~

The `author` field resolver uses the Spring-supplied DataLoader:

~~~java
import java.util.concurrent.CompletableFuture;

import org.dataloader.DataLoader;
import org.springframework.graphql.data.method.annotation.SchemaMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookController {

    @SchemaMapping(typeName = "Book", field = "author")
    public CompletableFuture<Author> author(
            Book book,
            DataLoader<Long, Author> authorLoader
    ) {
        return authorLoader.load(book.authorId());
    }
}
~~~

The resolver only calls `load(key)` and returns the future. Do not call `dispatch()` manually inside controllers; GraphQL Java manages dispatching during execution. This matters when testing: run real GraphQL operations to observe batching rather than manually dispatching the loader in the resolver.

Batching also depends on the execution strategy. GraphQL Java uses `AsyncExecutionStrategy` to track in-flight fields and decide when to dispatch batches. Spring for GraphQL uses the async execution strategy by default. If an application replaces the execution strategy, verify that the new strategy still supports DataLoader batching; some executor-based strategies may dispatch each field individually and negate batching benefits. Integration tests checking batch service call counts help catch such regressions.

## 5. Testing batching with @GraphQlTest and GraphQlTester

`@GraphQlTest` creates a test slice for GraphQL controllers. Use `@MockitoBean` to replace services with mocks, then assert both the response and the batch service invocation count.

~~~java
import java.util.List;
import java.util.Map;
import java.util.Set;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;
import org.springframework.context.annotation.Import;
import org.springframework.graphql.test.tester.GraphQlTester;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import reactor.core.publisher.Mono;

import static org.mockito.BDDMockito.given;
import static org.mockito.Mockito.verify;

@GraphQlTest({BookQueryController.class, BookController.class})
@Import(AuthorDataLoaderConfiguration.class)
class DataLoaderBatchingTests {

    @Autowired
    GraphQlTester graphQlTester;

    @MockitoBean
    BookService bookService;

    @MockitoBean
    AuthorService authorService;

    @Test
    void batchesAuthorLoadsForAllBooks() {
        given(bookService.findAll()).willReturn(List.of(
                new Book("book-1", "GraphQL Basics", 10L),
                new Book("book-2", "Spring GraphQL", 10L),
                new Book("book-3", "DataLoader in Practice", 20L)
        ));

        given(authorService.findByIds(Set.of(10L, 20L)))
                .willReturn(Mono.just(Map.of(
                        10L, new Author(10L, "Ada"),
                        20L, new Author(20L, "Grace")
                )));

        graphQlTester.document("""
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
                """)
                .execute()
                .path("books[*].author.name")
                .entityList(String.class)
                .containsExactly("Ada", "Ada", "Grace");

        verify(authorService).findByIds(Set.of(10L, 20L));
    }
}
~~~

This test verifies three things:

1. GraphQL returns the right author for each book.
2. Two books sharing the same `authorId` do not cause the backend to load that author twice in the batch.
3. `AuthorService.findByIds` is invoked once with the key set `{10, 20}`.

If the resolver called `authorService.findById(...)` directly for each book, the call-count verification would fail even though the response data might still match. That is why you should assert both results and interactions with the batch service.

`@MockitoBean` is available in newer Spring Boot versions. On older versions, use that version's mock bean mechanism, such as `@MockBean`. Ensure the test slice loads the SDL schema, `BatchLoaderRegistry`, and the loader registration configuration.

## 6. Testing caching when the same key is loaded multiple times

In the example above, two books both request author ID `10`. The resolver calls `authorLoader.load(10L)` twice. With default caching enabled, DataLoader shares the same future for the same key within a single execution and the mapped batch loader receives each unique key only once.

To make GraphQL Java's caching semantics explicit, you can write a direct unit test for DataLoader:

~~~java
import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.atomic.AtomicInteger;

import org.dataloader.DataLoader;
import org.dataloader.DataLoaderFactory;
import org.dataloader.MappedBatchLoader;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class DataLoaderUnitTests {

    @Test
    void batchesKeysAndCachesDuplicateLoads() {
        AtomicInteger batchCalls = new AtomicInteger();

        MappedBatchLoader<Long, String> batchLoader = keys -> {
            batchCalls.incrementAndGet();
            return CompletableFuture.completedFuture(Map.of(
                    1L, "Ada",
                    2L, "Grace"
            ));
        };

        DataLoader<Long, String> dataLoader =
                DataLoaderFactory.newMappedDataLoader(batchLoader);

        CompletableFuture<String> first = dataLoader.load(1L);
        CompletableFuture<String> duplicate = dataLoader.load(1L);
        CompletableFuture<String> second = dataLoader.load(2L);

        dataLoader.dispatchAndJoin();

        assertThat(first.join()).isEqualTo("Ada");
        assertThat(duplicate.join()).isEqualTo("Ada");
        assertThat(second.join()).isEqualTo("Grace");
        assertThat(batchCalls).hasValue(1);
    }
}
~~~

In a plain unit test, call `dispatchAndJoin()` to trigger the batch because no GraphQL execution is managing dispatch. Never call this method in real resolvers; GraphQL Java dispatches DataLoaders automatically.

The test above verifies that two `load(1L)` calls and one `load(2L)` call are processed in a single batch. If caching is disabled, repeated loads of the same key may enter the batch multiple times depending on the loader/options. Write tests matching the cache policy your application intentionally configures.

## 7. Verifying DataLoader is created separately per request

DataLoader caching is scoped strictly to a single GraphQL execution. Use the same `GraphQlTester` to execute two separate operations, then verify the batch service is called twice:

~~~java
@Test
void doesNotShareDataLoaderCacheAcrossExecutions() {
    given(bookService.findAll()).willReturn(List.of(
            new Book("book-1", "GraphQL Basics", 10L)
    ));
    given(authorService.findByIds(Set.of(10L)))
            .willReturn(Mono.just(Map.of(10L, new Author(10L, "Ada"))));

    String document = "{ books { id author { name } } }";

    graphQlTester.document(document)
            .execute()
            .path("books[0].author.name")
            .entity(String.class)
            .isEqualTo("Ada");

    graphQlTester.document(document)
            .execute()
            .path("books[0].author.name")
            .entity(String.class)
            .isEqualTo("Ada");

    verify(authorService, org.mockito.Mockito.times(2))
            .findByIds(Set.of(10L));
}
~~~

The two `execute()` calls are two independent GraphQL executions. Each creates a fresh `DataLoaderRegistry` and DataLoader cache, so the same author ID is loaded again from the batch service. Spring does not retain DataLoader caches across requests merely because `GraphQlTester` or `BatchLoaderRegistry` is reused.

If a test calls `load(key)` twice within the same execution, results may be cached. When sending two independent GraphQL requests, never expect the first request's cache to be reused by the second request.

## 8. Testing @BatchMapping

`@BatchMapping` is a concise way to declare batch resolvers. Spring for GraphQL automatically registers a DataLoader for the source field. Tests can follow the same strategy: supply multiple parent objects, assert child data, and verify the service is invoked in batches.

Example resolver:

~~~java
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

import org.springframework.graphql.data.method.annotation.BatchMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;

@Controller
public class BookBatchController {

    private final AuthorService authorService;

    public BookBatchController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @BatchMapping(typeName = "Book", field = "author")
    public Mono<Map<Book, Author>> author(List<Book> books) {
        Set<Long> authorIds = books.stream()
                .map(Book::authorId)
                .collect(Collectors.toSet());

        return authorService.findByIds(authorIds)
                .map(authorsById -> books.stream()
                        .filter(book -> authorsById.containsKey(book.authorId()))
                        .collect(Collectors.toMap(
                                book -> book,
                                book -> authorsById.get(book.authorId())
                        )));
    }
}
~~~

With `@BatchMapping`, the batch loader receives a list of source objects (`Book`) and returns a map from source objects to results (`Author`). In this example, the service still queries using the deduplicated set of author IDs. In tests, verify `findByIds` is called once with the expected ID set.

Using a `Book` record provides `equals` and `hashCode` derived from record components, making it suitable as a map key in this example. With mutable entities, ensure equality/hashCode remains stable while used as map keys.

## 9. Testing ordering and result mapping

A batch loader can return results in a different order than the input keys. With a mapped batch loader, DataLoader correlates results by map keys rather than map iteration order.

Tests should deliberately return a map ordered differently from the books list and still assert that each book receives the right author:

~~~java
given(authorService.findByIds(Set.of(10L, 20L)))
        .willReturn(Mono.just(Map.of(
                20L, new Author(20L, "Grace"),
                10L, new Author(10L, "Ada")
        )));

graphQlTester.document("{ books { id author { id name } } }")
        .execute()
        .path("books[*].author.name")
        .entityList(String.class)
        .containsExactly("Ada", "Ada", "Grace");
~~~

This is an important check when backends return rows from SQL `IN (...)`, because databases do not guarantee row order without an `ORDER BY`. If using a positional list `BatchLoader` instead of a mapped loader, the batch function must return a result list aligned strictly in the same order as the input key list.

## 10. Testing missing keys and nullability

A mapped batch loader might omit a key from its returned map. DataLoader will find no value for that key, and the resolver may receive `null` for the field.

For example, the service finds author ID `10` while ID `20` does not exist:

~~~java
given(authorService.findByIds(Set.of(10L, 20L)))
        .willReturn(Mono.just(Map.of(
                10L, new Author(10L, "Ada")
        )));
~~~

Since the SDL declares nullable `author: Author`, the test can assert that the missing field is null while other fields remain populated:

~~~java
graphQlTester.document("{ books { id title author { name } } }")
        .execute()
        .path("books[1].author")
        .valueIsNull();
~~~

If the schema changes to `author: Author!`, null is invalid and GraphQL applies null propagation up to the parent. Tests should verify the exact `data` location nulled out and the error behavior if the batch loader throws an exception. A missing key returning null and a batch loader throwing an exception are two distinct scenarios; do not collapse them into the same assertion.

## 11. Testing errors from batch loaders

When a batch service fails, its publisher may emit an error:

~~~java
given(authorService.findByIds(Set.of(10L, 20L)))
        .willReturn(Mono.error(new IllegalStateException("database unavailable")));
~~~

GraphQL records errors at the affected field or fields depending on how DataLoader emits errors and schema nullability. Use `GraphQlTester.errors()` to assert error codes/paths, then assert remaining valid data:

~~~java
graphQlTester.document("{ books { id title author { name } } }")
        .execute()
        .errors()
        .expect(error -> error.getPath() != null)
        .verify()
        .path("books[*].title")
        .entityList(String.class)
        .containsExactly("GraphQL Basics", "Spring GraphQL");
~~~

Do not assert only the error count. Assert specific paths or `extensions.code` values to confirm errors are attached to the expected fields and not confused with another resolver failure.

## 12. Testing maxBatchSize and multiple batch dispatches

DataLoader can cap the number of keys per batch using `maxBatchSize`. When the key count exceeds that limit, a single GraphQL execution can trigger multiple batch loader invocations.

Example configuring options on registration:

~~~java
registry.forTypePair(Long.class, Author.class)
        .withOptions(options -> options.setMaxBatchSize(2))
        .registerMappedBatchLoader((authorIds, environment) ->
                authorService.findByIds(authorIds)
        );
~~~

When testing with 5 distinct author IDs and `maxBatchSize = 2`, expect multiple batch loader calls, each containing at most 2 keys. The exact invocation count depends on how GraphQL Java splits batches and how many keys are loaded; with 5 keys, expect 3 batches.

You can capture each key set using Mockito `ArgumentCaptor<Set<Long>>` and verify:

- Total unique keys equal 5.
- No batch has more than 2 keys.
- The union of batch keys equals the expected ID set.
- No ID is lost or processed twice outside the cache policy.

Batch limits protect databases and downstream services from oversized queries. Tests should reflect the application's actual configured limits rather than assuming all keys always fit in a single batch.

## 13. Testing cache policies

By default, DataLoader caches by key within its instance scope. Applications can disable caching or supply custom cache keys/options as needed.

When caching is disabled, each `load(key)` call creates a distinct promise, and a positional batch loader can receive duplicate keys. However, `MappedBatchLoader` receives `Set<K>`, so its contract cannot represent duplicate keys in the batch argument itself. If you need to verify duplicate keys with caching disabled, use `BatchLoader<K, V>`, which receives `List<K>`.

Example unit testing a positional batch loader with caching disabled:

~~~java
import java.util.List;
import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CopyOnWriteArrayList;

import org.dataloader.BatchLoader;
import org.dataloader.DataLoader;
import org.dataloader.DataLoaderFactory;
import org.dataloader.DataLoaderOptions;

import static org.assertj.core.api.Assertions.assertThat;

List<Long> receivedKeys = new CopyOnWriteArrayList<>();
BatchLoader<Long, String> batchLoader = keys -> {
    receivedKeys.addAll(keys);
    Map<Long, String> values = Map.of(1L, "Ada", 2L, "Grace");
    return CompletableFuture.completedFuture(
            keys.stream().map(values::get).toList()
    );
};

DataLoaderOptions options = DataLoaderOptions.newOptions()
        .setCachingEnabled(false)
        .build();

DataLoader<Long, String> dataLoader =
        DataLoaderFactory.newDataLoader(batchLoader, options);

var first = dataLoader.load(1L);
var duplicate = dataLoader.load(1L);
dataLoader.dispatchAndJoin();

assertThat(first.join()).isEqualTo("Ada");
assertThat(duplicate.join()).isEqualTo("Ada");
assertThat(receivedKeys).containsExactly(1L, 1L);
~~~

This test proves two loads of the same key remain two elements in a positional batch when caching is off. With `MappedBatchLoader`, the input is a `Set<K>` and duplicate keys are already deduplicated from the batch input; in that case, assert call/future counts and mapped results according to the mapped loader's contract.

When using custom cache keys, tests must also prove that distinct keys do not accidentally collide on the same cache entry.

Do not disable caching merely to make tests predictable. Request-scoped caching is generally valuable for deduplicating repeated loads; change the policy only for specific data requirements.

## 14. Testing context and tenant isolation in batch loaders

Batch loaders may need the tenant, principal, or locale of the GraphQL execution. Spring for GraphQL passes execution context via `BatchLoaderEnvironment`, so tests should verify the batch loader receives the right context for the current request.

A testing strategy:

1. Use `WebGraphQlTester` or `HttpGraphQlTester` with an interceptor that authenticates or places the tenant into `GraphQLContext`.
2. Send requests for tenant A and tenant B with the same entity ID.
3. Verify the batch service receives each tenant accordingly and returns tenant-appropriate data.
4. Verify no cache is shared between the two executions.

Never rely on a `currentTenant` field on a singleton service in tests. Capture the tenant parameter passed to the service or read context from `BatchLoaderEnvironment` inside the batch loader. This catches tenant-leakage bugs caused by global mutable state.

## 15. Testing cache invalidation after mutations

If a mutation updates an entity and child fields in the same execution subsequently use DataLoader, stale cache entries may need to be cleared or replaced.

Example mutation accepting a DataLoader and updating its cache:

~~~java
@MutationMapping
public CompletableFuture<Author> renameAuthor(
        @Argument("id") Long id,
        @Argument("name") String name,
        DataLoader<Long, Author> authorLoader
) {
    return authorService.rename(id, name)
            .doOnNext(updated -> {
                authorLoader.clear(updated.id());
                authorLoader.prime(updated.id(), updated);
            })
            .toFuture();
}
~~~

Tests should verify that resolvers running after the mutation read the updated value. `clear(key)` removes the stale entry; `prime(key, value)` populates the new value if the key is not already cached. This is the DataLoader cache for the current execution, not a shared application cache.

If the application has a separate Redis/Caffeine cache, test invalidation of that cache at the corresponding service/integration layer. Never make a DataLoader outlive a request to act as a business cache.

## 16. Distinguishing DataLoader tests from repository tests

`GraphQlTester` is well suited to verifying that GraphQL operations genuinely batch field loads and return the right data. It does not necessarily have to inspect generated SQL. You can split tests by layer:

| Test type | What to verify |
| --- | --- |
| DataLoader unit test | Caching, dispatch, mapped results, and pure batch loader logic |
| GraphQL slice test | Resolver uses DataLoader, batching occurs, and responses match |
| Service/repository test | A single batch request queries data efficiently with proper transactions |
| Integration test | Full GraphQL stack, database, transactions, and transport work together |
| Performance test | Query count, batch size, latency, and throughput under representative load |

Do not use a GraphQL slice test to conclude the database ran only one SQL statement if the service could issue multiple queries internally. When you need to verify SQL/query counts, add tests at the repository or integration layer using appropriate instrumentation.

## 17. Anti-patterns in DataLoader tests

| Anti-pattern | Problem | Better approach |
| --- | --- | --- |
| Asserting response data only | An N+1 resolver can still return identical data | Verify batch service call counts and key sets |
| Calling `dispatch()` inside controllers | Interferes with GraphQL-managed lifecycle | Call only `load(key)` in resolvers |
| Using a singleton DataLoader in tests | Hides request-isolation bugs | Register via `BatchLoaderRegistry` and let Spring create loaders per execution |
| Reusing the same cache across two test requests | Results depend on order or stale data | Execute two separate operations and verify batch loaders run independently |
| Testing only one parent object | Cannot prove batching | Use multiple parents with both duplicate and distinct keys |
| Skipping ordering/mapping checks | Batch loader could map objects to wrong keys | Assert child fields on every parent, including out-of-order returned maps |
| Ignoring missing keys | Nullability can break entire parents/lists | Test mapped results with missing keys against both nullable and Non-Null schemas |
| Retrying batch errors unconditionally | Can duplicate side effects or overload downstream services | Classify errors and retry under bounded policies |

## 18. Workflow for writing DataLoader tests

When adding or modifying a DataLoader:

1. Create a GraphQL query with multiple parent objects needing the same related data type.
2. Register the batch loader via `BatchLoaderRegistry` or use `@BatchMapping`.
3. Use `GraphQlTester` to run the query through real GraphQL execution.
4. Assert child data for each parent using `entityList` or nested paths.
5. Verify the batch service was called the expected number of times with the right key set.
6. Include parents with duplicate keys to verify within-execution caching.
7. Execute two separate requests to confirm caches are not shared.
8. Test missing keys, batch errors, and null propagation.
9. If `maxBatchSize` is configured, capture batches and verify the limit.
10. If the loader depends on tenant/principal, test context isolation.
11. If mutations modify data, test `clear`/`prime` and cache invalidation.
12. Use dedicated repository/performance tests when SQL counts or latency need verification.

A strong DataLoader test proves both the GraphQL result and how the data was loaded. `GraphQlTester` verifies behavior from the operation perspective; Mockito or spies verify batch invocations; GraphQL Java DataLoader unit tests verify caching and dispatch. Combining these layers catches N+1 issues, mis-scoped caches, and mapping bugs before they reach production.

## References

- [Spring for GraphQL — Batch Loading](https://docs.spring.io/spring-graphql/reference/request-execution.html#execution.batch-loading)
- [Spring for GraphQL — BatchLoaderRegistry API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/execution/BatchLoaderRegistry.html)
- [Spring for GraphQL — Testing](https://docs.spring.io/spring-graphql/reference/testing.html)
- [GraphQL Java — DataLoader](https://github.com/graphql-java/java-dataloader)
