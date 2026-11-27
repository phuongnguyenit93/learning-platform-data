# Mapping source to target with @BatchMapping

In GraphQL, a nested field typically fetches data based on a parent object. For example, the `Book.author` field needs to take a `Book` as the source and return an `Author` as the target. If the resolver is invoked individually for each book, the application easily produces N+1 queries. Spring for GraphQL's `@BatchMapping` allows accepting a list of source objects, loading related data in bulk, and returning results mapped from each source to its target.

With the `Map<Source, Target>` return type, the map key is the source object that GraphQL passed into the batch method; the value is the resolved field value for that source. This structure does not depend on the order of results returned by the repository, as long as each source is linked to the right target. This is the core of the "map source to target" pattern.

After this lesson, you will be able to:

- Understand the source object and target value in a batch mapping.
- Declare `@BatchMapping` for relational fields in the SDL.
- Return `Map<Source, Target>` or `Mono<Map<Source, Target>>` according to the contract.
- Query targets by a set of keys and rebuild the map keyed by source objects.
- Handle one-to-one, many-to-one, and one-to-many relationships.
- Distinguish source-keyed maps from order-preserving lists/Flux.
- Handle missing targets, source equality, errors, and access permissions.
- Test mappings and verify that batching actually reduces backend access count.

## 1. Source and target in field mapping

Suppose the schema has books and authors:

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

When GraphQL resolves the `Book.author` field, the current `Book` object is the **source**. The returned `Author` value is the **target** of that field.

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

If the query returns 50 books, GraphQL may need 50 `author` values. `@BatchMapping` collects all 50 `Book` sources into a single call to the batch method. The method finds the required authors and returns a map so GraphQL knows which author each book receives.

The source does not have to be a JPA entity. It is the parent object returned to GraphQL by the preceding resolver, which can be a record, DTO, projection, or domain object. The Java type of the source method parameter must be able to accept those actual objects.

## 2. The @BatchMapping contract

Declaring a batch mapping for `Book.author`:

```java
@Controller
public class BookController {

    @BatchMapping(typeName = "Book", field = "author")
    public Map<BookView, AuthorView> author(List<BookView> books) {
        // The full implementation is presented in section 5.
        throw new UnsupportedOperationException("Illustrative signature");
    }
}
```

Key parts:

- `typeName = "Book"`: the object type name in the GraphQL SDL.
- `field = "author"`: the field to batch map.
- `List<BookView> books`: the list of source objects collected for that field.
- `Map<BookView, AuthorView>`: the key is the source `BookView`, and the value is the target `AuthorView` for the `author` field.

Spring for GraphQL registers the corresponding batch data fetcher for the field. Instead of calling the method once per `Book`, the framework collects the source objects and calls the batch method. The method must return results that can be matched accurately back to each source.

The GraphQL names in `typeName` and `field` must match the schema. The Java class name can differ from the GraphQL type name; for example, GraphQL `Book` can be represented by Java `BookView`.

## 3. Why return Map<Source, Target>?

A batch method can return a list of targets in the order of the input sources, or return a map from source to target. A Map is useful when the data order from the database does not match the source order, or when some targets may not exist.

Example source list:

```text
books = [Book-A(authorId=30), Book-B(authorId=10), Book-C(authorId=20)]
```

The repository may return authors in its own order:

```text
authors = [Author-10, Author-20, Author-30]
```

If you simply return a list in repository order, GraphQL may assign the wrong author to a book. A Map expresses the relationship explicitly:

```text
Book-A -> Author-30
Book-B -> Author-10
Book-C -> Author-20
```

A Map imposes no element ordering requirement. Each target is linked to its corresponding source object via the key. This allows the batch method to focus on looking up targets by key and then reconstructing the source-to-target relationships.

## 4. Preparing Java source and target models

Example using records as read models:

```java
public record BookView(
        Long id,
        String title,
        Long authorId) {
}

public record AuthorView(
        Long id,
        String name) {
}
```

Root resolver returning source objects:

```java
@Controller
public class CatalogQueryController {

    private final BookService bookService;

    public CatalogQueryController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public List<BookView> books() {
        return bookService.findBooks();
    }
}
```

When GraphQL executes the `author` field on each `BookView`, Spring collects the source objects and passes that list into the batch method. `authorId` is the foreign key linking to the target, but the key of the result map remains `BookView`, because GraphQL needs to know which target belongs to which source.

## 5. Implementing source-to-target mapping

The service loads multiple authors in one call and returns a map keyed by ID:

```java
@Service
public class AuthorService {

    private final AuthorRepository authorRepository;

    public AuthorService(AuthorRepository authorRepository) {
        this.authorRepository = authorRepository;
    }

    public Map<Long, AuthorView> findByIds(Set<Long> authorIds) {
        Iterable<AuthorEntity> entities = authorRepository.findAllById(authorIds);

        return StreamSupport.stream(entities.spliterator(), false)
                .collect(Collectors.toMap(
                        AuthorEntity::getId,
                        entity -> new AuthorView(entity.getId(), entity.getName())));
    }
}
```

The batch mapping converts the ID-keyed map into a source-keyed map:

```java
@Controller
public class BookFieldController {

    private final AuthorService authorService;

    public BookFieldController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @BatchMapping(typeName = "Book", field = "author")
    public Map<BookView, AuthorView> author(List<BookView> books) {
        Set<Long> authorIds = books.stream()
                .map(BookView::authorId)
                .filter(Objects::nonNull)
                .collect(Collectors.toSet());

        Map<Long, AuthorView> authorsById = authorService.findByIds(authorIds);

        Map<BookView, AuthorView> result = new HashMap<>();
        for (BookView book : books) {
            result.put(book, authorsById.get(book.authorId()));
        }
        return result;
    }
}
```

There are two distinct lookup steps:

1. Collect the set of unique `authorId`s and call the service once to load the targets.
2. Iterate through each `BookView` source again, find the target by `authorId`, and add the source-target pair to the result map.

The repository can return data in any order. Because `authorsById` is indexed by ID, the final map-building step still pairs the right author with each book.

In the example, `authorId` can be null because the schema declares `author: Author` as nullable and book records might not have an author attached yet. If `authorId` is always required, you can drop the null filter and enforce the invariant in the model/service.

## 6. Why must the result key be the source object?

A common mistake is returning `Map<Long, AuthorView>` because `Long` is the book's ID. However, `@BatchMapping` needs to associate field values with each received source object. For the `Book.author` field, the result map must use the source `BookView` as the key:

```java
Map<BookView, AuthorView> result;
```

An ID-keyed map can serve as an intermediate structure for looking up targets:

```java
Map<Long, AuthorView> authorsById;
```

You must then convert it into a source-to-target map. Do not return the intermediate map if its key is not the source type received by the batch method.

Distinguishing the three map key types:

| Map | Role | Is it a source-to-target result for `@BatchMapping`? |
| --- | --- | --- |
| `Map<Long, AuthorView>` | Look up target by `authorId` | No, usually only an intermediate map |
| `Map<BookView, AuthorView>` | Match each source book with its target author | Yes |
| `Map<AuthorView, BookView>` | Reverse-map author to book | Not suitable for the `Book.author` field |

This rule changes depending on the field being batched. If the field is `Author.books`, the source is `AuthorView` and the target is a list of `BookView`; in that case, an appropriate result can be `Map<AuthorView, List<BookView>>`.

## 7. Using a Map for one-to-many relationships

`@BatchMapping` is not limited to one-to-one or many-to-one relationships. If one source has multiple targets, the map value can be a collection.

Schema:

```graphql
type Author {
    id: ID!
    name: String!
    books: [Book!]!
}
```

Java batch method:

```java
@BatchMapping(typeName = "Author", field = "books")
public Map<AuthorView, List<BookView>> books(List<AuthorView> authors) {
    Set<Long> authorIds = authors.stream()
            .map(AuthorView::id)
            .collect(Collectors.toSet());

    Map<Long, List<BookView>> booksByAuthorId = bookService.findByAuthorIds(authorIds);

    Map<AuthorView, List<BookView>> result = new HashMap<>();
    for (AuthorView author : authors) {
        result.put(
                author,
                booksByAuthorId.getOrDefault(author.id(), List.of()));
    }
    return result;
}
```

Here the source is `AuthorView`, and the target is `List<BookView>`. The final map still uses the source object as its key, while the value is the list of targets. If an author has no books yet, returning `List.of()` matches the `[Book!]!` schema better than null.

For many-to-many relationships, the service can query the join table by the set of source IDs, group the targets by source ID, and similarly construct `Map<Source, List<Target>>`.

## 8. Source-to-target Map vs. ordered list

Spring for GraphQL supports different batch result types. Two common approaches are:

| Return type | How results are matched | Primary requirement |
| --- | --- | --- |
| `Map<Source, Target>` | Matched by source object key | Each source needs an accurate mapping |
| `List<Target>` or `Flux<Target>` | Matched by input source index | Results must preserve exact order and matching count |

Example source list `[Book-A, Book-B, Book-C]`:

**Map:**

```java
Map<BookView, AuthorView> result = new HashMap<>();
result.put(bookA, author30);
result.put(bookB, author10);
result.put(bookC, author20);
```

**List:**

```java
List<AuthorView> result = List.of(author30, author10, author20);
```

The List must match the order `[Book-A, Book-B, Book-C]`. If the repository returns `[author10, author20, author30]` and the method returns it directly, data will be misassigned. A Map avoids that ordering requirement because each target is linked to its source by key.

When a target can be absent, a list must preserve its position with null if the loader contract permits; do not filter out null elements because that shifts the positions of subsequent sources. With a map, you can omit the entry for a source with no target; the field is then resolved to null according to mapped loader semantics. Always check the field's nullability in the SDL.

## 9. Using Map with source objects and equals/hashCode

Maps in Java use `equals` and `hashCode` to locate keys. Therefore, the keys in the result map must match the source objects handled by the framework.

With a record like `BookView`, Java automatically generates `equals` and `hashCode` based on the record components. When the batch method receives the `books` list, using the exact objects from that list as keys is straightforward:

```java
Map<BookView, AuthorView> result = new HashMap<>();
for (BookView book : books) {
    result.put(book, authorsById.get(book.authorId()));
}
```

Do not construct a separate `new BookView(...)` to use as a key if the source type's equality does not guarantee the two instances are equivalent. With JPA entities, be careful when `equals`/`hashCode` depend on ungenerated IDs, mutable fields, or proxies. Changing the hash code after inserting an object into a `HashMap` can make the entry unreachable.

If you need to map by ID because the source object has complex equality, you can use `DataLoader` or another batch abstraction with an explicit ID key. With `@BatchMapping`, however, the result must follow the framework's source-mapping contract; do not arbitrarily replace the source key with an ID.

## 10. Missing targets and nullability

Suppose a book references an `authorId` that no longer exists. There are several ways to handle this:

- Return null for the `author` field if the relationship is optional.
- Return a fallback target if the domain actually defines a substitute object.
- Throw an error if an invalid reference is an invariant violation that must be reported.

With the schema:

```graphql
type Book {
    author: Author
}
```

the `author` field is nullable, so a missing target can be represented as null. If the schema declares `author: Author!`, null is invalid; GraphQL will create an execution error and apply null propagation up to the nearest nullable parent field.

In the result map, you can insert the key with a null value when using `HashMap`, or omit the entry for that source. Both representations should be tested according to the loader's semantics and framework version. Do not use `Map.of(...)` if you need to store null values, because that factory rejects nulls.

For one-to-many relationships, if the schema declares `[Book!]!`, return an empty list when there are no books instead of null. An empty value and a non-existent value carry different meanings.

## 11. Sources with null or invalid target IDs

Before querying, the batch method should identify which sources have valid keys:

```java
Set<Long> authorIds = books.stream()
        .map(BookView::authorId)
        .filter(Objects::nonNull)
        .collect(Collectors.toSet());
```

Then when building the result:

```java
for (BookView book : books) {
    AuthorView author = book.authorId() == null
            ? null
            : authorsById.get(book.authorId());
    result.put(book, author);
}
```

Do not include null in the query ID set if the repository does not support it or if the query would be meaningless. If a source has a malformed ID, inconsistent data, or an invariant violation, handle it consistently with domain rules. Do not silently assign a default target to all invalid sources.

## 12. Reactive source-to-target mapping

In WebFlux applications or services returning publishers, a batch method can return `Mono<Map<Source, Target>>`:

```java
@BatchMapping(typeName = "Book", field = "author")
public Mono<Map<BookView, AuthorView>> author(List<BookView> books) {
    Set<Long> authorIds = books.stream()
            .map(BookView::authorId)
            .filter(Objects::nonNull)
            .collect(Collectors.toSet());

    return authorService.findByIds(authorIds)
            .map(authorsById -> {
                Map<BookView, AuthorView> result = new HashMap<>();
                for (BookView book : books) {
                    result.put(book, authorsById.get(book.authorId()));
                }
                return result;
            });
}
```

Assuming `authorService.findByIds` returns `Mono<Map<Long, AuthorView>>`, the mapping is constructed after the service completes and still uses the source objects as keys.

With blocking services like JPA/JDBC, you can return a synchronous `Map` in a Spring MVC application. In WebFlux, do not call `.block()` inside a batch method; use a reactive repository or isolate blocking calls on a bounded scheduler/executor.

## 13. Actual batching must happen in the service/repository

`@BatchMapping` collects source objects, but it does not automatically turn them into a single SQL query. The service must accept a set of IDs and query in bulk:

```java
public Map<Long, AuthorView> findByIds(Set<Long> ids) {
    Iterable<AuthorEntity> entities = authorRepository.findAllById(ids);
    return StreamSupport.stream(entities.spliterator(), false)
            .collect(Collectors.toMap(
                    AuthorEntity::getId,
                    authorMapper::toView));
}
```

If the batch method loops over sources and calls `findById` for each element, N+1 still persists:

```java
// Avoid: still triggers one query per source.
for (BookView book : books) {
    AuthorView author = authorService.findById(book.authorId());
    result.put(book, author);
}
```

Inspect the SQL or the number of times the service/repository is called. A method named `findByIds` is not enough to prove it batches; check its implementation to verify it actually uses a multi-ID query, a bulk endpoint, or a batch loading mechanism.

If the source list is large, you may need to split the ID set into chunks to avoid bind parameter limits or overly heavy queries. `@BatchMapping` can be configured with a batch size limit depending on the Spring for GraphQL version's API; when needed, check the `maxBatchSize` attribute of the annotation in your project's version.

## 14. Multiple sources sharing the same target

Multiple sources can point to the same target. For example, 30 books may share one author. The service should deduplicate IDs when querying:

```java
Set<Long> authorIds = books.stream()
        .map(BookView::authorId)
        .filter(Objects::nonNull)
        .collect(Collectors.toSet());
```

Then map each source to the same `AuthorView`:

```text
Book-A -> Author-7
Book-B -> Author-7
Book-C -> Author-7
```

A source-to-target map allows multiple keys to share the same value. This does not drop any source because each key is still an individual `BookView`. Avoid flipping the result into an `AuthorView -> BookView` map, as that structure only retains one book per author and loses the many-to-one relationship.

If two source objects are equal according to `equals`, a standard map only keeps one entry for that key. Ensure source keys have equality semantics appropriate for each source in the batch. For source DTOs representing distinct records, ID-based equality is usually sensible; for entities/proxies, review the equality implementation before using them as keys.

## 15. Authorization and request context

A batch may contain sources belonging to different tenants or permission scopes. Never assume that because sources appear in the same batch, the caller is authorized to view all targets.

The service or repository must enforce authorization per caller and per resource. For instance, if some authors belong to another tenant, the bulk query must filter by the authenticated tenant or check permissions before placing targets into the map.

Do not take a tenant ID from `authorId` or a client-supplied field and treat it as proof of access rights. Caller identity and tenant context must come from a trusted security context or request context. If the batch loader needs context, pass it via the appropriate Spring for GraphQL context mechanism or service security boundary.

If only some sources are unauthorized, decide whether to return null, emit per-field errors, or reject the entire batch. This choice must align with security policy and avoid unintentionally leaking whether a resource exists.

## 16. Testing source-to-target Map mapping

Tests should verify both the mapping result and that source-target matching stays accurate when the repository order differs from the source order.

Example query:

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

With `GraphQlTester`:

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
    .path("books[0].author.name")
    .entity(String.class)
    .isEqualTo("Author for Book A");
```

Important test cases:

1. Multiple sources are grouped into a single batch method call.
2. Repository returns targets in a different order from sources, yet the map still matches accurately.
3. Multiple sources pointing to the same target all receive the right target.
4. Sources with a null target ID are handled according to the chosen semantics.
5. Non-existent targets produce null or errors appropriate for nullability.
6. One-to-many relationships return the correct list for each source.
7. Source objects used as map keys have stable `equals`/`hashCode`.
8. Authorization and tenant filtering apply across the entire batch.
9. Service/repository is called in bulk, not once per source.
10. Reactive methods do not block and complete with the expected response.

Verifying only the response is not sufficient to prove batching works. Use spies/mocks or instrumentation to confirm service/repository call counts and the number of keys per batch.

## 17. Common pitfalls

- **Returning `Map<ID, Target>` instead of `Map<Source, Target>`:** GraphQL needs a map keyed by the source object; an ID map is usually only an intermediate structure.
- **Using the target as the key:** Reverses the relationship and can lose multiple sources pointing to the same target.
- **Returning a list in repository order:** Targets can be assigned to the wrong sources. Use a map or reorder to match the sources.
- **Filtering out null targets from a list:** Shifts positions when using an order-based return type.
- **Creating new source objects as map keys:** Incompatible equality can prevent the framework from finding the mapping.
- **Ignoring entity `equals`/`hashCode`:** Mutable IDs or proxies can make map keys unstable.
- **Querying once per source inside the batch method:** N+1 still exists.
- **Skipping sources with a null target ID:** Can leave out keys and cause fields to return unexpected results.
- **Using `Map.of` when null values are needed:** `Map.of` does not allow null keys or values.
- **Failing to handle absent targets:** Non-null fields can trigger unexpected null propagation.
- **Skipping per-resource authorization:** A batch can contain data from multiple permission scopes.
- **Registering both `@SchemaMapping` and `@BatchMapping` for the same field:** Can create duplicate data fetcher coordinates.

## 18. Workflow for implementing source-to-target batch mapping

When you need to load targets for multiple source objects, follow these steps:

1. Identify the GraphQL field and source object type, such as `Book.author`.
2. Declare `@BatchMapping(typeName = "Book", field = "author")`.
3. Accept `List<Source>` and determine the key used to look up targets.
4. Remove null or duplicate keys according to business semantics.
5. Call the bulk service/repository to load targets by the key set.
6. Build an intermediate map by target ID if needed.
7. Iterate over the source list and construct `Map<Source, Target>` using the exact source objects received.
8. Decide how to handle missing/null targets and ensure alignment with SDL nullability.
9. Verify `equals`/`hashCode` of source keys and access permissions on every target.
10. Test ordering, shared targets, missing targets, and backend query counts.

Mapping source to target is an explicit representation for batch fields in Spring for GraphQL. The source object serves as the key and the target field value serves as the value; the service can look up targets by ID and the batch method rebuilds the map by source. When using proper keys, handling absent targets per the schema, and performing true bulk queries, `@BatchMapping` helps nested fields both match data accurately and avoid N+1 without relying on repository result order.

## References

- [Spring for GraphQL — Batch Mapping](https://docs.spring.io/spring-graphql/reference/controllers.html#controllers.batch-mapping)
- [Spring for GraphQL — Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL — BatchLoaderRegistry](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/execution/BatchLoaderRegistry.html)
- [GraphQL Java — DataLoader batching](https://www.graphql-java.com/documentation/batching/)
- [GraphQL Specification — Field Execution](https://spec.graphql.org/October2021/#sec-Field-Execution)
