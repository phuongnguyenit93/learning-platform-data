# Testing batch mapping in Spring for GraphQL

`@BatchMapping` lets Spring for GraphQL batch nested field resolution across multiple parent objects into a single batch load. When testing, verify that the GraphQL response is accurate, the batch method receives the expected collection of parent objects, and the service/repository is invoked in batches rather than once per parent. When using `BatchLoaderRegistry` and `DataLoader` directly, you can test the loader in isolation by registering it into a `DataLoaderRegistry`, queuing multiple keys, and dispatching.

Spring for GraphQL provides two complementary testing layers: use `GraphQlTester` to run operations through GraphQL execution and verify real field mappings; use `DataLoaderRegistry` to test individual batch loaders directly. Never call a `@BatchMapping` Java method directly and conclude that GraphQL batching works, because doing so skips framework data fetcher registration and DataLoader orchestration.

## 1. Why test batch mapping?

Suppose a query returns multiple books, each with an author:

```graphql
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
```

If `Book.author` is resolved by a regular `@SchemaMapping` that queries the database on every call, a query returning 50 books can trigger:

- 1 load for the list of books.
- 50 loads for authors, one per book.

That is the N+1 problem. `@BatchMapping` collects parent `Book` objects in the same batch and loads authors by a set of IDs:

```text
GraphQL query
     |
     v
Load 50 books
     |
     v
Collect parent Book objects
     |
     v
@BatchMapping(author)
     |
     v
Load authors for unique author IDs
     |
     v
Map each Book to its Author
```

Tests must verify both the data and the batching behavior. Checking only the list of `author.name` values will not catch an implementation that still calls the repository 50 times while happening to return the right data.

## 2. Preparing the example schema and models

SDL schema:

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

Place the schema file at `src/main/resources/graphql/books.graphqls` or in the schema location configured by your application.

Java models using records:

```java
public record Book(String id, String title, String authorId) {}

public record Author(String id, String name) {}
```

Records derive `equals` and `hashCode` from their components, so `Book` works well as a key in `Map<Book, Author>` in this example. If using mutable entities or regular classes, ensure keys maintain stable equality/hash semantics throughout batch mapping.

To use `GraphQlTester`, add the testing dependency:

```groovy
dependencies {
    testImplementation 'org.springframework.graphql:spring-graphql-test'
}
```

If the project uses Spring Boot, let Boot's dependency management align compatible Spring GraphQL versions.

Services used by the controller:

```java
public interface BookCatalog {
    List<Book> findAll();
}

public interface AuthorCatalog {
    Map<String, Author> findAllById(Set<String> authorIds);
}
```

`AuthorCatalog.findAllById` accepts a set of IDs and returns a map keyed by ID so the batch method can match authors back to their books.

## 3. Writing a controller with `@BatchMapping`

Controller:

```java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

import org.springframework.graphql.data.method.annotation.BatchMapping;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
class BookController {

    private final BookCatalog bookCatalog;
    private final AuthorCatalog authorCatalog;

    BookController(BookCatalog bookCatalog, AuthorCatalog authorCatalog) {
        this.bookCatalog = bookCatalog;
        this.authorCatalog = authorCatalog;
    }

    @QueryMapping
    List<Book> books() {
        return bookCatalog.findAll();
    }

    @BatchMapping(typeName = "Book", field = "author")
    Map<Book, Author> author(List<Book> books) {
        Set<String> authorIds = books.stream()
            .map(Book::authorId)
            .collect(Collectors.toSet());

        Map<String, Author> authors = authorCatalog.findAllById(authorIds);
        Map<Book, Author> result = new LinkedHashMap<>();

        for (Book book : books) {
            Author author = authors.get(book.authorId());
            if (author != null) {
                result.put(book, author);
            }
        }

        return result;
    }
}
```

`@BatchMapping` registers a batch data fetcher for the `Book.author` field. The framework collects parent `Book` instances requested in the same batch and passes them into the `List<Book>` parameter.

`Map<Book, Author>` maps each parent to its corresponding field value. If a key is absent from the map, that field resolves to `null`; hence the SDL declares nullable `author: Author` in this example. If the schema declares `author: Author!`, tests must ensure every book has an author or intentionally verify Non-null error propagation.

If the method name matches the field name, `field = "author"` can be omitted. If a controller has only a single type mapping and the method name is `author`, the annotation can be written more concisely:

```java
@BatchMapping
Map<Book, Author> author(List<Book> books) {
    // batch loading
}
```

Specifying `typeName` and `field` explicitly generally makes examples clearer and avoids relying on name inference.

## 4. Testing `@BatchMapping` with `@GraphQlTest` and `GraphQlTester`

`@GraphQlTest` creates a test slice for GraphQL controllers without starting an HTTP server. `GraphQlTester` is configured to send operations directly into GraphQL execution. Services the controller depends on can be replaced with mocks.

Complete test example:

```java
import java.util.List;
import java.util.Map;
import java.util.Set;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;
import org.springframework.graphql.test.tester.GraphQlTester;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.mockito.BDDMockito.given;
import static org.mockito.BDDMockito.then;
import static org.mockito.Mockito.times;

@GraphQlTest(BookController.class)
class BookBatchMappingTests {

    @Autowired
    GraphQlTester graphQlTester;

    @MockitoBean
    BookCatalog bookCatalog;

    @MockitoBean
    AuthorCatalog authorCatalog;

    @Test
    void loadsAuthorsInOneBatchForAllBooks() {
        Book book1 = new Book("book-1", "GraphQL Basics", "author-1");
        Book book2 = new Book("book-2", "Spring Guide", "author-2");
        Book book3 = new Book("book-3", "GraphQL Advanced", "author-1");

        given(bookCatalog.findAll()).willReturn(List.of(book1, book2, book3));
        given(authorCatalog.findAllById(Set.of("author-1", "author-2")))
            .willReturn(Map.of(
                "author-1", new Author("author-1", "Ada"),
                "author-2", new Author("author-2", "Grace")
            ));

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
            .containsExactly("Ada", "Grace", "Ada");

        then(bookCatalog).should(times(1)).findAll();
        then(authorCatalog).should(times(1))
            .findAllById(Set.of("author-1", "author-2"));
    }
}
```

The test above verifies three things:

1. GraphQL returns the right author name for each book.
2. Three books with two distinct author IDs are consolidated into a unique ID set.
3. `AuthorCatalog.findAllById` is called exactly once in this operation.

The first and third books share `author-1`. The test still expects both parents to receive the same author while the repository receives that author ID only once in the batch. This is a great case for testing deduplication at the batch query layer.

In Spring Boot 3.x, `@GraphQlTest` resides in `org.springframework.boot.test.autoconfigure.graphql`; in Spring Boot 4.x, test auto-configuration packages were reorganized under `org.springframework.boot.graphql.test.autoconfigure`. `@MockitoBean` comes from Spring Framework 6.2+; on older projects, use that version's mock bean mechanism such as `@MockBean`.

Accordingly, the import in the example targets Spring Boot 3.x. For Spring Boot 4.x, replace it with:

```java
import org.springframework.boot.graphql.test.autoconfigure.GraphQlTest;
```

## 5. Why must the GraphQL document select the batched field?

`@BatchMapping` runs only when the query actually selects the field it maps. For example:

```graphql
query {
    books {
        id
        title
    }
}
```

This operation does not select `Book.author`, so `author(...)` is never invoked. If a test queries only `id` and `title` and then verifies `authorCatalog.findAllById(...)`, the test will rightly fail because GraphQL had no need to resolve that field.

To test batch mapping, the selection set must include the corresponding field:

```graphql
query {
    books {
        id
        author {
            name
        }
    }
}
```

When verifying different mappings, craft operations whose selection set targets the exact field under test. Avoid adding unrelated fields just to trigger multiple resolvers, as that makes failures harder to diagnose.

## 6. Verifying invocation count and batch key set

A solid batch test typically checks both invocation count and key set:

```java
then(authorCatalog).should(times(1))
    .findAllById(Set.of("author-1", "author-2"));
```

This assertion proves the service receives a deduplicated set of keys in a single call. If you need to inspect key contents or ordering in detail, use `ArgumentCaptor`:

```java
ArgumentCaptor<Set<String>> idsCaptor = ArgumentCaptor.forClass(Set.class);

then(authorCatalog).should(times(1)).findAllById(idsCaptor.capture());

assertThat(idsCaptor.getValue())
    .containsExactlyInAnyOrder("author-1", "author-2");
```

Do not use `containsExactly(...)` on a `Set` unless order is part of the contract. `Set` does not guarantee ordering like `List`.

In complex GraphQL executions, a field might be invoked across multiple dispatches or execution branches. Therefore, asserting exactly one call fits a specific test with one root list and one batch dispatch. When queries have multiple branches or paginated subtrees, assert batch counts according to the operation structure rather than hard-coding one fixed number everywhere.

## 7. Testing `@BatchMapping` returning `Flux<V>`

`@BatchMapping` can also return `Flux<V>`. In that case, emitted values must follow the exact order of the parent object list passed to the method.

Example:

```java
@BatchMapping(typeName = "Book", field = "author")
Flux<Author> author(List<Book> books) {
    List<String> authorIds = books.stream()
        .map(Book::authorId)
        .toList();

    return authorCatalog.findAllInOrder(authorIds);
}
```

The test must verify matching order:

```java
graphQlTester.document("""
        query {
            books {
                id
                author { name }
            }
        }
        """)
    .execute()
    .path("books[*].author.name")
    .entityList(String.class)
    .containsExactly("Ada", "Grace", "Ada");
```

If a repository returns results in arbitrary database order or sorted by author ID, results can get attached to the wrong parent. When order cannot be guaranteed, `Mono<Map<K,V>>` expresses parent-to-value relationships much more safely.

## 8. Testing missing values in batch results

Suppose a book references a nonexistent `authorId`. With schema:

```graphql
type Book {
    id: ID!
    author: Author
}
```

The batch method can omit that parent from the map; GraphQL will return `author: null` for the nullable field.

Tests should verify both present and missing values:

```java
response.path("books[0].author.name")
    .entity(String.class)
    .isEqualTo("Ada");

response.path("books[1].author").valueIsNull();
```

If the SDL changes to `author: Author!`, resolving to `null` triggers a GraphQL execution error and null propagation up to the nearest nullable parent. When testing Non-null fields, assert both `response.errors()` and the nulled-out `data` location per schema rules.

Do not use `Map.of(...)` to construct maps containing null values because Java's `Map.of` forbids null keys and values. If you need to represent missing values, omit the key from the map or use a map implementation that allows nulls matching your resolver's semantics.

## 9. Testing batch mappings with arguments or context

`@BatchMapping` supports method arguments such as:

| Argument | Meaning |
|---|---|
| `List<K>` | List of parent/source objects in the batch. |
| `Principal` | Principal from the Spring Security context, if present. |
| `@ContextValue` | A value from the `GraphQLContext` of the batch loader environment. |
| `GraphQLContext` | Shared context for the GraphQL execution. |
| `BatchLoaderEnvironment` | Context and per-key local contexts for the batch. |

Example batch mapping with tenant context:

```java
@BatchMapping(typeName = "Book", field = "reviews")
Mono<Map<Book, List<Review>>> reviews(
        List<Book> books,
        @ContextValue("tenantId") String tenantId) {

    Set<String> bookIds = books.stream()
        .map(Book::id)
        .collect(Collectors.toSet());

    return reviewService.findByTenantAndBookIds(tenantId, bookIds)
        .collectMultimap(Review::bookId)
        .map(reviewsByBook -> {
            Map<Book, List<Review>> result = new LinkedHashMap<>();
            for (Book book : books) {
                result.put(book, List.copyOf(
                    reviewsByBook.getOrDefault(book.id(), List.of())
                ));
            }
            return result;
        });
}
```

When testing context, initialize `GraphQLContext` or configure the request to populate `tenantId` for execution. Then verify the service receives the expected tenant ID and full set of book IDs in the same batch. Do not assume the test slice creates tenant context or a Spring Security principal unless the test explicitly configures them.

## 10. Testing `BatchLoaderRegistry` and `DataLoader` directly

When using `DataLoader` directly instead of `@BatchMapping`, you can test the loader without running a GraphQL query. The approach recommended in the Spring for GraphQL docs:

1. Create a `DefaultBatchLoaderRegistry`.
2. Register the batch loader.
3. Create a `DataLoaderRegistry`.
4. Call `registerDataLoaders(...)` to populate the registry with registered loaders.
5. Retrieve the `DataLoader` by name.
6. Call `load` for multiple keys, then `dispatchAndJoin()` to execute the batch.

Example:

```java
@Test
void dispatchesSeveralKeysInOneBatch() {
    List<Set<Long>> dispatchedKeys = new ArrayList<>();

    BatchLoaderRegistry batchLoaderRegistry = new DefaultBatchLoaderRegistry();

    batchLoaderRegistry.forTypePair(Long.class, Author.class)
        .registerMappedBatchLoader((authorIds, environment) -> {
            dispatchedKeys.add(Set.copyOf(authorIds));

            return Mono.just(Map.of(
                1L, new Author("1", "Ada"),
                2L, new Author("2", "Grace"),
                3L, new Author("3", "Linus")
            ));
        });

    GraphQLContext graphQLContext = GraphQLContext.newContext().build();
    DataLoaderRegistry dataLoaderRegistry = DataLoaderRegistry.newRegistry().build();

    batchLoaderRegistry.registerDataLoaders(dataLoaderRegistry, graphQLContext);

    DataLoader<Long, Author> loader =
        dataLoaderRegistry.getDataLoader(Author.class.getName());

    loader.load(1L);
    loader.loadMany(List.of(2L, 3L));

    List<Author> authors = loader.dispatchAndJoin();

    assertThat(authors)
        .extracting(Author::name)
        .containsExactly("Ada", "Grace", "Linus");

    assertThat(dispatchedKeys)
        .containsExactly(Set.of(1L, 2L, 3L));
}
```

Key imports:

```java
import graphql.GraphQLContext;
import org.dataloader.DataLoader;
import org.dataloader.DataLoaderRegistry;
import org.springframework.graphql.execution.BatchLoaderRegistry;
import org.springframework.graphql.execution.DefaultBatchLoaderRegistry;
import reactor.core.publisher.Mono;

import static org.assertj.core.api.Assertions.assertThat;
```

In this example, the default `DataLoader` name comes from the value type's class name, `Author.class.getName()`. You can customize the loader name on the `BatchLoaderRegistry` builder; if customized, tests must look up the loader by that custom name.

`dispatchAndJoin()` dispatches queued keys and waits for results. This test verifies batching of the registered loader, but does not verify that `@BatchMapping` is bound properly to a GraphQL field. Therefore, combine it with `GraphQlTester` tests when controllers use annotated mappings.

## 11. Testing per-request caching of DataLoader

DataLoader normally caches results by key for the duration of a single GraphQL request. When the same key is loaded multiple times before the cache is cleared, the batch loader does not necessarily receive duplicate keys.

Tests can verify caching behavior:

```java
loader.load(1L);
loader.load(1L);
loader.load(2L);

List<Author> authors = loader.dispatchAndJoin();
```

With default caching enabled, the loader typically requests key `1` only once in the batch. If the application changes `DataLoaderOptions` to disable caching or use another cache strategy, expectations differ. Tests should clearly reflect the loader configuration in use rather than assuming all loaders deduplicate identically.

DataLoader caches are request-scoped, not global application caches. Never share a single `DataLoaderRegistry` across multiple GraphQL requests, as that breaks cache scope and leaks data.

## 12. Testing `BatchLoaderRegistry` with `GraphQLContext`

`BatchLoaderRegistry` supports passing the same `GraphQLContext` to batch loading functions and `@BatchMapping` methods. That is one reason Spring recommends registering loaders through the registry rather than instantiating standalone `DataLoader` objects manually.

Example loader reading tenant from context:

```java
batchLoaderRegistry.forTypePair(String.class, Book.class)
    .registerMappedBatchLoader((bookIds, environment) -> {
        GraphQLContext context = (GraphQLContext) environment.getContext();
        String tenantId = context.get("tenantId");

        return bookService.findByTenantAndIds(tenantId, bookIds)
            .collectMap(Book::id);
    });
```

In a direct test, build a context with the tenant before calling `registerDataLoaders`:

```java
GraphQLContext graphQLContext = GraphQLContext.newContext()
    .of("tenantId", "tenant-a")
    .build();
```

After dispatching, verify the service receives the expected tenant and ID set. For `@BatchMapping` tests, you can use `WebGraphQlTester` or `ExecutionGraphQlServiceTester` to configure the execution context accordingly. The goal is to confirm context is never shared across requests from different tenants.

## 13. Testing `@BatchMapping` over HTTP when transport verification is needed

`@GraphQlTest` tests GraphQL controllers and execution without starting an HTTP server. When you need to verify the full HTTP endpoint, headers, security, or application context wiring, use `HttpGraphQlTester` with `WebTestClient`.

Example configuration with a live server:

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureHttpGraphQlTester
class BookBatchMappingHttpTests {

    @Autowired
    HttpGraphQlTester graphQlTester;

    @Test
    void resolvesAuthorsThroughHttp() {
        graphQlTester.document("""
                query {
                    books {
                        id
                        author { name }
                    }
                }
                """)
            .execute()
            .path("books[*].author.name")
            .entityList(String.class)
            .contains("Ada", "Grace");
    }
}
```

This test requires a configured application context, schema, database/fixtures, and live GraphQL endpoint. If you need to prove the database executed only one query, use spies, metrics, or a query counter at the repository layer or inspect the batch service; asserting only the HTTP response does not prove query count.

The package for `@AutoConfigureHttpGraphQlTester` also depends on the Spring Boot version:

```java
// Spring Boot 3.x
import org.springframework.boot.test.autoconfigure.graphql.tester.AutoConfigureHttpGraphQlTester;

// Spring Boot 4.x
import org.springframework.boot.graphql.test.autoconfigure.tester.AutoConfigureHttpGraphQlTester;
```

## 14. Cases to include in the test matrix

| Case | What to verify |
|---|---|
| Single parent object | Mapping returns the associated object properly. |
| Multiple parent objects | Batch method receives the entire list in one dispatch. |
| Multiple parents sharing a key | Keys are deduplicated according to DataLoader or batch service setup. |
| A key has no result | Nullable field resolves to `null`, or Non-null errors per SDL. |
| Batch returns `Map<K,V>` | Each parent receives the value matching its key. |
| Batch returns `Flux<V>` | Value order matches the parent list order. |
| Query omits batched field | Batch method is not invoked. |
| Multiple batched fields | Each mapping is invoked with its own group of parents. |
| With `@ContextValue`/tenant | Batch query uses the current execution's context. |
| Two concurrent requests | Keys, caches, and contexts are never mixed across requests. |
| DataLoader cache | Duplicate keys follow `DataLoaderOptions`. |
| Repository failure | GraphQL errors and partial data adhere to schema rules. |

## 15. Common mistakes when testing batch mapping

**Calling the `@BatchMapping` method directly.** That skips GraphQL field registration, DataLoader dispatch, and parent-to-child mapping. Use `GraphQlTester` to test full execution.

**Query omits the batched field.** If the document selects only `Book.id`, the `Book.author` mapping will not run. Add the field to the selection set.

**Asserting only data without checking call counts.** N+1 queries can still happen even when the response matches. Verify the service/repository is invoked in batches with the expected key set.

**Using `Flux<V>` without preserving parent order.** Results may get paired with the wrong objects. Use `Map<K,V>` whenever order cannot be guaranteed.

**Using parent objects as map keys without stable equality.** Without proper `equals`/`hashCode`, DataLoader cannot correlate results reliably. Use records or immutable keys.

**Looking up DataLoader by the wrong name.** By default Spring uses the value type's class name; if the builder customizes the loader name, tests must use that exact name.

**Forgetting to dispatch in DataLoader unit tests.** `load()` only queues keys. Call `dispatchAndJoin()` or an appropriate dispatch call to run the batch.

**Reusing a registry across multiple tests/requests.** DataLoader caches are request-scoped. Create fresh registries for independent tests and avoid sharing caches across tenants.

**Drawing SQL optimization conclusions from mock tests.** Batch method tests verify service call counts, whereas verifying SQL queries, indexes, or database round-trips requires integration tests with real persistence and query metrics.

## Conclusion

To test `@BatchMapping`, write a GraphQL query selecting the batched field, run it through `GraphQlTester`, assert the returned data, and verify the service/repository receives the key set in the expected number of calls. For `BatchLoaderRegistry`/`DataLoader` directly, register the loader into a `DataLoaderRegistry`, queue multiple keys, and call `dispatchAndJoin()` to assert batch results. Add tests for duplicate keys, missing data, `Flux` ordering, `GraphQLContext`, and per-request caching. Combining these two layers catches both mapping bugs and batching regressions that response assertions alone would hide.

## References

- [Spring for GraphQL — Testing](https://docs.spring.io/spring-graphql/reference/testing.html)
- [Spring for GraphQL — Request Execution: Batch Loading and Testing Batch Loading](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring for GraphQL — Annotated Controllers: `@BatchMapping`](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [GraphQL Java — DataLoader](https://github.com/graphql-java/java-dataloader)
